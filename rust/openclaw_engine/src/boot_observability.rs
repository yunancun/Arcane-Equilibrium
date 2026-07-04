//! MODULE_NOTE
//! 模塊用途：P0-1c boot/build SHA 可觀測面（引擎側）。暴露 build.rs 編譯期嵌入的
//! git SHA / build 時間常量，並於啟動時 append 一行 boot 紀錄到
//! `OPENCLAW_DATA_DIR/boot_history.jsonl`（與 Python control API 共檔，
//! 以 `component` 欄位區分寫入者）。
//! 主要函數：`boot_record_json`（純函數，schema 唯一定義點）、`append_boot_record`。
//! 依賴：serde_json、chrono、std::fs。
//! 硬邊界：純可觀測性面 —— 寫入失敗必須由呼叫端 fail-soft（記 warn 不阻斷引擎
//! 啟動），絕不介入任何交易 / 風控 / 授權路徑。
//!
//! 為什麼需要：2026-07-03 冷審計 P0-1 —— 重啟未 rebuild 無人發現，根因是引擎
//! 與 uvicorn 都沒有 build/boot SHA 可觀測面。本模塊讓「運行進程的代碼世代」
//! 可經持久 log（boot_history.jsonl）、startup banner 與 IPC `get_state` 對表。

use std::io::Write;
use std::path::{Path, PathBuf};

/// 編譯期嵌入的 git SHA（build.rs `git rev-parse HEAD`；git 缺席時 = "unknown"）。
pub const BUILD_GIT_SHA: &str = env!("OPENCLAW_BUILD_GIT_SHA");

/// 編譯期嵌入的 build 時間（UTC RFC3339 秒級）。
pub const BUILD_TIME: &str = env!("OPENCLAW_BUILD_TIME");

/// boot 紀錄檔名（append-only JSONL，一行一次 boot）。
pub const BOOT_HISTORY_FILENAME: &str = "boot_history.jsonl";

/// 組出本次 boot 的單行紀錄（純函數，schema 唯一定義點，供測試釘格式）。
///
/// 欄位：component / boot_ts / build_sha / build_time / pid / binary_path。
/// `binary_path` 解析失敗 fallback "unknown"（可觀測性欄位不因平台差異而 panic）。
pub fn boot_record_json() -> serde_json::Value {
    serde_json::json!({
        "component": "openclaw_engine",
        "boot_ts": chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
        "build_sha": BUILD_GIT_SHA,
        "build_time": BUILD_TIME,
        "pid": std::process::id(),
        "binary_path": std::env::current_exe()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|_| "unknown".to_string()),
    })
}

/// 把本次 boot 紀錄 append 到 `data_dir/boot_history.jsonl`，回傳寫入路徑。
///
/// 為什麼 append-only：boot 歷史是審計證據（誰在何時以哪個世代啟動），
/// 覆寫會毀掉「重啟未 rebuild」這類事故的重建能力。
/// 錯誤直接上拋 `std::io::Error`，由呼叫端（main.rs）fail-soft 記 warn。
pub fn append_boot_record(data_dir: &Path) -> std::io::Result<PathBuf> {
    std::fs::create_dir_all(data_dir)?;
    let path = data_dir.join(BOOT_HISTORY_FILENAME);
    let mut line = boot_record_json().to_string();
    line.push('\n');
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;
    file.write_all(line.as_bytes())?;
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// build SHA 常量形狀：非空，且只允許「40 位 hex」或 fallback "unknown" 兩種。
    #[test]
    fn build_git_sha_is_full_hex_or_unknown() {
        assert!(!BUILD_GIT_SHA.is_empty());
        let is_full_hex =
            BUILD_GIT_SHA.len() == 40 && BUILD_GIT_SHA.chars().all(|c| c.is_ascii_hexdigit());
        assert!(
            is_full_hex || BUILD_GIT_SHA == "unknown",
            "BUILD_GIT_SHA 必須是 40 位 hex 或 'unknown'，實際：{BUILD_GIT_SHA}"
        );
    }

    /// boot 紀錄 schema：六個欄位齊備且型別正確（P0-1c 驗收要求的格式測試）。
    #[test]
    fn boot_record_schema_has_required_fields() {
        let record = boot_record_json();
        assert_eq!(record["component"], "openclaw_engine");
        // boot_ts 必須可被 chrono 解析回 RFC3339
        let boot_ts = record["boot_ts"].as_str().expect("boot_ts 必須是字串");
        assert!(
            chrono::DateTime::parse_from_rfc3339(boot_ts).is_ok(),
            "boot_ts 必須是 RFC3339，實際：{boot_ts}"
        );
        assert_eq!(record["build_sha"].as_str(), Some(BUILD_GIT_SHA));
        assert_eq!(record["build_time"].as_str(), Some(BUILD_TIME));
        assert!(record["pid"].as_u64().is_some_and(|pid| pid > 0));
        assert!(!record["binary_path"]
            .as_str()
            .expect("binary_path 必須是字串")
            .is_empty());
    }

    /// append 語意：兩次 boot 寫兩行，每行都是獨立可解析的 JSON（append-only 不覆寫）。
    #[test]
    fn append_boot_record_appends_parseable_lines() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = append_boot_record(dir.path()).expect("first append");
        assert_eq!(path, dir.path().join(BOOT_HISTORY_FILENAME));
        append_boot_record(dir.path()).expect("second append");

        let content = std::fs::read_to_string(&path).expect("read back");
        let lines: Vec<&str> = content.lines().collect();
        assert_eq!(lines.len(), 2, "兩次 boot 必須是兩行（append 不覆寫）");
        for line in lines {
            let parsed: serde_json::Value =
                serde_json::from_str(line).expect("每行必須是合法 JSON");
            assert_eq!(parsed["component"], "openclaw_engine");
        }
    }

    /// data_dir 不存在時必須自動建立（首次部署 / 全新 OPENCLAW_DATA_DIR 場景）。
    #[test]
    fn append_boot_record_creates_missing_data_dir() {
        let dir = tempfile::tempdir().expect("tempdir");
        let nested = dir.path().join("nested").join("data_dir");
        let path = append_boot_record(&nested).expect("append into missing dir");
        assert!(path.exists());
    }
}
