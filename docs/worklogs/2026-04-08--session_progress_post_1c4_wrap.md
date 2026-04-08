---
title: Session progress — post 1C-4 wrap (smoke test + 1C-3-D cleanup + DEAD-PY-1 + doc trim)
date: 2026-04-08
session: post-1c4-wrap
ends_at_commit: d10becc
---

# Session 進度（1C-4 wrap 之後）

接續 `f882473`（1C-4 doc sync wrap）之後的工作。本 session 4 個 commit：

## Commits

| Commit | 摘要 |
|---|---|
| `8554779` | **1C-3-D 留尾清理** — RiskViewClient 9 個 deprecated stub 方法 + helper + test 刪除；strategy_wiring `_RISK_MGR_REF.set_h0_gate` 注入區塊刪除；17 個 `.smbdelete*` Samba ghost 檔清除（~700KB）。0 regression。|
| `967f420` | **TODO.md DEAD-PY-1** — sub-agent 死代碼掃描 ~42 個候選項，4-phase plan 寫入 TODO.md「1C-4 留尾」段（Phase 1 SAFE-DELETE ~2h / Phase 2 CHECK-ROUTES ~1h / Phase 3 STALE-COMMENT ~3h / Phase 4 GUI ~1h，共 ~7h，risk LOW，非阻塞）|
| `d10becc` | **主檔瘦身** — CLAUDE.md 363→348 / TODO.md 237→218 / README.md 368→301 = 總 -139 行 (-14%)。新建 `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md` (167 行) 捕捉移除的 1C-3 SHIPPED narrative + README 過期 block + A-J 表 |

## 關鍵驗證（用戶 3 個確認問題）

1. **止損引擎** ✅ 唯一 Rust：`openclaw_core/src/stop_manager`，`paper_state.check_stops` + `tick_pipeline` 消費。1C-3-F 後 Rust openclaw_engine = paper/demo/live 三模式唯一引擎。
2. **學習引擎** ⚠️ 部分接上：LearningConfig 已熱重載 + IPC patch 可寫，但 `main.rs:198-200` 注釋 "learning_store currently has no consumer"。Phase 4.1 Claude Teacher consumer loop ✅ 已 spawn (`main.rs:1097-1110` TeacherConsumerLoop)。**LearningConfig → 學習動作的閉環尚未連通**。
3. **新聞引擎** ⚠️ 接好沒開動：`rust/openclaw_engine/src/news/pipeline.rs` `NewsPipeline::run_once` 完整實現，`NewsContextSnapshot` + `GuardianHaltCheckImpl` 在 main.rs 已 wire 進 guardian/governance。**缺 60s scheduler spawn（A2 任務，待 4-09 router 決策）**。

## Binary + GUI 驗證

- `cargo build --release -p openclaw_engine` ✅ 16s, 0 errors, 7 warnings (unused vars 級)
- `python3 main.py import` ✅ 183 routes registered
- `pytest --co` ✅ 2716 tests collected
- 全套測試 control_api 2693 passed + 1 skipped = **2694**（與 1C-4 baseline 完全一致）+ 21 pre-existing fail · **0 regression**

## 測試基準線（不變）

```
Rust  engine lib 767 · core 387 · types 27 · ml_training 35
Python control_api 2694 passed (21 pre-existing fail · 0 regression)
```

## 下一步建議排序（梳理後）

| 優先 | 任務 | 估時 | 阻塞 |
|---|---|---|---|
| P0 | 啟動 7d paper trading 觀察期（calendar-time 計時）| 7 天 | 無 |
| P1 | 多通道告警 OC-3 設計 + 落地 | ~1 週 | 無，可與觀察期並行 |
| P1 | DEAD-PY-1 Phase 1 SAFE-DELETE | ~2h | 無 |
| P2 | A2 NewsPipeline scheduler | ~5h | 4-09 router 決策 |
| P2 | DEAD-PY-1 Phase 2/3/4 | ~5h | Phase 1 完成 |
| P3 | Phase 5 spec 起草（James-Stein + DL-1/DL-2）| ~1 週 | 觀察期數據累積 |

並行建議：觀察期 7 天純時間消耗，可同時推進 OC-3 + DEAD-PY-1 全 4 phase + Phase 5 spec 三條獨立軌道。

## 接手 checklist（compact 後新 session）

1. `git log --oneline -8` 確認 HEAD = `d10becc`
2. 讀 `TODO.md` 找第一個 `[ ]`（目前是 A2 News scheduler 或 DEAD-PY-1 Phase 1）
3. 7d 觀察期開始日期需從用戶或 git log 確認
4. 學習/新聞 engine 部分接線狀態已寫入 README.md 当前状态 block，無需重新調查
