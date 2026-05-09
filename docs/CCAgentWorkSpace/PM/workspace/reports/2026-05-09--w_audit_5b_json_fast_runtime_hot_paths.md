# W-AUDIT-5b JSON Fast Runtime Hot Paths Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint extends the `json_fast` foundation to runtime hot paths that do
not own signatures, hashes, replay manifests, or canonical persisted bytes.

- Migrated async `app/ipc_client.py` JSON-RPC framing/parsing to
  `app/json_fast.py`, matching the already-migrated sync IPC client and AI
  service listener.
- Migrated local LLM HTTP request/response JSON in `app/ollama_client.py`.
- Migrated LM Studio shim HTTP request/response JSON in
  `app/local_llm_factory.py`.
- Updated the static guard so IPC and local LLM JSON hot paths cannot silently
  drift back to direct stdlib `json` imports.

## Deliberate Non-Scope

The following paths remain on stdlib JSON until they have explicit byte-contract
tests:

- Bybit request signing and HMAC/canonical body generation.
- Proposal IDs, audit hashes, state hashes, and other digest inputs.
- Replay manifests, replay report persistence, and experiment registry
  canonical JSON.

## Verification

- `python3 -m py_compile .../app/ipc_client.py .../app/ollama_client.py .../app/local_llm_factory.py`
- `python3 -m pytest .../tests/test_json_fast.py tests/structure/test_json_fast_hot_paths_static.py -q`
  -> 5 passed
- `python3 -m pytest .../tests/test_governance_lease_bridge.py .../tests/test_ipc_client_update_risk_config_unit.py -q`
  -> 50 passed
- `python3 -m pytest .../tests/test_ollama_integration.py .../tests/test_local_llm_factory.py -q`
  -> 45 passed, 1 pre-existing coroutine warning
- `git diff --check`

## Boundary

Source/test/docs only. No dependency install, rebuild, restart, deploy, DB
apply, live auth mutation, scanner authority change, Executor hard authority,
strategy/risk config mutation, MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
