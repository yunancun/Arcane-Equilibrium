# 2026-06-24 -- Profit Evidence Quality Operator Checkpoint

STATUS: BLOCKED_BY_OPERATOR_ACTION

Scope: `P0-PROFIT-EVIDENCE-QUALITY` under Profit-first Demo-learning Autonomy
Improvement Loop / Aggressive Alpha Expansion Mode.

Boundary: read-only source, artifact, PG SELECT, and Bybit demo private
read-only inventory. No order/cancel/modify, no PG write, no crontab edit, no
service restart, no Rust writer enablement, no live/probe/order authority, and
no Cost Gate lowering.

## session_loop_state

| field | value |
|---|---|
| session_goal | Continue the profit-first demo-learning autonomy loop while preserving survival, Guardian/risk gates, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| active_blocker_id | `P0-PROFIT-EVIDENCE-QUALITY` |
| blocker_goal | Inventory deep Working order overhang, classify stale/deep/open orders, root-cause unattributed fills, and define proof-exclusion rule. |
| profit_relevance | Clean order/fill lineage is mandatory before any bounded Demo candidate can prove risk-adjusted net PnL after fees/slippage. |
| completed_blockers | none in this loop |
| blocked_blockers | `P0-PROFIT-EVIDENCE-QUALITY` blocked by operator action |
| previous_report_paths | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-pm-current-state-report.md`, BB/MIT/E3/FA/QC/PA 2026-06-24 demo-learning autonomy reports |
| source_head | Mac/origin `a7d84862`; Linux runtime checkout/origin `c88deea7` |
| runtime_timestamp | `2026-06-24T01:53:48Z` from `trade-core` |
| pg_snapshot_timestamp | `2026-06-24 03:53:48.785827+02` |
| artifact_mtimes | Cost Gate latest artifacts refreshed through `2026-06-24T03:45:06+02`; demo order-to-fill latest `2026-06-24T03:30:01+02`; stack health latest `2026-06-24T03:32:01+02` |
| operator_action_required | yes: any Bybit cancel/modify/close, PG reconciliation/backfill, cron edit, service restart, or runtime mutation requires explicit authorization |
| new_evidence_delta_required | yes: source/runtime/artifact/PG/exchange delta after prior 03:19 audit |
| new_evidence_delta_found | yes: complete Bybit paged open-order inventory found 35 exchange open orders and one SOL open position |
| acceptance_criteria | classify exchange/DB overhang; root-cause unattributed fills; exclude unattributed fills from proof; stop before exchange write action |
| next_blocker_id | `P0-PROFIT-CANDIDATE-SELECTION` only after operator resolves/quarantines overhang and lineage blocker |

## Evidence Delta

- Previous PM audit saw 25 same-day deep `Working` orders and unattributed
  SOL/ETH fills.
- Current Mac source is `a7d84862`, while Linux runtime remains clean at
  `c88deea7`; the delta is governance/TODO state, not a runtime engine update.
- Current Cost Gate/artifact lane is fresh:
  - blocked-outcome review `2026-06-24T01:29:55Z`
  - false-negative packet `2026-06-24T01:29:55Z`
  - bounded operator authorization `decision=defer`
  - bounded result review `NO_PROBE_OUTCOMES_RECORDED`
  - profitability scorecard `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
- Complete paged Bybit demo open-order inventory found `35` exchange open
  orders:
  - `34` `New` PostOnly buy orders, all deep open vs latest mark by about
    `458.29` to `1785.22` bps, total notional about `8370.74` USDT.
  - `25` same-day PostOnly orders, about `2.0h` old, notional about
    `6204.80` USDT.
  - `9` stale `>24h` PostOnly orders, about `26.0h` to `103.52h` old,
    notional about `2165.94` USDT.
  - `1` SOLUSDT `Untriggered` Sell Market IOC conditional order with no
    `orderLinkId`.
- Bybit demo position inventory found one open position:
  - `SOLUSDT` Buy size `4`, avg `69.8`, mark about `70.15`, position value
    about `279.2` USDT.
- Local `/tmp/openclaw/demo_state.json` reports `positions []`, so SOL is an
  exchange/local position drift, consistent with the SOL unattributed fill.
- PG 7d lifecycle rows still show `79` demo `Working` rows. This is a
  reconstructability issue separate from exchange-open exposure.

## Unattributed Fill Root Cause

Facts:

- SOL dispatch log mapped exchange order id
  `91a47a7f-81f3-497f-ab26-542b7a094b53` to local orderLinkId
  `oc_dm_1782261306651_1`.
- ETH dispatch log mapped exchange order id
  `4cf5dd4a-f97c-4d2a-8d29-c92c12a565b3` to local orderLinkId
  `oc_dm_1782261306802_3`.
- PG fills then recorded SOL/ETH buys under Bybit UUID order ids with
  `strategy_name='unattributed:bybit_auto'`, while the local `oc_dm_*` orders
  stayed `Working`.
