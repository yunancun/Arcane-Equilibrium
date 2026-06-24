# 2026-06-24 -- Demo-Learning Autonomy MIT Audit

STATUS: DONE_WITH_CONCERNS

Scope: `MIT(default)` read-only audit for demo-learning / Cost Gate learning data pipeline, PG evidence, artifacts, schema/data freshness. No code/runtime/PG writes were performed by this audit; the only write is this requested report artifact.

## Verdict

The system is now continuously refreshing a Cost Gate learning artifact loop from runtime PG rows and market markout proxies, but it is not yet proven as continuous autonomous backend learning with decision impact. The active Rust engine has `OPENCLAW_DEMO_LEARNING_LANE_WRITER=` empty, so the hot-path backend writer is disabled; current Cost Gate learning rows are JSONL/artifact materialization, not PG learning-table accumulation or fill-backed autonomous probe learning.

## FACT

- Required PM context file is missing on both Mac and Linux: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md`.
- Mac and `trade-core` source are clean at `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92`; SQL migrations are applied through V145 (`127/127 success`).
- Demo engine is alive; true live is not active (`OPENCLAW_ALLOW_MAINNET=0`).
- Four demo-learning stack cron entries are installed and firing: demo evidence, sealed preflight, Cost Gate learning lane, and stack healthcheck. Their installed expected-head env still points to `1b6173e3`, while current source is `c88deea7`.
- Persisted stack health latest JSON at `2026-06-24T00:32:01Z` reports `SOURCE_NOT_READY` because of expected-head mismatch. A manual read-only healthcheck against current `c88deea7` reports `EVIDENCE_STACK_ACTIVE`.
- `/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl` has `92,105` valid JSONL rows, from `2026-06-22T09:56:31Z` through `2026-06-24T00:29:45Z`: `46,167` `probe_admission_decision` and `45,938` `blocked_signal_outcome`.
- Latest blocked-outcome review is fresh (`2026-06-24T00:29:46Z`), status `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`, with `16` false-negative candidates. Top side-cell at audit time: `grid_trading|ATOMUSDT|Sell`, net cost cushion `75.0738bps`.
- Latest false-negative operator review is `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW`; `probe_authority_granted=false`, `order_authority_granted=false`, `global_cost_gate_lowering_recommended=false`.
- Latest bounded probe result review says `NO_PROBE_OUTCOMES_RECORDED`; execution-realism review therefore has no probe outcome gap to review.
- PG runtime rows are accumulating:
  - last 15m: `289` `learning.decision_features` and `289` `trading.risk_verdicts`, all Cost Gate rejects.
  - last 4h: `7,656` decision/risk rows; `7,623` Cost Gate rejects.
  - all-time: `learning.decision_features=14,451,486`, `trading.risk_verdicts=3,257,099`.
- Recent orders/fills are not Cost Gate probe proof. The 4h order/fill sample is mostly `flash_dip_buy`, `risk_close`, and unattributed Bybit rows.
- ML/DB maturity remains non-production: `learning.model_registry` has 3 shadow-only grid models trained `2026-04-23`, `promoted_at=NULL`; `learning.decision_shadow_exits=0`; `learning.edge_estimate_snapshots` last updated `2026-06-19T21:26:01+02`.
- No dedicated PG Cost Gate learning ledger/outcome/review tables were observed. Relevant PG ledger tables are either empty or not this loop (`learning.experiment_ledger=0`, `research.alpha_wealth_ledger=0`, `learning.strategy_trial_ledger=55,560`).

## INFERENCE

- Current learning is continuous at the artifact layer, not stale or one-off: cron status logs and JSONL ledger counts show repeated refreshes and new materialized rows.
- Current learning is not autonomous trading learning in the strong sense: it does not enable probe/order authority, does not lower Cost Gate, does not train/promote a model, and does not feed a fill-backed decision-impact consumer.
- The project's own `autonomous_learning_chain_contract_v1` currently says `AUTONOMOUS_LEARNING_CHAIN_ACTIONABLE`, but its policy is explicitly artifact-only: no DB, Bybit, order, probe, or runtime mutation authority.
- The main reliability blocker is evidence semantics, not absence of activity: the system is learning from blocked-signal markout proxies, while the proof gate still requires candidate-matched fill/fee/slippage, matched controls, and operator-approved bounded probe evidence.
- The stale expected-head in installed cron env can make official health artifacts disagree with direct source reality. That is a freshness/source-drift blocker for operator dashboards unless corrected.

## ASSUMPTION

- PG `trading.risk_verdicts` and `learning.decision_features` are the authoritative runtime reject/decision source rows for this audit.
- `/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl` is the authoritative Cost Gate learning ledger until a PG-backed learning ledger is introduced.
- `OPENCLAW_DEMO_LEARNING_LANE_WRITER=` empty means the Rust hot-path learning writer is disabled, because the Rust writer checks that process env var for `1`/`true`.

## Answers

1. Backend learning engine continuously learning?
   - Artifact loop: yes, continuously refreshing from runtime PG rows and market markout proxies.
   - Backend autonomous learning with decision impact: no. Rust learning writer is disabled, model registry is stale shadow-only, and there are no probe outcomes.

2. Demo-learning / Cost Gate crons installed and fresh?
   - Yes, the four cron entries are installed and heartbeats/status/latest JSON are fresh.
   - Concern: installed expected-head is stale (`1b6173e3` vs current `c88deea7`), so persisted stack health reports `SOURCE_NOT_READY` until cron env is reconciled.

3. PG decision/risk/reject rows and learning rows accumulating?
   - PG decision/risk/reject rows: yes, fresh and accumulating.
   - Cost Gate learning ledger/outcome/review: accumulating in JSONL/artifacts, not in PG tables.

4. Data freshness/source drift/schema blockers?
   - Missing required PM context report.
   - Cron expected-head drift.
   - `activation_preflight_latest.json` is stale inside sealed-preflight artifact context.
   - ML model registry and edge estimate snapshots are stale for production ML claims.
   - No PG schema migration blocker observed; V145 is applied successfully.

5. Minimum evidence to prove continuous autonomous learning is actually live:
   - Cron expected-head reconciled and persisted stack health latest reports `EVIDENCE_STACK_ACTIVE`.
   - Rust hot-path writer enabled or explicitly declared unnecessary, with process env and ledger rows proving source.
   - Monotonic ledger/outcome/review row deltas across at least two natural cron cycles, with duplicate/idempotency checks.
   - Candidate-matched bounded probe authorization, no global Cost Gate lowering, and actual Demo order/fill rows for the selected side-cell.
   - Fill/fee/slippage lineage plus matched blocked controls, reviewed by bounded result and execution-realism artifacts.
   - A runtime consumer that changes only the allowed next action/worklist or a bounded gate state, with no unauthorized order/probe/promotion authority.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-24--demo-learning-autonomy-mit-audit.md
