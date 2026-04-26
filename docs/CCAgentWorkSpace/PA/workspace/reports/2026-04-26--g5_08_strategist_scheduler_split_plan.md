# G5-08 PRE-WORK：strategist_scheduler/mod.rs 拆分計劃

**Agent**：PA
**Date**：2026-04-26
**Task**：Wave 2 G5-08 規劃文件（不寫 code，只規劃；E1 接續實作）
**Sibling tickets**：G5-09 tick_pipeline/tests.rs (3524) · G5-10 intent_processor/tests.rs (1948) · G5-11 paper_state/tests.rs (1362) · G5-13 risk_config_advanced.rs (1297) · G5-FUP-IPC-MOD-SPLIT ipc_server/mod.rs (1251)
**Reference patterns**：G1-02 event_consumer 拆分計劃（同目錄 `2026-04-24--g1_02_event_consumer_split_plan.md`） · G5-07 tests.rs 拆 6 sibling · 既有 sibling-child-module pattern（commit `4108849` strategist persist）

---

## §1 現狀

### 1.1 file layout

```
rust/openclaw_engine/src/strategist_scheduler/
├── mod.rs       1770 行  🛑 47% over §九 1200 hard cap
└── persist.rs    446 行  ✅ <800 警告線（既有 sibling，commit 4108849）
```

### 1.2 mod.rs 行數明細（精確 LOC 量測）

| 段落 | 行範圍 | LOC | 內容 | 屬性 |
|---|---|---|---|---|
| Header（doc + use + mod decl） | 1-46 | 46 | MODULE_NOTE 雙語 + `mod persist` + `pub use load_latest_applied_params` + 5 個 use | infrastructure |
| **G3-11 CycleCounters** types | 47-150 | 104 | `pub struct CycleCounters` + impl + `pub struct CycleCountersSnapshot` + `pub const REJECT_REASONS` | **熱路徑共享 atomic（IPC slot 注入點）** |
| Module-level constants | 151-178 | 28 | `MAX_EVALS_PER_CYCLE` / `DEFAULT_MAX_PARAM_DELTA_PCT` / `WEIGHT_SUM_TARGET` / `WEIGHT_SUM_TOLERANCE` / `MIN_SAMPLE_COUNT` / `NORMAL_INTERVAL` | constants |
| `pub struct PairMetrics` + `impl deviation_score` | 179-202 | 24 | DTO + 排序函式 | pure |
| **`pub struct StrategistScheduler`** + 雙語 PAPER-ORPHAN-1 註解 | 203-274 | 72 | 8 fields + 雙語 SCHED-CHANNEL-PAPER-ORPHAN-1 設計記錄 | hot path holder |
| `impl StrategistScheduler` ctor + builder + getters | 276-401 | 126 | `new` (ctor) + `cycle_counters()` + `with_risk_store` + `current_max_param_delta_pct` + `tune_target` + `has_promote_channel` + `promote_params_to_live` | **外部 API 表面** |
| `impl run_forever` + `current_interval` | 405-463 | 59 | 主 loop + backoff 計算 | 熱路徑 |
| `impl evaluate_cycle` | 465-601 | 137 | 5 步驟核心：metrics → rank → IPC → validate → apply + persist | **熱路徑（每 5 min 1 次）** |
| `impl gather_strategy_metrics` (SQL) | 603-708 | 106 | fills 聚合 + 雙語 SCHED-CLOSE-FILTER-1 + FA-1 註解 | DB I/O |
| `impl fetch_current_params` + `apply_params` | 710-755 | 46 | PipelineCommand 雙語 helper | IPC helper |
| `fn rank_by_deviation` (free fn) | 757-767 | 11 | pure 排序 | pure |
| `pub fn validate_recommendation` + `validate_recommendation_with_reason` | 769-894 | 126 | R3-4 驗證 + G3-11 reason tagging | **pure**（最關鍵 logic） |
| `struct PairMetricsRow` (sqlx FromRow) | 896-905 | 10 | DB row 型別 | DB DTO |
| `mod tests` (整段尾部) | 907-1769 | 863 | 31 unit tests | tests |
| EOF | 1770 | 1 | `}` close mod | - |

**總和**：1770 行 = production 906 + tests 863 + EOF 1。

### 1.3 最近 3 commit 影響範圍

```
58a289e G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25)  ~250 行
e388065 STRATEGIST-TUNE-TARGET-CONFIG-1                       ~120 行
4108849 STRATEGIST-SCHEDULER-SPLIT-1                  (拆出 persist.rs，本檔當時 1342 → ~880)
d8f5560 STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1               ~150 行
e47b1e9 + 5538e52 (PERSIST-AUDIT-GAP-COUNTER FUP × 2)         ~50 行
```

**膨脹來源拆解**：
- G3-11 加 CycleCounters struct + Snapshot + REJECT_REASONS const + record_apply/reject/cycle_finish 方法 + IPC accessor + 6 個新 unit tests（`test_cycle_counters_*` × 4 + `test_validate_recommendation_with_reason_returns_each_reason` + `test_reject_reasons_list_covers_validate_branches`）
- TUNE-TARGET-CONFIG 加 `risk_store` field + `with_risk_store` builder + `current_max_param_delta_pct` + 把 `validate_recommendation` 從 0-arg const 改成 caller-supplied + 2 個 e2e tests（`test_param_delta_clamp_uses_config_value` + `test_param_delta_clamp_hot_reload_via_config_store_replace`，雙測都很長 ~130 + ~40）
- PERSIST-AUDIT-GAP-COUNTER 加 `record_reject("apply_failed")` / `record_reject("ipc_failed")` 等 cycle_count 落點

