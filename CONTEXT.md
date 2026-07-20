# 玄衡 · Arcane Equilibrium

Arcane Equilibrium is a Rust-core, Python-bridge agentic trading governance system that runs paper / demo / live pipelines as one process against Bybit, with a multi-agent decision loop gated by formal state machines (Decision Lease, Authorization, Risk Governor, OMS Execution).

This `CONTEXT.md` is the project's domain glossary. Every architectural suggestion, ADR, refactor, or review should use these terms exactly — don't substitute "service," "component," "module" (in the generic sense), or "API" when one of these names applies. Generic programming concepts (timeout, retry, lock, queue) are deliberately omitted — only Arcane Equilibrium / OpenClaw-specific terms belong here.

> **as-of 2026-07-18**（术语表，增量维护；术语随架构演进而更新，运行态与当前主线状态一律见 `TODO.md`。本 as-of 标记于 2026-07-18 文档审计补入）。

## Product naming

**玄衡 · Arcane Equilibrium**:
The formal project and product name after the 2026-05-06 soft rename. "玄衡" names the whole trading governance system: autonomous cognition, risk equilibrium, auditability, and bounded execution authority.
_Avoid_: using OpenClaw Bybit as the total project name in new docs.

**OpenClaw**:
The retained name for the OpenClaw Control Console, authenticated local `/api/v1/openclaw/*` read-only control/monitoring routes, Rust `openclaw_engine`, and existing runtime identifiers. The external OpenClaw Gateway was retired and removed on 2026-07-16.
_Avoid_: treating OpenClaw as the total project brand, Rust engine name target, or trading brain.

**Bybit**:
The sole exchange venue and the correct label for venue adapters, connector paths, API references, secrets slots, exchange endpoint behavior, and compliance notes.
_Avoid_: including Bybit in the formal product name unless discussing the venue adapter.

## Language

### Engine modes

**Paper mode**:
Fully simulated trading with synthetic fills, no exchange calls — used for strategy exploration and parameter coverage.
_Avoid_: simulation, backtest (REF-20 Replay Lab is a separate construct).

**Demo mode**:
Bybit demo endpoint trading with real API calls but Bybit play-money — primary source of truth for edge estimation.
_Avoid_: testnet (Bybit specifically calls this "demo"), sandbox.

**Live mode**:
Real Bybit Mainnet trading with real money — requires `OPENCLAW_ALLOW_MAINNET=1` plus full 5-gate authorization chain.
_Avoid_: production, real trading.

**LiveDemo**:
The Live code pipeline pointed at the Bybit demo endpoint — meets the full Live authorization standard (TTL, signing, governance gates) and is **never degraded** because the endpoint is non-mainnet.
_Avoid_: "live demo" (two words), treating it as a relaxed Live. Historical 43k DB rows tagged `engine_mode='live'` are actually LiveDemo.

**3E-ARCH**:
The three-engine architecture — paper / demo / live as one Rust binary spawning three pipelines with three independent risk-config TOML files.
_Avoid_: "multi-mode engine" (loses the "three independent configs" connotation).

**3-Config**:
The independent TOML/config ownership model for paper / demo / live. A setting
being safe in one engine mode does not imply the same value or authority in the
other two modes.
_Avoid_: "shared config" when the code path must respect per-mode authority.

### Alpha source taxonomy

**Alpha Surface Bundle**:
The proposed (ADR-0021 R-1) data-rich strategy input bundle: TA indicators + funding curve + basis curve + OI delta panel + orderflow + liquidation pulse + event alerts + sentiment panel. Replaces TickContext-only strategy interface.
_Avoid_: "context bundle" (loses alpha semantics), "feature vector" (suggests ML feature, not policy input).

**AlphaSourceTag**:
A declared dependency on a specific alpha source (TA1m, TA5m, FundingSkew, Basis, OIDeltaPanel, OrderflowImbalance, LiquidationCascade, EventDriven, CrossAsset). Every strategy must declare its alpha sources at registration; Strategy Registry rejects all-`[TA1m]` proposals without QC waiver.
_Avoid_: "feature tag" (ML-specific), "data source" (too generic).

**AlphaSourceRegistry**:
The proposed (ADR-0021 R-2) Python class tracking active / observing / deprecated / sunset alpha sources, used by Strategist Agent for inventory tracking and dynamic Sharpe-by-regime allocation.
_Avoid_: "strategy registry" (already overloaded).

**Hypothesis (governance object)**:
The proposed (ADR-0021 R-3) first-class governance object at parity with Decision Lease. Records statement / null hypothesis / evidence contract / experiment target / verdict / audit chain. Every new strategy / parameter / risk budget must have an originating Hypothesis. State machine: DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → PROMOTED / REJECTED / EXPIRED.
_Avoid_: "experiment" (loses governance weight), "test" (generic).

**Per-alpha-source Live Promotion Gate**:
The proposed (ADR-0021 R-4) replacement for "system-wide live_reserved" promotion model. LiveBudget(alpha_source_id, slice) allocates capital_cap_usd / max_concurrent_positions / max_drawdown_pct per alpha source. Each alpha source has independent promotion clock concurrent to others.
_Avoid_: "per-strategy live promotion" (alpha-source != strategy), "live budget" alone.

**Alpha Evidence Governance**:
The ADR-0047 evidence contract for Alpha-Edge S1-Sx. Promotion evidence must be math-primary and must report regime, breadth, freshness, survivorship, and execution realism. Bull-market data is allowed only when explicitly labeled; bull-only or stale-only positive results are not proof of durable alpha.
_Avoid_: "market narrative proof", "bull proof", "aggregate Sharpe proof" without evidence slices.

**Regime/Falsification Overlay**:
The S4/Sx cross-track layer that labels bull / range / bear / chop / high-vol and tests whether a candidate is a durable alpha or a regime bet. It consumes local math-first features from Bybit market data; it does not treat Bybit or narrative feeds as prediction oracles.
_Avoid_: "S4 bull alpha", "exchange prediction", "regime oracle".

**Narrative Side Evidence**:
News, X, Reddit, market-commentary, and event-summary inputs used only to annotate context or explain event risk. These feeds are inference/context, not primary strategy evidence, and cannot override quantitative gates.
_Avoid_: "sentiment signal" when it implies promotion authority, "news alpha proof".

