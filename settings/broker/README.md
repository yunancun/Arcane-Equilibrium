# Broker Settings

This directory stores broker capability contracts and default-off runtime posture. It must not contain API keys, account ids, cookies, tokens, local IBKR session details, or live credential paths.

`ibkr_external_surface_gate.toml` is a Phase 2 source template only. It is intentionally `BLOCKED` and cannot authorize IBKR contact until an immutable PASS artifact is produced under the ADR-0048 gate process.

`ibkr_phase2_policies.toml` records source policy prerequisites for redaction, rate limiting, audit events, paper attestation, and Python no-write guard. It is not a PASS artifact and does not authorize IBKR contact.

`ibkr_phase2_gate_artifact.template.toml` records the immutable gate artifact shape, including empty secret-slot and API topology evidence sections. It is intentionally empty/BLOCKED and cannot authorize IBKR contact.

`ibkr_phase2_runtime_contracts.toml` records the source evidence shape for secret-slot posture and API session topology. It is intentionally incomplete and cannot authorize IBKR contact.

`ibkr_feature_flag_secret_auth_matrix.toml` records the default-blocked feature-flag, secret, and scoped-authorization matrix shape. It does not authorize IBKR contact or paper orders.

`ibkr_paper_order_lifecycle.toml` records the default-blocked paper order lifecycle and append-only event log shape. It does not authorize connector creation or paper orders.

`stock_etf_phase3_evidence_contracts.toml` records the default-blocked market-data provenance, DQ, frozen-input, and evidence-clock checker shape. It does not start the evidence clock.

`stock_etf_release_packet.template.toml` records the default-blocked Phase 5 release packet shape. It is secret-free and does not authorize IBKR contact, paper orders, GUI lane authority, tiny-live, or live.

`stock_etf_tiny_live_adr_eligibility.template.toml` records the default-blocked future ADR discussion eligibility shape. It is secret-free and cannot authorize IBKR tiny-live or live even if a future paper/shadow scorecard is positive.
