# Xuanheng TODO - Active Dispatch Queue

**Version** v595 | **Date** 2026-06-26
**Source/runtime pointer**: source HEAD is the commit containing TODO v595; pre-edit source/origin checkpoint was `69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64`. Runtime `trade-core` source head is `69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64` as of `2026-06-26T21:45:04Z`.
**Current posture**: standing Demo authorization source plumbing is now runtime-synced and crontab expected-head pins are aligned, but bounded auth still fails closed because false-negative review/preflight cannot yet consume the standing Demo loss-control envelope. Current executable blocker is `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING`.
**Links**: loop spec `docs/agents/profit-first-autonomy-loop.md`; version log `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`; latest runtime sync checkpoint `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--standing_demo_auth_plumbing_runtime_sync_apply.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Stable loop source | `docs/agents/profit-first-autonomy-loop.md` defines the standing profit-first autonomous trading loop. | Agents must load this for loop behavior and load this TODO for current task state. Do not encode current candidate details into the loop spec. |
| Operator standing Demo authorization | Operator granted broad Demo operational authorization for development, deployment, and profit-loop progress, while requiring Demo evidence to remain live-applicable later. | Do not keep asking for generic permission. Convert standing authorization into structured runtime-readable Demo authority envelopes with loss controls, expiry, scope, and auditability. |
| Runtime auth reality | `2026-06-26T21:45:04Z` runtime check after sync: bounded auth sha `a2ee54e8bf91720a0f8c0bd1dfd19813d2eac266b2721ace346afec43e81c0f2`, mtime `2026-06-26T21:45:04.612928Z`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, `decision=defer`, no `authorization_id`, no emitted operator auth object, active runtime probe/order authority `false/false`. | Runtime now has the standing-auth source plumbing, but upstream false-negative/preflight still blocks admission. Do not rerun generic auth no-op audits. |
| False-negative/preflight reality | `false_negative_operator_review_latest.json` sha `df03c21f61bc820e59378881dc8e423f30c41e9ec349104534f063ad6b06eefb`, mtime `2026-06-26T21:29:17.571879Z`, still pending/defer; preflight sha `98a4a0cf3b3bc6c08f4d09f7a9fb34c74dbddf06e112325e9e580076444ceb8b`, mtime `2026-06-26T21:29:17.674307Z`, status `OPERATOR_REVIEW_REQUIRED`. | Current runtime remains non-admitting. Next source-progress blocker is making this layer consume the structured standing Demo envelope and emit machine-checkable ready/fail states. |
| Profitability reality | Runtime profitability scorecard at `2026-06-26T21:45:04Z` is `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING` (sha `f437a41d93248360f47b48a2f0309345326bf784e17f3407dfa48b895623f245`). | There are candidate paths, but no accepted profitability proof. Next work must produce executable Demo evidence only after runtime/admission gates pass. |
| Runtime sync state | Runtime source and origin/main are `69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64`; crontab has 11 matching expected-head pins, 0 old pins, 70 lines, no mainnet flag, no adapter enablement, and probe outcome recording remains disabled. | Source/expected-head drift is closed for this checkpoint. Reopen only on new runtime drift or source regression. |
| Standing auth plumbing source state | Source/test/runtime checkpoint `2026-06-26--standing_demo_auth_plumbing_runtime_sync_apply.md`: valid standing Demo JSON can derive candidate-scoped `authorization_id`, budget, and expiry; cron wrappers pass standing JSON only via explicit env path and default to `defer` when absent. Runtime has no standing env configured, and false-negative/preflight still blocks. | This grants no order/probe/live authority by itself. Next work must connect the standing envelope to the preflight/review layer without bypassing Rust, Decision Lease, Guardian, or Cost Gate rules. |
| Demo book / loss state | Latest accepted cleanup report shows post-action Bybit Demo open orders `0` and nonzero positions `0`; stale local `Working` rows and cleanup/risk-close/unattributed fills remain proof-excluded. | Exchange book is clean enough to resume bounded candidate work, but proof must remain candidate-matched and exclude cleanup/unattributed/local-stale rows. |
| Current candidate evidence | Candidate selection report selected exactly one review-only current-cap candidate, but current candidate identity must be read from the latest reports/artifacts, not from the stable loop spec. | Candidate-specific work should read the current TODO/reports/runtime artifacts before acting. |
| Verification of last runtime sync checkpoint | Linux focused verification passed auth `21`, cron static `24`, adjacent alpha/profitability `140`, bash syntax, py_compile, `git diff --check`, and service sanity without restart. Session state `/tmp/openclaw/session_loop_state_20260626T2131Z_standing_demo_auth_plumbing_sync_review.json` parsed as JSON. | Runtime sync is closed as `DONE_WITH_CONCERNS`; no profit proof or bounded execution happened. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING` | 0 | ACTIVE | PM -> PA/E1 -> E2 -> E4 -> E3 -> PM | False-negative operator review/preflight can consume structured `standing_demo_operator_authorization_v1` loss-control envelopes and emit auditable ready/fail states; absent/invalid/stale/scope-mismatched envelopes fail closed; no Cost Gate lowering, live/mainnet, runtime/order authority, or direct bounded execution is granted. | Runtime sync checkpoint `2026-06-26--standing_demo_auth_plumbing_runtime_sync_apply.md`; latest auth still blocks at false-negative preflight with `decision=defer`. | Build source/schema/runtime-check plumbing for standing-envelope consumption in the false-negative/preflight layer, then test fail-closed and positive ready states without order authority. |
| `P0-EXECUTION-EVIDENCE-LOOP` | 0 | WAITING | PM -> QC/MIT -> E3/BB -> PM | After standing Demo envelope is runtime-admissible, run only bounded, loss-controlled Demo execution that records candidate-matched fills, fees/slippage, controls, and reconstruction data. | Profitability scorecard says paths exist but execution evidence is missing. | Wait for preflight standing-envelope plumbing, a valid standing envelope, plan/admission review, and current candidate/execution envelope loss controls. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, proof exclusions, regime/OOS labels, and repeat path. | No authorized candidate-matched bounded Demo outcomes exist. | Run only after bounded Demo execution produces candidate-matched outcomes. |
| `P1-FEE-TIER-PRIVATE-READ-RUNTIME-INVOKE` | 1 | DEFERRED | PM -> E3 -> BB -> PM | One-shot exact-symbol fee-rate read may run only inside the standing Demo evidence envelope or separate E3/BB reviewed read scope; sanitized artifact only; no PG write, no runtime fee-cache replacement, no proof by itself. | v585 envelope is READY_NO_READ; actual private fee read has not run. | Reopen when execution envelope needs actual fee-tier evidence and the read is inside standing loss/evidence controls. |

