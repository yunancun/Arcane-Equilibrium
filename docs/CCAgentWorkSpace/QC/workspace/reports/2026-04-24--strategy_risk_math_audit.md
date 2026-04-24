# QC 策略・風控・數學審計（2026-04-24）

Author: QC (Quantitative Consultant)
Scope: Rust `openclaw_engine` / `openclaw_core` 全策略＋風控＋數學層面 + Python `james_stein_estimator.py` + cost_gate / kelly_sizer / stop_manager / guardian。
Baseline: engine lib 1980 / 0 failed @ HEAD `1a53400`（含 FIX-26-DEADLOCK-1 未 rebuild）。

---

## 0. TL;DR（行政摘要）

- **策略算法層總體健康**：ATR 已修為 Wilder 14 on kline 1m OHLCV（P0-13）、Bollinger/MACD/KAMA/Hurst/EWMA 用 Kahan summation、trailing-stop 有 activation gate 防鎖損、funding_arb edge amortization 公式正確、JS shrinkage positive-part 公式正確、`physical_micro_profit_lock_v2` 4-Gate 語意與設計一致（Gate 1 Hold 非 Lock）。**重大正向**。
- **重大數學風險 3 項**：
  1. **Donchian leak-free bias（F3 RETRACT 已驗）**：`openclaw_core/indicators/trend.rs::donchian` 視窗 `&high[n-period..n]` 含 current bar；`bb_breakout/mod.rs:532` `ctx.price < dc.upper` 門控在 current bar 就是 max 時必然 degenerate pass（同理 mean-revert direction）。memory `feedback_indicator_lookahead_bias.md` 已標；修正 = `shift(1)` 或 `&high[n-period-1..n-1]`（排除 current bar）。CLAUDE.md 已記 Phase 1 sweep retract 結論，但 **runtime 代碼尚未 shift 修復**。
  2. **Grid OU σ 估計有偏**：`strategies/grid_helpers.rs::compute_ou_step` line 128 用 `sigma = sqrt(Σ Δx²/n)`，這是 raw second moment 非 residual std；OU `Δx = -θX + ε` 的 `σ_ε` 應扣 drift（`sqrt(Σ(Δx-mean_dx)²/n)`）。當 `mean_dx` 非零（趨勢期接近 0 fails b>=0 那條路徑已擋掉主要誤用），但 ranging 期 mean_dx 雖小仍 biased 高估 σ → 高估 ou_step → 網格間距偏大，fewer fills。影響中度。
  3. **Kelly tier 邊界寫死（50 / 200 trades）**：`ml/kelly_sizer.rs:153-159` `kelly_full/8`、`/6`、`/4` tier 硬寫，與 `KellyConfig` 解耦；operator memory 明言「200+ 筆同 regime」是邊界 — 未來要按 regime shift reset 樣本計時器時沒 knob。**可調性問題，不是數學錯誤**。

- **風控邏輯**：P0/P1/P2 三層 + fast_track + Gate 1.6 negative balance + Guardian 4 check + trailing_activation_pct 鎖損修補 + Priority 6 v2 swap 已 live；**結構健全**，fast_track line 64 `margin_utilization_pct >= 90.0` 是 Bybit 物理常數無需參數化（已文件化）。

- **硬編碼熱點 7 類** — 詳見 §3。最嚴重：SLIPPAGE_TIERS（整張表 const）、confluence ADX divisor `50/25`、cost_gate `1.3` safety margin、bb_breakout `2_700_000` squeeze_expiry (與 TOML 有 duplicate)、Guardian risk_score weights `0.4/0.3/0.15/0.35` + verdict threshold `0.3`。

- **數學部署可用性**：NaN/Inf/div-by-0 基本防守到位（Kahan、`sq_sum > 1e-15`、`atr > 0.0 && is_finite`、`non_linear_giveback_fn` clamp non-finite 到 0）。**唯一殘留**：`volatility.rs::ewma_vol` 用 `(w[1]/w[0]).ln()`（line 278）無 `w[0] > 0` guard — 若 price 0.0 會 NaN propagate（low risk，crypto spot 不會 0 但 synthetic data 會）。

---

## 1. 策略算法檢驗

### 1.1 `bb_breakout` — Bollinger Squeeze → Expansion + Volume + Donchian

**File**: `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` (lines 357-800)
**Math correctness**: ✅ 核心正確；**Donchian leak-free bias 存在**。

