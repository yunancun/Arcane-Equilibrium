# 玄衡 TODO — Active Dispatch Queue

Version: v13
Date: 2026-05-08
Status: PM replan after AgentTodo M8 fast-track NO-GO and OpenClaw repositioning

This file is the active work queue only. Historical closures, stale observation
tables, and superseded OpenClaw/Gateway assumptions are archived in
`docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`.

## Current Architecture Boundary

- Formal product: `玄衡 · Arcane Equilibrium`.
- Bybit is the only exchange target.
- Rust `openclaw_engine` remains the trading, risk, strategy-config, and
  execution authority.
- Python/FastAPI is the control plane, bridge, GUI backend, replay/orchestration
  surface, and local 5-Agent runtime host. It is not the direct trading truth
  layer.
- The canonical GUI is the existing FastAPI console at
  `trade-core:8000/console`, now the OpenClaw Control Console.
- External OpenClaw Gateway is communication/mobile/supervisor/proposal relay
  only. It is not a trading conductor, not the local 5-Agent runtime, and not a
  second GUI.
- Local Scout / Strategist / Guardian / Analyst / Executor stay inside
  TradeBot. Cloud L2 calls must go through one supervisor escalation packet,
  explicit budget/model config, and durable `agent.ai_invocations` ledger
  reservation.
- `MessageBus` is legacy/advisory trace. Authoritative agent promotion requires
  typed lineage: StrategySignal -> StrategistDecision -> GuardianVerdict ->
  ExecutionPlan -> Decision Lease / idempotency -> ExecutionReport.
- Replay is advisory and diagnostic. Replay can fast-track preflight; it cannot
  substitute for runtime lineage or authorize live promotion.

## Latest State

- REF-20 Sprint A-D and REF-21 replay usability work are closed for current
  planning. Remaining replay work is empirical calibration maturity, not basic
  availability.
- AgentTodo Sprint A, M2, M3, M4, M5, M6, and M7 are closed.
- AgentTodo M8 completed MAG-080/MAG-081/MAG-082 checklist/policy work.
- `stage2_demo_livedemo_20260507t1602z` fast-track review is NO-GO:
  runtime `agent.decision_objects`, `agent.decision_edges`, and
  `agent.execution_idempotency_keys` remain 0 all-time; replay completed three
  strategy reports with 0 fills and `execution_confidence=none`.
- MAG-083 final release audit and MAG-084 operator sign-off remain BLOCKED.
- P1 healthcheck FAIL queue from 2026-05-07 is source-closed/downgraded:
  `[Xb]`, `[42]`, `[50]`, and `[51]` are not current hard blockers. Their
  residual WARN signals remain under P1 data/edge monitoring.
- `P1-FAKE-1` is closed: explicit Linux runtime smoke proved fake-live
  `live_demo` metadata routes through real Rust IPC with no exchange order and
  no DB write in the smoke harness.
- `P1-OPENCLAW-3` is closed at `c49125f1`: `/brief/latest`,
  `/diagnostics`, and `/escalations` are backend-authored read-only envelopes.
- `P1-OPENCLAW-6/7` backend foundation is closed at `276a9b17`: proposal
  intake, approval/reject relay, channel-event audit ledger, V065 schema, and
  healthcheck `[54]` are live on Linux. Approval relay records operator
  decisions only; side-effect delegation remains disabled/fail-closed.
- `P1-AGENT-OBS-1` is source-closed: passive healthcheck `[55]`
  `agent_decision_spine_lineage` distinguishes decision-spine disabled,
  enabled-but-empty, incomplete lineage, pending reports, and
  `MAG-082 readiness=*`. It is read-only and does not authorize runtime flag
  changes, rebuild, restart, or Stage 2.
- `W-B` runtime decision-spine lineage is source-ready: Rust startup now wires
  the durable Agent Spine writer behind `OPENCLAW_AGENT_SPINE_RUNTIME_MODE`,
  and approved demo/live_demo open intents emit shadow-only typed
  StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
  ExecutionReport objects plus edges and idempotency keys. Runtime row proof
  still requires explicit operator approval for rebuild/restart/env flip.