### 1.4 對外公開介面（pub use 面 + 跨檔依賴）

**外部呼叫點精盤點**（grep 命中且非自身目錄）：

| Caller | 引用 | 用途 |
|---|---|---|
| `main_boot_tasks.rs:170` | `Arc<openclaw_engine::strategist_scheduler::CycleCounters>` | IPC slot 注入型別 |
| `main_boot_tasks.rs:211` | `openclaw_engine::strategist_scheduler::load_latest_applied_params(...)` | 啟動時 restore tuned params |
| `main_boot_tasks.rs:300` | `openclaw_engine::strategist_scheduler::StrategistScheduler::new(...)` | 構造 scheduler |
| `main_boot_tasks.rs:308` | `.with_risk_store(Arc::clone(&risk_stores.demo))` | 注入 RiskConfig hot-reload |
| `main_boot_tasks.rs:316` | `scheduler.cycle_counters()` | 取 Arc 給 IPC slot |
| `main.rs:522 / 771 / 775 / 787` | `// CycleCounters 注入流程` 註解 + 流程協調 | 流程編排 |
| `ipc_server/mod.rs:103` | `Arc<RwLock<Option<Arc<crate::strategist_scheduler::CycleCounters>>>>` | IPC late-injection slot type alias |
| `ipc_server/mod.rs:566 + 709` | `Option<Arc<crate::strategist_scheduler::CycleCounters>>` | get_strategist_cycle_metrics handler 參數 |
| `ipc_server/handlers/misc.rs:210` | `&Option<Arc<crate::strategist_scheduler::CycleCounters>>` | snapshot 取值 |
| `config/risk_config_advanced.rs:1208` | comment 引用 `validate_recommendation` | 文檔交叉引用 |

**對外公開 API 表面**（拆分時必 100% 保留 path）：

```rust
openclaw_engine::strategist_scheduler::CycleCounters             // type
openclaw_engine::strategist_scheduler::CycleCountersSnapshot     // type
openclaw_engine::strategist_scheduler::REJECT_REASONS            // const
openclaw_engine::strategist_scheduler::PairMetrics               // type (test+future)
openclaw_engine::strategist_scheduler::StrategistScheduler       // type + impl
openclaw_engine::strategist_scheduler::DEFAULT_MAX_PARAM_DELTA_PCT // const
openclaw_engine::strategist_scheduler::validate_recommendation     // pure fn
openclaw_engine::strategist_scheduler::validate_recommendation_with_reason // pure fn
openclaw_engine::strategist_scheduler::load_latest_applied_params  // pure fn (already re-exported from persist)
```

**所有 9 條 path 必透過 `mod.rs` 的 `pub use` 維持** — 等同 G1-02 model + G5-07 tests 拆模式。

### 1.5 既有 sibling files 構造（reference 模式）

**`persist.rs` (446 行)**：
- 開檔 doc 註解雙語：「從父 mod.rs 拆出 / 為 commit f1f7403 post-commit FUP」 + 完整 `MODULE_NOTE` block
- `use super::StrategistScheduler;` + production use
- `impl StrategistScheduler { pub(super) async fn persist_applied_params(...) {...} }` (impl extension, sibling-child-module pattern)
- standalone `pub async fn load_latest_applied_params(...)` re-exported via mod.rs `pub use`
- `#[cfg(test)] mod tests` 含 5 unit tests（pool=None fail-soft × 2 + 3 SQL property tests via `include_str!`）
- 採 verbatim 搬出 + 0 邏輯改動 — 拆檔 commit `4108849` 文檔載「零行為改動」契約

→ G5-08 拆分**100% 沿襲 persist.rs pattern**：sibling-child-module + `impl StrategistScheduler { pub(super) ... }` + `mod.rs` re-export + 開檔 MODULE_NOTE 標明拆分 commit。

### 1.6 Test baseline

```
ssh trade-core "cargo test --release -p openclaw_engine --lib strategist_scheduler"
result: ok. 31 passed; 0 failed; 0 ignored; 0 measured; 2130 filtered out
```

**31 tests 完整名單**（拆分後必 100% 保留並全綠）：
- mod.rs 內 26 tests：pair_metrics_deviation_score / rank_by_deviation / 7 個 validate_recommendation_* / backoff_intervals / 5 個 PAPER-ORPHAN-1 regression（new_rejects_paper / new_accepts_demo_without_promote / new_accepts_demo_with_live_promote / promote_params_to_live × 3 + db_mode pin） / 2 e2e（test_param_delta_clamp_uses_config_value / test_param_delta_clamp_hot_reload_via_config_store_replace） / 4 CycleCounters tests / validate_recommendation_with_reason_returns_each_reason / reject_reasons_list_covers_validate_branches
- persist.rs 內 5 tests（已拆）：persist_..._fails_soft_on_pool_none / load_..._empty_on_pool_none / 3 SQL property tests

---

## §2 拆分方案 A/B 對比

按 G1-02 計劃方法論：給出 2 套候選方案 + 完整 trade-off。

### Method A — 保守方案（4 sibling，類型 + 邏輯 + tests 三層拆）

