# E1 報告 — Phase 2 PROMOTION_EDGE_SLOT 接線（E1-C 整合 seam）

- 日期：2026-06-17
- 角色：E1（Backend Developer）
- 狀態：IMPL DONE，待 E2 審查（不 commit；dirty multi-session worktree）
- repo root：/Users/ncyu/Projects/TradeBot/srv

## 1. 任務摘要

E1-A 在 Phase 2 build 留下整合 gap：`evaluate_promotion_criteria`（唯讀 IPC）讀
process-global `PROMOTION_EDGE_SLOT`（`OnceLock<Arc<parking_lot::RwLock<EdgeEstimates>>>`），
但無人注入 → handler 永遠走 fail-soft else 分支回 `criteria_engine_uninitialized` →
route 視為 Pending（gate 永不評真 edge）。本 task 接線注入真 EdgeEstimates，外科手術式，
**不動 criteria 邏輯 / migration / Python route**。

## 2. holder 身分確認（task point 2）

grep 全 crate 確認：程序內**只有一個** scanner `EdgeEstimates` holder。

- 構造唯一處：`main_scanner_init.rs:127-134`
  `Arc::new(parking_lot::RwLock::new(EdgeEstimates::load_from_env_or_default(&base)))`，
  載 `settings/edge_estimates.json` 的 validated-edge 資料。
- 暴露：`ScannerInitBundle.edge_estimates`（`main_scanner_init.rs:68`）。
- 流入 main.rs：`main.rs:352` 解構為 `scanner_edge_estimates`。
- Phase 1 用同一個：`main.rs:942 spawn_strategist_scheduler(..., &scanner_edge_estimates)`
  → `main_boot_tasks.rs:192` 收為 `edge_estimates` 參數 → `main_boot_tasks.rs:347`
  `.with_edge_store(Arc::clone(edge_estimates))`。

故我注入的 Arc 與 Phase 1 strategist `with_edge_store`、scanner scorer、position
reconciler（`main_boot_tasks.rs:97`）收的是**完全同一個** Arc。促升判定與 Phase 1
rich-input gate 讀同一份記憶體 snapshot。

**無 ambiguity**：不存在 per-engine live holder（只有這一個共享 scanner holder）；
demo/live 共用同份 production `edge_estimates.json`，promote 判定吃 leak-free
`validation_passed` OOS alpha + freshness（與引擎模式無關，§2.4.B）。當前 demo-only
runtime（無 live pipeline）注入此 scanner/demo holder 即正確。E1-A 原 doc 宣稱「必注入
live engine snapshot」是過期 overclaim（實際無 per-engine live holder），已同步訂正。

## 3. 修改清單（4 檔）

1. `rust/openclaw_engine/src/main.rs`（+16）— 注入點。boot 期、緊鄰 Phase 1
   `spawn_strategist_scheduler` call（同源 holder 旁），**無條件** call
   `openclaw_engine::ipc_server::set_promotion_edge_slot(Arc::clone(&scanner_edge_estimates))`
   + info! log。刻意不放 scheduler fn 內部（Demo 未綁時該 fn 早退會漏注入唯讀 handler）。
2. `rust/openclaw_engine/src/ipc_server/mod.rs`（+4）— facade re-export
   `pub use dispatch::set_promotion_edge_slot;`（`mod dispatch` 私有，binary crate
   `openclaw-engine` 經 facade 取 lib 內部，鏡像 `pub use server::IpcServer`）。
3. `rust/openclaw_engine/src/ipc_server/dispatch.rs`— setter `pub(crate)`→`pub` +
   移除 `#[allow(dead_code)]`（現有 caller）；訂正 setter doc + slot doc（去除「必注入
   live engine」overclaim，改述「同源 scanner holder + 引擎模式無關」實況）。**未動
   criteria 邏輯**（`promotion_criteria.rs` git diff 為空）。
