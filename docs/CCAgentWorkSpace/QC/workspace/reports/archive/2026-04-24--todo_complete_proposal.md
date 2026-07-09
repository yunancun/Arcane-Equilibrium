# QC 量化 TODO 完整提案
# OpenClaw 2026-04-24 五層量化問題清算 + 30-60 條提案

> **QC（Quantitative Consultant）**  
> 日期：2026-04-24 → 完成於 2026-04-24 14:30  
> 報告：OpenClaw 策略・風控・統計五層量化診斷與 TODO 提案  
> 涵蓋：5 份歷史報告盤點 + 當前 TODO.md 對比 + 未入 TODO 的活躍量化項 + 完整提案清單

---

## A. QC 歷史 5 份報告盤點

### 1. 2026-04-02 自適應參數架構審查（Adaptive Params Architecture）

**報告重點**（440 行）：
- **策略 edge 根本診斷**：MA Crossover 70% 勝率卻 Kelly f* = −0.014，數學上建議「不交易此策略」
- **確定性 vs 統計適應分界**：ATR 止損縮放可立即做；歷史參數優化必須 200+ 筆同 regime（當時僅 20 筆 ❌）
- **費用模型精確化**：「2× 手續費」magic number → `c_round_pct / estimated_win_rate × 1.3` 安全邊際公式
- **FundingRateArb 優先級**：5 策略中唯一有結構性 edge，應精算成本模型而非優化 MA Crossover

**仍活躍量化項**：
- ATR 倍數 {止損 1.5×, 追蹤 1.2× } walk-forward 驗證（未執行）
- Regime 參數映射表（trending/volatile/ranging/squeeze）設計與驗證
- 成本感知入場門檻公式實裝與 binding

---

### 2. 2026-04-03 外部改善報告數學驗證（Improvement Report Math Validation）

**報告重點**（233 行）：
- **Kelly 1/8→1/4 分級方案採納**：生存偏差修正＆小樣本阻塞設計清晰
- **OU Grid 間距公式修正**：`σ/√θ` → `σ/√(2θ)`（報告中有誤，已勘正）
- **EWMA Vol Estimator 整合**：`hist_decay 0.999→0.995` 半衰期 11.5h→2.3h
- **Hurst + Hysteresis 架構**：R/S 分析 + 6 週期滯後 + 凍結修正（vs 衰減）
- **CUSUM 策略衰減監控**：slack 與 threshold 需 σ 倍數校準（非絕對值）

**仍活躍量化項**：
- Kelly 分級 tier boundaries（50/200 trades）config 化
- EWMA 多參數 (lambda=0.90/0.94/0.97，hist_decay=0.995) 硬編碼移至 TOML
- Hurst 計算閾值 0.40/0.60 + required_consecutive 按時間框架分級
- CUSUM slack/threshold 從絕對值轉 σ 倍數

---

### 3. 2026-04-20 Maker Timeout & Paper Fill 模擬（EDGE-P2-3 Phase 1B）

**報告重點**（48 行）：
- **maker_limit_timeout_ms = 0.75 × effective_cooldown_ms**（base 45s，cap 300s）
- **Paper limit fill 4 項 bias 保護**：
  1. Queue position 折扣（touch = 50% fill, cross = 100%）
  2. Partial fill schema 預留
  3. Funding boundary drag 計算
  4. Adverse selection marker 記錄

**仍活躍量化項**：
- Paper→demo fill_rate 比例監控（>1.3 或 <0.7 = paper 偏離警告）
- Timeout 趨勢傾向縮放（A3 effective_cooldown 動態）實裝與驗證

---

### 4. 2026-04-24 策略・風控・數學全面審計（Strategy Risk Math Audit）

**報告重點**（372 行）：
- **16 Findings**：1 HIGH leak-free donchian, 5 HIGH 硬編碼(fast_track/guardian/kelly/slippage/cost_gate), 11 MEDIUM/LOW
- **Donchian leak 偏差**：含 current bar → shift(1) 排除 → P1-11 Phase 2 backlog
- **Grid OU σ 有偏**：raw 2nd moment vs residual std → stepping 偏大 → fills 過鬆
- **8 項硬編碼清單**：SLIPPAGE_TIERS / cost_gate 1.3 safety / fast_track 15%/5%/3σ / Guardian weights 0.4/0.3/0.4/0.15/0.35 / Kelly 50/200 dividers / confluence ADX 50/25 / grid DEFAULT_FEE / bb_breakout cooldown 600K vs params 300K

**仍活躍量化項**：
- P0: BB-01 Donchian shift(1) 修復 + runtime 部署驗證
- P1: H3 cost_gate 1.3 config 化 + H6 fast_track thresholds / H8 Guardian scoring + GT-01 Grid OU σ residual-based
- P2: SLIPPAGE_TIERS / Kelly tier boundaries / confluence magic numbers / br-01 EWMA w[0]>0 guard

---

### 5. 2026-04-24 TODO.md 量化審計（Edge 危機診斷 + 統計方法驗證）

**報告重點**（435 行）：
- **三層負 edge 根因**：(1) Fee drag 60-70% (2) R:R 不對稱 20-30% (3) Alpha 缺失 10%
- **edge_estimates.json 陳舊 4 天**：n_cells=1（vs TODO 聲稱 162），grand_mean=-45.73 無統計意義（n<3 時 JS 未定義）
- **統計方法評分 8/10**：James-Stein 正確、t-test ddof=1、leak-free shift(1) 驗證、但樣本量 8.9/cell <<< 30 基準
- **被動等待 threshold**：edge_estimate bind 須 grand_mean > -50 bps ∧ ≥2 策略 shrunk>0 尚未滿足

