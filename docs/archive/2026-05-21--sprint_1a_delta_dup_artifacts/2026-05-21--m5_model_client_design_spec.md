---
spec: M5 ModelClient Trait — Online Learning Interface Reservation DESIGN
date: 2026-05-21
author: PA Sprint 1A-δ M5 track（interface reservation only；對齊 ADR-0035 4 Decisions 邊界）
phase: v5.8 Sprint 1A-δ interface reservation
status: SPEC-PARTIAL-V0（interface 預留 only；Y3+ activation 期才寫 full streaming-update IMPL DESIGN；本 spec 不寫完整 streaming 算法 / drift detection closed-form）
parent specs:
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（4 Decisions ADR 權威 — Decision 1 trait stub / Decision 2 V114 reserved / Decision 3 6 觸發條件 / Decision 4 retirement criteria；本 spec 100% 對齊不違背）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M5 (line 188-217)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-δ (line 159-167)
sibling specs:
  - srv/docs/execution_plan/2026-05-21--v114_m5_model_versions_streaming_schema_spec.md（V114 reserved placeholder 同 Sprint 1A-δ land；本 spec 與 V114 schema 預留共享一致紀律）
  - srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md（M9 結構範式參考 §0-§7；M9 為 streaming 模型 Y3+ activation 觸發條件 (d) 引用對象）
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md（DESIGN spec partial / 對齊 ADR / §0-§7 範式）
related ADR:
  - ADR-0021 Alpha Source Architecture Upgrade（R-2 Strategist orchestrator；M5 streaming prediction 不繞）
  - ADR-0034 M1 Decision Lease LAL（Y3+ activation 走 LAL 4 capital structure / streaming reparam 走 LAL 1 intra-strategy）
  - ADR-0037 M9 A/B Framework（streaming 模型 alpha 驗證必經 M9 control vs variant；ADR-0035 Decision 3 (d) trigger）
  - ADR-0039 M12 OrderRouter（同 Sprint 1A-δ interface reservation pattern；trait stub + V### reserved 紀律同源）
  - ADR-0040 M13 Multi-Venue（同 Sprint 1A-δ interface reservation pattern；retirement criteria 紀律同源）
amendments referenced:
  - 無（M5 interface reservation Sprint 1A-δ scope 內無直接 amendment 依賴；Y3+ activation 期才可能新增 AMD）
scope: M5 ModelClient trait stub DESIGN spec only — Sprint 1A-δ 鎖定 6 method slot + default panic + Y3+ activation 6 條件 + 4 retirement criteria；不寫 IMPL Rust streaming 算法；不寫 drift detection closed-form；不寫 rollback 觸發 closed-form；不寫 Mac PG / Linux PG SQL；不假設 V114 final type；不取代既有 LightGBM / Optuna / 3DL daily-batch baseline
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# M5 ModelClient Trait — Online Learning Interface Reservation DESIGN（Sprint 1A-δ）

## §0 TL;DR

- **M5 為 online learning / streaming model update interface 預留**：Sprint 1A-δ 只交 ModelClient trait stub（6 method slot default `unimplemented!()` panic），不寫 streaming 算法 / drift detection IMPL；Y3+ activation 期 IMPL（200-400 hr）
- **6 method ModelClient trait**（per ADR-0035 Decision 1 + v5.8 §2 M5 line 188-217）：`get_predict(features) -> Prediction` + `get_predict_streaming(features) -> StreamingPrediction` + `version() -> ModelVersion` + `model_metadata() -> ModelMetadata` + `health() -> ModelHealth` + `streaming_supported() -> bool`
- **Y3+ activation 3 條 criteria**（per ADR-0035 + v5.8 §2 M5 line 211-213）：(a) daily retrain proven insufficient + (b) AUM > $50k + (c) operator opt-in；ADR-0035 Decision 3 擴為 6 條 AND gate（加 (d) M9 GA + (e) Live PnL 3 month > 0 + (f) daily-batch Sharpe threshold）
- **既有 ML 不被取代**（per memory `project_ml_dl_learning_architecture` + ADR-0035 §Context）：LightGBM + Optuna + 3DL daily-batch baseline Y1 + Y2 仍是主路徑；M5 streaming 是「在 baseline 之上加層」，Y3+ activation 才啟用
- **5-gate inheritance**（per ADR-0034 LAL Tier 對齊）：Y3+ activation IMPL 期 streaming update 必經 LAL Tier 3（new strategy promotion / capital structure / operator approval mandatory）；streaming reparam（單一 model 內 weight 增量更新）走 LAL Tier 1（intra-strategy reparam）
- **Fail-loud method default**：6 method 全 default `unimplemented!()` panic，禁默認 no-op `Ok(())` 回傳；Y1 + Y2 任何 caller 誤呼必 panic，強制 fail-loud
- **AC（5 條）**：trait stub panic smoke test + Y3+ activation 6 條件 schema review + V114 cross-ref test + 既有 ML 路徑 unchanged + LAL inheritance 對齊
- **IMPL phase**：Sprint 1A-δ trait stub 6-10 hr（PA Rust crate path 推 `rust/openclaw_engine/src/model_client.rs`，與既存 `edge_predictor/mod.rs` 同層）；Y3+ activation 200-400 hr 全 IMPL（streaming algorithm / drift detection / rollback / V114 full DDL）

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M5 module source

v5.8 §2 M5 line 188-217 將 Online Learning / Incremental Model Update 列為 13 module 之一：

