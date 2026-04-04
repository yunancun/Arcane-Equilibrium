//! Bybit V5 position manager — position queries and configuration (R-05 exchange infra).
//! Bybit V5 持倉管理器 — 持倉查詢與配置。
//!
//! MODULE_NOTE (EN): Manages positions on Bybit V5: query open positions, set leverage,
//!   configure trading stops (TP/SL/trailing), switch position mode, and fetch closed PnL.
//!   All methods are async and use Arc<BybitRestClient> for thread-safe sharing.
//! MODULE_NOTE (中): 管理 Bybit V5 上的持倉：查詢開放持倉、設置槓桿、配置交易止損
//!   （止盈/止損/追蹤止損）、切換持倉模式、獲取已平倉盈虧。
//!   所有方法為異步，使用 Arc<BybitRestClient> 線程安全共享。

use crate::bybit_rest_client::{BybitRestClient, BybitResult};
use crate::order_manager::OrderCategory;
use std::sync::Arc;
use tracing::{debug, info};

// ---------------------------------------------------------------------------
// Position structs / 持倉結構
// ---------------------------------------------------------------------------

/// Detailed position information from Bybit V5.
/// Bybit V5 的詳細持倉信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PositionInfo {
    /// Trading pair, e.g. "BTCUSDT" / 交易對
    pub symbol: String,
    /// Side: "Buy" (long) | "Sell" (short) | "None" (no position)
    /// 方向："Buy"（多）| "Sell"（空）| "None"（無持倉）
    pub side: String,
    /// Position size (absolute qty) / 持倉數量（絕對值）
    pub size: f64,
    /// Average entry price / 平均入場價
    pub avg_price: f64,
    /// Current mark price / 當前標記價
    pub mark_price: f64,
    /// Unrealised PnL / 未實現盈虧
    pub unrealised_pnl: f64,
    /// Current leverage / 當前槓桿
    pub leverage: f64,
    /// Liquidation price (0 = not applicable) / 清算價（0 = 不適用）
    pub liq_price: f64,
    /// Take profit price (0 = not set) / 止盈價（0 = 未設置）
    pub take_profit: f64,
    /// Stop loss price (0 = not set) / 止損價（0 = 未設置）
    pub stop_loss: f64,
    /// Position index: 0=one-way, 1=buy-side hedge, 2=sell-side hedge
    /// 持倉索引：0=單向，1=買側對沖，2=賣側對沖
    pub position_idx: i32,
    /// Trailing stop distance (0 = not set) / 追蹤止損距離（0 = 未設置）
    pub trailing_stop: f64,
    /// Position value (size * avgPrice) / 持倉價值
    pub position_value: f64,
    /// Cumulative realised PnL / 累計已實現盈虧
    pub cum_realised_pnl: f64,
    /// Creation timestamp / 創建時間戳
    pub created_time: String,
    /// Last update timestamp / 最後更新時間戳
    pub updated_time: String,
}

/// Request to set trading stops (TP/SL/trailing) on a position.
/// 設置持倉交易止損（止盈/止損/追蹤止損）的請求。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TradingStopRequest {
    /// Product category / 產品品類
    pub category: OrderCategory,
    /// Trading pair / 交易對
    pub symbol: String,
    /// Take profit price / 止盈價
    pub take_profit: Option<f64>,
    /// Stop loss price / 止損價
    pub stop_loss: Option<f64>,
    /// TP trigger by: "LastPrice" | "MarkPrice" / 止盈觸發依據
    pub tp_trigger_by: Option<String>,
    /// SL trigger by: "LastPrice" | "MarkPrice" / 止損觸發依據
    pub sl_trigger_by: Option<String>,
    /// Trailing stop distance in price / 追蹤止損價格距離
    pub trailing_stop: Option<f64>,
    /// Active price for trailing stop (activation threshold)
    /// 追蹤止損的激活價格（激活閾值）
    pub active_price: Option<f64>,
    /// Position index: 0=one-way, 1=buy-side, 2=sell-side
    /// 持倉索引：0=單向，1=買側，2=賣側
    pub position_idx: Option<i32>,
}

