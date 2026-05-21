---
spec: M2 — Overlay Enable / Disable State Machine（macro / on-chain / regime 三類 overlay 治理）
date: 2026-05-21
author: PA Sprint 1A-γ CRITICAL DESIGN deliverable
phase: v5.8 Sprint 1A-γ（M2 module DESIGN；V105 schema 已 land 由 MIT 主責）
status: DESIGN-DRAFT（V105 schema spec full DDL 已 land；本 spec 為 module 行為層 spec；待 M11 / M3 / M1 LAL sister-spec land 後 final cross-reference resolve）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M2 Overlay Enable / Disable（lines 89-121）
  - srv/docs/execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md（V105 schema spec full DDL；ref schema 不重定義）
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md（M3 module DESIGN spec；M2 ↔ M3 integration baseline 範式）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-γ + §跨 module dependency
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md（LAL Tier 0-4 對齊；M2 → LAL Tier 降階 cascade）
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md（M8 → M2 m8_anomaly trigger；amplification loop cap）
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md（M11 divergence → M2 m11_divergence trigger；counterfactual_log_ref UUID）
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md（M3 sister-module 17-section DESIGN spec 範式）
scope: M2 module 行為 + 5 狀態 finite state machine 行為 + 5 trigger_type semantic + dwell time + flap suppression + cross-module integration contract spec；**不寫 V105 DDL**（V105 spec 主責；已 land），**不寫 IMPL code**（E1 主責 Sprint 5+ ）
---

# M2 Overlay State Machine Module DESIGN Spec

## §0 TL;DR

- M2 是 **3 overlay type × 5-state FSM × 5 trigger_type** 治理模塊；strategy enable / disable 的決策由 overlay state 決定，**取代** v5.7 「macro + on-chain counterfactual-only」碎片化現狀
- 3 overlay_type：`macro`（Fed / FOMC / CPI / 宏觀 regime；strategy-scope = all symbol）/ `onchain`（BTC realized vol / ETH gas / stablecoin flow / exchange netflow；strategy-scope = per-symbol）/ `regime`（volatility ATR + ADX trend/range + cross-asset correlation；strategy-scope = per-(strategy, symbol)）
- 5 state ENUM 對齊 ADR-0034 LAL Tier 0-4：`INACTIVE`(Tier 0) → `WATCHING`(Tier 1) → `ARMED`(Tier 2) → `ACTIVE`(Tier 3) → `COOLDOWN`(Tier 4 disabled-auto；48h 後 INACTIVE)
- 5 trigger_type semantic（per CR-7 dedup contract single authority）：`m3_health`(M3 → COOLDOWN) / `m11_divergence`(M11 → WATCHING/ARMED 升階) / `m8_anomaly`(M8 → COOLDOWN demote) / `operator`(Console manual) / `time_based`(scheduled dwell-time auto)
- **每 transition 必 log counterfactual_log entry**（V105 schema `counterfactual_log_ref` UUID + `evidence_json`；M11 replay-driven transition 強制 NOT NULL；非 replay transition 仍寫 evidence_json 保留 trigger context）
- engine_mode 5 mode 差異：`replay` 是 M11 counterfactual write path（per ADR-0038）；training / production query 必 `IN ('live','live_demo')` 排除 replay 污染
- **M2 ↔ M11**（V107 divergence > NOISE_FLOOR → 升階 trigger）；**M2 ↔ M3**（HEALTH_DEGRADED → 自動 COOLDOWN）；**M2 ↔ M1 LAL**（state change 寫入 LAL Tier 2-3 reparam halt 決策路徑，**對齊 ADR-0034 LAL Tier 0-4 數字越大越嚴**）
- 反向 attack 6 條 mitigation（per H-11 #2 M2 false anomaly cascade + 配套）：嚴格 trigger 條件 + amplification cap + 多訊號合議 + dwell time + manual unlock fail-safe
- AC 7 條 sign-off 標準（per M3 範式 5-7 條規模）；IMPL 三階段（Sprint 5 read-only logger / Sprint 7 advisory / Y2+ auto-enable）
- 3+ open question 待 operator / cross-role 決議

---

## §1 Context — 為何 M2 必須 state machine 化

### 1.1 v5.7 現狀（fragmented overlay handling）

當前項目的 overlay 邏輯散落於以下三處互不協調：

| 來源 | 行為 | 問題 |
|---|---|---|
| 各策略內 hardcoded macro filter | 部分策略在 FOMC 前 ±24h 暫停 open；其他策略無此邏輯 | per-strategy 各做各的；策略間不一致；無 audit trail |
| `helper_scripts/regime/` 內 ad-hoc regime tag | per-bar 計算 volatility regime tag；僅 advisory log | 不影響 strategy 決策；regime shift 後策略繼續 trade |
| 無 on-chain signal | 完全缺；BTC realized vol / ETH gas / stablecoin flow / exchange netflow 全無 ingest | Y2 計劃要 enable，但無 hook 點 |
| M11 replay-driven counterfactual | 既有 ADR-0038 設計；M11 算 counterfactual divergence 但無 state advance 接口 | 即使 counterfactual 證明 overlay 有 alpha，無 mechanism trigger production enable |
| Operator Console manual toggle | 假想接口；無 backend；無 audit | Console 改了狀態 engine 不知道；改了狀態無 reverse mechanism |

**v5.8 §2 M2 設計意圖**（per v5.8 lines 89-121）：把上述碎片化 overlay handling 集中到 1 個 state machine module，加 5 state FSM + 5 trigger_type + V105 audit trail + cascade，**填補 "counterfactual-only Y1" 與 "Y2 production enable" 之間的中間層**。

### 1.2 3 類 overlay 為何如此切分

| Overlay Type | Signal Source | Scope | 採樣頻率 | state 變動預期 |
|---|---|---|---|---|
| **macro** | Fed FOMC + CPI + jobs report + macro regime indicator | all strategy × all symbol（strategy_id NULL + symbol NULL） | event-driven + daily | macro event 24h before → WATCHING；event window → ARMED；後 48h → COOLDOWN |
| **onchain** | BTC realized vol(24h) + ETH gas + stablecoin flow + exchange netflow | per-symbol（strategy_id NULL OR by策略；symbol NOT NULL） | hourly | signal PSI > 0.25 → WATCHING；confirm > 1h → ARMED；alpha confirmed → ACTIVE；anomaly → COOLDOWN |
| **regime** | volatility regime(ATR ratio) + trend vs range(ADX) + cross-asset correlation | per-(strategy_id, symbol)（兩者皆 NOT NULL） | per-bar(5min) | regime fluctuation 高頻 INACTIVE ↔ WATCHING；regime shift confirmed → ARMED；shift sustained → ACTIVE |

**3 類 scope 不同的工程意義**：
- macro overlay state 變動影響全 system；row 量級小（~20/月）但 cascade 範圍大
- onchain overlay state 變動影響該 symbol 的所有策略；row 量級中（~20/day）
- regime overlay state 變動影響該 (strategy, symbol) 對；row 量級大（~6250/day 主導 V105 chunk 設計）

### 1.3 為何 5-state FSM > 4-stage promotion ladder

v5.7 採 4-stage promotion ladder（counterfactual-only → shadow → advisory → production）；v5.8 §2 M2 + 本 spec 採 **5-state FSM**（INACTIVE / WATCHING / ARMED / ACTIVE / COOLDOWN），對齊 V105 schema land 後 ADR-0034 LAL Tier 0-4 共識：

| State | LAL Tier | 描述 | 對應 4-stage ladder 哪一段 | 為何 4-stage 不足 |
|---|---|---|---|---|
| INACTIVE | Tier 0 | overlay dormant baseline | counterfactual-only 期之前 | 4-stage 漏「未啟用」初始狀態 |
| WATCHING | Tier 1 | signal detected 未 confirm | counterfactual-only 期 | OK，但 4-stage 不分 detected/confirmed |
| ARMED | Tier 2 | signal confirmed，reparam halt 候選 | shadow + advisory 模糊邊界 | 4-stage 把 shadow 與 advisory 混為一段 |
| ACTIVE | Tier 3 | overlay 影響 production decision | production | OK |
| COOLDOWN | Tier 4 | disabled-auto；48h 後 INACTIVE | 漏；4-stage 無 disabled-auto 後過渡層 | **4-stage 最大缺漏**：disabled → 如何回 enable？需中間層保留 audit + dwell time |

**5-state vs 4-stage 工程收益**：
- 5-state 與 ADR-0034 LAL Tier 0-4 完美 1:1 mapping（per V105 spec §1.2）
- COOLDOWN 是 disabled-auto 後 audit + recovery 中間層；4-stage 漏此語義致 production rollback 後 state 模糊
- per FSM proptest（per dispatch H-14 + M3 spec AC-1 範式）5-state transition 窮舉測試比 4-stage 完備

### 1.4 strategy enable 由 overlay state 決定的工程語意

每筆 strategy decision 進 Guardian 前，必查當前 overlay state：

