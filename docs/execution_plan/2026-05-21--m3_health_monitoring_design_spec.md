---
spec: M3 — Self-Monitoring / Auto-Diagnostics / Health-Aware Degradation Module
date: 2026-05-21
author: PA Sprint 1A-β CRITICAL DESIGN deliverable
phase: v5.8 Sprint 1A-β（CRITICAL module DESIGN；ε wave 第 2 module）
status: DESIGN-DRAFT（Sprint 1A-β land 等待 V106 full DDL + M1 LAL / M8 / M11 spec 並行 land 後 cross-reference resolve）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M3 Health Domain（lines 123-151）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-β + §跨 module dependency
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md（V106 schema spec sub-agent 同時段 — placeholder reference）
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md（M3 ↔ M8 amplification loop cap 1-anomaly = 1-state-change/24h）
  - srv/docs/adr/0042-m3-health-monitoring.md（M3 governance authority；R4 audit H-1 reverse-ref patch 2026-05-21）
mirror precedent:
  - srv/helper_scripts/canary/engine_watchdog.py（existing process-level watchdog；M3 復用 + 升級）
  - srv/helper_scripts/db/passive_wait_healthcheck.sh（existing DB passive healthcheck；M3 復用 + 集中）
scope: module 行為 + state machine + integration contract spec；不寫 V106 DDL（V106 spec 主責），不寫 IMPL code（E1 主責）
---

# M3 Health Monitoring Module DESIGN Spec

## §0 TL;DR

- M3 是 **3 層集中健康觀測 + 4 級狀態機 + degradation cascade** 治理模塊；取代當前散落於 watchdog / passive_wait / per-strategy 內嵌 healthcheck 的碎片化現狀
- 6 健康 domain（engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope）；每 domain 獨立 SLO + threshold + dwell time
- 4 級狀態（HEALTH_OK / HEALTH_WARN / HEALTH_DEGRADED / HEALTH_CRITICAL）；升降需 dwell time + flap suppression；HEALTH_CATASTROPHIC 由現有 kill criteria 觸發（不在 M3 範圍）
- Degradation cascade：HEALTH_DEGRADED → Strategy Tier 1 reparam halt / M1 LAL Tier 自動降階 / Auto-approve disabled / Alert routing 升級
- Anomaly amplification loop cap（per H-11 反向 attack + ADR-0036）：M8 1-anomaly 在 24h 內只能觸發 1 次 state change；防 false anomaly burst 觸發無限 degrade
- M3 ↔ M1 LAL / M3 ↔ M11 replay divergence / M3 ↔ M8 anomaly：三個明文 integration contract（避免循環觸發）
- Sprint 1B DESIGN + Sprint 2 partial IMPL + Sprint 5-7 full active monitoring；Sprint 7-8 advisory alerting

---

## §1 Context — 為何 M3 必須集中

### 1.1 v5.7 現狀（fragmented healthcheck）

當前項目的健康監測散落於三處互不協調：

| 來源 | 範圍 | 觸發行為 | 問題 |
|---|---|---|---|
| `helper_scripts/canary/engine_watchdog.py` | engine 進程存活 / IPC heartbeat | systemd restart engine | 只看進程不看 pipeline；engine 跑著但 strategy 全 dormant 也不報警 |
| `helper_scripts/db/passive_wait_healthcheck.sh` | DB lock / migration 卡 / writer queue depth | 阻 TODO sign-off | 只在 passive wait 時觸發；live runtime stalls 無 active alarm |
| Strategy 內嵌 self-test | per-strategy first-detection / dormant / signal rate | strategy 內 log；不外發 alert | 各策略各做各的；無 cross-strategy 互比；first-detection deadlock 反模式（per `feedback_first_detection_deadlock_pattern`）|
| Bybit retCode fail-closed | per-operation API call | 該次 operation 失敗 + log | 不累積；rolling 失敗率高也不升級為 system-level 退化 |
| Manual operator check via Console | 手動觀察 | 操作員行動 | 依賴 operator 不忘記 + 線上時 + 看對 dashboard tab |

**v5.8 §2 M3 設計意圖**（per v5.8 lines 123-151）：把上述碎片化 healthcheck 集中到一個 module，加 state machine + degradation cascade + alert routing，**填補 "per-operation fail-closed" 與 "5-gate kill" 之間的中間層**。

### 1.2 3 層健康（每 domain 各層獨立觀測）

| 層 | 觀測對象 | M3 domain 對應 | 觀測手段 |
|---|---|---|---|
| **Process 層** | OS 級指標：engine 進程存活、CPU%、RSS、open fd、線程數 | `engine_runtime` | engine_watchdog 升級 + procfs 採樣 |
| **Pipeline 層** | 系統內部 throughput：WS tick rate / DB writer queue depth / IPC roundtrip latency / API success rate | `pipeline_throughput` / `database_pool` / `api_latency` | engine 內 metric emitter（5min sampling） |
| **Business 層** | 策略質量：per-strategy fill rate vs intent / signal rate / decision lease grant rate / position 持有時間異常 | `strategy_quality` / `risk_envelope` | engine event hooks + decision lease audit 反查 |

**3 層的存在意義**：Process 層 OK 不代表 Pipeline 層 OK（v5.8 §2 M3 line 125 例證 "engine 跑著但 strategy 全 dormant"）；Pipeline 層 OK 不代表 Business 層 OK（典型：WS 正常 + DB 正常 + strategy 卻 30 個 trade 全虧）。3 層分離是 M3 設計的根本。

### 1.3 為何**集中** > **每模塊各自做**

| 集中（M3） | 散落（現狀） |
|---|---|
| 4 級狀態機是全 system 一致定義 | 每個 module 各自定義 ok/degraded 語意 |
| Degradation cascade 全 system 一致；HEALTH_DEGRADED → 自動降 M1 LAL Tier + halt Tier 1 reparam | 每個 module 各自決定要不要降；缺一致性 + 易漏 |
| Alert routing 統一（Slack / log / Console dashboard）| 每個 module 各自 print log；operator 必須看對 tab 才看到 |
| Anomaly amplification loop cap 一處執行 | 每個 module 自管，互相觸發容易死循環 |
| 與 M1 LAL / M8 / M11 integration contract 明文化 | 隱式互相觸發，狀態流不可追溯 |

