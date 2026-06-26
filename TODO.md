# Xuanheng TODO - Active Dispatch Queue

**Version** v574 | **Date** 2026-06-26
**Source/runtime pointer**: source patch base `edf3b4fe6fe25a961f721941609306e0976699e0`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T10:24:35Z`; no runtime/service mutation.
**Current posture**: pause after v574. The next actionable blocker is `P0-BOUNDED-PROBE-AUTHORIZATION`, still `BLOCKED_BY_RUNTIME_AUTHORIZATION`; v574 closed candidate-source freshness and produced only no-order preview evidence.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T10:24:35Z`: runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API MainPID `2218842`. | Do not sync/restart unless a separate runtime blocker is opened. |
| Bounded authorization | Latest auth sha `61483e69223049e1cac40a9ea0f338a334dc4d8933b31f596e9f6f0783bfc63e`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; AVAX candidate; no authorization object or active probe/order authority. | P0 bounded probe authorization remains blocked. Broad Demo API intent is not a repo-valid order/probe grant. |
| Fresh AVAX source | `/tmp/openclaw/candidate_source_freshness_alignment_20260626T102434Z/bounded_probe_lower_price_reroute_review_avax_sell_fresh_aligned_cap_mapped.json`, sha `bc300277...`, status `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`, `current_cap_usdt=10.0`. | Source freshness/alignment blocker is closed; do not use stale `_latest`. |
| Atomic no-order preview | `/tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/summary.json`, sha `98c7d75...`, status `ATOMIC_QUOTE_ADAPTER_PREVIEW_READY_NO_ORDER`; construction preview sha `f721bc3...`. | Evidence-only. It is not order admission, bounded-probe proof, Cost Gate proof, or promotion proof. |
| Public request audit | Exactly three unauthenticated public GETs: `/v5/market/time`, `/v5/market/tickers`, `/v5/market/instruments-info`; each HTTP `200`, retCode `0`, no auth/cookie/private/order path. | Exchange-facing runner action is complete; do not repeat without new E3/BB review and evidence delta. |
| Proof exclusions | Exclude unattributed fills, cleanup/risk-close fills, stale local `Working` rows, `flash_dip_buy`, cross-symbol controls, artifact counts, source-smoke, replay-only results, public quotes, adapter snapshots, and no-order previews. | These never count toward promotion or risk-adjusted net PnL proof. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Auth sha `61483e69...` has no authorization object; v574 no-order preview is ready but non-authorizing. | Pause. Resume only on real candidate-scoped auth object, exact typed confirm, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DEFERRED | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | No authorized probe outcomes; v574 preview is evidence-only. | Resume after probe outcomes or explicit source-only ledger-design request. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DEFERRED | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Learning output can become reviewable proposal only; no direct order/risk/live mutation. | Latest proposal remains review-only; no new post-probe evidence. | No action until new proposal or post-probe delta. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DEFERRED | PM -> E3 -> PM | Reconcile cron expected-head drift or API ownership only when runtime change is explicitly opened. | Runtime clean/source/service fact in §0. | No restart, crontab edit, env mutation, or writer enablement. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | AVAX Sell candidate selected; v574 construction preview ready no order. | Reopen only if fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Do not repeat source alignment or public quote runner without new source/runtime/artifact delta and E3/BB review for exchange-facing work. |
| Prior quote/adapter design/runtime reviews | DONE_WITH_CONCERNS | v570-v573 reports in `docs/CLAUDE_CHANGELOG.md` | Do not rerun quote capture/adapter/preview as a substitute for authorization or proof. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or exact typed confirm plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview | Public quote, adapter snapshot, and no-order construction preview are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T102434Z_candidate_source_freshness_alignment_no_capture.json
jq '{status,reason,request_count,statuses,answers}' /tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/summary.json
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py helper_scripts/research/tests/test_atomic_quote_adapter_preview_runner.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: pause now; resume P0 only on candidate-scoped authorization delta, otherwise do not repeat no-order quote/preview work.
