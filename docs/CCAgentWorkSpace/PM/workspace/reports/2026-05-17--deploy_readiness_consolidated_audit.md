# PM — Deploy Readiness Consolidated Audit

Date: 2026-05-17
Role: PM
Scope: five-commit deploy readiness audit, Linux runtime empirical state, deploy order, operator authorization checklist, and post-authorization V094/V095 results.
Constraint: initial audit was read-only. After explicit operator authorization, Step 1 V094 manual apply/register, Step 2 Phase 1b engine deploy/restart, and Step 3 V095 manual apply/register were executed only. No production `allLiquidation*` subscription, no `risk_config`/runtime mutation, no W-AUDIT-8b tombstone, no sub-agent dispatch.

Verdict summary: **STEP 3 V095 APPLIED; PRODUCTION LIQUIDATION REVIVAL STILL BLOCKED**. The initial audit found a Linux cargo regression in the `risk_close:phys_lock_*` literal guard; remediation landed in `b867e452` and Linux `openclaw_engine --lib` is now green at `2969 passed / 0 failed / 1 ignored`. V094 was manually applied/registered, Phase 1b engine-only rebuild/restart completed, and V095 was manually applied/registered after separate authorization. This verdict does not authorize production `allLiquidation*` revival or any risk/runtime config mutation.

## §1 5-Commit Workchain Coverage Matrix（per commit × per role）

Authoritative inputs checked:

- Fix plan SoT: `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md`
- Current state SoT: `docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md`
- PM/E2/E4/MIT/BB workspace reports listed in the operator task.
- `git log --name-only --oneline -1 <commit>` for each subject commit.
- Local/origin/Linux sync pre-remediation: local `HEAD=38a9bedd`, `origin/main=38a9bedd`, Linux `HEAD=38a9bedd`, Linux `origin/main=38a9bedd`.
- Post-remediation sync: local/origin/Linux `HEAD=b867e452` after `fix(engine): route phys-lock test tags through helper`; Linux worktree clean.
- Pre-Step-2 sync: local/origin/Linux `HEAD=5f42771a`; Linux worktree clean.

| Commit | Source/test land evidence | E1 self-report | E2 verdict | E4 regression | A3 / MIT / BB | PM sign-off | Missing / caveat |
|---|---|---:|---:|---:|---:|---:|---|
| `ea4ceca6` Phase 1b close-maker-first Worktree B IMPL | `git log --name-only` shows Phase 1b Rust source/tests plus V094 migration/test surfaces, including close maker dispatch, pricing, fill audit, and healthcheck changes. | ✓ via E1 worktree reports referenced by PM closure | ✓ APPROVE via PM/Operator closure | ✓ historical PASS via PM/Operator closure; current Linux PASS after `b867e452` remediation | ✓ A3 via PM/Operator closure; MIT/BB N/A for this surface | ✓ `2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md` | Final standalone A3/E2/E4 role reports were not found as separate latest artifacts; closure report is the direct SoT. Initial audit found a test-only bare-literal regression in this commit, remediated by `b867e452`. |
| `a6e17d5d` W-AUDIT-8b Round 2 Phase A v0.3 sweep tooling | `git log --name-only` shows `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_*` tooling. | ✓ via implementation/closure packet | ✓ APPROVE via PM/Operator closure | ✓ historical PASS via PM/Operator closure | ✓ A3 via PM/Operator closure; MIT/BB N/A until Phase B result review | ✓ `2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md` | Direct final E1/A3/E2/E4 standalone reports were not found as separate latest artifacts; closure report is the SoT. Phase B rerun remains pending because panel coverage is still `<7d`. |
| `b5b6ce6a` W-AUDIT-8c liquidation correction packet | `git log --name-only` shows V095 migration/tests, parser/writer source, tick helper tests, spec/report updates. | ✓ via correction source/test closure | ✓ initial RETURN fixed, then closure accepted | ✓ PASS per PM closure | ✓ MIT approve-conduit and later re-sign; ✓ BB corrected side-mapping approval | ✓ `2026-05-17--w_audit_8c_correction_source_test_closure.md` | Direct final standalone E1/E2/E4/BB artifacts were not found as separate files; PM closure plus MIT re-sign and C1 final report are the SoTs. Production builders still exclude `allLiquidation*`; V095 schema apply is not production revival. |
| `bfffceeb` V095 dry-run resign | `git log --name-only` shows PM V095 dry-run report, MIT re-sign report, TODO update. | N/A docs/dry-run evidence packet | N/A | N/A | ✓ MIT re-sign in `MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md`; operator copy expected | ✓ PM dry-run report exists | Strict per-commit operator-copy file was not present in this commit. The latest operator continuation SoT carries the V095 dry-run/re-sign state. |
| `82ab71eb` C1 conditional sign-off | `git log --name-only` shows PM C1 final signoff report and TODO update. | N/A docs/sign-off packet | N/A | N/A | ✓ BB + MIT summarized in C1 final report | ✓ `2026-05-17--c1_final_signoff_result.md` | Direct BB/MIT standalone files were not included in this commit; C1 is technical PASS only. Production liquidation revival remains blocked pending explicit later authorization and source/config dispatch. |

