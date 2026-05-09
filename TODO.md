# 玄衡 TODO — Active Dispatch Queue

Version: v18
Date: 2026-05-09
Status: PM sync after 13-agent v3 adversarial verification + PA fix plan v2 DUAL-TRACK — operator 採納 PA R-1 啟動 W-AUDIT-8a Alpha Surface Foundation SPEC PHASE + W-AUDIT-9 Graduated Canary Foundation；MIT v3 第一次定位 attribution real root cause = label_close_tag NULL 98.9% (1-day fix)；BB v3 揭發 PA spec 3 條錯誤 (L25/liquidation/basis)；DUAL-TRACK: Track W 7 wave (~92h) + Track A 9 wave (~270-330h) / 6-12w；CC compliance B+→A- (27/30=90%)；v18 lifts v3 verified-closed to `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`

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
  scripts/docs no longer default Trading API to all interfaces; P0-NEW-VULN-1
  tailnet correction binds concrete Tailscale IPv4 when available, otherwise
  loopback, and rejects `0.0.0.0`; AI service Unix socket is chmod `0600`; Rust boot wires
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
- **2026-05-09 v2 Adversarial Verification land (after 34 commits)**：12 v2
  reports at `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-09--*_verification_v2.md`.
  Integrated summary at `srv/2026-05-09--audit_fix_verification_v2_summary.md`.
  v2 Tally: **259 verification points → ✅ 122 (47%) / ⚠️ 47 (18%) / ❌ 66 (25%) /
  🔄 3 (1%) / 🆕 21 (8%)**. **真實飛躍**：✅ +48 (+65%) / ❌ -54 (-45%) / 🆕 -32 (-60%)。
  v2 verified-closed details archived to
  `docs/archive/2026-05-09--w_audit_verified_closed_archive_v2.md`.
  - W-AUDIT-1: ⚠️ partial → ✅ **真 close** (R4: CRITICAL × 5 真 closed 5/5;
    LG-X-05 補完;　索引完整度 75→92%)
  - W-AUDIT-2: 🔄 source-only → ✅ **runtime verified** (V078 applied;
    learning.lease_transitions runtime rows=103; rebuild `862e79b7`)
  - W-AUDIT-3: ⚠️ → ⚠️ 真實 partial (F-01 lambda:True 真移除 + AMD §2 fail-closed;
    F-15 e2e DB row 仍 opt-in; runtime fail-closed metrics 未驗)
  - W-AUDIT-4: ❌ → ❌ 仍降級 (V068/V070/V071 reclassification COMMENT;
    row count 仍 0; cron 仍 not installed; attribution_chain_ok 24h 0.0188→0.5041%
    denominator artifact, ok_n only +47%)
  - W-AUDIT-5: ⚠️ → ✅ **F-12 真檔對齊** (replay/runner.rs 2467→1167 LOC) +
    W-AUDIT-6c portfolio tail risk gate IMPL bonus
  - W-AUDIT-6: ⏸ → ✅ **大爆發收口** (13+ commits / DSR-PBO+VaR-CVaR-EVT
    wired LIVE / Kelly RiskConfig / fast_track config / per_trade_risk_pct
    雙 SSOT 統一 / funding_arb 4 risk_config 全清 / ma_crossover R:R 重寫 /
    bb_breakout 5m IMPL；P0-V2 Donchian leak-bias 後續由 runtime snapshot
    回歸測試鎖定 `donchian_prior`)
  - W-AUDIT-7: ✅ → ✅ openConfirmModal a11y 真補 (A 級實作) +
    LiveDemo restored 三層 closure
- **5 P0-DECISION-AUDIT 全 closed**：AMD-2026-05-09-02 (`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`)
  收口 -2 (Option A) / -4 (Option ii) / -5 (Option i+ii)；ADR-0015/0017/0020 配套加入。
- **6 P0-NEW-ISSUE/VULN 全 closed**：LiveDemo auth restored + 4 NEW-VULN (launchd/lease audit/cookie/phase4) + LG-X-05 spec gap 全 closed。
- **W-AUDIT-1..7 verification verdict**:
  - W-AUDIT-1 docs sync: ⚠️ partial close (R4 CRITICAL × 5 真 closed only 2/5
    at verification time; follow-up `P0-AUDIT-NEW-LG-X-05` is now closed;
    CCAgentWorkSpace 表仍 17 agent 缺 MIT/BB; archive/ 仍 7/51 索引)
  - W-AUDIT-2 security: ✅ F-03 runtime verified after rebuild/restart
    (`learning.lease_transitions` nonzero; final spot-check rows=103, V078
    BYPASS check applied); other
    security fixes remain source/test unless separately runtime-smoked.
  - W-AUDIT-3 fake-live: ⚠️ true partial (F-17 ✅ / F-15 e2e DB row coverage
    opt-in default early-return / SM-05 Option A decided / F-01 source+test
    closed: no hidden `lambda: True` fallback; provider unavailable/exception
    fail-closes submit to shadow)
  - W-AUDIT-4 ML 基座: ❌ downgraded fix (V068/V070/V071 reclassification
    guard COMMENT only; row count still 0; cron not installed; attribution_chain_ok
    24h 0.0188% still catastrophic)
  - W-AUDIT-5 性能/結構: ⚠️ real progress; F-12 true-path mismatch closed
    (`replay/runner.rs` 2469→1166 plus `runner_tests.rs` 1299; previous
    `bin/replay_runner.rs` split remains valid; binary 25→20.6 MB ✅)
  - W-AUDIT-6 策略: ⚠️ source/test materially advanced (`bb_breakout`
    cooldown drift, Kelly tier fractions, fast_track thresholds, F-13
    DSR/PBO/CSCV gate, per_trade_risk_pct SSOT, and funding_arb RiskConfig
    cleanup are closed; ma_crossover R:R trailing/TP, bb_breakout 5m, and
    W-AUDIT-6c VaR/CVaR/EVT promotion evidence are source/test closed)
  - W-AUDIT-7 GUI: ✅ real GUI progress + 🆕 functional regression
    (4/5 critical close; live_reserved 5s+hold-to-confirm 業界標準;
    NEW-ISSUE-1 LiveDemo auth_missing restored 2026-05-09 via signed
    `/api/v1/live/auth/renew`; `--keep-auth` RCA closed: prior 01:11 UTC
    boot consumed `manual` sentinel, and restart script now warns when
    keep-auth would preserve missing auth)
- **W-AUDIT-4 V072 writer follow-through source/test added**：Rust
  `feature_baseline_writer` now rebuilds `observability.feature_baselines`
  from `trading.decision_context_snapshots.indicators_snapshot + last_price`
  by deserializing `IndicatorSnapshot` and using
  `FeatureSnapshot::to_feature_vector()` / `FEATURE_NAMES` / `FEATURE_DIM=34`.
  It is dry-run by default and requires `--apply --i-understand-this-modifies-db`
  to write; no DB apply, cron install, rebuild, or restart was performed in
  this source checkpoint.
- **W-AUDIT-4 F-09 FUP-2 deploy verified**：`34211ab4` is already in main;
  Linux `trade-core` has `edge_label_backfill_cron.sh` installed in crontab
  (`*/30 * * * *`), recent cron logs show demo + live_demo passes, and direct
  `[43] label_backfill_freshness` returned PASS with latest fill age `0.36h`
  at the 2026-05-09 read-only check. No deploy action was needed in this
  checkpoint.
- **W-AUDIT-6 first source/test checkpoint**：`bb_breakout` constructor and
  `BbBreakoutParams::default()` now share `DEFAULT_COOLDOWN_MS=300_000`; the
  runtime field and `TrendCooldown` duration are regression-tested against the
  params default. No strategy/risk TOML mutation, rebuild, restart, or runtime
  apply was performed in this checkpoint.
