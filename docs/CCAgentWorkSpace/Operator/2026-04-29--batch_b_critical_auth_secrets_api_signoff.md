# Batch B Operator Brief

Date: 2026-04-29 CEST

Batch B is fixed in the working tree, not deployed.

Closed findings: `DAPI-001..006`, `RC-003`, `SC-001..007`.

Key operator-impacting changes:

- High-risk POST routes now require authenticated Operator plus route-specific scope.
- Grafana no longer ships repo-known credentials and binds to loopback by default.
- API/Grafana/runtime scripts require real secrets supplied externally.
- Engine/API can read DB URL and IPC HMAC secret from `OPENCLAW_DATABASE_URL_FILE` / `OPENCLAW_IPC_SECRET_FILE`.
- Token/cookie/dashboard/model/DB/proxy exposure paths are hardened.

Verification:

- Python targeted tests: 47 passed.
- Shell syntax, plist lint, docker-compose config, Rust `cargo check`, and static secret sweep passed.

No deploy/restart was performed.
