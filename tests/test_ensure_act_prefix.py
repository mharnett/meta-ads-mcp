"""Tests for ensure_act_prefix utility function."""
import pytest
from meta_ads_mcp.core.api import ensure_act_prefix


class TestEnsureActPrefix:
    """Test ensure_act_prefix adds 'act_' prefix when needed."""

    def test_adds_prefix_to_numeric_account_id(self):
        """Adds 'act_' prefix to bare numeric account ID."""
        result = ensure_act_prefix("123456789")
        assert result == "act_123456789"

    def test_idempotent_already_prefixed(self):
        """Does not double-prefix if already present."""
        result = ensure_act_prefix("act_123456789")
        assert result == "act_123456789"

    def test_handles_empty_string(self):
        """Returns empty string as-is."""
        result = ensure_act_prefix("")
        assert result == ""

    def test_handles_none(self):
        """Returns None as-is."""
        result = ensure_act_prefix(None)
        assert result is None

    def test_preserves_alphanumeric_with_prefix(self):
        """Preserves full alphanumeric strings when prefixed."""
        result = ensure_act_prefix("act_abc123xyz")
        assert result == "act_abc123xyz"

    def test_adds_prefix_to_alphanumeric(self):
        """Adds prefix to alphanumeric without prefix."""
        result = ensure_act_prefix("abc123xyz")
        assert result == "act_abc123xyz"

    def test_whitespace_unprefixed(self):
        """Handles whitespace in unprefixed ID."""
        # Whitespace is rare but defensive
        result = ensure_act_prefix("123 456")
        assert result == "act_123 456"

    def test_short_id(self):
        """Works with short account IDs."""
        result = ensure_act_prefix("42")
        assert result == "act_42"

    def test_single_char(self):
        """Works with single character."""
        result = ensure_act_prefix("5")
        assert result == "act_5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
