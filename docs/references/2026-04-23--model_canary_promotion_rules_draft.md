# Model Canary Promotion Rules — Draft

**Status**: DRAFT — not auto-enforced. Operator-driven transitions only in
Phase 1a/2/3. Auto-promote cron job is a Phase 4 second-half deliverable.

**Scope**: `learning.model_registry` (V023 migration) state-machine
transitions. Applies to the ONNX quantile predictor trio produced by
`run_training_pipeline.py::_run_quantile_pipeline`.

**Owners**: Operator (manual promote) · Phase 4 auto-promote cron (future).

---

## State machine

```
          register                      operator                    operator
    ∅ ─────────────►  shadow  ──────────────► promoting ────────────────► production
                          │                       │                            │
                          │                       │                            │
                          └───── operator ────────┘                            │
                                  │                                            │
                                  ▼                                            │
                              rejected  ◄──────────────── (terminal)           │
                          (terminal)                                           │
                                                                               │
                                                                               ▼
                                                         operator    retired (terminal)
                                                         ─────────►
```

- **shadow** (default) — model registered, not yet approved for any use. ONNX
  artifact on disk + `_current` symlink updated automatically by training
  pipeline. Rust reader ignores shadow rows (only queries production/
  promoting).
- **promoting** — operator has approved for Phase 2 shadow observation via
  `combine_exit_decision`. ML inference runs on each close fill but does not
  influence execution (`ml_override_high=2.0` sentinel ensures no override).
  Data flows into `learning.decision_shadow_exits` for agreement-metric
  collection.
- **production** — operator has approved for Phase 3+ live inference. Rust
  OnnxModelManager loads this artifact on next SIGHUP/restart. `ml_override_
  high` tunable is tightened (Phase 3 plan: 0.95 → 0.85 → 0.75 per
  TODO.md DUAL-TRACK-EXIT-1 §Phase 3).
- **retired** — model superseded by a newer production model. Audit row
  retained for historical replay. `retired_at` + `retirement_reason` set.
- **rejected** — model rejected during shadow/promoting phase (Brier drift,
  feature skew, excessive disagreement, etc.). Never saw production traffic.
  Symmetric terminal to `retired` but carries the "never shipped" signal.

Python state-machine validator: `program_code.ml_training.model_registry.
transition_canary_status`. Rust reader: `openclaw_engine::ml::registry::
resolve_latest_production_artifact`. API route: `POST /api/v1/ml/model_
promote` (Operator gate).

---

## Registration criteria

Row is inserted when all of:

1. `run_training_pipeline.py::_run_quantile_pipeline` completes successfully.
2. `export_quantile_trio_to_onnx` writes the ONNX artifact with
   `verdict != 'no_ship'`.
3. `register_quantile_trio_from_onnx_out` commits the row with initial
   `canary_status = 'shadow'`.

Skipped when:

- DB unavailable (logged; training still succeeds, artifact on disk)
- `verdict = 'no_ship'` (quantile report fails n≥500 or 6 metrics gate)

Re-training the same slot refreshes `artifact_path / artifact_size / sha256 /
acceptance_report / verdict / training_sample_size` via ON CONFLICT DO UPDATE
but **preserves** `canary_status / promoted_at / retired_at` — operator's
transition decisions are sticky across retrains.

---

## Phase-gated promotion criteria

### Phase 2 shadow → promoting (Operator, manual)

Eligibility:

- `verdict = 'should_ship'` or `verdict = 'shadow_only'` (no_ship never
  registered; both are eligible because shadow_only is specifically meant
  to fire in shadow before graduating)
- `training_sample_size >= 200` (hard minimum from quantile_reports.py)
- `feature_schema_hash` matches the running Rust engine's
  `FEATURE_NAMES_V1_HASH` (no schema drift — Rust tract will refuse load
  otherwise per onnx_exporter.py `_META_SCHEMA_HASH` guard)
- Row exists in registry ≥ 1 day (Operator had time to review
  `acceptance_report` JSONB)

Operator action: `POST /api/v1/ml/model_promote { row_id, to_status: 'promoting' }`.

### Phase 2 promoting → production (Operator, manual in Phase 2; cron in Phase 4)

Eligibility (all must hold for ≥ 7 consecutive days of shadow data):

- Row has ≥ 500 observations in `learning.decision_shadow_exits` for the
  same (strategy, engine_mode) — statistical power minimum
- Shadow agreement ratio (Track P pure decision vs Combine-with-mock-ML)
  ≥ 60% — target set in DUAL-TRACK-EXIT-1 §Phase 2 completion standard
- Brier score on shadow predictions does not exceed 1.15 × baseline
  (heuristic: guards against miscalibration regression)
- Feature drift PSI for all 7 Track P dimensions < 0.25 vs training
  distribution (drift_detector.rs ADWIN threshold; Phase 4 will add model-
  specific PSI)

