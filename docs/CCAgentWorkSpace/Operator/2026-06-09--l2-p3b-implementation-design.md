# PA — L2 Phase 3b implementation design (`ml_advisory.hypothesize` alpha-bearing + B1 `beta_neutral_check` + altcap producer + leak producers)

Date: 2026-06-09 · Author: PA · Type: **DESIGN-ONLY** (no business code written, no migration applied, no deploy, no three-end sync — PM/operator owns dispatch). · Branch `feature/l2-critic-lessons-tools` @ `aeae4da4` (P3a green+committed).

Sign-off chain: **PA → E1 → E2 → QC(B1 final + leak-free PIT) → MIT(M3 leak + M4 recall) → E4 → QA → PM**. design-first: this report → PM → operator sign-off → E1.

SSOT integrated (NOT re-litigated): QC B1 spec `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-09--l2-p3b-b1-altcap-spec.md` (B1 four numbers FINALIZED, altcap=EQUAL-WEIGHT operator-locked); MIT spec `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-09--l2-p3b-leak-producers-m4-benchmark-spec.md` (shift1 reuse, is_oos build, M4 schema, V127 0-rows); execution-plan §2 Phase 3; PA P3 design `2026-06-09--l2-p3-ml-advisory-tech-design.md` §E/§G/§J; design v4 `2026-06-05--l2-advisory-mesh-design-draft.md` §N.1 (B1, lines 1862-1920) / §G.2 (cascade, 1217-1277) / §C.3 (forward-OOS/B2).

Read-in-full this session (ground for every assertion): `residual_alpha_gate.py` (full), `dsr_gate.py` (full), `l2_ml_advisory_executor.py` (full, P3a executor), `l2_advisory_orchestrator.py` (full), `l2_capability_registry.py` (full), `l2_prompt_contract_registry.py` (full), `l2_out_of_bound_guard.py` (full), `fnd2_pit_universe/{builder,cohorts,data_loader}.py` (full), `feature_engineering_validator.py` (full), `learning_tier_gate.py` (key spans), `settings/l2_capability_registry.toml` (full), `run_training_pipeline.py` (PipelineResult), `parquet_etl.py` (EDGE_P3_FEATURE_NAMES), `sample_weight_sensitivity.py:329` (is_oos namesake), `V133__agent_lessons.sql` (head).

---

## 0. The load-bearing P3b architectural truth (frames everything below)

**hypothesize is alpha-bearing, but its lane stays `ml_backlog` = `neutral`.** Verified: `LANE_DIRECTION["ml_backlog"]="neutral"` (`l2_capability_registry.py:70`). A hypothesize run produces a **backlog item + a promotion-relevant verdict** (pass/DEFER/fail). The verdict is "promotion-relevant" but the **act of promotion** (to demo Stage 1) is a *separate* `demo_stage1` lane = `expand` = forced MANUAL (`l2_capability_registry.py:74` + `effective_autonomy` STEP-1 `:119-120`). So:

- hypothesize itself = `neutral_sink` → routes through the existing `dispatch_and_execute` neutral path (`l2_advisory_orchestrator.py:411-416`).
- the **alpha validation** happens inside the cascade's **deterministic math gate** (B1+DSR+PBO+leak+Q1), the ONLY validator. LLM never validates (verified iron rule, `l2_ml_advisory_executor.py:27-35`).
- a pass-verdict backlog item is advisory only; **a human promotes it** (P4/P5), gated by B2 forward-OOS ≥21d demo Stage 1 (Stage 0R necessary-not-sufficient). **0 new live authority; 0 new auto-to-paper signal.**

This is why hypothesize can be `neutral` lane yet B1-gated: B1 gates the *promotion-relevant verdict*, not the lane. PA P3 design §C line 121 already established this; P3b implements it.

**P3b is NOT greenfield orchestration.** P2 (`6a9dd0f1`) shipped the whole mesh; P3a (`aeae4da4`) shipped the cascade executor for 2 modes. P3b is six surgical deltas on top:
1. `beta_neutral_check` (B1) — new deterministic gate member (§A).
2. altcap basket producer — new on-the-fly producer (§B).
3. `shift1_compliance` producer — thin adapter (§C).
4. `is_oos_gap` producer — new temporal-gap checker (§D).
5. hypothesize mode + math gate orchestration + guard extension (§E).
6. M4 benchmark artifact + seeding + V127 population (§F).

---

## A. `beta_neutral_check` (B1) — gate member implementation design

### A.1 Module + signature (NEW; reuses residual_alpha_gate OLS)

New file `program_code/learning_engine/beta_neutral_check.py` (sibling of `residual_alpha_gate.py` / `dsr_gate.py` — pure-math, 0 DB / 0 Bybit / 0 order path, same posture as the gate-stack neighbours). QC-gated.

