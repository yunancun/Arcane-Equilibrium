# Stock/ETF Risk Policy Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` source-only risk policy acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfRiskPolicyV1` 的 aggregate fail-closed coverage。它只改 acceptance 與
source-static guard，不改 Rust production validator、API/IPC route、GUI runtime、connector、secret、DB、IBKR
runtime 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_risk_policy_acceptance.rs` 將 default risk policy fail-closed posture 改成完整 exact ordered
  blocker vector，覆蓋 contract/source/config identity、Stock/ETF lane、IBKR broker、paper/shadow posture、caps、
  cash-only controls、universe gates、cost-model gates、paper-order gates 與 Bybit boundary proof。
- 將 contract/source drift、runtime/cap/cash-only aggregate regressions、universe/cost/paper-order gate aggregate、
  Bybit/IBKR/connector/secret boundary aggregate 改成 exact ordered blocker vectors。
- 移除 risk policy acceptance 中 loose `has()` / `blockers.contains` aggregate helper usage。
- 在 `test_stock_etf_risk_policy_source_static.py` 新增 validator blocker emit-order guard，pin top-level risk
  policy checks、caps、cash-only controls、universe controls、cost-model controls、paper-order controls 與 authority
  boundary flags 的 source order。

## Verification

- No risk policy blocker `.contains()` scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF risk policy source static pytest：`7 passed`。
- Stock/ETF risk policy Rust acceptance：`9 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- API/IPC route behavior change。
- GUI runtime or view authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
