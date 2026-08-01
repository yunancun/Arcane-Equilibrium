# GPT-5.6 Multi-Agent Efficiency Remediation TODO

Status: `SOURCE_REMEDIATION_COMPLETE_WITH_EXTERNAL_LIMITS`

Task ID: `GPT56-MULTIAGENT-EFFICIENCY-REMEDIATION-20260730`

Baseline: `3839e6e8267ac6abc779f41bcdc617e50beab97d`

Owner: `PM`

Scope: Development-Agent Governance Module only. This work never grants runtime,
deploy, PostgreSQL, broker, Decision Lease, order, or trading authority.

## Why this exists

Two recent AI/ML development sessions exposed an orchestration-amplification
failure mode:

| Session | Elapsed | Platform total tokens | Cached input | Orchestration |
|---|---:|---:|---:|---|
| 2026-07-15..16 | 19h16m | 302.7M | 296.4M | 16 spawns, 418 waits, 72 follow-ups, 12 compactions |
| 2026-07-19 | 4h22m | 105.7M | 103.8M | 18 spawns, 191 waits, 24 follow-ups, 4 compactions |

The dominant cost was repeated sampling over a 100k+ context, not output size.
Finite/no-delta rules added after those sessions reduce semantic continuation,
but actual provider consumption, history propagation, waits, and execution-surface
identity are still not closed by one enforceable Interface.

## Definition of done

All rows below must be `DONE` or carry an explicit `EXTERNAL_LIMIT` whose missing
platform capability is machine-detectable. Completion additionally requires:

1. one supported configuration path and one authoritative execution-policy
   Interface;
2. RED -> GREEN behavioral tests for every implementation row;
3. no direct/full-history fork admitted by default;
4. no inherited `max`/`xhigh` reasoning outside an explicit critical allowlist;
5. aggregate call/wait/no-delta/concurrency/depth counts are enforced before
   the next admitted action; unsupported deadline/cancellation remains an
   explicit host `EXTERNAL_LIMIT`;
6. exact history selection and hot-memory limits enforced structurally;
7. ordinary tasks cannot silently enter the 13-axis Full Audit;
8. governance validation, renderer drift checks, and focused test suites green;
9. an A/B evaluation command and result schema ready for platform-attested runs;
10. no unrelated source/runtime/effect mutation.

## Remediation ledger

