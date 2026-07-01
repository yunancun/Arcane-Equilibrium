# Operator Brief — IBKR Stock/ETF DQ Manifest Contract

## What Changed

新增 `stock_etf_dq_manifest_v1`，把未來 Phase 3 daily DQ manifest 必須提供的
contract identity、collector/provenance/source lineage、資料品質欄位與 side-effect
denial 固定為 source-only contract。

## Practical Effect

- Phase0 named contracts：`34 -> 35`。
- Existing Evidence Status panel 現在顯示 default-blocked `dq_manifest` contract
  id/source version、lineage hash presence 與 side-effect flags。
- FastAPI 會把 DQ manifest 的 IBKR contact、connector runtime、market-data
  ingestion、DQ writer、evidence-clock start、scorecard writer、DB apply、secret
  serialization、tiny-live/live truthy claims 擋成 contract violation。

## Verification

- Python compile PASS
- Stock/ETF JS syntax PASS
- Scoped Rust format PASS
- Phase3 evidence acceptance `19 passed`
- Phase0 manifest acceptance `6 passed`
- Focused Phase0/Evidence/Route pytest `22 passed`
- Full Stock/ETF FastAPI/static `120 passed`
- Full `openclaw_types` PASS
- Engine Stock/ETF focused `31 passed`
- Docs trace guard `2 passed`
- `git diff --check` PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read
probe execution, collector start, market-data ingestion, DQ writer, paper
order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence
clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.
