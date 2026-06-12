---
spec: M5 — Online Learning Interface Reserved (DESIGN spec, interface stub level)
date: 2026-05-21
author: PA (Sprint 1A-δ deliverable per v5.8 §10 ADR roster + Sprint 1A-δ trait stub dispatch)
phase: v5.8 Sprint 1A-δ — interface stub level only; full module DESIGN deferred Y3+
status: DESIGN-INTERFACE-STUB-ONLY（trait + 退役紀律 + V114 reserve cross-ref；Y3+ activation 後另開 amendment ADR + 完整 DESIGN spec）
parent specs:
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（治理 ADR；本 spec 為 ADR Sprint 1A-δ deliverable IMPL 邊界 spec）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M5 (lines 188-217) + §3.5 Sprint 1A-δ + §9 V114 reserved + §10 Risk #2 retirement criteria
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md（V103 frontmatter + 14 section 範式，本 spec V114 placeholder cross-ref ref）
related ADR:
  - ADR-0034 Decision Lease LAL（Y3+ activation 走 LAL 4 capital structure）
  - ADR-0036 M8 anomaly detection + M10 Tier-D model blacklist
  - ADR-0037 M9 A/B framework（本 spec retirement R2 引用：M9 A/B 擴 variant-as-streaming-update 可能收編 M5）
  - ADR-0038 M11 continuous counterfactual replay（IMPL 觸發條件 (a)1 引用：replay divergence 是 daily-batch 不足訊號）
  - ADR-0039 M12 OrderRouter trait stub（同 Sprint 1A-δ deliverable + 同 interface-reservation pattern）
  - ADR-0040 M13 multi-venue trait stub（同 Sprint 1A-δ deliverable + 同 interface-reservation pattern）
  - ADR-0041 Context-distiller v4 + AI cost cap amendment
scope: interface stub level only — 不寫 Rust IMPL 程式碼、不寫 V114 full DDL、不寫 streaming algorithm 選型、不寫 cross-module integration full DESIGN（Y3+ activation 後再寫）
---

> **REFERENCE / FROZEN AUTONOMY MODULE SPEC**
>
> 本 spec 保留 v5.8 Sprint 1A module design lineage。当前 active-IMPL 以
> `TODO.md` 和最新 PM/role reports 为准；不得仅凭本 spec 派发实现或扩展学习系统写权限。

# M5 Online Learning Interface Reserved — DESIGN spec（interface stub level）

## §0 TL;DR

- 本 spec = ADR-0035 IMPL 邊界 spec；只覆蓋 Sprint 1A-δ 階段 8-12 hr 工作的 interface 細節，**不展開 full module DESIGN**（per ADR-0035 status "IMPL Y3+"）。
- 8 section（不是 12 section）：Context / ModelClient trait 6 method slot / Retirement 4 criteria / Cross-module placeholder integration / Acceptance criteria / IMPL phase / V### dependency placeholder / Open Q。
- ModelClient trait 6 method slot **採 ADR-0035 §Decision 1 鎖定的 method 集合**（`get_predict / get_predict_streaming / drift_callback / rollback / throttle / health`），**非** prompt 列的泛 ML 套路（`predict / update / save / load / version / metrics`）— 對齊既有 LightGBM/3DL baseline 包裝意圖。Open Q #1 標出此分歧供 operator 仲裁。
- 全 6 method default `unimplemented!()` panic（fail-loud 紀律 per §二 原則 6）；Y1+Y2 任何 caller 呼叫即 panic = 反模式 grep gate。
- V114 reserve placeholder 同 Sprint 派發（本 spec sibling doc `2026-05-21--v114_m5_online_learning_reserved_schema_spec.md`），frontmatter only + 14 section outline only；Y3+ activation 才寫 full DDL。
- Retirement 4 criteria 明示（R1-R4），對齊 ADR-0035 §Decision 4；Y3 末未觸發 → dead-code removal PR。
- Cross-module placeholder（M9 A/B variant / M6 Bayesian reward / M11 nightly replay）全標 Y3+ activation；本 Sprint 不寫整合邏輯。

---

## §1 Context — M5 為 online learning interface 預留，Y3+ IMPL deferred

### 1.1 來源與 ADR 邊界

per ADR-0035 line 12-22 + v5.8 §2 M5 lines 188-217：M5 是 v5.8 13 module 圖中 online learning streaming 更新層的佔位 module，Sprint 1A-δ 僅交付 8-12 hr interface stub，full IMPL 200-400 hr deferred Y3+。

