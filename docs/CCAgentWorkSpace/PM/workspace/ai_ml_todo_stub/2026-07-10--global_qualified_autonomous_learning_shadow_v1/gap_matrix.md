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

| Gate | Status | Machine/source evidence | Exact missing producer/transition | Severity / terminal impact | Highest-ROI safe action / role gate |
|---|---|---|---|---|---|
| G1 Collection | `PARTIAL` | Fresh raw/ALR identity and lag `0` remained healthy through WP1. Runtime checkout and service pin now equal exact target `7d1c24794`; one session stayed stable with restart `0` and scanner INSERT denied. | Candidate decision, order/fill, actual cost/funding, and risk-context runtime evidence remain absent. | P0; blocks terminal | Design the durable attestation boundary, then later controlled acquisition. Any external acquisition remains exact E3/BB/Operator gated. |
| G2 Candidate selection | `PARTIAL_SOURCE_ACCEPTED` | The immutable handoff/replay checkpoint `328125a08` is preserved. Event checkpoint `1b85318f` replaces five-second polling. WP3 repository `c2bdefbf` reconstructs current projection/lineage; writer/reader `c0aec681` / `fb842a36` bind exact validated contract identity to V158; result observation `c64c5e28` derives closed identities; fit-capture `a09c70f2` rehashes actual input/runner/readback bytes. Fit-focused `43`, adjacent `217`, full ML `1998/36`, reviews `0/0/0`. | Linux runtime proof, candidate qualification, V158 apply, durable row/readback, trusted issuer attestation, and execution remain absent. | P0; blocks terminal | Run the durable-attestation schema design pre-authoring gate. Later runtime proof requires fresh exact E3/BB. |
| G3 Outcome chain | `FAIL_SOURCE_FIT_CAPTURE_ATTESTATION_CONTRACT_ACCEPTED_DURABLE_SCHEMA_UNAPPLIED` | Last accepted WP1 runtime snapshot had 638 feedback rows, all DEFER; ProofPacket-present `0`; Reward total `0`; complete PIT->fill->cost->proof->reward->label chain `0`. WP3 derives inputs; V158 declares durability; writer/reader prove fake-DB mapping; result observation binds closed post-fit inputs; fit-capture `a09c70f2` binds structural actual-input/runner/artifact evidence while explicitly remaining externally unchecked and non-persistent. | Forward durable attestation schema, separately gated V158/V159 apply, one real durable receipt/readback, platform/external trusted issuer receipt, and one current candidate-matched controlled Rust evidence chain. | P0; blocks terminal | Design only the durable attestation relation and fail-closed result boundary; external acquisition and PG apply remain separately gated. |
| G4 Actual training | `FAIL_SOURCE_FIT_CAPTURE_ATTESTATION_CONTRACT_ACCEPTED_EXECUTION_NOT_ESTABLISHED` | Last accepted WP1 runtime snapshot had 638 DEFER-only runs and `model_training_performed=0`. Fit-capture `a09c70f2` revalidates the result and actual input/runner/q10-q90 readback bytes; focused `43`, adjacent `217`, full ML `1998/36`, reviews `0/0/0`. Serialized and ephemeral paths keep execution/training `NOT_ESTABLISHED`, persistence false, and authenticity `EXTERNAL_HOST_UNCHECKED`. | Durable attestation/result schema accepting only trusted, current issuer receipts; later isolated runner, separately gated real fit, immutable model trio readback, migration apply, and runtime registry rows. | P0; blocks terminal | Execute `WP4-DURABLE-FIT-ATTESTATION-SCHEMA-DESIGN-PREAUTHORING-GATE`; do not build persistence/runner execution atop the untrusted candidate. Never train on one fill merely to check G3. |
| G5 OOS evaluation | `FAIL` | Hidden OOS state `0`; source selector scaffolding exists but runtime has no qualified training/evaluation. | Walk-forward, purge/embargo, hidden OOS, controls/negative/regime/stress/leakage/dedup runtime lineage. | P0; blocks terminal | WP5 preregistration and adversarial fixtures via QC/MIT/AI-E. |
| G6 Decisions | `FAIL` | Runtime distribution is DEFER only; V152/V153 constrain allowed run/feedback states. The source fit-capture candidate cannot establish execution or a decision. | Durable DEFER/ROTATE/TRAIN/REJECT/CHALLENGER_ACCEPT/ROLLBACK/STOP reasons and hashes. | P0; blocks terminal | WP4 durable attestation schema and later trainer first, followed by the WP5 decision engine. `CHALLENGER_ACCEPT` remains no-authority. |
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
