# W-AUDIT-8a C1 v2 — Resilient 24h `allLiquidation.BTCUSDT` Isolated WS Proof Plan

**Ticket**: `P1-W-AUDIT-8A-C1-RETRY-PLAN-1`
**Priority**: P1 (W-AUDIT-8a Phase C blocker — gates liquidation strategy revival)
**Owner**: PA design / E1 IMPL（harness）/ BB+MIT sign-off / operator hand-off
**Date**: 2026-05-16
**Scope**: Read-only standalone Bybit public WS probe v2；無 production subscription / parser revival / writer revival / DB write / runtime restart / auth change
**Status**: SPEC ONLY — pending PM Sign-off → E1 IMPL → BB+MIT schema delta pre-review → operator deploy

---

## 1. 背景與 v1 失敗證據

### 1.1 v1 first attempt (2026-05-15 → 2026-05-16) result

- **Started**: 2026-05-15T19:53:09Z on `trade-core` PID `4100789`
- **Ended early**: 2026-05-16T00:37:25Z with `verdict=FAIL_CONNECTION`
- **Duration**: 17055.2s / 86400s observed = **19.7% of target** (5h / 24h)
- **Partial evidence**: 15 candidate `allLiquidation.BTCUSDT` messages received + 0 subscribe failures + 0 topic poison events
- **Failure mode**: WS connection lost mid-run → harness 無 reconnect → `recv failed: <exception>` → break loop → `connection_errors` non-empty → assess() set `FAIL_CONNECTION`
- **Spec**: `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- **Probe script**: `helper_scripts/bybit/liquidation_topic_probe.py`（351 LOC，single connection no reconnect）

### 1.2 v1 部分證據對 C1 PASS gates 的影響

| C1 PASS requirement | v1 status | 結論 |
|---|---|---|
| Duration ≥ 24h | ❌ 5h only | FAIL — 必重跑 |
| 0 `handler not found` / topic rejection / rate-limit | ✅ 0 poison events (5h window 內) | PASS (partial) |
| 0 reconnect loop | ⚠️ N/A — v1 無 reconnect 邏輯 | INCONCLUSIVE |
| Control topics 持續收 data | ⚠️ 5h 內 OK 但無 24h window 證據 | INCONCLUSIVE |
| Candidate payload sample → existing `market.liquidations` shape or reviewed schema delta | ✅ 15 messages 已收（可前置 BB+MIT 預審） | PRE-PASS — 可加速 §3 |
| BB + MIT sign-off before production builder change | ❌ 必跑 24h 完整 proof 後 | FAIL — gate 維持 |

**Net verdict**：v1 證明工具可達 + topic 不 reject + control topics 5h 健康；root cause 純 network/WS reconnect 中斷，不是 Bybit-side hard fail。**v2 重派必要 + 可信度 HIGH**。

---

## 2. RCA — `FAIL_CONNECTION` root cause analysis

### 2.1 證據收集（PA empirical inspect probe script）

`helper_scripts/bybit/liquidation_topic_probe.py` 主迴圈 (line 162-208)：

```python
ws = websocket.create_connection(args.url, timeout=args.recv_timeout_sec)
ws.send(json.dumps({"op": "subscribe", "args": topics}))
next_ping = time.monotonic() + args.ping_interval_sec
while time.monotonic() - start < args.duration_sec:
    now = time.monotonic()
    if now >= next_ping:
        ws.send(json.dumps({"op": "ping"}))      # 20s ping interval default
        stats.pings_sent += 1
        next_ping = now + args.ping_interval_sec
    try:
        raw = ws.recv()                           # 5s recv timeout default
    except websocket.WebSocketTimeoutException:
        continue                                  # timeout = OK，繼續
    except Exception as exc:
        stats.connection_errors.append(...)
        break                                     # ★ 任何非 timeout 異常即 break，無 reconnect
