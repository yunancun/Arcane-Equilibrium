# AEG-S1 Foundation Unblock Packet

Date: 2026-06-01
Status: PM dispatch-ready; docs/design/read-only only
Owner: PM -> PA/MIT/QC/BB -> E1 only after scoped gates
Scope: classify AEG blocked items after S0 formal pass and convert safe work into S1 Foundation dispatch.

This packet resolves the ambiguous "blocked" state left after AEG-S0 by separating
design-ready work from implementation/runtime work. It does not authorize code,
migration, DB write, retention mutation, runtime deploy, auth change, order,
collector runtime, backfill run, alpha scoring, or promotion reporting.

## 1. Source Evidence

| Evidence | Confirmed result |
|---|---|
| `docs/execution_plan/2026-05-31--aeg_s0_contracts.md` | AEG-S0 formal PASS; only AEG-S1 Foundation limited scope is open. |
| `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_retention_symbol_universe.md` | MIT advisory PASS; `market.klines` is still 365d retention; S1-W1-S2 remains locked until operator signs storage/window/breadth. |
| `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv` | 797-row 18mo USDT LinearPerpetual survivorship universe, including 225 delisted/Closed overlap symbols. |
| `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-31--s2_w0_s1_listing_gate_a_feasibility.md` | Listing Gate-A can proceed to Gate-B; no production collector IMPL is authorized. |
| `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s4_w0_s1_bull_regime_backfill_preflight.md` | Bybit 2024 bull data is available by public API, but local PG has no 2024 rows and storage/writer gates block DB-writing backfill. |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_now_three_parallel_dispatch.md` | PM integration already identified the operator decision packet; this file turns it into S1 Foundation dispatch boundaries. |

## 2. Blocker Matrix

| Blocked item | Resolution now | Still not allowed |
|---|---|---|
| Bybit historical backfill writer | Convert to S1-W1-S2 design dependency. Writer scope can be drafted only after S1-W1-S1 chooses storage/provenance and S0 endpoint contract is mapped into implementation requirements. | No E1 writer implementation, no DB writes, no backfill run. |
| `market.klines` retention/runtime PG mutation | Convert to S1-FND-1 storage/change-control package. Use MIT sizing: current 365d, proposed 1095d, estimated 3y size about 4.6-7.0 GiB. | No Timescale retention change from Mac; no Linux PG mutation until operator + MIT/E2/E4 gates. |
| Funding/OI/long-short 18mo backfill | Convert to S1-FND-1 decision branch: extend raw-table retention or create dedicated research history/provenance storage. S4 explicitly adds `market.funding_rates` to the gate. | No funding/OI/long-short ingestion or historical rows. |
| Mark/index/premium kline client implementation | Convert to BB/PA client-gap design. Price-kline endpoints need price-only parser/schema and cannot reuse standard OHLCV assumptions. | No endpoint ingestion implementation. |
| `market.market_tickers` index/mark persistence gap | Convert to FND-4 fix-vs-bypass design for historical basis/index evidence. AEG-S0 already excludes `market_tickers.index_price/mark_price` until persistence is fixed or bypassed. | No historical basis/index promotion evidence relying on dead or sparse ticker persistence. |
| Listing-capture collector IMPL | Convert to S2 Gate-B planning: 24h isolated PreLaunch phase-transition probe plus capture-only design. | No production collector runtime or strategy-intent linkage. |
| Alpha scoring / promotion report | Keep blocked until S1 backfill/storage, S2 regime/breadth automation, and robustness matrix are green. | No alpha promotion, no candidate verdict, no paper/demo shortcut. |

## 3. Foundation Dispatch Opened

The following work is safe to dispatch now because it is docs/design/read-only:

| ID | Owner chain | Output | Acceptance |
|---|---|---|---|
| `AEG-S1-FND-1` Storage, retention, provenance change-control | PM -> MIT+PA -> E2/E4 review prep | Decision package for `market.klines` 1095d vs dedicated research storage; funding/OI/long-short storage branch; rollback and verify plan. | Names exact storage surface, retention/provenance model, migration path if any, and operator execution gate. |
| `AEG-S1-FND-2` PIT universe builder contract | PM -> MIT -> PA | Builder spec using `market.symbol_universe_snapshots` and the 797-row artifact as seed evidence. | Rejects current-survivor-only selection; includes lifetime masking and artifact digest requirements. |
| `AEG-S1-FND-3` Side-evidence artifact contract | PM -> PA+QC | `side_evidence.json` schema and run-id linkage. | Side evidence is explicitly secondary and excluded from promotion gates. |
| `AEG-S1-FND-4` Public endpoint runner and persistence gap map | PM -> BB+PA -> MIT | Endpoint-by-endpoint implementation/readiness map for kline, funding, OI, long-short, price-only mark/index/premium, ticker/orderbook where relevant; includes `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` fix-vs-bypass design. | Captures pagination, inclusive windows, rate-limit backoff, strict parser failure, persistence surface, and coverage report requirements. |
| `S2-GATE-B-PREP` Listing capture Gate-B plan | PM -> BB+MIT -> QC | 24h isolated PreLaunch phase-transition probe plan and capture-only isolation design. | No production collector code; no strategy leakage; n>=30 forward capture remains future evidence. |

## 4. Completion Check

Complete as of this packet:

- AEG-S0 formal review is closed PASS.
- S1-W1-S1 retention/window/breadth advisory is complete.
- Survivorship-corrected 18mo universe artifact exists and has 797 data rows.
- S2 Gate-A maker-fill feasibility proceeds to Gate-B planning.
- S4 preflight proves 2024 bull funding/price data is available by Bybit public API and identifies exact storage/script blockers.

Not complete:

- Linux retention policy is not changed.
- `market.funding_rates`, OI, and long-short 18mo storage is not decided or implemented.
- Bybit historical DB writer does not exist as a production-ready tool.
- No 18mo backfill or 2024 bull DB-writing backfill has run.
- No mark/index/premium endpoint ingestion implementation has landed.
- No historical basis/index evidence path is open until the index/mark persistence
  gap is fixed or explicitly bypassed.
- No listing collector runtime implementation has landed.
- No alpha scoring, robustness matrix, promotion report, or candidate verdict is open.

## 5. Operator Decision Card

The next operator/PM decision must answer these before implementation:

1. Approve or reject `market.klines` retention extension to 1095 days.
2. Choose funding-history storage: extend `market.funding_rates` retention or create dedicated research history/provenance storage.
3. Confirm 18mo collection window and core25 primary analysis with full survivorship-corrected collection.
4. Confirm that S1-W1-S2 stays locked until the chosen storage/provenance path is reviewed and ready.

If any answer is negative, S1 Foundation remains design-only and the backfill/scoring chain stays blocked.
