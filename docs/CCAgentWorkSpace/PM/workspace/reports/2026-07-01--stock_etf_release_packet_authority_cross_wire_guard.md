# Stock/ETF Release Packet Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；release packet authority boundary hardening

## 結論

已補強 `stock_etf_release_packet` artifact 對 secret serialization、live/tiny-live authority、
release seal、paper-shadow window、engineering shakedown posture 的 coverage。這次只改 acceptance 與
source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、secret、
DB/evidence writer、paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `release_packet_rejects_secret_authority_window_and_seal_cross_wire_independently`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 證明 `ibkr_live_or_tiny_live_authorized=true` 只產生 `LiveOrTinyLiveAuthorityPresent`。
- 證明 `sealed=false` 只產生 `ReleasePacketNotSealed`。
- 證明 `paper_shadow_window_complete=false` 只產生 `PaperShadowWindowIncomplete`。
- 證明 `engineering_shakedown_complete=false` 只產生 `EngineeringShakedownIncomplete`。
- Python source-static guard 新增 fixture cross-wire 禁止清單，拒絕 incomplete paper-shadow window、
  incomplete engineering shakedown、secret serialization、live/tiny-live authority、unsealed posture 被
  hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_release_packet_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_release_packet_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_release_packet_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 release execution、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
