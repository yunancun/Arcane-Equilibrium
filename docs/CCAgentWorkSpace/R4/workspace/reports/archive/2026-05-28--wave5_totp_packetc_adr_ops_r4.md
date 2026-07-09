# R4 Review — Wave 5 TOTP / Packet C / ADR / OPS Reality Check

**Date**: 2026-05-28  
**Mode**: PM local execution with R4-style audit; no sub-agent tool was available in this session.  
**Scope**: `P1-WAVE5-TOTP-BACKEND`, Packet C E2/E4/integration, ADR sync, and the 4 OPS residual healthcheck items.

## Verdict

Wave 5 can advance, but **cannot be honestly marked fully closed** yet.

- `P1-WAVE5-TOTP-BACKEND`: source implementation is now present and tested. Runtime remains fail-closed until operator enrolls a real secret file on `trade-core`.
- Packet C source-level E2/E4 evidence is green: `NotificationFailsafeTimeout`, `active_lock_profit_per_position`, and 7d cooling are present in `openclaw_core`; `cargo test -p openclaw_core risk_gov --lib` passed 27/27; `cargo test -p openclaw_engine --lib` passed 3468/3468 with 1 ignored.
- Packet C **integration is still open**: no engine caller currently emits `RiskEvent::NotificationFailsafeTimeout` from a 3-channel notification timeout; no exchange conditional stop sync caller is wired to `active_lock_profit_per_position`; no engine audit writer emits `notification_escalation_result='auto_escalated_to_sm04_defensive'` for that path.
- 5 ADR sync patches landed in ADR-0034 / ADR-0040 / ADR-0042 / ADR-0044 / ADR-0045 to align Autonomy Level v2 overlays and carve-outs.
- OPS `[80] pg_dump_freshness` was truly fixed at runtime by running the approved wrapper once and installing the daily 03:00 UTC cron.

## OPS Reality Check

| Check | Runtime finding | Action |
|---|---|---|
| `[48] replay_manifest_registry_growth` | `replay.experiments`: total 23, 7d 0, 24h 0, last `2026-05-11 16:35:27+02`. Replay cron files are firing, but they do not register new `replay.experiments` manifests. | Leave as real replay-runner / registry feed gap. Do not synthesize rows. |
| `[74] close_maker_reject_samples` | 7d demo attempts=17, postonly_reject=3, max_pending=0; reasons: timeout_taker 10, blank 4, postonly_reject 3. | Leave as real missing `EC_ReachMaxPendingOrders` evidence. Do not fabricate exchange reject samples. |
| `[56] live_pipeline_active` | live slot has `api_key` / `api_secret`, but `authorization.json` is missing and `bybit_endpoint` is still `demo`. | Leave operator-gated. Must renew via signed live-auth route; do not manually write authorization. |
| `[80] pg_dump_freshness` | First real dump created `/home/ncyu/pg_backups/trading_ai_2026-05-28.dump`, 4.6G, md5 `aaca62b0b45262038213f2357383bc97`; Python check 7/7 PASS; sidecar 5/5 PASS; cron installed. | Fixed. Continue monitoring next 03:00 UTC fire and later restore drill. |

## TOTP Source Evidence

- Added file-backed TOTP verifier at `program_code/exchange_connectors/bybit_connector/control_api_v1/app/autonomy_totp.py`.
- Default secret path: `$HOME/BybitOpenClaw/secrets/vault/autonomy_totp.json`; override: `OPENCLAW_AUTONOMY_TOTP_SECRET_FILE`.
- Backend is fail-closed: missing/unreadable/invalid/fingerprint mismatch returns `backend_unreachable / twofa_backend_down`; bad code returns `TOTP / twofa_fail`.
- Route now blocks Level 2 on evidence gate before TOTP, preventing a future real TOTP backend from bypassing P0-EDGE evidence.
- Tests: `python3 -m pytest -q .../test_autonomy_totp.py .../test_governance_autonomy_level_routes.py` -> 10 passed.

## ADR Sync

- ADR-0034: LAL 3/4 matrix now explicitly requires Autonomy Level overlay; Level 2 is not a bypass and venue remains manual.
- ADR-0040: venue change remains operator manual in both Level 1 and Level 2; deterministic gate evaluation may be automatic, final enable/signature is not.
- ADR-0042: M3 DEGRADED/CRITICAL freezes Autonomy Level auto paths and prevents switching into Level 2 during degraded health.
- ADR-0044: M7 `DECAY_ENFORCED` / `RETIRED` freezes auto paths; Level 2 does not override mitigation or RETIRED blocker.
- ADR-0045: M4 remains DRAFT-only under both levels; Level 2 does not promote hypotheses to live authority.

## Remaining Honest Work

1. Packet C integration: engine notification timeout scheduler -> `NotificationFailsafeTimeout` -> Defensive transition -> active lock-profit -> exchange conditional SL sync -> audit emit.
2. Runtime TOTP enrollment by operator: create secret file outside git, then restart/smoke API state to show `totp_backend_configured=true`.
3. OPS residuals `[48]`, `[74]`, `[56]`: fix only through real replay run, real exchange reject evidence, and signed live authorization renewal.
4. OPS restore drill remains required after dump evidence; dump freshness alone is not DR closure.

