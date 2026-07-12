# WP4 Trusted-Issuer / Isolated-Runner Handshake — Design Preauthoring Gate

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item:
`WP4-TRUSTED-ISSUER-ISOLATED-RUNNER-HANDSHAKE-DESIGN-PREAUTHORING-GATE`
Reviewed source head: `2189c996101da680a8ac9ec426d28c1028b3557d`
Status:
`DONE_DESIGN_ACCEPTED_TRUSTED_ISSUER_ISOLATED_RUNNER_HANDSHAKE_PREAUTHORING_GATE`

## Gate result

The fail-closed handshake design is accepted for **pure source and
mutation-biting test authoring only**. It does not authorize dispatch,
cryptographic key access, receipt acquisition, PostgreSQL or filesystem
contact, runner execution, fit, model creation, V159/V160 authoring or apply,
or any runtime/serving/trading effect.

The design closes the source-level ambiguity between a qualified V158
admission and a trusted V159 execution receipt. It does not claim that the
ambiguity is operationally closed. Goal and WP4 remain `ACTIVE`; G3 and G4
remain failed.

Independent contract/identity compatibility and adversarial security reviews
resolved the V159 session-user atomicity, admission singleton, pre-fit expiry,
partial-failure truth, signature-preimage, canonical-byte, revocation,
outer/inner equality, and replay findings. Final P0/P1/P2 is `0/0/0`.

## Existing evidence boundary

The existing chain is reusable but deliberately incomplete:

- `alr_challenger_training_contract_v1` binds repository evidence, exact
  training inputs, code, effective configuration, and resource budget into
  `contract_hash`, `training_input_hash`, and `training_key_hash`.
- V158 makes `durable_receipt_hash + training_key_hash` the durable admission
  key while keeping training/model/registry permissions false.
- The structural result and fit-capture contracts bind `attempt_id`, actual
  inputs, trainer/seed/times, q10/q50/q90 readback, and post-fit runner
  identity. They remain `NOT_ESTABLISHED`; an arbitrary callback can reach
  only `FIT_CAPTURE_ATTESTED_EPHEMERAL / EXTERNAL_HOST_UNCHECKED`.
- V159 contains the final immutable attestation and atomic
  run/artifact/`NOT_SERVING` registry binding. Its writer checks an exact
  closed receipt projection, identity lineage, database time, replay, ACLs,
  and false/zero authority.

V159 is containment, not a trusted handshake. Its closed
`alr_fit_execution_signed_receipt_v1` projection has no request digest,
nonce, audience, pre-fit runner target, trust-policy snapshot, or one-time
request-consumption identity. The writer accepts caller-supplied
`SIGNATURE_VERIFIED_BY_TRUST_POLICY` fields after structural checks; it does
not resolve a trust root or cryptographically verify the signature. The green
disposable probe intentionally used a synthetic base64-shaped signature.

Therefore no design or later implementation may claim that V159 alone proves
issuer authenticity, request freshness, isolated-runner use, or one-request /
one-execution consumption.

## Frozen protocol

### 1. Issuer-signed pre-fit request

The source contract is named `alr_trusted_fit_execution_request_v1`. It has
an exact bounded `signed_payload`, a derived `request_hash`, and a detached
`authentication.signature`.

The signed payload must bind:

- `durable_receipt_hash`, `training_key_hash`, training `contract_hash`,
  qualified-receipt binding hash, source head, every expected input hash,
  training rows, code/config hashes, execution-contract hash, and resource
  budget hash;
- a 256-bit public request nonce, its domain-separated `nonce_digest`, and a
  strictly positive request generation;
- exact requester/issuer identity, audience, trust-policy ID, immutable policy
  snapshot digest and epoch, allowed signing-key-set digest, algorithm, and
  key ID;
- a pre-fit `runner_target_policy_hash` covering the expected producer kind,
  runner source/measurement constraints, isolation class, capability class,
  and output contract. It must not substitute the post-fit
  `runner_identity_hash`;
- `issued_at`, `not_before`, `accept_by`, and `complete_by`;
- q10/q50/q90, ONNX semantic validation, immutable artifact readback, zero
  external requests/API cost, and all other existing execution obligations;
- every no-authority field false and every authority counter zero.

`request_hash` is the domain-separated SHA-256 of the canonical signed
payload. It is also the only permitted `attempt_id` and the only permitted
post-fit runner `invocation_id`. This connects the pre-fit request to the
existing structural result and runner identities without changing their hash
formulas.

The request contract itself has
`status=EXTERNAL_DISPATCH_AUTHORIZATION_REQUIRED`,
`dispatch_allowed=false`, `training_allowed=false`,
`persistence_allowed=false`, and grants no authority. Source construction is
not permission to contact a runner.

