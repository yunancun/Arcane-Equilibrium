# Operator Mirror — WP4 Durable Fit-Attestation Schema Source Checkpoint

Status: `DONE_SOURCE_ACCEPTED_DURABLE_FIT_ATTESTATION_SCHEMA` at
`27bfe34b608b732071205c351dd1aa3fdd7d2283`, published on
`origin/agent/alr-wp4-contracts` atop `origin/main` `b83ddee0`.

V159 now contractually prevents the direct V158 unattested-result persistence
path. It requires an exact externally authenticated fit receipt, derives
immutable attestation and durable identities inside PostgreSQL, and binds only
an atomic run/q10-q50-q90/`NOT_SERVING` bundle with strict expiry/replay,
concurrency, least-privilege, and false/zero-authority behavior. V158 remains
byte-identical.

Source/static verification passed `232/232`; V158+V159 passed `269/269`; the
governed Rust schema harness passed `7/7`. E2/CC/E3/MIT final P0/P1/P2 are
`0/0/0`, and E4 returned `SOURCE_ONLY_PASS` with one effect concern. A missing
V006 `trading_ai` CI precondition was caught with four RED checks and fixed to
four GREEN checks.

The effect concern is material: the isolated Cargo home fetched public
crates.io dependencies. An offline retry failed before tests because that home
had no cache, so zero-network/offline reproducibility is not proven. Beyond the
expected GitHub source fetch/push, no private trading/runtime or broker
endpoint, PostgreSQL, Linux/runtime service, or trading runtime was contacted.

This is still source acceptance, not G3/G4 runtime proof. V159 was not applied;
the functional/concurrency probes did not run; no external real receipt,
production caller, trainer/fit, model/file, durable row, registry, serving,
promotion, order, or authority effect occurred. The Goal remains `ACTIVE` and
G1-G9 are incomplete.

Next is
`WP4-DURABLE-FIT-ATTESTATION-DISPOSABLE-PG-VERIFICATION-GATE`: governed,
isolated PostgreSQL 16/Timescale execution of the functional and concurrency
probes only. It does not authorize runtime/production apply, fit, model files,
serving/promotion, exchange, or trading. A real external issuer receipt and
real fit remain a separate later gate.
