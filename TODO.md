# 玄衡 TODO — Active Dispatch Queue

Version: v19
Date: 2026-05-09
Status: PM merge of v18 (13-agent v3 audit verification + DUAL-TRACK) + QCTODO (4-agent loss audit + Sprint N+0..N+5 + 22 invariant) + PA merge analysis (`2026-05-09--todo_qctodo_merge_analysis.md`) + FA business-chain merge advice (`2026-05-09--todo_qctodo_merge_business_chain_advice.md`). QCTODO archived to `docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`; v18 closed historical narrative remains in git history (`5789a175..e7d58774`). Wave Label Reconciliation per PA §1; 22 sign-off invariant per FA §4.

This file is the active work queue only. Historical closures, stale observation
tables, and superseded OpenClaw/Gateway assumptions are archived in
`docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md` and
`docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`.

---

## §0 Sprint Milestone Banner（FA 業務鏈視角，63% → 85-89%）

| Sprint | Week | 主題 | E1 capacity | Business chain milestone |
|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY: W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | **5 active + 1 stand-by** (operator (a)) | 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING: 8a Phase B+C 並行 + 8d (BTC→Alt) spec + Stage 1 cohort 7d 觀察 | 4/6 | 65→70% (W-AUDIT-9 Stage 1 standalone +5-7%) |
| **N+2** | W5-W6 | 8d IMPL + 8a Phase D + Stage 2 demo cohort 14d | **5 active + 1 stand-by** | 70→76% |
| **N+3** | W7-W8 | 8c (Liquidation) IMPL + 8e (R-2) spec + Stage 3 demo full | 4/6 | 76→80% |
| **N+4** | W9-W10 | 8f (R-3) spec + 8b (Funding Skew) IMPL + 8e IMPL + Track W 收尾 | 4/6 | 80-83% |
| **N+5** | W11-W12 | 8f IMPL + 8g (R-4) spec + **first per-alpha-source supervised live** | **5 active + 1 stand-by** | **85-89%** |

**Stand-by E1 啟用條件**（operator 拍板 2026-05-09 (a)）：W-AUDIT-9 T3 stage-aware exception path 翻車 / W-AUDIT-8a Phase A byte-diff fail / W-AUDIT-6d mid-ground 與 8a Phase A 序列化 deadline 撞牆 / 任一 active E1 health incident → stand-by 即時補位。

**規劃帶 supervised live 概率**（FA）：6/15 樂觀 ~30% / 6/30 中位 ~40% / 7/15 悲觀 ~25% / 8/15 極悲觀 ~5%。

---

## §1 Wave Label Reconciliation（PA §1 採 QCTODO labeling）

merged TODO v19 採 QCTODO labeling（PA 後對齊正解）。原 v18 line 552-558 Track A 中段 wave 重命名清單：

| Wave Label v19 (canonical) | 內容 | v18 舊 label（已棄）|
|---|---|---|
| **W-AUDIT-8a** | Alpha Surface Foundation (R-1 spec phase) | 8a（一致，保留）|
| **W-AUDIT-8b** | A4-A Funding Skew Directional 新策略 | 原 8b = R-1 Alpha Surface IMPL → 改至 8a 內 phase B-D |
| **W-AUDIT-8c** | A4-B Liquidation Cluster Reaction 新策略 | 原 8c = R-2 Strategist scope → 改至 8e |
| **W-AUDIT-8d** | A4-C BTC→Alt Lead-Lag 新策略 | 原 8d = R-3 Hypothesis Pipeline → 改至 8f |
| **W-AUDIT-8e** | R-2 Strategist Alpha Source Orchestrator | 原 8e = R-4 per-alpha-source live promotion → 改至 8g |
| **W-AUDIT-8f** | R-3 Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 原 8f = R-5 Spec-as-Code → 改至 10 |
| **W-AUDIT-8g** | R-4 Per-alpha-source Live Promotion Gate | n/a（新建）|
| **W-AUDIT-8h** | Alpha Sources GUI tab + Hypothesis Lab GUI tab | 原 8g（重編號至 8h）|
| **W-AUDIT-9** | Graduated Canary Foundation (5-stage canary) | 9（一致，保留）|
| **W-AUDIT-10** | R-5 Spec-as-Code + Module Lifecycle SM | n/a（新建）|

