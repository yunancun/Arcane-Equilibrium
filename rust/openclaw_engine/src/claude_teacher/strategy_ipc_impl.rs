//! Production StrategyIpcSink wrapping PaperSessionCommand sender (Phase 4 W-1).
//! 生產環境 StrategyIpcSink wrapper，包 PaperSessionCommand sender（Phase 4 W-1）。
//!
//! MODULE_NOTE (EN):
//!   Implements `StrategyIpcSink` by sending `PaperSessionCommand` variants
//!   (UpdateStrategyParams / SetStrategyActive) into the existing event-consumer
//!   command channel. Each variant carries a `tokio::sync::oneshot::Sender`
//!   for ack/error propagation, which we use here to await Rust's confirmation
//!   before returning to the directive applier.
//!
//!   ARCH-RC1: this is the ONLY production sink. The trait surface
//!   (`update_strategy_params` + `set_strategy_active`) is intentionally
//!   limited to Rust-only methods. Adding any path that touches Python
//!   `RiskManager` here would violate the architecture invariant.
//!
//! MODULE_NOTE (中):
//!   實作 `StrategyIpcSink` — 透過既有 event-consumer 命令通道發送
//!   `PaperSessionCommand` variant（UpdateStrategyParams / SetStrategyActive）。
//!   每個 variant 帶 `tokio::sync::oneshot::Sender` 傳回 ack/error，本 wrapper
//!   await Rust 確認後才返回 directive applier。
//!
//!   ARCH-RC1：這是**唯一**的生產 sink。trait 介面（update_strategy_params +
//!   set_strategy_active）刻意只限 Rust-only 方法。在這裡加任何觸 Python
//!   `RiskManager` 的路徑都違反架構不變量。

use crate::claude_teacher::applier::{IpcFuture, StrategyIpcSink};
use crate::tick_pipeline::PaperSessionCommand;
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};

/// EN: Default IPC ack timeout (5 seconds).
/// 中文: 預設 IPC ack 超時（5 秒）。
const DEFAULT_IPC_TIMEOUT_MS: u64 = 5_000;

/// EN: Production StrategyIpcSink that forwards into the PaperSessionCommand channel.
/// 中文: 把呼叫轉發到 PaperSessionCommand 通道的生產 StrategyIpcSink。
pub struct PaperSessionCommandSink {
    sender: mpsc::UnboundedSender<PaperSessionCommand>,
    timeout_ms: u64,
}

impl PaperSessionCommandSink {
    /// EN: Construct with the existing PaperSessionCommand sender (cloned from main.rs).
    /// 中文: 用既有的 PaperSessionCommand sender 構造（從 main.rs clone）。
    pub fn new(sender: mpsc::UnboundedSender<PaperSessionCommand>) -> Self {
        Self {
            sender,
            timeout_ms: DEFAULT_IPC_TIMEOUT_MS,
        }
    }

    /// EN: Override the per-call timeout.
    /// 中文: 覆寫單次呼叫的超時。
    pub fn with_timeout_ms(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }
}

