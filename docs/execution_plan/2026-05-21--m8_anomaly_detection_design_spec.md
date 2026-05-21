---
spec: M8 — Anomaly Detection (DESIGN initial / IMPL phased Y1 read-only → Y2+ active)
date: 2026-05-21
author: MIT (Sprint 1A-γ DESIGN deliverable; ε wave 第 3 module; M3 / M11 / M2 / M6 / M7 / M9 / M10 same-window sister modules)
phase: v5.8 Sprint 1A-γ DESIGN
status: DESIGN-DRAFT (待 V109 full DDL + ADR-0036 Proposed → Accepted + M3 V106 spec cross-ref resolve 後 SPEC-FINAL)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M8 Anomaly Detection (lines 279-318)
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md (Decision 1 HMM/Markov/GARCH 永久禁用 + Decision 2 替代算法)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §1 CR-5 + §6 cross-V### dependency graph
sister specs (Sprint 1A-β / 1A-γ same window):
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md (M3 ↔ M8 amplification cap H-11)
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (M11 ↔ M8 counterfactual divergence input)
  - srv/docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md (M7 ↔ M8 persistent anomaly 14d → source 5)
  - srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md (M9 ↔ M8 anomaly 期間 A/B 暫停)
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md (M1 LAL ↔ M8 anomaly → Tier 自動降階)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md (648 行;same-wave 範式)
schema 對應:
  - srv/docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md (V109 full DDL;本 spec 同時段 sub-agent 並行)
scope: module 行為 + 9 event taxonomy + 黑名單算法 + severity matrix + amplification cap + cross-module integration contract；不寫 V109 DDL (V109 spec 主責)、不寫 IMPL code (E1 主責)、不寫 detector 數學細節 (per ADR-0036 + walk-forward skill)
---

# M8 Anomaly Detection Module DESIGN Spec

## §0 TL;DR

- M8 是**集中 anomaly 觀測 + classification + severity 分級**模塊;取代當前散落於 strategy 內嵌 self-test、bybit_connector retCode log、operator 手動觀察的碎片化現狀。
- **9 event taxonomy 子類**（market regime / liquidation / orderbook / funding / volume / spread / price / ws / fee）涵蓋市場結構異常 + 自身執行異常 + 基礎設施異常 3 大來源。
- **黑名單算法**：HMM (含所有變形) / Markov-switching regression / GARCH 家族**永久禁用** per ADR-0036 Decision 1；替代採 **ATR-vol regime × Funding state 雙 axis 9-cell 矩陣** + **Realized Vol percentile** + **block bootstrap threshold** per ADR-0036 Decision 2-4。
- **4 級 severity**：INFO（read-only log）/ WARN（alert + audit）/ CRITICAL（M3 HEALTH_DEGRADED + LAL Tier 降階）/ HALT（Y2+ active；新 position open block）。
- **Amplification loop cap**：1 anomaly_type = max 1 state change / 24h；cascade depth ≤ 8 action / 1 cascade per M3 §6.2 + H-11；fail-closed prevention。
- **M3 / M7 / M9 / M1 LAL 4 大 integration contract**；M11 divergence 為 M8 anomaly counterfactual 輸入但**不**為獨立 M8 source（per CR-7 dedup contract — M11 → M3 + M7 dedup,M8 cross-ref consume）。
- **Sprint 1A-γ DESIGN + V109 schema land** → **Sprint 3 statistical detector read-only** → **Sprint 8 advisory alerting** → **Y2+ active gate (M8 → M3 active trigger + ML autoencoder)**。

---

## §1 Context — M8 為何必須在 Sprint 1A-γ DESIGN

### 1.1 v5.7 現狀（fragmented anomaly handling）

當前項目對「anomaly」的處理散落於四處互不協調：

| 來源 | 範圍 | 觸發行為 | 問題 |
|---|---|---|---|
| Strategy 內嵌 self-test (e.g. `bb_breakout` first-detection / dormant timer) | per-strategy 個別 logic | strategy 內 log；不外發 | first-detection deadlock 反模式（per `feedback_first_detection_deadlock_pattern`）；無 cross-strategy 互比 |
| `bybit_connector` retCode nonzero / WS dropout | per-API-call | 該次 fail-closed + log；不累積 | rolling 失敗率不形成 anomaly event；CRITICAL-eligible 無 |
| Manual operator dashboard 觀察 | 全部 | operator 行動 | 依賴 operator 線上 + 看對 tab + 記憶 baseline |
| `learning.fills` slippage outlier silent log | per-fill | log only | 連續 3σ 不升級 anomaly；retroactive RCA 困難 |

**v5.8 §2 M8 設計意圖**（per v5.8 lines 279-318）：把上述碎片化 anomaly 集中到 module，加 9 event taxonomy + 4 severity + amplification cap + cross-module integration contract。

### 1.2 為何 DESIGN initial 必在 Sprint 1A-γ（schema 不可後置）

per v5.8 §2 M8 line 313-314：「Schema decisions made later are expensive to retrofit (audit trail migration, event back-fill). Locking schema in Sprint 1A even though detector waits costs 40-60 hr but saves 80-150 hr retrofit later.」

V109 schema column choice（anomaly_type / severity / detection_method / atr_vol_state / funding_state / amplification_loop_24h_count）必鎖在 Sprint 1A-γ；後置會：
- 已寫入 anomaly_events row 全部 back-fill 新 column
- detector 改 detection_method enum 需重 migrate
- amplification cap writer-side cache 與 schema 不對齊風險

### 1.3 ADR-0036 Decision 1 黑名單在 Sprint 1A-γ 前必 land

per ADR-0036 Context §「為什麼必須在 Sprint 1A-γ DESIGN 階段 land」：若 ADR 不在 dispatch 前 land，sub-agent IMPL 容易拉 `arch` / `hmmlearn` / `pomegranate` package；50-80 hr IMPL 後才發現要 rewrite。

本 spec § 3 為 ADR-0036 Decision 1-4 governance promotion 鏡像（不重寫 ADR；ADR 為 source of truth）。

### 1.4 不在本 spec 範圍

- V109.sql 實檔寫作（V109 spec 主責）
- Detector IMPL 代碼（Sprint 3 E1）
- Detector 數學細節（per `walk-forward-validation-protocol` skill + ADR-0036 Decision 4 block bootstrap）
- ML autoencoder 訓練細節（per `feature-engineering-protocol` skill + Y2+ M8 active trigger）
- HMM / GARCH read-only counterfactual benchmark 路徑（per ADR-0036 Decision 1 例外段 + M11 replay surface）

