# Operator Note: Bounded Probe Active Effective Cap Guard

Date: 2026-06-25
Status: DONE_WITH_CONCERNS

PM closed the source-only effective/post-round cap slice for active bounded Demo probes. The dormant active dispatch seam now rechecks `effective_qty * limit_price <= approved_cap` immediately before sending an `OrderDispatchRequest`, and sends nothing if the final draft breaches cap.

This grants no runtime adapter enablement, no probe/order authority, no Cost Gate lowering, and no promotion proof.

Canonical report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--bounded_probe_active_effective_cap_guard.md`.
