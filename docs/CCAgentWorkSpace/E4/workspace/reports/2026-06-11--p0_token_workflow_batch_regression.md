# E4 Regression — P0 token/workflow 批次 · 2026-06-11

**被驗**：「P0 token/workflow 批次」（4 路 E1：hooks/settings 接線、四態契約 rollout、rtk pytest error 計數 patch、skill descriptions 改寫；E2 兩輪 PASS）。派工時 base=`0c10e340` 未 commit；**驗證進行中（item 4 期間）並行 session 將整個工作樹 commit 成 `4587f65f`（"Three-side sync checkpoint"，76 檔 +5033/−35），P0 批次與 aeg_s3/TODO.md 同 commit entangled**。已證工作樹==HEAD（batch paths diff=0 行）且 item 1/2 對 post-commit 樹重驗同綠 → 本報告全部結論適用於 `4587f65f` 內的 P0 批次檔集。

**Verdict：GREEN（9/9 PASS）— P0 批次本身零 FAIL；1 個 process concern（見 C-1/C-2）。**

## 逐項結果

| # | 項目 | 結果 | 關鍵證據 |
|---|---|---|---|
| 1 | agent-wave.js 語法（wrapper 法+bite） | **PASS** | wrapper `node --check /dev/stdin` exit 0；壞副本（注入 `const y=(`）exit 1 `SyntaxError: Unexpected token '}'` = 有牙自證。**獨立確認 E2 claim**：字面 `node --check` 對同一壞副本 exit 0（node v26.0.0）= no-op，wrapper 法 load-bearing |
| 2 | hooks 腳本 | **PASS** | `bash -n` 兩腳本=0；`jq empty settings.json`=0；`session-start.sh \| jq empty`=0（直接 pipe）；輸出含 `<workflow-hot-rules>`（開閉 2 hit）+ `hookSpecificOutput.{hookEventName=SessionStart, additionalContext}` 兩鍵 + 四態字串在 payload 內 |
| 3 | rtk-rewrite shim 三路 | **PASS** | (a) rtk 不在 PATH（`command -v` rc=1）→ exit 0、0 bytes；(b) rtk 0.42.2 入 PATH → 合法 JSON（jq=0）`updatedInput.command="rtk git status"` startswith rtk=true；(c) `git diff > /tmp/x.txt` → `rtk rewrite` exit 1 → 透傳 exit 0、0 bytes，且 /tmp/x.txt 未被建立（rewrite 探測零副作用） |
| 4 | patched rtk 對抗複驗 | **PASS** | 下表；7 場景（4 必驗+2 現成餌+1 自建 skip）四元組全一致、exit 全透傳，run1==run2 決定性。⑤ `rtk git log -n 5` exit 0、1912 bytes、含 commit 主題（並順帶抓到 mid-run commit） |
| 5 | 25 skill YAML | **PASS** | 25/25 目錄 frontmatter `yaml.safe_load` OK、**全 25 檔** name==目錄名 + description 單行非空（強於抽 3）；樣本 3：regression-testing-protocol/token-cost-analysis/pr-adversarial-review |
| 6 | gitignore 白名單 | **PASS** | settings.json / hooks/rtk-rewrite.sh / tools/rtk/README.md → check-ignore rc=1（不被忽略）；.claude/worktrees/、.claude/settings.local.json → rc=0（仍被 `.gitignore:95 .claude/*` 忽略）；行為實證=三者真進了 commit `4587f65f`（被忽略檔無 -f 不可能入庫） |
| 7 | agent .md 一致性釘子 | **PASS** | `DONE_WITH_CONCERNS`：PM.md×2 / E1.md×1 / E1a.md×1 / agent-wave.js×4 / session-start.sh×1；變體掃描（`DONE[_ -]?WITH[_ -]?CONCERNS`）全域 10/10 全為精確同拼寫、0 變體；E4.md:34-36 含「四元組」+ tee 條款；BB.md:57 含 `untrusted_content` 圍欄條款 |
| 8 | rtk crate 測試計數 | **PASS** | 親跑 `cargo test --release pytest_cmd` @ /tmp/rtk-work（HEAD=`32561a0` squash on pin `6785a6c7`，porcelain=0）= **16 passed/0 failed ×2 同值**（16 fn 名單與 E1 自報逐一對上；2149 filtered → target 總數 2165 = 2157p+8ign 算術閉合）；workspace 2157/0/8 **引用** E1 報告 §三層測試(b) + E2 複審 entry（E2 已親跑，本輪不重跑）。加驗：repo 內 patch 檔在 pin SHA throwaway worktree `git apply --check`=0（+263/−17 單檔），驗 README 裝機流程 load-bearing claim，worktree 已清 |
| 9 | 基準線零影響佐證 | **PASS** | `git diff --name-only 0c10e340..4587f65f \| grep -E '\.(py\|rs)$'` = 15 檔**全部**在 `helper_scripts/research/`（=並行 session aeg_s3，非本批）；P0 批次路徑 .py/.rs = **0**；`-- program_code rust sql tests` = **0 檔**；tools/rtk/0001-\*.patch 為 .patch 資料檔非被執行代碼 |

## Item 4 A/B 詳表（native pytest 9.0.3 @ mac_dev venv vs patched rtk `32561a0`；run1==run2）

