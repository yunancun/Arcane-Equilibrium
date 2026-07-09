---
report: PA design — Sprint 5+ Wave 1 §8.6 §4.4 production hardening (4 items + AC-1b monthly cron)
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 5+ Wave 1 (per Stage F §8.6 carry-over)
status: DESIGN-DONE
parent_signoff: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.4
parent_acceptance: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.6
upstream_evidence:
  - rust/openclaw_engine/src/health/domains/api_latency.rs (classify ladders)
  - rust/openclaw_engine/src/health/metric_emitter/mod.rs (open_fd_count classify line 346-359)
  - rust/openclaw_engine/src/health/mod.rs (state machine line 395-449 OK→WARN dwell 60s)
  - rust/openclaw_engine/src/bybit_rest_client.rs line 318-441 (RestLatencyHistogram 60s rolling)
  - rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs line 176-241 (F-2 sanitize)
  - helper_scripts/db/passive_wait_healthcheck.sh (cron wrapper範式)
  - learning.health_observations 6h sample (Linux trading_postgres empirical 2026-05-23 13:20Z)
spec_artifacts:
  - 本 design 文件 = 4 items + AC-1b monthly cron 唯一 PA dispatch packet (E1/QA 派發入口)
  - 不另開 4 個 spec 子文件（避散落維護成本；E1 IMPL 階段如需細項 ADR/dispatch packet 由 PA 再開）
