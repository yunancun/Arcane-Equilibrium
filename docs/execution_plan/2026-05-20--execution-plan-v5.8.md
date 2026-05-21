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
| **M4** | Self-supervised hypothesis discovery (unsupervised pattern mining → preregistration draft) | Per operator: long-term self-iteration; bot proposes its own hypotheses for Cowork+operator review | **ADD per operator** | Sprint 1A schema + Sprint 8 first IMPL | Y2 Q2-Q3 active |
| **M5** | Online learning / incremental model update (vs daily-batch retrain) | Per operator: low priority, future development point | **ADD per operator (LOW)** | Sprint 1A interface reservation only | Y3+ when justified |
| **M6** | Multi-objective reward function tuning / weight self-calibration | Auto-Allocator's reward weights (λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay) tune from outcomes | CRITICAL (Auto-Allocator gate dependency) | Sprint 1A DESIGN + Sprint 7 IMPL (Advisory) | Y2 active |
| **M7** | Strategy decay detection + retirement automation | Per-strategy alpha decay → auto Stage demote / retire | CRITICAL (Sprint 8 originally in v5.7) | Sprint 1A DESIGN + Sprint 8 IMPL | Sprint 8 active |
| **M8** | Anomaly detection (market regime shift + own behavior anomaly) | Per operator: design at initial stage for friendly future integration | **ADD per operator (DESIGN initial)** | Sprint 1A schema + Sprint 3 read-only logging | Y1 H2 → Y2 active trigger |
| **M9** | A/B testing framework (parameter / variant test infrastructure) | Per operator: design at initial stage for friendly future integration | **ADD per operator (DESIGN initial)** | Sprint 1A schema + Sprint 4 read-only logging | Y2 active gate |
| **M10** | Autonomous strategy / market / regime discovery pipeline | Per operator: don't assume always $10k; design for capital scaling | **ADD per operator** | Sprint 1A DESIGN + Sprint 8 Discovery Pipeline IMPL | Y2-Y3 scaling activation |
| **M11** | Counterfactual replay automation + continuous validation | Stage 0R replay infrastructure scaling: nightly counterfactual replay for all live strategies | CRITICAL (replay is approved evidence lane) | Sprint 1A DESIGN + Sprint 3 IMPL | Sprint 5+ continuous |
| **M12** | Adaptive order routing (venue / order type / slicing self-tuning) | Per operator: do even if delayed | **ADD per operator (delayed)** | Sprint 1A interface reservation + Sprint 6 IMPL | Y2 Q2 active |
| **M13** | Multi-asset class / multi-venue capacity (beyond Bybit perp+spot+options) | Per operator: do even if delayed; capital may scale | **ADD per operator (delayed)** | Sprint 1A interface reservation + Y1 末 spec | Y2-Y3 phased per AUM |

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

Auto-retirement state machine (per-strategy):
  STAGE_LIVE → DECAY_DETECTED (signal triggered)
  DECAY_DETECTED → STAGE_DEMOTE_PROPOSED (Allocator generates proposal)
  STAGE_DEMOTE_PROPOSED → STAGE_DEMOTED (operator approve OR Tier 1 auto-approve via M1)
  STAGE_DEMOTED → live size scaled to 50% pending review
  Review window (14 d) → either RECOVER (re-promote) or RETIRE (size = 0)

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
  - Venue choice (Y1: Bybit only; Y2+: Bybit / Binance perp where price-equivalent)
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
  - Y2: Cross-venue routing (when Binance trading enabled per ADR-0006 amendment) (100-160 hr)

Initial DESIGN cost Sprint 1A: 20-30 hr
Total IMPL Y1-Y2: 240-380 hr
```

### M13 — Multi-Asset Class / Multi-Venue (DESIGN initial / IMPL delayed)

**Per operator: do even if delayed; capital may scale**.

**v5.8 design**:
```
Asset class expansion roadmap:
  Y1: Bybit perp + Bybit spot (Earn) + Bybit options (C13 VRP)
  Y2: + Binance perp (price-equivalent symbols only; per ADR-0006 amendment Binance market-data primary, trade secondary)
  Y2-Y3: + structured products (Bybit Earn variants, options strategies beyond VRP)
  Y3+: + Binance options (when AUM justifies)
  Always declined: DEX / Hyperliquid (D1a per operator)

Multi-asset abstractions:
  - AssetClass enum (Perp / Spot / Option / Earn / Structured)
  - Venue enum (BybitPerp / BybitSpot / BybitOption / BinancePerp / ...)
  - Cross-venue position aggregator (existing PositionAggregator extends)
  - Multi-venue Decision Lease + Guardian (extend to handle cross-venue netting)

