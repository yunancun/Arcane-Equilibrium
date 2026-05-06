# Console Navigation + Edge Gate Tab

Date: 2026-05-06
Status: source implemented and targeted tests green

Implemented:

- `/console` top tabs are grouped into `核心`, `交易`, `策略/Edge`, `治理`, `智能`, `运维`.
- Added standalone `Pre-Live Gates` tab.
- New tab shows strategy pass/warn/fail/crisis, active negative cells, [33]/[38]/[40] gate trends, Live readiness, and global healthcheck PASS/WARN/FAIL.
- Existing Live embedded edge-gate section remains available.

Verification:

- Edge/static targeted pytest: 46 passed.
- Backend py_compile passed.
- Inline JS syntax check passed.
- Diff whitespace check passed.

Boundary: no rebuild/restart/deploy action, no DB write, no trading/risk/live-auth change.
