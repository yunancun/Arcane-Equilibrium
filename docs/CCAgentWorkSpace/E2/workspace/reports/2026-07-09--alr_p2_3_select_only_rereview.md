# E2 Re-Review - ALR P2-3 Select-Only Repair

Date: 2026-07-09
Verdict: PASS_TO_E4_RETRY
Mode: ROLE_FALLBACK_SINGLE_SESSION

The isolated failure was correctly traced to two `FOR SHARE` identity reads in
the P2-2 repository. Those locks are not required because the existing
`INSERT ... ON CONFLICT ... RETURNING` plus source-hash recheck resolves the
only concurrent writer race. Removing them preserves append-only semantics and
restores the reviewed `alr_shadow` SELECT/INSERT-only boundary.

Evidence: focused persistence/event/role tests `17 passed`; expanded P2
focused-plus-adjacent suite passed twice at `171 passed`. The new regression
asserts that repository SQL contains no `FOR SHARE`. No UPDATE/DELETE privilege
was added and no production state was changed.
