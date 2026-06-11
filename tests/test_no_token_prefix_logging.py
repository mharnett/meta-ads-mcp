"""Guard test: no source line may log a prefix slice of a secret variable.

Logging even a partial token / code / CSRF value (e.g. ``token[:10]``) leaks
secret material into log aggregators and persistent log files. This test scans
the auth-related source files and fails if any line slices a secret-named
variable, regardless of slice length.

Origin: 2026-06-11 audit found 5 instances of ``access_token[:10]`` /
``code[:10]`` / ``csrf[:12]`` prefix logging across the auth path.
"""

import re
from pathlib import Path

import pytest

# meta-ads-mcp/tests/ -> meta-ads-mcp/meta_ads_mcp/core/
CORE_DIR = Path(__file__).resolve().parent.parent / "meta_ads_mcp" / "core"

SCANNED_FILES = [
    CORE_DIR / "auth.py",
    CORE_DIR / "callback_server.py",
    CORE_DIR / "http_auth_integration.py",
    CORE_DIR / "authentication.py",
    # Forcepoint 6sense script (also flagged in the 2026-06-11 audit). Path is
    # resolved from this file's location up to the claude-code root; skipped
    # cleanly (path.exists() is False) if the tree layout differs.
    Path(__file__).resolve().parents[3]
    / "clients" / "forcepoint" / "6sense" / "pause_and_rebudget.py",
]

# A variable whose name implies a secret, immediately followed by a slice that
# starts at the front: foo_token[:10], code[:8], csrf[: 12], auth_token[:n].
SECRET_NAME = r"(?:access_token|refresh_token|auth_token|cached_token|token|code|csrf|secret|password|credential|api_key|apikey|key|pat)"
PREFIX_SLICE = re.compile(
    rf"\b{SECRET_NAME}\s*\[\s*:\s*\d+\s*\]",
    re.IGNORECASE,
)


def _offending_lines(path: Path):
    if not path.exists():
        return []
    hits = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        if PREFIX_SLICE.search(line):
            hits.append((i, line.strip()))
    return hits


@pytest.mark.parametrize("path", SCANNED_FILES, ids=lambda p: p.name)
def test_no_secret_prefix_slice(path):
    hits = _offending_lines(path)
    assert not hits, (
        f"{path.name} logs/uses prefix slices of secret variables "
        f"(leaks partial secrets): "
        + "; ".join(f"line {n}: {l}" for n, l in hits)
    )
