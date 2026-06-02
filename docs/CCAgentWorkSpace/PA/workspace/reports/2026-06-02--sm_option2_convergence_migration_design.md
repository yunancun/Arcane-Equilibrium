# SM Single-Source Convergence — Option 2 Concrete Migration Design (DESIGN-ONLY)

- Date: 2026-06-02
- Author: PA
- Repo: srv @ main HEAD 344025f9 (Mac + Linux trade-core同 HEAD, ssh verified)
- Status: DESIGN-ONLY (no code). For PM → operator sign-off.
- Decision basis: operator-approved 2026-06-02 — end-state = Option 2 (Rust sole authority; Python delete transition logic, become read-only projection + control-plane + live-auth gate).
- Builds on: PA memory 2026-06-01 SM convergence (recommended Option 1 variant; operator overrode to Option 2 end-state), committed 4a contract/parity test (Rust `sm_contract.rs` + Python `test_sm_contract_parity.py` + fixture, Mac+Linux PASS).

## 0. Load-bearing reality corrections (grep/ssh proven — these change the plan vs. the brief's assumptions)

These were verified by reading source + ssh trade-core; they reshape the steps:

1. **The lease IPC seam is HALF-WIRED, not live.** Python client side exists (`governance_lease_bridge.acquire_lease_via_ipc/release/get`), but the Rust IPC server dispatch table (`rust/openclaw_engine/src/ipc_server/dispatch.rs`) has **NO** `governance.acquire_lease / governance.release_lease / governance.get_lease` arms. Unknown methods → `ERR_METHOD_NOT_FOUND` → Python fail-closed (`None`). Proof: `grep '" =>' dispatch.rs` full list has no lease arm; `_ => JsonRpcResponse::error(id, ERR_METHOD_NOT_FOUND, ...)`.
2. **The flag is OFF in production and never passed to the API.** `OPENCLAW_LEASE_PYTHON_IPC_ENABLED` is **not referenced in `helper_scripts/restart_all.sh`** (ssh-verified) → the Python API process never receives it → `is_lease_ipc_enabled()` returns False → lease acquire/release currently run the **legacy local Python SM path** (`governance_hub.py:853-905` / `957-982`). So today's runtime authority for lease is Python-local-SM, not Rust. (`OPENCLAW_LEASE_ROUTER_GATE_ENABLED` IS wired to the engine — different flag, different SM owner.)
3. **The IPC server has NO `GovernanceCore` handle.** dispatch.rs operates only via `pipeline_cmd_tx` / `EngineCommandChannels` → `PipelineCommand` → tick actor (which owns the per-pipeline `GovernanceCore`). Proof: `grep GovernanceCore` in dispatch.rs/mod.rs/server.rs = 0. Therefore every read-projection or lease IPC method must be a `PipelineCommand` round-trip to the tick actor + oneshot reply (the existing pattern, e.g. `ForceGovernorTighter`, `get_risk_runtime_status`).
4. **Operator escalate/de-escalate over IPC already exists** but targets the **engine tick-actor RiskGovernorSm**, not the GovernanceCore facade: `force_governor_tier_tighter/looser` → `PipelineCommand::ForceGovernorTighter/Looser` (handlers/governance.rs), with V014 audit on success AND rejected paths. SM-01 operator freeze/revoke + lease ops over IPC do NOT yet exist on the facade.
5. **The Python SM logic is reached ONLY through GovernanceHub + its 2 mixins + audit_persistence (replay) + a small route re-point set.** No production code imports the SM classes to call `transition()` directly except via `hub._authorization_sm.` / `hub._lease_sm.` / `hub._risk_governor_sm.` member access (full set in §1.3). This containment is what makes Option 2 tractable.
6. **No Python-unique enforcement is lost on cutover.** 4a fixture: `EXPECTED_RUST_ONLY=4` (Reconciler×3 + NotificationFailsafe×1), `EXPECTED_PY_ONLY=0`; 0 divergent allow/deny across shared transitions; INV-D constraint table parity locked. Rust SM unit coverage independently strong (auth ~28 / lease ~20 / risk_gov ~47 test markers). Deleting Python loses no logic-test coverage.

Net effect on plan: the migration is **less "flip a flag, delete Python"** and **more "first build the Rust IPC surface (lease + auth-read + risk-read + operator-freeze/revoke), wire dispatch, parity-gate, then delete."** The destructive delete is the LAST step and is preceded by an explicit operator sign-off gate.

---

## 1. Delete-vs-Keep Inventory

### 1.1 Per-file disposition

