# EDGE-P3-1 · Realized Edge Predictor — 功能規格 v1.3
# Realized Edge Predictor — Functional Specification v1.3
# 狀態：v1.3 整合 round-3 AI-E YELLOW 3 must-fix（U1/U2/U3）+ macOS Apple Silicon 標註 — 待 operator 簽核 → Stage 0 開工
# 日期：2026-04-15（v1.0 → v1.1 → v1.2 → v1.3）
# Owners：FA 主筆 · PA 架構 · ML-MIT 模型 · AI-E 接線 · CC 審查

---

## CHANGELOG v1.2 → v1.3（round-3 AI-E must-fix + Mac 平台標註）

| # | Section | 變更 | 來源 |
|---|---|---|---|
| U1 | §8.8 | `DisableEdgePredictorAll` 授權 envelope **分層明確化**：Python IPC proxy 層驗 `_EXECUTION_AUTHORITY_OVERRIDE == "granted"` + Rust 端 IPC 消息新增 `operator_token: String` 欄位（Python 層代填 session token） | AI-E U1 |
| U2 | §8.8 · §12.3 · §12.4 | `write_toml_atomic()` **helper 升級併入 task #27**：加 `File::sync_all()` + parent-dir `fsync`；CC 新增 **#13** 驗證 fsync 實際觸發；spec 「fsync before ArcSwap swap」的措辭與 helper 行為對齊 | AI-E U2 |
| U3 | §7.3 · §5.1 · §12.3 | ε-greedy `emit_shadow_fill_ipc` **IPC 契約定義**：新增 `PipelineCommand::EmitShadowFill { context_id, strategy, symbol, features_jsonb, prediction: (f64,f64,f64), cost_bps, ts_ms }`；Python consumer `_handle_shadow_fill_ipc` → `INSERT INTO learning.decision_shadow_fills` | AI-E U3 |
| U4 | §8.8 | 多引擎 TOML fsync **partial-failure 語義**明確化：兩階段 commit（stage 1 三個 tmp 全部成功落盤+fsync → stage 2 三個 rename 依序 best-effort；任一 stage 1 失敗 → 全 abort 不動 ArcSwap；stage 2 中失敗 → loud alert + 引擎繼續用舊 config + reconciler drift 處理） | AI-E B§8.8 should-fix 順手 |
| M1 | §12.4 CC #10 | macOS CI matrix **平台 tuple 明確化**：`aarch64-apple-darwin`（Apple Silicon M1/M2/M3/M4，operator 未來部署目標）+ 可選 `x86_64-apple-darwin`（Intel Mac backward compat）；**不**包含 `aarch64-unknown-linux-gnu`（linux-arm64 與 macOS arm64 為不同 target tuple，QA-E6 延後項不影響 Mac 部署） | operator 提醒 |

**Round-3 投票**：QC GREEN / QA GREEN / ML-MIT GREEN / AI-E YELLOW（3 must-fix U1-U3 已全修 → 預期 GREEN）

---

## CHANGELOG v1.1 → v1.2（round-2 must-fix 採納）

| # | Section | 變更 | 來源 |
|---|---|---|---|
| F1 | §4.2 · §4.3 | **Grid split 裁決**：`grid_trading` 單一 `entry_context_id` 下多腿 close → VWAP merge（不打 split_flag）；其餘策略 → qty-weighted blend + split_flag | QC-D1 |
| F2 | §7.3 | **Pseudocode ordering 修正**：`store.load_for()` 先於 age / sanity 檢查（原版變量未綁定 bug） | QC-D2 · AI-E B2 |
| F3a | §5.1 | `disagreed` GENERATED 改 `COALESCE` 語義避免 NULL 污染 WoW 告警聚合 | QC-D3 |
| F3b | §8.8 · §7.4 | `DisableEdgePredictorAll` **per-engine RiskConfig.toml 持久化 + fsync**，survives engine restart；加授權 envelope（同 `RevokeExecutionAuthority`） | QA-D2 · AI-E E6 |
| F4 | §4.2 · §5.1 · §7.3 | **ε-greedy shadow-filled 行 schema + 訓練排除**：`learning.decision_shadow_fills` 新表；`close_tag = shadow_fill:*` 在 label 回填時永久排除；CC #11 新增驗證 | QA-D3 · ML-MIT-D2 · ML-MIT-B5 |
| F5 | §12.4 | **具名測試清單 T1..T22 枚舉**（原僅說 "≥22"，不可驗證） | QA-D1 |
| F6 | §10.2 | **Live + Demo `edge_fallback_terminal` → P2 首次觸發即告警**（Paper 維持 P3/1h） | QA-D4 |
| F7 | CHANGELOG C2 · §3.2 | 校正 v1.1 CHANGELOG：`recent_slippage_bps_ewma` 並**未**納入 v1.1 §3.2（當時保守不加，延後至 v1.2+ 觀察 Stage 2 signal 強度）→ CHANGELOG 文字更正 | ML-MIT-D1 |
| F8 | §7.1 | 新增 `compile_error!` 當 `edge_predictor_tract` + `edge_predictor_ort` 同時開啟（避免操作員誤 +63MB 二進制 + 後端歧義） | AI-E E4 |
| F9 | §7.2 · §7.3 | `EdgePredictorStore::load_for()` guard discipline：clone `Arc<ArcSwap>` 後立刻 drop `RwLock::read()` guard 才 `.load()`，避免阻塞 add-strategy writer；`rand()` 明確為 per-engine `SmallRng`（非 `OsRng`） | AI-E E1/E3 |
| F10 | §10.2 · §12.5 | 新增 on-call runbook 引用路徑 `docs/runbooks/edge_predictor_on_call.md`（FA Stage 3 前交付） | QA E3 |

**Round-2 未採納 / 延後處理**（spec 不阻塞，Stage 0 inline 或 Stage 2 處理）：
- QC-E2（n 跌破 500 自動降級 shadow）— Stage 2 ML-MIT 處置；§6.5 現規則允許 retrain 時 gate 判斷
- QC-E3（§3.2 features 12-14 原子快照）— Stage 0 AI-E PR-level（`edge_predictor/features.rs::snapshot_atomic()`）
- QC-E4（orphan 單一排除源）— Stage 0 PA SQL WHERE 合併，非 spec 層
- QC-E5（feature_definition_hash CHAR(16) 收斂）— Stage 1 DDL 微調
- QA-E1（`cqr_offset_drift` metric + 日校準）— Stage 3 觀測後決定
- QA-E2（CC 驗證 linear QR baseline 每次跑了）— Stage 2 CC harness item
- QA-E4（ArcSwap mid-predict 屬性測試）— Stage 3 CC item
- QA-E5（funding_arb 樣本不足 auto-extend shadow）— Stage 4 FA 判定
- QA-E6（linux-arm64 CI / red-CI merge block）— W24+ CI 改造項
- ML-MIT-E1（split_flag=true 行降權 0.5）— Stage 2 ML-MIT PR-level
- ML-MIT-E2（CQR fold 策略）— Stage 2 ML-MIT PR-level
- ML-MIT-E3（post-CQR holdout coverage ±3pp 驗證）— §6.2 已有 coverage error 3pp，ML-MIT Stage 2 分兩階段驗證
- ML-MIT-E4（tod_sin/cos 與 funding_settlement 部分重疊）— 允許，LGBM 正則已處理
- ML-MIT-E5（per-strategy pinball skill 報告）— Stage 2 ML-MIT PR-level
- AI-E E2（§7.3 RNG 源）— 已在 F9 落實
- AI-E E5（macOS ort libonnxruntime 打包）— Stage 2 切 ort 時的 contingency note，§7.1 已標註

---

## CHANGELOG v1.0 → v1.1（針對 round-1 review 的採納）

| # | Section | 變更 | 來源 |
|---|---|---|---|
| C1 | §2 / §7.3 | **Quantile crossing 雙保險** — Python 端 CQR 替 Isotonic + Rust 端 monotone rearrangement + 屬性測試 + 越界 fallback | QC B3 · QA · ML-MIT |
| C2 | §3.2 | **Feature 14→17**：刪 `expected_slippage_bps`（tautological），加 `realized_vol_1h` / `orderbook_imbalance_top5` / `tod_sin+tod_cos` / `is_funding_settlement_window`。注意：`recent_slippage_bps_ewma` **保守不加 v1.1**（待 Stage 2 信號評估後 v1.2+ 再議） | QC B2 · ML-MIT |
| C3 | §3.1 / §3.3 | **Persistence freeze 語意明確化** — Open emission 同步 reset；新增 per-feature definition_hash 防 silent drift | QC B1 · QC M1 |
| C4 | §4.1 | **Label 加 funding 累計** — perp 策略（含 funding_arb）非可選 | ML-MIT |
| C5 | §4.2 | **Split close_tag qty-weighted blend** + `split_flag` 標註 | QC M2 |
| C6 | §6.1 | **funding_arb CPCV 3-fold** + 60d 窗口 carve-out；sample_weight 時間衰減 `exp(-days/14)` | ML-MIT |
| C7 | §6.2 | **量化閾值**：pinball skill score >0.10；coverage error <3pp（絕對）；decile lift 1000-bootstrap 下界 >1.3；**n_min 200→500 prod / 200-500 shadow-only** | QA · ML-MIT · QC M3 |
| C8 | §6.3 | **Hyperparam 收緊**：`num_leaves 15→7-10` / `min_data_in_leaf` 隨 n 自適應 / early_stopping 500 ceiling | ML-MIT |
| C9 | §6.4 | **Retrain 週期 daily→weekly**（active 後），daily 只做 drift 監控 | ML-MIT |
| C10 | §7.1 | **tract-onnx 先上 + Stage 2 精度 fail 回 ort**；`onnxmltools>=1.12` pin | AI-E · ML-MIT |
| C11 | §7.2 | **Per-engine ArcSwap predictor store**（不升級 EdgeEstimates） | AI-E |
| C12 | §7.4 | **Fallback-of-fallback** 明確 — 兩層都失效時 per-engine 終端策略 | QC B4 |
| C13 | §7.5 / 附錄 A | **ε-greedy 5% exploration carve-out** 防 off-policy coverage collapse | QC M4 |
| C14 | §8 | **7 條 auto-promote check** + **Stage 3 強制 rollback drill** + paper weight 下調 | QA · QC |
| C15 | §9 | **Invariants 10→12**：+ #11 model staleness + #12 feature range sanity | QC M5/M6 · QA |
| C16 | §10 / §5.1 | `decision_context_snapshots` 加 8 列；metric 門檻量化 | QA |
| C17 | §11 / §12 | **macOS CI matrix**（tract-onnx 跨平台）；AI-E 7 步 implementation order | AI-E · QA |
| C18 | §4.1 | **Label 含有 log-transform 選項** `sign(y)·log(1+\|y\|)` 作 clamp 替代 | ML-MIT |
| C19 | §3.2 | **Feature value sanity clamp** per-feature range + NaN/Inf 檢查 | QC M6 · QA |
| C20 | 附錄 B | **Round-1 review 摘要歸檔**（QC/QA/ML-MIT/AI-E） | 本次 |