**仍活躍量化項**：
- grand_mean <3 cells 時應設 NaN + _meta.is_valid=false（防止污染 JSON）
- edge_estimate 樣本層 threshold 從「無」→ n≥30/cell binding（當前 8.9/cell 噪音主導）
- PostOnly fee 改革驗證（預期 5.5→2 bps 降 60%）
- ma_crossover R:R 數據驗證（平均贏 1.2 bps vs 平均虧 4.7 bps 的合理性）

---

## B. 未入當前 TODO 的活躍量化項

> 來源：5 份報告中明確指出但當前 TODO.md 未提及的量化工作

### 1. Kelly 參數化 TODO

| 項 | 來源報告 | 描述 | 活躍度 |
|---|---|---|---|
| KellyConfig.fraction_tiers → Vec<(u32, f64)> | 2026-04-03 + 2026-04-24 audit | Kelly 1/8→1/4 tier hardcoded @153-159 ml/kelly_sizer.rs，需 TOML | **HIGH** |
| Kelly modified leverage cap (2.0x) → config | 2026-04-24 audit H9 | guardian.rs:142 `leverage_ratio > 2.0` hardcoded | **HIGH** |
| Kelly生存偏差修正 current_run_time語義 | 2026-04-03 S.1 | `total_observation_time` vs `current_tick_run_time` | **MEDIUM** |

### 2. 波動率估計 TODO

| 項 | 來源 | 描述 | 活躍度 |
|---|---|---|---|
| EWMA Vol lambda 參數化 | 2026-04-03 | 1m=0.90, 1h=0.94, 1d=0.97 + hist_decay=0.995 | **HIGH** |
| ATR 快/慢雙窗口 walk-forward | 2026-04-02 S1 | max(ATR_5, ATR_14) 倍數 {1.0, 1.5, 2.0, 2.5, 3.0} plateau 驗證 | **MEDIUM** |
| EWMA w[0]>0 guard | 2026-04-24 BR-01 | volatility.rs:278 ln(w[1]/w[0]) 無 guard → NaN 路徑 | **LOW** |

### 3. Regime 檢測 TODO

| 項 | 來源 | 描述 | 活躍度 |
|---|---|---|---|
| Hurst + Hysteresis 整合 | 2026-04-03 | R/S 分析 + 6 週期滯後 + 凍結修正（vs 衰減）| **HIGH** |
| Hurst required_consecutive 按時間框架分級 | 2026-04-03 M3 | 1h→4, 4h→3, 1d→3（vs 統一 6） | **MEDIUM** |
| Hurst 與 RegimeDetectorRule 交叉驗證 | 2026-04-03 | regime_from_indicators == TRENDING ∧ hurst==mean_reverting → confidence ×0.5 | **MEDIUM** |

### 4. 策略衰減監控 TODO

| 項 | 來源 | 描述 | 活躍度 |
|---|---|---|---|
| CUSUM StrategyHealthMonitor 實裝 | 2026-04-03 S4 | slack/threshold 從絕對 → σ 倍數（0.5σ/5σ）| **HIGH** |
| CUSUM 硬兜底 tier 動態 | 2026-04-03 | 連續虧損門檻 = max(10, ceil(3/ln(1/(1-wr))))（非固定 15） | **MEDIUM** |

### 5. Grid OU 間距 TODO

| 項 | 來源 | 描述 | 活躍度 |
|---|---|---|---|
| Grid OU σ residual-based | 2026-04-24 GT-01 | `σ = sqrt(Σ(Δx-mean_dx)²/n)` 而非 raw 2nd moment | **MEDIUM** |
| OU Grid 間距公式修正 | 2026-04-03 | `σ/√(2θ) + 2×fee_pct`（報告誤寫 σ/√θ） | **MEDIUM** |

### 6. Maker Timeout & Paper Fill TODO

| 項 | 來源 | 描述 | 活躍度 |
|---|---|---|---|
| paper→demo fill_rate ratio 監控 | 2026-04-20 | >1.3 或 <0.7 → 警告（當前未監控） | **MEDIUM** |
| Timeout 趨勢傾向縮放 A3 實裝 | 2026-04-20 Q1 | effective_cooldown 動態 vs base 45s | **MEDIUM** |

### 7. 硬編碼清單（未合入 TODO 的） — 2026-04-24 audit §3

#### HIGH 優先（影響 live 風控或 edge）

| # | 文件:行 | Literal | 建議 config | 狀態 |
|---|---|---|---|---|
| H1 | `intent_processor/mod.rs:229-235` | SLIPPAGE_TIERS 整張表 const | RiskConfig.cost_gate.slippage_tiers + IPC | 未入 TODO |
| H2 | 各處 | DEFAULT_TAKER/MAKER/SLIPPAGE_RATE | market_gate.default_*_rate + fallback | 未入 TODO |
| H3 | intent_processor/gates.rs | 1.3 safety margin | cost_gate.js_threshold_safety_mult | 已在 TODO §G1-04 |
| H4 | intent_processor/gates.rs | wr.clamp(0.3, 1.0) | cost_gate.min_win_rate_floor | 未入 TODO |
| H5 | intent_processor/gates.rs | notional <50 / <200 tier | cost_gate.notional_tier_* | 未入 TODO |
| H6 | fast_track.rs | 15% / 5% / 3σ | fast_track.{extreme/moderate}* | 已在 TODO §G2 |
| H7 | ml/kelly_sizer.rs | 50/200 tier + divisors | KellyConfig.fraction_tiers | 未入 TODO |
| H8 | guardian.rs | weights 0.4/0.3/0.4/0.15/0.35 + 0.3 threshold | GuardianConfig.scoring | 未入 TODO |
| H9 | guardian.rs | leverage_ratio > 2.0 | GuardianConfig.reject_leverage_ratio | 未入 TODO |

