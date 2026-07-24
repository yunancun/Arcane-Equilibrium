# S1 Formal Governance Closure — Wave A Design

**Status**: DESIGN (read-only; PA `design_writer`; no production code / schema /
Registry / test mutated by this doc). Author: PA design over PM decisions.
Branch: `agent/aiml-s1-formal-closure` @ origin/main `fae656cd7`.
Closes S1 `EFFECT_SEAMS_READY` per the delivery protocol requirement that it
"requires governance Registry/router/schema/closure wiring, bypass-negative
tests and disposable apply/rollback/postcheck, not contract prose alone."

This design turns the S1.6B target-host probe (today a *disjoint*,
self-validating harness) into a *closure-admissible effect seam*: a registered
Registry effect adapter, a typed intent, a route branch, a central-validator
delegation, a closure effect binding, a distinct verifier, and an SSHSIG-signed
evidence lane — all additive to, and provably outside, the frozen S0.3 surface.

---

## 0. Frozen S0.3 surface (do NOT touch) and the additive rule

The following are byte-frozen. Every Wave A change stays entirely outside them.

| Frozen artifact | Location | Why it must not move |
|---|---|---|
| `AIML_EFFECT_CLASSIFIER_RULES`, `S0_3_WORK_PACKAGE_ID`, `S0_3_DIRECT_INTERFACES_BY_PHASE`, `S0_3_SIDE_EFFECT_BY_PHASE`, `S0_3_EXACT_OWNED_PATHS`, `S0_3_OWNED_PATH_PREFIXES` | `aiml_gate_receipt_validator.py:127-193` | Exact inputs to `aiml_effect_classifier_digest()` (`:318-328`). Any edit changes the S0.3 classifier identity that the adoption receipt/closure pins. |
| `PROGRAM_SCHEMA_PATHS`, `S0_DEPENDENCY_DIGESTS` | `aiml_gate_receipt_validator.py:48-51, 83-94` | Pinned S0 predecessor identities. |
| `session_attempt_v1.schema.json` (const pins: `work_package_id`, `bootstrap_admission.task_id`, `side_effect_class` enum, `runtime_claim=false`) | `program_code/ml_training/schemas/aiml_gate_receipts/session_attempt_v1.schema.json` | Sealed S0.3 schema; listed in `PROGRAM_SCHEMA_PATHS` and `workflow_contracts.aiml_program_adoption_v1.schema_paths`. |
| `workflow_contracts.aiml_program_adoption_v1` (`selector_digest`, `schema_paths`) | `.codex/agent_registry_v1.json:94-113` | `selector_digest` frozen. |
| `execution_signer_fingerprint` | `.codex/agent_registry_v1.json:116` | S0.3 operator trust root. |
| `_s0_3_work_package_errors`, S0.3 branch of `classify_required_effects` | `aiml_gate_receipt_validator.py:354-447` | S0.3-hardcoded semantic path. |
| `EXPECTED_EXECUTION_SIGNER_IDENTITY/_FINGERPRINT`, `EXECUTION_SIGNATURE_NAMESPACE`, `TRUSTED_EXECUTION_PUBLIC_KEY` | `agent_governance_aiml_trusted_host.py:76-87` | S0.3 signer const; `_verify_execution_signature` default path stays byte-identical. |

**Additive rule**: every S1 artifact is a *new file*, a *new dict key*, a *new
const with a new name*, or a *new branch guarded by a new discriminator*. No
existing frozen line is rewritten. The only edits to existing files are
key/branch *insertions* and one test-assert flip (§3).

---

## 1. Change surface (files touched)

| # | File | Kind of edit | Frozen? |
|---|---|---|---|
| A | `program_code/ml_training/schemas/aiml_gate_receipts/aiml_landing_session_attempt_v1.schema.json` | NEW schema (additive attempt) | n/a |
| B | `program_code/ml_training/schemas/aiml_gate_receipts/target_host_disposable_runtime_probe_intent_v1.schema.json` | NEW typed intent schema | n/a |
| C | `aiml_gate_receipt_validator.py` | `SCHEMA_FILES` +2 keys (`:45`); new sibling validator fn + 2 delegating branches after `:1648`; register `learning_runtime_choice_receipt_target_host_v1` | additive only |
| D | `agent_governance_target_host_choice.py` / `agent_governance_target_host_probe.py` | reconcile "NOT registered / disjoint" prose (`probe:69-74`); no logic change | additive/doc |
| E | `agent_governance_runtime_choice_probe.py:28-34` | reconcile the "the split is…" prose (target-host receipt is now registered) | doc |
| F | `.codex/agent_registry_v1.json` | NEW `effect_adapters.target_host_disposable_runtime_probe_adapter_v1` | additive key |
| G | `agent_governance_routing.py` | `SIDE_EFFECT_CLASSES` +`target_host_probe` (`:41`); surface-consistency rules; `route_task` branch (mirror P0-B `:708-722`) | additive only |
| H | `agent_governance_effects.py` (+ NEW sibling `agent_governance_target_host_effects.py`) | dispatch target-host effect evidence/binding (mirror `p0b_effects` at `effects.py:657,699`) | additive only |
| I | `agent_governance_closure.py` | no logic edit needed — `runtime_contact` gate (`:743-744`) + effect loop (`:206-245`) already generic; binding lands via H | none |
| J | `agent_governance_aiml_trusted_host.py` | `ALLOWED_EXECUTION_KINDS` +1 kind (`:94-101`); NEW S1 signer consts; parameterize `from_bundle`/`_verify_execution_signature` signer-profile (S0.3 default) | additive only |
| K | Tests: `test_agent_governance_target_host_probe.py:640` flip; NEW `test_aiml_landing_session_attempt.py`; NEW `test_target_host_effect_adapter.py`; extend routing/closure/registry structure tests | additive + 1 flip |
| L | `docs/agents/ai-ml-landing-delivery-protocol.md`, `docs/execution_plan/2026-07-19--…landing_plan.md` (LR0B row ~236) | WORM S1.2A vs S8.6 amendment wording | doc |

