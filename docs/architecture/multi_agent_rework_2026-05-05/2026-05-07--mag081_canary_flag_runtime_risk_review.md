# MAG-081 Canary Flag Runtime Risk Review

Date: 2026-05-07
Status: risk review only, no runtime flag change
Review role: PM-local E3-style review

## Verdict

No reviewed canary flag can, by itself, enable true live autonomy without
operator approval.

This verdict is conditional on the current code surfaces reviewed for MAG-081:
Agent event-store health flags, Agent Spine client enablement/mode metadata,
scanner authority mode, Decision Lease router flag, ExecutorAgent shadow mode,
Mainnet opt-in, signed live authorization, OpenClaw read-only routes, H-state,
and cost-edge advisor gates.

Primary/live autonomy remains blocked until MAG-084 written operator sign-off.
MAG-081 does not authorize a flag flip, rebuild, restart, deploy, DB write,
live authorization renewal, or trading authority change.

## Required Conjunction For True Live

True live order flow still requires more than one flag:

1. Operator-authenticated live control-plane action.
2. Global mode exactly `live_reserved` for live authorization and live executor
   shadow unlock paths.
3. Signed, unexpired `authorization.json` written by the Python live trust
   route and accepted by Rust `live_authorization::load_and_verify`.
4. For Mainnet, `OPENCLAW_ALLOW_MAINNET=1` plus non-empty live secret-slot
   credentials; Mainnet environment credentials alone remain ignored by the
   Rust REST client.
5. Rust live pipeline startup through `build_exchange_pipeline`.
6. H0/P0/P1 risk gates.
7. GuardianVerdict and ExecutionPlan lineage required by the AgentTodo cutover
   policy before primary use.
8. Decision Lease for real submit once the router-side lease canary is in
   scope.
9. Executor submit path not in shadow mode for the targeted engine.
10. MAG-084 operator sign-off for primary.

No single item in the review table satisfies that conjunction.

## Reviewed Surfaces