```
strategist_scheduler/
├── mod.rs                  ~280 行  (header + pub use + 8 const + StrategistScheduler ctor/getters/builder + run_forever)
├── persist.rs               446 行  (existing, unchanged)
├── cycle_counters.rs       NEW ~250 行  (CycleCounters + Snapshot + REJECT_REASONS + 4 单测)
├── validation.rs           NEW ~220 行  (validate_recommendation + with_reason + ParamRange-related + 9 单测)
├── evaluate.rs             NEW ~370 行  (impl extension: evaluate_cycle + gather_strategy_metrics + fetch_current_params + apply_params + rank_by_deviation + PairMetrics + PairMetricsRow + ~3 unit test 共享)
└── tests.rs                NEW ~250 行  (剩餘 PAPER-ORPHAN-1 + backoff_intervals + e2e clamp tests + db_mode pin)
```

**LOC 預估表 A**：

| Sibling | LOC | <800? | 內容範圍 |
|---|---|---|---|
| `mod.rs` | ~280 | ✅ | 1-46 + 151-178 + 203-401 + 405-463 + EOF |
| `persist.rs` | 446 | ✅ | unchanged |
| `cycle_counters.rs` | ~250 | ✅ | 47-150 production + cycle_counters_* 4 tests |
| `validation.rs` | ~220 | ✅ | 769-894 + validate-related 7 tests + 1 reasons list test |
| `evaluate.rs` | ~370 | ✅ | 465-755 (impl block) + 179-202 + 757-767 + 896-905 + 3 共享 helper tests |
| `tests.rs` | ~250 | ✅ | mk_deps + 7 PAPER-ORPHAN-1 + 2 e2e clamp + backoff_intervals + db_mode pin |

**A 優點**：
- 純粹依「概念聚合」拆 — 每個 sibling 一個明確 domain（counters / validation / evaluation 主路徑 / tests）
- evaluate.rs 把 `impl StrategistScheduler` 的所有 cycle 邏輯放一起，可讀性最高
- mod.rs 230 行很瘦，純框架

**A 缺點**：
- 4 個新 sibling — refactor PR 動到 5 檔（mod.rs + 4 新檔），review 面廣
- evaluate.rs 跨 type 邊界（PairMetrics + impl StrategistScheduler 局部 + free fn rank_by_deviation + struct PairMetricsRow），「概念聚合」但 type 邏輯散
- 從 mod.rs 看 evaluate.rs 是黑盒，要看完整 cycle 流程需跳檔

---

### Method B — 大刀方案（3 sibling，按 hot-path / cold-path / tests 拆）

```
strategist_scheduler/
├── mod.rs                  ~480 行  (header + pub use + types + ctor + getters + builder + validate + free fns + 共享 const)
├── persist.rs               446 行  (existing, unchanged)
├── cycle_counters.rs       NEW ~280 行  (CycleCounters + Snapshot + REJECT_REASONS + ~4 unit tests)
├── runtime.rs              NEW ~280 行  (impl: run_forever + evaluate_cycle + gather_strategy_metrics + fetch_current_params + apply_params + current_interval + 0 unit tests)
└── tests.rs                NEW ~620 行  (所有 mod.rs tests 集中搬出，參考 G5-07 tests.rs split pattern)
```

**LOC 預估表 B**：

| Sibling | LOC | <800? | 內容範圍 |
|---|---|---|---|
| `mod.rs` | ~480 | ✅ | header + pub use + 8 const + PairMetrics + StrategistScheduler ctor + getters + builder + current_max_param_delta_pct + validate × 2 + rank_by_deviation + PairMetricsRow |
| `persist.rs` | 446 | ✅ | unchanged |
| `cycle_counters.rs` | ~280 | ✅ | 47-150 + 4 cycle_counters tests + 1 reasons list test |
| `runtime.rs` | ~280 | ✅ | 405-755 (run_forever / evaluate_cycle / gather / fetch / apply / current_interval) + 雙語 註解 |
| `tests.rs` | ~620 | ✅ | 所有 mod.rs 內現存 tests (除 cycle_counters 4 + reasons list 1 + persist 5) |

**B 優點**：
- 只 3 個新 sibling，PR 面更窄
- runtime.rs 純 hot-path execution（5 fn 緊密關聯，整段 cycle）
- mod.rs 維持「概念入口」 — 所有對外 type + pub fn + const 都在
- tests.rs 集中參考 G5-07 pattern（剛拆完 tick_pipeline/tests.rs 6 sibling），與既有規範一致

**B 缺點**：
- mod.rs 仍 480 行（雖 <800，但比 A 厚一倍）
- runtime.rs 是 impl 擴展的 sibling-child-module — 需 `impl StrategistScheduler { ... }` block in sibling，只能用 `pub(super) fn` 訪問，這是 persist.rs 已用 pattern，no new technique
- tests.rs 620 行靠近 §九 800 警告線，未來新增 test 需另拆

---

### Method 對比決策矩陣

