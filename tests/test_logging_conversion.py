"""Tests for L1: Print → Logging conversion in meta-ads-mcp."""


class TestPrintStatementsRemoved:
    """Verify print() is not used for logging in core modules."""

    def test_no_print_for_user_messages(self):
        """Core modules should not use print() for messages."""
        import ast
        from pathlib import Path

        # Resolve from __file__, never an absolute checkout path: hardcoded
        # /Users/mark/... paths pass only on one machine and are a guaranteed
        # FileNotFoundError on any CI runner.
        core = Path(__file__).resolve().parent.parent / "meta_ads_mcp" / "core"
        core_files = [core / "server.py", core / "auth.py", core / "callback_server.py"]

        for filepath in core_files:
            assert filepath.exists(), f"core module missing at {filepath}"
            tree = ast.parse(filepath.read_text())

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
