# ADR 0020: Layer2 Is Manual Supervisor Escalation, Not Autonomous Loop

Date: 2026-05-09
Status: Accepted

## Context

W-AUDIT-7 kept Layer2 trigger routes behind operator and scope gates. The
remaining question was whether to schedule an autonomous hourly Layer2 loop or
keep Layer2 as a manual operator/supervisor workflow.

## Decision

Layer2 is GUI/manual supervisor escalation by design. It may summarize context,
prepare proposals, and record AI invocation cost/lineage when an operator or
approved supervisor flow triggers it.

Layer2 must not run as an autonomous trading loop, mutate strategy/risk/live
configuration, grant live authorization, submit orders, or bypass Rust
execution authority.

## Consequences

- W-AUDIT-7 keeps manual trigger and observability work.
- The planned hourly Layer2 autonomous loop is sunset unless a future ADR
  explicitly reverses this boundary.
- Cost, prompt, and context-distillation work remains useful for manual
  escalation packets.