**v1.1 未採納項**（延後 v2 或獨立討論）：
- NGBoost 取代 LGBM（ML-MIT 建議）— v2 研究
- Conformal prediction 外加 wrapper（QC S3）— shadow 14d 結果若 coverage 偏差再啟
- LinUCB confidence bound 作 feature（ML-MIT #6）— v2
- BTC 跨資產 regime proxy / VWAP 偏離（ML-MIT feature #4/#7）— v2
- 結構性 multi-output quantile LGBM（QC S1）— 視 onnxmltools + tract 組合兼容性 Stage 2 再決；v1.1 以「獨立 fit + 重排」為主線

---

## 0. 一頁摘要（TL;DR）

**Problem**：`shrunk_bps`（James-Stein 靜態收縮）是策略-符號 cell 的**歷史平均** edge，backward-looking，不感知單筆交易當下的 regime / confluence / position state。cost_gate 用同一個 cell 數值對待「同策略同符號」所有機會，導致 Phase 5 坍塌（全 cell 收斂到 -35.72 bps）。

**Solution**：訓練一個 per-strategy quantile LightGBM 模型，輸入**決策瞬間**的 **17** feature 快照，輸出 `realized_net_edge_bps` 的 (q10, q50, q90) 三分位預測。cost_gate 新決策：`q50 − k × (q50 − q10) > cost` 才放行，`q10 > 0` 才加倉。Python 端用 **CQR（Conformalized Quantile Regression）** 校準；Rust 推理端加 **monotone rearrangement** 強制 q10 ≤ q50 ≤ q90。

**Invariants (12)**：
1. shadow mode ≥14d + paper ≥7d + demo ≥7d 才能 promote live（live 永遠手動）
2. feature freeze at entry instant（Open emission 同步 reset PersistenceTracker）
3. per-strategy 獨立模型
4. 推理失敗 fail-closed → shrinkage 回退
5. 不觸 LinUCB（blast radius 限縮）
6. schema_hash 不匹配 fail-closed；per-feature definition_hash 防 silent drift
7. Paper / Demo / Live 模型 artifact 分離
8. Live active 需 operator 手動
9. Label 僅來自真實 close fill
10. Outlier clamp 僅在訓練時
11. **（NEW）model staleness：artifact age ≤ 2× retrain_cadence → else fail-closed**
12. **（NEW）feature value range sanity：每 feature 有 hard range + NaN/Inf 拒絕**

**Blast radius**：Rust `intent_processor::gates` 新增 `edge_predictor_gate()`，feature flag `use_edge_predictor` 控，預設 `false`。停滯時 shrinkage 路徑未動。Cargo `edge_predictor` feature 封鎖 tract-onnx 依賴。

---

## 一、Context（為什麼不是已完成任務）

### 1.1 shrunk_bps 的三個結構缺陷

| 缺陷 | 具體表現 | 本規格如何解決 |
|---|---|---|
| **Backward-looking** | cell 值是過去 30d 成交平均 | 用**決策瞬間** feature 快照作為條件 |
| **Marginal, not conditional** | 同 cell 對所有信號等同處理 | per-decision 預測，每筆獨立條件向量 |
| **Self-fulfilling** | 過去負 edge → gate 寬鬆 → 負反饋 | shadow ≥14d + 5% ε-greedy 探索保證 off-policy 樣本（C13） |

### 1.2 LightGBM 管線與 LinUCB 的關係（同 v1.0）

edge predictor 取代 `shrunk_bps` 作為 cost_gate 的數值來源。LinUCB 不動——兩者語義正交。

### 1.3 Phase 5 cost_gate 與本規格的關係（同 v1.0）

本規格不是 Phase 5 的前置；價值是**把 cost_gate 從靜態平均升級為條件預測**。

---

## 二、模型規格

### 2.1 模型家族

- **算法**：LightGBM Quantile Regression（`objective='quantile'`, `alpha∈{0.1, 0.5, 0.9}`）三獨立 fit
- **Floor baseline 強制**：每策略先 fit `sklearn.linear_model.QuantileRegressor`；LGBM 若不顯著優於 linear QR（pinball skill >5%），**禁止 ship LGBM**（ML-MIT 強制）
- **Per-strategy 獨立訓練**：5 策略 × 3 分位 = 15 ONNX artifact
- **Per-strategy model naming**：`edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_{train_date}.onnx` + symlink `_current`

### 2.2 Quantile Crossing 雙保險（C1）

**Python 訓練端**：
- **CQR (Conformalized Quantile Regression, Romano et al. 2019)** 取代 Isotonic —— holdout fold 上計算 conformity score，加/減 offset 使 empirical coverage 對齊 nominal；對 tail（q10/q90）友善
- 訓練完檢查 holdout 上 q10 ≤ q50 ≤ q90 違反率；>1% 則拒絕 ship

**Rust 推理端**：
- 每次 predict 後檢查 q10 ≤ q50 ≤ q90；違反：
  - **首選**：monotone rearrangement — `q10'=min(q10,q50,q90)`, `q90'=max(q10,q50,q90)`, q50 取 median
  - 若 rearrangement 後仍語意偏離（如三值相等 > 0 但 shrinkage 強 reject）→ fail-closed fallback
- 埋 metric `quantile_crossing_count`

**測試**：屬性測試 10^5 隨機 feature 向量，斷言 rearrangement 後 q10 ≤ q50 ≤ q90 恒真

### 2.3 不使用的方案（v1.1 明確排除）

| 方案 | 為何不選 |
|---|---|
| Point regression | 丟失不確定性 |
| NGBoost | 延後 v2（low-n 優但 ONNX 支援未成熟） |
| Multi-output quantile LGBM（LGBM ≥4.0）| 視 Stage 2 實測決定，主線用獨立 fit + 重排 |
| Neural net / Transformer | 樣本不足 |
| Bayesian hierarchical | v2 |

---

## 三、Feature Contract（v1.1: 17 維）

### 3.1 Freeze-Time 規則（C3）

Feature vector 在 `StrategyAction::Open` 被 emit 的同一 tick 快照。

**強制新規則**：Open emission **同步**調用 `PersistenceTracker::consume_elapsed()`，該 tracker 立刻 reset first_ts。避免同 symbol 二次 open pre-close 繼承舊 first_ts（QC B1）。

### 3.2 Feature 清單 v1（17 維，per-strategy 模式下 strategy_id 省去）

| # | Feature | 類型 | 單位 | Range Clamp | 現狀 | 來源 / 計算 |
|---|---|---|---|---|---|---|
| **Regime (5)** |||||||
| 1 | `adx_1h` | f32 | 點 | [0, 100] | ✅ | `IndicatorSnapshot.adx` (1h TF) |
| 2 | `bb_width_pct` | f32 | % | [0, 50] | ✅ | `IndicatorSnapshot.bollinger.bandwidth` (5m) |
| 3 | `atr_pct` | f32 | % | [0, 20] | ✅ | `IndicatorSnapshot.atr_14.atr_percent` (5m) |
| 4 | `funding_rate` | f32 | 小數 | [-0.01, 0.01] | ✅ | `TickContext.funding_rate` |
| 5 | `realized_vol_1h` **(NEW)** | f32 | % | [0, 20] | ⚠️ 需接 | `stddev(log_returns_1m, window=60) × sqrt(60) × 100` |
| **Basis / Microstructure (3)** |||||||
| 6 | `basis_bps` | f32 | bps | [-500, 500] | ⚠️ 可算 | `(index_price - last_price) / mid × 10000` |
| 7 | `orderbook_imbalance_top5` **(NEW)** | f32 | ratio | [-1, 1] | ⚠️ 需接 | `(Σbid_vol_5 − Σask_vol_5)/(Σbid_vol_5 + Σask_vol_5)` |
| 8 | `spread_bps` | f32 | bps | [0, 1000] | ✅ | `(ask - bid) / mid × 10000` |
| **Strategy (3)** |||||||
| 9 | `confluence_score` | f32 | 0-65 | [0, 65] | ⚠️ 需暴露 | 每策略 state，經 `OrderIntent.confluence_score: Option<f32>` typed 字段（AI-E 修正） |
| 10 | `persistence_elapsed_ms` | f32 | ms | [0, 3_600_000] | ⚠️ 需暴露 | `OrderIntent.persistence_elapsed_ms: Option<u32>` typed 字段 |
| 11 | `side` | i8 | {-1, +1} | — | ✅ | `intent.is_long ? 1 : -1` |
| **Position (3)** |||||||
| 12 | `notional_pct_of_bal` | f32 | % | [0, 100] | ✅ | `qty × price / paper_state.balance()` |
| 13 | `concurrent_positions` | u8 | count | [0, 100] | ✅ | `paper_state.position_count()` |
| 14 | `same_direction_cnt` | u8 | count | [0, 100] | ⚠️ 需接 | `paper_state.count_same_direction(is_long)`（O(n≤100)=~100ns） |
| **Time (3)** |||||||
| 15 | `tod_sin` **(NEW)** | f32 | [-1, 1] | [-1, 1] | ⚠️ 需算 | `sin(2π × hour_utc / 24)` |
| 16 | `tod_cos` **(NEW)** | f32 | [-1, 1] | [-1, 1] | ⚠️ 需算 | `cos(2π × hour_utc / 24)` |
| 17 | `is_funding_settlement_window` **(NEW)** | u8 | {0, 1} | — | ⚠️ 需算 | 1 iff `now_ms % (8h) ∈ [last_15min of 8h cycle]`（Bybit settlement） |