| ID | Priority | Status | Problem | Required change | Acceptance |
|---|---:|---|---|---|---|
| `MAE-001` | P0 | `EXTERNAL_LIMIT_HOST_DURATION_TOKEN` | Workflow budgets are planned prompt lower bounds, not an aggregate session cap. | Add one `execution_budget_policy_v1` to route/context/wave receipts with count/state caps and explicit duration/platform-token capability status. Budget exhaustion is terminal and never PASS. | Count/state admission and exact event coverage are enforced; this host exposes no governed duration or provider-token cancellation Adapter. |
| `MAE-002` | P0 | `EXTERNAL_LIMIT_CODEX_HISTORY_ATTESTATION` | History propagation is prose-only; `fork_turns=all` caused large context duplication. | Bind normalized history mode, source thread, boundary turn, and ephemeral state in requested-agent/call records. Default to `none`; full/partial history requires an explicit reviewed exception. | Saved workflows enforce exact history records; Codex-native history/fork remains advisory until a host receipt attests the selected boundary. |
| `MAE-003` | P0 | `EXTERNAL_LIMIT_HOST_WAIT_CANCEL` | Repeated waits/follow-ups can create hundreds of new model turns. | Add aggregate `max_wait_cycles` and `max_no_delta_wakeups`; one watcher owns a wave. Represent call/wave deadline and cancellation capability truthfully. | Ledger events stop supported wait/no-delta admission at the cap; no supported host wait/deadline cancellation Adapter is available. |
| `MAE-004` | P0 | `DONE` | All 22 custom agents are fixed to `high`, while direct spawns may inherit root `max`. | Add role-specific GPT-5.6 model/effort policy. Terra/medium serves read-heavy support; Sol/high is limited to hard reasoning/review; `max`/`xhigh` needs an explicit critical node. | Native and saved-workflow identities resolve an exact Registry tier and reject caller or session inheritance. |
| `MAE-005` | P0 | `EXTERNAL_LIMIT_NATIVE_SELECTOR_ATTESTATION` | Native identity and budget enforcement vary by execution surface; a saved workflow cannot self-authorize data-dependent nodes discovered after its Context was compiled. | Add `execution_surface_profile_v1` with native-selector, telemetry, deadline, fork, and concurrency capabilities. Required-role closure fails closed on degraded identity. Full Audit stages discovered claim verification/fix/review as debt until a fresh host-attested exact DAG is compiled. | Degraded surfaces cannot close mandatory roles. The saved Full Audit exact-covers only 13 axes + seam and makes zero dynamic verifier/writer calls; the later host phase remains external pending a supported native-selector receipt. |
| `MAE-006` | P0 | `DONE` | Project config relies on legacy `max_threads` and undocumented `max_depth`. | Use `max_concurrent_threads_per_session`; make recursion policy explicit and receipt-validated rather than config folklore. | Current config validates and execution-lineage admission enforces spawn depth independently of undocumented config. |
| `MAE-007` | P1 | `DONE` | `active_state` can load the entire 44.8KB AI/ML board into many roles. | Select exact task ID/row plus direct dependency rows and digest those bytes. | Context compiles the exact active TODO projection; unrelated rows do not alter the admitted projection digest. |
| `MAE-008` | P1 | `DONE` | `history_on_demand` is declared but unreachable in the Context compiler. | Add exact `history_refs` selection with safe path/section/digest validation. | At most four repository-local safe H2 sections are byte/digest-bound; whole-glob and unselected history fail closed. |
| `MAE-009` | P1 | `EXTERNAL_LIMIT_MEMORY_PROMOTION_ATTESTATION` | Seven active role memories exceed the 300-line hot target and contain stale ledgers. | Archive dated task records; retain durable lessons and topical pointers only; add structural limits. | All 18 hot views, exact unique role roster, and archive lineage pass; promotion is zero-mutation unless a non-serialized host verifier authenticates exact typed external authority. |
| `MAE-010` | P1 | `DONE` | Budget envelope is chosen before the final required-node projection. | Select/promote the envelope after DAG construction, or return an executable partition plan. | Route chooses the envelope after required-node construction and emits an executable bounded partition when direct admission is unavailable. |
| `MAE-011` | P1 | `EXTERNAL_LIMIT_RECALL_AUTHORITY` | Full Audit default `adaptive_shadow` executes all 13 axes while appearing reduced. | Keep the complete audit as the safe default; permit genuinely reduced adaptive selection only with task-bound recall/non-inferiority authority. | Workflow and canonical skill execute only full 13-axis mode; every reduced set rejects before calls until an out-of-band host verifier authenticates recall non-inferiority. |
| `MAE-012` | P1 | `DONE` | Read-only operations review schedules preflight and postcheck without an intervening effect. | Collapse to one `ops_observation` for read-only/source lanes; keep two nodes only around an admitted effect. | Read-only/service review uses one observation; admitted effects retain distinct preflight and postcheck nodes. |
| `MAE-013` | P1 | `DONE` | Repeated universal contract prose inflates every custom-agent prompt. | Centralize common operating rules behind one generated compact contract; keep persona lens/Own/Refuse role-specific. | Generated common contract preserves required invariants and renderer drift checks pass with a smaller prompt corpus. |
| `MAE-014` | P1 | `EXTERNAL_LIMIT_HOST_DEADLINE_CANCEL` | Full Audit/agent-wave launch whole runnable sets without a local concurrency guard; host deadline/cancel is unavailable. | Put one workflow-global bounded scheduler in front of every `agent()` call and expose deadline/cancel capability separately. | Workflow-global scheduling enforces actual in-flight capacity; no supported host deadline/cancel Adapter exists. |
| `MAE-015` | P1 | `EXTERNAL_LIMIT_HOST_ACTIVITY_ADAPTER` | Liveness heuristics depend on private JSONL file layout. | Keep caller collaboration/thread activity and JSONL size diagnostic-only; require managed host acquisition plus monotonic identity/sequence/head verification before any `RUNNING`/`TERMINAL` claim. | Pure adjudication treats every caller mapping, including fresh active/terminal values, as unverified and returns `UNKNOWN + EXTERNAL_LIMIT`; a supported host activity acquisition Adapter is not available. |
| `MAE-016` | P1 | `DONE` | Interruption messages can alter model-visible context without call-record coverage. | Disable injected interruption messages for governed calls or bind them into the call record. | Governed project config disables interruption-message injection; replay records remain closed over model-visible inputs. |
| `MAE-017` | P1 | `DONE` | No reproducible efficiency regression benchmark exists. | Add `multi_agent_efficiency_evaluation_v1` fixture/schema/runner for current, single-agent, and bounded-role profiles. | Runner and typed attestation index compare quality and cost classes; standalone/self-attested input cannot unlock a measured claim. |
| `MAE-018` | P1 | `DONE` | Memories may be generated from external-context sessions and use an unreviewed model. | Document/project the supported memory-generation policy: external-context exclusion and lower-cost extract/consolidation model where the host supports it. | Local capability probe validates strict config keys, external-context exclusion, Codex version, and the Luna model without fallback. |

