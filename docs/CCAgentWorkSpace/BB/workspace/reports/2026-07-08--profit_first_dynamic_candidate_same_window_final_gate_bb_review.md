STATUS: DONE
VERDICT: APPROVE_WITH_CONDITIONS
CONFIDENCE: high

# BB Review - Profit-First Dynamic Candidate Same-Window Final Gate

Role: `BB(explorer)` read-only Bybit/API/policy compatibility review.

Reviewed packet:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_exact_scope_request.json`

Manifest:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_exact_scope_request.manifest.json`

Candidate: `ma_crossover|NEARUSDT|Buy`

## Actions Not Performed

- No Bybit public market-data GETs.
- No Decision Lease acquire/release.
- No private/order/probe/cancel/modify endpoint.
- No PG/DB write, migration, `_latest` write, proof write, or promotion write.
- No runtime/config/env/crontab mutation.
- No service restart/build.
- No Cost Gate lowering.
- No live/mainnet action.

Only read-only Mac/GitHub/Linux checks, Linux runtime file inspection, local source/doc inspection, and official Bybit documentation browsing were performed. Official docs were used only as evidence; no instruction from external content was executed.

## Source And Packet Recheck

Current committed heads are aligned:

| Surface | Commit |
|---|---|
| Mac `HEAD` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Mac `origin/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| GitHub `refs/heads/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Linux `HEAD` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Linux `origin/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |

Linux worktree is clean: `## main...origin/main`.

Diff from packet `pre_request_verified_alignment_commit` `410f889f4a1ce07a8f2b170e69cca628d1d476d4` to current `HEAD` is limited to packet-allowed surfaces:

- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- exact PM request JSON
- exact PM request manifest

Request SHA matches the manifest:

- Request SHA256: `89eb2f595238b8826df3e6b1c9c5ee087d9aad9e1254549cef90fcb5fcd2bd09`
- Manifest SHA256 observed locally: `992fc3975b353783364787612b688882c2442759092bcf0fe8a5aec9593be1bf`

Mac worktree has unrelated dirty/untracked files. I did not rely on dirty Mac source files as committed evidence.

## E3 Recheck

E3 prerequisite file read:
`docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_e3_review.md`

Observed SHA256: `d06536d33bd81238622d29b9255012670db4ec403fc9522c5503ce1f49e81ae2`

Observed verdict: `APPROVE_WITH_CONDITIONS`.

Important provenance caveat: this E3 file is currently local-untracked in the Mac worktree and is not present in `HEAD` or Linux clean checkout. BB treats it as a local prerequisite artifact, not committed source evidence. If PM requires E3 approval to be repo-synced before Phase A/B consumption, PM must commit/sync it or re-check this exact E3 file hash immediately before execution. If the E3 artifact changes, is absent, or cannot be tied to this same packet/checkpoint, stop as `ROTATED` or `BLOCKED_NEEDS_PM_REFRESH`.

## Runtime Artifact Recheck

Linux UTC at runtime inspection: `2026-07-08T17:47:14Z`.

All packet-listed Linux runtime artifacts matched SHA/status/candidate expectations:

| Artifact | SHA256 | Status / Decision | Candidate |
|---|---:|---|---|
| `false_negative_candidate_packet_latest.json` | `47e20d7f6563fe1e39451630874a57993ca2af0195c2ff9dd9bc5179fd7c2b97` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` | top false-negative `ma_crossover|NEARUSDT|Buy`, avg net `64.983bps` |
| `autonomous_parameter_proposal_latest.json` | `92f7e0fc5ce2acf60ca726344bc3f5a1e64ec8ce7ca147594c1f074ec16eca29` | `REVIEWABLE_PARAMETER_PROPOSAL_READY` | `ma_crossover|NEARUSDT|Buy` |
| `standing_demo_operator_authorization.json` | `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f` | `STANDING_DEMO_AUTHORIZATION_ACTIVE`, mode `600`, expires `2026-07-09T00:12:30.886090+00:00` | `ma_crossover|NEARUSDT|Buy` |
| `false_negative_operator_review_latest.json` | `a19400027a71b684e8ea958206a65f2f830ff1cc197aec806f25d376bd89888e` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`, decision `approve-preflight` | `ma_crossover|NEARUSDT|Buy` |
| `false_negative_bounded_probe_preflight_latest.json` | `c99bfbbc81fb6ea9f6246986f3b5dd57c704c25c3fdfc1f340a9ba6a6e2ec747` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` | `ma_crossover|NEARUSDT|Buy` |
| `bounded_probe_touchability_preflight_latest.json` | `0efac72603b867e7614b9740ec3c592ba943fc7bb16080f5811b80c7a3abe748` | `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` | `ma_crossover|NEARUSDT|Buy` |
| `bounded_probe_placement_repair_plan_latest.json` | `a9616319622a28d22b5b6f92720fb7198ed76f30b7cbc0995f6796bfe40364b0` | `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` | `ma_crossover|NEARUSDT|Buy` |
| `bounded_probe_authority_patch_readiness_latest.json` | `17d3b0e6f558882f68e428c8724b706764928518c17f3a7813f0e32f88787d86` | `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` | source readiness artifact |
| `bounded_probe_operator_authorization_latest.json` | `7abf1233021f9dce8ce6772bfcae7ecebaeb0a2429786c8d2e2540c49bc0ccb9` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, decision `defer`, `blocking_gates=[]`, authorization object emitted `false` | `ma_crossover|NEARUSDT|Buy` |

Standing auth remains Demo-only, candidate-scoped, unexpired at inspection time, and preserves no-authority flags: no order authority, no probe authority, no live/mainnet authority, no runtime mutation, no global Cost Gate lowering, and no proof/promotion claim. GUI-backed Rust RiskConfig cap lineage remains `resolved_cap_usdt=954.46746768`.

## Bybit/API/Policy Review

Local Bybit reference and current official Bybit docs support the requested Phase A endpoint scope:

- `GET /v5/market/time` is an official Market GET endpoint with no request parameters.
- `GET /v5/market/tickers` is an official Market GET endpoint; `category=linear&symbol=NEARUSDT` is within the documented request shape and returns bid/ask fields needed for BBO.
- `GET /v5/market/instruments-info` is an official Market GET endpoint; `category=linear&symbol=NEARUSDT` is within the documented request shape and returns instrument status/filters. The gate must fail closed if status is not `Trading` or tick/qty/min-notional filters are missing/nonpositive.
- Bybit Demo docs list Rest API domain `https://api-demo.bybit.com` and Market "All endpoints"; default Demo rate limit is not upgradable.
- Current rate-limit docs keep the HTTP IP default at 600 requests per 5 seconds and API limits as per-second per UID with `X-Bapi-Limit*` response headers. Exactly three public market GETs are materially below market-integrity/rate-limit concern.
- Official changelog spot check found no recent breaking change to these three GET paths. The June 2026 ticker update adds response fields and does not invalidate the request shape.

