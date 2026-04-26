//! WebSocket connection state + logging helpers.
//! WebSocket 連接狀態與日誌輔助。
//!
//! MODULE_NOTE (EN): The `WsState` enum is the visible state machine for the
//!   client (Connecting → Connected → Reconnecting → Disconnected). Logging
//!   helper `log_state` writes a uniform event per transition. Pure / no I/O
//!   beyond `tracing`.
//! MODULE_NOTE (中): `WsState` 是 client 可見的狀態機（Connecting → Connected
//!   → Reconnecting → Disconnected）。`log_state` 為每次轉換寫一致的事件。
//!   除 `tracing` 外無 I/O。

use tracing::{info, warn};

/// WebSocket connection state.
/// WebSocket 連接狀態。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WsState {
    /// Attempting initial or re-connection / 嘗試連接中
    Connecting,
    /// Connected and receiving data / 已連接並接收數據
    Connected,
    /// Lost connection, will retry / 連接斷開，將重試
    Reconnecting,
    /// Shut down / 已關閉
    Disconnected,
}

impl std::fmt::Display for WsState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Connecting => write!(f, "Connecting"),
            Self::Connected => write!(f, "Connected"),
            Self::Reconnecting => write!(f, "Reconnecting"),
            Self::Disconnected => write!(f, "Disconnected"),
        }
    }
}

/// Log state transition.
/// 記錄狀態轉換。
pub(super) fn log_state(state: WsState, attempt: u32) {
    match state {
        WsState::Connected => info!(state = %state, "WebSocket connected / WebSocket 已連接"),
        WsState::Disconnected => info!(state = %state, "WebSocket disconnected / WebSocket 已斷開"),
        WsState::Connecting => {
            info!(state = %state, attempt = attempt, "WebSocket connecting / WebSocket 連接中")
        }
        WsState::Reconnecting => {
            warn!(state = %state, attempt = attempt, "WebSocket reconnecting / WebSocket 重連中")
        }
    }
}
