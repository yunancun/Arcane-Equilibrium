//! Per-engine IPC routing primitives — `PerEngineRiskStores` (per-mode
//! `RiskConfig` ConfigStore bundle) + `EngineCommandChannels` (per-pipeline
//! `PipelineCommand` mpsc senders) + `extract_engine_tx` dispatcher helper.
//! 每引擎 IPC 路由原語 — `PerEngineRiskStores`（每模式 `RiskConfig`
//! ConfigStore 綑綁）+ `EngineCommandChannels`（每管線 `PipelineCommand`
//! mpsc 發送端）+ `extract_engine_tx` 分派輔助。
//!
//! MODULE_NOTE (EN): Centralises the "select the right pipeline by `engine`
//!   string" logic that LIVE-P2-1 (RiskConfig) and 3E-3 (command channels)
//!   added across the IPC handlers. Both bundles default unknown / missing
//!   engine names to `paper` (fail-safe). `extract_engine_tx` additionally
//!   falls back to the primary pipeline when no `engine` param is supplied,
//!   logging a debug hint so the migration to explicit engine routing can
//!   be observed in logs.
//! MODULE_NOTE (中)：集中 LIVE-P2-1（RiskConfig）與 3E-3（命令通道）在
//!   IPC handler 各處新增的「依 `engine` 字串選擇正確管線」邏輯。兩個綑綁都
//!   把未知/缺失的引擎名 default 到 `paper`（安全默認）。`extract_engine_tx`
//!   在缺 `engine` 參數時退到主要管線，並 debug log 一行提示，便於觀測
//!   遷移到明確 engine 路由的進度。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26).
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）從 `ipc_server/mod.rs` 拆出。

use crate::config::{ConfigStore, RiskConfig};
use crate::tick_pipeline::PipelineCommand;
use std::sync::Arc;

// ---------------------------------------------------------------------------
// LIVE-P2-1: Per-engine RiskConfig stores
// LIVE-P2-1：每個引擎模式的 RiskConfig stores
// ---------------------------------------------------------------------------

/// Bundles three RiskConfig stores — one per PipelineKind — so IPC routing and
/// TickPipeline wiring can select the correct store without scattering
/// individual Option<Arc<...>> fields across every function signature.
///
/// 將三個 RiskConfig stores 捆綁為一個結構體（每個 PipelineKind 一個），
/// 使 IPC 路由與 TickPipeline 接線可以選擇正確 store，
/// 而不需在每個函數簽名中分散獨立的 Option<Arc<...>> 字段。
#[derive(Clone)]
pub struct PerEngineRiskStores {
    /// Paper-only mode (no exchange connection) — liberal limits for strategy validation.
    /// 純 paper 模式（無交易所連接）— 寬鬆限制，用於策略驗證。
    pub paper: Arc<ConfigStore<RiskConfig>>,
    /// Demo mode (Bybit Demo exchange, simulated margin) — same as paper by default.
    /// Demo 模式（Bybit Demo 交易所，模擬保證金）— 默認與 paper 相同。
    pub demo: Arc<ConfigStore<RiskConfig>>,
    /// Live mode (real money, Mainnet) — tighter defaults, operator must relax before go-live.
    /// 實盤模式（真實資金，主網）— 更保守的默認值，Operator 需主動放寬才能上線。
    pub live: Arc<ConfigStore<RiskConfig>>,
}

impl PerEngineRiskStores {
    /// Select the store matching the given engine name string.
    /// Unknown names fall through to `paper` (fail-safe default).
    /// 按引擎名稱字符串選擇 store。未知名稱回退到 `paper`（安全默認）。
    pub fn select(&self, engine: &str) -> &Arc<ConfigStore<RiskConfig>> {
        match engine {
            "demo" => &self.demo,
            "live" => &self.live,
            _ => &self.paper, // "paper" or unknown → paper (fail-safe)
        }
    }
}

// ---------------------------------------------------------------------------
// 3E-3: Per-pipeline command channel routing
// 3E-3：每管線命令通道路由
// ---------------------------------------------------------------------------

/// Routes IPC commands to the correct pipeline's command channel.
/// In 3E-ARCH, each pipeline (Paper/Demo/Live) has its own command channel.
/// IPC handlers extract the `engine` param and select the correct sender.
///
/// 將 IPC 命令路由到正確管線的命令通道。
/// 3E-ARCH 下每個管線有獨立命令通道，IPC handler 按 `engine` 參數選擇。
#[derive(Clone, Default)]
pub struct EngineCommandChannels {
    pub paper: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    pub demo: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    pub live: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
}

impl EngineCommandChannels {
    /// Select the command sender for the given engine name.
    /// Falls back to paper for unknown names (fail-safe).
    /// 按引擎名選擇命令發送端。未知名稱回退到 paper（安全默認）。
    pub fn select(
        &self,
        engine: &str,
    ) -> &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        match engine {
            "demo" => &self.demo,
            "live" => &self.live,
            _ => &self.paper, // "paper" or unknown → paper (fail-safe)
        }
    }

    /// Return the primary (first available) sender for commands that
    /// don't specify an engine param. Priority: live > demo > paper.
    /// 返回主要（第一個可用）sender，供未指定 engine 的命令使用。
    pub fn primary(&self) -> &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        if self.live.is_some() {
            &self.live
        } else if self.demo.is_some() {
            &self.demo
        } else {
            &self.paper
        }
    }

    /// Return the label of the primary engine ("live" / "demo" / "paper").
    /// 返回主引擎的標籤。
    pub fn primary_label(&self) -> &'static str {
        if self.live.is_some() {
            "live"
        } else if self.demo.is_some() {
            "demo"
        } else {
            "paper"
        }
    }
}

/// 3E-3: Extract the `engine` param from request params and select the
/// matching pipeline command sender. Falls back to primary if missing.
/// 3E-3：從請求參數提取 `engine` 並選擇對應管線命令發送端，缺失時回退到主管線。
pub(crate) fn extract_engine_tx<'a>(
    params: &serde_json::Value,
    channels: &'a EngineCommandChannels,
) -> &'a Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
    match params.get("engine").and_then(|v| v.as_str()) {
        Some(engine) => channels.select(engine),
        None => {
            tracing::debug!(
                "ipc: no 'engine' param — routing to primary pipeline \
                 (add explicit engine param for deterministic routing) \
                 / ipc：無 'engine' 參數 — 路由到主管線（建議加入明確 engine 參數）"
            );
            channels.primary()
        }
    }
}