## Execution order

1. `MAE-001`..`MAE-006`: close the actual execution-control seam.
2. `MAE-007`..`MAE-009`: close Context and memory amplification.
3. `MAE-010`..`MAE-016`: remove routing/workflow duplicate work and private
   assumptions.
4. `MAE-017`..`MAE-018`: add longitudinal measurement and host policy.
5. Run full governance validation and update this ledger with exact evidence.

## Non-goals

- Lowering safety, reviewer independence, evidence quality, or hard-boundary
  coverage merely to reduce tokens.
- Treating cached tokens as free or planned bytes as provider billing truth.
- Adding a second orchestration framework beside the Development-Agent
  Governance Module.
- Editing generated role/profile views by hand.
- Committing, pushing, deploying, restarting, PostgreSQL writes, or broker
  contact without separate authority.

## Completion log

Append one concise row per completed remediation. Evidence belongs in tests and
source; this section is an index, not a second report.

| ID | Result | Evidence |
|---|---|---|
| `MAE-001` | Count/state control closed; duration/provider-token enforcement external. | `execution_budget_policy_v1`; exact-cover execution-ledger tests. |
| `MAE-002` | Saved-workflow history closed; Codex-native attestation external. | Requested identity/history bindings; workflow adversarial tests. |
| `MAE-003` | Wait/no-delta caps closed; host cancellation external. | One-watcher ledger policy and cap/state-machine tests. |
| `MAE-004` | Exact GPT-5.6 role tiers; inheritance rejected. | Registry, 22 native profiles, and three workflow override tests. |
| `MAE-005` | Surface claims fail closed; native receipt external. | Surface profiles and `mandatory_role_eligible` validation. |
| `MAE-006` | Supported concurrency config plus receipt-bound depth. | Config probe, Registry validation, and lineage tests. |
| `MAE-007` | Active TODO reduced to exact task/dependency projection. | Context reachability and unrelated-row stability tests. |
| `MAE-008` | Bounded, path/section/digest-pinned history refs. | Context adversarial/path-containment tests. |
| `MAE-009` | 18 bounded hot memories; future promotion requires external authority. | Manifest v3, exact unique roster, predecessor archive recovery, zero-mutation CLI, promotion and crash-resume tests. |
| `MAE-010` | Envelope selection moved after DAG construction. | Routing/admission tests and executable partition contract. |
| `MAE-011` | Safe full default; reduced mode requires external recall authority. | Full-Audit axis/authority/closure tests plus canonical skill/Registry consistency. |
| `MAE-012` | Read-only OPS calls collapsed without weakening effect gates. | OPS routing tests. |
| `MAE-013` | Common contract centralized and generated. | Renderer drift and prompt-invariant tests. |
| `MAE-014` | Workflow-global concurrency enforced; cancellation external. | Peak in-flight scheduler tests and surface capability record. |
| `MAE-015` | Private-file and caller-self-asserted liveness claims removed; managed host acquisition and monotonic replay resistance remain external. | Liveness schema/adjudicator plus fresh fabrication, replay/rollback, and caller identity/sequence/head rejection tests. |
| `MAE-016` | Unrecorded interruption injection disabled. | Strict config validation and execution-policy replay contract. |
| `MAE-017` | Quality-first A/B runner and typed trust seam complete. | Evaluation schemas, fixture, threshold and anti-self-attestation tests. |
| `MAE-018` | Memory-generation policy supported locally. | Strict negative-control capability probe reports `SUPPORTED`. |

