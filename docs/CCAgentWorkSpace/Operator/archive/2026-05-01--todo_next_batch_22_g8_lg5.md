# TODO next batch: [22], G8-05, LG-5

Date: 2026-05-01
Status: Complete

## Completed

- `[22]` healthcheck calibrated: maker working orders / rejected-only risk gates now WARN instead of false FAIL.
- G8-05 AI Cost ROI Monitor added to AI tab.
- LG-5 constrained autonomous live RFC landed.

## Verification

- F7 healthcheck tests: 43/0.
- tab-ai inline JS syntax: 2 scripts checked.
- Linux wrapper: SUMMARY WARN exit 0 at 2026-05-01 22:36 CEST. `[22]` is now WARN with maker-working context; `[16]` is a transient 11.3min strategist-cycle WARN inside the 30min backoff window.

## Boundary

No restart/rebuild, DB write, live auth change, risk/strategy config change, SIGHUP, HTTPS deploy, or true live action was performed.
