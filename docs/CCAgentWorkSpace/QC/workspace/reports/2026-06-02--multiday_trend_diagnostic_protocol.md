# QC 樞紐診斷協議 — 多日 Trend/Momentum Edge 證偽優先測試

**日期**：2026-06-02 | **作者**：QC | **狀態**：協議 spec，待 implementer 執行
**範圍**：20 liquid perp，`market.klines` timeframe='1d'，~730 日/symbol（POLUSDT 635）
**性質**：證偽優先（falsification-first）診斷，非策略提案。對「多日 trend 有 edge」抱持懷疑、要求它證明自己。

---

## 0. 立場
- 6 週 intraday 死於成本牆（edge 1-3bps < 成本 11-27bps）。多日翻牆論點（低 turnover 攤薄成本）**數學上成立但有條件**，要實測非預設。
- TSMOM 是少數有跨資產跨數十年樣本支撐、未進 anomaly graveyard 的因子，half-life 匹配 1d sampling → 值得嚴格一測。但 crypto 僅 ~2 年 × 20 高相關 symbol，**統計 power 先天不足** → INCONCLUSIVE 比 GO/NO-GO 更可能。
- 防自欺機制（leak-free 並列 / DSR honest-K / regime labeling / survivorship）放在信號設計**之前**，任一防線失守即停。

## 1. 信號（4 族，K=24 trial 預算上限，誠實計入 DSR）
記號：`C_t`=第 t 日收盤，`r_t=ln(C_t/C_{t-1})`。**全部 t-1 收盤後算、t 日開盤執行**。

- **A — TSMOM 符號**：`signal_A(k)_t = sign(ln(C_{t-1}/C_{t-1-k}))`，k∈{20,40,60,90}（K=4）。
- **B — Vol-scaled TSMOM**：`vol_t=std(r_{t-1..t-60})`；`signal_B(k)_t=sign(Σr)×(σ_target/vol_t)`，k∈{30,60}（K=2）。σ_target=樣本期 cross-sectional median daily vol，**不 sweep**。
- **C — MA crossover**：`fast=SMA(C_{t-1..t-fast_n})`、`slow=SMA(C_{t-1..t-slow_n})`（**不含 C_t**）；`+1 if fast>slow else -1`，(fast,slow)∈{(10,30),(20,60),(50,100)}（K=3）。
- **D — Cross-sectional momentum**：`mom(i)_t=ln(C_{t-1}^i/C_{t-1-k}^i)`；cross-sectional rank → top tertile +1 / bottom tertile -1 / mid 0，k∈{30,60,90}（K=3）。market-neutral long-short，對沖 BTC beta，是 bull-only 試金石。

**持有期變體（×2，核心「多日 vs intraday」變數）**：(1) 每日再平衡；(2) 信號翻轉才換倉 + 最短持有 H_min=5 日（過濾 whipsaw，最低 turnover）。
**K = 12 × 2 = 24**。implementer 禁止偷加 grid 不更新 K；需加先停回報 QC。

## 2. Leak-Free PIT 紀律（防自欺第一道，任一違反=結果作廢）
- **shift(1) 鐵律**：信號只用 `C_{t-1}` 及更早；禁 `rolling(N).max/min/mean()` 含 current bar（用 `.shift(1).rolling(N)`）；vol/rank 都不含 t 日。
- **★ 強制並列雙軌**：每信號同時算 leak-free 版（shift1，正式）+ naive leak 版（含 current bar，僅診斷）。若 `Sharpe(naive)−Sharpe(leak-free)>30%` → 強 look-ahead，naive 正結果是幻覺，以 leak-free 為準。**報告必須並列兩版 Sharpe**（Donchian F3 教訓）。
- **PIT universe（survivorship）**：POLUSDT 上市前不可交易（signal=0、不入 rank/portfolio）；universe 用 `market.symbol_universe_snapshots`（禁用今天的 20 個回填歷史）；明確標「結論僅適用持續流動大中市值 perp，不外推全 universe」。
- **執行**：進場=t 日開盤 `O_t`，出場=出場日開盤；**禁用 t 日收盤執行 t 日信號**。