**刪除**（v1.0 項）：
- ~~`expected_slippage_bps`~~（QC B2）— 靜態 tier lookup 與 label 的 round_trip_fee 扣除重複，改用 `recent_slippage_bps_ewma`（若 Stage 2 實測 signal 強，v1.2 納入）；v1.1 保守不加

**Sanity clamp 規則（C19，invariant #12）**：
- 每 feature 有上下硬 range（上表 Range Clamp 欄）
- 推理端：`feature.is_nan() || feature.is_infinite() || out_of_range` → emit `feature_out_of_range` metric + fail-closed fallback（不使用預測）
- 訓練端：同樣 clamp + 記錄 clamp ratio

### 3.3 Schema 與 definition hash（C3）

- `feature_schema_hash` = `sha256('\n'.join(sorted(feature_names))).hexdigest()[:16]`
- **（NEW）** `feature_definition_hash` = `sha256('\n'.join(f"{name}:{canonical_formula}" for name in sorted))...[:16]`
  - `canonical_formula` 例如 `adx_1h:rust/openclaw_core/src/indicators/adx.rs#fn_compute_adx,tf=1h`
  - 任何 feature 計算點變更（TF/公式/sign convention）→ formula 字串變 → definition_hash 變
- 任何 hash 不匹配 → fail-closed（invariant #6）

### 3.4 明確排除的 features（同 v1.0）

- 單 tick bid/ask 絕對值
- 原始 price / volume 絕對值
- 實時 unrealized PnL of other positions
- 任何 t+1 可見資訊

---

## 四、Label Contract

### 4.1 公式（C4 · C18）

**基礎公式**：
```
gross_edge_bps     = (exit_price - entry_price) / entry_price × side × 10000
round_trip_fees_bps = (entry_fee + exit_fee) / entry_notional × 10000
funding_accrued_bps = Σ_over_hold_period( funding_rate_at_settlement × 10000 ) × side
                      # 持倉方向對齊：long 付費率為正 → 扣；short 收費率為正 → 加

realized_net_edge_bps = gross_edge_bps
                        - round_trip_fees_bps
                        + funding_accrued_bps    # perp 策略（所有當前 5 策略皆是 perp）
```

**ML-MIT 強制**：funding_arb 必須包含 funding accrual，否則模型學噪音。其餘 perp 策略若跨 settlement 也須包含。

**訓練端 clamp（C18）**：
- 選項 A（默認）：hard clamp `label ∈ [-500, +500]` bps
- 選項 B（備選）：log-transform `y' = sign(y) · log(1 + |y|)`，訓練目標變 log-bps
- Stage 2 ML-MIT 決定；DB 原始值永保留真實

### 4.2 Close 歸屬規則（C5）

| close_tag 類別 | 歸屬 |
|---|---|
| `strategy_close:*` 單一 | 保留，label = 真實 net edge |
| `risk_close:*` 單一 | 保留，label 為真實 net edge（含強平虧損——模型應學此模式） |
| `stop_trigger:*` 單一 | 保留 |
| **Split（混合，非 grid）** | **qty-weighted blend** — `label = Σ (qty_i × bps_i) / Σ qty_i`；單 row 寫入，`split_flag=true` 記錄 |
| **Grid 多腿（`grid_trading`）** | **VWAP merge**，見 §4.3；`split_flag=false`（grid 設計即多腿，非異常 split） |
| `orphan_close:*` | **排除**訓練集 |
| `adopted_close:*`（orphan-adopt） | **排除**（`entry_context_id` 為 `"orphan:*"` 前綴） |
| **`shadow_fill:*`（ε-greedy 探索合成 fill）** | **永久排除**訓練集（C13 ε-greedy 產生的 paper 合成樣本，供 off-policy 觀測不入 label；見 §5.1 `learning.decision_shadow_fills` 獨立表） |

**split 判定（Grid 除外）**：`strategy != grid_trading` 且同一 `entry_context_id` 在 `hold_window + 1min` 內收到 >1 close fill → 視為 split → qty-weighted blend + `split_flag=true`。

**Grid 裁決（F1）**：`grid_trading` 策略由 §4.3 的「所有 legs 合併到單 entry_context_id 的 VWAP entry/exit」接管，**不走 split_flag 路徑**。ETL 判斷時先看 `strategy_name == 'grid_trading'`，命中則跳過 split detection，全部 legs 聚合為單一 VWAP label。

### 4.3 Partial fill 假設（v1.2 明確化）

**非 grid 策略**：`one entry → split close 合併` 走 §4.2 qty-weighted blend + `split_flag=true`。

**`grid_trading`（F1 權威規則）**：所有 legs 共享一個 `entry_context_id`；ETL 對該 context_id 下的全部 fills 計算：
- `vwap_entry = Σ(qty_i × entry_price_i) / Σ qty_i`（所有 open legs）
- `vwap_exit  = Σ(qty_j × exit_price_j)  / Σ qty_j`（所有 close legs）
- `total_fees = Σ fee`（所有 legs 雙向）
- `label_net_edge_bps = (vwap_exit − vwap_entry)/vwap_entry × side × 10000 − fees_bps + funding_accrued_bps`
- 寫入 `decision_features` 單 row；`split_flag=false`（grid 多腿是 by-design，不應視為異常 split）

**ETL 判斷順序**：`strategy_name=='grid_trading'` → VWAP merge 路徑；否則走 §4.2 split detection。互斥，單一判定源。

### 4.4 Label clamp + sample weight（C6）

- 訓練時 winsorize at ±500bps 或 log-transform
- Sample weight `w_i = exp(-days_ago_i / 14)`（14 日半衰期）

---

## 五、Data Pipeline

### 5.1 Feature Store Schema（C16 · 新 8 列）

**`learning.decision_features`**（新表，同 v1.0）：

```sql
CREATE TABLE learning.decision_features (
    context_id          TEXT PRIMARY KEY,
    ts                  TIMESTAMPTZ NOT NULL,
    engine_mode         TEXT NOT NULL,
    strategy_name       TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    side                SMALLINT NOT NULL,
    feature_schema_version  TEXT NOT NULL,
    feature_schema_hash     TEXT NOT NULL,
    feature_definition_hash TEXT NOT NULL,    -- NEW C3
    features_jsonb      JSONB NOT NULL,
    label_net_edge_bps  DOUBLE PRECISION,
    label_close_tag     TEXT,
    label_split_flag    BOOLEAN DEFAULT FALSE,  -- NEW C5
    label_filled_at     TIMESTAMPTZ
);
CREATE INDEX ON learning.decision_features (ts DESC);
CREATE INDEX ON learning.decision_features (strategy_name, engine_mode, ts DESC);
```

**`learning.decision_context_snapshots`**（既有表增列，C16 · QA 要求 · F3a NULL 語義修正）：
```sql
ALTER TABLE learning.decision_context_snapshots
  ADD COLUMN predicted_q10          DOUBLE PRECISION,
  ADD COLUMN predicted_q50          DOUBLE PRECISION,
  ADD COLUMN predicted_q90          DOUBLE PRECISION,
  ADD COLUMN predictor_decision     TEXT,   -- accept|reject_cost|reject_q10|fallback_no_model|fallback_error|fallback_schema_mismatch|shadow_fill
  ADD COLUMN shrinkage_decision     TEXT,   -- accept|reject
  -- F3a (v1.2): COALESCE 避免 NULL 污染 WoW disagree-rate 聚合。
  -- 任一邊 NULL 被視為空字串，非 NULL 邊的 decision 即驅動 disagreed 布林。
  -- 兩邊都 NULL（未評估行）→ disagreed = FALSE，不計入分母需 WHERE 過濾。
  ADD COLUMN disagreed              BOOLEAN GENERATED ALWAYS AS
      (COALESCE(predictor_decision,'') <> COALESCE(shrinkage_decision,'')) STORED,
  ADD COLUMN feature_schema_hash    TEXT,
  ADD COLUMN predict_latency_us     INTEGER;

-- 儀表板 / 告警查詢標準範式：
-- SELECT AVG(disagreed::int) FROM decision_context_snapshots
-- WHERE predictor_decision IS NOT NULL AND shrinkage_decision IS NOT NULL;
```

