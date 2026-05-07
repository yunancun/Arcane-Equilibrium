# MAG-050 Guardian V2 Risk Metrics Model

Date: 2026-05-07
Status: DONE contract
Scope: AgentTodo M5 Guardian V2
Owner: QC / PM local synthesis

## Verdict

APPROVED as the implementation contract for MAG-051 and MAG-052.

Guardian V2 must stop relying on the legacy BTC/ETH-only correlation map in
`guardian_agent.py`. The next implementation wave should use a dynamic
correlation snapshot when available and an explicit safe fallback when it is
not available. Guardian must also consume per-strategy drawdown and loss-streak
metrics before approving new opens.

## Authority Boundary

Guardian owns risk verdicts, not trade intent generation.

Guardian may:

- reject a new open;
- modify size, leverage, stop, or cooldown inside P0/P1 bounds;
- pause new entries for a symbol or strategy;
- request reduce-only / PositionReview evidence when risk warrants review.

Guardian may not:

- choose a new symbol, direction, or strategy;
- create an order;
- bypass Decision Lease;
- convert scanner decay directly into a close order;
- treat missing correlation data as positive evidence.

Protective H0/P0/P1 reduce-only paths remain separate from tactical
StrategistDecision -> GuardianVerdict -> ExecutionPlan flow.

## Dynamic Correlation Inputs

`CorrelationSnapshot` is the implementation target:

| Field | Meaning | Required |
|---|---|---|
| `snapshot_id` | stable id for audit and replay | yes |
| `ts_ms` | snapshot timestamp | yes |
| `engine_mode` | paper/demo/live_demo/live lane | yes |
| `window_minutes` | rolling return window | yes |
| `min_points` | minimum aligned return observations | yes |
| `symbols` | symbols included in the matrix | yes |
| `pairwise_r` | `{symbol_a: {symbol_b: r}}`, symmetric, diagonal 1.0 | yes |
| `sample_counts` | aligned return sample count by pair | yes |
| `source` | `runtime_returns`, `portfolio_risk_control`, `scanner_beta_proxy`, or `safe_fallback` | yes |
| `staleness_ms` | age at review time | yes |
| `quality` | `full`, `partial`, or `insufficient` | yes |
| `evidence_refs` | DB rows, cache ids, or replay fixture ids | yes |

Primary source:

- rolling symbol returns from Rust runtime market data or an already maintained
  portfolio-risk return tracker.

Allowed fallback sources:

- Python `PortfolioRiskControl.compute_correlation_matrix()` when wired with
  current active symbols and recent returns;
- scanner `beta_proxy` / sector metadata as fallback evidence only, never as a
  hidden hard reject by itself;
- `safe_fallback` when no matrix is available.

Forbidden fallback:

- a static hardcoded BTC/ETH pair map as Guardian risk authority.

## Correlation Review

`CorrelationReviewInput`:

| Field | Meaning |
|---|---|
| `decision_id` / `intent_id` | lineage |
| `symbol` | proposed symbol |
| `direction` | proposed direction |
| `strategy` | proposed strategy |
| `open_positions` | current positions with symbol, side, size/notional |
| `snapshot` | `CorrelationSnapshot` |
| `max_pairwise_r` | hard pairwise threshold, default `0.70` |
| `soft_pairwise_r` | modification threshold, default `0.55` |

Review rules:

1. Same-symbol add is not a correlation conflict; normal concentration/size
   gates still apply.
2. Opposite-side exposure is not automatically safe; it is classified as hedge
   evidence and still carries a reason code.
3. Same-direction pairwise `r >= max_pairwise_r` with enough samples is a
   hard correlation reject for new opens.
4. Same-direction `soft_pairwise_r <= r < max_pairwise_r` is a P2
   modification candidate: reduce size/leverage or add cooldown, not reject by
   default.
5. Missing or stale matrix does not approve risk. With no sufficient matrix,
   Guardian returns a safe fallback result:
   - no active same-direction positions: allow correlation check to pass with
     `correlation_data_insufficient` reason recorded;
   - one or more same-direction positions: prefer P2 modification / size cap;
   - same sector plus scanner high beta/crowding: reject or pause only if
     another hard risk fact is present.