```
Existing ML (per memory project_ml_dl_learning_architecture):
  - LightGBM / Optuna / 3DL trained via daily cron
  - Models swapped at daily boundary

Online learning addition (Y3+ when justified):
  - Streaming update: model parameters update per N new fills (vs full daily retrain)
  - Drift detection: KL divergence on feature distribution between train and live
  - Auto-rollback: if live performance degrades vs daily-batch baseline, revert to batch

Interface reservation (Sprint 1A only):
  - ModelClient trait in Rust: get_predict() / get_predict_streaming() (latter unimplemented panic!)
  - learning.model_versions table includes streaming_enabled BOOL column (default FALSE)
  - ADR-0035 (proposed): online learning interface reserved, IMPL deferred Y3+
  - No engineering past interface stub
```

operator 2026-05-21 D1 明寫「M5 must add at low priority — 這是個後續開發的點」（per PA dispatch consolidation report 行 21 / ADR-0035 §Context 起源段）。

### 1.2 為什麼是 interface reservation only（不寫 full streaming IMPL）

- **Y1 ROI 不成立**：$10k AUM × 5 strategy × daily ML retrain 場景下 streaming 邊際 gain ≤ 1-2% APR（per v5.8 §2 M5 line 217）；trait stub cost 僅 6-10 hr（本 Sprint）；full IMPL cost 200-400 hr 對 Y1 ROI 不成立
- **既有 ML 已能 cover Y1 + Y2 需求**：LightGBM + Optuna + 3DL daily-batch baseline 在 daily granularity 對 regime shift response time 充足；streaming 增量更新對 sub-daily latency 才有 marginal gain
- **零 schema breaking 風險**：trait + V114 reserved column 預留 → Y3+ activation 時 ALTER table flip DEFAULT FALSE → TRUE 即可，不需 schema rewrite
- **避免「DESIGN-only debt 永久債」風險**：ADR-0035 Decision 4 明示 4 retirement 條件 + Sprint 10 / Y2 Q4 / Y3 Q2 三輪 retirement audit cadence；若 Y3 末仍未觸發 → dead-code removal PR 強制清理

### 1.3 為什麼必須在 Sprint 1A-δ DESIGN 階段 land

per PA dispatch packet 行 159-167（Sprint 1A-δ deliverable）+ ADR-0035 §Context：

- M5 為 13 module 圖完整性要素 — operator low priority directive 已 land
- trait stub + V114 placeholder 必 Sprint 1A-δ 同時 land — 兩者共享同治理 pattern（per Sprint 1A-δ M5+M12+M13 三 stub 同 Sprint）
- Sprint 1A-ε cross-ADR consistency audit 必驗 ADR-0035 + V114 spec doc + 本 DESIGN spec 三者 cross-ref 一致；任一缺即 audit fail

### 1.4 不在本 spec 範圍

- ❌ Rust streaming 算法 IMPL（incremental gradient descent / online RandomForest / streaming PCA 等 — Y3+ activation 期 DESIGN）
- ❌ Drift detection closed-form 公式（KL divergence 算法細節 — Y3+ activation 期 DESIGN）
- ❌ Rollback 觸發 closed-form（streaming vs baseline error threshold 算法 — Y3+ activation 期 DESIGN）
- ❌ V114 full DDL（V114 reserved placeholder spec 同 Sprint land；full DDL 在 Y3+ activation 期才落地）
- ❌ Mac PG / Linux PG SQL 跑（trait stub + V114 placeholder 都不寫 SQL；Y3+ activation 真寫 V114 SQL 時走 Linux PG empirical dry-run per `feedback_v_migration_pg_dry_run`）
- ❌ ContextDistiller v4 token cap 對齊（per ADR-0041；M5 evaluation 不在 hot path L1 SLA）
- ❌ Y3+ activation full IMPL DESIGN（待 6 條件全 PASS 後開新 amendment ADR + full IMPL DESIGN spec）

---

## §2 ModelClient Trait Interface（6 Method Slot, Default Panic）

per ADR-0035 Decision 1 + v5.8 §2 M5 line 188-217，trait 預留 6 method slot；Sprint 1A-δ 全 default `unimplemented!()` panic（fail-loud）。

### 2.1 Method 1: `get_predict(features) -> Prediction`

| 元素 | 設計 |
|---|---|
| **用途** | 同步預測 — 既有 daily-batch 模型路徑（LightGBM / 3DL baseline）的統一包裝介面 |
| **Y1 + Y2 行為** | **既有 LightGBM / 3DL daily-batch 已 IMPL**；本 trait method 是其 unified interface wrapper；Sprint 1A-δ 階段 default `unimplemented!()` 但 Sprint 4+ 真包裝既有 EdgePredictor 時可以 land 真實 body |
| **Y3+ IMPL 行為** | 包裝不變；增加 streaming model fallback 路徑（如 streaming 模型 health degrade → fallback to daily-batch baseline） |
| **input contract** | `features: FeatureVector`（與既有 `edge_predictor::Prediction` 對齊；具體 type 走 Y3+ activation IMPL spec） |
| **output contract** | `Prediction`（既有 `rust/openclaw_engine/src/edge_predictor/mod.rs` line 45 `Prediction` struct）— 對齊既有路徑 |
| **panic 反模式** | Sprint 1A-δ default `unimplemented!()`；若 Sprint 4+ 包裝既有 EdgePredictor 時 IMPL 真 body，仍需確認對齊既有 path（非新增旁路） |

### 2.2 Method 2: `get_predict_streaming(features) -> StreamingPrediction`

