# L2 Advisory Mesh — Phase 3 `ml_advisory.v1` (FIRST L2 capability) Technical Design

Date: 2026-06-09
Author: PA (Project Architect)
Status: **DESIGN-ONLY** — no feature code, no migration apply, no DB write, no deploy in this pass. Every assertion grounded in `file:line`.
Owner chain (this phase): PM → **PA (this doc)** → E1/E1a → E2 → **QC (B1 final numbers + leak-free PIT)** → **MIT (M3 leak coverage + M4 recall)** → E4 (incl. Linux PG if V137 reopened) → QA → PM.
SSOT design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md` (v4-final) — §E.2(0) (lines 822-903), §G.2/G.2.1 (lines 1217-1277), §N.1 (lines 1862-1920), §B (lines 408-483), §C.2 (lines 536-633).
Execution plan: `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` §2 Phase 3 (lines 184-223) + §0 read-before-build (lines 36-54) + §1 gating ledger (B1/Q1/M3/M4/C2, lines 65-75).
P2 design (the seam P3 wires into): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-p2-orchestrator-tech-design.md`.
Branch `feature/l2-critic-lessons-tools` @ `6a9dd0f1` (P2 Orchestrator landed; **all mesh scaffolding shipped + all capabilities `enabled=false`**; P3 adds the FIRST capability).

**Critical framing:** P2 (`6a9dd0f1`) already shipped the entire mesh scaffolding as committed code — `l2_advisory_orchestrator.py`, `l2_capability_registry.py` + `settings/l2_capability_registry.toml` (skeleton, 0 capability stanza), `l2_prompt_contract_registry.py`, `l2_out_of_bound_guard.py`, `l2_conflict_adjudicator.py`. **P3 is NOT greenfield orchestration** — it is (a) one capability stanza in TOML, (b) the `ml_advisory.v1` PromptContract + OutputSchema in the contract registry, (c) the `ml_advisory.guard.v1` clauses in the guard registry, (d) the **executor** (the cascade) wired into the orchestrator dispatch seam, and (e) the **deterministic math gate including `beta_neutral_check` (B1, NEW, QC-gated)**. The big question P3 answers is the data + math-gate question, not the plumbing.

---

## A. ML-pipeline seam — input · output · sink (every claim ground:file:line)

I read `run_training_pipeline.py`, `mlde_shadow_advisor.py`, `leakage_check.py`, V031, and the V031 `mlde_shadow_recommendations` schema **in full** (execution-plan §0 line 36-38 binding precondition: "Re-read those modules in full before phase 3 sign-off").

| Module | Input | Output (shape) | Sink | Ground |
|---|---|---|---|---|
| **`run_training_pipeline.py`** | `PipelineConfig{strategy_type, symbol, regime, dsn, min_samples, use_quantile_predictor, engine_mode}`; loads `(features, labels, timestamps, feature_names)` via `parquet_etl.load_training_data` | `PipelineResult{success, stages_completed[], verdict, metrics{pinball_skill_q10/q50/q90, crossing_rate, decile_lift_point, decile_lift_ci_lower, feature_schema_hash, feature_definition_hash, n_samples_labeled, pooled, symbol_slot}, acceptance_report_path, onnx_artifacts}` | **filesystem** acceptance-report JSON (`run_training_pipeline.py:299-312`) + **`learning.model_registry`** (V023) via `register_quantile_trio_from_onnx_out` (`:374-384`) gated on `verdict ≠ no_ship` | class `:36-89`; `run_pipeline` `:474-513`; quantile path `:236-422`; metrics dict `:406-420`; legacy path `:425-471` → `metrics.json` `:462-463` |
| **`mlde_shadow_advisor.py`** | `learning.mlde_edge_training_rows` (V031 view) aggregate rows via `_fetch_aggregate_rows` (`:326-370`, reads `engine_mode/strategy_name/symbol_bucket/regime/scanner_*/avg_net_bps/win_rate`) | `list[ShadowRecommendation]{engine_mode, source, recommendation_type:rank|veto, strategy_name, expected_net_bps, confidence, sample_count, payload}` | **`learning.mlde_shadow_recommendations`** via `verify_replay_evidence_and_insert(...)` SQL fn (`:469-489`) with **`p_applied=false` (line 480), `p_requires_governance=true` (line 481)**, `p_created_by='mlde_shadow_advisor'` | class `:163-187`; `build_recommendations` `:271-323`; `_persist_recommendations` `:420-575`; `generate_shadow_recommendations` `:578-609` |
| **`leakage_check.py`** | `list[feature_names:str]` + `strict:bool` | `(passed:bool, violations:list[str])` | **none** (pure function; returns to caller) | `check_feature_leakage` `:41-78`; `FORBIDDEN_PATTERNS` `:20-30`; `ALLOWED_PREFIXES` `:33-38` |
| **V031 view `mlde_edge_training_rows`** | attribution chain (read-only view) | training rows (engine_mode, strategy, symbol_bucket, regime, scanner_*, net_bps_after_fee, attribution_chain_ok) | n/a (read-only view) | `V031__ml_dream_edge_unblock.sql:11-13` (view note); `:348` (FROM clause in advisor) |
| **`learning.mlde_shadow_recommendations`** | INSERT via `verify_replay_evidence_and_insert` | advisory rows | **terminal advisory sink** | `V031:407-434` (CREATE TABLE); **`applied BOOLEAN NOT NULL DEFAULT FALSE` `:432`**; **`requires_governance BOOLEAN NOT NULL DEFAULT TRUE` `:433`**; live-gate CHECK requires `decision_lease_id` when `applied` `:444-449`; COMMENT `:466-469` "Not an execution queue; live applied rows require Decision Lease id" |

### A.1 ★ Advisory-sink confirmation (execution-plan §0 line 37-38: "confirm this is the right advisory sink")

**CONFIRMED `learning.mlde_shadow_recommendations` is the correct, structurally-advisory sink.** Two-layer proof:
1. **Schema-enforced advisory**: `applied DEFAULT FALSE` (`V031:432`) + `requires_governance DEFAULT TRUE` (`V031:433`) + a DB CHECK constraint that any `applied` row MUST carry a `decision_lease_id` (`V031:444-449`). The table COMMENT (`V031:466-467`) states "Advisory ML/Dream/LinUCB/Opportunity outputs. **Not an execution queue**; live applied rows require Decision Lease id."
2. **Producer-enforced advisory**: the only producer (`mlde_shadow_advisor.py`) hardcodes `p_applied=false` (`:480`) and `p_requires_governance=true` (`:481`) at every INSERT — it is structurally incapable of writing an applied row.

So `ml_advisory.v1` feeding this surface = **0 new execution authority** (the iron rule). The hard boundary V031 already declares (`:15-17`): "ML/Dream output is advisory by default. Live/live_demo rows may be logged, but an applied live/live_demo row must carry a Decision Lease id." `ml_advisory` never sets `applied` and never supplies a lease — it only appends advisory rows the existing `requires_governance` surface already audits.

### A.2 Existing gate stack (what P3 reuses)

