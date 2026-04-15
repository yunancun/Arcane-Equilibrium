//! Generic ArcSwap-backed config store with hot reload + bulk patch + audit hook.
//! 通用 ArcSwap 配置存儲：熱重載、批次補丁、審計掛鉤。
//!
//! MODULE_NOTE (EN): `ConfigStore<T>` wraps any config type behind an `Arc<ArcSwap<T>>`,
//!   providing lock-free reads (~5ns, tick hot-path safe) and atomic writes serialised
//!   through a Mutex. Bulk patches are all-or-nothing: validation must succeed for
//!   ALL fields before the swap. Each store has a monotonic version counter and a
//!   `source` audit field (operator / agent / migration / startup) for traceability.
//!   The store does NOT itself persist to disk — that is the loader's job in 1C.
//! MODULE_NOTE (中): `ConfigStore<T>` 用 `Arc<ArcSwap<T>>` 包裹任意配置型別，
//!   提供無鎖讀取（~5ns，tick 熱路徑安全）與經 Mutex 序列化的原子寫入。批次補丁
//!   遵循 all-or-nothing：所有欄位必須驗證通過才會替換。每個 store 有單調遞增的
//!   version 計數器與 `source` 審計欄位（operator / agent / migration / startup）。
//!   Store 本身不負責落盤，那是 1C 載入器的工作。

use arc_swap::ArcSwap;
use serde::Serialize;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tracing::warn;

/// Source label for an audit-traceable config patch.
/// 配置補丁的審計來源標籤。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PatchSource {
    /// Operator GUI / CLI manual update / 操作員手動更新
    Operator,
    /// Agent runtime self-tuning / Agent 運行時自我調整
    Agent,
    /// One-time legacy migration / 一次性舊配置遷移
    Migration,
    /// Initial load on engine startup / 引擎啟動初始載入
    Startup,
}

impl PatchSource {
    /// String form for log lines and audit DB rows.
    /// 用於日誌與審計表的字串形式。
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Operator => "operator",
            Self::Agent => "agent",
            Self::Migration => "migration",
            Self::Startup => "startup",
        }
    }
}

/// Outcome of a single patch application.
/// 單次補丁套用的結果。
#[derive(Debug, Clone)]
pub struct PatchOutcome {
    /// Monotonic version after this patch.
    /// 套用後的單調版本號。
    pub version: u64,
    /// Audit source.
    /// 審計來源。
    pub source: PatchSource,
}

/// Generic config store with lock-free reads and serialised writes.
/// 通用配置存儲：無鎖讀取，序列化寫入。
///
/// `T` must be `Clone + Send + Sync + 'static`. Validation is delegated to a
/// caller-provided closure so different configs can enforce different invariants
/// without coupling the store to any specific schema.
///
/// `T` 必須滿足 `Clone + Send + Sync + 'static`。驗證由呼叫端傳入的閉包負責，
/// 讓不同配置可以強制不同的不變量，而不讓 store 耦合任何特定 schema。
pub struct ConfigStore<T: Clone + Send + Sync + 'static> {
    inner: ArcSwap<T>,
    /// Monotonic version counter (incremented per successful patch).
    /// 單調版本計數器（每次成功補丁遞增）。
    version: AtomicU64,
    /// Serialises writes (NOT reads) so concurrent patches don't interleave.
    /// Reads remain lock-free via ArcSwap.
    /// 序列化寫入（不影響讀取），避免並行補丁交錯。讀取仍透過 ArcSwap 無鎖。
    write_lock: Mutex<()>,
    /// ARCH-RC1 1C-4-fix (CFG-PERSIST-1): optional disk write-back path.
    /// When set together with `persist_writer`, every successful patch /
    /// replace triggers an atomic TOML write so operator changes survive
    /// engine restart. Wired via `with_toml_persist()`.
    /// 可選的磁碟回寫路徑。設定後，每次成功補丁/替換會原子寫回 TOML，
    /// 讓 operator 設定能跨重啟保留。透過 `with_toml_persist()` 啟用。
    persist_path: Option<PathBuf>,
    persist_writer: Option<Box<dyn Fn(&T, &Path) -> Result<(), String> + Send + Sync>>,
}