---

## §2 6 Health Domain

### 2.1 Domain 設計

| Domain | 層 | 觀測 metric（per V106 schema spec） | 採樣頻率 | 為何此 domain |
|---|---|---|---|---|
| `engine_runtime` | Process | `engine_pid_alive` / `engine_rss_mb` / `engine_cpu_pct` / `engine_open_fd` / `engine_thread_count` / `engine_uptime_sec` | 30s | 進程級基線；engine_watchdog 升級 |
| `pipeline_throughput` | Pipeline | `ws_tick_rate_per_sec` / `ws_heartbeat_lag_ms` / `ws_subscription_drift_count` / `strategy_signal_rate_per_min` / `ipc_roundtrip_ms_p99` | 30s | WS 訂閱 + IPC 健康；典型異常：WS reconnect 後漏訂閱 / IPC 線程死鎖 |
| `database_pool` | Pipeline | `pg_writer_queue_depth` / `pg_pool_active_conn` / `pg_pool_wait_ms_p95` / `pg_replication_lag_ms`（Y2+）/ `disk_data_dir_used_pct` | 60s | PG 寫入 backlog 是潛在系統性 stall；磁盤滿是潛在 corruption |
| `api_latency` | Pipeline | `bybit_rest_success_rate_5min` / `bybit_rest_p95_latency_ms` / `bybit_rest_retcode_nonzero_count` / `bybit_ws_dropout_count_5min` / `bybit_ws_reconnect_count_5min` | 60s | 交易所側健康；rate-limit / 5xx / WS 中斷的累積指標 |
| `strategy_quality` | Business | `per_strategy_fill_rate_intent_ratio` / `per_strategy_slippage_bps_p95` / `per_strategy_decision_lease_grant_rate` / `per_strategy_dormant_minutes` / `per_strategy_signal_count_24h` | 5min | 策略級活性 + fill 品質；典型異常：策略 dormant 不報 / slippage 持續 outlier / lease grant 跌 |
| `risk_envelope` | Business | `portfolio_cum_pnl_24h_usd` / `portfolio_max_dd_pct` / `position_count_active` / `correlation_avg_pairwise` / `concentration_top1_pct` | 5min | Portfolio 級風險聚合；與 §16 portfolio risk 原則對齊；與 5-gate 既有 kill 邊界協作 |

### 2.2 Domain 與既存基礎設施對齊

| Domain | 復用既存 | 新增 |
|---|---|---|
| `engine_runtime` | `engine_watchdog.py` PID check + heartbeat | procfs 採樣 helper（Linux 平台特定，per `feedback_cross_platform` Mac 走 sysctl fallback） |
| `pipeline_throughput` | 既有 IPC heartbeat + tick stats | strategy signal rate emitter（IndicatorEngine hook） |
| `database_pool` | `passive_wait_healthcheck.sh` queue depth check | active sampling cron + emit metric |
| `api_latency` | 既有 retCode log + WS dropout log | 5min rolling 聚合 + emit metric |
| `strategy_quality` | per-strategy log | 集中 emitter + dormant minute 計時 |
| `risk_envelope` | 5-gate envelope + Guardian metrics | 5min aggregator + portfolio metric emitter |

### 2.3 Per-domain SLO + threshold（per H-10 量化 threshold 缺漏 follow-up）

threshold 數值列入 V106 spec `regime_threshold_table`（per ADR-0036 Decision 4 block bootstrap 估計），M3 不寫死 magic number；本 spec 只列**結構 + ladder**。

| Domain | OK band | WARN band | DEGRADED band | CRITICAL band | Measurement window |
|---|---|---|---|---|---|
| `engine_runtime` | PID alive + RSS < 2GB + CPU < 50% | RSS 2-4GB OR CPU 50-80% | RSS > 4GB OR CPU > 80% 持續 5min | PID dead OR engine restart loop > 3/5min | 30s sample, 5min rolling |
| `pipeline_throughput` | WS tick rate > 1/sec/symbol + ipc p99 < 5ms | tick rate < 1/sec/symbol 持續 2min OR ipc p99 5-10ms | tick rate < 0.5/sec/symbol OR ipc p99 > 10ms | WS dropout > 60s OR ipc p99 > 50ms | 30s sample, 5min rolling |
| `database_pool` | queue < 100 + pool wait p95 < 50ms + disk < 70% | queue 100-500 OR wait 50-200ms OR disk 70-85% | queue > 500 OR wait > 200ms OR disk > 85% | queue > 5000 OR pool exhausted OR disk > 95% | 60s sample |
| `api_latency` | success rate > 99% + p95 < 500ms | success rate 97-99% OR p95 500-1000ms | success rate < 97% OR p95 > 1000ms 持續 5min | success rate < 90% OR WS reconnect storm | 60s sample, 5min rolling |
| `strategy_quality` | fill rate > 80% + slippage p95 < 5bps + lease grant rate > 70% | fill rate 60-80% OR slippage 5-10bps OR lease grant 50-70% | fill rate < 60% OR slippage > 10bps 持續 15min OR dormant > 60min | dormant > 6h OR fill rate < 20% OR lease grant < 10% | 5min sample, 1h rolling |
| `risk_envelope` | cum loss < $500/24h + dd < 5% + corr < 0.5 + top1 < 30% | cum loss $500-1500/24h OR dd 5-10% OR corr 0.5-0.7 OR top1 30-50% | cum loss $1500-2500/24h OR dd 10-15% OR corr > 0.7 OR top1 > 50% | cum loss > $2500/24h OR dd > 15% | 5min sample |

**HEALTH_CATASTROPHIC** = portfolio cum loss > $3000（既有 D2 kill criteria；M3 不重定義 only mirror 觀測）。

### 2.4 Multi-domain aggregation rule

M3 emit **per-domain 4 級狀態** + **system-level 1 個 aggregate 狀態**（最差 domain 的狀態 = system 狀態，但 amplification cap 仍適用 per §6）。

---

## §3 4 級狀態機

### 3.1 State 定義