| 項 | 評估 |
|---|---|
| bandwidth squeeze (`bb.bandwidth < squeeze_bw`) | 正確，P1-11 F1 確認 1m scale mismatch（squeeze=0.03 100% trigger，expansion=0.04 unreachable）是結構性 parameter tuning 問題非數學錯 |
| FIX-26-DEADLOCK-1 修補 | ✅ 2026-04-24 `bcc5401`：`squeeze_detected_ms` 過期 auto-clear 前置於 `is_none()` guard；saturating_add 避免 u64 wrap；已待 rebuild |
| Donchian 確認門（Hard mode）| ⚠️ `ctx.price < dc.upper` / `price > dc.lower` 用 current-bar-inclusive donchian — **leak bias** |
| Trailing stop（Chandelier 2×ATR from peak）| ✅ 單向 ratchet，ATR 從 kline 1m Wilder(14) |
| Regime exit（Hurst flip）| ✅ 邏輯對 |
| %B revert exit `[0.2, 0.8]` | 硬邊界但可配置（exit_pctb_lower/upper）|
| OI buffer dedup + monotonic ts guard | ✅ E2 FUP finding #1+#6 已修 |

**Finding BB-01 (HIGH / Math correctness)**
- File: `openclaw_core/src/indicators/trend.rs:190-194`
- Issue: Donchian uses `&high[n-period..n]` (inclusive of current bar). bb_breakout Hard mode at `mod.rs:532-537` treats breach as `price >= dc.upper`. When current bar's high IS the max-of-last-20, breach is mechanically guaranteed → false positive entry; mirror issue on mean-revert direction via bb_reversion (does not use donchian directly, but same `rolling(N).max()` pattern).
- Math: `dc.upper = max(high[n-20..n]) = max(..., high[n-1])`; but `ctx.price ≈ high[n-1]` at breakout check time → `price >= dc.upper` reduces to `price >= price`, always true.
- Severity: **HIGH** — CLAUDE.md F3 retract already identifies this as measurement bias under leak-free shift(1). P1-11 Phase 1 sweep concluded signal effect disappears under shift — but runtime strategy code **still uses inclusive window**.
- Suggestion: In `donchian()`, change window to `&high[n-period-1..n-1]` (exclude current bar). Same for `low`. Update callers/tests. Alternative: add a `shift: usize` parameter defaulting to 1 for research tooling and 0 for back-compat, then flip callers.

**Finding BB-02 (LOW / Semantic)**
- File: `bb_breakout/mod.rs:188-189`, `params.rs:250`
- Issue: `squeeze_expiry_ms = 2_700_000` (45 min) is duplicated in `BbBreakout::new()` literal and `BbBreakoutParams::default()` literal — two sources of truth for same default.
- Severity: **LOW** — consistency hazard on future edits.
- Suggestion: Extract `pub(crate) const DEFAULT_SQUEEZE_EXPIRY_MS: u64 = 2_700_000;` like `DEFAULT_SQUEEZE_BW`.

### 1.2 `bb_reversion` — %B extreme + RSI 過濾

**File**: `rust/openclaw_engine/src/strategies/bb_reversion.rs`
**Math correctness**: ✅ 正確。

| 項 | 評估 |
|---|---|
| %B < 0 + RSI < rsi_oversold → long | ✅ textbook reversion |
| Exit at %B ∈ [0.2, 0.8] | ✅ exit_pctb_lower/upper 可配置 |
| EDGE-P1-2 funding rate directional boost | ✅ 方向對（正 funding → over-long crowd → short reversion boost）|
| Hurst regime_boost 限定 `mean_reverting` | ✅ |
| Confluence inverted ADX (`1 - adx/50`) | 硬編碼 50（見 §3 confluence 硬編碼）|

**Finding BR-01 (MEDIUM / Math precision)**
- File: `openclaw_core/src/indicators/volatility.rs:278`
- Issue: `ewma_vol` 計算 `(w[1]/w[0]).ln()` 無 `w[0] > 0` guard。若 close 含 0.0 或 negative（synthetic test / data corruption）→ ln(neg) = NaN，regime classification `ewma < 0.6 * hist_mean_vol` 退化。
- Math: `if !(w[0] > 0.0 && w[1] > 0.0) { skip }` 對齊 `hurst()`'s filter (line 154)。
- Severity: **MEDIUM** — production feed 極不可能 ≤0，但對齊 hurst 的 defensive style 是零成本修補。
- Suggestion: `let returns: Vec<f64> = close.windows(2).filter(|w| w[0] > 0.0 && w[1] > 0.0).map(|w| (w[1] / w[0]).ln()).collect();`

### 1.3 `grid_trading` — OU-derived spacing + adaptive range

**File**: `rust/openclaw_engine/src/strategies/grid_trading/{mod,grid_layout,signal}.rs` + `grid_helpers.rs`
**Math correctness**: ⚠️ OU σ 估計有偏；其餘合理。

| 項 | 評估 |
|---|---|
| Level 構造（linear / geometric）| ✅ `ratio = (upper/lower)^(1/(n-1))`, 等比正確 |
| Nearest-level lookup | ✅ 線性掃描對小 grid ok |
| OU formula `step = max(σ√(2/θ), 2·fee·μ)` | ✅ 公式正確，fee floor 確保 step > round-trip cost |
| OU b 估計 `b = num/den = cov(ΔX, X_lag) / var(X_lag)` | ✅ 標準 OLS regression dx ~ X_lag；`b >= 0` fallback ±10% 合理 |
| θ = -b.max(0.01) | ✅ 最小 0.01 避免 divide-by-zero |
| σ estimation | ⚠️ **見 GT-01** |