Engineering scope:
  - Sprint 1A: AssetClass + Venue enums + ADR-0040 (interface stub only) (30-40 hr)
  - Y1 末: Multi-venue spec (when do we add Binance trade authority) (50-70 hr)
  - Y2: Binance perp trade enable (with Stage 0R replay using Binance data) (200-300 hr)
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

## §4 Y1 Total Engineering (v5.8)

| Sprint | Weeks (v5.7) | Weeks (v5.8) | Focus | Hours (v5.8) |
|---|---|---|---|---|
| 1A (α through ε) | 0-1.5 | 0-7 | v5.7 baseline + 13-module DESIGN | 600-900 |
| 1B | 1.5-3 | 7-10 | v5.7 baseline 1B + early M3/M11 IMPL | 130-180 |
| 2 | 4-7 | 10-13 | Alpha Tournament + M4 pattern miner stage 1 + M10 Tier A productionize | 220-310 |
| 3 | 8-11 | 13-16 | Top-1 build + Stage 0 shadow + M11 nightly replay + M3 statistical detectors | 220-300 |
| 4 | 12-15 | 16-19 | Top-1 live + Top-2 + Options Stack 1 + M1 Tier 1 IMPL + M9 read-only | 280-380 |
| 5 | 16-19 | 19-22 | Top-2 live + Top-3 + Options Stack 2 + M3 auto-degradation triggers + M11 hookups | 240-340 |
| 6 | 20-23 | 22-25 | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker adaptive | 240-340 |
| 7 | 24-27 | 25-28 | Top-5 + Advisory Allocator + M1 Tier 2 + M6 Advisory reward weights | 220-320 |
| 8 | 28-31 | 28-31 | Decay (M7) IMPL + M4 pattern miner stage 2 + M9 manual A/B + M3 recovery logic + M8 alerting | 280-380 |
| 9 | 32-35 | 31-34 | Continue Advisory + Copy Infra build + M12 slicing IMPL | 200-280 |
| 10 | 36-39 | 34-37 | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M2/M8/M9 Y2 prep + M13 spec | 150-200 |
| **Y1 Total** | **39 wk** | **37-44 wk** | | **2,780-3,930 hr** |

**vs v5.7 1,275-1,710 hr**: v5.8 ~2.0-2.3x engineering. This is the cost of designing 13 modules.

**vs reviewer's full-13-module estimate 2,000-7,800 hr**: v5.8 lands at ~3,200 hr median, lower bound of reviewer range. Achievable because most modules are DESIGN-only Y1; full IMPL phased Y2-Y3.

---

## §5 Capital-Tier IMPL Triggers (M10 / M13 Activation)

Per operator's "don't assume always $10k":

```
AUM trigger ladder:
  $10k  (Y1 start)                           : Sprint 1A-10 v5.8 scope
  $15-20k (Y1 末 if Copy Trading prep on)     : M4 active, M9 manual A/B active, M2 Y2 enable eval
  $20-30k (Y2 Q1-Q2)                         : Auto-Allocator active (M1 Tier 2 + M6 Auto), M8 active trigger, M11 mature
  $30-50k (Y2 Q2-Q4)                         : M10 Tier C (new symbol screening), M12 cross-venue routing
  $50-75k (Y2 末 - Y3 Q1)                    : M13 Binance perp trade enable, M10 Tier D regime auto-classify
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

## §8 ADR Roster (v5.8 adds 7 new ADRs)

| ADR | Topic | Status |
|---|---|---|
| 0034 | M1 Decision Lease Tier system | NEW Sprint 1A-β |
| 0035 | M5 Online learning interface (reservation) | NEW Sprint 1A-δ |
| 0036 | M8 Anomaly detection event taxonomy | NEW Sprint 1A-γ |
| 0037 | M9 A/B testing framework + statistical methodology | NEW Sprint 1A-γ |
| 0038 | M11 Continuous counterfactual replay | NEW Sprint 1A-β |
| 0039 | M12 OrderRouter trait interface (reservation) | NEW Sprint 1A-δ |
| 0040 | M13 AssetClass + Venue abstraction (reservation) | NEW Sprint 1A-δ |

Plus existing v5.7 lineage:
- 0030 Bybit Earn governance
- 0031 Macro counterfactual policy
- 0032 On-chain counterfactual policy
- 0033 ADR-0006 amendment (Bybit primary, DEX declined)

**Total ADR adds Sprint 1A**: 11 (4 from v5.7 + 7 from v5.8). TW workload concentrated here.

---

## §9 Schema Migration Roster (v5.8 adds V105-V107 + extensions)

```
v5.7 lineage:
  V097, V098: Linux DB catch-up (in flight)
  V099, V100: Track v3 (per PM arbitration)
  V101, V102: Earn schema (per PM arbitration)
  V103, V104: hypotheses + preregistration (v5.7) — EXTEND in v5.8 for M4