```
HEALTH_OK          ──→  no action
HEALTH_WARN        ──→  alert only（不 action）
HEALTH_DEGRADED    ──→  cascade（M1 LAL 自動降階 / Tier 1 reparam halt / Stage 4 only）
HEALTH_CRITICAL    ──→  halt new orders / drain existing per existing kill criteria
HEALTH_CATASTROPHIC（既有 D2 kill triggers；M3 mirror only，不在本 SM 範圍）
```

### 3.2 State transition graph（per-domain；每 domain 各自走一個 SM；system-level state = max(per-domain state)）

```
                  ┌─────────────────────────────────────┐
                  │                                     │
                  ▼                                     │
    ┌──────────────────┐  WARN-band 持續 dwell       ┌────────────────┐
    │   HEALTH_OK      │ ───────────────────────────▶ │  HEALTH_WARN   │
    │                  │ ◀─────────────────────────── │                │
    └──────────────────┘  OK-band 持續 recover dwell  └────────────────┘
                                                              │
                                                              │ DEGRADED-band 持續 dwell
                                                              │ AND amplification gate PASS
                                                              ▼
                  ┌─────────────────────────────────────────────────┐
                  │  HEALTH_DEGRADED                                │
                  │  (cascade triggered: M1 LAL down / Tier 1 halt) │
                  └─────────────────────────────────────────────────┘
                                                              │
                                                              │ CRITICAL-band 持續 dwell
                                                              │ OR catastrophic event
                                                              ▼
                                                  ┌────────────────────┐
                                                  │  HEALTH_CRITICAL   │
                                                  │  (halt new orders) │
                                                  └────────────────────┘
                                                              │
                                                              │ recovery: 2 階段降階 + 各階段 recover dwell
                                                              ▼ (CRITICAL → DEGRADED → WARN → OK)
```

### 3.3 Dwell time + flap suppression

每 domain 每 transition 必有 dwell time + flap suppression，避免 metric 抖動觸發 state oscillation：

| Transition | Dwell time | Flap suppression |
|---|---|---|
| OK → WARN | 60s 持續 WARN-band（30s × 2 sample）| 24h 內同 domain WARN ↔ OK transition > 3 次 → 自動 lock 至 WARN 直到 1h 全 OK |
| WARN → DEGRADED | 5min 持續 DEGRADED-band + amplification gate PASS | 24h 內同 domain DEGRADED ↔ WARN > 2 次 → 自動 lock 至 DEGRADED 直到 4h 全 OK + operator manual override unlock |
| DEGRADED → CRITICAL | 5min 持續 CRITICAL-band OR catastrophic event 立即 | 不可逆向自動降；只能 CRITICAL → DEGRADED 經 manual unlock |
| CRITICAL → DEGRADED | manual operator unlock + 30min 全 OK | — |
| DEGRADED → WARN | 30min 全 OK + cascade rollback complete | — |
| WARN → OK | 15min 全 OK | — |

**Dwell time rationale**：
- OK → WARN 短（60s）— alert 寧可早；WARN 不 action，false alarm 成本低
- WARN → DEGRADED 長（5min）— cascade 動作有成本（halt strategy / 降 LAL Tier），不能輕觸
- DEGRADED → CRITICAL 短（5min）+ catastrophic 立即 — 保護 priority
- 任何降階 dwell time > 升階 — 防 oscillation；recovery 必須 conservative

**Flap suppression rationale**：per `feedback_first_detection_deadlock_pattern` 反模式教訓——`is_none()` guard + 無過期 auto-clear → 永久 dormant。M3 必須避免該反模式：lock 一律有過期條件（1h / 4h 全 OK + operator manual override），絕不創 dead state。

### 3.4 Per-strategy 變體（strategy_quality domain 特殊規則）

`strategy_quality` 是 per-strategy maintained 25 個 SM（5 strategy × 5 symbol typical）；其他 domain 是 single SM。

- per-strategy SM 升 DEGRADED 不直接觸發 system-level cascade
- per-strategy SM HEALTH_CRITICAL → trigger M7 DECAY_ENFORCED route（per ADR M7；本 spec §5 cascade table）
- system-level `strategy_quality` aggregate = 「DEGRADED 策略數 / 總策略數」；> 40% 才升 system-level DEGRADED

---

## §4 SLO + measurement window + alarm threshold

per H-10 follow-up，本 spec 列 SLO 結構；具體 threshold 數值在 V106 schema spec + ADR-0036 Decision 4 block bootstrap 估計 land 後固化。

### 4.1 SLO target table（structural skeleton）

| Domain | SLO target | Measurement window | Alarm threshold | Re-estimate cadence |
|---|---|---|---|---|
| `engine_runtime` | uptime > 99.9% / month；CPU < 50% average | 1 month sliding | breach > 0.1% of 1 month | per-V Sprint 5 land |
| `pipeline_throughput` | WS tick rate > 1/sec/symbol > 99% time；ipc p99 < 5ms | 1d sliding | breach > 5min cumulative / 1d | 30d block bootstrap re-estimate |
| `database_pool` | queue depth p95 < 100；pool wait p95 < 50ms | 1h sliding | breach > 15min cumulative / 1h | 30d block bootstrap re-estimate |
| `api_latency` | bybit success rate > 99% / 5min；p95 < 500ms | 5min sliding | breach > 5min cumulative / 30min | 30d block bootstrap re-estimate |
| `strategy_quality` | per-strategy fill rate > 80%；slippage p95 < 5bps；dormant < 60min | 1h sliding | breach > 15min cumulative / 1h | per-strategy 30d block bootstrap |
| `risk_envelope` | portfolio dd < 10%；cum loss < $1500/24h | 24h sliding | breach 立即 | static (per 5-gate kill criteria) |

### 4.2 Threshold 從哪來 — 不寫死

per ADR-0036 Decision 4：所有 M3 threshold（除 catastrophic / kill criteria static）**block bootstrap 估計 + ArcSwap 熱更新 + 30d re-estimate cadence**。

threshold 存儲：V106 schema `regime_threshold_table` column（per V106 spec 大綱 §2.1）；hot update 路徑 = ADR-0009 ArcSwap pattern。

### 4.3 Measurement window vs Dwell time 區分

- **Measurement window**：metric 計算的 rolling window（如 ws p95 5min 窗）
- **Dwell time**：state transition 觸發前必持續落在 band 的時間（如 WARN → DEGRADED 5min dwell）
- 兩者**必須獨立**——measurement window 是 metric 算法，dwell time 是 SM 過渡規則

