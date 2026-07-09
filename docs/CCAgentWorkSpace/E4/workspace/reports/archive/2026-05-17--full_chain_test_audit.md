# E4 Full-Chain Test Audit And Executable Matrix

Date prefix: `2026-05-17` per operator request.  
Actual audit time: 2026-05-29 Europe/Madrid.  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.  
Role: E4(worker), read-only audit.

## Scope And Constraints

FACT: This audit is read-only except for this report file. I did not fix, refactor, deploy, restart, migrate, renew auth, edit live/demo/paper config, start trading, or mutate runtime/DB/schema/data.

FACT: I did not run full pytest/cargo suites in this turn. The operator allowed safe local tests, but also allowed creating exactly this report; full pytest/cargo would create or update local artifacts such as caches/target output. I used static inspection plus prior E4 reports as "already run" evidence.

FACT: Current local source at audit start:

```text
git rev-parse HEAD
b964876415adabcf8c745aec8528553f4823aefe

git status --porcelain=v1 -b
## main...origin/main
 M rust/openclaw_engine/src/notification_failsafe/dispatchers/console_banner.rs
 M rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs
?? docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-17--bybit_api_compatibility_audit.md
?? docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-17--root_principle_compliance_audit.md
?? docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-17--security_gate_secret_audit.md
?? docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-17--full_chain_functional_gap_dead_code_audit.md
?? docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md
?? docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md
?? docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md
```

FACT: PM baseline freeze was read at `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`. It reported local HEAD `9bf71423a0c3251ef56393c7b0e137f45f3127ff`, origin/Linux HEAD `b9bb6735698a15072746b014ea0ef80253ccb7e5`, and read-only runtime command boundaries. Current local HEAD is newer, so Linux runtime source evidence must be rechecked before runtime sign-off.

FACT: R4 report read: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`; TW report read: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`.

## Severity Summary

P0: 0.

P1: 2.

P2: 2.

P3: 0.

No P0 findings were found. P1 findings are test/behavior boundary conflicts, not evidence of live orders during this audit.

## Tests Already Run Before This Audit

FACT: Existing E4 reports show recent regression evidence:

| Evidence | Scope | Result |
|---|---|---|
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_gap_bd_e4_regression_round_2.md` | OPS-4 B/D round 2 | Linux control_api_v1 pytest `3994 passed / 68 failed / 51 skipped`; no regression versus round 1. |
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-25--fresh_e4_sprint_2_wave_2_complete_regression.md` | Sprint 2 Wave 2 complete chain | Mac cargo workspace `4300 passed / 1 failed / 6 ignored`; Mac pytest `6221 passed / 7 failed / 45 skipped`; both non-flaky in two runs. |
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-25--w2e4_sprint_2_wave_2_regression.md` | V109 writer + M4 | V109 writer `14/14`, helper M4 pytest `70/70`; cargo workspace `4205 passed / 1 failed / 6 ignored`; pytest `6158 passed / 7 failed / 45 skipped`. |
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1b_pytest_fail_triage.md` | Python failure triage | Two-run baseline `6037 passed / 28 failed / 45 skipped`; failures classified carry-over/static. |

## Tests Run In This Audit

None. Evidence commands were inspection-only: `sed`, `nl`, `rg`, `find`, `git status`, `git rev-parse`, and `test -e`.

## Findings

### E4-FCT-001 — Order Dispatch Tests Lock A Retry Path That Conflicts With Fail-Closed Timeout/retCode Boundary

- Label: FACT + INFERENCE
- Severity: P1
- Affected path + line:
  - `CLAUDE.md:88`
  - `rust/openclaw_engine/src/event_consumer/dispatch.rs:201`
  - `rust/openclaw_engine/src/event_consumer/dispatch.rs:227`
  - `rust/openclaw_engine/src/event_consumer/dispatch.rs:352`
  - `rust/openclaw_engine/src/event_consumer/dispatch.rs:619`
  - `rust/openclaw_engine/src/event_consumer/dispatch_tests.rs:371`
  - `rust/openclaw_engine/src/event_consumer/dispatch_tests.rs:462`
- Evidence command or inspection method:
  - `nl -ba CLAUDE.md | sed -n '78,90p'`
  - `nl -ba rust/openclaw_engine/src/event_consumer/dispatch.rs | sed -n '180,330p;352,430p;610,650p'`
  - `nl -ba rust/openclaw_engine/src/event_consumer/dispatch_tests.rs | sed -n '370,530p'`
