"""Tests for the read-only-by-default write gate.

Mirrors the shape of ``writeGate.test.ts`` in the Google Ads MCP. The
most important test here is the "drift alarm": every tool registered
with the FastMCP server must be classified as either a READ or a WRITE
tool. If a new tool is added without updating the gate, this test fails
loudly.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from meta_ads_mcp.core.write_gate import (
    WRITE_DISABLED_MESSAGE,
    WRITE_TOOLS,
    assert_write_allowed,
    filter_tools,
    is_write_enabled,
    is_write_tool,
)


# Canonical read-tool fixture — must stay in sync with the server.
# A new tool registered without updating this list or WRITE_TOOLS will
# trip the drift alarm below.
READ_TOOLS = frozenset(
    {
        "estimate_audience_size",
        "fetch",
        "get_account_info",
        "get_account_pages",
        "get_ad_accounts",
        "get_ad_creatives",
        "get_ad_details",
        "get_ad_image",
        "get_ads",
        "get_adset_details",
        "get_adsets",
        "get_campaign_details",
        "get_campaigns",
        "get_insights",
        "get_interest_suggestions",
        "get_login_link",
        "search",
        "search_ads_archive",
        "search_behaviors",
        "search_demographics",
        "search_geo_locations",
        "search_interests",
        "search_pages_by_name",
        # Conditional / behind env flags
        "generate_report",
    }
)


def _registered_tool_names() -> set[str]:
    """Return the tool names that FastMCP currently knows about.

    This imports the server lazily so the test module is cheap to collect.
    """
    # Enable every optional tool so the drift alarm exercises them.
    os.environ.setdefault("META_ADS_ENABLE_REPORTS", "1")
    os.environ.setdefault("META_ADS_ENABLE_DUPLICATION", "1")
    # Ads library is on by default; login link is on by default.

    import importlib

    import meta_ads_mcp  # noqa: F401  (loads core, triggers registration)
    from meta_ads_mcp.core import server as server_module

    # Re-import conditional modules so the env flags set above take effect
    # even if a prior test import happened before the flags were set.
    from meta_ads_mcp.core import reports, duplication, ads_library, authentication
    for mod in (reports, duplication, ads_library, authentication):
        importlib.reload(mod)

    mcp = server_module.mcp_server
    tools = asyncio.run(mcp.list_tools())
    return {t.name for t in tools}


class TestToolClassificationDriftAlarm:
    def test_every_registered_tool_is_classified(self) -> None:
        registered = _registered_tool_names()
        classified = WRITE_TOOLS | READ_TOOLS
        uncovered = sorted(n for n in registered if n not in classified)
        assert uncovered == [], (
            "New tools were registered without updating WRITE_TOOLS or the "
            f"READ_TOOLS test fixture: {uncovered}"
        )

    def test_write_and_read_do_not_overlap(self) -> None:
        overlap = sorted(WRITE_TOOLS & READ_TOOLS)
        assert overlap == []


class TestIsWriteEnabled:
    def test_defaults_to_false_when_unset(self) -> None:
        assert is_write_enabled({}) is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES"])
    def test_accepts_truthy_values(self, value: str) -> None:
        assert is_write_enabled({"META_ADS_MCP_WRITE": value}) is True

    @pytest.mark.parametrize("value", ["", "false", "0", "no", "maybe", "off"])
    def test_rejects_falsy_values(self, value: str) -> None:
        assert is_write_enabled({"META_ADS_MCP_WRITE": value}) is False

    def test_trims_whitespace(self) -> None:
        assert is_write_enabled({"META_ADS_MCP_WRITE": "  true  "}) is True


def _fake_tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class TestFilterTools:
    def _sample(self) -> list[SimpleNamespace]:
        return [
            _fake_tool("get_campaigns"),
            _fake_tool("create_campaign"),
            _fake_tool("update_ad"),
            _fake_tool("get_insights"),
            _fake_tool("upload_ad_image"),
        ]

    def test_hides_write_tools_when_disabled(self) -> None:
        filtered = filter_tools(self._sample(), {})
        names = {t.name for t in filtered}
        assert names == {"get_campaigns", "get_insights"}
        for write in WRITE_TOOLS:
            assert write not in names

    def test_keeps_read_tools_when_disabled(self) -> None:
        filtered = filter_tools(self._sample(), {})
        names = {t.name for t in filtered}
        assert "get_campaigns" in names
        assert "get_insights" in names

    def test_returns_everything_when_enabled(self) -> None:
        filtered = filter_tools(
            self._sample(), {"META_ADS_MCP_WRITE": "true"}
        )
        names = {t.name for t in filtered}
        assert names == {
            "get_campaigns",
            "create_campaign",
            "update_ad",
            "get_insights",
            "upload_ad_image",
        }


class TestAssertWriteAllowed:
    def test_permits_read_tools_regardless_of_env(self) -> None:
        # Must not raise.
        assert_write_allowed("get_campaigns", {})
        assert_write_allowed("get_insights", {})
        assert_write_allowed("search_interests", {"META_ADS_MCP_WRITE": "false"})

    def test_blocks_every_write_tool_when_env_unset(self) -> None:
        for name in WRITE_TOOLS:
            with pytest.raises(PermissionError, match="write operation"):
                assert_write_allowed(name, {})

    def test_allows_write_tools_when_env_enabled(self) -> None:
        for name in WRITE_TOOLS:
            # Must not raise.
            assert_write_allowed(name, {"META_ADS_MCP_WRITE": "true"})

    def test_error_message_points_at_env_var_fix(self) -> None:
        with pytest.raises(PermissionError) as excinfo:
            assert_write_allowed("create_campaign", {})
        assert "META_ADS_MCP_WRITE=true" in str(excinfo.value)


class TestIsWriteTool:
    def test_create_campaign_is_write(self) -> None:
        assert is_write_tool("create_campaign") is True

    def test_upload_ad_image_is_write(self) -> None:
        assert is_write_tool("upload_ad_image") is True

    def test_read_tools_are_not_write(self) -> None:
        for name in ("get_campaigns", "get_insights", "search_interests"):
            assert is_write_tool(name) is False


def test_write_disabled_message_mentions_env_var() -> None:
    assert "META_ADS_MCP_WRITE=true" in WRITE_DISABLED_MESSAGE


class TestInstallWriteGate:
    """Integration: the gate actually replaces the wired handlers."""

    def _make_server(self):
        # Lazy import so collection stays cheap and FastMCP only loads once.
        from mcp.server.fastmcp import FastMCP

        srv = FastMCP("test-meta-ads-gate")

        @srv.tool()
        async def get_campaigns() -> str:  # read tool
            return "read-ok"

        @srv.tool()
        async def create_campaign() -> str:  # write tool (in WRITE_TOOLS)
            return "wrote!"

        return srv

    def test_list_tools_hides_write_tools_when_disabled(self, monkeypatch) -> None:
        from meta_ads_mcp.core.write_gate import install_write_gate

        monkeypatch.delenv("META_ADS_MCP_WRITE", raising=False)
        srv = self._make_server()
        install_write_gate(srv)

        names = {t.name for t in asyncio.run(srv.list_tools())}
        assert "get_campaigns" in names
        assert "create_campaign" not in names

    def test_list_tools_exposes_everything_when_enabled(self, monkeypatch) -> None:
        from meta_ads_mcp.core.write_gate import install_write_gate

        monkeypatch.setenv("META_ADS_MCP_WRITE", "true")
        srv = self._make_server()
        install_write_gate(srv)

        names = {t.name for t in asyncio.run(srv.list_tools())}
        assert names == {"get_campaigns", "create_campaign"}

    def test_call_tool_refuses_write_when_disabled(self, monkeypatch) -> None:
        from meta_ads_mcp.core.write_gate import install_write_gate

        monkeypatch.delenv("META_ADS_MCP_WRITE", raising=False)
        srv = self._make_server()
        install_write_gate(srv)

        with pytest.raises(PermissionError, match="write operation"):
            asyncio.run(srv.call_tool("create_campaign", {}))

    def test_call_tool_permits_read_when_disabled(self, monkeypatch) -> None:
        from meta_ads_mcp.core.write_gate import install_write_gate

        monkeypatch.delenv("META_ADS_MCP_WRITE", raising=False)
        srv = self._make_server()
        install_write_gate(srv)

        # Must not raise.
        asyncio.run(srv.call_tool("get_campaigns", {}))
