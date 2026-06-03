# QC 樞紐診斷協議 — Funding-Tilt / 多日 Funding Carry Edge 證偽優先測試

**日期**：2026-06-03 | **作者**：QC（設計） | **持久化**：PM（QC 角色 Write 禁用，內容為 QC 產出）
**狀態**：協議 spec（DESIGN-only），待 implementer 執行
**範圍**：20 liquid linear perp（與 trend 診斷同 universe），signal = realized funding（`research.alpha_funding_rates_history`，8h 結算，run-versioned，~730d），price = `market.klines` 1d（open-to-open 執行）
**性質**：證偽優先（falsification-first）。對「perp-only directional funding-tilt 有扣成本後 edge」抱持懷疑，要求它證明自己。對標 `2026-06-02--multiday_trend_diagnostic_protocol.md` 的 5 重防自欺嚴謹度。
**前一象限結論**：多日 price trend = 🔴 NO-GO-TREND（commit a99ef886，已獨立複核）。本協議測 operator 戰略意圖逃逸象限路②的 funding 維度。

---

## 0. 立場與三條紅線（必須在實作前正確處理，否則重蹈覆轍）

### 0.1 為什麼 funding-tilt 值得一測（vs trend 剛 NO-GO）
- **alpha 來源歸類明確**：類別 #2 結構性低效（funding 是 perp 維持與 spot 掛鉤的結構性轉移支付）。crypto carry 是少數**未進 anomaly graveyard**、有跨資產跨數年學術支撐的因子（BIS WP 1087 "Crypto carry"；CMU Christin et al. "The Crypto Carry Trade"；crypto futures basis-momentum 文獻）。trend 在 universe-wide 缺正自相關（統計前提缺席）；funding-tilt 的統計前提是「funding 對未來報酬有 cross-sectional 預測力」，是**不同且尚未在本系統測過**的命題。
- **half-life 匹配**：funding 8h cycle + 結算費率的序列持續性（funding 有強自相關 / persistence，與 price return 的近白噪音相反）→ 信號 lifecycle 與 1d sampling 匹配，落在 OpenClaw 1-30d 適用區間。
- **資料品質升級**：trend 的 funding 成本被迫標 INCONCLUSIVE-on-coverage（`market.funding_rates` 僅 ~58d，用代表性均值）。本協議用 **V125 `research.alpha_funding_rates_history`**（~730d realized funding，PIT-clean，NOT NULL fail-closed，strict-parse 拒 fake-zero）→ funding 既是信號也是成本，可**逐結算對齊**而非均值近似。這是本協議相對 trend 的核心方法升級。

### 0.2 ★ 紅線 1：demo 無 spot lending → 只能 perp-only directional（不可 delta-neutral）
- A1 funding_arb DOA 教訓 + crypto-microstructure §3.2：cash-and-carry（long spot + short perp 收 funding）在 Bybit demo 數學不成立（無 spot 借貸腿）。
- **本協議信號 = perp-only directional funding-tilt**：做多 funding 最負的 perp（持有被付費）、做空 funding 最正的（持有收費）。**無對沖腿，價格方向風險完全裸露**。
- **誠實後果**：學術 carry 多數正報酬來自 delta-neutral（價格風險被對沖，純收 carry）。perp-only directional 是**更弱、更曝險的子集**——你同時押注「funding 方向」與「該 funding 隱含的價格不會反向吃掉 carry」。協議必須拆出「funding carry 貢獻」vs「裸價格方向貢獻」，否則無法歸因（見 §3.5 + §4b）。

