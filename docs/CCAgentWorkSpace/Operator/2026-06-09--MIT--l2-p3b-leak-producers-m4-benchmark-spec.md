# MIT P3b Prerequisite Spec — leak-free PIT producers (M3) + M4 benchmark + V127 down-market population

Date: 2026-06-09
Author: MIT (ML & Database Auditor)
Type: **DESIGN/SPEC — read-mostly; no business code written, no schema changed, no DB write, no cron install.**
Scope: the MIT-owned prerequisites that gate **P3b** (`ml_advisory.hypothesize` → promotion-relevant verdict, alpha-bearing). P3a (diagnose/interpret, zero-alpha) already green+committed `aeae4da4`; MIT already APPROVE-CONDITIONAL'd M3 typing + M4 mechanism (typing-only for P3a).
SSOT: PA P3 design `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3-ml-advisory-tech-design.md` §E/§F/§G/§J; design v4 §E.2(0) lines 884-903 (M3) + §G.2.1 lines 1246-1277 (M4); `V127__aeg_regime_labels.sql`; `agent.lessons` V133.
Boundary vs QC: MIT owns leak-typing producers + M4 benchmark + V127 population mechanics. QC owns B1 final numbers + altcap basket construction + down-market window ratification. The altcap basket (the biggest B1 data gap) is **NOT** in this report — it is QC-owned.

---

## 0. Runtime ground truth (ssh trade-core docker exec PG live 2026-06-09, sqlx_max=133)

All five queries read-only. These are the load-bearing facts; everything below is grounded in them.

| Query | Result | Implication |
|---|---|---|
| `research.aeg_regime_labels` count | **0 rows** | V127 schema applied (sqlx_max=133) but **population NEVER ran**. PA "owed-verify" → CONFIRMED EMPTY. Blocks B1 down-market regime axis. |
| `research.aeg_regime_transitions` count | 0 rows | same — runner `--write-db` never invoked. |
| `agent.lessons` count | **0 rows** | M4 bad-set source + novelty-dedupe source are **empty**. No L2 session has persisted a lesson. |
| `market.klines` BTCUSDT 1d | **730 rows, 2024-06-02 → 2026-06-01 (729d span)** | B1 BTC factor + down-market sub-sample raw data **READY** (no gap). |
| `learning.model_registry` count | **3 rows** | M4 good-set source: thin but non-zero (3 promoted models). |
| `learning.mlde_shadow_recommendations` count | 20313 rows | sink active (corroborates P3a S-2 semantic-overload finding). |
| BTC down-market bars (leak-free, prior-only `ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING`) | **309/730 either-down** (7d<-5%=123; 30d-dd>8%=285); **last 90d = only 23 down-bars** | B1 down-market mask is empirically populatable from BTC 1d, BUT a 90d window yields <30 down-bars → **B1 down sub-sample must use ≥180d/full-span, not 90d** (see §3.3). |

**Two empty tables are the gating fact:** V127 population (B1 down-regime) and agent.lessons (M4 bad-set + novelty) are both schema-ready / writer-ready / **runtime-empty**. Neither blocks the P3b *design*; both block the P3b *promotion-relevant verdict going live*.

---

## 1. `shift1_compliance` / `is_oos_gap` producer design (M3 leak-free PIT)

Both producers emit a typed evidence row that feeds the M3 leak-free set `source_class ∈ {shift1_compliance, is_oos_gap}` (`l2_prompt_contract_registry.py:164`). The P3a guard already enforces the typing (rejects a `leak_free=true` claim backed only by `name_pattern_check` — verified in my P3a sign-off, invariant B.2). What does NOT exist is the **producer** that earns a `shift1_compliance` / `is_oos_gap` source_class. This section is the precise build for E1.

### 1.1 ★ MAJOR REUSE FIND — `shift1_compliance` is NOT greenfield

`helper_scripts/m4/feature_engineering_validator.py` (read in full) **already implements** the substance of shift1_compliance:

