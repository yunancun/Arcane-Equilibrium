# 玄衡 TODO — Active Dispatch Queue

Version: v15
Date: 2026-05-09
Status: PM replan after 12-agent adversarial verification of W-AUDIT-1..7 24h fix sprint; v15 records verification verdict + lifts verified-closed details to `docs/archive/2026-05-09--w_audit_verified_closed_archive.md` + mounts 5 NEW-ISSUE + 4 NEW-VULN as active P0/P1

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
- `W-AUDIT-2` is source-closed: Phase4 weekly review, Scout signal/event, and
  Layer2 trigger mutating routes now require operator+scope gates; restart
  scripts/docs default Trading API bind to loopback via `OPENCLAW_BIND_HOST`;
  AI service Unix socket is chmod `0600`; Rust boot wires
  `spawn_lease_transition_pipeline` into Paper/Demo/Live GovernanceCore audit
  emitters. No rebuild/restart/runtime authority change was performed in this
  source checkpoint.
- **2026-05-08 12-Agent Full Audit + PA Fix Plan land**：12 audit (FA / AI-E /
  E5 / E4 / E3 / CC / QC / MIT / BB / TW / R4 / A3) reports written to
  `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-08--*.md`. PA
  integrated 88 unique findings (de-duped from 142 raw) into 7 waves
  W-AUDIT-1..7 with ~140h estimated. Full plan archived at
  `srv/2026-05-08--full_audit_fix_plan.md`.
- **2026-05-09 24h Fix Sprint** (operator) — 28 commits between `72f05aa0..7fccad06`
  covering W-AUDIT-1/2/3/5/7 source/test work + V077 columnstore hotfix.
- **2026-05-09 12-Agent Adversarial Verification land**：each original audit
  proposer ran adversarial fix verification. Reports at
  `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-09--*_verification.md`.
  Integrated summary at `srv/2026-05-09--audit_fix_verification_summary.md`.
  Tally: **319 verification points → ✅ 74 (23%) / ⚠️ 66 (21%) / ❌ 120 (38%) /
  🔄 6 (2%) / 🆕 53 (17%)**. Verified-closed sub-task details lifted to
  `docs/archive/2026-05-09--w_audit_verified_closed_archive.md`.
- **W-AUDIT-1..7 verification verdict**:
  - W-AUDIT-1 docs sync: ⚠️ partial close (R4 CRITICAL × 5 真 closed only 2/5
    at verification time; follow-up `P0-AUDIT-NEW-LG-X-05` is now closed;
    CCAgentWorkSpace 表仍 17 agent 缺 MIT/BB; archive/ 仍 7/51 索引)
  - W-AUDIT-2 security: 🔄 source-only close, runtime not verified
    (lease_transitions 0 row; E3 NEW-VULN-2)
  - W-AUDIT-3 fake-live: ⚠️ true partial (F-17 ✅ / F-15 e2e DB row coverage
    opt-in default early-return / F-01 lambda:True 0% modified, blocks on
    `P0-DECISION-AUDIT-2`)
  - W-AUDIT-4 ML 基座: ❌ downgraded fix (V068/V070/V071 reclassification
    guard COMMENT only; row count still 0; cron not installed; attribution_chain_ok
    24h 0.0188% still catastrophic)
  - W-AUDIT-5 性能/結構: ⚠️ real progress + critical mismatch
    (F-12 runner.rs 2467 UNCHANGED — commit modified `bin/replay_runner.rs`
    1599→626, NOT the original 2467-LOC `runner.rs`; binary 25→20.6 MB ✅)
  - W-AUDIT-6 策略: ⏸ untouched (0/20 量化 fixes; blocks on `P0-DECISION-AUDIT-4`)
  - W-AUDIT-7 GUI: ✅ real GUI progress + 🆕 functional regression
    (4/5 critical close; live_reserved 5s+hold-to-confirm 業界標準;
    BUT 🆕 NEW-ISSUE-1 LiveDemo pipeline auth_missing — V077 hotfix
    `restart_all.sh --keep-auth` 過程 auth file 遺失)
