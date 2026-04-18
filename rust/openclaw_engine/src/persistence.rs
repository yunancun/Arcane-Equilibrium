//! Persistence — JSON debounced write + JSONL audit (R04-8).
//! 持久化 — JSON 去抖寫入 + JSONL 審計。
//!
//! State persistence: debounced JSON write (5s interval).
//! Audit: JSONL append-only.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::time::Instant;
use tracing::{debug, error};

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
                // Atomic write: write to .tmp then rename to prevent readers seeing partial data.
                // 原子寫入：先寫 .tmp 再 rename，防止讀取端看到半寫數據。
                let tmp_path = self.path.with_extension("json.tmp");
                if let Err(e) = std::fs::write(&tmp_path, &json) {
                    error!(path = %tmp_path.display(), error = %e, "state write failed / 狀態寫入失敗");
                    return false;
                }
                // MAJOR-1 fix: Tighten permissions to 0600 (owner r/w only) before the
                // rename, because the snapshot may contain balance / position info.
                // fail-soft: a chmod error is logged but does not block the write —
                // the tmp file is already owner-created, so the usual default umask
                // keeps it reasonably tight even if this explicit call fails.
                // MAJOR-1 修復：rename 前收緊權限為 0600（僅所有者讀寫）—
                // 快照可能包含餘額/持倉資訊。fail-soft：chmod 失敗僅 warn，
                // 不阻塞寫入（tmp 檔已由本 process 建立，umask 已提供合理權限）。
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    if let Err(e) =
                        std::fs::set_permissions(&tmp_path, std::fs::Permissions::from_mode(0o600))
                    {
                        tracing::warn!(
                            path = %tmp_path.display(),
                            error = %e,
                            "chmod 0600 failed (fail-soft) / chmod 0600 失敗（fail-soft）"
                        );
                    }
                }
                if let Err(e) = std::fs::rename(&tmp_path, &self.path) {
                    error!(path = %self.path.display(), error = %e, "state rename failed / 狀態重命名失敗");
                    return false;
                }
                self.last_write = Some(now);
                debug!(path = %self.path.display(), "state written (atomic) / 狀態已寫入（原子）");
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

/// Dual snapshot writer — writes to per-engine file + optional backward-compat file (3E-5).
/// 雙快照寫入器 — 寫入每引擎文件 + 可選向後兼容文件。
pub struct DualStateWriter {
    primary: StateWriter,
    compat: Option<StateWriter>,
}

impl DualStateWriter {
    pub fn new(primary: StateWriter, compat: Option<StateWriter>) -> Self {
        Self { primary, compat }
    }

    pub fn maybe_write<T: Serialize>(&mut self, state: &T) -> bool {
        let wrote = self.primary.maybe_write(state);
        if wrote {
            if let Some(ref mut c) = self.compat {
                c.force_write(state);
            }
        }
        wrote
    }

    pub fn force_write<T: Serialize>(&mut self, state: &T) -> bool {
        let wrote = self.primary.force_write(state);
        if let Some(ref mut c) = self.compat {
            c.force_write(state);
        }
        wrote
    }
}

/// JSONL append-only audit writer.
/// JSONL 追加模式審計寫入器。
pub struct AuditWriter {
    path: PathBuf,
}

impl AuditWriter {
    pub fn new(path: &Path) -> Self {
        Self {
            path: path.to_path_buf(),
        }
    }

