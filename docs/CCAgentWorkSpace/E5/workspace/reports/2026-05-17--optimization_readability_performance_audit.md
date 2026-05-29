# E5 Optimization / Readability / Performance Audit

Report date prefix: `2026-05-17` per operator request.  
Actual local audit time: 2026-05-29 Europe/Madrid.  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.  
Role: E5(explorer), read-only optimization/readability/performance audit.

## Scope And Constraints

FACT: This audit is read-only except for creating this report file. I did not fix, refactor, deploy, restart, migrate, edit auth, edit live/demo/paper config, start trading, or mutate runtime.

FACT: Required context was read: `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`, `.codex/agents/INDEX.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, `.codex/agents/E5.md`, `.claude/agents/E5.md`, E5 profile/memory/skill/latest report, PM baseline, R4 report, and TW report.

FACT: Current local source observed during this audit is `b9648764`; PM baseline `2026-05-17--cold_audit_baseline_freeze.md` froze an earlier local HEAD `9bf71423`. Existing worktree changes were present before this report and were not modified.

## Summary

P0: 0. No P0 found.  
P1: 2.  
P2: 4.  
P3: 4.

The highest-priority work is behavior-preserving structural cleanup: split a 2,536-line production FastAPI route file and move a small test module out of a 2,020-line Rust hot-path dispatch file. The main performance risks are GUI async routes calling blocking clients directly, missing DB statement timeouts in closed-PnL helpers, and an 8-D Stage 0R sweep that multiplies row scans and bootstrap work per cell.

## Findings

### E5-OPT-001 - Production FastAPI Route File Exceeds 2000-Line Hard Cap

- Label: FACT
- Severity: P1
- Affected path + line: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:1`
- Evidence command or inspection method:
  - `find rust program_code helper_scripts -type f \( -name '*.rs' -o -name '*.py' -o -name '*.js' -o -name '*.sh' \) ... | xargs -0 wc -l | sort -nr | sed -n '1,80p'`
  - Result: `strategy_ai_routes.py` is `2536` lines, the largest production file found.
  - `rg -n "^@|^async def |^def " .../strategy_ai_routes.py` shows it mixes Telegram status, AI status, demo status/balance/positions/orders, closed-PnL cursor logic, close-position writes, session lifecycle, fills, PnL series, and metrics.
- Impact: Readability and review cost are high, and route-layer ownership is blurred. This violates the repo hard-cap rule and makes future behavior-preserving patches risky because unrelated GUI read models and demo session write paths live in one file.
- Why real, not false positive: The line count is physical source size, not generated output. The file is under `app/` production code, not tests or docs, and the route/function inventory proves multiple responsibilities are co-located.
- Suggested fix direction: Split by existing seams without changing route URLs or payloads: move closed-PnL helpers/routes, demo session lifecycle, and demo read-model helpers into sibling modules that register on the same `phase2_router`. Keep thin route handlers that parse, call, and format.
- Fix owner role: PA(default) for split plan, E1(worker) for behavior-preserving extraction.
- Verification owner role: E2(explorer) for API contract review, E4(worker) for route regression.

### E5-OPT-002 - Tick Dispatch Module Crosses 2000 Lines Because Tests Live In Hot-Path Source File

- Label: FACT
- Severity: P1
- Affected path + line: `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1`
- Evidence command or inspection method:
  - `wc -l rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` via the line-count scan: `2020`.
  - `nl -ba .../step_4_5_dispatch.rs | sed -n '1,120p;1880,2035p'`
  - `rg -n "#\[cfg\(test\)|mod tests" .../step_4_5_dispatch.rs` shows tests start at line `1799`.
  - Lines `5-19` still say the step is "~870 lines" and cannot be split further, which no longer matches the file's physical size.
- Impact: The on-tick dispatch file is an important performance/readability surface. The production body is under the hard cap, but embedded tests push the physical file over 2,000 lines and make hot-path review slower.
- Why real, not false positive: The overage is not a generated artifact. The line count is 2,020, and the `#[cfg(test)] mod tests` block begins at line 1799, so moving tests to a sibling test module would preserve production behavior while returning this file below the hard cap.
- Suggested fix direction: Extract the `#[cfg(test)] mod tests` block into a sibling file such as `step_4_5_dispatch_tests.rs` and keep an include/module declaration. Update the stale module note line count. Do not change dispatch logic.
- Fix owner role: E1(worker).
- Verification owner role: E4(worker) for targeted cargo tests plus E2(explorer) for zero-semantics review.

