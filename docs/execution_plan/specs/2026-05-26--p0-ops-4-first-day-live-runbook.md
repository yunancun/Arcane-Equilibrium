# P0-OPS-4 — First-Day Live 24h Runbook（spec-only / pre-ratification）

**Date**: 2026-05-26
**Status**: SPEC-DRAFT / pending operator + PA + E3 + BB + QA sign-off
**Scope**: Sprint 4 first Live $500 W18-21 (~2026-09 初) D-1（pre-launch）→ T+0 launch → T+24h closure
**Owner**: PA spec → operator ratify → ops handoff
**Trigger**: KNOWN_ISSUES.md:539-543（P0-OPS-4 blocker）/ TODO.md §1 第 3 列
**Cross-ref**: CLAUDE.md §四 hard boundaries / TODO.md §5 9 safety invariants / AMD-2026-05-21-01 v2 fail-safe / ADR-0030 4-gate / ADR-0034 LAL

---

## 0. Runbook 性質 + 邊界宣告

本 runbook 是 **operator + on-call agent 在第一日 live 24h 必須照表執行的 SOP**，**不**含：
- 策略 alpha 評估（由 P0-EDGE-1 + QC 仲裁）
- credential rotation 程序（P0-OPS-2 另出 runbook）
- legal / ToS / geography 合規（P0-OPS-3 另出 runbook）
- HTTPS / network hardening（P0-OPS-1 另出 runbook）

**前提**：本 runbook 假設 OPS-1/2/3 全 closure；任一未 closure 即 ABORT first-day live。

---

## 1. 24h Staffing Schedule（cadence + per-stage metrics）

### 1.1 階段 cadence overview

| Stage | Time anchor | Operator action | On-call agent (CC) action | Pass criteria → next stage |
|---|---|---|---|---|
| **T-1h** | -60 min | posture verify + 5-gate dry-run | 9 invariant dashboard 全 GREEN | 任一 invariant RED → 推遲 launch ≥ 24h |
| **T+0** | launch | 簽 authorization.json + verify 5 gate green-light | watchdog status JSON + binary SHA align | mismatch → 1 次原子 redeploy；2 連 fail → ABORT |
| **T+15min** | +15 min | 觀察 first 3 fills（若有） | 6 health domain freshness < 30s + fills 寫入 trading.fills | health degraded → §3 escalation |
| **T+1h** | +60 min | first checkpoint review | health 60-min 滾動 PASS rate ≥ 95% + 0 panic | < 95% 或 panic → §3 |
| **T+4h** | +240 min | mid-shift handoff | risk_verdicts row count 增長 + lease emission rate non-zero | lease 連續 60min 0 emission → §3 |
| **T+12h** | +720 min | sleep-shift handoff（or schedule sleep）| 6 domain 12h aggregate / unrealized PnL band | drawdown > daily budget 50% → 主動降 Defensive |
| **T+24h** | +1440 min | T+24h closure report | 14 invariant summary + PG row attribution_chain_ok % | 任 critical invariant FAIL → second-day live 暫停 + RCA |

### 1.2 T-1h posture verify checklist（每項必填 P/F）

