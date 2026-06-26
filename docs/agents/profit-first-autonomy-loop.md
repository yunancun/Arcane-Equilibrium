# Profit-First Autonomous Trading Loop

Purpose: define the stable operating loop for building a local, self-improving
trading system whose first optimization target is real risk-adjusted net PnL
after fees and slippage.

This document is intentionally not a task list. Current state, active blockers,
candidate identity, runtime evidence, and handoff commands live in `TODO.md`
and linked reports.

## Intent

The system should learn and improve trading ability locally, using Demo as the
live-applicable proving ground before any future live review. It should actively
seek profit opportunities instead of passively waiting for a narrow preplanned
task. Any action that can improve expected net PnL is allowed by default when it
stays inside the configured loss-control envelope, authority model, audit trail,
and reconstructability requirements.

The loop is not an artifact factory. A loop iteration is successful only if it
moves one of these surfaces forward:

- cleaner loss/exposure control
- stronger candidate selection
- executable bounded Demo evidence
- real after-cost outcome measurement
- autonomous parameter learning
- runtime capability needed for the above

## State Loading

Every loop iteration starts by loading current state from the source of truth
instead of embedding task details in this document.

Read in this order:

1. `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`
2. `README.md`
3. `docs/agents/context-loading.md`
4. `TODO.md`
5. latest reports linked from `TODO.md`
6. current runtime evidence pointed to by `TODO.md`, normally under
   `/tmp/openclaw/` on `trade-core`

If those sources disagree, prefer the newest verified runtime/source evidence
for facts, keep governance from accepted docs/ADRs, and update stale pointers.

## Standing Demo Authorization

The operator has granted standing Demo operational authorization for profit-loop
work. Agents should not repeatedly ask for generic permission to advance Demo
research, source changes, deployment, runtime sync, or bounded Demo execution
plumbing.

That authorization must be converted into machine-checkable runtime authority
before it can affect orders. A valid standing Demo envelope must be auditable and
must include at least:

- scope: Demo only, not live/mainnet
- permitted action classes: research, source changes, deploy/sync, runtime
  health, private/read-only evidence, loss-control cleanup, bounded Demo probes
- loss controls: max order notional, max open notional, max daily loss, max
  probe count, max concurrent symbols, kill-switch conditions
- evidence controls: order/fill lineage, fee/slippage capture, controls,
  reconstruction inputs, artifact hashes
- expiry or renewal policy
- explicit denial of global Cost Gate lowering and live promotion

Once such an envelope exists, recurring artifacts must not remain in a generic
`defer` state only because operator authorization is missing. They must emit an
actionable state:

- ready inside the standing Demo envelope
- blocked by a named missing runtime field
- blocked by loss-control limits
- blocked by execution realism or evidence quality
- blocked by live/mainnet scope

Broad chat authorization is not a live authorization and does not bypass Rust
trading authority, Decision Lease, auditability, or reconstructability.

## Loss-Control Envelope

Risk control is treated as loss control. The loop should not block profitable
exploration for abstract process reasons; it should block actions that can create
unbounded, unreconstructable, or unauthorized loss.

Autonomous adjustment is allowed for trading parameters when all of these hold:

- the change is inside the standing Demo envelope
- expected net PnL is tied to current evidence
- the order path remains Rust-authoritative
- the decision and data inputs are reconstructable
- the change has a rollback or kill condition

Risk-envelope parameters themselves, such as maximum loss, maximum notional,
kill-switch thresholds, live/mainnet enablement, and global Cost Gate policy,
are not silently expanded by the learning loop. They require an explicit
reviewed envelope update.

## Loop Phases

### 1. Reality Baseline

Collect the minimum current facts needed to avoid optimizing stale state:

- exchange truth: open orders, positions, residual exposure
- runtime health and ownership
- local state divergence that can contaminate proof
- latest learning/profitability artifacts
- latest authority/envelope artifacts
- current fee, slippage, BBO, and instrument constraints when relevant

If exchange truth shows residual exposure or stale orders, loss-control cleanup
or reconciliation has priority over alpha expansion. Cleanup evidence is risk
hygiene only; it is not profit proof.

### 2. Opportunity Search

Search broadly for high-upside paths inside the envelope:

- false-negative Cost Gate candidates
- new side-cell / symbol / horizon combinations
- maker/MM and fee-aware microstructure
- regime-specific filters
- entry, exit, stop, and placement variants
- portfolio allocation and capital efficiency
- cost reduction, maker ratio, and fee-tier routes
- explanations for structurally unprofitable strategy families