Coverage conclusion:

- Source commits are landed across local/origin/Linux.
- Historical workspace closure claims are internally consistent with the current-state SoT.
- Artifact hygiene is imperfect: several final role approvals are present through PM/Operator closure reports rather than standalone role-owned latest reports.
- Initial cargo regression was remediated by `b867e452`; current Linux cargo baseline is green. V094 is applied, Step 2 engine deploy/restart completed, and V095 is applied. Production liquidation revival remains blocked pending separate AMD/source/config dispatch and explicit operator authorization.

## §2 Linux Runtime Empirical State

Checks executed over `ssh trade-core`. Step 1 V094 and Step 3 V095 manual apply/register mutated DB state after explicit operator authorization; Step 2 rebuilt/restarted the engine after separate explicit authorization.

Migration status after Step 3 V095:

```text
SELECT version, success, installed_on
FROM _sqlx_migrations
WHERE version IN (94, 95)
ORDER BY version;

94|fills close maker audit|t|d7db4e674cc0505da787861b6777717059d69902137057350a3b4b0a5e527a41a1e7b7e3cb559ba2fb8a4dd3fead2512|-1
95|market liquidations identity|t|e25f110594587cddafd1e08f7699da593fe63c64af6d26415356c00b4534d8f60f0e67d7640ab8a6b18ba6ba742ca15b|-1
```

Interpretation: V094 and V095 are applied/registered in Linux production DB.

V094 execution details:

- Authorized scope: Step 1 V094 manual apply/register only.
- Backup timestamp: `20260517T201234Z`.
- Backup files:
  - `/tmp/openclaw/migration_backups/_sqlx_migrations_pre_v094_20260517T201234Z.sql`
  - `/tmp/openclaw/migration_backups/trading_fills_schema_pre_v094_20260517T201234Z.sql`
- Source checksum: `d7db4e674cc0505da787861b6777717059d69902137057350a3b4b0a5e527a41a1e7b7e3cb559ba2fb8a4dd3fead2512`.
- Registry description: `fills close maker audit`.
- Registry execution_time: `-1` because this was a manual apply/register, not sqlx auto-migrate.

V094 schema verify:

```text
close_maker_attempt|boolean|NO|false
close_maker_fallback_reason|text|YES|
chk_fills_close_maker_fallback_reason_v094|convalidated=f|NOT VALID
idx_fills_close_maker_attempt_v094|ON trading.fills (engine_mode, ts DESC) WHERE close_maker_attempt = true
```

V095 execution details:

- Authorized scope: Step 3 V095 manual apply/register only.
- Preflight: `market.liquidations` had `0` rows, `0` nulls on target PK columns, `0` duplicate target-PK groups, and `0` side values outside `Buy`/`Sell`.
- Backup timestamp: `20260517T202611Z`.
- Backup files:
  - `/tmp/openclaw/migration_backups/_sqlx_migrations_pre_v095_20260517T202611Z.sql`
  - `/tmp/openclaw/migration_backups/market_liquidations_schema_pre_v095_20260517T202611Z.sql`
  - `/tmp/openclaw/migration_backups/market_liquidations_pre_v095_20260517T202611Z.sql`
