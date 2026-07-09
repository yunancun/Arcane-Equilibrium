# Stage 0R Replay Preflight Spec — `bb_breakout_oi_confirmed_5m`

**Date**: 2026-05-15
**Owner chain**: PM -> QC(default) -> MIT(default) -> PM
**Task shape**: read-only quant/data preflight design
**Target strategy label**: `bb_breakout_oi_confirmed_5m`
**Output authority**: Stage 0R may emit only `eligible_for_demo_canary=true|false`.

## 0. Boundary

This document is a replay packet spec, not an execution result.

No code, config, risk, engine, auth, paper, demo, live_demo, or live runtime change is authorized by this report. It does not enable `bb_breakout`, does not flip `enable_oi_signal`, does not launch a demo canary, and does not write `canary_stage_log`.

AI-E(default) is skipped because the requested packet has no model-routing, token-cost, or AI inference surface. PA/E1/E2/E4/QA are skipped because this is not an implementation or regression batch.

Current Stage 0R state remains **GATE-RED** from prior A4-C packets. Because this report only designs the replay contract and does not run it:

```text
eligible_for_demo_canary=false
```

## 1. Repo Facts Used

- `bb_breakout` now supports `signal_timeframe="5m"` and skips when 5m indicators are not warm; it must not silently fall back to 1m.
- `bb_breakout` declares `[ta_1m, ta_5m, oi_delta_panel]`.
- `bb_breakout` fail-closes before entry logic when the OI panel is missing, older than 15 minutes, missing the symbol, missing finite `oi_abs`, or missing finite `oi_delta_5m_pct`.
- `panel.oi_delta_panel` stores `snapshot_ts_ms`, `symbol`, `oi_abs`, `oi_delta_5m_pct`, `oi_delta_15m_pct`, `oi_delta_1h_pct`, and `source_tier`.
- The Rust OI aggregator writes `source_tier='bybit_v5_ws_open_interest'`. The SQL default `bybit_v5_public` is not eligibility-grade unless traced to a real writer in the report.
- The OI panel health sentinel is `[66] panel.* freshness`: PASS under 5 minutes, WARN 5-15 minutes, FAIL over 15 minutes.
- Runtime demo config currently has `signal_timeframe="5m"`, `donchian_mode="score"`, `min_persistence_ms=300000`, and keeps the OI score modifier conservative/off by default. This spec labels an offline OI-confirmed variant and does not mutate that runtime setting.
- Inference: same-direction OI expansion is the best current alternative alpha pathway to test because it may separate leverage-backed breakouts from TA-only band expansion; that inference still requires replay proof before demo exposure.

## 2. Signal Row Contract

Each replay row is one lookahead-free candidate at `(symbol, closed_5m_signal_bucket_ts_ms)` built from closed 5m bars plus the latest raw OI panel snapshot at or before the signal timestamp. The signal timestamp must be the closed 5m bar close, e.g. `COALESCE(close_ts_ms, open_ts_ms + 300000)`, not the still-forming candle or a post-signal observation.

Do not join through `panel.oi_delta_panel_5m` continuous aggregates for eligibility unless the aggregate bucket is proven fully closed before the signal bucket. The safer default is raw `panel.oi_delta_panel`:

```sql
latest panel row where symbol = row.symbol
and panel.snapshot_ts_ms <= closed_5m_signal_bucket_ts_ms
order by panel.snapshot_ts_ms desc
limit 1
```

Required row fields:

| Field | Meaning |
|---|---|
| `strategy_variant` | Constant `bb_breakout_oi_confirmed_5m` |
| `symbol` | Bybit linear symbol |
| `signal_bucket_ts_ms` | Closed 5m bar timestamp used for the decision label |
| `row_health` | `ok`, `missing_5m_ta`, `partial_5m_bar`, `oi_missing`, `oi_stale`, `cost_missing`, or `synthetic_excluded` |
| `bb_signal_dir` | `+1` long, `-1` short, `0` no signal |
| `bb_signal_reason` | squeeze -> expansion + volume + %B direction; include Donchian mode/result |
| `bb_squeeze_bw`, `bb_expansion_bw`, `bb_volume_ratio`, `bb_percent_b` | TA diagnostics from 5m bars |
| `donchian_state` | `score_boost`, `score_penalty`, `hard_pass`, `hard_block`, `off`, or `missing`; current demo config is `score`, so do not label Donchian as a hard blocker unless the replay packet explicitly changes config |
| `oi_snapshot_ts_ms`, `oi_age_ms`, `oi_source_tier` | OI provenance and freshness |
| `oi_delta_5m_pct` | Main OI delta magnitude, percent units |
| `oi_delta_sign` | `+1`, `-1`, or `0` after finite/nonzero check |
| `oi_abs_magnitude_pct` | `abs(oi_delta_5m_pct)` |
| `oi_magnitude_bin` | Predeclared bins, e.g. `(0,.05]`, `(.05,.10]`, `(.10,.25]`, `>.25` |
| `oi_alignment` | `confirm`, `diverge`, `flat`, or `missing` |
| `oi_confirmed` | `true` only when direction and OI sign align and magnitude clears the preregistered floor |
| `gross_fwd_5m_bps`, `gross_fwd_15m_bps`, `gross_fwd_30m_bps`, `gross_fwd_60m_bps` | Direction-adjusted forward returns |
| `primary_horizon` | One preregistered primary horizon before the run; default candidate is `15m` |
| `fee_bps`, `slippage_bps`, `net_primary_bps` | Cost model output for the primary horizon |
| `data_tier` | Must be real market/panel data, never synthetic-only |

