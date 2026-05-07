//! REF-20 Wave 4 R20-P2b-T1 — `replay_runner` CLI argument parser.
//! REF-20 Wave 4 R20-P2b-T1 — `replay_runner` CLI 參數解析器。
//!
//! MODULE_NOTE (EN):
//!   Hand-rolled minimal CLI parser for the `replay_runner` Rust binary. We
//!   intentionally avoid `clap` because (a) it is NOT in the workspace
//!   dependency list (`Cargo.toml workspace.dependencies`), (b) adding `clap`
//!   would expand the replay crate boundary surface area beyond the
//!   `replay_isolated`-feature allowlist (PA boundary report §4), and (c) the
//!   binary needs only three flag types, all of which are trivially parseable
//!   without a heavyweight library. The parser supports POSIX-style long
//!   options:
//!
//!   ```text
//!       --manifest <path>       Required.  Path to signed manifest JSON.
//!       --output-dir <path>     Required.  Directory for replay report
//!                               artifacts (will be created if missing).
//!       --baseline-id <string>  Optional.  Baseline experiment id for
//!                               baseline-vs-candidate comparison; when
//!                               absent the run is treated as a single-leg
//!                               candidate replay (T2 will land the actual
//!                               comparison logic; T1 records the intent in
//!                               the report only).
//!   ```
//!
//!   The parser is fail-closed:
//!     - Unknown flag -> `CliError::UnknownArg`.
//!     - Missing required flag -> `CliError::MissingRequired`.
//!     - `--manifest=foo` (with `=`) is supported alongside `--manifest foo`.
//!     - Empty path strings -> `CliError::EmptyValue`.
//!
//!   Forbidden-list compliance:
//!     - 0 import of `intent_processor`, `ipc_server`, `bybit_*`,
//!       `governance_hub`, `decision_lease`, `canary_writer`, `database` -
//!       this module reads `std::env::args()` and constructs a typed struct.
//!
//! MODULE_NOTE (中):
//!   `replay_runner` Rust binary 用的手寫最小 CLI 解析器。刻意不使用 `clap`：
//!   (a) workspace 依賴清單未列 `clap`；(b) 加 `clap` 會把 replay crate 邊界
//!   surface area 擴大到 `replay_isolated`-feature allowlist 之外（PA boundary
//!   report §4）；(c) binary 僅需三類旗標，無需重量級 lib 即可平易解析。
//!   解析器支援 POSIX 風長旗標：
//!
//!   ```text
//!       --manifest <path>       必填。已簽 manifest JSON 路徑。
//!       --output-dir <path>     必填。replay report artifact 輸出目錄
//!                               （不存在則建立）。
//!       --baseline-id <string>  可選。baseline-vs-candidate 比較用 baseline
//!                               experiment id；缺省則視為單腿 candidate
//!                               replay（T2 落實際比較邏輯；T1 僅在 report
//!                               中記錄 intent）。
//!   ```
//!
//!   解析器 fail-closed：
//!     - 未知 flag -> `CliError::UnknownArg`。
//!     - 必填 flag 缺 -> `CliError::MissingRequired`。
//!     - 同時支援 `--manifest=foo`（含 `=`）與 `--manifest foo`。
//!     - 空字串路徑 -> `CliError::EmptyValue`。
//!
//!   Forbidden 清單合規：
//!     - 0 import `intent_processor` / `ipc_server` / `bybit_*` /
//!       `governance_hub` / `decision_lease` / `canary_writer` / `database` —
//!       本模組僅讀 `std::env::args()` 並構造 typed struct。
//!
//! SPEC: REF-20 V3 §6.2 + workplan §4 Wave 4 R20-P2b-T1.

use std::path::PathBuf;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Parsed CLI arguments for `replay_runner`.
///
/// `replay_runner` 的解析後 CLI 參數。
///
/// Field semantics (EN):
///   - `manifest_path`: file path to the signed manifest JSON (must be a
///     regular file readable by the runner; this struct does NOT validate
///     existence — fixture loader does, so failures attribute correctly).
///   - `output_dir`: directory where the report writer will materialise the
///     `replay_report.json` plus any sibling diagnostic artifacts. Created
///     by the report writer on demand if missing.
///   - `baseline_id`: optional baseline experiment id. When `Some(id)` the
///     report records `baseline_id` so the future T2 comparison route can
///     join two experiments; when `None` the report flags
///     `comparison_mode = "single_leg"`.
///
/// 欄位語意（中）：
///   - `manifest_path`: 已簽 manifest JSON 的檔案路徑（必為 runner 可讀的
///     一般檔案；此 struct **不**驗存在性 — fixture loader 做，使失敗歸因正確）。
///   - `output_dir`: report writer 落 `replay_report.json` 與相關 diagnostic
///     artifact 的目錄。缺則由 report writer on-demand 建立。
///   - `baseline_id`: 可選的 baseline experiment id。`Some(id)` 時 report
///     記錄 `baseline_id` 供未來 T2 comparison route join 兩 experiment；
///     `None` 時 report 標記 `comparison_mode = "single_leg"`。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayCliArgs {
    pub manifest_path: PathBuf,
    pub output_dir: PathBuf,
    pub baseline_id: Option<String>,
}