- Source checksum: `e25f110594587cddafd1e08f7699da593fe63c64af6d26415356c00b4534d8f60f0e67d7640ab8a6b18ba6ba742ca15b`.
- Registry description: `market liquidations identity`.
- Registry execution_time: `-1` because this was a manual apply/register, not sqlx auto-migrate.

V095 schema verify:

```text
market.liquidations primary key = symbol,ts,side,qty,price
chk_market_liquidations_side_v095|convalidated=f|CHECK ((side = ANY (ARRAY['Buy'::text, 'Sell'::text]))) NOT VALID
market.liquidations row count = 0
```

Panel coverage:

```text
panel.funding_rates_panel days = 6.8566833564814815
```

Interpretation: W-AUDIT-8b Phase B rerun gate remains closed until panel coverage is at least `7.0d`.

Liquidation primary key:

```text
market.liquidations primary key = symbol,ts,side,qty,price
```

Interpretation: Linux DB is post-V095. This is schema readiness only; production `allLiquidation*` topics remain disabled/excluded until a separate revival authorization.

Engine watchdog after Step 2 restart:

```json
{
  "engine_alive": true,
  "snapshot_age_seconds": 8.1,
  "stale_threshold_seconds": 45.0,
  "engines": {
    "paper": {"alive": true, "age_seconds": 11.6},
    "demo": {"alive": true, "age_seconds": 9.2},
    "live": {"alive": true, "age_seconds": 8.1}
  }
}
```

Paper note: `paper` is fresh because the engine writes a disabled paper snapshot on restart. `/tmp/openclaw/pipeline_snapshot_paper.json` and `/tmp/openclaw/paper_state.json` both show `disabled=true` and `disabled_reason="OPENCLAW_ENABLE_PAPER != 1"`; paper trading was not enabled.

Runtime environment read-only sample:

```text
OPENCLAW_AUTO_MIGRATE=0
OPENCLAW_ENABLE_PAPER=0
OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow
OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1
```

Interpretation: current engine restarts should not auto-apply migrations while `OPENCLAW_AUTO_MIGRATE=0`. If this flag is changed to `1` on current source without manual sequencing, V094 and V095 can apply together on restart, which is not the recommended deploy shape.

Healthcheck 40 direct module query:

```text
WARN: 24h MLDE rows=53830, win_rate=0.0%, avg_net=-0.00bps (target>5.0);
maker_like=96.5% (target>=50%), fee_drop=95.7% (target>=60%) —
avg_net -0.00bps <= target
```

Interpretation: `P0-EDGE-1` / check `[40]` remains WARN.

## §3 Cargo Regression Baseline

Operator-requested command path needed correction because `cargo` is in the login shell and the workspace `Cargo.toml` is under `srv/rust`, not `srv`.

Effective command:

```bash
ssh trade-core 'bash -lc "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5"'
```

Observed result after `b867e452` remediation:

```text
test result: ok. 2969 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.64s
```

Initial audit failure, now remediated:

```text
tick_pipeline::on_tick::helpers::phys_lock_wrapper_tests::no_new_literal_risk_close_phys_lock_outside_helpers_rs

RUST-DOUBLE-PREFIX-1 regression (bare literal angle):
new "risk_close:phys_lock_..." string literal outside allowlist
```

Offenders:

- `rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs:409`
- `rust/openclaw_engine/src/strategies/common/maker_price.rs:541`
- `rust/openclaw_engine/src/strategies/common/maker_price.rs:542`

`git blame` mapped all three offender lines to `ea4ceca6`. Fix commit `b867e452` routes the test-only PHYS-LOCK tags through `build_risk_close_tag()` instead of allowing new bare literals or widening the guard allowlist.

Baseline comparison:

- Last known E4 baseline: `2906 passed / 0 failed / 1 ignored`
- Initial audit Linux baseline: `2968 passed / 1 failed / 1 ignored`
- Current Linux baseline after `b867e452`: `2969 passed / 0 failed / 1 ignored`

PM assessment: source/test deploy blocker cleared; V094-only migration, Step 2 Phase 1b engine deploy/restart, and V095-only migration completed. Remaining gate is separate production liquidation revival authorization, which still requires AMD/source/config dispatch.

## §4 Cross-Commit Interaction Risk

