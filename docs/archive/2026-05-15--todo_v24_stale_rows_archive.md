# TODO v24 Stale Rows Archive — 2026-05-15

**Owner chain**: PM -> PA(default) -> FA(default) -> PM
**Scope**: active queue cleanup only. No code, config, DB, auth, runtime, paper,
demo, live_demo, or live change.

## Why Archived

PM/PA/FA reviewed the last 5 days of work and found several TODO / README /
MEMORY statements that were correct as historical checkpoints but misleading as
active work. TODO v25 keeps the active queue lean and moves these stale claims
here.

## Archived / Superseded Items

| Source text / row | Archived because |
|---|---|
| 2026-05-09 current demo state snapshot (`5 strategies 7d demo gross -26.44 USDT`, attribution `0.5041%`) | Historical loss-audit context only. Current active truth is 2026-05-15 Stage 0R GATE-RED + P0-EDGE active. |
| `13-agent v3 verification ... V079 完全未 apply / cron 未 install / engine 仍跑 5/8 binary` | Superseded. `trade-core` now has migrations through V090 applied, V079 is present, and `learning.strategy_trial_ledger` has 16,212 rows. |
| `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE ... ADR-0021 待` | Superseded by ADR-0022 strategist-cap-wide-parameter-adjustment skill; ADR-0021 was already alpha-source architecture. |
| `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON ... V079 待 apply` | Runtime V079 concern closed by 2026-05-15 read-only verification. Future promotion callers still require green demo evidence and governance gates. |
| `P0-V3-V079-NOT-APPLIED` | Closed. `_sqlx_migrations` max=90; V079 applied; `learning.strategy_trial_ledger` exists with 16,212 rows. |
| `P0-V3-PA-SPEC-FIX` | Closed by BB final compatibility review: L50 not L25, liquidation pulse dormant/requires revival, basis observation-only until mainnet spot capability. |
| `P0-V3-ADR-0021-ARCH-04` | Closed by ADR-0021, ADR-0022, ARCH-04, CONTEXT entries, AMD-2026-05-10-03, and AMD-2026-05-10-04. ARCH-04 Stage 1 paper semantics were later superseded by AMD-2026-05-15-01. |
| `P0-V3-ENGINE-RESTART` old 5/8 binary wording | No longer an active blocker. Current runtime checks on 2026-05-15 are against the current source line; Linux worktree dirty WIP is a separate sync issue. |
| Active-plan `[55] 24/138` blocker | Superseded by P1-HEALTHCHECK-55-INVARIANT: `25/25` fully-filled plan chains have real-fill ER, `0` missing, `13` partial chains are diagnostic. |
| Active-plan `[67] active feature_baselines=0` blocker | Superseded by feature baseline apply: 646 active rows / 19 symbols / 34 feature names, standalone `[67]` PASS. |

## Current Priority After Cleanup

1. No paper promotion, no Stage 1 demo canary, no true-live authority until a
   future Stage 0R packet is green and governance gates are satisfied.
2. Alpha path: A4-C revise-or-archive / diagnostic maturity, then W-AUDIT-8a
   Phase C/D, `8c` liquidation, and `8b` funding skew.
3. True-live prerequisites: `P0-EDGE-1`, `P0-LG-1/2/3`, `P0-OPS-1..4`.
4. Runtime/observability hardening: clear `P1-INTENT-FREEZE-27`, then
   fill-lineage monitor, startup burst, V083 current-log follow-up, feature
   baseline burn-in, W6-5 metrics.
5. P2 hygiene / GUI / AI UX cleanup after the above gates.
