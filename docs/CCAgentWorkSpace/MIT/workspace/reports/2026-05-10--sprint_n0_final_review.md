# MIT Sprint N+0 Final Review — V080-V084 + W-AUDIT-4b producer chain + invariant 21

- **Date**: 2026-05-10
- **Sprint**: N+0 final
- **Scope**: 4 V### migration (V080/V082/V083/V084) + W-AUDIT-4b 6-table INSERT path producer chain (M1+M2+M3 incl. E1-FIX-W2 retract) + W-AUDIT-9 T2 governance.canary_stage_log + AlphaSurface Phase A schema + invariant 21 P0-MIT-LABEL-CLOSE-TAG-1 + 6 push-back / risk items
- **Read-only stance** — no schema or code changes, source/static analysis only
- **Mac dev RCA blind spot caveat**: Mac has no live PG; row-rate / runtime acquisition uses static analysis + commit history + sub-agent E1 reports as proxy. Linux empirical verification required for items flagged with `[Linux PG VERIFY]`.

---

## 1. V### Schema Review (4 migrations)

### 1.1 V080 `governance.canary_stage_log` + `governance.canary_stage_metric_registry`

**Verdict**: PASS APPROVE — Guard A/B/C complete; idempotency confirmed via Linux PG empirical dry-run (per E1-A report §5.3); CHECK constraints semantically correct.

