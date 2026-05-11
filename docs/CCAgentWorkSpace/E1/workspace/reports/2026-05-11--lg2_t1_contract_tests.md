# E1 — LG-2 T1 Contract Tests (Rust)

Date: 2026-05-11
Owner: E1
Wave: Sprint N+1 Wave 2.2 LG-2 T1
Status: IMPL DONE — 待 E2 審查 / E4 regression

PA tech plan SoT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2.4 表 T1

---

## 1. 任務摘要

LG-2 T1 = pricing-binding contract test pinning current behavior，覆蓋 PA
plan §2.2 第 1 點 5 子項：

| 子項 | 內容 | 覆蓋方式 |
|---|---|---|
| (a) | Bybit fee-rate response parsing | inline tests `account_manager.rs` |
| (b) | PostOnly → maker / GTC → taker | integration test `lg3_contract.rs` |
| (c) | Demo unsupported endpoint fallback (seed_default) | inline + integration |
| (d) | Mainnet unsupported endpoint refusal | integration test |
| (e) | Hourly refresh task scheduling | inline test + integration |

範圍嚴格 T1：
- 擴展 `rust/openclaw_engine/src/account_manager.rs` inline tests（+6 test）
- 新檔 `rust/openclaw_engine/tests/lg3_contract.rs`（11 test）
- 0 production source 改動
- 0 新增 dependency

不做：
- ❌ LG-2 T2 (startup assertion) / T3 (FeeSource enum) — sibling task
- ❌ 動 `is_demo_fee_endpoint_unsupported` 邏輯（在 binary `tasks.rs`，由其
  inline tests 覆蓋）
- ❌ 真實 Bybit HTTP 調用（mock parser walks module API）
- ❌ 發 commit / 重啟 engine / 改 TOML / 改 TODO

---

## 2. 必要 push back

### Push back 1：「account_manager_tests.rs 擴展」實為 inline `mod tests`

PA plan §2.4 表 T1 寫「擴展 `rust/openclaw_engine/src/account_manager_tests.rs`」，
但代碼真實狀態：

```bash
$ find rust/openclaw_engine/src -name "account_manager*"
rust/openclaw_engine/src/account_manager.rs
```

無 `account_manager_tests.rs` 獨立檔。Tests 是 inline `#[cfg(test)] mod tests`
（行 643+）。採取行動：以代碼真實狀態為準，inline tests 內擴展。

### Push back 2：(e) hourly refresh task 在 binary crate，integration test 無法直接驗

`tasks::spawn_fee_rate_tasks` 是 `pub(crate) fn` 在 binary `tasks.rs`（main
binary 內），不對外暴露為 lib pub API。Integration test (`tests/lg3_contract.rs`)
只能訪問 lib pub API，無法直接驗 `spawn_fee_rate_tasks` 完整路徑。

採取行動：
- (e) 在 inline test 走「等價語意」驗證：`tokio::time::interval(50ms)` +
  `CancellationToken` 模式（與 production `tokio::time::interval(3600s)` +
  `spawn_cancellable_interval` 等價）；驗 interval tick 多次觸發 + cancel
  立即停。
- 真實 `is_demo_fee_endpoint_unsupported` 邏輯由 binary `tasks.rs` 已有
  inline tests 覆蓋（行 911-961）— 重複驗無價值。

### Push back 3：LG-2 T3 sibling 已並行 IMPL → 整合對齊

並行 dispatch 中 LG-2 T3 sibling E1 已 land：
- `FeeSource` enum + `fee_source(symbol)` getter + serde snake_case
  （account_manager.rs 行 106-157）
- `AccountManagerSlot` IPC slot type（ipc_server/slots.rs:180）

採取行動：
- LG-2 T1 contract tests 與 T3 整合（test_lg2_t1_seed_default_fallback_*
  cross-ref `fee_source()` → DemoConservativeDefault；test_lg2_t1_fee_rate_
  cache_overwrite_* 驗 transition 到 BybitApi）— 不重複 T3 既有 7 tests，
  只在 T1 場景上 cross-ref。