**AEG (Alpha-Edge Evidence Program)**:
The post-pivot mainline (2026-05-31, ADR-0047 + AMD-2026-05-31-01) replacing the v5.8 autonomy sprint sequencing: AEG-S0 contracts → AEG-S1 foundation (V125 alpha storage + backfill) → AEG-S2 evidence automation (regime runner / breadth ladder / robustness matrix) → AEG-S3 alpha research (≤4 candidates in parallel) → AEG-S4 decision (CP-2). SSOT: `TODO.md` §2 + `docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`.
_Avoid_: "Sprint 1A-x" (superseded sequencing), "alpha sprint" (loses the evidence-governance contract), bare "S1/S2" without the AEG- prefix (collides with the S1-Sx research-track labels in ADR-0047).

**Gate-B listing probe**:
The isolated listing-capture probe (deployed `c1c017b0`, R-0 zero-leak) feeding the listing-fade candidate — currently the AEG-S3 main path. Probe output is capture evidence only; promotion still requires the full AEG robustness matrix.
_Avoid_: "listing collector" (production collector IMPL is gated separately), treating probe capture as promotion evidence.

### Autonomy expansion taxonomy (v5.8)

These 12 terms are added by v5.8 13-module autonomy expansion thesis (執行計畫 v5.8 + ADR-0034..0044 + AMD-2026-05-21-01). Every new prose discussing autonomy / health / decay / replay / A/B / scope governance must use these names exactly — do not collapse them into "tier," "gate," "stage," "level," or generic "approval."

> **2026-06-10 校準**：V5.8 alpha pivot（2026-05-31，AMD-2026-05-31-01 + ADR-0047）已凍結 M1/M2/M6/M8/M9 的 active-IMPL（M7 例外）；解凍 gate = 首個 net+ candidate 達 `stage0_ready`。本節 Sprint 1A-β/γ/δ/ε/ζ 分期隨之暫停——（2026-06-10 校準時的）主線轉為 Alpha-Edge（AEG）；當前 active 主線一律以 `TODO.md` 為準（§2 舊指針已過時，現為 Closed No-Repeat Markers）。詞條定義保留：它們仍是 ADR-0034..0044 的權威詞彙，供歷史文檔閱讀與解凍後使用。

**LAL (Layered Approval Lease)**:
The five-level approval depth ladder layered onto Decision Lease — LAL 0 (per-fill, always autonomous via existing Guardian) / LAL 1 (intra-strategy reparam, auto after Stage 4 + 30d stable) / LAL 2 (cross-strategy reweight, Advisory Y1 / Auto Y2 with gate) / LAL 3 (new strategy promotion, always operator approval) / LAL 4 (capital structure / venue change, always operator approval). LAL 0-4 是 M1 Decision Lease 的 approval depth 維度，與 AMD-2026-05-15-01 Stage 0R-4 是兩個正交維度，per ADR-0034 + D2 改名（v5.7 之前稱「Lease Tier 0-4」已棄用）。
_Avoid_: "Lease Tier" (字面碰撞舊命名), "Stage" (Stage 是 strategy lifecycle，LAL 是 approval depth), "approval level" (失去 lease 語意).

**DECAY_ENFORCED**:
The M7 strategy lifecycle state replacing legacy `STAGE_DEMOTED` per CR-7。觸發後 strategy live size 自動 scaled to 50% pending 14d observation window；14d 末 operator 必 click decision（RECOVER 重新升 25%、或 RETIRE 降至 0）；不可被 LAL Tier 4 manual override 跳過 14d × 50% 強制 SUSPENDED 階段。M7 是 single decay authority per ADR-0044；M11 replay divergence emit-only，不可直接觸發 demote。schema 對應 V113 `decay_action_level` 欄（ENUM 值 `'DECAY_ENFORCED'` 替換舊 `'STAGE_DEMOTED'`）。
_Avoid_: "STAGE_DEMOTED" (legacy 命名 per CR-7 字面碰撞), "stage demote" (混淆 Stage lifecycle), "decay tier" (M7 用 action level 而非 tier).

**Counterfactual Replay**:
The M11 nightly continuous validation system running all live strategies through replay engine with last 24h market data — divergence taxonomy 5-7 type (PnL divergence > $X / decision count divergence > Y / slippage divergence > Z bps / 額外 type per spec)。Data source 為 self-hosted PG `market.liquidations` 而非 Bybit historical API（per ADR-0038 Decision 1；避 Bybit historical API 退出風險）。Budget < 4h wall-clock per nightly run。輸出 `learning.replay_divergence_log` (V107 hypertable) + daily Slack quality report + 高 divergence → M3 HEALTH_WARN escalation。
_Avoid_: "replay" (alone), "backtest" (REF-20 Replay Lab 是另一構造), "what-if" (Dream Engine 才是 what-if 探索).

**9-cell ATR-vol × Funding state**:
The M8 / M10 Tier D regime taxonomy 替代 HMM / Markov-switching / GARCH 三類被 ADR-0036 永久禁用的 model family。3 × 3 grid = ATR vol percentile (low / mid / high) × funding sign (negative / neutral / positive) = 9 cells；每 cell 獨立 baseline + RV percentile + block bootstrap 推導 confidence interval。math-model-audit skill 已 ADR 級永久強化禁 HMM。
_Avoid_: "regime classifier" (太 generic), "vol regime" (失去 funding 維度), "HMM" / "Markov-switching" / "GARCH" (永久禁用 per ADR-0036).

**A/B Variant Cluster (4)**:
The M9 A/B testing framework 4-variant cluster taxonomy per ADR-0037：parameter variant（如 MA=20 vs MA=30）/ signal source variant（如 indicator-based vs orderflow-based entry）/ risk profile variant（如 1.5% vs 2.0% risk per trade）/ exit logic variant（如 entry-on-touch vs entry-on-close）。Assignment 用 trial_id hash deterministic reproducible + stratified by symbol/regime/time-of-day。Statistics 用 mSPRT (mSequential Probability Ratio Test) + early stopping + Bonferroni / FDR multiple comparison correction。Test 不可 promote variant to live 不經 operator approval + Stage gate（per AMD-2026-05-21-01 opt-in scope）。
_Avoid_: "A/B test" (alone), "variant" (alone), "split test" (失去 sequential testing 語意), "experiment" (Hypothesis 才是 governance object).