| File | LOC | Disposition | Detail |
|---|---|---|---|
| `app/risk_governor_state_machine.py` | 856 | **DELETE transition logic; KEEP enum/constants as projection vocab** | DELETE: `transition()`, `_extra_validate` (min-hold), `evaluate_risk_context`, `escalate_to/de_escalate_to/circuit_break/request_manual_review/complete_manual_review`, `on_health_*`, `RISK_TRANSITION_RULES`, `EscalationThresholds`, `is_order_allowed`. KEEP (move to a slim `risk_projection_types.py`): `RiskLevel` IntEnum (value contract used by routes/GUI), `LEVEL_CONSTRAINTS` + `LevelConstraints` (INV-D mirror; or fetch from Rust — see §3d), `RiskEvent`/`RiskInitiator` enums (audit-record vocab + governance_events). |
| `app/decision_lease_state_machine.py` | 676 | **DELETE transition logic; KEEP enum/object as projection DTO** | DELETE: `transition()`, `LEASE_TRANSITION_RULES`, all convenience methods (`register/activate/bridge/consume/freeze/revoke/...`), `check_expiry`, `create_draft`. KEEP (move to `lease_projection_types.py`): `LeaseState` enum, `DecisionLeaseObject.from_dict/to_dict/clone` (DTO to deserialize Rust `get_lease` serde payload + render GUI), `LeaseEvent`/`LeaseInitiator` (audit vocab). |
| `app/authorization_state_machine.py` | 674 | **DELETE transition logic; KEEP enum/object as projection DTO** | DELETE: `transition()`, `TRANSITION_RULES`, `FORBIDDEN_TRANSITIONS`, all convenience methods (`create_draft/submit_for_approval/approve/reject/restrict/freeze/revoke/recover_*`), `check_expiry`, auto_approve branch. KEEP (move to `auth_projection_types.py`): `AuthState` enum + `EFFECTIVE_STATES`, `AuthorizationObject.from_dict/to_dict` (DTO), `AuthEvent`/`AuthInitiator` (audit vocab). |
| `app/state_machine_base.py` | 494 | **DELETE entirely** | `StateMachineBase`, `MultiObjectStoreMixin`, `_validate_transition` (5 guards), `_build_transition_record`, `_emit_audit`, `_record_change_audit`. Once the 3 subclasses no longer compute transitions, the base has no remaining purpose. (Audit-record schema builder migrates — see §1.2.) |

Rationale for the enum/DTO split: routes, GUI, governance_events, and audit serialization reference `RiskLevel.value`, `AuthState.value`, `LeaseState.value` as **value contracts**. These are not "transition logic"; they are the projection vocabulary and must survive. Keeping them in tiny `*_projection_types.py` files (no engine, no transition table, no guards) is the cleanest delete boundary and keeps `from .risk_governor_state_machine import RiskLevel` style imports re-pointable with a 1-line edit. **Mac note:** whether these enums physically move to new files or stay as enum-only stubs in the existing files is an E1 implementation choice; either way the transition engine is deleted.

### 1.2 Must-keep beyond the SM files (the "Python stays" layer)

These are NOT in scope to delete and are explicitly preserved:

- **5 live-auth gates (NOT in SM files at all)** — Python `live_reserved` flag, Operator-role auth (`_require_operator_role`), signed `authorization.json` HMAC renew/approve path, `OPENCLAW_ALLOW_MAINNET`, secret slot. These live in the live-session / auth routes layer, are independent of the 3 governance SMs, and **stay 100% Python** (CLAUDE.md §四 hard boundary). The SM-01 AuthorizationSM (paper/demo auto-auth + governance permits) is a SEPARATE object from these 5 gates; deleting the Python SM-01 transition logic does not touch them.
- **GovernanceHub control-plane (`governance_hub.py`)** — KEEP the class and its public API (`is_authorized`, `acquire_lease`, `release_lease`, `get_lease`, `drive_lease_expiry`, `grant_paper_authorization`, `request_de_escalation`, `approve_de_escalation`, `reconcile`, `get_status`, all `set_*` DI). The internals change from "call local SM `transition()`" to "IPC to Rust + project". This is the single chokepoint every caller already uses.
- **Cross-SM coordination mixins** — `governance_hub_cascades.py` (`get_status`, `_on_reconciliation_mismatch`, governance-event aggregation), `governance_hub_event_handlers.py` (callback factories, `_wire_callbacks`, `_invalidate_auth_cache`, `_check_de_escalation_gate`). Post-cutover these become **advisory / projection** (the authoritative cross-SM cascade is Rust `GovernanceCore::execute_risk_cascade`); the Python reconcile-mismatch escalation becomes either (a) an IPC command to Rust to escalate, or (b) advisory-only since the Rust `event_consumer` + reconcile already drives the Rust cascade. **Recommend (a)** to preserve the EX-04→SM-04 reaction explicitly. The `get_status` projection (9 route consumers) is reshaped to read from Rust (§2).
- **Audit-record schema builders** — `_build_transition_record` produces the `lease_transitions` / authorization / risk audit row shape. The AUTHORITATIVE writer is already Rust `event_consumer` + `lease_transition_writer.rs` (V054). The Python builder is retained ONLY if Python still writes any audit row post-cutover; recommendation: Python stops writing SM transition audit rows entirely (Rust owns it), so the Python builder is DELETED with the base. Hard constraint (§3e): byte-parity of Rust-written rows vs. historical Python rows must be Linux-verified before delete.
- **`governance_lease_bridge.py`** — KEEP and PROMOTE from "optional bridge" to "the lease path." Its dual-write mirror is retired in cleanup (§5 step iv).
- **`audit_persistence.py`** — constructs SMs for replay/persistence (`auth_sm = AuthorizationStateMachine(...)`, `risk_gov = RiskGovernorStateMachine(...)`). This is a REPLAY/audit-callback consumer, not live authority. Post-cutover it must NOT reconstruct a transition-capable Python SM. Re-point: either (a) replay reads Rust-emitted audit rows directly (no Python SM), or (b) keep a passive read-only "audit record renderer" using the kept DTOs. **Recommend (a)** — replay already has a Rust path (`replay/` package, P4 refactor at HEAD).

