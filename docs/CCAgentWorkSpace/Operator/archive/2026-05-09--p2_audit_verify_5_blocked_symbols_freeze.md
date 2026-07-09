# P2-AUDIT-VERIFY-5 Blocked Symbols Freeze

## Result

Closed source/test. I froze the current `blocked_symbols` lists so they cannot keep growing quietly after negative cells appear.

## What Changed

- Added `docs/governance_dev/strategy_blocked_symbols_freeze.json`.
- Added `tests/structure/test_strategy_blocked_symbols_freeze.py`.
- Added `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`.

The freeze covers:

- `grid_trading`: 17 symbols.
- `ma_crossover`: 4 symbols.

New blocked cells now require RFC + 7d counterfactual/rejected-outcome evidence + DSR/PBO or explicit QC waiver before source config mutation.

## Read-Only Runtime Finding

Recent 7d spot-check:

- `grid_trading/LABUSDT`: 51 fills, net `-9.7539 USDT`.
- `grid_trading/BILLUSDT`: 29 fills, net `-3.6751 USDT`.
- `ma_crossover/LABUSDT`: 16 fills, net `-18.2091 USDT`; 2772 blocked rejections but 0 decision-outcome labels.
- `ma_crossover/FARTCOINUSDT`: 13407 blocked rejections but 0 decision-outcome labels.

Conclusion: current blocks may be defensible as source freeze, but the system does not yet have true rejected-outcome counterfactual power for these rows. Further blocklist additions are now stopped until evidence exists.

No runtime change, DB write, rebuild, restart, or live auth mutation was performed.
