# P2 Maintenance Hygiene Closure — 2026-05-16

Scope: `P2-H0-DISPLAY-LABEL-1`, `P2-START-LOCAL-HELPER`, `P2-PA-CALLPATH-GREP-RULE`, `P2-CROSSTAB-I18N`, plus TODO correction for already-implemented `P2-PORTFOLIO-RESTING-58-HEALTHCHECK`.

## Changes

- H0 GUI status endpoint now returns `display_only=true`, explicitly marking the Python/FastAPI surface as read/display-only rather than execution authority.
- `control_api_v1/start_local.sh` and `scripts/beta_quickstart.sh` now source `helper_scripts/lib/api_bind_host.sh` and bind via `resolve_openclaw_api_bind_host()`.
- PA / E2 review rules now require P0/P1 leak, look-ahead, selection-bias, or stale findings to include production caller call-path grep; missing grep means the finding is unproven, not a blocker.
- Cross-tab static GUI files were string-cleaned to Traditional Chinese for the named i18n residual class; the ticket strings `实盘`, `平仓`, and `请检查` now grep to zero in the listed files.
- TODO now records that `P2-PORTFOLIO-RESTING-58-HEALTHCHECK` was already implemented as `[68] portfolio_resting_exposure_lineage` because `[58]` was occupied.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_routes_coverage.py::TestGetH0GateStatusFreshnessFields -q` -> 3 passed.
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py::test_w_audit_2_api_launches_default_to_tailnet_or_loopback_bind program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py::test_api_bind_host_helper_resolves_tailscale_and_rejects_all_interfaces -q` -> 2 passed.
- `bash -n program_code/exchange_connectors/bybit_connector/control_api_v1/start_local.sh program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/beta_quickstart.sh` -> passed.
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app.js && node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/risk-tab.js && node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js` -> passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_extended_routes.py` -> passed.
- `rg -n "实盘|平仓|请检查" <listed static cross-tab files>` -> 0 matches.
- `rg -n "P2-PA-CALLPATH-GREP-RULE|production caller call-path grep|IndicatorEngine.*production caller|P0/P1 leak/bias" .claude/skills/pr-adversarial-review/SKILL.md .claude/agents/PA.md -S` -> expected rule hits.
- `git diff --check -- <touched files>` -> passed.

## Boundaries

No runtime, DB, auth, strategy, risk-config, mode, or engine restart action was performed. This is source/test/docs only. Existing unrelated dirty files from the WP03 healthcheck and other parallel work were left untouched and should not be staged into this checkpoint.
