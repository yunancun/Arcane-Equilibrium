-- REF-21 replay fidelity: locally recorded ticker funding rate.
-- Bybit's historical public REST does not provide replayable ticker history;
-- future replay windows can only consume funding_rate if the local recorder
-- captured it in market.market_tickers.

ALTER TABLE market.market_tickers
    ADD COLUMN IF NOT EXISTS funding_rate REAL;

COMMENT ON COLUMN market.market_tickers.funding_rate IS
    'Locally recorded Bybit ticker fundingRate for replay TickContext enrichment; nullable for pre-recorder rows.';