/// Closed PnL record for a completed trade.
/// 已平倉交易的盈虧記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ClosedPnlInfo {
    /// Trading pair / 交易對
    pub symbol: String,
    /// Order ID that closed the position / 平倉訂單 ID
    pub order_id: String,
    /// Side of the closing trade / 平倉方向
    pub side: String,
    /// Closed quantity / 平倉數量
    pub qty: f64,
    /// Average entry price / 平均入場價
    pub avg_entry_price: f64,
    /// Average exit price / 平均出場價
    pub avg_exit_price: f64,
    /// Closed PnL (realized) / 已平倉盈虧（已實現）
    pub closed_pnl: f64,
    /// Cumulative entry value / 累計入場價值
    pub cum_entry_value: f64,
    /// Cumulative exit value / 累計出場價值
    pub cum_exit_value: f64,
    /// Total trading fee / 總交易手續費
    pub fill_count: i32,
    /// Leverage at time of trade / 交易時的槓桿
    pub leverage: f64,
    /// Creation timestamp / 創建時間戳
    pub created_time: String,
    /// Last update timestamp / 最後更新時間戳
    pub updated_time: String,
}

// ---------------------------------------------------------------------------
// PositionManager / 持倉管理器
// ---------------------------------------------------------------------------

/// Manages position queries and configuration on Bybit V5.
/// 管理 Bybit V5 上的持倉查詢與配置。
///
/// Thread-safe: uses Arc<BybitRestClient>.
/// 線程安全：使用 Arc<BybitRestClient>。
pub struct PositionManager {
    /// Shared REST client / 共享 REST 客戶端
    client: Arc<BybitRestClient>,
}

impl PositionManager {
    /// Create a new PositionManager.
    /// 創建新的持倉管理器。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Get positions / 查詢持倉
    // -----------------------------------------------------------------------

    /// Get all positions for a category, optionally filtered by symbol.
    /// 查詢某品類的所有持倉，可選按交易對過濾。
    ///
    /// GET /v5/position/list
    pub async fn get_positions(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
    ) -> BybitResult<Vec<PositionInfo>> {
        let mut params: Vec<(&str, &str)> = vec![("category", category.as_str())];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }

        let resp = self
            .client
            .get_checked("/v5/position/list", &params)
            .await?;
        parse_position_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Set leverage / 設置槓桿
    // -----------------------------------------------------------------------

