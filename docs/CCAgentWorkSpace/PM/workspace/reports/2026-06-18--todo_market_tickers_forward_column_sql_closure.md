# TODO v174 Market Tickers Forward-Column SQL Closure

Date: 2026-06-18
Role: PM
Scope: TODO active-queue hygiene backed by read-only source/runtime evidence

## Decision

Archive `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` from `TODO.md` §5.

The row was already source-landed and deploy-gated. Current runtime has passed the next operator-approved restart, and production SQL now shows the forward columns are being populated.

## Evidence

- Source checkpoint: `5733eb06` (`[skip ci] Complete A1 basis gate and ticker forward tests`) added/locked the forward path.
- Runtime source HEAD: `83b7632d`; Linux checkout contains that ancestry.
- Current Linux engine: PID 3134818, started `2026-06-18 14:11:50+02`.
- Production schema: `market.market_tickers.mark_price`, `index_price`, `open_interest`, and `funding_rate` are nullable `real`.
- Source path:
  - `ws_client/parsers.rs` parses Bybit tickers fields into optional `PriceEvent` values.
  - `step_0_fast_track.rs` forwards those options into `MarketDataMsg::TickerSnapshot`.
  - `database/market_writer.rs` inserts the optional fields into `market.market_tickers` via `sanitize_optional_f32`, preserving missing/non-finite values as SQL NULL.

## Production SQL

Read-only query window: `ts >= TIMESTAMPTZ '2026-06-18 14:11:50+02'`.

Result:

- rows: `587319`
- span: `2026-06-18 14:11:50.178+02` to `2026-06-18 20:37:07.831+02`
- `mark_price IS NOT NULL`: `40912`
- `index_price IS NOT NULL`: `84919`
- `open_interest IS NOT NULL`: `5913`
- `funding_rate IS NOT NULL`: `719`
- zero counts: mark/index/OI = `0`; funding = `8`

Funding `0.0` is a legitimate exchange value and was explicitly preserved by the source contract; mark/index/OI fake-zero evidence is absent in this post-start window.

## Boundary

This closes forward recorder persistence and fake-zero evidence only.

No backfill, no retention change, no CI, no deploy, no rebuild, no restart, no production source mutation, no runtime mutation, no DB write, no auth/risk/order/trading mutation.
