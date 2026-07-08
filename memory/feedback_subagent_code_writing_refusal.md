---
name: Sub-agents CAN write code — 2026-04-07 refuse 解除 / 2026-04-24 新 silent-failure 風險
description: refuse pattern 已於 2026-04-18 解除，但 2026-04-24 發現新 failure mode：multi-session stash race 下 subagent commit 只 add 不 modify，新 sibling 成 orphan；主 session 必 post-hoc 驗證
type: feedback
originSessionId: 7c05d736-4788-46a8-b62d-30efc56dda85
---

> 原 2026-04-07「sub-agent 讀檔後拒寫碼」pattern 已於 2026-04-18 歷史性解除（2/2 write-probe 通過，並行寫碼工作流可穩定使用）；本檔保留僅為下方 2026-04-24 silent-failure 稽核紀律。

## 2026-04-24：Sub-agent silent failure pattern（G1-03 startup refactor 實證）

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