| 元素 | 設計 |
|---|---|
| **用途** | 即時推論（streaming 更新版）— Y3+ activation 後 streaming weight 增量更新後即時推論 |
| **Y1 + Y2 行為** | **default `unimplemented!()` panic**（trait stub only）；任何 caller 誤呼 → fail-loud |
| **Y3+ IMPL 行為** | Sprint Y3+ IMPL：streaming weight 增量更新後即時推論；對齊 ADR-0035 Decision 1 表「Sprint Y3+ IMPL：streaming weight 增量更新後即時推論」 |
| **input contract** | `features: FeatureVector`（同 `get_predict`） |
| **output contract** | `StreamingPrediction`（含 baseline prediction + streaming delta + streaming model version + drift score；具體 struct 走 Y3+ activation IMPL spec） |
| **panic 紀律** | **Y1 + Y2 任何 module 呼叫 → `unimplemented!()` panic**；對齊 v5.8 §2 M5 line 204「latter unimplemented panic!」+ ADR-0035 Decision 1 反模式 (a) |

### 2.3 Method 3: `version() -> ModelVersion`

| 元素 | 設計 |
|---|---|
| **用途** | 返回當前 active model version（baseline / streaming 各自版本識別）|
| **Y1 + Y2 行為** | **default `unimplemented!()` panic**（trait stub only） |
| **Y3+ IMPL 行為** | Sprint Y3+ IMPL：返回 ModelVersion `{ baseline_version, streaming_version, version_ts }`；對齊 V114 `learning.model_versions.streaming_enabled` column |
| **input contract** | 無 |
| **output contract** | `ModelVersion`（具體 struct 走 Y3+ activation IMPL spec；與既有 model_versions 表 schema 對齊） |
| **panic 紀律** | Sprint 1A-δ default panic |

### 2.4 Method 4: `model_metadata() -> ModelMetadata`

| 元素 | 設計 |
|---|---|
| **用途** | 返回 model metadata（training data range / feature schema / hyperparameter snapshot / streaming config 等） |
| **Y1 + Y2 行為** | **default `unimplemented!()` panic**（trait stub only） |
| **Y3+ IMPL 行為** | Sprint Y3+ IMPL：返回 ModelMetadata `{ training_data_range, feature_schema_hash, hyperparameter_snapshot, streaming_config, last_update_ts }` |
| **input contract** | 無 |
| **output contract** | `ModelMetadata`（具體 struct 走 Y3+ activation IMPL spec） |
| **panic 紀律** | Sprint 1A-δ default panic |

### 2.5 Method 5: `health() -> ModelHealth`

| 元素 | 設計 |
|---|---|
| **用途** | 模型健康度（per ADR-0034 LAL gate criteria 對齊 evidence）— streaming 模型誤差 + drift + 樣本量綜合 health metric |
| **Y1 + Y2 行為** | **default `unimplemented!()` panic**（trait stub only） |
| **Y3+ IMPL 行為** | Sprint Y3+ IMPL：streaming model 誤差 + drift + 樣本量綜合 health metric；對齊 ADR-0034 LAL Tier 3 / 4 gate eligibility check |
| **input contract** | 無 |
| **output contract** | `ModelHealth`（含 healthy / degraded / unhealthy ENUM + 具體 metric 值；具體 struct 走 Y3+ activation IMPL spec） |
| **panic 紀律** | Sprint 1A-δ default panic |

### 2.6 Method 6: `streaming_supported() -> bool`

| 元素 | 設計 |
|---|---|
| **用途** | trait 自我宣告 streaming 是否啟用 — caller 判斷 `get_predict_streaming()` 是否可呼叫 |
| **Y1 + Y2 行為** | **可 IMPL 真 body 但永遠返回 `false`**（trait stub 階段；對齊「streaming 預設 OFF」紀律）；或者 default `unimplemented!()` panic 也可（前者更友善）|
| **Y3+ IMPL 行為** | Sprint Y3+ IMPL：返回 `true` 若 streaming pipeline 已 enable（對齊 V114 `streaming_enabled` column）|
| **input contract** | 無 |
| **output contract** | `bool` — `true` = streaming 可用 / `false` = streaming 未啟用（fallback to baseline）|
| **panic 紀律** | 例外：本 method 可 IMPL `false` 真 body（safe default）；或 default panic（fail-loud）— PA 建議走 default panic 統一紀律，避免 caller 誤判 |

### 2.7 6 Method Slot 對齊矩陣（核心 governance artifact）

per ADR-0035 Decision 1 表 + v5.8 §2 M5：

| Method | 用途 | Sprint 1A-δ default | Y3+ activation IMPL | 與 LAL 對齊 |
|---|---|---|---|---|
| `get_predict` | sync prediction（baseline wrapper） | `unimplemented!()` panic | wrapper 包裝既有 EdgePredictor + streaming fallback | LAL 1（intra-strategy reparam） |
| `get_predict_streaming` | streaming prediction | `unimplemented!()` panic | streaming weight 增量更新後即時推論 | LAL 1（intra-strategy）/ LAL 4（首次 activation）|
| `version` | model version 識別 | `unimplemented!()` panic | 返回 ModelVersion struct | 對齊 LAL audit trail |
| `model_metadata` | metadata snapshot | `unimplemented!()` panic | 返回 ModelMetadata struct | 對齊 LAL audit trail |
| `health` | health metric | `unimplemented!()` panic | streaming 誤差 + drift + 樣本量 health | 對齊 LAL Tier 3 / 4 gate eligibility |
| `streaming_supported` | streaming 是否啟用 | `unimplemented!()` panic（或 IMPL `false`） | 返回 `true` 對齊 V114 `streaming_enabled` | 對齊 V114 schema column |