```
For strategy decision (strategy_id, symbol):
  1. 查 macro overlay state（strategy_id=NULL, symbol=NULL；單一 row）
  2. 查 onchain overlay state for symbol（strategy_id=NULL, symbol=this_symbol）
  3. 查 regime overlay state for (strategy_id, symbol)
  4. 三層 state aggregate:
     - 任一 COOLDOWN → strategy decision BLOCKED（不允許新 open；既有 position 走 close-only）
     - 任一 ACTIVE 反向（如 macro ACTIVE 提示 risk-off 但 strategy 是 long-bias）→ strategy decision filtered
     - 全 INACTIVE/WATCHING/ARMED → strategy decision PASS（按 strategy 內部邏輯走）
  5. mv_latest_overlay_state_per_strategy materialized view 提供 μs 級 query path
```

**這是 M2 的 production wire 語意**（per Sprint 5 Tier 1 IMPL）；當前 Sprint 1A-γ DESIGN 階段不寫此 wire；只定義 state machine 行為。

### 1.5 v5.8 §2 M2 與本 spec 對齊

v5.8 §2 M2 早期 draft 用「4-stage promotion ladder」+ STATE_DISABLED_AUTO 後續補；V105 spec land 後採 5-state FSM。本 spec 採 V105 已 land 的 5-state ENUM（INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN）+ 5 trigger_type ENUM（m3_health/m11_divergence/m8_anomaly/operator/time_based）為 baseline，向 v5.8 §2 M2 早期 draft 終止 reconcile（per V105 spec §1.5）。

---

## §2 5-State Enum 行為定義

### 2.1 State semantic table

| State | LAL Tier | Strategy decision 影響 | Reparam halt | 進入條件主例 | 離開條件主例 |
|---|---|---|---|---|---|
| `INACTIVE` | 0 | 不影響 strategy decision；strategy 按既有邏輯 trade | 否 | M2 首次啟動 baseline；COOLDOWN dwell 48h 後 time_based 過渡 | signal detected：m11_divergence > NOISE_FLOOR / m3_health passes / regime PSI > 0.25 |
| `WATCHING` | 1 | 不影響 strategy decision；overlay observer mode | 否 | INACTIVE + 任一 signal 首次出現 | signal confirm > 1h dwell → ARMED；signal disappear > 15min recover dwell → INACTIVE |
| `ARMED` | 2 | 不影響 strategy decision；reparam halt **soft** candidate（advisory only Y1；Y2 active） | Soft（advisory） | WATCHING + signal sustained 1h | signal alpha confirmed > 6h dwell → ACTIVE；signal disappear > 30min recover dwell → WATCHING |
| `ACTIVE` | 3 | **影響 strategy decision**；overlay-affected strategies enable / disable per overlay logic | Hard | ARMED + alpha sustained 6h（Y2 only Auto；Y1 operator approve once）| Sharpe < 0 / counterfactual diverge / anomaly → COOLDOWN |
| `COOLDOWN` | 4 | **影響 strategy decision**：strategy 進入 close-only mode；新 open BLOCKED | Hard | ACTIVE + m3_health / m8_anomaly trigger / Sharpe collapse / 30d cumulative drawdown breach | 48h dwell → time_based INACTIVE（auto recovery）；OR operator manual unlock |

### 2.2 State transition graph（per overlay_type × scope 各自 1 個 SM）

```
              ┌─────────────────────────────────────────┐
              │                                         │
              ▼                                         │
   ┌────────────────────┐  signal detected (m11/m8 N/A) │
   │     INACTIVE       │ ───────────────────────────▶  │
   │  (LAL Tier 0)      │ ◀───────────────────────────  │
   └────────────────────┘  recover 15min dwell + COOLDOWN
            │             │                              │
            │             ▼                              │
            │   ┌─────────────────────────────┐          │
            │   │       WATCHING              │          │
            │   │     (LAL Tier 1)            │          │
            │   │  observer mode; no impact   │          │
            │   └─────────────────────────────┘          │
            │             │                              │
            │             │ signal sustained 1h dwell    │
            │             │ AND amplification gate PASS  │
            │             ▼                              │
            │   ┌─────────────────────────────┐          │
            │   │       ARMED                 │          │
            │   │     (LAL Tier 2)            │          │
            │   │  soft halt candidate; Y1 adv│          │
            │   └─────────────────────────────┘          │
            │             │                              │
            │             │ alpha sustained 6h dwell     │
            │             │ Y2: auto；Y1: operator once  │
            │             ▼                              │
            │   ┌─────────────────────────────┐          │
            │   │       ACTIVE                │          │
            │   │     (LAL Tier 3)            │          │
            │   │  production impact          │          │
            │   └─────────────────────────────┘          │
            │             │                              │
            │             │ m3_health DEGRADED           │
            │             │ OR m8_anomaly                │
            │             │ OR Sharpe < 0 30d sustained  │
            │             │ OR counterfactual diverge    │
            │             │ OR operator manual           │
            │             ▼                              │
            │   ┌─────────────────────────────┐          │
            │   │      COOLDOWN               │          │
            │   │    (LAL Tier 4 disabled)    │──────────┘
            │   │  close-only; 48h dwell      │
            │   └─────────────────────────────┘
            │             │
            │             │ 48h time_based dwell auto recovery
            │             │ OR operator manual unlock
            │             ▼
            └──────  INACTIVE
```

### 2.3 Dwell time + flap suppression（per M3 §3.3 範式）

每 transition 必有 dwell time + flap suppression，避免 signal 抖動觸發 state oscillation：

| Transition | Dwell time | Flap suppression |
|---|---|---|
| INACTIVE → WATCHING | 0（signal 首次檢測立即；observer mode 無風險） | 24h 內同 overlay 5 次 INACTIVE ↔ WATCHING transition → 自動 lock WATCHING 直到 1h 全 INACTIVE-band |
| WATCHING → ARMED | 1h 持續 signal sustained-band + amplification gate PASS | 24h 內同 overlay 3 次 WATCHING ↔ ARMED transition → 自動 lock ARMED 直到 4h 全 OK + operator manual override unlock |
| ARMED → ACTIVE | 6h alpha sustained + Y1: operator approve once / Y2: auto 5 gate PASS | 24h 內同 overlay 2 次 ARMED ↔ ACTIVE transition → 自動 lock ACTIVE 直到 12h 全 OK + operator manual unlock |
| ACTIVE → COOLDOWN | trigger 即時（m3_health / m8_anomaly catastrophic）；或 30d Sharpe < 0 sustained | 不可逆向自動降；COOLDOWN → ARMED/ACTIVE 需 operator manual unlock |
| COOLDOWN → INACTIVE | 48h dwell time_based 自動 | 不可短於 48h（auto recovery 必 conservative） |
| ACTIVE → ARMED | 6h signal weaken + counterfactual confirm | — |
| ARMED → WATCHING | 30min signal weak + recover dwell | — |
| WATCHING → INACTIVE | 15min signal disappear + recover dwell | — |

**Dwell time rationale**（per M3 §3.3 同精神 + M2 特化）：
- INACTIVE → WATCHING dwell 0 — observer mode 無 cascade，false alarm 成本零
- WATCHING → ARMED dwell 1h — soft halt candidate；reparam halt advisory 有 cost
- ARMED → ACTIVE dwell 6h — production impact；hard halt 對 strategy 直接影響；保護 priority
- ACTIVE → COOLDOWN immediate trigger（critical event）— 保護 priority per §二 原則 5 生存 > 利潤
- COOLDOWN → INACTIVE dwell 48h fix — 對齊 v5.8 §2 M2 "macro event 48h cooldown" 既有設計

**Flap suppression rationale**（per `feedback_first_detection_deadlock_pattern` 反模式教訓）：
- lock 一律有過期條件（1h / 4h / 12h 全 OK + operator manual unlock）
- 絕不創 dead state（`is_none()` guard + 無過期 auto-clear 反模式禁止）
- 每 lock 寫 V105 row + evidence_json 標 `lock_reason` + `lock_expires_at` + `lock_unlock_path`

### 2.4 Per-overlay-type SM 數量

| Overlay type | SM 數量 | scope key |
|---|---|---|
| macro | 1 single SM | strategy_id=NULL + symbol=NULL |
| onchain | 25 SM（5 strategy × 5 typical symbol；scope-by-symbol；strategy_id NULL OR per-strategy）| symbol（per-symbol granularity） |
| regime | 25 SM（5 strategy × 5 typical symbol；scope-by-(strategy, symbol)） | (strategy_id, symbol) |

system-level aggregate 不 emit（M2 sm 是 per-overlay-scope；strategy decision query 三層 aggregate per §1.4）。

---

## §3 5 Trigger_type 對應 V105 Schema

V105 schema `trigger_type` CHECK ENUM 5 值（per V105 spec §1.3）。本 spec § 3 對應 M2 行為定義；schema DDL 不重複（per V105 §2.1）。

### 3.1 Trigger_type semantic + V105 mapping

