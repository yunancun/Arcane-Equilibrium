# EDGE-P3-1 · Realized Edge Predictor — 功能規格
# Realized Edge Predictor — Functional Specification
# 狀態：FA 起草 v1.0（等待 PA/ML-MIT/AI-E/CC 平行展開）
# 日期：2026-04-15
# Owners：FA 主筆 · PA 架構 · ML-MIT 模型 · AI-E 接線 · CC 審查

---

## 0. 一頁摘要（TL;DR）

**Problem**：`shrunk_bps`（James-Stein 靜態收縮）是策略-符號 cell 的**歷史平均** edge，backward-looking，不感知單筆交易當下的 regime / confluence / position state。cost_gate 用同一個 cell 數值對待「同策略同符號」所有機會，導致 Phase 5 坍塌（全 cell 收斂到 -35.72 bps）。

**Solution**：訓練一個 per-strategy quantile LightGBM 模型，輸入**決策瞬間**的 feature 快照，輸出 `realized_net_edge_bps` 的 (q10, q50, q90) 三分位預測。cost_gate 新決策：`q50 − k × (q50 − q10) > cost` 才放行，`q10 > 0` 才加倉。

**Invariant**：(1) shadow mode ≥14d；(2) feature freeze at entry instant；(3) per-strategy 獨立；(4) 推理失敗 fail-closed → 回退現有 shrinkage；(5) 不觸 LinUCB（互補，不替代）。

**Blast radius**：Rust `intent_processor::gates` 新增 `edge_predictor_gate()`，feature flag `use_edge_predictor` 控，預設 `false`。停滯時 shrinkage 路徑未動。

---

## 一、Context（為什麼不是已完成任務）

### 1.1 shrunk_bps 的三個結構缺陷

| 缺陷 | 具體表現 | 本規格如何解決 |
|---|---|---|
| **Backward-looking** | cell 值是過去 30d 成交平均，今日極端行情/極高 funding/極大 spread 全部被抹平 | 用**決策瞬間** feature 快照作為條件，預測當前條件下的 conditional edge |
| **Marginal, not conditional** | 同一 (strategy, symbol) cell 對所有信號等同處理；ADX=15 與 ADX=45 共用一個 shrunk 數值 | per-decision 預測，每筆輸入獨立條件向量 |
| **Self-fulfilling**（見 `memory/project_edge_data_isolation.md`）| 過去 edge 負 → cost_gate 更寬鬆 → 低質信號放過去 → 新 edge 更負 → 負反饋循環 | shadow mode ≥14d 下預測器不改交易流；promote 後 q10 threshold 限制低質機會進場 |

### 1.2 LightGBM 管線與 LinUCB 的關係

現狀（2026-04-14）：
- **LightGBM 管線**：`run_training_pipeline.py` / `scorer_trainer.py` / `parquet_etl.py` / `onnx_exporter.py` 骨架就緒但 `load_training_data()` 未實現（阻塞 dry-run）。CPCV + embargo 已 live。
- **LinUCB**：15 arm（5 strat × 3 regime）ridge 已 live，寫 `learning.linucb_state`，Rust `decision_context_producer.rs` 讀之寫入 `linucb_arm_id` 用於 DB 觀測。**但 LinUCB 不 gate 交易**，只是記錄用。
- **cost_gate**：Rust `intent_processor::gates::cost_gate_paper/moderate/live`（gates.rs:30-192）消費 `shrunk_bps`，是唯一交易放行決策。

**定位**：edge predictor 取代 `shrunk_bps` 作為 cost_gate 的數值來源。LinUCB 不動——兩者語義正交（bandit 選 arm，GBM 評 arm 的 ex-ante edge；未來可把 LinUCB 的 `confidence_bound` 作為 predictor 的 feature）。

### 1.3 Phase 5 cost_gate 與本規格的關係

Phase 5（促進/降級管線）暫停原因：所有策略 gross edge ≈ 0，promotion criteria 無對象可升。本規格 **不是 Phase 5 的前置**——Phase 5 要等策略本身有正 edge（EDGE-P0/P1/P2 工作）才能推動。本規格的價值是：**把 cost_gate 從靜態平均升級為條件預測**，讓 strategy 層即使 gross edge 接近 0，net edge 也能被條件選擇放大（挑 regime / confluence / cost 最有利的子集進場）。