/// CLI parse failure modes.
///
/// CLI 解析失敗模式。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CliError {
    /// Required flag absent (e.g. caller forgot `--manifest`).
    /// 必填旗標缺失（例如 caller 忘了 `--manifest`）。
    MissingRequired { flag: &'static str },
    /// Required flag present but value missing (e.g. `--manifest` not followed by a path).
    /// 必填旗標存在但缺值（例如 `--manifest` 後無路徑）。
    MissingValue { flag: String },
    /// Required flag present but value is empty string (e.g. `--manifest ""`).
    /// 必填旗標存在但值為空字串（例如 `--manifest ""`）。
    EmptyValue { flag: String },
    /// Unknown / unsupported flag encountered.
    /// 遇到未知 / 不支援的旗標。
    UnknownArg { arg: String },
}

impl std::fmt::Display for CliError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingRequired { flag } => write!(
                f,
                "CliError::MissingRequired{{flag={flag}}} — \
                 replay_runner requires this flag (use --help)"
            ),
            Self::MissingValue { flag } => write!(
                f,
                "CliError::MissingValue{{flag={flag}}} — flag present but no value"
            ),
            Self::EmptyValue { flag } => write!(
                f,
                "CliError::EmptyValue{{flag={flag}}} — flag value is empty string"
            ),
            Self::UnknownArg { arg } => write!(
                f,
                "CliError::UnknownArg{{arg={arg}}} — unknown flag for replay_runner"
            ),
        }
    }
}

impl std::error::Error for CliError {}

// ─────────────────────────────────────────────────────────────────────────
// Public API / 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// Parse CLI args from `std::env::args()`.
///
/// 從 `std::env::args()` 解析 CLI 參數。
///
/// Semantics (EN):
///   - Skips `argv[0]` (the binary path).
///   - Walks remaining args and matches one of:
///         `--manifest`   `--manifest=<v>`
///         `--output-dir` `--output-dir=<v>`
///         `--baseline-id` `--baseline-id=<v>`
///   - `--<flag>=<v>` and `--<flag> <v>` are treated identically.
///   - Returns `Err(CliError::UnknownArg)` on any other token.
///
/// 語意（中）：
///   - 跳過 `argv[0]`（binary 路徑）。
///   - 走訪剩餘 args 並 match 其一：
///         `--manifest`   `--manifest=<v>`
///         `--output-dir` `--output-dir=<v>`
///         `--baseline-id` `--baseline-id=<v>`
///   - `--<flag>=<v>` 與 `--<flag> <v>` 視為等價。
///   - 其他 token 一律回 `Err(CliError::UnknownArg)`。
pub fn parse_cli_args() -> Result<ReplayCliArgs, CliError> {
    parse_from(std::env::args().skip(1))
}

/// Test-friendly: parse from any iterator of strings (skips no prefix).
///
/// Test-friendly：從任何 string iterator 解析（不跳前綴）。
///
/// Used by unit tests to inject synthetic argv sequences without going
/// through `std::env::args`.
///
/// 供 unit test 注入合成 argv 序列、不經 `std::env::args` 之用。
pub fn parse_from<I, S>(args: I) -> Result<ReplayCliArgs, CliError>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut manifest_path: Option<PathBuf> = None;
    let mut output_dir: Option<PathBuf> = None;
    let mut baseline_id: Option<String> = None;

    let mut iter = args.into_iter().map(Into::into);
    while let Some(arg) = iter.next() {
        // Pattern 1: `--flag=value` / `--flag=value` 模式。
        if let Some((name, value)) = arg.split_once('=') {
            match name {
                "--manifest" => manifest_path = Some(non_empty_path(name, value)?),
                "--output-dir" => output_dir = Some(non_empty_path(name, value)?),
                "--baseline-id" => baseline_id = Some(non_empty_string(name, value)?),
                _ => return Err(CliError::UnknownArg { arg: arg.clone() }),
            }
            continue;
        }

        // Pattern 2: `--flag value` / `--flag value` 模式。
        match arg.as_str() {
            "--manifest" => {
                let v = next_value(&mut iter, "--manifest")?;
                manifest_path = Some(non_empty_path("--manifest", &v)?);
            }
            "--output-dir" => {
                let v = next_value(&mut iter, "--output-dir")?;
                output_dir = Some(non_empty_path("--output-dir", &v)?);
            }
            "--baseline-id" => {
                let v = next_value(&mut iter, "--baseline-id")?;
                baseline_id = Some(non_empty_string("--baseline-id", &v)?);
            }
            _ => return Err(CliError::UnknownArg { arg }),
        }
    }

    let manifest_path = manifest_path.ok_or(CliError::MissingRequired { flag: "--manifest" })?;
    let output_dir = output_dir.ok_or(CliError::MissingRequired {
        flag: "--output-dir",
    })?;

    Ok(ReplayCliArgs {
        manifest_path,
        output_dir,
        baseline_id,
    })
}

