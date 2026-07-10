# E1 Source Implementation - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1

Date: 2026-07-10
Source checkpoint: `c080c552b`
Verdict: `SOURCE_READY_RUNTIME_UNPROVEN`

WP1 now suppresses health writes when semantic state is unchanged, while a
PostgreSQL-clock heartbeat remains bounded at 300 seconds. Metrics are excluded
from the semantic hash but remain inside each immutable snapshot hash, so they
checkpoint at state change or heartbeat without creating their own write loop.

Equivalent `DEFER_EVIDENCE` decisions are keyed by source head, complete
candidate/regime/evidence/blocker context, source contract, policy hash, and a
bounded source-time TTL. A reusable decision emits one immutable
`target_rotation` suppression artifact plus `training_input` lineage for the
new sources; it does not emit another run, candidate, defer, or feedback row.
Different source heads, evidence, policy, timestamps, or expired TTLs force
normal reevaluation.

Repositories now count actual inserted artifact, provenance, run, feedback,
health, and defer rows through `RETURNING`; payload bytes are counted only for
inserted canonical payloads. Session-scoped durable metrics include health and
decision suppression ratios plus feedback persisted/duplicate ratios. All
ratio and row-total invariants fail closed.

Verification: focused changed suites `70 passed`; full ALR unit suite
`246 passed`; full `ml_training` suite `1302 passed, 31 skipped`; changed-source
compile and scoped diff-check pass. No migration, service, PostgreSQL,
exchange, order, Cost Gate, Decision Lease, serving, promotion, or latest
pointer authority is included in this checkpoint.
