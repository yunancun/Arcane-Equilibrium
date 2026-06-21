# Cost-Gate Reject Materializer

## 結論

這次不是再加一層報表，而是補上 data loop 的實際缺口：

PG 裡已經有很多 demo Cost Gate rejects，但 learning ledger 還未必有逐條 rows。新增的 `reject_materializer.py` 可以把這些 PG rejects 轉成 existing learning ledger 格式，讓後續 outcome refresh/review 能逐條評估「被 Cost Gate 擋掉的信號，後來市場是否真的有盈利空間」。

## 對決策的意義

這條路可以在不下單、不降低主 Cost Gate 的情況下，先把已記錄的 reject 轉成可學習樣本。它比繼續只看 aggregate ranking 更接近真閉環：

1. PG recorded reject
2. materialize to learning ledger row
3. attach future market markout
4. review blocked-signal outcome
5. 再決定是否需要 bounded demo probe authority

## 邊界

本次沒有：

- 啟用 Rust writer
- append runtime ledger
- 安裝 cron
- 寫 PG
- 下單
- 授權 demo/live order
- 降低 main Cost Gate
- deploy / rebuild / restart / runtime source sync

Materializer 固定 `adapter_enabled=false`，所以輸出是 fail-closed evidence，不是 order authority。

## 驗證

- 相關 Python tests：100 passed
- Python compile：PASS
- Diff whitespace check：PASS
- Runtime PG read-only probe：確認最新 demo `cost_gate_js_demo_negative_edge` rows 可被 extractor 讀取
