//! Auto-migration runner — opt-in Flyway-style V###__*.sql apply on engine start.
//! 啟動自動遷移執行器 — opt-in 套用 Flyway 風格 V###__*.sql。
//!
//! MODULE_NOTE (EN): Replaces manual `psql < V*.sql` workflow that caused the
//!   V023/V019/V021 silent-noop postmortem (2026-04-24). Gated behind env var
//!   `OPENCLAW_AUTO_MIGRATE=1` so the default engine start remains identical to
//!   today — operator opts in explicitly once comfortable. When enabled:
//!     1. Seeds `_sqlx_migrations` with already-applied V001-V023 rows if (a)
//!        the table is empty AND (b) a canary schema object proves those
//!        migrations already ran via the legacy manual path. Operator gets a
//!        hard error otherwise (ambiguous state — refuse to guess).
//!     2. Uses a hand-rolled `Migrator` because sqlx's built-in directory
//!        parser rejects `V###__*.sql` (expects pure `<i64>_<desc>.sql`). Files
//!        V017_rollback.sql (rollback fixture) and V999__exit_features.sql
//!        (test fixture) are filtered out by pattern.
//!     3. Runs pending migrations via `Migrator::run_direct`; success adds rows
//!        to `_sqlx_migrations` with matching checksums.
//!
//! MODULE_NOTE (中): 取代舊有手動 `psql < V*.sql` 流程（見 2026-04-24
//!   V023/V019/V021 silent-noop postmortem）。預設關閉，由 `OPENCLAW_AUTO_MIGRATE=1`
//!   opt-in 開啟，engine 啟動行為與今天一致，直到 operator 信任後自行開啟。
//!   啟用後：
//!     1. 若 `_sqlx_migrations` 為空且 canary schema 物件證明 V001-V023 已走
//!        legacy 手動路徑套用，則 seed `_sqlx_migrations`；不符則硬性報錯，
//!        拒絕在曖昧狀態下猜測。
//!     2. 自刻 `Migrator`（不用 `sqlx::migrate!` macro），因 sqlx 內建目錄
//!        parser 不認 `V###__*.sql`（要求純整數 `<i64>_<desc>.sql`）。
//!        V017_rollback.sql（rollback）與 V999__exit_features.sql（測試 fixture）
//!        依檔名過濾。
//!     3. 經 `Migrator::run_direct` 套用 pending；成功後 checksums 寫入
//!        `_sqlx_migrations`。

use sqlx::migrate::{Migration, MigrationType, Migrator};
use sqlx::postgres::PgPool;
use sqlx::{Executor, Row};
use std::borrow::Cow;
use std::path::{Path, PathBuf};
use std::time::Instant;
use tracing::{debug, error, info, warn};

/// Env var gating auto-migrate behaviour. Default OFF to preserve today's
/// manual-apply workflow; flip to "1" once operator has validated one trial.
/// 控制自動遷移的環境變數。預設關，經 operator 首輪驗證後再打開。
pub const AUTO_MIGRATE_ENV_VAR: &str = "OPENCLAW_AUTO_MIGRATE";

/// Relative path (from `$OPENCLAW_BASE_DIR` or CWD) to the migrations directory.
/// 相對於 `$OPENCLAW_BASE_DIR` 或 CWD 的 migrations 目錄。
pub const MIGRATIONS_DIR_REL: &str = "sql/migrations";

/// Highest migration version already known to be manually applied (per
/// 2026-04-24 postmortem state). Used by `ensure_legacy_seeded` as the set of
/// rows to seed when `_sqlx_migrations` is empty.
/// 截至 2026-04-24 postmortem 已手動套用的最高版本。`_sqlx_migrations` 空
/// 且 canary 成立時 seed 到此版本為止（含 gap）。
const LEGACY_APPLIED_MAX_VERSION: i64 = 23;

