# E1 報告 — G3-09-FUP-MAIN-RS-SPLIT P3 + G3-09-FUP-MAIN-BOOT-TASKS-SPLIT P2 (combined)

- 日期：2026-04-28
- Agent：E1（Backend Developer）
- 工作模式：worktree isolation
- Base HEAD：`decf712`（origin/main，docs(pm) Wave B Sign-off）
- 範圍：純 location refactor，0 production behavior change

---

## 1. 任務摘要

E2 Phase B Wave 1 review (`adbc92e`) 揪出兩個 file size violation 由 Wave 1
deepened：

- **MED-2 (P3)** — `main.rs` 1208→1230 越過 §九 1200 行硬上限
  （Wave 1 加 22 LOC for `cost_edge_advisor_db_pool_slot` plumbing；pre-existing
  8 LOC 已過硬上限，被 Wave 1 進一步拉開）
- **LOW-1 (P2)** — `main_boot_tasks.rs` 944→1015 越過 §九 800 行警告線
  （Wave 1 加 71 LOC for `spawn_cost_edge_advisor_if_enabled` ~150 LOC）

E2 推薦 fix 一致：抽 `cost_edge_advisor_db_pool_slot` plumbing + `spawn_*` fn
→ 新 sibling `cost_edge_advisor_boot.rs`（**不**入 `cost_edge_advisor::boot`，
保 sibling pattern 避免 boot-time deps 拉進 engine library crate）。

完成狀態：✅ refactor 完成、✅ 編譯通過、✅ lib 2299/0、✅ daemon 11/0、
✅ persistence 2/0（Mac 實跑，未 skip）。
⚠️ main.rs 1213→1210 仍 10 LOC 高於 §九 1200 硬上限（PA RFC LOC 預估偏離
>20%，見 §5）。

---

## 2. 修改清單

| 檔 | 動作 | 行數 before / after | 說明 |
|---|---|---|---|
| `rust/openclaw_engine/src/cost_edge_advisor_boot.rs` | 新增 | 0 → **279** | sibling 模組：type alias + 2 helper + spawn fn |
| `rust/openclaw_engine/src/main.rs` | 修改 | 1230 → **1210** | 接 sibling helper：`mod` 註冊 + 11 LOC inline 區塊（原 22 LOC + 5 LOC late-inject 區塊） |
| `rust/openclaw_engine/src/main_boot_tasks.rs` | 修改 | 1015 → **816** | 移除 type alias + spawn fn + 不再使用的 `cost_edge_advisor` / `CostEdgeAdvisorSlot` import |

合計：純抽出 location，原 ~210 LOC（22 in main.rs + ~187 in main_boot_tasks.rs
含 doc）→ 279 LOC（sibling）+ ~25 LOC（main.rs 接線殘留）。淨 +94 LOC（多
出來的是 sibling 自己的 MODULE_NOTE 雙語標頭 + 2 個 helper 的 doc）。

---

## 3. 關鍵 diff

### main.rs — Wave 1 spawn 區塊（22 LOC → 11 LOC）

```rust
// G3-09 cost_edge_advisor — see sibling `cost_edge_advisor_boot`
// for full doc / G3-09 cost_edge_advisor — 詳見 sibling 模組。
let cost_edge_advisor_slot_handle = ipc_server.cost_edge_advisor_slot();
let cost_edge_advisor_db_pool_slot = cost_edge_advisor_boot::create_db_pool_slot();
cost_edge_advisor_boot::spawn_cost_edge_advisor_if_enabled(
    &cost_edge_advisor_slot_handle,
    &h_state_cache_slot_handle,
    &risk_stores,
    &cancel,
    &cost_edge_advisor_db_pool_slot,
);
```

### main.rs — late-inject 區塊（13 LOC → 2 LOC）

```rust
// G3-09 Phase B late-inject DbPool / G3-09 Phase B：late-inject DbPool。
cost_edge_advisor_boot::inject_db_pool(&cost_edge_advisor_db_pool_slot, &db_pool).await;
```

### cost_edge_advisor_boot.rs — type alias + 2 helper

