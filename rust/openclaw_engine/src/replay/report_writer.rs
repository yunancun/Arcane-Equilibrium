//! REF-20 Wave 4 R20-P2b-T1 — replay report writer (baseline JSON output).
//! REF-20 Wave 4 R20-P2b-T1 — replay report writer（基線 JSON 輸出）。
//!
//! MODULE_NOTE (EN):
//!   Writes the post-execution `ReplayResult` to disk as `replay_report.json`
//!   under `output_dir`, with a sibling `replay_report.summary.txt` for human
//!   inspection (operators on Mac smoke runs use the txt for quick triage).
//!
//!   T1 scope deliberately ships ONLY the baseline JSON + summary. Wave 4
//!   R20-P2b-T3 (canary/diagnostic artifacts) extends the artifact set with
//!   per-tick canary JSONL + diagnostic.json + comparison.json (when a
//!   baseline_id was supplied in CLI). T3 lives in a sibling boundary and
//!   shares only the JSON-emission helpers from this module.
//!
//!   Output paths:
//!     - `<output_dir>/replay_report.json`         (canonical, machine-readable)
//!     - `<output_dir>/replay_report.summary.txt`  (human-readable, optional)
//!
//!   V3 §6.2 + §12 contract bindings:
//!     - 0 import of `database`, `canary_writer`, `bybit_*`, `ipc_server`,
//!       `governance_hub`, `decision_lease`, `intent_processor` —
//!       this module is pure file IO over `serde_json`.
//!     - `execution_confidence='none'` is preserved verbatim from
//!       `ReplayResult::execution_confidence` (set in `runner.rs` per V3
//!       §12 #11). Report writer does NOT mutate it.
//!     - `replay_report.json` schema is forward-compatible: future Wave 5/6
//!       additions append fields rather than rename existing ones.
//!
//! MODULE_NOTE (中):
//!   將 post-execute 的 `ReplayResult` 以 `replay_report.json` 寫入 disk 於
//!   `output_dir` 下，並附 sibling `replay_report.summary.txt` 供人工檢視
//!   （Mac smoke run 的 operator 用 txt 快速 triage）。
//!
//!   T1 範圍刻意僅出貨基線 JSON + summary。Wave 4 R20-P2b-T3
//!   （canary/diagnostic artifacts）擴展 artifact 集，包含 per-tick canary
//!   JSONL + diagnostic.json + comparison.json（CLI 提供 baseline_id 時）。
//!   T3 屬 sibling 邊界，僅共用本模組的 JSON 發射 helper。
//!
//!   輸出路徑：
//!     - `<output_dir>/replay_report.json`         （標準、機器可讀）
//!     - `<output_dir>/replay_report.summary.txt`  （人可讀，可選）
//!
//!   V3 §6.2 + §12 契約綁定：
//!     - 0 import `database` / `canary_writer` / `bybit_*` / `ipc_server` /
//!       `governance_hub` / `decision_lease` / `intent_processor` —
//!       本模組為基於 `serde_json` 的純 file IO。
//!     - `execution_confidence='none'` 從 `ReplayResult::execution_confidence`
//!       原樣保留（runner.rs 依 V3 §12 #11 設定）。Report writer **不** mutate。
//!     - `replay_report.json` schema 向前相容：未來 Wave 5/6 附加欄位而非
//!       重新命名既有欄位。
//!
//! SPEC: REF-20 V3 §6.2 + §11 + §12 #11 + workplan §4 Wave 4 R20-P2b-T1.

use serde::Serialize;
use std::path::{Path, PathBuf};

use crate::replay::runner::ReplayResult;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Report writer failure modes.
///
/// Report writer 失敗模式。
#[derive(Debug)]
pub enum ReportError {
    /// Output directory does not exist AND could not be created.
    /// 輸出目錄不存在且無法建立。
    OutputDirCreate { path: PathBuf, source: std::io::Error },
    /// Failed to write `replay_report.json`.
    /// 寫 `replay_report.json` 失敗。
    JsonWrite { path: PathBuf, source: std::io::Error },
    /// Failed to write `replay_report.summary.txt`.
    /// 寫 `replay_report.summary.txt` 失敗。
    SummaryWrite { path: PathBuf, source: std::io::Error },
    /// `serde_json::to_string_pretty` failed (extremely rare; only happens on
    /// non-string-serialisable map keys, which `ReplayResult` does not use).
    /// `serde_json::to_string_pretty` 失敗（極罕見；僅發生於 non-string-
    /// serialisable map key，而 `ReplayResult` 不使用此類）。
    JsonSerialize { source: serde_json::Error },
}

impl std::fmt::Display for ReportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::OutputDirCreate { path, source } => write!(
                f,
                "ReportError::OutputDirCreate{{path={}, io={}}}",
                path.display(),
                source
            ),
            Self::JsonWrite { path, source } => write!(
                f,
                "ReportError::JsonWrite{{path={}, io={}}}",
                path.display(),
                source
            ),
            Self::SummaryWrite { path, source } => write!(
                f,
                "ReportError::SummaryWrite{{path={}, io={}}}",
                path.display(),
                source
            ),
            Self::JsonSerialize { source } => write!(
                f,
                "ReportError::JsonSerialize{{serde_err={}}}",
                source
            ),
        }
    }
}

