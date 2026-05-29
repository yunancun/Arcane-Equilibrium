# A3 GUI Usability / Dead-Button / Fake-Success Audit

Role: A3(default)  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Task shape: read-only GUI usability / dead-button / fake-success audit  
Report date prefix: `2026-05-17--` per operator request  
Actual audit time: 2026-05-29 Europe/Madrid  
Scope: canonical FastAPI OpenClaw Control Console only

## Context Read

FACT: Read startup/context files requested by operator: `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`, `.codex/agents/INDEX.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, `.codex/agents/A3.md`, `.claude/agents/A3.md`, `docs/CCAgentWorkSpace/A3/profile.md`, `docs/CCAgentWorkSpace/A3/memory.md`, latest A3 report, `README.md`, `docs/agents/context-loading.md`, A3 `ux-checklist`, PM baseline, R4 report, and TW report.

FACT: PM baseline says the requested report prefix remains `2026-05-17--` although PM freeze occurred on 2026-05-28/29. Current local/origin HEAD observed during this audit: `b964876415adabcf8c745aec8528553f4823aefe`. Existing unrelated dirty files and other role reports were already present; this A3 task created only this file.

FACT: No browser clicks against live/demo/paper mutating controls were performed. Evidence is static/source inspection.

## Executive Verdict

P0: 0

P1: 4

P2: 4

No P0 found. P1 risk is concentrated in fake-success write paths: the GUI can show success while Rust sync failed, live start can return active after swallowing IPC failure, emergency/close-all can display success on partial close failure, and "safe recheck" actions stamp readiness states instead of proving them.

## Findings

### A3-GUI-001 — Global Mode Switch Reports Success Even If Rust Mode Sync Fails

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html:723`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html:728`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:504`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:520`
- Evidence command / inspection method:
  - `nl -ba .../static/tab-system.html | sed -n '686,739p'`
  - `nl -ba .../app/control_ops.py | sed -n '452,530p'`
- Impact: The System tab can toast "global mode switched" after only Python control-plane state changed. If `sync_ipc_call("set_system_mode", ...)` fails, the exception is swallowed and the API still returns `action_result="success"`. This can display `live_reserved` while Rust remains in the previous mode.
- Why real, not false positive: `control_ops.py:520-523` catches all exceptions and `pass`es; `control_ops.py:525-529` still returns `"success"`. The frontend only checks `result.action_result === "success"` and then shows a success toast.
- Suggested fix direction: Make mode sync fail-closed for runtime-affecting modes, or return explicit `partial_failure/rust_synced=false` and have the GUI render a warning, not success. For `live_reserved`, require a fresh Rust-readback before success.
- Fix owner role: PA(default) for contract decision, E1(worker) for implementation.
- Verification owner role: E2(explorer) + A3(default); E4(worker) for regression if code changes.

### A3-GUI-002 — Live Start Can Return Active After Only Two Gates And Swallowed IPC Resume Failure

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:54`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:149`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:155`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:174`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:195`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:212`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1021`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1034`
- Evidence command / inspection method:
  - `nl -ba .../live_session_endpoints.py | sed -n '40,70p;135,224p'`
  - `nl -ba .../static/tab-live.js | sed -n '1018,1040p'`
  - `rg -n "authorization|OPENCLAW_ALLOW_MAINNET|secret|live_reserved" .../live_session_endpoints.py`
- Impact: Operator sees "Live session started" after the route verifies Operator scope and Python `global_mode == live_reserved`, then grants Python execution authority. The route does not visibly enforce all five live gates from `CLAUDE.md`/`README.md` and treats `resume_paper(engine=live)` failure as non-blocking.
- Why real, not false positive: The route comment and code say the start gate is Operator role + `live_reserved`; `resume_paper` failure is caught at `live_session_endpoints.py:197-198`; the response at `212-224` still reports session active.
- Suggested fix direction: Start must call a single five-gate live preflight: Python mode, Operator role, `OPENCLAW_ALLOW_MAINNET=1`, valid live secret slot, and signed unexpired authorization matching environment. IPC resume must be success/readback verified before `session_state=active`.
- Fix owner role: PA(default) + E1(worker); E3(explorer) for auth/gate review; BB(default) if Bybit/live endpoint semantics are touched.
- Verification owner role: E2(explorer) + E3(explorer) + A3(default).

### A3-GUI-003 — Live Emergency Stop / Close-All Can Show Success On Partial Close Failure

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1082`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1084`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1107`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1108`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js:1112`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:354`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:356`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py:687`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py:700`
- Evidence command / inspection method:
  - `nl -ba .../static/tab-live.js | sed -n '1068,1118p'`
  - `nl -ba .../live_session_endpoints.py | sed -n '267,374p'`
  - `nl -ba .../live_session_account_routes.py | sed -n '646,715p'`