- Source matching in `rust/openclaw_engine/src/event_consumer/loop_exchange.rs`
  first uses `order_id_to_link`, then a symbol+side fallback only if exactly one
  eligible pending order exists. If the fill arrives before an order update or
  the candidate set is ambiguous, it deliberately emits an unattributed audit
  fill. Existing test
  `test_ambiguous_fill_before_order_update_emits_unattributed_fill` pins this
  fail-closed behavior.

Inference:

- The SOL/ETH opens are not unknown Bybit actions; dispatch logs prove they
  were OpenClaw demo orders. They became unattributed because the fill path did
  not have a unique, active local mapping at fill time.
- The fail-closed unattributed behavior is audit-safe but not
  promotion-grade. It preserved the event instead of silently dropping it, but
  it did not produce a reconstructable candidate/order/fill lineage.

## Proof-Exclusion Rule

Effective immediately for this loop:

- Any fill with `strategy_name LIKE 'unattributed:%'` is excluded forever from
  promotion proof, Cost Gate proof, bounded-probe success proof, and
  risk-adjusted net PnL proof.
- Any fill that lacks candidate id, OpenClaw order id/orderLinkId, exchange
  order id mapping, intent, risk verdict, fee/slippage, close state, matched
  control, and source/artifact linkage is excluded from proof even if realized
  PnL is positive.
- Unattributed fills may be used only as audit/reconciliation evidence and as a
  blocker signal for future fill-lineage source work.
- `flash_dip_buy` demo fills remain ordinary demo evidence and cannot be
  counted as bounded Cost Gate probe proof unless they match an explicitly
  authorized bounded-probe contract.

## Operator Action Required

PM cannot safely proceed to bounded candidate selection while exchange/local
state is this dirty.

Explicit operator authorization is required for any of these possible actions:

1. Cancel some or all of the `34` deep PostOnly Bybit demo open orders.
2. Cancel/replace/keep the SOLUSDT untriggered conditional order.
3. Close, keep, or otherwise manage the SOLUSDT demo position.
4. Write PG reconciliation/backfill rows for stale local lifecycle state.
5. Restart/redeploy/edit crons/enable writers to repair runtime state.

Until that authorization and resulting evidence exists, the max safe next
action is source-only design/implementation for future fill attribution and
proof-exclusion guards. No exchange write or runtime mutation is authorized by
this report.

## Aggressive Profit Hypotheses

1. `false_negative_grid_short_packet`
   - why_it_might_make_money: ranked false-negative side-cells show large
     blocked markout cushions after current fee assumptions, especially
     grid-trading sell cells.
   - fastest_safe_test: source-only review packet selecting one exact side-cell
     after overhang cleanup; no probe authority.
   - required_data: clean candidate id, matched blocked controls, current fee,
     fillability/touchability, and no unattributed fills.
   - failure_condition: selected side-cell lacks candidate-matched fills,
     matched controls, or loses net edge after fees/slippage.
   - authority_required: operator approval only if moving from review packet to
     bounded Demo probe.
   - max_safe_next_action: source-only candidate review packet after this
     blocker is resolved.
   - scores: expected_net_pnl_upside 8, evidence_strength 6,
     execution_realism 3, cost_after_fees 6, time_to_test 5,
     risk_to_account 3, risk_to_governance 2, autonomy_value 8.
2. `mm_current_fee_repeat_window`
   - why_it_might_make_money: SOXLUSDT maker cell already clears current fee in
     one sample-gated window, so repeat/OOS confirmation could produce a low
     Cost Gate path without global threshold changes.
   - fastest_safe_test: artifact-only independent-window replay/accumulation
     for the same candidate key.
   - required_data: repeated windows, OOS/walk-forward, maker execution
     realism, queue/fill attribution, fee tier assumptions.
   - failure_condition: no repeated positive key, maker fills not realistic, or
     net cushion disappears after fees/slippage.
   - authority_required: none for replay; operator approval for any bounded
     Demo probe.
   - max_safe_next_action: source/artifact replay only.
   - scores: expected_net_pnl_upside 6, evidence_strength 4,
     execution_realism 4, cost_after_fees 5, time_to_test 4,
     risk_to_account 2, risk_to_governance 2, autonomy_value 7.
3. `near_touch_lineage_repair`
   - why_it_might_make_money: 10 bps near-touch flash_dip orders can fill, but
     profit evidence is lost when fills become unattributed; fixing lineage
     converts existing touchability into usable proof material.
   - fastest_safe_test: source-only design/tests for exchange-order-id to
     orderLinkId fallback and proof-exclusion guards; no PG backfill.
   - required_data: dispatch mapping, order updates, fills, candidate ids,
     existing pending-order ambiguity tests.
   - failure_condition: fallback risks misattribution under ambiguous pending
     orders or cannot preserve fail-closed behavior.
   - authority_required: none for source design/tests; operator approval for
     deploy/restart/PG backfill/exchange cleanup.
   - max_safe_next_action: PA/E1/E2/E4 source-only fix plan.
   - scores: expected_net_pnl_upside 5, evidence_strength 7,
     execution_realism 7, cost_after_fees 4, time_to_test 6,
     risk_to_account 1, risk_to_governance 2, autonomy_value 9.

PM SIGN-OFF: BLOCKED_BY_OPERATOR_ACTION.