---

## 二、模型規格

### 2.1 模型家族

- **算法**：LightGBM Quantile Regression（`objective='quantile'`, `alpha∈{0.1, 0.5, 0.9}`）
- **三個獨立模型**：`q10_model`, `q50_model`, `q90_model`（同一個 training set，三次 fit）
- **Per-strategy 獨立訓練**：5 個策略（ma_crossover / bb_reversion / bb_breakout / grid_trading / funding_arb）× 3 分位 = **15 個 ONNX artifact**
- **為什麼 per-strategy**：Simpson paradox 風險——不同策略對同一 feature（如 adx_1h）的 edge 響應曲線方向可能相反（trending 策略 love high adx，mean-reversion 策略 hate it）。合併訓練會平均掉真實信號。

### 2.2 Calibration

- **目標**：q50 預測值 = 真實條件中位數；預測分位覆蓋率對齊名義分位（q10 命中率 ≈ 10%, q90 ≈ 90%）
- **方法**：Isotonic regression on held-out CPCV fold
- **驗收**：coverage error < 3% per quantile on held-out（Phase 2 promote gate）

### 2.3 不使用的方案（明確排除）

| 方案 | 為何不選 |
|---|---|
| Point regression（單 MSE 模型）| 丟失不確定性，下游無法做 `q10 > 0` 加倉決策 |
| Neural net / Transformer | 樣本量不足（demo 30d ~幾千筆），過擬風險 × 推理延遲 × 訓練成本 |
| Gaussian mixture | 需要假設分佈族，crypto fat-tail 違反 |
| Bayesian hierarchical | 研究價值高但工程複雜；未來 v2 可考慮疊加 |

---

## 三、Feature Contract（凍結時點與可得性）

### 3.1 Freeze-Time 規則（不可違背）

Feature vector 在 `StrategyAction::Open` 被 emit 的**同一 tick**快照；後續任何事件（撮合、slippage 回補、partial fill）都不可改寫該 vector。違反即 look-ahead leakage。

### 3.2 Feature 清單（v1，schema_hash 鎖定）

| Feature | 類型 | 單位 | 現狀 | 來源 / 計算 |
|---|---|---|---|---|
| **Regime** ||||
| `adx_1h` | f32 | 點 | ✅ 可得 | `IndicatorSnapshot.adx`（1h TF） |
| `bb_width_pct` | f32 | % | ✅ 可得 | `IndicatorSnapshot.bollinger.bandwidth`（5m TF） |
| `atr_pct` | f32 | % | ✅ 可得 | `IndicatorSnapshot.atr_14.atr_percent`（5m TF） |
| `funding_rate` | f32 | 小數 | ✅ 可得 | `TickContext.funding_rate`（EDGE-P1-2 已接） |
| `basis_bps` | f32 | bps | ⚠️ 需接 | `(index_price - last_price) / mid × 10000`；`index_price` 已在 `TickContext` |
| **Strategy** ||||
| `strategy_id` | i8（enum → int）| — | ✅ 可得 | 訓練時作為模型 selector（per-strategy 模型則此 feature 可省） |
| `confluence_score` | f32 | 0-65 | ⚠️ 需暴露 | 現存於每策略 state；需經 `OrderIntent.metadata` 傳出 |
| `persistence_elapsed_ms` | u32 | ms | ⚠️ 需暴露 | `PersistenceTracker` 每策略獨立；同上 |
| `side` | i8 | {-1, +1} | ✅ 可得 | `intent.is_long ? 1 : -1` |
| **Position** ||||
| `notional_pct_of_bal` | f32 | % | ✅ 可得 | `qty × price / paper_state.balance()` |
| `concurrent_positions` | u8 | count | ✅ 可得 | `paper_state.position_count()` |
| `same_direction_cnt` | u8 | count | ⚠️ 需接 | 在 `paper_state.positions` 按 `is_long == intent.is_long` 計數 |
| **Cost** ||||
| `spread_bps` | f32 | bps | ✅ 可得 | `(ask - bid) / mid × 10000`（PriceEvent 已含 bid/ask） |
| `expected_slippage_bps` | f32 | bps | ✅ 可得 | `gates.rs::lookup_slippage(volume_24h)` 已存在，暴露為 feature |

**總計**：14 features（若 per-strategy 訓練去掉 `strategy_id` → 13）。

