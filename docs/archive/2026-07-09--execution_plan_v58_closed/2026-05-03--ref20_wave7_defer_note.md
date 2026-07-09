# REF-20 Wave 7 Defer Note — P5 Agents Monitor 抽出

**日期：** 2026-05-03
**狀態：** **DEFERRED** — Wave 7 hard prereq not GREEN
**Owner：** PM (operator full-autonomy mode)
**契約上游：** [`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`](2026-05-03--ref20_implementation_workplan_v1.md) §1 Wave 7 + §4 Wave 7 + §6 hard prereq #7

---

## 1. Defer 原因 / Why deferred

Wave 7 = REF-20 P5 Agents Monitor 抽出（4 task：A1 抽出位置決策 / A2 redirect notice / A3 既有 agent-tracker 保留 / A4 icon）。

Per workplan §6 hard prereq table row #7：
> **LG-2/3/4 frontend merged + 7d stable** — Wave 7 entry

**當前狀態（2026-05-03 14:00 UTC PM check）：**
- LG-2/3/4 = "Phase 3 Batch 3 fragmented" — RFC docs land but **frontend IMPL 0%**（per workplan §6 + memory `project_18_agent_runtime_wired.md` + `project_agent_tracker_mvp_shipped.md`）
- Most recent agent tracker land: 2026-04-28 (commit 884531a, `feature/agent-tracker-mvp` branch — MERGED to main but PM doesn't have stability evidence)
- 7d stable healthcheck PASS metric: **NOT YET MEASURED** (need passive_wait_healthcheck.py 7-day window)

事件觸發 dispatch 標準 = LG-2/3/4 frontend merged AND 7d stable healthcheck PASS。當前 ≤2/2 條件 GREEN。

PM 全自主模式不能 unilaterally 啟動 Wave 7（會 break workplan §6 contract + 引入 sibling CC race risk）。

---

## 2. 自動 re-check 排程 / Re-check schedule

PM 設定 weekly re-check：
- 每週一 09:00 UTC pull latest main + check LG-2/3/4 frontend health metric
- 如 7d window 滿足 → auto-dispatch Wave 7 batch
- 如 prereq 持續 deferred > 14d → escalate to operator with status report

機制（實作建議，非本 task scope）：
- Cron job in `helper_scripts/cron/ref20_wave7_prereq_monitor.sh`（reserved task; not yet implemented in this commit）
- 或 GitHub Actions weekly schedule
- 或 operator 手動 ping PM session 觸發

---

## 3. Wave 7 task 範圍 (forward-looking, IMPL 等 prereq)

per workplan §4 Wave 7（13-task IMPL plan reserved）:

### R20-P5-A1: 12-Tab top-level 抽出位置決策
- A3 + FA arch + E1a 主筆
- File: `program_code/.../control_api_v1/app/static/console.html` nav update +
       `program_code/.../control_api_v1/app/static/tab-agents.html` (NEW)
- Sprint: 0.5

### R20-P5-A2: Learning Tab redirect notice
- E1a + A3 + TW i18n
- File: `program_code/.../control_api_v1/app/static/tab-learning.html` (worktree isolation)
- Top banner div + 90d auto-dismiss
- Sprint: 0.5

### R20-P5-A3: 既有 agent-tracker.js 行為保留
- E1a + A3 + E4 regression
- File: `program_code/.../control_api_v1/app/static/tab-agents.html` + `agent-tracker.js`
- 5 卡 + feed + budget UI 不破
- Sprint: 0.5

### R20-P5-A4: 新 Tab icon
- A3 主筆 (read-only)
- File: `console.html` + `tab-agents.html`
- Sprint: 0.1

**Total Wave 7 scope: 1.6 sprint**（per workplan §4 estimate）

---

## 4. PM autonomous decision rationale

Per operator instruction (2026-05-03 PM session):
> 「Wave 7 dispatch: P5 Agents Monitor (event-triggered, may defer)」
> 「全自主推進至 Wave 7。不 require operator 允許。除非撞 compact 或快 compact 才 ping」

PM autonomous decision tree:
1. ✅ Wave 6 closed (commit eb5f106)
2. ⏳ Wave 7 prereq check: LG-2/3/4 frontend stable
3. ❌ Prereq NOT GREEN
4. → DEFER Wave 7 + write this note
5. → Update TODO + Schedule re-check
6. → Ping operator with closure report (Wave 1-6 summary)

非 ping operator 等 LG-2/3/4 frontend stable evidence；當 prereq GREEN 時自動 dispatch。

---

## 5. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM (autonomous mode) | Wave 7 defer 記錄；hard prereq LG-2/3/4 stable NOT GREEN；scheduled re-check + auto-dispatch on event |

---

## 6. Cross-References

- 上游：[Implementation Workplan V1](2026-05-03--ref20_implementation_workplan_v1.md) §1 Wave 7 + §4 + §6 hard prereq #7
- Wave 6 closure: commit `eb5f106` (2026-05-03)
- Memory: `project_agent_tracker_mvp_shipped.md` + `project_18_agent_runtime_wired.md`
- 相關 sibling CC work: LG-2/3/4 RFC docs (search `docs/**/LG*`)

Wave 7 IMPL 待 LG-2/3/4 frontend merged + 7d stable evidence；event 觸發 dispatch。