Operator action: `POST /api/v1/ml/model_promote { row_id, to_status: 'production' }`.

Rust reader picks up the new row on next SIGHUP or startup. No auto-reload
yet (Phase 4 auto-promote cron will emit SIGHUP after the UPDATE).

### Any → rejected (Operator, manual; auto-rejection criteria below)

Trigger conditions (any one):

- Shadow agreement < 40% after 3 days (disagrees more often than it agrees)
- Brier score > 1.5 × baseline for 2 consecutive days
- Feature drift PSI ≥ 0.25 on any dim
- Operator override (e.g. post-incident review concludes model is
  untrustworthy regardless of metrics)

Operator action:
```
POST /api/v1/ml/model_promote
{
  "row_id": N,
  "to_status": "rejected",
  "retirement_reason": "<audit-trail text>",
  "confirm": true
}
```

Terminal — no further transitions allowed. Artifact on disk stays for
forensic replay.

### production → retired (Operator, manual)

Trigger: a newer model reaches production for the same slot. Old model
retired same operator-transaction:

1. `POST /model_promote { row_id: OLD, to_status: 'retired', retirement_reason: 'superseded by row_id=NEW', confirm: true }`
2. `POST /model_promote { row_id: NEW, to_status: 'production' }`

Rust reader's "latest production" query returns NEW on next SIGHUP.

---

## Auto-promote cron (Phase 4 deliverable — **not in INFRA-PREBUILD-1**)

Planned workflow:

1. Nightly cron `scripts/auto_promote_canary.py` runs.
2. For each (strategy, engine_mode) with a `promoting` row:
   - Query last 7d of `learning.decision_shadow_exits`
   - Compute: agreement_pct, brier, per-dim PSI
   - If all thresholds met → issue `POST /model_promote` to transition to
     production + fire SIGHUP to engine
   - If any threshold violated severely → issue `POST /model_promote` to
     reject + alert channel
3. Log every decision to `learning.canary_promotion_decisions` (table not
   yet created — design placeholder for Phase 4).

Implementation deferred to Phase 4 second-half per DUAL-TRACK-EXIT-1
§Phase 4 plan. INFRA-PREBUILD-1 ships the state-machine foundation so
Phase 4 cron only has to author the thresholds + cron driver, no schema or
state-machine work needed.

---

## Operator playbook summary

```
# list all shadow models waiting for review
GET /api/v1/ml/model_registry?canary_status=shadow

# list in-flight promoting models
GET /api/v1/ml/model_registry?canary_status=promoting

# resolve which model would load today for this slot
GET /api/v1/ml/model_info?strategy=ma_crossover&engine_mode=demo&quantile=q50

# promote shadow → promoting (after reviewing acceptance_report)
POST /api/v1/ml/model_promote { row_id: N, to_status: "promoting" }

# promote promoting → production (after ≥7d of shadow observations meet gates)
POST /api/v1/ml/model_promote { row_id: N, to_status: "production" }

# reject a shadow/promoting model
POST /api/v1/ml/model_promote {
  row_id: N,
  to_status: "rejected",
  retirement_reason: "Brier drift on demo after 3d",
  confirm: true
}

# retire a prior production model when a new one is ready
POST /api/v1/ml/model_promote {
  row_id: OLD,
  to_status: "retired",
  retirement_reason: "superseded by row_id=NEW",
  confirm: true
}
```

All promote endpoints require Operator role auth (`_require_operator_role`
gate in `governance_routes.py`). Non-Operator callers get 403.

---

## Open questions

- **Threshold calibration**: 60% / 500 observations / 7 days are
  placeholders. Real numbers come from Phase 2 dry-run data when shadow
  first fires on demo.
- **Per-strategy overrides**: ma_crossover may need different thresholds
  than bb_breakout (different tick cadence, different sample rates).
  Phase 4 cron may add `strategy_overrides` YAML.
- **Automated retire on superseded**: when a new production model is
  promoted, should the old one auto-retire in the same transaction?
  Current design keeps them separate for audit clarity. Revisit when
  operators start doing N-per-week promotions and find this tedious.
- **Rollback semantics**: if a production model is found faulty post-
  deployment, what's the flow? Current design: retire + promote a
  prior-known-good model (manual). Phase 4 may add a "rollback" state
  that inverts a retired → production transition without re-training.

---

## References

- `sql/migrations/V023__model_registry.sql` — schema
- `program_code/ml_training/model_registry.py` — Python writer + state machine
- `rust/openclaw_engine/src/ml/registry.rs` — Rust reader (pure-fn resolver)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
  — `/api/v1/ml/*` endpoints
- `docs/worklogs/2026-04-18--dual_track_exit_design.md` — upstream design
- TODO.md INFRA-PREBUILD-1 section
