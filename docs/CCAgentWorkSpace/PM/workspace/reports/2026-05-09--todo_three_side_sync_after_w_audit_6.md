# TODO Three-Side Sync After W-AUDIT-6 Cleanup

Date: 2026-05-09
Role: PM
Scope: docs / queue synchronization only

## Summary

- Refreshed `TODO.md` v16 latest-state text so W-AUDIT-6 no longer reads as only `bb_breakout` cooldown kickoff.
- Updated `CLAUDE.md` Strategy / Edge funding_arb line: retirement authority is `strategy_params_{paper,demo,live}.toml active=false`; the four `risk_config*.toml` files no longer carry funding_arb per-strategy overrides.
- Updated `.codex/MEMORY.md` stale TODO-version references and added the current W-AUDIT-6 ordering.
- Indexed this PM sync report in `docs/CCAgentWorkSpace/PM/memory.md`.

## Current W-AUDIT-6 Order

1. `ma_crossover` R:R trailing/TP rewrite.
2. `bb_breakout` 1m->5m RFC, then IMPL.
3. Portfolio VaR/CVaR/EVT as W-AUDIT-6c.

The 2026-05-16 `funding_arb` 14d audit remains a verification/history artifact, not the retirement authority.

## Runtime Boundary

This checkpoint is docs-only. No rebuild, restart, runtime reload, DB write, live auth mutation, strategy activation, or risk parameter apply was performed.