### Independent review reopen

The 2026-07-30 final read-only review reopened `MAE-009` and `MAE-011` before
publication. It reproduced two self-attestation paths: a caller-supplied
`PM_CLOSURE` plus recomputed memory-lineage digests, and caller-built Full Audit
recall claim evidence.

Both paths are now closed. Memory promotion requires typed
`PLATFORM_OR_EXTERNAL_ATTESTED` authority plus a non-serialized host verifier,
and exact predecessor manifest/hot bytes are reconstructed from archive record
v2; standalone promotion is zero-mutation `EXTERNAL_LIMIT`. Full Audit rejects
adaptive, adaptive-shadow, reduced axes, and insufficient full capacity as
`EXTERNAL_LIMIT_RECALL_AUTHORITY` before the first model call. The original
exploits and the complete scoped governance suites must remain green before
publication.

### Independent review reopen round 2

The second independent read-only review found two consistency gaps after the
trust fixes: the canonical Full Audit skill still instructed callers to use a
now-forbidden reduced scheduler and stale envelope/model overrides, while the
memory manifest verifier did not require the exact unique governed role roster.
Both are closed: the skill now exposes only the executable full 13-axis
invocation and exact Registry caps with no model override, while
`verify_manifest()` compares the manifest roster to the discovered governed
active memories in exact canonical order. Missing and duplicate role cases now
fail after self-digest recomputation. At that point the independent rerun
reported no remaining P0/P1; this was a point-in-time result later superseded
by review rounds 3 through 6.

### Independent review reopen round 3

The third independent review found that Context capacity was bound to a
route-derived projection while Profit Diagnosis and Full Audit could construct
different call DAGs after admission. It also found that explicit empty DAGs,
unknown node fields, and malformed CLI JSON were not all rejected through one
typed fail-closed boundary.

The round-3 source repair now binds the complete saved-workflow DAG before the
first model call and exact-compares every node, predecessor edge, identity,
class, permission, count, and digest. Profit Diagnosis binds its 3 evidence +
6 probe + 1 map nodes. Full Audit binds only 13 discovery axes + 1 seam critic; all
data-dependent claim verification and fix/review paths were removed from the
saved workflow and emitted as coverage debt for a separately compiled,
host-attested phase under existing `MAE-005`. This is not a ninth
`EXTERNAL_LIMIT`. Public compilation rejects `[]` and unknown fields, while an
internal no-argument constructor represents compiler-derived zero-delegation
queries. CLI `null`, non-arrays, empty arrays, and malformed JSON return typed
`FAIL` with a nonzero exit and no traceback.