### 1.3 Caller re-point map (every production site that touches SM logic, + where it re-points)

GovernanceHub is the chokepoint; no caller imports SM classes to call `transition()` except via hub members. Full set (grep-proven, test files excluded):

| Caller : line | Current call | Re-points to |
|---|---|---|
| `governance_hub.py:771-905` `acquire_lease` | legacy local `_lease_sm.create_draft/register/activate` (Step 4 fallback) | DELETE Step 4; always route `acquire_lease_via_ipc` (Step 3 becomes unconditional once IPC server wired + flag on). |
| `governance_hub.py:907-982` `release_lease` | legacy local `_lease_sm.consume/revoke` | DELETE local; always `release_lease_via_ipc`. |
| `governance_hub.py:984-1009` `get_lease` | local `_lease_sm.get` | always `get_lease_via_ipc` (DTO deserialize). |
| `governance_hub.py:1011-1019` `drive_lease_expiry` | local `_lease_sm.check_expiry()` | Rust `GovernanceCore::check_expiry` (already runs on the tick actor every tick) → Python `drive_lease_expiry` becomes a no-op/`[]` or a read of Rust-expired ids via projection. Expiry is Rust-driven; Python stops driving it. |
| `governance_hub.py:460-514` `is_authorized` | local `_authorization_sm.get_effective()` | IPC read of Rust `is_authorized()` (new projection method) with fail-CLOSED + staleness (§4). Keep 100ms TTL cache. |
| `governance_hub.py:663-769` `grant_paper_authorization` | local `_authorization_sm.create_draft/submit/approve` | IPC command to Rust `grant_paper_authorization` (new IPC method) OR keep Python auto-grant ONLY for paper bootstrap if Rust per-pipeline auto-grant (`new_with_profile(Exploration/Validation)`) already covers it. **Verify on Linux**: Rust pipelines auto-grant at construction (`governance_core.rs:226 new_with_profile`), so Python `grant_paper_authorization` may already be redundant for live/demo and only matters for the Python-hub paper path. Decide per ssh check. |
| `governance_hub_cascades.py:487-559` `_on_reconciliation_mismatch` | local `_risk_governor_sm.escalate_to`, `_authorization_sm.freeze` | IPC command to Rust to escalate (reuse `ForceGovernorTighter` or new `governance.escalate`) — OR advisory-only (Rust reconcile already cascades). Recommend explicit IPC escalate. |
| `governance_routes.py:691-701` (create draft + submit) | `hub._authorization_sm.create_draft/submit_for_approval` | new hub method `submit_authorization_draft(...)` → IPC command to Rust auth SM. |
| `governance_routes.py:767-776` `approve_authorization` | `hub._authorization_sm.list_all()` + `.approve()` | new hub method `approve_pending_authorization(approved_by)` → IPC command. (Note `list_all()` ≠ kept `get_all()` — fix in this step.) |
| `governance_routes.py:932` operator escalate | `hub._risk_governor_sm.escalate_to(...)` | already-wired `force_governor_tier_tighter` IPC (or new `governance.escalate`); remove direct member access. |
| `governance_extended_routes.py:206-220` lease list | `hub._lease_sm.get_all()/get_live()` | new hub method `list_leases()` → IPC read (Rust `get_live` + a new `list_all_leases` projection) → DTO. |
| `paper_trading_wiring.py:145-224` incident wiring | `_authorization_sm.reject`, `_lease_sm.reject`, `_risk_governor_sm.request_manual_review`×2 | IPC commands to Rust (reject auth / reject lease / request manual review) — these are degrade-on-failure paths; must stay fail-CLOSED. |
| `audit_persistence.py:494-497` | constructs `AuthorizationStateMachine` / `RiskGovernorStateMachine` for replay | re-point to read-only audit replay (no transition-capable SM). |
| `paper_trading_routes.py:241-262`, `main.py:430-431`, `governance_extended_routes.py:411`, `lg5_review_consumer_scheduler.py` | `hub.is_authorized()` / `grant_paper_authorization()` (public API only) | NO change to call site — these use the public hub API; only the hub internals change. |

