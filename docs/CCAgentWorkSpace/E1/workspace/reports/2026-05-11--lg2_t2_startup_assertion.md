# E1 報告 — LG-2 T2 Startup Pricing Binding Assertion

Date: 2026-05-11
Owner: E1
Wave: Sprint N+1 Wave 2.2 — LG-2 provider pricing binding
PA SSoT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2.4 T2
Status: IMPL DONE, pending PM commit/push

---

## 1. 任務摘要

`build_exchange_pipeline` 對 Live 路徑（Mainnet + LiveDemo）加裝 pricing
binding startup pre-check。此 gate 位於 fee-rate refresh 之後、balance fetch
與 private WS spawn 之前；任一斷言失敗即拒絕 Live pipeline spawn。

Demo / Paper 路徑不 enforce pricing assertion，但仍沿用相同 `SpawnConfig`
Interface 傳遞 `PricingConfig`，保持 callsite 對齊。

---

## 2. 修改清單

| File | Action | Note |
|---|---|---|
| `rust/openclaw_engine/src/live_spawn_assert.rs` | NEW | Pricing binding assertion Module，含 11 個 unit tests |
| `rust/openclaw_engine/src/lib.rs` | edit | export `live_spawn_assert` |
| `rust/openclaw_engine/src/startup/mod.rs` | edit | `build_exchange_pipeline` 新增 `pricing_config`，Live kind 執行 pre-check |
| `rust/openclaw_engine/src/pipeline_slot.rs` | edit | `SpawnConfig` 新增 `pricing_config` |
| `rust/openclaw_engine/src/main.rs` | edit | boot spawn 傳 per-env `RiskConfig.pricing.unwrap_or_default()` |
| `rust/openclaw_engine/src/live_auth_watcher.rs` | edit | watcher respawn 路徑讀 live risk store 的 pricing config |

---

## 3. 設計判斷

### 3.1 真實 callsite 位置

PA plan 寫到 `bybit_rest_client.rs::build_exchange_pipeline`，但真實 codebase
位置是 `rust/openclaw_engine/src/startup/mod.rs::build_exchange_pipeline`。本次以
repo 內實際 call graph 為準。

### 3.2 Module 放在 lib crate

`live_spawn_assert` 放在 `openclaw_engine` lib crate，而不是 binary-only
`startup/` 子模組。原因是 assertion tests 需要同 crate 可見性，且避免把
startup wiring 與 pricing assertion Implementation 綁死。

### 3.3 Audit log 不寫 PG

startup pre-check 發生在 DB pool 完整可用之前，不能依賴 PG audit row。失敗與
成功都走 structured tracing：

- target: `openclaw_engine::live_spawn_audit`
- pass event: `lg2_t2_pricing_assert_pass`
- fail event: `lg2_t2_pricing_assert_fail`
- timeout event: `lg2_t2_wait_first_refresh_timeout`

healthcheck `[45]` 後續負責 runtime drift detection。

---

## 4. Assertion 規則

### 4.1 wait first refresh

`wait_for_first_refresh_or_timeout(account_manager, 30s)` 確認 fee-rate path 至少
一條完成：

- Bybit API refresh 成功，或
- demo / LiveDemo fallback `seed_default_fee_rates` 成功。

30s 後 `last_fee_refresh_ms == 0` 即 `NoRefresh`，拒絕 Live spawn。

### 4.2 cache coverage

`fee_rate_count() >= 25`。低於 25 視為 symbol coverage 異常，拒絕 Live spawn。

### 4.3 per-symbol source

逐一檢查 `SYMBOLS` 的 `AccountManager::fee_source(symbol)`：

- Mainnet: 任一 symbol 非 `FeeSource::BybitApi` 即拒絕。
- LiveDemo: 若 `cold_default_acceptable_modes` 包含 `live_demo`，接受
  `DemoConservativeDefault` / `ColdDefault`；否則與 Mainnet 同嚴格。

錯誤 reason code 固定為：

- `no_refresh`
- `insufficient_symbol_coverage`
- `mainnet_non_api_source`
- `live_demo_non_api_source_when_strict`

---

## 5. 驗證

本報告建立時對應 E1 原始驗證：

- `cargo build --release -p openclaw_engine` PASS
- `cargo test --lib --release -p openclaw_engine live_spawn_assert` PASS, 11/11
- `cargo test --lib --release` PASS, 2860 passed / 0 failed / 1 ignored
- `cargo test --release --bin openclaw-engine` PASS, 58/58

PM 接手同步前追加驗證：

- `cargo test -p openclaw_types --lib` PASS, 35/35
- `cargo test -p openclaw_engine --lib` PASS, 2860 passed / 0 failed / 1 ignored
- `cargo test -p openclaw_engine --test lg3_contract` PASS, 11/11
- `cargo test --workspace --no-run` PASS
- `python3 -m pytest helper_scripts/db/test_pricing_binding_healthcheck.py helper_scripts/db/test_h0_block_acceptance.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h0_block_summary_route.py -q` PASS, 56/56

---

## 6. 殘留風險

- `apply_risk_snapshot` 仍未把 `RiskConfig.runtime.h0_shadow_mode` 推入
  `H0GateConfig.shadow_mode`；此點已由 `h0_ctor_default` ignored test 標記為
  LG1-T3 follow-up，不屬 LG-2 T2。
- `openclaw_engine` 仍有既有 warning（unused import / private interface /
  deprecated test usage），本次未擴大處理。