**對齊紀律**：
- 6 method 預留 = 一次性鎖入 streaming lifecycle 完整對應（predict / streaming predict / version / metadata / health / streaming_enabled flag）
- Y3+ activation 期不需 amend trait 補 method → 避免 trait breaking change
- 對齊既有 `edge_predictor::EdgePredictor` trait pattern（`rust/openclaw_engine/src/edge_predictor/mod.rs` line 90），但 ModelClient 是 superset（含 streaming + metadata）

### 2.8 反模式（明示禁止 per ADR-0035 Decision 1）

- **(a)** Y1 + Y2 在任何 module 呼叫 `get_predict_streaming` / `version` / `model_metadata` / `health` / `streaming_supported`：違反 stub-only 紀律；trait fail-loud 設計就是要 panic
- **(b)** Sprint 1A-δ 把任一 method 改為 default no-op（`Ok(())` 回傳 / 返回 dummy struct）：違反 fail-closed 紀律；後續 caller 誤以為 stub 已 IMPL
- **(c)** trait 預留 method slot 但未對齊 V114 schema column（`streaming_enabled` BOOL DEFAULT FALSE）：trait + schema 必同步預留
- **(d)** Sprint 1A-δ 真 IMPL streaming 算法（即使是「prototype」）：違反 v5.8 §2 M5 「No engineering past interface stub」directive

---

## §3 Y3+ Activation 6 條件 AND Gate

per ADR-0035 Decision 3，Y3+ M5 online learning 真實 IMPL 開始的 6 條件，必 6 條全 PASS（AND 邏輯）。

### 3.1 條件 (a) — Daily-batch retrain 已證實不足

| 元素 | 設計 |
|---|---|
| **來源** | v5.8 §2 M5 line 211 + ADR-0035 Decision 3 |
| **評估方法** | 兩個並行條件 AND： |
|  | (a1) regime shift latency 觀察 ≥ 6 month 樣本顯示 daily granularity 失靈（如 hourly regime shift 在 daily retrain 之間造成 drawdown > N bps）|
|  | (a2) M11 nightly replay divergence ≥ N bps 持續觸發（對齊 ADR-0038 M11 continuous counterfactual replay）|
| **Owner** | MIT + QC Y3+ activation 期共同 verify |
| **Risk caveat** | 6 month observation window 對 $10k AUM 樣本量可能不足；mitigation = Y3+ AUM > $50k 後 (a) 評估才有 statistical power |

### 3.2 條件 (b) — AUM > $50k Sustained 30d

| 元素 | 設計 |
|---|---|
| **來源** | v5.8 §2 M5 line 212 + ADR-0035 Decision 3 |
| **評估方法** | per v5.8 §5 capital-tier ladder Y3 Q2 estimate $75-150k；$50k 是 ML infra 投入 break-even 點 |
| **Owner** | PM + operator Y3+ activation 期共同 verify |
| **Risk caveat** | $50k threshold 是 ML infra ROI break-even 估計；具體 threshold 可由 PM Y3+ activation 期仲裁調整（per ADR-0035 §Consequences Negative）|

### 3.3 條件 (c) — Operator opt-in

| 元素 | 設計 |
|---|---|
| **來源** | v5.8 §2 M5 line 213 + ADR-0035 Decision 3 |
| **評估方法** | per ADR-0034 LAL 4 capital structure / 新模塊啟用 → operator approval mandatory；走 5-gate review session |
| **Owner** | operator Y3+ activation 期顯式 opt-in（不可 silent enable） |
| **Risk caveat** | operator opt-in 必明示 signed approval（避免 ambiguous「我同意 streaming activation」聲明被誤用為 LAL 4 approval） |

### 3.4 條件 (d) — M9 A/B Framework 已 GA

| 元素 | 設計 |
|---|---|
| **來源** | ADR-0035 Decision 3 新增（per §3.3 streaming 模型必透過 M9 control vs variant 驗 alpha） |
| **評估方法** | per ADR-0037 M9 GA 條件 — Sprint 4 read-only logging + Sprint 7-8 manual A/B + Y2 auto-test scheduling 全 land 後才為 GA |
| **Owner** | MIT + QC Y3+ activation 期共同 verify |
| **Risk caveat** | M9 GA 預期 Y2 末 — Y3+ activation timing 與 M9 GA 時程對齊 |

### 3.5 條件 (e) — Live PnL 連續 3 month > 0

| 元素 | 設計 |
|---|---|
| **來源** | ADR-0035 Decision 3 新增（per §二 原則 5 生存 > 利潤）|
| **評估方法** | Live PnL 連續 3 month > 0 — minimum stable window；防 P0-EDGE-1 失血期啟用新 ML 路徑放大失血 |
| **Owner** | PM + FA Y3+ activation 期共同 verify |
| **Risk caveat** | Y1 + Y2 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure 後才開 Live；Live 3 month sustained 可能 Sprint 5+ 才達到；mitigation = (e) 條件本意就是 evidence-gated 紀律，延遲是 by design |

### 3.6 條件 (f) — 既有 LightGBM / 3DL Daily-Batch 連續 30d Sharpe > X

