# Operator Brief: SignalSpec Conformance TODO Relocation

Date: 2026-06-18
Owner: PM

## What Changed

`P2-AST-SIGNALSPEC-CONFORMANCE` was moved from `TODO.md` §5 to §7.

Reason: it is not an active engineering dispatch right now. The old row still said the SignalSpec producer existed only on an unmerged branch, but source now exists on main and the residual-producer baseline/history is already archived. The remaining blocker is formal SignalSpec schema freeze plus PA/PM GO.

## Important Boundary

This does not mean the checker is complete or approved for implementation. It also does not activate residual or Stage0R flags.

If reopened, it should be scoped as a `SignalSpec schema/lineage conformance checker`, not an expression-tree AST checker.

## Boundary

Docs/status correction only. No runtime, DB, auth, risk, order, or trading changes.
