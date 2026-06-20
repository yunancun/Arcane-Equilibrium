# Polymarket Wide-Symbol Universe

## 結論

v271 將 `polymarket_leadlag` 升到 report schema/runner v0.8，並把預設 symbol universe 從 `BTCUSDT,ETHUSDT` 擴到 `BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT`。這修正的是證據迴路過窄：Polymarket v2 query set 已經抓到 Solana/XRP 事件，但 IC cron 之前只分析 BTC/ETH。

候選 gate 未放寬：`min_points=30`、overlap-adjusted sample floor、HAC t threshold、BH q-value control、alpha-discovery `RUN_READ_ONLY_CAPTURE` 邏輯都不變。

## Same-Data 對照

- BTC/ETH baseline artifact：`/tmp/openclaw/research/polymarket_leadlag_experiments/polymarket_leadlag_btceth_baseline_20260620T151304Z.json`
- BTC/ETH baseline sha256：`a042a4f8ac78cc6f9da7228801fc85e1e6e653170d9d266c1dd545b3b42092a0`
- Wide-symbol artifact：`/tmp/openclaw/research/polymarket_leadlag_experiments/polymarket_leadlag_wide_symbols_20260620T151022Z.json`
- Wide-symbol sha256：`7c9b2a7443af8d3f9f5dceceba83d4b18c49ff4218171f869b9aa2ed10647a55`

Both runs used `snapshot_rows=11285`.

| Run | delta_rows | feature_points | joined_rows | max_overlap_adjusted_ic_points |
|---|---:|---:|---:|---:|
| BTC/ETH only | 4643 | 60 | 114 | 11 |
| BTC/ETH/SOL/XRP | 5715 | 120 | 190 | 11 |

Read：擴 universe 不是等待另一個 label 成熟造成的假象；同一批 snapshot 上它多拿到 1072 delta rows 與 76 joined rows。這是把樣本牆向前推的實際改動。

## Runtime 證據

- Latest report：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket latest sha256：`350a689a62ce688a1b1d3bd226f43165fbe9bddc2bc2a0a7f73cae124cd9b5a9`
- Alpha-discovery latest sha256：`3ade420bc5c20aa671d0a7772d79875446ae937fc3c71c80f03c407804f4d3d3`
- Created：`2026-06-20T15:12:20.333967+00:00`
- Symbols：`BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT`
- Status：`INSUFFICIENT_SAMPLE`
- Adjusted sample：`11 / 30`
- Remaining：`19`
- Sample-gate ETA：`2026-06-20T19:52:01.390Z`
- Candidate count：`0`
- Pre-gate watchlist count：`1`
- Best watch：`event_reg|XRPUSDT|60m`, floor `2`, gap `28`, IC `-0.6161628604153603`, HAC t `-5.002351854306203`, BH q `0.000010194318196581281`.

The XRP watch is diagnostic-only and blocked by sample floor. It may decay like the v269 BTC watch; it is evidence to keep collecting, not probe authority.

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` = 31 passed.
- Mac：`test_polymarket_leadlag_ic_cron_static.py` = 9 passed.
- Mac：`py_compile` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 31 + 9 focused tests passed; `py_compile` + `bash -n` passed.
- Linux v0.8 wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. The runtime smoke used read-only PG SELECT path; no PG table writes, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy mutation, crontab reinstall, or promotion proof.