The round-3 cross-review, whose point-in-time completeness judgment was later
superseded by rounds 4 and 5, reopened two P1 trust seams. First, a caller could
provide an explicit DAG that omitted or substituted canonical routed
call-producing nodes. Second, Closure validated a wave against its own
recomputed DAG but did not exact-bind that wave back to the Context DAG, so a
14-node Full Audit Context could accept an internally rehashed 16-node wave.
Both are now closed: explicit DAGs must retain the exact routed-node core while
permitting only legitimate supersets, and Closure exact-compares the ordered
admitted-task core plus `dag_digest` with the verified Context binding. Any DAG
expansion therefore requires a fresh Context before calls; packet-local
rehashing cannot self-authorize it.

### Independent review reopen round 4

The 2026-07-31 P1/P2 cross-review reopened five source-bound trust gaps. A
caller could truncate or reseal an execution ledger and race two admissions
from the same head; a fresh caller timestamp could be promoted to
`RUNNING`/`TERMINAL` without authenticated host acquisition; the generic
Context materializer could accept a self-rehashed omission or substitution;
the specialized Full Audit and Profit projections still disagreed with their
actual fixed call sets; and duplicated Full Audit claims could produce
ambiguous staged debt while an exhausted axis could continue to the seam.

The ledger admission path now requires one opaque, non-serializable,
Registry-minted controller capability. It freezes the exact Registry policy
and surface generation, admits from one process-lifetime genesis, advances a
monotonic ledger head under a per-controller lock, and rejects truncation,
replay, copied authority, forged caps, mutable-mapping races, and competing
same-head admissions. Receipt reconstruction remains structural and cannot
mint admission authority. Liveness now treats caller collaboration/thread
mappings only as freshness diagnostics: all such claims return
`UNKNOWN + EXTERNAL_LIMIT` until a managed host Adapter supplies authenticated
identity, sequence, and head continuity. The Registry owns the exact
60-second/zero-future-skew policy, and the public interface exposes no caller
clock override.

Context materialization now re-routes every plan and exact-checks the
task-aware execution projection before signing. Generic tasks preserve their
complete routed core and allow only legitimate supersets. Full Audit binds
exactly 14 call-producing nodes (13 axes plus seam), while Profit Diagnosis
binds exactly 10 (3 evidence, 6 probes, and 1 map); PA/CC/QC route obligations
reuse those fixed results instead of creating duplicate calls. Dispatch,
capture, trust, and Closure consume the same projection. Structurally valid
unauthorized waves remain visible to consumption exact-cover and also fail
with an explicit unbound-node error, so early DAG rejection cannot hide a
ghost wave.

Full Audit staged debt is now one sorted, unique typed record per discovered
claim, exact-bound to every source axis through `bound_axes`. Zero verification
outcomes cannot be reported as disputed or verified, and missing, extra, or
forged axis bindings fail closed. Persistent null after the one allowed retry
aborts before seam execution. The canonical skill supplies the exact Context
artifact and a positive dispatch-owned admission clock, and the AIML lineage
refresh updates the nested program-adoption bootstrap when recompilation
changes the Context generation.

Final evidence for this review lane is `244 passed` across Context/DAG/wave,
Full Audit, Profit, codegen, AIML-adoption, and development-governance tests,
plus `89 passed` across execution policy, liveness, and trust bindings.
Full-Audit and Profit files independently report `28 passed` and `29 passed`;
workflow codegen reports `3 passed`. Python compilation, Registry governance
validation (`PASS`, 20 roles), generated-workflow drift validation, and
`git diff --check` all pass. Those listed round-4 gaps were closed, but the
point-in-time completeness statement was superseded by round 6. The documented
host-capability `EXTERNAL_LIMIT` rows remain fail-closed rather than being
relabelled as source completion.

### Independent review reopen round 5