- Evidence:
  - Hard boundary says Bybit API timeout or nonzero `retCode` fails closed and hidden retry paths for trading effects must not be added.
  - `classify_dispatch_error()` maps `BybitApiError::Transport` and `JsonParse` to `DispatchOutcome::Transient`.
  - `classify_business_retcode()` maps nonzero retCodes `10006` and `10016..10019` to `Transient`.
  - `run_dispatch_retry()` sleeps and retries transient outcomes.
  - Production order dispatch calls `run_dispatch_retry()` for open and close intents.
  - Tests assert success after transient retries and exhaustion after multiple transient retCodes.
- Impact: A timeout, transport ambiguity, or nonzero Bybit retCode can trigger another trading-effect order dispatch attempt. `order_link_id` idempotency mitigates duplicate order creation, but this is still a retry path on the trading effect surface and conflicts with the stated project boundary.
- Why this is real, not false positive: This is not merely a classifier helper; the production dispatch path calls the retry loop, and the test suite explicitly enshrines retry semantics. The conflict is with the repo hard-boundary text, not with a guessed policy.
- Suggested fix direction: PA should arbitrate whether the hard boundary is absolute or whether a documented exception exists for idempotent dispatch retry. If absolute, E1 should change transport/retCode transient classification to fail-closed for trading-effect dispatch and add tests asserting one attempt only for timeout, transport, parse, rate-limit, and server error retCodes. If an exception is retained, update CLAUDE/ADR wording and add explicit idempotency proof tests against Bybit orderLinkId semantics.
- Fix owner role: PA(default) for policy arbitration, then E1(worker) for implementation.
- Verification owner role: E2(explorer) for adversarial review, E4(worker) for dispatch retry regression, BB(default) for Bybit orderLinkId compatibility.

### E4-FCT-002 — Active Promotion Pipeline Still Allows Paper-Based Demo Promotion Despite Paper Lane Freeze

- Label: FACT
- Severity: P1
- Affected path + line:
  - `CLAUDE.md:96`
  - `README.md:28`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py:1`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py:100`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py:518`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_promotion_routes.py:191`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_promotion_routes.py:236`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py:125`
- Evidence command or inspection method:
  - `nl -ba CLAUDE.md | sed -n '90,102p'`
  - `nl -ba README.md | sed -n '24,38p'`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py | sed -n '1,150p;500,570p'`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_promotion_routes.py | sed -n '191,260p'`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py | sed -n '100,180p'`
- Evidence:
  - CLAUDE says paper is not an active promotion evidence lane and Stage 1 alpha-bearing promotion is Demo-only after green Stage 0R replay preflight.
  - README labels the paper tab as archive status and says it is not a promotion lane.
  - `PromotionStage` still defines `PAPER_SHADOW`, and `promote()` allows `PAPER_SHADOW -> DEMO_ACTIVE` if paper gates pass.
  - The active governance route exposes `/promotion-pipeline/promote` with `target_stage: PAPER_SHADOW | DEMO_ACTIVE | LIVE_PENDING | LIVE_ACTIVE`.
  - Existing tests assert a full happy path from paper metrics into `DEMO_ACTIVE`.
- Impact: An Operator-only route can still use paper metrics as the formal gate into demo activation. That contradicts the current promotion boundary and can confuse Sprint 2 Stage 0R/Demo-only evidence discipline.
- Why this is real, not false positive: The route is imported into active governance routes, not an archived helper, and tests currently assert the obsolete path as success.
- Suggested fix direction: Freeze or deprecate `PAPER_SHADOW -> DEMO_ACTIVE` in active routes. Add a Stage 0R/Demo-only promotion gate or block this endpoint with a reason such as `paper_promotion_lane_frozen`. Keep legacy paper data read-only for diagnostics. Update tests to assert paper cannot promote to demo unless a future operator decision explicitly reopens that lane.
- Fix owner role: PA(default) for promotion semantics, E1(worker) for route/gate patch.
- Verification owner role: E4(worker) for route/unit regression, QA(worker) for promotion acceptance.

### E4-FCT-003 — Full-Chain Run Tests Are Strong Locally But Do Not Prove Linux PG/Subprocess Runtime Chain

- Label: FACT + INFERENCE
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1661`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1719`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1808`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py:235`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py:262`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py:271`
- Evidence command or inspection method:
  - `rg -n "replay_full_chain|full-chain|full_chain" program_code/exchange_connectors/bybit_connector/control_api_v1/tests tests rust/openclaw_engine/tests`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py | sed -n '1661,1930p'`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py | sed -n '235,315p'`
- Evidence:
  - The route performs real register and run work through `_er.run_register_in_pg_xact` and `_rrun._do_pg_path_for_run_sync`.
  - The happy-path test replaces both with `fake_register` and `fake_run`, then asserts route envelope behavior.
  - This is appropriate for local unit tests, but it does not prove the Linux PG transaction, run_state registration, artifact allowlist, or replay_runner subprocess path on current runtime.
- Impact: The test matrix can pass while runtime full-chain execution is broken by PG schema drift, binary/source drift, or replay_runner runtime configuration. TODO already tracks replay manifest healthcheck `[48]` as requiring runtime wiring/evidence.
- Why this is real, not false positive: The monkeypatches are visible in the test and replace the two highest-risk runtime dependencies. This is a coverage gap, not a criticism of the local route tests.
- Suggested fix direction: Keep the mocked local tests, but add a separate Linux read-only evidence gate for full-chain readiness: verify current Linux HEAD, replay_runner binary existence/hash, recent `replay.experiments`/`replay.runs` rows, cron healthcheck `[48]`, and artifact output dirs by SELECT/stat only. Do not call `/full-chain/run` during read-only audit because it registers runs and can spawn subprocesses.
- Fix owner role: E1(worker) or MIT(default) for runtime evidence script, PM(default) for gate placement.
- Verification owner role: E4(worker) for matrix execution, QA(worker) for acceptance.

### E4-FCT-004 — Missing Concurrent Duplicate Full-Chain Run Test For Same Actor/Payload

- Label: INFERENCE
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1661`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1719`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1833`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py:1868`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py:235`
- Evidence command or inspection method:
  - `rg -n "concurrent|ThreadPool|asyncio.gather|full-chain/run|idempotency" program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py`
  - `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py | sed -n '1661,1880p'`