1. V094 is now applied and the Phase 1b engine was rebuilt/restarted, so runtime can persist close-maker audit fields on subsequent fills.
2. V095 is now applied and fixes the liquidation table identity prerequisite. Current production subscription builders still exclude `allLiquidation*`, so V095 apply is not equivalent to liquidation revival.
3. W-AUDIT-8b Phase B rerun is data-coverage gated by `panel.funding_rates_panel >=7d`; it does not depend on V094/V095 deploy and can be scheduled independently once the gate opens.
4. Engine restart completed with `OPENCLAW_AUTO_MIGRATE=0`; V095 was applied manually later. Keep auto-migrate disabled for any future migration sequencing.
5. The initial cargo failure was a cross-commit readiness break because it invalidated the empirical regression baseline for the Phase 1b commit even though historical E4 closure was green. It is now remediated by `b867e452`, with Linux cargo green.
6. The C1 result is technical only. It validates corrected mapping and V095 idempotency evidence, but it does not authorize production topic revival.

## §5 Deploy Order Recommendation + Rationale

Current recommendation: **do not revive production liquidation yet**. V094, Phase 1b engine deploy/restart, and V095 are complete; production liquidation revival remains a separate later authorization step requiring AMD/source/config dispatch.

Conditional order:

1. **Preflight freeze**: confirm clean Linux worktree, expected commit, `OPENCLAW_AUTO_MIGRATE=0`, `OPENCLAW_ENABLE_PAPER=0`, and full Linux cargo baseline green.
2. **V094 first**: completed. Rationale: V094 enables close-maker audit fields required for Phase 1b observation and was isolated from V095.
3. **Phase 1b runtime deploy/restart**: completed after explicit engine restart authorization. Rationale: runtime writes become meaningful only after the schema exists.
4. **V095 second**: completed after separate authorization. Rationale: identity correction is prepared but still does not revive production liquidation subscriptions.
5. **W-AUDIT-8b Phase B rerun in parallel once eligible**: wait for panel `>=7d`, then run the read-only Phase B report. Rationale: independent data-analysis gate, not a runtime deploy gate.
6. **Liquidation revival last**: separate AMD/dispatch/authorization for production `allLiquidation*` subscriptions and writer path. Rationale: current source deliberately keeps production builders excluding those topics.

## §6 Operator Authorization Checklist（per step）

Each item below requires explicit operator authorization before execution.

### Step 0 — Preflight / blocker clearance

Operation: verify deploy baseline only; no mutation.

Linux commands:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && git rev-parse --short HEAD && git status --short && grep -E "^(OPENCLAW_AUTO_MIGRATE|OPENCLAW_ENABLE_PAPER)=" ~/BybitOpenClaw/secrets/environment_files/basic_system_services.env'
ssh trade-core 'bash -lc "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"'
```

Rollback path: none; read-only.

Expected verify:

- Worktree clean.
- `OPENCLAW_AUTO_MIGRATE=0`.
- `OPENCLAW_ENABLE_PAPER=0`.
- Cargo returns `0 failed`.

### Step 1 — V094 manual apply/register

Status: **completed on Linux** after explicit operator authorization. At this step boundary, V095 had not yet been applied; Step 3 later applied it.

Operation: apply V094 only and register `_sqlx_migrations.version=94`.

Linux command:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); mkdir -p /tmp/openclaw/migration_backups; ts=$(date -u +%Y%m%dT%H%M%SZ); pg_dump "$DB_URL" -t _sqlx_migrations > "/tmp/openclaw/migration_backups/_sqlx_migrations_pre_v094_${ts}.sql"; checksum=$(sha384sum sql/migrations/V094__fills_close_maker_audit.sql | awk "{print \$1}"); PGOPTIONS="-c lock_timeout=5s -c statement_timeout=120s" psql "$DB_URL" -v ON_ERROR_STOP=1 -f sql/migrations/V094__fills_close_maker_audit.sql; psql "$DB_URL" -v ON_ERROR_STOP=1 -c "INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (94, '\''fills close maker audit'\'', TRUE, decode('\''$checksum'\'', '\''hex'\''), -1) ON CONFLICT (version) DO NOTHING;"'
```

Rollback path:

- Before runtime writes: drop the V094-added constraints/indexes/columns and delete `_sqlx_migrations.version=94`.
- After runtime writes: prefer forward rollback by reverting binary/runtime behavior and leaving inert columns in place; do not drop populated audit columns without a data-retention decision.