#### MEDIUM 優先（策略行為 magic numbers）

| # | 文件 | Literal | 建議 | 狀態 |
|---|---|---|---|---|
| M1-M6 | confluence.rs | ADX 50/25 · volume 1.2 · RSI bands · ramp 5.0 | ConfluenceConfig | 未入 |
| M7 | funding_arb.rs | edge_bps/10.0 · clamp(0.3, 0.9) | FundingArbConfig | 未入 |
| M8 | bb_reversion.rs | exit_conf clamp(0.4, 0.8) | BbReversionParams | 未入 |
| M9 | exit_features/v2.rs | ROC 300ms window | ExitConfig.price_roc_window_ms | 未入 |
| M10 | bb_breakout/mod.rs | cooldown 600K (ctor) vs 300K (params) | 驗證 cold-boot 生效值 | 未入 |

---

## C. QC 完整量化 TODO 提案清單（30-60 條）

> 分級：High(P0/P1 阻塞關鍵路徑) / Mid(影響邊際 2-4w) / Low(參數調優/長尾)

### C.1 High 優先級（P0/P1 —— 影響 Live Gate 或邊際驗證）

#### 1. Edge 危機根源（G1 對應項目）

1. **QC-H1 · edge_estimator_scheduler 4 日停滯診斷** [P0]
   - 來源：2026-04-24 audit 發現 edge_estimates.json mtime 2026-04-20，未更新 4 日
   - 內容：root cause —— cron 未跑 / scheduler 掛起 / JSON 輸出路徑 bug
   - 驗收：scheduler 24h fresh · healthcheck [13] 報新鮮度 ≥2h
   - 工時：MIT 2h diagnosis + E1 0.5d hotfix

2. **QC-H2 · edge_estimates.json grand_mean <3 cells 時設 NaN** [P0]
   - 來源：2026-04-24 audit §4.1，grand_mean=-45.73 (n=1) 無統計意義
   - 內容：james_stein_estimator.py line 264，當 n<3 → grand_mean=NaN + _meta.is_valid=false
   - 驗收：proxy cells 生成後 (n≥5)，grand_mean 才信任；或條件綁 cost_gate
   - 工時：E1 0.5d + E4 1h

3. **QC-H3 · PostOnly 配置反向 bug 核實與修** [P0]
   - 來源：2026-04-24 audit FA 發現，demo=false / live=true（反向）
   - 內容：讀 `settings/strategy_params_{demo,live}.toml`，確認並修正
   - 驗收：demo=true, live=false（保守原則）
   - 工時：FA+E1 0.5d

4. **QC-H4 · edge 樣本層 threshold 設定（≥30 cells binding）** [P1]
   - 來源：2026-04-24 audit risk 清單 #3，當前 8.9/cell <<< 30 基準
   - 內容：cost_gate 不 bind grand_mean 直到 n_cells≥5 ∧ mean(n_per_cell)≥30
   - 驗收：edge_estimate_scheduler persist `_meta.bind_ready=false` 直到達標
   - 工時：E1 1d (Python + Rust schema)

---

#### 2. Kelly 參數化與風控

5. **QC-H5 · KellyConfig.fraction_tiers config 化** [P1]
   - 來源：2026-04-24 audit H7，kelly_sizer.rs:153-159 hardcoded 50/200 dividers
   - 內容：`KellyConfig { fraction_tiers: Vec<(u32, f64)> }` default [(50, 8.0), (200, 6.0), (∞, 4.0)]
   - 驗收：TOML per-symbol，IPC hot-reload 支持
   - 工時：PA+E1 1.5d

6. **QC-H6 · Guardian scoring weights config 化** [P1]
   - 來源：2026-04-24 audit H8，guardian.rs:123-177 hardcoded weights
   - 內容：`GuardianConfig.scoring { direction_conflict: 0.4, position_count: 0.3, ... threshold: 0.3 }`
   - 驗收：RiskConfig.guardian_scoring 派生 · 支持 IPC 和 TOML
   - 工時：PA+E1 2d

7. **QC-H7 · Guardian leverage_ratio reject cap config 化** [P1]
   - 來源：2026-04-24 audit H9，守護 line 142 `> 2.0` hardcoded
   - 內容：`GuardianConfig.reject_leverage_ratio: f64 = 2.0`
   - 驗收：TOML + IPC 熱更新
   - 工時：E1 0.5d（與 H6 共同修改）

---

#### 3. 波動率與 Regime

8. **QC-H8 · EWMA Vol Estimator 參數化** [P1]
   - 來源：2026-04-03 驗收報告，lambda + hist_decay 寫死
   - 內容：`EwmaVolConfig { lambda_1m: 0.90, lambda_1h: 0.94, lambda_1d: 0.97, hist_decay: 0.995 }`
   - 驗收：TOML per-symbol · Rust indicators 讀取配置
   - 工時：E1 1.5d (Rust + TOML binding)

9. **QC-H9 · Hurst + Hysteresis 整合** [P1]
   - 來源：2026-04-03 §3，Hurst R/S + hysteresis 作為 MarketRegimeTracker 輸入
   - 內容：MarketRegimeTracker 多信號融合（RegimeDetectorRule + Hurst + EWMA vol regime）
   - 驗收：regime_confidence 從 {0, 1} → weighted [0, 1]
   - 工時：E1+FA 2-3d (Hurst 實裝 + integration)

10. **QC-H10 · Hurst required_consecutive 按時間框架分級** [P1]
    - 來源：2026-04-03 M3，當前統一 6 週期過長
    - 內容：1h→4, 4h→3, 1d→3（而非統一 6）
    - 驗收：HurstHysteresis config per timeframe
    - 工時：E1 1d

---

#### 4. Cost Gate 與 Slippage

