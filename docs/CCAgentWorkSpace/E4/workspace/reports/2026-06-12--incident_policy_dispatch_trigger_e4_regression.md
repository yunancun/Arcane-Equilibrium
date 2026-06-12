# 2026-06-12 -- P2 Incident Policy Dispatch Trigger E4 Regression

## Verdict

**STATUS: PASS_WITH_CONDITIONS**

`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` passed a source-focused E4 regression / full-chain review for the planned producer set:

- CORE incident ledger / C4 arm path
- `auth_invalid`
- Bybit business-retCode fail-closed
- `sm_halt_stuck`
- `position_drift`
- external watchdog `engine_dead` notify-only producer

Conditions remain:

- This is **not** QA acceptance.
- This is **not** runtime deploy evidence.
- No CI, deploy, service rebuild, service restart, DB mutation, auth mutation, order mutation, risk mutation, or trading action was performed.

## Scope Boundary

The reviewed behavior is source-level wiring and focused regression only. `engine_dead` remains watchdog-side notify-only and does not feed Rust C4 `AllFail`. `position_drift` remains notify-only by incident policy class. `sm_halt_stuck` uses existing halt state and existing incident policy sustained/throttle/cooling semantics.

The initial `live_auth_watcher` Rust filter matched 0 tests and is **not counted** as coverage. It was corrected to the actual bin-test names:

- `auth_invalid_incident`
- `watcher_tears_down_when_auth_invalidates`

On Linux, the first non-interactive SSH Rust command failed before test execution because Cargo was not in PATH. It was rerun with `source ~/.cargo/env`; only the rerun is counted.

## Mac Verification

Rust release focused filters:

| Command | Result |
|---|---:|
| `cargo test --release -p openclaw_engine notification_failsafe::incident_policy --lib` | 15 passed, run twice |
| `cargo test --release -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib` | 4 passed, run twice |
| `cargo test --release -p openclaw_engine sm_halt_incident --lib` | 5 passed, run twice |
| `cargo test --release -p openclaw_engine position_reconciler::incident --lib` | 6 passed, run twice |
| `cargo test --release -p openclaw_engine ret_code_counter --lib` | 6 passed, run twice |
| `cargo test --release -p openclaw_engine auth_invalid_incident` | 2 passed |
| `cargo test --release -p openclaw_engine watcher_tears_down_when_auth_invalidates` | 1 passed |

Rust adjacent filters:

| Command | Result |
|---|---:|
| `cargo test --release -p openclaw_engine notification_failsafe --lib` | 124 passed |
| `cargo test --release -p openclaw_engine position_reconciler --lib` | 94 passed |
| `cargo test --release -p openclaw_engine halt_ttl --lib` | 29 passed |

Python canary/watchdog:

| Command | Result |
|---|---:|
| `python3 -m py_compile helper_scripts/canary/engine_dead_incident.py helper_scripts/canary/engine_watchdog.py helper_scripts/canary/test_canary.py` | passed |
| `python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q` | 5 passed, 82 deselected |
| `python3 -m pytest helper_scripts/canary/test_canary.py -q` | 87 passed, 9 subtests passed |
| `python3 -m pytest helper_scripts/canary/test_watchdog_alert.py -q` | 41 passed |
| `python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -q` | 40 passed |

## Linux Source Verification

Linux `trade-core` was at:

```text
82d02237ddf65140919fb26e67d1e4f0503b7642
```

Rust release focused filters:

| Command | Result |
|---|---:|
| `cargo test --release -p openclaw_engine notification_failsafe::incident_policy --lib` | 15 passed |
| `cargo test --release -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib` | 4 passed |
| `cargo test --release -p openclaw_engine sm_halt_incident --lib` | 5 passed |
| `cargo test --release -p openclaw_engine position_reconciler::incident --lib` | 6 passed |
| `cargo test --release -p openclaw_engine ret_code_counter --lib` | 6 passed |
| `cargo test --release -p openclaw_engine auth_invalid_incident` | 2 passed |
| `cargo test --release -p openclaw_engine watcher_tears_down_when_auth_invalidates` | 1 passed |

Python source check:

| Command | Result |
|---|---:|
| `python3 -m pytest helper_scripts/canary/test_canary.py -k "engine_dead or WatchdogAlertWiring" -q` | 5 passed, 82 deselected |

## Mock / Realism Review

Mocks are limited to IO/time/env/subprocess/alert sinks and in-memory Rust channels/test watchers. They do not bypass the incident-policy class ledger, C4 owner semantics, producer thresholds, or watchdog marker/recovery state.

No cross-language numeric kernel or hot-path latency claim is introduced by this slice. No new full E4 baseline is established; existing E4 baseline records remain unchanged.

## Remaining Work

Next step is QA acceptance over the same source boundary, followed by PM closure. Runtime activation evidence remains separate and requires explicit operator/deploy approval.
