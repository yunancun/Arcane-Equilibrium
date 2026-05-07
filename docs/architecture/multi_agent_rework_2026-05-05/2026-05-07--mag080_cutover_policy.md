# MAG-080 Cutover Policy: Shadow -> Canary -> Primary

Date: 2026-05-07
Status: policy only, no runtime flag change

## Non-Negotiable Boundary

This policy does not authorize live autonomy. Any move beyond shadow requires
operator approval, current Linux evidence, and the rollback commands below.
OpenClaw Gateway remains communication/supervisor/proposal relay only.

No stage may bypass:

- Rust execution authority.
- GuardianVerdict approval or modification.
- ExecutionPlan lineage.
- Decision Lease for any real submit.
- H0/P0/P1 protective risk gates.
- Operator live-auth requirements.

## Control Surfaces

| Surface | Shadow value | Canary value | Primary candidate value | Rollback |
|---|---|---|---|---|
| Agent event store | `OPENCLAW_AGENT_EVENT_STORE_ENABLED=1`; health visible | same, plus `OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED=1` | same | unset health-required first, then disable only if writer causes incident |
| Agent spine client | `OPENCLAW_AGENT_SPINE_CLIENT_ENABLED=1`, authority mode `shadow` | authority mode `canary` only after MAG-081 review | authority mode `primary` only after MAG-084 sign-off | mode back to `shadow`; if needed `OPENCLAW_AGENT_SPINE_CLIENT_ENABLED=0` |
| Scanner authority | `[authority].mode = "legacy_gate"` or `"advisory_shadow"` | `"advisory_enforced"` only for demo/live_demo canary | `"advisory_enforced"` after full lineage gates pass | set `[authority].mode = "legacy_gate"` |
| Decision Lease router | `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` unless running explicit lease canary | `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` for canary window after lease audit health passes | `1` | set `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` and restart affected runtime |
| Executor submit | `executor.shadow_mode=true` | demo/live_demo only, never true live without sign-off | primary only after MAG-084 | `patch_risk_config` executor shadow back to `true` |

## Stage 0: Baseline Shadow

Allowed:

- Persist StrategySignal, StrategistDecision, GuardianVerdict, ExecutionPlan,
  ExecutionReport, and AnalystInsight as shadow evidence.
- Compare scanner advisory output against legacy gating.
- Run replay and demo/live_demo research-only evidence.

Required before leaving Stage 0:

- 24h no spine writer serialization failures.
- 100% of sampled ExecutionPlans have prior StrategistDecision and
  approved/modified GuardianVerdict.
- 0 Executor symbol/direction authority mismatches.
- 0 unleased real-submit attempts.
- Event-store health row proof is PASS or explicitly degraded with reason.

## Stage 1: Shadow Soak

Duration: at least 24h on Linux `trade-core`.

Minimum thresholds:

- At least 50 complete decision chains, or all chains in the 24h window if
  fewer than 50 decisions occurred.
- 100% lineage completeness for new-open chains:
  StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan.
- 100% Guardian verdict presence before any ExecutionPlan.
- 100% ExecutionPlan symbol/direction copied from StrategistDecision.
- 0 direct close/reduce caused by scanner decay or Analyst risk pattern alone.
- 0 Decision Lease acquisition failure hidden as success.

Rollback trigger:

- Any P0/P1 bypass, missing lineage, symbol/direction mismatch, or false
  execution success immediately returns to Stage 0.

## Stage 2: Canary

Scope:

- Demo/live_demo only.
- No true-live primary autonomy.
- Canary must be time-boxed to 24h and named in the operator log.

Entry requirements:

- Stage 1 thresholds passed.
- MAG-081 runtime risk review completed.
- Operator records exact flags, engine scope, start time, and rollback command.
- Decision Lease router canary evidence is green if lease router flag is part
  of the canary.

Canary thresholds:

- 100% real-submit candidates have ExecutionPlan + lease ID.
- 0 order submit outside the approved engine scope.
- 0 scanner/Analyst direct trading authority.
- 0 cloud call unless supervisor budget policy has a reserved
  `agent.ai_invocations` row first.
- At least 95% lineage writer success over canary chains; any failed write is
  visible and does not become fake success.

Rollback:

```bash
export OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0
# Set scanner config [authority].mode back to "legacy_gate".
# Patch each affected engine executor shadow mode back on:
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
```

If runtime config patch is available, executor rollback must use:

```json
{
  "jsonrpc": "2.0",
  "method": "patch_risk_config",
  "params": {
    "engine": "demo",
    "source": "operator",
    "patch": {"executor": {"shadow_mode": true}}
  },
  "id": "rollback-executor-shadow"
}
```

## Stage 3: Primary Candidate

This is not live authorization.

Entry requirements:

- Stage 2 canary completed without rollback.
- 7d demo/live_demo audit shows no P0/P1 lineage or authority violation.
- Replay/canary reports show positive or explicitly accepted execution-quality
  evidence for the target strategy/symbol class.
- MAG-082 24h checklist completed.
- E3 review confirms no flag can accidentally enable live autonomy.

Primary-candidate thresholds:

- 100% new-open chain completeness.
- 100% lease-bound real submits.
- 0 unauthorized engine routing fallback to primary.
- 0 direct Bybit key/live TOML/proposal relay bypass.
- 0 hidden cloud-provider call.

## Stage 4: Primary

Primary can only be entered after MAG-084 operator sign-off.

Primary requires:

- Written operator sign-off.
- Exact engine scope.
- Exact strategy/symbol scope.
- Maximum notional and daily loss boundaries.
- Rollback owner present.
- Live auth current and explicitly enabled.

Any one of these incidents forces immediate rollback:

- Missing GuardianVerdict.
- Missing ExecutionPlan.
- Missing Decision Lease for real submit.
- Symbol/direction source not `strategist_decision`.
- Scanner/Analyst direct order or direct close authority.
- Unexpected engine fallback to live/primary.
- Any live-auth or Bybit key handling anomaly.

## Operator Checklist

Before any stage promotion, the operator must record:

- Current git commit on Mac, origin, and Linux.
- Engine scope.
- Strategy/symbol scope.
- Flag values.
- Start time and planned stop time.
- Evidence query or report path.
- Rollback command.
- Sign-off identity.

## MAG-080 Result

MAG-080 defines the policy only. No flag was changed, no rebuild or restart was
performed, and no trading authority changed.