---

## §2 9 Event Taxonomy（per V109 event_taxonomy ENUM 對齊）

### 2.1 Taxonomy 設計

| event_taxonomy | 來源層 | M8 detection_method | 對應 v5.8 §2 M8 原文 |
|---|---|---|---|
| `regime_shift` | Market regime | `atr_vol_funding_9cell` cell transition trigger + `rv_percentile` 30d window p90/p10 breach | "Vol regime shift (Hurst exponent change, GARCH break)" → 替換為 RV pct + 9-cell |
| `liquidation_cascade` | Market regime | Bybit liquidation feed 累計 5min count / volume vs 7d baseline (z-score > 3) | 補 (v5.8 不顯示，per ADR-0038 M11 liquidation source land 後 cross-ref) |
| `orderbook_imbalance` | Market regime | top-of-book bid/ask volume ratio > 5x or < 0.2x 持續 1min | 補（v5.8 §2 M8 "Correlation structure break" 範疇延伸） |
| `funding_outlier` | Market regime | funding rate cross-venue Δ > 2σ OR funding rate per-symbol abs > 0.5% | "Funding rate / basis dislocation" |
| `volume_spike` | Market regime | per-symbol 1min volume > 10x 7d rolling median | 補（v5.8 §2 M8 "vol regime shift" 範疇延伸；非 vol 而是 traded volume） |
| `spread_widening` | Market regime | top-of-book spread bps > 5x 7d rolling median 持續 30s | 補 (基礎設施 + market microstructure 邊界) |
| `price_dislocation` | Market regime | per-symbol price Δ vs cross-venue mid > 0.5% 持續 30s | 補 (Bybit perp vs spot vs other venue;Y2+ M13 multi-venue 時擴張) |
| `ws_disconnect` | Infrastructure | WS subscription dropout > 60s OR reconnect storm > 3/min | "Strategy fill rate divergence from historical" 之上游 (WS 斷則 fill rate 自然 divergence) |
| `fee_anomaly` | Infrastructure | per-fill effective fee bps vs config 預期 > 0.5bps 持續 5 fills | 補 (Bybit maker/taker fee schedule 變動 / VIP tier 變動之邊界) |

### 2.2 為什麼 9 子類（不是 4 / 6 / 12）

per v5.8 §2 M8 原文列 4 個 market regime + 4 個 own behavior 共 8 子類；本 spec 採 9 個的決策依據：

| 比對 | 棄 / 採理由 |
|---|---|
| 4 子類（僅 v5.8 原文 market regime）| 漏 infrastructure（WS / fee）+ own behavior 4 細項拆得太粗 |
| 6 子類 | 漏 liquidation 與 spread / volume 細項 |
| **9 子類（本 spec）** | **採用**：market regime (4) + market microstructure (3) + infrastructure (2) 三大來源完整覆蓋；每個 detection_method 可明確對應 anomaly_type，schema CHECK constraint 可窮舉 |
| 12 子類 | over-engineered；Y1 樣本量下 12 cell 過稀 |

### 2.3 event_taxonomy 與 own behavior 邊界

v5.8 §2 M8 原文列 4 個 own behavior anomaly（strategy fill rate divergence / order rejection spike / slippage outlier / Decision Lease grant rate anomaly）。本 spec 對 own behavior 的處理：

| Own behavior 異常 | 本 spec 處理 |
|---|---|
| Strategy fill rate divergence | 走 **M3 `strategy_quality` domain**（per M3 spec §2.1）；不寫入 V109 anomaly_events |
| Order rejection spike | 同上 M3 `strategy_quality` |
| Slippage outlier | 同上 M3 `strategy_quality`（per-strategy `slippage_bps_p95` metric） |
| Decision Lease grant rate anomaly | 同上 M3 `strategy_quality` |

**理由**：CR-7 dedup contract — M3 是 single health authority；M8 專注 market + infrastructure；own behavior 走 M3 → M7 decay route（per M3 spec §5.1 + ADR M7）。

V109 schema 不含 own_behavior anomaly_type 是設計決策（避免 M3 / M8 雙寫）。

### 2.4 Taxonomy 與 detection_method 對應表

| event_taxonomy | detection_method（V109 ENUM） |
|---|---|
| regime_shift | `atr_vol_funding_9cell` + `rv_percentile`（複合） |
| liquidation_cascade | `block_bootstrap`（liquidation 5min count baseline） |
| orderbook_imbalance | `rv_percentile`（imbalance ratio rolling p99 breach） |
| funding_outlier | `atr_vol_funding_9cell`（funding state axis trigger） + `block_bootstrap` |
| volume_spike | `rv_percentile`（volume 7d rolling median p99） |
| spread_widening | `block_bootstrap`（spread bps baseline） |
| price_dislocation | `block_bootstrap`（cross-venue mid baseline） |
| ws_disconnect | `manual_operator`（rule-based 60s threshold；非 statistical） |
| fee_anomaly | `manual_operator`（rule-based fee schedule diff；非 statistical） |

---

## §3 黑名單算法 — per ADR-0036 governance promotion

### 3.1 黑名單 3 模型（永久禁用）per ADR-0036 Decision 1

| 模型 | 黑名單範圍 | 適用 module | grep gate |
|---|---|---|---|
| **HMM (Hidden Markov Model)** | 含所有變形：HSMM / HHMM / Factorial HMM / Stochastic HMM 等 | M8 / M10 Tier D / M4 hypothesis miner / 任何 future module；**無例外** | dispatch 前 + IMPL DONE 後 PA + MIT + E2 雙 round `grep -rni 'hmm\\|markov_switching\\|garch'` |
| **Markov-switching regression** | Hamilton 1989 起所有變形 | 同上 | 同上 |
| **GARCH 家族** | EGARCH / TGARCH / IGARCH / FIGARCH / Multivariate GARCH / 任何 conditional heteroskedasticity 變形 | 同上 | 同上 |

### 3.2 Schema-level enforcement（V109 Guard A reverse pattern）

V109 schema `detection_method` CHECK constraint 必反向防護 — 不可含 `'hmm'` / `'markov_switching'` / `'garch'`；Guard A 必含 RAISE EXCEPTION 邏輯：若 `detection_method` ENUM 包含黑名單字眼 → migration fail。

