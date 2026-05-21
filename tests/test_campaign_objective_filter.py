"""In-process tests for `get_campaigns` filtering behavior.

These tests exercise the tool function directly (no HTTP transport, no server)
and assert on the arguments passed to `make_api_request` and on the returned
JSON payload. The previous version of this file POSTed JSON-RPC to a running
MCP server on :8080 and skipped silently when no server was present, hiding
real failures.

Scope of behaviors covered:
1. No filtering -> no `filtering` / `effective_status` params, response passes through
2. Single objective string -> `filtering` param contains `objective IN [obj]`
3. Multiple objectives list -> `filtering` param contains `objective IN [...list]`
4. Combined status + objective filter -> both params present
5. Empty string objective_filter -> no filtering param
6. Empty list objective_filter -> no filtering param
7. Missing account_id -> returns error JSON without hitting the API
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from meta_ads_mcp.core.campaigns import get_campaigns


SAMPLE_DATA_SINGLE = {
    "data": [
        {"id": "c1", "name": "Lead Gen 1", "objective": "OUTCOME_LEADS", "status": "ACTIVE"},
    ]
}

SAMPLE_DATA_MIXED = {
    "data": [
        {"id": "c1", "name": "A", "objective": "OUTCOME_LEADS", "status": "ACTIVE"},
        {"id": "c2", "name": "B", "objective": "OUTCOME_SALES", "status": "PAUSED"},
        {"id": "c3", "name": "C", "objective": "OUTCOME_TRAFFIC", "status": "ACTIVE"},
    ]
}


def _params_from_call(mock_api):
    """Extract the params dict (3rd positional arg) from the make_api_request call."""
    return mock_api.call_args[0][2]


def _filtering_from_params(params):
    """Parse the JSON-encoded filtering array from params, or return None."""
    raw = params.get("filtering")
    return json.loads(raw) if raw else None


@pytest.mark.asyncio
class TestGetCampaignsFiltering:
    """Direct in-process tests for the `get_campaigns` tool function."""

    async def test_no_filtering_passes_no_filter_params(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_MIXED

            result = await get_campaigns(account_id="act_test", access_token="t")
            data = json.loads(result)

            assert data == SAMPLE_DATA_MIXED
            params = _params_from_call(mock_api)
            assert "filtering" not in params
            assert "effective_status" not in params
            assert params["limit"] == 10

    async def test_single_objective_filter_emits_in_filter(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_SINGLE

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                objective_filter="OUTCOME_LEADS",
            )

            params = _params_from_call(mock_api)
            filtering = _filtering_from_params(params)
            assert filtering == [
                {"field": "objective", "operator": "IN", "value": ["OUTCOME_LEADS"]}
            ]
            assert "effective_status" not in params

    async def test_multiple_objectives_filter_emits_in_filter(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_MIXED

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                objective_filter=["OUTCOME_LEADS", "OUTCOME_SALES"],
            )

            params = _params_from_call(mock_api)
            filtering = _filtering_from_params(params)
            assert filtering == [
                {
                    "field": "objective",
                    "operator": "IN",
                    "value": ["OUTCOME_LEADS", "OUTCOME_SALES"],
                }
            ]

    async def test_combined_status_and_objective_filter(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_SINGLE

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                status_filter="ACTIVE",
                objective_filter="OUTCOME_LEADS",
            )

            params = _params_from_call(mock_api)
            # effective_status is JSON-encoded list of one
            assert json.loads(params["effective_status"]) == ["ACTIVE"]
            filtering = _filtering_from_params(params)
            assert filtering == [
                {"field": "objective", "operator": "IN", "value": ["OUTCOME_LEADS"]}
            ]

    async def test_empty_string_objective_filter_skips_filtering(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_MIXED

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                objective_filter="",
            )

            params = _params_from_call(mock_api)
            assert "filtering" not in params

    async def test_empty_list_objective_filter_skips_filtering(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_MIXED

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                objective_filter=[],
            )

            params = _params_from_call(mock_api)
            assert "filtering" not in params

    async def test_list_with_only_empty_strings_skips_filtering(self):
        """Edge case: list containing only empty strings should produce no filter."""
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = SAMPLE_DATA_MIXED

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                objective_filter=["", ""],
            )

            params = _params_from_call(mock_api)
            assert "filtering" not in params

    async def test_missing_account_id_returns_error_without_api_call(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            result = await get_campaigns(account_id="", access_token="t")
            # The @meta_api_tool decorator wraps the inner return value;
            # the inner function emits `{"error": "No account ID specified"}`.
            # Assert the error string appears anywhere in the serialized result.
            assert "No account ID specified" in result
            mock_api.assert_not_called()

    async def test_limit_and_after_are_forwarded(self):
        with patch(
            "meta_ads_mcp.core.campaigns.make_api_request", new_callable=AsyncMock
        ) as mock_api:
            mock_api.return_value = {"data": []}

            await get_campaigns(
                account_id="act_test",
                access_token="t",
                limit=25,
                after="cursor_xyz",
            )

            params = _params_from_call(mock_api)
            assert params["limit"] == 25
            assert params["after"] == "cursor_xyz"