| # | Check | Source / Command | Pass criteria |
|---|---|---|---|
| 1 | binary SHA matches `/proc/$PID/exe` | `ssh trade-core "sha256sum /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine; readlink /proc/$(pgrep -f openclaw-engine \| head -1)/exe"` | 兩 SHA 完全一致 + exe 非 `(deleted)` |
| 2 | watchdog single-instance | `ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"` | `engine_alive=true` for paper/demo/live 三 engine |
| 3 | 6 health domain 30min PASS | `ssh trade-core "bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"` | 0 FAIL（WARN 容許但需 list） |
| 4 | authorization.json valid + signed | `ssh trade-core "cat $OPENCLAW_DATA_DIR/runtime_secrets/authorization.json \| jq '.expires_at,.environment,.signature_alg'"` | environment=mainnet + expires_at > now+12h + signature_alg!=null |
| 5 | OPENCLAW_ALLOW_MAINNET=1 set + persistent | `ssh trade-core "cat /proc/$(pgrep -f openclaw-engine \| head -1)/environ \| tr '\0' '\n' \| grep ALLOW_MAINNET"` | `OPENCLAW_ALLOW_MAINNET=1` present |
| 6 | Tailscale connectivity | `tailscale status \| grep trade-core` | Mac dev 端可達；非 100.x.x.x → ABORT |
| 7 | PG retention + compression 健康 | `ssh trade-core "psql -d trading_ai -c \"SELECT chunk_name, range_end FROM timescaledb_information.chunks WHERE hypertable_name='risk_verdicts' ORDER BY range_end DESC LIMIT 3;\""` | 最新 chunk range_end > now-2h |
| 8 | Bybit demo→mainnet endpoint config 對齊 | `ssh trade-core "grep bybit_endpoint $OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env"` | live slot 顯示 `mainnet` 非 `demo`（per P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG） |
| 9 | last_shutdown_kind sentinel | `ssh trade-core "ls -la $OPENCLAW_DATA_DIR/last_shutdown_kind 2>/dev/null"` | 不存在（避免 boot 清 authorization.json）OR 內容非 `manual` |

任一 P/F 為 F → ABORT，operator 推遲 launch ≥ 24h 並走 RCA chain。

### 1.3 T+0 launch sequence（5-gate green-light）

按 CLAUDE.md §四 5 gate 順序逐個驗：

1. Python `live_reserved` 軟邊界 — GUI status badge 顯 `LIVE_RESERVED=true`
2. Python Operator role auth — operator login + 2FA + role=Operator
3. `OPENCLAW_ALLOW_MAINNET=1` — per T-1h check #5
4. valid secret slot — `ls -la $OPENCLAW_SECRETS_ROOT/secret_files/bybit/live/` 非空 + permissions 600
5. signed unexpired `authorization.json` — per T-1h check #4

**5 gate 全 green = launch；任一 FAIL → 不開 live**

### 1.4 Per-stage metrics 看什麼

| Stage | 必看 metric | SLA | 工具 |
|---|---|---|---|
| T+15min | `trading.fills` rows in last 15min（若有 intent） / `trading.intents` writer freshness | fills 數 = intents 接收數（fail-closed kill 不算） | psql query |
| T+1h | 6 domain × 60min rolling PASS rate / `learning.governance_audit_log` halt event 數 | PASS ≥ 95% / 0 halt event | passive_wait_healthcheck.sh + halt_audit.log tail |
| T+4h | `risk_verdicts` row 增長率 / `decision_lease` emission rate / unrealized PnL band | row 增長非 0；lease rate 非 0；PnL 在 ±0.5 × daily budget | psql + watchdog status |
| T+12h | 12h aggregate fill PnL / drawdown vs daily budget / 3 engine snapshot age | drawdown ≤ 50% daily budget；3 snapshot age < 45s | watchdog status + risk dashboard |
| T+24h | attribution_chain_ok % / 9 invariant snapshot / cron heartbeat 全 fire | attribution ≥ 99% / 0 invariant FAIL / 5 cron sentinel mtime fresh | passive_wait_healthcheck.sh + 14d audit query |

---

## 2. RTO / RPO Targets

### 2.1 RTO（Recovery Time Objective）

