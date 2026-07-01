# Stock/ETF Release Packet Exact Blocker Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；release packet acceptance hardening

## 結論

已補強 `StockEtfReleasePacketV1` aggregate fail-closed acceptance coverage。這次只改 Rust acceptance 與 PM/Operator
記錄，不改 Rust production validator、IPC/API routes、IBKR connector、secret、socket/client construction、paper order
routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default release packet 固定為完整 ordered blocker vector，覆蓋 packet identity/source、
  required Phase5 roles, role reports, log/manifest hashes, cleanup proof, evidence archive, paper-shadow window,
  shakedown 與 sealed posture。
- Rust acceptance 將 identity/source drift、Phase5 role/hash aggregate gaps、migration evidence gaps、kill-disable cleanup
  aggregate gaps、secret/live authority aggregate gaps 固定為 exact blocker vectors。
- Rust acceptance 移除 release packet blocker 的 loose `has/lacks` helpers；secret/live/seal/window/shakedown cross-wire
  cases 改為 exact single-blocker assertions。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_release_packet_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_release_packet_source_static.py --tb=short`：`9 passed`。
- `cargo test -p openclaw_types --test stock_etf_release_packet_acceptance`：`15 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer。
- 無 paper-shadow launch、release launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
