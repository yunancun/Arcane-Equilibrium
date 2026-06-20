# Polymarket Source-Split IC View

## 結論

v273 將 `polymarket_leadlag` 升到 report schema/runner v0.10。核心改動是保留既有 aggregate `event_reg` feature view，同時新增 `event_reg_direct` 與 `event_reg_macro` source-split IC cells。

這不是 promotion proof，也不是放寬 gate。Candidate review 仍要求 `min_points=30`、overlap-adjusted sample floor、HAC t-stat threshold、BH q-value control。

## 為什麼要拆

v0.9 已經把 generic macro/regulatory `event_reg` rows 映射到 BTC/ETH proxy series，但這些 rows 會被混進同一個 `event_reg|symbol|horizon` cell。這會把兩個不同假設綁在一起：

- `event_reg_direct`：直接提到 BTC/ETH/SOL/XRP 的資產事件。
- `event_reg_macro`：CPI、Fed、Tether、Coinbase SEC、ETF/regulation 等 generic crypto-wide macro/reg proxy。

v0.10 讓兩者可以獨立接受 IC/HAC/BH 檢驗，同時保留 aggregate cell 以觀察 combined-flow 是否更好。

## Runtime 證據

- Latest report：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T155005Z.json`
- Latest copy：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket latest sha256：`1f85dfb82789d3fd158272b8def4c0762755907e4ffbef7643243ba19e03b53f`
- Alpha-discovery latest sha256：`d609117f2c4f44c91643e27cddaddbca37c219c44413fd04c3c1a9f08d6beaf8`
- Created：`2026-06-20T15:50:07.824555+00:00`
- Report schema / runner：`polymarket.leadlag_report.v0.10` / `polymarket_leadlag.v0.10`
- Snapshot rows：`13001`
- Delta rows：`14393`
- Feature points / joined rows：`208 / 341`
- Feature bucket counts：`event_reg=40`, `event_reg_direct=40`, `event_reg_macro=28`, `other=44`, `price_target=56`
- Feature view counts：`aggregate=140`, `source_split=68`
- Adjusted sample：`13 / 30`
- Remaining：`17`
- Sample-gate ETA：`2026-06-20T19:52:02.188Z`
- Candidate count：`0`
- Pre-gate watchlist count：`0`
- Status：`INSUFFICIENT_SAMPLE`

Alpha discovery refreshed at `2026-06-20T15:50:28.327932+00:00` and reports `polymarket_leadlag_ic.sample_count=13`, split feature counts in detail, `gate_status=CAPTURING`, action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` + `test_polymarket_leadlag_ic_cron_static.py` = 43 passed.
- Mac：`py_compile` + `compileall` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 43 focused tests passed; `py_compile` + `bash -n` + targeted `git diff --check` passed.
- Linux v0.10 wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. The runtime smoke used read-only PG SELECT path; no PG table writes, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy mutation, crontab reinstall, or promotion proof.
