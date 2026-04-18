# Meta Ads MCP Examples

This directory contains example scripts and usage demonstrations for the Meta Ads MCP server.

## Files

### `example_http_client.py`
A minimal HTTP client that demonstrates how to interact with the Meta Ads MCP server using the HTTP transport.

**Features:**
- Sends a Meta access token in the `Authorization: Bearer` header
- Demonstrates all basic MCP operations (initialize, list tools, call tools)
- Includes error handling and response formatting

**Usage:**
```bash
# Start the MCP server
python -m meta_ads_mcp --transport streamable-http --port 8080

# Run the example (in another terminal)
cd examples
python example_http_client.py
```

**Authentication:**
- Set `META_ACCESS_TOKEN` in the environment before running, or pass the token
  directly to the `MetaAdsMCPClient` constructor.

## Adding New Examples

When adding new example files:
1. Include comprehensive docstrings
2. Add usage instructions in comments
3. Update this README with file descriptions