### 0.3 ★ 紅線 2：funding cap SSOT = `instruments-info.upperFundingRate`，禁從樣本窗 max 反推
- funding_short_v2 §2.4 方法論硬傷（已被 BB 實查否證）：用 66 天低-premium 窗 max(+0.0001) 誤判結構 cap +10.9% APR，真 cap 高 50-200×（BTC/SOL +547% / 1000PEPE +1095% / WIF +2190% APR）。
- **本協議任何涉及 funding 量級上下限的判斷，cap 一律查 `instruments-info` 的 `upperFundingRate`/`lowerFundingRate`/`fundingInterval`（SSOT）**。`research.alpha_funding_rates_history` 存的是**已實現**費率（backfill 明禁碰 cap，`funding_oi_backfill.rs` 硬邊界 #4），用於信號 + 成本；cap 只在「成本牆機制檢查」需判斷 funding 是否觸頂時引用，且只能讀 instruments-info。
- 本協議的信號**不依賴 cap**（用已實現 funding 排序），故 cap 誤判風險低於 funding_short_v2，但仍須在報告聲明「cap 一律 SSOT，未從 history max 反推」。

### 0.4 ★ 紅線 3：funding 是雙面的（信號 + side-dependent 成本同源）
- 你持倉跨越結算即付/收 funding：net funding 既是 alpha 來源，**也是 side-dependent 成本**。
- **致命陷阱**：若信號用「做多 funding 最負」（預期收 funding 補貼），則該 funding 補貼**同時**是成本模型的 funding 項——若 cost_model 把它算成正成本（drag），會雙重懲罰；若 gross edge 已含 funding carry 而 cost 又扣一次，會雙重計入。**必須明確定義 gross 是否含 funding**（見 §3.0 會計約定），避免符號錯置。

### 0.5 防自欺機制放在信號設計**之前**
leak-free PIT（§2）、會計約定（§3.0）、樣本充分性預檢（§4 Step 0）、regime labeling（§4b）、survivorship（§2.3）——任一防線失守即停，不進統計顯著性檢定。

---

## 1. 信號（2 族 + 持有期變體，K 誠實計入 DSR）

記號：對 symbol i、結算時點 s，`F^i_s` = 該結算**已實現** funding rate（分數，`alpha_funding_rates_history.funding_rate`）；`C^i_t` = 第 t 日收盤；`O^i_t` = 第 t 日開盤。**全部信號只用「進場日開盤前最後一個已結算 funding」及更早**（§2 leak-free 鐵律）。

### 1.A — Cross-sectional funding-tilt（核心，market-neutral long-short）
- **funding 信號聚合**：對每個 rebalance 日 t，每 symbol 算 `tiltscore^i_t = mean(F^i_s : s ∈ 過去 L 個已結算 funding, 全部 settlement_ts < entry_open_ts_t)`，L∈{3, 9, 21}（= 約 1d / 3d / 7d 的 8h 結算數，K=3）。用均值平滑單結算噪音。
- **cross-sectional rank**：每日對 `tiltscore^i_t` 做橫截面 rank → **top tertile（funding 最正）= short -1 / bottom tertile（funding 最負）= long +1 / mid = 0**。
  - 方向直覺：funding 最正 = 多頭擁擠/付費持有多單 → 做空收 funding + 賭擁擠反轉；funding 最負 = 空頭擁擠/付費持有空單 → 做多收 funding + 賭反轉。
  - market-neutral long-short **對沖 BTC beta**，是「funding carry 本身有無 edge」的試金石（剝離市場方向）。
- **K_A = 3（L 值）**。

### 1.B — Time-series funding-extreme（per-symbol，診斷對照）
- **per-symbol 信號**：`signal_B^i_t = -sign(tiltscore^i_t)` 當 `|tiltscore^i_t| ≥ θ`（funding 極端才進場），θ = 該 symbol 樣本期 `|tiltscore|` 的 80th percentile（**expanding window PIT，不含未來**）；否則 flat。
  - 方向：funding 極正 → 做空（收 funding）；funding 極負 → 做多（收 funding）。賭 funding-extreme mean-revert + 收 carry。
  - **這是 funding_short_v2 的 regime-dormant 版的正確 reframe**：不設固定 APR 門檻（那是 funding_short_v2 160% break-even 過高的死因），而是相對自身分布的極端。
- **K_B = 1**（θ 不 sweep，用固定 percentile）。
- **誠實預期**：time-series 版有 BTC-beta 污染（funding 極端常 universe-wide 同步 → 變相 BTC directional bet），是 §4b regime gate 的主要打擊對象。