| 元素 | 設計 |
|---|---|
| **來源** | ADR-0035 Decision 3 新增（streaming 是「在穩定 baseline 之上加層」）|
| **評估方法** | 既有 LightGBM / 3DL daily-batch baseline 連續 30d Sharpe > X — X 由 Y3+ activation 時 PM + MIT 仲裁定 |
| **Owner** | PM + MIT Y3+ activation 期共同仲裁 X |
| **Risk caveat** | 本 ADR 不鎖 X 數值；mitigation = Y3+ activation 真接近時 PM 仲裁定 X，避免本 ADR 寫死過時 threshold；evidence-based amendment 路徑符合 §二 原則 12 |

### 3.7 6 條件 AND 邏輯紀律

per ADR-0035 Decision 3 末段：

- **6 條全 PASS** → 開新 ADR amend ADR-0035 Decision 4 retirement criteria 反向（從 retirement 轉 activation）+ Y3+ V114 full DDL Sprint land
- **任一 FAIL** → 維持 trait stub 狀態，繼續 defer；retirement audit cadence Sprint 10 / Y2 Q4 / Y3 Q2 三輪 evaluation
- **(a) + (b) PASS 但 (c) FAIL（operator 不 opt-in）** → 維持 stub；operator opt-in 是 hard gate 不可 bypass
- **(c) PASS 但 (e) FAIL（Live PnL 不穩）** → 維持 stub；§二 原則 5 生存 > 利潤
- **(f) X 仍未定** → Y3+ activation 真接近時 PM 仲裁；本 spec 不寫 X

---

## §4 Decision Lease Boundary（per ADR-0034 LAL Tier 對齊）

### 4.1 為什麼 M5 必對齊 LAL

per ADR-0035 §一 16 根原則合規確認 + 根原則 4「策略不繞風控」+ 根原則 3「AI 輸出 ≠ 命令」：

- M5 streaming prediction 仍走 R-2 Strategist orchestrator 統一發 proposal（per ADR-0021 R-2 alignment）
- 任何 streaming 更新引發的 strategy parameter shift 仍走 R-3 hypothesis pipeline + ADR-0034 LAL gate 路徑
- M5 不創旁路寫入口（per §二 原則 1 單一寫入口）

### 4.2 LAL Tier 對齊矩陣

| 場景 | LAL Tier | 觸發紀律 |
|---|---|---|
| **Y3+ first activation**（首次啟用 streaming 路徑） | **LAL Tier 3**（new strategy promotion / capital structure / operator approval mandatory）| operator opt-in（per §3.3 條件 (c)）+ 5-gate review session |
| **Streaming reparam**（單一 model 內 weight 增量更新） | **LAL Tier 1**（intra-strategy reparam）| streaming weight 更新走 LAL 1 自動 path；不需 operator approval per update |
| **Streaming model swap**（跨 strategy 影響 — 如 M4 pattern miner 切到 M5 streaming）| **LAL Tier 2**（cross-strategy reweight）| 走 LAL 2 - 5-gate auto path inheritance + supervisor approval |
| **Streaming rollback**（streaming 模型誤差大 → rollback to baseline） | **無 LAL gate**（safety net 自動 trigger）| `rollback()` method Y3+ IMPL 期走 self-protective fail-closed；不需 operator approval rollback |

### 4.3 5-Gate Auto Path Inheritance（per ADR-0034 + v5.8 §11.5）

per ADR-0034 LAL Decision 5「5-gate auto path inheritance」+ v5.8 §11.5：

- M5 streaming update IMPL 階段（Y3+）必經 5-gate auto path：
  1. **Stage 0R replay preflight**（per AMD-2026-05-15-01）— streaming 更新後的模型必先 replay 驗
  2. **Stage 0 shadow** — streaming 模型跑 shadow（不寫 live state）
  3. **Stage 1 demo small** — streaming 模型跑 demo 小倉
  4. **Stage 2 demo full** — streaming 模型跑 demo full
  5. **Stage 3 live canary** — streaming 模型跑 live canary（per ADR-0035 Decision 3 (e) Live PnL 3 month > 0 才可進）

- Stage 4 live full：永遠 LAL Tier 3 operator approval（不開新 auto path繞 operator）

### 4.4 反模式（明示禁止）

- (a) M5 streaming prediction 不經 R-2 Strategist orchestrator 直接發 order：違反根原則 1 + 4 + ADR-0021 R-2 alignment
- (b) Streaming reparam 跳過 Stage 0 shadow 直接進 Stage 1 demo：違反 5-gate 紀律
- (c) Streaming rollback 需 operator approval per rollback：違反 safety net 設計（rollback 必快 / 自動）
- (d) Y3+ activation 不走 LAL Tier 3 operator approval：違反 ADR-0034 LAL 4 capital structure

---

## §5 IMPL Dispatch Brief for E1（Sprint 1A-δ Trait Stub IMPL）

### 5.1 Rust Crate Path 決策

**PA 推 `rust/openclaw_engine/src/model_client.rs`** — 理由：

1. **與既存 `edge_predictor/mod.rs` 同層**（per inspect `rust/openclaw_engine/src/edge_predictor/mod.rs` line 90 `pub trait EdgePredictor: Send + Sync`）— ModelClient 是 ML 推論介面，與 EdgePredictor 同 surface；放 openclaw_engine 內統一管理
2. **不放 openclaw_types**：openclaw_types 是 pure types crate（type definitions），ModelClient trait 含 future streaming logic + lifecycle method，更適合放 engine crate
3. **不創 model_client/ subdir**：Sprint 1A-δ 只 1 file（trait stub）；Y3+ activation 期才擴 subdir（streaming.rs / drift.rs / rollback.rs 等）
4. **lib.rs export**：`pub use model_client::ModelClient;` 加入 `rust/openclaw_engine/src/lib.rs`

