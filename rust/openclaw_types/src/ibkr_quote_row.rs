//! IBKR **W6-S3 quote (L1 tick) row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W6-S3 交付的**行契約層**：`reqMktData` 的 L1 tick（TICK_PRICE/TICK_SIZE 家族）
//! 單筆 typed 承載 shape,供 W6-S3 消化層（`ibkr_tws_market_data`）填值——「先契約後消化,
//! 禁裸 map」。不開 socket、不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;純資料 +
//! 純函數（`validate()` 零副作用）。
//!
//! **tickType 白名單紀律（fail-closed）**：L1 quote lane 只承 BID/ASK/LAST 三邏輯欄的
//! price/size 六種 realtime tickType（wire id 1/2/4/0/3/5,IB `TickType`）+ 其 delayed
//! 對映六種（wire id 66-71,`DELAYED_*`;IB 現勘 2026-07-17）。表外 tickType（HIGH/LOW/
//! VOLUME/greeks/option…）一律 `UnknownDenied` 拒——lane v1 只承 L1 報價/量,擴充須 IB 現勘。
//!
//! **delayed provenance 強制紀律（QC 紅線）**：delayed tickType（66-71）映射到正規欄位時
//! **必攜 `entitlement = Delayed`**,禁與 realtime（1-5）同標;realtime tickType 必攜
//! `Realtime`。任何 tickType 與 entitlement 不一致=`EntitlementProvenanceMismatch` blocker
//! （fail-closed:delayed 值被當 realtime 消費=下游決策讀到 15-20 分鐘前的價=實質數據謊言）。
//!
//! **配對守衛（pairing invariant）**：每個 delayed tickType 的 `logical_field()` 必等於其
//! realtime 對應的 `logical_field()`（delayed 只改 entitlement 與時效,不改邏輯語義）——
//! 由 `test_pairing_*` 與 structure 守衛雙鎖,確保 delayed↔realtime 映射完整且一致。
//!
//! **值保真紀律**：price 一律定點字串（嚴格正;禁 f64——浮點在對齊/雜湊上非確定性);size
//! 一律非負整數字串（bid_size 可為 0=無掛單,非錯誤)。`value_decimal` 依 `value_kind()`
//! 走 price 或 size 校驗。時間戳/序列語義同 W6-S1:wire tick 不自帶 per-row 時間戳,
//! `captured_at_ms`/`seq` 為消化層 client 側捕捉時鐘與訂閱單調序列;`validate(now_ms)`
//! 注入時鐘校驗 captured_at 非零且不在未來（fixture 用相對時鐘,禁硬編當前日期）。

use serde::{Deserialize, Serialize};

use crate::ibkr_account_summary_row::{is_nonnegative_decimal_string, is_positive_decimal_string};
use crate::ibkr_positions_row::is_normalized_symbol;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_QUOTE_ROW_CONTRACT_ID: &str = "ibkr_quote_row_v1";

/// tick 值的物理型別（price=定點嚴格正 / size=非負整數）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTickValueKind {
    /// 報價（定點字串;嚴格正）。
    Price,
    /// 數量（非負整數字串;0=無掛單合法）。
    Size,
}

/// L1 邏輯欄（BID/ASK/LAST 各含 price 與 size 邊）。delayed 與 realtime 共用同一 logical
/// field——**配對守衛的錨**。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrQuoteFieldV1 {
    Bid,
    Ask,
    Last,
    BidSize,
    AskSize,
    LastSize,
}

/// tick 的 entitlement provenance（realtime=live 訂閱 / delayed=15-20min 延遲免費檔）。
/// **Qc 紅線**:delayed tickType 映射到正規欄位時必攜 `Delayed`,禁與 realtime 同標。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTickEntitlementV1 {
    /// realtime（tickType 1-5;live/frozen 檔位）。
    Realtime,
    /// delayed（tickType 66-71;delayed/delayed-frozen 檔位,15-20 分鐘延遲）。
    Delayed,
}

/// L1 quote tickType 白名單枚舉（realtime 六 + delayed 六;表外/缺席=`UnknownDenied` 拒）。
/// wire id 出典:IB `TickType`（realtime BID_SIZE=0/BID=1/ASK=2/ASK_SIZE=3/LAST=4/
/// LAST_SIZE=5;delayed DELAYED_BID=66..DELAYED_LAST_SIZE=71,IB 現勘 2026-07-17）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTickTypeV1 {
    // ---- realtime（1-5,0）----
    Bid,
    Ask,
    Last,
    BidSize,
    AskSize,
    LastSize,
    // ---- delayed（66-71）----
    DelayedBid,
    DelayedAsk,
    DelayedLast,
    DelayedBidSize,
    DelayedAskSize,
    DelayedLastSize,
    /// 契約 default / 白名單外 wire id 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrTickTypeV1 {
    fn default() -> Self {
        Self::UnknownDenied
    }
}

