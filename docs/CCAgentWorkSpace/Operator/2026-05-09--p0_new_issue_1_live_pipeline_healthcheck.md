# P0-NEW-ISSUE-1 Live Pipeline Healthcheck

Date: 2026-05-09
Status: SOURCE/TEST PARTIAL

Added `[56] live_pipeline_active`, a read-only passive healthcheck for the
current LiveDemo `auth_missing` regression. It FAILs when the live slot is
configured but signed `live/authorization.json` is missing or the live pipeline
snapshot is stale.

Current runtime fact: live slot key/secret/endpoint files are present, but
`authorization.json` is missing, so Rust refused LiveDemo at boot. No live auth
file was recreated in this checkpoint.

Verification: `helper_scripts/db/test_live_pipeline_healthcheck.py` -> 7 passed.

