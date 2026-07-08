# Demo Order-To-Fill Gap Audit

- Generated: `2026-07-08T10:10:29+00:00`
- Engine modes: `demo`
- Lookback hours: `120`
- Touch window minutes: `15`
- Status: `FILL_FLOW_PRESENT`
- Reason: one or more fills exist for reviewed orders
- Next action: `review_realized_execution_quality_and_markouts`
- Boundary: read-only PG SELECT; no Bybit call, order, config, risk, auth, runtime, schema, Cost Gate, probe, or promotion mutation

## Counts

| metric | value |
|---|---:|
| reviewed_orders | 100 |
| fill_rows | 62 |
| post_only_orders | 54 |
| orders_price_missing | 46 |
| effective_limit_prices_inferred | 12 |
| bbo_touched_no_fill_orders | 16 |
| deep_passive_no_touch_orders | 0 |
| no_touch_orders | 8 |
| no_bbo_coverage_orders | 12 |

## Orders

| ts | symbol | side | tif | status | effective_px | px_source | best_touch_gap_bps | class |
|---|---|---|---|---|---:|---|---:|---|
| 2026-07-08 10:29:00.233000+02:00 | APTUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 10:29:00.053000+02:00 | APTUSDT | Sell | PostOnly | Cancelled | 0.6150000095367432 | orders.price | -17.8541 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 10:19:00.014000+02:00 | APTUSDT | Buy | None | Filled | 0.6195999979972839 | intents.price | None | FILLED |
| 2026-07-08 06:44:55.913000+02:00 | LTCUSDT | Buy | None | Filled | None | None | None | FILLED |
| 2026-07-08 06:44:53.908000+02:00 | LTCUSDT | Buy | PostOnly | Failed | 43.970001220703125 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-08 06:44:00.061000+02:00 | LTCUSDT | Sell | None | PartiallyFilled | 43.5099983215332 | intents.price | -11.4788 | FILLED |
| 2026-07-08 06:40:00.007000+02:00 | SNDKUSDT | Sell | PostOnly | Rejected | 1613.1700439453125 | orders.price | -1.0534 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 04:05:08.699000+02:00 | LINKUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 04:05:08.498000+02:00 | LINKUSDT | Sell | PostOnly | Cancelled | 7.669000148773193 | orders.price | -48.0143 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 04:04:00.031000+02:00 | LINKUSDT | Buy | None | Filled | 7.7220001220703125 | intents.price | -14.2655 | FILLED |
| 2026-07-08 04:01:03.248000+02:00 | DOTUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 03:39:46.032000+02:00 | DOTUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 03:39:45.849000+02:00 | DOTUSDT | Sell | PostOnly | Cancelled | 0.8363999724388123 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-08 03:39:32.926000+02:00 | AVAXUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 03:39:32.740000+02:00 | AVAXUSDT | Sell | PostOnly | Cancelled | 6.520999908447266 | orders.price | -59.4514 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 03:39:00.224000+02:00 | DOTUSDT | Buy | None | Filled | 0.8420000076293945 | intents.price | None | FILLED |
| 2026-07-08 03:39:00.055000+02:00 | AVAXUSDT | Buy | None | Filled | 6.560999870300293 | intents.price | None | FILLED |
| 2026-07-08 02:04:12.966000+02:00 | ATOMUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 02:04:12.804000+02:00 | FILUSDT | Buy | PostOnly | Working | 0.7715277075767517 | orders.price | 30.6537 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-08 02:04:12.321000+02:00 | ATOMUSDT | Sell | PostOnly | Cancelled | 1.5679999589920044 | orders.price | -16.5544 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 02:01:21.932000+02:00 | AVAXUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-08 02:01:21.759000+02:00 | SUIUSDT | Buy | PostOnly | Working | 0.7259733080863953 | orders.price | 12.7485 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-08 02:01:21.262000+02:00 | AVAXUSDT | Sell | PostOnly | Cancelled | 6.638999938964844 | orders.price | -67.325 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-08 02:00:00.685000+02:00 | BTCUSDT | Buy | PostOnly | Working | 63269.1171875 | orders.price | 0.5662 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-08 02:00:00.512000+02:00 | AVAXUSDT | Buy | PostOnly | PartiallyFilled | 6.679314136505127 | orders.price | 1.0267 | FILLED |
| 2026-07-08 02:00:00.033000+02:00 | ATOMUSDT | Buy | PostOnly | Filled | 1.5704280138015747 | orders.price | -1.4521 | FILLED |
| 2026-07-07 09:38:46.124000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 09:38:45.951000+02:00 | BTCUSDT | Sell | PostOnly | Cancelled | 63092.8984375 | orders.price | -0.8719 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-07 09:38:00.011000+02:00 | BTCUSDT | Buy | None | Filled | 63075.8984375 | intents.price | None | FILLED |
| 2026-07-07 05:00:53.872000+02:00 | VANRYUSDT | Buy | PostOnly | Cancelled | 0.008964999578893185 | orders.price | -34.6984 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-07 04:52:13.248000+02:00 | UNIUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 04:52:13.073000+02:00 | NEARUSDT | Buy | PostOnly | Cancelled | 2.0415563583374023 | orders.price | 10.0002 | POST_ONLY_REJECT_OR_CROSS_NO_FILL |
| 2026-07-07 04:52:12.896000+02:00 | UNIUSDT | Sell | PostOnly | Cancelled | 3.114000082015991 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-07 03:14:54.253000+02:00 | ICPUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 03:14:54.075000+02:00 | UNIUSDT | Buy | PostOnly | Filled | 3.139857053756714 | orders.price | 32.1998 | FILLED |
| 2026-07-07 03:14:53.591000+02:00 | ICPUSDT | Sell | PostOnly | Cancelled | 2.183000087738037 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-07 03:10:44.619000+02:00 | ICPUSDT | Buy | PostOnly | Filled | 2.225771903991699 | orders.price | 5.5146 | FILLED |
| 2026-07-07 03:10:44.441000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 02:03:28.764000+02:00 | OPUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 02:03:28.586000+02:00 | ADAUSDT | Buy | PostOnly | Cancelled | 0.18621359765529633 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-07 02:03:28.382000+02:00 | OPUSDT | Sell | PostOnly | Cancelled | 0.10670000314712524 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-07 02:02:49.527000+02:00 | SUIUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-07 02:02:49.353000+02:00 | BTCUSDT | Buy | PostOnly | Filled | 63956.578125 | orders.price | 4.442 | FILLED |
| 2026-07-07 02:02:49.160000+02:00 | SUIUSDT | Sell | PostOnly | Cancelled | 0.7455999851226807 | orders.price | -49.3796 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-07 02:00:00.351000+02:00 | AVAXUSDT | Buy | PostOnly | Cancelled | 6.930062770843506 | orders.price | -5.866 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-07 02:00:00.177000+02:00 | OPUSDT | Buy | PostOnly | Filled | 0.10706283152103424 | orders.price | 2.537 | FILLED |
| 2026-07-07 02:00:00.001000+02:00 | SUIUSDT | Buy | PostOnly | Filled | 0.748850405216217 | orders.price | 1.9973 | FILLED |
| 2026-07-06 23:23:30.340000+02:00 | FILUSDT | Buy | None | Filled | None | None | None | FILLED |
| 2026-07-06 23:22:00.130000+02:00 | FILUSDT | Buy | PostOnly | Cancelled | 0.7990000247955322 | orders.price | 27.4585 | SELF_CANCEL_NO_TOUCH |
| 2026-07-06 23:14:58.267000+02:00 | DOGEUSDT | Buy | None | Filled | None | None | None | FILLED |
| 2026-07-06 23:14:58.084000+02:00 | DOGEUSDT | Buy | PostOnly | Cancelled | 0.07824999839067459 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-06 23:12:33.852000+02:00 | BNBUSDT | Buy | None | Filled | None | None | None | FILLED |
| 2026-07-06 23:12:33.646000+02:00 | BNBUSDT | Buy | PostOnly | Cancelled | 595.2999877929688 | orders.price | -64.2432 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-06 23:12:00.356000+02:00 | FILUSDT | Sell | None | Filled | 0.8075000047683716 | intents.price | None | FILLED |
| 2026-07-06 23:12:00.181000+02:00 | BNBUSDT | Sell | None | Filled | 589.3499755859375 | intents.price | None | FILLED |
| 2026-07-06 23:12:00.006000+02:00 | DOGEUSDT | Sell | None | Filled | 0.07800500094890594 | intents.price | 5.7723 | FILLED |
| 2026-07-06 14:06:57.347000+02:00 | ARBUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-06 14:06:57.163000+02:00 | ARBUSDT | Sell | PostOnly | Cancelled | 0.07604999840259552 | orders.price | -58.8237 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-06 14:05:00.125000+02:00 | ARBUSDT | Buy | None | Filled | 0.07618000358343124 | intents.price | None | FILLED |
| 2026-07-06 02:04:05.560000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-06 02:02:52.713000+02:00 | TRXUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-06 02:02:52.538000+02:00 | TRXUSDT | Sell | PostOnly | Cancelled | 0.3285199999809265 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-06 02:02:26.047000+02:00 | DOTUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-06 02:02:25.819000+02:00 | DOTUSDT | Sell | PostOnly | Cancelled | 0.876800000667572 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-06 02:00:35.692000+02:00 | NEARUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-06 02:00:35.520000+02:00 | DOTUSDT | Buy | PostOnly | Filled | 0.8797193765640259 | orders.price | 0.9164 | FILLED |
| 2026-07-06 02:00:35.349000+02:00 | NEARUSDT | Sell | PostOnly | Cancelled | 2.009700059890747 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-06 02:00:00.361000+02:00 | TRXUSDT | Buy | PostOnly | Filled | 0.3288608193397522 | orders.price | 6.3567 | FILLED |
| 2026-07-06 02:00:00.188000+02:00 | NEARUSDT | Buy | PostOnly | Filled | 2.0131349563598633 | orders.price | 6.28 | FILLED |
| 2026-07-06 02:00:00.014000+02:00 | BTCUSDT | Buy | PostOnly | Filled | 63555.28125 | orders.price | 0.8525 | FILLED |
| 2026-07-05 13:30:28.271000+02:00 | BCHUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 13:29:58.178000+02:00 | BCHUSDT | Buy | None | PartiallyFilled | 237.8000030517578 | intents.price | None | FILLED |
| 2026-07-05 13:27:27.290000+02:00 | POLUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 02:31:05.151000+02:00 | BCHUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 02:20:55.611000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 02:20:55.431000+02:00 | BTCUSDT | Sell | PostOnly | Cancelled | 63014.1015625 | orders.price | 0.6668 | POST_ONLY_REJECT_OR_CROSS_NO_FILL |
| 2026-07-05 02:01:55.720000+02:00 | BCHUSDT | Buy | PostOnly | Working | 235.2145538330078 | orders.price | 7.8779 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-05 02:01:55.544000+02:00 | LINKUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 02:01:18.400000+02:00 | BTCUSDT | Buy | PostOnly | Working | 62995.2421875 | orders.price | 0.7711 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-05 02:01:18.221000+02:00 | OPUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-05 02:00:00.363000+02:00 | POLUSDT | Buy | PostOnly | Working | 0.07337655127048492 | orders.price | 19.5115 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-05 02:00:00.185000+02:00 | OPUSDT | Buy | PostOnly | Filled | 0.10745743662118912 | orders.price | 2.0993 | FILLED |
| 2026-07-05 02:00:00.002000+02:00 | LINKUSDT | Buy | PostOnly | PartiallyFilled | 7.9890031814575195 | orders.price | 1.2476 | FILLED |
| 2026-07-04 07:21:44.233000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 07:21:44.014000+02:00 | BTCUSDT | Sell | PostOnly | Cancelled | 62476.5 | orders.price | -1.0883 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-04 07:21:00.035000+02:00 | BTCUSDT | Buy | None | Filled | 62489.0 | intents.price | -0.176 | FILLED |
| 2026-07-04 03:45:41.279000+02:00 | ATOMUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 03:45:41.108000+02:00 | BCHUSDT | Buy | PostOnly | Working | 223.37640380859375 | orders.price | 146.6077 | PASSIVE_LIMIT_NOT_TOUCHED |
| 2026-07-04 03:45:40.933000+02:00 | ATOMUSDT | Sell | PostOnly | Cancelled | 1.586899995803833 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
| 2026-07-04 03:39:45.681000+02:00 | SUIUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 03:39:45.508000+02:00 | ATOMUSDT | Buy | PostOnly | Filled | 1.5869115591049194 | orders.price | -1.3333 | FILLED |
| 2026-07-04 03:39:45.025000+02:00 | SUIUSDT | Sell | PostOnly | Cancelled | 0.757099986076355 | orders.price | -34.2242 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-04 03:29:48.616000+02:00 | FILUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 03:29:48.444000+02:00 | SUIUSDT | Buy | PostOnly | Filled | 0.7599892616271973 | orders.price | 2.7721 | FILLED |
| 2026-07-04 03:29:47.961000+02:00 | FILUSDT | Sell | PostOnly | Cancelled | 0.7921000123023987 | orders.price | -50.2448 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-04 03:09:46.663000+02:00 | BTCUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 03:09:46.493000+02:00 | FILUSDT | Buy | PostOnly | Filled | 0.7953038811683655 | orders.price | 15.0172 | FILLED |
| 2026-07-04 03:09:46.257000+02:00 | BTCUSDT | Sell | PostOnly | Cancelled | 62485.69921875 | orders.price | -1.2003 | BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED |
| 2026-07-04 02:43:13.405000+02:00 | INJUSDT | Sell | None | Filled | None | None | None | FILLED |
| 2026-07-04 02:43:13.236000+02:00 | UNIUSDT | Buy | PostOnly | Cancelled | 3.2022945880889893 | orders.price | None | NO_BBO_COVERAGE_FOR_TOUCH_WINDOW |