| Gate | Signature | Reuse for P3 math gate |
|---|---|---|
| **`dsr_gate.compute_dsr`** | `compute_dsr(observed_sharpe, n_trials:int, n_observations=100, trial_sharpes=None, skew, excess_kurtosis) -> DsrResult` — `n_trials` is a **count** (K), theoretical `E[max SR_k]` via `_compute_expected_max_sharpe(K)`; `trial_sharpes` optional | **REUSE as-is** — peer-independent, single-config runnable. `DsrResult{observed_sharpe, deflated_sharpe, n_trials_K, psr_at_threshold, trials_max_sharpe, passes_threshold, insufficient_observations}` (`dsr_gate.py:127-133`). Q1 `N_trades_oos≥50` maps to `n_observations` precondition (DEFER if `insufficient_observations`). | `dsr_gate.py:381-440` |
| **`pbo_gate.compute_pbo`** | `compute_pbo(oos_returns_per_split:Sequence[np.ndarray], threshold, min_K, min_total_trades, s_slices) -> PboResult` — CSCV needs **N genuinely-different config OOS series** | **HONEST DEFER for single-config** — per 2026-06-08 Gap-A PBO ruling (memory): re-grouping one series ≠ N configs = PBO theater. ml_advisory candidates are single-config → `pbo_not_applicable`/`missing_cpcv_returns` defer (same outcome as fail-closed). PBO becomes active only when A-full (Rust replay variant series, P3b/P4) exists. | `pbo_gate.py:480-510` |
| **`leakage_check.check_feature_leakage`** | name-pattern only | **REUSE but CAP evidentiary weight** (M3, §F) | `leakage_check.py:41-78` |
| **`residual_alpha_gate.ResidualAlphaGate.evaluate`** | `evaluate(candidate_returns, factor_panel, protocol) -> ResidualEdgeReport` — fits factor beta on train window, computes OOS residual; `DEFAULT_REQUIRED_FACTORS=("btc","market")` | **REUSE the OLS/factor-fit machinery for B1** (§E) — but B1 needs different thresholds + a down-market sub-sample + altcap factor; not a drop-in. | `residual_alpha_gate.py:147-...`; factors `:23`; `ResidualEdgeReport{residual_mean_bps, beta_loadings, beta_edge_share, r_beta_retention, r_squared, ...}` `:101-127` |

---

## B. `ml_advisory.v1` capability — the P3 registry stanza (`enabled=false` default)

The P2 loader (`l2_capability_registry.py`) defines the typed `L2Capability` model (`:164-218`) and the `LANE_DIRECTION` table (`:67-76`). P3 adds **one `[[capability]]` stanza** to `settings/l2_capability_registry.toml` (today a skeleton with 0 stanzas — `l2_capability_registry.toml:15-16`). Because the 3 modes have different tier requirements and lanes, **P3 ships THREE capability stanzas** (one per mode) rather than one — this is cleaner than a single capability with a mode field, because `min_tier` and `lane` differ per mode and the registry's `min_tier`/`lane` are per-capability fields.

```toml
# settings/l2_capability_registry.toml — P3 adds these stanzas (all enabled=false)

[[capability]]
capability_id        = "ml_advisory.diagnose_leak"     # P3a — asserts NO alpha → ship before B1 final
enabled              = false                            # FAIL-CLOSED DEFAULT (loader :176)
min_tier             = "L1"                             # diagnosis needs no hypothesis-gen tier
tier_capability_flag = ""                               # no flag binding (L1 baseline)
model_tier           = "cloud_l2"                       # interpret survivors; Ollama screens (cascade §D)
cloud_model_pref     = "sonnet"
lane                 = "ml_backlog"                     # → LANE_DIRECTION="neutral" (registry :70)
output_schema_ref    = "ml_advisory.v1"
prompt_contract_ref  = "ml_advisory.diagnose_leak.v1"
out_of_bound_guard_ref = "ml_advisory.guard.v1"
novelty_gate         = false                            # diagnosis is not a hypothesis → no novelty dedupe
consequential_default = false
[capability.trigger]
kind          = "event"
spec          = "ml:training_complete"
debounce_secs = 900                                     # §F.1 trailing-edge (orchestrator _admit :347)
dedup_key     = "capability_id+spec+coarse_subject"
[capability.budget]
per_call_usd_cap = 0.50
daily_usd_cap    = 0.50                                 # ≤ DOC-08 $2/day (budget_config.toml:9)
tier_gated_spend = true

[[capability]]
capability_id        = "ml_advisory.interpret_result"  # P3a — asserts NO alpha → ship before B1 final
enabled              = false
min_tier             = "L1"
model_tier           = "cloud_l2"
cloud_model_pref     = "sonnet"
lane                 = "ml_backlog"                     # neutral
output_schema_ref    = "ml_advisory.v1"
prompt_contract_ref  = "ml_advisory.interpret_result.v1"
out_of_bound_guard_ref = "ml_advisory.guard.v1"
novelty_gate         = false
consequential_default = false
[capability.trigger]
kind          = "event"
spec          = "ml:training_complete"
debounce_secs = 900
[capability.budget]
per_call_usd_cap = 0.50
daily_usd_cap    = 0.50

[[capability]]
capability_id        = "ml_advisory.hypothesize"       # P3b — promotion-relevant → BLOCKED on B1 QC sign-off + altcap data
enabled              = false
min_tier             = "L3"                             # ★ can_generate_hypotheses first True at L3 (learning_tier_gate.py:203)
tier_capability_flag = "can_generate_hypotheses"       # bind to the L3+ flag (TierCapabilities :170)
model_tier           = "cloud_l2"
cloud_model_pref     = "sonnet"
lane                 = "ml_backlog"                     # neutral — backlog item, NOT a promotion lane
output_schema_ref    = "ml_advisory.v1"
prompt_contract_ref  = "ml_advisory.hypothesize.v1"
out_of_bound_guard_ref = "ml_advisory.guard.v1"
novelty_gate         = true                            # dedupe vs agent.lessons dead-modes (§H)
consequential_default = false
[capability.trigger]
kind          = "event"
spec          = "ml:training_complete"
debounce_secs = 900
[capability.budget]
per_call_usd_cap = 0.50
daily_usd_cap    = 0.50
```

**Grounding of each field decision:**
- **`enabled=false`** — fail-closed default; loader enforces (`l2_capability_registry.py:176` field default; `:265-285` reject branches).
- **`lane="ml_backlog"` → `direction="neutral"`** for ALL three modes — confirmed in `LANE_DIRECTION` (`l2_capability_registry.py:70`). **All three are `neutral`** (the iron rule: 0 new execution authority). The hypothesize mode lands a **backlog item**, which is NOT a promotion lane — promotion-relevance is about whether the *interpretation* claims promotion-readiness (§H regime_caveat guard), not about the lane. A backlog hypothesis is `neutral` (research sink); it only becomes promotion-relevant if it later passes B1+the full math gate and a human promotes it (P4/P5). This is why hypothesize can use `lane="ml_backlog"` (neutral) yet still be B1-gated for any promotion-relevant *output*.
- **`min_tier`**: `diagnose_leak`/`interpret_result` = **L1** (they assert no alpha, need no hypothesis generation). `hypothesize` = **L3** because `can_generate_hypotheses` is first `True` at L3 (`learning_tier_gate.py:203`; L1/L2 = `False` by default `:170`). `tier_capability_flag="can_generate_hypotheses"` binds the orchestrator's `effective_autonomy` STEP-2 tier-flag check (`l2_capability_registry.py:123-126`, `effective_autonomy` reads `tier_flag_value`).
- **`model_tier="cloud_l2"`** — the cascade's final interpret step is cloud-L2; the Ollama screen is an internal cascade stage, not a separate `model_tier` (§D explains why).
- **`daily_usd_cap=0.50`** ≤ DOC-08 `daily_usd_max=2.0` (`budget_config.toml:9`); orchestrator `_admit` stage-4 per-cap ceiling enforces (`l2_advisory_orchestrator.py:376-395`).

