# BB Audit - Demo Learning Autonomy / Bybit Execution Reality - 2026-06-24

- Role: BB(default)
- Scope: Bybit/demo execution compatibility, order/fill evidence, exchange-facing risk
- Runtime evidence window: 2026-06-24 03:02-03:07 +02 on `trade-core`
- Boundary: read-only repo, artifact, log, process, and PG `SELECT` inspection only. No Bybit private/trading call, no order/cancel/modify, no PG write, no cargo, no restart/deploy, no config/crontab edit.

## Verdict

STATUS: DONE_WITH_CONCERNS

The latest runtime is no longer "orders absent / fills absent": demo is posting and filling some `flash_dip_buy` PostOnly orders. The exchange-facing concern is that the new near-touch behavior coexists with 25 same-day deep passive working orders still recorded as open, and some new fills are unattributed to OpenClaw order ids, so this is fill-evidence collection with lineage gaps, not sustainable profit learning.

## Context Gap

FACT: The requested file `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md` is absent in the repo; `find` and `git ls-files` found no same-named or matching `demo-learning-autonomy` PM context file.

INFERENCE: This audit can still answer from current repo/runtime evidence, but that missing PM context is a completeness concern.

ASSUMPTION: The missing PM context was either not committed, not generated, or superseded by the 2026-06-21/22 PM reports plus TODO v452/v current runtime.

## FACT

1. Runtime source and process:
   - Linux repo HEAD: `c88deea7` (`Restore flash dip working orders into pending cap [skip ci]`), clean against `origin/main`.
   - Demo engine alive; watchdog snapshot age about 28s. Paper/live not running.
   - `live_demo` had 0 orders and 0 fills in both 24h and 168h PG windows.

2. Current demo PG reality:
   - At 03:02 +02 snapshot: last 1h had 760 decision features, 760 risk verdicts, 3 intents, 4 orders, 3 fills.
   - At 03:04 +02 updated snapshot: demo 24h had 35 orders and 5 fills; latest fill `2026-06-24 03:04:31.577+02`.
   - Recent derived order states over 24h: 27 `Working`, 5 `Cancelled`, 3 `Filled`; oldest working order age about 66 minutes during audit.

3. Latest fills:
   - `XRPUSDT` flash_dip maker open filled at 02:45:10, then dynamic stop market close filled at 02:45:52.
   - `ETHUSDT` buy fill at 03:04:16 was recorded as `unattributed:bybit_auto`, then an IPC close filled at 03:04:31.
   - `SOLUSDT` buy fill at 02:56:59 was also `unattributed:bybit_auto`.
   - Current `/tmp/openclaw/demo_state.json` shows no open positions after the latest close.

4. Order touchability:
   - The 02:35 near-touch orders used about 10 bps passive gap. XRP filled; ETH/SOL got exchange fills recorded as unattributed.
   - The 02:00 batch has 25 working PostOnly buy orders with deep passive gaps around 963 to 1825 bps versus reference price.
   - The 00:25 deep orders were self-cancelled at 02:00, but the 02:00 deep working batch remains recorded as `Working`.

5. Risk/Cost Gate:
   - Last 4h risk verdicts: 7,496 `cost_gate(JS-demo)` rejects, 84 `cost_gate(ATR-warmup)` rejects, 43 other `cost_gate` rejects, and 33 approvals.
   - Cost Gate still dominates MA/grid strategy flow, but flash_dip signals now reach intents/orders.

6. Artifact authority state:
   - `demo_learning_stack_healthcheck_latest.json`: stack installed, crons/heartbeats recent, ledger rows present, false-negative candidates present, but `source_ready=false`.
   - `bounded_probe_operator_authorization_latest.json`: decision `defer`; `active_runtime_order_authority=false`; `active_runtime_probe_authority=false`; `order_submission_performed=false`; `global_cost_gate_lowering_recommended=false`; `promotion_evidence=false`.

