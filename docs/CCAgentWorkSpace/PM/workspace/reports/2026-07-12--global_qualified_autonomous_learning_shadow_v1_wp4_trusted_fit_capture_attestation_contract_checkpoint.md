# WP4 Trusted Fit-Capture Attestation Contract — Source Checkpoint

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-TRUSTED-FIT-CAPTURE-ATTESTATION-CONTRACT-DESIGN-TDD`
Source checkpoint: `a09c70f243723fea1645b597e96c6cf08795fd6c`
Status: `DONE_SOURCE_ACCEPTED_TRUSTED_FIT_CAPTURE_ATTESTATION_CONTRACT`

## Accepted source effect

`alr_challenger_fit_capture_attestation_contract_v1` revalidates the complete
qualified training-result observation before binding a closed fit capture. It
derives source-head, input-lineage, dataset, row, split, code, config,
feature/label-schema, runner-identity, and q10/q50/q90 readback identities from
bounded raw bytes. Raw bytes are not retained in the serialized candidate.

The candidate is fixed to `OUT_OF_BAND_FIT_ATTESTATION_REQUIRED`. It keeps
`execution_claim` and `model_training_performed_claim` at `NOT_ESTABLISHED`,
sets persistence false, preserves every no-authority flag as false and every
authority counter as zero, and exposes no database, filesystem, trainer,
LightGBM, ONNX-runtime, V158, registry, symlink, serving, or promotion surface.

An optional host callback receives only immutable schema, digest, and canonical
bytes. Only literal `True` yields `FIT_CAPTURE_ATTESTED_EPHEMERAL`, and that
result remains `EXTERNAL_HOST_UNCHECKED`, non-persistent, no-authority, and
incapable of establishing execution or model training. Callback exceptions,
truthy non-booleans, mutation, missing callbacks, malformed contracts, and
bounded deep/wide/cyclic/exploding/infinite inputs fail closed.

Frozen SHA-256 values:

- source module: `48e7593137ace2e7132a19617e02dfb621e96da771f44ece2f6e2a84b790738f`
- source tests: `5ed3354c19f5d997fb4e1c718e0ba0949c5fced192ed3842a89df9bc06a27623`

## Verification

- RED checkpoints covered the absent API and builder, raw-material/hash-only
  substitution, self-consistent runner and material-budget tampering, numeric
  total-size aliases, and E2's integer/float aliases for required evidence
  booleans.
- Focused fit-capture suite: `43 passed`.
- Adjacent result/repository/training-contract/V158 suite: `217 passed`.
- Full ML suite: `1998 passed, 36 skipped`.
- Current-head E2, E4, CC, and MIT: PASS; P0/P1/P2 `0/0/0`.
- Governed current-head E4 capture:
  `9250f3ab31b17ec557f613629c7eb3eb70a4625e70e6677a4094c81daef61447`.
- Python compile, diff check, clean worktree, rebase patch-id, and exact source
  hashes: PASS.

## Deliberate unexecuted boundary

This is deterministic source-only structural evidence, not a trusted producer
attestation. No trainer or fit ran; no model, ONNX, or filesystem artifact was
created or read; V158 was not applied; PostgreSQL, Linux, runtime services, and
Bybit were not contacted. No durable receipt/run/artifact/registry row,
attestation, symlink, serving/promotion state, order, risk/Cost Gate change, or
authority was created. G3 and G4 remain failed.

## Next safe action

The Goal remains `ACTIVE`. A fresh exact-head scan found `140` migrations,
maximum V158, zero duplicate versions, and no V159 source or reservation. The
next item is
`WP4-DURABLE-FIT-ATTESTATION-SCHEMA-DESIGN-PREAUTHORING-GATE`.

That loop may design and adversarially review a forward durable-attestation
relation and fixed writer/read boundary that binds the qualified receipt,
result, fit-capture, runner, actual-input material set, artifact trio, trusted
external issuer receipt, verification interval, and zero authority. It must
reject `EXTERNAL_HOST_UNCHECKED` and prevent the V158 v1 result writer from
forming an unattested `TRAINING_PERFORMED` fact after the forward schema.

This next loop is design plus a fresh E3/BB source-authoring gate only. It does
not reserve, author, or apply V159; contact PostgreSQL/Linux/Bybit; run a fit;
create model files; or grant registry, serving, promotion, or trading authority.
