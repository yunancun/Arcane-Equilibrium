# 2026-06-22 Demo Order-To-Fill Gap Touchability Audit

## Summary

v414 adds a read-only `demo_order_to_fill_gap_audit_v1` artifact that explains why recent Demo orders are not filling. It is the next drilldown after v413's `DEMO_ORDER_FLOW_PRESENT_NO_FILLS` data-flow monitor status.

The runtime result is concrete: in the last 48h, Demo produced 6 PostOnly buy orders, 0 fills, and every reviewed order was a deep passive limit that never touched BBO. The current blocker is not silent drop and not a broken fill recorder. It is order touchability / execution realism.

## Source Changes

- Added `helper_scripts/db/audit/demo_order_to_fill_gap_audit.py`.
- Added focused tests in `helper_scripts/db/audit/test_demo_order_to_fill_gap_audit.py`.
- Updated `helper_scripts/SCRIPT_INDEX.md`.

The audit reads only:

- `trading.orders`
- `trading.intents`
- `trading.order_state_changes`
- `trading.fills`
- `market.ob_top`

It infers `effective_limit_price` from `orders.price`, `orders.details.limit_price`, `intents.details.limit_price`, or `intents.price`, then compares the effective limit with placement/future BBO. JSON numeric fields use defensive regex casts so malformed metadata fails closed as missing price instead of crashing the whole artifact.

## Runtime Evidence

Linux artifact-only smoke:

- artifact JSON: `/tmp/openclaw/demo_order_to_fill_gap/demo_order_to_fill_gap_smoke.json`
- artifact Markdown: `/tmp/openclaw/demo_order_to_fill_gap/demo_order_to_fill_gap_smoke.md`
- generated: `2026-06-22T17:37:09+00:00`
- JSON sha256: `e4eeee80ebc8fcbfe01433d9d7b67dff3bef4665d952b3f456669c6f1934078c`
- Markdown sha256: `1411cf9ea9fb6feb7286881d8075dcfc49bbd5abdaaaad89c8f59924c96be81a`

Summary:

- status: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- reviewed orders: `6`
- fills: `0`
- PostOnly orders: `6`
- `orders.price` missing: `6`
- effective prices inferred from intents: `6`
- BBO touched without fill: `0`
- deep passive no-touch orders: `6`
- no BBO coverage orders: `0`

Order classifications:

| Date | Symbol | Class | Effective limit source | Best touch gap |
|---|---|---|---|---:|
| 2026-06-22 | BNBUSDT Buy | `WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH` | `intents.details.limit_price` | `1441.7507bp` |
| 2026-06-22 | XRPUSDT Buy | `WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH` | `intents.details.limit_price` | `1310.2208bp` |
| 2026-06-22 | ETCUSDT Buy | `WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH` | `intents.details.limit_price` | `1265.6141bp` |
| 2026-06-21 | BNBUSDT Buy | `DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT` | `intents.details.limit_price` | `1530.6074bp` |
| 2026-06-21 | XRPUSDT Buy | `DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT` | `intents.details.limit_price` | `1388.4773bp` |
| 2026-06-21 | SUIUSDT Buy | `DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT` | `intents.details.limit_price` | `1156.7403bp` |

## PM Read

Fact: the order/fill path is not proven broken by this evidence. The BBO never touched the effective order limits, and prior orders self-cancelled after the day timeout.

Inference: the Demo system is accumulating data, but the live Demo order sample is low-value for learning fills because the current `flash_dip_buy` placement is too deep to generate fill-backed execution evidence.

Profitability implication: lowering the global Cost Gate would not solve this specific blocker. The system needs a touchability-aware bounded Demo probe design: smaller, operator-authorized, side-cell/horizon-specific orders that can realistically touch while preserving survival constraints and explicit stop conditions.

## Profit Path Update

The near-term engineering path to profit is now sharper:

1. Preserve the global Cost Gate.
2. Use blocked-signal learning to select side-cell/horizon candidates with multi-horizon edge evidence.
3. Add touchability constraints before any bounded Demo probe, so a probe is not another far-away passive order that produces no fill evidence.
4. Require matched-control result review and execution-realism review to measure whether realized Demo fills capture the blocked-signal edge.
5. Only after fill-backed edge capture exists should operator review any Cost Gate adjustment or promotion path.

This keeps the Interface small and deep: one audit answers whether no-fill means broken fill path, missing price metadata, missing BBO coverage, or intentionally unreachable passive pricing. That gives the learning loop better leverage and better locality for execution-realism fixes.

## Verification

- Mac: `python3 -m pytest -q helper_scripts/db/audit/test_demo_order_to_fill_gap_audit.py` = `8 passed`.
- Mac: related demo audit suite = `26 passed`.
- Mac: py_compile passed.
- Mac: `git diff --check` passed.
- Source commits: `6ced51e4`, `2a37deb9`, both pushed with `[skip ci]`.
- Linux source fast-forwarded to `2a37deb9`.
- Linux: related demo audit suite = `26 passed`.
- Linux: py_compile passed.
- Linux: `git diff --check` passed.
- Linux: artifact-only read-only PG smoke passed after loading the normal runtime PG env file.

## Boundary

Source/test/docs + Linux source sync + read-only PG SELECT + `/tmp/openclaw` artifact-only smoke only. No CI, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install, no writer/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
