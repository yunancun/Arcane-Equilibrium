# 玄衡 TODO — Active Dispatch Queue

Version: v49
Date: 2026-05-18
Status: v49 dispatch-state sync — v48 P0-PHASE-1B-PARAM-CALIBRATION-1 全 6 step chain CLOSED including deploy. Chain: PA spec v0.1 (`75e29265`) → E1 harness IMPL 12 files / 2781 LOC (`93069c29`) → E2 APPROVE-CONDITIONAL 0 MUST / 3 SHOULD → E4 PASS 7/7 → Merge (`8d8a0123`) → PA SHOULD-FIX memo (`5df39d13`, 3 accept-with-caveat 0 IMPL fix) → Spec v0.2 patch (`34af2d2e`) → SQL fix (`d2286c05`) → Sweep 81 cells (1.4 sec wall) → PA cell selection report (`2b65d3f1`, 78 unique cells / 35 INDETERMINATE / 43 TRUE FAIL / top `G-AB-01-C90` fill 70.8% / +3.37 bps) → E1 Rust 14 LOC `timeout 30s → 90s` (`820f0532`) → E2 light APPROVE-CONDITIONAL → E4 PASS 7/7 (`4cc32ff6`) → Merge (`67f1a047`) → operator-authorized rebuild + restart (engine PID 1253085 → **1506208**, binary mtime 2026-05-18 13:50 UTC). **Phase 2a 14d observation clock reset @ 13:50 UTC**; 24h AC-A SQL verification target ~2026-05-19 13:50 UTC. v48 carry-forward: v47 recovery + Wave 1 merge state preserved. **NEW 2026-05-18 ~10:30 UTC**: third-party assessment + own PG verify revealed Phase 1b 12H post-restart sample = **4 close fills, 100% `close_maker_attempt=TRUE` BUT 100% `close_maker_fallback_reason=timeout_taker`** → real fee saving = 0% so far (maker offset_bps=0.5 + buffer_ticks=1 + timeout 30s/15s too tight for sparse alt-coin spreads). Operator scheduled **P0 Phase 1b parameter calibration sweep + replay counterfactual** for AFTER 12H test window closes (~2026-05-18 11:54 UTC). Pre-calibration code path is verified correct (TOML activator + maker_attempt instrumentation working); root cause is parameter tuning, NOT IMPL bug. v47 carry-forward: W-AUDIT-8a Wave 1 (B-REM-1 `49975eeb` / B-REM-5 `5997dd43` + ADR-0023 `1b614daf` / C1-LIQ-WRITER `7ab6c22d` + healthcheck `[67]` `d8938a78`) merged via `ef0dfc6e` / `5aeae75c` / `25413e96`. EDGE-P2-3 Phase 1b runtime activator deploy chain remains CLOSED 2026-05-17 23:54 (engine PID 1143103, `runtime.use_maker_close=true`). W-AUDIT-8b Round 2 RED_FINAL tombstoned via spec v0.4 (`ef7ea6c2`) + AMD v0.7 (`71f2283b`). Wave 2 (`C2-ORDERFLOW` 5pd HIGH + `C3-SPREAD` + `D-CONTRACT-LOCK` 2pd PA-only) deferred to Sprint N+4. Previous v46 production `allLiquidation*` writer revival (`0e8a8ae8` / `bedc40c3`) remains CLOSED.
Maintenance contract: keep this file as the active dispatch queue per
`docs/agents/todo-maintenance.md`; stable project context belongs in
`README.md`, and agent operating rules belong in `CLAUDE.md` /
`.codex/MEMORY.md`.
- **v46 production liquidation revival**: ✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17；`0e8a8ae8` revives only C1-approved `allLiquidation.{symbol}` in startup and scanner dynamic production builders while legacy `liquidation.` / `price-limit.` / `adl-notice.` remain excluded；`bedc40c3` fixes runtime log observability (`topics_per_symbol=8`, `all_liquidation_enabled=true`)；local + Linux release lib both green `2969/0/1`；trade-core engine-only rebuild/restart completed with PID `1066422`；post-healthcheck: `OPENCLAW_AUTO_MIGRATE=0`, `OPENCLAW_ENABLE_PAPER=0`, V094/V095 still registered, `market.liquidations` PK `(symbol, ts, side, qty, price)`, public WS subscribed `200` topics / `20` batches, no handler/rate-limit/topic-poison errors, and 3 real liquidation rows landed. Paper remains disabled via `pipeline_snapshot_paper.json disabled=true` (`OPENCLAW_ENABLE_PAPER != 1`). PM consolidated report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--deploy_readiness_consolidated_audit.md`。
- **v45 deploy-readiness runtime closure**: ✅ V094/V095 + Phase 1b engine restart DONE 2026-05-17；`b867e452` restored Linux cargo baseline to `2969/0/1`；V094 registered with checksum `d7db4e674cc0505da787861b6777717059d69902137057350a3b4b0a5e527a41a1e7b7e3cb559ba2fb8a4dd3fead2512`；V095 registered with checksum `e25f110594587cddafd1e08f7699da593fe63c64af6d26415356c00b4534d8f60f0e67d7640ab8a6b18ba6ba742ca15b`；`market.liquidations` PK is now `(symbol, ts, side, qty, price)`；Phase 1b engine-only rebuild/restart completed at commit `74f88269` before V095 docs sync；`OPENCLAW_AUTO_MIGRATE=0` and `OPENCLAW_ENABLE_PAPER=0` remained unchanged. PM consolidated report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--deploy_readiness_consolidated_audit.md`。
- **v44 W-AUDIT-8c correction closure**: ✅ SOURCE/TEST + V095 LINUX APPLY + PRODUCTION WRITER REVIVAL DONE 2026-05-17；V095 source migration preserves liquidation item identity with `(symbol, ts, side, qty, price)`；parser/writer fail closed for invalid `allLiquidation` rows；corrected Bybit side mapping (`Buy` long liquidation / `Sell` short liquidation) is tested；V095 Linux PG transaction dry-run x2 PASS + MIT idempotency re-sign APPROVE-CONDITIONAL；V095 manual apply/register DONE in v45；production `allLiquidation.{symbol}` subscription/writer revival DONE in v46 after explicit authorization. PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md`；dry-run evidence: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--v095_linux_pg_dry_run_result.md`；MIT re-sign: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md`。
- **v43 Option A source/test closure**: ✅ DONE 2026-05-16；`a6e17d5d` adds W-AUDIT-8b v0.3 4-cell sweep tooling with A3/E2/E4 approval；`ea4ceca6` lands Phase 1b close-maker-first source/test bundle with Worktree B dispatch, V094 audit writer, fallback terminalization, and healthchecks. No deploy / production SQL migration / runtime restart / auth mutation / paper/live/mainnet enablement. PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md`。
- **v42 role profile/memory hygiene**: ✅ DONE 2026-05-16；新增 `docs/agents/role-profile-memory-standard.md`，所有 `docs/CCAgentWorkSpace/*/profile.md` 接入共同角色契約，所有 `memory.md` 頂部加 historical-memory 解讀契約；A3/E3/E4/E5/QA/PM 等 profile 去除「當前狀態即真相」歧義，改為 historical baseline + `TODO.md`/latest report/runtime evidence 為準。歷史 memory 正文未刪除。
- **v41 agent-settings refresh**: ✅ DONE 2026-05-16；all Claude/Codex agent role files now preload operating memory + `README.md` + `docs/agents/context-loading.md`, route active state to `TODO.md`, and no longer depend on stale numbered-memory sections, 11-tab, bilingual-comment, or 1200-line assumptions. Codex role index and agent-facing skills/profiles were aligned.
- **Wave 1-4 全 closed**: WP-01/02/05/09 (Wave 1) + WP-03/04/07/10/BB-MF-3 (Wave 2) + WP-06/08/13/WP-13-leftover (Wave 3) + WP-11 Phase 1 (Wave 4); WP-12 DEFERRED by design.
- **v35 rebuild + restart**: trade-core engine PID 69581 / API PID 69674 (2026-05-16); Wave 2-4 Rust source IMPL all deployed; runtime env at 2026-05-16 01:00 UTC had `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`, `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`, `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv`.
- **Round 4 三角 cross-validation (PA + FA + CC)**: 一致 verdict A/C/A for 3 P0 → operator 確認同意。
- **P0-1 WP-04 $2 RATIFY**: ✅ DONE 2026-05-16 commit `e24c1d8f`；operator ack at `docs/CCAgentWorkSpace/Operator/2026-05-16--wp04_budget_ratification.md`；governance debt cleared。
- **P0-2 WP-03 OU sigma deploy-gate**: ✅ Option C selected；PA spec `docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md` (~600 LOC) + `[69]` healthcheck design land；revert flag 三層 trigger logic (12h/24h/7d)；Operator notification ADR-0020 manual-only。**P1-WP03-DEPLOY-GATE-IMPL ✅ DONE 2026-05-16 commit `d6ff77f7`**：`checks_wp03_deploy_gate.py` 587 LOC + test 528→592 LOC（18/18 PASS）+ runner.py wire `[69]` + `__init__.py` re-export；完整工作鏈 E1→E2 RETURN→E1 round 2→E2 APPROVE（MEDIUM-1 ZERO_FILLS false-positive secondary guard 修 + LOW-1 REQUIRED escalation msg 加 `revert_recommended=false` hint + new test `test_zero_fills_env_override_age_mismatch`）；E4 386/0 sibling regression PASS；2 P2 follow-up: P2-WP03-MSG-STRUCT + P2-WP03-ALERT-FLAG-INDEPENDENCE；Linux-flagged 6 items（deploy 後 cron 第一次 fire empirical verify）。
- **P0-3 Race protocol SOP Phase 2 rollout**: ✅ APPROVE + enforce 立即生效 2026-05-16 18:00+；`.claude/agents/E2.md` §5 race check 5 條 + `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` PM §6 模板 + `docs/lessons.md` Phase 2 entry；2026-05-30 PM 2-week review。
- **P1 #5 F-09 model_tier TOML extraction**: ✅ DONE commit `3b055c98`；ArcSwap snapshot path；3 TOML 加 `model_tier="l1_9b"`；E2 APPROVE / E4 PASS 2917/0/1。
- **P1 #7 [68] portfolio_resting_exposure healthcheck**: ✅ DONE commit `3b055c98`；ID conflict [58]→[68] resolved；562+408 LOC new；E2 APPROVE-CONDITIONAL / E4 PASS 368/0。
- **P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG**: ✅ DONE 2026-05-16 on `trade-core`；V092 physical continuous aggregates applied online; V091/V092/V093 `_sqlx_migrations` metadata repaired to max_applied=93 / rows=90; checksum verify drift_count=0. PM closure report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_3_5_linux_migration_backlog_closure.md`。
- **P2 maintenance hygiene batch**: ✅ DONE 2026-05-16 local source/test closure for `P2-H0-DISPLAY-LABEL-1`, `P2-START-LOCAL-HELPER`, `P2-PA-CALLPATH-GREP-RULE`, and `P2-CROSSTAB-I18N`。H0 GUI endpoint now returns `display_only=true`; local Control API launchers use `resolve_openclaw_api_bind_host()`; PA/E2 audit skill requires P0/P1 leak/bias production caller grep; listed cross-tab static GUI files have `实盘/平仓/请检查` grep=0. PM closure report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--p2_maintenance_hygiene_closure.md`。
- **P1 #4 C1 v2 24h proof**: ✅ TECHNICAL PASS / APPROVE-CONDITIONAL + PRODUCTION WRITER REVIVAL DONE 2026-05-17；`trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md` verdict `PASS_C1_PROOF_CANDIDATE`, `c1_proof_eligible=true`, uptime ratio `0.999991`, failures `0`；BB APPROVE after corrected side mapping (`Buy` long liquidation / `Sell` short liquidation)；W-AUDIT-8c/V095 source-test idempotency correction is DONE, V095 Linux PG dry-run x2 PASS, MIT re-sign cleared the schema/idempotency blocker, V095 is applied on Linux, and v46 source/runtime revival now subscribes C1-approved `allLiquidation.{symbol}` with 3 real rows landed. PM result: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md`。
- **P1 #6 BB-MF-3 production wiring**: ✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17；Phase 1b checkpoint `ea4ceca6` is deployed after V094 apply + engine-only rebuild/restart；close-maker audit fields can populate on subsequent fills。
- **P1 #7 7d budget cap monitoring**: ⏳ passive deploy 後 1 週 (2026-05-23+)。
- Stage 1 promotion evidence is Demo-only per AMD-2026-05-15-01. A4-C remains diagnostic-only/no-revive unless a future materially new predictive variable is preregistered and passes a fresh Stage 0R gate.
- Operator 7 條 action 進度: 5/7 DONE + 2/7 passive wait. Wave 1-4 真實完成度 = TRULY DONE for source/test/deploy + governance A 99.0%.

