# QC 審計報告：策略算法 / 風控邏輯 / 數學正確性
# QC Audit Report: Strategy Algorithms / Risk Control Logic / Math Correctness

**審計日期 / Audit Date**: 2026-04-12
**審計範圍 / Scope**: 5 策略 + IntentProcessor 治理管線 + Guardian + Kelly + 風控檢查 + 16 指標 + 成本門
**審計結論 / Conclusion**: 數學公式整體正確，架構設計嚴謹。原發現 **3 個 P1** + **7 個 P2** + **12 個 [HARDCODED]** — **全部已修復（Session 3.3 + 3.3b, 2026-04-12）**。

---

## 一、策略算法審計 / Strategy Algorithm Audit

### 1.1 MaCrossover (`ma_crossover.rs`)

**信號邏輯 / Signal Logic:**
- 快線 = KAMA（自適應），慢線 = SMA(20)。KAMA 缺失時 fallback 到 SMA(20)，此時 fast == slow，永不交叉。 **[正確，fail-safe]**
- ADX < threshold 時跳過，防止在盤整市場假信號。 **[正確]**
- RC-01 Hurst regime filter：僅 `trending` 允許入場，`mean_reverting` / `random_walk` 阻擋。**出場不受此過濾影響。** **[正確，防止在不利 regime 開倉]**
- RC-02 Higher-TF confirmation：用 SMA(50) 的 EMA（alpha=0.003）模擬 4h 趨勢。做多需 bullish，做空需 bearish。**出場不受此過濾影響。** **[正確]**

**Confidence 計算:**
- `compute_entry_confidence`: base=0.45, adx_bonus up to +0.25, regime_bonus +/-0.15, clamp [0.2, 0.9]。 **[合理]**
- `compute_exit_confidence`: base=0.5, adx_bonus up to +0.2, clamp [0.4, 0.8]。 **[合理]**

**問題與發現:**

1. **[HARDCODED] 入場 confidence 參數**: `base=0.45`, `adx_bonus_divisor=100`, `regime_bonus=0.15`, exit `base=0.5`。這些值無法從 TOML 配置，需依賴硬編碼重編譯。**建議：加入 StrategyParams 或至少作為 const。**

2. **[P2] KAMA fallback 靜默退化**: 當 `kama` 為 None 時 fallback 到 `sma_20`，導致 `fast == slow == sma_20`，策略靜默失活而非報錯。建議加 `tracing::debug` 記錄此降級。

3. **[HARDCODED] higher_tf EMA alpha=0.003**: 已在 `MaCrossoverParams` 中可配置（agent_adjustable=true），**此項合規。**

---

### 1.2 BbReversion (`bb_reversion.rs`)

**信號邏輯 / Signal Logic:**
- 入場：`percent_b < 0.0 && RSI < 30.0`（超賣做多）或 `percent_b > 1.0 && RSI > 70.0`（超買做空）。**[正確，雙確認防假信號]**
- 出場：`percent_b in [0.2, 0.8]`（均值回歸目標達成）。**[正確，比精確 0.5 更寬容，適合加密貨幣超調]**
- Hurst regime boost：`mean_reverting` regime 時入場 confidence +0.1。**[正確，均值回歸 regime 提升均值回歸策略信心]**

**問題與發現:**

4. **[HARDCODED] RSI 閾值 30/70**: RSI 超賣/超買閾值硬編碼在 `on_tick` 邏輯中。加密貨幣市場 RSI 動態範圍與傳統市場不同，應可配置。**建議：加入 BbReversionParams（`rsi_oversold`, `rsi_overbought`）。**

5. **[HARDCODED] 出場 %B 區間 [0.2, 0.8]**: 均值回歸目標區間硬編碼。不同市場狀態下最佳出場帶可能不同。**建議：可配置化。**

6. **[HARDCODED] 入場 confidence base=0.6, 出場 base=0.55**: 與 MaCrossover 同類問題，confidence 參數硬編碼。