---

## §5 Degradation cascade

HEALTH_DEGRADED 觸發 cascade；HEALTH_CRITICAL 觸發更激進 cascade。

### 5.1 Cascade table

| Source state | Per-domain trigger | Cascade action | Target module | Reversible? |
|---|---|---|---|---|
| HEALTH_DEGRADED | `engine_runtime` | 暫停 non-essential strategy（Tier 1 reparam halt；Stage 4 only continue） | Conductor + Strategist | Yes（state recover 後自動 unhalt） |
| HEALTH_DEGRADED | `pipeline_throughput` | 降低新 order rate 50%；暫停 Tier 1 LAL auto-approve | M1 LAL + Conductor | Yes |
| HEALTH_DEGRADED | `database_pool` | 暫停 non-trading writer（learning.* table writer 降為 batch）；trading writer 不降 | DB writer | Yes |
| HEALTH_DEGRADED | `api_latency` | 切換策略默認 order type（Market → PostOnly maker，減 rate）；M1 LAL Tier 1 auto-approve disable | Strategist + M1 LAL | Yes |
| HEALTH_DEGRADED | `strategy_quality`（per-strategy）| trigger M7 DECAY_ENFORCED（per ADR M7） | M7 | M7 SM 自管 |
| HEALTH_DEGRADED | `risk_envelope` | 全 strategy size scale 50%；M1 LAL 2 auto-approve disable；新 position open block | Guardian + M1 LAL | Yes 經 manual unlock |
| HEALTH_CRITICAL | 任何 domain | halt new orders（HALT_NEW_ORDERS flag）；drain existing per 5-gate kill criteria；Slack CRITICAL alert | Conductor + Guardian | Manual operator action required |
| HEALTH_CATASTROPHIC | per 既有 D2 kill | 5-gate kill 路徑既有 mechanism；M3 不重定義 only mirror 觀測 | 既有 | 既有 mechanism |

### 5.2 Cascade activation order（per-domain trigger 多 domain 同時）

當多個 domain 同時 DEGRADED：
- 1️⃣ 先 cascade `risk_envelope`（直接影響資金安全）
- 2️⃣ 後 cascade `api_latency` + `database_pool`（基礎設施）
- 3️⃣ 最後 cascade `pipeline_throughput` + `strategy_quality`（策略級）

**為何此順序**：per §二 原則 5「生存 > 利潤」+ 原則 6「失敗默認收縮」——資金安全 cascade 優先；基礎設施 cascade 次之；策略級 cascade 最後（避免 false trigger 浪費 active capital）。

### 5.3 Cascade idempotency

每 cascade action 必須 idempotent：M3 重複 emit 同一 DEGRADED state（如 SM 內部 reset 後重 emit），cascade action 不可重複執行（已 halt 的 strategy 不再 halt 一次；已降的 LAL Tier 不再降一次）。

實現：M3 publish state change event 帶 `state_transition_id`（UUID）；下游 module 維護 last applied transition_id；重複 transition_id event 直接 drop。

### 5.4 Cascade rollback

state 降階（DEGRADED → WARN → OK）時必 emit `cascade_rollback` event；下游 module 自動 unhalt / 升 LAL Tier / 恢復 writer batch → realtime / 等。

rollback 觸發條件 = §3.3 dwell time + flap suppression 通過。

---

## §6 Anomaly amplification loop cap

per H-11 反向 attack list（dispatch report HIGH item）+ ADR-0036 Decision 1 例外段（M8 anomaly 不繞 Guardian）。

### 6.1 反向 attack 場景

```
M8 emit anomaly A → M3 HEALTH_DEGRADED → cascade → halt strategy → metric 變化
  → M8 emit anomaly B (因 metric 變化) → M3 HEALTH_CRITICAL → cascade more → ...
```

或：
```
M8 false anomaly burst（5 個 anomaly 1min 內 emit）
  → M3 5 次 state change → cascade 5 次 → 5 個 strategy halt
  → 全 system frozen, alert flooding, operator 無法 triage
```

兩個場景都是 amplification loop。

### 6.2 Loop cap rule（per ADR-0036 + dispatch H-11）

| Rule | 規範 |
|---|---|
| **M8 1-anomaly = max 1 state change / 24h** | M3 接收 M8 anomaly event 觸發 state change 後，**同 anomaly_type + 同 domain** 在 24h 內不再觸發 state change（只記 log）；下次 anomaly 必須 anomaly_type 不同 OR 距 24h |
| **State change rate cap** | M3 自身 state change rate 硬 cap：5 次 / 1h / per-domain；超過 cap 自動 freeze 在當前 state + Slack CRITICAL alert + operator manual unlock 才能繼續 |
| **Cascade depth cap** | 單次 state change 觸發的 cascade action 數量硬 cap：8 個 action / 1 cascade；超過 cap 截斷 + log warning + operator review |
| **Anomaly source identity** | M8 anomaly event 必帶 `anomaly_id` + `anomaly_type`；M3 內部維護 24h rolling cache (`anomaly_id` → 上次觸發 state change 的 timestamp)；同 `anomaly_type` 24h 內僅 1 次 |
| **Fail-open prevention** | 若 amplification cap 觸發後 metric 持續 DEGRADED（真實退化非 false alarm），cap 不自動釋放——必 operator manual unlock；防 fail-open（per §二 原則 6 失敗默認收縮） |

### 6.3 與 M11 replay divergence 的特殊處理

M11 replay divergence 不算 M8 anomaly（不適用 1-anomaly cap）；但 M11 高 divergence flag → trigger M3 對 specific domain re-check（per §7 integration contract）；該 re-check 觸發的 state change 仍受 §6.2 state change rate cap 約束。

---

## §7 M3 ↔ M1 LAL Integration

per CR-2 M1 Lease Tier → LAL 改名 + ADR-0034 spec land 後 final wire。

### 7.1 Integration contract

