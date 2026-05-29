# 2026-05-17 Security Gate / Secret Audit

Role: E3 (explorer)
Scope: read-only audit focused on gate bypass, injection, secret leakage, auth downgrade, dangerous defaults, live/live_demo auth, Decision Lease, risk gates, API auth, and logs.
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Runtime: `trade-core` read-only inspection only

## Baseline

- Local HEAD: `5097bd0670277e24516460f6914a85acf9969d87`
- Runtime HEAD: `5097bd0670277e24516460f6914a85acf9969d87`
- Local branch state: `main...origin/main`
- Runtime branch state: `main...origin/main`
- Dirty local state observed before this report: pre-existing modified `docs/CCAgentWorkSpace/MIT/memory.md` plus pre-existing untracked PM/R4/TW reports. This audit did not edit those files.

## Executive Result

- P0 findings: 0
- P1 findings: 1
- P2 findings: 1
- P3 findings: 0

No P0 was found. One P1 remains because one Python live-write verifier still authenticates `authorization.json` with the IPC secret domain instead of the live authorization signing-key domain introduced by OPS-2.

## Finding E3-SG-001: Python Live-Write Gate Verifies `authorization.json` With IPC Secret Domain

Severity: P1
Status: FACT

Affected paths and lines:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py:180`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py:290`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py:366`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py:393`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_promote_routes.py:451`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_promote_routes.py:463`
- Related contrasting implementation: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:58`
- Related contrasting implementation: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:253`
- Related contrasting implementation: `rust/openclaw_engine/src/live_authorization.rs:381`
- Related test gap: `tests/test_executor_shadow_toggle_api.py:547`
- Related positive split test: `tests/test_live_trust_routes_secret_split.py:156`

Evidence command / inspection method:

- `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py | sed -n '180,430p'`
- `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_promote_routes.py | sed -n '430,470p'`
- `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py | sed -n '58,94p;253,320p;444,570p;977,1100p'`
- `nl -ba rust/openclaw_engine/src/live_authorization.rs | sed -n '381,430p;720,800p'`
- `nl -ba tests/test_executor_shadow_toggle_api.py | sed -n '160,210p;540,580p'`
- `nl -ba tests/test_live_trust_routes_secret_split.py | sed -n '150,185p'`
- `rg -n "OPENCLAW_LIVE_AUTH_SIGNING_KEY|OPENCLAW_IPC_SECRET|authorization.json|_verify_live_gate|_verify_authorization_json_or_raise" program_code rust tests`

Impact:

`executor_routes._verify_authorization_json_or_raise()` validates the signed live authorization file using `OPENCLAW_IPC_SECRET`. OPS-2 split introduced `OPENCLAW_LIVE_AUTH_SIGNING_KEY` as the signing domain for live authorization. The Rust engine verifier and the GUI live-trust signer/status verifier now use the live-auth signing-key domain, with a temporary IPC fallback only when the new secret is absent. This executor verifier is therefore split-brain:

- A valid authorization signed with the primary live-auth key can be rejected by Python live-write surfaces when the IPC and live-auth keys differ.
- An authorization signed with the IPC key can satisfy this Python live-write gate if the other route preconditions hold.
- The issue affects `POST /api/v1/executor/shadow-toggle` live unshadow and strategist live apply paths that reuse `_verify_live_gate()`.
- The issue undermines OPS-2 Phase 1 and will become more brittle when the planned Phase 2 fallback removal occurs.

Why this is real, not a false positive:

- `live_trust_routes._write_signed_live_authorization()` signs `authorization.json` with `_read_live_auth_signing_key()`.
- `rust/openclaw_engine::read_live_auth_signing_key()` verifies the same artifact with `OPENCLAW_LIVE_AUTH_SIGNING_KEY` first, falling back to IPC only during Phase 1.
- `executor_routes._verify_authorization_json_or_raise()` computes the expected HMAC with `get_secret_value("OPENCLAW_IPC_SECRET")` instead of the live-auth signing-key helper/domain.
- Existing executor tests set only `OPENCLAW_IPC_SECRET`, so they cannot catch a primary-key split where `OPENCLAW_LIVE_AUTH_SIGNING_KEY != OPENCLAW_IPC_SECRET`.
- Existing live-trust tests prove the intended primary-key behavior when the two secrets differ, but that coverage does not exercise executor live-write verification.

Suggested fix direction:

- Centralize signed live authorization verification in one helper shared by Rust-facing status/trust routes and Python live-write routes, or make executor reuse the same live-auth signing-key lookup semantics as `live_trust_routes._read_live_auth_signing_key()`.
- Add negative and positive tests where `OPENCLAW_LIVE_AUTH_SIGNING_KEY` and `OPENCLAW_IPC_SECRET` are both present and different:
  - auth signed with the live-auth signing key passes executor live gate;
  - auth signed with IPC secret fails executor live gate.
- Add a regression check for strategist live apply because it imports/reuses the executor live gate.
- Keep the temporary fallback behavior aligned with the OPS-2 Phase 2 removal plan; do not extend IPC fallback beyond that plan.

Fix owner role:

- E1 with CC review, because this is control/API code plus shared live-auth domain behavior.

Verification owner role:

- E3 for security regression.
- E2/E4 for live-gate and engine/API integration checks.
- BB only if the fix changes Bybit REST/WS exchange behavior; the observed issue is local authorization-domain logic.