```python
# program_code/learning_engine/beta_neutral_check.py  (NEW — QC-owned numbers, E1 builds)
BETA_NEUTRAL_THRESHOLD = 0.15      # |β| point-estimate threshold (QC #3, FINAL)
BETA_UPPER_CAP = 0.20              # β + 1.96·SE upper bound (QC #4, FINAL)
WINDOW_DAYS_MIN = 90               # overall β window floor (QC #2)
DOWN_SUBSAMPLE_SPAN_DAYS_MIN = 180 # down-leg span floor (QC #3c-window; runtime: 90d=23 down-bars<30)
DOWN_BARS_MIN = 30                 # ≥30 down-bars else DEFER (QC #3c-window)

def beta_neutral_check(
    candidate_returns,        # Mapping[ts,float] | Sequence — same parser shapes as residual_alpha_gate
    btc_returns,              # BTC factor series (daily or 4h, pinned per candidate)
    altcap_returns,           # altcap basket series (§B producer; None ⇒ BTC-only ⇒ DEFER)
    down_market_mask,         # Mapping[ts,bool] — lagged-PIT down-market labels (§A.3)
    *,
    bar: str = "daily",       # "daily" | "4h" (QC #2; NOT 1m — attenuation)
    window_days: int = WINDOW_DAYS_MIN,
    threshold: float = BETA_NEUTRAL_THRESHOLD,
    upper_cap: float = BETA_UPPER_CAP,
) -> BetaNeutralResult:
    # BetaNeutralResult{
    #   verdict: "pass" | "fail" | "DEFER",
    #   beta_btc, beta_alt, beta_down: float | None,
    #   se: dict{"btc","alt","down"} float | None,         # coefficient SE (§A.2)
    #   beta_upper: dict{"btc","alt","down"} float | None,  # β + 1.96·SE
    #   durbin_watson: float | None,                        # → HAC escalation (§A.2)
    #   used_hac: bool,
    #   n_bars: int, n_down_bars: int,
    #   reasons: tuple[str,...],
    #   factor_hash: str,                                   # reuse _hash_factor_rows for provenance
    # }
```

### A.2 OLS + coefficient SE (the E1 build-note — reuse `residual_alpha_gate._fit_factor_beta` + add SE)

`residual_alpha_gate._fit_factor_beta(y, x)` (`:619-624`) returns **point coefficients only** via `np.linalg.lstsq` on `design = [1 | x]`. B1 reuses this exact OLS path (do NOT fork the regression), then **adds SE** — the one piece the residual gate does not compute:

1. Build `design = np.column_stack([ones, X])` where `X = [r_btc, r_altcap]` (dual-factor, the mandatory model `r_strat = α + β_btc·r_btc + β_alt·r_altcap + ε`).
2. `coef, *_ = np.linalg.lstsq(design, y)` (identical to `:621`).
3. **residual variance** `σ²_resid = SSR / (n − k)` where `k = design.shape[1]` (3: intercept + 2 betas), `SSR = Σ(y − design@coef)²`.
4. **`(X'X)⁻¹`** via `np.linalg.inv(design.T @ design)` (or `pinv` fail-soft on singular — singular ⇒ DEFER, not crash).
5. **`SE(β_j) = sqrt(σ²_resid · diag((X'X)⁻¹)_j)`** — exactly QC's "residual-var × diag((X'X)⁻¹)" formula (QC spec line 18).
6. **Durbin-Watson** on residual `e`: `DW = Σ(e_t − e_{t-1})² / Σe_t²`. **If `DW < 1.5` → escalate to HAC (Newey-West) SE** (QC spec line 18): `SE_HAC = sqrt(diag((X'X)⁻¹ · X' Ω̂ X · (X'X)⁻¹))` with Bartlett-kernel autocovariance lags `L = floor(4·(n/100)^(2/9))` (standard Newey-West bandwidth). Set `used_hac=True`. Hand-roll (stdlib + numpy, no statsmodels — consistent with `dsr_gate` "hand-roll to avoid scipy", `:161-164`).

**Why SE matters (the masquerade kill):** QC #4 `β_upper = β + 1.96·SE < 0.20` kills "small β but huge noise" passes. A candidate with `β_btc=0.12` (under threshold) but `SE=0.06` has `β_upper=0.2376 ≥ 0.20` → **fail**. Without SE, a noisy down-beta candidate would pass on the point estimate — the exact 5-candidate failure mode.

### A.3 Four QC numbers — deterministic enforcement (verdict logic)

| # | Rule | Enforcement in `beta_neutral_check` |
|---|---|---|
| 1 | dual-factor BTC+altcap MANDATORY; BTC-only → DEFER | if `altcap_returns is None` (producer absent) → `verdict="DEFER"`, reason `altcap_missing_btc_only_defer`. NEVER fit a BTC-only model and call it neutral (the masquerade pass-by-construction). |
| 2 | 90d window, daily/4h (not 1m) | if aligned bars `< window_days` → `DEFER` reason `window_below_90d`. `bar` pinned per-candidate (caller supplies); `bar="1m"` not offered (attenuation). |
| 3 | `BETA_NEUTRAL_THRESHOLD=0.15` on `|β_btc|` AND `|β_alt|` AND `|β_down|` | any `|β_j| ≥ 0.15` → `verdict="fail"`, reason `beta_{j}_above_threshold`. |
| 3c/3c-window | down-market def 30d-dd>8% OR 7d<-5%, lagged-PIT; down sub-sample span ≥180d; <30 down-bars → DEFER | `down_market_mask` is computed leak-free prior-only (§A.4). `β_down` fit on the **down sub-sample** drawn from a `≥180d` span. if `n_down_bars < 30` → `verdict="DEFER"`, reason `down_bars_below_30_defer` (runtime: last-90d=23 down-bars, full-span=309 — MIT §3.4). |
| 4 | `β_upper = β + 1.96·SE < 0.20` (all three betas) | any `β_upper_j ≥ 0.20` → `verdict="fail"`, reason `beta_{j}_upper_above_cap`. |

**Verdict precedence (deterministic, fail-closed):** any `fail` reason → `fail`. else any `DEFER` reason → `DEFER`. else `pass`. (fail dominates DEFER: a candidate that both has `|β|≥0.15` AND insufficient down-bars is a `fail`, not a `DEFER` — strictest verdict wins, mirrors `residual_alpha_gate._verdict_from_blocking_reasons:882-889`.) Three-state honesty (DEFER ≠ FAIL ≠ PASS).

### A.4 down-market mask — leak-free prior-only (MIT Path B; no V127 hard-dependency)

