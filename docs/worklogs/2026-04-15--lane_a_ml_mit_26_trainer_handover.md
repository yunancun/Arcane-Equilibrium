# Lane A — ML-MIT #26 Trainer（Python-only）交接備忘

**日期**：2026-04-15
**上下文**：EDGE-P3-1 Phase B #4 完成後，隔壁 session 正在做 FA-PHANTOM-2 修復（`price_tracker.rs` + `tick_pipeline/on_tick.rs` + fast_track tests）。本 session 接手 Lane A（ML-MIT #26 trainer），**純 Python**，零文件衝突風險。
**狀態**：尚未動手。compact 後新 session 照此備忘直接開工。

---

## 一、目標（一句話）

實現 EDGE-P3-1 的**訓練 pipeline**，交付三分位 LightGBM (q10/q50/q90) + CQR 校準 + ONNX 匯出 + 驗收指標報告，產出首個 per-strategy ONNX artifact（解鎖 Phase B #3 ONNX loader + CC T2/T7/T18 + Stage 3 Shadow mode）。

規格來源：`docs/references/2026-04-15--edge_predictor_spec.md` §6 Training Pipeline

## 二、為什麼現在做（而不是等數據）

- FA-PHANTOM-2 修復前，demo 沒有 clean labels（fast_track 誤平全部 strategy）
- 但 trainer 代碼**不需要真實數據**來寫 — 合成資料單元測試即可驗證正確性
- 數據到位後（FA-PHANTOM-2 ship → restart_all --rebuild → demo 累積 ~24-48h）直接跑已測試的 trainer
- 若不提前寫好，trainer 是那個窗口期的下一個瓶頸

## 三、文件衝突規則（與 FA-PHANTOM-2 並行的安全守則）

**隔壁 session 獨占以下文件，本 session 絕對不碰**：
- `rust/openclaw_core/src/risk/price_tracker.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick.rs`
- `rust/openclaw_core/src/risk/fast_track.rs`
- `rust/openclaw_core/tests/stress_integration.rs`
- `rust/openclaw_core/src/risk/fast_track_tests.rs`（若存在單獨測試檔）

**本 session 工作區**：`program_code/ml_training/*.py` + tests only（純 Python）

## 四、已有代碼 inventory

| 文件 | 行數 | 當前狀態 | 本 session 需要怎麼處理 |
|---|---|---|---|
| `scorer_trainer.py` | 235 | LightGBM regression（objective=regression, metric=rmse）+ CPCV 接入 | **參考樣板不改** — 新寫 `quantile_trainer.py` 並行存在 |
| `cpcv_validator.py` | 360 | CPCV 5-fold + purge + embargo 已完成，可直接重用 | 直接 import |
| `calibration.py` | 81 | 骨架（apply_calibration 存根） | **擴展**為 CQR + isotonic 兩種校準 |
| `onnx_exporter.py` | 119 | 單輸出 regression 匯出 + tract-precision 驗證 | **擴展**三分位 per-quantile 匯出（3 個 ONNX/策略） |
| `run_training_pipeline.py` | 172 | Orchestrator，dry_run 合成資料 ok | **擴展** config 加 `use_quantile_predictor=True` 分支，接 quantile trainer |
| `label_generator.py` | 86 | ATR-normalized PnL label（舊 regression 用） | 不動 — EDGE-P3-1 的 label 由 `edge_label_backfill.py` 在 DB 直接算寫 `learning.decision_features.label_net_edge_bps` |
| `edge_label_backfill.py` | 456 | §4.1/4.2/4.3 label 計算 + stale alerter，已完成 | 不動 — 是上游數據源 |
| `parquet_etl.py::load_training_data()` | 393-483 | JSONB→17 col matrix + `EDGE_P3_FEATURE_NAMES` 凍結順序 | 直接 import |
| `optuna_optimizer.py` | 943 | TPE 超參優化（regression） | **參考**，spec §6.3 每策略每分位 50 trials |

## 五、需要新增的文件

### 5.1 `quantile_trainer.py`（新，~400 行）

主要函數：