/// Errors surfaced from the migration runner.
/// 遷移執行器的錯誤型別。
#[derive(thiserror::Error, Debug)]
pub enum MigrationsError {
    #[error("migrations directory not found: {0}")]
    DirNotFound(PathBuf),
    #[error("I/O error reading migration {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to parse migration filename {name:?}: {reason}")]
    FilenameParse { name: String, reason: String },
    #[error("sqlx migrate error: {0}")]
    Sqlx(#[from] sqlx::migrate::MigrateError),
    #[error("sqlx query error: {0}")]
    Query(#[from] sqlx::Error),
    #[error(
        "legacy seed refused — _sqlx_migrations is empty BUT canary check did not \
         confirm V001-V023 already applied. Manual triage required: either apply \
         missing migrations with `bash helper_scripts/linux_bootstrap_db.sh --apply` \
         or run `helper_scripts/db/audit_migrations.py` to inventory DB state before \
         setting OPENCLAW_AUTO_MIGRATE=1. \
         / legacy seed 拒絕 — _sqlx_migrations 空但 canary 未證實 V001-V023 已套用。\
         請先手動 bootstrap 或 audit 後再開啟 OPENCLAW_AUTO_MIGRATE。"
    )]
    LegacySeedRefused,
    #[error(
        "legacy seed consistency check failed — partial _sqlx_migrations rows found \
         (count={existing}/expected>={expected}). Refusing to auto-complete. Operator \
         must investigate manually. \
         / legacy seed 一致性檢查失敗 — _sqlx_migrations 已有 {existing} 行（預期 \
         ≥{expected}），拒絕自動補齊，須人工介入。"
    )]
    LegacyPartialState { existing: i64, expected: i64 },
}

/// Result of a `MigrationRunner::run_if_enabled` call.
/// `MigrationRunner::run_if_enabled` 的結果。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RunOutcome {
    /// Env var not set to "1" — runner skipped. / 未 opt-in，跳過。
    Disabled,
    /// Pool is disconnected — nothing to do (matches optional-DB story).
    /// 資料庫未連接 — 無動作（與可選 DB 政策一致）。
    NoPool,
    /// Ran migrator; no new migrations applied (idempotent run).
    /// 已執行 migrator；無新遷移套用（冪等）。
    NoOp,
    /// Ran migrator; applied `n` new migrations. / 成功套用 `n` 筆新遷移。
    Applied(usize),
    /// Seeded `_sqlx_migrations` with legacy rows (V001-V023) then ran
    /// migrator. `seeded` = rows inserted, `applied` = new migrations beyond.
    /// 先 seed 舊 migrations 再跑 migrator。`seeded` 為 seed 行數，
    /// `applied` 為新套用筆數。
    SeededAndApplied { seeded: usize, applied: usize },
}

/// Entry point for the auto-migration runner.
/// 自動遷移執行器的入口。
pub struct MigrationRunner;

