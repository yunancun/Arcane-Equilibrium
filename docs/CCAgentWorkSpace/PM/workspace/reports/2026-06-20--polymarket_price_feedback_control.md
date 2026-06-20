# Polymarket Price-Feedback IC Control

## 結論

v274 將 `polymarket_leadlag` 升到 report schema/runner v0.11。核心改動是新增 same-horizon trailing-return control，用來判斷 Polymarket odds delta 是否只是在反應已經發生的 Bybit 價格變動。

這不是 promotion proof，也不是放寬 gate。Candidate review 仍要求 `min_points=30`、overlap-adjusted sample floor、HAC t-stat threshold、BH q-value control。`price_feedback_warning` 只是一個反誤判診斷。

## 為什麼要加

Polymarket 的 implied-probability delta 有可能不是 lead signal，而是市場已經動了之後，Polymarket odds 跟著調整。若不做這個 control，forward IC 可能把「慢半拍追價」誤判成可交易預測力。

v0.11 對每個 joined feature/horizon 保留原 forward return：

- forward target：first kline at/after `t` 到 first kline at/after `t+h`
- trailing control：price at/before `t-h` 到 price at/before `t`

若 trailing-return IC 的絕對值大於或等於 forward IC，且樣本與幅度達診斷門檻，該 cell 標記 `price_feedback_warning=true`。

## Runtime 證據

- Latest report：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T160421Z.json`
- Latest copy：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket latest sha256：`bf22fe98f4d391616a0d86552828618efb486cf97e44193a21016286627b9483`
- Alpha-discovery latest sha256：`41cdcad77a2897a28b57a73cba780c473f73306de784edbbcdac139699feaebe`
- Created：`2026-06-20T16:04:23.022939+00:00`
- Report schema / runner：`polymarket.leadlag_report.v0.11` / `polymarket_leadlag.v0.11`
- Snapshot rows：`13859`
- Delta rows：`15418`
- Feature points / joined rows：`222 / 371`
- Adjusted sample：`14 / 30`
- Remaining：`16`
- Sample-gate ETA：`2026-06-20T19:52:01.378Z`
- Candidate count：`0`
- Pre-gate watchlist count：`2`
- Status：`INSUFFICIENT_SAMPLE`

Price-feedback summary:

- `cells_with_control=32`
- `warning_count=22`
- `max_abs_past_return_ic=1.0`
- Top warnings are `price_target` BTC/ETH/XRP 15m/60m cells where past-return IC dominates forward IC.

Alpha discovery refreshed at `2026-06-20T16:04:43.322682+00:00` and reports `polymarket_leadlag_ic.sample_count=14`, `price_feedback_warning_count=22`, `gate_status=CAPTURING`, action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.

## PM Read

This is useful negative information. The Polymarket lane is gathering real samples, but a large fraction of current cells look more like price-feedback than lead-lag edge. That tells us what not to trust yet: no Polymarket cell should move to candidate review unless it clears the existing sample/HAC/BH gate and does not collapse under this trailing-return control.

The result does not kill the lane. Event/regulatory source-split cells still need full sample. It does make price-target cells especially suspect until they show forward information beyond the prior price move.

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` + `test_polymarket_leadlag_ic_cron_static.py` = 45 passed.
- Mac：`py_compile` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 45 focused tests passed; `py_compile` + `bash -n` + targeted `git diff --check` passed.
- Linux AppleDouble metadata check returned empty.
- Linux v0.11 wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. The runtime smoke used read-only PG SELECT path; no PG table writes, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy mutation, crontab reinstall, or promotion proof.