### 5.2 Trait Struct + Default Impl Pattern（E1 IMPL Skeleton 摘要）

**E1 IMPL 重點**（完整 trait code 由 E1 寫，PA 列簽名 + 紀律）：

- `pub use crate::edge_predictor::Prediction;` — 對齊既有 EdgePredictor `Prediction` type
- 5 placeholder struct：`ModelVersion` / `ModelMetadata` / `ModelHealthStatus` enum / `ModelHealth` / `StreamingPrediction`
- `pub type FeatureVector = serde_json::Value;` — Y3+ activation 期再對齊 FeatureCollector
- `pub trait ModelClient: Send + Sync` — 6 method default body 全 `unimplemented!("M5 ModelClient.<name> — interface stub only, IMPL deferred Y3+ (per ADR-0035 Decision 1)")`
- 簽名：
  - `fn get_predict(&self, _features: &FeatureVector) -> Prediction`
  - `fn get_predict_streaming(&self, _features: &FeatureVector) -> StreamingPrediction`
  - `fn version(&self) -> ModelVersion`
  - `fn model_metadata(&self) -> ModelMetadata`
  - `fn health(&self) -> ModelHealth`
  - `fn streaming_supported(&self) -> bool`
- doc string 全中文（per CLAUDE.md §七 + memory `feedback_chinese_only_comments`）
- `rust/openclaw_engine/src/lib.rs` 追加 `pub mod model_client;`

### 5.3 預估工時 + Acceptance Criteria

| 元素 | 設計 |
|---|---|
| **預估工時** | **6-10 hr Rust IMPL**（per ADR-0035 §Engineering Scope Reference Sprint 1A-δ 8-12 hr 範圍下限；含 trait 寫作 + 5 placeholder struct + lib.rs export + cargo build + cargo test smoke） |
| **acceptance criteria** | 1. `cargo build --workspace` PASS |
|  | 2. `cargo test --workspace --lib` PASS（新增 1-2 trait smoke test） |
|  | 3. 新增 sibling smoke test file `rust/openclaw_engine/tests/m5_model_client_stub_panic.rs`，驗證 5-6 method 全 panic（per AC-1 §6）|
|  | 4. trait 6 method 默認 `unimplemented!()` 不可改 `Ok(())` no-op（per §2.8 反模式 (b)） |
|  | 5. 中文注釋 default（per CLAUDE.md §七 + memory `feedback_chinese_only_comments`） |
| **依賴** | ADR-0035 land（已 Proposed 2026-05-21）+ V114 placeholder spec land（同 Sprint 1A-δ deliverable） |
| **中文注釋紀律** | per CLAUDE.md §七「新或修改之注釋默認中文」+ memory `feedback_chinese_only_comments`；trait + 5 placeholder struct + 6 method doc string 全中文；既有 bilingual 不主動清，但本 M5 文件全新建立 → 純中文 |
| **不在本 Sprint 範圍** | Streaming 算法 IMPL（Y3+） / V114 full DDL（Y3+） / FeatureCollector 對齊 IMPL（Y3+） / Real EdgePredictor wrapper（Sprint 4+） |

### 5.4 E1 Dispatch Packet（Sprint 1A-δ M5 trait stub IMPL 摘要）

| 元素 | 內容 |
|---|---|
| **Target** | E1 (Rust) |
| **Scope** | (1) 創建 `rust/openclaw_engine/src/model_client.rs`（trait + 5 placeholder struct + 重出 Prediction）；(2) 追加 `pub mod model_client;` 到 `rust/openclaw_engine/src/lib.rs`；(3) 新增 `rust/openclaw_engine/tests/m5_model_client_stub_panic.rs`（6 test case 各驗 1 method panic）；(4) 中文注釋 default |
| **Acceptance** | `cargo build --workspace` PASS / `cargo test --workspace --lib` PASS / 6 panic smoke test PASS / 無 `Ok(())` no-op / lib.rs export 已加 / 注釋全中文 |
| **Refs** | ADR-0035（4 Decisions 100% 對齊）+ v5.8 §2 M5 line 188-217 + 本 DESIGN spec + sibling V114 placeholder spec |
| **Out-of-scope** | 真實 streaming 算法 / V114 SQL file / 既有 EdgePredictor wrapper / FeatureCollector 對齊 / 任何其他 module |
| **Workload** | 6-10 hr |
| **Submit** | cargo build PASS log + cargo test PASS log + 3 file path + sub-agent dispatch report |

---

## §6 Acceptance Criteria（5 條）

per ADR-0035 4 Decisions + 本 DESIGN spec §2-§5：

### AC-1: Trait Stub Panic Smoke Test

- **驗**：6 method 各呼叫一次，全 panic
- **預期**：`unimplemented!()` panic 觸發；message 含「M5 ModelClient.<method> — interface stub only, IMPL deferred Y3+」
- **失敗**：任一 method 不 panic（被改為 no-op `Ok(())` / dummy struct）→ REJECT
- **Owner**：E4 Sprint 1A-δ regression

### AC-2: Y3+ Activation 6 條件 Schema Review

- **驗**：本 DESIGN spec §3 6 條件齊全 + AND 邏輯紀律明示
- **預期**：6 條件全列 + 各條 Owner / 評估方法 / Risk caveat 全表
- **失敗**：6 條件少於 6 / Owner 缺一 / AND 邏輯紀律未明示 → REJECT
- **Owner**：PA Sprint 1A-ε cross-ADR consistency audit

