# Fork/upstream reconciliation — 2026-09

**Upstream tip this record was classified against:** `2ef198e266ca6a37b6dc2c42335f0a0885002771`
(`pipeboard-co/meta-ads-mcp`, `main`)

**Chosen path for the divergence as a whole:** stay diverged and keep porting only reachable
security/dependency fixes on demand — this fork excised pipeboard.co cloud-auth (v1.2.0), made
writes opt-in (v1.1.0), and rewrote auth to an OAuth authorization-code flow, all load-bearing
removals that a re-fork would have to re-fight, and the fork is already slated for full
deprecation in favor of `mcp-meta-ads-incrementality` once its two remaining capability gaps
close (see README's deprecation notice), so vendoring-only or re-forking would be sunk cost.

## Reachability method

Checked against how this fork actually launches: `run-mcp.sh` → `python -m meta_ads_mcp`, stdio
transport only, `--transport streamable-http` never invoked. Commits that only matter under the
HTTP/SSE transport are unreachable under this launch path — a config fact, not a code guarantee,
since `--transport streamable-http` still exists at `core/server.py:213`.

## Classification

| Commit | Summary | Classification | Why |
|---|---|---|---|
| `2ef198e266ca6a37b6dc2c42335f0a0885002771` | chore(deps): bump mcp in the pip group (#150) | decline | dependency bump we don't take opportunistically; `mcp` stays pinned at 1.12.2 |
| `cbe4c6351ec3d80ca540def1ed768a76dc034209` | feat(auth)!: drop PIPEBOARD_API_TOKEN auth (#157) | already-done | this fork already dropped pipeboard.co cloud-auth independently in v1.2.0 |
| `ef2592d2d1b0702daa4793dedadf862cad5aedc0` | fix(security): attach HTTP auth middleware under `--sse-response` (GHSA-8353-5qhw-8hfw) (#151) | decline | HTTP/SSE-transport-only hardening, unreachable under stdio-only launch |
| `3b612c7d59646c76cc544d2d224baa550ca6b046` | chore(release): bump to 1.0.118 (#148) | decline | version bump only, no behavior change |
| `db8b9b8de5d6ef0f531c465f2d98dcbdc0c9779f` | fix(targeting): accept custom_locations/places/electoral_districts in estimate_audience_size preflight (#147) | decline | tool-shape enhancement, not requested by any current client; port on demand |
| `225f46f5586a66add4e30cca218c5e88982e066c` | docs(readme): front-load multi-platform + hosted + clients lede (#146) | decline | upstream marketing copy; our README carries our own deprecation notice instead |
| `555ae487f4a88cf4ea148ca58d9ff33d56c356c1` | fix(security): stop make_api_request mutating caller's params dict, token leak (#145) | port | hand-ported in `16b6862` (PR #5) |
| `24a155c94577332891eea8ba8b522fad18d92fe6` | docs(readme): Meta Business Partner positioning + comparison table (#142) | decline | marketing docs, not applicable to this fork's README |
| `15bddc3cfe05b4e76be27da027c1d42edb475546` | fix(insights): keep leads/CPL on platform_position breakdown (#141) | decline | tool-shape fix for an insights breakdown combo not currently exercised; port on demand |
| `b996a6aaca79351d107e4bf521272c43717f07a6` | docs(create_adset): clarify OUTCOME_ENGAGEMENT conversion locations (#140) | decline | docs only |
| `90bebea832b381abcbd022f3682d2902e9ec8d40` | docs(security): document GHSA-2v2f-mvfg-ph56 in SECURITY.md (#139) | decline | docs-only advisory note, no accompanying code change to evaluate; our SECURITY.md tracks our own fixes |
| `7d9926336bbdac6285a988d043c4ccfe126c94c5` | fix(security): block SSRF in upload_ad_image image_url fetch, GHSA-45gf-fjxp-cjpq (#138) | port | hand-ported in `16b6862` (PR #5) |
| `95e852793b7ff8604a8132e85d5facd08c91a36e` | fix(auth): require primary access-token credential at HTTP middleware (#137) | decline | HTTP-middleware-only hardening, unreachable under stdio-only launch |
| `93083c6c79f9e64d390bb912fb12238f6b35add9` | fix(deps): require starlette>=1.0.1, CVE-2026-48710 (#136) | port | hand-ported in `16b6862` (PR #5); `mcp` bump in the same upstream commit not taken |
| `e4f872bbba497e6ff0bcb18c960cdf86875d3706` | fix(auth): distinguish policy-blocked errors from token expiry (#134) | decline | HTTP-middleware-only error handling, unreachable under stdio-only launch |
| `24032e248422219f064dcfda01a70a37bb3fdb7a` | Bump version to 1.0.112 (#133) | decline | version bump only |
| `ab6689f7b74f16c0f2456383655dc6b1105ef5ae` | fix(video): surface real thumbnail frame and processing status (#132) | decline | tool-shape enhancement not currently exposed; port on demand |
| `3f57250ddd29d729c8fcdf6da766db7fa7997013` | Bump version to 1.0.111 (#131) | decline | version bump only |
| `85b40cdad371262c00797737675ab3f586869034` | Fix DOF + video + multi-text returning Meta error 2061015 (#130) | decline | error-shape fix for a creative path not hit by our current client set; port on demand if reproduced |
| `4d12f6522bc18414e36e4074fe75d8ef0fa5be07` | docs(readme): lead with Pipeboard MCP family (#129) | decline | marketing docs |
| `4e339ad26e3e6972e39364a9a60cf7cfc03fbf99` | docs(readme): writes-first framing + subdomain URLs + Snap/Reddit (#128) | decline | marketing docs |
| `ee92dc9290985330ed4860ac10e2a0302c0e418d` | feat(meta-ads): get_image_by_hash tool (#127) | decline | new tool-shape feature not adopted here; if the image/video library gap needs closing it belongs in `mcp-meta-ads-incrementality` per the README's deprecation notice, not this fork |
| `d0ce1ee646608d69190f08bc1f9fd1f8a23bf353` | docs(create_ad_creative): promote Placement Asset Customization to a named mode (#126) | decline | docs only |
| `14d7371d4ed77b1e9bb04ff1d00e94e00eba32a7` | fix(security): reject unauthenticated HTTP + redact tokens in error URLs, GHSA-9gw6-46qc-99vr (#125) | decline | HTTP-middleware-only hardening, unreachable under stdio-only launch |
| `9cbd8aa4c5235a5ae2f01c60eaf464c0b60ccf6a` | feat(transport): drop streamable_http_path override (#124) | decline | HTTP-transport-only, unreachable under stdio-only launch |
| `ef45fe14dd21c926aadc64f3309655a8725e569c` | fix(transport): disable DNS rebinding protection (#123) | decline | HTTP-transport-only, unreachable under stdio-only launch; re-evaluate if the transport is ever enabled |
| `893ba7bf491fb6b31b7845318cc40ed783bdf672` | fix(streamable-http): pin mount to /mcp/ (#122) | decline | HTTP-transport-only, unreachable under stdio-only launch |
| `18769152438a5d3f609a49cd95c352fa8eba1928` | fix(create_ad_creative): single video + IG actor -> object_story_spec for CTWA (#119) | decline | tool-shape fix for a CTWA creative path not currently exercised; port on demand |
| `5c87ee2dcae6fffeddd84fe1a95e8539e049f315` | chore(deps): bump mcp in the pip group (#121) | decline | dependency bump; `mcp` stays pinned |
| `e7ff4e1740c9e0bc725f0161e266540620bbdf66` | chore(release): bump to 1.0.103 (#117) | decline | version bump only |
| `d5b2d1001181f1cab1dc24d24e1ea42e7ad922ec` | fix(create_ad_creative): serialize CALL_NOW phone_number as tel: URI (#116) | decline | tool-shape fix for a CTA not currently used; port on demand |
| `6a74d46112d4ac1cfbb312b7a027cfcf4edf77fd` | Translate deprecated instagram_actor_id to instagram_user_id (#114) | decline | compat shim for a deprecated Meta field; port on demand if a client hits it |
| `30f901e55bd2f5038770ba152e8a0c6b6ac0890f` | chore(release): sync server.json version with pyproject.toml (#113) | decline | release hygiene only |
| `7d14226dcc7209ff016c3f9653209ba42a602325` | feat(campaigns): add adset_budgets to update_campaign for CBO to ABO migration (#112) | decline | tool-shape feature not requested by current clients |
| `9e2f5033bd3ef9e584005ea08c78563fcbee3bb3` | feat(ads): return effective_status and issues_info on get_ads/get_ad_details (#111) | decline | tool-shape enhancement not adopted |
| `7d2e43da3cd3c618aececb5ef2b14800f5c6a059` | docs(create_campaign): expand tool description (#110) | decline | docs only |
| `f3a982f6ad8b7a4c4223851afec6d6b9aeccee5b` | fix(creatives): strip deprecated standard_enhancements from GET responses (#109) | decline | tool-shape fix not currently causing observed issues; port on demand |
| `496c988aae74e7e432b67ed131211250b0a443e8` | feat(insights): action_breakdowns override + auto-empty for media_type (#107) | decline | tool-shape feature not adopted |
| `0a1145a6bc08daa789642d4d8727f38c8b6290c3` | docs(insights): restore media_type to supported list (#106) | decline | docs only |
| `7f9c5aeb3bc0fb915c9674a91103b0ae1d164e52` | docs(insights): remove unsupported media_* breakdowns (#105) | decline | docs only, self-reverted by upstream's own #106 above |
| `780a391c4635ca5c8652a027846d8ce070e3fb4e` | fix(insights,accounts): platform_position breakdown + fields passthrough on get_account_info (#103) | decline | tool-shape fix not exercised by current client set; port on demand |
| `358884c609e204c7a2832d677480e4e010ecbb69` | feat(duplicate_creative): add new_creative_features_spec override param (#102) | decline | tool-shape feature not adopted |
| `b2dc247449ff3ca23a8458bc52add8d5ef56c113` | fix(ads): accept {text,adlabels} headlines/descriptions/messages, drop client-side length guards (#101) | decline | tool-shape change not adopted |
| `2c8e64917f48ec6a3d54d14bcaf5c75a1a49d468` | fix(ads): emit call_to_actions plural with lead_gen_form_id on asset_feed_spec path (#100) | decline | tool-shape fix for lead-gen ads not used by current clients |
| `bec3af2a4e5c5604f78ca1c2170c53e4080916d4` | docs(ads): expand call_to_action_type enum list (#99) | decline | docs only |
| `7237f1992ece150d8076353ac5820b8d920637c7` | docs(ads): clarify link_url required when asset_customization_rules is set (#97) | decline | docs only; the placement-specific-creative capability gap itself is tracked for closure in `mcp-meta-ads-incrementality`, not this fork |
| `13ec83b150d80e4ba1ff7c7a72874233c89cfb37` | docs(ads): rewrite DOF-downgrade warning to name PAC (#95) | decline | docs only |
| `8c209133f4ceb1dd5dbd39e55bb17ac99844ad08` | fix(ads): reuse existing video adlabel in placement_groups rules (#94) | decline | tool-shape fix for the placement-specific-creative gap; real closure work belongs in `mcp-meta-ads-incrementality` per the README's deprecation notice |
| `4a7d5978e364a6c8d0be159adac9f1db44c79590` | fix(ads): detect silent single-image collapse in create_ad_creative (#93) | decline | tool-shape fix not currently causing observed issues; port on demand |
| `84d783048ba10c3ed3aa84e826f92e1f332b1893` | docs: remove RELEASE.md (#92) | decline | this fork keeps its own RELEASE.md; not applicable |
| `ef902874267c673cf48576e91b0e3062fbd555eb` | feat(adsets): expose bid_adjustments + bump to 1.0.87 (#91) | decline | tool-shape feature not adopted |

51 commits classified: 3 port, 1 already-done, 0 superseded, 47 decline.

## Port commits

All three commits classified `port` were hand-ported in the same PR as the previous reconciliation
pass, `16b6862` ("security: port the 3 reachable upstream fixes, not the other 48 commits", PR #5),
which is already merged to `main`. None require a newly filed Motion card.

## Follow-up

A card must be filed against `mharnett/drak-stack-monorepo` to add `meta-ads-mcp` to
`automation/git-janitor/upstream_diff_sweep.py`'s `RECONCILED_FORKS`, pinned to tip
`2ef198e266ca6a37b6dc2c42335f0a0885002771`. That edit is out of scope for this record — see the
PR's "Requested follow-ups" section for the exact card to file.
