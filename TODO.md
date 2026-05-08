# 玄衡 TODO — Active Dispatch Queue

Version: v14
Date: 2026-05-08
Status: PM replan after AgentTodo M8 fast-track NO-GO and OpenClaw repositioning; v14 mounts 12-agent full audit fix plan (PA integrated, 88 finding / 7 wave / ~140h)

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
- Scanner is always-on infrastructure for market context, active-universe
  attribution, route fitness, opportunity evidence, and legacy would-block
  audit. It is not a trading authority and cannot hard-gate opens, closes, live
  auth, or order dispatch.
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
- `W-B` runtime decision-spine lineage is closed: Linux `trade-core`
  deployed `3d6f62dd` with `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`;
  `[55]` PASSed with typed StrategySignal -> StrategistDecision ->
  GuardianVerdict -> ExecutionPlan -> ExecutionReport runtime rows, edges,
  and idempotency keys. This is still shadow-only and does not grant trading
  authority or complete the later Decision Lease Stage 2 gate.
- `W-C` Stage 2 evidence collection is active on Linux `trade-core` at
  `503eeb33`: `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` and
  `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` are runtime-loaded. Scanner hard
  authority is retired; `scanner_config.toml` no longer carries an `[authority]`
  mode switch, and scanner would-blocks are evidence only. `[55]` PASSed with
  `chains_with_lease=33`, proving router-gate bypass lineage is written into
  Agent Spine shadow ExecutionPlan rows. MAG-082 readiness remains
  `LINEAGE_READY_NOT_WINDOW_PASS`; the 24h window is not complete.
- `P1-DATA-4` is source-closed: passive healthcheck `[41]` now treats scanner
  market would-block contradictions as WARN-only calibration evidence, not hard
  FAIL. This matches the 2026-05-08 scanner boundary: scanner is always-on
  infrastructure and cannot hard-gate opens, closes, live auth, or order
  dispatch.
- `W-AUDIT-1` is source-closed: CLAUDE §三/§四/§五/§十 runtime/lease drift
  synced, W-C authorization file added, AMD §5.4.1 recorded, docs/README and
  SCRIPT_INDEX catch-up completed, SPECIFICATION_REGISTER now includes LG-X,
  active SM-03/EX-03, ARCH-02/03, AUDIT-13, CONTEXT glossary entries, ADR
  0015..0019, and MIT/BB workspace READMEs.
- **2026-05-08 12-Agent Full Audit + PA Fix Plan land**：12 audit (FA / AI-E /
  E5 / E4 / E3 / CC / QC / MIT / BB / TW / R4 / A3) reports written to
  `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-08--*.md`. PA
  integrated 88 unique findings (de-duped from 142 raw) into 7 waves
  W-AUDIT-1..7 with ~140h estimated. Top 30 critical/high 80% VERIFIED via
  grep + ssh trade-core PG. Full plan archived at
  `srv/2026-05-08--full_audit_fix_plan.md` and PA workspace
  `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md`.
  6 cross-agent consensus criticals (K-1..K-6); K-6 (LG-5 reviewer 0 row)
  is DISPUTED — PG actual 22,790 row, reviewer is active. 5 PM/operator
  decision points (`P0-DECISION-AUDIT-1..5`) below need operator sign-off
  before downstream IMPL fully unblocks.

## Dispatch Order

Do not start proposal relay, Telegram/WebChat, a second GUI, Stage 3/4, or true
live autonomy while MAG-082 runtime lineage is NO-GO.