7. **[HARDCODED] Hurst boost=0.1**: 相同問題。

---

### 1.3 BbBreakout (`bb_breakout.rs`)

**信號邏輯 / Signal Logic:**
- 入場條件：(1) 先檢測 squeeze（`bandwidth < squeeze_bw`），(2) 然後等 expansion（`bandwidth > expansion_bw`），(3) volume_ratio 確認，(4) Donchian 通道突破確認，(5) %B 方向判斷。**[正確，5 重過濾嚴謹]**
- 出場邏輯優先級：ATR trailing stop > Hurst regime shift > %B revert > BW squeeze。**[正確，trailing stop 最高優先]**
- Trailing stop: Chandelier exit，`price - ATR * mult` for long，`price + ATR * mult` for short。止損只單向移動（ratchet）。**[正確]**

**問題與發現:**

8. **[P2] squeeze 狀態未加冷卻/過期**: `was_in_squeeze` 一旦設為 true，永不過期。如果 squeeze 發生在很久以前，expansion 仍可觸發入場。這可能導致在非壓縮擴張場景中的虛假突破。**建議：加 squeeze 過期時間（如 squeeze_max_age_ms）。**

9. **[HARDCODED] 入場 confidence base=0.7, trailing_stop exit=0.7, regime_shift exit=0.6, pctb_revert exit=0.55, bw_squeeze exit=0.45**: 所有 confidence 值硬編碼。

---

### 1.4 GridTrading (`grid_trading.rs`)

**核心邏輯 / Core Logic:**
- 線性 / 幾何兩種網格構建模式。**[數學正確]**
  - 線性：`level[i] = lower + (upper-lower)/(n-1) * i`
  - 幾何：`level[i] = lower * (upper/lower)^(i/(n-1))`
- OU 模型動態間距：σ·sqrt(2/θ)，帶費用地板 `2 * FEE_PCT * mu`。**[數學正確]**
- 自適應範圍：首次 tick ±10% 初始化，之後 OU 模型調整。**[合理]**
- 庫存追蹤 + 健康檢查 + 再平衡機制。**[正確]**

**問題與發現:**

10. **[P1] OU 回歸估計可能為正**: `b = num/den` 的 `theta = (-b).max(0.001)`。如果 OLS 斜率 `b > 0`（非均值回歸序列），theta 被 clamp 到 0.001，產生極大的 `ou_step = sigma * sqrt(2000)`。這可能導致網格間距過寬，完全失去交易能力。**建議：當 b > 0 時返回 None（序列不適合 OU 模型），回退到 ±10% adaptive。**

11. **[HARDCODED] `DEFAULT_GRID_COUNT = 10`**: 雖在 `GridTradingParams` 中有 `grid_levels` 欄位，但 `on_tick` 和 `rebalance` 中使用的是 `DEFAULT_GRID_COUNT` 常量，**TOML 配置的 grid_levels 被存儲但從未應用**。這是 dead param（違反根原則：可調參數禁止假功能）。

12. **[HARDCODED] `FEE_PCT = 0.00055`**: 單邊 taker fee 硬編碼。IntentProcessor 中有動態 `fee_rate()` 查詢，但 GridTrading 的 OU 費用地板使用此硬編碼值。**建議：從 IntentProcessor 或策略參數傳入。**

13. **[HARDCODED] `ADAPTIVE_RANGE_PCT = 0.10` (±10%)**: 自適應範圍固定。

14. **[HARDCODED] `REJECT_BACKOFF_MS = 30_000` (30s)**: 拒絕退避時間固定。

15. **[P2] OU 更新頻率硬編碼 `hist_len % 50 == 0`**: 每 50 個 tick 更新一次 OU 間距，不可配置。

---

### 1.5 FundingArb (`funding_arb.rs`)

**狀態**: 完全 stub，`on_tick()` 返回 `vec![]`。待 OC-5 REST 接線。