Per MIT §3.3 recommendation, B1's **binary down-mask = klines-direct** (decouples from classifier_version + V127 population). E1 computes it from `market.klines` BTCUSDT 1d, prior-only:
- `30d-drawdown > 8%`: `close_t < peak(close[t-30 : t-1]) · 0.92` (peak over PRIOR 30 bars, NOT including t).
- OR `7d-return < -5%`: `close_t < close_{t-7} · 0.95`.
- Both use `ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING` / `LAG(close,7)` semantics (the exact leak-free pattern MIT §0/§3.5 verified). Down-threshold = absolute scalar (8%/5%), NOT full-sample percentile (avoids the `data_loader.py:300` ML-training vol-tercile leak class — QC spec §4).
- V127 `aeg_regime_labels.ret_30d` is a **corroborating cross-check only** (NOT binding); if V127 is empty (runtime: 0 rows), B1 still computes from klines (MIT §3.3 de-risking finding).

### A.5 ★ WHERE B1 inserts in the math gate (the gate-stage order)

The cascade math gate (for hypothesize) runs deterministic stages in this order, short-circuiting on the first DEFER/fail (cost + correctness):

```
STEP 0  — Q1 sample sufficiency:  N_trades_oos ≥ 50  else → DEFER   (§A.6; before any stat)
STEP 1  — DSR(K):   dsr_gate.compute_dsr(observed_sharpe, n_trials=K, n_observations=N_trades_oos,
                    min_observations=50)  → insufficient_observations ⇒ DEFER; else passes_threshold
STEP 2  — PBO:      single-config ⇒ HONEST-DEFER  (pbo_not_applicable / missing_cpcv_returns;
                    承 2026-06-08 Gap-A PBO ruling — fabricating peers is theater. Genuine PBO peers
                    owed to A-full Rust replay, P4+. DEFER here, do NOT synthesize.)
STEP 3  — BETA-NEUTRAL [B1]:  beta_neutral_check(...)  → pass | fail | DEFER   ← THIS DESIGN
            STEP 3a pooled betas (β_btc, β_alt) on ≥90d
            STEP 3b down-leg (β_down) on ≥180d-span down sub-sample
STEP 4  — LEAK precondition:  shift1_compliance AND/OR is_oos_gap leak_free=True  (§C/§D)
                    else → DEFER  (name_pattern_check alone NOT sufficient — M3)
→ overall verdict = strictest of {STEP0..STEP4}:  any fail → fail; else any DEFER → DEFER; else pass
```

**Why this order:** (1) Q1 first — cheapest, gates everything (no point computing β on <50 trades). (2) DSR before B1 — DSR's `insufficient_observations` is a stricter sample gate; if it DEFERs, B1's β is unreliable anyway. (3) **B1 is a hard precondition at the SAME tier as DSR** (design §N.1 (5) line 196 "a candidate failing B1 cannot pass") — it is NOT a soft/advisory dimension. (4) PBO honest-defer is placed before B1 so the DEFER is recorded but does not block (it is `_is_defer_only_reason`, `residual_alpha_gate.py:892-896`) — B1 still runs and can produce a real fail. (5) leak precondition last because it gates whether the whole evidence chain is admissible.

**Overall verdict combination = strictest-wins**, identical to `residual_alpha_gate._verdict_from_blocking_reasons` semantics: a hard `fail` (B1 `|β|≥0.15`, DSR block) dominates; absent fail, any `DEFER` (Q1<50, PBO single-config, B1 down-bars<30, leak-precondition-unmet) → overall DEFER; only all-pass → `pass`. **The math gate function has 0 LLM-invocation inside** (CC/E2/MIT grep target; PA P3 design §D line 171).

### A.6 Q1 mapping — `dsr_gate.compute_dsr(min_observations=50)`

Q1 (`N_trades_oos ≥ 50` → DEFER) maps cleanly to the EXISTING `dsr_gate`: pass `n_observations = N_trades_oos` and `min_observations=50` to `compute_dsr` (`dsr_gate.py:381-483`). When `N_trades_oos < 50` → `insufficient_observations=True` (`:465`) → `passes_threshold` forced False (`:466`) → `gate()` returns `"defer_data"` (`:506-507`). NOTE: `DEFAULT_DSR_MIN_OBSERVATIONS=30` (`:95`) is the module default; B1's math gate explicitly passes `min_observations=50` (QC #Q1, the trade-count gate, distinct from the 30-floor degenerate-input guard). No change to `dsr_gate.py` — it already supports the override (`compute_dsr(..., min_observations=...)` `:526`).

---

## B. altcap basket producer — equal-weight ex-BTC CORE25, daily-rebal, on-the-fly (NO V137)

### B.1 Module + interface (NEW)

New file `program_code/research/altcap_basket.py` (research producer, read-only — sibling posture of FND-2). Operator-locked EQUAL-WEIGHT (QC §2; cap-data does-not-exist + Root-Principle-14).

```python
# program_code/research/altcap_basket.py  (NEW — QC-owned spec, E1 builds; biggest B1 data gap)
def build_altcap_returns(
    fnd2_universe_rows,       # FND-2 build_universe() rows OR loaded universe.csv artifact
    daily_closes,             # {symbol: {date: close}} from market.klines 1d (read-only)
    *,
    window_start,             # date
    window_end,               # date
    ex_symbols=("BTCUSDT",),  # ex-BTC; ex-stablecoin already excluded by FND-2 USDT-perp scope
) -> AltcapReturnSeries:
    # AltcapReturnSeries{
    #   returns: dict[date, float],            # r_altcap_t = mean over PIT-alive constituents
    #   constituents_by_day: dict[date, list], # audit: who was alive each bar (PIT proof)
    #   n_constituents_by_day: dict[date, int],
    #   reasons: list[str],                    # e.g. day_skipped_no_constituents
    # }
```

### B.2 Construction (deterministic, leak-free-by-construction)

