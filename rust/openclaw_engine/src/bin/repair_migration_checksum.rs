//! Repair `_sqlx_migrations.checksum` drift caused by V028/V030/V031/V032/V034
//! file edits without DB checksum update.
//!
//! 修復 `_sqlx_migrations.checksum` drift（V028/V030/V031/V032/V034 經
//! audit-p1-1 retrofit `e858ae2` + round-3 `6cb1c3b` 改了檔案內容
//! 但未同步 DB checksum，導致 2026-05-02 18:35 engine startup abort）。
//!
//! MODULE_NOTE (EN): Standalone Rust binary that recomputes migration
//!   checksums via the same code path the engine uses
//!   (`openclaw_engine::database::migrations::load_migrations_from_dir`,
//!   which calls `sqlx::migrate::Migration::new` → `Sha384::digest(sql.as_bytes())`
//!   on raw UTF-8 bytes with NO normalization). This guarantees algorithmic
//!   parity with the engine's startup verification — if `--apply` writes a
//!   checksum here, the engine will accept it on next start.
//!
//!   Two modes:
//!     `--verify` (default, READ-ONLY) — print drift table comparing file
//!       SHA-384 vs DB-stored checksum; never writes to DB.
//!     `--apply` (DESTRUCTIVE) — requires `--i-understand-this-modifies-db`
//!       flag, automatic `pg_dump -t _sqlx_migrations` backup, in-transaction
//!       UPDATE with interactive `Type COMMIT/anything-else` prompt before
//!       commit/rollback decision.
//!
//!   SAFETY:
//!     - Never mutates migration files on disk.
//!     - Never silently writes to DB; `--apply` ALWAYS prompts.
//!     - `--apply` without explicit ack flag → exit 2.
//!     - DB URL is sourced via the same `secret_env::var_or_file` helper the
//!       engine uses (`OPENCLAW_DATABASE_URL` env var or `_FILE` indirection),
//!       so this binary cannot point at a DB the engine doesn't already trust.
//!
//! MODULE_NOTE (中): 獨立 Rust binary，借用 engine 同源程式碼
//!   （`openclaw_engine::database::migrations::load_migrations_from_dir`，
//!   內部呼叫 `sqlx::migrate::Migration::new` → `Sha384::digest(sql.as_bytes())`
//!   raw UTF-8 bytes 無 normalization）重算 checksum。算法與 engine 啟動驗證
//!   一致 → `--apply` 寫入後 engine 下次啟動必接受。
//!
//!   兩種模式：
//!     `--verify`（預設，唯讀）— 印出 file SHA-384 vs DB checksum 對照表，
//!       絕不寫 DB。
//!     `--apply`（破壞性）— 需顯式 `--i-understand-this-modifies-db`、
//!       自動 `pg_dump -t _sqlx_migrations` 備份、在 transaction 內 UPDATE
//!       後互動式 prompt（輸入 COMMIT 才提交，其他輸入則 ROLLBACK）。
//!
//!   不變量 / Invariants:
//!     - 永不修改 migration 檔案。
//!     - 永不未經確認寫 DB；`--apply` 必互動 prompt。
//!     - `--apply` 缺 ack flag → exit 2 拒絕執行。
//!     - DB URL 用與 engine 相同的 `secret_env::var_or_file` 來源。
//!
//! Refs: incident 2026-05-02 18:35 engine abort; PA plan B path.

use std::env;
use std::io::{self, BufRead, IsTerminal, Write};
use std::path::PathBuf;
use std::process::Command;
use std::time::SystemTime;

use openclaw_engine::database::migrations::{load_migrations_from_dir, MIGRATIONS_DIR_REL};
use openclaw_engine::secret_env;

use sqlx::postgres::{PgPool, PgPoolOptions};
use sqlx::Row;

/// Exit codes / 退出碼。
const EXIT_OK: i32 = 0;
const EXIT_ARG: i32 = 2;
const EXIT_RUNTIME: i32 = 3;
const EXIT_DB: i32 = 4;
const EXIT_USER_ROLLBACK: i32 = 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    /// READ-ONLY drift inspection / 唯讀漂移檢查。
    Verify,
    /// DESTRUCTIVE checksum repair (with backup + interactive prompt).
    /// 破壞性 checksum 修復（含備份與互動 prompt）。
    Apply,
}