| trigger_type | 觸發 source | Authority module | V105 `trigger_source_id` 指向 | 典型 transition | counterfactual_log_ref UUID |
|---|---|---|---|---|---|
| `m3_health` | M3 HEALTH_DEGRADED state change event | M3（single health authority per CR-7 dedup contract） | `learning.health_observations.observation_id`（V106） | ACTIVE → COOLDOWN（任一 domain DEGRADED 自動觸發） | NULL（非 replay-driven） |
| `m11_divergence` | M11 replay divergence > NOISE_FLOOR | M11（single replay authority per CR-7 + ADR-0038） | `learning.replay_divergence_log.divergence_id`（V107） | WATCHING → ARMED（升階）；或 ARMED → COOLDOWN（降階 if divergence 反向） | **NOT NULL UUID**（指向 `replay_runs.replay_uuid` per ADR-0038 §Decision 5） |
| `m8_anomaly` | M8 anomaly emit | M8（single anomaly authority per CR-7 + ADR-0036） | `learning.anomaly_events.anomaly_id`（V109） | ARMED → COOLDOWN / ACTIVE → COOLDOWN（防雪球） | NULL（非 replay-driven） |
| `operator` | Operator Console manual toggle | Operator 人工 | `governance.audit_log.id`（V098） | 任意 transition（含 emergency 跳階） | NULL |
| `time_based` | Scheduled dwell-time auto transition | M2 自身 scheduler | NULL（無單一 source row） | COOLDOWN → INACTIVE 48h auto；或 WATCHING → INACTIVE 15min recover | NULL |

### 3.2 Per-trigger 行為差異

| trigger_type | 是否走 dwell time | 是否受 amplification cap | 是否走 LAL gate（per ADR-0034）| 反向觸發禁止對象 |
|---|---|---|---|---|
| `m3_health` | DEGRADED 即時觸發 COOLDOWN；不走 dwell（保護 priority）| 受 amplification cap（per §6.2 防 M8/M3 雙重觸發 cascade） | 直接 cascade（系統級 LAL Tier 降階）| M2 state change 不可反向 trigger M3 state（per §6.4） |
| `m11_divergence` | 走 dwell + flap suppression（防 replay 抖動）| 受 cap（per §6.2） | 走 LAL gate per ADR-0034 升階路徑 | M2 state change 不可反向 trigger M11 replay re-run |
| `m8_anomaly` | COOLDOWN 即時觸發；不走 dwell | 受 24h 1-anomaly cap（per ADR-0036 + M3 §6.2 範式）| 直接 cascade | M2 state change 不可反向 trigger M8 anomaly emit |
| `operator` | 不走 dwell（manual override 立即）| 不受 amplification cap | 走 LAL Tier 3-4 operator approve path | — |
| `time_based` | 走 dwell（schedule 本身就是 dwell）| 不受 cap | 不走 LAL gate（純定時器） | — |

### 3.3 `trigger_source_id` 軟連結維護

per V105 §1.3 + §2.4：5 trigger_type 對 5 個不同表 PK；schema-level 無 FK；application-side enforce referential integrity。

**M2 writer 責任**：
- INSERT V105 row 前必驗 `trigger_source_id` row 在對應 source table 存在
- INSERT 後若 source row 被 retention drop（如 V106 90d retention）→ M2 V105 row `trigger_source_id` dangling；保留不刪
- cross-ref query 用 LEFT JOIN 處理 dangling case（per V105 §8.7）

---

## §4 Counterfactual_log FK 與 evidence_json

每 transition 必 log entry 以保 audit traceability + reconstructable（per §二 原則 8 交易可解釋 + DOC-08 §12 #8 安全不變量）。

### 4.1 counterfactual_log_ref UUID 設計（per V105 spec §1.4）

| 場景 | counterfactual_log_ref | 寫 V105 row 必含 |
|---|---|---|
| `trigger_type='m11_divergence'`（M11 replay-driven）| **NOT NULL UUID**（指向 `learning.replay_runs.replay_uuid`） | 必 |
| 非 replay trigger（m3 / m8 / operator / time_based） | NULL allowed | 不必但建議 evidence_json 標 |

**M2 writer 強制**：trigger_type='m11_divergence' 時 counterfactual_log_ref 必非 NULL；application-side check + raise（per V105 schema 不強制 CHECK）。

### 4.2 evidence_json 必填欄位 per trigger_type

`evidence_json JSONB`（per V105 §2.1）；每 transition 必填以下基線：

| trigger_type | evidence_json 必填 key |
|---|---|
| `m3_health` | `domain`（如 'pipeline_throughput' / 'risk_envelope'）、`state`（'HEALTH_DEGRADED' 等）、`m3_transition_id` UUID（指向 M3 V106 transition_id 反查）、`reason_summary` |
| `m11_divergence` | `divergence_metric`（小數）、`noise_floor`（小數）、`replay_run_id`、`replay_window_start_ts` / `replay_window_end_ts`、`bootstrap_ci`（[low, high]）、（若 Sprint 5+）`statistical_significance` p-value |
| `m8_anomaly` | `severity`（'CRITICAL' / 'WARNING'）、`anomaly_id`（V109 PK 反查）、`anomaly_type`（per M8 spec）、`anomaly_window_minutes` |
| `operator` | `audit_log_id`（V098 PK 反查）、`operator_username`、`override_reason`（**必填** per AMD-2026-05-15-01 + Decision Lease cross-ref per §二 原則 3）、`override_target_state` |
| `time_based` | `scheduled_at`（trigger 排程時間）、`actual_at`、`dwell_elapsed_sec` |

### 4.3 dwell_sec 寫入語意

V105 column `dwell_sec INTEGER`（per V105 §2.1）：M2 writer 每次 INSERT V105 row 時填 state_from 上一次停留時間（秒）：

```
For state_from='ARMED' transition INSERT:
  dwell_sec = NOW() - (上次 INSERT V105 row 對應 strategy_id+symbol+overlay_type 的 transition_at)
  WHERE state_to='ARMED'
  ORDER BY transition_at DESC
  LIMIT 1
```

第一次觀測（INACTIVE → WATCHING；無前序 transition）→ dwell_sec NULL。

### 4.4 不寫 V105 row 的場景禁止

任何 M2 state evaluation（even no-op same-state observation）若導致**新 transition** → 必寫 V105 row。**禁止**：
- application-side 判斷 state_from == state_to 後**完全不寫**任何 audit trail
- per V105 §2.5：no-op 仍可寫 V105 row（state_from == state_to）+ evidence_json 標 `no_op_reason`
- 但典型 no-op observation（如 5min cron tick 發現 state 未變）**不必寫 row**（避免 V105 row volume 爆炸）

---

## §5 engine_mode 5 mode 差異

V105 `engine_mode` CHECK ENUM 5 值（per V105 §2.1）：`paper` / `demo` / `live_demo` / `live` / **`replay`**。

### 5.1 5 mode semantic

| engine_mode | 寫 V105 row 場景 | 影響 production decision？ | 進入 training filter？ | 進入 M1 LAL eligibility filter？ | 進入 mv 嗎？ |
|---|---|---|---|---|---|
| `paper` | paper engine M2 state observer（per 2026-04-16 paper 預設關閉 memory；OPENCLAW_ENABLE_PAPER=1 才寫）| 否 | 否 | 否 | 否 |
| `demo` | demo engine M2 state observer | 否 | 否 | 否 | 否 |
| `live_demo` | LiveDemo engine M2 state observer | **是**（LiveDemo 是 live 管線走 demo endpoint per memory `feedback_live_no_degradation_by_endpoint`）| 是（per CLAUDE.md §七 + MIT memory `IN ('live','live_demo')`）| 是 | 是 |
| `live` | Live engine M2 state observer | **是** | 是 | 是 | 是 |
| `replay` | M11 nightly replay engine 寫 counterfactual transition（per ADR-0038 §Decision 5 + CR-7 + V105 §2.3） | **否**（replay 不影響 production decision；只算 counterfactual signal） | **否**（不污染 training） | **否**（不算 production evidence） | **否**（mv WHERE engine_mode IN ('live','live_demo') 排除） |

### 5.2 為何 V105 比 V106 多 `replay` 值

per V105 §2.3：M11 nightly replay engine 必寫 counterfactual transition；該 row 必區分 live observation 與 counterfactual model 結果。

- V106 M3 health domain 是 live runtime observation；M11 replay 不寫 M3 row（M3 量測對象是真實 engine 進程/pipeline；replay engine 是分離進程，不算 M3 monitoring 對象）
- V105 M2 overlay state 是 transition event log；M11 replay-driven transition 是 counterfactual model 的必要 audit trail；必區分 live transition vs counterfactual transition

### 5.3 Training / Query filter 規約

per memory `feedback_demo_over_paper_for_edge` + `IN ('live','live_demo')` baseline + V105 §5.1：

```sql
-- 所有 M1 LAL eligibility query + Sharpe / DD 計算 + ML training filter 必排除 replay
-- 例：M1 LAL Tier 升階 eligibility 查 M2 overlay COOLDOWN-free 90d
SELECT COUNT(*) FROM learning.overlay_state_transitions
WHERE strategy_id = 'grid'
  AND symbol = 'BTCUSDT'
  AND state_to = 'COOLDOWN'
  AND transition_at > now() - INTERVAL '90 days'
  AND engine_mode IN ('live','live_demo');  -- ⚠️ 排除 replay

-- M11 replay engine 反向 query 自己的 counterfactual transition
SELECT * FROM learning.overlay_state_transitions
WHERE counterfactual_log_ref = $1
  AND engine_mode = 'replay';  -- ⚠️ 只看 replay row
```

### 5.4 mv 中 `replay` 過濾

per V105 §7.2 mv DDL：

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_overlay_state_per_strategy AS
SELECT DISTINCT ON (overlay_type, strategy_id, symbol)
    ...