impl<T: Clone + Send + Sync + 'static> ConfigStore<T> {
    /// Create a new store with an initial value.
    /// 建立新 store，帶初始值。
    pub fn new(initial: T) -> Self {
        Self {
            inner: ArcSwap::from_pointee(initial),
            version: AtomicU64::new(0),
            write_lock: Mutex::new(()),
            persist_path: None,
            persist_writer: None,
        }
    }

    /// Internal: invoked under the write lock after a successful swap.
    /// If a persist writer is wired, write the snapshot to disk atomically.
    /// Failures are logged but never propagated — the in-memory swap already
    /// succeeded and tick consumers must not be blocked by disk issues.
    /// 內部：成功 swap 後在寫鎖內呼叫。若有 persist writer，原子寫回磁碟。
    /// 失敗只記 log 不向外傳遞 —— 內存 swap 已成功，不能因磁碟問題阻塞 tick。
    fn maybe_persist(&self) {
        if let (Some(path), Some(writer)) = (&self.persist_path, &self.persist_writer) {
            let snap = self.inner.load_full();
            if let Err(e) = writer(&*snap, path) {
                warn!(
                    path = %path.display(),
                    error = %e,
                    "ConfigStore TOML persist failed (in-memory swap still applied) / 配置磁碟回寫失敗（內存仍生效）"
                );
            }
        }
    }

    /// Lock-free snapshot read (~5ns). Safe to call from tick hot path.
    /// 無鎖快照讀取（~5ns）。可在 tick 熱路徑安全呼叫。
    pub fn load(&self) -> Arc<T> {
        self.inner.load_full()
    }

    /// EDGE-P3-1 Step 7e: persist path getter for callers that need to write
    /// the TOML directly (kill-switch Stage 1 fsync). Returns `None` when
    /// `with_toml_persist()` was not wired (e.g. test-constructed stores).
    /// EDGE-P3-1 Step 7e：回寫路徑 getter，for 需直接寫 TOML 的呼叫方
    /// （kill-switch Stage 1 fsync）。`with_toml_persist` 未接線時回 None。
    pub fn persist_path(&self) -> Option<&Path> {
        self.persist_path.as_deref()
    }

    /// Current version number.
    /// 當前版本號。
    pub fn version(&self) -> u64 {
        self.version.load(Ordering::Acquire)
    }

    /// Apply a patch atomically with validation.
    ///
    /// `mutate` receives a mutable copy of the current config and may modify
    /// any fields. After mutation, `validate` is called on the result. If
    /// validation passes, the new config is atomically swapped in and the
    /// version is incremented. If it fails, the swap is aborted and the error
    /// is returned (all-or-nothing).
    ///
    /// 帶驗證的原子補丁。`mutate` 取得當前配置的可變副本，可修改任意欄位。
    /// 修改後對結果呼叫 `validate`。驗證通過則原子替換並遞增版本號；
    /// 驗證失敗則中止替換並回傳錯誤（all-or-nothing）。
    pub fn apply_patch<F, V>(
        &self,
        source: PatchSource,
        mutate: F,
        validate: V,
    ) -> Result<PatchOutcome, String>
    where
        F: FnOnce(&mut T),
        V: FnOnce(&T) -> Result<(), String>,
    {
        // Serialise writes / 序列化寫入
        let _guard = self
            .write_lock
            .lock()
            .map_err(|_| "ConfigStore write lock poisoned".to_string())?;

        // Snapshot current under write lock so concurrent patches see a coherent base.
        // 在寫鎖內快照當前值，讓並行補丁看到一致的基線。
        let current = self.inner.load_full();
        let mut next: T = (*current).clone();
        mutate(&mut next);
        validate(&next)?;

        self.inner.store(Arc::new(next));
        let new_version = self.version.fetch_add(1, Ordering::AcqRel) + 1;

        // CFG-PERSIST-1: write-back to disk after every successful patch
        // (skipped for Startup/Migration sources to avoid load→write churn).
        // CFG-PERSIST-1：每次成功補丁後回寫磁碟（Startup/Migration 跳過避免來回寫）。
        if !matches!(source, PatchSource::Startup | PatchSource::Migration) {
            self.maybe_persist();
        }

        Ok(PatchOutcome {
            version: new_version,
            source,
        })
    }

    /// Replace the entire config in one atomic write (used by initial load + migration).
    /// 一次原子寫入完整替換配置（用於初始載入與遷移）。
    pub fn replace(&self, value: T, source: PatchSource) -> Result<PatchOutcome, String> {
        let _guard = self
            .write_lock
            .lock()
            .map_err(|_| "ConfigStore write lock poisoned".to_string())?;
        self.inner.store(Arc::new(value));
        let new_version = self.version.fetch_add(1, Ordering::AcqRel) + 1;

        // CFG-PERSIST-1: same write-back as apply_patch.
        // CFG-PERSIST-1：與 apply_patch 一致的回寫。
        if !matches!(source, PatchSource::Startup | PatchSource::Migration) {
            self.maybe_persist();
        }

        Ok(PatchOutcome {
            version: new_version,
            source,
        })
    }
}