Rank candidates by expected after-cost net PnL, evidence strength, execution
realism, time to test, account loss risk, governance risk, and autonomy value.
Do not select candidates from artifact count, replay-only positives, single
window positives, unattributed fills, or cleanup fills.

### 3. Envelope Admission

Before any order-capable action, compile the current candidate into an execution
envelope:

- candidate identity and horizon
- order construction and sizing under current cap
- fresh BBO/instrument checks
- maker/taker and fee/slippage capture plan
- max loss / max notional / max attempts
- Decision Lease and Rust admission path
- stop/kill conditions
- outcome review contract

If the envelope passes, proceed without another generic operator question. If it
fails, emit the exact missing condition and route to the next source/runtime fix
or candidate rotation.

### 4. Bounded Demo Execution

Execution is deliberately small, measured, and reconstructable:

- Demo only
- bounded by the standing loss-control envelope
- one candidate or one portfolio experiment per execution packet
- no global Cost Gate lowering
- no live/mainnet
- no direct order path outside Rust authority and Decision Lease
- no untracked manual mutation

Every attempt must produce enough evidence to reconstruct why the order was
allowed, what was sent, what filled, what fees/slippage occurred, and what would
have happened to matched controls.

### 5. Outcome Review

Review only candidate-matched outcomes:

- realized net PnL after actual fees and slippage
- maker/taker labels and fee provenance
- matched same-side-cell controls
- execution realism gaps
- regime/OOS labels
- proof-exclusion scan
- repeatability path

Positive result: propose scale, parameter mutation, or repeat/OOS test inside
the envelope.

Negative result: stop, quarantine, reduce scope, rotate candidate, or diagnose
loss drivers. Do not hide losses behind artifact success.

No result: diagnose execution blockers, touchability, fee, stale data, or
authority plumbing. Do not count non-fills as profitability proof.

### 6. Learning And Mutation

Learning output should become executable only through a reviewable proposal or a
standing-envelope-permitted parameter update. It must record:

- source evidence
- expected net PnL mechanism
- parameter delta
- loss-control limits
- rollback condition
- proof/exclusion status
- whether runtime mutation is permitted by the current envelope

The loop should prefer small profitable mutations that can be measured quickly
over large speculative rewrites.

### 7. Deployment And Hygiene

Source fixes, tests, runtime sync, and service changes are allowed when they
remove a blocker to profitable Demo evidence or loss control. The agent should
use the repo dispatch chains and leave an auditable trail, but it should not
repeat read-only audits when the next step is a source/runtime fix.

Runtime actions must preserve:

- no secrets in argv or artifacts
- sanitized evidence
- exact command/output provenance
- rollback or stop condition
- post-action health/evidence check

## Anti-Repeat Rules

Do not loop on a passive `defer`.

If an iteration sees the same non-actionable state twice, the next iteration
must rebase the work into one of:

- implement or deploy the missing plumbing
- rotate to another candidate
- reduce the experiment envelope
- mark the blocker as loss-control blocked
- update stale state pointers

The next action must be executable. It cannot be "observe again", "audit again",
"wait for cron", or "confirm learning is running" unless a specific new evidence
source is named.

## Profit Proof Rules

A profitability claim requires all of:

- candidate-matched orders/fills
- actual fees and slippage
- reconstructed entry/exit/markout
- matched controls
- proof-exclusion pass
- execution realism review
- repeat or OOS path

The following are never profit proof:

- artifact counts
- source smoke
- replay-only positives
- single-window MM positives
- `flash_dip_buy` cleanup or unrelated fills
- unattributed fills
- residual cleanup/risk-close fills
- stale local `Working` rows
- broad Demo activity from another candidate

## Current-State Pointers

Agents should not infer current tasks from this file. Use:

- `TODO.md` for the active queue and current runtime facts
- `docs/CLAUDE_CHANGELOG.md` for compact version history
- latest PM reports linked from `TODO.md` for evidence detail
- `/tmp/openclaw/alpha_discovery_throughput/` for current profitability and
  learning artifacts
- `/tmp/openclaw/cost_gate_learning_lane/` for current Cost Gate learning,
  false-negative, authorization, and probe artifacts
- `/tmp/openclaw/audit/` for runtime/exchange audit artifacts

If `TODO.md` is stale relative to verified runtime evidence, update `TODO.md`
rather than copying current facts into this loop document.