| M3 state | M1 LAL action |
|---|---|
| HEALTH_OK | LAL 1 + LAL 2 auto-approve 正常運作 per ADR-0034 |
| HEALTH_WARN | LAL 1 + LAL 2 auto-approve 正常運作；alert routing 升級 |
| HEALTH_DEGRADED | LAL 1 auto-approve **disabled**（per CR-15 5-gate auto path inheritance；HEALTH_DEGRADED → auto path inheritance fail-closed）；LAL 2 auto-approve **disabled**；所有 lease decision fall back to operator Advisory |
| HEALTH_CRITICAL | 所有 lease grant disabled；所有現有 active lease 立即 revoke（per 5-gate kill 路徑既有 mechanism） |

### 7.2 LAL Tier 降階與 M3 state mapping

| LAL Tier 降階規則 | 觸發 |
|---|---|
| Tier 1 自動降為 Advisory only | M3 HEALTH_DEGRADED 任一 domain 持續 > 5min |
| Tier 2 自動降為 Tier 1 | M3 HEALTH_DEGRADED 持續 > 30min OR M3 HEALTH_CRITICAL 任一 domain |
| Tier 升回原階 | M3 state 恢復 HEALTH_OK 持續 > 1h + operator manual confirm |

### 7.3 Hand-shake protocol

M3 ↔ M1 LAL 通信走 IPC message bus（per existing event_consumer mechanism）：

```
M3 emit: HealthStateChangeEvent { 
  domain, old_state, new_state, transition_id, timestamp, reason_summary 
}
M1 LAL subscribe: HealthStateChangeEvent → 內部維護 active LAL Tier cache
M1 LAL emit: LALTierChangeEvent { 
  old_tier, new_tier, transition_id (refer M3 transition_id), reason 
}
M3 subscribe: LALTierChangeEvent → 記 audit log；不形成反向 trigger
```

**反向觸發禁止**：M1 LAL state change 不可觸發 M3 state change（防循環）；M3 state change → M1 LAL state change 是單向。

---

## §8 M3 ↔ M11 Replay Divergence Integration

per ADR-0038 M11 + dispatch CR-7 M11 threshold + M11 daily divergence event = M7 input 非 independent demote。

### 8.1 Integration contract

| M11 event | M3 reaction |
|---|---|
| Daily replay divergence flag（small；< $X PnL divergence）| 記 audit log；不 trigger state change |
| Daily replay divergence flag（large；> threshold per ADR-0038 + V107 spec）| M3 對 `strategy_quality` domain 立即 re-check（強制 sample）+ 若 metric 越線則 trigger 標準 state transition（受 §6 amplification cap 約束） |
| Replay divergence 5 day 連續 unack | per dispatch H-11：自動升 M3 HEALTH_WARN（passive Slack 5d 不被 ack mitigation） |
| Replay divergence 7 day 連續 unack | per dispatch H-11：自動升 HEALTH_DEGRADED 並暫停 LAL 1+2 auto-approval（fail-safe to Advisory） |

### 8.2 Re-check trigger 與 amplification cap 協作

M11 trigger 的 re-check 動作 = 強制 sample 一次 metric（不依賴 normal 30s/60s/5min cron）；該強制 sample 走入正常 state transition 評估（包含 dwell time + amplification cap）。

**避免循環**：M11 → M3 state change → M11 不二次 trigger 該 state；M11 只在 nightly replay job 主動觸發 re-check，不接收 M3 state change event。

### 8.3 5d / 7d 自動升階的 dwell time 例外

dispatch H-11 5d unack 自動升 WARN 是**特殊規則**——不走 §3.3 dwell time（因為 unack 本身就 5d 條件嚴格）；7d unack 自動升 DEGRADED 同理。

該規則記為 strategy_quality domain 特殊條款（per V106 evidence_json 留 audit trail）。

---

## §9 Alert routing

### 9.1 Alert channel × severity matrix

| Severity | Slack channel | Console dashboard | Log level | Audit DB |
|---|---|---|---|---|
| INFO（HEALTH_WARN state change）| `#openclaw-alerts-info`（low-noise）| green badge w/ tooltip | `INFO` | learning.health_observations |
| WARNING（HEALTH_DEGRADED state change）| `#openclaw-alerts-warning` + 提及 operator | yellow badge + cascade summary | `WARN` | learning.health_observations + learning.cascade_event_log |
| CRITICAL（HEALTH_CRITICAL state change）| `#openclaw-alerts-critical` + @operator mention + SMS（per AMD-2026-05-15-01 / operator notification escalation） | red badge + kill switch button | `ERROR` | learning.health_observations + learning.cascade_event_log + immediate operator review row |
| CATASTROPHIC | per 既有 D2 kill alert path | red banner top of dashboard | `CRITICAL` | per 既有 |

### 9.2 Per-domain × severity matrix

| Domain | INFO routing | WARNING routing | CRITICAL routing |
|---|---|---|---|
| `engine_runtime` | log only | Slack info | Slack critical + @operator |
| `pipeline_throughput` | log only | Slack info | Slack critical + @operator |
| `database_pool` | log only | Slack info | Slack critical + DB ops alert |
| `api_latency` | log only | Slack info | Slack critical + BB consult |
| `strategy_quality` | log only | Slack info | Slack warning + M7 trigger |
| `risk_envelope` | Slack info | Slack warning + @operator | Slack critical + @operator + SMS |

### 9.3 Alert rate-limiting

per AMD-2026-05-15-01 mitigation：alert flooding 反 attack——operator 24h 內收 > 20 個 WARN level alert 自動降為 daily digest（per dispatch H-12 灰度事件嚴重度對照表）。

CRITICAL alert 不 rate limit（per §二 原則 5 生存 > 利潤）。

### 9.4 Alert content schema

每 alert 必含：
- `transition_id`（UUID；可 追溯 V106 audit row）
- `domain` + `old_state` → `new_state`
- `reason_summary`（自動生成；如 "ws_p99 > 50ms persistent 6min" / "portfolio dd 12% > 10% threshold"）
- `cascade_actions_taken`（list of cascade target + action）
- `expected_recovery_path`（如 "auto recover when ws_p99 < 5ms × 30min"）
- `manual_unlock_link`（Console deep link to relevant tab，per A3 GUI sign-off CR-11）

---

## §10 Acceptance criteria

Sprint 1B IMPL 完成時必須 PASS 全 7 條：

