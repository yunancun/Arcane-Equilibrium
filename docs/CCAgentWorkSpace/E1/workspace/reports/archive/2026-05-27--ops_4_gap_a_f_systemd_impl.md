# E1 IMPL — P0-OPS-4 GAP A + GAP F systemd unit · 2026-05-27

**Scope**: PA spec `docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §10 GAP A (watchdog respawn) + GAP F (engine systemd unit)
**Status**: IMPL DONE，待 E2 審查
**Out of scope**: GAP B / GAP D（MIT 負責）；不真實 install / start service；不 commit

## §1 GAP-A watchdog.service 內容 + install 步驟

**File**: `srv/helper_scripts/systemd/openclaw-watchdog.service`（93 行）

關鍵設計：
- `Restart=always` + `RestartSec=10` + `StartLimitBurst=10 / 10min` — watchdog 是純監控，crash 自動 respawn < 60s（per RTO §2.1）
- `User/Group=__ENGINE_USER__/__ENGINE_GROUP__`（非 root；install script 自動帶入 SUDO_USER）
- `EnvironmentFile=__OPENCLAW_SECRETS_ROOT__/environment_files/basic_system_services.env` — 載 PG / OPENCLAW_ALLOW_MAINNET / 其他 runtime env
- CLI args 對齊 `restart_all.sh:226` + launchd plist：`--stale-threshold 45 --grace-period 120 --poll-interval 1`
- `After=openclaw-engine.service` 給 startup hint 但**非硬依賴**（watchdog 可先啟，engine 後啟）
- `WatchdogSec` 暫註解 — watchdog python 進程未補 sd_notify(WATCHDOG=1)，避誤殺
- PreStart 三檢：python binary / engine_watchdog.py / data dir 存在

**Install**: `srv/helper_scripts/systemd/install_watchdog_service.sh`（126 行）
- Linux-only guard (`uname -s != Linux` exit 1)
- root guard (`EUID != 0` exit 2)
- `PYTHON_BIN` 偵測順序：`$PYTHON_BIN` > `$ENGINE_USER` home `.venv/bin/python3` > `/usr/bin/python3`
- atomic `mktemp` + sed 6 占位符替換 + 占位符殘留 grep guard + `systemd-analyze verify` + `install -m 644` + `daemon-reload`
- **不**自動 `systemctl start` — 留 operator 5-gate 後手動啟

## §2 GAP-F engine.service 內容 + install 步驟

**File**: `srv/helper_scripts/systemd/openclaw-engine.service`（94 行）

關鍵設計：
- `Restart=on-failure`（非 `always`） — SIGTERM exit 0 視 operator 主動 stop，不重啟；只有非 0 exit (panic/OOM) 才 respawn
- `RestartSec=10` + `StartLimitBurst=5 / 5min` — 5 連 fail 進 failed state（per RTO §2.1「5 連 fail → circuit-break」）
- `EnvironmentFile=basic_system_services.env` + 補 `Environment=` 對齊 `restart_all.sh:520-535` 完整 env list（OPENCLAW_BASE_DIR / DATA_DIR / CANARY_MODE / IPC_SOCKET / DATABASE_URL_FILE / IPC_SECRET_FILE）
- PreStart 三 fail-closed 檢：engine binary 可執行 / ipc_secret.txt 非空 / openclaw_database_url 非空
- `KillSignal=SIGTERM` + `TimeoutStopSec=15` — 對齊 engine 內 cancel_token shutdown 10s
- `After=network-online.target postgresql.service` — PG 不在同機亦不阻啟（engine 內含 retry）
- **不**設 `MemoryMax` — OOM kill 違 fail-closed（留半成型 IPC state）
- `LimitNOFILE=65536`

**Install**: `srv/helper_scripts/systemd/install_engine_service.sh`（107 行）
- 同 Linux + root guard / atomic sed / 占位符 grep / daemon-reload / 不自動 start

## §3 RTO ≤ 5min 驗證 SOP

寫於 `srv/helper_scripts/systemd/README.md` 「RTO ≤ 5min 驗證 SOP」（4 步）：

1. **baseline snapshot** — `stat -c %Y /tmp/openclaw/pipeline_snapshot.json` 記 mtime
2. **模擬 crash** — `sudo pkill -9 -f 'rust/target/release/openclaw-engine'` + `date -u +%s` 記 t0
3. **等 respawn** — 30 次 ×5s poll `systemctl is-active openclaw-engine` + `pgrep` 看新 PID
4. **驗 snapshot age 恢復** — `python3 helper_scripts/canary/engine_watchdog.py --status` 應顯 `engine_alive=true` + `snapshot_age_seconds < 45`

Pass criteria：systemctl respawn < 30s / snapshot 新鮮度恢復 < 45s / end-to-end RTO < 5min。

**注意**：本 sub-agent 不實跑 SOP；只寫 doc 供 operator first-day live 前演練；演練必非交易時段 + paper-mode。

## §4 跨平台 Portability

| 平台 | 部署方式 | 路徑來源 |
|---|---|---|
| Linux trade-core | 本目錄 systemd unit | `$OPENCLAW_BASE_DIR` env |
| macOS dev / 未來 Apple Silicon | `helper_scripts/deploy/*.plist` + `launchd_preflight.sh` | 同 `__BASE__/__HOME__` 占位符 |

- 所有 `/home/ncyu` / `/Users/ncyu` 在 service unit 模板中均為 `__OPENCLAW_BASE_DIR__` 占位符（install script sed 替換）
- `grep -nE '/home/ncyu|/Users/ncyu' systemd/*.service systemd/*.sh` — 命中 9 行**全部**在 docstring `如:` / `例:` 注釋（非 logic）
- `bash -n install_*.sh` 兩 script syntax PASS
- macOS 跑 install script → guard exit 1 + 提示用 launchd plist

## §5 Operator Deploy Hand-Action Checklist

完整版 `srv/helper_scripts/systemd/README.md` §A/B/C；摘要 **6 步**：

1. `ssh trade-core` + 確認 `OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT` env vars
2. 驗 engine binary 存在 — `ls -la $OPENCLAW_BASE_DIR/rust/target/release/openclaw-engine`（無則先 `restart_all.sh --rebuild`）
3. `sudo OPENCLAW_BASE_DIR=... bash helper_scripts/systemd/install_engine_service.sh`
4. `sudo OPENCLAW_BASE_DIR=... bash helper_scripts/systemd/install_watchdog_service.sh`
5. 確定走 systemd 後：`sudo systemctl stop` 既有 restart_all.sh 啟的 engine + watchdog
6. `sudo systemctl enable + start openclaw-engine openclaw-watchdog`

**注意**：步驟 5 不能跳 — systemd 與 restart_all.sh 啟動鏈打架會 race（兩個 engine 同時連 PG / IPC socket）。

## 修改清單

| 路徑 | 行數 | 類型 |
|---|---|---|
| `srv/helper_scripts/systemd/openclaw-engine.service` | 94 | NEW |
| `srv/helper_scripts/systemd/openclaw-watchdog.service` | 93 | NEW |
| `srv/helper_scripts/systemd/install_engine_service.sh` | 107 | NEW (exec) |
| `srv/helper_scripts/systemd/install_watchdog_service.sh` | 126 | NEW (exec) |
| `srv/helper_scripts/systemd/README.md` | 149 | NEW |
| `srv/helper_scripts/SCRIPT_INDEX.md` | +12 | EDIT (新增 §2026-05-27 entry) |

Total: 569 LOC new + 12 LOC index edit。

## 治理對照

- **CLAUDE.md §四 5 gate**：unit `Restart=on-failure` 對齊 — operator manual stop (exit 0) **不**自動清 `authorization.json`（依 `restart_all.sh --keep-auth` 邏輯，crash auto path 自然保留 auth）
- **CLAUDE.md §六 跨平台**：unit 模板 `__OPENCLAW_BASE_DIR__` 占位符 + install script 用 `$OPENCLAW_BASE_DIR` env，0 硬編碼 `/home/ncyu`
- **CLAUDE.md §七 新腳本必更新 SCRIPT_INDEX**：已加 5 entry
- **CLAUDE.md §七 新增 unit 寫 MODULE_NOTE**：兩 unit 模板 + 兩 install script 開頭都有 MODULE_NOTE 中文塊
- **PA spec §10**：GAP A + GAP F install-only (file land) 完成；不 deploy；deploy 由 operator first-day live 前獨立 hand-action
- **PA spec §8 Pre-Go-Live Ratification**：E3 sign-off「systemd / launchd respawn unit 已 land」可勾（GAP A/F file 部分）

## 不確定之處

1. **`StartLimitBurst=5` 是否合理** — engine 5 連 fail 應 circuit-break，但若是 PG 短暫不可達 5 連 fail 後 systemd 停 → 需 operator 手動 reset；vs `Restart=always` 不停 thrash。當前選 5 對齊 RTO §2.1「5 連 fail → circuit-break + alert」；可由 PA / E3 review 拍板
2. **`WatchdogSec` 是否該開** — 預留註解；要開需先 patch `engine_watchdog.py` 加 `sd_notify` 呼叫（systemd-notify 或 cysystemd）；本 sub-agent 不擴 watchdog scope
3. **`User=` 預設** — install script 用 `SUDO_USER` env 偵測；若 operator 用 `su - root` 切換非 sudo 跑可能 fallback 到 root（會被 grep guard 攔下但語意不純）— 建議 install script 顯式提示 `ENGINE_USER` env
4. **systemd-analyze verify warning** — install script 對 warning 不 abort（`/dev/null || true`）；若 future systemd 版本對 `EnvironmentFile=` 缺檔報 error 而非 warn，install 可能誤過；保留 manual `systemctl status` 兜底

## Operator 下一步

1. 等 E2 review 本 IMPL 是否符合 PA spec §10 GAP A/F + CLAUDE.md §七
2. 等 E4 regression — 本 sub-agent 未跑 `restart_all.sh` / `build_then_restart_atomic.sh` 兜底 path 是否仍 work（systemd unit + 既有 shell startup 鏈共存）
3. operator first-day live 前 D-2 走 §3 RTO ≤5min SOP 演練 1 次（非交易時段 + paper-mode）
4. 演練後 E3 補 sign-off report — `docs/CCAgentWorkSpace/E3/workspace/reports/YYYY-MM-DD--rto_systemd_drill_report.md`

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_gap_a_f_systemd_impl.md）
