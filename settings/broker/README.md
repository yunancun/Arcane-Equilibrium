# Broker Settings

This directory stores broker capability contracts and default-off runtime posture. It must not contain API keys, account ids, cookies, tokens, local IBKR session details, or live credential paths.

`ibkr_external_surface_gate.toml` is a Phase 2 source template only. It is intentionally `BLOCKED` and cannot authorize IBKR contact until an immutable PASS artifact is produced under the ADR-0048 gate process.

`ibkr_phase2_policies.toml` records source policy prerequisites for redaction, rate limiting, audit events, paper attestation, and Python no-write guard. It is not a PASS artifact and does not authorize IBKR contact.

`ibkr_phase2_gate_artifact.template.toml` records the immutable gate artifact shape, including empty secret-slot and API topology evidence sections. It is intentionally empty/BLOCKED and cannot authorize IBKR contact.

`ibkr_phase2_runtime_contracts.toml` records the source evidence shape for secret-slot posture and API session topology. It is intentionally incomplete and cannot authorize IBKR contact.

`ibkr_feature_flag_secret_auth_matrix.toml` records the default-blocked feature-flag, secret, and scoped-authorization matrix shape. It does not authorize IBKR contact or paper orders.
