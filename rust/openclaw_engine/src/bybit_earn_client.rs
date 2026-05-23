//! Bybit V5 Earn API client — Flexible Saving only（Sprint 1B Earn first stake B3）。
//!
//! MODULE_NOTE（中）：
//!   - 模塊用途：封裝 Bybit V5 Earn 5 個 endpoint，Sprint 1B first stake 走
//!     FlexibleSaving category only（per OP-3 拍板 flexible-only / fixed 鎖倉
//!     90+ day 對 W9-12 Sprint 1B 過長 defer Sprint 5+）。
//!   - 主要類/函數：`BybitEarnClient`（持 `Arc<BybitRestClient>` reference + 5
//!     endpoint method）；`FlexibleProduct` / `FlexibleSubscribeResult` /
//!     `FlexibleRedeemResult` / `FlexiblePosition` / `AprHistoryPoint` 5 response
//!     struct + 5 list wrapper。
//!   - 依賴：`crate::bybit_rest_client::BybitRestClient`（共用 HMAC-SHA256 簽名 /
//!     rate limit / retCode 觀測；不重複 HTTP 邏輯）。
//!   - 硬邊界：
//!     a. retCode != 0 fail-closed 不重試（per earn_governance §5 + 9 不變量 #7;
//!        共用 `get_checked` / `post_checked` 直接 propagate `BybitApiError`）。
//!     b. Rate limit group = `Asset`（5 req/s；per BB C4 verdict + SDK 註釋）；
//!        於 `bybit_rest_client::RateLimitGroup::from_path` 已 patch `/v5/earn/`
//!        前綴對映 Asset（同 PR）。
//!     c. 本 client 純 endpoint 包裝；intent processor / lease / audit log 接線在
//!        Sprint 1B Wave B 後續 PR（E1d/E1e）。
//!     d. **產線啟用前置**（OP-1 重發 API key 加 Earn scope，per dispatch packet
//!        §1.2 OP-1 < 2026-04-09 路徑）：本 client 在 OP-1 重發完成前僅走 mock
//!        unit test；real Bybit endpoint smoke 由 Wave E operator 親手觸發。
//!
//! Endpoint 對映（tiagosiebler 2026 reference SDK + Bybit V5 changelog 對齊；PA
//! dispatch packet §1.2.1 列「/v5/earn/flexible/*」屬 2025 舊路徑，2026 Bybit V5
//! 統一為 `/v5/earn/*` 帶 `category=FlexibleSaving`，本 IMPL 採真實 path）：
//!
//! | 編號 | dispatch packet | 真實 Bybit V5 path        | HTTP   | 本 client method        |
//! |-----|-----------------|---------------------------|--------|-------------------------|
//! | E-1 | flexible/product  | /v5/earn/product          | GET    | get_flexible_products   |
//! | E-2 | flexible/subscribe| /v5/earn/place-order      | POST   | subscribe_flexible      |
//! | E-3 | flexible/redeem   | /v5/earn/place-order      | POST   | redeem_flexible         |
//! | E-4 | flexible/position | /v5/earn/position         | GET    | get_flexible_positions  |
//! | E-5 | apr-history       | /v5/earn/apr-history      | GET    | get_apr_history         |

use crate::bybit_rest_client::{BybitApiError, BybitResult, BybitRestClient};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

// ---------------------------------------------------------------------------
// 常數 / Constants
// ---------------------------------------------------------------------------

/// Bybit Earn category 對應 OP-3 flexible-only 拍板。
/// 為什麼是常數而非 caller 傳值：Sprint 1B 範圍鎖定 FlexibleSaving；fixed staking
/// (OnChain / FixedTerm) defer Sprint 5+。caller 不應有自由度走非 flexible path。
const CATEGORY_FLEXIBLE_SAVING: &str = "FlexibleSaving";

/// Bybit V5 `accountType` 對應 Unified Trading Account（per Bybit V5 統一帳戶
/// 規範 + earn_governance §2.4 「Earn 餘額由 Unified Trading 主帳出資」）。
const ACCOUNT_TYPE_UNIFIED: &str = "UNIFIED";

// ---------------------------------------------------------------------------
// Endpoint 路徑 / Endpoint paths
// ---------------------------------------------------------------------------

const PATH_EARN_PRODUCT: &str = "/v5/earn/product";
const PATH_EARN_PLACE_ORDER: &str = "/v5/earn/place-order";
const PATH_EARN_POSITION: &str = "/v5/earn/position";
const PATH_EARN_APR_HISTORY: &str = "/v5/earn/apr-history";

