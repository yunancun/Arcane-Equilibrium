# Demo Resting Exposure Reconciliation Inventory

Timestamp: 2026-06-26T00:57Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESTING-EXPOSURE-RECONCILIATION-E3-BB-REVIEW`

## Decision

`DONE_WITH_CONCERNS`.

本輪只完成 read-only inventory / docs / TODO checkpoint。Demo resting
exposure 尚未清乾淨；exchange truth 仍未驗證；不得由此進入 restart、
adapter enablement、bounded probe、order path、Cost Gate change 或 promotion。

## Session State

- `/tmp/openclaw/session_loop_state_20260626T004943Z_demo_resting_exposure_reconciliation.json`

## Read-Only Evidence

Runtime posture:

- Linux checkout clean at `d2cd70d092916194043e112eeb402fb92bacb699`.
- Crontab expected-head SHA occurrence count: `d2cd70d0=11`, old `e0c2a0e1=0`.
- `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count `0`.
- `OPENCLAW_ALLOW_MAINNET=1` count `0`.
- Running engine/API were not restarted or rebuilt in this tranche.

Passive healthcheck:

- Timestamp: `2026-06-26T00:52:06Z`.
- Summary: `FAIL`.
- Relevant `[68] portfolio_resting_exposure_lineage`: demo 24h view
  `working_n=6`, resting about `691 USDT` (`L684/S7`), divergence critical.
- Other relevant failures remain `[74] close_maker_reject_samples` and `[82] lease_ipc_soak_window`.

Direct PG inventory:

- 72h demo `Working` orders at `2026-06-26T00:55Z`: `30`.
- Composition: `29` `flash_dip_buy` Limit/PostOnly Buy orders, total notional
  `7264.930000 USDT`; `1` `risk_close:phys_lock_gate4_giveback` Market Sell
  row with missing price / zero notional.
- Oldest working order: `2026-06-24 02:00:00.001+02`.
- Newest working order: `2026-06-26 02:28:22.834+02`.
- 24h direct view: `3` working, `2` priced, notional `483.640000 USDT`.
- The 24h healthcheck count and 72h direct count differ because they use
  different windows and exposure semantics; neither proves exchange truth.

Fill / attribution quality:

- 72h demo fills: `72`.
- `unattributed_order_id=0`.
- `unattributed_context_id=0`.
- Existing read-only audit script generated `2026-06-26T00:54:44Z` with
  `FILL_FLOW_PRESENT`, top 40 reviewed orders, `fill_rows=28`,
  `bbo_touched_no_fill_orders=6`, `no_touch_orders=3`,
  `no_bbo_coverage_orders=2`.

## E3 / BB Verdict

E3: `DONE_WITH_CONCERNS`.

- PM may close this blocker for read-only inventory + docs/TODO only.
- Must keep Bybit private read, cancel/modify/order-affecting actions, adapter
  enablement, restart/rebuild, PG write, env/crontab mutation, Cost Gate
  lowering, probe/order/live authority blocked.

BB: `DONE_WITH_CONCERNS`.

- PM may close only the read-only tranche.
- Next safe checkpoint is a separate `PM -> E3 -> BB -> PM` review for Bybit
  demo private read-only open-order inventory.
- If stale exchange-open orders exist, stop and create a separate E3/BB-reviewed
  cancel/modify plan. No cancel/modify/order action belongs in the read
  checkpoint.

## Proof Exclusions

- `flash_dip_buy` rows/fills are flow or touchability evidence only; they are
  not profit, promotion, bounded-probe, or Cost Gate proof.
- Cleanup / risk-close rows are risk-reduction evidence only.
- PG `Working` rows alone are not Bybit exchange truth.
- The audit status `FILL_FLOW_PRESENT` is not resting-exposure reconciliation
  proof.
- Unattributed fills, if they appear in future windows, must never count toward
  bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL.

## Boundary

No Bybit call, no private endpoint read, no order/cancel/modify, no PG write,
no service restart/rebuild, no crontab/env mutation, no adapter/writer
enablement, no Cost Gate lowering, no live/mainnet action, no probe/order
authority, and no promotion proof occurred.

## Next Blocker

`P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW`

Goal: perform a separately reviewed Bybit demo private read-only open-order
inventory and reconcile exchange-open orders against PG `Working`,
fills/attribution, and healthcheck [68]. Stop before any cancel/modify/order
action and create a separate plan if cleanup is needed.