| Failure scenario | Target RTO | 已驗 / 預估 | 路徑 |
|---|---|---|---|
| Engine crash → watchdog restart | < 5 min | 驗：2026-05-21 13:31 UTC 4h 後恢復屬 incident，watchdog 自動 < 5 min | engine_watchdog.py auto-restart per exponential backoff (60s/120s/300s/600s/3600s) |
| Engine SIGTERM → manual restart (atomic) | < 10 min | 驗：build_then_restart_atomic.sh 7-phase ~3-5 min；atomic verify 30s | `ssh trade-core "bash helper_scripts/build_then_restart_atomic.sh"` |
| Watchdog crash → re-spawn | < 1 min | 預估；systemd / launchd-style respawn 未實 — **GAP A**（見 §10） | manual `nohup python3 helper_scripts/canary/engine_watchdog.py &` |
| API server crash → uvicorn restart | < 2 min | 驗 | `bash helper_scripts/restart_all.sh --api-only` |
| PG out-of-disk → recover | < 30 min（已知最久）| 預估；含 retention compress + chunk drop + 重啟 engine | 見 §5.4 incident playbook |
| Bybit API outage > 5min | depends（external）| 不可控；engine fail-closed retry off | 見 §5.3 |
| Authorization.json expired | < 5 min（operator 在線）| operator manual renew via Python `/auth/renew` endpoint | per CLAUDE.md §四 「Signed live authorization 必走 Python renew/approve」 |
| Tailscale outage → Mac dev 失聯 | depends；engine 不停 | engine 在 Linux 自運行；只影響 dev / monitor surface | 見 §5.6 |

### 2.2 RPO（Recovery Point Objective）

| Data class | Retention | RPO | 風險場景 |
|---|---|---|---|
| `trading.fills` / `trading.intents` / `trading.orders` | 永久（無 retention drop）| 0（fsync write）| PG 主庫毀損 → 待 backup restore（GAP B） |
| `risk_verdicts` hypertable | 30d retention drop + 7d compression（V075）| ≤ 1 row（per-event INSERT）| 過期 chunk drop 後不可重建 |
| `learning.governance_audit_log` | 永久 | ≤ 5s（append-only batch flush）| 主庫毀損 |
| `halt_audit.log` (JSONL append-only fsync) | 永久（無 rotate cron — **GAP C**）| 0（per-event fsync）| 文件系統毀損 |
| `decision_lease` records | per ADR-0008 lifecycle | ≤ 60s（state machine snapshot 間距）| 引擎 crash 期間在飛 lease 失去 in-memory state |
| Bybit account state（position / balance）| Bybit 端權威 | 0（Bybit 主庫）| 不影響本地 RPO |
| `pipeline_snapshot.json` watchdog heartbeat | 即時覆寫 | < 5s | crash 期 stale → watchdog 觸發；RPO 不適用（觀測 only） |

**Known data loss windows**：
1. Engine crash 期間（typical < 5 min）— in-memory 已 emit 但未落 PG 的 lease state；mitigation = engine 重啟自 PG 恢復最後 settled snapshot
2. risk_verdicts 30d 前資料一定 drop — operator 須在 30d 內歸檔需保留樣本
3. halt_audit.log 無 rotate → 文件 inode 失效（rare）即全 loss — GAP C 修法見 §10

### 2.3 PG dump cadence（DR）

**現況**：未排定 PG dump cron — **GAP D**（見 §10）
**建議**：
- daily logical dump（`pg_dump --schema=trading,learning,governance,system`）→ NAS 40TB 異地
- weekly full base backup（`pg_basebackup` + WAL archive）
- 留 30d × 7 = 210 個 dump rotation
- restore drill 至少 quarterly

---

## 3. Emergency Liquidate Path

### 3.1 三條合法觸發路徑

| 路徑 | 觸發點 | Authorization 要求 | Partial-fill 處置 |
|---|---|---|---|
| **(A) GUI Emergency Halt button** | Console banner 永遠 active button（per AMD-2026-05-21-01 v2 §5.3）| Operator role + 2FA | freeze auto path + Defensive；fills 不可逆（per ADR-0034 §Decision 5） |
| **(B) SM-04 → Defensive auto-trigger** | `RiskEvent::NotificationFailsafeTimeout` / 6 freeze trigger 任一命中 | engine auto；無 operator click | active_de_risking + reduce_only + new_entries_allowed=false + 縮 SL 至 entry + sync exchange conditional |
| **(C) Manual flatten via REST endpoint** | `POST /api/v1/risk/unhalt-session` 反向；或 `clean_restart_flatten.py --env mainnet` | risk:write role | reduce_only market order + 取消未成交 + 5 輪 verify 殘尾 |

