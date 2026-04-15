//! Canary JSONL writer — dedicated task with bounded mpsc + BufWriter + size rotation.
//! 灰度 JSONL 寫入器 — 專用任務 + 有界 mpsc + BufWriter + 大小輪轉。
//!
//! MODULE_NOTE (EN): ENGINE-HEAL-FIX-PHASE1 R1 + FUP-3 — moves canary JSONL write
//!   off the event consumer hot path. Previously `writeln!(&std::fs::File, ...)`
//!   was called synchronously in the `event_rx.recv()` select arm on every tick;
//!   at ~280 tps × 2.5 KB × 100 GB+ file this periodically stalled the live
//!   consumer loop for >120s and tripped Fix 4 WS-stale self-cancel (2026-04-15
//!   02:03 UTC incident; see docs/worklogs/2026-04-15--engine_2000_stall_postmortem.md).
//!   Now: producer calls `try_send(record)` on a 4096-slot mpsc; on full the
//!   record is dropped with a rate-limited warn. A single dedicated tokio task
//!   owns the BufWriter, flush timer, and size-based rotation.
//!
//! Env vars (read once at spawn time):
//!   OPENCLAW_CANARY_MODE=1            — enable record build + write (required)
//!   OPENCLAW_DISABLE_CANARY_DUMP=1    — kill-switch; overrides CANARY_MODE
//!                                       (records are not built either — saves CPU)
//!   OPENCLAW_CANARY_ROTATE_MB=<u64>   — rotation threshold in MB (default 1024 = 1 GB)
//!   OPENCLAW_CANARY_MAX_ROTATED=<n>   — rotated files to keep (default 3)
//!
//! MODULE_NOTE (中): ENGINE-HEAL-FIX-PHASE1 R1 + FUP-3 — 將灰度 JSONL 寫盤移出
//!   event consumer 熱路徑。原本 `writeln!(&std::fs::File, ...)` 在
//!   `event_rx.recv()` select arm 同步調用，~280 tps × 2.5 KB × 100 GB+ 檔案
//!   週期性卡住 live consumer loop > 120s 觸發 Fix 4 自殺（2026-04-15 02:03 UTC）。
//!   現在：producer `try_send(record)` 入 4096 slot mpsc，滿則 warn 丟棄；
//!   單一專用 tokio 任務擁有 BufWriter、flush 定時器、與 size rotation。

use crate::pipeline_types::CanaryRecord;
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

const CHANNEL_CAPACITY: usize = 4096;
const BUF_WRITER_CAPACITY: usize = 64 * 1024;
const FLUSH_INTERVAL_MS: u64 = 200;
const DEFAULT_ROTATE_MB: u64 = 1024;
const DEFAULT_MAX_ROTATED: usize = 3;

/// Clonable handle passed into every pipeline. When `is_enabled()` returns false,
/// producers skip the record build step entirely (see `pipeline.canary_mode`).
/// 可 clone 的控制代碼 — 分發到每條管線。`is_enabled()` 為 false 時 producer
/// 完全跳過 record 建構（見 `pipeline.canary_mode`），零成本。
#[derive(Clone)]
pub struct CanaryWriterHandle {
    tx: Option<mpsc::Sender<CanaryRecord>>,
}

impl CanaryWriterHandle {
    /// Handle with the feature off — producer no-op.
    /// 停用狀態 — producer 零成本。
    pub fn disabled() -> Self {
        Self { tx: None }
    }

    /// Feature-on indicator. Event consumer uses this to set
    /// `pipeline.canary_mode` so `maybe_canary_record` actually builds records.
    /// 啟用指示 — event consumer 據此設置 `pipeline.canary_mode`。
    pub fn is_enabled(&self) -> bool {
        self.tx.is_some()
    }

    /// Non-blocking send. On channel full → warn + drop (observability beats
    /// blocking the tick consumer). On writer task exit → silent drop.
    /// 非阻塞發送 — 滿則 warn 丟棄；寫入任務退出則靜默丟棄。
    pub fn try_send(&self, record: CanaryRecord) {
        if let Some(ref tx) = self.tx {
            match tx.try_send(record) {
                Ok(()) => {}
                Err(mpsc::error::TrySendError::Full(_)) => {
                    warn!(
                        "canary_writer channel full — record dropped \
                         / 灰度通道滿，記錄丟棄"
                    );
                }
                Err(mpsc::error::TrySendError::Closed(_)) => {
                    // Writer task ended — nothing to recover.
                    // 寫入任務已退出 — 無需恢復。
                }
            }
        }
    }
}

