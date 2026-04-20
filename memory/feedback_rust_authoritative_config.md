---
name: Rust 為唯一交易參數權威
description: 所有交易/風控參數 GUI 直寫 Rust，Python 僅作只讀展示層，禁止 Python 持有可寫狀態
type: feedback
---

所有交易相關參數（風控、策略、模型、cost gate、cooldown 等）必須由 Rust 持有並持久化。GUI 修改參數時直接走 IPC 寫入 Rust，Rust 根據新參數調整交易邏輯與模型。Python 如果必須保留，只能作為 GUI 的**只讀**接口（IPC 拉 Rust 狀態 → 渲染），禁止任何寫入路徑或本地配置檔案。

**Why:** 雙系統並存導致語義分歧、競態、審計困難。Phase 4.1 default-off 翻 enabled 前必須消除雙風控債務（ARCH-RC1）。用戶 2026-04-07 明確要求 Python 風控徹底廢掉，界線一刀切。

**How to apply:**
- 新加任何交易/風控/模型參數 → 預設加在 Rust，IPC 暴露 get/set
- 看到 Python 端寫 JSON config / 改交易參數 → 立即標記為違反契約
- GUI 表單改參數 → 必須轉發到 Rust IPC，禁止 Python 本地持久化
- Python 模組只能呼叫 `get_*` 類 IPC，不能呼叫 `update_*`（除非是純轉發 GUI 請求）
- 驗證：`grep` Python 端不應再有 `_save_*config` / `json.dump.*config` 模式

**熱重載硬要求（不可妥協）：**
- 所有交易/風控/模型參數必須支援運行時熱更新，**禁止 restart-to-apply**
- Tick 熱路徑配置用 `Arc<ArcSwap<Config>>`（lock-free 讀），非熱路徑可用 `Arc<RwLock>`
- IPC `update_*` handler：驗證 → 構造新 Config → `arc_swap.store(Arc::new(new))` → 持久化 JSON → 立即返回，下個 tick 生效
- 狀態機不需要 reload 呼叫，純靠 tick 自然驅動讀取新配置
- Agent 熱調整與 Operator 走同一個寫路徑，僅審計日誌標記 source 區分
- Why: Agent 會在引擎運行時熱調參數，Operator 也會動態調整風控；每次重啟不合理