**禁用路徑**（不在 runbook 內）：
- Bybit Web UI 手動關倉（會破壞 audit chain；GAP E：需 add cross-check guard）
- 直接 kill engine process（不會 cancel pending orders；違反 §Decision 9 雙重防線）

### 3.2 SOP — Emergency liquidate execution

**Phase 1 — assess（≤ 30s）**：
1. `ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status"` 看 engine state
2. 確認當前 SM-04 mode：normal / cautious / reduced / defensive / circuit_breaker
3. 確認當前 position：psql `SELECT symbol, side, qty, avg_entry FROM trading.positions WHERE engine_mode='live';`

**Phase 2 — 5-gate force pause（≤ 60s）**：
1. operator click GUI Emergency Halt button OR ssh `curl -X POST /api/v1/risk/halt-session ...`
2. 5 gate live boundary 即時撤 `live_reserved=false`
3. 確認 `learning.governance_audit_log` 寫入 `halt_session_set` event

**Phase 3 — flatten（≤ 5 min）**：
1. `ssh trade-core "python3 helper_scripts/clean_restart_flatten.py --env mainnet"`
2. 監看 stdout 5 輪 verify 殘尾 fills；每輪間距 ~30s
3. 5 輪 verify 後 `psql -c "SELECT COUNT(*) FROM trading.orders WHERE status='New' AND engine_mode='live';"` 應 = 0

**Phase 4 — closure audit（≤ 5 min）**：
1. 拍照 GUI screenshot（unrealized PnL=0、無 open position）
2. `cat $OPENCLAW_DATA_DIR/halt_audit.log | tail -20` 確認 halt event 落地
3. 寫 incident report 進 `docs/CCAgentWorkSpace/PA/workspace/reports/YYYY-MM-DD--first_day_liquidate_incident.md`

**Phase 5 — 復原條件**：
- 7d cooling（per AMD §5.3）
- operator manual 解除 + 重新走 5-gate launch sequence
- 不允許「emergency liquidate 後當日重啟 live」

### 3.3 Partial-fill 處置

Bybit 市價單仍可能 partial：
1. clean_restart_flatten.py 5 輪 verify 即為 partial-fill 兜底 — 殘尾再下單
2. 5 輪後仍有殘尾 → 升 §4 ESCALATE manual intervention
3. 殘尾 < min lot size → 接受 dust 殘留 + audit `dust_after_liquidate=true`

---

## 4. Escalation Path

### 4.1 6 health domain WARN → CRITICAL 五階梯

| Stage | Trigger | Owner / Decision | Timeout | Next |
|---|---|---|---|---|
| **L0 normal** | 6 domain × 30min PASS | engine auto | – | – |
| **L1 WARN** | 1-2 domain WARN（健康分數 60-79 / 60-90% range）| watchdog log only；CC dashboard yellow | 持續 > 15min → L2 | observability ↑ |
| **L2 DEGRADED** | 3+ domain WARN OR 1 domain CRITICAL OR 60min PASS rate < 95% | on-call agent ping operator via 3-channel | **operator response < 30 min** | 否則 L3 |
| **L3 NOTIFY FAILSAFE** | 三路通知（Slack + email + Console banner）全失敗 OR operator 30 min 無 response | engine auto；emit `RiskEvent::NotificationFailsafeTimeout` | **wait 1h**（per AMD §5.1）| 無 operator → L4 |
| **L4 SM-04 DEFENSIVE** | L3 timeout 1h 內 operator 無 response | engine auto；SM-04 → Defensive | 立即 active_de_risking；reduce_only；縮 SL 至 entry | 持續 monitor |
| **L5 LIQUIDATE + HALT** | SM-04 Defensive 觸後仍 detected anomaly（如 kill criteria fire / fail-safe gate cascade FAIL）| engine auto；entry §3 emergency liquidate path | 立即 | 持續 halt + 7d cooling + operator manual review |