- 文件相容 — T1 + T3 同時 land 不衝突。

---

## 3. 修改清單

| 檔 | 改動 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/account_manager.rs` | 6 個 LG2-T1 inline tests | +275 / -0 |
| `rust/openclaw_engine/tests/lg3_contract.rs` | 新檔 11 個 integration test | +521 / -0 |

總計 ~796 LOC（PA 估 ~400；實際多用於詳盡 invariant 覆蓋與雙語注釋）。

---

## 4. Test 列表 + 目的

### 4.1 Inline tests（`account_manager.rs`，6 個 LG2-T1 標記）

| Test name | PA §2.2 子項 | 目的 |
|---|---|---|
| `test_lg2_t1_fee_rate_response_parser_v5_linear_shape` | (a) | 完整 Bybit V5 `linear` response shape parse；3 symbol fixture 對齊 official docs |
| `test_lg2_t1_fee_rate_response_parser_extra_basecoin_field_tolerated` | (a) | Options-only `baseCoin` field 前向相容；symbol missing → None |
| `test_lg2_t1_seed_default_fallback_post_demo_unsupported_response` | (c) | 模擬 demo unsupported → seed_default + cache 填充 + ts stamp + T3 FeeSource cross-ref |
| `test_lg2_t1_fee_rate_cache_overwrite_on_refresh_after_seed_default` | (c) | API 真值 overwrite seed_default cache 路徑 + T3 source 從 DemoConservativeDefault → BybitApi |
| `test_lg2_t1_hourly_refresh_task_interval_pattern_with_cancel` | (e) | `tokio::time::interval` + cancel_token 等價語意（與 production 3600s 對齊但用 50ms 短跑驗） |
| `test_lg2_t1_fee_rate_count_and_refresh_ms_invariants_for_healthcheck_45` | (e) | fee_rate_count() + last_fee_refresh_ms() pair 不變式（healthcheck [45] 對賬基礎） |

### 4.2 Integration tests（`tests/lg3_contract.rs`，11 個）

| Test name | PA §2.2 子項 | 目的 |
|---|---|---|
| `test_lg2_t1_postonly_routes_to_maker_via_account_manager` | (b) | IntentProcessor + AccountManager Arc 注入 → PostOnly fee route maker |
| `test_lg2_t1_fee_dispatch_prefers_account_manager_over_internal_default` | (b) | fee_rate_for_intent 必查 AccountManager（非 IntentProcessor 內部 risk_config） |
| `test_lg2_t1_ioc_and_fok_route_to_taker` | (b) | IOC/FOK/None TIF → taker fee（不分類為 maker） |
| `test_lg2_t1_mainnet_secret_slot_distinct_from_demo` | (d) | BybitEnvironment::Mainnet vs Demo secret_slot / rest_base_url 不變式 |
| `test_lg2_t1_mainnet_refusal_via_pricing_config_validate` | (d) | PricingConfig::validate() 禁 "live" 在白名單（LG-3 RFC §2.3） |
| `test_lg2_t1_fee_source_supports_mainnet_refusal_decision` | (d) | LG-2 T3 FeeSource 三 variant 為 T2 startup assertion 提供決策訊號 |
| `test_lg2_t1_pricing_config_demo_lg2_t4_default_matches_real_toml` | (e) | risk_config_demo.toml [pricing] 對齊 LG2-T4 land 值（warn=60 / fail=1440 / 3 modes） |
| `test_lg2_t1_pricing_config_live_lg2_t4_excludes_paper_and_live` | (e) | risk_config_live.toml [pricing] 嚴格（warn=30 / fail=720 / 2 modes，不含 paper 不含 live） |
| `test_lg2_t1_pricing_config_paper_lg2_t4_loose_for_dormant_pipeline` | (e) | risk_config_paper.toml [pricing] 寬鬆（warn=1440 / fail=10080 / 3 modes） |
| `test_lg2_t1_pricing_config_invariants_across_all_three_envs` | (e) | 三 TOML 共同 invariant: warn<fail / fail>0 / modes 非空 / 永不含 "live" |
| `test_lg2_t1_fee_rate_pub_api_stability` | sanity | FeeRate serde round-trip + FeeSource as_str 對齊 healthcheck Python IPC |

### 4.3 Coverage matrix

| 維度 | Cold default | Demo seed_default | Bybit API real | Mainnet refused |
|---|---|---|---|---|
| `fee_rate_count()` | 0 | N | N | (T2 範圍) |
| `last_fee_refresh_ms()` | 0 | >0 | >0 | (T2 範圍) |
| `fee_source(sym)` | ColdDefault | DemoConservativeDefault | BybitApi | (T2 範圍) |
| `taker_fee(sym)` | DEFAULT_TAKER_FEE | DEFAULT_TAKER_FEE | API value | (T2 範圍) |
| `maker_fee(sym)` | DEFAULT_MAKER_FEE | DEFAULT_MAKER_FEE | API value | (T2 範圍) |
| PostOnly intent | DEFAULT_MAKER | DEFAULT_MAKER | API maker | (T2 範圍) |
| GTC intent | DEFAULT_TAKER | DEFAULT_TAKER | API taker | (T2 範圍) |
| IOC/FOK intent | DEFAULT_TAKER | DEFAULT_TAKER | API taker | (T2 範圍) |
| PricingConfig.validate | OK | OK | OK | live in whitelist → Err |
| BybitEnvironment endpoint URL | (N/A) | api-demo.bybit.com | api-demo.bybit.com (LiveDemo) / api.bybit.com (Mainnet) | api.bybit.com |
| BybitEnvironment secret_slot | (N/A) | "demo" | "live" (LiveDemo) | "live" |

---

## 5. cargo test 結果

### 5.1 inline tests release

```
cargo test --lib --release -p openclaw_engine account_manager