**`min_tier` for hypothesize is L3 — but the system is currently below L3.** This is correct and desirable: the hypothesize capability ships `enabled=false` AND `min_tier=L3`, so even if enabled it returns `TIER_LOCKED` (`effective_autonomy` STEP-2, `l2_capability_registry.py:122-126`) until the tier ladder reaches L3. P3b is structurally gated twice (enabled-flag + tier).

---

## C. The 3 advisory modes — input · PromptContract · output-schema · gate · sink

All three reuse the **one** `output-schema ml_advisory.v1` (design §E.2(0) lines 857-867) but have **distinct deterministic versioned PromptContracts** (design forbids Ollama generating prompts — `l2_prompt_contract_registry.py:8-11`). Each mode is registered in `l2_prompt_contract_registry.py` as a `PromptContract` + `OutputSchema` (the P2 registry has `get_prompt_contract`/`get_output_schema`/`resolve_contract_versions` — `:127-161`).

| Mode | Input (from ML pipeline, structured/pre-extracted) | PromptContract (versioned, deterministic) | Output (ml_advisory.v1 fields used) | Gate | Sink | New exec authority |
|---|---|---|---|---|---|---|
| **`diagnose_leak`** (P3a) | `{training_run_id, metrics{auc,sharpe,pbo,dsr,cost_edge_ratio}, leakage_check_findings[] (from `check_feature_leakage`), drift_signals[]}` | `ml_advisory.diagnose_leak.v1` (role=diagnose leakage/drift; constraints: cite evidence + **tag source_class** per M3) | `leak_drift_diagnosis{suspected_cause, evidence[{claim,kind,source_ref,source_class}], recommended_check}` | **guard (M3 source_class typing) + NO alpha gate** (asserts no alpha → no B1) | `mlde_shadow_recommendations` (advisory) + D3 | **0** |
| **`interpret_result`** (P3a) | `{training_run_id, metrics{...}, feature_importance[], regime_label}` | `ml_advisory.interpret_result.v1` (role=interpret training result, separate signal from regime artifact) | `result_interpretation{reading, regime_caveat, confidence}` | **guard (regime_caveat when bull-only) + NO alpha gate** | `mlde_shadow_recommendations` + D3 | **0** |
| **`hypothesize`** (P3b) | `{available_signal_axes[] (from `parquet_etl.EDGE_P3_FEATURE_NAMES`), dead_failure_modes[] (from `agent.lessons` V133), regime_label, alpha_wealth_remaining (stub=null in P3; P4 supplies)}` | `ml_advisory.hypothesize.v1` (role=propose pre-registerable feature hypotheses w/ economic mechanism) | `feature_hypotheses[{hid, statement, mechanism, falsification_test, signal_axes_used[], expected_direction, beta_neutralization_plan}]`, `backlog_items[]` | **guard (curve-fit + novelty + axes) + FULL math gate incl. B1** (any promotion-relevant verdict) | `mlde_shadow_recommendations` (backlog, advisory) + D3 | **0** |

**The mode field** drives which output sub-object is populated (design §E.2(0) line 858 `mode:"hypothesize|diagnose_leak|interpret_result"`). The `OutputSchema.required_fields` (`l2_prompt_contract_registry.py:79`) per mode: diagnose → `("mode","leak_drift_diagnosis")`; interpret → `("mode","result_interpretation")`; hypothesize → `("mode","feature_hypotheses")`.

**Ground for the cascade-context being structured-not-model-authored:** design §E.2(0) line 851 ("context (structured, extracted from the pipeline, NOT model-authored)"). The `ContextDistiller` (Ollama input-extraction seam, design §E.1) does the unstructured→structured extraction; the PromptContract template is checked-in (`PromptContract.template` field is a literal constant, `l2_prompt_contract_registry.py:64-65`, `frozen=True` `:57`).

---

## D. Cascade (§G.2) — Ollama screen → deterministic math/leak gate (the ONLY alpha validator) → cloud-L2 interpret on survivors

Design §G.2 (lines 1217-1244):
```
Ollama (generate + AutoMix self-verify + LOOSE coarse screen; recall ≥0.85, §G.2.1)   ← reuse layer2_critic
   │  survivors only
   ▼
DETERMINISTIC MATH GATE — the ONLY alpha validator (NOT the LLM). All hard members:
   STEP 0 [Q1]  N_trades_oos ≥ 50  → else verdict = DEFER (third state)
   then    DSR(N_eff) (dsr_gate.compute_dsr)  /  PBO (honest-defer single-config)
           leak-free precondition [M3]: requires shift1_compliance and/or is_oos_gap —
                   name_pattern_check (leakage_check.py) NOT sufficient
           beta-neutral [B1]: deterministic §N.1 (≥90d, |β_btc|<0.15, |β_alt|<0.15, |β_down|<0.15)
           walk-forward
   │  math survivors only (verdict == PASS)
   ▼
Cloud L2 (deep reasoning ONLY on math survivors: interpret / red-team)                  ← cloud cost only here
```

**Where the cascade wires into P2's already-shipped dispatch loop:** `l2_advisory_orchestrator.py:300-301` carries the comment "P2：executor 實際呼叫沿用既有 manual 路徑（layer2_engine 自帶 D3 write）。此處示範 guard + routing 決策骨架（**P3 接各 capability executor + parsed_output**）". P3's executor is a new function (call it `_run_ml_advisory_cascade(cap, context)`) that the orchestrator calls in place of the P2 manual-path stub — it runs: (1) Ollama screen (reuse `layer2_critic`, design §G.2.1 "layer2_critic precedent"); (2) the deterministic math gate (the only alpha validator — for `hypothesize`); (3) cloud-L2 `Layer2Engine.run_session` ONLY on math survivors (the orchestrator already owns `Layer2Engine` as one executor, `l2_advisory_orchestrator.py:28`, P2 §A.1). The parsed output flows through `guard_output` (`l2_out_of_bound_guard.py:74`) → `record_l2_call` (`l2_call_ledger_writer.py:113`) before routing.

**The iron rule: the LLM NEVER validates alpha.** The math gate is the only validator (design §G.2 line 1224, §E.2(0) line 880 "The math gate (DSR/PBO/leak) is the **only** validator — the ML advisor never validates its own hypotheses"). The cloud-L2 step runs only AFTER the math gate passes, and only to **interpret** survivors — it cannot reverse a math `reject` (the adjudicator already enforces `gate reject > L2 recommend`, `l2_conflict_adjudicator.py:77-82` `adjudicate_vs_gate`).

**For diagnose/interpret modes (P3a): there is no math gate** — they assert no alpha, so there is no alpha to validate. Their cascade is: Ollama-extract context → cloud-L2 diagnose/interpret → guard (M3 source_class / regime_caveat) → advisory sink. This is why **P3a can ship before B1 final** (§L).

**CC/E2/MIT grep target:** the math gate function has **0** LLM-invocation inside it; the cloud-L2 step is reachable only when the math gate returned PASS (a `reject`/`DEFER` short-circuits before any cloud call — also saves cost, root principle 13).

---

## E. ★ Math gate includes `beta_neutral_check` (B1, §N.1) — **DETERMINATION: MUST BE BUILT** (data partially exists)

### E.1 Does `beta_neutral_check` already exist? — **NO (must be built); but reusable machinery exists**

