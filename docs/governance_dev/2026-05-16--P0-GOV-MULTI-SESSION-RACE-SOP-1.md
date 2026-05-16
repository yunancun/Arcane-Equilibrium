# P0-GOV-MULTI-SESSION-RACE-SOP-1 — Multi-Session Race Prevention SOP

**Ticket**: `P0-GOV-MULTI-SESSION-RACE-SOP-1`
**Priority**: P0 (governance hardening, multi-session loss-of-work prevention)
**Owner**: PA design / PM enforce / all CC sessions adopt
**Date**: 2026-05-16
**Scope**: Mac + Linux CC sessions, codex sessions, sub-agents, background tasks
**Status**: SPEC ONLY — pending PM Sign-off → enforce via §八 強制工作鏈

---

## 1. 背景 — 2026-05-16 race incident chain（4 events）

2026-05-16 凌晨同一 8 小時窗（22:00 UTC 2026-05-15 → 06:00 UTC 2026-05-16）內，同機 Mac 上 12-agent audit Wave 1-4 並行 session 期間至少發生 **4 個 race event**，分別造成 IMPL 工作損失、誤 revert、commit timing 與 background sub-agent quota race。Operator 在 27f02a07 commit message 自承「3 race events 2026-05-16 01:35-01:48」+ a7cb517f 在 v35 rebuild 前 land 留下 background sub-agent fail 兩段顯式記錄。

### 1.1 Event timeline（git 證據 + commit message ground truth）

| # | UTC | Event | 證據 |
|---|---|---|---|
| 1 | 2026-05-15 23:35-23:48 | **BB-MF-3 phantom sign-off + comment contamination** — sibling 12-agent audit session 連續 stash + silently drop Wave 2b BB-MF-3 5 grid_trading IMPL files；另一 session 在 `is_exchange_backoff` 加 contaminated comment 被 sibling preserved revert | `27f02a07` body `Multi-session race incident: sibling 12-agent audit session repeatedly stashed + silently dropped this work (3 race events 2026-05-16 01:35-01:48)` |
| 2 | 2026-05-15 23:48-23:55 | **主會話 stash 誤殺 BB-MF-3 + Wave 2 IMPL** — 主會話收 sibling commit `ef6ea79f`（含 「BB-MF-3 comment contamination in is_exchange_backoff reverted」）後做 stash cleanup；之後從 dropped stash refs `0a9d86d2` (mod/constructors/position_mgmt) + `8460bd3f` (signal/tests) selective restore | `27f02a07` body `Recovered from dropped stash refs 0a9d86d2 ... + 8460bd3f ... via git show extract`；Wave 2b 2906 lib tests + 8 new BB-MF-3 unit tests 已被 sibling verify 即丟失 |
| 3 | 2026-05-16 00:53 | **E1 leftover P1 background sub-agent 與 v35 rebuild 競賽** — Round 4 三角 cross-validation 識別 WP-13 真實只 partial fix，立刻派 background sub-agent 補 FA-P1-11 leftover；safely 在 v35 rebuild 前 land `a7cb517f`，僅 7 min margin（02:53 land → 03:04 `1517135a` v35 sync record） | git log timestamps：`a7cb517f` 02:53:33+0200 → `1517135a docs: record v35 post-rebuild sync` 03:04:28+0200 = 11 min 內 v35 rebuild 完成；若 leftover land 晚 11 min，stale `cmd_tx` 仍在 v35 binary |
| 4 | 2026-05-16 01:00 | **E1 WP-13 leftover P1 retry background sub-agent fail (org monthly limit)** — 同位 leftover background sub-agent retry 觸 org-level monthly quota，silent fail | (PM 派發 prompt 自承 event 4；本 PA SOP design 不引此 event 為 SOP 啟動條件，因 quota event ≠ race；但治理 §6 加 quota awareness 條款) |

### 1.2 Root cause taxonomy

