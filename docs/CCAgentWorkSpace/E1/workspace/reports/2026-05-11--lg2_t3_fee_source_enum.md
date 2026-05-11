# E1 IMPLEMENTATION — LG-2 T3 FeeSource enum + IPC route + healthcheck dual-source

Date: 2026-05-11
Owner: E1
Wave: Sprint N+1 Wave 2.2 (LG-2 T3)
PA tech plan: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2.4 (LG2-T3)
Status: DONE — awaiting E2 review

---

## 1. 任務性質

PA tech plan §2.4 LG-2 T3 (Mix Rust + Python)，3 個 surface 同次 ship：

| Surface | File | LOC 增 |
|---|---|---|
| FeeSource enum + getter (Rust) | `rust/openclaw_engine/src/account_manager.rs` | ~140 (含 7 tests) |
| 新 IPC handler (Rust) | `rust/openclaw_engine/src/ipc_server/handlers/fee_source.rs` | ~200 (含 4 tests) |
| IPC wiring (Rust) | `slots.rs` / `server.rs` / `connection.rs` / `dispatch.rs` / `handlers/mod.rs` / `main.rs` | ~50 |
| healthcheck [45] dual-source (Python) | `helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py` | ~150 (含 helpers) |
| Python tests | `helper_scripts/db/test_pricing_binding_healthcheck.py` | ~190 (含 9 new tests) |
| Rust test plumbing (47 既有 callsite + 6 import) | `rust/openclaw_engine/src/ipc_server/tests/*.rs` | ~50 |

序列依賴：T3 先 → T2 startup assertion 後 ─ T2 IMPL 依賴本 T3 的 `FeeSource` 公開 API 與
`AccountManager::fee_source()` getter。

---

## 2. Part A — Rust：FeeSource enum + getter

### 2.1 enum 定義
`account_manager.rs:106-157`：

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeeSource {
    BybitApi,
    DemoConservativeDefault,
    ColdDefault,
}

impl FeeSource {
    pub fn as_str(self) -> &'static str { /* snake_case 字串 */ }
    pub fn is_compatible_with_proxy(self, pg_proxy_source: &str) -> bool { /* dual-source compat */ }
}
```

字串對齊 PA §2.5 risk #5：`bybit_api / demo_conservative_default / cold_default`。

### 2.2 `AccountManager::fee_source(symbol)` getter
`account_manager.rs:421-451`，4 條 rule：

1. `last_fee_refresh_ms == 0` → `ColdDefault`（從未 refresh）
2. cache 無 symbol → `ColdDefault`（symbol 未涵蓋）
3. cache 有 + `maker_fee_rate == DEFAULT_MAKER_FEE && taker_fee_rate == DEFAULT_TAKER_FEE`
   → `DemoConservativeDefault`（seed_default_fee_rates 注入，直接賦常量無浮點誤差，
   故可精確比對 `==`）
4. 否則 → `BybitApi`

### 2.3 `is_compatible_with_proxy` 雙語對賬表
對齊 Python 端 `checks_pricing_binding.py:_infer_source` 字串集：

| Rust enum | PG proxy | Compatible? |
|---|---|---|
| `BybitApi` | `bybit_v5` | ✅ |
| `DemoConservativeDefault` | `seed_default` | ✅ |
| `ColdDefault` | `cold_default` | ✅ |
| (任一) | `inactive_mainnet` | ✅（OPENCLAW_ALLOW_MAINNET 未啟用標記）|
| 其他 | (其他) | ❌ |

### 2.4 Unit tests (7 個)
- `test_fee_source_cold_default_when_never_refreshed`：rule 1
- `test_fee_source_cold_default_when_symbol_missing`：rule 2
- `test_fee_source_demo_conservative_default_when_both_match`：rule 3
- `test_fee_source_bybit_api_when_real_rates_cached`：rule 4 + boundary（單邊 default）
- `test_fee_source_as_str_alignment`：字串對齊契約
- `test_fee_source_serde_snake_case`：serde JSON wire format
- `test_fee_source_compatible_with_proxy`：dual-source 字典

---

## 3. Part B — IPC route `query_fee_source`

### 3.1 新增 handler file
`rust/openclaw_engine/src/ipc_server/handlers/fee_source.rs` (~200 LOC，含 4 tests)。

對齊 cost_edge_advisor / h_state slot-based read-only pattern：

```rust
pub(in crate::ipc_server) async fn handle_query_fee_source(
    id: serde_json::Value,
    params: &serde_json::Value,
    account_manager_slot: &AccountManagerSlot,
) -> JsonRpcResponse
```

### 3.2 Request/Response shape

```
request  = {"jsonrpc":"2.0","method":"query_fee_source",
            "params":{"symbol":"BTCUSDT"},"id":N}
