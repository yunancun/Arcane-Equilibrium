# Live/Demo GUI 今日 PnL 口徑修正

Live GUI 顯示約 `-45.45` 今日淨虧損的原因是前端把 session/lifetime 累計手續費 bucket 混進「今日」欄位。Linux DB 只讀驗證顯示 LiveDemo 今日 DB 當地日 net 為 `+1.578890`，不是 `-45.45`。

已修正：
- 後端 canonical metrics 新增 `net_pnl_today`
- Live tab 與 console Live 側欄都改讀同一後端今日 metric
- Demo/Live tab endpoint contract 增加靜態測試，避免前端跨讀錯 backend

驗證：
- performance/trading true metrics tests: 10 passed
- static GUI contract tests: 50 passed
- `trading_true_metrics.py` compile PASS

邊界：未 restart、未 rebuild、未改 DB migration、未改 live auth、未改策略/風控。