### 4.2 五大關鍵 escalation timeout（operator 必背）

> 這 5 個數字是 first-day live 的最關鍵 governance bound：

1. **operator response window @ L2 DEGRADED = 30 min**（不 response → L3）
2. **三路通知 全 fail → SM-04 escalation wait = 1h**（per AMD §5.1）
3. **engine crash → watchdog auto-restart RTO = 5 min**（5 連 fail → circuit-break + alert）
4. **L4 SM-04 Defensive 觸後 cooling 必經 = 7d**（per AMD §5.3 + ADR-0044）
5. **Bybit API timeout fail-closed retry = 0**（per CLAUDE.md §四；任何 nonzero retCode 立即 fail）

### 4.3 三路通知冗餘 + 自動 escalation

per AMD-2026-05-21-01 v2 §5.1：

- Slack ≤ 10s emit / email ≤ 60s emit / Console banner 同步 emit
- 任一路 fail 不影響其他兩路
- 三路 **全 fail** → freeze + 1h wait → SM-04 Defensive 自動 escalation
- 不採 v1 「auto-recovery 通道恢復後自動 unfreeze」反模式
- 復原必 operator manual 解除 + 7d cooling

---

## 5. Incident SOP Playbooks

### 5.1 Engine SIGTERM family（2026-05-21 09:58 UTC marker）

**Symptom**：engine + watchdog 同時消失，watchdog 不自動 respawn

**Diagnose**：
```
ssh trade-core "ps aux | grep -E 'openclaw-engine|engine_watchdog' | grep -v grep"
ssh trade-core "journalctl --since '1 hour ago' | grep -E 'SIGTERM|engine_watchdog'"
ssh trade-core "tail -50 /tmp/openclaw/engine.log"
```

**Recover**：
```
ssh trade-core "bash helper_scripts/build_then_restart_atomic.sh"
ssh trade-core "nohup python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw > /tmp/openclaw/watchdog.log 2>&1 &"
```

**RTO**：< 10 min（含 atomic verify + watchdog respawn）

**Post-mortem**：
- 確認 SIGTERM 來源（systemd / OOM-killer / manual / 跨 session）
- 若多 session race → GAP F：systemd unit + restart policy 未實裝
- 寫 PA report；考慮升 P1-WATCHDOG-RESPAWN-SOP

### 5.2 proc-exe drift（2026-05-25 ×3 reproduce）

**Symptom**：`/proc/$PID/exe` 顯 `(deleted)`，binary inode 被 cargo incremental rebuild 覆蓋

**Diagnose**：
```
ssh trade-core "readlink /proc/$(pgrep -f openclaw-engine | head -1)/exe"
ssh trade-core "pgrep -af 'cargo build|cargo test'"
```

**Recover**：
```
ssh trade-core "bash helper_scripts/build_then_restart_atomic.sh"
```

**Mitigation 已 land**：
- `build_then_restart_atomic.sh` 7-phase flock（2026-05-25）
- `restart_all.sh --require-clean-build-window` flag
- sub-agent dispatch SOP（per `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`）

**RTO**：< 10 min

### 5.3 Bybit API outage > 5 min

**Symptom**：fills 停 / orders rejected with retCode != 0 / WS 斷線

**Engine 自動行為**：
- 任 nonzero retCode → fail-closed 不重試（per CLAUDE.md §四）
- WS 斷線 → automatic reconnect with backoff
- Reconciler 對賬差異 → auto degrade `engine_mode → paper`（per 9 invariant #8）