response = {"jsonrpc":"2.0","result":{
              "status":"ok"|"uninitialized"|"invalid_params",
              "symbol":"BTCUSDT",
              "fee_source":"bybit_api"|"demo_conservative_default"|"cold_default",
              "last_refresh_ms":1700000000000,
              "fee_rate_count":25
           },"id":N}
```

絕不爆 JSON-RPC error；slot=None / params 缺欄位 → structured payload。

### 3.3 wiring
- `slots.rs`：新 `AccountManagerSlot = Arc<RwLock<Option<Arc<AccountManager>>>>`
- `server.rs`：新 field + init + `account_manager_slot()` getter + accept-loop clone
- `connection.rs`：簽名加 `account_manager_slot: AccountManagerSlot`
- `dispatch.rs`：簽名加 `account_manager_slot: &AccountManagerSlot` + 新 route arm
- `handlers/mod.rs`：`mod fee_source` + re-export `handle_query_fee_source`
- `main.rs`：
  - L529：detach 前取 `account_manager_slot_handle = ipc_server.account_manager_slot()`
  - L573：main_instruments 後 `account_manager_slot_handle.write().await.replace(am)`

### 3.4 Unit tests (4 個)
- `query_uninjected_returns_uninitialized_shape`：slot=None payload contract
- `query_missing_symbol_returns_invalid_params_shape`：params 缺 symbol fail-soft
- `query_cold_default_when_never_refreshed`：AM 注入但 refresh ts=0
- `query_demo_conservative_default_after_seed`：seed 注入後正確回 enum 值

---

## 4. Part C — Python healthcheck [45] dual-source compare

### 4.1 既有 [45] 不變
`checks_pricing_binding.py:check_45_pricing_binding` 主流程（PG proxy 推斷 +
3 RFC fail-closed rule + per-mode summary）一字不動。

### 4.2 新增 dual-source compare 模組
- 常量：`DUAL_SOURCE_ENV_VAR / DUAL_SOURCE_PROBE_SYMBOL / DUAL_SOURCE_IPC_TIMEOUT_SECONDS`
- Rust enum 字串集鏡像：`RUST_FEE_SOURCE_BYBIT_API` 等 3 常量
- compat 字典 `_FEE_SOURCE_COMPAT`（dict[str, set[str]]）
- `_is_rust_pg_source_compatible(rust_enum, pg_proxy) -> bool`：對賬 helper

### 4.3 IPC 呼叫 helper
`_query_rust_fee_source(symbol) -> dict | None`：lazy import
`ipc_client_sync.sync_ipc_call` 走 `OPENCLAW_IPC_SOCKET` (默認 `/tmp/openclaw/engine.sock`)。
任何錯誤（FileNotFoundError / timeout / auth fail / engine 未跑）一律 fail-soft 回 `None` —
dual-source compare 是 advisory，**永不阻 healthcheck**。

### 4.4 主流程整合
`_dual_source_compare(per_mode) -> (disagree, summary_str)`：
- env-gated（`OPENCLAW_LG2_T3_DUAL_SOURCE=1`），預設關
- IPC 不可用 → `(False, "dual_source=ipc_unavailable")` fail-soft
- PG canonical：demo → live_demo → live 優先序取首個非 `cold_default` 的 source
- disagree → `(True, summary)`：升 PASS→WARN（**首階段不升 FAIL** per PA §2.5 risk #4）

verdict 整合（`check_45_pricing_binding` 末尾，前置於 PASS/WARN/FAIL 分支）：

```python
ds_disagree, ds_summary = _dual_source_compare(per_mode)
if ds_disagree and worst == "PASS":
    worst = "WARN"
    warn_reasons.append("LG-2 T3 dual_source disagree (...); 首階段升 WARN 不 FAIL（2 週觀察期）")