**Bayesian Reward Weight**:
The M6 reward function 5 λ tuning system per ADR-0043 — 5 λ = `λ_alpha`（alpha attribution）/ `λ_sharpe`（risk-adjusted return）/ `λ_max_dd`（max drawdown penalty）/ `λ_hit_rate`（win rate）/ `λ_capacity_used`（orderbook depth penalty）。Optimization 用 Gaussian Process (Matern 5/2 kernel) + Expected Improvement acquisition；monthly Bayesian opt run；Y2 auto-apply ≤ 30% weight change（per H-2 rollback cap）；> 30% change 必 operator confirm。weight bounds operator-set in Console。
_Avoid_: "reward tuning" (alone), "λ optimization" (失去 Bayesian methodology 語意), "weight calibration" (太 generic), "M6 Auto" (混淆 M6 Advisory vs Auto 階段).

**Cross-V### Dependency Graph**:
The V### sequencing graph 規範 Sprint 1A-β 必先 land 哪些 V### 再 Sprint 1A-γ 才能 land 後續 V### per CR-9 + E5 + MIT 共識。主要依賴鏈：V107 (M11) ← V103/V109/V113 / V108 (M9) ← V103 (共用 hypothesis schema) / V109 (M8) → V112 (M1 LAL anomaly→halt cross-ref) / V112 (M1 LAL) ← V113 (M7 reference for "no incident 90d" check) / V105 (M2 overlay) ← V107 (M11 state advance condition)。β → γ 不可重疊（per E5）；cross-ADR collision gate 走 Sprint 1A-ε single-thread。
_Avoid_: "V### roster" (失去 dependency 語意), "migration ordering" (太 generic), "schema sequence" (失去 cross-ref 語意).

**Protected vs Opt-in Scope**:
The AMD-2026-05-21-01 governance partition — **protected scope 6 條 (a-f)** 永遠不開放 auto path：(a) true-live kill 操作 / (b) signed authorization.json 簽發 / (c) `OPENCLAW_ALLOW_MAINNET=1` mainnet env 切換 / (d) Bybit retCode!=0 fail-closed 路徑 / (e) fake AI 寫入禁 / (f) paper promotion lane 重啟。**opt-in scope 8 條 (g-n)** 走 5 mitigation 機制：(g) M1 LAL 1+2 / (h) M2 enable / (i) M3 Tier 1+2 / (j) M4 DRAFT writeback / (k) M6 ≤30% weight change / (l) M7 demote / (m) M8 Y2 trigger / (n) M10 tier eval。LAL Tier 4 manual override 不可繞 protected scope。
_Avoid_: "auto scope" (失去 protected/opt-in 對立), "operator-only list" (太 generic), "permission tier" (混淆 LAL).

**Forbidden Algorithm Reverse Pattern**:
The V109 schema 雙重 (Guard A + Guard C) detection_method CHECK constraint 不可含 `hmm` / `markov_switching` / `garch` 任一字串，違反必 RAISE EXCEPTION per ADR-0036。這是 compile-time 強制 forbidden algorithm 不可寫入 anomaly detection schema；對應 M10 Tier D 也禁同類 model。math-model-audit skill 此 ADR 級永久強化。Schema-level enforcement 是 fail-closed first defense；application-level pattern miner 也必 grep 確認 0 hit `HMM / Markov / GARCH` 字串。
_Avoid_: "blacklist" (太 generic 失去 algorithm 語意), "禁用模型" (失去 ADR 強制力 + Guard CHECK 雙層強化), "HMM ban" (alone — 失去 Markov-switching + GARCH 完整 family).

**5-Gate Auto Path Inheritance**:
The v5.8 §11.5 hard invariant per CR-15 + E3 + CC audit — v5.8 引入 7 條 auto path 寫 live state（M1 LAL 1 intra-strategy reparam / M1 LAL 2 cross-strategy reweight Y2 / M2 overlay auto-disable / M3 auto-degradation / M6 weight ≤30% auto-apply / M7 auto-demote DECAY_ENFORCED / M10 capital tier activation eval），**任一條必經完整 5-gate fail-closed**（CLAUDE.md §四 hard boundaries：Python live_reserved + Operator role + `OPENCLAW_ALLOW_MAINNET=1` + valid secret slot + signed authorization.json）。任一 gate fail → 該 auto path **自動 fall-back to Advisory 模式**，不繞 gate 直寫。M4 DRAFT writeback Decision Lease 紀律相同（必經 lease + HMAC + ml-training-pattern-miner role + rate limit）。
_Avoid_: "auto path" (alone — 失去 5-gate 強制), "gate bypass" (反向反模式名稱), "fail-open" (永遠禁；任一 gate fail = fail-closed).

**Spike PASS/FAIL Verdict**:
The Sprint 1A-ζ governance gate output — 5 module spike（M1 LAL Tier 1 / M3 statistical detector / M6 Bayesian weight / M7 decay signal / M11 nightly replay）走 1.5 wall-clock week + 2-3 sub-agent 並行 + 60-90 hr engineering 後，PM verdict 三選一：(1) **PASS** = 5 module 全達 acceptance criteria → 進 Sprint 2 / (2) **FAIL (a) revise** = 部分 fail 但可修 → 加 1 週 revise + 再 verdict / (3) **FAIL (b) accept limited** = 部分 fail operator 接受降級 scope → 進 Sprint 2 with reduced module set / (4) **FAIL (c) defer first Live** = critical fail → 順移 Sprint 4 first Live 至 Sprint 5+。Spike phase 是 PM push back 2026-05-21 新增的 governance gate。
_Avoid_: "spike" (alone — 失去 PASS/FAIL verdict 語意), "prototype review" (太 generic 失去 module count + verdict 選項), "Sprint 1A-ζ gate" (失去 verdict 三選一 結構).

**Multi-Session Dual Write**:
2026-04-23 的歷史事故名：不同 session 對同一 Module 產出兩套 naming/
Implementation。現行 mitigation 不是自動 commit/fetch/memory log；依
`docs/agents/sub-agent-hygiene-sop.md` 綁 owned scope、保留 unrelated dirty diff、用
checkpoint/`role_fragment_v1` 交接，未知改動不 revert，直到 PM 依 Interface/evidence
仲裁。Commit/push/fetch 仍需當前 task 授權。
_Avoid_: "session race" (太 generic), "commit-first protocol" (已退役), "merge conflict" (失去多 session dual-write 的特定語意).

### Decision Lease state machine (SM-02)

**Decision Lease**:
A timed, revocable, scope-limited authorization wrapping a single trading intent. AI output never becomes an order — it becomes a Lease that must be activated, risk-approved, bridged, and consumed. Per-intent TTL 0.1–300s.
_Avoid_: lease (alone), intent token, trade ticket, signal.

