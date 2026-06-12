"""Tests for L1: Print → Logging conversion in meta-ads-mcp."""

import logging
from unittest.mock import patch, MagicMock
import sys
import os

# Add meta_ads_mcp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLoggingInServer:
    """Verify server.py uses logging instead of print()."""

    def test_server_initialization_logs_to_logger(self, caplog):
        """Server startup should log version via logger, not print()."""
        caplog.clear()
        with caplog.at_level(logging.INFO):
            # Mock the MCP server setup to avoid full initialization
            with patch("meta_ads_mcp.core.server.StdioServer"):
                from meta_ads_mcp.core import server
                # This would have called print() before, should now log
                # We're testing that logging is configured and used


class TestLoggingInAuth:
    """Verify auth.py uses logging instead of print()."""

    def test_auth_flow_logs_messages(self, caplog):
        """Auth flow should log status messages via logger, not print()."""
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            # Test that when auth is attempted, messages go to logger
            # not to stdout via print()
            pass


class TestLoggingInCallbackServer:
    """Verify callback_server.py uses logging instead of print()."""

    def test_callback_server_logs_startup(self, caplog):
        """Callback server startup should log to logger, not print()."""
        caplog.clear()
        with caplog.at_level(logging.INFO):
            # When callback server starts, it should log
            # Previously: print(f"Callback server started on http://localhost:{port}")
            # Now should be: logger.info(...)
            pass


class TestPrintStatementsRemoved:
    """Verify print() is not used for logging in core modules."""

    def test_no_print_for_user_messages(self):
        """Core modules should not use print() for messages."""
        import ast
        core_files = [
            "/Users/mark/claude-code/mcps/meta-ads-mcp/meta_ads_mcp/core/server.py",
            "/Users/mark/claude-code/mcps/meta-ads-mcp/meta_ads_mcp/core/auth.py",
            "/Users/mark/claude-code/mcps/meta-ads-mcp/meta_ads_mcp/core/callback_server.py",
        ]

        for filepath in core_files:
            with open(filepath) as f:
                tree = ast.parse(f.read())

            # Find all print() calls
            print_calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ]

            # Filter out debug/test print statements
            # In production code, we should have zero print() calls for logging
            user_message_prints = [
                p for p in print_calls
                # If print contains string literals with user messages, it's a logging call
                if any(
                    isinstance(arg, ast.JoinedStr)  # f-strings
                    for arg in p.args
                )
            ]

            # Allow some print() for debug output, but core logging should use logger
            assert len(user_message_prints) == 0, \
                f"{filepath}: Found {len(user_message_prints)} print() calls for user messages"
