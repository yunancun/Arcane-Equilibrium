//! PIPELINE-SLOT-1 Phase 1 — restart-kind sentinel detection.
//! PIPELINE-SLOT-1 Phase 1 — 重啟類型 sentinel 偵測。
//!
//! MODULE_NOTE (EN): Distinguish operator-initiated restart (`restart_all.sh`,
//!   which writes `settings/runtime/last_shutdown_kind = "manual"` before
//!   SIGTERM) from automatic/crash-only restart (watchdog, systemd, OOM — none
//!   of which run the script). The sentinel is consumed (deleted) on read so a
//!   subsequent crash after a clean boot is correctly classified as `Auto`.
//!   Any unexpected content is treated as `Auto` (safer default: only the
//!   exact word "manual" grants the elevated teardown actions tied to Manual).
//!
//! MODULE_NOTE (中): 區分 operator 主動重啟（`restart_all.sh` 會在 SIGTERM 前
//!   寫入 `settings/runtime/last_shutdown_kind = "manual"`）與自動/崩潰重啟
//!   （watchdog / systemd / OOM 都不跑該 shell）。sentinel 一讀即刪，乾淨啟動
//!   之後又崩潰時正確分類為 `Auto`。任何非預期內容按 `Auto` 處理（更安全的
//!   預設值：只有字串恰為 "manual" 才會觸發 Manual 專屬的 teardown 動作）。

use std::path::Path;

/// Runtime directory name under the settings root.
/// 位於 settings 根目錄下的 runtime 子目錄名。
pub const RUNTIME_DIR: &str = "runtime";
/// Sentinel filename written by `restart_all.sh`.
/// `restart_all.sh` 寫入的 sentinel 檔名。
pub const SENTINEL_FILENAME: &str = "last_shutdown_kind";
/// The only accepted "Manual" payload (exact, case-sensitive after trim).
/// 唯一被接受為 "Manual" 的 payload（trim 後大小寫敏感）。
pub const MANUAL_PAYLOAD: &str = "manual";

/// Classify the previous shutdown.
/// 分類前次關機類型。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RestartKind {
    /// Operator ran `restart_all.sh` (expected path for config/code push).
    /// Operator 主動跑 `restart_all.sh`（推送配置/代碼的正常路徑）。
    Manual,
    /// Anything else: crash, watchdog bounce, systemd auto-restart, OOM,
    /// fresh install with no prior shutdown record, or tampered content.
    /// 其他一切：崩潰、watchdog 拉起、systemd 自動重啟、OOM、初次啟動、
    /// 或 sentinel 內容被竄改。
    Auto,
}