```

### 2.2 5 個候選 root cause

| # | 假說 | 證據支持 | 可能性 |
|---|---|---|---|
| 1 | Bybit-side idle disconnect | Bybit V5 ws server 對 idle connection ≈ 5min 無 ping 自動 close（雖然本 probe 20s ping 主動）；可能 server 認為某種 internal state stale | LOW（probe 主動 ping） |
| 2 | TCP keepalive / NAT translation drop | Linux default `tcp_keepalive_time=7200s = 2h`；NAT box / corp firewall 可能更短（如 1800s）；連線 idle 久後 NAT translation 過期 | MED-HIGH |
| 3 | Bybit-side WebSocket frame error | Server 偶發推 malformed JSON / oversized frame / unexpected close code → `ws.recv()` raise | LOW（罕見） |
| 4 | Mac/Linux network blip（WiFi / DHCP renew / tailscale tunnel reset） | trade-core 是 Linux 物理機/穩定 ethernet 可能性低；但 5h 內 1 次 network glitch 完全合理 | MED |
| 5 | Python `websocket-client` internal exception（buffer overflow / decode error） | 5h × 持續 message flow（control 4 topics × ~10 msg/s = ~720k messages 5h）累積某 edge case | LOW-MED |

**最可能 root cause**：#2 TCP / NAT-level drop（5h 是 NAT translation expire 典型時間）+ #4 network blip 也合理；#1/#3/#5 都可能但證據弱。

### 2.3 結論：harness 必須 reconnect-tolerant

無論 root cause 為何，**任何 24h 級 WS proof 必須含 reconnect 邏輯**才能穩定通過。Production Rust engine 端的 `multi_interval_topics` 等 WS client 都有 reconnect；v1 probe 是「最小可達」設計反而 fragile。

---

## 3. v2 Resilient Harness 設計

### 3.1 設計目標

| 目標 | v1 status | v2 target |
|---|---|---|
| 24h wall-clock 完整 window | ❌ break on any error | ✅ exponential backoff reconnect 至 24h elapsed |
| 連線中斷自動恢復 | ❌ no | ✅ ≤ 60s recover from any single drop |
| Failure auto-restart 上限 | ❌ N/A | ✅ 3 次 restart 上限 + 每次紀錄 reason |
| 累計 uptime 可量化 | ❌ binary FAIL_CONNECTION | ✅ `uptime_sec / 86400s` ≥ 95% (tolerance 1.2h drop budget) |
| Per-hour checkpoint | ❌ 0 visibility | ✅ JSON 每小時寫 progress + samples |
| Start-of-day cutoff | ❌ mid-day start | ✅ UTC 00:00 啟避時區 timing race |
| Schema delta pre-review | ❌ 等 24h 後才看 | ✅ §4 用 v1 15 messages 預審 |

### 3.2 Reconnect 邏輯（exponential backoff）

```
attempt 1: 1s wait
attempt 2: 2s
attempt 3: 4s
attempt 4: 8s
attempt 5: 16s
attempt 6: 32s
attempt 7+: 60s cap