## Dispatch Order

Do not start proposal relay, Telegram/WebChat, a second GUI, Stage 3/4, or true
live autonomy while MAG-082 runtime lineage is NO-GO.

| Rank | Wave | Owner Chain | Target Window | Exit Criteria |
|---:|---|---|---|---|
| 1 | `W-A` Executor fake-live runtime smoke | PM -> E4 -> PM | DONE 2026-05-07 | Proved the loaded `P1-FAKE-1` path routes explicit `live_demo` metadata through real Rust IPC without exchange order, DB write, or Python-only fake success. |
| 2 | `W-B` Runtime decision-spine lineage wiring | PM -> PA -> E1 -> E2 -> E4 -> PM | 2026-05-08 to 2026-05-10 | Runtime shadow path writes nonzero typed decision objects, edges, and idempotency keys for demo/live_demo without changing trading authority. |
| 3 | `W-C` New MAG-082 Stage 2 evidence window | PM -> E3 -> E4 -> QA -> PM | after W-B + explicit operator rebuild/restart approval | Fresh 24h demo/live_demo canary proves StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease/idempotency -> ExecutionReport. |
| 4 | `W-D` MAG-083 / MAG-084 | QA -> PM | after W-C PASS only | Final release audit PASS, then operator sign-off. |
| 5 | `W-E` OpenClaw read-only observability expansion | PM -> PA -> E1 -> E2 -> E4 -> PM | DONE 2026-05-07 | Added `/brief/latest`, `/diagnostics`, and `/escalations` as backend-authored view models. |
| 6 | `W-F` Edge/data quality and Live Gate foundation | PM -> QC/MIT/PA -> E1/E4 -> PM | after W-A; before true-live | Work through residual WARN cluster, H0 production caller, pricing binding, and supervised-live state machine. |
| 7 | `W-G` Proposal/approval/mobile relay | PM -> CC/FA/PA -> E1/E2/E4 -> PM | BACKEND FOUNDATION DONE 2026-05-07 | Gateway/console may create proposals and relay approval/reject intent into the `openclaw.*` ledger. No direct order/config/live-auth authority; external Telegram/WebChat/mobile adapters remain disabled until separately configured. |

## P0 — True-Live Blockers

| ID | Status | Task | Acceptance |
|---|---|---|---|
| `P0-AGENT-1` | BLOCKED | Runtime Agent Decision Spine lineage | Nonzero demo/live_demo runtime rows for typed objects, edges, and idempotency keys; chain reconstructs StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease -> ExecutionReport. |
| `P0-AGENT-2` | BLOCKED | MAG-082 Stage 2 rerun | New operator-approved window completes with PASS. Replay cannot substitute. |
| `P0-AGENT-3` | BLOCKED | MAG-083 final release audit | QA PASS after `P0-AGENT-2`; no execution path bypasses StrategistDecision, GuardianVerdict, ExecutionPlan, and Decision Lease. |
| `P0-AGENT-4` | BLOCKED | MAG-084 operator sign-off | PM/operator sign-off after MAG-083 PASS. |
| `P0-EDGE-1` | ACTIVE | Edge net-positive decision | Current strategy edge must be positive or formally scoped to a limited supervised path before true-live. |
| `P0-LG-1` | ACTIVE | H0 blocking production caller | H0 is wired into the production decision path with metrics and fail-closed behavior. |
| `P0-LG-2` | ACTIVE | Provider pricing binding | Fee/pricing source is bound, freshness checked, and asserted at startup. |
| `P0-LG-3` | ACTIVE | Supervised-live state machine | Live authorization, lease, drawdown, revoke, and operator approval states are explicit and tested. |
| `P0-OPS-1` | ACTIVE | HTTPS + secure cookie deploy | Required before any external live-facing operator surface. |
| `P0-OPS-2` | ACTIVE | Credential rotation | PG/Grafana/live-secret rotation and history-clean plan complete before true-live. |
| `P0-OPS-3` | ACTIVE | Legal/ToS/geography check | Operator confirms Bybit ToS, KYC, and geography constraints before true-live. |
| `P0-OPS-4` | ACTIVE | First-day live runbook | Disaster and supervised-live first-day SOP exists and is rehearsed. |

