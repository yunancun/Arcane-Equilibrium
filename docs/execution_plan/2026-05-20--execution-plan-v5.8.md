# 玄衡 · Arcane Equilibrium — Execution Plan v5.8 (13-Module Autonomy Expansion)

**v5.7 dispatch packet preserved + 13 autonomy modules design-at-initial / IMPL phased**

**日期**：2026-05-21
**Status**：DESIGN COMPLETE — supplements v5.7 dispatch packet; does NOT supersede v5.7 Sprint 1A
**Foundation**：v5.7 (15 rounds reviewer convergence + 12 CRITICAL prefix DONE 2026-05-21 PM signoff) + reviewer round-16 autonomy gap audit (13 modules) + operator 2026-05-21 directive (reject Claude push-back on M4/M5/M10/M12/M13; ADD ALL 13 modules)
**Supersedes**: none. v5.7 remains dispatch-of-record for Sprint 1A. v5.8 is **the autonomy track** layered onto v5.7.

---

## §0 Why v5.8 exists

Round-16 reviewer audit on v5.7 found:
- v5.7 Y1 末 autonomy ≈ 60% / Y2 ≈ 88% per PM autonomy verdict (`2026-05-21--v57_autonomy_verdict.md`)
- Y2 88% claim has **framework shells only** (Auto-Allocator activation gate, overlay enable gate, Copy Trading evidence gate) — substantive design missing for 13 modules required to actually realize Y2+ autonomy
- Claude initially pushed back on 5 modules as "NOT NEEDED at $10k retail / over-engineering"
- **Operator REJECTED that push-back** with explicit reasoning:
  1. **M2** must add — "Operator 可能忘記，可能犯錯。我們追求 APR 的最大自動型"
  2. **M4** must add — "我們做的是一個長期的項目，要保證長期後續會自動迭代更新"
  3. **M5** must add at low priority — "這是個後續開發的點"
  4. **M8/M9** design at initial stage even if IMPL delayed — "對後續接入更 friendly"
  5. **M10** must add — "我們不能假設資金真的是 10K"
  6. **M12/M13** even if delayed should do

v5.8 honors operator directive: **all 13 modules in scope**, phased per operator priorities. Push-back rescinded.

---

## §1 The 13 Modules — Roster + Priority + Phase