// ---------------------------------------------------------------------------
// CFG-PERSIST-1: typed extension wiring TOML write-back.
// CFG-PERSIST-1：附帶 TOML 寫回的型別擴展。
// ---------------------------------------------------------------------------

impl<T> ConfigStore<T>
where
    T: Clone + Send + Sync + Serialize + 'static,
{
    /// Enable atomic TOML write-back to `path` on every successful Operator/Agent
    /// patch. The write is fail-soft: serialise → write tmp → rename. Errors are
    /// logged but never block the in-memory swap. Existing file (if any) is
    /// overwritten on first successful patch.
    /// 為每次 Operator/Agent 成功補丁啟用原子 TOML 回寫。寫入流程：序列化 → 寫
    /// 臨時檔 → rename。失敗只記 log，不阻塞內存 swap。
    pub fn with_toml_persist(mut self, path: PathBuf) -> Self {
        self.persist_path = Some(path);
        self.persist_writer = Some(Box::new(write_toml_atomic::<T>));
        self
    }
}

/// Free helper: serialise `cfg` to TOML and atomic-rename into `path`.
/// 自由函式：把 `cfg` 序列化為 TOML 並原子 rename 到 `path`。
fn write_toml_atomic<T: Serialize>(cfg: &T, path: &Path) -> Result<(), String> {
    let toml_str =
        toml::to_string(cfg).map_err(|e| format!("toml serialize failed: {e}"))?;
    let tmp = path.with_extension("toml.tmp");
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("mkdir parent failed: {e}"))?;
        }
    }
    std::fs::write(&tmp, toml_str.as_bytes())
        .map_err(|e| format!("write tmp failed: {e}"))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("rename failed: {e}"))?;
    Ok(())
}

