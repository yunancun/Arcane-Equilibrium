# Maintenance Warning-Zone Split — 2026-04-30

## Scope

- Operator request: finish TODO items 1-4 and update TODO.
- Local PM shortened chain: `PM -> local implementation/review/verification -> PM`.
- No deploy, rebuild, restart, live authorization, or runtime config change.

## Completed Items

1. `EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT`
   - `tick_pipeline/on_tick/helpers.rs` reduced from 1411 to 336 LOC.
   - Moved PHYS-LOCK / shadow-exit wrapper tests to `helpers/phys_lock_wrapper_tests.rs`.
   - Updated static guard allowlist for the new test sibling path.

2. `TIER4-AI-SERVICE-DISPATCH-SPLIT`
   - `ai_service_dispatch.py` reduced from 868 to 727 LOC.
   - Extracted Guardian L1 handler and parser to `ai_service_guardian.py`.
   - Preserved `AIService._handle_guardian()` and `_parse_guardian_response()` as delegators.

3. `G3-07-FUP-ENV-NAMESPACE`
   - `bybit_public_base_url()` now resolves:
     `OPENCLAW_BYBIT_PUBLIC_BASE_URL` -> legacy `OPENCLAW_BYBIT_ENV` ->
     production `live/bybit_endpoint` file -> safe demo fallback.
   - Added exact URL override and file-based endpoint tests.

4. `T6-FUP-WARN-ZONE-FILES-SPLIT`
   - `checks_derived.py` reduced from 990 to 444 LOC with three sibling modules.
   - `ipc_client.py` reduced from 901 to 749 LOC with sync IPC and risk-config payload siblings.
   - Public import surfaces remain compatible.

## Verification

- `python3 -m py_compile` for all touched Python modules: PASS.
- `python3 -m pytest tests/test_layer2_tools.py -m 'not slow and not e2e' -q`: 38 passed, 1 deselected.
- `python3 -m pytest tests/test_ipc_client_update_risk_config_unit.py tests/test_ipc_client_hmac_ts_unit.py -q`: 9 passed.
- `python3 helper_scripts/db/test_f7_new_healthchecks.py`: 39 passed.
- `python3 -m pytest tests/test_p1_audit_smoke.py -q`: 11 passed.
- `python3 -m pytest tests/test_h_state_query_handler.py -q`: 90 passed.
- Healthcheck re-export smoke: PASS.
- `cargo fmt --check`: PASS.
- `cargo test -p openclaw_engine --lib phys_lock_wrapper_tests -- --nocapture`: 22 passed.
- `git diff --check`: PASS.

## TODO Update

- Marked all four requested TODO rows complete in `TODO.md` with completion date and verification notes.
