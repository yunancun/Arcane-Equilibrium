# MAG-040 Strategist V2 Strategy Matching Model

Date: 2026-05-07
Status: DONE
Scope: AgentTodo M4 Strategist V2

## Verdict

APPROVED as the implementation contract for MAG-041/MAG-045.

Strategist V2 must choose among concrete strategy routes, not merely label
decisions as `strategist_ai` or `strategist_heuristic`. The canonical strategy
keys are:

- `ma_crossover`
- `grid_trading`
- `bb_reversion`
- `bb_breakout`
- `funding_arb`

Legacy aliases such as `funding_rate_arb` may be accepted at input boundaries
only if they are normalized to the canonical key before scoring or persistence.

## Authority Boundary

Strategist V2 owns tactical intent selection:

- action: `open`, `hold`, `reduce`, `close`, `no_action`
- concrete strategy key
- symbol and direction candidate
- thesis, invalidation, expected net edge, and portfolio impact

Strategist V2 does not own:

- Guardian veto/modification authority
- Decision Lease issuance
- final order style or submit timing
- Bybit execution
- live config mutation

Scanner evidence remains advisory. Scanner route rank can seed candidate
generation, but Strategist may select a lower-ranked route or `no_action` when
edge, risk, learning, or portfolio context says so.

## Input Contract

`StrategyMatchInput` should be assembled from typed evidence refs:

| Field | Source | Required |
|---|---|---|
| `match_id` | Strategist generated stable id | yes |
| `ts_ms` | Strategist clock | yes |
| `engine_mode` | caller context | yes |
| `symbol` | StrategySignal / OpportunityCandidate / PositionReview | yes |
| `candidate_routes` | scanner `strategy_judgments` plus explicit signal route | yes |
| `scanner_candidate_id` | OpportunityCandidate when present | no |
| `position_review_id` | PositionReview when present | no |
| `edge_cells` | `learning.edge_estimate_snapshots` / scanner route metadata | no |
| `execution_cost_bps` | scanner opportunity components / AccountManager prior | no |
| `market_regime` | scanner market judgment | no |
| `portfolio_context` | current exposure, overlap, correlation class | no |
| `guardian_feedback` | reject/modify stats by strategy-symbol | no |
| `analyst_insights` | AnalystInsight refs, fact/inference/hypothesis separated | no |
| `cognitive_context` | confidence floor / size ceiling if enabled | no |

Missing optional inputs must reduce confidence or produce `no_action`; they must
not be silently treated as positive evidence.

## Candidate Model

Each candidate route becomes a `StrategyCandidate`:

| Field | Meaning |
|---|---|
| `strategy` | canonical strategy key |
| `action` | proposed tactical action |
| `direction` | `long`, `short`, `close_long`, `close_short`, or `neutral` |
| `market_fit_score` | route compatibility from scanner/market judgment |
| `edge_lcb_bps` | realized or replay-calibrated lower confidence edge |
| `cost_bps` | expected fee/slippage/cost buffer |
| `net_edge_lcb_bps` | `edge_lcb_bps - cost_bps` when computable |
| `data_quality_score` | conservative data quality scalar |
| `learning_weight` | Analyst/TruthRegistry adjustment, bounded |
| `risk_acceptance_prior` | Guardian historical allow/modify/reject prior |
| `portfolio_fit_score` | exposure/correlation/capital compatibility |
| `confidence` | final bounded [0, 1] confidence |
| `reject_reasons` | explicit reasons if candidate is not selectable |

Default scoring for selectable candidates:

```text
match_score =
  0.25 * market_fit_score
+ 0.25 * edge_quality_score
+ 0.15 * net_cost_margin_score
+ 0.15 * portfolio_fit_score
+ 0.10 * data_quality_score
+ 0.05 * learning_weight
+ 0.05 * risk_acceptance_prior
```

All components are normalized to `[0, 1]`. If `edge_lcb_bps` is unknown, the
edge component is capped at exploration confidence and must be labeled
`edge_unproven`. If `net_edge_lcb_bps < 0`, the candidate is selectable only as
`no_action`, `hold`, or protective/tactical reduce/close review, not as a new
open.

## Strategy Fit Rules

| Strategy | Positive fit | Negative fit / reject |
|---|---|---|
| `grid_trading` | range-bound regime, enough intraday range, controlled directional efficiency, maker fill economics | one-way shock, strong trend, range too tight, maker economics below cost floor |
| `ma_crossover` | clean directional trend, ATR/SNR support, low chop, positive trend continuation evidence | range-bound chop, stale signal, low trend score, repeated whipsaw losses |
| `bb_reversion` | mean-reverting range, non-dominant trend, enough band width and round-trip room | strong trend, crowded shock, too little range, recent reversion failure pattern |
| `bb_breakout` | post-squeeze expansion, volume/turnover support, directional confirmation | no expansion, false-breakout pattern, low liquidity, excessive slippage risk |
| `funding_arb` | meaningful funding with controlled price drift and borrow/execution feasibility | directional momentum too high, funding too small, drift exceeds carry, symbol/policy blocked |

## Decision Output

MAG-041 should extend/persist `StrategistDecision` with at least:

- `decision_action`
- `selected_strategy`
- `selected_candidate_id`
- `candidate_scores`
- `expected_net_edge_bps`
- `portfolio_impact`
- `thesis`
- `invalidation`
- `confidence`
- `fact_refs`
- `inference_refs`
- `hypothesis_refs`

The output must be deterministic and auditable: every selected candidate and
every rejection reason must be reconstructable from `candidate_scores` and
`evidence_refs`.

## Fail-Closed Rules

Strategist V2 returns `no_action` when:

- no candidate has required lineage;
- evidence is stale or data quality is below the configured floor;
- every candidate has negative net LCB edge for a new open;
- the best candidate lacks a concrete strategy key;
- the model cannot normalize aliases to one of the canonical strategy keys;
- confidence is below the current cognitive floor;
- required position review evidence is missing for tactical close/reduce.

## Required Regression Targets

MAG-041 implementation tests must cover:

1. output strategy is one of the five canonical keys, never only
   `strategist_ai`/`strategist_heuristic`;
2. scanner top rank can lose to a lower-rank strategy when net edge or learning
   evidence is better;
3. negative net LCB blocks new open but still allows hold/reduce/close review;
4. alias `funding_rate_arb` normalizes to `funding_arb`;
5. missing evidence produces `no_action` with explicit reject reasons;
6. decision payload keeps fact/inference/hypothesis refs separated.

MAG-045 replay acceptance must prove the selected strategy is not equivalent to
raw scanner score sorting.
