# E2 Adversarial RCA — Phase 1b 0-attempt BLOCKER (2026-05-18)

**Reviewer**: E2 (Senior Code Reviewer + Adversarial Auditor)
**Triggered by**: PM main session dispatch (Phase 1b 0-attempt observation in trading.fills)
**Output mode**: Inline returned by E2 per base profile (no E2-authored file); this file is PM-curated persistence
**Verdict**: **BLOCKER** — RETURN to E1
**Source**: Linux runtime `ssh trade-core` empirical + Rust code path tracing

---

## Root cause: Phase 3 (Config / Runtime Activation Surface)

Phase 1b dispatch code is **fully wired in production binary**. The runtime activation flag `use_maker_close` is cold-default `false` with **ZERO production callers** to flip it true. Binary contains all 10 fallback enum values, V094 INSERT, and `compute_close_limit_price` symbols — but `commands.rs:117` early-returns `CloseOrderDispatchShape::market()` whenever `!self.use_maker_close`, bypassing the entire whitelist / maker price compute / audit chain.

The Demo pipeline ALWAYS runs with `use_maker_close=false` because no boot sequence, no TOML loader, no env var, no IPC handler, and no PyO3 binding calls `set_use_maker_close_runtime`. Only test-only callers exist (4 hits in `tick_pipeline/tests/dual_rail_dispatch.rs`).

## Evidence chain (top 3)

### 1. Binary contains Phase 1b code (path wired)
- `/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine` mtime `2026-05-17 23:13`, post-`ea4ceca6` (2026-05-16 23:47).
- `strings` extracts:
  - All 10 enum values: `timeout_taker`, `postonly_reject`, `fallback_to_taker_mandatory`, ...
  - V094 `INSERT INTO trading.fills (... close_maker_attempt, close_maker_fallback_reason)`
  - `compute_close_limit_price` symbol
- Engine PID 1066422 started 23:13:01.

### 2. Cold-default + dead activator
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:62` initialises `use_maker_close: false`.
- `rust/openclaw_engine/src/tick_pipeline/commands.rs:117` early-returns `market()` when `!self.use_maker_close`.
- Production grep `set_use_maker_close_runtime` across `srv/`: **0 production callers**.
- Only 4 test-only hits in `tick_pipeline/tests/dual_rail_dispatch.rs` + 1 self-reference in test wrapper.

### 3. Writer behaviour consistent with skip-path
- `commands.rs:786-798`: `close_maker_audit` is `Some(..)` only when `TimeInForce::PostOnly` set by `close_order_dispatch_shape`, which only happens when `use_maker_close=true`.
- With cold-default, `close_maker_attempt=FALSE` + `close_maker_fallback_reason=NULL` for **every** close fill regardless of whitelist membership.
- `risk_close:halt_session` + `ma_reverse_cross` rows also FALSE/NULL — confirms gate kicks in **before** whitelist eval, not the keep-market path writing `keep_market_whitelist`.

Entry/passive `close_maker_attempt=FALSE` is correct by V094 design (column is `NOT NULL DEFAULT FALSE`).

## Severity: BLOCKER

- **Phase 2a 14d observation period is completely void**. Engine never attempts maker close. Expected per spec §4.3 conservative 25% / median 35% maker_attempt rate → observed 0%.
- All taker-close bleed reduction targeted by Phase 1b is currently **0% realised**.
- Continuing the 14d clock without runtime activation produces no signal — calendar must reset post-IMPL+deploy.
- AMD-2026-05-15-02 §3.1 "cold-default `use_maker_close=false` configuration layer" expectation has cold-default but **missing activation layer** — AMD spec gap.

## Fix proposal (RETURN to E1, PA must select option)

### Option A — TOML (surgical, pattern-aligned, recommended)
- Add `runtime.use_maker_close` boolean to `config/risk_config_demo.toml`
- Wire into `apply_risk_snapshot` / `sync_risk_config_if_changed` (RMW pump in `pipeline_config.rs`)
- Sibling pattern: H0Gate shadow_mode at `pipeline_ctor.rs:80-93`
- Demo-only enforcement remains in `set_use_maker_close_runtime` (live/paper reject already implemented)

### Option B — env var (faster shortcut)
- Read `OPENCLAW_USE_MAKER_CLOSE=1` in `pipeline_ctor::with_balance` or boot path
- Gated by `PipelineKind::Demo`
- Risk: env var pattern is non-governance-friendly; cannot ArcSwap hot-reload

### Files to touch
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` (read flag — both options)
- `rust/openclaw_engine/src/tick_pipeline/pipeline_config.rs` (Option A only — RMW pump)
- `config/risk_config_demo.toml` (Option A only — add field)

