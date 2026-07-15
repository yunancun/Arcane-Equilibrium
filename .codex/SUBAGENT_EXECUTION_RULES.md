# Codex Sub-Agent Execution Rules

Last updated: 2026-07-14
Registry: `.codex/agent_registry_v1.json`

## Dispatch record

Every sub-agent is bound before spawn:

- repo role preset + exact native TOML identity + `work|verification` class + permission
- owned scope and task shape
- exact task prompt, objective, acceptance, hard stops, and required uncertainty
- expected patch or immutable fragment
- context digest and evidence scope
- allowed side effects (normally none)

The bound capsule is a validated `context_artifact_v1`, not a mutable summary.
Its `task_contract_digest` covers normalized task/surface/risk/uncertainty, exact
task-prompt digest, runtime/E2E claim,
side-effect class, objective/scope/acceptance/hard stops, source baseline, direct
interfaces, previous failure, and verdict-relevant `claim_inputs`. The returned
fragment must repeat that exact digest; changing scope, evidence input, or effect
class requires a new admission.

Temporary runtime nicknames are implementation detail. User-facing updates use
`ROLE(type)`.

## Intelligence and context

All native presets set `model_reasoning_effort = "high"`. Consumption is reduced
by routing fewer agents, loading less irrelevant context, and stopping when
evidence closes—not by lowering a role's reasoning ceiling. Do not use runtime
type, prompt length, or budget target as a proxy for intelligence.

The PM-supplied capsule is the starting point, not a ceiling on autonomous source
inspection. Mandatory objective/acceptance/hard-boundary/current-diff facts are
lossless. If the capsule is incomplete, return `NEEDS_CONTEXT` with the exact
missing source; do not guess or silently compress it away.

## Dispatch and hosted-CI economics

Do not admit a speculative sub-agent merely to increase apparent coverage. The
compiler's hard-edge roles remain mandatory, but every optional/adaptive node
must name the decision it can change and why that expected gain exceeds its
context, orchestration, and verification cost. Polling unchanged GitHub state,
duplicating another role's inspection, or asking multiple roles to produce the
same summary is not a decision-changing node.

Exactly one PM-owned publication lane may update a PR head or request an
automated review. Other roles return patches/fragments and never race `push`,
review requests, or CI reruns. Hosted CI is final integration evidence for a
stable, locally verified head; it is not the edit-debug loop. Before publishing,
run the closest feasible local form of the failing/final gate and batch all
known fixes into one head update.

Bind each hosted failure to `head_sha + workflow + job + failing step + failure
fingerprint`. One failure permits diagnosis and a locally verified repair. A
second occurrence of the same fingerprint forbids another publication until
the validation strategy changes, the failure is reproduced locally, or PM
records why the gate is external-only. Never retry an unchanged head. Request
at most one current-head automated review; a review result from an older SHA is
stale. Path-classified jobs and `cancel-in-progress` are mandatory whenever the
workflow supports them; do not bypass them with manual reruns.

Long-running loops checkpoint locally without publishing each iteration. Every
iteration begins from an exact clean feature-branch HEAD. Before staging, the
PM-owned checkpoint lane runs `git_loop_guard.py --phase checkpoint` with the
work item's allowlist and bounded dirty budget; builders/reviewers never stage.
After tests, PM stages exact paths, verifies the index, commits, updates the full
checkpoint SHA, and requires `--phase start` clean PASS before dispatching the
next row. Unowned/pre-staged/binary/oversized dirty state is a recovery stop, not
permission to stash, reset, clean, widen scope, or continue accumulating files.

Publication requires `--phase publish`, one non-force feature-branch push, and
`--phase post-push` exact remote-SHA proof. Merge must bind the reviewed head
with `--match-head-commit`. Branch/worktree deletion is never automatic and
occurs only after verified merge plus Mac/origin/Linux source sync under
`.codex/SYNC.md`.

## Permission enforcement

Registry permissions are binding even when a tool is technically exposed.
Native TOML makes the platform sandbox an additional least-privilege layer:
verification identities are `read-only`; writer identities are
`workspace-write` and still constrained by Registry ownership. Claude saved
workflows use matching generated native names; logical PA/E4 may not be invoked
and relabelled as investigator/verifier after the call.

- Read-only reviewer: no repo edit/stage/commit, PG write, restart, runtime
  mutation, private broker effect, unauthorized contact, memory/report append.
- E1/E1a: task-owned source only.
- E4-writer: test/fixture/test-helper writes only; E4-verifier is read-only.
- PA-design-writer/TW: scoped design/docs writes; PA-investigator is read-only.
- PM: orchestration/governance/closure/approved Adapter intent; no business code.

Every intended read-only verification argv runs only through the role/node-exact
`python3 helper_scripts/maintenance_scripts/agent_governance.py capture-command`
Adapter with the immutable Context and argv after `--`; do not preflight and then
execute a second shell command. Native read-only sandboxing
does not grant service mutation, private/authenticated external contact/effects,
or private broker authority. `public_web_read` is distinct read-only evidence
acquisition: open the public URL and bind citation/capture provenance; tool
availability is a separate platform fact. Rust/source
tests run on Mac. Linux `trade-core` cargo is forbidden to delegated roles;
Linux empirical evidence requires a separately governed, allowlisted read-only
transport/capture. Deploy and broker contact cannot be inferred from visible
runtime paths. `runtime_environment_probe_v1` now exists as a local-only,
non-secret, fail-closed source capability, and the Deploy Adapter independently
reruns and reconciles it; the probe is not remote transport, platform-attested
runtime evidence, deploy readiness, or effect authority. Deploy apply remains
disabled before component invocation until exact rollback binding and a stable
observation-window contract are separately bound and verified. Development-
agent broker/private external contact has no closure-admissible Adapter. Direct
`psql` is also denied until a local-socket/read-only-identity Adapter removes
ambient `psqlrc` and `PG*` routing.

