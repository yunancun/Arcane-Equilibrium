# Cost Gate Reject Counterfactual Runtime Sample Guard

日期：2026-06-22
角色：PM
範圍：read-only runtime PG counterfactual + source/test guard；不授權下單或降低 Cost Gate。

## 結論

最新只讀 counterfactual 顯示：被 Cost Gate 擋掉的信號裡確實有 learning candidate，不應假設全都沒有盈利可能。但它不是全局放寬 Cost Gate 的證據，因為結果明顯 horizon-specific。

關鍵結果：

| horizon | side-cell | action | n | avg_net_bps | net+ |
|---:|---|---|---:|---:|---:|
| 15m | `ma_crossover|BTCUSDT|Buy` | candidate | 28547 | +2.8273 | 75.68% |
| 60m | `ma_crossover|BTCUSDT|Buy` | candidate | 30902 | +12.2057 | 65.74% |
| 240m | `ma_crossover|BTCUSDT|Buy` | block confirmed | 36181 | -47.7899 | 0.00% |
| 240m | `ma_crossover|BTCUSDT|Sell` | candidate | 13819 | +31.8707 | 81.94% |

這代表下一步應該是 source reconcile 後做 bounded demo-learning / probe review，而不是全局降低 Cost Gate。

## 已補的工程保護

`cost_gate_reject_counterfactual.py` 現在輸出並使用：

- `distinct_ts`
- `timespan_minutes`
- `rows_per_distinct_ts`
- `sample_count_for_gate`

分類和 ranking 改用 `distinct_ts` 優先作為樣本門檻，避免同一 timestamp 重複 rows 把候選誤判為樣本充足。測試已鎖定：`n=500` 但 `distinct_ts=3` 會被判 `INSUFFICIENT_SAMPLE`。

## Runtime Caveat

本輪 runtime 成功 counterfactual 是 kline markout，不是成交或 queue-fill evidence：

- `features_joined_contexts=104`
- context coverage 約 `0.1702%`
- `features_joined_outcomes=0`
- concurrent demo data-flow 仍是 0 fills

Duplicate check 顯示目前 BTC/ETH side-cells `rows_per_ts=1.00`，這次 BTC candidate 不是同 timestamp 重複膨脹。

## 邊界

只做 source/test/docs + read-only runtime PG SELECT。未做 runtime source sync、cron/env/deploy/restart、PG write、Bybit private call、order/risk/strategy mutation、Cost Gate lowering 或 probe/order authority。