### Effort + risk
- ~40 LOC IMPL
- Risk LOW: cold-default false preserved; live/paper hard-blocked at activator; no schema/migration impact; no order-flow contract change since binary path already handles `use_maker_close=true`
- Test surface: existing dual_rail_dispatch.rs tests need RUNTIME activation case added
- Deploy: `restart_all.sh --rebuild` + 4h verify on Demo

## Verification protocol (post-IMPL)

```sql
-- 1. Confirm >0 maker_attempt rate within 2h of restart
SELECT engine_mode, fill_role,
       COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS attempts,
       COUNT(*) FILTER (WHERE liquidity_role IN ('maker','taker')) AS close_total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE close_maker_attempt=TRUE)
             / NULLIF(COUNT(*) FILTER (WHERE exit_reason IS NOT NULL), 0), 2) AS attempt_pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND engine_mode IN ('demo','live_demo')
   AND exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                       'ma_reverse_cross','bw_squeeze','pctb_revert')
 GROUP BY engine_mode, fill_role;

-- 2. fallback_reason distribution (expect non-NULL on closures hitting whitelist)
SELECT close_maker_fallback_reason, COUNT(*)
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND close_maker_attempt = TRUE
 GROUP BY 1 ORDER BY 2 DESC;
```

### Acceptance criteria
- `attempt_pct >= 25%` within 4h of restart on Demo whitelist closes (spec §4.3 conservative)
- 0% on `risk_close:halt_session` (negative whitelist)
- non-NULL `fallback_reason` on every `close_maker_attempt=TRUE` row that didn't fill at PostOnly limit

## Relevant file paths (absolute)

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:62` (cold default `use_maker_close: false`)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:91-107` (dead activator API)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:117` (skip-path gate)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:786-798` (writer payload chain)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:85-106` (whitelist policy)

## Downstream impact

- **Phase 2a 14d observation reset**: calendar restart from post-fix-deploy timestamp
- **W-AUDIT-8b Round 2 RED verdict** is unaffected (independent statistical sweep on funding rate panel data)
- **W-AUDIT-8a C1 production revival** is unaffected (allLiquidation production topic LIVE per commit `0e8a8ae8`)
- **AMD-2026-05-15-02 §3.1 wording** needs patch: "cold-default `use_maker_close=false`" + add "with TOML runtime activator `runtime.use_maker_close`"

## Chain handoff

**RETURN to E1** via PA option-selection dispatch. Suggested chain:
1. PA: option A vs B design decision + IMPL ticket draft (~30-60min)
2. E1: IMPL ~40 LOC + add runtime activation test case (~2-4h)
3. E2: re-review IMPL ((adversarial check on activator surface) (~30-60min)
4. E4: regression test pass (~30min)
5. QA: deploy readiness + verification protocol execution (~30min)
6. operator: `restart_all.sh --rebuild` on Linux + 4h verify

**Total ETA**: ~8-12h to verified maker_attempt rate ≥25% post-fix.

---

**E2 REVIEW DONE**: 1 BLOCKER finding (missing production activator for `use_maker_close`); RETURN to E1 via PA option selection.