Required row labels:

- `TA_ONLY_LONG`, `TA_ONLY_SHORT`, `TA_ONLY_NO_SIGNAL`
- `OI_CONF_LONG`, `OI_CONF_SHORT`
- `OI_DIVERGE_LONG`, `OI_DIVERGE_SHORT`
- `OI_FLAT`
- `OI_PANEL_UNAVAILABLE`

Primary label rule:

```text
bb_signal_dir != 0
AND oi_snapshot_ts_ms <= signal_bucket_ts_ms
AND oi_age_ms <= 300000
AND isfinite(oi_delta_5m_pct)
AND (
  (bb_signal_dir = +1 AND oi_delta_5m_pct > +oi_floor_pct)
  OR
  (bb_signal_dir = -1 AND oi_delta_5m_pct < -oi_floor_pct)
)
```

The OI floor must be preregistered before the replay run. If the configured runtime floor is `0.0`, the report must still show magnitude-bin sensitivity; eligibility cannot be based on a post-hoc best bin.

## 3. Report Contract

The generated Stage 0R report must include pooled and per-symbol sections for both:

1. `bb_breakout_oi_confirmed_5m`
2. TA-only `bb_breakout_5m` baseline on the same symbols, horizons, bar source, and cost model.

Required metrics:

| Metric | Required handling |
|---|---|
| `n` | Count of normal, finite `net_primary_bps` rows |
| `avg_net_bps` | Mean of `net_primary_bps` after fee/slippage |
| `t` | One-sample t-stat vs 0, sample stdev `ddof=1` |
| `PSR(0)` | Bailey-Lopez de Prado skew/kurt-aware PSR against 0 |
| `DSR` | Deflated Sharpe using explicit `K`; K must include symbols, horizons, OI floors/bins, and baseline variants actually reviewed |
| `bootstrap CI` | Block/stationary bootstrap 95% CI for mean net bps; lower bound must be reported |
| `per-symbol eligibility` | `true/false` per symbol with reasons |
| `PBO sanity` | CSCV or contiguous-block PBO; threshold and block count reported |
| `baseline comparison` | TA-only avg/t/PSR/DSR/CI plus OI-confirmed lift and lift CI |

Primary horizon: one preregistered value before the run. Recommended default is `15m` (`3` closed 5m bars); supporting horizons are `5m`, `30m`, and `60m`. If PM/QC chooses `30m` instead, that choice must be written into the packet before querying returns and counted in K/PBO.

Net return formula:

```text
net_primary_bps =
  direction_adjusted_forward_return_bps
  - entry_fee_bps
  - exit_fee_bps
  - entry_slippage_bps
  - exit_slippage_bps
```

## 4. Baseline Comparison

The baseline is not optional. It answers whether OI confirmation adds edge beyond the 5m TA breakout itself.

Baseline construction must include two slices:

| Baseline | Meaning |
|---|---|
| `TA_ONLY_ALL` | Every reconstructed TA-only 5m breakout row on the same symbol/window/horizon/cost model. This is a counterfactual baseline because current runtime `bb_breakout` also requires OI panel availability before entry logic. |
| `TA_ONLY_MATCHED` | The paired TA-only rows where a valid fresh OI panel row existed, before applying OI sign confirmation |

Eligibility should be judged against `TA_ONLY_MATCHED`; `TA_ONLY_ALL` is a context check for coverage/sample attrition.

Shared construction rules:

- Same symbol universe and window.
- Same 5m Bollinger squeeze/expansion/volume labels.
- Same forward-return horizons.
- Same fee/slippage assumptions.
- No OI alignment filter.
- OI fields may be joined for diagnostics, but cannot affect baseline membership.