**Finding GT-01 (MEDIUM / Math precision)**
- File: `strategies/grid_helpers.rs:128`
- Issue: `sigma = sqrt(Σ c² / n_f)` where `c = changes[i] = Δx_i`. 此為 raw 2nd moment，非 OLS residual std dev。OU 數學要求 `σ_ε = std of ε` where `Δx_i = b·X_lag_i + ε_i` — 因此 σ 應取 residual。在 strong mean-reversion 下 mean_dx ≈ 0 所以誤差小；但 weak drift 時高估 σ → step 偏大 → levels 過鬆 → fewer fills → grid edge 被稀釋。
- Math: `residual_i = changes[i] - (mean_dx + b*(x_lag[i] - mean_x))`；`sigma_eps = sqrt(Σ residual² / (n - 2))`（OLS df correction）。或至少用 `sqrt(Σ(changes - mean_dx)² / n)`（central 2nd moment）比 raw 2nd moment 更忠於 ε 的 scale。
- Severity: **MEDIUM** — 影響 spacing 但不是安全問題；grid_trading 當前 edge 負（TODO §P1-10 EDGE-P2-3 fee drag 主導）。
- Suggestion: 改 residual-based σ estimation；加單測：給定已知 OU process `dx = -0.1*x + 0.5*ε, ε ~ N(0,1)`，驗收恢復 σ ≈ 1 而非 raw second moment 的 ~sqrt(0.25 + drift²)。

**Finding GT-02 (LOW / Parameterization)**
- File: `strategies/grid_trading/mod.rs:78` `DEFAULT_GRID_COUNT = 10`, line 93 `DEFAULT_FEE_PCT = 0.00055`, line 96 `ADAPTIVE_RANGE_PCT = 0.10`
- Issue: 這些是策略基本參數；runtime 已有 TOML `grid_count`/`adaptive_range_pct`/`fee_rate` knob 接線，常數僅作 fallback。Config-vs-const 關係尚可，但 `DEFAULT_FEE_PCT = 0.00055` 寫死 0.055% 與 `intent_processor/mod.rs:214 DEFAULT_TAKER_FEE_RATE = 0.00055` 重複硬編碼不同 module，修 fee rate 需兩處改。
- Severity: **LOW**
- Suggestion: 引用 `intent_processor::DEFAULT_TAKER_FEE_RATE` 或上提至 `openclaw_core::constants`。

### 1.4 `ma_crossover` — KAMA × SMA20 + ADX gate + trend-adaptive cooldown

**File**: `rust/openclaw_engine/src/strategies/ma_crossover/{strategy_impl,helpers,config}.rs`
**Math correctness**: ✅ 正確。

| 項 | 評估 |
|---|---|
| KAMA as "fast" vs SMA20 as "slow" | ✅；KAMA fallback to SMA20 有 `tracing::debug` 警告，且 `fast == slow` 永不交叉 — 正確邊界 |
| ADX gate (`adx < adx_threshold` skip) | ✅ |
| ER-scaled exit persistence | ✅ 創新設計：choppy ER→0 → long persistence（避免假反轉），trend ER→1 → instant exit；KAMA-less 用 ER=0.5 mid fallback 也合理 |
| RC-02 higher TF confirmation | ✅ 用 sma_50 proxy |
| Regime 限定 + RC-01 | ✅ |

**Finding MC-01 (LOW / Win-rate asymmetry observation)**
- File: `ma_crossover/strategy_impl.rs` whole file + CLAUDE.md §三 P1-10
- Issue: CLAUDE.md 記錄「ma_crossover win rate 64% → 37.8% 崩」= 結構性 R:R 不對稱。**代碼數學無錯**；問題在於 exit path (reverse cross) 在趨勢反轉時距 entry 往往已經虧損穿越 hard-stop（而 profit side 依賴 trailing，止損優先順序 stop_manager.rs `Priority 0 TP > 1 Hard > 2 Trail > 3 Time`，reverse cross 只出現在 strategy-level exit）。
- Severity: **LOW / 策略設計** — non-actionable from math-audit perspective；operator 已在 §P1-10 觀察 EDGE-P2-3 PostOnly 驗證中。
- Suggestion: 記錄於本報告作 non-actionable 觀察；監控 post-PostOnly demo 資料，看 R:R distribution 是否收斂（≥1w 觀察）。

### 1.5 `funding_arb` — |funding rate| > threshold + edge + basis

**File**: `rust/openclaw_engine/src/strategies/funding_arb.rs`
**Math correctness**: ✅ 正確。