## Independence

- A Builder cannot be the only verifier of its patch.
- E2 does not fix the code it reviews, including typo/lint exceptions.
- OPS does not apply and then postcheck its own mutation.
- BB/IB review but do not contact/effect the broker.
- PM integrates; it cannot erase CC/E3/QA/OPS/venue dissent.

## Completion fragment

Return exactly one `role_fragment_v1` for PM to merge into
`closure_packet_v1`:

- identity: fragment ID, immutable DAG node ID, Registry role, exact native agent,
  node class/permission, payload kind
- the exact admitted `task_contract_digest`
- the exact `context_artifact_digest` plus producer record kind/call reference/
  receipt digest
- work status and gate verdict
- fact/inference/assumption classification + confidence
- non-empty summary, evidence references, concerns, and next owner/action
- actual measured/partial consumption only with platform/external-attested
  telemetry reference + digest, or an honest unavailable reason with no invented
  metrics; closure-only wave-ledger partials remain structural/planned accounting
- a lossless role-specific payload containing any check/contact/side-effect facts

`DONE+FAIL` is valid. `BLOCKED/NEEDS_CONTEXT+PASS` is invalid. NO-OP is a
packet disposition (`NO_CHANGE_NEEDED`), not an overloaded fragment status or
verdict. Packet-level disposition, aggregate checks, side effects, acceptance,
and skips are set only by PM closure; they are not extra fragment fields.

Do not automatically write a role report or append memory. PM may use the
deterministic Report Sink for one durable task closure; immutable dissent remains
referenced.

## Retry and stop

- Missing context: add the exact missing context, then retry.
- API/null failure: one checkpoint-aware relay may resume completed work.
- Same input/model/shape failure: no bare retry; change capability or split.
- Same hosted-CI failure fingerprint twice: freeze PR publication and change the
  local reproduction/validation strategy before any new head.
- Hard policy/external/operator blocker: stop with owner and unblock condition.
- Budget review point: split or return UNVERIFIED; never convert to PASS.

## Evidence truth

Three trust tiers apply independently of evidence class:

- `LOCAL_REPRODUCIBLE`: exact repository/command bytes can be regenerated and
  compared locally.
- `ORCHESTRATOR_BOUND`: canonical call/wave records bind controller-known task,
  context, role, result, retry, and coverage facts.
- `PLATFORM_OR_EXTERNAL_ATTESTED`: runtime, external-policy/outcome, and actual-
  usage facts are attested beyond the local controller.

A record self-digest proves canonical integrity only. It is not a provider/model
signature and cannot upgrade a local or orchestrator record into the third tier.
Every call attempt is retained in the call manifest; the wave record accounts for
admitted nodes, retries, nulls, result fragments, planned input lower bounds,
coverage debt, native identity/class/permission, DAG dependencies/topological
wave, producer generation, and controller-overhead exclusions. Dependencies are
not callable before predecessors finish. When closure reports
orchestrator structural consumption, its wave refs exact-cover every captured
wave; ghost, omitted, extra, or duplicate wave identity is invalid. Closure
recomputes the delegated execution projection from routed plus adaptive
admissions, so rehashing a graph after dropping a node, predecessor edge, or
topological wave remains invalid.

Test reuse requires an exact signature over source/diff/untracked/command/test/
toolchain/lock/OS/arch/env/config/runtime/auth plus TTL. Label `EXECUTED` and
`REUSED` distinctly. Both statuses reference an exact validated command capture; a
reused E4 check additionally needs a hash-pinned eligibility receipt matching
signature, execution evidence, and closure-time TTL. Closure performs trusted
local replay of command captures and rejects a claimed PASS that does not
reproduce or mutates task/whole-repository generation. This deliberately means
capture plus replay until a host verifier exists; one call does not mean one total
execution. `effect_enforcement=repository_policy_only` is not a no-contact proof.
Runtime PASS needs a
`PLATFORM_OR_EXTERNAL_ATTESTED` host/environment/time capture. Raw journal or
systemd Environment/argv output is not reviewer-safe evidence. Source-ready,
runtime-active, and authorized are separate claims.

Generic digests and self-authored summaries do not prove acceptance. Evidence
class must match the claim: unit test is not E2E outcome; source capture is not
runtime; runtime observation is not authority. Repo mutation additionally needs
exactly one task/role/node/scope-bound `repository_change_record_v1` per admitted
writer, in canonical writer order. Writer path scopes are non-empty, disjoint,
and exactly cover routed dirty scope; shared-worktree writers are transitively
serialized. Each receipt binds an owned mutation and the task-wide before/after
generation, forming exact G0 -> G1 -> ... -> Gn links. Gn and every owned after-
state must remain current. One mixed record cannot satisfy two writers;
a snapshot/diff or source-change summary cannot prove causality.
Authority claims bind class + subject + canonical value + source/scope/strength/
expiry + self-digest. Repository authority value must be the deterministic
identity projection of the exact pinned Context bytes; interpreted semantics use
typed claim evidence instead. A verification PASS must be FACT, not low confidence, and
carry no unresolved concerns; otherwise return the honest non-PASS state.

Post-closure durability metrics use `closure_quality_followup_v1` bound to the
immutable closure digest. Reopen/rework/false-closure/realized-value fields are
measured only with caller-trusted platform/external attestation; unknowns remain
scheduled/unavailable rather than zero.

Canonical design and examples:
`docs/agents/development-agent-governance.md`.