```python
@dataclass
class QuantileTrainingConfig:
    # Per spec §6.3
    num_leaves: int = 7               # 收緊到 7（v1.1）
    learning_rate: float = 0.05
    n_estimators: int = 500           # ceiling，early_stopping 必用
    early_stopping_rounds: int = 50
    min_data_in_leaf: str = "auto"    # max(20, n_train // 50)
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 5
    lambda_l2: float = 0.1

    # CPCV per §6.1
    n_folds: int = 5
    purge_hours: int = 2
    embargo_hours: int = 24           # funding_arb carve-out 在 get_embargo_hours 處理

    # Sample weight
    decay_halflife_days: float = 14.0  # w = exp(-days_ago / 14)

    # Acceptance gates §6.2
    min_pinball_skill: float = 0.10
    max_coverage_error_pp: float = 3.0
    min_decile_lift_ci_lower: float = 1.3
    max_crossing_rate: float = 0.01
    min_samples_prod: int = 500
    min_samples_shadow: int = 200
    min_samples_none: int = 200        # < 200 → 無模型，走 shrinkage

def train_quantile_trio(features, labels, timestamps, strategy_type, config) -> QuantileTrainingResult:
    """Train q10 / q50 / q90 三獨立 fit，return 3 LGBM models + metadata."""

def compute_sample_weights(timestamps_ms) -> np.ndarray:
    """Exponential decay weight per spec §6.1."""

def fit_floor_baseline(features, labels) -> sklearn.linear_model.QuantileRegressor:
    """§2 強制 floor baseline — LGBM 必須 +5pp pinball skill 勝過才 ship."""

def compute_pinball_skill(y_true, y_pred, alpha, baseline_pred) -> float:
    """1 - pinball(model) / pinball(constant_baseline), per quantile."""

def compute_coverage_error(y_true, q_pred, alpha) -> float:
    """|empirical_hit_rate - alpha|, absolute percentage points."""

def compute_decile_lift_bootstrap(y_true, q50_pred, n_boot=1000) -> tuple[float, float, float]:
    """Returns (point_estimate, ci_lower_95, ci_upper_95). Gate: ci_lower > 1.3."""

def check_quantile_crossing_rate(q10, q50, q90) -> float:
    """Violation rate. Gate: < 1%."""
```

### 5.2 `calibration.py` 擴展（~150 行加進去）

```python
def fit_cqr_offset(residuals_holdout: np.ndarray, alpha: float) -> float:
    """CQR (Romano et al. 2019) — conformity score offset for target alpha coverage.
    holdout conformity score = max(q_alpha_pred - y, y - q_1-alpha_pred).
    """

def apply_cqr_to_quantile(q_pred: np.ndarray, offset: float, alpha: float) -> np.ndarray:
    """q_pred_calibrated = q_pred ± offset (sign depends on alpha)."""

def fit_isotonic_fallback(y_true, y_pred) -> sklearn.isotonic.IsotonicRegression:
    """Monotonic calibration fallback（非 Stage 2 主線，保留備用）."""
```

### 5.3 `onnx_exporter.py` 擴展（~80 行加進去）

```python
def export_quantile_trio_to_onnx(
    models: dict[str, lgb.Booster],  # {"q10": ..., "q50": ..., "q90": ...}
    output_dir: str,
    engine_mode: str,
    strategy_name: str,
    schema_version: str = "v1",
    train_date: str = None,
    validate_samples: np.ndarray = None,
) -> dict:
    """為每個分位輸出獨立 ONNX 檔：
    edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_{train_date}.onnx
    並建立 `_current` symlink 指向最新匯出。Per-file precision validation < 1e-3。
    """
```

### 5.4 `quantile_reports.py`（新，~200 行 — 驗收指標報告）

