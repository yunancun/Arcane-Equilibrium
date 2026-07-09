# ALR P2-2 Persistence Design

P2-2 will add only ALR-owned append-only tables and a parameterized repository.
The existing Rust scanner table remains read-only. Duplicate source identity is
safe only when its canonical hash agrees; conflicting content fails closed and
is never overwritten.

The existing database remains untouched until source implementation completes,
the three source heads align, and the preapply check passes. All ledger rows and
provenance are retained; P2-6 may later retain only unreferenced derived cache.
