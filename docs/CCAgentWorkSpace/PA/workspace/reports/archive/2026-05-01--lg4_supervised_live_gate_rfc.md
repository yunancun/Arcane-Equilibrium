# LG-4 Supervised Live Gate RFC

Date: 2026-05-01
Owner: PA
Status: RFC complete

## Objective

LG-4 defines the supervised live gate between LiveDemo/live-grade observation
and any true live order authority. It does not grant autonomous live trading.
It specifies the operator approval flow, risk-limit override shape, kill switch,
and audit mirror required before a live session can be considered supervised.

## Non-Negotiable Boundaries

- Operator role auth remains mandatory.
- `live_reserved` global mode remains mandatory on the Python side.
- Rust mainnet still requires `OPENCLAW_ALLOW_MAINNET=1`.
- Valid signed `authorization.json` remains mandatory.
- Live actions still require GovernanceHub + Decision Lease.
- ML/Dream/agents cannot directly mutate live parameters or submit live orders.

## Proposed State Machine

```text
draft_request
  -> operator_review
  -> supervised_live_candidate
  -> signed_authorization
  -> live_reserved_session
  -> lease_bound_live_action
  -> closed_or_revoked
```

Rejected or expired requests return to `draft_request`; kill switch can revoke
from any non-terminal state.

## Approval RPC Schema

Endpoint shape:

```json
{
  "request_id": "uuid",
  "engine_mode": "live",
  "scope": {
    "symbols": ["BTCUSDT"],
    "strategies": ["ma_crossover"],
    "max_duration_minutes": 60
  },
  "risk_limits": {
    "max_position_notional_usd": 50.0,
    "max_daily_loss_usd": 25.0,
    "max_orders": 10,
    "max_leverage": 1.0
  },
  "operator_reason": "supervised smoke",
  "expires_at": "RFC3339 timestamp"
}
```

Validation:

- `engine_mode` must be true live, not `live_demo`.
- `expires_at` must be short-lived.
- Every symbol and strategy must be explicitly enumerated.
- Limits must be stricter than or equal to P1 hard ceilings.
- The request cannot widen live authorization; it can only consume an already
  valid authorization window.

## Risk Limit Override Flow

- Overrides are session-scoped and lease-bound.
- They live outside permanent `risk_config_live.toml`.
- Effective limit = min(P1 hard ceiling, session override, strategy/risk config).
- Overrides are auditable and expire with the supervised session.
- No restart-to-apply path is allowed.

## Kill Switch

Two independent paths must exist:

- API path: operator route revokes supervised live session and Decision Leases.
- IPC path: Rust-local kill command cancels pending lease-bound live actions and
  forces fail-closed for new live intents.

Both paths emit the same audit event and must be safe to call repeatedly.

## Audit Mirror

Mirror SM-04 style fields:

- `event_id`
- `ts`
- `operator_id`
- `request_id`
- `decision_lease_id`
- `engine_mode`
- `symbols`
- `strategies`
- `risk_limits`
- `action`
- `result`
- `reason`

Audit rows are append-only. No successful supervised live action is valid unless
the request, approval, lease, and execution result can be joined by ids.

## Acceptance Tests

- Non-operator approval request returns 403.
- Missing `live_reserved` rejects.
- Expired request rejects.
- Scope widening rejects.
- Missing signed authorization rejects.
- Valid request creates a short-lived supervised candidate but no order.
- Decision Lease is required for any live action.
- API kill switch revokes session idempotently.
- IPC kill switch revokes session idempotently.
- Audit join reconstructs request -> approval -> lease -> result.

## Rollback

- Revoke supervised session.
- Revoke active Decision Leases.
- Clear session-scoped overrides.
- Leave signed authorization handling unchanged.
- No permanent risk/strategy TOML rollback should be needed because LG-4 does
  not write permanent config.

## Root-Principle Check

- #1 single write entry: preserved through GovernanceHub and execution adapter.
- #2 read/write separation: learning/GUI remain read-only unless operator route
  grants a supervised session.
- #3 AI output is not command: Decision Lease remains required.
- #5 survival over profit: session limits can only tighten.
- #8 explainability: audit mirror is required.
- #11 autonomy: supervised live is explicit human-bound scope, not autonomous live.
