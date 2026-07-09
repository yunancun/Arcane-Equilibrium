# P1-INTENT-FREEZE-27 Post-Grace Closure

Date: 2026-05-15  
Scope: Runtime read-only verification after the `7b33ab2e` rebuild. No rebuild, restart, DB write, config change, auth renewal, paper launch, or demo-canary action.

## SSH Note

Codex short-name `ssh trade-core` was inconsistent in this session because the sandbox could not use the same resolver/agent path as the operator shell. The working Codex route was:

`ssh -o BatchMode=yes -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_mac trade-core.tail358794.ts.net ...`

This confirmed Linux `trade-core` was clean at docs head `8ab4abd9`.

## Probe Result

Post-grace narrow health probe at `2026-05-15T18:12Z`:

```text
[27] intents_counter_freeze|PASS|demo: stale=3.4m, 30min_n=4 | live_demo: stale=192.0m, 30min_n=0, verdicts_30min=0, approved_verdicts_30min=0, dcs_30min=0 — mode inactive in 30min window | live: never produced an intent
[66] panel_freshness|PASS|funding=PASS(57s), oi_delta=PASS(57s)
[67] feature_baseline_readiness|PASS|active_rows=646 active_symbols=19 feature_names=34/34
```

The `[27]` output no longer used the fresh-restart grace explanation. `live_demo` had no verdict/DCS activity in the 30-minute window, so it is inactive rather than frozen.

## Verdict

`P1-INTENT-FREEZE-27` is closed.

This does not authorize Stage 1 demo or true-live:

- A4-C Stage 0R remains GATE-RED.
- OI-confirmed 5m feasibility remains underpowered/negative.
- Signed live authorization is absent.
- Full passive wrapper previously hung after rebuild; a future full-suite passive rerun is still useful, but the `[27]` hard blocker is cleared.