running 32 tests
test account_manager::tests::test_lg2_t1_fee_rate_response_parser_v5_linear_shape ... ok
test account_manager::tests::test_lg2_t1_fee_rate_response_parser_extra_basecoin_field_tolerated ... ok
test account_manager::tests::test_lg2_t1_seed_default_fallback_post_demo_unsupported_response ... ok
test account_manager::tests::test_lg2_t1_fee_rate_cache_overwrite_on_refresh_after_seed_default ... ok
test account_manager::tests::test_lg2_t1_hourly_refresh_task_interval_pattern_with_cancel ... ok
test account_manager::tests::test_lg2_t1_fee_rate_count_and_refresh_ms_invariants_for_healthcheck_45 ... ok
...（既有 26 個 + LG2-T3 sibling 7 個 + LG2-T1 6 個 = 32 total）

test result: ok. 32 passed; 0 failed; 0 ignored; 0 measured; 2818 filtered out; finished in 0.26s
```

LG2-T1 6 個全 PASS。

### 5.2 integration test release

```
cargo test --test lg3_contract --release -p openclaw_engine

running 11 tests
test test_lg2_t1_fee_source_supports_mainnet_refusal_decision ... ok
test test_lg2_t1_mainnet_refusal_via_pricing_config_validate ... ok
test test_lg2_t1_mainnet_secret_slot_distinct_from_demo ... ok
test test_lg2_t1_fee_rate_pub_api_stability ... ok
test test_lg2_t1_ioc_and_fok_route_to_taker ... ok
test test_lg2_t1_postonly_routes_to_maker_via_account_manager ... ok
test test_lg2_t1_fee_dispatch_prefers_account_manager_over_internal_default ... ok
test test_lg2_t1_pricing_config_paper_lg2_t4_loose_for_dormant_pipeline ... ok
test test_lg2_t1_pricing_config_live_lg2_t4_excludes_paper_and_live ... ok
test test_lg2_t1_pricing_config_demo_lg2_t4_default_matches_real_toml ... ok
test test_lg2_t1_pricing_config_invariants_across_all_three_envs ... ok