/// EDGE-P3-1 U2: durable variant of `write_toml_atomic` used by the edge-predictor
/// kill-switch (`DisableEdgePredictorAll`). Serialises `cfg`, fsyncs the tmp file
/// contents, rename-swaps into place, then fsyncs the parent directory so the
/// rename metadata itself survives a crash window (OS buffer unflushed).
/// EDGE-P3-1 U2：供邊緣預測器一鍵關閉（`DisableEdgePredictorAll`）使用的落盤版本。
/// 序列化後先 fsync 臨時檔內容，rename 換入後再 fsync 父目錄，確保 rename metadata
/// 也落盤，避免在 OS buffer 未刷的 crash window 內「看似寫入卻實際丟失」。
///
/// Non-critical callers keep using `write_toml_atomic` to avoid the per-write
/// fsync cost. CC #13 regression `test_disable_all_survives_sigkill` is the
/// authoritative durability proof for this helper.
/// 非關鍵呼叫者仍用 `write_toml_atomic` 以避免每次寫入的 fsync 代價。耐久性由
/// CC #13 回歸測試 `test_disable_all_survives_sigkill` 權威驗證。
pub fn write_toml_atomic_fsynced<T: Serialize>(
    cfg: &T,
    path: &Path,
) -> Result<(), String> {
    let toml_str =
        toml::to_string(cfg).map_err(|e| format!("toml serialize failed: {e}"))?;
    let tmp = path.with_extension("toml.tmp");
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("mkdir parent failed: {e}"))?;
        }
    }
    {
        let mut f = std::fs::File::create(&tmp)
            .map_err(|e| format!("create tmp failed: {e}"))?;
        f.write_all(toml_str.as_bytes())
            .map_err(|e| format!("write tmp failed: {e}"))?;
        f.sync_all()
            .map_err(|e| format!("fsync tmp failed: {e}"))?;
    }
    std::fs::rename(&tmp, path).map_err(|e| format!("rename failed: {e}"))?;
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::File::open(parent)
                .and_then(|f| f.sync_all())
                .map_err(|e| format!("fsync parent dir failed: {e}"))?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Clone, Debug, PartialEq)]
    struct ToyConfig {
        threshold: i32,
        name: String,
    }

    fn no_validation(_c: &ToyConfig) -> Result<(), String> {
        Ok(())
    }

    fn require_positive_threshold(c: &ToyConfig) -> Result<(), String> {
        if c.threshold <= 0 {
            return Err("threshold must be > 0".to_string());
        }
        Ok(())
    }

    #[test]
    fn test_load_returns_initial_value() {
        let store = ConfigStore::new(ToyConfig {
            threshold: 5,
            name: "init".into(),
        });
        let snap = store.load();
        assert_eq!(snap.threshold, 5);
        assert_eq!(snap.name, "init");
        assert_eq!(store.version(), 0);
    }

    #[test]
    fn test_apply_patch_increments_version() {
        let store = ConfigStore::new(ToyConfig {
            threshold: 1,
            name: "a".into(),
        });
        let outcome = store
            .apply_patch(
                PatchSource::Operator,
                |c| c.threshold = 10,
                no_validation,
            )
            .unwrap();
        assert_eq!(outcome.version, 1);
        assert_eq!(outcome.source, PatchSource::Operator);
        assert_eq!(store.load().threshold, 10);
        assert_eq!(store.version(), 1);
    }

    #[test]
    fn test_apply_patch_validation_failure_rolls_back() {
        let store = ConfigStore::new(ToyConfig {
            threshold: 5,
            name: "init".into(),
        });
        let result = store.apply_patch(
            PatchSource::Agent,
            |c| c.threshold = -1,
            require_positive_threshold,
        );
        assert!(result.is_err());
        // State unchanged / 狀態未變
        assert_eq!(store.load().threshold, 5);
        assert_eq!(store.version(), 0);
    }

    #[test]
    fn test_apply_patch_partial_mutation_still_atomic() {
        // Mutate two fields; if validation fails on one, BOTH must roll back.
        // 變更兩個欄位；如果其中一個驗證失敗，兩者都必須回滾。
        let store = ConfigStore::new(ToyConfig {
            threshold: 5,
            name: "alpha".into(),
        });
        let result = store.apply_patch(
            PatchSource::Operator,
            |c| {
                c.name = "beta".into();
                c.threshold = -1;
            },
            require_positive_threshold,
        );
        assert!(result.is_err());
        let snap = store.load();
        // Name must NOT have been updated since validation failed
        // 名稱必須未被更新，因為驗證失敗
        assert_eq!(snap.name, "alpha");
        assert_eq!(snap.threshold, 5);
    }

    #[test]
    fn test_replace_overrides_entirely() {
        let store = ConfigStore::new(ToyConfig {
            threshold: 5,
            name: "old".into(),
        });
        let outcome = store
            .replace(
                ToyConfig {
                    threshold: 99,
                    name: "new".into(),
                },
                PatchSource::Migration,
            )
            .unwrap();
        assert_eq!(outcome.version, 1);
        assert_eq!(outcome.source, PatchSource::Migration);
        assert_eq!(store.load().threshold, 99);
        assert_eq!(store.load().name, "new");
    }

    #[test]
    fn test_concurrent_patches_serialise() {
        // Spawn 10 threads, each incrementing threshold by 1.
        // Final value must be exactly +10, version must be exactly 10.
        // 10 個線程，每個將 threshold 加 1。最終值必為 +10，版本必為 10。
        use std::thread;
        let store = Arc::new(ConfigStore::new(ToyConfig {
            threshold: 0,
            name: "race".into(),
        }));
        let mut handles = vec![];
        for _ in 0..10 {
            let s = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                s.apply_patch(
                    PatchSource::Agent,
                    |c| c.threshold += 1,
                    no_validation,
                )
                .unwrap();
            }));
        }
        for h in handles {
            h.join().unwrap();
        }
        assert_eq!(store.load().threshold, 10);
        assert_eq!(store.version(), 10);
    }

    // ─── CFG-PERSIST-1 / 磁碟回寫 ────────────────────────────────────────
    #[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
    struct PersistableToy {
        threshold: i32,
        name: String,
    }

    fn no_validation_p(_c: &PersistableToy) -> Result<(), String> {
        Ok(())
    }

    #[test]
    fn test_with_toml_persist_writes_on_operator_patch() {
        let dir = std::env::temp_dir().join(format!(
            "oc_cfgstore_persist_{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("toy.toml");
        let _ = std::fs::remove_file(&path);

        let store = ConfigStore::new(PersistableToy {
            threshold: 1,
            name: "init".into(),
        })
        .with_toml_persist(path.clone());

        // Operator patch → file should be written.
        store
            .apply_patch(
                PatchSource::Operator,
                |c| {
                    c.threshold = 42;
                    c.name = "patched".into();
                },
                no_validation_p,
            )
            .unwrap();

        let body = std::fs::read_to_string(&path).expect("toml file written");
        assert!(body.contains("threshold = 42"));
        assert!(body.contains("name = \"patched\""));

        // Simulate restart: parse the file back into a fresh value.
        let restored: PersistableToy = toml::from_str(&body).expect("re-parse");
        assert_eq!(restored.threshold, 42);
        assert_eq!(restored.name, "patched");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_with_toml_persist_skips_startup_and_migration() {
        let dir = std::env::temp_dir().join(format!(
            "oc_cfgstore_persist_skip_{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).ok();
        let path = dir.join("toy_skip.toml");
        let _ = std::fs::remove_file(&path);

        let store = ConfigStore::new(PersistableToy {
            threshold: 1,
            name: "x".into(),
        })
        .with_toml_persist(path.clone());

        // Migration replace must NOT touch disk (avoids load→write churn).
        store
            .replace(
                PersistableToy {
                    threshold: 7,
                    name: "y".into(),
                },
                PatchSource::Migration,
            )
            .unwrap();
        assert!(!path.exists(), "migration must not write back");

        // Operator replace DOES write.
        store
            .replace(
                PersistableToy {
                    threshold: 9,
                    name: "z".into(),
                },
                PatchSource::Operator,
            )
            .unwrap();
        assert!(path.exists(), "operator must write back");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_patch_source_as_str() {
        assert_eq!(PatchSource::Operator.as_str(), "operator");
        assert_eq!(PatchSource::Agent.as_str(), "agent");
        assert_eq!(PatchSource::Migration.as_str(), "migration");
        assert_eq!(PatchSource::Startup.as_str(), "startup");
    }

    // ── FIX-17: Config hot-reload + tick concurrency tests ──

    /// FIX-17: Concurrent readers + writers must never observe torn/partial state.
    /// 10 reader threads + 5 writer threads. Every snapshot must be internally
    /// consistent (threshold and name move together in each patch).
    /// FIX-17：並發讀寫不能觀察到撕裂/部分狀態。10 讀線程 + 5 寫線程，
    /// 每個快照的 threshold 和 name 必須一致。
    #[test]
    fn test_concurrent_read_during_write_no_torn_state() {
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::thread;

        let store = Arc::new(ConfigStore::new(ToyConfig {
            threshold: 0,
            name: "v0".into(),
        }));
        let done = Arc::new(AtomicBool::new(false));

        // 5 writer threads — each sets threshold=i, name="vN"
        let mut handles = vec![];
        for i in 1..=5 {
            let s = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for _ in 0..200 {
                    let val = i;
                    s.apply_patch(
                        PatchSource::Agent,
                        |c| {
                            c.threshold = val;
                            c.name = format!("v{val}");
                        },
                        no_validation,
                    )
                    .unwrap();
                }
            }));
        }

        // 10 reader threads — each reads and verifies consistency
        for _ in 0..10 {
            let s = Arc::clone(&store);
            let d = Arc::clone(&done);
            handles.push(thread::spawn(move || {
                while !d.load(Ordering::Relaxed) {
                    let snap = s.load();
                    let expected_name = format!("v{}", snap.threshold);
                    assert_eq!(
                        snap.name, expected_name,
                        "torn state: threshold={} but name={}",
                        snap.threshold, snap.name
                    );
                }
            }));
        }

        // Wait for writers, then signal readers to stop
        for h in handles.drain(..5) {
            h.join().unwrap();
        }
        done.store(true, Ordering::Relaxed);
        for h in handles {
            h.join().unwrap();
        }
    }

    /// FIX-17: version() is monotonically increasing even under concurrent patching.
    /// FIX-17：version() 在並發補丁下仍單調遞增。
    #[test]
    fn test_version_monotonic_under_concurrent_writes() {
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::thread;

        let store = Arc::new(ConfigStore::new(ToyConfig {
            threshold: 0,
            name: "mono".into(),
        }));
        let done = Arc::new(AtomicBool::new(false));

        // 3 writer threads
        let mut handles = vec![];
        for _ in 0..3 {
            let s = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for _ in 0..100 {
                    s.apply_patch(PatchSource::Agent, |c| c.threshold += 1, no_validation)
                        .unwrap();
                }
            }));
        }

        // 1 version-monitor thread — version must never decrease
        {
            let s = Arc::clone(&store);
            let d = Arc::clone(&done);
            handles.push(thread::spawn(move || {
                let mut last_v = 0u64;
                while !d.load(Ordering::Relaxed) {
                    let v = s.version();
                    assert!(v >= last_v, "version went backwards: {last_v} → {v}");
                    last_v = v;
                }
            }));
        }

        // Wait writers, signal monitor
        for h in handles.drain(..3) {
            h.join().unwrap();
        }
        done.store(true, Ordering::Relaxed);
        for h in handles {
            h.join().unwrap();
        }
        // 3 writers × 100 = 300
        assert_eq!(store.version(), 300);
        assert_eq!(store.load().threshold, 300);
    }

    // EDGE-P3-1 U2 regression: fsynced helper must round-trip TOML and survive
    // OS buffer semantics. Full SIGKILL durability is covered by CC #13
    // integration (test_disable_all_survives_sigkill); this unit test only
    // proves the happy-path write/read equivalence.
    // EDGE-P3-1 U2 回歸：fsync 版 helper 必須完成 TOML 往返並通過 OS buffer 語義。
    // 完整的 SIGKILL 耐久驗證由 CC #13 整合測試負責；本單元測試只證明正常路徑
    // write/read 等價。
    #[test]
    fn test_write_toml_atomic_fsynced_roundtrip() {
        use std::io::Read;

        #[derive(Serialize)]
        struct EdgePredictorSwitch {
            use_edge_predictor: bool,
            shadow_mode: bool,
            note: String,
        }

        let tmp_dir = std::env::temp_dir().join(format!(
            "edge_predictor_fsync_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&tmp_dir).unwrap();
        let path = tmp_dir.join("kill_switch.toml");

        let cfg = EdgePredictorSwitch {
            use_edge_predictor: false,
            shadow_mode: false,
            note: "fsynced kill-switch test".into(),
        };
        write_toml_atomic_fsynced(&cfg, &path).unwrap();

        let mut contents = String::new();
        std::fs::File::open(&path)
            .unwrap()
            .read_to_string(&mut contents)
            .unwrap();
        assert!(contents.contains("use_edge_predictor = false"));
        assert!(contents.contains("shadow_mode = false"));
        assert!(contents.contains("fsynced kill-switch test"));

        // Tmp companion must NOT linger after rename.
        // rename 後 tmp 伴隨檔不應殘留。
        let tmp_path = path.with_extension("toml.tmp");
        assert!(!tmp_path.exists(), "tmp file should be consumed by rename");

        std::fs::remove_dir_all(&tmp_dir).ok();
    }

    #[test]
    fn test_write_toml_atomic_fsynced_creates_parent_dir() {
        #[derive(Serialize)]
        struct Stub {
            x: i32,
        }

        let tmp_dir = std::env::temp_dir().join(format!(
            "edge_predictor_fsync_parent_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let nested = tmp_dir.join("settings").join("engine");
        let path = nested.join("live.toml");
        assert!(!nested.exists(), "precondition: nested dir absent");

        write_toml_atomic_fsynced(&Stub { x: 42 }, &path).unwrap();
        assert!(path.exists(), "file should be created under auto-mkdir parent");

        std::fs::remove_dir_all(&tmp_dir).ok();
    }

    // EDGE-P3-1 U2 / CC #13 regression (spec T23):
    //   `test_write_toml_atomic_fsynced_survives_sigkill`. Durability proof for
    //   the kill-switch path — after the helper returns, the TOML must be on
    //   disk even if the process is SIGKILLed immediately. The test uses
    //   `current_exe()` self-spawn: the child branch (env-var gated) writes the
    //   TOML + a completion marker + enters an idle loop; the parent waits for
    //   the marker, sends SIGKILL, reaps, then reads the file and asserts the
    //   kill-switch flags are intact. Gated `#[cfg(unix)]`: windows has no
    //   SIGKILL semantics and the project's deployment targets (linux + macOS)
    //   are both unix.
    // EDGE-P3-1 U2 / CC #13 回歸（spec T23）：
    //   `test_write_toml_atomic_fsynced_survives_sigkill`，kill-switch 路徑的
    //   耐久性證明 — helper 返回後，即使進程被立刻 SIGKILL，TOML 也必須已落盤。
    //   用 `current_exe()` 自我 spawn：child 分支（env var 閘控）寫 TOML + 完成
    //   標記 + 進入 idle 迴圈；parent 等標記 → 送 SIGKILL → 回收 → 讀檔驗開關
    //   旗標完整。`#[cfg(unix)]` 閘控：Windows 無 SIGKILL 語義，本專案部署目標
    //   （linux + macOS）皆為 unix。
    #[cfg(unix)]
    #[test]
    fn test_write_toml_atomic_fsynced_survives_sigkill() {
        const CHILD_ENV: &str = "OPENCLAW_FSYNC_SIGKILL_CHILD";

        #[derive(Serialize)]
        struct KillSwitch {
            use_edge_predictor: bool,
            shadow_mode: bool,
            note: String,
        }

        if let Ok(child_spec) = std::env::var(CHILD_ENV) {
            let (path_str, marker_str) = child_spec
                .split_once('|')
                .expect("child spec malformed: expected PATH|MARKER");
            let path = PathBuf::from(path_str);
            let marker = PathBuf::from(marker_str);

            let cfg = KillSwitch {
                use_edge_predictor: false,
                shadow_mode: false,
                note: "sigkill regression".into(),
            };
            write_toml_atomic_fsynced(&cfg, &path)
                .expect("child helper write must succeed");
            std::fs::write(&marker, b"ok").expect("child marker write");
            // Idle until parent SIGKILLs us. Sleep keeps CPU quiet.
            // 等待 parent 的 SIGKILL。sleep 讓 CPU 靜止。
            loop {
                std::thread::sleep(std::time::Duration::from_millis(500));
            }
        }

        let tmp_dir = std::env::temp_dir().join(format!(
            "edge_predictor_sigkill_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&tmp_dir).unwrap();
        let path = tmp_dir.join("kill_switch.toml");
        let marker = tmp_dir.join("child_done.marker");

        let child_spec = format!("{}|{}", path.display(), marker.display());
        let exe = std::env::current_exe().expect("current_exe");

        // libtest filter is substring-matched by default. The full test path
        // (`config::store::tests::test_write_toml_atomic_fsynced_survives_sigkill`)
        // is hard to keep in sync if the module moves, so we pass the suffix
        // `survives_sigkill` which is unique across the crate.
        // libtest filter 預設為 substring match。完整測試路徑模組一移就要改，
        // 改傳 `survives_sigkill` 這個跨 crate 唯一的尾綴更穩。
        let mut child = std::process::Command::new(&exe)
            .args(["survives_sigkill", "--nocapture"])
            .env(CHILD_ENV, &child_spec)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("spawn child test binary");

        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while !marker.exists() {
            if std::time::Instant::now() > deadline {
                let _ = child.kill();
                let _ = child.wait();
                std::fs::remove_dir_all(&tmp_dir).ok();
                panic!("child never wrote marker within 10s — fsync path likely hung");
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }

        // Child::kill() on unix maps to SIGKILL — exactly the spec T23 signal.
        // Child::kill() 在 unix 上對應 SIGKILL — 正好是 spec T23 要求的信號。
        child.kill().expect("SIGKILL child");
        let _ = child.wait();

        let contents = std::fs::read_to_string(&path)
            .expect("TOML must be durable after SIGKILL — fsync did its job");
        assert!(
            contents.contains("use_edge_predictor = false"),
            "post-SIGKILL TOML missing kill flag: {contents}"
        );
        assert!(
            contents.contains("shadow_mode = false"),
            "post-SIGKILL TOML missing shadow flag: {contents}"
        );
        assert!(
            contents.contains("sigkill regression"),
            "post-SIGKILL TOML missing note field: {contents}"
        );

        let tmp_path = path.with_extension("toml.tmp");
        assert!(
            !tmp_path.exists(),
            "tmp companion leaked after rename — atomic step likely broken"
        );

        std::fs::remove_dir_all(&tmp_dir).ok();
    }
}
