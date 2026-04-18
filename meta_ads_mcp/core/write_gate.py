"""Read-only-by-default safety gate for Meta Ads MCP.

Mutating tools are hidden from the ListTools response and refused at call
time unless the environment variable ``META_ADS_MCP_WRITE=true`` is set.

This mirrors the gate shipped in the Google Ads MCP
(see ``writeGate.ts``) and exists because a casual Slack/chat request
handed to the LLM can trigger a live mutation on ad spend (create /
update / pause / enable / upload) before anyone notices. Defaulting
to read-only forces an explicit opt-in for writes.

Adding a new tool? Put it in :data:`WRITE_TOOLS` if it creates, updates,
uploads, pauses, enables, removes, links, unlinks, duplicates, or
otherwise mutates anything.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Mapping, Optional, Sequence


WRITE_TOOLS: frozenset[str] = frozenset(
    {
        # Creates
        "create_ad",
        "create_ad_creative",
        "create_adset",
        "create_budget_schedule",
        "create_campaign",
        # Updates
        "update_ad",
        "update_ad_creative",
        "update_adset",
        "update_campaign",
        # Uploads (mutates ad account assets)
        "upload_ad_image",
        # Duplication tools (conditional on META_ADS_ENABLE_DUPLICATION)
        "duplicate_campaign",
        "duplicate_adset",
        "duplicate_ad",
        "duplicate_creative",
    }
)


WRITE_DISABLED_MESSAGE: str = (
    "Write operations are disabled. Set META_ADS_MCP_WRITE=true in the MCP "
    "server environment to enable mutating tools "
    "(create/update/upload/duplicate)."
)


def is_write_tool(name: str) -> bool:
    """Return True if ``name`` is a known mutating tool."""
    return name in WRITE_TOOLS


def is_write_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return True when the META_ADS_MCP_WRITE env var opts in to writes.

    Accepts ``true``/``1``/``yes`` (case-insensitive, whitespace-trimmed).
    """
    source = os.environ if env is None else env
    raw = source.get("META_ADS_MCP_WRITE", "")
    if raw is None:
        return False
    normalized = raw.strip().lower()
    return normalized in {"true", "1", "yes"}


def filter_tools(
    tools: Sequence, env: Optional[Mapping[str, str]] = None
) -> list:
    """Return tools visible under the current write-mode setting.

    When writes are disabled, every tool whose ``.name`` is in
    :data:`WRITE_TOOLS` is removed. When writes are enabled, the input
    is returned as-is (materialised into a fresh list).
    """
    if is_write_enabled(env):
        return list(tools)
    return [t for t in tools if getattr(t, "name", None) not in WRITE_TOOLS]


def assert_write_allowed(
    name: str, env: Optional[Mapping[str, str]] = None
) -> None:
    """Raise ``PermissionError`` if ``name`` is a write tool and writes are off.

    No-op for read-only tools and when writes are enabled.
    """
    if not is_write_tool(name):
        return
    if is_write_enabled(env):
        return
    raise PermissionError(
        f'Tool "{name}" is a write operation. {WRITE_DISABLED_MESSAGE}'
    )


def install_write_gate(mcp_server: Any, logger: Optional[logging.Logger] = None) -> None:
    """Wrap FastMCP ``list_tools`` and ``call_tool`` with the write gate.

    FastMCP registers low-level MCP request handlers by binding
    ``self.list_tools`` / ``self.call_tool`` at ``__init__`` time (in
    ``_setup_handlers``). There is no central tool registry the gate can
    hook, so we re-register the low-level handlers with wrappers that:

      * ``list_tools``  → filter out write tools when disabled
      * ``call_tool``   → refuse write tools with a clear error when disabled

    Safe to call after all tool modules have been imported (i.e. after
    every ``@mcp_server.tool()`` decorator has fired).
    """
    log = logger or logging.getLogger(__name__)

    original_list_tools = mcp_server.list_tools
    original_call_tool = mcp_server.call_tool

    async def gated_list_tools():
        tools = await original_list_tools()
        return filter_tools(tools)

    async def gated_call_tool(name: str, arguments: dict[str, Any]):
        assert_write_allowed(name)
        return await original_call_tool(name, arguments)

    # Replace the instance methods so direct callers also see gated
    # behaviour (tests, any code that holds the FastMCP instance and calls
    # ``list_tools()`` / ``call_tool()`` directly).
    mcp_server.list_tools = gated_list_tools
    mcp_server.call_tool = gated_call_tool

    # Re-register the low-level handlers. The decorators in
    # ``mcp.server.lowlevel.Server`` overwrite ``request_handlers`` for
    # ``ListToolsRequest`` / ``CallToolRequest``, so this replaces the
    # bindings that FastMCP set up in ``_setup_handlers``.
    mcp_server._mcp_server.list_tools()(gated_list_tools)
    mcp_server._mcp_server.call_tool(validate_input=False)(gated_call_tool)

    mode = "ENABLED" if is_write_enabled() else "DISABLED (read-only)"
    hidden = sorted(WRITE_TOOLS) if not is_write_enabled() else []
    log.info("Meta Ads MCP write mode: %s", mode)
    if hidden:
        log.info(
            "Write gate hiding %d mutating tools. Set META_ADS_MCP_WRITE=true to enable.",
            len(hidden),
        )


__all__ = [
    "WRITE_TOOLS",
    "WRITE_DISABLED_MESSAGE",
    "is_write_tool",
    "is_write_enabled",
    "filter_tools",
    "assert_write_allowed",
    "install_write_gate",
]
