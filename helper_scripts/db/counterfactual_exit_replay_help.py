"""Help text for counterfactual_exit_replay.py."""

from __future__ import annotations

DESCRIPTION = """Counterfactual exit replay — "lock profit at peak - k × ATR" vs realised exit.
反事實退場回放 — 「peak - k × ATR 鎖利」對比實際退場 net PnL。

Read-only SELECT over `learning.exit_features`, grouped by
(engine_mode, strategy_name, symbol), with JSON output under
`$OPENCLAW_DATA_DIR/audit/`.

Key interpretation notes:
- Default v1 mode is Gate-4-only linear `giveback_atr_norm >= k`; use
  `--v2-parity` for the Rust v2 4-Gate fire decision.
- Default `--cost-model both` prints `fee_only` and `proxy`; the `proxy` model is
  retained as an arithmetic sanity check and is not the operator decision line.
- `--exclude-close-tag risk_close:%` defaults on to avoid double-counting rows
  already closed by the risk layer; pass `--include-close-tag` to opt in.
- `--split-window` buckets pre-T3 / T3-T4-vacuum / post-T4-pre-P013 /
  post-P013-clean; only post-P013 data is numerically sound for v2-parity
  decisions after the ATR-scale fix.

Counterfactual model:
  cf_gross_bps          = (peak_pnl_pct - k * atr_pct) * 100.0
  cost_fee_only_bps     = 2 * fee_bps_per_side
  cf_net_fee_only_bps   = cf_gross_bps - cost_fee_only_bps
  improvement           = cf_net_fee_only_bps - realized_net_bps

Exit codes:
  0 = report generated (table printed, JSON written)
  2 = DB connection/query error

READ-ONLY: pure SELECT. Safe on production DB. Dispatch via `ssh trade-core`.
"""
