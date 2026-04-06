//! JSONL fallback writer — persists market data to file when PG is unavailable.
//! JSONL 回退寫入器 — PG 不可用時將市場數據持久化到文件。
//!
//! MODULE_NOTE (EN): Writes MarketDataMsg as JSON lines to a fallback file when the
//!   DbPool reports 3+ consecutive failures. Recovery is manual via scripts/recover_jsonl.sh
//!   and COPY FROM (W7 audit: no auto-recovery scope creep).
//! MODULE_NOTE (中): 當 DbPool 報告 3+ 次連續失敗時，將 MarketDataMsg 以 JSON 行格式
//!   寫入回退文件。恢復為手動操作（W7 審計：不做自動恢復以避免範圍膨脹）。

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use tracing::{info, warn};

/// JSONL fallback writer for market data persistence when PG fails.
/// PG 失敗時市場數據的 JSONL 回退寫入器。
pub struct FallbackWriter {
    dir: PathBuf,
    current_file: Option<std::fs::File>,
    current_file_lines: u64,
    /// Total lines written across all files / 所有文件的總寫入行數
    total_written: u64,
    /// Max lines per file before rotation / 每文件最大行數
    max_lines_per_file: u64,
    file_index: u32,
}

impl FallbackWriter {
    /// Create a new fallback writer in the specified directory.
    /// 在指定目錄中創建新的回退寫入器。
    pub fn new(dir: &Path) -> Self {
        if let Err(e) = fs::create_dir_all(dir) {
            warn!(error = %e, "failed to create fallback dir / 創建回退目錄失敗");
        }
        Self {
            dir: dir.to_path_buf(),
            current_file: None,
            current_file_lines: 0,
            total_written: 0,
            max_lines_per_file: 100_000,
            file_index: 0,
        }
    }

    /// Write a single JSON line to the fallback file.
    /// 寫入一行 JSON 到回退文件。
    pub fn write_line(&mut self, json: &str) -> bool {
        // Rotate if needed / 需要時輪換文件
        if self.current_file_lines >= self.max_lines_per_file {
            self.rotate();
        }

        let file = match &mut self.current_file {
            Some(f) => f,
            None => match self.open_new_file() {
                Some(f) => {
                    self.current_file = Some(f);
                    self.current_file.as_mut().unwrap()
                }
                None => return false,
            },
        };

        match writeln!(file, "{}", json) {
            Ok(_) => {
                self.current_file_lines += 1;
                self.total_written += 1;
                true
            }
            Err(e) => {
                warn!(error = %e, "fallback write failed / 回退寫入失敗");
                false
            }
        }
    }

    /// Total lines written across all files / 所有文件的總寫入行數
    pub fn total_lines(&self) -> u64 {
        self.total_written
    }

    fn open_new_file(&mut self) -> Option<std::fs::File> {
        let now = chrono::Utc::now().format("%Y%m%d_%H%M%S");
        let path = self
            .dir
            .join(format!("market_fallback_{}_{}.jsonl", now, self.file_index));
        self.file_index += 1;
        self.current_file_lines = 0;
        match OpenOptions::new().create(true).append(true).open(&path) {
            Ok(f) => {
                info!(path = %path.display(), "fallback file opened / 回退文件已打開");
                Some(f)
            }
            Err(e) => {
                warn!(error = %e, path = %path.display(), "failed to open fallback file / 打開回退文件失敗");
                None
            }
        }
    }

    fn rotate(&mut self) {
        self.current_file = None;
        self.current_file_lines = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_write_and_read_back() {
        let dir = tempfile::tempdir().unwrap();
        let mut writer = FallbackWriter::new(dir.path());
        assert!(writer.write_line(r#"{"type":"kline","symbol":"BTC"}"#));
        assert!(writer.write_line(r#"{"type":"ticker","symbol":"ETH"}"#));
        assert_eq!(writer.total_lines(), 2);

        // Read back / 回讀驗證
        let files: Vec<_> = fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|x| x == "jsonl").unwrap_or(false))
            .collect();
        assert_eq!(files.len(), 1);
        let content = fs::read_to_string(files[0].path()).unwrap();
        let lines: Vec<&str> = content.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("kline"));
        assert!(lines[1].contains("ticker"));
    }

    // ── T-P1-6: failure-rollback / degraded-mode coverage ──

    #[test]
    fn test_open_new_file_failure_returns_false_no_panic() {
        // Pointing the dir at a path that cannot be created (under a regular file)
        // forces open_new_file to return None and write_line should fail gracefully.
        // 將目錄指向一個無法被當作目錄的路徑，open_new_file 返回 None，write_line 應安全失敗。
        let tmp = tempfile::tempdir().unwrap();
        let blocker = tmp.path().join("blocker");
        std::fs::write(&blocker, b"not a dir").unwrap();
        let bad_dir = blocker.join("nested"); // cannot create — parent is a file
        let mut writer = FallbackWriter::new(&bad_dir);
        let ok = writer.write_line("{}");
        assert!(!ok, "write should fail when fallback dir is unusable");
        assert_eq!(writer.total_lines(), 0);
    }

    #[test]
    fn test_total_lines_unchanged_on_open_failure() {
        // Successive failed writes must not increment counters.
        // 連續失敗的寫入不應遞增計數器。
        let tmp = tempfile::tempdir().unwrap();
        let blocker = tmp.path().join("blocker2");
        std::fs::write(&blocker, b"x").unwrap();
        let bad_dir = blocker.join("inside");
        let mut writer = FallbackWriter::new(&bad_dir);
        for _ in 0..5 {
            assert!(!writer.write_line("{}"));
        }
        assert_eq!(writer.total_lines(), 0);
    }

    #[test]
    fn test_rotate_resets_per_file_counter() {
        let dir = tempfile::tempdir().unwrap();
        let mut writer = FallbackWriter::new(dir.path());
        writer.max_lines_per_file = 2;
        writer.write_line("{\"i\":1}");
        writer.write_line("{\"i\":2}");
        // Third write should rotate; per-file counter resets to 1 after the first
        // line of the new file. Total counter keeps growing.
        // 第三次寫入會輪換；新文件的第一行寫入後 per-file 為 1，total 持續增長。
        writer.write_line("{\"i\":3}");
        assert_eq!(writer.current_file_lines, 1);
        assert_eq!(writer.total_lines(), 3);
    }

    #[test]
    fn test_file_rotation() {
        let dir = tempfile::tempdir().unwrap();
        let mut writer = FallbackWriter::new(dir.path());
        writer.max_lines_per_file = 3;
        for i in 0..7 {
            writer.write_line(&format!(r#"{{"i":{i}}}"#));
        }
        // total_lines counts across all files (F-2 fix)
        assert_eq!(writer.total_lines(), 7);
        let files: Vec<_> = fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|x| x == "jsonl").unwrap_or(false))
            .collect();
        assert!(files.len() >= 2, "should rotate after 3 lines");
    }
}
