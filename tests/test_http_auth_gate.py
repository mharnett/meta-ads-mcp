"""The streamable-http transport must refuse callers that bring no credential.

Without a gate, a request with no token falls through to the tool handlers,
which then use the operator's own token (META_ACCESS_TOKEN or the OAuth
cache) on the anonymous caller's behalf. Binding to localhost does not close
that: any local process can connect, and mcp 1.12.2 leaves DNS-rebinding
protection off, so a web page can reach a localhost server too.

These tests drive the same app the transport serves: FastMCP.run
("streamable-http") calls ``self.streamable_http_app()``, which is the
method ``setup_fastmcp_http_auth`` patches. Each test builds a throwaway
FastMCP instance with one local tool, so nothing here reaches Meta.
"""

from __future__ import annotations

import json
import sys

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from meta_ads_mcp.core import http_auth_integration as hai
from meta_ads_mcp.core import server as server_mod
from meta_ads_mcp.core.http_auth_integration import (
    AuthInjectionMiddleware,
    FastMCPAuthIntegration,
    setup_fastmcp_http_auth,
)

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

CALL_WHOAMI = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "whoami", "arguments": {}},
}


def _gated_server(json_response: bool):
    """A fresh FastMCP with the auth gate installed and a tool that reports
    which token (if any) it sees. Returns (server, list_of_tool_calls)."""
    calls: list[str] = []
    server = FastMCP("auth-gate-test")
    server.settings.stateless_http = True
    server.settings.json_response = json_response

    @server.tool()
    async def whoami() -> str:
        token = FastMCPAuthIntegration.get_auth_token() or "<none>"
        calls.append(token)
        return token

    setup_fastmcp_http_auth(server)
    return server, calls


def _post(server, body, headers=None):
    app = server.streamable_http_app()
    with TestClient(app) as client:
        return client.post("/mcp", json=body, headers={**HEADERS, **(headers or {})})


def _tool_text(response) -> str:
    """Pull the tool's text result out of a JSON or SSE-framed response."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data_lines = [ln[len("data:"):].strip() for ln in response.text.splitlines() if ln.startswith("data:")]
        assert data_lines, f"no SSE data frame in: {response.text!r}"
        payload = json.loads(data_lines[-1])
    else:
        payload = response.json()
    return payload["result"]["content"][0]["text"]


@pytest.mark.parametrize("json_response", [True, False], ids=["json", "sse-response"])
def test_anonymous_request_is_refused_before_any_tool_runs(json_response):
    server, calls = _gated_server(json_response)

    r = _post(server, CALL_WHOAMI)

    assert r.status_code == 401, r.text
    assert r.headers.get("www-authenticate") == "Bearer"
    assert calls == [], "the tool ran for an anonymous caller"


@pytest.mark.parametrize(
    "header_value",
    ["Bearer ", "Bearer    ", "Basic dXNlcjpwYXNz"],
    ids=["empty-bearer", "whitespace-bearer", "basic-scheme"],
)
def test_authorization_header_without_a_bearer_token_is_refused(header_value):
    server, calls = _gated_server(json_response=True)

    r = _post(server, CALL_WHOAMI, {"Authorization": header_value})

    assert r.status_code == 401, r.text
    assert calls == []


@pytest.mark.parametrize("json_response", [True, False], ids=["json", "sse-response"])
def test_bearer_token_is_admitted_and_reaches_the_tool(json_response):
    server, calls = _gated_server(json_response)

    r = _post(server, CALL_WHOAMI, {"Authorization": "Bearer caller-own-token-123"})

    assert r.status_code == 200, r.text
    assert _tool_text(r) == "caller-own-token-123"
    assert calls == ["caller-own-token-123"]


def test_x_meta_access_token_header_is_admitted_and_reaches_the_tool():
    server, calls = _gated_server(json_response=True)

    r = _post(server, CALL_WHOAMI, {"X-META-ACCESS-TOKEN": "caller-meta-token-456"})

    assert r.status_code == 200, r.text
    assert calls == ["caller-meta-token-456"]


def test_both_app_providers_carry_the_gate():
    """streamable_http_app is the served app in both response modes; sse_app
    is patched too so a future SDK routing change can't serve an ungated app.
    Each patched provider must call its own original, not the loop's last."""
    server, _ = _gated_server(json_response=True)

    http_app = server.streamable_http_app()
    sse_app = server.sse_app()

    for app in (http_app, sse_app):
        assert any(m.cls is AuthInjectionMiddleware for m in app.user_middleware), app
    http_paths = {getattr(r, "path", None) for r in http_app.routes}
    sse_paths = {getattr(r, "path", None) for r in sse_app.routes}
    assert server.settings.streamable_http_path in http_paths
    assert server.settings.sse_path in sse_paths
    assert server.settings.sse_path not in http_paths


def test_middleware_install_failure_fails_closed(monkeypatch):
    """If the gate can't be attached, building the served app must raise,
    not hand back an app with no gate on it."""
    server, _ = _gated_server(json_response=True)

    def refuse(self, *args, **kwargs):
        raise RuntimeError("simulated add_middleware failure")

    monkeypatch.setattr("starlette.applications.Starlette.add_middleware", refuse)

    with pytest.raises(RuntimeError, match="simulated add_middleware failure"):
        server.streamable_http_app()


def test_main_refuses_to_start_http_when_the_gate_cannot_be_installed(monkeypatch):
    """server.main() must exit non-zero, and never start serving, when
    setup_fastmcp_http_auth fails."""
    started = []
    gate_installs = []

    def broken_setup(_server):
        raise RuntimeError("simulated gate setup failure")

    monkeypatch.setattr(hai, "setup_fastmcp_http_auth", broken_setup)
    monkeypatch.setattr(server_mod.mcp_server, "run", lambda *a, **k: started.append((a, k)))
    monkeypatch.setattr(server_mod, "install_write_gate", lambda *a, **k: gate_installs.append(a))
    # main() writes these onto the shared server; restore them afterwards.
    for attr in ("host", "port", "stateless_http", "json_response"):
        monkeypatch.setattr(server_mod.mcp_server.settings, attr, getattr(server_mod.mcp_server.settings, attr))
    monkeypatch.setattr(sys, "argv", ["meta-ads-mcp", "--transport", "streamable-http", "--port", "18080"])

    rc = server_mod.main()

    assert rc not in (None, 0), f"main() returned {rc!r} after the auth gate failed to install"
    assert started == [], "the HTTP server was started without its auth gate"