11. **QC-H11 · SLIPPAGE_TIERS table config 化** [P1]
    - 來源：2026-04-24 audit H1，intent_processor/mod.rs:229-235 整張表 const
    - 內容：`RiskConfig.cost_gate.slippage_tiers: Vec<(f64, f64)>` [(1B, 1), (100M, 2), ...]
    - 驗收：TOML + IPC patch_cost_gate
    - 工時：PA+E1 1.5d

12. **QC-H12 · Cost gate safety margin 1.3 config 化** [P1]
    - 來源：2026-04-24 audit H3，當 PostOnly 降費後需驗證是否過嚴
    - 內容：`RiskConfig.cost_gate.js_threshold_safety_mult: f64 = 1.3`
    - 驗收：TOML + IPC；≥1w PostOnly 驗證後可調 1.2-1.5 範圍
    - 工時：E1 0.5d

---

#### 5. Fast Track & Margin

13. **QC-H13 · fast_track 閾值 config 化** [P1]
    - 來源：2026-04-24 audit H6，15% / 5% / 3σ hardcoded
    - 內容：`RiskConfig.fast_track { extreme_drop_pct: 15.0, moderate_drop_pct: 5.0, moderate_drop_sigma: 3.0 }`
    - 驗收：TOML per-market (altseason/bear 兩套) + IPC
    - 工時：PA+E1 1d

---

### C.2 Mid 優先級（P1/P2 —— 2-4 週邊際驗證 + 調優）

#### 6. Donchian Leak-Free 修復

14. **QC-M1 · Donchian shift(1) 修復（leak-free bias）** [P1]
    - 來源：2026-04-24 audit BB-01 + memory F3 retract
    - 內容：openclaw_core/indicators/trend.rs::donchian 改 `&high[n-period-1..n-1]` 或加 shift param
    - 驗收：bb_breakout Hard mode breach 判定不再「mechanically always true」；Phase 1 sweep 重跑驗証
    - 工時：E1 1-2d + E4 回歸測試

15. **QC-M2 · Grid OU σ residual-based 修復** [P1]
    - 來源：2026-04-24 audit GT-01，raw 2nd moment vs residual std
    - 內容：grid_helpers.rs:128 改 `sqrt(Σ(changes-mean_dx)²/n)` + unit test
    - 驗收：OU recovery test（已知 OU process 下恢復 σ）
    - 工時：E1 1d

16. **QC-M3 · Kelly modified 生存偏差修正** [P1]
    - 來源：2026-04-03 S1 勘誤，current_run_time 語義
    - 內容：改為 total_observation_time（策略運行總時長）而非單筆交易持有時間
    - 驗收：Kelly 計算邏輯與原文一致
    - 工時：E1 0.5d

---

#### 7. Win-Rate & Cost Threshold

17. **QC-M4 · win-rate floor config 化** [P1]
    - 來源：2026-04-24 audit H4，wr.clamp(0.3, 1.0) hardcoded
    - 內容：`RiskConfig.cost_gate.min_win_rate_floor: f64 = 0.3`
    - 驗收：TOML + IPC；避免 division blowup
    - 工時：E1 0.5d

18. **QC-M5 · Cost gate notional tier boundaries config 化** [P1]
    - 來源：2026-04-24 audit H5，gate_k 分級 50 / 200 USDT
    - 內容：`RiskConfig.cost_gate.notional_tier_small: f64 = 50.0, _medium: f64 = 200.0`
    - 驗收：TOML，影響 cost_gate_k 乘子
    - 工時：E1 0.5d

---

#### 8. Confluence & Strategy-Level Magic Numbers

19. **QC-M6 · Confluence ADX scale config 化** [P1]
    - 來源：2026-04-24 audit M1，ADX divisor 50/25 hardcoded
    - 內容：`ConfluenceConfig.adx_scale_reversion: 50.0, adx_scale_trend: 25.0`
    - 驗收：TOML per-strategy
    - 工時：E1 1d（包含其他 confluence 參數）

20. **QC-M7 · Confluence volume ratio anchor config** [P1]
    - 來源：2026-04-24 audit M2，1.2 hardcoded
    - 內容：`ConfluenceConfig.volume_ratio_anchor: 1.2`
    - 工時：E1 0.5d（與 M6 共同）

21. **QC-M8 · Confluence RSI bands config 化** [P1]
    - 來源：2026-04-24 audit M4，scores 0.9/0.9/0.6 hardcoded
    - 內容：`ConfluenceConfig.rsi_bands: Vec<(lo, hi, score)>`
    - 工時：E1 0.5d（與 M6/M7 共同）

22. **QC-M9 · FundingArb confidence scaling** [P2]
    - 來源：2026-04-24 audit FA-01，divisor 10.0 + clamp(0.3, 0.9)
    - 內容：`FundingArbConfig.conf_edge_scale: 10.0, conf_min: 0.3, conf_max: 0.9`
    - 工時：E1 0.5d

23. **QC-M10 · BbReversion exit_conf bounds** [P2]
    - 來源：2026-04-24 audit M8，clamp(0.4, 0.8) hardcoded
    - 內容：`BbReversionParams.exit_conf_min: 0.4, exit_conf_max: 0.8`
    - 工時：E1 0.5d

24. **QC-M11 · Exit features ROC window** [P2]
    - 來源：2026-04-24 audit M9，300ms hardcoded
    - 內容：`ExitConfig.price_roc_window_ms: 300`
    - 工時：E1 0.5d

---

#### 9. Maker Timeout & Paper Fill

25. **QC-M12 · Maker timeout trend-aware scale** [P1]
    - 來源：2026-04-20 Q1，timeout 應按 A3 effective_cooldown 縮放
    - 內容：formula `min(0.75 × effective_cooldown_ms, 300_000)`
    - 驗收：grid entry 信號 half-life 秒級 vs cooldown 分鐘級對齊
    - 工時：E1 1d

