#!/bin/bash
# Wrapper to launch Meta Ads MCP with token from Keychain
export META_ACCESS_TOKEN=$(security find-generic-password -a meta-ads-mcp -s META_ACCESS_TOKEN -w 2>/dev/null)
export META_ADS_DISABLE_LOGIN_LINK=1

if [ -z "$META_ACCESS_TOKEN" ]; then
  echo "[FATAL] META_ACCESS_TOKEN is empty -- Keychain lookup failed." >&2
  echo "  Fix: security add-generic-password -a meta-ads-mcp -s META_ACCESS_TOKEN -w 'YOUR_TOKEN' -U" >&2
  exit 1
fi

exec /Users/mark/claude-code/mcps/meta-ads-mcp/.venv/bin/python -m meta_ads_mcp
