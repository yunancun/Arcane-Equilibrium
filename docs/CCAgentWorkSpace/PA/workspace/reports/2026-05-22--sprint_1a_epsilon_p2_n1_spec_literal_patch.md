---
report: PA Sprint 1A-ε P2 N1 spec literal patch — `cargo run --bin sqlx_migrate` not a real binary
date: 2026-05-22
author: PA Project Architect
phase: Sprint 1A-ε P2 N1 carry-over from Sprint 1A-ε P1 E3 push back
status: PASS（patch landed, Sprint 1B E1 carry-over noted, 不 commit）
trigger:
  - E3 P1 report §4.1 + §7.2 推 PA + QA spec literal patch
  - `srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--sprint_1a_epsilon_sandbox_admin_role.md`
scope: 字面 patch 4 個 spec doc，不寫 binary、不改 V### SQL、不 commit
SLA: 15-20 min single-thread
---

# PA Sprint 1A-ε P2 N1 — spec literal `sqlx_migrate` patch report

## §1 grep hit list（spec literal `sqlx_migrate`）

### 1.1 Target 4 spec docs（per task scope）

| File | Line | Original literal | 性質 |
|---|---|---|---|
| `docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` | 274 | `cargo run --release --bin sqlx_migrate -- run` | **誤導**（binary 不存在）→ **patch** |
| `docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` | 910 | `cargo run --release --bin repair_migration_checksum -- --version 106` | **真實 binary** ✅ → 不 patch |
| `docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md` | 1284 | `cargo run --release --bin repair_migration_checksum -- --version 107` | **真實 binary** ✅ → 不 patch |
| `docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` | 1157 | `cargo run --release --bin repair_migration_checksum -- --version 112` | **真實 binary** ✅ → 不 patch |

**結論**：4 個 spec doc 中**僅 1 處** spec literal 需 patch（spike scope spec AC-2 line 274）。V106/V107/V112 引用的 `repair_migration_checksum` 是 Cargo workspace 內 **真實 binary**（per `rust/openclaw_engine/Cargo.toml` + `src/bin/repair_migration_checksum.rs`），不誤導。

### 1.2 旁證 reports（task scope 外，記錄供 PM 知悉）