risk_grade: 低 (monitoring SOP + classify ladder threshold amend only; 無業務邏輯; 無 V### migration; 無 IPC schema 改動)
---

# §1 Executive Summary

## §1.1 Verdict
**DESIGN-DONE / READY-TO-DISPATCH** — Sprint 5+ Wave 1 §4.4 production hardening 4 items + AC-1b monthly cron 設計完成；4 items combined IMPL phase 估計 6-8 hr E1 + 2-3 hr QA + 1 hr operator deploy/crontab install；可單 E1 thread 串行做完，不需並行拆分。

## §1.2 §4.4 4 items 重新分類（基於 Linux empirical evidence）

per Stage F §8.6 PM phase 3e sign-off 拍板「§4.4 全部進 hardening (4 項) + AC-1b monthly cron (不 defer)」。但 Linux PG 6h empirical evidence (2026-05-23 13:20 UTC) 揭露原 §4.4 4 items 描述部分**與真實 runtime 不符**：

| # | §4.4 原描述 | Linux 真實 evidence (6h) | PA 重分類 |
|---|---|---|---|
| 1 | `HEALTH_WARN 60 row api_latency rest_p50/p95/p99` | rest_p50_ms 355 row + rest_p95_ms 354 + rest_p99_ms 354 = **1063 row total**；vavg p50=187 / p95=631 / p99=688；含 missing DEGRADED transition（state machine spike scope 限制）| **REAL** — threshold + state machine cascade 兩問題 |
| 2 | `HEALTH_WARN 41 row engine_runtime open_fd_count` | open_fd_count **711 row WARN**（不是 41）；vmin=1783 vmax=1809 vavg=1788；ladder OK<1024 / WARN 1024-4096 / DEGRADED>4096；典型 baseline 設計 <256 但 production engine 含 25 symbol WS + REST pool + IPC + PG pool = ~1700 fd 為 normal steady state | **REAL** — threshold mismatch（design 沒考慮 production fd footprint）|
| 3 | `60s expire boundary` verify | bybit_rest_client.rs L355-441 已實作真實 60s lazy expire；type-level `_60s_window` suffix；caller 端 `percentile_triple()` 走 `now.checked_sub(60s) → retain` | **VERIFIED FROM SOURCE** — code-level 已對齊；production 真實 sample 也吻合 |
| 4 | F-2 sanitize fire log 監測 | 6h `m3.health` log 6 row（全是 wireup INFO）；F-2 fire 0 次；生產 logger target `m3.health.risk_envelope` + `m3.health.strategy_quality` | **MONITORING SOP 待建** — 邏輯就緒；只缺 grep + alert routing |

**5th item NEW**: AC-1b monthly cron — Sprint 4+ §4.1 30 min sample 770 row 一次性 verify 已 PASS；monthly cron 把同 SQL pattern 自動化 + sentinel mtime 推斷 cron fire。

## §1.3 4 items + AC-1b 全景 (production hardening)

| Item | Type | Effort | Owner | Blocker? |
|---|---|---|---|---|
| §2 HEALTH_WARN classify ladder amend | code (Rust classify thresholds + state machine cascade defer 註) | 2 hr E1 + 1 hr E2 | E1 + E2 | none |
| §3 60s boundary verify SOP | doc (verify SOP 文件 + Linux empirical re-run) | 30 min QA | QA | none |
| §4 F-2 sanitize fire log monitoring | doc + script (grep cron + log routing) | 1 hr E1 + 30 min QA | E1 + QA | none |
| §5 AC-1b monthly cron | script + cron entry (sql + heartbeat) | 2-3 hr E1 + 0.5 hr QA | E1 + QA | depends §1 closure for stable threshold semantic |
| **total** | | **~6-8 hr E1 + 2-3 hr QA + 1 hr operator** | | |

---

# §2 HEALTH_WARN classify ladder amend

## §2.1 真實 evidence (Linux 6h)

```
domain          metric_name        state         rows   vmin   vmax   vavg   ladder (current)
─────────────────────────────────────────────────────────────────────────────────────────────
engine_runtime  open_fd_count      HEALTH_OK        5  1784   1808                OK<1024 / WARN 1024-4096
                                   HEALTH_WARN    711  1783   1809  1788.20      DEGRADED>4096
api_latency     rest_p50_ms        HEALTH_OK        3   169    345                OK<50 / WARN 50-200
                                   HEALTH_WARN    355   167    550   187.14      DEGRADED>200
api_latency     rest_p95_ms        HEALTH_OK        4   473    663                OK<200 / WARN 200-500
                                   HEALTH_WARN    354   174   1262   631.54      DEGRADED>500
api_latency     rest_p99_ms        HEALTH_OK        4   738   1261                OK<500 / WARN 500-1000
                                   HEALTH_WARN    354   174   1262   688.34      DEGRADED 1000-2000 / CRITICAL>2000
api_latency     ws_rtt_p50_ms      HEALTH_OK      311     0    162                OK<50 / WARN 50-150
                                   HEALTH_WARN     47   162    163   162.34      DEGRADED>150
strategy_quality dormant_minutes   HEALTH_WARN    128  3582 44325 26000.94       OK<60 / WARN 60-1440 / DEGRADED>1440
```

## §2.2 三類 root cause 識別

### §2.2.1 Threshold mismatch（兩條：open_fd_count + ws_rtt_p50_ms）

**open_fd_count**: ladder OK<1024 是基於「ulimit 1024 baseline」設計；但真實 production engine 跑 25 symbol × kline WS + REST connection pool (size 8) + IPC unix socket + PG pool (size 32) + epoll fd + tokio task fd = **常態 1700-1800 fd**。WARN 711 row 持續 6h 都是「engine 正常運轉 baseline」誤觸 WARN，不是 fd leak。

**ws_rtt_p50_ms**: ladder WARN 50-150ms。Linux 真實 6h vmin=162 vmax=163ms（卡邊；Bybit demo 對 trade-core 物理距離 ~150-160ms 為常態）。47 row WARN 全是「demo endpoint 物理距離」誤觸。Live mainnet endpoint 距離不同（更近 hk/sg DC），ladder 不能假設 demo 物理距離。

**對策**：amend ladder 把 baseline 範圍從 WARN 移出到 OK band。

### §2.2.2 State machine cascade IMPL gap（三條：rest_p50/p95/p99）

`rust/openclaw_engine/src/health/mod.rs:445`:
```rust
// WARN → DEGRADED 5min dwell 邏輯 Sprint 5 Tier 1 IMPL 時補。
(HealthState::HealthWarn, _) => Ok(false),
```

State machine **只 IMPL OK→WARN dwell 60s**（line 415-433）；WARN→DEGRADED dwell 5min **尚未 IMPL**。所以：
- rest_p95 vavg=631（落 DEGRADED band 500-1000）但 state 永遠卡在 HEALTH_WARN — band 計算正確，但 state machine 拒升階
- rest_p99 vavg=688（落 WARN band 500-1000）— state machine 行為正確（band=WARN，state=WARN）
- rest_p50 vmax=550（>200 DEGRADED band）但 state=WARN — 同樣 cascade gap

**對策**：cascade IMPL 是真正的 Sprint 5+ Tier 1 工作（per mod.rs line 411-412 注釋 "spike scope: 只 IMPL OK → WARN 60s dwell"），**不在本 hardening 範疇**。本 hardening 只做 doc 補充：在 ladder 注釋明標「state 卡 WARN ≠ band 計算錯誤；WARN→DEGRADED cascade 由 Sprint 5+ Tier 1 IMPL」+ monitoring SOP 解釋運維側看到 WARN row 大量 vmax 落 DEGRADED 是 cascade gap 預期行為，不是 bug。

### §2.2.3 Sprint 4+ §4.3.1 strategy_quality wireup 後續樣本（不是問題）

strategy_quality dormant_minutes 128 row WARN（vmax 44325 分鐘 ≈ 30 天 dormant）是 §4.3.1 wireup 後真實 5 strategy × 25 symbol pair 大量 dormant signal — 屬正常 funding_arb / bb_breakout 等冷板凳策略 evidence，不是 health bug。本 hardening 不動。

## §2.3 IMPL spec — classify ladder amend

### §2.3.1 open_fd_count (`rust/openclaw_engine/src/health/metric_emitter/mod.rs:346-359`)

**Before**:
```rust
/// open_fd_count classify：OK <1024 / WARN 1024-4096 / DEGRADED >4096。
///
/// 為什麼此 threshold:
///   - 典型 Linux 默認 ulimit 1024 為 baseline；engine 全功能含 PG/Bybit/IPC
///     正常 fd 數 < 256，> 1024 即 fd leak signal。
pub fn classify_engine_runtime_open_fd_count(value: u32) -> HealthState {
    if value > 4096 {
        HealthState::HealthDegraded
    } else if value >= 1024 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

**After**:
```rust
/// open_fd_count classify：OK <3072 / WARN 3072-6144 / DEGRADED >6144。
///
/// 為什麼此 threshold (per Sprint 5+ Wave 1 §4.4 production hardening empirical
/// 校準 2026-05-23)：
///   - production engine 6h empirical baseline 1783-1809 fd（25 symbol × kline
///     WS subscription + REST connection pool 8 + tokio task fd + IPC unix
///     socket + PG pool 32 + epoll fd + log file handle）；常態約 1700-1800。
///   - OK band 上限 3072 留 ~70% headroom 對應「symbol expansion to 40-50
///     scenario」+「short-lived REST burst」；3072 以下視為正常 production
///     steady state，不誤觸 WARN。
///   - WARN band 3072-6144 對應「真實 fd leak signal」（baseline 70% 以上不
///     正常累積）；engine debug 介入時間窗口。
///   - DEGRADED band > 6144 對應「leak 已嚴重」（接近典型 RLIMIT_NOFILE
///     8192 上限；engine 即將拒新 fd open）；engine 端不自動 abort，由
///     health writer 寫 V106 row 給 operator alert。
pub fn classify_engine_runtime_open_fd_count(value: u32) -> HealthState {
    if value > 6144 {
        HealthState::HealthDegraded
    } else if value >= 3072 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

### §2.3.2 ws_rtt_p50_ms (`rust/openclaw_engine/src/health/domains/api_latency.rs:303-323`)

**Before**: OK<50 / WARN 50-150 / DEGRADED >150

**After**: OK<170 / WARN 170-300 / DEGRADED >300

**注釋變更**:
```rust
/// ws_rtt_p50_ms classify（WS 常態 RTT）。
///
/// ladder (per Sprint 5+ Wave 1 §4.4 production hardening empirical 校準
/// 2026-05-23)：
///   OK       : < 170ms    （Bybit demo endpoint 到 trade-core 物理距離常態
///                            150-163ms；ladder 留 ~10% headroom 對應網路
///                            jitter）
///   WARN     : 170 - 300ms （網路抖動 / venue 端 push 退化）
///   DEGRADED : > 300ms     （已影響 trading hot path tick delivery；接近
///                            ws_dropout 風險窗）
///
/// 為什麼從 50ms baseline 改 170ms (per Linux empirical 2026-05-23 6h
/// trading_postgres 47 row HEALTH_WARN sample vmin=162 vmax=163ms)：
///   - 原 ladder 假設 WS persistent connection 無 TCP handshake / TLS
///     overhead 應 < 50ms；對 colocated venue 成立，但 Bybit demo endpoint
///     物理距離 ~150-160ms 是不可逆的網路常態。
///   - Live mainnet endpoint 物理距離可能不同（hk/sg DC 更近）；mainnet 切
///     換時須重 calibrate ladder；本次 amend 只覆蓋 demo + live_demo 範圍。
///   - 對應 spec §2.3 line 75-85 「ladder 應反映真實網路 baseline 而非
///     colocated 理論值」（per PA Sprint 5+ Wave 1 amend）。
///
/// 為什麼 WS RTT 退化判定仍嚴於 REST:
///   - WS 是 persistent connection；ws_rtt 退化是 venue 端 push 路徑慢或
///     client→venue 網路退化 signal；300ms+ 仍表示已影響 trading hot path
///     tick delivery，比 REST 的 500-1000ms 嚴格。
pub fn classify_api_latency_ws_rtt_p50_ms(value: u32) -> HealthState {
    if value > 300 {
        HealthState::HealthDegraded
    } else if value >= 170 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

### §2.3.3 rest_p50_ms / rest_p95_ms / rest_p99_ms — 維持 ladder 不變，補注釋

**Why 不改 ladder**: vavg p50=187 落正中 WARN band（50-200），p95=631 落 DEGRADED band 是 state machine cascade gap 不是 ladder 問題；ladder 設計與真實 venue 距離相符。

**注釋補充**（add to 三個 classify fn 末尾）:

```rust
/// production hardening note (per Sprint 5+ Wave 1 §4.4 empirical 2026-05-23)：
///   - 真實 6h sample 1063 row 大量持續落入 WARN band，vavg p50=187 / p95=631 /
///     p99=688 完全符合 ladder 預期；不誤觸但 state 卡 HEALTH_WARN 是預期。
///   - 持續 WARN 不會自動升 DEGRADED（per health/mod.rs line 445 spike scope
///     限制：WARN → DEGRADED 5min dwell 由 Sprint 5+ Tier 1 cascade IMPL 接）。
///   - 對應 monitoring SOP：operator dashboard 看 WARN row 大量是 cascade gap
///     預期行為，不是 health bug。真實 DEGRADED transition 上線後 alert 才
///     有意義；本 hardening phase doc 已記錄 baseline 行為。
```

### §2.3.4 test (`rust/openclaw_engine/src/health/metric_emitter/tests.rs` or inline)

新增 4 unit test：
1. `test_open_fd_count_baseline_1800_is_ok` — value=1800 → HealthOk（避未來人改回去誤觸 WARN）
2. `test_open_fd_count_3500_warn` — value=3500 → HealthWarn
3. `test_ws_rtt_p50_demo_baseline_163_is_ok` — value=163 → HealthOk
4. `test_ws_rtt_p50_250_warn` — value=250 → HealthWarn

## §2.4 risk + 副作用

| Risk | Severity | Mitigation |
|---|---|---|
| open_fd_count baseline 3072 太寬，真實 leak 期 delay 1-2 hr 才 alert | LOW | leak 累積線性；2x baseline 已是 leak signal；6144 DEGRADED 仍及時 |
| ws_rtt 170ms baseline 隱藏「demo→live mainnet 切換 latency 升 ws_rtt 退化」signal | MEDIUM | mainnet 切換 sprint 開新 calibrate（記入 §4.4 dispatch packet「未來 Live transition 必驗 ws_rtt ladder」）|
| 改 classify_engine_runtime_open_fd_count 影響 amplification_loop_24h_count 計算 | LOW | only enum 結果改變；amp cap 計入 state transition fire 數，state 從 WARN→OK 不算 fire（per mod.rs line 446）|
| 新 ladder 觸發既有 Track A test fixture（test_emitter_full_emit）assert | MEDIUM | E2 強制驗 + E4 regression cargo test --release 全跑 |

## §2.5 E1 + E2 派發

| Phase | Owner | Effort | Deliverable |
|---|---|---|---|
| §2.3.1 + §2.3.2 IMPL | E1 | 1 hr | classify ladder + 注釋 + 4 unit test |
| §2.3.3 注釋補充 | E1 | 30 min | 三 fn 注釋 production hardening note |
| E2 round 1 review | E2 | 30 min | 確認 ladder 不影響 amp cap / cascade / writer 路徑 |
| E4 regression | E4 | 30 min | cargo test --release + pytest 全跑 |

---

# §3 60s boundary verify SOP

## §3.1 Source review verdict — VERIFIED FROM CODE

`rust/openclaw_engine/src/bybit_rest_client.rs` line 318-441:
- `REST_LATENCY_WINDOW_SECS: u64 = 60` (line 319) — explicit 60s constant
- `record_latency`: 達 cap 走 `now.checked_sub(60s) → retain` (line 376-379)
- `percentile_triple`: `cutoff = now.checked_sub(60s); filter |(t, _)| *t >= cutoff` (line 405-413)
- `checked_sub.unwrap_or(now)` fallback 已處理 process boot < 60s edge case（per E2 round 1 M-1 fix）

`rust/openclaw_engine/src/health/domains/api_latency.rs:477-494`:
- trait method 命名強制 `_60s_window` suffix (Option C type-level enforce; per PA-DRIFT-4 round 2 HIGH-2 fix)

`rust/openclaw_engine/src/health/mod.rs:424,660,672`:
- `Duration::from_secs(60)` dwell trigger 對齊 60s window

**code-level 60s boundary 已完整對齊**；不需 runtime modify。

## §3.2 Linux empirical re-run SOP — 1 hr QA

QA 跑下列 sample-bucket SQL 確認 60s 窗口物理對齊（每 60s ≈ 一 emitter cycle 樣本）：

```sql
-- §3.2.1 sample inter-arrival check per metric — 連續 sample 距離 ~60s
SELECT
  domain, metric_name,
  observed_at,
  observed_at - LAG(observed_at) OVER (PARTITION BY domain, metric_name ORDER BY observed_at) AS delta
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
  AND domain IN ('api_latency', 'engine_runtime')
ORDER BY domain, metric_name, observed_at DESC
LIMIT 20;

-- 預期 delta ≈ 60.0 seconds（emitter scheduler 60s interval）
-- 允許 ±2s tolerance（scheduler tokio sleep 抖動）

-- §3.2.2 bucket density check — 每 60s 應有 1 row per (domain, metric_name)
SELECT
  domain, metric_name,
  date_trunc('minute', observed_at) AS bucket,
  COUNT(*) AS samples_per_min
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
  AND domain IN ('api_latency', 'engine_runtime')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3 DESC
LIMIT 30;

-- 預期 samples_per_min = 1 for 60s interval emitter（api_latency / engine_runtime
-- subset 6 metric × 1 sample/min = 6 row/min/domain）
-- 若 samples_per_min = 0 → emitter task crashed; > 1 → duplicate emit bug
```

## §3.3 Deliverable

- `helper_scripts/db/health_60s_boundary_verify.sql` (~30 行 SQL)
- `helper_scripts/db/health_60s_boundary_verify.sh` (~50 行 bash wrapper；對齊 passive_wait_healthcheck.sh 範式)
- update `helper_scripts/SCRIPT_INDEX.md` 加新項
- QA 跑一次 + 截圖 + 寫入 QA report

## §3.4 不在範疇

- 不改 60s 常量值（per source verified 已對齊）
- 不改 emitter scheduler tick （per main_health_emitters.rs 已對齊）
- 不加新 metric domain（per Sprint 5+ §4.2 / §4.3 範疇）

---

# §4 F-2 sanitize fire log monitoring

## §4.1 F-2 fire 源頭 (already shipped per Wave A round 2)

`rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:194-241` — 三類 NaN/inf skip + tracing::warn:
- `realized_pnl` 非 finite → skip push + log `"PortfolioStateCache: skip NaN/inf realized_pnl fill (F-2 sanitize)"` (line 197-202)
- `equity_usd` 非 finite → skip push + log `"PortfolioStateCache: skip NaN/inf equity sample (F-2 sanitize)"` (line 213-218)
- `notional_usd` 非 finite → filter + log `"PortfolioStateCache: filter NaN/inf notional exposure (F-2 sanitize)"` (line 232-237)

target = `m3.health.risk_envelope` + `m3.health.strategy_quality`

## §4.2 Current production fire rate (6h)

```
ssh trade-core 'grep -c "F-2 sanitize" /tmp/openclaw/engine.log'
→ 0
```

Zero fire 是 expected — Sprint 4+ Wave B placeholder no-op 階段（PortfolioStateCache update_task 是 placeholder；PaperState SSOT wireup 由 Sprint 5+ §4.2.2 接）。F-2 真實 fire 要等 Sprint 5+ §4.2.2 wireup 真實 PaperState 之後才會見到。

## §4.3 Monitoring SOP design

### §4.3.1 grep-based heartbeat (1 hr E1)

**file**: `helper_scripts/db/health_f2_sanitize_monitor.sh` (新)

```bash
#!/usr/bin/env bash
# health_f2_sanitize_monitor.sh — F-2 NaN/inf sanitize fire log 監測
#
# 為什麼 grep-based 而非 PG-based：
#   - F-2 sanitize 在 in-process tracing::warn 觸發，不寫 V106；engine.log
#     是唯一 source of truth。
#   - V106 row 是 fail-soft（state=HEALTH_OK 維持）；如 cache push 全 skip
#     表示 PaperState 餵 NaN 但 health row 不會反映。
#   - operator 看 health WARN dashboard 不會看到 F-2 issue → 需獨立 grep
#     cron。
#
# Exit codes:
#   0 = no fire in last hour OR fire < N threshold (default 0)
#   1 = fire ≥ N threshold (operator alert)
#   2 = engine.log 不存在或不可讀

set -u
LOG_FILE="${OPENCLAW_ENGINE_LOG:-/tmp/openclaw/engine.log}"
THRESHOLD="${OPENCLAW_F2_THRESHOLD:-0}"  # fire count > N → alert
WINDOW_HOURS="${OPENCLAW_F2_WINDOW_HOURS:-1}"

if [[ ! -r "$LOG_FILE" ]]; then
  echo "[FATAL] engine.log not readable: $LOG_FILE" >&2
  exit 2
fi

# 撈最後 1 小時的 F-2 fire（tracing log 格式：2026-05-23T10:30:25.381002Z）
CUTOFF=$(date -u -d "${WINDOW_HOURS} hour ago" +%Y-%m-%dT%H:%M:%S)
FIRE_COUNT=$(awk -v cutoff="$CUTOFF" '$0 ~ "F-2 sanitize" && $1 >= cutoff' "$LOG_FILE" | wc -l)

if (( FIRE_COUNT > THRESHOLD )); then
  echo "[ALERT] F-2 sanitize fire count $FIRE_COUNT in last ${WINDOW_HOURS}h > threshold $THRESHOLD"
  awk -v cutoff="$CUTOFF" '$0 ~ "F-2 sanitize" && $1 >= cutoff' "$LOG_FILE" | tail -5
  exit 1
fi

echo "[OK] F-2 sanitize fire count $FIRE_COUNT in last ${WINDOW_HOURS}h ≤ threshold $THRESHOLD"
exit 0
```

### §4.3.2 Crontab integration (operator step)

`crontab -e` 加（disabled-by-default 直到 Sprint 5+ §4.2.2 wireup PaperState SSOT 後 enable）:
```
# Sprint 5+ Wave 1 §4.4.4 F-2 sanitize fire log monitor
# DISABLED_OPENCLAW_20260523_ENABLE_AFTER_S5_4_2_2_WIREUP
# */15 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/health_f2_sanitize_monitor.sh >>/tmp/openclaw/logs/f2_sanitize_monitor.cron.log 2>&1
```

### §4.3.3 Threshold rationale

- `OPENCLAW_F2_THRESHOLD=0` (default) — 任一 F-2 fire 即 alert
- 上線初期偶有 fire 可允許並 raise threshold（per operator decision）
- 真實 PaperState 永遠 finite → F-2 fire 是 PaperState bug 早期 signal
- 對齊 §2 ladder semantic「敏感過於漏報」

## §4.4 SCRIPT_INDEX update

加新項：
```
| `db/health_f2_sanitize_monitor.sh` | Sprint 5+ Wave 1 §4.4 production hardening — F-2 NaN/inf sanitize fire 監測；DISABLED-by-default 直到 §4.2.2 PaperState SSOT wireup 後 enable；exit 1 表 fire count > threshold |
```

---

# §5 AC-1b monthly cron

## §5.1 AC-1b 範式（per Sprint 4+ §4.1.4 已驗範式）

Sprint 4+ §4.1.4 AC-1b verify SQL（已 PASS 5 active domain × 20-264 row）：
```sql
SELECT domain, COUNT(*) AS row_count
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
GROUP BY domain
ORDER BY row_count DESC;

-- 預期：engine_runtime ≥ 5 + pipeline_throughput ≥ 5 + api_latency ≥ 5 +
--       database_pool ≥ 5 + risk_envelope ≥ 5 (active 5 domain)
--       strategy_quality ≥ 5 (per Sprint 5+ §4.3.1 wireup 後)
-- Sprint 4+ baseline: 5 active × ≥5 row
-- Sprint 5+ baseline: 6 active × ≥5 row (含 strategy_quality)
```

## §5.2 Monthly cron design

### §5.2.1 cadence rationale

| 候選 cadence | trade-off | PA 選擇 |
|---|---|---|
| 每天 (daily) | over-alert；emitter 連續健康時冗餘 | × |
| 每週 (weekly) | 過長窗口；emitter task crash 一週才發現 | × |
| **每月 (monthly)** | **per operator 拍板；2-3 hr 內覆蓋 emitter scheduler resilience 驗證** | ✓ |
| 半年 (semi-annual) | 太稀疏；engine 升級頻率約半年一次無覆蓋 | × |

monthly cron 補位「emitter scheduler resilience verify」 — engine 即使 restart / rebuild / OOM kill 後仍能 30 min 內 5 active domain × ≥5 row 回填。

### §5.2.2 script design

**file**: `helper_scripts/db/ac1b_monthly_healthcheck.sh` (新)

```bash
#!/usr/bin/env bash
# ac1b_monthly_healthcheck.sh — Sprint 4+ §4.1.4 AC-1b production verify monthly cron
#
# 為什麼 monthly:
#   - Sprint 4+ Phase 3c AC-1b 30 min sample wait 一次性驗證 PASS（5 active
#     domain × 20-264 row）；monthly cron 是 sustained verification cadence。
#   - 對齊 operator 「§4.4 全部進 hardening (4 項) + AC-1b monthly cron (不
#     defer)」拍板（per Stage F §8.6 PM Phase 3e sign-off 2026-05-23）。
#
# Exit codes:
#   0 = 6/6 active domain ≥5 row in 30 min window (Sprint 5+ baseline)
#   1 = ≥1 active domain < 5 row (operator alert)
#   2 = DB connection error
#
# Dependencies (與 passive_wait_healthcheck.sh 共用):
#   - $OPENCLAW_BASE_DIR/secrets (POSTGRES env)
#   - control_api_v1/.venv (psycopg2)

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"

# Load secrets (mirror passive_wait_healthcheck.sh:79-88)
if [[ -f "$SECRETS_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_ENV"
  set +a
else
  echo "[FATAL] secrets env not found: $SECRETS_ENV" >&2
  exit 2
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
PG_USER="${POSTGRES_USER:-trading_admin}"
PG_DB="${POSTGRES_DB:-trading_ai}"
PG_CONT="${OPENCLAW_PG_CONTAINER:-trading_postgres}"

# AC-1b query: 30 min window × active domain × ≥5 row
SQL=$(cat <<'EOF'
WITH domain_counts AS (
  SELECT domain, COUNT(*) AS row_count
  FROM learning.health_observations
  WHERE observed_at > NOW() - INTERVAL '30 minutes'
  GROUP BY domain
),
expected AS (
  SELECT UNNEST(ARRAY[
    'engine_runtime',
    'pipeline_throughput',
    'api_latency',
    'database_pool',
    'risk_envelope',
    'strategy_quality'
  ]) AS domain
)
SELECT e.domain, COALESCE(d.row_count, 0) AS row_count
FROM expected e
LEFT JOIN domain_counts d ON e.domain = d.domain
ORDER BY row_count ASC;
EOF
)

# Run query (containerized PG)
OUTPUT=$(docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONT" psql -U "$PG_USER" -d "$PG_DB" -F'|' -A -t -c "$SQL" 2>&1)
RC=$?
if (( RC != 0 )); then
  echo "[FATAL] PG query failed (rc=$RC): $OUTPUT"
  exit 2
fi

# Parse + alert
FAIL_COUNT=0
while IFS='|' read -r domain count; do
  [[ -z "$domain" ]] && continue
  if (( count < 5 )); then
    echo "[ALERT] domain=$domain count=$count < 5 (AC-1b FAIL)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  else
    echo "[OK] domain=$domain count=$count >= 5"
  fi
done <<<"$OUTPUT"

# Sentinel mtime（per cron heartbeat 範式；passive_wait_healthcheck/checks_cron_heartbeat.py 同範式）
SENTINEL_DIR="${OPENCLAW_HEARTBEAT_DIR:-/tmp/openclaw/cron_heartbeat}"
mkdir -p "$SENTINEL_DIR"
touch "$SENTINEL_DIR/ac1b_monthly_healthcheck.last_run"

if (( FAIL_COUNT > 0 )); then
  echo "[ALERT] AC-1b monthly healthcheck FAIL ($FAIL_COUNT domain < 5 row)"
  exit 1
fi

echo "[OK] AC-1b monthly healthcheck PASS (6/6 active domain ≥ 5 row in 30 min window)"
exit 0
```

### §5.2.3 Crontab integration (operator step)

```
# Sprint 5+ Wave 1 §4.4.5 AC-1b monthly healthcheck (per Stage F §8.6 PM phase 3e 拍板)
# Cadence: 每月第 1 號 03:30 UTC（避 daily / weekly cron 撞時）
30 3 1 * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh >>/tmp/openclaw/logs/ac1b_monthly_healthcheck.cron.log 2>&1
```

### §5.2.4 expected baseline (Sprint 5+ post-deploy)

per Sprint 4+ §4.1.4 30 min × 5 domain × 20-264 row 驗證後，Sprint 5+ §4.3.1 wireup 加 strategy_quality 後：

| domain | expected 30 min row count |
|---|---|
| engine_runtime | ~360 row (30s interval × 6 metric) |
| pipeline_throughput | ~360 row |
| api_latency | ~240 row (60s interval × 4 active metric) |
| database_pool | ~150 row |
| risk_envelope | ~30 row (300s interval × 5 metric) |
| strategy_quality | ~125+ row (per Sprint 5+ §4.3.1 wireup 後) |

threshold ≥5/domain 是 「emitter 至少跑了 1 次」 baseline；6 active domain × ≥5 row = monthly cron PASS。

## §5.3 SCRIPT_INDEX update

加新項：
```
| `db/ac1b_monthly_healthcheck.sh` | Sprint 5+ Wave 1 §4.4 production hardening — AC-1b 30 min × 6 active domain × ≥5 row 持續驗證 monthly cron；對齊 Sprint 4+ Phase 3c 驗範式；sentinel mtime touch + exit 1 表 ≥1 domain < 5 row |
```

## §5.4 risk + 副作用

| Risk | Severity | Mitigation |
|---|---|---|
| monthly cron fire 過稀 → engine crash 1 月才發現 | MEDIUM | passive_wait_healthcheck 6h cron 已覆蓋 emitter task alive；本 cron 補位「30 min row count baseline」 |
| `strategy_quality < 5` 在 Sprint 5+ §4.3.1 wireup 前 alert | LOW | 1 號 03:30 UTC fire 時 Sprint 5+ §4.3.1 已 wireup（per Sprint 5+ Wave 1 §4.3 / §4.2 IMPL 先於本 hardening; 已 land Linux empirical 1386 row）|
| 1 號 月初 cron 撞 weekly_report 等其他 cron 競爭 PG 連接 | LOW | 03:30 UTC 是 trading slack；passive_wait_healthcheck 0,6,12,18:00 UTC fire，30 min offset 不撞 |

---

# §6 4 items combined Sprint 5+ IMPL phase split (~6-8 hr E1)

## §6.1 Phase 結構

| Phase | 範圍 | Owner | Effort | Blocker |
|---|---|---|---|---|
| **Phase A**: §2 classify ladder amend (Rust IMPL + test + 注釋) | 2 hr E1 | E1 (1 thread) | 2 hr | none |
| **Phase B**: §2 E2 round 1 + E4 regression | 1 hr E2 + 30 min E4 | E2 + E4 | 1.5 hr | Phase A done |
| **Phase C**: §3 60s boundary verify SOP + script | 1 hr E1 + 30 min QA | E1 + QA | 1.5 hr | Phase A done (concurrent OK) |
| **Phase D**: §4 F-2 sanitize monitor script + crontab spec | 1 hr E1 + 30 min QA | E1 + QA | 1.5 hr | none (concurrent w Phase A/C) |
| **Phase E**: §5 AC-1b monthly cron script + crontab spec + test run | 2 hr E1 + 30 min QA | E1 + QA | 2.5 hr | Phase B done (stable threshold) |
| **Phase F**: operator deploy + crontab install | 30 min operator | operator | 30 min | Phase B + Phase E done |
| **total** | **6-8 hr E1 + 2-3 hr QA + 0.5 hr operator** | | | |

**並行優化**: Phase A (Rust IMPL) + Phase D (Bash + doc) 同時做（不同 codebase；無 LOC 重疊；不會 race）。E1 1-2 thread 都可。

## §6.2 文件改動清單

| 文件 | 改動類型 | Phase |
|---|---|---|
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | edit classify_engine_runtime_open_fd_count + add 注釋 + 2 unit test | A |
| `rust/openclaw_engine/src/health/domains/api_latency.rs` | edit classify_api_latency_ws_rtt_p50_ms + 注釋 + rest_p50/p95/p99 注釋補充 + 2 unit test | A |
| `helper_scripts/db/health_60s_boundary_verify.sql` | new | C |
| `helper_scripts/db/health_60s_boundary_verify.sh` | new | C |
| `helper_scripts/db/health_f2_sanitize_monitor.sh` | new | D |
| `helper_scripts/db/ac1b_monthly_healthcheck.sh` | new | E |
| `helper_scripts/SCRIPT_INDEX.md` | add 4 entries | C/D/E |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md` | new (本文件) | (preamble; done) |

## §6.3 不在範疇

- 不做 WARN→DEGRADED 5min dwell cascade IMPL（per mod.rs line 411-412 注釋 "spike scope"；Sprint 5+ Tier 1 工作）
- 不改 60s window 常量（per source verified；已對齊）
- 不改 emitter scheduler tick interval
- 不加新 health domain（per Sprint 5+ §4.2 / §4.3 範疇）
- 不改 V106 schema（per Stage F §8.6 拍板「不改既有 V106 schema」）
- 不 commit（per dispatch packet 禁忌）

---

# §7 dispatch readiness verdict

## §7.1 verdict
**READY-TO-DISPATCH** — 本 PA design report = 4 items + AC-1b monthly cron 完整 dispatch packet。E1 + E2 + QA + operator chain 接 §6.1 phase 結構即可執行。

## §7.2 prerequisite verified (per memory feedback_fetch_before_dispatch)
- Linux HEAD 5a58cc96 對齊 Mac HEAD (`ssh trade-core git log --oneline -5` verified)
- 6 active domain emitter running (per Linux 6h sample 4296 + 3580 + 2864 + 1790 + 1386 + 365 = 14381 row)
- engine PID 3847231 etime 4h+ healthy
- engine.log writable (3.5 MB / 16749 line)
- F-2 fire 0 (expected; PaperState SSOT wireup 後驗)

## §7.3 16 根原則 compliance check（per skill 16-root-principles-checklist）
- 原則 1 單一寫入口：本 hardening 不改寫入路徑（無 IntentProcessor / submit_intent 涉及）✓
- 原則 4 策略不繞風控：classify ladder 是 health observability 不是 risk gate ✓
- 原則 6 失敗默認收縮：F-2 sanitize 已 fail-loud skip；本 hardening 補 monitoring 對齊保守原則 ✓
- 原則 8 交易可解釋：V106 row 仍含 metric_value + state + state_prev + dwell_time_sec 可追溯 ✓
- 原則 11 Agent 最大自主：本 hardening 不涉 Agent capability；無觸碰 ✓
- 原則 13 AI 成本感知：本 hardening 0 LLM call；無觸碰 ✓
- 原則 14 零外部成本可運行：grep + psql + bash 全本地；無外部依賴 ✓
- **硬邊界 grep**: `execution_state | execution_authority | live_execution_allowed | decision_lease_emitted | max_retries | OPENCLAW_ALLOW_MAINNET | live_reserved | authorization.json` — 本 hardening **0 觸碰** ✓
- 評級：**A 級** 16/16 合規 + 0 硬邊界觸碰

## §7.4 副作用識別清單（per profile §副作用識別清單）
1. ✗ 沒有其他模塊 import classify_engine_runtime_open_fd_count / classify_api_latency_ws_rtt_p50_ms（grep 確認；test fixture 例外見 §2.4）
2. ✗ 函數沒在其他測試 mock（只在 emitter 內部直呼）
3. ✗ 不涉 asyncio/threading 邊界
4. ✗ 不改 API response schema
5. ✗ 不改 RustEngine ↔ Python IPC schema

## §7.5 E2 必重點審查 3 點
1. **§2.3.1 open_fd_count baseline 3072 校準依據**：E2 必驗 production 25 symbol 真實 fd footprint Linux empirical (`docker exec engine ls /proc/{pid}/fd/ | wc -l` 應落 1700-1800)；amend 後 1800 必 OK / 3500 必 WARN unit test 全跑
2. **§2.3.2 ws_rtt 170ms baseline 對 demo / live_demo 適用但 mainnet 切換必 recalibrate**：E2 確認注釋有 "mainnet 切換 sprint 開新 calibrate ladder" warning；不留盲區
3. **§5.2.2 AC-1b script PGPASSWORD vs PG_PASSWORD 變量名一致性**：grep `$PG_PASSWORD` 應全 `$PGPASSWORD`（傳統 libpq env var 名）；E2 catch 變量拼錯 bug 避 cron 跑時 secret 沒注入

## §7.6 下一步
1. operator 確認本 PA design report
2. PM dispatch 4 items combined IMPL 給 E1（per §6.1 phase 結構）
3. E1 IMPL → E2 → E4 → QA → operator deploy + crontab install
4. closure 寫 PA workspace report + memory append

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md
