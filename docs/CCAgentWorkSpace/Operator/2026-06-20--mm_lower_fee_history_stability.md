# Operator Note — MM Lower-Fee History Stability

日期：2026-06-20

這批是 MM lower-fee history 診斷，不是交易變更。

最新 runtime 結論：

- Fill-sim history scorecard sha256 `7dbeb78fb528a8ed4a50710d102308bc77b2ff2cc57f38e0a45ea07e727ecaef`
- MM latest status-line sha256 `9d5a3c3ca7c1f28fceb5084a5dab8a4282222cb9ecce4b4b2fb6718994ddac4e`
- Alpha discovery latest sha256 `4efcd2f915a4de5913a3b1781a6051e45f7a71b4b479daa03e8a2f5657609399`
- `lower_fee_break_even_stability_status=LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT`
- lower-fee break-even windows `3`
- repeated lower-fee keys `11`
- distinct dates only `["2026-06-20"]`

Operator implication：there are repeated same-day lower-fee MM candidates, but this is not cross-date/cross-regime proof. Do not treat lower-fee history as strategy/probe/promotion authority yet.

Next useful trigger：let daily fill_sim history accumulate independent dates. Revisit only after repeated lower-fee break-even keys survive across distinct days/regimes, then combine with real fee eligibility and CP-3 review.

驗證：Mac/Linux fill_sim history tests `7 passed`，alpha focused tests `25 passed`，cron static `11 passed`，py_compile、shell syntax、diff-check、MM verdict smoke、alpha discovery smoke passed。邊界：source/test/docs + `/tmp/openclaw` artifact/status writes only；沒有 PG write、Bybit private/signed/trading call、engine/API restart、strategy/risk/order/auth mutation。
