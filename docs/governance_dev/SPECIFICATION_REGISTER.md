# Governance Specification Register / 治理規範註冊表

**Project:** 玄衡 · Arcane Equilibrium
**Last Updated:** 2026-06-30 (ADR-0048 + AMD-2026-06-29-01 IBKR stock/ETF GUI lane contract)
**Maintained By:** R4 (Document Auditor) · TW catch-up（2026-04-29）· FA Sign-off path A（2026-05-02 AMD-2026-05-02-01）

---

## Amendments / 規範修訂（2026-05 新增）

> Amendments are spec-level adjustments **without** changing the SM/EX/DOC numbered specifications themselves; they record implementation reaffirmations, scope clarifications, or last-mile fills (e.g., R-04 retrofit). Each amendment is dated `YYYY-MM-DD` and code-prefixed `AMD-YYYY-MM-DD-NN`.

| Code | 對應 spec | 路徑 | 日期 | 摘要 |
|------|----------|------|------|------|
| AMD-2026-05-02-01 | SM-02 §scope · DOC-01 §5.3 | `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | 2026-05-02 | Path A — Rust `acquire_lease()` facade R-04 retrofit；spec 條文 0 改動，回填 v3 plan §1.3 last-mile；bundled with 18 blocker #6 audit writer fix；E4 5 條 acceptance criteria（AC-1~5）|
| W-C-AUTH-2026-05-08 | AMD-2026-05-02-01 §5.4.1 · MAG-082 | `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md` | 2026-05-08 | Operator-authorized W-C evidence-mode lease-router flag ON；`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` + Agent Spine shadow lineage only；not true-live auth / not MAG-083 / not MAG-084 |
| AMD-2026-05-09-01 | SM-05 · DOC-01 §5.3/§5.6/§5.10/§5.11 · EX-06 | `docs/governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md` | 2026-05-09 | Accepted SM-05 Executor shadow-mode polling policy；documents `ExecutorConfigCache` poll / fail-closed / last-good behavior；F-01 source implemented |
| AMD-2026-05-09-02 | SM-05 · ADR-0015 · ADR-0018 · ADR-0020 | `docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md` | 2026-05-09 | Accepted operator decision audit closure for `P0-DECISION-AUDIT-2/4/5`: SM-05 Option A, W-AUDIT-6 strategy verdict, openclaw_core sunset candidates, Layer2 manual supervisor-only |
| AMD-2026-05-09-03 | SM-05 · DOC-01 §5.5/§5.6/§5.11 · ADR-0017 · ADR-0018 · ADR-0020 | `docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` | 2026-05-09 | Historical 5-stage graduated canary default; Stage 1 paper semantics superseded by AMD-2026-05-15-01. Retained for W-AUDIT-9 original rationale, `[58]`, and `governance.canary_stage_log` context. |
| AMD-2026-05-15-01 | W-AUDIT-9 · SM-05 · DOC-01 §5.5/§5.6/§5.11 · DOC-08 §12 · ARCH-04 | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` | 2026-05-15 | Removes Stage 1 `Environment::Paper × 7d`; adds Stage 0R Replay Preflight (`eligible_for_demo_canary=true/false`, no Stage 1 PASS); redefines Stage 1 as 1 strategy × 1 symbol × Demo × 7d micro-canary; Stage 2 must enter from Stage 1 demo evidence. |
| AMD-2026-05-15-02 | EDGE-P2-3 Phase 1b · DOC-08 §12 · CLAUDE.md §二 #16 · §四 reject_cooldown | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` | 2026-05-15 (v0.4 Wave 3a re-review 2026-05-16) | EDGE-P2-3 Phase 1b close-maker-first refactor — 8 maker-first / N keep-market 邊界明文；hybrid V094 schema；FDR multiple testing；phys_lock_gate4 timeout 30→15s；dynamic backoff per-symbol；reject_cooldown entry/close split P0 prereq；W-C Caveat 2 lineage carve-out；4-agent re-review (QC+FA+BB+MIT) APPROVED-CONDITIONAL → v0.4 consolidated patch |
| V094 hybrid schema spec | trading.fills.details JSONB extension · `close_maker_attempt:bool` + `close_maker_fallback_reason:text` 新欄位 · MakerRejectionCategory enum allowlist | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` | 2026-05-15 (commit `9b1117a0`) | Wave 2a Track A2 — V094 hybrid schema migration spec finalize（F-FA-1 IMPL Prereq 5 第 3 子條件）；Linux PG empirical 證實 trading.fills.details JSONB 已存於 V003 line 284，24h 98 fills 0% details；includes Guard A/B/C templates + Linux PG dry-run × 2 round + sqlx checksum repair SOP + writer upgrade spec (13 caller sites + TradingMsg::Fill enum +24 fields) + healthcheck [62][63][64][65] integration + Backward-compat append-only + Rollback paths；IMPL pending Phase 1b 主軸 |
| AMD-2026-05-21-01 (v1) | v5.8 §11 · CLAUDE.md §二 priority order 第 5 條 · ADR-0034 (M1 LAL) · AMD-2026-05-15-01 (Stage gate) | `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` | 2026-05-21 | Status: Superseded by v2 (2026-05-22). v5.8 13-module thesis 核心治理 amendment：priority 5「human final review」拆 protected scope（6 條 a-f 永不可 auto：Stage LAL 3-4 / 5-gate / Copy Trading enable / Auto-Allocator activation / kill criteria / ADR-debt creation）vs opt-in scope（8 條 g-n operator 一次 opt-in 後可 auto：LAL 1+2 / M2 auto-disable always-on / M3 Tier 1+2 / M6 ≤30% / M7 auto-demote / M8 Y2 trigger / M10 capital tier eval）；5 條 mitigation（default-OFF / 5-gate fail-closed / 24h undo config-only / per-action lease+notify / 60d inactivity auto-rollback Advisory）+ 6 條反向 attack counter-mitigation（M1 fill 不可逆 / M2 false anomaly counterfactual / M3 healthy burst HEALTH_WARN alert-only / M7 14d review 末必 operator click / M8 4-級 severity halt 只 CRITICAL / M11 5d 不 ack 自動升 HEALTH_WARN）；§二 16 原則合規 #5/#6/#11/#15 重點確認；不放鬆 §四 hard boundaries 任一條；TW Drafted / CC + E3 + FA PENDING |
| AMD-2026-05-21-01 v2 | v5.8 §11 · CLAUDE.md §二 priority order 第 5 條 · ADR-0034 (M1 LAL) · AMD-2026-05-15-01 (Stage gate) | `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` | 2026-05-22 | Active (Supersedes v1 2026-05-22). Layered Autonomy with Hard-Coded Fail-Safe — 取代 v1 protected/opt-in 二分；Autonomy Level Toggle (Conservative/Standard) + 三路通知 fail → 1h wait → SM-04 Defensive；Cache PG LISTEN/NOTIFY；7d fail-safe cooling；CC APPROVE A 級 (7/7 HC + 6/6 反模式 + 2 BLOCKER 候選解除)；4 SSOT file + Wave 5 cascade IMPL PENDING |
| AMD-2026-05-26-01 | ADR-0018 §Decision · TODO §1 P0-FUNDING-ARB-DECISION-FORCE · §6 P1-EDGE-2 · AMD-2026-05-09-02 W-AUDIT-6 | `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md` | 2026-05-26 | funding_arb V2 Deprecation Closure（Workflow F Phase 2）— operator (D) 3C TOML deprecation；ADR-0018 status 從 "retire from active strategy set" 升格 **Retired closed**；enforcement = 三端 TOML config-load active=false（commit `a19797d` 已 land）+ 5 textbook → 4 textbook roster reframe；程式碼層 `#[deprecated]` marker + runtime fail-closed guard 屬 §3.2 D+7 E1 IMPL，**從未 land**（per 2026-06-14 治理漂移訂正；無 runtime IPC active=true 注入 guard）；ADR-0046 future redesign slot 並存保留；D+0/D+7/D+30 cleanup 三階段；72 unit tests 全保留 dormant 結構驗。 |
| AMD-2026-05-31-01 | ADR-0047 · Alpha-Edge S1-Sx evidence governance · TODO §1 P0-EDGE-1 · Alpha-Edge execution plan | `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md` | 2026-05-31 | Alpha-Edge Evidence Governance — bull data allowed only when explicitly labeled; S4 downgraded to global S1-Sx regime/falsification overlay; Bybit market API treated as raw state input, not prediction oracle; trend/state classifier must be local math-first; future news/X/Reddit agents are secondary corroboration only and cannot override quantitative promotion gates. |
| AMD-2026-05-25-01 | ADR-0030 (Copy Trading evidence-gated) · ADR-0006/0033 (Bybit + Binance venue scope) · ADR-0040 (Multi-Venue Gate Spec) · ADR-0031/0032 (Bybit Earn governance) · AMD-2026-05-20-04 §1 Stream 2 (superseded) · AMD-2026-05-20-05 (scope extended) | `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md` | 2026-05-25 (operator approved 2026-05-27) | **Active** — Commercialization Boundary: Exchange-Native Only。Supersedes AMD-04 §1 Stream 2 (Monetization Demand Test 30% capacity) + extends AMD-05 retract scope from「IP sale only」to「all non-exchange-native commercialization」。Retire 8 路徑（IP sale / Telegram subscription / Substack/Beehiiv / signal feed integration / MEV/DEX / Stripe pre-order / Cloudflare Pages landing / Twitter outreach）。Retain 6 路徑（Bybit Copy Trading per ADR-0030 / Bybit Earn per ADR-0031-0032 / Bybit competitions / Binance Copy Trading reserve Y3+ / Binance Earn reserve Y3+ / prop firm trading capital channel 特例）。`monetization-demand-test-spec.md` superseded marker land 2026-05-25；v5.5 single product 定位對齊。Y1 末 evidence packet 只 evaluate Bybit Copy Trading per ADR-0030 4-gate。|
| AMD-2026-05-25-02 | v5.5 §0 changelog · ADR-0030 (Copy Trading 4-gate evidence) · ADR-0006/0033 (Bybit/Binance venue scope) · ADR-0040 (Multi-Venue Gate) · AMD-2026-05-25-01 (Commercialization Boundary paired) · v5.4 §2/§3/§10 (superseded) | `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md` | 2026-05-25 (operator approved 2026-05-27) | **Active** — v5.5 Bot Positioning + Capital Structure Formalization。Decision 1 = OpenClaw / 玄衡 是**完整 quant bot 單一產品**，主帳承載全部 strategies（含 C10 spot+perp funding harvest / C13 options VRP multi-leg 等 Bybit Copy Trading 不可 copy 子集），Copy Trading 是後續可選 monetization channel 非平行 product line。Decision 2 = Y1 100% 主帳 $7,500 active + Off-exchange $2,500 (Revolut+Wise 3-4% APR)；副帳 $0 Y1；Y2+ 副帳 enable 條件 = ADR-0030 4-gate + 本 AMD §4.2 Gate 5 Moat (reverse-snipe defense + simulator >95% + anti-snipe + Master Trader API + ranking dashboard) 全 5 gate PASS。Supersedes v5.4 §2 主帳$8.5k+副帳$1.5k / §3 Strategy Lab+Copy Trading dual product framing / §10 Master Trader Cadet-Bronze-Silver-Gold immediate Sprint 1 setup（Cadet/Bronze/Silver/Gold tier ladder 全部 defer to Y2+ Conditional Enable phase）。Decision 3 = Zero new engineering work；v5.5/v5.6/v5.7/v5.8 已對齊。|
| AMD-2026-06-29-01 | ADR-0006 (Bybit-only baseline) · ADR-0033/0040 (registered non-Bybit exception pattern) · ADR-0048 (IBKR stock/ETF paper/shadow lane) · TODO IBKR Phase 0/1 gates | `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md` | 2026-06-29 | **Active** — IBKR `stock_etf_cash` paper/shadow research lane boundary。Bybit remains the only active live execution exchange；IBKR is limited to read-only / paper / shadow contracts under ADR-0048 and the Phase 0 named contract packet。Phase 2 immutable artifact candidates must embed validated secret-slot and API topology runtime evidence, and missing/mismatched evidence remains a first-contact blocker；feature flags alone cannot grant paper/live authority without validated secret/artifact/session/envelope evidence；paper lifecycle evidence is append-only and transition-validated before any future paper route；`audit.asset_lane_events_v1` now validates immutable cross-phase event references without writing audit rows or applying DDL；Phase 3 PASS_DAY / QUARANTINED_DAY evidence-clock checker semantics are source-defined but not started；Phase 3 scorecard input contracts validate cash ledger, cost model, benchmark, shadow fill, storage capacity, and derived-only bundle shape without importing fills or writing scorecards；Phase 4 GUI readiness is display-only and fail-closed through `/api/v1/stock-etf/readiness` with no POST/order/secret/contact/lane-selector authority；`gui_lane_contract_v1` now source-validates GET-only display, client lane state untrusted, route/cache/auth partition, stale-cache cross-lane denial, crypto tab and Decision Lease/risk regression evidence, and no IBKR contact/secret serialization；Phase 5 release packet contract is machine-checkable but source-only and still does not authorize release, paper-shadow clock start, connector runtime, tiny-live, or live；`tiny_live_adr_eligibility_v1` is a discussion-only contract and explicitly rejects tiny-live/live authorization values。Denies IBKR live/tiny-live/margin/short/options/CFD/transfer/account-management writes, Python broker write authority, GUI lane authority, and automatic promotion。|

