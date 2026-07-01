# Stock/ETF Risk Policy Runtime Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；risk policy runtime authority boundary hardening

## 結論

已補強 `stock_etf_risk_policy` artifact 對 dormant paper/shadow posture、cash-only controls、
live-denial controls、Bybit unchanged、IBKR contact、connector runtime、secret serialization posture 的
coverage。這次只改 acceptance 與 source-static guard，不改 Rust production code、IPC method、
runtime、IBKR connector、secret、DB/evidence writer、paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `risk_policy_rejects_runtime_cash_and_authority_cross_wire_independently`。
- 證明 `enabled=true` 只產生 `RuntimeEnablementClaimed`。
- 證明 `shadow_only=false` 只產生 `ShadowOnlyPostureMissing`。
- 證明 `environment=LiveReservedDenied` 只產生 `WrongEnvironment`。
- 證明 `allow_margin=true`、`allow_short=true`、`allow_options=true`、`allow_cfd=true`、
  `allow_transfer=true`、`allow_live=true` 會各自只產生單一對應 blocker。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- 證明 `connector_runtime_started=true` 只產生 `ConnectorRuntimeStarted`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- Python source-static guard 新增 accepted fixture / source-config mapper body parser，拒絕 runtime
  enabled、non-shadow、live environment、margin/short/options/CFD/transfer/live allowance、Bybit
  changed、IBKR contact、connector runtime、secret serialization 被 hardcoded 到 accepted fixture 或
  source-config mapper，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_risk_policy_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_risk_policy_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test stock_etf_risk_policy_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 risk runtime enablement、order execution、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
