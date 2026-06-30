# Runtime Governance IPC Snapshot Repair Ready

Status: `DONE_WITH_CONCERNS`

The runtime governance IPC read-only snapshot blocker is repaired. The previous failure was caused by the snapshot helper not explicitly routing the runtime IPC secret-file path into the existing HMAC auth layer. Source commit `9880045575021af3663da79555ff251f507ef56c` fixes that without printing or storing the secret value.

Runtime `trade-core` cherry-picked the fix as `5e1c4091c1ce9182fcafa83c55feb4a9887425cb`. The new read-only snapshot is:

- `/tmp/openclaw/runtime_governance_ipc_snapshot_repair_20260630T233847Z/governance/runtime_governance_snapshot.json`
- sha256 `f7070bc4d7adba0c908c18ff40dcdb6177ff9bd15d0f130a1dfeec06d997b4ed`
- status `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY`
- all governance methods ok
- Guardian `NORMAL`
- live lease count `0`

No order, Decision Lease acquire/release, private endpoint, PG write, service restart, risk/Cost Gate change, live/mainnet action, fill/PnL/proof, or downstream gate continuation occurred.

Next blocker: rebuild the pre-active sizing-aware gate from the READY snapshot, then rerun corrected dry-run before any active lease/BBO `--run`.
