"""
Pytest configuration for Meta Ads MCP tests

This file provides common fixtures and configuration for all tests.

NOTE: The previous `check_server_running` fixture has been removed. It used
`pytest.skip()` when no MCP server was listening on :8080, which is the
rubric #4 silent-skip antipattern (tests pass green when nothing ran).
HTTP-style tests have been converted to in-process tool tests, and the
remaining transport coverage lives in `test_http_transport_smoke.py`, which
spawns its own subprocess (see `mcp_http_server` fixture there) and HARD-FAILS
if the server can't start.
"""

import os

import pytest


# Every env var the production code reads via os.environ / os.getenv.
# Anything in this list, if set in the dev shell, can silently change
# test behaviour because `assert_write_allowed` / `is_write_enabled` /
# `filter_tools` and the auth/api modules read os.environ by default.
# We delenv all of them in _isolate_auth_env so the dev shell can never
# turn a CI-red test green on a laptop.
_ISOLATED_ENV_VARS = (
    # Write gate. THE critical one: with META_ADS_MCP_WRITE=true in the dev
    # shell, every write-gate negative test that calls is_write_enabled()
    # without an explicit env dict starts passing for the wrong reason.
    "META_ADS_MCP_WRITE",
    # Auth tokens / app credentials. Read by auth.py, utils.py, api.py,
    # server.py. If a dev has a real token in their shell, tests that
    # exercise the "no auth configured" path silently take the
    # authed-path branch and stop covering what they claim to cover.
    "META_ACCESS_TOKEN",
    "META_APP_ID",
    "META_APP_SECRET",
    # Feature flags whose default-off behaviour is what the tests assume.
    # Flipping any of these on in the dev shell changes which tools are
    # registered or which code paths run.
    "META_ADS_ENABLE_REPORTS",
    "META_ADS_ENABLE_SAVE_AD_IMAGE_LOCALLY",
    "META_ADS_DISABLE_ADS_LIBRARY",
    "META_ADS_DISABLE_CALLBACK_SERVER",
    "META_ADS_DISABLE_LOGIN_LINK",
    "META_MCP_DISABLE_DELIVERY_FALLBACK",
    # Legacy alternate auth path. Keeping this isolated guards against any
    # residual module state from the (now removed) Pipeboard support
    # silently re-enabling itself.
    "PIPEBOARD_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _isolate_auth_env(monkeypatch):
    """Strip every Meta-related env var from the test process.

    Without this, a developer with ``META_ADS_MCP_WRITE=true`` (or a real
    ``META_ACCESS_TOKEN``, etc.) in their shell will see tests pass locally
    that fail in CI, because the write-gate / auth helpers default-read
    ``os.environ`` when no explicit env mapping is passed.

    The vars isolated and why each matters are documented on
    ``_ISOLATED_ENV_VARS`` above. If you add a new ``os.environ.get`` /
    ``os.getenv`` call to production code for a ``META_*`` style var,
    add it to that tuple.

    Individual tests that legitimately need one of these set should use
    ``monkeypatch.setenv`` AFTER this fixture has run (fixture-order is
    fine: autouse fixtures run before per-test monkeypatch calls in the
    test body).
    """
    for name in _ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Belt-and-braces: assert isolation actually happened. If this ever
    # fires, something is reseting env between the delenv and the test
    # body (highly unlikely with monkeypatch, but the assert is cheap
    # and makes the contract explicit).
    for name in _ISOLATED_ENV_VARS:
        assert name not in os.environ, (
            f"_isolate_auth_env failed to remove {name!r}; "
            "tests cannot trust the write gate / auth defaults."
        )