/// Parsed CLI arguments / 解析後的命令列參數。
struct Args {
    mode: Mode,
    /// Required for `--apply` to proceed; guards against accidental run.
    /// `--apply` 必帶；防止誤觸。
    i_understand: bool,
}

fn parse_args() -> Result<Args, String> {
    let mut mode = Mode::Verify;
    let mut i_understand = false;

    // Skip argv[0] / 跳過程式名
    for arg in env::args().skip(1) {
        match arg.as_str() {
            "--verify" => mode = Mode::Verify,
            "--apply" => mode = Mode::Apply,
            "--i-understand-this-modifies-db" => i_understand = true,
            "--help" | "-h" => {
                print_help();
                std::process::exit(EXIT_OK);
            }
            // Reject auto-yes / bypass flags explicitly, per PA spec.
            // 顯式拒絕 auto-yes / 旁路 flag。
            "--auto-yes" | "--yes" | "-y" | "--force" => {
                return Err(format!(
                    "rejected flag {:?}: interactive prompt is mandatory for --apply \
                     / 拒絕旁路 prompt 的 flag {:?}",
                    arg, arg
                ));
            }
            other => {
                return Err(format!("unknown argument: {other}"));
            }
        }
    }

    Ok(Args { mode, i_understand })
}

fn print_help() {
    println!(
        "repair_migration_checksum — recompute and (optionally) repair _sqlx_migrations.checksum\n\
         \n\
         USAGE:\n  \
           repair_migration_checksum [--verify | --apply --i-understand-this-modifies-db]\n\
         \n\
         MODES:\n  \
           --verify (default)   READ-ONLY. Print drift table for V###__*.sql files.\n  \
           --apply              DESTRUCTIVE. Requires --i-understand-this-modifies-db.\n                       \
                            Automatic pg_dump backup; interactive COMMIT prompt.\n\
         \n\
         ENV VARS:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE  (engine same source)\n  \
           OPENCLAW_MIGRATIONS_DIR     (default: $OPENCLAW_BASE_DIR/sql/migrations)\n  \
           OPENCLAW_BASE_DIR           (fallback CWD)\n  \
           OPENCLAW_DATA_DIR           (default: /tmp/openclaw, used for backup dir)\n"
    );
}

/// Resolve migrations directory / 解析 migrations 目錄。
///
/// Priority: `OPENCLAW_MIGRATIONS_DIR` > `$OPENCLAW_BASE_DIR/sql/migrations` >
///           `$CWD/sql/migrations`. Engine uses `MIGRATIONS_DIR_REL` constant
/// for the relative tail; we honour the same convention.
fn resolve_migrations_dir() -> PathBuf {
    if let Ok(p) = env::var("OPENCLAW_MIGRATIONS_DIR") {
        if !p.is_empty() {
            return PathBuf::from(p);
        }
    }
    let base = env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    base.join(MIGRATIONS_DIR_REL)
}

/// Resolve DB URL via the same secret_env helper the engine uses.
/// 透過與 engine 相同的 secret_env 取得 DB URL。
fn resolve_db_url() -> Result<String, String> {
    secret_env::var_or_file("OPENCLAW_DATABASE_URL")
        .filter(|s| !s.is_empty())
        .ok_or_else(|| {
            "OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE not set / 未設定 DB URL"
                .to_string()
        })
}

/// Detect line-ending style for a SQL file (best effort, byte-level).
/// 偵測 SQL 檔的換行型態（位元組層級）。
fn detect_line_ending(sql: &str) -> &'static str {
    let crlf = sql.matches("\r\n").count();
    let lf_total = sql.matches('\n').count();
    let lf_only = lf_total.saturating_sub(crlf);
    match (crlf, lf_only) {
        (0, 0) => "none",
        (c, 0) if c > 0 => "CRLF",
        (0, _) => "LF",
        _ => "MIXED",
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let exit = run().await;
    std::process::exit(exit);
}