operator 2026-05-21 D1 directive：「M5 must add at low priority — 這是個後續開發的點」。本 spec **不重複** ADR-0035 已論證的 deferred 理由（regime shift latency / AUM break-even / operator opt-in / framework dependency 等），僅引用 ADR 鎖定的邊界。

### 1.2 與既有 ML 路徑關係

既有 ML 為 daily-batch retrain（per memory `project_ml_dl_learning_architecture`）：

| 元素 | 既有設計 | M5 trait 包裝關係 |
|---|---|---|
| LightGBM Teacher-Student | daily cron 訓練 / daily boundary swap | 由 `get_predict()` method 包裝（Y1+Y2 既有路徑），`get_predict_streaming()` panic 預留 Y3+ |
| Optuna | weekly/monthly cron hyperparameter search | 不在 M5 trait 範圍（M5 = inference + streaming update，不是 hyperparameter search） |
| 3DL（Teacher / Student / Distill 三層 DL） | daily cron + 模型版本 register | 由 `get_predict()` 包裝；`drift_callback()` + `health()` + `rollback()` 預留 Y3+ streaming 路徑 |

**M5 不取代 baseline；是在 daily-batch baseline 之上加 streaming 更新層**（per ADR-0035 line 35）。Sprint 1A-δ 階段 trait 預留 6 method slot 中只有 `get_predict()` 在 Y3+ activation 後有實際 IMPL change（從 baseline 包裝改為 baseline + streaming fallback），其餘 5 method 為 Y3+ activation 才從 panic 改為實作。

### 1.3 範圍與本 spec 不涵蓋

| 涵蓋 | 不涵蓋（Y3+ activation 後另開 spec） |
|---|---|
| trait 6 method signature 鎖定 | streaming algorithm 選型（online gradient descent / streaming RF / online SVM 等） |
| 6 method default panic 紀律 | streaming model state persistence schema 細節 |
| Retirement 4 criteria + audit cadence | drift detection algorithm（KL divergence threshold / EDDM / DDM 等） |
| Cross-module placeholder（M6/M9/M11）介面預留 | M5 對 M9 A/B variant 的具體 control vs streaming-variant 分配邏輯 |
| V114 reserve frontmatter cross-ref | V114 full DDL（含 `learning.online_learning_models` 完整 column / index / partition） |
| 反模式 grep gate（防 caller 誤呼） | streaming 更新觸發時機（per-fill / per-N-fills / time-window 三種策略選型） |

---

## §2 ModelClient Trait — 6 method slot（all default `unimplemented!()` panic）

### 2.1 trait 定義（interface 鎖定，不寫 IMPL）

```rust
// crate path（預期）：openclaw_engine::ml::model_client
//
// Sprint 1A-δ deliverable：trait + 6 method default impl 全 panic
// Y3+ activation 才實作；本 stub 階段任何 caller 觸發 method = panic（fail-loud）

pub trait ModelClient: Send + Sync {
    /// 同步預測（既有 daily-batch baseline 包裝介面）
    ///
    /// Y1+Y2 行為：包裝既有 LightGBM / 3DL daily-batch model；Y3+ activation 後
    /// 加 streaming fallback path（先試 streaming model，失敗或 unhealthy 降回 baseline）
    fn get_predict(&self, features: &FeatureVector) -> Result<Prediction, M5Error> {
        unimplemented!(
            "M5 ModelClient::get_predict stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// 即時推論（streaming weight 增量更新後的預測）
    ///
    /// Y1+Y2 行為：panic（無 streaming model）；Y3+ activation 後實作
    fn get_predict_streaming(&self, features: &FeatureVector) -> Result<StreamingPrediction, M5Error> {
        unimplemented!(
            "M5 ModelClient::get_predict_streaming stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// feature distribution 漂移回呼（KL divergence trigger）
    ///
    /// Y1+Y2 行為：panic；Y3+ activation 後實作 drift detection → Strategist propose
    /// model rollback path
    fn drift_callback(&self, distribution_metrics: &DistributionMetrics) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::drift_callback stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// 回滾到指定模型版本（safety net）
    ///
    /// Y1+Y2 行為：panic；Y3+ activation 後實作 streaming model degrade →
    /// rollback to daily-batch baseline
    fn rollback(&self, version: ModelVersion) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::rollback stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// streaming 更新速率限流（防 over-fit single fill）
    ///
    /// Y1+Y2 行為：panic；Y3+ activation 後實作 rate-limited streaming update + cooldown
    fn throttle(&self, rate_per_sec: f64) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::throttle stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// 模型健康度（per ADR-0034 LAL gate criteria 對齊 evidence）
    ///
    /// Y1+Y2 行為：panic；Y3+ activation 後實作 streaming model 誤差 + drift +
    /// 樣本量綜合 health metric
    fn health(&self) -> Result<ModelHealth, M5Error> {
        unimplemented!(
            "M5 ModelClient::health stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }
}

// 支援 type stub（interface 預留，body 不在本 Sprint 寫實）
pub struct FeatureVector { /* Y3+ activation define */ }
pub struct Prediction { /* Y3+ activation define */ }
pub struct StreamingPrediction { /* Y3+ activation define */ }
pub struct DistributionMetrics { /* Y3+ activation define */ }
pub struct ModelVersion(pub String);
pub struct ModelHealth { /* Y3+ activation define */ }

#[derive(Debug)]
pub enum M5Error {
    NotImplemented,
    // Y3+ activation 擴展：DriftDetected / RollbackFailed / ThrottleExceeded etc.
}
```

