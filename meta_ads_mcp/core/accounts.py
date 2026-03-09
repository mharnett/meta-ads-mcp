"""Account-related functionality for Meta Ads API."""

import json
from typing import Optional, Dict, Any
from .api import meta_api_tool, make_api_request
from .server import mcp_server


@mcp_server.tool()
@meta_api_tool
async def get_ad_accounts(access_token: Optional[str] = None, user_id: str = "me", limit: int = 200) -> str:
    """
    Get ad accounts accessible by a user.

    amount_spent and balance are returned in currency units (e.g. USD dollars),
    not cents.

    Args:
        access_token: Meta API access token (optional - will use cached token if not provided)
        user_id: Meta user ID or "me" for the current user
        limit: Maximum number of accounts to return (default: 200)
    """
    fields = "id,name,account_id,account_status,amount_spent,balance,currency,age,business_city,business_country_code"

    # First get user's direct accounts
    endpoint = f"{user_id}/adaccounts"
    params = {"fields": fields, "limit": limit}
    data = await make_api_request(endpoint, access_token, params)

    # Also query Business Manager ad accounts (client, owned, and partner-shared)
    bm_ids = ["285682998480431"]  # Drak Marketing
    seen_ids = {acc["id"] for acc in data.get("data", [])}

    for bm_id in bm_ids:
        for edge in ["client_ad_accounts", "owned_ad_accounts"]:
            bm_endpoint = f"{bm_id}/{edge}"
            bm_params = {"fields": fields, "limit": limit}
            bm_data = await make_api_request(bm_endpoint, access_token, bm_params)
            for acc in bm_data.get("data", []):
                if acc["id"] not in seen_ids:
                    data.setdefault("data", []).append(acc)
                    seen_ids.add(acc["id"])

    # Directly fetch known partner-shared accounts that BM edges may miss
    known_account_ids = ["act_441611459623086"]  # Neon CRM Facebook Ads (owned by Neon One, shared with Drak Marketing)
    for acct_id in known_account_ids:
        if acct_id not in seen_ids:
            try:
                acct_data = await make_api_request(acct_id, access_token, {"fields": fields})
                if "error" not in acct_data:
                    data.setdefault("data", []).append(acct_data)
                    seen_ids.add(acct_id)
            except Exception:
                pass  # Skip if not accessible

    return json.dumps(data, indent=2)


@mcp_server.tool()
@meta_api_tool
async def get_account_info(account_id: str, access_token: Optional[str] = None) -> str:
    """
    Get detailed information about a specific ad account.
    
    Args:
        account_id: Meta Ads account ID (format: act_XXXXXXXXX)
        access_token: Meta API access token (optional - will use cached token if not provided)
    """
    if not account_id:
        return {
            "error": {
                "message": "Account ID is required",
                "details": "Please specify an account_id parameter",
                "example": "Use account_id='act_123456789' or account_id='123456789'"
            }
        }
    
    # Ensure account_id has the 'act_' prefix for API compatibility
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    
    # Try to get the account info directly first
    endpoint = f"{account_id}"
    params = {
        "fields": "id,name,account_id,account_status,amount_spent,balance,currency,age,business_city,business_country_code,timezone_name"
    }
    
    data = await make_api_request(endpoint, access_token, params)
    
    # Check if the API request returned an error
    if "error" in data:
        # If access was denied, provide helpful error message with accessible accounts
        if "access" in str(data.get("error", {})).lower() or "permission" in str(data.get("error", {})).lower():
            # Get list of accessible accounts for helpful error message
            accessible_endpoint = "me/adaccounts"
            accessible_params = {
                "fields": "id,name,account_id,account_status,amount_spent,balance,currency,age,business_city,business_country_code",
                "limit": 50
            }
            accessible_accounts_data = await make_api_request(accessible_endpoint, access_token, accessible_params)
            
            if "data" in accessible_accounts_data:
                accessible_accounts = [
                    {"id": acc["id"], "name": acc["name"]} 
                    for acc in accessible_accounts_data["data"][:10]  # Show first 10
                ]
                return {
                    "error": {
                        "message": f"Account {account_id} is not accessible to your user account",
                        "details": "This account either doesn't exist or you don't have permission to access it",
                        "accessible_accounts": accessible_accounts,
                        "total_accessible_accounts": len(accessible_accounts_data["data"]),
                        "suggestion": "Try using one of the accessible account IDs listed above"
                    }
                }
        
        # Return the original error for non-permission related issues
        return data
    
    # Add DSA requirement detection
    if "business_country_code" in data:
        european_countries = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "IE", "DK", "SE", "FI", "NO"]
        if data["business_country_code"] in european_countries:
            data["dsa_required"] = True
            data["dsa_compliance_note"] = "This account is subject to European DSA (Digital Services Act) requirements"
        else:
            data["dsa_required"] = False
            data["dsa_compliance_note"] = "This account is not subject to European DSA requirements"
    
    return data 