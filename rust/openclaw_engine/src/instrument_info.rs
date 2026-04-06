//! Bybit instrument info cache — symbol lot sizes, tick sizes, min notional (R-05).
//! Bybit 合約信息緩存 — 交易對步長、tick 精度、最小名義值。
//!
//! MODULE_NOTE (EN): Fetches GET /v5/market/instruments-info and caches symbol
//!   specifications. Provides rounding helpers for qty and price to comply with
//!   exchange precision requirements. Cache can be refreshed periodically.
//! MODULE_NOTE (中): 獲取 GET /v5/market/instruments-info 並緩存交易對規格。
//!   提供 qty 和 price 取整輔助函數以符合交易所精度要求。緩存可定期刷新。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use std::collections::HashMap;
use std::sync::RwLock;
use tracing::info;

// ---------------------------------------------------------------------------
// SymbolSpec — per-symbol trading spec / 單交易對交易規格
// ---------------------------------------------------------------------------

/// Trading specification for a single symbol.
/// 單個交易對的交易規格。
#[derive(Debug, Clone, serde::Serialize)]
pub struct SymbolSpec {
    /// Symbol name, e.g. "BTCUSDT" / 交易對名稱
    pub symbol: String,
    /// Base currency, e.g. "BTC" / 基礎貨幣
    pub base_currency: String,
    /// Quote currency, e.g. "USDT" / 計價貨幣
    pub quote_currency: String,
    /// Contract type: "LinearPerpetual", "InversePerpetual", etc.
    /// 合約類型
    pub contract_type: String,
    /// Lot size step (qty precision), e.g. 0.001 for BTC / 步長精度
    pub qty_step: f64,
    /// Minimum order quantity / 最小下單數量
    pub min_qty: f64,
    /// Maximum order quantity / 最大下單數量
    pub max_qty: f64,
    /// Tick size (price precision), e.g. 0.10 for BTCUSDT / Tick 精度
    pub tick_size: f64,
    /// Minimum price / 最小價格
    pub min_price: f64,
    /// Maximum price / 最大價格
    pub max_price: f64,
    /// Minimum notional value (qty * price), 0 if not available / 最小名義值
    pub min_notional: f64,
    /// Number of decimal places for qty (derived from qty_step) / qty 小數位數
    pub qty_decimals: u32,
    /// Number of decimal places for price (derived from tick_size) / price 小數位數
    pub price_decimals: u32,
}

impl SymbolSpec {
    /// Round quantity down to the nearest qty_step (floor).
    /// 將數量向下取整到最近的 qty_step（地板除法）。
    ///
    /// Floor is used to avoid exceeding available balance.
    /// 使用 floor 避免超過可用餘額。
    pub fn round_qty(&self, qty: f64) -> f64 {
        if self.qty_step <= 0.0 || qty <= 0.0 {
            return 0.0;
        }
        let floored = (qty / self.qty_step).floor() * self.qty_step;
        round_to_decimals(floored, self.qty_decimals)
    }

    /// Round price to the nearest tick_size.
    /// 將價格取整到最近的 tick_size。
    pub fn round_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let rounded = (price / self.tick_size).round() * self.tick_size;
        round_to_decimals(rounded, self.price_decimals)
    }

    /// Round price down (floor) — conservative for long stop-loss.
    /// 價格向下取整（floor）— 適用於多頭止損。
    pub fn floor_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let floored = (price / self.tick_size).floor() * self.tick_size;
        round_to_decimals(floored, self.price_decimals)
    }

    /// Round price up (ceil) — conservative for short stop-loss.
    /// 價格向上取整（ceil）— 適用於空頭止損。
    pub fn ceil_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let ceiled = (price / self.tick_size).ceil() * self.tick_size;
        round_to_decimals(ceiled, self.price_decimals)
    }

    /// Validate an order's qty and price against exchange limits.
    /// 驗證訂單的 qty 和 price 是否符合交易所限制。
    ///
    /// Returns (valid, reason). If valid is false, reason explains why.
    /// 返回 (valid, reason)。若 valid 為 false，reason 說明原因。
    pub fn validate_order(&self, qty: f64, price: f64) -> (bool, String) {
        if qty < self.min_qty {
            return (false, format!("qty {qty} < min_qty {}", self.min_qty));
        }
        if qty > self.max_qty {
            return (false, format!("qty {qty} > max_qty {}", self.max_qty));
        }
        if price > 0.0 {
            if price < self.min_price {
                return (
                    false,
                    format!("price {price} < min_price {}", self.min_price),
                );
            }
            if self.max_price > 0.0 && price > self.max_price {
                return (
                    false,
                    format!("price {price} > max_price {}", self.max_price),
                );
            }
            if self.min_notional > 0.0 && qty * price < self.min_notional {
                return (
                    false,
                    format!(
                        "notional {:.4} < min_notional {}",
                        qty * price,
                        self.min_notional
                    ),
                );
            }
        }
        (true, String::new())
    }
}

