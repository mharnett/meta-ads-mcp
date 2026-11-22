"""Tools must never write to stdout: under the stdio transport it is the
JSON-RPC channel, and a stray line corrupts the stream the client parses.

save_ad_image_locally, get_ad_image, upload_ad_image, create_ad_creative's
page auto-discovery and the image download helpers all used bare print().
Each test below drives one of those paths to its end and asserts nothing
reached stdout.

Containment: make_api_request and the ads-module download helpers are
replaced with fakes; the download-helper tests swap httpx.AsyncClient for a
MockTransport and block sockets and DNS, so a path that slipped past the fake
fails instead of reaching the network. Tokens are fake strings.
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import subprocess
import sys

import httpx
import pytest
from mcp.server.fastmcp import Image
from PIL import Image as PILImage

from meta_ads_mcp.core import ads, utils

FAKE_TOKEN = "FAKE_TEST_TOKEN_not_a_real_credential"
AD_ID = "120210000000000001"
IMAGE_HASH = "a1b2c3d4e5f6"
PUBLIC_IMAGE_URL = "https://93.184.216.34/image.jpg"  # literal public IP: no DNS


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _assert_no_stdout(capsys):
    out = capsys.readouterr().out
    assert out == "", f"wrote to stdout (the MCP stdio channel): {out!r}"


@pytest.fixture
def fake_ads_graph(monkeypatch):
    """Fake the Graph calls and the image download used by the ads tools."""
    state = {"image_hash": IMAGE_HASH}

    async def fake_request(endpoint, access_token, params=None, method="GET", **kwargs):
        if endpoint == AD_ID:
            return {"creative": {"id": "777"}, "account_id": "555"}
        if endpoint == "777":
            return {"id": "777", "image_hash": state["image_hash"]} if state["image_hash"] else {"id": "777"}
        if endpoint == "act_555/adimages":
            if method == "POST":
                return {"images": {IMAGE_HASH: {"hash": IMAGE_HASH, "url": PUBLIC_IMAGE_URL}}}
            return {"data": [{"hash": IMAGE_HASH, "url": PUBLIC_IMAGE_URL}]}
        if endpoint == "act_555/adcreatives":
            return {"id": "888"}
        if endpoint == "888":  # create_ad_creative reads the new creative back
            return {"id": "888", "name": "Test creative"}
        raise AssertionError(f"unexpected Graph endpoint {endpoint!r}")

    async def fake_download(url):
        return _jpeg_bytes()

    monkeypatch.setattr(ads, "make_api_request", fake_request)
    monkeypatch.setattr(ads, "download_image", fake_download)
    return state


@pytest.fixture
def mock_http(monkeypatch):
    """httpx.AsyncClient answers from a MockTransport; real sockets and DNS fail."""
    state = {"status": 200, "body": _jpeg_bytes()}
    real_client = httpx.AsyncClient

    def handler(request):
        return httpx.Response(state["status"], content=state["body"])

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    def blocked(*_a, **_k):
        raise RuntimeError("real network access is blocked in this test")

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    return state


async def test_save_ad_image_locally_writes_nothing_to_stdout(tmp_path, monkeypatch, capsys, fake_ads_graph):
    monkeypatch.setenv("META_ADS_IMAGE_SAVE_DIR", str(tmp_path / "images"))

    result = json.loads(await ads.save_ad_image_locally(ad_id=AD_ID, access_token=FAKE_TOKEN))

    assert result["filepath"].endswith(f"{AD_ID}_{IMAGE_HASH}.jpg")
    _assert_no_stdout(capsys)


async def test_get_ad_image_writes_nothing_to_stdout(capsys, fake_ads_graph):
    result = await ads.get_ad_image(ad_id=AD_ID, access_token=FAKE_TOKEN)

    assert isinstance(result, Image)
    _assert_no_stdout(capsys)


async def test_get_ad_image_direct_url_fallback_writes_nothing_to_stdout(monkeypatch, capsys, fake_ads_graph):
    fake_ads_graph["image_hash"] = None

    async def fake_creatives(**kwargs):
        return json.dumps({"data": [{"id": "777", "image_url": PUBLIC_IMAGE_URL}]})

    monkeypatch.setattr(ads, "get_ad_creatives", fake_creatives)

    result = await ads.get_ad_image(ad_id=AD_ID, access_token=FAKE_TOKEN)

    assert isinstance(result, Image)
    _assert_no_stdout(capsys)


async def test_upload_ad_image_writes_nothing_to_stdout(capsys, fake_ads_graph):
    file = base64.b64encode(_jpeg_bytes()).decode("ascii")

    result = json.loads(await ads.upload_ad_image(account_id="act_555", file=file, name="x.jpg", access_token=FAKE_TOKEN))

    assert "error" not in result, result
    _assert_no_stdout(capsys)


async def test_create_ad_creative_page_autodiscovery_writes_nothing_to_stdout(monkeypatch, capsys, fake_ads_graph):
    async def fake_discover(account_id, access_token):
        return {"success": True, "page_id": "123", "page_name": "Test Page"}

    monkeypatch.setattr(ads, "_discover_pages_for_account", fake_discover)

    result = json.loads(await ads.create_ad_creative(
        account_id="act_555",
        image_hash=IMAGE_HASH,
        link_url="https://example.test/",
        message="Test message",
        access_token=FAKE_TOKEN,
    ))

    assert "error" not in result, result
    _assert_no_stdout(capsys)


async def test_download_image_refusal_writes_nothing_to_stdout(capsys, mock_http):
    assert await utils.download_image("http://127.0.0.1/x.jpg") is None
    _assert_no_stdout(capsys)


async def test_download_image_success_writes_nothing_to_stdout(capsys, mock_http):
    assert await utils.download_image(PUBLIC_IMAGE_URL) == mock_http["body"]
    _assert_no_stdout(capsys)


async def test_download_fallbacks_write_nothing_to_stdout_when_every_method_fails(capsys, mock_http):
    mock_http["status"] = 404

    assert await utils.try_multiple_download_methods(PUBLIC_IMAGE_URL) is None
    _assert_no_stdout(capsys)


def test_import_without_credentials_writes_nothing_to_stdout(tmp_path):
    """The no-credentials startup warning ran at import time, before the
    server could answer `initialize`. It belongs on stderr."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("META_", "PIPEBOARD_"))}
    env["HOME"] = str(tmp_path)  # token cache and log file land in tmp_path
    env["APPDATA"] = str(tmp_path)

    proc = subprocess.run(
        [sys.executable, "-c", "import meta_ads_mcp.core.utils"],
        env=env, capture_output=True, text=True, timeout=60, cwd=str(tmp_path),
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert "META_APP_ID environment variable is not set" in proc.stderr