- **W-AUDIT-6 Kelly fraction config source/test checkpoint**：
  `RiskConfig.kelly` now exposes `{young,mature,established}_fraction` with
  defaults `1/8`, `1/6`, `1/4`, and `ml::kelly_sizer::compute_kelly_qty()`
  consumes those fields instead of hardcoded tier divisors. All risk-config
  TOMLs expose the same default values, preserving behavior until an operator
  edits config; no rebuild/restart/runtime apply was performed.
- **W-AUDIT-6 fast_track threshold config source/test checkpoint**：
  `RiskConfig.fast_track` now exposes `extreme_drop_pct=15.0`,
  `moderate_drop_pct=5.0`, and `outlier_sigma_threshold=3.0`; Step 0
  fast_track decisions, scoped-reduce classification, and sigma-scaled
  cooldown consume this snapshot. Paper/demo/live risk TOMLs expose the same
  defaults, preserving runtime behavior until an operator edits config; the
  90% margin-crisis threshold remains a code safety constant. No
  rebuild/restart/runtime apply was performed.
- **W-AUDIT-6 F-13 selection-bias promotion gate source/test checkpoint**：
  `program_code/learning_engine/promotion_gate.py` now composes existing
  DSR(K) and PBO/CSCV gates into a JSON-safe fail-closed result, and
  `PromotionGate` requires `demo_selection_bias_report.passes=true` before
  Demo→LivePending graduation. Missing CV returns, insufficient PBO power,
  high PBO, or DSR block/borderline all block/defer promotion. This wires the
  existing advisory math into the production promotion pipeline; it does not
  mutate runtime state, DB rows, live auth, or strategy/risk TOMLs.
- **W-AUDIT-6 per-trade risk SSOT source/test checkpoint**：
  `RiskConfig.limits.per_trade_risk_pct` is now the authoritative Kelly
  cold-start sizing source. Shared constants lock the validated/runtime bounds
  to `0.001..=0.20`; `KellyConfig::from_risk_config()` derives `risk_pct` and
  Kelly fractions from the active `RiskConfig`; replay runner and
  `IntentProcessor::update_risk_config()` consume that derived snapshot. No
  risk TOML mutation, rebuild, restart, runtime apply, DB write, or live auth
  change was performed.
- **W-AUDIT-6 funding_arb RiskConfig cleanup source/test checkpoint**：
  `funding_arb` is fully removed from the four `risk_config*.toml` files and
  remains retired through `strategy_params_{paper,demo,live}.toml::active=false`.
  New Rust regressions assert this SSOT split and real TOML parse/validate.
  The same checkpoint removed five existing lib-test warnings and wires
  `grid_trading`'s `on_post_only_rejected()` callback into its cooldown helper.
  No rebuild, restart, runtime reload, DB write, live auth mutation, or strategy
  activation was performed.
- **W-AUDIT-6 ma_crossover R:R trailing/TP source/test checkpoint**：
  `StrategyOverride` now includes `take_profit_enforced_override`, allowing
  `ma_crossover` to enforce TP without globally enabling TP for grid / BB
  strategies. All four `risk_config*.toml` files bind MA exits to
  `stop_loss_max_pct_override=2.5`, `take_profit_max_pct_override=8.0`,
  `take_profit_enforced_override=true`, `trailing_activation_pct_override=0.6`,
  and `trailing_distance_pct_override=0.4`; real TOML and runtime risk tests
  cover the wire shape and per-strategy TP enforcement. Runtime load is handled
  by the operator-requested post-sync rebuild/restart for this checkpoint.
- **Post-rebuild `[40]` BILLUSDT grid negative-cell source guard**：the first
  rebuild after MA R:R surfaced `[40] realized_edge_acceptance` FAIL from
  `grid_trading/BILLUSDT` (`24h n=11 avg=-49.67bps`). `BILLUSDT` is now added
  to `grid_trading.blocked_symbols` across paper/demo/live strategy params,
  blocking new grid entries only; existing close/reduce paths remain enabled.
  The 24h healthcheck window may remain FAIL until historical rows roll off.
- **W-AUDIT-6 bb_breakout 5m RFC/IMPL source/test checkpoint**
  (`6d3ea046`)：
  the old 1m rescue family is retired. `TickContext` now carries a real 5m
  indicator snapshot, `BbBreakoutParams` / `strategy_params_*.toml` expose
  `signal_timeframe`, and runtime `bb_breakout` consumes `indicators_5m` when
  configured for `5m`; missing 5m warmup skips rather than falling back to 1m.
  Initial kline bootstrap now seeds 1m + 5m REST bars to avoid post-rebuild 5m
  cold start. Demo `bb_breakout` is active on the 5m family; paper/live remain
  inactive. This is source/test only and does not grant true-live authority.
- **`P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` source/test closed 2026-05-09**：
  runtime `IndicatorEngine::compute_all_with_lambda()` already emits Donchian
  through `donchian_prior()`, not the inclusive helper `donchian()`. Added core
  and `bb_breakout` regressions proving current-bar high/low spikes are excluded
  from the runtime snapshot and that 5m hard-gate entry uses prior-bar upper.
  No strategy pause, rebuild, restart, DB write, live auth mutation, or runtime
  reload was performed in this checkpoint.
  **[2026-05-09 4-agent fact-check 補述]**：QC v2-NEW-4 對「runtime contaminated /
  Donchian shift(1) 未進 runtime」的判定為**過期 contaminated belief**。
  `rust/openclaw_core/src/indicators/mod.rs:150` 自 commit `75741eff`
  (2026-04-28 16:24) 起 IndicatorEngine `compute_all` 已呼 `donchian_prior(...)`
  寫入 `IndicatorSnapshot.donchian` 作為 prior-bar leak-free snapshot；
  `bb_breakout/mod.rs:551-571` 的 Hard/Score/Off 三 mode 全消費 prior 版本。
  當前運行 engine PID 起於 2026-05-09 15:52，已包含 04-28 修復 11 天。
  `ad14db07` (2026-05-09 17:01) 僅補 regression test 防 future regression，
  並非「runtime fix」。**結論**：runtime 已 leak-free 11 天；NEW-ISSUE-1 caveat
  「No reload/rebuild was performed」事實正確但**不再是 actionable blocker**，
  4-agent loss audit 引用此 finding 為 active runtime 問題的論述應撤銷。
- **W-AUDIT-6 queue ordering after source/test cleanup**：QC stand-alone fixes
  through `bb_breakout` 5m are closed. W-AUDIT-6c portfolio VaR/CVaR/EVT is
  now source/test closed at `cc6476dd`; W-AUDIT-6 has no remaining source/test
  item in the active queue. Keep the 2026-05-16 `funding_arb` 14d audit as
  verification/history only, not retirement authority.
- **W-AUDIT-6c portfolio VaR/CVaR/EVT source/test checkpoint**
  (`cc6476dd`)：
  `program_code/learning_engine/cvar.py` adds historical VaR/CVaR, EVT/GPD
  tail fit, and stationary block-bootstrap VaR/CVaR confidence intervals.
  `portfolio_var.py` adds portfolio return composition, LUNA/FTX/COVID stress
  scenarios, and `PortfolioTailRiskGate`. `PromotionGate` now requires
  `demo_tail_risk_report.passes=true` before DEMO_ACTIVE can graduate to
  LIVE_PENDING; missing stress exposures, insufficient observations, failing
  EVT, historical VaR/CVaR breach, or LUNA/FTX stress breach fail closed. This
  is source/test promotion evidence only: no DB apply, no runtime reload, no
  live auth mutation, and no order authority change.
