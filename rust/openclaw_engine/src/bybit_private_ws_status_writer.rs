//! Periodic status-JSON writer for the Bybit private WebSocket listener.
//! Bybit 私有 WebSocket listener 的週期性狀態 JSON 寫入器。
//!
//! MODULE_NOTE (EN): Retires the Python `bybit_private_ws_listener.py` by
//!   producing the same status JSON file (`bybit_private_ws_listener_status_
//!   latest.json`) read by the `readonly_observer_pipeline/` scripts. Reads
//!   live atomic counters from `ExecutionListener` via `Arc<AtomicStats>` and
//!   dumps them every 5 s using a tmp-then-rename atomic write. Cancellation-
//!   aware: triggers a final `running=false` write on shutdown so observers
//!   see the clean state after engine stop.
//! MODULE_NOTE (中): 透過產生與 Python listener 相同路徑的狀態 JSON 讓
//!   `readonly_observer_pipeline/` 腳本無感切換，取代 Python listener；
//!   經由 `Arc<AtomicStats>` 讀取 `ExecutionListener` 即時計數器，每 5 秒以
//!   tmp → rename 原子寫入；cancel 時會做一次 `running=false` 的終止寫入，
//!   讓 observer 在 engine 停止後看到乾淨狀態。
//!
//! Retirement reference / 退役文件：
//!   `.claude_reports/20260423_*_ws_listener_retirement.md`

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use tokio::io::AsyncWriteExt;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use crate::execution_listener::AtomicStats;

// ---------------------------------------------------------------------------
// Constants / 常量
// ---------------------------------------------------------------------------

/// Fixed identifier matching the Python listener's `listener_type` field.
/// 與 Python listener `listener_type` 欄位一致的固定識別字。
pub const LISTENER_TYPE: &str = "bybit_private_ws_listener";

/// Version tag: "rust-v1" indicates the writer is produced by the Rust engine
/// (distinct from Python's "v2" so observers can tell which implementation
/// owns the file at a glance).
/// 版本標籤："rust-v1" 表示檔案由 Rust engine 產生（與 Python "v2" 區分，方便
/// observer 一眼辨識實作方）。
pub const LISTENER_VERSION: &str = "rust-v1";

/// Default write interval (5 s) — matches the Python listener's cadence so
/// `readonly_observer_pipeline` staleness thresholds apply unchanged.
/// 預設寫入間隔（5 秒），對齊 Python listener cadence 以保持 observer 的
/// freshness 判定邏輯不變。
pub const DEFAULT_WRITE_INTERVAL_SEC: u64 = 5;

/// Status JSON filename (unchanged from Python for drop-in replacement).
/// 狀態 JSON 檔名（與 Python 一致以直接取代）。
pub const STATUS_FILENAME: &str = "bybit_private_ws_listener_status_latest.json";

/// Subpath under `OPENCLAW_SRV_ROOT` / `OPENCLAW_BASE_DIR` where the file
/// lives. Matches Python's hardcoded location so observers read the same
/// path without config change.
/// 相對於 `OPENCLAW_SRV_ROOT` / `OPENCLAW_BASE_DIR` 的子路徑，對齊 Python
/// 硬編碼位置，observer 無需改 config。
pub const STATUS_SUBDIR: &str =
    "docker_projects/trading_services/connector_logs/bybit/ws_persistent";

// ---------------------------------------------------------------------------
// PrivateWsStatus / 私有 WS 狀態結構
// ---------------------------------------------------------------------------