**已實現的邏輯審計（dead code）:**
- `compute_edge`: `funding_rate.abs() - amortized_fee`，其中 `amortized_fee = TOTAL_COST_BPS / 10_000 / expected_periods`。**[數學正確]**
- `should_exit`: 4 退出條件（費率翻轉 / 費率太小 / 基差風險 / 最大持倉時間）。**[邏輯正確]**

**問題與發現:**

16. **[HARDCODED] `TOTAL_COST_BPS = 34`, `FUNDING_THRESHOLD = 0.0005`, `MAX_BASIS_PCT = 0.5`, `MAX_HOLD_MS = 72h`**: 全部硬編碼。作為 stub 可接受，上線前必須參數化。

17. **[P2] FundingArb 不是 multi-symbol**: 使用 `position: Option<FundingPosition>` 而非 `HashMap<String, FundingPosition>`。上線前需改為 per-symbol tracking（與其他 4 策略對齊）。

---

## 二、風控邏輯審計 / Risk Control Logic Audit

### 2.1 Guardian 4-Check (`guardian.rs`)

**4 項檢查 / 4 Checks:**
1. Direction conflict（同 symbol 反向持倉）→ risk_score +0.4 → Reject
2. Same-direction position count ≥ `max_same_direction_positions`（默認 3）→ risk_score +0.3 → Reject
3. Leverage cap → >2x 上限 Reject，>1x 但 <2x → Modified（qty×0.5, leverage→2x）
4. Drawdown breach → risk_score +0.35 → Reject

**裁決邏輯**: `risk_score >= 0.3 && 存在 reject-class reason` → Rejected；有修改 → Modified；其餘 → Approved。

**問題與發現:**

18. **[正確] fail-closed 設計**: 所有檢查項累積風險分數，任何嚴重問題直接拒絕。
19. **[正確] Guardian 僅用於 Open 路徑**: `StrategyAction::Close` 繞過 Guardian，因為平倉降低風險。
20. **[RISK-GAP] 修改邏輯不影響 direction_conflict 和 position_count**: 這些始終 Reject。但 leverage_over_cap 的修改（qty×0.5）可能在 Guardian 後被 Kelly/P1 進一步裁剪，邏輯正確。

### 2.2 IntentProcessor 治理管線 (`router.rs`)

**Gate 順序 / Gate Order:**
1. Governance authorization（是否授權）
1.5. Duplicate position check（同方向已有倉位）
2. Guardian 4-check
2.5. Kelly position sizing
2.6. P1 hard cap（2% of balance）
2.7. Order admission risk check（日損/槓桿/持倉/曝險/相關曝險）
   - BLOCKER-3 D15: Global notional cap check
3. Cost gate（confidence + ATR + JS edge estimate）
4. Execute fill（paper）/ Return approved qty（exchange）

**問題與發現:**

21. **[正確] P1 cap 在 Kelly 之後**: `final_qty = kelly_qty.min(p1_max_qty)`，P1 是不可突破的硬上限。
22. **[正確] PNL-1 qty=0 guard**: 防止幽靈倉位。
23. **[正確] SEC-11 ATR=0 fail-closed**: ATR 不可用時拒絕，防止在沒有波動率數據時開倉。

24. **[P1] `correlated_exposure_pct` 永遠傳入 0.0**: 代碼註釋 "Phase C wiring"，但 `check_order_allowed` 的 `correlated_exposure_pct` 始終為 0.0。RiskConfig 的 `correlated_exposure_max_pct`（默認 50%）永遠不會觸發。**這是組合級風險意識的缺口（根原則 #16）。**

25. **[P2] `leverage` 永遠傳入 1.0**: paper/exchange 模式均固定 1.0。Exchange 模式應讀取 Bybit 實際槓桿。

### 2.3 Order Admission Risk Check (`risk_checks.rs`)

