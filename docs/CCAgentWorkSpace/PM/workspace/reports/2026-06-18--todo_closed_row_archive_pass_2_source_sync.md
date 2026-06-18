# TODO v169 Closed-Row Archive Pass #2 + Source Sync

Date: 2026-06-18
Role: PM
Scope: TODO/changelog/memory/report hygiene only

## Verdict

`TODO.md` v169 keeps the active queue narrower by archiving five completed rows that no longer carry an executable next action:

- `AUDIT-2026-06-14-PERF-123`
- `AUDIT-2026-06-14-DIRTY-FIX`
- `V5.8-PAUSE-READINESS`
- `P0-EDGE-1-POST-DEPLOY-QA-A1A2BA4`
- `CODE-SIMPLIFY-D-CLOSED`

The active facts they still matter to are preserved elsewhere:

- cold-audit fix-wave reports/changelog cover PERF and DIRTY-FIX;
- V5.8 freeze / resume posture remains in TODO §3.1;
- A1/A2/B/A4 follow-up path is carried by `P1-BB-REVERSION-REGIME-OBSERVABILITY` and Stage0R event triggers;
- `CODE-SIMPLIFY-D-CLOSED` remains in the archive marker with no-reopen semantics.

## Source Sync

The prior docs checkpoint `e4e1b7a3` was already pushed to GitHub and fast-forwarded on Linux `trade-core`. Linux status after that sync had only unrelated untracked artifacts:

- `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md`
- `helper_scripts/research/variance_risk_premium/`

This pass updates the TODO masthead and §0 source-sync pointer to reflect that checkpoint.

## Boundary

No code/source change, CI, deploy, rebuild, restart, DB migration/write, auth, risk, order, or trading mutation was performed.
