---
name: Sub-agents CAN write code — 2026-04-07 refuse 解除 / 2026-04-24 新 silent-failure 風險
description: refuse pattern 已於 2026-04-18 解除，但 2026-04-24 發現新 failure mode：multi-session stash race 下 subagent commit 只 add 不 modify，新 sibling 成 orphan；主 session 必 post-hoc 驗證
type: feedback
originSessionId: 7c05d736-4788-46a8-b62d-30efc56dda85
---

## 🆕 2026-04-24 新增：Sub-agent silent failure pattern（G1-03 startup refactor 實證）

**場景**：G1-03 refactor startup.rs 1377→1131 派 subagent A。Agent 報告 "commit `39773e1` pushed, 1131 lines"。但審計發現：

- `git show --stat 39773e1` 只顯示 `startup/private_ws.rs +293`（新建 sibling），**無** startup.rs → startup/mod.rs 改動
- `startup/mod.rs` 仍 **1377 行**（原始內容未動）
- 新 sibling `private_ws.rs` **orphan**（mod.rs 無 `mod private_ws;` decl，不編譯）
- `cargo test` 仍 1990 passed — 因為 orphan file 被 cargo 忽略，原 mod.rs 自足

**Root cause**：Subagent 寫了兩個操作（add sibling + remove duplicate from mod.rs）。multi-session stash race 下其他 session 的「drift not mine」stash 腳本把「remove duplicate」這步回退，只留「add sibling」。Subagent 的 `git commit --only <my files>` 成功但只 commit 了未被 stash 的一半。

**審計方法**：主 session 收 subagent "done" 後必跑：
1. `git show --stat <commit>` — 實際變更 LOC ≈ 聲稱 LOC？
2. `wc -l <target_file>` — 目標檔案真的縮小到聲稱值？
3. `grep -n "mod <new_sibling>" <parent>` — 新 sibling 真的被引用？（防 orphan）
4. `grep -n "^pub.*<extracted_item>" <parent>` — duplicate 真的被刪？
5. 若 cargo test pass 但檔案沒瘦 = silent failure 信號

**本 session 修復**：commit `ab03dcb` 補做 mod.rs deletion + add mod decl，startup/mod.rs 1377→1126 真正達標。

**How to apply**：
- 派 subagent 做 refactor（尤其 extract-to-sibling pattern）後**必**走上述 5 步 audit
- 若多 session 並行：prefer atomic bash chain (sed + commit 同 call) 取代 subagent；subagent 寫碼脆弱
- TODO 標「completed」前必對照 `git show --stat` 不要信 commit message 宣稱

---

## STATUS 2026-04-18 ✅ RESOLVED (refuse pattern 部分)

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
