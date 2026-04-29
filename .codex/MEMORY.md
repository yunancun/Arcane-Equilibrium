# Codex Memory

Last updated: 2026-04-29

## Role

Codex is used here as:
- secondary engineer
- external reviewer / supervisor
- deploy operator when requested

Current expectation:
- preserve project context in repo files, not hidden chat memory
- operate safely around a dirty worktree
- avoid touching unrelated user changes when syncing or deploying

## Default startup context

Read these first for project state:
- `AGENTS.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`
- `.codex/agents/PM.md`

Default entry role for this repository:
- `PM`

Read on demand for deep history or RCA:
- `OPENCLAW_INVENTORY_CONSOLIDATED.md`

## Current operating model

- Mac is the development machine
- Linux `trade-core` is the active runtime machine
- Future target is Apple Silicon Mac deployment, but current production-like runtime remains Linux

Practical rule:
- Mac-local runtime absence is normal
- real engine / watchdog / rebuild checks must be done through `ssh trade-core`

## Inventory usage policy

- `OPENCLAW_INVENTORY_CONSOLIDATED.md` exists in-repo and is large
- do not load it by default at session start
- use it selectively for deep history, RCA, or old design decisions
- primary control docs remain `CLAUDE.md` and `TODO.md`

## Preferred deploy flow

1. Edit on Mac
2. Commit and push to `origin/main`
3. SSH to `trade-core`
4. Pull on Linux
5. Rebuild / restart on Linux
6. Run watchdog / healthcheck / targeted verification

Typical commands:
- `git push origin main`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull --ff-only'`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild'`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth'`

## Sync policy

- keep Codex durable notes under `.codex/`
- sync them through git like normal source files
- do not mix `.codex` sync commits with unrelated local edits unless explicitly requested
- before deploy, verify local/remote HEAD and working tree state

Current known topology at setup time:
- Mac repo path: `/Users/ncyu/Projects/TradeBot/srv`
- Linux repo path: `/home/ncyu/BybitOpenClaw/srv`
- git remote: `git@github.com:yunancun/BybitOpenClaw.git`
- ssh target alias: `trade-core`

## Documentation policy

- Put durable Codex memory here
- Keep long-form analysis in `reports/`
- Move stale material to `archive/`
- Never store secrets here

## Durable decisions from setup session

- `.codex/` is the Codex-owned repo-synced workspace
- `AGENTS.md` at the git root is the Codex auto-load entry file for this repository
- `CLAUDE.md` stays the project constitution / runtime summary
- `TODO.md` stays the primary execution timeline
- Codex memory should be explicit and file-backed, not assumed to persist across sessions
- Linux deploy actions may be performed from Mac through `ssh trade-core`
- Codex role mirror is deployed in `.codex/agents/`
- Shared skill SSOT remains `.claude/skills/*/SKILL.md`, indexed by `.codex/skills/INDEX.md`
- default project entry role is `PM`
- PM is responsible for initial triage and role dispatch
- dispatch protocol is documented in `.codex/AGENT_DISPATCH_PROTOCOL.md`
- sub-agent role binding and anti-anonymous dispatch rules are documented in `.codex/SUBAGENT_EXECUTION_RULES.md`
- meaningful dispatches should be logged in `.codex/DISPATCH_LEDGER.md`
- temporary runtime nicknames are never the authoritative role identity
- operator needs judgment and pushback; if risk or contradiction is detected, stop and report first

## Notes for future sessions

- `CLAUDE.md` is the high-level constitution and runtime status document
- `TODO.md` is the active timeline and work queue
- The inventory file is useful, but it should be queried selectively rather than loaded in full every time

## 2026-04-29 Batch B Remediation

