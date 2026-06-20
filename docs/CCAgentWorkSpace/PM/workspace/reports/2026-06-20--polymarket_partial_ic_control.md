# Polymarket Partial IC Control

## 結論

v275 將 `polymarket_leadlag` 升到 report schema/runner v0.12。核心改動是把 v274 的 same-horizon trailing-return price-feedback control 再往前推一步：每個可控制的 IC cell 會計算 partial/residual IC：

`corr(feature_delta_at_t, residual(forward_return_t_to_t_plus_h ~ trailing_return_t_minus_h_to_t))`

這不是 promotion proof，也不是放寬 gate。Candidate review 仍要求 `min_points=30`、overlap-adjusted sample floor、HAC t-stat threshold、BH q-value control。Partial IC 只是反誤判診斷，用來檢查 raw forward IC 是否主要來自已發生的價格移動。

## 為什麼要加

v0.11 已能標記 odds delta 與 trailing return 的相關性，但仍沒有直接回答一個更嚴格問題：扣除 trailing return 能解釋的 forward-return 部分後，Polymarket odds delta 還剩多少獨立 forward information？

v0.12 對每個有 trailing-return control 的 cell 做單變量 residualization：

- forward target：first kline at/after `t` 到 first kline at/after `t+h`
- trailing control：price at/before `t-h` 到 price at/before `t`
- residual target：`forward_return ~ trailing_return` 的殘差
- partial IC：`corr(mean_delta_prob_yes, residual target)`

若 raw IC 達診斷幅度，但 residualization 後 partial IC 低於絕對門檻或保留比例不足，該 cell 標記 `price_feedback_partial_collapse_warning=true`。

## Runtime 證據

- Latest report：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T161441Z.json`
- Latest copy：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket latest sha256：`ab2620e8edc223583b63bcbc00de94c979fcfb45288dc4513845dd9331fd5322`
- Alpha-discovery latest sha256：`1a78a867e9912fe7a70ec51032f95e1cbd0f3d37dc288e0c98e82d838ee322e0`
- Created：`2026-06-20T16:14:43.328104+00:00`
- Report schema / runner：`polymarket.leadlag_report.v0.12` / `polymarket_leadlag.v0.12`
- Snapshot rows：`14727`
- Delta rows：`16453`
- Feature points / joined rows：`236 / 414`
- Adjusted sample：`15 / 30`
- Remaining：`15`
- Sample-gate ETA：`2026-06-20T19:52:01.632Z`
- Candidate count：`0`
- Pre-gate watchlist count：`3`
- Status：`INSUFFICIENT_SAMPLE`

Price-feedback / partial-control summary:

- `price_feedback_warning_count=22`
- `cells_with_control=46`
- `partial_control_cells=29`
- `raw_to_partial_collapse_count=4`
- `max_abs_partial_ic_controlling_trailing_return=0.726`

Concrete collapse example: `price_target|XRPUSDT|15m` had raw IC around `0.306`, past-return IC around `-0.934`, trailing-forward-return IC around `-0.228`, and partial IC around `0.095`. That is a raw forward IC that largely disappears after controlling for trailing return.

Alpha discovery refreshed at `2026-06-20T16:14:55.332474+00:00` and reports `polymarket_leadlag_ic.sample_count=15`, `price_feedback_warning_count=22`, `price_feedback_partial_collapse_count=4`, `gate_status=CAPTURING`, action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.

## PM Read

This strengthens the negative/diagnostic evidence. Some current raw IC cells are not yet credible lead-lag edge because their apparent signal collapses after residualizing the forward label against the same-horizon trailing price move.

This does not kill the Polymarket lane. It makes the review rule stricter and more honest: future Polymarket candidates must clear sample/HAC/BH gates and survive residual control before they are treated as plausible alpha. Price-target cells remain especially suspect; event/regulatory source-split cells still need full sample.

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` + `test_polymarket_leadlag_ic_cron_static.py` = 46 passed.
- Mac：`py_compile` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 46 focused tests passed; `py_compile` + `bash -n` + targeted `git diff --check` passed.
- Linux AppleDouble metadata check returned empty.
- Linux v0.12 wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. The runtime smoke used read-only PG SELECT path; no PG table writes, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy mutation, crontab reinstall, or promotion proof.