| Aspect | Status | Evidence |
|---|---|---|
| Guard A (canary_stage_log columns) | PASS | V080 lines 55-89, 9 required columns checked via `array_agg` pattern |
| Guard A (canary_stage_metric_registry columns) | PASS | V080 lines 95-126, 7 required columns |
| Guard C (idx_canary_stage_log_cohort_created_at column ordering) | PASS | V080 lines 345-364, asserts `created_at_ms DESC` ordering |
| `manual_promote NOT NULL` constraint (E2 audit point #2) | PASS | V080 lines 186-190 — PG-layer enforcement (`transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL`); **not just application-level** ✓ |
| stage value range CHECK (0..=4) | PASS | V080 lines 168-171, 275-276 |
| transition_kind enum CHECK | PASS | V080 lines 174-180, 4 values |
| direction enum CHECK | PASS | V080 lines 278-284, 4 values |
| `created_at_ms` sane epoch CHECK (>= 2020-01-01) | PASS | V080 lines 194-195 |
| `triggered_value` NaN/Inf guard | PASS | V080 lines 199-205 (NaN-self-not-equal trick) |
| Partial index for rollback events | PASS | V080 lines 332-334 (`WHERE transition_kind IN ('auto_rollback', 'incident_rollback')`) — bounded growth |
| UNIQUE active partial index `(stage, metric_name) WHERE active=true` | PASS | V080 lines 373-375 — drift detection + audit-soft-delete friendly |
| Linux PG empirical dry-run | PASS | E1-A report §5.3: first apply CREATE OK / second apply NOTICE-skip / `INSERT manual_promote NULL lease` REJECTED with `check_violation` / `INSERT auto_promote NULL lease` ACCEPTED / `stage=5` REJECTED |
| Idempotency (re-run NOTICE-only) | PASS | E1-A report §5.3 confirmed |

**Push-back / Risk**:
- **MED**: AMD-2026-05-09-03 §4.2 references `canary_stage_metric_registry` for healthcheck `[58]` reads, but no FK relationship from `canary_stage_log.triggered_metric` to `canary_stage_metric_registry.metric_name`. Drift is possible (auto_promote writes a metric_name not in registry). E2 audit point coverage is partial — recommend follow-up V08X to add either FK constraint or runtime validation in healthcheck `[58]`. Not blocking N+0.
- **LOW**: V080 line 268 `description` column is NULL-allowed but no length check. Future GUI surface (W-AUDIT-9 T5) may benefit from `CHECK (description IS NULL OR length(description) <= 4096)`.
- **LOW**: No `created_at_ms` index on metric_registry — operator manual TOML seed audit timeline scan will be O(N), but row count is < 100, so non-blocker.

### 1.2 V082 `learning.decision_features_evaluations` (W-AUDIT-4b-M1)

**Verdict**: PASS APPROVE — Guard chain complete, schema design separates evaluation log from production training pool (CLAUDE.md §九 Non-training surfaces compliant), idempotency verified.

| Aspect | Status | Evidence |
|---|---|---|
| Guard A (learning schema exists) | PASS | V082 lines 59-66 |
| Guard A2 (legacy decision_features columns) | PASS | V082 lines 73-102, 10 required V017-aligned columns |
| Guard A3 (new table schema drift on re-run) | PASS | V082 lines 109-140, 14 required columns |
| Guard C (hot-path index column order) | PASS | V082 lines 240-262, asserts `(strategy_name, engine_mode, ts DESC)` |
| evaluation_outcome enum CHECK (7 values) | PASS | V082 lines 184-193 — aligned to PredictorAction |
| evidence_source_tier enum CHECK (2 values, intentionally non-overlapping with V050 replay tiers) | PASS | V082 lines 206-211 — prevents downstream ML SELECT pool contamination ✓ |
| side enum CHECK (-1/+1) | PASS | V082 lines 222-225 |
| BIGSERIAL PK (no dedup, allows multi-evaluation per context_id) | PASS | V082 line 147 — semantic difference from V017 PK=context_id documented in COMMENT |
| 4 indexes (strategy_mode_ts, ts_DESC, context_id, outcome_ts) | PASS | V082 lines 264-277 |
| Idempotency | PASS | E1-E report §驗證證據: Linux PG dry-run #1 + #2 NOTICE-only |
| Linux PG empirical dry-run | PASS | E1-E report: "Linux PG V082 dry-run #1/#2 PASS" |
| **No label_* columns on evaluations table** | PASS | Confirmed via grep — table is producer-debug only, intentionally NOT a training source |

**Push-back / Risk**:
- **MED**: V082 evaluations table writes 24h ~30k rows per E1-E spec (38k legacy → producer改造後類似量級). **No retention policy.** TimescaleDB hypertable is NOT configured. Long-term storage growth = ~1M rows/month. Recommend follow-up V08X add `add_retention_policy('learning.decision_features_evaluations', INTERVAL '30 days')` after hypertable conversion. Not blocking N+0 but BLOCKER for sustained operation.
- **LOW**: `evidence_source_tier='shadow_synthetic'` is V082-defined but unclear if writer ever sets this value in M1 commit. Per E1-E report §不確定 #2, shadow_mode→PredictorAction::UseLegacyGate writes `evaluation_log` not `shadow_synthetic`. The 'shadow_synthetic' tier may be dead code at runtime — verify after 24h Linux PG SELECT.
- **GREEN**: ML training safety boundary is clean. `mlde_edge_training_rows` view reads `learning.decision_features` (production), NOT `decision_features_evaluations`. Pool not contaminated. ✓

### 1.3 V083 `trading.fills` entry_context_id close-fill enforcement (W-AUDIT-4b-M2)

**Verdict**: PASS APPROVE WITH CAVEAT — Guard chain complete, NOT VALID CHECK is correct strategy; **MED RISK** flagged for future ALTER VALIDATE CONSTRAINT lock duration.

| Aspect | Status | Evidence |
|---|---|---|
| Guard A (trading schema) | PASS | V083 lines 68-75 |
| Guard A2 (trading.fills columns including V003+V017+V021+V033 chain) | PASS | V083 lines 83-111, 9 required columns |
| Guard B (entry_context_id type = TEXT, V017 alignment) | PASS | V083 lines 117-130 |
| Guard C (partial index column list) | PASS | V083 lines 136-159, asserts strategy_name + engine_mode + symbol + side + ts |
| NOT VALID CHECK semantic | PASS | V083 lines 178-181: `exit_reason IS NULL OR entry_context_id IS NOT NULL` — only enforces new INSERTs, historical 175 rows (38% NULL close fills) untouched ✓ |
| Partial index `WHERE entry_context_id IS NULL` | PASS | V083 lines 198-200 — backfill cron lookup hot path, bounded size |
| Telemetry view `observability.fills_entry_context_id_health` | PASS | V083 lines 222-244, computes 24h null_ratio per engine_mode for healthcheck consumption |
| Idempotency | PASS | V083 lines 280-284 design — NOT VALID re-run no-op via `IF NOT EXISTS` constraint check |
| Linux PG empirical dry-run | **BLOCKED** | E1-B report §不確定 #1: "Linux PG V083 dry-run **未跑** (Mac sandbox refused production read) — 必由 E4 / operator 接手" — **must verify before Sprint N+0 sign-off** |

**Push-back / Risk** (HIGH/MED):
- **HIGH `[Linux PG VERIFY]`**: V083 Linux PG dry-run NOT executed (per E1-B report). Mac mock pytest does NOT catch PG runtime semantic per CLAUDE.md §七 V055 教訓. **MUST be tested on trade-core before invariant 18 PASS** — risk of NOT VALID parser quirk on TimescaleDB hypertable.
- **MED**: Future `ALTER TABLE trading.fills VALIDATE CONSTRAINT chk_fills_close_has_entry_context_id_v083` (M2 +7d observation period per V083 line 169) will trigger full table scan + ACCESS EXCLUSIVE lock. With 25k+ historical rows + hypertable chunks, lock duration estimate **30s-3min** depending on chunk count. Recommend operator schedule during low-activity window + dry-run on copy first. **Not blocking N+0**, but needs explicit operator runbook before VALIDATE.
- **MED**: Backfill SQL `entry.side <> c.side` opposite-side JOIN (E1-B report §關鍵 diff `_BACKFILL_FILL_ENTRY_CONTEXT_SQL`) assumes Buy↔Sell symmetric pairing. funding_arb retired (per AMD-2026-05-09-02), but if any future strategy splits multi-leg close (TP partial + remainder close), the backfill cron will mis-pair. Document strategy taxonomy invariant explicitly.
- **LOW**: 7-day inner LATERAL window for entry lookup (`entry.ts > (c.ts - INTERVAL '7 days')`) excludes any position held >7d. funding_arb history had >7d positions; if any other strategy ever holds >7d, those close fills remain NULL and become permanent gap.
- **GREEN**: ENTRY fill (open path) `entry_context_id = NULL` BY DESIGN — edge_label_backfill SQL relies on this NULL convention. V083 NOT VALID CHECK explicitly preserves this via `exit_reason IS NULL` branch. ✓

### 1.4 V084 `learning.mlde_sample_weight` UDF + `mlde_edge_training_rows` view (W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1)

**Verdict**: PASS APPROVE WITH CAVEAT — Guard A/B complete, UDF IMMUTABLE+PARALLEL SAFE correct, view backward-compatible, but **HIGH RISK** flagged for class weight semantic + invariant 21 mock estimate over-optimism.

| Aspect | Status | Evidence |
|---|---|---|
| Guard A (3 label columns existence) | PASS | V084 lines 65-89 |
| Guard B (3 label column types) | PASS | V084 lines 92-125 — text / float / timestamp |
| UDF `learning.mlde_sample_weight(close_tag)` IMMUTABLE | PASS | V084 lines 137-147 — eligible for plan cache + index expression |
| UDF PARALLEL SAFE | PASS | V084 line 141 — eligible for parallel scan |
| UDF return type DOUBLE PRECISION | PASS | V084 line 138 |
| 1/170 hardcoded ratio | PASS WITH RISK (see push-back below) | V084 line 144 |
| View `mlde_edge_training_rows` re-creation preserves V034 schema | PASS | V084 lines 157-387 — recreated WITH/SELECT structure identical to V034 baseline (verified by grep on attribution_chain_ok formula) |
| `attribution_chain_ok` formula PRESERVED | PASS | V084 lines 339-343 — `(signal_id NOT NULL AND context_id NOT NULL AND signal_context_id = context_id AND label_net_edge_bps NOT NULL)` — V031/V034 untouched |
| `sample_weight` column appended at view tail | PASS | V084 line 386 — backward-compat (column-unaware downstream trainer = automatic ignore) |
| Idempotency | PASS | CREATE OR REPLACE FUNCTION + CREATE OR REPLACE VIEW natural |
| Linux PG empirical dry-run | **BLOCKED** | E1-C report §不確定 #1 + §治理對照: "Linux PG dry-run Mac 無 PG, 未跑" — E4 must verify on trade-core |

**Push-back / Risk** (HIGH):

- **HIGH `[ML methodology]`**: 1/170 sample weight has multiple compounding issues:
  1. **Hardcoded ratio drift**: spec rationale = "reject:fill 70:1 + 100x safety margin" (V084 line 362). But empirical ratio per MIT v3 = `12,681 intent / 175 fill = 72.46:1`. `100x safety margin` is arbitrary — no statistical justification. Recommend run actual class weight = `n_majority / n_minority` per LightGBM/sklearn convention (~72) or PA-defined penalty function.
  2. **Imbalance handling vs cost-sensitive learning**: 1/170 weight on reject pool means each reject has effectively 0.59% the training signal of a fill. For LightGBM `is_unbalance=true` or `scale_pos_weight=170` is the more standard parameter; sample_weight column requires trainer to call `lgb.Dataset(..., weight=sample_weight)`. **No trainer in current commit subscribes to sample_weight** (per E1-C report §不確定 #3).
  3. **LinUCB / Thompson sampling pose-different problem**: bandit algorithms don't directly consume sample_weight. They learn action-reward distributions. A reject with `label_net_edge_bps=0.0` and weight 1/170 is nearly indistinguishable from no-data for LinUCB UCB calculations.
  4. **DL3 ensemble**: deep models with `class_weight={0: 1/170, 1: 1.0}` in Keras compile is the more idiomatic pattern, NOT per-sample weight column. Need consistent translation layer per model type.

  **Recommendation**: V084 ships sample_weight column for OPTIONAL opt-in by future trainer. Sprint N+1 should add per-trainer adapter (linucb_trainer / mlde_shadow_advisor / mlde_demo_applier / scorer_trainer / quantile_trainer / 3-DL).

- **HIGH `[invariant 21 risk]`**: invariant 21 acceptance = `attribution_chain_ok 24h ≥ 5%`. This requires:
  1. label_close_tag writer (V084 + Rust producer M3 part 2) to write 'rejected_governance' on reject paths
  2. label_net_edge_bps to be NOT NULL (the formula's binding clause)
  3. signal_id + context_id + signal_context_id chain to match
  
  **PA mock estimate "0.5% → ~90%"** in dispatch plan is OVER-OPTIMISTIC. True estimate analysis:
  - Pre-fix denominator = 12,681 intents/24h (incl. 12,506 rejects)
  - Pre-fix numerator = 76 (fills with full chain) → 0.6%
  - Post-fix numerator = 76 (existing fills) + 12,506 (rejects writing label) = ~12,582
  - Post-fix denominator unchanged = 12,681
  - Predicted ratio = 12,582 / 12,681 ≈ **99.2%** IF reject path writes `signal_context_id == context_id` AND `label_net_edge_bps IS NOT NULL`
  - **Realistic ratio ≈ 60-90%** depending on:
    - whether reject paths preserve signal_id chain integrity (paper engine path 1 pre_risk inline build features may NOT have signal_id from prior signal step)
    - pre_risk emit only fires on demo/live_demo (paper engine bypasses path 1 — per E1-C §不確定 #4)
  
  **Realistic mock**: 60-80%. **Operator should not commit to 90% as success criterion** — invariant 21 ≥ 5% is achievable but ratio between 5%-95% needs RCA case-by-case.

- **HIGH `[E4 third-pass observation per task brief]`**: task notes "runtime 仍 0.286% (engine 跑舊 binary)". This is **expected**: V084 + M3 producer change is in main repo but not deployed to engine PID 298034 (built 14:02 UTC vs commits later). After `restart_all.sh --rebuild --keep-auth`:
  - Window for ratio recovery model: 24h continuous engine uptime needed (per `attribution_chain_ok` 24h sliding window)
  - First 1h: noise only (ratio drift from old data dominance)
  - 4-12h: ratio rises proportional to (new reject rows accumulated) / (24h window)
  - 24h: reach steady state — should be 60-90%
  - **Recommend healthcheck `[42b]` add 6h moving-average warning bound** to detect regression after deploy

- **MED**: V084 line 110 `label_net_edge_bps` type CHECK accepts `('double precision', 'real', 'numeric')`. Empirical V017 type should be exactly one — accepting all three is permissive. Recommend tighten to actual V017 type after `[Linux PG VERIFY]`.

- **LOW**: V084 line 121 `label_filled_at` type CHECK uses `LIKE 'timestamp%'` — accepts both `timestamp without time zone` and `timestamp with time zone`. CLAUDE.md §三 convention is TIMESTAMPTZ everywhere. Tighten to `IN ('timestamp with time zone')`.

---

## 2. W-AUDIT-4b 6-Table INSERT Path Producer Chain (FA invariant 5)

### 2.1 Producer chain mapping (current state)

| Step | Source | Target table | Wired? | Evidence |
|---|---|---|---|---|
| 1. Intent emit (success path) | `step_4_5_dispatch.rs` paper/exchange success | `learning.decision_features` (intent-only) | YES (M1) | E1-E report §關鍵 diff Caller 改造 |
| 2. Candidate evaluation | `intent_processor::evaluate_predictor_gate` | `learning.decision_features_evaluations` | YES (M1) | V082 + decision_feature_evaluation_writer.rs |
| 3. Fill record (entry/close) | `trading_writer::flush_fills` | `trading.fills` with `entry_context_id` | YES (M2) | E1-B report — Rust writer-side enforcement + WARN log + V083 NOT VALID + cron backfill |
| 4. Governance reject (3 paths) | `step_4_5_dispatch.rs` pre_risk + exchange + paper | `learning.decision_features` with `label_close_tag='rejected_governance'` | YES (M3 part 2) | E1-FIX-W2 commit chain — `grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` = 5 hits ✓ |
| 5. Backfill / label fill | `edge_label_backfill.py` cron Step 1 + Step 2 | `learning.decision_features.label_filled_at` | YES (M2 backfill cron) | E1-B report — `_BACKFILL_FILL_ENTRY_CONTEXT_SQL` + cron upgrade |
| 6. Sample weight surface | V084 UDF + view column | `mlde_edge_training_rows.sample_weight` | YES (M3) | V084 line 386 |
| 7. **feature_baselines** writer | (none — Sprint N+1 candidate) | `observability.feature_baselines` | **NO** | Per memory `2026-05-09 v2`: feature_baseline_writer is CLI dry-run, no daemon, drift chain still broken |

### 2.2 FA invariant 5 sequential ordering verdict

FA invariant 5 specifies: "feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行".

**Current Sprint N+0 sequence does NOT match FA invariant 5 strict ordering**. Reasoning:
- W-AUDIT-4b M1 → M2 → M3 (decision_features producer + fills writer + reject negative label) is the actual sequence implemented
- `feature_baselines` is NOT in Sprint N+0 scope — it's a Sprint N+1 P1 candidate (memory 2026-05-09 v2 final state)
- mlde_edge_training_rows is a VIEW (not a producer-target) — populated transitively through underlying tables

**Verdict**: invariant 5 wording presupposes feature_baselines is part of Sprint N+0 producer chain, which is NOT the case. FA wording needs reframe; current N+0 producer chain (M1+M2+M3) is sequentially consistent within its scope (intent → eval log → fill → reject negative label). **Recommend FA invariant 5 amendment** to reflect:
- Sprint N+0 chain order: M1 (intent emit producer) → M2 (entry_context_id INSERT trigger) → M3 (reject negative label) — already follows this dependency order
- Sprint N+1+ chain order: feature_baselines writer first → drift_events emit → scorer_predictions → 3 advisor (mlde_shadow / mlde_demo / cost_edge) parallel

**Push-back to PM**: Either (a) N+0 invariant 5 reword to match actual M1→M2→M3 sequence, or (b) cancel feature_baselines requirement from N+0 to N+1 explicitly.

### 2.3 Producer chain code-path verification

| Producer call site | Source LOC | Target | Status |
|---|---|---|---|
| `emit_decision_feature_intent_emitted` (paper success) | step_4_5_dispatch.rs ~713 | decision_features intent-only | LANDED (E1-E commit `4a90966a`) |
| `emit_decision_feature_intent_emitted` (exchange success) | step_4_5_dispatch.rs ~510 | decision_features intent-only | LANDED |
| `try_emit_evaluation_log` (predictor disabled fallback) | intent_processor/mod.rs | decision_features_evaluations | LANDED |
| `try_emit_evaluation_log` (PredictorAction::Reject) | intent_processor/mod.rs | decision_features_evaluations | LANDED |
| `try_emit_evaluation_log` (RejectAdd / ShadowFill / Fallback / use_legacy) | intent_processor/mod.rs | decision_features_evaluations | LANDED |
| `emit_decision_feature_intent_rejected` (pre_risk demo/live_demo only) | step_4_5_dispatch.rs ~407 | decision_features with negative label | LANDED (E1-FIX-W2) |
| `emit_decision_feature_intent_rejected` (exchange gate.rejected) | step_4_5_dispatch.rs ~678 | decision_features with negative label | LANDED |
| `emit_decision_feature_intent_rejected` (paper gate.rejected) | step_4_5_dispatch.rs ~1081 | decision_features with negative label | LANDED |

**Verdict**: 8 producer call sites land in main. **E1-FIX-W2 fixed E1-C fake-PASS retract** — Rust producer 6 files now actually committed (verified by grep).

---

## 3. P0-MIT-LABEL-CLOSE-TAG-1 + invariant 21 ML View Analysis

### 3.1 attribution_chain_ok formula correctness

Formula (V034 + preserved in V084):
```
attribution_chain_ok = (
    signal_id IS NOT NULL AND signal_id <> ''
    AND context_id IS NOT NULL AND context_id <> ''
    AND signal_context_id IS NOT NULL
    AND signal_context_id = context_id
    AND label_net_edge_bps IS NOT NULL
)
```

**Pre-W-AUDIT-4b state**: 4 conditions all NULL-checked from `signals` table + `decision_features` table; only 4th condition `label_net_edge_bps IS NOT NULL` was the binding constraint — only filled via fill backfill, which had 38% NULL entry_context_id → 99% backfill failures → 0.5% chain_ok.

**Post-W-AUDIT-4b state**:
- M2 (V083 + cron Step 1): close fill entry_context_id ratio improves 38% → 95%+ → backfill EXISTS join hits → label_filled_at populated
- M3 (V084 + Rust producer): governance reject paths write `label_net_edge_bps = 0.0` immediately (label_filled_at_now=true → server-side NOW()) — eliminates the binding bottleneck for reject cohort

**Formula correctness verdict**: PASS — formula unchanged, semantic preserved, downstream view query unchanged.

### 3.2 Mock estimate 0.5% → ~90% reality check (HIGH RISK)

PA dispatch plan suggests post-fix ratio ~90%. **MIT analysis**:

| Cohort | Pre-fix # | Post-fix # | label_net_edge_bps NOT NULL? | signal_id chain present? | Contributes to numerator? |
|---|---|---|---|---|---|
| paper success (path 3 rejects too) | ~50/24h | unchanged | YES (after backfill) | YES | YES |
| exchange success (gate.approved=true) | ~25/24h | unchanged | YES | YES | YES |
| paper reject (path 3) | ~3000/24h | now writes negative label | YES (=0.0 immediate) | **MAYBE** (depends on signal_id propagation) | MAYBE |
| exchange reject (path 2) | ~2000/24h | now writes negative label | YES (=0.0 immediate) | **MAYBE** | MAYBE |
| pre_risk reject (path 1, demo+live_demo only) | ~7500/24h | now writes negative label | YES (=0.0 immediate) | **MAYBE** (inline-built features, may bypass signal_id flow) | MAYBE |

**Critical concern**: in path 1 pre_risk reject, features are inline-built via `build_feature_vector` (E1-FIX-W2 line 124). The intent flow: signal → intent → pre_risk evaluation → reject. The intent should already have signal_id from prior step. **But if pre_risk fires before signal_id is populated** (e.g., intent comes from non-signal source like rebalance / orphan adopt), `signal_id` field in OrderIntent may be empty/NULL → `attribution_chain_ok = false`.

**Mock estimate revision**:
- Best case (all reject paths preserve signal_id): ratio ≈ 99.2%
- Worst case (only paper success + exchange success): ratio = 75 / 12681 = 0.6% (regression to baseline)
- **Realistic case (60-80%)** depends on signal_id propagation through reject paths

**Recommendation**:
- PM should NOT commit to 90% as Sprint N+0 success criterion
- invariant 21 ≥ 5% is achievable target (well above 0.5% baseline)
- After deploy + 24h, if ratio < 60%, fire RCA to map signal_id propagation in 3 reject paths

### 3.3 E4 third-pass observation: runtime 0.286% (engine 跑舊 binary)

Acknowledged. The 0.286% is BEFORE M3 Rust producer deployment. After `restart_all.sh --rebuild --keep-auth`:
- T+0h: 0.286% baseline (24h backward-looking window dominated by pre-fix data)
- T+6h: ratio rises ≈ 25% × proportion of new data + 75% × old data → projected ~15-25%
- T+12h: ~40-60%
- T+24h: steady state ~60-90% (per §3.2 analysis)

**Critical: 24h ratio recovery model assumes**:
1. Engine uptime continuous (no crashes / restarts that purge in-memory state)
2. New reject row volume matches pre-fix reject volume (~12,000+/24h)
3. signal_id chain integrity in reject paths (the unverified hypothesis)

### 3.4 Class weight 1/170 impact on ML model training

| Model | sample_weight handling | Risk with 1/170 |
|---|---|---|
| **LightGBM** (linucb_trainer / scorer_trainer) | `lgb.Dataset(weight=col)` opt-in or `is_unbalance=true` / `scale_pos_weight` | LOW if explicitly subscribed; HIGH if mismatch with `is_unbalance` (double counting) |
| **LinUCB bandit** (linucb_trainer) | NOT directly supported — bandit needs reward distributions | **HIGH** — 1/170 weight collapses signal; reject pool with reward=0 + tiny weight ≈ no information; LinUCB will keep exploring |
| **Thompson sampling** | Bayesian posterior update, not weighted samples | **HIGH** — same issue as LinUCB; 1/170 weight diminishes Beta posterior update from rejects |
| **Quantile regression (quantile_trainer)** | `sklearn.QuantileRegressor(weight=)` | LOW if subscribed |
| **3-DL ensemble** (dl3_foundation) | Keras `class_weight=` or per-sample `sample_weight=` | MEDIUM — Keras supports both but trainer must pick consistent style |
| **Optuna optimizer** | Hyperparameter search over weighted dataset | MEDIUM — Optuna sees weighted CV scores; if base trainer ignores weight, Optuna search degenerates |
| **CPCV validator** | Combinatorial purged CV, not weighted samples | LOW — orthogonal to weight, but if CV folds don't preserve class ratio, weighted score becomes unreliable |

**Push-back to E1**: V084 ships sample_weight column. Sprint N+1 must add per-trainer subscription adapters. Without it, sample_weight is a dead column.

---

## 4. AlphaSurface Phase A Schema Design (W-AUDIT-8a)

### 4.1 4-Tier struct readiness for future ML/Hypothesis Pipeline

| Tier | Components | Phase A IMPL state | W-AUDIT-4 + R-3 (Hypothesis Pipeline N+5) merge cleanliness |
|---|---|---|---|
| **Tier 1 TA** | `Indicators` (1m + 5m) | LANDED (5 strategies declare Ta1m / Ta5m) | CLEAN — already SoT in `feature_collector` 34-dim; no schema migration needed |
| **Tier 2 cross-section** | FundingSkew + Basis + OiDeltaPanel + CrossAsset | STUB (Phase B Sprint N+1) | CLEAN — declared via AlphaSourceTag; Phase B collector will populate; future hypothesis registry reads `declared_alpha_sources()` per strategy |
| **Tier 3 microstructure** | OrderflowImbalance + LiquidationCascade + Sentiment | STUB (Phase C Sprint N+1) | CLEAN — same pattern as Tier 2 |
| **Tier 4 information flow** | EventDriven | STUB (Phase D Sprint N+2) | CLEAN |

**Verdict**: AlphaSourceTag enum + AlphaSurface struct + Strategy::declared_alpha_sources() are well-designed for future merge into:
- W-AUDIT-4 ML 基座 — feature_collector consumes Tier 1 already; Tier 2-4 will need 34-dim → N-dim expansion (each Tier adds dimensions)
- R-3 Hypothesis Pipeline N+5 — Hypothesis state machine can register `AlphaSourceTag` → strategy mapping; clean lookup

### 4.2 Need for new PG schema for alpha source attribution?

**Verdict**: NO new PG schema needed for Sprint N+0 / N+1.

Reasoning:
- AlphaSourceTag is in-memory Rust enum (alpha_surface.rs) — no PG materialization needed for dispatch tracking
- Orchestrator counter HashMap (`alpha_dispatched_counter` / `alpha_unavailable_counter`) is in-memory metric — exposed via prometheus / IPC, not PG
- Future `learning.hypotheses` table (R-3 N+5) will hold AlphaSourceTag as TEXT column — but that's N+5 scope, not N+0

**Sprint N+5 R-3 Hypothesis Pipeline schema preview** (informational, not blocking):
```sql
CREATE TABLE learning.hypotheses (
    hypothesis_id BIGSERIAL PRIMARY KEY,
    alpha_source_tag TEXT NOT NULL,  -- 'ta_1m' | 'funding_skew' | etc, FK-like to AlphaSourceTag
    state TEXT NOT NULL,  -- 'proposed' | 'shadow' | 'paper' | 'demo' | 'live_pending' | 'rejected' | 'retired'
    proposed_at_ms BIGINT NOT NULL,
    decision_lease_id UUID NULL,
    -- ...
);
```

### 4.3 Phase A byte-identical replay E2E

Per E1-A Phase A report §1: "0 行為變化 — 5 策略的 on_tick body 不動，只加 _surface: &AlphaSurface<'_> unused param". E2E byte-identical replay PASS requirement (per spec §3 Phase A Deliverable #7). 

**MIT verdict**: AlphaSurface Phase A is a pure trait expansion + counter wiring. No alpha source actually consumed yet. Byte-identical guaranteed. ✓

---

## 5. Existing ML Training Pipeline Alignment

### 5.1 mlde_edge_training_rows view + decision_features split

**Question**: After V082 split, is `mlde_edge_training_rows` view query correct?

**Verdict**: YES CORRECT.

Verification (V084 line 191): `LEFT JOIN learning.decision_features df ON df.context_id = i.context_id`. Join is on V017 production table (intent-only emit), NOT the new evaluations table. Pool not contaminated by 30k/24h evaluation log rows.

Cross-reference grep: only 7 callers `FROM learning.decision_features` (run_training_pipeline.py / parquet_etl.py / edge_label_backfill.py / V075 view) — none reference `decision_features_evaluations`. Production training pool stays intent-only.

### 5.2 5 ML cron alignment with split schema

| Cron job | Source | Reads decision_features? | Reads decision_features_evaluations? | Alignment after V082 split |
|---|---|---|---|---|
| **thompson_sampling** | ml_training_maintenance.py:48 | Indirect via mlde_shadow_advisor | NO | OK |
| **optuna_optimizer** | ml_training_maintenance.py:49 | Hyperparameter search using underlying trainer scores | NO | OK |
| **cpcv_validator** | ml_training_maintenance.py:50 | Reads training set features | NO | OK |
| **dl3_foundation** | ml_training_maintenance.py:51 | Reads `mlde_edge_training_rows` view | NO | OK (view on production table) |
| **weekly_report_generator** | ml_training_maintenance.py:52 | Reads multiple tables incl. attribution_chain_ok | NO | OK |
| linucb_trainer (legacy) | ml_training_maintenance.py:36 | YES via parquet_etl | NO | OK |
| mlde_shadow_advisor (legacy) | ml_training_maintenance.py:37 | YES via run_training_pipeline | NO | OK |
| mlde_demo_applier (legacy) | ml_training_maintenance.py:38 | YES via run_training_pipeline | NO | OK |
| scorer_trainer (legacy) | ml_training_maintenance.py:39 | YES via parquet_etl | NO | OK |
| quantile_trainer (legacy) | ml_training_maintenance.py:40 | YES via parquet_etl | NO | OK |

**Verdict**: All 10 ML jobs (5 legacy + 5 F-08 new) read production `learning.decision_features` and views thereof. The split is transparent to these jobs. ✓

### 5.3 Cron install pending operator

Per `ml_training_maintenance_cron.sh` line 11: "It does not install itself."

**MIT verdict**: invariant 18 ("F-08 5 ML cron `crontab -e` install + 24h 真 fire") is **operator action** — `[Xc] ml_training_cron_active` healthcheck must PASS. **Not blocking for E1 IMPL closure, blocking for Sprint N+0 sign-off.**

---

## 6. Push-back / Risk Identification (HIGH/MED summary)

### 6.1 V083 NOT VALID CHECK constraint future ALTER VALIDATE lock duration

**Risk level**: MED → HIGH

**Issue**: After M2 7d observation passes, operator may run `ALTER TABLE trading.fills VALIDATE CONSTRAINT chk_fills_close_has_entry_context_id_v083`. With 25k+ historical rows in TimescaleDB hypertable:
- Lock type: ACCESS EXCLUSIVE on each chunk
- Estimate: 30s-3min depending on chunk count + partition skew
- During lock: fill writer batches BLOCK → IPC channel back-pressure → potential producer cascade

**Mitigation recommendations**:
1. Operator runbook: schedule VALIDATE during low-activity window (off-hours UTC)
2. Pre-flight: dry-run on copy table first
3. Add fill_writer back-pressure monitor before VALIDATE
4. Consider: per-chunk `VALIDATE CONSTRAINT` if PG version supports (Postgres ≥ 14.x with TimescaleDB partitioning helpers)

### 6.2 V084 UDF `learning.mlde_sample_weight` vacuum-friendly

**Risk level**: LOW

**Verdict**: PASS. UDF is `IMMUTABLE` + `PARALLEL SAFE` + `LANGUAGE sql` (PG can inline). VACUUM does NOT call UDFs in row visibility check. UDF is index-expression-eligible BUT no current index uses it. UDF stable per stable input. No vacuum interference.

### 6.3 E1-C M3 reject row producer wired (V084 view real populate)

**Risk level**: MED — defer 24h passive watch

**Verdict**: 
- E1-FIX-W2 retract chain: 6 Rust producer files actually committed (verified `grep emit_decision_feature_intent_rejected` = 5 hits)
- DecisionFeatureMsg struct has 3 new fields (label_close_tag / label_net_edge_bps / label_filled_at_now) — verified
- decision_feature_writer.rs INSERT SQL bifurcated (reject vs intent-only paths) — verified

**Pending verification** (operator passive watch 24h post-deploy):
1. `learning.decision_features` 24h SELECT grouped by `label_close_tag`: should show non-zero `'rejected_governance'` count
2. `mlde_edge_training_rows` view 24h SELECT grouped by `label_close_tag`: same
3. `attribution_chain_ok` 24h ratio: should rise from 0.5% to 60-90% (not 90% per §3.2 reality check)

### 6.4 V082 evaluation table retention/hypertable absence

**Risk level**: MED — Sprint N+1 follow-up

V082 evaluations table accumulates ~30k/24h ≈ 1M/month. No retention, no hypertable. Long-term storage problem. Recommend Sprint N+1 V08X add hypertable + 30d retention.

### 6.5 V080 metric_registry / canary_stage_log no FK

**Risk level**: LOW-MED → see §1.1 push-back

Drift between `triggered_metric` value and registry `metric_name` possible. Recommend healthcheck `[58]` add cross-table validation, or Sprint N+1 add FK constraint.

### 6.6 Mac dev RCA blind spot — Linux PG empirical verification deferred

**Risk level**: HIGH

V083 + V084 Linux PG dry-run NOT executed (per E1-B / E1-C reports). CLAUDE.md §七 V055 教訓 explicitly mandates Linux PG dry-run before sign-off. **MUST be executed by E4 / operator on trade-core before Sprint N+0 PM sign-off** (invariant 18 + 22).

---

## 7. Final Verdict

### 7.1 Sprint N+0 MIT verdict

**RETURN-TO-E4 with HIGH/MED issues** (NOT ready for unconditional APPROVE)

| Item | State | Blocker for sign-off? |
|---|---|---|
| V080 governance.canary_stage_log + metric_registry | APPROVE — Linux PG empirical verified | NO |
| V082 decision_features_evaluations split | APPROVE — Linux PG empirical verified | NO |
| V083 fills entry_context_id NOT VALID CHECK | APPROVE WITH `[Linux PG VERIFY]` MUST | **YES — must verify** |
| V084 sample_weight UDF + view | APPROVE WITH `[Linux PG VERIFY]` MUST | **YES — must verify** |
| W-AUDIT-4b producer chain (M1+M2+M3) | APPROVE — code-path 8 call sites verified | NO (subject to V083+V084 verify) |
| AlphaSurface Phase A (W-AUDIT-8a) | APPROVE — 0 behavior change, byte-identical replay design clean | NO |
| invariant 21 P0-MIT-LABEL-CLOSE-TAG-1 acceptance ≥5% | LIKELY ACHIEVABLE (60-90% projected, NOT 90%) | NO (24h passive observation post-deploy required) |
| F-08 5 ML cron install (invariant 18) | NOT EXECUTED — operator action | **YES — must install** |
| FA invariant 5 sequential ordering | RECOMMEND amendment to match actual M1→M2→M3 sequence | NO (FA reword) |
| Sample weight downstream trainer adapter | DEFERRED to Sprint N+1 | NO (acceptable scope cut) |

### 7.2 Required actions before Sprint N+0 PM sign-off

1. **MUST**: E4 / operator execute V083 + V084 Linux PG dry-run × 2 on trade-core (per CLAUDE.md §七 + V055 教訓)
2. **MUST**: operator install `ml_training_maintenance_cron.sh` in crontab + `[Xc]` healthcheck PASS
3. **MUST**: operator deploy via `restart_all.sh --rebuild --keep-auth` to make M3 Rust producer + sample_weight UDF active
4. **SHOULD**: 24h passive observation `attribution_chain_ok` ≥ 5% (invariant 21) post-deploy
5. **SHOULD**: PM amend invariant 5 wording to match actual N+0 chain order (M1→M2→M3) OR cancel feature_baselines from N+0 scope explicitly
6. **MAY**: tighten V084 type CHECK (line 110 + 121) for label_net_edge_bps + label_filled_at after Linux PG verify
7. **MAY**: add Sprint N+1 ticket for V082 evaluation table hypertable + 30d retention
8. **MAY**: add Sprint N+1 ticket for V080 FK or healthcheck cross-validation between canary_stage_log.triggered_metric and metric_registry

### 7.3 Architecture clean assessment

- **Schema clean**: V080+V082+V083+V084 follow CLAUDE.md §七 Guard A/B/C convention; idempotency built-in; engine_mode aware where applicable
- **Producer chain consistent**: 8 producer call sites verified via grep; E1-FIX-W2 retract chain successfully closed E1-C fake-PASS
- **Backward compatibility preserved**: V034 view formula untouched; legacy ML jobs unaffected; AlphaSurface Phase A 0 behavior change
- **Mac RCA blind spot acknowledged**: V083 + V084 Linux PG dry-run gap is real — explicit gate before sign-off

### 7.4 Sprint N+1 carry-forward MIT priorities

1. feature_baselines writer (real daemon, not CLI dry-run) → drift_events emit chain repair
2. Per-trainer sample_weight subscription adapter (LightGBM / LinUCB / Thompson / 3-DL / quantile)
3. V082 evaluations hypertable + retention
4. attribution_chain_ok signal_id propagation RCA in 3 reject paths (if 24h ratio < 60%)
5. AlphaSurface Phase B/C cross-section + microstructure collectors

---

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--sprint_n0_final_review.md
