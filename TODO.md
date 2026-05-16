# 玄衡 TODO — Active Dispatch Queue

Version: v36
Date: 2026-05-16
Status: v36 completion cleanup. Completed v35 / 2026-05-15..16 detail has been cross-checked against commits and PM/E2/E4/BB reports, then moved to `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`. Active TODO now keeps blockers, dependent gates, deferred work, and runnable backlog only. Runtime/code-bearing v35 head `5f6f3edf` was synced across Mac/origin/Linux before rebuild; post-rebuild docs-only sync may advance repository HEAD without another rebuild. `trade-core` rebuilt/restarted via `restart_all.sh --rebuild --keep-auth` on 2026-05-16. Runtime after rebuild: engine PID `69581`, API PID `69674`, watchdog `engine_alive=true`, demo fresh, live inactive due signed auth absence, and paper pipeline disabled by `OPENCLAW_ENABLE_PAPER=0` (`paper_state.disabled=true`; fresh paper marker is disabled-state write, not active Paper trading). W-AUDIT-8a C1 is blocked again because the isolated `allLiquidation.BTCUSDT` proof ended `FAIL_CONNECTION` at `2026-05-16T00:37:25Z` after `17055.2s/86400s`; it is not proof-eligible. True-live remains blocked by `P0-EDGE-1`, `P0-LG-1/2/3`, and `P0-OPS-1..4`.

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

## §0.0 PM Freeze — 2026-05-15 Canary Rebase Guard

**Status**: ACTIVE PM freeze; AMD-2026-05-15-01 now carries the rebase authority.

