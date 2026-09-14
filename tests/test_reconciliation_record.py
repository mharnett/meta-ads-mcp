"""Fork/upstream reconciliation record must classify every commit we're behind on.

The weekly upstream-diff sweep flags this fork as behind pipeboard-co/meta-ads-mcp.
docs/reconciliation-2026-09.md is the durable record that answers "was that ever
looked at, and what happened to it" for each commit, so the sweep (and a human)
can tell a reconciled gap from a silently ignored one. This test pins the record
against the commit population as it stood at the tip SHA the record names,
frozen at authoring time (2026-09-14) — it does not re-fetch upstream.
"""
import re
from pathlib import Path

RECORD = Path(__file__).parent.parent / "docs" / "reconciliation-2026-09.md"

TIP_SHA = "2ef198e266ca6a37b6dc2c42335f0a0885002771"

# HEAD..upstream/main, no merges, as of TIP_SHA (2026-09-14). One row per hash below.
EXPECTED_COMMITS = {
    "2ef198e266ca6a37b6dc2c42335f0a0885002771",
    "cbe4c6351ec3d80ca540def1ed768a76dc034209",
    "ef2592d2d1b0702daa4793dedadf862cad5aedc0",
    "3b612c7d59646c76cc544d2d224baa550ca6b046",
    "db8b9b8de5d6ef0f531c465f2d98dcbdc0c9779f",
    "225f46f5586a66add4e30cca218c5e88982e066c",
    "555ae487f4a88cf4ea148ca58d9ff33d56c356c1",
    "24a155c94577332891eea8ba8b522fad18d92fe6",
    "15bddc3cfe05b4e76be27da027c1d42edb475546",
    "b996a6aaca79351d107e4bf521272c43717f07a6",
    "90bebea832b381abcbd022f3682d2902e9ec8d40",
    "7d9926336bbdac6285a988d043c4ccfe126c94c5",
    "95e852793b7ff8604a8132e85d5facd08c91a36e",
    "93083c6c79f9e64d390bb912fb12238f6b35add9",
    "e4f872bbba497e6ff0bcb18c960cdf86875d3706",
    "24032e248422219f064dcfda01a70a37bb3fdb7a",
    "ab6689f7b74f16c0f2456383655dc6b1105ef5ae",
    "3f57250ddd29d729c8fcdf6da766db7fa7997013",
    "85b40cdad371262c00797737675ab3f586869034",
    "4d12f6522bc18414e36e4074fe75d8ef0fa5be07",
    "4e339ad26e3e6972e39364a9a60cf7cfc03fbf99",
    "ee92dc9290985330ed4860ac10e2a0302c0e418d",
    "d0ce1ee646608d69190f08bc1f9fd1f8a23bf353",
    "14d7371d4ed77b1e9bb04ff1d00e94e00eba32a7",
    "9cbd8aa4c5235a5ae2f01c60eaf464c0b60ccf6a",
    "ef45fe14dd21c926aadc64f3309655a8725e569c",
    "893ba7bf491fb6b31b7845318cc40ed783bdf672",
    "18769152438a5d3f609a49cd95c352fa8eba1928",
    "5c87ee2dcae6fffeddd84fe1a95e8539e049f315",
    "e7ff4e1740c9e0bc725f0161e266540620bbdf66",
    "d5b2d1001181f1cab1dc24d24e1ea42e7ad922ec",
    "6a74d46112d4ac1cfbb312b7a027cfcf4edf77fd",
    "30f901e55bd2f5038770ba152e8a0c6b6ac0890f",
    "7d14226dcc7209ff016c3f9653209ba42a602325",
    "9e2f5033bd3ef9e584005ea08c78563fcbee3bb3",
    "7d2e43da3cd3c618aececb5ef2b14800f5c6a059",
    "f3a982f6ad8b7a4c4223851afec6d6b9aeccee5b",
    "496c988aae74e7e432b67ed131211250b0a443e8",
    "0a1145a6bc08daa789642d4d8727f38c8b6290c3",
    "7f9c5aeb3bc0fb915c9674a91103b0ae1d164e52",
    "780a391c4635ca5c8652a027846d8ce070e3fb4e",
    "358884c609e204c7a2832d677480e4e010ecbb69",
    "b2dc247449ff3ca23a8458bc52add8d5ef56c113",
    "2c8e64917f48ec6a3d54d14bcaf5c75a1a49d468",
    "bec3af2a4e5c5604f78ca1c2170c53e4080916d4",
    "7237f1992ece150d8076353ac5820b8d920637c7",
    "13ec83b150d80e4ba1ff7c7a72874233c89cfb37",
    "8c209133f4ceb1dd5dbd39e55bb17ac99844ad08",
    "4a7d5978e364a6c8d0be159adac9f1db44c79590",
    "84d783048ba10c3ed3aa84e826f92e1f332b1893",
    "ef902874267c673cf48576e91b0e3062fbd555eb",
}

