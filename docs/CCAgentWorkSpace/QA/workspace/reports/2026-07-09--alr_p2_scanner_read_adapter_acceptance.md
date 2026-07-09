# QA Acceptance - ALR P2-1 Scanner Read Adapter

Date: 2026-07-09
Verdict: PASS_TO_FRESH_E3_BB_GATE
Scope: P2-1 source acceptance only; this is not P2 operational completion or a runtime soak.

| Chain stage | Evidence | Status |
|---|---|---|
| Rust scanner producer | `runner.rs` snapshots the post-update registry and emits `TradingMsg::ScannerSnapshot`. | PASS |
| Durable scanner source contract | V030 defines the nine required `trading.scanner_snapshots` fields and `(scan_id, ts)` primary key; writer uses `ON CONFLICT DO NOTHING`. | PASS |
| ALR read adapter | Exact field validation, canonical SHA-256, duplicate/late disposition, non-rewinding watermark, and lifecycle checks are covered by 14 direct tests. | PASS |
| Authority boundary | Runtime invocation returned `scanner_evidence_only=true` and every exchange/trading/proof/serving/promotion flag false; static scan found no direct DB/network/trading import or call. | PASS |
| Persistence/restart/repository | Not implemented in P2-1. | WAITING_P2-2 |
| Service/event loop/training/evaluation/retention/health/soak | Not implemented in P2-1. | WAITING_P2-3..P2-8 |

E4 evidence is two identical runs of the focused plus adjacent ALR suite:
`153 passed, 0 failed`. The scanner adapter is evidence-only and does not make a
scanner fact a proof, trading, serving, or promotion authority.

The full runtime E2E checklist is intentionally not run: P2-1 neither applies a
migration nor starts a service, and the active root TODO requires a fresh
`PM -> E3 -> BB -> PM` gate before P2-2 can create/apply the isolated
`learning.alr_*` persistence surface or consume Linux runtime state. The QA role
memory file is left untouched because it has pre-existing unrelated dirty edits.
