# S2-W0-S1 Listing Gate-A Maker-Fill Feasibility

**Date**: 2026-05-31
**Role**: QC(default)
**Scope**: Track 2 listing-window capture feasibility + maker-fill Gate-A. Read-only quant/data investigation.
**Verdict**: **PROCEED to Gate-B**, with BB follow-up before production collector IMPL.

## Executive Summary

Gate-A does **not** kill Track 2. The primary maker-fill feasibility estimate is:

| Estimate | Result |
|---|---:|
| Primary BBO-touch estimate, +500bps pump trigger, 1bp PostOnly offset, 60s timeout | **59/67 = 88.1%** |
| Wilson 95% interval | **78.2% - 93.8%** |
| One-tick cross-through haircut, same trigger/offset | **57/67 = 85.1%** |
| Two-tick cross-through haircut, same trigger/offset | **54/67 = 80.6%** |
| Gate-A kill line | **<30% = KILL** |

This clears the Gate-A feasibility threshold by a wide margin. However, it is not an alpha proof. The same filled-touch sample shows adverse-selection risk: at the primary setting, **55.2%** of filled touches had positive short-side 60s markout, with median adverse markout **+6.6bps**. Interpretation: passive shorts are reachable because the pump often keeps moving, but that reachability can be toxic.

## Data Reality

Runtime PG, read-only, Linux `trade-core`:

| Item | Result |
|---|---:|
| `market.symbol_universe_snapshots` distinct symbols | 935 |
| New symbols since `market.klines` start (`2026-04-05`) | 52 |
| New symbols with any 1m kline | 5 |
| New symbols with first kline within listed_at +5m / +1h | 0 / 0 |
| New symbols with first kline within listed_at +24h | 2 |
| First-kline lag range | 8h19m42s to 5d05h43m10s |
| Median first-kline lag among captured symbols | 2d16h13m |

The current dataset still does **not** contain true listing-window bars. Gate-A therefore uses only the five partially captured listing samples as a microstructure proxy, not as a real listing alpha backtest.

Partially captured samples:

| Symbol | First kline lag | 60m up/down from first captured open | 6h up/down |
|---|---:|---:|---:|
| `GENIUSUSDT` | 2d16h13m | +189bps / -535bps | +189bps / -1450bps |
| `CHIPUSDT` | 5d05h43m | +542bps / -279bps | +1387bps / -677bps |
| `OPGUSDT` | 11h35m | +543bps / -389bps | +957bps / -389bps |
| `AIGENSYNUSDT` | 3d13h56m | +361bps / -145bps | +731bps / -341bps |
| `BILLUSDT` | 8h19m | +627bps / -98bps | +1108bps / -98bps |

## Method

I reused the `a2_maker_fill_feasibility.py` methodology:

- Synthetic smoke for A2 methodology passed: `PASS a2_maker_fill_feasibility smoke`.
- Entry BBO grace: 10s.
- Fill proxy: BBO touch within 60s.
- Spread guard: skip if entry spread >50bps.
- Offsets: 0, 1, 2, 5 bps; primary = 1bp.
- No orders, no fills, no TOML, no IPC, no collector changes.

Listing adaptation:

- Use the first captured 6h for each of the five partial listing samples.
- Trigger a fade-short opportunity after cumulative high from first captured open crosses a pump threshold.
- Primary trigger threshold = +500bps.
- De-duplicate to at most one trigger per symbol per 5-minute bucket.
- Passive short limit = `entry_best_ask * (1 + offset_bps / 10000)`.
- Simulated touch = future `best_bid >= limit_price` within 60s.

## Results

Primary sensitivity:

| Pump threshold | Offset | Events | Fills | Touch fill rate |
|---:|---:|---:|---:|---:|
| 300bps | 1bp | 124 | 109 | 87.9% |
| **500bps** | **1bp** | **67** | **59** | **88.1%** |
| 800bps | 1bp | 30 | 25 | 83.3% |

Primary +500bps / 1bp by symbol:

| Symbol | Attempts | Fills | Fill rate | Avg entry spread | Avg 60s short-side markout |
|---|---:|---:|---:|---:|---:|
| `AIGENSYNUSDT` | 8 | 7 | 87.5% | 2.77bps | -40.0bps |
| `BILLUSDT` | 40 | 34 | 85.0% | 7.64bps | +20.5bps |
| `CHIPUSDT` | 8 | 8 | 100.0% | 4.05bps | -22.1bps |
| `OPGUSDT` | 11 | 10 | 90.9% | 8.49bps | +36.0bps |