- **`P2-AUDIT-VERIFY-5` source/test closed 2026-05-09**：
  current `blocked_symbols` lists are frozen in
  `docs/governance_dev/strategy_blocked_symbols_freeze.json` and guarded by
  `tests/structure/test_strategy_blocked_symbols_freeze.py`. New
  strategy-symbol block entries now require RFC + 7d counterfactual or
  rejected-outcome evidence + DSR/PBO or explicit QC waiver before source
  config mutation. Read-only Linux evidence showed `grid_trading/LABUSDT`
  7d net `-9.7539 USDT`, `grid_trading/BILLUSDT` `-3.6751 USDT`, and MA
  blocked rejections with `decision_outcomes=0`; this prevents more
  selection-biased list growth until rejected-outcome power exists. No strategy
  config change, DB write, rebuild, restart, live auth mutation, or runtime
  reload was performed.
- **`P2-AUDIT-VERIFY-4` F-08 source scope corrected 2026-05-09**：
  `helper_scripts/cron/ml_training_maintenance.py` / `_cron.sh` no longer
  cover only the replacement jobs (`linucb_trainer`, `mlde_shadow_advisor`,
  `mlde_demo_applier`, `scorer_trainer`, `quantile_trainer`). The default
  cron job list now also includes the five original audit targets:
  `thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`,
  and `weekly_report_generator`. `weekly_report_generator` persists
  `learning.weekly_review_log`; Thompson samples real `trading.fills` into
  `learning.bayesian_posteriors`; DL-3 reads `market.klines` and writes
  `learning.foundation_model_features`; Optuna uses IPC/env param ranges and
  real fills to write `learning.ml_parameter_suggestions`; CPCV is invoked via
  the existing training pipeline. This is still source/test only: crontab is
  not installed, no DB write/rebuild/restart/runtime reload was performed.
- **`P0-DECISION-AUDIT-1` ✅ closed** (W-C operator auth file + AMD §5.4.1)
- **`P0-DECISION-AUDIT-3` ✅ closed** (§三 5 stale 數字真修 + healthcheck id)
- **`P0-DECISION-AUDIT-2/4/5` ✅ closed** — AMD-2026-05-09-02 selects
  SM-05 Option A, W-AUDIT-6 strategy verdict Option ii, and openclaw_core /
  Layer2 sunset boundaries. This unlocks F-01 and W-AUDIT-6 implementation;
  it does not flip runtime config, live auth, or strategy risk files.
