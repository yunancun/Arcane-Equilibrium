# Stock/ETF Lane Taxonomy Authority Decision Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；lane taxonomy authority / decision hardening

## 結論

已補強 `stock_etf_lane` 的 broker capability decision coverage，固定 StockEtfCash/IBKR/Paper/Shadow/ReadOnly
taxonomy、feature flag fail-closed posture、gate input fail-closed posture、live/margin/options/account-write
denial、flag denial、read/shadow/paper gate denial與 allowed authority scope。這次只改 acceptance 與
source-static guard，不改 Rust production logic、runtime、IBKR connector、secret、DB/evidence writer、paper
order route 或 Bybit 路徑。

## 變更

- Rust acceptance 新增 `broker_capability_rejects_each_lane_broker_and_operation_gap_independently`。
- Rust acceptance 新增 `broker_capability_rejects_each_flag_gap_independently`。
- Rust acceptance 新增 `broker_capability_rejects_each_gate_gap_independently`。
- Rust acceptance 新增 `broker_capability_allows_only_read_shadow_or_paper_when_all_gates_pass`。
- Acceptance 證明 wrong asset lane、wrong broker、live-reserved environment、live order、margin/short、
  options/CFD、transfer/account-write、wrong instrument kind 可各自只產生單一對應 denial reason。
- Acceptance 證明 lane disabled、readonly disabled、paper disabled、shadow-only flags 可各自只產生單一對應
  denial reason。
- Acceptance 證明 read authorization、shadow cost/universe、paper market/credential/connector/auth/decision
  lease/guardian gates 可各自只產生單一對應 denial reason。
- Acceptance 證明 all-green read、shadow、paper requests 只得到對應 ReadOnly/ShadowOnly/PaperRehearsal
  authority scope；live/tiny-live 和 account-write 仍不可通過。
- Python source-static guard 新增 default block parser，鎖住 `StockEtfFeatureFlags` 與
  `StockEtfGateInputs` default fail-closed posture，並鎖住 `evaluate_broker_operation` denial ordering。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_lane_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_lane_acceptance`：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
