---
name: ssh-bridge-workflow-2026-04-21
description: Mac CC 為 SSOT 透過 ssh trade-core 遠端觸發 Linux runtime 任務；取代雙 CC session 靠 prompt 同步的浪費流程；Mac 本地允許 git fetch + git pull --ff-only（原「CC 絕不 pull」規則放寬）
metadata: 
  node_type: memory
  type: project
  originSessionId: bbc3e5c6-e79b-42de-8add-b6790a1c3f07
---

# SSH bridge workflow（2026-04-21 採納）

**Operator 原觀察**（2026-04-21）：
> 現在工作流程是 Mac CC 寫 prompt → 他貼給 Linux CC → Linux CC 讀 → 執行 → 回報 → Mac 消化。兩次浪費（我生成 prompt + Linux CC 讀 prompt），不合理。

**採納方案 B**：Mac CC 透過 `ssh trade-core` 遠端觸發 Linux runtime 任務（Tailscale MagicDNS + key-based auth，operator 已設好 passwordless ssh）。Linux 變成 Mac session 的 remote shell。

## 工作流程分工

| 角色 | 職責 |
|---|---|
| **Mac CC**（主 session，SSOT） | 對話決策、寫碼、commit/push、ssh 遠端執行 runtime 任務（cargo test / psql / restart_all / git 操作）、消化結果、產出 report 到 `.claude_reports/` |
| **Linux CC**（輔助 session，24h 守夜） | 監控 watchdog alert、處理 Mac CC 做不了的 local 操作（rebase、amend、interactive git）、接 operator 直接指令做獨立 audit/fix、從 Mac push 的 docs 中 pull 更新 |
| **Operator** | 決策、cross-session 溝通、pull Mac → Linux（若需 Linux session context 要最新）、按 per-case 授權高風險動作 |

## 🔒 硬規則：commit 完必 push（2026-04-21 operator 指示）

**無例外**。維持 Mac / Linux / GitHub origin 三處 state 一致性。

| 主體 | 規則 |
|---|---|
| **Mac CC** commit | 同一個 Bash 鏈內接 `git push origin main`，禁 commit 不 push 就離開 |
| **Linux CC** commit | 同樣規範，禁 commit 不 push |
| **Operator 手動 Linux shell commit** | 建議自己 push；若忘 → 下次 CC 接手會偵測 + 補 push（不批評，但不保證零時差可見） |
| **Operator 手動 Mac shell commit** | 同上 |

### Session 開始強制 sync 三連檢查

所有 CC 接手 session 第一件事（無論 Mac / Linux）：
```bash
git fetch --prune origin
# 若 local 落後 origin：
git pull --ff-only origin main
# 若 local 超前 origin（前一 session 漏 push）：
git push origin main
```

這三步應**例行自動做**，不待 operator 提醒；目的是接手時確保 origin、Mac、Linux 三處對齊，後續動作才不會基於 stale state 產生 divergence。

**ff-only pull 失敗**（divergent branches，雙邊各自有 commit 無重疊）→ 報告 operator，不擅自 merge/rebase（見下方 SSH bridge workflow Mac 本地 git 規則）。

---

## SSH 命令授權範圍

### 允許（Mac CC 可直接透過 ssh 執行）
- `ssh trade-core "cargo test -p openclaw_engine --lib --release"` — 測試
- `ssh trade-core "psql -h localhost -U openclaw -d openclaw -c 'SELECT ...'"` — DB 查詢（read-only，需 `.pgpass` 或 libpq 免密碼）
- `ssh trade-core "cd ~/BybitOpenClaw/srv && git log/diff/branch/status/show"` — git read-only
- `ssh trade-core "git pull origin main"` / `"git push origin main"` — Linux 本地 repo 同步
- `ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"` — engine rebuild+restart（遵循 `feedback_restart_rebuild_flag_scope`）
- `ssh trade-core "tail -n 200 /tmp/openclaw/engine.log"` — log 查看
- `ssh trade-core "rm /tmp/openclaw/<sentinel_file>"` — Linux tmp 狀態清理
- `ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status"` — watchdog

### 需 operator per-case 授權（CC **絕不**擅自做）
- 觸及真實 live API 的動作（Mainnet 下單、撤單、修倉）
- 改 `authorization.json` 或任何 secret 檔
- 刪 remote branch（`git push origin --delete ...`）即使 TODO 或 doc 標「可清」—— 本 session 已 trigger 過 guardrail（刪 `feature/p1-16-h0-gate-deterministic` 被 deny，正確）
- 刪 worktree（`git worktree remove ...`）即使 locked agent-* 看似遺留
- 刪 `trading.*` / `learning.*` table 資料（DROP / TRUNCATE / DELETE 大批）
- 改 `settings/risk_config*.toml` 或其他風控 config（走正常 commit 流程，不 ssh hotpatch）

## Mac 本地 git 規則（2026-04-21 放寬）

**原規則**（CLAUDE.md §七 Mac 規則第 4 點 舊版）：
> CC 絕不執行 `pull` / `merge` / `checkout` / `reset` / `rebase`