cross-document 引用對齊：CLAUDE.md §三 / §五 中對 W-AUDIT-8b/c/d/e/f/g 的引用（如有）需同步更新到 v19 labeling；docs/CCAgentWorkSpace/PA/* 報告引用以 PA dispatch plan + AMD-2026-05-09-03 為準（已採 v19 labeling）。

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
- **Graduated Canary**（AMD-2026-05-09-03）：alpha-bearing pathway 預設 5-stage（Stage 0 shadow → 1 paper × 7d → 2 demo single × 14d → 3 demo full × 21d → 4 LIVE_PENDING）；DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 Latest State

### 4-agent loss audit landing (2026-05-09)
- 4 agent (QC alpha / MIT data / PA architecture / FA business chain) 獨立分析虧損根因 + 全面提升路徑；4-視角共識：**5 textbook 策略 = dead-end alpha territory**（Bybit perp + 1m + standard TA + retail flow 數學上無 alpha）。
- Operator 拍板 5 群 dispatch（A 新策略 / B ML 三斷層 / C Promotion+Dormant / D Architectural Wave / E G3-08+治理）；PM Sign-off `5789a175` (QCTODO) → `fed11435` (operator (a))；merged 進 v19。
- AMD-2026-05-09-03 graduated canary default supersedes AMD-02 §2 binary fail-closed。
- W-AUDIT-8a Alpha Surface Foundation SPEC PHASE land (`c13c811e`)；W-AUDIT-9 Graduated Canary IMPL spec via amendment。
- **A2-followup G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable** ✅ DONE 2026-05-09 17:27 UTC（commit `dddc5dc1` engine + API env wire；env file appended；engine.log: `cost_edge_advisor spawned env=1 phase=B_shadow`）。

### v18 Latest State 保留摘要（細節在 git history `e7d58774` 之前）
- W-A/W-B/W-E/W-G backend foundation DONE。W-C MAG-082 Stage 2 evidence 收集中。
- W-AUDIT-1 docs sync DONE; W-AUDIT-2 security IMPL DONE (V078 applied, lease_transitions rows=103); W-AUDIT-3 PARTIAL (F-01 source/test); W-AUDIT-4 PARTIAL (V068/V070/V071 reclassification COMMENT, 6 表 row count 仍 0, cron 仍 not installed); W-AUDIT-5 ACTIVE; W-AUDIT-6 SOURCE/TEST CLOSED by AMD-02; W-AUDIT-7 ACTIVE; W-AUDIT-8a SPEC PHASE。
- 13-agent v3 verification (5/9 commits cover P0-V2-NEW-1/2/3 + selection bias + cron scope; **source/test only**: V079 完全未 apply / cron 未 install / engine 仍跑 5/8 binary)。
- MIT v3 第一次定位 attribution real root cause = `label_close_tag` NULL 98.9% (24h 76/7000)；**1-day fix vs PA R-3 Hypothesis Pipeline 4-6 sprint，最高 ROI**。
- v18 Latest State 200+ 行 source/test checkpoint historical 已 archive 到 `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`，以保 v19 active queue 健康。

### Current Demo State (2026-05-09)
- 5 策略 7d demo gross **-26.44 USDT** (PA `[40]` realized_edge_acceptance baseline)
- attribution_chain_ok 24h **0.5041%** (denominator artifact, ok_n only +47% 真改善；MIT root cause `label_close_tag` NULL 98.9%)
- W-AUDIT-2 V078 lease_transitions BYPASS 24h 7955 → 11133 = +40% growth（v2 唯一真活躍 runtime 進步）

---

## §4 Active Dispatch Queue

**Dispatch Order** — 不再啟動 proposal relay / Telegram/WebChat / 第二 GUI / Stage 3/4 / true live autonomy 直到 MAG-082 runtime lineage PASS。

### §4.1 Wave Roster (DUAL-TRACK + 8a-8h)

| Rank | Wave | Tag | Owner Chain | Status / Target | Exit Criteria |
|---:|---|---|---|---|---|
| 1 | `W-A` Executor fake-live runtime smoke | alpha-neutral | PM → E4 → PM | DONE 2026-05-07 | P1-FAKE-1 path routes explicit live_demo metadata through real Rust IPC. |
| 2 | `W-B` Runtime decision-spine lineage wiring | alpha-neutral | PM → PA → E1 → E2 → E4 → PM | DONE 2026-05-08 | Runtime shadow path writes nonzero typed decision objects/edges/idempotency. |
| 3 | `W-C` MAG-082 Stage 2 evidence window | alpha-neutral | PM → E3 → E4 → QA → PM | ACTIVE 2026-05-08 | Fresh 24h demo/live_demo canary proves typed lineage chain. |
| 4 | `W-D` MAG-083 / MAG-084 | alpha-neutral | QA → PM | after W-C PASS only | Final release audit + operator sign-off. |
| 5 | `W-E` OpenClaw read-only observability | alpha-neutral | PM → PA → E1 → E2 → E4 → PM | DONE 2026-05-07 | `/brief/latest` `/diagnostics` `/escalations` view models. |
| 6 | `W-F` Edge/data quality + Live Gate foundation | alpha-bearing | PM → QC/MIT/PA → E1/E4 → PM | after W-A; before true-live | H0 production caller, pricing binding, supervised-live state machine. |
| 7 | `W-G` Proposal/approval/mobile relay | alpha-neutral | PM → CC/FA/PA → E1/E2/E4 → PM | BACKEND FOUNDATION DONE 2026-05-07 | Gateway/console proposal/approval relay; no direct order/config/live-auth. |
| 8 | `W-AUDIT-1` Docs sync + governance compliance | alpha-neutral | TW + R4 + PM + PA | DONE 2026-05-09 | CLAUDE.md §三/§五/§四 lease drift sync + AMD §5.4.1 + W-C auth file + docs/README + SPECIFICATION_REGISTER + ADR-0015..0019 + SCRIPT_INDEX + MIT/BB workspace READMEs. |
| 9 | `W-AUDIT-2` Security IMPL (4 HIGH) | alpha-neutral | E1×4 + E2 + E4 + E3 | DONE 2026-05-09 | F-24/F-25 mutating routes gated; F-23 tailnet auto bind; F-03 lease writer; AI socket chmod 0600. Runtime deploy `862e79b7`: V078 applied, lease_transitions rows=103. |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live | alpha-neutral | E1 + E1a + E2 + E4 + PA + PM | PARTIAL → `W-AUDIT-3b` runtime smoke pending Sprint N+0 | F-17 ✅ / F-15 ⚠️ / SM-05 Option A / F-01 source/test closed. **`W-AUDIT-3b` Sprint N+0 必先 land**（解 D-01 + 避 W-AUDIT-9 衝突）。 |
| 11 | `W-AUDIT-4` ML 基座 + dead schema | alpha-bearing | E1×6 並行 + MIT + E2 + E4 | PARTIAL → `W-AUDIT-4b` Sprint N+1 串行 IMPL | V068/V070/V071 reclassification COMMENT only; row count 仍 0. **`W-AUDIT-4b` Sprint N+1 6 表 INSERT path 串行**（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）。Decision-3 採納合併入 `W-AUDIT-8f` (R-3) Hypothesis Pipeline 同 wave 做。 |
| 12 | `W-AUDIT-5a/5b` 性能/結構/CI/跨平台 | alpha-neutral | E1×6 並行 + E5 + E2 + E4 | ACTIVE 2026-05-09 | F-21 strip / F-26 CI matrix / F-27 字典修正 / F-test-h-state split / F-12 runner.rs split / W-AUDIT-5b event_consumer + state-machine clone snapshot + orjson + ai_budget ArcSwap; 剩 F-20 909MB damaged dump drop ops。 |
| 13 | `W-AUDIT-6` 策略 + 量化 promotion gate | alpha-bearing | E1×5 + QC + E2 + E4 + PM | SOURCE/TEST CLOSED 2026-05-09 → `W-AUDIT-6c` runtime apply + `W-AUDIT-6d` mid-ground Sprint N+0 | AMD-02 Option ii: grid CONDITIONAL ORDIUSDT, ma_crossover REVISE, bb_breakout 5m, funding_arb RETIRE, bb_reversion pair MA. W-AUDIT-6c VaR/CVaR/EVT IMPL `cc6476dd`. **`W-AUDIT-6d` mid-ground 保 6 / 砍 6** (見 §8)。 |
| 14 | `W-AUDIT-7` AI 棧 + GUI/UX | alpha-neutral | E1×4 + AI-E + A3 + E2 + E4 + ops | ACTIVE → `W-AUDIT-7c` Sprint N+2 | F-30 prompt modal / F-system-mode-confirm 5s countdown / F-strategist-cap 30→50 ADR-0021 待 / F-28 ContextDistiller IMPL. 剩 F-07 ANTHROPIC_API_KEY + cea-env. Layer2 autonomous loop sunset by ADR-0020. |
| 15 | `W-AUDIT-8a` Alpha Surface Foundation (R-1 spec) | alpha-bearing | PA → E1 → E2 → E4 + MIT/QC/CC/BB → PM | SPEC PHASE 2026-05-09 / **Phase A target Sprint N+0** | Strategy on_tick(ctx, surface) 升級 + AlphaSurface<'a> 4 tier + AlphaSourceTag enum + 5 既存策略 declare alpha sources + Phase B Tier 2 cross-symbol panel collector + Phase C Tier 3 microstructure + Phase D Tier 4 + 7d replay E2E byte-identical baseline。Spec: `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`. |
| 16 | `W-AUDIT-8b` A4-A Funding Skew Directional 新策略 | alpha-bearing | PA spec → E1 IMPL + QC + MIT + BB review | Sprint N+3 spec → N+4 IMPL (1 sprint) | funding rate 期限結構 directional alpha；demo signal noise（mainnet 才能完整驗證）；25-symbol funding curve 消費 AlphaSurface Tier 2。 |
| 17 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction 新策略 | alpha-bearing | PA spec → E1 (Rust hot-path) + QC + BB review WS | Sprint N+2 spec → N+3 IMPL (1.5 sprint) | Bybit `allLiquidation` WS topic 真接；event-trigger 模式；消費 AlphaSurface Tier 3 microstructure。 |
| 18 | `W-AUDIT-8d` A4-C BTC→Alt Lead-Lag 新策略 | alpha-bearing | PA spec → E1 IMPL + QC review | Sprint N+1 spec → N+2 IMPL (1.5 sprint，**最高 impact + 第一 IMPL**) | BTC 1m 急動 ≥1.5σ 信號；alt 同方向 entry 60s 內（前提 alt-BTC 60s ρ>0.7 + alt 仍未動 ≥50%）；半衰期 30-180s 與 1m sampling 完美匹配。 |
| 19 | `W-AUDIT-8e` (R-2) Strategist Alpha Source Orchestrator | alpha-bearing | PA spec → E1 IMPL | Sprint N+4 spec → N+5 IMPL (2-3 sprint) | Strategist 從 4×5 hardcoded regime preferences → AlphaSourceRegistry + 動態 Sharpe-by-regime + Hypothesis sourcing。 |
| 20 | `W-AUDIT-8f` (R-3) Hypothesis Pipeline + W-AUDIT-4 ML 併入 | alpha-bearing | PA spec → E1 IMPL + MIT spec | Sprint N+5 IMPL (2-3 sprint) | learning.hypotheses table state machine + Decision Lease + Hypothesis 關係 + W-AUDIT-4 6 dead schema 併入解 attribution_chain 0.5%→80% root cause（Decision-3 confirmed）。 |
| 21 | `W-AUDIT-8g` (R-4) Per-alpha-source Live Promotion Gate | alpha-bearing | PA spec → E1 IMPL | Sprint N+7+ defer (2 sprint) | LiveBudget(alpha_source_id, slice) 替代「整 system live_reserved」線性 LG-2/3/4/5；FA defer 至 N+7（W-AUDIT-9 已部分覆蓋）。 |
| 22 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | alpha-neutral | E1a + A3 review | Sprint N+4-N+6 (1 sprint) | A3 建議 13→15 tab。 |
| 23 | `W-AUDIT-9` Graduated Canary Foundation IMPL | alpha-bearing | E1 (5 active + 1 stand-by 並行) | **Sprint N+0 IMPL T1-T7 (1.5-2 sprint)** | AMD-2026-05-09-03 配套：Rust schema executor_canary_stage + V### migration + shadow_mode_provider stage-aware + healthcheck [58] + governance.canary_stage_log + GUI surface + LeaseScope::CanaryStagePromotion + E4 regression。**`W-AUDIT-9` Stage 1 launch 是 standalone milestone**（FA 估 +5-7%，不混 Track A funding skew Stage 1 行）。 |
| 24 | `W-AUDIT-10` (R-5) Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec → E1 IMPL | defer 中期 (1-2 sprint) | CI gate spec drift > 7d auto-fail + module/table lifecycle header + 自動抽 SCRIPT_INDEX/SPEC_REGISTER。 |

### §4.2 Cross-Wave Conflict Resolution（4 條，PA §3.3 必繼承）

| # | 衝突 | Files / Surface | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | **序列化**：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | **W-AUDIT-3b 必先 land**；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群 3 新策略（8b/8c/8d）↔ W-AUDIT-9 Stage 1 cohort 選擇 | governance/canary | A4-C (8d) 用 W-AUDIT-9 Stage 1 paper cohort 入場；非 W-AUDIT-9 7 sub-task 完整 land 不啟動 |

---

## §5 PM Sign-off Pre-flight Checklist（22 invariant，FA §4 + PA §6 deduplicate；任一 FAIL = BLOCKER）

### §5.1 結構 invariant（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 1 | Sprint N+0 W-AUDIT-9 7 sub-task 全 land + `[58]` PASS + `governance.canary_stage_log` active | `git log --grep=W-AUDIT-9` 7 commit + healthcheck PASS | PA-1 |
| 2 | Sprint N+0 W-AUDIT-8a Phase A trait 升級 land + 5 策略 byte-identical replay PASS + `cargo build --release` 綠 | E2E byte-diff test PASS | PA-2 |
| 3 | W-AUDIT-6d mid-ground 6 保子項 land + 砍 6 子項 grep blacklist 0 命中 | grep audit + 6 commit 存在 | PA-3 |
| 4 | W-AUDIT-9 Stage 1 cohort active + 7d wall-clock 觀察期未提前升級（**standalone milestone**） | `governance.canary_stage_log` Stage 1 entered_at_ms + auto-promote 條件未提前觸 | PA-4 + FA-Critique-2 |
| 5 | W-AUDIT-4b 6 表 INSERT path 已**串行** IMPL（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行） | commit ordering 驗 + schema relationship test PASS | FA-2 |

### §5.2 安全 invariant（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 6 | DOC-08 §12 9 條安全不變量未違反 | 逐條 grep + healthcheck pass | PA-5 |
| 7 | live boundary 5-gate 所有 stage active 期間未繞過 | LiveDemo authorization.json 簽名+TTL+env_allowed 全 pass | PA-6 |
| 8 | §二 16 根原則合規（especially 1/4/5/6/9） | 逐條 grep + AMD-2026-05-09-03 §6.3 校核 | PA-7 |
| 9 | `shadow_mode_provider` exception path fail-closed Stage 0（**不是** Stage 1） | E2 review T3 + unit test PASS | PA-8 |
| 10 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留（Live boundary 5-gate / SM-04 ladder / DOC-08 §12 / §二 16 原則 4 範圍均不被 graduated canary 觸碰） | 4 範圍逐條 invariant test | FA-4 |

### §5.3 治理 invariant（7 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 11 | `canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL 強制 | V0XX migration 含 `CHECK (transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL)` | PA-9 |
| 12 | healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback | `[58]` IMPL 對 SM-04 L3 邏輯 explicit + unit test PASS | PA-10 |
| 13 | A 群 3 新策略 IMPL 後 `declared_alpha_sources()` 與真實邏輯對齊 | grep 3 新策略 ctor + QC review report sign-off | PA-11 |
| 14 | W-AUDIT-8b/c/d sequence 必含 **Stage 2 abort gate**（A4-C IMPL 後 Stage 2 demo 14d gross < 0 → A 群 8b/8c 重評，**不**連續 IMPL） | Sprint sign-off report 明文記入 | FA-5 |
| 15 | D-02 Layer 2 manual SOP 不違反 ADR-0020（manual probe 不可自動化為 cron / event-trigger） | code grep audit | FA-6 |
| 16 | W-AUDIT-6d mid-ground 砍 6 polishing 的 **K -12 trial DSR penalty 量化結論記入 sign-off report**（mu_0 從 ~2.54 降至 ~2.27 用 ln，z_DSR 增益 +0.30） | sign-off report 明文 | FA-7 |
| 17 | v2-NEW-1 strategist cap 30%→50% 補 **ADR-0021**（freedom-not-gate rationale + SM-05 張力 + 50% 偏離監測指標） | ADR-0021 land + commit | FA-8 |

### §5.4 監督 / record（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 18 | F-08 5 ML cron `crontab -e` install + 24h 真 fire 驗 | `[Xc] ml_training_cron_active` PASS（A1 cron 已 install at `17 3 * * *`，24h fire 待驗）| FA-3 |
| 19 | 6 表 0 INSERT 18 天無變動 gap 必有 owner + ETA（individual P1 ticket：`P1-INSERT-PATH-1..6`） | TODO entry P1 標記 | FA-9 |
| 20 | W-AUDIT-3b runtime smoke 已從 Linux 驗（`pytest -k test_executor_fail_closed` + engine restart 後 `[55] chains_with_lease > 0`） | ssh trade-core run + log evidence | FA-1 |
| 21 | **`P0-MIT-LABEL-CLOSE-TAG-1`** 1-day fix 已 IMPL + `attribution_chain_ok` 24h ≥ 5%（從 0.5% → 5%） | `[42b]` healthcheck PASS + writer fix commit | merged FA |
| 22 | Sprint N+0/N+2/N+5 capacity = 5 active + 1 stand-by E1 explicit recorded（不允許「臨時降級為 5/5 HOT」） | Sprint sign-off report 明文 | merged FA |

**git status clean 強制**（CLAUDE.md §七 P0-GOV-3）：merge 後 mandatory，process gate（不算 22 條 invariant 之內）。`git status --porcelain` 對應檔案必 clean，違反 = PM 拒絕 sign-off。

---

## §6 Sprint N+0 Day-by-Day Dispatch（PM 從 v19 sign-off 後立即派發）

### Day 0-3 並行 5 active E1 + 1 stand-by E1 + ops（operator 2026-05-09 拍板 (a)）

**5 active E1 IMPL slot**：
- `@E1-A` W-AUDIT-9 T1 Rust schema 升級（並行 `@QC` enum review）
- `@E1-B` W-AUDIT-9 T2 V### migration（並行 `@MIT` review）
- `@E1-C` W-AUDIT-9 T3 `shadow_mode_provider` stage-aware
- `@E1-D` W-AUDIT-9 T6 manual promote Decision Lease（後段轉 W-AUDIT-6d mid-ground 6 保子項，並行 `@QC` 數學審計）
- `@E1-E` W-AUDIT-4b-M1 decision_features intent-only emit（並行 `@MIT` review V###）

**1 stand-by E1 slot**：
- `@E1-F` (stand-by) 平時跑 W-AUDIT-5b 維護 backlog；任一 active E1-A/B/C/D/E health incident → 立即切換補位
- 每日 stand-up 25 min 對齊（active E1 status + stand-by 是否需切換）

**ops**：
- `@ops` A2-followup G3-08 ✅ DONE（2026-05-09 17:27 UTC, daemon spawn confirmed）

### Day 3-5 E2 first-pass

- `@E2` review T1+T2+W-AUDIT-6d mid-G+W-AUDIT-4b-M1
- `@E4` regression schema test

### Day 5-7 Dispatch（W-AUDIT-6d mid-G done 後 8a Phase A 序列化開始）

- `@E1-A` W-AUDIT-8a Phase A trait 升級 + 5 策略 declare
- `@E1-B` W-AUDIT-4b-M2 entry_context_id INSERT trigger
- `@E1-C` W-AUDIT-4b-M3 negative label + class weight
- `@E1-D` W-AUDIT-6c runtime apply (V079 + cron + DSR/PBO evidence pipeline)
- `@E1-E` W-AUDIT-9 T4 healthcheck `[58]`
- `@E1-F` 切換補位 W-AUDIT-9 T5 GUI surface（從 stand-by 進 active）

### Day 12-14 Full review chain

- `@E2` second-pass review T3+T4+T5+T6+8a Phase A+M2+M3+W-AUDIT-6c
- `@E4` regression 5-stage transition + byte-diff E2E + 6 表 INSERT schema + DSR/PBO query
- `@QC` 5 策略數學審計 + AlphaSourceTag enum 完整性
- `@MIT` V### migration row-rate 估算 + cron install
- `@CC` Scout IPC schema preview（為 8a Phase D Sprint N+2）
- `@BB` Bybit V5 levels 對齊 review（為 Phase C Sprint N+1）

### Day 14-15 PM Sign-off Sprint N+0 milestone（跑 §5 22 invariant）

---

## §7 W-AUDIT-6d Mid-Ground（保 6 / 砍 6 + DSR K -12 量化）

### 保 6 結構性子項（Sprint N+0, 5 person-day, QC review）

1. DSR/PBO 自動化 evidence push（V079 + `promotion_evidence.py`） — alpha-bearing
2. Kelly RiskConfig SSOT（`per_trade_risk_pct` + Kelly tier） — alpha-bearing
3. funding_arb retire（4 TOML clean, ADR-0018, ✅ done）
4. portfolio VaR/CVaR/EVT promotion gate（W-AUDIT-6c, IMPL ✅, runtime apply 待）
5. `portfolio_var min_observations=200` review + sampling unit 校正
6. bb_reversion verdict（pair MA per AMD-2026-05-09-02 §3）

### 砍 6 polishing 子項（**E2 grep blacklist; 命中即 reject merge**）

1. ❌ ma_crossover 5m 反向觀察重做
2. ❌ bb_breakout Donchian 5m optimization sweep
3. ❌ grid_trading symbol expansion ORDIUSDT → 5
4. ❌ funding_arb v3 MA pair retry
5. ❌ strategy_params 4×5 hardcoded → 動態 Sharpe-by-regime（W-AUDIT-8e 後做更合適）
6. ❌ 5 策略 cost_gate threshold 個別 tune

### DSR Multiple Testing Penalty 量化

- 保 6: K +3 trial（DSR/PBO + portfolio VaR + min_obs review）
- 砍 6: K -15 trial（避免 sweep / per-symbol / per-threshold inflation）
- **Net: K -12 trial**

DSR 公式 `mu_0 = sqrt(2 × ln(K))` 修正項（**ln 自然對數**，非 log₁₀）。K 從 ~25 降至 ~13 → `mu_0` 從 ~2.54 降至 ~2.27 → Δ ≈ -0.27 → z_DSR 增益 +0.30 → 對 5 策略 sharpe ~0.5 demo n=200 樣本，DSR PASS percentile 增益 +5-10%（fat-tail 折扣後）。E1-D `2026-05-09--w_audit_6d_dsr_penalty_quantification.md` 詳細推導；早期 QCTODO/PA 引用 ~2.83 是 log₁₀ 錯算，不採。

**FA Push back**：mid-ground 砍 6 polishing **正是 DSR 數學意義的 right move**，不是省工時妥協。invariant 16 必明文記入 sign-off report。

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
| `P0-AGENT-1` | ACTIVE | Runtime Agent Decision Spine lineage | One-shot runtime proof now includes Decision Lease bypass lineage; continue W-C until 24h Stage 2 PASS. |
| `P0-AGENT-2` | ACTIVE | MAG-082 Stage 2 rerun | New operator-approved window collecting evidence; PASS requires 24h window. Replay cannot substitute. |
| `P0-AGENT-3` | BLOCKED | MAG-083 final release audit | QA PASS after `P0-AGENT-2`. |
| `P0-AGENT-4` | BLOCKED | MAG-084 operator sign-off | PM/operator sign-off after MAG-083 PASS. |
| `P0-EDGE-1` | ACTIVE | Edge net-positive decision | Strategy edge must be positive or scoped to limited supervised path before true-live. **Root cause linked to `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI）**。 |
| `P0-MIT-LABEL-CLOSE-TAG-1` | **ACTIVE 1-DAY FIX** | `label_close_tag` NULL writer fix（attribution real root cause） | MIT v3 第一次定位：24h 76/7000 = 1.0857% chain_ok；fix `label_close_tag` writer 後預期 attribution_chain_ok 24h ≥ 5%（invariant 21）。**最高 ROI** vs PA R-3 4-6 sprint。 |
| `P0-LG-1` | ACTIVE | H0 blocking production caller | H0 wired into production decision path with metrics + fail-closed. |
| `P0-LG-2` | ACTIVE | Provider pricing binding | Fee/pricing source bound, freshness checked, asserted at startup. |
| `P0-LG-3` | ACTIVE | Supervised-live state machine | Live authorization, lease, drawdown, revoke, operator approval explicit + tested. |
| `P0-OPS-1..4` | ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | Required before true-live. |
| `P0-DECISION-AUDIT-1..5` | DONE 2026-05-09 | AMD §5.4.1 / shadow_mode TOML / §三 stale 防線 / 5 策略 verdict / openclaw_core+Layer2 sunset | AMD-2026-05-09-02 + ADR-0015/0017/0020 + W-C operator auth file。 |
| `P0-DECISION-AUDIT-6` | DONE 2026-05-09 | **W-AUDIT-6d mid-ground verdict**（保 6 / 砍 6） | Operator confirmed 2026-05-09 mid-ground (PM session)；保 6 結構性 + 砍 6 polishing；DSR K -12 量化（§7）。 |
| `P0-DECISION-AUDIT-7` | DONE 2026-05-09 | **W-AUDIT-4 ML 基座併入 W-AUDIT-8f (R-3) Hypothesis Pipeline** | Operator confirmed 2026-05-09 (PM session)；W-AUDIT-4b 6 表 INSERT path 串行 IMPL 是 W-AUDIT-8f schema migration 同 wave 一部分。 |
| `P0-NEW-ISSUE-1` | DONE 2026-05-09 | LiveDemo pipeline auth_missing → restored | `[56]` PASS via signed `/api/v1/live/auth/renew`；RCA: `manual` sentinel；`--keep-auth` warns when auth absent. |
| `P0-NEW-VULN-1..2` | DONE 2026-05-09 | launchd plist HIGH / lease audit runtime emit HIGH | Mac launchd 127.0.0.1 binds; `100.91.109.86:8000` Tailscale; lease_transitions `BYPASS` rows=103. |
| `P0-AUDIT-NEW-LG-X-05` | DONE 2026-05-09 | SPECIFICATION_REGISTER LG-X-05 缺 + LG-X-04 編號錯位 | LG-X 完整登記。 |
| `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` | DONE 2026-05-09（**4-agent fact-check 撤銷 stale belief**） | `IndicatorEngine::compute_all` 自 `75741eff` (2026-04-28) 起呼 `donchian_prior()` leak-free 11 天；`ad14db07` 僅補 regression test；QC v2-NEW-4「runtime contaminated」判定為過期 contaminated belief（commit `6afad6e8`）。 | n/a |
| `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE` | DONE 2026-05-09; **ADR-0021 待**（invariant 17） | F-strategist-cap 30→50 是 wide_parameter_adjustment skill；不是 supervised gate；待補 ADR-0021。 | ADR-0021 land + commit |
| `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` | SOURCE/TEST CLOSED 2026-05-09; RUNTIME PENDING Sprint N+0 | DSR/PBO promotion gate IMPL ✅；`learning.strategy_trial_ledger` V079 待 apply；evidence push 鏈 `promotion_evidence.py` IMPL；待 cron install + V079 apply + rebuild/restart。 | V079 apply + cron install + 24h fire |
| `P0-V3-MIT-ROOT-CAUSE` | **= P0-MIT-LABEL-CLOSE-TAG-1**（cross-reference）| 同上 | 同上 |
| `P0-V3-V079-NOT-APPLIED` | ACTIVE Sprint N+0 | 48227607 source 已落但 _sqlx_migrations max=78；V079 待 apply | engine restart with auto-migrate；invariant 18 |
| `P0-V3-CRON-NOT-INSTALLED` | ✅ DONE 2026-05-09 | F-08 5 ML cron `17 3 * * *` 已 install Linux crontab；待 24h fire 驗 | invariant 18 24h fire |
| `P0-V3-PA-SPEC-FIX` | ACTIVE Sprint N+0 | BB v3 揭發 PA spec 3 條錯誤：(1) Bybit V5 WS L25→L50 / (2) liquidation_pulse 4 weeks ago deleted 需 revert / (3) basis demo 限 observation 沒分（execution 需 mainnet） | PA spec 修 3 條 + ADR-0021/ARCH-04 同 wave |
| `P0-V3-ADR-0021-ARCH-04` | ACTIVE Sprint N+0 | 建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-03/04（R4/TW 共識） | ADR/ARCH/CONTEXT 全 land |
| `P0-V3-ENGINE-RESTART` | ACTIVE Sprint N+0 | engine 仍跑 5/8 binary 待 rebuild 含 Donchian fix + 多 commits 落地（注：Donchian fix 已自 75741eff 04-28 land 11 天，不是 actionable blocker；其他 commits 如 V079/A4-C 等 land 後 rebuild） | engine restart with latest binary |

---

## §11 P1 — Next Engineering Queue

### §11.1 Sprint N+0 Active

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `W-AUDIT-9` | 1 | Sprint N+0 IMPL 7 sub-task（T1-T7） | E1-A..E1-D + E1-F catch-up；invariant 1 |
| `W-AUDIT-8a` Phase A | 1 | Sprint N+0 trait 升級 + 5 策略 declare | E1-A 後段；invariant 2；序列化於 W-AUDIT-6d 後 |
| `W-AUDIT-6d` mid-G 6 保 | 1 | Sprint N+0 6 保子項 land | E1-D；invariant 3 |
| `W-AUDIT-4b-M1/M2/M3` | 1 | Sprint N+0 ML 三斷層串行 IMPL | E1-E（M1） / E1-B（M2） / E1-C（M3）；invariant 5 + 19 |
| `W-AUDIT-6c` runtime apply | 1 | Sprint N+0 V079 apply + DSR/PBO evidence pipeline runtime + cron 24h fire 驗 | E1-D；invariant 18 |
| `W-AUDIT-3b` runtime smoke | 1 | Sprint N+0 ExecutorAgent runtime smoke + fail-closed metrics 從 Linux 驗 | E1（W-AUDIT-9 T3 前置 mandatory）；invariant 20 |
| `P0-MIT-LABEL-CLOSE-TAG-1` | 1 | Sprint N+0 1-day fix `label_close_tag` NULL writer | E1；invariant 21 |
| `ADR-0021` + `ARCH-04` + `AMD-03/04` | 1 | Sprint N+0 governance 補完 | PA + R4 + TW；invariant 17 |

### §11.2 P1-INSERT-PATH-1..6（FA §2.1 必 individual ticket，invariant 19）

| ID | Table | Sequential order | Owner |
|---|---|---|---|
| `P1-INSERT-PATH-1` | observability.feature_baselines | **first** | E1 |
| `P1-INSERT-PATH-2` | learning.mlde_edge_training_rows | 2nd | E1 |
| `P1-INSERT-PATH-3` | learning.scorer_predictions | 3rd | E1 |
| `P1-INSERT-PATH-4` | learning.cost_edge_advisor_log | parallel after 3 | E1 |
| `P1-INSERT-PATH-5` | observability.drift_events | parallel after 3 | E1 |
| `P1-INSERT-PATH-6` | learning.scorer_training_features | parallel after 3 | E1 |

### §11.3 P1 — Other Active

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `P1-CRON-ML-1` | 2 | F-08 5 ML cron 24h fire 驗（cron 已 install at `17 3 * * *`） | invariant 18 |
| `P1-AUDIT-RUNTIME-3` | 2 | W-AUDIT-3 + W-AUDIT-3b（mounts W-A close-out + W-B regression） | F-01 source/test closed; 待 W-AUDIT-3b runtime smoke + W-AUDIT-9 stage-aware integration |
| `P1-AUDIT-PERF-5` | 3 | W-AUDIT-5a/5b 性能/結構/CI urgent | 剩 F-20 909MB damaged dump drop ops |
| `P1-AUDIT-AI-UX-7` | 3 | W-AUDIT-7c GUI/UX 收口 | F-07 ANTHROPIC_API_KEY + cea-env restart |
| `P1-DATA-1..3` | 3 | Runtime-reloaded WARN cluster + low-sample attribution watch + scanner opportunity calibration watch | DONE source-fixed; row rolloff monitor |
| `P1-EDGE-1..2` | 3 | ma_crossover/grid blocked_symbols 已 frozen + funding_arb 14d audit 2026-05-16 | 維持 freeze + 2026-05-16 audit |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source active; audit-row health |
| `P1-FAKE-1` / `P1-OPENCLAW-3/6/7` / `P1-AGENT-OBS-1` / `P1-AGENT-RUNTIME-1` / `P1-DATA-4` / `P1-REPLAY-1/2` | DONE | （詳細歷史見 git history `e7d58774`）| |

---

## §12 P2 — Maintenance Backlog

| ID | Task | Trigger |
|---|---|---|
| `P2-LEASE-1` | Clean terminal `DecisionLeaseSm.objects` Vec entries | If long soak shows memory growth or before high-volume live |
| `P2-STRUCT-1` | DONE 2026-05-09 17:27 UTC commit `dddc5dc1` — HStateCache + CostEdgeAdvisor late-inject slot enablement | A2-followup G3-08 enable verified |
| `P2-STRUCT-2` | Zombie/deprecated code inventory | Next architecture hygiene sweep |
| `P2-AUDIT-PERF-5b` | DONE — event_consumer + state-machine snapshot + orjson + ai_budget ArcSwap | (see git history) |
| `P2-AUDIT-VAR-6c` | DONE 2026-05-09 — W-AUDIT-6c portfolio VaR/CVaR/EVT IMPL `cc6476dd` | runtime apply at Sprint N+0 |
| `P2-AUDIT-LAYER2-7c` | DONE-BY-DECISION — autonomous Layer2 loop sunset by ADR-0020 | manual+supervisor only |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset (D-16 dormant，§9) | ADR-0015 + AMD-2026-05-09-02 accept; Sprint N+6+ |
| `P2-AUDIT-VERIFY-1..7` | DONE 2026-05-09 (詳細歷史見 git history) | various |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix → **mounted into `W-AUDIT-8f` (R-3) Hypothesis Pipeline per Decision-3 (P0-DECISION-AUDIT-7)** | Sprint N+5 |
| `P2-AUDIT-VERIFY-4` | F-08 cron install ✅ DONE 2026-05-09 (P1-CRON-ML-1 24h fire pending) | invariant 18 |
| `P2-AUDIT-QC-STAND-ALONE` | DONE — QC stand-alone fixes (funding_arb / Kelly / cooldown / DSR-PBO / §三 -26.44) | (see git history) |
| `P2-V19-CYCLE` | TODO v19 land 後 1-2 sprint 啟動 v20 archive cycle | 防 v19 突破 800 行衛生線 |

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
| 2026-05-10..16 | Sprint N+0 W1-W2 FOUNDATION HEAVY | §6 Day-by-Day; §5 22 invariant sign-off |
| 2026-05-16 | funding_arb 14d audit | verification/history; retirement decision in AMD-2026-05-09-02 / ADR-0018 |
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | 8a Phase B+C 並行 + 8d (BTC→Alt) spec + W-AUDIT-9 Stage 1 cohort |
| 2026-05-24..30 | Sprint N+2 8d IMPL + 8a Phase D + Stage 2 demo cohort 14d | 8a wave acceptance |
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
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only

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
