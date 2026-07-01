# PM Report — IBKR Paper Lifecycle Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR paper order lifecycle and append-only event-log source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_paper_lifecycle.rs` 的 source-only 姿態；不是 IBKR contact、不是 connector
construction、不是 paper order route、不是 lifecycle writer。

## Completed

- 新增 `tests/structure/test_ibkr_paper_lifecycle_source_static.py`。
- Guard 要求 `ibkr_paper_lifecycle.rs` 低於 800 行 governance cap。
- Guard 要求 lifecycle/event-log contract ids、event fields、event verdict/blocker
  surface、stale-state policy、restart recovery input/action、transition helpers 保持在
  source 中。
- Guard 要求 default event 仍 blocked/incomplete，accepted ack fixture 仍保留 request
  contract lineage、event sequence、append-only hashes、paper environment、submit ack
  transition、idempotency/reconciliation ids 與 raw/redacted hashes。
- Guard 要求 append-only validation 保留 genesis sequence/hash rules、event/request
  hash checks、StockEtfCash/IBKR/Paper checks、live environment denial、paper lifecycle
  operation gating、operation-transition gating、state-transition gating、raw/redacted hash
  checks。
- Guard 要求 StateUnknown recovery 只能 manual-review 或 terminal-with-evidence，denied
  events 必須有 denial reason 且不能 advance active state，stale-state policy matching
  不得消失。
- Guard 要求 restart recovery 分類保持 fail-closed：terminal evidence preserve、
  broker known + broker order id + idempotency key 才 reconcile，否則 MarkStateUnknown。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_paper_lifecycle_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_paper_lifecycle_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_paper_lifecycle_acceptance -- --nocapture`：
  `12 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