| Surface | Enable path | Single-flag live-autonomy risk | Reason | Rollback |
|---|---|---|---|---|
| Agent event store | `OPENCLAW_AGENT_EVENT_STORE_ENABLED=1`; optional `OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED=1` | No | Healthcheck `[52]` only checks recent `agent.messages`, `agent.state_changes`, and `agent.ai_invocations`. Health-required escalates missing rows from WARN to FAIL; it does not submit orders, mutate configs, or grant auth. | Unset `OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED`; disable event store only if the writer itself causes an incident. |
| Agent Spine client | `OPENCLAW_AGENT_SPINE_CLIENT_ENABLED=1`; Python ctor `authority_mode`, default `shadow` | No | The Python client is a typed fail-soft writer/reader. It records objects, edges, transitions, and idempotency rows; it does not call Bybit or mutate Rust risk/config. The design-doc `OPENCLAW_AGENT_SPINE_MODE` is not a Python runtime env read in the current client, so env drift on that name cannot silently change Python publish authority today. | Set mode back to `shadow`; if writer health regresses, set `OPENCLAW_AGENT_SPINE_CLIENT_ENABLED=0`. |
| Rust Agent Spine mode metadata | `AgentSpineMode` on stored events | No | Mode is stored as object/event metadata and validated by tests. Current runtime startup remains default-disabled/unwired as an authority router. | Return to `shadow` metadata before any canary evidence capture. |
| Scanner authority | `settings/risk_control_rules/scanner_config.toml` `[authority].mode` values: `legacy_gate`, `advisory_shadow`, `advisory_enforced` | No, but this is a real candidate-flow change | `legacy_gate` is the only mode that enforces the legacy scanner new-open block. Advisory modes record legacy would-block evidence and allow the intent to continue to the normal governance path. That can change demo/live_demo candidate flow, but it still does not create Guardian approval, ExecutionPlan, lease, executor unlock, live auth, or Bybit credentials. | Set `[authority].mode = "legacy_gate"` and restart/reload the affected runtime config path. |
| Decision Lease router gate | `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`, read once at `GovernanceCore::new()` | No | Flag ON adds router-side lease consultation. In Production without effective auth it fails closed; in Exploration/Validation it uses bypass semantics and does not touch the live lease state machine. It cannot create live authorization or executor submit authority. | Set `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`; restart affected runtime so boot-time env is reread. |
| Executor submit shadow mode | `patch_risk_config` for `executor.shadow_mode=false`; HTTP route `/api/v1/executor/shadow-toggle` | Not by itself | This is the highest-risk surface because `false` lets Python ExecutorAgent send SubmitOrder IPC instead of returning a shadow report. The HTTP route requires Operator role for demo/paper and full live 5-gate for live. Live unlock requires `live_reserved`, Mainnet env when applicable, live secret slot, valid signed authorization, and HMAC verification. It still does not choose symbol/direction outside the approved intent path. Raw IPC access is not treated as an approved canary flag path. | Patch `executor.shadow_mode=true` for each affected engine; audit IPC/socket access if any raw patch is suspected. |
| Mainnet env opt-in | `OPENCLAW_ALLOW_MAINNET=1` | No | Rust `BybitRestClient::new(Mainnet, ...)` still requires live slot credentials and ignores Mainnet env-var credential fallback. Live pipeline startup also requires signed authorization. | Unset the env and restart affected runtime before Mainnet can be constructed again. |
| Signed live authorization | `POST /api/v1/live/auth/renew` or `/renew-review` writes `authorization.json` | No, because it is an approval artifact, not a flag | The file can only be produced by an Operator path that first requires `live_reserved` and `OPENCLAW_IPC_SECRET`. Rust rejects missing, malformed, bad-signature, expired, wrong-env, or non-`live_reserved` records. By itself it does not change executor shadow mode or strategy scope. | Revoke through the live auth path. Break-glass deletion of `authorization.json` must be logged and followed by watcher/engine status proof. |
| OpenClaw Gateway active routes | Active allowlist: `GET /api/v1/openclaw/status`, `GET /api/v1/openclaw/self-state` | No | Current OpenClaw posture reports `can_submit_orders=false`, `can_cancel_orders=false`, `can_close_positions=false`, `can_mutate_live_config=false`, `can_mutate_risk_config=false`, `can_read_secrets=false`, and deferred workflows disabled. No proposal/approval/write route is active in Sprint A/M8. | Remove any unexpected non-GET OpenClaw route; fail the canary until the allowlist is restored. |
| H-state gateway | `OPENCLAW_H_STATE_GATEWAY=1` | No | The gateway constructs a fire-and-forget H-state invalidator. Disabled path PASS-skips; enabled path validates IPC registration. It carries cache invalidation hints, not order authority. | Unset `OPENCLAW_H_STATE_GATEWAY`; verify passive check returns dormant/PASS-skip. |
| Cost-edge advisor | `OPENCLAW_COST_EDGE_ADVISOR=1` | No | Healthcheck treats disabled as dormant. Phase A checks TOML/module invariants and advisor thresholds; it does not create order authority or bypass Guardian/lease/executor gates. | Unset `OPENCLAW_COST_EDGE_ADVISOR`; verify dormant/PASS-skip. |
| Supervisor cloud policy | MAG-019 policy module | No | Cloud is default-disabled; future allowed calls must reserve `agent.ai_invocations` before provider IO. It has no order, live TOML, secret, or deploy capability. | Disable supervisor cloud config and fail canary if hidden cloud IO appears. |

## Risk Scenarios

### Scanner Advisory Flip Alone

Fact: in advisory modes, the scanner active-universe and route would-block
conditions are recorded instead of suppressing the new-open intent at the
legacy scanner gate.

Inference: this can increase candidate flow into the normal governance path,
so it must remain Stage 2 demo/live_demo only until MAG-082 evidence exists.

Boundary: it cannot directly close, reduce, submit, or authorize live. A trade
still needs downstream governance, execution planning, lease handling, and an
unshadowed executor path.

### Lease Router Flag Alone