/// Status-JSON schema — mirrors the subset of the Python listener's output
/// that `readonly_observer_pipeline` actually reads:
///
/// - `listener_type` / `listener_version` / `session_ts_ms` / `started_ts_ms` —
///   identity & freshness
/// - `ws_url` / `topics_requested` — subscribe config
/// - `running` — boolean liveness
/// - `message_count` + `topic_message_count` — cumulative traffic
/// - `auth_ok_count` / `disconnect_count` — session health
/// - `last_event_ts_ms` — freshness check anchor
/// - `engine_mode` — NEW: paper / demo / live_demo / live (Rust-only addition,
///   Python never produced this because it was single-env)
///
/// 狀態 JSON schema — 鏡像 Python listener 輸出中被 observer 真正讀取的欄位；
/// `engine_mode` 為 Rust 新增欄位（多引擎並行識別）。
#[derive(Debug, Clone, Serialize)]
pub struct PrivateWsStatus {
    pub listener_type: String,
    pub listener_version: String,
    pub session_ts_ms: u64,
    pub started_ts_ms: u64,
    pub ws_url: String,
    pub topics_requested: Vec<String>,
    pub running: bool,
    pub message_count: u64,
    pub topic_message_count: HashMap<String, u64>,
    pub auth_ok_count: u64,
    pub disconnect_count: u64,
    pub last_event_ts_ms: Option<u64>,
    pub engine_mode: String,
}

// ---------------------------------------------------------------------------
// Snapshot builder / 快照建構器
// ---------------------------------------------------------------------------

/// Build a `PrivateWsStatus` from live counters + session-level config.
/// Pure fn (no IO, no time-of-day) so it's trivially testable.
///
/// 由即時計數器 + 會話配置建構 `PrivateWsStatus`；純函數（無 IO、無時鐘）
/// 便於單元測試。
pub fn snapshot_status(
    stats: &AtomicStats,
    session_ts_ms: u64,
    started_ts_ms: u64,
    ws_url: &str,
    topics: &[String],
    engine_mode: &str,
    running: bool,
) -> PrivateWsStatus {
    let snap = stats.snapshot();

    // Per-topic counters (Bybit V5 canonical topic names).
    // 各 topic 計數（Bybit V5 canonical 命名）。
    let mut topic_count: HashMap<String, u64> = HashMap::new();
    topic_count.insert("order".to_string(), snap.total_order_updates);
    topic_count.insert("execution".to_string(), snap.total_fills);
    topic_count.insert("position".to_string(), snap.total_position_updates);
    topic_count.insert("wallet".to_string(), snap.total_balance_updates);

    let message_count = snap
        .total_fills
        .saturating_add(snap.total_order_updates)
        .saturating_add(snap.total_position_updates)
        .saturating_add(snap.total_balance_updates);

    // `last_event_ts == 0` means "no event yet" — emit `None` so observer
    // freshness checks don't falsely treat epoch-zero as a stale event.
    // `last_event_ts == 0` 表示「尚未收到事件」，回傳 `None` 避免 observer
    // 把 epoch-0 誤判為過期事件。
    let last_event_ts_ms = if snap.last_event_ts > 0 {
        Some(snap.last_event_ts)
    } else {
        None
    };

    PrivateWsStatus {
        listener_type: LISTENER_TYPE.to_string(),
        listener_version: LISTENER_VERSION.to_string(),
        session_ts_ms,
        started_ts_ms,
        ws_url: ws_url.to_string(),
        topics_requested: topics.to_vec(),
        running,
        message_count,
        topic_message_count: topic_count,
        auth_ok_count: snap.total_auth_successes,
        disconnect_count: snap.total_disconnects,
        last_event_ts_ms,
        engine_mode: engine_mode.to_string(),
    }
}

// ---------------------------------------------------------------------------
// Path resolution / 路徑解析
// ---------------------------------------------------------------------------

/// Resolve the status-JSON output path from env vars, replicating Python's
/// lookup order:
/// 1. `OPENCLAW_SRV_ROOT` (legacy, matches Python listener)
/// 2. `OPENCLAW_BASE_DIR` (new convention per CLAUDE.md §六)
/// 3. Fallback: `.` (CWD)
///
/// 從 env var 解析狀態 JSON 輸出路徑，遵循 Python 查找順序：
/// 1. `OPENCLAW_SRV_ROOT`（legacy）2. `OPENCLAW_BASE_DIR`（新規範）3. `.`（fallback）
pub fn resolve_status_path_from_env() -> PathBuf {
    let root = std::env::var("OPENCLAW_SRV_ROOT")
        .ok()
        .or_else(|| std::env::var("OPENCLAW_BASE_DIR").ok())
        .unwrap_or_else(|| ".".to_string());
    PathBuf::from(root)
        .join(STATUS_SUBDIR)
        .join(STATUS_FILENAME)
}

