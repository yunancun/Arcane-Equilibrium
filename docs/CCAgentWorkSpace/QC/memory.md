# QC — Quantitative Consultant 工作記憶

> 初始化日期：2026-04-02
> 本文件隨每次任務完成後更新，記錄關鍵發現、決策依據、需記住的教訓。

---

## 當前系統策略狀態（首次評估前快照）

### 已實現策略（5 個）
| 策略 | 類型 | 數學基礎 | QC 初步印象 |
|------|------|---------|------------|
| MA_Crossover | 趨勢跟蹤 | EMA(12)×EMA(26) + MACD | 標準技術指標，無獨特 edge |
| BB_Reversion | 均值回歸 | %B < 0.1 + RSI 超賣 | 有回歸邏輯但缺乏統計檢驗（half-life？協整？） |
| BB_Breakout | 突破 | 布林帶擠壓→擴張 | 波動率 regime 切換信號，需驗證假突破率 |
| FundingRateArb | 套利 | 永續-現貨基差 | 結構性 edge 最清晰，但需精算成本 |
| GridTrading | 網格 | 等距掛單 | 本質是做空波動率，趨勢市場風險極大 |

### FA 審計已指出的關鍵問題
- 「策略层标准 RSI/MACD/MA，无可证明的 alpha」
- 策略選擇完成度僅 40%
- 無 AI、無回測驗證、無動態倉位（部分已改善）

### 系統基礎設施（與 QC 相關）
- **BacktestEngine**：已建好（純函數指標 + KlineAdapter），但缺乏 walk-forward 和過擬合檢測
- **EvolutionEngine**：網格搜索（max 50 組合），無貝葉斯優化
- **TruthSourceRegistry**：AI confidence 上限 0.85，TTL by source
- **RiskManager**：P0/P1/P2 三層規則型，無統計風控（VaR/CVaR）
- **H0 Gate**：<1ms 確定性門控（freshness/health/eligibility/risk/cooldown）

### 風控參數
- risk_per_trade_pct = 3%（每筆最大虧損佔總額）
- max_symbols = 25（最多同時部署 25 個幣種）
- max_single_position_pct = 15%
- max_leverage: linear=10.0, spot=1.0, inverse=50.0

---

## 待辦評估清單（尚未執行，按優先級排序）

1. **[ ] 五策略 Edge 審計** — 逐一評估每個策略是否存在可論證的 alpha
2. **[ ] FundingRateArb 精算** — 這是最可能有結構性 edge 的策略，需要精確成本建模
3. **[ ] 回測方法論設計** — 為 BacktestEngine 補充 walk-forward + 過擬合檢測框架
4. **[ ] 組合風險模型提案** — 從規則型 → 統計型風控的路線圖
5. **[ ] 新策略方向研究** — 基於 crypto 市場結構性特徵的 alpha 來源識別

---

## 關鍵教訓（任務完成後追加）

### 2026-04-24：策略・風控・數學全面 audit
- **ATR P0-13 修復確認有效**：`atr(high, low, close, 14)` 用 Kahan summation + Wilder's smoothing 實作正確，且 `tick_pipeline/pipeline_helpers.rs::build_exit_feature_row` + `step_6_risk_checks.rs` 都已從 `kline_manager.get_ohlcv("1m", 20)` + `atr(_, _, _, 14)` 取 atr_pct（~0.05-0.5% scale），舊 per-tick `compute_atr_pct` deprecated。phys_lock Gate 3 peak/ATR 閾值在新 scale 下健康運作。
- **Donchian leak-free bias 還沒修 runtime**：CLAUDE.md F3 retract 已記述 measurement bias 在 leak-free `shift(1)` 下消失，但 `openclaw_core/src/indicators/trend.rs::donchian` 視窗 `&high[n-period..n]` 仍含 current bar，`bb_breakout/mod.rs:532` Hard mode 仍做 current-bar-inclusive breach 判定。P1-11 Phase 2 backlog 需修 `&high[n-period-1..n-1]`（或加 shift 參數）。
- **v2 `physical_micro_profit_lock_v2` 25 測試 + 設計文檔對齊**：Gate 1 Hold（非 Lock）、Non-linear giveback fn NaN/Inf 輸入 clamp 到 0、volatility normalisation 經 peak_atr_norm 雙路驗證。設計 + 實作雙重嚴謹，無 finding。
- **Kelly tier 邊界 50 / 200 trades 寫死不在 config**：`ml/kelly_sizer.rs:153-159` 分母 `8/6/4` 全 hardcoded；operator 前置 memory「200+ 筆同 regime」意圖 — 要 regime shift 重置 sample timer 沒 knob。
- **Guardian 裁決數學全硬編碼**：`risk_score` 增量 `0.4/0.3/0.4/0.15/0.35` + verdict threshold `0.3` + `leverage_ratio > 2.0` 寫死；與 E-Merge-4「GuardianConfig = RiskConfig 派生視圖」精神對立，operator 無 IPC/TOML 調裁決敏感度路徑。
- **grid_trading OU σ 估計有偏**：`grid_helpers.rs:128 sigma = sqrt(Σ Δx²/n)` 是 raw second moment，非 residual std；weak drift 期 mean_dx≠0 會高估 σ → ou_step 偏大。對 `b >= 0` fallback 路徑無影響（擋趨勢期），但 ranging 期 σ 高估導致 levels 過鬆、fewer fills。
- **cost_gate safety margin 30%（`fee_bps/wr*1.3`）寫死**：三個 cost_gate 變體（paper/moderate/live）都用同一 literal `1.3`，EDGE-P2-3 PostOnly 降 fee 後此 margin 是否過嚴需重驗。
- **SLIPPAGE_TIERS 整張表 const**：`intent_processor/mod.rs:229-235` 五層硬編碼，IPC 不可改；altseason vs bear 流動性差異需 config table。
- **FastTrack 閾值 15% / 5% / 3σ 寫死，僅 90% margin 合法寫死（Bybit MMR 物理常數）**：fast_track.rs:64 comment 正確文件化為何 90% 不可 auto-scale；但 74/89 的 15% 閃崩 + 5%+3σ 是風控參數不是物理常數，應 config 化。
- **Bb_breakout ctor vs params.default `cooldown_ms` 分歧（600_000 vs 300_000）**：潛在 BUG candidate —— 取決於 factory 是否在 cold-boot 跑 `update_params(Default::default())`，現場生效值需驗證。
- **ewma_vol `(w[1]/w[0]).ln()` 無 w[0]>0 guard**：與 hurst() 的 filter 不一致，零成本修補。

