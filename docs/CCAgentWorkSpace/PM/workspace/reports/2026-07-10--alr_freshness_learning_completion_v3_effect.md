# PM Effect Review - ALR Freshness and Learning Completion V3

Date: 2026-07-10
Terminal state: `WAIT_OPERATOR_DEMO_AUTH_EXACT`
Behavioral source head: `091b5d446403d8fe83a15b57142819cbd1ceac6d`
Supersedes: the prior `DONE_OPERATIONAL_SHADOW` terminal inference only

The prior P2 terminal was reopened because production steady-state evidence
showed raw scanner state advancing while ALR remained trapped in the oldest
backlog. The reproduced root cause had two parts: notification parsing discarded
the exact `(scan_id, ts)` identity, then a global oldest-first limited query let
roughly 79k historical rows starve fresh intake. An active service and a zero
failure counter were therefore not truthful freshness evidence.

## F1-F4 Freshness Closure

Commit `091b5d446403d8fe83a15b57142819cbd1ceac6d` preserves each notification
identity, performs exact identity intake first, repairs missed live rows through
a durable fresh cursor, and advances history through an independent low-priority
cursor. V156 SHA-256 is
`d55d2ab71e40e921b9d60362112a75d42b5ad84f0793ba42ba3d2073cccc6b9f`;
the role contract SHA-256 is
`bf004e45077f1d425ca13089d67426dccd5831d4d4f8487a8aeb333b4e927905`.
`ALR_RECONCILE_AFTER` and temporary cursor/drop-in behavior are absent.

Validation was green at `215 passed` for the focused ALR suite, `1271 passed,
31 skipped` for the full ML suite, and PostgreSQL 16 for clean/reapply catalog
guards and the adversarial 79,000-history-plus-one-fresh workload. Duplicate,
out-of-order, late, coalesced, missed-notification, max-batch-plus-one,
crash/restart, singleton, starvation, artificial raw-only gap, phantom cursor,
weakened-constraint/index, and role-ACL cases passed. Scanner privileges remain
`SELECT` only; the consumer event ledger is `SELECT/INSERT` only.

Fresh E3 and BB gates approved only V156, the role contract, source pinning, one
activation restart, a separately approved single V156-to-V156 recovery restart,
and read-only acceptance. Physical V156 was applied directly; the SQLx ledger
truthfully remained at max version `150`, `132` rows, with zero V156 ledger rows.
Only the ALR unit restarted. Its PID moved `2038844 -> 2040797` for recovery;
the engine remained PID `1983100`. Session evidence is two starts, one graceful
stop, zero failed sessions, zero unclean recoveries, and one open session.

The first ten natural post-baseline Rust cycles ran from
`scan-1783642145098` through `scan-1783642692157`. Closed-window counts were
raw/ALR/raw-only/ALR-only `10/10/0/0`; identity/hash/payload equality was
`10/10/10`; duplicate ingests were zero; received and consumed notification
identities were `10/10`; duplicate/invalid deltas were zero. Ingest latency was
`0.979724s` minimum, `1.7048254s` mean, and `2.608247s` maximum. Latest raw,
fresh cursor, and ALR source ended at
`2026-07-10 02:18:12.157+02 / scan-1783642692157`; health reported raw-only
zero, lag zero, no failures, and all authority flags/counters false/zero.

Historical remaining stayed `75657`, because the low-priority cursor traversed
rows already persisted by the legacy consumer; this is not reported as backlog
reduction or completion. It is bounded non-starvation evidence: during the
window history recorded nine success events and 72 rows, and across the final
inspection ten success events / 80 rows advanced the cursor from
`2026-04-30 09:18:33.585+02` to `2026-05-01 18:48:34.871+02` while fresh stayed
current.

## F5 Learning Qualification

Actual training was not run: `model_training_performed=false`. The production
audit found 139 ALR runs, all `DEFER_EVIDENCE`; 138 feedback events had no proof
packet and zero reward records. Among 3,569 candidate-related realized-fill
lifecycles, fees were complete, but only 201 had slippage on every fill, 2,063
had any slippage, only 3,524 reconstructed every order ID, and only 2,166 had
reference price/time/source on every fill. Funding had only 76 heuristic
contexts without candidate identity. There was no `source_l2_reply_id`, current
proof packet, reward ledger, linked purge/embargo/true-OOS/control outcome chain,
or hidden-OOS registry. Negative and failed examples exist but are not a
substitute for the complete qualified chain. Verdict: `F5_EVIDENCE_INSUFFICIENT`.

Because data are insufficient, PM produced a new executable-but-unauthorized
Demo packet for the exact `grid_trading|SUIUSDT|Sell` cell. Packet SHA-256 is
`1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`.
Its side comes from `learning.decision_features.side=-1`; the scanner is only an
object selector. Embedded VOI manifest/runtime hashes reproduce, and E3/BB both
approved this exact hash for operator decision only. It remains
`operator_authorized=false`, `execution_performed=false`, with zero authority
and action counters.

## F6 Retention and Terminal

Production had zero derived-cache rows, zero quarantine/sweep/restore eligible
rows, and zero retention events. The retention pass scanned zero and performed
no deletion; protected ledgers remain populated and mutation-denied to the ALR
role. The only truthful verdict is `NOT_EXERCISED_NO_ELIGIBLE_CACHE`, not a
fabricated lifecycle pass.

`DONE_FRESH_OPERATIONAL_LEARNING_SHADOW` is unavailable because no qualified
training/evaluation run occurred. The exact packet exists and has hash-bound
E3/BB review, but no operator decision. The terminal is therefore
`WAIT_OPERATOR_DEMO_AUTH_EXACT`. No exchange contact, order/probe/cancel/modify,
Decision Lease, Cost Gate mutation, live/mainnet action, Guardian/RiskConfig
mutation, serving/promotion, `_latest` overwrite, or protected-evidence deletion
occurred.

