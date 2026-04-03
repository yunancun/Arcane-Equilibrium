# Rust 遷移階段執行文件索引
# Rust Migration Phase Execution Index

**源文件**：`docs/references/2026-04-03--rust_migration_v3_final.md`（V3-FINAL，不可修改）
**本目錄**：拆分後的階段執行文件，每個文件是獨立可執行的工作單元

---

## 全局時間線

```
Phase 0-3（現有積壓，~7 週）
  ├── Phase 0 Sub-A：學習閉環 + 管線連通
  ├── Phase 0 Sub-B：策略 Edge 驗證
  ├── Phase 1：Agent 感知工具箱 + 認知三模組 ← Rust 00 提前並行開始
  ├── Phase 2：策略 V2 + Agent 整合 ← L1 接口凍結
  └── Phase 3：Claude API + 四階段框架 ← L2 接口凍結

Rust 遷移（14 週主開發）
  ├── 00：提前並行（Phase 1-3 期間）
  ├── 01：IPC + shared_types + WS（W1-2）
  ├── 02：core 上半——感知+認知+風控（W3-4）
  ├── 03：core 下半——SM+執行+回測（W5-6）
  ├── 04：engine 完整交易路徑（W7-8）
  ├── 05：★ Week 8 硬決策點
  ├── 06：Python IPC 改造（W9-10）
  └── 07：灰度驗證 + 穩定觀察（W11-14）
```

## 文件清單

| 文件 | 階段 | 週 | 前置 | 狀態 |
|------|------|-----|------|------|
| [00--preparation_parallel.md](00--preparation_parallel.md) | 提前並行 | Phase 1-3 期間 | 無 | [ ] 待開始 |
| [01--ipc_shared_types_ws.md](01--ipc_shared_types_ws.md) | IPC + 基礎設施 | W1-2 | 00 + L1 凍結 | [ ] 待開始 |
| [02--core_upper.md](02--core_upper.md) | 感知 + 認知 + 風控 | W3-4 | 01 Go | [ ] 待開始 |
| [03--core_lower.md](03--core_lower.md) | SM + 執行 + 回測 | W5-6 | 02 Go | [ ] 待開始 |
| [04--engine_full_path.md](04--engine_full_path.md) | 完整交易路徑 | W7-8 | 03 Go | [ ] 待開始 |
| [05--week8_decision_gate.md](05--week8_decision_gate.md) | 硬決策點 | W8 末 | 04 完成 | [ ] 待決策 |
| [06--python_ipc_integration.md](06--python_ipc_integration.md) | Python 改造 | W9-10 | 05 Go | [ ] 待開始 |
| [07--canary_validation.md](07--canary_validation.md) | 灰度 + 穩定觀察 | W11-14 | 06 Go | [ ] 待開始 |

## Agent 接手規則

1. **每次新 session 先讀本 README** 確認當前進度
2. 找到第一個 `[ ] 待開始` 或 `[~] 進行中` 的階段文件
3. 進入該文件，讀「上下文導航」和「進度追蹤」
4. 完成工作後更新該文件的進度追蹤 + 本 README 的狀態欄
5. **不修改 V3-FINAL 源文件**——階段文件中發現的問題記錄在該文件末尾「問題與變更」區域
