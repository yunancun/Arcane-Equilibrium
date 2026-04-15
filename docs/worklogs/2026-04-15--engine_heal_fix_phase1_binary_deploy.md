# 2026-04-15 工程日誌 — ENGINE-HEAL FIX-PHASE1 binary 正式部署
# Worklog — Deploy FIX-PHASE1 engine binary via restart_all.sh --rebuild

**Session**: /compact 後續會話
**Commits**: 無新 commit（純部署動作 + 記憶庫同步）
**Branch**: `main`（本地領先 `origin/main`，未 push）

---

## 一、背景 / Context

本 session 前序完成 FUP-1 watchdog systemd 化審計（`2026-04-15--engine_heal_fup1_watchdog_systemd.md`）。審計過程中發現：

- CLAUDE.md §三 / TODO 留尾 #1：FIX-PHASE1 binary（commits `5d5ec13 + 6c73b60 + 0762006`）在磁碟上已 build，但運行中 engine PID 577219 啟動於 11:13:56，為 **pre-FIX-PHASE1 binary 的 mmap 映像**
- `/tmp/openclaw/engine_results.jsonl` 從 worklog 記錄的 111GB 漲到 **122GB**（14:45 仍在增長），因為舊 binary 沒有 rotation 邏輯（純 append-only），15 分鐘內增長 1-2GB

Operator 指令：「按照方案 1 你直接做掉」= 執行 `bash helper_scripts/restart_all.sh --rebuild` 部署 FIX-PHASE1 binary。

---

## 二、改動 / Changes

### 1. 部署動作（非代碼變更）

執行 `bash helper_scripts/restart_all.sh --rebuild`。腳本行為（2026-04-14 FA-PHANTOM-1 修復後）：

1. `cargo build --release -p openclaw_engine`（增量編譯，因 binary 已是 14:47 的版本，no-op）
2. `build_pyo3.sh` 重建 PyO3 wheel + 雙寫 `.so`
3. `restart_engine`：kill PID 577219 → 起新 PID 693387
4. `restart_api`：kill :8000 → 起 uvicorn 4 workers（PID 693442）
5. `wait_and_verify`：sleep 10 + engine watchdog --status 確認

### 2. 記憶庫誤導修正

`~/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/feedback_restart_rebuild_flag_scope.md`：

- 原 name：「restart_all.sh --rebuild 只重建 PyO3，不重建 engine binary」
- 改後 name：「restart_all.sh --rebuild 現在會同時重建 engine binary + PyO3（2026-04-14 後）」
- Body 內容本已反映 2026-04-14 FA-PHANTOM-1 修復後的新行為，是 frontmatter 落後於 body。MEMORY.md 索引條目同步更新。

這個記憶在本 session 差點誤導決策（看到「只重 PyO3」差點改走 `cargo build && --engine-only` 雙步驟）— 及時 grep 腳本驗證才發現記憶過時。

---

## 三、驗證 / Verification

### Pre-flight

| 項目 | 結果 |
|------|------|
| binary mtime (部署前) | 14:47（FIX-PHASE1 已 build，但 577219 仍持有舊 mmap） |
| engine PID 577219 | 11:13:56 啟動，PPID=1 孤兒（早於 watchdog systemd 化） |
| G-2 daemon 598572 | 3h06m 存活，n_fills=0（未寫 audit，重啟安全） |
| 磁碟空間 | 1020G 可用，cargo 增量編譯無壓力 |

### Rebuild 過程觀察

- `restart_all.sh --rebuild` 總耗時不可精確測（bash wrapper 被 `| tail -80` 卡住，詳見留尾 #1）
- cargo 增量 no-op（binary 已是 14:47 版本，mtime 未更新）
- engine kill → new PID 間隔 < 5s（restart_engine 用 lsof + kill -9 + sleep 2）

### Post-flight

| 驗證項 | 結果 |
|--------|------|
| binary mtime | 14:47 > 最新 FIX-PHASE1 commit `0762006` 14:06:41 ✅ |
| 舊 engine PID 577219 | 已死 ✅ |
| 新 engine PID 693387 | 14:55:04 啟動，3 engines (paper/demo/live) 全 alive，snapshot age 22-24s ✅ |
| API uvicorn :8000 | PID 693442，4 workers listening ✅ |
| Watchdog PID 684057 | flock 仍握（restart_all.sh 自清，watchdog 未介入） ✅ |
| **canary rotation** ⭐ | **122GB → 519MB（rebuild 瞬間重置）→ 584MB（6min 後）** ✅ |
| G-2 daemon 598572 | 3h13m 存活，n_fills=0 未變（engine restart 不影響監控 daemon） ✅ |