### 3.3 Feature schema hash

- 計算：`sha256('\n'.join(sorted(feature_names))).hexdigest()[:16]`
- 存儲：每個 model artifact 的 metadata 內；Rust 推理端 load 時比對，不匹配 fail-closed fallback
- 變更規則：**任何 feature 增刪必須遞增 schema_version**，舊模型 artifact 永不兼容新 schema（防止 silent train-serve skew）

### 3.4 明確排除的 features（v1）

- 單 tick bid/ask 絕對值（非 stationary）
- 原始 price / volume 絕對值（只用 normalized 衍生物）
- 實時 unrealized PnL of other positions（防自相關泄漏）
- 任何 t+1 可見資訊（明顯 look-ahead）

---

## 四、Label Contract

### 4.1 公式

```
realized_net_edge_bps = (exit_price - entry_price) / entry_price × side × 10000
                        - (entry_fee_bps + exit_fee_bps)
```

**等價於**：
```
realized_net_edge_bps = gross_edge_bps - round_trip_fees_bps
```

### 4.2 Close 歸屬規則

| close_tag 類別 | 歸屬 |
|---|---|
| `strategy_close:signal_flip` / `strategy_close:target` | 該筆 sample 保留，label = 真實 net edge |
| `risk_close:*`（各種強平）| 該筆 sample 保留，label 為真實 net edge（**包含**被強平的負值——這正是 predictor 應學到的模式） |
| `stop_trigger:hard_stop` / `stop_trigger:trailing_stop` / `stop_trigger:time_stop` | 同上，保留 |
| `orphan_close:*` | 該筆 sample **排除訓練集**（外部事件，非策略預期路徑） |

### 4.3 Partial fill 處理

- 當前 `emit_close_fill` 按 FIFO 對每個 position 記錄單次 entry / 單次 exit（見 EDGE-P2-1 修復後的 close_tag schema）
- **v1 假設**：one entry → one exit，無 pyramid
- Monitoring：`realized_edge_stats.py::_pair_round_trips()` 若 unmatched qty > 5% 發告警（已存在）

### 4.4 Label clamp

- Hard clamp：`label ∈ [-500, +500]` bps（±5%）
- 超限樣本保留原值進入 DB，但訓練時截斷（防極端 outlier 主導 loss）

---

## 五、Data Pipeline

### 5.1 Feature Store Schema

**新表**：`learning.decision_features`（SQL migration 由 PA 負責）

```sql
CREATE TABLE learning.decision_features (
    context_id        TEXT PRIMARY KEY,  -- entry-time context_id (make_context_id(em, symbol, ts_ms))
    ts                TIMESTAMPTZ NOT NULL,
    engine_mode       TEXT NOT NULL,     -- 'paper' | 'demo' | 'live'
    strategy_name     TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    side              SMALLINT NOT NULL, -- -1 or +1
    feature_schema_version  TEXT NOT NULL, -- 'v1'
    feature_schema_hash     TEXT NOT NULL, -- 16-hex sha256
    features_jsonb    JSONB NOT NULL,    -- { adx_1h: 22.3, bb_width_pct: 1.8, ... }
    -- Label 回填（close fill 時 UPDATE）
    label_net_edge_bps  DOUBLE PRECISION,  -- NULL 代表尚未平倉
    label_close_tag     TEXT,              -- NULL 代表尚未平倉
    label_filled_at     TIMESTAMPTZ
);
CREATE INDEX ON learning.decision_features (ts DESC);
CREATE INDEX ON learning.decision_features (strategy_name, engine_mode, ts DESC);
```

**為何 JSONB + 固定 schema_hash 雙軌**：
- JSONB 允許未來 schema 演化無需 migration
- schema_hash 鎖定訓練與推理特徵一致性，防 silent skew

### 5.2 寫入時機

| 事件 | 動作 |
|---|---|
| `StrategyAction::Open` 被接受（過 H0 + cost_gate） | Rust emit `DecisionFeatureSnapshot` message → Python consumer UPSERT INSERT |
| Close fill 觸發（無論 strategy / risk / stop） | Python job 按 `(engine_mode, symbol, strategy, entry_ts)` 回找未標註的 feature row，UPDATE label 字段 |

### 5.3 Entry → Close 關聯