**Operator action**：
1. 確認 Bybit status page（external）
2. 評估持倉 risk exposure；若 ≥ daily budget 50% → 走 §3 emergency liquidate（離線手動下單）
3. Bybit 恢復後 → wait 6 health domain 30min PASS → operator 重新 5-gate launch

**RTO**：external dependent；自動降 paper 立即（< 1 min）

### 5.4 PG out-of-disk

**Symptom**：`SQLSTATE 53100 disk full` / engine 開始寫 fail-soft

**Diagnose**：
```
ssh trade-core "df -h /var/lib/postgresql"
ssh trade-core "psql -d trading_ai -c \"SELECT hypertable_name, pg_size_pretty(total_bytes) FROM timescaledb_information.hypertable_size('risk_verdicts');\""
```

**Recover（30 min）**：
1. 觸發提早 chunk compression：`SELECT compress_chunk(c) FROM show_chunks('risk_verdicts', older_than => INTERVAL '7 days') c;`
2. 觸發 retention drop：`SELECT drop_chunks('risk_verdicts', INTERVAL '30 days');`
3. 若仍不夠 → archive `learning.governance_audit_log` 舊資料到 NAS（GAP G：archive script 未實裝）
4. 釋出空間後 → `bash helper_scripts/restart_all.sh --engine-only`

**Prevention**：
- daily cron monitor `df -h` 並 alert > 80%
- weekly check `risk_verdicts` chunk 數

### 5.5 Authorization.json expired

**Symptom**：engine `cancel_token shutdown` / 9 invariant #5 violate

**Recover**：
1. operator login GUI
2. 走 Python `/auth/renew` endpoint（NOT 手寫 JSON per CLAUDE.md §四）
3. 確認新 file `expires_at` > now+12h
4. `bash helper_scripts/restart_all.sh --keep-auth`

**RTO**：< 5 min（operator 在線）

### 5.6 Tailscale outage（Mac dev 失聯）

**Engine 行為**：engine 在 Linux trade-core 獨立運行不停

**Operator action**：
- engine + watchdog 不停 → 不需緊急 action
- 失去 GUI access → 用手機 4G 連 Bybit Web UI 監看 position
- 若 Tailscale > 1h 不恢復 → 物理到 Linux 主機 + 用 USB keyboard local login
- 若需 emergency liquidate → 走 Bybit Web UI（接受 audit chain 破壞 + 事後補 record）

**RTO**：取決 Tailscale；non-blocking for engine

---

## 6. Observability — Handoff Inspection Commands

per CLAUDE.md §16 + `docs/agents/context-loading.md` handoff SOP，**5 個必跑命令**：

```bash
# 1. 三端同步狀態
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"

# 2. Engine + watchdog 存活 + binary SHA
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "sha256sum /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine; readlink /proc/\$(pgrep -f openclaw-engine | head -1)/exe"

# 3. 6 health domain + cron heartbeat
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"

# 4. Trading throughput 30min view
ssh trade-core "psql -d trading_ai -c \"SELECT engine_mode, COUNT(*) AS fills_30min FROM trading.fills WHERE ts > NOW() - INTERVAL '30 minutes' GROUP BY engine_mode;\""

# 5. halt_audit.log tail（forensic）
ssh trade-core "tail -20 /tmp/openclaw/halt_audit.log 2>/dev/null || echo 'no halt audit since boot'"
```

**Log locations**：
- engine.log : `$OPENCLAW_DATA_DIR/engine.log`
- engine rotated : `$OPENCLAW_DATA_DIR/engine_logs/engine-*.log`
- watchdog : `$OPENCLAW_DATA_DIR/watchdog.log`
- halt_audit : `$OPENCLAW_DATA_DIR/halt_audit.log` (fallback `/tmp/openclaw/halt_audit.log`)
- API server : `$OPENCLAW_DATA_DIR/api.log` / uvicorn stdout
- canary events : `$OPENCLAW_DATA_DIR/canary_events.jsonl`

