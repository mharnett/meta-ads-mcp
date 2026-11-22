"""meta_api_tool must return a tool's error JSON as-is.

The wrapper inspects string results for an app-ID error at
``result["details"]["error"]``. Its probe, ``result.get("details", {})
.get("error", {})``, evaluates to ``{}`` when there is no top-level
``details`` key, passes the ``isinstance(..., dict)`` check, and then
``result["details"]`` raises KeyError. The bare ``except`` turned that into
``{"data": "<the whole error JSON as a string>"}``, so a caller saw a
success-shaped payload with the error buried in a string. Every error from
``make_api_request`` has this shape (its ``details`` sits under ``error``).

Containment: every call passes a fake access token, and the one real tool
exercised has ``make_api_request`` replaced, so nothing leaves the process.
"""

from __future__ import annotations

import json

from meta_ads_mcp.core import campaigns
from meta_ads_mcp.core.api import meta_api_tool

FAKE_TOKEN = "FAKE_TEST_TOKEN_not_a_real_credential"


@meta_api_tool
async def _echo_tool(payload: str = "", access_token: str | None = None) -> str:
    return payload


async def _through_wrapper(payload: str) -> dict:
    return json.loads(await _echo_tool(payload=payload, access_token=FAKE_TOKEN))


# The shape make_api_request returns for a non-transient HTTP error.
HTTP_ERROR = {
    "error": {
        "message": "HTTP Error: 400",
        "details": {"error": {"message": "Invalid parameter", "code": 100, "error_subcode": 1487}},
        "full_response": {"status_code": 400},
    }
}


async def test_error_with_details_nested_under_error_is_returned_unwrapped():
    result = await _through_wrapper(json.dumps(HTTP_ERROR))

    assert result == HTTP_ERROR


async def test_plain_string_error_is_returned_unwrapped():
    result = await _through_wrapper(json.dumps({"error": "No campaign ID provided"}))

    assert result == {"error": "No campaign ID provided"}


async def test_non_dict_top_level_details_does_not_rewrap_the_error():
    payload = {"error": "Could not get video 1", "details": "not a dict"}

    result = await _through_wrapper(json.dumps(payload))

    assert result == payload


async def test_app_id_error_at_top_level_details_is_still_made_friendly():
    payload = {
        "error": "API call failed",
        "details": {"error": {"code": 200, "message": "(#200) Provide valid app ID"}},
    }

    result = await _through_wrapper(json.dumps(payload))

    assert result["error"]["message"] == "Meta API Configuration Issue"
    assert result["error"]["details"]["original_error"] == "(#200) Provide valid app ID"


async def test_success_json_passes_through():
    payload = {"data": [{"id": "1", "name": "Test campaign"}]}

    assert await _through_wrapper(json.dumps(payload)) == payload


async def test_non_json_text_is_still_wrapped_as_data():
    result = await _through_wrapper("plain text, not JSON")

    assert result == {"data": "plain text, not JSON"}


async def test_real_tool_surfaces_a_graph_error_at_the_top_level(monkeypatch):
    async def fake_request(endpoint, access_token, params=None, method="GET", **kwargs):
        return HTTP_ERROR

    monkeypatch.setattr(campaigns, "make_api_request", fake_request)

    raw = await campaigns.get_campaign_details(campaign_id="1", access_token=FAKE_TOKEN)
    result = json.loads(raw)

    assert "data" not in result
    assert result["error"]["message"] == "HTTP Error: 400"
    assert result["error"]["details"]["error"]["code"] == 100