// ---------------------------------------------------------------------------
// InstrumentInfoCache / 合約信息緩存
// ---------------------------------------------------------------------------

/// Thread-safe instrument info cache.
/// 線程安全的合約信息緩存。
pub struct InstrumentInfoCache {
    /// Map of symbol -> SymbolSpec / 交易對 -> 規格 映射
    /// pub(crate) for test access from sibling modules / pub(crate) 供兄弟模組測試存取
    pub(crate) cache: RwLock<HashMap<String, SymbolSpec>>,
}

impl InstrumentInfoCache {
    /// Create an empty cache.
    /// 創建空緩存。
    pub fn new() -> Self {
        Self {
            cache: RwLock::new(HashMap::new()),
        }
    }

    /// Refresh cache by fetching instrument info from Bybit.
    /// 通過從 Bybit 獲取合約信息刷新緩存。
    ///
    /// Fetches both linear and spot categories in one call each.
    /// 分別獲取 linear 和 spot 品類。
    pub async fn refresh(&self, client: &BybitRestClient, category: &str) -> BybitResult<usize> {
        let resp = client
            .get("/v5/market/instruments-info", &[("category", category)])
            .await?;

        if resp.ret_code != 0 {
            let ret_msg = resp.ret_msg.clone();
            return Err(BybitApiError::Business {
                ret_code: resp.ret_code,
                ret_msg,
                response: serde_json::to_value(&resp).unwrap_or_default(),
            });
        }

        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();

        let mut count = 0;
        let mut cache = self.cache.write().unwrap();

        for item in &list {
            if let Some(spec) = parse_instrument_item(item) {
                cache.insert(spec.symbol.clone(), spec);
                count += 1;
            }
        }

        info!(
            category = category,
            symbols = count,
            "instrument info refreshed / 合約信息已刷新"
        );

        Ok(count)
    }

    /// Get the SymbolSpec for a given symbol.
    /// 取得指定交易對的 SymbolSpec。
    pub fn get(&self, symbol: &str) -> Option<SymbolSpec> {
        self.cache.read().unwrap().get(symbol).cloned()
    }

    /// Get lot size (qty_step) for a symbol. Returns None if not cached.
    /// 取得交易對的步長。未緩存時返回 None。
    pub fn get_lot_size(&self, symbol: &str) -> Option<f64> {
        self.cache.read().unwrap().get(symbol).map(|s| s.qty_step)
    }

    /// Get tick size for a symbol. Returns None if not cached.
    /// 取得交易對的 tick 精度。未緩存時返回 None。
    pub fn get_tick_size(&self, symbol: &str) -> Option<f64> {
        self.cache.read().unwrap().get(symbol).map(|s| s.tick_size)
    }

    /// Round qty for a symbol using cached spec.
    /// 使用緩存的規格為交易對取整 qty。
    pub fn round_qty(&self, symbol: &str, qty: f64) -> Option<f64> {
        self.cache
            .read()
            .unwrap()
            .get(symbol)
            .map(|s| s.round_qty(qty))
    }

    /// Round price for a symbol using cached spec.
    /// 使用緩存的規格為交易對取整 price。
    pub fn round_price(&self, symbol: &str, price: f64) -> Option<f64> {
        self.cache
            .read()
            .unwrap()
            .get(symbol)
            .map(|s| s.round_price(price))
    }

    /// Get all cached symbols.
    /// 取得所有已緩存的交易對。
    pub fn symbols(&self) -> Vec<String> {
        self.cache.read().unwrap().keys().cloned().collect()
    }

    /// Get number of cached symbols.
    /// 取得已緩存的交易對數量。
    pub fn len(&self) -> usize {
        self.cache.read().unwrap().len()
    }

    /// Check if cache is empty.
    /// 檢查緩存是否為空。
    pub fn is_empty(&self) -> bool {
        self.cache.read().unwrap().is_empty()
    }
}