### 1.2 持有期變體（×2，「多日 vs 單結算」核心變數 = 成本牆攤薄論點的命脈）
- **variant 1「per-settlement-ish daily rebalance」**：每日按信號再平衡（最高 turnover）。
- **variant 2「low-turnover multi-day」**：信號 tertile 翻轉才換倉 + **最短持有 H_min = 7 日**（≥21 結算，最低 turnover）。**這是 operator「低 turnover 多日 carry 攤薄成本」逃逸論點的直接實作**。

### 1.3 K 預算（誠實計入 DSR）
`K = (K_A=3 + K_B=1) × 2 持有期 = 8`。比 trend 的 K=24 小（信號族少），DSR deflate 壓力較輕，但仍誠實計入。**implementer 禁止偷加 grid（如多個 θ、多個 H_min）不更新 K**；需加先停回報 QC。沿用 trend harness 的 `count_trial_budget()` 自檢範式。

---

## 2. Leak-Free PIT 紀律（防自欺第一道，任一違反 = 結果作廢）

### 2.1 ★ funding 信號的 leak-free 鐵律（與 trend 的 price-shift 不同，這是本協議獨有的關鍵）
- **funding 結算時點才已知**：`F^i_s` 在 settlement instant `s` 之後才可知。信號在進場日 t 只能用 **`settlement_ts < entry_open_ts_t` 的已結算 funding**。
- **實作鐵律**：`tiltscore^i_t` 的 funding 集合必須嚴格滿足 `funding_ts < O_t 的 wall-clock`（進場日開盤時點）。因 funding 8h 結算（00/08/16 UTC）、進場用日開盤（00:00 UTC），進場日 00:00 UTC 的信號**只能用前一日 16:00 UTC 及更早的結算**（當日 00:00 結算與開盤同時，保守排除 → 用 `funding_ts ≤ entry_open_ts − ε` 嚴格小於，ε = 1 結算間隔，對齊 AEG-S0 §2.3 `feature_ts ≤ t − one_complete_bar`）。
- **★ 強制並列雙軌（對標 trend §2.2 Donchian F3 教訓）**：每信號同時算
  - **leak-free 版（正式）**：funding 嚴格 `< entry_open_ts − ε`。
  - **naive leak 版（僅診斷）**：funding 含「進場當日結算」（look-ahead）。
  - 若 `Sharpe(naive) − Sharpe(leak-free) > 30%（相對）` → 強 look-ahead，naive 正結果是幻覺 → **NO-GO-B**。報告必須並列兩版。
  - **為什麼這個對照對 funding 特別重要**：funding 與當期價格走勢同期相關（funding 正常因多頭擁擠 = 價格剛漲）；若洩漏當日結算，等於偷看當日價格方向 → 必虛高。

### 2.2 funding interval 不可假設 8h（per-symbol 變異）
- `funding_oi_backfill.rs:611` 寫 `funding_interval_minutes = None`（未拉 instruments-info）。**禁假設全 universe 8h**。
- **實作**：per-symbol 從 `alpha_funding_rates_history.funding_ts` 相鄰結算間距推 interval（眾數），與 instruments-info `fundingInterval` 交叉核對（cap discipline：只讀 interval 欄，不讀 history max）。WIF 等 4h symbol 的「L 個結算」對應的 wall-clock 窗較短，須正確換算。APR 換算 `× (24/interval_h) × 365`。
- interval 不一致或缺 → 該 symbol 標 `funding_interval_uncertain`，從 cross-sectional rank 排除。

### 2.3 PIT universe（survivorship）
- 用 `market.symbol_universe_snapshots.listed_at` 做 survivorship mask；上市前 signal=0、不入 rank/portfolio。
- **明確標**：universe = 持續流動 20 大中市值 perp（backfill_universe.toml，**尚未經 QC/MIT 流動性 cutoff 復核**）。結論僅適用此 cohort，不外推全 universe。AEG-S0 §1.6 要求 PIT universe 不可 current-survivor-only；本協議 20-symbol 是 current-liquid 子集 → 必標 `breadth-limited / survivor-cohort`，**不可宣稱 cross-universe durable**。