| Root cause class | 對應 event | 既有 memory/feedback 規則 | 缺口 |
|---|---|---|---|
| Stash drop without provenance check | 1, 2 | `feedback_git_commit_only_for_metadoc` (`--only` 隔絕 index race) | **`git stash drop/pop` 前 0 強制 provenance check**；sibling session 看不認識的 unstaged code 就 stash → 後續 drop = silent loss |
| 不認識 WIP 誤 revert | 1, 2 | `project_multi_session_memory_race` 規則 2 「不認識的 working-tree 改動禁 revert」 | **規則只覆蓋 `memory/` 路徑**；Rust source / Python source 同型 race 未明文禁；sub-agent 不讀此 memory |
| Sub-agent dispatch 與 main thread 改動 race | 3 | `feedback_fetch_before_dispatch`（派 sub-agent 前 fetch + 查 remote branch） | **未覆蓋「主 session 改動已 land main，背景 sub-agent 仍跑舊版」**；rebuild race 沒 SOP |
| Background sub-agent quota awareness | 4 | (無) | **派背景 sub-agent 前 0 quota check**；fail 後也沒 graceful degrade 路徑 |

---

## 2. 適用範圍

本 SOP 適用：
1. 同機 multi-CC session（Mac dev / Linux CC / codex session）
2. Sub-agent 派發（@E1 / @E1a / @E2 / @E4 / @A3 / 任何 background sub-agent）
3. Meta-doc 改動（CLAUDE.md / TODO.md / docs/ / memory/）
4. Code 改動（Rust / Python / SQL migration / TOML / shell script）
5. Rebuild / restart 操作（涉及 `restart_all.sh` / `--rebuild` / engine PID 切換）

不適用：
- 純 operator 手動 commit（人類 NCYu 自己提交不受此 SOP 限制；此 SOP 是 CC session 衛生）
- Read-only research / report 寫入 `.claude_reports/`（無 commit）

---

## 3. 8 條強制規則

### Rule 1 — Commit-first 原則（必）