| 項 | 評估 |
|---|---|
| Edge = \|funding_rate\| − total_cost/expected_periods | ✅ amortized fee 除 expected_periods 是正確 amortization |
| 方向：positive funding → short perp | ✅ convention 正確（shorts receive funding）|
| Basis hysteresis: entry `max_basis × entry_basis_ratio` < exit `max_basis` | ✅ 防止瞬間 re-entry |
| Exit on rate flip / edge ≤ 0 / basis > max / max_hold 72h | ✅ 4 條出場條件邏輯齊全 |
| Confidence bps scaling `(edge_bps / 10.0).clamp(0.3, 0.9)` | ⚠️ 硬編碼 |

**Finding FA-01 (LOW / Hardcoded confidence bounds)**
- File: `funding_arb.rs:452-454`
- Issue: Confidence 縮放 `clamp(0.3, 0.9)` 寫死，`10.0` divisor 也寫死（10 bps edge → 1.0, clamp 回 0.9）。
- Severity: **LOW** — 與其他策略 `entry_conf_base` / `exit_conf_base` 可配置對齊原則不一致。
- Suggestion: 加 `FundingArbUpdateParams { conf_edge_scale: f64, conf_min: f64, conf_max: f64 }`；默認 10.0/0.3/0.9。

### 1.6 `sync_label` / `bybit_sync` — 4 strategies × 23 symbols proxy cells

**File**: `program_code/ml_training/james_stein_estimator.py:56-119` + Rust `exit_features/v2.rs:missing_edge_fallback_bps`
**Math correctness**: ✅ 邏輯正確。

| 項 | 評估 |
|---|---|
| 4 sync-label strategies 列舉 | ✅ `bybit_sync / orphan_adopted / orphan_frozen / dust_frozen` |
| Proxy cell `shrunk_bps = grand_mean_bps, n=0, _proxy_from="grand_mean"` | ✅ 弱先驗，provenance trackable |
| 不覆蓋已訓練 cell（key absent-only） | ✅ 防污染真實 label |
| Gate 1 Option A `missing_edge_fallback_bps = -10.0` (conservative) | ✅ 確保 `≤ min_net_floor_bps=5.0` → Hold (fail-safe preserved) |

**Finding SL-01 (NONE)** — 正確設計，無問題。

---

## 2. 風控邏輯檢驗

### 2.1 三層風控 P0/P1/P2

- **P0 (CategoryOverrides + fast_track CloseAll)**: `risk_config.rs:408` CategoryOverride + `fast_track.rs`.
- **P1 (GlobalLimits, operator hard ceilings)**: 26 欄位，完整 `validate()` 跨欄位 invariant（partial_tp levels ≤ take_profit_max_pct, min ≤ max notional）。
- **P2 (AgentParams, agent self-tunable)**: `size_multiplier ∈ [0.1, 1.0]`, `trailing_*` > 0，無硬 `max_concurrent` 但透過 StrategyOverride 覆蓋。

**Finding RK-01 (MEDIUM / Config duplication)**
- Files: `risk_config.rs:253 default_stop_loss_max_pct=5.0` 與 `stop_manager.rs:33 hard_stop_pct = 5.0`.
- Issue: Stop loss max 在兩個 module 各寫 `5.0`，沒有依賴關係；改 risk_config 不影響 stop_manager 默認。
- Severity: **MEDIUM** — ARCH-RC1 §"Rust ConfigStore 為所有交易/風控/學習/預算參數權威" 精神是單一真相，此為 drift 源。
- Suggestion: `StopConfig::from_risk_config(&RiskConfig) -> Self` 派生路徑；或 StopConfig 裡標注「this is a pre-hot-reload seed; production path uses apply_risk_snapshot」對齊 GuardianConfig.

### 2.2 fast_track emergency closure（margin + drop + sigma）

**File**: `rust/openclaw_engine/src/fast_track.rs`
**Correctness**: ✅ FA-PHANTOM-1 / FA-PHANTOM-2 regression tests pass; margin = leverage-aware notional/leverage.

**Finding FT-01 (HIGH / Hardcoded magic numbers with no config knob)**
- File: `fast_track.rs:64, 74, 89, 90`
- Issues:
  - Line 64: `margin_utilization_pct >= 90.0` — Bybit 物理 MMR 常數，**legitimately hardcoded**（已文件化）。
  - Line 74: `held_drop_pct >= 15.0` — 15% 閃崩閾值硬編碼。
  - Line 89: `held_drop_pct >= 5.0 && held_drop_sigma >= 3.0` — 5% drop + 3σ outlier 硬編碼。
  - Line 133-141: `is_drop_scoped_reduce` 同樣 5 / 3σ / 15 硬編碼邊界。
- Severity: **HIGH** — 15% / 5% / 3σ 是風控參數不是物理常數；crypto 市場在 altseason / crash 期 threshold 敏感性很高，operator 無 IPC 或 TOML 調整路徑。
- Suggestion: 加 `struct FastTrackThresholds { extreme_drop_pct: f64, moderate_drop_pct: f64, moderate_drop_sigma: f64 }` 入 `RiskConfig`，evaluate_fast_track 改接收 `&FastTrackThresholds` 第二參數。Defaults 維持現值 bit-identical。