async fn run() -> i32 {
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("error: {e}");
            print_help();
            return EXIT_ARG;
        }
    };

    if args.mode == Mode::Apply && !args.i_understand {
        eprintln!(
            "REFUSED: --apply requires --i-understand-this-modifies-db flag.\n\
             拒絕：--apply 需同時帶 --i-understand-this-modifies-db。"
        );
        return EXIT_ARG;
    }

    // ───── 1. Load migration files (parser identical to engine) ─────
    let migrations_dir = resolve_migrations_dir();
    println!("# migrations_dir = {}", migrations_dir.display());
    if !migrations_dir.is_dir() {
        eprintln!(
            "ERROR: migrations dir not found: {} / 找不到 migrations 目錄",
            migrations_dir.display()
        );
        return EXIT_RUNTIME;
    }
    let migrations = match load_migrations_from_dir(&migrations_dir) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("ERROR loading migrations: {e}");
            return EXIT_RUNTIME;
        }
    };
    println!("# parsed_count = {}", migrations.len());

    // Collect file metadata side-table (line endings, byte size, file path).
    // We re-read file bytes here for diagnostics; checksum already in `m.checksum`.
    // 收集檔案 metadata（換行、大小、路徑）作為輔助診斷；checksum 已在 `m.checksum`。
    let mut file_meta: Vec<(i64, String, String, String, u64, String)> = Vec::new(); // (version, file_name, line_end, file_size, mtime_unix, sha384_hex)
    for m in &migrations {
        // Find matching file on disk by version prefix `V###__` — engine parser
        // already validated existence, so unwrap_or fallback is safe.
        // 依版本前綴 `V###__` 對應檔案；engine parser 已驗存在性。
        let prefix = format!("V{:03}__", m.version);
        let mut file_name = String::new();
        let mut size: u64 = 0;
        let mut mtime: u64 = 0;
        let mut line_end = String::from("?");
        if let Ok(entries) = std::fs::read_dir(&migrations_dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with(&prefix) && name.ends_with(".sql") {
                    file_name = name.clone();
                    if let Ok(meta) = entry.metadata() {
                        size = meta.len();
                        if let Ok(t) = meta.modified() {
                            if let Ok(d) = t.duration_since(SystemTime::UNIX_EPOCH) {
                                mtime = d.as_secs();
                            }
                        }
                    }
                    if let Ok(text) = std::fs::read_to_string(entry.path()) {
                        line_end = detect_line_ending(&text).to_string();
                    }
                    break;
                }
            }
        }
        let sha = hex::encode(m.checksum.as_ref());
        file_meta.push((m.version, file_name, line_end, format!("{size}"), mtime, sha));
    }

    // ───── 2. Connect to DB and read _sqlx_migrations ─────
    let db_url = match resolve_db_url() {
        Ok(u) => u,
        Err(e) => {
            eprintln!("ERROR: {e}");
            return EXIT_DB;
        }
    };
    let pool = match PgPoolOptions::new()
        .max_connections(2)
        .connect(&db_url)
        .await
    {
        Ok(p) => p,
        Err(e) => {
            eprintln!("ERROR: failed to connect DB: {e}");
            return EXIT_DB;
        }
    };

    let db_rows = match read_sqlx_migrations(&pool).await {
        Ok(r) => r,
        Err(e) => {
            eprintln!("ERROR reading _sqlx_migrations: {e}");
            return EXIT_DB;
        }
    };
    println!("# db_rows = {}", db_rows.len());

    // ───── 3. Build drift table and print ─────
    println!();
    println!(
        "version\tdescription\tfile_name\tline_end\tfile_size\tfile_mtime_unix\tfile_sha384\tdb_checksum\tdrift?"
    );

    let mut drift_versions: Vec<i64> = Vec::new();
    let mut versions_seen_in_files = std::collections::BTreeSet::new();

    for m in &migrations {
        versions_seen_in_files.insert(m.version);
        let meta = file_meta
            .iter()
            .find(|(v, ..)| *v == m.version)
            .expect("file_meta covers all migrations");
        let file_sha = &meta.5;
        let db_row = db_rows.iter().find(|(v, _, _)| *v == m.version);
        let (db_hex, drift_label) = match db_row {
            None => (String::from("(not in DB)"), "MISSING_IN_DB".to_string()),
            Some((_, _, db_bytes)) => {
                let db_hex = hex::encode(db_bytes);
                let drift = db_hex != *file_sha;
                if drift {
                    drift_versions.push(m.version);
                }
                (db_hex, if drift { "YES".into() } else { "no".into() })
            }
        };
        println!(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
            m.version,
            m.description,
            meta.1,
            meta.2,
            meta.3,
            meta.4,
            file_sha,
            db_hex,
            drift_label
        );
    }

    // Rows present in DB but no matching file (defensive).
    // DB 有但本地無檔的條目（防禦性）。
    for (v, desc, db_bytes) in &db_rows {
        if !versions_seen_in_files.contains(v) {
            println!(
                "{}\t{}\t(no file)\t-\t-\t-\t-\t{}\tEXTRA_IN_DB",
                v,
                desc,
                hex::encode(db_bytes)
            );
        }
    }

    println!();
    println!("# ───── SUMMARY ─────");
    println!("# parsed_files = {}", migrations.len());
    println!("# db_rows      = {}", db_rows.len());
    println!("# drift_count  = {}", drift_versions.len());
    println!("# drift_versions = {:?}", drift_versions);

    // Sanity: per PA spec, V028/V030/V031/V032/V034 should drift; V033 unknown.
    // Print known-affected expectation versus actual.
    // 對照 PA 已驗 drift 名單：V028/V030/V031/V032/V034；V033 由 binary 判定。
    let pa_known: [i64; 5] = [28, 30, 31, 32, 34];
    let mut pa_caught: Vec<i64> = Vec::new();
    let mut pa_missed: Vec<i64> = Vec::new();
    for v in pa_known {
        if drift_versions.contains(&v) {
            pa_caught.push(v);
        } else {
            pa_missed.push(v);
        }
    }
    println!("# pa_known_drift     = {:?}", pa_known);
    println!("# pa_caught_by_binary = {:?}", pa_caught);
    println!("# pa_missed_by_binary = {:?}", pa_missed);
    let v033_drifts = drift_versions.contains(&33);
    println!("# v033_verdict       = {}", if v033_drifts { "DRIFT" } else { "clean" });

    // ───── 4. --verify exit ─────
    if args.mode == Mode::Verify {
        return EXIT_OK;
    }

    // ───── 5. --apply path ─────
    println!();
    println!("# ───── --apply mode ─────");

    if drift_versions.is_empty() {
        println!("# nothing to repair / 無需修復");
        return EXIT_OK;
    }

    // 5-PRE. TTY guard (E2 review MEDIUM, 2026-05-02).
    // 拒絕 non-TTY stdin（如 `echo COMMIT | binary --apply ...`）以保留
    // 「人類在現場」防線。必須在 BEGIN tx / pg_dump / UPDATE 之前 short-circuit。
    // Refuse non-TTY stdin (e.g. `echo COMMIT | binary --apply ...`) to preserve
    // the human-in-the-loop safety net. Must short-circuit BEFORE pg_dump / BEGIN /
    // UPDATE so no side-effects (DB writes, dump file) occur on a piped invocation.
    if !io::stdin().is_terminal() {
        eprintln!("REFUSED: --apply requires interactive TTY stdin; piped/non-TTY input rejected.");
        eprintln!("拒絕：--apply 必須由互動式 TTY stdin 執行；偵測到 piped / non-TTY 輸入。");
        return EXIT_ARG;
    }

    // 5a. pg_dump backup of _sqlx_migrations
    if let Err(e) = pg_dump_backup(&db_url) {
        eprintln!("ERROR: pg_dump backup failed: {e}");
        return EXIT_DB;
    }

    // 5b. Build UPDATE statements within a single transaction.
    // 在單一 transaction 內組 UPDATE。
    let mut tx = match pool.begin().await {
        Ok(t) => t,
        Err(e) => {
            eprintln!("ERROR: BEGIN failed: {e}");
            return EXIT_DB;
        }
    };

    for m in &migrations {
        if !drift_versions.contains(&m.version) {
            continue;
        }
        let new_hex = hex::encode(m.checksum.as_ref());
        let r = sqlx::query("UPDATE _sqlx_migrations SET checksum = decode($1, 'hex') WHERE version = $2")
            .bind(&new_hex)
            .bind(m.version)
            .execute(&mut *tx)
            .await;
        match r {
            Ok(res) => {
                println!(
                    "# UPDATE v={} hex={} rows_affected={}",
                    m.version,
                    new_hex,
                    res.rows_affected()
                );
            }
            Err(e) => {
                eprintln!("ERROR: UPDATE v={} failed: {e}", m.version);
                let _ = tx.rollback().await;
                return EXIT_DB;
            }
        }
    }

    // 5c. SELECT in-tx confirmation print.
    // 在 tx 內 SELECT 確認。
    println!();
    println!("# in-transaction state (NOT YET COMMITTED) / 尚未 COMMIT 的當前狀態:");
    let confirm_rows: Result<Vec<(i64, String, String)>, sqlx::Error> = sqlx::query(
        "SELECT version, description, encode(checksum,'hex') AS hex \
         FROM _sqlx_migrations WHERE version = ANY($1) ORDER BY version",
    )
    .bind(&drift_versions)
    .fetch_all(&mut *tx)
    .await
    .map(|rows| {
        rows.into_iter()
            .map(|r| {
                let v: i64 = r.get("version");
                let d: String = r.get("description");
                let h: String = r.get("hex");
                (v, d, h)
            })
            .collect()
    });
    match confirm_rows {
        Ok(rows) => {
            for (v, d, h) in rows {
                println!("#   v={} desc={:?} new_checksum={}", v, d, h);
            }
        }
        Err(e) => {
            eprintln!("ERROR: in-tx confirm SELECT failed: {e}");
            let _ = tx.rollback().await;
            return EXIT_DB;
        }
    }

    // 5d. Interactive prompt.
    // 互動 prompt。
    println!();
    print!("Type COMMIT to apply, anything else to ROLLBACK: ");
    let _ = io::stdout().flush();
    let mut answer = String::new();
    let stdin = io::stdin();
    if stdin.lock().read_line(&mut answer).is_err() {
        eprintln!("ERROR: failed to read stdin; rolling back.");
        let _ = tx.rollback().await;
        return EXIT_USER_ROLLBACK;
    }
    let typed = answer.trim();
    if typed == "COMMIT" {
        if let Err(e) = tx.commit().await {
            eprintln!("ERROR: COMMIT failed: {e}");
            return EXIT_DB;
        }
        println!("# COMMITTED / 已提交");
    } else {
        let _ = tx.rollback().await;
        println!("# ROLLED BACK (input != COMMIT) / 已回滾（輸入非 COMMIT）");
        return EXIT_USER_ROLLBACK;
    }

    // 5e. Final state read-back.
    // 提交後最終讀回。
    println!();
    println!("# final state (post-commit) / 提交後最終狀態:");
    match read_sqlx_migrations(&pool).await {
        Ok(rows) => {
            for (v, d, c) in rows {
                if drift_versions.contains(&v) {
                    println!("#   v={} desc={:?} checksum={}", v, d, hex::encode(&c));
                }
            }
        }
        Err(e) => eprintln!("WARN: post-commit readback failed: {e}"),
    }

    EXIT_OK
}