impl IbkrTickTypeV1 {
    /// wire tickType id → 白名單枚舉（**精確匹配**;表外一律 `UnknownDenied`）。
    pub fn classify_wire_tick_type(id: i64) -> Self {
        match id {
            1 => Self::Bid,
            2 => Self::Ask,
            4 => Self::Last,
            0 => Self::BidSize,
            3 => Self::AskSize,
            5 => Self::LastSize,
            66 => Self::DelayedBid,
            67 => Self::DelayedAsk,
            68 => Self::DelayedLast,
            69 => Self::DelayedBidSize,
            70 => Self::DelayedAskSize,
            71 => Self::DelayedLastSize,
            _ => Self::UnknownDenied,
        }
    }

    /// 白名單枚舉 → wire tickType id（`UnknownDenied` → `None`;round-trip 測試面）。
    pub fn as_wire_tick_type(&self) -> Option<i64> {
        Some(match self {
            Self::Bid => 1,
            Self::Ask => 2,
            Self::Last => 4,
            Self::BidSize => 0,
            Self::AskSize => 3,
            Self::LastSize => 5,
            Self::DelayedBid => 66,
            Self::DelayedAsk => 67,
            Self::DelayedLast => 68,
            Self::DelayedBidSize => 69,
            Self::DelayedAskSize => 70,
            Self::DelayedLastSize => 71,
            Self::UnknownDenied => return None,
        })
    }

    /// 邏輯欄投影（**配對守衛錨**:delayed 與其 realtime 對應必回同值;`UnknownDenied` → `None`）。
    pub fn logical_field(&self) -> Option<IbkrQuoteFieldV1> {
        use IbkrQuoteFieldV1 as F;
        Some(match self {
            Self::Bid | Self::DelayedBid => F::Bid,
            Self::Ask | Self::DelayedAsk => F::Ask,
            Self::Last | Self::DelayedLast => F::Last,
            Self::BidSize | Self::DelayedBidSize => F::BidSize,
            Self::AskSize | Self::DelayedAskSize => F::AskSize,
            Self::LastSize | Self::DelayedLastSize => F::LastSize,
            Self::UnknownDenied => return None,
        })
    }

    /// entitlement provenance（realtime 1-5 → `Realtime`;delayed 66-71 → `Delayed`;
    /// `UnknownDenied` → `None`）。delayed provenance 強制的判源。
    pub fn entitlement(&self) -> Option<IbkrTickEntitlementV1> {
        use IbkrTickEntitlementV1 as E;
        Some(match self {
            Self::Bid | Self::Ask | Self::Last | Self::BidSize | Self::AskSize | Self::LastSize => {
                E::Realtime
            }
            Self::DelayedBid
            | Self::DelayedAsk
            | Self::DelayedLast
            | Self::DelayedBidSize
            | Self::DelayedAskSize
            | Self::DelayedLastSize => E::Delayed,
            Self::UnknownDenied => return None,
        })
    }

    /// 值的物理型別（price/size;`UnknownDenied` → `None`）。
    pub fn value_kind(&self) -> Option<IbkrTickValueKind> {
        use IbkrQuoteFieldV1 as F;
        use IbkrTickValueKind as K;
        Some(match self.logical_field()? {
            F::Bid | F::Ask | F::Last => K::Price,
            F::BidSize | F::AskSize | F::LastSize => K::Size,
        })
    }
}