### 2.2 6 method slot 鎖定理由（對齊 ADR-0035 §Decision 1）

| Method | 用途 | Y1+Y2 panic 理由 | Y3+ activation 後 IMPL 範圍 |
|---|---|---|---|
| `get_predict(features) -> Prediction` | 同步預測 baseline 包裝 | baseline 既有 IMPL 在 daily cron 路徑，trait 包裝 Y3+ 才 IMPL 避免雙路徑混亂 | 包裝既有 LightGBM/3DL predict + 加 streaming fallback chain |
| `get_predict_streaming(features) -> StreamingPrediction` | streaming 更新後即時推論 | 無 streaming model 物件存在 | rate-limited streaming weight update 後的 inference |
| `drift_callback(metrics)` | feature distribution 漂移回呼 | 無 drift detection 路徑 | KL divergence trigger → Strategist propose model rollback |
| `rollback(version)` | 模型回滾安全網 | 無 streaming model state，無 rollback target | streaming degrade → rollback to daily-batch baseline version |
| `throttle(rate_per_sec)` | streaming 更新速率限流 | 無 streaming update 路徑 | rate-limited update + cooldown (e.g. ≤ 0.1 update/sec) |
| `health() -> ModelHealth` | 模型健康度 (per ADR-0034 LAL gate) | 無 streaming 模型 evidence 可彙整 | streaming 誤差 + drift score + 樣本量 → composite health metric |

### 2.3 反模式 grep gate（防 stub 階段誤呼 / 誤改）

Sprint 1A-δ 結束後 E2 review + QA 必跑：

```bash
# Gate 1：production code 不可呼叫 6 method（除 trait 自己 definition）
rg --type rust -n "(get_predict_streaming|drift_callback|\.rollback\(|\.throttle\(|ModelClient::|ModelHealth)" \
    program_code/exchange_connectors/bybit_connector/openclaw_engine/src/ \
    --glob='!**/model_client.rs' \
    --glob='!**/tests/**'
# Expected: 0 hit Y1+Y2（Y3+ activation 後本 grep gate 解除）

# Gate 2：6 method 不可改為 default no-op（fail-loud 紀律）
rg --type rust -nB2 -A2 "fn (get_predict|get_predict_streaming|drift_callback|rollback|throttle|health)" \
    program_code/exchange_connectors/bybit_connector/openclaw_engine/src/ml/model_client.rs \
    | grep -E "Ok\(\(\)\)|Ok\(\w+\)" | grep -v "unimplemented"
# Expected: 0 hit（任何 method default impl 出現 Ok(()) / Ok(default) 而非 unimplemented! = 違反 ADR-0035 反模式 (b)）

# Gate 3：sibling panic test 必存在 6 case
rg --type rust -n "#\[test\]" program_code/exchange_connectors/bybit_connector/openclaw_engine/tests/m5_model_client_stub_panic.rs
# Expected: 6 case（每 method 各一 panic assertion）
```

---

## §3 Retirement Criteria — 4 條（per ADR-0035 §Decision 4）

per v5.8 §10 Risk #2 + ADR-0035 §Decision 4：trait + V114 placeholder 不是永久債務，必有明示退役條件。

### 3.1 R1 — Y3 末仍無 activation triggered → dead-code removal

