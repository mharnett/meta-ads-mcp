"""Authentication-specific functionality for Meta Ads API.

The Meta Ads MCP server supports two local authentication modes:

1. **Direct access token** (simplest)
   - Provide a Meta System User access token via the `META_ACCESS_TOKEN`
     environment variable. The token is used as-is for every API call.

2. **Local OAuth flow**
   - Uses a local callback server on localhost:8080+ for the OAuth redirect.
   - Requires `META_APP_ID` (and `META_APP_SECRET` for long-lived-token
     exchange) to be set.
   - Requires `META_ADS_DISABLE_CALLBACK_SERVER` to NOT be set.

Environment Variables:
- META_ACCESS_TOKEN: Direct Meta token (preferred for local/server use)
- META_APP_ID / META_APP_SECRET: Meta Developer App credentials for OAuth
- META_ADS_DISABLE_CALLBACK_SERVER: Disables the local callback server
- META_ADS_DISABLE_LOGIN_LINK: Hard-disables the get_login_link tool
"""

import json
from typing import Optional
import asyncio
import os
from .api import meta_api_tool
from . import auth
from .auth import start_callback_server, shutdown_callback_server, auth_manager
from .server import mcp_server
from .utils import logger, META_APP_SECRET

# Only register the login link tool if not explicitly disabled
ENABLE_LOGIN_LINK = not bool(os.environ.get("META_ADS_DISABLE_LOGIN_LINK", ""))


async def get_login_link(access_token: Optional[str] = None) -> str:
    """
    Get a clickable login link for Meta Ads authentication.

    Uses the local OAuth flow: starts a callback server on localhost and
    returns the Facebook OAuth URL. Requires `META_APP_ID` to be set.

    Args:
        access_token: Meta API access token (optional - will use cached token if not provided)

    Returns:
        A clickable resource link for Meta authentication
    """
    callback_server_disabled = bool(os.environ.get("META_ADS_DISABLE_CALLBACK_SERVER", ""))

    # Check if we have a cached token
    cached_token = auth_manager.get_access_token()

    # If we already have a valid token and none was provided, just return success
    if cached_token and not access_token:
        logger.info("get_login_link called with existing valid token")
        return json.dumps({
            "message": "Already Authenticated",
            "status": "You're successfully authenticated with Meta Ads!",
            "token_info": f"Token preview: {cached_token[:10]}...",
            "created_at": auth_manager.token_info.created_at if hasattr(auth_manager, "token_info") and auth_manager.token_info else None,
            "expires_in": auth_manager.token_info.expires_in if hasattr(auth_manager, "token_info") and auth_manager.token_info else None,
            "authentication_method": "meta_oauth",
            "ready_to_use": "You can now use all Meta Ads MCP tools and commands."
        }, indent=2)

    if callback_server_disabled:
        return json.dumps({
            "message": "Local Authentication Unavailable",
            "error": "The local callback server is disabled (META_ADS_DISABLE_CALLBACK_SERVER is set)",
            "solutions": [
                "Set META_ACCESS_TOKEN environment variable with a Meta System User token",
                "Unset META_ADS_DISABLE_CALLBACK_SERVER to use the local OAuth flow",
            ],
            "authentication_method": "meta_oauth_disabled"
        }, indent=2)

    # Start the local callback server and produce a direct Facebook OAuth URL
    logger.info("Starting callback server for authentication")
    try:
        port = start_callback_server()
        logger.info(f"Callback server started on port {port}")

        # Generate direct login URL
        auth_manager.redirect_uri = f"http://localhost:{port}/callback"
        logger.info(f"Setting redirect URI to {auth_manager.redirect_uri}")
        login_url = auth_manager.get_auth_url()
        logger.info(f"Generated login URL: {login_url}")
    except Exception as e:
        logger.error(f"Failed to start callback server: {e}")
        return json.dumps({
            "message": "Local Authentication Unavailable",
            "error": "Cannot start local callback server for authentication",
            "reason": str(e),
            "solutions": [
                "Set META_ACCESS_TOKEN environment variable with a Meta System User token",
                "Check if another service is using the required ports",
            ],
            "authentication_method": "meta_oauth_disabled"
        }, indent=2)

    # Check if we can exchange for long-lived tokens
    token_exchange_supported = bool(META_APP_SECRET)
    token_duration = "60 days" if token_exchange_supported else "1-2 hours"

    # Return a special format that helps the LLM format the response properly
    response = {
        "message": "Click to Authenticate",
        "login_url": login_url,
        "markdown_link": f"[Authenticate with Meta Ads]({login_url})",
        "instructions": "Click the link above to authenticate with Meta Ads.",
        "server_info": f"Local callback server running on port {port}",
        "token_duration": f"Your token will be valid for approximately {token_duration}",
        "authentication_method": "meta_oauth",
        "what_happens_next": "After clicking, you'll be redirected to Meta's authentication page. Once completed, your token will be automatically saved.",
        "security_note": "This uses a secure local callback server for development purposes."
    }

    # Wait a moment to ensure the server is fully started
    await asyncio.sleep(1)

    return json.dumps(response, indent=2)

# Conditionally register as MCP tool only when enabled
if ENABLE_LOGIN_LINK:
    get_login_link = mcp_server.tool()(get_login_link)