per V109 schema spec §5 Guard A reverse pattern：
```sql
-- Guard A 反向防護：detection_method CHECK enum 不可含 HMM / Markov / GARCH
DO $$
DECLARE v_check_def TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_check_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%detection_method%check%';
    IF v_check_def IS NOT NULL THEN
        IF position('hmm' IN lower(v_check_def)) > 0
           OR position('markov_switching' IN lower(v_check_def)) > 0
           OR position('garch' IN lower(v_check_def)) > 0
        THEN
            RAISE EXCEPTION
                'V109 Guard A FAIL: detection_method CHECK contains forbidden algorithm. '
                'Per ADR-0036 Decision 1, HMM/Markov-switching/GARCH 永久禁用。'
                'Actual: %', v_check_def;
        END IF;
    END IF;
END $$;
```

### 3.3 替代算法（採用）per ADR-0036 Decision 2-4

| 採用算法 | 對應 detection_method ENUM | 數學基礎 |
|---|---|---|
| **ATR-vol × Funding state 雙 axis 9-cell 矩陣** | `atr_vol_funding_9cell` | 3 級 ATR percentile (< 33% LOW / 33-66% MED / > 66% HIGH) × 3 級 funding state (< -0.005% NEGATIVE / -0.005~+0.005% NEUTRAL / > +0.005% POSITIVE) = 3 × 3 = 9 cell；cell transition trigger anomaly |
| **Realized Vol percentile (RV pct)** | `rv_percentile` | 30d rolling window σ_realized 對 90d distribution percentile；超 [10%, 90%] 觸發 LOW / HIGH regime |
| **Block bootstrap threshold** | `block_bootstrap` | block size 5-10 day × ~500 resamples；對 vol clustering robust；用於 funding Δ / spread / cross-venue mid threshold sampling distribution |
| **Manual operator rule-based** | `manual_operator` | rule-based threshold（如 WS dropout 60s / fee Δ 0.5bps）；非 statistical learning |

### 3.4 算法 hot path budget per ADR-0036 §「M8 統計檢測 hot path budget」

per dispatch H-16 SLA：M8 hot path detection ≤ 5μs。本 spec 替代算法（RV pct / 9-cell / block bootstrap）為 O(rolling window) 計算，typical N=30/90 + 25 symbols cargo bench 預估 < 2μs。**不破鎖點**。

### 3.5 例外段 — read-only counterfactual analysis

per ADR-0036 Decision 1 例外段：純 read-only counterfactual analysis（如 backtest 對照 HMM 是否真不工作、學術復現）允許 read-only run，但：
- 結果**不得寫 live state**
- 結果**不得進入 strategy trigger**
- 結果**不得進入 promotion evidence**
- 必走 M11 read-only replay surface（per ADR-0036 + ADR-0038）
- 不創新模塊

---

## §4 Severity Matrix

### 4.1 4 級 severity 定義 + 行為

per ADR-0036 + CR-7 lifecycle alignment（與 M11 divergence_level 3 級對齊但 M8 多 HALT 級 Y2+）：

| Severity | 觸發條件 | M8 action | 與 M3 對齊 | 與 M11 對齊 |
|---|---|---|---|---|
| **INFO** | baseline noise；rare-but-not-actionable anomaly（如單次 spread widening < 30s recover） | log only；write V109 row；不 alert | 不觸 M3 state change | M11 NOISE 等價 |
| **WARN** | actionable observation；rolling 3-5x baseline persistent > 1min | log + Slack `#alerts-info` + write V109 row | 不直接觸 M3；但 24h 內同 type 累積 3 次 → M3 強制 re-check | M11 WARN 等價 |
| **CRITICAL** | severe；持續 5min + 多 symbol affected OR cross-axis 9-cell 連續 2 cell transitions | log + Slack `#alerts-critical` + @operator + write V109 row + **trigger M3 HEALTH_DEGRADED**（Sprint 5 Tier 1）+ **M1 LAL Tier 自動降階**（per §7 + ADR-0034） | CRITICAL → M3 HEALTH_DEGRADED 是 Sprint 5 Tier 1 active wire | M11 CRITICAL 等價 |
| **HALT (Y2+)** | extreme；catastrophic event（如 ws_disconnect > 5min + liquidation_cascade > 50x baseline） | 上述 CRITICAL + **trigger M3 HEALTH_CRITICAL** + **新 position open block**（per §7 ADR-0034 hand-shake） + **M9 A/B 暫停**（per §8） | HALT → M3 HEALTH_CRITICAL 是 Y2+ active gate | M11 不對應（M11 max CRITICAL） |

### 4.2 Severity threshold 不寫死

per ADR-0036 Decision 4 + M3 spec §4.2：所有 severity threshold（除 HALT catastrophic 由既有 5-gate kill criteria 鎖）**block bootstrap 估計 + ArcSwap 熱更新 + 30d re-estimate cadence**。

threshold 存儲：V109 schema `regime_threshold_table` 對應 column 或 `learning.anomaly_severity_taxonomy` registry 表（per V109 spec 設計）；hot update 路徑 = ADR-0009 ArcSwap pattern。

### 4.3 Severity ladder 與 M3 4 state ENUM 邊界區分

per V106 spec §2.3 + ADR-0036：
- **M3 4 state** = continuous-state observation（每 metric 必有 current state；OK 必須是 enum 值）
- **M8 4 severity** = event-discrete anomaly（沒有「正常 anomaly」概念；INFO 即 baseline noise）

兩 enum 不同對齊規則由 PA dispatch §1 CR-X 仲裁；本 spec 採 PA verdict — M8 INFO/WARN/CRITICAL/HALT 4 severity 獨立 enum，與 M3 HEALTH_OK/WARN/DEGRADED/CRITICAL 4 state 各自存活。

### 4.4 HALT 級 Y2+ active gate 而非 Y1

per v5.8 §2 M8 phasing：
- Y1（Sprint 3-8）：M8 全 severity read-only；CRITICAL 只 alert 不 trigger M3 state change
- Y2+（Sprint 9+）：M8 CRITICAL → M3 HEALTH_DEGRADED active wire；HALT 級啟用 + halt new positions

理由：
- Y1 樣本量不足以校準 HALT threshold（block bootstrap 估計 sampling distribution 寬）
- HALT 行為（halt new positions）影響 capital effective allocation；必先 30d 累積 evidence 驗 false alarm rate
- 對齊 v5.8 §2 M8 「Y2 (active trigger)」phasing

---

## §5 Amplification Loop Cap per M3 §6.2 + H-11

### 5.1 反向 attack 場景

per M3 spec §6.1 + H-11：

```
M8 emit anomaly A → M3 HEALTH_DEGRADED → cascade halt strategy → metric 變化
  → M8 emit anomaly B (因 metric 變化) → M3 HEALTH_CRITICAL → cascade more → 雪球
```

