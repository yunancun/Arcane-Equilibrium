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
use crate::instrument_info::{normalize_trading_stop_price, InstrumentInfoCache};
use crate::order_manager::OrderCategory;
use std::sync::Arc;
use tracing::{debug, info, warn};

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
    /// P1-06（cold audit pkg B）：持倉方向，供 SL 保守取整方向判定。
    /// Some(true)=多頭 SL floor / Some(false)=空頭 SL ceil / None=回退最近 round。
    /// TP/trailing/active 不依方向（永遠最近 round）。
    pub side_is_long: Option<bool>,
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
    /// P1-06（cold audit pkg B）：共享 instrument cache，供 trading-stop 價格 tick 取整。
    /// 與 OrderManager 共用同一引擎 cache（bootstrap 注入），無 spec 時 fail-closed。
    instruments: Arc<InstrumentInfoCache>,
}

impl PositionManager {
    /// Create a new PositionManager.
    /// 創建新的持倉管理器。
    pub fn new(client: Arc<BybitRestClient>, instruments: Arc<InstrumentInfoCache>) -> Self {
        Self {
            client,
            instruments,
        }
    }

    // -----------------------------------------------------------------------
    // Get positions / 查詢持倉
    // -----------------------------------------------------------------------

    /// Bybit linear `/v5/position/list` 單頁筆數上限（Bybit 預設 20，最大 200）。
    /// 全量 baseline 掃描固定取 200，以最少 REST 往返抓齊全量。
    const FULL_SCAN_PAGE_LIMIT: &'static str = "200";
    /// 全量分頁迴圈頁數硬上限（防無限迴圈）。200 筆/頁 × 50 頁 = 10000 倉，遠超實際
    /// 帳戶規模；觸頂代表交易所異常分頁或 cursor 邏輯失常，須 fail-closed 拋錯而非
    /// 靜默截斷（截斷本身就是 baseline 盲區，正是本票 P2-RECONCILER-GET-POSITIONS-
    /// PAGINATION 要修的問題）。
    const FULL_SCAN_MAX_PAGES: u32 = 50;