Expected verify:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT version, success FROM _sqlx_migrations WHERE version=94;"; psql "$DB_URL" -At -c "SELECT column_name FROM information_schema.columns WHERE table_schema='\''trading'\'' AND table_name='\''fills'\'' AND column_name IN ('\''close_maker_attempt'\'','\''close_maker_fallback_reason'\'') ORDER BY column_name;"'
```

### Step 2 — Phase 1b engine deploy/restart

Status: **completed on Linux** after explicit operator authorization.

Operation: rebuild/restart engine on the approved source after V094 is present.

Linux command:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --engine-only --rebuild --keep-auth'
```

Rollback path:

- Record pre-deploy commit and service state before restart.
- Revert runtime binary to previous known-good commit and rerun the same engine-only restart command.
- Keep V094 schema columns unless a separate DB rollback is authorized.

Expected verify:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status'
```

Additional expected health:

- Engine alive and fresh snapshots under threshold.
- No unexpected paper enablement. Disabled paper snapshot is fresh, but `disabled=true` and `OPENCLAW_ENABLE_PAPER=0`.
- Close-maker audit fields begin populating only after fills occur.
- Check `[40]` may remain WARN until strategy edge recovers; it is not expected to flip solely from deploy.

Observed result:

- Rebuild completed with non-fatal warnings only.
- Engine stopped gracefully and restarted as PID `1035839`.
- Previous engine log archived at `/tmp/openclaw/engine_logs/engine-1779049036.log`.
- Watchdog post-check: engine alive; live/demo snapshots fresh; disabled paper snapshot fresh.
- V094 remained registered. At this step boundary, V095 had not yet been applied; Step 3 later applied it.
- `OPENCLAW_AUTO_MIGRATE=0` and `OPENCLAW_ENABLE_PAPER=0` remained unchanged.

### Step 3 — V095 manual apply/register

Status: **completed on Linux** after explicit operator authorization.

Operation: apply V095 only and register `_sqlx_migrations.version=95`; no production `allLiquidation*` revival.

Linux command:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); mkdir -p /tmp/openclaw/migration_backups; ts=$(date -u +%Y%m%dT%H%M%SZ); pg_dump "$DB_URL" -t _sqlx_migrations > "/tmp/openclaw/migration_backups/_sqlx_migrations_pre_v095_${ts}.sql"; checksum=$(sha384sum sql/migrations/V095__market_liquidations_identity.sql | awk "{print \$1}"); PGOPTIONS="-c lock_timeout=5s -c statement_timeout=120s" psql "$DB_URL" -v ON_ERROR_STOP=1 -f sql/migrations/V095__market_liquidations_identity.sql; psql "$DB_URL" -v ON_ERROR_STOP=1 -c "INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (95, '\''market liquidations identity'\'', TRUE, decode('\''$checksum'\'', '\''hex'\''), -1) ON CONFLICT (version) DO NOTHING;"'
```

Rollback path:

- Before production liquidation writer revival: restore old PK shape and delete `_sqlx_migrations.version=95` if rollback is explicitly authorized.
- After any writer/revival: do not restore the lossy old PK; forward rollback by disabling writer/topic and leaving schema in place.

Expected verify:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT version, success FROM _sqlx_migrations WHERE version=95;"; psql "$DB_URL" -At -c "SELECT array_to_string(array_agg(a.attname ORDER BY array_position(i.indkey,a.attnum)), chr(44)) FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid='\''market.liquidations'\''::regclass AND i.indisprimary;"'
```

Expected PK: `symbol,ts,side,qty,price`.

Observed result:

- Preflight target-PK risk checks passed: no rows, nulls, duplicates, or invalid side values.
- V095 added `chk_market_liquidations_side_v095` as `NOT VALID`.
- V095 replaced old lossy PK `(symbol, ts, side)` with item-level PK `(symbol, ts, side, qty, price)`.
- Registry inserted version `95` with checksum `e25f110594587cddafd1e08f7699da593fe63c64af6d26415356c00b4534d8f60f0e67d7640ab8a6b18ba6ba742ca15b`.
- Engine was not restarted and runtime/config was not changed.

### Step 4 — W-AUDIT-8b Phase B rerun

Operation: read-only Stage 0R Round 2 Phase B rerun after panel coverage reaches `>=7d`.

Linux commands:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000.0)-to_timestamp(MIN(snapshot_ts_ms)/1000.0)))/86400 FROM panel.funding_rates_panel;"'
ssh trade-core 'cd ~/BybitOpenClaw/srv && export OPENCLAW_DATABASE_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url) && python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py --window-days 7 --sweep --format json --out /tmp/openclaw/funding_skew_stage0r_round2_$(date -u +%Y%m%dT%H%M%SZ).json'
```

