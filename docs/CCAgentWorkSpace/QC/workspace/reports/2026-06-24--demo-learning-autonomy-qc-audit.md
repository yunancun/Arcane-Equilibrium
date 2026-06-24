# 2026-06-24 -- Demo Learning Autonomy QC Audit

Bound role: `QC(default)`
Scope: alpha / strategy / profitability evidence and Cost Gate demo-learning quantitative status
Mode: read-only audit, except this requested report artifact

## Verdict

`DONE_WITH_CONCERNS`.

The system is not signal-silent: current runtime has strategy signals, Demo intents/orders/fills, Cost Gate false-negative candidates, sealed-horizon candidates, and a current-fee MM candidate. It is still not producing promotion-grade profit evidence: bounded Cost Gate probe/order authority is absent, sealed-horizon operator review is pending, MM lacks repeat/OOS confirmation, and bounded probe result review has `NO_PROBE_OUTCOMES_RECORDED`.

## FACT

- Requested PM context file was not present under canonical repo root `srv/` at:
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md`.
- A parent-workspace copy was present and read at
  `/Users/ncyu/Projects/TradeBot/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md`.
  It was treated as non-authoritative unless corroborated by `srv/` or runtime
  evidence; its task framing matched the audit questions and TODO v452 posture.
- Required repo/context files were read: `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `docs/agents/context-loading.md`, `TODO.md`, `.codex/agents/PM.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, `.codex/agents/QC.md`, `.claude/agents/QC.md`, `docs/CCAgentWorkSpace/QC/profile.md`, and `docs/CCAgentWorkSpace/QC/memory.md`.
- Runtime source direct read-only probe: Linux `/home/ncyu/BybitOpenClaw/srv` and local repo both report clean `main` at `c88deea7` (`Restore flash dip working orders into pending cap [skip ci]`).
- Latest alpha runtime artifact `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json` was generated `2026-06-24T01:00:04Z`, reports `git_status=SYNCED_CLEAN`, `source_ready=true`, and worklist status `LEARNING_WORK_AVAILABLE`.
- Demo-learning health artifact at `/tmp/openclaw/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_latest.json` reports `SOURCE_NOT_READY` from an expected-head mismatch, while also reporting stack installed, cron entries present, recent heartbeats/statuses, latest artifacts present, and false-negative packet present. This health artifact conflicts with the direct current git probe and should be treated as a stale or expected-head artifact concern, not proof that source is currently dirty.
- Read-only PG snapshot around `2026-06-24T01:04Z`:
  - last 24h: `39,395` signals, `33` intents, `35` orders, `5` fills, `56,600` decision outcomes.
  - last 48h: `96,568` signals, `36` intents, `38` orders, `5` fills, `114,200` decision outcomes.
- Last-24h strategy signal leaders include `ma_crossover|BTCUSDT` OpenShort `20,961`, `ma_crossover|BTCUSDT` OpenLong `11,569`, `ma_crossover|ETHUSDT` OpenLong `5,211`, plus many `grid_trading` symbols. Signals are therefore present.
- Last-24h Demo fills:
  - `XRPUSDT` flash_dip_buy maker Buy, fee `0.05732711`.
  - `XRPUSDT` risk/ma_crossover Sell close, realized PnL `-0.20664`, taker slippage `-37.1108bps`, fee `0.15753588`.
  - `SOLUSDT` and `ETHUSDT` unattributed Bybit-auto Buy fills.
  - `ETHUSDT` `risk_close:ipc_close_symbol` taker Sell, slippage `1.6194bps`, fee `0.15586825`.
- Cost Gate false-negative packet `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json`, generated `2026-06-24T00:29:46Z`:
  - status `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`.
  - `16` false-negative candidates, `0` edge-amplification candidates in the packet summary.
  - top candidates: `grid_trading|ATOMUSDT|Sell`, `grid_trading|AVAXUSDT|Sell`, `grid_trading|ICPUSDT|Sell`.
  - all authority/proof answers false: no global Cost Gate lowering, no probe authority, no order authority, no promotion evidence.
- Blocked-outcome review `/tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json`:
  - status `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`.
  - `43` side-cells, `16` review candidates, `2` edge-amplification-required side-cells.
  - top side-cell `grid_trading|ATOMUSDT|Sell`, wrongful-block score `150.1476`, net cost cushion `75.0738bps`.
  - `main_cost_gate_adjustment=NONE`, `order_authority=NOT_GRANTED`, `promotion_evidence=false`.
- Learning lane materialization artifacts:
  - reject materializer: `MATERIALIZED_REJECT_ROWS_PRESENT`, `38` materialized/appended reject rows in latest batch.
  - outcome refresh: `68` blocked-signal outcomes appended in latest batch, `0` probe outcomes.
  - health component reports accumulated blocked-signal outcome count `45,938`.
- Demo learning lane plan:
  - status `READY_FOR_DEMO_LEARNING_PROBE`.
  - `probe_candidate_count=2`, `selected_probe_candidate_count=2`.
  - `order_authority=NOT_GRANTED`, `main_cost_gate_adjustment=NONE`.
- Sealed horizon evidence:
  - leading sealed candidate `ma_crossover|BTCUSDT|Sell`, horizon `240m`.
  - sealed replay reports best avg net `31.8707bps`, best net-positive `81.94%`, sample count `13,819`.
  - horizon stability reports best avg net `108.1777bps` and best net-positive `54.05%`.
  - operator review artifact status `PENDING_OPERATOR_REVIEW`, decision `defer`, typed confirm expected `approve_sealed_horizon_preflight:ma_crossover|BTCUSDT|Sell:240`.
  - sealed preflight status `OPERATOR_REVIEW_REQUIRED`, blocking gate `operator_sealed_horizon_review_recorded`.
- Bounded authorization chain:
  - bounded operator authorization status `SEALED_HORIZON_PREFLIGHT_NOT_READY`, decision `defer`, blocking gate `sealed_horizon_preflight_ready`.
  - authority patch readiness status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`.
  - placement repair status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`.
  - no active probe/order authority and no promotion evidence.
- Touchability/execution artifacts:
  - latest order-to-fill/touchability artifact was generated before the newest fills and reports `33` reviewed no-fill PostOnly orders, `33` deep passive no-touch, `0` BBO-touched-without-fill, best-touch gaps roughly `987-1821bps`.
  - bounded result review status `NO_PROBE_OUTCOMES_RECORDED`.
  - bounded execution realism review status `NO_EXECUTION_REALISM_GAP_TO_REVIEW` because no completed probe outcomes exist.
- MM current-fee packet `/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.json`, generated `2026-06-24T01:00:04Z`:
  - status `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`.
  - top candidate `edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`, `n=43`, edge-before-fees `4.715bps`, round-trip fee `4.0bps`, net `0.715bps`.
  - `2` current-fee-positive candidates.
  - history valid windows `11`, current-fee sample-gated positive windows `1`, repeated positive key count `0`.
  - repeat window false, OOS/walk-forward false, maker execution realism not reached.
- Profitability scorecard `/tmp/openclaw/alpha_discovery_throughput/profitability_path_scorecard_latest.json`, generated `2026-06-24T01:00:04Z`:
  - status `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`.
  - primary blocker `PENDING_OPERATOR_REVIEW`.
  - next move `BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY`.
  - recommended action `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe`.
  - no global Cost Gate lowering, no order authority, no promotion evidence.

## INFERENCE

- Current strategy/alpha lanes are generating real candidate material, not only empty artifacts or worklist placeholders. Evidence includes PG signals/orders/fills, a `READY_FOR_DEMO_LEARNING_PROBE` plan, ranked false-negative side-cells, sealed-horizon candidates, and a current-fee MM candidate.
- The Cost Gate learning/profit lane is still no-authority. Candidate artifacts are review/proposal evidence, not execution permission.
- The statement "Demo is not ordering" is no longer true for general Demo runtime: recent Demo orders and fills exist. It remains true for the bounded Cost Gate learning probe lane: there are no authorized bounded probe orders and no completed probe outcomes.
- The primary non-ordering cause for the Cost Gate candidate lane is not signal absence. It is the combination of Cost Gate blocking, pending operator review, missing bounded operator authorization, and missing candidate-matched execution evidence.
- Touchability remains a live execution-quality blocker for the flash_dip order flow: the latest audit shows most reviewed orders were deep passive no-touch. The newer fills weaken the absolute "no fills" statement but do not prove the bounded candidate path is touchable.
- Latest realized Demo fills are not promotion proof. The only clearly attributed round-trip-like XRP sequence closed negative after fees/slippage, and the other fills are unattributed or risk/IPC closes rather than matched bounded-probe outcomes.
- The strongest profitability evidence is pre-trade/replay/blocked-outcome evidence, not realized promoted alpha:
  - false-negative Cost Gate candidates are promising but require operator review and bounded probe evidence.
  - sealed horizon `ma_crossover|BTCUSDT|Sell@240m` is quantitatively interesting but still pending operator review and preflight.
  - SOXLUSDT MM is a single-window current-fee positive lead, not repeated/OOS-confirmed.
- Product requirement judgment: the system now has a credible autonomous learning/evidence-preservation loop, but it has not yet demonstrated long-term sustainable autonomous profit generation. It is a learning system with promising candidates, not a profit-generating autonomous trading system.

## ASSUMPTION

- "Demo not ordering" is interpreted as referring to the Cost Gate demo-learning/probe lane, not every ordinary Demo strategy path. If the operator meant all Demo trading, current PG evidence contradicts that premise.
- Runtime JSON artifacts and PG SELECT snapshots are treated as authoritative for current quantitative state at their timestamps.
- Promotion proof requires candidate-matched, fill-backed, fee/slippage-aware, matched-control, OOS/repeatable evidence under current governance, not only blocked-outcome markouts or single-window fill-sim positives.

## Answers To Audit Questions

1. **Are alpha lanes generating candidates/proposals?**
   Yes. Signals and Demo order flow exist; Cost Gate false-negative candidates, sealed horizon candidates, probe plans, placement repair plans, and MM current-fee candidates exist. They are not merely worklist text. However, the actionable trading side is still artifact/proposal gated, not authorized execution.

2. **Why is Demo not ordering?**
   General Demo is ordering and has recent fills. The bounded Cost Gate learning lane is not ordering because bounded probe/order authority is absent, sealed-horizon operator review is pending, preflight is not ready, and candidate-matched execution evidence is missing. Cost Gate blocks are a source of candidate discovery, not the only blocker. Touchability remains an execution-quality blocker for current flash_dip-style passive orders.

3. **Latest profitability evidence.**
   False-negative path: `16` ranked candidates, top `grid_trading|ATOMUSDT|Sell`, net cushion `75.0738bps`, but no authority/proof.
   Current-fee MM path: SOXLUSDT top candidate net `0.715bps`, `n=43`, two current-fee-positive cells, but only one positive history window and no repeated/OOS confirmation.
   Sealed horizon path: `ma_crossover|BTCUSDT|Sell@240m` has sealed replay best avg net `31.8707bps` and best net-positive `81.94%`, but operator review is pending and preflight blocks.
   Fills/orders: recent Demo fills exist, but no bounded-probe outcomes; the attributed XRP close is negative. None of this is promotion proof.

4. **Product requirement judgment.**
   Current state partially satisfies autonomous learning/evolution: it preserves rejects, refreshes artifacts, ranks candidates, and surfaces blockers. It does not satisfy autonomous profit generation: no durable current-fee/OOS/repeated candidate is approved, no bounded probe has produced outcomes, no Cost Gate change is justified, and no promotion proof exists.

## QC Recommendation

`REVISE / CONTINUE_EVIDENCE_BUILD`, not promote.

Next quantitative gate should be narrow: operator review of the sealed-horizon candidate or ranked false-negative packet, followed only by bounded Demo probe authorization if the exact contract passes. Promotion remains blocked until candidate-matched fills, fee/slippage lineage, matched controls, repeated/OOS confirmation, and execution-realism review are all positive.