- **NEW-ISSUE / NEW-VULN queue updated**：LiveDemo auth restored, keep-auth
  RCA closed with warning preflight, and lease audit runtime emit verified.

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
| 9 | `W-AUDIT-2` Security IMPL (4 HIGH) | E1×4 並行 + E2 + E4 + E3 | DONE 2026-05-09 | F-24/F-25 mutating learning routes gated by operator+scope, F-23 Trading API no longer defaults to all interfaces; P0-NEW-VULN-1 follow-up uses safe tailnet auto bind (`100.64.0.0/10` when available, else loopback) and rejects `0.0.0.0`; F-03 lease transition writer wired into all active pipelines, Layer2 trigger gated, AI service socket chmod 0600. Runtime deploy 2026-05-09 `862e79b7`: V078 applied and `learning.lease_transitions` nonzero (`BYPASS` demo/live_demo; final spot-check rows=103). |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live + 5-Agent decision spine (mount W-A/W-B) | E1 + E1a + E2 + E4 + PA + PM | PARTIAL 2026-05-09 (`da2dba25` + F-01 source/test checkpoint) | F-17 dynamic `/api/v1/governance/lease-router/status` source patch added; F-15 lease flip→writer e2e regression added; SM-05 polling policy accepted via AMD-2026-05-09-01/02; F-01 source/test removed the unconditional `lambda: True` fallback and made provider-unavailable/exception reads fail-closed before submit authority. |
| 11 | `W-AUDIT-4` ML 基座 + dead schema (mount W-F-1) | E1×6 並行 + MIT + E2 + E4 | PARTIAL 2026-05-09 (~30h, 3 sessions, after W-AUDIT-1) | V068/V070/V071 source/test are metadata-only retention/review guards, not functional dead-schema closure. V069 corrected observability cleanup; V072 contract guard + dry-run-default 34-dim Rust `feature_baseline_writer` source/test; V073/V074 wrappers and V075/V076/V077 guards landed; F-09 FUP-2 runtime is verified (`edge_label_backfill_cron.sh`, `[43]` PASS). F-08 source scope is now corrected: `ml_training_maintenance` covers both operational jobs and the original audit five (`thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`, `weekly_report_generator`). Remaining functional work: operator-authorized F-08/V073/V074 cron install + 24h fire, separately authorized V072 writer apply/install if runtime `feature_baselines` rows are wanted, and true INSERT/writer decisions for retained-but-empty tables that still have no production caller. |
| 12 | `W-AUDIT-5` 性能/結構/CI/跨平台 (split 5a + 5b) | E1×6 並行 + E5 + E2 + E4 | ACTIVE 2026-05-09 (~17h+17h, 2 sessions) | F-21 source/test added `rust/Cargo.toml [profile.release] strip = "symbols"`; F-26 source/test added GitHub Actions Rust release-check matrix for `x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`; F-27 source/test corrected Bybit API dictionary drift for `intervalTime`, `/v5/user/query-api`, and G9-02, while documenting the official `account-ratio` daily-period contradiction instead of inventing runtime truth; F-test-h-state source/test split the 2641 LOC compatibility suite into `tests/h_state_query/` siblings while keeping the historical pytest path as a 9-line collector; F-12 source/test now covers both replay runner paths: `src/bin/replay_runner.rs` 1599→626 with `src/bin/replay_runner/{manifest,manifest_tests,config,calibration}.rs`, and the verified true finding `src/replay/runner.rs` 2469→1166 with `src/replay/runner_tests.rs` 1299 plus LOC static regression; W-AUDIT-5b event_consumer source/test split moved `dispatch.rs` tests to `dispatch_tests.rs` and Arm C exchange-event handling to `loop_exchange.rs`; W-AUDIT-5b state-machine snapshot source/test replaced the 10 generic `copy.deepcopy` snapshot callsites with explicit `clone()` snapshots over JSON-like mutable fields; W-AUDIT-5b orjson foundation/runtime-hot-path source/test added `json_fast`, migrated `ai_service_listener.py`, `ipc_client_sync.py`, `ipc_client.py`, `ollama_client.py`, and `local_llm_factory.py`; W-AUDIT-5b ai_budget source/test replaced the read-heavy config snapshot `RwLock` with `ArcSwap<BudgetConfig>` while keeping mutable usage counters under async `RwLock`; no release build/restart. Remaining 5a: F-20 damaged table dump+drop ops. Remaining 5b: canonical/byte-contract JSON paths stay stdlib until explicit byte tests; any per-strategy budget model is a separate schema/policy design, not a cache-swap mechanic. |
| 13 | `W-AUDIT-6` 策略 + 量化 promotion gate (mount P0-EDGE-1) | E1×5 + QC + E2 + E4 + PM | SOURCE/TEST CLOSED 2026-05-09 | AMD-2026-05-09-02 selects Option ii: grid conditional ORDIUSDT, ma_crossover revise, bb_breakout reject 1m→revise 5m, funding_arb retire, bb_reversion pair with MA. `bb_breakout` cooldown 600k vs 300k source/test drift is closed; Kelly `{young,mature,established}_fraction` config is source/test closed; fast_track 15%/5%+3σ thresholds are now `RiskConfig.fast_track` + TOML defaults and Step 0 consumes them; F-13 DSR/PBO/CSCV promotion gate is source/test closed; per_trade_risk_pct SSOT is source/test closed; funding_arb RiskConfig cleanup is source/test closed; ma_crossover R:R trailing/TP source/test is closed with strategy-scoped TP enforcement and four risk TOMLs bound; bb_breakout 5m RFC/IMPL is source/test closed at `6d3ea046` with real 5m indicators and no 1m fallback; W-AUDIT-6c VaR/CVaR/EVT is source/test closed at `cc6476dd` with portfolio tail-risk promotion evidence. Runtime deploy/reload remains separate. |
| 14 | `W-AUDIT-7` AI 棧 + GUI/UX 收口 | E1×4 + AI-E + A3 + E2 + E4 + ops | ACTIVE 2026-05-09 (~25h, 2 sessions, parallel-able) | F-30 source/test replaced native `prompt()` in learning + governance flows with shared custom prompt modal, including select pickers for tier/confidence inputs; F-system-mode-confirm source/test/browser-smoke added `live_reserved` 5s countdown + hold-to-confirm; F-strategy-confirm source/test/browser-smoke added risk-zoned Stop/Pause/Delete controls across strategy/live/paper and moved Paper/Live native confirm paths to custom modal confirm; F-strategist-cap source/test raised `RiskConfig.strategist.max_param_delta_pct` source/TOML/no-store fallback from 30% to 50% with Rust regression coverage; P0-V2 follow-up made 30%-50% a `wide_parameter_adjustment` Strategist skill in the Rust→Python prompt payload rather than a new supervised gate; F-28 source/test added a real stdlib-only `ContextDistiller` and wired Layer2 triage/manual prompt context through bounded compact JSON. No backend/restart/runtime reload/provider traffic. Remaining: F-07 operator API key + Layer2 manual trigger/observability, F-cea-env CostEdgeAdvisor env+restart. Layer2 autonomous loop is sunset by ADR-0020. |
| 15 | `W-AUDIT-8a` Alpha Surface Foundation (R-1 architectural amendment) | PA → E1 → E2 → E4 + MIT/QC/CC/BB → PM | SPEC PHASE 2026-05-09 / Phase A target Sprint N+0 (~40 person-day, 4 phases) | Strategy `on_tick(ctx, surface)` 接口升級 + `AlphaSurface<'a>`（Tier 1-4）+ `AlphaSourceTag` enum + 5 既存策略 declare alpha sources + Tier 2 cross-symbol panel collector（funding curve / OI delta） + Tier 3 liquidation pulse 真接 Bybit `allLiquidation` WS topic + Tier 4 EventAlert/RegimeTag wire + 7d replay E2E byte-identical baseline; **本 wave 不含**任何具體 alpha source 業務 IMPL（候選 A/B/C/D 留 8b/c/d）/ Strategist reframe（R-2 留 8e）/ Hypothesis Pipeline（R-3 留 8f）/ per-alpha-source budget gate（R-4 留 8g）。Spec：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`. |

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
| `P0-DECISION-AUDIT-2` | DONE 2026-05-09 | shadow_mode TOML × 3 設計意圖鎖定（FA push back #2） | AMD-2026-05-09-02 selects PA option (a): demo TOML `shadow_mode=true` is W-A demo fail-closed posture; after `P0-EDGE-1` + supervised gates, demo may flip false for shadow→submit promotion. SM-05 policy accepted; F-01 source/test implemented. |
| `P0-DECISION-AUDIT-3` | DONE | CLAUDE.md §三 數值 vs runtime drift 防線改造 | §三 now keeps only active current state, every runtime number carries timestamp/healthcheck id, and stale completed history points to archive/report sources. |
| `P0-DECISION-AUDIT-4` | DONE 2026-05-09 | 5 策略 verdict 採納 | AMD-2026-05-09-02 selects PA option (ii): grid CONDITIONAL ORDIUSDT, ma_crossover REVISE, bb_breakout REJECT 1m→REVISE 5m, funding_arb RETIRE, bb_reversion pair with MA confirmation. W-AUDIT-6 implementation unblocked; no risk config mutated by the decision doc. |
| `P0-DECISION-AUDIT-5` | DONE 2026-05-09 | openclaw_core 9 模組 + Layer2 自主循環 14 天 0 動作 sunset（FA push back #3） | AMD-2026-05-09-02 selects PA option (i)+(ii): ADR-0015 now records legacy `openclaw_core` modules as permanent sunset candidates; ADR-0020 records Layer2 manual supervisor-only, no autonomous loop. W-AUDIT-5/W-AUDIT-7 cleanup unblocked. |
| `P0-NEW-ISSUE-1` | RUNTIME-RESTORED / RCA DONE 2026-05-09 | LiveDemo pipeline auth_missing → engine boot demo-only (CRITICAL functional regression) | Restored through signed `/api/v1/live/auth/renew` route, not manual file write: `tier=T0_ENTRY`, `approved_system_mode=live_reserved`, `valid_for_engine=true`, expires_at_ms=1778405563954. `[56]` direct check PASS after renew and after rebuild/restart: live pipeline active endpoint=live_demo auth=present snapshot fresh. RCA: engine log `engine-1778289328.log` shows 2026-05-09T01:11:28Z Rust consumed a `manual` restart sentinel and cleared `authorization.json`; later `--keep-auth` preserved the already-missing state. Guard added: `restart_all.sh --keep-auth` warns when live slot is configured but signed auth is absent. |
| `P0-NEW-VULN-1` | DONE 2026-05-09 | launchd / lifecycle bind 安全弱點 (HIGH) | Mac launchd Trading API template binds `127.0.0.1` and preflight rejects all-interface plist binds. Lifecycle scripts now use `helper_scripts/lib/api_bind_host.sh`: default `auto` binds the concrete Tailscale IPv4 when available, otherwise loopback; `OPENCLAW_BIND_HOST=tailscale` forces tailnet-only; `0.0.0.0` / `::` are rejected. Linux API-only runtime reload applied: Trading API listens on `100.91.109.86:8000`, not `0.0.0.0:8000`, preserving Tailscale GUI access without LAN/all-interface exposure. |
| `P0-NEW-VULN-2` | DONE 2026-05-09 | lease audit runtime 0 emit (HIGH) | `e97a333b` emits one synthetic `BYPASS` audit row for Validation/Exploration facade bypass without creating SM objects. Linux rebuild/restart deployed `862e79b7`; auto-migrate applied V078 (`_sqlx_migrations version=78 success=t`); `learning.lease_transitions` is nonzero with `BYPASS` rows for `demo` and `live_demo` (final spot-check rows=103). |
| `P0-AUDIT-NEW-LG-X-05` | DONE 2026-05-09 | SPECIFICATION_REGISTER LG-X-05 缺 + LG-X-04 編號錯位 (R4 N1 CRITICAL) | Fixed in `docs/governance_dev/SPECIFICATION_REGISTER.md`: LG-X now maps historical LG-1..LG-5 as evidence window / H0 / pricing / supervised-live / constrained autonomous live; LG-X-05 registers the LG-5 constrained-autonomous RFC, eval-contract v2, R-meta amendment, and healthchecks. Live Ops moved to separate `OPS-X-01` so it no longer occupies LG-X-04. |
| `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` | DONE 2026-05-09 | bb_breakout 5m active=true 但 Donchian leak-free shift(1) 未進 runtime (QC v2-NEW-4 HIGH) | Source/test closure: `donchian()` remains the explicit inclusive helper, but runtime `IndicatorEngine::compute_all_with_lambda()` feeds snapshots via `donchian_prior()`. Added regressions in `openclaw_core::indicators` and `openclaw_engine::strategies::bb_breakout` proving current-bar high/low spikes are excluded and 5m hard-gate entry uses prior-bar upper. No runtime reload/rebuild or strategy pause was performed. |
| `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE` | DONE 2026-05-09 | F-strategist-cap 30%→50% 一次 67% 放寬無 supervised gate (FA v2-NEW-1 升 P0 因治理一致性) | Operator decision: do **not** add a new hard/supervised gate and do **not** revert to 30%; develop the extra freedom as a Strategist skill. Source/test closure: Rust now sends `strategist_skill={name: wide_parameter_adjustment, normal_delta_pct:0.30, max_delta_pct:<RiskConfig snapshot>}` in each strategist_evaluate payload; Python prompt shows both `normal_range` and `wide_skill_range`, teaching <=30% as ordinary tuning and 30%-50% as deliberate wide adjustment skill. Rust still validates only the configured max envelope. No runtime reload/rebuild/provider call. |
| `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` | SOURCE/TEST CLOSED 2026-05-09; RUNTIME PENDING | DSR/PBO promotion gate IMPL ✅ 但 evidence push 鏈缺 (QC §6.1 (a)(c) HIGH) | Source/test closure: James-Stein cycle now keeps real per-cell `raw_bps_series`; new `ml_training.promotion_evidence` builds strategy-level observed_sharpe, candidate_oos_returns, persisted trial_sharpes, and portfolio_returns from real realized-edge series; `edge_estimator_scheduler.py` pushes Demo-only promotion evidence each JS cycle; `PromotionGate.update_demo_selection_bias_evidence()` now fail-closes invalid evidence; V079 adds `learning.strategy_trial_ledger` plus `promotion_pipeline.demo_selection_bias_report/demo_tail_risk_report`, and governance promotion status reloads DB report rows fail-soft. No cron install, V079 DB apply, rebuild/restart, live auth, or strategy/risk runtime mutation was performed; runtime activation requires explicit ops apply/rebuild. |

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
| `P1-EDGE-1` | 3 | Source-fixed ma_crossover LABUSDT block + bb_breakout 5m revise | Runtime diagnosis: 7d ma_crossover combined demo/live_demo is negative mainly from `LABUSDT` (`n=6 avg=-244.54bps`), so `LABUSDT` is source-blocked for ma_crossover new entries in risk configs while close/reduce remains allowed; bb_breakout 1m rescue is retired and revised to consume real 5m indicators in demo only, with live disabled until fresh 5m evidence is net-positive. Post-rebuild `[40]` also surfaced `grid_trading/BILLUSDT` 24h negative cell (`n=11 avg=-49.67bps`), so `BILLUSDT` is source-blocked for new grid entries across paper/demo/live strategy params. |
| `P1-EDGE-2` | 3 | funding_arb 14d audit | Run the 2026-05-16 audit before retention or deprecation decisions. |
| `P1-REPLAY-1` | 4 | Recorder-history maturity | Build longer local BBO/orderbook/latency history for S1/S1+ calibration; never fabricate old microstructure. |
| `P1-REPLAY-2` | 4 | DONE — runtime-applied replay artifact type cleanup | V066 applied twice on Linux for idempotency, constraints verified, rollback smoke passed, and runtime reloaded with `restart_all.sh --keep-auth` on 2026-05-08. New finalize rows can use `replay_report`; legacy `pnl_summary` remains readable. |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | Source is active; continue audit-row and attribution health monitoring. |
| `P1-AUDIT-DOCS-1` | 2 | DONE — W-AUDIT-1 docs sync chain | CLAUDE.md §三/§五/§四/§十 sync, AMD §5.4.1, W-C operator auth file, docs/README catch-up, SPECIFICATION_REGISTER LG-X / SM-03 / EX-03 / ARCH-02/03 / AUDIT-13, CONTEXT glossary, ADR-0015..0019, SCRIPT_INDEX, and MIT/BB workspace READMEs completed. |
| `P1-AUDIT-SEC-2` | 2 | DONE — W-AUDIT-2 security IMPL chain | F-24/F-25/F-23/F-03 + Layer2 trigger + AI socket chmod landed with static regressions, route tests, py_compile, Rust cargo check, and lease writer tests. Runtime deploy/restart intentionally not performed. |
| `P1-AUDIT-RUNTIME-3` | 2 | W-AUDIT-3 ExecutorAgent fake-live (mounts W-A close-out + W-B regression) | PARTIAL `da2dba25` + F-01 source/test checkpoint: F-17 source/API/GUI dynamic status patch added; F-15 lease flip→writer e2e regression added with opt-in `OPENCLAW_TEST_PG` DB row coverage; AMD-2026-05-09-01/02 accept SM-05 Option A; F-01 removes `executor_agent.py` unconditional `lambda: True` fallback and keeps missing/failing provider reads fail-closed before submit authority. |
| `P1-AUDIT-ML-4` | 3 | W-AUDIT-4 ML 基座 + dead schema (mounts W-F-1) | PARTIAL: V068/V070/V071 are metadata-only retention/review guards, so COMMENT/reclass does not close functional row production. V072 source/test adds a contract guard and dry-run-default 34-dim Rust `feature_baseline_writer`; V073/V074 wrappers, V075 retention/compression, V076 Guard A, and V077 archive CHECK/trigger fallback landed. F-08 source scope mismatch is corrected: `ml_training_maintenance_cron.sh` + runner now covers the original audit five (`thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`, `weekly_report_generator`) in addition to operational MLDE jobs, with real data paths to `bayesian_posteriors`, `ml_parameter_suggestions`, `cpcv_results`, `foundation_model_features`, and `weekly_review_log` where dependencies/data exist. Cron is still not installed. F-09 FUP-2 runtime is verified (`edge_label_backfill_cron.sh`, `[43]` PASS). Remaining: operator-authorized F-08/V073/V074 cron install + 24h fire, separately authorized V072 writer apply/install, and true source/writer decisions for retained empty tables that still lack production callers. |
| `P1-AUDIT-PERF-5` | 3 | W-AUDIT-5a 性能/結構/CI urgent | F-21 source/test added release symbol stripping in `rust/Cargo.toml`; F-26 source/test added `.github/workflows/ci.yml` cargo release-check matrix for `x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`; F-27 source/test corrected Bybit API dictionary drift: `get_open_interest` now documents Rust `interval` -> Bybit `intervalTime`, `/v5/user/query-api` key-validation path is recorded, G9-02 UnknownHandlerGuard documents the actual runtime env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`, and the official `account-ratio` `1d` vs enum `4d` contradiction is marked exchange-smoke-required. F-test-h-state source/test split `test_h_state_query_handler.py` from 2641 LOC to a 9-line compatibility collector plus `tests/h_state_query/{common,test_core,test_h_buckets,test_agent_states}.py`, with LOC static regression. F-12 source/test now includes the earlier `rust/openclaw_engine/src/bin/replay_runner.rs` split and the true-path fix for `rust/openclaw_engine/src/replay/runner.rs` 2469→1166 plus `runner_tests.rs` 1299, with LOC static regression. W-AUDIT-5b has also landed event_consumer split, state-machine clone snapshots, json_fast foundation/runtime IPC+local LLM hot paths, and ai_budget config `ArcSwap` source/test. No release build/restart/deploy. Remaining: F-20 DROP `trading.*_damaged_20260414_130607` 4 表 909MB (E1-b+ops 2h, NAS dump 先); canonical/byte-contract JSON paths remain intentionally stdlib until byte tests exist. Heavy parallel; 1 session ~17h. |
| `P1-AUDIT-STRATEGY-6` | 3 | W-AUDIT-6 策略 verdict + DSR/PBO promotion gate (mounts P0-EDGE-1) | SOURCE/TEST CLOSED by AMD-2026-05-09-02 implementation wave: bb_breakout cooldown 600k vs 300k DONE (`DEFAULT_COOLDOWN_MS=300_000` shared by params default + constructor). Kelly tier 8/6/4 DONE: `RiskConfig.kelly.{young,mature,established}_fraction` drives `compute_kelly_qty()` with defaults `1/8`, `1/6`, `1/4`. fast_track 15%/5%+3σ DONE: `RiskConfig.fast_track.{extreme_drop_pct,moderate_drop_pct,outlier_sigma_threshold}` drives Step 0, scoped reduce, and sigma cooldown. F-13 DONE: DSR(K)+PBO/CSCV blocks Demo→LivePending without passing `demo_selection_bias_report`. per_trade_risk_pct SSOT DONE. funding_arb RiskConfig cleanup DONE. ma_crossover R:R trailing/TP DONE. bb_breakout 5m RFC/IMPL DONE at `6d3ea046`. W-AUDIT-6c portfolio VaR/CVaR/EVT DONE at `cc6476dd`: `cvar.py`, `portfolio_var.py`, EVT/GPD, stationary block bootstrap CI, LUNA/FTX/COVID stress, and required `demo_tail_risk_report` before Demo→LivePending. Runtime deploy/reload remains separate; P0-EDGE-1 remains active until observed edge evidence clears. |
| `P1-AUDIT-AI-UX-7` | 3 | W-AUDIT-7 AI + GUI/UX 收口 | F-30 source/test/browser-smoke DONE: `common.js` now exposes shared `openPromptModal()`, learning experiment completion uses textarea + confidence select modal, governance audit/live-auth renewal/review flows use custom modal prompts and tier select pickers, and static guard prevents native `prompt()` from returning in those target files. F-system-mode-confirm source/test/browser-smoke DONE: `tab-system.html` `live_reserved` mode confirmation now disables the confirm button for 5s, rejects single-click confirmation after countdown, and submits only after a 1.2s hold-to-confirm. F-strategy-confirm source/test/browser-smoke DONE: `common.js` now defines shared action risk zones, `tab-strategy.html` visually separates Pause/Stop/Delete, `tab-paper.html` separates run/pause/stop/dual-stop and replaces `sessionStopAll()` native confirm with `openConfirmModal()`, and `tab-live.html` groups Stop/Emergency plus marks close-all/row-close actions as destructive with custom modal confirms. F-strategist-cap source/test DONE: `risk_config_{paper,demo,live}.toml`, `StrategistConfig::default()`, and `DEFAULT_MAX_PARAM_DELTA_PCT` now align on 0.50, with config + scheduler tests covering serde fallback, no-store fallback, and hot-reload overrides; P0-V2 no-gate follow-up DONE by teaching `wide_parameter_adjustment` skill in strategist prompt payload. F-28 ContextDistiller source/test DONE: new `app/context_distiller.py` compacts market/portfolio/health/events/pressure/dream into bounded deterministic JSON, exposes thread-safe cached cycle summaries, and `Layer2Engine` uses it for L1 triage + manual session context; provider-mock tests were updated to the current provider abstraction. No runtime reload/rebuild/provider traffic. Remaining: F-07 operator GUI ANTHROPIC_API_KEY + Layer2 manual trigger 觀察 7d (operator 5min) + F-cea-env `OPENCLAW_COST_EDGE_ADVISOR=1` env + restart (ops 0.5h). W-AUDIT-7c autonomous loop is sunset by ADR-0020; keep manual/supervisor trigger work only. 2 sessions urgent; can parallel with W-AUDIT-3..6. |

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
| `P2-AUDIT-VAR-6c` | DONE 2026-05-09 — W-AUDIT-6c portfolio VaR/CVaR/EVT IMPL | `cc6476dd` adds `portfolio_var.py` + `cvar.py`, EVT/GPD tail fit, LUNA/FTX/COVID stress tests, stationary block-bootstrap VaR/CVaR CI, and `PromotionGate.demo_tail_risk_report` fail-closed requirement for DEMO_ACTIVE→LIVE_PENDING. |
| `P2-AUDIT-LAYER2-7c` | DONE-BY-DECISION — autonomous Layer2 loop sunset | ADR-0020 keeps Layer2 manual/supervisor only. Do not build hourly autonomous loop unless a future ADR reverses the boundary. ContextDistiller/manual escalation packet work remains under W-AUDIT-7b. |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset | ADR-0015 + AMD-2026-05-09-02 accept permanent sunset candidates; next W-AUDIT-5 pass may drop attention.rs / attribution.rs / backtest.rs / cognitive.rs / dream.rs / message_bus.rs / opportunity.rs / order_match.rs / portfolio.rs after reference audit + green tests. |
| `P2-AUDIT-VERIFY-1` | DONE 2026-05-09 — DOCS-1 殘缺項收口 | Closed the R4 verified W-AUDIT-1 index gaps: `docs/README.md` now has a `docs/agents/` section, links `../helper_scripts/SCRIPT_INDEX.md`, indexes every top-level `docs/archive/*.md`, updates CCAgentWorkSpace from 17→19 agents with MIT/BB rows, and MIT/BB now also have `workspace/README.md`. Added `tests/structure/test_docs_readme_index_static.py` to guard all five findings. |
| `P2-AUDIT-VERIFY-2` | DONE 2026-05-09 — F-12 runner.rs 真檔對齊 | Verified true finding closed: `rust/openclaw_engine/src/replay/runner.rs` 2469→1166 and tests moved to sibling `runner_tests.rs` 1299; `tests/structure/test_replay_runner_split_static.py` now guards both files under the 2000 LOC cap. |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix | FA NEW-2 verified: V068/V070/V071 全降級為 reclassification guard（COMMENT only），row count 仍 0；不要把 COMMENT-only 當 functional close。2026-05-09 source follow-up has connected the F-08 audit scripts to real writer paths for `bayesian_posteriors` / `ml_parameter_suggestions` / `cpcv_results` / `foundation_model_features` / `weekly_review_log` when cron + dependencies + data exist. Remaining functional wave: verify runtime rows after F-08 install, and separately decide true producer/drop policy for retained empty tables that still lack a production caller (`rl_transitions`, `symbol_clusters`, and any residual review-only placeholder after code-reference audit). |
| `P2-AUDIT-VERIFY-4` | cron not installed (F-08) | FA NEW-3 + AI-E verified: source wrapper existed but was not in crontab, and its first scope covered a different five jobs. 2026-05-09 source correction makes default jobs include the original audit five (`thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`, `weekly_report_generator`) plus operational jobs; targeted tests and forced dry-run smoke pass. Remaining action requires operator authorization: install `ml_training_maintenance_cron.sh` in crontab, then verify status JSON/log and 24h fire; no runtime install was performed in this source checkpoint. |
| `P2-AUDIT-VERIFY-5` | DONE 2026-05-09 — grid blocked_symbols selection-bias freeze | Current grid 17-symbol and MA 4-symbol blocklists are frozen in `docs/governance_dev/strategy_blocked_symbols_freeze.json` and guarded by `tests/structure/test_strategy_blocked_symbols_freeze.py`; new blocked cells require RFC + 7d counterfactual/rejected-outcome evidence + DSR/PBO or explicit QC waiver. Added `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`; read-only Linux spot-check found only LAB/BILL grid and LAB MA realized fills, while MA blocked rejections had `decision_outcomes=0`, so no further blocklist growth is allowed until outcome-backed counterfactual power exists. |
| `P2-AUDIT-VERIFY-6` | DONE 2026-05-09 — A3 NEW-1 openConfirmModal a11y | `common.js` and legacy `app.js` `openConfirmModal` paths now set dialog role/`aria-modal`, support Esc cancel, Tab focus loop, initial cancel focus, and previous-focus restore. Static a11y regression + JS syntax checks passed. |
| `P2-AUDIT-VERIFY-7` | DONE 2026-05-09 — NEW-VULN-3 / NEW-VULN-4 修復 | Cookie Secure auto mode now treats positive HTTPS proxy hints as fail-closed Secure-cookie signals even without trust-proxy env, while explicit `OPENCLAW_COOKIE_SECURE=0` remains an operator override. Phase4 router is mounted in Control API `main.py`, so weekly-review operator+scope gates are reachable rather than dead code. Source/test only; no runtime reload. |
| `P2-AUDIT-QC-STAND-ALONE` | QC stand-alone fixes（verdict 已由 AMD-2026-05-09-02 選定）| DONE: (1) funding_arb schema 4 TOML 完全清除 source/test; (2) Kelly tier 8/6/4 → RiskConfig.kelly.{young,mature,established}_fraction source/test; (3) bb_breakout cooldown 600k vs 300k source/test 統一；(4) DSR/PBO production caller 加進 promotion_pipeline.py demo gate source/test；(5) CLAUDE.md §三 -26.44 已加 source report + `[40]` realized_edge_acceptance healthcheck id。 |

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
| 2026-05-16 | funding_arb 14d audit | Run `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh` as verification/history artifact; retirement decision is already recorded in AMD-2026-05-09-02 / ADR-0018. |
| 2026-05-09 | W-AUDIT-1 docs sync | DONE. PA fix plan §6 W-AUDIT-1 source-closed. |
| 2026-05-09 | W-AUDIT-2 security IMPL | DONE source/test checkpoint; no rebuild/restart. |
| 2026-05-10/12 | W-AUDIT-3 ExecutorAgent fake-live | F-01 source/test closed after AMD-2026-05-09-02; W-AUDIT-3 remains runtime-partial unless operator asks for opt-in DB/runtime closure. |
| 2026-05-10..18 | W-AUDIT-4 ML 基座 + dead schema | After W-AUDIT-1; parallel with W-AUDIT-3/5/6/7; ~30h, 3 sessions. |
| 2026-05-10..14 | W-AUDIT-5a 性能/結構/CI | After W-AUDIT-1; parallel; ~17h, 1 session. |
| 2026-05-15..22 | W-AUDIT-6 策略 + DSR/PBO promotion gate | Strategy verdict selected by AMD-2026-05-09-02; proceed after W-AUDIT-1/3; ~30h, 3 sessions. |
| 2026-05-12..16 | W-AUDIT-7 AI + GUI/UX 收口 | Parallel; operator API key 7d 觀察 + GUI fix; ~25h, 2 sessions urgent (7a) + 7b/7c 後期。 |
| 2026-06-15 | Supervised live target (悲觀帶) | Conditional on W-AUDIT-1..7 implementation + 5 P0-LG/OPS 條目 + W-A/W-B/W-C/W-D PASS. P0-DECISION-AUDIT-2/4/5 已收口，但不代表 true-live 授權。PA panorama 偏向悲觀。 |
| 2026-05-09 | 12-Agent Adversarial Verification land + TODO v15 | 12 verification reports written；總 tally ✅74 / ⚠️66 / ❌120 / 🔄6 / 🆕53；PM sign-off + verified-closed 細節歸檔到 `docs/archive/2026-05-09--w_audit_verified_closed_archive.md`；summary at `srv/2026-05-09--audit_fix_verification_summary.md`。 |
| 2026-05-09 | NEW-ISSUE-1 keep-auth RCA | DONE: LiveDemo auth restored and `[56]` PASS; RCA traced loss to prior `manual` sentinel consumption at 2026-05-09T01:11:28Z, and `restart_all.sh --keep-auth` now warns if auth is already absent. |
| 2026-05-10..13 | W-AUDIT-3 F-01 + W-AUDIT-6 kickoff | F-01 provider fail-closed source/test checkpoint is closed; next active implementation can move to W-AUDIT-6 strategy cleanup unless W-AUDIT-3 runtime evidence is explicitly requested. |

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

