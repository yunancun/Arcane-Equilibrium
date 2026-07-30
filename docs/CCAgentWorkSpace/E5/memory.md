# E5 Role memory

## Usage contract

- This hot file contains role-specific durable judgment only; it is not active state, a task log, a runtime ledger, or closure evidence.
- Load it only when the routed role and current task make the lessons relevant; do not preload every role memory.
- Normative policy, current source, typed Context, current TODO state, and fresh runtime or external evidence override historical memory.
- Persist task detail in the canonical closure or role report. Promote only a recurring heuristic, authority boundary, or prevention rule here.
- The cold archive is append-only evidence. Never edit an archived payload; use its digest-bound slice when exact history is required.

## Durable lessons

- Optimize from measured bottlenecks and call frequency, not file size or intuition; distinguish hot-path cost from infrequent control-plane work.
- Capacity models must include burst tails, all producers, consumer blocking windows, queue bounds, and observed drop or retry rates.
- Separate algorithmic latency, statistical tail, and platform scheduling floor before changing an SLA or implementation.
- Low-resolution timers can round real work to zero; state measurement resolution and use distributions rather than a single maximum.
- Reconstruct slow-run and shutdown claims from monotonic or append-only event timelines; buffered output can falsify apparent ordering.
- Child processes must not inherit governance locks or unrelated descriptors, and background configuration must be reproducible from versioned setup.
- Hot reload must update downstream derived copies as one contract; swapping the source object alone can leave runtime state silently stale.
- Source-only performance changes are dormant until the target binary is rebuilt and observed under the admitted runtime lane.

## Topical pointers

- Role reports: `docs/CCAgentWorkSpace/E5/workspace/reports/`
- Source pointer: `rust/openclaw_engine/`
- Source pointer: `helper_scripts/`

## Archive pointer

- Complete pre-compaction bytes: `docs/CCAgentWorkSpace/E5/memory-archive.md`
- Payload digest: `sha256:80ec55f1d37a2901c93fd2b782efd9d1aba3a377ad1959b3e3bdaeb7fefa6300`
- Payload slice: offset `33618`, bytes `26778`
- Pointer digest: `sha256:0710e818b2007cbf5cb163e9d7d975de842d5e02a76e3a5f22ad51640ccb7fea`
- Recovery manifest: `docs/agents/role-memory-compaction-v1.json`