26. **QC-M13 · Paper→demo fill_rate ratio 監控** [P1]
    - 來源：2026-04-20 phase1b，>1.3 或 <0.7 → paper 偏離警告
    - 內容：daily cron 計算 paper_fill_rate / demo_fill_rate，閾值告警
    - 驗收：每週 SLA 報告；超閾值禁用 paper 餵 edge_estimates
    - 工時：E1+QA 1.5d

27. **QC-M14 · Paper limit fill queue position 折扣** [P1]
    - 來源：2026-04-20 day-1 bias#1，touch = 50% fill vs cross = 100%
    - 內容：paper engine fill logic 改機率模型而非 optimistic
    - 驗收：Phase 1b 驗證 paper/demo fill 分佈對齊（Kolmogorov-Smirnov）
    - 工時：E1+E4 2d

---

#### 10. 數據品質 & 邊際基準線

28. **QC-M15 · fee drag vs R:R vs alpha 分解驗證** [P1]
    - 來源：2026-04-24 audit §2.1，3 層根因分解
    - 內容：SQL query per-strategy 驗收 win_bps / loss_bps / fee_bps 一致性
    - 驗收：ma_crossover avg_win=1.2 bps vs avg_loss=4.7 bps 真實性確認
    - 工時：QC+FA 1d

29. **QC-M16 · ma_crossover counterfactual R:R 對稱驗證** [P1]
    - 來源：2026-04-24 audit §2.1 / TODO G2-02
    - 內容：EDGE-DIAG Phase 2 replay 後重新計算 win/loss distribution
    - 驗收：R:R < 0.5 或 > 2.0 的根因（stop loss vs take profit 參數 mismatch）
    - 工時：QC+FA 2d

30. **QC-M17 · PostOnly 1-2w 驗證（被動觀察）** [P1]
    - 來源：2026-04-24 audit G2-01，demo grid fee 降 50% 預期
    - 內容：counterfactual cross-check maker rebate share；healthcheck fill_rate trend
    - 驗收：demo grid fee drag 從 3.5→1.75 bps，或決策 disable grid
    - 工時：PM+QC 被動 1-2w

---

### C.3 Low 優先級（P2/P3 —— 長尾參數調優 + 衛生）

#### 11. CUSUM & 策略衰減

31. **QC-L1 · CUSUM strategy health monitor 實裝** [P2]
    - 來源：2026-04-03 §4，當前無衰減檢測
    - 內容：`slack = 0.5σ, threshold = 5σ`（改絕對值為 σ 倍數）
    - 驗收：unit tests + strategy衰減檢測自動 suspend
    - 工時：E1+E4 3d

32. **QC-L2 · CUSUM 硬兜底 tier 動態** [P2]
    - 來源：2026-04-03 §4，連續虧損 15 筆太寬鬆
    - 內容：公式 `max(10, ceil(3/ln(1/(1-win_rate))))`
    - 驗收：per-strategy tier；勝率 70% → 7 筆自動暫停
    - 工時：E1 0.5d

---

#### 12. ATR 波動率基準線

33. **QC-L3 · ATR 倍數 walk-forward 驗證** [P2]
    - 來源：2026-04-02 §1.1 S1
    - 內容：{1.0, 1.5, 2.0, 2.5, 3.0} 中尋 parameter plateau vs cliff
    - 驗收：20d walk-forward 後確定最優 ATR multiplier per regime
    - 工時：E4+QC 3-5d（per-strategy 回測）

34. **QC-L4 · Regime 參數映射表（trending/volatile/ranging/squeeze）** [P2]
    - 來源：2026-04-02 §5.1C
    - 內容：hardcode → 確定性轉換表（不統計搜索）
    - 驗收：TABLE 設計 + TOML binding + unit test
    - 工時：E1+FA 2d

---

#### 13. Miscellaneous 衛生

35. **QC-L5 · bb_breakout cooldown ctor vs params 分歧驗證** [P2]
    - 來源：2026-04-24 audit L2，600K (ctor) vs 300K (params)
    - 內容：確認 cold-boot 實際生效值；統一為單一源
    - 驗收：const DEFAULT_COOLDOWN_MS 或 factory update_params(Default)
    - 工時：E1 0.5d

36. **QC-L6 · bb_breakout squeeze_expiry 重複常數提取** [P2]
    - 來源：2026-04-24 audit L1，2_700_000 重複定義
    - 內容：`const DEFAULT_SQUEEZE_EXPIRY_MS`
    - 工時：E1 0.25d

37. **QC-L7 · Grid DEFAULT_FEE_PCT vs intent_processor 去重** [P2]
    - 來源：2026-04-24 audit GT-02，0.00055 兩處定義
    - 內容：引用 intent_processor::DEFAULT_TAKER_FEE_RATE
    - 工時：E1 0.5d

38. **QC-L8 · RiskConfig vs StopConfig 默認同步** [P2]
    - 來源：2026-04-24 audit RK-01，5.0 寫死兩處
    - 內容：StopConfig::from_risk_config()派生路徑或明確註記「pre-hot-reload seed」
    - 工時：E1+E4 1d

39. **QC-L9 · Guardian Correlation dead field 清理** [P2]
    - 來源：2026-04-24 audit GD-01
    - 內容：要麼實裝（用 price_tracker 計 realized correlation），要麼刪（RiskConfig + TOML）
    - 工時：PA+E1 1-2d（取決於實裝 vs 刪除決策）

40. **QC-L10 · Bonferroni 修正在報告層應用** [P2]
    - 來源：2026-04-24 audit §3.2，64 combos × 3 horizons 需 log(192)≈5.3 adjustment
    - 內容：bb_breakout_threshold_sweep 報告層標準化 t-critical
    - 驗收：當 n_combos > 20 時自動應用 Bonferroni correction
    - 工時：E1 1d

