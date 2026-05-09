# W-AUDIT-5b AI Budget ArcSwap Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the cache-mechanics part of the W-AUDIT-5b `ai_budget`
review without changing budget policy or live authority.

- Replaced `BudgetTracker.config_cache: Arc<RwLock<BudgetConfig>>` with
  `Arc<ArcSwap<BudgetConfig>>`.
- Converted config refresh and IPC override paths to whole-snapshot swaps.
- Converted read-heavy config consumers (`get_remaining`, `degrade_level`,
  `cost_edge_ratio`, and `status_json`) to ArcSwap snapshot reads.
- Kept `usage_cache: Arc<RwLock<UsageCache>>` by design because spend recording
  mutates cumulative per-scope counters.
- Added a static structure guard to prevent the config cache from drifting back
  to async `RwLock` while preserving the mutable usage lock.

Current `ai_budget` is a five-scope budget model (`local_total`,
`platform_hard_cap`, `agent_teacher`, `agent_analyst`, `agent_reserve`).
No per-strategy budget schema, hard authority, or policy expansion was
introduced by this checkpoint. Any per-strategy model should be handled as a
separate schema/policy design, not as a cache-swap refactor.

## Verification

- `cargo fmt --all --manifest-path rust/Cargo.toml --check`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine ai_budget -q`
  -> 31 passed plus filtered zero-test targets
- `cargo check --manifest-path rust/Cargo.toml -p openclaw_engine --bin openclaw-engine`
  -> pass with pre-existing Rust warnings
- `python3 -m pytest tests/structure/test_ai_budget_arc_swap_static.py -q`
  -> 1 passed
- `git diff --check`

## Boundary

Source/test/docs only. No rebuild, restart, deploy, DB apply, live auth
mutation, scanner authority change, Executor hard authority, strategy/risk
config mutation, MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