### AC-3: V114 Cross-Ref Test

- **驗**：本 DESIGN spec frontmatter + 內文 cross-ref V114 placeholder spec doc 路徑正確
- **預期**：sibling V114 placeholder spec doc 存在 + 雙向 cross-ref 一致
- **失敗**：V114 placeholder spec doc 未 land / cross-ref 路徑錯誤 → REJECT
- **Owner**：PA Sprint 1A-ε cross-ADR consistency audit

### AC-4: 既有 ML 路徑 Unchanged

- **驗**：本 DESIGN spec land 後既有 LightGBM / Optuna / 3DL daily-batch baseline 路徑 0 改動
- **預期**：既有 `rust/openclaw_engine/src/edge_predictor/mod.rs` 全 unchanged；ModelClient trait 純新增不取代
- **失敗**：existing EdgePredictor trait 被改 / 既有 daily-batch cron 被改 → REJECT
- **Owner**：E2 Sprint 1A-δ review

### AC-5: LAL Inheritance 對齊

- **驗**：本 DESIGN spec §4 LAL Tier 對齊矩陣齊全 + 5-gate auto path inheritance 明示
- **預期**：4 場景 LAL Tier 對齊（first activation / streaming reparam / streaming swap / streaming rollback）+ 5-gate inheritance 明示
- **失敗**：LAL Tier 對齊缺 / 5-gate inheritance 未明示 / 反模式未明示 → REJECT
- **Owner**：QA + PA Sprint 1A-ε cross-ADR consistency audit

---

## §7 Open Q / Risk Caveats / Spec→IMPL Gaps

### Open Q

| # | 議題 | 建議 | Owner |
|---|---|---|---|
| 1 | `streaming_supported()` default — panic vs `return false` | PA 推 default panic 統一紀律；E1 IMPL 期反饋若友善度不足可 amend，但需 ADR-0035 minor amend | E1 / PA |
| 2 | 5 placeholder struct field stability — Y3+ activation 期可能因算法選型 amend | Sprint 1A-δ struct field 不鎖死；Y3+ 期可 amend；Sprint 4+ EdgePredictor wrapper 若改動 → minor amend ADR | MIT Y3+ |
| 3 | Sprint 4+ 是否提前包裝既有 EdgePredictor 進 `get_predict()` 真 body | Sprint 1A-δ 階段全 default panic；Sprint 4+ 可 amend `get_predict` 改 wrapper 真 body — 走 minor amend ADR | PA Sprint 4+ |
| 4 | V114 final schema column set — Y3+ activation 期可能 normalize 多表 | 本 DESIGN spec 鎖 trait interface（不依賴 V114 final schema）；schema 兼容靠 application layer adapter | PA + MIT Y3+ |
| 5 | ModelClient vs EdgePredictor 角色邊界 | Sprint 1A-δ 兩 trait 並存（ModelClient = future-facing）；Y3+ activation 期可考慮 blanket impl 或 merge | PA Y3+ |

### Risk Caveats

| # | 風險 | Mitigation |
|---|---|---|
| 1 | 6 條件 AND gate 過嚴可能 Y3+ activation 永不觸發 | retirement audit cadence Sprint 10 / Y2 Q4 / Y3 Q2 三輪；(f) X threshold 可 amend |
| 2 | trait stub 死碼 Y1~Y3 約 6 method panic | sibling 6 panic test 驗證 + retirement audit cadence + ADR-0035 + 本 spec 明示「reserved for Y3+」 |
| 3 | Sprint 4+ 包裝既有 EdgePredictor 可能改 trait default body 為 `Ok(())` no-op | Sprint 4+ amend 必走 minor amend ADR + PA approval + E2 對抗 review |

### Spec→IMPL Gaps（Y3+ Activation 期才 land）

| # | Gap | 處置 |
|---|---|---|
| 1 | Streaming 算法選型未鎖 | Y3+ activation 觸發後開新 amendment ADR + Y3+ full IMPL DESIGN spec |
| 2 | Drift detection / rollback closed-form 公式未鎖 | Y3+ activation IMPL DESIGN spec 鎖定 |
| 3 | V114 full DDL 未鎖 | sibling V114 placeholder spec 明示 Y3+ land；Linux PG empirical dry-run per `feedback_v_migration_pg_dry_run` |

---

## §8 References

### Parent specs

- **ADR-0035**：`srv/docs/adr/0035-m5-online-learning-interface-reserved.md`（4 Decisions ADR 權威；本 DESIGN spec 100% 對齊）
- **v5.8 execution plan**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M5 line 188-217
- **PA dispatch consolidation**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` 行 159-167 Sprint 1A-δ deliverable

### Sibling specs

- **V114 reserved placeholder spec**：`srv/docs/execution_plan/2026-05-21--v114_m5_model_versions_streaming_schema_spec.md`（同 Sprint 1A-δ land；本 DESIGN spec 與 V114 schema 預留共享一致紀律）
- **M9 DESIGN spec (mirror precedent)**：`srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md`（DESIGN spec partial / 對齊 ADR / §0-§7 範式參考）

### ADR cross-ref

- **ADR-0021 Alpha Source Architecture Upgrade**：`srv/docs/adr/0021-alpha-source-architecture-upgrade.md`（R-2 Strategist orchestrator + R-3 hypothesis pipeline 對齊）
- **ADR-0034 M1 Decision Lease LAL**：`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（Y3+ activation 走 LAL Tier 3 + streaming reparam 走 LAL Tier 1 + 5-gate auto path inheritance）
- **ADR-0037 M9 A/B Framework**：`srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`（streaming 模型 alpha 驗證必經 M9 control vs variant；ADR-0035 Decision 3 (d) trigger）
- **ADR-0039 M12 OrderRouter**：同 Sprint 1A-δ interface reservation pattern（trait stub + V### reserved 紀律同源）
- **ADR-0040 M13 Multi-Venue**：`srv/docs/adr/0040-multi-venue-gate-spec.md`（同 Sprint 1A-δ interface reservation pattern；retirement criteria 紀律同源）