**Feature flag**:
A named runtime or config switch that changes evidence collection, routing, or
behavior only inside its documented authority boundary. A feature flag is never
an operator sign-off, never a live authorization, and never a substitute for
MAG-082/083/084 evidence.
_Avoid_: treating a flag flip as a release decision.

**DRAFT**:
Lease draft formed by H5 / Strategist but not yet accepted by the Lease Control Plane; cannot bridge downstream.

**REGISTERED**:
Formally accepted as a control object but not yet in its active window — waiting on activation conditions.

**ACTIVE** (Lease):
Within effective window and may be evaluated by Risk Governor for downstream bridging; cannot self-execute or skip Risk Governor.

**BRIDGED**:
Formally handed off to the downstream governance chain (Risk Governor → Execution); does NOT mean risk approved or order placed.

**CONSUMED**:
Terminal — the bridged Lease has been fully consumed by the downstream execution lifecycle.

**REVOKED / EXPIRED / REJECTED** (Lease):
Three terminal failure states. REVOKED = formally cancelled, no revival. EXPIRED = TTL or condition timeout, no auto-extend. REJECTED = approval denied at draft.

**FROZEN** (Lease):
Temporarily frozen — cannot bridge during freeze; thaws back to a restricted state, never auto-active.

### Authorization state machine (SM-01)

**Authorization** (formal object):
A versioned, audited governance permission object stating what an Agent may do within a scope/phase/mode. Distinct from H0–H5 market judgment, Risk Governor verdicts, or Control Plane snapshots. Stored at `$OPENCLAW_SECRETS_DIR/live/authorization.json` with HMAC-SHA256 signing.
_Avoid_: permission, role, ACL.

**EarnedTrust T0/T1/T2/T3**:
The session-scope Authorization TTL ladder (24h–360h) governing how long a Live session runs before re-authorization. Complements Decision Lease (Lease = "may this single intent fire"; T0–T3 = "how long does the session live").

**Authorization states** (PENDING_APPROVAL / ACTIVE / RESTRICTED / FROZEN / REVOKED / EXPIRED / REJECTED):
RESTRICTED = scope shrunk vs ACTIVE (e.g. near-miss recovery window). REVOKED is terminal, not pause. Authorizations cannot silently auto-expand without versioned re-approval.

**GovernanceHub**:
The Python coordinator object that bundles SM-01 Authorization + SM-02 Lease + SM-04 Risk + EX-04 Reconciliation. Owns `acquire_lease()` / `release_lease()`.

**H0_GATE**:
The local <1ms deterministic kernel performing freshness / health / eligibility / risk-envelope checks before any AI layer runs. First non-bypassable gate; outputs PASS or NO; never generates ideas.
_Avoid_: prefilter, validator.

### Risk Governor state machine (SM-04)

**Risk Governor**:
The formal risk-control state machine — a versioned, auditable, replayable state object, not a config string or ad-hoc mode flag.
_Avoid_: risk module, risk engine.

**NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER**:
The five-step progressive de-risking ladder. Tightening is automatic; loosening requires explicit conditions and typically approval. CAUTIOUS = higher gates / more downsize. REDUCED = scope/symbol/strategy restriction. DEFENSIVE = reduce-only, no new risk. CIRCUIT_BREAKER = emergency stop, only protective actions allowed.

**MANUAL_REVIEW**:
Orthogonal state — system not fully halted but specific decisions blocked pending human review (used for novel anomalies, conflicting verdicts, recovery gates).

**near-miss**:
Formally recorded prior-to-incident risk signal that triggers RESTRICTED Authorization or CAUTIOUS→REDUCED escalation.

### OMS / Execution state machine (SM-03)

**Execution object**:
The in-flight process object for an action that the governance chain has allowed to proceed. Distinct from the Lease, the order fact, the fill fact, and the position fact.
_Avoid_: order, trade.

**PENDING → APPROVED → SUBMITTED → PARTIALLY_FILLED / FILLED → COMPLETED**:
Happy-path execution lifecycle. SUBMITTED ≠ filled; FILLED ≠ position closed; COMPLETED is the only formal closure.

**CANCEL_REQUESTED → CANCELLED**:
Cancellation pair — the request being sent does not equal cancellation confirmed.

**RECONCILING**:
Mandatory holding state when local execution view diverges from external truth; the system MUST enter RECONCILING rather than guess.

**FAILED / ABORTED**:
FAILED = a step failed and cannot close as success. ABORTED = governance-driven stop. Neither may auto-revert to APPROVED/SUBMITTED — a fresh Execution object is required.

### Architectural planes & seams

**Engine** (vs **Bridge**):
"Engine" = the Rust `openclaw_engine` binary owning paper / demo / live as one process. "Bridge" = the Python FastAPI Control API + GUI layer with read-only authority over engine state.
_Avoid_: calling the Python side "the engine."

**Hot path** (vs **Cold path**):
Hot path = Rust tick pipeline / IntentProcessor / governance gate (sub-ms SLA). Cold path = Python ML / learning / GUI / scheduled audits.

**Pipeline Slot**:
A late-injectable Rust component slot inside `ipc_server/slots.rs` (e.g. `HStateCacheSlot`, `CostEdgeAdvisorDbSlot`) — env-gated; coded but typically OFF.

**Control Plane / Operator Console** (EX-03):
The unified human-governance entry surface for observation, mode switching, approvals, freezes, recoveries — explicitly NOT a truth source for market/account/order/fill/position state, NOT a trading write path, NOT a strategy brain.
_Avoid_: GUI, dashboard, admin panel (these are *implementations* of the Control Plane).

**OpenClaw Control Console**:
The canonical GUI implementation of the Control Plane: the existing FastAPI console at `trade-core:8000/console`. It is the only operator trading GUI and exposes authenticated local system, governance, and 5-Agent read-only views.
_Avoid_: inventing a second trading console or restoring a retired external dashboard.

**OpenClaw Gateway (retired)**:
Historical external self-hosted communication/relay component. Its service, reverse proxy, remote-access endpoint, and GUI integration were removed on 2026-07-16 and are not part of the deployable architecture.
_Avoid_: describing it as active, restoring it from archived instructions, or confusing it with `openclaw_engine` and the local Control API.

**LG-X**:
The Live Gate foundation specification family aligned to the historical
LG-1..LG-5 gate sequence: evidence window, H0 blocking verification, provider
pricing binding, supervised-live gate, and constrained autonomous live.
Operational prerequisites such as HTTPS, credential rotation, legal/geography,
and first-day runbooks are tracked separately as OPS-X.
_Avoid_: treating LG-X as a single runtime gate.

