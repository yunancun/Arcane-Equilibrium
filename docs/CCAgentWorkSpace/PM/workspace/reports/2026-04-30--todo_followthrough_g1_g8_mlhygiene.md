# TODO Follow-through: G1-04 / G8-01 / ML Hygiene

Date: 2026-04-30
Owner: PM

## Scope

Operator asked to do all four suggested follow-through items:

1. Correct active documentation drift.
2. Run G1-04 fee/R:R as-of compute.
3. Close G8-01 cognitive adaptive e2e / coverage work.
4. Complete ML training data hygiene quantification and recurrence guard decision.

No trading, risk, strategy parameter, authorization, rebuild, or restart action was performed.

## Runtime / Doc Drift

At collection time, Mac and Linux were aligned to code-bearing runtime checkpoint `a9fce24`. The follow-through itself is documentation and read-only analysis only. Linux engine stayed alive:

| Process | PID |
|---|---:|
| Rust engine | 1529433 |
| API uvicorn | 1591455 |
| engine_watchdog | 3450754 |
| openclaw-gateway | 3973441 |

Latest watchdog: `engine_alive=true`, demo/live snapshots fresh, paper inactive by design.

Latest passive healthcheck at 2026-04-30 22:12 CEST returned SUMMARY WARN, not FAIL. Notable WARNs were `[4]`, `[11]`, `[27]`, `[33]`, `[38]`, and `[40]`; `[35]`, `[36]`, `[37]`, and `[39]` passed.

## G1-04 Fee / R:R Compute

Window A: post-G7-09 deploy from 2026-04-24 23:41 CEST to 2026-04-30 22:17 CEST, 5.942 days.

| Metric | Value |
|---|---:|
| Entry fills | 1933 |
| Maker-like | 508 / 1933 = 26.28% |
| Avg fee | 4.754 bps |
| Fee drop | 21.30% |
| Limit rows | 663 |
| PostOnly rows | 310 |

Window B: post-2026-04-29 12:27:53 CEST strategy reload, the more relevant current execution slice.

| Metric | Value |
|---|---:|
| Entry fills | 665 |
| Maker-like | 487 / 665 = 73.23% |
| Avg fee | 3.424 bps |
| Fee drop | 59.32% |
| Limit rows | 454 |
| PostOnly rows | 310 |

Post-reload by strategy:

| Strategy | n | Maker-like | Avg fee | Fee drop |
|---|---:|---:|---:|---:|
| grid_trading | 328 | 72.87% | 3.484 bps | 57.60% |
| ma_crossover | 289 | 78.89% | 3.177 bps | 66.37% |
| bb_breakout | 27 | 62.96% | 3.615 bps | 53.86% |
| funding_arb | 15 | 13.33% | 5.873 bps | -10.67% |
| bb_reversion | 4 | 0.00% | 5.500 bps | 0.00% |

Post-reload close R:R:

| Close key | n | Total PnL | Wins | Losses | R:R | PnL bps |
|---|---:|---:|---:|---:|---:|---:|
| grid_close_short | 129 | +2.9625 | 62 | 67 | 1.454 | +4.867 |
| ma_reverse_cross | 104 | -4.7912 | 39 | 65 | 1.076 | -9.424 |
| grid_close_long | 43 | +0.3254 | 20 | 23 | 1.381 | +2.190 |
| phys_lock_gate4_giveback | 37 | +0.9004 | 23 | 14 | 0.798 | +3.659 |
| ma_crossover | 15 | -0.6501 | 4 | 11 | 1.903 | -7.003 |
| grid_trading | 11 | -1.7397 | 6 | 5 | 0.299 | -34.229 |

PM verdict: Post-reload maker execution is now close to the G2-01 target, but the full 7d rolling window remains diluted by pre-reload samples. R:R is still not clean enough for promotion: grid close behavior improved in the short reload slice, while ma_reverse_cross remains net negative with a low win rate. Treat this as the operator-requested G1-04 as-of compute; G2-01 settlement remains time-driven around 2026-05-07/08.

## G8-01 Cognitive Adaptive Tests

Existing G8-01 W1/W2/W3 tests were verified:

- `test_cognitive_modulator_coverage.py`
- `test_strategist_cognitive_integration.py`
- `test_strategist_cognitive_w1_fix.py`

Result: `40 passed`.

Coverage note: local Python does not have `coverage.py`, so I used Python stdlib `trace` plus AST executable-statement accounting. `CognitiveModulator` covered 76/81 executable AST statements, 93.8%, above the >=85% target. `strategist_cognitive.py` covered 51/76 executable AST statements on the hot integration paths; regret/dream producer branches remain intentionally deferred by PA Option C because those producers are separate future work.

## ML Training Data Hygiene

Read-only SQL over `learning.exit_features`:

| Metric | Value |
|---|---:|
| Total rows | 1843 |
| Dust spiral noise rows | 37 |
| Noise ratio | 2.01% |
| Noise rows in last 24h | 0 |
| Noise rows in last 7d | 37 |

All 37 rows were confined to `demo/orphan_frozen/STRKUSDT` between 2026-04-26 07:37:59 and 2026-04-26 08:13:59 CEST.

Decision: no DB backfill is warranted because the all-time noise ratio is below the 5% threshold and 24h recurrence is zero. Existing healthchecks already cover recurrence:

- `[26] dust_spiral_noise_in_ef`: total + 24h delta in `learning.exit_features`.
- `[21] paper_state_dust_inventory`: runtime recurrence sentinel over demo/live/live_demo fills.

## Verification

- Local G8-01 pytest: 40 passed.
- Local stdlib trace + AST executable-statement coverage: `CognitiveModulator` 76/81 (93.8%).
- Linux watchdog: `engine_alive=true`.
- Linux passive healthcheck wrapper: SUMMARY WARN, exit 0.
- Linux DB read-only queries for G1-04 and ML hygiene completed successfully.