FROM learning.overlay_state_transitions
WHERE engine_mode IN ('live','live_demo')   -- ⚠️ 不含 replay / paper / demo
ORDER BY overlay_type, strategy_id, symbol, transition_at DESC;
```

M11 replay-driven transition 不進 mv；strategy decision query 從 mv 拿 latest state（per §1.4 production wire）→ 不被 counterfactual 污染。

---

## §6 M2 ↔ M11 Integration（V107 divergence → overlay trigger）

per ADR-0038 M11 + CR-7 dedup contract + V105 §1.4 counterfactual_log_ref + 本 spec §3.1。

### 6.1 Integration contract

| M11 event | M2 reaction |
|---|---|
| Nightly replay divergence flag（small；divergence_metric < NOISE_FLOOR per ADR-0038）| 不 trigger transition；只在 evidence_json 標 audit |
| Nightly replay divergence flag（large；divergence_metric ≥ NOISE_FLOOR）| trigger M2 transition with trigger_type='m11_divergence' + counterfactual_log_ref UUID + evidence_json 含 bootstrap_ci |
| Daily replay divergence sustained 5 day（per M11 daily divergence event = M7 input 非 independent demote per CR-7） | 不直接 demote M2 state；但 evidence_json 累計 5d divergence trend；若 trend 持續 → 配合 §6.2 升階觸發 ARMED |
| Replay divergence 7d 連續 unack | per dispatch H-11：自動升 M2 WATCHING → ARMED；evidence_json 標 `unack_5d_escalation` |

### 6.2 M11 trigger 與 dwell time 協作

M11 nightly replay 觸發的 M2 升階 transition 仍走 §2.3 dwell time + flap suppression：

```
M11 emit divergence event D1 (divergence_metric=0.08, noise_floor=0.05)
  → M2 evaluate: state=WATCHING, signal sustained-band, dwell 1h?
    - If dwell achieved → INSERT V105 row state_from='WATCHING' state_to='ARMED' trigger_type='m11_divergence'
    - If dwell 未到 → record dwell start time + signal evidence；wait
  → M2 emit OverlayStateChangeEvent → 下游 M1 LAL + Conductor reaction
```

### 6.3 避免循環觸發

M2 state change **不可**反向 trigger M11 replay re-run：
- M11 replay schedule 由 nightly cron 主動觸發；不接收 M2 state change event
- M2 state change → 走 V105 INSERT 行為；M11 不訂閱 V105 INSERT trigger
- 若需 M2 ARMED → 加密 replay sampling（更頻繁 replay）→ 走 operator 手動指令 + M11 spec extension（非本 spec 範圍）

### 6.4 counterfactual_log_ref UUID 完整性

M2 writer 寫 V105 row trigger_type='m11_divergence' 時：

```python
def m2_write_m11_transition(replay_run_id, replay_uuid, divergence_metric, ...):
    # 1. 驗 replay_uuid 在 learning.replay_runs 中存在（application-side）
    if not exists_replay_run(replay_uuid):
        raise M2WriterError("M11 replay_uuid not found; refuse INSERT")
    # 2. INSERT V105 row
    insert_v105_row(
        trigger_type='m11_divergence',
        trigger_source_id=replay_run_id,
        counterfactual_log_ref=replay_uuid,  # NOT NULL
        evidence_json=jsonb_build({
            'divergence_metric': divergence_metric,
            'noise_floor': 0.05,
            'replay_run_id': replay_run_id,
            'bootstrap_ci': [low, high],
        }),
        engine_mode='replay' if replay_engine else 'live'
    )
```

---

## §7 M2 ↔ M3 Integration（HEALTH_DEGRADED → auto COOLDOWN）

per M3 spec §5.1 cascade table + §7 M3 ↔ M1 LAL integration 範式 + 本 spec §3.1。

### 7.1 Integration contract

| M3 state | M2 reaction |
|---|---|
| HEALTH_OK | 不 trigger M2 transition |
| HEALTH_WARN | 不 trigger M2 transition；M2 evidence_json 不需標 |
| HEALTH_DEGRADED（任一 domain） | trigger M2 ACTIVE → COOLDOWN（受影響 strategy / symbol）；不走 dwell time（保護 priority）；受 amplification cap（per §6.2 M3 spec + 本 spec §9.2）|
| HEALTH_CRITICAL（任一 domain）| trigger M2 任一 state → COOLDOWN（全部受影響 overlay）；不走 dwell；不受 amplification cap（critical 立即觸發）|

### 7.2 Per-M3-domain → M2 overlay scope mapping

| M3 domain | 影響的 M2 overlay scope |
|---|---|
| `engine_runtime` | 全部 overlay（system-level critical）|
| `pipeline_throughput` | 全部 overlay |
| `database_pool` | 全部 overlay |
| `api_latency` | 全部 overlay（與 Bybit 通信故障；交易能力受損）|
| `strategy_quality`（per-strategy） | 該 strategy 對應 regime overlay + onchain overlay（不影響 macro overlay） |
| `risk_envelope`（portfolio）| 全部 overlay（資金安全 priority）|

### 7.3 Hand-shake protocol

M3 ↔ M2 通信走 IPC message bus（per M3 spec §7.3 範式 + existing event_consumer mechanism）：

```
M3 emit: HealthStateChangeEvent {
  domain, old_state, new_state, transition_id (M3-side), timestamp,
  reason_summary, affected_strategy_id, affected_symbol
}
M2 subscribe: HealthStateChangeEvent
  → 內部 evaluate 受影響 overlay scope (per §7.2 mapping)
  → 對每個受影響 overlay INSERT V105 row:
    state_from=current, state_to='COOLDOWN',
    trigger_type='m3_health', trigger_source_id=M3-V106-observation_id,
    evidence_json={ 'domain': ..., 'state': 'HEALTH_DEGRADED', 'm3_transition_id': transition_id }
M2 emit: OverlayStateChangeEvent { overlay_type, scope, old_state, new_state, transition_id (M2-side) }
M3 subscribe: OverlayStateChangeEvent → 記 audit log；**不形成反向 trigger**（per §6.3 + M3 spec §7.3 反向觸發禁止）
```

### 7.4 Recovery cascade（M3 OK → M2 COOLDOWN release）

M3 state recover HEALTH_OK 後**不**自動 release M2 COOLDOWN：
- M2 COOLDOWN 走 §2.3 48h dwell time + time_based auto recovery
- 即使 M3 立即 OK，M2 維持 COOLDOWN 48h（**conservative recovery** per §二 原則 6）
- 若 operator 需 emergency release → 走 trigger_type='operator' manual unlock（per §3.1 + 本 spec §9.3）

---

## §8 M2 ↔ M1 LAL Integration（state change 走 LAL Tier 2-3；對齊 ADR-0034 LAL 0-4 數字越大越嚴）

per ADR-0034 LAL Tier 0-4 + 本 spec §1.2 + M3 spec §7 範式。

### 8.1 ADR-0034 LAL Tier 0-4 對齊（**數字越大越嚴**）

per ADR-0034 §LAL ↔ Stage 對齊矩陣：

| LAL Tier | 描述 | M2 state 對應 | M2 state change 觸發 LAL 嗎 |
|---|---|---|---|
| LAL 0 | per-fill（always autonomous Guardian path）| INACTIVE | M2 INACTIVE → WATCHING transition **不**走 LAL（observer mode 無 production impact）|
| LAL 1 | intra-strategy reparam（Stage 4 + 30d stable autonomous）| WATCHING | M2 WATCHING transition 不走 LAL（仍 observer）|
| LAL 2 | cross-strategy reweight（Y1 Advisory / Y2 Auto with gate）| ARMED | **M2 → ARMED transition 寫入 LAL Tier 2 reparam halt 決策路徑**（advisory only Y1） |
| LAL 3 | new strategy promotion（always operator approve）| ACTIVE | **M2 → ACTIVE transition Y1 必 operator approve once**；Y2 only auto with 5 gate |
| LAL 4 | capital structure / venue change（always operator approve）| COOLDOWN | **M2 → COOLDOWN transition 即時自動**（per §2.1 保護 priority；不需 operator approve；但 release 必 operator manual unlock if pre-48h）|

**關鍵**：LAL Tier 4（COOLDOWN）對齊 disabled-auto；數字最大；保護最嚴。**ADR-0034 "數字越大越嚴" 與 v5.7 早期某些文檔可能看到的「Tier 0 = 最嚴」反向**；本 spec 嚴格遵守 ADR-0034 v2026-05-21 D2 已批本（LAL 0 = autonomous baseline / LAL 4 = strictest gate）。

### 8.2 LAL Tier 降階與 M2 state change 對齊

per ADR-0034 §Decision 5 LAL 1+2 auto-approve eligibility gate + M3 spec §7.2 LAL Tier 降階規則：

| LAL Tier 降階規則 | M2 觸發 |
|---|---|
| Tier 1 reparam auto-approve 受 M2 影響 | M2 任一 overlay ACTIVE（per §2.1 strategy decision 影響） + Sharpe 30d sustained < 0 → LAL 1 auto-approve disable for that strategy |
| Tier 2 cross-strategy auto-approve 受 M2 影響 | M2 macro/onchain ARMED + portfolio 對 reweight 提案 → LAL 2 auto-approve 強制 advisory |
| Tier 3 new strategy promotion | M2 macro/onchain regime ACTIVE 期間 LAL Tier 3 promotion blocked（新策略不准在 ACTIVE overlay 期間 promote）|

### 8.3 Hand-shake protocol

```
M2 emit: OverlayStateChangeEvent {
  overlay_type, strategy_id, symbol, old_state, new_state,
  trigger_type, transition_id (M2-side), counterfactual_log_ref?,
  reason_summary
}
M1 LAL subscribe: OverlayStateChangeEvent
  → 內部維護 active overlay state cache（key: (strategy_id, symbol, overlay_type)）
  → 評估 LAL Tier 1/2 auto-approve eligibility:
    - 若任一 overlay state ∈ {ARMED, ACTIVE, COOLDOWN} → LAL 1 disable for affected scope
    - 若任一 overlay state == COOLDOWN → LAL 2 disable for affected scope