impl Default for InstrumentInfoCache {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse a single instrument item from Bybit API response.
/// 從 Bybit API 回應中解析單個合約信息。
///
/// Bybit V5 instruments-info response structure:
///   { "symbol": "BTCUSDT", "baseCoin": "BTC", "quoteCoin": "USDT",
///     "contractType": "LinearPerpetual",
///     "lotSizeFilter": { "qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100" },
///     "priceFilter": { "tickSize": "0.10", "minPrice": "0.10", "maxPrice": "999999" },
///     "lotSizeFilter": { ... "minNotionalValue": "5" } }
fn parse_instrument_item(item: &serde_json::Value) -> Option<SymbolSpec> {
    let symbol = item.get("symbol")?.as_str()?.to_string();
    let base_currency = item
        .get("baseCoin")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let quote_currency = item
        .get("quoteCoin")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let contract_type = item
        .get("contractType")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let lot_filter = item.get("lotSizeFilter")?;
    let price_filter = item.get("priceFilter")?;

    let qty_step = parse_f64_field(lot_filter, "qtyStep").unwrap_or(0.001);
    let min_qty = parse_f64_field(lot_filter, "minOrderQty").unwrap_or(0.001);
    let max_qty = parse_f64_field(lot_filter, "maxOrderQty").unwrap_or(100.0);
    let tick_size = parse_f64_field(price_filter, "tickSize").unwrap_or(0.01);
    let min_price = parse_f64_field(price_filter, "minPrice").unwrap_or(0.01);
    let max_price = parse_f64_field(price_filter, "maxPrice").unwrap_or(0.0);

    // minNotionalValue can be in lotSizeFilter or at root level / 最小名義值位置不固定
    let min_notional = parse_f64_field(lot_filter, "minNotionalValue")
        .or_else(|| parse_f64_field(item, "minNotionalValue"))
        .unwrap_or(0.0);

    let qty_decimals = decimal_places_from_step(qty_step);
    let price_decimals = decimal_places_from_step(tick_size);

    Some(SymbolSpec {
        symbol,
        base_currency,
        quote_currency,
        contract_type,
        qty_step,
        min_qty,
        max_qty,
        tick_size,
        min_price,
        max_price,
        min_notional,
        qty_decimals,
        price_decimals,
    })
}

/// Parse a string field as f64 from a JSON object.
/// 從 JSON 對象中將字串欄位解析為 f64。
fn parse_f64_field(obj: &serde_json::Value, field: &str) -> Option<f64> {
    obj.get(field)?.as_str().and_then(|s| s.parse::<f64>().ok())
}

/// Derive number of decimal places from a step value.
/// 從步長值推導小數位數。
///
/// e.g. 0.001 → 3, 0.10 → 1, 1.0 → 0
fn decimal_places_from_step(step: f64) -> u32 {
    if step <= 0.0 || step >= 1.0 {
        return 0;
    }
    let s = format!("{:.10}", step);
    let trimmed = s.trim_end_matches('0');
    if let Some(dot_pos) = trimmed.find('.') {
        (trimmed.len() - dot_pos - 1) as u32
    } else {
        0
    }
}

/// Round a float to N decimal places.
/// 將浮點數取整到 N 位小數。
fn round_to_decimals(value: f64, decimals: u32) -> f64 {
    let factor = 10_f64.powi(decimals as i32);
    (value * factor).round() / factor
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_btc_spec() -> SymbolSpec {
        SymbolSpec {
            symbol: "BTCUSDT".to_string(),
            base_currency: "BTC".to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.001,
            min_qty: 0.001,
            max_qty: 100.0,
            tick_size: 0.10,
            min_price: 0.10,
            max_price: 999999.0,
            min_notional: 5.0,
            qty_decimals: 3,
            price_decimals: 1,
        }
    }

    #[test]
    fn test_round_qty() {
        let spec = sample_btc_spec();
        assert!((spec.round_qty(0.0056) - 0.005).abs() < 1e-10);
        assert!((spec.round_qty(0.0019) - 0.001).abs() < 1e-10);
        assert!((spec.round_qty(1.9999) - 1.999).abs() < 1e-10);
        assert!((spec.round_qty(0.0001) - 0.0).abs() < 1e-10); // below step
    }

    #[test]
    fn test_round_qty_zero_negative() {
        let spec = sample_btc_spec();
        assert_eq!(spec.round_qty(0.0), 0.0);
        assert_eq!(spec.round_qty(-1.0), 0.0);
    }

    #[test]
    fn test_round_price() {
        let spec = sample_btc_spec();
        // tick_size = 0.10, so 65000.55 → 65000.6
        assert!((spec.round_price(65000.55) - 65000.6).abs() < 1e-10);
        // 65000.04 → 65000.0
        assert!((spec.round_price(65000.04) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_floor_price() {
        let spec = sample_btc_spec();
        assert!((spec.floor_price(65000.99) - 65000.9).abs() < 1e-10);
        assert!((spec.floor_price(65000.01) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_ceil_price() {
        let spec = sample_btc_spec();
        assert!((spec.ceil_price(65000.01) - 65000.1).abs() < 1e-10);
        assert!((spec.ceil_price(65000.0) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_validate_order_ok() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(0.01, 65000.0);
        assert!(ok, "should be valid: {reason}");
    }

    #[test]
    fn test_validate_order_qty_too_small() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(0.0001, 65000.0);
        assert!(!ok);
        assert!(reason.contains("min_qty"));
    }

    #[test]
    fn test_validate_order_qty_too_large() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(200.0, 65000.0);
        assert!(!ok);
        assert!(reason.contains("max_qty"));
    }

    #[test]
    fn test_validate_order_notional_too_small() {
        let spec = sample_btc_spec();
        // 0.001 * 1.0 = 0.001 < min_notional 5
        let (ok, reason) = spec.validate_order(0.001, 1.0);
        assert!(!ok);
        assert!(reason.contains("min_notional"));
    }

    #[test]
    fn test_decimal_places_from_step() {
        assert_eq!(decimal_places_from_step(0.001), 3);
        assert_eq!(decimal_places_from_step(0.10), 1);
        assert_eq!(decimal_places_from_step(0.01), 2);
        assert_eq!(decimal_places_from_step(1.0), 0);
        assert_eq!(decimal_places_from_step(0.0), 0);
    }

    #[test]
    fn test_round_to_decimals() {
        assert!((round_to_decimals(1.23456, 3) - 1.235).abs() < 1e-10);
        assert!((round_to_decimals(1.23456, 0) - 1.0).abs() < 1e-10);
        assert!((round_to_decimals(1.5, 0) - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_instrument_item() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
                "maxOrderQty": "100",
                "minNotionalValue": "5"
            },
            "priceFilter": {
                "tickSize": "0.10",
                "minPrice": "0.10",
                "maxPrice": "999999.00"
            }
        });

        let spec = parse_instrument_item(&item).unwrap();
        assert_eq!(spec.symbol, "BTCUSDT");
        assert_eq!(spec.base_currency, "BTC");
        assert!((spec.qty_step - 0.001).abs() < 1e-10);
        assert!((spec.tick_size - 0.10).abs() < 1e-10);
        assert!((spec.min_notional - 5.0).abs() < 1e-10);
        assert_eq!(spec.qty_decimals, 3);
        assert_eq!(spec.price_decimals, 1);
    }

    #[test]
    fn test_parse_instrument_item_missing_symbol() {
        let item = serde_json::json!({
            "baseCoin": "BTC",
            "lotSizeFilter": {"qtyStep": "0.001"},
            "priceFilter": {"tickSize": "0.10"}
        });
        assert!(parse_instrument_item(&item).is_none());
    }

    #[test]
    fn test_cache_basic_operations() {
        let cache = InstrumentInfoCache::new();
        assert!(cache.is_empty());
        assert_eq!(cache.len(), 0);
        assert!(cache.get("BTCUSDT").is_none());
        assert!(cache.get_lot_size("BTCUSDT").is_none());
        assert!(cache.get_tick_size("BTCUSDT").is_none());
        assert!(cache.round_qty("BTCUSDT", 1.0).is_none());
        assert!(cache.round_price("BTCUSDT", 65000.0).is_none());
    }

    #[test]
    fn test_cache_manual_insert_and_query() {
        let cache = InstrumentInfoCache::new();
        {
            let mut map = cache.cache.write().unwrap();
            map.insert("BTCUSDT".to_string(), sample_btc_spec());
        }

        assert!(!cache.is_empty());
        assert_eq!(cache.len(), 1);
        assert!(cache.get("BTCUSDT").is_some());
        assert!((cache.get_lot_size("BTCUSDT").unwrap() - 0.001).abs() < 1e-10);
        assert!((cache.get_tick_size("BTCUSDT").unwrap() - 0.10).abs() < 1e-10);
        assert!((cache.round_qty("BTCUSDT", 0.0056).unwrap() - 0.005).abs() < 1e-10);
        assert!((cache.round_price("BTCUSDT", 65000.55).unwrap() - 65000.6).abs() < 1e-10);
        assert!(cache.symbols().contains(&"BTCUSDT".to_string()));
    }

    /// Test ETH-style spec with different precision.
    /// 測試 ETH 風格的規格（不同精度）。
    #[test]
    fn test_eth_spec_rounding() {
        let spec = SymbolSpec {
            symbol: "ETHUSDT".to_string(),
            base_currency: "ETH".to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.01,
            min_qty: 0.01,
            max_qty: 1000.0,
            tick_size: 0.01,
            min_price: 0.01,
            max_price: 99999.0,
            min_notional: 5.0,
            qty_decimals: 2,
            price_decimals: 2,
        };
        assert!((spec.round_qty(1.234) - 1.23).abs() < 1e-10);
        assert!((spec.round_price(3500.555) - 3500.56).abs() < 1e-10);
    }
}