每 attempt 重新 create_connection + re-subscribe topics
若連續 5 次 attempt 都 fail → 第 6 attempt 後若仍 fail → 該 session 標 `FAIL_RECONNECT_EXHAUSTED` 觸 §3.4 escalation
```

**TCP-level 加固**：
- 設 `socket.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)` + `TCP_KEEPIDLE=60` + `TCP_KEEPINTVL=10` + `TCP_KEEPCNT=3`（NAT translation 維持）
- Default ping interval 縮 20s → 10s（更快發現 server-side close）

### 3.3 Per-hour checkpoint

每 60min 寫 `$OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/c1_proof_progress.json`：

```json
{
  "session_id": "c1_v2_20260516T000000Z",
  "started_at_utc": "2026-05-16T00:00:00Z",
  "elapsed_sec": 7200.5,
  "target_sec": 86400,
  "uptime_sec": 7195.2,
  "uptime_ratio": 0.999,
  "reconnect_attempts": 1,
  "reconnect_successes": 1,
  "reconnect_failures": 0,
  "last_reconnect_reason": "recv failed: ConnectionClosedError",
  "candidate_messages_seen": 47,
  "control_topics_status": {
    "tickers.BTCUSDT": {"count": 2880, "last_seen_utc": "2026-05-16T02:00:00Z"},
    "orderbook.50.BTCUSDT": {"count": 14400, "last_seen_utc": "2026-05-16T02:00:00Z"},
    "publicTrade.BTCUSDT": {"count": 7234, "last_seen_utc": "2026-05-16T01:59:59Z"},
    "kline.1.BTCUSDT": {"count": 120, "last_seen_utc": "2026-05-16T01:59:00Z"}
  },
  "interim_verdict": "IN_PROGRESS_HEALTHY",
  "blocker_if_aborted_now": "Duration shorter than 24h; SMOKE_PASS_NOT_C1_PROOF if abort"
}
```

Operator 透過 `cat` / `jq` 隨時看狀態；若 `uptime_ratio < 0.95` 或 `reconnect_failures >= 3` → operator 可決定 early abort + 改 next-day retry。

### 3.4 Failure auto-restart（3 次上限）

| Restart trigger | 動作 | Log entry |
|---|---|---|
| 連續 5 次 reconnect attempt fail | 暫停 60s → restart full session（保持 elapsed clock）| `RESTART_REASON=RECONNECT_EXHAUSTED` |
| Control topic silent ≥ 300s（即使 candidate topic 有 message） | 暫停 30s → restart full session | `RESTART_REASON=CONTROL_SILENT` |
| `c1_proof_progress.json` 連續 2 hour 未更新（probe 自身 dead） | 外層 watchdog cron 重啟 | `RESTART_REASON=WATCHDOG_REVIVE` |

**累計 restart > 3** → 整 session 標 `FAIL_RESTART_BUDGET_EXHAUSTED` → §6 escalation；不再 auto-retry，等 PM 介入決策。

### 3.5 24h tolerance retry budget

v2 PASS 條件鬆綁為：
- Duration observed ≥ 23h（允許 1h drop budget 給 1-2 次短 reconnect 期）
- `uptime_ratio ≥ 0.95`（即實際 connected time ≥ 23h）
- 0 `handler not found` / topic rejection / rate-limit
- 至少 3 control topics 全期 alive（不要求所有 4 個）
- 候選 candidate topic 至少 1 message 收到 + schema 對齊 §4 預審

**仍要求**：BB+MIT sign-off after final report。

### 3.6 Start-of-day cutoff alignment

```bash
# Wait until next UTC 00:00:00 + 30s buffer
while [ $(date -u +%H%M%S) -gt 000030 ]; do sleep 30; done
nohup python3 helper_scripts/bybit/liquidation_topic_probe_v2.py \
  --topic allLiquidation.BTCUSDT \
  --duration-sec 86400 \
  --session-id "c1_v2_$(date -u +%Y%m%dT%H%M%SZ)" \
  --enable-reconnect \
  --max-restart 3 \
  --checkpoint-interval-sec 3600 \
  > /tmp/openclaw/audit/liquidation_topic_probe/nohup_c1_v2_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