- Impact: A partial live close failure can leave residual live positions/orders while the emergency path always toasts "Emergency Stop executed" for any truthy response. Close-all checks `d.data.close_result.errors`, but backend returns top-level `d.data.errors`, `partial_failure`, and `closed_all`.
- Why real, not false positive: Backend explicitly returns `partial_failure` and `closed_all=false` with HTTP 200; emergency frontend ignores both. Close-all frontend checks the wrong nested field and then displays a green success toast with the backend message, even when that message says partial failure.
- Suggested fix direction: GUI must treat `partial_failure`, `closed_all=false`, `status="partial_failure"`, or any `errors` as red blocking state with residual details. Backend should consider HTTP 409/424 for incomplete live risk-reduction operations, while preserving audit payload.
- Fix owner role: E1(worker) for frontend/backend contract patch; PA(default) for status-code contract.
- Verification owner role: E2(explorer) + A3(default) + BB(default).

### A3-GUI-004 — Safe Recheck / Demo Validate Buttons Stamp Readiness Instead Of Proving It

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:666`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:680`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:164`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:172`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:329`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_ops.py:360`
- Evidence command / inspection method:
  - `nl -ba .../static/tab-settings.html | sed -n '650,685p'`
  - `nl -ba .../app/control_ops.py | sed -n '154,224p;319,397p'`
- Impact: Settings exposes "Validate" and "Safe Recheck Bundle" as if they perform checks. The backend mutator directly sets demo validate state and J/K canonical/closeout states to `"passed"` / `"success"` without invoking an external checker, Rust readback, replay, or runtime proof.
- Why real, not false positive: The inspected functions only mutate `_base.STORE`; there is no subprocess, IPC validation, healthcheck call, or DB evidence query in the code paths shown. GUI toasts "Demo <action> OK" and "Recheck bundle OK" for any truthy response.
- Suggested fix direction: Rename to "manual mark passed" with audit-only semantics, or replace with real check executors and require evidence fields. Do not let these writes satisfy readiness gates unless backed by fresh runtime proof.
- Fix owner role: PA(default) for semantics, E1(worker) for implementation.
- Verification owner role: E2(explorer) + A3(default); QA(worker) if acceptance flow changes.

### A3-GUI-005 — Paper/Demo Stop And Dual-Stop Return Success Envelopes Even With Residual Errors

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html:392`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html:396`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html:398`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:399`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:420`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:428`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:451`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:511`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:531`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_response.py:8`
- Evidence command / inspection method:
  - `nl -ba .../static/tab-paper.html | sed -n '392,403p'`
  - `nl -ba .../paper_trading_routes.py | sed -n '385,542p'`
  - `nl -ba .../paper_trading_response.py | sed -n '1,20p'`
- Impact: Paper/Demo stop paths can report "stopped" while `errors` contains close/pause/verify residuals. This is not real-money live, but it undermines operator trust and Stage 1 demo evidence because the UI can show stop success after residual paper/demo state remains.
- Why real, not false positive: Backend appends residual errors but still calls `_paper_response(...)` with default `action_result="success"`. Frontend only checks `if (d)` and toasts success.
- Suggested fix direction: For stop/stop-all, map non-empty errors or clean=false to `action_result="partial_failure"` and have GUI show red/warn with residual symbols/orders. Consider non-2xx when the operator asked for a stop and verification failed.
- Fix owner role: E1(worker).
- Verification owner role: E2(explorer) + A3(default).

