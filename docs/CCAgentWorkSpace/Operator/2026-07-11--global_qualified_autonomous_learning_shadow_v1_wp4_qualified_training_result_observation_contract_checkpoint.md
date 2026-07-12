# Operator Mirror — WP4 Qualified Training-Result Observation Contract

Status: `DONE_SOURCE_ACCEPTED_QUALIFIED_TRAINING_RESULT_OBSERVATION_CONTRACT`
at `c64c5e28be80bad1093c39c90eda161004ab34d5`.

The pure source contract now accepts only a complete validated training
contract plus its exact `FOUND` qualified receipt and a closed post-fit
observation. It binds trainer spec/seed, canonical timestamps, q10/q50/q90 raw
bytes and I/O descriptors, exact-decimal metrics, and integer resources, then
derives artifact, run, challenger, and result identities internally. Callers
cannot provide hashes, paths, statuses, persistence, or authority.

Eight RED-to-GREEN checkpoints, focused `105`, adjacent `174`, full ML
`1955/36`, exact same-environment delta `+44`, and PA/E2/E4/MIT P0/P1/P2
`0/0/0` passed. Governed captures and frozen source hashes are recorded in the
PM checkpoint.

Execution and model-training claims remain `NOT_ESTABLISHED`; all submitted
observation claims remain `UNVERIFIED`; persistence is false. This did not
apply V158, contact PostgreSQL/Linux/runtime/Bybit, run a trainer or fit, or
create a durable row, model/file, artifact readback, attestation, registry,
symlink, serving/promotion state, order, lease, Cost Gate change, or authority.
G3/G4 remain failed.

The Goal remains active. Next is only trusted fit-capture attestation contract
design/TDD binding actual input rehashes, trusted runner identity, trainer
spec/seed, exact result hash, artifact readback, and ONNX semantic obligations.
Migration, persistence adapters, execution, filesystem, registry, runtime,
serving, and exchange work remain later gates.