**check_order_allowed 5 項檢查:**
1. Daily loss ≥ `daily_loss_max_pct` → reject
2. Leverage > `leverage_max` → reject
3. Single position ≥ `position_size_max_pct` → reject
4. Total exposure ≥ `total_exposure_max_pct` → reject
5. Correlated exposure ≥ `correlated_exposure_max_pct` → reject

**reducing orders 永遠通過**（原則 #5）。**[正確]**

### 2.4 Tick-Level Position Risk Check (`risk_checks.rs`)

**check_position_on_tick 9 層優先級:**
1. Hard stop: `pnl_pct <= -stop_loss_max_pct` → Close
2. Dynamic stop: `compute_dynamic_stop_pct(base, atr, regime, ...)` → Close
3. Take profit（if enforced）: `pnl >= tp_target * regime_mult` → Close
4. Trailing stop: peak-based，需 `min_locked_profit`（R:R floor）→ Close
5. Time stop: `holding_hours >= max * regime_mult` → Close
6. Cost edge ratio: `cost_ratio >= 0.8 && pnl > 0` → Close（suggest）
7. Session drawdown: → Halt
8. Consecutive losses: → Cooldown
9. Daily loss: → Halt

**問題與發現:**

26. **[正確] 優先級正確**: Hard stop > Dynamic stop > TP > Trailing > Time > Cost Edge > Session DD > Consec > Daily。嚴重問題優先處理。
27. **[正確] Trailing stop 有 R:R floor**: `pnl >= min_locked_profit` 才觸發，防止在接近成本時被 trailing 平倉。
28. **[正確] Cost edge ratio 只在盈利時觸發**: `pnl > 0.0` 條件，避免在虧損時因成本比高而強制平倉。

### 2.5 Cost Gate (`gates.rs`)

**三層模式 / Three Profiles:**
- **Paper (Exploration)**: 正 JS 估計 → 檢查門檻；負 JS 估計 → exploration 放行；冷啟動 → exploration 放行
- **Demo (Validation)**: 正 → 檢查門檻；負 → **阻擋**；冷啟動 → 放行（警告）
- **Live (Production)**: 正 → 檢查門檻；負 → **fail-closed**；冷啟動 → **fail-closed**

**門檻公式**: `threshold_bps = fee_bps / max(0.3, win_rate) * 1.3`（30% 安全邊際）
**fee_bps** = `2 * (fee_rate + slippage) * 10_000`（來回成本）

**問題與發現:**

29. **[正確] Live fail-closed**: 無正 JS 估計時拒絕，符合原則 #5（生存 > 利潤）。
30. **[正確] Paper exploration mode**: 允許累積數據以建立估計，避免死循環。
31. **[MATH] 門檻公式合理性**: `fee/wr * 1.3` — 勝率越低門檻越高，要求更大 edge。win_rate clamp 到 [0.3, 1.0]，防止除以接近 0 的值。**[正確]**

### 2.6 Reconciler Escalation/De-escalation

**已在 Phase 6 審計完成 (6-RC-1~10)，此處不重複。確認 27 tests pass。**

---

## 三、數學正確性審計 / Mathematical Correctness Audit

### 3.1 指標計算 / Indicator Computations

