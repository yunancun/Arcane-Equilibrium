# G3-02 Phase C — ExecutorAgent Shadow-Mode Flip API (Operator Runbook)

- **Author**: E1+PA (G3-02 Phase C)
- **Date**: 2026-04-25
- **Status**: Live (Python-only commit, no `--rebuild` required)
- **Endpoint**: `POST /api/v1/executor/shadow-toggle`
- **Source**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py`
- **RFC**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md` §6.1
- **Predecessors**: Phase A `16c97c1` + `03acedb` + `3bed899` (Rust schema + IPC)
  · Phase B `51608fe` (Python cache + ExecutorAgent rewire)
  · Phase D e2e `852da0f`
- **Related memory**: `feedback_live_no_degradation_by_endpoint.md` · `project_paper_pipeline_disabled_by_default.md`

---

## 1. Purpose

Operator-controlled IPC bridge that flips `RiskConfig.executor.shadow_mode`
via the existing `patch_risk_config` IPC method, behind an authentication
gate that mirrors the canonical 5-gate live chain. This is the *last* control
plane piece that completes the ExecutorAgent shadow→live unblock per RFC §6.1.

Without this endpoint, flipping `shadow_mode=false` requires either (a) a
TOML edit + engine restart (slow, not auditable) or (b) a raw socket-level
JSON-RPC call (no auth gate). The endpoint fixes both.

---

## 2. Auth gate matrix

| Direction × Engine | Gate set | Notes |
|---|---|---|
| `shadow_mode=true` (retreat) on **any** engine | Operator role only | Cheap retreat per CLAUDE.md §六 #6 |
| `shadow_mode=false` on `engine=paper` | Operator role only | Paper opt-in via env (`OPENCLAW_ENABLE_PAPER=1`) |
| `shadow_mode=false` on `engine=demo` | Operator role only | Demo uses demo Bybit endpoint; no live-gate needed |
| `shadow_mode=false` on `engine=live` | **Full 5-gate chain** | See §3 |

**5-gate live chain** (matches CLAUDE.md §四):

1. **Operator role** — `current_actor` Bearer-token auth + `_require_operator_role`
2. **`live_reserved` global mode** — `live_session_routes._get_global_mode_state()` must contain `"live"`
3. **`OPENCLAW_ALLOW_MAINNET=1` env** — only when `bybit_endpoint=mainnet` (LiveDemo skips this gate)
4. **Secret slot** — `$OPENCLAW_SECRETS_DIR/live/{api_key,api_secret}` non-empty
5. **`authorization.json`** — HMAC valid + unexpired + `env_allowed` contains current endpoint label

Failure of any gate returns HTTP 403 with a structured `gate_failed` field
(e.g. `{"gate_failed": "authorization_expired", "hint": "..."}`) so the
operator can self-diagnose and fix the specific issue rather than guessing.

---

## 3. Request / response schema

### Request

```http
POST /api/v1/executor/shadow-toggle
Authorization: Bearer <api_token>
Content-Type: application/json

{
  "engine": "demo",
  "shadow_mode": false,
  "source": "operator"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `engine` | `"paper" \| "demo" \| "live"` | yes | Whitelisted server-side; other values → 400 |
| `shadow_mode` | `bool` | yes | `true` = log-only · `false` = real submit |
| `source` | string | no (default `"operator"`) | Audit provenance tag; written to IPC audit log |

### Response (success — 200)

```json
{
  "ok": true,
  "engine": "demo",
  "applied": {"shadow_mode": false},
  "version": 47,
  "ts_ms": 1729800000000,
  "source": "operator",
  "actor": "demo-operator",
  "ipc_response": {"version": 47, "applied": true}
}
```

### Response (gate denied — 403)

```json
{
  "detail": {
    "ok": false,
    "gate_failed": "authorization_expired",
    "hint": "authorization.json expired at ts_ms=… (now=…). Run /api/v1/live/auth/renew."
  }
}
```

`gate_failed` values: `live_reserved` · `mainnet_env` · `secret_slot` ·
`authorization` · `authorization_malformed` · `authorization_signature` ·
`authorization_expired` · `authorization_env_mismatch` · `operator_role` ·
`unauthenticated` · `ipc_unavailable`.

### Response (invalid engine — 400)

```json
{"detail": "Invalid engine 'evil'; must be one of ['demo', 'live', 'paper']"}
```

### Response (IPC failure — 500)

```json
{"detail": "rust_engine_unavailable: patch_risk_config: <error>"}
```

---

## 4. Operator playbook

### 4.1 Demo: enable real submit (G3-02 Phase C primary use case)

```bash
# Pre-check: verify current shadow state.
curl -sH "Authorization: Bearer $OPENCLAW_API_TOKEN" \
  http://localhost:8000/api/v1/executor/shadow-toggle  # GET not implemented — use IPC

# Flip demo to live (real demo orders).
curl -sX POST -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/executor/shadow-toggle \
     -d '{"engine":"demo","shadow_mode":false,"source":"operator"}'
