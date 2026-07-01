# PM Report — IBKR Connector Risky Config Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Stock/ETF inert connector skeleton source-only guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 test-only regression，鎖住 risky endpoint
config 對 inert IBKR connector preview payload 的 fail-closed 行為；不是 connector
wiring、不是 FastAPI route wiring、不是 Rust IPC behavior change。

## Completed

- 在 `test_stock_etf_ibkr_connector_skeleton.py` 新增 `RISKY_CONFIG_BLOCKERS`。
- 新增 `test_ibkr_connector_risky_config_only_expands_blockers`。
- 覆蓋 `connection_plan`、readiness、account/market-data/contract-detail preview、
  session attestation、readonly probe result-import、paper lifecycle、fill import、
  paper attestation。
- 斷言 risky config 只會新增 blockers，且所有 side-effect false keys 保持 `false`。

## Verification

- `python3 -B -m py_compile ...test_stock_etf_ibkr_connector_skeleton.py`：PASS。
- `python3 -B -m pytest -q ...test_stock_etf_ibkr_connector_skeleton.py`：
  `9 passed`。
- Python no-write/static/GUI guard focused pytest：`30 passed`。
- Stock/ETF Python route/static suite：`121 passed`。

廣義 `-k stock_etf` collection 嘗試因無關 L2 tests 在 Python 3.10 缺少
`tomllib` 中止；本 checkpoint 改用 `test_stock_etf_*.py` 檔案集合完成相關覆蓋。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
