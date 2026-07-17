//! IBKR **W6-S3 market data provenance 契約**（`stock_market_data_provenance_v1`;source-only,
//! Rust 為 authority）。
//!
//! 本檔是 W6-S3 交付的**溯源契約層**：一個 (instrument, reqId) 訂閱窗的 market-data 溯源
//! 事實 typed shape,供 W6-S3 消化層（`ibkr_tws_market_data`）填值——把「這批 quote 是誰、
//! 哪種 entitlement、何時、對哪個 instrument/日曆、是否 adjustment」收斂成可重建、可審計的
//! 單一雜湊錨。不開 socket、不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;純資料 +
//! 純函數（`validate()` 零副作用）。
//!
//! **entitlement 三態紀律（QC 紅線的溯源側）**：`Entitled`（realtime live）/`Delayed`
//! （15-20min 免費檔）/`None`（無權限,halt）——溯源必誠實標明本窗檔位,禁把 delayed 窗
//! 標成 entitled。`UnknownDenied` 為 fail-closed 預設（`validate()` 必拒）。
//!
//! **provenance_hash（PIT 可重建）**：sha256（64 lowercase hex）over
//! `provenance_hash_preimage()` 的規範化溯源欄序——preimage 為本檔純函數（單一定義點,消化
//! 層/重放端共用),雜湊計算歸消化層（本 crate 無雜湊依賴,契約只驗 shape `is_sha256_hex`）。
//! 溯源欄集含 instrument identity hash（W6-S1）+ calendar hash（W6-S2;本切片以消化層供給的
//! sha256 占位承載,契約只驗 shape,語義綁定歸 S2）+ entitlement 態 + adjustment marker +
//! 窗時戳——令「同批 quote 的溯源」跨端可重建一致。
//!
//! **時戳紀律**：`first_tick_at_ms`/`last_tick_at_ms` 為消化層 client 側捕捉時鐘（wire tick
//! 不自帶 per-row 時戳）;`validate(now_ms)` 注入時鐘校驗兩者非零、有序（last≥first）、不在
//! 未來（fixture 用相對時鐘,禁硬編當前日期）。

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_positions_row::is_normalized_symbol;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID: &str = "stock_market_data_provenance_v1";

/// **W6-S4 calendar 未綁哨兵**：market data provenance mint 時,若該 conId 尚無 W6-S1
/// identity row,或其 tradingHours/liquidHours 無法解析為交易日曆,消化層以此哨兵填
/// `calendar_hash`——`validate()` 收斂為 `CalendarUnbound` blocker（fail-closed,不 accepted）。
///
/// 為什麼要 typed 未綁態而非捏值:calendar_hash 是溯源錨,未綁時**絕不捏 hash、絕不以
/// shape-only 佔位冒充真值**（那會令下游把未經日曆綁定的 quote 當可信）——未綁就誠實標未綁。
/// 本哨兵刻意非 sha256 形狀,與真 hash / 「hash 形狀損壞」在 `validate()` 分支上結構性區隔。
pub const IBKR_CALENDAR_HASH_UNBOUND_SENTINEL: &str = "calendar_unbound";

/// market-data entitlement 三態（+ fail-closed 未知）。錯誤碼 FSM（354/10167/10197…）的
/// 收斂終態:`None`=halt、`Delayed`=降級檔、`Entitled`=realtime。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrMarketDataEntitlementStateV1 {
    /// realtime live 訂閱權限。
    Entitled,
    /// delayed（15-20min）免費檔——**必顯式 opt-in（reqMarketDataType 3|4）**。
    Delayed,
    /// 無權限（354/10186/10190 halt;不重試,fail-closed）。
    None,
    /// 契約 default / 未定 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrMarketDataEntitlementStateV1 {
    fn default() -> Self {
        Self::UnknownDenied
    }
}

impl IbkrMarketDataEntitlementStateV1 {
    /// 規範化 wire 投影（preimage/telemetry 用;`UnknownDenied` 以固定哨兵串保 preimage 確定性）。
    pub fn as_wire(&self) -> &'static str {
        match self {
            Self::Entitled => "entitled",
            Self::Delayed => "delayed",
            Self::None => "none",
            Self::UnknownDenied => "unknown_denied",
        }
    }
}