impl MigrationRunner {
    /// Run auto-migrations if `OPENCLAW_AUTO_MIGRATE=1`; otherwise no-op.
    ///
    /// Called from startup AFTER the DbPool has connected and BEFORE any writer
    /// task that depends on a specific schema revision. On migrate error the
    /// function returns `Err` — caller decides whether to abort startup (strict)
    /// or log and continue (lenient). Current wiring aborts startup on Err to
    /// surface the silent-noop class of bugs loudly.
    ///
    /// 若 `OPENCLAW_AUTO_MIGRATE=1` 則跑自動遷移，否則 no-op。
    /// 由 startup 在 DbPool 連上後、依賴特定 schema 的 writer 啟動前呼叫。
    /// 遷移錯時回傳 `Err`，目前接線會讓 engine 中止啟動以明示問題。
    pub async fn run_if_enabled(
        pool: Option<&PgPool>,
        base_dir: &Path,
    ) -> Result<RunOutcome, MigrationsError> {
        let enabled = std::env::var(AUTO_MIGRATE_ENV_VAR).ok().as_deref() == Some("1");
        if !enabled {
            info!(
                env_var = AUTO_MIGRATE_ENV_VAR,
                "auto_migrate disabled — set OPENCLAW_AUTO_MIGRATE=1 to enable \
                 / 自動遷移未啟用，設定 OPENCLAW_AUTO_MIGRATE=1 開啟"
            );
            return Ok(RunOutcome::Disabled);
        }
        let Some(pool) = pool else {
            warn!(
                "auto_migrate enabled but DbPool disconnected — skipping \
                 / 已開 auto_migrate 但 DbPool 未連接，跳過"
            );
            return Ok(RunOutcome::NoPool);
        };

        let migrations_dir = base_dir.join(MIGRATIONS_DIR_REL);
        if !migrations_dir.is_dir() {
            return Err(MigrationsError::DirNotFound(migrations_dir));
        }
        info!(
            path = %migrations_dir.display(),
            "auto_migrate: loading migrations / 自動遷移：載入遷移檔"
        );

        let migrations = load_migrations_from_dir(&migrations_dir)?;
        info!(
            count = migrations.len(),
            versions = ?migrations.iter().map(|m| m.version).collect::<Vec<_>>(),
            "auto_migrate: migrations parsed / 自動遷移：遷移檔已解析"
        );

        let migrator = build_migrator(migrations.clone());

        // Seed legacy rows first (if applicable), so the subsequent
        // `migrator.run_direct` treats them as already applied and skips to the
        // real pending list (empty today, but V024+ in the future).
        // 先 seed 舊行（必要時），讓後續 run_direct 視為已套用，直接跳到真正
        // 的 pending（目前無，未來 V024+ 才會有）。
        let seeded = ensure_legacy_seeded(pool, &migrations).await?;

        // Count rows before/after to report `applied` count truthfully.
        // 用 row count 差值回報實際套用數量。
        let before = count_applied_rows(pool).await?;
        let t0 = Instant::now();
        migrator.run(pool).await?;
        let after = count_applied_rows(pool).await?;
        let applied = (after - before).max(0) as usize;

        info!(
            seeded = seeded,
            applied = applied,
            elapsed_ms = t0.elapsed().as_millis() as u64,
            "auto_migrate: completed / 自動遷移：完成"
        );

        Ok(match (seeded, applied) {
            (0, 0) => RunOutcome::NoOp,
            (0, n) => RunOutcome::Applied(n),
            (s, n) => RunOutcome::SeededAndApplied {
                seeded: s,
                applied: n,
            },
        })
    }
}

/// Parse a filename of the form `V###__<desc>.sql` into (version, description).
/// Returns `Err(FilenameParse)` on malformed input. Callers filter non-matching
/// files before calling this; it is strict on shape.
///
/// 解析 `V###__<desc>.sql` 檔名為 (version, description)。
/// 呼叫者先過濾不符合的檔案；本函式對形狀嚴格。
fn parse_flyway_filename(file_name: &str) -> Result<(i64, String), MigrationsError> {
    let stem = file_name.strip_suffix(".sql").ok_or_else(|| {
        MigrationsError::FilenameParse {
            name: file_name.to_string(),
            reason: "missing .sql suffix / 無 .sql 後綴".into(),
        }
    })?;

    // Must start with 'V' / 必須以 V 開頭
    let rest = stem.strip_prefix('V').ok_or_else(|| MigrationsError::FilenameParse {
        name: file_name.to_string(),
        reason: "missing V prefix / 無 V 前綴".into(),
    })?;

    // Split on "__" / 以雙底線分段
    let (version_str, desc) = rest.split_once("__").ok_or_else(|| {
        MigrationsError::FilenameParse {
            name: file_name.to_string(),
            reason: "missing double-underscore separator / 無雙底線分隔".into(),
        }
    })?;

    let version: i64 = version_str
        .parse()
        .map_err(|e: std::num::ParseIntError| MigrationsError::FilenameParse {
            name: file_name.to_string(),
            reason: format!("version prefix not i64 / 版本非整數: {e}"),
        })?;

    if version <= 0 {
        return Err(MigrationsError::FilenameParse {
            name: file_name.to_string(),
            reason: "version must be > 0 / 版本需 > 0".into(),
        });
    }

    Ok((version, desc.replace('_', " ")))
}

