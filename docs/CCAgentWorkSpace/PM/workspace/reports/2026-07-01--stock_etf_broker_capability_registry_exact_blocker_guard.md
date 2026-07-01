# Stock/ETF Broker Capability Registry Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` read-only/paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfBrokerCapabilityRegistryV1` source-only broker operation matrix 的 aggregate
fail-closed coverage。它只改 acceptance 與 source-static guard，不改 Rust production validator、IPC/API route、
GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_broker_capability_registry_acceptance.rs` 將 default broker capability registry 固定為完整
  ordered blocker vector，覆蓋 registry/source identity、Stock/ETF lane、IBKR broker、Bybit live unchanged
  proof、Python broker write denial、IBKR live denial、CFD/margin denial、required audit fields，以及 15 個 required
  broker operations 的 missing blockers。
- 將 read-row IPC/probe gate aggregate、registry id/source mismatch、operation coverage once-only、paper write row
  shape failures、paper fill-import row shape failures、denied live/account-write row regressions、contact/secret/
  Bybit/Python-write boundary flags改成 exact ordered vectors 或 exact single-blocker vectors。
- 移除 broker capability blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對 missing、
  extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_broker_capability_registry_source_static.py` 補 validator blocker emit-order guard，pin
  registry top-level checks、operation coverage checks，以及 operation row validation 的 source order。

## Verification

- No blocker loose helper scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF broker capability registry source static pytest：`9 passed`。
- Stock/ETF broker capability registry Rust acceptance：`14 passed`。
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
- connector runtime、broker session、read-only probe execution、result/fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