| 維度 | A 保守 | B 大刀 |
|---|---|---|
| 新檔數 | 4 | 3 |
| 主檔(mod.rs)精簡 | ~280（74% reduction） | ~480（66% reduction） |
| Hot-path 集中度 | 中（evaluate 拆出 + run_forever 留 mod） | 高（runtime.rs 全部 hot 一起） |
| Refactor risk surface | 廣（5 檔變動） | 中（4 檔變動） |
| 與既有 split 模式一致性 | 高（cycle_counters / validation 純抽出像 G1-02 governor_cooldown） | 高（tests.rs 抽出對齊 G5-07） |
| 後續維護單檔大小 | 全 <450 ✅ | tests.rs 620 距 800 較近 ⚠️ |
| Hot-path semantic preservation | ✅ evaluate_cycle 整段成立 | ✅ runtime.rs 整段成立 |
| Cross-cutting risk（CycleCounters 散） | 低（cycle_counters.rs 集中） | 低（cycle_counters.rs 集中） |
| Test traceability | 中（tests 散 mod.rs + 各 sibling） | 高（除 5 + 5 外集中 tests.rs） |

---

## §3 推薦方案 + 理由

**推薦：Method A（保守 4-sibling）**

### 理由

1. **單檔 LOC 全 <450**：所有 sibling 全部離 §九 800 警告線有 ≥350 行 buffer。後續 G3-11 Phase 2（DB sink）、PERSIST-AUDIT-GAP-COUNTER FUP 等 ~100-200 行新增不會立即再撞 §九。

2. **概念清晰 = code review 加速**：cycle_counters / validation / evaluate / tests 是 4 個正交 domain。E2 看 PR 時可逐 sibling 分塊核對 verbatim 搬出 vs 邏輯動了，比「runtime.rs 280 行混 5 fn」更易抓 regression。

3. **跟隨 persist.rs sibling-child-module 既有 pattern**：A 方案的 evaluate.rs 與 persist.rs 結構同形（impl extension via `impl StrategistScheduler { pub(super) async fn ... }`），合併後本目錄變成 5 個 sibling 完全一致 layout。B 方案 runtime.rs 也用 sibling-child-module，但跟 cycle_counters.rs（純 type + impl 無 super 依賴）混搭，pattern 不齊。

4. **G3-11 + PERSIST-AUDIT-GAP-COUNTER 兩個高價值熱點隔離**：cycle_counters.rs 是 IPC 注入面（externally facing via `Arc<RwLock<Option<...>>>` slot），單檔隔離後未來 G3-11 Phase 2 加 DB sink 時 PR 範圍 = 1 sibling。

5. **驗證面對等**：兩方案的 hot-path semantic 都能保留（evaluate_cycle / persist_applied_params / IPC accessor 全部 verbatim 搬出），所以選 A 不犧牲 invariant，純取「未來可維護性 + review 友好」。

### 唯一不足

- 多 1 sibling 即 4 → 5 檔（含 persist + mod），目錄略繁
- 但對比已存在的 `event_consumer/`（11 檔含 handlers/ × 5）、`tick_pipeline/`（4 檔含 tests/ × 6），仍屬輕量

---

## §4 拆分順序（E1 工作步驟，每步可獨立 commit + cargo test）

### Step 1：cycle_counters.rs（最低風險）

**邏輯**：純 type + impl + const，零 cross-cutting。CycleCounters Arc 對外曝露但 ctor 無變化，IPC accessor 路徑（`scheduler.cycle_counters()`）走 `super::` re-export。

**操作**：
1. 新建 `rust/openclaw_engine/src/strategist_scheduler/cycle_counters.rs`
2. 開檔 doc：套 persist.rs MODULE_NOTE 雙語模板，標 commit reason = "G5-08 §九 1200 hard cap fix"
3. 從 mod.rs lines 47-150 verbatim 搬出 production code
4. 從 mod.rs tests block 搬出 4 + 1 unit tests：`test_cycle_counters_record_apply_and_snapshot` / `test_cycle_counters_record_reject_per_reason` / `test_cycle_counters_record_cycle_finish_freshness` / `test_cycle_counters_concurrent_record_reject` / `test_reject_reasons_list_covers_validate_branches`
5. mod.rs 刪掉 47-150 + 對應 tests，加 `mod cycle_counters; pub use cycle_counters::{CycleCounters, CycleCountersSnapshot, REJECT_REASONS};`

**驗收**：
```
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib strategist_scheduler::cycle_counters && cargo test --release -p openclaw_engine --lib strategist_scheduler"
```
預期：cycle_counters tests 5 PASS + strategist_scheduler 全 31 PASS（無 net 變化，只移位）

**Commit message**：
```
refactor(strategist_scheduler): extract CycleCounters to cycle_counters.rs (G5-08 step 1/4)

Verbatim extraction of CycleCounters + CycleCountersSnapshot + REJECT_REASONS
+ 5 unit tests from mod.rs (lines 47-150 production + 5 cycle_counters tests).
mod.rs 1770 → ~1665. Sibling-child-module pattern per persist.rs (4108849).
0 logic change. 31/31 strategist_scheduler tests still PASS.

Co-Authored-By: ...
```

### Step 2：validation.rs（純 fn，零 state）

**邏輯**：`validate_recommendation` + `validate_recommendation_with_reason` 是 pure fn，0 self 引用，搬出最簡單。

**操作**：
1. 新建 `rust/openclaw_engine/src/strategist_scheduler/validation.rs`
2. 從 mod.rs lines 769-894 搬出兩 pub fn + 雙語 R3-4 doc
3. 從 mod.rs tests 搬出：`test_validate_recommendation_passes_valid` / `test_validate_recommendation_rejects_out_of_range` / `test_validate_recommendation_rejects_excessive_delta` / `test_validate_recommendation_weight_params_exempt_from_delta` / `test_validate_recommendation_rejects_bad_weight_sum` / `test_validate_recommendation_non_adjustable_skipped` / `test_validate_empty_recommendation_passes` / `test_validate_recommendation_with_reason_returns_each_reason`（共 8 個）
4. mod.rs 加 `mod validation; pub use validation::{validate_recommendation, validate_recommendation_with_reason};`