### 2.4 執行紀律（沿用 trend pnl.py）
- 進場 = 進場日**開盤 `O_t`**（信號在前一結算後算），出場 = 出場日開盤。open-to-open 報酬，徹底避免隱性 look-ahead。

### 2.5 run-versioning 去重（V125 schema 特性，trend 無此問題）
- `alpha_funding_rates_history` PK 含 `run_id`，多次 backfill run append 各自證據（ON CONFLICT DO NOTHING）。
- **實作鐵律**：data_loader 必須**先選定單一 canonical accepted run**（`alpha_history_ingest_runs.status='accepted'`，取最新 `completed_at` 或 operator 指定 run_id），**只讀該 run 的 funding rows**。禁跨 run 混讀。報告記錄所用 `run_id` + `manifest_sha256`。

---

## 3. 多日成本模型（含 funding 雙面 + taker/maker）

### 3.0 ★ 會計約定（紅線 3 落地，釘死符號避免雙重計入）
**約定**：`gross_edge` = **純價格 open-to-open 報酬 × side（不含 funding）**；`funding_pnl` = 持有期跨越結算的 `Σ side × F_realized`（**單獨一項**，可正可負）；`cost` = fee + slippage（**不含 funding**）；`net_edge = gross_edge + funding_pnl − cost`。
- funding 只進 `funding_pnl` 一次，不重複。
- **報告必須三項分開呈現**：`gross_price_bps` / `funding_pnl_bps` / `cost_bps`，使「edge 來自 carry 還是價格」一目了然。
- ⚠ 與 trend cost_model 把 funding 當「cost 的一項」的會計不同。本協議因 funding **是信號本身**，必須把它從 cost 提出來當獨立 PnL 項。沿用 `funding_cost_bps_for_holding(side, holding_days, F)` 計算 `side × F × n_settlements`，但**命名為 `funding_pnl` 並從 net 的加項處理**（符號：多單付正 funding → funding_pnl 為負；空單收正 funding → funding_pnl 為正）。

### 3.1 Fee（沿用 trend，保守上限）
Taker 5.5 bps/side（SSOT `/v5/account/fee-rate`），RT = 11 bps；maker 情境 RT = 4 bps 作 upside 敏感度。低 turnover 多日用 taker 上限證明能 survive 最壞成本。maker fill rate caveat（≥60% fill）標明，未驗 queue position。

### 3.2 Slippage（沿用 trend）
5 bps/side 保守上限，RT = 10 bps；BTC/ETH vs altcoin 兩組敏感度（若有 orderbook/spread 數據校準）。

### 3.3 funding_pnl（本協議核心，雙面）
- `funding_pnl_bps = Σ(持有期跨越的每個結算) side × F_realized_settlement × 1e4`，**逐結算對齊**（用該 symbol 該窗真實結算序列，**非均值近似**——相對 trend 的升級）。
- per-symbol interval 正確（§2.2）：8h symbol 持有 7 日 = 21 結算；4h symbol = 42 結算。
- **多/空拆解**：long_funding_pnl vs short_funding_pnl 分開報。

### 3.4 ★ 樞紐命題（成本牆攤薄論點的數學核心 — 與 trend 對稱但結論可能相反）
- **trend 的成本牆**：funding 按時間累積 → 多日持倉 funding **drag** 比 intraday 更高（funding 是純成本）。
- **funding-tilt 的不同**：funding 是**信號 + PnL 來源**，方向設計成「收 funding」→ 持有越久，funding_pnl **累積為正**（carry 收割）：**fee/slippage 按交易次數攤薄（低 turnover → 每筆攤更多 carry），funding_pnl 按時間累積為正**。
- **真實翻牆條件**：`mean(funding_pnl_bps per trade) > cost_bps per trade` 且 `gross_price_bps` 不顯著為負。
- **break-even 攤薄算式**：H_min=7 日、8h symbol、per-trade fee+slip RT = 21 bps（taker），若每結算平均收 funding |F| = 1 bp，21 結算 × 1 bp = 21 bps carry → 剛打平。**若 realized funding 中位數 < ~1 bp/結算，carry 攤不平成本 → NO-GO-C**。這是 funding_short_v2「160% break-even 攤到 ~3% APR」論點的可測版：3% APR ≈ 0.027 bp/結算的 carry，遠低於打平所需 → **這正是最可能的失敗模式**。

