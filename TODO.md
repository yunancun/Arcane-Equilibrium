# Xuanheng TODO - Active Dispatch Queue

**Version** v572 | **Date** 2026-06-26
**Source/runtime pointer**: v572 source design started from HEAD `8e7ac05287071d47329eb9ee4b5b9de4d43b94c4`; Linux runtime source remains `dd22810ee41c353c1d214d9a3217862d7b2bac74`; this TODO lives at current repo HEAD.
**Current posture**: `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE` is `DONE_WITH_CONCERNS`; next step is runtime/exchange-facing review before any future capture.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--atomic_quote_adapter_preview_design_no_capture.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--atomic_quote_adapter_preview_design_no_capture.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T09:33:47Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service active, MainPID `2218842`. | Runtime intentionally unchanged by v571. Do not sync/restart unless a separate runtime blocker is opened. |
| Bounded authorization | `2026-06-26T09:30:48Z`, sha `1d12302a32d9bcadec8245abd4ebd54a8daa88b468a568342ed6493ef115bc6c`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, decision `defer`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | Artifact changed, but no usable authorization delta. P0 bounded probe authorization remains blocked/no-repeat. |
| Public quote capture | `/tmp/openclaw/public_quote_capture_runtime_review_20260626T092300Z/public_quote.json`, sha `4d46d88a3ccda4dc108fada2f5ba9b321f774cd5a199ec89d63d3a11c1883de2`, generated `2026-06-26T09:27:22Z`, status `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`. | Quote was fresh at capture, but is now stale for adapter generation. |
| AVAX quote fields | Bid/ask `6.212/6.213`; spread `1.609658bps`; effective BBO age `529.314ms` vs max `1000ms`; instrument `Trading`, tick `0.001`, qty step `0.1`, min notional `5.0`. | Historical quote evidence only; not reusable for current adapter/construction because the adapter generation window expired. |
| Reroute input | Local reroute input sha `fcd7f92563dcb1384f6a35f98b6c38cdc21e612c0920e7e3e618aedb5ac3390b`, generated `2026-06-24T17:32:23Z`, status `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`. | Acceptable as quote-capture identity input only; stale for downstream construction preview until separately reviewed. |
| Adapter attempt | Existing adapter rejected v570 quote with `public_quote_stale_at_adapter_generation`; no market snapshot or construction preview emitted. | Correct fail-closed result. Do not retry with generated-at override or lower freshness gate. |
| Atomic design smoke | `/tmp/openclaw/atomic_quote_adapter_preview_design_smoke_20260626T094000Z/atomic_design.json`, sha `fda084c17a5345a272617eda9fd88064a10ec4f1b5d3853176e20ce42635099d`, status `ATOMIC_QUOTE_ADAPTER_PREVIEW_DESIGN_READY_NO_CAPTURE_NO_AUTHORITY`; E2/E4 final verification `2026-06-26T09:40Z`: focused `10 passed`, adjacent quote/adapter/construction `73 passed`, `py_compile`, JSON parse, `git diff --check`. | Source-only design is ready; it does not authorize capture/order and must go through PM->E3->BB before runtime use. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, cross-symbol controls, and public quote/adapter artifacts as promotion/profit proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T094000Z_atomic_quote_adapter_preview_design_no_capture.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE` |
| `blocker_goal` | Create a source-only no-capture design packet for a future reviewed atomic public quote capture -> adapter market snapshot -> no-order construction preview flow. |
| `profit_relevance` | Future AVAX profitability review needs fresh BBO to survive adapter and construction gates; delayed quote reuse is not viable. |
| `previous_evidence_checked` | v571 stale adapter failure, v569 reviewed no-capture packet, runtime auth no-authority artifact, existing capture/adapter/construction helpers. |
| `new_evidence_delta_found` | New source helper and smoke `ATOMIC_QUOTE_ADAPTER_PREVIEW_DESIGN_READY_NO_CAPTURE_NO_AUTHORITY`; no runtime capture or authority. |
| `anti_repeat_decision` | `DONE_WITH_CONCERNS`; do not repeat source-only design on the same evidence. |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-RUNTIME-REVIEW`, unless a real AVAX-scoped auth delta appears first. |
| `why_not_repeating_current_blocker` | Design packet exists, is smoke-tested, E2-hardened against authority/path/stale-evidence bypasses, and adjacent-tested. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `grid_trading\|AVAXUSDT\|Sell`; PM reports in changelog v562-v570. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | Auth latest sha `1d12302a...`: AVAX-scoped, review-required, decision `defer`, no authority object/grant. | Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> BB -> PM | One public/read-only AVAX quote capture artifact; no private/order endpoint, no auth headers, no order/probe/live authority. | v570 report; capture sha `4d46d88a...`, status `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`. | No-repeat. |
| `P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Use existing adapter to verify whether v570 quote can still become no-order market snapshot without stale quote reuse. | v571 report; adapter failed closed with `public_quote_stale_at_adapter_generation`. | No-repeat. |
| `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Design a no-capture, no-authority packet for a future single reviewed flow that captures public quote and immediately emits adapter snapshot + no-order construction preview. | v572 report; smoke sha `fda084c1...`, status `ATOMIC_QUOTE_ADAPTER_PREVIEW_DESIGN_READY_NO_CAPTURE_NO_AUTHORITY`; E2/E4 `10/73` tests passed. | No-repeat. |
| `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-RUNTIME-REVIEW` | 1 | READY | `READY_RUNTIME_REVIEW` | PM -> E3 -> BB -> PM | Review and, only if gates pass, run exactly one future atomic public quote capture plus immediate local adapter and no-order construction preview; no private/order endpoint, no auth headers, no order/probe/live authority. | v572 design packet; v571 stale delayed adapter failure. | Open a new `session_loop_state`; verify no P0 auth delta first; then run PM->E3->BB review before any capture. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DEFERRED | `WAITING_FOR_PROBE_EVIDENCE_OR_LEDGER_DECISION` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | No authorized probe outcomes yet. | Resume after bounded probe authorization/outcomes or explicit ledger-design request. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DEFERRED | `REVIEW_ONLY_CONTRACT_EXISTS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | Autonomous proposal latest sha `abe948aa...`, status `REVIEWABLE_PARAMETER_PROPOSAL_READY`. | No action until new proposal delta or post-probe evidence. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DEFERRED | `NO_ACTIVE_RUNTIME_CHANGE_REQUEST` | PM -> E3 -> PM | Reconcile cron expected-head drift and API process/service ownership only when runtime change is explicitly opened. | Runtime source/service fact in §0. | No restart, crontab edit, service mutation, or writer enablement. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter | Public quote and adapter artifacts are evidence-only. Stale quote reuse is forbidden; raw quote must never feed construction directly; adapter failure is not profit proof or order admission. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action | Score |
|---|---|---|---|---|---|---|---|
| Atomic quote->adapter->preview runtime review | The stale failure shows capture and adapter/preview must be one bounded flow to preserve freshness without lowering gates. | PM->E3->BB-reviewed one-shot public capture followed immediately by local adapter and no-order preview. | v572 design packet, endpoint envelope, fresh quote artifact, adapter snapshot, construction preview, path+sha lineage. | Private/auth/order endpoint, second capture on old review, stale BBO, generated-at override, raw quote construction, or authority claim. | E3/BB before capture; no order authority. | Open `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-RUNTIME-REVIEW`. | upside High; evidence Medium-High; realism High if ready; cost critical; time Fast-Medium; account risk None; governance Medium; autonomy High |
| Maker spread/cost screen after atomic preview | Future atomic preview can evaluate whether AVAX remains viable for post-only maker tier after fees/slippage. | Use future adapter-backed construction preview to compute skip/edge cushion, still no order. | Fresh spread, maker fee, slippage buffer, tier notional, current cap, construction limit/qty. | After-cost cushion <= 0 or taker/crossing placement required. | Analysis only after future no-order preview. | Keep as follow-on after atomic design. | upside Medium; evidence Medium; realism Medium; cost critical; time Medium; account risk None; governance Low; autonomy High |
| Stale-quote reuse guard | Blocking stale quote reuse avoids false profitability proof and keeps future autonomous learning live-applicable. | Preserve adapter failure in TODO/report; add no code unless a future stale-bypass appears. | Adapter failure reason, freshness gate, quote timestamp, report/TODO pointer. | Future proposal counts stale quote as construction/proof evidence. | None. | Keep no-repeat/fail-closed status explicit. | upside Medium; evidence High; realism High; cost Low; time Fast; account risk None; governance Low; autonomy High |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--atomic_quote_adapter_preview_design_no_capture.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T094000Z_atomic_quote_adapter_preview_design_no_capture.json
python3 -m json.tool /tmp/openclaw/atomic_quote_adapter_preview_design_smoke_20260626T094000Z/atomic_design.json
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_atomic_quote_adapter_preview_design.py helper_scripts/research/tests/test_cost_gate_reviewed_public_quote_capture_packet.py helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: real P0 auth delta takes precedence; otherwise open atomic quote->adapter->preview runtime review with PM->E3->BB.