Fact: `OPENCLAW_LEASE_ROUTER_GATE_ENABLED` is read at GovernanceCore
construction. When enabled, router gate errors return rejection; when disabled,
the gate short-circuits.

Inference: the flag is risk-reducing for Production if auth is missing because
it fails closed. It does not grant auth.

Boundary: Stage 2 canary may enable it only with rollback owner present and
lease audit evidence visible.

### Executor Shadow False Alone

Fact: ExecutorAgent defaults to shadow. With shadow false, it sends SubmitOrder
IPC to Rust. The operator HTTP route applies full live gates before live
unlock and only Operator role for demo/paper.

Inference: this surface can turn approved demo/live_demo intent flow from
shadow observation into submit attempts, so it is the most operationally
sensitive canary control.

Boundary: a live engine shadow unlock still needs the live 5-gate chain. Raw
IPC mutation is outside the approved canary path and should be treated as an
incident, not a valid flag flip.

### Mainnet Env Alone

Fact: `OPENCLAW_ALLOW_MAINNET=1` only clears one Rust Mainnet guard. Mainnet
still needs live slot credentials, and the Live pipeline still requires signed
authorization.

Inference: setting the env accidentally is insufficient to create a live
autonomous pipeline.

Boundary: Mainnet env should stay unset outside an approved live window.

### Signed Authorization Alone

Fact: Rust verifies HMAC, expiry, env, schema version, and
`approved_system_mode=live_reserved`. The Python writer requires
`OPENCLAW_IPC_SECRET` and live_reserved first.

Inference: a valid file proves a prior operator approval path, but does not
select strategy/symbol scope, disable executor shadow, or bypass risk gates.

Boundary: stale or unexpected valid authorization is a live-auth anomaly and
forces rollback/revoke before further canary work.

## GO / NO-GO

MAG-081 permits proceeding to MAG-082 checklist design for Stage 2
demo/live_demo canary evidence. It does not permit Stage 3 or Stage 4.

Stage 2 GO only if:

- Engine scope is demo or live_demo.
- Exact flags and rollback owner are recorded.
- Executor live engine remains shadowed unless a separate operator-approved
  live 5-gate review is performed.
- OpenClaw remains read-only.
- No proposal/approval relay is introduced in this M8 canary.

Stage 3/4 NO-GO until:

- MAG-082 24h checklist is complete.
- MAG-083 final release audit proves no execution without StrategistDecision,
  GuardianVerdict, ExecutionPlan, and Decision Lease.
- MAG-084 written operator sign-off exists.

## Rollback Bundle

Use the smallest rollback that restores the violated boundary:

```bash
# Lease router
export OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0

# Scanner authority
# Set settings/risk_control_rules/scanner_config.toml:
# [authority]
# mode = "legacy_gate"

# Agent Spine writer
export OPENCLAW_AGENT_SPINE_CLIENT_ENABLED=0

# Event-store health hard fail
unset OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED

# H-state / cost-edge advisory gates
unset OPENCLAW_H_STATE_GATEWAY
unset OPENCLAW_COST_EDGE_ADVISOR
```

Executor rollback payload:

```json
{
  "jsonrpc": "2.0",
  "method": "patch_risk_config",
  "params": {
    "engine": "demo",
    "source": "operator",
    "patch": {"executor": {"shadow_mode": true}}
  },
  "id": "rollback-executor-shadow-demo"
}
```

Repeat the same executor rollback for any affected `paper` or `live` engine
scope.

Live-auth anomaly rollback:

- Revoke through the live auth route when possible.
- If break-glass deletion of `authorization.json` is used, log actor, reason,
  path, time, and follow with Rust watcher/engine status proof.

Post-rollback evidence:

```bash
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
bash helper_scripts/db/passive_wait_healthcheck.sh
```

## MAG-081 Result

MAG-081 is complete as a runtime risk review. The current code/policy surface
does not contain a single reviewed flag that can accidentally enable live
autonomy without approval. The highest-risk surface is executor
`shadow_mode=false`, and it remains gated by Operator role plus the full live
5-gate chain for live engine use.
