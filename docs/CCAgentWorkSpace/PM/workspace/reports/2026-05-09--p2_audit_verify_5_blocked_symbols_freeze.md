# P2-AUDIT-VERIFY-5 Blocked Symbols Freeze

## Scope

- Target: `grid_trading.blocked_symbols` and `per_strategy.ma_crossover.blocked_symbols`.
- Boundary: source/read-only only. No strategy config mutation, DB write, rebuild, restart, live auth change, or runtime reload.
- Reason: QC v2 found the blocklist process was still vulnerable to selection bias: negative cells were being added to `blocked_symbols`, then future samples disappeared.

## Source Fix

- Added frozen registry: `docs/governance_dev/strategy_blocked_symbols_freeze.json`.
- Added static guard: `tests/structure/test_strategy_blocked_symbols_freeze.py`.
- Added read-only audit helper: `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`.
- Current frozen cells:
  - `grid_trading`: 17 symbols.
  - `ma_crossover`: 4 symbols.

New blocked cells now require RFC + 7d counterfactual/rejected-outcome evidence + DSR/PBO or explicit QC waiver before source config mutation.

## Linux Read-Only Evidence

Command shape:

```bash
python3 helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py --days 7
```

Runtime DB spot-check used `trading.fills` and `trading.risk_verdicts` only with no writes. `learning.mlde_edge_training_rows` 7d all-cell scan was intentionally stopped because the table has no usable index for this ad hoc query and the read was too heavy for runtime.

| strategy | symbol | fills | entries | exits | net_pnl_usdt | rejected_n | rejected_outcome_n | evidence_power |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| grid_trading | LABUSDT | 51 | 51 | 0 | -9.7539 | 0 | 0 | realized_fill_only |
| grid_trading | BILLUSDT | 29 | 29 | 0 | -3.6751 | 0 | 0 | realized_fill_only |
| ma_crossover | LABUSDT | 16 | 16 | 0 | -18.2091 | 2772 | 0 | no_rejected_outcome_labels |
| ma_crossover | FARTCOINUSDT | 0 | 0 | 0 | 0.0000 | 13407 | 0 | no_rejected_outcome_labels |

All other frozen grid/MA cells had zero observed fills in the 7d spot-check window.

## Verdict

P2-AUDIT-VERIFY-5 is source/test closed: the list is frozen by static guard, and the audit helper makes future blocked-symbol changes evidence-producing instead of post-hoc.

Important residual: current rejected `blocked_symbols` rows have `decision_outcomes=0`, so the system cannot yet claim true future counterfactual PnL for those rejections. That is exactly why the freeze is needed; more source blocklist additions would deepen selection bias until rejected-outcome labeling or a reviewed replay path exists.
