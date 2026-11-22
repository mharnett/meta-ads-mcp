"""Smoke tests for the streamable-http transport.

These are the few things that ONLY a real HTTP transport can verify:
- JSON-RPC 2.0 envelope shape (jsonrpc/id/result)
- A full tool-call round trip through the wire
- Authorization header acceptance

The autostart fixture spawns `python -m meta_ads_mcp --transport streamable-http`
in a subprocess at session start and polls for readiness. If the subprocess
cannot be started (port collision, import error, etc.), the fixture raises —
it never silently skips. That is the whole point of moving away from the
previous `check_server_running` skip pattern.

In-process tool behavior is covered by `test_campaign_objective_filter.py`
and `test_ad_formats_flexible.py` etc.; this file only validates the HTTP
transport itself.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT_S = 20.0
SHUTDOWN_TIMEOUT_S = 3.0


def _pick_free_port() -> int:
    """Discover a free localhost TCP port. There is a small race between
    closing the socket and the child binding, but it is fine for a single
    test session."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_ready(url: str, proc: subprocess.Popen, timeout: float) -> None:
    """Poll the root URL until it answers. Raise if the process dies first
    or the timeout elapses. Never returns success silently on a dead server."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = ""
            if proc.stderr is not None:
                try:
                    stderr = proc.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
            raise RuntimeError(
                f"MCP server subprocess exited with code {proc.returncode} "
                f"before becoming ready.\nstderr:\n{stderr}"
            )
        try:
            # Authenticated, so readiness doesn't hinge on the 401 gate.
            r = requests.get(url + "/", headers=AUTH, timeout=1.0)
            # FastMCP returns 404 at "/" — that's a live server.
            if r.status_code in (200, 404):
                return
        except requests.exceptions.RequestException as e:
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(
        f"MCP server did not become ready at {url} within {timeout}s. "
        f"Last connection error: {last_err!r}"
    )


def _spawn_server(extra_args=()):
    """Spawn the MCP server as a subprocess and yield it until teardown.

    Yields a dict with the bound URL and the live Popen object. Hard-fails
    (does NOT skip) if the subprocess cannot be started or never becomes
    ready — that is intentional. A smoke suite that silently skips on
    startup failure provides no signal.
    """
    port = _pick_free_port()
    url = f"http://127.0.0.1:{port}"
    cmd = [
        sys.executable,
        "-m",
        "meta_ads_mcp",
        "--transport",
        "streamable-http",
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
        *extra_args,
    ]
    env = os.environ.copy()
    # Strip every META_* / PIPEBOARD_* var, not just the token. This fixture
    # is session-scoped, so it copies os.environ before the per-test
    # _isolate_auth_env fixture runs, and an earlier test that set
    # META_APP_ID directly leaks into the child. With one leaked, the
    # server's tools tried a real Graph call in a full-suite run.
    for k in list(env):
        if k.startswith(("META_", "PIPEBOARD_")):
            env.pop(k)

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        _wait_for_ready(url, proc, STARTUP_TIMEOUT_S)
    except Exception:
        # Make sure we don't leak the process if startup blew up.
        proc.kill()
        proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
        raise

    try:
        yield {"url": url, "port": port, "process": proc}
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=SHUTDOWN_TIMEOUT_S)


@pytest.fixture(scope="session")
def mcp_http_server():
    yield from _spawn_server()


@pytest.fixture(scope="session")
def mcp_http_server_sse():
    yield from _spawn_server(["--sse-response"])


# Any non-empty bearer admits the request; the tools below never send it
# anywhere (tools/list and compute_image_crops make no Graph call).
AUTH = {"Authorization": "Bearer smoke-test-not-a-real-token"}


def _post_jsonrpc(server, method, params=None, extra_headers=None, req_id=1):
    """POST a JSON-RPC request. We POST to `/mcp` (no trailing slash) to
    avoid the 307 redirect that FastMCP issues from `/mcp/`."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if extra_headers:
        headers.update(extra_headers)
    payload = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        payload["params"] = params
    return requests.post(
        f"{server['url']}/mcp", headers=headers, json=payload, timeout=10
    )


def test_server_root_responds(mcp_http_server):
    """Confirm the autostarted server is up. If the autostart fixture
    succeeded, this is essentially a no-op — but it documents the
    expected baseline."""
    r = requests.get(f"{mcp_http_server['url']}/", headers=AUTH, timeout=5)
    assert r.status_code in (200, 404)


def test_tools_list_returns_well_formed_jsonrpc(mcp_http_server):
    """JSON-RPC 2.0 framing: tools/list response has jsonrpc/id/result."""
    r = _post_jsonrpc(mcp_http_server, "tools/list", params={}, extra_headers=AUTH, req_id=42)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 42
    assert "result" in body, body
    tools = body["result"].get("tools")
    assert isinstance(tools, list)
    assert len(tools) > 0
    tool_names = {t["name"] for t in tools}
    # Sanity check: at least one well-known tool is registered.
    assert "get_campaigns" in tool_names


def test_tool_call_round_trip(mcp_http_server):
    """End-to-end JSON-RPC tools/call round trip for an authenticated caller.

    compute_image_crops is pure arithmetic, so the round trip proves
    transport, dispatch and serialization without any Graph call."""
    r = _post_jsonrpc(
        mcp_http_server,
        "tools/call",
        params={"name": "compute_image_crops", "arguments": {"image_width": 1080, "image_height": 1080}},
        extra_headers=AUTH,
        req_id=7,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 7
    assert "result" in body, body
    content = body["result"].get("content", [])
    assert content, body
    assert "100x100" in content[0].get("text", "")


@pytest.mark.parametrize("server_fixture", ["mcp_http_server", "mcp_http_server_sse"])
def test_anonymous_tool_call_is_refused_over_the_wire(server_fixture, request):
    """No credential header: the real server answers 401 before dispatch,
    in both response modes, instead of running the tool on the operator's
    token."""
    server = request.getfixturevalue(server_fixture)
    r = _post_jsonrpc(
        server,
        "tools/call",
        params={"name": "get_ad_accounts", "arguments": {"limit": 1}},
        req_id=8,
    )
    assert r.status_code == 401, r.text
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_authorization_header_accepted(mcp_http_server):
    """Server accepts an Authorization: Bearer header and returns 200 with
    a JSON-RPC result envelope. We don't assert on auth success — only that
    the header doesn't cause the transport to reject the request."""
    r = _post_jsonrpc(
        mcp_http_server,
        "tools/list",
        params={},
        extra_headers={"Authorization": "Bearer test_bearer_token_12345"},
        req_id=99,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 99
    assert "result" in body