---

## 2. Additive `aiml_landing_session_attempt_v1` (File A + validator C)

**Purpose**: an S1+ durable attempt row that mirrors `session_attempt_v1` but
*generalizes* the S0.3 const pins and adds an author-declared, cross-checked
effect binding and an explicit closure binding. There is **no S1 landing
classifier** here: the attempt row does not recompute an effect classification;
`required_effects` are author-declared and cross-checked at validation, and the
authoritative effect classification is enforced at the target-host
effect/closure lane. It is a **new schema file** — `session_attempt_v1`
is not edited — with its **own sibling semantic validator**, NOT the
S0.3-hardcoded `_s0_3_work_package_errors` branch.

### 2.1 Field table (delta vs `session_attempt_v1`)

| Field | Type / rule | Relationship to S0.3 |
|---|---|---|
| `schema_version` | const `aiml_landing_session_attempt_v1` | new const |
| `attempt_id … self_digest` (attempt_id, session_id, scope_ref, cohort_epoch, attempt, attempt_key, attempt_phase, status, owner, lease\|read_only_admission phase-conditional, source{branch,worktree,baseline_head,checkpoint_head}, path_manifest, dag_nodes, native_admission, dependency_generations, ci_classifier, created_at, self_digest) | mirror of `session_attempt_v1` (identical shapes) | unchanged mirror |
| `scope_ref.kind` | enum `PROGRAM`\|`LANDING_SCOPE`; `LANDING_SCOPE` **permitted** (S0.3 forbids it for `S0.*`) | GENERALIZED |
| `work_package.work_package_id` | `type:string,minLength:1` (NOT const `AIML-S0.3-…`) | GENERALIZED |
| `work_package.side_effect_class` | enum incl. `repo_write,none,target_host_probe` | GENERALIZED |
| `work_package.runtime_claim` | `type:boolean` — `true` **allowed** (S0.3 pins `false`) | GENERALIZED |
| `bootstrap_admission.task_id` | `type:string,minLength:1` (NOT const `AIML-S0-3-…`) | GENERALIZED |
| `required_effects` | array of `{effect_class, adapter_id, actor_node_id, rollback_contract, independent_postcheck_node_id, status}` — author-declared, cross-checked at validation (`adapter_id` must equal the attempt `adapter_id`; `closure_binding.effect_adapter_id` must match); NOT recomputed from a landing classifier — the authoritative effect classification is enforced at the target-host effect/closure lane, not at this attempt row | NEW (S1 effect binding) |
| `adapter_id` | string; the DAG effect-node adapter identity | NEW |
| `actor_node` | string; the applier node id | NEW |
| `rollback` | string; rollback contract label | NEW |
| `independent_postcheck_node` | string; distinct verifier node id (≠ `actor_node`) | NEW |
| `closure_binding` | object `{closure_packet_digest, effect_receipt_digest, effect_adapter_id}` binding the attempt to its `closure_packet_v1` / effect-receipt | NEW |

`additionalProperties:false`; `required` adds the five S1 fields + `closure_binding`.
Phase-conditional `allOf` (SOURCE_BUILD⇒lease / POST_MERGE⇒read_only_admission)
is copied verbatim from `session_attempt_v1` — those blocks are shape rules, not
S0.3 identity pins.

### 2.2 New sibling validator (in `aiml_gate_receipt_validator.py`)

- Register `"aiml_landing_session_attempt_v1"` in `SCHEMA_FILES` (`:45` block, new key).
- New branch `if schema_version == "aiml_landing_session_attempt_v1":` (added in
  the dispatch chain after the existing `session_attempt_v1` block `:1373-1493`),
  calling a NEW `_aiml_landing_work_package_errors(...)` that mirrors the
  structural checks in `_s0_3_work_package_errors` (`:354-395`) — sorted/unique
  paths, writer-lease binding, path⊆manifest, ≤2 writer nodes, native-admission
  match — but **without** the S0.3 const equalities. It additionally asserts:
  `actor_node ≠ independent_postcheck_node`; `required_effects[*].adapter_id ==
  adapter_id`; `closure_binding` digests are `sha256:`-shaped; `attempt_id`,
  `attempt_key`, `self_digest` recompute via the existing
  `session_attempt_identity_digest` / `artifact_self_digest` helpers (reused,
  unchanged). The S0.3 `_s0_3_work_package_errors` is NOT called on this path.

**Proof it is disjoint from the classifier digest**: the new validator function
is a *reader* of the artifact; it is not referenced by
`aiml_effect_classifier_digest()` (see §7.2). Adding the `SCHEMA_FILES` key and
the branch cannot alter the S0.3 classifier identity.

---

## 3. Register the target-host receipt into the central validator (C, D, E)

Today `learning_runtime_choice_receipt_target_host_v1` is deliberately absent
from `SCHEMA_FILES`; the probe/choice modules self-validate.

**Change (C)**:
1. Add key at `aiml_gate_receipt_validator.py:45` block:
   `"learning_runtime_choice_receipt_target_host_v1":
   "learning_runtime_choice_receipt_target_host_v1.schema.json"`.
2. Add a delegating branch after `:1648` (mirroring the S1.5 component-effects
   block `:1617-1648`), forcing `now`:
   ```
   if schema_version == "learning_runtime_choice_receipt_target_host_v1":
       now_text = _now_text(now)
       if now_text is None:
           errors.append("target-host choice receipt requires now …")
       else:
           import agent_governance_target_host_choice as _th
           errors.extend(_th.validate_target_host_choice_receipt(
               artifact, now=now_text, require_target_host_attested=False))
   ```

**Decision (structure-only at the central gate)**: `require_target_host_attested
=False`. Per CLAUDE.md "the standalone CLI performs offline structure/integrity
checks and cannot authenticate PASS." The central offline gate proves the
receipt is *well-formed* (schema subset, field-set, const identity, OCI
non-satisfiable, BINDING-requires-all-passed, self_digest). The **attested** gate
— `evidence_class==PLATFORM_OR_EXTERNAL_ATTESTED` + embedded governed
`command_capture_v2` (`validate_target_host_choice_receipt` `:636-668`) — is
enforced in the closure/trusted-host lane (§5–§6, `require_target_host_attested
=True`). This preserves the disposable-real vs offline honesty boundary S1.6B
already encodes.