The re-point set requiring NEW Rust IPC methods: auth submit/approve/freeze/revoke/restrict, lease reject, risk request-manual-review, list-all-leases, is_authorized-read, risk-state-read. This drives §2 + the Rust-touching steps in §5.

---

## 2. Read-projection design (the IPC surface Python uses)

Principle: **cold-path only, never hot-path.** Hot-path enforcement (per-tick H0 gate, intent gate, lease acquire-on-trade) is already Rust in the tick actor; the Python projection is for GUI/routes/cold coordination. The projection reuses the established `PipelineCommand` round-trip pattern (oneshot reply), because the IPC server has no direct `GovernanceCore` handle (§0.3).

### 2.1 Existing surface to leverage (confirm/extend)

- **Lease ops (extend — currently half-wired):** `governance.acquire_lease`, `governance.release_lease`, `governance.get_lease` — Python client methods EXIST (`lease_ipc_schema.py:69-71` constants; `governance_lease_bridge.py`). **MUST ADD the Rust dispatch arms** mapping these to `GovernanceCore::acquire_lease/release_lease/get_lease_by_id` via a new `PipelineCommand::{AcquireLease,ReleaseLease,GetLease}` + oneshot. This is the single biggest "extend existing" task.
- **Status snapshot (extend):** Rust `GovernanceCore::status()` → `GovernanceStatus { enabled, mode, risk_level, auth_effective_count, lease_live_count, oms_active_count }`. There is likely an existing status read path (`get_risk_runtime_status`, `get_mode_snapshot`); extend or add `governance.get_status` to project this for the 9 `get_status()` route consumers.

### 2.2 New projection methods (read-only; cold-path)

| IPC method (proposed) | Rust source | Python consumer | Returns |
|---|---|---|---|
| `governance.is_authorized` | `GovernanceCore::is_authorized()` | `hub.is_authorized()` | bool (fail-CLOSED on IPC error) |
| `governance.get_status` | `GovernanceCore::status()` + auth_pending count | `hub.get_status()` (9 consumers), `governance_routes.approve_authorization` (needs `auth_pending_approval`) | GovernanceStatus dict |
| `governance.list_leases` | `GovernanceCore::lease.get_live()` + new `list_all()` | `governance_extended_routes` lease list GUI | list[LeaseObject serde] |
| `governance.get_risk_state` | `GovernanceCore::risk` snapshot (level, level_entered_at, held_ms, last_event, transitions tail, constraints) | `hub.get_status()["risk"]`, risk GUI | GovernorState-equivalent dict |
| `governance.get_auth_states` | `GovernanceCore::auth.get_all()` projection | auth GUI / pending-approval queue | list[AuthorizationObject serde] |

Transition-legality reads: the control-plane does NOT need a generic "is (from,to) legal?" projection — it needs to ISSUE transitions (commands, §3c), and Rust returns Ok/Err. So no `is_transition_legal` projection method is required; legality is enforced Rust-side on the command.

### 2.3 DTO contract

Python keeps `AuthorizationObject.from_dict` / `DecisionLeaseObject.from_dict` / a `GovernorState`-equivalent dataclass (in the `*_projection_types.py` files) purely to deserialize Rust serde payloads for GUI rendering. The Rust serde field names must match these `from_dict` keys — locked by a new serde-shape parity assertion (extend 4a, see §3e/§5).

---

## 3. Hard constraints — how each is met

**(a) 5 live-auth gates stay Python (NOT deleted).** These are in the live-session/auth-routes layer, structurally separate from the 3 governance SM files. The delete set (§1.1) touches only `*_state_machine.py` + `state_machine_base.py`. CC guardrail: a `grep` proof in the cutover PR that `live_reserved`, `_require_operator_role`, `authorization.json` HMAC renew/approve path, `OPENCLAW_ALLOW_MAINNET`, secret-slot code are untouched by the diff. (CLAUDE.md §四 + DOC-08 §12 inv 5/6/9.)