- Evidence:
  - `_register_full_chain_experiment()` and `_start_full_chain_run()` build deterministic idempotency keys from actor/strategy/manifest and actor/experiment/strategy.
  - `post_replay_full_chain_run()` registers strategies and then starts runs in sequential loops.
  - Existing tests cover normal multi-strategy behavior, caps, coverage verdicts, and several abnormal cases, but I found no test that sends two identical `/full-chain/run` calls concurrently and asserts one logical experiment/run set, no duplicate subprocess launch, and stable idempotency responses.
- Impact: Duplicate user clicks, browser retries, or two API workers can race the register/run chain. If PG idempotency or active caps are imperfect, this can spawn duplicate replay_runner work or confusing duplicate records.
- Why this is real, not false positive: The code is multi-step and side-effecting; the test suite has concurrency tests in other modules, but not for this route. The route's deterministic idempotency key is exactly the surface that should be stress-tested.
- Suggested fix direction: Add a pure local concurrency test with mocked PG/run helpers that synchronize on a barrier and simulate idempotency-hit behavior. Follow with Linux read-only evidence after a governed real run: no duplicate active runs for the same manifest hash/actor/strategy in the same window.
- Fix owner role: E1(worker) for tests.
- Verification owner role: E4(worker).

## Existing Coverage Map

| Domain | Normal | Boundary | Abnormal / fail-closed | Concurrency | Regression |
|---|---|---|---|---|---|
| Bybit REST client timeout/retCode | `test_checked_methods_propagate_no_credentials` | timeout configured | `test_into_result_non_zero_retcode_fails_closed`; hung server timeout test | Env tests use `LIVE_GUARD_ENV_LOCK` | Prior cargo reports. Gap: dispatch wrapper retries transient timeout/retCode. |
| Dispatch order effects | Open/close retry tests exist | Close retry budget cap | Structural errors break without retry | Not enough for exchange ambiguity | P1 conflict: tests lock retry behavior. |
| Auth expiry / live gates | Valid auth watcher respawn | stale v1 / wrong mode | missing/expired auth returns 403; mainnet env gate | Back-to-back route calls; Rust watcher trigger tests | Good local coverage; Linux auth state requires read-only evidence only. |
| Stale data | Dust stale price skip; stale heartbeat route tests | zero/NaN floors | stale price preserves position | limited | Good targeted Rust/Python coverage. |
| Replay full-chain | Mocked route happy path | strategy cap, event/window limits, prod-IP guard | coverage warnings and prepare rejection tests | missing duplicate concurrent run test | Needs Linux read-only evidence for PG/subprocess runtime. |
| Promotion boundary | Legacy happy path tests | no stage skip | operator approval needed for live | concurrent same-stage promotion test | P1 conflict: paper->demo path still active; no Stage 0R/Demo-only freeze test. |

## Executable Test Matrix

Run from `/Users/ncyu/Projects/TradeBot/srv` unless noted.

