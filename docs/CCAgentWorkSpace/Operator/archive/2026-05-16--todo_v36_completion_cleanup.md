# Operator Handoff — TODO v36 Completion Cleanup

Date: 2026-05-16
Role: PM

## Summary

Completed TODO detail from v35 / 2026-05-15..16 was cross-checked against
commits and reports, then moved to
`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.

`TODO.md` v36 is now the active queue: blockers, dependent gates, deferred work,
and runnable backlog remain visible; completed historical detail is archived.

## Important Preserved Blockers

- W-AUDIT-8a C1 is still blocked: the prior 24h liquidation proof ended
  `FAIL_CONNECTION` and is not proof-eligible.
- W-AUDIT-8b remains read-only Stage 0R only.
- True-live remains blocked by `P0-EDGE-1`, `P0-LG-1/2/3`, and `P0-OPS-1..4`.
- EDGE-P2-3 Phase 1b still depends on the 3-gate condition, Wave 3.5 Linux
  migration backlog, and `P1-BBMF3-WIRE-1`.

## Runtime Impact

None. This was docs-only cleanup after runtime/code-bearing v35 head `5f6f3edf`
had already been rebuilt and restarted on `trade-core`.
