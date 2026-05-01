# RFC — MLDE-6 Live Promotion Contract

Date: 2026-05-01
Owner: PA
Status: Ready for PM/E2/E4 review
Scope: Wave 4 pre-stage RFC for the MLDE path from advisory output to governed live candidate.

## Executive Summary

MLDE-6 defines the contract for moving ML/Dream/LinUCB recommendations through a governed ladder:

`advisory -> proposal -> demo patch -> live candidate -> operator-approved live application`

The key boundary is unchanged: demo may auto-apply bounded changes, but live/live_demo must never be auto-applied without GovernanceHub approval and a Decision Lease.

Current code fact:

- V031 `learning.mlde_shadow_recommendations` stores advisory/shadow outputs and has `requires_governance` plus `decision_lease_id`.
- V032 `learning.mlde_param_applications` stores demo applications and live promotion candidates.
- Both migrations enforce that `live` / `live_demo` applied rows require a non-empty `decision_lease_id`.

## State Machine

| Stage | Table / Status | Allowed Engine | Who Can Advance | Required Evidence |
|---|---|---|---|---|
| Advisory | `mlde_shadow_recommendations.applied=false` | demo/live_demo/live read-only rows | trainer/advisor | source, confidence, sample_count, expected_net_bps |
| Proposal | recommendation type `parameter_proposal` or `experiment_plan` | demo primary | MLDE scheduler | confidence >= threshold, sample_count >= threshold |
| Demo Patch | `mlde_param_applications.status=applied` | demo only | demo applier | bounded delta, IPC success, previous snapshot |
| Live Candidate | `status=candidate`, `application_type=live_promotion_candidate` | live_demo/live candidate row only | demo applier | demo uplift window, rollback patch, counterfactual summary |
| Live Application | `status=applied` | live_demo/live | operator + GovernanceHub | Decision Lease id, unexpired approval, audit mirror |

## Contract Schema

Every live candidate payload must include:

```json
{
  "schema_version": "mlde_live_promotion_v1",
  "source_recommendation_id": 0,
  "target_engine": "live_demo",
  "target_surface": "strategy_params|risk_config",
  "target_name": "grid_trading",
  "patch": {},
  "rollback_patch": {},
  "evidence_window": {
    "start_ts": "",
    "end_ts": "",
    "sample_count": 0,
    "primary_metric": "net_bps_after_fee",
    "baseline_net_bps": 0.0,
    "candidate_net_bps": 0.0,
    "confidence": 0.0
  },
  "counterfactual": {
    "report_path": "",
    "expected_net_bps": 0.0,
    "known_limitations": []
  },
  "operator_review": {
    "required": true,
    "review_route": "/api/v1/mlde/live-candidates/{id}",
    "expires_at": ""
  }
}
```

Versioning rule: consumers must fail closed on unknown `schema_version`.

## Promotion Gates

Minimum candidate gates:

- `sample_count >= 200` for the affected strategy/cell, unless the candidate is explicitly `dry_run`.
- `confidence >= 0.70`.
- primary metric is post-fee `net_bps_after_fee`.
- demo application exists and has an attached `prev_snapshot`.
- rollback patch is structurally valid before any approval is shown to the operator.
- candidate row is immutable after operator review starts; revisions create a new candidate row.

Live application gates:

- operator role auth passes;
- GovernanceHub `acquire_lease()` returns a non-empty lease id;
- target engine is still authorized by the live auth boundary;
- patch stays inside existing RiskConfig/strategy parameter ranges;
- SM-04 style audit mirror records who/what/why/previous/new/lease.

## Rollback

Rollback path is part of the candidate, not an afterthought:

1. apply `rollback_patch` through the same IPC/write path as the original patch;
2. mark the application row `status=failed` or append a new reversal row;
3. release or expire the Decision Lease;
4. emit operator-visible audit text with candidate id and lease id.

## E1 Work Items

| ID | Scope | Files |
|---|---|---|
| MLDE6-T1 | candidate payload validator + version fail-closed | `program_code/.../app` or `ml_training` validator module |
| MLDE6-T2 | API read/review route for candidate rows | control API route + tests |
| MLDE6-T3 | governed application path requiring Decision Lease | GovernanceHub integration tests |
| MLDE6-T4 | rollback validator | tests for patch and rollback symmetry |

## Acceptance

MLDE-6 RFC is implementation-ready when:

- candidate schema validator rejects missing rollback, unknown schema, and live applied rows without lease;
- API can list and inspect candidates without mutating live state;
- at least 8 tests cover advisory, demo applied, candidate, applied-with-lease, reject-without-lease, rollback, version mismatch, and immutable revision behavior;
- E2 confirms no ML/Dream/Agent code path can call `patch_risk_config` or `update_strategy_params` for live/live_demo without GovernanceHub + Decision Lease.

## Root-Principle Check

| Principle | Verdict |
|---|---|
| #2 Read/write separation | Preserved; advisory rows are not execution queues. |
| #3 AI output is not command | Central contract: AI creates candidate, not command. |
| #7 Learning does not rewrite Live | Preserved through demo-only auto-apply and live governance. |
| #8 Explainability | Candidate payload carries evidence, patch, rollback, and lease. |
| #11 Agent autonomy | Preserved within hard boundaries; agent can propose, not self-authorize live. |
| #13 Cost awareness | Candidate evidence keeps net post-fee metric as primary. |

## Open Questions

- Whether the first operator review UI is a full GUI panel or a read-only API route plus CLI review command.
- Whether candidate expiry should default to 24h or align with the Decision Lease TTL used by LG-4.