**Disjoint receipt stays disjoint**: `learning_runtime_choice_receipt_v1` (S1.6
Mac stand-in) is NOT registered.

### 3.1 Exact assert lines (grep-confirmed §7.4)

- **FLIP** `tests/structure/test_agent_governance_target_host_probe.py:640`
  from `assert "learning_runtime_choice_receipt_target_host_v1" not in
  validator.SCHEMA_FILES` → `assert … in validator.SCHEMA_FILES` and add
  `assert (validator.SCHEMA_DIR / …).is_file()`.
- **LEAVE** `test_agent_governance_target_host_probe.py:641` (`…_receipt_v1`
  disjoint) unchanged.
- **LEAVE** `test_agent_governance_runtime_choice_probe.py:376` unchanged.

### 3.2 Prose reconciliation (D, E)

- `agent_governance_target_host_probe.py:69-74` and the sibling
  `agent_governance_target_host_choice.py` header claim the harness "is NOT
  registered into the central AIML closure-validator … stays disjoint" and "adds
  NO registry adapter." Reword to: the *self-validating logic* remains, but the
  target-host **receipt schema is now centrally registered (structure-only)** and
  a **dedicated `target_host_disposable_runtime_probe_adapter_v1` is now
  registered** (see §4). The Mac S1.6 receipt (`…_receipt_v1`) remains disjoint.
- `agent_governance_runtime_choice_probe.py:28-34` says "the split is: closure-
  carried seam/identity proof receipts get eager central recognition, while
  intermediate self-contained contract receipts — S1.3, S1.4, S1.6 —
  self-validate." Update to move the target-host receipt into the
  *eager-recognition* set (it is now closure-carried), keeping S1.3/S1.4/S1.6
  Mac stand-ins in the self-validating set.

---

## 4. New Registry effect adapter (F) + the two-notion adapter-id

Add sibling in `.codex/agent_registry_v1.json` `effect_adapters` (mirror
`learning_runtime_deploy_adapter_v1` template `:392-405`):

```
"target_host_disposable_runtime_probe_adapter_v1": {
  "status": "declared_disposable_target_host_probe_gated",
  "owner_session": "S1.6B",
  "authority": "PM/operator approved target_host_disposable_runtime_probe_intent_v1
     for an exact non-root user-scope disposable probe on the bound target host only;
     no production apply, no real service, no system-scope unit, no OCI socket, prod PG untouched",
  "invariant": "non-root + user-scope transient units only; applier != independent
     postcheck verifier; exact rollback + complete teardown with an INDEPENDENT residue
     sweep are machine-enforced; AIML_TARGET_HOST_PROBE is set only by the admitted-intent
     execution path (governed capture-command strips it); real operator SSHSIG attestation
     is the out-of-band trusted-host step",
  "implementation_paths": ["helper_scripts/maintenance_scripts/agent_governance_target_host_choice.py"],
  "component_paths": ["helper_scripts/maintenance_scripts/agent_governance_target_host_probe.py"],
  "intent_schema_path": "program_code/ml_training/schemas/aiml_gate_receipts/target_host_disposable_runtime_probe_intent_v1.schema.json",
  "result_schema_path": "program_code/ml_training/schemas/aiml_gate_receipts/learning_runtime_choice_receipt_target_host_v1.schema.json"
}
```

Both `implementation_paths` and `component_paths` files exist and are <2000
lines (§7.3), satisfying the registry structure test (`test_development_agent_
governance.py:277-284`).

### 4.1 The two `adapter_id` notions (explicit, so reviewers are not confused)

There are two distinct identities, deliberately **not** unified:

- **DAG effect-node identity** = `target_host_disposable_runtime_probe_adapter_v1`
  (the new Registry adapter). This is what the `route_task` effect node is named
  and what the closure `effect_adapter_result_v1`-style wrapper's `adapter_id`
  must equal to match the route.
- **Receipt `probe_scope.adapter_id`** = `learning_runtime_deploy_adapter_v1`
  (S1.5, sealed const in the receipt schema). This names the *underlying S1.5
  deploy adapter that the probe exercises* to run the disposable lifecycle.

**Decision**: KEEP `probe_scope.adapter_id` const = `learning_runtime_deploy_
adapter_v1`; do NOT re-seal the receipt schema. The new adapter is the *effect-
node identity*; the receipt's field names the *exercised deploy adapter*. The
closure binding (§6) cross-checks: wrapper `adapter_id == route node id ==
target_host_disposable_runtime_probe_adapter_v1`, while the embedded typed
receipt keeps `probe_scope.adapter_id == learning_runtime_deploy_adapter_v1`.
This is verified by the validator (`_validate_probe_scope`
`target_host_probe.py:712-713`) and re-asserted in the new closure binding
(§6).

---

## 5. New typed intent (File B) + authorization derivation (decision #5)

`target_host_disposable_runtime_probe_intent_v1` — authorization is **derived
from a validated typed intent**, never from a user-set `AIML_TARGET_HOST_PROBE=1`.

### 5.1 Intent field table

| Field | Type / rule |
|---|---|
| `schema_version` | const `target_host_disposable_runtime_probe_intent_v1` |
| `intent_id` | `sha256:` self-identity |
| `expected_host` | string == `host_identity.expected_host` bound in the receipt (e.g. `trade-core`) |
| `non_root_uid` | const `true` (uid≠0 required) |
| `user_scope_only` | const `true` (systemd `--user` only; no `--system`) |
| `candidate_ids` | array ⊆ `{exact_image_id_oci, content_addressed_fixed_path}` |
| `per_seam_argv` | object seam→argv[]; each seam ∈ the 8 `TARGET_HOST_SEAMS` |
| `throwaway_root` | string under `$XDG_RUNTIME_DIR`; not a `PRODUCTION_PATH_PREFIXES` member |
| `ttl_seconds` | integer ≤ `TTL_CEILING_SECONDS` (3600) |
| `rollback` | object {`atomic_pointer_swap`, `teardown_reset_failed`, `rmtree`} contract labels |
| `applier_node_id` | string |
| `postcheck_node_id` | string; **must differ** from `applier_node_id` |
| `created_at`, `expires_at`, `self_digest` | time + self hash |

