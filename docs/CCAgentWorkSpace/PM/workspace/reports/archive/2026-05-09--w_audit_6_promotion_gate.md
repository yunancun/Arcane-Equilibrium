# W-AUDIT-6 F-13 Promotion Gate Checkpoint

Date: 2026-05-09
Scope: source/test only

## Summary

F-13 is source/test closed for the current production promotion pipeline:

- Added `program_code/learning_engine/promotion_gate.py`.
- Composed existing DSR(K) and PBO/CSCV math gates into a single JSON-safe
  `SelectionBiasPromotionGate` result.
- Wired `PromotionGate` Demo→LivePending graduation to require
  `demo_selection_bias_report.passes=true`.
- Missing CV returns, insufficient PBO power, high PBO, DSR block, or DSR
  borderline now prevent promotion instead of remaining advisory-only.
- Preserved `to_db_rows()` / `load_from_db_rows()` status serialization for the
  selection-bias report.

## Boundary

This checkpoint does not claim a full purged-CPCV integration beyond the
existing PBO/CSCV math path. The older `ml_training/cpcv_validator.py` remains a
separate model-validation surface.

No runtime mutation was performed:

- no DB apply
- no rebuild
- no restart
- no live auth change
- no strategy/risk TOML mutation

## Verification

- `python3 -m py_compile program_code/learning_engine/promotion_gate.py program_code/learning_engine/tests/test_promotion_gate.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py`
- `python3 -m pytest program_code/learning_engine/tests/test_promotion_gate.py program_code/learning_engine/tests/test_dsr_gate.py program_code/learning_engine/tests/test_pbo_gate.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py -q`
  - Result: 60 passed in 9.28s
- `git diff --check`
