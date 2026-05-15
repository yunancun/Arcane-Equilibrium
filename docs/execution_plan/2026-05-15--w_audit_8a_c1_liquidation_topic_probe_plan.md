# W-AUDIT-8a C1 — Liquidation Topic Standalone Proof Plan

Date: 2026-05-15
Scope: BB standalone public WebSocket proof only. No production subscription change, no parser revival, no writer revival, no DB write, no runtime restart, no auth change.

## Verdict

C1 remains BLOCKED until a 24h isolated WebSocket proof passes.

The current official Bybit V5 public topic is `allLiquidation.{symbol}` (example: `allLiquidation.BTCUSDT`). This supersedes the older shorthand `allLiquidation` used in some internal notes. The legacy `liquidation.{symbol}` topic is deprecated and must not be reintroduced into production.

Source checked 2026-05-15: Bybit official V5 docs describe `allLiquidation.{symbol}` as a public stream with 500ms push frequency and response fields `T`, `s`, `S`, `v`, and `p`.

## Current Run

2026-05-15 update:

- 60s smoke returned `SMOKE_PASS_NOT_C1_PROOF`.
- Smoke report: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_20260515T195158Z.md`.
- 24h isolated proof started on `trade-core` at `2026-05-15T19:53:09Z`.
- PID: `4100789`.
- Log: `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log`.
- Expected finish if uninterrupted: `2026-05-16T19:53:09Z`.

This run still does not authorize production revival until the final report is reviewed by BB and MIT.

## Probe Tool

Added standalone helper:

`helper_scripts/bybit/liquidation_topic_probe.py`

Default command:

```bash
python3 helper_scripts/bybit/liquidation_topic_probe.py \
  --topic allLiquidation.BTCUSDT \
  --duration-sec 86400
```

Short smoke:

```bash
python3 helper_scripts/bybit/liquidation_topic_probe.py \
  --topic allLiquidation.BTCUSDT \
  --duration-sec 60
```

The short smoke can prove only that the probe is executable and that the candidate topic does not immediately reject. It cannot satisfy C1.

## Contract

The probe uses a single isolated public WS connection to `wss://stream.bybit.com/v5/public/linear`.

It subscribes to:

- candidate topic: `allLiquidation.BTCUSDT` by default
- control topics on the same connection: `tickers.BTCUSDT`, `orderbook.50.BTCUSDT`, `publicTrade.BTCUSDT`, `kline.1.BTCUSDT`

C1 PASS requires all of:

- duration is at least 24h
- no `handler not found`, topic rejection, rate-limit, or access-frequency error
- connection does not enter a reconnect loop
- control topics continue receiving data on the same connection
- candidate payload sample, if seen, maps to the existing `market.liquidations` shape or a reviewed schema delta
- BB + MIT sign-off before any production topic builder change

## Output

The probe writes both latest and dated reports under:

`$OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/`

Files:

- `liquidation_topic_probe_latest.json`
- `liquidation_topic_probe_latest.md`
- `liquidation_topic_probe_<UTC>.json`
- `liquidation_topic_probe_<UTC>.md`

## Production Boundary

Production `full_subscription_list()` must remain unchanged until the 24h proof passes. The C0 guard forbidding `liquidation.*`, `price-limit.*`, `adl-notice.*`, and `allLiquidation*` remains correct because it protects the production builder from both legacy and new liquidation topics before BB sign-off.

## C1 Implementation After Proof

Only after PASS:

1. Restore parser support for `allLiquidation.{symbol}` with the official payload shape.
2. Add or update writer mapping into `market.liquidations` after MIT schema review.
3. Populate `LiquidationPulseProvider` from an in-memory rolling 60s buffer, not from PG hot path reads.
4. Enable a new passive healthcheck for liquidation pulse freshness.
5. Keep strategies declaring `LiquidationCascade` fail-closed when the pulse is missing or stale.