`additionalProperties:false`.

### 5.2 Authorization derivation (honest boundary)

The **admitted-intent execution path** (the adapter applier, running on the
bound trusted target host after the route + PM approval admit the intent) is the
only thing that sets `AIML_TARGET_HOST_PROBE=1` — after it has validated the
typed intent against the admitted route/approval. `target_host_available()`
(`probe.py:453-466`) already gates the real seams on that env var; the design
does not weaken it. The governed `capture-command` continues to env-strip
`AIML_TARGET_HOST_PROBE`/`XDG_RUNTIME_DIR` (`probe.py:332,459`), so the flag can
never be smuggled in by a user or by capture — it is set programmatically by the
applier only. No user-facing toggle is added; no capture env stripping is
relaxed.

---

## 6. Routing + closure admission (G, H, I)

### 6.1 Routing (`agent_governance_routing.py`)

1. `SIDE_EFFECT_CLASSES` (`:41`) += `"target_host_probe"`.
2. Surface-consistency rules (mirror `deploy` `:361-366`): `target_host_probe`
   requires `runtime_effect` (and/or `service`) surface + `runtime_claim=true` +
   `risk in {high,critical}`; a bare surface without the class, or the class
   without those surfaces, raises — mirroring the deploy asymmetry. **No new
   `KNOWN_SURFACES` entry needed** (reuse existing `runtime_effect`/`service`/
   `runtime`; `target_host` is intentionally not a surface — §7.5).
3. `route_task` branch (mirror P0-B `:703-722`) inside the existing
   `if operations_needed:` block (`target_host_probe` must be OR-ed into
   `operations_needed` at `:594`):
   ```
   ops_preflight (OPS)
     → pm_target_host_approval (PM)               # authorizes the exact intent; not verification
       → target_host_disposable_runtime_probe_adapter_v1 (kind=effect_adapter,
             intent_schema_version=target_host_disposable_runtime_probe_intent_v1,
             result_schema_version=learning_runtime_choice_receipt_target_host_v1)
         → ops_postcheck (OPS)                     # INDEPENDENT residue sweep, distinct process/capture (§ 6.3)
   ```
   Selection is keyed by `side_effect_class == "target_host_probe"` (a clean
   discriminator; unlike P0-B it needs no `claim_inputs` selector because the
   effect class itself is unambiguous).

### 6.2 Closure effect binding (`agent_governance_effects.py` + new sibling H)

The closure evidence loop (`closure.py:206-245`) already routes `kind ==
"effect_adapter_result_v1"` to `validate_effect_evidence`, which dispatches to
`p0b_effects` by `adapter_id` (`effects.py:657`). Add a **parallel dispatch**
for the target-host adapter — a new sibling module
`agent_governance_target_host_effects.py` mirroring `agent_governance_p0b_
effects.py`, with `validate_target_host_effect_evidence` and
`validate_target_host_effect_binding`, dispatched from `effects.py` at `:657`
(evidence) and `:699` (binding) keyed by
`adapter_id == "target_host_disposable_runtime_probe_adapter_v1"`.

**What the `closure_packet_v1` must bind for this effect (exact list):**

1. Route node `target_host_disposable_runtime_probe_adapter_v1` present,
   `mandatory=true`.
2. Exactly one evidence item, `kind="effect_adapter_result_v1"`, `scope="runtime"`,
   `adapter_id == target_host_disposable_runtime_probe_adapter_v1` (the route
   node id), whose embedded/attached typed receipt is a valid
   `learning_runtime_choice_receipt_target_host_v1` with `status="PASS"`,
   `evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED"`, `probe_scope.adapter_id ==
   learning_runtime_deploy_adapter_v1`, validated via
   `validate_target_host_choice_receipt(receipt, now=…, require_success=True,
   require_target_host_attested=True)`.
3. `side_effects.runtime_contact = true` (`closure.py:743-744` then requires a
   typed runtime/effect receipt — the target-host effect receipt satisfies
   `valid_effect_receipts`).
4. Authority cross-binding to the typed intent: a `claim_evidence` authority_ref
   `source == "target_host_disposable_runtime_probe_intent_v1:<intent_id>"` whose
   `digest == receipt intent binding` and whose `observed_at ≤ effect start`
   (mirror the deploy intent binding `effects.py:726-741`).
5. The **distinct** `ops_postcheck` fragment binds its own runtime evidence
   (residue sweep) — verifier node ≠ applier node (§6.3).
6. Trusted-host attestation: the typed receipt `self_digest` is consumed by the
   injected `execution_attestation_verifier` (§6.4) — offline packet bytes alone
   never PASS.

`runtime_contact` (`closure.py:743-744`) and the effect-loop (`:206-245`) are
already generic, so `agent_governance_closure.py` needs **no logic edit**; the
binding lands entirely in the new `effects.py` dispatch + sibling module (H).

### 6.3 Distinct verifier (decision #7)

Applier and independent verifier must differ by **role + process + capture**,
not two node-id strings:

- Applier node = the `target_host_disposable_runtime_probe_adapter_v1` effect
  node (OPS/adapter identity that runs the seams + produces the applier receipt
  with `independent_postcheck=DEFERRED`).
- Verifier node = `ops_postcheck` (OPS/QA), a **separate ssh session/process**
  that re-observes every seam (unit `NoSuchUnit`, cgroup gone, netns gone, temp
  gone) and produces **its own** governed `command_capture_v2`. The choice
  receipt earns `independent_postcheck=PASS` and `BINDING` only when this
  distinct capture is attached (`attach_independent_postcheck`,
  `choice.py`). The closure binding asserts `applier_node_id !=
  postcheck_node_id` (already an intent field §5.1) and that the two capture
  digests differ.