**觸發條件**：Y3 末（Sprint 30 / W144 預估）ADR-0035 §Decision 3 (a)+(b)+(c) 3 條必要條件仍未全 PASS。

具體判斷：
- (a) daily-batch 不足 evidence 未達標（regime shift latency 觀察 < 6 month 樣本 OR M11 nightly replay divergence < N bps）
- (b) AUM < $50k sustained 30d
- (c) operator 未 opt-in M5 activation

**觸發行為**：
1. 開新 amendment ADR Supersede ADR-0035
2. dead-code removal PR：移除 `ModelClient` trait + 6 method stub + sibling panic test + V114 reserve frontmatter + `streaming_enabled` column（per ADR-0035 §Decision 2 預留欄）
3. 移除 cross-ADR ref（ADR-0036/0037/0038 中對 M5 的 placeholder ref）
4. Sprint 30 retirement audit report 寫入 `learning.adr_retirement_audit` table（per ADR-0034 audit pattern 延伸）

### 3.2 R2 — M5 被其他 module 吸收 → Supersede

**觸發條件**：M5 範疇被其他 module 完整覆蓋。具體 2 個常見路徑：

| 收編 module | 收編路徑 |
|---|---|
| **M9 A/B framework 擴 variant-as-streaming-update** | per ADR-0037 M9 A/B framework，若 M9 GA 後擴展 variant 概念為「per-fill streaming update 即是一個 variant 候選」→ streaming 更新由 M9 A/B framework 統一治理（control = daily-batch baseline / variant = streaming-updated weights），不需獨立 M5 trait |
| **M6 Bayesian reward weight tuning 已涵蓋 streaming 需求** | per ADR-未來（M6 待 ADR draft），若 M6 Bayesian reward weight 自動 tuning 邏輯本身已含「per-outcome weight 增量更新」→ streaming 更新需求被 M6 reward path 吸收 |

**觸發行為**：
1. 開新 amendment ADR Supersede ADR-0035
2. 移除 trait + V114 + `streaming_enabled` column（同 R1）
3. 收編 module（M9/M6）的 ADR 引用本 amendment 為 retirement evidence

### 3.3 R3 — operator 永久放棄 online learning 路徑

**觸發條件**：Live evidence 連續 12 month 顯示 daily-batch retrain 足夠 + AUM 增長已穩定 + operator 明示放棄 streaming 路徑。

**觸發行為**：
1. 開新 ADR Supersede ADR-0035
2. ADR-debt closure note：永久放棄 streaming 路徑，後續若再需要走完整 ADR 重新 propose
3. dead-code removal PR（同 R1）

### 3.4 R4 — 替代技術出現 → ADR amend

**觸發條件**：未來出現 OpenClaw 採用的 streaming ML framework（vendor SaaS / 開源 streaming library 如 River / Vowpal Wabbit 等），且 evaluation 後本 trait 設計不適用。

**觸發行為**：
1. 開新 amendment ADR + Sprint planning evaluation alternative
2. 若 alternative 採納 → ADR-0035 Supersede + trait refactor 或 deprecate

### 3.5 Retirement audit cadence

per ADR-0035 §Decision 4：

| 時點 | Sprint | Audit 內容 | Output |
|---|---|---|---|
| Y1 Review | Sprint 10 | R1-R4 retirement signal 評估 #1 | `learning.adr_retirement_audit` row + PM checkpoint |
| Y2 Q4 | TBD | retirement signal 評估 #2 | 同上 |
| Y3 Q2 | TBD | retirement signal 評估 #3 + 若 (a)(b)(c) PASS 啟動 amendment ADR + Y3+ activation Sprint planning | 同上 + activation ADR draft |
| Y3 末 | Sprint 30 / W144 | 最終 retirement audit | R1 觸發 → dead-code removal PR |

---

## §4 Cross-module Placeholder Integration（全標 Y3+ activation）

M5 streaming 路徑與其他 module 的整合介面預留位置（**全 Y3+ activation 後再寫實**，本 Sprint 不寫整合邏輯）：

### 4.1 M9 A/B framework variant 整合（ADR-0037）

**Y3+ activation 後角色**：streaming 模型必透過 M9 A/B framework 做 control vs variant 對比（per ADR-0035 §Decision 3 條件 (d) — M9 GA 為 activation 必要條件）。

**Sprint 1A-δ 階段**：trait `get_predict_streaming()` 為 M9 variant 統一介面預留；不寫 M9-side 整合 adapter。

