---
name: ultracode-full-audit
description: Conductor 專用；operator 要求全盤審查、全面優化、multi-agent 冷酷對抗審計時使用。
---

# Full Audit Orchestration

Canonical workflow: `.claude/workflows/openclaw-full-audit.js`
Governance: `.codex/agent_registry_v1.json` and
`docs/agents/development-agent-governance.md`

## Objective

Full Audit maximizes decision-changing defect recall and durable closure value,
not findings per token. It may use a materially larger target/quality reserve
than a narrow task when that avoids false closure or rework. Hard boundaries,
independent discovery, negative space, dissent, and raw evidence are never
compressed away to meet a budget.

The saved workflow in this source generation has one exact pre-call DAG:
13 discovery axes plus one seam critic. Data-dependent claim verification and
fix/review are a separately admitted phase under the existing
`MAE-005 / EXTERNAL_LIMIT_NATIVE_SELECTOR_ATTESTATION` host capability; the
saved workflow emits typed coverage debt and makes zero such agent calls.

## Stage 0 — PM freeze

Before the workflow, PM freezes the claims that need stable identity:

- source HEAD, origin head, relevant dirty/untracked hash
- runtime head/build/host/environment when runtime is in scope
- active TODO owner/blocker and applicable hard stops
- scope, surfaces, focus, allowed evidence/effects
- previous unresolved audit concerns

The workflow is read-only by default. Baseline absence is visible debt; a
runtime/live claim without fresh runtime identity cannot PASS.

## Scheduler modes

- `full` is the only currently executable scheduler. It executes all 13
  canonical discovery axes.
- `adaptive_shadow`, `adaptive`, and any `full` axes subset are unavailable
  until a separate `PLATFORM_OR_EXTERNAL_ATTESTED` recall/non-inferiority
  Adapter and out-of-band host verifier exist. A task claim, boolean,
  self-digest, `claim_evidence`, or ordinary execution attestation cannot grant
  this authority. The workflow returns `EXTERNAL_LIMIT_RECALL_AUTHORITY` before
  its first model call.

The full axes are CC/FA/E2/E3/BB/IB/OPS/QC/MIT/AI-E/E5/A3/R4. E4
regression evidence belongs to the post-integration pipeline outside this
workflow (claim-0011) and TW is a writer, so neither is a discovery axis.
IBKR never routes to BB; runtime/deploy evidence gets OPS.

## Elastic admission envelope

The compiler-produced `context_budget_authority_v1` is required. Its canonical
bytes and digest supply every execution cap; caller-local values cannot
override them. The current Registry `full_audit` authority is:

- `max_unique_nodes` = `44`
- `max_call_attempts` = `46`
- `max_context_tokens_per_call` = `96000`
- `max_workflow_planned_input_tokens` = `4416000`
- `retry_budget` = `2`
- `max_concurrent_calls` = `3`

Tunable args inside that authority:

| Arg | Default | Meaning |
|---|---:|---|
| `estimated_tokens_per_audit` | 4,500 | Admission lower-bound estimate, not a prompt cap |
| `estimated_seam_tokens` | 4,000 | Cross-axis seam critic reserve |
| `admission_now_ms` | wall clock | Dispatch-side epoch-ms admission clock; mandatory where the sandbox denies `Date.now()` |
| `stop_when` | decision-value rule | Mandatory coverage closed and next novelty/verdict-reversal value below marginal cost |

If the envelope cannot admit all 13 discovery axes, the workflow returns
`EXTERNAL_LIMIT_RECALL_AUTHORITY` before its first model call. Every discovered
decision claim becomes explicit `coverage_debt` for a fresh MAE-005
host-attested verification Context; `fix=true` likewise emits host-phase debt
and authorizes no writer/reviewer call. Deferred or unverified debt makes
`pass_eligible=false` and never truncates into PASS.

Call and token accounting covers the 13 audit axes, their bounded infrastructure
retries, and one seam critic. Registry authority is a ceiling, not a target.

## Audit phase

Every axis discovers independently and returns `audit_fragment_v2` with:

- FACT/INFERENCE/ASSUMPTION, severity, confidence
- concise reproducible evidence and impact
- assertion, file, symbol/root anchor, post-hoc defect type
- negative-space assumptions/why unproven
- measured consumption or an unavailable reason

No axis writes a role report or memory. Findings are not shown to peers during
discovery; this protects independence.

## Claim staging and seam phase

