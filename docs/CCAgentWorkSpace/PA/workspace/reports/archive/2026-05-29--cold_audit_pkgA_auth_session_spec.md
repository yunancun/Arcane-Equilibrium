# PA Implementation Spec — Cold Audit Package A: Auth/Session/GUI Truthfulness

Date: 2026-05-29 Europe/Madrid. Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
HEAD `58f9519a` on `main`. Role: PA(default). Mutation scope: this report only.
Source basis: PA validated fix plan `2026-05-17--cold_audit_validated_fix_plan.md`
(Session A). All file:line ranges re-read at current HEAD during this synthesis.

This is an implementation spec. PA designs contracts/interfaces/tests; E1
implements; E2/E4/A3/E3 verify. No feature code is written here.

---

## 0. CRITICAL RULING — Python control-plane state: advisory, never gate-authoritative

**Ruling: Python control-plane state (`active`/`granted`/`success`/`passed`) is
ADVISORY for live readiness and is NOT gate-authoritative.**

Per CLAUDE.md §一/§四: Rust `openclaw_engine` is the execution/authorization
authority; Python is control-plane/GUI-backend only and must never fake success.
Therefore every Python response field that asserts live readiness MUST be backed
by one of:

1. A successful IPC call to Rust whose result is read back (not fire-and-forget), OR
2. A successful signed-authorization verification against the SAME key domain Rust
   uses (`OPENCLAW_LIVE_AUTH_SIGNING_KEY` with Phase-1 IPC fallback), OR
3. Explicit operator manual-mark semantics that the readiness gate does NOT trust
   as evidence (P1-05).

Concrete invariants E1 must enforce:

- **INV-A1**: No live response may carry `authority:"granted"` /
  `session_state:"active"` unless the IPC resume/start call returned success AND
  a `get_state` readback confirms the engine is in a live-capable posture.
- **INV-A2**: No control response may return `"success"` / `rust_synced` true after
  a swallowed IPC exception (P1-17). IPC failure => `partial_failure` +
  `rust_synced:false`.
- **INV-A3**: Stamped recheck/validate states (P1-05) must NOT satisfy any
  downstream readiness gate. They are operator memos with a distinct
  `evidence:"manual_mark"` marker, or they are replaced by real evidence executors.
- **INV-A4**: Live-auth HMAC verification must use the live-auth signing-key domain,
  never the IPC transport secret (P1-01). The two secret domains are distinct:
  - `OPENCLAW_IPC_SECRET` = IPC transport/channel auth ONLY (see
    `ipc_client_sync.py:50,94-102` __auth token). Correct usage.
  - `OPENCLAW_LIVE_AUTH_SIGNING_KEY` (+ Phase-1 IPC fallback) = authorization.json
    HMAC. Used by signer `live_trust_routes.py:272` and Rust
    `live_authorization.rs:392-399`. The executor verifier violates this.

This ruling resolves PA-plan Serialized item 3 for P1-02 and P1-17.

---

## 1. SHARED HELPER E1 MUST CREATE (de-dup across the 5 fixes)

Three of the five fixes need the same primitives. To avoid duplicated logic E1
introduces ONE small helper module (Python control plane) plus reuse of an
existing Rust IPC method. No new Rust code is required for Package A.

### 1.1 `live_preflight.py` (new, control_api_v1/app/)

A single import-light module that the executor gate, live-session start/resume,
and grant all call. It must NOT duplicate the verifier body — it delegates.

```python
# live_preflight.py
def live_auth_signing_key() -> str:
    """Reuse live_trust_routes._read_live_auth_signing_key() (lazy import).
    Returns the live-auth signing key (primary OPENCLAW_LIVE_AUTH_SIGNING_KEY,
    Phase-1 fallback OPENCLAW_IPC_SECRET). Empty string => caller fail-closed.
    為何集中：P1-01 root cause 是 executor verifier 直讀 IPC secret。"""

def verify_signed_authorization(slot_dir: Path, endpoint_label: str, actor) -> None:
    """Single source-of-truth signed-auth verifier. Body MOVED from
    executor_routes._verify_authorization_json_or_raise, with the one HMAC
    line changed to use live_auth_signing_key(). Raises the same _gate_failure
    taxonomy (authorization / _malformed / _schema / _signature / _expired /
    _env_mismatch)."""

async def engine_mode_readback(timeout: float = 3.0) -> dict:
    """Call Rust IPC method "get_state" and return {system_mode, trading_mode,
    status}. Raises on IPC failure (caller decides fail-closed)."""

def all_five_live_gates_ok(actor, *, require_authz: bool) -> tuple[bool, list[str]]:
    """Optional convenience: evaluate role + live_reserved exact-match +
    OPENCLAW_ALLOW_MAINNET + secret slot + (if require_authz) signed authorization.
    Returns (ok, reason_codes). Used by start/resume to consolidate gate logic.
    Must use EXACT == 'live_reserved', never substring."""
```

