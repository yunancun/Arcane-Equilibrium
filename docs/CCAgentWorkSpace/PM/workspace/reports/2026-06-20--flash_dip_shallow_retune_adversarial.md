# 2026-06-20 FlashDip Shallow Retune Adversarial Review

## Scope

PM-local adversarial pass after `shallow_retune_screen.py`.

Question: can the K4/K5/K6 N2/C3 shallow-retune candidates survive regime concentration, fixed-notional death stress, and DSR/PBO selection deflation?

Boundary: counterfactual research only. No live/demo parameter change, no engine/API restart, no rebuild, no order placement, no risk/auth/trading mutation, no PG write. Linux runs used `PGOPTIONS="-c default_transaction_read_only=on"` and wrote only `/tmp/openclaw/research/tail_dislocation_meanrev/*.json`.

## Artifacts

| Run | Artifact | Purpose |
|---|---|---|
| nf3 stress | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_adversarial_20260620T020302Z.json` | K4/K5/K6 N2/C3/nf3%, G1/G2/G3 adversarial review |
| nf0.5 stress | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_adversarial_20260620T020453Z.json` | same candidates at notional_frac 0.005 with selection grid 0.5%-5% |

Data: 26 symbols, 2020-03-25..2026-06-18, 2042 aligned days for G3 selection deflation. Selection grid: K2-K6, N1/N2/N3/N5, cap 1/3/5/unlimited, notional grid. PBO was 0.1349 with verdict `ROBUST` in both runs.

## Findings

The earlier N2/C3/nf3% candidates should not be implemented. They pass G1 and DSR/PBO, but fail death-stress sizing:

| Cell | Baseline annret | Baseline maxDD | Death 2% p95 maxDD | Death 3% p95 maxDD | Gate |
|---|---:|---:|---:|---:|---|
| K4 N2 C3 nf3 | 28.1% | 17.5% | 74.4% | 93.4% | blocked |
| K5 N2 C3 nf3 | 27.9% | 12.9% | 62.9% | 85.1% | blocked |
| K6 N2 C3 nf3 | 23.7% | 9.4% | 49.4% | 76.1% | blocked |

Reducing notional is the binding survival lever. At nf0.5%, K4 and K5 become conditional candidates but still fail death 3% p95. K6 survives the full adversarial gate:

| Cell | Baseline annret | Baseline maxDD | Death 2% p95 maxDD | Death 3% p95 maxDD | DSR effective/full | Gate |
|---|---:|---:|---:|---:|---|---|
| K4 N2 C3 nf0.5 | 4.25% | 3.15% | 21.3% | 35.3% | pass/pass | conditional |
| K5 N2 C3 nf0.5 | 4.22% | 2.26% | 14.1% | 27.2% | pass/pass | conditional |
| K6 N2 C3 nf0.5 | 3.64% | 1.62% | 11.0% | 20.0% | pass/pass | strong |

K6 N2/C3/nf0.5 also has low top-crash concentration: top-1 crash net-PnL share 12.36%, top-3 17.80%. It is the only survivor-first retune candidate from this pass.

Interpretation: the alpha is real enough to keep researching, but it is not a high-notional rescue. The system was not profitable because live K15 never touched; shallow K can create fills, but 3% sizing converts the edge into latent tail ruin. The viable next step is much smaller notional, not more aggression.

## Next Gate

Do not retune demo/live from PM-local evidence alone. Required next step remains formal QC/MIT/AI-E review, especially delisting bias and execution fill realism for shallower K. If approved, E1 should implement a flag-gated demo retune candidate around K6/N2/C3/nf0.5%, with explicit kill switches and no default-on behavior.