```rust
pub type CostEdgeAdvisorDbSlot = Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>;

#[inline]
pub(crate) fn create_db_pool_slot() -> CostEdgeAdvisorDbSlot {
    Arc::new(tokio::sync::RwLock::new(None))
}

#[inline]
pub(crate) async fn inject_db_pool(slot: &CostEdgeAdvisorDbSlot, pool: &Arc<DbPool>) {
    *slot.write().await = Some(Arc::clone(pool));
}
```

`spawn_cost_edge_advisor_if_enabled` body 與 main_boot_tasks.rs 原版逐字
相同（含全部三階段 spawn + warn log + engine_mode hardcode "demo"）。

### main_boot_tasks.rs — 移除的 imports

```diff
- use openclaw_engine::cost_edge_advisor::{
-     is_advisor_env_enabled, spawn_cost_edge_advisor_with_persistence, CostEdgeAdvisor,
-     DEFAULT_POLL_INTERVAL as COST_EDGE_DEFAULT_POLL_INTERVAL,
- };
- // [Phase B comments + type alias 8 LOC]
- pub type CostEdgeAdvisorDbSlot = Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>;
- use openclaw_engine::ipc_server::{CostEdgeAdvisorSlot, HStateCacheSlot, PerEngineRiskStores};
+ use openclaw_engine::ipc_server::{HStateCacheSlot, PerEngineRiskStores};
```

`use openclaw_engine::database::pool::DbPool;` + `use openclaw_engine::config::{ConfigStore, RiskConfig};`
保留（其他 fn 仍用）。

---

## 4. 驗收

| 項 | 期望 | 實測 | 狀態 |
|---|---|---|---|
| `wc -l main.rs` | ≤ 1200 | **1210** | ⚠️ 10 LOC 超 |
| `wc -l main_boot_tasks.rs` | ≤ 800 首選 / ≤ 1015 acceptable | **816** | ✅ acceptable（≤865 PA target，距 800 warn 16 LOC） |
| `wc -l cost_edge_advisor_boot.rs` | ≤ 800 | **279** | ✅ |
| `cargo build --release -p openclaw_engine` | OK | OK（4 pre-existing warnings，無新 warning 來自新檔） | ✅ |
| `cargo test --release -p openclaw_engine --lib` | 2299/0 | **2299/0** | ✅ 與 baseline 完全一致 |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon` | 11/0 | **11/0** | ✅ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_persistence` | 2/0（Mac auto-skip） | **2/0**（Mac 實跑通過） | ✅ |
| 0 production behavior change | ✅ | ✅（spawn fn body 逐字相同；`inject_db_pool` 與原 inline `*slot.write().await = Some(Arc::clone(...))` 語意一致） | ✅ |

---

## 5. 治理對照

- **CLAUDE.md §九 文件大小** — main.rs 仍 10 LOC 高於 1200 硬上限；
  main_boot_tasks.rs 從 1015 降到 816（仍 16 LOC 高於 800 警告線，但 PA RFC
  acceptable target ≤865 達標）。
- **CLAUDE.md §七「跨平台合規」** — 無路徑硬編碼新增；新 sibling 純
  Rust + Arc + tokio std lib，無平台特定依賴。
- **CLAUDE.md §七「雙語注釋」** — 新 sibling 含 MODULE_NOTE 中英對照
  + type alias / 2 helper / spawn fn 全 docstring 中英對照（spawn fn doc
  逐字保留 main_boot_tasks.rs 原版）。
- **CLAUDE.md §九 singleton 表** — 新增的 `CostEdgeAdvisorDbSlot` (rust)
  本來就在 §九 表中（記為 `main_boot_tasks.rs` 出處），需在 PM 統一 commit
  時更新出處為 `cost_edge_advisor_boot.rs`。**標示為 follow-up**，本 ticket
  不修 CLAUDE.md 避 scope creep。
- **CLAUDE.md §二 16 條根原則** — 0 觸碰。spawn fn body 逐字保留（DEFAULT-OFF
  env-gate 邏輯不變）；late-inject 行為不變（`inject_db_pool` 內部就是
  `*slot.write().await = Some(Arc::clone(pool))`）。

---

## 6. 不確定之處

