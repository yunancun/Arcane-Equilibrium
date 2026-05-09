# P0-NEW-VULN-1 Launchd Bind Hardening

Date: 2026-05-09
Role: PM
Status: DONE

## Scope

Closed E3 NEW-VULN-1: the Mac launchd Trading API plist still bound uvicorn
to `0.0.0.0`.

Changes:

- `helper_scripts/deploy/com.openclaw.trading-api.plist` now binds `127.0.0.1`.
- `helper_scripts/deploy/launchd_preflight.sh` fail-closes if an installed
  Trading API plist contains `0.0.0.0`.
- `test_batch_e_runtime_ownership.py` now asserts the plist/preflight guard
  cannot regress.
- `TODO.md`, PM memory, and WORKLOG updated.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q`
- `plutil -lint helper_scripts/deploy/com.openclaw.trading-api.plist`
- Static grep confirms deploy plist templates no longer contain `0.0.0.0`.
- `git diff --check`

## Boundary

Source/test only. No launchd load/unload, rebuild, restart, deploy, DB apply,
live auth mutation, scanner authority change, Executor hard authority,
strategy/risk config mutation, MAG-083/084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED.