**關鍵證據**：rebuild 前後 `engine_results.jsonl` 從 122GB 重置為 519MB，證實 FIX-PHASE1 的 size rotation 邏輯（`OPENCLAW_CANARY_ROTATE_MB=1024` 預設）生效。這是對 `5d5ec13 fix(engine-heal-phase1): offload canary write off live event loop hot path` 首次真實運行時驗證。

---

## 四、留尾 / Follow-ups

1. **`restart_all.sh` + bash pipe EOF 陷阱**：`bash ... | tail -80` 中 uvicorn `&` 背景後繼承 stdout FD，導致 pipe 不 EOF，`tail -80` 永遠等不到結束，wrapper bash 卡住。部署已完成（services 全 up），手動 kill wrapper（exit 144 為我自殘非腳本錯誤）即可。可選優化：`restart_all.sh` 內 uvicorn 重定向 stdout/stderr 到 log file + `disown`，讓 pipe 正常 EOF。**非阻塞**。

2. **canary rotation 首次壓力測試**：寫入速率 ~65MB/min，7-8 分鐘就會觸碰 1024MB 閾值。**建議 20 分鐘後檢查**：
   ```bash
   ls -lh /tmp/openclaw/engine_results.jsonl*
   ```
   確認 rotation 行為是「重命名保留 `.1/.2/...`」還是「truncate 覆寫」。若是保留，需要額外 retention policy；若是覆寫，資料保留窗口 ≈ 15min（取決於寫入速率），寫 audit 時可能需要抓 snapshot。

3. **G-2 daemon progress 文件時間戳未刷新**：`ts_utc` 停在 12:47:55（2h+ 前），但 daemon 進程 PID 598572 存活。可能是 progress 文件只在 fill 事件時更新（n_fills=0 → 沒觸發 update），非 daemon 假死。**接手時**：`ps -p 598572` 若仍存活 + engine canary 有活動 → 視為正常；若懷疑 daemon hang，讀 `/tmp/openclaw/g2_monitor.py` 看 update 觸發條件。

4. **CLAUDE.md §三 與 §十一 更新**（未做）：「ENGINE-HEAL 部署留尾」段寫「運行中引擎仍 pre-fix binary。operator 需 restart_all.sh --rebuild 部署」已不再成立。下 session 接手或下次 commit 時順手改成「FIX-PHASE1 binary ✅ 已部署（2026-04-15 14:55 PID 693387）」。

5. **TODO.md 留尾 #1 結清**（未做）：`docs/worklogs/2026-04-15--engine_heal_fix_phase1_fup_and_e4_hygiene.md` 四、留尾 #1「FIX-PHASE1 binary 部署（operator 動作）」可標記為 ✅。

---

## 五、經驗提煉 / Lessons

- **記憶庫 frontmatter 過時 = 隱藏陷阱**：`feedback_restart_rebuild_flag_scope.md` body 本已反映 2026-04-14 修復後的新行為，但 name/description 還停在舊認知。差點誤導走雙步驟部署（`cargo build` + `--engine-only`）。**紀律**：修一個記憶時 frontmatter + body 必須同步；讀記憶時不能只看 description，涉及操作行為的必須回 body 或驗證實際狀態。

- **部署前先 grep 腳本**：不要信任「記憶說它會做 X」。`grep -n "rebuild\|cargo build" helper_scripts/restart_all.sh` 5 秒就看出真實行為，比回溯記憶更可靠。

- **bash `|` pipe + 背景進程 = wrapper 永遠不結束**：`cmd | tail -80` 中 `cmd` 內 `somedaemon &` 會讓 pipe 無法 EOF。這是 shell 基礎陷阱但容易中招。未來 `run_in_background` 包 `restart_all.sh` 時值得記住。

- **FIX-PHASE1 rotation 壓力測試窗口**：122GB → 519MB 這個對比是本 session 最漂亮的單一證據。`5d5ec13` 的核心承諾（bounded mpsc + BufWriter + size rotation）在 6 分鐘內就以對比數字坐實，比任何單元測試都有說服力。

- **「方案 1 你直接做掉」= 高度授權 + 低延遲必要**：operator 給出明確授權後，主會話先做風險評估（倉位/daemon 獨立性/磁碟）再執行；完成後 post-flight 必須 honest 地列出驗證項 + 側邊發現（canary 寫速率），不能只報喜。

---

**作者**：Claude（main session，PM+Conductor）
**接手指引**：
1. 若下 session 在 ≤20 分鐘內：`ls -lh /tmp/openclaw/engine_results.jsonl*` 檢查 rotation 首次觸發行為（留尾 #2）
2. 若下 session 要 commit：順手更新 CLAUDE.md §三 / §十一 + TODO.md 留尾 #1 標記（留尾 #4, #5）
3. 否則：繼續等 G-2 daemon 完成（~17h ETA）→ audit 寫入解鎖升 R-02
