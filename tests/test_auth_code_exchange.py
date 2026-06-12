"""Tests for the OAuth authorization-code → access-token exchange.

H6 migrated to authorization-code flow (response_type=code). The callback now
stores an ``auth_code`` in token_container, but the code was never exchanged for
an access token. These tests pin the server-side code→token exchange:

  - exchange_authorization_code_for_token() POSTs to Meta's OAuth endpoint with
    the right params and returns a TokenInfo on success / None on error.
  - process_token_response() routes on the presence of ``auth_code``:
      * auth_code present  → exchange code, store resulting token
      * invalid code       → error path, no token stored
      * no auth_code, direct token present → old implicit path still works
"""

import os
from unittest.mock import patch, MagicMock

from meta_ads_mcp.core.auth import (
    AuthManager,
    TokenInfo,
    process_token_response,
    exchange_authorization_code_for_token,
)

EXPECTED_URL = "https://graph.instagram.com/v24.0/oauth/access_token"
REDIRECT_URI = "http://localhost:8888/callback"


def _mock_post(*, status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# exchange_authorization_code_for_token
# ---------------------------------------------------------------------------

def test_exchange_code_posts_correct_params_and_returns_token():
    """Success: POSTs to Meta's OAuth endpoint with the documented params and
    returns a TokenInfo carrying access_token + expires_in."""
    os.environ["META_APP_ID"] = "app-123"
    os.environ["META_APP_SECRET"] = "secret-xyz"
    try:
        with patch("meta_ads_mcp.core.auth.meta_config.get_app_id", return_value="app-123"), \
             patch("meta_ads_mcp.core.auth.requests.post") as mock_post:
            mock_post.return_value = _mock_post(
                json_data={"access_token": "tok-abc", "expires_in": 5184000}
            )

            info = exchange_authorization_code_for_token("the-code", REDIRECT_URI)

            assert info is not None
            assert info.access_token == "tok-abc"
            assert info.expires_in == 5184000

            # Verify the request shape.
            args, kwargs = mock_post.call_args
            url = args[0] if args else kwargs.get("url")
            assert url == EXPECTED_URL
            sent = kwargs.get("data") or kwargs.get("params") or {}
            assert sent["client_id"] == "app-123"
            assert sent["client_secret"] == "secret-xyz"
            assert sent["redirect_uri"] == REDIRECT_URI
            assert sent["code"] == "the-code"
            assert sent["grant_type"] == "authorization_code"
    finally:
        os.environ.pop("META_APP_SECRET", None)


def test_exchange_code_error_returns_none():
    """Error: a non-200 from Meta returns None and does not raise."""
    os.environ["META_APP_SECRET"] = "secret-xyz"
    try:
        with patch("meta_ads_mcp.core.auth.meta_config.get_app_id", return_value="app-123"), \
             patch("meta_ads_mcp.core.auth.requests.post") as mock_post:
            mock_post.return_value = _mock_post(
                status_code=400, json_data={}, text="invalid code"
            )

            info = exchange_authorization_code_for_token("bad-code", REDIRECT_URI)
            assert info is None
    finally:
        os.environ.pop("META_APP_SECRET", None)


def test_exchange_code_missing_secret_returns_none():
    """No app_secret configured → cannot exchange, returns None (no request)."""
    os.environ.pop("META_APP_SECRET", None)
    with patch("meta_ads_mcp.core.auth.meta_config.get_app_id", return_value="app-123"), \
         patch("meta_ads_mcp.core.auth.requests.post") as mock_post:
        info = exchange_authorization_code_for_token("the-code", REDIRECT_URI)
        assert info is None
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# process_token_response routing
# ---------------------------------------------------------------------------

def test_process_token_response_exchanges_auth_code():
    """auth_code present → exchange code → token stored on the manager."""
    mgr = AuthManager("app-123")
    mgr.token_info = None
    container = {"auth_code": "the-code", "redirect_uri": REDIRECT_URI}

    fake_token = TokenInfo(access_token="exchanged-tok", expires_in=5184000)
    with patch(
        "meta_ads_mcp.core.auth.exchange_authorization_code_for_token",
        return_value=fake_token,
    ) as mock_exchange:
        ok = process_token_response(container, auth_manager=mgr)

    assert ok is True
    assert mgr.token_info is not None
    assert mgr.token_info.access_token == "exchanged-tok"
    mock_exchange.assert_called_once_with("the-code", REDIRECT_URI)


def test_process_token_response_invalid_code_stores_no_token():
    """auth_code present but exchange fails → no token stored, returns False."""
    mgr = AuthManager("app-123")
    mgr.token_info = None
    container = {"auth_code": "bad-code", "redirect_uri": REDIRECT_URI}

    with patch(
        "meta_ads_mcp.core.auth.exchange_authorization_code_for_token",
        return_value=None,
    ):
        ok = process_token_response(container, auth_manager=mgr)

    assert ok is False
    assert mgr.token_info is None


def test_process_token_response_backward_compat_direct_token():
    """No auth_code, direct token present → old implicit path still stores it."""
    mgr = AuthManager("app-123")
    mgr.token_info = None
    os.environ.pop("META_APP_SECRET", None)  # no long-lived exchange → short-lived
    container = {"token": "y" * 40, "expires_in": 3600}

    ok = process_token_response(container, auth_manager=mgr)

    assert ok is True
    assert mgr.token_info is not None
    assert mgr.token_info.access_token == "y" * 40