| AC-# | Acceptance criteria | Verification method |
|---|---|---|
| **AC-1** | 6 domain 各自 SM 完整性 proptest（state transition 窮舉 + invalid transition rejected + dead-state scan + `is_none()` reset auto-clear 反模式 scan） | E4 `cargo test` proptest harness per dispatch H-14 |
| **AC-2** | Dwell time validation：mock metric sequence（WARN-band 持續 30s, 60s, 90s）驗 60s threshold 觸發 transition | E4 unit test + integration test |
| **AC-3** | Flap suppression validation：24h 內 3 次 WARN ↔ OK transition → 第 4 次 lock 至 WARN | E4 integration test + 24h simulated time |
| **AC-4** | Cascade chain test：HEALTH_DEGRADED → 觀察 M1 LAL Tier 1 auto-approve disabled + strategy halt + cascade_rollback 升回 → 全部復原 | E4 integration test + cross-module mock |
| **AC-5** | Amplification cap test：M8 emit 5 同 anomaly_type / 1min → 只觸發 1 次 state change | E4 integration test + M8 mock |
| **AC-6** | Cross-language fixture：M3 state evaluation 在 Rust + Python 復刻 1e-4 容差 | E4 共用 fixture harness per dispatch H-18 |
| **AC-7** | SLO breach detection：mock metric sequence breach SLO → 對應 V106 audit row INSERT + Slack mock emit | E4 integration test + V106 schema verify |

額外（推薦但非阻塞）：
- AC-8（Sprint 5 Tier 1 IMPL）：HEALTH_DEGRADED → M7 DECAY_ENFORCED 自動觸發路徑 verify
- AC-9（Sprint 7 Tier 2 IMPL）：alert routing × severity matrix end-to-end Slack mock verify

---

## §11 IMPL phase split

### 11.1 Tier 1 — Active monitoring（Sprint 4-5）

| Item | Sprint | Workload |
|---|---|---|
| V106 schema land + Guard A/B/C + hypertable + idempotency | 1A-β | per V106 spec full DDL |
| 6 domain metric emitter（engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope） | 2 | 60-80 hr |
| 4 級 SM（per-domain + system-level aggregate；dwell time + flap suppression） | 2 | 40-60 hr |
| Cascade action wire（M1 LAL Tier 自動降階 / Tier 1 reparam halt） | 5 | 40-60 hr |
| Amplification cap（M8 anomaly cap + state change rate cap） | 5 | 20-30 hr |
| AC-1..7 全 PASS verify | 5 | per E4 regression |

### 11.2 Tier 2 — Advisory alerting（Sprint 7-8）

| Item | Sprint | Workload |
|---|---|---|
| Alert routing × severity matrix（Slack channel + Console badge）| 7 | 40-60 hr |
| Recovery / auto-restore logic（state 降階 cascade rollback） | 7 | 40-60 hr |
| M11 replay divergence integration（5d/7d unack auto-escalate） | 8 | 20-30 hr |
| Per-domain × severity alert content schema + audit trail | 8 | 20-30 hr |
| Monthly Operator Review Wizard M3 panel（A3 GUI per CR-11） | 8 | 16-24 hr A3 |

### 11.3 Y2+ — Active trigger（M8 → M3）

per v5.8 §2 M3 line 144-149 既有 scope + ADR-0036 Decision 2 Y2 active trigger：M8 high-severity anomaly → trigger M3 HEALTH_DEGRADED state（不再只 read-only logging）。

Workload：30-50 hr per v5.8 §2 M8 Sprint 8 + Y2 scope。

---

## §12 Cross-V### dependency

### 12.1 Direct dependency

| V### | Role | Dependency direction | Sprint |
|---|---|---|---|
| **V106** | M3 own schema（hypertable 7d chunk + 7d compression + 90d retention） | M3 直接 owner；MIT 同時段 spec doc | 1A-β |
| V109 | M8 anomaly_events table（M3 subscribe → §6 amplification cap） | M3 read-only consume；不寫 V109 | 1A-γ |
| V112 | M1 LAL tier table（M3 publish HealthStateChangeEvent → M1 LAL Tier 降階） | M3 publish；M1 LAL consume | 1A-β |
| V107 | M11 replay_divergence_log（M3 read-only consume → §8 re-check trigger） | M3 read-only consume；不寫 V107 | 1A-β |
| V108 | M9 A/B framework（M3 不直接交互；M9 read-only） | 無 direct | 1A-γ |
| 既有 V### | strategy fills / lease audit | M3 read-only consume for strategy_quality + risk_envelope domain | — |

### 12.2 V106 schema 大綱（per V106 spec 主責）

per V106 spec 大綱 §2.1：
- 新增 hypertable `learning.health_observations`（7d chunk + 7d compression policy + 90d retention per E5 audit）
- 6 hot domain × 多 metric per domain（per §2.1）
- `engine_mode CHECK` 4 值齊全；training filter `IN ('live','live_demo')`
- `regime_threshold_table` column（per §4.2 threshold 估計）

新增 audit/cascade 表（V106 範圍待 MIT 確認）：
- `learning.cascade_event_log`（state transition + cascade action audit；per AC-5 + §9.4）
- 或合入 V106 同次 migration（per V106 spec 結構由 MIT 決定）

### 12.3 Cross-V### sequencing

per dispatch CR-9 + 5.3 V### 順序：
- Sprint 1A-β：V106 + V107 + V112 必先 land（M3 / M11 / M1 LAL DESIGN 共享）
- Sprint 1A-γ：V109 land 後 M3 ↔ M8 wire 才能 IMPL（Sprint 5）

### 12.4 Migration dependency lock

V106 必先於 V107 + V112 land（M3 是 M11 + M1 LAL 的 downstream consumer；schema 順序倒置會死鎖）；MIT 寫 V106 spec 時必標 cross-V### dependency graph。

---

## §13 §二 16 根原則合規確認