### Skill cross-ref

- **`srv/.claude/skills/db-schema-design-financial-time-series`**：V114 future full DDL hypertable / chunk / partial index 規範對齊（Y3+ activation 期）
- **`srv/.claude/skills/quant-strategy-design`**：streaming 更新 + drift detection 對齊 ML governance（Y3+ activation 期）

### Memory cross-ref

- **`project_ml_dl_learning_architecture`**：既有 LightGBM / Optuna / 3DL daily-batch baseline（M5 streaming 為「baseline 之上加層」非取代）
- **`feedback_chinese_only_comments`**：本 spec + Sprint 1A-δ IMPL Rust 注釋全中文
- **`feedback_v_migration_pg_dry_run`**：Y3+ activation 真寫 V114 full DDL 時必走 Linux PG empirical dry-run
- **`project_2026_05_02_p0_sqlx_hash_drift`**：V114 不寫 DDL 即避免 sqlx checksum drift（per ADR-0035 Decision 2 反模式 (a)）
- **`feedback_new_code_rust_first`**：M5 ModelClient trait 是 Rust-first 新模組（per CLAUDE.md §七）
- **`feedback_multi_role_strategic_review`**：本 DESIGN spec land 後 Sprint 1A-ε cross-ADR consistency audit 走多角色 review

### Code path reference

- **`rust/openclaw_engine/src/edge_predictor/mod.rs`** line 90 `pub trait EdgePredictor: Send + Sync` — 既有 ML 推論 trait pattern；ModelClient 是 superset（與其同層放 `rust/openclaw_engine/src/model_client.rs`）
- **`rust/openclaw_engine/src/lib.rs`** — Sprint 1A-δ E1 IMPL 期追加 `pub mod model_client;`

---

## §9 §二 16 根原則合規確認

per ADR-0035 §二 16 根原則合規確認（已在 ADR-0035 完整列；本 DESIGN spec 100% 對齊不複制）—— 重點：

- 原則 1/3/4：M5 streaming prediction 仍走 R-2 Strategist + Decision Lease + Guardian gate；不創旁路寫入口
- 原則 5/6：§3.5 條件 (e) Live PnL > 0 + §2 default panic + V114 streaming_enabled DEFAULT FALSE 三層 fail-closed
- 原則 7/8：M5 是 learning surface；Y3+ activation 必經 M9 A/B 驗 alpha + V114 audit trail 完整
- 原則 11/12：Y3+ activation 6 條件全 evidence-based + 自主 within LAL Tier 3 operator approval
- 原則 13/14：trait stub 6-10 hr cost + retirement R1 防永久債 + streaming 全自建（無 vendor SaaS）

完整逐條對齊請見 ADR-0035 §二 表（16 條）。

---

## §10 Sign-off Table

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via D1 v5.8 §2 M5 ADD-per-operator LOW priority interface reservation only 已批 | 2026-05-21 | ✅ APPROVED-pending-spec-land |
| PA | 本 DESIGN spec 起草（對齊 ADR-0035 4 Decisions + 6 method slot 規範 + Y3+ activation 6 條件 + LAL Tier 對齊 + IMPL dispatch brief + 5 AC + 5 Open Q + 3 Risk caveat + 3 Spec→IMPL Gap） | 2026-05-21 | ✅ Drafted v0 |
| MIT | trait 6 method slot 設計 review + Y3+ activation 6 條件 evidence 評估方法 review | TBD（Sprint 1A-δ） | 🟡 PENDING |
| E1 | ModelClient trait stub IMPL（Sprint 1A-δ default panic）+ 5 placeholder struct + lib.rs export | TBD（Sprint 1A-δ） | 🟡 PENDING |
| E2 | trait stub 對抗 review（防 default no-op 反模式 / Ok(()) 改 panic）| TBD（Sprint 1A-δ） | 🟡 PENDING |
| E4 | sibling panic test `tests/m5_model_client_stub_panic.rs` 6 case + 既有 ML 路徑 unchanged 驗證 | TBD（Sprint 1A-δ） | 🟡 PENDING |
| QA | Sprint 1A-δ trait stub dispatch grep gate（防 default no-op 反模式）對齊 dispatch SOP + LAL Tier 對齊驗 | TBD（Sprint 1A-δ） | 🟡 PENDING |
| PM | Y3+ activation 觸發評估仲裁 + retirement audit 仲裁（Sprint 10 / Y2 Q4 / Y3 Q2）| TBD（Sprint 10 起） | 🟡 PENDING |

---

**END M5 ModelClient Trait Stub DESIGN spec partial v0（Sprint 1A-δ；對齊 ADR-0035 4 Decisions；待 V114 reserved placeholder spec 同 Sprint land；待 E1 IMPL trait stub + E4 panic smoke test + QA dispatch grep gate）**

---

Sub-agent dispatch: PA Sprint 1A-δ M5 track
完成時間：2026-05-21
