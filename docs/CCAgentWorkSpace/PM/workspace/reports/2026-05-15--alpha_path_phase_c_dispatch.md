# Alpha Path Dispatch — A4-C + W-AUDIT-8a Phase C/D + 8c/8b

Date: 2026-05-15  
Scope: PM/PA dispatch after post-rebuild three-side sync. No runtime mutation, no DB write, no auth change, no paper/demo launch.

## Current Runtime Gate

- Source sync: Mac/origin/Linux are on docs head `e8944cf4`.
- Runtime rebuild code line: `7b33ab2e`; later `e8944cf4` is docs-only.
- True-live remains blocked because signed live auth is absent.
- Narrow post-rebuild probe at `2026-05-15T17:29:47Z`:
  - `[27] intents_counter_freeze` PASS, but still under fresh-restart grace (`engine restarted 13.0m ago`; live_demo baseline pending).
  - `[66] panel_freshness` PASS (`funding=PASS(30s)`, `oi_delta=PASS(30s)`).
  - `[67] feature_baseline_readiness` PASS (`646` active rows / `19` symbols / `34/34` feature names).

`P1-INTENT-FREEZE-27` therefore stays POST-GRACE PENDING. Do not use this as demo-canary clearance yet.

## Alpha Verdict

1. A4-C BTC->Alt Lead-Lag remains GATE-RED. Step 5b and the OI-confirmed 5m feasibility probe are diagnostic only and cannot authorize Stage 1 demo.
2. W-AUDIT-8a Phase B is healthy enough to be used as foundation evidence: funding/OI panels are fresh and `[66]` PASSes.
3. The next engineering start should be W-AUDIT-8a Phase C0, not A4-C demo preparation.

## Liquidation Phase C Inventory

Confirmed facts:

- `market.liquidations` already exists from V002 with 5 columns; current production rows are `0`, latest `none`.
- The table is reserved/dormant, not an active writer target.
- `multi_interval_topics.rs` explicitly excludes `liquidation.*`, `price-limit.*`, and `adl-notice.*` because old Bybit topics returned `"handler not found"` and poisoned the WS connection.
- Legacy parser/dispatch code for `liquidation.{symbol}` still exists, but the production subscription path does not emit that topic and `MarketDataMsg::Liquidation` / writer path were removed.

Dispatch correction:

- Phase C must be split:
  - C0: inventory + BB standalone probe spec + fail-closed contract, with production subscriptions unchanged.
  - C1: only after BB proves a safe topic, restore parser/writer/pulse and enable freshness healthcheck.
- Do not add `allLiquidation` or any liquidation topic to the main WS subscription list until C1.

## Naming Collision

Current TODO canonical IDs:

- `W-AUDIT-8b`: A4-A Funding Skew Directional strategy.
- `W-AUDIT-8c`: A4-B Liquidation Cluster Reaction strategy.
- `W-AUDIT-8d`: A4-C BTC->Alt Lead-Lag strategy.
- `W-AUDIT-8e`: R-2 Strategist Alpha Source Orchestrator.
- `W-AUDIT-8f`: R-3 Hypothesis Pipeline.

Existing execution-plan files named `w_audit_8b_strategist_alpha_orchestrator_spec.md` and `w_audit_8c_hypothesis_pipeline_spec.md` are legacy aliases. I added PM notes to both files so implementers do not pick them up as the current A4-A/A4-B strategy specs.

## Next Work Packet

1. Run a post-grace `[27]` narrow check later; close `P1-INTENT-FREEZE-27` only if it passes outside fresh-restart grace.
2. Create W-AUDIT-8a Phase C0 work packet: table/retention inventory, production topic guard test, legacy parser status, and BB standalone liquidation-topic probe contract.
3. After C0, draft A4-B / `W-AUDIT-8c` Liquidation Cluster Reaction spec against `LiquidationCascade`, still fail-closed until C1.
4. Draft A4-A / `W-AUDIT-8b` Funding Skew Directional spec from the already-live funding curve panel; keep demo/mainnet execution limitations explicit.