/// Decide whether a directory entry is a valid Flyway migration we should apply.
/// Rejects rollback fixtures (`V###_rollback.sql` — single underscore) and the
/// test-only `V999__*.sql` sentinel used for in-memory fixture loading.
///
/// 判斷目錄項是否為有效 Flyway 遷移。過濾 rollback fixture（單底線版本別）
/// 與測試用 V999 sentinel。
fn is_eligible_migration_file(file_name: &str) -> bool {
    // Must be .sql / 必須 .sql
    if !file_name.ends_with(".sql") {
        return false;
    }
    // Must start with "V<digit>" / 起手 V + 數字
    if !file_name.starts_with('V') || !file_name[1..].chars().next().is_some_and(|c| c.is_ascii_digit())
    {
        return false;
    }
    // Reject V999 test fixture / 拒絕 V999 測試 fixture
    if file_name.starts_with("V999") {
        return false;
    }
    // Reject rollback fixtures (single underscore between digits and word).
    // 拒絕 rollback fixture（單底線分隔版本與說明）。
    // Only accept double-underscore form "V###__desc.sql".
    // 僅接受雙底線格式「V###__desc.sql」。
    let Some(stem) = file_name.strip_suffix(".sql") else {
        return false;
    };
    let Some(rest) = stem.strip_prefix('V') else {
        return false;
    };
    rest.contains("__")
        && rest
            .split_once("__")
            .is_some_and(|(v, _)| v.parse::<i64>().is_ok())
}

/// Read the migrations directory, filter eligible files, and build a sorted
/// `Vec<Migration>`. Fatal on filename-parse errors of an *eligible* file.
///
/// 讀目錄、過濾、建構排序後的 `Vec<Migration>`。合規檔解析失敗即中止。
pub fn load_migrations_from_dir(dir: &Path) -> Result<Vec<Migration>, MigrationsError> {
    let mut out: Vec<Migration> = Vec::new();
    let entries = std::fs::read_dir(dir).map_err(|source| MigrationsError::Io {
        path: dir.to_path_buf(),
        source,
    })?;
    for entry in entries {
        let entry = entry.map_err(|source| MigrationsError::Io {
            path: dir.to_path_buf(),
            source,
        })?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Some(fname) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if !is_eligible_migration_file(fname) {
            debug!(file = fname, "auto_migrate: skipping non-eligible / 略過非合規檔");
            continue;
        }
        let (version, description) = parse_flyway_filename(fname)?;
        let sql = std::fs::read_to_string(&path).map_err(|source| MigrationsError::Io {
            path: path.clone(),
            source,
        })?;
        let no_tx = sql.starts_with("-- no-transaction");
        let m = Migration::new(
            version,
            Cow::Owned(description),
            MigrationType::Simple,
            Cow::Owned(sql),
            no_tx,
        );
        out.push(m);
    }
    out.sort_by_key(|m| m.version);

    // Detect duplicate versions up front (migration file rename accidents).
    // 預檢版本重複（重命名事故）。
    for pair in out.windows(2) {
        if pair[0].version == pair[1].version {
            return Err(MigrationsError::FilenameParse {
                name: format!("V{:03}__*.sql (multiple)", pair[0].version),
                reason: format!(
                    "duplicate version {} after filtering / 過濾後版本仍重複 {}",
                    pair[0].version, pair[0].version
                ),
            });
        }
    }
    Ok(out)
}

