---
name: Meta-doc 改動用 git commit --only 隔絕 multi-session index race
description: 改 CLAUDE.md/TODO.md/docs/*.md/memory/*.md 等 meta-doc 時必用 `git commit --only <file>`，避免 operator 並行 session 往 git index 加檔意外被 commit 吸收
type: feedback
originSessionId: 6ebc2016-7557-4ddd-a03f-8418227b1456
---
Multi-session 環境下改 meta-doc（CLAUDE.md / TODO.md / docs/*.md / memory/*.md / SCRIPT_INDEX.md / LOGICAL_SCRIPT_CATEGORY_MAP.md 等）必用 `git commit --only <file> -m "..."`（或等效的 `git commit -m "..." <file>`）明確指定路徑，**不**依賴 `git add <file>` + `git commit` 組合。

**Why:** 2026-04-23 同一 session 內發生兩次相同事故：
1. 我 commit CLAUDE.md 時不小心把 operator 的 6 個 unstaged WIP 檔一起 commit + push（`4ca71c5`：`rust/openclaw_engine/src/combine_layer.rs` / `.../on_tick/helpers.rs` / `.../on_tick/mod.rs` / `.../on_tick/step_6_risk_checks.rs` / `helper_scripts/db/passive_wait_healthcheck.py` / `docs/references/2026-04-23--model_canary_promotion_rules_draft.md`）；之後 revert `13d0dd9` + 用 `--only` 旗標重提 `79bb20b`。
2. 同 session 更早也發生過一次 operator 的 bb_breakout rename 被誤 commit（見此 session 較早處）。

根因：我的 `git status` 檢查（顯示僅 CLAUDE.md staged）與 `git commit` 之間，operator 並行 session（另一 terminal / 另一 Claude Code / IDE）對 git index 做 `git add` 擴充 index；我的 `git commit`（無 `-a`，無指定路徑）依然 commit 所有當下 staged 內容，包括並行 session 加進 index 的檔。`git status | head -N` 截斷輸出還會讓並行新增的 staged 檔沒被看見。

**How to apply:**
1. **meta-doc / single-file cleanup / typo fix** 這類「清楚只該提一個檔」的 commit，**強制用 `git commit --only <path> -m "..."`**（或 `git commit -m "..." <path>`）。`--only` 會忽略 index 裡其他已 staged 但非本次意圖的檔。
2. **Code 多檔 feature commit**（本來就一組相關多檔變動，例：新 Rust module + caller 改 + tests）可沿用正常 `git add <file1> <file2> ...` + `git commit` — 那類本來就意圖多檔一起，index race 影響較小；但提交前仍需完整看 `git status`（不要 `head -N` 截斷）確認列表無意料外檔。
3. 提交前完整看 `git status`（無 `head`/`tail`/`| head`），若 "Changes to be committed:" 區塊出現預期外的檔 → 當下 `git restore --staged <file>` 摘除。
4. commit 完後立刻 `git show --stat HEAD` 驗證 files changed 數量符合預期再 push；若數量超出 → `git revert <hash>` 建立 revert commit，然後用 `--only` 重提我的 intended 改動。不要 `reset --hard` 或 force-push（CLAUDE.md §executing-actions-with-care 禁）。
5. 純 operator（人類 NCYu）自己 commit 不受此規則限制；這規則是 **CC session 的 commit 衛生**。
6. 追加策略：遇到 meta-doc 改動時，可以先 `git stash push program_code/ rust/ helper_scripts/` 把 code WIP 暫存、commit 完再 `git stash pop`，雙保險阻絕 race — 但此方式會影響 operator 的 editor working tree，僅在風險高時採用。

**Recovery**（如果已發生誤 commit）：
- `git revert <accidental-hash>` 建 revert commit（安全、非 destructive）
- 從被 revert 的 commit 抽取 intended 檔：`git checkout <accidental-hash> -- <intended-file>`
- 其他被吸收的 operator WIP 檔仍在 git history 內，operator 可用 `git checkout <accidental-hash> -- <path>` 或 `git cherry-pick <accidental-hash> -- <path>` 恢復到 working tree