### 2.3 Stop Manager — Hard / Trailing / Time + Take Profit

**File**: `rust/openclaw_core/src/stop_manager.rs`
**Correctness**: ✅ 含鎖損 bug 修補（trailing_activation_pct 默認 = trailing_stop_pct 確保 trail_price ≥ entry）+ priority 順序 TP > Hard > Trail > Time 正確。

**Finding SM-01 (LOW / See RK-01)**
— StopConfig default duplication with RiskConfig already captured.

### 2.4 Physical micro-profit lock v2

**File**: `rust/openclaw_engine/src/exit_features/v2.rs`
**Correctness**: ✅ Gate 語意對齊設計文檔（Gate 1 Hold 非 Lock，只有 Gate 4 是合法 Lock 路徑），non-linear giveback 閾值 `max(base - slope*peak_atr_norm, floor)` monotonic non-increasing 有 unit test 固化。

**Finding V2-01 (NONE)** — 25 個單測覆蓋含 Option=None 保守路徑 + NaN clamp + Gate ordering。

### 2.5 Negative balance Gate 1.6

**File**: `intent_processor/router.rs:58-74`
**Correctness**: ✅ `balance ≤ 0 && no existing position` → reject open；opposite-direction close 允許。邏輯正確。

### 2.6 FA-PHANTOM-1 margin_util 陷阱（歷史 bug）

- 已修復，`margin_utilization_pct` 在 on_tick 計算時 `/ leverage` 轉為 leverage-aware。`fast_track.rs:64` comment 詳細文件化為何 90% 閾值不可參數化為 `leverage_max`-scaled。regression test `test_fa_phantom_1_regression_full_notional_no_action` 證實 20x leverage × 100% notional = 5% margin util 不觸發 CloseAll。
- **NO FINDING**。

### 2.7 Guardian max_daily_drawdown / max_symbol_exposure / sector_cap

**File**: `rust/openclaw_core/src/guardian.rs` + `risk_config.rs::GlobalLimits`.

- `max_drawdown_pct` = `GlobalLimits::session_drawdown_max_pct` (default 15%), Guardian Check 4 正確引用。
- `max_symbol_exposure` 未直接在 Guardian 出現；`anti_cluster::max_same_direction` = Guardian Check 2。
- `sector_cap` / correlation 有 `Correlation { max_pairwise_r, window_minutes }` 但 Guardian 未調用（ARCH-RC1 1C-4 E-Merge-4 `max_correlation` dead field 已刪）— **未實作 sector-cap 語意**。

**Finding GD-01 (LOW / Semantic gap)**
- File: `guardian.rs:110-193`
- Issue: `max_correlation` 已刪但 `Correlation.max_pairwise_r` 仍留在 `RiskConfig`（line 1226-1231），沒有 runtime consumer。與根原則 16「組合級風險意識 — 監控關聯曝險」有 gap。
- Severity: **LOW / Feature gap** — 非 bug，未實作功能。
- Suggestion: 要麼實作（用 `price_tracker` 的 price window 計 realized correlation + veto when > `max_pairwise_r`），要麼從 risk_config 刪 `Correlation` struct + 從 TOML 刪（dead config）。

**Finding GD-02 (MEDIUM / Hardcoded verdict math)**
- File: `guardian.rs:123, 137, 148, 157, 166, 169, 177`
- Issues:
  - Risk score 增量：`direction_conflict +0.4`、`position_count +0.3`、`leverage_excessive +0.4`、`leverage_modified +0.15`、`drawdown +0.35`。
  - Line 142 `leverage_ratio > 2.0` (2x over-cap reject); line 151 `modification_leverage_cap` (config)；line 177 verdict threshold `risk_score >= 0.3`。
- Severity: **MEDIUM** — 這些 weights 是 Guardian 核心裁決邏輯，寫死會讓 operator / agent 無法調整敏感度；`2x cap` 與 `RiskConfig::leverage_max` 的關係沒有 knob。
- Suggestion: 把 weights + `reject_threshold = 0.3` + `reject_at_leverage_ratio = 2.0` 搬入 `GuardianConfig`（或 `RiskConfig.guardian_scoring`），E-Merge-4 同模式 hot-reload.

---

## 3. 硬編碼清單（literal → 建議 config key）

> **重點任務**。按嚴重度排序，已在策略/風控章節點出的不再重複。

### 3.1 HIGH severity（影響 live 風控或 edge）

