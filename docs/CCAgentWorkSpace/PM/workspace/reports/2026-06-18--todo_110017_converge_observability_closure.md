# TODO v176 110017 Convergence Observability Closure

Date: 2026-06-18
Role: PM
Scope: TODO active-queue hygiene backed by read-only DB/source verification

## Decision

Archive `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` from `TODO.md` §5.

The row asked for deployment verification of the `exchange_zero_close_converge` audit row plus the approximately 63 second stop-timing check. Both are now verified from production DB read-only evidence.

## Evidence

Linux production DB, read-only:

- `trading.order_state_changes.reason LIKE 'exchange_zero_close_converge:%'`
  - rows: `4`
  - span: `2026-06-03 17:36:20.263+02` to `2026-06-06 07:27:25.119+02`
  - all rows are `Working -> Cancelled` with `110017` convergence reason

Rows:

| ts | order_id | symbol | side | strategy | reason |
|---|---|---|---|---|---|
| `2026-06-03 17:36:20.263+02` | `oc_risk_dm_1780500980096_18` | `ARBUSDT` | `Sell` | `risk_close:phys_lock_gate4_giveback` | `exchange_zero_close_converge:110017; removed_position=true` |
| `2026-06-05 02:00:34.259+02` | `oc_risk_dm_1780617634096_7` | `ETHUSDT` | `Sell` | `risk_close:phys_lock_gate4_giveback` | `exchange_zero_close_converge:110017; removed_position=true` |
| `2026-06-05 18:51:04.153+02` | `oc_risk_dm_1780678263986_74` | `OPUSDT` | `Buy` | `risk_close:phys_lock_gate4_giveback` | `exchange_zero_close_converge:110017; removed_position=true` |
| `2026-06-06 07:27:25.119+02` | `oc_ipc_close_dm_1780723644651_18` | `AVAXUSDT` | `Sell` | `risk_close:ipc_close_symbol` | `exchange_zero_close_converge:110017; removed_position=false` |

`trading.orders` confirms these are demo qty=0 close-form orders. The `removed_position=false` row is a valid already-flat/no-op convergence outcome, not an absence of the audit row.

Stop-timing check:

- same symbol+strategy follow-up orders within `63 seconds`: `0` for all 4 rows
- same symbol+strategy follow-up orders within `5 minutes`: `0` for all 4 rows
- next same symbol+strategy order:
  - ARBUSDT: `2026-06-14 21:20:30.11+02`
  - ETHUSDT: `2026-06-09 15:20:30.14+02`
  - OPUSDT: `2026-06-08 00:15:31.031+02`
  - AVAXUSDT: none observed

## Source Nuance

Current source has two related observability paths:

- D1 immediate close convergence writes `trading.order_state_changes.reason='exchange_zero_close_converge:110017; ...'`.
- D2 reconciler ghost dispatch source audit writes `observability.engine_events.event_type='reconcile_ghost_converge'`.

Production currently has many legacy/current `observability.engine_events.event_type='reconcile_ghost'` rows, but no `reconcile_ghost_converge` rows in the checked window. That does not block this archive because the active row's acceptance was the D1 `exchange_zero_close_converge` audit row plus stop-timing. D2 semantic cleanup remains tracked by separate active rows.

## Still Active

Do not infer broader 110017 closure from this archive:

- `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` remains active with the reconciler batch.
- `P3-110017-BB-DOC-FOLLOWUPS` remains active for the 110017 dictionary and 110009 doc ambiguity.

## Boundary

Read-only DB/source verification plus docs/TODO hygiene only.

No CI, deploy, rebuild, restart, production source mutation, runtime mutation, DB write, auth/risk/order/trading mutation.