| Rank | Wave | Owner Chain | Target Window | Exit Criteria |
|---:|---|---|---|---|
| 1 | `W-A` Executor fake-live runtime smoke | PM -> E4 -> PM | DONE 2026-05-07 | Proved the loaded `P1-FAKE-1` path routes explicit `live_demo` metadata through real Rust IPC without exchange order, DB write, or Python-only fake success. |
| 2 | `W-B` Runtime decision-spine lineage wiring | PM -> PA -> E1 -> E2 -> E4 -> PM | DONE 2026-05-08 | Runtime shadow path writes nonzero typed decision objects, edges, and idempotency keys for demo/live_demo without changing trading authority. |
| 3 | `W-C` New MAG-082 Stage 2 evidence window | PM -> E3 -> E4 -> QA -> PM | ACTIVE 2026-05-08 | Fresh 24h demo/live_demo canary proves StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease/idempotency -> ExecutionReport. |
| 4 | `W-D` MAG-083 / MAG-084 | QA -> PM | after W-C PASS only | Final release audit PASS, then operator sign-off. |
| 5 | `W-E` OpenClaw read-only observability expansion | PM -> PA -> E1 -> E2 -> E4 -> PM | DONE 2026-05-07 | Added `/brief/latest`, `/diagnostics`, and `/escalations` as backend-authored view models. |
| 6 | `W-F` Edge/data quality and Live Gate foundation | PM -> QC/MIT/PA -> E1/E4 -> PM | after W-A; before true-live | Work through residual WARN cluster, H0 production caller, pricing binding, and supervised-live state machine. |
| 7 | `W-G` Proposal/approval/mobile relay | PM -> CC/FA/PA -> E1/E2/E4 -> PM | BACKEND FOUNDATION DONE 2026-05-07 | Gateway/console may create proposals and relay approval/reject intent into the `openclaw.*` ledger. No direct order/config/live-auth authority; external Telegram/WebChat/mobile adapters remain disabled until separately configured. |
| 8 | `W-AUDIT-1` Docs sync + governance compliance | TW + R4 + PM + PA | DONE 2026-05-09 | CLAUDE.md §三/§五/§四 lease drift sync, AMD §5.4.1 amendment, W-C authorization file, docs/README +50 entries, SPECIFICATION_REGISTER LG-X + SM-03/EX-03/ARCH-02/03 + AUDIT-13, CONTEXT.md glossary, ADR-0015..0019, SCRIPT_INDEX, MIT/BB workspace READMEs. |
| 9 | `W-AUDIT-2` Security IMPL (4 HIGH) | E1×4 並行 + E2 + E4 + E3 | NEXT 2026-05-09/10 (~7-8h, after W-AUDIT-1) | F-24 phase4 0 actor / F-25 scout 0 require_operator / F-23 0.0.0.0 binding / F-03 lease audit channel writer wire (4h) / layer2 +chmod 0o600. |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live + 5-Agent decision spine (mount W-A/W-B) | E1 + E1a + E2 + E4 + PA + PM | NEW 2026-05-08 (~10h, 2 sessions, after W-AUDIT-2 #4) | F-01 lambda:True 移除 + TOML × 3 PM 決策 / F-17 GUI dynamic / F-15 lease flip→writer e2e test / SM-05 spec 補；mounts W-A close-out condition + W-B regression test. |
| 11 | `W-AUDIT-4` ML 基座 + dead schema (mount W-F-1) | E1×6 並行 + MIT + E2 + E4 | NEW 2026-05-08 (~30h, 3 sessions, after W-AUDIT-1) | V068-V076 9 條 migration: retention 9 表 / compression / drop 4 dead / feature_baselines writer / edge cycle / outcome backfill / Guard retrofit / engine_mode CHECK / 5 ML cron + FUP-2 deploy. |
| 12 | `W-AUDIT-5` 性能/結構/CI/跨平台 (split 5a + 5b) | E1×6 並行 + E5 + E2 + E4 | NEW 2026-05-08 (~17h+17h, 2 sessions) | 5a: F-12 runner.rs split 5 sibling / F-20 drop 952MB damaged / F-21 strip / F-26 .github CI aarch64-apple-darwin / F-27 字典 4 drift / test_h_state split. 5b: orjson / deepcopy / ai_budget RwLock / event_consumer split. |
| 13 | `W-AUDIT-6` 策略 + 量化 promotion gate (mount P0-EDGE-1) | E1×5 + QC + E2 + E4 + PM | NEW 2026-05-08 (~30h+VaR, 3 sessions, PM 決策後) | PM 5 策略 verdict (1d) → F-13 DSR/PBO/CPCV promotion gate / Kelly tier config / fast_track config / funding clean / bb_breakout cooldown 統一 / bb 1m→5m RFC / ma_crossover R:R 重寫 / VaR/CVaR/EVT (3d after). |
| 14 | `W-AUDIT-7` AI 棧 + GUI/UX 收口 | E1×4 + AI-E + A3 + E2 + E4 + ops | NEW 2026-05-08 (~25h, 2 sessions, parallel-able) | F-07 operator API key + Layer2 manual / F-cea-env CostEdgeAdvisor / F-strategist-cap / F-30 prompt() × 6 → custom modal / F-system-mode-confirm 5s 倒計時 / F-strategy-confirm 視覺隔離 / F-28 ContextDistiller IMPL / Layer2 autonomous loop. |

## P0 — True-Live Blockers

| ID | Status | Task | Acceptance |
|---|---|---|---|
| `P0-AGENT-1` | ACTIVE | Runtime Agent Decision Spine lineage | One-shot runtime proof now includes Decision Lease bypass lineage (`chains_with_lease=6`); continue W-C until the 24h Stage 2 window passes. |
| `P0-AGENT-2` | ACTIVE | MAG-082 Stage 2 rerun | New operator-approved window is collecting evidence; PASS requires the 24h window. Replay cannot substitute. |
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
| `P0-DECISION-AUDIT-1` | DONE | AMD-2026-05-02-01 §5.4 流程搶跑補件 | Added `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md` and AMD §5.4.1. Flag remains ON for W-C shadow evidence only; no true-live auth / no order authority / no MAG-083/084. |
| `P0-DECISION-AUDIT-2` | PENDING-OPERATOR | shadow_mode TOML × 3 設計意圖鎖定（FA push back #2） | PA 推薦 (a)：「demo TOML 是 W-A demo fail-close，等 P0-EDGE-1 後 demo 翻 false 啟 shadow→live promotion」+ 補 SM-05 spec。或 (b)「5-Agent 鏈是 shadow-only 觀察工具，真實下單永遠走 Rust tick_pipeline 直接路徑」。Operator 必擇一寫進 amendment。 |
| `P0-DECISION-AUDIT-3` | DONE | CLAUDE.md §三 數值 vs runtime drift 防線改造 | §三 now keeps only active current state, every runtime number carries timestamp/healthcheck id, and stale completed history points to archive/report sources. |
| `P0-DECISION-AUDIT-4` | PENDING-OPERATOR | 5 策略 verdict 採納 | PA 推薦 (ii)：保留 grid CONDITIONAL（限 ORDIUSDT）+ ma_crossover REVISE + bb_breakout REJECT 1m→REVISE 5m + funding_arb RETIRE（完全清 RiskConfig）+ bb_reversion 配 ma pair。或 (i) 全 RETIRE 重做 / (iii) 觀望 P0-EDGE-1 後決。 |
| `P0-DECISION-AUDIT-5` | PENDING-OPERATOR | openclaw_core 9 模組 + Layer 2 自主循環 14 天 0 動作 sunset（FA push back #3） | PA 推薦 (i)+(ii)：ADR-0015 「openclaw_core 9 模組永久 sunset」決議 + W-AUDIT-5 接續 drop；ADR-0017「Layer 2 GUI-only by design」+ CLAUDE.md §五 圖示更正。或 (ii) 排 W-AUDIT-5 P2 修 / (iii) 接受長期共存。 |

## P1 — Next Engineering Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `P1-FAKE-1` | 1 | DONE — executor fake-live smoke | Linux runtime smoke passed: Rust IPC path exercised, no exchange order, no DB write. |
| `P1-OPENCLAW-3` | 2 | DONE — read-only brief/diagnostics/escalations APIs | Backend-authored view models from durable stores only; no raw frontend table stitching. |
| `P1-OPENCLAW-6/7` | 2 | DONE — proposal/approval relay backend foundation | V065 `openclaw.*` ledger applied on Linux; proposal create + approve runtime smoke passed with `side_effect_executed=false`; `[54]` PASS. |
| `P1-AGENT-OBS-1` | 2 | DONE — explicit lineage healthcheck | `[55] agent_decision_spine_lineage` distinguishes disabled / enabled-empty / incomplete / report-pending states and surfaces `MAG-082 readiness=*`; `OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED=1` escalates WARN to FAIL. |
| `P1-AGENT-RUNTIME-1` | 2 | DONE — runtime decision-spine + lease lineage | Linux `trade-core` is running `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` and `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`; `[55]` PASSed after `503eeb33` with objects=290/290, edges=232/232, idempotency=58/58, chains=58, `chains_with_lease=33`, reports=58. W-C/MAG-082 still needs the 24h window PASS. |
| `P1-DATA-1` | 3 | Runtime-reloaded WARN cluster: `[14]`, `[37]`, `[40]`, `[45]` | `[14]` distinguishes risk/cost gate suppression from writer-health evidence; `[37]` ignores recovered historical failures; `[40]` catches combined demo/live_demo negative cells and `LABUSDT` grid block source is now runtime-reloaded as of 2026-05-08; `[45]` accepts recent AccountManager fee-use proof during rejected-only demo/live_demo no-fill windows. Monitor row rolloff after reload. |
| `P1-DATA-2` | 3 | Source-fixed `[42b]` / `[42c]` low-sample attribution watch | Settled attribution ratio failures stay fail-closed, but low-sample strategies now render as `LOW_SAMPLE(n, need)` sample-maturity watch instead of misleading `0.000` ratio drift; low-sample strategies still defer promotion until mature. |
| `P1-DATA-3` | 3 | Source-fixed `[51]` scanner opportunity calibration watch | `[51]` now requires mature `opportunity_positive` samples before PASS, reports `MATURE/LOW_SAMPLE(n, need)`, and keeps scanner opportunity shadow-only when only exploration positive LCB samples exist or calibrated samples are immature. |
| `P1-DATA-4` | 3 | DONE — source-fixed `[41]` scanner would-block evidence semantics | `[41] scanner_market_gate_confirmation` no longer hard-fails when legacy scanner would-block evidence later realizes non-negative; it returns WARN calibration evidence because scanner is always-on infrastructure, not trading authority. |
| `P1-EDGE-1` | 3 | Source-fixed ma_crossover LABUSDT block + bb_breakout diagnosis | Runtime diagnosis: 7d ma_crossover combined demo/live_demo is negative mainly from `LABUSDT` (`n=6 avg=-244.54bps`), so `LABUSDT` is source-blocked for ma_crossover new entries in risk configs while close/reduce remains allowed; bb_breakout stays demo-only/live-disabled with low negative sample (`7d n=10 avg=-5.06bps`) pending more evidence. |
| `P1-EDGE-2` | 3 | funding_arb 14d audit | Run the 2026-05-16 audit before retention or deprecation decisions. |
| `P1-REPLAY-1` | 4 | Recorder-history maturity | Build longer local BBO/orderbook/latency history for S1/S1+ calibration; never fabricate old microstructure. |
| `P1-REPLAY-2` | 4 | DONE — runtime-applied replay artifact type cleanup | V066 applied twice on Linux for idempotency, constraints verified, rollback smoke passed, and runtime reloaded with `restart_all.sh --keep-auth` on 2026-05-08. New finalize rows can use `replay_report`; legacy `pnl_summary` remains readable. |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | Source is active; continue audit-row and attribution health monitoring. |
| `P1-AUDIT-DOCS-1` | 2 | DONE — W-AUDIT-1 docs sync chain | CLAUDE.md §三/§五/§四/§十 sync, AMD §5.4.1, W-C operator auth file, docs/README catch-up, SPECIFICATION_REGISTER LG-X / SM-03 / EX-03 / ARCH-02/03 / AUDIT-13, CONTEXT glossary, ADR-0015..0019, SCRIPT_INDEX, and MIT/BB workspace READMEs completed. |
| `P1-AUDIT-SEC-2` | 2 | W-AUDIT-2 security IMPL chain (4 HIGH from E3) | F-24 phase4_routes.py:822/832 +actor +require_scope_and_operator (E1-a 1h) + F-25 scout_routes.py:325/431 (E1-a 0.5h same PR) + F-23 restart_all.sh:489 + clean_restart.sh:390 + fresh_start.sh + deploy/README `--host 0.0.0.0` → `${OPENCLAW_BIND_HOST:-127.0.0.1}` + Tailscale doc (E1-b 1.5h) + F-03 `spawn_lease_transition_pipeline` 接線到 main.rs/pipeline_ctor.rs (E1-c 4h, blocks W-AUDIT-3 F-15 e2e test) + ai_service_listener.py:149 chmod 0o600 (E1-d 0.2h). Parallel sub-agents; depends on W-AUDIT-1. |
| `P1-AUDIT-RUNTIME-3` | 2 | W-AUDIT-3 ExecutorAgent fake-live (mounts W-A close-out + W-B regression) | F-01 executor_agent.py:223-224 lambda:True 移除（after P0-DECISION-AUDIT-2 operator 拍板）+ F-17 tab-settings.html:393 dynamic 改 `/api/v1/governance/lease-router/status` (E1-b 1h) + F-15 lease flip→writer→DB row e2e regression test (E4 4h, depends on W-AUDIT-2 #4 F-03) + SM-05 spec / ExecutorConfigCache polling design (PA+PM 1h). 2 sessions; depends on W-AUDIT-2 F-03. |
| `P1-AUDIT-ML-4` | 3 | W-AUDIT-4 ML 基座 + dead schema (mounts W-F-1) | V068-V071 drop dead schema (4 條, MIT+E1-b 4h) + V072 feature_baselines writer + helper script (MIT+E1-c 4h) + V073 edge_estimate_snapshots cycle hourly cron (E1-c 3h) + V074 decision_outcomes daily backfill (E1-d 3h) + V075/V075b retention + compression policies 9 表 (E1-a+MIT 5h) + V076 retrofit Guard A for V062/V063/V065 (E1-e 1h) + F-29 trading.fills.engine_mode='demo_archive_20260418' 6,616 row CHECK (E1-f 2h) + F-08 5 ML 腳本 cron (thompson/optuna/cpcv/dl3/weekly_report, E1+ops 3h) + F-09 sibling FUP-2 commit `34211ab4` E4 regression + merge + deploy (E4+ops 4h, passive wait). Heavy parallel; 3 sessions; depends on W-AUDIT-1. |
| `P1-AUDIT-PERF-5` | 3 | W-AUDIT-5a 性能/結構/CI urgent | F-12 runner.rs 2467 LOC hard violation split 5 sibling (config/scheduler/reporter/calibrator/metrics, E1-a 6h) + F-20 DROP `trading.*_damaged_20260414_130607` 4 表 909MB (E1-b+ops 2h, NAS dump 先) + F-21 Cargo.toml `[profile.release] strip="symbols"` (E1-c 0.5h) + F-26 `.github/workflows/ci.yml` cargo check aarch64-apple-darwin + linux-gnu matrix (E1-d 4h) + F-27 字典 4 drift L5-1..L5-4 + G9-02 章節補 (TW or BB 1.5h) + test_h_state_query_handler.py 2641 split (E4 3h). Heavy parallel; 1 session ~17h. |
| `P1-AUDIT-STRATEGY-6` | 3 | W-AUDIT-6 策略 verdict + DSR/PBO promotion gate (mounts P0-EDGE-1) | After P0-DECISION-AUDIT-4 operator 拍板：F-13 `learning_engine/promotion_gate.py` DSR/PBO/CPCV 強制 promotion gate (QC+E1-a 8h, mounts LG-2 IMPL) + Kelly tier 8/6/4 → RiskConfig.kelly.{young/mature/established}_fraction (E1-b+QC 3h) + per_trade_risk_pct 雙 SSOT 統一 0.1% (kelly_sizer.rs:109) + fast_track 15%/5%+3σ → RiskConfig (E1-c 1h) + funding_arb 完全清除 RiskConfig schema 段 (E1-d+QC 1h) + bb_breakout cooldown 600k vs 300k 統一 (E1-e 0.3h). Plus QC heavy: bb_breakout 1m→5m RFC (4h spec + 1d IMPL) + ma_crossover R:R trailing/TP 重寫 (1d). VaR/CVaR/EVT 排 W-AUDIT-6c (3d 後期). 3 sessions; depends on W-AUDIT-1 + W-AUDIT-3. |
| `P1-AUDIT-AI-UX-7` | 3 | W-AUDIT-7 AI + GUI/UX 收口 | F-07 operator GUI ANTHROPIC_API_KEY + Layer2 manual trigger 觀察 7d (operator 5min) + F-cea-env `OPENCLAW_COST_EDGE_ADVISOR=1` env + restart (ops 0.5h) + F-strategist-cap RiskConfig strategist max_param_delta_pct 30%→50% (E1 1h) + F-30 governance prompt() × 4 + learning prompt() × 2 → custom modal (A3+E1 4h) + tab-system.html:243-252 live_reserved 5s 倒計時 + hold-to-confirm (A3+E1 2h) + tab-strategy/live/paper Stop/Pause/Delete 視覺隔離 (A3+E1 3h). W-AUDIT-7b: F-28 ContextDistiller IMPL (PA+E1 8h, 推遲到 LG-2 IMPL 之後). W-AUDIT-7c: Layer2 autonomous loop hourly L1 triage cron (E1+AI-E 8h, 推遲下個 cycle). 2 sessions urgent; can parallel with W-AUDIT-3..6. |

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
| `P2-AUDIT-PERF-5b` | W-AUDIT-5b 性能優化次層（after 5a）| json.loads/dumps 501 處 → orjson (E1-f 3h) + Python copy.deepcopy 10 處 → frozen dataclass (E1-g 6h) + ai_budget tracker 16+ 鎖 → RwLock + per-strategy ArcSwap (E1-h 4h) + event_consumer/loop_handlers + dispatch 1144+1195 再拆 (E1-e 4h)。 |
| `P2-AUDIT-VAR-6c` | W-AUDIT-6c portfolio VaR/CVaR/EVT IMPL | After 5 策略 verdict 落地：portfolio_var.py + cvar.py + EVT/GPD tail fit + LUNA/FTX stress test + block bootstrap CI (QC+MIT+E1, ~3d)。 |
| `P2-AUDIT-LAYER2-7c` | W-AUDIT-7c Layer 2 autonomous loop | Hourly L1 triage cron + ContextDistiller wire (E1+AI-E ~8h)。Depends on W-AUDIT-7a operator API key 7d 累積觀察。 |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset (after P0-DECISION-AUDIT-5) | 待 ADR-0015 通過後 drop attention.rs / attribution.rs / backtest.rs / cognitive.rs / dream.rs / message_bus.rs / opportunity.rs / order_match.rs / portfolio.rs ~4468 行 Rust dead code。 |

## Schedule

Dates are planning windows, not automatic authorization.

| Date | Work | Gate |
|---|---|---|
| 2026-05-07/08 | `W-A` executor fake-live runtime smoke | No rebuild unless operator asks. |
| 2026-05-08 | `W-B` runtime decision-spine lineage wiring | DONE: operator-authorized env flip + rebuild/restart completed in shadow mode. |
| 2026-05-09 | 3C 7d audit | Run `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` if still relevant to current runtime history. |
| 2026-05-08+ | New Stage 2 evidence window | ACTIVE after operator-authorized rebuild/restart; requires 24h PASS before MAG-083/MAG-084. |
| 2026-05-11/12 | MAG-083/MAG-084 candidate | Only if new MAG-082 report PASSes. |
| 2026-05-15 | Edge / Decision Lease canary decision review | Use current edge data; do not promote if MAG-082 lineage is still NO-GO. |
| 2026-05-16 | funding_arb 14d audit | Run `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`. |
| 2026-05-09 | W-AUDIT-1 docs sync | DONE. PA fix plan §6 W-AUDIT-1 source-closed. |
| 2026-05-09/10 | W-AUDIT-2 security IMPL | NEXT after W-AUDIT-1; ~7-8h, 1 session. 4 HIGH security fixes (phase4 / scout / 0.0.0.0 / lease audit). |
| 2026-05-10/12 | W-AUDIT-3 ExecutorAgent fake-live | After W-AUDIT-2 #4 (F-03 lease audit channel); blocks on `P0-DECISION-AUDIT-2`; ~10h, 2 sessions. |
| 2026-05-10..18 | W-AUDIT-4 ML 基座 + dead schema | After W-AUDIT-1; parallel with W-AUDIT-3/5/6/7; ~30h, 3 sessions. |
| 2026-05-10..14 | W-AUDIT-5a 性能/結構/CI | After W-AUDIT-1; parallel; ~17h, 1 session. |
| 2026-05-15..22 | W-AUDIT-6 策略 + DSR/PBO promotion gate | After `P0-DECISION-AUDIT-4` operator 5 策略 verdict + W-AUDIT-1/3; ~30h, 3 sessions. |
| 2026-05-12..16 | W-AUDIT-7 AI + GUI/UX 收口 | Parallel; operator API key 7d 觀察 + GUI fix; ~25h, 2 sessions urgent (7a) + 7b/7c 後期。 |
| 2026-06-15 | Supervised live target (悲觀帶) | Conditional on W-AUDIT-1..7 完成 + 5 PENDING-OPERATOR 拍板 + 5 P0-LG/OPS 條目 + W-A/W-B/W-C/W-D PASS. PA panorama 偏向悲觀。 |

## Dispatch Rules

- Use PM-first triage for every wave.
- Implementation work: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`, with
  roles skipped only when explicitly justified.
- Security/deploy/runtime work: `PM -> E3 -> BB if exchange-facing -> PM`.
- Quant/data decisions: `PM -> QC -> MIT -> AI-E if model economics matter ->
  PM`.
- Commit each green checkpoint with subject and body, push to origin, then
  sync Linux by fast-forward.
- Do not rebuild, restart, mutate live auth, change scanner evidence contract, unlock
  executor shadow, enable lease-router, or add OpenClaw write/proposal routes
  unless the operator explicitly authorizes that action.

## Handoff Checks

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

## Reference — 2026-05-08 Full Audit Fix Plan

- **Sign-off archive**: `srv/2026-05-08--full_audit_fix_plan.md`（PM banner + PA 原文 543 行）
- **PA workspace original**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md`
- **12 audit reports**: `srv/docs/CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-08--*.md`
- **Cross-agent consensus**: K-1..K-6 critical (見 fix plan §3.1)；K-6 (LG-5 reviewer 0 row) DISPUTED — 真實 PG 22,790 row。
- **W-AUDIT-1 closure**: 5 策略 7d gross PA 直查 demo -26.44 USDT / live_demo +0.43 已同步到 CLAUDE §三；舊 §三 的 -6.98 USDT 是 2026-05-03 stale，不再作為 current-state。`[40]` / `[33]` / `[42b]` 等數字改以 2026-05-08/09 W-AUDIT-1 facts 為準。