### 4.2 M6 Bayesian reward weight 整合（待 ADR）

**Y3+ activation 後角色**：M5 streaming weight update 結果作為 M6 reward weight 一個 input feature；M6 reward 反饋作為 M5 throttle decision 一個 input。雙向 placeholder。

**Sprint 1A-δ 階段**：trait `throttle()` 預留接收外部 rate hint 介面；不寫 M6 整合 binding。

### 4.3 M11 nightly replay 整合（ADR-0038）

**Y3+ activation 後角色**：per ADR-0035 §Decision 3 條件 (a)1 — M11 nightly replay divergence ≥ N bps 持續觸發是 daily-batch 不足訊號。streaming 模型 GA 後，M11 replay 同時驗證 baseline vs streaming 兩條路徑。

**Sprint 1A-δ 階段**：trait `drift_callback()` + `health()` 為 M11 replay divergence signal 接收介面預留；不寫 M11 整合 adapter。

### 4.4 ADR-0034 Decision Lease LAL 整合

**Y3+ activation 後角色**：
- streaming 模型本身啟用 = ADR-0034 LAL 4 (capital structure / 新模塊啟用 → operator approval mandatory)
- streaming 更新引發的 strategy parameter shift = ADR-0034 LAL 1 (intra-strategy reparam)
- streaming 更新引發的 cross-strategy reweight = ADR-0034 LAL 2

**Sprint 1A-δ 階段**：trait 6 method 全 panic 不觸 LAL gate；Y3+ activation 後才接 LAL。

---

## §5 Acceptance Criteria（interface stub level only — 5 條）

Sprint 1A-δ M5 deliverable 驗收：

| # | 驗收標準 | 證據 |
|---|---|---|
| **AC1** | `ModelClient` trait 6 method slot 全在 trait definition 且 default impl 全為 `unimplemented!()` panic | `program_code/exchange_connectors/bybit_connector/openclaw_engine/src/ml/model_client.rs` 含 trait 定義 + grep `unimplemented` 6 hit |
| **AC2** | V114 reserve frontmatter spec doc 存在，cross-ref ADR-0035 + 本 spec | `srv/docs/execution_plan/2026-05-21--v114_m5_online_learning_reserved_schema_spec.md` 含 frontmatter `parent specs: ADR-0035 + 本 spec` + 14 section outline |
| **AC3** | production caller 0 hit（§2.3 反模式 grep gate 1 通過） | `rg ModelClient::` 在 src/ 非 model_client.rs + 非 tests/ 0 hit |
| **AC4** | sibling panic test 6 case 全存在且 `cargo test` 確認 6 case 全 panic | `program_code/exchange_connectors/bybit_connector/openclaw_engine/tests/m5_model_client_stub_panic.rs` 含 `#[test]` 6 個 + `cargo test --release m5_model_client` 6/6 expected panic |
| **AC5** | ADR-0035 §Decision 4 retirement audit cadence schema 預留（`learning.adr_retirement_audit` table 留 V114 spec 註明）| V114 spec §14 cross-V### dependency placeholder 中明示 retirement audit 表 Y3+ activation 後加 |

### 5.1 為什麼只列 5 條（非完整 12 條 spec acceptance）

per ADR-0035 status「IMPL Y3+」：本 spec 是 interface stub level，不含 streaming algorithm performance metric / drift detection accuracy / rollback rollback latency 等 Y3+ activation 後才有意義的 functional acceptance。Y3+ activation amendment ADR 開出後另寫完整 12 條 spec acceptance。

---

## §6 IMPL Phase

### 6.1 Sprint 1A-δ（本 Sprint）— interface stub only

| Item | Workload | Owner |
|---|---|---|
| `ModelClient` trait + 6 method default panic + support type stub | 3-4 hr | E1（per ADR-0035 §Sign-off table） |
| sibling panic test 6 case `tests/m5_model_client_stub_panic.rs` | 1-2 hr | E4 |
| V114 reserve frontmatter spec doc（本 spec sibling）| 1-2 hr | PA / E1 |
| 既有 `learning.model_versions` 表加 `streaming_enabled BOOL NOT NULL DEFAULT FALSE` column（per ADR-0035 §Decision 2）| 1-2 hr | E1（V### 改動需走 PG empirical dry-run per CLAUDE §七 + feedback_v_migration_pg_dry_run）|
| E2 review + QA grep gate（§2.3）| 1 hr | E2 / QA |
| **總計** | **7-11 hr**（對齊 ADR-0035 估算 8-12 hr） | |

