"""save_ad_image_locally must write only inside one configured directory.

The tool is opt-in (META_ADS_ENABLE_SAVE_AD_IMAGE_LOCALLY), but once enabled
its caller-supplied ``output_dir`` decided where bytes landed: an absolute
path or ``../`` wrote anywhere the server process could. Saves are now
confined to META_ADS_IMAGE_SAVE_DIR (default ``./ad_images``), and
``output_dir`` is a location inside it.

The Graph API and the image download are both faked in the ads module, so
nothing here leaves the process.
"""

from __future__ import annotations

import json
import os

import pytest

from meta_ads_mcp.core import ads
from meta_ads_mcp.core.server import mcp_server

AD_ID = "120210000000000001"
IMAGE_HASH = "a1b2c3d4e5f6"
IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
FAKE_TOKEN = "fake-token-for-tests-0000000000"


@pytest.fixture
def fake_graph(monkeypatch):
    """Fake make_api_request + download_image; return the list of calls."""
    calls: list[str] = []
    state = {"image_hash": IMAGE_HASH}

    async def fake_request(endpoint, access_token, params=None, method="GET", **kwargs):
        calls.append(endpoint)
        if endpoint == AD_ID:
            return {"creative": {"id": "777"}, "account_id": "555"}
        if endpoint == "777":
            return {"id": "777", "image_hash": state["image_hash"]}
        if endpoint == "act_555/adimages":
            return {"data": [{"hash": state["image_hash"], "url": "https://img.invalid/x.jpg"}]}
        raise AssertionError(f"unexpected Graph endpoint {endpoint!r}")

    async def fake_download(url):
        calls.append(f"download:{url}")
        return IMAGE_BYTES

    monkeypatch.setattr(ads, "make_api_request", fake_request)
    monkeypatch.setattr(ads, "download_image", fake_download)
    return calls, state


@pytest.fixture(autouse=True)
def _cwd_in_tmp(tmp_path, monkeypatch):
    """Run from inside tmp_path so a regression that resolves paths against
    the cwd (as the unconfined code did) writes into tmp_path, never into
    the checkout. "../x" from tmp_path/cwd still lands under tmp_path."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


@pytest.fixture
def base(tmp_path, monkeypatch):
    base_dir = tmp_path / "base"
    monkeypatch.setenv("META_ADS_IMAGE_SAVE_DIR", str(base_dir))
    return base_dir


async def _save(**kwargs):
    kwargs.setdefault("ad_id", AD_ID)
    raw = await ads.save_ad_image_locally(access_token=FAKE_TOKEN, **kwargs)
    return json.loads(raw)


def _files_under(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


async def test_default_save_lands_in_the_configured_dir(base, fake_graph):
    result = await _save()

    expected = base / f"{AD_ID}_{IMAGE_HASH}.jpg"
    assert result == {"filepath": str(expected)}
    assert expected.read_bytes() == IMAGE_BYTES


async def test_unset_save_dir_defaults_to_ad_images_under_cwd(_cwd_in_tmp, monkeypatch, fake_graph):
    monkeypatch.delenv("META_ADS_IMAGE_SAVE_DIR", raising=False)

    result = await _save()

    expected = _cwd_in_tmp.resolve() / "ad_images" / f"{AD_ID}_{IMAGE_HASH}.jpg"
    assert result == {"filepath": str(expected)}
    assert expected.read_bytes() == IMAGE_BYTES


async def test_relative_output_dir_is_a_subdir_of_the_save_dir(base, fake_graph):
    result = await _save(output_dir="campaign_a/week_1")

    expected = base / "campaign_a" / "week_1" / f"{AD_ID}_{IMAGE_HASH}.jpg"
    assert result == {"filepath": str(expected)}
    assert expected.read_bytes() == IMAGE_BYTES


async def test_absolute_output_dir_inside_the_save_dir_is_allowed(base, fake_graph):
    result = await _save(output_dir=str(base / "inside"))

    expected = base / "inside" / f"{AD_ID}_{IMAGE_HASH}.jpg"
    assert result == {"filepath": str(expected)}


@pytest.mark.parametrize(
    "output_dir",
    ["..", "../escape", "sub/../../escape", "./../escape"],
)
async def test_parent_traversal_is_refused_before_any_graph_call(tmp_path, base, fake_graph, output_dir):
    calls, _ = fake_graph

    result = await _save(output_dir=output_dir)

    assert "error" in result and "filepath" not in result, result
    assert calls == [], "a refused path still cost a Graph call"
    assert _files_under(tmp_path) == []
    assert not (tmp_path / "escape").exists()


async def test_absolute_output_dir_outside_the_save_dir_is_refused(tmp_path, base, fake_graph):
    calls, _ = fake_graph
    outside = tmp_path / "outside"

    result = await _save(output_dir=str(outside))

    assert "error" in result and "filepath" not in result, result
    assert calls == []
    assert not outside.exists()
    assert _files_under(tmp_path) == []


async def test_sibling_dir_sharing_the_prefix_is_refused(tmp_path, base, fake_graph):
    """/x/base-evil starts with /x/base as a string but is not inside it."""
    sibling = tmp_path / "base-evil"

    result = await _save(output_dir=str(sibling))

    assert "error" in result, result
    assert not sibling.exists()


async def test_symlinked_subdir_pointing_outside_is_refused(tmp_path, base, fake_graph):
    outside = tmp_path / "outside"
    outside.mkdir()
    base.mkdir()
    (base / "link").symlink_to(outside, target_is_directory=True)

    result = await _save(output_dir="link")

    assert "error" in result and "filepath" not in result, result
    assert list(outside.iterdir()) == []


async def test_ad_id_with_path_characters_is_refused_before_any_graph_call(tmp_path, base, fake_graph):
    calls, _ = fake_graph

    result = await _save(ad_id="../../evil")

    assert "error" in result, result
    assert calls == []
    assert _files_under(tmp_path) == []


async def test_image_hash_with_path_characters_from_the_api_is_refused(tmp_path, base, fake_graph):
    """The hash comes back from the API and becomes part of the filename
    ("<ad_id>_<hash>.jpg"). With a "<ad_id>_x" directory present, a hash of
    "x/../../escaped" would resolve to a file outside the save directory."""
    _, state = fake_graph
    state["image_hash"] = "x/../../escaped"
    (base / f"{AD_ID}_x").mkdir(parents=True)

    result = await _save()

    assert "error" in result and "filepath" not in result, result
    assert not (tmp_path / "escaped.jpg").exists()
    assert _files_under(tmp_path) == []


async def test_existing_symlink_at_the_target_file_is_not_written_through(tmp_path, base, fake_graph):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"original")
    base.mkdir()
    (base / f"{AD_ID}_{IMAGE_HASH}.jpg").symlink_to(outside)

    result = await _save()

    assert "error" in result and "filepath" not in result, result
    assert outside.read_bytes() == b"original"


def test_tool_stays_unregistered_unless_enabled():
    names = {t.name for t in mcp_server._tool_manager.list_tools()}
    assert ads.ENABLE_SAVE_AD_IMAGE_LOCALLY is False
    assert "save_ad_image_locally" not in names
    # A neighbouring tool from the same module is registered, so the check
    # above is looking at the right registry.
    assert "get_ad_image" in names
