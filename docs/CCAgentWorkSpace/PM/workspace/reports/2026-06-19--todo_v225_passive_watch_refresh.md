# TODO v225 Passive-Watch Refresh

Date: 2026-06-19
Owner: PM
Scope: Linux read-only passive-watch refresh + TODO evidence update

## Result

This checkpoint advances `TODO.md` to v225 and records the latest passive watch state. It does not close or archive any active runtime, alpha, review, or operator gate.

## Evidence

- Source sync: Mac/origin/Linux were aligned at v224 checkpoint `f622574a`; Linux `trade-core` watchdog reported `engine_alive=true` with demo snapshot age `28.6s`.
- Gate-B: `/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json` generated `2026-06-19T01:12:01.485600Z` remained `WATCH_ONLY`, with 21 total candidates, 0 alertable, 0 start_now, 0 schedule, and 1 watch_only. Top candidates were stale/old `BPUSDT`; no preflight or isolated probe was run.
- flash_dip: `/tmp/openclaw/flash_dip_buy_entry_ts.json` remained `{}`; death-rate last-success/log remained absent. Read-only PG found 0 flash_dip rows in intents, orders, fills, order-state changes joined through orders, and position snapshots.
- L2: `agent.l2_calls` remained 1 historical row; `memory_recall_shadow` remained 0 rows; `agent.l2_consequential_marks` remained 0. Cursor remained `last_success_utc_date=2026-06-17`; 2026-06-12..17 log tail remained no-op with `materials_l2=0` and `stored=0`.
- D2: `observability.engine_events(event_type='reconcile_ghost_converge')` remained total=0 / semantics=0.
- Passive health: `2026-06-19T01:23:30Z` overall still FAIL on `[74] close_maker_reject_samples` (`attempts=200`, `postonly_reject_samples=26`, `max_pending_samples=0`) and `[56] live_pipeline_active` (`authorization_json_missing`).

## Boundary

No CI full suite, cargo, Linux build, deploy, rebuild, restart, DB write, Bybit private/signed call, credential/key/secret mutation, runtime/auth/risk/order/trading mutation, probe start, archive, promotion, or gate closure.
