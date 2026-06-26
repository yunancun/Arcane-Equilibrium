# Xuanheng TODO - Active Dispatch Queue

**Version** v548 | **Date** 2026-06-26
**Repo/runtime pointer**: Mac/origin `main` was clean at docs checkpoint `60bdbdb472374db674efb717b444f8813d9351fd` before this docs checkpoint. Linux runtime `trade-core` remains source-clean at runtime code checkpoint `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`.
**Current posture**: `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` is closed `DONE_WITH_CONCERNS`. AVAX remains champion/current P0 candidate; SUI/FIL are source-only controls; no regime proof or order/probe authority. Next source-only blocker is `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER`.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_feasible_low_price_filter_no_order.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene | `2026-06-26T04:34:19Z` hygiene packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility clean; all mutation/authority/proof answers false/NONE. | Hygiene false blockers are closed. This is not profit/probe proof and grants no authority. |
| Runtime source/services | Linux runtime source is clean at `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`; crontab expected-head pins match; user API/watchdog services were active/enabled in the hygiene report. | Do not repeat runtime sync, crontab alignment, or hygiene snapshot without new source/crontab/service/artifact delta. |
| False-negative scorecard | Runtime read-only evidence: scorecard sha `0d01ca3d...` is `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`; top row is cap-blocked ETH Buy. | Research signal only; not proof. ETH remains research-only under current cap. |
| ETH Buy cap feasibility | ETH construction preview sha `f4e36f14...` is `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`: current cap `10 USDT`, min executable notional `15.7105 USDT`, rounded qty `0`. | Do not raise cap now. No ETH probe/order path unless future QC/operator cap envelope + E3/BB/auth chain exists. |
| Cap-feasible filter | Cap screen sha `09627dcd...` has `8` current-cap-feasible rows. Clean-BBO/high-cushion filter keeps AVAX as champion; SUI/FIL as source-only controls; rejects ETC/APT for incomplete BBO and UNI/XRP/OP for thin cushion/hit-rate/sample/spread. | Use AVAX/SUI/FIL for source-only matched-control design. Do not change P0 candidate without reopening P0 selection. |
| AVAX bounded candidate | AVAX selection sha `909651b8...` remains `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`: `grid_trading|AVAXUSDT|Sell`, 60m, `73.5511bps`, `48/48` positive, current-cap feasible. | Remains the only current cap-feasible bounded Demo candidate, still blocked by valid scoped authorization. |
| Authorization | Latest authorization sha `c2854973...`, generated `2026-06-26T05:15:05Z`, remains `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`; no emitted auth object/probe/order authority. | Do not rerun bounded authorization without a real AVAX-scoped auth delta. |
| Regime evidence | Current scorecard/cap-screen artifacts contain no leak-free regime labels or markout buckets for the cap-feasible split. | Do not claim regime proof. A future regime split needs a separate data-design blocker. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results. | Never count these as bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T051422Z_cap_feasible_low_price_filter_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` |
| `blocker_goal` | Source-only split of current-cap-feasible false-negative rows by verifiable filter fields; produce one review-only proposal or rejection. |
| `profit_relevance` | Focuses future work on candidates likely to survive fees/slippage while staying inside the existing `10 USDT` cap. |
| `previous_evidence_checked` | `2026-06-26--eth_buy_cap_feasibility_no_order.md`; `2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md`; runtime scorecard/candidate-packet/cap-screen/auth artifacts. |
| `new_evidence_delta_required` | A non-repeated current-cap-feasible filter decision, not another ETH cap, P0 candidate-selection, or authorization audit. |
| `new_evidence_delta_found` | AVAX passes champion filter; SUI/FIL pass only as controls; no regime labels are present. |
| `anti_repeat_decision` | Distinct source-only blocker completed. Do not repeat without fresh scorecard/cap-screen/auth or real regime-label/outcome evidence. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` |
| `why_not_repeating_current_blocker` | Row set is filtered/classified; rerunning the same artifacts would not add evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE_WITH_CONCERNS | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED_BY_RUNTIME_AUTHORIZATION | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid authorization is admitted and E3/BB review passes. | Latest auth sha `c2854973...` is defer/review-only; no AVAX-scoped authority. | Resume only if valid AVAX-scoped auth appears; otherwise stay source-only. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` | 1 | DONE_WITH_CONCERNS | PM -> QC -> MIT -> PM | Source-only cap decision recorded; no cap mutation, no order/probe authority. | `2026-06-26--eth_buy_cap_feasibility_no_order.md`; ETH needs `15.7105 USDT` vs current `10 USDT` cap. | No-repeat unless fresh cap envelope, scorecard, construction, or authorization evidence changes. |
| `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` | 1 | DONE_WITH_CONCERNS | PM-local synthesis | One source-only filter proposal; no order/probe authority and no candidate replacement. | `2026-06-26--cap_feasible_low_price_filter_no_order.md`; AVAX champion, SUI/FIL controls. | No-repeat unless fresh scorecard/cap-screen/auth/regime evidence changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` | 1 | ACTIVE | PM -> QC/MIT if design affects candidate priority | Define a source-only matched-control evidence contract for AVAX champion vs SUI/FIL controls; no order/probe authority, no PG write, no runtime mutation. | v548 filter packet; current artifacts lack candidate-matched fills and regime labels. | Build the minimal no-order control design: fields, pass/fail criteria, required future evidence, and hard exclusions. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Durable learning SSOT selected. | `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DONE_WITH_CONCERNS / NO-OP_ALREADY_DONE | PM -> E3 -> PM | Runtime source/crontab/API hygiene closed without authority/proof contamination. | `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has helper; no exchange-facing use authorized here. | Carry into future exchange-inventory/reconciler blocker only if needed. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Authorization | Any move from review/defer to bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus fresh E3/BB review. |
| Runtime/order path | Any Bybit private/trading call, adapter/writer enablement, plan mutation, or order submission requires PM -> E3 -> BB -> PM. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the selected P0 candidate. SUI/FIL controls cannot become bounded candidates without reopening P0 selection. |
| Live/mainnet | Out of scope; no live/mainnet authority. |
| Runtime mutation | Source sync, crontab/env edits, service restart/rebuild/daemon-reload, and PG writes require a separate reviewed blocker. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.
- Exclude from proof: `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| AVAX champion with SUI/FIL matched controls | upside Medium-High; evidence Medium; realism Medium; cost Good for AVAX; time Fast source-only; account risk None; governance Low; autonomy High | Source-only matched-control design defining required future rows/fields/pass-fail criteria. | Research only; no order/probe authority. |
| AVAX near-touch bounded Demo after valid auth | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance Medium; autonomy High | After valid AVAX-scoped auth plus E3/BB: one capped post-only near-touch-or-skip attempt. | Structured bounded Demo authorization + E3/BB required. |
| Future regime split with point-in-time labels | upside Medium; evidence Low now; realism Unknown; cost Unknown; time Medium; account risk None; governance Low; autonomy High | Requirements packet for joining false-negative outcomes to leak-free regime labels; no regime claim from current artifacts. | Research/data design only; PG read needs separate reviewed runtime data step if used. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_feasible_low_price_filter_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T051422Z_cap_feasible_low_price_filter_no_order.json | sed -n '1,220p'
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