### 2. Atomic runner claim before fit

A future stateful runner seam must enforce two identities:

- singleton admission identity
  `(durable_receipt_hash, training_key_hash)`; and
- request identity
  `(issuer_id, trust_policy_snapshot_digest, request_hash, nonce_digest,
  request_generation)`.

The request generation is strictly monotonic per admission. At most one active
or non-retryable terminal request may exist for an admission before any input
consumption or fit. Exact request retry returns the existing claim/status and
must not launch another fit. Reuse of a nonce with different bytes, use by a
different runner target, a different request for an already active admission
key, a non-monotonic generation, or any payload divergence is a permanent
conflict.

Request expiry before claim becomes the durable request-state terminal
`EXPIRED_UNCLAIMED`: it has no runner receipt, input consumption, fit, or
V159 state. A new monotonic generation is allowed only after the future fixed
coordinator consumes that exact signed request expiry using trusted time. A
post-fit-only nonce or a nonce invented by the runner cannot prove fresh
execution.

### 3. Trusted terminal receipt for the isolated runner

The response contract is named `alr_isolated_fit_execution_receipt_v1`. It
is signed by the trusted issuer only after the issuer's platform-attested
capability verifies the isolated runner; a runner self-signature alone is not
eligible. Its signed payload must echo `request_hash`, `nonce_digest`,
request generation, audience, policy snapshot, and the actual runner
measurement/isolation and capability identities.

It has exactly three terminal outcome classes:

- `SUCCEEDED`: binds every existing V159 subject hash, structural result,
  fit-capture, runner, actual-input material set, ordered artifact set, exact
  result observation, execution claims, and the digest of the byte-exact
  V159-compatible inner receipt.
- `REJECTED_PRE_FIT`: requires literal
  `actual_inputs_consumed=false`, `fit_started=false`,
  `model_training_performed=false`, no result/artifact payload, and one
  closed failure code/phase.
- `FAILED_AFTER_START`: records truthful monotonic observed stage facts plus
  a closed failure code/phase, fixes
  `v159_success_projection_allowed=false`, and must never carry an inner V159
  receipt or permit automatic retry.

`ACCEPTED_IN_PROGRESS` is a signed nonterminal status response, not a
terminal receipt. Missing response, transport timeout, malformed or
unauthenticated bytes, and conflicting responses produce local
`RECONCILE_REQUIRED`, not a new fit request.

The outcome field matrix is closed:

| Outcome | Required | Forbidden |
|---|---|---|
| `SUCCEEDED` | request/claim identity, actual authenticated runner, all five V159 success claims literal true, complete structural result/fit-capture/material/artifact identities, complete inner V159 receipt | failure diagnostics, missing/partial inner receipt |
| `REJECTED_PRE_FIT` | request/claim identity, `rejected_at`, closed pre-fit failure code, all execution/model/artifact/persistence booleans false | fit/result/fit-capture/model/artifact identities or bytes, inner V159 receipt |
| `FAILED_AFTER_START` | request/claim identity, `fit_started=true`, closed phase/code, truthful monotonic stage observations, `v159_success_projection_allowed=false`, persistence false | successful V159 projection, inner V159 receipt, automatic retry |
| `ACCEPTED_IN_PROGRESS` | request/claim identity, `accepted_at`, strictly monotonic status generation, `status_issued_at`, `status_expires_at` | terminal marker, execution success/failure claims, result/artifact/inner receipt |

One request has at most one terminal receipt. An exact byte replay is
idempotent. Any divergent terminal receipt is a permanent conflict. A new
request generation for the same admission is possible only after a durably
consumed `REJECTED_PRE_FIT` or `EXPIRED_UNCLAIMED`; success, after-start
failure, or ambiguous timeout forbids autonomous re-execution.

### 4. Canonical bytes and signatures

Every signature is detached and never signs a structure containing itself.
Three preimages and construction order are distinct:

1. sign the request payload with
   `ALR_TRUSTED_FIT_REQUEST_V1\0 || u64be(length) || canonical_payload`,
   then append the request signature;
2. for `SUCCEEDED`, sign the V159 inner projection **with its
   authentication.signature field omitted** using
   `ALR_V159_INNER_FIT_RECEIPT_V1\0 || u64be(length) || canonical_inner_unsigned`,
   append that signature, then canonicalize the complete inner bytes and
   derive their digest; and