## Finding E3-SG-002: Live Session Authority Endpoints Can Persist `granted` Without Full Current Live Gate

Severity: P2
Status: FACT / INFERENCE

Affected paths and lines:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:135`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:174`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:212`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:407`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:423`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:432`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:466`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:480`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py:87`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py:342`

Evidence command / inspection method:

- `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py | sed -n '120,230p;400,500p'`
- `nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py | sed -n '80,130p;330,395p'`
- `rg -n "execution_authority|live_reserved|authorization.json|OPENCLAW_ALLOW_MAINNET|secret_slot|_set_execution_authority|session/start|session/resume|execution-authority/grant" program_code/exchange_connectors/bybit_connector/control_api_v1/app`
- Cross-check against project boundary note in `CLAUDE.md` that Rust-side `execution_authority` is not the hard live authorization mechanism.

Impact:

The live session endpoints can set and persist `execution_authority = "granted"` without verifying the full current live-gate bundle used by executor live-write paths. `session/start` requires operator/live-trade authority and exact `global_mode == "live_reserved"`, but does not verify `OPENCLAW_ALLOW_MAINNET`, secret slot, or signed `authorization.json`. `session/resume` is weaker and accepts any `global_mode` containing the substring `live`, rather than exact `live_reserved`. `execution-authority/grant` sets the state after `_require_live_authority(actor)` and does not perform exact live-reserved or signed authorization checks.

Today this appears to be a control-plane/state and UI-risk issue rather than a direct order-bypass issue because the project boundary documents Rust signed authorization as the hard live trading guard, not the `execution_authority` string. The risk is still real: these endpoints can create a persisted "granted" state that does not represent the same live-gate posture as executor/Rust authorization, and future consumers may incorrectly treat that state as authoritative.

Why this is real, not a false positive:

- The inspected code path directly calls `core._set_execution_authority("granted")` in the affected handlers.
- The same inspected handlers do not call the signed authorization verifier used by executor live-write gates.
- `session/resume` explicitly uses substring membership for live-mode acceptance.
- The finding is intentionally rated P2, not P1/P0, because current project docs say the hard trading authorization is Rust signed-authorization verification, and this audit did not find evidence that this string alone can bypass the engine live gate.

Suggested fix direction:

- Reuse a centralized full live-gate helper before any endpoint persists `execution_authority = "granted"`, or rename/limit this state so it cannot be mistaken for hard live authorization.
- Change `session/resume` to exact `global_mode == "live_reserved"` if it is intended to represent the same live boundary as `session/start`.
- Add regression tests proving start/resume/grant cannot mark authority granted when the signed authorization file is absent, invalid, expired, or signed with the wrong domain, unless the endpoint is deliberately downgraded to advisory-only state.

Fix owner role:

- PA with E1, because the fix needs product/architecture clarity on whether live session authority is advisory or an enforcement boundary.

Verification owner role:

- E3 for security semantics.
- E2/E4 for live-session and engine/API integration behavior.

## Non-Finding Evidence

### Secret File Existence / Mode Checks

Status: FACT

Evidence command / inspection method:

- `ssh trade-core 'stat -c "%n %a %U:%G %s %y" ...'`

Inspected only existence, permissions, ownership, size, and modification time. No secret contents were read or printed.

Observed:

- Runtime IPC secret file exists with mode `600`.
- Runtime live-auth signing-key file exists with mode `600`.
- Runtime live Bybit credential files exist with mode `600`.
- Runtime `authorization.json` exists with mode `600`.

### OPS-2 Fallback Runtime Log Count

Status: FACT

Evidence command / inspection method:

- `ssh trade-core 'grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/engine.log /tmp/openclaw/api.log'`

Observed:

- `engine.log`: `0`
- `api.log`: `0`

This supports the current PM/TODO note that the Phase 1 fallback is not being exercised in runtime logs so far. It does not remove the Phase 2 cutover requirement.

### Tracked Source Secret Scan

Status: FACT / INFERENCE

Evidence command / inspection method:

- Redacted `rg`/scripted scan over tracked source paths for token-like values and sensitive variable names.

Observed:

- No confirmed tracked-source secret leak was established during this read-only audit.
- Candidate hits were documentation examples, placeholders, hashes, test fixtures, or build/env variable names after redacted path/line review.
- Because this audit did not read or print live secret values, it cannot prove absence of every possible secret leak. It only records that no confirmed tracked-source leak was found by the redacted inspection.

### Existing Known OPS-2 Items

Status: FACT

Evidence command / inspection method:

- `nl -ba TODO.md | sed -n '160,180p'`
- `nl -ba helper_scripts/restart_all.sh | sed -n '137,165p'`

Observed:

- OPS-2 Phase 1 secret split is documented as implemented.
- Phase 2 fallback removal remains pending for the planned D+14 cutover.
- `restart_all.sh` still contains a migration-time copy from IPC secret file to live-auth signing-key file when the latter is absent; TODO already tracks the atomicity cleanup as a P3 follow-up.

## Blockers

- P1 blocker: `executor_routes.py` still verifies live authorization with `OPENCLAW_IPC_SECRET` instead of the live-auth signing-key domain.
- Existing operational blocker: OPS-2 Phase 2 fallback removal/cutover remains pending per TODO schedule.

