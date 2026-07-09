# E2 Review - ALR P2-6 Retention Guardian

Date: 2026-07-09
Verdict: `APPROVE_TO_FRESH_RUNTIME_GATE`

Commit `14a09b5621f0c5e81018a0e9cd8ccccd1647c82a` limits retention mutation to
`learning.alr_derived_cache_entries`, whose constraints require
`ALR_OWNED_REBUILDABLE`, `rebuildable=true`, and active/quarantined state. The
guardian reference-checks before quarantine, rechecks after grace before sweep,
and leaves all artifact, provenance, run, feedback, proof, and source rows
intact. Each mutation appends an immutable retention event.

Only the cache table gets shadow UPDATE/DELETE; every other ALR table remains
SELECT/INSERT-only. The event listener invokes one bounded pass only during an
existing startup/wake cycle. Focused and adjacent suite passed `210`; the
isolated V154 test passed quarantine, sweep, lineage retention, and non-cache
DELETE denial.
