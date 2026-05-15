# 2026-05-15 - Stage 0R OI-confirmed 5m Feasibility Probe

## Scope

Read-only feasibility probe for the `bb_breakout_oi_confirmed_5m` Stage 0R
packet. This is not a full eligibility report and does not emit an eligibility
upgrade.

Boundary: no rebuild, restart, paper enablement, demo canary launch, runtime
config change, live auth mutation, DB write, migration, strategy/risk change, or
source-code change was performed.

## Inputs

Spec basis:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_preflight.md`
- Runtime demo `bb_breakout` params from `settings/strategy_params_demo.toml`:
  `signal_timeframe="5m"`, `squeeze_bw=0.02`, `expansion_bw=0.04`,
  `volume_threshold=1.5`, `min_persistence_ms=300000`,
  `donchian_mode="score"`, `enable_oi_signal=false`.

Data-health facts from `trade-core` read-only SQL:

| Surface | Result |
|---|---:|
| `panel.oi_delta_panel` 7d rows | 166,921 |
| OI symbols | 25 |
| OI source tier | `bybit_v5_ws_open_interest` |
| OI latest snapshot | `2026-05-15 16:57:42.933 UTC` |
| OI latest age at probe | 24.9s |
| OI first 7d snapshot | `2026-05-10 23:30:15.872 UTC` |
| `market.klines` 5m rows, 7d | 52,005 |
| 5m kline symbols | 63 |
| 5m latest bar | `2026-05-15 16:55:00 UTC` |

## Probe Method

This probe reconstructed a rough runtime-style 5m breakout candidate set from
closed `market.klines` 5m bars:

- Bollinger(20, 2) from closed 5m closes.
- Volume ratio as current volume over previous 20 closed 5m bars.
- Squeeze memory proxy: prior `bandwidth < squeeze_bw` within 45 minutes.
- Breakout direction: `bandwidth > expansion_bw`, `volume_ratio >= threshold`,
  and `%B > 1` for long or `%B < 0` for short.
- OI join: latest raw `panel.oi_delta_panel` row at or before signal timestamp.
- Fresh OI: `oi_age_ms <= 300000`.
- OI-confirmed: breakout direction and `oi_delta_5m_pct` sign aligned.
- Forward return: direction-adjusted gross 15m/30m/60m bps.

Limitations:

- This is not the full Stage 0R report contract.
- It does not compute fee/slippage net return, PSR, DSR, PBO, bootstrap CI, or
  baseline lift CI.
- The `persistence_proxy_n` count uses a conservative previous-5m same-direction
  proxy; runtime intrabar persistence can differ.
- Results are diagnostic only and cannot authorize demo canary.

## Runtime-strict Result

Runtime-strict means `squeeze_bw=0.02`, `expansion_bw=0.04`,
`volume_threshold=1.5`, prior squeeze required, fresh OI required, and OI sign
alignment for the OI-confirmed slice.

| Scope | TA triple rows | Fresh OI rows | OI-confirmed rows | Persistence proxy rows | TA avg gross 15m bps | OI avg gross 15m bps | OI avg gross 30m bps | OI avg gross 60m bps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 23 | 16 | 9 | 5 | +20.8829 | -33.6345 | -11.4065 | -57.3574 |

Per-symbol OI-confirmed rows were all far below the Stage 0R `n >= 100`
eligibility floor:

| Symbol | OI-confirmed rows | OI avg gross 15m bps |
|---|---:|---:|
| APTUSDT | 1 | +9.6660 |
| ATOMUSDT | 1 | +40.9859 |
| FILUSDT | 2 | -95.0122 |
| ICPUSDT | 1 | -32.8059 |
| INJUSDT | 2 | -46.4602 |
| POLUSDT | 1 | -112.6604 |
| TONUSDT | 1 | +75.0488 |

## Fixed Diagnostic Sensitivity

These fixed probes are diagnostic only. They are not post-hoc eligibility
selection and must not be used to request a canary.

| Variant | TA rows | Fresh OI rows | OI-confirmed rows | TA avg gross 15m bps | OI avg gross 15m bps |
|---|---:|---:|---:|---:|---:|
| runtime strict | 23 | 16 | 9 | +20.8829 | -33.6345 |
| strict without prior squeeze | 52 | 27 | 12 | +12.6211 | -45.2030 |
| volume threshold 1.2 | 24 | 17 | 9 | +19.1460 | -33.6345 |
| expansion 0.03 + volume 1.2 | 69 | 55 | 23 | +0.8335 | -18.9629 |
| squeeze 0.03 + expansion 0.04 + volume 1.2 | 38 | 22 | 9 | +30.4636 | -33.6345 |

## Verdict

`bb_breakout_oi_confirmed_5m` is not ready for a full eligibility report from
the current 7d data window.

Reasons:

- Sample is underpowered by orders of magnitude: runtime-strict OI-confirmed
  pooled `n=9`; every per-symbol `n` is far below `100`.
- OI confirmation did not improve the rough 15m forward-return slice; pooled OI
  gross 15m was `-33.6345 bps`.
- Even fixed diagnostic loosening to `expansion=0.03` and `volume=1.2` only
  reached OI-confirmed `n=23` and remained negative at `-18.9629 bps`.
- The current blocker is alpha/signal quality and sample scarcity, not OI panel
  freshness or missing 5m bars.

Decision: keep `eligible_for_demo_canary=false`. Do not launch Stage 1 demo,
do not mutate runtime config, and do not spend implementation time on full
OI-confirmed 5m report tooling until either the data window matures materially
or the hypothesis is revised.

Recommended next work: continue A4-C revise-or-archive analysis and W-AUDIT-8a
Phase C/D / 8c / 8b alpha-path work rather than demo canary preparation.