```

### 4.5 Python tests (9 new)

| Test class | Test name | Coverage |
|---|---|---|
| `TestLg2T3DualSourceCompat` | `test_bybit_api_compatible_with_bybit_v5` | 字典正常 path |
| | `test_demo_conservative_default_compatible_with_seed_default` | 字典正常 path |
| | `test_cold_default_compatible_with_cold_default` | 字典正常 path |
| | `test_inactive_mainnet_compatible_with_all_enum` | `inactive_mainnet` 特殊 |
| | `test_disagree_cases` | 跨類 disagree + 未知 enum fail-closed |
| `TestLg2T3DualSourceWarn` | `test_dual_source_disagree_promotes_pass_to_warn` | 端對端 WARN 升級 |
| | `test_dual_source_compat_no_verdict_change` | 相容時 verdict 不變但 summary 含 dual_source |
| | `test_dual_source_ipc_unavailable_fail_soft` | IPC FileNotFoundError fail-soft |
| | `test_dual_source_disabled_by_default` | env 未設不執行（向後相容） |

---

## 5. Unit test 結果

### 5.1 Rust
```bash
cd srv/rust && cargo test --release -p openclaw_engine --lib fee_source
# 11 passed; 0 failed; 0 ignored

cd srv/rust && cargo test --release -p openclaw_engine --lib
# 2849 passed; 0 failed; 1 ignored
```

### 5.2 Python
```bash
cd srv && python3 -m pytest helper_scripts/db/test_pricing_binding_healthcheck.py -v
# 21 passed (12 existing + 9 new dual-source)
```

### 5.3 Build
```bash
cd srv/rust && cargo build --release -p openclaw_engine
# Finished `release` profile [optimized] target(s) in 25.36s
```

---

## 6. 關鍵 diff

### account_manager.rs (Rust)
- 加 `pub enum FeeSource { BybitApi, DemoConservativeDefault, ColdDefault }`
  - `#[serde(rename_all = "snake_case")]`
  - `as_str()` + `is_compatible_with_proxy(pg_proxy)`
- 加 `impl AccountManager { pub fn fee_source(&self, symbol: &str) -> FeeSource }`
- 加 7 unit tests in `mod tests`

### IPC server (Rust)
- `slots.rs`：新 `pub type AccountManagerSlot = Arc<RwLock<Option<Arc<AccountManager>>>>`
- `server.rs`：IpcServer 新 field + init + accessor + accept-loop clone
- `connection.rs`：handle_connection 簽名加 `account_manager_slot: AccountManagerSlot`
- `dispatch.rs`：dispatch_request 簽名加 `account_manager_slot: &AccountManagerSlot` +
  新 `"query_fee_source" => handle_query_fee_source(...)` arm
- `handlers/mod.rs`：`mod fee_source` + `pub(in crate::ipc_server) use fee_source::handle_query_fee_source`
- `handlers/fee_source.rs`：**新檔**，~200 LOC 含 4 unit tests
- `main.rs`：L529 取 slot handle / L573 main_instruments 後注入

### Python (checks_pricing_binding.py)
- 加 module-level `import os`（移除 `_mainnet_live_enabled` 內 lazy import）
- 加 dual-source 8 常量（DUAL_SOURCE_ENV_VAR 等）
- 加 `_is_rust_pg_source_compatible` helper
- 加 `_dual_source_enabled / _query_rust_fee_source / _dual_source_compare` 3 函數
- `check_45_pricing_binding` 主流程末尾插入 dual-source compare（前置於 PASS/WARN/FAIL 分支）

### Python tests (test_pricing_binding_healthcheck.py)
- 加 5 新 import（`DUAL_SOURCE_ENV_VAR / RUST_FEE_SOURCE_* / _is_rust_pg_source_compatible`）
- 加 `TestLg2T3DualSourceCompat`（5 tests）
- 加 `TestLg2T3DualSourceWarn`（4 tests）

### Test plumbing (46+1 callsite 批量更新)
- `ipc_server/tests/mod.rs`：新 `empty_account_manager_slot() -> AccountManagerSlot` helper
- 6 `tests/*.rs` 檔 import + 46 個 dispatch_request callsite 加 `&empty_account_manager_slot()`
  arg（Python regex 批量替換）

---

## 7. 治理對照