Design notes:
- `verify_signed_authorization` is the moved body of the existing executor
  verifier. `executor_routes.py` keeps a thin wrapper that calls
  `live_preflight.verify_signed_authorization(...)` so its one caller at
  `executor_routes.py:261` is untouched.
- `engine_mode_readback` wraps the **existing** Rust IPC method `"get_state"`
  (confirmed `ipc_server/dispatch.rs:130` -> `handlers/misc.rs:54-63` returns
  `system_mode`/`trading_mode`/`status`). No Rust change needed.
- Cross-platform: reuse `live_trust_routes._live_secret_slot_dir()` for paths; no
  hardcoded home.

### 1.2 GUI helper `renderMutationResult(d)` (tab-live.js / shared static helper)

A small Vanilla-JS helper (no framework) that reads the CANONICAL top-level
envelope fields and decides toast severity. Eliminates the wrong-nested-field bug
across close-all, emergency-stop, and session-stop:

```js
// returns {severity:'success'|'warn'|'error', message:String}
function classifyLiveMutation(d) {
  // d is the ocPost result; live responses are wrapped: real payload at d.data
  const p = (d && d.data) ? d.data : d;
  if (!p) return {severity:'error', message:'命令失敗'};
  const partial = p.partial_failure === true || p.closed_all === false
                  || p.status === 'partial_failure';
  const errs = collectAllErrors(p); // p.errors + p.close_result?.errors + p.orphan_sweep
  if (partial || (errs && errs.length))
    return {severity:'error', message:'部分失敗，殘留風險: ' + errs.join('; ')};
  return {severity:'success', message:(p.message || '完成')};
}
```

Rationale: backend already returns correct top-level `partial_failure`/
`closed_all`/`status` (verified `live_session_account_routes.py:687-714`,
`live_session_endpoints.py:354-372`). The defect is purely frontend reading
`d.data.close_result.errors` and ignoring top-level flags + `orphan_sweep`.

---

## 2. PER-FINDING SPEC

### P1-01 — Executor verifier uses wrong secret domain

- **Scope**: `executor_routes.py:290-429` (`_verify_authorization_json_or_raise`),
  specifically the HMAC line `368` (`get_secret_value("OPENCLAW_IPC_SECRET")`).
  Single caller `executor_routes.py:261`.
- **Contract change**: HMAC key source changes from `OPENCLAW_IPC_SECRET` to
  `live_preflight.live_auth_signing_key()` (primary live-auth key + Phase-1 IPC
  fallback, matching `live_trust_routes._read_live_auth_signing_key()` and Rust
  `live_authorization.rs:392-399`). Missing-key fail-closed message updated to
  name `OPENCLAW_LIVE_AUTH_SIGNING_KEY`.
- **E1 changes**: Move verifier body into `live_preflight.verify_signed_authorization`;
  change the one HMAC line; leave the executor wrapper delegating. Do NOT change
  the `_gate_failure` reason taxonomy or the schema/expiry/env checks.
- **E2/E4 tests** (extend `test_executor_shadow_toggle_api.py` + new
  `test_live_auth_key_domain.py`): split-key matrix —
  (a) auth signed with `OPENCLAW_LIVE_AUTH_SIGNING_KEY`, only live-auth key set =>
  PASS; (b) auth signed with live-auth key, only IPC secret set (no live-auth key,
  Phase-1 fallback resolves IPC) => PASS via fallback parity; (c) auth signed with
  live-auth key but verifier given a different IPC secret and no live-auth key =>
  FAIL `authorization_signature`; (d) both keys distinct & set => primary wins,
  parity with signer.