M1 LAL emit: LALTierChangeEvent { strategy_id, old_tier, new_tier, transition_id (refer M2 transition_id), reason }
M2 subscribe: LALTierChangeEvent → 記 audit log；**不形成反向 trigger**（per §6.3 + M3 §7.3 範式）
```

### 8.4 LAL eligibility query 路徑

per V105 §8.3 範例 query + 本 spec §1.4：

```sql
-- 例 1: M1 LAL Tier 1 升階 eligibility 必查 90d COOLDOWN-free
SELECT COUNT(*) FROM learning.overlay_state_transitions
WHERE strategy_id = 'grid'
  AND symbol = 'BTCUSDT'
  AND state_to = 'COOLDOWN'
  AND transition_at > now() - INTERVAL '90 days'
  AND engine_mode IN ('live','live_demo');
-- > 0 → LAL Tier 1 升階 eligibility fail

-- 例 2: M1 LAL Tier 2 reparam halt 即時查當前 overlay state（μs 級 mv path）
SELECT current_state, latest_transition_at
FROM learning.mv_latest_overlay_state_per_strategy
WHERE overlay_type = 'regime'
  AND strategy_id = 'grid'
  AND symbol = 'BTCUSDT';
-- current_state IN ('ARMED','ACTIVE','COOLDOWN') → LAL Tier 2 reparam halt
```

---

## §9 反向 Attack Mitigation（per H-11 #2 M2 false anomaly cascade）

per PA dispatch consolidation §H-11 反向 attack 6 條 follow-up + AMD-2026-05-15-01 mitigation + M3 spec §6 amplification loop cap 範式。

### 9.1 6 條反向 attack 場景 + mitigation

| # | 反向 attack 場景 | Mitigation |
|---|---|---|
| 1 | **M2 false anomaly cascade**：M8 emit false anomaly burst → M2 連續 COOLDOWN 多個 overlay → strategy 全 halt | per §9.2 amplification cap（24h 1-anomaly = 1-transition；per ADR-0036 + M3 spec §6.2 同 pattern） |
| 2 | **healthy market burst → 誤 disable overlay**（M2 reverse attack item per v5.8 §11 line 890）| M2 auto-disable 條件嚴格 = Sharpe < 0 AND counterfactual diverge AND 30d sustained；**單一 burst 不觸發**（per v5.8 §11 explicit mitigation）|
| 3 | M11 replay false-positive divergence → M2 連續 ARMED | per §9.4 多訊號合議：m11_divergence 升 ARMED 需 + signal sustained 1h dwell + amplification cap |
| 4 | M3 false HEALTH_DEGRADED → M2 全 overlay COOLDOWN | per M3 spec §6.2 M3-side amplification cap（M3 state change rate cap）+ M2 受 M3 cascade 不再二次 cap；M3 already capped |
| 5 | Operator misclick / fat-finger Console manual override 連續觸發 | operator trigger 必填 `override_reason`（per §4.2 evidence_json）+ Decision Lease cross-ref（per §二 原則 3）+ 24h undo（per ADR-0034 §Decision 4） |
| 6 | M11 passive divergence report 5d unack → operator 忽略 → 系統無 escalation | per dispatch H-11 #6：5d unack 自動升 M3 HEALTH_WARN（per M3 spec §8.1）；M3 HEALTH_WARN 不直接觸 M2 cascade（per §7.1）；但 7d unack 升 HEALTH_DEGRADED → 觸發 M2 COOLDOWN cascade |

### 9.2 Amplification cap rules（per M3 spec §6.2 範式 + M2 特化）

| Rule | 規範 |
|---|---|
| **M8 1-anomaly = max 1 M2 transition / 24h** | M2 接收 M8 anomaly event 觸發 transition 後，同 `anomaly_type` + 同 overlay scope 在 24h 內不再觸發 transition（per ADR-0036 Decision 1 例外段 + M3 spec §6.2） |
| **M11 1-divergence = max 1 M2 升階 transition / 12h** | M11 divergence 觸發 M2 升階（WATCHING→ARMED 或 ARMED→ACTIVE）後，同 `replay_run_id` 在 12h 內不再觸發升階；防 nightly replay 多次 emit 同一 divergence 累積觸發 |
| **M2 自身 state change rate cap** | M2 per-overlay-scope state change rate 硬 cap：5 次 / 1h；超過 cap 自動 freeze 當前 state + Slack CRITICAL alert + operator manual unlock |
| **Cascade depth cap** | 單次 M3 HEALTH_DEGRADED cascade 觸發的 M2 transition 數量硬 cap：50 個 transition（全 overlay scope 上限約 51）；超過 cap 截斷 + log warning + operator review |
| **Anomaly source identity** | M8 / M11 event 必帶 `anomaly_id` / `replay_run_id`；M2 內部維護 24h / 12h rolling cache → 同 source 24h/12h 內僅 1 次升階 |
| **Fail-open prevention** | amplification cap 觸發後不自動釋放——必 operator manual unlock；防 fail-open（per §二 原則 6 失敗默認收縮） |

### 9.3 Operator manual unlock 路徑

per AMD-2026-05-15-01 + ADR-0034 §Decision 4 LAL undo + §二 原則 3 Decision Lease：

```
Operator unlock COOLDOWN (pre-48h auto-recovery):
  1. Console 觸發 unlock action
  2. 系統 emit Decision Lease emit event (lease_id + payload_hash + lal_level=4)
  3. Operator 必填 override_reason
  4. LAL Tier 4 operator approve required（per ADR-0034 §LAL ↔ Stage 矩陣）
  5. Approve 後 → M2 INSERT V105 row state_to='INACTIVE'（or operator-specified target state）
  6. evidence_json = { 'audit_log_id': ..., 'operator_username': ..., 'override_reason': ..., 'override_target_state': 'INACTIVE' }
  7. 24h undo window open（per ADR-0034 §Decision 4）