### E5-OPT-003 - Stage 0R 8-D Sweep Recomputes Expensive Per-Cell Metrics From Raw Rows

- Label: INFERENCE
- Severity: P2
- Affected path + line: `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py:1660`
- Evidence command or inspection method:
  - `nl -ba helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py | sed -n '1148,1290p;1580,1695p'`
  - Lines `1616-1617` document the 8-D sweep as `11664 cells`.
  - Lines `1660-1685` call `compute_stage0r(...)` inside the full grid.
  - Each `compute_stage0r` call scans rows for trigger extraction at lines `1217-1229`, runs two bootstrap CIs at lines `1251-1258` with default `bootstrap_iters=400`, calls `_compute_baseline_lift` at lines `1320-1327`, and `_build_exclusion_counts` at lines `1328-1336`.
  - `_compute_baseline_lift` itself calls `_extract_trigger_rows` twice at lines `1058-1071`; `_build_exclusion_counts` scans rows at lines `998-1029`.
- Impact: A full Stage 0R preflight can spend most time repeatedly scanning the same row set and rerunning bootstrap/PBO work for cells that will fail early. This threatens the replay/preflight workflow with long wall-clock time and poor iteration speed, even though it is offline tooling rather than live trading hot path.
- Why real, not false positive: This is a static multiplicative cost in the code path: full grid cells times multiple full-row passes and 400 bootstrap iterations. The code has no visible memoization or early coarse prefilter cache around row-derived features.
- Suggested fix direction: Preserve metrics and verdict semantics but precompute per-row normalized numeric fields once, cache loose/tight baseline trigger sets per `(horizon, quiet, pct, side_dom)` where valid, and short-circuit expensive bootstrap/PBO after deterministic hard failures when the report only needs RED reasons. Keep an optional exact/full mode if reviewers need every diagnostic for every cell.
- Fix owner role: PA(default) for exact-vs-fast report contract, E1(worker) for implementation.
- Verification owner role: MIT(default) for metric equivalence and E4(worker) for runtime/performance regression.

### E5-OPT-004 - Async GUI Routes Directly Call Blocking Bybit HTTP Client Methods

- Label: FACT
- Severity: P2
- Affected path + line: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:765`
- Evidence command or inspection method:
  - `rg -n "async def|get_executions\(|get_positions\(|get_active_orders\(|refresh_balance\(" .../strategy_ai_routes.py`
  - Direct blocking calls occur inside async routes/helpers at lines `765`, `1068`, `1119`, `1617`, `1764`, `1832`, `1921-1922`, `2243`, and `2494-2497`.
  - `nl -ba .../bybit_rest_client.py | sed -n '1,40p;286,318p;390,444p;720,790p'`
  - `bybit_rest_client.py:6-7` and `:31-32` state the client uses blocking `httpx.Client`; `_get` calls `self._client.get(...)` synchronously at lines `406-415`; `get_executions` calls `_get` at line `739`.
- Impact: GUI polling or slow exchange/API reads can block the uvicorn event loop for that worker. That degrades console responsiveness and can amplify tail latency during exchange slowness.
- Why real, not false positive: The client explicitly uses blocking `httpx.Client`, and several callers are `async def` endpoints. Some closed-PnL paths already use `asyncio.to_thread`, proving the codebase recognizes this pattern; the listed direct calls are the inconsistent cases.
- Suggested fix direction: Wrap blocking Bybit/Rust-reader calls in `asyncio.to_thread` or convert purely blocking route handlers to sync `def` so FastAPI runs them in the threadpool. Preserve response payloads and error handling.
- Fix owner role: E1(worker).
- Verification owner role: E4(worker) for route tests and an event-loop responsiveness smoke; E2(explorer) for error-path parity.

### E5-OPT-005 - Closed-PnL PG Helpers Miss The GUI Statement Timeout Used Elsewhere In The Same Route File

- Label: FACT
- Severity: P2
- Affected path + line: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:1205`
- Evidence command or inspection method:
  - `rg -n "statement_timeout|SET LOCAL|cur\.execute\(" .../strategy_ai_routes.py`
  - `_fetch_strategy_by_order_id` executes a PG query at lines `1205-1210` without setting `statement_timeout`.
  - `_fetch_pg_closed_pnl_fallback` executes at lines `1352-1354` without setting `statement_timeout`.
  - The later demo fills DB route explicitly sets `SET LOCAL statement_timeout` at line `2187`, using `_GUI_READ_STATEMENT_TIMEOUT_MS`.