impl StrategyIpcSink for PaperSessionCommandSink {
    fn update_strategy_params<'a>(
        &'a self,
        strategy_name: &'a str,
        params_json: &'a str,
    ) -> IpcFuture<'a> {
        let strategy = strategy_name.to_string();
        let params = params_json.to_string();
        let sender = self.sender.clone();
        let timeout = Duration::from_millis(self.timeout_ms);
        Box::pin(async move {
            let (tx, rx) = oneshot::channel();
            let cmd = PaperSessionCommand::UpdateStrategyParams {
                strategy_name: strategy,
                params_json: params,
                response_tx: tx,
            };
            sender
                .send(cmd)
                .map_err(|e| format!("ipc send failed (UpdateStrategyParams): {e}"))?;
            tokio::time::timeout(timeout, rx)
                .await
                .map_err(|_| "ipc timeout (UpdateStrategyParams)".to_string())?
                .map_err(|_| "ipc cancelled (UpdateStrategyParams)".to_string())?
        })
    }

    fn set_strategy_active<'a>(
        &'a self,
        strategy_name: &'a str,
        active: bool,
    ) -> IpcFuture<'a> {
        let strategy = strategy_name.to_string();
        let sender = self.sender.clone();
        let timeout = Duration::from_millis(self.timeout_ms);
        Box::pin(async move {
            let (tx, rx) = oneshot::channel();
            let cmd = PaperSessionCommand::SetStrategyActive {
                strategy_name: strategy,
                active,
                response_tx: tx,
            };
            sender
                .send(cmd)
                .map_err(|e| format!("ipc send failed (SetStrategyActive): {e}"))?;
            tokio::time::timeout(timeout, rx)
                .await
                .map_err(|_| "ipc timeout (SetStrategyActive)".to_string())?
                .map_err(|_| "ipc cancelled (SetStrategyActive)".to_string())?
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// EN: Receiver thread that auto-acks any incoming PaperSessionCommand
    ///     by sending Ok("ack") to the response_tx.
    /// 中文: 接收 thread，對任何傳入的 PaperSessionCommand 自動回 Ok("ack")。
    fn spawn_ack_receiver(
        mut rx: mpsc::UnboundedReceiver<PaperSessionCommand>,
        seen: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    ) {
        tokio::spawn(async move {
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PaperSessionCommand::UpdateStrategyParams {
                        strategy_name,
                        response_tx,
                        ..
                    } => {
                        seen.lock()
                            .unwrap()
                            .push(format!("update:{}", strategy_name));
                        let _ = response_tx.send(Ok("ack".to_string()));
                    }
                    PaperSessionCommand::SetStrategyActive {
                        strategy_name,
                        active,
                        response_tx,
                        ..
                    } => {
                        seen.lock()
                            .unwrap()
                            .push(format!("set_active:{}:{}", strategy_name, active));
                        let _ = response_tx.send(Ok("ack".to_string()));
                    }
                    _ => {
                        // Ignore other variants
                        // 忽略其他 variant
                    }
                }
            }
        });
    }

    #[tokio::test]
    async fn test_send_update_strategy_params_via_channel() {
        let (tx, rx) = mpsc::unbounded_channel();
        let seen = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        spawn_ack_receiver(rx, std::sync::Arc::clone(&seen));
        let sink = PaperSessionCommandSink::new(tx);
        let result = sink
            .update_strategy_params("ma_crossover", r#"{"min_confidence":0.5}"#)
            .await;
        assert!(result.is_ok());
        // Allow receiver to record the call
        // 等待 receiver 記錄呼叫
        tokio::task::yield_now().await;
        let logged = seen.lock().unwrap().clone();
        assert!(logged.iter().any(|s| s == "update:ma_crossover"));
    }

    #[tokio::test]
    async fn test_send_set_strategy_active_via_channel() {
        let (tx, rx) = mpsc::unbounded_channel();
        let seen = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        spawn_ack_receiver(rx, std::sync::Arc::clone(&seen));
        let sink = PaperSessionCommandSink::new(tx);
        let result = sink.set_strategy_active("bb_breakout", true).await;
        assert!(result.is_ok());
        tokio::task::yield_now().await;
        let logged = seen.lock().unwrap().clone();
        assert!(logged.iter().any(|s| s == "set_active:bb_breakout:true"));
    }

    #[tokio::test]
    async fn test_send_failed_when_channel_closed() {
        let (tx, rx) = mpsc::unbounded_channel();
        drop(rx); // close receiver immediately / 立即關閉 receiver
        let sink = PaperSessionCommandSink::new(tx);
        let result = sink.update_strategy_params("any", "{}").await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("ipc send failed"));
    }

    #[tokio::test]
    async fn test_timeout_returns_err_when_no_ack() {
        // Receiver that consumes commands but never responds → timeout fires.
        // Receiver 消費命令但永不回應 → timeout 觸發。
        let (tx, mut rx) = mpsc::unbounded_channel();
        tokio::spawn(async move {
            while let Some(_cmd) = rx.recv().await {
                // Drop the response_tx by ignoring it (variant moves it inside _cmd).
                // 忽略 _cmd 即丟棄 response_tx。
            }
        });
        let sink = PaperSessionCommandSink::new(tx).with_timeout_ms(50);
        let result = sink.update_strategy_params("any", "{}").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        // Either "ipc timeout" (waited 50ms) or "ipc cancelled" (sender dropped).
        // Both are valid fail-closed paths.
        // "ipc timeout" 或 "ipc cancelled" 都是有效的 fail-closed 路徑。
        assert!(err.contains("ipc timeout") || err.contains("ipc cancelled"));
    }

    #[tokio::test]
    async fn test_with_timeout_ms_overrides_default() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let sink = PaperSessionCommandSink::new(tx).with_timeout_ms(123);
        assert_eq!(sink.timeout_ms, 123);
    }
}
