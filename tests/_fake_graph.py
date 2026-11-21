"""Shared fakes for tests that drive the real server startup path.

Two pieces:

* ``fake_graph``: replaces the HTTP layer ``make_api_request`` uses
  (``httpx.AsyncClient``) with an ``httpx.MockTransport`` that records every
  request and answers 200 with a canned body. It also blocks real sockets,
  so a code path that bypasses httpx fails loudly instead of reaching the
  network. Nothing here reads a credential: the access token is a fake
  string supplied through ``META_ACCESS_TOKEN``.

* ``started_server``: runs the real console-script entry point
  (``meta_ads_mcp:entrypoint`` -> ``server.main()``) with ``mcp_server.run``
  stubbed, so startup does everything it does in production (argument
  parsing, ``install_write_gate``) except block on a transport. The module
  singleton is restored afterwards so later tests see an ungated server.

``dispatch_call`` / ``dispatch_list`` go through the low-level MCP request
handlers, the same entry a stdio or HTTP client hits.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs

import httpx
import pytest
from mcp import types


FAKE_TOKEN = "FAKE_TEST_TOKEN_not_a_real_credential_000000"
FAKE_RESPONSE: Dict[str, Any] = {"id": "990000000000001", "success": True, "data": []}

_REAL_ASYNC_CLIENT = httpx.AsyncClient
_MISSING = object()


@dataclass
class RecordedRequest:
    method: str
    url: str
    form: Dict[str, str]
    query: Dict[str, str]


@dataclass
class GraphRecorder:
    requests: List[RecordedRequest] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        form = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
        query = {k: v[0] for k, v in parse_qs(request.url.query.decode("utf-8"), keep_blank_values=True).items()}
        url = str(request.url.copy_with(query=None))
        self.requests.append(RecordedRequest(request.method, url, form, query))
        return httpx.Response(200, json=FAKE_RESPONSE)


def _blocked(*_args: Any, **_kwargs: Any):
    raise RuntimeError("Real network access is blocked in this test")


@pytest.fixture
def fake_graph(monkeypatch) -> GraphRecorder:
    recorder = GraphRecorder()
    transport = httpx.MockTransport(recorder.handler)

    def _client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setenv("META_ACCESS_TOKEN", FAKE_TOKEN)
    return recorder


@pytest.fixture
def started_server(monkeypatch) -> Callable[..., Any]:
    """Return ``start(*argv)``: run the real entry point, return the server.

    Restores the ``mcp_server`` singleton (instance attributes, low-level
    handlers, tool cache, settings) and the module-level token resolvers the
    HTTP branch patches, so gating installed here cannot leak into other
    tests.
    """
    import meta_ads_mcp
    from meta_ads_mcp.core import api, auth, authentication
    from meta_ads_mcp.core import server as server_module

    srv = server_module.mcp_server
    lowlevel = srv._mcp_server
    saved_dict = dict(srv.__dict__)
    saved_handlers = dict(lowlevel.request_handlers)
    saved_cache = dict(lowlevel._tool_cache)
    resolver_modules = (auth, api, authentication)
    saved_resolvers = [
        (mod, mod.__dict__.get("get_current_access_token", _MISSING))
        for mod in resolver_modules
    ]

    run_calls: List[Dict[str, Any]] = []

    def start(*argv: str):
        # main() mutates settings in place on the HTTP branch; give it a copy.
        srv.settings = srv.settings.model_copy()
        srv.run = lambda transport="stdio", **kw: run_calls.append({"transport": transport, **kw})
        monkeypatch.setattr(sys, "argv", ["meta-ads-mcp", *argv])
        meta_ads_mcp.entrypoint()
        assert run_calls, "entrypoint() returned without reaching mcp_server.run"
        return srv

    start.run_calls = run_calls  # type: ignore[attr-defined]

    yield start

    srv.__dict__.clear()
    srv.__dict__.update(saved_dict)
    lowlevel.request_handlers.clear()
    lowlevel.request_handlers.update(saved_handlers)
    lowlevel._tool_cache.clear()
    lowlevel._tool_cache.update(saved_cache)
    for mod, value in saved_resolvers:
        if value is _MISSING:
            mod.__dict__.pop("get_current_access_token", None)
        else:
            mod.get_current_access_token = value


def dispatch_call(srv: Any, name: str, arguments: Optional[Dict[str, Any]] = None) -> types.CallToolResult:
    handler = srv._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    return asyncio.run(handler(request)).root


def dispatch_list(srv: Any) -> List[str]:
    handler = srv._mcp_server.request_handlers[types.ListToolsRequest]
    request = types.ListToolsRequest(method="tools/list")
    return [t.name for t in asyncio.run(handler(request)).root.tools]


def result_text(result: types.CallToolResult) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


def result_json(result: types.CallToolResult) -> Dict[str, Any]:
    return json.loads(result_text(result))
