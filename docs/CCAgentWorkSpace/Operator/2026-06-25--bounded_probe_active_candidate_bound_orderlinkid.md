# Operator Note: Bounded Probe Active Candidate-Bound OrderLinkId

Date: 2026-06-25
Status: DONE_WITH_CONCERNS

PM closed the source-only orderLinkId/reconstruction slice for active bounded Demo probes. Future active bounded Demo order drafts must use a deterministic, Bybit-safe `orderLinkId` bound to engine mode, timestamp, sequence, side-cell, context id, and signal id.

This grants no runtime adapter enablement, no probe/order authority, no Cost Gate lowering, and no promotion proof.

Canonical report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--bounded_probe_active_candidate_bound_orderlinkid.md`.