---

#### 14. 教訓文檔與記錄

41. **QC-L11 · Kelly modified vs 簡單 Kelly 文檔化** [Etc]
    - 來源：2026-04-02/03 memory
    - 內容：docs/lessons.md 記「20 筆數據無法支持統計適應」原則
    - 工時：TW 1h

42. **QC-L12 · Edge estimate 樣本量門檻文檔** [Etc]
    - 來源：memory.md 2026-04-24
    - 內容：<50 不可信、50-200 低信、200-500 中信、>500 可信
    - 工時：TW 0.5h

43. **QC-L13 · Paper→Demo 一致性原則文檔** [Etc]
    - 來源：2026-04-20 / 2026-04-24
    - 內容：fill_rate ratio + 4 項 bias 防護原則
    - 工時：TW 0.5h

---

### C.4 Etc 級別（研究 / 方法論改進 / 長期）

44. **QC-E1 · Deflated Sharpe Ratio 自動計算** [Etc]
    - 來源：2026-04-02 §3.2
    - 內容：EvolutionEngine 輸出 DSR，DSR < 0.5 自動 reject
    - 工時：E1+E4 2d

45. **QC-E2 · Parameter plateau vs cliff 視覺化** [Etc]
    - 來源：2026-04-02 profile
    - 內容：walk-forward 後繪製 Sharpe vs ATR multiplier 曲線
    - 工時：E1 1d

46. **QC-E3 · Kelly fraction GUI 展示** [Etc]
    - 來源：2026-04-02 S4
    - 內容：tab-strategy 新增 Kelly f* 計算與建議（負 f* 警告）
    - 工時：E1a 1.5d

47. **QC-E4 · cost_edge_ratio 原則 #13 實裝** [Etc]
    - 來源：CLAUDE.md 原則 #13
    - 內容：cost/edge ≥ 0.8 → 建議關倉（當前僅前端展示）
    - 工時：AI-E+E1+E2 2-3d

48. **QC-E5 · Per-regime 表現追蹤（非參數優化）** [Etc]
    - 來源：2026-04-02 §5.2D
    - 內容：記錄 regime × 策略 Sharpe 矩陣，積累 200+/regime 後人工審閱
    - 工時：E1 1d (logging) + QC ongoing

49. **QC-E6 · Jump detection（K 線 body > 3σ）** [Etc]
    - 來源：2026-04-02 §5.3 N3
    - 內容：異常波動自動加寬止損 50%
    - 工時：E1 1d

50. **QC-E7 · Cross-exchange basis 新策略評估** [Etc]
    - 來源：2026-04-02 §5.3 F
    - 內容：Bybit vs Binance 基差回歸可行性分析
    - 工時：QC 3-5d 研究

51. **QC-E8 · Volatility mean reversion（variance risk premium）** [Etc]
    - 來源：2026-04-02 §5.3
    - 內容：隱含波動率 > 實現波動率 edge 可行性
    - 工時：QC 3-5d 研究

52. **QC-E9 · Liquidation cascade counter 信號** [Etc]
    - 來源：2026-04-02 §5.3
    - 內容：大量清算後均值回歸策略設計
    - 工時：QC 2-3d 研究

53. **QC-E10 · FundingRateArb 三參數 R-02 重評** [P3]
    - 來源：CLAUDE.md P3 G-2
    - 內容：待 Strategist live，重評 entry_basis_ratio / max_hold / confidence scaling
    - 工時：QC+FA 1d（R-02 上線後）

---

## D. 策略負 Edge 結構原因完整分層

> 基於 2026-04-24 audit 三層根因 + memory，完整拆解每個策略虧損根源

### D.1 Grid Trading（-36.15 bps/RT）

**費用層（主導 74%）**：
- Taker fee 5.5 bps × 2 (entry+exit) = 11 bps/RT
- PostOnly 改革預期 -2 + 5.5 = 3.5 bps/RT（降 60%）
- 毛虧損估計 -32 bps（即使 PostOnly）

**信號質量層（主導 20-30%）**：
- OU 模型 σ 估計有偏（raw 2nd moment vs residual）→ level 過鬆 → fills 過少
- 均值回歸假設在 weak drift 期失效（b < 0.05）→ 難入場難出場

**執行層（5-10%）**：
- Squeeze threshold 0.03 100% 觸發、expansion 0.04 永不達（1m scale mismatch）
- 適應範圍太寬 ±10%

**修復路徑**（優先順序）：
1. **P0**：PostOnly deploy 後驗證 fee drag 改善（預期 -3.5 → -1.75 bps）
2. **P1**：Grid OU σ residual-based 修復
3. **P2**：Squeeze/expansion threshold 重校（或 4h 框架）
4. **P3**：若毛虧損仍負 → 考慮 grid disable（P1-10 決策點）

---

### D.2 MA Crossover（-31.3 bps/RT）

**R:R 不對稱層（主導 20-30%）**：
- win_bps = 1.2、loss_bps = 4.7 → R:R = 0.26× 極端失衡
- 根因：
  - 止損距離可能固定、未按 ATR 縮放（vs 止盈可能追蹤）
  - 反向交叉出場只在損失已深時觸發（early exit 機制缺失）
  - Entry 信號弱（KAMA fallback to SMA，ER=0.5 中立）

**費用層（20-25%）**：
- Taker 5.5 bps 雙邊 = 11 bps/RT（不受 PostOnly 影響，因為小額快進出）
- 毛收益 = 0.64 × 1.2 - 0.36 × 4.7 ≈ -0.9 bps，費用再 -11 bps → -12 bps/RT 還達不到 -31.3

