# QC 策略・風控・數學全面審計報告 — 2026-05-08

## §1 Executive Summary

**判定**：5 策略整體 **REVISE**；目前 demo 7d gross **-26.80 USDT**（PA 直查；CLAUDE.md §三 -6.98 是早期 stale 快照），edge 仍負；4/5 策略無可解釋的結構性 alpha。grid_trading 唯一正收益但依賴單一 ORDIUSDT cell + 多次 blocked_symbol patches，泛化性疑慮高；funding_arb 數學失效已 V2 棄策略路徑（commit `a19797d`）；bb_breakout 1m bandwidth 結構錯配（live_demo 14d 0 fires），demo rescue gate 為實驗性；ma_crossover ATR-SNR 修復後仍 -5.09，R:R 不對稱根本未解。

**關鍵硬編碼**：
- 5 策略 `default_qty = 1e9` sentinel（5 處 hardcoded，僅靠 IntentProcessor sizing 補救）
- `cooldown_ms` 多處 `Default::default()` 與 ctor 分歧（`bb_breakout/mod.rs:193` ctor=600_000 vs default 300_000）
- funding_arb 6 個 `DEFAULT_*` 在 `funding_arb.rs:27-33` module-level const
- `fast_track.rs:64,74,89` 90/15/5%+3σ 閾值寫死（90% MMR 是物理常數可接受；15%/5%/3σ 是策略風控應 config）

**Walk-forward 真實接線狀態**：
- `edge_estimate_validation.py` 有 `_walk_forward_oos_values` rolling 90/30，PSR + Bonferroni m_tests 完整實作
- DSR (`learning_engine/dsr_gate.py`) + PBO (`pbo_gate.py`) + CPCV (`cpcv_validator.py`) **全部已落地**為純數學 module
- **gap**：DSR/PBO/CPCV 至今未在 production 路徑上強制 fire（為 REF-20 P4 advisory layer 提供 verdict，**未阻擋 production strategy promotion**）

**主要建議**：
1. ma_crossover R:R 不對稱（avg_win=1.2 vs avg_loss=4.7）= 結構性問題；單獨 ATR-SNR 修不了，**必須上 trailing stop 動態 R:R 調整 + Kelly fractional 強制 ≥ 200 trades**
2. bb_breakout 1m timeframe 應 RFC 升 5m
3. funding_arb 應 RETIRE，不留 dormant slot
4. grid_trading PostOnly 已開但 maker fill rate 36.6% < 60% baseline → missed-trade opportunity cost > rebate edge
5. **新增 cell-level cost_gate** + **將 DSR/PBO 設為 promotion 必要條件**

---

## §2 5 策略逐條 review

### §2.1 grid_trading — 7d demo +4.98 USDT（唯一 net positive）

**Alpha 來源**：類別 6（短期均回 + ranging regime gating）；OU model + Hurst regime filter。

**數學基礎**（`grid_helpers.rs:90-164`）：
- `step = max(σ·√(2/θ), 2·fee_rate·μ·multiplier, mu·min_grid_step_bps/1e4)`
- OU 估計 `Δx_t = a + b·x_{t-1} + ε_t`，OLS 求 b；b≥0 fallback 到 ±10% adaptive
- σ 計算 `sqrt(Σ Δx²/n)` — **biased high**（殘差未扣 drift）；G7-06 Phase A 已落 `OuResidualSigma` 估計器但 Phase B wire 未完成

**Leakage**：✅ 低 — OU 估計用 lag-1，無未來資訊穿透

**負 edge RCA**：
- 單一 ORDIUSDT cell 主導；其他 25 symbols 多數 blocked
- maker fill rate 36.6% < 60% baseline → PostOnly + missed trade 對沖 fee rebate
- `min_grid_step_bps = 22.0` 對 ORDIUSDT 適配但 illiquid altcoin 失靈

**判定**：CONDITIONAL；唯一正 edge cell 不代表策略普適；建議降到單 symbol（ORDIUSDT only）並做 OOS 21d 驗證

### §2.2 ma_crossover — 7d demo -5.09 USDT（ATR-SNR 修復後仍負）

**Alpha 來源**：類別 1（行為偏差，趨勢追隨）。Crypto 1m 趨勢 alpha < 1 day，OpenClaw 1m sampling 落在邊界。

