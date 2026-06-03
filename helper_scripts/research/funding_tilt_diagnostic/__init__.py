"""Funding-tilt / 多日 funding carry edge 證偽優先診斷 harness。

MODULE_NOTE:
  模塊用途：實作 QC 協議 spec（``docs/CCAgentWorkSpace/QC/workspace/reports/
    2026-06-03--funding_tilt_carry_diagnostic_protocol.md``）的 funding 維度
    證偽優先診斷。對「perp-only directional funding-tilt 有扣成本後 edge」抱持
    懷疑、要求它證明自己；NO-GO / INCONCLUSIVE / regime-bet 是合法且（QC 預判）
    最可能的結果，不准 massage 數字製造 GO。
  子模塊：
    - ``data_loader`` — read-only PG SELECT：canonical run-versioned
      ``research.alpha_funding_rates_history``（固定 run_id 只讀它）+
      ``market.klines`` timeframe='1d'（open-to-open 執行價）+ listed_at
      survivorship；per-symbol 從 funding_ts 間距推 interval（NULL 不假設 8h）；
      rule-based regime（expanding/prior-365 vol tercile，**修 trend full-sample
      cross-section leak**）。
    - ``signals`` — 2 信號族：(A) cross-sectional funding-tilt tertile long-short
      （tiltscore=過去 L 結算已實現 funding 均值，L∈{3,9,21}）；(B) time-series
      funding-extreme（per-symbol，80th pct expanding PIT）。**強制雙軌 naive/
      leak-free 對照**（funding 嚴格 `< entry_open_ts − ε`）。
    - ``cost_model`` — 會計約定 §3.0：`net = gross_price + funding_pnl −
      (fee+slip)`，funding_pnl 為**獨立項**（不混入 cost），逐結算對齊。
    - ``pnl`` — open-to-open trade 構造 + H_min 變體 + **per-leg（long/short）
      funding_pnl + gross_price + carry_share 分解**（MIT 強制：短腿擠壓不可被
      aggregate 正 net 藏住）。
    - ``stats`` — 純 numpy 統計（funding persistence Ljung-Box / HAC funding-tilt
      forward / 兩個 N_eff：price-return PCA + funding-tiltscore PCA / JB / ARCH）
      + 復用 ``lib/stats_common``（PSR/DSR(K=8)/PBO/block bootstrap）。
    - ``harness`` — 編排 DATA TASK 0-5 + Step0 + leak/naive + cost + 統計 +
      §4.5 horizon-vs-cost-share 掃描 + §4b regime split + 決策樹，輸出 JSON +
      markdown artifact。
  依賴：numpy（Linux runtime 已驗 2.4.4）+ psycopg2（連線時延遲 import）+
    ``lib/stats_common``（純 stdlib）。**不依賴 scipy / statsmodels**。
  硬邊界（研究紅線）：
    - PG **唯讀**：只 SELECT，絕不寫 production 表。結果寫研究 artifact。
    - 紅線 1：demo 無 spot lending → perp-only directional（非 delta-neutral）。
    - 紅線 2：funding cap SSOT=instruments-info `upperFundingRate`，禁從 history
      max 反推（本 harness 信號不依賴 cap，用已實現 funding 排序）。
    - 紅線 3：funding 雙面會計 §3.0，funding_pnl 單獨一項不重複計入。
    - leak-free 鐵律：funding 嚴格 `< entry_open_ts − ε`；強制雙軌 naive 對照。
    - K 鎖 8（K_A=3 + K_B=1）× 2 持有期；偷加 grid 不更新 K → 自檢抓到。
    - 誠實標所有限制（survivor-cohort / bull-heavy 72.4% / N_eff×2）；不外推。
"""
