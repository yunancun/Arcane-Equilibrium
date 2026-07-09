# BB Prestart Review - ALR P2-3 Service Only

Date: 2026-07-09
Verdict: `APPROVE_SERVICE_ONLY_ENGINE_RESTART_DENIED`

The ALR unit connects only to local PostgreSQL using a role that cannot use
broker credentials and has no Bybit REST/WS, official-MCP, order, account,
position, private-read, signature, rate-limit, or trading client surface.
The service consumes existing Rust-owned scanner database rows and appends only
ALR evidence.

BB approves the limited role/DSN/unit/startup-reconciliation apply defined in
the PM request. It denies any engine restart because the current engine would
resume with an enabled demo learning writer, bounded probe adapter, and Bybit
connector write setting. No source or runtime action here grants exchange,
order, Decision Lease, Cost Gate, proof, serving, promotion, or live authority.