## Reference — 2026-05-09 v2 Adversarial Verification (after 34 commits)

- **PM Sign-off v2 summary**: `srv/2026-05-09--audit_fix_verification_v2_summary.md`（259 verification points 整合 + v2 wave verdict + 5 P0-DECISION + 6 P0-NEW-ISSUE/VULN 全 closed + v2 21 NEW-ISSUE 清單）
- **v2 Verified-closed details archive**: `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_v2.md`（**v2 過時/已修復內容單獨存放**）
- **12 v2 verification reports**: `srv/docs/CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-09--*_verification_v2.md`
- **v2 Total tally**: **✅ 122 (47%) / ⚠️ 47 (18%) / ❌ 66 (25%) / 🔄 3 (1%) / 🆕 21 (8%)** = 259 points
- **vs v1**: ✅ 74→122 (+48, **+65%**) / ❌ 120→66 (-54, **-45%**) / 🆕 53→21 (-32, **-60%**)
- **Compliance score**: B (21/30 = 70%) → **B+ (25/30 = 83.3%)** (CC v2 verdict)
- **P0-DECISION 拍板**: 2/5 → **5/5**（AMD-2026-05-09-02 收口 -2/-4/-5）
- **6 P0-NEW-ISSUE/VULN**: **全 closed**（LiveDemo restored / 4 NEW-VULN / LG-X-05）
- **ML 基座達標率**: 42% → **44%**（attribution_chain_ok 24h 0.0188→0.5041% denominator artifact, ok_n only +47%）
- **GUI 整體**: 8.1 → **8.3 / 10**（Critical 4/5；openConfirmModal a11y A 級補完）
- **5 策略 7d gross**: demo avg_net=-17.82bps / live_demo PnL delta +20.87 USD vs baseline (`[40]` 2026-05-09)
- **DSR/PBO promotion gate**: **LIVE**（W-AUDIT-6 大爆發收口）
- **VaR/CVaR/EVT**: **LIVE**（W-AUDIT-6c portfolio tail risk gate IMPL）
- **runner.rs LOC**: 2467 → **1167**（F-12 真檔對齊；E5 v2 verified）
- **核心 v2 verdict**: 真實飛躍 — 修復覆蓋率從 v1 23% → v2 47%（+104%）。W-AUDIT-2 從 source-only 翻 runtime verified；W-AUDIT-6 從 untouched 大爆發收口；W-AUDIT-1 從 partial 翻 5/5 CRITICAL closed；P0-DECISION-AUDIT 5/5 拍板。**剩餘核心 gap**：(1) W-AUDIT-4 6 表 0 INSERT + cron not installed → MLDE 仍 catastrophic；(2) DSR/PBO evidence 自動化 push 鏈 + trial_sharpes 持久化缺已 source/test 補上，待 V079 apply + rebuild/restart 後進入 runtime evidence；(3) bb_reversion verdict 仍未動。`P0-V2-NEW-1-DONCHIAN-LEAK-BIAS`、`P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE`、`P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` 已於 2026-05-09 source/test closed。距 supervised live 規劃帶仍是 6/15 悲觀 / 6/30 中位 / 7/15 樂觀，但 v2 飛躍把樂觀帶 6/30 提前可能性提升至 ~40%。

