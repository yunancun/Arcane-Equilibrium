# Operator Brief: Fresh Invocation Source-Input Refresh Blocked By Runtime IPC

PM refreshed the current ETH Buy no-order source inputs for the invocation-window gate:

- Equity READY sha `b807478957cce36ca270b9dec6bc8f33f31c2c01ba8bdaa16bf9636a3a8d9892`
- No-authority envelope READY sha `5e1a7102dd23d203b1162f876d3da2ee0becd8f0ccfbc896c1e1ce2aa4604a65`
- Public quote/construction READY sha `523dd1ac711f2f03798d289aa461312df9ad512b1addeca39aa6ad9925f6c9ba`
- Guardian-adjusted sizing READY sha `65fed2d356c1841baa99aa4b43077e80abef6922de07691e68e75d39cf585745`

The run then stopped on a real runtime blocker. The E3-approved governance IPC read-only snapshot failed closed:

- `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/governance/runtime_governance_snapshot.json`
- Sha `8a9e85db5550d18b0a3c3cf887f2202f095e6c2e4a33ba7cf3026ee4c2634db3`
- Status `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_BLOCKED_BY_RUNTIME`
- Blockers: `governance.get_status_not_ok`, `governance.list_leases_not_ok`, `governance.get_risk_state_not_ok`

No order, lease acquire/release, private endpoint, PG access, runtime mutation, service restart, Cost Gate change, live/mainnet, fill/PnL, or proof occurred.

Next blocker is `P0-RUNTIME-GOVERNANCE-IPC-READONLY-SNAPSHOT-REPAIR`.
