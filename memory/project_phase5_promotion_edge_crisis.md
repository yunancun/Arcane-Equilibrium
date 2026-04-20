---
name: Phase 5 PAUSED — strategies broken, not fees (2026-04-12)
description: Post-PNL-FIX-1/2 reality — all 4 strategies gross-negative edge before fees; Phase 5 cost_gate/JS/DL work paused pending strategy redesign. FA-PHANTOM-1 fix removes ~20% contaminated fills but won't flip aggregate positive.
type: project
originSessionId: 9c75dfaf-58b4-49bb-bbde-4c0da0b4880f
---
**Decision (2026-04-12)**: Phase 5 cost_gate / JS / DL work is **paused**. The premise ("cost edge crisis, cut fees") was wrong — it was based on data contaminated by two bugs.

## What the data actually says

After PNL-FIX-1 (cross-symbol last_price bug, commit `2a422fa`) + PNL-FIX-2 (emit_close_fill fee=0.0) cleanup:

| Strategy | RT | Net | Gross edge bps | Net edge bps |
|---|---|---|---|---|
| bb_reversion | 62 | -$125 | -0.46 | -5.96 |
| ma_crossover | 148 | -$370 | -2.64 | -8.14 |
| grid_trading | 446 | -$2280 | -0.67 | -6.17 |
| bb_breakout | 0 | — | — | — |
| **TOTAL** | 656 | **-$2775** | — | — |

**Every active strategy is gross-negative before fees.** Tightening cost_gate just trades less at the same loss rate.

## How to apply

- **Don't** tune cost_gate or rerun JS on clean baseline expecting strategies to flip positive.
- **Don't** assume FA-PHANTOM-1 fix alone unpauses Phase 5 (it's ~20-40% of closes; remaining 60% is independently edge-negative — see `project_fa_phantom_bug.md`).
- **Don't** propose "block worst symbols" — every strategy is negative on its own average.
- **Do** treat next focus as **strategy redesign** (G-SR-1 / Strategist agent / new signal logic) before Phase 5 resumes.
- **Do** rerun per-strategy edge breakdown (TODO PNL-3) after 2 weeks clean paper post FA-PHANTOM-1 deploy — if gross flips positive, Phase 5 resumes; else redesign.
- **Do** keep `tick_pipeline.rs` `risk-close` diagnostic warn — canonical source for live close-reason debugging.

## Anchors

- Edge = pre-cost expected net PnL per trade in bps.
- "BTC/ETH + tech indicator + 0.055% fee structurally cannot profit" — new data confirms for current strategy zoo.
- Hand-roll edge tracker still rejected (70% overlap with Phase 5).

## Full detail

- Archived long-form: `docs/archive/2026-04-15--phase5_promotion_edge_crisis_full.md`
- Related: `memory/project_edge_data_isolation.md` (engine_mode-separated edge pipeline)
- Worklog: `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`
- TODO: PNL-1~4 entries
