---
name: Agent 追蹤視圖 MVP shipped (2026-04-28)
description: Learning Cockpit 新加 sub-section「AI 团队工作台」5 卡 + feed + shadow/live diff + governance + 思考預算；對普通人友善、A 級 UX；branch feature/agent-tracker-mvp
type: project
originSessionId: 68a363bd-768c-48ac-8992-3d449bc0f085
---
# Agent 追蹤視圖 MVP（2026-04-28 shipped）

## 範圍

Learning Cockpit (`tab-learning.html`) 新增 sub-section `<section id="agent-tracker">`，6 區塊：
- A: 5-Agent 卡片 grid（偵察員 🔭 / 策略師 ♟️ / 守門員 🛡️ / 執行員 🧤 / 分析師 🔍）
- C: 最近活動 feed
- D: AI 思考預算進度條（MVP 簡化版，三段警示）
- E: 影子 vs 真倉對比（demo + live_demo UNION）
- F: Lease + 守門員拒絕紀錄

## 技術接點

- 新 endpoint：
  - `GET /api/v1/agents/roster` — 5-agent 聚合
  - `GET /api/v1/agents/recent_rejects?limit=N`
  - `GET /api/v1/agents/shadow_vs_live_summary?since=24h`
- 新檔：`agents_routes.py`（334）+ `agents_routes_helpers.py`（783）+ `static/js/agent-tracker.js`（954）
- 改檔：`executor_agent.py`（741→804，補 `shadow_mode` + `orders_submitted` 入 `get_stats()`）+ `strategist_agent.py`（782→824，加公開 `get_scan_interval_seconds()`）
- 跨 800 警告線兩檔：governance accept + P3 backlog ticket（雙語 docstring 不可壓）

## UX A 級 關鍵契約

- Strategist `summary_zh` **後端結構化**（`agents_routes_helpers.py:_compose_summary_zh`）— 不是前端套模板（會退 B 級）
- Executor 卡片 shadow vs live 三層視覺隔離：底色漸層（藍/紅）+ banner + 數字單位變化
- `shadow_mode === null/undefined` 強制紅 unknown「⚠️ 状态未确认，已暂停接单」永不留灰
- 8 條 tooltip 雙語 + 三態文案明確區分（loading/empty/error），失敗文案明說「不是 Agent 掛了」
- 0 寫入按鈕（plan §「對普通人友善」決策；shadow→live 切換維持 5-gate auth endpoint）

## 工作流（多 agent 兩輪）

```
PA + A3 (Plan) → E1-A + E1-B (round 1 並行寫碼) → E2 退 11 finding
→ E1-A + E1-B (round 2 並行修) → E2 round 2 CONDITIONAL APPROVED
→ E4 (Linux pytest 21/21 + baseline 3117→3138 + curl smoke + EXPLAIN ANALYZE) + A3 (Grade A)
→ PM sign-off
```

E2 round 1 catch 4 個 contract drift（Block C/D/E/F 都因 schema mismatch 而死亡）— round 1 E1-B 自報「未驗證」是真實風險，E2 adversarial review 把它驗了。

## 部署狀態

- Branch：`feature/agent-tracker-mvp` HEAD `884531a`（origin 已 push）
- E4 commit `d1c6911`（修 strip-docstring helper test）
- 部署：merge → main → `bash helper_scripts/restart_all.sh --keep-auth`（純 Python+JS，**不需 --rebuild**）
- 4 minor backlog（A3 提）：繁簡一致性（Strategist offline + Guardian summary）/ Block C emoji 增強 / Block E 真倉空態補白