- `W3 Stage 1 paper cohort` → **FROZEN**. Paper is permanently disabled for promotion evidence; `Environment::Paper × 7d` cannot be used as Stage 1 PASS evidence.
- `A4-C D+12 paper edge report` promotion path → **FROZEN**. A4-C promotion must be rebased to replay preflight + demo Stage 1 gate; legacy paper-edge report remains diagnostic/read-only only.
- Any plan, command, env file, script, or runtime launch that sets `OPENCLAW_ENABLE_PAPER=1` → **BLOCKED** unless a future operator decision explicitly reopens paper for non-promotion diagnostics.
- AMD-2026-05-15-01 revises W-AUDIT-9 / AMD-2026-05-09-03 to Stage 0R replay preflight + Stage 1 demo micro-canary.
- Completed 2026-05-15 Stage 0R / OI packet / `[55]` detail is archived in `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`; active fact remains: A4-C and OI-confirmed 5m are both non-promotional.
- Completed 2026-05-15 `[27]` / `[67]` infrastructure-closure details are archived in `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`; active fact remains: `[27]`, `[55]`, and `[67]` are closed, while Stage 1 demo is still blocked by alpha evidence.
- Completed alpha-path / Phase C0 / W-AUDIT-8b design / v35 deploy details are archived in `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
- Current active alpha gates: A4-C remains diagnostic-only/no-revive; W-AUDIT-8b waits for a read-only Stage 0R query/report packet; W-AUDIT-8a C1 waits for a new full-duration BB/MIT-approved proof after the 2026-05-16 `FAIL_CONNECTION`.

---

## §0 Sprint Milestone Banner（FA 業務鏈視角，63% → 85-89%）

| Sprint | Week | 主題 | E1 capacity | Business chain milestone |
|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY: W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | **5 active + 1 stand-by** (operator (a)) | 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING: 8a Phase B+C 並行 + 8d (BTC→Alt) + Stage 0R replay preflight + **Stage 1 demo micro-canary** prep | 4/6 | 65→70% must be recalculated after demo canary evidence |
| **N+2** | W5-W6 | 8d follow-up + 8a Phase D + Stage 2 demo cohort 14d（only after Stage 1 demo evidence） | **5 active + 1 stand-by** | 70→76% rebase pending |
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
- A4-C BTC→Alt Lead-Lag Stage 0R remains **GATE-RED** after Step 5b (`eligible_for_demo_canary=false`). The OI-confirmed 5m packet is only a replay spec and does not change eligibility.
- `[55]` is source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; `[67]` is restored to PASS after feature baseline apply; `[4]` phys lock and `[Xb]` triangulation are PASS after `7108035d`.
- V079 / `learning.strategy_trial_ledger` is runtime-applied on `trade-core` (migrations through V090 applied; 16,212 ledger rows observed). Old "V079 not applied / engine still 5/8 binary" text is archived in `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`.
- Remaining business root cause: 5 textbook strategies still lack durable positive net edge. `P0-EDGE-1`, `P0-LG-1/2/3`, `P0-OPS-1..4`, Alpha Surface Phase C/D, and alternative alpha candidates are the current path.
- **EDGE-P2-3 Phase 1b close-maker-first refactor**: spec / AMD / 4-agent review / Wave 1..3b prep details are archived. Current blockers are the same 3 gates (`P0-EDGE-1`, `W-AUDIT-8b Stage 0R`, `W-AUDIT-8a C1`), Wave 3.5 Linux migration backlog, and `P1-BBMF3-WIRE-1` production callback wiring. phys_lock live enablement remains deferred to Phase 2b.

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
| 4 | `W-AUDIT-8a` Alpha Surface Foundation | alpha-bearing | PA → E1 → E2 → E4 + MIT/QC/CC/BB → PM | 🟡 **PARTIAL / C1 BLOCKED** | Phase A/B/C0 complete; C1 proof failed `FAIL_CONNECTION` on 2026-05-16 and is not proof-eligible. Production liquidation revival remains blocked until a new full-duration BB/MIT-approved proof passes. |
| 5 | `W-AUDIT-8b` A4-A Funding Skew Directional | alpha-bearing | PA spec → Stage 0R query/report + QC + MIT + BB review | 🔵 **READ-ONLY STAGE 0R PACKET NEXT** | Spec v0.2 review/design done; strategy IMPL and demo spend remain blocked until replay packet is green. |
| 6 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction | alpha-bearing | PA spec → E1 + QC + BB review WS | ⏳ **DEFER** Sprint N+2 spec → N+3 IMPL | Gated on C1 proof + MIT schema review. |
| 7 | `W-AUDIT-8e` (R-2) Strategist Alpha Source Orchestrator | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+4 spec → N+5 IMPL | AlphaSourceRegistry + dynamic Sharpe-by-regime + Hypothesis sourcing. |
| 8 | `W-AUDIT-8f` (R-3) Hypothesis Pipeline + W-AUDIT-4 ML | alpha-bearing | PA spec → E1 IMPL + MIT spec | ⛔ **DEFER** Sprint N+5 IMPL | learning.hypotheses state machine + W-AUDIT-4 dead schema root-cause closure. |
| 9 | `W-AUDIT-8g` (R-4) Per-alpha-source Live Promotion Gate | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+7+ | LiveBudget(alpha_source_id, slice) replacement for system-wide live_reserved model. |
| 10 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | alpha-neutral | E1a + A3 review | ⛔ **DEFER** Sprint N+4-N+6 | A3 tab expansion follow-up. |
| 11 | `W-AUDIT-10` (R-5) Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec → E1 IMPL | ⛔ **DEFER** 中期 | CI gate spec drift > 7d auto-fail + module/table lifecycle header. |
| 12 | `EDGE-P2-3 Phase 1b` Close-Maker-First Refactor | alpha-impact-adjacent execution-quality | PA → E1 → E2 → E4 → QA → PM | 🔵 **PRE-IMPL GATED** | Spec/AMD/reviews/prep are mostly closed and archived; active blockers are §11.5 3-gate, Wave 3.5 migration backlog, and `P1-BBMF3-WIRE-1`. |

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
| 4 | A 群 3 新策略（8b/8c/8d）↔ W-AUDIT-9 Stage 1 cohort 選擇 | governance/canary | **FROZEN 2026-05-15**: A4-C 不再用 Stage 1 paper cohort 入場；改走 Stage 0R replay preflight + demo Stage 1 gate（AMD-2026-05-15-01）。 |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | docs/execution_plan | **TODO IDs 為 SoT 2026-05-15**: `8b`=A4-A Funding Skew，`8c`=A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現 tracked as `8e/8f`），不得拿來當策略 spec。 |

---

## §5 Active Sign-off Delta

Full Sprint N+0 22-invariant ledger is closed and archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Current sign-off deltas only:
- ❌ **Stage 0R GATE-RED 2026-05-15**: A4-C Step 5b returned
  `eligible_for_demo_canary=false` after diagnostic producer restoration; no
  Stage 1 demo cohort selected.
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
2. **Stage 1 demo micro-canary is blocked**, not active execution. A4-C is
   GATE-RED, and the OI-confirmed 5m packet is underpowered/negative until a
   future full Stage 0R replay returns green.
3. **Alpha path priority**: A4-C is archived from promotion and remains
   diagnostic-only. `P1-A4C-RCA-1` is closed as no revive hypothesis found
   after QC/MIT review, so `P1-A4C-REV-1` is not opened and no A4-C Stage 0R
   rerun is authorized for the same feature shape. Shift active effort to
   `W-AUDIT-8b` Funding Skew read-only Stage 0R query/report packet while
   `W-AUDIT-8a C1` waits for a new full-duration proof after the 2026-05-16
   `FAIL_CONNECTION`. `W-AUDIT-8c` Liquidation Cluster remains gated until C1
   and MIT schema review pass. The business-chain root cause is still lack of
   non-textbook alpha.
4. **Runtime blocker update**: `[27]`, `[55]`, and `[67]` are closed and
   archived; this does not unblock Stage 1 demo because A4-C remains GATE-RED.
5. **Maintenance**: P2 hygiene remains below alpha/LG/ops gates; W-AUDIT-5
   damaged dump cleanup and W-AUDIT-7 F-07/CEA env are ops-closed as of
   2026-05-15.

### §6.1 A4-C BTC→Alt Lead-Lag PM/PA/FA Engineering Card（2026-05-15）

FA verdict: A4-C does **not** currently justify spending 7d Demo
micro-canary budget. Producer silence was fixed, but Step 5b still failed
edge/statistical gates: `avg_net_bps=+0.3552`, `t=0.2231`,
`PSR(0)=0.5877`, `DSR=0.0000`, CI lower tail < 0, and
R²(60/120/300)=`0.0009/0.0005/0.0027`.

| ID | Status | Owner Chain | Task | Acceptance / Stop Rule |
|---|---|---|---|---|
| `P0-A4C-FA-GATE-1` | ⛔ ARCHIVE FROM PROMOTION | PM → QC/MIT → FA → PA → PM | Keep A4-C out of active promotion budget | A4-C remains diagnostic-only unless a future, preregistered strategy×symbol Stage 0R packet emits `eligible_for_demo_canary=true`. Pooled-only evidence is insufficient. |
| `P0-A4C-DEMO-BUDGET-GATE` | BLOCKED | PM → QC → MIT → FA → PA → PM | Demo micro-canary spend gate | Demo budget requires one concrete `strategy × symbol` with `n>=100`, `avg_net_bps>=+15`, `t>2.0`, `PSR>=0.95`, `DSR>=0.95` with explicit K, bootstrap lower bound > 0, PBO <= 0.20, no leak/cherry-pick, and operator-approved cohort. |
| `P1-A4C-REV-1` | ❌ NOT OPENED | PA → QC → MIT → FA → PM | Bounded preregistered revise-or-archive decision | QC/MIT found no new preregistered hypothesis. Threshold loosening, post-hoc symbol picking, or rerunning the same BTC-return/xcorr feature shape are non-triggers. |
| `P1-A4C-RERUN-1` | ⛔ BLOCKED | PM → QC → MIT → PM | Stage 0R replay rerun | No rerun for A4-C unless a materially new predictive variable is preregistered in the future. Output may only be `eligible_for_demo_canary=true/false`; paper promotion remains blocked by AMD-2026-05-15-01. |
| `P0-ALPHA-SWITCH-8B-8C` | 🔵 ACTIVE | PM → QC/MIT/BB → PA → FA → PM | Switch alpha focus after A4-C RCA closure | `W-AUDIT-8b` proceeds only to a read-only Stage 0R query/report packet; `W-AUDIT-8a C1` waits for a new full-duration proof after `FAIL_CONNECTION`; `W-AUDIT-8c` waits for C1 proof + MIT schema sign-off. |

`P1-A4C-RCA-1` closure details are archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

Hard boundaries: no `OPENCLAW_ENABLE_PAPER=1` promotion use, no Stage 1 demo
launch from RCA, no live/LiveDemo relaxation, no auth/risk/lease/runtime
mutation, and no gate relaxation to make A4-C pass.

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
| `P1-BBMF3-WIRE-1` | 2 | Wire production maker rejection callbacks into close cooldown plumbing | E2/BB found `arm_close_cooldown` helper + 8 tests landed, but production caller is still Phase 1b main-scope. Wire WS/order rejectReason classifier → strategy callback → close cooldown write/read; add integration regression. |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | spec §5.4 完整 dynamic backoff state machine IMPL（per-symbol 1s exp → 60s + ≥10 symbol cascade → 5min global pause + audit row `rate_limit_scope = "global"`）| Phase 1b initial IMPL（commit `27f02a07`）取 per-symbol 5min 固定（避 scope creep）；Phase 2a Demo PASS 後另開 PR；PA 估 ~50 LOC state machine + ~80 LOC integration test；對應 spec §5.4 v1.4 footnote + AMD v0.4 §11.2 |
| `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` | 1 | Wave 3.5 V091/V092/V093 Linux PG backlog apply + sqlx checksum repair（V094 deploy 前必跑）| PA verdict `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md` NEEDS-ACTION；V092 真 IMPL（matview 0 row）+ V091/V093 metadata 補登（schema partial applied）；V081 = dead slot；est. 2h；V094 IMPL kickoff NOT BLOCKED，但 deploy 階段 BLOCKED 直到本 ticket done |
| `P1-PORTFOLIO-RESTING-EXPOSURE-1` | 4 | **Wave 1.5 NEW**（per Track A3 portfolio_var verify finding 2026-05-15 commit `96995b61`）：fix `compute_correlated_exposure_pct` / `compute_exposure_pct` 在 `intent_processor/mod.rs:761-805` 把 `paper_state.resting_orders.qty` 加進 effective exposure 計算 | est. 3 person-day, 250 LOC；獨立平行 Phase 1b IMPL，互不阻塞；解 entry-side resting maker 既有 systemic gap；對 close-maker-first 是「nice-to-have but not blocker」；scope 詳見 spec §15 + A3 verify report §8；派發時點：Wave 4+ |

Archived completed P1 rows: `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