/// Spawn the canary writer task if the feature is enabled. Safe to call once at
/// engine startup; returns a `CanaryWriterHandle` (clone into every pipeline).
/// 啟動灰度寫入任務（如啟用）。引擎啟動時呼叫一次，回傳 handle（clone 到每條管線）。
pub fn spawn(data_path: PathBuf, cancel: CancellationToken) -> CanaryWriterHandle {
    let canary_mode = std::env::var("OPENCLAW_CANARY_MODE").unwrap_or_default() == "1";
    let disable_dump =
        std::env::var("OPENCLAW_DISABLE_CANARY_DUMP").unwrap_or_default() == "1";
    if !canary_mode {
        return CanaryWriterHandle::disabled();
    }
    if disable_dump {
        info!(
            "canary mode disabled by OPENCLAW_DISABLE_CANARY_DUMP=1 (overrides CANARY_MODE) \
             / 旗標關閉灰度寫盤（覆寫 CANARY_MODE）"
        );
        return CanaryWriterHandle::disabled();
    }

    let rotate_mb: u64 = std::env::var("OPENCLAW_CANARY_ROTATE_MB")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_ROTATE_MB);
    let max_rotated: usize = std::env::var("OPENCLAW_CANARY_MAX_ROTATED")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_MAX_ROTATED);

    let (tx, rx) = mpsc::channel::<CanaryRecord>(CHANNEL_CAPACITY);
    let canary_path = data_path.join("engine_results.jsonl");
    info!(
        path = %canary_path.display(),
        rotate_mb,
        max_rotated,
        channel_capacity = CHANNEL_CAPACITY,
        "canary writer started / 灰度寫入器已啟動"
    );
    tokio::spawn(run_writer(rx, canary_path, rotate_mb, max_rotated, cancel));
    CanaryWriterHandle { tx: Some(tx) }
}

async fn run_writer(
    mut rx: mpsc::Receiver<CanaryRecord>,
    canary_path: PathBuf,
    rotate_mb: u64,
    max_rotated: usize,
    cancel: CancellationToken,
) {
    let rotate_bytes = rotate_mb.saturating_mul(1024).saturating_mul(1024);
    let (mut bw, mut bytes_written) = match open_writer(&canary_path) {
        Ok(p) => p,
        Err(e) => {
            warn!(
                error = %e,
                path = %canary_path.display(),
                "canary writer failed to open file — exiting task \
                 / 灰度寫入器開檔失敗，任務退出"
            );
            return;
        }
    };
    let mut flush_timer = tokio::time::interval(
        std::time::Duration::from_millis(FLUSH_INTERVAL_MS),
    );
    flush_timer.tick().await;

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                let _ = bw.flush();
            }
            msg = rx.recv() => {
                let Some(record) = msg else { break };
                let Ok(json) = serde_json::to_string(&record) else { continue };
                let wrote = bw.write_all(json.as_bytes()).and_then(|_| bw.write_all(b"\n"));
                match wrote {
                    Ok(()) => bytes_written = bytes_written.saturating_add(json.len() as u64 + 1),
                    Err(e) => {
                        warn!(error = %e, "canary write failed / 灰度寫入失敗");
                        continue;
                    }
                }
                if bytes_written >= rotate_bytes {
                    let _ = bw.flush();
                    drop(bw);
                    if let Err(e) = rotate_file(&canary_path, max_rotated) {
                        warn!(error = %e, "canary rotate failed / 輪轉失敗");
                    }
                    match open_writer(&canary_path) {
                        Ok((new_bw, sz)) => {
                            bw = new_bw;
                            bytes_written = sz;
                        }
                        Err(e) => {
                            warn!(
                                error = %e,
                                "canary reopen after rotate failed — exiting task \
                                 / 輪轉後重新開檔失敗，任務退出"
                            );
                            return;
                        }
                    }
                }
            }
        }
    }
    let _ = bw.flush();
    info!("canary writer stopped / 灰度寫入器已停止");
}

fn open_writer(path: &Path) -> std::io::Result<(BufWriter<File>, u64)> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    let size = file.metadata().map(|m| m.len()).unwrap_or(0);
    Ok((BufWriter::with_capacity(BUF_WRITER_CAPACITY, file), size))
}

fn rotate_file(canary_path: &Path, max_rotated: usize) -> std::io::Result<()> {
    let ts = chrono::Utc::now().format("%Y%m%dT%H%M%SZ").to_string();
    let parent = canary_path.parent().unwrap_or_else(|| Path::new("."));
    let stem = canary_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("engine_results");
    let ext = canary_path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("jsonl");
    let archive_dir = parent.join("engine_logs");
    std::fs::create_dir_all(&archive_dir)?;
    let archived = archive_dir.join(format!("{}-{}.{}", stem, ts, ext));
    std::fs::rename(canary_path, &archived)?;
    debug!(archived = %archived.display(), "canary rotated / 灰度輪轉");
    if let Err(e) = prune_rotated(&archive_dir, stem, ext, max_rotated) {
        warn!(error = %e, "canary prune failed / 輪轉清理失敗");
    }
    Ok(())
}