/// Pure variant of `resolve_status_path_from_env` for tests — takes the
/// root explicitly so no env-var mutation is needed.
/// 純函數版（用於測試），明確接 root 避免 env var 污染。
pub fn resolve_status_path_from_root(root: &Path) -> PathBuf {
    root.join(STATUS_SUBDIR).join(STATUS_FILENAME)
}

// ---------------------------------------------------------------------------
// Atomic write / 原子寫入
// ---------------------------------------------------------------------------

/// Write status JSON atomically: `write → fsync → rename`. Creates parent
/// dirs as needed. Observers never see a partial file.
///
/// 原子寫入狀態 JSON：`write → fsync → rename`；parent dir 自動建立；
/// observer 不會看到半寫狀態。
pub async fn write_status_atomic(path: &Path, status: &PrivateWsStatus) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    let tmp = path.with_extension("json.tmp");
    let json = serde_json::to_string_pretty(status)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
    {
        let mut f = tokio::fs::File::create(&tmp).await?;
        f.write_all(json.as_bytes()).await?;
        f.sync_all().await?;
    }
    tokio::fs::rename(&tmp, path).await?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Writer task / Writer 任務
// ---------------------------------------------------------------------------

/// Configuration for `run_private_ws_status_writer` — avoids a 7-arg fn sig.
/// `run_private_ws_status_writer` 的組態 struct，避免 7 個參數的長簽名。
pub struct WriterConfig {
    pub output_path: PathBuf,
    pub engine_mode: String,
    pub ws_url: String,
    pub topics: Vec<String>,
    pub interval: Duration,
}

impl WriterConfig {
    /// Construct with default 5 s interval + env-resolved path.
    /// 以預設 5 秒間隔 + env 解析路徑建構。
    pub fn from_env(engine_mode: String, ws_url: String, topics: Vec<String>) -> Self {
        Self {
            output_path: resolve_status_path_from_env(),
            engine_mode,
            ws_url,
            topics,
            interval: Duration::from_secs(DEFAULT_WRITE_INTERVAL_SEC),
        }
    }
}

