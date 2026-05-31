# PM Report — AEG-S1-FND-2/FND-4 Parallel Integration

Date: 2026-06-01
Role: PM(default)
Scope: integrate operator-approved FND-1 storage branch with parallel FND-2 and FND-4 docs/design outputs.
Mode: documentation/governance only; no DB write, migration apply, retention mutation, runtime deploy, auth, order, endpoint ingestion, collector runtime, backfill run, alpha scoring, or promotion verdict.

## Dispatch

Operator approved the FND-1 recommended storage branch and asked PM to continue
FND-2 while opening FND-4 in parallel.

Sub-agent fanout:

| Agent | Role | Scope | Result |
|---|---|---|---|
| Cicero `019e8034-d203-7981-a6ed-f57bc0620638` | MIT(explorer) | FND-2 PIT universe builder contract | Complete, read-only; no files/git/DB/runtime touched. |
| Aristotle `019e8034-ed72-77e1-b6d1-0dede37c1e24` | BB(explorer) | FND-4 endpoint/client/persistence gap map | Complete, read-only; no web/git/files/DB/runtime touched. |

## Integrated Outputs

| ID | Output | PM status |
|---|---|---|
| `AEG-S1-FND-1` | `docs/execution_plan/2026-06-01--aeg_s1_fnd1_storage_retention_provenance_change_control.md` | Decision branch approved: `market.klines` 1095d + DB provenance ledger; dedicated research-history storage for funding/OI/long-short. Execution still blocked. |
| `AEG-S1-FND-2` | `docs/execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md` | Contract complete: PIT source is `market.symbol_universe_snapshots`; 797-row CSV is seed/regression only; current-survivor shortcuts fail. |
| `AEG-S1-FND-4` | `docs/execution_plan/2026-06-01--aeg_s1_fnd4_public_endpoint_runner_client_gap_persistence_map.md` | Map complete: extend isolated Python public replay client; bypass `market_tickers` for historical basis/index; fix ticker persistence later for forward capture only. |

## Key Decisions

FND-2:

- Required source is V058 `market.symbol_universe_snapshots`, including
  `status`, listing/delisting timestamps, source URI, payload hash, and raw
  payload.
- Target filter is Bybit linear USDT `LinearPerpetual`; raw `category=linear`
  alone is too broad.
- Builder must use fixed `run_id/asof/window` inputs, lifecycle masks, delisted
  proof, and deterministic artifact digests.
- Existing 797-row CSV with 225 delisted/closed overlap rows is a seed and
  regression check, not a permanent source.

FND-4:

- Preferred runner base is the isolated Python public replay client, extended
  with an explicit allowlist and fail-closed parsers.
- Rust `MarketDataClient` is not accepted for evidence ingestion until BB
  verifies a public-only facade and zero-default parser behavior is removed.
- Mark/index/premium endpoints are price-only kline surfaces; they cannot reuse
  OHLCV schema/parsers or fabricate volume/turnover.
- Bybit `tickers` and `orderbook` are current snapshots only. Local
  `market.market_tickers` is forward evidence where recorded, not 18mo
  historical proof.

## Still Blocked

- V### migration implementation or apply.
- Timescale retention mutation.
- New research-history schema apply.
- DB provenance ledger apply.
- Bybit historical writer implementation.
- Endpoint ingestion/backfill run.
- Listing collector runtime.
- Alpha scoring, robustness matrix, promotion report, candidate verdict.

## Next Schedule

1. `AEG-S1-FND-3`: side-evidence artifact contract; secondary-only and excluded
   from promotion gates.
2. `S2-GATE-B-PREP`: 24h isolated PreLaunch phase-transition probe plan and
   capture-only collector design.
3. MIT migration-design packet for the approved FND-1 storage branch:
   `market.klines` 1095d retention/provenance ledger plus dedicated
   research-history tables. This is design/review only until separately
   approved for execution.
