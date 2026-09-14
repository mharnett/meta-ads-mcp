"""Behavioral + ratchet test for run-mcp.sh's Keychain resolution.

run-mcp.sh must source the shared drak_ops keychain_get.sh helper (resolved
via keychain_shell_helper_path()) instead of shelling out to
`security find-generic-password` inline. Runs hermetically: a fake
`security` and a fake `python` are placed first on PATH, so no real Keychain
access and no server launch. Mirrors drak-ops's own
tests/test_keychain_get_sh.py fake-security-on-PATH technique.
"""
import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "run-mcp.sh"

# run-mcp.sh resolves the shared helper by importing drak_ops, so the two
# behavioral tests below cannot run without that package on the interpreter
# path. It lives in the private mharnett/drak-ops repo and this fork's CI
# installs no credential to reach it, so on a runner they are skipped rather
# than silently red.
#
# KNOWN COVERAGE GAP, stated rather than left to look complete: on CI only
# the text ratchet at the bottom of this file runs. It is the assertion that
# actually guards the regression this file exists for -- that run-mcp.sh keeps
# sourcing the shared helper instead of re-inlining `security
# find-generic-password` -- and it needs no dependency, so the ratchet holds
# everywhere. What CI does not exercise is the end-to-end launch, which is a
# macOS Keychain path that only ever runs on Mark's Mac in the first place.
# Closing the gap properly means installing drak-ops in this workflow, which
# means putting a PAT into a fork's CI; not worth it for this.
_HAS_DRAK_OPS = importlib.util.find_spec("drak_ops") is not None
needs_drak_ops = pytest.mark.skipif(
    not _HAS_DRAK_OPS,
    reason="drak_ops not importable: run-mcp.sh's keychain_shell_helper_path() lookup would fail",
)

FAKE_SECURITY = """#!/bin/bash
acct=""; svc=""
while [ $# -gt 0 ]; do
  case "$1" in
    -a) acct="$2"; shift 2 ;;
    -s) svc="$2";  shift 2 ;;
    *)  shift ;;
  esac
done
while IFS= read -r row; do
  [ -z "$row" ] && continue
  racct="${row%%|*}"; rest="${row#*|}"; rsvc="${rest%%|*}"
  [ "$rsvc" = "$svc" ] || continue
  if [ -z "$acct" ] || [ "$racct" = "$acct" ]; then
    printf '%s' "${row##*|}"; exit 0
  fi
done <<< "$KEYCHAIN"
exit 44
"""

# Silent stub for the .venv python launched by `exec` -- prints nothing so a
# real secret could never leak into test output, matching mcp-google-ads's
# run-mcp.wrapper.test.mjs convention of a silent replacement binary.
FAKE_PYTHON_SILENT = "#!/bin/bash\nexit 0\n"
FAKE_PYTHON_ECHO = '#!/bin/bash\necho "TOKEN=${META_ACCESS_TOKEN:-}"\nexit 0\n'


def _sandbox_bin(tmp_path, python_body):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    venv_dir = tmp_path / ".venv" / "bin"
    venv_dir.mkdir(parents=True, exist_ok=True)

    security = bin_dir / "security"
    security.write_text(FAKE_SECURITY)
    security.chmod(security.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # run-mcp.sh execs the absolute .venv/bin/python path, not one resolved
    # via PATH -- so the stub must live at REPO_ROOT/.venv/bin/python. We
    # can't relocate REPO_ROOT for a hermetic test, so instead we run a copy
    # of the script with its exec line pointed at our stub.
    python = venv_dir / "python"
    python.write_text(python_body)
    python.chmod(python.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return bin_dir, python


def _run_script(tmp_path, keychain_rows, python_body=FAKE_PYTHON_ECHO):
    bin_dir, fake_python = _sandbox_bin(tmp_path, python_body)
    script_text = SCRIPT.read_text().replace(
        "/Users/mark/claude-code/mcps/meta-ads-mcp/.venv/bin/python",
        str(fake_python),
    )
    script_copy = tmp_path / "run-mcp.sh"
    script_copy.write_text(script_text)
    script_copy.chmod(script_copy.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["KEYCHAIN"] = keychain_rows
    return subprocess.run(
        ["bash", str(script_copy)], capture_output=True, text=True, env=env,
    )


@needs_drak_ops
def test_token_present_resolves_and_launches(tmp_path):
    result = _run_script(tmp_path, "meta-ads-mcp|META_ACCESS_TOKEN|tok123")
    assert result.returncode == 0
    assert "TOKEN=tok123" in result.stdout


@needs_drak_ops
def test_token_missing_is_fatal(tmp_path):
    result = _run_script(tmp_path, "", python_body=FAKE_PYTHON_SILENT)
    assert result.returncode == 1
    assert "META_ACCESS_TOKEN is empty" in result.stderr


def test_script_sources_shared_helper_via_keychain_shell_helper_path():
    text = SCRIPT.read_text()
    assert "keychain_shell_helper_path" in text
    assert 'source "$HELPER"' in text


def test_no_tracked_sh_file_still_shells_out_to_security_find_generic_password():
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.sh"],
        capture_output=True, text=True, check=True,
    ).stdout
    rel_files = [line for line in out.splitlines() if line]
    offenders = [
        rel for rel in rel_files
        if "find-generic-password" in (REPO_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"inline find-generic-password still present in: {offenders}"
