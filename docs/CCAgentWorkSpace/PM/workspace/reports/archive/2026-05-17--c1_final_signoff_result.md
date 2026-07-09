# W-AUDIT-8a C1 Final Sign-Off Result

**Date**: 2026-05-17T15:06Z
**Role**: PM(default)
**Scope**: final governance result for C1 v2 24h liquidation topic proof. No code change, no DB migration, no runtime restart, no production topic revival, no paper/live/mainnet enablement.

## PM Verdict

**C1 technical proof: PASS.**
**Final BB/MIT sign-off: APPROVE-CONDITIONAL.**

This is not a C1 transport or stability failure. The isolated 24h WebSocket proof completed and produced a valid candidate PASS artifact.

Final review result:

1. BB initially blocked the prior proposed side semantics, then re-signed after PM corrected the mapping to Bybit V5 semantics: `S=Buy` is long liquidation and `S=Sell` is short liquidation.
2. MIT approves the field mapping and Stage 0R precision, but requires schema/writer idempotency alignment before production writer revival because the current DB primary key `(symbol, ts, side)` can collapse distinct same-ms same-side liquidation items.

Production `allLiquidation*` writer revival remains blocked until the MIT idempotency condition is corrected and re-signed. W-AUDIT-8c may proceed only as a correction-scoped packet that includes the corrected side mapping, tests for both sides, and the schema/writer idempotency fix.

## C1 Evidence

Final runtime artifacts on `trade-core`:

- `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md`
- `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.json`

Key values:

| Field | Value |
|---|---:|
| Session | `c1_v2_20260516T145616Z` |
| Started | `2026-05-16T14:56:16Z` |
| Finished | `2026-05-17T14:56:15Z` |
| Verdict | `PASS_C1_PROOF_CANDIDATE` |
| C1 proof eligible | `true` |
| Elapsed sec | `86399.2236` |
| Uptime sec | `86398.4539` |
| Uptime ratio | `0.9999910906` |
| Candidate topic | `allLiquidation.BTCUSDT` |
| Candidate messages | `161` |
| Subscribe success / failure | `8613 / 0` |
| Reconnect attempts / failures | `0 / 0` |
| Connection errors | `[]` |
| Poison events | `[]` |

Control streams remained active through the run:

| Topic | Count |
|---|---:|
| `tickers.BTCUSDT` | `540173` |
| `orderbook.50.BTCUSDT` | `2373076` |
| `publicTrade.BTCUSDT` | `256077` |
| `kline.1.BTCUSDT` | `49001` |

## BB Final Review

**Verdict**: `APPROVE` after corrected side mapping

Accepted:

- The C1 artifact is `PASS_C1_PROOF_CANDIDATE`.
- `allLiquidation.BTCUSDT` produced valid envelope/data shape: `topic`, `type`, `ts`, `data[]`, and item fields `T/s/S/v/p`.
- No handler rejection, subscribe failure, connection error, poison event, reconnect issue, or control-stream pollution was observed.

Initial blocker:

- Proposed semantics `S=Sell -> long liquidation -> +1` and `S=Buy -> short liquidation -> -1` are reversed relative to Bybit V5 public all-liquidation documentation.

Corrected and approved BB mapping:

- `S=Buy` = long liquidation; mean-reversion reaction direction `+1`.
- `S=Sell` = short liquidation; mean-reversion reaction direction `-1`.
- W-AUDIT-8c must test both `Buy` and `Sell` mapping paths before writer or strategy revival.

BB remaining condition:

- Production topic/writer remains disabled until MIT schema/idempotency sign-off is separately satisfied and PM explicitly authorizes revival.

Official reference:

- https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation

## MIT Final Review

**Verdict**: `APPROVE-CONDITIONAL`

Accepted:

- C1 final verdict gate passes.
- Mapping `T -> ts`, `s -> symbol`, `S -> side`, `v -> qty`, `p -> price` is sufficient.
- Use event-level `T`, not frame-level `ts`.
- Current `real` precision for `qty` and `price` is acceptable for BTCUSDT W-AUDIT-8c Stage 0R.
- Top-level `type=snapshot` can be ignored for storage; parser should reject/log any unexpected non-snapshot type.
- One `data[]` item should map to one liquidation row.

Condition before production writer revival:

- Current Linux schema primary key is `PRIMARY KEY (symbol, ts, side)`.
- Final samples include distinct same-`T/s/S` liquidation items with different price.
- Writer revival must not rely on lossy `(symbol, ts, side)` idempotency if Stage 0R needs one row per item.

MIT accepted dedupe identity:

- `(ts, symbol, side, qty, price)` is sufficient for initial revival.
- A V09X schema/writer decision should preserve this five-field identity or add a surrogate/event-sequence key.

## PM Decision

1. Mark C1 v2 proof as **TECHNICAL PASS / APPROVE-CONDITIONAL**.
2. Do not enable production `allLiquidation*`.
3. Treat BB side semantics as signed off only with the corrected mapping: `Buy` long liquidation / `Sell` short liquidation.
4. Do not revive production writer or deploy W-AUDIT-8c until MIT idempotency is fixed and re-signed.
5. Next dispatch should be a narrow correction packet:
   - V09X idempotency/surrogate-key plan preserving one `data[]` item per row.
   - W-AUDIT-8c tests covering both `Buy` and `Sell` mapping paths.
   - E1 implementation only inside that corrected scope.

PM STATUS: C1 TRANSPORT PASS / BB APPROVE / MIT APPROVE-CONDITIONAL / PRODUCTION WRITER REVIVAL BLOCKED UNTIL IDEMPOTENCY FIX.