**數學基礎**（`ma_crossover/strategy_impl.rs`）：KAMA(fast) vs SMA-20(slow) 交叉 + ADX ≥ 25 + Hurst regime + persistence 4min + trend-adaptive cooldown + min_trend_snr=0.75 + 4-feature confluence

**Leakage**：⚠️ KAMA 退化 fallback 到 SMA-20（QC-#2 文件化）

**負 edge RCA**：
- R:R 不對稱：`avg_win = 1.2 bps` vs `avg_loss = 4.7 bps`，ratio R = 0.255
- Kelly formula `f* = W − (1−W)/R = 0.64 − 0.36/0.255 = -0.77` — **負 Kelly**
- Kelly sizer 對負 Kelly 已 reject，但實際走的是 risk_pct 0.03 fallback（`stats.total_trades < min_trades = 50`）
- ATR-SNR 修了什麼？只 filter 弱信號，不修 R:R 不對稱

**判定**：REVISE；R:R 結構性問題，必須調 take_profit (0.5×ATR → 2× ATR) + 拉長 trailing distance；同步把 `min_trades` 從 50 → 200

### §2.3 funding_arb — 7d demo -5.96 USDT（V2 棄策略 commit a19797d）

**OpenClaw 數學失效根因**：
1. **Bybit demo 不支援 spot lending** → 無法做純 short spot leg → 所謂 delta-neutral 其實是裸 perp
2. `total_cost_bps = 34.0` 包含 spot 20 bps；現況無 spot leg → 真實 cost ≈ 14 bps，但仍 amortized 34
3. `expected_periods = 3.0`（24h carry）硬編，極端 funding spike 下 1 period exit 即虧
4. Entry edge 公式 → 要 funding > 11.3 bps，Bybit BTC 永續 funding 幾乎不到此值
5. `funding_threshold = 0.0005`（5 bps）< amortized cost 0.001133 → entry threshold 達標仍 negative edge → bug

**判定**：REJECT — V2 棄策略決策正確；不留 dormant slot

### §2.4 bb_breakout — 7d demo -0.75 USDT（live_demo 14d 0 fires）

**Alpha 來源**：類別 1（行為偏差，volatility regime 切換捕捉）。

**數學基礎**：5-AND 鏈：squeeze (BW < squeeze_bw) → expansion (BW > expansion_bw) → volume (vol_ratio > 1.2) → Donchian breach → confluence ≥ threshold_full

**Leakage**：🔴 **HIGH** — Donchian `&high[n-period..n]` 含 current bar，rolling-max 含當前值必 mean-revert

**負 edge RCA**：
- 1m bandwidth 結構錯配：default `squeeze_bw = 0.03`、`expansion_bw = 0.04` 在 1m timeframe 結構性不可達
- Demo rescue gate (EDGE-DIAG-2C) Sweep 結果僅 +5.33 bps fwd30 raw signal-level（**不可 promote**）
- 1m sampling rate vs breakout half-life ~1-3 min 不匹配

**判定**：REJECT 1m → REVISE 5m RFC

### §2.5 bb_reversion — 7d demo -0.16 USDT（live_demo dormant）

**Alpha 來源**：類別 6（短期均回 + RSI 確認）

**負 edge RCA**：
- 樣本量極低（n=7）— 統計上無意義
- RSI 30/70 是技術指標 default，無 crypto-specific 校驗
- mean-revert in trending crypto = 系統性虧損

**判定**：REVISE — 建議與 ma_crossover 配對作 long/short pair（同 symbol 趨勢 vs 回歸對沖），單獨運行無 alpha

---

## §3 風控邏輯 review

### §3.1 三層 P0/P1/P2 架構

| 層 | 真實接線 | 對應代碼 |
|---|---|---|
| P0 hard limit | RiskConfig `[limits]` SSOT | `rust/openclaw_engine/src/config/risk_config.rs` |
| P1 governance | Guardian 動態收縮 + SM-04 6-state | `openclaw_core/src/sm/risk_gov.rs` |
| P2 adaptive | per_strategy override + Agent 自主 | TOML `[per_strategy]` |

Guardian modification ✅ 已 config 化；SM-04 cascade 閾值已配置 driven；6 state position_size_multiplier (1.0/0.7/0.5/0.0/0.0/0.0) — 是 SM-04 spec 級不變硬編碼，非錯誤