Queue-priority haircut:

| Offset | Raw touch | 1-tick cross-through | 2-tick cross-through |
|---:|---:|---:|---:|
| 0bps | 88.1% | 85.1% | 83.6% |
| **1bp** | **88.1%** | **85.1%** | **80.6%** |
| 2bps | 86.6% | 83.6% | 80.6% |
| 5bps | 80.6% | 79.1% | 76.1% |

Even with a crude queue-priority haircut, estimated reachability remains far above the 30% kill line.

## Risk And Limitations

The estimate is deliberately narrow: it tests whether a passive price is reachable, not whether the trade should be taken.

Key limitations:

- True listing instant is absent. The five samples begin **8h to 5d** after `listed_at`.
- Only 4 symbols contribute to the +500bps primary sample; `BILLUSDT` contributes 40/67 attempts.
- All primary triggers are pump-fade shorts. This does not test post-listing dump fades or two-sided behavior.
- BBO touch does not prove queue fill priority or partial fill.
- `market.market_tickers` snapshots can miss intra-snapshot trade-through.
- Adverse selection is not solved: primary filled touches have median **+6.6bps** adverse 60s markout for short entries.
- No exit model, holding-period PnL, borrow/funding drag, or liquidation-regime interaction is tested here.

## BB Read-Only Check

Local reference confirms production history: invalid public WS topics such as old `liquidation.{symbol}` returned `"handler not found"` and poisoned the connection; valid active public topics include `kline`, `publicTrade`, `orderbook.50`, and `tickers`.

Official Bybit docs checked:

- [Get Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument): `category=linear&status=PreLaunch` returns PreLaunch instruments with `launchTime` and `preListingInfo`.
- [Public Kline WS](https://bybit-exchange.github.io/docs/v5/websocket/public/kline): topic shape is `kline.{interval}.{symbol}`.
- [Public Trade WS](https://bybit-exchange.github.io/docs/v5/websocket/public/trade): topic shape is `publicTrade.{symbol}` and docs state pre-market public trade data is released from Continuous Trading.
- [Enums / pre-market phases](https://bybit-exchange.github.io/docs/v5/enum): docs state candle data is released from Cross Matching, while orderbook and public trade data are released from Continuous Trading.

Runtime isolated probe, read-only:

- Current PreLaunch symbols from public REST / runtime DB: `BPUSDT`, `SPCXUSDT`.
- Isolated WS subscribed to `kline.1.BPUSDT`, `publicTrade.BPUSDT`, `kline.1.SPCXUSDT`, `publicTrade.SPCXUSDT`, plus BTC control topics.
- Probe result: HTTP 101 handshake, subscribe ack `success:true`, **no `handler not found`**, BTC control kline/trade continued receiving data.
- PreLaunch `kline.1` produced zero-volume snapshots for `BPUSDT` and `SPCXUSDT`; PreLaunch `publicTrade` produced no messages during the short 12s probe, consistent with docs.

BB risk judgment:

- **Not a Gate-A blocker**: `kline.1` / `publicTrade` topic names for current PreLaunch symbols did not poison an isolated connection.
- **Gate-B follow-up required before production collector IMPL**: run a longer isolated probe through a real PreLaunch phase transition, especially CallAuction/CrossMatching -> ContinuousTrading. The current probe only covered symbols whose public REST reported `curAuctionPhase=ContinuousTrading`.
- Recommended engineering guard if Gate-B proceeds: subscription should be on an isolated connection or protected by unknown-handler forced reconnect, so any unexpected topic rejection cannot poison the main market-data connection.

## Recommendation

**PROCEED** from Gate-A to Gate-B planning. Do not kill Track 2 on maker-fill feasibility.

Gate-B still needs:

1. BB 24h isolated PreLaunch probe covering phase transition.
2. Capture-only collector design with no strategy-intent leakage.
3. Forward accumulation to n>=30 true listing captures.
4. A separate alpha/PnL test after captured samples exist.

This report performed **0 collector IMPL, 0 production code changes, 0 live/auth/order/execution changes, 0 commit, 0 push**.