- 62-finding remediation Batch B is fixed locally, not deployed: `DAPI-001..006`, `RC-003`, `SC-001..007`.
- Sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_b_critical_auth_secrets_api_signoff.md`; operator brief copied to `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_b_critical_auth_secrets_api_signoff.md`.
- Key code paths: shared `auth.require_scope_and_operator`, `secret_runtime.get_secret_value`, Rust `secret_env::var_or_file`, high-risk write route scopes, Grafana loopback/default-secret hardening, `/openclaw` header allowlist.
- Verification baseline: targeted pytest 47 passed; `cargo check -p openclaw_engine` passed with existing warnings; bash/plist/compose/static sweeps passed.
- No deploy/restart was performed. `cargo fmt --all --check` remains blocked by pre-existing repo-wide Rust formatting drift.

## 2026-04-29 Batch C Remediation

- 62-finding remediation Batch C is fixed locally, not deployed: `OE-001..005`, `OE-008`, `OE-009`, `DBW-001..005`.
- Sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_c_trading_record_durability_signoff.md`; operator brief copied to `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_c_trading_record_durability_signoff.md`.
- Key code paths: private WS event parsing, pending dispatch failure terminalization, DB writer retention/requeue, exec-id fill idempotency, stop/close-all partial-failure reporting, risk verdict persistence, migration filtering, DB pool rollback reset.
- Verification baseline: Rust targeted tests 77 passed total; `cargo check -p openclaw_engine` passed with existing warnings; Python py_compile passed; targeted pytest 14 passed.
- No deploy/restart was performed. Batch D remains next: risk/config fail-closed.

## 2026-04-29 Batch E Remediation

- 62-finding remediation Batch E is fixed locally, not deployed: `SW-001`, `SW-003`, `SW-004`, `SW-005`, `SW-006`, `SW-007`, `OS-002`, `OS-003`, `OS-004`, `OS-005`, `OS-006`, `OS-007`, `DAPI-007`.
- Sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_e_operator_runtime_ownership_signoff.md`; operator brief copied to `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_e_operator_runtime_ownership_signoff.md`.
- Key code paths: scheduled restart endpoint disabled (410), maintenance-flag trap lifecycle, DB reset fingerprint confirmation + wrapper explicit confirm, narrowed process-kill scope, launchd preflight gate, least-privilege DB bootstrap role, cron overlap locks, multi-worker leader election for evolution/reconciler/grafana, ExperimentLedger expiry persistence.
- Verification baseline: shell `bash -n` passed for touched scripts; Python `py_compile` passed for touched app/script files; new `test_batch_e_runtime_ownership.py` 10 passed; Batch B+E combined static suite 20 passed.
- No deploy/restart was performed. This note was later superseded by Batch F local completion.

## 2026-04-29 Batch D Remediation

- 62-finding remediation Batch D is fixed locally, not deployed: `RC-002`, `RC-004`, `RC-005`, `RC-006`, `SADF-002`, `SADF-003`, `LP-002`, `OE-006`.
- Sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_d_risk_config_fail_closed_signoff.md`; operator brief copied to `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_d_risk_config_fail_closed_signoff.md`.
- Key code paths: H0 periodic risk snapshot merge preserving cooldown/kill-switch, startup fail-closed on missing demo/live risk config files, router-level governor constraints enforcement, legacy `update_risk_config` event-consumer applied ack + send/apply failure errors, atomic mixed strategy params update, demo/live strategy params fail-closed inactive fallback, `openclaw_engine` package-id checks in clean/fresh restart scripts, close dispatch per-attempt timeout guard.
- Verification baseline: new `test_batch_d_risk_fail_closed.py` 8 passed; Rust targeted tests 9 passed; `cargo check -p openclaw_engine` passed with existing warnings.
- No deploy/restart was performed. This note was later superseded by Batch F local completion.

## 2026-04-29 Batch F Prework

- Batch F F0 prework completed before implementation; superseded by the remediation sign-off below.
- Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_prework.md`.
- Scope: `MLM-001..005`, `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`, `LP-003`.
- F implementation later completed locally with the same dirty-collision preservation constraint.
- Dirty-file collision map for later F work includes `helper_scripts/start_paper_trading.sh`, `helper_scripts/deploy/README.md`, `app/ml_routes.py`, `app/paper_trading_routes.py`, `decision_feature_writer.rs`, `main.rs`, and `step_3_signals.rs`.

## 2026-04-29 Batch A-E Reassessment

- Operator-supplied review was checked against the current worktree. D/E tracking/sign-off missing was stale; Batch A fixture drift, `RC-005`, `RC-006`, `OS-003`, and `OS-006` were real gaps and are now fixed locally.
- Key follow-up code paths: `test_live_gate_fallback.py` fixture actor scopes; `intent_processor/router.rs` reducing qty cap before Guardian/risk checks; `step_4_5_dispatch.rs` reduce-only exchange dispatch; `risk.rs` JSON-RPC apply ack path through event consumer; lifecycle scripts PID/cwd validation; `mac_bootstrap_db.sh` fixed SQL heredoc.
- Verification baseline after reassessment: A-E Python targeted suite 128 passed; Rust full lib suite 2355 passed; `cargo check -p openclaw_engine` passed; `cargo build --release -p openclaw_engine` passed; Batch D+E static guards 18 passed; script `bash -n`, broad-kill/heredoc static scan, and `git diff --check` passed.
- Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md`; operator copy at `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_a_e_gap_reassessment.md`.
- No deploy/restart/commit/push was performed. A-E were green for sync + rebuild at that checkpoint; this note was later superseded by Batch F local completion.