- **Acceptance**: A `authorization.json` produced by the canonical renew/approve
  path (`_write_signed_live_authorization`) is accepted by the executor gate under
  every key-config the signer accepts; never accepts an IPC-only signature when a
  live-auth key is present.
- **Risk**: HIGH (security gate). Coupling: `live_trust_routes` internal helpers.
  Verify by: E3 + E2 + E4.

### P1-02 — start/resume/grant mark active/granted without gate + readback

- **Scope**: `live_session_endpoints.py:135-224` (start), `407-457` (resume),
  `466-493` (grant).
- **Defects confirmed**: (1) start sets `_set_execution_authority("granted")` and
  returns `authority:"granted"` + `session_state:"active"` BEFORE IPC `resume_paper`;
  IPC failure at `197-198` is swallowed (`logger.warning`); no signed-auth verify.
  (2) resume `423` uses substring `"live" not in global_mode` instead of exact
  `== "live_reserved"`; grants before IPC; swallows nothing but returns "active"
  even though IPC success is not read back. (3) grant `480` stamps granted with no
  auth verify or readback.
- **Contract change (INV-A1)**: ordering becomes gate -> IPC -> readback -> stamp.
  - Exact match: replace substring check with `global_mode == "live_reserved"`.
  - Before returning `authority:"granted"`/`session_state:"active"`, the IPC
    `resume_paper` MUST succeed (not be swallowed) AND `engine_mode_readback()`
    MUST confirm engine posture. On IPC failure: do NOT grant; return 502/409 with
    `authority:"denied"`, `session_state:"inactive"`, `rust_synced:false`, and
    `partial_failure:true`. Keep `_set_execution_authority` revocation on failure.
  - `start` and `resume` should call `verify_signed_authorization` (via
    `all_five_live_gates_ok(require_authz=True)`) so a missing/expired/wrong-domain
    authorization blocks the session — aligning the session surface with the
    executor surface and Rust spawn gate.
  - `grant` (manual operator) must either (a) also run the full preflight before
    stamping granted, or (b) be explicitly demoted to an advisory "intent" that the
    readiness path does not treat as live-ready. PA recommends (a) for consistency.
- **E1 changes**: reorder; remove swallow; add readback; exact-match; route start/
  resume/grant through `live_preflight`. Keep contraction-monitor wiring.
- **E2/E4/A3 tests** (extend `test_live_session_endpoint_actual_engine_kind.py`,
  `test_session_stop_cancel_verify.py`; A3 `node --check` for any touched JS):
  IPC-failure-on-start => no `granted`, response `partial_failure:true`; resume
  with `global_mode="live_demo_observe"` (contains "live") => 409 (exact match
  blocks); missing authorization => gate_failure; happy path => readback-confirmed
  active.
- **Acceptance**: No `active`/`granted` is returned unless gates pass + IPC success
  + readback. Exact `live_reserved` only.
- **Risk**: HIGH (live authority surface). Coupling: `live_session_routes` core
  (`_ipc_command`, `_set_execution_authority`, `_live_response`), earned-trust hook.
  Verify by: E3 + E2 + A3 + E4.

### P1-04 — close-all / emergency GUI shows success on partial failure

- **Scope**: `tab-live.js:1082-1089` (doEmergencyStop), `1105-1117` (doLiveCloseAll);
  backends `live_session_endpoints.py:354-372` (stop), `live_session_account_routes.py:687-714`
  (close-all). Backends are CORRECT (top-level `partial_failure`/`closed_all`/`status`).
- **Root cause**: frontend reads `d.data.close_result.errors` only, ignores
  top-level `partial_failure`/`closed_all`/`status` and `orphan_sweep`. Because
  `_live_response` wraps payload under `data`, the canonical flags live at
  `d.data.partial_failure` etc. `doEmergencyStop` only checks `if (d)` truthiness.
- **Contract change**: introduce `classifyLiveMutation(d)` (§1.2); render red/error
  + blocking on any partial failure; never green when residual risk exists.
  Consider backend returning HTTP 424 Failed Dependency (or 409) on
  `partial_failure` so `ocPost` surfaces it as non-OK — PA recommends 424 for
  close-all/stop incomplete risk-reduction (frontend must still classify on 200 for
  defense-in-depth). Backend status-code change is OPTIONAL and must keep the body
  shape stable for existing tests.
