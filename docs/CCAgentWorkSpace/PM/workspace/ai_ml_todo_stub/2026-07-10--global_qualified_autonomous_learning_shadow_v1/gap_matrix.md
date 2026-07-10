# G1-G9 Gap Matrix

Baseline verified: 2026-07-10T09:55:00Z..2026-07-10T09:58:00Z
Mac/origin/Linux: `1a3ecdd57927e70dd8c6dedfed4ecef04c7a46d3`
Running ALR source pin: `8dfa1200a37351b142df60f8cd8bd84a5adce6c5`

| Gate | Status | Machine/source evidence | Exact missing producer/transition | Severity / terminal impact | Highest-ROI safe action / role gate |
|---|---|---|---|---|---|
| G1 Collection | `PARTIAL` | Fresh raw/ALR latest identity matched; lag `0`; raw `80,495`, ALR `5,261`, historical remainder `75,234`; 583 notifications received/consumed, 0 invalid/duplicate. Source already has split cursors/LISTEN. | Candidate decision, order/fill, actual cost/funding, and risk-context adapters are absent; service pin differs from checkout and next restart will fail closed. | P0; blocks terminal | WP1 first, then WP2/WP3. Runtime repin/restart only through E3/BB. |
| G2 Candidate selection | `FAIL` | 364 candidate artifacts; all `scanner_novelty`, side `NONE`, no horizon/regime; only 37 IDs; ADA repeated 209 times. V152 locks novelty/DEFER. | Full candidate identity, distinct-entry/day/regime/quality/proof-gap/EVI/cost/cooldown arbiter and global rotation. | P0; blocks terminal | WP2 via QC/MIT/AI-E then PA/E1/E2/E4/QA. |
| G3 Outcome chain | `FAIL` | 362 feedback rows all DEFER; ProofPacket-present `0`; Reward total `0`; complete PIT->fill->cost->proof->reward->label chain `0`. | Runtime repository adapters and one current candidate-matched controlled Rust evidence chain. | P0; blocks terminal | WP3 source adapters first. Any external acquisition requires fresh exact E3/BB + Operator + same-window Rust gates. |
| G4 Actual training | `FAIL` | 362 runs; all `scanner_novelty_statistical_baseline/DEFER_EVIDENCE`; `model_training_performed=0`; no model artifact/registry. | Eligible multi-sample labels, actual fit, hashes, isolated registry, next versioned migration. | P0; blocks terminal | WP4; never train on one fill merely to check G3. V152/V153 stay immutable. |
| G5 OOS evaluation | `FAIL` | Hidden OOS state `0`; source selector scaffolding exists but runtime has no qualified training/evaluation. | Walk-forward, purge/embargo, hidden OOS, controls/negative/regime/stress/leakage/dedup runtime lineage. | P0; blocks terminal | WP5 preregistration and adversarial fixtures via QC/MIT/AI-E. |
| G6 Decisions | `FAIL` | Runtime distribution is DEFER only; V152/V153 constrain allowed run/feedback states. | Durable DEFER/ROTATE/TRAIN/REJECT/CHALLENGER_ACCEPT/ROLLBACK/STOP reasons and hashes. | P0; blocks terminal | WP4 schema + WP5 decision engine. `CHALLENGER_ACCEPT` remains no-authority. |
| G7 Auto-evolution | `FAIL` | No second evidence-delta re-evaluation/retrain/rotation proof; current baseline delta hash only. | Evidence-delta trigger, cooldown/idempotency, two-delta natural-cycle evidence, restart recovery. | P0; blocks terminal | WP6 after WP1-WP5. |
| G8 Artifact/retention usefulness | `PARTIAL` | 20,825 artifacts / 493.99 MB payload; last hour ~52.9 MB, dominated by history backfill; health `735 rows/1.256 MB`; cache/retention `0/0`. | State-delta/heartbeat suppression, bytes/rows/cycle metrics, useful model/eval/registry/effect artifacts, eligible-cache retention proof. | P0; blocks terminal | WP1 churn control, then WP4/WP6 retention. Protected evidence never ordinary-delete. |
| G9 Boundaries | `PARTIAL` | Current ALR output has authority false/zero; service is local event-driven. No exchange action occurred. | Re-audit after schema/training/runtime changes; future G3 external evidence must prove local and exchange-side disaster protection plus current GUI/Rust/Guardian/Lease lineage. | P0; blocks terminal | Every WP static authority tests; WP7 current runtime E3/BB audit. |

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