| 指標 | 公式 | Kahan 補償 | 驗證結果 |
|------|------|-----------|---------|
| SMA | `sum(window) / period` | **是** | **[正確]** |
| EMA | `price * k + prev * (1-k)`, k = 2/(period+1), seed = SMA(first period) | **是 (seed)** | **[正確]** |
| RSI (Wilder) | `100 - 100/(1+RS)`, RS = avg_gain/avg_loss, Wilder smoothing | **是 (initial)** | **[正確]** |
| Bollinger | mean ± std_mult * stddev(population), %B = (last-lower)/(upper-lower) | **是** | **[正確]** — 使用 population stddev（/N 而非 /N-1），與 TradingView 20-period 一致 |
| ATR (Wilder) | TR series → Kahan initial → Wilder smooth | **是** | **[正確]** |
| MACD | fast_ema - slow_ema, signal = EMA(macd_line, signal_period) | **是** | **[正確]** |
| KAMA | ER = |direction|/volatility, SC = ER*(fast_alpha-slow_alpha)+slow_alpha, kama += SC^2 * (price - kama) | **是** | **[正確]** |
| ADX (Wilder) | +DM/-DM → Wilder smooth → +DI/-DI → DX → Wilder smooth ADX | **是** | **[正確]** |
| Hurst (R/S) | Log-log OLS regression of R/S vs lag, clamp [0, 1] | **是** | **[正確]** |
| EWMA Vol | variance = lambda*prev + (1-lambda)*r^2, ewma = sqrt(variance) | 否（遞推） | **[正確]** — 遞推結構不需要 Kahan |
| Stochastic | %K = (close-lowest)/(highest-lowest)*100, %D = SMA(%K) | **是 (%D)** | **[正確]** |
| Donchian | max(high[window]), min(low[window]) | 否（min/max） | **[正確]** |
| Volume Ratio | current_vol / sma(volume, period) | **是** | **[正確]** |

**[MATH] Bollinger population vs sample stddev**: 使用 population stddev（除以 N 而非 N-1）。技術分析慣例上 Bollinger Bands 使用 population stddev，與 TradingView 一致。**合規。**

### 3.2 Kelly Criterion (`kelly_sizer.rs`)

**公式**: `f* = W - (1-W)/R`，其中 W = win_rate, R = avg_win/avg_loss。**[標準 Kelly 公式，正確]**

**分數 Kelly**:
- < 50 trades: 1/8 Kelly
- < 200 trades: 1/6 Kelly
- >= 200 trades: 1/4 Kelly
- cap at `max_fraction` (default 0.25)

**ATR 波動率調整**: `vol_multiplier = reference_atr_pct / atr_pct`, clamp [0.5, 1.5]。高波動縮量，低波動擴量。**[正確]**

**問題與發現:**

32. **[MATH] 正確**: Kelly 公式無誤。分數 Kelly 極度保守（最大 1/4），防止 overbetting。
33. **[P2] 負 Kelly 仍開倉 1%**: `kelly_full <= 0` 時仍以 `balance * 0.01 / price` 開倉。在 Phase 5 暫停（所有策略 gross 負 edge）的背景下，這導致每次 Kelly 判斷邊際為負時仍開 1% 倉位。**建議：Phase 5 重啟時，負 Kelly 應返回 0 或極小值（如 0.1%）。**

### 3.3 OU 最佳網格間距 (`grid_trading.rs`)

**公式**: `ou_step = sigma * sqrt(2/theta)`，其中：
- theta 由 OLS 回歸 dx_t = a + b*x_{t-1} 的斜率 b 取 `-b`
- sigma = RMS(changes)
- 費用地板 = `2 * FEE_PCT * mu`

**[MATH] 公式正確**（源自 OU 首次穿越時間理論）。但見 #10：當 b > 0 時（非均值回歸序列），theta 被 clamp 到 0.001，產生巨大間距。

### 3.4 PnL 計算

**PNL-FIX-1/2 已修復（2026-04-12）**：
- FIX-1: 5 條 close 路徑從 `event.last_price` 改為 per-symbol 正確價格
- FIX-2: `emit_close_fill` 寫入真實費用而非 0.0

**[正確] 當前 PnL 計算使用 `execute_market_fill_with_rate()` 包含真實費率和滑點。**

### 3.5 Position Sizing

**P1 cap 公式**: `p1_max_qty = balance * p1_risk_pct / price`。默認 `p1_risk_pct = 0.02`（2%）。**[正確]**

**Exposure 計算**: `exposure_pct = sum(position_qty * price) / balance * 100`。**[正確]**

