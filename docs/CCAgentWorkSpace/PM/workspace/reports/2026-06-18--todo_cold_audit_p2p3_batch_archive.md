# TODO v189 Cold-Audit P2/P3 Batch Archive

**Date**: 2026-06-18
**Scope**: TODO queue hygiene only

## Decision

Archived `AUDIT-2026-06-14-P2P3-BATCH` out of `TODO.md` §5.

The row described a completed cold-audit Batch 4/5 fix wave plus several deferred tails. Keeping it in the active engineering queue now misstates the work shape: the safe fixes are done, and the residual items are policy, architecture, doc hygiene, or future perf follow-up.

## Evidence

- Cold-audit fix-wave body was completed and deployed by the v161 checkpoint (`c7f97f50` + Linux rebuild/restart).
- `daily_cost_snapshot.sh` broken-cron action was superseded by v167 read-only Linux recheck: current crontab had no `daily_cost_snapshot` line and repo/Linux had no such script.
- `AUDIT-2026-06-14-DIRTY-FIX` was archived in v169.
- `AUDIT-2026-06-14-MIGRATION-TREE-1` was archived in v171 after implementation/deploy/checksum repair.
- 110009 retCode semantics drift was closed separately in v186.

## Preserved Future Gates

`TODO.md` §7 now carries `P2-COLD-AUDIT-P2P3-BATCH-FOLLOWUP`. Reopen an active row only if one of these conditions becomes actionable:

- operator/QC/AI-E/PA chooses the cost-edge re-gate policy;
- PA/AI-E chooses AI-PRICING option1 SSOT merge plus `last_verified` architecture;
- BB/PA doc hygiene window updates the rate-limit dictionary;
- perf sprint explicitly takes the PERF-1 1m timeframe minor follow-up.

## Boundary

Docs/TODO/changelog/memory/report/index hygiene only. No CI, no source/code change, no deploy/rebuild/restart, and no production runtime/DB/auth/risk/order/trading mutation.