## Reference — 2026-05-09 v3 Adversarial Verification (after 5 commits) + PA Fix Plan v2 DUAL-TRACK

- **PM Sign-off v3 summary**: `srv/2026-05-09--audit_fix_verification_v3_summary.md`（230 verification points 整合 + 13 v3 verdict + PA fix plan v2 DUAL-TRACK 結構）
- **v3 Verified-closed details archive**: `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`
- **PA Fix Plan v2 (DUAL-TRACK)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` + `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **12 v3 verification reports**: `srv/docs/CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-09--*_v3.md`
- **v3 Total tally**: **✅ 65 (28%) / ⚠️ 39 (17%) / ❌ 84 (37%) / 🔄 3 (1%) / 🆕 39 (17%)** = 230 points
- **vs v2**: ✅ 122→65 (**v3 暴露更多真 outstanding**) / ❌ 66→84 (+18) / 🆕 21→39 (+18 PA redesign 引入新對齊任務)
- **Compliance score**: B+ (25/30 = 83.3%) → **A- (27/30 = 90.0%)** (CC v3 verdict)
- **PA Redesign cross-agent verdict**: FA AGREE / QC PARTIAL / MIT PARTIAL / E5 PARTIAL / E3 ACCEPT WITH 7 HARD-PRECON / CC ACCEPT-WITH-CONDITIONS / AI-E PARTIAL / BB CONDITIONAL APPROVE / TW 應升 ADR+AMD+Spec / R4 必建 ADR-0021+ARCH-04+CONTEXT 5 詞條 / A3 GUI HIGH 影響需新 2 tab → **整合 verdict: DUAL-TRACK 採納**
- **PA Fix Plan v2 結構**: 16 wave / ~360-420h / 6-12 weeks
  - **Track W**（7 wave / ~92h / 6-8w）：W-AUDIT-3b/4b/6c/6d/7c/1d/5b 收 v2 outstanding
  - **Track A**（9 wave / ~270-330h / 6-12w）：W-AUDIT-8a/9 + 8b-8g + W-ARCH-3 alpha source 升級
