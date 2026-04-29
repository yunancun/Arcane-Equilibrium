# ML/Dream Edge Unblock Completion

Date: 2026-04-29 18:16 CEST
Owner: PM/Codex
Status: Local implementation complete; push pending at report creation.

## What Landed

1. **Learning Data Contract**
   - Added `sql/migrations/V031__ml_dream_edge_unblock.sql`.
   - New `learning.mlde_edge_training_rows` view links `intents -> signals -> decision_features -> decision_context_snapshots`.
   - Primary reward is post-fee `net_bps_after_fee`.
   - Rows expose both canonical `linucb_arm_id` and richer `mlde_arm_id = strategy + symbol_bucket + regime + scanner.route_mode + edge_status`.

2. **LinUCB Unblock**
   - `program_code/ml_training/linucb_trainer.py` now defaults to the V031 view.
   - Trainer filters to valid attribution rows and 8-dim context features.
   - Reward scaling is configurable via `reward_scale_bps`.
   - Scheduler trains the shared LinUCB state once per cycle on `demo_live_demo` to avoid demo/live_demo overwriting the same `learning.linucb_state` rows.

3. **ML Shadow Scorer**
   - Added `program_code/ml_training/mlde_shadow_advisor.py`.
   - Emits advisory `rank` / `veto` recommendations into `learning.mlde_shadow_recommendations`.
   - Recommendations are `applied=false` and `requires_governance=true`.

4. **DreamEngine / OpportunityTracker Read-Only Producers**
   - Added `program_code/local_model_tools/dream_engine.py`.
   - Added `program_code/local_model_tools/opportunity_tracker.py`.
   - Wired `strategist_cognitive.tick_cognitive_modulator()` to load read-only regret/dream inputs fail-soft.
   - `CognitiveModulator` now keeps `last_regret_summary` and `last_dream_summary` for audit/prompt visibility.

5. **Scheduler and Healthchecks**
   - `EdgeEstimatorScheduler` now runs MLDE tasks after label backfill + JS estimates.
   - Added healthchecks:
     - `[35] mlde_learning_data_contract`
     - `[36] mlde_shadow_recommendations`
   - `[36] enforces the live/live_demo advisory boundary: any applied live row must carry `decision_lease_id`.

## Boundary

This does **not** enable live autonomous trading or live parameter mutation.

ML/Dream outputs are advisory/shadow rows. Live/live_demo promotion still requires GovernanceHub approval, Decision Lease, and the existing live gates.

## Verification

- `python3 -m compileall` targeted MLDE/control/healthcheck modules: PASS
- Workspace Python pytest:
  - `program_code/ml_training/tests/test_linucb_trainer.py`
  - `program_code/ml_training/tests/test_mlde_shadow_advisor.py`
  - Result: 21 passed
- Workspace Python pytest:
  - `helper_scripts/db/test_mlde_healthchecks.py`
  - `helper_scripts/db/test_maker_entry_intent_drift.py`
  - Result: 15 passed
- Workspace Python pytest:
  - `test_strategist_cognitive_w1_fix.py`
  - `test_strategist_cognitive_integration.py`
  - `test_g8_01_fup_losses_wiring.py`
  - `test_edge_estimator_scheduler_observability.py`
  - Result: 27 passed
- `git diff --check`: PASS

## Notes

- Canonical Rust LinUCB runtime still loads `v1_15` arms. The richer MLDE arm shape is available now through `mlde_arm_id` and ML shadow recommendations; promoting that into Rust runtime arm selection is a future arm-space migration, not needed to unblock learning data and advisory repair.
- The scheduler uses `OPENCLAW_MLDE_LINUCB_ENGINE_MODE` default `demo_live_demo` and `OPENCLAW_MLDE_LINUCB_REWARD_SCALE_BPS` default `100.0`. ML/Dream producer thresholds are env-tunable.