| # | 原則 | 是否相容 | M3 對應設計 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M3 不創 order 寫入口；cascade action 經 Conductor + Guardian 既有單一寫入口 |
| 2 | 讀寫分離 | ✅ | M3 自身僅讀 metric + 寫 audit row (V106)；不寫 trading state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M3 state change → cascade action 經 M1 LAL + Conductor + 既有 5-gate；不繞 lease |
| **4** | **策略不繞風控** | ✅ | **M3 HEALTH_DEGRADED → 走 Guardian + 5-gate 既有 cascade**；不創新風控繞道 |
| 5 | 生存 > 利潤 | ✅ | §5.2 cascade activation order risk_envelope 優先；CRITICAL 立即 halt new orders |
| 6 | 失敗默認收縮 | ✅ | §6.2 amplification cap 觸發後 fail-open prevention；M11 5d/7d unack 自動升階 |
| 7 | 學習 ≠ live | ✅ | M3 不寫 live strategy state；只 publish state change event → 下游 module 自決定 cascade action |
| 8 | 交易可解釋 | ✅ | §9.4 alert content schema 含 transition_id + reason_summary + cascade_actions_taken 可 audit reconstruct |
| 9 | 雙重防線 | ✅ | 本地 M3 + Bybit 既有 conditional order 雙重防線；M3 不替代 5-gate kill |
| 10 | 分離事實 / 推論 / 假設 | ✅ | metric 數值 = 事實；state transition = 推論（per threshold）；amplification cap 設計 = 假設待 RCA 驗 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | M3 SM 自主升降 state；cascade action 在 P0/P1 既有風控邊界內；不擴 |
| 12 | 行為由 evidence 演化 | ✅ | per §4.2 threshold 30d block bootstrap 自動 re-estimate；不寫死 |
| **13** | **cost 感知** | ✅ | M3 metric emitter 5min sample 為主（不 hot path）；cascade action 既有 mechanism cost 已驗；不新增 LLM cost |
| 14 | 零外部成本 | ✅ | M3 全 self-monitoring；不依賴付費 external metric service |
| 15 | 多 agent 形式化協作 | ✅ | M3 + M1 LAL + M7 + M8 + M11 + Conductor 各有明確 message contract；不暗交互 |
| **16** | **Portfolio > 孤立 trade** | ✅ | `risk_envelope` domain 是 portfolio-level（cum loss / dd / correlation / concentration）；對齊 §16 |

---

## §14 Open questions

### Q1 — `strategy_quality` per-strategy SM 是否需要單獨 LAL Tier 降階？

當前設計：per-strategy SM 升 DEGRADED → trigger M7 DECAY_ENFORCED；不直接 cascade LAL Tier。

替代設計：per-strategy SM 升 DEGRADED → 該策略 own lease grant 降為 Advisory only（其他策略不影響）。

**問題**：per-strategy LAL Tier 降階機制在 ADR-0034 中是否支援？若不支援，是 ADR-0034 升 v1.1 還是 M3 維持當前設計？

**Owner**：CC + QA + PA cross-review Sprint 1A-β land 前 confirm。

### Q2 — Amplification cap 24h window 是 wall-clock 還是 strategy-active hour？

當前設計：24h wall-clock。

**問題**：若 strategy 在 24h 內僅 active 8h（per market hour overlap），cap 是否應只算 active 8h？wall-clock 太鬆？

考量：crypto perp 24/7 都 active，wall-clock 應該 OK；但 Y2+ M13 multi-venue 後可能 venue 各自有 trading window，需重新評估。

**Owner**：QC + FA Sprint 5 Tier 1 IMPL 前 confirm。

### Q3 — HEALTH_DEGRADED 觸發 LAL Tier 降階後，operator 是否有 manual override 「force LAL Tier 1」的能力？

當前設計：LAL Tier 自動降階後，只能 M3 state 恢復 HEALTH_OK 持續 > 1h + operator manual confirm 才升回。

**問題**：若 M3 false alarm（如 metric 採樣 bug），operator 是否需要 force override 立即升回 LAL Tier 1（不等 1h dwell）？

考量：force override 違反 §二 原則 5/6（生存 > 利潤 / 失敗默認收縮）；但若是真 false alarm，cost 高（halt strategy 1h）。

**Mitigation 候選**：operator manual override **必走 Decision Lease**（per §二 原則 3）+ 必填 `override_reason` + override audit 走 V106 audit trail。

**Owner**：CC + Operator Sprint 5 Tier 1 IMPL 前 confirm。

### Q4 — Domain `risk_envelope` 與既有 5-gate kill criteria 的 boundary 如何明示？

當前設計：M3 risk_envelope CRITICAL trigger 自身 cascade action（halt new orders）；HEALTH_CATASTROPHIC（cum loss > $3000）由既有 D2 kill 觸發；M3 mirror only。

**問題**：risk_envelope DEGRADED → CRITICAL → CATASTROPHIC 三 band 的 threshold 從哪來？V106 spec 是否需要 cross-reference 既有 5-gate kill config（risk_config*.toml）？

考量：若 M3 與 5-gate kill threshold 不同步（如 M3 認為 $2500 DEGRADED 但 5-gate 認為 $2000 已 kill），會出現 5-gate 已 kill 但 M3 還在 DEGRADED 的不一致狀態。

**Owner**：FA + PA Sprint 5 Tier 1 IMPL 前 confirm（per `feedback_env_config_independence` 三環境風控 config 獨立教訓）。

### Q5 — Mac 平台 procfs 不存在；engine_runtime domain Mac fallback 機制？

當前設計：engine_runtime 采樣依賴 procfs（Linux 平台特定）；Mac 走 sysctl fallback（per `feedback_cross_platform` 跨平台兼容性準則）。

**問題**：Mac sysctl 提供的 metric 與 procfs 是否 1:1 對應？若不對應，Mac 上 engine_runtime domain state 是否會與 Linux 不一致？

考量：Mac 是開發機，不是 runtime；M3 在 Mac 上應該 graceful degrade（某些 metric 標 `UNAVAILABLE`）不 crash；但 Mac 開發者要 confirm 不會誤判 state。

**Owner**：E5 + PA Sprint 2 metric emitter IMPL 前 confirm。

---

## §15 Cross-References

