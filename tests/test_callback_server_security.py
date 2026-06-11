"""Test callback server security."""
import pytest
from pathlib import Path


class TestCallbackServerSecurity:
    """Verify callback server doesn't expose unauthenticated /token endpoint."""

    def test_token_endpoint_removed(self):
        """The /token endpoint should not exist (removed for security)."""
        callback_server_path = Path(__file__).parent.parent / "meta_ads_mcp" / "core" / "callback_server.py"
        content = callback_server_path.read_text()

        # The _handle_token method should not exist
        assert "_handle_token" not in content, "Unauthenticated /token endpoint should be removed"

    def test_no_unauthenticated_token_response(self):
        """Callback server should not serve tokens without authentication."""
        callback_server_path = Path(__file__).parent.parent / "meta_ads_mcp" / "core" / "callback_server.py"
        content = callback_server_path.read_text()

        # Should not have a path handler for /token
        assert "self.path.startswith(\"/token\")" not in content
        assert 'self.path.startswith("/token")' not in content

    def test_only_callback_endpoint(self):
        """Only /callback endpoint should be handled."""
        callback_server_path = Path(__file__).parent.parent / "meta_ads_mcp" / "core" / "callback_server.py"
        content = callback_server_path.read_text()

        # Should handle /callback
        assert "/callback" in content
        # But should not serve arbitrary token over HTTP
        assert "token_container" not in content or "_handle_token" not in content
