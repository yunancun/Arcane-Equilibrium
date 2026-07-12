# Operator Mirror — WP4 Trusted Ed25519 Verifier Source Preauthoring

Status:
`DONE_DESIGN_ACCEPTED_TRUSTED_ED25519_VERIFIER_SOURCE_PREAUTHORING_GATE`
against reviewed clean head
`75f3db2b55cd1d9737d83c811d291abecb67ad49`.

The next separately governed source/TDD gate may add one isolated
`openclaw_alr_fit_verifier` Rust library, exact lock entries, one static guard,
and dedicated CI only. It may not wire core/engine/types, Python runtime,
PostgreSQL, V160, trainer/model/registry, broker, order/risk, Guardian, Lease,
Cost Gate, serving, promotion, or authority paths.

The verifier constructs request/status/terminal/inner Ed25519 preimages
internally and uses only `ed25519-dalek 2.2.0` strict verification. Its maximum
success is
`STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED` with
`capability_authenticity=SOURCE_ONLY_UNATTESTED`. Semantic phase, canonical
input, envelope/payload parity, policy/overlay adjudication, trusted time,
platform attestation, durable consumption, persistence, training, coordinator
eligibility, and model training remain unestablished.

The receipt has exact deterministic top/evidence/job schemas, 17 false
authority fields, 17 zero counters, checked 10 MiB aggregate input, fallible
allocation, closed total errors, and redacted Debug. The future attestation seam
must re-run the verifier in-process from original inputs; caller-made receipt
bytes/digests cannot be attested or promoted.

The later source gate records the one-time public crates.io fetch, tests online
and from a distinct initially absent offline target, parses metadata/lock
graphs, inventories licenses/build scripts/unsafe/advisories, and proves that
the live engine cannot reach the verifier dependency.

PA/FA/CC/E3/MIT independently accepted the repaired design at final
P0/P1/P2=`0/0/0`. This checkpoint itself fetched no crate and authored no
source/test/Cargo/lock/workflow/SQL. Public official documentation lookup was
research only. No PG/Linux/runtime/issuer/runner/broker/real-byte/fit/model/
registry/serving/order/risk/Cost Gate or authority effect occurred. V160 remains
absent/unreserved and production/runtime V159 remains unapplied/unrefreshed.

G1/G2 remain partial, G3/G4 and G5-G7 failed, and G8/G9 partial. Goal and WP4
remain active. The next state is
`ACTIVE_WP4_TRUSTED_ED25519_VERIFIER_SOURCE_TDD_GATE`; it is source-only until
its own governed RED/GREEN, offline, supply-chain, and independent review gates
pass.
