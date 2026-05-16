# W-AUDIT-8b Funding Skew Stage 0R Replay Packet Verdict

Date: 2026-05-16
Role: PA(default)
Status: RED / fail-closed
Scope: read-only Stage 0R replay packet for `funding_skew_directional.v0_2`

## Verdict

`eligible_for_demo_canary=false`.

This is a valid Stage 0R fail-closed result, not a demo canary approval and not a strategy implementation. No runtime config, risk config, strategy wiring, paper/demo/live cohort, DB schema, migration, auth, or production WS/runtime wiring was changed.

## Run Context

- Repo root: `/Users/ncyu/Projects/TradeBot/srv`
- Mac source at final PA write time: `main` at `197ca14d`; `trade-core` source used for the read-only replay run: `main` at `abaa4de7`
- Linux artifact: `trade-core:/tmp/openclaw/w_audit_8b_stage0r_20260516_pa.json`
- Run command shape: `OPENCLAW_DATABASE_URL=postgresql://trading_admin@localhost:5432/trading_ai OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 timeout 1200 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py --window-days 7 --format json --out /tmp/openclaw/w_audit_8b_stage0r_20260516_pa.json`
- Data window observed in panel metadata: funding snapshots from `2026-05-10T23:30:15.872Z` to `2026-05-16T16:49:14.925Z`, about 5.72 days inside the requested 7-day lookback.

## Contract Evidence

| Field | Evidence |
|---|---|
| Branch-separated hypotheses | `crowded_long_fade` and `crowded_short_squeeze` evaluated separately. Selected least-failed primary cell was `INJUSDT crowded_short_squeeze`; `crowded_long_fade` had `n=0` under that fixed parameter family. |
| K accounting | `K_prior=0` using strict funding-skew ledger filter; `K_new_actual=4050`; `K_new_min=4050`; `K_total=4050`. This satisfies `K_total >= K_prior + 4050`. |
| Primary/sensitivity horizons | K includes `25 symbols * 2 branches * 3 z * 3 percentile pairs * 3 OI thresholds * 3 horizons(15m/30m/60m) = 4050`; 30m remains the primary selection horizon. |
| Funding attribution | `funding_attribution_mode=excluded`. No positive funding income is counted. |
| Raw panel as-of joins | SQL uses `snapshot_ts_ms <= signal_ts_ms` lateral joins for funding and OI, with exact 15m/30m/60m forward close timestamps. |
| BB funding fields | `source_mode=ws_current`; all inferred funding intervals are `480` minutes; source-tier counts include `bybit_v5_ws_tickers` and `bybit_v5_ws_open_interest`. |
| Settlement handling | Eligibility uses `primary_excluding_settlement_window`; selected family had `primary_settlement_window_signals=0`, share `0.0`, adverse-drag sensitivity `0.0 bps`. |
| PBO / DSR | `DSR=0.0`; `PBO=0.5`; both fail the required floors (`DSR>=0.95`, `PBO<=0.20`). |

## Statistical Evidence

Selected least-failed primary cell:

- `candidate_key=INJUSDT|crowded_short_squeeze|z=1.5|p=0.85/0.15|oi=3|h=30`
- `n=7`, `n_eff=1`
- `avg_gross_bps=128.7802`, `avg_net_bps=116.7802`
- `PSR(0)=0.999755`, `DSR=0.0`
- `funding_cycles=2`
- `max_day_share=1.0`
- `max_funding_cycle_share=0.8571`
- 60m and 8h block bootstrap CIs are `null` because the selected sample is too small.

Eligibility fail reasons:

- `symbol n_eff < 100`
- `branch n_eff < 50`
- `pooled n_eff < 300`
- `funding cycles < 14`
- `single-day share > 25%`
- `single funding-cycle share > 25%`
- `DSR < 0.95`
- `PBO missing or > 0.20`
- `pooled 60m bootstrap lower bound <= 0`
- `pooled 8h bootstrap lower bound <= 0`
- `plateau check failed`

Baseline and cost:

- Pooled no-funding/OI baseline avg net: `-16.9149 bps`
- Stage0R minus baseline avg net: `+133.6951 bps` for the selected parameter family
- Conservative flat cost: `12.0 bps`
- Cost-edge ratio: `0.09318`
- Maker/taker split: unavailable in Stage 0R replay rows, explicitly reported as not available.

Plateau check:

- `plateau_passed=false`
- `reason=insufficient_adjacent_support`
- `neighbor_count=3`
- `passing_neighbor_count=0`

## Per-Symbol Breakdown

This table is for the selected fixed 30m primary parameter family, not a pooled grid-expanded duplicate count.

| Symbol | n | n_eff | Branch counts | Avg net bps | Funding cycles | Max day share | Max cycle share |
|---|---:|---:|---|---:|---:|---:|---:|
| INJUSDT | 7 | 1 | long 0 / short 7 | 116.7802 | 2 | 1.0000 | 0.8571 |
| ADAUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| APTUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| ARBUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| ATOMUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| AVAXUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| BCHUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| BTCUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| DOGEUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| DOTUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| ETCUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| ETHUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| FILUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| ICPUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| LINKUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| LTCUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| NEARUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| OPUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| POLUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| SOLUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| SUIUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| TONUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| TRXUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| UNIUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |
| XRPUSDT | 0 | 0 | long 0 / short 0 | n/a | 0 | 0.0000 | 0.0000 |

## PA Interpretation

The tooling satisfies the required read-only packet contract after the same-topic hardening already present on `origin/main`. No additional SQL/Python patch was needed in this session.

The empirical result is RED because the only least-failed diagnostic cell is a seven-signal INJUSDT crowded-short squeeze cluster concentrated in one day and two funding cycles. It fails sample size, branch support, pooled support, funding-cycle diversity, DSR, PBO, bootstrap, and plateau requirements. The baseline lift and cost-edge ratio are positive, but they are not sufficient to override the fail-closed gates.

No demo canary, paper cohort, W-3 cohort, strategy implementation, or runtime wiring should be opened from this packet.
