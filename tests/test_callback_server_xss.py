"""Regression tests for GHSA-6v2r-2m4r-768m (ported from upstream 271ea4c).

The OAuth callback server reflected the `error` query parameter into an HTML
error page with no output encoding, so any page in the browser could navigate
to http://localhost:8080-8089/callback?error=<script>... while the callback
server was up and run script on the localhost origin.

Adapted to this fork's callback: the CSRF state lives in
``token_container['expected_state']`` (minted by ``AuthManager.get_auth_url``),
not upstream's ``new_oauth_state()``.
"""

import threading
from http.server import HTTPServer
from urllib.parse import quote

import httpx
import pytest

from meta_ads_mcp.core import callback_server
from meta_ads_mcp.core.callback_server import CallbackHandler, token_container

# Read with a default so a missing constant fails test_module_exposes_cap_constant
# alone, instead of a collection error hiding every behavioural assertion.
MAX_ERROR_DISPLAY_LENGTH = getattr(callback_server, "MAX_ERROR_DISPLAY_LENGTH", 200)

XSS_PAYLOAD = "<script>alert(document.domain)</script>"


@pytest.fixture
def callback_url():
    """Run a real CallbackHandler on an ephemeral localhost port."""
    server = HTTPServer(("localhost", 0), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    saved = dict(token_container)
    try:
        yield f"http://localhost:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        token_container.clear()
        token_container.update(saved)


def test_error_parameter_is_html_escaped(callback_url):
    response = httpx.get(f"{callback_url}/callback?error={quote(XSS_PAYLOAD)}")

    assert response.status_code == 200
    assert XSS_PAYLOAD not in response.text
    assert "<script>" not in response.text
    # The error is still shown to the user, just entity-encoded.
    assert "&lt;script&gt;" in response.text
    assert "Authorization Failed" in response.text


def test_error_parameter_cannot_break_out_of_attributes(callback_url):
    payload = '" onload="alert(1)'
    response = httpx.get(f"{callback_url}/callback?error={quote(payload)}")

    assert 'onload="alert(1)' not in response.text
    assert "&quot;" in response.text


def test_error_parameter_is_truncated(callback_url):
    payload = "A" * (MAX_ERROR_DISPLAY_LENGTH + 500)
    response = httpx.get(f"{callback_url}/callback?error={payload}")

    assert "A" * MAX_ERROR_DISPLAY_LENGTH in response.text
    assert "A" * (MAX_ERROR_DISPLAY_LENGTH + 1) not in response.text


@pytest.mark.parametrize(
    "query",
    ["error=access_denied", "code=c&state=wrong", "", "code=c"],
)
def test_every_non_success_page_sets_locked_down_headers(callback_url, query):
    token_container["expected_state"] = "expected-state-value"
    response = httpx.get(f"{callback_url}/callback?{query}")

    assert response.headers["content-security-policy"] == "default-src 'none'"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_success_page_allows_only_its_own_nonced_script(callback_url):
    token_container["expected_state"] = "expected-state-value"
    response = httpx.get(
        f"{callback_url}/callback?code=test-auth-code&state=expected-state-value"
    )

    assert "Authorization Successful" in response.text
    csp = response.headers["content-security-policy"]
    assert csp.startswith("default-src 'none'; script-src 'nonce-")
    nonce = csp.split("'nonce-")[1].rstrip("'")
    # The inline script carries the nonce, so an injected script would not run.
    assert f'<script nonce="{nonce}">' in response.text
    assert response.text.count("<script") == 1
    assert response.headers["x-content-type-options"] == "nosniff"


def test_nonce_differs_per_response(callback_url):
    nonces = []
    for _ in range(2):
        token_container["expected_state"] = "expected-state-value"
        response = httpx.get(
            f"{callback_url}/callback?code=c&state=expected-state-value"
        )
        nonces.append(response.headers["content-security-policy"])
    assert nonces[0] != nonces[1]


def test_module_exposes_cap_constant():
    assert callback_server.MAX_ERROR_DISPLAY_LENGTH == 200
