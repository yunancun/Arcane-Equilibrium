//! Persistence — JSON debounced write + JSONL audit (R04-8).
//! 持久化 — JSON 去抖寫入 + JSONL 審計。
//!
//! State persistence: debounced JSON write (5s interval).
//! Audit: JSONL append-only.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::time::Instant;
use tracing::{error, debug};

/// Debounced JSON state writer — flushes at most once per interval.
/// 去抖 JSON 狀態寫入器 — 最多每間隔刷新一次。
pub struct StateWriter {
    path: PathBuf,
    interval_ms: u64,
    last_write: Option<Instant>,
}

impl StateWriter {
    pub fn new(path: &Path, interval_ms: u64) -> Self {
        Self {
            path: path.to_path_buf(),
            interval_ms,
            last_write: None,
        }
    }

    /// Write state if enough time has passed since last write.
    /// 如果距上次寫入已過足夠時間，則寫入狀態。
    pub fn maybe_write<T: Serialize>(&mut self, state: &T) -> bool {
        let now = Instant::now();
        if let Some(last) = self.last_write {
            if now.duration_since(last).as_millis() < self.interval_ms as u128 {
                return false;
            }
        }

        match serde_json::to_string_pretty(state) {
            Ok(json) => {
                if let Err(e) = std::fs::write(&self.path, &json) {
                    error!(path = %self.path.display(), error = %e, "state write failed / 狀態寫入失敗");
                    return false;
                }
                self.last_write = Some(now);
                debug!(path = %self.path.display(), "state written / 狀態已寫入");
                true
            }
            Err(e) => {
                error!(error = %e, "state serialize failed / 狀態序列化失敗");
                false
            }
        }
    }

    /// Force immediate write (for shutdown).
    /// 強制立即寫入（用於關閉）。
    pub fn force_write<T: Serialize>(&mut self, state: &T) -> bool {
        self.last_write = None;
        self.maybe_write(state)
    }
}

/// JSONL append-only audit writer.
/// JSONL 追加模式審計寫入器。
pub struct AuditWriter {
    path: PathBuf,
}

impl AuditWriter {
    pub fn new(path: &Path) -> Self {
        Self { path: path.to_path_buf() }
    }

    /// Append a single audit record as JSONL.
    /// 追加單條審計記錄為 JSONL。
    pub fn append<T: Serialize>(&self, record: &T) -> bool {
        match serde_json::to_string(record) {
            Ok(json) => {
                use std::io::Write;
                let mut file = match std::fs::OpenOptions::new()
                    .create(true).append(true).open(&self.path)
                {
                    Ok(f) => f,
                    Err(e) => {
                        error!(path = %self.path.display(), error = %e, "audit open failed");
                        return false;
                    }
                };
                if let Err(e) = writeln!(file, "{}", json) {
                    error!(error = %e, "audit write failed");
                    return false;
                }
                true
            }
            Err(e) => {
                error!(error = %e, "audit serialize failed");
                false
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::Read;

    #[test]
    fn test_state_writer_debounce() {
        let dir = std::env::temp_dir().join("oc_test_persist");
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("test_state.json");

        let mut w = StateWriter::new(&path, 5000);
        let data = json!({"balance": 10000});

        // First write succeeds
        assert!(w.maybe_write(&data));
        // Second write debounced
        assert!(!w.maybe_write(&data));

        // Verify content
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("10000"));

        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_state_writer_force() {
        let dir = std::env::temp_dir().join("oc_test_persist2");
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("test_force.json");

        let mut w = StateWriter::new(&path, 999_999);
        let data = json!({"test": true});
        assert!(w.force_write(&data));

        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_audit_writer_append() {
        let dir = std::env::temp_dir().join("oc_test_audit");
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("test_audit.jsonl");
        let _ = std::fs::remove_file(&path);

        let w = AuditWriter::new(&path);
        assert!(w.append(&json!({"event": "trade", "id": 1})));
        assert!(w.append(&json!({"event": "trade", "id": 2})));

        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<_> = content.lines().collect();
        assert_eq!(lines.len(), 2);

        std::fs::remove_file(&path).ok();
    }
}