**注意**：`use crate::strategies::ParamRange;` 必須在 validation.rs 也加；test fixture 內的 `DEFAULT_MAX_PARAM_DELTA_PCT` 在 mod.rs 還在，validation.rs 用 `super::DEFAULT_MAX_PARAM_DELTA_PCT` 引用（或直接 hard-code 0.30，但**不要這麼做** — 維持 const 引用契約）。

**驗收**：cargo test 31/31 PASS（移位）

### Step 3：evaluate.rs（impl extension 大塊，最高 risk）

**邏輯**：`impl StrategistScheduler` 中的 5 fn — `run_forever` / `evaluate_cycle` / `gather_strategy_metrics` / `fetch_current_params` / `apply_params` / `current_interval` — 加上 `PairMetrics` + `rank_by_deviation` + `PairMetricsRow`。

**操作**：
1. 新建 `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs`
2. 開檔 doc：標 commit reason + impl extension pattern（`use super::StrategistScheduler;`）
3. 從 mod.rs lines 179-202（PairMetrics + deviation_score）搬出 — 標為 `pub` 維持外部可見
4. 從 mod.rs lines 405-755 搬出整 impl block（用 `impl StrategistScheduler { ... }` sibling form）
   - **注意**：`run_forever` 是 `pub async fn`，不能改 `pub(super)` — `main_boot_tasks.rs:316` `tokio::spawn(scheduler.run_forever())` 直接呼叫。**原 pub 屬性必須保留**。
   - `evaluate_cycle` / `gather_strategy_metrics` / `fetch_current_params` / `apply_params` / `current_interval` 全是私有 `async fn`，搬出後可改 `pub(super)` 或保留 `fn`（impl extension 可見性同 trait）
5. 從 mod.rs lines 757-767 搬出 `fn rank_by_deviation` — 是 free fn `fn`（默認 module-private），改 `pub(super)`
6. 從 mod.rs lines 896-905 搬出 `struct PairMetricsRow` — 改 `pub(super)`
7. mod.rs 加 `mod evaluate; pub use evaluate::PairMetrics;`（PairMetrics 為 pub，rank_by_deviation 與 PairMetricsRow 不需公開）

**注意**：
- `use serde_json::Value;` / `tokio::sync::oneshot` / `sqlx::query_as` 等 use 必須在 evaluate.rs 全部加齊
- evaluate_cycle 內呼叫 `self.cycle_counters.record_*` → 走 `super::cycle_counters::*` 已 re-export，accessor `self.cycle_counters` 是 field 直接訪問無 cross-檔影響
- evaluate_cycle 內呼叫 `validate_recommendation_with_reason(...)` → 走 `super::validate_recommendation_with_reason`（Step 2 已 re-export）
- evaluate_cycle 內呼叫 `self.persist_applied_params(...)` → persist.rs 既有 `pub(super) async fn` 在同 super crate，**OK**
- 「FA-1 雙語註解」+ debug_assert 等 documentation/safety 100% 保留 verbatim

**驗收**：cargo test 31/31 PASS（移位）+ 確認 `cargo build --release` 編譯通過（impl extension 跨檔最常踩 use 漏帶）

### Step 4：tests.rs（剩餘整合測試 + ctor regression）

**邏輯**：剩下 mod.rs 內未搬走的 tests 集中到 `tests.rs`。

**剩餘 tests 名單**：
- `test_pair_metrics_deviation_score`（PairMetrics pure 測，可放 evaluate.rs 內 mod tests，但 evaluate.rs 已 ~370 行，move 到 tests.rs 更平衡）
- `test_rank_by_deviation`
- `test_backoff_intervals`
- `test_new_rejects_paper_tune_target`（#[should_panic]，ctor regression）
- `test_new_accepts_demo_without_promote_channel`
- `test_new_accepts_demo_with_live_promote_channel`
- `test_promote_params_to_live_err_when_no_channel`
- `test_promote_params_to_live_sends_and_awaits_response`
- `test_promote_params_to_live_err_on_handler_failure`
- `test_pipeline_kind_db_mode_demo_is_lowercase_snake`
- `test_param_delta_clamp_uses_config_value`（e2e）
- `test_param_delta_clamp_hot_reload_via_config_store_replace`（e2e）
- `mk_deps()` helper（要搬到 tests.rs 或變成 sibling 共用 module）

**操作**：
1. 新建 `rust/openclaw_engine/src/strategist_scheduler/tests.rs`（檔案頭加 `#![cfg(test)]`）
2. 加 `use super::*;` + 必要 use（`std::sync::Arc` / `tokio::sync::mpsc` / `tokio_util::sync::CancellationToken` / etc）
3. 把上述 13 tests + mk_deps 從 mod.rs 搬入
4. mod.rs 加 `#[cfg(test)] mod tests;`（不需要 pub use；tests 不對外）

**驗收**：cargo test 31/31 全綠 + cargo test --release 完整 strategist_scheduler 範圍通過

### Step 5：mod.rs 最終形態（檢核點）

