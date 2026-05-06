//! Scanner runner — background tokio task that drives the scan-score-select cycle.
//! 掃描器運行器 — 驅動掃描-評分-選擇週期的後台 tokio 任務。
//!
//! MODULE_NOTE (EN): ScannerRunner is spawned once at engine startup and runs forever
//!   until the CancellationToken fires. Each cycle:
//!   1. Fetch all linear perp tickers from Bybit REST
//!   2. Hard-filter → per-strategy scoring → edge bonus → correlation filter
//!   3. Query open positions from event_consumer (via PipelineCommand)
//!   4. Apply result to SymbolRegistry (anti-churn rules enforced)
//!   5. Send WsTopicChange::Subscribe/Unsubscribe for added/removed symbols
//!   6. Trigger kline bootstrap for newly added symbols
//!   7. Sleep scan_interval_secs
//! MODULE_NOTE (中): ScannerRunner 在引擎啟動時生成一次，永久運行直到 CancellationToken 觸發。
//!   每個週期：
//!   1. 從 Bybit REST 獲取所有 linear perp 行情
//!   2. 硬過濾 → 分策略評分 → 邊際獎勵 → 相關性過濾
//!   3. 從 event_consumer 查詢開放持倉（通過 PipelineCommand）
//!   4. 將結果應用到 SymbolRegistry（執行反 churn 規則）
//!   5. 為新增/移除的交易對發送 WsTopicChange::Subscribe/Unsubscribe
//!   6. 為新增的交易對觸發 kline bootstrap
//!   7. 睡眠 scan_interval_secs

use crate::database::{try_send_trading_msg, TradingMsg};
use crate::edge_estimates::EdgeEstimates;
use crate::market_data_client::MarketDataClient;
use crate::scanner::advisory::build_opportunity_decays;
use crate::scanner::config::ScannerConfig;
use crate::scanner::opportunity::OpportunityCostPrior;
use crate::scanner::registry::SymbolRegistry;
use crate::scanner::scorer::{
    apply_correlation_filter, score_ticker_for_context_opportunity_and_cost,
    score_ticker_with_policy_opportunity_and_cost,
};
use crate::scanner::strategy_policy::ScannerStrategyPolicyStores;
use crate::scanner::types::ScanResult;
use crate::tick_pipeline::PipelineCommand;
use crate::ws_client::WsTopicChange;
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Generates the list of WebSocket topics for a single symbol.
/// Includes `tickers.{sym}` so scanner-added symbols receive fundingRate /
/// indexPrice updates required by FundingArb (OC-5 / G-2), and
/// `orderbook.50.{sym}` so PostOnly maker strategies can compute passive BBO
/// prices on dynamic symbols instead of strict-skipping new entries.
/// 生成單個交易對的 WebSocket 主題列表。包含 `tickers.{sym}` 讓 scanner 新增
/// 交易對接收 FundingArb 所需的資金費率/指數價格，也包含
/// `orderbook.50.{sym}`，讓 PostOnly maker 策略在動態交易對上取得 BBO
/// 被動掛價，避免因缺 best_bid/best_ask 而跳過新開倉。
fn topics_for_symbol(symbol: &str) -> Vec<String> {
    vec![
        format!("kline.1.{symbol}"),
        format!("publicTrade.{symbol}"),
        format!("tickers.{symbol}"),
        format!("orderbook.50.{symbol}"),
    ]
}

/// Background scanner task that dynamically manages the active symbol universe.
/// 動態管理活躍交易對品類的後台掃描器任務。
pub struct ScannerRunner {
    registry: Arc<SymbolRegistry>,
    market_client: Arc<MarketDataClient>,
    edge_estimates: Arc<parking_lot::RwLock<EdgeEstimates>>,
    scanner_config: Arc<crate::config::ConfigStore<ScannerConfig>>,
    account_manager: Option<Arc<crate::account_manager::AccountManager>>,
    strategy_policy_stores: ScannerStrategyPolicyStores,
    ws_tx: mpsc::UnboundedSender<WsTopicChange>,
    pipeline_cmd_tx: mpsc::UnboundedSender<PipelineCommand>,
    trading_tx: Option<mpsc::Sender<TradingMsg>>,
    cancel: CancellationToken,
}

