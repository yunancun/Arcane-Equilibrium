# AEG-S1-FND-4 Public Endpoint Runner Client Gap + Persistence Map

Date: 2026-06-01
Status: PM/BB design map complete; implementation still blocked until scoped separately
Owner chain: PM -> BB + PA -> MIT -> E1 only after scoped implementation task
Mode: docs/design/read-only. No endpoint ingestion implementation, DB write, migration apply, runtime deploy, auth, order, collector runtime, backfill run, alpha scoring, or promotion verdict.

## Verdict

FND-4 maps the public Bybit endpoint runner/client gaps and persistence choices
needed before any historical writer can be implemented. BB read-only audit
returned with no web/git/file/DB/runtime changes.

Preferred client path: extend the isolated Python replay public client into an
AEG public-only runner. Do not directly use the Rust `MarketDataClient` for AEG
evidence ingestion until BB verifies a public-only facade that cannot touch auth,
private, order, or account endpoints.

## 1. Endpoint Readiness Matrix

| Endpoint | AEG use | Current local posture | Future persistence target | Gate |
|---|---|---|---|---|
| `GET /v5/market/kline` | Primary OHLCV, trend/momentum/regime bars. | Python replay client allowlists kline but uses `_KLINE_LIMIT=200`; Rust method exists; parsers are not AEG-strict and can skip/default malformed values. | `market.klines` after approved 1095d retention + DB provenance ledger. | Add strict parser, 2-5 rps throttle, page guards, coverage report, no historical `1m` first pass. |
| `GET /v5/market/mark-price-kline` | Mark-price liquidation and execution-realism sensitivity. | No verified local Python/Rust implementation. Standard OHLCV parser is incompatible. | Future dedicated price-kline research table or artifact-only diagnostics until storage is approved. | Add price-only parser `[start, open, high, low, close]`; no volume/turnover assumptions. |
| `GET /v5/market/index-price-kline` | Basis/regime inputs when long-history basis is needed. | No verified local Python/Rust implementation. | Future dedicated price-kline research table; do not use `market.market_tickers` as historical source. | Same price-only parser and storage decision gate. |
| `GET /v5/market/premium-index-price-kline` | Premium/funding-regime features. | No verified local Python/Rust implementation. | Future dedicated price-kline research table or artifact-only diagnostics. | Same price-only parser and storage decision gate. |
| `GET /v5/market/funding/history` | Funding realized carry and funding-extreme overlays. | Rust method has start/end/limit, but live poller only fetches latest `limit=1`; Python replay client does not allowlist it; existing Stage 0R script is not a DB writer. | Approved dedicated research-history funding table. | Historical paging by `endTime`, `limit<=200`, no start-only request, funding interval/cap provenance from instruments-info. |
| `GET /v5/market/open-interest` | OI participation/trend overlay. | Rust method exists but lacks `startTime`/`endTime` and cursor pagination contract; live poller only fetches latest `limit=1`. | Approved dedicated research-history OI table. | Add cursor pagination, intervalTime support, non-advance cursor guard, strict numeric parser. |
| `GET /v5/market/account-ratio` | Long-short sentiment overlay, secondary evidence. | Rust method exists but lacks historical cursor contract; live poller only fetches latest `limit=1`; period docs have drift history. | Approved dedicated research-history long-short table. | Smoke period values, cursor pagination, `limit<=500`, strict parser. |
| `GET /v5/market/tickers` | Current liquidity, BBO, current mark/index/funding metadata. | Python and Rust clients exist; endpoint is current snapshot only; current Rust snapshot path does not preserve the full funding/mark/index/OI surface needed for evidence. | Local forward recorder only; not historical proof. | Label as locally recorded snapshots. Never call it Bybit historical ticker history. |
| `GET /v5/market/orderbook` | Current execution realism/capacity snapshots. | Python and Rust snapshot support exists; REST orderbook is not replayable historical orderbook. | Local forward recorder only. | Not an 18mo historical source unless locally captured forward. |
| `GET /v5/market/instruments-info` | PIT universe, launch/delist, funding cap/interval metadata. | V058 helper/cron exists with pagination; Rust `SymbolSpec` omits status, launch/delivery time, funding interval, and funding caps. | `market.symbol_universe_snapshots` and FND-2 universe artifacts. | Must query non-default statuses intentionally; parse `launchTime`, `deliveryTime`, `fundingInterval`, `upperFundingRate`, `lowerFundingRate`. |

## 2. Public-Only Runner Contract

