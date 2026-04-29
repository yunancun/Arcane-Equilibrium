//! Production StrategyIpcSink wrapping PipelineCommand sender (Phase 4 W-1).
//! 生產環境 StrategyIpcSink wrapper，包 PipelineCommand sender（Phase 4 W-1）。
//!
//! MODULE_NOTE (EN):
//!   Implements `StrategyIpcSink` by sending `PipelineCommand` variants
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
//!   `PipelineCommand` variant（UpdateStrategyParams / SetStrategyActive）。
//!   每個 variant 帶 `tokio::sync::oneshot::Sender` 傳回 ack/error，本 wrapper
//!   await Rust 確認後才返回 directive applier。
//!
//!   ARCH-RC1：這是**唯一**的生產 sink。trait 介面（update_strategy_params +
//!   set_strategy_active）刻意只限 Rust-only 方法。在這裡加任何觸 Python
//!   `RiskManager` 的路徑都違反架構不變量。

use crate::claude_teacher::applier::{IpcFuture, StrategyIpcSink};
use crate::ipc_server::EngineCommandChannels;
use crate::tick_pipeline::PipelineCommand;
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};

/// EN: Default IPC ack timeout (5 seconds).
/// 中文: 預設 IPC ack 超時（5 秒）。
const DEFAULT_IPC_TIMEOUT_MS: u64 = 5_000;

/// EN: Production StrategyIpcSink that forwards into the PipelineCommand channel.
/// 中文: 把呼叫轉發到 PipelineCommand 通道的生產 StrategyIpcSink。
pub struct PipelineCommandSink {
    sender: mpsc::UnboundedSender<PipelineCommand>,
    timeout_ms: u64,
}

impl PipelineCommandSink {
    /// EN: Construct with the existing PipelineCommand sender (cloned from main.rs).
    /// 中文: 用既有的 PipelineCommand sender 構造（從 main.rs clone）。
    pub fn new(sender: mpsc::UnboundedSender<PipelineCommand>) -> Self {
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

/// EN: Production sink that routes through the per-engine command bundle.
/// Defaults Teacher tuning to Demo; Live promotion stays a separate
/// operator-authorized path and disabled Paper is never the default target.
/// 中文：透過每引擎命令 bundle 路由的生產 sink。Teacher 調參默認 Demo；
/// Live 促升保留為獨立授權路徑，disabled Paper 絕不作為默認目標。
pub struct EngineCommandSink {
    channels: EngineCommandChannels,
    target_engine: &'static str,
    timeout_ms: u64,
}

impl EngineCommandSink {
    /// EN: Construct the default Teacher sink. Demo is the only supported
    /// target for autonomous directive application in this phase.
    /// 中文：構造 Teacher 默認 sink。本階段自主 directive application 僅支援 Demo。
    pub fn demo(channels: EngineCommandChannels) -> Self {
        Self {
            channels,
            target_engine: "demo",
            timeout_ms: DEFAULT_IPC_TIMEOUT_MS,
        }
    }

    /// EN: Override the per-call timeout.
    /// 中文：覆寫單次呼叫的超時。
    pub fn with_timeout_ms(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }

    fn sender(&self) -> Result<mpsc::UnboundedSender<PipelineCommand>, String> {
        self.channels.select(self.target_engine).ok_or_else(|| {
            format!(
                "ipc route unavailable: target_engine={} command channel not bound \
                 / IPC 目標管線未綁定",
                self.target_engine
            )
        })
    }
}

impl StrategyIpcSink for EngineCommandSink {
    fn update_strategy_params<'a>(
        &'a self,
        strategy_name: &'a str,
        params_json: &'a str,
    ) -> IpcFuture<'a> {
        let strategy = strategy_name.to_string();
        let params = params_json.to_string();
        let timeout = Duration::from_millis(self.timeout_ms);
        Box::pin(async move {
            let sender = self.sender()?;
            let (tx, rx) = oneshot::channel();
            let cmd = PipelineCommand::UpdateStrategyParams {
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

    fn set_strategy_active<'a>(&'a self, strategy_name: &'a str, active: bool) -> IpcFuture<'a> {
        let strategy = strategy_name.to_string();
        let timeout = Duration::from_millis(self.timeout_ms);
        Box::pin(async move {
            let sender = self.sender()?;
            let (tx, rx) = oneshot::channel();
            let cmd = PipelineCommand::SetStrategyActive {
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

impl StrategyIpcSink for PipelineCommandSink {
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
            let cmd = PipelineCommand::UpdateStrategyParams {
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

    fn set_strategy_active<'a>(&'a self, strategy_name: &'a str, active: bool) -> IpcFuture<'a> {
        let strategy = strategy_name.to_string();
        let sender = self.sender.clone();
        let timeout = Duration::from_millis(self.timeout_ms);
        Box::pin(async move {
            let (tx, rx) = oneshot::channel();
            let cmd = PipelineCommand::SetStrategyActive {
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

    /// EN: Receiver thread that auto-acks any incoming PipelineCommand
    ///     by sending Ok("ack") to the response_tx.
    /// 中文: 接收 thread，對任何傳入的 PipelineCommand 自動回 Ok("ack")。
    fn spawn_ack_receiver(
        mut rx: mpsc::UnboundedReceiver<PipelineCommand>,
        seen: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    ) {
        tokio::spawn(async move {
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PipelineCommand::UpdateStrategyParams {
                        strategy_name,
                        response_tx,
                        ..
                    } => {
                        seen.lock()
                            .unwrap()
                            .push(format!("update:{}", strategy_name));
                        let _ = response_tx.send(Ok("ack".to_string()));
                    }
                    PipelineCommand::SetStrategyActive {
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
        let sink = PipelineCommandSink::new(tx);
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
        let sink = PipelineCommandSink::new(tx);
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
        let sink = PipelineCommandSink::new(tx);
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
        let sink = PipelineCommandSink::new(tx).with_timeout_ms(50);
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
        let sink = PipelineCommandSink::new(tx).with_timeout_ms(123);
        assert_eq!(sink.timeout_ms, 123);
    }

    #[tokio::test]
    async fn test_engine_command_sink_defaults_to_demo_not_paper() {
        let (paper_tx, mut paper_rx) = mpsc::unbounded_channel();
        let (demo_tx, demo_rx) = mpsc::unbounded_channel();
        let seen = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        spawn_ack_receiver(demo_rx, std::sync::Arc::clone(&seen));

        let mut channels = EngineCommandChannels::default();
        channels.paper = Some(paper_tx);
        channels.demo = Some(demo_tx);

        let sink = EngineCommandSink::demo(channels).with_timeout_ms(500);
        let result = sink
            .update_strategy_params("ma_crossover", r#"{"min_confidence":0.5}"#)
            .await;
        assert!(result.is_ok());
        tokio::task::yield_now().await;

        assert!(
            paper_rx.try_recv().is_err(),
            "Teacher IPC must not default-route to Paper"
        );
        let logged = seen.lock().unwrap().clone();
        assert!(logged.iter().any(|s| s == "update:ma_crossover"));
    }
}
