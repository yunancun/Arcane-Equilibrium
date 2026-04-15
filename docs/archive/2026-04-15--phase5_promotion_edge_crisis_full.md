---
name: Phase 5 reframed — strategies broken, not fees (2026-04-12, 2026-04-14 QC refine)
description: Post-PNL-FIX-1/2 cleanup truth — all 4 strategies negative gross edge before fees; Phase 5 cost_gate work was solving the wrong problem. 2026-04-14 update: FA-PHANTOM-1 is a contributor (20% of fills / 40% of closes) but NOT the primary cause — remaining 60% of closes are independently edge-negative
type: project
originSessionId: 2d1509fb-93b5-475b-bff7-1669864c86a8
---
**Decision (2026-04-12 — supersedes 2026-04-08 framing)**: Phase 5 cost_gate /
DL / James-Stein work is **paused**. The premise was wrong.

## What changed: data was lying

Two bugs hid the real strategy performance for weeks:

1. **PNL-FIX-1** (commit `2a422fa`, 2026-04-12) — `on_tick.rs` 5 close paths
   used `event.last_price` (one tick's symbol+price) for cross-symbol closes,
   inflating realized PnL by 1000–10000× whenever fast_track / risk_close /
   strategy_close fired across multiple symbols on one tick. The 2026-04-11
   18:51 fast_track event produced 8 fills all stamped at price=2301.205,
   creating $497K of fake balance from a $10K start.
2. **PNL-FIX-2** (commit pending, 2026-04-12) — `emit_close_fill` wrote
   `fee: 0.0` to `trading.fills` for every risk/strategy close, with a
   misleading "accrued separately" comment. `paper_state.close_position()`
   in fact charges no fee at all. Open path billed $648 across 742 fills;
   close path billed $0 across 653 fills. Real round-trip fee on the clean
   1395-fill paper baseline is ~$2483, **~4× the ledger value**.

After cleanup + PNL-FIX-2 wired:

| Strategy | Round trips | Gross PnL | Real RT fee | Net | Gross edge bps | Net edge bps |
|---|---|---|---|---|---|---|
| bb_reversion | 62 | -$9.71 | $115 | **-$125** | -0.46 | -5.96 |
| ma_crossover | 148 | -$119.88 | $250 | **-$370** | -2.64 | -8.14 |
| grid_trading | 446 | -$248.80 | $2032 | **-$2280** | -0.67 | -6.17 |
| bb_breakout | 0 | — | — | — | — | — (never closed) |
| **TOTAL** | 656 | **-$378** | **$2397** | **-$2775** | — | — |

**Every active strategy is gross-negative before fees.** The 2026-04-08 frame
("realized 2 bps vs fee 11 bps → cost edge crisis, cut fees") was based on
contaminated data. There is no positive alpha to preserve by tightening
cost_gate. Tightening cost_gate just trades less while losing the same
fraction per trade.

## Why Phase 5 work is paused, not killed

The cost_gate / James-Stein machinery itself is fine — it just needs a real
positive-edge strategy to be useful on. Currently:
- PH5-WIRE-0/1, DL-1/2, JS-1, 5-01~03 are all wired
- They estimate edge from `trading.fills.realized_pnl`
- That input was garbage from PNL-FIX-1 contamination + PNL-FIX-2 zero fees
- Re-running on clean data would just confirm "all cells are negative"

## FA-PHANTOM-1 re-framing (2026-04-14)

A third, unrelated bug was discovered on 2026-04-14: `on_tick.rs`
`margin_utilization_pct` treated `total_notional / balance` as margin util
without dividing by leverage, tripping fast_track 90% threshold every time
positions stacked to ~100% notional. **QC quantified the impact** over the
2026-04-14 17:00-20:30 paper window:

| Category | Count | Share |
|---|---|---|
| strategy_open (entries) | 263 | 50% |
| fast_track_close | 105 | 20% total / 40% of closes |
| strategy_close (TP/SL/exits) | 94 | 18% / 36% of closes |
| other_risk_close | 63 | 12% / 24% of closes |

**Conclusion: FA-PHANTOM-1 is a contributor, NOT the primary cause of Phase 5
edge crisis.** The other 60% of closes (strategy_close + other_risk_close)
happened at the strategies' own TP/SL/exit signals — the gross-negative edge
seen in the PNL-FIX-1/2 cleanup table above is independently real for those
samples. Fixing fast_track will remove ~20% of the contaminated fills but
will not flip aggregate gross edge positive on its own.

Full root cause + fix details in `memory/project_fa_phantom_bug.md`.

## How to apply

- **Don't** tune cost_gate parameters or rerun JS-1 on the clean baseline
  expecting it to flip strategies positive — it won't.
- **Don't** propose "let's just block the worst symbols" — every strategy is
  negative on its own average. Sub-cell rescue requires a real per-cell win
  that current data doesn't show.
- **Don't** assume the FA-PHANTOM-1 fix alone will unpause Phase 5. It
  cleans up 20-40% of the close sample but the remaining majority is
  independently edge-negative.
- **Do** treat the next focus as **strategy redesign** (G-SR-1 / Strategist
  agent / new signal logic) before Phase 5 work resumes.
- **Do** rerun the per-strategy edge breakdown (TODO PNL-3) after 2 weeks
  of clean paper data (post FA-PHANTOM-1 deploy) — if gross edge flips
  positive, Phase 5 resumes; if still negative, strategy redesign proceeds
  as planned.
- **Do** keep the diagnostic warn at `tick_pipeline.rs` `risk-close` site —
  it remains the canonical source for live close-reason debugging.

## What still holds from the old memory

- Edge concept anchor: edge = pre-cost expected net PnL per trade in bps.
- "BTC/ETH + technical indicator + 0.055% fee structurally cannot profit" —
  the new data confirms this for the current strategy zoo, not refutes it.
- Hand-roll realized-edge tracker is still rejected for the same reason
  (~70% overlap with Phase 5; would be thrown away).

## Edge data isolation (2026-04-13 update)

Analysis of paper vs demo PnL divergence (paper -118 USDT vs demo -2.78 USDT)
revealed a suspected degenerative feedback loop: `realized_edge_stats.py` used
`is_paper=TRUE` which mixed paper+demo fills — paper's 518 noisy Exploration-mode
trades dominated the sample, potentially dragging all 68 JS cells to -35.72 bps
(B=1.0 full pooling). Fix: edge data now computed per `engine_mode` — demo fills →
`edge_estimates.json` (production), paper fills → `edge_estimates_paper.json` (draft
strategy evaluation only). Poisoned production estimates cleared to cold-start.

See `memory/project_edge_data_isolation.md` for full details.

## Cross-references

- TODO.md: PNL-1 (this rewrite) / PNL-2 (fix shipped) / PNL-3 (data above) /
  PNL-4 (fast_track trigger root cause — observability added, log
  archaeology impossible)
- Worklog: `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`
- Code: `tick_pipeline/mod.rs` `emit_close_fill` (PNL-FIX-2),
  `tick_pipeline/on_tick.rs` `close_position_at_symbol_market` callers
  (PNL-FIX-1), `fast_track.rs` (price_drop / margin_util now real — FIX-04 wired PriceHistoryTracker.max_drop_pct() + paper_state notional)
- Edge isolation: `realized_edge_stats.py`, `james_stein_estimator.py`,
  `edge_estimates.rs`, `event_consumer/mod.rs`
