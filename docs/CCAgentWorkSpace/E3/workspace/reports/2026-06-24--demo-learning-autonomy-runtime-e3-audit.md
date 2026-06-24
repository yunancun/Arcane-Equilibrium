# 2026-06-24 -- Demo Learning Autonomy Runtime E3 Audit

Role: E3(explorer)
Scope: Linux `trade-core` runtime / security gate / service and cron evidence
Mode: read-only audit; no code patch, no deploy/restart, no crontab edit, no PG write, no Bybit write API, no Linux cargo/build/test/check.

## Verdict

STATUS: DONE_WITH_CONCERNS

Runtime is synced clean to current `main` and the demo-learning / Cost Gate learning stack is now installed, firing, and evidence-producing. True live remains closed. The main concern is that several installed cron entries still pin `OPENCLAW_EXPECTED_SOURCE_HEAD=1b6173e3`, so persisted health/evidence artifacts can report source-not-ready even though the checkout is now clean at `c88deea7`.

Runtime evidence strongly contradicts any blanket claim that Demo has not placed orders for a long time: demo orders and fills occurred within the last hour, including the newly enabled `flash_dip_buy` demo pilot.

## FACT

### Context Note

- The prompt-requested PM context file `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md` was not present in the repo.
- Fallback context used: required governance docs plus adjacent PM demo-learning / Cost Gate runtime reports from 2026-06-22 and 2026-06-23.

### Source State

- Linux repo: `/home/ncyu/BybitOpenClaw/srv`
- `git status --short --branch`: `## main...origin/main`
- `HEAD`: `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92`
- `origin/main`: `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92`
- Latest commit: `c88deea7 Restore flash dip working orders into pending cap [skip ci]`
- Worktree status: clean.

### Services / Runtime

- Watchdog user service: `openclaw-watchdog.service` active/running since `2026-06-23 14:04:11 CEST`.
- Engine process: `rust/target/release/openclaw-engine`, PID `1932312`, started `2026-06-24 02:45:28 CEST`.
- API process: uvicorn `app.main:app`, PID `1859622`, started `2026-06-24 00:26:04 CEST`, listening on `100.91.109.86:8000`.
- API unit concern: `openclaw-trading-api.service` is `inactive (dead)` even though uvicorn is running.
- Gateway unit: `openclaw-gateway.service` inactive.
- Watchdog status: `engine_alive=true`, demo alive with snapshot age `2.4s`; live `not_running`; paper stale/not alive.

### Demo-Learning / Cost Gate Crons

Installed cron entries are present for:

- `demo_learning_evidence_audit_cron.sh` at `7,37 * * * *`
- `sealed_horizon_probe_preflight_cron.sh` at `22 * * * *`
- `cost_gate_learning_lane_cron.sh` at `27 * * * *`
- `demo_learning_stack_healthcheck_cron.sh` at `32 * * * *`
- `alpha_discovery_throughput_cron.sh` at `*/15 * * * *`

Fresh heartbeat/artifact evidence at `2026-06-24 03:06:15 CEST`:

- `demo_learning_evidence_audit.last_fire`: `2026-06-24 02:37:01 +0200`
- `sealed_horizon_probe_preflight.last_fire`: `2026-06-24 03:00:03 +0200`
- `cost_gate_learning_lane.last_fire`: `2026-06-24 02:27:01 +0200`
- `demo_learning_stack_healthcheck.last_fire`: `2026-06-24 02:32:01 +0200`
- `alpha_discovery_throughput.last_fire`: `2026-06-24 03:00:01 +0200`
- Latest demo-learning evidence JSON: `2026-06-24 02:37:18 +0200`
- Latest blocked-outcome review JSON: `2026-06-24 02:29:46 +0200`
- Latest activation packet JSON: `2026-06-24 03:00:02 +0200`
- Latest alpha discovery JSON: `2026-06-24 03:00:06 +0200`

Direct healthcheck with current expected head `c88deea7` returned:

- `status=EVIDENCE_STACK_ACTIVE`
- `source_ready=true`
- `stack_installed=true`
- `heartbeats_recent=true`
- `latest_artifacts_present=true`
- `cost_gate_learning_ledger_rows_present=true`
- `blocked_signal_outcomes_present=true`

Persisted cron healthcheck artifact still reported:

- `status=SOURCE_NOT_READY`
- source head in artifact: `697b24b5...`
- expected head in artifact: `1b6173e3`
- reason: `runtime_source_not_clean_or_expected_head_mismatch`