The future AEG runner must:

- Use only Bybit public market endpoints.
- Maintain an explicit endpoint allowlist.
- Have no auth headers, signing path, account/private/order endpoints, or shared
  live trading REST pool.
- Default to 2-5 requests/sec for AEG backfill, even if older replay code allows
  higher rates.
- Capture `X-Bapi-Limit*` headers when the client surface exposes them.
- Retry only bounded transient cases (`429`, selected `5xx`, documented Bybit
  rate/transient retCodes).
- Treat final nonzero `retCode`, timeout, unexpected row shape, cursor
  non-advance, or parse failure as coverage failure.
- Emit per-endpoint request/response lineage into the AEG run artifact set.

## 3. Parser Rules

Strict parser requirements:

- Missing numeric fields fail the row; they cannot silently become `0.0`.
- Standard OHLCV kline requires 7 fields:
  `[start, open, high, low, close, volume, turnover]`.
- Price-only mark/index/premium klines require 5 fields:
  `[start, open, high, low, close]`.
- Funding rows require `symbol`, `fundingRate`, and `fundingRateTimestamp`.
- OI rows require `openInterest` and `timestamp`.
- Long-short rows require `buyRatio`, `sellRatio`, and `timestamp`.
- Any extra fields may be preserved in raw payload artifacts, but missing
  required fields fail coverage.

Rust parser behavior that defaults failures to empty string or `0.0` is not
acceptable for promotion evidence.

## 4. Persistence Map

Approved by FND-1:

| Data | Persistence path |
|---|---|
| OHLCV `1d`/`4h` | `market.klines` only after 1095d retention mutation and DB provenance ledger. |
| Funding history | Dedicated research-history funding table. |
| Open-interest history | Dedicated research-history OI table. |
| Long-short history | Dedicated research-history long-short table. |

Not yet approved:

| Data | Required decision |
|---|---|
| Mark/index/premium price-only klines | Dedicated `research.alpha_price_klines_history`-style table or artifact-only diagnostics. |
| Current tickers/orderbook | Forward local recorder only; no 18mo historical claim. |

Any new table or retention mutation requires V### migration design, Guard A/B/C,
Linux PG dry-run, idempotency double-apply, rollback plan, E2/E4 review, and PM
operator execution approval.

## 5. `market_tickers` Fix-vs-Bypass

Recommendation: bypass `market.market_tickers` for historical basis/index
evidence.

Facts:

- Bybit `tickers` is current snapshot only.
- V063 explicitly says historical ticker funding data is only available if this
  system locally recorded it.
- Current Rust ticker/event path does not propagate every field needed for
  evidence: `TickerSnapshot` has no funding field, the writer insert excludes
  V063 `funding_rate`, and one fast-track path can write placeholder
  `mark_price=0` / `open_interest=0`.
- REF-21 Python recorder can write `funding_rate`, `mark_price`, and
  `index_price`, but that is forward local capture only.
- V115 documents `market_tickers` historical basis as dead/unbackfillable.
- Existing retention is short (`90d` Timescale, REF-21 prune default `45d`).

Therefore:

- Historical basis/index proof should use price-only kline endpoints with a
  dedicated storage decision, not `market_tickers`.
- `market_tickers` can remain a forward replay/microstructure surface.
- A future P3 fix may align Rust ticker writer with V063 `funding_rate`, but that
  fix is not a substitute for 18mo historical mark/index/premium evidence.
- That P3 fix should add/propagate `mark_price`, `index_price`,
  `funding_rate`, and `open_interest` with nullable/strict semantics instead of
  zero placeholders. Even after the fix, the evidence is forward-only.

## 6. Future Implementation Gates

Before E1 implements an endpoint runner:

1. BB approves the public-only client path and endpoint allowlist.
2. MIT confirms storage target for every endpoint output.
3. PA confirms artifact/manifest/coverage lineage matches AEG-S0.
4. E2 reviews fail-closed parser and pagination behavior.
5. E4 runs unit/integration tests with fake Bybit payloads:
   - reverse-sorted kline paging,
   - funding `endTime` paging,
   - OI cursor non-advance failure,
   - long-short period smoke fixture,
   - price-only parser rejects OHLCV assumptions,
   - tickers/orderbook are labeled current snapshot only.

Still blocked after this FND-4 map:

- Endpoint ingestion implementation.
- Historical writer implementation.
- DB writes/backfill.
- New price-kline storage migration.
- Alpha scoring or promotion verdict.