### §11.5 EDGE-P2-3 Phase 1b — Final Dispatch Plan (2026-05-15 4-agent review 後拍板)

**Status**：Pre-IMPL prep details through Wave 3b are closed and archived in
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`. Phase 1b
main implementation remains blocked by gates below.

**Still Active**
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge remains active.
2. ❌ `W-AUDIT-8b Stage 0R` — read-only Stage 0R query/report packet still pending.
3. ❌ `W-AUDIT-8a C1` — prior 24h proof ended `FAIL_CONNECTION`; needs a new full-duration BB/MIT-approved proof.
4. 🔵 `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — V091/V092/V093 Linux PG backlog apply / sqlx checksum repair before V094 deploy.
5. 🔵 `P1-BBMF3-WIRE-1` — production rejectReason/callback wiring must be included in Phase 1b main implementation.

**IMPL kickoff（only after gates clear）**：
- PA finalize IMPL plan → E1 parallel worktrees → E2 review → E4 regression → QA → PM sign-off.
- Phase 2a Demo 14d → Phase 2b LiveDemo 7d → operator + AMD live carve-out → Phase 3 Mainnet.

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
| `W-AUDIT-8b` (A4-A) | Funding Skew Directional 新策略（R-1 IMPL）| W-AUDIT-8a Phase B 後 | Spec v0.1 done 2026-05-15；review/replay next |
| `W-AUDIT-8c` (A4-B) | Liquidation Cluster Reaction 新策略 | W-AUDIT-8a Phase C 後 | N+3 |
| `W-AUDIT-8d` (A4-C) | BTC→Alt Lead-Lag 新策略 | W-AUDIT-8a Phase B 平行 | ⛔ Archived from promotion 2026-05-15；diagnostic-only |
| `W-AUDIT-8e` (R-2) | Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d land 後 | N+3-N+4 |
| `W-AUDIT-8f` (R-3) | Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 個月）** — 真實 gross 轉正最早窗口。

