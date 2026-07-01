# Downstream No-Auth Refresh Blocked By Runtime Authority Inputs

- Status: `BLOCKED_BY_RUNTIME`
- Active blocker: `P0-CURRENT-CANDIDATE-DOWNSTREAM-NOAUTH-INPUT-REFRESH-FOR-PHASE-AB`
- Next blocker: `P0-CURRENT-CANDIDATE-STANDING-AUTH-AND-EQUITY-INPUT-REFRESH-FOR-DOWNSTREAM-NOAUTH`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Source head: `a4a598a2e1402c1477cbd94088eeabc14a0f6839`
- Runtime head: `e16d3323cb58a549262f6bfa6f1ef48ca140aea0`
- Runtime manifest: `trade-core:/tmp/openclaw/downstream_noauth_input_refresh_20260701T044905Z_noauth/manifest/downstream_noauth_input_refresh_manifest.json`
- Runtime manifest sha: `7c502ccf4b5d68573eaeddbb71ece1563b566fa66a4a9e704a6ea68491fc54bc`
- Final session state: `/tmp/openclaw/session_loop_state_20260701T044053Z_downstream_noauth_input_refresh/session_loop_state_final.json`
- Final session state sha: `824105656544ae1ead4d856b9149b8006b7b8fe2ba3a22b639875f37a3964127`

## Summary

PM attempted the first actionable v700 blocker: refresh downstream no-authority inputs so the order-capable Phase A/B gate would not reuse stale false-negative review/preflight evidence.

E3 first blocked the broader command sequence because a bounded auth object with an `authorize` decision cannot be fed into `current_candidate_no_order_refresh_envelope`, which rejects order/probe authority inputs. PM corrected the sequence to only produce fresh false-negative operator review, false-negative bounded preflight, accepted equity input, and the no-order envelope, with no bounded auth input and no `_latest` overwrite. E3 approved that corrected scope with local-only Control API equity capture conditions.

The corrected runtime run failed closed. Equity capture against `http://127.0.0.1:8000` failed because the runtime API service is active on `100.91.109.86:8000`, not localhost. The false-negative review and preflight also rejected the existing standing auth as invalid for preflight under helper freshness/schema gates. The final no-authority envelope therefore stayed blocked as `GUI_RISK_CAP_INPUT_REQUIRED_NO_AUTHORITY`.

## Evidence

| Artifact | Status | SHA |
|---|---|---|
| Equity | `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_SOURCE_FAILURE_NO_AUTHORITY` | `abbb7b781cba03498d7896387d121697e6208cfbb49ff3c9f12703d3f612b850` |
| False-negative review | `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW` | `b526992d85cc2bb78ea2fc2f47c16b9496fbea71a01360f90f4a9073c49c1e22` |
| False-negative preflight | `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT` | `af9abe9a79fdc750225840214c06165692b4251e8e4a5b5fc6337849ab213c45` |
| No-authority envelope | `GUI_RISK_CAP_INPUT_REQUIRED_NO_AUTHORITY` | `cba5728559b94151e1b2cb3bde00315a7385ef676778f6f7de3d90239e51b775` |

Runtime diagnosis found `127.0.0.1:8000` and `localhost:8000` connection refused, while `openclaw-trading-api.service` was active with uvicorn bound to `100.91.109.86:8000`. Because E3 only approved localhost/127.0.0.1 capture for this run, PM did not switch the API base.

## Boundary

No `_latest` overwrite, public quote, active Decision Lease, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, Cost Gate change, live/mainnet action, fill, PnL, or profit proof occurred.

Do not rerun Phase A/B, broaden the Control API base, mutate API binding, raise the `21600` or `900` second freshness gates, or consume older auth/admission artifacts without fresh E3/BB review. Next progress is to refresh or revalidate standing-auth consumption and the accepted Demo equity input path for downstream no-authority review/preflight.