### 6.4 SSHSIG-signed evidence (decision #8 — reuse S0.3 primitive, no new crypto)

Reuse `agent_governance_aiml_trusted_host._verify_ssh_signature` **unchanged**
(it already takes `identity`/`namespace` kwargs `:210-211`). Additive steps in
`agent_governance_aiml_trusted_host.py`:

1. `ALLOWED_EXECUTION_KINDS` (`:94-101`) += `"learning_runtime_choice_receipt_
   target_host_v1"` — the S1 target-host evidence kind. (This frozenset is NOT a
   frozen S0.3 classifier input; decision #8 explicitly sanctions the add.)
2. NEW S1 signer consts (new names — do NOT repoint S0.3):
   `EXPECTED_S1_TARGET_HOST_SIGNER_IDENTITY = "aiml-s1-target-host-operator-v1"`,
   `S1_TARGET_HOST_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s1-target-host"`,
   `EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT = "<operator-provides>"`,
   `S1_TRUSTED_TARGET_HOST_PUBLIC_KEY = "<operator-provides>"`.
3. PARAMETERIZE the bundle verifier: give `AuthenticatedExecutionEvidenceIndex.
   from_bundle` and `_verify_execution_signature` an optional `signer_profile`
   (identity/namespace/fingerprint/public-key) **defaulting to the S0.3 consts**
   — so the S0.3 adoption path stays byte-identical and green, and an S1
   target-host profile becomes selectable. The signed `trusted_execution_bundle`
   entry for the target-host effect binds: `source_head`, host identity, intent
   digest, effect result (`learning_runtime_choice_receipt_target_host_v1`
   `self_digest`), `target_host_capture_digest`, cleanup postcheck digest,
   observed/expiry time, verifier identity.
4. **Honest boundary**: the *actual* operator SSHSIG signing is an out-of-band
   trusted-host step (exactly like S0.3's `aiml-trusted-finalize` — the matching
   private key is deliberately absent from source). Wave A builds the source
   machinery + verification + bundle structure; the closure PASS's trusted
   attestation is enforced through the injected `execution_attestation_verifier`
   (`closure.py:67,152` → `AuthenticatedExecutionEvidenceIndex.verify`). Offline,
   the receipt self_digest proves integrity only, never authenticity.

---

## 7. Self-verification (run and recorded)

### 7.1 Baseline AST parse (all touched modules parse clean)

```
$ python3 -c "import ast; …"
AST OK program_code/ml_training/aiml_gate_receipt_validator.py 1653 lines
AST OK helper_scripts/maintenance_scripts/agent_governance_routing.py 798 lines
AST OK helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py 474 lines
AST OK helper_scripts/maintenance_scripts/agent_governance_target_host_choice.py 1273 lines
AST OK helper_scripts/maintenance_scripts/agent_governance_target_host_probe.py 1541 lines
AST OK helper_scripts/maintenance_scripts/agent_governance_closure.py 795 lines
```

### 7.2 Adding a `SCHEMA_FILES` key does NOT change `aiml_effect_classifier_digest()`

```
$ python3 -c "import aiml_gate_receipt_validator as v; print(v.aiml_effect_classifier_digest())"
classifier_digest BEFORE: sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc
SCHEMA_FILES referenced in classifier digest?: False
```

Reason: `aiml_effect_classifier_digest()` (`:318-328`) hashes only
`{effect_rules, work_package_id, direct_interfaces_by_phase, side_effect_by_phase,
exact_owned_paths, owned_path_prefixes}` — none of which is `SCHEMA_FILES`,
`_load_schema`, or any S1 branch. `SCHEMA_FILES` is consumed only by
`_load_schema` (`:1080-1084`) for schema *lookup*, not by any classifier input.
Therefore the digest stays `…d0ddbc` after the +2 keys. (This must be re-asserted
by a test that pins the exact string — §8.)

### 7.3 New adapter paths exist; both target-host modules <2000 lines

```
EXISTS  helper_scripts/maintenance_scripts/agent_governance_target_host_choice.py   (1273)
EXISTS  helper_scripts/maintenance_scripts/agent_governance_target_host_probe.py    (1541)
EXISTS  program_code/ml_training/schemas/…/learning_runtime_choice_receipt_target_host_v1.schema.json
ABSENT(expected-new) …/target_host_disposable_runtime_probe_intent_v1.schema.json
```
Both modules ≤2000 (registry structure-test cap `MAX_FILE_LINES=2000`). The new
intent schema is correctly absent today (created by Wave A). The registry test
(`test_development_agent_governance.py:277-284`) asserts only
`implementation_paths`/`component_paths` `.is_file()` — both exist — and does not
require `intent_schema_path`/`result_schema_path` to pre-exist.

### 7.4 Exact assert lines (grep-confirmed)

```
test_agent_governance_target_host_probe.py:640  → FLIP  (…_target_host_v1 not in → in SCHEMA_FILES)
test_agent_governance_target_host_probe.py:641  → LEAVE (…_receipt_v1 disjoint)
test_agent_governance_runtime_choice_probe.py:376 → LEAVE (…_receipt_v1 disjoint)
```

### 7.5 Insertion-point map (file:line, from baseline)

| Insert | File:line |
|---|---|
| `SCHEMA_FILES` +2 keys | `aiml_gate_receipt_validator.py:45` |
| new sibling attempt validator branch | after `:1493` (post `session_attempt_v1` block) |
| target-host receipt delegating branch | after `:1648` |
| `SIDE_EFFECT_CLASSES` += target_host_probe | `agent_governance_routing.py:41` |
| surface-consistency rules | `agent_governance_routing.py:361-366` neighborhood |
| `operations_needed` OR target_host_probe | `agent_governance_routing.py:594` |
| route branch | mirror `:703-722` |
| effects dispatch (evidence / binding) | `agent_governance_effects.py:657 / :699` |
| `ALLOWED_EXECUTION_KINDS` +1 | `agent_governance_aiml_trusted_host.py:94-101` |
| new S1 signer consts + signer-profile param | `agent_governance_aiml_trusted_host.py:76-87, 257-360` |
| new adapter | `.codex/agent_registry_v1.json:405` (after `learning_runtime_deploy_adapter_v1`) |
| prose reconcile | `target_host_probe.py:69-74`, `runtime_choice_probe.py:28-34` |

### 7.6 Editing `PROGRAM_GOVERNANCE_PATHS` files is safe (§13 C7)

Editing `aiml_gate_receipt_validator.py`, `agent_governance_routing.py`, and
`.codex/agent_registry_v1.json` — all members of `PROGRAM_GOVERNANCE_PATHS`
(`aiml_gate_receipt_validator.py:95-116`) — does **not** invalidate the sealed
S0.3 program-adoption receipt. `_program_adoption_receipt_errors` compares the
adoption manifest as **path LISTS, not file content**; the S0.3 receipt's blob
digests bind to a historical `merge_head` that S1 commits do not rewrite; and the
adoption fixture derives its path identities via `canonical_digest(path_string)`,
so appending `SCHEMA_FILES` keys / a routing branch / a Registry effect-adapter
key changes none of the hashed inputs. This is confirmed empirically: after all
Wave A edits, `test_aiml_gate_receipt_validator.py` and
`test_agent_governance_aiml_adoption.py` stay green and
`aiml_effect_classifier_digest()` stays `sha256:1cf8…d0ddbc` (§7.2).

---

## 8. New / changed tests

| Test | Asserts |
|---|---|
| `test_agent_governance_target_host_probe.py:640` (FLIP) | receipt now `in SCHEMA_FILES` + schema file `.is_file()`; `:641` unchanged |
| `test_aiml_landing_session_attempt.py` (NEW) | **positive**: a well-formed `aiml_landing_session_attempt_v1` with `LANDING_SCOPE` scope, generalized work_package, `runtime_claim=true`, `required_effects[*].adapter_id==adapter_id`, `actor_node≠independent_postcheck_node`, valid `closure_binding` → `[]`. **negatives**: applier==postcheck; `required_effects.adapter_id` mismatch; S0.3-hardcoded branch never invoked (call `_s0_3_work_package_errors` is not on this path); tampered `self_digest`/`attempt_id`. |
| `test_target_host_effect_adapter.py` (NEW) | registry adapter present with correct impl/component/intent/result paths (mirror `test_agent_governance_p0b_effect_adapter.py:123-160`); `route_task({side_effect_class:target_host_probe,…})` yields the exact node chain `ops_preflight→pm_target_host_approval→target_host_disposable_runtime_probe_adapter_v1(effect_adapter)→ops_postcheck`; generic deploy/runtime does NOT select it; closure consumes the effect receipt (runtime_contact PASS) with intent cross-binding; **bypass-negatives**: wrapper `adapter_id≠route node id`; receipt `require_target_host_attested=True` rejects a `STRUCTURAL_ONLY` synthesis; `probe_scope.adapter_id` re-sealing rejected; applier==verifier capture; missing distinct postcheck capture. |
| `test_development_agent_governance.py` (EXTEND) | new adapter iterated by the existing `.is_file()` loop (`:277-284`) — no new assertion required, but add an explicit line binding the new adapter's four paths. |
| `test_aiml_gate_receipt_validator.py` (EXTEND) | pin `aiml_effect_classifier_digest() == sha256:1cf8…d0ddbc` AFTER the `SCHEMA_FILES` +2 keys (regression guard that the additive keys did not move the S0.3 identity). |
| Trusted-host test (EXTEND `test_agent_governance_aiml_trusted_host.py`) | S0.3 bundle path unchanged (default signer profile); NEW S1 target-host kind accepted in `ALLOWED_EXECUTION_KINDS`; S1 signer-profile bundle verifies with the S1 identity/namespace and is rejected under the S0.3 profile (domain separation). |

**Bypass-negative discipline**: every fail-closed path (unrouted adapter,
adapter-id spoof, structural-only masquerade, applier==verifier, intent expiry,
env-var smuggling, re-sealed receipt scope) has an explicit negative test that
must actually raise — not a rubber stamp.

---

## 9. WORM staging amendment (L) — S1.2A vs S8.6 (decision #9)

The terminal WORM rule must **not** be silently downgraded. Split the concept:

- **S1.2A — external-capable source Adapter (this sprint)**: build the
  `terminal_receipt_sink_v1` Adapter's *external-capable source machinery* — the
  typed append intent/result/readback-ACK contracts, the disposable local WORM
  emulation (chmod 0o444 immutable content-addressed records, idempotent dedup,
  distinct-actor readback ACK) that already exist — and explicitly document that
  **no external WORM destination is bound and no route/closure effect is injected
  before S8.6**. This is a source/contract deliverable only.
- **S8.6 — external binding / effect (later)**: the *actual* external immutable
  WORM append to an out-of-repo destination, the fresh full-runtime identity
  validation, and the terminal receipt stored outside the repo so it creates no
  new head. The terminal WORM *rule* (immutable/append-only, dedicated actor,
  idempotency key, independent readback ACK, stored outside the repo) is
  preserved verbatim.

### 9.1 Amendment wording (design, not applied by this PA doc)

- `docs/agents/ai-ml-landing-delivery-protocol.md:148-149` (S1.2 bullet): append
  a clarifying clause — "S1.2 delivers the *external-capable source* Adapter
  (typed append/readback contracts + disposable local WORM emulation) as
  **S1.2A**; the external immutable destination binding and terminal effect
  remain **S8.6** and are not routed or closure-bound before then." Do not alter
  the S8.6 terminal-state text (`:274-303`).
- `docs/execution_plan/2026-07-19--…landing_plan.md` LR0B row (`:236`, "Terminal
  receipt append"): keep the row's requirement text unchanged; add a footnote —
  "Source machinery (intent/result/ACK + disposable local WORM) lands in S1.2A;
  the external immutable/WORM destination and terminal append are S8.6. The
  terminal WORM rule is not relaxed." And extend `:245-247` ("current generic
  deploy apply remains disabled…") with a parallel sentence that the external
  WORM effect remains unbound until S8.6.

No terminal-state or immutability language is weakened; the split is purely
"source-buildable now" vs "operator/external-bound later," matching how S1.5/
S1.6B already separate disposable-real source seams from real effects.

---

## 10. Terminal-state analysis (achievable now vs operator-gated)

> **Historical design analysis.** The operator and target-host gates described
> below were completed on 2026-07-24. Section 14 is the authoritative current
> state and supersedes this section's terminal wording.

**Achievable source-side now (Wave A)**:
- Additive `aiml_landing_session_attempt_v1` schema + sibling validator.
- Central-validator structure-only registration of the target-host receipt
  (`require_target_host_attested=False`).
- New Registry effect adapter + typed intent schema.
- `route_task` branch + `side_effect_class=target_host_probe` + surface rules.
- Closure effect binding (effects.py dispatch + sibling module) with
  `runtime_contact=true`, intent cross-binding, distinct-verifier requirement.
- SSHSIG source machinery: new evidence kind + parameterized signer profile +
  new S1 consts (names reserved; fingerprint/public-key are operator inputs).
- Bypass-negative tests, additive-attempt positive/negative, register-flip,
  route/closure/registry structure tests.
- Prose reconciliation + WORM S1.2A/S8.6 amendment wording.

**Operator-gated (cannot be self-produced source-side)**:
- **Actual operator SSHSIG signing** of a live target-host `trusted_execution_
  bundle` (the S1 private key is deliberately absent, like S0.3). Until the
  operator signs, the closure PASS's trusted attestation cannot be authenticated
  — the offline gate proves structure only.
- **External S3 WORM configuration/binding** (S8.6): the out-of-repo immutable
  destination. Not in scope for Wave A by design (§9).
- A live trade-core probe run producing a real
  `PLATFORM_OR_EXTERNAL_ATTESTED` receipt + governed `command_capture_v2` (the
  disposable-real effect itself is an on-host OPS execution, not a source edit).

**Realistic terminal state**: `S1_ENGINEERING_CLOSED_EXTERNAL_WORM_BINDING_
PENDING` — the full governance seam (Registry/router/schema/closure wiring +
bypass-negative tests + disposable apply/rollback/postcheck contracts) is
source-landed and green, but `EFFECT_SEAMS_READY` reaches *fully attested* only
when (a) the operator SSHSIG-signs the target-host execution bundle and (b) the
external WORM destination is configured at S8.6. Absent those two operator
actions, the honest terminal is engineering-closed with external WORM binding
and live attestation explicitly pending — never a forced or faked PASS.

---

## 11. Open questions for PM (residual ambiguity)

> **Resolved.** Section 13 records the build-time decisions and section 14
> records the final runtime/signing resolution. These questions are retained
> only as design history.

1. **Effect-receipt shape**: does the closure evidence carry the typed
   `learning_runtime_choice_receipt_target_host_v1` *embedded inside* an
   `effect_adapter_result_v1` wrapper (chosen here, mirroring the deploy
   wrapper's `receipt` field), or a purpose-built
   `target_host_effect_result_v1` like P0-B's dedicated result schema? This doc
   assumes the wrapper-embeds-typed-receipt shape (least new schema). Confirm, or
   direct a dedicated result schema.
2. **Signer-profile parameterization vs sibling index**: §6.4 parameterizes
   `AuthenticatedExecutionEvidenceIndex.from_bundle` with an S0.3-default signer
   profile. If PM prefers zero touch to that class, the alternative is a sibling
   `S1TargetHostExecutionEvidenceIndex` (more code, stricter isolation). Confirm
   the parameterize-with-default choice.
3. **`aiml_landing_session_attempt_v1` issuance owner**: which session first
   *emits* this attempt row (S1.6B closure, or a new S1-formal session)? The
   schema/validator are session-agnostic, but the `closure_binding` needs a
   concrete first producer for the acceptance test fixture.
4. **S1 signer fingerprint/public-key**: operator must provide the S1 target-host
   SSHSIG public key + fingerprint before the trusted-host S1 profile can verify a
   real bundle; the const names are reserved but their values are operator inputs.
5. **`target_host_probe` risk floor**: §6.1 proposes `risk in {high,critical}`
   mirroring P0-B. Confirm, or set a distinct floor for target-host probes.

---

## 13. PM Corrections after CC + E2 architecture gate (AUTHORITATIVE — override §4.1/§6.1.2/§6.2/§11 where they conflict)

CC verdict: constitutionally sound to build; frozen S0.3 surface independently confirmed untouched (`aiml_effect_classifier_digest()` = `sha256:1cf8…d0ddbc` reproduced; `SCHEMA_FILES` proven non-hashed). E2 verdict: not buildable as-drafted — one P0 + two P1 + P2 items. The following PM corrections are the build authority:

- **C1 (E2 P0-1 — REVERSES open-q1 / PM-resolution #1): dedicated result schema, NOT the `effect_adapter_result_v1` wrapper.** `effect_adapter_result_v1` is `additionalProperties:false`, pins `adapter_id` const `deploy_adapter_v1`, and has only a scalar `receipt_digest` — there is no embeddable receipt object and the adapter_id cannot be the target-host adapter, so reusing it is unbuildable and would route to the generic deploy validator. **Create a dedicated `target_host_effect_result_v1.schema.json`** mirroring `.codex/schemas/p0b_alr_rollforward_effect_result_v1.schema.json`: `additionalProperties:false`, `adapter_id` const == `target_host_disposable_runtime_probe_adapter_v1` (its own route-node id), a field carrying the typed `learning_runtime_choice_receipt_target_host_v1` (or binding it by its `self_digest`), `source_head`, `applier_node_id`, `postcheck_verifier_node_id`, self-digest. It is dispatched by a new sibling `agent_governance_target_host_effects.py` (mirror `agent_governance_p0b_effects.py`), keeping `agent_governance_closure.py` core edit-free. Register the dedicated result in `SCHEMA_FILES` + the Registry adapter's `result_schema_path`.
- **C2 (CC P2-1 reconciled with C1): ONE authenticated bundle entry.** The dedicated `target_host_effect_result_v1` is the single trusted-bundle-authenticated effect receipt (its `receipt_digest` transitively covers the embedded typed choice receipt). Do NOT add `learning_runtime_choice_receipt_target_host_v1` as a separate `ALLOWED_EXECUTION_KINDS` entry (that would be an unconsumed-entry rejection). Add only the dedicated result's kind to the S1 evidence-kind set if the execution-attestation path needs it; otherwise rely on the generic effect-receipt authentication (verify which, mirroring P0-B).
- **C3 (E2 P1-2): FORWARD-only surface rule.** Implement ONLY `effect==target_host_probe ⇒ requires runtime_effect/service surface + runtime_claim=true + risk∈{high,critical}`. Do NOT implement the reverse "a bare runtime_effect/service surface without the class raises" rule — `runtime_effect`/`service` are SHARED `OPERATION_SURFACES`; a reverse rule regresses existing deploy/ops routing.
- **C4 (E2 P1-3): strict attestation is a MANDATORY bypass-negative.** The sibling `agent_governance_target_host_effects.py` MUST validate the embedded choice receipt via `validate_target_host_choice_receipt(receipt, now=…, require_success=True, require_target_host_attested=True)`. Add a bypass-negative test proving a STRUCTURAL_ONLY / bare-digest / non-attested receipt is REJECTED at the effect/closure lane (the central offline gate stays `require_target_host_attested=False`, so the strict gate here is the only real enforcement — it must be tested).
- **C5 (CC P2-2): skip the redundant `operations_needed` insertion** at `routing.py:594` — the surface rule already sets it via `runtime_claim=true`. Do not add a second authorization path.
- **C6 (E2 P2-4): the new sibling attempt-validator MUST reject `session_id` beginning `"S0."`** (mirror the `aiml_gate_receipt_validator.py:1375` guard) so the permissive S1 `aiml_landing_session_attempt_v1` cannot re-express an S0.3 attempt with relaxed pins.
- **C7 (E2 P2-5): extend the frozen-surface proof.** Editing `aiml_gate_receipt_validator.py` / `agent_governance_routing.py` / `.codex/agent_registry_v1.json` (all in `PROGRAM_GOVERNANCE_PATHS`) is safe: `_program_adoption_receipt_errors` compares manifest PATH LISTS not content; the S0.3 adoption receipt's blob digests bind to a historical `merge_head` that S1 commits do not rewrite; the fixture uses `canonical_digest(path_string)`. State this in §7.
- **C8 (E2 P2-6): housekeeping.** Add `agent_governance_target_host_effects.py` (+ any new module) to `helper_scripts/SCRIPT_INDEX.md`; new module is glob-subject to the ≤2000-line cap; split/rename the flipped `test_target_host_receipt_is_not_registered_in_central_validator` (post-`:640`-flip its name is misleading).

Everything else in the design (frozen-surface additivity, dispatch separation, central-gate structure-only, two-notion adapter-id, registry/route/closure wiring, SSHSIG S1 domain separation, additive attempt schema, WORM S1.2A/S8.6 split, terminal `S1_ENGINEERING_CLOSED_EXTERNAL_WORM_BINDING_PENDING`) is confirmed SOUND by CC + E2 and stands.

---

## 14. Final runtime and signing resolution (AUTHORITATIVE, 2026-07-24)

This section supersedes the terminal/open-question wording in §§6, 10, 11 and
the last sentence of §13.

- Final H_effect:
  `45a854fa6638aa0be677a2b705f42fe8f417ac95`.
- The real executor is an intent-bounded `python3 -E` child. It ignores
  `PYTHON*`/`PYTHONPATH` injection without excluding the target host's
  user-site `psycopg2`; the parent never opens the probe gate.
- Linux `trade-core` revalidated the still-fresh, source/schema-identical
  six-class S1.5 receipt
  (`sha256:ab63d9db3682e94be195446e4e4d9a586d1ef327427547d88347d934914b140f`)
  and emitted a fresh eight-seam S1.6 effect
  (`sha256:9f8f40b15598822544f0dd8618429ae3c6c2ac2b153d8b3acd70094b73fffd99`),
  with `binding=BINDING`, exact rollback/postcheck, and zero residue.
- The S1 signer reuses the adopted S0.3 trust root with identity
  `aiml-s1-target-host-operator-v1` and namespace
  `arcane-equilibrium-aiml-s1-target-host`. Operator fingerprint
  `SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ` signed the canonical bundle;
  an independent `ssh-keygen -Y verify` passed.
- Closure digest:
  `sha256:eeef47cca1bcbfd44fb917759539b6afd06610669ec65a3be9e30b27a1f46de1`.
  All artifacts are durable in
  `docs/execution_plan/ai_ml_landing/receipts/S1-closure-fix-2026-07-24/`.
- Current state: `S1_CLOSURE_AUTHENTICATED_PENDING_MERGE`. The remaining
  publication gates are exact-head Codex review, required CI, PR #115 merge,
  final `S1_CLOSED` ledger projection, and three-way synchronization.
- External Object-Lock execution remains S8.6 and is not an S1 blocker. All
  nine authority grants remain false.
- Final adversarial closure repaired four additional P1s: inline caller
  previews are byte-bounded while the complete match manifest remains
  digest-bound, and the target-host driver binds `--source-head` to the exact
  clean worktree `HEAD` before any effect. The finalization result now captures
  `evaluated_at` after trusted evaluation, so it cannot predate a Context
  source's validity window; immediate and receipt-time historical replay both
  pass. The finalizer regression now matches the required governance CI glob,
  and the job's 10-minute budget prevents a mechanically green full gate from
  being cancelled at the former five-minute ceiling.