- **operator 已採納部分 PA R-1**：CLAUDE.md §三 已加 W-AUDIT-8a row + spec doc `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`；W-AUDIT-9 AMD-2026-05-09-03 起 5-stage graduated canary supersedes AMD-02 §2 binary fail-closed
- **MIT v3 第一次定位 attribution real root cause**: `label_close_tag` NULL 98.9%（attr_chain_ok 24h 1.0857% = 76/7000）；**1-day fix vs PA R-3 Hypothesis Pipeline 4-6 sprint，最高 ROI** → 升 P0-V3-MIT-ROOT-CAUSE
- **BB v3 揭發 PA spec 3 條錯誤**: (1) Bybit V5 WS 沒「L25」levels（真實 1/50/200/1000）；(2) liquidation_pulse 4 weeks ago deleted 需 revert；(3) basis demo 限 observation 沒分（execution 需 mainnet）→ R-1 spec 必修
- **5 commits 真實 cover**: ad14db07/c2ab7b1a/48227607/c081029d/da2aba11 cover P0-V2-NEW-1/2/3 + selection bias + cron scope，但**source/test only**：V079 完全未 apply / cron 未 install / engine 仍跑 5/8 binary（Donchian fix 未 runtime 落地）
- **W-AUDIT-2 V078 lease_transitions BYPASS 24h**: 7955 → 11133 = **+40% growth**（v2 唯一真活躍 runtime 進步）
- **核心 v3 verdict**: 架構 inflection point — operator 已採納 PA R-1；PA fix plan v2 DUAL-TRACK；MIT 第一次定位 attribution real root cause；BB 揭 PA spec 3 條錯誤。**真實 ❌ 上升非倒退**而是「v2 high-estimate 被 v3 校正」+「PA redesign 引入新對齊任務」+「runtime apply 全 outstanding 暴露 source/test 假進度模式」。**最緊要 24-48h actions**：(1) MIT label_close_tag NULL writer fix（1-day, 最高 ROI）；(2) V079 DB apply；(3) operator 授權 crontab 安裝 ml_training_maintenance；(4) PA spec 修 3 條（L25/liquidation/basis）；(5) 建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-03/04；(6) engine restart 落地多 commits。距 supervised live 規劃帶仍是 6/15 樂觀(~40%) / 6/30 中位(~40%) / 7/15 悲觀(~20%)。

