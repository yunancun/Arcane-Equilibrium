# E4 Regression Test Report - ALR P2-1 Scanner Read Adapter

Date: 2026-07-09
Verdict: PASS
Scope: source-only Python adapter and tests; no Rust, DB, network, service, or runtime change.

| Engine | Result | Baseline | Delta |
|---|---:|---|---|
| P2-1 focused plus ALR adjacency, run 1 | 153 passed, 0 failed | New P2-1 slice baseline | N/A |
| P2-1 focused plus ALR adjacency, run 2 | 153 passed, 0 failed | Run 1 | 0 |
| Python bytecode compilation | PASS | N/A | N/A |
| Diff whitespace check | PASS | N/A | N/A |

The test set covered `test_alr_scanner_snapshot_adapter.py` together with the
controller, target-arbiter, local-runner, outcome-bridge, and retention-guardian
ALR suites. The new adapter test file contributes 14 direct behavior tests:
canonical row/hash output, malformed row rejection, duplicate and late-cycle
watermark behavior, timestamp normalization, lifecycle set invariants, invalid
counters/config/watermark rejection, canonical-hash stability, and a static
no-direct-IO-import guard.

No test mocks business logic. Concurrency/SLA/cross-language float tests are not
applicable: this is a pure one-row adapter with no mutable singleton, scanner
cadence change, numerical indicator, or Rust surface change. The red-to-green
lifecycle regression proves `removed` cannot overlap the post-update active set
or `added`.

The E4 role memory file was deliberately not modified because it contains
pre-existing unrelated dirty worktree edits. This standalone report is the
durable result for this slice.