fn prune_rotated(
    dir: &Path,
    stem: &str,
    ext: &str,
    max_rotated: usize,
) -> std::io::Result<()> {
    let mut entries: Vec<_> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok())
        .filter(|e| {
            let n = e.file_name();
            let s = n.to_string_lossy();
            s.starts_with(stem) && s.ends_with(ext)
        })
        .collect();
    // Oldest first by mtime → truncate tail (oldest) until within cap.
    entries.sort_by_key(|e| e.metadata().and_then(|m| m.modified()).ok());
    while entries.len() > max_rotated {
        let stale = entries.remove(0);
        if let Err(e) = std::fs::remove_file(stale.path()) {
            warn!(
                error = %e,
                path = %stale.path().display(),
                "canary stale file remove failed / 舊輪轉檔刪除失敗"
            );
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn mk_record(n: u64) -> CanaryRecord {
        CanaryRecord {
            schema_version: "test".into(),
            source: "test".into(),
            tick_number: n,
            timestamp_ms: n,
            symbol: "BTCUSDT".into(),
            price: 100.0,
            indicators: None,
            signals: vec![],
            order_intents: vec![],
            paper_state: crate::paper_state::PaperState::new(1000.0).export_state(),
            stats: crate::tick_pipeline::TickStats::default(),
            tick_duration_us: 0,
        }
    }

    #[test]
    fn handle_disabled_is_noop() {
        let h = CanaryWriterHandle::disabled();
        assert!(!h.is_enabled());
        h.try_send(mk_record(1)); // must not panic, no channel
    }

    #[tokio::test]
    async fn spawn_honours_disable_dump() {
        let tmp = TempDir::new().unwrap();
        std::env::set_var("OPENCLAW_CANARY_MODE", "1");
        std::env::set_var("OPENCLAW_DISABLE_CANARY_DUMP", "1");
        let cancel = CancellationToken::new();
        let h = spawn(tmp.path().to_path_buf(), cancel);
        std::env::remove_var("OPENCLAW_CANARY_MODE");
        std::env::remove_var("OPENCLAW_DISABLE_CANARY_DUMP");
        assert!(!h.is_enabled(), "disable flag must override canary mode");
    }

    #[tokio::test]
    async fn spawn_without_canary_mode_is_disabled() {
        let tmp = TempDir::new().unwrap();
        std::env::remove_var("OPENCLAW_CANARY_MODE");
        std::env::remove_var("OPENCLAW_DISABLE_CANARY_DUMP");
        let cancel = CancellationToken::new();
        let h = spawn(tmp.path().to_path_buf(), cancel);
        assert!(!h.is_enabled());
    }

    #[tokio::test]
    async fn writer_round_trips_records_and_flushes() {
        let tmp = TempDir::new().unwrap();
        let canary_path = tmp.path().join("engine_results.jsonl");
        let (tx, rx) = mpsc::channel::<CanaryRecord>(16);
        let cancel = CancellationToken::new();
        let cancel2 = cancel.clone();
        let path2 = canary_path.clone();
        let h = tokio::spawn(async move {
            run_writer(rx, path2, 1024, 3, cancel2).await;
        });
        tx.send(mk_record(1)).await.unwrap();
        tx.send(mk_record(2)).await.unwrap();
        // Give flush_timer a chance.
        tokio::time::sleep(std::time::Duration::from_millis(400)).await;
        cancel.cancel();
        drop(tx);
        let _ = h.await;
        let contents = std::fs::read_to_string(&canary_path).unwrap();
        let lines: Vec<_> = contents.lines().collect();
        assert_eq!(lines.len(), 2, "expected 2 JSONL lines, got: {:?}", lines);
        let r1: CanaryRecord = serde_json::from_str(lines[0]).unwrap();
        assert_eq!(r1.tick_number, 1);
    }

    #[tokio::test]
    async fn writer_rotates_on_size_threshold() {
        let tmp = TempDir::new().unwrap();
        let canary_path = tmp.path().join("engine_results.jsonl");
        let (tx, rx) = mpsc::channel::<CanaryRecord>(1024);
        let cancel = CancellationToken::new();
        let cancel2 = cancel.clone();
        let path2 = canary_path.clone();
        // rotate_mb=0 → any write triggers rotation (saturating_mul(0) = 0 threshold)
        let h = tokio::spawn(async move {
            run_writer(rx, path2, 0, 2, cancel2).await;
        });
        for i in 0..3u64 {
            tx.send(mk_record(i)).await.unwrap();
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        cancel.cancel();
        drop(tx);
        let _ = h.await;
        let archive_dir = tmp.path().join("engine_logs");
        assert!(archive_dir.exists(), "rotation must create engine_logs/");
        let archived: Vec<_> = std::fs::read_dir(&archive_dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .collect();
        assert!(!archived.is_empty(), "expected at least one rotated file");
    }
}