### §3.2 Position sizing（per_trade_risk_pct + Kelly）

**真實 SSOT**：
- `risk_config.toml [limits].per_trade_risk_pct = 0.1`（base, 0.1%）
- `risk_config_demo.toml = 0.1`
- `risk_config_live.toml = 0.05`
- KellyConfig `risk_pct = 0.03`（**3%**，非 config！）

**Conflict**：
- `kelly_sizer.rs:109` `risk_pct: 0.03` hardcoded default — 與 RiskConfig 的 `per_trade_risk_pct` 不同源
- Memory `feedback_position_sizing.md` 記載「3% risk/trade」（operator 設計意圖）
- 兩個值 30× 差異，會直接決定每筆 risk 是 0.05% 或 3%

**push back operator**：哪個值真正生效？

### §3.3 Kelly fractional 4 層

**4 層真實接線**（`kelly_sizer.rs:198-204`）：
```
trades < 50  → kelly_full / 8.0   (1/8 Kelly)
trades < 200 → kelly_full / 6.0   (1/6 Kelly)
trades >= 200 → kelly_full / 4.0   (1/4 Kelly)
max_fraction = 0.25 (cap)
```

✅ G7-01 已 config 化 young_threshold/mature_threshold
**剩餘 hardcoded**：分母 `8/6/4` 三個 magic number 寫死（不在 config）

### §3.4 StopManager Hard / Trailing / Time + ATR Wilder

ATR：Kahan summation + Wilder's smoothing 已驗證正確

Trailing stop：`trailing_activation_pct = 0.8` + `trailing_distance_pct = 3.5`，沒有違反成本陷阱

Time stop：168h (demo) / 72h (live) — 治理級

Hard stop：25% (demo) / 15% (live) + dynamic_stop.base_ratio=0.25 (2026-05-02 BUSDT incident 後從 0.4 收緊)

### §3.5 對抗性止損 + Kelly fractional 真實使用

`fast_track.rs` 90/15/5%+3σ ladder + `risk_gov.rs` 6-state + `protective_order_manager` 雙重交易所側 stop

Kelly 真實 fire ✅；但 `total_trades >= min_trades = 50`，許多 cell n < 50 走 fallback `risk_pct` 路徑

---

## §4 數學部署 inventory

| 部件 | 部署狀態 |
|---|---|
| ATR Wilder smoothing | ✅ Production |
| Bollinger Band | ✅ Production |
| KAMA + SMA crossover | ✅ Production |
| Hurst exponent | ⚠️ Schema only |
| OU mean-reversion fit | ✅ Production；σ residual 估計器 dormant |
| EWMA volatility | ✅ Production |
| ADX | ✅ Production |
| Kelly fractional | ✅ Production |
| **VaR (parametric)** | ❌ **無 production VaR 計算** |
| **CVaR / Expected Shortfall** | ❌ **無** |
| **EVT / GPD tail fit** | ❌ **無** |
| Sharpe (single) | ⚠️ 有計算但無年化 |
| **PSR** | ✅ advisory 層 |
| **DSR** | ✅ REF-20 P4 advisory |
| **PBO** | ✅ advisory |
| **CSCV / CPCV** | ✅ 4-fold + per-strategy embargo |
| **Bonferroni** | ✅ Wired |
| **Walk-forward (rolling 90/30)** | ✅ 真接 |
| **Stress test (LUNA / FTX scenarios)** | ❌ 無 |
| **Block bootstrap CI** | ❌ 無 |
| **Plateau heatmap** | ❌ 無 |

**最大 gap**：**VaR/CVaR/EVT 全部缺**。OpenClaw 有 SM-04 drawdown ladder 但無 prob-based tail risk 量化。LUNA-FTX cascade 場景 0 stress test。

---

## §5 硬編碼清單

### Severity 1（HIGH — 核心策略邏輯應 config，當前寫死）