/// Assemble a sqlx `Migrator` with our hand-parsed migrations.
/// 用手動解析的 migration 組 `Migrator`。
pub fn build_migrator(migrations: Vec<Migration>) -> Migrator {
    Migrator {
        migrations: Cow::Owned(migrations),
        // We do NOT want to silently ignore applied-but-absent entries (defence
        // against accidental file deletion). Default = false = strict.
        // 絕不靜默忽略已套用但本地缺失的遷移（防止意外刪檔）。
        ignore_missing: false,
        // Locking uses pg_advisory_lock; safe for our single-engine cold-start
        // (no concurrent migrators running).
        // 用 pg_advisory_lock；單引擎冷啟動安全。
        locking: true,
        // Default: every migration wrapped in a tx unless file starts with
        // `-- no-transaction`. Matches current migration files.
        // 預設 tx 包裹，除非檔首為 `-- no-transaction`。
        no_tx: false,
    }
}

/// Read `_sqlx_migrations` row count. Returns 0 when the table does not yet
/// exist (a fresh DB case).
/// 讀 `_sqlx_migrations` 行數。表不存在時（全新庫）回 0。
async fn count_applied_rows(pool: &PgPool) -> Result<i64, MigrationsError> {
    let exists: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables \
         WHERE table_schema = 'public' AND table_name = '_sqlx_migrations')",
    )
    .fetch_optional(pool)
    .await?;
    if !exists.unwrap_or(false) {
        return Ok(0);
    }
    let row = sqlx::query("SELECT COUNT(*)::BIGINT AS n FROM public._sqlx_migrations")
        .fetch_one(pool)
        .await?;
    Ok(row.try_get::<i64, _>("n")?)
}

/// Canary: does `learning.model_registry` (introduced in V023) exist?
/// True → V023 has already run via the legacy manual path, which implies
/// V001-V022 also ran (migrations are sequential and V023 CREATEs tables in
/// the `learning` schema introduced in V001 / expanded in V004).
/// 回傳 V023 是否已由手動路徑套用；真時代表 V001-V022 亦然（逐號套用）。
async fn canary_v023_applied(pool: &PgPool) -> Result<bool, MigrationsError> {
    let exists: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables \
         WHERE table_schema = 'learning' AND table_name = 'model_registry')",
    )
    .fetch_optional(pool)
    .await?;
    Ok(exists.unwrap_or(false))
}