The post-fix contract review found one final P1 mismatch between the real Full
Audit workflow result and Closure. Although the Context and wave exact-bound
the fixed 14-node axes-plus-seam DAG, workflow `closure_admissions` returned
only the 13 axes. It also omitted the required dispatch fields on those axis
admissions. Tests had copied the fixture admissions into Closure instead of
directly consuming the real workflow result, so the mismatch remained hidden.

The workflow now returns ordered exact-cover admissions for the same Context
core: 13 `role_fragment` axis admissions with explicit empty predecessors,
followed by one `nested_payload` `seam:critic` admission whose CC native
identity, verification/read-only class, sorted 13-axis predecessors, empty
path scope, and canonical reason match the Full Audit contract. Controller
`axis_bindings` remains the axis-only projection and cannot absorb the seam.

The real saved-workflow integration test now copies these admissions directly
into a closure packet, proves their ordered identity-bearing core equals the
Context DAG binding, and obtains a valid Closure result. Removing the seam or
changing its predecessor set is rejected as a missing or substituted fixed
call admission. Earlier round-2 through round-4 completeness language became
historical at this round and was later superseded again by round 6; publication
must use the cumulative round-1-through-round-6 result.

Round-5 evidence is `28 passed` for the complete Full Audit adversarial file
and `107 passed` for the combined Closure quality, Context, dispatch-DAG, wave,
trust-binding, and development-governance suite. Workflow codegen reports
`3 passed`; Node syntax validation, Registry governance validation (`PASS`,
20 roles), generated-workflow drift validation, and `git diff --check` pass.

### Independent review reopen round 6

The pre-merge review found one call-zero availability seam. Valid end-to-end or
runtime facts could produce a 15-node Full Audit or 11/12-node Profit Context
even though the corresponding saved workflow can execute only its fixed
14/10-node graph. The compiler admitted and materialized the Context, while the
executor rejected it before call 1. No authority or model call escaped, but the
contradictory admission could waste sessions and provoke retry loops.

The first repair made compiler-derived specialized plans reject unmatched calls
with `SPECIALIZED_WORKFLOW_SPLIT_REQUIRED`, while retaining explicit supersets
for a presumed separately selected executor. That distinction was an
intermediate state only and was superseded by round 7 after independent review
proved a caller argument is not executor authority.

### Independent review reopen round 7

Exact-head adversarial review found four related remaining seams:

- a caller-supplied specialized superset could impersonate host-executor
  authority and reach the fixed saved workflow;
- an injected Registry could redefine fixed axes or graph identity between
  compile, materialize, validation, and saved-JS admission;
- mixed omission/substitution plus an extra node could be misclassified as a
  safe split and feed a retry loop; and
- Closure validated only a partial mirror of the model-facing Full Audit
  schema, then continued deriving decisions from malformed raw audits or
  malformed inline verifier outcomes.

The final contract permits explicit DAG supersets only on non-specialized
generic/host routes. Full Audit and Profit Diagnosis always require their exact
fixed graph. A pure fixed-core-plus-extra graph raises the typed
`SPECIALIZED_WORKFLOW_SPLIT_REQUIRED` with `surface` and sorted
`extra_node_ids`. This signal exists only after exact Registry/artifact
metadata, complete route authorization, canonical ASCII node ids,
Registry-native role/class/permission bindings, and acyclic topology pass;
mixed or malformed artifacts receive only a generic DAG error. PM branches on
`error_code` and freshly compiles the fixed
saved-workflow phase plus a non-specialized host phase. It never slices,
re-signs, or retries the rejected artifact. Mixed tampering remains a generic
DAG mismatch and cannot auto-split. Python materialization, the public
validator, Full Audit JS, and Profit JS all enforce the same call-zero rule.

Context now binds the canonical digest of a governance-validated Registry.
Compile, materialize, independent validation, generated `agent-wave`, and both
saved workflows reject invalid or different Registry generations. This
prevents axis deletion, fixed-graph redefinition, and cross-generation artifact
reuse.

