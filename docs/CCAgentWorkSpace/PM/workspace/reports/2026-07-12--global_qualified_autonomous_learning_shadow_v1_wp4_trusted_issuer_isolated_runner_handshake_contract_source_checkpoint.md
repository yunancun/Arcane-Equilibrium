# WP4 Trusted-Issuer / Isolated-Runner Handshake Contract — Source Checkpoint

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item:
`WP4-TRUSTED-ISSUER-ISOLATED-RUNNER-HANDSHAKE-CONTRACT-SOURCE-TDD`
Source checkpoint: `c900d1ecb2eac495994b8715f09ad10bee6d9583`
Status:
`DONE_SOURCE_ACCEPTED_TRUSTED_ISSUER_ISOLATED_RUNNER_HANDSHAKE_CONTRACT`

## Accepted source effect

The pure `alr_trusted_fit_handshake` module implements the frozen handshake
without I/O, external dispatch, persistence, or runtime surfaces. It builds
and validates the bounded issuer-signed request, accepted-in-progress status,
and terminal receipt envelopes while preserving distinct request, inner V159,
and outer-terminal signature domains.

The accepted contract closes these source-level seams:

- request hash as the only attempt and runner invocation identity;
- 256-bit nonce, monotonic request generation, immutable trust-policy snapshot,
  current revocation overlay, audience, and pre-fit runner-target binding;
- strict Ed25519 key/signature shapes and bounded canonical outer/inner bytes;
- exact replay, divergent conflict, expiry, and reconciliation semantics;
- complete V158 qualified-admission parity and success-only V159 projection;
- post-fit runner, actual-input, time, resource, q10/q50/q90 artifact, and
  terminal branch binding;
- exhaustive success, `REJECTED_PRE_FIT`, and `FAILED_AFTER_START`
  exclusivity plus fail-closed request-expiry handling; and
- fixed false/zero persistence, serving, promotion, trading, order, risk,
  Cost Gate, and other authority fields.

The module uses only the Python standard library plus existing pure public
validators. It reads no files, opens no sockets, calls no database, invokes no
subprocess, executes no trainer/fit, and writes no model or state.

Frozen SHA-256 values:

- source module:
  `32181c5f14e099c996befa9f84009b372b969edfecfce3741169aca7b5acb81d`
- source tests:
  `ac7ac6876f49ea13f1eadf202ef9eb42dfdc8d914a385de09a9b51ec4a19db20`
- V158 SQL:
  `7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b`
- V159 SQL:
  `2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74`
- training contract:
  `9549db6557f6d2241cbfe375f1d012db06f7e988438d3c6b13f2768c94ca4776`
- receipt repository:
  `c9c1ad2ea6b5fa5280a165172daadba4ea93c82e733d8170e8217fc8a1696c26`
- training-result contract:
  `47a49abf8ebfe94e1cdd2b8996e1e33c0c870818d227e8f3e36fc26f46c9a03a`
- fit-capture contract:
  `48e7593137ace2e7132a19617e02dfb621e96da771f44ece2f6e2a84b790738f`

## TDD and verification

The contract went through four RED-to-GREEN cycles. Cold mutation reviews
exposed singleton replay, status progression, runner splice, elapsed/resource,
capture-time, totality, overlay TOCTOU, failure-phase, precedence, lower-bound
freshness, malformed signature/audience taxonomy, cross-window time,
inner-crypto precedence, fit-runner mapping, fixture-flag, and structure-first
multi-fault defects. Each was reproduced before repair.

- focused handshake suite: `105 passed`;
- adjacent five-contract suite: `285 passed`;
- full ML suite: `2103 passed, 36 skipped`;
- Python compile and scoped diff check: PASS.
- hosted CI run `29201919849` (#1090): `7/7` jobs SUCCESS, including both
  Rust targets, governance/static guards, and the schema-consumer disposable-PG
  contract job. PR #3 remained open and draft; no rerun, comment, or merge was
  performed.

E4 governed capture digests:

- focused record:
  `sha256:52d304f118275856decfde8b872e6cf97b6c6719ec52aec556b51a7f3b287b34`;
- adjacent record:
  `sha256:a036fcfc5fcdd03d73d17072c7cc03c51b56209b6a74438a076ded1305a07c3f`;
- full record:
  `sha256:9df8dceae36d9d27d26ac18daf6f970b8448b88da03cb78cdc8f89f2eec75d04`;
- full stdout:
  `sha256:b3c12f9995c71dc6b5e6820ab0068fa9db14476e9a4c16e7e7fa99c82d1dbd95`;
- full replay:
  `sha256:4247b5a165ea43cd73a52b94e4429099f1e9ee3fba0f8ea85131517ae633ef65`.

## Independent reviews

Final E2 contract/security review, E3 boundary review, E4 source regression,
CC constitutional review, and MIT data/ML review all passed with exact current
source. Final P0/P1/P2 is `0/0/0`. CC graded the boundary `A`, `16/16`, with
zero boundary fingerprints. MIT explicitly classified the result as
source-ready only: runtime, training, serving, promotion, and profit remain
`NOT_ESTABLISHED`.

## Deliberate unexecuted boundary

`AUTHENTICATED_UNCONSUMED` is the maximum contract verdict for production-valid
inputs; it is not produced by the included synthetic fixture verifier. The
fixture result remains `EXTERNAL_HOST_UNCHECKED`, `signatures_valid=false`,
non-persistent, no-authority, and incapable of establishing durable request
consumption, fit execution, or model training. Execution and
`model_training_performed` remain `NOT_ESTABLISHED`.

No real issuer or runner bytes were created, consumed, or verified. No
PostgreSQL, Linux `trade-core`, runtime service, filesystem model surface,
network, broker, or exchange was contacted. V158/V159 were not changed or
applied; V160 was not reserved or authored. No trainer/fit ran, no model or
model-artifact file,
receipt/request row, registry state, symlink, serving/promotion state, order,
risk/Cost Gate mutation, or authority was created. Production/runtime V159
remains unapplied and unrefreshed.

## G1-G9 adjudication

- G1 remains `PARTIAL`.
- G2 remains `PARTIAL_DISPOSABLE_PG_VERIFIED`.
- G3 remains `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN`.
- G4 remains `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED`.
- G5, G6, and G7 remain `FAIL`.
- G8 and G9 remain `PARTIAL_WP1_PASS`.

The Goal and WP4 remain `ACTIVE`; this source checkpoint is not a Goal
terminal.

## Next safe action

Advance only to
`WP4-V160-STYLE-ATOMIC-CONSUMPTION-DESIGN-PREAUTHORING-GATE`. That read-only
gate must freeze one fixed guarded atomic coordinator with:

- singleton admission plus request/nonce consumption;
- exact outer terminal receipt persistence;
- independent inner receipt re-verification;
- success-only binding to the complete V159 bundle;
- exact replay/conflict and trusted-time semantics;
- closed pre-fit reject, after-start failure, and unclaimed-expiry behavior;
  and
- explicit reachability and least-privilege ACL treatment for the two existing
  V159 wrappers.

This next gate is design and review only. It may not reserve, author, or apply
V160; contact PostgreSQL/runtime/issuer/runner; execute fit; create model or
registry state; serve/promote; contact a broker; place orders; change risk or
Cost Gate; or grant authority.