或：
```
M8 false anomaly burst (5 個同 type anomaly 1min 內 emit)
  → M3 5 次 state change → cascade 5 次 → 5 個 strategy halt
  → 全 system frozen, alert flooding, operator 無法 triage
```

### 5.2 Loop cap rule（V109 schema 強制）

per M3 spec §6.2 + ADR-0036 + 本 spec governance promotion：

| Rule | 規範 | V109 schema 強制 |
|---|---|---|
| **1 anomaly_type = 1 state change / 24h** | 同 `event_taxonomy` 在 24h 內僅可觸發 1 次 M3 state change；後續同 type anomaly 寫入 V109 但**不**觸 M3 cascade（log only） | `amplification_loop_24h_count` column；writer 預計算同 type 24h count；≥ 2 → 雖寫入但 evidence_json 標 `cap_suppressed=true` |
| **State change rate cap** | M3 自身 state change rate 5 次 / 1h / per-domain；超 cap 自動 freeze + Slack CRITICAL alert + operator manual unlock | M8 不直接管控；走 M3 §6.2 既有 mechanism；本 spec § 7 hand-shake protocol |
| **Cascade depth cap** | 單次 state change 觸發的 cascade action 數量 ≤ 8 / 1 cascade；超 cap 截斷 + log warning + operator review | M8 不直接管控；走 M3 § 5 cascade mechanism |
| **Anomaly source identity** | M8 anomaly event 必帶 `event_id` (UUID) + `event_taxonomy` + `detected_at`；M3 內部維護 24h rolling cache (`event_taxonomy` → 上次觸發 state change 的 timestamp) | V109 `event_id BIGSERIAL` + `event_taxonomy TEXT` + `observed_at TIMESTAMPTZ`；M3 query JOIN cross-ref |
| **Fail-open prevention** | cap 觸發後 metric 持續 DEGRADED（真實退化非 false alarm），cap 不自動釋放 — 必 operator manual unlock；防 fail-open（per §二 原則 6 失敗默認收縮） | per M3 spec §6.2 + 本 spec §7 hand-shake |

### 5.3 amplification_loop_24h_count writer-side query 範例

per V109 spec §1.2：

```sql
-- writer 在 INSERT V109 row 前查同 type 24h transition count
SELECT COUNT(*) FROM learning.anomaly_events
WHERE event_taxonomy = $1
  AND observed_at > now() - INTERVAL '24 hours'
  AND severity IN ('CRITICAL', 'HALT')
  AND engine_mode = $2;
-- 結果寫入新 row 的 amplification_loop_24h_count column
-- ≥ 2 → 新 row 雖寫但 evidence_json 標 cap_suppressed=true,不 emit M3 cascade event
```

### 5.4 amplification cap 與 M11 replay divergence 互動

per M3 spec §6.3 + ADR-0038 CR-7 dedup contract：
- M11 replay divergence **不**算 M8 anomaly（不適用 1-anomaly cap）
- M11 高 divergence flag → trigger M3 對 specific domain re-check（per M3 spec §8）
- 該 re-check 觸發的 state change 仍受 M3 §6.2 state change rate cap 約束
- M8 不直接接收 M11 event；M11 event 經 M3 中轉

---

## §6 M8 ↔ M3 Integration

### 6.1 Integration contract

| M8 event | M3 reaction |
|---|---|
| INFO | 不通知 M3；M8 自身 V109 audit row only |
| WARN | M8 → M3 WARNING-level event；M3 audit log；不 trigger state change（除非 §6.2 累積觸發） |
| CRITICAL | M8 → M3 trigger HEALTH_DEGRADED（Sprint 5 Tier 1 active wire；Y1 read-only deferred） |
| HALT (Y2+) | M8 → M3 trigger HEALTH_CRITICAL（Y2+ active gate） |

### 6.2 累積觸發（WARN 升 DEGRADED）

per M3 spec §8.1 mirror pattern：M8 WARN 24h 內同 `event_taxonomy` 累積 3 次 → 強制 M3 對對應 domain re-check（強制 sample 一次 metric）；若 metric 越線則正常走 M3 §3.3 dwell time + amplification cap 評估。

### 6.3 Hand-shake protocol

M8 ↔ M3 通信走 IPC message bus（per M3 spec §7.3 + existing event_consumer mechanism）：

```
M8 emit: AnomalyEvent {
  event_id, event_taxonomy, severity, detection_method,
  atr_vol_state, funding_state, observed_at,
  amplification_loop_24h_count, engine_mode,
  evidence_json (含 detector raw output)
}
M3 subscribe: AnomalyEvent → §6.1 routing 表決定 reaction
M3 emit: HealthStateChangeEvent (per M3 spec §7.3)
M8 不訂閱: M3 HealthStateChangeEvent（防循環 — 單向 M8 → M3）
```

### 6.4 反向觸發禁止

per M3 spec §7.3 同範式：M3 state change**不可**觸發 M8 anomaly event；M8 → M3 是單向 signal flow。

---

## §7 M8 ↔ M7 Integration（persistent anomaly 14d → source 5）

### 7.1 Integration contract per CR-7 dedup

per CR-7 dedup contract + M7 spec §「M7 decay enforced source」：

| M8 anomaly pattern | M7 reaction |
|---|---|
| 同 `(symbol, event_taxonomy, severity ≥ WARN)` 連續 14d 出現 anomaly event ≥ 7d（per V113 source 5 「persistent_anomaly_14d」邏輯） | M7 INSERT `decay_signals` row source=5 (`persistent_anomaly_14d`)；走標準 M7 DECAY_ENFORCED route |
| 同 `(symbol, event_taxonomy)` 7d 內 anomaly burst 但每次 < 5min recover | 不觸 M7（per CR-7 dedup — short-lived recover ≠ structural decay） |
| 不同 `event_taxonomy` 在同 symbol 7d 累積 | 不直接 M7；走 M3 strategy_quality domain accumulator 判斷 |

### 7.2 M7 source 5 對齊 V113

per V113 (M7 decay_signals) spec § decay_source ENUM：
- source 1: ml_oos_decay
- source 2: drift_psi
- source 3: m3_health_degraded
- source 4: m11_replay_divergence
- **source 5: persistent_anomaly_14d** ← 本 spec 對應

M7 writer 從 V109 anomaly_events 查 `(symbol, event_taxonomy, severity ≥ WARN, observed_at > now() - 14d)` 累積 ≥ 7 distinct days → INSERT V113 source 5 row。

### 7.3 7d threshold 與 14d window 設計理由