    /// Get all positions for a category, optionally filtered by symbol.
    /// 查詢某品類的所有持倉，可選按交易對過濾。
    ///
    /// GET /v5/position/list
    ///
    /// 為什麼全量路徑要分頁（P2-RECONCILER-GET-POSITIONS-PAGINATION 修法 B）：
    /// Bybit linear 全量查詢預設單頁僅 20 筆，持倉 > 20 時 page2+ 會被漏報，導致
    /// reconciler 把第 2 頁的真實持倉看不見 → Orphan 誤判 + baseline 完整性盲區。
    /// 全量（symbol=None）路徑顯式 limit=200 並用 nextPageCursor 迴圈抓齊全頁。
    /// single-symbol point-query（symbol=Some，S-6 D2 收斂 gate 用）只回單筆、無
    /// 分頁，維持原單次取數行為不動。
    pub async fn get_positions(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
    ) -> BybitResult<Vec<PositionInfo>> {
        // single-symbol point-query 路徑：Bybit 回單筆、無分頁，保持原單次取數行為。
        // S-6 D2 收斂 gate 依賴此路徑，勿動。
        if let Some(sym) = symbol {
            let params: Vec<(&str, &str)> = vec![("category", category.as_str()), ("symbol", sym)];
            let resp = self
                .client
                .get_checked("/v5/position/list", &params)
                .await?;
            // point-query 忽略 cursor（只回單 symbol，無第二頁）
            let (positions, _cursor) = parse_position_list_with_cursor(&resp.result)?;
            return Ok(positions);
        }

        // 全量 baseline 路徑：顯式 limit=200 + nextPageCursor 分頁迴圈抓齊全頁。
        // Bybit 列出所有倉位時要求 symbol 或 settleCoin 二擇一；linear 永遠以 USDT 結算。
        let mut all_positions: Vec<PositionInfo> = Vec::new();
        let mut cursor: Option<String> = None;

        for page in 1..=Self::FULL_SCAN_MAX_PAGES {
            let mut params: Vec<(&str, &str)> = vec![
                ("category", category.as_str()),
                ("settleCoin", "USDT"),
                ("limit", Self::FULL_SCAN_PAGE_LIMIT),
            ];
            if let Some(ref cur) = cursor {
                params.push(("cursor", cur.as_str()));
            }

            // 非 0 retCode / timeout 由 get_checked fail-closed 上拋；不可當「無持倉」吞。
            let resp = self
                .client
                .get_checked("/v5/position/list", &params)
                .await?;
            let (positions, next_cursor) = parse_position_list_with_cursor(&resp.result)?;
            all_positions.extend(positions);

            // cursor 為 None（空字串已正規化）→ 無更多頁，正常結束。
            let Some(next) = next_cursor else {
                debug!(
                    page = page,
                    total = all_positions.len(),
                    "get_positions full-scan pagination complete / 全量分頁完成"
                );
                return Ok(all_positions);
            };

            // 防無限迴圈：cursor 與上一頁相同代表交易所分頁異常，fail-closed 拋錯
            // 而非靜默截斷。
            validate_full_scan_cursor_advanced(cursor.as_deref(), &next, page)?;
            cursor = Some(next);
        }

        // 觸及頁數上限仍有 cursor：異常分頁，fail-closed 不可靜默截斷。
        Err(crate::bybit_rest_client::BybitApiError::Other(format!(
            "get_positions full-scan exceeded {} page cap with cursor remaining (fail-closed: \
             prevents infinite loop + baseline truncation blindspot) / 全量分頁超頁數上限仍未取盡",
            Self::FULL_SCAN_MAX_PAGES
        )))
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

        let resp = self.client.post("/v5/position/set-leverage", &body).await?;

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
    /// POST /v5/position/trading-stop
    pub async fn set_trading_stop(&self, req: TradingStopRequest) -> BybitResult<()> {
        let mut body = serde_json::json!({
            "category": req.category.as_str(),
            "symbol": req.symbol,
        });

        // P1-06（cold audit pkg B）：每個價格欄位先經 normalize_trading_stop_price 做
        // 方向保守的 tick 取整；spec 缺失（None）→ 跳過該欄位的交易所止損並 warn，依賴
        // 本地 StopManager（root principle 9 雙軌），絕不送原始未取整值。
        // SL 用方向保守取整（多頭 floor / 空頭 ceil）；TP/trailing/active 用最近 round。
        if let Some(sl) = req.stop_loss {
            match normalize_trading_stop_price(
                &self.instruments,
                &req.symbol,
                sl,
                req.side_is_long,
                true,
            ) {
                Some(v) => {
                    body["stopLoss"] = serde_json::Value::String(format!("{}", v));
                }
                None => {
                    warn!(
                        symbol = req.symbol.as_str(),
                        raw_stop_loss = sl,
                        "P1-06: stop_loss tick-normalize failed (spec missing) — exchange SL skipped, local stop active \
                         / stop_loss 取整失敗（缺規格）— 跳過交易所 SL，本地止損生效"
                    );
                }
            }
        }
        if let Some(tp) = req.take_profit {
            match normalize_trading_stop_price(
                &self.instruments,
                &req.symbol,
                tp,
                req.side_is_long,
                false,
            ) {
                Some(v) => {
                    body["takeProfit"] = serde_json::Value::String(format!("{}", v));
                }
                None => {
                    warn!(
                        symbol = req.symbol.as_str(),
                        raw_take_profit = tp,
                        "P1-06: take_profit tick-normalize failed (spec missing) — exchange TP skipped \
                         / take_profit 取整失敗（缺規格）— 跳過交易所 TP"
                    );
                }
            }
        }
        if let Some(ref tptb) = req.tp_trigger_by {
            body["tpTriggerBy"] = serde_json::Value::String(tptb.clone());
        }
        if let Some(ref sltb) = req.sl_trigger_by {
            body["slTriggerBy"] = serde_json::Value::String(sltb.clone());
        }
        if let Some(ts) = req.trailing_stop {
            match normalize_trading_stop_price(
                &self.instruments,
                &req.symbol,
                ts,
                req.side_is_long,
                false,
            ) {
                Some(v) => {
                    body["trailingStop"] = serde_json::Value::String(format!("{}", v));
                }
                None => {
                    warn!(
                        symbol = req.symbol.as_str(),
                        raw_trailing_stop = ts,
                        "P1-06: trailing_stop tick-normalize failed (spec missing) — skipped \
                         / trailing_stop 取整失敗（缺規格）— 跳過"
                    );
                }
            }
        }
        if let Some(ap) = req.active_price {
            match normalize_trading_stop_price(
                &self.instruments,
                &req.symbol,
                ap,
                req.side_is_long,
                false,
            ) {
                Some(v) => {
                    body["activePrice"] = serde_json::Value::String(format!("{}", v));
                }
                None => {
                    warn!(
                        symbol = req.symbol.as_str(),
                        raw_active_price = ap,
                        "P1-06: active_price tick-normalize failed (spec missing) — skipped \
                         / active_price 取整失敗（缺規格）— 跳過"
                    );
                }
            }
        }
        if let Some(idx) = req.position_idx {
            body["positionIdx"] = serde_json::Value::Number(serde_json::Number::from(idx));
        }

        debug!(
            symbol = req.symbol.as_str(),
            "setting trading stop / 設置交易止損"
        );

        self.client
            .post_checked("/v5/position/trading-stop", &body)
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
    // Confirm pending MMR / 確認待定 MMR 變更
    // -----------------------------------------------------------------------

    /// Confirm pending MMR (Maintenance Margin Rate) change after risk limit adjustment.
    /// 風險限額調整後確認待定的 MMR（維持保證金率）變更。
    ///
    /// POST /v5/position/confirm-pending-mmr
    /// FIX-56/BB-A1: Corrected path (was confirm-mmr, missing `pending-`).
    /// FIX-56/BB-A1：修正路徑（原為 confirm-mmr，缺少 `pending-`）。
    /// Pre-wired, not on trading path. 預接線，不在交易路徑上。
    #[allow(dead_code)]
    ///
    /// Note: Replaces the deprecated /v5/position/set-risk-limit endpoint.
    /// Risk limits are now auto-adjusted; this endpoint confirms the new MMR.
    /// 注意：替代已棄用的 /v5/position/set-risk-limit 端點。
    /// 風險限額現在自動調整；此端點確認新的 MMR。
    pub async fn confirm_pending_mmr(
        &self,
        category: OrderCategory,
        symbol: &str,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
        });

        info!(
            symbol = symbol,
            "confirming pending MMR / 確認待定 MMR 變更"
        );

        // FIX-56/BB-A1: Correct path is confirm-pending-mmr (not confirm-mmr).
        // FIX-56/BB-A1：正確路徑為 confirm-pending-mmr（非 confirm-mmr）。
        self.client
            .post_checked("/v5/position/confirm-pending-mmr", &body)
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
        let mut params: Vec<(&str, &str)> =
            vec![("category", category.as_str()), ("limit", &limit_str)];
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

/// Parse a list of PositionInfo from Bybit position query result (public for PyO3 bridge).
/// 從 Bybit 持倉查詢結果解析 PositionInfo 列表（公開供 PyO3 橋接使用）。
pub fn parse_position_list_pub(result: &serde_json::Value) -> BybitResult<Vec<PositionInfo>> {
    parse_position_list(result)
}

/// Parse a list of PositionInfo from Bybit position query result.
/// 從 Bybit 持倉查詢結果解析 PositionInfo 列表。
fn parse_position_list(result: &serde_json::Value) -> BybitResult<Vec<PositionInfo>> {
    // 復用帶 cursor 的解析，丟棄 cursor（保留供 PyO3 橋接的原簽名不變）。
    let (positions, _cursor) = parse_position_list_with_cursor(result)?;
    Ok(positions)
}

/// 解析持倉列表並回傳 nextPageCursor（P2-RECONCILER-GET-POSITIONS-PAGINATION 修法 B）。
///
/// 為什麼回傳 cursor：全量 baseline 掃描須跨頁取齊，呼叫端用本函數回傳的
/// nextPageCursor 決定是否續抓下一頁。
/// 約定（迴圈終止關鍵不變式）：cursor 為空字串或缺失 → 回 None（無更多頁）；
/// 非空 → 回 Some(token)。把空字串正規化成 None，避免 Bybit 回 "" 時被誤當有效
/// cursor 而無限請求同一末頁。
fn parse_position_list_with_cursor(
    result: &serde_json::Value,
) -> BybitResult<(Vec<PositionInfo>, Option<String>)> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut positions = Vec::with_capacity(list.len());
    for item in &list {
        positions.push(parse_position_item(item));
    }

    // nextPageCursor 提取：空字串 / 缺失正規化為 None（= 無更多頁）
    let next_cursor = result
        .get("nextPageCursor")
        .and_then(|c| c.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());

    Ok((positions, next_cursor))
}

fn validate_full_scan_cursor_advanced(
    current_cursor: Option<&str>,
    next_cursor: &str,
    page: u32,
) -> BybitResult<()> {
    if current_cursor == Some(next_cursor) {
        return Err(crate::bybit_rest_client::BybitApiError::Other(format!(
            "get_positions pagination cursor did not advance at page {page} (fail-closed) \
             / 分頁 cursor 未推進，fail-closed"
        )));
    }
    Ok(())
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

    // --- P2-RECONCILER-GET-POSITIONS-PAGINATION：cursor 提取單元測試 ---

    #[test]
    fn cursor_nonempty_returned_verbatim() {
        // 非空 cursor 須原樣回傳驅動下一頁；含 %3A escape，驗證不被改寫
        // （HTTP client 端負責不 double-encode）。
        let result = serde_json::json!({
            "list": [{ "symbol": "BTCUSDT", "side": "Buy", "size": "1.0",
                       "avgPrice": "1.0", "markPrice": "1.0", "positionIdx": 0 }],
            "nextPageCursor": "page2token%3Aabc",
        });
        let (positions, cursor) = parse_position_list_with_cursor(&result).unwrap();
        assert_eq!(positions.len(), 1);
        assert_eq!(cursor.as_deref(), Some("page2token%3Aabc"));
    }

    #[test]
    fn cursor_empty_string_normalized_to_none() {
        // 空字串 cursor 必須正規化為 None（迴圈終止關鍵不變式，防無限請求末頁）。
        let result = serde_json::json!({ "list": [], "nextPageCursor": "" });
        let (_positions, cursor) = parse_position_list_with_cursor(&result).unwrap();
        assert_eq!(cursor, None);
    }

    #[test]
    fn cursor_missing_field_is_none() {
        // result 缺 nextPageCursor 欄位也視為無更多頁（None），不可 panic。
        let result = serde_json::json!({ "list": [] });
        let (_positions, cursor) = parse_position_list_with_cursor(&result).unwrap();
        assert_eq!(cursor, None);
    }

    #[test]
    fn parse_list_delegates_and_drops_cursor() {
        // 既有 parse_position_list 委派新函數但丟棄 cursor，行為對齊原語意。
        let result = serde_json::json!({
            "list": [{ "symbol": "ETHUSDT", "side": "Sell", "size": "2.5",
                       "avgPrice": "1.0", "markPrice": "1.0", "positionIdx": 0 }],
            "nextPageCursor": "ignored-cursor",
        });
        let positions = parse_position_list(&result).unwrap();
        assert_eq!(positions.len(), 1);
        assert_eq!(positions[0].symbol, "ETHUSDT");
        assert_eq!(positions[0].side, "Sell");
    }

    #[test]
    fn full_scan_cursor_guard_accepts_first_nonempty_cursor() {
        validate_full_scan_cursor_advanced(None, "page2", 1).unwrap();
    }

    #[test]
    fn full_scan_cursor_guard_fails_when_next_cursor_does_not_advance() {
        let err = validate_full_scan_cursor_advanced(Some("page2"), "page2", 2)
            .expect_err("same cursor must fail closed");
        let msg = err.to_string();
        assert!(msg.contains("cursor did not advance"));
        assert!(msg.contains("page 2"));
    }

    #[test]
    fn full_scan_cursor_guard_accepts_advanced_cursor() {
        validate_full_scan_cursor_advanced(Some("page2"), "page3", 2).unwrap();
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
            side_is_long: Some(true),
        };
        let json = serde_json::to_string(&req).unwrap();
        let deser: TradingStopRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert!((deser.take_profit.unwrap() - 70000.0).abs() < 1e-10);
        assert_eq!(deser.position_idx, Some(0));
        assert_eq!(deser.side_is_long, Some(true));
    }
}