impl std::error::Error for ReportError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::OutputDirCreate { source, .. }
            | Self::JsonWrite { source, .. }
            | Self::SummaryWrite { source, .. } => Some(source),
            Self::JsonSerialize { source } => Some(source),
        }
    }
}

/// Report envelope persisted to `replay_report.json`. We wrap the
/// `ReplayResult` with metadata fields (`schema_version`, `generated_at_ms`)
/// so future readers can detect schema drift without a separate registry
/// table. Wave 4 emits `schema_version = 1`.
///
/// 持久化到 `replay_report.json` 的 report envelope。我們以 metadata 欄位
/// （`schema_version`、`generated_at_ms`）包覆 `ReplayResult`，使未來 reader
/// 可在無獨立 registry table 之下偵測 schema 漂移。Wave 4 發 `schema_version = 1`。
#[derive(Debug, Serialize)]
struct ReportEnvelope<'a> {
    schema_version: u32,
    generated_at_ms: i64,
    /// Echoed for trace correlation; same value as `result.manifest_id` so
    /// JSON consumers can `jq '.manifest_id'` without descending into
    /// `result`.
    /// 回聲供 trace 關聯；與 `result.manifest_id` 同值，使 JSON 消費者可
    /// `jq '.manifest_id'` 而不必下到 `result`。
    manifest_id: &'a str,
    /// V3 §12 #11 invariant — surfaces at envelope level for jq-friendly
    /// access; identical to `result.execution_confidence`.
    /// V3 §12 #11 不變量 — 於 envelope 層揭露便於 jq 存取；與
    /// `result.execution_confidence` 同值。
    execution_confidence: &'a str,
    result: &'a ReplayResult,
}

// ─────────────────────────────────────────────────────────────────────────
// Public API / 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// Write the replay report to disk and return the JSON file path.
///
/// 將 replay report 寫入 disk 並回傳 JSON file 路徑。
///
/// Semantics (EN):
///   1. Ensures `output_dir` exists (creates if missing).
///   2. Serialises `ReportEnvelope` to pretty JSON.
///   3. Writes `<output_dir>/replay_report.json`.
///   4. Writes `<output_dir>/replay_report.summary.txt` (best-effort; a
///      summary write failure does NOT shadow a successful JSON write —
///      summary IS still considered an error path for callers who want both).
///
/// 語意（中）：
///   1. 確保 `output_dir` 存在（不存在則建立）。
///   2. 將 `ReportEnvelope` 序列化為 pretty JSON。
///   3. 寫 `<output_dir>/replay_report.json`。
///   4. 寫 `<output_dir>/replay_report.summary.txt`（best-effort；summary
///      寫入失敗**不**遮蔽 JSON 寫入成功 — 但仍視為 caller 的 error path
///      若 caller 期待兩者皆成功）。
///
/// SAFETY / 不變量:
///   - `result.execution_confidence` is propagated verbatim (V3 §12 #11).
///   - The function is idempotent: a second call with the same `output_dir`
///     and `result` overwrites the previous report. No append, no lock.
///
/// SAFETY / 不變量：
///   - `result.execution_confidence` 原樣傳遞（V3 §12 #11）。
///   - 函式 idempotent：以同 `output_dir` + `result` 二次呼叫會覆蓋前次
///     report。無 append、無 lock。
pub fn write_replay_report(
    output_dir: &Path,
    result: &ReplayResult,
) -> Result<PathBuf, ReportError> {
    // Step 1: ensure output dir.
    // Step 1：確保 output dir 存在。
    if !output_dir.exists() {
        std::fs::create_dir_all(output_dir).map_err(|e| ReportError::OutputDirCreate {
            path: output_dir.to_path_buf(),
            source: e,
        })?;
    }

    // Step 2: serialise.
    // Step 2：序列化。
    let envelope = ReportEnvelope {
        schema_version: 1,
        generated_at_ms: now_ms(),
        manifest_id: &result.manifest_id,
        execution_confidence: &result.execution_confidence,
        result,
    };
    let json = serde_json::to_string_pretty(&envelope)
        .map_err(|e| ReportError::JsonSerialize { source: e })?;

    // Step 3: write JSON.
    // Step 3：寫 JSON。
    let json_path = output_dir.join("replay_report.json");
    std::fs::write(&json_path, json.as_bytes()).map_err(|e| ReportError::JsonWrite {
        path: json_path.clone(),
        source: e,
    })?;

    // Step 4: write summary (best-effort error surfacing).
    // Step 4：寫 summary（盡力錯誤揭露）。
    let summary = format_summary(result);
    let summary_path = output_dir.join("replay_report.summary.txt");
    std::fs::write(&summary_path, summary.as_bytes()).map_err(|e| ReportError::SummaryWrite {
        path: summary_path,
        source: e,
    })?;

    Ok(json_path)
}

