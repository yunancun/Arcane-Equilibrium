# Operator Note — MM Sample-Gated Cost-Wall Diagnosis

日期：2026-06-20

這批是診斷修正，不是交易變更。

之前 MM cost wall 裡最接近 breakeven 的 live symbol 是 `ARBUSDT`，net `-0.0357bp`，但它只有 `n=1` maker fill。這個數字不能當作盈利路徑。

現在 `recorder_mm_verdict_cron.sh` 會輸出 `sample_gated_cost_wall_summary`，只用通過 sample gate 的 fill_sim cells。最新 runtime：

- MM verdict status-line sha256 `fe2ae9b675b11e4e43ebc8ba4bfbd704e30478db8d9cf18be1293cc310d8a5d5`
- `SAMPLE_GATED_CURRENT_FEE_COST_WALL`
- sample-gated cells = 74
- best cell `LABUSDT` / back / informed_skip, `n=170`
- net `-1.73bp`
- break-even maker fee `1.135bp/side`
- fee reduction needed `0.865bp/side`
- live ARBUSDT row remains diagnostic only because `n=1`

Alpha discovery latest sha256 `05301d674686b2763f122b915a47d7837a36ff5829c22c44abda81d9fc0727ad` still says `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0. MM primary blocker remains feature-family failure; sample-gated cost wall is now the first secondary blocker.

驗證：Mac/Linux focused suite `58 passed`，py_compile、shell syntax、diff-check 和 runtime smoke passed。邊界：source/test/docs + `/tmp/openclaw` artifact/status writes only；沒有 PG write、Bybit private/signed/trading call、engine/API restart、strategy/risk/order/auth mutation。
