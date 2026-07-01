# Stock/ETF Release Packet Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；release packet authority / lineage hardening

## 結論

已補強 `stock_etf_release_packet` 的 release identity、ADR/AMD/spec path、source timestamp、reviewer
signoff、evidence hash、migration evidence、kill-disable-cleanup proof 與 final no-live posture coverage。
這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC method、runtime、IBKR
connector、secret、DB/evidence writer、release executor、tiny-live/live gate 或 Bybit 路徑。

## 變更

- Rust acceptance 新增 `release_packet_rejects_each_identity_and_path_gap_independently`。
- Rust acceptance 新增 `release_packet_rejects_each_required_role_gap_independently`。
- Rust acceptance 新增 `release_packet_rejects_each_evidence_hash_gap_independently`。
- Rust acceptance 新增 `release_packet_rejects_each_migration_evidence_gap_independently`。
- Rust acceptance 新增 `release_packet_rejects_each_kill_disable_cleanup_gap_independently`。
- Rust acceptance 新增 `release_packet_rejects_each_final_posture_gap_independently`。
- Acceptance 證明 packet id/source version、ADR/AMD/spec path、source commit、created timestamp 可各自只
  產生單一對應 blocker。
- Acceptance 證明 PM/Operator/E2/E3/E4/QA/QC/MIT signoff 與 role report paths 可各自只產生單一對應
  blocker。
- Acceptance 證明 E2/E3/E4/QA logs、manifest、redaction fixture、GUI screenshot、DQ manifest、scorecard
  regeneration、evidence archive pointer/hash 可各自只產生單一對應 blocker。
- Acceptance 證明 migration manifest、dry-run log、double-apply log，以及 lane/readonly/paper disable、
  shadow-only preservation、collector stop、GUI disable、live-secret absence、forward-only archive、
  destructive DB cleanup denial、kill proof hash 可各自獨立阻斷。
- Acceptance 證明 paper-shadow window、engineering shakedown、secret serialization、live/tiny-live authority、
  release seal posture 可各自只產生單一對應 blocker。
- Python source-static guard 新增 impl-block parser，精準鎖住 `StockEtfReleasePacketV1::accepted_fixture`
  / `Default` 與 `StockEtfKillDisableCleanupProofV1::accepted_fixture`，避免錯抓第一個
  `accepted_fixture()` 區塊。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_release_packet_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_release_packet_source_static.py --tb=short`：`9 passed`。
- `cargo test -p openclaw_types --test stock_etf_release_packet_acceptance`：`15 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 release execution、DB/evidence writer、scorecard writer、broker session、paper order route、tiny-live/live
  authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
