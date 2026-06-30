# Runtime Governance IPC Snapshot Repair Ready

## Session State

| Field | Value |
|---|---|
| active_blocker_id | `P0-RUNTIME-GOVERNANCE-IPC-READONLY-SNAPSHOT-REPAIR` |
| status | `DONE_WITH_CONCERNS` |
| next_blocker_id | `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE` |
| session_loop_state | `/tmp/openclaw/session_loop_state_20260630T234050Z_runtime_governance_ipc_repair/session_loop_state.json` |
| session_loop_state_sha256 | `6d3e22c5758f132eded755bfb9081bc264e1a4e6bb1536f82d68b94fb817cf82` |

## What Changed

Source commit `9880045575021af3663da79555ff251f507ef56c` added explicit `--ipc-secret-file` routing to `helper_scripts/research/cost_gate_learning_lane/runtime_governance_ipc_readonly_snapshot.py`.
The helper now passes only the secret-file path through `OPENCLAW_IPC_SECRET_FILE` during snapshot build, restores any previous env value, and never serializes the IPC secret value.

Runtime `trade-core` cherry-picked the source fix onto local hotfix lineage as `5e1c4091c1ce9182fcafa83c55feb4a9887425cb`.
Changed paths were limited to the helper and its test.

## Verification

- Focused helper tests: `4 passed`
- Adjacent IPC auth/HMAC tests: `13 passed`
- `py_compile`: passed
- `git diff --check`: passed
- E2 review: `ACCEPT`
- E4 verification: `PASS`
- E3 runtime/security review: `APPROVE_WITH_CONDITIONS`

## Runtime Evidence

| Artifact | Status | SHA256 |
|---|---|---|
| `/tmp/openclaw/runtime_governance_ipc_snapshot_repair_20260630T233847Z/governance/runtime_governance_snapshot.json` | `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY` | `f7070bc4d7adba0c908c18ff40dcdb6177ff9bd15d0f130a1dfeec06d997b4ed` |
| `/tmp/openclaw/runtime_governance_ipc_snapshot_repair_20260630T233847Z/governance/runtime_governance_snapshot.md` | summary markdown | `8727ec647b1bde2755e4a0e26c180018b16ded6a73c21c9f33161da793f0d3fd` |

Snapshot summary:

- `governance.get_status`: ok
- `governance.list_leases`: ok
- `governance.get_risk_state`: ok
- `runtime_blockers`: `[]`
- Guardian risk level: `NORMAL`
- position size multiplier: `1.0`
- live lease count: `0`

## Boundary

No order, cancel, modify, Decision Lease acquire/release, private endpoint, PG query/write, service restart, risk mutation, Cost Gate change, live/mainnet action, fill/PnL/proof claim, or downstream gate/dry-run continuation occurred under this E3 approval.

## Next Action

Rebuild the pre-active sizing-aware Decision Lease/Guardian gate from final admission + Guardian sizing + READY governance snapshot, then rerun the corrected dry-run.
If standing/bounded auth or source artifacts fail freshness before that run, refresh those inputs first.
Fresh E3/BB is required before any exchange-facing active lease/BBO `--run`.