```

### 9.4 多訊號合議（多 signal aggregator 降 false-positive）

M2 升階 transition 不依賴單一 trigger；強制 multi-signal aggregator：

| 升階目標 | 必要 signal aggregator |
|---|---|
| WATCHING → ARMED | (signal sustained 1h dwell) AND (amplification gate PASS) |
| ARMED → ACTIVE | (alpha sustained 6h dwell) AND (Y1: operator approve; Y2: 5 gate PASS) |
| ACTIVE → COOLDOWN | (m3_health DEGRADED) OR (m8_anomaly) OR (Sharpe<0 30d) OR (counterfactual diverge 7d sustained) OR (operator)；**任一 trigger 直接觸發**（保護 priority） |
| COOLDOWN → INACTIVE | (48h dwell time_based) OR (operator manual unlock) |

降階 / COOLDOWN 進入是 **single signal trigger**（保護 priority；per §二 原則 5）；升階是 **multi signal aggregator**（保守 + 防 false-positive；per §二 原則 6）。

---

## §10 Acceptance Criteria（7 條 sign-off 標準）

Sprint 5 Tier 1 IMPL 完成時必 PASS 全 7 條（per M3 spec §10 範式）：

| AC-# | Acceptance criteria | Verification method |
|---|---|---|
| **AC-1** | 5 state × 3 overlay_type proptest 完整性（state transition 窮舉 + invalid transition rejected + dead-state scan + `is_none()` reset auto-clear 反模式 scan per dispatch H-14）| E4 `cargo test` proptest harness per dispatch H-14 |
| **AC-2** | Dwell time validation：mock signal sequence（WATCHING-band 持續 30min, 1h, 2h）驗 1h threshold 觸發 WATCHING → ARMED transition；mock alpha sequence 6h 驗 ARMED → ACTIVE | E4 unit test + integration test |
| **AC-3** | Flap suppression validation：24h 內同 overlay 3 次 WATCHING ↔ ARMED transition → 第 4 次 lock ARMED；4h 全 OK + operator unlock 才能 release | E4 integration test + 24h simulated time |
| **AC-4** | Cascade chain test：M3 HEALTH_DEGRADED → 觀察 M2 全 overlay COOLDOWN + cascade rollback 48h 後 INACTIVE → 全部復原；OR operator manual unlock | E4 integration test + M3 mock + M1 LAL mock |
| **AC-5** | Amplification cap test：M8 emit 5 同 anomaly_type / 1min → 只觸發 1 次 M2 transition；M11 emit 3 同 replay_run_id / 6h → 只觸發 1 次 M2 升階 | E4 integration test + M8 mock + M11 mock |
| **AC-6** | counterfactual_log_ref UUID 完整性：trigger_type='m11_divergence' 寫 V105 row 時 counterfactual_log_ref 必非 NULL；application-side reject 驗 | E4 integration test + V105 INSERT mock |
| **AC-7** | engine_mode 5 mode 隔離：replay engine 寫 row 必 engine_mode='replay'；mv 不含 replay row；M1 LAL eligibility query filter `IN ('live','live_demo')` PASS | E4 integration test + V105 schema verify + mv DDL verify |

額外（推薦但非阻塞）：
- AC-8（Sprint 7 Tier 2 IMPL）：Advisory alerting × overlay state matrix Slack mock verify
- AC-9（Y2+ Active）：M2 auto-enable 5 gate eligibility evaluation harness（per v5.8 §2 M2 lines 108-112）

---

## §11 IMPL Phase Split

### 11.1 Tier 1 — Read-only logger（Sprint 5）

per v5.8 §2 M2 lines 114-118 + V105 §15.1 Sprint 1A-γ schema prereq closure：

| Item | Sprint | Workload | 行為 |
|---|---|---|---|
| V105 schema land + Guard A/C + hypertable + idempotency | 1A-γ | per V105 spec full DDL（已 land 由 MIT 主責） | — |
| M2 state machine 5 state evaluator（per-overlay-type SM；dwell time + flap suppression） | 5 | 40-60 hr | read-only：observe overlay signal + log V105 transition；**不影響 strategy decision** |
| Counterfactual logger hook（per v5.8 line 116 "+10 hr"）| 5 | 10-20 hr | M11 replay-driven transition 寫 V105 row + engine_mode='replay' |
| mv_latest_overlay_state_per_strategy refresh cron（per V105 §7）| 5 | 10-20 hr | 5min cron CONCURRENTLY refresh；失敗 healthcheck（per V105 §14.2 caveat 7） |
| AC-1..3 PASS verify | 5 | per E4 regression | proptest + dwell time + flap suppression |

Sprint 5 Tier 1 結束時 M2 為 **read-only state observer**；strategy decision 不受 M2 影響（per §1.4 production wire 在 Sprint 7+ 才 enable）。

### 11.2 Tier 2 — Advisory（Sprint 7-8）

| Item | Sprint | Workload | 行為 |
|---|---|---|---|
| M2 → M3 / M11 / M8 cascade trigger wire | 7 | 40-60 hr | m3_health / m11_divergence / m8_anomaly trigger 真實 INSERT V105 row + emit OverlayStateChangeEvent |
| M2 → M1 LAL Tier 1+2 eligibility query 接口（per §8.4） | 7 | 30-40 hr | M1 LAL 查 mv 即時 query + 90d COOLDOWN-free query |
| Amplification cap（per §9.2 6 rules）| 7 | 30-40 hr | M8 1-anomaly / M11 1-divergence cap；M2 self rate cap；fail-open prevention |
| Advisory alerting × overlay state matrix（Slack + Console badge）| 7 | 30-40 hr | per M3 spec §9 範式 + M2 特化（macro/onchain/regime 區分 alert）|
| Operator manual unlock path（per §9.3 + ADR-0034 LAL Tier 4 approve）| 8 | 20-30 hr | Console 觸發 + Decision Lease + override_reason 必填 |
| AC-4..7 PASS verify | 8 | per E4 regression | cascade + amplification + counterfactual UUID + engine_mode 隔離 |
| A3 Monthly Review M2 panel（per M3 spec §11.2 範式）| 8 | 16-24 hr A3 | M2 state matrix + transition history + amplification cap trigger log |

Sprint 7-8 Tier 2 結束時 M2 為 **advisory module**：state change → emit event → 下游 module（M1 LAL / Conductor）參考但**不強制** strategy halt；strategy decision 仍由 strategy 內部邏輯主導。

### 11.3 Y2+ — Auto-enable / auto-disable（Y2 Q1）

per v5.8 §2 M2 lines 108-112 + line 118 "Y2 Q1: Auto-enable evaluation framework IMPL (30-50 hr)"：

| Item | Sprint | Workload | 行為 |
|---|---|---|---|
| Auto-disable 5 trigger active（per v5.8 lines 102-106）| Sprint 8-10 | 40-60 hr | (a) Sharpe < 0 + counterfactual diverge / (b) M8 anomaly + drawdown / (c) macro event FP > 3/90d / (d) operator inactivity > 60d failsafe / (e) hard ACTIVE → COOLDOWN trigger |
| Auto-enable 4 gate framework（per v5.8 lines 108-112；Y2 only + operator opt-in via Console toggle）| Y2 Q1 | 30-50 hr | (a) counterfactual t-stat ≥ 1.5 sustained 60d / (b) sample size ≥ 30 events / (c) no regime shift / (d) Allocator proposal approval rate > 80% 6mo |
| M2 strategy decision wire（per §1.4 production wire）| Y2 Q1 | 20-30 hr | strategy decision 進 Guardian 前查 M2 mv；ACTIVE/COOLDOWN strategy 走 close-only |

Y2+ 結束時 M2 為 **fully autonomous** module：auto-disable always-on（per v5.8 line 121 forgetfulness mitigation）；auto-enable 需 operator Console opt-in。

---

## §12 Cross-V### Dependency + Open Questions

### 12.1 Direct dependency

| V### | Role | Dependency direction | Sprint |
|---|---|---|---|
| **V105** | M2 own schema（已 land 由 MIT 主責；hypertable + 3 indexes + mv + Guard A/C） | M2 直接 owner | 1A-γ（已 land） |
| V107 | M11 replay_runs（M2 counterfactual_log_ref UUID cross-ref；per V105 §1.6） | M2 read-only consume；不寫 V107 | 1A-γ FIRST（per V105 §15.2 必先 V105 land） |
| V112 | M1 LAL tier table（M2 publish OverlayStateChangeEvent → M1 LAL Tier 1/2 eligibility）| M2 publish；M1 LAL consume | 1A-ε（per V105 §15.2 sequence） |
| V106 | M3 health_observations（M2 read-only consume → m3_health trigger） | M2 read-only consume；不寫 V106 | 1A-β（已 land 由 MIT 主責） |
| V109 | M8 anomaly_events（M2 read-only consume → m8_anomaly trigger） | M2 read-only consume；不寫 V109 | 1A-δ |
| 既有 V### | governance.audit_log（V098；operator trigger 反查） | M2 read-only consume | — |

### 12.2 Cross-V### sequencing

per V105 §15.2 + PA dispatch consolidation §6 cross-V### dependency graph：

```
V096 → V097 → V098 → V106 (M3) → V107 (M11) → V105 (M2 schema) → V109 (M8) → V112 (M1 LAL)
                          ↓             ↓
                      M3 ↔ M2     M11 ↔ M2
                      cross-ref   counterfactual_log_ref