/// Read + consume the sentinel file at `<settings_dir>/runtime/last_shutdown_kind`.
/// Returns `Manual` iff the file exists and its trimmed content is exactly
/// [`MANUAL_PAYLOAD`]; otherwise returns `Auto`. The file is best-effort
/// removed so a subsequent clean-boot-then-crash cycle is correctly classified.
///
/// Never panics: file absence, permission denied, or remove failure all fall
/// through to the correct kind without interrupting startup.
///
/// 讀取並消費 `<settings_dir>/runtime/last_shutdown_kind` sentinel。
/// 檔案存在且 trim 後內容恰為 [`MANUAL_PAYLOAD`] 時回傳 `Manual`，其餘一律
/// 回傳 `Auto`。檔案盡力刪除以便下次乾淨啟動後再崩潰能被正確分類。
///
/// 永不 panic：檔案不存在、無權限、或刪除失敗都不會中斷啟動流程。
pub fn detect_and_consume(settings_dir: &Path) -> RestartKind {
    let path = settings_dir.join(RUNTIME_DIR).join(SENTINEL_FILENAME);
    let content = match std::fs::read_to_string(&path) {
        Ok(s) => s,
        // File absent → Auto (fresh install / post-crash / watchdog bounce).
        // 檔案不存在 → Auto（初次啟動 / 崩潰後 / watchdog 拉起）。
        Err(_) => return RestartKind::Auto,
    };

    let kind = if content.trim() == MANUAL_PAYLOAD {
        RestartKind::Manual
    } else {
        // Garbage content: intentionally NOT Manual — Manual unlocks privileged
        // teardown actions (e.g., clearing authorization.json), which must be
        // gated on an exact-match contract with restart_all.sh.
        // 垃圾內容：刻意不視為 Manual — Manual 會解鎖特權 teardown 動作（如清空
        // authorization.json），必須綁定 restart_all.sh 的精確契約。
        RestartKind::Auto
    };

    // Best-effort removal. If this fails (permissions, race, read-only fs) the
    // next startup may redundantly re-detect the same sentinel; acceptable —
    // we return the classified kind regardless of remove outcome.
    // 盡力刪除。若失敗（權限/競爭/唯讀檔案系統），下次啟動會重覆讀到同一個
    // sentinel；可接受 — 無論刪除是否成功，都回傳已分類的 kind。
    let _ = std::fs::remove_file(&path);

    kind
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Create a sentinel file at `<tmp>/runtime/last_shutdown_kind` with the
    /// given content. Returns the tempdir (must be kept alive for the test).
    fn write_sentinel(content: &str) -> tempfile::TempDir {
        let tmp = tempfile::tempdir().expect("tempdir");
        let runtime = tmp.path().join(RUNTIME_DIR);
        std::fs::create_dir_all(&runtime).expect("create runtime dir");
        std::fs::write(runtime.join(SENTINEL_FILENAME), content).expect("write sentinel");
        tmp
    }

    #[test]
    fn detect_and_consume_present_manual() {
        let tmp = write_sentinel("manual");
        let kind = detect_and_consume(tmp.path());
        assert_eq!(kind, RestartKind::Manual);
        // File must be removed so the next boot does not redundantly re-detect.
        let path = tmp.path().join(RUNTIME_DIR).join(SENTINEL_FILENAME);
        assert!(!path.exists(), "sentinel file should be consumed");
    }

    #[test]
    fn detect_and_consume_absent() {
        let tmp = tempfile::tempdir().expect("tempdir");
        // Don't create runtime dir or sentinel at all.
        let kind = detect_and_consume(tmp.path());
        assert_eq!(kind, RestartKind::Auto);
    }

    #[test]
    fn detect_and_consume_present_garbage() {
        for payload in [
            "",
            "auto",
            "Manual", // case-sensitive after trim
            "MANUAL",
            "manual\nextra",
            "crash",
            "{\"kind\":\"manual\"}",
        ] {
            let tmp = write_sentinel(payload);
            let kind = detect_and_consume(tmp.path());
            assert_eq!(
                kind,
                RestartKind::Auto,
                "payload {payload:?} must map to Auto (strict match on 'manual' only)"
            );
            // Garbage is still consumed so operator observes the sentinel
            // vanishing confirming the engine saw it.
            let path = tmp.path().join(RUNTIME_DIR).join(SENTINEL_FILENAME);
            assert!(
                !path.exists(),
                "garbage sentinel should still be removed for payload {payload:?}"
            );
        }
    }

    #[test]
    fn detect_and_consume_present_manual_whitespace() {
        // Leading/trailing whitespace + trailing newline trimmed.
        // 前後空白與結尾換行應被 trim 掉。
        for payload in ["manual\n", "  manual  ", "\tmanual\t\n"] {
            let tmp = write_sentinel(payload);
            let kind = detect_and_consume(tmp.path());
            assert_eq!(
                kind,
                RestartKind::Manual,
                "payload {payload:?} should trim to Manual"
            );
        }
    }

    #[test]
    fn detect_and_consume_missing_runtime_dir_is_auto() {
        // When settings_dir exists but runtime/ subdir does not — common for
        // fresh installs — we must classify Auto without creating anything.
        // settings_dir 存在但 runtime/ 子目錄不存在（常見於初次安裝）時應分類
        // 為 Auto 且不建立任何檔案。
        let tmp = tempfile::tempdir().expect("tempdir");
        let kind = detect_and_consume(tmp.path());
        assert_eq!(kind, RestartKind::Auto);
        // Confirm we did not accidentally create the runtime dir.
        assert!(!tmp.path().join(RUNTIME_DIR).exists());
    }
}
