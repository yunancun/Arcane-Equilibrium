# Claude Code 錯誤模式與預防規則庫

**定位**：Operator 每次糾正後，CC 抽象成可 grep 的模式規則寫入本檔，會話起手掃近期相關條目以降錯誤率。

**與 auto-memory `feedback_*.md` 的區別**：
- 本檔 = 技術/流程錯誤模式庫（可 grep；跨 CC 實例可讀；CC 自己維護）
- memory/feedback = operator 偏好與工作風格（通過 auto-memory 系統跨 session 持久化）
- 兩者互補不重複：行為偏好進 memory；「做錯 X 應做 Y」進 lessons

**條目格式**：

```markdown
## YYYY-MM-DD · <錯誤模式短名>
- **場景**：觸發條件（什麼情境下容易犯）
- **錯誤模式**：具體做錯了什麼
- **預防規則**：下次遇到該場景時的行為準則
- **相關檔案 / 指令**：grep 起點（可選）
- **來源 commit / session**：追溯（可選）
```

**維護準則**：
- 同模式第 2 次犯 → 條目強調升級（加 🚫 標記 / 移至頂部）
- 條目連續 30d 無相關糾正 → 移到文末 "低頻" 區，不刪
- 條目發現與既有 auto-memory feedback 重複 → 合併到 memory，lessons 留引用行

---

## 條目

## 2026-05-10 · improve-codebase-architecture 中文輸出偏好

- **場景**：使用 `improve-codebase-architecture` skill 做架構候選、deepening opportunities、grilling loop 或後續總結。
- **錯誤模式**：雖然 repo 記憶已有 operator-facing responses should be Chinese-first，但架構 review 候選仍可能以英文為主，增加 operator 閱讀與決策成本。
- **預防規則**：該 skill 的候選清單、追問、方案比較與總結默認中文；skill 強制詞彙 `Module` / `Interface` / `Implementation` / `Depth` / `Seam` / `Adapter` / `Leverage` / `Locality` 保留英文原詞，可搭配中文解釋；`CONTEXT.md` domain terms 按 glossary 原文使用。
- **相關檔案 / 指令**：`.codex/MEMORY.md`; `/improve-codebase-architecture`
- **來源 commit / session**：2026-05-10 Codex PM session

## 2026-04-26 · 並行派發中「commit B 應 invalidate commit A doc」的時序 hazard

- **場景**：PM 在同一 session 並行派發多個 sub-agent（5+），其中部分任務有**doc 依賴關係**（commit A 的 doc/comment 提及「直到 X 條件達成才移除」，commit B 完成 X 條件）。並行派發無時序保證，A 與 B 完成時序不可預測。
- **錯誤模式**：本 session 實例（2026-04-26 12:17 → 12:36）：
  - commit `92ea90b` G1-FUP-CALIBRATOR-WARNING (12:17) 加 calibrator banner「IPC bind only covers 6/7 dimensions」+ 自身宣告「Tracking ticket EDGE-P1b-FUP-STALE-PEAK-IPC closed → banner removable」
  - commit `c2ca032` EDGE-P1b-FUP-STALE-PEAK-IPC (12:36, 19min 後) 加 `exit_stale_peak_ms` 進 IPC，**closed 該 ticket**
  - PM 漏執行 banner 移除 → E2 batch review 揭發 → 補 fixup commit `f633a5a`
  - 結果：1 個多餘 commit + E2 review + fixup 周期，浪費 ~30min session time
- **預防規則**：PM 識別「commit B 應 invalidate commit A doc」依賴對時，派發前選 3 種編排模式之一：
  1. **模式 A（合併 commit）**：commit A 與 commit B 改用 batch sub-agent（同一 sub-agent 順序完成 A→B 或 PM 自己合併兩 commit），消除中間 stale 期窗
  2. **模式 B（補 patch）**：派 commit B 時 prompt 明示「完成後同次 patch 移除 commit A 的 stale doc」（需 commit B sub-agent 知道 commit A 內容）
  3. **模式 C（TODO 標記）**：commit A 的 stale-able doc 加 `TODO(commit-B-id): remove this when X closes` 標記 + 後續 ticket 提醒 PM 自動掃描
  - 默認選 C（最不依賴 sub-agent 間溝通），有明顯時序排序時選 A