| File | Line | Literal | 動作 |
|---|---|---|---|
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md` | 32, 48, 69 | `cargo sqlx_migrate run` / `sqlx_migrate run path` | 歷史 sign-off 報告，**不修**（report 是時點記錄；以本 patch report 為更正） |
| `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3c_qa_empirical_verify.md` | 64, 76, 427, 480, 515 | `cargo run --release --bin sqlx_migrate -- run` 等 | 歷史 QA 報告，**不修**（report 是時點記錄；以本 patch report 為更正） |

**理由**：歷史 sign-off / audit report 是時點快照，不應 retroactive 改寫；本 patch report 作為更正記錄供 Sprint 1B 引用。task scope 限定 spec doc，無 sign-off review/edit 報告的授權。

## §2 Cargo workspace binary reality（empirical）

### 2.1 `rust/openclaw_engine/Cargo.toml` 真實 binary list（5 個）

| `[[bin]]` name | 用途 |
|---|---|
| `openclaw-engine` | 主 engine binary（內嵌 `MigrationRunner::run_if_enabled` per `src/main.rs:633-650`）|
| `repair_migration_checksum` | sqlx checksum drift 修補（V055 + 2026-05-02 incident 治本工具） |
| `feature_baseline_writer` | ML 訓練 baseline writer |
| `replay_runner` | Replay harness |
| `hot_path_baseline` / `intent_processor_exposure` | bench / debug tooling（Cargo.toml 額外 declared） |

### 2.2 `sqlx_migrate` standalone binary

**不存在**。Cargo workspace 全 5 個 binary 均不叫 `sqlx_migrate`，也無 sandbox 專用 migration runner binary。

`src/bin/` 文件列表 empirical 確認：
```
feature_baseline_writer.rs
repair_migration_checksum.rs
replay_runner/ (dir)
replay_runner.rs
```
+ `openclaw-engine` 由 `src/main.rs` declared（`[[bin]] name = "openclaw-engine"`）。

## §3 MigrationRunner real path（production migration entry）

### 3.1 入口 callsite

`rust/openclaw_engine/src/main.rs:633-650`（engine startup block）：

```rust
{
    let base_dir = std::env::var("OPENCLAW_BASE_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("."));
    match openclaw_engine::database::migrations::MigrationRunner::run_if_enabled(
        db_pool.get(),
        &base_dir,
    )
    .await
    {
        Ok(outcome) => info!(?outcome, "auto_migrate runner completed / 自動遷移執行器已完成"),
        Err(e) => {
            error!(error = %e, ...);
            // engine startup aborts on Err (silent-noop class loudly surfaced)
        }
    }
}
```

### 3.2 Runner impl

`rust/openclaw_engine/src/database/migrations.rs:140-152`：

```rust
pub async fn run_if_enabled(
    pool: Option<&PgPool>,
    base_dir: &Path,
) -> Result<RunOutcome, MigrationsError> {
    let enabled = std::env::var(AUTO_MIGRATE_ENV_VAR).ok().as_deref() == Some("1");
    if !enabled {
        info!(env_var = AUTO_MIGRATE_ENV_VAR,
            "auto_migrate disabled — set OPENCLAW_AUTO_MIGRATE=1 to enable");
        return Ok(RunOutcome::Disabled);
    }
    // ... run sql/migrations/V*.sql + write _sqlx_migrations
}
```

### 3.3 Env trigger

- **Env var**：`OPENCLAW_AUTO_MIGRATE=1`（const `AUTO_MIGRATE_ENV_VAR` per `migrations.rs:44`）
- **預設**：OFF（per 2026-04-24 V023 silent-noop postmortem，opt-in）
- **DB-less degraded path**：`OPENCLAW_ALLOW_DBLESS=1`（per `migrations.rs:154-160`，DbPool 未連時允許降級啟動）
- **失敗行為**：返回 `Err(MigrationsError)`，engine startup **abort**（loud-fail by design）

### 3.4 Production migration path（trading_ai）

```bash
# engine startup time auto-migrate（production）
OPENCLAW_AUTO_MIGRATE=1 bash helper_scripts/restart_all.sh --rebuild
# 由 main.rs:633 內嵌 runner 跑 sql/migrations/V*.sql + 寫 _sqlx_migrations
```

### 3.5 Sandbox migration path（trading_ai_sandbox）

**目前狀態（Sprint 1A-ε P1 結束時）**：
- Sandbox 走 `psql -f sql/migrations/V###__*.sql` raw apply（**不**寫 `_sqlx_migrations` 註冊表 — 即 QA Phase 3c AC-1 RCA 揭露的 root cause）
- Sandbox standalone CLI binary **缺**（Sprint 1B E1 carry-over）

**Sprint 1B 兩條路徑（per E3 P1 §4.3）**：
- **Path A**（推薦）：Sprint 1B 啟動獨立 sandbox engine instance + `--dry-run-migrations-only` flag（需 E1 確認 / 加 flag）
- **Path B**（後備）：E1 新建 `sandbox_migrate_runner` binary（1-2 hr E1 + 1 hr E2 review）

## §4 Patch applied

### 4.1 唯一 patch

**File**：`docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`
**Line**：274
**AC**：AC-2（V### Round 1 + Round 2 idempotency）

**Before**（誤導 — `sqlx_migrate` standalone binary 不存在）：
```markdown
| **AC-2** | **三 V### Round 1 + Round 2 idempotency 跑 0 RAISE** | 第二次跑 `cargo run --release --bin sqlx_migrate -- run` 必 0 RAISE；對齊 V103/V104 dry-run 範式 | QA |
```

**After**（真實 path Option 1 推薦 + Option 2 Sprint 1B E1 carry-over）：
```markdown
| **AC-2** | **三 V### Round 1 + Round 2 idempotency 跑 0 RAISE** | 第二次跑必 0 RAISE；對齊 V103/V104 dry-run 範式。**Apply path（per 2026-05-22 E3 Sprint 1A-ε P1 push back — `sqlx_migrate` standalone binary 不存在）**：Option 1（推薦）engine startup auto-migrate — `OPENCLAW_AUTO_MIGRATE=1 bash helper_scripts/restart_all.sh --rebuild`，由 `rust/openclaw_engine/src/main.rs:633-650` 內嵌 `MigrationRunner::run_if_enabled()` 跑 `sql/migrations/V*.sql` 並寫 `_sqlx_migrations`；Option 2（sandbox standalone CLI 仍缺）目前 sandbox V### apply 走 `psql -f sql/migrations/V###__*.sql`（**不**寫 `_sqlx_migrations` 註冊表 — Sprint 1B E1 carry-over 新建 `sandbox_migrate_runner` bin 收口）。Round 2 idempotency 驗用 Option 1 第二次 `restart_all.sh --rebuild` 或在 sandbox engine instance（path A per E3 §4.3）執行。| QA |
```

**Diff stats**：
- 1 file modified
- 1 line replaced（單表格 cell）
- 0 binary 改動 / 0 V### SQL 改動 / 0 commit（task scope 限定）

### 4.2 Post-patch verification

```bash
$ grep -n "sqlx_migrate" docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
274:| **AC-2** | ... `sqlx_migrate` standalone binary 不存在 ... |
```

剩 1 處字面 `sqlx_migrate` 出現在 **explicit push-back reference 語境**內（明確說明 binary 不存在），對 reader 不誤導。

## §5 Sprint 1B E1 carry-over（重申）

| Track | Owner | Estimate | Trigger |
|---|---|---|---|
| 新建 `rust/openclaw_engine/src/bin/sandbox_migrate_runner.rs`（path B）| E1 | 1-2 hr IMPL | Sprint 1B 第一個 Track（沙箱 V### re-apply 正式化）|
| E2 對抗 review path B binary（與 engine migration runner 算法同源驗證）| E2 | 1 hr review | path B IMPL 完 |
| OR `openclaw-engine --dry-run-migrations-only` flag（path A）| E1 | 0.5-1 hr | 若 PM 決定走 path A 而非 path B |

**E3 推薦**：path B（standalone binary）— 與 production engine 解耦，避免 sandbox migration 邏輯依賴 engine startup 完整路徑（cost_edge_advisor / strategy / risk 等 dep 無 sandbox 場景必要）。

## §6 §16 根原則合規檢查（patch 動作）

| # | 原則 | 證據 |
|---|---|---|
| 8 | 交易可解釋 / audit traceability | spec patch 明確指出 `MigrationRunner::run_if_enabled` 真實 callsite + env trigger → 後續 audit 可追 |
| 10 | 認知誠實 | 區分「真實 binary（repair_migration_checksum）」vs「不存在 binary（sqlx_migrate）」事實 |
| 14 | 零外部成本可運行 | path A（engine startup）無新依賴，與現有 `restart_all.sh --rebuild` 流程一致 |

**硬邊界**：本 patch 不觸碰任何硬邊界（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json / decision_lease）。

**3E-ARCH 合規**：Sprint 1A-ζ spike 場景限 sandbox（trading_ai_sandbox DB），與 production trading_ai 隔離；P1 E3 已驗 sandbox_admin role attacker fence（5/6 attack vector PASS，1 MED finding pg_hba.conf carry-over）。

## §7 Verdict

**PASS**

| Acceptance | Status |
|---|---|
| Step 1: grep 4 spec doc spec literal hits 確認 | ✅ 1 真實 hit（AC-2 line 274）+ 3 false-positive（V### spec 用真實 `repair_migration_checksum` bin）|
| Step 2: Cargo workspace binary list empirical | ✅ 5 binary（openclaw-engine / repair_migration_checksum / feature_baseline_writer / replay_runner / hot_path_baseline+intent_processor_exposure）；**0 sqlx_migrate** |
| Step 3: MigrationRunner real path | ✅ `src/main.rs:633-650` + `database/migrations.rs:140` + `OPENCLAW_AUTO_MIGRATE=1` env |
| Step 4: Spec literal patch | ✅ 1 patch landed（spike scope spec AC-2 line 274）|
| Step 5: Patch report write | ✅ 本報告 |
| Constraint: 不寫新 binary | ✅（Sprint 1B E1 carry-over 記錄）|
| Constraint: 不改 V106/V107/V112 SQL | ✅（V### spec 引用 `repair_migration_checksum` 是真實 binary，不需 patch）|
| Constraint: 不 commit | ✅ |
| Constraint: 不派下游 sub-agent | ✅（single-thread PA execution）|

**SLA**：~15 min 完成（task scope 預期 15-20 min）。

---

## §8 Sign-off

- **PA Project Architect** 簽收 Sprint 1A-ε P2 N1 spec literal patch
- **Verdict**：PASS（單 patch landed，0 commit per task constraint）
- **下一步**：
  1. PM 收 PA 報告 + E3 P1 報告，決定 Sprint 1B Track 排序（path A vs path B）
  2. Sprint 1B Phase 1 E1 wave：新建 `sandbox_migrate_runner` bin（path B）OR 加 `--dry-run-migrations-only` flag（path A）
  3. （獨立）Sprint 1A-ε P2 N2+：[E3-MED-1] pg_hba.conf hardening（per E3 P1 §7.1 carry-over）

---

**END OF Sprint 1A-ε P2 N1 spec literal patch report**
