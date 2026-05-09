# ADR 0021: Alpha Source Architecture Upgrade — Strategy Interface, Strategist Scope, Hypothesis Pipeline, Per-Alpha-Source Promotion

Date: 2026-05-09
Status: **Accepted**
Operator Sign-off Date: 2026-05-09
Sign-off Mode: Auto-mode dispatch via PM, operator approval recorded in Session N+1 handoff（中文：「ADR 0021 可以」）

## Context

5 active strategies (`bb_breakout`, `bb_reversion`, `ma_crossover`, `grid_trading`, `funding_arb`) produced 7d demo gross **-26.44 USDT** (CLAUDE.md §三 2026-05-08 PA direct PG check; healthcheck `[40]` realized_edge_acceptance同源 edge/MLDE 口徑). The 12-agent full audit (`2026-05-08--full_audit_fix_plan.md`) catalogued 88 unique findings. Subsequent v2 verification land + PA architectural redesign (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`) reached the verdict that the loss is **architectural**, not strategy-bug or parameter-tuning failure:

- **Root cause 1 (Strategy interface alpha-poverty)**: `Strategy::on_tick(&TickContext)` structurally incentivises 1m kline + classic indicator path; non-TA alpha sources (funding curve, OI delta panel, orderflow features, liquidation pulse) require strategies to self-buffer (second-class), causing all incubated strategies to regress to textbook TA.
- **Root cause 2 (Strategist scope)**: Strategist Agent is bounded to `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded weights + `max_param_delta_pct` 50%; no alpha-discovery responsibility in code.
- **Root cause 3 (Analyst L2-L5 dormant)**: hypothesis-experiment-verdict loop specified in EX-06 but 0% IMPL; ADR-0020 keeps Layer2 manual supervisor-only by design.
- **Root cause 4 (Risk-side iron / alpha-side shepherd)**: 4 risk_config TOML + Guardian veto + SM-04 5-step ladder + Cost Gate vs 1 strategy_params TOML + 1 hardcoded preferences dict — no architectural forcing function on alpha side.
- **Root cause 5 (5-Agent skeleton without soul)**: Conductor + 5-Agent split is correct governance bone, but 4 of 5 are runtime hollow (Scout intel logging only, Analyst L2-L5 dormant, Strategist alpha-discovery absent, Layer2 manual).

The 88 finding patch list addresses Cluster D/E/F/G surface symptoms but cannot solve Cluster A (alpha-poverty, ~25-30 findings) or Cluster B (learning loop dead, ~15-20 findings) under current architecture.

## Decision

Adopt the PA R-1..R-5 architectural upgrade roadmap as new Track A wave family (W-AUDIT-8a..8g):

- **R-1 / W-AUDIT-8a (Spec Phase started 2026-05-09)** — Alpha Surface Bundle + Strategy Interface upgrade. New Rust `AlphaSurface<'a>` 4-tier struct (Tier 1 TA / Tier 2 cross-asset panel / Tier 3 microstructure / Tier 4 information flow); `Strategy` trait gains `declared_alpha_sources()` + `on_tick(ctx, surface)` signature; 5 existing strategies declare alpha sources for backward compat; Orchestrator adds dispatch tracking metric `alpha_source_dispatched_total{tag=...}`. Spec: `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`.
- **R-2 / W-AUDIT-8e (later)** — Strategist scope reframe to `AlphaSourceRegistry` orchestrator (active / observing / deprecated / sunset 4 stage) + `propose_alpha_source()` producing `Hypothesis` rather than `TradeIntent`. Removes `_REGIME_STRATEGY_PREFERENCES` hardcoded dict in favour of dynamic Sharpe-by-regime computation.
- **R-3 / W-AUDIT-8f (later)** — Hypothesis Pipeline as first-class governance object (parity with Decision Lease). New V### migration `learning.hypotheses` table + state machine `DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → PROMOTED|REJECTED|EXPIRED`. Decision Lease + ExecutionPlan + fills propagate `originating_hypothesis_id`. attribution_chain rewritten on hypothesis_id.
- **R-4 / W-AUDIT-8g (later)** — Per-alpha-source Live Promotion Gate replacing system-wide `live_reserved` binary. New `LiveBudget(alpha_source_id, slice)` allocation model. **Supersedes LG-X-02..05 system-wide promotion design** (LG-X 1-5 baseline foundation — H0 production caller / pricing binding / supervised-live state machine — remains required as substrate; only the per-system-wide allocation surface is replaced).
- **R-5 / W-AUDIT-1 increment (parallel)** — Spec-as-Code + Module Lifecycle State Machine (active / observing / deprecated / sunset header per module + table). CI gate for CLAUDE.md §三 stale > 7d. Auto-extracted SCRIPT_INDEX / SPECIFICATION_REGISTER from code.

R-1 SPEC phase IMPL is deferred to per-wave decision; this ADR records the architectural direction. W-AUDIT-9 graduated canary (per AMD-2026-05-09-03) is the deploy substrate for any alpha-bearing IMPL landing under R-1..R-4.

## Consequences

**Reversible**:
- R-1..R-5 are incremental; AlphaSurface backward-compatible (Tier 2-3 fields are `Option<&...>`, default `None` until later phase wires panel collectors).
- 5 existing strategies migration is `declared_alpha_sources()` declaration only, not logic rewrite (Sprint estimate: 3 sprint for R-1 spec + IMPL + 5-strategy migration + tests).
- Each wave has explicit failure fallback (R-1: stub Tier 2-3 only; R-2: keep hardcoded dict, add Registry observation; R-3: phase 1 manual approval before Analyst L3 auto; R-4: keep binary `live_reserved` with alpha-source-aware budget within Live).

**Surprising / breaking**:
- **`Strategy::on_tick` signature changes** from `(ctx)` to `(ctx, surface)` — breaking interface change for all 5 strategies (mitigated by backward-compat declare-only migration).
- **LG governance model reversal under R-4**: `live_reserved (yes/no)` → `live_budget(alpha_source_id, slice)`. LG-X-02..05 system-wide design semantics partially superseded.
- **CLAUDE.md §五 architecture description rewrites**: pipeline reframed from "KlineManager → IndicatorEngine → SignalEngine → 5 策略" to "市場數據 → AlphaSurface (kline + funding + basis + orderflow + xasset) → Strategy → Orchestrator". Mental model shift required.
- **Strategist Agent identity reframe** (R-2): from parameter tuner to alpha-source orchestrator; removal of `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded dict is breaking change to Strategist contract.

**Real trade-off / alternatives considered**:
- vs **"先修 88 finding 再說架構" path**: 88 findings catalogue real defects but Cluster A (~25-30) and Cluster B (~15-20) are downstream symptoms of Root Cause 1+2+3; patching 5 TA strategies to gross-positive is structurally improbable (5 strategies all consume same TA alpha source → mutually cannibalising). Trade-off: 88 finding path delivers visible patch progress but unlikely to flip gross sign; R-1..R-5 path defers visible strategy-level fix but addresses architectural root cause. **Decision rationale**: per PA report Layer 4, 88 patch + R-1..R-5 parallel — W-AUDIT-2/-5 maintenance + minimum W-AUDIT-6 (funding_arb retire + DSR/PBO + Kelly config) + R-1 SPEC concurrent.
- vs **`_REGIME_STRATEGY_PREFERENCES` hardcoded retention**: keeping the 4×5 dict avoids R-2 churn but cements Strategist as parameter tuner; ruled out.
- vs **ADR-0020 (Layer2 manual supervisor-only) extension**: R-2 reframes the Layer2 unblock path to "alpha-source proposal cloud reasoning" rather than autonomous high-frequency trade signal; ADR-0020 manual + supervisor-only invariant is **preserved** (Layer2 alpha-source proposals still require manual operator/supervisor approval before promotion to active alpha source). R-2 is compatible with ADR-0020.
- vs **Conductor + 5-Agent skeleton dismantle**: PA verdict Layer 1.5 — split is governance-correct (clear responsibility boundaries, Decision Lease + Guardian veto + Authorization governance). Do **not** dismantle skeleton; install souls (Analyst L2-L5 + Strategist alpha-discovery + Layer2 cloud reasoning per R-2/R-3).

**Supersedes / impacts**:
- LG-X-02..05 system-wide promotion design partially superseded by R-4 per-alpha-source budget model (LG-X-02..05 baseline IMPL — H0 production caller / pricing binding / supervised-live state machine — remains required as substrate). SPECIFICATION_REGISTER LG-X-02..05 entries should be annotated `Superseded by ARCH-04 R-4 (proposed)` once this ADR is Accepted.
- `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded dict added to DEPRECATED.md candidate list when ADR-0021 reaches Accepted status.
- W-AUDIT-4 (ML/Dream feature_baselines + outcome backfill) recommended to **fold into R-3 Hypothesis Pipeline IMPL** rather than run as parallel track (otherwise dead schema becomes alive schema without semantic anchor).
- W-AUDIT-7 Layer2 portion reframed by R-2 (alpha-source proposal as Layer2 unblock substrate, compatible with ADR-0020 manual + supervisor-only invariant).
- W-AUDIT-6 戰略 ROI 重評為 minimum-only (funding_arb retire per ADR-0018 + DSR/PBO wiring + Kelly config), not full 5-strategy rewrite.
- R-3 introduces new V### migration (`learning.hypotheses` table + state machine + `originating_hypothesis_id` columns on Decision Lease / ExecutionPlan / fills); subject to Guard A/B/C + Linux PG dry-run mandate (CLAUDE.md §七 V### migration rule).

## References

- PA architectural redesign: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- W-AUDIT-8a Spec Phase: `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- AMD-2026-05-09-03 graduated canary default: `docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`
- 88 finding source: `2026-05-08--full_audit_fix_plan.md`
- v2 verification summary: `2026-05-09--audit_fix_verification_v2_summary.md`
- v3 verification summary: `2026-05-09--audit_fix_verification_v3_summary.md`
- R4 v3 index verification: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-09--index_verification_v3.md`
- ADR-0018 funding_arb V2 deprecation: `docs/adr/0018-funding-arb-v2-deprecation-watch.md`
- ADR-0020 Layer2 manual supervisor-only: `docs/adr/0020-layer2-manual-supervisor-only.md`
- EX-06 Agent Conflict Arbitration: `docs/governance_dev/EX-06.md`