```

V105 schema 已 land（Sprint 1A-γ SECOND）；M2 module IMPL 在 Sprint 5（Tier 1）+ Sprint 7-8（Tier 2）+ Y2+（Active）。

### 12.3 Open questions（≥ 3 條）

#### Q1 — Per-overlay-scope SM 數量（macro 1 + onchain 25 + regime 25 = 51）的 watchdog 監測機制

當前設計：每 overlay scope 維護獨立 SM；M2 自身 watchdog 必能監測 51 個 SM 的活性（per `feedback_no_dead_params` 教訓——可調參數禁止假功能）。

**問題**：51 個 SM 中若某 (strategy, symbol) 從未有 signal 觸發 → 該 SM 永久 INACTIVE；如何區分「真的 INACTIVE」vs「SM dead unable to evaluate」？

**Mitigation 候選**：每 SM 必有 last_eval_at timestamp + watchdog 5min cron 驗 last_eval_at 不超過 sample frequency × 2（如 regime 5min sample → last_eval_at 不超過 10min）。

**Owner**：CC + E5 + PA Sprint 5 Tier 1 IMPL 前 confirm。

#### Q2 — Operator inactivity 60d failsafe（per v5.8 line 106）的監測機制

當前設計：operator inactivity > 60d → 自動 rollback overlay 至 ADVISORY（按 v5.8 §2 M2 line 106 設計）。

**問題**：「operator inactivity」如何量化？是「無 Console login 60d」還是「無 Console action 60d」還是「無 Decision Lease approve 60d」？三者語意不同。

**Mitigation 候選**：採「無 Decision Lease approve OR override 60d」（最嚴；行為基準而非 presence 基準）。

**Owner**：CC + QA + Operator Sprint 5 Tier 1 IMPL 前 confirm。

#### Q3 — Y2 auto-enable 5 gate 中「Allocator proposal approval rate > 80% in last 6mo」如何度量

當前設計：per v5.8 §2 M2 line 112 列為 4 gate 之一；但 Allocator 路徑在 v5.7 Sprint 8 才設計，metric 尚未 land。

**問題**：approval rate 度量 baseline 從何時起？是 Y1 末 6mo？還是 Y2 開始後 6mo（造成 Y2 Q1 enable evaluation 不能用，須等 Y2 Q3+）？

**Mitigation 候選**：採「Y1 末（Y2 Q1 前 6mo）approval rate」為 baseline；若 baseline < 80% → 直接 reject Y2 auto-enable，不可重評。

**Owner**：QC + FA Y2 Q1 IMPL 前 confirm。

#### Q4 — M11 replay 觸發 M2 升階時的 statistical significance 要求

當前設計：trigger_type='m11_divergence' 升階只需 divergence_metric ≥ noise_floor（per V105 §8.4 example）+ §6.2 dwell + amplification cap。

**問題**：divergence_metric ≥ noise_floor 是 **point estimate** 比較；應否要求 bootstrap CI 下界 > noise_floor 才升階？per ADR-0038 + per dispatch C9 統計嚴格性。

**Mitigation 候選**：升階 ARMED 需 divergence_metric point ≥ noise_floor；升階 ACTIVE 需 bootstrap CI 下界 > noise_floor + sample size ≥ 30 events（per v5.8 §2 M2 line 110 already requires）。

**Owner**：QC + MIT Sprint 5 Tier 1 IMPL 前 confirm。

#### Q5 — replay engine 寫 V105 row 與 live engine 寫 V105 row 的 PID isolation

當前設計：engine_mode='replay' 區分 counterfactual transition vs live transition；但兩者寫同一 V105 hypertable。

**問題**：M11 nightly replay engine（獨立進程）若 crash → 寫一半的 row 是否 leak？需 transaction wrap；replay 對 V105 hypertable 的 write privilege 是否與 live engine 隔離？

**Mitigation 候選**：M11 replay engine 走獨立 PG role（per `OPENCLAW_REPLAY_ROLE`）；INSERT 走 transaction；V105 schema 不需 schema-level 限制（per engine_mode CHECK 已隔離 query side）。

**Owner**：E3 + PA Sprint 5 Tier 1 IMPL 前 confirm。

### 12.4 §二 16 根原則合規確認

per M3 spec §13 範式 + DOC-08 §12 9 安全不變量：

| # | 原則 | 是否相容 | M2 對應設計 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M2 不創 order 寫入口；overlay state change → strategy decision 影響經 Guardian + Conductor 既有單一寫入口 |
| 2 | 讀寫分離 | ✅ | M2 自身僅讀 signal source + 寫 V105 audit row；不寫 trading state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M2 state change → cascade action 經 M1 LAL + Conductor + 既有 5-gate；operator manual override 必走 Decision Lease（per §9.3） |
| **4** | **策略不繞風控** | ✅ | M2 ACTIVE/COOLDOWN 影響 strategy decision **前** 必走 Guardian（per §1.4 production wire）；不創新風控繞道 |
| 5 | 生存 > 利潤 | ✅ | §2.3 ACTIVE → COOLDOWN immediate trigger 保護 priority；§9.4 降階是 single signal trigger |
| 6 | 失敗默認收縮 | ✅ | §9.2 amplification cap fail-open prevention；§2.3 升階是 multi-signal aggregator |
| 7 | 學習 ≠ live | ✅ | M2 engine_mode='replay' 隔離 counterfactual transition；不污染 live strategy state |
| 8 | 交易可解釋 | ✅ | §4 evidence_json 必填 + V105 audit row + transition_id 可 audit reconstruct |
| 9 | 雙重防線 | ✅ | M2 不替代 5-gate kill；M3 / M8 既有 cascade 並行；本地 M2 + Bybit conditional order 雙重防線 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | signal value = 事實；state transition = 推論；amplification cap 設計 = 假設待 RCA 驗 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | M2 SM 自主升降 state；cascade action 在 P0/P1 既有風控邊界內；不擴 |
| 12 | 行為由 evidence 演化 | ✅ | counterfactual_log_ref + evidence_json 30d block bootstrap 估計（per ADR-0038）；不寫死 |
| **13** | **cost 感知** | ✅ | M2 signal source 採樣 5min 為主（regime）/ hourly（onchain）/ event-driven（macro）；不 hot path；不新增 LLM cost |
| 14 | 零外部成本 | ✅ | M2 signal source 全 self-compute（macro event public schedule + onchain free RPC + regime indicator）；不依賴付費 external service |
| 15 | 多 agent 形式化協作 | ✅ | M2 + M3 + M11 + M8 + M1 LAL + Conductor 各有明確 message contract（per §6 / §7 / §8）；不暗交互 |
| **16** | **Portfolio > 孤立 trade** | ✅ | M2 macro overlay scope=all strategy × all symbol（portfolio-level）；對齊 §16 portfolio risk 原則 |

---

## §13 Cross-References

- **v5.8 主檔 §2 M2 Overlay**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md:89-121`
- **V105 schema spec full DDL**（已 land）：`srv/docs/execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md`
- **M3 spec 17-section 範式 + cascade 範式**：`srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`
- **ADR-0034 LAL Tier 0-4 對齊**：`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 0 = autonomous baseline；LAL 4 = strictest gate；**數字越大越嚴**）
- **ADR-0036 M8 + M10 Tier D**：`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（amplification loop cap 1-anomaly = 1-state-change/24h）
- **ADR-0038 M11 Continuous Counterfactual Replay**：`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（counterfactual_log_ref UUID + engine_mode='replay' 出處）
- **PA dispatch consolidation §6 + §H-11**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（反向 attack 6 條 follow-up + cross-V### dep graph）
- **AMD-2026-05-15-01 + AMD-2026-05-21-01**：operator forgetfulness mitigation + autonomy-vs-human-final-review；M2 forgetfulness mitigation 對齊
- **CLAUDE.md §五 Architecture Pointers + §Hard Boundaries**：stable architecture routing + 16 根原則合規 baseline
- **`feedback_first_detection_deadlock_pattern` memory**：`is_none()` guard + 無過期 auto-clear 反模式禁止；M2 lock 必有過期條件
- **`feedback_no_dead_params` memory**：M2 51 SM 必真實被 healthcheck 監測；watchdog last_eval_at + 5min cron 驗
- **`feedback_demo_over_paper_for_edge` memory**：training filter `IN ('live','live_demo')` 排除 replay
- **`feedback_live_no_degradation_by_endpoint` memory**：LiveDemo 是 live 管線；M2 live_demo state 與 live state 同等對待
- **`feedback_env_config_independence` memory**：三環境風控 config 獨立；M2 threshold per-engine_mode 獨立評估
- **dispatch H-10 量化 threshold**：M2 dwell time / amplification cap / Sharpe threshold / counterfactual divergence threshold 量化 follow-up
- **dispatch H-11 反向 attack mitigation**：6 條 reverse attack + 5d/7d unack auto-escalate
- **dispatch H-12 灰度事件嚴重度對照表**：M2 COOLDOWN 對應 CRITICAL alert routing
- **dispatch H-14 STATE-MACHINE-TEST**：5 state × 3 overlay_type proptest 窮舉 + dead-state scan + `is_none()` reset auto-clear 反模式 scan
- **dispatch H-18 cross-language 1e-4 容差 fixture**：M2 state evaluation Rust + Python 共用 fixture harness

---

## §14 Engineering Scope Summary

| Phase | Sprint | Item | Workload |
|---|---|---|---|
| DESIGN | 1A-γ | M2 module spec doc（本 spec） | 12-20 hr |
| DESIGN | 1A-γ | V105 schema spec full DDL（已 land 由 MIT 主責） | per V105 spec 主責 70-100 hr |
| Tier 1 IMPL | 5 | M2 5-state evaluator + dwell time + flap suppression | 40-60 hr |
| Tier 1 IMPL | 5 | Counterfactual logger hook（M11 replay 寫 V105 row + replay engine_mode） | 10-20 hr |
| Tier 1 IMPL | 5 | mv refresh cron + healthcheck | 10-20 hr |
| Tier 2 IMPL | 7 | M2 → M3 / M11 / M8 cascade trigger wire | 40-60 hr |
| Tier 2 IMPL | 7 | M2 → M1 LAL Tier 1+2 eligibility query 接口 | 30-40 hr |
| Tier 2 IMPL | 7 | Amplification cap（6 rules） | 30-40 hr |
| Tier 2 IMPL | 7 | Advisory alerting × overlay state matrix | 30-40 hr |
| Tier 2 IMPL | 8 | Operator manual unlock path + LAL Tier 4 approve | 20-30 hr |
| Tier 2 IMPL | 8 | A3 Monthly Review M2 panel | 16-24 hr A3 |
| Y2+ | Sprint 8-10 | Auto-disable 5 trigger active | 40-60 hr |
| Y2+ | Y2 Q1 | Auto-enable 4 gate framework + Console opt-in toggle | 30-50 hr |
| Y2+ | Y2 Q1 | M2 strategy decision wire（production wire per §1.4） | 20-30 hr |
| **Total Y1** | — | DESIGN + Tier 1 + Tier 2 | **268-414 hr** + V105 schema |
| **Total Y2+** | — | Auto-disable + auto-enable + production wire | **90-140 hr** |

---

## §15 Risk / Blockers / Operator Decisions

### 15.1 Risk

| Risk | Mitigation |
|---|---|
| V105 schema 已 land 但 51 個 SM watchdog 機制未確認 → SM 假活 | per Q1 last_eval_at + 5min cron + healthcheck mandate |
| M11 replay-driven transition 與 live transition 寫同一 V105 hypertable → schema isolation 不嚴 | per Q5 PG role isolation + engine_mode CHECK + mv WHERE filter |
| 51 SM × 5 state × 5 trigger_type 組合爆炸 → proptest 覆蓋不全 | per AC-1 proptest 窮舉 + dead-state scan + dispatch H-14 mandate |
| Amplification cap 過嚴致漏報真實 critical | per §9.2 fail-open prevention；critical 立即觸發不受 cap |
| Operator inactivity 60d 度量歧義 | per Q2 採「無 Decision Lease approve OR override 60d」最嚴語意 |
| Y2 auto-enable 4 gate 中 Allocator approval rate baseline 缺漏 | per Q3 採 Y1 末 6mo baseline；若 < 80% reject |
| M11 divergence ≥ noise_floor point estimate 觸發升階致 false-positive | per Q4 升階 ACTIVE 需 bootstrap CI 下界 > noise_floor |
| ADR-0034 LAL 數字越大越嚴 與 v5.7 早期文檔可能反向理解 | 本 spec §8.1 明示嚴格遵守 ADR-0034 v2026-05-21 D2 已批本 |

### 15.2 Blockers

| Blocker | Resolution |
|---|---|
| V105 spec full DDL（已 land 由 MIT 主責；Sprint 1A-γ） | 已解 |
| V107 (M11) replay_runs.replay_uuid column type 確認（UUID vs TEXT） | per V105 §14.1 caveat 6；MIT + PA cross-confirm Sprint 1A-γ 末 |
| ADR-0034 final commit（"Proposed-pending-commit" 狀態）| Sprint 1A-β 同時段並行；PA + CC + QA 主責 |
| ADR-0038 M11 已 land（V105 spec §1.4 + 本 spec §3.1 cross-ref 可用） | 已解 |
| M3 spec land（本 spec §7 integration contract cross-ref） | 已解（M3 spec 同時段 Sprint 1A-β land） |
| H-10 量化 threshold（dwell time / amplification cap / Sharpe threshold 數值）| per V105 §4.2 block bootstrap 估計；Sprint 5 Tier 1 IMPL 前 land |
| H-11 反向 attack 6 條 mitigation 完整 cross-ref | 本 spec §9.1 已 6 條對應；待 PM sign-off |

### 15.3 Operator decision points

per v5.8 §12 operator decision pattern + M3 spec §17.3 範式：

- **D1**：Q1 — 51 SM watchdog 機制是否採 last_eval_at + 5min cron + healthcheck mandate？是否需 Sprint 5 IMPL 前 ADR 級 commit？
- **D2**：Q2 — operator inactivity 60d failsafe 採「無 Decision Lease approve OR override」最嚴語意確認
- **D3**：Q3 — Y2 auto-enable Allocator approval rate baseline 採 Y1 末 6mo；若 < 80% reject 確認
- **D4**：Q4 — M11 divergence 升階 ACTIVE 需 bootstrap CI 下界 > noise_floor + sample size ≥ 30 events 確認
- **D5**：Q5 — M11 replay engine PG role isolation 採 `OPENCLAW_REPLAY_ROLE` 確認

---

## §16 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 M2 spec | PM | Sprint 1A-γ M2 DESIGN closure | P0 |
| Reconcile cross-spec dependency（M3 spec §7 + ADR-0034 + ADR-0038 + V105 spec final cross-ref resolve）| PA | Sprint 1A-γ pre-dispatch | P0 |
| Q1-Q5 operator decision land | PM + Operator | Sprint 1A-γ pre-dispatch | P0 |
| H-10 量化 threshold（M2 部分；dwell time / amplification cap / Sharpe / counterfactual divergence）block bootstrap 估計 | QC + MIT | Sprint 5 Tier 1 pre-IMPL | P1 |
| Sprint 5 Tier 1 IMPL kickoff：派 E1 寫 M2 5-state evaluator + counterfactual logger hook + mv refresh cron | PM | Sprint 5 IMPL | P1 |
| Sprint 7-8 Tier 2 IMPL kickoff：cascade trigger wire + amplification cap + advisory alerting + operator unlock | PM | Sprint 7-8 IMPL | P2 |
| Y2 Q1 auto-enable 4 gate framework + Console opt-in toggle 派發 | PM | Y2 Q1 | P3 |

### 16.1 Sprint 1A-γ M2 DESIGN closure 標誌

本 spec PM sign-off + Q1-Q5 operator decision land + cross-spec final reconcile（M3 spec + ADR-0034 + ADR-0038 + V105 spec）→ Sprint 1A-γ M2 DESIGN 解除 → Sprint 5 Tier 1 IMPL kickoff。

### 16.2 與 sister-module DESIGN spec 對齊

per PA dispatch consolidation §Sprint 1A-γ + §跨 module dependency：

| Sister module | 對齊點 | Status |
|---|---|---|
| M3 spec | §7 cascade table M2 HEALTH_DEGRADED → COOLDOWN | M3 spec land；本 spec §7 cross-ref OK |
| M11 spec | §6 m11_divergence trigger + counterfactual_log_ref UUID | M11 spec sub-agent 同時段在寫；本 spec §6 待 M11 spec land 後 final wire |
| M8 spec | §3.1 m8_anomaly trigger + amplification cap | M8 spec sub-agent 同時段在寫；本 spec §9.2 cap 待 M8 spec land 後 final wire |
| M1 LAL spec | §8 OverlayStateChangeEvent → LAL Tier 1/2 eligibility | M1 LAL spec sub-agent 同時段在寫；本 spec §8 待 M1 LAL spec land 後 final wire |

---

## §17 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| PA（本文起草）| spec 設計 + cross-V### dependency + 反向 attack mitigation + LAL Tier 對齊 + cascade contract | 17-section structure 對齊 M3 sister-spec / 5 state FSM × 3 overlay_type × 5 trigger_type / dwell time + flap suppression / amplification cap 6 rules / counterfactual_log_ref UUID 完整性 / engine_mode='replay' 隔離 |
| M3 spec（sister-module DESIGN spec 範式）| 結構 + cascade 範式 + amplification cap 範式 + alert routing 範式 | 17 section structure / cascade idempotency / cascade rollback / multi-domain aggregation / amplification cap 6 rules pattern |
| V105 spec（schema spec full DDL；已 land）| schema baseline | 5 state ENUM + 5 trigger_type ENUM + counterfactual_log_ref UUID + engine_mode 5 mode + mv + Guard A/C |
| ADR-0034 (LAL Tier 0-4 對齊；數字越大越嚴) | 5 state ↔ LAL Tier 1:1 mapping + LAL gate + 24h undo | INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN ↔ LAL 0/1/2/3/4 完美對齊 + LAL Tier 4 operator manual unlock + Decision Lease emit |
| ADR-0036 (M8 + M10 Tier D) | amplification loop cap + 24h 1-anomaly = 1-state-change | M8 anomaly trigger M2 COOLDOWN + amplification cap pattern |
| ADR-0038 (M11 replay + counterfactual) | counterfactual_log_ref UUID + engine_mode='replay' | M11 nightly replay 寫 counterfactual transition + engine_mode='replay' + 50d retention 內保留 |
| PA dispatch consolidation 5.21 §6 + §H-11 | cross-V### dep graph + 反向 attack 6 條 | Sprint 1A-γ dispatch sequence (V107 先 V105 後) + 反向 attack 6 條對應 mitigation |
| v5.8 §2 M2 (operator: APR max autonomy + safety net) | auto-disable always-on + auto-enable opt-in | 5 trigger active for auto-disable + 4 gate for auto-enable + operator forgetfulness mitigation |
| `feedback_first_detection_deadlock_pattern` memory | 反模式禁止 + lock 必有過期條件 | §2.3 flap suppression lock 1h/4h/12h 全 OK + operator manual unlock |
| `feedback_no_dead_params` memory | 51 SM 必真實活 + watchdog 監測 | §12.3 Q1 last_eval_at + 5min cron healthcheck |
| dispatch H-14 STATE-MACHINE-TEST | proptest 窮舉 + dead-state scan + is_none() reset auto-clear 反模式 scan | §10 AC-1 5 state × 3 overlay_type proptest + dispatch H-14 mandate |

### 17.1 待 PM sign-off + operator decision land

- [ ] PM sign-off 本 spec
- [ ] Q1 51 SM watchdog 機制 operator decision land
- [ ] Q2 operator inactivity 60d failsafe 度量 operator decision land
- [ ] Q3 Y2 auto-enable Allocator approval rate baseline operator decision land
- [ ] Q4 M11 divergence 升階 ACTIVE bootstrap CI 嚴格性 operator decision land
- [ ] Q5 M11 replay PG role isolation operator decision land
- [ ] M11 spec land 後 §6 cross-ref final wire
- [ ] M8 spec land 後 §9.2 cap final wire
- [ ] M1 LAL spec land 後 §8 final wire
- [ ] ADR-0034 final commit 解 "Proposed-pending-commit" 狀態

---

**END M2 Overlay State Machine Module DESIGN Spec**

*OpenClaw / Arcane Equilibrium M2 Module DESIGN — 3 Overlay × 5-State FSM × 5 Trigger Type + Counterfactual Log Integration + LAL Tier 0-4 Cascade — Sprint 1A-γ DESIGN deliverable per v5.8 §2 M2 + V105 schema land + PA dispatch consolidation §6 cross-V### + §H-11 反向 attack mitigation*