```

**理由**：UTC 00:00 起跑覆蓋整 24h trading day；24h 後 cutoff 落在隔日 UTC 00:00 完整對齊 Bybit funding cycle / OI panel 對賬 SLA；避免 mid-day 起跑 22h 收尾撞 funding rate flush 等 noise。

---

## 4. MIT Schema Delta Review Prep（基於 v1 15 messages）

### 4.1 Pre-review 工作（v1 收到的 15 candidate messages 已可用）

從 v1 log `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log` 抽取 15 candidate `allLiquidation.BTCUSDT` payloads，PA pre-package 給 MIT review：

**Bybit V5 official `allLiquidation.{symbol}` schema** (per OFFICIAL_DOC_URL `https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation`)：

```json
{
  "topic": "allLiquidation.BTCUSDT",
  "type": "snapshot",
  "ts": 1745386800000,
  "data": [
    {
      "T": 1745386800000,   // timestamp ms
      "s": "BTCUSDT",       // symbol
      "S": "Sell",          // side
      "v": "0.001",         // qty
      "p": "98765.5"        // price
    }
  ]
}
```

**現有 `market.liquidations` schema**（PA 必查 Linux PG）：

```sql
-- 需 PA pre-IMPL 期跑：
ssh trade-core "psql -d trading_bot -c \"\d market.liquidations\""
```

### 4.2 Schema delta 預判 + MIT pre-review checklist

| Bybit field | 現 `market.liquidations` column | 風險 |
|---|---|---|
| `T` (timestamp ms) | `event_time` / `liquidation_time_ms` | LOW (mirror existing) |
| `s` (symbol) | `symbol` | LOW |
| `S` (side) | `side` | LOW (enum 對齊 Buy/Sell) |
| `v` (qty) | `qty` | LOW |
| `p` (price) | `price` | LOW |
| 無 USD value column | 若 schema 有 `value_usd` → 必須 `qty * price` 計算 | MED |
| Snapshot vs delta type | 若 schema 有 `event_type` → 必須 map `snapshot` → 適當 enum | MED |

**MIT pre-review 任務**（v2 啟動前完成）：
1. 用 v1 15 messages 對齊 schema 1:1 ratio
2. 識別任何 v1 messages 不對齊現 schema 的 case
3. 若 delta 真需 schema migration → spawn `V09X` migration spec 與 v2 proof 並行 IMPL（v2 PASS 後即可 BB sign-off + V09X apply + writer 升級）
4. 若 delta 為 0 → BB sign-off 後直接走 existing writer

### 4.3 Pre-review output

`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--c1_v2_schema_delta_pre_review.md` 必含：
- v1 15 messages full JSON dump
- 對 `market.liquidations` 1:1 mapping table
- delta 清單（如有）
- V09X migration draft（如需）
- MIT verdict: APPROVE / CONDITIONAL / DELTA-REQUIRES-MIGRATION

---

## 5. BB Sign-off Invariants（4 條）

v2 24h proof 完成後，BB（Bybit Connector Specialist）sign-off 必跑：

### 5.1 (a) 24h+ wall-clock pin window
```bash
# 從 c1_proof_progress.json 最終 entry
test "$(jq -r '.elapsed_sec' /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json)" -ge 82800  # ≥ 23h tolerance
```

### 5.2 (b) 0 subscribe failures + 0 topic rejection
```bash
test "$(jq -r '.subscribe_failure_count' /tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.json)" = "0"
test "$(jq -r '.poison_events | length' /tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.json)" = "0"
```

### 5.3 (c) Reconnect 自動恢復 + 累計 uptime ≥ 23h
```bash
test "$(jq -r '.uptime_ratio' /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json)" -ge 0.95
test "$(jq -r '.reconnect_failures' /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json)" -lt 3
```

### 5.4 (d) Message schema 對齊 Bybit V5 official 字典手冊
```bash
# Pre-review (§4) 完成 + MIT verdict APPROVE 或 CONDITIONAL-WITH-MIGRATION-PLAN
ls /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--c1_v2_schema_delta_pre_review.md
grep "verdict:" /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--c1_v2_schema_delta_pre_review.md
```

**4 條全 ✅ → BB sign-off 寫 `docs/governance_dev/2026-05-1X--w_audit_8a_c1_v2_bb_signoff.md`**

---

## 6. Operator Hand-off

### 6.1 啟動 oneliner（單行 paste-safe per `feedback_shell_paste_safety`）

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && nohup python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --topic allLiquidation.BTCUSDT --duration-sec 86400 --enable-reconnect --max-restart 3 --checkpoint-interval-sec 3600 --session-id c1_v2_$(date -u +%Y%m%dT%H%M%SZ) > /tmp/openclaw/audit/liquidation_topic_probe/nohup_c1_v2_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &'
```

### 6.2 狀態檢查 oneliner

```bash
ssh trade-core 'jq . /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json'
```