**根本 Alpha 層（至少 30-40%）**：
- 64% 勝率可能是小樣本假象（fold 偏差或參數過擬合）
- KAMA 參數對 BTC/ETH 不適配（crypto 24h 連續 vs 傳統市場日盤）
- ADX gate 可能過鬆（趨勢判定誤）

**修復路徑**（優先順序）：
1. **P0**：SQL verify avg_win_bps / avg_loss_bps 真實性（數據一致性檢查）
2. **P1**：Counterfactual replay（Phase 2）重新計算 win/loss 分佈，確認 R:R 根因
3. **P1**：Stop loss ATR 動態化、take profit 改為 ATR 倍數（Option B，待 G2-02 決策）
4. **P3**：若 R:R 仍 <0.5，考慮 ma_crossover replace（策略層改動）

---

### D.3 FundingRateArb（樣本不足，無邊際數據）

**結構性 Edge（理論上正）**：
- Funding rate 永續 8h 周期結算，日均 0.01-0.05%
- 基差交易成本：taker 11 bps round-trip = 0.11% per day equivalent
- 若 funding > 20 bps 8h period，edge 應正（需 ≥2 日持倉才 cover）

**數據不足**：
- 僅 77 fills，樣本量太低（need ≥200 per asset）
- 無借幣成本模型（spot short leg）
- 無 basis risk 分解（永續 vs 現貨價差波動）

**修復路徑**：
1. **P2**：蒐集 30d funding rate 時間序列，計算平均與分佈
2. **P2**：精算借幣成本（pool interest rate from Bybit/dydx）
3. **P2**：模型化 basis 動態，估計 max holding period（decay half-life）
4. **P3**：若 edge > +15 bps/day，啟用；< -10 bps，disable

---

### D.4 BB Reversion（信號不足 n=2）

**問題**：僅 2 fills，無法診斷

**根本原因推測**：
- %B < 0 過度敏感（BB 必須極度擠壓）
- RSI oversold < 30 限制太嚴（ % of time very small）
- Entry 信號稀缺（per 2w 可能僅 1-2 次）

**修復建議**：
- 放寬 %B 門檻至 < 0.2（vs <0）
- RSI 改為 < 35（vs < 30）
- 加入 Hurst regime boost（mean_reverting 時放寬門檻）
- Observe 2-4w 後重評

---

### D.5 BB Breakout（0 fills）

**問題**：dormant，無 edge 數據

**已知根因**（memory + CLAUDE.md）：
- **F1**：1m scale 與 threshold 不匹配（squeeze=0.03 100% trigger vs expansion=0.04 never reach）
- **F4**：FIX-26-DEADLOCK-1（squeeze_detected_ms 過期後無清除 → symbol 永久 dormant，已修）
- **F2**：信號 > edge（top edge <95% signal 效力）
- **F3**：Donchian leak-free shift(1) 後信號消失（measurement bias confirmed）

**修復路徑**：
1. **P0**：FIX-26-DEADLOCK-1 `--rebuild` 部署，healthcheck [12] 監控 fill 復活
2. **P1**：Donchian shift(1) 修復
3. **P2**：Scale 重校（4h framework？）或 conservative profile 種子值調整
4. **P3**：若修復後仍 0 fills，考慮 disable（策略刪除）

---

## E. 統計方法論 TODO 清單（獨立梳理）

> 除上述 C 節外，統計方法層還需補強的工作

### E.1 樣本量門檻 & Binding 邏輯

54. **QC-E11 · edge_estimate per-strategy sample floor config** [P1]
    - 當 n_cells < 3 時禁止 grand_mean binding
    - 當 mean(n_per_cell) < 30 時禁止 cost_gate bind（當前 8.9）
    - Healthcheck [14]：持續檢測達標進度

55. **QC-E12 · James-Stein shrinkage validity flag** [P1]
    - 新增 _meta.is_valid (bool)
    - n_cells ≥ 3 ∧ mean(n) ≥ 10 時 true；否則 false
    - Cost gate 繁讀 JSON 時驗證 is_valid

---

### E.2 Bootstrap 與信度區間

56. **QC-E13 · Per-strategy bootstrap 95% CI** [P2]
    - 對每策略池化標籤，計算 (edge_mean - 1.96×SE, edge_mean + 1.96×SE)
    - EDGE-DIAG Phase 3 依賴條件：per-strategy CI_lower > 0 for gate 1 fallback enable

---

### E.3 Leak-free 監測 & Audit

57. **QC-E14 · leak-free Donchian 大樣本重驗（Phase 2 backlog）** [P2]
    - 30-60d × 20+ symbols 真實數據
    - 比較 current-bar-inclusive vs shift(1)
    - 若 breach_diff_tstat(shift=1) > breach_diff_tstat(current) 顯著，runtime 改 shift

---

### E.4 多重檢驗修正

58. **QC-E15 · Bonferroni auto-adjustment** [P2]
    - bb_breakout_threshold_sweep.py 當 n_combos > 20 自動應用 log(n) t-critical adjustment
    - 64 combos → t_crit *= 1.18（log(64) ≈ 4.16，1.96 → 2.31）

---

### E.5 小樣本保護

59. **QC-E16 · Bessel 修正標準化** [P2]
    - 所有方差估計統一 ddof=1（當前混用）
    - 特別是 win_rate/avg_win/avg_loss 在 n<30 時

---

### E.6 出樣驗證框架

60. **QC-E17 · Walk-forward harness 補完** [P3]
    - 自動切分 train/test（3 月 train + 1 月 test）
    - 計算 per-fold Sharpe + 合併指標
    - Deflated SR 輸出

---

## F. 給 PA 的量化驗證重點（Fast Track）

> PA 在 FIX-PLAN 執行時必須關注的量化關鍵詞

