# IBKR Phase 2 Policy Exact Prerequisite Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 2 prerequisite policy hardening

## 結論

已補強 `ibkr_phase2_policies` 的 prerequisite policy exact rejection coverage。這次只改 acceptance 與
source-static guard，不改 Rust production validator、runtime、IBKR connector、secret、DB/evidence writer、
paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `IbkrPhase2PolicyBundleV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 redaction/rate-limit/audit/paper-attestation/python-write-guard contract id/source
  version drift 固定為 exact 雙 blocker。
- Rust acceptance 將 redaction leak、rate-limit budget、audit lineage、paper-attestation authority、
  python-write guard aggregate gaps 固定為 exact blocker vectors。
- Python source-static guard 新增各 policy validator 與 bundle validator blocker ordering parser，鎖住
  prerequisite policy emit order。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_policy_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_policies_source_static.py --tb=short`：`5 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_policy_acceptance`：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
