"""Tests that auth.py does not use os.environ / NameError as an inter-module bus.

Two anti-patterns made auth state implicit and builds/tests fragile:
  1. MetaConfig.set_app_id() mutated os.environ["META_APP_ID"] as a side channel so
     other modules could read app_id without an explicit dependency. That couples
     unrelated modules through process-global env state and leaks across tests.
  2. process_token_response() referenced a module-global `auth_manager` guarded by
     `except NameError` — passing state by hoping a name exists, instead of an
     explicit parameter.

These tests pin the explicit-dependency contract.
"""

import ast
import os
from pathlib import Path

from meta_ads_mcp.core.auth import (
    MetaConfig,
    AuthManager,
    TokenInfo,
    process_token_response,
)

AUTH_FILE = Path(__file__).resolve().parents[1] / "meta_ads_mcp" / "core" / "auth.py"


def test_set_app_id_does_not_mutate_os_environ():
    """set_app_id updates the instance only — it must not write os.environ."""
    cfg = MetaConfig()
    sentinel = "test-app-id-12345"
    os.environ.pop("META_APP_ID", None)
    try:
        cfg.set_app_id(sentinel)
        assert cfg.get_app_id() == sentinel
        assert "META_APP_ID" not in os.environ, (
            "set_app_id leaked state into os.environ — pass app_id explicitly instead"
        )
    finally:
        cfg.app_id = os.environ.get("META_APP_ID", "")
        os.environ.pop("META_APP_ID", None)


def test_process_token_response_takes_explicit_auth_manager():
    """process_token_response must accept an auth_manager parameter (explicit DI),
    not reach for a module global under `except NameError`."""
    import inspect

    params = list(inspect.signature(process_token_response).parameters)
    assert "auth_manager" in params, (
        "process_token_response should accept auth_manager explicitly, "
        f"got params: {params}"
    )


def test_auth_source_has_no_nameerror_bus_guard():
    """No `except NameError` guard remains around auth_manager usage."""
    tree = ast.parse(AUTH_FILE.read_text(), filename=str(AUTH_FILE))
    name_error_handlers = [
        h
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for h in node.handlers
        if (isinstance(h.type, ast.Name) and h.type.id == "NameError")
    ]
    assert not name_error_handlers, (
        "except NameError guard found — auth_manager should be passed explicitly, "
        "not discovered as a maybe-defined global"
    )


def test_process_token_response_actually_sets_token_on_passed_manager():
    """Behavioral: passing an auth_manager and a token container stores the token
    on THAT manager (no globals involved)."""
    mgr = AuthManager("test-app-id")
    mgr.token_info = None
    container = {"token": "x" * 40, "expires_in": 3600}

    # No long-lived exchange creds in test env → falls back to short-lived token.
    os.environ.pop("META_APP_SECRET", None)
    ok = process_token_response(container, auth_manager=mgr)

    assert ok is True
    assert mgr.token_info is not None
    assert mgr.token_info.access_token == "x" * 40