- **Universe = FND-2 PIT universe, ex-BTC, ex-stablecoin.** Launch scope = **CORE25 ex-BTC = 24 symbols** (`cohorts.py:27-33` `CORE25_PINNED` minus `BTCUSDT`). Widen to full FND-2 `included` set later (post-launch).
- **Return** `r_altcap_t = mean over PIT-alive constituents of (close_s,t / close_s,{t-1} − 1)`, **daily equal-weight** (each alive constituent weight = 1/N_t where N_t = count of PIT-alive-at-t).
- **★ PIT discipline (the one MIT M3 review hot-spot)**: constituents at bar `t` = **PIT-alive set at `t`** per FND-2 `alive_from`/`alive_to` walk-forward, NOT today's survivors. Verified the source: `builder._build_row` computes `alive_from = max(eff_listed, ws)` / `alive_to = min(eff_delisted, we)` (`builder.py:235-236`) → the `alive_from_utc`/`alive_to_utc` columns (`UNIVERSE_COLUMNS:46`). A constituent enters the basket at `alive_from` and exits after `alive_to` (no zombie forward-fill of a delisted symbol's last price). The `SymbolLifecycle.listed_at`/`delisted_at` (`builder.py:79-80`) are the lifetime authority; `first_seen_ts`/`last_seen_ts` are diagnostic-only (`:83-84`, snapshot ts spans only 27d — the documented trap). E1 walks day-by-day, includes symbol s in bar t iff `alive_from_s ≤ t ≤ alive_to_s`.
- **Why equal-weight is defensible (QC §2, not re-litigated)**: cap-data does-not-exist (0 hits over srv); funding-tilt PCA PC1 ~69% ⇒ basket dominated by common alt move ⇒ weighting second-order (equal/cap/volume ~0.95+ corr). Reject OI-weight (contaminates with the cascade signal B1 must be orthogonal to). 0 free params.

### B.3 Inputs + output interface to B1