**問題**：當前 `emit_close_fill` 生成的 `context_id = make_context_id(em, symbol, close_ts_ms)` 與 entry 時的 context_id 不同（時間不同），無法直接 JOIN。

**方案**：
- `PaperPosition` 結構新增字段 `entry_context_id: String`
- `StrategyAction::Open` 寫入 position 時保存
- `emit_close_fill` 將 `entry_context_id` 一併寫入 fill row（`trading.fills` 新增 `entry_context_id` 列）
- Label 回填 job：`UPDATE learning.decision_features SET label = ... WHERE context_id = fill.entry_context_id`

（PA 負責 SQL migration + Rust struct 擴展；AI-E 負責 emit path 改造）

### 5.4 ETL 流程

- **Shadow 期**：每日 cron，`decision_features + label` → parquet → 訓練
- **Active 後**：同上，外加 real-time drift 監控
- **批量參數**：30d rolling window（初期），後續按 fill 量調整

### 5.5 Paper / Demo 隔離（延續 `project_edge_data_isolation.md`）

- Paper fills → `decision_features WHERE engine_mode='paper'` → 訓練 `edge_predictor_paper_<strategy>.onnx`（僅觀察用）
- Demo + Live fills → `engine_mode IN ('demo','live')` → 訓練 `edge_predictor_prod_<strategy>.onnx`（cost_gate 消費）
- 推理時按引擎選 artifact：paper engine 讀 paper 模型，demo/live engine 讀 prod 模型

---

## 六、Training Pipeline

### 6.1 分割方式

- **CPCV**（Combinatorial Purged Cross-Validation）— 複用 `cpcv_validator.py` 既有實現
- **Purge window**：2h（防 label 泄漏到訓練集）
- **Embargo window**：24h（防 overlap；funding_arb 策略加長至 72h）
- **Folds**：5
- **Holdout tail**：最近 7d 嚴格 holdout，不入 CPCV，用於最終 promote gate 驗證

### 6.2 Loss & Metrics

| 指標 | 用途 | 驗收門檻 |
|---|---|---|
| Pinball loss (per quantile) | 訓練目標 + CPCV 交叉驗證 | vs 常數分位基線（數據全局分位）改善 >10% |
| Quantile coverage | calibration 驗收 | \|empirical - nominal\| < 3% per quantile |
| Decile lift | 業務驗收 | top decile predicted q50 對應真實 edge > median decile 兩倍 |
| Train-serve skew | 生產驗證 | Rust 推理結果 vs Python 原始預測，max abs error < 1e-3 |

### 6.3 Hyperparameter（默認，Optuna 可微調）

```python
{
    'objective': 'quantile',
    'alpha': <0.1|0.5|0.9>,
    'metric': 'quantile',
    'num_leaves': 15,          # 樣本少→小樹防過擬
    'learning_rate': 0.05,
    'n_estimators': 200,
    'min_data_in_leaf': 20,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'lambda_l2': 0.1,
}
```

（ML-MIT 負責 Optuna TPE，預算 100 trials per strategy per quantile；Layer 2 hyperparams 由 TPE 覆蓋）

### 6.4 訓練觸發

- **v1**：手動 trigger（`run_training_pipeline.py` CLI），shadow 期每週一次
- **Active 後**：cron 每日訓練 + shadow-shadow 對照（新模型與線上模型同 tick 推理，差異記錄；差異 >20% 觸發告警）

---

## 七、Inference Pipeline（Rust 側）

### 7.1 ONNX Runtime 選擇

現狀：Rust 側無 ONNX runtime。

**選項評估**（AI-E 最終決定，此處給建議）：

| Crate | Pros | Cons |
|---|---|---|
| **`ort`** | 成熟穩定（ONNX Runtime 官方 binding）· 支援 GPU（未來）· 社群活躍 | 外部 C++ 依賴 (~60MB)；build 複雜 |
| **`tract-onnx`** | 純 Rust · 無外部依賴 · build 簡單 | 運算符覆蓋較窄 · 性能差一點（但 LightGBM ONNX 都是基本算子，夠用） |

**建議**：`tract-onnx`（純 Rust、build 簡單、LightGBM 操作符全支援）；`ort` 作為未來深度模型（DL3 foundation 等）備案。

### 7.2 模型加載與熱重載