3. encode the completed inner bytes as strict unpadded RFC 4648 base64url in
   `inner_receipt_bytes_base64url`, bind
   `inner_receipt_digest_sha256` over the decoded raw PostgreSQL
   `jsonb::text` bytes, place both in the outer terminal payload, then sign
   that payload with
   `ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1\0 || u64be(length) || canonical_outer_payload`
   before appending the outer signature.

No inner field covers the outer receipt, no outer signature enters the inner
preimage, and no signature or envelope digest covers itself. Authentication
context—issuer/requester, audience, policy snapshot/epoch, key-set digest, key
ID, and algorithm—is inside each applicable signed payload.

For `SUCCEEDED`, outer-to-inner equality is exhaustive: every V159 subject
hash, all five literal-true claims, the full result observation,
issuer/policy/key/algorithm, `verified_at`, `expires_at`, no-authority map,
and authority counters must be typed-equal. In particular,
`outer.issuer_verified_at == inner.verified_at`,
`outer.receipt_expires_at == inner.expires_at`, and recomputing the complete
inner envelope digest must equal the outer-bound inner digest. A digest match
without this full semantic equality is insufficient.

The outer request and runner receipt use one frozen bounded canonical-JSON
profile: UTF-8; unique ASCII string keys sorted lexicographically by UTF-8
bytes; `json.dumps(..., sort_keys=True, separators=(",",":"),
ensure_ascii=True, allow_nan=False)` equivalence; exact JSON scalar types; and
explicit byte/nesting limits. The successful inner V159 receipt remains
byte-exact to the existing PostgreSQL `jsonb::text` contract: keys ordered by
`(UTF8-byte-length, UTF8-bytes)`, separators `(", ", ": ")`, ASCII-bounded
protocol values, and no non-finite values. Outer and inner canonicalizers must
never be conflated.

Base64url decoding is strict: alphabet `[A-Za-z0-9_-]`, no padding or
whitespace, canonical re-encoding must equal the submitted text, and the inner
digest is computed only after decoding. The `1,048,576` inner limit applies
to decoded bytes; the `2,097,152` outer limit applies to the final encoded
outer envelope.

`ed25519` is the only eligible handshake-v1 signature algorithm. V159's
broader structural enum does not expand this protocol. ECDSA requires a new
protocol version with a separately frozen canonical low-S encoding.
Each request, inner, and outer Ed25519 signature field is the strict unpadded
base64url encoding of exactly 64 signature bytes (exactly 86 ASCII
characters); decoding and canonical re-encoding must reproduce the submitted
text.

The exact outer limits are depth `64`, nodes `50,000`, request bytes
`2..1,048,576`, terminal-receipt bytes `2..2,097,152`, and inner V159
receipt bytes `2..1,048,576`. Identifiers remain bounded ASCII, hashes remain
exact lowercase hex, integer fields reject booleans/floats, duplicate keys and
unknown fields reject, and raw bytes never appear in error text.

All newly derived identities use:

`H(domain,payload) = SHA256("alr_trusted_fit_handshake_v1\0" || domain ||
"\0" || u64be(len(canonical(payload))) || canonical(payload))`.

The 256-bit nonce is exactly 64 lowercase hex characters decoded to 32 bytes;
`nonce_digest = SHA256("alr_trusted_fit_handshake_v1\0nonce\0" ||
nonce_bytes)`. `request_hash=H("request_signed_payload", signed_payload)`.
`execution_contract_hash=H("execution_contract", exact_execution_contract)`,
`resource_budget_hash=H("resource_budget", exact_resource_budget)`,
`trust_policy_snapshot_digest=H("trust_policy_snapshot",
closed_policy_snapshot)`, and
`runner_target_policy_hash=H("runner_target_policy",
closed_runner_target_policy)`. The allowed-key-set digest uses
`H("allowed_key_set", ordered_entries)` with entries sorted by
`(issuer_id,key_id,generation,algorithm,public_key_digest)`.

The qualified-receipt binding is not redefined: it must reuse exactly
`_domain_hash("qualified_receipt_read", validated_read)` from the accepted
training-result contract. No second receipt-binding formula is allowed.