| 設計 | 理由 |
|---|---|
| 14d window | 對齊 M7 decay observation 標準 window（per ADR M7）；avoid short-burst false positive |
| 7d 累積 | 50% of window；持續性 indicator；< 7d 視為 transient market event 而非 structural decay |
| `severity ≥ WARN` | INFO 為 baseline noise；不計入 persistent decay 評估 |

### 7.4 Hand-shake

M7 writer cron 每日掃描 V109 → 計算 14d window 累積 → INSERT V113；M8 不直接 emit M7 event。M7 寫入後走 standard M7 DECAY_ENFORCED route（per M7 spec）。

---

## §8 M8 ↔ M9 Integration（anomaly 期間 A/B 暫停）

### 8.1 Integration contract

per CR-X M9 A/B framework 與 M8 同 Sprint 1A-γ DESIGN：

| M8 severity | M9 A/B reaction |
|---|---|
| INFO / WARN | M9 A/B 不暫停；正常運行 |
| **CRITICAL** | M9 A/B **暫停**該 anomaly affected `(symbol, strategy)` pair；其他 A/B test 正常 |
| **HALT (Y2+)** | M9 A/B **全暫停**（per-symbol 影響無法估算；保守路徑） |

### 8.2 為什麼 anomaly 期間 A/B 暫停

per `time-series-cv-protocol` skill §6.3 cross-fold consistency：anomaly 期間 sample 是 outlier；A/B test 收 anomaly 期間 sample 會：
- 污染 treatment / control group 統計力（A/B 估計偏移）
- 違反 i.i.d. 假設 → A/B 結論不可信
- 後續 promotion 評估時必 exclude anomaly window → 樣本量損失

設計選擇：暫停 A/B 收 sample（不暫停 strategy 本身執行），anomaly 結束後 resume；A/B sample 流不含 anomaly window data。

### 8.3 Hand-shake

```
M8 emit: AnomalyEvent (severity ≥ CRITICAL)
M9 subscribe: AnomalyEvent → 內部維護 active A/B test list,標 affected pair "paused_due_to_anomaly_${event_id}"
M9 emit: ABStatePauseEvent (audit log only)
M8 不訂閱 M9 event (單向)
M9 resume: AnomalyEvent severity 降回 < CRITICAL 持續 30min → A/B 自動 resume sampling
```

### 8.4 V108 (M9) cross-ref pattern

per V108 spec § (sister spec)：M9 `learning.ab_test_assignments` row 加 `paused_until_anomaly_resolved` 標記欄位；A/B aggregator query 自動 exclude `paused_until_anomaly_resolved IS NOT NULL` 期間 sample。

---

## §9 M8 ↔ M1 LAL Integration（anomaly → Tier 自動降階）

### 9.1 Integration contract

per ADR-0034 M1 LAL + M3 spec §7：

| M8 severity | M1 LAL reaction（直接 via M3）|
|---|---|
| INFO / WARN | M1 LAL 不變 |
| **CRITICAL** | M8 → M3 HEALTH_DEGRADED → M3 spec §7.2 規則:M1 LAL 1 auto-approve disabled；M1 LAL 2 auto-approve disabled（per CR-15 5-gate auto path inheritance fail-closed） |
| **HALT (Y2+)** | M8 → M3 HEALTH_CRITICAL → M3 spec §7.2 規則:所有 lease grant disabled + 所有現有 active lease 立即 revoke |

### 9.2 LAL Tier 降階是 indirect（經 M3）

per M3 spec §7.3 hand-shake：M1 LAL 不直接訂閱 M8 anomaly event；M1 LAL 訂閱 M3 HealthStateChangeEvent；M8 → M3 → M1 LAL 是 2 跳路徑。

理由：
- 集中 health authority 在 M3（避免 M1 LAL 多源訂閱複雜化）
- amplification cap 在 M3 處理（per §5 + M3 §6.2）；M1 LAL 不重複實現 cap 邏輯
- LAL Tier 規則對應 M3 4 state ENUM；M8 severity 與 M3 state 不 1:1 對齊（per §4.3 enum 邊界區分）

### 9.3 LAL Tier 降階方向 per ADR-0034 數字越大越嚴

per ADR-0034 + M1 LAL spec §3 + 啟動 prompt §「⚠️ 注意」：
- LAL Tier 0 < 1 < 2 < 3 < 4（數字越大越嚴格）
- HEALTH_DEGRADED → Tier 1 auto-approve **disabled**（用戶必經 Tier 2+ operator advisory）
- HEALTH_DEGRADED 持續 > 30min OR HEALTH_CRITICAL → Tier 2 auto-approve **disabled**（用戶必經 Tier 3+ operator manual decision）

V109 `m1_lal_demote_ref BIGINT` column 對齊 ADR-0034 數字越大越嚴；不寫反向降階。

### 9.4 V112 cross-ref pattern

per V109 spec §5 + V112 spec § governance.lease_lal_assignments：
- M1 LAL Tier 升階 eligibility check 必查 V109 incident-free 90d（per V112 spec § mv_lease_lal_eligibility 範例）
- query：`SELECT count(*) FROM learning.anomaly_events WHERE symbol/strategy = $1 AND severity ≥ 'CRITICAL' AND observed_at > now() - INTERVAL '90 days' AND engine_mode IN ('live','live_demo')`
- > 0 → eligibility fail

---

## §10 Acceptance Criteria（5-7 條 sign-off 標準）

Sprint 1A-γ DESIGN + V109 schema land 完成時必 PASS 全 6 條；Sprint 3 statistical detector IMPL + Sprint 8 advisory alerting 補後 PASS AC-7。