- **新模組**：`rust/openclaw_engine/src/edge_predictor/`
  - `mod.rs` — `EdgePredictor` trait + 工廠
  - `tract_backend.rs` — tract-onnx 具體實現
  - `null_backend.rs` — 關閉時的 no-op 實現（永遠返回 `Err(NoModel)`，讓 gate 走 fallback）
- **加載路徑**：啟動時從 `settings/models/edge_predictor_<mode>_<strategy>.onnx` 讀
- **熱重載**：`Arc<ArcSwap<EdgePredictor>>` 包裝，IPC `PipelineCommand::ReloadEdgePredictor { strategy, path }` 觸發
  - 注意：現有 `EdgeEstimates` 不是 ArcSwap（見審計），本規格新增 ArcSwap 包裝不觸動既有路徑
- **Schema hash 驗證**：load 時比對 model metadata 與 hardcoded `FEATURE_SCHEMA_HASH_V1`，不匹配 → log error + 不替換（當前 model 不變）

### 7.3 Gate 新決策

**新函數**：`intent_processor::gates::edge_predictor_gate()`

```rust
// 偽代碼
fn edge_predictor_gate(ctx, features, config) -> GateDecision {
    let predictor = match predictor_store.load_for_strategy(strategy_id) {
        Some(p) => p,
        None => return fallback_shrinkage_gate(ctx, features, config),
    };
    let pred = match predictor.predict(&features.to_vec()) {
        Ok(p) => p,
        Err(_) => return fallback_shrinkage_gate(ctx, features, config),  // fail-closed
    };
    // pred = (q10, q50, q90)
    let cost_bps = estimate_round_trip_cost_bps(features.spread_bps, features.expected_slippage_bps);
    let k = config.quantile_safety_k;  // 預設 0.5
    let safety_margin = pred.q50 - k * (pred.q50 - pred.q10);
    if safety_margin < cost_bps {
        return GateDecision::Reject("predictor_cost_margin_insufficient");
    }
    // 可選：加倉條件
    if pred.q10 < 0.0 && config.require_q10_positive_for_adds {
        return GateDecision::RejectAdd("q10_negative");
    }
    GateDecision::Accept
}
```

**Config 新字段**（RiskConfig 內）：
```toml
[edge_predictor]
use_edge_predictor = false       # 預設關閉
shadow_mode = true               # 推理 + 記錄，但不影響 gate
quantile_safety_k = 0.5
require_q10_positive_for_adds = true
fallback_on_error = "shrinkage"  # shrinkage | reject_all | accept_all
```

### 7.4 Fail-Closed 回退鏈

```
edge_predictor.predict()
  ├─ Ok(pred) → edge_predictor_gate logic
  └─ Err / no model
      └─> fallback_shrinkage_gate (現有 cost_gate_paper / moderate / live)
          ├─ paper: fail-open exploration（現狀）
          ├─ demo:  block negative（現狀）
          └─ live:  fail-closed（現狀）
```

Shadow 期整條 edge_predictor_gate 不影響交易流，只輸出 DecisionContextMsg 記錄 `predicted_q10/q50/q90` 到 `learning.decision_context_snapshots`。

### 7.5 推理性能預算

- **目標**：per-prediction < 1ms（H0 SLA 預算內）
- **tract-onnx 實測**：14-feature LightGBM 200-tree 模型通常 < 200μs（CPU）
- **每 tick 最多 1 次推理**（StrategyAction::Open 時），對 tick 處理 overhead < 1%

---

## 八、Rollout Stages

### 8.1 Stage 0 — Feature 接線（AI-E）

- 暴露 `confluence_score` / `persistence_elapsed_ms` 至 OrderIntent.metadata
- 接 `basis_bps` / `same_direction_cnt`
- `PaperPosition.entry_context_id` 字段 + emit path
- 新 `DecisionFeatureSnapshot` IPC message + Python consumer

**驗收**：`learning.decision_features` 表出現記錄；隨機抽 10 筆人工覆核 feature 正確性。

### 8.2 Stage 1 — Label 回填（PA）

- `trading.fills.entry_context_id` 列 migration
- Label backfill job：close fill event → UPDATE `decision_features.label_*`
- Reconcile job：檢測 7d 前仍 label_net_edge_bps IS NULL 的 row（漏了的 close fill）並告警

**驗收**：demo 模式 48h 運行後，label 填充率 > 95%。

### 8.3 Stage 2 — 訓練管線（ML-MIT）

