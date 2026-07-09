# E4 Isolated PostgreSQL Regression - ALR P2-4

Date: 2026-07-09
Verdict: `PASS`

A disposable Linux PostgreSQL 16 container applied V030, V151, V152, and the
reviewed `alr_shadow` contract. The real shadow role reconciled four scanner
rows, then executed the P2-4 operational probe.

- startup reconciliation: `4` persisted, `0` duplicate;
- operational statistical run: `1` persisted, `0` deferred;
- provenance: `4` `training_input` edges;
- run ledger: `1` row;
- UPDATE denial: verified against ALR artifact, provenance, and run tables;
- authority flags: exchange/trading/proof/serving/promotion all false.

The first container had been removed after it exposed the datetime-to-UTC-Z
contract gap. The corrected R2 container passed and was removed automatically.
No production service, database, scanner, engine, broker, order, lease, Cost
Gate, serving, promotion, or proof state was touched by this regression.