---

## Active Specifications / 活躍規範

### State Machine Specifications (SM)

| Code | Name | Module | Status | Description |
|------|------|--------|--------|-------------|
| SM-01 | Authorization State Machine | authorization_state_machine.py | ✅ Active | 8 states, 16 transitions, fail-closed auth |
| SM-02 | Decision Lease State Machine | decision_lease_state_machine.py | ✅ Active | 9 states, TTL-based lease lifecycle |
| SM-03 | OMS / Execution State Machine | oms_state_machine.py / Rust execution lifecycle | ✅ Active | Formal execution object lifecycle: pending/approved/submitted/filled/completed plus cancel/reconcile/fail states |
| SM-04 | Risk Governor State Machine | risk_governor_state_machine.py | ✅ Active | 6-level risk escalation/de-escalation |
| SM-05 | Executor Shadow-Mode / Graduated Canary Runtime Policy | executor_config_cache.py / executor_agent.py / RiskConfig.executor | 🟡 Accepted / Source Implemented | Polling + fail-closed policy per AMD-2026-05-09-01；Option A 字面 by AMD-2026-05-09-02 §2 被 AMD-2026-05-09-03 修訂為 graduated canary，又由 AMD-2026-05-15-01 rebased to Stage 0R replay preflight + Stage 1 demo micro-canary；F-01 source implemented |