This file is the active work queue only. Historical closures, stale observation
tables, and superseded OpenClaw/Gateway assumptions are archived in
`docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md` and
`docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`.
v21 cleanup archive:
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.
v24 stale-row audit archive:
`docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`.
v26 alpha-path dispatch report:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--alpha_path_phase_c_dispatch.md`.
v27 intent-freeze post-grace closure report:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_intent_freeze_27_post_grace_closure.md`.
v28 Phase C0 liquidation inventory report:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8a_phase_c0_liquidation_inventory.md`.
v29 P0-MICRO-PROFIT alpha prework:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--micro_profit_alpha_prework.md`.
v29 A4-C PM/PA/FA unblock/archive engineering card:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_unblock_engineering_card.md`.
v29 A4-C RCA start:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_stage0r_rca_start.md`.
v30 TODO/source three-side sync:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--todo_v30_three_side_sync.md`.
v31 A4-C RCA final + C1 proof start:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md`.
v32 W-AUDIT-8b review + Stage 0R design:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8b_review_stage0r_design.md`.
v35 current-progress sync + rebuild decision:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`.
v36 completion cleanup archive:
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
v37 Stage 1 / A4-C active-marker cleanup:
`docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`.
W-AUDIT-8b adversarial hardening commit `1499778b`:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_adversarial_hardening.md`.
v39 Wave 3.5 Linux PG migration backlog closure:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_3_5_linux_migration_backlog_closure.md`.

## §0.0 PM Freeze — Demo-Only Stage 1 + A4-C Tombstone Guard

**Status**: ACTIVE PM freeze; AMD-2026-05-15-01 now carries the rebase authority.

- Stage 1 promotion evidence is **Demo-only**: Stage 0 shadow → Stage 0R replay preflight (`eligible_for_demo_canary=true/false`) → Stage 1 Demo micro-canary (1 strategy × 1 symbol × 7d). Stage 0R is not Stage 1 PASS.
- Paper is not an active promotion lane. Any plan, command, env file, script, or runtime launch that sets `OPENCLAW_ENABLE_PAPER=1` for promotion evidence remains **BLOCKED** unless a future operator decision explicitly reopens paper for non-promotion diagnostics.
- A4-C tombstone: `W-AUDIT-8d` BTC→Alt Lead-Lag is archived from active promotion and closed no-revive for the BTC 1m return + xcorr feature shape. Keep `panel.btc_lead_lag_panel` / `[57]` diagnostic-only; do not use A4-C as a Stage 0R promotion candidate or Stage 1 Demo cohort source.
- Future A4-C reopen requires a materially new predictive variable, preregistered validation, and a fresh strategy×symbol Stage 0R packet with `eligible_for_demo_canary=true`. Threshold loosening, post-hoc symbol picking, or reusing paper evidence are non-triggers.
- Current active alpha gates: W-AUDIT-8b Stage 0R tooling has v0.3 sweep source/test checkpoint `a6e17d5d` and waits for panel ≥7d plus QC/MIT/BB Round 2 verdict; W-AUDIT-8a C1 transport proof is `PASS_C1_PROOF_CANDIDATE` with BB corrected side mapping approved; W-AUDIT-8c source/test correction, V095 migration source, V095 Linux PG dry-run x2, MIT re-sign, V095 Linux apply, and production `allLiquidation.{symbol}` writer revival are DONE. No liquidation strategy launch/promotion gate is implied by writer revival.

---

## §0 Sprint Milestone Banner（FA 業務鏈視角，63% → 85-89%）

| Sprint | Week | 主題 | E1 capacity | Business chain milestone |
|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY: W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | **5 active + 1 stand-by** (operator (a)) | 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING: 8a Phase B+C + 8b Stage 0R packet + **Stage 1 Demo micro-canary** prep after a future green Stage 0R | 4/6 | 65→70% must be recalculated after demo canary evidence |
| **N+2** | W5-W6 | 8a Phase D + Stage 2 demo cohort 14d（only after Stage 1 demo evidence） | **5 active + 1 stand-by** | 70→76% rebase pending |
| **N+3** | W7-W8 | 8c (Liquidation) IMPL + 8e (R-2) spec + Stage 3 demo full | 4/6 | 76→80% |
| **N+4** | W9-W10 | 8f (R-3) spec + 8b (Funding Skew) IMPL + 8e IMPL + Track W 收尾 | 4/6 | 80-83% |
| **N+5** | W11-W12 | 8f IMPL + 8g (R-4) spec + **first per-alpha-source supervised live** | **5 active + 1 stand-by** | **85-89%** |

**Stand-by E1 啟用條件**（operator 拍板 2026-05-09 (a)）：W-AUDIT-9 T3 stage-aware exception path 翻車 / W-AUDIT-8a Phase A byte-diff fail / W-AUDIT-6d mid-ground 與 8a Phase A 序列化 deadline 撞牆 / 任一 active E1 health incident → stand-by 即時補位。

**規劃帶 supervised live 概率**（FA）：6/15 樂觀 ~30% / 6/30 中位 ~40% / 7/15 悲觀 ~25% / 8/15 極悲觀 ~5%。

---

## §2 Architecture Boundary

- Formal product: `玄衡 · Arcane Equilibrium`.
- Bybit is the only exchange target.
- Rust `openclaw_engine` remains the trading, risk, strategy-config, and execution authority.
- Python/FastAPI is the control plane, bridge, GUI backend, replay/orchestration surface, and local 5-Agent runtime host. It is not the direct trading truth layer.
- The canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now the OpenClaw Control Console.
- External OpenClaw Gateway is communication/mobile/supervisor/proposal relay only. It is not a trading conductor, not the local 5-Agent runtime, and not a second GUI.
- Local Scout / Strategist / Guardian / Analyst / Executor stay inside TradeBot. Cloud L2 calls must go through one supervisor escalation packet, explicit budget/model config, and durable `agent.ai_invocations` ledger reservation.
- Scanner is always-on infrastructure for market context, active-universe attribution, route fitness, opportunity evidence, and legacy would-block audit. It is not a trading authority and cannot hard-gate opens, closes, live auth, or order dispatch.
- `MessageBus` is legacy/advisory trace. Authoritative agent promotion requires typed lineage: StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease / idempotency -> ExecutionReport.
- Replay is advisory and diagnostic. Replay can fast-track preflight; it cannot substitute for runtime lineage or authorize live promotion.
- **Graduated Canary rebase**（AMD-2026-05-15-01 supersedes AMD-2026-05-09-03 Stage 1 paper semantics）：alpha-bearing pathway now uses Stage 0 shadow → **Stage 0R Replay Preflight** (`eligible_for_demo_canary=true/false`, not Stage 1 PASS) → **Stage 1 Demo micro-canary** (1 strategy × 1 symbol × `Environment::Demo` × 7d) → Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING。DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 Latest State

### Current State (2026-05-16 PM cleanup)

