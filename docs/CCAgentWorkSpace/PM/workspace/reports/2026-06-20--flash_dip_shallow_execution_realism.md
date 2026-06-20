# 2026-06-20 FlashDip Shallow Retune Execution-Realism Check

## Verdict

PM-local execution-realism result: **block the 2-day K6/N2/C3/nf0.5% demo-retune path**.

The v244 survivor-first candidate was not killed by simple no-touch. In the recent 1m data slice, touch/fill proxy is high. It is killed because the same K6/N2/C3/nf0.5% events have negative 2-day daily-exit fixed-notional return after realistic through-buffer filtering.

The useful follow-up is different: fee-adjusted intraday short exits show a separate, weak but positive research signal. That signal is **not promotion proof** and needs L1/orderbook replay plus formal QC/MIT/AI-E review before any E1 implementation.

## Scope And Boundary

- Source added: `helper_scripts/research/tail_dislocation_meanrev/shallow_retune_execution_realism.py`.
- Test extended: `helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py`.
- Read-only PG only, with `PGOPTIONS="-c default_transaction_read_only=on"` and `OPENCLAW_DATABASE_URL` read from the runtime secret file without printing it.
- No Bybit private/signed/trading call.
- No engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no credential/auth/risk/order/trading mutation.
- PM-local shortened chain used because no explicit subagent request was made. Formal quant chain `PM -> QC -> MIT -> AI-E -> PM` remains open.

## Feedback Loop

The artifact intersects the v244 K6/N2/C3/nf0.5% daily candidate with `market.klines` 1m rows and checks:

- whether the daily limit was only touched or moved through by 0/5/10/25/50 bps;
- fixed-notional daily-exit return on the filled proxy sample;
- post-fill 5/15/30/60/240 minute markout from the maker limit;
- fee-adjusted short-exit net return assuming maker entry plus taker exit.

Linux artifact:

- `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_execution_realism_20260620T022015Z.json`
- SHA256: `5d4206ab7c0666c62209a0e99950dee82d69725c3a778101166da05653d91f41`
- Version: `tail_dislocation_meanrev.shallow_retune_execution_realism.v0.2`

## Results

Daily candidate coverage:

- Full daily K6/N2/C3 candidate after cap: 2519 kept events from 2020-03-27 to 2026-06-18.
- 1m coverage: 2026-04-05 to 2026-06-18, 2,799,861 rows, 26 symbols.
- Candidate events with same-day 1m data: 70 events, 2.78% of full history.

Execution gate:

| Buffer | Filled | Days | Fill proxy rate | Daily-exit annret | MaxDD |
|---:|---:|---:|---:|---:|---:|
| 0 bps | 69 | 38 | 98.57% | -2.44% | 0.87% |
| 5 bps | 68 | 38 | 97.14% | -1.96% | 0.78% |
| 10 bps | 65 | 37 | 92.86% | -2.49% | 0.81% |
| 25 bps | 61 | 35 | 87.14% | -2.20% | 0.75% |
| 50 bps | 54 | 35 | 77.14% | -2.10% | 0.74% |

Configured gate buffer was 10 bps with minimum 30 fills and 20 days. Sample passes those thresholds, but daily-exit annualized return is negative, so verdict is:

`EXECUTION_REALISM_BLOCKED`, fail reason `gate_buffer_nonpositive_annret`.

Short-exit signal:

- Best research-only short exit: 0 bps buffer, 240m horizon, annret 1.71%, maxDD 0.033%, mean net taker 0.90%, positive 68.1%.
- 10 bps buffer, 240m horizon: annret 1.29%, maxDD 0.033%, mean net taker 0.73%, positive 66.2%.
- 0/5/10 bps buffers also have small positive 15/30/60m short-exit variants after maker-entry plus taker-exit fees.
- 50 bps buffer kills most fast horizons, but 240m remains positive in the recent slice.

## Interpretation

Hypothesis H1, "daily-low touch is too optimistic and real fills disappear," is not the main failure. Through-buffer fill proxy remains high through 10 bps.

Hypothesis H2, "post-fill adverse selection / wrong exit horizon eats the edge," is supported. The same events have positive short-horizon bounce but negative 2-day daily-exit fixed-notional return.

Hypothesis H3, "intraday sample is too small," remains a caveat for promotion. The configured gate has enough recent filled events to block the 2-day retune, but the full 2020-2026 history only has 2.78% 1m coverage. A live/demo parameter change still needs richer replay or ongoing capture.

## Decision

- Do not retune `flash_dip_buy` to K6/N2/C3/nf0.5% with the current 2-day exit.
- Preserve K6 shallow entry as a research object, but pivot the next experiment to intraday exits: 240m first, then 15/30/60m as secondary horizons.
- Next validation must use a replay that models L1/orderbook fill conditions, maker queue risk, timeout behavior, and day-clustered/selection-deflated robustness. The short-exit signal is a candidate direction, not authorization to deploy.

## Verification

Mac:

- `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev python3 -m py_compile helper_scripts/research/tail_dislocation_meanrev/shallow_retune_execution_realism.py helper_scripts/research/tail_dislocation_meanrev/shallow_retune_adversarial.py helper_scripts/research/tail_dislocation_meanrev/shallow_retune_screen.py`
- `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev python3 -m pytest -q helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py` -> 7 passed

Linux `trade-core`:

- selective helper/test sync only;
- py_compile passed;
- focused pytest passed -> 7 passed;
- read-only PG artifact generated at the path above.