A verifier intersects two independent inputs: the request-pinned immutable
trust-policy snapshot and a closed
`alr_fit_trust_key_status_overlay_v1` with exactly
`schema_version,evidence_tier,issuer_id,trust_policy_snapshot_digest,key_id,
public_key_digest,algorithm,generation,status,observed_at,valid_until,
provider_evidence_digest,overlay_digest`. The overlay must be
`PLATFORM_OR_EXTERNAL_ATTESTED`, bind the same issuer/key bytes/digest,
generation and algorithm, and satisfy
`observed_at <= adjudicated_at < valid_until` with
`valid_until-observed_at <= 300 seconds`. `adjudicated_at` is an explicit
canonical UTC verifier input; `overlay_digest=H("key_status_overlay",
overlay_without_digest)`. Missing, stale, mismatched, unauthenticated, or
ambiguous overlay evidence fails closed; receipt bytes cannot supply it.
`ACTIVE` keys may sign new requests/receipts. `RETIRED` keys may verify an
already issued, still-fresh receipt only when the pinned policy explicitly
allows it. `REVOKED`, `COMPROMISED`, `EXPIRED`, unknown, ambiguous, or a
reused key ID with different key bytes always rejects. Receipt-provided
`authentication_status`, a matching session role, self-hash, callable
identity, fixture key, or truthy return value is never authenticity evidence.
Key rotation outside the pinned snapshot fails closed; it requires a new
request rather than silently changing trust semantics.

### 5. Closed failures and deterministic precedence

The public failure enum is closed to:

`STRUCTURE_INVALID`, `CANONICAL_BYTES_INVALID`,
`REQUEST_SIGNATURE_INVALID`, `REQUEST_NOT_YET_VALID`,
`REQUEST_EXPIRED`, `AUDIENCE_MISMATCH`, `POLICY_OR_KEY_REJECTED`,
`RUNNER_TARGET_MISMATCH`, `NONCE_REPLAY_CONFLICT`,
`RECEIPT_SIGNATURE_INVALID`, `RECEIPT_REQUEST_BINDING_MISMATCH`,
`RECEIPT_TIME_INVALID`, `RECEIPT_OUTCOME_INVALID`,
`EXECUTION_CLAIM_MISMATCH`, `V159_INNER_SIGNATURE_INVALID`,
`V159_INNER_RECEIPT_MISMATCH`,
`AUTHORITY_MISMATCH`, `RECONCILE_REQUIRED`,
`DURABLE_CONSUMPTION_REQUIRED`, and
`DURABLE_CONSUMPTION_CONFLICT`.

Validation precedence is deterministic: bounds/shape/canonical bytes; request
signature and pinned policy; request audience/time; pre-fit claim/replay state;
receipt signature and pinned policy; receipt request/nonce/time/runner/outcome
binding; V158/V159 lineage, actual inputs, resources and artifacts; then
false/zero authority and final verdict. Tests must mutate every branch and
prove the same first public code without exposing keys, signatures, raw bytes,
paths, or provider details.

### 6. Time and replay rules

Every terminal runner-receipt outcome first requires
`issued_at <= not_before <= accepted_at <= accept_by < complete_by` and
`issuer_verified_at < receipt_expires_at`. Outcome-specific fields then
apply:

- `SUCCEEDED` requires
  `accepted_at <= fit_started_at <= accept_by`,
  `fit_started_at <= fit_completed_at <= complete_by`, and
  `fit_completed_at <= captured_at <= issuer_verified_at`; fit duration and
  all resource observations must remain inside the signed request budget.
- `REJECTED_PRE_FIT` forbids fit/capture/result/artifact timestamps and
  payloads; it requires `rejected_at` between `accepted_at` and
  `issuer_verified_at` plus literal pre-fit/no-input/no-model claims.
- `FAILED_AFTER_START` requires `fit_started_at`, may include
  `failure_observed_at`, and permits `fit_completed_at` or `captured_at`
  only when actually observed and ordered; missing later phases remain absent,
  never synthesized.

`ACCEPTED_IN_PROGRESS` instead requires
`accepted_at <= status_issued_at < status_expires_at <= complete_by`; it has
no issuer terminal-verification or receipt-expiry fields. Its monotonic stage
booleans are observational only and never authorize a V159 projection.

Request acceptance/start freshness and V159 attestation/bind expiry are
different clocks and must not substitute for each other.

### 7. Pure verification verdict

The future pure verifier must validate the request, outer terminal, and inner
V159 signatures; exact bytes; request and nonce binding; exhaustive
outer-to-inner equality; audience; pinned policy plus current revocation
overlay; key usage; time ordering; runner target/actual identity; all existing
V158/V159 hashes; actual inputs; resource budget; artifacts; and
failure-branch exclusivity. Inner signature failure maps specifically to
`V159_INNER_SIGNATURE_INVALID`.

Its maximum pure/no-write verdict is `AUTHENTICATED_UNCONSUMED`. Without a
platform-attested trust capability it remains `EXTERNAL_HOST_UNCHECKED`.
Neither verdict writes a row, launches a fit, or establishes
`TRAINING_PERFORMED`.

An arbitrary `Callable -> bool` is not an eligible success Adapter. Synthetic
source tests may exercise deterministic branches but must remain visibly
fixture-only and cannot emit a production-trusted verdict.

