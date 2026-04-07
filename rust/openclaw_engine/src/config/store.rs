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
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

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
}

impl<T: Clone + Send + Sync + 'static> ConfigStore<T> {
    /// Create a new store with an initial value.
    /// 建立新 store，帶初始值。
    pub fn new(initial: T) -> Self {
        Self {
            inner: ArcSwap::from_pointee(initial),
            version: AtomicU64::new(0),
            write_lock: Mutex::new(()),
        }
    }

    /// Lock-free snapshot read (~5ns). Safe to call from tick hot path.
    /// 無鎖快照讀取（~5ns）。可在 tick 熱路徑安全呼叫。
    pub fn load(&self) -> Arc<T> {
        self.inner.load_full()
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
        Ok(PatchOutcome {
            version: new_version,
            source,
        })
    }
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

    #[test]
    fn test_patch_source_as_str() {
        assert_eq!(PatchSource::Operator.as_str(), "operator");
        assert_eq!(PatchSource::Agent.as_str(), "agent");
        assert_eq!(PatchSource::Migration.as_str(), "migration");
        assert_eq!(PatchSource::Startup.as_str(), "startup");
    }
}
