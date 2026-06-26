# Xuanheng TODO - Active Dispatch Queue

**Version** v592 | **Date** 2026-06-26
**Source/runtime pointer**: source HEAD is the commit containing TODO v592; pre-edit source/origin checkpoint was `da00709b4041835e23b5c3bdd347da3e2fe44949`. Runtime `trade-core` read-only source head remains `b224c759200d8dfc6fc4a53cbee39b8fb3683118` as of `2026-06-26T20:23:02Z`.
**Current posture**: P0 bounded Demo authorization is still blocked/no-op. v592 only refreshes the active queue to the latest no-admitted-auth-delta evidence and removes stale source/runtime pointers from v591.
**Links**: version log `docs/CLAUDE_CHANGELOG.md`; latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--todo_source_pointer_drift_correction.md`; prior auth semantic report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--p0_auth_semantic_delta_noop_no_authority.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Current loop state | `/tmp/openclaw/session_loop_state_20260626T2023Z_p0_auth_resumed_no_admitted_delta.json`, sha `cc45ea6a161c6178d09a1c5aa6ab033f453245c3390961bd159be41f80abad43`. | This round has an explicit anti-repeat state. It is resumed-run no-delta count `2/3` after the previous blocked goal was reactivated; do not mark the goal blocked again until the same condition repeats for `3/3`. |
| Source checkpoint | Pre-edit local/origin `main` were both `da00709b4041835e23b5c3bdd347da3e2fe44949`; v592 is docs-only TODO/changelog maintenance. | Source changed only to correct active queue state. This is not P0 authorization evidence and does not justify runtime source sync. |
| Runtime source | Runtime checkout read-only pointer remains clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; runtime status was `## main...origin/main [behind 1]` at `2026-06-26T20:23:02Z`. | Runtime drift is docs-only from the source side; no runtime apply is justified. |
| Bounded authorization artifact | Runtime `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json`, sha `fc898e1ae98094c163ec4e30ebb3fd33ebd7e8a62d9fe21d0558af0ef72f25d6`, mtime `2026-06-26T20:15:05.089360Z`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; candidate `grid_trading|AVAXUSDT|Sell`; `decision=defer`; no `authorization_id`, typed-confirm match, standing Demo authorization, probe authority, or order authority. | P0 authorization remains `BLOCKED`. Reopen only on a semantic authority delta, not cron sha/mtime churn. |
| False-negative operator review | Runtime `false_negative_operator_review_latest.json`, sha `fc7610d55cb5570ac381d13bc5fbd89720fdd62697eea24439a8e896b62f481b`, mtime `2026-06-26T19:29:18.803039Z`; status `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW`; selected `grid_trading|AVAXUSDT|Sell`, rank `2`; `decision=defer`; expected confirm `approve_cost_gate_false_negative_preflight:grid_trading|AVAXUSDT|Sell:2`; `typed_confirm_matches=false`. | This is still review-required state. It supplies no bounded-probe authority. |
| False-negative preflight | Runtime `false_negative_bounded_probe_preflight_latest.json`, sha `a6c2ac18af2b46e9d7508500f52aa8522de9ea24b8d49107cb188bb2a784b6ce`, mtime `2026-06-26T19:29:18.890524Z`; status `OPERATOR_REVIEW_REQUIRED`. | The preflight has not reached a runtime-admissible authorization state. |
| Regime/OOS label contract | Source-only smoke `/tmp/openclaw/regime_oos_label_contract_smoke_20260626T1420Z/regime_oos_label_contract.json`, sha `739f684258bf1b21ba26f44b1cf964f54a46eee94a5f31f7b9c949b0c3c8a9a7`, status `REGIME_OOS_LABEL_CONTRACT_READY_NO_AUTHORITY`. | Future AVAX proof must attach leak-free PIT regime, freshness, recent net fields, breadth/survivorship, repeat/OOS, purge/embargo, independent-sample labels, and reject/verdict labels. This is not proof or order admission. |
| Verification | Current session state parsed with `python3 -m json.tool`; source/runtime checks were read-only. | No runtime, PG, exchange, service, crontab, Cost Gate, writer, order, or authority mutation was performed. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no probe/order authority unless a valid scoped authorization object or valid exact typed confirm is admitted and E3/BB review passes. | `2026-06-26T20:23:02Z` read-only check: bounded auth sha `fc898e1a...` remains `decision=defer`, no `authorization_id`, no exact typed confirm, no standing Demo authorization, no probe/order authority. Session state sha `cc45ea6a...` classified this as `NO-OP_NO_EVIDENCE_DELTA`. | Wait for semantic authority delta: ready/authorized decision, non-empty `authorization_id`, exact typed-confirm match, valid standing Demo authorization, emitted authorization object, or active runtime probe/order authority. Do not rerun for defer-only sha/mtime refresh. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-FEE-TIER-PRIVATE-READ-RUNTIME-INVOKE-AUTHORIZATION` | 1 | BLOCKED | PM -> E3 -> BB -> PM | Any actual private fee-rate read requires a fresh one-shot runtime action: exact `AVAXUSDT`, no argv secrets, bounded timeout/no redirects, strict exact-row parser, sanitized artifact only, no PG write, no runtime fee-cache replacement, no proof/authority use. | v585 envelope is READY_NO_READ; no private read has been executed. | Stop unless a later checkpoint explicitly opens and reviews the one-shot private read action. |

## §2 Closed No-Repeat Markers

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P1-TODO-MAINTENANCE-SOURCE-POINTER-DRIFT-CORRECTION` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--todo_source_pointer_drift_correction.md` | Do not repeat for source pointer drift unless TODO active state again conflicts with verified source/runtime evidence or `docs/agents/todo-maintenance.md`. |
| `P1-AGGRESSIVE-ALPHA-REGIME-OOS-LABEL-CONTRACT-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--regime_oos_label_contract_no_order.md` | Do not rerun on the same gap/control/auth artifacts. Reopen only if candidate identity, ADR-0047 evidence rules, label schema, or a real auth/runtime data-access scope changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SOURCE-ONLY-LADDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Compact ladder is closed through low-price ranking, evidence-floor gap closure, control identity, current cap/risk, fee/slippage, fresh BBO, maker policy, public quote packet/capture, quote adapter, atomic preview runner, fee-tier/maker-ratio, private fee read envelope design/review, and regime/OOS label contract. Reopen only on changed candidate identity, fee/freshness/regime policy, source/runtime evidence delta, or reviewed exchange-facing scope. |
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. Unattributed/cleanup fills still never count as promotion or bounded-probe proof. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md` | AVAX Sell remains the current cap-feasible bounded Demo review candidate unless fresh evidence invalidates cap feasibility or ranking. |
| `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md` | Source-only envelope is reviewed and hardened, but actual private read remains blocked until separately opened through PM -> E3 -> BB. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md` | Runtime source is `b224c759`; expected-head pins were aligned. Do not repeat for docs/TODO/report/SCRIPT_INDEX drift. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | Artifact `probe_ledger.jsonl` remains current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | Learning output becomes inactive review packet only, never direct order/risk/live mutation. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | A changed defer artifact or broad chat approval is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or valid exact typed confirm after fixed runtime/preflight readiness plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, regime/OOS labels, and execution realism. |
| Live/mainnet | Out of scope; Demo experience must be reconstructable and portable for later live review, but cannot bypass live gates. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T2023Z_p0_auth_resumed_no_admitted_delta.json
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json, hashlib, os, datetime
p="/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json"
b=open(p,"rb").read(); d=json.loads(b)
print(hashlib.sha256(b).hexdigest())
print(datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).isoformat())
print(d.get("status"), d.get("decision"), d.get("candidate"), d.get("authorization_id"), d.get("typed_confirm_expected"), d.get("probe_authority_granted"), d.get("order_authority_granted"))
PY'
python3 -m json.tool /tmp/openclaw/regime_oos_label_contract_smoke_20260626T1420Z/regime_oos_label_contract.json | sed -n '1,220p'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 authorization is blocked; defer-only cron sha/mtime refresh is not enough to rerun P0. Reopen only on semantic authority delta or separately reviewed runtime/private-read scope.