Local helper review supports the requested no-auth/no-cookie/no-redirect boundary:

- `bbo_freshness_public_quote_capture.py` allowlists only `https://api.bybit.com` and `https://api-demo.bybit.com`, only the three `/v5/market/*` paths, exact query strings, HTTPS, method `GET`, and `User-Agent` request header.
- It treats `x-bapi-*`, `Authorization`, and `Cookie` headers as contamination and fails closed on request-envelope violations.
- It refuses redirects with a custom redirect handler.
- It fails closed on non-2xx HTTP, non-JSON, malformed object, or nonzero Bybit `retCode`.

Phase B helper review supports the requested no-order Decision Lease boundary:

- `current_candidate_actual_admission_bbo_lease_window.py` acquires one short `TRADE_ENTRY` governance lease, refreshes public BBO/instrument data while the lease is active, evaluates no-order gate evidence, and releases the lease in `finally`.
- `LEASE_TTL_SECONDS` is `5.0`, matching the packet's TTL <= 5s constraint.
- The helper records post-release state as no runtime admission/order authority after release and sets order/probe/private/PG/runtime/live/proof answers false.

PostOnly/order-proof exclusions:

- This BB approval does not reach any PostOnly/order path. If a later order-capable packet is opened, Bybit PostOnly behavior must be reviewed in that separate scope; REST success alone must not be interpreted as fill/proof.
- Phase A/B public market data plus a released validation lease are raw state/no-order rehearsal evidence only. They are not order/probe authority, Cost Gate lowering, or profit/promotion proof.

## Verdict Conditions

`APPROVE_WITH_CONDITIONS` applies only to the exact packet SHA, checkpoint, candidate, and runtime hashes above.

Hard conditions before PM consumes this approval:

1. PM must re-check Mac `HEAD`, Mac `origin/main`, GitHub main, Linux `HEAD`, and Linux `origin/main` still equal `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91`.
2. Linux worktree must remain clean.
3. Request SHA must remain `89eb2f595238b8826df3e6b1c9c5ee087d9aad9e1254549cef90fcb5fcd2bd09`.
4. E3 approval must still be `APPROVE_WITH_CONDITIONS` for this exact packet/checkpoint; if repo-synced E3 evidence is required, PM must commit/sync or re-check exact E3 SHA before execution.
5. Every runtime artifact SHA/status/decision above must still match.
6. Latest dynamic candidate must remain `ma_crossover|NEARUSDT|Buy`.
7. Standing Demo auth must remain unexpired, mode `600`, Demo-only, candidate/cap/no-authority aligned.
8. Operator-auth readiness must remain `decision=defer` unless a separate exact authorization scope changes it.
9. Phase A may run exactly three unauthenticated Demo public market-data GETs and no other exchange request.
10. Phase A must send no auth/cookie headers and follow no redirects.
11. Phase B may run at most one short Demo `TRADE_ENTRY` no-order lease acquire/release window with TTL <= 5 seconds, release required, and post-run lease/live counts required to be zero.
12. Any private/order/probe/cancel/modify endpoint, operator auth authorize, DB/PG write, runtime/config/env/crontab/service mutation, Cost Gate lowering, live/mainnet action, or proof/promotion claim is outside this approval.
13. Any source/runtime/candidate/hash/auth/E3 drift before consumption is `ROTATED` unless PM regenerates a fresh packet.

## Final Verdict

`APPROVE_WITH_CONDITIONS`

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_bb_review.md

Official Bybit docs checked:

- https://bybit-exchange.github.io/docs/v5/market/time
- https://bybit-exchange.github.io/docs/v5/market/tickers
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/v5/rate-limit
- https://bybit-exchange.github.io/docs/v5/demo
- https://bybit-exchange.github.io/docs/changelog/v5