/// Read all rows of `_sqlx_migrations` ordered by version.
/// 讀 `_sqlx_migrations` 全行（依 version 排序）。
async fn read_sqlx_migrations(
    pool: &PgPool,
) -> Result<Vec<(i64, String, Vec<u8>)>, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT version, description, checksum FROM _sqlx_migrations ORDER BY version",
    )
    .fetch_all(pool)
    .await?;
    let mut out = Vec::with_capacity(rows.len());
    for r in rows {
        let v: i64 = r.try_get("version")?;
        let d: String = r.try_get("description")?;
        let c: Vec<u8> = r.try_get("checksum")?;
        out.push((v, d, c));
    }
    Ok(out)
}

/// Run `pg_dump -t _sqlx_migrations` writing to backup directory.
/// 跑 `pg_dump -t _sqlx_migrations` 寫入備份目錄。
fn pg_dump_backup(db_url: &str) -> Result<PathBuf, String> {
    let data_dir = env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".to_string());
    let backup_dir = PathBuf::from(&data_dir).join("backup");
    std::fs::create_dir_all(&backup_dir).map_err(|e| format!("mkdir backup_dir: {e}"))?;
    let ts = chrono::Utc::now().format("%Y%m%dT%H%M%SZ").to_string();
    let out_path = backup_dir.join(format!("_sqlx_migrations_pre_repair_{ts}.sql"));

    println!(
        "# pg_dump backup target: {} / 備份目標",
        out_path.display()
    );

    let status = Command::new("pg_dump")
        .arg("--data-only")
        .arg("-t")
        .arg("_sqlx_migrations")
        .arg("-f")
        .arg(&out_path)
        .arg(db_url)
        .status()
        .map_err(|e| format!("spawn pg_dump: {e}"))?;
    if !status.success() {
        return Err(format!("pg_dump exit status: {status}"));
    }
    println!("# pg_dump backup ok / 備份完成");
    Ok(out_path)
}