**`trading.fills`** 加 `entry_context_id TEXT NULL`（backward-compat）。

**`learning.decision_shadow_fills`**（F4 · 新表，C13 ε-greedy 合成 fill 專用）：
```sql
CREATE TABLE learning.decision_shadow_fills (
    shadow_id           BIGSERIAL PRIMARY KEY,
    context_id          TEXT NOT NULL,        -- 原 decision context_id
    ts                  TIMESTAMPTZ NOT NULL,
    engine_mode         TEXT NOT NULL,        -- 僅 'paper' 合法（invariant: Demo/Live 不做 ε-greedy）
    strategy_name       TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    side                SMALLINT NOT NULL,
    features_jsonb      JSONB NOT NULL,
    predicted_q10       DOUBLE PRECISION,
    predicted_q50       DOUBLE PRECISION,
    predicted_q90       DOUBLE PRECISION,
    cost_bps_at_open    DOUBLE PRECISION,
    -- Paper 引擎「紙上模擬」此 fill 的回報；與真實 trading.fills 隔離
    synthetic_exit_price DOUBLE PRECISION,    -- 某 exit rule 確定後填入
    synthetic_hold_ms   BIGINT,
    synthetic_net_edge_bps DOUBLE PRECISION,  -- 純觀測，不入 learning.decision_features label
    close_tag           TEXT NOT NULL DEFAULT 'shadow_fill:epsilon_greedy'
);
CREATE INDEX ON learning.decision_shadow_fills (strategy_name, engine_mode, ts DESC);
CHECK (engine_mode = 'paper');  -- invariant
```

**Label 回填強制排除（F4）**：`parquet_etl.py::backfill_labels()` SQL WHERE 永遠包含
```sql
AND f.close_tag NOT LIKE 'shadow_fill:%'
AND NOT EXISTS (SELECT 1 FROM learning.decision_shadow_fills s WHERE s.context_id = f.entry_context_id)
```
確保 ε-greedy 合成樣本**不**污染 `learning.decision_features.label_net_edge_bps`。

### 5.2 寫入時機（同 v1.0）

- Open 接受 → Rust emit `DecisionFeatureSnapshot` → Python consumer `INSERT ... ON CONFLICT DO NOTHING`
- Close fill → 按 `entry_context_id` 回填 label；split 情況合併為 qty-weighted blend 單 row

### 5.3 Entry → Close 關聯

- `PaperPosition` 加 `entry_context_id: String`
- Open 時寫入；`emit_close_fill` 讀出寫入 fill row
- **重啟 paper 遺失**：`restore_from_db` 不還原 position-level state（QoL-1 設計）→ entry_context_id 丟失；paper 重啟少見，Demo/Live 有 reconciler hydrate
- **Orphan adopt**：寫 `"orphan:{symbol}:{ts}"` 前綴 → 訓練端 skip

### 5.4 ETL 流程（同 v1.0，週期調整見 §6.4）

### 5.5 Paper / Demo / Live 隔離（同 v1.0）

---

## 六、Training Pipeline

### 6.1 分割方式（C6）

- **CPCV** 5-fold；purge=2h；embargo=24h（多數）
- **funding_arb carve-out**：embargo=72h × 5-fold → 每 fold 剩 ~100 樣本（below stable）。解法：
  - 選項 A：對該策略改 3-fold
  - 選項 B：訓練窗口擴到 60d（其他策略維持 30d）
  - ML-MIT Stage 2 實施時按當時樣本量決；spec 兩選項皆允
- **Sample weight**：`w = exp(-days_ago / 14)`
- **Holdout tail**：最近 7d 嚴格 holdout，不入 CPCV；funding_arb 延至 14d

### 6.2 Loss & Metrics（C7）

| 指標 | 公式 | 驗收 |
|---|---|---|
| **Pinball skill score** | `1 − pinball(model) / pinball(constant_baseline)` per quantile | > **0.10** all 3 quantiles on holdout |
| **Coverage error** | `\|empirical_hit_rate − alpha\|`（絕對 percentage points）| < **3pp** per quantile |
| **Decile lift** | `mean(y \| pred_q50 top_decile) / mean(y \| pred_q50 median_decile)` | **1000-bootstrap 95% CI 下界 > 1.3**，點估計 ≥ 1.5 |
| **Quantile crossing** | 違反率 on holdout | < **1%** |
| **Train-serve skew** | `max(\|py_pred − rust_tract_pred\|)` 1000 random vectors | < **1e-3** |
| **LGBM vs linear QR** | Pinball skill vs sklearn QuantileRegressor | LGBM 須 > **+5pp** 才 ship |

### 6.3 Hyperparameters（C8）

```python
{
    'objective': 'quantile',
    'alpha': <0.1|0.5|0.9>,
    'metric': 'quantile',
    'num_leaves': 7,                    # v1.1: 收緊 (15→7)
    'learning_rate': 0.05,
    'n_estimators': 500,                # ceiling
    'early_stopping_rounds': 50,        # 必須 early stop
    'min_data_in_leaf': 'max(20, n_train // 50)',  # 隨 n 調整
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'lambda_l2': 0.1,
}
```

Optuna TPE 預算：每策略每分位 50 trials（從 100 降）。

### 6.4 訓練觸發（C9）

- **Shadow 期**：每週一次訓練 + daily drift 監控
- **Active 後**：**每週訓練**（不是 daily）+ daily 只做 drift / rolling coverage 監控
- Drift 閾值：rolling 7d coverage error > 5pp → retrain 觸發 + 告警

### 6.5 樣本量閘（C7）

- **Prod artifact**：per-strategy n ≥ **500**
- **Shadow-only artifact**：200 ≤ n < 500（不可入 gate，僅觀察）
- n < 200：該策略無模型，走 shrinkage

---

## 七、Inference Pipeline（Rust 側）

### 7.1 ONNX Runtime（C10）

**主線**：`tract-onnx = "0.21"` (default-features off, onnx feature on)
- 純 Rust，binary +3.5MB，LGBM `TreeEnsembleRegressor` ai.onnx.ml v1/v3 opset 已支援（AI-E 驗證）
- **但** ML-MIT 警告歷史 bug（missing value 處理、晚加算子）

**Stage 2 精度驗證 fail 切換**：
- CC harness 用 1000 random vector 比對 tract 輸出 vs Python LGBM
- max abs err >= 1e-3 或任何 NaN/Inf → swap feature flag 到 `ort = "2.x"`（+60MB 外部依賴但穩定）
- `onnxmltools >= 1.12` pin（quantile bug 修復版本）

**Cargo 配置**：
```toml
tract-onnx = { version = "0.21", default-features = false, features = ["onnx"], optional = true }
ort = { version = "2", optional = true }

[features]
edge_predictor_tract = ["dep:tract-onnx"]
edge_predictor_ort = ["dep:ort"]
edge_predictor = ["edge_predictor_tract"]  # default alias
```

**F8 · 互斥守則**：`edge_predictor/mod.rs` 頂部加
```rust
#[cfg(all(feature = "edge_predictor_tract", feature = "edge_predictor_ort"))]
compile_error!(
    "edge_predictor_tract and edge_predictor_ort are mutually exclusive; \
     pick exactly one backend to avoid +63MB binary bloat and ambiguous runtime selection"
);
```
避免操作員誤同時啟用（`cargo build --features edge_predictor_tract,edge_predictor_ort`）。

### 7.2 模型加載與熱重載（C11）

**新模組**：`rust/openclaw_engine/src/edge_predictor/`
- `mod.rs` — `EdgePredictor` trait + `EdgePredictorStore`
- `features.rs` — `FeatureVectorV1`（Copy, 17 f32 + u8 packed）+ builder
- `tract_backend.rs` / `ort_backend.rs` — 後端實現（feature-gated）
- `null_backend.rs` — 永遠 `Err(NoModel)`（default build）
- `rearrangement.rs` — monotone rearrangement 工具

**Per-engine 結構**（並行於 `PerEngineRiskStores`）：
```rust
pub struct PerEnginePredictors {
    pub paper: Arc<EdgePredictorStore>,
    pub demo:  Arc<EdgePredictorStore>,
    pub live:  Arc<EdgePredictorStore>,
}

pub struct EdgePredictorStore {
    inner: RwLock<HashMap<StrategyName, Arc<ArcSwap<Option<Arc<dyn EdgePredictor + Send + Sync>>>>>>,
}
```

- Per-strategy ArcSwap（細粒度熱重載）
- **不升級** `EdgeEstimates` 為 ArcSwap（範圍守則）

**F9 · `load_for()` guard discipline**（強制）：
```rust
impl EdgePredictorStore {
    pub fn load_for(&self, strategy: &str) -> Option<Arc<dyn EdgePredictor + Send + Sync>> {
        // 1. 取 read guard
        let guard = self.inner.read();
        // 2. clone 內部 Arc<ArcSwap<...>>
        let arc_swap = guard.get(strategy)?.clone();
        // 3. 立刻 drop read guard（避免 .load() 期間阻塞 add-strategy writer）
        drop(guard);
        // 4. ArcSwap lock-free 讀取當前模型
        arc_swap.load_full()
    }
}
```
`predict()` 呼叫者必須在 `load_for()` 返回後的短 Arc 生命週期內完成推理；mid-predict swap 是 lock-free 安全的（舊 Arc 繼續服務到當前 predict 結束）。

### 7.3 Gate 新決策（C1 · C13）

**F2 · Pseudocode ordering 修正**（v1.1 原版 bug：`predictor.age_seconds()` 在 `load_for()` 之前，變量未綁定）：

