# Batch A-E Gap Reassessment

Date: 2026-04-29 CEST
Owner: PM
Status: A-E fixed locally, uncommitted, not deployed

## Conclusion

A-E are now green in the working tree for the audited remediation scope. The earlier review mixed one stale status finding with several real gaps:

- Stale: D/E tracking and sign-off are no longer missing; A/B/C/D/E are marked fixed and have sign-off docs.
- Real and fixed: Batch A direct-handler fixture drift, `RC-005`, `RC-006`, `OS-003`, and `OS-006`.

After syncing these local changes and rebuilding the engine, A-E have no known unresolved gap from this reassessment. If the deployment gate is the entire 62-finding program, Batch F is still open and remains outside this A-E sign-off.

## Findings Checked

- Batch A red test: real test fixture drift after Batch B auth hardening. The direct handler test now passes an actor with `operator` role and `live:trade` scope; handler behavior remains 409 for unavailable stop channel.
- `RC-005`: real semantic gap. Reduced/circuit-breaker opposite-side intents could be treated as reducing without capping to current position size. Router now caps reducing qty to existing position before Guardian/risk checks, and demo/live dispatch uses close/reduce-only semantics.
- `RC-006`: real semantic gap. Legacy `update_risk_config` returned JSON-RPC success after queueing, not after application. Handler now waits for event-consumer ack and returns `applied=true` only after apply; send/apply/timeout failures return errors.
- `OS-003`: real ownership gap. Lifecycle scripts no longer rely on broad engine `pkill -f`; they resolve candidate PIDs and validate cwd/command ownership before signaling.
- `OS-006`: real script gap. `mac_bootstrap_db.sh` SQL heredoc is properly closed; shell fragments are no longer written into the generated SQL.

## Verification

- A-E Python targeted suite: 128 passed, 22 existing Pydantic warnings.
- Batch A targeted suite: 69 passed, 11 existing warnings.
- Batch D/E static guards: 18 passed.
- Rust full lib suite: `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml --lib` -> 2355 passed.
- Rust intent processor suite: 86 passed.
- Governor follow-up tests: 4 passed.
- Risk update IPC follow-up tests: 3 passed.
- `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing warnings.
- Local release rebuild: `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing warnings.
- `bash -n` on patched lifecycle/bootstrap scripts -> passed.
- Static scan for broad engine kill/heredoc regressions -> no matches.
- `git diff --check` -> passed.

## Deployment Notes

- No deploy, restart, commit, or push was performed in this reassessment.
- Worktree remains dirty because A-E/F prework remediation changes are local and uncommitted.
- A-E can proceed to sync + deploy/restart from this code state; local release rebuild has been verified. Do not claim the full 62-finding remediation complete until Batch F is implemented and signed off.
