# Polymarket Sample-Gate Clock

## 結論

v270 將 `polymarket_leadlag` 升到 report schema/runner v0.7，新增 `counts.sample_gate_clock`，並把 `sample_gate_status` / `sample_gate_eta_utc` 透傳到 cron status 與 alpha-discovery。候選 gate 未放寬：`candidate_count` 仍要求 `min_points`、overlap-adjusted sample floor、HAC t threshold 與 BH q-value control。

## Runtime 證據

- Linux v0.7 latest：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket sha256：`0eb7c4bdea86f60810f4824d3a0c201b7cbcea67c5077be9ea36a9b8a86c21f2`
- Alpha-discovery sha256：`682c1a278cc9384ccde3680d0ea1024e2b973185728d9befbf5546ec81bfcc4c`
- Created：`2026-06-20T15:03:30.244514+00:00`
- Status：`INSUFFICIENT_SAMPLE`
- Adjusted sample：`10 / 30`
- Remaining：`20`
- Fastest gate-ready ETA：`2026-06-20T19:52:03.862000+00:00`
- Alpha action：`RUN_READ_ONLY_CAPTURE`; ready/probe remains `0`.

Important diagnosis：v269 的早期 watch 沒有延續。`pre_gate_hac_watchlist_count` 從 5 變 0；原 best `other|BTCUSDT|15m` 在第 10 個 adjusted sample 後變成 `ic_pearson=0.12859612566091114`、`t_stat_hac=0.4009494041768312`、`bh_q_value_hac_approx=0.7649526391417382`。這支持「先繼續收樣本，不可基於 9 點 watch 開 probe」。

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` = 31 passed.
- Mac：`test_polymarket_leadlag_ic_cron_static.py` = 9 passed.
- Mac：`py_compile` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 31 + 9 focused tests passed; `py_compile` + `bash -n` passed.
- Linux wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. No PG table writes, no Bybit private/signed/trading call, no engine/API rebuild or restart, no credential/auth/risk/order/strategy mutation, and no promotion proof.