/// Render a short human-readable summary.
///
/// 產出簡短的人可讀 summary。
///
/// Format (EN):
///
/// ```text
/// replay_report.summary.txt
/// manifest_id: <id>
/// status: <label>
/// execution_confidence: none
/// events_processed: N
/// fills_emitted: M
/// starting_balance: 10000
/// ending_balance: 10005
/// net_pnl: 5
/// guard_enforce_runtime_calls: K
/// abort_reason: -|<text>
/// ```
///
/// 格式（中）：見 EN。
fn format_summary(result: &ReplayResult) -> String {
    let abort = match &result.diagnostics.abort_reason {
        Some(s) => s.as_str(),
        None => "-",
    };
    format!(
        "replay_report.summary.txt\n\
         manifest_id: {}\n\
         status: {}\n\
         execution_confidence: {}\n\
         events_processed: {}\n\
         fills_emitted: {}\n\
         starting_balance: {}\n\
         ending_balance: {}\n\
         net_pnl: {}\n\
         guard_enforce_runtime_calls: {}\n\
         last_action_label: {}\n\
         abort_reason: {}\n",
        result.manifest_id,
        result.status.label(),
        result.execution_confidence,
        result.pnl_summary.events_processed,
        result.pnl_summary.fills_emitted,
        result.pnl_summary.starting_balance,
        result.pnl_summary.ending_balance,
        result.pnl_summary.net_pnl,
        result.diagnostics.guard_enforce_runtime_calls,
        result.diagnostics.last_action_label,
        abort,
    )
}

// ─────────────────────────────────────────────────────────────────────────
// Internal helpers / 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// Wallclock now in unix ms (UTC). Encapsulated so future test injection
/// can stub a deterministic timestamp.
///
/// 牆鐘 now（UTC ms）。封裝以便未來 test 注入確定性時戳。
fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use crate::replay::runner::{
        PnlSummary, ReplayDiagnostics, ReplayResult, ReplayStatus, SimulatedFill,
    };
    use tempfile::tempdir;

    fn fixture_result() -> ReplayResult {
        ReplayResult {
            manifest_id: "exp_test_1".into(),
            status: ReplayStatus::Completed,
            execution_confidence: "none".into(),
            fills: vec![SimulatedFill {
                ts_ms: 1,
                symbol: "BTCUSDT".into(),
                side: "long".into(),
                qty: 1.0,
                price: 100.0,
                evidence_source_tier: "synthetic_replay".into(),
            }],
            pnl_summary: PnlSummary {
                events_processed: 3,
                fills_emitted: 1,
                starting_balance: 10_000.0,
                ending_balance: 10_005.0,
                net_pnl: 5.0,
            },
            diagnostics: ReplayDiagnostics {
                guard_enforce_runtime_calls: 3,
                last_action_label: "on_event:BTCUSDT@3".into(),
                abort_reason: None,
            },
        }
    }

    #[test]
    fn write_creates_json_and_summary() {
        let tmp = tempdir().unwrap();
        let r = fixture_result();
        let p = write_replay_report(tmp.path(), &r).unwrap();
        assert!(p.exists());
        let summary = tmp.path().join("replay_report.summary.txt");
        assert!(summary.exists());

        // JSON parses back / JSON 可解析回。
        let raw = std::fs::read_to_string(&p).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(v["schema_version"], 1);
        assert_eq!(v["manifest_id"], "exp_test_1");
        assert_eq!(v["execution_confidence"], "none");
        assert_eq!(v["result"]["status"]["kind"], "completed");
        assert_eq!(v["result"]["fills"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn write_creates_missing_output_dir() {
        let tmp = tempdir().unwrap();
        let nested = tmp.path().join("nested").join("does_not_exist");
        let r = fixture_result();
        let p = write_replay_report(&nested, &r).unwrap();
        assert!(p.exists());
    }

    #[test]
    fn execution_confidence_is_propagated_verbatim() {
        let tmp = tempdir().unwrap();
        let mut r = fixture_result();
        // Even if a hypothetical caller (not in this codebase) tried to set
        // confidence to something else, the writer must propagate verbatim.
        // 即便假設的 caller（不存在於此 codebase）嘗試設定 confidence 為其他
        // 值，writer 必原樣傳遞。
        r.execution_confidence = "limited".into();
        write_replay_report(tmp.path(), &r).unwrap();
        let raw = std::fs::read_to_string(tmp.path().join("replay_report.json")).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(v["execution_confidence"], "limited");
        assert_eq!(v["result"]["execution_confidence"], "limited");
    }

    #[test]
    fn summary_contains_status_and_pnl() {
        let tmp = tempdir().unwrap();
        let r = fixture_result();
        write_replay_report(tmp.path(), &r).unwrap();
        let summary =
            std::fs::read_to_string(tmp.path().join("replay_report.summary.txt")).unwrap();
        assert!(summary.contains("status: completed"));
        assert!(summary.contains("net_pnl: 5"));
        assert!(summary.contains("execution_confidence: none"));
    }
}
