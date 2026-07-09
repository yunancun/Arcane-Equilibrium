# PM Request - ALR P2-8 Fresh Scanner Shadow Soak

Date: 2026-07-09
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`
Target source head: `26401fbbce9a97e68583a5b8f069ffa3fba0a4d1`

Fresh three-head source alignment is clean at the target head. The existing
engine PID is `1561777` and must not be restarted. The ALR user service is the
only runtime unit in scope. There is no migration, role/privilege change,
scanner write, external contact, order/probe/lease/Cost Gate, serving,
promotion, `_latest`, proof, or deletion action in this request.

The raw Rust-owned scanner baseline is `79786` rows at
`2026-07-09 23:53:38.956+02`. Three later scanner identities are present and
not yet in `learning.alr_source_events`:

| scan id | scanner timestamp |
|---|---|
| `scan-1783634080306` | `2026-07-09 23:54:40.306+02` |
| `scan-1783634141263` | `2026-07-09 23:55:41.263+02` |
| `scan-1783634202522` | `2026-07-09 23:56:42.522+02` |

The normal consumer correctly starts from the oldest unseen historical rows,
which cannot demonstrate that it reached these fresh rows in one bounded
restart. Source commit `26401fbbc` adds a SELECT-only, timestamp-bounded
reconciliation path for this one soak. Apply it only through a temporary
`ALR_RECONCILE_AFTER=2026-07-09T21:53:38.956000+00:00` user-service drop-in;
remove the drop-in after the first healthy service start and restart only the
same ALR service to prove restart recovery.

Required postchecks: all three identities appear exactly once in the ALR source
ledger, no source-key duplicate exists, at least one target/run remains or is
newly decided, a health snapshot is appended, authority counters are zero,
scanner INSERT remains denied to `alr_shadow`, and engine PID remains `1561777`.
Any source, service, authority, or engine drift stops the apply.
