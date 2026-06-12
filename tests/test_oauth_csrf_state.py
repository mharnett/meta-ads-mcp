"""OAuth CSRF / authorization-code-flow tests (issue H6).

These lock down the migration from implicit grant (response_type=token, token
exposed in the redirect URL) to the authorization code flow with proper CSRF
`state` validation.

Behaviors under test:
  1. The OAuth authorization URL uses response_type=code (NOT token).
  2. A random `state` of sufficient entropy is generated and embedded in the URL.
  3. The generated `state` is recorded so the callback can validate it.
  4. The callback ACCEPTS a code only when the returned state matches.
  5. The callback REJECTS (does not store the code) when the state mismatches.
"""

import re
from urllib.parse import urlparse, parse_qs

import pytest

from meta_ads_mcp.core import auth as auth_mod
from meta_ads_mcp.core import callback_server as cb


@pytest.fixture
def manager():
    return auth_mod.AuthManager("123456789", redirect_uri="http://localhost:8080/callback")


def _query(url):
    return parse_qs(urlparse(url).query)


class TestAuthorizationCodeFlow:
    def test_response_type_is_code_not_token(self, manager):
        """Authorization URL must request a code, never an implicit token."""
        q = _query(manager.get_auth_url())
        assert q.get("response_type") == ["code"], (
            f"expected response_type=code, got {q.get('response_type')}"
        )

    def test_state_parameter_is_generated(self, manager):
        """A `state` parameter must be present in the URL."""
        q = _query(manager.get_auth_url())
        assert "state" in q, "OAuth URL must include a state parameter"
        assert q["state"][0], "state must be non-empty"

    def test_state_has_sufficient_entropy(self, manager):
        """state must be a high-entropy random value (>= 32 bytes -> long token)."""
        state = _query(manager.get_auth_url())["state"][0]
        # token_urlsafe(32) yields ~43 url-safe chars; require >= 32 chars and
        # only url-safe alphabet.
        assert len(state) >= 32, f"state too short ({len(state)} chars) for CSRF safety"
        assert re.fullmatch(r"[A-Za-z0-9_-]+", state), "state must be url-safe random"

    def test_state_differs_between_calls(self, manager):
        """Each authorization request must mint a fresh state."""
        s1 = _query(manager.get_auth_url())["state"][0]
        s2 = _query(manager.get_auth_url())["state"][0]
        assert s1 != s2, "state must be regenerated per request"

    def test_generated_state_is_recorded_for_validation(self, manager):
        """The generated state must be stored so the callback can compare it."""
        state = _query(manager.get_auth_url())["state"][0]
        assert cb.token_container.get("expected_state") == state


class TestCallbackStateValidation:
    def setup_method(self):
        # reset shared container between tests
        cb.token_container.clear()
        cb.token_container.update({"token": None, "expires_in": None, "user_id": None})

    def test_matching_state_accepts_code(self):
        cb.token_container["expected_state"] = "good-state-value"
        result = cb.validate_and_store_callback(code="the-code", state="good-state-value")
        assert result is True
        assert cb.token_container.get("auth_code") == "the-code"

    def test_mismatched_state_rejects_code(self):
        cb.token_container["expected_state"] = "good-state-value"
        result = cb.validate_and_store_callback(code="the-code", state="attacker-state")
        assert result is False, "mismatched state must be rejected"
        assert cb.token_container.get("auth_code") is None, (
            "code from a CSRF/forged callback must NOT be stored"
        )

    def test_missing_state_rejects_code(self):
        cb.token_container["expected_state"] = "good-state-value"
        result = cb.validate_and_store_callback(code="the-code", state=None)
        assert result is False
        assert cb.token_container.get("auth_code") is None

    def test_no_expected_state_rejects_code(self):
        # If we never initiated a flow, any inbound callback is forged.
        cb.token_container.pop("expected_state", None)
        result = cb.validate_and_store_callback(code="the-code", state="whatever")
        assert result is False
        assert cb.token_container.get("auth_code") is None
