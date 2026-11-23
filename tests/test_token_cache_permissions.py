"""Regression tests for GHSA-prmg-4fr3-mm6x (ported from upstream d5eacee).

The fork already created the cache file with ``os.open(..., 0o600)``, but
O_CREAT's mode only applies at creation and ``mkdir()`` had no mode, so a
cache file or directory written by an older version (or under a loose umask)
stayed wider than owner-only. Both are now narrowed explicitly, on save and
on load.
"""

import os
import platform
import stat

import pytest

from meta_ads_mcp.core import auth as auth_mod
from meta_ads_mcp.core.auth import AuthManager, TokenInfo

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows", reason="POSIX permission bits only"
)


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(auth_mod.pathlib.Path, "home", lambda: tmp_path)
    m = AuthManager("test-app-id")
    return m


def test_mode_constants():
    assert auth_mod.TOKEN_CACHE_FILE_MODE == 0o600
    assert auth_mod.TOKEN_CACHE_DIR_MODE == 0o700


def test_cache_dir_is_narrowed_even_if_it_already_exists_wide(manager):
    cache_dir = manager._get_token_cache_path().parent
    os.chmod(cache_dir, 0o755)

    path = manager._get_token_cache_path()

    assert _mode(path.parent) == 0o700


def test_save_narrows_a_preexisting_world_readable_cache(manager):
    path = manager._get_token_cache_path()
    path.write_text("{}")
    os.chmod(path, 0o644)

    manager.token_info = TokenInfo(access_token="EAAtest", expires_in=3600)
    manager._save_token_to_cache()

    assert _mode(path) == 0o600


def test_load_repairs_a_world_readable_cache(manager):
    manager.token_info = TokenInfo(access_token="EAAtest", expires_in=3600)
    manager._save_token_to_cache()
    path = manager._get_token_cache_path()
    os.chmod(path, 0o644)

    manager.token_info = None
    manager._load_cached_token()

    assert _mode(path) == 0o600
