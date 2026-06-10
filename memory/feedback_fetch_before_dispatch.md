---
name: 派 sub-agent 前 fetch + 查遠端 branch + git-log-grep ticket
description: Multi-agent 派發前必 `git fetch` + `git branch -r | grep <topic>` + `git log --oneline --all | grep <ticket-keyword>`；TODO 的「pending」Phase Banner 可能 stale 數天，工作可能已 merge 進 main，派 IMPL 前必 git-log 驗，不可盲信 TODO 狀態
type: feedback
originSessionId: 1d6c6364-1fdb-4b51-a62a-b4624f0fa446
---
規則：任何 multi-agent 並行派發（尤其 Wave-level TODO 批次）之前，必先跑：

```bash
git fetch --prune origin && git branch -r | grep -iE '<topic-keyword>'
git log --oneline origin/main -10  # 看隔壁剛推什麼
```

若匹配到 `origin/fix/<topic>` / `origin/<topic>-*` / 近期 commits 已帶 `<topic>` tag，**先判斷隔壁進度再決定派不派**：
- 已完成 → 跳過，TODO 標 [x] + 指向 commit
- 進行中 → 等或派補充工作（test / doc / review）
- 未動 → 正常派

**Why**：2026-04-24 G6 Wave 1 派發時沒先 fetch，結果：
- G6-01 被**重派** — 隔壁 session 早已開 `origin/fix/g6-01-healthcheck-5-defects` branch 做完 5 缺陷 + FUP [Xb]，我的 sub-agent 讀到 QA audit 後發現 4/5 已修（實際 5/5 都已修），重複工時
- Branch topology 一度混亂 — 我 commit 落到 feature branch `g1-06-drawdown-auto-revoke` 而非 main，需暫停等 operator 判讀 PR-style workflow 意圖
- G6-02 也被隔壁順手做了（commit `a0a4981`），我原計畫「G6-01 完成後接力派」多餘

**How to apply**：
- Multi-session 協作中，派發 sub-agent 或 background agent 前**必** fetch + 掃 branches
- 單 session 線性工作可略（無隔壁併發）
- 派發前一次 fetch 成本遠低於派發後發現重複的處理成本（branch 歸屬討論 / commit 拓撲修復）
- 亦適用：operator 說「隔壁 session 已派 X」時，不要盲信完成狀態，fetch + log 確認實際進度

**2026-05-28 第二次踩雷（升級教訓：不只查 branch，查 ticket 是否已 merge）**：
派 E1 去做 Sprint 2「W2-B IMPL」（TODO Phase Banner 標 IMPL NOT STARTED），但 E1 disk + `git log` 發現 W2-B 早於 **3 天前** 已完整 land（`817de10a` funding_short_v2 + liquidation_cascade_fade +3737 LOC）+ E2 R2/R3 APPROVE + E4 regression PASS。同輪派的背景 PA agent 也只讀 SSOT/dispatch packet/TODO Phase Banner，**沒 git-log grep ticket keyword**，照樣回報「dispatch ready」誤導。
- **Root cause**：TODO 的 Phase Banner 與 git 真相漂移數天；PA agent 與 PM 都信任 TODO「pending」標籤沒驗 disk。
- **救援**：E1 sub-agent 自己 disk check 後做 **NO-OP closure**（不重做 30-40hr），證明 dispatch prompt 留 NO-OP exit path 的價值 — 派 IMPL 的 prompt 應允許 agent「發現已完成則 NO-OP 回報」而非硬寫。
- **升級規則**：派任何 IMPL（非只 review）前，除 branch grep 外，**必** `git log --oneline --all | grep -iE '<ticket-keyword|主要檔名|strategy-name>'` 確認 main 上沒做過；TODO Phase Banner 不是 git 真相，commit 落地時必同步更新 Phase Banner（否則下一個 session 重派）。
- 同樣適用 PA / 任何 planning agent：dispatch prompt 應強制「先 git-log grep，TODO 狀態僅參考」。

**2026-06-10 第三次踩雷（升級教訓：commit 前 re-fetch；branch 有效性會在 session 中途改變）**：
root sweep 任務開工時只看了 git status/log 沒 fetch；工作中途並行 session (a) 在本地 main 搶先做了 SKILLS_TODO 歸檔（`9de97d6e`，檔名不同），(b) 把我所在的 `feature/l2-critic-lessons-tools` 宣告 **SUPERSEDED**（`1f34653c`「勿 merge/rebase/cherry-pick」，L2 內容已 cherry-pick 重放上 main）。我的 3 個 doc commit 全落在死 branch 上+1/3 與 `9de97d6e` 撞車。
- **升級規則**：(1) **每個 commit 批次前 re-fetch**，不只 dispatch 前——branch 在 session 進行中可能被並行 session 廢棄；(2) 發現本地 main 被別的 worktree 占用（`git worktree list`）= 有活躍並行 session 正在治理同域，先看它的 WIP 再動相鄰文件。
- **救援模式（驗證有效）**：`git worktree add --detach /tmp/x origin/main` + `cherry-pick -x`（乾淨部分）/ `cherry-pick -n` 後撤出撞車檔（部分讓位）/ 手工重做（全撞部分，commit-first 讓位）→ push 前再 fetch 確認 → `git push origin HEAD:main`。不占 branch、不擾並行 worktree、不違 Mac 禁 rebase 規則。
- **考古鏈**：遷移 commit message 記 SHA 對映表（模仿 `1f34653c`），死 branch 上的孤兒 commit 不再處理。
