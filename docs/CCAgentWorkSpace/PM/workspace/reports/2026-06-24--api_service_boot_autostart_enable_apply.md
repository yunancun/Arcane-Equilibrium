# API Service Boot Autostart Enable Apply

Date: 2026-06-24  
Active blocker: `P1-RUNTIME-HEALTH-HYGIENE`  
Runtime chain: PM -> E3 -> PM  
Status: `DONE`

## Decision

Enabled boot autostart for the existing user service:

```text
systemctl --user enable openclaw-trading-api.service
```

This was an enable-only checkpoint. PM did not use `--now`, did not restart the service, did not run daemon-reload, did not edit the unit, and did not signal any process.

BB was skipped because the action was not exchange-facing.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P1-RUNTIME-HEALTH-HYGIENE",
  "blocker_goal": "Close remaining API service boot-autostart hygiene without changing trading authority.",
  "profit_relevance": "Boot-stable Demo/API service ownership improves evidence capture, auditability, reconstructability, and live-applicable operating discipline.",
  "completed_blockers": [
    "P1-LEARNING-LOOP-CLOSURE",
    "P1-AUTONOMOUS-PARAMETER-PROPOSAL",
    "P1-RUNTIME-SOURCE-SYNC-MM-MOTIF-ARTIFACT-REFRESH"
  ],
  "blocked_blockers": [
    "P0-BOUNDED-PROBE-AUTHORIZATION",
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--api_service_enablement_review_packet.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--api_service_runtime_cutover_pm_apply.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_mm_motif_artifact_refresh.md"
  ],
  "source_head": {
    "local_origin": "9c1b4895aa2eb7d0c4e69e2a4710776f494d4bf6",
    "runtime_operational": "dd3088dbee3b70eaf02b28f1279d0d3694b0cc5f"
  },
  "runtime_timestamp": "2026-06-24T15:33:xx+02:00",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "learning_ssot_decision_latest": "2026-06-24T15:29:42+02:00",
    "autonomous_parameter_proposal_latest": "2026-06-24T15:29:42+02:00",
    "mm_motif_amplification_latest": "2026-06-24T15:24:53+02:00"
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "Fresh API service enabled/active/listener/health/unit snapshot and E3 approval.",
  "new_evidence_delta_found": "UnitFileState disabled, service active/running, no wants symlink, clean parity packet, E3 enable-only approval.",
  "acceptance_criteria": [
    "E3 approve enable-only runtime mutation",
    "run exactly systemctl --user enable openclaw-trading-api.service",
    "no restart, no daemon-reload, no unit edit, no process signal",
    "is-enabled becomes enabled",
    "MainPID and NRestarts unchanged",
    "listener remains 100.91.109.86:8000",
    "unauthenticated health remains 401",
    "no OPENCLAW_ALLOW_MAINNET=1 or authority/proof contamination"
  ],
  "next_blocker_id": "P1-RUNTIME-HEALTH-HYGIENE-FINAL-SNAPSHOT or next source-only profit blocker"
}
```

## Anti-Repeat Decision

The loop did not repeat:

- `P0-BOUNDED-PROBE-AUTHORIZATION`: bounded auth latest is still `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW` with no `operator_authorization` object.
- `P0-PROFIT-OUTCOME-REVIEW`: result review is still `NO_PROBE_OUTCOMES_RECORDED`.
- `P1-LEARNING-LOOP-CLOSURE`: latest `learning_ssot_decision` is already `ARTIFACT_LEDGER_CURRENT_SSOT`.
- `P1-AUTONOMOUS-PARAMETER-PROPOSAL`: latest proposal is already `REVIEWABLE_PARAMETER_PROPOSAL_READY`, review-packet-only, no authority.

New evidence delta existed for `P1-RUNTIME-HEALTH-HYGIENE`: the API service was active/running but still `UnitFileState=disabled`, and the prior review explicitly left enablement as a separate PM/E3 checkpoint.

## Fresh Pre-Enable Evidence

Read-only facts before enablement:

- `UnitFileState=disabled`
- `ActiveState=active`
- `SubState=running`
- `MainPID=2218842`
- `NRestarts=0`
- `FragmentPath=/home/ncyu/.config/systemd/user/openclaw-trading-api.service`
- `default.target.wants/openclaw-trading-api.service=missing`
- `Linger=yes`
- listener: `100.91.109.86:8000`
- health: HTTP `401`
- runtime repo clean at `dd3088dbee3b70eaf02b28f1279d0d3694b0cc5f`

Fresh local parity packet:

- snapshot: `/tmp/api_service_enable_snapshot_20260624T133236Z.json`
- packet: `/tmp/api_service_enable_parity_20260624T133245Z.json`
- markdown: `/tmp/api_service_enable_parity_20260624T133245Z.md`
- status: `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`
- findings: `[]`
- unit enablement review: `enable_step_template=systemctl --user enable openclaw-trading-api.service`
- all authority/proof/mutation answers false or `NONE`

## E3 Review

E3 verdict: `APPROVED_FOR_PM_RUNTIME_ACTION`

E3 conditions:

- PM action must be exactly `systemctl --user enable openclaw-trading-api.service`.
- No `--now`, restart, reload, daemon-reload, unit edit, process signal, API POST, PG write, Bybit order/cancel/modify.
- Post-check must verify enabled state, wants symlink, same PID or no unexpected restart, Tailscale-only listener, health `401`, and no authority/proof/mainnet contamination.

## Runtime Action

Command:

```text
systemctl --user enable openclaw-trading-api.service
```

Output:

```text
Created symlink /home/ncyu/.config/systemd/user/default.target.wants/openclaw-trading-api.service -> /home/ncyu/.config/systemd/user/openclaw-trading-api.service.
```

## Post-Enable Verification

Guarded post-check:

- before state: `disabled`
- after state: `enabled`
- before PID: `2218842`
- after PID: `2218842`
- before restarts: `0`
- after restarts: `0`
- unit SHA: `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- symlink: `/home/ncyu/.config/systemd/user/default.target.wants/openclaw-trading-api.service`
- symlink target: `/home/ncyu/.config/systemd/user/openclaw-trading-api.service`
- listener: `100.91.109.86:8000`
- health: `401`
- `OPENCLAW_ALLOW_MAINNET=1` count in unit env: `0`

