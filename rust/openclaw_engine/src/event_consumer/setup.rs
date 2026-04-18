//! Pipeline wire-up helpers — extracted from event_consumer/mod.rs (I-22).
//! 管線接線輔助 — 從 event_consumer/mod.rs 提取（I-22）。

use crate::config::EngineBootstrap;
use crate::database::{DecisionContextMsg, MarketDataMsg, TradingMsg};
use crate::feature_collector::FeatureSnapshot;
use crate::instrument_info::InstrumentInfoCache;
use crate::tick_pipeline::TickPipeline;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::info;

/// Wire fee rate, risk config, instrument cache, and DB channels into the pipeline.
/// 將費率、風控配置、合約緩存與 DB 通道接入管線。
#[allow(clippy::too_many_arguments)]
pub(super) fn wire_pipeline(
    pipeline: &mut TickPipeline,
    _cfg: &EngineBootstrap,
    taker_fee_rate: Option<f64>,
    shared_instruments: Option<&Arc<InstrumentInfoCache>>,
    market_data_tx: Option<mpsc::Sender<MarketDataMsg>>,
    feature_tx: Option<mpsc::Sender<FeatureSnapshot>>,
    trading_tx: Option<mpsc::Sender<TradingMsg>>,
    context_tx: Option<mpsc::Sender<DecisionContextMsg>>,
) {
    // PNL-2: log H0Gate wiring on boot so operators can confirm fresh binary.
    info!(
        shadow_mode = pipeline.h0_gate.config().shadow_mode,
        "H0Gate wired in tick_pipeline (PNL-2) / H0 門控已接入"
    );

    // Item 2: dynamic fee rate / 動態費率
    if let Some(rate) = taker_fee_rate {
        pipeline.set_fee_rate(rate);
        info!(
            taker_rate = format!("{:.5}", rate),
            "pipeline using API fee rate / 管線使用 API 費率"
        );
    }

    // ARCH-RC1 1C-1: All risk seed values come from RiskConfig::default().
    // RuntimeConfig no longer carries risk fields (deleted in Batch 5).
    // Session 1C-2 will inject a live ConfigStore<RiskConfig> handle loaded from
    // settings/risk_control_rules/risk_config.toml (with operator overrides).
    // ARCH-RC1 1C-1：所有風控種子值改從 RiskConfig::default() 讀取；
    // RuntimeConfig 已不持有風控欄位（Batch 5 刪除）。
    let default_risk = crate::config::RiskConfig::default();

    // P1 risk cap (IntentProcessor internal knob; will migrate to RiskConfig in 1C-2)
    // IntentProcessor uses its built-in DEFAULT_P1_RISK_PCT (2%) when unset.
    // P1 每筆交易風險上限（IntentProcessor 內部旋鈕，1C-2 遷入 RiskConfig）

    pipeline
        .paper_state
        .set_hard_stop_pct(default_risk.limits.stop_loss_max_pct);
    pipeline
        .paper_state
        .set_take_profit_pct(Some(default_risk.limits.take_profit_max_pct));
    // ARCH-RC1 1C-4 E-Merge-4: GuardianConfig is fully derived from RiskConfig
    // — no read-modify-write, no Default fallback for any field.
    // ARCH-RC1 1C-4 E-Merge-4：GuardianConfig 完全派生自 RiskConfig，無 RMW，
    // 任何欄位都不走 Default 回退。
    let gc = openclaw_core::guardian::GuardianConfig {
        max_leverage: default_risk.limits.leverage_max,
        max_drawdown_pct: default_risk.limits.session_drawdown_max_pct,
        max_same_direction_positions: default_risk.anti_cluster.max_same_direction as usize,
        modification_size_factor: default_risk.limits.guardian_modification_size_factor,
        modification_leverage_cap: default_risk.limits.guardian_modification_leverage_cap,
    };
    pipeline.intent_processor.update_guardian_config(gc);
    pipeline
        .intent_processor
        .update_risk_config(default_risk.clone());

    info!(
        hard_stop = format!("{:.1}%", default_risk.limits.stop_loss_max_pct),
        take_profit = format!("{:.1}%", default_risk.limits.take_profit_max_pct),
        max_leverage = default_risk.limits.leverage_max,
        max_drawdown = format!("{:.1}%", default_risk.limits.session_drawdown_max_pct),
        max_positions = default_risk.anti_cluster.max_same_direction,
        max_exposure = format!("{:.1}%", default_risk.limits.total_exposure_max_pct),
        "risk config seeded from RiskConfig::default() [ARCH-RC1 1C-1; 1C-2 will wire ConfigStore]"
    );

    // R-05: instrument cache for precision rounding
    if let Some(icache) = shared_instruments {
        pipeline.set_instrument_cache(Arc::clone(icache));
        info!("pipeline using instrument cache for precision rounding / 管線使用合約信息緩存");
    }

    // Phase 1: market data + feature + trading + context channels
    if let Some(tx) = market_data_tx {
        pipeline.set_market_data_channel(tx);
        info!("pipeline market_data channel wired / 管線市場數據通道已接入");
    }
    if let Some(tx) = feature_tx {
        pipeline.set_feature_channel(tx);
        info!("pipeline feature channel wired / 管線特徵通道已接入");
    }
    if let Some(tx) = trading_tx {
        pipeline.set_trading_channel(tx);
        info!("pipeline trading channel wired / 管線交易通道已接入");
    }
    if let Some(tx) = context_tx {
        pipeline.set_context_channel(tx);
        info!("pipeline context channel wired / 管線上下文通道已接入");
    }
}
