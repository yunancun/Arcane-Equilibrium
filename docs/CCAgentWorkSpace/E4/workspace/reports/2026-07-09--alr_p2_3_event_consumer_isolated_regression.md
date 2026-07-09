# E4 Regression Test Report - ALR P2-3 Event Consumer

Date: 2026-07-09
Verdict: PASS

| Check | Result |
|---|---|
| Mac P2 focused plus adjacent, run 1 | `171 passed` |
| Mac P2 focused plus adjacent, run 2 | `171 passed` |
| Targeted Rust identity notification test | `1 passed`, `4405` unrelated filtered |
| Rustfmt / diff check / Python bytecode compile | PASS |
| Linux disposable PostgreSQL listener retry | PASS |

The first disposable probe exposed a `FOR SHARE` privilege mismatch and was
removed automatically. After the select-only repair, a new disposable
PostgreSQL container applied V151 and the no-credential role contract, then a
real `alr_shadow` listener consumed one `pg_notify` wake and appended one
source/ingest/watermark/provenance chain. Replaying the same wake returned zero
new rows. A competing advisory-lock acquire was rejected; role UPDATE and
DELETE were denied. Final isolated ledger counts were `1/1/1/1`
(source/ingest/watermark/edge). The container was removed.

The isolated result exposed all exchange/trading/proof/serving/promotion
authority counters as false. No existing PostgreSQL, scanner source row,
service, engine, broker, order, lease, Cost Gate, proof, serving, promotion,
or retention state was changed.
