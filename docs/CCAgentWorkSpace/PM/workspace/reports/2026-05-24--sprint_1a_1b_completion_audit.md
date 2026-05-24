# Sprint 1A -> 1B Completion Audit

Date: 2026-05-24  
Owner: PM local audit  
Scope: verify TODO 1A through 1B completion claims against source, tests, Linux runtime, and higher-level product outcome.

## Verdict

Sprint 1A through 1B is **not fully complete** in runtime/product terms.

What is complete:
- Design/spec layer for most 1A modules is landed.
- Mac/source layer has real implementation for 1A-delta trait stubs, 1A-zeta LAL/health/replay prototype pieces, Sprint 1B C10 funding_harvest, and Earn Wave B source modules.
- Targeted source tests are green for the audited C10/Earn areas.
- trade-core production PG has the current landed V100/V103/V106/V107/V112 table set applied, and V106 health observations are live.

What is not complete:
- Running trade-core engine binary does not include C10 funding_harvest, Earn, LAL auto-tier, or replay divergence symbols.
- C10 Stage 1 Demo is not closed; it still needs E2/V108, E1 follow-up if required, E4 regression, QA Stage 0R acceptance, and PM Phase 3e.
- Earn first stake is not executed; Wave C is still blocked by IntentProcessor Earn branch, OP-1 Bybit key refresh, Stage 0R Earn variant, rebuild/deploy, and operator first-stake execution.
- Several 1A modules remain design/spec-only by plan, not implementation gaps.

## Evidence

Local source/tests:
- Migration files present: V100, V101, V102, V103, V106, V107, V112.
- Migration SQL missing by design/future work: V099, V104, V105, V108, V109, V110, V111, V113, V114, V115, V116.
- C10 files present: `rust/openclaw_engine/src/strategies/funding_harvest/*` and `helper_scripts/canary/replay_funding_harvest.py`.
- Earn files present: `rust/openclaw_engine/src/bybit_earn_client.rs`, `rust/openclaw_engine/src/database/earn_movement_writer.rs`, `rust/openclaw_engine/src/cron/earn_reconciliation.rs`, and LeaseScope Earn variants.
- `cargo test -p openclaw_core --release lease_scope`: 7 passed.
- `cargo test -p openclaw_engine --release --lib strategies::funding_harvest`: 61 passed.
- `cargo test -p openclaw_engine --release --lib earn`: 69 passed.
- `cargo test -p openclaw_engine --release --lib bybit_earn_client`: 10 passed.
- `cargo test -p openclaw_engine --release --lib earn_movement_writer`: 14 passed.
- `python -m py_compile helper_scripts/canary/replay_funding_harvest.py` passed.
- `pytest helper_scripts/canary/ --tb=short -q`: 235 passed.

trade-core read-only runtime evidence:
- Remote source HEAD: `c2fc1d8b`.
- Engine process: PID 4105805, started 2026-05-24 00:11:52 +0200, owns `/tmp/openclaw/engine.sock`.
- API process: PID 3989463 owns port 8000.
- Watchdog: `engine_alive=true`.
- PG `_sqlx_migrations`: max version 112, count 102.
- V100/V101/V102/V103/V106/V107/V112 registered with `success=true`.
- Target tables present: `governance.lease_lal_assignments`, `governance.lease_lal_tiers`, `learning.earn_movement_log`, `learning.health_observations`, `learning.hypotheses`, `learning.hypothesis_preregistration`, `learning.replay_divergence_log`.
- 30m health rows: `api_latency=240`, `database_pool=150`, `engine_runtime=360`, `pipeline_throughput=300`, `risk_envelope=30`, `strategy_quality=756`.
- `learning.earn_movement_log`: 0 rows.
- `learning.replay_divergence_log`: 0 rows.
- Running binary mtime: 2026-05-23 17:56:09 +0200.
- C10/Earn commits are later than the binary: C10 `255a83f6` at 2026-05-23 19:36:55 +0200, Earn Wave B `875de212` at 21:09:38, Earn spec `5e95edfe` at 21:24:41.
- Binary `strings` hits: `funding_harvest=0`, `EarnStake=0`, `LAL_0_AUTO=0`, `replay_divergence_log=0`, `health_observations=1`.

## Completion Matrix

| Area | Real status | Reason |
|---|---|---|
| 1A-alpha / repair / beta / gamma | DESIGN-DONE, IMPL-PENDING | Specs/ADR/runbooks landed; many modules intentionally future implementation. |
| 1A-delta | SOURCE-DONE, runtime not proven | Trait stubs and tests landed; running Linux binary still lacks expected later runtime symbols. |
| 1A-zeta | PARTIAL RUNTIME-DONE | V106/V107/V112 and production tables exist; health rows live; LAL/replay runtime integration still not in binary. |
| V099 autonomy | DESIGN-DONE only | No local V099 SQL migration; GUI/Rust cascade waits for Wave 5 implementation. |
| Sprint 1B early | SOURCE-DONE | Tests pass locally, but runtime binary evidence is not sufficient for closure. |
| C10 funding harvest | SOURCE/HARNESS-DONE, Stage 1 not closed | Runtime binary lacks C10 and C10 accounting/acceptance gaps remain. |
| Earn first stake | SPEC-FINAL + Wave B source done, not executed | No IntentProcessor Earn branch, no refreshed Bybit key, no first stake rows. |
| PG checksum/current landed SQL | CLOSED for current landed set | trade-core has V100/V103/V106/V107/V112 family applied and health live. |

## Unimplemented Work Classification

Intentional design/future implementation:
- V099 autonomy toggle and failsafe cascade.
- V104/V105/V108/V109/V110/V111/V113/V114/V115/V116 SQL migrations.
- M2/M4/M6/M7/M8/M9/M10/M11 continuous/full implementations.
- C10 final closure chain and Earn Wave C were already marked as next-session work.

Operational/runtime not applied:
- trade-core source is synced, but the running binary predates C10/Earn commits.
- Earn and replay tables exist but have no runtime rows.

Logic/acceptance gaps that should not be ignored:
- Short-capable strategies can emit `OrderIntent { is_long: false, intent_type: OpenLong }`. Today execution direction still follows `is_long`; future LeaseScope/IntentProcessor routing will make this unsafe unless normalized before B6/Earn routing.
- C10 synthetic spot close currently realizes spot PnL with `entry_price` fallback because the Strategy trait does not provide close price. This may be acceptable only if Stage 0R replay is the explicit accounting authority; otherwise Stage 1 Demo PnL evidence will be misleading.
- Earn client/writer/reconciliation have source tests, but there is no production execution branch or operator first-stake evidence.

## Product-Level Assessment

The project now has a stronger governance/data foundation, but it cannot yet claim the intended Sprint 1B outcome: a trustworthy C10 Stage 1 Demo plus an executed Earn first stake. It is also not evidence for Sprint 4 live readiness. The current state is enough to dispatch closure work; it is not enough to promote live, run first stake, or present C10 runtime PnL as proven.

## PM Dispatch

1. C10 closure chain: E2 + V108 review, resolve synthetic spot close accounting and IntentType direction risk, then E1 patch if required, E4 regression, QA Stage 0R acceptance, PM Phase 3e.
2. Earn Wave C: wait for OP-1 key refresh, implement B6 IntentProcessor Earn branch, decide Stage 0R Earn variant, rebuild/deploy, then execute $100-200 Flexible-only first stake.
3. Runtime deploy: after closure reviews, rebuild/restart trade-core and verify binary strings/symbols plus watchdog and targeted C10/Earn checks.
4. Keep design-only 1A modules marked as future implementation, not silently closed.
