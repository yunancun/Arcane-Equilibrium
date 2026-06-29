# Broker Settings

This directory stores broker capability contracts and default-off runtime posture. It must not contain API keys, account ids, cookies, tokens, local IBKR session details, or live credential paths.

`ibkr_external_surface_gate.toml` is a Phase 2 source template only. It is intentionally `BLOCKED` and cannot authorize IBKR contact until an immutable PASS artifact is produced under the ADR-0048 gate process.
