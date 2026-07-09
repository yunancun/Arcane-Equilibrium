# QA Runtime Acceptance - ALR P2-3 Service Only

Date: 2026-07-09
Verdict: `PASS_SERVICE_ONLY_ENGINE_NOTIFIER_DORMANT`

Verified on Linux: active user service, private DSN mode `0600`, exact
least-privilege grants, immutable source-key duplicate count zero, and durable
restart recovery across a second bounded backlog drain. Scanner source count
was not mutated by ALR. The Rust engine PID and start time remained unchanged.

This does not close event-driven new-cycle acceptance: current engine has
write-capable demo flags and was deliberately not rebuilt/restarted. P2-4 is
unblocked for existing durable backlog; P2-8 stays pending safe notifier
activation plus three real event-driven cycles.
