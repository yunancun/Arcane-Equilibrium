---
name: governance-continuation-delta-protocol
description: agent_governance.py continuation 只能在本輪確有 admitted dirty_scope 位元組變更後呼叫一次;空呼叫或 scope 漂移會把 admission 判 BLOCKED_NO_DELTA 且該 admission 就此終結
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 55161662-fa9a-41a3-b950-a8943a4c3b03
  modified: 2026-07-26T08:21:39.473Z
---

`agent_governance.py continuation` 是**一輪一次、且必須在做完工作之後**才呼叫的裁決,不是狀態查詢。

**Why:** 它比對「當前 admitted `dirty_scope` 的 source bytes」與「admission 快照」。兩種情況會判 `BLOCKED_NO_DELTA`:
1. 剛 acquire 完 admission 就呼叫(還沒動任何檔)——快照與現況當然相同;
2. 本輪確實做了大量工作,但改的檔**不在** admission 當初綁的 `dirty_scope` 內(長跑任務隨 wave 推進,擁有面會從 W1 期檔案漂到 W2/W3 期檔案)。

關鍵:`BLOCKED_NO_DELTA` 對該 admission 是**終結**的。之後對同一 `admission_id` 再呼叫 continuation 只會回
`{"status":"FAIL","reasons":["TASK_ADMISSION_TERMINAL"]}`,必須 release 舊 admission 再 acquire 新的(舊的沒 release 就 acquire 會回 `WORKTREE_TASK_ADMISSION_HELD`)。

**How to apply:**
- 每輪順序固定:acquire/沿用 admission → 做實工並 commit → **呼叫一次** continuation → ScheduleWakeup。絕不在輪首或「順手查一下」時呼叫。
- 長跑 loop 的 `dirty_scope` 要涵蓋**當前 wave 會動到的面**,包含 PM 每輪必落帳的 `PROGRESS.md` / `TODO.md`;否則純 ledger 輪會被判無 delta。
- Wave 推進造成的 scope 漂移是 AGENTS.md 明訂要「顯式重新 admission」的情形,不是可以無視的雜訊——照 release → 重建 contract(新 `dirty_scope` + 誠實的 `previous_failure`)→ acquire 走一遍。

見 [[project_2026_07_12_reconcile_pathb_arc]] 家族的 AIML S2 長跑弧。