// ---------------------------------------------------------------------------
// Request payload struct
// ---------------------------------------------------------------------------

/// `/v5/earn/place-order` POST body — stake / redeem 統一入口。
///
/// 為什麼 `orderType` 為 enum 而非自由字串：Bybit V5 僅接受 `Stake` / `Redeem` 兩
/// 字面；強型別在編譯期阻止打字漂移污染 audit log。
/// `orderLinkId` 為 caller 端 idempotency key（per Bybit V5 慣例）；建議 UUID v7
/// 對映 lease_id / authorization 但本 client 不強制（caller 端責任）。
#[derive(Debug, Clone, Serialize)]
struct PlaceOrderRequest<'a> {
    category: &'a str,
    #[serde(rename = "orderType")]
    order_type: &'static str,
    #[serde(rename = "accountType")]
    account_type: &'a str,
    coin: &'a str,
    #[serde(rename = "productId")]
    product_id: &'a str,
    /// Bybit V5 amount field 為字串型；Decimal/USDT 精度由 caller 端負責對齊
    /// `EarnProduct.precision`，避免浮點誤差。
    amount: &'a str,
    /// Caller-side idempotency key；Bybit V5 強制要求。
    #[serde(rename = "orderLinkId")]
    order_link_id: &'a str,
}

// ---------------------------------------------------------------------------
// Response struct — Flexible Saving only（5 endpoint）
// ---------------------------------------------------------------------------

/// E-1 GET `/v5/earn/product` — Flexible Saving 產品。
///
/// 對齊 tiagosiebler SDK `EarnProductV5` 但 `status` 改 `String` 而非 enum，因
/// Bybit V5 未來可能加新 status（e.g. "Maintenance"）；保守 String 避免 panic-on-
/// unknown。caller 端必須白名單 "Available" 才允許 stake。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FlexibleProduct {
    pub category: String,
    /// 預估 APR；Bybit V5 返回字串如 "0.1023"（10.23%）；caller 端負責解析。
    #[serde(rename = "estimateApr")]
    pub estimate_apr: String,
    pub coin: String,
    /// 最小 stake 金額（per coin precision；e.g. "1.0" 表 1 USDT）。
    #[serde(rename = "minStakeAmount")]
    pub min_stake_amount: String,
    /// 最大 stake 金額（單筆上限；tier ceiling 由 caller 對 risk_config cap 對齊）。
    #[serde(rename = "maxStakeAmount")]
    pub max_stake_amount: String,
    /// Coin precision（decimal digits）；amount 字串四捨五入依據。
    pub precision: String,
    #[serde(rename = "productId")]
    pub product_id: String,
    /// "Available" 或 "NotAvailable"；caller 必白名單。
    pub status: String,
}

/// `/v5/earn/product` GET response result 內部 list 結構。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlexibleProductListResult {
    #[serde(default)]
    pub list: Vec<FlexibleProduct>,
}

/// E-2 / E-3 POST `/v5/earn/place-order` — Stake / Redeem 統一 response。
///
/// Bybit V5 返回 `orderId` + `orderLinkId`；交易為 async（per SDK 註釋「使用
/// getEarnOrderHistory 追蹤」），caller 端負責後續 status 輪詢或 reconciliation
/// 對賬（per earn_governance §6 Daily cron）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PlaceOrderResult {
    #[serde(rename = "orderId")]
    pub order_id: String,
    #[serde(rename = "orderLinkId")]
    pub order_link_id: String,
}

/// E-4 GET `/v5/earn/position` — Flexible Saving 持倉。
///
/// 對齊 tiagosiebler SDK `EarnPositionV5`；多數 field optional 因 Bybit V5
/// 不同 product type 返回不同子集。`amount` / `totalPnl` / `claimableYield` 為
/// 字串型 Decimal（caller 端負責 parsing），對齊 Bybit V5 精度語意。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FlexiblePosition {
    pub coin: String,
    #[serde(rename = "productId")]
    pub product_id: String,
    /// 當前 stake 數量。
    pub amount: String,
    /// 累計 PnL（含利息）。
    #[serde(rename = "totalPnl")]
    pub total_pnl: String,
    /// 可領取收益（pending claim）。
    #[serde(rename = "claimableYield")]
    pub claimable_yield: String,
    /// position id（fixed-term 有；flexible 可能空）。
    #[serde(default)]
    pub id: Option<String>,
    /// 狀態（"Holding" / "PendingRedeem" 等；具體值看 Bybit V5 spec）。
    #[serde(default)]
    pub status: Option<String>,
    /// 對應 orderId（最近一筆 stake / redeem）。
    #[serde(rename = "orderId", default)]
    pub order_id: Option<String>,
}