**Watchdog status JSON path**：
- 命令 `engine_watchdog.py --status` 印 stdout（per code review；watchdog_status.json file 未實裝 — **GAP H**，見 §10）
- TODO §6 `P2-WATCHDOG-STATUS-JSON-WRITER` 已記，未 land

---

## 7. DR Plan Summary

### 7.1 三大依賴 + 失效策略

| 依賴 | 失效模式 | 自動 fallback | Manual 救援 |
|---|---|---|---|
| PG (trading_ai) | out-of-disk / network / 主庫 corrupt | engine 寫 fail-soft + degrade paper（per 9 invariant #8）| §5.4 SOP + GAP D PG dump |
| Bybit API | timeout / nonzero retCode | fail-closed retry off + 自動 degrade paper | §5.3 SOP |
| Tailscale | network outage | engine 不停（不依賴 Tailscale）| 物理 local login |

### 7.2 NAS backup（40TB via 10GbE，per memory `project_hardware_constraints`）

**現況**：PG → NAS dump cron 未排（GAP D）；只有 manual ad-hoc

**建議 cadence**（pre-ratification）：
- daily 02:00 UTC：`pg_dump --schema=trading,learning,governance,system` → NAS
- weekly Sunday 03:00 UTC：full `pg_basebackup` + WAL archive
- monthly 1st：restore drill on staging Linux instance

---

## 8. Pre-Go-Live Ratification Checklist

| Role | Sign-off item | Source | 缺哪個 → ABORT? |
|---|---|---|---|
| **Operator** | 接受本 runbook 24h 排班負責（含 12h 睡眠期 on-call rotation 安排）| 本 §1 | YES |
| **Operator** | 接受 RTO < 5 min（engine crash）/ < 10 min（manual restart）SLA | 本 §2 | YES |
| **Operator** | 接受 emergency liquidate 觸後 7d cooling + 第二日 live 暫停條款 | 本 §3 + AMD §5.3 | YES |
| **Operator** | 5 escalation timeout 數字背熟 + 三路通知設定完成（Slack + email + Console push 全部配對）| 本 §4.2 | YES |
| **PA** | 本 runbook spec 通過 architectural 審查（與 9 invariant + 5-gate + AMD v2 fail-safe 一致）| 本 spec | YES |
| **E3** | OPS-1 HTTPS / OPS-2 cred rotation / OPS-3 legal+ToS 全 closure | KNOWN_ISSUES.md / TODO P0-OPS-1..3 | YES |
| **E3** | systemd / launchd respawn unit 已 land（GAP A / GAP F mitigation）| GAP 修法 | YES |
| **BB** | Bybit-facing API path 全走 fail-closed + reconciler 對賬 enabled | per CLAUDE.md §八 | YES |
| **BB** | clean_restart_flatten.py 對 mainnet 已 dry-run 並驗 reduce_only 行為 | dry-run report | YES |
| **QA** | 5 handoff inspection commands 走過一輪 + halt_audit.log fsync 驗 | 本 §6 | YES |
| **QA** | passive_wait_healthcheck.sh 6 domain × 30min PASS rate ≥ 95% 連續 ≥ 7d | TODO §0 + §5 | YES |
| **MIT** | PG dump cadence cron 已 land + restore drill quarterly schedule 已排（GAP D mitigation）| GAP 修法 | YES |
| **PM** | 本 ratification checklist 全 12 項 sign-off 集齊 | 本 §8 | YES |

**未集齊任一 → first-day live 推遲**。

---

## 9. Cross-References