- Impact: Slow closed-PnL attribution/fallback queries can tie up a DB connection and a threadpool worker longer than the intended GUI-read budget. This does not change trading state, but it harms operator console tail latency.
- Why real, not false positive: The same module already defines `_GUI_READ_STATEMENT_TIMEOUT_MS` and uses it for a similar GUI read query, while the closed-PnL helper queries omit it.
- Suggested fix direction: Apply the same local statement timeout helper before both closed-PnL PG queries, ideally via a tiny shared `_set_gui_read_timeout(cur)` helper to avoid drifting string literals.
- Fix owner role: E1(worker).
- Verification owner role: E4(worker) for route tests; MIT(default) if Linux PG EXPLAIN/timeout behavior needs empirical confirmation.

### E5-OPT-006 - Notification Failsafe Dispatchers Duplicate Vault Path And Fingerprint Helpers

- Label: FACT
- Severity: P3
- Affected path + line: `rust/openclaw_engine/src/notification_failsafe/dispatchers/slack.rs:169`
- Evidence command or inspection method:
  - `rg -n "BybitOpenClaw|secrets|vault|fn sha256_hex|default_secret_path|from_default_path" rust/openclaw_engine/src/notification_failsafe/dispatchers/*.rs`
  - Slack default path construction appears at `slack.rs:169-179`; email repeats the same `$HOME/BybitOpenClaw/secrets/vault` base at `email.rs:368-378`; console banner repeats the vault dir at `console_banner.rs:87-97`.
  - `sha256_hex` is duplicated at `slack.rs:215-220` and `email.rs:422-427`.
- Impact: This is low performance impact but meaningful readability/debt. Future path or fingerprint-policy changes must be synchronized across three files, creating avoidable drift in a security-adjacent surface.
- Why real, not false positive: The grep shows literal duplicate construction in the active notification failsafe module, not test-only code.
- Suggested fix direction: Add a small private dispatchers helper for `default_vault_path(env_override, filename)` and `sha256_hex`. Keep each dispatcher-specific env var and filename unchanged.
- Fix owner role: E1(worker).
- Verification owner role: E2(explorer) for no path/env semantic drift; E4(worker) for existing notification tests.

### E5-OPT-007 - Generic FailsafeWatcher Duplicates Shared Watcher Logic With A Less Robust Claim-Before-Await Pattern

- Label: FACT
- Severity: P3
- Affected path + line: `rust/openclaw_engine/src/notification_failsafe/mod.rs:580`
- Evidence command or inspection method:
  - `rg -n "FailsafeWatcher::new|FailsafeWatcher<|SharedFailsafeWatcher|check_timer\(" rust/openclaw_engine/src`
  - Production references to `FailsafeWatcher` are only the type/impl and tests in `notification_failsafe/mod.rs`; `SharedFailsafeWatcher` is the C3 singleton surface in `providers/single_watcher.rs`.
  - Generic `FailsafeWatcher::check_timer` checks expiration, awaits escalation, then sets `escalated_for_current_arm` at lines `584-598`.
  - `SharedFailsafeWatcher::check_timer` documents and implements claim-before-await at `providers/single_watcher.rs:219-245`.
- Impact: Two watcher implementations now encode the same state machine shape. The generic one is test-only today, but it is public within the module and retains the older after-await flag pattern, so future callers can accidentally use the stale implementation or tests can assert behavior on the wrong surface.
- Why real, not false positive: The code has two concrete implementations and grep shows the generic one is not currently wired outside its own tests. This is therefore readability/API-drift debt, not an active runtime bug claim.
- Suggested fix direction: Mark the generic watcher as test-only if it is only a fixture carrier, or make it delegate to the shared claim-before-await helper so there is one implementation of timer escalation semantics.
- Fix owner role: PA(default) for API ownership decision, E1(worker) for cleanup.
- Verification owner role: E2(explorer).

### E5-OPT-008 - Prelive Edge Trend Query Repeats Lifecycle CTE Logic

