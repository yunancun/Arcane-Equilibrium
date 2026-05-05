---
status: accepted
---

# Trading/risk/model parameters use Arc<ArcSwap<Config>> for restart-free hot reload

All trading-related parameters must support runtime hot updates without engine restart. The tick hot path uses `Arc<ArcSwap<Config>>` for lock-free reads; non-hot-path config can use `Arc<RwLock>`. IPC `update_*` handlers validate, build a new Config, `arc_swap.store(Arc::new(new))`, persist JSON, and return — the next tick reads the new value naturally. Agents and Operator share the same write path; only the audit log records `source` to distinguish them.

## Considered alternatives

A restart-to-apply config flow was rejected because Agents adjust parameters live (Strategist, Guardian, Cognitive Modulator) and forcing a process bounce per tweak is incompatible with autonomous operation. See ARCH-RC1 unified config contract at `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`.