## P1 — Next Engineering Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `P1-FAKE-1` | 1 | DONE — executor fake-live smoke | Linux runtime smoke passed: Rust IPC path exercised, no exchange order, no DB write. |
| `P1-OPENCLAW-3` | 2 | DONE — read-only brief/diagnostics/escalations APIs | Backend-authored view models from durable stores only; no raw frontend table stitching. |
| `P1-OPENCLAW-6/7` | 2 | DONE — proposal/approval relay backend foundation | V065 `openclaw.*` ledger applied on Linux; proposal create + approve runtime smoke passed with `side_effect_executed=false`; `[54]` PASS. |
| `P1-AGENT-OBS-1` | 2 | DONE — explicit lineage healthcheck | `[55] agent_decision_spine_lineage` distinguishes disabled / enabled-empty / incomplete / report-pending states and surfaces `MAG-082 readiness=*`; `OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED=1` escalates WARN to FAIL. |
| `P1-AGENT-RUNTIME-1` | 2 | SOURCE-READY — runtime decision-spine lineage | Source/test wiring complete behind `OPENCLAW_AGENT_SPINE_RUNTIME_MODE`; 2026-05-08 restart loaded current source, but env remains disabled, so no runtime row proof until explicit env flip. |
| `P1-DATA-1` | 3 | Runtime-reloaded WARN cluster: `[14]`, `[37]`, `[40]`, `[45]` | `[14]` distinguishes risk/cost gate suppression from writer-health evidence; `[37]` ignores recovered historical failures; `[40]` catches combined demo/live_demo negative cells and `LABUSDT` grid block source is now runtime-reloaded as of 2026-05-08; `[45]` accepts recent AccountManager fee-use proof during rejected-only demo/live_demo no-fill windows. Monitor row rolloff after reload. |
| `P1-DATA-2` | 3 | Source-fixed `[42b]` / `[42c]` low-sample attribution watch | Settled attribution ratio failures stay fail-closed, but low-sample strategies now render as `LOW_SAMPLE(n, need)` sample-maturity watch instead of misleading `0.000` ratio drift; low-sample strategies still defer promotion until mature. |
| `P1-DATA-3` | 3 | Source-fixed `[51]` scanner opportunity calibration watch | `[51]` now requires mature `opportunity_positive` samples before PASS, reports `MATURE/LOW_SAMPLE(n, need)`, and keeps scanner opportunity shadow-only when only exploration positive LCB samples exist or calibrated samples are immature. |
| `P1-EDGE-1` | 3 | Source-fixed ma_crossover LABUSDT block + bb_breakout diagnosis | Runtime diagnosis: 7d ma_crossover combined demo/live_demo is negative mainly from `LABUSDT` (`n=6 avg=-244.54bps`), so `LABUSDT` is source-blocked for ma_crossover new entries in risk configs while close/reduce remains allowed; bb_breakout stays demo-only/live-disabled with low negative sample (`7d n=10 avg=-5.06bps`) pending more evidence. |
| `P1-EDGE-2` | 3 | funding_arb 14d audit | Run the 2026-05-16 audit before retention or deprecation decisions. |
| `P1-REPLAY-1` | 4 | Recorder-history maturity | Build longer local BBO/orderbook/latency history for S1/S1+ calibration; never fabricate old microstructure. |
| `P1-REPLAY-2` | 4 | DONE — runtime-applied replay artifact type cleanup | V066 applied twice on Linux for idempotency, constraints verified, rollback smoke passed, and runtime reloaded with `restart_all.sh --keep-auth` on 2026-05-08. New finalize rows can use `replay_report`; legacy `pnl_summary` remains readable. |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | Source is active; continue audit-row and attribution health monitoring. |