### 8. Required forward durability seam

Current V159 cannot durably expose or atomically consume the request/nonce and
policy-snapshot identities. Its attestation and result wrappers also require
different exact `session_user` identities, so one transaction cannot obtain
atomicity by calling those wrappers sequentially.

A later, separately reviewed V160-style companion seam must introduce a new
single fixed coordinator owner/caller Interface with exact forward
catalog/ACL/owner/body guards, no generic DML or cross-seam grants, and a
single atomic transaction. The later preauthoring gate must determine how the
existing wrappers are made unreachable from the application path; this gate
does not approve that schema or privilege change.

That fixed coordinator must atomically:

1. enforce and consume the singleton
   `(durable_receipt_hash,training_key_hash)` admission plus the exact
   monotonic request-generation identity and nonce once;
2. persist the authenticated outer terminal receipt;
3. independently reverify the inner signature and, for `SUCCEEDED` only,
   insert/bind the exact V159 attestation and complete bundle atomically with
   that consumption through the new fixed Interface—not by sequential calls
   to the current V159 wrappers;
4. for `REJECTED_PRE_FIT`, close the claim as no-execution without creating
   any V159 attestation/run/artifact/registry row;
5. for `FAILED_AFTER_START`, close and quarantine the claim without V159
   success projection or automatic retry; and
6. for `EXPIRED_UNCLAIMED`, consume the signed request expiry with trusted
   time, create no runner receipt or V159 state, and permit only the next
   monotonic generation; and
7. return an exact duplicate for byte-identical re-consumption while mapping
   every divergent or partial reuse to
   `DURABLE_CONSUMPTION_CONFLICT`.

Until that forward seam has its own design, source, disposable-PG, and
runtime gates, `AUTHENTICATED_UNCONSUMED` is not eligible for production
persistence and no real issuer/runner contact is authorized.

## Acceptance / rejection matrix

| Case | Required result |
|---|---|
| Exact signed request replay before or during execution | Return existing claim/status; do not start another fit |
| Same nonce or request hash with different bytes/audience/runner | Permanent conflict |
| Future, stale, expired, revoked, unknown-key, wrong-usage, or wrong-audience request/receipt | Reject closed |
| Exact authenticated success with every V158/V159 binding | `AUTHENTICATED_UNCONSUMED`; no write or authority |
| Exact authenticated `REJECTED_PRE_FIT` | Terminal no-execution fact; new generation only after future durable consumption |
| Exact unclaimed request expires under trusted time | Future seam records `EXPIRED_UNCLAIMED`; no runner/V159 state; next monotonic generation only after consumption |
| `FAILED_AFTER_START`, timeout, missing or ambiguous response | `RECONCILE_REQUIRED`; no automatic retry |
| Receipt does not echo request/nonce/policy/runner target | Reject closed |
| V159 inner bytes/digest/projection or structural hashes differ | Reject closed |
| Literal callback true, self-hash, role match, or fixture signature only | `EXTERNAL_HOST_UNCHECKED` |
| Exact already-consumed success | Future companion returns duplicate; never a second fit/bind |

## Deliberate no-effect boundary

This gate read only source text and synthetic-test contract definitions. It did
not create, read, sign, verify, transmit, or persist request/receipt evidence
bytes; author source/tests/SQL/workflow; contact PostgreSQL, files as transport,
Linux, runtime, network, issuer, runner, broker, or exchange; execute trainer
or fit; create/read model artifacts; mutate registry/serving/promotion state;
or grant Guardian, Lease, Cost Gate, risk, order, proof, latest, runtime,
serving, promotion, or trading authority.

Qualified-learning, actual-training, model-artifact, and challenger-registry
counts remain zero. Production/runtime V159 remains unapplied and unrefreshed.
G1/G2 remain partial, G3/G4 and G5-G7 remain failed, G8/G9 remain partial, and
terminal eligibility remains false.

## Next safe action

Advance only to
`WP4-TRUSTED-ISSUER-ISOLATED-RUNNER-HANDSHAKE-CONTRACT-SOURCE-TDD`.

That gate may author one pure contract module and mutation-biting tests for the
frozen request, runner receipt, canonical/signature preimages, state machine,
and pure/no-write verifier behavior using synthetic fixtures. Synthetic tests
cannot emit production-trusted `AUTHENTICATED_UNCONSUMED`. It may not contact
an issuer/runner, consume real bytes, open PostgreSQL/files/network, modify
V158/V159 or reserve V160, execute trainer/fit, create model files, or perform
any runtime/authority effect. A V160-style durability design-preauthoring gate
must follow before any stateful or external integration.