## Reference — DUAL-TRACK Wave Definitions (新 16 wave，PA fix plan v2)

### Track W — 收 v2 outstanding（~92h / 6-8 weeks）

| Wave | 內容 | ETA |
|---|---|---|
| `W-AUDIT-3b` | ExecutorAgent runtime smoke + fail-closed metrics（**必先 land 避 W-AUDIT-9 衝突**）| sprint 1 |
| `W-AUDIT-4b` | V079 DB apply + cron install + **label_close_tag NULL writer fix（MIT v3 真實 root cause，最高 ROI）** | sprint 1 |
| `W-AUDIT-6c` | portfolio tail risk gate runtime apply | sprint 2 |
| `W-AUDIT-6d` | 5 策略 verdict IMPL maintenance | sprint 2 |
| `W-AUDIT-7c` | API Key clear modal + Settings 拆 sub-tab + GUI a11y 補齊（含 governance-tab.js 兩個 confirm 修）| sprint 2-3 |
| `W-AUDIT-1d` | docs/README index sync（5 commits 期間 0/30+ 新文件登記）+ ADR-0021 草擬 | sprint 1 |
| `W-AUDIT-5b` | H-8 H-9 sunset + runner.rs split bin/server-side | sprint 3 |

### Track A — Alpha Source Architecture 升級（~270-330h / 6-12 weeks）

| Wave | 內容 | ETA |
|---|---|---|
| `W-AUDIT-8a` | Alpha Surface Foundation SPEC PHASE | **operator 已啟動**（CLAUDE.md §三 已加 row + spec doc）|
| `W-AUDIT-9` | Graduated Canary Foundation（5-stage canary，supersedes AMD-02 §2 binary fail-closed）| **operator 已啟動**（AMD-2026-05-09-03 起）|
| `W-AUDIT-8b` | R-1 Alpha Surface IMPL（funding/oi 25 symbols throughput fix；BB spec 修：L50 / liquidation revive / basis observation-only）| sprint 2-4 |
| `W-AUDIT-8c` | R-2 Strategist scope expansion（alpha-source orchestrator）| sprint 4-6 |
| `W-AUDIT-8d` | R-3 Hypothesis Pipeline first-class | sprint 6-8 |
| `W-AUDIT-8e` | R-4 Per-alpha-source supervised promotion | sprint 8-10 |
| `W-AUDIT-8f` | R-5 Spec-as-Code | sprint 10-12 |
| `W-AUDIT-8g` | Alpha Sources GUI tab + Hypothesis Lab GUI tab（A3 建議 13→15 tab）| sprint 4-6 |
| `W-ARCH-3` | Spec drift 收口（EX-06 §6.3「自动进入 live」+ LG-X-02..05 supersedes 標記）| sprint 1 |

### 關鍵協調風險

W-AUDIT-9 T3 改 `executor_config_cache.py` + `_read_shadow_mode` stage-aware 與 Track W W-AUDIT-3b ExecutorAgent runtime smoke 衝突中-高 → **必須 W-AUDIT-3b 先 land**。

### v3 P0 升級條目

- `P0-V3-MIT-ROOT-CAUSE` ACTIVE 2026-05-09 v3：label_close_tag NULL 98.9% 1-day fix（最高 ROI；MIT v3 第一次定位）
- `P0-V3-V079-NOT-APPLIED` ACTIVE 2026-05-09 v3：48227607 source 已落但 _sqlx_migrations max=78
- `P0-V3-CRON-NOT-INSTALLED` ACTIVE 2026-05-09 v3：3 天 0 進展，operator 授權 crontab
- `P0-V3-PA-SPEC-FIX` ACTIVE 2026-05-09 v3：L25→L50 / liquidation revive / basis observation-only
- `P0-V3-ADR-0021-ARCH-04` ACTIVE 2026-05-09 v3：建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-03/04（R4/TW 共識）
- `P0-V3-ENGINE-RESTART` ACTIVE 2026-05-09 v3：engine 仍跑 5/8 binary 待 rebuild 含 Donchian fix + 多 commits 落地