| # | File:Line | 當前值 | 是否合理 | 建議去處 |
|---|---|---|---|---|
| 1 | `kelly_sizer.rs:198-204` | 分母 `8/6/4` | **❌ 不合理** | `RiskConfig.kelly.young_fraction/mature_fraction/established_fraction` |
| 2 | `kelly_sizer.rs:107-117` | `vol_mult_floor = 0.5`、`vol_mult_ceil = 1.5`、`reference_atr_pct = 0.02` | ⚠️ KellyConfig 但 hardcode default | TOML `[kelly]` |
| 3 | `fast_track.rs:74` | `held_drop_pct >= 15.0` | ❌ 應 config | `RiskConfig.fast_track.flash_crash_drop_pct` |
| 4 | `fast_track.rs:89` | `held_drop_pct >= 5.0 && held_drop_sigma >= 3.0` | ❌ 應 config | `RiskConfig.fast_track.moderate_drop_pct` + `moderate_sigma_z` |
| 5 | `funding_arb.rs:27-33` | 6 個 module-level const | ⚠️ default fallback | RiskConfig.funding_arb（如未來 redesign）|
| 6 | `bb_breakout/params.rs:17-21` | 3 個 DEFAULT 值 | ⚠️ TOML 可 override | OK |
| 7 | `grid_trading/mod.rs:81,93,96,104` | `DEFAULT_QTY_PER_GRID=1e9` sentinel、fee_pct、`ADAPTIVE_RANGE_PCT=0.10`、`MAKER_OFFSET=1.0` | ⚠️ fee_pct 應從 RiskConfig 讀 | RiskConfig.execution.taker_fee_rate |
| 8 | `grid_trading/mod.rs:128-138` | `MAKER_LIMIT_TIMEOUT_MS=45_000` | OK | OK |
| 9 | `bb_breakout/mod.rs:191,193` | `cooldown = 600_000`（ctor）vs default 300_000 | 🔴 BUG candidate | params.default 與 ctor 統一 |

### Severity 2（MEDIUM）

| # | File:Line | 當前值 | 建議去處 |
|---|---|---|---|
| 10 | `bb_breakout/mod.rs:199-200` | `entry_conf_base = 0.7`、`exit_conf_base = 0.5` | TOML |
| 11 | `bb_breakout/params.rs:227,243` | Conservative/Aggressive profile magic number | OK |
| 12 | `funding_arb.rs:34-35` | maker buffer/timeout | RiskConfig.execution |
| 13 | `risk_config.toml:148-149` | `cost_gate_win_rate_floor = 0.3` | ✅ 已 config |
| 14 | `risk_gov.rs:158-204` | 6 state position_size_multiplier | OK — SM-04 spec 不變 |
| 15 | `risk_gov.rs:233-247` | EscalationThresholds default 5/8/12/15% | ✅ 已 config |

### Severity 3（LOW — 治理常量，可不改）

16-20: `fast_track.rs:64` 90% MMR 物理常數 / `bb_breakout/params.rs:530` oi_confluence_bonus cap / `dsr_gate.py` 學術常數 / `cpcv_validator.py:54-61` embargo_map / `edge_estimate_validation.py:23-33` ValidationConfig defaults

---

## §6 Walk-forward / IS-OOS / PSR / PBO / CSCV 真實接線

| 部件 | 接線狀態 | 證據 |
|---|---|---|
| **Walk-forward rolling 90/30** | ✅ Production | `_walk_forward_oos_values` |
| **PurgedKFold** | ✅ Implemented | `cpcv_validator.py` 4-fold |
| **Embargo (per-strategy)** | ✅ Implemented | `CPCVConfig.embargo_map` |
| **PSR** | ✅ Implemented | normal-CDF approx；dsr_gate 完整 |
| **DSR** | ✅ Implemented | `compute_dsr()` Bailey-LopezDePrado 完整 |
| **Bonferroni** | ✅ Implemented | `p_bonf = min(1.0, p_raw * max(m_tests, 1))` |
| **PBO** | ✅ Implemented | `learning_engine/pbo_gate.py` |
| **CSCV / CPCV** | ✅ Implemented | `cpcv_validator.py` |
| **block bootstrap CI** | ❌ 無 | — |
| **Plateau heatmap** | ❌ 無 | — |

**Gap 1（致命）**：DSR/PBO/CPCV 全是 **REF-20 P4 advisory layer**，未進 production strategy promotion blocker。當前 5 策略 promotion 完全靠 operator 手動評估 + edge_estimator JS shrinkage 的 cost_gate。

