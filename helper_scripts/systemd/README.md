# helper_scripts/systemd/ — Linux systemd Unit Templates

## 目的

per **P0-OPS-4 first-day-live runbook** (`docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md`) §10 GAP A + GAP F：

- **GAP A**：watchdog 自己 crash 後無 systemd 自動 respawn → RTO ~ manual
- **GAP F**：engine SIGTERM 後依賴 manual respawn → RTO 違反 < 5min 承諾

本目錄提供 Linux `trade-core` 上的 systemd unit 模板 + 安裝腳本，補齊 first-day live RTO 鏈。

## 範圍

| File | 對應 macOS launchd | GAP |
|---|---|---|
| `openclaw-engine.service` | `helper_scripts/deploy/com.openclaw.engine.plist` | F |
| `openclaw-watchdog.service` | `helper_scripts/deploy/com.openclaw.engine-watchdog.plist` | A |
| `install_engine_service.sh` | — | F |
| `install_watchdog_service.sh` | — | A |

## 跨平台 Portability

- **Linux trade-core (runtime)** — 用本目錄 systemd unit
- **macOS dev (本機開發 / 未來 Apple Silicon 部署)** — 用 `helper_scripts/deploy/*.plist` + `launchd_preflight.sh`
- **路徑無硬編碼** — 所有 `/home/ncyu` 在 unit 模板中是 `__OPENCLAW_BASE_DIR__` 占位符，install script `sed` 替換為 `$OPENCLAW_BASE_DIR`

## Operator Deploy Hand-Action Checklist

按順序執行（**僅 trade-core Linux runtime；Mac dev 跳過**）：

### A. 一次性 install（每次 srv repo update 後 unit template 變更才需重跑）

```bash
ssh trade-core
cd ~/BybitOpenClaw/srv

# 1. 確認 env vars 設定
export OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv
export OPENCLAW_DATA_DIR=/tmp/openclaw   # 或 $HOME/.openclaw_runtime
export OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets

# 2. 確認 engine binary 已 build
ls -la $OPENCLAW_BASE_DIR/rust/target/release/openclaw-engine
# 若無 → bash helper_scripts/restart_all.sh --rebuild 先建好

# 3. 安裝 engine service unit
sudo OPENCLAW_BASE_DIR=$OPENCLAW_BASE_DIR \
     OPENCLAW_DATA_DIR=$OPENCLAW_DATA_DIR \
     OPENCLAW_SECRETS_ROOT=$OPENCLAW_SECRETS_ROOT \
     bash helper_scripts/systemd/install_engine_service.sh

# 4. 安裝 watchdog service unit
sudo OPENCLAW_BASE_DIR=$OPENCLAW_BASE_DIR \
     OPENCLAW_DATA_DIR=$OPENCLAW_DATA_DIR \
     OPENCLAW_SECRETS_ROOT=$OPENCLAW_SECRETS_ROOT \
     bash helper_scripts/systemd/install_watchdog_service.sh
```

### B. Enable + Start（決定首日 live 走 systemd 後操作）

```bash
# Engine
sudo systemctl enable openclaw-engine
sudo systemctl start openclaw-engine
sudo systemctl status openclaw-engine

# Watchdog
sudo systemctl enable openclaw-watchdog
sudo systemctl start openclaw-watchdog
sudo systemctl status openclaw-watchdog

# 若 5 連 fail（StartLimitBurst 達上限）→ 進 failed state，再 start 不會起
# 必須先 reset-failed 清計數器，再 start：
#   sudo systemctl reset-failed openclaw-engine && sudo systemctl start openclaw-engine
#   sudo systemctl reset-failed openclaw-watchdog && sudo systemctl start openclaw-watchdog
```

### C. 與既有 restart_all.sh 共存

- `restart_all.sh` 仍可用於 dev / debug — 但若 systemd unit 已啟動，需先 `sudo systemctl stop openclaw-engine openclaw-watchdog` 否則兩條啟動鏈打架。
- 推薦範式：**生產 = systemd；開發 = restart_all.sh**。

## RTO ≤ 5min 驗證 SOP

per runbook §2.1 RTO target「Engine crash → watchdog restart < 5 min」。

### Step 1 — baseline snapshot

```bash
ssh trade-core "ls -la /tmp/openclaw/pipeline_snapshot.json"
# 記下 mtime（baseline timestamp）
```

### Step 2 — 模擬 engine crash

```bash
# 強制 SIGKILL（模擬 panic / OOM）
ssh trade-core "sudo pkill -9 -f 'rust/target/release/openclaw-engine'"

# 立即記時 t0
date -u +%s
```

### Step 3 — 等 systemd respawn

```bash
# 連續 poll until systemctl 顯 active (running) 且新 PID 出現
ssh trade-core "for i in {1..30}; do
    state=\$(systemctl is-active openclaw-engine)
    pid=\$(pgrep -f 'rust/target/release/openclaw-engine' | head -1)
    echo \"\$(date -u +%s) state=\$state pid=\$pid\"
    [ \"\$state\" = \"active\" ] && [ -n \"\$pid\" ] && break
    sleep 5
done"
```

### Step 4 — 驗 snapshot age 恢復 < 45s

```bash
ssh trade-core "stat -c %Y /tmp/openclaw/pipeline_snapshot.json"
# 應在 systemd respawn 後 30~90s 內出現新 mtime
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
# 應顯 engine_alive=true + snapshot_age_seconds < 45
```

### Pass criteria

| 項 | 預期 | 失敗 → |
|---|---|---|
| systemctl respawn 時間 | < 30s（RestartSec=10 + start delay） | 升 P1，檢 systemd journal |
| snapshot 新鮮度恢復 | < 45s after respawn | 升 P1，engine startup 卡住排查 |
| **end-to-end RTO** | **< 5min** | 違反 first-day live SLA → ABORT |

### 注意

- 本 sub-agent **不真實 deploy / 不真實跑此 SOP** — 寫成 doc 供 operator first-day live 前演練。
- 演練前必先確認非交易時段 + paper-mode（避實單部分成交殘留）。
- 演練後寫 `docs/CCAgentWorkSpace/E3/workspace/reports/YYYY-MM-DD--rto_systemd_drill_report.md`。

## 反模式 / 不做

- **不**在 unit 設 `Restart=always` 於 engine — `on-failure` 才區分 operator manual stop（exit 0）vs crash
- **不**設 `MemoryMax` — 違反 fail-closed 語意（OOM kill 留半成型 IPC）
- **不**在 install script 自動 `systemctl start` — 留 operator 5-gate 決策
- **不**用 `0.0.0.0` 或 network all-interface bind — engine 走 IPC unix socket
- **不**寫 `User=root` — engine 以 `ncyu`（或 operator 指定 user）身份跑

## Cross-reference

- spec: `docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md`
- macOS 對應: `helper_scripts/deploy/launchd_preflight.sh`
- watchdog 內部 CLI: `helper_scripts/canary/engine_watchdog.py --help`
- restart_all.sh dev path: `helper_scripts/restart_all.sh`
- atomic deploy: `helper_scripts/build_then_restart_atomic.sh`