### 3.6 Slippage Tiers

| 24h 成交額 | 滑點 |
|-----------|------|
| >$1B | 1 bps |
| >$100M | 2 bps |
| >$10M | 5 bps |
| >$1M | 15 bps |
| <$1M | 30 bps |

**[合理]** — 分層符合加密貨幣流動性梯度。BTC/ETH 在 1B+ 層，altcoin 在低層。

### 3.7 James-Stein Estimator (`edge_estimates.rs`)

此文件僅是緩存/查詢層，真正的 JS 估計在 Python `james_stein_estimator.py` 中計算。Rust 側正確加載 `shrunk_bps`, `win_rate`, `n_trades`, `std_bps` 並提供 O(1) 查詢。**[正確]**

---

## 四、硬編碼值彙總 / Hardcoded Values Summary

| # | 位置 | 值 | 嚴重性 | 狀態 | 修復方式 |
|---|------|-----|--------|------|----------|
| H1 | `ma_crossover.rs` | confidence base=0.45, regime_bonus=0.15 | P3 | ✅ S3.3 | 3 struct fields + TOML |
| H2 | `bb_reversion.rs` | RSI thresholds 30/70 | **P2** | ✅ FIX-24 | `rsi_oversold`/`rsi_overbought` + param_ranges + validate |
| H3 | `bb_reversion.rs` | Exit %B range [0.2, 0.8] + confidence | P3 | ✅ S3.3 | 4 struct fields + TOML |
| H4 | `bb_breakout.rs` | Entry/exit confidence | P3 | ✅ S3.3 | 2 struct fields + TOML |
| H5 | `grid_trading.rs` | DEFAULT_GRID_COUNT=10 | **P1** | ✅ S3.3b | `gt.grid_count = p.grid_trading.grid_levels` factory 接線 |
| H6 | `grid_trading.rs` | FEE_PCT=0.00055 | **P2** | ✅ FIX-25 | `fee_rate` struct field + `set_fee_rate()` 動態注入 |
| H7 | `grid_trading.rs` | ADAPTIVE_RANGE_PCT=0.10 | P3 | ✅ S3.3 | struct field + TOML |
| H8 | `grid_trading.rs` | REJECT_BACKOFF_MS=30_000 | P3 | ✅ S3.3 | struct field + TOML |
| H9 | `grid_trading.rs` | OU update frequency (% 50) | P3 | ✅ S3.3 | `ou_update_interval` struct field + TOML |
| H10 | `funding_arb.rs` | All 5 constants | P3 | ✅ S3.3b | 5 struct fields + FundingArbParams TOML |
| H11 | `intent_processor/mod.rs` | DEFAULT_P1_RISK_PCT=0.02 | P3 | ✅ 已解決 | struct field + setter + TOML `per_trade_risk_pct` |
| H12 | `volatility.rs` | HURST thresholds 0.60/0.40 | P3 | ✅ S3.3 | 函數參數注入 + 公開默認常量 |

---

## 五、風控 Gap 彙總 / Risk Gaps Summary

| # | 類型 | 描述 | 嚴重性 | 狀態 | 修復方式 |
|---|------|------|--------|------|----------|
| RG-1 | [RISK-GAP] | `correlated_exposure_pct` 永遠 0.0 | **P1** | ✅ FIX-05 | `compute_correlated_exposure_pct()` 實算 |
| RG-2 | [RISK-GAP] | leverage 永遠 1.0 | P2 | ✅ S3.3b | `compute_leverage(paper_state)` 動態計算 |
| RG-3 | [RISK-GAP] | GridTrading `grid_levels` dead param | **P1** | ✅ S3.3b | factory 接線 `gt.grid_count = p.grid_trading.grid_levels` |
| RG-4 | [RISK-GAP] | OU theta clamp 0.001 → 巨大間距 | **P1** | ✅ FIX-07 | `b >= 0 → return None` |
| RG-5 | [RISK-GAP] | FEE_PCT 硬編碼 vs 動態費率不一致 | P2 | ✅ FIX-25 | `fee_rate` struct field + setter |
| RG-6 | [RISK-GAP] | BbBreakout squeeze 永不過期 | P2 | ✅ FIX-26 | `squeeze_expiry_ms` + timestamp tracking |
| RG-7 | [RISK-GAP] | Kelly 負邊際仍開 1% 倉 | P2 | ✅ FIX-27 | `return 0.0` 拒絕開倉 |

