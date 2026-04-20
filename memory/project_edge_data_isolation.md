---
name: Edge data isolation — suspected degenerative feedback loop (2026-04-13)
description: Paper exploration fills likely polluted JS edge estimates via feedback loop; demo/paper edge now computed separately
type: project
originSessionId: 2e12b7ca-81a7-4ab8-9f6a-16bbf0d9ad39
---
**Discovery (2026-04-13)**: Paper vs Demo PnL gap analysis revealed a suspected
degenerative feedback loop in the edge estimation pipeline. The loop has been
broken by isolating edge data by engine_mode.

## The suspected problem

`realized_edge_stats.py` queried `is_paper = TRUE` which included both paper AND
demo fills indiscriminately. Paper's Exploration governance profile allowed all
trades (including negative-edge), producing 518 fills vs Demo's 40. These 518
mostly-losing paper fills dominated the JS edge estimates:

- All 68 cells collapsed to shrunk_bps = -35.72 (B=1.0 = full pooling)
- Paper fees alone: 77.38 USDT (65% of total paper loss)
- Demo separately: realized PnL +0.70 with only 3.48 in fees

The suspected loop: paper exploration → noisy negative fills → JS estimates all negative
→ cost_gate sees negative edge but Exploration allows anyway → more negative fills →
estimates get worse. Meanwhile Demo cost_gate (Validation profile) blocks on the same
poisoned estimates, potentially rejecting viable trades.

**Why:** This is described as "suspected" / "discovered problem" rather than proven
causation — the strategies may genuinely have negative edge regardless. But the data
pipeline design clearly allows paper noise to contaminate production estimates, which
is architecturally wrong regardless of the root cause of negative edge.

## The fix (2026-04-13)

1. `realized_edge_stats.py` — SQL changed from `is_paper=TRUE` to `engine_mode=%(engine_mode)s`,
   default changed from paper to `"demo"`
2. `james_stein_estimator.py` — mode-aware snapshot paths:
   - demo → `edge_estimates.json` (production, read by demo/live cost_gate + scanner)
   - paper → `edge_estimates_paper.json` (isolated, for draft strategy evaluation only)
3. Rust `EdgeEstimates::load_for_mode(base, mode)` — paper pipeline loads paper file,
   demo/live load production file
4. `event_consumer/mod.rs` — uses `pipeline_kind.db_mode()` to load correct edge file
5. Poisoned `edge_estimates.json` cleared to cold-start (empty)

## How to apply

- When running JS estimator, always specify `--mode demo` (default) for production estimates
- Paper edge data is useful for evaluating draft/experimental strategies, not for
  gating production trades
- If edge estimates are unexpectedly uniform (all cells same shrunk_bps, B=1.0),
  investigate whether one mode's noise is dominating the sample
- Demo needs to accumulate enough fills (currently only 40) before JS estimates
  become statistically meaningful — cold-start fallback is correct for now