mod.rs 收斂內容：
1. lines 1-46 header（doc + use + mod decl）
2. **`mod persist; mod cycle_counters; mod validation; mod evaluate; #[cfg(test)] mod tests;`**
3. `pub use persist::load_latest_applied_params;`
4. `pub use cycle_counters::{CycleCounters, CycleCountersSnapshot, REJECT_REASONS};`
5. `pub use validation::{validate_recommendation, validate_recommendation_with_reason};`
6. `pub use evaluate::PairMetrics;`
7. lines 151-178 module-level constants（保留在 mod.rs，因 cycle_counters / validation / evaluate 都引用）
8. lines 203-401（`pub struct StrategistScheduler` + ctor / getters / builder / current_max_param_delta_pct）

mod.rs 預估 ~280 行 ✅。

---

## §5 熱路徑保護清單（E1 拆分時必 100% 保留 invariant）

| # | Invariant | 證據 / 違反後果 |
|---|---|---|
| 1 | `CycleCounters` 是 single Arc 全進程共享 | IPC slot 注入（`ipc_server/mod.rs:103` `Arc<RwLock<Option<Arc<CycleCounters>>>>`）+ scheduler 持有 + main_boot_tasks 注入；拆檔不可改 Arc 包裝層級 |
| 2 | `CycleCounters` atomic field 順序與 `Ordering::Relaxed` | 原代碼 4 個 AtomicU64 + 1 Mutex<HashMap>；拆檔不可改 ordering（會破壞 G3-11 IPC 觀察值的可見性）|
| 3 | `validate_recommendation_with_reason` 6 reject reason 字串 | `REJECT_REASONS` const 與 evaluate_cycle 中 `record_reject("apply_failed"/"ipc_failed")` 全部串聯；改字串會破壞 healthcheck `[16] strategist_cycle_fresh` 的 reason matcher |
| 4 | `evaluate_cycle` 5 步驟順序 + persist 寫入位置 | gather_metrics → rank → fetch_current → IPC → validate → apply → persist + record_apply；拆檔調動順序 = STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 退化（重新引入 type-cast 漏洞或漏 record_reject 路徑） |
| 5 | `PERSIST-AUDIT-GAP-COUNTER` type-cast bug 規避 | `applied_at_ms: i64 = chrono::Utc::now().timestamp_millis()` 必須 i64（commit `d8f5560` 修了 int→float silent truncation），E1 不可在搬出時改為 `as f64` |
| 6 | `gather_strategy_metrics` 三條 NOT LIKE close-path filter | SCHED-CLOSE-FILTER-1（2026-04-23 EDGE-DIAG-1 副產物）— `NOT LIKE 'risk_close:%'` / `'strategy_close:%'` / `'ipc_close%'`；漏一條 = 每 5 min log spam 復發 |
| 7 | `gather_strategy_metrics` `engine_mode = $2` filter + `debug_assert!(matches!(self.tune_target, PipelineKind::Demo))` | FA-1 雙語 + STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1；FA-1 提示 Live tune 須擴 IN，目前必 Demo only；E1 不可省 debug_assert（會在 Live tune 切換時靜默無聲故障） |
| 8 | `current_max_param_delta_pct` ArcSwap load + fallback 0.30 | TUNE-TARGET-CONFIG-1 寫法 `self.risk_store.as_ref().map(|s| s.load().strategist.max_param_delta_pct).unwrap_or(DEFAULT_MAX_PARAM_DELTA_PCT)`；ArcSwap load 必須 hot-path safe（單次 load 無鎖）；E1 不可改成 `Mutex` 或加 cache |
| 9 | `with_risk_store` builder semantics | 返回 `Self`（取所有權後返還）— E1 不可改成 `&mut self -> &mut Self`，會破壞 main_boot_tasks 的 chained call `StrategistScheduler::new(...).with_risk_store(...)` |
| 10 | `assert!(matches!(tune_target, PipelineKind::Demo \| PipelineKind::Live))` Paper panic | PAPER-DISABLE-1 防禦性檢查；E1 拆出 ctor 時保留 panic（否則 paper 路徑復活，drained engine 被 tune） |
| 11 | `mod.rs` 對外 9 條 pub path 全部維持 | 詳 §1.4；任一 path 漏 re-export = 外部 caller 編譯失敗，下游 main_boot_tasks / ipc_server / handlers/misc 三檔同時掛 |
| 12 | `run_forever` 是 `pub async fn`（非 `pub(super)`） | main_boot_tasks 直接 `tokio::spawn(scheduler.run_forever())` 呼叫；E1 不可降可見性 |
| 13 | `persist_applied_params` 是 `pub(super) async fn` | persist.rs 已用此 modifier；evaluate.rs 內呼叫 `self.persist_applied_params(...)` 必須維持 `pub(super)` 可見性 |
| 14 | `record_cycle_finish` 在 `run_forever` loop 末尾無條件呼叫 | G3-11 healthcheck `[16]` 的核心：even AI service down 也要更新 `last_cycle_ts_ms`；E1 不可在 Step 3 搬出時把這呼叫條件化 |
| 15 | tests.rs `mk_deps()` 對所有 ctor regression 共用 | 拆完後 mk_deps 只在 tests.rs 內定義（E1 可選 sibling 用 `super::tests::mk_deps`，或在每個 sibling tests 重複定義；推薦集中在 tests.rs）|

---

## §6 E1 工作 prompt template（給 PM 後續派 E1 用的骨架）