VALID_CLASSIFICATIONS = {"superseded", "already-done", "port", "decline"}

ROW_RE = re.compile(
    r"^\|\s*`?([0-9a-f]{7,40})`?\s*\|.*?\|\s*(superseded|already-done|port|decline)\s*\|",
    re.MULTILINE | re.IGNORECASE,
)


def _record_text():
    assert RECORD.exists(), f"{RECORD} does not exist"
    return RECORD.read_text()


def test_record_exists_and_names_the_tip_sha():
    text = _record_text()
    assert TIP_SHA in text, "record does not name the upstream tip SHA it was classified against"


def test_record_states_chosen_divergence_path():
    text = _record_text().lower()
    assert "stay diverged" in text or "re-fork" in text or "vendor" in text, (
        "record must state the chosen path for the divergence as a whole in one sentence"
    )


def test_record_classifies_every_commit_exactly_once():
    text = _record_text()
    rows = ROW_RE.findall(text)
    classified_hashes = [full_hash.lower() for full_hash, _ in rows]

    assert len(classified_hashes) == len(EXPECTED_COMMITS), (
        f"expected {len(EXPECTED_COMMITS)} classified commits, found {len(classified_hashes)}"
    )
    assert len(classified_hashes) == len(set(classified_hashes)), "a commit is classified more than once"

    # Compare on the shorter of full/abbreviated hash length actually used in the record.
    found_prefixes = set(classified_hashes)
    missing = [h for h in EXPECTED_COMMITS if not any(h.startswith(p) or p.startswith(h[:len(p)]) for p in found_prefixes)]
    assert not missing, f"commits missing from the record: {missing}"


def test_record_uses_only_valid_classifications():
    text = _record_text()
    rows = ROW_RE.findall(text)
    assert rows, "no classification rows found — table must use `| <sha> | ... | <classification> |` rows"
    for _, classification in rows:
        assert classification.lower() in VALID_CLASSIFICATIONS


def test_record_ported_commits_are_named_in_the_porting_commit():
    """DoD 4: a commit classified 'port' must be ported in this PR or named with a filed Motion card.

    All three port-classified commits here were hand-ported by 16b6862 (PR #5), whose message
    names each upstream short SHA it carried. This ties the record's 'port' rows to that evidence
    instead of trusting the classification on its own say-so.
    """
    import subprocess

    text = _record_text()
    rows = {h.lower(): c.lower() for h, c in ROW_RE.findall(text)}
    port_shas = [h for h, c in rows.items() if c == "port"]
    assert port_shas, "expected at least one commit classified 'port'"

    repo_root = Path(__file__).parent.parent
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%B", "16b6862"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, "expected 16b6862 (the porting commit) to exist in history"
    porting_commit_message = result.stdout.lower()

    for sha in port_shas:
        assert sha[:7] in porting_commit_message, (
            f"{sha[:7]} is classified 'port' but is not named in 16b6862's commit message"
        )
