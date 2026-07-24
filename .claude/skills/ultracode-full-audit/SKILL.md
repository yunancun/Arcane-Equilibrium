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

- `adaptive_shadow` (default): execute the full requested backstop while also
  calculating the scope-selected adaptive subset. This measures recall without
  paying a second discovery wave.
- `full`: execute every requested axis.
- `adaptive`: execute the selected subset + rotating negative-space axis; allowed
  only with `adaptive_recall_approved=true` plus a hash-pinned
  `adaptive_recall_authority_digest` after the benchmark below. Mandatory axes
  come from the canonical Dispatch role projection, then add CC/FA and one
  rotating negative-space axis. Full Audit does not maintain a second
  surface-to-role table. Selection surfaces and run sequence are closure-bound
  and recomputed; CC/FA-only cannot PASS.

Default full axes include CC/FA/E2/E3/BB/IB/OPS/QC/MIT/AI-E/E5/A3/R4. E4
regression evidence belongs to the post-integration pipeline outside this
workflow (claim-0011) and TW is a writer, so neither is a discovery axis.
IBKR never routes to BB; runtime/deploy evidence gets OPS.

## Elastic admission envelope

The compiler-produced `context_budget_authority_v1` is required. Its canonical
bytes and digest supply the exact `max_agents`, `retry_budget`, and
`max_input_tokens`; caller-local values cannot override them. The current
Registry `full_audit` authority is 20 agents, 2 total retries, and 96,000 planned
input tokens.

Tunable args inside that authority:

| Arg | Default | Meaning |
|---|---:|---|
| `max_verification_calls` | Context `max_agents` | Independent claim-verification calls; cannot exceed agent authority |
| `estimated_tokens_per_audit` | 4,500 | Admission lower-bound estimate, not a prompt cap |
| `estimated_tokens_per_verification` | 2,000 | Admission lower-bound estimate |
| `estimated_seam_tokens` | 4,000 | Cross-axis seam critic reserve |
| `estimated_fix_tokens` | 8,000 | Optional E1 fix reserve per admitted finding |
| `estimated_review_tokens` | 4,000 | Independent E2 fix-review reserve |
| `max_fixes` | 5 | Optional fix-mode source patches |
| `admission_now_ms` | wall clock | Dispatch-side epoch-ms admission clock; mandatory where the sandbox denies `Date.now()` |
| `judgment_model` | inherit session model | Explicit strong-judgment override; derive from `settings/ai_pricing.yaml` active entries, `null` = inherit |
| `stop_when` | decision-value rule | Mandatory coverage closed and next novelty/verdict-reversal value below marginal cost |

If the envelope cannot admit an axis/claim/fix, it becomes explicit
`coverage_debt`. Deferred or unverified debt makes `pass_eligible=false`; the
scheduler never truncates it into PASS. Increase the envelope or split scope when
the debt is decision-critical.

Call and token accounting reserves every phase: audit axes, one shared total
retry budget across audit and verification, seam critic, verifier quorum with
risk-conditioned third votes, and optional E1/E2 fix pairs. The 20/96k authority is a ceiling,
not a target; unused reserves are not actual usage. If full backstop plus claims
cannot fit, split scope and preserve coverage debt rather than lowering evidence.

## Audit phase

Every axis discovers independently and returns `audit_fragment_v2` with:

- FACT/INFERENCE/ASSUMPTION, severity, confidence
- concise reproducible evidence and impact
- assertion, file, symbol/root anchor, post-hoc defect type
- negative-space assumptions/why unproven
- measured consumption or an unavailable reason

No axis writes a role report or memory. Findings are not shown to peers during
discovery; this protects independence.

## Verify phase

1. Deterministically validate required finding fields and normalize exact claim
   identity.
2. Exact duplicate assertion+evidence can share verification; distinct
   assertions at one symbol remain separate and all original members survive.
3. Every admitted CRITICAL/HIGH/goal-bearing MEDIUM claim receives two
   independent verifiers.
4. High-risk/reachability or verifier disagreement receives a third independent
   adjudicator within the risk-conditioned third-vote capacity (dedicated
   reservation per admitted high-risk claim, then deterministic severity-order
   floating entitlements); shortfall is explicit coverage debt.
5. Missing quorum is disputed, never confirmed.
6. A seam critic returns re-probes; these remain coverage debt until an assigned
   role obtains evidence.

The workflow preserves verifier dissent. Capability/over-gate findings are not
downgraded merely because the capability is unreachable; unreachability may be
the defect itself.

## Cluster and fix

Clustering is presentation-only by normalized file+symbol. Members, severity,
evidence, and fix identity remain untouched.

`fix=true` admits only bounded confirmed claims. E1 fixes in isolated scope; E2
reviews without editing. Candidates are never integrated in-run
(`integration_status` stays `NOT_INTEGRATED`); E4 regression evidence belongs to
the post-integration pipeline after the candidate merges (claim-0011).

## Closure

The workflow returns one immutable `full_audit_control_v1` fragment, exact
`closure_admissions`, immutable axis `role_fragment_v1` objects, slim decision
views, coverage holes/debt, assumptions, seam re-probes, fixes (in-run
regression is retired; result fields stay null), and
partial or measured consumption. PM must copy controller/admissions/fragments and
the canonical unverified projection into one `closure_packet_v1`. Closure
recomputes adaptive selection, eligibility and axis parity; validates canonical
JSON debt projection, seam result digest, axis fragment digests and hash-pinned
verification outcomes. Omitting an axis/debt or overwriting dissent fails.

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

Until proven, `adaptive_shadow` remains the default. After approval, run a full
backstop at least every 10 adaptive runs or 30 days and rotate the negative-space
axis.

## Standard invocation

```text
Workflow({
  name: "openclaw-full-audit",
  args: {
    baseline: {
      source_head: "<40-hex>",
      dirty_diff_hash: "sha256:<64-hex>",
      untracked_relevant_hash: "sha256:<64-hex>",
      runtime_head: "<40-hex-or-null>",
      runtime_observed_at: "<ISO-time-or-null>"
    },
    scope,
    dirty_scope: ["<sorted-repo-path>"],
    surfaces: ["full_audit", "agent_workflow", "authority", "runtime", "bybit", "ibkr", "ml", "gui", "docs"],
    focus,
    scheduler: "adaptive_shadow",
    task_contract_digest: "sha256:<64-hex>",
    context_artifact_digest: "sha256:<64-hex>",
    route_required_roles: ["CC", "AI-E", "QC", "MIT", "OPS", "BB", "IB"],
    budget_authority_canonical: "<exact compiler-produced canonical JSON bytes>",
    budget_authority_digest: "sha256:<64-hex>",
    run_sequence: 0,
    fix: false
  }
})
```

`openclaw-full-audit` finds defects. `profit-diagnosis` finds money. Profit
diagnosis requires a fresh baseline and hash-pinned current priors, allows an
honest well-covered `NO_EVIDENCE`, and returns one structured result rather than
forcing hallucinated opportunities or per-axis reports.
