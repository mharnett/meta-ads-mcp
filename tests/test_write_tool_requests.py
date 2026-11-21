"""Pin the Graph API request each core write tool sends.

``create_campaign``, ``update_campaign``, ``create_ad`` and
``create_budget_schedule`` had no tests. Each is driven through the real
startup path and MCP dispatch with writes enabled, against a recording fake
transport, and the test asserts on the request that reached the wire: method,
endpoint and form body.

Create rules pinned here:

* Every create tool that takes a ``status`` creates PAUSED. Any other status
  is refused before a request is made: create paused, enable separately.
* ``create_campaign`` never invents a budget. With no campaign budget it
  sends the ad-set-level request Graph v24.0 requires
  (``is_adset_budget_sharing_enabled``, no campaign ``bid_strategy``).
* Account ids get the ``act_`` prefix on every create.
"""

from __future__ import annotations

import json

import pytest

from tests._fake_graph import (  # noqa: F401  (fixtures)
    FAKE_TOKEN,
    dispatch_call,
    fake_graph,
    result_json,
    result_text,
    started_server,
)


GRAPH = "https://graph.facebook.com/v24.0"
FAKE_ACCOUNT_NUMBER = "100000000000001"
FAKE_ACCOUNT = f"act_{FAKE_ACCOUNT_NUMBER}"
FAKE_CAMPAIGN = "120000000000010"
FAKE_ADSET = "120000000000020"
FAKE_CREATIVE = "120000000000040"


@pytest.fixture
def writable_server(started_server, fake_graph, monkeypatch):
    monkeypatch.setenv("META_ADS_MCP_WRITE", "true")
    return started_server()


def _tool_error(result):
    """Return the tool's ``error`` text, or None.

    ``meta_api_tool`` currently re-wraps an error payload without a
    ``details`` key as ``{"data": "<original JSON>"}``, so look in both
    places.
    """
    payload = result_json(result)
    if "error" not in payload and isinstance(payload.get("data"), str):
        try:
            payload = json.loads(payload["data"])
        except ValueError:
            return None
    error = payload.get("error")
    return None if error is None else str(error)


def _only_request(fake_graph):
    assert len(fake_graph.requests) == 1, [(r.method, r.url) for r in fake_graph.requests]
    return fake_graph.requests[0]


# Create tools that take a status, with the minimal args to reach the Graph
# API, and the update tool the refusal should point at.
CREATE_TOOLS_WITH_STATUS = {
    "create_campaign": (
        {"account_id": FAKE_ACCOUNT, "name": "Test Campaign", "objective": "OUTCOME_TRAFFIC"},
        "update_campaign",
    ),
    "create_adset": (
        {
            "account_id": FAKE_ACCOUNT,
            "campaign_id": FAKE_CAMPAIGN,
            "name": "Test Ad Set",
            "optimization_goal": "LINK_CLICKS",
            "billing_event": "IMPRESSIONS",
            "daily_budget": 1000,
            "targeting": {"geo_locations": {"countries": ["US"]}},
        },
        "update_adset",
    ),
    "create_ad": (
        {"account_id": FAKE_ACCOUNT, "name": "Test Ad", "adset_id": FAKE_ADSET, "creative_id": FAKE_CREATIVE},
        "update_ad",
    ),
}