/// Seed legacy `_sqlx_migrations` rows for V001-V023 if the DB is in the
/// "manual-applied, never tracked" state from the 2026-04-24 postmortem.
///
/// Returns the count of rows seeded (0 when not applicable). Errors when state
/// is ambiguous (partial rows, or canary fails).
///
/// 在 2026-04-24 postmortem 狀態下 seed V001-V023 到 `_sqlx_migrations`。
/// 回傳 seed 行數（不適用時 0）。曖昧狀態（部分列或 canary 失敗）即報錯。
pub async fn ensure_legacy_seeded(
    pool: &PgPool,
    migrations: &[Migration],
) -> Result<usize, MigrationsError> {
    // Make sure the tracking table exists (noop if it does).
    // 確保追蹤表存在（已存在則 noop）。
    pool.execute(
        r#"CREATE TABLE IF NOT EXISTS _sqlx_migrations (
            version BIGINT PRIMARY KEY,
            description TEXT NOT NULL,
            installed_on TIMESTAMPTZ NOT NULL DEFAULT now(),
            success BOOLEAN NOT NULL,
            checksum BYTEA NOT NULL,
            execution_time BIGINT NOT NULL
        );"#,
    )
    .await?;

    let existing = count_applied_rows(pool).await?;
    if existing > 0 {
        // Table non-empty. Caller (Migrator::run) will validate checksum
        // alignment per-version; nothing to seed.
        // 非空，交給 Migrator 自行比對 checksum。
        debug!(
            existing,
            "auto_migrate: _sqlx_migrations non-empty, skipping seed / \
             _sqlx_migrations 非空，跳過 seed"
        );
        return Ok(0);
    }

    // Empty table. Decide between fresh-DB (run migrator normally) and
    // legacy-manual-applied state (seed V001-V023, then migrator is a no-op
    // through V023, plus any V024+).
    // 空表。決定是 fresh-DB（讓 migrator 正常跑）還是 legacy-manual
    // 狀態（seed V001-V023，migrator 到 V023 為 no-op，V024+ 自然跑）。
    let canary_ok = canary_v023_applied(pool).await?;
    if !canary_ok {
        // Could legitimately be a fresh DB (no schemas yet) — that is fine;
        // the upcoming migrator run will apply V001+. Return 0 (no seed).
        // But if there ARE schema tables but V023 canary missing, that is an
        // ambiguous partial state we refuse to touch.
        // 可能是全新 DB（無 schema），讓 migrator 跑 V001+；回 0。
        // 若已有 schema 物件但 canary 不成立 → 曖昧狀態，拒絕 seed。
        let schema_probe: Option<bool> = sqlx::query_scalar(
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata \
             WHERE schema_name IN ('learning','trading','market'))",
        )
        .fetch_optional(pool)
        .await?;
        if schema_probe.unwrap_or(false) {
            error!(
                "auto_migrate: ambiguous state — schemas present but V023 canary \
                 missing. Refusing to seed. \
                 / 曖昧狀態 — 已有 schema 但 V023 canary 不成立，拒絕 seed。"
            );
            return Err(MigrationsError::LegacySeedRefused);
        }
        info!(
            "auto_migrate: fresh DB detected (no learning.* / trading.* / market.* \
             schemas) — migrator will apply V001+ normally \
             / 全新 DB — migrator 將正常套用 V001+"
        );
        return Ok(0);
    }

    // Canary confirmed. Seed every known migration up to
    // LEGACY_APPLIED_MAX_VERSION with the computed checksums from the current
    // files. Any V024+ migration falls through to the normal apply path.
    // Canary 成立。依現檔 checksum seed 到 LEGACY_APPLIED_MAX_VERSION 為止，
    // V024+ 留給 migrator 正常套用。
    let mut seeded = 0usize;
    let mut tx = pool.begin().await?;
    for m in migrations {
        if m.version > LEGACY_APPLIED_MAX_VERSION {
            continue;
        }
        // `execution_time = -1` matches sqlx's own partial-write pattern used
        // when the post-apply UPDATE is interrupted; harmless marker.
        // `execution_time = -1` 與 sqlx 自身部分寫入的記號一致，僅為標記。
        sqlx::query(
            "INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) \
             VALUES ($1, $2, TRUE, $3, -1) \
             ON CONFLICT (version) DO NOTHING",
        )
        .bind(m.version)
        .bind(m.description.as_ref())
        .bind(m.checksum.as_ref())
        .execute(&mut *tx)
        .await?;
        seeded += 1;
    }
    tx.commit().await?;

    // Post-seed sanity: row count must equal what we inserted (no pre-existing
    // partial state got past the earlier check).
    // seed 後完整性：行數需等於插入數。
    let after = count_applied_rows(pool).await?;
    if (after as usize) < seeded {
        return Err(MigrationsError::LegacyPartialState {
            existing: after,
            expected: seeded as i64,
        });
    }

    info!(
        seeded,
        max_version = LEGACY_APPLIED_MAX_VERSION,
        "auto_migrate: seeded _sqlx_migrations from legacy-manual-applied canary \
         / 已由 canary 確認的 legacy 手動套用狀態 seed _sqlx_migrations"
    );
    Ok(seeded)
}

/// For test isolation: drop `_sqlx_migrations` (and nothing else). Intended for
/// integration tests and ops debug scripts; safe for prod only when the
/// operator is explicitly re-seeding.
/// 測試隔離用：DROP `_sqlx_migrations`（其他不動）。整合測試與 ops debug 用，
/// 正式環境僅在 operator 明確 re-seed 時使用。
pub async fn truncate_tracking_table(pool: &PgPool) -> Result<(), MigrationsError> {
    pool.execute("DROP TABLE IF EXISTS _sqlx_migrations").await?;
    Ok(())
}

