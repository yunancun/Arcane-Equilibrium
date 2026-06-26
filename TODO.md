# Xuanheng TODO - Active Dispatch Queue

**Version** v570 | **Date** 2026-06-26
**Source/runtime pointer**: v570 capture used source HEAD `cce761ba43df2799e35368665d704c724c7a818b`; Linux runtime source remains `dd22810ee41c353c1d214d9a3217862d7b2bac74`; this TODO lives at current repo HEAD.
**Current posture**: `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` is `DONE_WITH_CONCERNS`. Operator requested pause after this round.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--public_quote_capture_runtime_review.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--public_quote_capture_runtime_review.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T09:12:05Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service active, MainPID `2218842`. | Runtime intentionally unchanged by v570. Do not sync/restart unless a separate runtime blocker is opened. |
| Bounded authorization | `2026-06-26T09:00:04Z`, sha `85c92d10f07f776ee70547bd3fa362856f3f447fcc52e8ac5dbf043d83ea7bda`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, decision `defer`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | P0 bounded probe authorization remains blocked/no-repeat. |
| Public quote capture | `/tmp/openclaw/public_quote_capture_runtime_review_20260626T092300Z/public_quote.json`, sha `4d46d88a3ccda4dc108fada2f5ba9b321f774cd5a199ec89d63d3a11c1883de2`, generated `2026-06-26T09:27:22Z`, status `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`. | Fresh quote evidence exists, but it is not profit proof, order admission, or authority. |
| AVAX quote fields | Bid/ask `6.212/6.213`; spread `1.609658bps`; effective BBO age `529.314ms` vs max `1000ms`; instrument `Trading`, tick `0.001`, qty step `0.1`, min notional `5.0`. | Useful for a future no-order quote-to-adapter freshness review only. |
| Reroute input | Local reroute input sha `fcd7f92563dcb1384f6a35f98b6c38cdc21e612c0920e7e3e618aedb5ac3390b`, generated `2026-06-24T17:32:23Z`, status `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`. | Acceptable as quote-capture identity input only; stale for downstream construction preview until separately reviewed. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, cross-symbol controls, and this public quote capture as promotion/profit proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T092300Z_public_quote_capture_runtime_review.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` |
| `blocker_goal` | Run PM->E3->BB review, then at most one public/read-only AVAX quote capture with no private/order/auth path, no runtime mutation, no order admission, and no authority. |
| `profit_relevance` | Fresh AVAX BBO/spread/instrument filters are needed before maker-first micro-tier economics can be reviewed after fees/slippage. |
| `previous_evidence_checked` | v569 no-capture packet, E3 verdict, BB verdict, auth latest no-authority artifact, stale local reroute input. |
| `new_evidence_delta_found` | One ready quote artifact: `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`, 3 public GETs, `retCode=0`, fresh BBO, no authority/proof/mutation answers. |
| `anti_repeat_decision` | `DONE_WITH_CONCERNS`; do not repeat capture on the same reviews/artifacts. |
| `next_blocker_id` | Paused. On resume use `P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER`, unless a real AVAX-scoped auth delta appears first. |
| `why_not_repeating_current_blocker` | The single allowed capture already ran; another capture would add market noise, not governance evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `grid_trading\|AVAXUSDT\|Sell`; PM reports in changelog v562-v570. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | Auth latest sha `85c92d10...`: AVAX-scoped, review-required, decision `defer`, no authority object/grant. | Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> BB -> PM | One public/read-only AVAX quote capture artifact; no private/order endpoint, no auth headers, no order/probe/live authority. | v570 report; capture sha `4d46d88a...`, status `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`. | No-repeat. |
| `P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER` | 1 | PAUSED | `OPERATOR_REQUESTED_PAUSE` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Convert reviewed quote evidence into adapter-backed no-order freshness/construction input without bypassing stale reroute-chain review; no order authority. | v570 quote capture plus stale reroute warning. | After operator resumes, open a new `session_loop_state`; do not use raw quote directly for order construction. |
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
| Quote capture | The v570 public quote artifact is evidence-only. It is not demo fill proof, not profit proof, not Cost Gate proof, not promotion proof, and not order admission. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action | Score |
|---|---|---|---|---|---|---|---|
| Quote-to-adapter freshness review | Fresh AVAX BBO can remove the stale-BBO blocker and make maker-first construction economics realistic. | No-order adapter-backed snapshot and construction freshness review from the captured quote. | Capture path/sha, bid/ask/size, instrument filters, adapter snapshot, construction math. | Candidate mismatch, stale quote, raw-quote construction bypass, or any order authority claim. | Source/read-only review only. | Open `P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER` after pause. | upside Medium-High; evidence Medium-High; realism Medium; cost critical; time Fast; account risk None; governance Low-Medium; autonomy High |
| Maker spread/cost skip calibration | Captured spread `1.609658bps` may leave enough cushion for a maker-first micro tier after fees/slippage. | Evaluate existing skip formula against captured spread and modeled edge cushion. | Spread, maker fee, slippage buffer, tier notional, edge cushion, cap. | After-cost cushion <= 0 or taker fallback required. | Analysis only. | Produce no-order cost-screen result. | upside Medium; evidence Medium; realism Medium; cost critical; time Fast; account risk None; governance Low; autonomy High |
| Demo-live applicability guard | Separating public quote evidence from future demo fills avoids false live-applicability conclusions. | Source-only contract that keeps quote evidence separate from actual demo fee/slippage/fill proof. | Capture environment, future fill lineage, actual fee/slippage, maker/taker labels. | Public quote counted as fill/profit/proof. | None for source contract; bounded auth needed for future fills. | Keep quote evidence-only in future proposal contracts. | upside Medium; evidence Medium; realism Medium; cost Medium; time Fast; account risk None; governance Low; autonomy High |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--public_quote_capture_runtime_review.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T092300Z_public_quote_capture_runtime_review.json
python3 -m json.tool /tmp/openclaw/public_quote_capture_runtime_review_20260626T092300Z/public_quote.json
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: pause now; on resume, real P0 auth delta takes precedence, otherwise open no-order quote-to-adapter freshness review.
