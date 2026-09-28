//! H1：本機送出進度與 venue 證據分流；不提供跨重啟恢復。

use std::collections::HashSet;
use std::sync::Arc;

/// dispatch 與 pipeline 共用的未結案集合；鎖內同時檢查及保留，避免排隊開倉穿透。
/// 任何未結案單均禁止新增開倉；reduce-only 平倉仍可進入原有受控路徑。
#[derive(Clone, Debug, Default)]
pub(crate) struct SubmissionGuard(Arc<parking_lot::Mutex<HashSet<String>>>);

impl SubmissionGuard {
    pub(crate) fn reserve(&self, id: &str, is_close: bool) -> bool {
        let mut pending = self.0.lock();
        if pending.contains(id) || (!is_close && !pending.is_empty()) {
            return false;
        }
        pending.insert(id.to_owned());
        true
    }

    pub(crate) fn track(&self, id: &str) {
        self.0.lock().insert(id.to_owned());
    }

    pub(crate) fn resolve(&self, id: &str) {
        self.0.lock().remove(id);
    }

    pub(crate) fn blocks_entry(&self) -> bool {
        !self.0.lock().is_empty()
    }

    pub(crate) fn contains(&self, id: &str) -> bool {
        self.0.lock().contains(id)
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
