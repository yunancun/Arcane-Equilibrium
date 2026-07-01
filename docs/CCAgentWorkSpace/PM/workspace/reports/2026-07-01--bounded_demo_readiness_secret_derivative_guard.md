# Bounded Demo Readiness Secret-Derivative Guard

## Scope

Active blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`.

This was a source/test/docs checkpoint only. It addressed the E3 blocker from the fresh standing-envelope runtime-refresh packet review: the readiness helper could not be used in the exact request while it emitted Demo API-key derivatives such as masked values and hash prefixes.

Source drift occurred during the session. PM moved the patch from the clean linked worktree base `eca96d0d1525a0505a39d16325c68243d6496133` onto current `origin/main 631f5ce3b9966c8d3412e199ebdbc975e7e28f31` before committing the source fix as `35ce0fc8f267db827983fd32944fd0fc9b3e66b1`.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/bounded_demo_runtime_readiness.py`
  - adds `--redact-secret-derivatives`;
  - uses stat-only secret presence checks for `api_key` and `api_secret` in redacted mode;
  - requires redacted secret paths to be regular nonempty files, so directories and other non-regular paths fail closed;
  - emits no API-key masked value, length, sha, expected-prefix length/hash, or match derivative in redacted mode;
  - treats expected-key hints under redaction as advisory when strict matching is not required;
  - fails closed when strict expected-key matching is requested under redaction, because the match cannot be observed without reading secret bytes;
  - preserves the existing non-redacted strict expected-key mismatch behavior.
- `helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py`
  - adds redacted no-derivative coverage;
  - adds redacted strict expected-key fail-closed coverage;
  - adds non-regular secret path regression coverage.

## Verification

```bash
python3 -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/bounded_demo_runtime_readiness.py \
  helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research \
  python3 -m pytest -q -p no:cacheprovider \
  helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py \
  helper_scripts/research/tests/test_standing_demo_authorization_refresh_guardrail.py \
  helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py
# 26 passed in 0.12s

git diff --check
```

E2 final review returned `DONE` with no findings. E4 final verification returned `DONE`, reran focused checks, confirmed the no-byte-read smoke for redacted `api_key` / `api_secret`, and reported no blocking test gaps.

## Boundary

No runtime or exchange-facing action occurred. No Control API GET, public quote, standing-envelope materialization, plan inclusion preview, canonical plan write, `_latest`, Decision Lease, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, Cost Gate change, live/mainnet, fill/PnL/proof, runtime action, or consumable approval occurred.

## Status

State transition: `DONE_WITH_CONCERNS`.

The E3 secret-derivative source blocker is closed, but the runtime standing Demo envelope remains expired in the last verified runtime evidence. The next PM step is still `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`: generate a fresh current-head exact E3/BB runtime-refresh request using `--redact-secret-derivatives` for readiness and `--forbid-env-token` for fast-balance capture. The request should not ask for strict expected-key matching under redaction. No runtime action is allowed without fresh exact E3 and BB approval.