## 2026-04-29 Batch F Remediation

- 62-finding remediation Batch F is fixed and committed/pushed in `bc3fa70`: `MLM-001..005`, `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`, `LP-003`.
- Sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md`; operator brief copied to `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_f_ml_agent_autonomy_signoff.md`.
- Key code paths: feature-definition hash + ONNX metadata validation, ML ETL row-level schema/hash filters, quantile trio registry transition, label full-close finality, LinUCB arm/state loop, Teacher Demo command sink, disabled Paper command rejection, observation-only LinUCB metadata, `boost_arm` unsupported result, Strategist Live fail-fast, Paper opt-in script/runbook.
- Verification baseline: Python py_compile passed; `bash -n helper_scripts/start_paper_trading.sh` passed; `cargo check -p openclaw_engine` passed with existing warnings; ML targeted pytest 78 passed and 7 skipped; Rust targeted tests 47 passed.
- Mac/origin/Linux were initially synced clean at `bc3fa70`; this was later superseded by docs sync `6539e4e` and deploy hotfix `5db4e29`.

## 2026-04-29 A-F Commit/Push Sync

- Commit `bc3fa70` (`fix(audit): close 62-finding remediation batches`) contains the A-F remediation work, reports, and tracking updates.
- Commit `6539e4e` (`docs: record audit remediation sync state`) records the first post-A-F sync state.
- Commit `5db4e29` (`fix(deploy): recognize api uvicorn cwd during restart`) fixes lifecycle PID ownership checks so restart scripts recognize uvicorn master/workers whose command line lacks `control_api_v1` but whose cwd is the API workdir.
- Hotfix verification: `bash -n helper_scripts/restart_all.sh helper_scripts/stop_all.sh helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh`, Batch E runtime ownership pytest 10 passed, and `git diff --check` passed before commit/push.

## 2026-04-29 Linux Rebuild/Redeploy Result

- Linux deploy was completed from Mac through `ssh trade-core` using `PATH="$HOME/.cargo/bin:$PATH" bash helper_scripts/restart_all.sh --rebuild --keep-auth`; the first attempt without cargo in PATH failed before service replacement.
- New runtime after successful redeploy: engine PID `161957` (`openclaw-engine`), API master PID `162029` plus four uvicorn workers. Port `8000` is owned by the new control API venv; the previous address-in-use problem is fixed.
- Runtime checks: watchdog reports `engine_alive=true` and demo snapshot fresh; API direct unauth health endpoints return 401, proving auth enforcement; GUI-origin API requests are returning 200 OK.
- Not full green: `passive_wait_healthcheck.sh --quiet` still fails `[12] bb_breakout_post_deadlock_fix` and `[22] trading_pipeline_silent_gap`, and warns `[27] intents_counter_freeze` plus `[31] edge_diag_2_strategy_diversity`. The earlier startup-transient `[16] strategist_cycle_fresh` cleared after the first 5-minute cycle.
- Live pipeline is intentionally blocked until operator renewal: engine log shows signed authorization schema version mismatch (`got 1, expected 2`), so `/api/v1/live/auth/renew` or renew-review is required. Do not hand-write `authorization.json`.
- Remaining release gaps: live Postgres registry integration run, real ONNX artifact e2e load, LinUCB live boot smoke, and RCA/fix for `[22]` silent-gap / fee-rate cold-boot cost_gate fail-closed before any full-green production sign-off.