**Gap 2**：no block bootstrap → max_DD CI 不存在。

**Gap 3**：no plateau analysis → BB sweep 只跑 fwd30 mean，無 cliff/plateau heatmap。

---

## §7 funding_arb 數學失敗 RCA

**operator 棄策略決策（commit a19797d）QC 數學上完全支持**。

### 7.1 Delta-neutral 數學前提不成立

Bybit demo（v5）:
- ✅ Spot trading 支援
- ❌ Spot lending / margin borrow 不支援（demo 限制）
- ❌ 無法做空 spot 來 hedge perp long

實際在 Bybit demo 上跑 funding_arb，等於 **裸 perp 持倉**，完全暴露於 BTC 波動。

### 7.2 Cost 模型錯誤

`total_cost_bps = 34.0` 包含 `spot 20 bps`：假設有 spot leg 才合理；現況無 spot leg → 真實 cost ≈ 14 bps；但代碼仍 amortized 34 bps → entry threshold 過高 → 0 fires

### 7.3 樣本量不可信

n=99 fills (demo only)，G-2 v2 結案 n=13；99 fills 中 0 wins → win_rate=0 → fallback risk_pct 0.03，cost 仍 amortize → 累積虧損

### 7.4 max_basis_pct 邏輯死循環

demo 無 spot leg → basis 永遠是 perp price - index_price 的 noise，spread 經常 < 0.1%

### 7.5 結論

operator 決策正確：**RETIRE not REVISE**。建議：
1. 從 active config（已做）
2. RiskConfig schema 完全移除 `[per_strategy.funding_arb]` 段
3. 若未來想做 funding arb，必須是 mainnet（有 spot lending）+ 跨 perp/perp 同 symbol funding spread
4. 不留 dormant slot

---

## §8 Replication crisis check

### 8.1 5 策略對照 anomaly graveyard

| 策略 | 學術根源 | Replication 狀態 |
|---|---|---|
| MA crossover | Lo, Mamaysky, Wang (2000) | ⚠️ Decayed alpha |
| BB Reversion | Bollinger 1992 + Lo, MacKinlay 1990 | ⚠️ McLean-Pontiff decay 50% |
| BB Breakout | Donchian 1948 | ⚠️ rolling-max look-ahead bias 標準陷阱 |
| FundingArb | Cash-and-carry literature | ✅ 結構性 alpha 但 Bybit demo 不適用 |
| Grid Trading | OU mean-revert + market-making | ⚠️ ranging regime dependent |

### 8.2 Walk-forward 真實驗證狀態

| 策略 | walk-forward 跑過？ | OOS gross > 0？ | DSR > 0.95？ | PBO < 0.5？ |
|---|---|---|---|---|
| grid_trading | 部分 | ⚠️ 部分 cell 正 | 未驗 | 未驗 |
| ma_crossover | 部分 | ❌ -5.09 | 未驗 | 未驗 |
| funding_arb | n=99 不夠 | ❌ -5.96 | N/A | N/A |
| bb_breakout | EDGE-DIAG-2C sweep | ❌ +5.33 raw | 未驗 | 未驗 |
| bb_reversion | n=7 太少 | N/A | N/A | N/A |

**結論**：5 策略**沒一個**經過完整 walk-forward + DSR + PBO 驗證並通過。

### 8.3 Data snooping bias

- BB sweep 跑了多參數組，未 Bonferroni 修正提報 best fwd30
- Grid blocked_symbols 多次 patch（demo 16 / live 16）— 樣本選擇偏差「事後刪除虧損 symbol 留下盈利 symbol」

**建議**：blocked_symbols list 必須 freeze + 在新 symbol 上做 OOS 驗證

---

## §9 Top 20 量化問題