**Gateway Agent (historical)**:
An LLM/session formerly hosted through the retired external OpenClaw Gateway. It is not an active runtime role. The retained local 5-Agent runtime remains inside TradeBot and follows its existing governance boundaries.
_Avoid_: presenting Gateway Agents as deployed or confusing them with the local 5-Agent runtime.

**Data Plane / Perception** (EX-07):
The external-data ingestion layer that tags every inflow with source, freshness, cognitive level, and quality dimensions; un-tagged inference may not enter the decision chain.
_Avoid_: market data layer, ingestion.

**Reconciliation** (EX-04):
The independent fact-governance layer that adjudicates consistency between local process view, sync-chain fact view, and exchange truth — designed to force the system to admit "unknown" rather than self-convince.
_Avoid_: sync, reconciler.

**Venue Adapter**:
The exchange adapter shim sitting between OMS/Execution and the exchange — not authoritative for any state.

### Truth-source ownership (DOC-05)

**Source of Truth (SoT)**:
The single formal fact source for a given object class; downstream may cache/project/derive but may not claim SoT status.
_Avoid_: master record.

**Primary Writer**:
The unique module/chain authorized to write or transition the formal state of an object.

**Advisory Writer**:
A module that may propose drafts, candidates, or suggestions but cannot become a Primary Writer (e.g. H1–H5 vs Lease lifecycle, Learning Plane vs live config).

**Forbidden Writer**:
A module explicitly prohibited from writing the formal state of an object (typically: GUI, Learning, H0–H5 against fact objects).

**Human Override Path**:
The formally controlled route by which a human Operator may act on an object — must use governance objects + audit trail, never direct-edit.

**Display layer reverse contamination** (DOC-05 §3.5):
The forbidden anti-pattern of letting GUI labels / front-end state / report aggregates write back into formal state objects.

### Multi-Agent runtime (EX-06)

**Operator**:
The single human supervisor (cloud@ncyu.me). Sets only global stop-loss / take-profit, batches confirmations, drives strategy evolution; everything else is Agent autonomy within P0/P1 hard bounds.

**Conductor** (local runtime role):
The local coordination role for Scout / Strategist / Guardian / Analyst / Executor. It is NOT a sixth Agent and is unrelated to the retired external OpenClaw Gateway. It coordinates local runtime agent lifecycle and arbitration inside the TradeBot stack.
_Avoid_: the retired Gateway, master agent.

**Local 5-Agent runtime**:
Scout / Strategist / Guardian / Analyst / Executor running inside TradeBot's FastAPI + PostgreSQL + Rust-engine-adjacent stack. This is the retained trading cognition layer and has no dependency on the retired external Gateway.
_Avoid_: moving these Agents into an external Gateway unless a future ADR explicitly authorizes and re-establishes that surface.

**Agent Decision Spine**:
The typed, durable lineage chain for trade-relevant decisions:
StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
Decision Lease / idempotency -> ExecutionReport -> AnalystInsight. It
supersedes free-text MessageBus traces for promotion evidence.
_Avoid_: using MessageBus rows alone as execution lineage proof.

**Scout Agent** (情報):
"Eyes and ears" — news search, event calendar, sentiment, exchange anomaly monitoring. Emits `intel_object` and `event_alert`; never produces trade signals or modifies risk parameters.

**Strategist Agent** (策略):
"Brain" — symbol selection, strategy matching, parameter optimization, portfolio allocation. Emits `trade_intent` and `portfolio_allocation`; may not bypass Guardian or H0.

**Guardian Agent** (風控):
"Safety officer" — owns P2 dynamic risk; has veto, downsize, downgrade, and circuit-breaker authority over Strategist; cannot loosen P0/P1.

**Analyst Agent** (進化):
"Evolution engine" — runs the observation/lesson/hypothesis/experiment/verdict pipeline + the L1–L5 maturity ladder. Can deploy paper experiments autonomously but cannot directly modify live config.

**Executor Agent** (執行):
The only Agent permitted to call exchange write APIs, and only when holding a valid Decision Lease; cannot generate its own intents.

**Cognitive Modulator**:
Pressure-response design pattern: under stress, Agents raise decision thresholds rather than disable capability. Virtual scarcity (energy / credits / internal currency) is explicitly rejected.
_Avoid_: throttle, rate-limiter.

**Conflict Arbitration** (EX-06 §2.3):
Formal rule that Guardian veto overrides Strategist proposals; Strategist may "appeal" via the learning pipeline but not by retry.

### Compute tiers & H-pipeline

**H0**:
Local deterministic judgment kernel — first non-bypassable gate; pure in-memory, sub-millisecond; only outputs PASS or NO; never generates ideas.

**H1–H5**:
The five-stage AI governance pipeline — Thought Gate / Budget Gate / Model Router / Governor / Cost Logger; reframed in DOC-02 V2 as Multi-Agent precursors mapped onto Strategist / Guardian / Analyst.

**L0 / L1 / L1.5 / L2** (compute tiers):
Cost-routed inference tiers. L0 = local deterministic (zero-cost, <1ms). L1 = local Ollama. L1.5 = low-cost cloud (Haiku + Perplexity). L2 = full cloud (Sonnet/Opus). Lowest-cost tier capable of the task wins; the Budget Gate (H2) approves tier BEFORE computation.

**Cognitive level** (data tag):
The mandatory `fact / inference / hypothesis` tag attached to every inflow; un-tagged inference may not enter decision chains.

**Four-layer search degradation**:
L0 cache → L1 local → L1.5 Perplexity → L2 full search; information retrieval always tries cheapest source first.

### Trading domain

**Edge**:
Expected per-trade net basis-points after fees and slippage — the system's primary survival metric.
_Avoid_: alpha, PnL (PnL is the realized aggregate, not edge).

**Cost Gate**:
Cost-versus-edge threshold blocking new fills when `cost_edge_ratio` exceeds the cap. Demo can be relaxed; Live is fail-closed.

**cost_edge_ratio**:
Ratio of AI inference cost (or holding cost) to expected trading edge — when ≥ 0.8 the system recommends closing positions.

**AI Attention Tax** (DOC-04 capability I):
Every open position consumes AI compute; the position is graded A–F by `cost_edge_ratio`, F-grade triggers auto-close review.

**Funding Arb (funding_arb)**:
A delta-neutral perpetual-funding-rate harvesting strategy; **已 retired（AMD-2026-05-26-01，2026-05-26 起 Retired closed）**——原因 QC math infeasibility + Bybit demo 缺 spot lending。regime-dormant 非永久 DOA；revive 参见 ADR-0046 funding v3 slot。