## P2 — Maintenance Backlog

Only keep maintenance items that are still actionable under the current
architecture. Obsoleted LOC-governance items, closed REF-20/REF-21 tasks,
historical wave narratives, and old date-driven reminders are archived.

| ID | Task | Trigger |
|---|---|---|
| `P2-MIG-1` | DONE — V054 lease transitions Python migration sibling test | Added sibling coverage for V054 Guard A, `lease_transitions` schema/checks/indexes, Timescale hypertable branch, and `governance_audit_log` event_type extension. |
| `P2-MIG-2` | DONE — V066 byte-size CHECK and `replay_report` artifact enum migration | Covered by `P1-REPLAY-2`; Linux runtime DB applied and idempotency-verified on 2026-05-08. |
| `P2-SEC-1` | DONE — generic replay finalize 503 exception messages | Client 503 no longer exposes backend exception class/message; detailed failure remains in server logs under `replay_finalize_failed`. |
| `P2-REPLAY-1` | DONE — PID reuse guard for replay runner finalize | V067 adds nullable `subprocess_started_at_ms`; spawn captures process create_time when available, and finalize rejects reused replay_runner PIDs whose cmdline matches but start-time differs. |
| `P2-PYDANTIC-1` | DONE — replay Pydantic V1 `@validator` -> V2 `@field_validator` migration | Removed replay validator deprecation warnings under pinned `pydantic>=2.11.0`. |
| `P2-RUST-1` | DONE — split `intent_processor/tests.rs` under 2000 LOC | `tests.rs` is 1556 LOC; larger nested predictor/maker/router suites moved to `tests_predictor_router.rs` at 1363 LOC. |
| `P2-LEASE-1` | Clean terminal `DecisionLeaseSm.objects` Vec entries | If long soak shows memory growth or before high-volume live. |
| `P2-STRUCT-1` | HStateCache + CostEdgeAdvisor late-inject slot enablement | After H0/pricing ownership is clear. |
| `P2-STRUCT-2` | Zombie/deprecated code inventory | Next architecture hygiene sweep. |

## Schedule

Dates are planning windows, not automatic authorization.

| Date | Work | Gate |
|---|---|---|
| 2026-05-07/08 | `W-A` executor fake-live runtime smoke | No rebuild unless operator asks. |
| 2026-05-08 to 2026-05-10 | `W-B` runtime decision-spine lineage wiring | Source/test only until operator authorizes runtime reload. |
| 2026-05-09 | 3C 7d audit | Run `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` if still relevant to current runtime history. |
| 2026-05-10/11 | New Stage 2 evidence window candidate | Requires W-B, rebuild/restart approval, and clean entry checks. |
| 2026-05-11/12 | MAG-083/MAG-084 candidate | Only if new MAG-082 report PASSes. |
| 2026-05-15 | Edge / Decision Lease canary decision review | Use current edge data; do not promote if MAG-082 lineage is still NO-GO. |
| 2026-05-16 | funding_arb 14d audit | Run `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`. |

## Dispatch Rules

- Use PM-first triage for every wave.
- Implementation work: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`, with
  roles skipped only when explicitly justified.
- Security/deploy/runtime work: `PM -> E3 -> BB if exchange-facing -> PM`.
- Quant/data decisions: `PM -> QC -> MIT -> AI-E if model economics matter ->
  PM`.
- Commit each green checkpoint with subject and body, push to origin, then
  sync Linux by fast-forward.
- Do not rebuild, restart, mutate live auth, change scanner authority, unlock
  executor shadow, enable lease-router, or add OpenClaw write/proposal routes
  unless the operator explicitly authorizes that action.

## Handoff Checks

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```
