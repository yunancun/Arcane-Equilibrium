//! Pipeline wire-up helpers — extracted from event_consumer/mod.rs (I-22).
//! 管線接線輔助 — 從 event_consumer/mod.rs 提取（I-22）。

use crate::config::RuntimeConfig;
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
    cfg: &RuntimeConfig,
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
        info!(taker_rate = format!("{:.5}", rate), "pipeline using API fee rate / 管線使用 API 費率");
    }

    // P1 risk cap / P1 風險上限
    pipeline.intent_processor.set_p1_risk_pct(cfg.p1_risk_pct);
    info!(
        p1_risk_pct = format!("{:.2}%", cfg.p1_risk_pct * 100.0),
        "P1 risk cap set / P1 風險上限已設定"
    );

    // Wire ALL risk config from engine.toml → paper_state + guardian + intent_processor
    pipeline.paper_state.set_hard_stop_pct(cfg.max_stop_loss_pct);
    pipeline
        .paper_state
        .set_take_profit_pct(Some(cfg.max_take_profit_pct));
    let gc = openclaw_core::guardian::GuardianConfig {
        max_leverage: cfg.max_leverage,
        max_drawdown_pct: cfg.max_drawdown_pct,
        max_same_direction_positions: cfg.max_same_direction_positions as usize,
        ..openclaw_core::guardian::GuardianConfig::default()
    };
    pipeline.intent_processor.update_guardian_config(gc);

    // RRC-1-B4: Wire RiskManagerConfig from engine.toml → IntentProcessor Gate 0
    let mut rc = openclaw_core::risk::RiskManagerConfig::default();
    rc.max_stop_loss_pct = cfg.max_stop_loss_pct;
    rc.max_take_profit_pct = cfg.max_take_profit_pct;
    rc.max_leverage = cfg.max_leverage;
    rc.max_total_exposure_pct = cfg.max_total_exposure_pct;
    rc.max_session_drawdown_pct = cfg.max_drawdown_pct;
    pipeline.intent_processor.update_risk_config(rc);

    info!(
        hard_stop = format!("{:.1}%", cfg.max_stop_loss_pct),
        take_profit = format!("{:.1}%", cfg.max_take_profit_pct),
        max_leverage = cfg.max_leverage,
        max_drawdown = format!("{:.1}%", cfg.max_drawdown_pct),
        max_positions = cfg.max_same_direction_positions,
        max_exposure = format!("{:.1}%", cfg.max_total_exposure_pct),
        "risk config wired from engine.toml / 風控配置已從 engine.toml 接入"
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