**Maker fill rate**:
% of fills hitting as maker (PostOnly TIF) — gate target ≥40% PASS / ≥60% fee-drop tier.

**Realized edge**:
Empirical net bps after fee per fill, aggregated over a window.

**Symbol**:
A single Bybit instrument (e.g. BTCUSDT, BUSDT) — the unit of strategy attention.

**Strategy**:
A code-defined trading rule set; current **4** = `grid_trading`, `ma_crossover`, `bb_breakout`, `bb_reversion`（`funding_arb` 已 retired per AMD-2026-05-26-01，原 5-textbook roster 缩为 4；见下 Funding Arb 词条）。

**Tick pipeline**:
The Rust hot-path pipeline (in `openclaw_engine`) fanning market ticks out to IntentProcessor, paper_state, governance, and stop_manager.

**IntentProcessor**:
Rust component converting strategy intents into orders; holds the `apply_fill` fee/slippage byte-equal logic for replay.

**StopManager**:
Rust component handling Hard / Trailing / Time stop and ATR-based dynamic position sizing.

**dust clear**:
The SOP for cleaning up sub-min-notional residual positions.

### Risk control framework (EX-01)

**P0 / P1 / P2 three-tier**:
P0 = product-family-specific hard limits (Operator-only). P1 = system-wide hard limits (Operator-only). P2 = Agent-adjustable parameters with `effective = min(P0 ?? P1, P1)`. Higher tiers always win; P2 may only tighten.

**Hard Stop / Soft Stop**:
Dual-layer adversarial stop architecture. Hard stop = absolute defense, P1-capped, never disabled. Soft stop = Agent-evaluated conditional stop, ATR + regime-adjusted.

**Stop concealment**:
Mandatory rule that stop orders are NEVER placed on the exchange order book — all stops are local tick()-triggered to defend against stop-hunting.

### Bybit-specific

**Mainnet**:
Bybit production endpoint — gated by `OPENCLAW_ALLOW_MAINNET=1`; current flow = 0 by design.

**PostOnly**:
Order TIF requiring the order to be a maker; if it would cross the book it's rejected. Drives `liquidity_role='maker'` fee accounting.

**IOC**:
Immediate-Or-Cancel TIF; produces taker fills.

**Funding rate**:
Periodic perpetual-swap payment between long and short holders — the source signal for `funding_arb`.

**Master / Sub account**:
Bybit account hierarchy; covered by the `bybit-policy-compliance` skill.

### Learning & replay

**MLDE** (ML Decision Engine):
Cold-path learning component; consumes `mlde_shadow_recommendations` filtered by `evidence_source_tier`.

**Dream Engine**:
Cold-path counterfactual / what-if exploration component — emits advisories, never commands.

**Shadow vs Live model**:
Shadow = model running in parallel for evaluation, no execution effect. Live = model whose output drives orders. Per principle #7, the two planes are isolated.

**Teacher–Student**:
The v0.4 ML/DL self-learning architecture — Teacher labels, Student trains; combined with LightGBM + Optuna + 3 DL.

**REF-20 Paper Replay Lab**:
The reality-calibrated fast-replay subsystem (Sprint A–D) for backtest evidence. Data tagged `evidence_source_tier='synthetic_replay'` is **non-training** by design.

**REF-19 Reality-Calibrated Fast Replay Governance**:
The governance boundary for replay as an experiment and evidence surface.
Replay may accelerate diagnostics and preflight evidence; it cannot directly
authorize demo/live mutation or true-live promotion.

**REF-21 Full-Chain Replay Engine**:
The full-chain replay foundation with dedicated `replay_runner`, preflight
coverage, scanner timeline, calibration overlays, and read-only advisory
surfaces. Remaining trust depends on empirical recorder history and calibration
maturity.

**evidence_source_tier**:
Column on `replay.simulated_fills` ∈ {`synthetic_replay`, `calibrated_replay`, `counterfactual_replay`} — only the latter two may feed MLDE / Dream / attribution writers.

**Learning Pipeline**:
The five-stage funnel: Observation → Lesson → Hypothesis → Experiment → Verdict.

**Strategy Incubation Pipeline**:
Idea → Design → Paper Deployment → Validation Gate → Live Promotion → Live Monitoring → Retirement. Paper deployment is autonomous; live promotion is gated.

**Validation Gate** (EX-05 §4):
The 5-criteria simultaneous gate for paper→live promotion: 4 weeks + 500 trades + positive net PnL + >30% win rate + Sharpe > 0.5.

**Cross-strategy transfer learning**:
Applying parameters / filters / regime knowledge / exit rules learned in one strategy to others; each transfer is a fresh hypothesis requiring fresh validation.

**Analyst Evolution L1–L5**:
Post-Trade Review → Pattern Discovery → Hypothesis & Experiment → Strategy Evolution → Meta-Learning; each level requires demonstrated competence at the prior one.

### Product family taxonomy (DOC-04 §3)

**Product family**:
Independent governance unit — `spot / margin / perp_linear / perp_inverse / options / other_derivatives`. Each progresses independently with its own P0 config.

**Capability Level Progression**:
`unsupported → observe_only → shadow_ready → demo_ready → live_guarded_ready → live_ready` — each promotion requires demonstrated competence.

### Reconciliation consistency states (EX-04)

**IN_SYNC / LAGGING / MISMATCH_DETECTED / STATE_UNKNOWN / MANUAL_REVIEW_REQUIRED**:
The five formal verdicts Reconciliation may emit. STATE_UNKNOWN is a valid "I don't know" outcome that must NOT be guess-resolved.

### Common governance terms

**audit_event**:
The append-only formal audit log entry — every state transition, override, and approval must emit one. Reports/GUI may not write audit results directly.

**reason_code**:
Required structured field on every governance action (mode change, lease freeze, restriction, etc.) — free text alone is insufficient.

**Lease TTL**:
Configurable expiry on every Decision Lease (0.1–300s); expiry is automatic and untouchable by GUI/Learning.

