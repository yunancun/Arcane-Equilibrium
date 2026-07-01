# PM Report — Stock/ETF Release Packet Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF release packet source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_release_packet.rs` 的 source-only 姿態；不是 PASS artifact creation、不是
secret slot、不是 broker session、不是 paper order、不是 evidence clock、不是 tiny-live/live
authorization。

## Completed

- 新增 `tests/structure/test_stock_etf_release_packet_source_static.py`。
- Guard 要求 `stock_etf_release_packet.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD/spec release paths、release packet contract id、manifest hash、
  PG migration evidence、kill-disable cleanup proof、release packet/verdict/blocker surface 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：empty packet id、source_version 0、paper-shadow window
  incomplete、engineering shakedown incomplete、secret false、IBKR live/tiny-live false、sealed false。
- Guard 要求 accepted fixture 保留 exact release paths、all required roles、manifest hashes、
  no-migration fixture、kill-disable cleanup proof、evidence archive pointer/hash、paper-shadow
  window complete、engineering shakedown complete、secret false、IBKR live/tiny-live false、
  sealed=true。
- Guard 要求 PM/Operator/E2/E3/E4/QA/QC/MIT signoff mapping、role reports、E2/E3/E4/QA logs、
  manifest hashes、PG migration dry-run/double-apply evidence、redaction fixture、GUI screenshots、
  DQ manifests、scorecard regeneration hashes、kill-disable cleanup proof、evidence archive、
  paper-shadow window、engineering shakedown gates 不得消失。
- Guard 要求 secret serialization denial、IBKR live/tiny-live authority denial、release packet
  sealed requirement 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_release_packet_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_release_packet_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_release_packet_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：PASS artifact creation、secret slot、broker session、paper order、
tiny-live/live authorization、IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、DQ writer、
broker fill import、scorecard writer、DB apply、evidence writer/clock、GUI fanout、或任何
Bybit behavior change。
