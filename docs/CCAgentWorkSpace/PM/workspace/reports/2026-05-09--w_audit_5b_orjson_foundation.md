# W-AUDIT-5b Orjson Foundation Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint starts the W-AUDIT-5b JSON serialization optimization without
touching byte-contract-sensitive signature/hash paths.

- Added `app/json_fast.py`, an optional `orjson` fast path with stdlib fallback.
- Added `orjson>=3.10.0` to `control_api_v1/requirements.txt`.
- Migrated newline-delimited IPC JSON hot paths in `ai_service_listener.py` and
  `ipc_client_sync.py` to `json_fast`.
- Kept canonical JSON used for signatures, hashes, replay manifests, and Bybit
  request signing on stdlib JSON until each byte contract has explicit tests.

## Verification

- `python3 -m py_compile .../app/json_fast.py .../app/ipc_client_sync.py .../app/ai_service_listener.py`
- `python3 -m pytest .../tests/test_json_fast.py .../tests/test_ipc_client_hmac_ts_unit.py .../tests/test_batch_e_runtime_ownership.py tests/structure/test_json_fast_hot_paths_static.py -q` -> 21 passed
- `git diff --check`

## Boundary

Source/test/docs only. No dependency install, rebuild, restart, deploy, DB
apply, live auth mutation, scanner authority change, Executor hard authority,
strategy/risk config mutation, MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
