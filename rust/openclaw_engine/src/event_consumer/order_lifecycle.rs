//! H1：本機送出進度與 venue 證據分流；不提供跨重啟恢復。

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

/// dispatch 與 pipeline 共用的未結案集合；鎖內同時檢查及保留，避免排隊開倉穿透。
/// 任何未結案單均禁止新增開倉；reduce-only 平倉仍可進入原有受控路徑。
#[derive(Clone, Debug, Default)]
pub(crate) struct SubmissionGuard(Arc<parking_lot::Mutex<HashMap<String, SubmissionPhase>>>);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SubmissionPhase {
    Queued,
    Claimed,
}

impl SubmissionGuard {
    pub(crate) fn reserve(&self, id: &str, is_close: bool) -> bool {
        let mut pending = self.0.lock();
        // The producer reserved before persistence; exactly one dispatcher may
        // claim that queued request. An already-dispatched ID remains a duplicate.
        if pending.get(id) == Some(&SubmissionPhase::Queued) {
            pending.insert(id.to_owned(), SubmissionPhase::Claimed);
            return true;
        }
        if pending.contains_key(id) || (!is_close && !pending.is_empty()) {
            return false;
        }
        pending.insert(id.to_owned(), SubmissionPhase::Claimed);
        true
    }

    pub(crate) fn reserve_queued(&self, id: &str, is_close: bool) -> bool {
        let mut pending = self.0.lock();
        if pending.contains_key(id) || (!is_close && !pending.is_empty()) {
            return false;
        }
        pending.insert(id.to_owned(), SubmissionPhase::Queued);
        true
    }

    pub(crate) fn track(&self, id: &str) {
        self.0
            .lock()
            .insert(id.to_owned(), SubmissionPhase::Claimed);
    }

    pub(crate) fn resolve(&self, id: &str) {
        self.0.lock().remove(id);
    }

    pub(crate) fn clear(&self) {
        self.0.lock().clear();
    }

    pub(crate) fn blocks_entry(&self) -> bool {
        !self.0.lock().is_empty()
    }

    pub(crate) fn contains(&self, id: &str) -> bool {
        self.0.lock().contains_key(id)
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum OrderStatus {
    #[default]
    PendingSubmit,
    Submitted,
    Acknowledged,
    Unknown,
    Working,
    PartiallyFilled,
    Filled,
    Cancelled,
    PartiallyFilledCanceled,
    Rejected,
    Deactivated,
}

impl OrderStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PendingSubmit => "PendingSubmit",
            Self::Submitted => "Submitted",
            Self::Acknowledged => "Acknowledged",
            Self::Unknown => "Unknown",
            Self::Working => "Working",
            Self::PartiallyFilled => "PartiallyFilled",
            Self::Filled => "Filled",
            Self::Cancelled => "Cancelled",
            Self::PartiallyFilledCanceled => "PartiallyFilledCanceled",
            Self::Rejected => "Rejected",
            Self::Deactivated => "Deactivated",
        }
    }

    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Filled
                | Self::Cancelled
                | Self::PartiallyFilledCanceled
                | Self::Rejected
                | Self::Deactivated
        )
    }
}

#[derive(Clone, Debug, Default)]
pub struct OrderProgress {
    pub status: OrderStatus,
    /// order topic 只宣告累計量；execution topic 仍是唯一持倉寫入者。
    pub venue_filled_qty: Option<f64>,
    pub venue_reject_reason: String,
    /// A queued reprice successor owns close protection; this predecessor only
    /// retains fill attribution until its own terminal confirmation arrives.
    pub replacement_order_link_id: Option<String>,
    /// Earliest next bounded read-only confirmation batch; retained across failures.
    pub reconciliation_retry_after_ms: Option<u64>,
    /// Partial-entry grace has its own clock; registration identity is immutable.
    pub maker_remainder_started_ts_ms: Option<u64>,
    /// One in-flight cancel attempt per incarnation; ACK never proves terminal.
    pub maker_cancel_attempt_ts_ms: Option<u64>,
    pub maker_cancel_retry_after_ms: Option<u64>,
    /// Keep per-order replay dedup until terminal cleanup, independent of the global FIFO.
    pub applied_execution_ids: HashSet<String>,
}

impl OrderProgress {
    /// REST／transport 事件不得覆寫已觀察到的 WS 證據。
    pub(crate) fn dispatch_status(&mut self, next: OrderStatus) -> bool {
        let allowed = match next {
            OrderStatus::Submitted => self.status == OrderStatus::PendingSubmit,
            OrderStatus::Acknowledged => matches!(
                self.status,
                OrderStatus::PendingSubmit | OrderStatus::Submitted
            ),
            OrderStatus::Unknown => matches!(
                self.status,
                OrderStatus::PendingSubmit | OrderStatus::Submitted | OrderStatus::Acknowledged
            ),
            _ => false,
        };
        if allowed {
            self.status = next;
        }
        allowed
    }

    pub(crate) fn executions_accounted(&self, filled: f64) -> bool {
        self.status.is_terminal()
            && self
                .venue_filled_qty
                .is_some_and(|expected| filled + 1e-10 >= expected)
    }
}

#[cfg(test)]
mod tests {
    use super::SubmissionGuard;

    #[test]
    fn h1_queued_admission_transfers_once_and_retains_reduce_only_access() {
        let guard = SubmissionGuard::default();
        assert!(guard.reserve_queued("entry", false));
        assert!(!guard.reserve_queued("second-entry", false));
        assert!(guard.reserve_queued("protection", true));
        let dispatcher = guard.clone();
        assert!(dispatcher.reserve("entry", false));
        assert!(
            !dispatcher.reserve("entry", false),
            "duplicate cannot claim a second submission"
        );
        assert!(!dispatcher.reserve("unreserved-entry", false));
        dispatcher.resolve("entry");
        assert!(
            guard.blocks_entry(),
            "queued protection is still unresolved"
        );
        assert!(dispatcher.reserve("protection", true));
        dispatcher.resolve("protection");
        assert!(!guard.blocks_entry());
    }
}
