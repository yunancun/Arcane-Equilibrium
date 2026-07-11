# G1-G9 Gap Matrix

Baseline verified: 2026-07-10T09:55:00Z..2026-07-10T09:58:00Z
WP1 runtime checkpoint: 2026-07-10T14:36:40Z..2026-07-10T14:43:50.582201Z
Mac/origin at apply: `a927c37d14f768b923f11b29ea61d8e94ca8d5ff`
Linux checkout and running ALR pin: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`
WP2-A source checkpoint: `c84e14f5de67f8a6e55d3759d307087323118f86`
WP2-B candidate-board extraction: `13d2b980cecd4b9f83de669c19220c820afe4e89`
WP2-B prospective-lineage checkpoint: `1afdf423104ce8303d90f9e86b0896039948a692`
WP2-B validated-lineage propagation checkpoint: `38ccd014c5ce974fbd395625b9597e12832395ee`

| Gate | Status | Machine/source evidence | Exact missing producer/transition | Severity / terminal impact | Highest-ROI safe action / role gate |
|---|---|---|---|---|---|
| G1 Collection | `PARTIAL` | Fresh raw/ALR identity and lag `0` remained healthy through WP1. Runtime checkout and service pin now equal exact target `7d1c24794`; one session stayed stable with restart `0` and scanner INSERT denied. | Candidate decision, order/fill, actual cost/funding, and risk-context adapters remain absent. | P0; blocks terminal | WP2 selection, then WP3 adapters. Any external acquisition remains exact E3/BB/Operator gated. |
| G2 Candidate selection | `PARTIAL_SOURCE_ACCEPTED` | B2.2c source acceptance `328125a08` adds immutable board-handoff identity, scanner-idle board-delta processing, artifact-store replay suppression, restart integrity checks, and durable no-qualified rotation. Focused `109`, integration `190`, E2/QC/QA PASS, P0/P1 `0/0`. | Runtime deployment/natural-cycle proof of the handoff remains external-gated; candidate qualification itself remains absent. | P0; blocks terminal | Do not apply runtime. Advance source-only WP3 proof/reward adapters; later B2.2c runtime proof requires fresh exact E3/BB. |
| G3 Outcome chain | `FAIL` | Last accepted WP1 runtime snapshot had 638 feedback rows, all DEFER; ProofPacket-present `0`; Reward total `0`; complete PIT->fill->cost->proof->reward->label chain `0`. WP2-A did not re-probe runtime. | Runtime repository adapters and one current candidate-matched controlled Rust evidence chain. | P0; blocks terminal | WP3 source adapters first. Any external acquisition requires fresh exact E3/BB + Operator + same-window Rust gates. |
| G4 Actual training | `FAIL` | Last accepted WP1 runtime snapshot had 638 runs, all `scanner_novelty_statistical_baseline/DEFER_EVIDENCE`; `model_training_performed=0`; no model artifact/registry. WP2-A did not re-probe runtime. | Eligible multi-sample labels, actual fit, hashes, isolated registry, next versioned migration. | P0; blocks terminal | WP4; never train on one fill merely to check G3. V152/V153 stay immutable. |
| G5 OOS evaluation | `FAIL` | Hidden OOS state `0`; source selector scaffolding exists but runtime has no qualified training/evaluation. | Walk-forward, purge/embargo, hidden OOS, controls/negative/regime/stress/leakage/dedup runtime lineage. | P0; blocks terminal | WP5 preregistration and adversarial fixtures via QC/MIT/AI-E. |
| G6 Decisions | `FAIL` | Runtime distribution is DEFER only; V152/V153 constrain allowed run/feedback states. | Durable DEFER/ROTATE/TRAIN/REJECT/CHALLENGER_ACCEPT/ROLLBACK/STOP reasons and hashes. | P0; blocks terminal | WP4 schema + WP5 decision engine. `CHALLENGER_ACCEPT` remains no-authority. |
| G7 Auto-evolution | `FAIL` | No second evidence-delta re-evaluation/retrain/rotation proof; current baseline delta hash only. | Evidence-delta trigger, cooldown/idempotency, two-delta natural-cycle evidence, restart recovery. | P0; blocks terminal | WP6 after WP1-WP5. |
| G8 Artifact/retention usefulness | `PARTIAL_WP1_PASS` | WP1 immutable checkpoint: stale/new normalized health rows `740/117.05 h^-1` (ratio `0.1582`), bytes `1,755,280/406,509 h^-1` (ratio `0.2316`); `74/87` health writes suppressed; one equivalent decision suppressed; cache/retention `0/0`. | Useful model/evaluation/registry/effect artifacts and eligible-cache quarantine/grace/recheck/sweep proof remain missing. | P0; blocks terminal | WP4 useful artifacts, then WP6 retention. Protected evidence never ordinary-delete. |
| G9 Boundaries | `PARTIAL_WP1_PASS` | WP1 isolated and production evidence has all authority false/zero; direct run/feedback mismatch `0/0`; scanner INSERT, health UPDATE, and run DELETE denied. Only the ALR service restarted; engine/API/watchdog identities stayed fixed; no exchange/order/lease/Cost Gate action occurred. | Re-audit after selector, schema, training, and runtime changes; future G3 external evidence must prove local and exchange-side disaster protection plus current GUI/Rust/Guardian/Lease lineage. | P0; blocks terminal | Every WP static authority tests; WP7 current runtime E3/BB audit. |

## Superseded evidence

SUI packet:

```text
status=ROTATED_UNCONSUMABLE_STALE_PACKET
packet_sha256=1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde
consumable=false
operator_decision_requested=false
reasons=[SOURCE_HEAD_DRIFT,CURRENT_CANDIDATE_NOT_SUI,CURRENT_GUI_RUST_RISKCONFIG_EQUITY_CAP_LINEAGE_INVALID,CURRENT_GUARDIAN_BBO_ORDER_SHAPE_LINEAGE_INVALID,E3_BB_REVIEWS_PRESENTATION_ONLY_AND_STALE]
```

NEAR evidence:

```text
status=FROZEN_INVALIDATED_EFFECTIVE_SAMPLE
n_raw=5058
distinct_entry_ts=2
n_eff=1
utc_days=1
verdicts=[SAMPLE_INSUFFICIENT_AFTER_DEDUP,EXECUTION_REALISM_SUSPECT]
edge_claim_allowed=false
no_edge_claim_allowed=false
order_dispatch_allowed=false
```

The original artifacts remain historical and unmodified. A future candidate
must pass the landed WP-A.6 preregistered gates and bind full current lineage.