- **相關檔案 / 指令**：
  - PM 派發 prompt 模板（`docs/CCAgentWorkSpace/PM/profile.md` 派工章節）
  - `helper_scripts/db/passive_wait_healthcheck.py` 規則「被動等待必附 healthcheck」（同型「PM 編排規則」）
- **來源 commit / session**：2026-04-26 PM Phase 1+2 sign-off (`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--phase1_2_signoff.md` §4)

## 2026-04-26 · Sub-agent 完成測試 ≠ 完成 commit

- **場景**：PM 派發 sub-agent 完成 quick fix / refactor，prompt 含 commit + push 指示。Sub-agent 完成代碼修改 + 跑通測試後，可能因「system reminder 禁寫 .md 報告」誤判延伸到「禁 commit」，或因 E1/E2/E4 強制鏈想法 push back 不直接 commit。
- **錯誤模式**：本 session 兩次發生：
  - **G9-01 TW** (`0cda2d9`): TW 完成字典修正 + 給 PM 一個 commit oneliner 但**沒自動 commit**（誤判 system reminder 禁寫 .md = 禁 commit）
  - **EDGE-P1b E1** (`c2ca032`): E1 完成 7 檔修改 + cargo 2162 / pytest 130 PASS 但**改動留 Mac/Linux staging dir**（push back PA prompt 與 system 規則衝突）
  - 兩次都需 PM 介入 cp / git add / commit，浪費 ~10min session time
- **預防規則**：PM 派發 prompt 必含**3 條明示**：
  1. **「直接 commit + push 為任務完成標準的一部分，不要留 staging dir」**
  2. **「不要把 commit oneliner 當作給 PM 的下一步指示，PM 已授權 sub-agent 直接執行 commit + push」**
  3. **「system reminder 對 .md 報告檔的限制不延伸到 commit/push 操作」**
  - 對於 TW（doc-only writer），補 prompt 最末段「TW 範圍含 commit + push docs，不需 PM 代 commit」
  - 對於 E1/E5（實作 sub-agent），補 prompt 最末段「PM 顯式授權 commit + push，CLAUDE.md §七 強制 commit 即 push 適用本任務」
- **相關檔案 / 指令**：grep `staging|don't commit|不直接 commit` in sub-agent prompts
- **來源 commit / session**：2026-04-26 PM Phase 1+2 sign-off §3

## 2026-04-24 · CLAUDE.md §三 敘述 vs runtime drift

- **場景**：`CLAUDE.md §三「當前系統狀態摘要」` 中嵌入 runtime 數值（cell count / row count / fill rate / binary mtime / commit progress / fire 次數），寫入時即場驗證但後續無自動化更新；數天後 runtime 已演化，§三 仍引用舊數字導致 audit 結論建立在 stale 假設上。
- **錯誤模式**：典型表現 — `CLAUDE.md` 宣稱「162 cells」但 `settings/edge_estimates.json` 實測僅 **1 cell**（mtime 4 天停滯，2026-04-24 G1-01 audit 揭露）；該數字曾經正確但 `edge_estimator_scheduler` 後續死掉無人察覺，§三 變成「過去快照」假冒「現況」。同型 drift 早期亦發生於「main_legacy.py 1630 行未拆」（2026-04-23 audit 才更正為已拆 468 行）。Root cause = 寫入即定型 + 無 freshness gate + 無自動 invalidate。
- **預防規則**：
  1. **採集標記**：§三 任何「runtime 數值 + 狀態」描述必註明「採集時間」（YYYY-MM-DD HH:MM CEST）+ 對應 healthcheck id（`passive_wait_healthcheck.py` 中的 `[N] check_*`）或具體驗證 oneliner，缺一即 E2 打回。
  2. **7 日鮮度上限**：§三 任何「狀態 + 數字」描述滿 7 天未經自動化重驗，必須由 cron / healthcheck / 手動驗證更新到當前值，或從 §三 刪除（移到「已完成里程碑索引」表保留 1 行）。違反 = 下一輪維護週期必補。
  3. **Audit-first 原則**：CC 收到 §三 數字當輸入時，**禁止無條件採信** — 凡涉及決策（rebuild / TOML 改 / 部署 gate），先跑對應 healthcheck 或讀 source-of-truth 檔案實測，發現 drift 立即在 commit 同次更新 §三。
  4. **Healthcheck 反向綁定**：每條 §三「runtime 數值」必對應 `passive_wait_healthcheck.py` 一個 `check_*()` 能在 silent-dead 時 RAISE / Exit 1（與 §七「被動等待 TODO 必附 healthcheck」規則同型，但這條覆蓋的是「敘述」而非「TODO」）。