## 3. 多日成本模型（含 funding 累積）
`cost_RT = fee_entry + fee_exit + slippage_entry + slippage_exit + funding_cost`
- **Fee**：taker 5.5bps/side（保守，SSOT `/v5/account/fee-rate`），RT=11bps；maker 情境 RT=4bps 作 upside 敏感度。多日 trend 用 taker 上限證明能 survive 最壞成本。
- **Slippage**：5bps/side 保守上限，RT=10bps；分 BTC/ETH vs altcoin 兩組敏感度（若有 orderbook/spread 數據校準）。
- **Funding（多日關鍵新成本）**：`funding_cost = Σ(每個持有期跨越的 8h 結算) position_side × F_settlement`，`F_settlement` 取 `market.funding_rates` **已實現** history（NOT cap，不從 history max 反推 cap——funding_short_v2 教訓）。做多付正 funding（雙重成本）、做空收正 funding（部分補貼）。**分多/空拆解 funding 損益**。
- **★ 樞紐命題**：多日成本 = 30-66bps（做多牛市，含 funding）/ 21-31bps（做空收 funding），**比 intraday 11-27bps 更高**（funding 按時間累積非按交易次數攤薄）。翻牆真實條件 = **per-trade gross edge > 30-66bps**（一次成功波段捕 500-1500bps 理論上夠，問題在 win rate × R:R 結構撐不撐得起）。
- **cost_edge_ratio = cost_RT / gross_edge_per_trade**：<0.5 健康 / 0.5-0.8 marginal / ≥0.8 放棄。

## 4. 驗證門檻（防自欺核心）
- **★ Step 0 樣本量預檢（強制前置）**：N_min≈((z_{α/2}+z_β)σ/Δ)²，detect Sharpe Δ=0.5 需 ≥60 獨立 trades。算每信號每變體**實際方向翻轉次數/symbol**（變體2 下 60日 TSMOM 可能整 2 年僅 ~10-20 次/symbol）→ pooled trades → cluster-aware effective N。**effective N<60 → 直接 INCONCLUSIVE-A，不跑 DSR**（power<0.5 顯著性無意義）。
- **Walk-forward**：anchored expanding 4 折（train [0,365]→test[366,456]...逐步擴），train 內選最佳參數、test OOS；5 日 embargo；OOS≥0.3×IS 否則過擬合。
- **PSR(0)≥0.95**：skew/kurt-aware（crypto 厚尾，禁 normal z-test）。
- **DSR(K=24)≥0.95**：`SR_max_expected=sqrt(Var(SR_K))·[(1−γ)Φ⁻¹(1−1/K)+γΦ⁻¹(1−1/(Ke))]`，γ=0.5772。K=24 是命脈，誠實計入。
- **PBO<0.5**（CSCV，S=8 time-block）；2 年切 8 block 後若 model-selection 維度不足，誠實標 PBO semantics、主防線回 walk-forward OOS。
- **Block bootstrap**（block=20-30日，非 IID）1000 次 → net Sharpe 95% CI 下界 >0。
- **相關性/Effective N**：Pearson+Spearman 矩陣、PCA（PC1 預期 50-70%=BTC beta）、`N_eff≈(Σλ)²/Σλ²`（預期 3-8 非 20）→ 縮減 Step0 有效樣本。
- **資料品質 5-test**：ADF/KPSS（平穩）、**Ljung-Box（正自相關=TSMOM 統計基礎；無/負自相關 → NO-GO-A 早期信號）**、Jarque-Bera（必拒 normality）、ARCH（vol clustering）。
- **年化用 ×365**（crypto 24/7，非 ×252）。