- **E1 changes**: frontend wire close-all + emergency-stop + stop toasts through the
  helper; (optional) backend 424 on partial. No change to backend body fields.
- **A3/E2/E4/BB tests**: render test (partial backend payload => error/blocking
  toast, not success); `node --check` for tab-live.js; backend test asserting
  `partial_failure:true` when `orphan_sweep.skipped` non-empty even if
  `close_result.errors` empty (the exact silent path).
- **Acceptance**: any `partial_failure`/`closed_all=false`/non-empty errors (incl.
  orphan_sweep) renders red/blocking; only fully-clean => success.
- **Risk**: MEDIUM (display layer + optional status code). Coupling: `ocPost`
  truthiness contract, `_live_response` wrapper. Verify by: A3 + E2 + BB + E4.

### P1-05 — safe-recheck / demo-validate stamp readiness without evidence

- **Scope**: `control_ops.py:164-224` (`demo_validate`), `329-396`
  (`safe_recheck_bundle`); `tab-settings.html:680-685` (bundleRecheck),
  `666-678` (demoAction).
- **Defect**: mutators write `demo_last_action_result="success"`,
  `canonical_recheck_state="passed"`, `closeout_state="passed"` and emit step
  arrays all `action_result:"success"` with no runtime/replay/IPC evidence.
- **Contract decision (INV-A3)**: PA selects **rename-to-manual-mark** for this
  package (real evidence executors are out of Session A scope and belong to the
  evidence/promotion package, Session D). E1 must:
  - Rename result semantics: `demo_last_action_result` stays but add
    `evidence:"manual_mark"` and `verified:false` to the action record and response
    `data`. States become `manual_marked` not `passed` where they feed readiness;
    OR keep field names but add an `evidence_kind` marker that downstream readiness
    gates explicitly reject (see below).
  - **Hard requirement**: stamped states MUST NOT satisfy any readiness gate. E1
    must locate every reader of `canonical_recheck_state=="passed"` /
    `closeout_state=="passed"` / `demo_last_action_result=="success"` and ensure a
    `manual_mark` stamp does not unlock demo arm/enable. If a reader currently
    trusts these, gate it on `evidence != "manual_mark"`.
  - GUI: toast wording changes from "OK/completed" to "已手動標記（非驗證）/ manual
    mark, not verified" so the operator is not misled.
- **E1 changes**: add evidence markers; downgrade language; add reject-on-manual to
  readiness readers. Do NOT invent fake replay/IPC here.
- **A3/E2/QA tests**: assert response carries `evidence:"manual_mark"`/`verified:false`;
  assert a manual mark does NOT flip any demo readiness gate to ready; `node --check`
  for tab-settings.html inline JS; GUI shows non-success styling.
- **Acceptance**: recheck/validate are honest memos; readiness gates reject manual
  marks as evidence.
- **Risk**: MEDIUM (control-plane state + readiness coupling). Coupling: demo
  readiness gate readers (must be enumerated by E1 before edit). Verify by: A3 + E2
  + QA.

### P1-17 — set_system_mode swallow returns success

- **Scope**: `control_ops.py:504-529` (`apply_input_action` mode push);
  `tab-system.html:723-738` (switchSystemMode result handling).
- **Defect**: `sync_ipc_call("set_system_mode")` exception caught `520-523` with bare
  `pass`; function returns `"success"` at `529` regardless. GUI reads
  `result.action_result==='success'` (`728`) and shows green.
- **Contract change (INV-A2)**: when `_MODE_PATH in accepted_paths` and the new mode
  is set, the IPC push result MUST be reflected:
  - On IPC success: optionally `engine_mode_readback()` to confirm
    `system_mode == new_mode`; set `rust_synced:true`.
  - On IPC failure: return `data.rust_synced:false`, `data.partial_failure:true`,
    `data.ipc_error:<sanitized>`; the top-level action result becomes
    `"partial_failure"` not `"success"`. Engine-not-running is a known case: still
    surface `rust_synced:false` + a clear "will sync on restart" reason, but the
    response is NOT plain success.
  - **For live-capable modes** (any future `live_reserved`/`live` switch — currently
    excluded by `ALLOWED_MODE_SWITCHES` at `control_ops.py:537`): a Rust `get_state`
    readback confirming the mode is MANDATORY before returning success. Non-live
    modes (disabled/observe_only/shadow_only/demo_reserved) may return
    `rust_synced:false` partial without readback (engine optional), but never plain
    success on swallowed exception.