Closure mirrors the complete model-facing `FINDINGS_SCHEMA` and quarantines an
invalid raw audit before finding counts, staged-debt derivation, decision
classification, or set operations. A checked-in cross-language parity test
extracts the live JS schema and exact-compares its JSON-Schema semantics with
the Python mirror. Inline verifier outcomes and votes are likewise type-checked
and quarantined before identity lookup, nested-admission projection,
aggregation, or hash-set use, so malformed JSON returns deterministic errors
instead of crashing the session. Until a real host executor exists, those
typed verifier calls remain explicit MAE-005 host-phase debt rather than
inline saved-workflow authority.

The earlier `507 passed` and `5131 passed / 16 skipped` figures belong to the
superseded round-6 head and are not release evidence for round 7. Final frozen
worktree counts, independent post-fix review, hosted exact-head CI/review, and
publication are recorded only after the cumulative rerun completes.

### Independent review reopen round 8 and final local evidence

The cumulative exact-bytes review found additional cross-language admission
and availability gaps before publication. Python-valid Unicode object keys
could be rejected because JavaScript canonical JSON used UTF-16 key order;
generic saved-workflow admission checked contract shape without proving that
the bound DAG contained every canonical routed call; operator-loop, hidden
suffix, focus, and repository-scope normalization had narrower parity gaps;
and fixed Full Audit reviewers could absorb the downstream reviewers of an
unmatched writer, producing a generic topology error instead of the promised
typed fresh-phase split. Host-effect contracts also needed an explicit
call-zero boundary on both specialized saved workflows.

Canonical JSON and every repository-path ordering boundary now use Unicode
code-point order, reject lone surrogates and unsafe/pathspec spellings, and
preserve Python `PurePosixPath` hidden-file suffix semantics. The generic
workflow recomputes the exact canonical routed call core before call 1,
including every source, review, gate, broker, P0-B, S2, AIML, and operator-loop
selector. Full Audit and Profit Diagnosis allow source/docs/test calls only as
typed `SPECIALIZED_WORKFLOW_SPLIT_REQUIRED` extras; any unmatched call now
pulls its complete downstream reviewer/gate dependency chain into the fresh
phase. Effects requiring a host Adapter reject before calls, while `none`,
`public_web_read`, and source/docs/test classes retain their documented split
semantics. Malformed or self-rehashed contracts, routes, Registries, schemas,
paths, and digests remain ordinary zero-call failures rather than retry
signals.

The first complete structure rerun exposed one stale test fixture, not a
production fallback: it self-signed a test-only Registry generation that the
saved workflow correctly rejected before any call. The fixture now supplies
the canonical core/docs pack sources and uses the repository Registry; cyclic
DAGs are asserted at the earlier zero-call binding gate. Its complete file is
`15 passed`.

Final local release evidence on the cumulative worktree is:

- scoped Context/DAG/Full-Audit/Profit/codegen suite: `218 passed`;
- non-disposable structure suite: `5150 passed, 16 skipped, 0 failed` in
  `1130.30s`;
- Python-to-generated-JavaScript route parity: generic `129/129` and
  specialized `46/46` exact;
- directed/fuzz route corpus: 2,707 cases and zero full-entry mismatches (the
  two synchronous-helper differences are cryptographic digest checks that the
  full async entry rejects with zero calls);
- valid finite, operator-loop, and Unicode-bound requests each call exactly
  once; invalid prompt/loop digests, focus, path order/safety, omitted route,
  host effects, and forged Registries call zero times;
- Registry validation, workflow codegen drift, all three Node syntax checks,
  and `git diff --check`: PASS;
- two independent exact-byte release/parity reviews: `0 P0 / 0 P1 / 0 P2`.

These results establish source-level release readiness only. They do not close
the eight typed host/platform `EXTERNAL_LIMIT` rows, attest provider billing or
duration telemetry, authorize deployment/runtime mutation, or prove any
broker/trading effect. Hosted exact-head CI/review and publication remain Git
release steps, not substitutes for those external capabilities.
