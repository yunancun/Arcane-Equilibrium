# Alpha-Edge Regime Evidence Governance Findings

Date: 2026-05-31
Scope: S4 critique, S1-Sx evidence governance, Bybit market-data role, external narrative side evidence.
Mode: read-only governance and planning audit. No runtime deploy, DB write, auth change, or trading action.

## What We Checked

- Current Alpha-Edge state in `TODO.md` and `docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`.
- Operator decisions recorded after S1-W1-S1 / S2-W0-S1 / S4-W0-S1.
- QC review of regime/falsification gates for S1-Sx.
- MIT review of existing tables, Bybit endpoints, retention, provenance, and breadth automation feasibility.
- Bybit V5 public market API documentation for kline, funding history, open interest, long/short ratio, orderbook, ticker, and historical volatility.

## What We Found

1. Bull-market data is not the problem. The risk is unlabeled use of bull-heavy evidence as if it proves general-market alpha.
2. S4 cannot remain a 2024 bull funding proof track. It should be a global S1-Sx regime/falsification overlay.
3. Bybit public market endpoints provide raw market-state data, not prediction. Trend/regime labels must be computed locally from leak-free, point-in-time features.
4. Existing storage is partly ready but not enough for 18mo evidence:
   - `market.klines` can support S1 after the approved retention extension.
   - `market.symbol_universe_snapshots` supports survivorship-correct breadth.
   - funding/OI/long-short tables currently have shorter retention and need an explicit storage decision.
   - `panel.*` tables are short-retention derived surfaces and cannot be treated as 18mo alpha-history.
   - `market.market_tickers.index_price` / `mark_price` persistence is already flagged as unreliable.
5. Future news / X / Reddit agents can add context, but they cannot be primary signal sources and cannot override failed quantitative gates.

## Conclusion

Alpha-Edge promotion must move to a fixed evidence matrix:

- regime: bull / range / bear / chop / high-vol,
- breadth: core25 / scanner-active / top-liquidity 40-50 / full survivorship diagnostics,
- freshness: 2024 / 2025 / 2026 and rolling recent windows,
- survivorship: active-only comparison vs delisted/closed-aware universe,
- execution realism: fees, slippage, maker-fill, latency, order availability, and capacity/depth.

Bull-only or stale-only positive results are not durable alpha. They should be classified as `regime-bet / learning-only` unless non-bull and recent slices independently pass.

Do not dispatch E1 straight into backfill. The next step is PA/MIT engineering arrangement for alpha-history provenance, automated breadth-ladder, local trend/state classifier, global regime robustness gates, and side-evidence boundaries.

## Source Links

- Bybit Kline: https://bybit-exchange.github.io/docs/v5/market/kline
- Bybit Funding History: https://bybit-exchange.github.io/docs/v5/market/history-fund-rate
- Bybit Open Interest: https://bybit-exchange.github.io/docs/v5/market/open-interest
- Bybit Long/Short Ratio: https://bybit-exchange.github.io/docs/v5/market/long-short-ratio
- Bybit Market category: https://bybit-exchange.github.io/docs/api-explorer/v5/market/market