| ID | Status | Class | Command | Expected | Notes |
|---|---|---|---|---|---|
| M1 | Already run, not this turn | Regression | `cd rust && cargo test --workspace --release --no-fail-fast` | Latest prior E4: `4300 passed / 1 failed / 6 ignored` | Local cache/build writes; not run in this report-only audit. |
| M2 | Already run, not this turn | Regression | `python3 -m pytest -q --tb=no --ignore=venvs --ignore=tests/misc_tools/test_pure_utils.py --ignore=tests/ml_training/test_pure_utils.py` | Latest prior E4: `6221 passed / 7 failed / 45 skipped` | Not run in this report-only audit. |
| M3 | Not run | Fail-closed Bybit | `cd rust && cargo test --release -p openclaw_engine --lib bybit_rest_client_tests -- --nocapture` | Nonzero retCode and hung server tests pass | Safe local but writes cargo output. |
| M4 | Not run | Dispatch boundary | `cd rust && cargo test --release -p openclaw_engine --lib event_consumer::dispatch_tests -- --nocapture` | Current expected pass, but exposes P1 retry conflict | After fix, add one-attempt timeout/nonzero-retCode assertions. |
| M5 | Not run | Auth expiry | `cd program_code/exchange_connectors/bybit_connector/control_api_v1 && python3 -m pytest tests/test_executor_shadow_toggle_api.py -q --tb=short` | Missing/expired/stale/wrong-mode auth 403 | Tempfile-only local test. |
| M6 | Not run | Rust auth watcher | `cd rust && cargo test --release -p openclaw_engine --lib live_auth_watcher_tests -- --nocapture` | watcher respawn/teardown/backoff pass | Local tempfile/env-guard tests. |
| M7 | Not run | Replay full-chain local | `cd program_code/exchange_connectors/bybit_connector/control_api_v1 && python3 -m pytest tests/test_replay_full_chain_routes.py tests/test_replay_full_chain_run_routes.py tests/test_replay_prepare_policy.py -q --tb=short` | Mocked local route tests pass | Does not prove Linux PG/subprocess. |
| M8 | Not run | Promotion boundary | `cd program_code/exchange_connectors/bybit_connector/control_api_v1 && python3 -m pytest tests/test_promotion_pipeline.py -q --tb=short` | Current expected pass, but P1 because paper->demo happy path passes | After fix, update expected result. |
| M9 | Not run | Stale data | `cd rust && cargo test --release -p openclaw_engine --lib paper_state::tests::evict_on_dust_failclosed_stale_price_skips_symbol -- --nocapture` | stale price preserves position | Narrow safe unit. |
| M10 | Not run | Concurrency | Add test first, then run targeted full-chain concurrency test | identical concurrent payload does not duplicate logical run | Missing today. |
| M11 | Cannot run in read-only audit | Runtime full-chain side effect | `POST /api/v1/replay/full-chain/run` | Would register PG rows and spawn replay_runner | Forbidden for this audit. |
| M12 | Requires Linux read-only evidence | Runtime replay readiness | `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && test -x rust/target/release/replay_runner && psql ... SELECT ... FROM replay.experiments/replay.runs ...'` | HEAD/hash/source aligned; recent rows/healthcheck status known | SELECT/stat only; no `/run` call. |
| M13 | Requires Linux read-only evidence | Auth/runtime gates | `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && systemctl --user is-active openclaw-watchdog.service && test -f .../authorization.json; echo AUTH_PRESENT=$?'` | Report presence/absence only | Do not edit or renew auth. |
| M14 | Requires Linux read-only evidence | Bybit runtime fail-closed | `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && rg -n "OPENCLAW_ALLOW_MAINNET|authorization_json_missing|retCode|timeout" /tmp/openclaw/logs -g "*.log" | tail -50'` | log evidence only | Use grep/tail only; do not trigger calls. |

## Linux Trade-Core Read-Only Evidence Needed

These cannot be replaced by Mac tests:

1. Source/runtime alignment: Linux `HEAD`, branch, dirty status, and replay_runner/openclaw-engine binary hashes.
2. Replay health: SELECT-only counts/ages for `replay.experiments`, `replay.runs`, manifest registry healthcheck `[48]`, and M11 cron output.
3. Auth/runtime gate reality: `authorization.json` presence/expiry status by read-only stat/parse only; do not renew.
4. Bybit-facing logs: timeout/retCode handling must be inspected from logs, not provoked by new live/demo orders.
5. Full-chain concurrency proof after a governed run: duplicate manifest/run rows by actor/strategy/window.

## Verdict

E4 FULL-CHAIN TEST AUDIT DONE: FAIL for boundary alignment because two P1 issues need PA/E1 action before this can be called a clean full-chain test surface.

No P0 found. P1 count: 2.
