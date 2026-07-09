# Operator Brief — A4-C RCA Final + C1 Proof Start

Date: 2026-05-15

## Result

- `P1-A4C-RCA-1` is closed as no-revive.
- `P1-A4C-REV-1` is not opened.
- A4-C remains diagnostic-only; no same-feature Stage 0R rerun is authorized.
- `W-AUDIT-8a C1` 24h isolated `allLiquidation.BTCUSDT` proof is running on
  `trade-core`.

## Evidence

- A4-C 7d RCA remained red: `avg_net_bps=-1.0013`, `PSR(0)=0.1904`,
  `DSR=0`, R2(120)=0.
- Best finite threshold probe X=5/Y=0.20 was only `+1.4739 bps`, below
  revive/promotion bands.
- C1 60s smoke verdict: `SMOKE_PASS_NOT_C1_PROOF`.
- C1 24h proof PID: `4100789`; started `2026-05-15T19:53:09Z`; expected
  finish `2026-05-16T19:53:09Z` if uninterrupted.

## Boundary

No production WS topic revival, parser/writer restoration, DB write,
rebuild/restart, auth renewal, paper/demo launch, risk/sizing/config mutation,
or live action.