| # | File:line | Literal | 語意 | 建議 config key |
|---|---|---|---|---|
| H1 | `intent_processor/mod.rs:229-235` | `SLIPPAGE_TIERS = [(1B,1bps),(100M,2bps),(10M,5bps),(1M,15bps),(0,30bps)]` | 成本門核心輸入 | `RiskConfig.cost_gate.slippage_tiers: Vec<(f64, f64)>` + IPC patch |
| H2 | `intent_processor/mod.rs:214, 220, 224` | `DEFAULT_TAKER_FEE_RATE = 0.00055`, `DEFAULT_MAKER_FEE_RATE = 0.0002`, `DEFAULT_SLIPPAGE_RATE = 0.0005` | Fee/slippage fallback | 已有 account_manager per-symbol；但 fallback 值應 `RiskConfig.market_gate.default_*_rate` |
| H3 | `intent_processor/gates.rs:37, 108, 164` | `threshold_bps = fee_bps / wr * 1.3` (30% safety margin) | Cost gate 安全餘量 | `RiskConfig.cost_gate.js_threshold_safety_mult: f64` default 1.3 |
| H4 | `intent_processor/gates.rs:36, 107, 163` | `wr.clamp(0.3, 1.0)` | Win-rate floor avoid division blowup | `RiskConfig.cost_gate.min_win_rate_floor: f64` default 0.3 |
| H5 | `intent_processor/gates.rs:197, 199` | `notional < 50.0` / `< 200.0` | cost_gate_k tier boundaries | `RiskConfig.cost_gate.notional_tier_small_usdt / _medium_usdt` |
| H6 | `fast_track.rs:74, 89` | `held_drop_pct >= 15.0`, `>= 5.0 && sigma >= 3.0` | 閃崩 + outlier 雙條件 | `RiskConfig.fast_track.extreme_drop_pct / moderate_drop_pct / moderate_drop_sigma` |
| H7 | `ml/kelly_sizer.rs:153, 155` | `trades < 50` / `< 200` tiers + divisors `8.0 / 6.0 / 4.0` | Fractional Kelly by sample size | `KellyConfig.fraction_tiers: Vec<(u32, f64)>` (cutoff, divisor) |
| H8 | `guardian.rs:123, 137, 148, 157, 166, 177` | risk_score weights `0.4/0.3/0.4/0.15/0.35`, verdict threshold `0.3` | Guardian 裁決核心 | `GuardianConfig.scoring: GuardianScoringConfig` (5 weights + threshold) |
| H9 | `guardian.rs:142` | `leverage_ratio > 2.0` (2x over-cap reject) | Modified vs Rejected boundary | `GuardianConfig.reject_leverage_ratio: f64` default 2.0 |

### 3.2 MEDIUM severity（策略行為 magic numbers）

| # | File:line | Literal | 語意 | 建議 config key |
|---|---|---|---|---|
| M1 | `strategies/confluence.rs:251, 255` | `1.0 - (adx/50.0)`, `adx/25.0` | ADX component normalisation constants | `ConfluenceConfig.adx_scale_reversion: f64 = 50.0`, `.adx_scale_trend: f64 = 25.0` |
| M2 | `strategies/confluence.rs:268` | `(vr / 1.2).clamp(0.0, 1.0)` | Volume ratio normalisation anchor | `ConfluenceConfig.volume_ratio_anchor: f64 = 1.2` |
| M3 | `strategies/confluence.rs:259-264` | regime_score 硬編碼 `{aligned:1.0, opposed:0.3, uncertain:0.6}` | Regime score mapping | `ConfluenceConfig.regime_score_map: HashMap<str, f64>` |
| M4 | `strategies/confluence.rs:275-279` | RSI bands `55..=80 → 0.9`, `30..=50 → 0.9`, `40..=60 → 0.6` | Momentum scoring | `ConfluenceConfig.rsi_bands: Vec<(f64, f64, f64)>` (lo, hi, score) |
| M5 | `strategies/confluence.rs:303` | `ramp_start = threshold_no_trade - 5.0` | Soft floor 5-point ramp width | `ConfluenceConfig.soft_floor_width: f64 = 5.0` |
| M6 | `strategies/confluence.rs:307-316` | `0.10 / 0.40 / 0.50 / 0.50` qty_pct band endpoints | Band-to-qty mapping | Derive from `threshold_light/full` anchors + a couple of `ConfluenceConfig` knobs |
| M7 | `strategies/funding_arb.rs:452-454` | `edge_bps / 10.0`, `clamp(0.3, 0.9)` | Confidence scaling | `FundingArbUpdateParams.{conf_edge_scale, conf_min, conf_max}` |
| M8 | `strategies/bb_reversion.rs:660` | `(exit_conf_base + hurst_boost).clamp(0.4, 0.8)` | Exit confidence bounds | `BbReversionParams.exit_conf_min / _max` |
| M9 | `tick_pipeline/pipeline_helpers.rs:370` | `compute_roc(symbol, 300)` = 300 ms ROC window | ROC window hardcoded | `ExitConfig.price_roc_window_ms: u64 = 300` |
| M10 | `fast_track.rs:64` | `margin_utilization_pct >= 90.0` | Bybit MMR 物理常數 | **無需參數化** (already documented inline) — 但可改為 named const `BYBIT_MMR_CRISIS_PCT` 明示 |
| M11 | `strategies/grid_trading/mod.rs:78, 93, 96, 104, 111, 128, 133, 138` | `DEFAULT_GRID_COUNT = 10`, `DEFAULT_FEE_PCT = 0.00055`, `ADAPTIVE_RANGE_PCT = 0.10`, `DEFAULT_MAKER_OFFSET_BPS = 1.0`, `DEFAULT_USE_MAKER_ENTRY = false`, `DEFAULT_MAKER_LIMIT_TIMEOUT_MS = 45_000`, `MIN/MAX_MS = 15_000 / 300_000` | Grid 默認值 + clamp bounds | 多數已有 TOML path；`DEFAULT_FEE_PCT` duplicate with `intent_processor`; timeout clamp 建議 config-per-strategy |

