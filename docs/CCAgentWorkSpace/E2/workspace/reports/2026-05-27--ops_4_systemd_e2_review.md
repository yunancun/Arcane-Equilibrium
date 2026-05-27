# E2 PR Adversarial Review — P0-OPS-4 GAP-A + GAP-F systemd · 2026-05-27

**Scope**: 4 NEW + 1 NEW(README) + 1 EDIT(SCRIPT_INDEX) (E1 report claim 569 LOC + 12)
**Files**: `helper_scripts/systemd/{openclaw-engine.service, openclaw-watchdog.service, install_engine_service.sh, install_watchdog_service.sh, README.md}`
**Cross-ref**: PA spec `2026-05-26--p0-ops-4-first-day-live-runbook.md` §10 GAP A/F + E1 report
**Verdict**: **APPROVE WITH MINOR (LOW × 3 + MED × 1)** — 1 MED 建議 E1 fix in-place（無需重 round），3 LOW 入 follow-up；無 HIGH/CRITICAL；E2 不代寫，將具體 fix 建議列在 §6。

---

## §1 Issue 矩陣（2 unit + 2 script + README）

| # | 嚴重 | 位置 | 問題 | 建議 |
|---|---|---|---|---|
| 1 | MED | `openclaw-engine.service:38` `Requires=` 空值 | systemd 直接拒絕空 directive 或 warning（依版本）；E1 留空意圖是「無硬依賴」但語法應**整行刪除**而非保留空 key | 刪整行 `Requires=` |
| 2 | LOW | `install_engine_service.sh:89-91` `systemd-analyze verify` warning 被 `2>&1` 後仍走 install | 若 future systemd 對 syntax error 升 error，腳本仍會 install 半成型 unit；建議 verify 失敗 → exit 11；warning-only 允許過 | 切 `verify || exit` 並區分 warn vs error |
| 3 | LOW | `openclaw-watchdog.service` vs macOS plist 對稱性 | plist `KeepAlive=true` + 無 `User=` (login user 自然非 root)；E1 用 `User=__ENGINE_USER__` + install script `id -un` fallback — `sudo` 時 `SUDO_USER` 取得，OK；但若 operator 用 `su - root` 啟 install，fallback `id -un=root` → unit 跑 root；目前 grep guard 不擋 root | install script 加 `[[ "$ENGINE_USER" == "root" ]] && fail` |
| 4 | LOW | `engine.service:73 Restart=on-failure` vs launchd plist `KeepAlive=true`（= `Restart=always`） | 跨平台行為**不對稱**：Linux SIGTERM exit-0 不重啟；macOS 任何退出都重啟。E1 注釋已說明（區分 operator manual stop），但 launchd plist 沒有對應 throttle/burst 設定 → Mac 5 連 crash 會無限 thrash | 文件補 plist `ExitTimeOut`/`ThrottleInterval` 與 systemd `StartLimitBurst` 對齊 plan（後續工作） |

**Cross-verify**：
- `bash -n install_*.sh` → PASS（E2 重跑 confirm，與 E1 report claim 一致）
- `grep -nE '/home/ncyu\|/Users/[^/]+' systemd/*` → 11 hit，**全為注釋示例**（占位符替換 doc / `:?` 預設值提示），**0 命中 logic line** → 跨平台 0 硬編碼 PASS
- `sed` 占位符替換失敗 → install script `grep -E '__[A-Z_]+__'` guard 攔下 exit 7/9 → atomic PASS
- `install -m 644` over `mv` → atomic 寫入 + 權限正確（不覆蓋 ACL bug）
- `daemon-reload` 在最後一步 — 不漏
- `EnvironmentFile=` 無 `-` 前綴 → 缺檔 systemd fail-closed = 預期語意（E1 design correct）
- secret 洩漏：`/proc/$PID/environ` 同 user 可讀（OK），`systemctl show` 不顯示 EnvironmentFile 內容（OK），stderr 不 echo env → **0 secret leakage**

---

## §2 RTO ≤ 5min 真實成立 verify

**E1 設計組合**：
- `RestartSec=10` + `StartLimitBurst=5 / 300s` → 連 5 crash 後 → failed state
- 最壞情境：5 crash × 10s = ~50s + engine cold startup ~30-60s（PG retry + IPC bind + binary mmap）= **~80-110s ≤ 5min** → PASS
- watchdog `RestartSec=10 + StartLimitBurst=10 / 600s` → watchdog crash → < 60s respawn ≤ runbook §2.1「< 1min」承諾 → PASS

**Verdict**：RTO ≤ 5min **數學上成立**，但實際成立**前提**：
1. PG 可達（engine 內 retry/backoff 未驗實際 RTO）
2. binary 未被 cargo incremental rebuild 覆蓋（proc-exe drift §5.2 教訓）— systemd unit 不防 `(deleted)` inode，仍須 `build_then_restart_atomic.sh` flock 配合
3. PreStart `test -s ipc_secret.txt` + `test -s openclaw_database_url` → 若 secret file 在 boot 時尚未 seed → systemd 直接 fail（**desired** fail-closed，非 RTO 失敗）

