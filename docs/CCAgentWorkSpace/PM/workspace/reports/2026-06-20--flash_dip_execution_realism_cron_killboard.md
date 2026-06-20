# FlashDip Execution-Realism Cron/Killboard Arm

Date: 2026-06-20
Owner: PM
Scope: artifact-only FlashDip profitability diagnosis

## Summary

The previous FlashDip touchability scorecard identified K6 as the deepest shallow band with touches. This checkpoint turns the next trigger into durable evidence: K6 execution-realism now has a read-only cron/status surface and an alpha-discovery arm.

The result is sharper but still blocked: K6 daily-exit retune remains negative after intraday execution realism, while the 240m short-exit research signal remains positive under the 1m proxy and still needs L1 candidate-window coverage before any retune design.

## Source Change

- Added `helper_scripts/cron/flash_dip_execution_realism_cron.sh`.
  - Reads PG through `basic_system_services.env`.
  - Sets `PGOPTIONS=-c default_transaction_read_only=on`.
  - Writes dated/latest local artifacts, status JSONL, heartbeat, lock, and cron logs only.
  - Default target: K6/N2/C3/nf0.005, 10bps gate buffer, 30 fills / 20 days.
- Added static contract tests:
  - `helper_scripts/cron/tests/test_flash_dip_execution_realism_cron_static.py`.
- Updated `alpha_discovery_throughput.runtime_runner`:
  - Reads `logs/flash_dip_execution_realism.log`.
  - Adds independent arm `flash_dip_execution_realism`.
  - Nests the same detail under `flash_dip_buy_demo.detail.execution_realism`.
- Updated `alpha_discovery_throughput.discovery_loop`:
  - `EXECUTION_REALISM_BLOCKED` + `SHORT_EXIT_RESEARCH_SIGNAL` becomes a `data_coverage` blocker that points to L1 candidate-window replay.
  - Blocked without a short-exit signal becomes `rejected_no_edge`.

## Runtime Evidence

Execution-realism latest:

- Path: `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_execution_realism_latest.json`
- SHA256: `68c0c5ad486fbf2c71be95eea41c1861472bd7f03411e0da48d3d0e2cf375aa3`
- Generated: `2026-06-20T17:49:51.492343+00:00`
- Candidate: `K6_N2_C3_nf0.005`
- Verdict: `EXECUTION_REALISM_BLOCKED`
- Fail reason: `gate_buffer_nonpositive_annret`
- Gate buffer: `10bps`
- Gate filled sample: `68`
- Gate distinct days: `38`
- Gate annualized return: `-0.02557783616762699`
- Gate max drawdown: `0.008140367127197123`

Short-exit research signal:

- Status: `SHORT_EXIT_RESEARCH_SIGNAL`
- Best horizon: `240m`
- Best buffer: `0bps`
- Filled sample: `72`
- Distinct days: `39`
- Annualized return: `0.01731646147973054`
- Max drawdown: `0.00033040682581697567`

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- SHA256: `225de153dafec013270530b64883c0c6317082a56f66c118c1c55f042bc4bc2c`
- `created_at_utc`: `2026-06-20T17:49:57.097014+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Ready/probe: `0`
- New blocker: `flash_dip_execution_realism`
- New primary blocker: `daily_exit_execution_realism_blocked_short_exit_needs_l1_replay`
- Next trigger: `run_l1_short_exit_replay_with_candidate_window_coverage_before_any_retune`

Linux cron:

- Installed: `29 6 * * * ... flash_dip_execution_realism_cron.sh`
- Existing L1 replay remains: `31 6 * * * ... flash_dip_l1_short_exit_replay_cron.sh`
- Backup: `/tmp/openclaw/cron_backups/crontab_before_flash_dip_execution_realism_20260620T175028Z.txt`

## Interpretation

This narrows the FlashDip failure tree:

- K15 is not touchable in the observed runtime window.
- K6 is touchable enough to test.
- K6 two-day daily-exit retune is not viable under the current execution-realism gate.
- The K6 short-exit hypothesis is still alive under 1m proxy evidence.
- L1 replay cannot yet judge it because candidate maker windows still lack L1 overlap.

The profitable path, if any, is not "retune K6 now"; it is "collect L1-overlapped K6 candidate windows and replay the 240m short-exit path."

## Verification

Mac:

- `helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `24 passed`
- `helper_scripts/cron/tests/test_flash_dip_execution_realism_cron_static.py` + L1 cron static -> `12 passed`
- `py_compile` for alpha runtime/discovery and execution-realism helper -> PASS
- `bash -n helper_scripts/cron/flash_dip_execution_realism_cron.sh` -> PASS
- `git diff --check` -> PASS

Linux:

- Focused alpha-discovery pytest -> `24 passed`
- Cron static tests -> `12 passed`
- `py_compile` -> PASS
- `bash -n` -> PASS
- Targeted `git diff --check` -> PASS
- Runtime wrapper smoke -> PASS
- Alpha-discovery runtime smoke -> PASS

## Boundary

- No PG table write or schema migration.
- No Bybit private/signed/trading call.
- No engine/API rebuild or restart.
- No credential/auth/risk/order/strategy mutation.
- No live/demo retune.
- No promotion proof.