Rollback path: none for DB/runtime; output file can be archived or ignored.

Expected verify:

- Panel days `>=7.0`.
- Report JSON exists.
- QC/MIT/BB review can evaluate Phase B result.
- No strategy/risk/runtime/paper/live mutation.

### Step 5 — Production liquidation revival

Operation: enable production `allLiquidation*` subscription/writer path.

Linux command: **not provided for immediate use**. This requires a separate AMD/source/config dispatch and explicit operator authorization after V095 is applied and verified.

Rollback path:

- Disable the production subscription/writer path.
- Keep V095 schema unless a separate data-retention rollback is authorized.

Expected verify:

- Production builders intentionally include the approved `allLiquidation*` topics.
- Parser/writer fail-closed behavior remains active.
- No duplicate/overwrite collapse under corrected PK.
- C1 side mapping remains `Buy = long liquidation`, `Sell = short liquidation`.

## §7 3-Gate Status Update

| Gate | Current status | Evidence | PM state |
|---|---|---|---|
| `P0-EDGE-1` / `[40]` | WARN active | Direct healthcheck module query: `avg_net=-0.00bps <= target`, rows `53830`, maker-like `96.5%`, fee-drop `95.7%` | Not cleared. Deploying Phase 1b may improve execution-quality observability, but does not itself prove alpha recovery. |
| W-AUDIT-8b Stage 0R | Round 1 RED; Phase B pending | Panel coverage `6.8566833564814815d` | Do not tombstone. Rerun only after `>=7d` panel gate. |
| W-AUDIT-8a C1 | Technical PASS | `82ab71eb` PM C1 final signoff; MIT/BB conditions summarized; V095 now applied | Production revival remains blocked pending separate AMD/source/config dispatch and explicit operator authorization. |

## §8 P1/P2 Backlog Status（W-AUDIT-8b Phase B / phys_lock AMD / Phase 1b deploy）

- **W-AUDIT-8b Phase B**: pending panel `>=7d`; currently `6.8566833564814815d`. This remains an active P1/P2 analytical gate and can proceed independently once eligible.
- **phys_lock AMD / literal guard remediation**: completed by `b867e452`; Linux full lib baseline is `2969 passed / 0 failed / 1 ignored`.
- **Phase 1b deploy**: completed after V094 apply; close-maker audit fields can populate on subsequent fills.
- **V095 / liquidation correction**: completed after separate explicit authorization. V095 does not revive production liquidation subscriptions.
- **Production liquidation revival**: still blocked and intentionally excluded from immediate deploy plan. Requires separate AMD/PM dispatch and operator authorization.

## §9 PM Verdict（READY-TO-AUTHORIZE / NEEDS-WORK / BLOCKED）

**STEP 3 V095 APPLIED; PRODUCTION LIQUIDATION REVIVAL STILL BLOCKED**.

Reason:

1. Source commits are landed and workspace reports broadly cover the expected role chain, with noted artifact-hygiene gaps.
2. Linux runtime is stable after restart. V094 and V095 are applied; check `[40]` remains WARN.
3. The current Linux cargo regression baseline is green after `b867e452`: `2969 passed / 0 failed / 1 ignored`.
4. Production liquidation revival remains blocked; V095 schema readiness is not topic revival.

PM authorization condition:

- Any production `allLiquidation*` revival must be separately authorized and must include AMD/source/config dispatch.
- Do not bundle production subscription revival with unrelated risk/runtime config changes.
- Keep W-AUDIT-8b Phase B pending until panel coverage reaches `>=7d`.

No production liquidation revival or risk/runtime config mutation was executed as part of Step 3.