- **`beta_neutral_check`** as a named, wired-into-the-gate-stack check: **0 hits** (grep `beta_neutral` over all `.py` = empty). **Must be built.**
- **HOWEVER, `residual_alpha_gate.py` already exists** (the 2026-06-05 residual-producer build) and computes factor-beta residualization: `DEFAULT_REQUIRED_FACTORS=("btc","market")` (`residual_alpha_gate.py:23`), fits beta on a train/prior window, computes OOS residual alpha (`:4-5`), produces `ResidualEdgeReport{residual_mean_bps, beta_loadings:dict[str,float], beta_edge_share, r_beta_retention, r_squared, psr_residual, dsr_residual, pbo_residual, verdict}` (`:101-127`). **This is the OLS/factor-fit machinery B1 reuses** — but it is NOT B1 itself:
  - `residual_alpha_gate` thresholds are `beta_edge_share < 0.5` / `r_beta_retention > 0.5` (`:90-91`); B1 wants **`|β_btc|<0.15 AND |β_alt|<0.15 AND |β_down|<0.15`** deterministic coefficient thresholds (design §N.1 (3)).
  - `residual_alpha_gate` takes a **caller-supplied `factor_panel`** (`:147-149`) — it does NOT produce the BTC/altcap return series or the down-market sub-sample. Those are the missing data inputs.
  - `residual_alpha_gate` has no down-market regime-conditional sub-sample re-check (design §N.1 (4)).
- **Memory corroboration** (`feedback_*` / `project_2026_06_04_external_framework_audit_and_self_audit`): "grep beta=0 = the dimension that killed you 5 times is NOT wired into the gate." The residual machinery exists but is not bound into the production/promotion gate as a deterministic `|β|<0.15` precondition. **B1 = build the deterministic `beta_neutral_check` reusing `residual_alpha_gate`'s OLS, with B1's thresholds + the altcap factor + the down-market sub-sample.**

### E.2 B1 construction spec (design §N.1, lines 1862-1920 — QC-gated)

A new deterministic function `beta_neutral_check(candidate_returns, btc_returns, altcap_returns, down_market_mask, *, window_days=90, threshold=0.15) -> BetaNeutralResult{verdict:"pass|fail|DEFER", beta_btc, beta_alt, beta_down, beta_upper, se, n_bars, reasons[]}`:
1. **Dual-factor BTC+altcap MANDATORY** (design §N.1 (1) lines 1873-1884): `r_strat = α + β_btc·r_btc + β_alt·r_altcap + ε`. **BTC-only → DEFER** (a BTC-only model scores alt-down-beta candidates as "neutral" — the exact masquerade, design line 1880).
2. **OLS at daily/4h, NOT 1m** (execution-plan §1 B1 line 65; design §N.1 (2) "candidate's native bar" but the factor regression at daily/4h).
3. **`|β_btc|<0.15 AND |β_alt|<0.15`** on ≥90d window (design §N.1 (3) lines 1893-1897; `BETA_NEUTRAL_THRESHOLD=0.15` deterministic constant).
4. **Down-market `|β_down|<0.15`** (design §N.1 (4) lines 1899-1906): β estimated separately on the down-market sub-sample. Down-market def = **30d drawdown >8% OR 7d return <-5%** (execution-plan §1 B1 line 65), **lagged-PIT** (leak-free, not future-looking), **≥30 bars else DEFER**.
5. **`β_upper = β + 1.96·SE < 0.20`** (execution-plan §1 B1 line 65; design §N.1 NOTE line 1911) — the upper CI bound, not just the point estimate.
6. **Insufficient history (<90d aligned returns) → DEFER**, never auto-pass (design §N.1 (2) lines 1890-1891).

**One computation, three consumers** (design §N.1 (5) lines 1908-1914): the B1 result is computed once and consumed by (a) the §G.2 math gate (B1 is a hard precondition at the same tier as DSR; a candidate failing B1 cannot pass), (b) the §N live-cross packet (P5), (c) the §E(ii) regime-risk-advisor `portfolio_beta` input (a different capability, not P3). No capability ever substitutes its own beta.

### E.3 ★ B1 data availability — **DETERMINATION**

| B1 data requirement | Status | Ground |
|---|---|---|
| **BTC return series** (daily/4h, PIT) | **EXISTS** | `research.alpha_klines_*` daily kline history (V125 `alpha_history_storage` + the daily-kline backfill producing 14505 daily lines, memory `project_2026_06_02_aeg_trend_listing_infra_deployed`). BTC daily closes → return series derivable. |
| **Leak-free down-market regime label (lagged-PIT)** | **SCHEMA + WRITER EXIST; population owed-verify** | **V127 `research.aeg_regime_labels`** has `ret_30d`, `ret_90d`, `main_regime`, `market_anchor_regime` (BTC-anchored), **versioned + leak-free PIT, daily bars** (`V127__aeg_regime_labels.sql:5-21` design; `:68-71` ret_30d/ret_90d feature cols). The down-market mask (30d drawdown >8% OR 7d return <-5%) is **derivable from `ret_30d`/`ret_90d` + a 7d return** (7d not directly stored but computable from daily klines). The writer exists (`helper_scripts/research/aeg_regime_runner/db_writer.py:28-79` writes ret_30d/ret_90d/main_regime). **BUT V127 is populated only via the runner's explicit `--write-db` path** (`db_writer.py:6` "默認 runner 只產 artifact"); the migration itself builds only the 2 tables, not the runner data (`V127:17-21`). **Whether V127 is populated on Linux = OWED runtime-verify (J).** |
| **PIT cap-weighted altcoin basket return series** | **DOES NOT EXIST — MUST BE CONSTRUCTED** | grep `altcap\|cap_weight\|basket\|market_cap\|weighted.*return` over `helper_scripts/research/` + `program_code/ml_training/` = **0 producer**. FND-2 `fnd2_pit_universe` produces a **symbol-list artifact** (`included`/`cohort_ids`/`alive_from_utc`/`alive_to_utc` — `aeg_breadth_ladder/universe_artifact.py:3-10`), **NOT a cap-weighted return series** (`fnd2_pit_universe/builder.py` has 0 return/price/cap-weight; `artifact.py` UNIVERSE_COLUMNS are symbol-list only). The PIT universe gives *which symbols are alive when* (survivorship-correct); a cap-weighted **return** basket additionally needs per-symbol PIT market caps (or a circulating-supply proxy) × daily returns. **This is the single biggest B1 data gap.** |

**B1 verdict on data:** BTC factor = ready. Down-market regime = schema/writer ready, population owed-verify. **Altcap basket = does not exist; must be constructed** — this is a **QC/MIT-data construction item** (execution-plan §0 line 48 "PIT cap-weighted altcoin basket... exist (or specify construction)"). PA's recommendation: QC owns the altcap construction spec (per-symbol PIT cap proxy × FND-2 universe membership × daily returns); **until it exists, B1's dual-factor model cannot be computed → `hypothesize` mode's promotion-relevant verdict DEFERs (BTC-only → DEFER per design §N.1 (1))**. This does NOT block P3a (diagnose/interpret) and does NOT block shipping the B1 *function* with a DEFER-on-missing-altcap path.

### E.4 Q1 sample bar (design §G.2 STEP 0, line 1225)

`N_trades_oos ≥ 50` else verdict = **DEFER** (third state, not PASS/FAIL). Maps to `dsr_gate.compute_dsr`'s `n_observations`/`insufficient_observations` (`dsr_gate.py:122-124`). DEFER propagates to §C.3 (cannot auto-promote) and the D3/§N packet (`gate_verdict:"DEFER"`). Execution-plan §1 Q1 line 71.

---

## F. M3 leak typing — `source_class` mandatory; **shift1_compliance/is_oos_gap MUST BE BUILT**

### F.1 Determination: do `shift1_compliance` / `is_oos_gap` (as leak-typing source-classes) exist?