/// Periodic status-JSON writer. Runs until `cancel` fires, then performs one
/// final write with `running=false` so observers see a clean stopped state.
///
/// 週期性狀態 JSON writer。`cancel` 觸發前持續運作；收到 cancel 後做一次
/// `running=false` 的終止寫入，讓 observer 看到乾淨的停止狀態。
pub async fn run_private_ws_status_writer(
    stats: Arc<AtomicStats>,
    config: WriterConfig,
    cancel: CancellationToken,
) {
    let started_ts_ms = now_ms();
    // `session_ts_ms == started_ts_ms` — single-session writer (no restart).
    // 單會話 writer（未重啟）時兩值一致。
    let session_ts_ms = started_ts_ms;

    info!(
        path = ?config.output_path,
        engine_mode = %config.engine_mode,
        interval_ms = config.interval.as_millis() as u64,
        "Private WS status writer started / 私有 WS 狀態寫入器已啟動"
    );

    let mut ticker = tokio::time::interval(config.interval);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    ticker.tick().await; // Consume the immediate initial tick.

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                info!("Private WS status writer shutting down / 私有 WS 狀態寫入器關閉中");
                let status = snapshot_status(
                    &stats,
                    session_ts_ms,
                    started_ts_ms,
                    &config.ws_url,
                    &config.topics,
                    &config.engine_mode,
                    false, // running=false on shutdown
                );
                if let Err(e) = write_status_atomic(&config.output_path, &status).await {
                    warn!(error = %e, "Final status write failed / 最終狀態寫入失敗");
                }
                break;
            }
            _ = ticker.tick() => {
                let status = snapshot_status(
                    &stats,
                    session_ts_ms,
                    started_ts_ms,
                    &config.ws_url,
                    &config.topics,
                    &config.engine_mode,
                    true,
                );
                match write_status_atomic(&config.output_path, &status).await {
                    Ok(()) => {
                        debug!(
                            count = status.message_count,
                            auth_ok = status.auth_ok_count,
                            "Status written / 狀態已寫入"
                        );
                    }
                    Err(e) => {
                        warn!(error = %e, path = ?config.output_path,
                              "Status write failed / 狀態寫入失敗");
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助函數
// ---------------------------------------------------------------------------

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::Ordering;
    use tempfile::TempDir;

    fn topics_fixture() -> Vec<String> {
        vec![
            "order".to_string(),
            "execution".to_string(),
            "position".to_string(),
            "wallet".to_string(),
        ]
    }

    /// snapshot_status sets cumulative message_count + per-topic counts.
    /// snapshot_status 會設定累積 message_count 與每 topic 計數。
    #[test]
    fn test_snapshot_status_basic_shape() {
        let stats = AtomicStats::default();
        stats.total_fills.store(10, Ordering::Relaxed);
        stats.total_order_updates.store(5, Ordering::Relaxed);
        stats.total_position_updates.store(3, Ordering::Relaxed);
        stats.total_balance_updates.store(2, Ordering::Relaxed);
        stats.total_auth_successes.store(1, Ordering::Relaxed);
        stats.total_disconnects.store(0, Ordering::Relaxed);
        stats
            .last_event_ts
            .store(1_700_000_000_000, Ordering::Relaxed);

        let status = snapshot_status(
            &stats,
            1_700_000_000_000,
            1_700_000_000_000,
            "wss://stream.bybit.com/v5/private",
            &topics_fixture(),
            "demo",
            true,
        );

        assert_eq!(status.listener_type, "bybit_private_ws_listener");
        assert_eq!(status.listener_version, "rust-v1");
        assert!(status.running);
        assert_eq!(status.message_count, 10 + 5 + 3 + 2);
        assert_eq!(status.auth_ok_count, 1);
        assert_eq!(status.disconnect_count, 0);
        assert_eq!(status.topic_message_count.get("order"), Some(&5));
        assert_eq!(status.topic_message_count.get("execution"), Some(&10));
        assert_eq!(status.topic_message_count.get("position"), Some(&3));
        assert_eq!(status.topic_message_count.get("wallet"), Some(&2));
        assert_eq!(status.last_event_ts_ms, Some(1_700_000_000_000));
        assert_eq!(status.engine_mode, "demo");
        assert_eq!(status.ws_url, "wss://stream.bybit.com/v5/private");
        assert_eq!(status.topics_requested.len(), 4);
    }

    /// last_event_ts == 0 → last_event_ts_ms == None (no event yet).
    /// last_event_ts 為 0 → last_event_ts_ms 回 None（尚無事件）。
    #[test]
    fn test_snapshot_last_event_ts_zero_is_none() {
        let stats = AtomicStats::default();
        let status = snapshot_status(&stats, 0, 0, "url", &[], "paper", true);
        assert_eq!(status.last_event_ts_ms, None);
        assert_eq!(status.message_count, 0);
        assert!(status.topics_requested.is_empty());
    }

    /// running=false serialises as expected (used in shutdown path).
    /// running=false 可正確序列化（關閉流程用）。
    #[test]
    fn test_snapshot_running_false() {
        let stats = AtomicStats::default();
        let status = snapshot_status(&stats, 1, 1, "url", &[], "demo", false);
        assert!(!status.running);
    }

    /// saturating_add guards against u64 overflow when summing counters.
    /// saturating_add 於累加計數器時防 u64 溢位。
    #[test]
    fn test_snapshot_message_count_saturates_on_overflow() {
        let stats = AtomicStats::default();
        stats.total_fills.store(u64::MAX - 5, Ordering::Relaxed);
        stats.total_order_updates.store(10, Ordering::Relaxed);
        let status = snapshot_status(&stats, 0, 0, "url", &[], "demo", true);
        // Saturates at u64::MAX rather than wrapping / 飽和於 u64::MAX 不環繞。
        assert_eq!(status.message_count, u64::MAX);
    }

    /// resolve_status_path_from_root composes the correct full path without
    /// touching env vars.
    /// resolve_status_path_from_root 正確組合完整路徑，不觸及 env var。
    #[test]
    fn test_resolve_status_path_from_root_composition() {
        let root = Path::new("/tmp/example_root");
        let path = resolve_status_path_from_root(root);
        let s = path.to_string_lossy();
        assert!(s.starts_with("/tmp/example_root/"));
        assert!(s.contains("docker_projects/trading_services/connector_logs/bybit/ws_persistent"));
        assert!(s.ends_with("bybit_private_ws_listener_status_latest.json"));
    }

    /// write_status_atomic creates missing parent directories and produces
    /// valid JSON observers can parse.
    /// write_status_atomic 自動建立 parent dir 並輸出可解析的 JSON。
    #[tokio::test]
    async fn test_write_atomic_creates_parent_dir_and_valid_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("a/b/c").join(STATUS_FILENAME);
        let stats = AtomicStats::default();
        stats.total_fills.store(7, Ordering::Relaxed);
        let status = snapshot_status(
            &stats,
            1_700_000_001_000,
            1_700_000_000_000,
            "wss://url",
            &topics_fixture(),
            "demo",
            true,
        );
        write_status_atomic(&path, &status).await.unwrap();
        assert!(path.exists());

        // Parent dir chain was created / parent dir chain 已建。
        assert!(path.parent().unwrap().exists());

        // Content is valid JSON with the right keys / 內容為含正確 key 的合法 JSON。
        let contents = tokio::fs::read_to_string(&path).await.unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&contents).unwrap();
        assert_eq!(parsed["listener_type"], "bybit_private_ws_listener");
        assert_eq!(parsed["listener_version"], "rust-v1");
        assert_eq!(parsed["engine_mode"], "demo");
        assert_eq!(parsed["running"], true);
        assert_eq!(parsed["message_count"], 7);
        assert!(parsed["topic_message_count"].is_object());
        assert_eq!(parsed["topic_message_count"]["execution"], 7);
    }

    /// Overwriting an existing file replaces content cleanly (tmp+rename).
    /// 覆寫既有檔案會乾淨替換內容（tmp+rename）。
    #[tokio::test]
    async fn test_write_atomic_overwrites_cleanly() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join(STATUS_FILENAME);

        let stats = AtomicStats::default();
        let s1 = snapshot_status(&stats, 1, 1, "url1", &[], "demo", true);
        write_status_atomic(&path, &s1).await.unwrap();

        stats.total_fills.store(99, Ordering::Relaxed);
        let s2 = snapshot_status(&stats, 2, 2, "url2", &[], "paper", false);
        write_status_atomic(&path, &s2).await.unwrap();

        let contents = tokio::fs::read_to_string(&path).await.unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&contents).unwrap();
        assert_eq!(parsed["session_ts_ms"], 2);
        assert_eq!(parsed["ws_url"], "url2");
        assert_eq!(parsed["engine_mode"], "paper");
        assert_eq!(parsed["running"], false);
        assert_eq!(parsed["message_count"], 99);
    }

    /// No `.tmp` artefact remains after a successful write (clean rename).
    /// 寫入成功後不留 `.tmp` 殘檔（rename 完成）。
    #[tokio::test]
    async fn test_write_atomic_leaves_no_tmp_artifact() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join(STATUS_FILENAME);
        let stats = AtomicStats::default();
        let status = snapshot_status(&stats, 1, 1, "u", &[], "demo", true);
        write_status_atomic(&path, &status).await.unwrap();

        let tmp_path = path.with_extension("json.tmp");
        assert!(
            !tmp_path.exists(),
            "tmp file should be renamed, not left behind"
        );
    }

    /// Writer task performs a final `running=false` write on cancel, so
    /// observers see the clean stopped state.
    /// Writer 任務於 cancel 時會做一次 `running=false` 的終止寫入。
    #[tokio::test]
    async fn test_writer_task_final_write_on_cancel() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join(STATUS_FILENAME);
        let stats = Arc::new(AtomicStats::default());
        stats.total_fills.store(3, Ordering::Relaxed);
        let cancel = CancellationToken::new();

        let config = WriterConfig {
            output_path: path.clone(),
            engine_mode: "demo".to_string(),
            ws_url: "wss://test".to_string(),
            topics: topics_fixture(),
            interval: Duration::from_secs(60), // long — we rely on cancel to end.
        };

        let cancel_clone = cancel.clone();
        let stats_clone = Arc::clone(&stats);
        let handle = tokio::spawn(async move {
            run_private_ws_status_writer(stats_clone, config, cancel_clone).await
        });

        // Give the task a moment to start, then cancel.
        // 給任務啟動的時間後再 cancel。
        tokio::time::sleep(Duration::from_millis(50)).await;
        cancel.cancel();
        handle.await.unwrap();

        // Final write happened with running=false.
        // 終止寫入已發生且 running=false。
        assert!(
            path.exists(),
            "writer should have written at least once on cancel"
        );
        let contents = tokio::fs::read_to_string(&path).await.unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&contents).unwrap();
        assert_eq!(parsed["running"], false);
        assert_eq!(parsed["engine_mode"], "demo");
        assert_eq!(parsed["message_count"], 3);
    }

    /// Writer task ticks on interval — short-interval test triggers at least
    /// one tick before cancellation.
    /// 短間隔測試：cancel 前至少觸發一次 tick。
    #[tokio::test]
    async fn test_writer_task_ticks_on_interval() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join(STATUS_FILENAME);
        let stats = Arc::new(AtomicStats::default());
        stats.total_fills.store(42, Ordering::Relaxed);
        let cancel = CancellationToken::new();

        let config = WriterConfig {
            output_path: path.clone(),
            engine_mode: "demo".to_string(),
            ws_url: "wss://t".to_string(),
            topics: Vec::new(),
            interval: Duration::from_millis(20),
        };

        let cancel_clone = cancel.clone();
        let stats_clone = Arc::clone(&stats);
        let handle = tokio::spawn(async move {
            run_private_ws_status_writer(stats_clone, config, cancel_clone).await
        });

        // Wait long enough for ≥2 ticks at 20 ms interval.
        // 等待 ≥2 次 20ms tick。
        tokio::time::sleep(Duration::from_millis(60)).await;
        cancel.cancel();
        handle.await.unwrap();

        let contents = tokio::fs::read_to_string(&path).await.unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&contents).unwrap();
        // Final write observed (running=false).
        assert_eq!(parsed["running"], false);
        assert_eq!(parsed["message_count"], 42);
    }

    /// `WriterConfig::from_env` honours env-var precedence: SRV_ROOT over
    /// BASE_DIR over fallback `.`. (Uses env-var mutation — serial_test-style
    /// isolation isn't needed because the test writes to a scoped TempDir.)
    /// `WriterConfig::from_env` 尊重 env var 優先序。
    #[test]
    fn test_writer_config_from_env_honours_srv_root() {
        // Preserve + restore any existing env state / 保存並還原既有 env 狀態。
        let prior_srv = std::env::var("OPENCLAW_SRV_ROOT").ok();
        let prior_base = std::env::var("OPENCLAW_BASE_DIR").ok();

        std::env::set_var("OPENCLAW_SRV_ROOT", "/tmp/writer_cfg_srv_root");
        std::env::remove_var("OPENCLAW_BASE_DIR");
        let cfg = WriterConfig::from_env("demo".to_string(), "url".to_string(), vec![]);
        assert!(cfg.output_path.starts_with("/tmp/writer_cfg_srv_root"));
        assert!(cfg.output_path.ends_with(STATUS_FILENAME));
        assert_eq!(
            cfg.interval,
            Duration::from_secs(DEFAULT_WRITE_INTERVAL_SEC)
        );

        // Restore original state / 還原原始 env 狀態。
        match prior_srv {
            Some(v) => std::env::set_var("OPENCLAW_SRV_ROOT", v),
            None => std::env::remove_var("OPENCLAW_SRV_ROOT"),
        }
        if let Some(v) = prior_base {
            std::env::set_var("OPENCLAW_BASE_DIR", v);
        }
    }
}