/// L1 tick 單筆 typed 契約（W6-S3 消化層的唯一合法承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrQuoteRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// IBKR contract id（主鍵;正整數;由 W6-S1 identity 快照解出）。
    pub con_id: i64,
    /// 標的代碼（規範化;沿 W5-S1/W6-S1 row 家族）。
    pub symbol: String,
    /// 訂閱 reqId（per-reqId entitlement 綁定的鍵;正整數）。
    pub req_id: i64,
    /// tick 型別白名單（`UnknownDenied` 即 blocker）。
    pub tick_type: IbkrTickTypeV1,
    /// tick 值（price=定點嚴格正 / size=非負整數;依 `tick_type.value_kind()` 校驗;禁 f64）。
    pub value_decimal: String,
    /// entitlement provenance（**必與 `tick_type.entitlement()` 一致**——QC 紅線,
    /// mismatch=blocker）。
    pub entitlement: IbkrTickEntitlementV1,
    /// 消化層 client 側捕捉時間戳（epoch ms;非零且 ≤ validate 注入的 now_ms）。
    pub captured_at_ms: u64,
    /// 消化層訂閱單調序列（非零）。
    pub seq: u64,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrQuoteRowV1 {
    /// fail-closed 預設（空 id / 未知 tickType / 空值 / 零時間戳——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            con_id: 0,
            symbol: String::new(),
            req_id: 0,
            tick_type: IbkrTickTypeV1::UnknownDenied,
            value_decimal: String::new(),
            entitlement: IbkrTickEntitlementV1::Realtime,
            captured_at_ms: 0,
            seq: 0,
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrQuoteRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;realtime BID price）。時間戳為任意非零
    /// 占位（無牆鐘依賴;`validate(now_ms)` 以 ≥ 此值的注入時鐘呼叫）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_QUOTE_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            con_id: 756733,
            symbol: "SPY".to_string(),
            req_id: 101,
            tick_type: IbkrTickTypeV1::Bid,
            value_decimal: "512.34".to_string(),
            entitlement: IbkrTickEntitlementV1::Realtime,
            captured_at_ms: 123_456_789,
            seq: 1,
            order_routed: false,
            secret_content_serialized: false,
        }
    }

    /// 可通過校驗的 delayed fixture（acceptance:delayed provenance 正確標記的 BID）。
    pub fn accepted_delayed_fixture() -> Self {
        Self {
            tick_type: IbkrTickTypeV1::DelayedBid,
            entitlement: IbkrTickEntitlementV1::Delayed,
            ..Self::accepted_fixture()
        }
    }

    /// 行級校驗（零副作用;fail-closed）。`now_ms` 注入時鐘（captured_at 不得在未來;fixture
    /// 用相對時鐘,禁硬編當前日期）。
    pub fn validate(&self, now_ms: u64) -> IbkrQuoteRowVerdict {
        use IbkrQuoteRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_QUOTE_ROW_CONTRACT_ID {
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
        if self.tick_type == IbkrTickTypeV1::UnknownDenied {
            blockers.push(B::TickTypeUnknownDenied);
        }
        // 值型別依 tickType 走 price/size 校驗（UnknownDenied 已計 blocker,此處跳過值判）。
        match self.tick_type.value_kind() {
            Some(IbkrTickValueKind::Price) => {
                if !is_positive_decimal_string(&self.value_decimal) {
                    blockers.push(B::PriceValueInvalid);
                }
            }
            Some(IbkrTickValueKind::Size) => {
                // size 非負整數（0=無掛單合法;禁小數/負/空）。
                if !is_nonnegative_decimal_string(&self.value_decimal)
                    || self.value_decimal.contains('.')
                {
                    blockers.push(B::SizeValueInvalid);
                }
            }
            None => {}
        }
        // **delayed provenance 強制（QC 紅線）**:entitlement 必與 tickType 的 entitlement 一致。
        if let Some(expected) = self.tick_type.entitlement() {
            if expected != self.entitlement {
                blockers.push(B::EntitlementProvenanceMismatch);
            }
        }
        if self.captured_at_ms == 0 {
            blockers.push(B::CapturedAtMissing);
        } else if self.captured_at_ms > now_ms {
            blockers.push(B::CapturedAtInFuture);
        }
        if self.seq == 0 {
            blockers.push(B::SeqMissing);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrQuoteRowVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrQuoteRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrQuoteRowBlocker>,
}

impl IbkrQuoteRowVerdict {
    pub fn new(blockers: Vec<IbkrQuoteRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed;封閉枚舉）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrQuoteRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ConIdInvalid,
    SymbolInvalid,
    ReqIdInvalid,
    TickTypeUnknownDenied,
    PriceValueInvalid,
    SizeValueInvalid,
    /// **delayed provenance 強制**:entitlement 與 tickType 不一致（delayed 值被當 realtime
    /// 消費=數據謊言;fail-closed）。
    EntitlementProvenanceMismatch,
    CapturedAtMissing,
    CapturedAtInFuture,
    SeqMissing,
    OrderRouted,
    SecretContentSerialized,
}

#[cfg(test)]
mod tests {
    use super::*;

    const NOW: u64 = 1_000_000_000;

    #[test]
    fn accepted_fixtures_validate() {
        assert!(IbkrQuoteRowV1::accepted_fixture().validate(NOW).accepted);
        assert!(
            IbkrQuoteRowV1::accepted_delayed_fixture()
                .validate(NOW)
                .accepted
        );
    }

    #[test]
    fn default_is_fail_closed() {
        assert!(!IbkrQuoteRowV1::default().validate(NOW).accepted);
    }

    #[test]
    fn wire_tick_type_whitelist_and_roundtrip() {
        for id in [0, 1, 2, 3, 4, 5, 66, 67, 68, 69, 70, 71] {
            let t = IbkrTickTypeV1::classify_wire_tick_type(id);
            assert_ne!(t, IbkrTickTypeV1::UnknownDenied, "id={id} 應在白名單");
            assert_eq!(t.as_wire_tick_type(), Some(id), "round-trip id={id}");
        }
        // 表外（HIGH=6/VOLUME=8/greeks…）拒。
        for id in [6, 7, 8, 9, 14, 45, 72, 88, 90, 100] {
            assert_eq!(
                IbkrTickTypeV1::classify_wire_tick_type(id),
                IbkrTickTypeV1::UnknownDenied
            );
        }
    }

    /// **配對守衛**:每個 delayed tickType 的 logical_field 必等於其 realtime 對應——
    /// delayed 只改 entitlement/時效,不改邏輯語義。同時 entitlement 判源正確。
    #[test]
    fn delayed_realtime_pairing_invariant() {
        let pairs = [
            (IbkrTickTypeV1::Bid, IbkrTickTypeV1::DelayedBid),
            (IbkrTickTypeV1::Ask, IbkrTickTypeV1::DelayedAsk),
            (IbkrTickTypeV1::Last, IbkrTickTypeV1::DelayedLast),
            (IbkrTickTypeV1::BidSize, IbkrTickTypeV1::DelayedBidSize),
            (IbkrTickTypeV1::AskSize, IbkrTickTypeV1::DelayedAskSize),
            (IbkrTickTypeV1::LastSize, IbkrTickTypeV1::DelayedLastSize),
        ];
        for (rt, dl) in pairs {
            assert_eq!(
                rt.logical_field(),
                dl.logical_field(),
                "delayed 與 realtime 必共用 logical_field"
            );
            assert_eq!(rt.value_kind(), dl.value_kind());
            assert_eq!(rt.entitlement(), Some(IbkrTickEntitlementV1::Realtime));
            assert_eq!(dl.entitlement(), Some(IbkrTickEntitlementV1::Delayed));
        }
    }

    #[test]
    fn delayed_provenance_mismatch_is_blocked() {
        // delayed tickType 標成 realtime → EntitlementProvenanceMismatch。
        let mut r = IbkrQuoteRowV1::accepted_delayed_fixture();
        r.entitlement = IbkrTickEntitlementV1::Realtime;
        let v = r.validate(NOW);
        assert!(!v.accepted);
        assert!(v
            .blockers
            .contains(&IbkrQuoteRowBlocker::EntitlementProvenanceMismatch));
    }

    #[test]
    fn size_tick_allows_zero_but_rejects_decimal() {
        let mut r = IbkrQuoteRowV1::accepted_fixture();
        r.tick_type = IbkrTickTypeV1::BidSize;
        r.value_decimal = "0".to_string();
        assert!(r.validate(NOW).accepted, "size 0=無掛單合法");
        r.value_decimal = "1.5".to_string();
        assert!(r
            .validate(NOW)
            .blockers
            .contains(&IbkrQuoteRowBlocker::SizeValueInvalid));
    }

    #[test]
    fn price_tick_rejects_zero_and_future_capture() {
        let mut r = IbkrQuoteRowV1::accepted_fixture();
        r.value_decimal = "0".to_string();
        assert!(r
            .validate(NOW)
            .blockers
            .contains(&IbkrQuoteRowBlocker::PriceValueInvalid));
        let mut r2 = IbkrQuoteRowV1::accepted_fixture();
        r2.captured_at_ms = NOW + 1;
        assert!(r2
            .validate(NOW)
            .blockers
            .contains(&IbkrQuoteRowBlocker::CapturedAtInFuture));
    }
}