**新規則**（SSH bridge workflow 啟用後）：
- ✅ **允許** `git fetch --all --prune`（更新 refs，不動工作樹，completely safe）
- ✅ **允許** `git pull --ff-only`（純 fast-forward，無 merge commit 生成，衝突自動 abort）
- 🚫 **仍禁** `git merge <branch>`（非 ff-only，有衝突風險）
- 🚫 **仍禁** `git rebase` / `git reset --hard` / `git checkout <branch>`（改變工作樹有風險）
- ✅ **允許** `git checkout -- <file>`（單檔 revert 本地 unstaged 改動，等同 restore）
- 🚫 **仍禁** 透過 ssh 在 Linux 端做 `git reset --hard` / `git rebase`（Linux 本地 history 變更，可能 break remote）除非 operator 明確授權

**理由**：原規則假設 Mac 沒有測試能力需要完全被動同步，但 SSH bridge 後 Mac 是主動 driver，ff-only pull 是必要的 state 同步動作，不做會累積 drift。保留 merge/rebase/reset 的禁制防止無意 history 改寫。

## 工作流範例

### 範例 1：Mac CC 寫碼 → 跑 Linux 測試 → commit
```
1. Mac CC Edit rust/.../foo.rs
2. Mac CC: ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"  # Linux 同步 Mac push 前
   （等等 — 這步有問題：Mac 還沒 push，Linux 不需 pull。流程正確版：）
3. Mac CC: cargo check --lib (Mac 本地 debug build)
4. Mac CC: git add/commit/push origin main (Mac → origin)
5. Mac CC: ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"  # Linux 從 origin 拉 Mac push
6. Mac CC: ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test -p openclaw_engine --lib --release"
7. Mac CC 看結果，若綠 → ok；若紅 → 回 step 1 fix
```

### 範例 2：Linux 端 DB 狀態查詢
```
Mac CC: ssh trade-core "psql -h localhost -U openclaw -d openclaw -c \"SELECT ...\""
```
若需密碼：透過 `.pgpass`（operator 設）或 `PGPASSWORD=xxx ssh trade-core "PGPASSWORD=... psql ..."`（避免 argv 洩）

### 範例 3：部署 + 觀察
```
Mac CC: ssh trade-core "bash helper_scripts/restart_all.sh --rebuild" 2>&1 | tail -30
Mac CC: ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
Mac CC: ssh trade-core "tail -n 100 /tmp/openclaw/engine.log | grep -E 'ERROR|phys_lock|INIT'"
```

## 優勢量化

| 指標 | 舊流程（雙 session + prompt） | 新流程（SSH bridge） |
|---|---|---|
| 跨 session tokens/turn | ~2000-5000（prompt 序列化 + Linux CC 讀） | 0（Mac session 直出 ssh 命令） |
| Round-trip 數/task | 2-3（prompt → Linux exec → 回報 → 再 prompt） | 1（Mac 下令 → ssh 返回，同一 turn） |
| Operator 人手 attention 負擔 | 2 次貼 prompt | 0（除非 per-case 高風險授權） |
| Context 丟失風險 | 中-高（Linux CC 可能遺漏 Mac session 未寫入 prompt 的隱性知識） | 低（Mac session 完整 context） |

## 遺留的 Linux CC 職能

不要完全關閉 Linux CC，它仍有不可替代的角色：
1. **監控**：24h 守夜 engine watchdog、DB alert、fee anomaly
2. **Mac CC 禁做的 interactive 操作**：`git rebase -i`、`git reset --hard <commit>`、`git push --force`（operator 請求時）
3. **Linux-side hotfix**：engine runtime 急性 bug operator 可直接派 Linux CC 不等 Mac session 回來
4. **Mac CC 離線時兜底**：operator 不在 Mac，Linux CC 仍可接指令

## 未來潛在問題

1. **Mac session context 累積**：ssh 命令輸出進 Mac session 會佔 context，大量時（e.g. `cargo test` 幾百 test 輸出）需用 `| tail -N` 截斷
2. **Linux worktree agent 遺留管理**：本 session 見 13+ worktree locked，SSH bridge 不解決這個 — 需 operator 決策是否清
3. **PR-review-in-Mac**：若 Mac CC 直接 ssh 執行 Linux 的 debug/audit，Linux CC 失去檢查機會。解法：重要 commit 前讓 Linux CC 過一眼（純 read-only review）

## 演變:main 直推被禁(2026-07-14 起,2026-07-15 實證)