// ─────────────────────────────────────────────────────────────────────────
// Internal helpers / 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// Pull next value from iterator or return `MissingValue`.
///
/// 從 iterator 取下一個 value，缺則回 `MissingValue`。
fn next_value<I>(iter: &mut I, flag: &str) -> Result<String, CliError>
where
    I: Iterator<Item = String>,
{
    iter.next().ok_or_else(|| CliError::MissingValue {
        flag: flag.to_string(),
    })
}

/// Reject empty-string values on path-typed flags.
///
/// 路徑型 flag 拒絕空字串值。
fn non_empty_path(flag: &str, raw: &str) -> Result<PathBuf, CliError> {
    if raw.is_empty() {
        return Err(CliError::EmptyValue {
            flag: flag.to_string(),
        });
    }
    Ok(PathBuf::from(raw))
}

/// Reject empty-string values on plain-string flags.
///
/// 純字串 flag 拒絕空字串值。
fn non_empty_string(flag: &str, raw: &str) -> Result<String, CliError> {
    if raw.is_empty() {
        return Err(CliError::EmptyValue {
            flag: flag.to_string(),
        });
    }
    Ok(raw.to_string())
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    fn parse_strs(args: &[&str]) -> Result<ReplayCliArgs, CliError> {
        parse_from(args.iter().map(|s| s.to_string()))
    }

    #[test]
    fn happy_path_required_only() {
        let r = parse_strs(&["--manifest", "/tmp/m.json", "--output-dir", "/tmp/out"]).unwrap();
        assert_eq!(r.manifest_path, PathBuf::from("/tmp/m.json"));
        assert_eq!(r.output_dir, PathBuf::from("/tmp/out"));
        assert_eq!(r.baseline_id, None);
    }

    #[test]
    fn happy_path_with_baseline_id() {
        let r = parse_strs(&[
            "--manifest",
            "m.json",
            "--output-dir",
            "out",
            "--baseline-id",
            "exp_123",
        ])
        .unwrap();
        assert_eq!(r.baseline_id.as_deref(), Some("exp_123"));
    }

    #[test]
    fn equals_form_supported() {
        let r = parse_strs(&["--manifest=foo.json", "--output-dir=out_dir"]).unwrap();
        assert_eq!(r.manifest_path, PathBuf::from("foo.json"));
        assert_eq!(r.output_dir, PathBuf::from("out_dir"));
    }

    #[test]
    fn missing_required_manifest() {
        let err = parse_strs(&["--output-dir", "out"]).unwrap_err();
        assert_eq!(err, CliError::MissingRequired { flag: "--manifest" });
    }

    #[test]
    fn missing_required_output_dir() {
        let err = parse_strs(&["--manifest", "m.json"]).unwrap_err();
        assert_eq!(
            err,
            CliError::MissingRequired {
                flag: "--output-dir"
            }
        );
    }

    #[test]
    fn missing_value() {
        let err = parse_strs(&["--manifest"]).unwrap_err();
        assert_eq!(
            err,
            CliError::MissingValue {
                flag: "--manifest".to_string()
            }
        );
    }

    #[test]
    fn empty_value_rejected() {
        let err = parse_strs(&["--manifest", "", "--output-dir", "out"]).unwrap_err();
        assert_eq!(
            err,
            CliError::EmptyValue {
                flag: "--manifest".to_string()
            }
        );
    }

    #[test]
    fn unknown_flag_rejected() {
        let err = parse_strs(&["--bogus"]).unwrap_err();
        assert_eq!(
            err,
            CliError::UnknownArg {
                arg: "--bogus".to_string()
            }
        );
    }

    #[test]
    fn unknown_equals_flag_rejected() {
        let err = parse_strs(&["--bogus=x"]).unwrap_err();
        assert_eq!(
            err,
            CliError::UnknownArg {
                arg: "--bogus=x".to_string()
            }
        );
    }
}
