"""
M4 Stage 1 source ingestion helpers（per W1-B spec §1）。

4 PG loader + 1 stub：
   - kline_loader: market.klines
   - fills_loader: trading.fills (engine_mode IN ('live', 'live_demo'))
   - liquidations_loader: market.liquidations + self-fill filter
   - funding_loader: market.funding_rates
   - token_unlocks_stub: Sprint 3+ stub (NotImplementedError)
"""