```rust
fn edge_predictor_gate(
    ctx: &TickContext,
    features: &FeatureVectorV1,
    engine: EngineKind,
    strategy: &str,
    store: &EdgePredictorStore,
    rng: &mut SmallRng,          // F9: per-engine seeded, not OsRng (hot path)
    config: &EdgePredictorConfig,
) -> GateDecision {
    // Step 1 · invariant #12 feature sanity（不需 model 可先查）
    if !features.all_in_range() {
        metric_inc("feature_out_of_range");
        return fallback_shrinkage_gate(ctx, strategy);
    }

    // Step 2 · 取 predictor（load_for 按 F9 guard discipline 實作）
    let predictor = match store.load_for(strategy) {
        Some(p) => p,
        None => return fallback_shrinkage_gate(ctx, strategy),  // NoModel
    };

    // Step 3 · invariant #11 model staleness（需 predictor 才能 .age_seconds()）
    if predictor.age_seconds() > config.model_max_age_seconds {
        metric_inc("model_stale");
        return fallback_shrinkage_gate(ctx, strategy);
    }

    // Step 4 · 推理
    let pred = match predictor.predict(features) {
        Ok(p) => p,
        Err(NoModel | SchemaHashMismatch | DefinitionHashMismatch) => {
            metric_inc("predict_schema_error");
            return fallback_shrinkage_gate(ctx, strategy);
        }
        Err(InferenceFailed(_)) => {
            metric_inc("predict_errors");
            return fallback_shrinkage_gate(ctx, strategy);
        }
    };

    // Step 5 · C1 monotone rearrangement
    let pred = rearrangement::enforce_monotone(pred);
    if !pred.is_valid() {
        metric_inc("quantile_crossing_fatal");
        return fallback_shrinkage_gate(ctx, strategy);
    }

    // Step 6 · cost gate
    let cost_bps = estimate_round_trip_cost_bps(features);
    let k = config.quantile_safety_k;  // 默認 0.5
    let safety_margin = pred.q50 - k * (pred.q50 - pred.q10);

    if safety_margin < cost_bps {
        // Step 7 · C13 ε-greedy 5% exploration (paper 引擎 only; F9 SmallRng)
        if engine == EngineKind::Paper && rng.gen_bool(config.exploration_rate) {
            metric_inc("epsilon_greedy_exploration");
            // F4+U3: 經 PipelineCommand::EmitShadowFill IPC → Python consumer
            // → INSERT learning.decision_shadow_fills。close_tag='shadow_fill:epsilon_greedy'
            // 永久排除於 label 回填（§5.1 WHERE 子句強制）。
            // context_id 與原 OrderIntent 共用，但不會在 learning.decision_features 出現
            // （§5.2: Open 「接受」才寫 DecisionFeatureSnapshot；shadow fill 是 reject 分支）
            pipeline.send(PipelineCommand::EmitShadowFill {
                context_id:    ctx.order_intent.context_id.clone(),
                strategy:      strategy.to_string(),
                symbol:        ctx.symbol.clone(),
                features_jsonb: features.to_jsonb(),
                prediction:    (pred.q10, pred.q50, pred.q90),
                cost_bps:      cost_bps,
                ts_ms:         ctx.now_ms,
            });
            return GateDecision::ShadowFill;
        }
        return GateDecision::Reject("predictor_cost_margin_insufficient");
    }

    if pred.q10 < 0.0 && config.require_q10_positive_for_adds {
        return GateDecision::RejectAdd("q10_negative");
    }
    GateDecision::Accept
}
```

**RNG 來源（F9）**：`SmallRng::seed_from_u64(engine_startup_instant_nanos ^ engine_kind_discriminant)`，per-engine 各一，放入 `TickPipeline` 的 `&mut` 上下文。非 crypto 用途；hot path 禁用 `OsRng`（syscall 開銷）。

**`RiskConfig.edge_predictor`** 新字段：
```toml
[edge_predictor]
use_edge_predictor = false
shadow_mode = true
quantile_safety_k = 0.5
require_q10_positive_for_adds = true
fallback_on_error = "shrinkage"
exploration_rate = 0.05               # NEW C13
retrain_cadence_seconds = 604800      # 1 week
model_max_age_seconds = 1209600       # 2 weeks (invariant #11)
```

### 7.4 Fallback-of-Fallback 明確化（C12）

```
predictor.predict()
  ├─ Ok(pred) → rearrangement → gate logic
  └─ Err / stale / invalid
      └─> shrinkage_gate
          ├─ Ok (cell hit) → 現有 paper/demo/live 邏輯
          └─ Err / missing cell / stale edge_estimates.json
              └─> TERMINAL FALLBACK （NEW）:
                  ├─ Paper:  fail-open（exploration mode，記 metric）
                  ├─ Demo:   fail-closed（拒絕 + metric，避免假數據污染 prod）
                  └─ Live:   fail-closed（根原則 #5）
```

Terminal fallback 統一 emit metric `edge_fallback_terminal` 讓 operator 早期發現雙層失效。

### 7.5 推理性能預算（同 v1.0）

- 目標 < 1ms；tract 實測 ~80-150μs（200-tree × 17-feature）
- Warm-up predict 在 startup 跑一次，避免首次調用冷 cache 尖峰

---

## 八、Rollout Stages

### 8.1 Stage 0 — Feature 接線（AI-E）

- `OrderIntent` typed 字段 `confluence_score` / `persistence_elapsed_ms`
- `basis_bps` / `same_direction_cnt` / `realized_vol_1h` / `orderbook_imbalance_top5` / `tod_sin/cos` / `is_funding_settlement_window` 計算點
- `PaperPosition.entry_context_id` + emit path
- `DecisionFeatureSnapshot` IPC + Python consumer
- **PersistenceTracker `consume_elapsed()` reset on Open**（C3）

**驗收**：`learning.decision_features` 出現記錄；隨機 10 筆人工覆核。

### 8.2 Stage 1 — Label 回填（PA）

- `trading.fills.entry_context_id` migration
- Label backfill job（含 split qty-weighted blend 邏輯）
- Reconcile 7d NULL alerter

**驗收**：demo 48h 後 label 填充率 > 95%。

### 8.3 Stage 2 — 訓練管線（ML-MIT）

- `run_training_pipeline.py::load_training_data()` 實作
- CPCV（funding_arb carve-out）+ sample_weight decay
- Linear QuantileRegressor floor baseline
- Per-strategy quantile LGBM × 3
- CQR calibration
- Pinball skill / coverage error / decile lift（bootstrap CI）/ crossing rate 報告
- ONNX 匯出 + precision validation（tract + ort 雙跑）
- **關鍵判斷點**：tract 精度 pass？是 → `edge_predictor_tract` feature；否 → `edge_predictor_ort`

**驗收**：per-strategy n ≥ 500 且 all metrics pass → ship prod artifact；200≤n<500 → ship shadow artifact。

### 8.4 Stage 3 — Shadow Mode（AI-E + PA）

- `use_edge_predictor=true` + `shadow_mode=true`
- 每 Open 並行 predict，寫 `decision_context_snapshots` 8 新列
- 繼續使用 shrinkage gate 決定交易
- **強制 rollback drill**（QA）：shadow→active→shadow 一次，驗證 IPC 無縫切換

**驗收**：Shadow ≥14d，推理 failure < 0.1%，train-serve skew < 1e-3，p99 < 2ms，coverage error rolling 7d < 3pp，decile lift 穩定。

### 8.5 Stage 4 — Promote to Paper Active（7d）

**7 條 auto-promote check**（QA C14，全過才顯示 promote 按鈕）：
1. pinball skill > 0.10 holdout
2. coverage error < 3pp per quantile
3. decile lift bootstrap lower 95% > 1.3
4. train-serve skew < 1e-3
5. predict failure < 0.1%
6. p99 latency < 2ms
7. feature_missing_count < 1%

**Paper engine 權重下調**（QC S）：Paper active 通過只證明 model 對 self-distribution 穩定；真實信號靠 Demo 確認。

### 8.6 Stage 5 — Promote to Demo Active（7d，operator 手動）

Paper 7d pass → operator 手動 promote demo。demo 期觀察真實 fill 與 decile lift 對照。

### 8.7 Stage 6 — Live（永遠手動，最早 2026-05-30+）

Demo 7d 穩定 + operator 明確放行 + 至少 21d 累計觀察無異常。

### 8.8 Rollback 機制（C14 · F3b）

- `PipelineCommand::SetEdgePredictorShadow { shadow_mode, engine: Option<String> }` per-engine
- `PipelineCommand::DisableEdgePredictorAll`（NEW，QC S5）— 一鍵全局關閉，fallback 至 shrinkage
- Artifact 保留 14d（`settings/models/archive/`）

**F3b · `DisableEdgePredictorAll` 持久化語義（QA-D2 + AI-E U1/U2/U4 必修）**：

**IPC 消息定義（U3 同構）**：
```rust
PipelineCommand::DisableEdgePredictorAll {
    operator_token: String,   // U1: Python IPC proxy 層代填 session token
    reason:         String,   // audit log 用
}
```