class TestCreateToolsArePausedOnly:
    def test_every_create_tool_with_a_status_is_covered(self, writable_server) -> None:
        with_status = {
            t.name
            for t in writable_server._tool_manager.list_tools()
            if t.name.startswith("create_") and "status" in t.parameters.get("properties", {})
        }
        assert with_status == set(CREATE_TOOLS_WITH_STATUS)

    @pytest.mark.parametrize("tool", sorted(CREATE_TOOLS_WITH_STATUS))
    @pytest.mark.parametrize("status", ["ACTIVE", "active", "ARCHIVED", "DELETED", ""])
    def test_non_paused_status_is_refused_before_any_request(
        self, tool, status, writable_server, fake_graph
    ) -> None:
        args, update_tool = CREATE_TOOLS_WITH_STATUS[tool]

        result = dispatch_call(writable_server, tool, {**args, "status": status})

        error = _tool_error(result)
        assert error is not None, result_text(result)
        assert "PAUSED" in error
        assert f"{update_tool}(" in error, error
        assert fake_graph.requests == []

    @pytest.mark.parametrize("tool", sorted(CREATE_TOOLS_WITH_STATUS))
    @pytest.mark.parametrize("status", [None, "PAUSED", "paused"])
    def test_creates_paused(self, tool, status, writable_server, fake_graph) -> None:
        args, _ = CREATE_TOOLS_WITH_STATUS[tool]
        if status is not None:
            args = {**args, "status": status}

        result = dispatch_call(writable_server, tool, args)

        assert _tool_error(result) is None, result_text(result)
        creates = [r for r in fake_graph.requests if r.method == "POST"]
        assert len(creates) == 1, [(r.method, r.url) for r in fake_graph.requests]
        assert creates[0].form["status"] == "PAUSED"


class TestCreateCampaign:
    def test_without_budget_sends_adset_level_request_and_invents_none(
        self, writable_server, fake_graph
    ) -> None:
        result = dispatch_call(
            writable_server,
            "create_campaign",
            {"account_id": FAKE_ACCOUNT, "name": "Test Campaign", "objective": "OUTCOME_TRAFFIC"},
        )

        assert result.isError is False, result_text(result)
        assert result_json(result)["budget_strategy"] == "ad_set_level"
        req = _only_request(fake_graph)
        assert req.method == "POST"
        assert req.url == f"{GRAPH}/{FAKE_ACCOUNT}/campaigns"
        # No campaign budget and no campaign bid strategy; Graph v24.0 requires
        # is_adset_budget_sharing_enabled when budgets live on the ad sets.
        assert req.form == {
            "name": "Test Campaign",
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "special_ad_categories": "[]",
            "is_adset_budget_sharing_enabled": "false",
            "access_token": FAKE_TOKEN,
        }

    def test_explicit_daily_budget_sends_campaign_budget(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Campaign",
                "objective": "OUTCOME_TRAFFIC",
                "daily_budget": 5000,
            },
        )

        assert _only_request(fake_graph).form == {
            "name": "Test Campaign",
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "special_ad_categories": "[]",
            "daily_budget": "5000",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "access_token": FAKE_TOKEN,
        }

    def test_explicit_lifetime_budget_sends_campaign_budget(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Campaign",
                "objective": "OUTCOME_TRAFFIC",
                "lifetime_budget": 90000,
            },
        )

        form = _only_request(fake_graph).form
        assert form["lifetime_budget"] == "90000"
        assert "daily_budget" not in form
        assert "is_adset_budget_sharing_enabled" not in form

    def test_adds_act_prefix_to_bare_account_id(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {"account_id": FAKE_ACCOUNT_NUMBER, "name": "Test Campaign", "objective": "OUTCOME_TRAFFIC"},
        )

        assert _only_request(fake_graph).url == f"{GRAPH}/{FAKE_ACCOUNT}/campaigns"

    def test_adset_level_budgets_ignore_a_campaign_budget(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Campaign",
                "objective": "OUTCOME_LEADS",
                "special_ad_categories": [],
                "daily_budget": 5000,
                "use_adset_level_budgets": True,
            },
        )

        form = _only_request(fake_graph).form
        assert form["is_adset_budget_sharing_enabled"] == "false"
        assert "daily_budget" not in form
        assert "bid_strategy" not in form

    def test_missing_objective_makes_no_request(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_campaign",
            {"account_id": FAKE_ACCOUNT, "name": "Test Campaign", "objective": ""},
        )

        assert "No campaign objective provided" in result_text(result)
        assert fake_graph.requests == []


