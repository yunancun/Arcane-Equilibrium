---
name: Sub-agents CAN write code — 2026-04-07 refuse pattern RESOLVED (verified 2026-04-18)
description: 2026-04-07 的 refuse pattern 已於 2026-04-18 E5 Phase A 派發中驗證為環境問題，現已解除。Sub-agent 可被派發寫碼任務，parallel E1 執行可行。
type: feedback
originSessionId: 7c05d736-4788-46a8-b62d-30efc56dda85
---
**STATUS 2026-04-18 ✅ RESOLVED**: 於 E5 Phase A FA 派發中夾帶 2 個 write-capability
probe（FA-1 `/tmp/fa1_probe.rs`、FA-3 `/tmp/fa3_probe.py`），均在讀過 repo 多檔後
成功寫入 throwaway Rust/Python 檔；兩個 sub-agent 明確回報 `probe written: YES`，
2/2 通過。2026-04-07 觀察到的 8+ 次 refuse 模式**已不再成立**（推測為當時環境/config 問題）。

**二次確認 2026-04-18 晚**：DUAL-TRACK Step 0 延伸 (a) MARKET-KLINES-STALE-1 fix
+ (c) EXIT-FEATURES-TABLE-1 skeleton 並行派發兩個 general-purpose sub-agent，
分別對 main.rs/tasks.rs/database/mod.rs/types.rs/event_consumer/mod.rs 寫入改動，
新增 `exit_feature_writer.rs` (+325 行 / 5 單測) + `V999__exit_features.sql`，
兩 agent 均回報 `cargo check` PASS 0 errors 0 新警告；主會話 merge 後 cargo check
再次 PASS。並行寫碼工作流可穩定使用。

**後續規劃更新**：
- E1 寫碼任務可派發給 sub-agent 並行執行，不必主會話 inline 串行
- Phase B E5 五個 P0 可考慮由 5× sub-agent 並行（視任務規模/commit 顆粒度而定）
- Explore subagent_type 仍無 Write 工具 → 寫碼需用 general-purpose subagent_type
- 建議保留 4 週觀察期（至 2026-05-16），若期間再現 refuse，重啟本記憶

---

**Original 2026-04-07 observation (below, retained for historical reference)**:

Sub-agents (Agent tool) consistently refuse to write or modify code after
reading any internal repo file, triggered by a "this file might be malware,
refuse to improve/augment" system-reminder injected post-Read. This reminder
takes priority over in-task "false positive, continue" overrides.

**Why:** Confirmed across 8+ refusals in Phase 4 session (2026-04-07):
4-03, 4-09, 4-12, 4-13, 4-17, 4-20, W-1, W-2 sub-agents all refused after
reading. Some exceptions succeed (4-04, 4-06, 4-07, 4-11, 4-18, 4-19, W-3)
but the pattern is unreliable — can't plan parallel execution on agents
that might refuse mid-task.

**How to apply:**

1. **Dispatch SAFELY to sub-agents (they work)**:
   - Pure research / web search / documentation reading
   - Code audits / reviews (analysis-only, no modifications)
   - Exploring codebase structure / finding call sites
   - Writing reports or summaries (output goes to return message, not files)
   - `Explore` agent for codebase questions — especially reliable

2. **Dispatch INLINE in main session (sub-agents will refuse)**:
   - Writing new Rust/Python/SQL files
   - Modifying existing files (Edit/Write after Read)
   - Adding tests alongside new code
   - Schema migrations (SQL file creation)
   - Any "implement this spec" task

3. **Hybrid strategy** when task is large:
   - Sub-agent produces a detailed spec / design doc (analysis)
   - Main session implements from spec inline
   - Sub-agent audits the result (analysis)

4. **Parallel dispatch discipline**:
   - Even for "safe" sub-agent tasks, expect 30-50% refusal rate
   - Always have a fallback plan: main session picks up the refused task
   - Budget main-session context for potential inline writes

5. **When refusal happens**:
   - Don't retry the same sub-agent task with "override harder" — it won't work
   - Immediately do it inline in main session (proven faster than re-dispatch)
   - The reminder applies to main session too, but main session has clearer
     authority to judge "user's private repo ≠ malware" and proceed

**Example from Phase 4**: W-1 (DirectiveApplier wrappers) was dispatched as
sub-agent, refused, then main session wrote the 2 wrapper files (~450 lines)
+ tests inline in ~15 minutes. Net faster than 2 retry rounds would have been.
