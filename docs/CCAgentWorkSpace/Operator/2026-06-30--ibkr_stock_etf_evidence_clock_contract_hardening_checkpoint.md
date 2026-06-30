# Operator Brief - IBKR Stock/ETF Evidence-Clock Contract Hardening

日期：2026-06-30
結論：`stock_etf_evidence_clock_v1` 已加硬，但不啟動 evidence clock。

## 完成內容

- Evidence-clock day packet 現在必須帶正確 named `contract_id` 和
  `source_version=1`。
- Checker 現在要求 `stock_etf_cash` / IBKR lane binding、read-only/paper/shadow
  environment、source artifact hash、market-data provenance hash、scorecard input
  bundle hash。
- Checker 會拒絕自身接觸 IBKR、啟動 connector、啟動 runtime evidence clock、
  寫 scorecard、DB apply、secret serialization、tiny-live/live authority，以及
  Bybit-live regression。
- `WINDOW_COMPLETE` 仍不能由 source checker 單獨宣稱。

## 驗證

- Focused acceptance: `33 passed`
- Full `openclaw_types`: `35` unit/golden + `174` integration/acceptance +
  `0` doc-tests passed

## 邊界

這不是 IBKR 上線，也不是 evidence clock start。仍然沒有：

- IBKR contact / process startup
- secret read/create/serialization
- connector runtime / collector
- runtime evidence clock / scorecard writer / DB apply
- GUI lane authority / paper order
- tiny-live / live
- Bybit live behavior change

首次 IBKR contact 仍需 real secret/topology evidence + immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact。
