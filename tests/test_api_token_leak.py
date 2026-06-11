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