    /// Set leverage for a symbol (buy and sell sides).
    /// 設置交易對的槓桿（買賣兩側）。
    ///
    /// POST /v5/position/set-leverage
    ///
    /// Note: Bybit returns retCode 110043 if leverage is already set to the
    /// requested value. This is NOT treated as an error (idempotent).
    /// 注意：如果槓桿已經設置為請求值，Bybit 返回 retCode 110043。
    /// 這不被視為錯誤（冪等）。
    pub async fn set_leverage(
        &self,
        category: OrderCategory,
        symbol: &str,
        buy_leverage: f64,
        sell_leverage: f64,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "buyLeverage": format!("{}", buy_leverage),
            "sellLeverage": format!("{}", sell_leverage),
        });

        info!(
            symbol = symbol,
            buy_leverage = buy_leverage,
            sell_leverage = sell_leverage,
            "setting leverage / 設置槓桿"
        );

        let resp = self
            .client
            .post("/v5/position/set-leverage", &body)
            .await?;

        // 110043 = leverage not modified (already set) — treat as success
        // 110043 = 槓桿未修改（已設置）— 視為成功
        if resp.ret_code == 0 || resp.ret_code == 110043 {
            Ok(())
        } else {
            Err(crate::bybit_rest_client::BybitApiError::Business {
                ret_code: resp.ret_code,
                ret_msg: resp.ret_msg.clone(),
                response: serde_json::to_value(&resp).unwrap_or_default(),
            })
        }
    }

    // -----------------------------------------------------------------------
    // Set trading stop / 設置交易止損
    // -----------------------------------------------------------------------

    /// Set trading stop (TP/SL/trailing stop) on a position.
    /// 在持倉上設置交易止損（止盈/止損/追蹤止損）。
    ///
    /// POST /v5/position/set-trading-stop
    pub async fn set_trading_stop(&self, req: TradingStopRequest) -> BybitResult<()> {
        let mut body = serde_json::json!({
            "category": req.category.as_str(),
            "symbol": req.symbol,
        });

        if let Some(tp) = req.take_profit {
            body["takeProfit"] = serde_json::Value::String(format!("{}", tp));
        }
        if let Some(sl) = req.stop_loss {
            body["stopLoss"] = serde_json::Value::String(format!("{}", sl));
        }
        if let Some(ref tptb) = req.tp_trigger_by {
            body["tpTriggerBy"] = serde_json::Value::String(tptb.clone());
        }
        if let Some(ref sltb) = req.sl_trigger_by {
            body["slTriggerBy"] = serde_json::Value::String(sltb.clone());
        }
        if let Some(ts) = req.trailing_stop {
            body["trailingStop"] = serde_json::Value::String(format!("{}", ts));
        }
        if let Some(ap) = req.active_price {
            body["activePrice"] = serde_json::Value::String(format!("{}", ap));
        }
        if let Some(idx) = req.position_idx {
            body["positionIdx"] = serde_json::Value::Number(serde_json::Number::from(idx));
        }

        debug!(
            symbol = req.symbol.as_str(),
            "setting trading stop / 設置交易止損"
        );

        self.client
            .post_checked("/v5/position/set-trading-stop", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Switch position mode / 切換持倉模式
    // -----------------------------------------------------------------------

    /// Switch position mode between one-way and hedge mode.
    /// 切換單向模式和對沖模式。
    ///
    /// POST /v5/position/switch-mode
    ///
    /// mode: 0 = merged single (one-way), 3 = both-side (hedge)
    /// mode: 0 = 合併單向, 3 = 雙向（對沖）
    pub async fn switch_position_mode(
        &self,
        category: OrderCategory,
        symbol: &str,
        mode: i32,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "mode": mode,
        });

        info!(
            symbol = symbol,
            mode = mode,
            "switching position mode / 切換持倉模式"
        );

        self.client
            .post_checked("/v5/position/switch-mode", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Switch margin mode / 切換保證金模式
    // -----------------------------------------------------------------------

    /// Switch between isolated and cross margin for a symbol.
    /// 切換指定交易對的逐倉/全倉保證金模式。
    ///
    /// POST /v5/position/switch-isolated
    ///
    /// trade_mode: 0 = cross margin, 1 = isolated margin
    /// trade_mode: 0 = 全倉, 1 = 逐倉
    pub async fn switch_isolated(
        &self,
        category: OrderCategory,
        symbol: &str,
        trade_mode: i32,
        buy_leverage: f64,
        sell_leverage: f64,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "tradeMode": trade_mode,
            "buyLeverage": format!("{}", buy_leverage),
            "sellLeverage": format!("{}", sell_leverage),
        });

        info!(
            symbol = symbol,
            trade_mode = trade_mode,
            "switching margin mode / 切換保證金模式"
        );

        self.client
            .post_checked("/v5/position/switch-isolated", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Set TP/SL mode / 設置止盈止損模式
    // -----------------------------------------------------------------------

    /// Set TP/SL mode: full position or partial.
    /// 設置止盈止損模式：全倉或部分。
    ///
    /// POST /v5/position/set-tpsl-mode
    ///
    /// tp_sl_mode: "Full" = full position, "Partial" = partial position
    /// tp_sl_mode: "Full" = 全倉, "Partial" = 部分倉位
    pub async fn set_tpsl_mode(
        &self,
        category: OrderCategory,
        symbol: &str,
        tp_sl_mode: &str,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "tpSlMode": tp_sl_mode,
        });

        info!(
            symbol = symbol,
            mode = tp_sl_mode,
            "setting TP/SL mode / 設置止盈止損模式"
        );

        self.client
            .post_checked("/v5/position/set-tpsl-mode", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Set risk limit / 設置風險限額
    // -----------------------------------------------------------------------

    /// Set risk limit tier for a symbol.
    /// 設置交易對的風險限額層級。
    ///
    /// POST /v5/position/set-risk-limit
    pub async fn set_risk_limit(
        &self,
        category: OrderCategory,
        symbol: &str,
        risk_id: u32,
        position_idx: Option<i32>,
    ) -> BybitResult<()> {
        let mut body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "riskId": risk_id,
        });

        if let Some(idx) = position_idx {
            body["positionIdx"] = serde_json::Value::Number(serde_json::Number::from(idx));
        }

        info!(
            symbol = symbol,
            risk_id = risk_id,
            "setting risk limit / 設置風險限額"
        );

        self.client
            .post_checked("/v5/position/set-risk-limit", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Auto-add margin / 自動追加保證金
    // -----------------------------------------------------------------------

    /// Toggle auto-add margin for a position.
    /// 切換持倉自動追加保證金。
    ///
    /// POST /v5/position/set-auto-add-margin
    ///
    /// auto_add_margin: 0 = off, 1 = on
    /// auto_add_margin: 0 = 關閉, 1 = 開啟
    pub async fn set_auto_add_margin(
        &self,
        category: OrderCategory,
        symbol: &str,
        auto_add_margin: i32,
        position_idx: Option<i32>,
    ) -> BybitResult<()> {
        let mut body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "autoAddMargin": auto_add_margin,
        });

        if let Some(idx) = position_idx {
            body["positionIdx"] = serde_json::Value::Number(serde_json::Number::from(idx));
        }

        info!(
            symbol = symbol,
            auto_add = auto_add_margin,
            "setting auto-add margin / 設置自動追加保證金"
        );

        self.client
            .post_checked("/v5/position/set-auto-add-margin", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Add margin / 手動追加保證金
    // -----------------------------------------------------------------------

    /// Manually add margin to a position.
    /// 手動追加保證金到持倉。
    ///
    /// POST /v5/position/add-margin
    pub async fn add_margin(
        &self,
        category: OrderCategory,
        symbol: &str,
        margin: f64,
        position_idx: Option<i32>,
    ) -> BybitResult<()> {
        let mut body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "margin": format!("{}", margin),
        });

        if let Some(idx) = position_idx {
            body["positionIdx"] = serde_json::Value::Number(serde_json::Number::from(idx));
        }

        info!(
            symbol = symbol,
            margin = margin,
            "adding margin / 追加保證金"
        );

        self.client
            .post_checked("/v5/position/add-margin", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Closed PnL / 已平倉盈虧
    // -----------------------------------------------------------------------

    /// Get closed PnL records.
    /// 查詢已平倉盈虧記錄。
    ///
    /// GET /v5/position/closed-pnl
    pub async fn get_closed_pnl(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<ClosedPnlInfo>> {
        let limit_str = limit.unwrap_or(50).to_string();
        let mut params: Vec<(&str, &str)> = vec![
            ("category", category.as_str()),
            ("limit", &limit_str),
        ];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }

        let resp = self
            .client
            .get_checked("/v5/position/closed-pnl", &params)
            .await?;
        parse_closed_pnl_list(&resp.result)
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse a list of PositionInfo from Bybit position query result.
/// 從 Bybit 持倉查詢結果解析 PositionInfo 列表。
fn parse_position_list(result: &serde_json::Value) -> BybitResult<Vec<PositionInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut positions = Vec::with_capacity(list.len());
    for item in &list {
        positions.push(parse_position_item(item));
    }
    Ok(positions)
}

/// Parse a single PositionInfo item from Bybit response.
/// 從 Bybit 回應解析單個 PositionInfo 項目。
///
/// Bybit V5 position fields:
///   symbol, side, size, avgPrice, markPrice, unrealisedPnl, leverage,
///   liqPrice, takeProfit, stopLoss, positionIdx, trailingStop,
///   positionValue, cumRealisedPnl, createdTime, updatedTime
fn parse_position_item(item: &serde_json::Value) -> PositionInfo {
    PositionInfo {
        symbol: str_field(item, "symbol"),
        side: str_field(item, "side"),
        size: f64_field(item, "size"),
        avg_price: f64_field(item, "avgPrice"),
        mark_price: f64_field(item, "markPrice"),
        unrealised_pnl: f64_field(item, "unrealisedPnl"),
        leverage: f64_field(item, "leverage"),
        liq_price: f64_field(item, "liqPrice"),
        take_profit: f64_field(item, "takeProfit"),
        stop_loss: f64_field(item, "stopLoss"),
        position_idx: int_field(item, "positionIdx"),
        trailing_stop: f64_field(item, "trailingStop"),
        position_value: f64_field(item, "positionValue"),
        cum_realised_pnl: f64_field(item, "cumRealisedPnl"),
        created_time: str_field(item, "createdTime"),
        updated_time: str_field(item, "updatedTime"),
    }
}

/// Parse a list of ClosedPnlInfo from Bybit closed PnL query result.
/// 從 Bybit 已平倉盈虧查詢結果解析 ClosedPnlInfo 列表。
fn parse_closed_pnl_list(result: &serde_json::Value) -> BybitResult<Vec<ClosedPnlInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut pnls = Vec::with_capacity(list.len());
    for item in &list {
        pnls.push(parse_closed_pnl_item(item));
    }
    Ok(pnls)
}

/// Parse a single ClosedPnlInfo item.
/// 解析單個 ClosedPnlInfo 項目。
fn parse_closed_pnl_item(item: &serde_json::Value) -> ClosedPnlInfo {
    ClosedPnlInfo {
        symbol: str_field(item, "symbol"),
        order_id: str_field(item, "orderId"),
        side: str_field(item, "side"),
        qty: f64_field(item, "qty"),
        avg_entry_price: f64_field(item, "avgEntryPrice"),
        avg_exit_price: f64_field(item, "avgExitPrice"),
        closed_pnl: f64_field(item, "closedPnl"),
        cum_entry_value: f64_field(item, "cumEntryValue"),
        cum_exit_value: f64_field(item, "cumExitValue"),
        fill_count: int_field(item, "fillCount"),
        leverage: f64_field(item, "leverage"),
        created_time: str_field(item, "createdTime"),
        updated_time: str_field(item, "updatedTime"),
    }
}

// ---------------------------------------------------------------------------
// Field extraction helpers / 欄位提取輔助函數
// ---------------------------------------------------------------------------

/// Extract a string field from JSON, defaulting to "" / 提取字串欄位，默認 ""
fn str_field(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// Extract a numeric-string field as f64, defaulting to 0.0 / 提取數字字串欄位為 f64，默認 0.0
fn f64_field(obj: &serde_json::Value, field: &str) -> f64 {
    obj.get(field)
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0)
}

/// Extract an integer field (string or number), defaulting to 0 / 提取整數欄位，默認 0
fn int_field(obj: &serde_json::Value, field: &str) -> i32 {
    obj.get(field)
        .and_then(|v| {
            v.as_i64()
                .map(|n| n as i32)
                .or_else(|| v.as_str().and_then(|s| s.parse::<i32>().ok()))
        })
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -- Position parsing tests / 持倉解析測試 --

    #[test]
    fn test_parse_position_item() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.01",
            "avgPrice": "65000.0",
            "markPrice": "65500.0",
            "unrealisedPnl": "5.0",
            "leverage": "10",
            "liqPrice": "58000.0",
            "takeProfit": "70000.0",
            "stopLoss": "60000.0",
            "positionIdx": 0,
            "trailingStop": "500.0",
            "positionValue": "650.0",
            "cumRealisedPnl": "120.5",
            "createdTime": "1700000000000",
            "updatedTime": "1700000001000"
        });

        let pos = parse_position_item(&item);
        assert_eq!(pos.symbol, "BTCUSDT");
        assert_eq!(pos.side, "Buy");
        assert!((pos.size - 0.01).abs() < 1e-10);
        assert!((pos.avg_price - 65000.0).abs() < 1e-10);
        assert!((pos.mark_price - 65500.0).abs() < 1e-10);
        assert!((pos.unrealised_pnl - 5.0).abs() < 1e-10);
        assert!((pos.leverage - 10.0).abs() < 1e-10);
        assert!((pos.liq_price - 58000.0).abs() < 1e-10);
        assert!((pos.take_profit - 70000.0).abs() < 1e-10);
        assert!((pos.stop_loss - 60000.0).abs() < 1e-10);
        assert_eq!(pos.position_idx, 0);
        assert!((pos.trailing_stop - 500.0).abs() < 1e-10);
        assert!((pos.position_value - 650.0).abs() < 1e-10);
        assert!((pos.cum_realised_pnl - 120.5).abs() < 1e-10);
    }

    #[test]
    fn test_parse_position_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.01",
                    "avgPrice": "65000.0",
                    "markPrice": "65500.0",
                    "unrealisedPnl": "5.0",
                    "leverage": "10",
                    "liqPrice": "58000.0",
                    "takeProfit": "0",
                    "stopLoss": "0",
                    "positionIdx": 0,
                    "trailingStop": "0",
                    "positionValue": "650.0",
                    "cumRealisedPnl": "0",
                    "createdTime": "1700000000000",
                    "updatedTime": "1700000001000"
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "size": "1.5",
                    "avgPrice": "3500.0",
                    "markPrice": "3480.0",
                    "unrealisedPnl": "30.0",
                    "leverage": "5",
                    "liqPrice": "4200.0",
                    "takeProfit": "3200.0",
                    "stopLoss": "3800.0",
                    "positionIdx": 0,
                    "trailingStop": "0",
                    "positionValue": "5250.0",
                    "cumRealisedPnl": "50.0",
                    "createdTime": "1700000000000",
                    "updatedTime": "1700000001000"
                }
            ]
        });

        let positions = parse_position_list(&result).unwrap();
        assert_eq!(positions.len(), 2);
        assert_eq!(positions[0].symbol, "BTCUSDT");
        assert_eq!(positions[0].side, "Buy");
        assert_eq!(positions[1].symbol, "ETHUSDT");
        assert_eq!(positions[1].side, "Sell");
        assert!((positions[1].size - 1.5).abs() < 1e-10);
    }

    #[test]
    fn test_parse_position_list_empty() {
        let result = serde_json::json!({"list": []});
        let positions = parse_position_list(&result).unwrap();
        assert_eq!(positions.len(), 0);

        // Missing "list" key / 缺少 "list" 鍵
        let result = serde_json::json!({});
        let positions = parse_position_list(&result).unwrap();
        assert_eq!(positions.len(), 0);
    }

    // -- Closed PnL parsing tests / 已平倉盈虧解析測試 --

    #[test]
    fn test_parse_closed_pnl_item() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "orderId": "ord-close-001",
            "side": "Sell",
            "qty": "0.01",
            "avgEntryPrice": "65000.0",
            "avgExitPrice": "66000.0",
            "closedPnl": "10.0",
            "cumEntryValue": "650.0",
            "cumExitValue": "660.0",
            "fillCount": 2,
            "leverage": "10",
            "createdTime": "1700000000000",
            "updatedTime": "1700000001000"
        });

        let pnl = parse_closed_pnl_item(&item);
        assert_eq!(pnl.symbol, "BTCUSDT");
        assert_eq!(pnl.order_id, "ord-close-001");
        assert!((pnl.qty - 0.01).abs() < 1e-10);
        assert!((pnl.avg_entry_price - 65000.0).abs() < 1e-10);
        assert!((pnl.avg_exit_price - 66000.0).abs() < 1e-10);
        assert!((pnl.closed_pnl - 10.0).abs() < 1e-10);
        assert_eq!(pnl.fill_count, 2);
        assert!((pnl.leverage - 10.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_closed_pnl_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "orderId": "o1",
                    "side": "Sell",
                    "qty": "0.01",
                    "avgEntryPrice": "65000.0",
                    "avgExitPrice": "66000.0",
                    "closedPnl": "10.0",
                    "cumEntryValue": "650.0",
                    "cumExitValue": "660.0",
                    "fillCount": 1,
                    "leverage": "10",
                    "createdTime": "1700000000000",
                    "updatedTime": "1700000001000"
                }
            ]
        });
        let pnls = parse_closed_pnl_list(&result).unwrap();
        assert_eq!(pnls.len(), 1);
        assert_eq!(pnls[0].symbol, "BTCUSDT");
    }

    #[test]
    fn test_parse_closed_pnl_empty() {
        let result = serde_json::json!({"list": []});
        assert_eq!(parse_closed_pnl_list(&result).unwrap().len(), 0);
    }

    // -- Field helper tests / 欄位輔助函數測試 --

    #[test]
    fn test_str_field() {
        let obj = serde_json::json!({"a": "hello", "b": 123});
        assert_eq!(str_field(&obj, "a"), "hello");
        assert_eq!(str_field(&obj, "b"), "");
        assert_eq!(str_field(&obj, "missing"), "");
    }

    #[test]
    fn test_f64_field() {
        let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999});
        assert!((f64_field(&obj, "a") - 123.45).abs() < 1e-10);
        assert!((f64_field(&obj, "b") - 0.0).abs() < 1e-10);
        assert!((f64_field(&obj, "missing") - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_int_field() {
        // Integer value / 整數值
        let obj = serde_json::json!({"a": 42, "b": "7", "c": "bad"});
        assert_eq!(int_field(&obj, "a"), 42);
        // String integer / 字串整數
        assert_eq!(int_field(&obj, "b"), 7);
        // Bad value / 無效值
        assert_eq!(int_field(&obj, "c"), 0);
        // Missing / 缺失
        assert_eq!(int_field(&obj, "missing"), 0);
    }

    // -- Serde round-trip tests / 序列化往返測試 --

    #[test]
    fn test_position_info_serde_roundtrip() {
        let pos = PositionInfo {
            symbol: "BTCUSDT".to_string(),
            side: "Buy".to_string(),
            size: 0.01,
            avg_price: 65000.0,
            mark_price: 65500.0,
            unrealised_pnl: 5.0,
            leverage: 10.0,
            liq_price: 58000.0,
            take_profit: 70000.0,
            stop_loss: 60000.0,
            position_idx: 0,
            trailing_stop: 0.0,
            position_value: 650.0,
            cum_realised_pnl: 120.5,
            created_time: "1700000000000".to_string(),
            updated_time: "1700000001000".to_string(),
        };
        let json = serde_json::to_string(&pos).unwrap();
        let deser: PositionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert!((deser.avg_price - 65000.0).abs() < 1e-10);
        assert_eq!(deser.position_idx, 0);
    }

    #[test]
    fn test_closed_pnl_serde_roundtrip() {
        let pnl = ClosedPnlInfo {
            symbol: "ETHUSDT".to_string(),
            order_id: "o1".to_string(),
            side: "Buy".to_string(),
            qty: 1.0,
            avg_entry_price: 3500.0,
            avg_exit_price: 3600.0,
            closed_pnl: 100.0,
            cum_entry_value: 3500.0,
            cum_exit_value: 3600.0,
            fill_count: 3,
            leverage: 5.0,
            created_time: "1700000000000".to_string(),
            updated_time: "1700000001000".to_string(),
        };
        let json = serde_json::to_string(&pnl).unwrap();
        let deser: ClosedPnlInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "ETHUSDT");
        assert!((deser.closed_pnl - 100.0).abs() < 1e-10);
        assert_eq!(deser.fill_count, 3);
    }

    #[test]
    fn test_trading_stop_request_serde() {
        let req = TradingStopRequest {
            category: OrderCategory::Linear,
            symbol: "BTCUSDT".to_string(),
            take_profit: Some(70000.0),
            stop_loss: Some(60000.0),
            tp_trigger_by: Some("MarkPrice".to_string()),
            sl_trigger_by: Some("LastPrice".to_string()),
            trailing_stop: Some(500.0),
            active_price: Some(66000.0),
            position_idx: Some(0),
        };
        let json = serde_json::to_string(&req).unwrap();
        let deser: TradingStopRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert!((deser.take_profit.unwrap() - 70000.0).abs() < 1e-10);
        assert_eq!(deser.position_idx, Some(0));
    }
}
