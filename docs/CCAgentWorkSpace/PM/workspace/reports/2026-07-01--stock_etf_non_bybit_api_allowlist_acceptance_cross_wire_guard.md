# Stock/ETF Non-Bybit API Allowlist Acceptance Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；non-Bybit API allowlist acceptance hardening

## 結論

已補強 `NonBybitApiAllowlistV1` artifact 對 read / paper-write / denied action bucket、Client Portal
Web API denial、live/account-transfer/margin-short-options-CFD / market-data entitlement /
account-management write denial、IBKR contact、secret serialization、Bybit live protection posture 的
coverage。這次只新增 acceptance 與 source-static guard，不改 Rust production code、IPC method、
runtime、IBKR connector、Client Portal Web API、secret、broker routing、paper order route 或
tiny-live/live authority。

## 變更

- Rust acceptance 新增 `ibkr_non_bybit_api_allowlist_acceptance.rs`。
- 證明 default allowlist 在 contact 前 fail closed，且包含 contract/source/action/denial/Bybit blocker。
- 證明 accepted fixture pin 住 required action matrix、contract id、source version、no contact、no
  secret、Bybit live execution protected。
- 證明 `ServerTimeRead`、`AccountSummarySnapshotRead`、`PaperOrderSubmit`、`LiveOrderSubmit`、
  `ClientPortalWebApiUse` 的 allow/deny classification semantics。
- 證明 missing action、duplicated action、wrong bucket action 都會被 validator 拒絕。
- 證明 Client Portal Web API、live order、account transfer、margin/short/options/CFD、
  market-data entitlement purchase、account-management write denial 缺失都會各自只產生單一 blocker。
- 證明 IBKR contact、secret serialization、Bybit live execution protection loss 都會各自只產生單一 blocker。
- Python source-static guard 新增 accepted fixture body parser，拒絕 empty action buckets、false denial
  booleans、IBKR contact、secret serialization、Bybit protection loss 被 hardcoded 到 accepted fixture，
  並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_non_bybit_api_allowlist_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test ibkr_non_bybit_api_allowlist_acceptance`：`4 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## Workflow Note

本 checkpoint 原則上屬 `PM -> E1 -> E2 -> E4 -> PM` 的窄範圍 source/test hardening；但當前 Codex
multi-agent 工具政策要求只有 operator 明確要求 sub-agent / delegation 時才可 spawn。PM 因此未另行
spawn E2/E4，改以 focused local checks 覆蓋 regression surface，並在本報告明確揭露。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 Client Portal Web API enablement、broker routing、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
