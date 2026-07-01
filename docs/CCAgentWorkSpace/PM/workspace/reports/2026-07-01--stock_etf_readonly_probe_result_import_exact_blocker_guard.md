# Stock/ETF Readonly Probe Result Import Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` read-only/paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfIbkrReadonlyProbeResultImportRequestV1` sanitized read-only probe result-import request
contract 的 aggregate fail-closed coverage。它只改 acceptance 與 source-static guard，不改 Rust production
validator、IPC、API route、GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_ibkr_readonly_probe_result_import_request_acceptance.rs` 將 default result-import request 固定為
  完整 ordered blocker vector，覆蓋 contract/source identity、lane/broker/environment、probe action、operation、
  authority scope、API read allowlist、result-import/request/probe ids、readonly probe request、session
  attestation、API allowlist、redaction/audit policies、payload/raw/redacted/source hashes、timestamps、
  idempotency 與 health snapshot hash。
- 將 read-action/operation cross-wire、common lineage/hash/timestamp aggregate、kind-specific downstream lineage、
  duplicate/stale replay、no-side-effect boundary regression cases 改成 exact ordered vectors。
- 保留 paper-order API action 與 missing import timestamp 的天然 aggregate 行為：paper action 必須同時命中
  `ProbeActionMismatch` 與 `ApiActionNotReadAllowed`；`import_requested_at_ms=0` 必須同時命中
  `ImportRequestedAtMissing` 與 `ResultAsOfAfterImportRequested`。
- 移除 result-import request blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對
  missing、extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py` 補 validator blocker emit-order
  guard，pin top-level identity、required lineage、kind-specific lineage 與 boundary flags 的 source order。

## Verification

- Targeted rustfmt check：PASS。
- Stock/ETF readonly probe result-import source static pytest：`12 passed`。
- Stock/ETF readonly probe result-import Rust acceptance：`11 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- IPC/API route behavior change。
- GUI runtime or lane selector authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、result import execution。
- evidence writer、scorecard writer、DB apply。
- paper order routing/cancel/replace execution。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