**U1 · 授權 envelope（分層設計）**：
- **Python 層**（`control_api_v1/app/live_session_routes.py` 類似既存 pattern）：caller 須已持有 `_EXECUTION_AUTHORITY_OVERRIDE == "granted"`，否則 HTTP 403；通過檢查後才向 Rust 發 IPC，`operator_token` 由 Python 從 session 生成傳入
- **Rust 層**（`ipc_server/handlers.rs`）：IPC handler 驗 `operator_token` 非空、格式正確（e.g. `len >= 32`、UUID v4）；未來擴展可對 token 做 HMAC 驗證
- **Audit**：同一 token 寫入 `audit.events` → 事後可追蹤觸發 operator
- **差異化**：此授權檢查**只**作用於 `DisableEdgePredictorAll` 與 `SetEdgePredictorShadow`；`ReloadEdgePredictor` 屬於資料面操作走既有 `ReloadRiskConfig` 既存授權路徑

**U2 · Helper 升級（任務 #27 併修）**：
當前 `rust/openclaw_engine/src/config/store.rs::write_toml_atomic()` L231-244 **僅做 `write → rename`，無 `fsync`**，在 crash window（OS buffer 未刷）下 TOML 可能丟失。Task #27 Step 7 (IPC 接線) 併修：
```rust
fn write_toml_atomic_fsynced<T: Serialize>(cfg: &T, path: &Path) -> Result<(), String> {
    let toml_str = toml::to_string(cfg)?;
    let tmp = path.with_extension("toml.tmp");
    // create_dir_all 同前
    {
        let mut f = std::fs::File::create(&tmp)?;
        f.write_all(toml_str.as_bytes())?;
        f.sync_all()?;             // NEW: fsync tmp 檔內容
    }
    std::fs::rename(&tmp, path)?;
    // NEW: fsync parent dir（否則 rename metadata 可能未落盤）
    if let Some(parent) = path.parent() {
        std::fs::File::open(parent)?.sync_all()?;
    }
    Ok(())
}
```
Kill-switch path 使用 `write_toml_atomic_fsynced()` 而非舊版（其他非關鍵路徑可保留舊 helper 避免性能回歸）。**CC #13 驗證**：寫入後立即 `SIGKILL` engine → 讀 TOML 驗 `use_edge_predictor=false` 確實落盤（regression test `test_disable_all_survives_sigkill`）。

**執行步驟（atomic sequence）**：
1. 對 Paper/Demo/Live 三 `RiskConfigStore`：`use_edge_predictor = false`（in-memory only 先）
2. **Stage 1（全 fsync 都完成才算 commit）**：對三引擎分別 `write_toml_atomic_fsynced()` 寫 `settings/engine/{paper,demo,live}.toml` 的 `[edge_predictor]` section；任一失敗 → **全 abort**（三 `RiskConfigStore` in-memory flag 回滾）
3. **Stage 2**：三 ArcSwap 依序 swap；此步無 I/O，近乎無失敗可能
4. **Audit**：`INSERT INTO audit.events (event_type, operator_token_hash, reason, ts) VALUES ('edge_predictor_disabled_all', sha256(token), reason, now())`

**U4 · Partial-failure 語義**：
- Stage 1（fsync）失敗 → 安全 abort，沒任何副作用
- Stage 1 與 Stage 2 之間 crash → 重啟後三 TOML 全是 `use_edge_predictor=false`（符合 operator 意圖）
- Stage 2 過程 crash（極罕，rename 之後）→ 重啟後同樣讀到 `false`（Stage 1 已落盤）→ 等效 success
- 不存在「半啟用」情況

**重啟存活**：engine watchdog 自動重啟時讀 TOML → `use_edge_predictor=false` 仍然生效（不會因 ENGINE-HEAL 重啟「遺忘」kill-switch 狀態）

**回復（重新啟用）**：operator 需顯式發 `SetEdgePredictorShadow{shadow_mode=true, engine=..., operator_token}` 3 次（per engine）才逐一重新啟用，防止誤 revert

**返回契約**：`DisableEdgePredictorAll` 在 Stage 1 全部 fsync 落盤 + Stage 2 三 ArcSwap swap 全部完成後才返回 `Ok`；Stage 1 失敗回退 + 報錯（不半啟用）；Stage 2 罕見失敗 → loud alert（P1）+ 繼續使用舊 config 但 TOML 已是新狀態，operator 下次重啟即自動取齊。

---

## 九、Safety Invariants（C15 · 12 條）

1. Shadow ≥14d + Paper ≥7d + Demo ≥7d 才能 promote live
2. Feature freeze at entry instant（Open emission reset tracker）
3. Per-strategy 獨立模型
4. 推理失敗 fail-closed → shrinkage
5. 不觸 LinUCB
6. schema_hash + definition_hash 不匹配 fail-closed
7. Paper/Demo/Live artifact 分離
8. Live active 需 operator 手動
9. Label 僅來自真實 close fill
10. Outlier clamp 僅在訓練時
11. **（NEW）Model staleness**：`age(artifact) ≤ 2 × retrain_cadence` 否則 fail-closed
12. **（NEW）Feature value range sanity**：每 feature 有 hard range + NaN/Inf 拒絕 → fail-closed

---

## 十、Observability（C16）

### 10.1 Metrics（完整列表）

| Metric | 標籤 |
|---|---|
| `edge_predictor_predict_latency_us` | engine, strategy, quantile |
| `edge_predictor_predict_errors` | engine, strategy, error_type |
| `edge_predictor_shadow_vs_shrinkage_disagree_rate` | engine, strategy |
| `edge_predictor_feature_missing_count` | engine, strategy, feature |
| `edge_predictor_feature_out_of_range` | engine, strategy, feature |
| `edge_predictor_schema_hash_mismatch` | engine, strategy |
| `edge_predictor_definition_hash_mismatch` | engine, strategy |
| `edge_predictor_quantile_crossing_count` | engine, strategy |
| `edge_predictor_quantile_crossing_fatal` | engine, strategy |
| `edge_predictor_decile_lift_rolling_7d` | engine, strategy |
| `edge_predictor_rolling_coverage_7d` | engine, strategy, quantile |
| `edge_predictor_epsilon_greedy_exploration` | engine, strategy |
| `edge_fallback_terminal` | engine, strategy |

### 10.2 Alerts（量化版 QA C16）

| 優先級 | 條件 | 視窗 | Playbook |
|---|---|---|---|
| **P1** | `schema_hash_mismatch > 0` OR `definition_hash_mismatch > 0` | 即時 | auto-revert shadow 該策略 + page on-call |
| **P1** | `predict_errors > 10%` | 5m | auto-fallback shrinkage + page |
| **P2** | `predict_errors > 2%` | 1h | Slack notify |
| **P2** | `p99_latency > 5ms` | 15m | Slack + 檢查 tick flood |
| **P2** | `feature_missing_count > 2%` per-feature | 1h | Slack 上游 owner |
| **P2** | `quantile_crossing_fatal > 0.5%` | 1h | Slack + 排 retrain |
| **P3** | `decile_lift_rolling_7d < 1.0` | 3d | retrain ticket 48h 內 |
| **P3** | `rolling_coverage_7d` drift > 5pp | 1d | retrain 觸發 |
| **P3** | `shadow_vs_shrinkage_disagree_rate` WoW 漂 >20% | 1w | FA review |
| **P3** | artifact age > 21d | 每日 | retrain |
| **P2** | `edge_fallback_terminal > 0`（engine ∈ {demo, live}）**首次觸發** | 即時 | **Slack page + on-call runbook §4** — Live/Demo 雙層失效即 fail-closed 全部被拒，1h 延遲不可接受 |
| **P3** | `edge_fallback_terminal > 0` 連 1h（engine = paper） | 1h | 調查雙層失效，paper 已 fail-open 影響僅記錄品質 |

**F10 · On-call Runbook**：所有 P1/P2 alert 附 runbook 連結 `docs/runbooks/edge_predictor_on_call.md`（FA Stage 3 前交付，內容：5-min 診斷路徑 / disable kill-switch 操作步驟 / 各 metric 常見失效來源對照表 / escalation ladder）。

---

## 十一、Scope / Out of Scope

### 11.1 In Scope v1.1

- 5 策略 × 3 分位 = 15 ONNX artifact（+ 15 shadow-only for 200-500 n cells if any）
- 17 feature schema v1
- Rust tract-onnx 推理 + ort fallback + per-engine ArcSwap
- CQR calibration + Rust 端 monotone rearrangement
- cost_gate `edge_predictor_gate` + shrinkage fallback + terminal fallback
- Shadow → paper → demo → live 四階段 rollout
- `learning.decision_features` + `decision_context_snapshots` 8 列 + `trading.fills.entry_context_id`
- 12 invariants
- ε-greedy 5% exploration（paper 引擎 only）
- macOS CI tract-onnx build matrix

### 11.2 Out of Scope（v2）

- NGBoost 取代 LGBM
- Conformal prediction wrapper（v1.1 用 CQR 已解 tail）
- LinUCB confidence bound 作 feature
- BTC 跨資產 regime / VWAP 偏離
- DL3 foundation models 作 feature
- Multi-output quantile LGBM（視 Stage 2 實測再決）

### 11.3 明確不做

- 動 LinUCB
- 改 cost_gate_live fail-closed
- 移除 James-Stein shrinkage（保留 fallback）
- 移除 `edge_estimates.json`

---

## 十二、分工交接清單

### 12.1 PA（架構）— 4 件

1. **SQL migration**：`learning.decision_features` 新表（含 definition_hash + split_flag）
2. **SQL migration**：`learning.decision_context_snapshots` 加 8 列
3. **SQL migration**：`trading.fills.entry_context_id` 列
4. **`parquet_etl.py`** 擴 Feature store 接入 + split-blend label backfill job + reconcile 7d NULL alerter

### 12.2 ML-MIT（模型）— 6 件