- `run_training_pipeline.py::load_training_data()` 補實作
- Per-strategy CPCV + quantile LGBM + Isotonic calibration
- Pinball loss / decile lift 報告生成
- ONNX 匯出 + precision validation

**驗收**：5 策略各 3 分位共 15 個 ONNX artifact 產出，pinball 改善 >10%，coverage error <3%。

### 8.4 Stage 3 — Shadow Mode（AI-E + PA）

- `use_edge_predictor=true` + `shadow_mode=true`
- 引擎每 Open 決策並行跑 predictor.predict()，結果寫 decision_context_snapshots
- 繼續使用現有 shrinkage gate 決定交易

**驗收**：
- Shadow 期 ≥14d
- Predictor 推理 failure rate < 0.1%
- Train-serve skew（同一 feature vector，Rust 推理 vs Python 原始）max abs err < 1e-3
- Decile lift 在 shadow 數據上持續成立

### 8.5 Stage 4 — Promote to Active（Operator 確認）

- 切 `shadow_mode=false`，edge_predictor_gate 真正影響交易
- **先在 Paper engine 激活**，觀察 7d
- **Demo engine 激活**需額外 7d Paper 正常數據
- **Live engine 激活**：永久禁止自動，operator 手動確認 + 21d demo 穩定才能開

**Promote gate**：
- Shadow 14d + Paper active 7d = 21d 無異常
- Decile lift 維持 baseline × 1.5 以上
- 推理 latency p99 < 2ms
- 任何嚴重不對齊 → 自動 revert shadow

### 8.6 Rollback 機制

- 任何 promote 後問題 → IPC `PipelineCommand::SetEdgePredictorShadow { shadow_mode: true }` 即時回到 shadow
- 完全關閉：`use_edge_predictor=false` → 純 shrinkage 路徑（即現狀）
- Artifact 管理：舊版本 ONNX 永保留 14d（`settings/models/archive/`），rollback 可選任一歷史版本

---

## 九、Safety Invariants（不可違背，CC 必查）

1. **Shadow ≥14d + Paper ≥7d 才能 promote**
2. **Feature freeze at entry instant**，禁止 close 後回看調整任何 feature
3. **Per-strategy 獨立模型**，禁止合併訓練
4. **推理失敗 fail-closed → shrinkage 回退**；禁止推理錯誤時放行交易
5. **不觸 LinUCB**（blast radius 限縮）
6. **schema_hash 不匹配 fail-closed**，禁止 silent skew
7. **Paper / Demo / Live 模型分離**，Paper fills 禁止污染 prod 模型
8. **Live active 需 operator 手動確認**，禁止自動 promote 到 live
9. **Label 僅來自真實 close fill**，禁止插值或預測回填
10. **Outlier clamp 僅在訓練時**，DB 原始 label 保留真實值

---

## 十、Observability

### 10.1 Metrics（必須記錄）

| Metric | 標籤 | 用途 |
|---|---|---|
| `edge_predictor_predict_latency_ms` | strategy, quantile | 推理性能監控 |
| `edge_predictor_predict_errors` | strategy, error_type | 失敗率監控 |
| `edge_predictor_shadow_vs_shrinkage_disagree_rate` | strategy | shadow 期決策差異率 |
| `edge_predictor_feature_missing_count` | strategy, feature | 上游 feature 缺失 |
| `edge_predictor_schema_hash_mismatch` | strategy | train-serve skew 早期信號 |
| `edge_predictor_decile_lift_rolling_7d` | strategy | 模型退化預警 |

### 10.2 Dashboards（Grafana）

- **Panel 1**：per-strategy predict latency p50/p95/p99
- **Panel 2**：shadow agreement rate（predictor 決策 vs shrinkage 決策）
- **Panel 3**：decile lift rolling 7d
- **Panel 4**：feature coverage（每 feature non-null 比例）

### 10.3 Alerts

- **P1**：`schema_hash_mismatch > 0` — 立即關閉該策略 predictor
- **P2**：`predict_errors > 5%` 連續 1h — 切回 shadow + 查 log
- **P3**：`decile lift < 1.0` 連續 3d — 人工審查是否需要 retrain

---

## 十一、Scope / Out of Scope

### 11.1 In Scope（v1）

