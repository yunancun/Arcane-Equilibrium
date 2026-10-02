# D1.1 fixed ONNX and advisory contract smoke

This fixture trio exercises the public Rust loader/predictor and the existing pure
predictor gate. `apply_advisory_action` additionally consumes an authoritative
router baseline and an already-selected action. The router tests compose the real
`process_gates_only_with_features` baseline with that pure consumer.

This is mechanics evidence. The legacy predictor still emits Accept/Reject/Fallback;
no quantile-to-size calibration, model SIZE_DOWN serving caller, registry activation,
or venue execution is enabled. A fixture cannot qualify a real market cell.

## Action contract

- `NO_OP` preserves baseline action, quantity and reason. Serialized `ALLOW`
  is accepted only as an alias and serializes back to `NO_OP`.
- `VETO` can reject an allowed increasing entry, with zero final quantity.
- `SIZE_DOWN.max_quantity` is a finite absolute cap in the baseline instrument's
  quantity units. A smaller positive cap reduces quantity; zero denies. A cap
  greater than or equal to baseline preserves the baseline and its reason.
- Negative/non-finite caps deny an eligible entry with a stable invalid-input
  reason. An invalid allowed baseline quantity also fails closed for SIZE_DOWN.
- Baseline denial and its reason are preserved first. Risk reduction, unknown
  classification, or unmatched/unknown model identity bypass even malformed actions.
- The caller supplies Rust-derived position classification and independently
  checked identity. This scalar consumer cannot establish qualified generation,
  change price/instrument/side/order fields, or normalize venue lot sizes.

For the same fixture event, baseline ALLOW 0.001 plus model cap 0.0004 produces
ALLOW 0.0004 with reason `fixture_policy_quantity_cap`. These literals are fixed
independently of the implementation and bound in `aiml_d1_shared_inputs.json`.
The cap is a fixture policy input, not inferred from the ONNX predictions.

## Inputs and exact predictions

Shared mechanics contract SHA-256: `08353f098f8aa6e022aa241f982b729bf55a0c906b442aad2f9404da1cb873d7`.
The true selected cell, PIT availability/revisions, label/cost/split and
trial/holdout lineage remain incomplete. PA/MIT acceptance and PM real-input
freeze have not occurred; D1.1 remains open. Any shared field change invalidates
its digest and requires affected consumers to be revalidated.

| Fixture | SHA-256 | Expected bps |
| --- | --- | ---: |
| q10 | `afe5733af214e49797a2997e1ca314ee99d87232e03fea2eaa05b0aa2038aa31` | -1.5273265838623047 |
| q50 | `d8201723e4fc5d0c06193d542b54a0ac2a6c6dd4a0c9b6339f3ac2e6f283bf59` | 1.7042269483208656 |
| q90 | `dd222cd5ecf5b47af325c869a7f0eb1a329c134cf6791b950edad8b570d5e10c` | 4.102983659686288 |

Absolute tolerance is fixed at **0.00001 bps** before inference. Existing graph
and weights were preserved when correcting definition metadata. Retry, alias,
model version and fixture identity never create independent market samples.

## Rerun

From the repository root, with the locked Rust dependencies and compatible local
ONNX Runtime available, use an isolated `CARGO_TARGET_DIR`. The recorded Mac run
uses Rust 1.95.0, ort 2.0.0-rc.12/API24 and local ONNX Runtime 1.27.
Set `ORT_SKIP_DOWNLOAD=1`, `ORT_LIB_LOCATION` and the platform library search path
for that local installation. Cargo `--offline` alone does not attest that build
scripts cannot access the network.

```sh
cargo test --locked --offline --manifest-path rust/openclaw_engine/Cargo.toml --features edge_predictor_ort --lib edge_predictor:: -- --nocapture
cargo test --locked --offline --manifest-path rust/openclaw_engine/Cargo.toml --features edge_predictor_ort --lib predictor_wiring_tests -- --nocapture
cargo test --locked --offline --manifest-path rust/openclaw_engine/Cargo.toml --features edge_predictor_ort --test edge_predictor_ort_backend -- --nocapture
cargo test --locked --offline --manifest-path rust/openclaw_engine/Cargo.toml --features edge_predictor_ort --lib reload_edge_predictor -- --nocapture
```

The ONNX file is feature-gated: **zero tests or an entirely skipped file is not a
pass**. Logs print loaded hashes, exact predictions and same-event action traces.
Direct-path reload remains rejected under ADR-0051. Independent reviews remain
UNVERIFIED until the original controlled review lane can legally resume.
