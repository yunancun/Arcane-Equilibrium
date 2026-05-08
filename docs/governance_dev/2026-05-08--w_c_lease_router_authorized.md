# W-C Lease Router Evidence Authorization

Date: 2026-05-08
Recorded: 2026-05-09
Status: Active authorization record
Scope: MAG-082 Stage 2 demo/live_demo evidence collection

## Decision

Operator authorized enabling `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` on Linux
`trade-core` for W-C Stage 2 evidence collection, together with
`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`.

This keeps the Decision Lease router-gate evidence path ON while the MAG-082
24h window collects runtime lineage.

## Allowed

- Write shadow Agent Spine lineage for:
  StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
  Decision Lease / idempotency -> ExecutionReport.
- Record router-gate bypass / lease ids into shadow ExecutionPlan rows.
- Run read-only healthchecks, SQL audits, watchdog checks, and reports.
- Keep LiveDemo on the Bybit demo endpoint under existing live-grade controls.

## Not Authorized

- No true Mainnet live traffic.
- No live authorization renewal, revoke, or manual authorization file writing.
- No Executor shadow unlock or new order authority.
- No strategy/risk parameter change.
- No scanner hard authority, scanner mode switch, or scanner hard gate.
- No MAG-083 final release PASS or MAG-084 operator sign-off.
- No Stage 3 / Stage 4 promotion.

## Evidence at Recording Time

- Linux source synced to `b91487f2`.
- Runtime process env proved:
  - `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`
  - `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`
  - `OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv`
- `settings/risk_control_rules/scanner_config.toml` has no `[authority]`.
- `[55] agent_decision_spine_lineage` PASS at 2026-05-08 22:09 UTC:
  `objects=505/505`, `edges=404/404`, `idempotency=101/101`,
  `chains=101`, `chains_with_lease=76`, `chains_with_report=101`,
  `bad_report_quality=0`.
- MAG-082 readiness remains `LINEAGE_READY_NOT_WINDOW_PASS`.
- Passive healthcheck after `[41]` source fix returned `SUMMARY: WARN`, not
  FAIL, at 2026-05-08 22:08 UTC.

## Rollback

If W-C evidence collection causes runtime instability or lineage corruption,
operator rollback is:

1. set `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` in the runtime env source;
2. rebuild/restart only with explicit operator approval;
3. verify watchdog, `[55]`, and passive healthcheck output after restart;
4. record the rollback in this directory or a dated PM report.

## Cross-References

- Amendment: `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- Current queue: `TODO.md` W-C and W-AUDIT-1
- Runtime boundary: `CLAUDE.md` §三 / §四 / §五
