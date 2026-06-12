"""Tests for L2: Remove hardcoded App ID fallback."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestNoHardcodedAppID:
    """Verify MetaConfig doesn't use hardcoded App ID fallback."""

    def test_no_hardcoded_app_id_in_metaconfig(self):
        """MetaConfig should not have hardcoded app ID fallback."""
        import ast
        from pathlib import Path

        auth_file = Path(__file__).parent.parent / "meta_ads_mcp" / "core" / "auth.py"
        source = auth_file.read_text()

        # Parse the file
        tree = ast.parse(source)

        # Find the MetaConfig.__new__ method
        found_hardcoded = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                # Look for the hardcoded app ID
                if node.value == "779761636818489":
                    found_hardcoded = True
                    break

        assert not found_hardcoded, \
            "Found hardcoded app ID '779761636818489' in MetaConfig — should require META_APP_ID env var"

    def test_no_placeholder_app_id_at_module_level(self):
        """Module-level META_APP_ID should not use 'YOUR_META_APP_ID' placeholder."""
        import ast
        from pathlib import Path

        auth_file = Path(__file__).parent.parent / "meta_ads_mcp" / "core" / "auth.py"
        source = auth_file.read_text()

        tree = ast.parse(source)

        # Look for the placeholder string
        found_placeholder = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if node.value == "YOUR_META_APP_ID":
                    found_placeholder = True
                    break

        assert not found_placeholder, \
            "Found placeholder 'YOUR_META_APP_ID' — should require explicit META_APP_ID env var"