/// `/v5/earn/position` GET response result。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlexiblePositionListResult {
    #[serde(default)]
    pub list: Vec<FlexiblePosition>,
}

/// E-5 GET `/v5/earn/apr-history` — APR 歷史 sample 單點。
///
/// 對齊 tiagosiebler SDK `EarnAprHistoryPointV5`；`timestamp` / `apr` 均為字串
/// 型，避免 Bybit V5 精度漂移（caller 端責任 parse）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AprHistoryPoint {
    /// 採樣時間戳（毫秒字串）。
    pub timestamp: String,
    /// 該時刻 APR（e.g. "0.0987"）。
    pub apr: String,
}

/// `/v5/earn/apr-history` GET response result。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AprHistoryResult {
    #[serde(default)]
    pub list: Vec<AprHistoryPoint>,
}

// ---------------------------------------------------------------------------
// BybitEarnClient
// ---------------------------------------------------------------------------

/// Bybit V5 Earn API client — Flexible Saving only。
///
/// 為什麼 `Arc<BybitRestClient>`：共用既有 HMAC-SHA256 簽名 / rate limit /
/// retCode 4xx/5xx 觀測；caller 端從 IntentProcessor / reconciliation cron 共用
/// 同一 client handle 不重複建立 reqwest pool。
pub struct BybitEarnClient {
    rest_client: Arc<BybitRestClient>,
}

impl BybitEarnClient {
    /// 構造 Earn client。
    ///
    /// 為什麼接 `Arc<BybitRestClient>`：production 端從 builder（per intent
    /// processor / engine bootstrap）共用同一 client；test 端可注入自構 client
    /// 走 mock secret slot。
    pub fn new(rest_client: Arc<BybitRestClient>) -> Self {
        Self { rest_client }
    }

    // -----------------------------------------------------------------------
    // E-1: GET /v5/earn/product — Flexible Saving 產品列表
    // -----------------------------------------------------------------------

