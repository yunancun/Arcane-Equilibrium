# 2026-07-01 — Stock/ETF Dynamic Checkpoint Trace Guard

## Scope

PM replaced the hand-maintained Stock/ETF checkpoint trace title list with a dynamic source-only
guard derived from the main IBKR development arrangement.

This is not a runtime behavior change, not IBKR contact, not connector runtime wiring, not secret
access, not DB migration apply, not paper order routing, and not a Bybit behavior change. It only
keeps the PM main plan and Operator round3 summary traceable as the checkpoint list grows.

## Guard Updated

- `tests/structure/test_docs_readme_index_static.py`

The guard now:

- parses all PM session checkpoint titles from
  `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`;
- requires the dynamic title list to remain large enough to cover the current Stock/ETF checkpoint
  history;
- requires every parsed checkpoint title to be searchable in the Operator round3 summary;
- avoids adding a new hand-maintained title tuple for each future checkpoint.

## Trace Repair

PM added exact `Trace title:` aliases for three historical Operator updates whose content already
existed but whose headings did not exactly match the main plan checkpoint titles:

- `Stock/ETF GUI split`
- `Paper Lifecycle State-Machine Contract Hardening`
- `Paper Status Lifecycle Surface Hardening`

## Verification

- Dynamic docs trace guard py_compile: PASS.
- Dynamic docs trace pytest: `2 passed, 5 deselected`.
- Full docs README/index structure pytest: known pre-existing docs README index drift remains
  (4 failures outside the Stock/ETF trace guard).
- Diff check: PASS.

## Boundary

No production code, endpoint, IPC method, connector, SDK import, socket/HTTP path, secret access,
DB/evidence writer, paper order route, tiny-live/live authorization, Linux runtime sync/restart, or
Bybit live/demo execution behavior changed.
