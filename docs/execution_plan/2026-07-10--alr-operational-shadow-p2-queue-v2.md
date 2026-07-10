# ALR Operational Shadow P2 Queue v2

Date: 2026-07-10
Authority: `TODO.md` controls live status. This file pins the V3 acceptance contract and current alternative terminal evidence; it is not a replacement dispatch queue.
Boundary: ADR-0049, AMD-2026-07-09-02, and AMD-2026-07-10-02.
Supersession: queue v1 remains immutable historical evidence. Its `DONE_OPERATIONAL_SHADOW` completion rule and generic `WAIT_OPERATOR_DEMO_AUTH` gate are invalid for V3 truth.

## Completion Rule

The only normal terminal state is `DONE_FRESH_OPERATIONAL_LEARNING_SHADOW`. It requires F1 through F6, including a qualified full-proof-chain training/evaluation run when eligible data exists.

The only alternative terminal state is `WAIT_OPERATOR_DEMO_AUTH_EXACT`. It is permitted only after all currently safe sources are proven insufficient for a qualified candidate-matched label and a brand-new executable-but-unauthorized exact packet is emitted. `DEFER_EVIDENCE`, service active, tests complete, empty queue, old soak evidence, source-only completion, or `model_training_performed=false` alone are not terminal states.

## V3 Queue

| ID | Status | Owner chain | Acceptance / current truth |
|---|---|---|---|
| V3-REOPEN | DONE | PM -> CC -> FA -> PA -> PM | The observed steady-state freshness regression invalidated the old P2-8 terminal inference. V1/V2 records remain historical; they grant no current completion or Demo authority. |
| F1-FRESH-LANE | DONE | PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM | Notification consumption preserves exact `(scan_id, ts)` identity. Durable bounded live-watermark catch-up recovers missed/coalesced notifications. Fresh and historical lanes have independent persistent cursor/state; fresh runs first and capped low-priority history cannot starve it. No normal dependency on `ALR_RECONCILE_AFTER` or a temporary drop-in exists. |
| F2-HEALTH-TRUTH | DONE | PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM | Persisted health exposes raw/ALR latest timestamps, ingestion lag, fresh raw-only count, historical remainder, notification received/consumed/invalid counts, last success, and true failure/restart counters. Untrained backlog is not reported as ingestion backlog. |
| F3-ADVERSARIAL | DONE | PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM | 79k+1 fresh priority, duplicate/out-of-order/late/coalesced/missed notification, crash/restart, watermark recovery, single-instance, starvation, forced raw-only health alarm, scanner SELECT-only, and false/zero authority cases are covered. |
| F4-NATURAL-SOAK | DONE | PM -> E3 -> BB -> PM -> QA -> PM | At least ten consecutive natural Rust scanner cycles passed without a temporary cursor: bounded-latency raw/ALR identity equality, fresh raw-only `0`, duplicate `0`, advancing max source timestamp, one ALR-only restart recovery, and no engine restart for the acceptance exercise. A failed window would require RCA and a new complete window. |
| F5-QUALIFIED-LEARNING | WAIT_OPERATOR_DEMO_AUTH_EXACT | PM -> QC -> MIT -> AI-E -> PM; PM -> E3 -> BB -> PM -> Operator | All currently safe sources lack the complete candidate-matched PIT/proof/reward/after-cost chain, so `model_training_performed=false` is truthful and no model claim was made. A new fixed-cell `grid_trading|SUIUSDT|Sell` packet is emitted at SHA `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`; it is exact, executable in specification, unauthorized, unexecuted, challenger-only, E3/BB-approved for Operator decision only, and awaiting the Operator decision. |
| F6-RETENTION | NOT_EXERCISED_NO_ELIGIBLE_CACHE | PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM | Production has no eligible ALR-owned rebuildable unreferenced derived cache. No deletion is claimed. Future eligible cache must pass reference graph, quarantine, grace/recheck, sweep, and protected-lineage validation. |
| V3-TERMINAL | WAIT_OPERATOR_DEMO_AUTH_EXACT | PM | Alternative terminal reached only at the unauthorized exact-packet boundary. This state grants zero exchange, trading, order/probe, Decision Lease, Cost Gate, proof, serving, promotion, or `_latest` authority. |

## Exact Packet Binding

- Path: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-10--alr_f5_exact_demo_authorization_packet.json`
- SHA-256: `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`
- Source/runtime construction head: `091b5d446403d8fe83a15b57142819cbd1ceac6d`
- Packet status: `EXACT_DEMO_AUTHORIZATION_PACKET_READY_UNAUTHORIZED`
- Operator authorized: `false`
- Execution performed: `false`
- E3/BB review: immutable approval complete for Operator decision only, bound to the same packet SHA

Any packet-byte, candidate, source/runtime head, instrument, market, RiskConfig, Guardian, loss-envelope, order-shape, or lineage change invalidates this binding and requires ROTATE. Historical NEAR material and generic authorization requests are not consumable authority.

## Qualified Learning Rule

Scanner evidence selects research objects only. A row becomes a training label/reward only when strategy, symbol, side, and decision context match and the point-in-time manifest, actual fee/slippage/funding, order-to-fill reconstruction, `proof_packet_v1`, `reward_ledger_v1`, and after-cost label all pass. Training/evaluation additionally requires walk-forward, purge/embargo, OOS, matched controls, negative cells, and reconstructable lineage. Eligible evidence requires an actual run with `model_training_performed=true`; output remains challenger-only and cannot serve or promote automatically.

## Shared Guards

- No ALR-initiated Bybit REST/WS, official MCP, order/probe/cancel/modify/close, live/mainnet, or private exchange access.
- No Guardian, RiskConfig, order-dispatch, Decision Lease policy, global Cost Gate, engine, or scanner mutation.
- Scanner ranking, snapshots, registry, no-fill facts, and artifact counts never become trade/proof/reward authority.
- No auto-serving/promotion, `_latest` overwrite, or protected-evidence deletion.
- Any runtime apply requires fresh Mac/GitHub/Linux alignment and exact-scope `PM -> E3 -> BB -> PM`; stale approvals do not carry forward.
- Exact-packet authorization, if ever granted, must be atomic and SHA-bound; this queue and the packet itself are not authorization.
