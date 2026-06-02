"""多日 trend/momentum edge 證偽優先診斷 harness（Phase 1：fail-fast 早期門檻）。

MODULE_NOTE:
  模塊用途：實作 QC 協議 spec（``docs/CCAgentWorkSpace/QC/workspace/reports/
    2026-06-02--multiday_trend_diagnostic_protocol.md``）的 Phase 1 早期決策樹門檻。
    對「多日 trend 有 edge」抱持懷疑、要求它證明自己；INCONCLUSIVE/NO-GO 是合法
    且最可能的結果，不准 massage 數字製造 GO。
  子模塊：
    - ``stats`` — 純 numpy 統計（Ljung-Box / ADF / KPSS / Jarque-Bera / ARCH-LM /
      PCA effective N），復用 W2 metrics 的 PSR/DSR skew-kurt 公式。
    - ``signals`` — 4 信號族（A TSMOM / B vol-scaled / C MA-cross / D x-sectional），
      每族同時算 leak-free（shift(1) 正式）+ naive（含 current bar，僅診斷）雙軌。
    - ``cost_model`` — 多日成本模型，含 funding 按時間累積（非按交易次數攤薄）。
    - ``pnl`` — per-trade PnL / Sharpe / effective N / 多空 + regime 拆解。
    - ``data_loader`` — read-only PG SELECT（market.klines/funding_rates/
      symbol_universe_snapshots/regime_snapshots）+ rule-based regime + listed_at
      survivorship。
    - ``harness`` — 編排 DATA TASK 1-5 + Step0 + Ljung-Box + leak-free/naive +
      net-Sharpe/cost-edge 門檻，輸出 JSON + markdown artifact。
  依賴：numpy（Linux runtime 已驗 2.4.4）+ psycopg2（連線時延遲 import）。
    **不依賴 scipy / statsmodels**（Linux runtime 缺，故所有統計檢定純 numpy 自實作）。
  硬邊界（研究紅線）：
    - PG **唯讀**：只 SELECT，絕不寫 production 表。結果寫研究 artifact（JSON +
      markdown）。
    - leak-free shift(1) 鐵律：信號只用 C_{t-1} 及更早；禁 rolling 含 current bar。
    - 誠實標所有限制（funding 覆蓋僅 ~58 天 / effective N / regime 組成 /
      survivorship）；不外推全 universe。
"""