- W-C MAG-082 Stage 2 **WINDOW_PASS 2026-05-11** and W-D MAG-083/MAG-084 **DONE 2026-05-11** are closed; proposal/mobile/Stage 3+/true-live gates remain separate and still blocked by edge/LG/ops prerequisites.
- A4-C BTC→Alt Lead-Lag active-promotion marker is removed: Step 5b and RCA are archived as **GATE-RED / no-revive** for the BTC 1m return + xcorr feature shape; `panel.btc_lead_lag_panel` remains diagnostic-only. The OI-confirmed 5m packet is only a replay spec and does not change eligibility.
- `[55]` is source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; `[67]` is restored to PASS after feature baseline apply; `[4]` phys lock and `[Xb]` triangulation are PASS after `7108035d`.
- V079 / `learning.strategy_trial_ledger` is runtime-applied on `trade-core` (migrations through V090 applied; 16,212 ledger rows observed). Old "V079 not applied / engine still 5/8 binary" text is archived in `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`.
- Remaining business root cause: 5 textbook strategies still lack durable positive net edge. `P0-EDGE-1`, `P0-LG-1/2/3`, `P0-OPS-1..4`, Alpha Surface Phase C/D, and alternative alpha candidates are the current path.
- **EDGE-P2-3 Phase 1b close-maker-first refactor — Round 1 Design/Governance CLOSED + Worktree B DEPLOY DONE 2026-05-17**: round 1 歷史 + spec v1.3 / AMD v0.4 / V094 spec archived at `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`；Option A Worktree B source/test landed at `ea4ceca6` with A3/E2/E4 approval；`b867e452` fixed the test-only phys-lock literal guard regression；V094 Linux apply + engine-only rebuild/restart are DONE. phys_lock live enablement remains deferred to Phase 2b. Honest 認知：本 refactor 是 execution-quality optimization（fee saving ~$50-$200/year per E3 empirical），不解 trading losses root cause（5 textbook 策略 structural alpha deficit）；真實治癒走 W-AUDIT-8a/8b/8c alpha source 軸。
- **Trading losses Round 2 — Alpha Source Push Option A SOURCE/TEST DONE 2026-05-16 + W-AUDIT-8c correction/V095 APPLY DONE 2026-05-17**: operator trigger 後同步派發 2 路：(P0) Phase 1b Worktree B source/test done `ea4ceca6` and runtime deploy done after V094；(P1) W-AUDIT-8b Round 2 Phase A sweep tooling done `a6e17d5d`。C1 transport proof passed 2026-05-17; W-AUDIT-8c correction source/test includes V095 idempotency source; V095 Linux PG dry-run x2 PASS + MIT re-sign APPROVE-CONDITIONAL + Linux apply/register DONE。Production writer revival still waits for separate AMD/source/config dispatch；no production `allLiquidation*` enablement / auth mutation / paper/live/mainnet enablement yet.
- **2026-05-18 EDGE-P2-3 Phase 1b RUNTIME ACTIVATOR BLOCKER — ✅ RESOLVED via deploy chain CLOSED (see entry below)**: original RCA preserved for governance audit — post-deploy 4h `trading.fills` sample showed 0% maker_attempt rate (18 grid_close_short + 2 ma_reverse_cross all `close_maker_attempt=FALSE` + `fallback_reason=NULL`). E2 adversarial RCA `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_0_attempt_rca.md` identified cold-default `use_maker_close=false` + ZERO production callers for `set_use_maker_close_runtime`. Resolution: PA design `2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md` Option A TOML activator → E1 second-dispatch IMPL `18081551` (~40 LOC `pipeline_ctor.rs` + `pipeline_config.rs` + `risk_config_demo.toml`) → E2 re-review APPROVE 0 new MUST-FIX (`a94825cb`) → E4 PASS 12/12 (`af3b3010`) → QA APPROVE 0 BLOCKER (`a1b3ca908`) → merge `c737a1e4` → restart 2026-05-17 23:54 UTC engine PID 1143103. AMD-2026-05-15-02 v0.5 (`23e6b6b2`) added Runtime Activation Layer wording. AC-A 24h window verification still pending statistical significance per QA template.
- **2026-05-18 W-AUDIT round 2 milestones**: (a) **W-AUDIT-8b Round 2 Phase B preliminary sweep** on panel 6.92d (operator-auth override pending 7.0d natural confirm ≈2026-05-18 01:30 CEST) returned **8/8 cells RED HIGH conf** with DSR=0 / PBO 0.64-0.75 / z=1.2 INJUSDT dilution -9.64 bps / crowded_long_fade dead trigger all z (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`); 7.0d confirm rerun + 4-agent QC/MIT/BB/FA review packet template (`docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md`) ready. (b) **W-AUDIT-8a Phase B/C/D 11-worktree decomposition** done (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md`): 36.1 pd / 8.5 wallclock weeks @ 4 active E1. **Wave 1 ✅ MERGED 2026-05-18** via single-sequential E1+E2 chain post race-incident recovery: B-REM-1 dispatch snapshot contract tests `49975eeb` (merge `5aeae75c`), B-REM-5 SourceAvailability schema `5997dd43` + ADR-0023 `1b614daf` (merge `ef0dfc6e`, E2 APPROVE per `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8a_b_rem_5_e2_review.md`), C1-LIQ-WRITER LiquidationPulse provider `7ab6c22d` + healthcheck `[67]` `d8938a78` + W-AUDIT-8c spec v0.3 (`06897175`) (merge `25413e96`, E2 APPROVE-CONDITIONAL + QA APPROVE WITH RESERVATIONS per `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--w_audit_8a_c1_liq_writer_qa_deploy_readiness.md`). Wave 2 (`C2-ORDERFLOW` 5pd HIGH + `C3-SPREAD` + `D-CONTRACT-LOCK` 2pd PA-only) **deferred to Sprint N+4** (W9-W10, 2026-06-07..13).
- **2026-05-18 AMD-2026-05-15-02 v0.5 land + multi-agent dispatch race incident + recovery**: AMD v0.4 → v0.5 wording patch (`23e6b6b2`) adds explicit Runtime Activation Layer + three-env TOML table + Phase 2b live_demo Demo-only guard conflict defer to AMD §3 line 84 (closes E2-identified spec/IMPL gap). **4-E1 + 1-PA parallel dispatch on 2026-05-18 SUSPENDED** due to (a) `isolation=worktree` 機制不可靠（hook 未設 + agents 用絕對路徑 write main tree），(b) agents cross-wrote main tree（Phase 1b activator agent + B-REM-1 agent 都動 `rust/openclaw_engine/src/tick_pipeline/`，導致 `step_4_5_dispatch.rs +246 LOC` (B-REM-1 dispatch snapshot contract tests) leaked into `feature/phase-1b-runtime-activator` branch alongside Phase 1b activator IMPL），(c) AMD v0.5 patch 在 main tree 被某 agent 過程 silent revert（已 re-apply）。**Recovery state ✅ CLOSED 2026-05-18 via single-sequential dispatch**: Phase 1b activator IMPL second-dispatch `18081551` (post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1) → merge `c737a1e4`. B-REM-5 SourceAvailability `5997dd43` E2 APPROVE → merge `ef0dfc6e` + ADR-0023 `1b614daf`. B-REM-1 dispatch snapshot contract tests re-dispatched as `49975eeb` → merge `5aeae75c`. C1-LIQ-WRITER LiquidationPulse provider re-dispatched as `7ab6c22d` + healthcheck `[67]` `d8938a78` → merge `25413e96`. **Lesson learned**: 不再多 E1 同時並行；single-agent sequential + E2 chain 完才下個 — 本批 recovery 是這條規則的首次實證；後續所有 W-AUDIT-8a Wave 2+ 工作必繼承。
- **2026-05-18 Phase 1b runtime activator deploy chain CLOSED + W-AUDIT-8b Round 2 RED_FINAL tombstoned**:
  - **Phase 1b deploy chain APPROVED**: E1 second-dispatch (`18081551`, post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1) → E2 re-review APPROVE 0 new MUST-FIX (`a94825cb`) → E4 PASS 12/12 runs Mac+Linux release cross-arch (`af3b3010`) → QA APPROVE 0 BLOCKER (`a1b3ca908`) → merge to main (`c737a1e4`) → operator-代跑 restart_all.sh --rebuild on trade-core UTC 2026-05-17 23:54 → engine PID 1066422 → **1143103** with new binary containing `runtime.use_maker_close` activator. `risk_config_demo.toml [runtime] use_maker_close=true` confirmed via grep + engine boot log shows `risk_demo_version=2` loaded. **Post-restart 90min sample: 1 whitelist close, 0 maker_attempts (n=1 too small)**; AC-A/B/C verification requires ~24h window for statistical significance per QA template. Phase 2a 14d observation clock t=0 = first AC-A SQL PASS UTC timestamp (NOT restart timestamp). **Cross-wave consistency check pending** (QA recommendation #3 — restart triggered W6/W7/W1 main-landed-but-not-deployed sources too; PM 24h audit packet §3.9).
  - **W-AUDIT-8b Round 2 RED_FINAL tombstoned**: PA 7.0d sweep rerun (panel 7.0049d natural gate, +7min margin, 4/4 empirical assertion gates PASS) returned 8/8 cells RED HIGH conf 100% aligned with preliminary 6.92d (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md`). 4-agent independent review **4/4 APPROVE concur RED_FINAL** (BB 0/2/3, QC 0/4/2, FA 3/2/3, MIT 0/4/3 MUST/SHOULD/NTH); MIT report `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md` (`d3fe4063`); BB/QC/FA inline per profile rule; consolidated verdict `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_4agent_consolidated.md` (`ffdbc2d0`). **Cross-agent consensus root causes**: (a) z 39x asymmetry (MIT empirical: z≥+1.5 0.27% vs z≤-1.5 10.5%) + Bybit USDT-perp 25-sym 結構性 funding tail bimodal (BB structural) → crowded_long_fade dead **data-structural, NOT demo silent degradation NOT strategy design bug**; (b) INJUSDT 87% concentration in 2026-05-13 single-day event (MIT) → effective independent obs ≈ 2-3 days; (c) `_n_eff` formula deterministic horizon-overlap (not cluster-aware) — RED robust but W-AUDIT-8c+ must retrofit. **AMD-2026-05-15-02 v0.6 → v0.7 wording patch** (`71f2283b`) §8 condition 3 funding-related general + tombstone clause. **W-AUDIT-8b spec v0.3 → v0.4 tombstone amendment** (`ef7ea6c2`) + NEW `Branch-Level Dormancy Retire Path` governance hardening (FA-MUST-FIX-2 forward-applicable to W-AUDIT-8c/8a/8e/8f specs). **REJECTED**: Round 3 zoom-in (MIT ROI≈0) / 28d panel expansion / dual-AMD. **Redirect path**: W-AUDIT-8c Liquidation Cluster + W-AUDIT-8a Phase B/C/D per fix-plan v1.1 §9.4 critical path (11-worktree decomposition, Wave 1 = B-REM-1/5 + C1-LIQ-WRITER ready).
- **2026-05-18 ~10:30 UTC EDGE-P2-3 Phase 1b 12H sample BLOCKER — 100% timeout fallback → P0 calibration scheduled after 12H window closes**: Operator surfaced third-party assessment + main session PG verify converged on same finding. **PG data (post-restart UTC 2026-05-17 23:54 + ~10.5h)**:
  ```
  engine_mode | close_maker_attempt | close_maker_fallback_reason | count
  demo        | f                   |                             | 23
  live_demo   | f                   |                             | 13
  demo        | t                   | timeout_taker               | 4
  ```
  4 attempted close fills (all on whitelist exit_reasons: 3 `grid_close_short` + 1 `phys_lock_gate4_giveback`) were maker_attempt=TRUE BUT **100% fell back to taker via timeout** → real fee saving = 0% currently. **Pre-calibration code path is verified correct** (TOML activator firing + maker_attempt instrumentation populating audit fields); root cause is **parameter tuning** (offset_bps=0.5 + buffer_ticks=1 + timeout 30s grid / 15s phys_lock too tight for sparse alt-coin spreads), NOT an IMPL bug. **Schedule**: 12H test window ends ~2026-05-18 11:54 UTC; after window closes → P0 dispatch sequence below. Pre-window remaining ~1.5h is observation-only (no parameter changes during 12H window per AC-A integrity). Operator instruction: "12H 後做 calibration，然後三端同步".

---

## §4 Active Dispatch Queue

**Dispatch Order** — ✅ MAG-082 runtime lineage PASS 2026-05-11；✅ MAG-083 三角 audit + MAG-084 sign-off CLOSED 2026-05-11；W-D wave closed。但 proposal relay / Telegram/WebChat / 第二 GUI / Stage 3/4 / true live autonomy 仍受 W-AUDIT-3..7 + LG-2/3/4 + edge net-positive + ops gates 限制，不因 W-D closure 自動解除。

**Status Legend**: ✅ DONE / ⏳ PENDING / 🟡 PARTIAL / 🔵 ACTIVE / ⛔ DEFER

### §4.1 Wave Roster (DUAL-TRACK + 8a-8h)

| Rank | Wave | Tag | Owner Chain | Status / Target | Exit Criteria |
|---:|---|---|---|---|---|
| 1 | `W-F` Edge/data quality + Live Gate foundation | alpha-bearing | PM → QC/MIT/PA → E1/E4 → PM | ⏳ **PENDING** before true-live | H0 production caller, pricing binding, supervised-live state machine. |
| 2 | `W-G` Proposal/approval/mobile relay | alpha-neutral | PM → CC/FA/PA → E1/E2/E4 → PM | 🟡 **BACKEND FOUNDATION DONE**（待 mobile relay）| Gateway/console proposal/approval relay; no direct order/config/live-auth. |
| 3 | `W-AUDIT-4` ML 基座 + dead schema | alpha-bearing | E1×6 + MIT + E2 + E4 | 🟡 **PARTIAL** | Corrected retained scope still active in §11.2: `cost_edge_advisor_log`, `drift_events`, two companion views, and dropped/no-DDL `scorer_predictions`; long-wave fix remains mounted into `W-AUDIT-8f`. |
| 4 | `W-AUDIT-8a` Alpha Surface Foundation | alpha-bearing | PA → E1 → E2 → E4 + MIT/QC/CC/BB → PM | ✅ **C1 TRANSPORT PASS + WRITER REVIVAL DONE 2026-05-17 + WAVE 1 MERGED 2026-05-18** | Phase A/B/C0 complete; v1 C1 proof FAIL_CONNECTION 5h/24h → v2 resilient harness IMPL `25396b0b` + consolidated 6-fix `8d2eef58` 全鏈 GREEN；C1 24h artifact on `trade-core` is `PASS_C1_PROOF_CANDIDATE`; BB approved corrected side mapping (`Buy` long liquidation / `Sell` short liquidation); MIT schema/writer idempotency condition is cleared by V095 apply; production `allLiquidation.{symbol}` writer revival landed in `0e8a8ae8`/`bedc40c3` with Linux rows observed. **Phase B/C/D 11-worktree Wave 1 (B-REM-1 `49975eeb` + B-REM-5 `5997dd43` + ADR-0023 `1b614daf` + C1-LIQ-WRITER `7ab6c22d` + healthcheck `[67]` `d8938a78`) MERGED 2026-05-18 via `ef0dfc6e` / `5aeae75c` / `25413e96`** with E2 APPROVE + E4 PASS + QA APPROVE WITH RESERVATIONS. Wave 2 (`C2-ORDERFLOW` 5pd HIGH + `C3-SPREAD` + `D-CONTRACT-LOCK` 2pd PA-only) deferred to Sprint N+4 (W9-W10, 2026-06-07..13) per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md`. PM result: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md`。 |
| 5 | `W-AUDIT-8b` A4-A Funding Skew Directional | alpha-bearing | PA spec → Stage 0R query/report + QC + MIT + BB review | ⛔ **TOMBSTONED 2026-05-18 Round 2 RED_FINAL** | Spec v0.3 → **v0.4 tombstone** (`ef7ea6c2`) per Round 2 7.0d sweep 8/8 cells RED HIGH conf + 4-agent (BB/QC/FA/MIT) **4/4 APPROVE concur** (`ffdbc2d0` consolidated verdict). AMD v0.6 → v0.7 (`71f2283b`) §8 condition 3 funding-related general + tombstone clause. No-revive on same feature shape per A4-C precedent. NEW `Branch-Level Dormancy Retire Path` governance hardening forward-applicable to W-AUDIT-8c/8a/8e/8f. **Redirect**: W-AUDIT-8c + W-AUDIT-8a Phase B/C/D per fix-plan v1.1 §9.4 critical path. REJECTED: Round 3 zoom-in / 28d panel expansion / dual-AMD. |
| 6 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction | alpha-bearing | PA spec → E1 + E2/E4 + MIT + BB → PM | ✅ **SOURCE/TEST + V095 LINUX APPLY + WRITER REVIVAL DONE 2026-05-17** | V095 source/test preserves one `data[]` item per row via `(symbol, ts, side, qty, price)`; parser/writer fail closed; corrected side mapping tested; V095 Linux PG dry-run x2 PASS + MIT re-sign + Linux apply/register DONE; production `allLiquidation.{symbol}` writer revival DONE; strategy launch remains separate. |
| 7 | `W-AUDIT-8e` (R-2) Strategist Alpha Source Orchestrator | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+4 spec → N+5 IMPL | AlphaSourceRegistry + dynamic Sharpe-by-regime + Hypothesis sourcing. |
| 8 | `W-AUDIT-8f` (R-3) Hypothesis Pipeline + W-AUDIT-4 ML | alpha-bearing | PA spec → E1 IMPL + MIT spec | ⛔ **DEFER** Sprint N+5 IMPL | learning.hypotheses state machine + W-AUDIT-4 dead schema root-cause closure. |
| 9 | `W-AUDIT-8g` (R-4) Per-alpha-source Live Promotion Gate | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+7+ | LiveBudget(alpha_source_id, slice) replacement for system-wide live_reserved model. |
| 10 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | alpha-neutral | E1a + A3 review | ⛔ **DEFER** Sprint N+4-N+6 | A3 tab expansion follow-up. |
| 11 | `W-AUDIT-10` (R-5) Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec → E1 IMPL | ⛔ **DEFER** 中期 | CI gate spec drift > 7d auto-fail + module/table lifecycle header. |
| 12 | `EDGE-P2-3 Phase 1b` Close-Maker-First Refactor | alpha-impact-adjacent execution-quality | PA → E1 → E2 → E4 → QA → PM | ✅ **DEPLOY DONE 2026-05-18, AC-A VERIFICATION PENDING 24h** | Full chain APPROVED: E1 second-dispatch `18081551` (post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1) → E2 re-review APPROVE 0 new MUST-FIX → E4 PASS 12/12 cross-arch → QA APPROVE 0 BLOCKER → merge to main `c737a1e4` → operator-authorized restart UTC 2026-05-17 23:54 (PID 1066422 → 1143103). AMD v0.6 → v0.7 (`71f2283b`) wording patch §8 condition 3 land. `runtime.use_maker_close=true` confirmed in demo TOML. Phase 2a 14d clock t=0 trigger = first AC-A SQL PASS (attempt_pct ≥ 25% on demo whitelist closes within 2h post-restart), NOT restart timestamp. Post-90min sample: 1 whitelist close, 0 attempts (n=1 too small). PM 24h post-deploy verification audit pending dispatch (template `2026-05-18--pm_24h_post_deploy_verification_audit_packet.md`). Cross-wave consistency check pending (QA recommendation #3). |

### §4.1.1 Completed Sprint Ledgers Archived

Sprint N+0, Sprint N+1 D+0, Phase 3, Phase 4 W1+W2, and v35 12-agent
completion details are closed and archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md` and
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`. Active
follow-ups remain in §10 / §11 / §12.

### §4.2 Cross-Wave Conflict Resolution（4 條，PA §3.3 必繼承）

| # | 衝突 | Files / Surface | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | **序列化**：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | **W-AUDIT-3b 必先 land**；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群策略候選 ↔ W-AUDIT-9 Stage 1 Demo cohort 選擇 | governance/canary | **RESOLVED 2026-05-16**: Stage 1 is Demo-only after a future green Stage 0R. A4-C is tombstoned diagnostic-only and must not be selected as the Stage 1 cohort source. |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | docs/execution_plan | **TODO IDs 為 SoT 2026-05-15**: `8b`=A4-A Funding Skew，`8c`=A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現 tracked as `8e/8f`），不得拿來當策略 spec。 |

---

## §5 Active Sign-off Delta

Full Sprint N+0 22-invariant ledger is closed and archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Current sign-off deltas only:
- ⛔ **A4-C active-promotion marker removed 2026-05-16**: Step 5b / RCA details
  are archived as no-revive; retain only the tombstone guard and diagnostic
  panel reference in active docs.
- 🟡 **OI-confirmed 5m Stage 0R packet remains non-promotional**: the packet
  defines `bb_breakout_oi_confirmed_5m` replay acceptance rules, and a
  follow-up read-only feasibility probe found runtime-style OI-confirmed rows
  far below the Stage 0R sample floor (`n=9` pooled; every symbol `<100`) with
  negative rough gross 15m. It cannot be used as promotion evidence.
- ⏳ **A-group alpha-source invariant**: `declared_alpha_sources()` vs real
  logic re-check remains deferred until new alpha candidates land.
- 🟡 **W-AUDIT-4b corrected scope** remains active via §11.2 remaining
  retained tables/views/drop scope; `P1-WA4B-INSERT-1` is completed.
- Completed `[55]`, W-AUDIT-3b, F-08 cron, and `P0-MIT-LABEL-CLOSE-TAG-1`
  details are archived in `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`;
  residual edge risk is tracked by `P0-EDGE-1`.

---

## §6 Current W-AUDIT Priority Delta

Completed Sprint N+0 / N+1 D+0 execution ledgers and Post-MAG-084 Wave 1
planning are archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Priority verdict after PM/PA/FA cross-check:
1. **True-live remains blocked** by `P0-EDGE-1`, `P0-LG-1/2/3`, and
   `P0-OPS-1..4`; none of the 2026-05-15 runtime/doc fixes grant live authority.
2. **Stage 1 Demo micro-canary is blocked**, not active execution. There is no
   active paper cohort and no A4-C cohort candidate; launch requires a future
   strategy×symbol Stage 0R packet with `eligible_for_demo_canary=true` plus the
   runtime/lineage/operator gates in AMD-2026-05-15-01.
3. **Alpha path priority**: active effort is `W-AUDIT-8b` Funding Skew
   read-only Stage 0R query/report packet while `W-AUDIT-8a C1` is technical
   PASS / approve-conditional. BB corrected side mapping is signed; MIT
   W-AUDIT-8c source/test correction is done; V095 Linux PG dry-run x2 passed;
   MIT re-signed the idempotency gate, V095 is applied on Linux, and v46
   production writer revival is deployed. The business-chain root cause is still lack
   of non-textbook alpha.
4. **Runtime blocker update**: `[27]`, `[55]`, and `[67]` are closed and
   archived; this does not unblock Stage 1 Demo because no green alpha
   Stage 0R cohort exists.
5. **Maintenance**: P2 hygiene remains below alpha/LG/ops gates; W-AUDIT-5
   damaged dump cleanup and W-AUDIT-7 F-07/CEA env are ops-closed as of
   2026-05-15.

### §6.1 A4-C BTC→Alt Lead-Lag Tombstone（2026-05-16）

`W-AUDIT-8d` A4-C is not an active promotion task. Keep only this guard in
active docs:

- status: archived from promotion; diagnostic-only/no-revive for the BTC 1m
  return + xcorr feature shape
- keep: `panel.btc_lead_lag_panel`, `[57] btc_lead_lag_panel_health`, and
  historical rows for future Hypothesis Pipeline exploration
- do not keep: Stage 0R promotion candidate status, Stage 1 Demo cohort source
  status, paper-based promotion language, or threshold-only revive tasks
- future reopen: materially new predictive variable + preregistered validation
  + fresh strategy×symbol Stage 0R packet with `eligible_for_demo_canary=true`

Detailed Step 5b / RCA / PM+QC+MIT verdicts are archived in
`docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md`,
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`, and
`docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`.

---

## §7 W-AUDIT-6d Mid-Ground Summary

Detailed 保 6 / 砍 6 ledger and DSR K -12 derivation are archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Active rule that remains: the 6 polishing items are still rejected unless a
future QC/PM decision reopens them; do not add per-symbol/per-threshold sweeps
that inflate DSR trial count.

---

## §8 D-02 Layer 2 Manual 7d 試運行 SOP（Operator 自執行）

完整 6 step SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **Manual trigger 7d daily**（每天 1 次任意時間）：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. **4 metric 7d 觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**: alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**: alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**: `rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha contribution；如 7d < 1 USDT/week 不值人工 fixed cost，建議 abort。

---

## §9 Dormant D-XX Section（FA §5.2 必 explicit + reason）

| D-XX | Description | Status | Reason | Earliest reactivate |
|---|---|---|---|---|
| D-13 | Cognitive Modulator | DORMANT | 3-Tier `consecutive_loss/weekly_pnl` 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 跨 strategy meta-learning（ADR-0020 限制 manual）；Foundation Model 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset candidates | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only by design | **不解** |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §10 P0 — True-Live Blockers

| ID | Status | Task | Acceptance |
|---|---|---|---|
| `P0-PHASE-1B-PARAM-CALIBRATION-1` | ✅ **DONE 2026-05-18 13:50 UTC (deploy chain CLOSED)** | Option C path (simulation = evidence, no live pilot): PA spec v0.1/v0.2 → E1 harness IMPL (`93069c29`) + Rust constant change (`820f0532`) → E2 + E4 review chain → Merge (`8d8a0123` + `67f1a047`) → Sweep 81 cells (1.4 sec wall, top `G-AB-01-C90` fill 70.8% / +3.37 bps simulated) → operator rebuild + restart (engine PID 1506208 binary mtime 13:50 UTC). Grid family `timeout_ms 30s → 90s` deployed; phys_lock family timeout unchanged. **Acceptance result**: simulation `maker_fill_rate=70.8% ≥ 25%` AND `expected_fee_saving_bps=+3.37 ≥ 0.5` (top cell). **Outstanding**: 24h post-deploy AC-A SQL verify real fill rate vs 70.8% simulation prediction (E2 caveat: BBO-cross-proxy systematically optimistic) ~2026-05-19 13:50 UTC. Rollback trigger: real fill < 15% Wilson lower at n≥30 OR adverse_real > 5.55 bps baseline. PnL unlock projection $32-162/year × ~65% PASS prior. Phase 2a 14d observation clock reset from 13:50 UTC. |
| `P3-AGENT-SPINE-BENCH` | ⏳ scheduled N+3 | emit_entry_lineage / emit_fill_completion bench harness | E5 注：當前只有 tick_pipeline hot_path_baseline；補 1000×100 sample SLA monitoring |
| `P3-SPINE-COUNTER-CACHE-ALIGN` | ⏳ scheduled quiet period | 3 AtomicU64 counter `#[repr(align(64))]` cache line | E5 cosmetic; 10 min fix; ~50-200ns extra latency 降到 0 |
| `LG-1` H0 production caller | 🔵 Wave 2.2 dispatched 2026-05-11 | T1+T2+T3+T4 E1×4 parallel IMPL | per PA plan §1.4 |
| `LG-2` Provider pricing binding | 🔵 Wave 2.2 dispatched 2026-05-11 | T4 RiskConfig 先 → T1+T3 parallel → T2 startup assertion 序列 | per PA plan §2.4 |
| `LG-3` Supervised live SM | 🔵 Wave 2.1 PA spec phase dispatched 2026-05-11 | PA spec doc 1-1.5d → QC+BB+MIT parallel review → PA spec v2 → Wave 2.4 E1×7 IMPL | per PA plan §3.6 + §6.1 + §6.4 |
| `P0-EDGE-1` | ACTIVE | Edge net-positive decision | Strategy edge must be positive or scoped to limited supervised path before true-live. **Root cause linked to `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI）**。 |
| `P0-LG-1` | ACTIVE | H0 blocking production caller | H0 wired into production decision path with metrics + fail-closed. |
| `P0-LG-2` | ACTIVE | Provider pricing binding | Fee/pricing source bound, freshness checked, asserted at startup. |
| `P0-LG-3` | ACTIVE | Supervised-live state machine | Live authorization, lease, drawdown, revoke, operator approval explicit + tested. |
| `P0-OPS-1..4` | ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | Required before true-live. |

Completed §10 rows are archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

---

## §11 P1 — Next Engineering Queue

### §11.1 Sprint N+0 Active

Archived as completed in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`. Current
active work starts at §10 / §11.2 / §11.3.

### §11.2 W-AUDIT-4b corrected retained tables/views/drop scope（invariant 19）

| ID | Object | Corrected class | Owner | Notes |
|---|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT table / row-growth confirmed | E1 | Writer live at `cost_edge_advisor/mod.rs`; 2026-05-14 runtime row-growth confirmed: 6091 rows. Current demo `[cost_edge].enabled=false`, so rows are `Disabled` / `ratio=NULL`; ratio-present rows require a separate config decision. |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT table / readiness gated | E1 | Writer exists in `drift_detector.rs` and is spawned in `tasks.rs`; it depends on active `feature_baselines` and the configured ADWIN burn-in (default 30d). Do not remove burn-in without operator approval. |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | E1/MIT | Read-only projection, not an INSERT path. Keep contract under ML training-data healthchecks. |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | E1/MIT | Read-only projection, not an INSERT path. Full unbounded counts are expensive; use bounded/metadata probes. |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped / no-DDL target | E1/MIT | Dropped by V069; no producer wiring target unless a future spec recreates it. |

`P1-WA4B-INSERT-1` completion detail is archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

### §11.3 P1 — Other Active

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `P1-DATA-1..3-WATCH` | 3 | Runtime-reloaded WARN cluster row-rolloff watch | Source fixes are done; keep as observation-only watch, not an implementation blocker. |
| `P1-EDGE-1..2` | 3 | ma_crossover/grid blocked_symbols 已 frozen + funding_arb 14d audit 2026-05-16 | 維持 freeze + 2026-05-16 audit |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source active; audit-row health |
| `P1-EDGE-P2-3-PH1B-ML-INVARIANT` | 4 | E3 grep guard rule：`details->>'close_maker_*'` 禁餵任何 ML training pipeline（LinUCB / scorer / quantile / MLDE / DL3）| MIT-MF-1 non-training surface invariant；E3 PR pre-merge gate |
| `P1-BBMF3-WIRE-1` | 2 | ✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17 | Phase 1b source/test bundle wires close-maker reject/backoff/cooldown plumbing and integration regression. Runtime evidence: V094 Linux apply + engine-only rebuild/restart completed; close-maker audit fields can populate on subsequent fills. |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | spec §5.4 完整 dynamic backoff state machine IMPL（per-symbol 1s exp → 60s + ≥10 symbol cascade → 5min global pause + audit row `rate_limit_scope = "global"`）| Phase 1b initial IMPL（commit `27f02a07`）取 per-symbol 5min 固定（避 scope creep）；Phase 2a Demo PASS 後另開 PR；PA 估 ~50 LOC state machine + ~80 LOC integration test；對應 spec §5.4 v1.4 footnote + AMD v0.4 §11.2 |
| `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` | 1 | ✅ **DONE 2026-05-16**：`trade-core` online PG closure complete. V092 physical continuous aggregates created (6 views + 6 refresh policies); V091/V092/V093 `_sqlx_migrations` metadata inserted with source SHA-384 checksums; max_applied=93 / rows=90 / checksum drift_count=0. V081 remains legal dead slot. V094 deploy is no longer blocked by this backlog. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_3_5_linux_migration_backlog_closure.md`. |
| `P1-PORTFOLIO-RESTING-EXPOSURE-1` | 4 | ✅ **DONE 2026-05-16 commit `9980448a`**（Round 2 alpha push P1）：337 LOC source (intent_processor/mod.rs +118 / tests.rs +208 / paper_state/resting_orders.rs +11) + 7 unit test；Mac+Linux cargo test --release 2915/0/1 (= baseline 2908 + new 7)；hot_path bench p99=42μs << 300μs SLA；aarch64-apple-darwin PASS。A3 對抗審 APPROVE 9/10 (2 WARN advisory 不阻 commit)；E2 PASS to E4 (0 CRITICAL / 1 MEDIUM / 4 LOW)；E4 regression PASS。16-root + 9 invariant + 硬邊界全 GREEN；live/auth/lease 全未動；注釋全中文。Follow-ups → P2-PORTFOLIO-RESTING-{58-HEALTHCHECK / TEST-COVERAGE / ROUTER-CACHE / DOCSTRING-CLEANUP / E5-BENCH / REPLAY-PARALLEL}。 |
| `P2-PORTFOLIO-RESTING-58-HEALTHCHECK` | 4 | ✅ **DONE 2026-05-16 as `[68] portfolio_resting_exposure_lineage`**：原 spec/TODO 標 `[58]`，但 `[58]` 已被 W-AUDIT-9 T4 `check_58_graduated_canary_stage_invariant` 占用；實作取下一個 free slot `[68]`，保留 lineage name。`check_68_portfolio_resting_exposure` 已在 `runner.py` wire + `__init__.py` re-export；targeted pytest `helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py -q` = 10 passed。Residual LOW：engine-specific fallback cap / live+live_demo snapshot double-count future hardening，不阻 Stage 1 demo 啟動前監控目的。 |
| `P2-PORTFOLIO-RESTING-TEST-COVERAGE` | 4 | **P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up**：補 unit test 涵蓋「同 symbol 多筆 close-side resting 累積 > filled qty」場景（A3 WARN-2）。數學等價於現有 cap 邏輯但缺 test 釘 invariant；< 30 LOC，`intent_processor/tests.rs` 餘 207 LOC。 |
| `P2-PORTFOLIO-RESTING-ROUTER-CACHE` | 4 | **P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up**：`router.rs:438/445/446` 三 caller 連呼三個 helper 各跑一次 `compute_effective_long_short_notional`（4×HashMap + 1×HashSet local alloc 重複 3 次）→ caller 端 cache 一次 tuple 共用（E2 MEDIUM-1，pre-existing pattern non-regression）。 |
| `P2-PORTFOLIO-RESTING-DOCSTRING-CLEANUP` | 4 | **P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up**：清理 intent_processor/mod.rs 三處 docstring（RRC-1-B3 / FIX-05 / RG-2）的舊中英對照塊（per 2026-05-05 governance「修改既有中英對照塊時移除英文只保留中文」，E2 LOW-2）。涉歷史 issue 標籤 grep，由 E1 作者決定清理範圍。 |
| `P2-PORTFOLIO-RESTING-E5-BENCH` | 4 | **P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up**：E5 加 `benches/intent_processor_exposure.rs` micro-bench 覆蓋 `compute_effective_long_short_notional` per-symbol HashMap netting 階段（E4 P2 follow-up）。Production PostOnly maker-first 設計下 resting 可累積數十個，現有 hot_path_baseline 沒覆蓋這條 new path。 |
| `P2-PORTFOLIO-RESTING-REPLAY-PARALLEL` | 4 | **P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up**：`replay/risk_adapter.rs` parallel surface（ReplayPaperSnapshot.exposure_pct）目前 runner.rs 直寫，沒共用 `compute_effective_long_short_notional` helper。本 IMPL 故意不感染 replay；後續若 replay 也吃 resting-aware → 另案 P2 設計（E4 §7 + E1 self-report §6 P2 #2）。 |
| `P1-CRON-INSTALL-WAVE-1` | 2 | **2026-05-16 12-agent audit PM reprioritization #2 reconcile follow-up**：install 5 個 `helper_scripts/cron/` 未啟用 wrapper（panel_aggregator_health 5min / wave9_replay_no_live_mutation_watch 1h / replay_key_rotation_check daily / feature_baseline_writer daily / blocked_symbols_30d_unblock_check weekly）。reconcile evidence：MIT-P0-2「6/12 not installed」實際 8/11 not installed；P0-V3 F-08 5 ML cron 是 `ml_training_maintenance_cron.sh` wrapper 內部（已 installed `17 3 * * *`），兩 claim 不衝突。建議 schedule + 完整 reconcile：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--cron_reconcile_p0v3_mit_p02.md` | install 動作 = affect Linux trade-core shared infra，需 operator 確認；installs 完後加 healthcheck [68..72] 驗 fire；違反 `docs/agents/todo-maintenance.md` passive-wait 規則 |
| `P1-C1-PROBE-RECONNECT-SPEC` | 2 | ✅ **DONE 2026-05-16 commits `25396b0b` + `8d2eef58`**：v2 resilient harness IMPL `liquidation_topic_probe_v2.py` (942→1045 LOC) + 49/49 unit test + wrapper script `run_c1_v2_proof.sh`；5 reviewer 全綠（A3 7.5/10 APPROVE-COND + E2 PASS to merge + E4 Linux 49/49 + 60s smoke PASS + BB COND 0 Critical/High/Med + MIT FULL V09X 不需）+ E1 consolidated 6-fix + E2 re-review PASS + E4 quick recheck PASS。Operator 24h proof launch：`ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh'` (paste-safe <120 char)。Spec amendment via design plan `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md` 425 LOC。9 P2/P3 follow-up（checkpoint summary 拆檔 / blocker text edge case / tmp cleanup / etc.）見 E1 fix self-report §4。 |

Archived completed P1 rows: `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

### §11.5 EDGE-P2-3 Phase 1b — Final Dispatch Plan (2026-05-15 4-agent review 後拍板)

**Status**：Pre-IMPL prep details through Wave 3b are closed and archived. Full
close-maker-first Round 1（Design + Governance）closure narrative + 30+ commit timeline
+ 4-agent verdict + IMPL Prereq status + next-round scope → `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`.
Sibling TODO cleanup（broader v36 scope）→ `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
Phase 1b main source/test implementation is complete at `ea4ceca6`; V094 Linux apply and engine-only deploy/restart completed 2026-05-17. Phase 2a observation can collect subsequent fills; alpha/true-live gates below remain active.

**Still Active**
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge remains active.
2. ⛔ `W-AUDIT-8b Stage 0R` — **TOMBSTONED 2026-05-18 Round 2 RED_FINAL**：7.0d sweep 8/8 cells RED HIGH conf + 4-agent (BB/QC/FA/MIT) 4/4 APPROVE concur (`ffdbc2d0`). Spec v0.3 → v0.4 tombstone (`ef7ea6c2`) + AMD v0.6 → v0.7 (`71f2283b`) §8 condition 3 funding-related general + tombstone clause. No-revive on same feature shape. Redirect: W-AUDIT-8c Liquidation Cluster (Wave 1 已 merged) + W-AUDIT-8a Phase B/C/D per fix-plan v1.1 §9.4。
3. ✅ `W-AUDIT-8a C1` — **v2 24h proof TECHNICAL PASS / APPROVE-CONDITIONAL + writer revival DONE 2026-05-17**：session `c1_v2_20260516T145616Z` finished `2026-05-17T14:56:15Z`; artifact `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md` verdict `PASS_C1_PROOF_CANDIDATE`; BB approved corrected Bybit side semantics; W-AUDIT-8c/V095 source-test idempotency correction is done; V095 Linux PG dry-run x2 PASS + MIT re-sign APPROVE-CONDITIONAL + Linux apply/register DONE; production `allLiquidation.{symbol}` subscription/writer revival DONE in `0e8a8ae8`/`bedc40c3` with Linux runtime rows observed.
4. ✅ `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — **P0c DONE 2026-05-16**：V091/V092/V093 Linux PG backlog apply + sqlx record closed; V094 deploy no longer blocked by this ticket.
5. ✅ `P1-BBMF3-WIRE-1` — source/test included in `ea4ceca6`; V094 Linux apply + engine-only rebuild/restart completed 2026-05-17.
6. ✅ `W-AUDIT-8c` — source/test correction + V095 Linux PG dry-run x2 + MIT re-sign + Linux apply/register + production `allLiquidation.{symbol}` subscription/writer revival DONE 2026-05-17. Strategy launch/promotion remains a separate future gate.

**Phase 1b runtime deploy 已完成**（2026-05-17）：V094 apply + engine-only rebuild/restart complete；Phase 2a observation begins from subsequent fills. W-AUDIT-8b Stage 0R and `P0-EDGE-1` remain active alpha/true-live gates, not Phase 1b schema/deploy blockers.

**✅ 2026-05-18 RUNTIME ACTIVATOR BLOCKER — RESOLVED via deploy chain CLOSED**:
- Original symptom (preserved for governance audit): Post-deploy 4h `trading.fills` sample = **0% maker_attempt rate** (18 grid_close_short + 2 ma_reverse_cross whitelist closes all `close_maker_attempt=FALSE` + `fallback_reason=NULL`)
- E2 adversarial RCA `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_0_attempt_rca.md` identified: cold-default `use_maker_close=false` at `pipeline_ctor.rs:62` + ZERO production callers for `set_use_maker_close_runtime` + `commands.rs:117` early-returns `market()` skip path
- Resolution chain: PA design `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md` Option A TOML activator (`runtime.use_maker_close` field + H0Gate shadow_mode RMW pattern) → E1 second-dispatch IMPL `18081551` (~40 LOC `pipeline_ctor.rs` + `pipeline_config.rs` + `risk_config_demo.toml`, post-strip 245 LOC B-REM-1 leak, honest cargo test 2972/0/1) → E2 re-review APPROVE 0 new MUST-FIX (`a94825cb`) → E4 PASS 12/12 Mac+Linux release cross-arch (`af3b3010`) → QA APPROVE 0 BLOCKER (`a1b3ca908`) → merge `c737a1e4` → operator-代跑 restart_all.sh --rebuild UTC 2026-05-17 23:54 → engine PID 1066422 → 1143103 with new binary containing activator
- AMD-2026-05-15-02 v0.4 → v0.5 wording patch (`23e6b6b2`) lands Runtime Activation Layer + three-env TOML table
- `risk_config_demo.toml [runtime] use_maker_close=true` confirmed via grep + engine boot log shows `risk_demo_version=2` loaded

**Runtime kickoff status**：
- V094 Linux migration/deploy authorization → deploy-chain regression → post-deploy healthchecks → PM sign-off: ✅ DONE 2026-05-17.
- Phase 1b runtime activation: ✅ **DEPLOY DONE 2026-05-17 23:54 UTC** (engine PID 1143103).
- AC-A verification T+10.6h (2026-05-18 10:29 UTC): **PARTIAL PASS / EXTEND_MONITORING** — demo-only post-restart 3/3 = 100% attempt_pct (Wilson CI lower 43.85% > 25% PRELIMINARY PASS, n=3 insufficient); 24h combined 9.38% (pre-restart cold-default 拖低 + live_demo TOML disabled 稀釋). E2 RCA verdict `9a6787ce`: 4/4 fallback `timeout_taker` = STRUCTURAL DESIGN (NOT bug), n=4 small-n statistical noise at lower-bound of spec §1.2 predicted 15-25% range + entry-side baseline 14.7% PostOnly fill rate 證實 demo low-liquidity floor.
- **Calibration sweep + Rust timeout deploy** ✅ **DONE 2026-05-18 13:50 UTC** (engine PID 1253085 → 1506208): grid family `timeout_ms 30_000 → 90_000` post-sweep top cell `G-AB-01-C90` (fill 70.8% / +3.37 bps simulated, sweep wall 1.4 sec). Spec v0.2 land (`34af2d2e`) per PA decision memo `5df39d13` denom drift fix. **Phase 2a 14d observation clock reset @ 13:50 UTC NEW t=0**; 24h post-deploy AC-A SQL verification target ~2026-05-19 13:50 UTC (real fill vs simulation 70.8% prediction, E2 caveat BBO-cross-proxy systematically optimistic).
- Cross-wave consistency check pending (QA recommendation #3 — restart triggered W6/W7/W1 main-landed-but-not-deployed sources too; calibration restart 同樣 trigger).
- Outstanding anomaly investigations (low-priority, parallel SD agent dispatched 2026-05-18 14:00 UTC): SD-1 A axis (offset_bps) dead-variable hypothesis / SD-2 PS family (phys_lock_gate4_stale_roc_neg) 100% n_skip / 0 fill — investigation report `2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md` pending.
- Next: 24h AC-A real verdict → if PASS Phase 2a 14d observation continue / if FAIL revert timeout 90s→30s OR PA tune-further; Phase 2b LiveDemo / operator + AMD live carve-out / Phase 3 Mainnet remain future gates.

---

### §11.4 P0-MICRO-PROFIT — 微利根因治本路徑（2026-05-11 QC audit 拍板）

**Background**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0 (-17.82 bps demo)，**任何 sizing 槓桿 L>1 必放大虧損**（數學常數）。先修 alpha，再談 size。

**5 root cause + 占比**：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

**治本路徑 = PA R-1/R-2/R-3 redesign（已映射 W-AUDIT-8a..8f wave 矩陣）**：

| ID | Task | Spec source | ETA |
|---|---|---|---|
| `W-AUDIT-8a` Phase B/C/D | Tier 2 panel collector + Tier 3 microstructure + Tier 4 information flow | Sprint N+1 W2 起逐步 IMPL | 4-6 sprint |
| `W-AUDIT-8b` (A4-A) | Funding Skew Directional 新策略（R-1 IMPL）| W-AUDIT-8a Phase B 後 | Spec v0.3 sweep tooling source/test done `a6e17d5d`；Round 2 replay waits panel ≥7d |
| `W-AUDIT-8c` (A4-B) | Liquidation Cluster Reaction 新策略 | C1 transport PASS + correction source/test + V095 dry-run/MIT re-sign + Linux apply + writer revival done | Strategy launch waits separate Stage 0R/design gate |
| `W-AUDIT-8d` (A4-C tombstone) | BTC→Alt Lead-Lag diagnostic panel | Archived guard only | ⛔ Not an active alpha path; diagnostic-only/no-revive for BTC 1m return + xcorr |
| `W-AUDIT-8e` (R-2) | Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d land 後 | N+3-N+4 |
| `W-AUDIT-8f` (R-3) | Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 個月）** — 真實 gross 轉正最早窗口。

**2026-05-15 PM prework / RCA final update**:
- `W-AUDIT-8a C1` proof packet exists: `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` + `helper_scripts/bybit/liquidation_topic_probe.py`。The prior PID `4100789` run started at `2026-05-15T19:53:09Z` and ended `FAIL_CONNECTION`; the v2 proof session `c1_v2_20260516T145616Z` completed 2026-05-17 with `PASS_C1_PROOF_CANDIDATE`; BB approved corrected side semantics; W-AUDIT-8c/V095 source-test correction, Linux PG dry-run x2, MIT re-sign, V095 Linux apply, and production `allLiquidation.{symbol}` writer revival are done.
- `W-AUDIT-8b` Funding Skew spec exists: `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`。It is a cross-sectional crowding signal, not retired `funding_arb`; v0.3 4-cell sweep tooling is source/test done at commit `a6e17d5d`; next gate is panel ≥7d Round 2 packet + QC/MIT/BB verdict.
- `W-AUDIT-8d` A4-C has only a tombstone in active docs: archive/no-revive for the BTC 1m return + xcorr shape, keep `panel.btc_lead_lag_panel` diagnostic-only, and do not select it for Stage 1 Demo.

**Operator 5 zero/small cost actionable（2026-05-11 拍板）**：
1. ✅ **DONE**：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ **PASSIVE wait**：等 7d 重測 §三 [40]（24h MLDE +8.75bps 是 transitory 還是穩態）— 2026-05-17 自動收口
3. ⏳ **INFO gathering**：查 Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ **PASSIVE wait**：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze decision（2026-06-09 收口）
5. ✅ **DEFER 記錄**：D/E sizing 槓桿（volatility scaling / edge-weighted）等 ML calibration N≥200 — 寫入 backlog 防過早 commit

**11 sizing 槓桿全 REJECT in current EV<0 state**（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

**Operator 守則**：
- 不要看見 memory「3%」就直接套到 TOML（必先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`（待 QC commit）

---

## §11.6 12-Agent Full System Audit WPs (2026-05-16)

**Source**: `srv/2026-05-16--full-system-audit-fix-plan.md` (PA consolidated + PM sign-off)
**PM Sign-off**: APPROVED-CONDITIONAL 2026-05-16
**Status**: Wave 1-4 source/test work is closed and archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

**Retained follow-ups**:
- WP-11 Phase 2 residuals are tracked in §12 P2 backlog.
- WP-12 ONNX remains deferred; rule-based fallback is current behavior.
- PA audit drift hardening is tracked by `P2-PA-CALLPATH-GREP-RULE`.
- LOC follow-ups from Wave 1 are tracked by `P2-COMMON-JS-LOC` and
  `P2-TAB-LIVE-LOC`.

---

## §12 P2 — Maintenance Backlog

| ID | Task | Trigger |
|---|---|---|
| `P2-LEASE-1` | Clean terminal `DecisionLeaseSm.objects` Vec entries | If long soak shows memory growth or before high-volume live |
| `P2-STRUCT-2` | Zombie/deprecated code inventory | Next architecture hygiene sweep |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset (D-16 dormant，§9) | ADR-0015 + AMD-2026-05-09-02 accept; Sprint N+6+ |
| `P2-DEAD-SCHEMA-DROP-1` | **WP-07 NEW**：`rl_transitions` + `symbol_clusters` 2 dead tables DROP（V004 remnant，0 rows，0 writers/readers）| est. V### migration + E2+MIT review |
| `P2-DEAD-RUST-CLEANUP-1` | **WP-07 NEW**：openclaw_core 7 dead modules 3186 LOC 退役（attention/attribution/cognitive/dream/message_bus/order_match/opportunity）| est. 1 session；依 ADR-0015 路徑 |
| `P2-PERCEPTION-DEPRECATE-1` | **WP-07 NEW**：`PerceptionPlane::validate_for_decision` 0 production callers → `#[deprecated]` + 14 test callers migrate | est. 0.5 session |
| `P2-H0-DISPLAY-LABEL-1` | ✅ **DONE 2026-05-16**：Python H0Gate GUI endpoint 回傳 `display_only=true`，明確標示此 FastAPI/GUI surface 僅展示 H0 狀態，不是 Rust H0 execution authority；targeted pytest `TestGetH0GateStatusFreshnessFields` = 3 passed。 |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix → **mounted into `W-AUDIT-8f` (R-3) Hypothesis Pipeline per Decision-3 (P0-DECISION-AUDIT-7)** | Sprint N+5 |
| `P2-ORDERS-INTENT-ID-WRITER-GAP-1` | **Wave 1.5 NEW**（per Track E3 maker fill baseline 2026-05-15 commit `b98706d5`）：fix `orders.intent_id` 100% NULL writer 漏接；恢復 intent → order linkage 給 Guardian-pass-rate 計算 | est. 1 person-day；不阻 Phase 1b IMPL；E3 finding 1 證實 7d 1394 demo orders / 1021 live_demo orders 全部 `intent_id IS NULL`；無法走 `intents → orders` join 算 Guardian-pass-rate；派發時點：N+2 backlog |
| `P2-WP05-FUP-1` | **Wave 1 Round 2 follow-up**：32 處 `str(exc)` 殘留（22 處 E1 自承非 SoT 列名 + 9 處 risk_routes.py `_ipc_failure(f"...: {e}")` E2 新發現 + 1 處 strategist_promote_routes:564 enum 字串）— 走全域 handler regex 二次消毒，但仍建議逐處 migrate 為穩定 reason_code | est. 0.5 session；非 blocking；handler regex 為 second-line defense |
| `P2-COMMON-JS-LOC` | **Wave 1 Round 2 NEW**：`common.js` 2198 LOC 超 §九 2000 hard cap（pre-existing 2135 + Wave 1 +63 SDK consolidation）— 拆檔（建議 modal SDK / API helper / formatter 三檔）| est. 1 session；PM 已 accept governance exception |
| `P2-TAB-LIVE-LOC` | **Wave 1 NEW**：`tab-live.html` 2142 LOC 超 §九 2000 hard cap（Wave 1 Round 2 已從 2190 拆 -50 LOC）— 進一步拆 form / modal partials | est. 1 session；low priority |
| `P2-CROSSTAB-I18N` | ✅ **DONE 2026-05-16**：tab-system / tab-paper / console / tab-settings / governance-tab.js / tab-risk / app.js / risk-tab.js 進行 static UI 繁體化 cleanup；指定殘留 `实盘/平仓/请检查` grep=0；JS syntax `node --check app.js risk-tab.js governance-tab.js` passed。 |
| `P2-STOCHASTIC-LEAK` | **Wave 1 Round 2 NEW (QC)**：`momentum.rs:80-86` Stochastic 含 current bar（`high[start..=i]` 含 i=n-1）同類 look-ahead leak — 加 `stochastic_prior()` 變體 + 5 textbook indicator 完整 leak audit | est. 0.5 session；low priority（bb_breakout 不直接用 Stochastic，但其他 indicator 應掃完）|
| `P2-START-LOCAL-HELPER` | ✅ **DONE 2026-05-16**：`start_local.sh` + `beta_quickstart.sh` source `helper_scripts/lib/api_bind_host.sh` 並使用 `resolve_openclaw_api_bind_host()`；safe default 保持 auto→Tailscale IPv4/loopback，`OPENCLAW_BIND_HOST` 可 override，`0.0.0.0` / `::` 仍 fail-closed；static pytest + `bash -n` passed。 |
| `P2-PA-CALLPATH-GREP-RULE` | ✅ **DONE 2026-05-16**：repo 內無 literal `code-quality-audit` skill，落地到實際審核入口 `.claude/skills/pr-adversarial-review/SKILL.md` §3.10，並同步 `.claude/agents/PA.md`；P0/P1 leak / look-ahead / selection-bias / stale finding 必附 IndicatorEngine / production caller call-path grep，未附 grep 不得作 P0/P1 blocker。 |
| `P2-WP05-CSP-UNSAFE-INLINE` | **Wave 1 Round 2 NEW (E3)**：CSP `unsafe-inline` 推遲在 live 前 30 天窗口不安全（25 處 innerHTML + unpkg CDN 無 SRI）— 至少加 SRI integrity hash；live cohort 前必補 nonce-based CSP | est. 1 session；live-gate prerequisite |

Completed Sprint N+2 P2 rows (`P2-N2-1..4`) are archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

---

## §13 Push Back / Risk 治理記錄（不可漏失，FA §5.6）

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升級為 6 並行（5 active + 1 stand-by）
- **記錄**：v19 §0 Sprint Banner / §5.4 invariant 22 / §6 Day 0-3 dispatch

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻（合規/安全/可觀測 baseline），**不能被 Track A lobby 取代**
2. D-02 SOP 預期上限 +2-5 USDT/week；若 7d < 1 USDT/week 不值人工 fixed cost，建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12），不是省工時妥協

### 4-agent loss audit cross-fact-check（已撤銷的 stale belief）
- **QC v2-NEW-4 Donchian「runtime contaminated」過期 contaminated belief**：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff` (2026-04-28) 起 leak-free 11 天；`ad14db07` 僅補 regression test。後續 audit / push back 不可再引此 finding 為 active runtime issue。

---

## §14 Schedule

| Date | Work | Gate |
|---|---|---|
| 2026-05-10..16 | Sprint N+0 W1-W2 FOUNDATION HEAVY | Closed; detailed ledger archived in `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md` |
| 2026-05-16 | funding_arb 14d audit | verification/history; retirement decision in AMD-2026-05-09-02 / ADR-0018 |
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | 8a C1 transport proof passed; W-AUDIT-8c/V095 source-test correction + Linux PG dry-run/MIT re-sign + Linux apply done but production revival waits separate AMD/source/config dispatch; 8b read-only Stage 0R query/report packet; Stage 1 Demo only after a future green Stage 0R (`[55]` source-cleared) |
| 2026-05-24..30 | Sprint N+2 8a Phase D + Stage 2 demo cohort 14d | Stage 2 only from Stage 1 Demo empirical evidence |
| 2026-05-31..06-06 | Sprint N+3 8c (Liquidation) IMPL + 8e (R-2) spec + Stage 3 demo full | |
| 2026-06-07..13 | Sprint N+4 8f (R-3) spec + 8b (Funding Skew) IMPL + 8e IMPL + Track W 收尾 | Track W 全 closed |
| 2026-06-14..20 | Sprint N+5 8f IMPL + 8g (R-4) spec + first per-alpha-source supervised live | 業務鏈 85-89% |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+） | conditional on W-AUDIT-1..7 + 5 P0-LG/OPS + W-A/B/C/D PASS |
| 2026-06-30 | Supervised live 中位帶（業務鏈 80%+） | ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（業務鏈 85%+） | ~25% probability per FA |

---

## §15 Dispatch Rules + Handoff Checks

### Dispatch Rules
- PM-first triage for every wave
- Implementation work: `PM → PA → E1/E1a → E2 → E4 → QA → PM`，roles 跳過需 explicit justify
- Security/deploy/runtime work: `PM → E3 → BB if exchange-facing → PM`
- Quant/data decisions: `PM → QC → MIT → AI-E if model economics matter → PM`
- Commit each green checkpoint with subject and body, push to origin, then sync Linux by fast-forward
- **Commit message 加 `[skip ci]`** 對非 CI-relevant 變更（doc / governance / TODO update / report land），保 CI usage 額度
- Do not rebuild, restart, mutate live auth, change scanner evidence contract, unlock executor shadow, enable lease-router, or add OpenClaw write/proposal routes unless operator explicitly authorizes
- W-AUDIT-6d 砍 6 子項：E2 必 grep blacklist；命中即 reject merge

### Handoff Checks

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §16 References

### 4-Agent Loss Audit (2026-05-09)
- **PA dispatch plan**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md` (commit `d3bf7be2`, 689 lines)
- **PA architectural redesign**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **PA merge analysis**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- **FA business chain validation**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md` (commit `5a2dee98`)
- **FA dormant alpha inventory**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- **FA merge advice**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- **4-agent loss audit worklog**: `srv/docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- **QCTODO archived**: `srv/docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment
- **W-AUDIT-8a spec**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` (commit `c13c811e`)
- **AMD-2026-05-09-02** (5 P0-DECISION-AUDIT closure): `srv/docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- **AMD-2026-05-09-03** (Graduated Canary Default): `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` (commit `b1891023`)
- **AMD-2026-05-15-01** (Canary Rebase Replay Preflight + Demo Micro-Canary): `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- **AMD-2026-05-15-02 v0.4** (EDGE-P2-3 Phase 1b Close-Maker-First): `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **EDGE-P2-3 Phase 1b spec v1.3**: `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- **V094 hybrid schema migration spec**: `srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- **Round 1 Closure Archive**: `srv/docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`（完整 round 1 closure + 30+ commit timeline + IMPL prereq status + next-round scope）
- **W-AUDIT-8b Funding Skew Directional spec v0.2**: `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only / **ADR-0022** strategist cap

### Close-Maker-First 3-agent Verdicts (2026-05-15 round 1 — Spec)
- **PM verdict**: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md` (APPROVED-CONDITIONAL，scope-in Sprint N+2 P1)
- **PA verdict + spec outline**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` (READY-FOR-SPEC，0 BLOCKED-BY-1B-4.2，~985 LOC)
- **FA verdict + AC**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md` (APPROVED-CONDITIONAL，5 conditions + 5 missing keep-market reasons)

### Close-Maker-First 4-agent AMD Adversarial Review (2026-05-15 round 2 — AMD)
- **QC verdict**: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md` (APPROVED-CONDITIONAL，4 must + 5 should + 3 NTH；framing / multiple testing / phys_lock timeout / AC-5 sample-size)
- **FA round 2 verdict**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md` (APPROVED-CONDITIONAL，4 must + 5 should + 4 recommended；framing / IMPL prereq 5 / W-C Caveat 2 / V### backward-compat)
- **BB verdict**: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md` (APPROVED-CONDITIONAL，5 must + 3 should + 4 補錄；PostOnly+reduceOnly dict / dynamic backoff / reject_cooldown split P0 / classifier reuse / reject sample HC)
- **MIT verdict**: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md` (APPROVED-CONDITIONAL，6 must + 4 should + 1 may；hybrid schema / Wilson-CI gating / NULL ladder / non-training invariant；V094 recommended)
- **Consolidated 4-agent summary**: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md` (4 consensus + 13 unique must-fix + 14 should-fix；AMD v0.2 + spec v1.1 patch plan)

### Adversarial Verification
- **v3 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_v3_summary.md`
- **v2 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_v2_summary.md`
- **v1 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_summary.md`
- **PA Fix Plan v2 (DUAL-TRACK)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **2026-05-08 12-Agent Full Audit + PA Fix Plan**: `srv/2026-05-08--full_audit_fix_plan.md`
- **Verified-closed archives**: `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_{,v2,v3}.md`

### Bybit / API
- **Bybit API 字典/審計**: `docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- **Operator G3-08 enable evidence**: commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`