- **v5.8 主檔 §2 M3 Health Domain**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:123-151`
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-β + §跨 module dependency
- **V106 schema spec**：`docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`（MIT 同時段 placeholder；full DDL Sprint 1A-β land）
- **ADR-0036 M8 anomaly + M10 Tier D**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（M3 ↔ M8 amplification loop cap 1-anomaly = 1-state-change/24h；per H-11 + Decision 1 例外段）
- **ADR-0034 M1 LAL（待 commit）**：M3 ↔ M1 LAL integration contract；HEALTH_DEGRADED → LAL Tier 自動降階
- **ADR-0038 M11 Continuous Counterfactual Replay**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（M3 ↔ M11 replay divergence re-check trigger）
- **M1 LAL spec doc**：（sub-agent 同時段在寫 — placeholder）
- **M8 spec doc**：（sub-agent 同時段在寫 — placeholder）
- **M11 spec doc**：（sub-agent 同時段在寫 — placeholder）
- **CLAUDE.md §五 Architecture Pointers**：stable architecture pointer routing
- **`feedback_no_dead_params` memory**：「可調參數禁止假功能」——M3 所有 threshold 必真實被 healthcheck 使用 + V106 audit row 真實 INSERT；不允許 placeholder threshold 不接入 SM
- **`feedback_first_detection_deadlock_pattern` memory**：M3 state lock 機制必有過期條件（1h / 4h 全 OK + operator manual override），絕不創 dead state
- **`feedback_cross_platform` memory**：Mac 開發機 graceful degrade（procfs fallback）
- **`feedback_env_config_independence` memory**：三環境風控 config 獨立——M3 threshold per-engine_mode 獨立
- **`helper_scripts/canary/engine_watchdog.py`**：既存 process-level watchdog；M3 復用 + 升級至 domain-level
- **`helper_scripts/db/passive_wait_healthcheck.sh`**：既存 DB passive healthcheck；M3 復用 + 集中
- **dispatch H-10 量化 threshold**：M3 5 domain threshold 具體值 follow-up
- **dispatch H-11 反向 attack mitigation**：amplification cap + 5d/7d unack 自動升階
- **dispatch H-12 灰度事件嚴重度對照表**：M3 HEALTH_DEGRADED WARNING / HEALTH_CRITICAL CRITICAL-eligible 重置 7d
- **dispatch H-14 STATE-MACHINE-TEST**：per-domain proptest 窮舉 + dead-state scan
- **dispatch H-18 cross-language 1e-4 容差 fixture**：M3 state evaluation 共用 fixture harness

---

## §16 Engineering scope summary

| Phase | Sprint | Item | Workload |
|---|---|---|---|
| DESIGN | 1A-β | M3 module spec doc（本 spec）+ ADR (R4 建議補 stateful SM 必要) | 12-20 hr |
| DESIGN | 1A-β | V106 schema spec land + Linux PG dry-run | per V106 spec 主責 30-50 hr |
| Tier 1 IMPL | 2 | 6 domain metric emitter | 60-80 hr |
| Tier 1 IMPL | 2 | 4 級 SM + dwell + flap suppression | 40-60 hr |
| Tier 1 IMPL | 5 | Cascade wire（M1 LAL + Tier 1 halt） | 40-60 hr |
| Tier 1 IMPL | 5 | Amplification cap | 20-30 hr |
| Tier 2 IMPL | 7 | Alert routing × severity matrix | 40-60 hr |
| Tier 2 IMPL | 7 | Recovery / auto-restore cascade rollback | 40-60 hr |
| Tier 2 IMPL | 8 | M11 replay divergence integration | 20-30 hr |
| Tier 2 IMPL | 8 | A3 Monthly Review M3 panel | 16-24 hr A3 |
| Y2+ | Y2 | M8 active trigger（M8 anomaly → M3 HEALTH_DEGRADED）| 30-50 hr |
| **Total Y1** | — | DESIGN + Tier 1 + Tier 2 | **288-430 hr** + V106 schema (per V106 spec) |
| **Total Y2+** | — | Active trigger + recovery polish | 30-50 hr |

---

## §17 Risk / Blockers / Operator Decisions

### 17.1 Risk

| Risk | Mitigation |
|---|---|
| V106 schema 大綱與本 spec § domain list 不一致 | MIT 寫 V106 spec 時 cross-verify 本 spec §2.1 6 domain；本 spec land 後 V106 spec 同步 update placeholder |
| Cascade action 與 M1 LAL Tier 降階 race condition | per §7.3 hand-shake transition_id 機制；E4 integration test 必 simulate concurrent state change |
| Amplification cap 過嚴致漏報真實 critical | per §6.2 fail-open prevention；CRITICAL band 不受 amplification cap 約束（critical 立即觸發） |
| Mac 平台 procfs 不存在致 engine_runtime UNAVAILABLE | per Q5 graceful degrade；Mac engine 本就不是 runtime |
| Dwell time 過長致 emergency 反應延遲 | CRITICAL band dwell 短（5min + catastrophic 立即）；DEGRADED dwell 較長（5min）平衡 |
| Flap suppression lock 後 metric 真實 OK 但 stuck 至 lock 過期 | per §3.3 lock 必有過期條件 + operator manual override unlock；絕不創 dead state |

### 17.2 Blockers

| Blocker | Resolution |
|---|---|
| V106 spec full DDL 未 land | Sprint 1A-β 同時段並行；MIT 主責 |
| ADR-0034 M1 LAL 未 land | Sprint 1A-β 同時段並行；PA + CC + QA 主責；本 spec § 7 integration contract 待 ADR-0034 land 後 final wire |
| ADR-0038 M11 未 land | 已 land（per `docs/adr/0038-...md`）；§8 integration contract 可 cross-ref |
| H-10 量化 threshold 缺漏 | per V106 spec block bootstrap 估計；Sprint 5 Tier 1 IMPL 前 land |

### 17.3 Operator decision points

per v5.8 §12 operator decision pattern：

- **D1**：Q1 — `strategy_quality` per-strategy LAL Tier 降階機制是否擴 ADR-0034 v1.1？或維持當前 M7 DECAY_ENFORCED route？
- **D2**：Q3 — operator manual override LAL Tier 升回的機制是否走 Decision Lease + override_reason 必填？
- **D3**：Q4 — risk_envelope domain threshold 與 5-gate kill criteria 的同步 mechanism 是 manual sync 還是 V106 schema cross-reference？

---

**END M3 Health Monitoring Module DESIGN Spec**

*OpenClaw / Arcane Equilibrium M3 Module DESIGN — Self-Monitoring / Auto-Diagnostics / Health-Aware Degradation — Sprint 1A-β CRITICAL deliverable per v5.8 §2 M3 + PA dispatch consolidation CR-2-related cascade integration*
