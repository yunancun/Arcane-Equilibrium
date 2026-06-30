# Operator Brief — IBKR Stock/ETF Market-Data Provenance Contract

日期：2026-06-30
結論：已加硬 `stock_market_data_provenance_v1`，但不授權 runtime。

## 完成內容

- Future Stock/ETF market-data provenance 現在可 machine-check。
- 驗證內容包括 lane/broker/environment、vendor/entitlement、payload/source
  hashes、received/exchange timestamps、adjustment marker、instrument identity
  hash、calendar session id。
- Broker capability gates 現在要求此 contract 才能做 market-data read、
  shadow-fill reconstruction、scorecard derivation。

## 邊界

這不是 IBKR 上線，也不是 healthcheck。仍然沒有：

- IBKR contact / process startup
- secret read/create/serialization
- connector runtime / collector / market-data ingestion
- evidence clock / scorecard writer / DB apply
- GUI lane authority / paper order
- tiny-live / live
- Bybit live behavior change

首次 IBKR contact 仍需 real secret/topology evidence + immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact。