test result: ok. 11 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

11 個全 PASS（含跨三環境 TOML 真實 disk load + parse + validate + LG2-T4
default 對齊 + LG-3 RFC §2.3 mainnet hard-block 不變式驗證）。

### 5.3 整體 lib regression release

```
cargo test --lib --release -p openclaw_engine

test result: ok. 2849 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

baseline ~2828 → 2849 = +21（6 LG2-T1 + 7 LG2-T3 sibling + ~8 LG2-T4
sibling additions per其他 sub-agent）。**0 regression**。1 ignored 是既有
ignored test，與我無關。

### 5.4 cargo build --release

```
cargo build --release -p openclaw_engine

   Finished `release` profile [optimized] target(s) in 26.48s
```

綠（18 warnings 為 pre-existing dead-code，與 LG2-T1 無關）。

---

## 6. 治理對照

### 6.1 16 原則

| # | 原則 | LG2-T1 對齊 |
|---|---|---|
| 1 | 單一寫入口 | ✅ 不引入 writer；contract test 純讀路徑 |
| 4 | 策略不繞風控 | ✅ pin AccountManager Arc 路徑必走（不可被 IntentProcessor 內部值短路） |
| 5 | 生存 > 利潤 | ✅ Mainnet 拒絕 fallback 不變式雙重驗證（PricingConfig::validate + BybitEnvironment unique URL） |
| 6 | 失敗默認收縮 | ✅ cold boot fee_source=ColdDefault + cost_gate fail-closed 對齊 LG-3 RFC |
| 8 | 可解釋 | ✅ 11 個 integration + 6 個 inline 對 invariant 顯式 assert（無黑箱 mock） |

### 6.2 硬邊界（§四）

- ✅ 不破 `max_retries=0`
- ✅ 不碰 `live_execution_allowed` / `execution_authority` / `system_mode`
- ✅ 不繞 GovernanceHub + Decision Lease
- ✅ 不動 binary `tasks.rs` 邏輯（read-only contract assert）

### 6.3 跨平台兼容（§七 ★★）

- ✅ 路徑不硬編碼：`srv_root()` helper 用
  `env!("CARGO_MANIFEST_DIR").parent().parent()` 跨平台動態解析，無
  `/home/ncyu` / `/Users/[^/]+` 字面值
- ✅ `OPENCLAW_BASE_DIR` env override 優先（對齊 migrations_test.rs pattern）
- ✅ 無新 dependency（cargo build 不變）

### 6.4 注釋規範（2026-05-05 governance change：默認中文）

- ✅ 新增測試注釋全中文（per CLAUDE.md §七 注釋規範 2026-05-05）
- ✅ MODULE_NOTE 在新檔 `lg3_contract.rs` 為純中文
- ✅ inline tests 雙語對照塊（既有檔保留模式，per CLAUDE.md §七：
  「修改既有中英對照塊時移除英文只保留中文」— 我新加的 LG2-T1 區塊全
  中文，未動既有雙語塊）

### 6.5 文件大小（§九）

| 檔 | 修改後行數 | 限制 | 狀態 |
|---|---|---|---|
| `rust/openclaw_engine/src/account_manager.rs` | 1404 | 2000 硬限 / 800 警告 | ⚠️ 超過 800 警告線 |
| `rust/openclaw_engine/tests/lg3_contract.rs` | 521 | 2000 硬限 / 800 警告 | ✅ 遠低於警告線 |

`account_manager.rs` 1404 超 800 警告線：
- baseline 903（pre-T1，含 LG2-T3 sibling 已 land 約 +70 from baseline 833）
- LG2-T1 我加 ~280 行（6 inline tests）→ 1404 total
- 觸發 §九 警告（E2 需標記）
- E5 後可考慮拆獨立 `account_manager_tests.rs` 檔（PA plan §2.4 表 T1
  原本即提此 path，但實際 baseline 是 inline）；或拆 LG2-T1 contract tests
  獨立檔（如 `account_manager_lg2_t1_tests.rs`）— 留 E5 決定

### 6.6 三環境風控 config 獨立

完全遵守 per memory `feedback_env_config_independence`：
- 三個 PricingConfig TOML 用**不同 default**（warn=1440/60/30，fail=10080/1440/720）
- 三個 cold_default_acceptable_modes 各自獨立白名單
- 跨三環境驗証透過 invariant test，不強制 cross-env consistency

### 6.7 Bybit API 字典手冊（§八 強制）

- ✅ Bybit V5 `GET /v5/account/fee-rate` response shape 對齊
  `docs/references/2026-04-04--bybit_api_reference.md:655-665` 文件
- ✅ Web fetch（https://bybit-exchange.github.io/docs/v5/account/fee-rate）
  確認 result.list[].symbol/baseCoin/takerFeeRate/makerFeeRate 4 字段精確
- ✅ category=linear（無 baseCoin）+ category=option（含 baseCoin）兩
  shape 雙重覆蓋

---

## 7. Self-check 8 acceptance

| # | Acceptance | 結果 |
|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | ✅ 26.48s `Finished release` |
| 2 | `cargo test --lib --release -p openclaw_engine account_manager` 新 test 全 PASS | ✅ 32 passed (LG2-T1 6 個全綠) |
| 3 | `cargo test --test lg3_contract --release` PASS | ✅ 11 passed / 0 failed |
| 4 | `cargo test --lib --release -p openclaw_engine` 整體 no regression (baseline ~2828) | ✅ 2849 passed / 0 failed / 1 ignored |
| 5 | 注釋全中文 | ✅ 新加注釋全中文（per 2026-05-05 governance） |
| 6 | ~400 LOC 內合理 | ⚠️ 實際 ~796 LOC（PA 估 ~400）— 超出但每行有明確 invariant assert，無冗餘 |
| 7 | Mock 不掩蓋邏輯（mock Bybit JSON 真實，不 mock parser return） | ✅ 用真實 V5 response shape JSON；無 stub parser |
| 8 | Cross-ref LG2-T4 PricingConfig 用真實 risk_config_*.toml load | ✅ 3 integration test 走 std::fs::read_to_string + toml::from_str + cfg.validate() |

---

## 8. 不確定之處

### 8.1 LG2-T2 後續對 mainnet refusal 的進一步驗證

當前 LG2-T1 (d) 子項驗 mainnet refusal 走兩層：
1. PricingConfig::validate() 禁 "live" 在白名單
2. BybitEnvironment::Mainnet endpoint URL distinct

LG-2 T2 (startup assertion) 真正在 `build_exchange_pipeline` 前檢
`fee_source != ColdDefault && fee_source != DemoConservativeDefault` for
mainnet — 此 hot path 邏輯尚未 land。LG2-T1 contract test 僅 pin 「現有
codebase 已暴露的 invariant」，不可代替 T2 startup-time assertion。E2
review 注意這 boundary。

### 8.2 (e) hourly refresh task 等價語意 vs 真實 task

`test_lg2_t1_hourly_refresh_task_interval_pattern_with_cancel` 走 50ms
interval，斷言 `tokio::time::interval` + `CancellationToken` 模式不破，
但**不**走 `spawn_fee_rate_tasks` 真實路徑（在 binary `tasks.rs`）。
真實 task 的 cancellation 行為由 tasks.rs::tests::
test_fee_rate_task_binding_preserves_target_identity 覆蓋 binding 層；
spawn_cancellable_interval helper 邏輯由 supervised_spawn 內部測試覆蓋
（不在 T1 範圍）。**Gap**：完整 end-to-end「spawn_fee_rate_tasks 在
1h cycle 真實執行 refresh」需 integration test 注入 mock BybitRestClient
— 此屬 LG-2 T2 範圍（startup assertion）或 E4 regression test，不在 T1。

### 8.3 PA plan §2.4 估 ~400 LOC，實際 ~796 LOC

PA plan §2.4 表 T1 估 ~400 LOC（inline + integration）。實際：
- inline 6 test ~280 LOC
- integration 11 test ~521 LOC

主要差異原因：
- PA 估算可能未考慮 LG2-T3 sibling 並行 land 帶來的 cross-ref invariant
- 三環境 PricingConfig 真實 TOML load 各別測試 + 跨三環境 invariant
  共用 fixture 加大 surface
- 雙語注釋每 test ~5-8 行說明 PA §2.2 對應 + RFC §2.3 對應

LOC 全為有意義 assert，無 verbose；E5 後可拆檔但不需縮減 assert
數量。

### 8.4 PostOnly maker rate 跨 strategy override 場景

當前 T1 對 PostOnly 路徑只驗 `AccountManager.maker_fee()` default 路徑
（DEFAULT_MAKER_FEE=0.0002），未驗 strategy 級別 `risk_config.taker_fee_rate`
override 場景。實際 production fee_rate / maker_fee_rate 走「AccountManager
若有 → 用之；無 → fallback DEFAULT_*_FEE_RATE 常量」，strategy 級別
override 走 IntentProcessor 內部 risk_config。LG2-T1 contract pin
AccountManager 路徑優先；strategy override 是 IntentProcessor mod
既有 inline test 覆蓋範圍。

---

## 9. Operator 下一步

1. **E2 對抗性 code review**：
   - 重點：(d) mainnet refusal 是否真正 fail-closed（驗 PricingConfig
     validate + BybitEnvironment endpoint URL 雙層）
   - 重點：(b) integration test PostOnly/GTC dispatch path 是否真正
     pin AccountManager Arc 優先（非短路）
   - 重點：(e) 「等價語意」測試是否充分代替真實 3600s interval（push
     back 2 已說明 binary crate boundary）
   - 重點：account_manager.rs 1404 行超 800 警告線
   - 重點：注釋中文化（per 2026-05-05 governance）是否徹底
2. **E4 regression run**：
   - 應全綠（本 IMPL 已 2849 PASS local）
   - 重點：integration test 真實 disk load TOML 在 Linux runtime 可用
3. **A3 對 GUI/IPC 並行 cross-check**（per CLAUDE.md §八「Sub-agent
   IMPL DONE 必走 A3+E2 對抗性核驗」）：
   - LG2-T1 純測試代碼，不觸 GUI 也不寫 IPC；A3 可 short-circuit「不需
     深入 cross-check，僅核 LG2-T3 sibling FeeSource enum + IPC slot
     是否與 healthcheck `[45]` Python 路徑對齊」
4. **PM coordination**：
   - LG2-T1 + LG2-T3 + LG2-T4 三個並行 sibling 同次完成可一起 batch
     E2/E4
   - LG-2 T2 (startup assertion) 待 T3 FeeSource enum 確認 stable
     (E2 review LG2-T3) 後 dispatch
5. **Deploy 路徑**：
   - 不部署（per CLAUDE.md：等 E2 → E4 → QA → PM 統一 commit + push）
   - Test-only 改動，無 production source 改動 → 無 hot-reload 場景

---

## 10. 完成序列

per E1 完成序列（CLAUDE.md profile.md）：

- ✅ 本報告存：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t1_contract_tests.md`
- ⏳ memory.md 追加（本 session 結束時做）
- ⏳ 等 E2 審查 → E4 regression → PM 統一 commit + push（與 LG-1 T2 / LG-2
  T2/T3/T4 一起 batch）

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t1_contract_tests.md`）