| 場景 | native 四元組(p/f/s/e) + exit | rtk 摘要 + exit | 一致? |
|---|---|---|---|
| ① s0_all_green | 5/0/0/0 (0) | `Pytest: 5 passed` (0) | YES |
| ② s3_mixed | 7/2/0/1 (1) | `Pytest: 7 passed, 2 failed, 1 error` (1) | YES |
| ③ s2_collection_error | 0/0/0/1 (2) | `Pytest: 0 passed, 0 failed, 1 error` (2) | YES（非 "No tests collected"） |
| ④ s4_stdout_error_bait | 1/1/0/0 (1) | `Pytest: 1 passed, 1 failed` (1) | YES（E2 HIGH 餌不誤捕） |
| s1_fixture_error（加驗） | 20/0/0/1 (1) | `Pytest: 20 passed, 0 failed, 1 error` (1) | YES（主缺陷不吞 error） |
| s5_stdout_passed_bait（加驗） | 1/1/0/0 (1) | `Pytest: 1 passed, 1 failed` (1) | YES（base 假全綠已死） |
| s6_skip_mix_e4（**自建**，補 skipped 元） | 2/1/1/0 (1) | `Pytest: 2 passed, 1 failed, 1 skipped` (1) | YES |

原始輸出留檔：`/tmp/e4-p0-batch/ab_run{1,2}.txt`（s6 為本輪自建：既有 6 場景無一覆蓋四元組的 skipped 元）。

## full pytest / cargo 回歸 = N/A 之理由（正式記錄）

本批 P0 檔集（.claude/agents+skills+workflows+hooks+settings.json、CLAUDE.md、.gitignore、.codex/、tools/rtk/、docs/CCAgentWorkSpace memory/reports、helper_scripts/SCRIPT_INDEX.md）**零 .py/.rs 被執行代碼觸碰**：`git diff --name-only 0c10e340..4587f65f` 中 .py/.rs 命中 15 檔全屬並行 session aeg_s3（`helper_scripts/research/`），P0 批次貢獻=0；`program_code/`、`rust/`、`sql/`、`tests/` 0 檔被動。pytest 基線 lane（control_api_v1/tests）與 Rust suite 的 collection root 均不含本批任何路徑 → 結構性零影響。**BASELINE 行不變沿用：`BASELINE: 2026-06-11 passed=4728 failed=66`（+ Rust scoped 4669/0/6ign）**，本輪非全量回歸不新增 BASELINE 行。

## Findings（全量列出含 INFO）

- **C-1 [MEDIUM·process·confidence=確證]**：並行 session 在我回歸進行中（item 4 期間）把 P0 批次提前 commit（`4587f65f`），早於 E4 verdict，違反 E2→E4→PM-commit 鏈序。降損已做：batch paths 工作樹==HEAD diff=0 + item 1/2 post-commit 重驗綠 → 結論有效移轉到該 commit。處置權在 PM。
- **C-2 [MEDIUM·scope·confidence=確證]**：`4587f65f` 同時混入 aeg_s3 12 .py + 3 test .py + TODO.md（非本批）。**本 GREEN 僅覆蓋 P0 批次檔集**；aeg_s3 代碼/測試未經本輪驗證，須由其自身 E 鏈收尾（其 impl/design 報告在 PM workspace）。
- **F-1 [INFO·confirmed]**：字面 `node --check` 對含 `export` 的檔在 node v26.0.0 連注入語法錯誤都 exit 0（no-op）——以壞副本親證，E2 claim 成立；wrapper 檢法必須成為 SOP。
- **F-2 [INFO]**：`rtk rewrite "git status"` 回 exit 3（ask 規則）非 exit 0（allow）→ shim 正確走 ask 分支（updatedInput 無 permissionDecision，交 Claude Code 原生確認）。協議符合、非缺陷；PM 應知 git-status 類改寫不會自動放行。
- **F-3 [INFO·假陽性已自證]**：首次 `session-start.sh | jq empty` 報 parse error 是我的 zsh harness artifact（zsh `echo "$out"` 會解 `\n` 轉義污染 JSON）；直接 pipe 即綠。教訓：JSON 驗證鏈禁用 zsh echo 中轉。
- **F-4 [LOW]**：shim 版本守衛 cache（`rtk-hook-version-ok`）寫死「一次 OK 永遠 OK」——若未來換上 <0.23 舊 binary，cache 在場會跳過版本檢查。fail-open 設計內風險極小，列名不阻。

## 跑兩遍

item 4 七場景 run1==run2 全同值；item 8 模組 16/16 ×2 同值。無 flaky。

## 零觸碰確認

prod/runtime 零接觸（純 Mac 靜態+/tmp）；`/tmp/rtk-work` 還原確認（單 worktree、porcelain=0，PM 裝機 binary 未動）；pin-check throwaway worktree 已 remove；我的 scratch 僅留 A/B 原始輸出 `/tmp/e4-p0-batch/`；`/tmp/x.txt` 未產生；真 HOME cache 未污染（測試用 XDG_CACHE_HOME 隔離）。

**E4 REGRESSION DONE: PASS**（P0 批次；C-1/C-2 交 PM 裁決）