### 6.2 Sprint 10 / Y2 Q4 / Y3 Q2 — retirement audit cadence

| Sprint | Item | Workload |
|---|---|---|
| Sprint 10 (Y1 Review) | retirement audit #1（評估 R1-R4 signal）| 1-2 hr |
| Y2 Q4 | retirement audit #2 | 1-2 hr |
| Y3 Q2 | retirement audit #3 + 若 (a)(b)(c) PASS → 啟動 activation amendment ADR | 2-4 hr |

### 6.3 Y3+ Activation Sprint（若 6 條件全 PASS）— 本 Sprint 範圍外

| Item | Workload |
|---|---|
| Streaming algorithm 選型 spec | 20-40 hr |
| 6 method 真實 IMPL（從 panic 改為實作）| 80-160 hr |
| V114 full DDL + healthcheck + writer code | 40-80 hr |
| M9 A/B framework variant integration | 20-40 hr |
| M11 replay divergence signal integration | 20-40 hr |
| Y3+ activation E2E QA + LAL 4 operator approval flow | 20-40 hr |
| **總計** | **200-400 hr**（per ADR-0035 line 18 估算）|

### 6.4 Y3 末（若未 activation）— retirement R1 觸發

| Item | Workload |
|---|---|
| dead-code removal PR + Supersede ADR | 4-8 hr |

---

## §7 Cross-V### Dependency Placeholder

### 7.1 V114 own（M5 own schema）

| V### | spec doc | Sprint | Status |
|---|---|---|---|
| **V114** | `2026-05-21--v114_m5_online_learning_reserved_schema_spec.md`（本 spec sibling） | 1A-δ（frontmatter only）+ Y3+ activation（full DDL） | Sprint 1A-δ = SPEC-PLACEHOLDER-RESERVED-Y3 |
| **`learning.model_versions` 加 `streaming_enabled` column** | 不在 V114；在 V104 or V### in-flight migration（per ADR-0035 §Decision 2）| Sprint 1A-δ | DEFAULT FALSE；Y3+ activation 時 ALTER DEFAULT TRUE |

### 7.2 Cross-module V### placeholder（其他 module 的 V###，本 spec 引用其 Y3+ activation 範圍）

| V### | Owner module | M5 引用範圍 | Sprint | Activation phase |
|---|---|---|---|---|
| **V108** | M9 A/B framework | M9 variant table 可能加 `streaming_update_id` column 引用 M5 streaming weight update audit row | Sprint 1A-δ frontmatter only / M9 GA 後 IMPL | Y3+ M5 activation 後 cross-link |
| **V110** | M6 Bayesian reward weight | reward weight history 表預留 `streaming_model_version_id` column 引用 M5 model version | Sprint 1A-δ frontmatter only | Y3+ M5 activation 後 cross-link |
| **V107** | M11 nightly replay | replay divergence 表預留 `model_path` enum (`baseline` / `streaming`) 雙路徑 evidence | Sprint 1A-δ frontmatter only | Y3+ M5 activation 後 cross-link |

**所有 cross-V### binding 全 Y3+ activation 後才寫實**；Sprint 1A-δ 階段僅 frontmatter cross-ref，不寫 SQL 整合。

---

## §8 Open Questions — ≥3

### Open Q #1 — ModelClient trait 6 method 名與泛 ML 套路衝突（高優先 / PA push back operator）

**衝突描述**：operator prompt 列的 6 method slot 為泛 ML 套路（`predict / update / save / load / version / metrics`），但 ADR-0035 §Decision 1 已鎖定的 6 method 為 `get_predict / get_predict_streaming / drift_callback / rollback / throttle / health`。兩套差異：

| Prompt 列 | ADR-0035 鎖定 | 差異本質 |
|---|---|---|
| `predict(features) -> Result<f64>` | `get_predict(features) -> Result<Prediction>` | 泛套路 vs 對齊既有 baseline 包裝 |
| `update(features, label)` | `get_predict_streaming(features)` | 直接 online learning update vs 推論介面（update 邏輯隱於 streaming model 內部）|
| `save(path) / load(path)` | `drift_callback / rollback` | 直接 persistence vs 漂移 + 回滾（persistence 走 V114 schema 不走 trait method）|
| `version() -> String` | `throttle(rate_per_sec)` | version metadata vs 速率控制（version 由 ModelHealth 結構返回）|
| `metrics() -> ModelMetrics` | `health() -> ModelHealth` | metric snapshot vs 健康度（health 範圍更廣含 drift / 樣本量 / 誤差）|