**(b) Fail-CLOSED on Python↔Rust IPC failure.** Every projection read and every command degrades conservatively:
- `is_authorized()` IPC failure → return **False** (deny), never True. (Mirrors existing `governance_hub.py:488,508,514` fail-closed.)
- `acquire_lease` IPC failure → return **None** (deny) — already the contract (`governance_hub.py:836-851` "we do NOT silently fall through to local SM"). After Python SM delete there is no local SM to fall through to, so fail-closed is structurally guaranteed.
- `get_status`/`get_risk_state` IPC failure → project **most-conservative** view (mode=FROZEN / risk≥CAUTIOUS sentinel + `stale=true` flag), never NORMAL. GUI shows "SM unavailable (engine down) — treating as restricted."
- Operator commands (freeze/revoke/escalate) IPC failure → return error to operator (command not applied), surfaced loudly; never silently succeed.
- No path may interpret an IPC timeout/`ERR_METHOD_NOT_FOUND`/malformed payload as permissive. CC guardrail: cutover PR must show each new projection/command has an explicit fail-closed branch.

**(c) Preserve operator freeze/revoke (SM-01 Active→Frozen/Revoked via Console).** Today: `governance_routes` operator routes reach `hub._authorization_sm` (and one `escalate_to`). Design: these become **IPC commands to Rust** routed through new `PipelineCommand` variants to the tick-actor `GovernanceCore`:
- New IPC methods: `governance.freeze_authorization`, `governance.revoke_authorization`, `governance.restrict_authorization`, `governance.recover_authorization` (+ `submit/approve` for the pending flow). Each → `PipelineCommand::Auth{Freeze,Revoke,Restrict,Recover,Submit,Approve}` → tick actor calls `core.auth.freeze/revoke/...` → oneshot Ok/Err → V014 audit (reuse `spawn_governor_audit_row` pattern, both success + rejected). The operator-role gate stays Python (constraint a) BEFORE the IPC command is issued.
- Operator risk escalate/de-escalate already have IPC (`force_governor_tier_tighter/looser`); the route stops touching `_risk_governor_sm` directly and uses the IPC path. De-escalation keeps Python `RecoveryApprovalGate` (control-plane) in front of the IPC command.
- Risk: this expands the Rust IPC command surface touching auth authority → high-risk; E2 + CC + BB (if it can affect live auth) must review. Must NOT touch the 5 live-auth gates or `execution_authority`.

**(d) SM-04 INV-A..E enforced ONLY in Rust; 4a is the byte-parity regression lock.** After delete, the only validator of escalation-without-approval / de-escalation-needs-approval+hold-time / constraint table / no-bypass-circuit-breaker is `rust/openclaw_core/src/sm/risk_gov.rs` (47 unit tests) + `governance_core.rs`. The 4a `sm_contract.rs` + `test_sm_contract_parity.py` REMAIN as the regression lock. **Subtlety:** after the Python transition engine is deleted, the *Python side* of the parity test can no longer drive a real Python `transition()`. Two options for 4a post-cutover:
  - (d-1) **Keep a test-only minimal Python reference SM** (frozen, ~150 LOC, not imported by production) that the parity harness drives — preserves true cross-language equivalence forever. **Recommended.**
  - (d-2) Convert the Python side to assert against the fixture's `expect` directly (fixture becomes the spec; Rust harness validates Rust against it). Loses the "two independent implementations agree" property but keeps the spec lock.
  Recommend (d-1): the frozen reference is cheap and is the strongest anti-regression. INV-B (hold-time) and INV-D (constraint table) already have dedicated Python tests (`test_inv_b_*`, `test_inv_d_*`) — INV-D's `_EXPECTED_CONSTRAINTS` table stays as the Rust-mirror lock.

**(e) Audit-schema parity (Rust event_consumer rows == what Python wrote) — Linux-verify.** The `lease_transitions` (V054) rows are ALREADY written by Rust `event_consumer` + `lease_transition_writer.rs`; Python's local-SM path also wrote audit via `_emit_audit`→audit_pipeline. Before deleting the Python writer:
  - **Linux dry-run**: run a lease acquire/release through the IPC path on Linux, compare the Rust-written `lease_transitions` row columns (transition_id/previous_status/next_status/initiated_by/trigger_event_type/effective_at_ms/profile/engine_mode/...) against a historical Python-written row. Confirm column set + value semantics match V054 CHECK constraints.
  - Extend the 4a fixture with an **audit-row-shape vector** (or a separate `test_lease_audit_schema_parity`) asserting the Rust serde `LeaseTransitionMsg` → V054 row maps to the same keys the Python `_build_transition_record` produced. This is a NEW deliverable in step (i).
  - For auth/risk audit rows: confirm whether Rust emits equivalent rows (auth transitions / risk transitions). If Rust does NOT yet write auth/risk transition audit rows that Python wrote, that is a **gap to close before delete** (else cutover loses audit lineage → violates principle 8 / DOC-08 inv). **Linux-verify which audit tables Rust currently populates for auth + risk.** (Flag: this is the highest-risk parity unknown; resolve before step iii.)