Independent final check:

```text
ENABLED=enabled
ACTIVE=active
STATE=enabled
PID=2218842
RESTARTS=0
WANTS=/home/ncyu/.config/systemd/user/openclaw-trading-api.service
LISTEN=100.91.109.86:8000
HEALTH=401
MAINNET_ENV_COUNT=0
```

## Aggressive Profit Hypotheses

1. Boot-stable Demo/API evidence capture
   - why_it_might_make_money: less runtime ownership drift means fewer missed learning artifacts and cleaner reconstruction of demo outcomes.
   - fastest_safe_test: enable-only symlink plus post-check; completed.
   - required_data: service state, listener, health, unit env, symlink.
   - failure_condition: restart, listener drift, health failure, mainnet/authority contamination.
   - authority_required: PM/E3 runtime mutation approval; satisfied.
   - max_safe_next_action: final runtime hygiene snapshot only.
   - scoring: expected_net_pnl_upside=4, evidence_strength=8, execution_realism=8, cost_after_fees=4, time_to_test=8, risk_to_account=1, risk_to_governance=3, autonomy_value=7.

2. Reviewable false-negative parameter proposal remains the highest bounded-demo path
   - why_it_might_make_money: latest proposal is `REVIEWABLE_PARAMETER_PROPOSAL_READY` for `grid_trading|AVAXUSDT|Sell`, but still no authority.
   - fastest_safe_test: no-authority preflight/proposal review only; do not re-run authorization without exact authority artifact.
   - required_data: exact authorization object, candidate-matched fills, matched controls, fee/slippage.
   - failure_condition: no candidate-matched fill or net negative after fees/slippage.
   - authority_required: candidate-scoped bounded Demo authorization only.
   - max_safe_next_action: source-only preflight hardening or wait for exact artifact.
   - scoring: expected_net_pnl_upside=7, evidence_strength=6, execution_realism=5, cost_after_fees=5, time_to_test=4, risk_to_account=2, risk_to_governance=2, autonomy_value=8.

3. MM motif distinct-date accumulation
   - why_it_might_make_money: latest motif artifact found a low-friction repeated motif with 4 frontier candidates and a 2.608 bps current-fee gap.
   - fastest_safe_test: continue artifact-only distinct-date accumulation through scheduled fill-sim history.
   - required_data: independent-date fill-sim history, frontier train/holdout gross edge, current fees.
   - failure_condition: motif fails repeat or gap remains positive.
   - authority_required: none for artifact accumulation.
   - max_safe_next_action: source/artifact-only scoring refresh.
   - scoring: expected_net_pnl_upside=7, evidence_strength=4, execution_realism=5, cost_after_fees=5, time_to_test=6, risk_to_account=1, risk_to_governance=1, autonomy_value=8.

## Boundaries Preserved

No Bybit call, no order/cancel/modify, no API POST, no PG query/write, no unit edit, no daemon-reload, no restart, no process signal, no live/mainnet, no Cost Gate lowering, no probe/order authority, no Rust writer, and no promotion proof.
