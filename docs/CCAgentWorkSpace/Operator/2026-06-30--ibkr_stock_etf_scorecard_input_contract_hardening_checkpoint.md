# Operator Brief - IBKR Stock/ETF Scorecard Input Contract Hardening

日期：2026-06-30
結論：scorecard input contracts 已加硬，但不授權 runtime。

## 完成內容

- Cash ledger、cost model、benchmark、shadow fill、storage capacity 現在都必須
  帶正確 named `contract_id` 和 `source_version=1`。
- Scorecard bundle 現在必須帶 market-data provenance、reference-data source、
  risk-policy 三個上游 contract hashes。
- Bundle 會拒絕 IBKR contact、connector runtime、broker fill import、
  scorecard writer、DB apply、evidence clock、secret serialization、
  tiny-live/live authority，以及 Bybit-live regression。
- Broker capability registry 和 lane-scoped IPC 已改用同一組 scorecard contract
  constants，降低 gate drift。

## 驗證

- Focused acceptance: `30 passed`
- Full `openclaw_types`: `35` unit/golden + `173` integration/acceptance +
  `0` doc-tests passed

## 邊界

這不是 IBKR 上線，也不是 healthcheck。仍然沒有：

- IBKR contact / process startup
- secret read/create/serialization
- connector runtime / collector
- broker fill import / scorecard writer / DB apply
- evidence clock / GUI lane authority / paper order
- tiny-live / live
- Bybit live behavior change

首次 IBKR contact 仍需 real secret/topology evidence + immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact。