4. `docs/architecture/singleton-registry.md`（+§2.8）— 登記 `PROMOTION_EDGE_SLOT`
   （鏡像 §2.7 NonceLedger 格式：name/type_signature/location/owner_lifecycle/
   cross_task_pattern/lock_primitive/visibility/caller_chain/health_monitoring/
   registered_date/governance_authority/migration_plan）。

## 4. 關鍵 diff（接線三點，同一 static）

- producer：`main.rs:926` `set_promotion_edge_slot(Arc::clone(&scanner_edge_estimates))`
- facade：`mod.rs:83` `pub use dispatch::set_promotion_edge_slot;`
- setter：`dispatch.rs:896` `pub fn set_promotion_edge_slot(...) { PROMOTION_EDGE_SLOT.set(edge).is_ok() }`
- consumer：`dispatch.rs:1005` `let Some(edge_arc) = PROMOTION_EDGE_SLOT.get() else { ...criteria_engine_uninitialized... }`

注入後 `.get()` 回 `Some` → 不再走 uninitialized else 分支 → 進真 per-cell 自查路徑。

## 5. 治理對照

- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority /
  system_mode；未動 5-gate；handler 仍純唯讀 fail-closed（未注入=Pending）。
- 新 singleton 登記：singleton-registry.md §2.8（CLAUDE §七/§九 要求 merge 前登記）。
- 注釋規範：新註釋中文為主，技術詞英文保留；訂正過期誤導 doc（governance trail）。
- 範圍：未動 criteria 邏輯 / migration / Python route（task 明令）。
- 跨平台：注入用既有 `scanner_edge_estimates` 變數，無硬編路徑。

## 6. 驗證結果

- `cargo build -p openclaw_engine`：clean。3 個 warning 全 pre-existing 且與我無關
  （unused import `LEAD_WINDOW_SECS_MAIN`、failsafe watcher 欄位、`make_intent`）；
  **無 dead_code warning on setter**（binary 現有 caller + facade pub re-export）。
- `cargo test -p openclaw_engine --lib`：**3987 passed; 0 failed; 1 ignored**。
  - promotion_criteria 純函數 23 test 全綠（含 zero_validated_cells_is_pending_not_eligible）。
  - method_registry `evaluate_promotion_criteria_is_readonly_no_slot` /
    `evaluate_promotion_criteria_not_in_live_write_methods` 綠（readonly + token 豁免不變）。
  - edge_estimates suite 全綠。
- 碼級接線可達確認（Mac 限制，無真 engine/PG）：producer(main.rs)→facade(mod.rs)→
  setter(dispatch.rs)→`PROMOTION_EDGE_SLOT` ← consumer(handler `.get()`) 全 reference
  同一 static；注入 Arc = Phase 1 同源（main.rs:352 同變數）。

## 7. 不確定之處 / E4 owed

- **runtime 行為（注入後 0-validated cell 回 Pending 而非 uninitialized）= E4 Linux
  empirical**：Mac 無真 engine，只能驗碼級接線可達 + 純函數/單元測試綠。E4 須在 Linux
  起引擎、對 `evaluate_promotion_criteria` 發 IPC、確認回 verdict（per-cell 自查）而非
  `criteria_engine_uninitialized`。
- dirty multi-session worktree：dispatch.rs 在 git diff 顯示 +244（E1-A 整個 Phase 2
  block 在此 worktree 未 commit），我的編輯僅其中 setter 可見性/doc + slot doc；其餘
  Phase 0/1/2 + Python routes 是並行 session 的改動，非我。

## 8. Operator / 下一步

1. E2 對抗審查（聚焦：注入點無條件性、facade 可見性最小化、doc 訂正正確、單一 holder
   論證、未越界改 criteria）。
2. E2 PASS → E4 Linux 回歸 + runtime empirical（注入後 handler 不回 uninitialized）。
3. E4 GREEN → QA → PM 統一 commit + push（強制鏈，不跳）。