- **Input 1 (membership)**: FND-2 `build_universe()` rows in-memory (preferred — recompute per B1 run, leak-free) OR the persisted `universe.csv` artifact (`alive_from_utc`/`alive_to_utc` columns). Use `fnd2_pit_universe.data_loader.load_lifecycles()` (read-only, `set_session(readonly=True)` fail-closed `:69`) → `builder.build_universe()` → rows.
- **Input 2 (prices)**: `market.klines` 1d closes (read-only SELECT; BTC 1d = 730 rows runtime-verified, alts similar). Same leak-free posture as the FND-2 data_loader.
- **Output → B1**: `altcap_returns` (the `returns` dict) is passed as the second factor (`altcap_returns` arg) to `beta_neutral_check` (§A.1). When the producer cannot build (no constituents alive in window, or prices missing) → returns empty → B1 sees `altcap_returns=None`-equivalent → **DEFER** (BTC-only, §A.3 #1). fail-closed by construction.

### B.4 Persistence — ON-THE-FLY, NO V137 (QC §2 + operator-locked)

Deterministic function of (FND-2 membership + daily closes). Recompute per B1 run = cheap + leak-free-by-construction. **NO persisted table, NO V137.** Mirrors the FND-2 CSV-artifact pattern. V137 stays reserved-not-used (reopen ONLY if a persisted basket is wanted for replay → owes Linux dry-run — explicitly out of P3b scope).

---

## C. `shift1_compliance` producer — thin adapter (MIT §1.1; reuse, NOT greenfield)

New file `program_code/ml_training/shift1_compliance.py` (MIT-owned, E1 builds). **Reuses `helper_scripts/m4/feature_engineering_validator.py`** — verified the substance already exists:
- `is_leaky_sql(sql)` (`:43`) / `is_leakfree_sql(sql)` (`:51`) — SQL-side static (`AND 1 PRECEDING` = leak-free proof; `AND CURRENT ROW` = leak).
- `is_leaky_pandas(code)` (`:63`) — pandas-side static (`.rolling(N)` without `.shift(1)` = leak).
- **`validate_shift1_pattern(feature_values, forward_return_bps, window, diff_threshold=0.1)` (`:72-113`)** — the core empirical test: `leak_corr` (slice incl. current bar) vs `clean_corr` (shift(1) slice), `diff=|leak_corr−clean_corr|`, `leak_suspected = diff>0.1`, `insufficient_sample` flag.

**Determination: thin adapter, NOT a new algorithm.** It calls these functions and emits a typed evidence row:

```python
# program_code/ml_training/shift1_compliance.py  (NEW — adapter over feature_engineering_validator)
def check_shift1_compliance(
    feature_series: dict[str, Sequence[float]],   # {feature_name: realized values, time-ordered}
    forward_return_bps: Sequence[float],
    *, window: int, compute_exprs: dict[str, str] | None = None, diff_threshold: float = 0.1,
) -> Shift1ComplianceResult:
    # source_class="shift1_compliance", leak_free: bool, per_feature[...], reasons[], evidence_ref
```

**Two-layer per feature** (MIT §1.1.1): (1) static — `is_leakfree_sql`/`is_leaky_*` if `compute_exprs` available; (2) empirical — `validate_shift1_pattern`; `leak_suspected=True` → FAIL; `insufficient_sample` → **DEFER** (never auto-pass on thin data).

**Output → M3**: `leak_free=True` ONLY when EVERY feature is `pass` AND none is `defer` (**fail-closed: any DEFER → `leak_free=False`**). Emits `source_class="shift1_compliance"` → enters the M3 leak-free set (`ML_ADVISORY_LEAKFREE_SOURCE_CLASSES`, `l2_prompt_contract_registry.py:163`) → a hypothesize leak-free claim backed by THIS is legal (vs `name_pattern_check` which guard B.2 rejects, `l2_out_of_bound_guard.py:251`).

---

## D. `is_oos_gap` producer — BUILD (MIT §1.2; distinct module name to dodge namesake collision)

New file `program_code/ml_training/is_oos_gap.py` (MIT-owned, E1 builds). **Confirmed namesake collision**: `sample_weight_sensitivity.py:329` has an `is_oos_gap` that is a **train-vs-OOS RMSE gap-ratio overfit detector** (`{mean_train_rmse, mean_oos_rmse, gap_ratio:(mean_oos-mean_train)/..., withdraw_baseline}`) — NOT the M3 temporal-gap source-class. Verified the exact code (`:329-340`). MIT recommends option (a): **keep the M3 `source_class` STRING `"is_oos_gap"` (registry constant `:157` unchanged), use a distinct internal module/function name** (`check_oos_gap`) — zero collision at source_class layer, only human-facing names differ. **PA concurs with (a)** (option b renames an existing metric's consumers for cosmetic reasons → violates surgical-change discipline).

```python
# program_code/ml_training/is_oos_gap.py  (NEW; function check_oos_gap; source_class "is_oos_gap")
def check_oos_gap(
    train_signal_ts, test_signal_ts, train_label_end_ts,
    *, label_horizon_bars: int, embargo_bars: int,
) -> OosGapResult:
    # source_class="is_oos_gap", leak_free: bool, temporal_separation_ok, embargo_gap_bars,
    #   embargo_sufficient, purge_violations, shuffle_detected, reasons[]
```

**Four checks per `time-series-cv-protocol` §2 (MIT §1.2.1):** (1) temporal separation `max(train.signal_ts) < min(test.signal_ts)`; (2) embargo gap present `min(test)−max(train) ≥ embargo_bars` (Lopez de Prado AFML Ch.7); (3) purge applied `train.label_end_ts < min(test.signal_ts)` (no label-window overlap into test); (4) no shuffle (contiguous time blocks; KFold-shuffle forbidden). `leak_free=True` ONLY when all four hold. Feeds M3 set.

**P3b gate wiring (the leak precondition, §A.5 STEP 4)**: until both producers exist + return `leak_free=True` for a candidate, the math gate leak precondition is unmet → hypothesize verdict **DEFERs** (consistent fail-closed; MIT §1.3). No producer ⇒ no leak-free claim ⇒ no promotion. Correct.

---

## E. hypothesize → backlog → promotion mode (alpha-bearing capability)

### E.1 Registry stanza (TOML; `min_tier=L3`, `enabled=false`)

Add a third `[[capability]]` to `settings/l2_capability_registry.toml` (the template at file lines 100-125 is the pattern):

```toml
[[capability]]
capability_id          = "ml_advisory.hypothesize"   # P3b — alpha-bearing; promotion-relevant verdict
enabled                = false                        # FAIL-CLOSED DEFAULT (loader-enforced; double-gate w/ tier)
min_tier               = "L3"                         # can_generate_hypotheses first True @L3 (learning_tier_gate.py:203)
tier_capability_flag   = "can_generate_hypotheses"    # bind the L3 flag (STEP-2 TIER_LOCKED if flag False)
model_tier             = "cloud_l2"
cloud_model_pref       = "sonnet"
lane                   = "ml_backlog"                 # → LANE_DIRECTION="neutral" (backlog sink; promotion is separate expand/MANUAL)
output_schema_ref      = "ml_advisory.v1"             # shared schema (mode field drives sub-object)
prompt_contract_ref    = "ml_advisory.hypothesize.v1" # NEW contract (§E.2)
out_of_bound_guard_ref = "ml_advisory.guard.v1"       # extended guard (§E.4)
novelty_gate           = true                         # hypothesis → novelty dedupe vs dead_failure_modes
consequential_default  = false
[capability.trigger]
kind = "event"; spec = "ml:training_complete"; debounce_secs = 900
[capability.budget]
per_call_usd_cap = 0.50; daily_usd_cap = 0.50         # ≤ DOC-08 $2/day
```

**Double-gate verified**: `enabled=false` (loader fail-closed, `l2_capability_registry.py:176`) AND `min_tier=L3` + `tier_capability_flag=can_generate_hypotheses` (`effective_autonomy` STEP-2 TIER_LOCKED if tier<L3 or flag False, `:122-126`). Deployment is behaviorally inert until operator sets `enabled=true` AND tier is L3+ with the flag.

### E.2 PromptContract `ml_advisory.hypothesize.v1` (NEW; deterministic versioned template)

Add to `l2_prompt_contract_registry.py` `_PROMPT_CONTRACTS` (mirror `_ML_ADVISORY_DIAGNOSE_CONTRACT` shape `:171`). The template hard-constrains: **propose pre-registerable feature hypotheses with an economic mechanism + a falsification test + signal_axes_used + a beta_neutralization_plan; LLM makes NO alpha claim (the math gate validates)**. Add `"hypothesize": ("mode", "feature_hypotheses")` to `ML_ADVISORY_MODE_REQUIRED_FIELDS` (`:144` — currently has no hypothesize key by P3a design). Output schema (mode-driven sub-object): `feature_hypotheses[{hid, statement, mechanism, falsification_test, signal_axes_used[], expected_direction, beta_neutralization_plan}]` + `backlog_items[]` (PA P3 design §C line 138).

### E.3 Executor extension — math gate orchestration (`l2_ml_advisory_executor.py`)

P3a's `run_ml_advisory_cascade` rejects hypothesize at `:563` (`mode not in _P3A_MODES`). P3b:
1. **Extend `_P3A_MODES`** → add `"hypothesize"` (or add a `_P3B_MODES` set + union; E1 surgical choice). Add `"hypothesize": "ml_advisory.hypothesize.v1"` to `_MODE_CONTRACT_REF` (`:87`).
2. **Insert the math gate as a NEW STAGE between STAGE 3 (guard) and STAGE 4 (sink)** — ONLY for hypothesize (diagnose/interpret keep the P3a path, no math gate, `:611-639`). After guard passes, call a new `_run_math_gate(parsed, context) -> MathGateResult{verdict, stage_verdicts, reasons}` that runs the §A.5 stage order. Wire each stage to a gate-seam (`_seam(..., gate_id="ml_advisory_math_gate", verdict=...)` — reuse the existing `_seam` `:693`). **The math gate result becomes the promotion-relevant verdict.** A DEFER/fail still writes the D3 ledger row (reconstructable, `:624-631`) and still sinks the backlog item to `agent.lessons` (advisory; the verdict is recorded in content), but the verdict field marks it non-promotable.
3. **Cost-on-survivors preserved**: the cloud-L2 interpret step (STAGE 2, `:591`) for hypothesize runs BEFORE the math gate (to extract the structured hypothesis), but the math gate gates whether the verdict is promotion-relevant. Alternative (cheaper): generate-via-Ollama → math-gate-on-structured-candidate → cloud-interpret only survivors. **PA recommends the design v4 §G.2 cascade order** (Ollama generate → math gate → cloud interpret survivors only, `2026-06-09--l2-p3-ml-advisory-tech-design.md` §D lines 150-158) — but P3a's executor currently does cloud-FIRST. **E1 acceptance item: reconcile the cascade order so the math gate runs before the (expensive) cloud-L2 survivor-interpret for hypothesize** (cost, root principle 13). This is a real ordering decision E1 must implement per §G.2, not the P3a cloud-first path.
4. **Iron-rule grep target preserved VERBATIM**: the executor MODULE_NOTE `:27-35` ("本模塊 import 無 order surface / IntentProcessor / place_order / acquire_lease / promote_tier / live-config write") — verified these are comment-only (the 2 grep hits at `:29-30` are the iron-rule statement, 0 actual calls). **P3b adds 0 order/lease/promote_tier/live-config imports or calls.** The math gate has 0 LLM-invocation inside (CC/E2 grep target).

### E.4 out-of-bound guard extension (`l2_out_of_bound_guard._guard_ml_advisory_v1`)

Extend the existing guard (`:175`) with hypothesize-specific clauses (the guard already has clause D `signal_axes_used ⊄ available_signal_axes` `:277-287` and clause C regime/bull-only `:257-275` — REUSE both):
- **E.4(a) axes guard (REUSE clause D)**: `signal_axes_used ⊄ available_signal_axes` → reject. `available_signal_axes` from `parquet_etl.EDGE_P3_FEATURE_NAMES` (`:40`), passed via context (executor `:614-615` already threads `available_signal_axes`). Already implemented; hypothesize just populates `signal_axes_used`.
- **E.4(b) empty-mechanism curve-fit guard (NEW clause)**: for `mode=="hypothesize"`, each `feature_hypotheses[].mechanism` must be a non-empty string AND `falsification_test` non-empty → else reject `empty_mechanism_curve_fit`. (A hypothesis with no economic mechanism is curve-fitting; execution-plan §2 Phase 3 "reject empty mechanism (curve-fit guard)".)
- **E.4(c) novelty vs dead_failure_modes (NEW clause)**: dedupe the hypothesis statement against `agent.lessons` V133 `lesson_type='dead_mode'` (the novelty source; `novelty_gate=true` in the stanza). **Determination on WHERE this runs**: the guard is pure/deterministic/no-DB (`l2_out_of_bound_guard.py:24` "無 model、無 DB"). Novelty dedupe needs a DB read (`retrieve_lessons` pg_trgm, `layer2_critic.py:278`). **So novelty is NOT a guard clause** — it runs in the **executor** (which already does DB I/O) as a pre-gate step: executor calls `retrieve_lessons(symbol, hint=statement, lesson_type='dead_mode')`; if a near-duplicate dead-mode exists → mark the hypothesis `novelty=duplicate` and the math gate verdict → `DEFER` (reason `duplicate_of_dead_failure_mode`). The guard stays DB-free; the executor owns the novelty DB read. This corrects a naive "guard does novelty" reading — the guard's no-DB invariant is load-bearing.
- **E.4(d) bull-only → regime-bet/learning-only (REUSE clause C)**: a hypothesis whose only support is bull-only/rally-dominated metrics → the interpretation must carry `regime_caveat`; promotion-ready + bull-only + no caveat → reject (existing clause C, `:271-275`). hypothesize inherits this.

### E.5 Promotion routing (the promotion-relevant verdict → backlog/B2; NO auto-to-live)

- `verdict=pass` → backlog item sinks to advisory (`agent.lessons` via `write_ml_advisory_advisory_sink` `:404`, genuinely-inert, OR `mlde_shadow_recommendations` per design §C line 138 — PA recommends `agent.lessons` for the same 0-exec-authority structural guarantee P3a uses, `:382-398`). The verdict marks it **promotion-candidate**. Promotion to demo Stage 1 = a SEPARATE `demo_stage1` lane = `expand` = **forced MANUAL** (`effective_autonomy` STEP-1, `:119-120`) → human promotes. **Auto promotion requires B2 forward-OOS ≥21d (demo-only, Stage 0R necessary-not-sufficient)** — and even then it is the `demo_stage1` expand lane = MANUAL under Conservative posture (`:132-133`). 0 new live authority.
- `verdict=DEFER` → backlog with `gate_verdict:"DEFER"` (shown in §N packet, P5); not promotion-relevant.
- `verdict=fail` → logged-and-dropped (D3 ledger records the rejected hypothesis + math-gate reasons); not sinked as a candidate.
- **`can_modify_live_config=False`** is hard in `learning_tier_gate.py:664-671` (literal False) — P3b touches nothing here. **C1 hazard (`AUTO_PROMOTE_L3_TO_L4` `:119`, `promote_tier(approved_by=None)` `:520-525`) is NOT touched by the executor** (verified 0 actual calls).

---

## F. M4 benchmark artifact + seeding + V127 population

### F.1 M4 benchmark artifact (MIT §2.1; JSON, NO migration)

MIT-owned artifact `settings/l2_ml_advisory_screen_benchmark.json` (the loader `load_ollama_screen_calibration` `l2_ml_advisory_executor.py:156` reads `settings/l2_ml_advisory_screen_calibration.json` — **NOTE path discrepancy**: MIT schema names it `..._screen_benchmark.json`, the P3a loader reads `..._screen_calibration.json`. **E1 acceptance: align the filename** — either the loader reads the benchmark artifact, or the benchmark build writes to the calibration path. PA recommends the benchmark BUILD writes the calibration artifact the loader already reads `:153`, carrying MIT's extended schema fields). Schema (MIT §2.1): `{benchmark_version, classifier_version, measured_at, recall_floor:0.85, threshold, n_good, n_bad, recall, precision, per_class_recall{good_recall, bad_reject_rate}, confusion{tp,fn,fp,tn}, enabled_decision}`. Mirrors FND-2 CSV-artifact pattern. **NO V137.**

### F.2 good/bad set construction (MIT §2.2-2.4)

- **good set ≈ 8** (runtime-ready): 3 `learning.model_registry` promoted models (MIT §0 verified) + 5 correct down-beta-masquerade NO-GO diagnoses (A1 funding_short, oi_delta, cascade-fade, funding-tilt, listing — each correctly diagnosed "beta, not alpha").
- **bad set — BLOCKED on seeding**: `agent.lessons` V133 dead-modes = **0 rows** (MIT §0 runtime-verified). MIT recommends **(a) seed 5-10 historical dead-modes** via `persist_lessons` (`lesson_type="dead_mode"`, content = the failed hypothesis statement + why beta-masquerade) — one-shot, operator/E1-executed. Until seeded, **M4 correctly stays placeholder-DISABLED** (the P3a loader fail-closes to DISABLED on missing/low-recall artifact `:169-201` — subtraction-only, everything to the deterministic gate, loses no alpha).
- **Build steps (MIT §2.4)**: seed bad set → assemble good set → run screen over (good ∪ bad), record pass-through vs coarse-reject → fill confusion/recall/precision → if `recall≥0.85 AND bad_reject_rate>0` → `enabled_decision="ENABLED"` at loosest threshold meeting recall≥0.85, else DISABLED + flag MIT → log to D3 gate-seam → write artifact.

### F.3 V127 population (MIT §3; owed-runtime, corroboration-only)

`research.aeg_regime_labels` = **0 rows** (MIT §0). Population via `aeg_regime_runner.harness --write-db` (MIT §3.3 Path A). **NOT strictly needed for B1's binary down-mask** (B1 uses klines-direct Path B, §A.4) — V127 supplies the categorical regime axis (bull/bear/chop) as orthogonal corroboration only. **Marked owed-runtime** (operator/E1; not a P3b design blocker, blocks only the §C.2 robustness-matrix categorical axis). The runner is already leak-free PIT (MIT §3.2 verified `classifier.py:110-178` prior-only).

---

## G. Migration judgment — **V137 reserved-not-used; P3b is ZERO-migration**

| P3b artifact | Storage | Migration? |
|---|---|---|
| `beta_neutral_check` | pure-math function, 0 DB | NO |
| altcap basket | on-the-fly / CSV-artifact (FND-2 pattern) | NO |
| `shift1_compliance` / `is_oos_gap` producers | compute over existing data (klines / training run series) | NO |
| M4 benchmark | JSON artifact | NO |
| hypothesize capability | TOML stanza + contract/guard registry (in-code) | NO |
| V127 population | runner `--write-db` invocation (schema already applied, sqlx_max=133) | NO (not schema) |

**Confirmed: P3b needs NO migration.** V137 stays **reserved-not-used** (verified next-free per P2 design; reopen ONLY if operator wants a persisted altcap table for replay → then V137 + Linux PG dry-run, explicitly out of P3b scope). Consistent with PA P3 design §M + MIT §4 ("None of these reopen V137") + QC §5. **No is_oos_gap/benchmark table needed** (both are compute/JSON).

---

## H. E1 acceptance mapping + sign-off chain + read-before-build

### H.1 E1 acceptance → execution-plan §2 Phase 3 bullets

| Execution-plan §2 Phase 3 bullet | This design | E1 acceptance |
|---|---|---|
| **B1** dual-factor BTC+altcap mandatory, OLS daily/4h, `|β_btc/alt/down|<0.15`, down-def 30d-dd>8% OR 7d<-5% lagged-PIT ≥30bars else DEFER, `β_upper=β+1.96·SE<0.20` | §A | feed a known down-beta candidate → assert B1 `fail`/`DEFER`; BTC-only (altcap=None) → DEFER; <30 down-bars → DEFER; β_upper kills noisy-small-β |
| **Q1** math-gate step-0 `N_trades_oos≥50` else DEFER, propagates to §C.3/§N | §A.5 STEP0 + §A.6 | `compute_dsr(min_observations=50)` → `insufficient_observations` → `defer_data`; DEFER blocks auto-promote |
| **M3** leak typing `source_class∈{name_pattern_check,shift1_compliance,is_oos_gap}`; name_pattern_check NOT sufficient | §C + §D | producers emit typed rows; guard B.2 rejects leak-free claim backed only by name_pattern_check; math-gate leak precondition needs shift1/is_oos |
| **M4** Ollama screen recall≥0.85 else disabled+flag MIT | §F | benchmark has both classes (n_bad>0); recall measured; classifier_version pinned; loader fail-closes to DISABLED if low/missing |
| **C2** demo-promotion does not read can_auto_deploy_to_paper | §E.5 | promotion routing uses LANE_DIRECTION (demo_stage1=expand=MANUAL), NOT can_auto_deploy_to_paper (loader rejects it as posture-gate, `:278-285`) |
| guard: reject axes⊄available, empty mechanism, dedupe dead_failure_modes, regime_caveat | §E.4 | clause D (reuse) + new empty-mechanism clause + novelty (executor DB read) + clause C (reuse) |
| PromptContract deterministic versioned; contract_ver+schema_ver to every D3 row | §E.2 | `ml_advisory.hypothesize.v1` checked-in template; `resolve_contract_versions` writes versions |
| bull-only labeled regime-bet/learning-only | §E.4(d) | reuse clause C |
| **B2 forward-OOS** auto-promote needs ≥21d demo Stage 1 (Stage 0R necessary-not-sufficient) | §E.5 | promotion=demo_stage1 expand=MANUAL; auto-promote gated on B2 forward-OOS≥21d demo-only |

### H.2 §3 invariants (the iron laws)

- hypothesize=alpha-bearing → promotion-relevant verdict requires **B1 QC sign-off** (chain below).
- **math gate is the ONLY alpha validator; LLM never validates** (§A.5 + §E.3 iron-rule grep target preserved verbatim).
- bull-only → regime-bet/learning-only (§E.4(d)).
- promotion auto requires B2 forward-OOS ≥21d (demo-only, Stage 0R necessary-not-sufficient) (§E.5).
- **0 new live authority; can_modify_live_config=False untouched; 0 promote_tier/order/lease imports** (§E.3/§E.5 verified).
- do NOT exceed P3b: **FDR loop = P4 (NOT done), GUI = P5 (NOT done).** This design touches neither.

### H.3 read-before-build (E1 MUST do before coding)

1. **FND-2 membership shape**: read `universe.csv` artifact or `build_universe()` rows live to confirm `alive_from_utc`/`alive_to_utc` column presence + per-symbol coverage over the B1 window (the altcap PIT walk-forward depends on it). `builder.py:235-236` is the source.
2. **residual_alpha_gate SE addition point**: the OLS is `_fit_factor_beta:619-624` (`np.linalg.lstsq`). E1 adds SE around it (§A.2) — do NOT fork the lstsq, wrap it.
3. **down-bars count verification (≥180d span)**: re-run MIT's leak-free query on live `market.klines` BTCUSDT 1d to confirm ≥30 down-bars in the chosen down sub-sample span (runtime: full-span=309, last-90d=23). owed-runtime.
4. **cascade order reconcile**: P3a executor is cloud-first (`:591` before guard `:611`); design §G.2 wants Ollama-generate → math-gate → cloud-interpret-survivors. E1 implements the §G.2 order for hypothesize (cost discipline) — read both before wiring (§E.3 item 3).
5. **M4 artifact path**: align `..._screen_benchmark.json` (MIT) vs `..._screen_calibration.json` (P3a loader `:153`) — §F.1.

### H.4 owed-runtime (NOT design blockers; block the verdict going live)

- V127 population (`--write-db`) — categorical regime axis (§F.3); B1 binary mask does not need it.
- `agent.lessons` seed (5-10 dead-modes) — M4 bad-set + novelty source (§F.2); until seeded M4 correctly DISABLED.
- down-bars ≥30 confirmation in the chosen span (§H.3 item 3).
- altcap producer Linux smoke (real `market.klines` SELECT over 24 symbols × window).

### H.5 Sign-off chain (design-first; per execution-plan §2)

**PA → E1 → E2 → QC(B1 final numbers + leak-free PIT features) → MIT(M3 leak coverage + M4 recall) → E4 → QA → PM.** E2 review focus (3 high-risk points): (1) the math-gate stage order + strictest-wins verdict combination (§A.5) — assert B1 cannot be bypassed and a fail dominates; (2) the executor extension preserves the 0-order/lease/promote iron-rule verbatim + math gate has 0 LLM-invocation (§E.3 grep target); (3) altcap PIT walk-forward (§B.2) — the one M3 leak hot-spot (no today's-survivors, no zombie forward-fill).

---

## I. Risk rating + verdict

**Change risk: HIGH** (alpha-bearing promotion-relevant gate touching the math-gate stack; B1 is the down-beta-masquerade guard that killed 5 candidates — getting it wrong re-opens the exact failure mode). Mitigations: B1 is a pure-math additive function (0 DB/order); hypothesize stanza double-gated (`enabled=false` + L3 tier); 0 new live authority; the masquerade-kill is verified by feeding a known down-beta candidate and asserting fail/DEFER (E4).

**Verdict: E1-READY conditional on operator/QC/MIT ratification of 4 already-decided-but-cross-team items** (none re-open design; all are sign-off confirmations the chain provides):
1. **operator**: altcap = EQUAL-WEIGHT (QC already recommends; operator-lock per QC §5) — CONFIRMED in prompt ("operator 鎖").
2. **operator**: P3b zero-migration / V137 reserved-not-used / altcap on-the-fly — CONFIRMED in prompt.
3. **QC**: B1 final numbers + leak-free PIT (chain QC sign-off at P3b).
4. **MIT**: M3 producers (shift1/is_oos) + M4 recall (chain MIT sign-off at P3b); is_oos namesake → option (a) distinct module name (PA concurs).

**Everything else design-decided + grounded `file:line`.** Two E1 implementation decisions surfaced (not blockers, E1 acceptance items): (i) cascade order reconcile (§E.3 item 3 / §H.3 item 4) — implement §G.2 Ollama-generate→math-gate→cloud-interpret-survivors, not P3a cloud-first; (ii) M4 artifact path alignment (§F.1).

Design path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3b-implementation-design.md`.

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3b-implementation-design.md
