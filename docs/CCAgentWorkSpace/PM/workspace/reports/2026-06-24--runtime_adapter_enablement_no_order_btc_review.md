# Runtime Adapter Enablement No-Order BTC Review

日期：2026-06-24
Active blocker：`P0-BOUNDED-PROBE-RUNTIME-ADAPTER-ENABLEMENT-DEMO-ONLY-E3-BB-REVIEW`
角色鏈：PM -> E3 -> BB -> PM
狀態：`DONE_WITH_CONCERNS`

## 結論

本輪沒有啟用 writer、沒有重啟服務、沒有改 env/cron、沒有寫 PG/ledger，也沒有呼叫 Bybit 或送單。

E3/BB review 一致指出：現有 source 沒有一個安全 production flag 可以把 bounded BTC candidate 從 artifact-only 直接變成 demo order submission。Rust writer 仍 hard-code `adapter_enabled=false`，tick path 只產生 placement preview，沒有 order routing。

PM 只做了 no-order checkpoint：

- 用 timestamped 臨時計畫副本注入既有 BTC operator authorization object，不改 canonical `demo_learning_lane_plan_latest.json`
- 對 `ma_crossover|BTCUSDT|Sell` / 240m / demo 事件跑 `runtime_adapter.py --adapter-enabled`，不加 `--record-decision`
- 從 runtime read-only PG 讀 BTCUSDT 本地 BBO 與 instrument filters，做 no-order placement construction preview

結果：

```text
admission_decision=ADMIT_DEMO_LEARNING_PROBE
placement_status=SKIP_FAIL_CLOSED_NO_ORDER
canonical_plan_sha=624a62d56912ebe5ddaab898296e55a0281b0d524dc0fa32e11355f70e917a10
canonical_ledger_sha=846242266373bf50b4bedd098bcbcb30011269d9bb1b13b10f74a00200dcf7d5
```

Admission gate 在臨時計畫 + adapter-enabled dry-run 下通過，但真實 order construction fail-closed，原因：

- `stale_bbo_snapshot`：本地 BTCUSDT BBO age `1652ms`，超過 placement repair plan 的 `1000ms` freshness gate
- `max_demo_notional_below_min_positive_qty_step`
- `rounded_notional_below_min_notional`
- `min_positive_qty_notional_exceeds_demo_cap`

BTCUSDT runtime filters：

```text
tick_size=0.10
qty_step=0.001
min_notional=5
```

No-order Sell construction：

```text
best_bid=60040.1
best_ask=60040.2
post_round_limit_price=60040.2
post_round_passive_against_best_bid=true
touch_gap_bps=0.0166555352
max_demo_notional_usdt_per_order=10.0
raw_qty_for_max_notional=0.0001665551
rounded_qty_down=0.0
min_positive_qty_notional_at_limit=60.0402
```

So the current 10 USDT/order cap is below BTCUSDT's minimum positive quantity step at current prices. A real order path must remain blocked unless a separate source/proposal checkpoint repairs either sizing/cap policy under operator/QC risk bounds or candidate selection picks a lower-price symbol whose instrument filters fit the current cap.

## Runtime Artifacts

Generated on `trade-core`:

- Summary：`/tmp/openclaw/cost_gate_learning_lane/runtime_adapter_enablement_no_order_review_btc_sell_20260624T164719Z.json`
- Temporary authorized plan copy：`/tmp/openclaw/cost_gate_learning_lane/no_order_authorized_plan_copy_btc_sell_20260624T164719Z.json`
- Event：`/tmp/openclaw/cost_gate_learning_lane/no_order_admission_event_btc_sell_20260624T164719Z.json`
- Admission dry-run：`/tmp/openclaw/cost_gate_learning_lane/no_order_admission_adapter_enabled_btc_sell_20260624T164719Z.json`
- Placement preview：`/tmp/openclaw/cost_gate_learning_lane/no_order_placement_construction_preview_btc_sell_20260624T164719Z.json`

## Anti-Repeat Decision

`P0-BOUNDED-PROBE-RUNTIME-ADAPTER-ENABLEMENT-DEMO-ONLY-E3-BB-REVIEW` is no longer a reason to rerun generic runtime-adapter review without new source/runtime/artifact evidence.

Decision：`DONE_WITH_CONCERNS`

Why not repeat:

- E3/BB review already established the source boundary: no safe direct demo order flag exists today.
- No-order admission dry-run already proved the candidate can reach `ADMIT_DEMO_LEARNING_PROBE` only in a temporary, non-ledger plan copy.
- No-order placement preview found concrete execution blockers that must be repaired before any demo order attempt.

Next blocker:

`P0-BOUNDED-PROBE-CAP-AND-ORDER-CONSTRUCTION-REPAIR-DEMO-ONLY-SOURCE-PROPOSAL`

Max safe next action:

Source-only proposal to repair bounded-probe sizing contract: either raise demo notional cap above BTCUSDT minimum positive qty notional under operator/QC risk bounds, or choose a lower-price candidate whose min qty fits the existing 10 USDT cap. No order/live/runtime mutation.

## Boundary

Performed:

- read-only source/runtime review
- timestamped `/tmp/openclaw` artifact writes
- read-only PG queries for BBO/instrument filters
- no-order admission dry-run against temporary plan copy
- no-order placement construction preview

Not performed:

- no canonical latest plan mutation
- no canonical ledger append
- no PG write
- no Bybit public/private/order call
- no order/cancel/modify
- no env/crontab/service mutation
- no Rust writer enablement
- no Cost Gate lowering
- no live/mainnet authority
- no promotion proof