### 3.3 LOW severity（defaults / ctor literals, already have config path）

| # | File:line | Literal | 備註 |
|---|---|---|---|
| L1 | `bb_breakout/mod.rs:187` + `params.rs:250` | `squeeze_expiry_ms = 2_700_000` | Duplicate default → extract const |
| L2 | `bb_breakout/mod.rs:188` | `cooldown_ms: 600_000` (10 min) in ctor but `params.rs:244 cooldown_ms = 300_000` (5 min) — **MISMATCH** |
| L3 | `bb_breakout/mod.rs:190` + others | `default_qty: 1e9` sentinel | 已文件化 "IntentProcessor sizing caps to risk budget" |
| L4 | `bb_breakout/mod.rs:195-196` | `entry_conf_base: 0.7`, `exit_conf_base: 0.5` | 有 config field 但 ctor 寫死同值 |
| L5 | `bb_breakout/mod.rs:202` | `min_persistence_ms: 60_000` | params.rs 有同值 default — 一致 |
| L6 | `bb_breakout/mod.rs:206-210` | E5-P2-4 extracted confidence bonuses `{0.1, 0.2, 0.1, 0.05, 0.05}` | 已 config 化；ctor literals 為 Default trait 語義保留 |

**LOW #L2 bb_breakout cooldown_ms mismatch（實質是 BUG candidate）**:
- `BbBreakout::new()` line 188 `TrendCooldown::new(600_000)` + `cooldown_ms: 600_000`
- `BbBreakoutParams::default()` line 244 `cooldown_ms: 300_000`
- 啟動 seed 用 ctor `new()` 600_000，但 hot-reload 經 `update_params` 第一次呼叫時會替換為 300_000。**預設值分歧**（5 vs 10 min）。實測哪個生效取決於 factory 是否跑 `update_params(Default::default())` — 需 operator 驗證。
- **Severity**: LOW（consistency hazard）→ 可能 MEDIUM 如果 cold-boot 無 update_params。

---

## 4. 數學部署可用性（NaN / Inf / div-by-zero）

| 指標/函數 | 守護 | 評估 |
|---|---|---|
| ATR (Wilder) | `last_close > 1e-15` check line 100, period+1 sample | ✅ |
| Bollinger | `mean > 1e-15` line 39, `band_range > 1e-15` line 46 | ✅ |
| MACD | `fast < slow` check, len comparison | ✅ |
| KAMA | `volatility > 1e-15` line 147, `er = 0.0` fallback | ✅ |
| Hurst | empty returns → `H=0.5 random_walk` fallback, `denom.abs() < 1e-15` check, clamp `[0.0, 1.0]` | ✅ |
| Donchian | `n < period` return None | ✅ nature but see BB-01 leak |
| EWMA Vol | `(0.0..1.0).contains(&lambda)`, len>=3 check | ⚠️ **見 BR-01**: no `w[0] > 0` guard → NaN propagate path |
| OU θ | `(-b).max(0.01)` | ✅ |
| Kelly | `avg_loss > 0.0 && win_rate > 0.0` | ✅ reject at 0; negative kelly → return 0.0 (FIX-27 applied) |
| phys_lock v2 | `atr_pct > 0.0 && atr_pct.is_finite()`, `giveback_base > giveback_floor` validate | ✅ |
| non_linear_giveback_fn | NaN/Inf/negative input → clamp 0 → return base | ✅ |
| confluence.compute_score | Option types, cold-start fallback | ✅ |
| JS shrinkage | `p < 3` return raw, `sq_sum < 1e-12` return raw | ✅ |
| funding_arb compute_edge | `expected_periods` validated `[0.5, 30.0]` strictly positive | ✅ |
| compute_basis_pct | `index_price > 0.0` check | ✅ |
| compute_ou_step | `den.abs() < 1e-15`, `step > 0 && mu > 0` | ✅ |

**整體評估**：floating-point safety discipline 非常好。唯一明確 gap 為 EWMA Vol（BR-01），零成本修補。

---

## 5. Leak-free 性專項

（遵循 memory `feedback_indicator_lookahead_bias.md`：`rolling(N).max()` 含 current bar 是 look-ahead bias）

