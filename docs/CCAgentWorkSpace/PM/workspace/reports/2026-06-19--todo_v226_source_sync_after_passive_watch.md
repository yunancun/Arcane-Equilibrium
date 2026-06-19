# TODO v226 Source-Sync Correction After Passive Watch

Date: 2026-06-19
Owner: PM
Scope: source-sync metadata correction after TODO v225

## Result

Corrected TODO source-sync metadata after v225 passive-watch refresh.

## Evidence

- Mac `HEAD=origin/main=e8ade59a9eaaf775b2b5c9f8a304885dff4db23b`.
- Linux `trade-core` `HEAD=origin/main=e8ade59a9eaaf775b2b5c9f8a304885dff4db23b` after `git fetch` + `git merge --ff-only origin/main`.
- Linux watchdog read-only status: `engine_alive=true`, demo snapshot age `30.0s`.

## Boundary

Docs/TODO source-sync metadata only. No CI full suite, cargo, Linux build, deploy, rebuild, restart, DB write, Bybit private/signed call, credential/key/secret mutation, runtime/auth/risk/order/trading mutation, probe, archive, promotion, or active gate closure.
