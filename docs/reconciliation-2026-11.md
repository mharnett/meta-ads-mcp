# Fork/upstream reconciliation, 2026-11

**Upstream tip this record was classified against:** `63d0e5e29f2cf823f7f5317a77e66151eceb7415`
(`pipeboard-co/meta-ads-mcp`, `main`)

**Covers:** the 10 commits after the 2026-09 record's tip
`2ef198e266ca6a37b6dc2c42335f0a0885002771`. The 51 commits before it remain classified in
`docs/reconciliation-2026-09.md`.

**Chosen path:** unchanged from 2026-09. The fork stays diverged and ports only reachable
security and dependency fixes.

## Reachability method

Same as 2026-09, with one check added: `run-mcp.sh`, the `Dockerfile` `CMD` and both
`~/.claude.json` registrations all launch `python -m meta_ads_mcp` over stdio, single user. No
deployment runs `--transport streamable-http`. A fix whose threat is one HTTP caller reading
another caller's data can't be reached here. Local-attacker and browser-origin fixes are
reachable on this laptop, so they are ported even when the risk is low.

## Classification

| Commit | Summary | Classification | Why |
|---|---|---|---|
| `63d0e5e29f2cf823f7f5317a77e66151eceb7415` | chore(deps): bump mcp (#170) | decline | dependency bump not taken opportunistically; `mcp` stays pinned |
| `093062c6655682a20ff0814b468e0e877263d494` | fix(security): stop writing access tokens to the debug log, GHSA-r3r9-3mrh-x966 (#168) | already-done | ported as `a3a6bfa` (PR #8) |
| `d5eaceeb00edb5a71c7432bb437bef120cc65bb6` | fix(security): write the token cache owner-only, GHSA-prmg-4fr3-mm6x (#167) | port | the fork already created the file 0600, but did not narrow a pre-existing file or the directory; covered by `tests/test_token_cache_permissions.py` |
| `8f8eda64dc00a04661b2d136dfb9415fc4b26800` | fix(security): confine save_ad_image_locally to an allowed base directory, GHSA-2h5x-4qc8-3x27 (#166) | already-done | done independently in `e68a917` (PR #11) |
| `d136b4ce681ceeaf68529fbf17b8bc276592740d` | fix(security): require is_global in the SSRF guard, GHSA-cx77-j6h8-3382 (#165) | port | reachable: `upload_ad_image` fetches a caller-supplied URL, and 100.64.0.0/10 passed the fork's guard; covered by `tests/test_ssrf_url_validation.py` |
| `9365b94ce2c2a8a0f3cce310445308530e178320` | fix(security): require an OAuth state on the callback, GHSA-75j5-qp3x-mx37 (#164) | already-done | the fork's authorization-code rewrite `e57d9e8` already rejects a missing or mismatched state |
| `8b6b0fd181850d1eae539c9166a7f5b352cbaa63` | fix(security): remove process-global image cache and MCP resource interface, GHSA-25fp-988j-w29f (#163) | decline | the threat is cross-caller under HTTP, which can't be reached over stdio; upstream also confirms nothing writes the cache, so it is always empty |
| `96eaf2d8a0e6f94e797fed2808756b32e1097b87` | fix(security): remove deep-research search/fetch tools, GHSA-j7p8-g5m6-3wv5 (#162) | decline | the threat is a module-level cache shared across HTTP callers; over stdio the only caller is the token owner |
| `ceee65b8180332f98660aee0e544aeb7855e5bd2` | chore(release): bump to 1.0.121 (#161) | decline | version bump only |
| `271ea4cd5e0e21ae306e3768af8fc4dd1b928298` | fix(security): HTML-escape OAuth callback error param, GHSA-6v2r-2m4r-768m (#160) | port | reachable whenever the local OAuth flow runs: the fork still reflected `error` unescaped (its `/token` endpoint was already gone, via `b6af84d`); covered by `tests/test_callback_server_xss.py` |

10 commits classified: 3 port, 3 already-done, 0 superseded, 4 decline.

## Port commits

All three are ported in the same PR as this record. The port re-implements each fix on the
fork's code rather than cherry-picking it, because the fork's auth and callback modules differ:

- **SSRF guard:** `_ip_is_disallowed` now requires `is_global` and lists the non-public
  networks.
- **OAuth callback:** `error` is HTML-escaped and capped at 200 characters. Every response
  carries `Content-Security-Policy: default-src 'none'`, `nosniff`, `X-Frame-Options: DENY`,
  `no-referrer` and `no-store`. The success page's own script runs under a per-response nonce.
- **Token cache:** the directory is narrowed to 0700 and the file to 0600 on save and on load.
  This also repairs a cache that an older version wrote.

## Follow-up

After this PR merges, bump `meta-ads-mcp` in `automation/git-janitor/upstream_diff_sweep.py`'s
`RECONCILED_FORKS` (in `mharnett/drak-stack-monorepo`) to `63d0e5e29f2cf823f7f5317a77e66151eceb7415`.