```markdown
## 任務 ID：G5-08 STRATEGIST-SCHEDULER-MOD-SPLIT-1（P1 Wave 2）

## 背景
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs` = 1770 行（§九 1200 hard cap 47% over）
- 既有 sibling `persist.rs` 446 行（commit 4108849 拆成的 first-pass）
- 最近 3 commit（G3-11 + TUNE-TARGET-CONFIG + PERSIST-AUDIT-GAP-COUNTER）累積膨脹 ~520 行
- PA design plan：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md`

## 採用方案
**Method A（保守 4-sibling）**：
1. cycle_counters.rs（CycleCounters + Snapshot + REJECT_REASONS + 5 tests）
2. validation.rs（validate_recommendation × 2 + 8 tests）
3. evaluate.rs（impl: run_forever + evaluate_cycle + 4 helpers + PairMetrics + rank_by_deviation + PairMetricsRow + 0 unit tests）
4. tests.rs（剩餘 13 tests + mk_deps helper）

mod.rs 收斂至 ~280 行（header + const + StrategistScheduler ctor/getters/builder + 4 mod decl + 4 pub use）

## 4 步驟（每步獨立 commit + cargo test）
- Step 1：cycle_counters.rs（lines 47-150 + 5 tests）
- Step 2：validation.rs（lines 769-894 + 8 tests）
- Step 3：evaluate.rs（lines 179-202 + 405-755 + 757-767 + 896-905）
- Step 4：tests.rs（剩餘 13 tests + mk_deps）

## 熱路徑保護（必讀 §5 全 15 條）
要點摘錄：
- CycleCounters Arc + atomic ordering 不動（IPC slot 共享）
- validate_recommendation_with_reason 6 reason string 不改（healthcheck matcher）
- evaluate_cycle 5 步驟 + persist 順序不動（PERSIST-AUDIT-GAP-COUNTER bug 規避）
- gather_strategy_metrics 三條 NOT LIKE filter + debug_assert(Demo only) 不省
- run_forever pub async fn 不降可見性
- mod.rs 9 條 pub path 全部維持

## 驗收
- 每 Step：`cargo test --release -p openclaw_engine --lib strategist_scheduler` 31/31 PASS（不可少）
- 全 4 step 完成：`cargo test --release -p openclaw_engine --lib` 全套（baseline 2161）+ `cargo build --release` 通過
- mod.rs 行數 ≤ 300（給 ~20 行 buffer）
- 4 sibling 全部 ≤ 450 行
- 所有 sibling 開檔加 MODULE_NOTE 雙語 + 標明 commit reason "G5-08 §九 1200 hard cap fix"

## 不要做
- 不改 SQL（gather_strategy_metrics + persist_applied_params + load_latest_applied_params 三段 SQL byte-identical）
- 不改 reject reason 字串（healthcheck dependency）
- 不重整 evaluate_cycle 內部步驟順序
- 不擴 ctor signature（new 6 個 arg 不變）
- 不順手「修」FA-1 / SCHED-CHANNEL-PAPER-ORPHAN-1 / SCHED-CLOSE-FILTER-1 註解（這些是 design rationale，下次如要改是另一個 ticket）

## 工時估計
- 每 Step ~30-45 min（含 cargo test 4 min release build × 4 = 16 min）
- 全 4 step ≈ 2.5-3 h（E1 主操作）
- E2 review 1 h（4 step PR 合併）
- E4 regression：cargo test 全套 + smoke `restart_all.sh --rebuild` + healthcheck 6h cron 1 cycle ≈ 2 h
- **Total**：5.5-6 h
```

---

## §7 預估工時表

| 角色 | 任務 | 工時 |
|---|---|---|
| E1 | Step 1 cycle_counters.rs（含 cargo test 驗收） | 30-45 min |
| E1 | Step 2 validation.rs（含 cargo test 驗收） | 30-40 min |
| E1 | Step 3 evaluate.rs（impl 擴展，含 build + test） | 60-75 min |
| E1 | Step 4 tests.rs + mod.rs 最終收斂 | 30-45 min |
| E1 小計 | | **2.5-3 h** |
| E2 | PR 4 step 全 review（diff 概念對齊 + 9 pub path 驗證 + 15 invariant grep）| 1-1.5 h |
| E4 | cargo test 全套 + smoke restart + healthcheck cron | 1.5-2 h |
| **合計** | | **5-6.5 h** |

**並行可能**：4 step 必串行（後步依賴前步 mod.rs 已減）。Step 4 後可派 E5 平行 review optimization 機會（pure fn 應否放 const generics 等），但屬 nice-to-have 非阻塞。

---

## §8 測試集 baseline + 拆分後預期

### Baseline（2026-04-26 採集）

```
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && PATH=$HOME/.cargo/bin:$PATH cargo test --release -p openclaw_engine --lib strategist_scheduler"
```

```
test result: ok. 31 passed; 0 failed; 0 ignored; 0 measured; 2130 filtered out; finished in 0.00s
```

**31 tests 完整名單** — 拆完後必逐項在新位置 PASS：

