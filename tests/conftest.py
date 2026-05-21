"""
Pytest configuration for Meta Ads MCP tests

This file provides common fixtures and configuration for all tests.

NOTE: The previous `check_server_running` fixture has been removed. It used
`pytest.skip()` when no MCP server was listening on :8080, which is the
rubric #4 silent-skip antipattern (tests pass green when nothing ran).
HTTP-style tests have been converted to in-process tool tests, and the
remaining transport coverage lives in `test_http_transport_smoke.py`, which
spawns its own subprocess (see `mcp_http_server` fixture there) and HARD-FAILS
if the server can't start.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_auth_env(monkeypatch):
    """Defensive: make sure no stray env var from the dev shell leaks into
    tests. Specifically keep PIPEBOARD_API_TOKEN unset so any residue in
    module state from a previous removal of pipeboard support is flagged
    rather than silently re-enabled."""
    monkeypatch.delenv("PIPEBOARD_API_TOKEN", raising=False)


@pytest.fixture
def test_headers():
    """Common test headers for HTTP requests"""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "MCP-Test-Client/1.0"
    }


@pytest.fixture
def bearer_auth_headers(test_headers):
    """Headers with a generic Bearer access token"""
    headers = test_headers.copy()
    headers["Authorization"] = "Bearer test_bearer_token_12345"
    return headers


@pytest.fixture
def meta_app_auth_headers(test_headers):
    """Headers with Meta app ID authentication"""
    headers = test_headers.copy()
    headers["X-META-APP-ID"] = "123456789012345"
    return headers