**未驗證**（spec-only / file-land-only，per E1 §3 注）：
- 演練 SOP 在 README 落地，但 E1 未真實跑 SOP；first-day live D-2 operator 必跑一次（spec §8 已列）

**E2 不阻**：RTO 設計合理，實證留 operator drill。

---

## §3 restart_all.sh 並存衝突分析

**並發風險**：
- `restart_all.sh:555 nohup rust/target/release/openclaw-engine` → 直接 spawn engine
- systemd `openclaw-engine.service` 同時 active → **兩 PID 競爭**：
  - IPC socket `engine.sock` 第二個 bind fail（fail-closed）
  - PG connection pool 雙倍消耗
  - `pipeline_snapshot.json` 互寫（atomic rename + temp file race）
- `restart_all.sh:474 graceful_stop_engine` 用 `pgrep -f openclaw-engine` → **會同時殺 systemd 啟的 engine**，但 systemd `Restart=on-failure` 看到 SIGTERM exit 不重啟（exit 0）→ 不會 thrash；但隨後 `nohup` spawn 一個 systemd 不管的 PID → systemd `is-active` 顯 inactive，watchdog 仍看 snapshot OK → 雙 control plane 分裂

**E1 mitigation 已做**：
- README.md §C「systemd 與 restart_all.sh 共存」明確「生產 = systemd；開發 = restart_all.sh」+ 「systemd 已啟 → 先 `sudo systemctl stop openclaw-engine openclaw-watchdog`」
- E1 report §5 步驟 5 顯式列為 deploy hand-action

**未做**（建議 follow-up，**不阻 E2**）：
- `restart_all.sh` 啟動前**檢測** `systemctl is-active openclaw-engine` = active → 提示 abort 並要 operator 顯式 `--override-systemd` flag；目前 silently dual-spawn
- 反向：`install_engine_service.sh` 啟動前**檢測** restart_all.sh 啟的 PID 存在 → 提示停掉再 install；目前不檢測

**E2 verdict**：當前 deploy SOP 在 README §C 明確切換步驟，**operator follow doc 即可避 race**；race 自動防護是 nice-to-have，非 first-day live blocker。

---

## §4 跨平台 portability verify

| 項 | 結果 |
|---|---|
| `/home/ncyu` / `/Users/ncyu` 硬編碼 grep | 11 hit 全在注釋 `如:` / `例:` 提示 — 0 logic line 違反 |
| 占位符替換 atomic | `mktemp` + `sed` + `grep -E '__[A-Z_]+__'` guard + `install -m 644` → atomic + 失敗不破壞既有 file PASS |
| macOS guard | `uname -s != Linux` exit 1，並提示用 launchd plist — PASS |
| launchd plist 對稱性 | engine plist 存在 + 註解明確 `KeepAlive=true` = `Restart=always`（**非** `on-failure`）；watchdog plist 存在但 E2 未深入比對 throttle / burst（建議後續 follow-up）|
| Apple Silicon Mac 未來部署 | systemd unit 走 Linux only，launchd plist 走 macOS；切換點 = `launchd_preflight.sh` + install_*_service.sh 一一對應 — 結構正確 |

**verdict**：跨平台 0 硬編碼 logic 違反 PASS；launchd 與 systemd 在 Restart 語意上**不對稱**（§1 issue 4 列為 LOW follow-up）。

---

## §5 對抗反問結果

| Q | E1 claim | E2 評估 |
|---|---|---|
| 「`Requires=` 空值真的合法？」 | 不在 report 提；line 38 留空 | **MED**：systemd 接受但會 warn；應整行刪除 |
| 「`bash -n` 通過 ≠ semantic safe，sed 替換對含 `\|` 路徑會炸？」 | `s\|__X__\|$VAL\|g` — 用 `\|` 為 delimiter；若 `$OPENCLAW_BASE_DIR` 含 `\|` 會炸 | `\|` 在 Unix path 非法字符 → 實際不會碰到，但若 operator 用詭異路徑（如含 space）→ `sed` 仍 OK（`\|` delimiter），且 `install -m 644` 處理 space 路徑 OK |
| 「`SUDO_USER` fallback 在 `su -` 場景如何？」 | E1 自己在 §uncertainty #3 提到，但未防護 | **LOW issue 3**：建議 install script 顯式擋 `ENGINE_USER=root` |
| 「PG 不可達 → 5 連 crash → failed state；operator 手動 reset 流程？」 | E1 report §uncertainty #1 提到 trade-off；README §B 沒寫 `systemctl reset-failed` recovery | LOW follow-up：README §B 補 `systemctl reset-failed openclaw-engine` 一行 |
| 「watchdog `Restart=always` + burst 10/600s — 真的不 thrash？」 | watchdog 是純 monitor + 1s poll；crash 通常 = python env 損毀（rare）；10 連 fail 後 failed state 合理 | PASS |
| 「`After=postgresql.service` — 若 PG 在另一台機（trade-core PG often localhost 但可能 remote）？」 | unit 只是 startup hint，engine 內含 retry，不依賴此 ordering | PASS |
| 「`KillSignal=SIGTERM` + `TimeoutStopSec=15` — engine cancel_token 10s window 真夠？」 | E1 注釋說「engine 內部 cancel_token shutdown 10s 足夠」+ 15s buffer | 對齊 `restart_all.sh:graceful_stop_engine` 5s window — `restart_all.sh` 比 systemd unit 嚴；不對稱但 systemd 給 buffer 是保守選擇，PASS |