| Test | 拆分目的地 | 名稱（不變）|
|---|---|---|
| 1-4 | `cycle_counters.rs` mod tests | test_cycle_counters_record_apply_and_snapshot / record_reject_per_reason / record_cycle_finish_freshness / concurrent_record_reject |
| 5 | `cycle_counters.rs` mod tests | test_reject_reasons_list_covers_validate_branches |
| 6-12 | `validation.rs` mod tests | test_validate_recommendation_passes_valid / rejects_out_of_range / rejects_excessive_delta / weight_params_exempt_from_delta / rejects_bad_weight_sum / non_adjustable_skipped / empty_recommendation_passes |
| 13 | `validation.rs` mod tests | test_validate_recommendation_with_reason_returns_each_reason |
| 14-26 | `tests.rs` | test_pair_metrics_deviation_score / rank_by_deviation / backoff_intervals / new_rejects_paper_tune_target / new_accepts_demo_without_promote_channel / new_accepts_demo_with_live_promote_channel / promote_params_to_live_err_when_no_channel / promote_params_to_live_sends_and_awaits_response / promote_params_to_live_err_on_handler_failure / pipeline_kind_db_mode_demo_is_lowercase_snake / param_delta_clamp_uses_config_value / param_delta_clamp_hot_reload_via_config_store_replace |
| 27-31 | `persist.rs` mod tests | (無變動，5 個 persist tests 保持原位)|

### 拆分後預期

```
strategist_scheduler::cycle_counters tests : 5 PASS
strategist_scheduler::validation tests     : 8 PASS
strategist_scheduler::tests                : 13 PASS
strategist_scheduler::persist tests        : 5 PASS
─────────────────────────────────────────────────
strategist_scheduler 範圍 total            : 31 PASS （與 baseline 完全相符）

cargo test --release -p openclaw_engine --lib total : 2161 PASS（與全 lib baseline 相符，無 net 變化）
```

**Regression breakers**（任一觸發 = E2 必打回）：
- `strategist_scheduler::*` 範圍 PASS 數 ≠ 31
- 任一 test 名稱被改（pin 在 `[16] strategist_cycle_fresh` healthcheck 之外的 cron / log 監控可能讀 test 名）
- mod.rs ≥ 800 行（§九 警告線復返）
- 任一新 sibling ≥ 800 行

### 後續監控（E4 完成後 PM 跑 6h 1 cycle 確認）

- healthcheck `[16] strategist_cycle_fresh` PASS（CycleCounters last_cycle_ts_ms 正常累進）
- engine.log 無新增 `RecvError` / `channel closed` spam
- 無新 `persist_applied_params failed` warn 噴發

---

## §9 與 G5-FUP-IPC-MOD-SPLIT 的依賴關係

PM 規劃中 `ipc_server/mod.rs` (1251 行) 由隔壁 ticket G5-FUP-IPC-MOD-SPLIT 處理。本 ticket 與其有 3 個邊界依賴點：

| 點 | G5-08 動作 | G5-FUP-IPC-MOD-SPLIT 影響 |
|---|---|---|
| 1 | `CycleCounters` 型別維持 `pub` 在 `crate::strategist_scheduler::CycleCounters` | ipc_server/mod.rs L103 + L566 + L709 用此 path（`crate::strategist_scheduler::CycleCounters`）— 路徑不動，G5-08 拆完仍合法 |
| 2 | `cycle_counters()` accessor 維持 method on `StrategistScheduler` | main_boot_tasks L316 呼叫此 method — 路徑不動 |
| 3 | `patch_risk_config` IPC handler **不在本檔** | ipc_server/mod.rs L998 + handlers/misc.rs；G5-08 完全不碰，純由 G5-FUP-IPC-MOD-SPLIT 處理。**無依賴 / 無 lock contention** |

**結論**：G5-08 + G5-FUP-IPC-MOD-SPLIT **可並行進行**（兩 ticket 操作不重疊檔），不需 isolation worktree。PM 派發時可同時下兩 prompt。

---

## §10 派發架構建議（給 PM）

| 子任務 | E1 instance | isolation | 工時 | 阻塞項 |
|---|---|---|---|---|
| G5-08 全 4 step | E1（單實例串行） | 主樹（無並行衝突）| 2.5-3 h | 無，可立即派 |
| G5-FUP-IPC-MOD-SPLIT | E1（隔壁 ticket）| 主樹（與 G5-08 不重疊檔）| ~3-4 h（推測，未盤點）| 無 |
| **可同時派 2 個 E1 instance** | | | | |

E2 / E4 等待 E1 完成後串行（standard chain），不需特殊調度。

---

## §11 結論

- **推薦方案：Method A（保守 4-sibling）** — 全 sibling <450 行，跟隨 persist.rs 既有 sibling-child-module pattern，4 step 串行可獨立 commit + 獨立 cargo test
- **15 條熱路徑 invariant 全部識別 + 寫入 §5** — E1 操作時逐條核對
- **31 tests baseline 鎖定** — 拆分後分布到 4 sibling 但 PASS 數不變
- **無架構級風險** — 純 file partition + sibling-child-module pattern 已在本目錄（persist.rs）+ event_consumer/ + tick_pipeline/ 三處驗證成功
- **無 §四 硬邊界觸碰** — 不動 live_execution / max_retries / decision_lease 等
- **無跨 ticket 鎖** — 與 G5-FUP-IPC-MOD-SPLIT 完全獨立，可並行派發

PM 後續操作：用 §6 prompt template 派 E1（單實例串行）→ E2 review → E4 regression → PM Sign-off。

---

## §12 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G5-08 strategist_scheduler/mod.rs 拆分計劃（推 Method A 保守 4-sibling） | `workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md` |

---

**PA Sign-off**：design ready。E1 可開工，Operator 確認方案 A 後派發。