**2026-05-15 PM prework / RCA final update**:
- `W-AUDIT-8a C1` proof packet exists: `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` + `helper_scripts/bybit/liquidation_topic_probe.py`。The prior PID `4100789` run started at `2026-05-15T19:53:09Z` and ended `FAIL_CONNECTION` at `2026-05-16T00:37:25Z`; C1 still requires a new full-duration isolated BB proof + MIT sign-off before production revival.
- `W-AUDIT-8b` Funding Skew spec v0.2 exists: `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`。It is a cross-sectional crowding signal, not retired `funding_arb`; QC/MIT/BB conditionally approve Stage 0R replay design only, so next gate is a read-only query/report packet.
- `W-AUDIT-8d` A4-C is archived from promotion and `P1-A4C-RCA-1` is closed no-revive: `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` + `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md`。Keep `panel.btc_lead_lag_panel` diagnostic-only.

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
| `P2-H0-DISPLAY-LABEL-1` | **WP-07 NEW**：Python H0Gate GUI endpoint 加 `display_only=true` 標記，避免誤認為執行權威 | est. trivial |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix → **mounted into `W-AUDIT-8f` (R-3) Hypothesis Pipeline per Decision-3 (P0-DECISION-AUDIT-7)** | Sprint N+5 |
| `P2-ORDERS-INTENT-ID-WRITER-GAP-1` | **Wave 1.5 NEW**（per Track E3 maker fill baseline 2026-05-15 commit `b98706d5`）：fix `orders.intent_id` 100% NULL writer 漏接；恢復 intent → order linkage 給 Guardian-pass-rate 計算 | est. 1 person-day；不阻 Phase 1b IMPL；E3 finding 1 證實 7d 1394 demo orders / 1021 live_demo orders 全部 `intent_id IS NULL`；無法走 `intents → orders` join 算 Guardian-pass-rate；派發時點：N+2 backlog |
| `P2-WP05-FUP-1` | **Wave 1 Round 2 follow-up**：32 處 `str(exc)` 殘留（22 處 E1 自承非 SoT 列名 + 9 處 risk_routes.py `_ipc_failure(f"...: {e}")` E2 新發現 + 1 處 strategist_promote_routes:564 enum 字串）— 走全域 handler regex 二次消毒，但仍建議逐處 migrate 為穩定 reason_code | est. 0.5 session；非 blocking；handler regex 為 second-line defense |
| `P2-COMMON-JS-LOC` | **Wave 1 Round 2 NEW**：`common.js` 2198 LOC 超 §九 2000 hard cap（pre-existing 2135 + Wave 1 +63 SDK consolidation）— 拆檔（建議 modal SDK / API helper / formatter 三檔）| est. 1 session；PM 已 accept governance exception |
| `P2-TAB-LIVE-LOC` | **Wave 1 NEW**：`tab-live.html` 2142 LOC 超 §九 2000 hard cap（Wave 1 Round 2 已從 2190 拆 -50 LOC）— 進一步拆 form / modal partials | est. 1 session；low priority |
| `P2-CROSSTAB-I18N` | **Wave 1 Round 2 NEW**：tab-system / tab-paper / console / tab-settings / governance-tab.js / tab-risk / app.js cross-tab 殘留簡體 `实盘/平仓/请检查` — 統一繁體 | est. 0.5 session；A3 follow-up wave |
| `P2-STOCHASTIC-LEAK` | **Wave 1 Round 2 NEW (QC)**：`momentum.rs:80-86` Stochastic 含 current bar（`high[start..=i]` 含 i=n-1）同類 look-ahead leak — 加 `stochastic_prior()` 變體 + 5 textbook indicator 完整 leak audit | est. 0.5 session；low priority（bb_breakout 不直接用 Stochastic，但其他 indicator 應掃完）|
| `P2-START-LOCAL-HELPER` | **Wave 1 Round 2 NEW (E2/E3)**：`start_local.sh` + `beta_quickstart.sh` 死綁 `127.0.0.1` — 改用 `helper_scripts/lib/api_bind_host.sh:resolve_openclaw_api_bind_host()` 抽象，保 safe default 但允 `OPENCLAW_BIND_HOST` override | est. 0.25 session |
| `P2-PA-CALLPATH-GREP-RULE` | **Wave 1 Round 2 NEW (audit drift 反模式)**：PA `code-quality-audit` skill 加 hard rule「P0/P1 leak/bias finding 必附 IndicatorEngine/production caller call-path grep」— QC-P0-1 Donchian 第 3 次復發 + QC-P1-1 OU sigma 第 1 次 stale finding 證實 audit drift 反模式 | est. 0.25 session；治理 skill 改進 |
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
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | rerun/repair 8a C1 full-duration proof path after `FAIL_CONNECTION` + 8b read-only Stage 0R query/report packet; A4-C diagnostic-only after no-revive RCA closure; Stage 1 demo only after future green Stage 0R (`[55]` source-cleared) |
| 2026-05-24..30 | Sprint N+2 8d follow-up + 8a Phase D + Stage 2 demo cohort 14d | Stage 2 only from Stage 1 demo empirical evidence |
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
- **AMD-2026-05-15-02 DRAFT** (EDGE-P2-3 Phase 1b Close-Maker-First): `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **EDGE-P2-3 Phase 1b spec**: `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
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