## 4b. Regime Labeling（治理強制）
- 標 730 天 regime（leak-free PIT，scoring 前凍結）：用 `market.regime_snapshots` 或 `HurstHysteresis`，**禁 HMM**；rule-based 如 BTC 200日MA 上下 + realized vol tercile → {bull,bear,chop}。報告 bull/bear/chop 各佔多少天（2024-2026 很可能 bull-dominated）。
- **net Sharpe 分 regime 報告**。**治理判定（不可協商）**：edge 只在 bull 為正 → `regime-bet/learning-only` **非 promotion proof**；durable 需 non-bull non-negative 支持，或信號 D market-neutral 後仍有 idiosyncratic alpha。
- walk-forward 各 fold 落哪個 regime；4 折 OOS 全在 bull → 標「OOS 本身 bull-only 不能宣稱 cross-regime robust」。

## 5. 決策樹
- Step0 effective N<60 → **INCONCLUSIVE-A**（2 年不足，接 longer-history backfill 重跑）
- Ljung-Box 無正自相關 → **NO-GO-A**（trend 無統計基礎）
- leak-free 版 Sharpe≈0 但 naive 高 → **NO-GO-B**（全 look-ahead）
- net Sharpe<0.5 OR cost_edge_ratio≥0.8 → **NO-GO-C**（成本牆在多日仍成立；gross 正但 funding 轉負則標「funding 是殺手」）
- DSR<0.95 OR PSR<0.95 OR bootstrap CI 下界≤0 → **NO-GO-D**（樣本足=過擬合）/ **INCONCLUSIVE-B**（樣本邊緣=power 不足）
- OOS<0.3×IS OR PBO≥0.5（維度足）→ **NO-GO-E**（過擬合）
- 全過 + edge 只在 bull → **GO-CONDITIONAL（learning-only，禁 promotion）**
- 全過 + non-bull non-negative（或信號 D market-neutral 後正）→ **GO**（進完整策略設計）

## DATA TASKS（implementer 須查真實數據）
1. **Fee tier**：`/v5/account/fee-rate` 或 `bybit_api_reference.md` 實際 demo/live taker/maker bps。
2. **Funding 量級**：`market.funding_rates` 對 20 symbol 算 mean/median per 8h、分 regime、持有 5/30/60 日累積 drag 分布（多 vs 空）。**決定成本牆高度**。⚠ 須先確認 funding history 覆蓋是否達 730 天窗口（可能僅近期 → 成本模型用代表性均值或標 INCONCLUSIVE-on-cost）。
3. **Slippage 校準**：`market.market_tickers` 歷史 spread，BTC/ETH vs altcoin 分組。
4. **信號頻率**：跑信號生成報告每信號每變體實際方向翻轉次數/symbol → pooled trades → effective N。**決定能否進 §4.1 之後**。
5. **Regime 組成**：730 天 bull/bear/chop 各佔多少（`market.regime_snapshots`/`HurstHysteresis`，禁 HMM，scoring 前凍結 label）。

## 派工鏈
implementer（E1/research）實作 harness + 先跑 DATA TASK → MIT 主審 §2 leak harness（feature leakage 是 MIT 主責）→ QC 複核 §4 統計執行（DSR 的 K、PSR skew/kurt、PBO semantics、regime 拆解誠實性）+ 最終判定。

## 已知陷阱（implementer 防範並聲明）
小樣本 power 不足 / 20 symbol 高相關假性大樣本 / look-ahead（rolling 含 current）/ survivorship（今天 liquid 20 回填）/ multiple-testing（K 誠實）/ bull-only 偽 alpha / funding 低估（誤推 cap）/ cascade 反轉 / PBO single-cell 退化 / maker 樂觀 / ×252 誤用 / normal 顯著性。

## INCONCLUSIVE 出口路徑
INCONCLUSIVE-A/B → 接 V125 + daily backfill writer（已部署）backfill 更長歷史（Bybit 有更早 daily 數據）後重跑；診斷與 backfill 可並行。NO-GO → 誠實收掉多日 trend，回 listing fade（probe 已建）。