- **`shift1_compliance`**: **0 hits** anywhere (grep `shift1_compliance` over all `.py` = empty). **Must be built.**
- **`is_oos_gap`**: **exists but is a NAMESAKE-DIFFERENT metric.** `sample_weight_sensitivity.py:329-334,433,440` has an `is_oos_gap` that is a **train-vs-OOS RMSE gap-ratio overfitting detector** (`{mean_train_rmse, mean_oos_rmse, gap_ratio, withdraw_baseline}`), NOT the M3 `is_oos_gap` source-class (which means "a real in-sample → out-of-sample **temporal** gap", design §E.2(0) line 897). **The M3 is_oos_gap leak-typing producer must be built** (or M3's `is_oos_gap` source_class repurposed — QC/MIT decide).
- **Only `name_pattern_check` exists** (`leakage_check.py`, 78 lines confirmed — name-substring/prefix matching only, `:57-68`).

### F.2 M3 spec (design §E.2(0) lines 884-903, execution-plan §1 M3 line 74)

Every leak/PIT claim in `diagnose_leak` output carries `source_class ∈ {name_pattern_check, shift1_compliance, is_oos_gap}` (the output-schema `evidence[].source_class` field, design §E.2(0) line 864). **`ml_advisory` may NOT claim `leakage_check` output as leak-free PIT evidence** (design line 892) — a `name_pattern_check` pass is a weak, necessary-not-sufficient screen. A promotion-relevant "leak-free" assertion (used by the math gate's leak precondition for `hypothesize`) requires `shift1_compliance` and/or `is_oos_gap`, NOT `name_pattern_check` (design lines 894-900). The out-of-bound guard (§G) and the math gate both enforce this typing.

**This caps `leakage_check`'s evidentiary weight; it does NOT remove it** (it stays a cheap first screen, design line 901-902). Building `shift1_compliance`/`is_oos_gap` is owned by MIT/QC (design line 903; execution-plan §L). For P3a's `diagnose_leak`, the immediate requirement is the **source_class typing enforcement** (guard rejects an evidence row that claims leak-free PIT backed only by `name_pattern_check`); the actual `shift1_compliance`/`is_oos_gap` *producers* are a MIT-owned build that `diagnose_leak` *references* but does not itself implement.

---

## G. M4 Ollama calibration (§G.2.1) — recall ≥ 0.85 = "loose"; below → disable screen

Design §G.2.1 (lines 1246-1277):
- **Held-out good/bad benchmark set** (good = historically demo-confirmed discoveries / correct post-hoc diagnoses; bad = `agent.lessons` V133 dead-modes). Versioned, grows with outcomes.
- **Measure recall of the SCREEN** (pass-through vs coarse-reject), not the final answer. **Recall floor = 0.85** (PA default; MIT may raise) — the screen lets through ≥85% of genuinely-good hypotheses. The screen is tuned for recall; the math gate provides precision (defense-in-depth, design line 1267).
- **"Loose" = most-permissive operating point that still meets recall ≥ 0.85** while removing obvious dead-modes (design line 1268-1272).
- **Below recall 0.85 → screen DISABLED** (degrade to "no screen" — everything goes to the math gate; costs more cloud but loses no alpha) + flagged to MIT (design line 1271-1272).
- **Re-calibration**: on benchmark-version bump + at least monthly; logged (precision/recall/threshold/version) for §O metric + MIT audit (design line 1273-1275).
- **MIT owns**: benchmark construction, recall floor, false-kill-vs-false-pass trade-off (design line 1276-1277). Execution-plan §1 M4 line 75.

**Wiring into the fail-safe SM:** "screen disabled (no screen)" is a *cascade-internal* degrade (everything to math gate); it is NOT the orchestrator `FailSafeState.DEGRADE_OLLAMA` (that is when Ollama is *unavailable*, `l2_advisory_orchestrator.py:518-521`). The screen-disabled state must be logged to D3 gate-seam (`record_gate_seam(gate_id="ollama_screen", verdict="disabled", details={recall, threshold, version})`) so MIT can audit, and must flag MIT — but trading/baseline is untouched (subtraction-only).

---

## H. Out-of-bound guard extension — `ml_advisory.guard.v1` (P3 makes `get_guard` a callable registry)

The P2 guard (`l2_out_of_bound_guard.py`) ships generic clauses (range-clamp leverage/size, negative-cost reject, schema-nonconformant reject, `available_signal_axes`/`referenced_signal_axes` reject — `:74-151`) and a placeholder `get_guard(guard_ref)` that returns the ref echo (`:154-159`, comment "P3 改為回 callable registry"). **P3 turns `get_guard` into a callable registry** keyed by `out_of_bound_guard_ref`, and registers `ml_advisory.guard.v1` with the capability-specific clauses (design §E.2(0) lines 868-873):

1. **reject `signal_axes_used ⊄ available_signal_axes`** (no inventing data, design line 869). `available_signal_axes` ground-truth = `parquet_etl.EDGE_P3_FEATURE_NAMES` (`parquet_etl.py:40`, the live feature axes incl. `funding_rate`/`is_funding_settlement_window`/etc.). The P2 guard already has the axes-subset check skeleton (`l2_out_of_bound_guard.py:113-125`) — P3 binds `available_signal_axes` to the real axis list and checks `feature_hypotheses[].signal_axes_used`.
2. **reject empty mechanism** (curve-fit guard, design line 870) — a `feature_hypothesis` with empty `mechanism` is rejected.
3. **dedupe vs `dead_failure_modes` by similarity** (novelty, design line 871). **`dead_failure_modes` source = `agent.lessons` V133** (the L2 Reflexion lesson store with pg_trgm trigram similarity, `V133__agent_lessons.sql` — `persist_lessons` single-INSERT entry, trigram retrieve). `dead_failure_modes` literal = **0 hits** (it is NOT a table; it is the `agent.lessons` dead-mode rows retrieved via trigram). The guard dedupes `feature_hypotheses` against retrieved dead-modes.
4. **reject promotion-ready interpretation missing `regime_caveat` when bull-only** (design line 872) — a `result_interpretation` asserting promotion-readiness without a `regime_caveat`, when metrics are flagged bull-only, is rejected (defense-in-depth vs Alpha Evidence Governance, CLAUDE.md).

**The guard catches *form*; the math gate catches *substance*** (design §E.2(0) line 984, P2 guard module-note `:8-9`). A guard `reject` means the proposal is never routed to an applier (logged-and-dropped, `l2_out_of_bound_guard.py:88` + orchestrator routing). **The guard is deterministic — 0 model calls inside** (`l2_out_of_bound_guard.py:16,19` "純函數 + 確定性 bounds"; CC/E2 grep target).

---

## I. D3 integration — every call writes the ledger + gate-seam

Every `ml_advisory` cascade call writes **one** D3 row via `record_l2_call` (`l2_call_ledger_writer.py:113-139`) with: `l2_reply_id`, `capability_id` (the registry id, e.g. `ml_advisory.hypothesize`), `trigger`, `model`, `contract_ver`/`schema_ver` (from `resolve_contract_versions`, `l2_prompt_contract_registry.py:137-161`), `system_prompt`, `input_context`, `raw_response`, `parsed_output`, **`guard_verdict`** (the §H guard result, V134 column), **`fact_inf_assm`** (the fact/inference/assumption tags from the output, design §E.2(0) line 848 "label fact|inference|assumption"), tokens/cost/latency. The writer sanitizes all large-text columns before INSERT (P1 D3, `:145-151`).

Each deterministic gate stage (Ollama screen, Q1 sample, B1 beta, DSR, leak-typing) writes a **gate-seam row** via `record_gate_seam` (`l2_call_ledger_writer.py:314`) as the artifact flows — so the §D.4 fault-localization replay can reconstruct exactly which gate stage produced which verdict (design §G.2 DEFER propagation). The orchestrator already writes the admission gate-seam (`l2_advisory_orchestrator.py:466-491`); P3 adds the math-gate-stage seams inside the cascade executor.

---

## J. Read-before-build verification items (flag Linux/DB; do NOT block design)

| Item | Status | Owed-verify |
|---|---|---|
| ML-pipeline output shape | **CLEARED** (§A, ground:file:line) | none |
| Advisory sink (`mlde_shadow_recommendations` applied=false/requires_governance=true) | **CLEARED** (§A.1, `V031:432-433`) | none |
| `beta_neutral_check` exists? | **CLEARED — NO (must build); residual_alpha_gate reusable** (§E.1) | none (design determination) |
| `shift1_compliance` exists? | **CLEARED — NO (must build)** (§F.1) | none |
| `is_oos_gap` (leak-typing) exists? | **CLEARED — namesake-different metric only; leak-typing producer must build** (§F.1) | none |
| BTC return series (B1 factor) | **EXISTS** (V125 + daily-kline backfill) | none |
| **V127 `research.aeg_regime_labels` POPULATED on Linux?** | schema+writer exist; population via `--write-db` only | **OWED — Linux `SELECT count(*) FROM research.aeg_regime_labels` + check `classifier_version` pinned + ret_30d/ret_90d non-null coverage** |
| **PIT cap-weighted altcap basket return series** | **DOES NOT EXIST** (§E.3) | **OWED — QC/MIT-data construction spec** (biggest B1 gap) |
| `available_signal_axes` ground-truth | **CLEARED** (`parquet_etl.EDGE_P3_FEATURE_NAMES:40`) | none |
| `dead_failure_modes` source (`agent.lessons` V133) | **CLEARED** (V133 trigram store) | **OWED-soft — Linux `SELECT count(*) FROM agent.lessons` (is it populated for novelty dedupe to be meaningful?)** |
| `learning.model_registry` (training pipeline sink) | exists (V023) | none (read-only for ml_advisory) |

None of these block the **design**; the two hard OWED items (V127 population + altcap construction) gate **P3b's promotion-relevant verdict**, not P3a and not the design.

---

## K. Reuse vs new —逐項 ground-confirmed

| Build | Decision | Ground |
|---|---|---|
| P2 Orchestrator dispatch loop (admission/contract/guard/routing/fail-safe) | **REUSE** (P3 hooks the executor at the `:300-301` seam) | `l2_advisory_orchestrator.py:232-312` |
| P2 capability registry + LANE_DIRECTION + effective_autonomy + loader | **REUSE** (P3 adds 3 TOML stanzas) | `l2_capability_registry.py:67-349`; `l2_capability_registry.toml:15-16` (skeleton) |
| P2 PromptContract/OutputSchema registry + resolve_contract_versions | **REUSE + EXTEND** (register `ml_advisory.*.v1` contracts/schemas) | `l2_prompt_contract_registry.py:113-161` |
| P2 out-of-bound guard generic clauses + `get_guard` placeholder | **REUSE + EXTEND** (make `get_guard` a callable registry; add `ml_advisory.guard.v1`) | `l2_out_of_bound_guard.py:74-159` |
| P2 conflict adjudicator (`adjudicate_vs_gate` gate-reject>L2-recommend) | **REUSE** (math gate reject beats LLM interpret) | `l2_conflict_adjudicator.py:50-82` |
| P1 D3 writer (`record_l2_call`/`record_gate_seam`) | **REUSE** | `l2_call_ledger_writer.py:113/314` |
| `Layer2Engine.run_session` (cloud-L2 interpret, one executor) | **REUSE** | `layer2_engine.py:538`; `is_simulated=True`/`shadow_only` `:16` |
| `layer2_critic` (Ollama screen self-verify) | **REUSE** | design §G.2.1 "layer2_critic precedent" |
| `ContextDistiller` (Ollama input-extraction) | **REUSE** | design §E.1 |
| `dsr_gate.compute_dsr` (DSR, count-based, single-config) | **REUSE as-is** | `dsr_gate.py:381` |
| `pbo_gate.compute_pbo` (honest-defer single-config) | **REUSE (defer)** | `pbo_gate.py:480`; 2026-06-08 Gap-A ruling |
| `leakage_check.check_feature_leakage` (name_pattern_check, capped) | **REUSE (M3-capped)** | `leakage_check.py:41` |
| `residual_alpha_gate` OLS/factor-fit machinery | **REUSE the machinery for B1** | `residual_alpha_gate.py:147`, factors `:23` |
| ML pipeline (`run_training_pipeline`/`mlde_shadow_advisor`) as input source | **REUSE (read)** | §A |
| `agent.lessons` V133 (dead_failure_modes novelty) | **REUSE** | `V133__agent_lessons.sql` |
| `parquet_etl.EDGE_P3_FEATURE_NAMES` (available_signal_axes) | **REUSE** | `parquet_etl.py:40` |
| V127 `aeg_regime_labels` / V125 daily klines (B1 regime + BTC factor) | **REUSE (read)** | `V127:5-21`, `db_writer.py:28-79`; V125 |
| **3 `ml_advisory.*.v1` PromptContracts + OutputSchemas** | **NEW** | greenfield (register in P2 registry) |
| **`ml_advisory` cascade executor** (`_run_ml_advisory_cascade`) | **NEW** | greenfield (the P2 `:300-301` seam) |
| **`ml_advisory.guard.v1` clauses** (curve-fit/novelty/axes/regime_caveat) | **NEW** | greenfield (extend `get_guard`) |
| **★ `beta_neutral_check` (B1) deterministic function** | **NEW (QC-gated)** | greenfield; reuses `residual_alpha_gate` OLS |
| **Q1 `N_trades_oos≥50` DEFER precondition** | **NEW** | greenfield (wraps `dsr_gate`) |
| **M3 source_class typing enforcement** | **NEW** (guard + math-gate leak precondition) | greenfield |
| **M4 Ollama screen calibration harness** | **NEW (MIT-owned)** | greenfield |
| **PIT cap-weighted altcap basket producer** | **NEW (QC/MIT-data, blocks P3b)** | greenfield (no producer) |
| **`shift1_compliance` / leak-typing `is_oos_gap` producers** | **NEW (MIT-owned, P3b leak precondition)** | greenfield |

**Net P3 framing:** the orchestration plumbing is ~all reused from P2; the net-new is the **capability content** (3 contracts, the cascade executor, the guard clauses) + the **alpha-validation substance** (B1, Q1, M3 typing, M4 calibration) + the **two data builds** (altcap basket, shift1/is_oos producers) that gate P3b only.

---

## L. ★ Recommended P3 split — P3a (ship before B1) vs P3b (B1 QC sign-off + altcap data)

Execution-plan §1 line 79-82 + §2 line 197-199 explicitly: "Diagnose/interpret-only modes (which assert no alpha) may ship earlier. ... hypothesize→promotion-relevant verdict may not [before B1 final]." PA recommends a **hard P3a/P3b split**:

| Split | Modes | Gates | Sign-off dependency | Can ship when |
|---|---|---|---|---|
| **P3a** | `ml_advisory.diagnose_leak` + `ml_advisory.interpret_result` | guard (M3 source_class typing + regime_caveat) + **NO alpha gate** (assert no alpha) + M4 screen calibration | **E2 + MIT (M3 typing + M4 recall)** — **NOT B1** | **Now** (after E2/MIT/E4/QA); does NOT wait on B1 final numbers or altcap data |
| **P3b** | `ml_advisory.hypothesize` (promotion-relevant verdict) | guard + **FULL math gate incl. B1** (`beta_neutral_check`) + Q1 + M3 leak precondition (shift1/is_oos) | **QC (B1 final numbers + altcap construction + leak-free PIT) + MIT (M3 producers + M4)** | **After**: (1) QC signs off B1 four numbers {factor set / window / threshold / down-market rule}, (2) the altcap basket producer exists + V127 populated, (3) shift1_compliance/is_oos_gap producers exist |

**Why this split is correct and safe:**
- P3a **asserts no alpha** — a leak diagnosis or a result interpretation makes **no promotion-relevant claim** that B1 guards against. The masquerade B1 defends (down-beta dressed as alpha) only matters when a hypothesis claims edge. P3a can therefore ship the full cascade (proving the Ollama→cloud path + the D3 + the M3 typing + the M4 calibration) on the lowest-blast surface, **without** the altcap data dependency.
- P3b's `hypothesize` produces a backlog item; that item only becomes promotion-relevant if it later passes the math gate. **B1 is the unattended-gate command-line** (design §N.1 line 1864-1867) — shipping `hypothesize` with a promotion-relevant verdict before B1 final + altcap data would let a down-beta masquerade through an unattended gate (the exact failure that killed 5 candidates). P3b is **hard-blocked** on B1 QC sign-off.
- **Tier alignment reinforces this**: P3b's `min_tier=L3` (`can_generate_hypotheses` first True at L3, `learning_tier_gate.py:203`); the system is below L3, so `hypothesize` is doubly gated (enabled=false + TIER_LOCKED) regardless. P3b is genuinely not-yet-needed; P3a delivers the cascade proof now.

**This split is the single most important P3 recommendation:** ship P3a to prove the cascade + D3 + M3 + M4 on a zero-alpha surface; defer P3b until B1 QC sign-off + the altcap basket build. It de-risks the phase and avoids a beta-masquerade leak through an unattended gate.

---

## M. Migration requirement judgment — **P3 needs NO migration** (V137 still reserved-not-used)

**Determination: P3 ships ZERO DB migration.** Grounded per surface:
- **Advisory sink** = the **existing** `learning.mlde_shadow_recommendations` (V031, `:407-434`) — ml_advisory appends advisory rows (`applied=false`/`requires_governance=true`); no new column, no new table.
- **D3 ledger** = the **existing** `agent.l2_calls` (V134) + gate-seam `learning.l2_gate_seam_log` (V135) — `guard_verdict`/`fact_inf_assm` columns already exist (V134); no new column.
- **Novelty / dead_failure_modes** = the **existing** `agent.lessons` (V133) trigram store — no new table.
- **Capability registry** = **TOML SSOT** (`settings/l2_capability_registry.toml`) — P3 adds stanzas, not a DB table (the operator-confirmed "P2 ships TOML-SSOT, no DB table, no V137" carries forward).
- **B1 regime + factor data** = the **existing** V127 `aeg_regime_labels` + V125 daily klines (read-only) — no new table. **EXCEPT the altcap basket**: if QC's altcap construction needs a *persisted* cap-weighted return series (vs computed-on-the-fly), that producer might want a `research.altcap_basket_returns` table → **that would be V137** (verified next-free: V134/V135/V136 on disk, V137+ absent). **PA recommendation: compute the altcap basket from existing daily klines + a PIT cap proxy on-the-fly (or as a research artifact file, mirroring FND-2's CSV-artifact pattern), avoiding a new migration.** If QC decides a persisted table is needed, V137 owes a Linux PG dry-run + double-apply idempotency (E4).

**Verdict: no V137 in P3 as designed.** V137 remains reserved-not-used; it is taken ONLY IF QC's altcap construction requires a persisted DB table (a QC decision, §N). The shift1_compliance/is_oos_gap producers are compute, not schema (they read existing data) — no migration.

---

## N. E1 acceptance mapping + sign-off points

Maps each deliverable to execution-plan §2 Phase-3 (lines 192-217) + gating (B1/Q1/M3/M4/C2) + §3 cross-phase invariants (lines 328-341). **Route handlers parse→call→format only; business logic below (CLAUDE.md §七).**

| Deliverable | E1 builds | E2 reviews | **QC verifies** | **MIT verifies** | E4 |
|---|---|---|---|---|---|
| **3 capability stanzas (TOML)** | `ml_advisory.{diagnose_leak,interpret_result,hypothesize}`; all `enabled=false`; min_tier L1/L1/L3; lane=ml_backlog(neutral) | loader accepts; fail-closed default | — | — | Mac+Linux test pass |
| **3 PromptContracts + OutputSchemas** | deterministic versioned templates; Ollama-forbidden-to-generate; `contract_ver`/`schema_ver`→every D3 row | template from registry only (no model generates) | — | — | — |
| **cascade executor** | Ollama screen → math gate (ONLY validator) → cloud-L2 interpret on survivors; `record_l2_call`+gate-seams; cost only on survivors | route-thin; LLM never validates alpha; 0 order/lease imports | — | **M4 recall ≥0.85 screen calibration** | — |
| **★ `beta_neutral_check` (B1)** | dual-factor BTC+altcap (BTC-only→DEFER); OLS daily/4h; `|β_btc|<0.15 AND |β_alt|<0.15`; down-market `|β_down|<0.15` (30d dd>8% OR 7d<-5%, lagged-PIT, ≥30 bars else DEFER); `β_upper=β+1.96SE<0.20`; reuses residual_alpha_gate OLS | deterministic (no model inside); fail-closed DEFER | **B1 FINAL NUMBERS {factor set / window / threshold / down-market rule} + altcap construction spec + leak-free PIT** | — | (V137 dry-run IF altcap persisted) |
| **Q1 sample bar** | `N_trades_oos≥50` else DEFER (third state); propagates to §C.3 + D3 | DEFER ≠ PASS | **Q1 threshold ratify** | — | — |
| **M3 leak typing** | every leak claim carries `source_class`; name_pattern_check NOT leak-free PIT; guard+math-gate enforce | source_class mandatory in schema | **leak-free PIT precondition** | **M3: shift1_compliance/is_oos_gap producers; name_pattern_check capped** | — |
| **M4 calibration harness** | held-out good/bad benchmark; recall≥0.85=loose; below→disable screen+flag MIT; logged | screen-disabled = subtraction-only | — | **M4: benchmark construction + recall floor + cost trade-off** | — |
| **`ml_advisory.guard.v1`** | reject axes⊄available; reject empty mechanism; dedupe vs agent.lessons; reject promotion-ready w/o regime_caveat when bull-only | guard pre-proposal; deterministic (no model); reject→never routed | — | — | — |
| **(write endpoints, if any)** | capability enable/disable = `Depends(_require_operator_auth)` (C2: no can_auto_deploy_to_paper branch) | parse→call→format; operator-scope | — | — | — |

**Sign-off chain (execution-plan §2 lines 218-219):** PA (this doc — ML-pipeline seam read in full) → **E1** → **E2** → **QC (B1 final numbers + leak-free PIT features)** → **MIT (M3 leak coverage + M4 recall calibration)** → **E4** → **QA** → PM. **CC re-checks cross-phase invariants** (§3): L2 touches none of `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`/`execution_authority`/`system_mode`/lease-trading; `can_modify_live_config=False@all-tiers` (`learning_tier_gate.py:178`); single write entry (no order path); AI≠command; survival>profit (B1+Q1 are hard gate members so the down-beta/small-sample masquerades cannot pass an unattended gate); AI cost≥edge (cloud only on math survivors).

**P3a/P3b split sign-off note:** P3a (`diagnose_leak`+`interpret_result`) gates on **E2 + MIT (M3+M4)** only — **NOT B1**. P3b (`hypothesize`) gates on **QC (B1 final + altcap + leak-free PIT) + MIT (M3 producers + M4)**.

---

## O. Side-effect / hard-boundary checklist (PA discipline)

1. **Other modules importing the changed surface?** P3 adds 3 TOML stanzas + 3 contracts + guard clauses + a cascade executor + B1 — all **additive** to the P2 mesh. The wiring change is at the P2 orchestrator `:300-301` seam (the manual-path stub → the ml_advisory executor for ml_advisory capabilities); the existing manual-trigger path (`l2.manual_reasoning`) stays unchanged (it is a different capability — no regression). The ML pipeline (`run_training_pipeline`/`mlde_shadow_advisor`) is **read-only consumed** — no change to those modules.
2. **Mocked functions?** The cascade executor + B1 are new; tests verify **intent** (LLM never validates alpha; B1 rejects down-beta masquerade; M3 source_class enforced; M4 screen-disable is subtraction-only; DEFER propagates), not only behavior (CLAUDE.md Operating Style 9).
3. **asyncio/threading boundary?** The cascade executor is async (drives `Layer2Engine.run_session`, async `layer2_engine.py:538`); the orchestrator `_admit` is sync under `RLock` (`l2_advisory_orchestrator.py:174,337`); B1/math gate are pure sync compute; D3 writer is sync PG INSERT via the existing pool. **No new asyncio/thread mixing** beyond the P2 pattern.
4. **API response schema change?** ml_advisory output flows to the **existing** `mlde_shadow_recommendations` (no schema change) + D3 (no schema change). If P3 adds a read route for ml_advisory status, it is additive (parse→call→format). No breaking change to existing routes.
5. **Rust ↔ Python IPC schema?** **None in P3.** No live table, no engine change, no Rust touch. P3 is Python control-plane + TOML + (read-only) research DB. The trading-truth layer (Rust) is untouched.

**Hard boundaries (CLAUDE.md §四) — all honored:**
- No `live_execution_allowed`/`max_retries`/`system_mode`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`/`execution_authority` touch. ✔
- `direction=neutral` for all 3 modes (`LANE_DIRECTION["ml_backlog"]="neutral"`, `l2_capability_registry.py:70`); **0 new execution authority**; feeds existing `applied=false`/`requires_governance=true` sink. ✔
- **LLM never validates alpha** — the deterministic math gate (incl. B1) is the only validator; cloud-L2 interprets only math survivors (§D). ✔
- bull-only/rally-dominated results labeled `regime-bet/learning-only` (Alpha Evidence Governance; the regime_caveat guard, §H). ✔
- `can_modify_live_config=False@all-tiers` already in code, untouched (`learning_tier_gate.py:178`). ✔
- `can_generate_hypotheses` correctly gates `hypothesize` at L3+ (`learning_tier_gate.py:203`). ✔
- New PromptContracts/guards registered in the existing P2 registries (not new singletons — they are registry entries). ✔
- **Design-only, no code/no apply/no deploy. Does NOT exceed P3 scope** (online-FDR loop=P4, feedback/GUI=P5 not designed here). ✔

---

## P. Verdict

**DESIGN-ONLY, conditionally E1-ready.** No code, no migration apply, no DB write, no deploy was performed. Every assertion grounded in `file:line`.

**ML-pipeline seam:** read in full (§A) — `run_training_pipeline`/`mlde_shadow_advisor`/`leakage_check`/V031/`mlde_shadow_recommendations` input·output·sink grounded; **advisory sink CONFIRMED** schema-enforced (`applied=false`/`requires_governance=true`, `V031:432-433`) AND producer-enforced.

**beta_neutral_check:** **MUST BE BUILT** (0 hits); but the OLS/factor-fit machinery of the existing `residual_alpha_gate.py` (`DEFAULT_REQUIRED_FACTORS=("btc","market")`, `:23`) is reusable. B1 is a NEW deterministic function with B1's thresholds (`|β|<0.15`, down-market `|β_down|<0.15`, `β_upper<0.20`) + the altcap factor + the down-market sub-sample.

**B1 data availability:** BTC factor = **ready** (V125 daily klines). Down-market regime = **schema+writer ready (V127), population owed Linux-verify**. **Altcap cap-weighted basket return series = DOES NOT EXIST — must be constructed (QC/MIT-data; the biggest B1 gap).**

**shift1_compliance / is_oos_gap (M3 leak-typing):** **shift1_compliance = 0 hits (must build); is_oos_gap = only a namesake-different RMSE-gap metric exists (leak-typing producer must build)**. P3a needs only the source_class **typing enforcement**; the producers are MIT-owned and gate P3b.

**3 modes + cascade:** designed (§C/§D). All `direction=neutral`, 0 new exec authority, feeds existing advisory sink. Cascade = Ollama screen (recall≥0.85) → deterministic math gate (ONLY alpha validator) → cloud-L2 interpret on survivors. **LLM never validates alpha.** Wires into the P2 orchestrator `:300-301` executor seam.

**P3a/P3b split (the key recommendation):** **P3a** (`diagnose_leak`+`interpret_result`, assert no alpha) ships on **E2+MIT(M3+M4)** — **NOT B1** — proving the cascade+D3+M3+M4 on a zero-alpha surface now. **P3b** (`hypothesize`, promotion-relevant verdict) is **hard-blocked** on **QC B1 final numbers + altcap construction + leak-free PIT + (L3 tier)**.

**Migration:** **P3 needs NO migration** (advisory sink V031, D3 V134/V135, novelty V133, regime V127/V125 all existing; registry=TOML). V137 reserved-not-used — taken ONLY IF QC decides the altcap basket needs a persisted DB table (PA recommends on-the-fly/artifact construction to avoid migration).

**Residual Linux/DB verify (owed, do NOT block design):** (1) V127 `aeg_regime_labels` population + classifier_version pin + ret_30d/ret_90d coverage; (2) altcap basket construction spec (QC/MIT); (3) `agent.lessons` V133 population for novelty dedupe.

**Needs operator / QC / MIT to ratify:**
- **QC (gates P3b):** B1 four final numbers {factor set BTC+altcap / WINDOW_DAYS≥90 / BETA_NEUTRAL_THRESHOLD 0.15 / down-market def + |β_down| rule}; the **altcap basket construction spec**; Q1 `N_trades_oos≥50`.
- **MIT (gates P3a M3/M4 + P3b producers):** `shift1_compliance`/`is_oos_gap` leak-typing producer build; M4 benchmark construction + recall floor (≥0.85) + false-kill-vs-false-pass trade-off.
- **operator:** lock "P3 ships no migration; altcap basket = on-the-fly/artifact (no V137)" — OR reopen V137 if QC wants a persisted altcap table.

**Explicit verdict:** **P3a is E1-ready now** (design-decided + grounded; gates on E2+MIT M3/M4, not B1). **P3b is design-ready but EXECUTION-BLOCKED** on QC B1 final numbers + the altcap basket construction (the data does not exist) + the shift1/is_oos producers. Recommend dispatching **P3a first** to prove the full cascade on a zero-alpha surface, and opening the QC B1-finalization + altcap-construction track in parallel for P3b.

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3-ml-advisory-tech-design.md
