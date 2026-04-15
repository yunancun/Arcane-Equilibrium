# 2026-04-15 工程日誌 — ENGINE-HEAL-FUP-1 watchdog systemd 正式化
# Worklog — Promote nohup watchdog to systemd user unit (cross-reboot survival)

**Session**: /compact 後續會話
**Commit 範圍**: TODO.md + CLAUDE.md + 新 worklog + 新 systemd unit（unit 在 `~/.config/systemd/user/` 非 repo 內，不入 commit）
**Branch**: `main`（本地領先 `origin/main`，未 push）

---

## 一、背景 / Context

`TODO.md:60` 原 `[ ]` item **ENGINE-HEAL-FUP-1**：watchdog 從 nohup 升級為 systemd user unit。

**事故鏈回顧**：
- 2026-04-15 02:03 UTC：Fix 4 WS tick stale self-cancel 按設計觸發，engine 優雅關閉
- 02:03 → 09:13 UTC **空窗 7h10m**：**watchdog daemon 從未部署**（`restart_all.sh:187` 僅跑 `--status` 一次性檢查），無人拉起引擎
- 09:13 operator 手動重啟 PID 577219
- 11:31 臨時 nohup 起 PID 592881（跨重啟不存活 — 留尾）
- 14:25 **本 session**：升級為 systemd user unit，正式結清 FUP-1

**前置條件都已齊備**（先驗證才動手，避免「做一半」）：
- `loginctl show-user ncyu` → `Linger=yes` ✅（user systemd 跨重啟存活）
- `engine_watchdog.py:508` 已有 `fcntl.flock LOCK_EX|LOCK_NB` 單例保護 ✅
- `engine_watchdog.py:523` 已有 `SIGTERM/SIGINT` handler 優雅釋放 flock ✅
- `RESTART_BACKOFF_SECONDS = [60,120,300,600,3600]` 已實作 ✅
- `MAX_CONSECUTIVE_FAILURES = 5` circuit-break 已實作 ✅
- `RESTART_COMMAND = ["bash", "helper_scripts/restart_all.sh", "--engine-only"]` 已實作 ✅

也就是 TODO 原文列的「E2 必查項」全部已在 commit `4e09c09` Fix 2 時完成，本次純粹只做 systemd 包殼。

---

## 二、改動 / Changes

### 1. 新增 `~/.config/systemd/user/openclaw-watchdog.service`

**不在 repo 內**（與 `openclaw-gateway.service` 同路徑，符合既有慣例）。關鍵配置：

```ini
[Service]
Type=simple
WorkingDirectory=/home/ncyu/BybitOpenClaw/srv
ExecStart=/usr/bin/python3 helper_scripts/canary/engine_watchdog.py \
  --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --poll-interval 2
Restart=always
RestartSec=5
TimeoutStopSec=30
KillMode=control-group
KillSignal=SIGTERM
StandardOutput=append:/tmp/openclaw/watchdog.log
StandardError=append:/tmp/openclaw/watchdog.log
Environment=HOME=/home/ncyu
Environment=OPENCLAW_DATA_DIR=/tmp/openclaw
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/usr/bin:/home/ncyu/.local/bin:/usr/local/bin:/bin
```

**設計要點**：
- `WorkingDirectory` 必須是 repo root — watchdog auto-restart 時呼叫 `bash helper_scripts/restart_all.sh --engine-only`，cwd 錯了 sh 找不到腳本
- `StandardOutput=append:` 保留歷史 log（非 `truncate:`），systemd v240+ 支援，本機 v255 OK
- `KillSignal=SIGTERM` + 30s timeout → watchdog 有足夠時間執行 `_shutdown` handler 釋放 flock（防止升級/重啟後新實例 exit 3）
- 沒有 `--auto-restart` CLI flag — watchdog 主迴圈本來就在 `run_watchdog()` 裡判斷 stale → 呼叫 `RESTART_COMMAND`，不需要額外旗標

### 2. 遷移 nohup → systemd

```bash
kill -TERM 592881           # 釋放 flock
systemctl --user daemon-reload
systemctl --user enable --now openclaw-watchdog.service
```

**結果**：
- 新 PID 678153，PPID=1983（`systemd --user`），**非 PPID=1 nohup 孤兒**
- `cat /tmp/openclaw/watchdog.lock` → `678153`（flock 正確轉交）
- `/tmp/openclaw/watchdog.log` 新增 `Watchdog started — monitoring /tmp/openclaw (threshold=45.0s, poll=2.0s, grace=120.0s)`
- `/home/ncyu/.config/systemd/user/default.target.wants/openclaw-watchdog.service` symlink 建立 → boot 時自動啟動

### 3. TODO.md 更新