### F.1 G1 邊界（Scheduler + Edge 數據）

**PA 必檢**：
- [ ] edge_estimator_scheduler 執行日誌（ `/tmp/openclaw/scheduler.log`）
- [ ] edge_estimates.json mtime 在過去 2h 內
- [ ] n_cells >= 1（至少有樣本）+ grand_mean 有值（非 NaN）
- [ ] proxy cells 包含全部 4 × N_symbols 項目（如 sync_label_*）
- [ ] healthcheck [13] 報 `freshness: PASS`

**验收標准**：
- scheduler 24h 必跑一次以上
- 新鮮度 < 2h

---

### F.2 G2 邊際驗收（Fee Drag & R:R）

**PA 必檢**：
- [ ] PostOnly demo=true / live=false（反向 bug 修）
- [ ] PostOnly 已部署後 grid_trading demo 跑 1w，fee drag 統計（預期 3.5 → 1.75 bps）
- [ ] ma_crossover SQL 驗證：avg_win_bps, avg_loss_bps 一致性（需 FA/QC 簽核）
- [ ] counterfactual replay mtime（Phase 2 結果）並產 R:R 新值

**驗收標准**：
- grid fee drag 改善 ≥ 30%（from 3.5 → 2.5 bps 或更低）或決策 disable
- ma_crossover R:R 數字合理化（≤1.0 的話需根因說明）

---

### F.3 G3 AI 接線（ExecutorAgent 決策鏈）

**PA 必檢**：
- [ ] ExecutorAgent IPC RFC 已簽核（PA 與 E1）
- [ ] shadow→live toggle IPC 有 unit test
- [ ] Rust intent_processor 有 intent 接收 handler（接 Python）
- [ ] e2e 測試執行通過（paper mode 下 intent → position 閉環）

**驗收標准**：
- intent IPC 吞吐 > 100/sec （延遲 <100ms）
- shadow→live 成功路徑有 ≥3 場景測試

---

### F.4 G4 ML 管線（Labels & Model Registry）

**PA 必檢**：
- [ ] labels 累積進度（grid_trading pooled 當前 47/200，ETA 2026-04-26）
- [ ] `run_training_pipeline.py` 首跑產出 ONNX artifact + registry row
- [ ] model_registry canary rules 實裝（state machine + auto-promote logic）
- [ ] shadow exit 數據寫入成功（learning.decision_shadow_exits row count > 0）

**驗收標准**：
- 首個 ONNX mtime < 24h
- registry 有 ≥2 rows（production + shadow canary）

---

### F.5 P0-3 邊評決策點（5 月初）

**PA 與 QC 必協商**：
- [ ] Phase 2 counterfactual replay 結果（edge 翻正 vs 仍負）
- [ ] PostOnly 1-2w 驗證結果（fee drag 改善幅度）
- [ ] grand_mean_bps 樣本量達標（n_cells≥5）
- [ ] healthcheck [11] 持續 PASS（3 日以上）

**決策分岔**：
- **A. 邊界翻正**（grand_mean > -20 bps）→ cost_gate 重啟、Track P Phase 1b 解凍
- **B. 邊界仍負**（grand_mean < -30 bps）→ DUAL-TRACK 全力（Phase 5 重做）

---

### F.6 E/QC 簽核清單（快速通道）

**為加快審核，QC 在以下檢查點「需秒簽」**：

1. **P0-13 ATR 修復驗證**：
   - Rust 代碼確認 Wilder's ATR (α=1/14)
   - Diff 與 pandas_ta 或 talib < 3%

2. **P1-11 FIX-26-DEADLOCK-1 驗收**：
   - squeeze_detected_ms 過期 auto-clear 邏輯
   - bb_breakout healthcheck [12] cron 報 fill 復活

3. **Graph OU σ 修復驗收**：
   - Unit test：已知 OU process 下恢復 σ

4. **Kelly / Guardian 參數化 TOML binding**：
   - 讀 config 邏輯與預期值一致

---

## 完整提案統計

| 級別 | 條數 | 涵蓋 |
|---|---|---|
| **High (P0/P1)** | 13 | G1-G3 edge/kelly/regime/cost gate |
| **Mid (P1/P2)** | 27 | Donchian/Grid OU/timeout/confluence/fee/R:R |
| **Low (P2/P3)** | 10 | CUSUM/ATR/衛生清理 |
| **Etc** | 10 | 教訓/研究/長期 |
| **Total** | **60** | — |

---

## 結語與下一步

當前系統面臨**結構性 edge 危機**（負 -45.7 bps grand_mean），根源來自：
1. **Fee drag** (60-70%)：PostOnly 改革中，預期改善 50%
2. **R:R 不對稱** (20-30%)：ma_crossover 待驗證與調整
3. **Alpha 缺失** (10%)：4/5 策略無可解釋的邊際

**QC 的 60 條提案按優先級排列為**：
- **P0 緊急**（13 項）：scheduler 恢復、kelly 參數化、Guardian 風控 → W1 解決
- **P1 關鍵**（27 項）：數學修復、邊際驗證、配置化 → W1-W2 解決
- **P2 中期**（10 項）：衛生、參數調優 → W2-W3 分散
- **Etc**（10 項）：研究方向、教訓文檔 → 持續

**最早 Live 日期依賴路徑**：
- P0-2 21d demo（~2026-05-07 解鎖）
- P0-3 邊評（+3 days）
- LG-2/3/4/5 live gate（2-3w）
- **樂觀 ~2026-05-23 / 中位 ~2026-05-30 / 悲觀 ~2026-06-15**

---

**Report Generated**: 2026-04-24 14:30 UTC  
**QC Signature**: Quantitative Consultant (OpenClaw)  
**Approval Required**: PA / PM / FA before Wave 1 execution