1. Deterministically validate required finding fields and normalize exact claim
   identity.
2. Exact duplicates remain grouped for presentation; distinct assertions at one
   symbol remain separate and all original members survive.
3. Every zero-outcome decision claim is staged as typed
   `staged_claim_verification` debt with exact `MAE-005`,
   `REQUIRES_HOST_CAPABILITY_PHASE`, and sorted unique `bound_axes`. It is
   `UNVERIFIED`, not a verified dispute; exact duplicates across axes share one
   claim/debt whose binding exact-covers every originating axis.
4. The current saved workflow performs zero data-dependent verifier, third-vote,
   fix, or fix-review calls. A host phase must recompile Context with its now
   knowable exact call DAG before any such call.
5. A seam critic returns re-probes; these remain coverage debt until an assigned
   role obtains evidence.

No absent host phase is presented as verifier dissent or quorum.

## Cluster and fix

Clustering is presentation-only by normalized file+symbol. Members, severity,
evidence, and fix identity remain untouched.

`fix=true` does not authorize an in-run E1/E2 call. It records MAE-005
host-capability debt. A later host-attested phase may compile a fixed candidate
DAG; E4 regression remains post-integration.

## Closure

The workflow returns one immutable `full_audit_control_v1` fragment, exact
`closure_admissions`, immutable axis `role_fragment_v1` objects, slim decision
views, coverage holes/debt, assumptions, seam re-probes, fixes (in-run
regression is retired; result fields stay null), and
partial or measured consumption. PM must copy controller/admissions/fragments and
the canonical unverified projection into one `closure_packet_v1`. Closure
requires the full scheduler and exact ordered 14-node admission parity:
13 `role_fragment` axis admissions followed by the `nested_payload`
`seam:critic` admission. It validates canonical JSON debt projection, seam
result digest, axis fragment digests, and exact workflow call coverage of the
Context-bound axes+seam DAG. Omitting or substituting an axis, seam, or debt
fails.

## Recall benchmark before adaptive default

Replay at least 24 historical closures spanning Rust, Python, GUI, ML/data,
runtime, security, docs, Bybit, and IBKR, plus at least 12 seeded known defects.

Required before `adaptive_recall_approved=true`:

- seeded P0/P1 recall 100%
- goal-bearing MEDIUM recall >=95%
- hard-edge routing 100%
- false PASS/false DONE 0
- mandatory scope/hard-boundary omission 0
- invalid test/evidence reuse 0
- 7/30-day reopen no worse than full baseline
- median token per durable closure and p75 closure lead time improve without
  quality regression

This benchmark is a future design input, not current execution authority. Even
after it is satisfied, reduced scheduling remains disabled until an independent
platform/external Adapter and out-of-band verifier are implemented and admitted.
Until then every run uses `full`.

## Standard invocation

```javascript
const dispatchFullAudit = ({
  Workflow,
  contextArtifact,
  admissionNowMs,
  baseline,
  scope,
  dirtyScope,
  surfaces,
  focus = "",
  routeRequiredRoles,
  runSequence = 0,
}) => {
  if (
    !contextArtifact ||
    contextArtifact.schema_version !== "context_artifact_v1"
  ) {
    throw new Error("exact materialized contextArtifact is required");
  }
  if (!Number.isInteger(admissionNowMs) || admissionNowMs <= 0) {
    throw new Error("dispatch-side admissionNowMs must be positive epoch-ms");
  }
  return Workflow({
    name: "openclaw-full-audit",
    args: {
      context_artifact: contextArtifact,
      admission_now_ms: admissionNowMs,
      baseline,
      scope,
      dirty_scope: dirtyScope,
      surfaces,
      focus,
      scheduler: "full",
      route_required_roles: routeRequiredRoles,
      run_sequence: runSequence,
      fix: false,
    },
  });
};
```

`admissionNowMs` is captured by the desktop dispatch side immediately before
invocation; the saved-workflow sandbox never has to call `Date.now()`.
`contextArtifact` is the exact object returned by Context materialization.
Digest and budget fields are derived from those inline bytes rather than copied
as a second caller-controlled authority.

`openclaw-full-audit` finds defects. `profit-diagnosis` finds money. Profit
diagnosis requires a fresh baseline and hash-pinned current priors, allows an
honest well-covered `NO_EVIDENCE`, and returns one structured result rather than
forcing hallucinated opportunities or per-axis reports.