### A3-GUI-006 — Settings Shows A Three-Step Scheduled Restart Flow For An Endpoint That Is Permanently Disabled

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:159`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:161`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:610`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-settings.html:614`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py:89`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py:116`
- Evidence command / inspection method:
  - `rg -n "scheduled|restart|計劃重啟|scheduled-restart" .../static/tab-settings.html .../control_legacy_routes.py`
  - `nl -ba .../control_legacy_routes.py | sed -n '87,122p'`
- Impact: Operator can spend time in a polished modal selecting delay/liquidation choices, but the route always returns HTTP 410. This is a dead operation with hostile UX, especially during maintenance windows.
- Why real, not false positive: The backend route unconditionally raises `HTTPException(status_code=410)` with a disabled endpoint message; the frontend still exposes the active "計劃重啟服務器" button and modal.
- Suggested fix direction: Replace the button with a disabled status card linking to the service-manager/runbook command, or wire a real non-API restart authority if that becomes an explicit product decision.
- Fix owner role: E1(worker) for GUI, PA(default) if restart authority semantics change.
- Verification owner role: A3(default) + E2(explorer).

### A3-GUI-007 — Governance Quick Status Refresh Button Calls Undefined `loadGovernance()`

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html:245`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js:1780`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js:1849`
- Evidence command / inspection method:
  - `rg -n "function loadGovernance|loadGovernance\\s*=|loadGovernance\\(" .../static`
  - Source result: only the onclick call and comments mention `loadGovernance`; actual loader is `loadAll()`.
- Impact: A core governance refresh control is a dead button. The tab still auto-refreshes, but a first-time operator clicking the visible refresh button gets a JavaScript error/no visible update.
- Why real, not false positive: `governance-tab.js` defines `loadAll()` and starts `ocStartRefresh(loadAll, 10000)`; it does not define `loadGovernance`.
- Suggested fix direction: Change the onclick to `loadAll()` or add a stable `window.loadGovernance = loadAll` alias after script load.
- Fix owner role: E1(worker).
- Verification owner role: A3(default).

### A3-GUI-008 — Autonomy Posture Still Exposes Operator-Hostile Governance Jargon

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/autonomy-posture.js:8`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/autonomy-posture.js:35`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/autonomy-posture.js:79`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html:527`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html:536`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html:580`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html:629`
- Evidence command / inspection method:
  - `nl -ba .../static/autonomy-posture.js | sed -n '1,230p'`
  - `rg -n "autonomy|Level 2|Wilson|SM-04|CONSERVATIVE|STANDARD|CONFIRM SWITCH|Escalation" .../static/tab-governance.html .../static/autonomy-posture.js`
- Impact: This does not create fake success, but it is still hostile for a first-time operator. The panel exposes `CONSERVATIVE/STANDARD`, path ids, Wilson CI, LAL/Stage terms, and "三路全 fail -> 1h wait -> SM-04 Defensive" without plain-language consequences.
- Why real, not false positive: A3's 2026-05-27 V099 review already flagged these as Packet B/C UX conditions; current source still renders the same class of jargon and raw gate identifiers.
- Suggested fix direction: Map enum labels to operator language, group the 13/14-path matrix behind collapsible plain-language categories, translate statistical blockers into "not enough successful demo evidence yet", and render escalation as concrete operator consequence/action.
- Fix owner role: PA(default) for copy/semantics, E1(worker) for frontend.
- Verification owner role: A3(default).

## Verification Notes

No runtime, browser mutation, deployment, restart, migration, auth edit, live/demo/paper action, or trading action was performed. This audit used static/source inspection only.

A3 UX AUDIT DONE: fake-success/dead-button readiness grade C · report path: `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-17--gui_usability_dead_button_audit.md`
