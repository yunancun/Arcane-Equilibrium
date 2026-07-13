# Operator Mirror — WP4 V160-Style Atomic Consumption Design

Status:
`DONE_DESIGN_ACCEPTED_V160_STYLE_ATOMIC_CONSUMPTION_PREAUTHORING_GATE` against
reviewed source head `9a41c8d2abf34dbdce01fde010a500b4c19ba4f4`.

The accepted design uses a dedicated platform-attested Rust strict-Ed25519
verifier and a phase-bound `alr_fit_ed25519_verification_receipt_v1`, never a
bool callback or role claim. One fixed coordinator later owns six bounded
actions: register, claim, record status, consume terminal, expire unclaimed,
and append optional reconcile audit evidence. No transaction spans fit.

Only authenticated `SUCCEEDED` may atomically commit the terminal plus the
complete V159 attestation, completed run, ordered q10/q50/q90 artifacts, and
`NOT_SERVING` registry bundle. `REJECTED_PRE_FIT`, `FAILED_AFTER_START`, and
`EXPIRED_UNCLAIMED` write no V159 state. Immutable request/nonce/generation/
claim/terminal identities are the retry and conflict safety oracle; reconcile
markers are audit only.

The future roles are membership-free coordinator owner and single-connection
caller. Old V159 application wrappers and direct INSERT paths must be
unreachable, while the exact V158 qualified-receipt writer/reader remains.
Deletion tests must show that removing coordinator `EXECUTE` or the real
verifier leaves no eligible V159 application write path.

PA/FA/CC/E3/MIT accepted the repaired design at final P0/P1/P2=`0/0/0`.
Fresh migration inspection is `141/max159/duplicates0/V160 absent`.

This gate made no source, test, migration, PG, filesystem-transport, network,
Linux/runtime, issuer/runner, broker, signature-verification, fit, model,
row/registry, serving/promotion, order, risk/Cost Gate, or authority effect.
Production/runtime V159 remains unapplied and unrefreshed. A production verifier
does not exist, V160 was not reserved or authored, and source authoring is
`NOT_AUTHORIZED_YET`.

G1/G2 remain partial, G3/G4 and G5-G7 remain failed, and G8/G9 remain partial.
The Goal and WP4 stay active.

The next loop is only the read-only
`WP4-TRUSTED-ED25519-VERIFIER-SOURCE-PREAUTHORING-GATE`: freeze the exact Rust
verifier module/API, byte ownership, strict result/error taxonomy, attestation
boundary, dependency/offline posture, and mutation tests. It does not authorize
source/tests, V160 reservation or authoring, PG/runtime/issuer/runner/fit,
model/registry state, serving/promotion, broker/order/risk, Cost Gate, or
authority.
