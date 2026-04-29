//! Cycle counter state for `strategist_scheduler`.
//! `strategist_scheduler` 的 cycle 計數器狀態。
//!
//! MODULE_NOTE (EN): Extracted from parent `mod.rs` by G5-08 to keep the
//! scheduler module under the §九 1200-line hard cap. The public re-export from
//! `mod.rs` preserves `openclaw_engine::strategist_scheduler::CycleCounters`,
//! `CycleCountersSnapshot`, and `REJECT_REASONS`.
//! MODULE_NOTE (中): G5-08 從父 `mod.rs` 抽出，讓 scheduler 主檔回到 §九
//! 1200 行硬上限以下；`mod.rs` re-export 保持外部路徑不變。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

/// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25, MVP slice).
/// Thread-safe cycle counters: per-reason reject tally + apply count + last-ts.
/// Exposed via IPC (`get_strategist_cycle_metrics`) so the GUI can replace the
/// engine.log tail-parse fallback with a structured pull. Persistent DB sink
/// (`learning.strategist_cycle_events`) is **deliberately deferred** — see
/// TODO §G3-11 downgrade rationale: PERSIST-AUDIT-GAP-COUNTER-1 already gives
/// `strategist_applied_params` rows for cross-validation, and an in-memory
/// snapshot satisfies the 80% observability case without a new hypertable.
///
/// G3-11：執行緒安全的 cycle 計數器。reject 按 reason / apply 次數 / 最後時戳
/// 都暴露給 IPC。DB sink 故意延後（理由見 TODO 降級）。
#[derive(Debug, Default)]
pub struct CycleCounters {
    /// Total apply / 累計 apply 次數
    apply_count: AtomicU64,
    /// Total cycles attempted (regardless of outcome)
    /// 累計 cycle 嘗試次數（無論結果）
    cycle_count: AtomicU64,
    /// Last time `evaluate_cycle` finished (Ok or Err) in epoch-ms.
    /// 最後一次 evaluate_cycle 完成時的時戳（無論成敗）。
    last_cycle_ts_ms: AtomicU64,
    /// Last successful apply timestamp (epoch-ms). 0 if never applied.
    /// 最後一次成功 apply 的時戳；從未 apply 為 0。
    last_apply_ts_ms: AtomicU64,
    /// Per-reason reject tally. Reasons are short stable strings
    /// (`out_of_range`, `delta_exceeded`, `weight_sum`, `not_object`,
    /// `ipc_failed`, `apply_failed`).
    /// reject 按 reason 累計。reason 為短穩定字串。
    reject_by_reason: Mutex<HashMap<String, u64>>,
}

impl CycleCounters {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a rejected recommendation by reason.
    /// 按 reason 記錄一個被拒的建議。
    pub fn record_reject(&self, reason: &str) {
        let mut map = match self.reject_by_reason.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(), // poisoned — recover and continue
        };
        *map.entry(reason.to_string()).or_insert(0) += 1;
    }

    /// Record a successful apply (validated + sent through PipelineCommand).
    /// 記錄一次成功 apply。
    pub fn record_apply(&self, now_ms: u64) {
        self.apply_count.fetch_add(1, Ordering::Relaxed);
        self.last_apply_ts_ms.store(now_ms, Ordering::Relaxed);
    }

    /// Record cycle completion (Ok or Err) — updates `last_cycle_ts_ms` and
    /// the cycle counter. Called once per `evaluate_cycle` regardless of
    /// outcome so freshness checks (healthcheck `[16]`) work even when
    /// the AI service is down.
    /// 記錄 cycle 完成（無論成敗）— 健康檢查需要新鮮度即使 AI service 掛掉。
    pub fn record_cycle_finish(&self, now_ms: u64) {
        self.cycle_count.fetch_add(1, Ordering::Relaxed);
        self.last_cycle_ts_ms.store(now_ms, Ordering::Relaxed);
    }

    /// Snapshot the current counter state into a serializable struct.
    /// 把當前計數狀態快照成可序列化的 struct。
    pub fn snapshot(&self) -> CycleCountersSnapshot {
        let reject_map = match self.reject_by_reason.lock() {
            Ok(g) => g.clone(),
            Err(p) => p.into_inner().clone(),
        };
        CycleCountersSnapshot {
            apply_count: self.apply_count.load(Ordering::Relaxed),
            cycle_count: self.cycle_count.load(Ordering::Relaxed),
            last_cycle_ts_ms: self.last_cycle_ts_ms.load(Ordering::Relaxed),
            last_apply_ts_ms: self.last_apply_ts_ms.load(Ordering::Relaxed),
            reject_by_reason: reject_map,
        }
    }
}

/// Serializable snapshot of `CycleCounters` returned by IPC
/// `get_strategist_cycle_metrics`.
/// CycleCounters 的可序列化快照，回給 IPC `get_strategist_cycle_metrics`。
#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct CycleCountersSnapshot {
    pub apply_count: u64,
    pub cycle_count: u64,
    pub last_cycle_ts_ms: u64,
    pub last_apply_ts_ms: u64,
    pub reject_by_reason: HashMap<String, u64>,
}

/// Reject-reason short tags. Stable strings — used as JSON keys + healthcheck
/// matchers. Any new reason added in `validate_recommendation_with_reason`
/// MUST also be listed here so consumers know the universe.
/// reject reason 短標籤。穩定字串；新增 reason 也要更新此 list。
pub const REJECT_REASONS: &[&str] = &[
    "not_object",
    "out_of_range",
    "delta_exceeded",
    "weight_sum",
    "ipc_failed",
    "apply_failed",
];