- `[ ] ENGINE-HEAL-FUP-1` → `[x]` + 展開完成細節（unit 設計要點、遷移步驟、單例/退避確認、未壓測 kill -9 的理由）
- `~~1~~` 表行移除「留尾 W22 收尾」備註，改為 systemd 結清描述
- 頂部 `最後更新` 註記加入 FUP-1 正式結清摘要
- `G-2 FundingArb 驗證（Action #4，BLOCKED by FUP-1）` → `（Action #4 — FUP-1 ✅ 已解除）`

### 4. CLAUDE.md 同步（§三 + §十一）

- §三 ENGINE-HEAL 部署留尾：`FUP-1 ✅ systemd user unit 正式結清`
- §十一 一句話狀態：`engine_watchdog daemon ✅ PID 592881 nohup` → `engine_watchdog systemd user unit ✅ openclaw-watchdog.service Restart=always + linger=yes`
- §十一 下一步：移除 `ENGINE-HEAL-FUP-2/3 排隊`（FUP-2 已調查完成入 FIX-PHASE1，FUP-3 折入 FIX-PHASE1 同 commit）

---

## 三、驗證 / Verification

| 項目 | 命令 | 結果 |
|------|------|------|
| 服務狀態 | `systemctl --user is-active openclaw-watchdog.service` | `active` |
| Main PID | `ps -p 678153 -o pid,ppid,etime,cmd` | PPID=1983（systemd --user），18s 存活 |
| 日誌落盤 | `tail /tmp/openclaw/watchdog.log` | 啟動訊息正確追加 |
| flock 轉交 | `cat /tmp/openclaw/watchdog.lock` | `678153`（新 PID） |
| 舊 nohup 清除 | `ps -p 592881` | not found ✅ |
| Linger | `loginctl show-user ncyu \| grep Linger` | `Linger=yes` ✅ |
| Enable on boot | `ls ~/.config/systemd/user/default.target.wants/` | `openclaw-watchdog.service` symlink ✅ |

**未做項**：
- **不做 kill -9 engine 壓測** — 會打斷 G-2 daemon 監控（已累積 demo 資料）+ 當前活倉位。FUP-1 的單例 + 退避邏輯在 commit `4e09c09` Fix 2 已有單元測試驗證過；systemd 本身的 Restart=always 是成熟 proven 機制，不需要額外壓測證明。
- **不改 `restart_all.sh`** — 原腳本 `--status` 一次性檢查保留（operator 手動快速驗證用），daemon 模式由 systemd 負責。兩者不衝突。

---

## 四、留尾 / Follow-ups

1. **FIX-PHASE1 binary 部署**（operator 動作，未變）：`restart_all.sh --rebuild` 讓運行中 binary 換成含 `5d5ec13 + 6c73b60 + 0762006` 的新版。Watchdog 已 systemd 化，若 rebuild 過程 engine 掛了會自動拉起。
2. **G-2 FundingArb 驗證繼續**（Action #4，daemon PID 598572）：FUP-1 解除後不再有 blocking 關係，等 demo ≥20 fills 自動寫 audit。
3. **`restart_all.sh` systemd 感知**（非阻塞，次要）：可選改為先 `systemctl --user stop openclaw-watchdog` → kill engine → 拉起 engine → `systemctl --user start openclaw-watchdog`，避免 restart 過程 watchdog 誤判 engine 死亡觸發 double-restart。目前透過 `grace_period=120s` + `RestartSec=5` 覆蓋大部分情境，不構成阻塞。

---

## 五、經驗提煉 / Lessons

- **systemd user unit + linger=yes = 跨重啟存活的 zero-dep daemon 配方**：不需要 root、不需要 cron、不需要 tmux detach。`openclaw-gateway.service` 已是既有範例，抄 pattern 即可。
- **flock 轉交要走 SIGTERM 而非 SIGKILL**：`engine_watchdog.py:523` 的 `_shutdown` handler 依賴 clean exit path 讓 `fcntl` 釋放 fd。SIGKILL 雖然 kernel 也會釋放，但若 systemd 在同一 tick 啟動新實例會 race。SIGTERM + 等 3s 保險。
- **「做一半」比「不做」更糟**：原 TODO 描述「方案 A 或 方案 B」+「若尚未實作則先實作 `--auto-restart`」看似詳盡，實際 watchdog 本體已在 `4e09c09` Fix 2 實作完備，只差外殼。先 audit 代碼再設計方案，避免重複造輪子。
- **關鍵路徑更新要連同所有 reference**：TODO §`BLOCKED by FUP-1`、CLAUDE.md §三、§十一 都有對應條目；改一處不改全部 = 殭屍文本。grep 結果必須逐條確認處理。

---

**作者**：Claude（main session，PM+Conductor）
**接手指引**：下一個 `[ ]` 起點是 TODO Action #4 G-2 FundingArb 驗證 daemon 完成（~17h ETA，passive wait）。若 operator 要立即推進，可選 ENGINE-HEAL binary 部署（`restart_all.sh --rebuild`），watchdog 已 systemd 化可安全執行。