**PA 判斷**：採 ADR-0035 鎖定的 6 method。理由：
1. **真 SSOT 是 ADR-0035 §Decision 1**（per 16-root-principles-checklist + CLAUDE.md §五）；ADR Status = Proposed + operator sign-off 2026-05-21 已 land
2. **ADR 6 method 對齊 OpenClaw 既有 LightGBM/3DL daily-batch baseline 包裝意圖**（per ADR §Context line 25-35 「baseline 之上加層」）；泛套路 6 method 假設 from-scratch streaming model，與既有 ML infra 不符
3. **泛套路 `update(features, label)` 隱含 per-fill online update**，但 ADR §Decision 1 line 70 + §Decision 3 line 102「(d) M9 A/B framework 已 GA」要求 streaming update 必經 M9 A/B 對比 — `get_predict_streaming` + `throttle` 組合更符合 governance 紀律

**Open Q to operator**：是否確認採 ADR-0035 鎖定的 6 method（PA 推薦）？若 operator 偏好泛套路 6 method，需先 amend ADR-0035 §Decision 1，再 redispatch Sprint 1A-δ 工作。

### Open Q #2 — M5 是否 Y3+ 真的會 IMPL（retirement R1 預判機率）

**問題本質**：本 spec 為 interface stub 預留 8-12 hr 工作 + Y3+ activation 200-400 hr 工作。若 Y3 末 R1 觸發 → 18+ 個月後 4-8 hr dead-code removal。

**評估**：
- (+) M5 activation 機率 evidence：v5.8 §5 capital-tier ladder Y3 Q2 estimate $75-150k AUM 已超 $50k break-even（per ADR-0035 §Decision 3 條件 (b)）；regime shift latency 觀察若 Y2 Q4 顯示 daily-batch 不足機率 30-50%
- (-) R1 觸發 evidence：既有 LightGBM/3DL daily-batch baseline 已可承載多策略 + AUM < $50k 期間 ML infra 投入 ROI < 1；operator 偏好「最少代碼」（per memory `feedback_minimal_confirmation`）

**Open Q to PM**：若 PM 預判 Y3 末 R1 觸發機率 > 60%，是否考慮 ADR-0035 §Alternatives 已棄選的「Drop M5 entirely」路徑 reopen？（PA 不推薦 reopen，stub cost 僅 8-12 hr；但 PM 仲裁判斷）

### Open Q #3 — activation 6 條 hard gate 是否可調

**問題本質**：ADR-0035 §Decision 3 鎖定 6 條件 AND gate (a)(b)(c)(d)(e)(f) 全 PASS 才 activation。

**潛在風險**：
- (d) M9 A/B framework GA 依賴 ADR-0037 land + Sprint 1B+ IMPL；若 ADR-0037 在 Y3+ 仍 stub → M5 永遠卡 (d) 不能 activation → R1 觸發風險上升
- (e) Live PnL 連續 3 month > 0 依賴 P0-EDGE-1 closure；若 Y3 仍 P0-EDGE-1 未 close → (e) 永遠 FAIL
- (f) baseline Sharpe threshold X 未鎖定數值（per ADR-0035 §Decision 3 line 111 「由 Y3+ activation 時 PM + MIT 仲裁」）；Y3+ PM 仲裁可能定 X = 1.5 / 2.0 / 2.5 影響 activation timing

**Open Q to PM + MIT**：是否考慮 Y2 Q4 retirement audit 時對 6 條件做 sensitivity analysis（評估若 5/6 條件 PASS 但 1 條件 marginal 時是否走 conditional activation）？或維持嚴格 AND gate 紀律到 Y3 末？

### Open Q #4 — M5 trait vs M9 expansion 收編 boundary（per Retirement R2）

**問題本質**：ADR-0035 §Decision 4 R2 列「M9 A/B framework 擴 variant-as-streaming-update」為收編路徑。

**邊界不清**：
- M9 A/B framework 本意是「策略 A/B test」（per ADR-0037）；「variant 是 streaming update」是延伸用法
- 若 M9 A/B variant 真的能涵蓋 streaming update 治理需求 → M5 從一開始就不該獨立預留
- 反之若 M9 A/B variant 邊界是「策略級 / 大週期實驗」不適合 per-fill streaming 更新 → M5 必獨立

