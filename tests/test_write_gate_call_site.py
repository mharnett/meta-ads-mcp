"""Call-site test for the write gate.

``test_write_gate.py`` proves ``install_write_gate`` works on a toy FastMCP
server. It does not prove production installs it: delete the
``install_write_gate(mcp_server, logger)`` line from ``main()`` and that file
stays green. These tests close that gap. They run the real console-script
entry point (``meta_ads_mcp:entrypoint`` -> ``main()``) on both transports,
then call every write tool through the low-level MCP request handler a
client reaches, against a recording fake of the Graph API.

With writes off, every write tool must be refused by the gate before a
single request is made. The positive control runs the same calls with
writes on and requires each one to reach the fake, so "zero requests" above
means the gate stopped the call, not that the arguments were too thin to
get anywhere.
"""

from __future__ import annotations

import pytest

from meta_ads_mcp.core.write_gate import WRITE_DISABLED_MESSAGE, WRITE_TOOLS
from tests._fake_graph import (  # noqa: F401  (fixtures)
    dispatch_call,
    dispatch_list,
    fake_graph,
    result_text,
    started_server,
)


FAKE_ACCOUNT = "act_100000000000001"
FAKE_CAMPAIGN = "120000000000010"
FAKE_ADSET = "120000000000020"
FAKE_AD = "120000000000030"
FAKE_CREATIVE = "120000000000040"
FAKE_PAGE = "100000000000099"
# 1x1 transparent PNG.
PIXEL_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# Arguments that get each tool past its own validation to the Graph API.
# The positive control below proves they do.
WRITE_TOOL_ARGS = {
    "create_campaign": {
        "account_id": FAKE_ACCOUNT,
        "name": "Gate Test Campaign",
        "objective": "OUTCOME_TRAFFIC",
    },
    "update_campaign": {"campaign_id": FAKE_CAMPAIGN, "name": "Gate Test Rename"},
    "create_adset": {
        "account_id": FAKE_ACCOUNT,
        "campaign_id": FAKE_CAMPAIGN,
        "name": "Gate Test Ad Set",
        "optimization_goal": "LINK_CLICKS",
        "billing_event": "IMPRESSIONS",
        "daily_budget": 1000,
        "targeting": {"geo_locations": {"countries": ["US"]}},
    },
    "update_adset": {"adset_id": FAKE_ADSET, "name": "Gate Test Rename"},
    "create_ad": {
        "account_id": FAKE_ACCOUNT,
        "name": "Gate Test Ad",
        "adset_id": FAKE_ADSET,
        "creative_id": FAKE_CREATIVE,
    },
    "update_ad": {"ad_id": FAKE_AD, "name": "Gate Test Rename"},
    "create_ad_creative": {
        "account_id": FAKE_ACCOUNT,
        "image_hash": "0123456789abcdef0123456789abcdef",
        "page_id": FAKE_PAGE,
        "link_url": "https://example.com/",
        "message": "Gate test body",
        "headline": "Gate test",
    },
    "update_ad_creative": {"creative_id": FAKE_CREATIVE, "name": "Gate Test Rename"},
    "upload_ad_image": {"account_id": FAKE_ACCOUNT, "file": PIXEL_PNG, "name": "pixel.png"},
    "create_budget_schedule": {
        "campaign_id": FAKE_CAMPAIGN,
        "budget_value": 100,
        "budget_value_type": "ABSOLUTE",
        "time_start": 1767225600,
        "time_end": 1767312000,
    },
}

TRANSPORTS = {
    "stdio": (),
    "streamable-http": ("--transport", "streamable-http"),
}


def test_every_write_tool_has_call_args() -> None:
    # A tool added to WRITE_TOOLS without args here would drop out of the
    # call-site loop below; fail instead.
    assert set(WRITE_TOOL_ARGS) == set(WRITE_TOOLS)


@pytest.mark.parametrize("transport", sorted(TRANSPORTS))
def test_main_refuses_every_write_tool_before_any_graph_request(
    transport, started_server, fake_graph
) -> None:
    srv = started_server(*TRANSPORTS[transport])
    assert started_server.run_calls[-1]["transport"] == transport

    registered = {t.name for t in srv._tool_manager.list_tools()}
    for name in sorted(WRITE_TOOLS):
        # An unregistered name is also refused (as "Unknown tool"), which
        # would make this test pass for the wrong reason.
        assert name in registered, f"{name} is not registered on the server"

        result = dispatch_call(srv, name, WRITE_TOOL_ARGS[name])

        assert result.isError is True, f"{name} was not refused: {result_text(result)}"
        assert WRITE_DISABLED_MESSAGE in result_text(result), (
            f"{name} was refused by something other than the write gate: "
            f"{result_text(result)}"
        )
        assert fake_graph.requests == [], (
            f"{name} reached the Graph API with writes disabled: "
            f"{[(r.method, r.url) for r in fake_graph.requests]}"
        )


@pytest.mark.parametrize("transport", sorted(TRANSPORTS))
def test_main_hides_every_write_tool_from_list_tools(transport, started_server, fake_graph) -> None:
    srv = started_server(*TRANSPORTS[transport])

    listed = set(dispatch_list(srv))

    assert listed & WRITE_TOOLS == set()
    assert "get_campaigns" in listed
    assert fake_graph.requests == []


@pytest.mark.parametrize("transport", sorted(TRANSPORTS))
def test_positive_control_each_write_tool_reaches_graph_when_enabled(
    transport, started_server, fake_graph, monkeypatch
) -> None:
    monkeypatch.setenv("META_ADS_MCP_WRITE", "true")
    srv = started_server(*TRANSPORTS[transport])

    assert WRITE_TOOLS <= set(dispatch_list(srv))
    for name in sorted(WRITE_TOOLS):
        before = len(fake_graph.requests)

        result = dispatch_call(srv, name, WRITE_TOOL_ARGS[name])

        assert WRITE_DISABLED_MESSAGE not in result_text(result)
        assert len(fake_graph.requests) > before, (
            f"{name} made no Graph API request with writes enabled, so the "
            f"zero-request check above proves nothing for it: {result_text(result)}"
        )
        assert all(r.url.startswith("https://graph.facebook.com/") for r in fake_graph.requests)