| AC-# | Acceptance criteria | Verification method |
|---|---|---|
| **AC-1** | V109 schema 9 event_taxonomy ENUM 真齊全 + 4 severity ENUM 真齊全 + 4 detection_method ENUM 真齊全；Guard A 反向防護真 reject HMM/Markov/GARCH column | per V109 spec §9.2 Linux PG empirical INSERT test + Guard A reverse pattern empirical RAISE test |
| **AC-2** | Amplification cap mock test：emit 同 `event_taxonomy` × 5 CRITICAL anomaly / 24h → 僅 1 次 M3 state change；其他 4 次 V109 row 標 `cap_suppressed=true` | E4 integration test + M3 mock subscribe |
| **AC-3** | M8 ↔ M3 hand-shake：emit CRITICAL anomaly → M3 HEALTH_DEGRADED → V106 audit row INSERT + M1 LAL Tier 1 auto-approve disabled（per §6.3 + §9） | E4 integration test + M3 / M1 LAL mock |
| **AC-4** | M8 ↔ M7 persistent anomaly 14d cron：mock V109 row (`symbol=BTCUSDT, type=regime_shift, severity=WARN`) × 7 distinct days within 14d → M7 INSERT V113 source 5 row | E4 integration test + M7 cron mock |
| **AC-5** | M8 ↔ M9 A/B 暫停：emit CRITICAL anomaly affecting `(BTCUSDT, grid)` → M9 mark A/B `paused_until_anomaly_resolved`；resume 後 sampling 恢復 | E4 integration test + M9 mock |
| **AC-6** | ADR-0036 黑名單 grep gate：PA dispatch 前 + IMPL DONE 後雙 round `grep -rni 'hmm\\|markov_switching\\|garch'` 0 hit | PA + MIT + E2 dispatch 程序遵守；E4 regression CI 加入 grep gate |
| **AC-7** (Sprint 3+) | Statistical detector（RV pct / 9-cell / block bootstrap）read-only INSERT V109 row real workload；threshold block bootstrap empirical 估計 30d 重 estimate auto cron 真跑 | E1 Sprint 3 IMPL + E4 regression |

### 10.1 Y2+ active gate AC（額外）

- **AC-8 (Y2+)**：M8 CRITICAL → M3 HEALTH_DEGRADED active wire（不再 read-only deferred）verify
- **AC-9 (Y2+)**：HALT 級啟用 + halt new positions cascade verify
- **AC-10 (Y2+)**：ML autoencoder reconstruction error detector 接線 + training data exclude anomaly window（per ADR-0036 §「Y2+ ML detector」ADR-debt H-4）

---

## §11 IMPL Phase Split

### 11.1 Sprint 1A-γ — DESIGN + Schema（本 spec scope）

| Item | Workload |
|---|---|
| 本 M8 DESIGN spec doc | 12-20 hr MIT |
| V109 schema spec land + Linux PG dry-run（per V109 spec 主責）| 30-50 hr MIT + PA |
| ADR-0036 Proposed → Accepted（per PM 仲裁 #5 closure）| pending |

### 11.2 Sprint 3 — Statistical detector read-only

| Item | Workload |
|---|---|
| `atr_vol_funding_9cell` detector（hot path < 2μs；per ADR-0036 §「M8 統計檢測 hot path budget」） | 20-30 hr E1 |
| `rv_percentile` detector（30d rolling window per-symbol）| 20-30 hr E1 |
| `block_bootstrap` threshold estimator（per ADR-0036 Decision 4；500 resamples × 30d cron）| 20-30 hr E1 |
| V109 writer + ArcSwap threshold hot reload | 15-20 hr E1 |
| Healthcheck wiring（`passive_wait_healthcheck.py` `check_anomaly_writer()`） | 5-10 hr E1 |
| AC-1 全 PASS verify + AC-2/5 mock test | 5-10 hr E4 |
| **Sprint 3 total** | **85-130 hr** (對齊 v5.8 §2 M8 estimate 60-80 hr + 20-50 hr margin) |

### 11.3 Sprint 8 — Advisory alerting

| Item | Workload |
|---|---|
| Slack channel routing + per-severity matrix（per §4.1 + M3 spec §9.1） | 15-20 hr E1 |
| Alert content schema 含 `event_id` + `event_taxonomy` + `severity` + `cascade_actions_taken` 等 | 10-15 hr E1 |
| Alert rate-limiting（per AMD-2026-05-15-01 + M3 spec §9.3）| 5-10 hr E1 |
| AC-3/4/5 cross-module integration test + AC-6 grep gate CI 加入 | 10-15 hr E4 |
| **Sprint 8 total** | **40-60 hr** (對齊 v5.8 §2 M8 estimate 30-50 hr) |

### 11.4 Y2+ — Active gate（M8 → M3 + ML detector）

per v5.8 §2 M8 Y2 active trigger + ADR-0036：

| Item | Workload |
|---|---|
| M8 CRITICAL → M3 HEALTH_DEGRADED active wire（取消 Y1 read-only deferred）| 20-30 hr E1 |
| HALT 級啟用 + halt new positions cascade（per §4.4 + M3 cascade table）| 30-50 hr E1 + FA |
| ML autoencoder reconstruction error detector（per `feature-engineering-protocol` skill leakage 防護 + training data exclude anomaly window） | 30-40 hr E1 + MIT |
| **Y2+ total** | **80-120 hr** (對齊 v5.8 §2 M8 estimate) |

### 11.5 工程總 cost 對齊 v5.8 §2 M8

| Phase | 本 spec estimate | v5.8 §2 M8 estimate |
|---|---|---|
| Sprint 1A-γ DESIGN + Schema | 42-70 hr | 40-60 hr (✓) |
| Sprint 3 statistical detector | 85-130 hr | 60-80 hr (margin 25-50 hr — 因 9 子類 vs 4 子類擴增) |
| Sprint 8 advisory alerting | 40-60 hr | 30-50 hr (✓) |
| Y2+ active gate + ML | 80-120 hr | 80-120 hr (✓) |
| **Total Y1-Y2** | **247-380 hr** | **210-310 hr** |

差距 ~37-70 hr 來自 9 子類擴增 + amplification cap H-11 cross-cutting wire 額外複雜度（per dispatch H-11）。

---

## §12 Cross-V### Dependency + Open Questions

### 12.1 V### dependency 圖

```
V096 boundary (TimescaleDB extension) → V109 (prereq)
V098 (governance.audit_log)            → V109 (cross-ref；非 FK)
V109 (M8 anomaly_events;本 spec schema 對應)
   ├─→ V106 (M3 health_observations) — M8 CRITICAL → M3 HEALTH_DEGRADED (cross-ref query)
   ├─→ V112 (M1 LAL lease_lal_assignments) — anomaly 90d incident-free → eligibility (cross-ref query)
   ├─→ V113 (M7 decay_signals) — persistent anomaly 14d → source 5 (cross-ref query)
   ├─→ V107 (M11 replay_divergence_log) — M11 不直接 emit M8;CR-7 dedup cross-ref only
   └─→ V108 (M9 ab_test_assignments) — anomaly 期間 A/B 暫停 (cross-ref query)
```

### 12.2 Cross-V### sequencing