This is because installed stack cron entries still include expected-head values pinned to `1b6173e3`.

### Cost Gate / Authorization Artifacts

Latest blocked-outcome review:

- schema: `cost_gate_demo_learning_lane_blocked_outcome_review_v2`
- generated: `2026-06-24T00:29:46Z`
- status: `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`
- blocked-signal outcome count: `45,938`
- false-negative candidate count: `16`
- top candidate: `grid_trading|ATOMUSDT|Sell`
- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`
- `promotion_evidence=false`

Latest bounded-probe operator authorization packet:

- schema: `bounded_demo_probe_operator_authorization_packet_v1`
- generated: `2026-06-24T01:00:04Z`
- decision: `defer`
- `operator_authorization=null`
- `active_runtime_order_authority=false`
- `active_runtime_probe_authority=false`
- `global_cost_gate_lowering_recommended=false`
- `order_submission_performed=false`
- `writer_enabled=false`

### Live / Demo Gates

- Engine process env summary showed `OPENCLAW_ALLOW_MAINNET=0`.
- Engine process env summary showed `OPENCLAW_FLASH_DIP_PILOT_ENABLED=1`.
- No `authorization.json` files were found under the checked runtime secret/data roots.
- PG evidence for true live in last 30 days: `live_orders_30d=0`, `live_fills_30d=0`.
- `live_demo` latest order was `2026-06-13 05:00:01 +0200`; latest fill was `2026-06-12 23:29:14 +0200`.
- Source and running binary contain the flash-dip demo pilot registration and bounded near-touch strings.

### Demo Order Evidence

PG counts by window:

- Last 1h demo: `orders=5`, `fills=5`, `intents=3`, `risk_verdicts=760`, latest order `2026-06-24 03:04:31 +0200`, latest fill `2026-06-24 03:04:31 +0200`.
- Last 4h demo: `orders=35`, `fills=5`, `intents=33`, `risk_verdicts=7,656`.
- Last 24h demo: `orders=35`, `fills=5`, `intents=33`, `risk_verdicts=39,395`.
- Last 7d demo: `orders=913`, `fills=352`, `intents=629`.
- Last 30d demo: `orders=57,680`, `fills=993`, `intents=1,733`.

Latest 24h order/fill breakdown:

- `flash_dip_buy`: `33` demo `Limit`/`PostOnly` `Working` orders in 24h; latest `2026-06-24 02:35:26 +0200`.
- `flash_dip_buy`: `1` demo maker fill in 24h; `XRPUSDT Buy`, `2026-06-24 02:45:10 +0200`.
- Risk-close orders/fills also occurred around `02:45` and `03:04`.

## INFERENCE

- True-live execution is closed as expected: no live engine, `OPENCLAW_ALLOW_MAINNET=0`, no live authorization artifact found, and no live orders/fills in 30 days.
- Cost Gate bounded demo-probe authority remains closed: artifacts explicitly withhold operator authorization and order/probe authority.
- A separate, narrow Demo order path is open and active: `flash_dip_buy` demo pilot is enabled by runtime env + demo-only source gates and is placing PostOnly demo orders/fills.
- The claim "Demo has not placed orders for a long time" is false for the current runtime. It may have been true for an earlier stale-source window, but it is contradicted by 2026-06-24 PG order/fill evidence.
- The installed stack is functionally active, but cron expected-head drift can produce misleading `SOURCE_NOT_READY` artifacts until the cron env pins are reconciled to current `c88deea7` or intentionally left unpinned.

## ASSUMPTION

- "Current main" means `origin/main` as visible on Linux without fetching during this read-only audit.
- The checked runtime secret/data roots are the expected roots for live authorization artifacts.
- The operator intentionally enabled the `flash_dip_buy` demo pilot because both source config and engine env are aligned to that state.

## Concerns

1. `openclaw-trading-api.service` is inactive while uvicorn is running manually or outside that unit. Operational status is currently good enough for API reachability, but service evidence is not clean.
2. Demo-learning stack cron entries still pin `1b6173e3` expected-head values while runtime is at `c88deea7`. This causes stale/contradictory health artifacts.
3. Reporting should separate "Cost Gate bounded demo-probe authority is closed" from "Demo order authority is globally absent." The latter is no longer true because `flash_dip_buy` demo pilot is actively ordering.

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 2 MEDIUM-CONCERN / 1 LOW-CONCERN · report path: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-24--demo-learning-autonomy-runtime-e3-audit.md`