| 檢查點 | 結論 |
|---|---|
| `openclaw_core/src/indicators/trend.rs::donchian` | ❌ 含 current bar（見 BB-01）— **須修** |
| `volatility.rs::bollinger` | ✅ bandwidth `(upper-lower)/mean` 於 current window 計算，語意上「本 bar 的波動 envelope」不是突破判定 — **OK**（不是預測用途）|
| `momentum.rs::rsi` | （未審閱，但公式上 Wilder smooth 只用 past）|
| `trend.rs::macd` | ✅ 純 EMA，自然遞推 |
| `trend.rs::ema` | ✅ 歷史遞推 |
| `trend.rs::sma` | ✅ 歷史窗口均值，無 future peek |
| Hurst R/S | ✅ 滑動 lag windows 全 historical |
| Volume ratio | （未讀，但常見 `current_volume / past_mean_volume` — 語意上 current 可用）|
| ATR (Wilder) | ✅ |
| `strategies/*` on_tick 讀取 indicators | ✅ 除 donchian 外所有指標語意為「截至此 tick 的歷史估計」 |

**唯一 leak 源**：Donchian。CLAUDE.md F3 retract 已記；BB-01 finding 是 runtime 代碼待修（Phase 2 backlog per P1-11）。

---

## 6. 建議修補優先順序（P0 / P1 / P2）

### P0（阻 Live / 阻 Phase 5 edge 評估）
1. **BB-01 Donchian shift(1)**：修 `openclaw_core/src/indicators/trend.rs::donchian` 為 leak-free，bb_breakout Hard mode 的 breach 判定才不會 mechanically always true。
2. **RK-01 StopConfig-RiskConfig drift**：在 StopConfig 加明確 "apply_risk_snapshot 每 tick 覆蓋，ctor default 僅 unit-test 用" 文件化 + 加 debug_assert。

### P1（影響 edge 估計或風控敏感度）
3. **H3 cost_gate safety margin 1.3**：提升 config；當 EDGE-P2-3 PostOnly 降 fee 後 1.3 是否過嚴需驗證。
4. **H6 fast_track thresholds 15% / 5% / 3σ**：需 config 化才能 altseason / crash 兩套閾值切換。
5. **H8 Guardian scoring weights**：把 risk_score 組合提升為 config；`0.3` 裁決閾值尤其敏感。
6. **GT-01 Grid OU σ residual-based**：修為 residual std；加 OU-recovery unit test。

### P2（衛生 / consistency）
7. **H1 SLIPPAGE_TIERS** → config table。
8. **H2 fee rate defaults 集中常數**。
9. **H7 Kelly tier boundaries → KellyConfig**。
10. **M1-M6 confluence magic numbers → ConfluenceConfig**。
11. **L2 bb_breakout cooldown_ms ctor vs params.default 分歧** — 驗證首次啟動 cold-boot 用哪個。
12. **BR-01 EWMA Vol w[0]>0 guard**（零成本）。
13. **GD-01 Correlation dead field** — 實作 or 刪。

---

## 7. 不審計但發現的觀察（non-actionable）

- `tick_pipeline/pipeline_helpers.rs:370` ROC 窗口 `300 ms` 是極短窗口，對於 5 秒以上 tick 間隔會幾乎永遠是相鄰 2 samples — 與 Track P `price_roc_short` 語義「短期 ROC」相符，但若 paper engine tick 頻率稀疏（≤ 0.2 Hz）可能 Some/None 邊界敏感。
- `confluence::compute_score` RSI 預設 `50.0` 用於 missing input — `(40.0..=60.0)` 帶寬內 → `momentum_score = 0.6`，總 score 會固定抬高。對 ma_crossover 這可能掩蓋 cold-start edge。非 bug。
- `exit_features/v2.rs::physical_micro_profit_lock_v2` Gate 2 `entry_age_secs < 30s` 與 Gate 3 `peak_atr_norm < 0.5` 若 atr_pct 極小（<0.1%）peak 門檻實質不可達；P0-13 post-fix atr 回到 ~0.05-0.5% 尺度，Gate 3 健康運作 — 已驗證於 `EDGE-DIAG-1 Phase 2 post-P013 clean window +11.95 bps` 真實 signal。

---

## 8. 指向後續工作的指針

- **P1-11 Phase 2 backlog** 已 priority sorted（CLAUDE.md）— 本 audit 的 BB-01 donchian shift(1) 應納入 Phase 2 第一條（已在該任務審計中點出 F3 retract）。
- **EDGE-DIAG-1 Phase 3** passive_wait check [11] 自動 gate — cost_gate safety margin 重算可借機重評。
- **DYNAMIC-RISK-1**（`dynamic_risk_sizer.rs` 已接線，預設 off）— Sharpe-aware per_trade_risk_pct 啟動前需先把 Guardian scoring 的 `0.35 drawdown weight` 與 `session_drawdown_max_pct` 交互路徑審一次（未在本 scope）。

---

QC AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-24--strategy_risk_math_audit.md