per dispatch CR-9 + 5.3 V### 順序：
- Sprint 1A-β：V106 + V107 + V112 必先 land（M3 / M11 / M1 LAL DESIGN 共享）
- **Sprint 1A-γ：V109 + V108 + V111 + V113 並行 land**；本 spec V109 schema 不依賴 V107/V108/V111/V113 hard FK，cross-ref query 走 application layer
- Sprint 3+：detector IMPL 才需 V108/V113 cross-ref query 接線；schema-level 0 dependency lock

### 12.3 Open Questions（≥ 3）

#### Q1 — 9 event_taxonomy vs v5.8 §2 M8 原文 4 個 market regime 的 governance 取齊

**問題**：本 spec 採 9 子類（補 liquidation_cascade / orderbook_imbalance / volume_spike / spread_widening / price_dislocation / ws_disconnect / fee_anomaly 共 7 個 v5.8 原文未列）；ADR-0036 未 enumerate 子類；操作員是否 explicit approve 9 子類擴展？

**選項**：
- (a) 採 9 子類（本 spec 提案）；理由：market microstructure + infrastructure 完整覆蓋；Sprint 3 detector 對應明確
- (b) 限縮回 v5.8 §2 M8 原文 4 子類（規格嚴格對齊）；副作用：infrastructure event（WS disconnect / fee anomaly）無 schema 落腳點
- (c) 採中間 6 子類；理由：保留 market regime 4 + 添 ws_disconnect + fee_anomaly 2 infrastructure；棄 microstructure 細項 3

**Owner**：PM + PA cross-review Sprint 1A-γ V109 land 前 confirm；建議採 (a) 因 Sprint 3 IMPL hot path detector 對 schema column 對應需求高。

#### Q2 — Amplification cap 24h window 是 wall-clock 還是 strategy-active hour？

**問題**：M3 spec § Q2 同問題；M8 amplification cap 是否需與 M3 同步答案？

**當前設計**：24h wall-clock（per M3 spec §6 + 本 spec §5）。

**問題擴張**：Y2+ M13 multi-venue 後可能 venue 各自有 trading window，需重新評估；同 type anomaly 在 venue A 期間出現 + venue B 期間又出現是否視為「同 anomaly type 2 次 / 24h」？

**Owner**：QC + FA Sprint 5 Tier 1 IMPL 前 confirm（同步 M3 spec Q2）。

#### Q3 — ML autoencoder Y2+ 啟用時 training data exclude anomaly window 的 enforcement 路徑？

**問題**：per ADR-0036 §「Y2+ ML detector」ADR-debt H-4：autoencoder training data **必 exclude anomaly period**。但 anomaly period 由 V109 自身定義 → autoencoder training query 需 LEFT JOIN V109 exclude `severity ≥ WARN` 期間 sample → 但 autoencoder 訓練前的 baseline 也是 anomaly detector 之一 → 雞蛋問題。

**選項**：
- (a) Bootstrap：Y2+ 啟用前用 statistical detector（9-cell + RV pct + block bootstrap）累積 6mo anomaly_events 為 ground truth；autoencoder training exclude 該 6mo period 內 severity ≥ WARN sample
- (b) Unsupervised：autoencoder training 不 exclude；reconstruction error 自然 reflect anomaly outlier；對 leakage tolerance 寬
- (c) 不啟用 autoencoder（per ADR-0036 Decision 1 例外段不採 ML，永久 statistical-only）

**Owner**：MIT + QC Y2+ active gate IMPL 前 confirm（per `feature-engineering-protocol` skill leakage 6 維度 + `time-series-cv-protocol` skill purge + embargo）。

#### Q4（補充） — `engine_mode = paper` 是否寫入 V109？

**問題**：V109 schema engine_mode CHECK 4 值齊全（paper/demo/live_demo/live）；但 paper 是 simulation，anomaly 是否 paper 也採集？

**選項**：
- (a) 不寫 paper（query filter `engine_mode IN ('demo','live_demo','live')`）；理由：paper 失真，anomaly 無研究價值
- (b) 寫 paper 但 `cap_suppressed=true` 跳過 amplification cap；理由：保留 schema column 4 值 enum；training data filter 期可 exclude
- (c) 全寫 paper；理由：cross-engine_mode anomaly 對比可作為 paper / live divergence 研究

**Owner**：MIT + QC Sprint 3 detector IMPL 前 confirm；per CLAUDE.md §七 training filter `IN ('live','live_demo')` 既有原則，建議採 (a) 或 (b)。

---

## §13 §二 16 根原則合規確認

| # | 原則 | 是否相容 | M8 對應設計 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M8 不創 order 寫入口；anomaly trigger → M3 cascade 走 Conductor + Guardian 既有單一寫入口 |
| 2 | 讀寫分離 | ✅ | M8 自身僅讀 market metric + 寫 V109 audit row；不寫 trading state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M8 anomaly event → cascade action 經 M3 + M1 LAL + 既有 5-gate；不繞 lease |
| **4** | **策略不繞風控** | ✅ | **M8 CRITICAL/HALT → 走 Guardian + 5-gate 既有 cascade**；不創新風控繞道 |
| 5 | 生存 > 利潤 | ✅ | HALT Y2+ 立即 halt new positions；CRITICAL 立即 M3 HEALTH_DEGRADED |
| 6 | 失敗默認收縮 | ✅ | §5.2 amplification cap fail-open prevention；cap 觸發後 operator manual unlock 才釋放 |
| 7 | 學習 ≠ live | ✅ | M8 不寫 live strategy state；只 publish event → 下游 module 自決定 cascade action；HMM/GARCH read-only counterfactual 不得寫 live state |
| 8 | 交易可解釋 | ✅ | V109 evidence_json + audit field 5 件 + transition_id 可 reconstruct |
| 9 | 雙重防線 | ✅ | 本地 M8 + Bybit 既有 conditional order 雙重防線 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | metric 數值 = 事實；anomaly classification = 推論（per threshold）；amplification cap 設計 = 假設待 RCA 驗 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | M8 anomaly 自主 emit；cascade action 在 P0/P1 既有風控邊界內；不擴 |
| 12 | 行為由 evidence 演化 | ✅ | per §4.2 threshold 30d block bootstrap 自動 re-estimate；不寫死 |
| **13** | **cost 感知** | ✅ | **RV pct + 9-cell + block bootstrap cost 低**（< 2μs hot path）**遠優於 HMM/GARCH MCMC iteration**（typical 100-1000ms train cost）；ADR-0036 黑名單即是 cost 治理 |
| 14 | 零外部成本 | ✅ | M8 全 self-monitoring；不依賴付費 external data |
| 15 | 多 agent 形式化協作 | ✅ | M3 + M1 LAL + M7 + M8 + M9 + M11 各有明確 message contract |
| **16** | **Portfolio > 孤立 trade** | ✅ | **regime_shift / liquidation_cascade / orderbook_imbalance / funding_outlier 為 portfolio-level event**；對齊 §16 |