### Exchange Specifications (EX)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| EX-01 | Protection & Anti-Hunt | protective_order_manager.py, portfolio_risk_control.py | ✅ Active | Hard stops, ATR dynamic distance, correlation gates |
| EX-02 | OMS & Order Lifecycle | oms_state_machine.py | ✅ Active | 11-state order management with reconciliation gate |
| EX-03 | Control Plane / Operator Console Boundary | FastAPI Control Console / OpenClaw Control Console | ✅ Active | Operator control plane is a governed override/approval surface, not market/account/order/fill source of truth and not a trading write path |
| EX-04 | Reconciliation Engine | reconciliation_engine.py | ✅ Active | Paper vs. live/demo position consistency checks |
| EX-05 | Learning Tiers & Autonomy | learning_tier_gate.py | ✅ Active | L1-L5 analyst evolution with tier gates |
| EX-06 | Agent Conflict Arbitration | multi_agent_framework.py, market_regime.py | ✅ Active | Scout/Conductor pattern, fact/inference/hypothesis |
| EX-07 | Agent Data Access Control | governance_hub.py | ✅ Active | Cross-SM authorization and data flow control |

### Organization Document Specifications (DOC)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| DOC-01 | Core Risk Doctrine | protective_order_manager.py | ✅ Active | Hard stop-loss §5.9, position sizing, risk limits |
| DOC-02 | Scanning & Monitoring | scanner_rate_limiter.py | ✅ Active | 5-minute scan interval, rate limiting |
| DOC-03 | Market Regime Detection | market_regime.py | ✅ Active | Regime classification, confidence scoring |
| DOC-04 | Agent Learning Evolution | learning_tier_gate.py | ✅ Active | Tier advancement criteria, performance metrics |
| DOC-06 | Change Audit Log | change_audit_log.py | ✅ Active | Append-only JSONL, rotation, thread-safe |
| DOC-07 | Audit Persistence | audit_persistence.py | ✅ Active | JSONL audit trail, file rotation |
| DOC-08 | Incident Response | incident_event_model.py | ✅ Active | Incident classification, SM trigger integration |