v5.8 new:
  V105: overlay_state_transitions + counterfactual_to_state hooks (M2)
  V106: health_observations + degradation_state (M3)
  V107: replay_divergence_log (M11)
  V108: ab_tests + ab_assignments + ab_results (M9) [could merge with V107 if dispatch consolidates]
  V109: anomaly_events + severity (M8)
  V110: reward_weight_history + bayesian_opt_runs (M6)
  V111: discovery_tier_config + capital_triggers (M10)
  V112: decision_lease_tiers + tier_eligibility_log (M1)
  V113: decay_signals + strategy_lifecycle (M7)

Interface-stub schemas (no DDL Sprint 1A, but reserved numbers):
  V114: online_learning_models (M5; reserved, not used Y1)
  V115: order_routing_profiles (M12; reserved, IMPL Sprint 6)
  V116: asset_class_venue_registry (M13; reserved, IMPL Y2)

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
1. **Schema sprawl** (V103-V116): PA dispatch must verify ordering + idempotency; mitigated by per-V dry-run requirement (CLAUDE.md §Data, Migrations, And Validation)
2. **DESIGN-only debt** (M5/M12/M13 interface stubs): if Y2-Y3 IMPL skipped, interfaces become dead code; mitigated by ADR-0035/0039/0040 explicit retirement criteria
3. **Sprint 1A timeline 1.5w → 7w**: Sprint 2+ shifts right; Sprint 4 first Live (W12-15 → W16-19); operator must accept; **mitigated by**: v5.7 Sprint 1A baseline (75-105 hr) still completes in 1.5w as scheduled, so first usable governance + sensors lands W1.5 unchanged. v5.8 module DESIGN runs **parallel** to Sprint 1B-3 execution where possible.
4. **Engineering 2.3x** (1,710 → 3,930 hr): operator cost-of-time exposure; mitigated by **parallel sub-agent execution** (PA + MIT + TW + CC parallelize most DESIGN work) and **DESIGN-deferred-IMPL** structure
5. **Auto-Allocator gate unchanged**: even with v5.8, Y2 90% requires 6+ months Advisory + >80% approval. **v5.8 does NOT shortcut this**.

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

## §12 Dispatch Plan

**v5.7 Sprint 1A-α (Week 0-1.5)**: DISPATCH-OF-RECORD. Already PM signed off 2026-05-21 (TODO §0.5). 5 parallel sub-agent tracks. UNCHANGED.

**v5.8 Sprint 1A-β onwards**: 
- Operator approves v5.8 (this document)
- PA produces dispatch packet for Sprint 1A-β (M1+M3+M6+M7+M11 DESIGN; 220-320 hr; 5-7 parallel sub-agents)
- Sprint 1A-β runs Week 1.5-3.5 (after v5.7 1A-α tracks land)
- Subsequent γ/δ/ε per §3 schedule

**Operator decision points**:
1. **Approve v5.8 13-module scope** (this document) — Y/N
2. **Approve Y1 timeline 39w → 44w** — operator accepts 5w slip for autonomy DESIGN
3. **Approve engineering 2.3x** (1,710 → 3,930 hr) — operator accepts cost
4. **Confirm interface-stub policy for M5/M12/M13** — Sprint 1A-δ stubs + Y2-Y3 IMPL trigger by AUM

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

---

## §14 v5.8 Summary

**Thesis**: v5.7 thesis preserved (Self-Trading Lab + governance-first + evidence-gated). v5.8 adds 13-module autonomy track per operator directive 2026-05-21.

**Scope change vs v5.7**:
- +13 modules with full DESIGN at Sprint 1A (M5/M12/M13 interface stubs only)
- +7 new ADRs (0034-0040)
- +12 new schema migrations / extensions
- +1,505-2,220 hr engineering Y1
- +5 weeks Y1 timeline (Sprint 1A 1.5w → 7w)
- +Capital tier scaling design (M10 Tier A-E roadmap)
- +Operator forgetfulness mitigation (M1 default-OFF auto, M2 auto-disable, M3 auto-degrade, M7 safer demote, M8 alert→action, M11 daily report)

**Autonomy delta**:
- Y1 末: 60% → 66%
- Y2 Q2: 88% → 90%
- Y3 Q2: (v5.7 not reaching) → 95% (with capital growth)

**Long-term value**:
- M4 self-supervised discovery delivers Y2-Y3 alpha (operator's "long-term auto-iteration")
- M10 Tier C-E enables capital scaling without re-architecture (operator's "don't assume $10k")
- M5/M12/M13 interface reservations keep Y3+ doors open

**Dispatch readiness**: v5.7 Sprint 1A-α unchanged (already PM-signed). v5.8 awaits operator approval of this document, then PA dispatch Sprint 1A-β.

---

**END v5.8 — 13-Module Autonomy Expansion**

**Operator action required**: 4 decision points in §12.
