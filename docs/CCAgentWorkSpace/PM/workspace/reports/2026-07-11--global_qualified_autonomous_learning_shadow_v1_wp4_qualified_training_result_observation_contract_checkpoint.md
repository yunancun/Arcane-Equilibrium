# WP4 Qualified Training-Result Observation Contract — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-QUALIFIED-TRAINING-RESULT-CONTRACT-TDD`
Source checkpoint: `c64c5e28be80bad1093c39c90eda161004ab34d5`
Status: `DONE_SOURCE_ACCEPTED_QUALIFIED_TRAINING_RESULT_OBSERVATION_CONTRACT`

## Accepted source effect

`build_alr_challenger_training_result_contract(...)` and its public pure
validator consume one complete validated
`alr_challenger_training_contract_v1` plus the exact `FOUND` qualified-receipt
read. The closed observation shape binds the LightGBM trainer specification and
admitted non-Boolean seed, canonical UTC timestamps, model schema,
q10/q50/q90 raw ONNX bytes and I/O descriptors, exact-decimal metrics, and
integer resource observations.

Callers cannot supply lineage, artifact, run, challenger, or result hashes;
paths; statuses; persistence; or authority. Raw model bytes derive each
artifact hash and size plus the exact ordered q10/q50/q90 set hash. The
contract derives its run, challenger, and result identities internally.

The envelope is fixed to `POST_FIT_RESULT_OBSERVATION` with status
`EXECUTION_EVIDENCE_REQUIRED`. Execution and model-training claims remain
`NOT_ESTABLISHED`; observation, trainer, seed, artifact, metrics, and resource
claims remain `UNVERIFIED`; persistence is false; trusted fit-capture
attestation and V158 persistence-schema binding are required. Bounded snapshot
and validation logic is total over ordinary malformed deep, wide, cyclic,
exploding, and infinite container inputs.

Frozen SHA-256 values:

- repository module: `c9c1ad2ea6b5fa5280a165172daadba4ea93c82e733d8170e8217fc8a1696c26`
- result-contract module: `47a49abf8ebfe94e1cdd2b8996e1e33c0c870818d227e8f3e36fc26f46c9a03a`
- repository tests: `e9d3b259b5a509b9d22fefa9f0b0735fd4f08c9f50730a86792190e02d8fe8d8`
- result-contract tests: `4f7943cc0811b7100b01a8b38987429608721e02489204e1d968082e72919761`

## Verification

- Eight RED checkpoints covered the missing module/API and pure receipt
  validator, absent builder, malformed admission/authority acceptance,
  mixed-key and resource-budget failures, deep/exploding inputs, eager/infinite
  sequences, and missing trainer-spec/seed binding.
- Focused repository/result suite: `105 passed`.
- Adjacent training-contract/repository/result/V158 suite: `174 passed`.
- Full ML suite: `1955 passed, 36 skipped in 22.07s`.
- Same-environment receipt-reader baseline: `1911 passed, 36 skipped`; exact
  result-contract delta `+44`.
- PA, E2, E4, and MIT: PASS; final P0/P1/P2 `0/0/0`.
- Governed E4 captures: focused
  `2a6663d3806738c33235fb8570920d46692dc79caace332c74c3848210ff7673`,
  adjacent
  `dac6e439502f69f6ce130d1db8cabce06cd282feee87262360379b5f6eda048e`,
  diff check
  `84fe23c04afefbbc3a7d393aa9108741ddd5a75b7d10b9b3fe47d4f8bac9f5be`,
  clean status
  `48d7ecacfefd03672d2433c0d2383dcdd46133969a360da0b8c39812052e79a9`.
- Python compile, public API/shape pins, forbidden-input scans, and diff checks:
  PASS.

## Deliberate unexecuted boundary

This was source-only synthetic-fixture TDD. V158 was not applied or exercised
against PostgreSQL; Linux, runtime services, and Bybit were not contacted. No
receipt/result API, trainer, or fit ran. This step created no durable
receipt/run/artifact/registry row, fitted matrix, model or ONNX file, artifact
readback, attestation, symlink, serving/promotion state, order, lease, Cost
Gate change, or authority. G3 and G4 remain failed.

## Next safe action

The Goal remains `ACTIVE`. Design and TDD only a pure trusted fit-capture
attestation contract/verifier. It must bind actual input rehashes, trusted
runner identity, the observed trainer specification and seed, exact
`result_hash`, artifact readback, and ONNX semantic-validation obligations
without accepting caller self-attestation as execution proof. Migration
authoring/apply, result persistence adapters, trainer execution, fit,
filesystem publication, registry, PostgreSQL/Linux/runtime, serving, and
exchange work remain later gates.