| Existing function (`feature_engineering_validator.py`) | What it does | shift1_compliance use |
|---|---|---|
| `is_leaky_sql(sql)` (`:43-48`) | regex: `ROWS BETWEEN N PRECEDING AND CURRENT ROW` = leak | SQL-side static check |
| `is_leakfree_sql(sql)` (`:51-60`) | regex: `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` = leak-free | SQL-side positive proof |
| `is_leaky_pandas(code)` (`:63-69`) | regex: `.rolling(N)` WITHOUT preceding `.shift(1)` = leak | pandas-side static check |
| **`validate_shift1_pattern(feature_values, forward_return_bps, window, diff_threshold=0.1)` (`:72-113`)** | **empirical**: computes `leak_corr` (slice incl. current bar) vs `clean_corr` (shift(1) slice), `diff=|leak_corr-clean_corr|`, `leak_suspected = diff>threshold`; aligns Rust `m4_miner::feature_engineering::validate_leak_free_pattern` | **the core empirical compliance test** |
| `shift1_rolling_mean_pure_python` / `shift1_rolling_std_pure_python` (`:116-156`) | leak-free reference impls (`output[i]` depends only on `values[i-window:i]`, ddof=0) | reference oracle |

**Determination: `shift1_compliance` producer = a thin adapter** that calls these existing functions and emits a typed evidence row. NOT a new algorithm.

#### 1.1.1 `shift1_compliance` producer — what it computes

Input: the training-run's feature definitions + the realized feature/forward-return series the pipeline already produced (post-training, read-only — same leak-free posture as P3a §A).

Two-layer check (static + empirical), per feature:
1. **Static (cheap, structural)**: if the feature's compute expression is available (SQL window / pandas / polars), run `is_leaky_sql`/`is_leakfree_sql`/`is_leaky_pandas`. A `is_leakfree_sql` positive (`AND 1 PRECEDING`) is structural proof of shift(1); a `is_leaky_*` positive is an immediate FAIL.
2. **Empirical (the real proof)**: `validate_shift1_pattern(feature_values, forward_return_bps, window)`. If `leak_suspected=True` (leak-vs-clean correlation diverge > 0.1) → the feature behaves as if it peeked at its own bar → FAIL. If `insufficient_sample` → DEFER (not PASS — never auto-pass on thin data).

#### 1.1.2 `shift1_compliance` — code shape (E1 builds; pure compute, no DB write of its own)

```python
# program_code/ml_training/shift1_compliance.py  (NEW — MIT-owned, E1 builds)
# reuses helper_scripts/m4/feature_engineering_validator.py (no new leak algorithm)
def check_shift1_compliance(
    feature_series: dict[str, Sequence[float]],   # {feature_name: realized values, time-ordered}
    forward_return_bps: Sequence[float],          # aligned forward returns (label proxy)
    *,
    window: int,
    compute_exprs: dict[str, str] | None = None,  # optional: SQL/pandas source per feature
    diff_threshold: float = 0.1,
) -> Shift1ComplianceResult:
    # Shift1ComplianceResult{
    #   source_class: "shift1_compliance",          # the M3 typed tag
    #   leak_free: bool,                             # True only if ALL features pass + no DEFER
    #   per_feature: list[{feature, verdict:"pass|fail|defer",
    #                      static:{leaky_sql,leakfree_sql,leaky_pandas},
    #                      empirical:{leak_corr,clean_corr,diff,leak_suspected,insufficient_sample}}],
    #   reasons: list[str],
    #   evidence_ref: str,                           # training_run_id + feature_definition_hash
    # }
    ...
```

#### 1.1.3 `shift1_compliance` — output → M3

- `leak_free=True` ONLY when every feature is `pass` AND none is `defer` (fail-closed: any DEFER → `leak_free=False`, NOT a leak-free claim).
- The diagnose evidence row carries `source_class="shift1_compliance"` → enters the M3 leak-free set → a `hypothesize` "leak-free" assertion backed by THIS is legal (vs `name_pattern_check` which the guard rejects).
- This is the producer P3a's guard B.2 referenced as "legal typing; producer P3b-owned" (my P3a sign-off, Axis 1). It now exists for P3b.

### 1.2 `is_oos_gap` producer — must be built (namesake-different metric exists)

