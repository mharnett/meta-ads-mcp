"""Tests that prove ``_isolate_auth_env`` in conftest.py actually strips
Meta env vars from the test process, so a polluted dev shell cannot
silently invalidate the write-gate (or auth) negative tests.

This is the positive-coverage test for v2 audit finding M3:
``conftest._isolate_auth_env`` previously only cleared
``PIPEBOARD_API_TOKEN``, leaving ``META_ADS_MCP_WRITE`` and friends
exposed from the developer shell.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from tests.conftest import _ISOLATED_ENV_VARS
from meta_ads_mcp.core.write_gate import is_write_enabled


def test_isolate_auth_env_clears_every_listed_var() -> None:
    """The autouse fixture must have already cleared every var.

    This test runs in a normal pytest process; if any of the listed env
    vars is still set when the test body executes, the fixture did not
    do its job and every other test that relies on default-off behaviour
    is at risk.
    """
    for name in _ISOLATED_ENV_VARS:
        assert name not in os.environ, (
            f"{name!r} leaked into test process; conftest._isolate_auth_env "
            "is not actually isolating it."
        )


def test_write_gate_defaults_to_disabled_under_fixture() -> None:
    """With the fixture active, ``is_write_enabled()`` (reading os.environ
    by default) must return False — even if the parent shell exported
    ``META_ADS_MCP_WRITE=true``.
    """
    assert is_write_enabled() is False


def test_isolation_survives_polluted_parent_shell() -> None:
    """Spawn a pytest subprocess with ``META_ADS_MCP_WRITE=true`` (and a
    fake ``META_ACCESS_TOKEN``) set in its environment, run a tiny inline
    test that asserts those vars are gone inside the test body, and
    confirm the subprocess pytest exits 0.

    If ``_isolate_auth_env`` regressed (e.g. someone deleted entries from
    ``_ISOLATED_ENV_VARS``), the inline assertions would fail and the
    subprocess would exit non-zero, failing this test.
    """
    polluted_env = os.environ.copy()
    polluted_env["META_ADS_MCP_WRITE"] = "true"
    polluted_env["META_ACCESS_TOKEN"] = "fake_dev_shell_token"
    polluted_env["META_APP_ID"] = "999999999999999"
    polluted_env["META_ADS_ENABLE_REPORTS"] = "1"

    inline_test = textwrap.dedent(
        """
        import os
        from meta_ads_mcp.core.write_gate import is_write_enabled

        def test_polluted_parent_does_not_leak():
            assert "META_ADS_MCP_WRITE" not in os.environ
            assert "META_ACCESS_TOKEN" not in os.environ
            assert "META_APP_ID" not in os.environ
            assert "META_ADS_ENABLE_REPORTS" not in os.environ
            # And the write gate reading os.environ directly must agree.
            assert is_write_enabled() is False
        """
    )

    # Write the inline test next to the real tests so conftest.py is
    # picked up (pytest walks up to find conftest).
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir)
    )
    tmp_path = os.path.join(
        repo_root, "tests", "_tmp_isolation_subprocess_test.py"
    )
    try:
        with open(tmp_path, "w") as fh:
            fh.write(inline_test)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", tmp_path, "-q", "--no-header"],
            cwd=repo_root,
            env=polluted_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    assert result.returncode == 0, (
        "Subprocess pytest failed with polluted parent env. "
        "This means _isolate_auth_env did NOT strip the leaked vars.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
