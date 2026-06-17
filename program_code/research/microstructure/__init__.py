"""program_code.research.microstructure — Campaign-8 微結構 leak-free 研究 harness（productionized）。

MODULE_NOTE
模塊用途：
  把 campaign-8 在 /tmp 驗證過的「microstructure lead」（OFI@10s beta-clean 信號）
  固化進 repo，提供「一條可重現命令」做 CP-1 / CP-2 / CP-3 re-verification。
  核心結論變數：OFI@10s residual-IC（非 raw-IC）+ 非重疊 t-stat（Fisher-z）+
  per-symbol same-sign fraction + book-imb@30s。

主要檔/函數：
  - core.py：leak-free 純函數核心（clean_obtop / build_grid / ofi / fwd /
    fisher_t / assemble_frames / pooled_ic_t / per_symbol_same_sign）。0 DB / 0 網路。
  - data_loader.py：read-only PG loader（PG* libpq env 或 OPENCLAW_DATABASE_URL，
    禁硬編 trading_admin）。只 SELECT market.trades / market.ob_top / market.l1_events，0 寫入。
  - harness.py：thin runner CLI（--hours N 或 --since/--until），輸出單一 report JSON。
  - mm_sizing_run.py：GROSS 做市 spread-capture pool sizing（spread × flow，未扣逆選）。
  - fill_sim.py：queue-position fill-simulation（CP-3 go/no-go 工具）。讀 l1_events 做
    事件驅動掛單成交模擬,量 fill-conditional adverse selection（beta-residual）+ naive vs
    informed-skip NET 對照。誠實單窗=偵察讀數非裁決。

leak-free 保證（與 campaign8b/sharpen_ofi.py 逐位元對齊，不得偷偷弱化）：
  - 特徵窗 [t-w, t) 嚴格 < t；預測窗 [t, t+h) 嚴格在特徵之後（半開不重疊）。
  - bar 對齊後 book_imb 再 shift(1) 做雙保險（asof-backward 之上額外 leak guard）。
  - clean_obtop 硬過濾：best_ask>best_bid AND bid_size>0 AND ask_size>0（NON-NEGOTIABLE，
    壞 tick 不可拿來算 imbalance；campaign-8 v1 ob_top 14.7% 壞 tick）。
  - per-symbol BTC-beta 殘差化：leak-free rolling 30min beta，cov/var 各 shift(1)
    後相除（去 down-beta 偽裝，只留 idiosyncratic）。
  - 非重疊取樣 stride = ceil(max(w,h)/grid)：特徵窗與預測窗在保留樣本間皆不重疊；
    pooled Spearman IC + Fisher-z t 用「非重疊 n」（誠實，不騎邊界自相關）。
  - native exchange side label 決定 OFI 符號（Buy=+qty / Sell=-qty）。

硬邊界：
  - $0 read-only：只 SELECT market.trades / market.ob_top / market.klines；
    只寫自己的 report artifact；0 order / 0 auth / 0 lease / 0 risk / 0 寫 market 表。
  - 2h ≈ 1 個 regime 樣本 → 任何輸出都帶 caveat，禁 PBO/DSR/Sharpe，禁 GO/NO-GO。
    真結論須 recorder-v2 full-L1 + 多週 regime 覆蓋（CP-1/CP-2/CP-3）。
"""
