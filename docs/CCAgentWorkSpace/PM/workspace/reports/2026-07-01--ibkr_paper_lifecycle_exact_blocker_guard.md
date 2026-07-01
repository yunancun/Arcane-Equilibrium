# IBKR Paper Lifecycle Exact Blocker Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper lifecycle acceptance hardening

## 結論

已補強 `BrokerLifecycleEventLogV1` append-only paper lifecycle/event-log 的 aggregate fail-closed acceptance coverage。
這次只改 Rust acceptance 與 PM/Operator 記錄，不改 Rust production validator、IPC/API routes、IBKR connector、
secret、socket/client construction、lifecycle writer、paper order routing、fill import execution 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `BrokerLifecycleEventLogV1` 固定為完整 ordered blocker vector，覆蓋 lifecycle/
  event-log/source identity、event/request hashes、operation transition、local/idempotency/reconciliation ids、state
  transition、denial reason、stale policy 與 raw/redacted artifact hashes。
- Rust acceptance 將 contract/source drift、live/account-write cross-wire、append-only chain gaps、genesis shape、
  operation/transition mismatches、terminal-state reversal、unknown-state recovery、stale-policy drift、denied-event
  posture 固定為 exact blocker vectors。
- Rust acceptance 移除 paper lifecycle blocker 的 loose `blockers.contains` checks；aggregate 與 cross-wire cases
  改為完整 ordered-vector assertions。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_paper_lifecycle_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_paper_lifecycle_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test ibkr_paper_lifecycle_acceptance`：`15 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 lifecycle writer、paper order routing、fill import execution、broker session、DB/evidence writer、scorecard writer、evidence clock。
- 無 paper-shadow launch、release launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