- `srv/CLAUDE.md` §四 hard boundaries / §16 handoff inspection
- `srv/TODO.md` §0 三端同步 / §5 9 safety invariants / §13 drift + multi-session race
- `srv/docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` §5.1-§5.3 / §9.8 SM-04
- `srv/docs/adr/0008-decision-lease-state-machine.md`（lease lifecycle）
- `srv/docs/adr/0030-copy-trading-evidence-gated.md`（4-gate scoping）
- `srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL tier authority）
- `srv/docs/adr/0040-multi-venue-gate-spec.md`（venue boundary）
- `srv/docs/adr/0042` ~ `0045`（M3/M6/M7/M4 module hooks）
- `srv/helper_scripts/restart_all.sh` + `build_then_restart_atomic.sh`（atomic deploy chain）
- `srv/helper_scripts/canary/engine_watchdog.py`（watchdog status + inert probe）
- `srv/helper_scripts/db/passive_wait_healthcheck.sh`（6 health domain）
- `srv/helper_scripts/clean_restart_flatten.py`（emergency liquidate）
- `srv/docs/KNOWN_ISSUES.md:539-543`（P0-OPS-4 原始描述）

---

## 10. NEW Tooling Gaps（PA 識別 / 不在本 spec 實作）

下列 gap 需 **新增 tooling** 才能滿足本 runbook 要求；PA 不在本 spec 實作，**派 E1 子任務 dispatch packet**：

| Gap ID | 描述 | 影響 runbook 段落 | 估時 | Owner |
|---|---|---|---|---|
| **GAP A** | watchdog systemd respawn unit 未實裝 → watchdog 自己 crash 後無自動恢復 | §2.1 / §5.1 | 2-4 hr | E3 → E1 |
| **GAP B** | PG 主庫毀損 backup restore SOP 未驗 → RPO 不可承諾 | §2.2 / §5.4 | 4-6 hr（含 drill）| MIT |
| **GAP C** | halt_audit.log 無 rotate cron → 長期 unbounded growth + 單檔失效全 loss | §2.2 | 1-2 hr | E1 |
| **GAP D** | PG dump cadence cron 未排 → 無 DR backup | §2.3 / §7.2 | 3-5 hr（含 cron + sentinel）| MIT |
| **GAP E** | Bybit Web UI manual close 旁路 → audit chain 破壞 + 無 cross-check guard | §3.1 forbidden path | 4-8 hr（reconciler enhancement）| BB |
| **GAP F** | engine systemd unit + restart policy 未實裝 → SIGTERM 後依賴 manual respawn | §5.1 | 3-5 hr | E3 |
| **GAP G** | `learning.governance_audit_log` 舊資料 archive script 未實裝 → §5.4 PG full 時無法快速釋空間 | §5.4 | 2-4 hr | E1 |
| **GAP H** | watchdog_status.json file writer 未實裝（per TODO P2-WATCHDOG-STATUS-JSON-WRITER）→ CLI --status 命令需 ssh，無 file-based observability | §6 | 2-4 hr | E1（已記 TODO）|

**E1 dispatch packet（合併 8 gap）**：
- **Owner chain**：PA spec → E1×3（GAP A/F systemd, GAP C/G/H E1, GAP D/B MIT, GAP E BB）→ E2 → E4 → BB review → QA → PM
- **估時 total**：21-38 hr / 4 並行 sub-agent / 1 sprint wall-clock
- **不阻 spec sign-off**（spec sign-off 後可平行 land 各 gap）

**註**：GAP B/D 是 DR 範疇，必在 first-day live 前 land；GAP A/F 影響 RTO 承諾，必在 first-day live 前 land；GAP C/E/G/H 不阻 first-day live 但 strongly recommended。

---

## 11. Ratification Sign-off Block

| Role | Date | Signature / Commit SHA | Notes |
|---|---|---|---|
| Operator | | | |
| PA | 2026-05-26 | spec draft | 本 spec author |
| E3 | | | OPS-1/2/3/A/F gap clearance |
| BB | | | clean_restart_flatten dry-run + GAP E |
| QA | | | 5 handoff command walk-through |
| MIT | | | GAP B/D land |
| PM | | | final ratification + Sprint 4 first Live unlock |