The selected verdict must persist:

- pair reviewed;
- `r`;
- sample count;
- threshold;
- source and quality;
- fallback reason if no matrix is available.

## Per-Strategy Drawdown Inputs

`StrategyRiskSnapshot` is the implementation target:

| Field | Meaning |
|---|---|
| `snapshot_id` | stable id |
| `ts_ms` | snapshot timestamp |
| `engine_mode` | paper/demo/live_demo/live |
| `strategy` | canonical strategy key |
| `symbol` | optional symbol slice |
| `regime` | optional regime slice |
| `lookback_trades` | rolling trade count |
| `lookback_ms` | rolling time window |
| `sample_count` | filled round trips used |
| `net_pnl_bps_sum` | realized net bps sum |
| `max_drawdown_bps` | rolling equity-curve max drawdown |
| `current_drawdown_bps` | drawdown from rolling peak |
| `consecutive_losses` | current loss streak |
| `loss_rate` | losses / sample count |
| `worst_trade_bps` | worst net trade |
| `quality` | `full`, `partial`, or `insufficient` |
| `evidence_refs` | fills, execution reports, attribution rows |

Primary source:

- durable execution reports / attribution rows with strategy, symbol, net PnL,
  fees/slippage, and decision lineage.

Allowed fallback:

- recent Guardian verdict history and strategy metrics cache may create a
  partial snapshot;
- missing samples create `quality=insufficient`, never a positive score.

## Drawdown Review

Default states:

| State | Suggested condition | Guardian effect |
|---|---|---|
| `ok` | enough samples, drawdown/loss streak below soft thresholds | no extra risk action |
| `watch` | partial data or mild deterioration | record reason, no size boost |
| `modify` | drawdown above soft threshold or loss streak active | reduce size/leverage, raise cooldown |
| `pause_new_entries` | severe strategy drawdown or repeated losses | reject new opens for strategy/symbol |
| `review_positions` | open positions in affected strategy while risk worsens | request PositionReview evidence, not direct close |

Suggested starting thresholds for implementation tests, not live tuning:

- `min_samples = 10`
- `soft_drawdown_bps = 150`
- `hard_drawdown_bps = 300`
- `soft_loss_streak = 3`
- `hard_loss_streak = 5`
- `loss_rate_warn = 0.60`

These are code defaults only until surfaced through real config. They must not
be presented as live-tuned profitable settings.

## GuardianVerdict Mapping

MAG-052 should extend Guardian output with P2 modifications:

| Risk input | Verdict |
|---|---|
| hard same-direction correlation breach | `rejected` |
| soft correlation breach | `modified` with size/leverage/cooldown |
| missing matrix plus existing same-direction exposure | `modified` safe fallback |
| strategy hard drawdown / hard loss streak | `rejected` for new opens, pause reason |
| strategy soft drawdown / soft loss streak | `modified` |
| open position risk deterioration | request `PositionReview`, no direct close |

Every result must carry reason codes that Strategist can consume in the next
cycle.

## Required MAG-051 Regression Targets

1. Non-BTC/ETH pair can be rejected when the dynamic matrix says correlation is
   high.
2. BTC/ETH static pair cannot be the only source of a rejection.
3. Missing matrix with no active same-direction positions records
   `correlation_data_insufficient` but does not become positive evidence.
4. Missing matrix with active same-direction exposure produces safe P2
   modification / size cap.
5. Opposite-side pair records hedge/correlation evidence and does not use the
   same hard reject path.

## Required MAG-052 Regression Targets

1. GuardianVerdict can represent P2 modification output without changing
   symbol/direction authority.
2. Per-strategy drawdown can reject or pause new opens with persisted reason.
3. Soft drawdown can modify size/leverage/stop/cooldown.
4. Open-position deterioration requests PositionReview rather than direct
   close.
5. Reason codes are available for later Strategist feedback.

## Rollout Notes

MAG-050 is docs/contract only. It does not apply migrations, enable runtime
config, modify live settings, or change Guardian runtime behavior.