    /// Append a single audit record as JSONL.
    /// 追加單條審計記錄為 JSONL。
    pub fn append<T: Serialize>(&self, record: &T) -> bool {
        match serde_json::to_string(record) {
            Ok(json) => {
                use std::io::Write;
                let is_new = !self.path.exists();
                let mut file = match std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&self.path)
                {
                    Ok(f) => f,
                    Err(e) => {
                        error!(path = %self.path.display(), error = %e, "audit open failed");
                        return false;
                    }
                };
                // m-8: Set chmod 0600 on newly created audit files.
                // m-8：新建審計文件設定 chmod 0600。
                #[cfg(unix)]
                if is_new {
                    use std::os::unix::fs::PermissionsExt;
                    let _ = std::fs::set_permissions(
                        &self.path,
                        std::fs::Permissions::from_mode(0o600),
                    );
                }
                #[cfg(not(unix))]
                let _ = is_new;
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

    #[test]
    fn test_dual_state_writer_writes_both() {
        let dir = std::env::temp_dir().join("oc_test_dual");
        std::fs::create_dir_all(&dir).ok();
        let primary_path = dir.join("pipeline_snapshot_paper.json");
        let compat_path = dir.join("pipeline_snapshot.json");
        let _ = std::fs::remove_file(&primary_path);
        let _ = std::fs::remove_file(&compat_path);

        let primary = StateWriter::new(&primary_path, 5_000);
        let compat = StateWriter::new(&compat_path, 5_000);
        let mut dual = DualStateWriter::new(primary, Some(compat));

        let data = json!({"pipeline_kind": "paper", "balance": 10000});
        assert!(dual.force_write(&data));

        // Both files should exist with correct content
        // 兩個文件都應該存在且包含正確內容
        let p_content = std::fs::read_to_string(&primary_path).unwrap();
        let c_content = std::fs::read_to_string(&compat_path).unwrap();
        assert!(p_content.contains("paper"));
        assert!(c_content.contains("paper"));

        std::fs::remove_file(&primary_path).ok();
        std::fs::remove_file(&compat_path).ok();
    }

    /// MAJOR-1 regression test: snapshot file must be chmod 0600 on Unix.
    /// MAJOR-1 回歸測試：快照檔在 Unix 上必須是 0600。
    #[cfg(unix)]
    #[test]
    fn test_state_writer_chmod_0600() {
        use std::os::unix::fs::PermissionsExt;
        let dir = std::env::temp_dir().join("oc_test_chmod_0600");
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("test_chmod.json");
        let _ = std::fs::remove_file(&path);

        let mut w = StateWriter::new(&path, 1);
        let data = json!({"balance": 123});
        assert!(w.maybe_write(&data));

        let meta = std::fs::metadata(&path).expect("snapshot must exist");
        // mode() returns the full stat mode; mask to permission bits only.
        // mode() 回傳整個 stat mode，只比對權限位。
        let mode = meta.permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "snapshot must be chmod 0600, got {:o}", mode);

        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_dual_state_writer_no_compat() {
        let dir = std::env::temp_dir().join("oc_test_dual_no_compat");
        std::fs::create_dir_all(&dir).ok();
        let primary_path = dir.join("pipeline_snapshot_demo.json");
        let compat_path = dir.join("pipeline_snapshot.json");
        let _ = std::fs::remove_file(&primary_path);
        let _ = std::fs::remove_file(&compat_path);

        let primary = StateWriter::new(&primary_path, 5_000);
        let mut dual = DualStateWriter::new(primary, None);

        let data = json!({"pipeline_kind": "demo"});
        assert!(dual.force_write(&data));

        // Only primary file should exist
        // 只有主文件應該存在
        assert!(primary_path.exists());
        assert!(!compat_path.exists());

        std::fs::remove_file(&primary_path).ok();
    }

    /// FIX-15: Three concurrent writers to separate per-pipeline files don't corrupt.
    /// Simulates Paper/Demo/Live pipelines writing concurrently from 3 threads.
    /// FIX-15：三個並發寫入器寫入各自管線文件不會互相損壞。
    /// 模擬 Paper/Demo/Live 管線從 3 個線程並發寫入。
    #[test]
    fn test_three_pipeline_concurrent_writes() {
        let dir = std::env::temp_dir().join("oc_test_3pipeline_concurrent");
        std::fs::create_dir_all(&dir).ok();

        let kinds = ["paper", "demo", "live"];
        let paths: Vec<PathBuf> = kinds
            .iter()
            .map(|k| dir.join(format!("pipeline_snapshot_{}.json", k)))
            .collect();
        for p in &paths {
            let _ = std::fs::remove_file(p);
        }

        // Spawn 3 threads, each writing 50 snapshots to its own file
        // 各啟動 3 個線程，每個寫 50 次快照到各自文件
        let handles: Vec<_> = kinds
            .iter()
            .enumerate()
            .map(|(i, kind)| {
                let path = paths[i].clone();
                let kind = kind.to_string();
                std::thread::spawn(move || {
                    let mut w = StateWriter::new(&path, 0); // 0ms debounce for stress
                    for tick in 0..50 {
                        let data = json!({
                            "pipeline_kind": kind,
                            "tick": tick,
                            "balance": 10000.0 + tick as f64,
                        });
                        w.force_write(&data);
                    }
                })
            })
            .collect();

        for h in handles {
            h.join().expect("thread panicked");
        }

        // Verify each file contains the correct pipeline_kind and last tick
        // 驗證每個文件包含正確的 pipeline_kind 和最後的 tick
        for (i, kind) in kinds.iter().enumerate() {
            let content = std::fs::read_to_string(&paths[i])
                .unwrap_or_else(|_| panic!("{} snapshot missing", kind));
            let parsed: serde_json::Value = serde_json::from_str(&content)
                .unwrap_or_else(|_| panic!("{} snapshot corrupted", kind));
            assert_eq!(
                parsed["pipeline_kind"], *kind,
                "{} has wrong pipeline_kind",
                kind
            );
            assert_eq!(parsed["tick"], 49, "{} didn't reach last tick", kind);
            // Verify no cross-contamination
            assert!(
                !content.contains(if *kind == "paper" {
                    "\"demo\""
                } else {
                    "\"paper\""
                }),
                "cross-contamination in {} snapshot",
                kind
            );
        }

        // Cleanup
        for p in &paths {
            std::fs::remove_file(p).ok();
        }
    }
}
