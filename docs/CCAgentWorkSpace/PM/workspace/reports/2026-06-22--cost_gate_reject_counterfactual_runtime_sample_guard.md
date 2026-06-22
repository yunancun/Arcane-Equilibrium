# Cost Gate Reject Counterfactual Runtime Sample Guard

日期：2026-06-22
角色：PM
範圍：read-only runtime PG counterfactual + source/test guard；不授權下單或降低 Cost Gate。

## 結論

被 Cost Gate 擋掉的信號不應被粗暴視為“必然沒有盈利可能”。最新只讀 counterfactual 顯示 `ma_crossover|BTCUSDT|Buy` 在 15m/60m horizon 扣 4bp 後仍為正，且樣本量大；但 240m horizon 反轉，`BTCUSDT Buy` 被確認為 blocked，`BTCUSDT Sell` 變成 candidate。這是 horizon/regime-specific learning evidence，不是全局放寬 Cost Gate 的證據。

同時，現有工具只報 raw `n`，可能讓重複行膨脹樣本門檻。已補 source guard：counterfactual SQL 現在輸出 `distinct_ts`、`timespan_minutes`、`rows_per_distinct_ts`，並以 `distinct_ts` 優先作為 `sample_count_for_gate`。這讓 bounded demo-learning review 更可靠。

## Runtime Evidence

Commands used existing runtime checkout in read-only mode with explicit PG identity:

```bash
PGHOST=127.0.0.1 PGPORT=5432 PGUSER=trading_admin PGDATABASE=trading_ai \
PGOPTIONS='-c default_transaction_read_only=on' \
python3 helper_scripts/db/audit/cost_gate_reject_counterfactual.py \
  --lookback-hours 24 --horizon-minutes <15|60|240> --limit 50000
```

Runtime source is stale and lacks the local multi-horizon CLI flag, so horizons were run separately.

| horizon | side-cell | action | n | avg_net_bps | p50_gross_bps | net_positive_pct |
|---:|---|---|---:|---:|---:|---:|
| 15m | `ma_crossover|BTCUSDT|Buy` | `LEARNING_PROBE_CANDIDATE` | 28547 | 2.8273 | 11.1350 | 75.68 |
| 60m | `ma_crossover|BTCUSDT|Buy` | `LEARNING_PROBE_CANDIDATE` | 30902 | 12.2057 | 10.1657 | 65.74 |
| 240m | `ma_crossover|BTCUSDT|Buy` | `BLOCK_CONFIRMED` | 36181 | -47.7899 | -24.7210 | 0.00 |
| 240m | `ma_crossover|BTCUSDT|Sell` | `LEARNING_PROBE_CANDIDATE` | 13819 | 31.8707 | 51.4448 | 81.94 |

Coverage caveat from runtime output:

- `features_joined_contexts=104`
- context coverage roughly `0.1702%`
- `features_joined_outcomes=0`
- `risk_verdicts_joined_intents=0`
- 0 fills in the concurrent demo data-flow refresh

Interpretation: this is kline markout counterfactual evidence over recorded rejects, not execution/fill evidence.

## Duplicate Sample Check

Read-only runtime SQL over the latest 24h `ma_crossover` Cost Gate rejects:

| symbol | side | rows | distinct_ts | rows_per_ts |
|---|---|---:|---:|---:|
| BTCUSDT | Buy | 39637 | 39637 | 1.00 |
| BTCUSDT | Sell | 16515 | 16515 | 1.00 |
| ETHUSDT | Buy | 2583 | 2583 | 1.00 |
| ETHUSDT | Sell | 2355 | 2355 | 1.00 |

Current BTC candidate is therefore not inflated by same-timestamp duplicate rows. The source guard still matters for future bursts.

## Source Change

File changed:

- `helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
- `helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py`

New fields:

- `distinct_ts`
- `timespan_minutes`
- `rows_per_distinct_ts`
- `sample_count_for_gate`

Behavior:

- Classification uses `distinct_ts` first, falling back to raw `n`.
- Profit ranking, horizon stability, JSON, and Markdown expose raw rows and effective sample count.
- Duplicate-row test locks `n=500`, `distinct_ts=3` as `INSUFFICIENT_SAMPLE`.

## Verification

- `python3 -m py_compile helper_scripts/db/audit/cost_gate_reject_counterfactual.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py`
- `python3 -m pytest helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q` = `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `117 passed`
- `git diff --check`

## Boundary

Performed:

- source/test/docs edits
- read-only runtime PG SELECTs
- no remote artifact write for the successful counterfactual runs

Not performed:

- no runtime source sync
- no cron install
- no env edit
- no deploy/rebuild/restart
- no PG write/schema migration
- no Bybit private/signed/trading call
- no credential/auth/risk/order/strategy mutation
- no writer enablement
- no Cost Gate lowering
- no order/probe authority
- no promotion proof

## Next

After operator-approved source reconcile, run the current multi-horizon counterfactual on Linux, produce the decision packet, and use the top horizon-specific side-cell for bounded demo-probe review. The correct next action is bounded review, not global Cost Gate relaxation.
