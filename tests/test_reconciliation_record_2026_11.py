"""Shape test for docs/reconciliation-2026-11.md.

The 2026-11 record classifies the 10 upstream commits between the 2026-09
record's tip (2ef198e) and 63d0e5e. Every commit gets exactly one row; a
`port` row names the regression test that covers it in this fork, and an
`already-done` row names the fork commit that did it, both of which must exist.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
RECORD = ROOT / "docs" / "reconciliation-2026-11.md"

PREVIOUS_TIP = "2ef198e266ca6a37b6dc2c42335f0a0885002771"
TIP_SHA = "63d0e5e29f2cf823f7f5317a77e66151eceb7415"

EXPECTED_COMMITS = {
    "63d0e5e29f2cf823f7f5317a77e66151eceb7415",
    "093062c6655682a20ff0814b468e0e877263d494",
    "d5eaceeb00edb5a71c7432bb437bef120cc65bb6",
    "8f8eda64dc00a04661b2d136dfb9415fc4b26800",
    "d136b4ce681ceeaf68529fbf17b8bc276592740d",
    "9365b94ce2c2a8a0f3cce310445308530e178320",
    "8b6b0fd181850d1eae539c9166a7f5b352cbaa63",
    "96eaf2d8a0e6f94e797fed2808756b32e1097b87",
    "ceee65b8180332f98660aee0e544aeb7855e5bd2",
    "271ea4cd5e0e21ae306e3768af8fc4dd1b928298",
}

ROW_RE = re.compile(
    r"^\|\s*`([0-9a-f]{40})`\s*\|(.*?)\|\s*(superseded|already-done|port|decline)\s*\|(.*)\|\s*$",
    re.MULTILINE,
)


def _rows():
    assert RECORD.exists(), f"{RECORD} does not exist"
    return ROW_RE.findall(RECORD.read_text())


def test_record_names_both_tips():
    text = RECORD.read_text()
    assert TIP_SHA in text
    assert PREVIOUS_TIP in text


def test_every_commit_classified_exactly_once():
    shas = [r[0] for r in _rows()]
    assert len(shas) == len(set(shas)), "a commit is classified more than once"
    assert set(shas) == EXPECTED_COMMITS


def test_port_rows_name_an_existing_regression_test():
    ports = [r for r in _rows() if r[2] == "port"]
    assert ports, "expected at least one port row"
    for sha, _summary, _cls, why in ports:
        names = re.findall(r"`(tests/test_[a-z0-9_]+\.py)`", why)
        assert names, f"port row {sha[:7]} names no regression test"
        for name in names:
            assert (ROOT / name).exists(), f"{name} (row {sha[:7]}) does not exist"


def test_already_done_rows_name_a_fork_commit_in_history():
    done = [r for r in _rows() if r[2] == "already-done"]
    assert done, "expected at least one already-done row"
    for sha, _summary, _cls, why in done:
        fork_shas = re.findall(r"`([0-9a-f]{7})`", why)
        assert fork_shas, f"already-done row {sha[:7]} names no fork commit"
        for fork_sha in fork_shas:
            r = subprocess.run(
                ["git", "cat-file", "-e", f"{fork_sha}^{{commit}}"],
                cwd=ROOT, capture_output=True,
            )
            assert r.returncode == 0, f"{fork_sha} (row {sha[:7]}) not in history"