The report must show:

| Comparison | Pass expectation |
|---|---|
| `avg_net_bps_oi_confirmed - avg_net_bps_ta_only` | Positive |
| Bootstrap CI of lift | Lower bound >= 0 for eligibility |
| `n_oi_confirmed / n_ta_only` | Enough retained sample; tiny cherry-picked subset fails |
| PBO with both variants in K | No high-PBO selection artifact |

If OI confirmation merely filters to a smaller, noisier subset without a robust lift over TA-only, `eligible_for_demo_canary=false`.

## 5. Data-Health Prerequisites

These are hard fail-closed prerequisites before the report may emit `eligible_for_demo_canary=true`.

| Prerequisite | Required result |
|---|---|
| OI freshness | Current `[66]` OI panel PASS, and row-level `oi_age_ms <= 300000` for eligible rows |
| OI availability | `panel.oi_delta_panel` present, non-empty, source tier real Bybit WS/REST, finite `oi_abs` and `oi_delta_5m_pct`; `bybit_v5_public` default rows require provenance proof before eligibility |
| 5m feature availability | `market.klines` 5m closed bars sufficient for BB, Donchian, volume, and forward horizons; no fallback to 1m |
| Lookahead safety | Indicator windows use only closed/current decision bar as runtime would; leak-free Donchian diagnostic is shown separately |
| Fee/slippage source | Preferred: same-symbol demo/live_demo realized fee/slippage with maker/taker role. AccountManager/default/q90 fallback may be diagnostic only and forces `eligible_for_demo_canary=false` unless QC explicitly waives |
| No synthetic-only rows | Exclude `synthetic_replay`/synthetic-only rows from eligibility and ML/training surfaces |
| Symbol coverage | Per-symbol report for every candidate symbol; no cherry-picked hidden exclusions |
| Replay immutability | Query/report is read-only: no INSERT/UPDATE/DDL, no paper enablement |

Rows with `oi_age_ms > 300000` are excluded from eligibility. Rows with `300000 < oi_age_ms <= 900000` may appear only in a diagnostic appendix; they cannot contribute to `n`, `avg_net_bps`, PSR, DSR, PBO, CI, or eligibility.

Recommended health section fields:

```text
oi_latest_snapshot_utc
oi_panel_age_seconds
oi_symbols_present / expected_symbols
signal_rows_with_finite_oi_pct
rows_excluded_missing_oi
rows_excluded_stale_oi
fee_source
slippage_source
synthetic_rows_seen
synthetic_rows_used_for_eligibility
```

## 6. Eligibility Gate

Stage 0R eligibility is per strategy x symbol. Pooled results are supporting evidence only.

Per-symbol `eligible_for_demo_canary=true` requires all of:

| Gate | Threshold |
|---|---|
| Data-health prerequisites | PASS |
| `n` | `>= 100` OI-confirmed rows |
| `avg_net_bps` | `>= +15.0` at the preregistered primary horizon |
| `t` | `> 2.0` |
| `PSR(0)` | `>= 0.95` |
| `DSR` | `>= 0.95` with explicit K |
| Bootstrap CI | 95% lower bound `> 0` |
| PBO sanity | `PBO <= 0.20` for eligibility. `0.20 < PBO <= 0.50` is diagnostic/weak only and still forces eligibility false. If underpowered, emit `PBO=defer_insufficient_power` and eligibility is false |
| Baseline lift | OI-confirmed lift over `TA_ONLY_MATCHED` has CI lower bound `>= 0` |
| Selection sanity | OI floor/horizon/symbol was preregistered, not chosen after seeing returns |

Report output must end with exactly one boolean:

```text
eligible_for_demo_canary=true
```

or

```text
eligible_for_demo_canary=false
```

No `Stage 1 PASS`, `auto_promote`, `promote_n2`, or stage transition language is allowed.

## 7. Suggested Packet Layout

1. Scope and read-only boundary.
2. Data-health table.
3. Signal-row counts: TA-only rows, OI-joined rows, OI-confirmed rows, excluded rows.
4. Pooled metrics for OI-confirmed.
5. Per-symbol eligibility table.
6. Baseline TA-only comparison table.
7. PBO / DSR K accounting.
8. Bootstrap CI and lift CI.
9. Final boolean only.

## 8. PM Verdict

This spec is suitable as the next Stage 0R replay packet design for the OI-confirmed 5m squeeze/expansion pathway.

Because no replay run was executed in this task and the current active Stage 0R state is still GATE-RED:

```text
eligible_for_demo_canary=false
```
