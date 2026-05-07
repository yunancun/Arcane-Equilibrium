# TODO v12 Archive: Agent/OpenClaw Replan

Date: 2026-05-07
Archived from: `TODO.md` v12 at commit `66cbc0e1`
New active queue: `TODO.md` v13

## Why This Archive Exists

`TODO.md` had become a mixed historical ledger and active queue. After the
latest AgentTodo M8 fast-track NO-GO and the accepted OpenClaw control-plane
repositioning, the active queue needed to remove stale or completed work so the
next PM/E1/E2/E4 handoff starts from the current architecture.

The full pre-replan TODO can be recovered from git:

```bash
git show 66cbc0e1:TODO.md
```

## Removed From Active TODO

### Completed or Historical

- REF-20 Sprint A-D closure narrative and Wave 1-9 details.
- REF-21 replay availability / scanner timeline / migration dry-run closure
  details.
- AgentTodo Sprint A, M2, M3, M4, M5, M6, and M7 completed milestone tables.
- MAG-080/MAG-081/MAG-082 policy/checklist completion details.
- P1 healthcheck FAIL queue closure details for `[Xb]`, `[42]`, `[50]`, and
  `[51]`; these are now summarized as closed/downgraded in v13.
- Full healthcheck implementation inventory `[1]..[53]`, `[Xa]`, `[Xb]`;
  the scripts are the source of truth.
- Old observation values from early May snapshots.

### Superseded By OpenClaw Repositioning

- Any work implying OpenClaw Gateway is the trading conductor.
- Any work implying a second OpenClaw GUI or iframe.
- Legacy `OC-1~6` gateway sequencing; active work is now:
  read-only brief/diagnostics/escalations first, proposal/mobile relay later.
- Slack alert evaluation unless the operator explicitly reopens it; active
  external workflow posture remains Linear-only.

### Obsoleted By Governance Change

- LOC tickets that only existed because the old hard cap was 1500 and the file
  is now below the 2000 hard cap.
- Replay routes cap tickets already resolved by Sprint B extraction.
- Historical "near cap" LG5 consumer split item that no longer violates the
  current governance threshold.

### Replaced By v13 Active Work

- Generic "continue AgentTodo" guidance is replaced with:
  1. executor fake-live runtime smoke;
  2. runtime decision-spine lineage wiring;
  3. new MAG-082 Stage 2 evidence window;
  4. MAG-083/MAG-084 only after PASS;
  5. OpenClaw read-only observability expansion before proposal/mobile.
- P0-LG dates are now planning windows, not automatic authorization.
- Replay work is now empirical calibration maturity, not availability.

## Still Active After Replan

- MAG-082 runtime lineage remains NO-GO and blocks MAG-083/MAG-084.
- P1-FAKE-1 still needs explicit fake-live runtime smoke.
- OpenClaw read-only foundation can expand to backend-authored brief,
  diagnostics, and escalations.
- Live Gate H0/pricing/supervised-live, edge decision, credential/HTTPS/legal
  and runbook work remain true-live blockers.
- Funding arb audit on 2026-05-16 and the 2026-05-09 3C audit remain scheduled
  only if their source data is still relevant.