### A. main.rs 仍 10 LOC 超硬上限（>20% LOC 偏離 PA RFC 預估）

**PA RFC 預估**：main.rs 1230 → ~1010（drop ~220 LOC）。
**實測**：main.rs 1230 → 1210（drop **20 LOC**）。

**原因分析**：
- Wave 1 在 main.rs 加的 wiring 只有 22 LOC（line 507-525）；剩 8 LOC 是
  pre-existing over-cap（main.rs pre-Wave-1 已 1208）。
- 抽掉 Wave 1 的 22 LOC + 7 LOC late-inject 註解 + 1 LOC `mod` 註冊 = -28；
  但 + 11 LOC inline stub + 2 LOC 縮短的 late-inject = +13。淨 -20 LOC。
- PA RFC 「drop ~220 LOC」似乎假設可抽出更大區塊。實際 main.rs:507-525 只
  22 LOC（Wave 1 真實 footprint），無 220 LOC 的可抽出量。

**處理**：
- 已將可抽範圍最大化（type alias / spawn fn / `create_db_pool_slot` /
  `inject_db_pool`）。
- 進一步降低 main.rs LOC 須觸碰 **非 Wave 1 / 非 cost_edge_advisor** 的
  unrelated 區塊（如其他 boot wiring 或 setup helpers），**已超出本 ticket
  scope**（E1 規則：「不擴大 PA 給定的改動範圍」）。
- E1 boundary 觸發：「若 LOC 預估偏離 >20% → 回報主會話」。本回報文檔即為
  「回報」動作，等 PA / PM 決定：(a) 接受 1210 略超 + 標 P3 follow-up 後續
  trim / (b) 派額外 ticket 抽其他 main.rs 區塊。

**注意**：CLAUDE.md §九「不允許 merge」是 governance gate（人工審查），不是
編譯/測試 gate；engine binary 完全可運作，純檔案大小 governance 紅燈。

### B. main_boot_tasks.rs 還有 16 LOC 高於 800 警告線

PA RFC acceptable target ≤865，實測 816。已達 acceptable。如要降到 ≤800
警告線，需抽其他 fn（出 scope）。建議標 P4 follow-up。

### C. 跨平台

純 Rust refactor，無平台分歧。Mac/Linux 行為一致。`cargo test
test_cost_edge_advisor_persistence` 在 Mac 上 2/0 全綠（未 skip，與 ticket
spec 的「Mac auto-skip」描述不同，這是好事 — 邏輯不變）。

### D. PM commit 時注意

- CLAUDE.md §九 singleton 表 `CostEdgeAdvisorDbSlot` 出處需從
  `main_boot_tasks.rs` 改為 `cost_edge_advisor_boot.rs`。
- `.claude/agents/.gitignore` 等不需動。
- 新檔 `cost_edge_advisor_boot.rs` 須 `git add`。

---

## 7. Operator 下一步

1. **E2 審查**重點：
   - 確認 spawn fn body 與原 main_boot_tasks.rs:459-613 逐字一致
     （`diff` 兩段內容應只差縮排）
   - 確認 `inject_db_pool` 語意與原 `*cost_edge_advisor_db_pool_slot.write().await
     = Some(Arc::clone(&db_pool))` 完全等價
   - 評估 main.rs 1210 略超 1200 是否接受 / 派額外 ticket
2. **E4 回歸**：lib 2299/0 / daemon 11/0 / persistence 2/0 已驗，無回歸；
   E4 可加跑其他 integration test 套件（test_h_state_gateway / 等）做 sanity。
3. **PM commit**：等 E2 + E4 通過後統一 commit + push；同 commit 內順手更新
   CLAUDE.md §九 singleton 表 `CostEdgeAdvisorDbSlot` 出處。
4. **Follow-up tickets**（若 PA / PM 決定保 main.rs ≤1200）：
   - **G3-09-FUP-MAIN-RS-FURTHER-TRIM (P3)**：抽 main.rs 其他 ≥10 LOC 區塊
   - **G3-09-FUP-MAIN-BOOT-TASKS-WARN-CLEAR (P4)**：再抽 16 LOC 進 ≤800 警告