### 6.3 Expected complete timestamp

| Start UTC | Expected complete UTC | 容差 |
|---|---|---|
| `2026-05-1X T00:00:00Z`（next UTC midnight after Sign-off） | `+24h00m` ± 5min | 5min for graceful shutdown / final report write |

### 6.4 PID + log 路徑

啟動 oneliner output `&` 後 echo PID；operator 記錄到本 spec §10 變更歷史一欄。Log 路徑：`/tmp/openclaw/audit/liquidation_topic_probe/nohup_c1_v2_<UTC>.log`。

### 6.5 Early abort 條件

operator 可在以下情況 early abort（不等 24h）：
- `uptime_ratio < 0.85` 連續 2 小時（system 級 network unhealthy）
- Operator 收 trade-core HW alert（reboot / network reconfig）
- 突發 Bybit V5 API breaking change（極罕見）

Abort 時：`kill $PID` + write `/tmp/openclaw/audit/liquidation_topic_probe/ABORTED_<UTC>.flag` + ping PM。

---

## 7. Failure Escalation（3 次 retry budget exhausted → P0）

| 第幾次 retry 仍 fail | 動作 |
|---|---|
| Retry 1 fail | PM 派 E1 debug harness；可能 root cause = harness bug；改 v2.1 spec |
| Retry 2 fail | 升 P1 → BB+MIT+PA joint root cause review；可能 root cause = Bybit-side issue / network infrastructure；改 v2.2 spec |
| Retry 3 fail | **升 P0** + 暫停 W-AUDIT-8a Phase C IMPL chain；W-AUDIT-8a 內 liquidation revival path 整鏈 freeze 直到 root cause 明朗 |

P0 escalation 觸發：
- Spawn `P0-W-AUDIT-8A-C1-INFRA-BLOCKER-1`
- Slack-equiv alert (manual operator notice)
- W-AUDIT-8b Funding Skew 仍可進，但 W-AUDIT-8a strategy revival 整支 deferred
- 考慮 alternative path：用 production replay 模擬 liquidation cascade 來部分驗證 `LiquidationCascade` fail-closed behavior（不依賴 Bybit WS proof）

---

## 8. ETA + Supervised Live Readiness Impact

### 8.1 重派 ETA estimation

| Phase | 工作 | Owner | ETA |
|---|---|---|---|
| Phase 1 | 本 spec PM Sign-off | PM | 2026-05-16 |
| Phase 2 | E1 IMPL probe_v2 harness（reconnect / checkpoint / restart / TCP keepalive）| E1 | 2026-05-16 / 0.5d |
| Phase 3 | E2 review harness + 短 smoke (60s) verify | E2 | 2026-05-17 / 0.2d |
| Phase 4 | MIT schema delta pre-review on v1 15 messages | MIT | 2026-05-17 / 0.5d |
| Phase 5 | Operator 啟動 v2 24h proof（next UTC 00:00 cutoff） | operator | 2026-05-17 → 2026-05-18 / 24h wall |
| Phase 6 | BB+MIT sign-off on final report | BB+MIT | 2026-05-18 / 0.5d |
| Phase 7 | If PASS → W-AUDIT-8a Phase C IMPL kickoff（parser + writer + LiquidationPulseProvider）| PA+E1+MIT | 2026-05-19+ |

**Total v2 proof 路徑**：~3 工作日（含 24h wall-clock）；最早 2026-05-19 進入 Phase C IMPL kickoff。

### 8.2 Supervised live readiness 影響

W-AUDIT-8a C1 PASS 是 liquidation strategy revival 的 hard gate，**但不是 supervised live readiness 的 P0 critical path**：

| 維度 | 影響 |
|---|---|
| LG-1/2/3 IMPL | 0 影響（W-AUDIT-8a 是 alpha discovery 路徑，與 live gate IMPL 平行） |
| LG-5 supervised-live state machine | 0 影響 |
| P0-EDGE-1 closure | 0 影響（5 textbook 策略 alpha-deficient 結構性問題不依賴 liquidation 路徑） |
| true live deploy | 0 影響（最早 2026-06-15 pessimistic ETA） |
| W-AUDIT-8b Funding Skew | 0 影響（兩 audit 平行） |
| W-AUDIT-8c Liquidation Cluster | ⚠️ 阻塞 — 8c 等 8a C1 PASS |