/// price adjustment marker（L1 realtime/delayed tick 恆 `Raw`=未調整;split/div 調整歸歷史面,
/// 本 lane 不承）。`UnknownDenied`=fail-closed 預設。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPriceAdjustmentV1 {
    /// 未調整原始 tick（L1 lane 唯一合法值）。
    Raw,
    /// 契約 default / 未定 的 fail-closed 分類（`validate()` 必拒——lane 不承調整序列)。
    UnknownDenied,
}

impl Default for IbkrPriceAdjustmentV1 {
    fn default() -> Self {
        Self::UnknownDenied
    }
}

impl IbkrPriceAdjustmentV1 {
    pub fn as_wire(&self) -> &'static str {
        match self {
            Self::Raw => "raw",
            Self::UnknownDenied => "unknown_denied",
        }
    }
}

/// market-data 溯源單筆 typed 契約（W6-S3 消化層的唯一合法溯源承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrMarketDataProvenanceV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// vendor 綁定（恆 `Ibkr`;溯源的 vendor 欄）。
    pub broker: Broker,
    /// IBKR contract id（主鍵;正整數）。
    pub con_id: i64,
    /// 標的代碼（規範化）。
    pub symbol: String,
    /// 訂閱 reqId（窗鍵;正整數）。
    pub req_id: i64,
    /// entitlement 三態（`UnknownDenied` 即 blocker）。
    pub entitlement_state: IbkrMarketDataEntitlementStateV1,
    /// price adjustment marker（L1 恆 `Raw`;`UnknownDenied` 即 blocker）。
    pub adjustment: IbkrPriceAdjustmentV1,
    /// 窗首 tick 捕捉時戳（epoch ms;非零）。
    pub first_tick_at_ms: u64,
    /// 窗末 tick 捕捉時戳（epoch ms;非零、≥first、≤now）。
    pub last_tick_at_ms: u64,
    /// W6-S1 instrument identity hash（sha256 64 hex;溯源錨,綁 instrument 身分）。
    pub instrument_identity_hash: String,
    /// W6-S2 calendar hash（sha256 64 hex;溯源錨,綁交易日曆——本切片消化層占位供給,
    /// shape 驗;語義綁定歸 S2）。
    pub calendar_hash: String,
    /// 溯源雜湊（sha256 64 hex over `provenance_hash_preimage()`;計算歸消化層,契約驗 shape）。
    pub provenance_hash: String,
    // ---- 負空間安全束（溯源為唯讀事實,恆 false）----
    /// 溯源承載過程永不路由訂單。
    pub order_routed: bool,
    /// 溯源永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrMarketDataProvenanceV1 {
    /// fail-closed 預設（空 id / 未知 entitlement/adjustment / 零時戳 / 空 hash——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            con_id: 0,
            symbol: String::new(),
            req_id: 0,
            entitlement_state: IbkrMarketDataEntitlementStateV1::UnknownDenied,
            adjustment: IbkrPriceAdjustmentV1::UnknownDenied,
            first_tick_at_ms: 0,
            last_tick_at_ms: 0,
            instrument_identity_hash: String::new(),
            calendar_hash: String::new(),
            provenance_hash: String::new(),
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrMarketDataProvenanceV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;Entitled realtime 窗）。hash 為 64 hex 占位
    /// （真 hash 由消化層鑄）;時戳為非零占位（無牆鐘依賴）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            con_id: 756733,
            symbol: "SPY".to_string(),
            req_id: 101,
            entitlement_state: IbkrMarketDataEntitlementStateV1::Entitled,
            adjustment: IbkrPriceAdjustmentV1::Raw,
            first_tick_at_ms: 123_456_700,
            last_tick_at_ms: 123_456_789,
            instrument_identity_hash: placeholder_hash('a'),
            calendar_hash: placeholder_hash('b'),
            provenance_hash: placeholder_hash('c'),
            order_routed: false,
            secret_content_serialized: false,
        }
    }

    /// 可通過校驗的 delayed 溯源 fixture（acceptance:誠實標 Delayed 檔位）。
    pub fn accepted_delayed_fixture() -> Self {
        Self {
            entitlement_state: IbkrMarketDataEntitlementStateV1::Delayed,
            ..Self::accepted_fixture()
        }
    }

    /// **provenance_hash 規範化 preimage**（單一定義點;PIT 可重建的溯源錨）。
    /// 為什麼取這個欄集:溯源=「這批 quote 的來歷」——vendor/instrument/日曆身分 + entitlement
    /// 檔位 + adjustment + 窗時戳;欄序固定、`\n` 定界、域前綴防跨契約碰撞;枚舉以 wire 投影
    /// （含 `UnknownDenied` 哨兵串,保 preimage 全域確定性）。**排除** provenance_hash 自身
    /// （避免自指）。
    pub fn provenance_hash_preimage(&self) -> String {
        [
            IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            match self.broker {
                Broker::Ibkr => "ibkr",
                Broker::Bybit => "bybit",
            },
            &self.con_id.to_string(),
            &self.symbol,
            &self.req_id.to_string(),
            self.entitlement_state.as_wire(),
            self.adjustment.as_wire(),
            &self.first_tick_at_ms.to_string(),
            &self.last_tick_at_ms.to_string(),
            &self.instrument_identity_hash,
            &self.calendar_hash,
        ]
        .join("\n")
    }

    /// 行級校驗（零副作用;fail-closed）。`now_ms` 注入時鐘（時戳不得在未來;fixture 用相對
    /// 時鐘,禁硬編當前日期）。
    pub fn validate(&self, now_ms: u64) -> IbkrMarketDataProvenanceVerdict {
        use IbkrMarketDataProvenanceBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID {
            blockers.push(B::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(B::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(B::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(B::WrongBroker);
        }
        if self.con_id <= 0 {
            blockers.push(B::ConIdInvalid);
        }
        if !is_normalized_symbol(&self.symbol) {
            blockers.push(B::SymbolInvalid);
        }
        if self.req_id <= 0 {
            blockers.push(B::ReqIdInvalid);
        }
        if self.entitlement_state == IbkrMarketDataEntitlementStateV1::UnknownDenied {
            blockers.push(B::EntitlementStateUnknownDenied);
        }
        if self.adjustment == IbkrPriceAdjustmentV1::UnknownDenied {
            blockers.push(B::AdjustmentUnknownDenied);
        }
        if self.first_tick_at_ms == 0 {
            blockers.push(B::FirstTickMissing);
        }
        if self.last_tick_at_ms == 0 {
            blockers.push(B::LastTickMissing);
        } else if self.last_tick_at_ms > now_ms {
            blockers.push(B::LastTickInFuture);
        }
        // 窗有序:last≥first（兩者非零時才判序,避免與缺失 blocker 疊加噪音）。
        if self.first_tick_at_ms != 0
            && self.last_tick_at_ms != 0
            && self.last_tick_at_ms < self.first_tick_at_ms
        {
            blockers.push(B::WindowOutOfOrder);
        }
        if !is_sha256_hex(&self.instrument_identity_hash) {
            blockers.push(B::InstrumentIdentityHashInvalid);
        }
        // W6-S4:calendar 未綁（conId 尚無 identity row / 日曆解析失敗）以哨兵承載 → typed
        // `CalendarUnbound`（fail-closed）;與「hash 形狀損壞」（`CalendarHashInvalid`）分支區隔——
        // 消化層絕不捏 hash 冒充已綁。
        if self.calendar_hash == IBKR_CALENDAR_HASH_UNBOUND_SENTINEL {
            blockers.push(B::CalendarUnbound);
        } else if !is_sha256_hex(&self.calendar_hash) {
            blockers.push(B::CalendarHashInvalid);
        }
        if !is_sha256_hex(&self.provenance_hash) {
            blockers.push(B::ProvenanceHashInvalid);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrMarketDataProvenanceVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrMarketDataProvenanceVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrMarketDataProvenanceBlocker>,
}

impl IbkrMarketDataProvenanceVerdict {
    pub fn new(blockers: Vec<IbkrMarketDataProvenanceBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed;封閉枚舉）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrMarketDataProvenanceBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ConIdInvalid,
    SymbolInvalid,
    ReqIdInvalid,
    EntitlementStateUnknownDenied,
    AdjustmentUnknownDenied,
    FirstTickMissing,
    LastTickMissing,
    LastTickInFuture,
    WindowOutOfOrder,
    InstrumentIdentityHashInvalid,
    CalendarHashInvalid,
    /// W6-S4:calendar 未綁（哨兵承載;conId 尚無 identity row / 日曆解析失敗）——fail-closed
    /// 未綁態,與 `CalendarHashInvalid`（形狀損壞）語義區隔。
    CalendarUnbound,
    ProvenanceHashInvalid,
    OrderRouted,
    SecretContentSerialized,
}

/// fixture 用 64 hex 占位（沿 W6-S1 `placeholder_hash` 慣例;真 hash 由消化層鑄）。
fn placeholder_hash(fill: char) -> String {
    fill.to_string().repeat(64)
}

#[cfg(test)]
mod tests {
    use super::*;

    const NOW: u64 = 1_000_000_000;

    #[test]
    fn accepted_fixtures_validate() {
        assert!(
            IbkrMarketDataProvenanceV1::accepted_fixture()
                .validate(NOW)
                .accepted
        );
        assert!(
            IbkrMarketDataProvenanceV1::accepted_delayed_fixture()
                .validate(NOW)
                .accepted
        );
    }

    #[test]
    fn default_is_fail_closed() {
        let v = IbkrMarketDataProvenanceV1::default().validate(NOW);
        assert!(!v.accepted);
        assert!(v
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::EntitlementStateUnknownDenied));
        assert!(v
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::AdjustmentUnknownDenied));
    }

    #[test]
    fn preimage_excludes_provenance_hash_and_is_deterministic() {
        let mut a = IbkrMarketDataProvenanceV1::accepted_fixture();
        let p1 = a.provenance_hash_preimage();
        // 改 provenance_hash 不動 preimage（排除自指）。
        a.provenance_hash = placeholder_hash('f');
        assert_eq!(p1, a.provenance_hash_preimage());
        // 改 entitlement 態則 preimage 變（溯源錨真綁 entitlement）。
        a.entitlement_state = IbkrMarketDataEntitlementStateV1::Delayed;
        assert_ne!(p1, a.provenance_hash_preimage());
    }

    #[test]
    fn window_out_of_order_and_future_are_blocked() {
        let mut r = IbkrMarketDataProvenanceV1::accepted_fixture();
        r.last_tick_at_ms = r.first_tick_at_ms - 1;
        assert!(r
            .validate(NOW)
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::WindowOutOfOrder));
        let mut r2 = IbkrMarketDataProvenanceV1::accepted_fixture();
        r2.last_tick_at_ms = NOW + 1;
        assert!(r2
            .validate(NOW)
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::LastTickInFuture));
    }

    #[test]
    fn calendar_unbound_sentinel_is_typed_fail_closed() {
        // W6-S4:未綁哨兵 → `CalendarUnbound`（非 `CalendarHashInvalid`）,fail-closed 不 accepted。
        let mut r = IbkrMarketDataProvenanceV1::accepted_fixture();
        r.calendar_hash = IBKR_CALENDAR_HASH_UNBOUND_SENTINEL.to_string();
        let v = r.validate(NOW);
        assert!(!v.accepted);
        assert!(v
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::CalendarUnbound));
        assert!(!v
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::CalendarHashInvalid));
    }

    #[test]
    fn non_sha256_hashes_are_blocked() {
        let mut r = IbkrMarketDataProvenanceV1::accepted_fixture();
        r.instrument_identity_hash = "not-a-hash".to_string();
        assert!(r
            .validate(NOW)
            .blockers
            .contains(&IbkrMarketDataProvenanceBlocker::InstrumentIdentityHashInvalid));
    }
}