- **相關檔案 / 指令**：
  - `CLAUDE.md` §三「當前系統狀態摘要」+「進行中/阻塞」段
  - `helper_scripts/db/passive_wait_healthcheck.py`（既有 12 個 check_*）
  - V023 postmortem 衍生 §七 SQL migration guard 4 條（同源規範，敘述-vs-runtime drift 是更廣的同類）
  - Verify pattern：`python3 helper_scripts/db/passive_wait_healthcheck.py --all`
- **來源 commit / session**：2026-04-24 G6-04（10-Agent audit Wave 1 子任務）；觸發案例 = G1-01「edge_estimator_scheduler 4 天停滯，§三 宣稱 162 cells 實測 1 cell」+ 2026-04-23 「main_legacy.py 1630 行宣稱未拆實測 468 行已拆」

---

## Multi-session race incident

> 本區記錄同機 multi-CC session 並行造成 race 事件的事實鏈，配合 `docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md` SOP 8 條規則。每 entry 含 root cause + remediation + 本 SOP 是否完整 cover 的判斷。新增 entry 必同時觸發 SOP §1.2 taxonomy review。

## 2026-05-15 23:35-23:48 UTC · BB-MF-3 phantom sign-off + comment contamination

- **觸發場景**：12-agent full system audit Wave 2 並行（WP-03 / WP-04 / WP-07 / WP-10 by sibling session）+ Wave 2b BB-MF-3 grid_trading IMPL（by 本 session sub-agent）；兩 session 都動 `rust/openclaw_engine/src/strategies/grid_trading/` package
- **檢測**：commit `27f02a07` body 自承「sibling 12-agent audit session repeatedly stashed + silently dropped this work (3 race events 2026-05-16 01:35-01:48)」+ sibling `ef6ea79f` body 自承「BB-MF-3 comment contamination in is_exchange_backoff reverted」
- **損失量**：5 grid_trading IMPL files (mod.rs / constructors.rs / position_mgmt.rs / signal.rs / tests.rs) + 8 new BB-MF-3 unit tests + 2906 lib tests verify 浪費（必重跑）
- **Root cause**：規則 1 (Stash drop without provenance check) + 規則 2 (不認識 WIP 誤 revert)
- **Remediation**：從 dropped stash refs `0a9d86d2` (mod/constructors/position_mgmt) + `8460bd3f` (signal/tests) selective restore via `git show extract`；commit `27f02a07` land Wave 2b recovery；comment contamination 保留 sibling preserve revert（單向認輸 dual-write 損失 minimal）
- **本 SOP 涵蓋等級**：FULL — Rule 2 + Rule 3 直接針對此事件；Rule 8 (Wave 並行同 crate fence rule) 防同 crate 並行 race
- **Commits**：`27f02a07` (recovery) / `ef6ea79f` (sibling silent revert) / `15e67220` (E1 self-report) / `5682994c` (WP-04 E2 review) / `88f9254f` (Wave 1 Round 3 補修)