```python
def generate_acceptance_report(result: QuantileTrainingResult, config: QuantileTrainingConfig) -> dict:
    """產出 §6.2 六項驗收指標報告：
    - pinball_skill_q10 / q50 / q90
    - coverage_error_q10 / q50 / q90
    - decile_lift + ci_95
    - crossing_rate
    - lgbm_vs_linear_qr_skill_diff（LGBM 勝過 linear QR ≥ +5pp 才 ship）
    - train_serve_skew（留給 Rust CC T7，這裡輸出 1000 random vector predictions 供比對）

    回傳 dict + 持久化 JSON 到 {output_dir}/{strategy}_acceptance_report.json。
    每項 pass/fail + 整體 should_ship / shadow_only / no_ship 三檔結論。
    """
```

### 5.5 `run_training_pipeline.py` 擴展

在 `PipelineConfig` 加 `use_quantile_predictor: bool = False`（預設 False 保持既有行為），分支到新 quantile path：

```
1. ETL (load_training_data, quantile path)
2. Train q10/q50/q90 trio (quantile_trainer)
3. CQR calibration on holdout (calibration)
4. Acceptance metrics (quantile_reports)
5. Gate check: should_ship / shadow_only / no_ship
6. ONNX export per quantile (onnx_exporter)
7. Write artifacts + report
```

## 六、測試策略

新增 `tests/test_quantile_trainer.py`、`tests/test_calibration_cqr.py`、`tests/test_quantile_reports.py`、`tests/test_onnx_exporter_quantile.py`，全部**合成資料單元測試**（np.random seeded），不依賴 DB / PG / 真實 labels。

關鍵測試目標：
- Pinball skill 公式正確性（手算一個簡單 case 對比）
- Coverage error 對齊預期（alpha=0.1 時 empirical ≈ 10%）
- CQR 推移後 coverage 趨近 nominal
- Decile lift bootstrap CI 覆蓋機率（用 known-edge 合成資料）
- Quantile crossing 檢測（手塞一個 q10 > q50 樣本 → 計入違反）
- ONNX 三檔匯出 + tract 精度驗證 < 1e-3（若 tract-python 不好裝，可先用 onnxruntime validate，Rust tract 比對留給 CC T7）
- Acceptance gate 邏輯：n < 200 → no_ship / 200-500 → shadow_only / ≥500 且指標全過 → should_ship

既有 `ml_training/` 135 測試必須保持 pass 數（不打破現有 regression / optuna / cpcv 測試）。

## 七、驗收門檻（spec §6.2）

| 指標 | 閾值 |
|---|---|
| Pinball skill score | > 0.10 all 3 quantiles on holdout |
| Coverage error | < 3pp per quantile |
| Decile lift | 1000-bootstrap 95% CI 下界 > 1.3，點估計 ≥ 1.5 |
| Quantile crossing | < 1% |
| LGBM vs linear QR | LGBM pinball skill > +5pp 才 ship |
| Train-serve skew | max(|py_pred − rust_tract_pred|) < 1e-3（Rust 側 CC T7，Python 側只需輸出 1000 random vectors） |

樣本量閘：n ≥ 500 prod / 200 ≤ n < 500 shadow-only / n < 200 無模型（走 shrinkage）

## 八、funding_arb carve-out

spec §6.1：funding_arb 因 embargo=72h × 5-fold 導致每 fold ~100 樣本 < stable：
- **選項 A**：該策略改 3-fold
- **選項 B**：訓練窗口擴到 60d（其他策略維持 30d）
- Stage 2 按當時樣本量決，兩選項皆允

**實作建議**：`get_embargo_config(strategy_name)` 回傳 `EmbargoConfig { n_folds, embargo_hours }`，funding_arb 傳 n_folds=3，其他傳 n_folds=5；兩個都讓 `cpcv_validator` 透過既有 config 吃入。

## 九、不做什麼（Out of Scope for Lane A）

- ❌ **不跑真實訓練** — 數據還沒 clean，跑了也是 garbage in garbage out。本 session 只寫代碼 + 合成資料測試。
- ❌ **不觸 Rust 側** — Phase B #3 ONNX loader、CC T1-T22 是 Lane B，另一 session / 另一後續工作。
- ❌ **不動 edge_label_backfill.py** — 那是上游數據源，FA spec 已定，不改。
- ❌ **不動 ETL** — PA #63 已完成，`load_training_data()` 就是契約，直接用。

