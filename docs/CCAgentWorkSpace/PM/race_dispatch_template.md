# PM Sub-Agent Dispatch — Multi-Session Race Safety Template

**Date**: 2026-05-16
**Owner**: PM (主會話 = PM + Conductor 合一)
**Authority**: P0-GOV-MULTI-SESSION-RACE-SOP-1 Phase 2 enforce
**Scope**: PM 派 sub-agent (@E1 / @E1a / @E2 / @E4 / @A3 / @QC / @MIT / @BB / @TW / @R4 / @CC / @PA / @FA / @QA / @AI-E / @E3 / @E5) 之 prompt 必含 race safety boilerplate
**Sibling docs**:
- SOP 8 條：`srv/docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md`
- 事件鏈：`srv/docs/lessons.md` Multi-session race incident 區
- E2 review checklist §5：`srv/.claude/agents/E2.md`

---

## §6 Dispatch Boilerplate（強制）

PM 派 sub-agent 前 prompt 必含下列 4 條檢查（順序執行）：

### 6a Pre-dispatch fetch + sibling check

派發前 PM 主會話 boilerplate（不是 sub-agent 跑，是 PM 自跑）：

```bash
# 1. Fetch 最新 origin
git fetch --prune origin

# 2. 本地對 origin/main 狀態
git status --short --branch

# 3. 看近 2h sibling push
git log --since="2h ago" --oneline origin/main
git log --since="2h ago" --oneline HEAD

# 4. 若 origin/main 領先 HEAD → ff pull
# 若 HEAD 領先 origin → push origin HEAD:main
# 不能 ff（divergence） → 暫停 ask operator
```

PM 自己跑完 + 確認無 sibling 衝突，再派 sub-agent。

### 6b 同主題 branch check

派發前 PM 主會話查 remote topic branch：

```bash
# 看 remote 有沒同主題 branch
git branch -r | grep -iE '<topic-keyword>'

# 跨 branch 看 4h sibling 工作
git log --since="4h ago" --all --oneline
```

任一 sibling 已開同主題 branch → PM 評估：
- 是否真需重派（隔壁可能已做完）？
- 若隔壁進度 partial → 主 session 接手 finish，**不重派 sub-agent**
- 若需並行 → 顯式 isolation（per CLAUDE.md §八「動態 isolation 派工準則」）

### 6c Sub-agent prompt footer 強制 4 條

PM 派 sub-agent prompt **結尾** 必含下列 footer（複製貼入）：

```
---

## Multi-Session Race Safety (P0-GOV-MULTI-SESSION-RACE-SOP-1 強制)

- **禁 commit / push**：本任務 sign-off 後留 staged file，PM 統一 commit / push。不要自行 `git add` / `git commit` / `git push`（除非本任務 type=TW doc-only writer 或 prompt 明示授權 commit）
- **不認識禁 revert**：看到 `git status` / `git stash list` 出現非本 session 剛做的改動 → 一律不 `git checkout --` / `git stash drop` / `git clean -fd`；先 `git log + reflog + stash show -p stash@{N}` + ask operator
- **Stash drop / pop 前 grep**：必跑 `git stash show -p stash@{N} | grep -iE '(BB-MF-|WP-[0-9]+|F-FA-[0-9]+|MIT-|QC-|MAG-08[234]|W-AUDIT-8[abc]|wave [0-9]\\.?[0-9]?b?|E1[ ]+IMPL|sign[-_]off|workspace/reports)'`；any hit → 禁 drop + 通報 PM
- **Sign-off report commit 前 sibling check**：commit 對應 .md 前必 `git fetch` + `git log --since="2h ago" origin/main` 確認無衝突
```

### 6d 並行 sub-agent isolation 判斷

派 **≥ 2 sub-agent** 並行操作 **≥ 2 重疊檔** → 必加 `isolation: worktree`。判斷流程：

```
PM main session 收到並行任務 → 列舉每 sub-agent 改檔 scope (per CLAUDE.md §八)：

  情境 A：單 sub-agent 操作單檔 → 0 isolation
  情境 B：≥ 2 sub-agent 改互不重疊檔（PM 顯式列 file scope）→ 0 isolation
  情境 C：≥ 2 sub-agent 可能改重疊檔 → 對重疊 sub-agent 組加 isolation: worktree
  情境 D：destructive (git reset / 大量 rm / 跨檔重構) → isolation: worktree
```

重疊判斷 grep helper：

```bash
# 派發前列每 sub-agent file scope；grep 重疊
echo "<sub-agent-A scope>" > /tmp/A_scope.txt
echo "<sub-agent-B scope>" > /tmp/B_scope.txt
comm -12 <(sort /tmp/A_scope.txt) <(sort /tmp/B_scope.txt)
# 任一 line 即重疊 → isolation 必加
```

---

## §6.x 違規緊急流程

若 PM 派發後發現任一 SOP 規則違反 → 立即：

1. **Pause 所有 in-flight sub-agent**（不 retry，不重派；防 race chain compound）
2. **Race incident log**：`docs/lessons.md` Multi-session race incident 區 append entry（per SOP Rule 6）
3. **重新規劃**：依事件嚴重度（IMPL loss / silent revert / stash drop / quota fail）選 SOP 對應補救規則
4. **告知 operator**：附 git evidence 鏈（reflog / stash show / log --since）

---

## §6.y 30d effectiveness review（2026-06-15）

Phase 2 enforce 後 30 天 PM review：
- 收集本 SOP 觸發次數（多少 race event 被 catch）
- 收集 false positive（boilerplate 應跑但事後證明無 race）
- 收集 false negative（race 發生但 SOP 6a-6d 漏掉）
- 評估 fine-tune：
  - threshold 是否合理（2h sibling window / 4h branch window）
  - isolation 判斷是否 over-/under-engineered
  - footer 4 條是否仍 sub-agent 廣泛遵守
- Output：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-15--race_sop_phase2_30d_review.md`

---

## §6.z Out-of-scope

本 dispatch template **不**處理：
- 人類 operator 直接 commit（NCYu 手動 push 不受此 SOP，per SOP §2 不適用範圍）
- Read-only research / report 寫入 `.claude_reports/`（無 commit）
- Cross-machine git push collision（git remote atomic refs；極罕見）
- iCloud / editor hook 自動 revert（H2/H3 假說未驗證，per SOP §10）

---

**Status**: ENFORCED 2026-05-16；本 template land 與 SOP land 同 Sprint
**Phase 3 link**：本 template = SOP §9 Rollout Phase 3「PM dispatch prompt 加 §6 模板」交付物