repo 落地 Git 政策硬化(`61eae47c6`/`c7e256889`/`e62bb71f3` 鏈):**pre-push hook 禁止直推 `refs/heads/main`**,訊息指示「push a feature branch, open an exact-head PR, and merge on GitHub」。2026-07-15 實證:detached worktree push HEAD:main 被 BLOCKED;改走 `git push origin HEAD:refs/heads/agent/<topic>`(detached HEAD 推新分支需完整 refspec)→ `gh pr create` → `gh pr merge --merge --delete-branch` 成功(PR #17,merge `834f6fe31`)。main 近史 #13-15 全是 merge commit,同流程。**「commit 完必 push」硬規則精神不變,但目標改為 feature branch + PR merge**;Linux 端 `pull --ff-only origin main` 不受影響。

## 演變:CI 成本收斂「非必要,不 CI」(2026-07-16 operator 定調)

operator 觀察 CI 用量持續爆炸,定調**三端同步沿用優化版 CI,非必要不 CI**。落地 `.github/workflows/ci.yml`(單一 workflow):
- **手段1 path-filter 已存在且優於 naive `on.push.paths`**:`changes` classifier job(`helper_scripts/ci/classify_ci_changes.py`)算精確 diff,gate 所有重 job 於 `needs.changes.outputs.<gate>`;`on.push.paths` 會連帶關掉刻意無條件的安全閘(migration/stable-id/git-workflow-policy,靜態測試 `tests/ci/test_github_ci_workflow_static.py` 明文守衛)且會卡 required check pending → **不採納 literal 版**。
- **手段1 真漏洞已補**:push-to-main 原本 classifier 走 `--all`→ 每次純 docs/governance 合併都觸發整棵 Rust cold build。改為 `event.before...sha` 精確 diff(force-push/首推 `git cat-file` 守衛退回 `--all`;schedule 仍 `--all` 保週 macOS smoke)。
- **手段2 rust-cache 新增**:`Swatinem/rust-cache@v2` `workspaces: rust`(workspace 根,非成員 crate `openclaw_engine`;Cargo.lock 在 `rust/Cargo.lock`)掛在 `rust-check-linux`/`rust-check-macos`/`schema-contract` 三個編譯密集 job。**`alr-fit-verifier` 刻意不快取**——它靠乾淨 offline target 做 locked-online↔clean-offline 對賬,快取會破壞 hermetic 語義。
- **commit 面**:doc/governance-only commit 用 `[skip ci]`(CLAUDE.md §Git And Sync 既有慣例,此directive 強化之)。
- **已 landed**:PR #41 → merge `55bdb6c55`(commit `84b5a3d90`);feature branch `agent/ci-cost-path-filter-rust-cache`(已刪)off `origin/main`。手段2 實為**四** job(含 origin/main 上的 `rust-ibkr-tests`,recovery 分支沒有)。
- ⚠️ **drift 風險**:併時 worktree 在 `recovery/gui-design-14-concurrent-20260714`,該分支的 ci.yml 已 committed **drop 掉 `rust-ibkr-tests` job**(較 origin/main 少 ~71 行 tail);故本 CI 優化刻意在 **origin/main 建 clean worktree** 落地,不基於 recovery 分支(否則會 revert 掉 main 的 IBKR CI job)。**recovery 分支日後合併前須 rebase/對齊 main,否則會同時 revert IBKR job + 本優化**——非我引入,屬併發 session 帳,operator 留意。

## 演變:main 全史重寫(2026-07-16 23:46,secret purge)

- 事故面:三憑證曾入 git 史——generic CLI/gateway secret、bearer token、PostgreSQL password。三者已全部 revoke/rotate;兩個未用外部面(外部 OpenClaw Gateway、Grafana 容器/dashboard/寫入鏈)整體退役移除(PR#53 `5504daf95`)。
- 手術:`git-filter-repo 2.47.0 --sensitive-data-removal --replace-text` 重寫全史,所有可寫分支/tag force-update;attest commit=`967188c35`(PR#55)。鏡像掃描確認三值已從全部可寫 branch head/tag/重寫後 commit message 缺席。
- **影響(對每個 session 的硬事實)**:2026-07-16 23:46 前記錄在 memory/TODO/docs/報告裡的一切 commit SHA pin 屬舊史,在新史 dangling——定位一律改用 PR 編號/日期/subject(`git log --grep`)。舊史留本地備份 ref:Mac+Linux `pre-rewrite-main-20260716`(=舊 main head `94380563f`),SHA 考古用,永不 push。
- GitHub 側殘留:`refs/pull/2..53` 唯讀 PR head refs 仍含憑證(52 refs/156 secret-ref 對),已備 GitHub Support 請求稿(外層 `~/Projects/TradeBot/GITHUB_SUPPORT_SECRET_PURGE_REQUEST.md`)待送/待 GitHub 端 GC;forks=0。憑證已全 revoke,殘留屬衛生面非活風險。
- 三端影響與復位(2026-07-17):重寫使 Mac main(.codex-worktrees/main-sync)與 Linux trade-core 雙雙停在舊史 head、ff 不可能——`.codex/SYNC.md`「diverged=stop」契約在「操刀式全史重寫」場景下的正解=各留備份 ref 後 re-point 新史 origin/main,此後恢復常規 ff-only。教訓:全史重寫是「三端同步」的紀元斷點,重寫者應同輪把兩端 main 帶過紀元並落 memory,否則每個後續 session 都要重新考古一遍。

## 設定狀態（2026-04-21）

- ✅ Tailscale 已設（Linux hostname resolves）
- ✅ SSH key auth 已設（`ssh trade-core` 免密碼通）
- ⏳ `.pgpass` 未確認（DB 查詢需要）
- ⏳ 本 memory 取代原 CLAUDE.md §七 Mac 規則第 4 點描述（CLAUDE.md 同步更新）