---

## §6 退回清單（E1 in-place fix 建議，無需重 E2 round）

> E2 立場：以下 4 fix 均非 logic blocker，E1 可在當前 working tree 直接補；不要求重 round；建議 commit 前一併 push。

1. **MED**：`openclaw-engine.service:38` 刪整行 `Requires=`（空值 directive）
2. **LOW**：`install_engine_service.sh:89-91` + `install_watchdog_service.sh:105-107` — `systemd-analyze verify` 失敗時區分 warn vs error（建議：`verify` 退出碼非 0 但 stdout 含 `Warning` → 繼續；含 `Error` → exit 11）；當前實作對所有非 0 一律 warn
3. **LOW**：兩 install script 加 `[[ "$ENGINE_USER" == "root" ]] && { echo "[FAIL] 不允許 root"; exit 12; }`（在 `id -u "$ENGINE_USER"` 檢查附近）
4. **LOW**：`README.md §B` 補一行 `# 若 5 連 fail → sudo systemctl reset-failed openclaw-engine 再 start` recovery 提示

**不在退回範圍**（標 follow-up TODO）：
- restart_all.sh 啟動前 systemctl is-active 互檢（race 自動防護）
- launchd plist throttle / burst 補齊與 systemd `StartLimitBurst` 對稱
- `WatchdogSec=` 開啟需 engine_watchdog.py 補 sd_notify（E1 注釋已預留）
- GAP-A/F 真實 RTO drill（operator 任務）

---

## §7 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | PASS（GAP-A + GAP-F file-land，spec §10 對應） |
| 沒有 except:pass / 靜默吞異常 | N/A（bash + systemd unit；install script `set -euo pipefail` + 顯式 exit codes 1-9） |
| 日誌使用 %s 格式 | N/A（bash） |
| 新 API 端點有 _require_operator_role() | N/A（無 API 改動） |
| except HTTPException 順序 | N/A |
| detail=str(e) 改為 Internal server error | N/A |
| asyncio threading.Lock | N/A |
| 私有屬性穿透 | N/A |

## §8 OpenClaw 9 條（§3）checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` | PASS（11 hit 全為注釋示例） |
| 注釋規範（中文為主） | PASS（5 file 開頭 MODULE_NOTE 中文塊） |
| Rust unsafe / unwrap / panic | N/A |
| IPC schema 一致性 | N/A |
| Migration Guard A/B/C | N/A（無 SQL） |
| healthcheck 配對 | PASS（README §3 RTO SOP + spec §8 sign-off block） |
| Singleton / monkey-patch | N/A |
| 文件大小 800/2000 行 | PASS（最大 README 149 行） |
| Bybit API 改動 | N/A |

## §9 §5 Multi-session race check（governance enforce 2026-05-16）

| Check | 狀態 |
|---|---|
| 5a fetch + sibling window | N/A（E2 review file-land；尚未 commit；無 sibling push 風險直到 PM commit） |
| 5b sub-agent IMPL DONE status clean | E1 report claim 6 file 全屬本任務 scope；E2 verify `git status` 應全 staged 同一 commit — 留 PM commit 時驗 |
| 5c unknown WIP 禁 revert | N/A |
| 5d Sign-off report path clean | 本 report 唯一 file E2 寫；不修改 E1 改動 |
| 5e sibling push 期間重 fetch | N/A |

---

## §10 結論

**APPROVE TO E4 with 4 minor (1 MED + 3 LOW) fix 建議**。

- E1 IMPL 結構正確 / 0 CRITICAL / 0 HIGH
- 跨平台 0 硬編碼 logic 違反
- `bash -n` syntax PASS（E2 重跑 confirm）
- atomic install 路徑 PASS
- RTO ≤ 5min 設計成立（實證留 operator drill，spec §8 已列）
- restart_all.sh 並存衝突由 README §C SOP 明確切換步驟 mitigate；race 自動防護建議 follow-up
- 1 MED（Requires= 空值）+ 3 LOW（verify error 區分 / root user guard / reset-failed 提示）建議 E1 in-place 補，不重 round

**下一步**：E1 補 §6 4 fix → 直接過 E4 regression（無 logic 變動，regression 限於 `bash -n` 重跑 + README 渲染 check）→ PM commit。

E2 REVIEW DONE: APPROVE-WITH-MINOR · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-27--ops_4_systemd_e2_review.md