- 5 策略 × 3 分位 = 15 個 per-strategy ONNX
- 14 feature schema v1
- Rust tract-onnx 推理 + Arc<ArcSwap> 熱重載
- cost_gate 新增 `edge_predictor_gate()` + shrinkage fallback
- shadow → paper active → demo active 三階段 rollout
- `learning.decision_features` 表 + label backfill
- `trading.fills.entry_context_id` 列

### 11.2 Out of Scope（延後 v2）

- LinUCB ↔ edge_predictor 雙向整合（v1 只單向：LinUCB confidence 作 feature 可選 later）
- Live engine 自動 promote（v1 永遠手動）
- Foundation model (DL3 TimesFM/Chronos) 作為 feature（v2 加）
- Bayesian hierarchical 疊加（v2 研究）
- Deep learning 替代 LGBM（v2+，需要樣本量增長）
- 多時間尺度 label（1h / 4h / 24h 條件預測；v1 只用實際持倉期 realized edge）

### 11.3 明確不做

- **不動現有 LinUCB ridge state / arm selection**
- **不改 cost_gate_live 的 fail-closed 語義**
- **不改 James-Stein shrinkage pipeline**（保留作為回退）
- **不移除 `edge_estimates.json`**（shrinkage fallback 依賴）

---

## 十二、分工交接清單（FA → PA/ML-MIT/AI-E/CC）

### 12.1 PA（架構）— 3 件

1. **SQL migration** `learning.decision_features` + `trading.fills.entry_context_id`（§5.1 + §5.3）
2. **Feature store ETL 接入** `parquet_etl.py`（§5.4）
3. **Label backfill job** + reconcile（§8.2）

### 12.2 ML-MIT（模型）— 4 件

1. **補 `load_training_data()`** in `run_training_pipeline.py`（§6.4 前置）
2. **Quantile LGBM + CPCV + Isotonic calibration** per-strategy 訓練流（§二 + §6）
3. **Pinball loss / decile lift / coverage 報告** 輸出
4. **ONNX 匯出 + precision validation**（既有 `onnx_exporter.py` 加 quantile 模型適配）

### 12.3 AI-E（接線）— 6 件

1. **新 Rust `edge_predictor/` module**（§7.1-7.2；`mod.rs` + `tract_backend.rs` + `null_backend.rs`）
2. **Feature 暴露**：`confluence_score` / `persistence_elapsed_ms` / `basis_bps` / `same_direction_cnt` / `expected_slippage_bps` → `FeatureVectorV1` struct
3. **`PaperPosition.entry_context_id` 字段** + `emit_close_fill` 寫 `entry_context_id`（§5.3）
4. **`DecisionFeatureSnapshot` IPC message** + Python consumer 寫 PG
5. **`edge_predictor_gate()` function** + `RiskConfig.edge_predictor` section（§7.3）
6. **`PipelineCommand::ReloadEdgePredictor` / `SetEdgePredictorShadow`** IPC（§7.2, §8.6）

### 12.4 CC（審查）— 7 項必查

1. **Label leakage 檢查**：feature vector 內是否有任何 close 後才可得的量
2. **Train-serve skew 檢查**：Python LGBM vs Rust tract 推理同 input 的 max abs error <1e-3
3. **Fail-closed 回退路徑**：`edge_predictor.predict()` 拋錯 → shrinkage gate 被調用（不是被繞過）
4. **Schema hash 防呆**：不匹配時載入失敗而非 silent skew
5. **Per-strategy 隔離**：策略 A 的模型不會被策略 B 調用
6. **Paper / Demo / Live 模型檔隔離**：paper 訓練 artifact 不會被 prod engine 載入
7. **Regression tests**：新增 `edge_predictor_tests.rs`（推理 / fallback / schema mismatch / hot-reload），最少 15 個 case

### 12.5 FA（持續 owner）

- 本 spec 維護 + v2 planning
- Stage gate 決策（promote / rollback）
- 每週 metrics review（shadow → paper → demo）

---

## 十三、時程估計（草案，實際由 PA 調整）