**Open Q to MIT + PM**：M9 A/B framework GA 後（預估 Sprint 1B 或 Sprint 2），是否安排一次 cross-architecture review 評估 M9 是否能收編 M5？若可收編，Sprint 1A-δ 預留的 M5 trait 是 8-12 hr 沉沒成本（接受）但 Y3+ activation 200-400 hr 可省。

---

## §9 §二 16 原則合規確認（interface stub level）

per 16-root-principles-checklist + ADR-0035 §二 16 根原則合規確認：

| # | 原則 | 本 spec interface stub 階段合規 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | trait 6 method 全 panic；無寫入路徑 |
| 2 | 讀寫分離 | ✅ | trait stub 不寫 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | trait stub 不發 proposal；Y3+ activation 後 proposal 走 R-2 Strategist |
| 4 | 策略不繞風控 | ✅ | trait stub 不繞 Guardian；Y3+ activation 走 LAL 4 |
| 5 | 生存 > 利潤 | ✅ | activation 條件 (e) Live PnL 連續 3 month > 0 = evidence-gated |
| 6 | 失敗默認收縮 | ✅ | 6 method default panic（fail-loud）+ `streaming_enabled` DEFAULT FALSE + R1 dead-code removal |
| 7 | 學習 ≠ live | ✅ | trait stub 在 learning surface；Y3+ activation 經 M9 A/B framework 驗 alpha 才上 Live |
| 8 | 交易可解釋 | ✅ | V114 reserve frontmatter 預留 per-streaming-update audit row schema（Y3+ activation 時 DDL） |
| 9 | 雙重防線 | ✅ | `rollback()` + `health()` method slot 預留 + Y3+ activation 後 streaming model 誤差 → rollback to baseline |
| 10 | 分離事實 / 推論 / 假設 | N/A | interface stub 不涉 reasoning 紀錄 |
| 11 | Agent 自主在 P0/P1 內 | ✅ | trait stub 不擴 agent 能力；Y3+ activation 後新模塊啟用走 LAL 4 |
| 12 | Evidence-based evolution | ✅ | 6 activation 條件全 evidence-based |
| 13 | cost 感知 | ✅ | stub Y1 cost 8-12 hr；full IMPL 200-400 hr 推 Y3+ ROI 成立才啟動；R1 dead-code 防永久債 |
| 14 | 零外部成本 | ✅ | streaming 默認自建（沿用 LightGBM/3DL infra）；R4 引入 vendor SaaS 走 amendment |
| 15 | 多 agent 形式化協作 | ✅ | Sprint 1A-δ dispatch 涉 PA/MIT/TW/E1/E4 等 role |
| 16 | Portfolio > 孤立 trade | ✅ | streaming reparam 走 LAL 1 / 2，LAL 2 = portfolio 級治理 |

---

## §10 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via Sprint 1A-δ M5 interface stub deliverable | 2026-05-21 | 🟡 PENDING（待 Open Q #1 仲裁 + 本 spec PM sign-off）|
| PA | 本 spec 起草（ADR-0035 IMPL 邊界 spec interface stub level）+ Open Q #1-#4 push back | 2026-05-21 | ✅ Drafted |
| MIT | trait 6 method slot 設計確認 + Open Q #2-#4 評估 | TBD（Sprint 1A-δ）| 🟡 PENDING |
| E1 | trait IMPL（default panic）+ V114 reserve frontmatter + `streaming_enabled` column V### 改動 | TBD（Sprint 1A-δ）| 🟡 PENDING |
| E4 | sibling panic test 6 case + cargo test verify | TBD（Sprint 1A-δ）| 🟡 PENDING |
| E2 | trait IMPL review + §2.3 反模式 grep gate 3 條 | TBD（Sprint 1A-δ）| 🟡 PENDING |
| QA | grep gate 3 條 + Sprint 1A-δ closure | TBD（Sprint 1A-δ）| 🟡 PENDING |
| PM | Open Q #1-#4 仲裁 + Sprint 10 / Y2 Q4 / Y3 Q2 retirement audit 仲裁 | TBD | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium M5 Online Learning Interface Reserved DESIGN spec — ModelClient trait 6 method default panic + V114 reserve placeholder cross-ref + Retirement R1-R4 + Cross-module placeholder + 5 AC + 4 Open Q（Sprint 1A-δ deliverable per ADR-0035 IMPL 邊界 spec interface stub level；full module DESIGN deferred Y3+ activation）*