### 3.5 cost_edge_ratio + carry 歸因
- `carry_cost_ratio = cost_bps / funding_pnl_bps`（funding_pnl > 0 時）：<0.5 健康 / 0.5-0.8 marginal / ≥0.8 放棄。
- **carry 純度**：`carry_share = funding_pnl_bps / (funding_pnl_bps + max(gross_price_bps, 0))`。若 net 為正但 carry_share 低 → 偽裝成 carry 的 directional bet，須 regime gate（§4b）；若 gross_price_bps 顯著為負而 funding_pnl 為正抵銷 → 「收 carry 但被價格反向吃」，淨 marginal。

---

## 4. 統計門檻（防自欺核心）

### 4.0 ★ Step 0 樣本充分性預檢（強制前置，binding gate）
operator 直接問：「funding-tilt 是否也有 trend 那種 BTC-beta 致 N_eff 崩塌（2.087）問題，還是 cross-sectional funding 更獨立？」

**誠實回答：cross-sectional funding-tilt 的 N_eff 比 time-series 高，但仍受 BTC-beta 部分限制，且 AEG-S0 的 `n_independent` 規則對它特別嚴。**

1. **AEG-S0 §2.9 `n_independent` 計數規則（治理硬規範）**：Cross-sectional 策略 = 每個 rebalance 時點算 1 個獨立樣本（BTC-beta clustering 後）；同 rebalance 的多 symbol 是 **breadth，不是 independent time evidence**。→ 信號 A 的 n_independent = 獨立 rebalance 次數。variant 2（H_min=7d）下，730d / 7d ≈ **104 次 rebalance**（上限，實際因翻轉觸發更少）。
2. **cross-sectional 的相對優勢**：信號 A long-short market-neutral，剝離 PC1（BTC beta）後賭 funding 的橫截面離散度 → 獨立性 > 時間序列方向（**funding-tilt 比 trend 更可能有 power 的理由**）。但 crypto funding 橫截面相關性高 → 須實證 PCA on funding-tiltscore 矩陣取 N_eff。
3. **Step 0 硬門檻**：算信號 A 實際獨立 rebalance 次數 + 信號 B cluster-aware 獨立持有窗數 + funding-tiltscore 橫截面矩陣 `N_eff = (Σλ)²/Σλ²`。N_min = detect Sharpe Δ=0.5 需 ≥60 獨立 trades。**n_independent(A) < 60 → INCONCLUSIVE-A**（接 longer backfill，但見誠實 caveat：backfill 對 N_eff 救不了）。

### 4.1 資料品質檢定（funding-specific）
純 numpy（Linux runtime 無 scipy/statsmodels）：
- **funding persistence（Ljung-Box on funding series）**：carry 統計基礎 = funding 自相關為正。無正自相關 → **NO-GO-A**（預期 PASS，funding 已知有強 persistence，非主要 binding gate）。
- **funding-tiltscore vs forward return 正確尺度檢定**（對標 trend `tsmom_significance`）：pooled cross-sectional mean net forward + **HAC t-stat（Newey-West lag = 重疊持有期）** + hit rate。`mean > 0 且 HAC |t| ≥ 2` → 顯著。
- **Jarque-Bera**（拒 normality → PSR 非 normal z-test）。**ARCH-LM**（vol clustering → block bootstrap）。年化 ×365。