1. 補 `run_training_pipeline.py::load_training_data()`
2. Linear QR floor baseline
3. Per-strategy quantile LGBM（num_leaves=7, early_stop 500）+ sample_weight decay + funding_arb CPCV carve-out
4. **CQR calibration**（取代 Isotonic）
5. Pinball skill / coverage / decile lift bootstrap / crossing rate 報告
6. ONNX 匯出 + 雙 runtime 精度驗證（tract + ort）+ `onnxmltools>=1.12`

### 12.3 AI-E（接線）— 7 步（AI-E 建議順序）

1. **`edge_predictor/features.rs`** — FeatureVectorV1 + range clamp + NaN 拒絕
2. **`edge_predictor/{mod,null_backend,rearrangement}.rs`** + `PerEnginePredictors` 結構
3. **`OrderIntent` typed 字段** + 3 confluence 策略 populate + `PersistenceTracker.consume_elapsed()` + `paper_state.count_same_direction()`
4. **`edge_predictor_gate()`** in `gates.rs` + `RiskConfig.edge_predictor` section + terminal fallback
5. **`PaperPosition.entry_context_id`** + `emit_close_fill` propagation + `TradingMsg::Fill.entry_context_id`
6. **`tract_backend.rs`** + `ort_backend.rs`（feature-flagged）+ warm-up predict
7. **IPC 全套 + Python consumer + helper 升級**（U1-U4 集中點）：
   - `DecisionFeatureSnapshot` IPC（既有設計）+ Python consumer → `learning.decision_features`
   - **`EmitShadowFill` IPC**（U3 新增）+ Python consumer → `learning.decision_shadow_fills`（含 CHECK `engine_mode='paper'`）
   - `ReloadEdgePredictor{engine, strategy, path}`（資料面，既有授權）
   - `SetEdgePredictorShadow{engine, operator_token}`（U1 分層授權）
   - `DisableEdgePredictorAll{operator_token, reason}`（U1 分層授權 + U2 fsync + U4 兩階段 commit）
   - **`write_toml_atomic_fsynced()` helper 併修**（U2，`rust/openclaw_engine/src/config/store.rs`）— kill-switch path 切換使用，附 `test_disable_all_survives_sigkill` 回歸測試
   - `GET /api/v1/engine/capabilities`（backward-compat）

### 12.4 CC（審查）— 13 項必查（v1.3 從 12→13，加 U2 fsync 驗證）

1. **Label leakage 檢查**：feature vector 無 close 後可得量；FeatureVectorV1 field provenance 自動掃描
2. **Train-serve skew**：tract & ort vs Python LGBM max abs error < 1e-3 at 1000 random vectors
3. **Fail-closed 回退路徑全鏈**：predictor → shrinkage → terminal 三級都驗證
4. **Schema + definition hash 防呆**
5. **Per-strategy 隔離負測試**：策略 A ONNX 載入策略 B slot 應拒絕
6. **Paper/Demo/Live artifact 隔離**
7. **Regression tests**：`edge_predictor_tests.rs` ≥ **22 case**，具名 T1..T22 見下表
8. **Quantile crossing property test**：10^5 random → rearrangement 後 q10 ≤ q50 ≤ q90 恒真
9. **Disaster scenarios**：file corruption / disk full / ArcSwap torn read / Python consumer down → 皆 fail-closed 不 panic
10. **macOS CI matrix**（M1 平台 tuple 明確化）：
    - **`aarch64-apple-darwin`**（**必**，Apple Silicon M1/M2/M3/M4，operator 未來部署目標；GitHub `macos-14`/`macos-15` runner 默認已是 ARM64）
    - `x86_64-apple-darwin`（建議，Intel Mac backward compat；runner `macos-13`）
    - **不**包含 `aarch64-unknown-linux-gnu`（linux-arm64 是 Linux-on-ARM 如 NAS / Pi，**與 macOS arm64 不同 platform tuple**，此項 QA-E6 延後不影響 Mac 部署）
    - 驗證範圍：tract-onnx build + precision test + 7.2 ArcSwap concurrent test
11. **（F4）Shadow-fill label 排除**：`learning.decision_shadow_fills` 的 context_id **從不**出現在 `learning.decision_features.label_net_edge_bps` 非 NULL 行；自動 SQL 反向斷言（training 前置 check）
12. **（F3b）Kill-switch 持久化**：`DisableEdgePredictorAll` 後 kill engine → restart → `use_edge_predictor` 三引擎皆 `false`；TOML 檔 fsync 過；audit event 記錄存在
13. **（NEW U2）fsync helper 行為驗證**：新增 `test_write_toml_atomic_fsynced_survives_sigkill` — 寫 TOML → `libc::SIGKILL` engine → 讀檔驗內容與預期一致；**strace 驗證** `fsync()` 系統呼叫確實觸發（CI 跑 `strace -e fsync` 檢證）

---

**F5 · T1..T22 regression 具名清單**（`rust/openclaw_engine/tests/edge_predictor_tests.rs`）：

| # | 測試名 | 類別 | 斷言 |
|---|---|---|---|
| T1 | `test_feature_vector_snapshot_at_open` | Feature freeze | Open emission 時 17 維全部填入，type 正確 |
| T2 | `test_persistence_elapsed_reset_on_open` | Feature freeze | consume_elapsed() 呼叫後 first_ts=None |
| T3 | `test_feature_out_of_range_triggers_fallback` | Invariant #12 | adx=150 注入 → fallback_shrinkage + metric |
| T4 | `test_feature_nan_inf_triggers_fallback` | Invariant #12 | NaN/Inf 單 feature → fallback |
| T5 | `test_schema_hash_mismatch_fail_closed` | Invariant #6 | schema_hash 改 1 位 → NoModel-like fallback |
| T6 | `test_definition_hash_mismatch_fail_closed` | Invariant #6 | formula 字串改 → fallback |
| T7 | `test_model_staleness_fail_closed` | Invariant #11 | artifact mtime > 2×cadence → fallback |
| T8 | `test_predictor_noModel_falls_back_to_shrinkage` | Fail-closed | 空 store → fallback；shrinkage cell hit → accept |
| T9 | `test_terminal_fallback_paper_fail_open` | §7.4 | 雙層失效 + Paper → GateDecision::Accept + metric |
| T10 | `test_terminal_fallback_demo_fail_closed` | §7.4 | 雙層失效 + Demo → Reject + metric |
| T11 | `test_terminal_fallback_live_fail_closed` | §7.4 | 雙層失效 + Live → Reject + metric |
| T12 | `test_quantile_crossing_rearranged` | §2.2 | 注入 q10=5, q50=3, q90=4 → rearrangement 後 (3,4,5) |
| T13 | `test_quantile_crossing_property_1e5_random` | §2.2 | 10^5 隨機 → always q10≤q50≤q90 post-rearrangement |
| T14 | `test_q10_negative_blocks_add` | Gate | pred=(-5,10,20), require_q10_positive → RejectAdd |
| T15 | `test_safety_margin_below_cost_rejects` | Gate | q50=10, q10=0, k=0.5, cost=8 → margin=5<8 → Reject |
| T16 | `test_epsilon_greedy_paper_only` | §7.3 | engine=Demo + margin reject → 永不觸發 shadow fill |
| T17 | `test_epsilon_greedy_rate_approx_5pct` | §7.3 | 10^4 rejects in Paper → shadow_fill count ∈ [450, 550] |
| T18 | `test_arcswap_hot_reload_no_torn_read` | §7.2 F9 | 1000 concurrent predict × 100 swap → 無 panic / 無 NaN 輸出 |
| T19 | `test_per_strategy_isolation_negative` | CC #5 | MaCrossover artifact 塞 bb_breakout slot → load 拒絕 |
| T20 | `test_per_engine_isolation` | CC #6 | Paper 模型寫 Live 路徑 → Live store 不載入 |
| T21 | `test_disable_all_persists_across_restart` | F3b | disable → kill → restart → use_edge_predictor=false 三引擎 |
| T22 | `test_shadow_fill_row_never_in_training_labels` | F4 | 灌 shadow fill → run backfill → 該 context_id 無 label row |
| T23 | `test_write_toml_atomic_fsynced_survives_sigkill` | U2 | 寫 TOML → `kill -9` → 讀檔驗內容；`strace -e fsync` 驗證 syscall 觸發 |

執行：`cargo test -p openclaw_engine --test edge_predictor_tests -- --nocapture`。CI gate：**23/23** pass 才允許合併（v1.3 新增 T23）。

### 12.5 FA（持續 owner）

- v1.x spec 維護
- Stage gate 決策（promote / rollback）
- 週 review 4 層 metrics（shadow→paper→demo→live）
- Round-2 / Round-3 review 整合
- **F10 · `docs/runbooks/edge_predictor_on_call.md` Stage 3 前交付**（P1/P2 告警引用路徑，內容：5-min 診斷路徑 / kill-switch 操作 / metric 失效對照 / escalation ladder）

---

## 十三、時程估計（v1.1 調整）

| Stage | 工作量 | 前置 |
|---|---|---|
| Round-2 review（QC/QA/ML-MIT/AI-E 覆審 v1.1）| ~2d | 本文件 |
| Stage 0 Feature 接線 | AI-E ~12h（從 8→12，加 3 新 feature）| Round-2 pass |
| Stage 1 Label 回填 | PA ~8h | Stage 0 部分完成 |
| Stage 2 訓練管線 | ML-MIT ~18h（從 12→18，加 CQR + 雙 runtime + baseline）| Stage 1 數據就緒 |
| Stage 3 Shadow 14d | 計時 + rollback drill | Stage 0-2 完成 |
| Stage 4 Paper active 7d | 計時（auto-check 7 條通過後 operator 啟動）| Shadow pass |
| Stage 5 Demo active 7d | 計時 + operator 確認 | Paper active pass |
| Stage 6 Live（永遠手動）| 2026-05-30+ | Demo active + 21d 累計 |

