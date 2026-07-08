STATUS: DONE
VERDICT: APPROVE_WITH_CONDITIONS
CONFIDENCE: high

# E3 Review - Profit-First Dynamic Candidate Same-Window Final Gate

Role: `E3(explorer)` read-only security/runtime review.

Request:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_exact_scope_request.json`

Manifest:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_same_window_final_gate_exact_scope_request.manifest.json`

Candidate: `ma_crossover|NEARUSDT|Buy`.

## Scope Boundary

No Bybit public/private call, Decision Lease acquire/release, order/probe/cancel/modify, PG/DB write, runtime/env/service/crontab mutation, build/restart, Cost Gate change, live/mainnet action, or proof/promotion claim was performed by this review.

The only write is this report.

## Request And Manifest

- Request sha256 matched expected: `89eb2f595238b8826df3e6b1c9c5ee087d9aad9e1254549cef90fcb5fcd2bd09`.
- Manifest sha256 observed: `992fc3975b353783364787612b688882c2442759092bcf0fe8a5aec9593be1bf`.
- Request schema passed: `current_candidate_same_window_final_gate_exact_scope_request_v1`.
- Manifest schema passed: `exact_scope_request_manifest_v1`.
- Request is committed in current `HEAD`; `git show HEAD:<request>` hashes to the same `89eb2f59...` value.
- Manifest grants no authority: `authority_granted_by_manifest=false`; hard-boundary flags deny private calls, order/probe/cancel/modify, runtime mutation, DB write, Cost Gate lowering, live/mainnet, and proof/promotion.

## Source And Runtime Head Check

Expected checkpoint: `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91`.

| Surface | Result |
|---|---|
| Mac `HEAD` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Mac `origin/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| GitHub `refs/heads/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Linux `HEAD` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Linux `origin/main` | `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91` |
| Linux worktree | clean: `## main...origin/main` |

Diff from request `pre_request_verified_alignment_commit` `410f889f4a1ce07a8f2b170e69cca628d1d476d4` to current `HEAD` is limited to the packet-allowed surfaces:

- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- request JSON
- request manifest JSON

Mac worktree has unrelated dirty files and untracked E3 reports; these were excluded from evidence.

## Runtime Input Recheck

Linux UTC at current inspection: `2026-07-08T17:44:10Z`.

All packet-listed runtime `_latest` hashes matched Linux:

| Runtime input | Packet / Linux sha256 | Current status |
|---|---|---|
| `false_negative_candidate_packet_latest.json` | `47e20d7f6563fe1e39451630874a57993ca2af0195c2ff9dd9bc5179fd7c2b97` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` |
| `autonomous_parameter_proposal_latest.json` | `92f7e0fc5ce2acf60ca726344bc3f5a1e64ec8ce7ca147594c1f074ec16eca29` | `REVIEWABLE_PARAMETER_PROPOSAL_READY` |
| `standing_demo_operator_authorization.json` | `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f` | `STANDING_DEMO_AUTHORIZATION_ACTIVE` |
| `false_negative_operator_review_latest.json` | `a19400027a71b684e8ea958206a65f2f830ff1cc197aec806f25d376bd89888e` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT` |
| `false_negative_bounded_probe_preflight_latest.json` | `c99bfbbc81fb6ea9f6246986f3b5dd57c704c25c3fdfc1f340a9ba6a6e2ec747` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` |
| `bounded_probe_touchability_preflight_latest.json` | `0efac72603b867e7614b9740ec3c592ba943fc7bb16080f5811b80c7a3abe748` | `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` |
| `bounded_probe_placement_repair_plan_latest.json` | `a9616319622a28d22b5b6f92720fb7198ed76f30b7cbc0995f6796bfe40364b0` | `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` |
| `bounded_probe_authority_patch_readiness_latest.json` | `17d3b0e6f558882f68e428c8724b706764928518c17f3a7813f0e32f88787d86` | `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` |
| `bounded_probe_operator_authorization_latest.json` | `7abf1233021f9dce8ce6772bfcae7ecebaeb0a2429786c8d2e2540c49bc0ccb9` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW` |

