# AEG-S3 Empirical Execution Realism + Gate-B Watch

Date: 2026-06-12
Owner: PM
Code checkpoint: `c35f8425` (`[skip ci] Add AEG-S3 event execution realism adapter`)

## 結論

Empirical execution realism 的 artifact-only 接線已完成。`listing_fade` /
`funding_revive` 這類單 symbol event candidate 現在可吃 execution-observations JSONL，
按 `sample_id` 或 `(symbol, sample_ts)` 回配候選事件，聚合成既有
`aeg_execution_realism` gate 所需輸入，再由原 gate 重算 PASS/FAIL。`oi_delta`
basket evidence 沒有單一 event symbol，仍 fail-closed。

Gate-B 不應無意義乾等。現時官方公告頁 / API 最近一批 `new_crypto` + `Derivatives`
是 2026-06-09 的 AAOIUSDT / IRENUSDT / ONDSUSDT / QNTXUSDT / CTRUSDT，公告語義均為
已 open / 已 listed，不是可捕捉的未來 PreLaunch transition。live
`instruments-info?category=linear&status=PreLaunch` 目前只回 `BPUSDT`，其
`launchTime=2026-03-16T05:45:14Z`，`preListingInfo.curAuctionPhase=ContinuousTrading`，
不是今日新窗口。可執行候選是：繼續盯 BPUSDT conversion-to-standard 公告，或下一個
新的 Pre-Market / PreLaunch listing 公告。

## 接線設計

新增：

- `helper_scripts/research/aeg_s3_event_execution_realism/__init__.py`
- `helper_scripts/research/aeg_s3_event_execution_realism/builder.py`
- `helper_scripts/research/aeg_s3_event_execution_realism/harness.py`
- `helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py`

輸入：

- AEG-S3 candidate evidence JSON：支援 `listing_fade` / `funding_revive` 單 symbol
  event samples。
- execution-observations JSONL：每 row 可帶 `sample_id` 或 `symbol + sample_ts`，
  加上 `evidence_source_tier`、`order_style`、fee、slippage、maker fill、
  adverse selection、latency、participation、capacity、order availability。

Fail-closed 規則：

- unmatched observation 不進樣本，寫入 summary reject count。
- `candidate_id` / `parameter_cell_id` mismatch 不進樣本。
- matched sample `<30` 由既有 `aeg_execution_realism` 打回。
- 非 empirical source tier、缺 fill/slippage/adverse/latency/capacity/availability
  仍由既有 gate 打回。
- `oi_delta` basket evidence 直接 unsupported，不拆 fake symbol。

## Gate-B 時間與前提

回答「要等多久」要分兩層：

1. 單次 Gate-B attempt：一旦有真 PreLaunch/listing/conversion 窗口，隔離 probe 的計劃
   run length 是 24h。雖然 markout 最長只到 +300s，24h 目的是覆蓋 phase transition
   稀有與公告時間誤差；無 transition 則 `INCONCLUSIVE_NO_TRANSITION`。
2. 日曆等待：不是固定從今天開始等 24h，而是等下一個有效窗口出現。有效窗口可能來自
   `new_crypto` 公告中的 Pre-Market listing / conversion 公告，或 live
   `instruments-info` 出現新的 `PreLaunch` symbol 且接近 conversion/Trading transition。

可用 artifact 的前提：

- Bybit USDT linear instrument 真的在 isolated probe 期間發生 PreLaunch / pre-market
  conversion / Trading transition。
- Probe 是獨立 public REST/WS 進程，不接 production WS/scanner/strategy/DB/order/auth。
- BTC control publicTrade liveness healthy；無 handler poison / subscribe reject / reconnect loop。
- `capture_lag.jsonl` 對每個 transition symbol 有首筆 publicTrade；`capture_lag_ms <= 300000`
  才是 PASS_CAPTURE。
- `markout.jsonl` 有 +30/+60/+300s row，`listing_fade` producer 才能形成 event samples。
- 之後還需要 empirical execution observations `>=30` matched rows，execution realism 才可能 PASS。

## 公告/市場檢查

使用來源：

- Bybit 公告頁：`https://announcements.bybit.com/zh-MY/?category=new_crypto`
- Bybit 官方公告 API 文件：`GET /v5/announcements/index`
- Bybit public market REST：`GET /v5/market/instruments-info?category=linear&status=PreLaunch&limit=1000`
- Bybit Pre-Market Perpetual FAQ：transition 時間不固定，需 spot market 足夠成熟，且不保證必轉 standard perpetual。

2026-06-12 檢查結果：

- 最新 derivatives new-listing 公告：2026-06-09 `AAOIUSDT`、`IRENUSDT`、`ONDSUSDT`、
  `QNTXUSDT`、`CTRUSDT`；語義是已 listed/open，不是 Gate-B future trigger。
- 歷史最近 Pre-Market / conversion 公告：`MEGAUSDT` convert 2026-04-30、
  `CHIPUSDT` convert 2026-04-21、`BPUSDT` Pre-Market listing 2026-03-16。
- live PreLaunch：`BPUSDT` only；`curAuctionPhase=ContinuousTrading`，等待的是 future
  conversion-to-standard，而不是 call-auction opening。

現有 `helper_scripts/canary/bybit_announcement_sentinel.py` 已是 30min alert-only
公告哨兵，2026-06-12 runtime partial 報告記錄 cron installed（`7,37 * * * *`）。
本次不改 active cron script，避免把研究調度變成未請求 runtime 行為改動；下一個
Gate-B 行動由 sentinel alert 或手動 API check 觸發。

## 驗證

Mac:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py \
  helper_scripts/research/tests/test_aeg_execution_realism.py \
  helper_scripts/research/tests/test_aeg_s3_event_breadth.py \
  helper_scripts/research/tests/test_aeg_s3_matrix_inputs.py \
  helper_scripts/research/tests/test_aeg_s3_funding_revive.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_aeg_breadth_ladder.py -q
```

Result: `88 passed in 2.00s`.

Static / compile:

- `python3 -m compileall -q ...` OK.
- forbidden-route `rg` against new package: no hits.
- `git diff --check`: OK.

Linux:

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_event_execution_realism.py -q'
```

Result: `4 passed in 0.06s`.

No CI, no deploy, no rebuild/restart, no DB/auth/risk/trading mutation.

## 下一步

1. 主線 Gate-B：等公告哨兵或手動 API check 出現新的 Pre-Market / conversion / fresh
   PreLaunch trigger，再啟動 isolated 24h `aeg_gate_b_probe`；不要從無事件狀態硬跑 24h。
2. 並行 execution realism：等有 real demo/live-demo/replay calibrated observations 後，收集
   `>=30` matched JSONL rows，跑 `aeg_s3_event_execution_realism.harness`，再餵
   robustness matrix。
3. 已有 funding_revive / oi_delta formal matrices 仍 non-promotable：DSR/PBO/PSR 與 execution
   evidence 未達標前，不作 promotion proof。
