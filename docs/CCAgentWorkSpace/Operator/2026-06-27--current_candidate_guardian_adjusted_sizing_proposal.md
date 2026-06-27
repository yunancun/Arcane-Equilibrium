# Current Candidate Guardian-Adjusted Sizing Proposal

狀態：`DONE_WITH_CONCERNS`。

已按你的修正處理：風控參數以 GUI/Rust RiskConfig 為準，GUI `10.0%` 不是 `10 USDT`。

- Runtime read-only `get_risk_config(engine=demo)` 確認 `per_trade_risk_pct=0.1`，也就是 GUI 顯示的 `10.0%`。
- `position_size_max_pct=25.0`，對目前 Demo equity `9552.43426257` 代表 max-single-position budget `2388.10856564 USDT`。
- 目前 per-order GUI cap 仍是 `955.24342626 USDT`。
- local/bounded `10 USDT` 不得再作為全局單筆風控權威。

本輪新增 helper 會重新驗證 GUI cap lineage，拒絕舊 `cap_usdt=10.0` 這類非 GUI 權威輸入。正式 no-order proposal：

- Artifact: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T051233Z/current_candidate_guardian_adjusted_sizing_proposal.json`
- sha256: `6fb60dfab8967209910aa8ffa34148abe9a24ac0b6b18cf954f63b12692d1a29`
- Candidate: `grid_trading|AVAXUSDT|Sell`
- Guardian: `CAUTIOUS`
- Guardian multiplier: `0.7`
- Guardian-adjusted cap: `668.67039838 USDT`
- Original: `145.7 AVAX / 954.6264 USDT`
- Proposed: `102.0 AVAX / 668.304 USDT`

Runtime source 已同步到 `b51f7602192b5f312c231ddbb0e16a34112746b7`，crontab expected-head pin 11 處已更新，沒有重啟服務。

仍然不能下單。下一步必須先有真實 current-candidate Demo Decision Lease，並讓 Guardian gate 對 proposed reduced sizing 通過；之後才可做 fresh actual-admission BBO。沒有 Cost Gate lowering、沒有 risk expansion、沒有 live/mainnet、沒有 order/proof。
