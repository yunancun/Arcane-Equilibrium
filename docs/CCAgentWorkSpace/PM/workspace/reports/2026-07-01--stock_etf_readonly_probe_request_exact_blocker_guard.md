# Stock/ETF Readonly Probe Request Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` read-only/paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfIbkrReadonlyProbeRequestV1` pre-contact read-only probe request contract 的 aggregate
fail-closed coverage。它只改 acceptance 與 source-static guard，不改 Rust production validator、IPC、API route、
GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_ibkr_readonly_probe_request_acceptance.rs` 將 default readonly probe request 固定為完整 ordered
  blocker vector，覆蓋 contract/source identity、lane/broker/readonly environment、probe action、operation、
  authority scope、request/probe ids、Phase2 external-surface gate、API allowlist、secret-slot、session topology、
  session attestation、redaction/rate-limit/audit policies 與 source/raw/redacted hashes。
- 將 read-action/operation/authority/effect cross-wire、pre-contact lineage/hash aggregate、no-side-effect boundary
  regression cases 改成 exact ordered vectors。
- 保留 paper-order API action 的天然 aggregate 行為：它必須同時命中 `ProbeActionMismatch` 與
  `ApiActionNotReadAllowed`，不得被誤寫成 single-blocker。
- 移除 readonly probe request blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對
  missing、extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_ibkr_readonly_probe_request_source_static.py` 補 validator blocker emit-order guard，pin
  top-level identity、required pre-contact lineage fields 與 boundary flags 的 source order。

## Verification

- Targeted rustfmt check：PASS。
- Stock/ETF readonly probe request source static pytest：`10 passed`。
- Stock/ETF readonly probe request Rust acceptance：`10 passed`。
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
- connector runtime、broker session、read-only probe execution。
- paper order routing/cancel/replace execution、result import、scorecard writer、DB/evidence writer、evidence clock。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
