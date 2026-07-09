# PM Effect Review - ALR P2 Operational Shadow Completion

Date: 2026-07-10
State: `DONE_OPERATIONAL_SHADOW`
Authority chain: PM -> E3 -> BB -> QA -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

P2 now has a Rust scanner snapshot read-adapter, append-only provenance and
operational ledgers, a source-head-pinned long-lived event consumer, PIT-backed
research challenger/evaluation, deferred ProofPacket/RewardLedger feedback
rotation, derived-cache-only retention, health metrics, and a production Linux
soak with restart recovery. Migrations V151 through V155 already provide the
five ALR persistence/operational/feedback/retention/health schema surfaces; P2-8
added no migration.

The fresh P2-8 transaction closed before engine drift: five real post-baseline
Rust scanner cycles were reconciled exactly once, two service starts made
scanner-backed `DEFER_EVIDENCE` target decisions, and health showed false/zero
authority. During the closed transaction, service PID changed only
`1973155 -> 1982389 -> 1982461`; engine PID remained `1561777`. The temporary
cursor drop-in was then removed. Later observation shows the service remains
active, has continued to append ALR-only research work, and its latest health
still has zero authority/action counters, zero source duplicates, zero retained
cache entries/events, and no proof/reward evidence.

No claim of profitability, proof, serving, promotion, or model deployment is
made. All eight observed statistical runs are challengers with deferred
evidence. P3 is therefore a separate fail-closed authorization gate: it needs a
fresh operator/E3/BB packet with a newly validated candidate, side, order shape,
loss envelope, Decision Lease, and rollback. The external engine PID change to
`1983100` after the closed P2 window is un-attributed and must be revalidated in
that future gate; it grants no order or Demo authority.
