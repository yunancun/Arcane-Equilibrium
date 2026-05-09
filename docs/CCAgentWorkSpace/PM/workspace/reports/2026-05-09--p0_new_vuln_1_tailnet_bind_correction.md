# P0-NEW-VULN-1 Tailnet Bind Correction

**Date**: 2026-05-09  
**Owner**: PM local implementation  
**Scope**: P0-NEW-VULN-1 / W-AUDIT-2 F-23 follow-up  
**Status**: Source/test closed; runtime API-only reload required to replace any already-running `0.0.0.0:8000` process.

## Decision

Tailscale GUI access must not be implemented by defaulting lifecycle scripts to
`0.0.0.0`. That exposes the Trading API on every host interface, not just the
tailnet.

The corrected model is:

- default `OPENCLAW_BIND_HOST=auto`
- `auto` binds the concrete Tailscale IPv4 (`100.64.0.0/10`) from
  `tailscale ip -4` when available
- otherwise `auto` falls back to `127.0.0.1`
- `OPENCLAW_BIND_HOST=tailscale` forces tailnet-only binding and fails closed if
  Tailscale has no IPv4
- `OPENCLAW_BIND_HOST=0.0.0.0` and `OPENCLAW_BIND_HOST=::` are rejected

This keeps `http://trade-core:8000` reachable over Tailscale while preserving
the P0-NEW-VULN-1 safety property: no default all-interface bind.

## Files Changed

- `helper_scripts/lib/api_bind_host.sh`
- `helper_scripts/restart_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/deploy/README.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py`
- `memory/MEMORY.md`
- `memory/feedback_restart_bind_host_default.md`
- `TODO.md`

## Verification

- `bash -n helper_scripts/lib/api_bind_host.sh helper_scripts/restart_all.sh helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh helper_scripts/deploy/launchd_preflight.sh`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py`
  - 15 passed
- Helper smoke:
  - `OPENCLAW_BIND_HOST=tailscale` resolved local Tailscale IPv4
  - `OPENCLAW_BIND_HOST=0.0.0.0` returned nonzero with an all-interface exposure error
- `git diff --check`

## Boundary

No rebuild, DB migration, live auth mutation, true-live API use, scanner
authority change, strategy/risk config mutation, MAG-083/084 unlock, or order
authority change. Runtime remediation should be API-only restart after sync.