| # | Module | Role | Operator Priority | Initial Phase | Full-IMPL Phase |
|---|---|---|---|---|---|
| **M1** | Decision Lease autonomous proposal-to-execution loop | Closes per-strategy Advisory→Auto gate without operator click for proven trials | CRITICAL (was Claude's prior triage) | Sprint 1A DESIGN + Sprint 4 partial IMPL | Sprint 7-10 full |
| **M2** | Overlay enable / disable mechanism (macro + on-chain auto-trigger) | Per operator: APR max autonomy + safety net when operator forgets / errs | **ADD per operator** | Sprint 1A DESIGN + Sprint 3 hook | Y2 Q1 enable (post counterfactual verify) |
| **M3** | Self-monitoring / auto-diagnostics / health-aware degradation | Detect own failure modes, auto-degrade without operator alert lag | HIGH (was Claude's prior triage) | Sprint 1B DESIGN + Sprint 2 partial IMPL | Sprint 5-7 full |
| **M4** | Self-supervised hypothesis discovery (unsupervised pattern mining → preregistration draft) | Per operator: long-term self-iteration; bot proposes its own hypotheses for Cowork+operator review | **ADD per operator** | Sprint 1A schema + Sprint 2-3 stage 1 IMPL + Sprint 8 stage 2 (per §2 spec) | Y2 Q2-Q3 active |
| **M5** | Online learning / incremental model update (vs daily-batch retrain) | Per operator: low priority, future development point | **ADD per operator (LOW)** | Sprint 1A interface reservation only | Y3+ when justified |
| **M6** | Multi-objective reward function tuning / weight self-calibration | Auto-Allocator's reward weights (λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay) tune from outcomes | CRITICAL (Auto-Allocator gate dependency) | Sprint 1A DESIGN + Sprint 7 IMPL (Advisory) | Y2 active |
| **M7** | Strategy decay detection + retirement automation | Per-strategy alpha decay → auto Stage demote / retire | CRITICAL (Sprint 8 originally in v5.7) | Sprint 1A DESIGN + Sprint 8 IMPL | Sprint 8 active |
| **M8** | Anomaly detection (market regime shift + own behavior anomaly) | Per operator: design at initial stage for friendly future integration | **ADD per operator (DESIGN initial)** | Sprint 1A schema + Sprint 3 read-only logging | Y1 H2 → Y2 active trigger |
| **M9** | A/B testing framework (parameter / variant test infrastructure) | Per operator: design at initial stage for friendly future integration | **ADD per operator (DESIGN initial)** | Sprint 1A schema + Sprint 4 read-only logging | Y2 active gate |
| **M10** | Autonomous strategy / market / regime discovery pipeline | Per operator: don't assume always $10k; design for capital scaling | **ADD per operator** | Sprint 1A DESIGN + Sprint 8 Discovery Pipeline IMPL | Y2-Y3 scaling activation |
| **M11** | Counterfactual replay automation + continuous validation | Stage 0R replay infrastructure scaling: nightly counterfactual replay for all live strategies | CRITICAL (replay is approved evidence lane) | Sprint 1A DESIGN + Sprint 3 IMPL | Sprint 5+ continuous |
| **M12** | Adaptive order routing (venue / order type / slicing self-tuning) | Per operator: do even if delayed | **ADD per operator (delayed)** | Sprint 1A interface reservation + Sprint 6 IMPL | Y2 Q2 active |
| **M13** | Multi-asset class / multi-venue capacity (beyond Bybit perp+spot+options) | Per operator: do even if delayed; capital may scale | **ADD per operator (delayed)** | Sprint 1A interface reservation + Y1 末 spec | **Y3+ at earliest** phased per AUM (per ADR-0040 §Decision 1 supersede ADR-0033) |

**Module count by phase**:
- Sprint 1A DESIGN-or-IMPL-start: 13/13
- Sprint 1A-7 partial / full IMPL: M1, M3, M6, M7, M11 (the 5 CRITICAL/HIGH)
- Sprint 8-10 IMPL: M4, M7, M10, partial M8 (anomaly detector trigger), M11 continuous
- Y2 IMPL: M1 full auto, M2 enable, M6 Auto, M8 trigger, M9 gate, M10 active, M12 active
- Y3+ IMPL: M5, M13 full multi-asset

---

## §2 Module Specs (architecture-level; full PA dispatch in separate spec docs)

### M1 — Decision Lease Autonomous Proposal-to-Execution Loop

**Problem v5.7 had**: Every Allocator monthly proposal requires operator click via Console. Operator vacation / forgotten approval = paralyzed bot.

**v5.8 design**:
```
Lease Tier system (extends existing Decision Lease):
  Tier 0 (per-fill): always autonomous (existing Guardian)
  Tier 1 (intra-strategy reparam): autonomous after Stage 4 + 30d stable
  Tier 2 (cross-strategy reweight): Advisory Y1 / Auto Y2 with gate
  Tier 3 (new strategy promotion): always operator approval
  Tier 4 (capital structure / venue change): always operator approval

Auto-approval gate criteria (Tier 1+2 only):
  - Strategy/proposal has ≥ 30 prior Advisory approvals with > 80% operator yes-rate
  - No incident within proposal scope in last 90d
  - Risk envelope check passes (no parameter outside historical Stage 4 envelope)
  - Operator has set "Auto-Approve On" via Console toggle (default OFF)
  - Each auto-approval emits Slack/email + Console notification (post-hoc transparency)
  - Operator one-click undo within 24h (rollback to pre-proposal state)

Engineering scope:
  - Sprint 1A: Lease Tier schema + ADR-0034 (60-80 hr)
  - Sprint 4: Tier 1 IMPL (per-strategy reparam after stable) (40-60 hr)
  - Sprint 7-8: Tier 2 IMPL (Advisory + auto-eligibility tracking) (50-70 hr)
  - Y2: Tier 2 auto-execution enable (gate + monitoring) (30-50 hr)
```

**Operator forgetfulness mitigation**: Even Tier 2 Auto requires operator opt-in via Console toggle. Default-OFF means "operator forgot to enable" = system falls back to v5.7 Advisory (safe degradation, not paralysis — Advisory proposals queue + 30-day SLA escalation alert).

### M2 — Overlay Enable / Disable Mechanism

**Problem v5.7 had**: Macro + on-chain overlays are counterfactual-only Y1; Y2 enable requires operator decision but no mechanism for auto-enable when evidence passes threshold.

**v5.8 design**:
```
Overlay state machine:
  STATE_COUNTERFACTUAL_ONLY (Y1 default)
    → STATE_SHADOW_TRIGGER (counterfactual t-stat ≥ 1.5, sample ≥ 30 events)
    → STATE_ADVISORY_TRIGGER (shadow 60d no false-positive, Allocator proposes)
    → STATE_PRODUCTION_TRIGGER (operator approve once, then auto-maintained)
    → STATE_DISABLED_AUTO (any: Sharpe collapse / regime change anomaly / drawdown breach)

Auto-disable triggers (no operator click needed):
  - Overlay-attributed PnL has 30d Sharpe < 0 AND counterfactual diverges from production
  - Regime change anomaly (M8) flags + overlay-affected strategies show coupled drawdown
  - Macro event prediction false-positive > 3 in 90d (FOMC predicted halt but no impact)
  - Operator inactivity > 60d (failsafe: auto-rollback overlay to ADVISORY)

Auto-enable trigger (Y2 only, operator opted in via Console):
  - Counterfactual t-stat ≥ 1.5 sustained 60d
  - Sample size ≥ 30 events
  - No regime shift flagged in test window
  - Allocator proposal approval rate > 80% in last 6 mo

Engineering scope:
  - Sprint 1A: Overlay state machine schema + state transition log table (V105) (40-60 hr)
  - Sprint 3: Counterfactual logger hook into state (already in v5.7 §5; +10 hr)
  - Sprint 8-10: Auto-disable trigger IMPL (90 d after first counterfactual data) (40-60 hr)
  - Y2 Q1: Auto-enable evaluation framework IMPL (30-50 hr)
```

**Operator forgetfulness mitigation**: Auto-disable is always-on (does not require operator opt-in). Auto-enable requires Console toggle opt-in. So worst case "operator forgot" = overlay stays in safer state.

### M3 — Self-Monitoring / Auto-Diagnostics / Health-Aware Degradation

**Problem v5.7 had**: Healthcheck system exists but downstream auto-degradation logic is partial. Currently retCode!=0 fails closed per operation; no system-level degradation (e.g., "WS latency spike → reduce order rate" or "DB write backlog → pause non-essential strategies").

**v5.8 design**:
```
Health domains tracked:
  - Exchange WS latency p95 / dropout rate
  - REST API success rate / retry rate
  - DB write backlog (rows queued > threshold)
  - Disk usage (audit log growth)
  - Engine memory / CPU
  - Strategy-level: fill rate vs intent rate, slippage trend, decision lease grant rate

Auto-degradation responses (graduated):
  HEALTH_NORMAL → no action
  HEALTH_WARN → emit alert, no behavior change
  HEALTH_DEGRADED → throttle non-critical strategies (Tier 1 reparam halted, only Stage 4 continues)
  HEALTH_CRITICAL → halt new orders, drain existing positions per existing kill criteria
  HEALTH_CATASTROPHIC → existing kill criteria (portfolio cum loss > $3,000) triggers

Engineering scope:
  - Sprint 1B: Health domain schema + health_observations table (V106) (40-60 hr)
  - Sprint 2: per-domain probes (extend existing watchdog) (60-80 hr)
  - Sprint 5: Auto-degradation triggers (Tier 1 + 2 halt logic) (40-60 hr)
  - Sprint 7: Recovery / auto-restore logic (40-60 hr)
```

**Status**: HIGH (was Claude prior triage) — fills the gap between "per-operation fail-closed" and "5-gate kill". v5.7's existing healthcheck is observational; v5.8 makes it actionable.

### M4 — Self-Supervised Hypothesis Discovery

**Problem v5.7 had**: Sprint 8 Discovery Pipeline = operator + Cowork monthly review. Bot does not propose its own hypotheses; it just records preregistration of operator-proposed ones.

**v5.8 design** (per operator: long-term self-iteration):
```
Self-supervised pipeline:
  1. Ingestion: market.kline / trading.fills / market.liquidations / market.funding / token unlocks
  2. Pattern miner:
     - Statistical: rolling cross-correlation between asset features and forward returns
     - Temporal: event-window analysis (unlock / FOMC / liquidation cascade / large funding flip)
     - Cross-sectional: residual-return clustering, volatility regime clustering
  3. Hypothesis draft generator: pattern + supporting stats + suggested setup written to learning.hypotheses table (V103) in DRAFT state
  4. Hypothesis stays DRAFT until operator + Cowork review (per ADR-0024-lite, Cowork is operator-assistant, not autonomous L2)
  5. Approved DRAFT → preregistration → Alpha Tournament inclusion next sprint
  6. Rejected DRAFT → archived with rejection reason (feedback for miner)

Critical constraints (per ADR-0024-lite + 16 root principles):
  - Bot CAN propose hypotheses (write DRAFT row)
  - Bot CANNOT promote hypotheses (no auto Stage transition)
  - Bot CANNOT execute hypotheses (no auto trial activation)
  - Discovery output ≠ trading authority

Engineering scope:
  - Sprint 1A: hypothesis_drafts table + state machine (already partly in V103; extend +30 hr)
  - Sprint 2-3: Pattern miner stage 1 (cross-correlation + event-window) (80-120 hr)
  - Sprint 8: Pattern miner stage 2 (clustering + regime) (60-90 hr)
  - Sprint 10 / Y1 末: first 5-10 self-generated DRAFT hypotheses for operator review
  - Y2 Q2-Q3: full discovery loop active (DRAFT → review → preregister → Tournament)

Total: 170-240 hr across Sprint 1A → Y2 Q3
```

**Long-term value**: After 24 months of trading data, bot's own pattern miner should surface alphas that operator + Cowork manual review would miss. This is the "long-term auto-iterating project" framing operator stated.

### M5 — Online Learning / Incremental Model Update

**Per operator**: low priority, future development point.

**v5.8 design** (interface reservation only Sprint 1A; IMPL Y3+):
```
Existing ML (per memory project_ml_dl_learning_architecture):
  - LightGBM / Optuna / 3DL trained via daily cron
  - Models swapped at daily boundary

Online learning addition (Y3+ when justified):
  - Streaming update: model parameters update per N new fills (vs full daily retrain)
  - Drift detection: KL divergence on feature distribution between train and live
  - Auto-rollback: if live performance degrades vs daily-batch baseline, revert to batch

Interface reservation (Sprint 1A only):
  - ModelClient trait in Rust: get_predict() / get_predict_streaming() (latter unimplemented panic!)
  - learning.model_versions table includes streaming_enabled BOOL column (default FALSE)
  - ADR-0035 (proposed): online learning interface reserved, IMPL deferred Y3+
  - No engineering past interface stub

Engineering scope:
  - Sprint 1A: Interface stub + ADR-0035 (8-12 hr)
  - Y3+: actual IMPL (estimated 200-400 hr) when:
    (a) daily retrain proven insufficient (e.g., regime shift faster than daily granularity matters)
    (b) AUM > $50k (justify ML infra investment)
    (c) operator opt-in
```

**Why low priority is honest**: At $10k AUM with 5 strategy + daily ML retrain, online learning marginal gain ≤ 1-2% APR. Interface reservation costs 8-12 hr; full IMPL costs 200-400 hr. ROI-defer is correct.

### M6 — Multi-Objective Reward Function Tuning

**Problem v5.7 had**: v5.7 §7 Auto-Allocator uses reward function with manual-set weights (λ_dd, λ_tail, λ_turnover, λ_slippage, λ_decay). Manual weights don't self-calibrate from outcomes; reward function becomes stale as market regimes shift.

**v5.8 design**:
```
Reward weight calibration pipeline:
  1. Track each allocation decision's realized:
     - Net return contribution
     - DD contribution
     - 5%-tail contribution
     - Turnover cost
     - Slippage cost
     - Decay rate of allocated strategy
  2. Monthly reward-weight optimization:
     - Bayesian optimization over λ_dd, λ_tail, λ_turnover, λ_slippage, λ_decay
     - Objective: realized risk-adjusted return on last 6 mo
     - Constraints: weights within operator-set bounds (e.g., λ_dd ∈ [0.5, 5.0])
  3. Allocator uses new weights for next monthly proposal
  4. Operator sees weight change in proposal review (transparency)

Bounded autonomy:
  - Weight bounds set by operator in Console (initial: conservative ranges)
  - Weight change > 30% requires operator confirm (vs auto-apply)
  - Weight change rolled back if next-month Sharpe < baseline

Engineering scope:
  - Sprint 1A: reward_weight_history table + ADR (40-60 hr)
  - Sprint 7: Advisory weight optimization runs monthly (operator approves) (60-80 hr)
  - Y2: Auto-weight update (≤ 30% change) enabled (30-50 hr)

Total: 130-190 hr
```

### M7 — Strategy Decay Detection + Auto-Retirement

**Already in v5.7 §8 (Decay Detector) but underspecified**. v5.8 promotes to full spec:

```
Decay detection signals:
  - Rolling 30d Sharpe drops below strategy-specific threshold (per Alpha Tournament baseline)
  - Drawdown exceeds Stage 4 envelope max
  - N consecutive losing trades > 2σ historical max
  - Counterfactual replay (M11) shows strategy underperforming baseline by ≥ X bps

Auto-retirement state machine (per-strategy; renamed per ADR-0044 CR-7 to avoid Stage 0R-4 字面碰撞):
  STAGE_LIVE → DECAY_DETECTED (signal triggered)
  DECAY_DETECTED → DEMOTE_PROPOSED (Allocator generates proposal; was STAGE_DEMOTE_PROPOSED)
  DEMOTE_PROPOSED → DECAY_ENFORCED (operator approve OR Tier 1 auto-approve via M1; was STAGE_DEMOTED)
  DECAY_ENFORCED → live size scaled to 50% pending review (14d window)
  Review window (14 d) → either RECOVERY (re-promote NORMAL_LIVE) or RETIRED (size = 0)

Engineering scope:
  - Sprint 1A: decay_signals + strategy_lifecycle schema (40-60 hr)
  - Sprint 8: Decay detector IMPL + Demote state machine (60-80 hr)
  - Sprint 10: Auto-demote via M1 Tier 1 (Y1 末 first auto-demote allowed) (30-40 hr)

Total: 130-180 hr
```

### M8 — Anomaly Detection (DESIGN initial / IMPL phased)

**Per operator: design at initial stage even if IMPL delayed**.

**v5.8 design**:
```
Anomaly domains:
  Market regime anomaly:
    - Vol regime shift (Hurst exponent change, GARCH break)
    - Correlation structure break (eigendecomp shift)
    - Funding rate / basis dislocation
  Own behavior anomaly:
    - Strategy fill rate divergence from historical
    - Order rejection spike
    - Slippage outlier (single fill > 3σ historical)
    - Decision Lease grant rate anomaly

Detection methods:
  - Statistical: rolling z-score, ARIMA residual, isolation forest
  - ML (Y2+): autoencoder reconstruction error
  - Counterfactual (M11): live vs replay divergence

Response:
  - Y1 (read-only logging): anomalies written to learning.anomaly_events table; daily summary to operator
  - Y1 H2 (alerting): Slack notification on high-severity anomaly
  - Y2 (active trigger): high-severity anomaly → trigger M3 HEALTH_DEGRADED state
  - Y2+ (preemptive halt): correlation-break anomaly → halt new positions on coupled strategies

Engineering scope:
  - Sprint 1A: Schema (anomaly_events + severity taxonomy) + ADR-0036 (40-60 hr)  ← DESIGN done
  - Sprint 3: Statistical detector (rolling z, ARIMA) read-only (60-80 hr)
  - Y1 H2 (Sprint 8): Alerting + severity routing (30-50 hr)
  - Y2: Active trigger into M3 + ML detector (autoencoder) (80-120 hr)

DESIGN cost Sprint 1A: 40-60 hr (locked in V105/V106-range schema + ADR)
Total IMPL across Y1-Y2: 210-310 hr
```

**Why "DESIGN initial" matters**: Schema decisions made later are expensive to retrofit (audit trail migration, event back-fill). Locking schema in Sprint 1A even though detector waits costs 40-60 hr but saves 80-150 hr retrofit later.

### M9 — A/B Testing Framework (DESIGN initial / IMPL phased)

**Per operator: design at initial stage even if IMPL delayed**.

**v5.8 design**:
```
A/B test infrastructure:
  Test types:
    - Parameter variant (e.g., strategy uses MA=20 vs MA=30)
    - Sizing variant (e.g., 1.5% risk vs 2.0% risk per trade)
    - Trigger variant (e.g., entry on touch vs entry on close)
    - Overlay variant (e.g., with macro halt vs without)

  Assignment:
    - Random by trial_id hash (deterministic, reproducible)
    - Stratified by symbol / regime / time-of-day
    - Sample size pre-calculated per power analysis (operator-set min effect size)

  Statistics:
    - Sequential testing with mSPRT (msequential probability ratio test)
    - Early stopping for futility / efficacy
    - Multiple comparisons correction (Bonferroni / FDR)

  Governance:
    - All A/B tests are preregistered (M4 hypothesis schema reuse)
    - Test can degrade variant size (50% main / 25% A / 25% B max)
    - Test cannot promote variant to live without operator approval + Stage gate

Phased IMPL:
  - Sprint 1A: A/B schema (ab_tests + ab_assignments + ab_results) + ADR-0037 (50-70 hr)  ← DESIGN done
  - Sprint 4: Read-only A/B logging for already-live strategies (60-80 hr)
  - Sprint 7-8: Operator-approved manual A/B tests (Advisory variant adoption) (60-80 hr)
  - Y2: Auto-test scheduling + auto-promotion gate (80-120 hr)

DESIGN cost Sprint 1A: 50-70 hr
Total IMPL across Y1-Y2: 200-280 hr
```

### M10 — Autonomous Strategy / Market / Regime Discovery Pipeline

**Per operator: don't assume always $10k; design for capital scaling**.

**v5.8 design**:
```
Discovery pipeline tiers:
  Tier A (always on Y1): Strategy parameter discovery via Optuna + walk-forward (already exists)
  Tier B (Sprint 8+): Strategy variant discovery (M4 self-supervised pattern miner)
  Tier C (Y2+ when AUM > $25k): Market discovery (new symbol screening; cross-asset correlation)
  Tier D (Y2-Y3 when AUM > $50k): Regime discovery (auto-classify market regime + regime-specific strategy allocation)
  Tier E (Y3+ when AUM > $100k): Venue discovery (Binance perp, options, structured products evaluation)

Scaling capital path:
  $10k (Y1)                  : Tier A only
  $10-25k (Y1 末)             : Tier A + Tier B
  $25-50k (Y2)               : Tier A + B + C
  $50-100k (Y2-Y3, Copy Trading scaling): + Tier D
  > $100k (Y3+)              : + Tier E + M13 multi-asset

Engineering scope:
  - Sprint 1A: Discovery tier schema + capital-trigger config table (30-50 hr)
  - Sprint 2: Tier A productionization (cron + auto-walk-forward) (40-60 hr)
  - Sprint 8: Tier B activation hook (depends on M4) (built into M4 cost)
  - Y2: Tier C activation + new symbol screener (80-120 hr)
  - Y2-Y3: Tier D (regime auto-classify) (100-160 hr)
  - Y3+: Tier E (venue evaluation framework) (120-200 hr)

Initial DESIGN cost Sprint 1A: 30-50 hr
Active IMPL by capital tier: $400-600 total Y1-Y3
```

**Why this matters**: If Copy Trading kicks in Y2 and AUM goes to $30-50k, bot needs Tier C+D ready. Designing the capital-tier hooks in Sprint 1A lets growth happen without re-architecting.

### M11 — Counterfactual Replay Automation + Continuous Validation

**Already in v5.7 (Stage 0R replay) but as one-time gate**. v5.8 promotes to continuous:

```
Continuous counterfactual replay:
  Nightly job:
    1. Pull last 24h of market data
    2. Run all live strategies through replay engine with same data
    3. Compare replay-decided trades vs production-executed trades
    4. Flag divergences:
       - PnL divergence > $X
       - Decision count divergence > Y
       - Slippage divergence > Z bps

  Use cases:
    - Catch silent strategy drift (param hot-reloaded incorrectly)
    - Catch infra-induced behavioral change (latency spike altered fills)
    - Provide M8 anomaly detection input (own behavior anomaly)
    - Provide M7 decay detection input (strategy underperforming replay baseline)

  Output:
    - learning.replay_divergence_log table (V107)
    - Daily replay quality report → operator (Slack)
    - High-divergence flag → M3 HEALTH_WARN → review

Engineering scope:
  - Sprint 1A: Schema + ADR-0038 (40-60 hr)
  - Sprint 3: Nightly replay job (extend existing Stage 0R infra) (60-80 hr)
  - Sprint 5+: Hookups into M3, M7, M8 (40-60 hr)

Total: 140-200 hr
```

### M12 — Adaptive Order Routing (DESIGN initial / IMPL delayed)

**Per operator: do even if delayed**.

**v5.8 design**:
```
Routing dimensions:
  - Venue choice (Y1: Bybit only; **Y3+ at earliest**: Bybit / Binance perp where price-equivalent, per ADR-0040 §Decision 1)
  - Order type (Market / Limit / PostOnly maker / Conditional / FOK / IOC)
  - Slicing (single shot / TWAP / VWAP / iceberg / dark)
  - Time-in-force tuning

Adaptive logic:
  - Per-symbol routing profile learned from fill quality data
  - Maker-vs-taker decision based on:
    * Spread tightness vs strategy urgency
    * Recent rejection rate
    * Reverse-snipe defense (Q3 market-driven trigger insight: maker default; switch to taker only on confirmed signal)
  - Slice size learned from market impact regression

Bounds:
  - Operator-set max single-order $ size (initial: $500)
  - Operator-set max slippage tolerance per strategy
  - Auto-routing within bounds; outside-bounds requires operator confirm

Engineering scope:
  - Sprint 1A: OrderRouter trait interface + ADR-0039 (interface stub only) (20-30 hr)
  - Sprint 6: Maker-vs-taker adaptive logic IMPL (Bybit only) (80-120 hr)
  - Sprint 7-8: Slicing IMPL (TWAP for unlock SHORT entry, iceberg for pairs) (60-100 hr)
  - **Y3+ at earliest**: Cross-venue routing (when Binance trading enabled per ADR-0040 §Decision 1 supersede ADR-0033) (100-160 hr)

Initial DESIGN cost Sprint 1A: 20-30 hr
Total IMPL Y1-Y2: 240-380 hr
```

### M13 — Multi-Asset Class / Multi-Venue (DESIGN initial / IMPL delayed)

**Per operator: do even if delayed; capital may scale**.

**v5.8 design**:
```
Asset class expansion roadmap (per ADR-0040 §Decision 1 supersede ADR-0033 §Decision 2 timing):
  Y1: Bybit perp + Bybit spot (Earn) + Bybit options (C13 VRP)
  Y1-Y2: Binance market-data only (per ADR-0033 amendment; no trade)
  **Y3+ at earliest**: + Binance perp trade enable (per ADR-0040; was v5.7/v5.8 §2 draft "Y2"; BB push back + Bybit-only baseline)
  Y2-Y3: + structured products (Bybit Earn variants, options strategies beyond VRP)
  Y3+: + Binance options (when AUM justifies)
  Always declined: DEX / Hyperliquid (D1a per operator; ADR-0040 venue enum 根源拒絕)

Multi-asset abstractions:
  - AssetClass enum (Perp / Spot / Option / Earn / Structured)
  - Venue enum (BybitPerp / BybitSpot / BybitOption / BinancePerp / ...)
  - Cross-venue position aggregator (existing PositionAggregator extends)
  - Multi-venue Decision Lease + Guardian (extend to handle cross-venue netting)

Engineering scope:
  - Sprint 1A: AssetClass + Venue enums + ADR-0040 (interface stub only) (30-40 hr)
  - Y1 末: Multi-venue spec (when do we add Binance trade authority) (50-70 hr)
  - **Y3+ at earliest**: Binance perp trade enable (with Stage 0R replay using Binance data) (200-300 hr; per ADR-0040 §Decision 1 supersede)
  - Y3+: Additional asset classes per AUM (variable)

Initial DESIGN cost Sprint 1A: 30-40 hr
Total IMPL across Y2-Y3+: 250-400 hr
```

**Note on D1a constraint**: DEX / Hyperliquid remain not approved. M13 is Bybit + Binance only.

---

## §3 Sprint 1A Engineering Delta (vs v5.7)

v5.7 §8 Sprint 1A was 75-105 hr (PM arbitration 2 mid-range). v5.8 adds **DESIGN-only initial work for all 13 modules**:

| Module | Sprint 1A Initial Work | Hours |
|---|---|---|
| M1 Lease Tier | Schema + ADR-0034 | 60-80 |
| M2 Overlay state machine | Schema (V105) + state log | 40-60 |
| M3 Health domain | Schema (V106) + design | 40-60 |
| M4 Hypothesis discovery | Schema extension to V103 | 30-50 |
| M5 Online learning | Interface stub + ADR-0035 | 8-12 |
| M6 Reward weight history | Schema + ADR | 40-60 |
| M7 Decay signals | Schema + ADR | 40-60 |
| M8 Anomaly events | Schema + ADR-0036 | 40-60 |
| M9 A/B framework | Schema + ADR-0037 | 50-70 |
| M10 Discovery tier | Schema + capital trigger table | 30-50 |
| M11 Replay divergence log | Schema (V107) + ADR-0038 | 40-60 |
| M12 OrderRouter trait | Interface stub + ADR-0039 | 20-30 |
| M13 AssetClass/Venue enums | Interface stub + ADR-0040 | 30-40 |
| **Total v5.8 Sprint 1A add** | | **468-692 hr** |

**Sprint 1A total v5.8 = v5.7 75-105 + v5.8 468-692 = 543-797 hr**

This is **NOT executable in 1.5 weeks at 50-60% parallel sub-agent load**. v5.8 splits Sprint 1A into FIVE phases:

```
Sprint 1A-α (Week 0-1): v5.7 12-CRITICAL prefix DONE work + Sprint 1A v5.7 baseline 75-105 hr
   [Status: PM signed off 2026-05-21 per TODO §0.5]

Sprint 1A-β (Week 1-3): v5.8 CRITICAL module DESIGN
   M1, M3, M6, M7, M11 schemas + ADRs : 220-320 hr

Sprint 1A-γ (Week 3-5): v5.8 ADD-per-operator module DESIGN
   M2, M4, M8, M9, M10 schemas + ADRs : 190-290 hr

Sprint 1A-δ (Week 5-6): v5.8 delayed-IMPL module interface stubs
   M5, M12, M13 interface stubs + ADRs : 58-82 hr

Sprint 1A-ε (Week 6-7): Integration verify + cross-ADR consistency audit
   Audit pass + ADR cross-link + schema migration ordering : 40-60 hr
```

**Sprint 1A total v5.8 = ~7 weeks instead of 1.5 weeks**.

v5.7 Sprint 2+ shifts right by ~5.5 weeks. Y1 timeline becomes 44.5 weeks instead of 39 weeks.

---

## §3.5 PM 整合上修（per 14-Agent v5.8 Audit + PA Consolidation + Operator D1-D5）

**14 audit verdict 共識**：v5.8 §3 上方表 543-797 hr Sprint 1A + 2,780-3,930 hr Y1 系統性偏低 20-43%。原因 = 漏 GUI + TW + MIT spec 完整 work + A3 sign-off + governance amend buffer + AI cost。**operator 2026-05-21 D3 已批接受 +20-43% 工時 + 7-11w calendar 延後**。

### 3.5.1 Sprint 1A 真實工時上修（CR-13）

| 維度 | v5.8 §3 文本 | PM 整合真實 | 差距 |
|---|---|---|---|
| Sprint 1A engineering | 543-797 hr / 7w | **670-1,015 hr / 8.5w**（含 GUI/TW/MIT buffer）| +127-218 hr |
| Sprint 1A-β CRITICAL DESIGN | 220-320 hr | **310-460 hr**（含 MIT spec 90-140 hr buffer + TW 35-45 hr + GUI 9-11 hr + governance buffer）| +90-140 hr |
| Sprint 1A-γ ADD-per-operator DESIGN | 190-290 hr | **240-360 hr**（含 TW 35-45 hr + GUI 7-9 hr）| +50-70 hr |
| Sprint 1A-δ interface stubs | 58-82 hr | **75-110 hr**（含 TW 15-25 hr + GUI 2 hr）| +17-28 hr |
| Sprint 1A-ε integration verify | 40-60 hr | **86-126 hr**（含 TW 20-30 hr + GUI 6 hr + Monthly Review Wizard A3 16-24 hr + Lv3-4 modal helper 8-12 hr）| +46-66 hr |

### 3.5.2 維度缺漏補位（CR-11 GUI + CR-12 TW + MIT spec + A3 + AI cost）

| 缺漏項 | v5.8 §3 上方 | 補後 | 來源 |
|---|---|---|---|
| **GUI 工時 Y1**（CR-11）| 0 hr（漏） | **+261-374 hr**（Sprint 1A 24-28 hr + 1B-10 漸增；Console tab 歸屬 4 tab × 2-4 sub-section 不擴張 16 tab）| A3 5.21 audit |
| **TW 工時 Y1**（CR-12）| 0 hr（漏） | **+450-640 hr**（Sprint 1A 五階段 135-175 hr critical-path + 1B-10 ADR/spec/runbook 漸增；並行 dispatch with PA-MIT-CC tracks）| TW 5.21 audit |
| **MIT 9 V### spec doc**（CR-8）| 0 hr placeholder | **+90-140 hr**（V105-V113 仿 V103/V104 範式 full DDL；Sprint 1A-β/γ 內逐個推進）| MIT 5.21 audit |
| **Governance amend buffer**（4 ADR/AMD draft + 0034/0036/0037/0038/0040/0041 細節 + AMD-2026-05-21-01）| 0 hr | **+60-90 hr** | TW + CC + PM |
| **A3 sign-off Y1**（CR-11）| 0 hr | **+48-53 hr**（8 surface Lv 3-4 防誤觸 modal + cooldown 設計 + Monthly Review Wizard）| A3 5.21 audit |
| **AI LLM cost Y1**（CR-16）| 0 | **$505-865 / yr**（Y1 cap DOC-08 §4 $60/月 + ContextDistiller v4 800 token hard cap per ADR-0041） | AI-E 5.21 audit |
| **AI LLM cost Y2**（CR-16）| 0 | **$1,344-2,556 / yr**（超 DOC-08 §4 cap 1.9-3.5x；conditional opt-in raise to $150-200/月 per ADR-0041 LAL 4 approval） | AI-E 5.21 audit |

### 3.5.3 Sprint 1A 五階段真實 wall-clock

```
Sprint 1A-α  : W0-1.5  (DONE 2026-05-21 PM sign-off + 4 v5.7 follow-up D+1 land — V103 audit fields / V### re-number / PG conn / Earn 五角色 cross-ref)
Sprint 1A-β  : W1.5-3.5 (2 wall-clock weeks; 5-7 sub-agent 並行; M1 LAL / M3 / M6 / M7 / M11 CRITICAL DESIGN; V107/V112/V113/V106/V110 spec full DDL + 5 module spec doc + 6 runbook draft; ADR-0034 + ADR-0038 + ADR-0041 + AMD-2026-05-21-01 land)
Sprint 1A-γ  : W3.5-5.5 (2 wall-clock weeks; 5-7 sub-agent 並行; M2 / M4 / M8 / M9 / M10 ADD-per-operator DESIGN; V105/V108/V109/V111 spec full DDL + 5 module spec doc + 2 runbook; ADR-0036 / ADR-0037 / V103 EXTEND M4 + Cowork hybrid path land)
Sprint 1A-δ  : W5.5-6.5 (1 wall-clock week; 3-4 sub-agent 並行; M5 / M12 / M13 interface stubs; V114/V115/V116 reserve; ADR-0035 + ADR-0039 + ADR-0040 land; Mac CI 13-module cross-compile verify)
Sprint 1A-ε  : W6.5-8.5 (1.5-2 wall-clock weeks; single-thread cross-ADR + 並行 docs/index; cross-ADR consistency audit + schema migration ordering land + 12 V### dry-run SOP + docs/README.md index 補 + Monthly Review Wizard + Lv3-4 modal helper + CHANGELOG v5.7→v5.8 + CONTEXT.md 12 詞條)
Sprint 1A    : ~8.5w 真實 (v5.8 §3 上方表 7w + 1.5w cross-ADR collision risk slip)
```

### 3.5.4 並行 sub-agent ceiling

7 並行 + PM hands-on coordination 是 hard ceiling（per memory `project_multi_session_memory_race` 2026-04-23 事件 + v5.7 12 prefix DONE 證實）。1A-β/γ **5-7 並行**；1A-δ **3-4 並行**；1A-ε **single-thread cross-ADR + 並行 docs**。

### 3.5.5 PG Dry-Run Mandate + Cross-V### Dependency Graph（CR-9）

**PG dry-run mandate (per CLAUDE.md §Data, Migrations, And Validation + feedback_v_migration_pg_dry_run.md 2026-05-05 V055 教訓)**：

- 任何 V### migration 含 PG reflection / transaction control / schema assumption 必先 **Linux PG empirical dry-run** before IMPL sign-off
- `CREATE TABLE IF NOT EXISTS` 需 Guard A；type-sensitive `ADD COLUMN` 需 Guard B；hot-path indexes 需 Guard C
- Idempotency 必雙跑驗
- Engine restart 實測必含（per 2026-05-02 a19797d sqlx hash drift 教訓）

**Cross-V### dependency graph (V099-V116)**：

```
V099/V100 (v5.7 Track v3) — Sprint 1A-α DONE
V101/V102 (v5.7 Earn schema) — Sprint 1A-α DONE
V103/V104 (v5.7 hypotheses + preregistration) — Sprint 1A-α DONE + EXTEND for M4 (Sprint 1A-γ +30 hr)
   ↓
V105 (M2 overlay) — Sprint 1A-γ ← V107 (M11 reference for state advance condition)
V106 (M3 health) — Sprint 1A-β (hypertable 7d chunk + 7d compression + 90d retention 必)
V107 (M11 replay div) — Sprint 1A-β ← V103/V109/V113 (M7 source per CR-7 dedup) (hypertable 必)
V108 (M9 A/B) — Sprint 1A-γ ← V103 (share M4 hypothesis schema)
V109 (M8 anomaly) — Sprint 1A-γ → V112 (M1 LAL anomaly→halt cross-ref) (hypertable 必)
V110 (M6 reward weight) — Sprint 1A-β (regular table)
V111 (M10 discovery tier) — Sprint 1A-γ (regular table; Tier D 用 ATR-vol+funding NOT HMM/GARCH per ADR-0036)
V112 (M1 LAL) — Sprint 1A-β ← V113 (M7 reference for "no incident 90d" check)
V113 (M7 decay; DECAY_ENFORCED rename per CR-7) — Sprint 1A-β (hypertable 必; M7 是 single decay authority)
V114 (M5 online learning) — Sprint 1A-δ reserve frontmatter only
V115 (M12 order routing) — Sprint 1A-δ reserve frontmatter only
V116 (M13 asset/venue) — Sprint 1A-δ reserve frontmatter only
```

**順序限制**：Sprint 1A-β **必先 land** V106/V107/V110/V112/V113 → Sprint 1A-γ 才能 land V105/V108/V109/V111；β → γ 不可重疊（per E5 + MIT 共識）。Cross-ADR collision gate single-thread Sprint 1A-ε。

**Spec placeholder 已 land**（per CR-8 2026-05-21）：V105-V113 9 個 frontmatter + 7-section 大綱已 reserve（位於 `docs/execution_plan/2026-05-21--v###_*_schema_spec.md`）。Sprint 1A-β/γ 各週 sub-agent 接手補完整 DDL。

---

## §4 Y1 Total Engineering (v5.8)

| Sprint | Weeks (v5.7) | Weeks v5.8 §3 上方 | **Weeks PM 整合真實**（CR-13）| Focus | **Hours PM 整合真實**（CR-11+12+13） |
|---|---|---|---|---|---|
| 1A (α through ε) | 0-1.5 | 0-7 | **0-8.5** | v5.7 baseline + 13-module DESIGN + GUI + TW + MIT spec + AI cost | **720-1,090 hr**（v5.8 §3 上方 543-797 + GUI 24-28 + TW 135-175 + MIT spec 90-140 + governance buffer 60-90 + A3 sign-off 48-53）|
| 1B | 1.5-3 | 7-10 | **8.5-11.5** | v5.7 baseline 1B + early M3/M11 IMPL + ContextDistiller v4 IMPL | 165-220 |
| 2 | 4-7 | 10-13 | **11.5-14.5** | Alpha Tournament + M4 pattern miner stage 1 + M10 Tier A productionize + M8 read-only | 280-400 |
| 3 | 8-11 | 13-16 | **14.5-17.5** | Top-1 build + Stage 0 shadow + M11 nightly replay + M3 statistical detectors + M8 alerting prep | 280-380 |
| 4 | 12-15 | 16-19 | **17.5-20.5** | Top-1 LIVE $500 + Top-2 + Options Stack 1 + M1 LAL 1 IMPL + M9 read-only + ★ Sprint 4 首次 Live（P0-EDGE-1/LG-3/OPS-1..4 全 closure precondition） | 360-490 |
| 5 | 16-19 | 19-22 | **20.5-23.5** | Top-2 LIVE + Top-3 + Options Stack 2 + M3 auto-degradation + M11 hookups + LAL 1 auto-approve elig logging | 305-440 |
| 6 | 20-23 | 22-25 | **23.5-26.5** | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker + M12 maker_fill_rate_30d metric per ADR-0039 | 305-440 |
| 7 | 24-27 | 25-28 | **26.5-29.5** | Top-5 + Advisory Allocator + M1 LAL 2 + M6 Advisory reward weights + M9 manual A/B | 280-410 |
| 8 | 28-31 | 28-31 | **29.5-32.5** | Decay (M7 DECAY_ENFORCED) IMPL + M4 pattern miner stage 2 + M3 recovery + M8 alerting + LAL 1 auto-demote | 360-490 |
| 9 | 32-35 | 31-34 | **32.5-35.5** | Continue Advisory + Copy Infra build + M12 slicing IMPL | 255-360 |
| 10 | 36-39 | 34-37 | **35.5-38.5** | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M2/M8/M9 Y2 prep + M13 Y3+ spec | 190-260 |
| **Y1 buffer** | — | — | **38.5-44 (5.5w)** | cross-Sprint collision + cross-ADR re-amendment + 13 prerequisite emergent | 80-120 |
| **Y1 Total** | **39 wk** | **37-44 wk** | **44-55 wk** | | **3,500-5,200 hr** |

**Sprint 2 Alpha SSOT (2026-05-26 addendum)**：Sprint 2 `Alpha Tournament` 不再只是本表的 implicit slot；執行、候選池、評分、淘汰、Stage output 與治理讀取順序以 `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` 為準。任何後續 agent 觸碰 Sprint 2 alpha work 必先讀該 SSOT + `TODO.md` 最新 P0/P1 狀態。

**vs v5.7 1,275-1,710 hr**: v5.8 ~2.7-3.0x engineering（含補位完整工時）。

**vs v5.8 §3 上方文本 2,780-3,930 hr**: PM 整合上修 +26-32% / +7-11w。原因 = GUI 261-374 hr + TW 450-640 hr + MIT spec 90-140 hr + A3 sign-off 48-53 hr + governance amend 60-90 hr + AI cost reserve $1,344-2,556 Y2 + cross-Sprint collision buffer 80-120 hr。

**operator D3 已批接受**（2026-05-21）：Y1 calendar 44-55w + 工時 3,500-5,200 hr。

---

## §5 Capital-Tier IMPL Triggers (M10 / M13 Activation)

Per operator's "don't assume always $10k":

```
AUM trigger ladder:
  $10k  (Y1 start)                           : Sprint 1A-10 v5.8 scope
  $15-20k (Y1 末 if Copy Trading prep on)     : M4 active, M9 manual A/B active, M2 Y2 enable eval
  $20-30k (Y2 Q1-Q2)                         : Auto-Allocator active (M1 Tier 2 + M6 Auto), M8 active trigger, M11 mature
  $30-50k (Y2 Q2-Q4)                         : M10 Tier C (new symbol screening), M12 cross-venue routing
  $50-75k (Y3 Q1+ at earliest)               : M13 Binance perp trade enable (per ADR-0040 §Decision 1), M10 Tier D regime auto-classify
  $75-150k (Y3+)                             : M5 online learning IMPL, M10 Tier E venue evaluation
  > $150k (Y4+)                              : Full M13 multi-asset (Binance options, structured products)

Trigger logic:
  - 7-day moving AUM > threshold sustained 30 day → trigger eval
  - Operator confirms tier activation via Console
  - Activation initiates phased IMPL per module spec
  - De-activation possible if AUM drops sustained 90 day
```

This addresses operator's reject of "$10k forever" assumption. Architecture scales without re-design.

---

## §6 Honest Autonomy Outcomes (v5.8)

```
Y1 末 (W37-44 with v5.8 timeline):
  - 自主交易 (autonomous trading): 70% → 75% (M1 Tier 1 active, M7 auto-demote active)
  - 自主風控 (autonomous risk): 90% → 93% (M3 auto-degradation, M11 nightly replay catches drift)
  - 自主調整 (autonomous adjustment): 30% → 35% (M6 Advisory weight tuning, M9 manual A/B)
  - 自主學習 (self-learning): 50% → 60% (M4 pattern miner stage 2, M11 continuous validation)
  - Weighted: 60% → 66%

Y2 Q2 (Auto-Allocator activation + overlay enable, capital ~$25k):
  - 自主交易: 90% → 92% (M1 Tier 2 auto)
  - 自主風控: 95% → 96% (M8 active trigger, M11 mature)
  - 自主調整: 80% → 85% (M6 Auto weight, M2 overlay enable)
  - 自主學習: 85% → 88% (M4 active, M9 auto-gate, M10 Tier C)
  - Weighted: 88% → 90%

Y3 Q2 (multi-asset + M5 online learning, capital ~$75k):
  - 自主交易: 92% → 95%
  - 自主風控: 96% → 97%
  - 自主調整: 85% → 92% (M10 Tier D + Tier E, M12 cross-venue)
  - 自主學習: 88% → 95% (M5 streaming + M10 Tier E venue eval)
  - Weighted: 90% → 95%

"真正不需介入" time-point:
  v5.7 estimated: Y2 Q2-Q3 (~21-24 mo from Sprint 1A)
  v5.8 estimated: 
    - 90% autonomy at Y2 Q2-Q3 (same as v5.7 — Auto-Allocator gate is the binding constraint)
    - 95% autonomy at Y3 Q2 (~32 mo from Sprint 1A) — requires capital growth
```

**v5.8 does not accelerate Y2 90% target**. It does:
1. Make Y2 90% **substantively realizable** (not framework shells)
2. Provide capital-scaling roadmap so Y3 95% is reachable without re-architecture
3. Reduce operator forgetfulness risk (M2 auto-disable safety net, M3 auto-degradation, M1 default-OFF auto)
4. Enable long-term bot self-iteration (M4 self-supervised discovery)

---

## §7 Honest Income Outcomes (v5.8)

```
Y1: $300-550 (unchanged from v5.7 — module IMPL Y1 is mostly DESIGN + early hooks; no new strategies)

Y2 (with M2 overlay enabled if verified + M1 Tier 2 + M6 Auto):
  - Base (no overlay): $850-1,050 (same as v5.7)
  - With M2 overlay enabled: $1,050-1,350 (overlay verified +1-3% on $5,400)
  - With Copy Trading scaling (M13 prep not yet active): variable
  Total Y2: $1,050-1,350 if overlay verified, otherwise $850-1,050

Y3 (with M10 Tier C+D, M12 cross-venue, M9 auto-gate optimized):
  - Strategy diversity gain via M4 self-supervised: +2-4% on AUM
  - Cross-venue routing slippage save (M12): +0.5-1% on AUM
  - Regime auto-classify (M10 Tier D): +1-3% on AUM
  - Optimized weights (M6 Auto): +1-2% on AUM
  - Y3 APR estimate: 13-18% (vs v5.7 Y3 10-12% steady)

Y3 income on $25k Y2 末 AUM compounded:
  - 15% midpoint → $25k * 1.15 = $28.75k → +$3.75k Y3
  - With Copy Trading scaling pacing (per evidence gate): $30-50k AUM → 15% → $4.5-7.5k Y3 income

10-year compound (v5.8 honest):
  At 12% Y1-Y2 / 15% Y3+ sustained: $10k → $36-45k Y10
  At 15% Y1-Y2 / 17% Y3+ stretch (overlay + Copy Trading work): $10k → $52-70k Y10

vs v5.7 honest Y10: $25.9-31.1k
vs S&P passive: $21.6k

v5.8 advantage: long-term auto-iteration delivers compounding alpha gain via M4/M6/M10
```

These are honest. M4/M6/M10 alpha contributions are **conditional on actually working**; reviewer is right that they have uncertainty. v5.8 income range bottom (no module-derived alpha) = v5.7 Y3+ 10-12% sustained.

---

## §8 ADR Roster (v5.8 adds 7 new ADRs; 2026-05-25 V1→V5.8 drift audit adds 1 proposed)

| ADR | Topic | Status |
|---|---|---|
| 0034 | M1 Decision Lease Layered Approval (LAL) | Land 2026-05-21 |
| 0035 | M5 Online learning interface (reservation) | Land 2026-05-21 |
| 0036 | M8 Anomaly + M10 Tier D Model Blacklist (HMM/Markov/GARCH 永久禁) | Land 2026-05-21 |
| 0037 | M9 A/B testing framework + statistical methodology (mSPRT + Bonferroni) | Land 2026-05-21 |
| 0038 | M11 Continuous counterfactual replay + self-hosted PG | Land 2026-05-21 |
| 0039 | M12 OrderRouter trait + maker_fill_rate_30d metric | Land 2026-05-21 |
| 0040 | M13 Multi-Venue Gate Spec (Binance trade Y3+ at earliest) | Land 2026-05-21 |
| 0041 | ContextDistiller v4 + DOC-08 §4 AI cost cap amendment | Land 2026-05-21 |
| 0042 | M3 Single Health Authority | Land 2026-05-21 |
| 0043 | M6 Bayesian Reward Weight (GP Matern 5/2 + EI) | Land 2026-05-21 |
| 0044 | M7 Single Decay Authority + DECAY_ENFORCED FSM | Land 2026-05-21 |
| 0045 | M4 Hypothesis Discovery Governance | Reserved placeholder 2026-05-21 (full IMPL 待 Sprint 6+) |
| **0046** | **basis observation vs execution split (funding_arb scope)** | **PROPOSED 2026-05-25 per BB+QC spec; IMPL Sprint 1A-δ/ε 平行 land (24-30 hr)** |

Plus existing v5.7 lineage:
- 0030 Bybit Copy Trading evidence-gated (Y1末 4-gate)
- 0031 Framework Expansion (Earn + Macro + On-chain counterfactual)
- 0032 Bybit Earn Asset Movement Guardian
- 0033 ADR-0006 amendment (Bybit primary, Binance market-data Y1, DEX declined)

**Total ADR adds Sprint 1A**: 11 (4 from v5.7 + 7 from v5.8 batch 1; +4 from v5.8 batch 2 = 0042/0043/0044/0045 land 2026-05-21; +1 proposed 2026-05-25 = ADR-0046). TW workload concentrated here.

---

## §9 Schema Migration Roster (v5.8 adds V105-V116; V### re-number consistent per CR-1)

**V### re-number search/replace 狀態 (per CR-1 v5.7 4 follow-up 第 2 條 2026-05-21 補)**：

- ✅ `srv/sql/migrations/` git tree empirical head = **V098** (V091-V098 全 land)；V099-V116 為 spec 未 SQL IMPL
- ✅ V099-V104 spec docs consistent；V103/V104 spec doc v3 (`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`) 已 SPEC-FINAL with V103 §14 EXTEND
- ✅ V105-V113 spec placeholder land 2026-05-21 (per CR-8)；V114-V116 reserve frontmatter only
- ✅ 無 dangling V### references (grep 確認 `V097`/`V098`/`V099`/`V100`/`V101`/`V102` 全部命中為 prereq references 或 catch-up status；無歷史 inconsistent 引用)
- ✅ Memory `project_2026_05_02_p0_sqlx_hash_drift` 教訓：V### SQL file 不直接 rename（觸 sqlx checksum drift）；V### re-number 只在 spec doc + dispatch packet 層；SQL IMPL 階段 E1 land V### sql file 時必 cross-ref spec doc V### number

```
v5.7 lineage:
  V091-V098 (已 land 到 srv/sql/migrations/, sqlx_migrations head = V098)
  V097/V098: Linux DB catch-up (DONE Phase 0 per v5.7 §3)
  V099, V100: Track v3 (per PM 仲裁 1 option A, spec ready, IMPL Sprint 1A-α/β)
  V101, V102: Earn schema (per PM 仲裁 1 option A, spec ready, IMPL Sprint 1A-α/β)
  V103, V104: hypotheses + preregistration + earn_movement_log (v5.7 v3 SPEC-FINAL + §14 audit field EXTEND per CR-1)
             V104 退號為 no-op (per V103/V104 spec §1.3 情境 1)

v5.8 new (CR-8 placeholder spec land 2026-05-21；full DDL Sprint 1A-β/γ 逐個推進):
  V105: overlay_state_transitions + counterfactual_to_state hooks (M2; Sprint 1A-γ; ← V107)
  V106: health_observations + degradation_state (M3; Sprint 1A-β; hypertable 必)
  V107: replay_divergence_log (M11; Sprint 1A-β; ← V103/V109/V113; hypertable 必; ADR-0038)
  V108: ab_tests + ab_assignments + ab_results (M9; Sprint 1A-γ; ← V103; ADR-0037)
  V109: anomaly_events + severity (M8; Sprint 1A-γ; → V112; hypertable 必; ADR-0036; NO HMM/GARCH)
  V110: reward_weight_history + bayesian_opt_runs (M6; Sprint 1A-β)
  V111: discovery_tier_config + capital_triggers (M10; Sprint 1A-γ; Tier D ATR-vol+funding NOT HMM per ADR-0036)
  V112: decision_lease_lal_tiers + lal_eligibility_log + lal_toggle_audit (M1; Sprint 1A-β; ← V113; ADR-0034 LAL rename)
  V113: decay_signals + strategy_lifecycle (M7; Sprint 1A-β; hypertable 必; M7 single decay authority per CR-7)

Interface-stub schemas (no DDL Sprint 1A-δ, reserved numbers only):
  V114: online_learning_models (M5; reserved, not used Y1)
  V115: order_routing_profiles + order_routing_decisions (M12; reserved, IMPL Sprint 6; per ADR-0039 含 maker_fill_rate_30d)
  V116: asset_class_venue_registry (M13; reserved, IMPL Y3+; per ADR-0040 multi-venue Y3+ at earliest)

PA dispatch finalizes consolidation (may merge V109+V108 etc. if logically related).
```

---

## §10 Risk + Constraint Recheck

**Per CLAUDE.md hard boundaries**: all v5.8 modules respect:
- 5-gate live deploy (no bypass)
- AMD-2026-05-15-01 Stage transitions (operator approve for new strategy / size scale up)
- ADR-0024-lite (Cowork operator-assistant; M4 outputs are DRAFTs, not autonomous decisions)
- D1c/D1d (no withdrawal API key; Earn governance per ADR-0030)
- D2 ($3k max loss ceiling; M3 HEALTH_CATASTROPHIC triggers existing kill)

**New risks v5.8 introduces**:
1. **Schema sprawl** (V103-V116): PA dispatch must verify ordering + idempotency; mitigated by per-V dry-run requirement (CLAUDE.md §Data, Migrations, And Validation) + §3.5.5 cross-V### dependency graph
2. **DESIGN-only debt** (M5/M12/M13 interface stubs): if Y2-Y3 IMPL skipped, interfaces become dead code; mitigated by ADR-0035/0039/0040 explicit retirement criteria
3. **Sprint 1A timeline 1.5w → 8.5w PM 整合** (per §3.5): Sprint 2+ shifts right; Sprint 4 first Live (W12-15 → W17.5-20.5); operator must accept; **mitigated by**: v5.7 Sprint 1A baseline (75-105 hr) still completes in 1.5w as scheduled, so first usable governance + sensors lands W1.5 unchanged. v5.8 module DESIGN runs **parallel** to Sprint 1B-3 execution where possible.
4. **Engineering 2.7-3.0x** (1,710 → 3,500-5,200 hr PM 整合): operator cost-of-time exposure; mitigated by **parallel sub-agent execution** (PA + MIT + TW + CC parallelize most DESIGN work) and **DESIGN-deferred-IMPL** structure
5. **Auto-Allocator gate unchanged**: even with v5.8, Y2 90% requires 6+ months Advisory + >80% approval. **v5.8 does NOT shortcut this**.
6. **AI cost Y2 超 DOC-08 §4 cap 1.9-3.5x**（per ADR-0041 / CR-16）：$1,344-2,556/yr Y2 vs DOC-08 §4 $60/月 baseline；mitigated by ContextDistiller v4 800 token hard cap + Y2 conditional opt-in $150-200/月 LAL 4 approval
7. **PG buffer V106 health 高頻表**：6mo +1.25-2.5 GB（占 buffer 16-63%）；mitigated by hypertable 7d chunk + 7d compression + 90d retention (per V106 spec placeholder + E5 audit)
8. **4 state machine（M1/M2/M3/M7）50+ transition 易漏邊**：first-detection deadlock 反模式風險（per memory `feedback_first_detection_deadlock_pattern`）；mitigated by §STATE-MACHINE-TEST proptest 窮舉 + dead-state scan + is_none() reset auto-clear 反模式 scan (per E4 H-14)

---

## §10.5 P0 Precondition Table — Sprint 4 First Live 阻塞（per CR-10 / E2 + FA Audit）

Sprint 4 首次 Live（W17.5-20.5 PM 整合 calendar）受以下 4+1 條 active P0 precondition 阻塞，必先 closure 或 operator accept LiveDemo 自動降級：

| P0 ID | 描述 | Status (2026-05-21) | Sprint 4 Live 阻塞影響 |
|---|---|---|---|
| **P0-EDGE-1** | net-positive edge — **4 textbook** 策略結構性 alpha-deficient（QC 2026-05-11 audit verdict 持續有效；funding_arb 已 retired per AMD-2026-05-26-01，原 5 textbook roster 收斂 4）| OPEN — Phase B/C/D + A 群 待 closure | **HARD BLOCKER**：Sprint 4 Top-1 LIVE 必先有 net-positive edge evidence |
| **P0-LG-3** | Wave 2.4 IMPL DISPATCH 完整鏈 | OPEN — 部分 IMPL | Sprint 4 部分 module 依賴 LG-3 落地 |
| **P0-OPS-1..4** | HTTPS / cred rotation / legal / runbook OPS 4 條 | OPEN — OPS-1 HTTPS 部署 / OPS-2 cred rotation cadence / OPS-3 legal sign-off / OPS-4 runbook完整 | OPS-1/2 是 Live 5-gate 級必要；OPS-3/4 可 LiveDemo 階段並行補 |
| **5-gate live boundary** | Python live_reserved + Operator role + OPENCLAW_ALLOW_MAINNET=1 + valid secret slot + signed authorization.json | 4/5 gate ready；secret slot Sprint 1A-α DONE；authorization 在 Sprint 4 W17.5 簽發 | **HARD GATE**：5/5 必齊；缺一不可 Live |

**operator decision 5（per §12 第 5 條 CR-10）**：
- 選項 A：**Sprint 4 W17.5 前 P0-EDGE-1 + P0-LG-3 + P0-OPS-1/2 全 closure** → 真實 Live $500 開放
- 選項 B：**accept LiveDemo 自動降級** → Sprint 4 走 LiveDemo（live-grade control flow against demo endpoint per ADR-0004 + CLAUDE.md §四 LiveDemo 不降級）；P0 closure deferred to Sprint 6+；Live deadline 至 Sprint 6 末重評
- 選項 C：**Sprint 4 LIVE skip，跳到 Sprint 5+ direct Live** → 須伴隨 P0 emergency closure plan + 操作 risk acceptance

**Sprint 1A-β/γ/δ/ε 不阻**：P0 precondition 在 Sprint 4 W17.5 前須 closure（or operator accept B/C）；不影響 Sprint 1A 多階段 DESIGN dispatch。

---

## §11 Operator Forgetfulness Mitigation (Per Operator's M2 Reasoning)

Operator stated: "Operator 可能忘記，可能犯錯。我們追求 APR 的最大自動型". v5.8 modules that address this:

| Operator failure mode | v5.8 mitigation |
|---|---|
| Forgets to approve monthly Allocator proposal | M1 Tier 2 auto-approval after 6+ months Advisory + opt-in (operator opts in once, auto runs) |
| Forgets to disable overlay when regime shifts | M2 auto-disable (always on, no opt-in needed) |
| Misses anomaly alert | M8 alert severity → M3 auto-degradation (action without operator click) |
| Forgets to retire decayed strategy | M7 auto-demote → 50% size pending review (safer state pending) |
| Forgets to check counterfactual replay | M11 daily replay quality auto-Slack report |
| Forgets to evaluate Copy Trading gate Y2 | v5.7 evidence gate framework still requires explicit operator click; **v5.8 does not auto-enable Copy Trading** (operator preserved as explicit decision per AMD-2026-05-15-01) |

**Limit**: Some decisions remain operator-only (Stage transitions, size scale ups, new strategy promotion, Copy Trading enable, capital tier activation). These are per AMD-2026-05-15-01 + 16 root principles "survival > profit". v5.8 does NOT remove these.

---

## §11.5 5-Gate Auto Path Inheritance — Hard Invariant（per CR-15 / E3 + CC Audit）

**Invariant**：v5.8 引入 7 條 auto path 寫 live state，**任一條必經完整 5-gate fail-closed**。任何一 gate fail → 該 auto path 自動 fall-back to Advisory 模式，**不**繞 gate 直寫。

| Auto path | Module | LAL 級 | 5-gate inheritance contract |
|---|---|---|---|
| 1. M1 LAL 1 intra-strategy reparam | M1 | LAL 1 | Console toggle ON + 30d stable + 90d no-incident + 5/5 gate green; gate fail → fall-back Advisory |
| 2. M1 LAL 2 cross-strategy reweight Y2 | M1 | LAL 2 | Console toggle ON + Y2 enable gate + 6mo Advisory + 80% yes-rate + 5/5 gate green; gate fail → fall-back Advisory |
| 3. M2 overlay auto-disable | M2 | LAL 2 (auto-disable always-on per AMD-2026-05-21-01) | 5/5 gate green; trigger 條件 = Sharpe collapse OR regime anomaly + counterfactual diverge; gate fail → keep current state (degraded conservative) |
| 4. M3 auto-degradation HEALTH_DEGRADED/CRITICAL | M3 | LAL 2 (always-on) | 5/5 gate green required for state transition write; HEALTH_WARN 不 action 只 alert; gate fail → emit alert no state change |
| 5. M6 reward weight ≤30% auto-apply | M6 | LAL 2 (Y2 enable) | Console toggle ON + Y2 enable + bounds within operator-set + 5/5 gate green; gate fail → keep current weight |
| 6. M7 auto-demote DECAY_ENFORCED (50% size) | M7 | LAL 1 (always-on per CR-7 single decay authority) | 5/5 gate green + M11/Sharpe/DD/N-loss 4 signal source ≥ 2 confirm; gate fail → emit alert keep current size |
| 7. M10 capital tier activation eval | M10 | LAL 4 (always operator approve per AMD-2026-05-21-01) | AUM 30d sustained + Console toggle per tier + 5/5 gate green + operator click; gate fail → defer activation |

**M4 DRAFT writeback Decision Lease 紀律**（CR-15 + ADR-0024-lite）：
- M4 pattern miner DRAFT 寫入 V103 EXTEND 必經 Decision Lease + HMAC signature + `ml-training-pattern-miner` role + rate limit
- DRAFT 寫入 rate limit：≤ 10 DRAFT / hour / instance + ≤ 100 DRAFT / day (per AI-E cost guard ADR-0041)
- DRAFT 不可 auto promote 到 preregistered（per CR-6 6 attribute minimum bar + operator+Cowork review required）
- DRAFT 不可 auto trigger trial activation（per ADR-0024-lite Cowork operator-assistant scope）
- DRAFT 寫入 audit log：`agent.ai_invocations` ledger 必含 `fallback_reason` if token budget exhausted

**operator forgetfulness 6 條反向 attack 對應 mitigation**（per E2 H-11 + AMD-2026-05-21-01 §4）：

| 反向 attack | Mitigation |
|---|---|
| M1 24h undo 已 fill 不可逆 | LAL undo scope 明寫 "config + risk envelope only, not fills"（per ADR-0034 Decision 5） |
| M2 false anomaly trigger（healthy market burst → 誤 disable overlay）| M2 auto-disable 條件嚴格 = Sharpe < 0 AND counterfactual diverge AND 30d sustained；單一 burst 不觸發 |
| M3 healthy market burst false-positive | HEALTH_WARN 不 action 只 alert；HEALTH_DEGRADED/CRITICAL 才 state change |
| M7 14d × 50% 持續虧 | 14d review window 末必 operator click decision；不 auto-recover；無 ack 升 25% size 自動 |
| M8 alpha source vs halt 混淆 | M8 severity 4 級（INFO/WARN/CRITICAL/HALT 對齊 M11 per CR-7 §5）；halt 只在 CRITICAL+；HIGH=throttle 非 halt |
| M11 passive Slack 5d 不被 ack | 自動升 M3 HEALTH_WARN；7d 升 HEALTH_DEGRADED 並暫停 LAL 1+2 auto-approval（fail-safe to Advisory） |

**Operator inactivity > 60d** → auto-rollback opt-in scope 全部回 Advisory（per AMD-2026-05-21-01 §3）。

---

## §12 Dispatch Plan

**v5.7 Sprint 1A-α (Week 0-1.5)**: DISPATCH-OF-RECORD. Already PM signed off 2026-05-21 (TODO §0.5). 5 parallel sub-agent tracks. UNCHANGED.

**v5.8 Sprint 1A-β onwards**: 
- Operator approves v5.8 (this document)
- PA produces dispatch packet for Sprint 1A-β (M1+M3+M6+M7+M11 DESIGN; 220-320 hr; 5-7 parallel sub-agents)
- Sprint 1A-β runs Week 1.5-3.5 (after v5.7 1A-α tracks land)
- Subsequent γ/δ/ε per §3 schedule

**Operator decision points (D1-D5 PM 仲裁 batch；2026-05-21 全批)**:

1. **Approve v5.8 13-module scope** (this document) — ✅ D1 已批 (2026-05-21)
2. **Approve Y1 timeline 39w → 44-55w PM 整合**（per §3.5）— ✅ D3 已批 (2026-05-21)
3. **Approve engineering 2.7-3.0x** (1,710 → 3,500-5,200 hr PM 整合) — ✅ D3 已批 (2026-05-21)
4. **Confirm interface-stub policy for M5/M12/M13** — Sprint 1A-δ stubs + Y2-Y3 IMPL trigger by AUM — ✅ D1 含 (2026-05-21)
5. **★ NEW (per CR-10 E2+FA audit)**：**確認 Sprint 4 Live precondition ETA OR accept LiveDemo 自動降級** — Sprint 4 W17.5-20.5 首次 Live 阻塞於 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 4 條 active P0；operator 選 (A) Sprint 4 前全 closure / (B) LiveDemo 降級 deferred to Sprint 6+ / (C) skip Sprint 4 LIVE to Sprint 5+ direct（per §10.5 P0 precondition table）— **PENDING operator click decision before Sprint 4 W17.5 dispatch**

**PM 仲裁 D2/D4/D5（per PA consolidation §8 + PM final verdict §四）**：

- **D2 M1 Lease Tier 改名為 LAL (Layered Approval Lease)** — ✅ 已批 (2026-05-21)；ADR-0034 land；V112 schema column rename `decision_lease_tiers` → `decision_lease_lal_tiers`；避 AMD-01 Stage 0R-4 字面碰撞
- **D4 M13 Y2 Binance trade enable → Y3+ at earliest** — ✅ 已批 (2026-05-21)；ADR-0040 land；per BB push back + ADR-0033 + CLAUDE.md §一 衝突；Y2 期間 Binance 維持 market-data only
- **D5 立 AMD-2026-05-21-01 autonomy-vs-human-final-review** — ✅ 已批 (2026-05-21)；AMD draft land；priority order 第 5 條 protected scope vs opt-in scope 邊界明示

**PM additional decisions（CR-11 + CR-12 + CR-15 + CR-16）**：

- **CR-11 GUI 工時 +261-374 hr 寫入 §3 + §4** — ✅ §3.5.2 + §4 已 reflect；Console tab 歸屬 4 tab × 2-4 sub-section（不擴張 16 tab）；A3 sign-off 48-53 hr Y1 8 surface Lv 3-4
- **CR-12 TW 工時 +450-640 hr 寫入 §3 + §4 + §8 + §9** — ✅ §3.5.2 + §4 已 reflect；TW 並行 dispatch with PA-MIT-CC parallel tracks
- **CR-15 5-gate auto path inheritance hard invariant** — ✅ §11.5 已 land 7 條 auto path + M4 DRAFT writeback Decision Lease + 6 反向 attack mitigation
- **CR-16 ADR-0041 ContextDistiller v4 + DOC-08 §4 amendment** — ✅ ADR-0041 land；Y1 cap $60/月 + Y2 conditional $150-200/月 LAL 4 approval；800 token hard cap；M4 純規則 vs LLM hybrid 明示；M11 daily L1 vs CRITICAL L2 narrative cadence 分

**Sub-agent dispatch readiness（per CR-1..16 完成度）**：

| Prerequisite | 狀態 | Owner |
|---|---|---|
| CR-1 v5.7 4 follow-up | ✅ DONE 主會話 2026-05-21 + sub-agent | PA + MIT + TW + FA + E3 + QA |
| CR-2 ADR-0034 M1 LAL | ✅ DONE 2026-05-21 | TW |
| CR-3 AMD-2026-05-21-01 | ✅ DONE 2026-05-21 | TW + CC |
| CR-4 ADR-0040 multi-venue | ✅ DONE 2026-05-21 | TW + BB + E3 |
| CR-5 ADR-0036 M8 + M10 blacklist | ✅ DONE 2026-05-21 | TW + MIT + QC |
| CR-6 M4 leakage protocol | ✅ DONE 2026-05-21 | MIT + PA |
| CR-7 M11 threshold + M7 dedup | ✅ DONE 2026-05-21 | MIT + QC |
| CR-8 V105-V113 spec placeholders | ✅ DONE 2026-05-21 | MIT + PA + E5 |
| CR-9 PG dry-run + cross-V### graph | ✅ DONE 主會話 §3.5.5 | PA + E5 |
| CR-10 §10.5 P0 precondition + §12 decision 5 | ✅ DONE 主會話 | PM |
| CR-11 GUI hours + §12 A3 sign-off | ✅ DONE 主會話 | PM + A3 |
| CR-12 TW hours + §12 dispatch | ✅ DONE 主會話 | PM + TW |
| CR-13 Sprint 1A + Y1 hours uplift | ✅ DONE 主會話 §3.5 + §4 | PM |
| CR-14 ADR-0039 M12 + ADR-0038 M11 | ✅ DONE 2026-05-21 | TW + BB |
| CR-15 5-gate auto path inheritance | ✅ DONE 主會話 §11.5 | TW + E3 + CC |
| CR-16 ADR-0041 ContextDistiller v4 | ✅ DONE 2026-05-21 | AI-E + TW + PM |

**Sprint 1A-β 派發 readiness**：16/16 CRITICAL 完成 → **GO** D+5~D+10 內 PA dispatch 5-7 並行 sub-agent 開始真實 DESIGN。

**Optional shortcuts (operator can elect)**:
- **Drop M5** entirely (online learning not even interface stub): saves 8-12 hr Sprint 1A but loses interface compatibility
- **Defer M13 Sprint 1A interface stub to Y1 末**: saves 30-40 hr Sprint 1A; risk = Y2 retrofit cost
- **Compress Sprint 1A-γ + δ + ε**: parallel-execute all 13 module DESIGNs in single 4-week burst (high sub-agent load; high cross-ADR collision risk)

---

## §13 References

- v5.7 dispatch (preserved): `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- v5.7 PM autonomy verdict: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md`
- v5.7 12-CRITICAL prefix PM sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
- v5.7 Sprint 1A dispatch packet: `docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md`
- ADR-0024-lite Cowork operator-assistant scope
- AMD-2026-05-15-01 Stage gate framework
- CLAUDE.md root principles (16) + hard boundaries (D1c/D1d)
- 16 root principles priority order: survival > risk governance > system health > audit traceability > human final review > real net PnL > autonomy evolution

**v5.8 16 CRITICAL prefix DONE 2026-05-21 references**:
- PM final verdict (主入口): `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- PA dispatch consolidation 562 行: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- 14 agent v5.8 executability audit: `docs/CCAgentWorkSpace/{A3,AI-E,BB,CC,E2,E3,E4,E5,FA,MIT,QA,QC,R4,TW}/workspace/reports/2026-05-21--v58_executability_audit.md`
- **新 ADR (2026-05-21 batch)**：ADR-0034 (M1 LAL) / ADR-0036 (M8 anomaly + M10 Tier D blacklist) / ADR-0038 (M11 replay + liquidations source) / ADR-0039 (M12 OrderRouter + maker_fill_rate) / ADR-0040 (multi-venue Y3+) / ADR-0041 (ContextDistiller v4 + DOC-08 amend) / ADR-0042 (M3 health) / ADR-0043 (M6 reward) / ADR-0044 (M7 decay DECAY_ENFORCED) / ADR-0045 (M4 governance placeholder)
- **新 AMD**：AMD-2026-05-21-01 v2 Layered Autonomy with Hard-Coded Fail-Safe (2026-05-22 supersede v1 protected 6 / opt-in 8)
- **新 spec doc**：m4_minimum_bar_and_leakage_protocol / m11_threshold_m7_dedup_decay_enforced_rename
- **新 V### placeholder spec**：V105-V113 (9 docs at `docs/execution_plan/2026-05-21--v{105..113}_*_schema_spec.md`)
- **新 AMD (2026-05-25 V1→V5.8 drift audit closure)**:
  - AMD-2026-05-25-01 Commercialization Boundary (Exchange-Native Only) — Retire IP sale + Telegram subscription + Substack + codebase sale + signal feed + MEV/DEX + Stripe pre-order；Retain Bybit + Binance 平台官方 (Copy Trading / Earn / Master Trader / Competitions)
  - AMD-2026-05-25-02 v5.5 Bot Positioning + Capital Structure Formalization — Single product 完整 quant bot；Y1 100% 主帳 $7,500；副帳 Y2+ ADR-0030 4-gate + Moat 5-gate conditional enable
- **新 ADR proposed (2026-05-25)**: ADR-0046 basis observation vs execution split (funding_arb scope, BB+QC spec; Sprint 1A-δ/ε 24-30 hr 平行 IMPL)
- **新 AMD (2026-05-26 Workflow F closure)**: AMD-2026-05-26-01 funding_arb V2 Deprecation Closure — operator (D) 3C TOML deprecation closure；ADR-0018 status 升格 Retired closed；strategy code `#[deprecated]` marker + runtime fail-closed guard；**5 textbook roster → 4 textbook**（funding_arb 移除）；ADR-0046 future redesign slot 並存保留；D+0/D+7/D+30 cleanup 三階段
- **drift audit 終稿**: `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` (V1→V5.8 全鏈 plan/audit 整合 + 8 條報告錯誤修正 + SSH empirical verify + 10 條剩餘 unresolved + 2 AMD drafts + canary [67]→[80] rename)
- **canary [67]→[80] rename**: per operator 2026-05-25 directive avoid passive_wait [67] collision; 4 files modified, 16 tests collected PASS, pending operator commit
- **Alpha Tournament SSOT (2026-05-26)**: `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`（Sprint 2 盈利主線補洞；候選池 / scoring contract / Stage output / 最小前置 / 跨文檔讀取順序）

---

## §14 v5.8 Summary

**Thesis**: v5.7 thesis preserved (Self-Trading Lab + governance-first + evidence-gated). v5.8 adds 13-module autonomy track per operator directive 2026-05-21.

**Scope change vs v5.7**:
- +13 modules with full DESIGN at Sprint 1A (M5/M12/M13 interface stubs only)
- +**8 new ADRs (0034-0041)** + **1 new AMD (2026-05-21-01)** + 2 spec docs (M4 leakage / M11+M7 dedup)
- +**12 new schema migrations / extensions** (V105-V116; V105-V113 active; V114-V116 reserve)
- +**1,790-3,490 hr engineering Y1 PM 整合**（v5.7 1,275-1,710 hr → v5.8 真實 3,500-5,200 hr）
- +**5-16 weeks Y1 timeline PM 整合**（Sprint 1A 1.5w → 8.5w；Y1 39w → 44-55w）
- +Capital tier scaling design (M10 Tier A-E roadmap)
- +Operator forgetfulness mitigation (M1 default-OFF auto, M2 auto-disable, M3 auto-degrade, M7 DECAY_ENFORCED safer demote, M8 alert→action, M11 daily report) + AMD-2026-05-21-01 protected vs opt-in scope 明示
- +**M1 Tier 0-4 → LAL 0-4** rename（per D2 + ADR-0034；避 AMD-01 Stage 0R-4 字面碰撞）
- +**M7 STAGE_DEMOTED → DECAY_ENFORCED** rename（per CR-7；避 Stage 字面碰撞）
- +**M13 Y2 → Y3+ at earliest**（per D4 + ADR-0040；BB push back + Bybit-only baseline）
- +**M8/M10 Tier D HMM/Markov-switching/GARCH 黑名單**（per ADR-0036；math-model-audit skill 永久 ADR 級強化）
- +**M11 self-hosted PG market.liquidations historical source**（per ADR-0038；不依賴 Bybit historical API）
- +**ContextDistiller v4 800 token hard cap + DOC-08 §4 Y2 conditional opt-in $150-200/月**（per ADR-0041）

**Autonomy delta**:
- Y1 末: 60% → 66%
- Y2 Q2: 88% → 90%
- Y3 Q2: (v5.7 not reaching) → 95% (with capital growth)

**Long-term value**:
- M4 self-supervised discovery delivers Y2-Y3 alpha (operator's "long-term auto-iteration")；per CR-6 6 attribute minimum bar + shift(1) leak-free 紀律
- M10 Tier C-E enables capital scaling without re-architecture (operator's "don't assume $10k")；Tier D 用 ATR-vol+funding 不 HMM
- M5/M12/M13 interface reservations keep Y3+ doors open；M12 含 maker_fill_rate_30d 維持 Bybit rebate eligibility
- M11 continuous counterfactual replay 100% self-hosted；governance posture 不押 vendor optionality

**Dispatch readiness**: v5.7 Sprint 1A-α unchanged (already PM-signed 2026-05-21). v5.8 **16 CRITICAL prefix DONE 2026-05-21**，operator D1-D5 + PM 仲裁 10 條已批；Sprint 1A-β D+5~D+10 內可派 5-7 並行 sub-agent DESIGN dispatch。

---

**END v5.8 — 13-Module Autonomy Expansion + 16 CRITICAL Prefix DONE 2026-05-21**

**Sprint 1A-β 派發 readiness**：**GO** — 16/16 CRITICAL prefix 完成；5 operator decision (D1-D5) 已批；3 PM 仲裁 (D2/D4/D5) 已批；7 additional PM decisions (CR-11/12/15/16) 已批；D+5~D+10 PA dispatch packet → 5-7 並行 sub-agent → 真實 DESIGN 開始。