## §2 Closed No-Repeat Markers

| ID | Status | Latest report/spec | No-repeat rule |
|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--standing_demo_auth_plumbing_runtime_sync_apply.md` | Runtime source/expected-head sync is done at `69f6c4b2`; do not repeat unless runtime source/pins drift or the synced standing-auth source regresses. |
| `P0-STANDING-DEMO-AUTHORIZATION-PLUMBING` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--standing_demo_authorization_plumbing_source_fix.md` | Source/test plumbing is done; do not repeat auth no-op audits. Reopen only for source regression or after runtime sync reveals a standing-envelope consumption failure. |
| `P1-PROFIT-FIRST-LOOP-REBASE` | DONE_WITH_CONCERNS | `docs/agents/profit-first-autonomy-loop.md` | Do not re-encode current tasks into the stable loop. Reopen only if operator changes loop principles or governance conflicts with the spec. |
| `P1-TODO-MAINTENANCE-SOURCE-POINTER-DRIFT-CORRECTION` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--todo_source_pointer_drift_correction.md` | Do not repeat for source pointer drift unless TODO active state again conflicts with verified source/runtime evidence or `docs/agents/todo-maintenance.md`. |
| `P1-AGGRESSIVE-ALPHA-REGIME-OOS-LABEL-CONTRACT-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--regime_oos_label_contract_no_order.md` | Reopen only if candidate identity, ADR-0047 evidence rules, label schema, or real auth/runtime data-access scope changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SOURCE-ONLY-LADDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Reopen only on changed candidate identity, fee/freshness/regime policy, source/runtime evidence delta, or reviewed exchange-facing scope. |
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. Unattributed/cleanup fills never count as promotion or bounded-probe proof. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md` | Reopen only if fresh evidence invalidates current candidate feasibility/ranking or the active loop rotates candidates after a failed/lossy outcome. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | Artifact `probe_ledger.jsonl` remains current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | Learning output becomes inactive review packet or standing-envelope-permitted parameter update; never direct live mutation. |

## §3 Hard Gates And Loss Controls

| Gate | Rule |
|---|---|
| Profit priority | Seek real risk-adjusted net PnL after fees/slippage. Process gates exist to prevent uncontrolled loss and false proof, not to replace profitability as the optimization target. |
| Standing Demo authorization | Generic operator permission is granted for Demo loop progress. Agents must convert it into structured runtime-readable loss-control envelopes instead of re-asking or repeating defer audits. |
| Loss controls | Autonomous trading actions must stay inside max loss, max notional, max attempts, max concurrency, kill-switch, and reconstructability limits. Expanding those limits requires reviewed envelope change. |
| Runtime/order path | Rust authority and Decision Lease remain required for order-capable actions. Direct unaudited order paths are not allowed. |
| Cost Gate | Do not lower global Cost Gate. Use candidate-scoped bounded Demo evidence and outcome review to learn whether a path deserves scale or mutation. |
| Proof | Profit proof requires candidate-matched fills, actual fees/slippage, matched controls, execution realism, proof-exclusion pass, and repeat/OOS path. |
| Live/mainnet | Still out of scope. Demo evidence must be live-applicable, but live requires separate live gates. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/agents/profit-first-autonomy-loop.md
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json, hashlib, os, datetime
for p in [
  "/tmp/openclaw/alpha_discovery_throughput/profitability_path_scorecard_latest.json",
  "/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json",
  "/tmp/openclaw/cost_gate_learning_lane/false_negative_operator_review_latest.json",
  "/tmp/openclaw/cost_gate_learning_lane/false_negative_bounded_probe_preflight_latest.json",
]:
    b=open(p,"rb").read(); d=json.loads(b)
    print(p, hashlib.sha256(b).hexdigest(), datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).isoformat(), d.get("status"), d.get("decision"))
PY'
```

**Maintenance contract**: stable loop behavior lives in `docs/agents/profit-first-autonomy-loop.md`; current tasks and runtime facts live here. Do not turn either file into a duplicated historical report.
**Self-check**: The next PM can identify the next action in under one minute: stop repeating runtime sync/auth no-op; build false-negative/preflight standing-envelope plumbing so runtime artifacts become actionable under loss controls.