**(f) 3-config independence (paper/demo/live SM-04 thresholds).** Rust holds per-pipeline `EscalationThresholds` inside each pipeline's `GovernanceCore` (each pipeline constructs its own via `new_with_profile`). The Python `EscalationThresholds` deletion does NOT collapse the 3 configs — Rust already has 3 independent `RiskConfig`/threshold sets (paper/demo/live `risk_config*.toml` → ConfigStore). Constraint: the projection `get_risk_state` must read the **per-pipeline** governor (the projection command must target the correct pipeline slot, like `set_system_mode` broadcasts but reads are per-pipeline). CC guardrail (feedback_env_config_independence): do not merge the 3 threshold sources during this work.

---

## 4. Engine-down handling (this was 4b's main argument; show Option 2 handles it)

Problem: Option 2 makes Python a projection of Rust. If the engine is DOWN, Python has no live SM state. Design:

- **Live-auth gate layer still issues authoritative deny when engine down (the critical guarantee).** The 5 live-auth gates are Python and do NOT depend on the engine being up: `live_reserved`, operator-role, `authorization.json` HMAC, `OPENCLAW_ALLOW_MAINNET`, secret slot are all evaluated in Python regardless of engine state. With the engine down, no Rust pipeline is running to execute orders anyway, so "Python has no SM projection" does not create a live-trading hole — there is no order path. This is the structural answer to 4b: **engine-down ⇒ no execution ⇒ the missing projection cannot be exploited.**
- **Projection degrades to last-known-cached + staleness flag, conservatively.** `is_authorized()` engine-down → return **False** (fail-closed, §3b). `get_status()` engine-down → return cached-last-known with `stale=true` + `engine_reachable=false` + `mode=FROZEN` sentinel for any consumer that gates on it. GUI renders an explicit "SM state unavailable (engine down) — shown as FROZEN/restricted; last known at <ts>." Never render NORMAL when stale.
- **Operator commands engine-down** → return loud error ("cannot apply: engine unreachable"); operator uses the live-auth/console halt path (which is engine-independent) for emergency freeze. The existing engine-down emergency paths (clean_restart_flatten demo-only, console halt) are unchanged.
- **No fabricated state.** Python NEVER invents an SM transition or assumes a permissive state when Rust is unreachable (principle 6 + 10). The cached snapshot is read-only display, never an authority for a new decision.

Acceptability: engine-down means trading is already halted; the only thing the operator needs is (1) a truthful "unavailable/FROZEN" projection and (2) an engine-independent halt path — both preserved. Option 2 therefore handles engine-down acceptably without retaining a parallel Python authority. (This is strictly better than the prior dual-write ambiguity where Python and Rust could disagree silently.)

---

## 5. Incremental migration steps (each behavior-preserving + parity-gated)

Every step is independently revertible until step (iii). Gate = condition that must be GREEN before the step is allowed to land/deploy.