### 4.2 Walk-forward + 過擬合
anchored expanding 4 折；train 內選最佳 L、test OOS；**embargo = max(H_min, L 對應天數)**；OOS ≥ 0.3×IS。**PSR(0) ≥ 0.95**；**DSR(K=8) ≥ 0.95**；**PBO < 0.5**（CSCV，維度不足則誠實標 semantics、主防線回 walk-forward OOS）；**Block bootstrap**（block = max(20日, H_min)）1000 次 → net Sharpe 95% CI 下界 > 0。

### 4.3 相關性 / N_eff（兩個矩陣，本協議獨有）
- **price-return N_eff**（沿用 trend，預期 ~2.087）：裸價格方向風險集中度。
- **funding-tiltscore N_eff**（新）：cross-sectional funding 信號有效獨立維度。**兩者並列**，回答 operator 核心問題。

### 4b. Regime Labeling（治理強制，AEG-S0 §2.7 + ADR-0047）
用 AEG frozen classifier `aeg_regime_v0.1.0`（或 trend harness rule-based BTC 200日MA + vol tercile fallback，**禁 HMM**，leak-free PIT，scoring 前凍結）標 730 天 regime。報告 overlay flags。**net edge 分 regime 報告**。治理判定（不可協商）：edge 只在 bull 為正 → `regime-bet / learning-only`；durable 需 ≥1 non-bull slice 獨立通過 gates 1-7。
- **★ funding-tilt 的 regime 陷阱（必查）**：bull market 多數 perp funding 同正 → cross-sectional tilt 退化為「做空 funding 最正（最擁擠）的 alt」，本質是 **short-squeeze 風險暴露**（類 trend short-side 厚尾）。若正 edge 集中在 short top-funding alt + bull regime → **賣 short-squeeze 保險偽裝成 carry，NO-GO**。

### 4.5 ★ funding 的 cost-wall 機制檢查（成本牆論點直接驗證）
- 報告 per-trade 拆解 `fee+slip 佔 |net|` vs `funding_pnl 佔 |net|`，**沿 H_min 掃描**（H_min ∈ {1,3,7,14 日}診斷，不入 K）→ 畫「holding horizon vs cost-share」曲線。
- **驗證攤薄論點**：cost-share 隨 H_min 上升而下降、且 net 隨 H_min 上升轉正 → 攤薄成立。**若 net 隨 H_min 上升仍 ≤0 → 攤薄論點證偽，NO-GO-C**。
- ⚠ 學術紅旗：「daily factor returns 顯著強於 weekly，monthly nonsignificant」→ carry signal 隨 horizon 拉長**衰減**。與「低 turnover 多日攤薄」直接張力（拉長 horizon 省 fee 但 carry edge 也衰減）。本檢查量化淨效果。

---

## 5. 決策樹
- Step 0：n_independent(A) < 60 → **INCONCLUSIVE-A**
- funding Ljung-Box 無正自相關 → **NO-GO-A**（預期不發生）
- leak-free Sharpe ≈ 0 但 naive 高（>30% gap）→ **NO-GO-B**
- §4.5 net 隨 H_min 上升仍 ≤0 OR carry_cost_ratio ≥ 0.8 → **NO-GO-C**（攤薄證偽，最可能）
- net 正但 carry_share 低 + edge 集中 bull short-side top-funding → **NO-GO（short-squeeze 保險偽裝）**
- DSR(K=8) < 0.95 OR PSR < 0.95 OR bootstrap CI 下界 ≤ 0 → **NO-GO-D** / **INCONCLUSIVE-B**
- OOS < 0.3×IS OR PBO ≥ 0.5 → **NO-GO-E**
- 全過 + edge 只在 bull → **regime-bet / learning-only**
- 全過 + ≥1 non-bull slice 獨立通過（carry_share 高）→ **GO（durable-alpha candidate）**

---

## DATA TASKS（implementer 須查真實數據，先於 §4 — binding，避免 trend/funding_short_v2 覆蓋假設覆轍）