**IBKR live-capable vs active**:
For `stock_etf_cash`, AMD-2026-07-11-01 permits implementation of readonly,
paper, shadow, tiny-live, and live capability, including production transport
and lifecycle code. `live-capable` means the source/configuration can support a
mode while remaining inactive; it is not a login, connection, data request, or
order authorization. Real contact/effect requires a Rust-validated,
time-bounded `ibkr_activation_envelope_v1` binding lane/broker/environment/
operation, build SHA, account/session fingerprints, risk limits, Cost Gate,
Guardian, Decision Lease, Operator nonce, expiry/revocation, and kill-switch
epoch. Credentials or sessions never auto-activate. Missing external
credentials/session/entitlement/activation is `EXTERNAL_VERIFICATION_PENDING`.
Python and GUI are thin control-plane surfaces only; Rust remains sole order,
risk, and activation authority. Margin, short, options, CFD, transfer, and
account-management writes remain denied.

**Freshness ladder** (EX-07 §2.1):
`FRESH (<5m) / RECENT (5–30m) / STALE (30m–2h) / EXPIRED (>2h)` — STALE blocks new entries; EXPIRED forces CAUTIOUS mode.

### Operator workflow

**SSH bridge workflow**:
Pattern where the Mac Claude session is SSOT and triggers Linux runtime tasks via `ssh trade-core`; replaces synchronizing two parallel Claude sessions.

**Mac=dev / Linux=runtime split**:
Mac is read/write/RCA only; Engine + Python + Postgres run only on the Linux trade-core box. `engine: not_running` on Mac is expected.

**`restart_all.sh --rebuild`**:
The deploy command that rebuilds engine binary + PyO3 in one step (post 2026-04-14 semantics).

**18 Live blockers**:
The Operator-tracked panorama of remaining gaps before true Live trading — a historical PM construct from the 2026-04/05 era. Current open blockers live in `TODO.md` §1 (P0 queue); do not cite the original "18 / N unresolved" counts in new prose.

### Development-agent governance

**Development-Agent Governance Module**:
The deep repo module that owns four Interfaces for development sub-agents:
Registry, Context, Dispatch, and Closure. Its machine Interface is
`.codex/agent_registry_v1.json`; Claude/Codex/profile files are generated
platform Adapters, not independent authorities.

**Execution mode**:
One of Conductor, Investigator, Builder, or Verifier. PM/PA/E1/QC and other role
names are capability presets over these modes. Codex `default/explorer/worker`
is only runtime substrate and does not represent intelligence level.

**Hybrid execution DAG**:
A task-fact-derived workflow with mandatory safety/evidence edges and advisory
specialist nodes. It replaces fixed all-role chains while keeping independent
review/test/runtime/venue/acceptance edges when their surfaces are present.

**Task Execution Control**:
The internal Development-Agent Governance Implementation shared by Dispatch and
Closure. `finite` is the default and cannot schedule another turn;
`operator_loop` requires exact Operator opt-in. It compares semantic progress
without round/time/unrelated-repo noise, terminates unchanged work as
`BLOCKED_NO_DELTA`, selects only ACTIVE queue rows, and owns the writer-lease
Seam. It is not a daemon, runtime scheduler, or fifth public governance
Interface.

**Development writer lease**:
An exclusive, expiring, task/owner/branch-bound fencing token for one attached
non-main linked worktree. The filesystem Adapter stores it atomically under
Git's common dir; the in-memory Adapter exercises collision/expiry/release.
`git_loop_guard.py` validates an existing lease without acquiring or stealing
it. It is unrelated to the trading Decision Lease.

**Elastic context envelope**:
`target + quality reserve + review_at` planning guidance. It triggers expansion,
split, or escalation; it never truncates user scope, acceptance, hard stops, or
mandatory evidence.

**Governance evidence trust tier**:
One of `LOCAL_REPRODUCIBLE`, `ORCHESTRATOR_BOUND`, or
`PLATFORM_OR_EXTERNAL_ATTESTED`. The first proves locally recapturable bytes; the
second binds controller-known request/result provenance; the third attests
runtime, external-policy/outcome, or actual-usage facts. A self-digest proves
canonical integrity only, not producer authenticity.

**Workflow call/wave record**:
`workflow_call_record_v1` binds one requested role/node/model call to the exact
task contract, context artifact, dirty scope, focus, response schema, attempt/
retry lineage, native agent/node class/permission, DAG predecessors/topological
wave, producer generation, time, and parsed-result digest. Its canonical call manifest is
closed by `workflow_wave_record_v1`, which accounts for every admitted node,
call/retry/null, result fragment, planned input lower bound, coverage debt, and
controller-overhead boundary. A closure orchestrator ledger must exact-cover all
captured waves; ghost, omitted, extra, or duplicate wave identity fails closed.

**Native development-agent binding**:
The Registry-derived pre-spawn tuple `role + native_agent + node_class + permission`.
PA and E4 have distinct writer and read-only verifier TOML identities. Codex
sandbox mode is an additional filesystem boundary, not authority for services,
private/authenticated external contact/effects, or private broker effects;
read-only Bash still needs exact native-identity command preflight.

**Public Web Read**:
Read-only evidence acquisition from an actually opened public URL. It requires
citation/capture provenance and never implies permission for authenticated,
private, transactional, messaging, or broker effects. Platform web-tool
availability is checked separately from this authority class.

**Private External Contact**:
Authenticated/private communication, transaction, broker session, or other
external effect. Development-Agent Governance has no closure-grade Adapter for
this class, so it routes fail-closed as an unsupported effect.

**Repository authority identity projection**:
A repository-backed authority value is the exact pinned Context content for
UTF-8/JSON, or the exact encoding+content wrapper for base64. A matching digest
cannot be paired with interpreted or substituted semantics; those use typed
`claim_inputs` or validated evidence. `command_capture_v2` derives native
identity, routed task and path scope from immutable Context, executes argv after
`--` with `shell=false`, streams bounded redacted previews plus exact output
digests, and binds task plus whole-repository generations. Its
`repository_policy_only` effect enforcement is not host network/no-contact
attestation; strong PASS remains trusted-local-replayed until a host verifier exists.

**External evidence capture** (`external_evidence_capture_v1`):
An out-of-band host-verified public HTTPS policy/outcome capture binding opened
URL, content/excerpt digest, selector, citation and bounded freshness. URL text,
self-report, generic repo evidence, expired/future records, or a structurally
valid capture without the host verifier remains evidence debt/INFERENCE.

**Repository change record** (`repository_change_record_v1`):
A task/role/node/scope-bound before/after pair of exact
`repository_capture_v1` generations. A snapshot or diff digest alone can prove
content integrity, but not mutation causality. Multiple admitted writers form one
canonical writer order with exactly one record per node. Their owned scopes are
non-empty/disjoint and writers are transitively serialized. Every record captures
both its owned mutation and task-wide generation, so adjacent receipts link exact
G0 -> G1 -> ... -> Gn digests; Gn and every owned after-state remain current.
One mixed-role record cannot satisfy multiple writers.