```

Expected: 200 + `applied.shadow_mode=false`. Within `OPENCLAW_EXECUTOR_CACHE_POLL_SEC`
(default 10s) the next Guardian-approved intent on demo will hit the real Rust
`intent_processor` → demo paper_state → fill in `trading.fills`.

### 4.2 Demo: retreat to shadow

```bash
curl -sX POST -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/executor/shadow-toggle \
     -d '{"engine":"demo","shadow_mode":true,"source":"operator"}'
```

Cheap retreat — Operator role only.

### 4.3 Live (mainnet): full gate chain

```bash
# 0. Pre-flight — confirm 5 gates green before flipping.
#    a. Operator role logged in (Bearer token).
#    b. /api/v1/system/global-mode shows live_reserved.
#    c. OPENCLAW_ALLOW_MAINNET=1 in engine env.
#    d. live/api_key + live/api_secret populated.
#    e. live/authorization.json present, fresh, env_allowed=["mainnet"].

# 1. Flip.
curl -sX POST -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/executor/shadow-toggle \
     -d '{"engine":"live","shadow_mode":false,"source":"operator"}'
```

If a gate fails, the 403 response names the specific failing gate. Common fixes:

| `gate_failed` | Fix |
|---|---|
| `live_reserved` | Switch Global Mode → `live_reserved` in System Overview tab |
| `mainnet_env` | Set `OPENCLAW_ALLOW_MAINNET=1` in engine env, restart engine |
| `secret_slot` | Populate `live/api_key` + `live/api_secret` in secrets dir |
| `authorization` | Run `POST /api/v1/live/auth/renew` (Operator) |
| `authorization_expired` | Same — rerun renew |
| `authorization_signature` | `OPENCLAW_IPC_SECRET` rotated; re-sign via renew |
| `authorization_env_mismatch` | Authorization signed for wrong endpoint; renew with current label |

---

## 5. Audit trail

Every request — success **and** denial — writes a STATE_CHANGE row to
`change_audit_log` (via `governance_routes._get_governance_hub`):

- `who`: `actor.actor_id`
- `what`: `"ExecutorAgent shadow_mode flip → <bool> on engine=<engine> (applied|denied)"`
- `reason`: `"source=<source>; gate_failed=<gate>"`
- `affected_components`: `["executor:<engine>", "rust:RiskConfig.executor.shadow_mode"]`

On the Rust side, the IPC `patch_risk_config` handler also appends to
`ipc_change_audit_log` per Phase A.

If the governance hub is unavailable, a WARN log is emitted (Root Principle
#8 trace gap noted) but the request completes — same fail-soft behavior as
`risk_routes._record_reset_drawdown_audit`.

---

## 6. Verification

### Mac smoke (no engine running):

```bash
python3 -c "
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.executor_routes \
  import executor_router
print(len(executor_router.routes))
"
# expected: 1
```

### Linux pytest:

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ \
  -k 'executor or shadow_toggle'"
# expected: 91 passed (74 existing + 17 new)
```

### Linux end-to-end smoke (after deploy):

```bash
# 1. flip demo to live (real demo orders).
curl -sX POST -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/executor/shadow-toggle \
     -d '{"engine":"demo","shadow_mode":false}'
# expected: 200 + applied.shadow_mode=false

# 2. wait one cache poll (default 10s, env OPENCLAW_EXECUTOR_CACHE_POLL_SEC).
sleep 12

# 3. verify ExecutorConfigCache picked up the flip.
ssh trade-core "tail -200 /tmp/openclaw/uvicorn.log | grep ExecutorConfigCache"
# expected: refreshed shadow=False ...

# 4. retreat for safety until ready for full demo run.
curl -sX POST -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/executor/shadow-toggle \
     -d '{"engine":"demo","shadow_mode":true}'
```

---

## 7. Defense-in-depth notes

- **Python-side cache ALSO checks shadow** — even if cache is stale, Rust
  `intent_processor` re-checks `executor.shadow_mode` per RFC §6.6 before
  forwarding to Bybit REST. Two independent gates → either failing closed →
  no live order.
- **Retreat direction is always cheap** — `shadow_mode=true` patch has zero
  blast radius; gate is just Operator role. This matches CLAUDE.md §六 #6.
- **No fail-open path** — if `OPENCLAW_IPC_SECRET` is unset (HMAC verifier
  cannot run), gate 5 fails closed with `gate_failed: authorization`.

---

## 8. Files & tests

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py` (NEW, ~430 LOC)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` (router registration)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py` (NEW, 17 tests)

Helper functions added (no Rust changes; all reuse existing primitives):

- `_verify_demo_gate(actor)` / `_verify_paper_gate(actor)` / `_verify_live_gate(actor)` — gate matrix
- `_verify_authorization_json_or_raise(...)` — HMAC + expiry + env_allowed (mirrors Rust `live_authorization::verify`)
- `_record_shadow_toggle_audit(...)` — STATE_CHANGE audit (mirrors `risk_routes._record_reset_drawdown_audit`)
- `_gate_failure(gate_name, hint)` — structured 403 builder

---

**End of runbook.**