### 2026-04-20：EDGE-P2-3 Phase 1B — maker timeout & paper fill sim
- **Timeout 應 < cooldown，不是 ≥ cooldown。** grid entry 信號 half-life = 秒級（瞬時價格穿越，非 regime 信號）。timeout 1.5× 的提議錯在方向：舊未成交單會與下一個 cooldown 週期的新 tick 評估重疊，造成 stale order 與 fresh intent 雙重 exposure。正確 = 0.5–0.75× cooldown。
- **Timeout 要 scale with A3 effective cooldown，不是 base。** 趨勢越強 → maker 單在 1 bps offset 上越難 fill（單邊行情很少回探），同比例拉長 timeout 給 resting order 一個 fill 窗口才合理。推薦公式 `min(0.75 × effective_cooldown, 300_000)`。
- **Maker passive order = 賣出一個看跌期權。** 思考 timeout 不該問「信號還有效嗎」（45s 後幾乎都無效了），要問「order 還在 book 上提供選擇性嗎」。附帶指標 `(fill × rebate) - (cancel × adverse_move × size)` 為負 → timeout 太長或 offset 太窄。
- **Paper Limit fill 必須 touch-based，不是 optimistic。** optimistic fill 高估 edge 5-8 bps/RT（maker rebate 全吃 + 零 adverse selection），會再次污染 edge_estimates，重演 `project_edge_data_isolation.md` 的墮落循環。
- **Paper→demo 一致性必須 day-1 catch 4 項 bias：** (i) queue position 折扣（tick == limit 僅 50% fill，tick 真實穿越 100% fill）；(ii) partial fill 不模擬但 schema 預留 `filled_qty`；(iii) funding 跨越結算邊界即使未 fill 也要計 funding drag（grid 大量 resting 放大此 bias）；(iv) 記 adverse selection marker `mid@submit` vs `mid@fill`。
- **Paper fill_rate / demo fill_rate 比例 >1.3 或 <0.7 → paper 微結構偏離真實**，禁止餵 edge_estimates（原則重申）。

### 2026-04-02：自適應參數審查
- **20 筆交易的統計量什麼都說明不了。** 任何基於歷史交易的參數優化需要 200+ 筆同 regime 數據。Deflated Sharpe 修正後觀察到的 SR 要扣掉 ~0.9。
- **MA Crossover 的 Kelly fraction 為負 (f* = -0.014)。** 數學上建議不交易。根本問題不在參數，在策略本身無 edge。
- **確定性適應 vs 統計適應是完全不同的東西。** 前者（ATR 縮放、成本門檻）可以立即做；後者（歷史表現 → 參數調整）需要極其謹慎，數據不足時必須禁用。
- **追蹤止損存在成本陷阱：** 若 trail_activation - trail_distance < round_trip_cost，追蹤止損鎖定的利潤 < 手續費，實質上每次觸發都虧錢。必須加約束。
- **FundingRateArb 是 5 個策略中唯一有結構性 edge 的。** 應優先精算其成本模型。

---

## 報告索引

| 日期 | 報告 | 結論 |
|------|------|------|
| 2026-04-02 | [自適應參數架構審查](workspace/reports/2026-04-02--adaptive_params_architecture_review.md) | PROCEED WITH REVISIONS — 確定性適應立即做，統計適應暫緩，核心問題是策略無 edge |
| 2026-04-03 | [外部改善報告數學驗證](workspace/reports/2026-04-03--improvement_report_math_validation.md) | 6/6 兼容，0 衝突，3 採用 / 2 疊加 / 1 暫緩 |
| 2026-04-20 | [EDGE-P2-3 Phase 1B timeout & paper sim](workspace/reports/2026-04-20--edge_p2_3_phase1b_timeout_and_paper_sim.md) | timeout = 0.75× effective_cooldown (base 45s / cap 300s)；paper = (a) touch-based + 4 項 bias 保護 |
| 2026-04-24 | [策略・風控・數學全面 audit](workspace/reports/2026-04-24--strategy_risk_math_audit.md) | 16 findings（1 HIGH leak-free donchian, 5 HIGH 硬編碼 fast_track/guardian/cost_gate/slippage/kelly, 11 MEDIUM/LOW），P0 修補 = donchian shift(1) + StopConfig-RiskConfig drift 文件化；P1 = cost_gate 1.3 safety margin / fast_track thresholds / Guardian scoring weights config 化 / Grid OU σ residual-based |
