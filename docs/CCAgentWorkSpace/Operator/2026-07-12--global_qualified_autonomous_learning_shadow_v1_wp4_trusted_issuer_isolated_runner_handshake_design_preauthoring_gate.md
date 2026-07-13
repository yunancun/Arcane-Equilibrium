# Operator Mirror — WP4 Trusted-Issuer / Isolated-Runner Handshake Design

Status:
`DONE_DESIGN_ACCEPTED_TRUSTED_ISSUER_ISOLATED_RUNNER_HANDSHAKE_PREAUTHORING_GATE`
at reviewed source head
`2189c996101da680a8ac9ec426d28c1028b3557d`.

Independent contract/identity and adversarial security reviews finished at
P0/P1/P2 `0/0/0` after the repaired design below.

The accepted design separates four things that were previously easy to
overclaim:

1. an issuer-signed pre-fit request with a 256-bit nonce, exact V158 admission,
   immutable trust-policy snapshot, target-runner policy, time windows,
   resource limits, and false/zero authority;
2. an isolated runner claim made before fit and a trusted-issuer-signed
   terminal success/pre-fit-rejection/after-start-failure receipt that binds
   the actual measured runner;
3. a pure verifier whose maximum result is
   `AUTHENTICATED_UNCONSUMED`; and
4. a future V160-style seam with a new single fixed coordinator owner/caller
   that must atomically consume the admission/request/nonce/receipt and, for
   success only, insert the V159 attestation and complete bundle. It cannot
   obtain atomicity by sequentially calling the current V159 wrappers because
   those wrappers require different exact session users.

The singleton admission is `(durable_receipt_hash,training_key_hash)`; request
generation is monotonic and at most one active/non-retryable terminal request
may exist. Exact retries are idempotent. Divergent nonce/request/receipt or
durable-consumption reuse is a permanent conflict. A timeout or after-start
failure requires reconciliation and cannot autonomously launch another fit.
Only a durably consumed, authenticated `REJECTED_PRE_FIT` may later allow a
new request generation. A never-claimed expiry must first be durably closed as
`EXPIRED_UNCLAIMED` with trusted time and no runner/V159 state. Failure
terminals never call V159 success persistence. `FAILED_AFTER_START` records
truthful observed stages but fixes V159 success/persistence false and remains
non-retryable.

Handshake v1 accepts Ed25519 only. Request, inner V159 receipt, and outer
terminal receipt have three distinct domain-separated signature preimages,
with the inner signed and finalized before the outer binds its digest.
Verification intersects the request-pinned policy with a current
platform-attested revocation overlay whose exact issuer/key/generation,
`observed_at <= adjudicated_at < valid_until`, and at-most-300-second interval
are bound: retired-key verification is policy bounded, while missing/stale
status or revoked/compromised/expired/ambiguous keys always reject. Successful
outer JSON carries the complete inner PostgreSQL bytes as strict unpadded
base64url and hashes the decoded raw bytes.

V159 remains the durable containment layer, not the trust root. It does not
cryptographically verify signatures and does not currently persist request,
nonce, audience, pre-fit runner target, or trust-policy snapshot identities.
The disposable PG success therefore remains synthetic schema evidence, not a
real issuer, runner, fit, or model fact.

This gate created no request/receipt bytes, source, test, SQL, PG, file,
network, runtime, issuer/runner, trainer/fit, model, registry,
serving/promotion, broker/order/risk/Cost Gate, or authority effect.
Production/runtime V159 remains unapplied. G3/G4 remain failed and the Goal
remains active.

Next is only
`WP4-TRUSTED-ISSUER-ISOLATED-RUNNER-HANDSHAKE-CONTRACT-SOURCE-TDD`: one pure
contract module plus synthetic mutation-biting tests. Real bytes, external
contact, PostgreSQL/files/network, V159/V160 changes, fit/model effects, and
authority remain forbidden and separately gated.