/// Debug helper: list versions currently recorded in `_sqlx_migrations`.
/// 除錯輔助：列出目前 `_sqlx_migrations` 紀錄的版本。
pub async fn list_applied_versions(pool: &PgPool) -> Result<Vec<i64>, MigrationsError> {
    let rows = sqlx::query("SELECT version FROM _sqlx_migrations ORDER BY version")
        .fetch_all(pool)
        .await?;
    Ok(rows
        .into_iter()
        .map(|r| r.try_get::<i64, _>("version").unwrap_or(-1))
        .collect())
}

// ═══════════════════════════════════════════════════════════════════
// Unit tests (no DB required) / 單元測試（無需 DB）
// ═══════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn parse_ok_leading_zeroes() {
        let (v, d) = parse_flyway_filename("V001__create_schemas.sql").unwrap();
        assert_eq!(v, 1);
        assert_eq!(d, "create schemas");
    }

    #[test]
    fn parse_ok_larger_version() {
        let (v, d) = parse_flyway_filename("V023__model_registry.sql").unwrap();
        assert_eq!(v, 23);
        assert_eq!(d, "model registry");
    }

    #[test]
    fn parse_rejects_missing_v() {
        assert!(parse_flyway_filename("001__create.sql").is_err());
    }

    #[test]
    fn parse_rejects_single_underscore() {
        assert!(parse_flyway_filename("V017_rollback.sql").is_err());
    }

    #[test]
    fn parse_rejects_nonnumeric_version() {
        assert!(parse_flyway_filename("Vabc__create.sql").is_err());
    }

    #[test]
    fn parse_rejects_missing_suffix() {
        assert!(parse_flyway_filename("V001__create_schemas").is_err());
    }

    #[test]
    fn parse_rejects_zero_version() {
        assert!(parse_flyway_filename("V000__foo.sql").is_err());
    }

    #[test]
    fn eligibility_accepts_valid() {
        assert!(is_eligible_migration_file("V001__create_schemas.sql"));
        assert!(is_eligible_migration_file("V023__model_registry.sql"));
    }

    #[test]
    fn eligibility_rejects_fixtures_and_rollbacks() {
        // rollback fixture / rollback fixture
        assert!(!is_eligible_migration_file("V017_rollback.sql"));
        // V999 test fixture / V999 測試 fixture
        assert!(!is_eligible_migration_file("V999__exit_features.sql"));
        // README and other misc
        assert!(!is_eligible_migration_file("README.md"));
        assert!(!is_eligible_migration_file("notes.txt"));
    }

    #[test]
    fn eligibility_rejects_wrong_prefix() {
        assert!(!is_eligible_migration_file("U001__foo.sql"));
        assert!(!is_eligible_migration_file("Vabc__foo.sql"));
    }

    #[test]
    fn load_migrations_filters_and_sorts() {
        let dir = tempdir().unwrap();
        // Eligible / 合規
        fs::write(dir.path().join("V002__b.sql"), "SELECT 2;").unwrap();
        fs::write(dir.path().join("V001__a.sql"), "SELECT 1;").unwrap();
        fs::write(dir.path().join("V010__j.sql"), "SELECT 10;").unwrap();
        // Filtered / 應被過濾
        fs::write(dir.path().join("V017_rollback.sql"), "SELECT 'rollback';").unwrap();
        fs::write(dir.path().join("V999__fixture.sql"), "SELECT 'fixture';").unwrap();
        fs::write(dir.path().join("README.md"), "# hi").unwrap();

        let list = load_migrations_from_dir(dir.path()).unwrap();
        let versions: Vec<_> = list.iter().map(|m| m.version).collect();
        assert_eq!(versions, vec![1, 2, 10]);
    }

    #[test]
    fn load_migrations_detects_duplicate_version() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("V001__a.sql"), "SELECT 1;").unwrap();
        fs::write(dir.path().join("V001__alt.sql"), "SELECT 1;").unwrap();
        let err = load_migrations_from_dir(dir.path()).unwrap_err();
        matches!(err, MigrationsError::FilenameParse { .. });
    }

    #[test]
    fn load_migrations_real_srv_tree() {
        // Exercises the real sql/migrations to make sure every shipped file is
        // parseable under our eligibility rule (catches rename accidents).
        // 以實際倉庫內容檢查所有 V### 檔都能被解析（防止重命名事故）。
        let base = match std::env::var("OPENCLAW_BASE_DIR") {
            Ok(s) => PathBuf::from(s),
            Err(_) => PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join(".."),
        };
        let dir = base.join(MIGRATIONS_DIR_REL);
        if !dir.is_dir() {
            // Running outside the srv tree (e.g. standalone crate check).
            // 於 srv 樹外執行，跳過。
            eprintln!("skipping: {} not present", dir.display());
            return;
        }
        let list = load_migrations_from_dir(&dir).unwrap();
        assert!(
            list.len() >= 22,
            "expected ≥22 migrations, got {}",
            list.len()
        );
        let versions: Vec<_> = list.iter().map(|m| m.version).collect();
        // Sanity: sorted and monotonically increasing.
        for w in versions.windows(2) {
            assert!(w[0] < w[1], "not sorted: {:?}", versions);
        }
        // V023 must be present per 2026-04-24 postmortem / V023 須在。
        assert!(
            versions.contains(&23),
            "V023 missing from parse: {:?}",
            versions
        );
    }

    #[test]
    fn build_migrator_echoes_inputs() {
        let m = Migration::new(
            42,
            Cow::Borrowed("hello"),
            MigrationType::Simple,
            Cow::Borrowed("SELECT 1;"),
            false,
        );
        let mig = build_migrator(vec![m]);
        assert_eq!(mig.migrations.len(), 1);
        assert_eq!(mig.migrations[0].version, 42);
        assert!(mig.locking);
        assert!(!mig.ignore_missing);
    }

    // Flip `OPENCLAW_AUTO_MIGRATE` in-process mutates global env — cargo test
    // runs async tests on multiple threads by default, so we gate the two
    // env-sensitive cases behind a process-wide mutex. Combined into a single
    // `#[tokio::test]` to avoid the serial-test dep.
    // `OPENCLAW_AUTO_MIGRATE` 翻轉影響全局 env；cargo 預設多執行緒跑 async，
    // 用 process-wide mutex 串行化，避免引入 serial-test 依賴。
    static ENV_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[tokio::test]
    async fn disabled_and_enabled_no_pool() {
        let _lock = ENV_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempdir().unwrap();

        // Phase 1: env var unset → Disabled, regardless of pool.
        // Phase 1：未設 env → 不管 pool 都回 Disabled。
        std::env::remove_var(AUTO_MIGRATE_ENV_VAR);
        let outcome = MigrationRunner::run_if_enabled(None, tmp.path())
            .await
            .unwrap();
        assert_eq!(outcome, RunOutcome::Disabled);

        // Phase 2: env var set, pool None → NoPool (warn-level, not Err).
        // Phase 2：opt-in 但 pool 為 None → NoPool（警告級，不 Err）。
        let _guard = EnvVarGuard::set(AUTO_MIGRATE_ENV_VAR, "1");
        let outcome = MigrationRunner::run_if_enabled(None, tmp.path())
            .await
            .unwrap();
        assert_eq!(outcome, RunOutcome::NoPool);
    }

    /// RAII env var override for tests that flip `OPENCLAW_AUTO_MIGRATE`.
    /// 測試用 RAII 環境變數翻轉器。
    struct EnvVarGuard {
        key: &'static str,
        prev: Option<String>,
    }

    impl EnvVarGuard {
        fn set(key: &'static str, value: &str) -> Self {
            let prev = std::env::var(key).ok();
            std::env::set_var(key, value);
            Self { key, prev }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            match self.prev.take() {
                Some(v) => std::env::set_var(self.key, v),
                None => std::env::remove_var(self.key),
            }
        }
    }
}