### Live Gate Foundation Specifications (LG-X)

| Code | Name | Module(s) / SoT | Status | Description |
|------|------|------------------|--------|-------------|
| LG-X-01 | Demo / LiveDemo Evidence Window | TODO.md `W-C` / `P0-AGENT-2` / MAG-082 | 🟡 Active Evidence | Historical LG-1 stability evidence is currently reframed as the W-C MAG-082 Stage 2 demo/live_demo lineage window; it does not grant true-live authority |
| LG-X-02 | H0 Blocking Verification | TODO.md `P0-LG-1` / `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md` / Rust H0 hot path | 🔴 Active Gap | H0 blocking must be wired into the production decision path with metrics and fail-closed behavior; Python `H0_GATE` singleton is not the Rust hot path authority |
| LG-X-03 | Provider Pricing Binding | TODO.md `P0-LG-2` / `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg3_provider_pricing_binding_rfc.md` / AccountManager + healthcheck `[45]` | 🔴 Active Gap | Fee/pricing source must be bound, freshness-checked, and asserted before true live |
| LG-X-04 | Supervised-Live Gate | TODO.md `P0-LG-3` / `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg4_supervised_live_gate_rfc.md` | 🔴 Active Gap | Live authorization, lease, drawdown, revoke, and operator approval states must be explicit and tested before supervised true-live sessions |
| LG-X-05 | Constrained Autonomous Live | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg5_constrained_autonomous_live_rfc.md`<br>`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md`<br>`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md`<br>`docs/healthchecks/2026-05-02--lg5_health_checks.md` | 🟡 Design / Active Gap | Constrained autonomous live requires LG-X-02/03/04, positive edge decision, explicit autonomy envelope, Decision Lease TTL, live-cost re-evaluation, R-meta attribution guard, and reconstructable audit |

### Live Operational Prerequisites (OPS-X)

| Code | Name | Module(s) / SoT | Status | Description |
|------|------|------------------|--------|-------------|
| OPS-X-01 | Live Ops Foundation | TODO.md `P0-OPS-1..4` | 🔴 Active Gap | HTTPS/secure cookies, credential rotation, legal/ToS/geography, and first-day runbook are true-live prerequisites but are not LG-4 supervised-live state-machine specifications |

---

## Reference Documents (REF) / 參考規格文件（2026-04 補登）

> **REF-XX**：屬「規格性質」的長期參考文件（架構契約 / 設計規範 / 跨語言邊界 / Agent 行為規範）。
> 與 SM/EX/DOC 不同處：REF 通常為跨多模組的協調規格，無單一 implementing module。
> 路徑：`docs/references/` 或 `docs/architecture/`，所有檔遵循 `YYYY-MM-DD--<topic>.md` 命名。

| Code | Name | Path | Status | Description |
|------|------|------|--------|-------------|
| REF-01 | ARCH-RC1 Unified Config Contract | docs/references/2026-04-15--arch_rc1_unified_config_contract.md | ✅ Active | 3-Config + StrategyParams Rust 權威 / ArcSwap 熱重載 / 4 IPC 寫入面（2026-04-07 定稿） |
| REF-02 | Rust Migration V3-FINAL | docs/references/2026-04-03--rust_migration_v3_final.md | ✅ Active | Rust 遷移正式執行依據：32,500 行 / 14 週路線圖 / 分級浮點容差 / 四層測試（五角色三輪審查 21 修正） |
| REF-03 | Agent Cognitive Adaptation Spec V1 | docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md | 🟡 Draft | CognitiveModulator + OpportunityTracker + DreamEngine（五角色審查通過，Phase 1 並行組 B；CLAUDE.md §二 衍生「認知調製 ≠ 能力限制」實施準則） |
| REF-04 | ML/DL Learning Architecture V0.4 | docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md | ✅ Active | Teacher-Student + LightGBM + Optuna + 3 DL 場景（三方審查完成） |
| REF-05 | Bybit V5 API Reference (SSOT) | docs/references/2026-04-04--bybit_api_reference.md | ✅ Active | REST/WS 全端點速查 · V5 API 分類覆蓋 · 開發必讀（SSOT 標記 v1.1，2026-04-26 G9-01 路徑修正後） |
| REF-06 | Comprehensive Audit Template V1 | docs/references/2026-04-04--comprehensive_audit_template_v1.md | ✅ Active | L1/L2/L3 三級審計流程 · 5 路並行 9 角色 + DL/DB 專項 |
| REF-07 | Execution Plan V1 (Fusion Plan) | docs/references/2026-04-04--execution_plan_v1.md | ✅ Active | DB + ML/DL + 新聞 Agent 20 週路線圖 · Phase 0-6 詳細規格 |
| REF-08 | Math Implementation Notes | docs/references/2026-04-06--math_implementation_notes.md | ✅ Active | 數學實現方案彙編：LinUCB/風控公式/統計檢定/校準/shrinkage |
| REF-09 | Phase 4 Execution Plan V2 | docs/references/2026-04-06--phase4_execution_plan_v2.md | ✅ Active | 融合方案執行計劃 V2：Phase 4 更新版排期 |
| REF-10 | ARCH-RC1 1C-3 Scope | docs/references/2026-04-07--arch_rc1_1c3_scope.md | ✅ Active | ARCH-RC1 1C-3 範圍定義 |
| REF-11 | ARCH-RC1 1C-3A Gap Analysis | docs/references/2026-04-07--arch_rc1_1c3a_gap_analysis.md | ✅ Active | ARCH-RC1 1C-3A 缺口分析 |
| REF-12 | ARCH-RC1 1C-3C Reconciliation | docs/references/2026-04-07--arch_rc1_1c3c_recon.md | ✅ Active | ARCH-RC1 1C-3C 對賬設計 |
| REF-13 | Signal Diamond DB TODO | docs/references/2026-04-10--signal_diamond_db_todo.md | ✅ Active | 多引擎數據分離 5 Phase 規劃（Phase 1-4 ✅，Phase 5 待實施） |
| REF-14 | 3E-ARCH Three-Engine Parallel Plan V4 | docs/references/2026-04-11--three_engine_parallel_arch_plan.md | ✅ Implemented Historical Reference | 三引擎並行架構遷移計劃 v4：26 設計決策 · PM+PA+FA 三角色（已完成）。不是当前派工权威；当前 OpenClaw / Bybit-only / Decision Lease / promotion 语义以 `CLAUDE.md`、`TODO.md`、ADR/AMD 和最新 reports 为准。 |
| REF-15 | 3E-ARCH Session Execution Plan | docs/references/2026-04-11--3e_arch_session_execution_plan.md | ✅ Active | 3E-ARCH Session 執行計劃：8 工作日排期（已完成） |
| REF-16 | Dust-Frozen Position Manual Clear SOP | docs/references/2026-04-20--dust_frozen_position_manual_clear_procedure.md | ✅ Active | DUST-EVICTION-GAP-1 P1-8 設計背景 · Bybit GUI 三路線 · Live 前 pre-flight checklist |
| REF-17 | Cross-Platform Redeploy Dependencies | docs/references/2026-04-20--cross_platform_redeploy_dependencies.md | ✅ Active | Linux→macOS（Apple Silicon）冷裝清單 · brew/rustup/pip 步驟 · systemd↔launchd 差異 · HMAC 憑證重簽陷阱 |
| REF-18 | Model Canary Promotion Rules (Draft) | docs/references/2026-04-23--model_canary_promotion_rules_draft.md | 🟡 Draft | INFRA-PREBUILD-1 Part B Model Registry canary 狀態機 + Phase 晉升閾值 + Operator playbook（Phase 4 auto-promote cron 延後） |
| REF-19 | Reality-Calibrated Fast Replay Governance | docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md<br>中文：docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md | 🟡 Draft | Replay/MLDE/DreamEngine 邊界契約：Replay 是實驗環境與資料來源之一；ML/Dream 仍為 Agent 自我學習與策略/風控調參能力；禁止 replay 直接 live/demo mutation |
| REF-20 | Paper Replay Lab and Learning Surface Design | docs/references/2026-05-02--paper_replay_learning_surface_design.md<br>中文：docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md<br>★ SoT V3：docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md<br>Workplan V1：docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md | ⚠️ Active-with-Cold-Audit-Caveat | Paper Tab 原地升級為 Replay Lab；Learning 保持知識 cockpit 並新增 replay evidence / ML-Dream producer monitor；5-Agent 從 Learning 抽出為 read-only Agents Monitor。**2026-05-03 8-agent cold audit 揭 Wave 1-9 IMPL 是結構性 false positive**（runner 從未啟動 → vacuous truth）；Sprint 1 修 5 P0 critical security + 3 schema drift（commit edf33c0）；Sprint 2 補 §八 evidence trail + AMD-2026-05-03-01 Wave 7 IMPL/Deploy 2-stage gate（commits aa9343c + 5184990）；deploy 待 Sprint 3 Linux 實機（cargo --release replay_runner + 18 V### apply + 5 e2e smoke + Decision Lease retrofit AMD-2026-05-02-01）+ Sprint 4 14d gradient observation。詳 TODO P1-INFRA-3a-m + docs/CCAgentWorkSpace/{PA,E1,E2,E4}/workspace/reports/2026-05-03--ref20_sprint{1,2}_*.md |
| REF-21 | Full-Chain Replay Engine | docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md | 🟠 Revise / Blocked | Active V1.3 plan；provisional `/full-chain/prepare` endpoint default-OFF；R2/R3 前必過 subprocess deploy path、expanded write confinement、V057/V058/V059/V060 Linux PG dry-run、negative-edge fail-closed promotion FSM、SECURITY DEFINER metrics、Bybit SSOT URI/rate/IP policy、block bootstrap、survival/correlation/cost gates、baseline SLA、GUI V1.1；MLDE/DreamEngine 僅作 verified advisory / exploration consumer。 |

### Architecture Specifications

| Code | Name | Path | Status | Description |
|------|------|------|--------|-------------|
| ARCH-01 | Data Storage Architecture V1 | docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md | ✅ Active | PG + TimescaleDB · 8 Schema · 存儲精簡 97%（5.6→0.17 GB/day）· 冷存儲 NAS 策略 |
| ARCH-02 | OpenClaw Control Plane Repositioning | docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md | ✅ Active | OpenClaw is communication/control-plane/Gateway/proposal relay only, not trading conductor and not second GUI |
| ARCH-03 | Agent Decision Spine Architecture | docs/architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md<br>docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag030_agent_spine_rust_module_design.md | ✅ Active | Typed StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease/idempotency -> ExecutionReport lineage |
| ARCH-04 | Alpha Source Architecture Upgrade | docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md<br>docs/adr/0021-alpha-source-architecture-upgrade.md<br>docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md | 🟠 Proposed | R-1..R-5 architectural amendments (AlphaSurface Bundle / Strategist scope / Hypothesis Pipeline / Per-alpha-source Live Promotion / Spec-as-Code). operator partial accept: W-AUDIT-8a SPEC + W-AUDIT-9 graduated canary started. Supersedes LG-X-02..05 system-wide promotion design (baseline IMPL still required as substrate). |
| ARCH-05 | Alpha Tournament SSOT | docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md | ✅ Active / IMPL-PENDING | Sprint 2 profit-spine SSOT. Fills v5.8 implicit Alpha Tournament slot with required read order, candidate pool, fee-adjusted scoring, minimum evidence gates, Stage output lanes, role chain, and cross-document pointers. Does not grant trading authority or relax Stage/5-gate constraints. **狀態拆分（P1-16）**：source scaffold = done（`alpha_tournament/` package）；active = false（orchestrator 仍 stub）；Stage 0R evidence = pending；M11 Stage-A smoke cron = installed（liveness-only）；M11 Stage-B divergence output = pending（`replay_divergence_log=0`）。scaffold 落地非「mostly done」，Stage-A smoke 非 promotion/divergence evidence。 |
| ARCH-06 | Alpha-Edge Regime Evidence Governance | docs/adr/0047-alpha-edge-regime-evidence-governance.md<br>docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md | ✅ Active | Math-primary evidence governance for Alpha-Edge S1-Sx. Bull data is allowed but must be labeled; S4 is a global regime/falsification overlay; Bybit market endpoints are raw state inputs, not prediction; future news/X/Reddit agents are secondary context only. |

### Architecture Decision Records (ADR-0034 ~ ADR-0047)

> v5.8 13-module thesis Sprint 1A 系列 ADR：M1 LAL 起步 / M5/M12/M13 Y3+ trait stub / M8+M10 安全機制 / M9 A/B / M11 counterfactual replay / ContextDistiller v4 / M3/M6/M7 health+reward+decay / M4 hypothesis discovery / funding_arb V3 redesign slot；ADR-0047 追加 Alpha-Edge evidence governance。
>
> **註**：ADR-0001 ~ ADR-0033 直接索引於 `docs/adr/`（檔名即 ID），不在本 register 重複登錄；本表僅追蹤 ADR-0034+（v5.8 系列）。完整 ADR 清單見 `docs/adr/` 目錄與 `docs/README.md` 索引。

| Code | Name | Path | Status | Sprint Phase |
|------|------|------|--------|--------------|
| ADR-0034 | Decision Lease Layered Approval (LAL) | docs/adr/0034-decision-lease-layered-approval-lal.md | ✅ Active | Sprint 1A-β land |
| ADR-0035 | M5 Online Learning Interface Reserved | docs/adr/0035-m5-online-learning-interface-reserved.md | ✅ Active | Sprint 1A-δ |
| ADR-0036 | M8 Anomaly + M10 Tier D Blacklist | docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md | ✅ Active | Sprint 1A-修補 |
| ADR-0037 | M9 A/B Framework | docs/adr/0037-m9-ab-framework-and-statistical-methodology.md | ✅ Active | Sprint 1A-修補 |
| ADR-0038 | M11 Continuous Counterfactual Replay | docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md | ✅ Active | Sprint 1A-β land |
| ADR-0039 | M12 OrderRouter Trait + maker_fill_rate | docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md | ✅ Active | Sprint 1A-δ |
| ADR-0040 | M13 Multi-Venue Gate Y3+ | docs/adr/0040-multi-venue-gate-spec.md | ✅ Active | Sprint 1A-δ |
| ADR-0041 | ContextDistiller v4 + DOC-08 AI Cost Cap Amendment | docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md | ✅ Active | Sprint 1A-修補 |
| ADR-0042 | M3 Health Monitoring | docs/adr/0042-m3-health-monitoring.md | ✅ Active | Sprint 1A-γ |
| ADR-0043 | M6 Bayesian Reward Weight | docs/adr/0043-m6-bayesian-reward-weight.md | ✅ Active | Sprint 1A-γ |
| ADR-0044 | M7 Decay Enforced Single Authority | docs/adr/0044-m7-decay-enforced-single-authority.md | ✅ Active | Sprint 1A-γ |
| ADR-0045 | M4 Hypothesis Discovery Governance | docs/adr/0045-m4-hypothesis-discovery-governance.md | ✅ Active | Sprint 1A-ε |
| ADR-0046 | funding_arb V3 Redesign Slot (Basis Observation vs Execution Split) | docs/adr/0046-funding-arb-v3-redesign-slot.md | 🟠 Proposed | Sprint 1A-δ/ε（revive-gate placeholder per AMD-2026-05-26-01；decision TBD，未 Accepted） |
| ADR-0047 | Alpha-Edge Regime Evidence Governance | docs/adr/0047-alpha-edge-regime-evidence-governance.md | ✅ Active | Alpha-Edge S1-Sx evidence governance（bull data labeling / local trend-state classifier / narrative side-evidence boundary） |
| ADR-0048 | IBKR Stock/ETF Paper + Shadow Lane | docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md | ✅ Active | Accepts `stock_etf_cash` as an isolated IBKR read-only / paper / shadow research lane under Phase 0 named contracts; Phase 1 source foundation covers closed type/config/IPC fixture/source-only DDL, and Phase 2 source covers typed external-surface gate / allowlist / session attestation / redaction / rate-limit / audit / paper-attestation / Python no-write prerequisites, IPC pre-contact status visibility, immutable gate artifact validation, secret-slot/topology runtime evidence contracts, artifact rejection for missing/mismatched runtime evidence, feature-flag/secret/scoped-auth matrix validation, and paper lifecycle/event-log transition validation. Asset-lane audit event source covers immutable `audit.asset_lane_events_v1` references across gate/DQ/scorecard/release evidence, with hash-chain and redaction boundaries but no audit writer/runtime authority. Phase 3 source covers market-data provenance, frozen inputs, DQ/quarantine manifest, evidence-clock day checker contracts, and scorecard input validators for cash ledger / cost model / benchmark / shadow fill / storage capacity / derived-only bundle boundaries. Phase 4 GUI readiness covers a display-only console tab and fail-closed readiness endpoint, plus source validation for GET-only display, untrusted client lane state, no effect-capable surfaces, route/cache/auth partition, stale-cache cross-lane denial, and crypto Decision Lease/risk regression evidence. Phase 5 source covers release/shakedown packet validation, role signoff/hash requirements, forward-only evidence archive checks, and a default blocked template, without release/tiny-live/live authority. Tiny-live ADR eligibility source covers the discussion-only gate for a future ADR and rejects `tiny_live_authorized` / `live_authorized` decisions even with positive paper/shadow evidence. Bybit remains the only active live execution venue; IBKR contact still requires real secret/topology evidence plus immutable PASS artifact; IBKR live/tiny-live/margin/short/options/CFD/transfer remain denied. |

### v5.8 13-Module Thesis (M1 ~ M13)

> v5.8 13-module thesis：M1 LAL / M2 overlay / M3 health / M4 hypothesis discovery / M5 online learning stub / M6 reward / M7 decay / M8 anomaly / M9 A/B / M10 Tier D / M11 counterfactual replay / M12 order routing stub / M13 multi-venue stub。

| Code | Name | Sprint Phase | Status |
|------|------|--------------|--------|
| M1 | Decision Lease Layered Approval (LAL) | Sprint 1A-β DESIGN / Sprint 1A-ζ Track A IMPL prototype / Sprint 4+ full | 🟡 Design + Prototype |
| M2 | Overlay State Machine | Sprint 1A-γ DESIGN / Sprint 2+ IMPL | 🟡 Design |
| M3 | Self-monitoring + Auto-diagnostics + Health-aware Degradation | Sprint 1A-β DESIGN / Sprint 1A-ζ Track B IMPL prototype / Sprint 2 M3 metric emitter full | 🟡 Design + Prototype |
| M4 | Self-supervised Hypothesis Discovery | Sprint 1A-γ DESIGN / Sprint 2+ IMPL | 🟡 Design |
| M5 | Online Learning / Incremental Model Update (Y3+ stub) | Sprint 1A-δ Rust trait stub IMPL | 🟡 Trait Stub |
| M6 | Multi-objective Reward Function Tuning | Sprint 1A-β DESIGN / Sprint 3+ IMPL | 🟡 Design |
| M7 | Strategy Decay Detection + Auto-retirement (DECAY_ENFORCED single authority) | Sprint 1A-β DESIGN / Sprint 3+ IMPL | 🟡 Design |
| M8 | Anomaly Detection | Sprint 1A-γ DESIGN / Sprint 2+ IMPL | 🟡 Design |
| M9 | A/B Testing Framework | Sprint 1A-γ DESIGN / Sprint 2+ IMPL | 🟡 Design |
| M10 | Autonomous Discovery Pipeline (Tier D) | Sprint 1A-γ DESIGN / Sprint 3+ IMPL | 🟡 Design |
| M11 | Counterfactual Replay Automation | Sprint 1A-β DESIGN / Sprint 1A-ζ Track C IMPL prototype / Sprint 2+ full | 🟡 Design + Prototype |
| M12 | Adaptive Order Routing (Y3+ stub) | Sprint 1A-δ Rust trait stub IMPL | 🟡 Trait Stub |
| M13 | Multi-asset Class / Multi-venue Capacity (Y3+ stub) | Sprint 1A-δ Rust trait stub IMPL | 🟡 Trait Stub |

> **M11 狀態拆分（P1-16，2026-05-29 TW）**：Stage-A smoke cron
> `m11_replay_runner_daily_cron.sh`（`0 4 * * *`）= installed，僅作 `[48]`
> liveness heartbeat；Stage-B divergence output = pending（`replay.completed=0`
> / `replay_divergence_log=0`，divergence 未物化）。Stage-A smoke 心跳 **不是**
> promotion / divergence evidence，不得用於 Stage 0R / Stage 1 升級。

---

## Audit Catalog (AUDIT) / 審計報告目錄（2026-04 補登）

> **AUDIT-XX**：重大審計報告索引。涵蓋多角色聯合審計、合規審查、安全審計、ARCH 審查。
> register 不重複內容，僅追蹤審計與規範條目（SM/EX/DOC/REF）的對應關係，便於後續引用。
> 路徑：`docs/audits/`，所有檔遵循 `YYYY-MM-DD--<topic>.md` 命名。

| Code | Name | Path | Date | Cross-Reference |
|------|------|------|------|------------------|
| AUDIT-01 | Bilingual Comment Audit | docs/audits/2026-03-30--bilingual_comment_audit_report.md | 2026-03-30 | CLAUDE.md §七 雙語注釋規範 |
| AUDIT-02 | Bybit V5 API Infrastructure Audit | docs/audits/2026-04-04--bybit_api_infra_audit.md | 2026-04-04 | REF-05 / BB+E5 聯合審核 |
| AUDIT-03 | L3 Consolidated Remediation Report | docs/audits/2026-04-06--consolidated_remediation_report.md | 2026-04-06 | L3 414 findings → 63 tracker · 11 工作包 · R0-R3 整改記錄 |
| AUDIT-04 | E3 R6 Directive Applier Security Audit | docs/audits/2026-04-07--e3_r6_directive_applier_security_audit.md | 2026-04-07 | Phase 4 前置安全審查 |
| AUDIT-05 | Phase 4 Final Sign-off Audit | docs/audits/2026-04-07--phase4_final_signoff_audit.md | 2026-04-07 | Phase 4 最終驗收審計報告 |
| AUDIT-06 | E2 Review ARCH-RC1 1C-3 BBC | docs/audits/2026-04-08--e2_review_1c3_bbc.md | 2026-04-08 | REF-10 / ARCH-RC1 1C-3 Build-Before-Commit 驗收 |
| AUDIT-07 | DB R/W + ML Pipeline Full Audit | docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md | 2026-04-09 | Signal Diamond Phase 1 前置 |
| AUDIT-08 | 3E-ARCH E2 Multi-Role Review | docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md | 2026-04-11 | REF-14 / REF-15 · 9 角色並行 Phase A-F 全修驗證 |
| AUDIT-09 | 3E-ARCH Phase G Re-audit | docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md | 2026-04-11 | REF-14 · 9/9 PASS — 0 BLOCKER |
| AUDIT-10 | Full Program Chain Audit | docs/audits/2026-04-12--full_program_chain_audit.md | 2026-04-12 | 12 角色合併 · 58 findings（8 P0 · 17 P1 · 28 P2 · 5 P3） |
| AUDIT-11 | Full Audit Fix Plan (PM Confirmed) | docs/audits/2026-04-12--full_audit_fix_plan_pm_confirmed.md | 2026-04-12 | AUDIT-10 配套 · P0~P3 分級修復排期 + PM 簽核 |
| AUDIT-12 | TODO Refactor Audit (10-Agent) | docs/audits/2026-04-24--todo_refactor_audit.md | 2026-04-24 | 10 Agent 獨立 audit · PA FIX-PLAN（45 findings / 6 工作組 / 4 Wave）· PM Sign-off |
| AUDIT-13 | 2026-05-08 12-Agent Full Audit + PA Fix Plan | 2026-05-08--full_audit_fix_plan.md<br>docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md | 2026-05-08 | 12 audit reports -> 88 unique findings -> W-AUDIT-1..7；5 pending operator decisions；K-6 LG-5 reviewer stale finding disputed |

> **註**：早期審計（2026-04-05 L3 12 角色報告）位於 `docs/audits/2026-04-05--l3_comprehensive/` 子目錄；
> Phase 治理審計位於 `docs/governance_dev/audits/`（如 `2026-03-31--gap_analysis_287_specs.md`）。
> 各 Agent workspace audit 位於 `docs/CCAgentWorkSpace/<Agent>/workspace/reports/`，不在本表內。

---

## Specification Numbering Rules / 編號規則

- **SM-XX**: State Machine specifications (core governance automata)
- **EX-XX**: Exchange specifications (trading operations and integration)
- **DOC-XX**: Organization document specifications (policies and procedures)
- **LG-X-XX**: Live Gate foundation specifications, aligned to historical LG-1..LG-5 gates
- **OPS-X-XX**: Live operational prerequisites adjacent to, but not numbered as, LG-X state/gate specs
- **REF-XX**: Reference specifications (architecture contracts, design specs, cross-language boundaries; 2026-04 新增類別)
- **ARCH-XX**: Architecture specifications (system-level design documents; 2026-04 新增類別)
- **AUDIT-XX**: Audit catalog (major audit reports cross-referenced to SM/EX/DOC/REF; 2026-04 新增類別)
- **§** notation: Section references within a spec (e.g., "DOC-01 §5.9", "REF-01 §3")

---

## Cross-Reference Summary / 交叉引用摘要

| Metric | Count |
|--------|-------|
| Active SM/EX/DOC/LG-X specifications | 24 |
| Active OPS-X prerequisites | 1 |
| Reserved specifications | 0 |
| Active REF specifications | 19 |
| Active ARCH specifications | 5 |
| Active AUDIT entries | 13 |
| Total code references | 見代碼內 spec-tag grep（數量持續增加，不在此固定計數） |
| Implementing modules | 見各 spec row 對應模組（數量持續增加，不在此固定計數） |
| Test coverage | 持續增加；live 數字見 `TODO.md` runtime evidence（早期靜態值 2,308+ Rust lib tests 已過期，現 cargo workspace 約 3,600+ Rust lib tests + Python pytest，以 TODO 實測為準） |

> **計數註（去數字化）**：上表三項原為靜態硬編碼數字（335+ refs / 22 modules / 2,308+ tests），易隨開發 drift。現改為指向 live 來源（代碼 grep + `TODO.md`），避免 register 自帶過期數字誤導讀者估算治理面大小。如需快照數字，請註明 collection date 並以當日實測為準。

---

## How to Add New Specifications / 如何新增規範

1. Assign next available code in appropriate category (SM/EX/DOC/LG-X/OPS-X/REF/ARCH/AUDIT)
2. Create implementation module / document following naming convention
   - Code modules：`lowercase_snake_case.py` / `.rs`
   - Documents：`YYYY-MM-DD--<topic>.md`（中文描述優先）
3. Add spec code references in code comments (e.g., `# Per SM-XX §Y` / `// REF-XX`)
4. Create test file with matching name (test_module_name.py)
5. Add changelog entry in `docs/governance_dev/phase{N}_*/changelogs/` 或 `docs/CLAUDE_CHANGELOG.md`
6. Update this register **and** `docs/README.md` 索引

---

## Catch-up History / 補登歷史

| 日期 | 動作 | 範圍 |
|------|------|------|
| 2026-04-29 | TW catch-up（4 月補登） | 新增 REF-01~18（18 條 reference 規格）+ ARCH-01（架構規格）+ AUDIT-01~12（12 條主要審計索引）。新增 3 個編號類別：REF / ARCH / AUDIT。`Last Updated` 由 2026-03-30 → 2026-04-29。詳見 commit message 與 `docs/CCAgentWorkSpace/TW/memory.md` 同日記錄。 |

---

*OpenClaw / Bybit Governance Specification Register*