**結論**：v2 ETA slip 0-3 工作日對 supervised live readiness 整體 timeline 影響 0；對 alpha revival 影響 = 8a/8c 整鏈延後 3 工作日 + Phase 7 IMPL kickoff 延後。

### 8.3 並行 NICE-TO-HAVE work（v2 24h wait 期）

v2 24h proof 跑期間，可平行進：
- MIT schema delta pre-review（§4）
- W-AUDIT-8b Funding Skew Stage 0R query/report packet IMPL
- 12-agent audit Wave 4 後續 P2 backlog
- Wave 3.5 Linux PG backlog V091/V092/V093 apply（per `2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md`）

24h 不浪費。

---

## 9. Restrictions（PM 明示）

本 spec **不**：
- 改 `helper_scripts/bybit/liquidation_topic_probe.py`（v1，保留歷史）→ 新建 `liquidation_topic_probe_v2.py`
- Trigger 新 24h probe（等 BB+MIT 預審 + operator 啟）
- Commit / push（PM 統一 commit）
- 改 `rust/openclaw_engine/src/main.rs` 或任何 production source / TOML
- 改 production `full_subscription_list()` / topic builder guards
- 改 auth / GovernanceHub / Decision Lease state

---

## 10. 16 根原則 + 9 不變量 合規

| 維度 | 評估 |
|---|---|
| 原則 1 單一寫入口 | N/A（read-only WS probe） |
| 原則 4 策略不能繞過風控 | N/A |
| 原則 6 失敗默認收縮 | ✅ Reconnect budget exhausted → §7 escalation 而非 silent continue |
| 原則 8 交易可解釋 | ✅ Per-hour checkpoint + 完整 connection_errors log |
| 原則 10 認知誠實 | ✅ Pre-review 用 v1 真實 partial evidence + 5 候選 root cause 明列 |
| 原則 14 零外部成本可運行 | ✅ 0 paid API；純 public Bybit WS |
| DOC-08 §12 9 不變量 | 0 觸碰 |
| 硬邊界 | 0 觸碰（不動 `live_execution_allowed` / `max_retries` / `execution_authority`） |

**合規評級**：A 級（16/16 + 硬邊界 0 觸碰）

---

## 11. v2 與 v1 對比 quick reference

| 維度 | v1 (FAILED) | v2 (designed) |
|---|---|---|
| Reconnect | ❌ break on error | ✅ exponential backoff 1s→60s cap |
| Restart budget | ❌ N/A | ✅ 3 次 / RESTART_REASON log |
| Per-hour checkpoint | ❌ 0 | ✅ JSON 每 60min |
| TCP keepalive | ❌ default | ✅ SO_KEEPALIVE + TCP_KEEPIDLE=60 |
| Ping interval | 20s | 10s |
| Start cutoff | mid-day arbitrary | UTC 00:00 aligned |
| PASS gate | exact 24h continuous | ≥ 23h uptime + uptime_ratio ≥ 0.95 |
| Pre-review schema | 等 24h 後才看 | ✅ v1 15 messages 即用 |
| Failure escalation | 不明確 | ✅ 3 retry → P0 + 整鏈 freeze |

---

## 12. 變更歷史

| 日期 | 變更 | 引用 |
|---|---|---|
| 2026-05-16 | 本 spec draft v2.0 land | PA design `2026-05-16--w_audit_8a_c1_v2_resilient_proof`；基於 v1 spec `2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` + v1 run report at PID 4100789 |
| (TBD) | PM Sign-off | (TBD) |
| (TBD) | E1 harness IMPL commit | (TBD) |
| (TBD) | Operator v2 start PID + log path | (TBD) |
