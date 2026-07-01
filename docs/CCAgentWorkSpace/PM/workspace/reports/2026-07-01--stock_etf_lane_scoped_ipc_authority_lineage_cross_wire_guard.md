# Stock/ETF Lane-Scoped IPC Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；lane-scoped IPC authority / lineage hardening

## 結論

已補強 `stock_etf_lane_scoped_ipc` 的 top-level lane/broker/authority flags、Python forward-only / direct-write
denial、Bybit IPC/paper path denial、live denial、no-contact/no-runtime/no-secret flags、required method
coverage、denied method handling、command operation/authority/effect/rust ownership、required gate/request-field/
denial-reason coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC
runtime、IBKR connector、secret、DB/evidence writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 新增 `lane_scoped_ipc_rejects_each_top_level_authority_gap_independently`。
- Rust acceptance 新增 `lane_scoped_ipc_rejects_each_command_coverage_gap_independently`。
- Rust acceptance 新增 `lane_scoped_ipc_rejects_each_command_shape_gap_independently`。
- Acceptance 證明 contract/source/lane/broker/Rust authority/Python forward-only/Python direct-write denial/
  Bybit IPC reuse denial/existing Bybit paper path denial/live denial/Bybit live protection/contact/runtime/secret
  gaps 可各自只產生單一對應 blocker。
- Acceptance 證明 missing command、duplicated command、extra denied command 可各自只產生單一對應 blocker。
- Acceptance 證明 submit-paper command 的 operation、authority scope、effect flag、rust ownership、required gate、
  required request field、typed denial reason gaps 可各自只產生單一對應 blocker。
- Python source-static guard 新增 required-method/default/accepted-fixture block parsers，鎖住 denied methods
  不得進 `REQUIRED_METHODS`，並鎖住 accepted fixture 只能用 StockEtfCash/IBKR/no-runtime/no-secret posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance`：`12 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IPC server start、IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
