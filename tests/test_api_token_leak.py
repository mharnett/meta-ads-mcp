"""Test that access tokens are not leaked in error responses."""
import pytest
import sys
from pathlib import Path

# Add the source directory to the path so we can import just the function module
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTokenRedaction:
    """Verify token redaction function works correctly."""

    def test_redact_access_token_from_url_removes_token(self):
        """redact_access_token_from_url removes access_token parameter."""
        from meta_ads_mcp.core.api import redact_access_token_from_url

        url_with_token = "https://graph.facebook.com/v24.0/ads?access_token=LIVE_TOKEN_60DAY"
        redacted = redact_access_token_from_url(url_with_token)

        assert "access_token=" not in redacted
        assert "LIVE_TOKEN_60DAY" not in redacted

    def test_redact_preserves_endpoint(self):
        """Redacted URL preserves the endpoint."""
        from meta_ads_mcp.core.api import redact_access_token_from_url

        url_with_token = "https://graph.facebook.com/v24.0/ads?access_token=TOKEN"
        redacted = redact_access_token_from_url(url_with_token)

        assert "graph.facebook.com" in redacted
        assert "/ads" in redacted

    def test_redact_preserves_other_params(self):
        """redact_access_token_from_url preserves non-sensitive params."""
        from meta_ads_mcp.core.api import redact_access_token_from_url

        url = "https://graph.facebook.com/v24.0/ads?account_id=123&access_token=TOKEN&limit=10"
        redacted = redact_access_token_from_url(url)

        assert "account_id=123" in redacted
        assert "limit=10" in redacted
        assert "access_token=" not in redacted


class TestCallerParamsNotMutated:
    """make_api_request must not inject credentials into the caller's dict.

    Ported from upstream pipeboard-co/meta-ads-mcp 555ae48 (PR #145). The
    function took params by reference and then set request_params["access_token"],
    so the caller's own dict came back carrying the live Meta token. Any tool
    that echoes its params to the user *after* the call then leaked it — in this
    fork that is update_ad_creative, which returns "attempted_updates" on Meta
    error subcode 1815573 and "update_data_sent" from its exception handler
    (core/ads.py), both of which echo the same dict handed to make_api_request.
    """

    TOKEN = "LEAKED_IF_MUTATED_0123456789"

    @staticmethod
    def _mock_client(captured):
        """AsyncClient stand-in that records the params it was handed."""
        from unittest.mock import AsyncMock, MagicMock

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": []}
        response.raise_for_status.return_value = None

        client = MagicMock()
        for verb in ("get", "delete"):
            setattr(client, verb, AsyncMock(
                side_effect=lambda *a, **kw: captured.update(kw.get("params") or {}) or response
            ))
        client.post = AsyncMock(
            side_effect=lambda *a, **kw: captured.update(kw.get("data") or {}) or response
        )

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=ctx)

    async def test_get_does_not_inject_token_into_callers_params(self):
        from unittest.mock import patch
        from meta_ads_mcp.core.api import make_api_request

        caller_params = {"fields": "id,name"}
        captured = {}
        with patch("meta_ads_mcp.core.api.httpx.AsyncClient", self._mock_client(captured)):
            await make_api_request("act_123/ads", self.TOKEN, caller_params)

        assert caller_params == {"fields": "id,name"}
        assert "access_token" not in caller_params
        assert self.TOKEN not in str(caller_params)

    async def test_post_does_not_inject_token_into_callers_params(self):
        from unittest.mock import patch
        from meta_ads_mcp.core.api import make_api_request

        # Mirrors update_ad_creative's shape: the dict it later echoes back as
        # "attempted_updates" / "update_data_sent".
        update_data = {"name": "New creative name"}
        captured = {}
        with patch("meta_ads_mcp.core.api.httpx.AsyncClient", self._mock_client(captured)):
            await make_api_request("123456/", self.TOKEN, update_data, method="POST")

        assert update_data == {"name": "New creative name"}
        assert "access_token" not in update_data

    async def test_token_still_reaches_the_wire(self):
        """Anchor: the fix must not stop sending the token, only stop mutating."""
        from unittest.mock import patch
        from meta_ads_mcp.core.api import make_api_request

        caller_params = {"fields": "id,name"}
        captured = {}
        with patch("meta_ads_mcp.core.api.httpx.AsyncClient", self._mock_client(captured)):
            await make_api_request("act_123/ads", self.TOKEN, caller_params)

        assert captured.get("access_token") == self.TOKEN
        assert captured.get("fields") == "id,name"

    async def test_none_params_is_still_accepted(self):
        from unittest.mock import patch
        from meta_ads_mcp.core.api import make_api_request

        captured = {}
        with patch("meta_ads_mcp.core.api.httpx.AsyncClient", self._mock_client(captured)):
            result = await make_api_request("act_123/ads", self.TOKEN, None)

        assert result == {"data": []}
        assert captured.get("access_token") == self.TOKEN

    async def test_same_dict_reused_across_two_calls_stays_clean(self):
        """A caller that reuses one params dict must not accumulate credentials."""
        from unittest.mock import patch
        from meta_ads_mcp.core.api import make_api_request

        caller_params = {"fields": "id"}
        captured = {}
        with patch("meta_ads_mcp.core.api.httpx.AsyncClient", self._mock_client(captured)):
            await make_api_request("act_123/ads", self.TOKEN, caller_params)
            await make_api_request("act_123/adsets", "SECOND_TOKEN_VALUE", caller_params)

        assert caller_params == {"fields": "id"}