Dynamic candidate check:

- Top false-negative candidate remains `ma_crossover|NEARUSDT|Buy`.
- Proposal `selected_side_cell_key` remains `ma_crossover|NEARUSDT|Buy`.
- Proposal avg net remains `64.983bps`.
- Proposal flags still deny order authority, probe authority, promotion evidence, and global Cost Gate lowering.

Standing auth check:

- File mode: `600`.
- Environment: `demo`.
- Expires: `2026-07-09T00:12:30.886090+00:00`; unexpired against Linux UTC `2026-07-08T17:44:10Z`.
- Candidate: strategy `ma_crossover`, symbol `NEARUSDT`, side `Buy`, horizon `60`.
- Cap lineage is GUI-backed Rust RiskConfig; resolved cap `954.46746768` USDT; local `10 USDT` is explicitly not global risk authority.
- No-authority flags remain false for active runtime order authority, active runtime probe authority, bounded Demo probe authorization, order submission, probe/order authority grants, live authority, runtime/env/crontab mutation, Cost Gate lowering, promotion evidence, and proof.

Operator-auth readiness:

- Status: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`.
- Decision: `defer`.
- Blocking gates: `[]`.
- Operator authorization object: `null`.
- No plan/runtime mutation, writer enablement, order/probe authority, Cost Gate lowering, promotion evidence, or proof is granted.

## Phase 0/A/B Security Shape

E3 accepts the requested future shape only if BB also approves this exact packet and PM repeats same-window rechecks immediately before use.

Approved conditional shape:

- Phase 0: local no-authority input refresh only; no exchange call, lease action, private endpoint, PG write, runtime mutation, service restart, or build.
- Phase A: exactly three unauthenticated Bybit Demo public market-data GETs for `NEARUSDT`:
  - `GET /v5/market/time`
  - `GET /v5/market/tickers?category=linear&symbol=NEARUSDT`
  - `GET /v5/market/instruments-info?category=linear&symbol=NEARUSDT`
- Phase A must use no auth/cookie headers, refuse redirects, stay on allowlisted HTTPS base URL, and touch no private/order endpoint.
- Phase B: one `TRADE_ENTRY` no-order validation window only, max lease TTL `5s`, acquire then release in the same invocation, with post-run governance snapshot and post-run lease/live counts required to be zero.
- The released lease must not be reused as admission, order authority, or proof.

Source review of the named helper confirms the intended no-order boundary: explicit env plus CLI opt-in, TTL guard, public quote capture only, read-only gate evidence, release in `finally`, and output flags that keep private call, order/probe/cancel/modify, PG write, runtime mutation, Cost Gate lowering, live/mainnet, and proof all false.

## Conditions

`APPROVE_WITH_CONDITIONS` is valid only for the exact committed checkpoint and runtime hashes listed above.

Required before any PM consumption:

1. BB independently returns `APPROVE_WITH_CONDITIONS` for this exact request path, request SHA, and checkpoint.
2. PM rechecks Mac `HEAD`, Mac `origin/main`, GitHub main, Linux `HEAD`, and Linux `origin/main` still equal `08f7e9571f03a2dea7a0a20e0e8fe4e0d4c01d91`.
3. Linux worktree remains clean.
4. Every runtime SHA/status/decision listed above still matches Linux.
5. Standing Demo auth remains unexpired and candidate/cap/no-authority aligned.
6. Operator-auth readiness remains `decision=defer` unless a separate exact authorization scope changes it.
7. Any source, runtime, candidate, hash, auth, endpoint, lease-release, or authority drift before consumption is `ROTATED`.

## Next PM Work Item If This Rotates

If any condition fails before consumption: `ROTATED; regenerate same-window final gate packet from current machine-readable artifacts, commit/sync it, and re-dispatch E3/BB`.

## Verdict

`APPROVE_WITH_CONDITIONS`

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW; gating result `APPROVE_WITH_CONDITIONS`.
