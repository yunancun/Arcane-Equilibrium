# IBKR Phase 2 Runtime Secret/Topology Exact Default Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 2 secret-slot / API topology fail-closed hardening

## 結論

已補強 `ibkr_phase2_runtime` 的 secret-slot contract 與 API session topology default fail-closed posture。
這次只改 acceptance 與 source-static guard，不改 Rust production validator、runtime、IBKR connector、secret、
DB/evidence writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `IbkrSecretSlotContractV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 default `IbkrApiSessionTopologyV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 live TWS/Gateway port topology case 固定為 `LivePortDenied` + `PaperPortNotUsed` 雙 blocker。
- Python source-static guard 新增 fail-closed verdict 與 live-port dual-denial source guard，鎖住 secret slot
  live-secret denial 與 topology live-port/paper-port 雙重拒絕邏輯。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_runtime_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_runtime_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