---

## 六、正面發現 / Positive Findings

1. **Kahan 補償求和全面覆蓋**: 所有指標累加運算使用 Kahan，消除浮點漂移。
2. **RC-04 rejection rollback 一致實現**: 5 策略全部實現 per-symbol 狀態快照+回滾。
3. **StrategyAction::Close 繞過治理**: 平倉不需 Guardian/cost_gate/Kelly/P1，正確反映降風險本質。
4. **P1 hard cap 不可繞過**: `kelly_qty.min(p1_max_qty)` 確保 Kelly 不能超過風控上限。
5. **cost_gate 三級分層**: Paper/Demo/Live 逐級嚴格，符合漸進放權設計。
6. **ATR=0 fail-closed (SEC-11)**: 指標故障時自動阻止開倉。
7. **PNL-1 qty=0 guard**: 防止幽靈倉位。
8. **reducing orders 永遠通過**: 符合原則 #5（生存 > 利潤），不阻擋平倉/減倉。
9. **Trailing stop R:R floor**: 防止在接近成本時被追蹤止損意外平倉。
10. **Per-engine TOML 策略配置**: 三引擎可獨立配置策略參數。

---

## 七、建議行動項 / Recommended Actions

### P0（無）

### P1（3 項）— ✅ 全部完成
1. ~~**RG-1**: 接線 `correlated_exposure_pct`~~ → FIX-05 `compute_correlated_exposure_pct()`
2. ~~**RG-3**: 將 `GridTradingParams.grid_levels` 接線到 `build_levels()`~~ → S3.3b factory 接線
3. ~~**RG-4**: 當 OU 回歸斜率 b > 0 時 `compute_ou_step()` 返回 None~~ → FIX-07

### P2（7 項）— ✅ 全部完成
4. ~~H2: RSI 閾值加入 BbReversionParams~~ → FIX-24 完整 param_ranges
5. ~~H6: GridTrading FEE_PCT 改為動態讀取~~ → FIX-25 `set_fee_rate()`
6. ~~RG-2: leverage 永遠 1.0~~ → S3.3b `compute_leverage(paper_state)`
7. ~~RG-6: 加 squeeze 過期時間配置~~ → FIX-26 `squeeze_expiry_ms`
8. ~~RG-7: 負 Kelly 時返回 0~~ → FIX-27 `return 0.0`
9. ~~FundingArb multi-symbol 改造~~ → S3.3b `HashMap<String, FundingPosition>`
10. ~~KAMA fallback 加 trace log~~ → S3.3b `tracing::debug!`

### P3 ��編碼（12 項）— ✅ 全部完成
- H1/H3/H4/H7/H8/H9/H12: S3.3 struct fields + TOML
- H10: S3.3b FundingArb 5 struct fields + TOML
- H6/H11: 已解決確認
- H5: S3.3b factory 接線
- #7: S3.3b `hurst_regime_boost` field

---

**審計員 / Auditor**: QC (Quality Controller)
**審計級別 / Level**: L2 全模組審計
**測試基線 / Test Baseline**: 939 engine lib + 366 core + 18 e2e + 32 promotion = 1355 Rust / 2852 Python
**修復驗證 / Fix Verification**: 934 engine lib + 366 core = 1300 passed, 0 failed（S3.3b 修復後）
**修復完成日期 / Fix Completion**: 2026-04-12 Session 3.3 + 3.3b