**Closure quality follow-up** (`closure_quality_followup_v1`):
An immutable-closure-digest longitudinal record for reopen, rework, false closure,
decision-changing findings, and realized value. Measured fields require a
caller-trusted `PLATFORM_OR_EXTERNAL_ATTESTED` record; absent telemetry remains
scheduled/unavailable and is never replaced with zero.

**Closure Packet** (`closure_packet_v1`):
The single task completion/evidence Interface. It separates work status, gate
verdict, and disposition and preserves immutable role dissent, evidence scope,
checks, side effects, consumption, and next action. Evidence classes do not
substitute: unit tests are not E2E outcomes, source capture is not runtime proof,
and actual consumption requires platform/external-attested telemetry.

**Broker Compatibility Interface**:
The shared broker review Seam. BB is its Bybit Adapter and IB is its IBKR Adapter;
each preserves broker-specific policy/session/effect semantics. Review never
performs broker contact. No development-agent broker contact/private-effect
Adapter currently emits a closure-admissible receipt; such routes remain blocked.

**Operations reviewer** (`OPS`):
Read-only development preset for preflight, rollback, postcheck, source/build
pin, observability, and incident RCA. The Deploy Adapter currently validates an
exact intent/environment contract only; effectful apply remains disabled until a
trusted reproducible local runtime probe exists, preserving maker/checker truth.

## Relationships

- A **Strategy** produces signals on a **Symbol**, which generate intents that flow into the Rust **IntentProcessor**.
- An intent is gated by **GovernanceHub**, which consults SM-01 **Authorization**, SM-04 **Risk Governor**, and SM-02 **Decision Lease** before the **IntentProcessor** emits an order.
- The **Decision Lease** is acquired per-intent (sub-second TTL); the **Authorization** lives at session scope (T0–T3 ladder, 24h–360h).
- The **Strategist** runs in cold-path Python and proposes parameter changes; the **Executor** is the only Agent permitted to call exchange write APIs, and only while holding a valid Lease.
- **Guardian** holds veto, downsize, and circuit-breaker authority over **Strategist**; **Strategist** may "appeal" only through the learning pipeline.
- The **Tick pipeline** (hot path, Rust) feeds prices to the **Strategy** layer; intents return via the Python **Bridge** and back into Rust via PyO3 IPC.
- A fill writes to `trading.fills` and (if cell-calibrated) to `replay.simulated_fills` for **REF-20** scoring.
- **MLDE** and **Dream Engine** consume `mlde_shadow_recommendations` filtered by `evidence_source_tier IN ('calibrated_replay','counterfactual_replay')` — they emit advisories, never commands.
- **Cost Gate** enforces `cost_edge_ratio < 0.8`; if violated, the **Cognitive Modulator** raises decision thresholds rather than disabling capability.
- **LiveDemo** uses the Live code pipeline against Bybit's demo endpoint — same Decision Lease + Authorization checks as Mainnet; only the `OPENCLAW_ALLOW_MAINNET=1` env requirement separates them.
- The **Operator** sets only the global stop-loss / take-profit envelope; Agents pick symbols, strategies, parameters, and timing within P0/P1 hard bounds.
- **18 Live blockers** are project-management gates tracked outside Decision Lease state — they are not runtime gates.
- The **Control Plane / GUI** is a **Forbidden Writer** for every fact object; it may only act on objects via the **Human Override Path** (versioned governance + audit_event).
- **Reconciliation**'s STATE_UNKNOWN verdict must enter **MANUAL_REVIEW**, not be guess-resolved.

## Flagged ambiguities

- **`engine_mode='live'` historical 43k rows are actually LiveDemo** — resolved: ML filters now use `engine_mode IN ('live','live_demo')`; new INSERTs write `'live_demo'` for the LiveDemo pipeline.
- **"Engine" can mean the Rust process OR the whole Python+Rust stack** — resolved: in this codebase, "engine" without qualification = the Rust `openclaw_engine` binary; the Python side is "Bridge" or "Control API." Note "Dream Engine" is a separate subsystem.
- **"Demo" means the engine_mode OR the Bybit endpoint** — resolved: `demo` (lowercase) = engine_mode; "Bybit demo endpoint" = the API target. **LiveDemo** always means "Live pipeline → Bybit demo endpoint."
- **Decision Lease deployment status** — Path A retrofit IMPL landed (commit `dbcf845b`); the router gate flag remains shadow/evidence semantics only (no true-live auth, no Executor order authority, no MAG-083/084). 2026-06 校準：SM end-state 已定為 Option 2（Rust 唯一權威，P5-SM）；step-i Rust (`a99bfa1d`) + E1b comparator (`e6aa5e37`) 完成，soak gate 因監測重設計暫停（2026-06-03 發現 Python shadow-hub 無 organic 流量時「0 divergence」屬空轉偽 pass），現狀以 `TODO.md` §0/§5 為準。
- **`replay.simulated_fills.evidence_source_tier='synthetic_replay'`** looks usable but is explicitly non-training data. Always filter `IN ('calibrated_replay','counterfactual_replay')` before feeding MLDE / Dream / attribution.
- **5-Agent runtime set (Scout / Strategist / Guardian / Analyst / Executor) vs development role presets (PM / FA / PA / CC / E1 / E2 / OPS / IB …)** — different vocabularies. The 5-Agent set is a runtime trading construct (DOC-01); development names are generated capability presets under the Development-Agent Governance Module. Neither Conductor nor a development preset is a sixth trading Agent.
- **`OPENCLAW_BASE_DIR` vs `OPENCLAW_SRV_ROOT`** — `SRV_ROOT` is a legacy alias; new code must use `OPENCLAW_BASE_DIR`. They do not fall back to each other; Mac dev must export both to the same value.
- **"Agent" overloaded** — can mean the 5 runtime trading Agents (Strategist etc.), the 20 generated development capability presets (E1, FA, PM, OPS, IB…), or a generic LLM agent. Always qualify: "Strategist Agent," "E1 sub-agent," "LLM agent." Never bare "Agent" in new prose.
- **Retired OpenClaw Gateway vs OpenClaw Control Console** — the external Gateway was removed on 2026-07-16; the Control Console remains the existing FastAPI GUI and the only trading console.
- **MessageBus vs Agent Decision Spine** — MessageBus is legacy/advisory local routing; the authoritative spine is typed persisted objects plus Decision Lease and Rust enforcement.