### CLAUDE.md §二 16 原則 compliance
- ✅ **#2 讀寫分離**：IPC handler 純讀 `RwLock::read()`，無 cache write / refresh ts 修改
- ✅ **#8 可解釋**：dual-source disagree 寫入 healthcheck output 完整 summary，
  可重建判斷依據
- ✅ **#11 Agent 最大自主**：不削弱 agent 能力，純增 observability surface

### CLAUDE.md §四 硬邊界
- ✅ 不碰 max_retries / live_execution_allowed / system_mode
- ✅ 不破 IPC contract（純加 method，既有 method 不變）
- ✅ 不改 RiskConfig schema（LG2-T4 領域）

### CLAUDE.md §七 跨平台合規
- ✅ 無硬編碼路徑（grep `/home/ncyu|/Users/[^/]+` 0 hits）
- ✅ IPC socket 走 `OPENCLAW_IPC_SOCKET` env var 既有 pattern
- ✅ 注釋全中文（CLAUDE.md §七 2026-05-05 規）
- ✅ Python `import os` 標準 stdlib，無新依賴

### CLAUDE.md §九 Singleton 表
- ⚠️ `AccountManagerSlot` 是 late-inject Arc，等同既有 `CostEdgeAdvisorSlot` / `HStateCacheSlot` pattern
- §九 表已含「Rust 端 late-injected slot」一類；新 slot 不需新增獨立條目（屬同類）

---

## 8. 不確定之處

1. **Linux runtime IPC smoke test 未跑**：本 task 在 Mac dev 環境，無 engine
   socket。所有 IPC route 測試走 unit-level mock（4 個 tokio test + 4 個
   pytest mock）。Linux trade-core 下次 restart_all --rebuild 後可實測。
   E4 regression 階段建議加 `helper_scripts/canary/lg2_t3_smoke.py` 跑 Linux 端
   IPC smoke。
2. **dual-source 啟用旗標 OPENCLAW_LG2_T3_DUAL_SOURCE 預設關**：保守設計，
   PASS phase 不影響既有 healthcheck 行為。Operator 決定何時開（PA §2.5 risk #4
   2 週觀察期建議在 LG2-T4 land 後啟用）。
3. **`fee_source(symbol)` rule 3 浮點精確比對**：依賴 `seed_default_fee_rates`
   寫入時直接賦 `DEFAULT_*_FEE` 常量無中間運算。若未來改實作改為 `xxx * 1.0`
   等運算 → 精確比對會失敗，分類錯成 BybitApi。已加 test
   `test_fee_source_demo_conservative_default_when_both_match` 偵測此 regression。

---

## 9. Operator 下一步

1. **E2 代碼審查**：focus on
   - FeeSource enum semantics（4 rule 推斷）
   - IPC route slot late-inject pattern（與 cost_edge_advisor 對稱性）
   - Python dual-source helper fail-soft path 完整性
   - Test plumbing 47 callsite 批量更新沒漏（grep `empty_account_manager_slot` 47 hits）
2. **E4 回歸**：cargo test release + pytest，確認 0 regression
3. **A3 / R4 不需介入**（無 governance / GUI 改動）
4. **PM 派 LG-2 T2**（startup assertion）：依賴本 T3 公開 API；
   PA §2.4 表 T2 設計已成熟，可直接派工

---

## 10. Self-check 8 acceptance ✅

| # | Criterion | Status |
|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | ✅ Finished in 25.36s |
| 2 | `cargo test --release --lib fee_source` 新 test PASS | ✅ 11/11 pass |
| 3 | `cargo test --release --lib` 整體 no regression | ✅ 2849/0/1 ignored |
| 4 | `pytest test_pricing_binding_healthcheck.py` 新 test PASS | ✅ 21/0 pass (含 9 new) |
| 5 | IPC route smoke：Linux runtime 跑 query → return correct FeeSource enum | ⚠️ 已 mock test pass，Linux runtime 待 E4 regression 階段實測 |
| 6 | 注釋全中文 | ✅ CLAUDE.md §七 2026-05-05 規 |
| 7 | Cross-lang serialize 對齊 string enum | ✅ `bybit_api / demo_conservative_default / cold_default` snake_case |
| 8 | healthcheck [45] dual-source disagree → WARN（不直接 FAIL，2 週觀察期）| ✅ test_dual_source_disagree_promotes_pass_to_warn 驗證 |

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t3_fee_source_enum.md`）
