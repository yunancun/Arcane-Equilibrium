# REF-21 V1.3 Consensus Revision PM Report

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** Landed as active governance baseline  
**Primary doc:** `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md`  
**GUI companion:** `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1_1.md`

## Decision

The V1.2 adversarial closure audit is accepted. V1.2 is superseded because it
left five P0 blockers: negative-edge promotion fail-open, missing DDL/dry-run,
subprocess deploy-path ambiguity, write-confinement gaps, and missing
tamper-resistant promotion sign-off.

## V1.3 Corrections

- Promotion now fails closed unless `predicted_edge_bps > 0`,
  `oos_net_bps > 0`, OOS gap <= 30 bps, `PSR(0) >= 0.95`, `DSR > 0`, and
  `PBO <= 0.20`.
- Added V057/V058/V059/V060 DDL sketches and mandatory MIT Linux PG dry-run
  before implementation.
- Added real deploy path: Control API may spawn `replay_runner`; it must not run
  full-chain replay inside uvicorn workers.
- Expanded forbidden writes to `agent.messages`, arbitrary `audit.*`,
  `engine_state.json`, `/tmp/openclaw/*.lock`, and healthcheck sentinels.
- Added promotion FSM, approval signature rows, and SECURITY DEFINER metrics
  calculator.
- Added Bybit SSOT URI mapping, rate/IP interlock, stationary block bootstrap,
  survival/correlation/cost thresholds, baseline SLA, and wave-to-tier mapping.
- GUI V1.1 adds second confirmation, cooldown, 12-tab consistency,
  accessibility/i18n, agent quota UI, and sign-off SOP.

## Status

R2/R3 remain blocked. R1 hardening may continue with the endpoint default-OFF
and no GUI binding.
