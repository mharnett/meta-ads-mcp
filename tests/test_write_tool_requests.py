"""Pin the Graph API request each core write tool sends.

``create_campaign``, ``update_campaign``, ``create_ad`` and
``create_budget_schedule`` had no tests. Each is driven through the real
startup path and MCP dispatch with writes enabled, against a recording fake
transport, and the test asserts on the request that reached the wire: method,
endpoint and form body. The create tests pin the default ``status`` to
``PAUSED``: a new campaign or ad must never start spending on creation unless
the caller asks for it.
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


def _only_request(fake_graph):
    assert len(fake_graph.requests) == 1, [(r.method, r.url) for r in fake_graph.requests]
    return fake_graph.requests[0]


class TestCreateCampaign:
    def test_sends_one_post_with_paused_status_by_default(self, writable_server, fake_graph) -> None:
        result = dispatch_call(
            writable_server,
            "create_campaign",
            {"account_id": FAKE_ACCOUNT, "name": "Test Campaign", "objective": "OUTCOME_TRAFFIC"},
        )

        assert result.isError is False, result_text(result)
        req = _only_request(fake_graph)
        assert req.method == "POST"
        assert req.url == f"{GRAPH}/{FAKE_ACCOUNT}/campaigns"
        assert req.form == {
            "name": "Test Campaign",
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "special_ad_categories": "[]",
            # Silent default: with no budget given, the tool sets a
            # campaign-level daily budget of 1000 (account-currency cents).
            "daily_budget": "1000",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "access_token": FAKE_TOKEN,
        }

    def test_adds_act_prefix_to_bare_account_id(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {"account_id": FAKE_ACCOUNT_NUMBER, "name": "Test Campaign", "objective": "OUTCOME_TRAFFIC"},
        )

        assert _only_request(fake_graph).url == f"{GRAPH}/{FAKE_ACCOUNT}/campaigns"

    def test_explicit_status_and_adset_budgets_are_sent_as_given(self, writable_server, fake_graph) -> None:
        dispatch_call(
            writable_server,
            "create_campaign",
            {
                "account_id": FAKE_ACCOUNT,
                "name": "Test Campaign",
                "objective": "OUTCOME_LEADS",
                "status": "ACTIVE",
                "special_ad_categories": [],
                "use_adset_level_budgets": True,
            },
        )

        form = _only_request(fake_graph).form
        # PAUSED is a default, not enforced: an explicit status goes through.
        assert form["status"] == "ACTIVE"
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