0. **★ canonical run + 覆蓋驗證（最 binding）**：選定 accepted run；per-symbol count / min-max(funding_ts) / 相鄰間距眾數（推 interval）/ gap；確認 46539 列 ~730d 均勻覆蓋 20 symbol（≈2327/symbol @ 8h），**非近期密集 + 早期稀疏**；交叉核對 `alpha_history_ingest_pages.coverage_status`（AEG-S0 §1.5 funding overlay gate coverage_pct ≥ 0.95）。**若覆蓋實為近期密集 + 早期稀疏 → 退回 INCONCLUSIVE-on-coverage，不值得跑全程**。
1. **funding 量級分布（決定成本牆高度）**：per-settlement `|F|` 的 mean/median、分 regime、per-symbol。**核心**：median |F| 是否 ≳ 1 bp/結算（§3.4 break-even 所需）。若 median |F| ≈ IR floor 量級（~0.01 bp）→ 提前 NO-GO-C 信號。
2. **funding interval per-symbol**：funding_ts 間距推 + instruments-info `fundingInterval` 核對（cap discipline）。
3. **funding cross-sectional 離散度**：每 rebalance 日橫截面 tiltscore std/IQR → 有無足夠離散度支撐 tertile long-short。
4. **Fee tier**：`/v5/account/fee-rate` 實際 demo/live taker/maker bps。
5. **Regime 組成**：730 天 bull/bear/range/chop 各佔多少（禁 HMM，scoring 前凍結）。預期 bull-dominated → 觸 overlay。

---

## 派工鏈
implementer（E1/research）實作 harness（**復用 trend harness 骨架**：data_loader 改讀 canonical run + klines、signals 改 funding-tilt 雙族、cost_model 沿用但會計改 §3.0、stats 沿用 + funding-tiltscore PCA、pnl 沿用 open-to-open）+ 先跑 DATA TASK → **MIT 主審 §2 leak harness**（funding 結算對齊 PIT + canonical run 去重 + coverage 驗證）→ QC 複核 §4 統計執行 + 最終判定。

## 已知陷阱（implementer 防範並聲明）
覆蓋假設 / run-versioning 跨 run 混讀重複計數 / funding 洩漏當期價格（naive 雙軌抓）/ funding interval 假設 8h / funding cap 從 history max 反推（紅線 2）/ 會計雙重計入 funding（紅線 3 + §3.0）/ carry 偽裝裸 directional bet（carry_share 低）/ bull short-side top-funding squeeze 保險偽裝 carry / cross-sectional N_eff 假性大樣本 / AEG n_independent 把 breadth 誤當 time evidence / survivorship（20 current-liquid 子集）/ multiple-testing K=8 誠實 / bull-only 偽 alpha / horizon 拉長 carry 衰減 vs fee 攤薄 trade-off。

## INCONCLUSIVE 出口路徑
INCONCLUSIVE-A/B → 接更長 funding backfill（V125 retention 1095d 已批）後重跑；診斷與 backfill 可並行。**誠實 caveat（同 trend）**：backfill 給更多 trade 數，對 cross-sectional N_eff（由 funding 橫截面相關結構決定）幫助有限。NO-GO → 誠實收掉 funding-tilt，回 listing fade（路①）。

## 誠實預判（QC）
清成本牆機率 **~20-25%**。失敗模式按可能性：(1) carry 量級不足（~45%，median |F|≈IR floor → NO-GO-C）；(2) horizon 衰減 vs fee 攤薄淨負（~25%）；(3) bull short-side squeeze 偽裝（~15%）；(4) N_eff/power 不足 INCONCLUSIVE（~10%）。仍值得跑：唯一未測逃逸象限 + 資料真升級（逐結算 PIT vs 均值）+ carry 非 graveyard 因子 + informative negative 也有價值。**強烈建議 MIT 先跑 DATA TASK #0+#1（覆蓋 + funding 量級），~1 天可能就 NO-GO-C，省下全 harness 建置。**

## 文獻
- BIS WP 1087 — Crypto carry；CMU Christin et al. — The Crypto Carry Trade；arXiv 2506.08573 — Designing funding rates；MDPI Mathematics 14(2):346 — Two-Tiered funding rate markets。