- **`P0-DECISION-AUDIT-1` ✅ closed** (W-C operator auth file + AMD §5.4.1)
- **`P0-DECISION-AUDIT-3` ✅ closed** (§三 5 stale 數字真修 + healthcheck id)
- **`P0-DECISION-AUDIT-2/4/5` 仍 PENDING-OPERATOR** — operator 24h 內拍板
  最緊要：P0-DECISION-AUDIT-2 解 F-01 fake-live 死鎖；P0-DECISION-AUDIT-4 解
  W-AUDIT-6 全套 IMPL 鎖。
- **5 NEW-ISSUE / 4 NEW-VULN 加為 active P0/P1** (見下表)。

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
| 9 | `W-AUDIT-2` Security IMPL (4 HIGH) | E1×4 並行 + E2 + E4 + E3 | DONE 2026-05-09 | F-24/F-25 mutating learning routes gated by operator+scope, F-23 Trading API bind default loopback via `OPENCLAW_BIND_HOST`, F-03 lease transition writer wired into all active pipelines, Layer2 trigger gated, AI service socket chmod 0600. Source/test only; no rebuild/restart. |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live + 5-Agent decision spine (mount W-A/W-B) | E1 + E1a + E2 + E4 + PA + PM | PARTIAL 2026-05-09 (`da2dba25`) | F-17 dynamic `/api/v1/governance/lease-router/status` source patch added; F-15 lease flip→writer e2e regression added; SM-05 polling design draft added as AMD-2026-05-09-01. F-01 lambda:True removal + final SM-05 authority semantics still block on P0-DECISION-AUDIT-2 operator decision. |
| 11 | `W-AUDIT-4` ML 基座 + dead schema (mount W-F-1) | E1×6 並行 + MIT + E2 + E4 | ACTIVE 2026-05-09 (~30h, 3 sessions, after W-AUDIT-1) | V068/V070/V071 source/test reclassify the dead-schema plan as metadata-only retention/review guards after code-reference audit; V069 corrected observability cleanup source/test drops only empty `observability.scorer_predictions` with RESTRICT; V072 contract guard source/test locks `feature_baselines` to Rust drift-detector 34-dim `features.online_latest` semantics and prevents accidental 17-dim `decision_features` seeding; V073 edge snapshot cycle wrapper/contract, V074 decision_outcomes live-lane backfill helper/wrapper/index guard, V075 corrected retention/compression, V076 Guard A retrofit, V077 F-29 archive CHECK with Timescale columnstore trigger fallback, and F-08 ML training maintenance cron source/test added. V068-V076 were auto-applied during the 2026-05-09 authorized rebuild/restart; V077 initially hit Timescale columnstore CHECK limitation and was hotfixed before final engine restart. Cron not installed. Remaining: V072 still needs a real 34-dim historical baseline writer design, and F-09 FUP-2 deploy. Source work may proceed; DB apply/deploy remains separate authorization. |
| 12 | `W-AUDIT-5` 性能/結構/CI/跨平台 (split 5a + 5b) | E1×6 並行 + E5 + E2 + E4 | ACTIVE 2026-05-09 (~17h+17h, 2 sessions) | F-21 source/test added `rust/Cargo.toml [profile.release] strip = "symbols"`; F-26 source/test added GitHub Actions Rust release-check matrix for `x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`; F-27 source/test corrected Bybit API dictionary drift for `intervalTime`, `/v5/user/query-api`, and G9-02, while documenting the official `account-ratio` daily-period contradiction instead of inventing runtime truth; F-test-h-state source/test split the 2641 LOC compatibility suite into `tests/h_state_query/` siblings while keeping the historical pytest path as a 9-line collector; F-12 source/test split `replay_runner.rs` from 1599 LOC to a 626 LOC orchestration entrypoint plus `src/bin/replay_runner/{manifest,manifest_tests,config,calibration}.rs`, with LOC static regression; W-AUDIT-5b event_consumer source/test split moved `dispatch.rs` tests to `dispatch_tests.rs` and Arm C exchange-event handling to `loop_exchange.rs`; W-AUDIT-5b state-machine snapshot source/test replaced the 10 generic `copy.deepcopy` snapshot callsites with explicit `clone()` snapshots over JSON-like mutable fields; W-AUDIT-5b orjson foundation/runtime-hot-path source/test added `json_fast`, migrated `ai_service_listener.py`, `ipc_client_sync.py`, `ipc_client.py`, `ollama_client.py`, and `local_llm_factory.py`; W-AUDIT-5b ai_budget source/test replaced the read-heavy config snapshot `RwLock` with `ArcSwap<BudgetConfig>` while keeping mutable usage counters under async `RwLock`; no release build/restart. Remaining 5a: F-20 damaged table dump+drop ops. Remaining 5b: canonical/byte-contract JSON paths stay stdlib until explicit byte tests; any per-strategy budget model is a separate schema/policy design, not a cache-swap mechanic. |
| 13 | `W-AUDIT-6` 策略 + 量化 promotion gate (mount P0-EDGE-1) | E1×5 + QC + E2 + E4 + PM | NEW 2026-05-08 (~30h+VaR, 3 sessions, PM 決策後) | PM 5 策略 verdict (1d) → F-13 DSR/PBO/CPCV promotion gate / Kelly tier config / fast_track config / funding clean / bb_breakout cooldown 統一 / bb 1m→5m RFC / ma_crossover R:R 重寫 / VaR/CVaR/EVT (3d after). |
| 14 | `W-AUDIT-7` AI 棧 + GUI/UX 收口 | E1×4 + AI-E + A3 + E2 + E4 + ops | ACTIVE 2026-05-09 (~25h, 2 sessions, parallel-able) | F-30 source/test replaced native `prompt()` in learning + governance flows with shared custom prompt modal, including select pickers for tier/confidence inputs; F-system-mode-confirm source/test/browser-smoke added `live_reserved` 5s countdown + hold-to-confirm; F-strategy-confirm source/test/browser-smoke added risk-zoned Stop/Pause/Delete controls across strategy/live/paper and moved Paper/Live native confirm paths to custom modal confirm. No backend/restart. Remaining: F-07 operator API key + Layer2 manual / F-cea-env CostEdgeAdvisor / F-strategist-cap / F-28 ContextDistiller IMPL / Layer2 autonomous loop. |

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
| `P0-NEW-ISSUE-1` | ACTIVE 2026-05-09 | LiveDemo pipeline auth_missing → engine boot demo-only (CRITICAL functional regression) | FA NEW-1 verified via `.codex/WORKLOG.md:332`：W-AUDIT-7 階段 V077 hotfix `restart_all.sh --rebuild --keep-auth` 過程 authorization file 遺失；LiveDemo 從 5/8 真實 fills 流量 → 5/9 變 0。Source/test partial: §三 now records `auth_missing`, and passive healthcheck `[56] live_pipeline_active` was added because `[Xb]` is already occupied by `pipeline_triangulation`. `[56]` FAILs when live slot is configured but signed auth is missing or `pipeline_snapshot_live.json` is stale. Remaining Action: (1) operator renews authorization via `_write_signed_live_authorization()` Python route; (2) RCA `--keep-auth` 為何失效; (3) rerun healthcheck to confirm `[56]` PASS after auth renewal. |
| `P0-NEW-VULN-1` | DONE 2026-05-09 | launchd plist 安全弱點 (HIGH) | Fixed Mac launchd Trading API template to bind `127.0.0.1` instead of `0.0.0.0`; `launchd_preflight.sh` now rejects all-interface Trading API plist binds; Batch E runtime ownership static regression covers the plist and preflight guard. Source/test only; no launchd load/unload or runtime change. |
| `P0-NEW-VULN-2` | ACTIVE 2026-05-09 | lease audit runtime 0 emit (HIGH) | E3 NEW-VULN-2 verified: W-AUDIT-2 #4 `spawn_lease_transition_pipeline` 接到 main.rs:657 是 source 真改但 runtime 未 restart 落地；lease_transitions PG row count 仍 0。Action: 觸發 engine restart + verify row count > 0。等 NEW-ISSUE-1 LiveDemo 修復後一併 restart。 |
| `P0-AUDIT-NEW-LG-X-05` | DONE 2026-05-09 | SPECIFICATION_REGISTER LG-X-05 缺 + LG-X-04 編號錯位 (R4 N1 CRITICAL) | Fixed in `docs/governance_dev/SPECIFICATION_REGISTER.md`: LG-X now maps historical LG-1..LG-5 as evidence window / H0 / pricing / supervised-live / constrained autonomous live; LG-X-05 registers the LG-5 constrained-autonomous RFC, eval-contract v2, R-meta amendment, and healthchecks. Live Ops moved to separate `OPS-X-01` so it no longer occupies LG-X-04. |

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
| `P1-AUDIT-SEC-2` | 2 | DONE — W-AUDIT-2 security IMPL chain | F-24/F-25/F-23/F-03 + Layer2 trigger + AI socket chmod landed with static regressions, route tests, py_compile, Rust cargo check, and lease writer tests. Runtime deploy/restart intentionally not performed. |
| `P1-AUDIT-RUNTIME-3` | 2 | W-AUDIT-3 ExecutorAgent fake-live (mounts W-A close-out + W-B regression) | PARTIAL `da2dba25`: F-17 source/API/GUI dynamic status patch added; F-15 lease flip→writer e2e regression added with opt-in `OPENCLAW_TEST_PG` DB row coverage; AMD-2026-05-09-01 draft documents SM-05 `ExecutorConfigCache` polling/fail-closed behavior. Remaining: F-01 `executor_agent.py` lambda:True removal and final SM-05 authority semantics after `P0-DECISION-AUDIT-2` operator decision. |
| `P1-AUDIT-ML-4` | 3 | W-AUDIT-4 ML 基座 + dead schema (mounts W-F-1) | ACTIVE: V068/V070/V071 source/test reclassify the original dead-schema drop/archive plan as metadata-only guards: route/cron/Rust-writer/Agent-Spine referenced tables are retained, and review-only placeholders are not destructively removed in this wave. V069 source/test corrects the observability cleanup to drop only empty `observability.scorer_predictions`; `model_performance` is retained because `canary_promoter.py` reads it, and `feature_baselines`/`drift_events` are retained for V072/drift-detector resolution. V072 source/test adds a contract guard: Linux read-only proof shows `features.online_latest` has 43 rows at 34 dims, `feature_baselines` active rows = 0, and 7d `decision_features` has 51,130 rows at 17 keys, so the MIT-proposed 17-dim writer must not seed the 34-dim drift-detector baseline. V073 source/test adds a V059 edge snapshot contract guard and a cron wrapper around `ref21_backfill_v058_v059.py --skip-instruments --skip-freeze-log --apply`; cron is not installed. V074 source/test adds live/live_demo `decision_outcomes` backfill helper + cron wrapper + pending-scan index guard. V075 source/test corrects the "9 table retention" plan to 5 hypertables + 2 plain tables + 2 views. V076 Guard A retrofit and V077 F-29 bounded archive CHECK/trigger fallback also source/test added. F-08 source/test adds `ml_training_maintenance_cron.sh` + runner covering `linucb_trainer`, `mlde_shadow_advisor`, `mlde_demo_applier`, `scorer_trainer`, and `quantile_trainer`; cron is not installed. V068-V076 auto-applied during 2026-05-09 rebuild/restart; V077 required columnstore fallback hotfix before final restart. Remaining: V072 still needs a real 34-dim historical baseline writer design + F-09 FUP-2 deploy. Heavy parallel; 3 sessions; depends on W-AUDIT-1. |
| `P1-AUDIT-PERF-5` | 3 | W-AUDIT-5a 性能/結構/CI urgent | F-21 source/test added release symbol stripping in `rust/Cargo.toml`; F-26 source/test added `.github/workflows/ci.yml` cargo release-check matrix for `x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`; F-27 source/test corrected Bybit API dictionary drift: `get_open_interest` now documents Rust `interval` -> Bybit `intervalTime`, `/v5/user/query-api` key-validation path is recorded, G9-02 UnknownHandlerGuard documents the actual runtime env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`, and the official `account-ratio` `1d` vs enum `4d` contradiction is marked exchange-smoke-required. F-test-h-state source/test split `test_h_state_query_handler.py` from 2641 LOC to a 9-line compatibility collector plus `tests/h_state_query/{common,test_core,test_h_buckets,test_agent_states}.py`, with LOC static regression. F-12 source/test split `rust/openclaw_engine/src/bin/replay_runner.rs` from 1599 LOC to a 626 LOC orchestration entrypoint plus `src/bin/replay_runner/{manifest,manifest_tests,config,calibration}.rs`, with LOC static regression. W-AUDIT-5b has also landed event_consumer split, state-machine clone snapshots, json_fast foundation/runtime IPC+local LLM hot paths, and ai_budget config `ArcSwap` source/test. No release build/restart/deploy. Remaining: F-20 DROP `trading.*_damaged_20260414_130607` 4 表 909MB (E1-b+ops 2h, NAS dump 先); canonical/byte-contract JSON paths remain intentionally stdlib until byte tests exist. Heavy parallel; 1 session ~17h. |
| `P1-AUDIT-STRATEGY-6` | 3 | W-AUDIT-6 策略 verdict + DSR/PBO promotion gate (mounts P0-EDGE-1) | After P0-DECISION-AUDIT-4 operator 拍板：F-13 `learning_engine/promotion_gate.py` DSR/PBO/CPCV 強制 promotion gate (QC+E1-a 8h, mounts LG-2 IMPL) + Kelly tier 8/6/4 → RiskConfig.kelly.{young/mature/established}_fraction (E1-b+QC 3h) + per_trade_risk_pct 雙 SSOT 統一 0.1% (kelly_sizer.rs:109) + fast_track 15%/5%+3σ → RiskConfig (E1-c 1h) + funding_arb 完全清除 RiskConfig schema 段 (E1-d+QC 1h) + bb_breakout cooldown 600k vs 300k 統一 (E1-e 0.3h). Plus QC heavy: bb_breakout 1m→5m RFC (4h spec + 1d IMPL) + ma_crossover R:R trailing/TP 重寫 (1d). VaR/CVaR/EVT 排 W-AUDIT-6c (3d 後期). 3 sessions; depends on W-AUDIT-1 + W-AUDIT-3. |
| `P1-AUDIT-AI-UX-7` | 3 | W-AUDIT-7 AI + GUI/UX 收口 | F-30 source/test/browser-smoke DONE: `common.js` now exposes shared `openPromptModal()`, learning experiment completion uses textarea + confidence select modal, governance audit/live-auth renewal/review flows use custom modal prompts and tier select pickers, and static guard prevents native `prompt()` from returning in those target files. F-system-mode-confirm source/test/browser-smoke DONE: `tab-system.html` `live_reserved` mode confirmation now disables the confirm button for 5s, rejects single-click confirmation after countdown, and submits only after a 1.2s hold-to-confirm. F-strategy-confirm source/test/browser-smoke DONE: `common.js` now defines shared action risk zones, `tab-strategy.html` visually separates Pause/Stop/Delete, `tab-paper.html` separates run/pause/stop/dual-stop and replaces `sessionStopAll()` native confirm with `openConfirmModal()`, and `tab-live.html` groups Stop/Emergency plus marks close-all/row-close actions as destructive with custom modal confirms. Remaining: F-07 operator GUI ANTHROPIC_API_KEY + Layer2 manual trigger 觀察 7d (operator 5min) + F-cea-env `OPENCLAW_COST_EDGE_ADVISOR=1` env + restart (ops 0.5h) + F-strategist-cap RiskConfig strategist max_param_delta_pct 30%→50% (E1 1h). W-AUDIT-7b: F-28 ContextDistiller IMPL (PA+E1 8h, 推遲到 LG-2 IMPL 之後). W-AUDIT-7c: Layer2 autonomous loop hourly L1 triage cron (E1+AI-E 8h, 推遲下個 cycle). 2 sessions urgent; can parallel with W-AUDIT-3..6. |

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
| `P2-AUDIT-PERF-5b` | W-AUDIT-5b 性能優化次層（after 5a）| event_consumer/loop_handlers + dispatch split source/test completed: `dispatch.rs` 1144→683, `loop_handlers.rs` 1195→717, with `dispatch_tests.rs` and `loop_exchange.rs` siblings plus LOC regression. Python state-machine snapshot source/test completed: AuthorizationObject, DecisionLeaseObject, GovernorState, and TierState now use explicit `clone()` snapshots and `state_machine_base` requires clone-backed multi-object snapshots, removing the 10 generic `copy.deepcopy` snapshot callsites while preserving isolated mutable dict/list outputs. Orjson foundation/runtime-hot-path source/test added `app/json_fast.py` with optional `orjson` fast path + stdlib fallback, declared `orjson>=3.10.0`, and migrated newline IPC plus local LLM HTTP JSON hot paths (`ai_service_listener.py`, `ipc_client_sync.py`, `ipc_client.py`, `ollama_client.py`, `local_llm_factory.py`). ai_budget source/test replaced the read-heavy `config_cache` async `RwLock` with `ArcSwap<BudgetConfig>` whole-snapshot swaps, and intentionally kept `usage_cache` under async `RwLock` because usage mutates cumulative per-scope counters. Remaining: signature/hash/replay-manifest/canonical JSON paths stay stdlib unless byte-contract tested; any per-strategy budget model would require separate schema/policy design. |
| `P2-AUDIT-VAR-6c` | W-AUDIT-6c portfolio VaR/CVaR/EVT IMPL | After 5 策略 verdict 落地：portfolio_var.py + cvar.py + EVT/GPD tail fit + LUNA/FTX stress test + block bootstrap CI (QC+MIT+E1, ~3d)。 |
| `P2-AUDIT-LAYER2-7c` | W-AUDIT-7c Layer 2 autonomous loop | Hourly L1 triage cron + ContextDistiller wire (E1+AI-E ~8h)。Depends on W-AUDIT-7a operator API key 7d 累積觀察。 |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset (after P0-DECISION-AUDIT-5) | 待 ADR-0015 通過後 drop attention.rs / attribution.rs / backtest.rs / cognitive.rs / dream.rs / message_bus.rs / opportunity.rs / order_match.rs / portfolio.rs ~4468 行 Rust dead code。 |
| `P2-AUDIT-VERIFY-1` | DOCS-1 殘缺項收口 | R4 verified W-AUDIT-1 CRITICAL × 5 真 closed 僅 2/5；剩餘需做：(C2) docs/README 補 docs/agents/ 整章 / (C3) docs/README 補 SCRIPT_INDEX 入口 / (H3) docs/README archive/ 缺漏 44 條 / (H5) docs/README CCAgentWorkSpace 表補 MIT/BB（line 727 仍寫 17 agent）/ (M5) MIT/BB workspace/README.md 位置補錯到 dir 根。詳見歸檔 §1。 |
| `P2-AUDIT-VERIFY-2` | F-12 runner.rs 真檔對齊 | E5 verified: commit `3372eb18` 改的是 `bin/replay_runner.rs`（1599→626），不是原 finding 的 `runner.rs` 2467 行檔。**原 file 仍違反 governance 2000 cap**。需 PM/PA 對齊真實 file path 並補修。 |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix | FA NEW-2 verified: V068/V070/V071 全降級為 reclassification guard（COMMENT only），row count 仍 0；6 表 0 INSERT 必另開 functional fix wave。Action: 區分「source-only checkpoint」與「functional fix complete」並接 INSERT path。 |
| `P2-AUDIT-VERIFY-4` | cron not installed (F-08) | FA NEW-3 + AI-E verified: 5 ML 訓練腳本 cron script 寫了但 cron not installed；attribution_chain_ok 24h 仍 0.0188%。Action: operator 授權 `crontab -e` 安裝 + verify 24h cron fire。 |
| `P2-AUDIT-VERIFY-5` | grid blocked_symbols selection bias 加劇 | QC NEW-1 verified: P1-EDGE-1 commit 又追加 LABUSDT；selection bias 持續加劇而非 freeze。Action: 凍結列表 + 新加入需 RFC + DSR/PBO; 計算 4 blocked symbol counterfactual 7d PnL。 |
| `P2-AUDIT-VERIFY-6` | A3 NEW-1 openConfirmModal a11y | Critical UX gap: openConfirmModal 無 Esc / 無 focus trap / 無 aria-modal。Action: 30 行 JS 對齊 openPromptModal a11y 樣式。 |
| `P2-AUDIT-VERIFY-7` | NEW-VULN-3 / NEW-VULN-4 修復 | E3 verified: cookie secure default fail-OPEN (MEDIUM) + phase4 dead code (INFO)。 |
| `P2-AUDIT-QC-STAND-ALONE` | QC 5 條 stand-alone fix（不需 P0-DECISION-AUDIT-4 拍板）| QC: (1) funding_arb schema 4 TOML 完全清除 1h / (2) Kelly tier 8/6/4 → RiskConfig.kelly.{young/mature/established}_fraction 3h / (3) bb_breakout cooldown 600k vs 300k 統一 0.3h / (4) DSR/PBO production caller 加進 promotion_pipeline.py demo gate (advisory) 8h / (5) CLAUDE.md §三 -26.44 加掛 healthcheck id 0.5h。共 ~13h。 |

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
| 2026-05-09 | W-AUDIT-2 security IMPL | DONE source/test checkpoint; no rebuild/restart. |
| 2026-05-10/12 | W-AUDIT-3 ExecutorAgent fake-live | NEXT after W-AUDIT-2 source close; F-01 blocks on `P0-DECISION-AUDIT-2`; ~10h, 2 sessions. |
| 2026-05-10..18 | W-AUDIT-4 ML 基座 + dead schema | After W-AUDIT-1; parallel with W-AUDIT-3/5/6/7; ~30h, 3 sessions. |
| 2026-05-10..14 | W-AUDIT-5a 性能/結構/CI | After W-AUDIT-1; parallel; ~17h, 1 session. |
| 2026-05-15..22 | W-AUDIT-6 策略 + DSR/PBO promotion gate | After `P0-DECISION-AUDIT-4` operator 5 策略 verdict + W-AUDIT-1/3; ~30h, 3 sessions. |
| 2026-05-12..16 | W-AUDIT-7 AI + GUI/UX 收口 | Parallel; operator API key 7d 觀察 + GUI fix; ~25h, 2 sessions urgent (7a) + 7b/7c 後期。 |
| 2026-06-15 | Supervised live target (悲觀帶) | Conditional on W-AUDIT-1..7 完成 + 5 PENDING-OPERATOR 拍板 + 5 P0-LG/OPS 條目 + W-A/W-B/W-C/W-D PASS. PA panorama 偏向悲觀。 |
| 2026-05-09 | 12-Agent Adversarial Verification land + TODO v15 | 12 verification reports written；總 tally ✅74 / ⚠️66 / ❌120 / 🔄6 / 🆕53；PM sign-off + verified-closed 細節歸檔到 `docs/archive/2026-05-09--w_audit_verified_closed_archive.md`；summary at `srv/2026-05-09--audit_fix_verification_summary.md`。 |
| 2026-05-09+ | NEW-ISSUE-1 LiveDemo auth restore + RCA | P0 急。重生 authorization file + RCA `--keep-auth`；準備一次 engine restart 同時 land NEW-VULN-2 lease audit runtime emit verification。 |
| 2026-05-10..13 | 等 P0-DECISION-AUDIT-2/4 operator 拍板 | 解 W-AUDIT-3 F-01 + W-AUDIT-6 全套 IMPL 鎖。 |

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

## Reference — 2026-05-09 Adversarial Verification + Verified-Closed Archive

- **PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_summary.md`（319 verification points 整合 + 7 wave verdict + P0-DECISION 拍板狀態 + 5 NEW-ISSUE / 4 NEW-VULN 清單）
- **Verified-closed details archive**: `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive.md`（**過時 / 已修復內容單獨存放**，避免 active TODO 膨脹）
- **12 verification reports**: `srv/docs/CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-09--*_verification.md`
- **Total tally**: ✅ 74 (23%) / ⚠️ 66 (21%) / ❌ 120 (38%) / 🔄 6 (2%) / 🆕 53 (17%)
- **Compliance score**: B- (17/30 = 56.7%) → B (21/30 = 70%) (CC verdict)
- **ML 基座達標率**: 38% → 42% (MIT verdict; attribution_chain_ok 24h 0.0188% 仍 catastrophic)
- **GUI 整體**: 7.4 → 8.1 / 10 (A3 verdict; Critical 4/5 close)
- **核心 verdict**: 24h 28 commits 是高 throughput 但典型 source-only 假進度。74 真修中**沒有任何單一 finding 真改變 fake-live 結構**；NEW-ISSUE-1 LiveDemo 停是修復過程引入的 functional regression。修復節奏需從「source-checkpoint」升為「runtime-checkpoint」。
