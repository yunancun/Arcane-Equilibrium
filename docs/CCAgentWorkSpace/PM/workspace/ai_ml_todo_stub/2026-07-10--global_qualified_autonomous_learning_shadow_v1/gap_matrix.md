# G1-G9 Gap Matrix

Baseline verified: 2026-07-10T09:55:00Z..2026-07-10T09:58:00Z
WP1 runtime checkpoint: 2026-07-10T14:36:40Z..2026-07-10T14:43:50.582201Z
Mac/origin at apply: `a927c37d14f768b923f11b29ea61d8e94ca8d5ff`
Linux checkout and running ALR pin: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`
WP2-A source checkpoint: `c84e14f5de67f8a6e55d3759d307087323118f86`
WP2-B candidate-board extraction: `13d2b980cecd4b9f83de669c19220c820afe4e89`
WP2-B prospective-lineage checkpoint: `1afdf423104ce8303d90f9e86b0896039948a692`
WP2-B validated-lineage propagation checkpoint: `38ccd014c5ce974fbd395625b9597e12832395ee`
WP2-B READY-handoff repair checkpoint: `03ef761bf92a6055ef3555d68d47a1f075b2298b`
WP2-B event-primary checkpoint: `1b85318f29a16d5a7575b27cb158486fdfd47331`
WP3 proof/reward validation adapter checkpoint: `8999aa2b7e4a3bba3841f4c72cf054d88cb69c5c`
WP3 read-only repository adapter checkpoint: `c2bdefbfdb52eeaab4e801de783719ecfe0da7bc`
WP4 schema-required challenger-training contract checkpoint: `f36379b9ddf10ee1055daeda27805c409c6ee8bd`
WP4 forward-only V158 source schema checkpoint: `beeb77325c83a157c74cf54e79b7146876ed5e27`
WP4 durable-receipt writer repository checkpoint: `c0aec6813b59f3c17b1fb93350794a3581ccd5ae`
WP4 qualified-receipt reader checkpoint: `fb842a36f006ad58249ff536a455232d2c455f8b`
WP4 qualified training-result observation checkpoint: `c64c5e28be80bad1093c39c90eda161004ab34d5`
WP4 trusted fit-capture attestation candidate checkpoint: `a09c70f243723fea1645b597e96c6cf08795fd6c`
WP4 durable fit-attestation V159 source checkpoint: `27bfe34b608b732071205c351dd1aa3fdd7d2283`
WP4 disposable PostgreSQL verification checkpoint: `74d8475e32ff89b67e2b6a1346e0839bbcfa646f`, run `29195892105`

| Gate | Status | Machine/source evidence | Exact missing producer/transition | Severity / terminal impact | Highest-ROI safe action / role gate |
|---|---|---|---|---|---|
| G1 Collection | `PARTIAL` | Fresh raw/ALR identity and lag `0` remained healthy through WP1. Exact head `74d8475e3` now also proves isolated V159 functional/concurrency behavior and cleanup. | Candidate decision, order/fill, actual cost/funding, and risk-context runtime evidence remain absent. | P0; blocks terminal | Freeze only the trusted-issuer/isolated-runner handshake design; any external acquisition remains exact E3/BB/Operator gated. |
| G2 Candidate selection | `PARTIAL_DISPOSABLE_PG_VERIFIED` | The WP2/WP3 lineage chain and WP4 source chain are preserved. Hosted run `29195892105` proved V159 double-apply, ACL, replay/expiry, atomicity, collisions, readback, concurrency, and zero-authority behavior in two isolated disposable databases; cleanup left zero survivors. | Linux runtime proof, current candidate qualification, production V159 apply, real durable row/readback, trusted issuer receipt, and real execution remain absent. | P0; blocks terminal | Execute only the design-preauthoring handshake gate. Production/runtime proof remains a later fresh exact E3/BB gate. |
| G3 Outcome chain | `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN` | Last accepted WP1 runtime snapshot had 638 feedback rows, all DEFER; ProofPacket-present `0`; Reward total `0`; complete PIT->fill->cost->proof->reward->label chain `0`. V159 isolated behavior is now verified, but only with synthetic fixtures destroyed after the run. | Separately gated production apply, one real durable receipt/readback, platform/external trusted issuer receipt, production caller, and one current candidate-matched controlled Rust evidence chain. | P0; blocks terminal | Design the issuer/runner handshake only; external acquisition, production apply, and real evidence remain separately gated. |
| G4 Actual training | `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED` | Last accepted WP1 runtime snapshot had 638 DEFER-only runs and `model_training_performed=0`. Disposable probes explicitly report synthetic signature fixtures and `model_fit_performed_by_probe=false`; no trainer/fit, model bytes, or production rows exist. | Isolated runner, separately gated real fit and external issuer receipt, immutable model trio readback, production apply, and runtime registry rows. | P0; blocks terminal | Define only the isolated-runner handshake. Do not execute a real fit or claim training; never train on one fill merely to check G3. |
| G5 OOS evaluation | `FAIL` | Hidden OOS state `0`; source selector scaffolding exists but runtime has no qualified training/evaluation. | Walk-forward, purge/embargo, hidden OOS, controls/negative/regime/stress/leakage/dedup runtime lineage. | P0; blocks terminal | WP5 preregistration and adversarial fixtures via QC/MIT/AI-E. |
| G6 Decisions | `FAIL` | Runtime distribution is DEFER only; V152/V153 constrain allowed run/feedback states. Disposable V159 verification creates no real execution or decision. | Durable DEFER/ROTATE/TRAIN/REJECT/CHALLENGER_ACCEPT/ROLLBACK/STOP reasons and hashes. | P0; blocks terminal | Design the issuer/runner handshake, then separately gate any later trainer before WP5. `CHALLENGER_ACCEPT` remains no-authority. |
| G7 Auto-evolution | `FAIL` | Event-primary candidate-board source transport is accepted at `1b85318f`, but no second evidence-delta re-evaluation/retrain/rotation runtime proof exists. | Linux service activation, evidence-delta trigger, cooldown/idempotency, two-delta natural-cycle evidence, restart recovery. | P0; blocks terminal | WP6 after WP1-WP5 under fresh E3/BB; source transport alone is not evolution proof. |
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
