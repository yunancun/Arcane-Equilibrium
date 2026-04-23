---
name: 多 CC session 並行時的 memory race 與處理協議（2026-04-23 採納）
description: 同機多 Mac CC session 同時存取 srv/memory/ 可能發生 working-tree 改動被隔壁 session 意外 revert 的 race；協議規定 memory 寫入 commit-first / session owner 識別 / 不認識改動禁 revert。
type: project
---

# 多 CC Session Memory Race（2026-04-23 採納）

## 觀察到的現象

2026-04-23 本 session（5-AGENT-RUNTIME-AUDIT-1）工作流：
1. Mac CC Session A（主）透過 Write/Edit 改 srv/memory/{MEMORY,project_layer2_agent_design}.md + 新增 project_5agent_runtime_state.md
2. tool calls 回傳成功；實測當時 mtime 已更新
3. 數分鐘後同 session Mac 端 sed/ls 檢查：**所有 4 處 edits 回到原版**，新檔消失
4. Linux 端（透過 scp + git apply patch 同步的副本）edits **完整保留** → 證明 edit 本身成功，revert 發生在 Mac working tree
5. Operator 事後確認：非有意，推測隔壁 CC session 誤 revert

## 根本原因假說（按可能性排序）

### H1（最可能）：隔壁 Mac CC session 做了 `git checkout -- memory/` 或 `git stash` 清除未認識的 working-tree 改動
- Claude Code session 可能在某些 workflow（例如用戶請求「恢復乾淨狀態」、或 session 初始化時）掃 working-tree diff 並做 cleanup
- 若該 session 不是 memory 改動的作者，不理解 origin 的 staged/unstaged edit，可能判定為「髒 tree 需清」
- 支持證據：ls/sed 看到的是 HEAD 版本（精準回到 git index 狀態），不是 random corruption

### H2（次要）：editor/linter hook 自動 revert
- settings.json 有 PostToolUse hook 對 memory/ 做 git checkout？
- 當前未驗證；需查 settings

### H3（不太可能）：iCloud / Time Machine 同步還原
- /Users/ncyu 外的 srv/ 路徑非 iCloud sync 範圍
- 但如果 symlink target 或整個 Projects/ 有同步設定則有可能

## 處理協議（採納）

### 規則 1：Memory 寫入 commit-first
任何 memory/*.md Write/Edit **必須** 在同一 turn 內立即 `git add memory/<file> && git commit && git push`（push 可被 hook 阻時至少 commit 到 local，commit 完成即受 git history 保護）。

**理由**：commit 後的改動在 reflog + git index 受保護，即使 working tree 被 revert，`git log` 仍可找到作者與內容並 `git checkout HEAD -- <file>` 還原。

### 規則 2：不認識的 working-tree 改動禁 revert
任何 session 見 `git status -s` 出現 memory/ 下的 M/A/?? 且 **非本 session 剛做** → 禁 `git checkout` / `git stash drop` / `git clean`，必 `git log --oneline -5 <path>` 查最近 commit + `git diff <path>` 讀內容 + 若仍無法判斷 → **stop + report operator**。

**理由**：working-tree 的 memory 改動可能是隔壁 session 尚未 commit 的 in-progress work，清掉即丟失。

### 規則 3：Session 接手三連檢查加 memory 驗證
project_ssh_bridge_workflow 原有 `git fetch + pull --ff-only + push`，擴充為：
```
git fetch --prune origin
git log --oneline -5 memory/                              # 看最近 memory 改動作者/時間
git status -s memory/                                     # 看本地未 commit 改動
若 memory/ 有 M/A/?? 且非本 session → 讀內容判斷是否為隔壁 session work
若是 → 保留 + 優先給該 session 完成 commit；本 session 延後動 memory/
若否 → 按需繼續
```

### 規則 4：Write 後立即驗證
memory Edit/Write tool call 後立即 Read 或 ls -la 驗證內容 + mtime，若 <5 sec 被改 → 記錄時間戳 + report（幫助未來 RCA）。

### 規則 5：Mac 被 revert 時的 fallback
若 Mac 端 memory 改動被 revert 但 Linux（透過 scp/patch）或 origin（已 commit）仍有副本：
- **優先路徑**：從 Linux / origin 重建 Mac（`git fetch && git checkout origin/main -- memory/<file>`）
- **次要路徑**：若 Mac 無法 sync（如 operator in-progress 阻 pull），在 Linux 繼續 commit + push，讓 Mac 下次自己處理
- **禁路徑**：不可在 Mac 重做 Write/Edit —— 會再次被隔壁 session revert 陷循環

## 與 SSH bridge workflow 的整合

project_ssh_bridge_workflow 定義 Mac=SSOT, Linux=守夜。多 session 情況下：
- **同機 Mac 多 session** 沒在該 memory 覆蓋 → 本 memory 補
- Mac multi-session 時最好只有**一個 session 是 memory writer**，其他只讀
- 若 operator 必須同時開兩個 Mac session 寫 memory（罕見），兩 session 互相以 `git log --oneline -1 memory/` 輪詢確認另方已 commit 後再動

## 未解待查（建議 operator 跟進）

1. 查 ~/.claude/settings.json 有無 PostToolUse hook 對 memory/ 做 git checkout（H2 驗證）
2. 若隔壁 session 能重現問題 → 抓 tool-use log 找 revert 動作來源
3. 考慮在 Mac 工程上 lockfile 機制：memory Write 前 touch /tmp/claude_memory_writer_<pid>，其他 session 見 lockfile 則等

**Why:** 2026-04-23 session 丟失 4 處 memory edits 工作量（~5 min 重做 + Linux patch 繞路），若常發 = 生產力損失 + 真實 memory 內容靜默漂移
**How to apply:** 所有 CC session 寫 memory 時遵守規則 1-4；遇隔壁 session 未認領 working-tree 改動啟動規則 2；已被 revert 時走規則 5 從 origin/Linux 重建
