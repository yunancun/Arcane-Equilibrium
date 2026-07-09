# C1 BB/MIT Pre-Review Packet

**Date**: 2026-05-17T07:19Z  
**Role**: PM(default)  
**Scope**: pre-review packet only. No final C1 sign-off, no production topic revival, no parser/writer implementation, no DB schema write, no runtime restart, no auth mutation, no paper/live/mainnet enablement.

## Status

C1 v2 proof is still in flight and must not be treated as PASS.

Current checkpoint at `2026-05-17T07:19:12Z`:

| Field | Value |
|---|---|
| PID | `377531` |
| Session | `c1_v2_20260516T145616Z` |
| Started | `2026-05-16T14:56:16Z` |
| 23h tolerance check | `2026-05-17T13:56:16Z` |
| 24h target complete | `2026-05-17T14:56:16Z` |
| Remaining to 24h | `7h 37m` |
| Interim verdict | `IN_PROGRESS_HEALTHY` |
| C1 proof eligible | `false` |
| Connection errors | `0` |
| Reconnect attempts / successes | `0 / 0` |
| Subscribe failures | `0` |
| Uptime ratio | `0.999989570622708` |
| Candidate messages seen | `80` |

Topic counts:

| Topic | Count | Last seen UTC |
|---|---:|---|
| `allLiquidation.BTCUSDT` | 80 | `2026-05-17T05:59:00Z` |
| `kline.1.BTCUSDT` | 30,469 | `2026-05-17T06:56:15Z` |
| `orderbook.50.BTCUSDT` | 1,488,796 | `2026-05-17T06:56:17Z` |
| `publicTrade.BTCUSDT` | 156,685 | `2026-05-17T06:56:15Z` |
| `tickers.BTCUSDT` | 333,554 | `2026-05-17T06:56:17Z` |

Runtime artifact:

- `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json`

## BB Pre-Review Focus

BB can pre-review the current evidence before final duration completes, but final sign-off must wait for the completed report.

Pre-review questions:

1. Does `allLiquidation.BTCUSDT` match the official public topic shape expected by Bybit V5?
2. Did candidate traffic poison or interfere with control streams (`tickers`, `orderbook.50`, `publicTrade`, `kline.1`)?
3. Are `subscribe_failure_count=0`, `connection_errors=0`, and `reconnect_attempts=0` acceptable so far?
4. Are the observed candidate samples sufficient to confirm no `handler not found` / topic rejection behavior?
5. Does BB agree that production topic-builder removal remains blocked until final C1 PASS, not merely interim health?
6. Does BB sign or reject the side semantics needed by W-AUDIT-8c:
   - `S=Sell` = long liquidations, mean-reversion direction `+1`
   - `S=Buy` = short liquidations, mean-reversion direction `-1`

BB final sign-off must cite the final C1 JSON/Markdown report, not this pre-review note alone.

## MIT Pre-Review Focus

Actual Linux schema at `2026-05-17T07:19Z`:

| Column | Type | Nullable |
|---|---|---|
| `ts` | `timestamp with time zone` | NO |
| `symbol` | `text` | NO |
| `side` | `text` | NO |
| `qty` | `real` | NO |
| `price` | `real` | NO |

Current row count:

- `market.liquidations = 0`

Mapping table:

| Bybit field | Meaning | Actual target | Transform | MIT question |
|---|---|---|---|---|
| `T` | event timestamp ms | `market.liquidations.ts` | `to_timestamp(T / 1000.0)` or equivalent Rust UTC conversion | Approve direct mapping? |
| `s` | symbol | `market.liquidations.symbol` | string, e.g. `BTCUSDT` | Approve exact pass-through? |
| `S` | liquidation side | `market.liquidations.side` | string `Buy` / `Sell` | Approve enum/text semantics and BB side meaning? |
| `v` | quantity | `market.liquidations.qty` | decimal string -> finite positive float | Approve `real`, or require precision migration? |
| `p` | price | `market.liquidations.price` | decimal string -> finite positive float | Approve `real`, or require precision migration? |

Schema delta finding:

- Earlier design text mentioned `event_time` / `liquidation_time_ms`, but the actual Linux table has `ts`.
- No `value_usd` column exists. Strategy/replay should derive `notional_usd = qty * price` outside the writer.
- No `event_type` column exists. The Bybit payload `type=snapshot` should not be stored unless MIT requests a V09X schema delta.

MIT pre-review questions:

1. Is the current 5-column schema sufficient for W-AUDIT-8c Stage 0R cluster construction?
2. Is `real` precision acceptable for `qty` / `price`, or does MIT require a V09X migration to `double precision` / `numeric` before writer revival?
3. Should the writer preserve the Bybit `type=snapshot` field, or is it safe to ignore for current replay math?
4. Does MIT accept one row per liquidation item in the `data` array?
5. Does MIT require dedupe keys beyond `(ts, symbol, side, qty, price)` before production writer revival?

## Final C1 Sign-Off Gate

The final reviewer packet should be generated only after one of these checkpoints:

1. Preferred: 24h target complete at `2026-05-17T14:56:16Z`.
2. Earliest tolerance: `elapsed_sec >= 82,800` (23h), if PM explicitly chooses to use the v2 tolerance path and BB/MIT accept it.

Required final checks:

- final report verdict is `PASS_C1_PROOF_CANDIDATE`
- `subscribe_failure_count = 0`
- `poison_events = []`
- `connection_errors = []`, or any reconnect behavior is explicitly accepted by BB
- `uptime_ratio >= 0.95`
- candidate samples contain valid `T/s/S/v/p` shape
- MIT signs schema mapping or provides a concrete V09X migration delta

## Hard Boundary

Until final BB + MIT sign-off:

- production topic builders must still exclude `liquidation.*`, `price-limit.*`, `adl-notice.*`, and `allLiquidation*`
- `AlphaSurface.liquidation_pulse` must remain `None`
- any `LiquidationCascade` consumer must fail closed
- no W-AUDIT-8c runtime implementation is authorized

PM STATUS: PRE-REVIEW READY / FINAL SIGN-OFF BLOCKED.