| Stage | 工作量 | 前置 |
|---|---|---|
| Stage 0 Feature 接線 | AI-E ~8h | FA spec（本文件） |
| Stage 1 Label 回填 | PA ~6h | Stage 0 部分完成 |
| Stage 2 訓練管線 | ML-MIT ~12h | Stage 1 `decision_features` 有數據 |
| Stage 3 Shadow 14d | 計時等數據 | Stage 0-2 全部完成 |
| Stage 4 Paper active 7d | 計時 | Shadow pass |
| Stage 5 Demo active 7d | 計時 + operator 確認 | Paper active pass |
| Stage 6 Live（永遠手動）| 2026-05-16+ | Demo active + 21d 穩定 + operator 放行 |

**最早投產日期**：Stage 0-2 實施 ~26h 工時 → 2026-04-18 完成 → shadow 開跑 → 2026-05-02 promote paper → 2026-05-09 promote demo → 2026-05-30+ live（視穩定度）。

**關鍵路徑**：`Stage 0 (AI-E) → Stage 1 (PA) → Stage 2 (ML-MIT) → Stage 3 (14d)`。PA / ML-MIT / AI-E 可部分並行（特別是 Stage 2 ML-MIT 可在 Stage 1 剛開始時並行補 `load_training_data()` 和單元測試）。

---

## 十四、FAQ / 邊界情況

**Q1：Paper fills 怎麼訓出 prod 模型？**
A：不會。Paper 訓 paper artifact（僅觀察），Demo+Live fills 訓 prod artifact。見 §5.5。

**Q2：冷啟動時沒有 14d 數據怎麼辦？**
A：`edge_predictor_gate` 返回 `NoModel` → fallback 到 shrinkage。正常流程。

**Q3：策略 X 樣本量太少訓不出模型怎麼辦？**
A：ML-MIT 訓練流驗收閾值：per-strategy n ≥ 200 才發 ONNX。不達閾值 → 該策略不啟用 predictor，仍用 shrinkage。

**Q4：推理時某個 feature 缺失（如 funding_rate = None）怎麼辦？**
A：tract-onnx 不支援 nullable；feature 缺失 → 寫入 `sentinel value`（如 0.0 for funding_rate）+ 記錄 `feature_missing_count` metric。若缺失率 > 5% 於 shadow 期內告警。

**Q5：GUI 如何展示新 cost_gate 決策？**
A：Stage 4+ `tab-risk.html` 新增 "Edge Predictor" section，顯示每策略 q10/q50/q90 分佈 + shadow agreement rate。詳見 Stage 3 實施時由 AI-E + FA 補規範。

**Q6：如果 shadow 期 predictor 表現比 shrinkage 差怎麼辦？**
A：Promote gate 不通過 → 回到 Stage 2 retrain（加 feature / 調 hyperparam / 檢查 label 污染）。14d 再來一輪。

**Q7：這會替代 Phase 5 嗎？**
A：不。Phase 5 是「把 draft strategy 升級為 active」的流程，需要策略本身有正 edge。本規格只讓 cost_gate 變聰明，不創造正 edge。兩者正交。

**Q8：LightGBM 的 ONNX 匯出支援 quantile regression 嗎？**
A：支援。`onnxmltools` 將 quantile objective 的 LightGBM 樹結構直接匯出，推理結果與原模型一致（見 §六.2 precision validation）。

---

## 十五、狀態與簽核

- **2026-04-15**：FA v1.0 起草完成，送 PA / ML-MIT / AI-E / CC 評審
- **待確認**：
  - PA 對 schema 與 ETL 節奏的細節
  - ML-MIT 對 `load_training_data()` 簽名與樣本量閾值
  - AI-E 對 tract vs ort 的最終選型
  - CC 對 Safety Invariants 的補遺
- **下一步**：各角色 reply 48h 內回饋 → FA v1.1 整合 → operator 確認 → Stage 0 開工

---

## 附錄 A · 與既有計劃關係

- **`ml_dl_learning_architecture_v0.4.md`**：本規格是 v0.4「Signal Quality Scorer (LightGBM)」的具體落地版本，填補「什麼 target？什麼 feature？怎麼接 cost_gate？」三個空白。
- **`g_sr1_signal_tightening_plan_v2.5.md`**：G-SR-1 在 strategy 層收緊信號；本規格在 gate 層加條件過濾；兩者疊加為策略淨 edge 的兩道防線。
- **`project_edge_data_isolation.md`**：本規格延續並強化 paper / demo / live 資料隔離，至 model artifact 級別。
- **TODO.md EDGE-P3-1**：本文件為該任務的 FA spec；完成後 TODO 可標示 FA 階段 ✅。