## 2026-05-15 23:48-23:55 UTC · 主會話 stash 誤殺 BB-MF-3 + Wave 2 IMPL（之後 selective restore）

- **觸發場景**：本 session 接 sibling 推送的 `ef6ea79f` commit 後做 stash cleanup；sibling 此前已 silently drop 多個 stash
- **檢測**：本 session 嘗試 verify BB-MF-3 IMPL 仍在時發現 working tree 已被 sibling commit overwrite + stash 列表異常
- **損失量**：與 event 1 同範圍（5 IMPL 檔），所幸從 dropped stash refs 找回
- **Root cause**：規則 1 (Stash drop without provenance check) + 規則 3 (Stash forensics 強制) — 本 session 與 sibling 都未做 `git stash show -p stash@{N}` 內容 grep 確認 BB-MF / WP-N / sign-off 等他 session 關鍵字
- **Remediation**：與 event 1 同 (selective restore)；本 SOP Rule 3 強制化 stash forensics 模式以防再犯
- **本 SOP 涵蓋等級**：FULL — Rule 3 stash forensics SOP 直接針對；Rule 6 (Race incident log) 強制留證據
- **Commits**：與 event 1 重疊（同一物理 race window）

## 2026-05-16 00:53 UTC · E1 leftover P1 background sub-agent 與 v35 rebuild 競賽（safely land）

- **觸發場景**：Round 4 三角 cross-validation (`864f4e81`) 識別 WP-13 真實只 partial fix（FA-P1-11 leftover），立即派 background E1 sub-agent 補；同時主 session 進入 v35 rebuild 規劃流程
- **檢測**：git log timestamp 對比：`a7cb517f` (02:53:33+0200, leftover land) → `5f6f3edf` (02:58:25+0200, v35 sync record) → `1517135a` (03:04:28+0200, post-rebuild sync) = leftover land 領先 rebuild 啟動 5 min margin
- **損失量**：0 — safely 在 v35 rebuild 前 land；若晚 5 min，stale `cmd_tx` 仍在 v35 binary 必須二次 rebuild
- **Root cause**：規則 7 (Sub-agent dispatch SOP) 部分覆蓋 — 派發前若先 fetch 可發現 rebuild planning 進行；本事件無實質損失但 margin 緊
- **Remediation**：本 SOP Rule 7 + Rule 8 強制 dispatch 前 fetch + sibling time-window check；Rule 5 (Org-limit awareness) 防 background sub-agent 失敗 race
- **本 SOP 涵蓋等級**：PARTIAL — Rule 7 cover dispatch fetch；對「主 session 已開始 rebuild planning 但 background sub-agent 仍 in-flight」型 race 未明文 SOP；後續可補 Rule 9（rebuild 前必 wait background sub-agent settle）
- **Commits**：`864f4e81` (Round 4 三角 cross-validation) / `a7cb517f` (leftover land) / `5f6f3edf` (v35 sync record) / `1517135a` (post-rebuild sync)

## 2026-05-16 01:00 UTC · E1 WP-13 leftover P1 retry background sub-agent fail (org monthly limit)

- **觸發場景**：event 3 leftover land 後 follow-up sub-agent retry（PM 派 second pass verification）觸 Anthropic org monthly quota
- **檢測**：sub-agent dispatch silent fail；operator 注意異常後通報
- **損失量**：unbounded — 後續若有 leftover 需修則 backlog 排隊；本次因 event 3 已 fully land，無實質工作損失
- **Root cause**：規則 5 (Org-limit awareness) — dispatch 前 0 quota check；fail 後 0 graceful degrade
- **Remediation**：本 SOP Rule 5 強制化 quota check + 不 auto-retry + 改 sequential single-session 路徑；未來高峰期前 operator 手動 quota dashboard 預估
- **本 SOP 涵蓋等級**：FULL — Rule 5 直接針對；Rule 6 強制 incident log 累積 quota pattern 證據
- **Commits**：N/A（fail 無 commit；event 3 `a7cb517f` 已包覆所有真正必要工作）

---