7. Source changes:
   - `697b24b5` enabled bounded flash-dip demo probes: demo `[flash_dip_buy] active=true`, `bounded_demo_near_touch=true`, `near_touch_offset_bps=10.0`.
   - `b6edd0dd` allowed near-touch fill-discovery to continue even when prior-close seed is absent, using current price only for the near-touch placement path.
   - `c88deea7` restores same-day working flash_dip orders into the strategy pending cap after bootstrap to prevent restart over-emission.
   - Safety constraints present in source/config: PostOnly only, near-touch offset validated to 1-50 bps, producer `max_concurrent=3`, risk per-strategy `max_concurrent_positions=3`, and `flash_dip_buy_max_notional_pct_equity=0.03`. Global `max_order_notional_usdt` is disabled in demo config.

## INFERENCE

1. Orders are not absent, and fills are not absent. The earlier 2026-06-21/22 "no fills / deep passive no-touch" diagnosis is superseded for the latest runtime by actual demo fills on 2026-06-24.

2. The current absence/staleness root cause is mixed by strategy:
   - MA/grid still mostly stop before Bybit due Cost Gate negative-edge/ATR rejects.
   - flash_dip now bypasses the former no-touch evidence problem by producing near-touch PostOnly orders through normal Rust strategy/risk/order flow.
   - The bounded operator-authorization artifacts do not grant authority, but separate runtime source/config commits have already enabled demo flash_dip order placement.

3. The near-touch/flash-dip commits are not merely "source readiness." They changed live demo-runtime behavior for `demo` by turning a demo strategy active and moving actual flash_dip placement from deep static dip to near-touch PostOnly. They do not grant live/mainnet authority, do not lower global Cost Gate, and do not make artifact-only bounded authorization active.

4. Exchange-side safety concern:
   - `c88deea7` is directionally safety-positive because it prevents restart over-emission.
   - It does not cancel the already accepted same-day working overhang. The 25 deep PostOnly working orders are far from touch now, but if a real flash crash touches multiple symbols, exchange-side fills could exceed the intended C=3 exposure because those orders are already resting.
   - The unattributed SOL/ETH fills are an evidence-quality concern: fills reached DB, but original OpenClaw order state did not transition to `Filled` for those opening orders. That weakens fill lineage and sustainable-learning attribution.

5. Current execution path supports bounded evidence collection, not sustainable profit learning. It has first fill/touchability evidence, but it lacks enough clean attributed fills, matched controls, result-review artifacts, and net-positive execution proof. The latest fills include stop/IPC closes and unattributed opens, so they cannot support Cost Gate lowering or promotion.

## ASSUMPTION

1. `trading.order_state_changes` is the best available read-only proxy for current order state because this audit did not call Bybit private open-order endpoints.

2. A DB `Working` order with no later `Cancelled/Filled` state is treated as exchange-open until a later local state-change proves otherwise.

3. `live_demo` inactivity means no recorded runtime activity in the audited DB tables, not proof that every possible live_demo logging path is healthy.

## Answers

1. Latest demo/live_demo reality: demo is active with recent orders and fills; live_demo is inactive/no rows. Orders are not multi-day stale, but there is a current same-day working overhang. Fills are present, but not all are cleanly attributed.

2. If orders were absent before, that was Cost Gate/reject-wall plus no-touch strategy placement. Now, MA/grid remain Cost Gate blocked, while flash_dip strategy signals reach order intent and Bybit. Some orders are touchable/fillable; many 02:00 deep orders are still not realistically touchable absent a large crash.

3. Current near-touch/flash-dip commits changed demo source behavior and order placement, not global/live authority. Exchange-side safety concern exists due outstanding deep working overhang plus unattributed fill lineage. No BB action was taken because cancel/modify is prohibited in this audit.

4. The path currently supports safe evidence collection with concerns, not sustainable profit learning. Next useful evidence should be clean attributed order-to-fill lineage, bounded result review after fresh fills, and explicit operator/PM handling of the outstanding working-order overhang before any Cost Gate or promotion decision.

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-24--demo-learning-autonomy-bb-audit.md