impl ScannerRunner {
    /// Create a new ScannerRunner.
    /// 創建新的 ScannerRunner。
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        registry: Arc<SymbolRegistry>,
        market_client: Arc<MarketDataClient>,
        edge_estimates: Arc<parking_lot::RwLock<EdgeEstimates>>,
        scanner_config: Arc<crate::config::ConfigStore<ScannerConfig>>,
        account_manager: Option<Arc<crate::account_manager::AccountManager>>,
        strategy_policy_stores: ScannerStrategyPolicyStores,
        ws_tx: mpsc::UnboundedSender<WsTopicChange>,
        pipeline_cmd_tx: mpsc::UnboundedSender<PipelineCommand>,
        trading_tx: Option<mpsc::Sender<TradingMsg>>,
        cancel: CancellationToken,
    ) -> Self {
        Self {
            registry,
            market_client,
            edge_estimates,
            scanner_config,
            account_manager,
            strategy_policy_stores,
            ws_tx,
            pipeline_cmd_tx,
            trading_tx,
            cancel,
        }
    }

    /// Run the scanner loop. Designed to be spawned with tokio::spawn.
    /// 運行掃描器循環。設計為通過 tokio::spawn 生成。
    pub async fn run(self) {
        let config = self.scanner_config.load();
        let warmup_secs = config.scheduling.warmup_delay_secs;
        drop(config); // release Arc before sleeping / 睡眠前釋放 Arc

        info!(warmup_secs, "[scanner] warmup delay / 暖機延遲");
        tokio::select! {
            _ = self.cancel.cancelled() => return,
            _ = tokio::time::sleep(Duration::from_secs(warmup_secs)) => {}
        }

        info!("[scanner] starting first scan / 開始首次掃描");

        loop {
            if self.cancel.is_cancelled() {
                info!("[scanner] cancelled / 已取消");
                break;
            }

            let scan_start = std::time::Instant::now();
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64;
            let scan_id = format!("scan-{now_ms}");

            let config = self.scanner_config.load();
            let strategy_policy = self.strategy_policy_stores.load_policy();

            // ── Step 1: Fetch all linear perp tickers / 獲取所有 linear perp 行情 ──
            let tickers = match self.market_client.get_tickers("linear", None).await {
                Ok(t) => t,
                Err(e) => {
                    warn!(error = %e, "[scanner] get_tickers failed, skipping cycle / 獲取行情失敗，跳過本週期");
                    tokio::time::sleep(Duration::from_secs(60)).await;
                    continue;
                }
            };

            let total_universe = tickers.len();

            // ── Step 2: Find BTC ticker for beta_proxy / 找 BTC 行情作 beta_proxy 分母 ──
            let btc_change_pct = tickers
                .iter()
                .find(|t| t.symbol == "BTCUSDT")
                .map(|t| t.price_change_24h_pct * 100.0) // convert ratio to % / 比率轉百分比
                .unwrap_or(0.0);

            // ── Step 3: Score each ticker / 對每個行情評分 ──
            // Use a block so the RwLockReadGuard is dropped before any await point.
            // RwLockReadGuard is not Send, so it must not be held across .await.
            // 使用塊確保 RwLockReadGuard 在任何 await 點之前被丟棄。
            let mut candidates: Vec<_> = {
                let estimates_guard = self.edge_estimates.read();
                tickers
                    .iter()
                    .filter_map(|t| {
                        let cost_prior = self.opportunity_cost_prior(&t.symbol, &config);
                        score_ticker_with_policy_opportunity_and_cost(
                            t,
                            btc_change_pct,
                            &estimates_guard,
                            &config.hard_filters,
                            &config.edge_routing,
                            &config.market_judgment,
                            &config.opportunity,
                            &strategy_policy,
                            cost_prior,
                        )
                    })
                    .collect()
            }; // estimates_guard dropped here

            let rejected_count = total_universe.saturating_sub(candidates.len());

            // Sort by final_score descending / 按 final_score 降序排序
            candidates.sort_by(|a, b| {
                b.final_score
                    .partial_cmp(&a.final_score)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });

            // ── Step 4: Correlation filter / 相關性過濾 ──
            let pinned = config.universe.pinned_symbols.clone();
            let max_dynamic = config.universe.max_symbols.saturating_sub(pinned.len());

            let filtered = apply_correlation_filter(
                candidates.clone(),
                &pinned,
                max_dynamic,
                &config.correlation,
            );

            // ── Step 5: Query open positions / 查詢開放持倉 ──
            let open_positions = self.query_open_positions().await;
            let previous_scan = self.registry.last_scan();

            // ── Step 6: Apply to registry / 應用到注冊表 ──
            let (added, removed) = self.registry.apply_scan_result(
                &filtered,
                now_ms,
                &config.anti_churn,
                &open_positions,
                max_dynamic,
            );

            // ── Step 7: Update WS subscriptions / 更新 WS 訂閱 ──
            if !added.is_empty() {
                let add_topics: Vec<String> =
                    added.iter().flat_map(|s| topics_for_symbol(s)).collect();
                if let Err(e) = self.ws_tx.send(WsTopicChange::Subscribe(add_topics)) {
                    warn!(error = %e, "[scanner] ws subscribe send failed");
                }
            }
            if !removed.is_empty() {
                let remove_topics: Vec<String> =
                    removed.iter().flat_map(|s| topics_for_symbol(s)).collect();
                if let Err(e) = self.ws_tx.send(WsTopicChange::Unsubscribe(remove_topics)) {
                    warn!(error = %e, "[scanner] ws unsubscribe send failed");
                }
            }

            // ── Step 8: Store scan result / 存儲掃描結果 ──
            let scan_duration_ms = scan_start.elapsed().as_millis() as u64;
            let active_symbols = self.registry.snapshot();
            let opportunity_decays = build_opportunity_decays(
                previous_scan.as_ref(),
                &filtered,
                &scan_id,
                now_ms,
                &open_positions,
                &added,
                &removed,
                &pinned,
            );
            let snapshot_candidates = {
                let by_selected: HashMap<&str, _> =
                    filtered.iter().map(|c| (c.symbol.as_str(), c)).collect();
                let by_ticker: HashMap<&str, _> =
                    tickers.iter().map(|t| (t.symbol.as_str(), t)).collect();
                let estimates_guard = self.edge_estimates.read();
                let mut seen = HashSet::new();
                let mut out = Vec::with_capacity(active_symbols.len());

                for symbol in &active_symbols {
                    if let Some(candidate) = by_selected.get(symbol.as_str()) {
                        if seen.insert(symbol.clone()) {
                            out.push((*candidate).clone());
                        }
                        continue;
                    }
                    if let Some(ticker) = by_ticker.get(symbol.as_str()) {
                        let cost_prior = self.opportunity_cost_prior(&ticker.symbol, &config);
                        if let Some(candidate) = score_ticker_for_context_opportunity_and_cost(
                            ticker,
                            btc_change_pct,
                            &estimates_guard,
                            &config.hard_filters,
                            &config.edge_routing,
                            &config.market_judgment,
                            &config.opportunity,
                            &strategy_policy,
                            cost_prior,
                        ) {
                            if seen.insert(symbol.clone()) {
                                out.push(candidate);
                            }
                        }
                    }
                }

                out
            };

            let scan_result = ScanResult {
                scan_ts_ms: now_ms,
                scan_id,
                active_symbols: active_symbols.clone(),
                added: added.clone(),
                removed: removed.clone(),
                candidates: snapshot_candidates,
                opportunity_decays: opportunity_decays.clone(),
                rejected_count,
                scan_duration_ms,
            };
            if let Some(ref tx) = self.trading_tx {
                let candidates = serde_json::to_value(&scan_result.candidates)
                    .unwrap_or_else(|_| serde_json::json!({"serialization_error": "candidates"}));
                let config_json = serde_json::to_value(&*config).unwrap_or_else(
                    |_| serde_json::json!({"serialization_error": "scanner_config"}),
                );
                let _ = try_send_trading_msg(
                    tx,
                    TradingMsg::ScannerSnapshot {
                        scan_id: scan_result.scan_id.clone(),
                        ts_ms: scan_result.scan_ts_ms,
                        active_symbols: scan_result.active_symbols.clone(),
                        added: scan_result.added.clone(),
                        removed: scan_result.removed.clone(),
                        rejected_count: scan_result.rejected_count as i64,
                        scan_duration_ms: scan_result.scan_duration_ms as i64,
                        candidates,
                        config: config_json,
                    },
                    "scanner_snapshot",
                );
                for decay in &opportunity_decays {
                    let _ = try_send_trading_msg(
                        tx,
                        TradingMsg::ScannerOpportunityDecay {
                            decay: decay.clone(),
                        },
                        "scanner_opportunity_decay",
                    );
                }
            }
            self.registry.store_last_scan(scan_result);

            info!(
                active = active_symbols.len(),
                added = added.len(),
                removed = removed.len(),
                rejected = rejected_count,
                duration_ms = scan_duration_ms,
                "[scanner] scan complete / 掃描完成"
            );

            // ── Step 9: Sleep until next scan / 睡眠到下次掃描 ──
            let interval_secs = config.scheduling.scan_interval_secs;
            drop(config);

            tokio::select! {
                _ = self.cancel.cancelled() => break,
                _ = tokio::time::sleep(Duration::from_secs(interval_secs)) => {}
            }
        }

        info!("[scanner] runner stopped / 掃描器已停止");
    }

    /// Query the event_consumer for the set of symbols with open positions.
    /// Returns an empty set on timeout or channel error (safe — will just defer removal).
    /// 向 event_consumer 查詢有開放持倉的交易對集合。
    /// 超時或通道錯誤時返回空集合（安全 — 只會延遲移除）。
    async fn query_open_positions(&self) -> HashSet<String> {
        let (tx, rx) = tokio::sync::oneshot::channel();
        if self
            .pipeline_cmd_tx
            .send(PipelineCommand::GetOpenPositionSymbols { response_tx: tx })
            .is_err()
        {
            warn!("[scanner] pipeline_cmd_tx send failed (channel closed?)");
            return HashSet::new();
        }
        match tokio::time::timeout(Duration::from_secs(2), rx).await {
            Ok(Ok(symbols)) => symbols,
            Ok(Err(_)) => {
                warn!("[scanner] open positions query: response channel dropped");
                HashSet::new()
            }
            Err(_) => {
                warn!("[scanner] open positions query timed out (2s)");
                HashSet::new()
            }
        }
    }

    fn opportunity_cost_prior(
        &self,
        symbol: &str,
        config: &ScannerConfig,
    ) -> Option<OpportunityCostPrior> {
        let account_manager = self.account_manager.as_ref()?;
        let source = if account_manager.fee_rate_count() == 0 {
            "account_manager_default_taker_fee"
        } else {
            "account_manager_taker_fee"
        };
        // Scanner admission does not know the final strategy TIF; taker is the
        // conservative fee prior and prevents cost underestimation.
        Some(OpportunityCostPrior {
            one_way_fee_bps: account_manager.taker_fee(symbol) * 10_000.0,
            slippage_buffer_bps: config.opportunity.slippage_buffer_bps,
            source,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_runner(
        account_manager: Option<Arc<crate::account_manager::AccountManager>>,
    ) -> ScannerRunner {
        let (ws_tx, _ws_rx) = mpsc::unbounded_channel();
        let (cmd_tx, _cmd_rx) = mpsc::unbounded_channel();
        ScannerRunner {
            registry: Arc::new(SymbolRegistry::new(vec![], vec![])),
            market_client: Arc::new(MarketDataClient::new(Arc::new(
                crate::bybit_rest_client::BybitRestClient::new(
                    crate::bybit_rest_client::BybitEnvironment::Demo,
                    None,
                    None,
                )
                .expect("demo client"),
            ))),
            edge_estimates: Arc::new(parking_lot::RwLock::new(EdgeEstimates::empty())),
            scanner_config: Arc::new(crate::config::ConfigStore::new(ScannerConfig::default())),
            account_manager,
            strategy_policy_stores: ScannerStrategyPolicyStores::new(
                Arc::new(crate::config::ConfigStore::new(
                    crate::config::RiskConfig::default(),
                )),
                Arc::new(crate::config::ConfigStore::new(
                    crate::config::RiskConfig::default(),
                )),
                Arc::new(crate::config::ConfigStore::new(
                    crate::config::RiskConfig::default(),
                )),
            ),
            ws_tx,
            pipeline_cmd_tx: cmd_tx,
            trading_tx: None,
            cancel: CancellationToken::new(),
        }
    }

    /// EN: topics_for_symbol generates market, ticker, and BBO topics for each symbol.
    /// 中文: topics_for_symbol 為每個交易對生成行情、ticker 與 BBO 主題。
    #[test]
    fn test_topics_for_symbol_standard() {
        let topics = topics_for_symbol("BTCUSDT");
        assert_eq!(topics.len(), 4);
        assert_eq!(topics[0], "kline.1.BTCUSDT");
        assert_eq!(topics[1], "publicTrade.BTCUSDT");
        assert_eq!(topics[2], "tickers.BTCUSDT");
        assert_eq!(topics[3], "orderbook.50.BTCUSDT");
    }

    /// EN: topics_for_symbol with different symbols produces unique topics.
    /// 中文: 不同交易對產生唯一主題。
    #[test]
    fn test_topics_for_symbol_uniqueness() {
        let btc = topics_for_symbol("BTCUSDT");
        let eth = topics_for_symbol("ETHUSDT");
        // No overlap between different symbols
        for t in &btc {
            assert!(!eth.contains(t));
        }
    }

    /// EN: query_open_positions returns empty set when channel is closed.
    /// 中文: 通道關閉時 query_open_positions 返回空集合。
    #[tokio::test]
    async fn test_query_open_positions_channel_closed() {
        let (cmd_tx, cmd_rx) = mpsc::unbounded_channel();
        drop(cmd_rx); // receiver dropped → send will fail
        let mut runner = make_test_runner(None);
        runner.pipeline_cmd_tx = cmd_tx;
        let result = runner.query_open_positions().await;
        assert!(result.is_empty());
    }

    #[test]
    fn test_opportunity_cost_prior_uses_account_manager_default_at_cold_boot() {
        let runner = make_test_runner(Some(
            Arc::new(crate::account_manager::AccountManager::new()),
        ));
        let prior = runner
            .opportunity_cost_prior("BTCUSDT", &ScannerConfig::default())
            .expect("account manager prior");
        assert_eq!(prior.source, "account_manager_default_taker_fee");
        assert!((prior.one_way_fee_bps - 5.5).abs() < 1e-9);
    }
}
