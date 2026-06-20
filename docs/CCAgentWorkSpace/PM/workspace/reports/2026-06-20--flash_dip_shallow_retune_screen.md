# 2026-06-20 FlashDip Shallow Retune Screen

## Scope

PM-local read-only research screen for the live FlashDip no-touch problem.

Question: if current K15 orders are too deep to touch, do K2-K6 merely fill more, or do any shallow K values survive historical edge, cost, tail, fixed-notional sizing, and walk-forward checks?

Boundary: research artifact only. No strategy parameter change, no engine/API restart, no rebuild, no order placement, no risk/auth/trading mutation, no PG write. Linux runs used `PGOPTIONS="-c default_transaction_read_only=on"` and wrote only `/tmp/openclaw/research/tail_dislocation_meanrev/*.json`.

## Artifacts

| Run | Artifact | Purpose |
|---|---|---|
| live identity | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_screen_20260620T015017Z.json` | K2-K6 + K10/K15 reference, N3/C3/nf3%, bootstrap 1000 |
| finalist confirm | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_screen_20260620T015040Z.json` | K5/K6 N3/C3/nf3%, bootstrap 5000 |
| hold sweep | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_screen_20260620T015132Z.json` | K2-K6, N1/N2/N3/N5, C3/nf3%, bootstrap 1000 |
| N2 confirm | `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_screen_20260620T015210Z.json` | K4/K5/K6 N2/C3/nf3%, bootstrap 5000 |

Data: 26 symbols, REST cache 26/26, 2020-03-25..2026-06-18, span 6.24 years. Runtime context embedded: current K15 touchability had 18 true orders, 0 touched, deepest runtime K with any touch K6.

## Findings

Current non-profitability/no-fill is no longer ambiguous: K15 live placement is too deep for the recent runtime window. The live touchability monitor observed K15/K12/K10/K8 all 0/18 touched; K6 had 1/18, K4/K5 2/18, K2 4/18.

Touchability alone is not enough, but the historical screen produced real candidates. Under the live identity N3/C3/nf3%, K5 and K6 passed full-history and two-sided walk-forward gates. K2-K4 had positive/significant returns but failed maxDD survival at N3.

The hold sweep moved the best candidate from N3 to N2. Top research cells:

| Cell | n kept / days | mean net | boot_t | CI95 | annret | maxDD | worst trade |
|---|---:|---:|---:|---|---:|---:|---:|
| K4 N2 C3 nf3 | 4001 / 1586 | 1.30% | 7.15 | [1.03%, 1.83%] | 28.1% | 17.5% | -44.0% |
| K5 N2 C3 nf3 | 3244 / 1347 | 1.59% | 6.84 | [1.22%, 2.14%] | 27.9% | 12.9% | -43.4% |
| K6 N2 C3 nf3 | 2519 / 1099 | 1.77% | 6.89 | [1.41%, 2.52%] | 23.7% | 9.4% | -42.8% |

5000-bootstrap confirmation on K4/K5/K6 N2 preserved the result: boot_t K4 6.96, K5 6.94, K6 7.08; walk-forward pass 3/3.

Risk read: crash-window mean is still negative for K4/K5/K6 N2, so this is not a "profits during crash" strategy. It is a shallow panic mean-reversion candidate whose all-window edge offsets crash-window loss under small fixed-notional and concurrency cap. K6 is the most survival-conservative; K4/K5 are higher-return but with materially higher crash-window and maxDD risk.

## Next Gate

Do not retune live/demo parameters from this PM-local artifact alone. Required next step is QC/MIT/AI-E review of K4/K5/K6 N2 C3 nf3 using the same artifact plus an adversarial pass on delisting bias, crash-regime concentration, DSR/PBO/selection deflation, and execution fill realism for shallower K. Only after that should E1 implement a flag-gated demo retune candidate.