class TestUpdateCampaign:
    def test_sends_only_the_fields_given(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "update_campaign",
            {"campaign_id": FAKE_CAMPAIGN, "status": "PAUSED", "daily_budget": 5000},
        )

        assert result.isError is False, result_text(result)
        req = _only_request(fake_graph)
        assert req.method == "POST"
        assert req.url == f"{GRAPH}/{FAKE_CAMPAIGN}"
        assert req.form == {
            "status": "PAUSED",
            "daily_budget": "5000",
            "access_token": FAKE_TOKEN,
        }

    def test_switch_to_adset_budgets_clears_campaign_budgets(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "update_campaign",
            {"campaign_id": FAKE_CAMPAIGN, "use_adset_level_budgets": True},
        )

        form = _only_request(fake_graph).form
        assert form["daily_budget"] == ""
        assert form["lifetime_budget"] == ""

    def test_no_fields_makes_no_request(self, writable_server, fake_graph) -> None:
        result = dispatch_call(writable_server, "update_campaign", {"campaign_id": FAKE_CAMPAIGN})

        assert "No update parameters provided" in result_text(result)
        assert fake_graph.requests == []


class TestCreateAd:
    def test_sends_one_post_with_paused_status_by_default(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_ad",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Ad",
                "adset_id": FAKE_ADSET,
                "creative_id": FAKE_CREATIVE,
            },
        )

        assert result.isError is False, result_text(result)
        req = _only_request(fake_graph)
        assert req.method == "POST"
        assert req.url == f"{GRAPH}/{FAKE_ACCOUNT}/ads"
        assert req.form["status"] == "PAUSED"
        assert req.form["name"] == "Test Ad"
        assert req.form["adset_id"] == FAKE_ADSET
        assert json.loads(req.form["creative"]) == {"creative_id": FAKE_CREATIVE}
        assert req.form["access_token"] == FAKE_TOKEN
        assert set(req.form) == {"name", "adset_id", "creative", "status", "access_token"}

    def test_adds_act_prefix_to_bare_account_id(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_ad",
            {
                "account_id": FAKE_ACCOUNT_NUMBER,
                "name": "Test Ad",
                "adset_id": FAKE_ADSET,
                "creative_id": FAKE_CREATIVE,
            },
        )

        assert _only_request(fake_graph).url == f"{GRAPH}/{FAKE_ACCOUNT}/ads"

    def test_bid_amount_and_tracking_specs_are_encoded(self, writable_server, fake_graph) -> None:
        specs = [{"action.type": ["offsite_conversion"], "fb_pixel": ["100000000000077"]}]
        dispatch_call(
            writable_server,
            "create_ad",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Ad",
                "adset_id": FAKE_ADSET,
                "creative_id": FAKE_CREATIVE,
                "bid_amount": 250,
                "tracking_specs": specs,
            },
        )

        form = _only_request(fake_graph).form
        assert form["bid_amount"] == "250"
        assert json.loads(form["tracking_specs"]) == specs

    def test_missing_creative_makes_no_request(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_ad",
            {"account_id": FAKE_ACCOUNT, "name": "Test Ad", "adset_id": FAKE_ADSET, "creative_id": ""},
        )

        assert "No creative ID provided" in result_text(result)
        assert fake_graph.requests == []


class TestCreateBudgetSchedule:
    def test_sends_one_post_to_budget_schedules(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_budget_schedule",
            {
                "campaign_id": FAKE_CAMPAIGN,
                "budget_value": 200,
                "budget_value_type": "ABSOLUTE",
                "time_start": 1767225600,
                "time_end": 1767312000,
            },
        )

        assert result.isError is False, result_text(result)
        assert result_json(result)["id"]
        req = _only_request(fake_graph)
        assert req.method == "POST"
        assert req.url == f"{GRAPH}/{FAKE_CAMPAIGN}/budget_schedules"
        assert req.form == {
            "budget_value": "200",
            "budget_value_type": "ABSOLUTE",
            "time_start": "1767225600",
            "time_end": "1767312000",
            "access_token": FAKE_TOKEN,
        }

    def test_invalid_value_type_makes_no_request(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_budget_schedule",
            {
                "campaign_id": FAKE_CAMPAIGN,
                "budget_value": 2,
                "budget_value_type": "PERCENT",
                "time_start": 1767225600,
                "time_end": 1767312000,
            },
        )

        assert "Invalid budget_value_type" in result_text(result)
        assert fake_graph.requests == []