### Step (i) — Wire the Rust IPC surface + make IPC routing authoritative (Rust + Python; NO delete)
- **Rust:** add dispatch arms `governance.acquire_lease/release_lease/get_lease` + new read/command methods (§2.2, §3c) via new `PipelineCommand` variants + oneshot replies routed to the tick-actor `GovernanceCore`. (Closes §0.1 half-wire.)
- **Python:** keep the local SM but route the public hub API through IPC when flag on; the local SM SHADOW-computes in parallel and a runtime comparator logs any divergence (extends the existing dual-write mirror to a compare).
- **Parity additions:** extend 4a with (1) lease audit-row-shape parity (§3e), (2) DTO serde-shape parity (§2.3). Add a runtime divergence counter (IPC-result vs shadow-local-SM) surfaced in healthcheck.
- **Gate before landing:** 4a (existing + new vectors) PASS on Mac AND Linux; Rust `cargo test` sm/* + governance_core PASS; Linux `--rebuild` deploy; Linux empirical: flip `OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1` (add to restart_all.sh API env), run lease acquire/release + status reads through IPC, confirm Rust `lease_transitions` rows written and shadow-compare shows 0 divergence over a soak window (e.g. 24-48h, or N≥ a few hundred lease ops). **This step makes Rust the authoritative runtime path while Python SM still exists as a safety net.**

### Step (ii) — Reconcile known drift; Python projection adopts Rust's view (read-only)
- Python `get_status`/projection switches to reading Rust state (Reconciler initiator, NotificationFailsafeTimeout, 7d failsafe cooling, `active_lock_profit_per_position`) — these were Rust-only (the 4 rust_only vectors). Python stops pretending it can model them; the projection simply reflects Rust. No Python transition uses them (it never did).
- Re-point `_on_reconciliation_mismatch` to IPC-escalate (§1.3) OR confirm advisory-only is sufficient (Rust reconcile already cascades). Decide via Linux check of whether Rust `event_consumer` reconcile drives SM-04 without the Python escalate.
- **Gate:** divergence counter from step (i) at 0 across the soak; reconcile-mismatch path verified on Linux to still escalate SM-04 (via Rust). Operator informed.

### Step (iii) — CUTOVER: delete Python transition logic; read from Rust (POINT OF NO RETURN)
- DELETE the transition engines + base (§1.1): remove `transition()`/rules/guards/convenience methods from the 3 files; delete `state_machine_base.py`; relocate enums/DTOs to `*_projection_types.py`.
- Delete the local-SM fallback branches in `governance_hub.py` (`acquire_lease` Step 4, `release_lease` legacy, `get_lease` local, `drive_lease_expiry` local, `is_authorized` local), the shadow-compute from step (i), and the route direct-member access (re-point to hub methods → IPC).
- Re-point `audit_persistence.py` replay (§1.2).
- 4a: install the frozen test-only reference SM (d-1) so parity persists.
- **Gate (HARD, irreversible — requires explicit operator sign-off, see §6):** all of step (i)+(ii) gates green for the full soak with 0 divergence; audit-schema parity (§3e) Linux-verified for lease AND (auth+risk if applicable); CC compliance sign-off (16 principles + DOC-08 §12 + 5 hard boundaries 0-touch, esp. inv 5/6/9 + boundary "execution_authority"/`live_reserved` untouched); E2 review of the Rust IPC command surface (esp. auth freeze/revoke); BB review IF any path can affect live auth. Branch frozen, full regression (E4), node --check for any GUI status JS.

### Step (iv) — Cleanup dual-write/fallback/mirror
- Remove `_DUAL_WRITE_MIRROR` + `record_dual_write_*` from `governance_lease_bridge.py` (its 4-week reconcile purpose is fulfilled). Remove divergence comparator. Simplify `acquire_lease_via_ipc` (drop mirror writes).
- Remove `OPENCLAW_LEASE_PYTHON_IPC_ENABLED` gate (IPC is now the only path) OR keep as a kill-switch that, when off, returns fail-CLOSED (NOT local-SM, which no longer exists). Recommend keeping a fail-closed kill-switch for operator emergency.
- **Gate:** post-cutover soak green (e.g. 1 week); no projection/audit anomalies. Reversible (pure Python cleanup, no behavior change).

---

## 6. Risk + rollback

| Step | Blast radius | Reversible? | Rollback |
|---|---|---|---|
| (i) | Rust IPC dispatch + Python hub routing. Risk: new Rust IPC command surface; flag flip changes lease runtime authority paper→Rust. | YES | Flag `OPENCLAW_LEASE_PYTHON_IPC_ENABLED=0` → Python local SM resumes (still present). Revert Rust dispatch arms (additive). |
| (ii) | Python projection read source + reconcile re-point. | YES | Revert projection to local-SM read; revert reconcile re-point. |
| (iii) | **DELETE** Python SM + base + fallback. Touches governance_hub core, 2 mixins, 3 route files, paper_trading_wiring, audit_persistence. | **NO (point of no return)** | Only by `git revert` of the delete commit + redeploy; not a runtime flag. This is why the gate is hard + operator-signed. |
| (iv) | Python-only cleanup (mirror, comparator). | YES | git revert; no behavior change. |

- **Point of no return = step (iii)** deleting the Python transition logic. After it, there is no local-SM safety net; the flag can only fail-closed, not fall back to Python authority.
- **Operator sign-off gate REQUIRED before step (iii)** (the destructive cutover). Sign-off packet must include: (1) step i/ii soak evidence (0 divergence, N ops), (2) audit-schema parity Linux proof for lease + auth + risk, (3) CC compliance verdict (0 hard-boundary touch), (4) E2 + (BB if live-auth-affecting) verdicts, (5) the engine-down behavior demo (§4) showing fail-closed + truthful stale projection.
- **Highest residual risks to flag:** (R1) audit lineage gap if Rust does not yet write auth/risk transition rows that Python wrote (§3e) — MUST resolve before iii. (R2) new Rust IPC auth-command surface (freeze/revoke) is high-risk authority code — full E2/CC/BB. (R3) the in-flight Rust `tick_pipeline/mod.rs` WIP consumes `RiskGovernorSm`; Rust SM enum/API changes in this work must sequence after that WIP lands or be additive-only (PA memory 2026-06-01 §E).

---

## 7. Sequencing / isolation / role shape

- **Branch strategy:** one feature branch per step, merged sequentially; step (iii) on its own branch with the operator-sign-off gate as a merge precondition. Never combine (i) Rust-wiring with (iii) delete.
- **Rust-touching steps (need `restart_all --rebuild` + Linux verify):** (i) [IPC dispatch + commands], (ii) [reconcile IPC-escalate if chosen]. These need Linux empirical (PG `lease_transitions` rows, IPC round-trip, soak divergence). Per CLAUDE.md §六 + feedback_v_migration_pg_dry_run, Mac mock cannot validate IPC/PG runtime.
- **Python-only steps:** (iii) delete + re-point (but its GATE depends on Rust soak), (iv) cleanup. GUI status JS changes (engine-down projection rendering) need `node --check` (feedback_gui_node_check_sop).
- **Per-step chain (CLAUDE.md §八 feature chain):** `PM → PA → E1/E1a → E2 → E4 → QA → PM`, with **CC sign-off gate before step (iii)** (compliance/architecture chain `PM → CC → FA → PA`), and **BB review** for step (i)/(iii) if the Rust auth-command IPC can affect live authorization. E1 parallelization: step (i) splits into E1a=Rust dispatch+PipelineCommand (file: dispatch.rs, handlers/governance.rs, pipeline commands, governance_core projection methods) and E1b=Python hub IPC routing+parity tests (governance_hub.py, governance_lease_bridge.py, test_sm_contract_parity.py extensions) — disjoint files, parallel-safe. Step (iii) is mostly serial (delete touches shared governance_hub + mixins).
- **E2 must-review top-3:** (1) every new projection/command has an explicit fail-CLOSED branch (no permissive default on IPC error); (2) the Rust auth-command IPC surface does not touch `execution_authority` / `live_reserved` / the 5 gates and writes V014 audit on success AND rejected; (3) audit-schema parity Linux proof attached for lease + auth + risk before the delete commit (no silent audit-lineage loss).

---

## Appendix — Key file:line anchors (verified this session)

- Python SMs: `authorization_state_machine.py` (674), `decision_lease_state_machine.py` (676), `risk_governor_state_machine.py` (856), `state_machine_base.py` (494).
- Hub: `governance_hub.py` — `acquire_lease` 771-905, `release_lease` 907-982, `get_lease` 984-1009, `drive_lease_expiry` 1011-1019, `is_authorized` 460-514, `grant_paper_authorization` 663-769, `_ensure_initialized` 395-451 (constructs SMs 424-426).
- Bridge: `governance_lease_bridge.py` — `is_lease_ipc_enabled` 124-134, `acquire_lease_via_ipc` 353-440, dual-write mirror 150-227. Schema: `lease_ipc_schema.py:69-71` (METHOD constants).
- Rust facade: `governance_core.rs` — `acquire_lease` 400-519, `release_lease` 658-774, `get_lease_by_id` 784-794, `is_authorized` 263-268, `status` 993-1002, `new_with_profile` 226-251, `execute_risk_cascade` 802-885.
- Rust IPC: `ipc_server/dispatch.rs` (no lease arm; unknown→ERR_METHOD_NOT_FOUND ~502), `ipc_server/handlers/governance.rs` (force_governor tighter/looser + set_system_mode + spawn_governor_audit_row V014).
- 4a parity: `rust/openclaw_core/tests/sm_contract.rs` (EXPECTED_RUST_ONLY=4 / PY_ONLY=0 @419-420), `control_api_v1/tests/test_sm_contract_parity.py` (same constants @304-305; INV-D table @394-401), fixture `rust/openclaw_core/tests/fixtures/sm_contract_vectors.json`.
- Re-point set: `governance_routes.py:691,701,770,776,932`, `governance_extended_routes.py:206-220`, `paper_trading_wiring.py:145,171,200,224`, `audit_persistence.py:494,497`.
- Runtime (ssh trade-core): `OPENCLAW_LEASE_PYTHON_IPC_ENABLED` NOT in restart_all.sh → API never gets it → lease path = Python local SM today.