**關鍵路徑**：`Round-2 → Stage 0 → Stage 1 → Stage 2 → Stage 3 (14d) → Stage 4 (7d) → Stage 5 (7d)`

**最早 Live 日期**：視 Stage 0-2 實施速度；樂觀 2026-05-30，保守 2026-06-15+。

---

## 十四、FAQ / 邊界情況（v1.1 更新）

**Q1 Paper/Demo/Live 模型隔離？** 不變。Paper fills 訓 paper artifact（僅觀察），Demo+Live 訓 prod。

**Q2 冷啟動 n<200？** predictor 無 model → `NoModel` → 走 shrinkage。

**Q3 策略 X 樣本少訓不出？** n<200 無 model；200≤n<500 ship shadow artifact（僅記錄 latency/coverage）；n≥500 ship prod artifact 可 gate 交易。

**Q4 Feature 缺失 / NaN / out-of-range？** 不使用 predictor 此次，走 shrinkage，emit metric（不等到 shadow 期才發現數據品質問題）。

**Q5 GUI 展示？** Stage 4+ `tab-risk.html` 新 "Edge Predictor" section：per 策略 q10/q50/q90 近 24h 分佈 + coverage rolling + agreement rate + 模型 age + 下次 retrain ETA。

**Q6 Shadow 表現差於 shrinkage？** 7 auto-check 任一未過 promote button 不出現 → 回 Stage 2 retrain。

**Q7 這替代 Phase 5？** 不。Phase 5 是 draft→active 升級流程；本規格只讓 cost_gate 變聰明。

**Q8 ONNX quantile LGBM 能匯出？** `onnxmltools>=1.12` 修復了先前 silent quantile bug；Stage 2 用 synthetic 已知分位驗證強制確認（詳 CC #2）。

**Q9 tract 若不行怎麼辦？** Cargo feature flag 切 `ort`。spec 不變；實施細節切換。

**Q10 ε-greedy 5% 在 Paper 引擎做什麼？** 拒絕的機會中 5% 寫 "shadow-filled" 合成 fill 記真實結果，保證 off-policy 探索樣本不為零。Demo/Live 不做。

**Q11 Monotone rearrangement 會扭曲預測嗎？** 僅在越界時觸發（預期 <1%），rearrangement 是保守操作不改業務語意。若違反率 >1% on holdout 本應拒絕 ship。

---

## 十五、狀態與簽核

- **2026-04-15 v1.0**：FA 起草完成
- **2026-04-15 v1.1**：整合 QC/QA/ML-MIT/AI-E round-1 review（4 位全部 GREEN with adjustments 條件通過）
- **2026-04-15 v1.2**：整合 round-2 must-fix 10 項（F1-F10）。Round-2 投票：AI-E GREEN / ML-MIT GREEN · 1 YELLOW caveat / QC YELLOW / QA YELLOW，所有阻塞項已修
- **2026-04-15 v1.3**：整合 round-3 AI-E YELLOW 3 must-fix（U1 auth 分層 / U2 fsync helper 升級 / U3 EmitShadowFill IPC 契約）+ operator 提醒的 Apple Silicon Mac 平台 tuple 標註（M1）。Round-3 投票：QC GREEN / QA GREEN / ML-MIT GREEN / AI-E YELLOW → 全修後預期 GREEN
- **下一步**：operator 簽核 → Stage 0 開工（AI-E task #27 Step 1/2/3/5/6 可即刻開始；Step 4/7 等 U1-U3 spec 條款落實完畢即解鎖；PA task #25 無阻礙）

---

## 附錄 A · 與既有計劃關係（同 v1.0）

- `ml_dl_learning_architecture_v0.4.md`：本規格是 v0.4「Signal Quality Scorer (LightGBM)」的具體落地版本
- `g_sr1_signal_tightening_plan_v2.5.md`：G-SR-1 收緊 strategy 層信號；本規格在 gate 層加條件過濾
- `project_edge_data_isolation.md`：延續並強化 paper / demo / live 資料隔離至 model artifact 級別
- `TODO.md EDGE-P3-1`：本文件為該任務的 FA spec

---

## 附錄 B · Round-1 Review 歸檔

四角色平行審查 v1.0 於 2026-04-15 完成。整體結論：**GREEN with adjustments**（架構通過，需 v1.1 修訂）。全部意見已在 CHANGELOG 反映。以下為各角色關鍵發現摘要。

### B.1 QC（對抗性審查）

**Blockers（4）**：
- **B1** persistence freeze 脆弱：PersistenceTracker 只在 close 後 clear，二次 open pre-close 繼承舊 first_ts → **v1.1 §3.1 Open emission 同步 reset**
- **B2** `expected_slippage_bps` 靜態 tier 與 label fee 扣除重複（tautological）→ **v1.1 §3.2 刪除**
- **B3** Quantile crossing 未守：三獨立 fit 2-5% 概率 q10>q50 → **v1.1 §2.2 雙保險 + §7.3 rearrangement**
- **B4** Fallback-of-fallback 未定義（shrinkage 也可能失效）→ **v1.1 §7.4 terminal fallback**

**Majors（6）**：
- **M1** schema_hash 只覆名字不覆意義（TF/sign/公式變）→ **v1.1 §3.3 per-feature definition_hash**
- **M2** split close_tag 同 entry_context_id label 衝突 → **v1.1 §4.2 qty-weighted blend + split_flag**
- **M3** decile lift n=200 統計不穩 → **v1.1 §6.2 bootstrap 1000 下界 >1.3 + §6.5 n≥500 prod**
- **M4** off-policy coverage collapse → **v1.1 §7.3 5% ε-greedy（paper only）**
- **M5** 缺 model staleness invariant → **v1.1 §9 invariant #11**
- **M6** 缺 feature range sanity clamp → **v1.1 §3.2 range clamp 欄 + invariant #12**

**採納的 Suggestions**：S3 CQR/conformal tail 校準（§2.2）；S5 `DisableEdgePredictorAll` 1-button（§8.8）

### B.2 QA（測試與驗收）

**Conditional Pass — 5 條 tightening**：
1. **7 條 auto-check before promote button** → v1.1 §8.5
2. **decision_context_snapshots 加 8 列** → v1.1 §5.1
3. **Quantile crossing defense** → v1.1 §2.2 + property test
4. **Stage 3 強制 rollback drill** → v1.1 §8.4
5. **Test 15→22 case** → v1.1 §12.4 #7

**結構化要求**：Acceptance criteria table 量化 / Monitoring alerts P1/P2/P3 量化 / Sampling protocol（每 Open 都 predict 不抽樣）/ 災難場景（file corruption / disk full / ArcSwap race / consumer down）/ macOS CI matrix — 全部 v1.1 落實

### B.3 ML-MIT（模型合理性）

**必改**：
- **Isotonic → CQR**（tail 友善）→ v1.1 §2.2
- **Label 加 funding accrual**（perp 策略非可選）→ v1.1 §4.1
- **Hyperparam 收緊**：num_leaves 7-10 / min_data_in_leaf 自適應 / early_stop → v1.1 §6.3
- **Retrain 週期 daily→weekly** + daily drift → v1.1 §6.4
- **funding_arb CPCV carve-out**（3-fold 或 60d）→ v1.1 §6.1
- **Sample weight `exp(-days/14)`** → v1.1 §4.4 + §6.1
- **n≥500 prod / 200-500 shadow-only** → v1.1 §6.5
- **Linear QR floor baseline** → v1.1 §2.1 + §6.2
- **`onnxmltools>=1.12` pin**（quantile silent bug）→ v1.1 §7.1
- **tract LightGBM 歷史 bug 警告** → v1.1 §7.1 雙 runtime 策略
- **Feature 新增**：`realized_vol_1h` / `orderbook_imbalance_top5` / `tod_sin/cos` / `is_funding_settlement_window` → v1.1 §3.2

**延後 v2**：NGBoost、BTC 跨資產、VWAP、LinUCB confidence

### B.4 AI-E（工程可行性）

**GREEN 採納**：
- **tract-onnx 主線 +3.5MB**（vs ort +60MB），feature-flag 封裝 → v1.1 §7.1
- **OrderIntent typed 字段**（拒絕 HashMap metadata）→ v1.1 §3.2 feature #9/#10
- **basis_bps 用現有 `TickContext.index_price`**，無需改 PriceEvent → v1.1 §3.2 feature #6
- **`paper_state.count_same_direction()` O(n≤100) = ~100ns**，免索引
- **`PerEnginePredictors` 平行 RiskStores**（不內嵌）→ v1.1 §7.2
- **Per-strategy ArcSwap**（不升 EdgeEstimates）→ v1.1 §7.2
- **IPC per-engine selector**：`ReloadEdgePredictor{engine, strategy, path}` + `SetEdgePredictorShadow{engine}` → v1.1 §8.8
- **`GET /api/v1/engine/capabilities`** backward-compat → v1.1 §12.3 #7
- **7 步 implementation order** → v1.1 §12.3

**Open questions**（v1.1 已答）：
- Paper restart 遺失 entry_context_id 可接受（Paper 重啟少見；Demo/Live reconciler hydrate）
- Orphan adoption 寫 `"orphan:*"` 前綴 label 回填 skip
- tract LightGBM opset 兼容 Stage 2 CC 強制驗證

---

（END v1.1）
