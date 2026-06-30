# Operator Summary - IBKR Stock/ETF Risk Policy Contract

Date: 2026-06-30
Status: Source checkpoint only; runtime still blocked

新增 `stock_etf_risk_policy_v1`，讓 future Stock/ETF paper/shadow 風險設定可以被
Rust machine-check，而不是只依賴文字或 loose config hash。

What changed:

- 現有 dormant `risk_config_stock_etf_paper.toml` now parses through a source
  config type and validates as cash-only paper/shadow risk policy.
- Paper IPC effect methods and broker capability paper write rows now require
  `stock_etf_risk_policy_v1`.
- Broker shadow / scorecard rows also require the risk policy gate.
- Phase 0 manifest contract list now includes `stock_etf_risk_policy_v1`.

Verification:

- Focused linked tests passed: 28 tests.
- Full `cargo test -p openclaw_types` passed: 35 unit/golden + 163
  integration/acceptance + 0 doc-tests.
- Targeted Rust format check and `git diff --check` passed.

Still not authorized:

- No IBKR contact or healthcheck.
- No secret read/create/serialization.
- No connector runtime.
- No paper order routing.
- No evidence clock or scorecard writer.
- No GUI lane authority.
- No tiny-live/live.
- No Bybit live execution behavior change.

Next hard blocker is unchanged: real secret/topology evidence plus immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact before first IBKR contact.