- **E1 changes**: replace bare `pass` with structured capture; thread
  `rust_synced`/`partial_failure`/`ipc_error` into the return; add live-mode
  readback branch.
- **GUI changes**: `tab-system.html` handler treats `action_result==='partial_failure'`
  or `rust_synced===false` as warn/error (not the green path); message names
  rust-sync state.
- **E2/E4/A3 tests** (extend `test_live_auth_recheck_trigger.py` pattern for sync IPC
  mock): mock `sync_ipc_call` raising => response `partial_failure`/`rust_synced:false`,
  not success; mock success + readback mismatch (live mode) => fail-closed; GUI
  `node --check`.
- **Acceptance**: IPC failure never yields a success envelope; live modes require
  readback.
- **Risk**: HIGH (system mode authority surface). Coupling: `apply_input_action`
  return contract consumed by `/api/v1/input/config-change` callers + tab-system +
  any test asserting `"success"`. E1 must check those callers. Verify by: A3 + E2 + E4.

---

## 3. CROSS-FILE COUPLING + DISPATCH

- `live_preflight.py` is the single new shared module; P1-01, P1-02 (and P1-17 via
  `engine_mode_readback`) all consume it. Build it FIRST.
- `classifyLiveMutation` shared JS helper consumed by P1-04 (and reusable by P1-02
  GUI). Build alongside P1-04.
- Coupling watch: `apply_input_action` return contract (P1-17) and
  `_live_response`/`ocPost` envelope (P1-04, P1-02) are consumed by existing tests
  asserting `"success"`/`action_result` — E1 must grep and update those assertions,
  not silently break them.
- `_set_execution_authority` (`live_session_routes.py:129`) is mutated by start/
  resume/grant — ensure failure paths revoke (fail-closed), no orphan "granted".
- Rust: NO Rust change required for Package A (verifier key is Python-side; readback
  uses existing `get_state`). Do NOT touch `live_authorization.rs`,
  `set_system_mode` handlers, or any hard-boundary surface.

### Recommended E1 split (max parallelism, near-disjoint files)

- **E1-A (Python control plane / auth)**: `live_preflight.py` (new), `executor_routes.py`
  (P1-01 delegate), `live_session_endpoints.py` (P1-02), `control_ops.py` (P1-05 + P1-17).
  Serialize internally: build `live_preflight` first.
- **E1-B (GUI, depends only on contracts)**: `tab-live.js` + shared `classifyLiveMutation`
  (P1-04), `tab-settings.html` (P1-05 wording), `tab-system.html` (P1-17 handler).
  Can run in parallel with E1-A once response contracts are frozen by this spec.

### E2 top-3 review focus

1. P1-01 key domain: confirm verifier now uses live-auth key + Phase-1 fallback and
   has parity with the signer; no fail-open when both keys unset.
2. P1-02 ordering: no `granted`/`active` precedes IPC success + readback; exact
   `live_reserved`; failure revokes authority.
3. P1-17 / P1-05 no-fake-success: swallowed IPC never returns success; manual marks
   never satisfy readiness gates.

---

## 4. BLOCKERS / FLAGS

- No P0. No hard-boundary edit required; Package A strengthens fail-closed posture.
- `get_state` readback for P1-17/P1-02 reads `system_mode` from
  `pipeline_snapshot.json` (engine-written) — acceptable as engine-confirmed posture,
  but E1 must treat a stale/missing snapshot as readback FAILURE (fail-closed), not
  success.
- P1-05 requires E1 to enumerate demo-readiness gate readers BEFORE editing; if a
  reader is found that already trusts stamped `passed`, that becomes the real
  closure point. Flag to PM if the reader set is larger than `control_ops`.
- Phase-1 secret fallback (OPS-2) remains intentional; do not remove it under
  Package A (separate TODO P1-OPS-2-SECRET-SPLIT-PHASE-2).
- Forbidden under this plan (per validated fix plan): no deploy/restart/migration,
  no authorization.json edits, no secret/TOML edits, no mutating Bybit calls.

PA DESIGN DONE: report path:
docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgA_auth_session_spec.md