## 十、完成後下一步（下一個 session / 下一個 task）

1. 等 FA-PHANTOM-2 ship + restart_all --rebuild
2. 觀察 demo 1-2 天累積 ≥200 close round-trips
3. 跑 `edge_label_backfill.py --engine-mode demo`
4. 跑 `run_training_pipeline.py --use_quantile_predictor --strategy ma_crossover`（或 funding_arb）
5. 讀 acceptance_report.json — 若 should_ship，產出 ONNX
6. 🟢 **unblock** AI-E Phase B #3（ONNX loader）、Step 7b flip capability flag、CC T2/T7/T18

## 十一、關鍵路徑檔案清單（新 session 最先讀這些）

1. 本備忘（`docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md`）
2. EDGE-P3-1 spec §6（`docs/references/2026-04-15--edge_predictor_spec.md:423-478`）
3. `program_code/ml_training/parquet_etl.py:393-483`（`load_training_data` 契約）
4. `program_code/ml_training/cpcv_validator.py`（CPCV 重用）
5. `program_code/ml_training/scorer_trainer.py`（regression 樣板，quantile 照此結構寫）
6. `program_code/ml_training/onnx_exporter.py`（regression ONNX 匯出，擴展三分位）

## 十二、commit / 工作鏈

- E1 inline（主會話寫代碼）
- E2 code review（sub-agent OK 或主會話 self-review 雙視角）
- E4 回歸（`cd program_code && python -m pytest ml_training/tests -x -q`，確保既有 135 測試 + 新增測試全過）
- commit: `feat(edge-p3 stage 2): quantile LGBM trainer + CQR + per-strategy ONNX export`

---

## 十三、當前 DB 數據現況（接手時驗證用）

```sql
-- 2026-04-15 確認：
SELECT engine_mode, strategy_name, count(*) AS total,
       sum(CASE WHEN label_net_edge_bps IS NOT NULL THEN 1 ELSE 0 END) AS labeled
FROM learning.decision_features
GROUP BY engine_mode, strategy_name ORDER BY engine_mode, strategy_name;

-- 結果：
-- paper | funding_arb  |      5 |       0
-- paper | grid_trading |   1010 |       0
-- paper | ma_crossover | 156064 |       0
-- （demo engine 0 rows — 疑似 Step 7a 未進 running binary，需 rebuild 驗證）
```

**Lane A 不 block 此處** — trainer 代碼先寫完測好，等 FA-PHANTOM-2 ship + demo 產生 labels 再跑。

---

## 十四、並行狀況總覽

| 隊伍 | 任務 | 文件區 | 狀態 |
|---|---|---|---|
| 隔壁 session | FA-PHANTOM-2 修復 | `risk/price_tracker.rs` + `tick_pipeline/on_tick.rs` + fast_track | 🟡 進行中 |
| 本 session（Lane A） | ML-MIT #26 trainer | `program_code/ml_training/*.py` + tests | ⬜ 待開工 |
| 未開（Lane B） | Phase B #3 ONNX loader + Step 7b flip | `rust/openclaw_engine/src/edge_predictor/*.rs` + `engine_capabilities_routes.py` | ⬜ blocked by Lane A 首 artifact |
| G-2 daemon | FundingArb 驗證 | `/tmp/openclaw/g2_monitor.*` | 🟡 背景運行（被 FA-PHANTOM-2 間接 block） |

---

**接手快速啟動**：

```bash
# 1. 驗證 repo 狀態
cd /home/ncyu/BybitOpenClaw/srv && git status && git log --oneline -5

# 2. 確認 FA-PHANTOM-2 區文件沒被改動（避免本 session 不小心碰到）
git log -1 --name-only --pretty=format: | grep -E "price_tracker|on_tick|fast_track" || echo "safe"

# 3. 既有測試基準線
cd program_code && python -m pytest ml_training/tests -x -q --co 2>&1 | tail -5
# 應該看到 ~135 測試

# 4. 開工：從 §五 quantile_trainer.py 骨架開始
```
