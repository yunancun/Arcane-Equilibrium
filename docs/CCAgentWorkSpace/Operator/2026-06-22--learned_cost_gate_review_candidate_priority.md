# 2026-06-22 — Learned Cost Gate Review Candidate Priority

本輪確認 demo-learning 路徑已經不只是「準備安裝 stack」。一次 artifact-only Cost Gate learning refresh 從 blocked signals 中產生了具體候選。

當前候選：

- side-cell: `ma_crossover|ETHUSDT|Sell`
- blocked outcomes: `22419`
- review status: `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`
- wrongful block score: `75.49272112494981`
- net cost cushion bps: `37.746360562474905`

alpha worklist 現在顯示：

- top task: `operator_probe_review`
- blocker: `cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review`
- objective: `operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe`
- next trigger: `operator_review_blocked_outcome_scorecard_before_demo_probe_authority`
- requires operator authorization: `true`
- runtime mutation required: `false`

已驗證：

- Mac alpha/worklist tests `65 passed`
- Linux alpha/worklist tests `65 passed`
- Linux artifact-only Cost Gate learning refresh passed
- Linux artifact-only alpha smoke passed
- source commits `51e3e520` + `9768b3dd` pushed with `[skip ci]`

這不是：

- cron install
- Cost Gate lowering
- probe/order authority
- PG write/schema migration
- Bybit private/signed/trading call
- deploy/rebuild/restart
- env/auth/risk/order/strategy mutation
- promotion proof

下一個 operator action 是 review blocked-outcome scorecard。只有另行批准，才進入 bounded demo probe；probe 後仍需要 matched-control 和 execution-realism review。