Confirmed: `sample_weight_sensitivity.py:329,433,440` has an `is_oos_gap` that is a **train-vs-OOS RMSE gap-ratio overfit detector** (`{mean_train_rmse, mean_oos_rmse, gap_ratio, withdraw_baseline}`) — NOT the M3 temporal-gap source-class. The M3 `is_oos_gap` means "a real in-sample → out-of-sample **temporal** gap with embargo, no leakage across the boundary" (design line 897). **Must build** (or QC/MIT formally repurpose the existing name — MIT recommends a distinct name to avoid the collision; see §1.2.3).

#### 1.2.1 `is_oos_gap` producer — what it computes

Given a CV split spec (train index set, test index set, label horizon H, embargo size E — all expressed as timestamps/bar indices), verify the split is **temporally leak-free** per `time-series-cv-protocol` §2:
1. **Temporal separation**: `max(train.signal_ts) < min(test.signal_ts)` (no future-in-train).
2. **Embargo gap present**: `min(test.signal_ts) - max(train.signal_ts) >= embargo_bars` (Lopez de Prado AFML Ch.7; `time-series-cv-protocol` §2.2). Embargo size from label horizon + autocorrelation (not hardcoded; the skill's rule).
3. **Purge applied**: no train sample whose label window `[t, t+H]` overlaps the test fold (`time-series-cv-protocol` §2.1). I.e. `train.label_end_ts < min(test.signal_ts)` for all kept train samples.
4. **No shuffle**: train and test are contiguous time blocks (KFold-shuffle forbidden — the skill's golden rule).

#### 1.2.2 `is_oos_gap` — shape + output

```python
# program_code/ml_training/is_oos_gap.py  (NEW — MIT-owned, E1 builds)
def check_oos_gap(
    train_signal_ts: Sequence,    # train fold timestamps
    test_signal_ts: Sequence,     # test fold timestamps
    train_label_end_ts: Sequence, # per-train-sample label window end (for purge)
    *,
    label_horizon_bars: int,
    embargo_bars: int,
) -> OosGapResult:
    # OosGapResult{
    #   source_class: "is_oos_gap",
    #   leak_free: bool,                        # all 4 checks pass
    #   temporal_separation_ok: bool,           # max(train)<min(test)
    #   embargo_gap_bars: int,                  # actual gap
    #   embargo_sufficient: bool,               # gap >= embargo_bars
    #   purge_violations: int,                  # train samples w/ label window into test
    #   shuffle_detected: bool,                 # non-contiguous fold
    #   reasons: list[str],
    # }
    ...
```

Output: `leak_free=True` ONLY when temporal_separation_ok AND embargo_sufficient AND purge_violations==0 AND NOT shuffle_detected. Feeds M3 set; a `hypothesize` leak-free claim citing a real OOS temporal gap is then legal.

#### 1.2.3 MIT recommendation on the namesake collision (operator/QC ratify)

The existing `sample_weight_sensitivity.is_oos_gap` (overfit RMSE-gap) and the M3 `is_oos_gap` (temporal-gap source_class) are **semantically different**. Two options:
- **(a) MIT preferred**: build the temporal producer under a **distinct internal name** (e.g. function `check_oos_gap`/module `is_oos_gap.py`) but keep the M3 **source_class string** `"is_oos_gap"` (the registry constant `:164` stays; it is a leak-typing tag, not the RMSE metric). No rename of the existing overfit metric. Zero collision at the source_class layer; only the human-facing names differ. **This is achievable today; recommend (a).**
- (b) rename the existing overfit metric — NOT recommended (touches `sample_weight_sensitivity.py` consumers for cosmetic reasons; violates surgical-change discipline).

### 1.3 Leak-typing coverage matrix (what P3b can legally claim)

| source_class | producer | exists today | P3b legal "leak-free" claim? |
|---|---|---|---|
| `name_pattern_check` | `leakage_check.py` (78 lines, name-substring only — re-confirmed this session) | YES | **NO** (guard B.2 rejects; necessary-not-sufficient) |
| `shift1_compliance` | `shift1_compliance.py` (NEW, **reuses** `feature_engineering_validator.py`) | NO → thin build | **YES** when leak_free=True |
| `is_oos_gap` | `is_oos_gap.py` (NEW, per `time-series-cv-protocol` §2) | NO → build | **YES** when leak_free=True |

**P3b gate wiring**: the §G.2 math gate's leak precondition (design line 158) requires `shift1_compliance and/or is_oos_gap`. Until both producers exist + return `leak_free=True` for a candidate, the math gate leak precondition cannot be satisfied → `hypothesize`'s promotion-relevant verdict DEFERs (consistent with fail-closed). This is correct: no producer ⇒ no leak-free claim ⇒ no promotion.

---

## 2. M4 benchmark artifact schema + initial set construction (MIT-owned)

The M4 screen (Ollama coarse gatekeeper) is currently **placeholder-DISABLED** (my P3a sign-off Axis 2: `load_ollama_screen_calibration` fail-closes to DISABLED with no artifact → everything routes to the deterministic gate, loses no alpha). To move it to live-calibrated, MIT builds the held-out benchmark and measures the screen's recall.

### 2.1 Finalized schema (extends E1's `{benchmark_version, recall, measured_at}`)

Per design §G.2.1 ("measure recall of the SCREEN, not the final answer") + my P3a recommendation. Artifact = **JSON file** (mirror the FND-2 CSV-artifact pattern — design §M, PA recommends on-the-fly/artifact to avoid a migration; I concur — no V137 for the benchmark):

```jsonc
// settings/l2_ml_advisory_screen_benchmark.json  (MIT-owned artifact; NOT a DB table)
{
  "benchmark_version": "v1",              // bump on set change; triggers recalibration
  "classifier_version": "<screen prompt+model pin>",  // e.g. "ollama_qwen2.5:7b@layer2_critic.v1" — pins the screen under test
  "measured_at": "2026-06-09T..Z",
  "recall_floor": 0.85,                   // PA default; MIT may raise (design line 1262)
  "threshold": "<screen operating point>",// the "loose" operating point (design line 1268)
  "n_good": 0,                            // |good set|
  "n_bad": 0,                             // |bad set|
  "recall": null,                         // tp/(tp+fn) over good set — the screen lets through ≥85%
  "precision": null,                      // tp/(tp+fp) — modest OK (gate provides precision)
  "per_class_recall": {
    "good_recall": null,                  // fraction of known-good the screen PASSES
    "bad_reject_rate": null               // fraction of known-bad the screen COARSE-REJECTS
  },
  "confusion": {"tp": 0, "fn": 0, "fp": 0, "tn": 0},
  "enabled_decision": "DISABLED"          // DISABLED until recall>=floor measured; gate-seam-logged
}
```

**Why these fields** (beyond E1's three): `precision`+`confusion` make the false-kill-vs-false-pass trade-off auditable (MIT-owned per design line 1276-1277); `per_class_recall.bad_reject_rate` confirms the screen actually sheds dead-modes (not just passing everything — the degenerate case design line 1270-1271 disables); `classifier_version` pins WHICH screen was measured (a prompt/model bump invalidates the calibration — design line 1273). Log every (re)calibration to D3 gate-seam (`record_gate_seam(gate_id="ollama_screen", ...)`) for the §O metric + MIT audit.

### 2.2 Initial good set

| Source | Count today | Notes |
|---|---|---|
| `learning.model_registry` promoted models | **3** (runtime-verified) | demo-confirmed discoveries (Stage-0R/Stage-1 promoted) — the canonical "good" class. |
| post-hoc-correct diagnoses: the 5 down-beta-masquerade NO-GOs | 5 (from memory: A1 funding_short, oi_delta, cascade-fade, funding-tilt, listing — each correctly diagnosed "beta, not alpha") | these are GOOD *diagnoses* (the correct answer was a NO-GO). They test the screen's ability to pass a correct skeptical reading. |

Good set ≈ **8** initial items. Thin but real. Grows as outcomes accrue (design line 1257).

### 2.3 Initial bad set — BLOCKED on population

| Source | Count today | Notes |
|---|---|---|
| `agent.lessons` V133 dead-modes | **0 rows (runtime-verified)** | the designated bad-set source is **EMPTY**. No L2 session has persisted a lesson. |

**This is the M4 blocker.** The screen calibration cannot measure `bad_reject_rate` (or compute meaningful precision) with an empty bad set. Two paths:
- **(a) seed `agent.lessons` from historical dead-modes** (the 5 down-beta NO-GOs as *bad hypotheses* — the statement "X is alpha" was wrong — distinct from §2.2 where the *diagnosis* was right; plus the broader dead-mode catalogue in memory). This is a one-shot seed via `persist_lessons` (V133's single-INSERT entry). MIT-specifiable, operator/E1-executed.
- (b) wait for organic L2 sessions to accrue lessons — slow; leaves M4 placeholder-DISABLED indefinitely.

MIT recommends **(a)** — seed ~5-10 known dead-modes so the benchmark has both classes. Until then, **M4 correctly stays placeholder-DISABLED** (subtraction-only; everything to the deterministic gate; loses no alpha — exactly the conservative start I approved in P3a).

### 2.4 How to build the initial benchmark (move off placeholder-DISABLED)

1. **Seed bad set**: `persist_lessons` the 5+ historical dead-modes into `agent.lessons` (lesson_type="dead_mode", content=the failed hypothesis statement + why it was beta-masquerade). One-shot; operator/E1.
2. **Assemble good set**: 3 model_registry promoted + 5 correct NO-GO diagnoses → good-set JSON.
3. **Run the screen** over (good ∪ bad), record pass-through vs coarse-reject per item → fill `confusion`/`recall`/`precision`/`per_class_recall`.
4. **Decision**: if `recall >= 0.85` AND `bad_reject_rate` materially > 0 → `enabled_decision="ENABLED"` at the loosest threshold meeting recall≥0.85 (design line 1268). Else `DISABLED` + flag MIT (design line 1271).
5. **Log** to D3 gate-seam; write artifact JSON; `load_ollama_screen_calibration` reads it (the loader I verified in P3a reads exactly this artifact and fail-closes if recall<floor or missing).

---

## 3. V127 down-market regime label population — verify + spec

### 3.1 Verification (Linux) — DONE this session

- **`research.aeg_regime_labels` = 0 rows** → population NEVER ran. PA owed-verify CONFIRMED EMPTY.
- `aeg_regime_transitions` = 0; runner `--write-db` (`harness.py:218-219, _write_db:224-245`) never invoked.
- V127 schema IS applied (sqlx_max=133 ≥ 127) — Guard A/B/C are in the tree; the tables/hypertables/indexes exist, just no rows.
- BTC 1d source = 730 rows / 729d → population is feasible (raw data ready).

### 3.2 The runner is already leak-free PIT (no rebuild needed for population)

I read `classifier.py` + `data_loader.py` in full:
- **`compute_feature_rows_for_symbol` (`classifier.py:110-178`) is leak-free**: signal at index `i` uses `prior = close_arr[:i]` (`:130`) — strictly closes **before** `i` — and `feature_ts = ts_arr[i-1]` (`:131`). This IS the shift(1) discipline (a bar's label never sees its own close). The docstring (`:119-121`) states it explicitly: "第 i 個 signal_ts 只能看 closes[:i]". `ret_30d` = `_ret(prior,30)` (`:133`), `ret_90d` = `_ret(prior,90)` (`:134`) — both prior-only.
- **`data_loader.load_daily_closes` (`data_loader.py:46-92`) is leak-free**: `history_start = window_start - lookback_days` (`:63`) provides prior context WITHOUT borrowing in-window future, and the `closed_bar_cutoff` filter (`:78`) excludes un-closed bars. Docstring `:59-60`: "避免 runner 在沒有足夠 prior context 時偷用 window 內未來分布補樣本".
- **Correction to a stale cross-reference**: the V127 §F NOTICE (`V127:609`) warns "修 full-sample vol-tercile cross-section leak（data_loader.py:300 不可繼承）". That refers to the **ML-training `data_loader.py`** (the QC/MIT cross-finding from `project_2026_06_03_v58...`), **NOT** this aeg-runner `data_loader.py` (which is 105 lines, no line 300, and is clean). The aeg-runner data path does not inherit that leak. (E1 should not conflate the two files.)

### 3.3 Population spec (operator/E1 runs; MIT specifies parameters)

The down-market mask B1 needs (30d drawdown >8% OR 7d return <-5%, lagged-PIT, ≥30 down-bars) is derivable two ways — and BOTH should be leak-free prior-only:

**Path A — populate V127, derive mask from stored features (PA's design intent):**
```
python3 -m helper_scripts.research.aeg_regime_runner.harness \
  --run-id aeg_s2_pop_$(date +%Y%m%d) \
  --fnd2-run-dir <FND-2 universe artifact dir> \   # survivorship-correct symbol set
  --window-start 2024-06-02 --window-end 2026-06-01 \  # full BTC 1d span (see §3.4 why not 90d)
  --cutoff <last-closed-bar UTC> \
  --lookback-days 430 \                            # already provides ≥200d prior for ma_200
  --write-db                                        # the population switch (default OFF)
```
This writes `ret_30d`/`ret_90d`/`main_regime`/`market_anchor_regime` per (symbol, daily bar). B1's down-market mask then reads V127: a bar is down-market if `ret_30d < <30d-drawdown-proxy>` OR a derived 7d return < -0.05. **Caveat**: V127 stores `ret_30d`/`ret_90d` (log returns) but NOT a 7d return and NOT a 30d *drawdown* (peak-to-current) directly — the 7d return + drawdown must be computed from `market.klines` 1d (as my §0 verification query did, leak-free with `ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING`). So V127 gives the regime *label* axis; the precise B1 down-mask (drawdown>8% OR 7d<-5%) is computed from klines. Both are PIT.

**Path B — compute the down-mask purely from `market.klines` 1d** (no V127 dependency for the mask itself): exactly my §0 query. B1 can use this directly; V127 then supplies the *categorical regime label* (bull/bear/high-vol/chop/range) as an orthogonal axis, not the binary down-mask.

**MIT recommendation**: B1's binary down-market mask = **Path B** (klines-direct, leak-free, no population dependency — unblocks B1 sooner). V127 population = still valuable (regime-categorical axis for §C.2 robustness matrix + AEG-S2), but **B1 does not strictly need V127 populated** if the down-mask is computed from klines. This is a de-risking finding: **B1's down-regime axis is NOT hard-blocked on V127 population** — only on QC ratifying the window (§3.4) + the altcap basket (QC-owned, separate).

### 3.4 ★ Down-market window constraint (empirical — QC must ratify)

My §0 query found: **last 90d = only 23 down-market bars** (< B1's ≥30 threshold). 30d-drawdown>8% bars = 285 over the full span; 7d<-5% = 123. Therefore:
- A **90d** B1 down-market sub-sample → <30 down-bars → B1 DEFERs on `|β_down|` (design §N.1 (4): "≥30 bars else DEFER"). Correct fail-closed, but means 90d is structurally insufficient for the down-market leg.
- A **≥180d or full-span (729d)** window → 309 down-bars available → clears the ≥30 gate comfortably.
- **MIT spec to QC**: B1's `WINDOW_DAYS≥90` (design §N.1 (3)) governs the **overall** β regression, but the **down-market sub-sample** must draw from a **longer window (≥180d, recommend full 2-yr span)** to satisfy the ≥30-down-bar precondition. These are two different windows — QC's "B1 four final numbers" should explicitly state the down-sub-sample window separately. This is a real constraint surfaced by runtime data, not a design assumption.

### 3.5 Down-market def alignment — CONFIRMED

The design's down-market def (30d drawdown >8% OR 7d return <-5%, execution-plan §1 B1 line 65) is **exactly** what my §0 query implemented leak-free: `close < peak_30d_prior*0.92` (drawdown from 30d prior peak > 8%) OR `close < close_7d_ago*0.95` (7d return < -5%), both prior-only (`ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING`, `LAG(close,7)`). The def is computable, PIT, and aligned. No ambiguity for E1.

---

## 4. Residual items for operator / QC / MIT (ratify before P3b ship)

| Item | Owner | Status / MIT position |
|---|---|---|
| **B1 down-market sub-sample window** | **QC** | Runtime says 90d = only 23 down-bars < 30 → **must be ≥180d/full-span** for the down leg. QC's "B1 four numbers" should state the down-window separately. |
| **Altcap cap-weighted basket** | **QC** | 0 producer (PA §E.3, the biggest B1 gap). NOT in this report (QC-owned). Until it exists, B1 dual-factor → BTC-only → DEFER. |
| **V127 population (`--write-db`)** | **operator/E1** | 0 rows. Needed for the regime-categorical axis (§C.2 robustness); **NOT strictly needed for B1's binary down-mask** if computed from klines (§3.3 Path B). |
| **agent.lessons seed (M4 bad-set + novelty)** | **operator/E1** | 0 rows. Blocks M4 moving off placeholder-DISABLED. MIT spec: seed 5-10 historical dead-modes via `persist_lessons` (§2.3/§2.4). |
| **`shift1_compliance` producer** | **MIT-owned, E1 builds** | thin adapter over `feature_engineering_validator.py` (reuse, not greenfield) (§1.1). |
| **`is_oos_gap` producer** | **MIT-owned, E1 builds** | new, per `time-series-cv-protocol` §2; keep source_class string, distinct internal name to dodge the `sample_weight_sensitivity` collision (§1.2.3). |
| **M4 benchmark artifact build** | **MIT-owned** | schema finalized (§2.1); good-set ≈8 ready; bad-set blocked on agent.lessons seed (§2.3). Artifact = JSON file, no migration. |
| **is_oos_gap namesake collision** | **QC/MIT ratify** | MIT recommends option (a): keep `"is_oos_gap"` source_class string, distinct module/function name. |

**None of these reopen V137.** Both producers are compute (read existing data). The M4 benchmark is a JSON artifact (FND-2 pattern). V127 population is a runner invocation, not schema. P3b stays zero-migration (consistent with PA §M + my P3a finding).

---

## 5. P3b sign-off criteria (what MIT will verify when P3b is dispatched)

1. **Leak coverage**: `shift1_compliance` + `is_oos_gap` producers exist, return `leak_free=True/False/DEFER` correctly; a `hypothesize` leak-free claim is backed by one of them, NOT `name_pattern_check` (the guard already enforces — I'll verify the producers actually feed it).
2. **M4 recall**: benchmark artifact has both classes (good ∪ bad, n_bad>0), measured recall ≥ 0.85 to ENABLE the screen (else correctly DISABLED + flagged); `classifier_version` pinned.
3. **B1 leak-free**: down-market mask computed prior-only (`ROWS BETWEEN N PRECEDING AND 1 PRECEDING` / `LAG`); down sub-sample window ≥180d (≥30 down-bars); BTC-only → DEFER (no false neutral); `β_upper=β+1.96·SE<0.20`.
4. **Zero leak through unattended gate**: the masquerade B1 defends (down-beta dressed as alpha) cannot pass — verified by feeding a known down-beta candidate and asserting B1 FAIL/DEFER.

Leakage / look-ahead is the alpha命門 — these are strict gates, verified empirically (Linux), not by static parse.

---

## Files / data this report grounds in (read in full this session)

| Source | Role |
|---|---|
| `ml_training/leakage_check.py` (78 lines) | re-confirmed name-substring only — `name_pattern_check` cannot prove leak-free |
| `helper_scripts/m4/feature_engineering_validator.py` (full) | **the shift1_compliance reuse find** (`is_leaky_sql`/`validate_shift1_pattern`/pure-Python ref) |
| `helper_scripts/research/aeg_regime_runner/classifier.py` (full) | leak-free PIT confirmed (`prior=close_arr[:i]`, `feature_ts=ts_arr[i-1]`) |
| `helper_scripts/research/aeg_regime_runner/data_loader.py` (full) | leak-free confirmed (lookback history_start + closed_bar_cutoff); NOT the leaky ML-training data_loader |
| `helper_scripts/research/aeg_regime_runner/harness.py` (full) | `--write-db` population path (`_write_db:224-245`); default artifact-only |
| `sql/migrations/V127__aeg_regime_labels.sql` (full) | schema applied; population owed; §F cross-ref to a different data_loader corrected |
| `sql/migrations/V133__agent_lessons.sql` (full) | `agent.lessons` schema (M4 bad-set + novelty source); `persist_lessons` single-INSERT entry |
| design v4 §E.2(0) 884-903 + §G.2.1 1246-1277 | M3 typing + M4 calibration SSOT |
| PA P3 design §E/§F/§G/§J | B1/M3/M4/V127 design determinations |
| Linux PG (5 read-only queries) | V127=0, agent.lessons=0, BTC 1d=730/729d, model_registry=3, 309 down-bars, last-90d=23 down-bars |

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-09--l2-p3b-leak-producers-m4-benchmark-spec.md
