# GPT-5.6 Multi-Agent Efficiency Remediation TODO

Status: `COMPLETE_WITH_EXTERNAL_LIMITS_UNCOMMITTED`

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
| `MAE-005` | P0 | `EXTERNAL_LIMIT_NATIVE_SELECTOR_ATTESTATION` | Native identity and budget enforcement vary by execution surface. | Add `execution_surface_profile_v1` with native-selector, telemetry, deadline, fork, and concurrency capabilities. Required-role closure fails closed on degraded identity. | Degraded surfaces cannot close mandatory roles; Codex-native selector/history enforcement remains reported-only pending a supported host receipt. |
| `MAE-006` | P0 | `DONE` | Project config relies on legacy `max_threads` and undocumented `max_depth`. | Use `max_concurrent_threads_per_session`; make recursion policy explicit and receipt-validated rather than config folklore. | Current config validates and execution-lineage admission enforces spawn depth independently of undocumented config. |
| `MAE-007` | P1 | `DONE` | `active_state` can load the entire 44.8KB AI/ML board into many roles. | Select exact task ID/row plus direct dependency rows and digest those bytes. | Context compiles the exact active TODO projection; unrelated rows do not alter the admitted projection digest. |
| `MAE-008` | P1 | `DONE` | `history_on_demand` is declared but unreachable in the Context compiler. | Add exact `history_refs` selection with safe path/section/digest validation. | At most four repository-local safe H2 sections are byte/digest-bound; whole-glob and unselected history fail closed. |
| `MAE-009` | P1 | `EXTERNAL_LIMIT_MEMORY_PROMOTION_ATTESTATION` | Seven active role memories exceed the 300-line hot target and contain stale ledgers. | Archive dated task records; retain durable lessons and topical pointers only; add structural limits. | All 18 hot views, exact unique role roster, and archive lineage pass; promotion is zero-mutation unless a non-serialized host verifier authenticates exact typed external authority. |
| `MAE-010` | P1 | `DONE` | Budget envelope is chosen before the final required-node projection. | Select/promote the envelope after DAG construction, or return an executable partition plan. | Route chooses the envelope after required-node construction and emits an executable bounded partition when direct admission is unavailable. |
| `MAE-011` | P1 | `EXTERNAL_LIMIT_RECALL_AUTHORITY` | Full Audit default `adaptive_shadow` executes all 13 axes while appearing reduced. | Keep the complete audit as the safe default; permit genuinely reduced adaptive selection only with task-bound recall/non-inferiority authority. | Workflow and canonical skill execute only full 13-axis mode; every reduced set rejects before calls until an out-of-band host verifier authenticates recall non-inferiority. |
| `MAE-012` | P1 | `DONE` | Read-only operations review schedules preflight and postcheck without an intervening effect. | Collapse to one `ops_observation` for read-only/source lanes; keep two nodes only around an admitted effect. | Read-only/service review uses one observation; admitted effects retain distinct preflight and postcheck nodes. |
| `MAE-013` | P1 | `DONE` | Repeated universal contract prose inflates every custom-agent prompt. | Centralize common operating rules behind one generated compact contract; keep persona lens/Own/Refuse role-specific. | Generated common contract preserves required invariants and renderer drift checks pass with a smaller prompt corpus. |
| `MAE-014` | P1 | `EXTERNAL_LIMIT_HOST_DEADLINE_CANCEL` | Full Audit/agent-wave launch whole runnable sets without a local concurrency guard; host deadline/cancel is unavailable. | Put one workflow-global bounded scheduler in front of every `agent()` call and expose deadline/cancel capability separately. | Workflow-global scheduling enforces actual in-flight capacity; no supported host deadline/cancel Adapter exists. |
| `MAE-015` | P1 | `EXTERNAL_LIMIT_HOST_ACTIVITY_ADAPTER` | Liveness heuristics depend on private JSONL file layout. | Define supported collaboration/thread activity as the primary Interface and retain JSONL size only as diagnostic fallback; require a real host acquisition Adapter before integration claims. | Pure adjudication returns `UNKNOWN` without evidence; a supported host activity acquisition Adapter is not available. |
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
| `MAE-015` | Private-file liveness claim removed; host acquisition external. | Liveness schema/adjudicator tests. |
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
fail after self-digest recomputation. The independent rerun reported no
remaining P0/P1.