- Label: FACT
- Severity: P3
- Affected path + line: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/prelive_edge_gate_trends.py:352`
- Evidence command or inspection method:
  - `nl -ba .../prelive_edge_gate_trends.py | sed -n '340,450p'`
  - `day_sql` defines `entries`, `closes`, `first_close`, and `lifecycles` at lines `352-387`.
  - `current_lifecycle_cte` repeats the same conceptual CTE sequence at lines `401-436`, with only the time window/output changing.
- Impact: Medium-term readability debt. Changes to close matching, fee handling, or grid entry predicate must be synchronized across two embedded SQL strings, increasing drift risk in a gate/trend surface.
- Why real, not false positive: The two SQL fragments are in the same function and repeat the same lifecycle construction. This is not a cross-file style preference; it is duplicated business query logic.
- Suggested fix direction: Extract a pure string builder for the lifecycle CTE that accepts the time predicate/window expression and returns `(sql, params_prefix)`, or keep SQL text duplicated but add a test that asserts both CTEs use the same close predicate and fee/PnL projection.
- Fix owner role: E1(worker) with PA(default) if query contract needs design arbitration.
- Verification owner role: MIT(default) for SQL parity, E4(worker) for route/gate tests.

### E5-OPT-009 - Intent Processor Test File Still Sits Above The 2000-Line Hard Cap

- Label: FACT
- Severity: P3
- Affected path + line: `rust/openclaw_engine/src/intent_processor/tests.rs:2003`
- Evidence command or inspection method:
  - Line-count scan reports `rust/openclaw_engine/src/intent_processor/tests.rs` at `2005` lines.
  - `nl -ba rust/openclaw_engine/src/intent_processor/tests.rs | sed -n '1660,1725p;1980,2025p'`
  - Lines `2003-2005` already note LOC control and include two sibling files, but the parent file remains above the hard cap.
- Impact: Low runtime impact because this is test-only, but it weakens the repository's file-size guardrail and makes intent-processor review slower.
- Why real, not false positive: This is a physical test source file above 2,000 lines, and the file already contains a local note acknowledging LOC control.
- Suggested fix direction: Move the resting-order exposure tests and helpers from roughly lines `1678-2001` into another included sibling test file. Preserve test names and assertions.
- Fix owner role: E1(worker).
- Verification owner role: E4(worker) for intent-processor cargo tests.

### E5-OPT-010 - Demo Route File Contains Several Blocking Reader Calls Not Covered By A Single Helper Boundary

- Label: INFERENCE
- Severity: P3
- Affected path + line: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:452`
- Evidence command or inspection method:
  - `rg -n "get_paper_state\(|get_engine_snapshot\(" .../strategy_ai_routes.py`
  - Direct reader calls appear at lines `452`, `458`, `755`, `779`, `821`, `1054`, `2158`, and `2494-2497`.
- Impact: Even when these calls are local IPC/file reads rather than exchange HTTP, their blocking behavior is scattered across async route code. It makes it hard to enforce a consistent GUI latency budget or reason about event-loop blocking.
- Why real, not false positive: The calls are physically inside the same async route module and are not behind one timing/timeout/offload helper. I am not claiming each call is currently slow; the risk is missing a central boundary.
- Suggested fix direction: Add a behavior-preserving helper such as `await _read_rust_state(...)` or `_read_rust_state_sync(...)` with explicit route-level offload/timing policy, then migrate call sites gradually.
- Fix owner role: PA(default) for boundary choice, E1(worker) for cleanup.
- Verification owner role: E2(explorer) and E4(worker).

## Non-Findings / De-Dup Notes

- I did not re-raise R4/TW documentation inventory findings except where they directly intersected code optimization/readability.
- I did not treat `SELECT *` inside the `first_close` CTE as a standalone finding because it selects from a narrow local CTE and is secondary to the duplicated lifecycle SQL finding.
- I did not treat `ConsoleBannerDispatcher` synchronous metadata/permission calls as P2 because notification failsafe dispatch is rare and not on the tick path; if Packet C becomes a high-frequency status writer, revisit it.

## Suggested Follow-Up Order

1. P1 split `strategy_ai_routes.py` and `step_4_5_dispatch.rs` tests without changing contracts.
2. P2 normalize blocking GUI reads with `asyncio.to_thread` / sync route handlers and add missing statement timeouts.
3. P2 optimize Stage 0R sweep only after PA/MIT define exact-vs-fast report contract.
4. P3 cleanup duplicate notification helper code and test-file size debt opportunistically.

E5 OPTIMIZATION REPORT: report path: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-17--optimization_readability_performance_audit.md`