    /// 查詢 Flexible Saving 產品列表（含 APR + tier + product_id）。
    ///
    /// 為什麼 `coin` 強制傳：Sprint 1B first stake 鎖定 USDT；Bybit V5 spec 允許
    /// 不傳 coin 拉所有 coin，但本 IMPL 強制 caller 傳明確 coin 避免 overshare。
    pub async fn get_flexible_products(
        &self,
        coin: &str,
    ) -> BybitResult<FlexibleProductListResult> {
        let params = [
            ("category", CATEGORY_FLEXIBLE_SAVING),
            ("coin", coin),
        ];
        let resp = self
            .rest_client
            .get_checked(PATH_EARN_PRODUCT, &params)
            .await?;
        serde_json::from_value::<FlexibleProductListResult>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    // -----------------------------------------------------------------------
    // E-2: POST /v5/earn/place-order — Subscribe (Stake) Flexible Saving
    // -----------------------------------------------------------------------

    /// 認購（stake）Flexible Saving 產品。
    ///
    /// 為什麼 `amount` 為 `&str` 而非 `f64` / `Decimal`：Bybit V5 amount field
    /// 為字串型避免浮點誤差；caller 端必須先依 `FlexibleProduct.precision` 對齊
    /// 字串四捨五入。本 client 不做隱式轉換，保持責任邊界清晰。
    ///
    /// 為什麼 `order_link_id` 強制 caller 傳：Bybit V5 強制要求 idempotency
    /// key；caller 端應對映 lease_id 或 authorization UUID（per
    /// earn_governance §3.2 + W-AUDIT-9 LeaseScope 設計），確保 audit chain 可
    /// reconstruct。
    pub async fn subscribe_flexible(
        &self,
        coin: &str,
        product_id: &str,
        amount: &str,
        order_link_id: &str,
    ) -> BybitResult<PlaceOrderResult> {
        let body = PlaceOrderRequest {
            category: CATEGORY_FLEXIBLE_SAVING,
            order_type: "Stake",
            account_type: ACCOUNT_TYPE_UNIFIED,
            coin,
            product_id,
            amount,
            order_link_id,
        };
        let body_value = serde_json::to_value(&body).map_err(BybitApiError::JsonParse)?;
        let resp = self
            .rest_client
            .post_checked(PATH_EARN_PLACE_ORDER, &body_value)
            .await?;
        serde_json::from_value::<PlaceOrderResult>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    // -----------------------------------------------------------------------
    // E-3: POST /v5/earn/place-order — Redeem Flexible Saving
    // -----------------------------------------------------------------------

    /// 贖回（redeem）Flexible Saving 產品。
    ///
    /// 為什麼與 stake 共用同 endpoint 但分兩 method：對映上層 `IntentType::
    /// EarnStake` / `IntentType::EarnRedeem` 兩 enum variant；caller 端不需自行
    /// 處理 `order_type` 字串對映，編譯期強型別保護。
    ///
    /// 注意 Bybit 提示：redemption 高需求時段可能延遲 48 小時且不可取消，本金繼
    /// 續計息直到完成（per SDK 註釋）。caller 端 reconciliation cron 應將
    /// `EstimateRedeemTime` 納入超時告警閾值。
    pub async fn redeem_flexible(
        &self,
        coin: &str,
        product_id: &str,
        amount: &str,
        order_link_id: &str,
    ) -> BybitResult<PlaceOrderResult> {
        let body = PlaceOrderRequest {
            category: CATEGORY_FLEXIBLE_SAVING,
            order_type: "Redeem",
            account_type: ACCOUNT_TYPE_UNIFIED,
            coin,
            product_id,
            amount,
            order_link_id,
        };
        let body_value = serde_json::to_value(&body).map_err(BybitApiError::JsonParse)?;
        let resp = self
            .rest_client
            .post_checked(PATH_EARN_PLACE_ORDER, &body_value)
            .await?;
        serde_json::from_value::<PlaceOrderResult>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    // -----------------------------------------------------------------------
    // E-4: GET /v5/earn/position — Flexible Saving 持倉
    // -----------------------------------------------------------------------

    /// 查詢 Flexible Saving 持倉。
    ///
    /// `product_id` / `coin` 為可選過濾；Daily reconciliation cron 路徑通常只傳
    /// category=FlexibleSaving 拉全部，逐筆對照 `learning.earn_movement_log`。
    pub async fn get_flexible_positions(
        &self,
        product_id: Option<&str>,
        coin: Option<&str>,
    ) -> BybitResult<FlexiblePositionListResult> {
        // 為什麼用 Vec 而非固定 array：可選 param 數量動態（0-2 個），Vec 簡單
        // 且 rest_client.get_checked 接 `&[(&str, &str)]` 兼容。
        let mut params: Vec<(&str, &str)> = vec![("category", CATEGORY_FLEXIBLE_SAVING)];
        if let Some(pid) = product_id {
            params.push(("productId", pid));
        }
        if let Some(c) = coin {
            params.push(("coin", c));
        }
        let resp = self
            .rest_client
            .get_checked(PATH_EARN_POSITION, &params)
            .await?;
        serde_json::from_value::<FlexiblePositionListResult>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    // -----------------------------------------------------------------------
    // E-5: GET /v5/earn/apr-history — APR 歷史
    // -----------------------------------------------------------------------

    /// 查詢產品 APR 歷史（最多 ~6 個月）。
    ///
    /// 為什麼 `product_id` 強制傳：Bybit V5 spec 此 endpoint 必填 `productId`；
    /// `start_time` / `end_time` 為毫秒時間戳 optional filter。
    ///
    /// 為什麼公開 endpoint 仍走 `get_checked`：BybitRestClient `get_checked`
    /// 路徑統一帶簽名 + retCode 觀測（per PA-DRIFT-4 round 1 H-3 fix）；本 IMPL
    /// 不繞 signed path 即可繞過 4xx/5xx 計數遺漏。
    pub async fn get_apr_history(
        &self,
        product_id: &str,
        start_time_ms: Option<i64>,
        end_time_ms: Option<i64>,
    ) -> BybitResult<AprHistoryResult> {
        let start_str = start_time_ms.map(|t| t.to_string());
        let end_str = end_time_ms.map(|t| t.to_string());
        let mut params: Vec<(&str, &str)> = vec![
            ("category", CATEGORY_FLEXIBLE_SAVING),
            ("productId", product_id),
        ];
        if let Some(ref s) = start_str {
            params.push(("startTime", s.as_str()));
        }
        if let Some(ref e) = end_str {
            params.push(("endTime", e.as_str()));
        }
        let resp = self
            .rest_client
            .get_checked(PATH_EARN_APR_HISTORY, &params)
            .await?;
        serde_json::from_value::<AprHistoryResult>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }
}

// ---------------------------------------------------------------------------
// Tests — mock response only（OP-1 key 重發前不接 real Bybit endpoint）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// E-1 response serde round-trip。
    ///
    /// 為什麼 round-trip：production 路徑 `serde_json::from_value(resp.result)`
    /// 失敗會被 `BybitApiError::JsonParse` 攔截；本 test 確保正常 Bybit V5
    /// payload schema 在 caller 端不誤判 parse fail。
    #[test]
    fn test_flexible_product_serde_round_trip() {
        let raw = serde_json::json!({
            "list": [
                {
                    "category": "FlexibleSaving",
                    "estimateApr": "0.1023",
                    "coin": "USDT",
                    "minStakeAmount": "1",
                    "maxStakeAmount": "1000000",
                    "precision": "8",
                    "productId": "USDT001",
                    "status": "Available"
                },
                {
                    "category": "FlexibleSaving",
                    "estimateApr": "0.03",
                    "coin": "USDT",
                    "minStakeAmount": "200.01",
                    "maxStakeAmount": "5000000",
                    "precision": "8",
                    "productId": "USDT002",
                    "status": "Available"
                }
            ]
        });
        let parsed: FlexibleProductListResult =
            serde_json::from_value(raw).expect("flexible product list deserialize");
        assert_eq!(parsed.list.len(), 2);
        assert_eq!(parsed.list[0].product_id, "USDT001");
        assert_eq!(parsed.list[0].estimate_apr, "0.1023");
        assert_eq!(parsed.list[0].status, "Available");
        assert_eq!(parsed.list[1].min_stake_amount, "200.01");
    }

    /// 未知 status 不應 panic（Bybit 未來可能加新狀態如 "Maintenance"）。
    #[test]
    fn test_flexible_product_unknown_status_does_not_panic() {
        let raw = serde_json::json!({
            "list": [{
                "category": "FlexibleSaving",
                "estimateApr": "0.05",
                "coin": "USDT",
                "minStakeAmount": "1",
                "maxStakeAmount": "1000",
                "precision": "8",
                "productId": "USDT099",
                "status": "Maintenance"
            }]
        });
        let parsed: FlexibleProductListResult =
            serde_json::from_value(raw).expect("unknown status should not panic");
        assert_eq!(parsed.list[0].status, "Maintenance");
    }

    /// E-2 / E-3 place-order response 對映。
    #[test]
    fn test_place_order_result_round_trip() {
        let raw = serde_json::json!({
            "orderId": "1234567890",
            "orderLinkId": "lease-uuid-abc"
        });
        let parsed: PlaceOrderResult =
            serde_json::from_value(raw).expect("place order result deserialize");
        assert_eq!(parsed.order_id, "1234567890");
        assert_eq!(parsed.order_link_id, "lease-uuid-abc");
    }

    /// 確認 PlaceOrderRequest body 序列化為 Bybit V5 預期 camelCase + 字面 enum。
    ///
    /// 為什麼測 body 序列化：Bybit V5 簽名走 body JSON 字串；若 field 名漂移
    /// （e.g. snake_case 漏 rename）→ 簽名與 body 不一致 → retCode != 0 連續
    /// fail，影響 production 不可恢復。本 test 在編譯時 catch field rename 漂移。
    #[test]
    fn test_place_order_request_serialization() {
        let req = PlaceOrderRequest {
            category: CATEGORY_FLEXIBLE_SAVING,
            order_type: "Stake",
            account_type: ACCOUNT_TYPE_UNIFIED,
            coin: "USDT",
            product_id: "USDT001",
            amount: "200.0",
            order_link_id: "test-lease-uuid",
        };
        let body = serde_json::to_value(&req).expect("serialize");
        assert_eq!(body["category"], "FlexibleSaving");
        assert_eq!(body["orderType"], "Stake");
        assert_eq!(body["accountType"], "UNIFIED");
        assert_eq!(body["coin"], "USDT");
        assert_eq!(body["productId"], "USDT001");
        assert_eq!(body["amount"], "200.0");
        assert_eq!(body["orderLinkId"], "test-lease-uuid");
    }

    /// E-4 position 缺 optional field 仍能 deserialize（per Bybit V5 spec
    /// flexible 不一定返回 fixed-term 才有的 estimateRedeemTime 等 field）。
    #[test]
    fn test_flexible_position_optional_fields() {
        let raw = serde_json::json!({
            "list": [{
                "coin": "USDT",
                "productId": "USDT001",
                "amount": "200.0",
                "totalPnl": "0.0152",
                "claimableYield": "0.0123"
                // id / status / orderId 缺
            }]
        });
        let parsed: FlexiblePositionListResult =
            serde_json::from_value(raw).expect("optional fields should default to None");
        assert_eq!(parsed.list.len(), 1);
        let pos = &parsed.list[0];
        assert_eq!(pos.coin, "USDT");
        assert_eq!(pos.amount, "200.0");
        assert_eq!(pos.total_pnl, "0.0152");
        assert_eq!(pos.claimable_yield, "0.0123");
        assert!(pos.id.is_none());
        assert!(pos.status.is_none());
        assert!(pos.order_id.is_none());
    }

    /// E-4 position 完整 field（fixed-term-like sample）。
    #[test]
    fn test_flexible_position_full_fields() {
        let raw = serde_json::json!({
            "list": [{
                "coin": "USDT",
                "productId": "USDT001",
                "amount": "200.0",
                "totalPnl": "0.0152",
                "claimableYield": "0.0123",
                "id": "pos-abc",
                "status": "Holding",
                "orderId": "ord-xyz"
            }]
        });
        let parsed: FlexiblePositionListResult =
            serde_json::from_value(raw).expect("full fields deserialize");
        let pos = &parsed.list[0];
        assert_eq!(pos.id.as_deref(), Some("pos-abc"));
        assert_eq!(pos.status.as_deref(), Some("Holding"));
        assert_eq!(pos.order_id.as_deref(), Some("ord-xyz"));
    }

    /// E-5 APR history 多點對映。
    #[test]
    fn test_apr_history_round_trip() {
        let raw = serde_json::json!({
            "list": [
                {"timestamp": "1714000000000", "apr": "0.1023"},
                {"timestamp": "1714086400000", "apr": "0.1001"}
            ]
        });
        let parsed: AprHistoryResult =
            serde_json::from_value(raw).expect("apr history deserialize");
        assert_eq!(parsed.list.len(), 2);
        assert_eq!(parsed.list[0].timestamp, "1714000000000");
        assert_eq!(parsed.list[0].apr, "0.1023");
        assert_eq!(parsed.list[1].apr, "0.1001");
    }

    /// 空 list 不應 panic（per Bybit V5 spec：未上架 / filter 不符 → 空 list）。
    #[test]
    fn test_empty_list_does_not_panic() {
        let raw = serde_json::json!({});
        let parsed: FlexibleProductListResult =
            serde_json::from_value(raw).expect("empty payload defaults to empty list");
        assert!(parsed.list.is_empty());

        let raw_apr = serde_json::json!({});
        let parsed_apr: AprHistoryResult =
            serde_json::from_value(raw_apr).expect("empty apr defaults to empty list");
        assert!(parsed_apr.list.is_empty());

        let raw_pos = serde_json::json!({});
        let parsed_pos: FlexiblePositionListResult =
            serde_json::from_value(raw_pos).expect("empty position defaults to empty list");
        assert!(parsed_pos.list.is_empty());
    }

    /// 確認 Bybit V5 path constants 對齊 tiagosiebler 2026 SDK 範式。
    ///
    /// 為什麼測常數：Sprint 1B first stake 5 endpoint 走 Asset 5 req/s rate limit
    /// group（per bybit_rest_client::RateLimitGroup::from_path patch + test）；
    /// path 字面若漂移會繞過 rate limit + audit observation。
    #[test]
    fn test_endpoint_path_constants() {
        assert_eq!(PATH_EARN_PRODUCT, "/v5/earn/product");
        assert_eq!(PATH_EARN_PLACE_ORDER, "/v5/earn/place-order");
        assert_eq!(PATH_EARN_POSITION, "/v5/earn/position");
        assert_eq!(PATH_EARN_APR_HISTORY, "/v5/earn/apr-history");
    }

    /// 確認 category / accountType 字面對齊 OP-3 拍板 flexible-only。
    #[test]
    fn test_category_and_account_type_constants() {
        assert_eq!(CATEGORY_FLEXIBLE_SAVING, "FlexibleSaving");
        assert_eq!(ACCOUNT_TYPE_UNIFIED, "UNIFIED");
    }
}