---

## §14 Cross-References

- **v5.8 主檔 §2 M8 Anomaly Detection**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:279-318`
- **ADR-0036 M8 anomaly + M10 Tier D blacklist**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（Decision 1 永久禁用 HMM/Markov/GARCH + Decision 2 替代算法 ATR-vol+funding 9-cell + RV pct + block bootstrap + Decision 3 M10 Tier D 9-cell regime + Decision 4 threshold 估計）
- **V109 schema spec**（本 spec 同時段 sub-agent 並行 full DDL）：`docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md`
- **M3 spec**：`docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（M8 ↔ M3 amplification cap H-11 + cascade hand-shake）
- **M7 spec**：`docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md`（M8 persistent anomaly 14d → source 5）
- **M9 spec**：`docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md`（anomaly 期間 A/B 暫停）
- **M11 spec**：`docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md`（CR-7 dedup contract — M11 → M3 + M7,M8 cross-ref only）
- **M1 LAL spec**：`docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`（M8 CRITICAL → M3 → LAL Tier 自動降階；ADR-0034 數字越大越嚴）
- **V106 schema spec**：`docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- **V107 schema spec**：`docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md`
- **V112 schema spec**：`docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- **V113 schema spec**：`docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- **V108 schema spec**：`docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md`
- **CLAUDE.md §Data, Migrations, And Validation**：Guard A/B/C + Linux PG dry-run mandate
- **`feedback_v_migration_pg_dry_run.md` memory**：V055 5-round loop precedent
- **`feedback_first_detection_deadlock_pattern.md` memory**：lock 必有過期條件
- **`feedback_chinese_only_comments.md` memory**：注釋默認中文（本 spec 中文為主）
- **`walk-forward-validation-protocol` skill**：Decision 4 block bootstrap + OOS SOP
- **`feature-engineering-protocol` skill**：Y2+ autoencoder leakage 6 維度
- **`time-series-cv-protocol` skill**：autoencoder training data purge + embargo

---

## §15 Engineering Scope Summary

| Phase | Sprint | Item | Workload |
|---|---|---|---|
| DESIGN | 1A-γ | M8 module spec doc（本 spec）| 12-20 hr MIT |
| DESIGN | 1A-γ | V109 schema spec land + Linux PG dry-run | 30-50 hr MIT + PA |
| DESIGN | 1A-γ | ADR-0036 Proposed → Accepted closure | pending PM 仲裁 |
| Sprint 3 | 3 | `atr_vol_funding_9cell` + `rv_percentile` + `block_bootstrap` detector + V109 writer + healthcheck wiring | 85-130 hr E1 |
| Sprint 8 | 8 | Slack alerting × severity matrix + alert rate-limiting + cross-module integration | 40-60 hr E1 |
| Y2+ | Y2 | M8 CRITICAL → M3 active wire + HALT cascade + ML autoencoder + training data exclude anomaly window | 80-120 hr E1 + MIT |
| **Total Y1** | — | DESIGN + Sprint 3 + Sprint 8 | **167-260 hr** |
| **Total Y2+** | — | Active gate + ML | **80-120 hr** |

---

## §16 Risk / Blockers / Operator Decisions

### 16.1 Risk

| Risk | Mitigation |
|---|---|
| 9 子類擴增與 v5.8 §2 M8 原文 4 子類不對齊 | per Q1 PM/PA confirm Sprint 1A-γ land 前；建議採 (a) 9 子類 |
| Amplification cap 過嚴致漏報真實 CRITICAL | per §5.2 fail-open prevention；CRITICAL band 不受 cap 約束 |
| Y2+ ML autoencoder leakage 風險（training data exclude anomaly window 雞蛋問題） | per Q3 Y2+ active gate IMPL 前 confirm；建議採 (a) bootstrap 6mo statistical-only baseline |
| 9-cell 矩陣 Y1 樣本量 cell 過稀 | per ADR-0036 §「3.3 為什麼分 3 級」+ cell stability metric 7d 統計 warning |
| Detector hot path > 5μs 超 budget | per ADR-0036 §「M8 統計檢測 hot path budget」cargo bench 預估 < 2μs；Sprint 3 IMPL 必驗 |
| Block bootstrap 估計噪音致 false alarm rate 飆 | per ADR-0036 Decision 4 re-estimate cadence 30d + Operator manual override |

### 16.2 Blockers

| Blocker | Resolution |
|---|---|
| V109 spec full DDL 未 land | Sprint 1A-γ 同時段 sub-agent 並行；MIT 主責 |
| ADR-0036 Proposed → Accepted 未 closure | PM 仲裁 #5 confirm；本 spec 假設 ADR Accepted |
| M3 spec / V106 schema 未 land | Sprint 1A-β 已 land（per 同 wave）；§6 hand-shake protocol 可 cross-ref |
| M1 LAL ADR-0034 未 land | Sprint 1A-β 同 wave；§9 integration contract 待 ADR-0034 land 後 final wire |
| M7 V113 / M9 V108 / M11 V107 未 land | Sprint 1A-γ 同 wave 並行；§7 / §8 cross-ref query 走 application layer 不阻 schema |

### 16.3 Operator Decision Points

- **D1**：Q1 — 9 event_taxonomy vs v5.8 §2 M8 原文 4 子類；建議 (a) 9 子類
- **D2**：Q2 — amplification cap 24h window wall-clock vs strategy-active hour；建議 wall-clock 同步 M3 spec
- **D3**：Q3 — ML autoencoder Y2+ 啟用時 training data exclude anomaly window enforcement；建議 (a) bootstrap 6mo
- **D4**：Q4 — engine_mode=paper 是否寫入 V109；建議 (a) 不寫 paper（per CLAUDE.md §七 training filter 既有原則）

---

**END M8 Anomaly Detection Module DESIGN Spec**

*OpenClaw / Arcane Equilibrium M8 Module DESIGN — Anomaly Detection — Sprint 1A-γ DESIGN deliverable per v5.8 §2 M8 + ADR-0036 + PA dispatch consolidation; 9 event taxonomy + ATR-vol × Funding 9-cell + RV pct + block bootstrap; HMM/Markov/GARCH permanently blacklisted per ADR-0036 Decision 1; amplification cap H-11 + 4 cross-module integration contract (M3 / M7 / M9 / M1 LAL)*