| # | 嚴重度 | 問題 | 修復路徑 |
|---|---|---|---|
| 1 | 🔴 P0 | DSR/PBO/CPCV 為 advisory，未強制 promotion gate | 寫入 promotion blocker（REF-20 P5 LG-2 IMPL）|
| 2 | 🔴 P0 | per_trade_risk_pct 雙 SSOT (RiskConfig 0.1 vs Kelly 0.03) | 統一 |
| 3 | 🔴 P0 | bb_breakout 1m timeframe + Donchian look-ahead bias | 升 5m + Donchian shift(1) |
| 4 | 🔴 P0 | funding_arb dormant slot 未完全移除 | RiskConfig schema 完全清除 |
| 5 | 🟠 P1 | grid_trading OU σ 估計 biased high | G7-06 Phase B wire `OuResidualSigma` |
| 6 | 🟠 P1 | bb_breakout `Default::default cooldown_ms` (300k) ≠ ctor (600k) | 統一 |
| 7 | 🟠 P1 | Kelly tier 分母 8/6/4 寫死 | RiskConfig.kelly.{young/mature/established}_fraction |
| 8 | 🟠 P1 | fast_track 15%/5%+3σ 寫死 | RiskConfig.fast_track |
| 9 | 🟠 P1 | grid blocked_symbols selection bias | Freeze list + OOS 新 symbol 驗 |
| 10 | 🟠 P1 | ma_crossover R:R 結構不對稱 | trailing 動態 + take_profit 拉長 |
| 11 | 🟠 P1 | 無 production VaR/CVaR/EVT | 加 portfolio-construction-protocol §4 |
| 12 | 🟡 P2 | Walk-forward 沒 block bootstrap CI | 加 Politis-Romano block bootstrap |
| 13 | 🟡 P2 | 沒 plateau heatmap | sweep 結果加 plateau 分析 |
| 14 | 🟡 P2 | min_trades = 50 太低（operator 意圖 200）| `KellyConfig.min_trades = 200` |
| 15 | 🟡 P2 | bb_reversion 無 alpha + 無 demo 樣本 | RETIRE 或配 ma_crossover pair trade |
| 16 | 🟡 P2 | 沒 stress test (LUNA/FTX) | 加 portfolio §4.5 5 場景 |
| 17 | 🟡 P2 | Effective N (25 symbol PCA) 未實證 | PCA on 25 symbol returns |
| 18 | 🟡 P2 | edge_estimator grand_mean n=1 仍報數 | n_cells < 3 設 NaN |
| 19 | 🟢 P3 | OI signal 預設未過濾 noise | 預設 0.001 |
| 20 | 🟢 P3 | `cost_floor_multiplier` demo/live 不對稱 | 三 env 統一邏輯 |

---

## §10 QC Verdict

### 10.1 5 策略各自能否撐到 supervised live

| 策略 | Verdict | Supervised Live 條件 |
|---|---|---|
| **grid_trading** | ⚠️ CONDITIONAL | 限 ORDIUSDT only + 7d gross > 0 + DSR > 0.95 + PBO < 0.5 |
| **ma_crossover** | ❌ REJECT 當前形態 | R:R 不對稱必修；trailing/TP 重寫；min_trades = 200 + DSR/PBO 驗 |
| **funding_arb** | ❌ RETIRE | Bybit demo 數學不成立；不留 dormant |
| **bb_breakout** | ❌ REJECT 1m | 必須升 5m + Donchian shift(1) 修補 |
| **bb_reversion** | ❌ REJECT 單獨運行 | 配 ma_crossover 做 pair trade，或 RETIRE |

### 10.2 新策略 RFC 建議

按 alpha 來源類別優先級：
1. **類別 2（結構性）**：跨期貨基差套利（Bybit BTC perp vs quarterly futures）
2. **類別 3（流動性提供）**：純 PostOnly market making 在 spot pair
3. **類別 6（短期均回）pair trading**：BTC/ETH cointegration pair

**禁止**（黑名單）：HMM regime / GARCH / VPIN / 純 vol mean-revert / 獨立 Donchian breakout

### 10.3 整體 portfolio 建議

- **5 策略 → 收斂到 1-2 策略**
- **DSR/PBO 強制 promotion gate**
- **per_trade_risk_pct 雙 SSOT 統一** — 0.1% (RiskConfig) 才是真值
- **cell-level cost_gate**
- **stop loss + trailing 重寫對 ma_crossover R:R 結構問題**
- **新增 portfolio level VaR/CVaR backtesting**

---

**QC AUDIT DONE** · severity tally：HIGH 9 / MEDIUM 6 / LOW 5；20 量化問題（4 P0 / 7 P1 / 7 P2 / 2 P3）；5 策略 verdict：1 CONDITIONAL (grid) / 4 REJECT