Meta-doc 改動（CLAUDE.md / TODO.md / docs/*.md / memory/*.md / SCRIPT_INDEX.md / LOGICAL_SCRIPT_CATEGORY_MAP.md 等）**必**用：

```bash
git commit --only <path> -m "..."   # 或等效 git commit -m "..." <path>
git push origin HEAD:main
```

**不**用 `git add <file>` + `git commit`（無路徑 arg）的兩步式組合。`--only` 忽略 index 內其他已 staged 但非本次意圖檔。

**範圍擴充**：原 `feedback_git_commit_only_for_metadoc` 只覆蓋 meta-doc；本 SOP 擴到「single-file cleanup / typo fix / 任何 single-purpose commit」全程強制 `--only`。

Code multi-file feature commit（例：新 Rust module + caller 改 + tests）沿用 `git add <file1> <file2> ...` + `git commit`，但 commit 前必完整看 `git status`（無 `head` / `tail` / `| head` 截斷）並驗 `git status --porcelain` 列表無預期外檔。

**Why**：commit 後改動在 reflog + git index 受保護；working tree 被 revert 時仍可 `git checkout HEAD -- <file>` 還原。Staged-uncommitted 跨 session 是高風險 race window。

### Rule 2 — 不認識禁 revert（必）

任何 CC session / sub-agent 見 `git status -s` / `git stash list` 出現**非本 session 剛做**的改動 → **一律不 revert**，必先：

```bash
git log --oneline -20                              # 看最近 commit 作者 + 時間
git reflog                                         # 看 HEAD/stash 變動軌跡
git stash show -p stash@{N}                        # stash 內容 patch（每個 stash）
git diff <path>                                    # working tree diff 內容
```

**不執行**：`git checkout -- <path>` / `git stash drop` / `git clean -fd` / `git restore --staged <path>` 之類動作除非完成下列至少一條：
1. 改動明確是本 session 之前 turn 留下的 WIP（可從本 session 工具歷史驗證）
2. operator 顯式確認可清
3. 改動內容對應 CLAUDE.md §四 硬邊界違規必須緊急回退（極罕見；必先 ask operator）

**範圍擴充**：原 `project_multi_session_memory_race` 規則 2 只覆蓋 `memory/`；本 SOP 擴到**任何路徑**（Rust source / Python / SQL / TOML / docs / scripts）。

**Why**：working tree 的非本 session 改動可能是隔壁 session in-progress IMPL，drop = loss of work。Event 1+2 整類事故的 root cause。

### Rule 3 — Stash forensics 強制（必）

`git stash drop` / `git stash pop` 前**必跑** stash 內容 grep 檢查是否含其他 session 關鍵字：

```bash
# Step 1：列舉所有 stash
git stash list

# Step 2：對每個 stash 看完整 patch
git stash show -p stash@{N} > /tmp/stash_${N}_inspect.patch

# Step 3：grep 9 大關鍵字判斷是否含他 session 工作
grep -iE '(BB-MF-|WP-[0-9]+|F-FA-[0-9]+|MIT-|QC-|MAG-08[234]|W-AUDIT-8[abc]|wave [0-9]\.?[0-9]?b?|E1[ ]+IMPL|sign[-_]off|TODO §|workspace/reports)' /tmp/stash_${N}_inspect.patch
```

**Any hit** → **禁 drop**，立刻：
1. 記錄 stash ref + commit SHA `git stash show stash@{N} --format=fuller`
2. 看 git log 找對應 commit owner sub-agent / session
3. Ask operator 是否可清，或保留待 owner session 自己 process

**Why**：Event 1+2 整類事故衍生：sibling session 直接 drop unknown stash，造成 BB-MF-3 等 5 IMPL 檔需從 dropped stash refs `0a9d86d2` + `8460bd3f` 二次 selective restore（高難度 + 失敗會永久丟）。

### Rule 4 — Sign-off git status clean 加固（必）

任何 sub-agent / session sign-off report commit 前**必檢**：

```bash
# Step 1：路徑乾淨
git status --porcelain <signoff-target-path>      # 必 empty 或僅本 commit 對應檔

# Step 2：時間窗 sibling commit 檢查
git fetch --prune origin
git log --oneline --since="2 hours ago" origin/main  # 看有無 sibling push
git log --oneline --since="2 hours ago" HEAD          # 看本 session 已 commit

# Step 3：若 origin/main 領先 HEAD → ff pull / 若不能 ff → 暫停 ask PM
```

**Why**：原 `feedback_git_commit_only_for_metadoc` rule 5「commit 完後 `git show --stat HEAD` 驗 files changed 數量」是 commit-after 檢查；本 rule 4 是 commit-before sibling-aware 檢查。Sign-off report 進 PM 工作流後常 trigger 下一節流，必須 commit 點 sibling 狀態無衝突才不污染後續 chain。

### Rule 5 — Org-limit awareness（必）

派 sub-agent（尤其 background sub-agent）前**必** quota check：

```bash
# Anthropic API quota（如有 dashboard 工具）—— 不存在公開 CLI 時改 operator manual
# 替代方案：估算 token spend + 既有 in-flight sub-agent 數量
```

**降級協議**：sub-agent dispatch fail（quota / rate-limit / network）→ 不自動 retry；報 operator + 改 sequential single-session 路徑。Background sub-agent 失敗超過 1 次 → 升 P1 ticket 排隊不重派。

**Why**：Event 4 leftover P1 retry background sub-agent 觸 org monthly limit silent fail；後續 work item 進 backlog 損失即時 close 機會。

### Rule 6 — Race incident log 強制（必）

任何 race 事件發生（規則 1-5 任一被觸發 / IMPL 工作損失 / silent revert / stash drop catastrophe），**必**在 `docs/lessons.md` 「Multi-session race incident」區內加一條 entry：

```markdown
## YYYY-MM-DD HH:MM UTC · <race event 短名>
- **觸發場景**：（如：sibling 12-agent audit 並行 + Wave 2b BB-MF-3 IMPL 進行中）
- **檢測**：（誰先發現；commit body 自承 / E2 review 揭發 / operator 反饋）
- **損失量**：（如：5 grid_trading 檔 + 8 unit test + 2906 lib tests verify 浪費）
- **Root cause**：（對應第 1 節 taxonomy）
- **Remediation**：（如：從 dropped stash refs selective restore + Rule 3 SOP 加固）
- **本 SOP 涵蓋等級**：FULL / PARTIAL / GAP（GAP = 暴露未覆蓋 race 模式，必加 SOP 規則）
- **Commits**：（涉及 commit SHA 列表）
```

**Why**：Pattern learning — race 事件不留證據 → 同型重犯。`feedback_*.md` auto-memory 是 stale 性質（point-in-time 警告）；race incident log 是 evergreen 證據鏈，支援 SOP 演化。

### Rule 7 — Sub-agent dispatch SOP（必）

派 sub-agent / background sub-agent 前**必**：

```bash
git fetch --prune origin
git branch -r | grep -iE '<topic-keyword>'         # 看 remote 有沒同主題 branch
git log --oneline origin/main -20                  # 看隔壁最近推什麼
git log --oneline --since="4 hours ago" --all      # 跨 branch sibling 工作
```

**判斷**：
- Remote `origin/fix/<topic>` 已存在 → 先讀 branch HEAD commit 判隔壁進度
- 近 4h sibling commits 觸 `<topic>` → 暫停 ask PM 是否真需重派
- Local HEAD 落後 origin → 必 `git pull --ff-only`（CC 不執行 merge / rebase / reset）後再派
- Local HEAD 領先 origin → 必先 `git push origin HEAD:main` 再派（避 sub-agent 拿到 stale base）

**範圍擴充**：原 `feedback_fetch_before_dispatch` 只強調 Wave-level batch；本 SOP 對**所有** sub-agent dispatch 強制（含 single-task 派發）。

**Why**：Event 3 主會話派 leftover background sub-agent 時若先做 fetch，可發現 v35 rebuild planning 已在進行（5f6f3edf 02:58 land 前 5 min），可選擇 sequential 而非 parallel 派發避 11 min margin race。

### Rule 8 — Wave 並行同 crate fence rule（必）

同 Rust crate / 同 Python package 內並行**兩個或以上** IMPL sub-agent：

**強制 sequencing 條件（任一觸發）**：
1. 兩任務改同檔（直接 file collision）
2. 兩任務有 cross-file diff context（如 A 改 trait def，B 改 trait impl）
3. 兩任務都需 `cargo check --release` / `pytest` 全 crate 驗證（避測試結果污染）

**並行准許條件（必同時滿足）**：
1. 兩任務改檔集合 disjoint（PM dispatch prompt 必明列 file scope per sub-agent）
2. 兩任務 cross-file 引用 0（grep verify）
3. PM dispatch prompt 顯式聲明 isolation（per CLAUDE.md §八「動態 isolation 派工準則」必要時加 `isolation: worktree`）

**範圍**：本規則特別針對 `rust/openclaw_engine/src/` 巨型 crate，內聚高 + cross-module trait 多；Python `program_code/exchange_connectors/bybit_connector/control_api_v1/app/` 同樣 high-cohesion 適用。

**Why**：Event 1+2 整類事故部分是因為 Wave 2 4 個 WP 並行（WP-03 sigma residual / WP-04 AI observability / WP-07 dead code / WP-10 Bybit retCode）+ Wave 2b BB-MF-3 grid_trading 並行；雖然 file 集合理論 disjoint，但 sibling session 對 `is_exchange_backoff` 註釋的 comment contamination 跨檔污染了 BB-MF-3 IMPL window 的 working tree。

---

## 4. SOP 啟動觸發點

任一 CC session / sub-agent 在以下時點**必**自檢 SOP 8 條：

| Trigger | 必檢規則 |
|---|---|
| Session 啟動（接手三連 sync 後） | Rule 1, 2, 6 |
| Sub-agent dispatch 前 | Rule 5, 7, 8 |
| Meta-doc 改動 commit 前 | Rule 1 |
| 看到 `git status` / `git stash list` 有不認識項 | Rule 2, 3 |
| Sign-off report commit 前 | Rule 4 |
| 任何 race 事件發生後 | Rule 6 |
| Engine rebuild / restart 計劃前 | Rule 7, 8 |
| Wave-level batch dispatch 前 | Rule 5, 7, 8 |

---

## 5. E2 review checklist 整合（強制）

E2 PR review 必加：

1. ✅ Commit 範圍對齊 commit message 描述（無 silent inclusion）
2. ✅ Commit 前 sibling 時間窗 ≥ 2h 內無 origin/main push 衝突
3. ✅ Meta-doc 改動用 `git commit --only`（單檔 commit）
4. ✅ 若涉 sub-agent dispatch / parallel work → SOP Rule 7+8 已執行
5. ✅ 若 race 事件已發生 → `docs/lessons.md` 已加 Multi-session race incident entry

任一 ❌ → E2 RETURN（不 merge）。

---

## 6. PM enforcement 強制

PM 派發 sub-agent prompt 必含：

```
## Multi-Session Race Safety (P0-GOV-MULTI-SESSION-RACE-SOP-1 強制)
- Commit-first 原則：meta-doc 改動必 `git commit --only <file>` + push
- 不認識 working tree / stash 改動禁 revert（先 git log + reflog + stash show + ask operator）
- Stash drop / pop 前必 grep 內容是否含 BB-MF/WP-N/F-FA-N/MIT/QC/MAG-08X/W-AUDIT/wave Nb/sign-off/workspace/reports 等他 session 關鍵字
- Sign-off commit 前必 `git fetch + git log --since="2h ago"` 確認無 sibling 衝突
- Background sub-agent 失敗（quota / rate-limit）禁 retry，回報 operator
- 任何 race 事件必 append `docs/lessons.md` Multi-session race incident 區
- 派發前必 `git fetch` + `git branch -r | grep <topic>` 看隔壁 branch
- 同 Rust crate 並行 ≥ 2 sub-agent 必驗 file scope disjoint + cross-file ref 0
```

PM Sign-off report 前必跑 §5 E2 checklist 5 條全 ✅。

---

## 7. Tooling 建議（PA design optional）

| 工具 | 用途 | 實裝難度 |
|---|---|---|
| `helper_scripts/git/stash_inspect.sh` | wrap `git stash show -p stash@{N}` + 自動 grep 9 大關鍵字並 exit 1 if hit | LOW 0.5h |
| `helper_scripts/git/sibling_check.sh` | wrap `git fetch + git log --since="2h ago" origin/main` + exit 1 if sibling commit detected | LOW 0.3h |
| `helper_scripts/git/pre_dispatch.sh` | combine fetch + branch grep + topic check + sequential vs parallel decision matrix | MED 1.5h |
| `.git/hooks/pre-commit` 加 `--only` 強制檢測 | 拒收 commit 包含未在 path arg 列表內檔 | MED 1h |

**建議優先級**：先 `stash_inspect.sh`（Rule 3 自動化，最高 ROI）→ 後 `sibling_check.sh`（Rule 4 自動化）→ 不裝 git hook（強制太狠，operator 可能 frustrated）

---

## 8. 16 根原則 + 9 不變量 合規

| 維度 | 評估 |
|---|---|
| 原則 1 單一寫入口 | N/A（governance SOP，非 trading path） |
| 原則 6 失敗默認收縮 | ✅ Rule 2 不認識禁 revert + Rule 5 quota fail 不 retry |
| 原則 7 學習 ≠ 改寫 Live | ✅ Rule 6 race incident log = pattern learning，不改 Live |
| 原則 8 交易可解釋 | ✅ Rule 6 audit trail 完整 |
| 原則 10 認知誠實 | ✅ Rule 6 明寫損失量 + root cause + remediation |
| 原則 12 持續進化 | ✅ §1.2 taxonomy + §4 trigger + §5 E2 checklist + §6 PM enforcement = 完整反饋迴路 |
| DOC-08 §12 9 不變量 | 0 觸碰（純 governance / process SOP，不動 lease / exec / fail-closed code） |
| 硬邊界 | 0 觸碰（不動 `live_execution_allowed` / `max_retries` / `execution_authority` / `decision_lease_emitted`） |

**合規評級**：A 級（16/16 + 硬邊界 0 觸碰）

---

## 9. Rollout plan

| Phase | 工作 | Owner | ETA |
|---|---|---|---|
| Phase 1 | 本 SOP land + PM Sign-off | PA → PM | 2026-05-16 |
| Phase 2 | 4 race incident entry append `docs/lessons.md` | PA | 2026-05-16（本 commit 內） |
| Phase 3 | PM dispatch prompt 加 §6 模板（更新 PM.md） | PM | 2026-05-17 |
| Phase 4 | E2 review checklist 5 條入 `.claude/agents/E2.md` | PA + E2 | 2026-05-17 |
| Phase 5 | Optional tooling (§7) — `stash_inspect.sh` + `sibling_check.sh` | E1 | 2026-05-18+ |
| Phase 6 | 30 天觀察期：race incident frequency 統計 | PM | 2026-06-15 review |

---

## 10. Out-of-scope

本 SOP **不**處理：
- iCloud / Time Machine 同步 race（H3 假說 in `project_multi_session_memory_race`，未驗證 + 罕見）
- Editor / linter PostToolUse hook 自動 revert（H2 假說，當前未驗證）
- Mac LaunchAgent / Linux systemd 與 CC session 的服務 race（runtime ops 範疇，非 dev process）
- Cross-machine git push collision（極罕見，git remote 本身 atomic refs）

如未來發現以上類型 race 事件，加新 SOP 補充而非擴本 SOP。

---

## 11. 變更歷史

| 日期 | 變更 | 引用 |
|---|---|---|
| 2026-05-16 | 本 SOP draft v1.0 land | PA design report `2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1` |
| (TBD) | PM Sign-off | (TBD) |
