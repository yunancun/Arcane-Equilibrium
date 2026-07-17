//! IBKR **W6-S2 trading calendar 契約**（`ibkr_trading_calendar_v1`;source-only,Rust 為
//! authority）。
//!
//! 本檔是 W6-S2 交付的**日曆結果契約層**：把 W6-S1 identity row 的 `trading_hours`/
//! `liquid_hours`/`time_zone_id` 原字串,解析成有序、DST-aware、可重建的 typed 日曆——供
//! W6-S3 provenance 的 `calendar_hash` 綁真值、W6-S4 regime overlay 綁交易窗。不開 socket、
//! 不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;純資料 + 純函數（`validate()` 零副
//! 作用）。**雙 grammar 解析、legacy→IANA 映射、DST 時刻計算**歸 engine 解析器
//! （`ibkr_trading_calendar` 消化層,需 chrono-tz/sha2）——本契約只承載解析結果 + 驗 shape。
//!
//! **fail-closed 紀律**：engine 解析器對未識別 grammar / 未知 timeZoneId / 非法日期 一律回
//! typed blocker（`GrammarUnrecognized`/`TimeZoneUnknownDenied`/`DateInvalid`）而**不產**
//! 日曆——不靜默默認 `America/New_York`、不猜格式。本契約 `validate()` 為 defense-in-depth,
//! 再驗結構不變量（session 有序、Open 時刻關係、非空、hash shape、負空間束）。
//!
//! **time_zone_iana 紀律**：本欄為 engine 映射 legacy→IANA **後**的規範化 IANA 名（如
//! `America/New_York`）——契約不承載 legacy 名（`US/Eastern`/`EST`）,禁殘留;engine 映射
//! 失敗即 `TimeZoneUnknownDenied` 不建曆。
//!
//! **calendar_hash（PIT 可重建）**：sha256（64 lowercase hex）over `calendar_hash_preimage()`
//! 的規範化 session 集——preimage 為本檔純函數（單一定義點,engine/重放端共用),雜湊計算歸
//! engine（本 crate 無雜湊依賴,契約只驗 shape `is_sha256_hex`）。同一 hours 字串 + tz 於任何
//! 端重建必得同 hash,供 provenance calendar_hash 綁定。
//!
//! **時刻語義**：`open_ms`/`close_ms` 為 epoch ms 絕對時刻（engine 以 chrono-tz 依 IANA tz +
//! DST 由本地時算得;跨午夜 session 的 `close_ms` 已解成次日絕對時刻,恆 `close_ms > open_ms`）。
//! `Closed` 全休日兩者恆 0。半日=較短 session 區段,不特殊標記(UNVERIFIED:官方未明文
//! 「half-day」字樣,屬推論,EA4 遇真半日校驗)。

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_positions_row::is_normalized_symbol;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（engine 解析器 / cross-surface parity 對齊）。
pub const IBKR_TRADING_CALENDAR_CONTRACT_ID: &str = "ibkr_trading_calendar_v1";

/// engine 解析器對「未知 timeZoneId」寫入的哨兵 IANA 值（fail-closed:`validate()` 必拒）。
/// 為什麼要哨兵而非空:令「解析器判未知」與「欄位漏填」在 telemetry 上可區分,兩者皆拒。
pub const CALENDAR_TZ_UNKNOWN_DENIED_SENTINEL: &str = "UNKNOWN_DENIED";

/// 解析目標:liquidHours(RTH)或 tradingHours(全時段)。v1 姿態聚焦 RTH,同解析器複用。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrCalendarHoursKindV1 {
    /// liquidHours = 常規交易時段(RTH)。
    Rth,
    /// tradingHours = 全時段(含盤前盤後)。
    Trading,
}

impl Default for IbkrCalendarHoursKindV1 {
    fn default() -> Self {
        // 預設 RTH(v1 主目標);非 fail-closed 判別欄,故不設 unknown。
        Self::Rth
    }
}

impl IbkrCalendarHoursKindV1 {
    /// 規範化 wire 投影(preimage 用)。
    pub fn as_wire(&self) -> &'static str {
        match self {
            Self::Rth => "rth",
            Self::Trading => "trading",
        }
    }
}

/// 單日 session 狀態(開市 / 全休)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrCalendarSessionKindV1 {
    /// 開市區段(有 open/close 時刻)。
    Open,
    /// 全休日(`日期:CLOSED`;open/close 恆 0)。
    Closed,
}

impl IbkrCalendarSessionKindV1 {
    /// 規範化 wire 投影(preimage 用)。
    pub fn as_wire(&self) -> &'static str {
        match self {
            Self::Open => "open",
            Self::Closed => "closed",
        }
    }
}

/// 單筆日曆 session(engine 解析結果的最小承載;禁裸 tuple)。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrTradingCalendarSessionV1 {
    /// session 所屬日期(`YYYYMMDD` 8 位;engine 解析驗;跨午夜 session 仍記為開市日)。
    pub date: String,
    /// 開市 / 全休。
    pub kind: IbkrCalendarSessionKindV1,
    /// 開市絕對時刻(epoch ms;`Closed` 恆 0)。
    pub open_ms: u64,
    /// 收市絕對時刻(epoch ms;`Closed` 恆 0;`Open` 恆 `> open_ms`,跨午夜已解成次日)。
    pub close_ms: u64,
}

/// W6-S2 交易日曆 typed 契約(engine 解析器的唯一合法承載;禁裸 map)。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrTradingCalendarV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定(恆 `StockEtfCash`)。
    pub asset_lane: AssetLane,
    /// broker 綁定(恆 `Ibkr`)。
    pub broker: Broker,
    /// IBKR contract id(主鍵;正整數;綁 identity row)。
    pub con_id: i64,
    /// 標的代碼(規範化)。
    pub symbol: String,
    /// 解析目標(RTH / Trading)。
    pub hours_kind: IbkrCalendarHoursKindV1,
    /// 規範化 IANA 時區名(engine 映射 legacy→IANA 後填;禁 legacy 殘留;未知=哨兵拒)。
    pub time_zone_iana: String,
    /// 有序 session 列(依日期/時刻遞增;engine 解析器保序)。
    pub sessions: Vec<IbkrTradingCalendarSessionV1>,
    /// 日曆雜湊(sha256 64 hex over `calendar_hash_preimage()`;計算歸 engine,契約驗 shape)。
    pub calendar_hash: String,
    // ---- 負空間安全束(日曆為唯讀事實,恆 false)----
    /// 日曆承載過程永不路由訂單。
    pub order_routed: bool,
    /// 日曆永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrTradingCalendarV1 {
    /// fail-closed 預設(空 id / 空 tz / 無 session / 空 hash——校驗必拒)。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            con_id: 0,
            symbol: String::new(),
            hours_kind: IbkrCalendarHoursKindV1::Rth,
            time_zone_iana: String::new(),
            sessions: Vec::new(),
            calendar_hash: String::new(),
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrTradingCalendarV1 {
    /// 可通過校驗的代表 fixture(acceptance 基線;兩開市日 RTH,固定過去日期為 payload 資料
    /// 非牆鐘)。時刻為任意遞增占位(engine 真值由 chrono-tz 算);hash 為 64 hex 占位。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_TRADING_CALENDAR_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            con_id: 756733,
            symbol: "SPY".to_string(),
            hours_kind: IbkrCalendarHoursKindV1::Rth,
            time_zone_iana: "America/New_York".to_string(),
            sessions: vec![
                IbkrTradingCalendarSessionV1 {
                    date: "20260302".to_string(),
                    kind: IbkrCalendarSessionKindV1::Open,
                    open_ms: 1_772_000_000_000,
                    close_ms: 1_772_020_000_000,
                },
                IbkrTradingCalendarSessionV1 {
                    date: "20260303".to_string(),
                    kind: IbkrCalendarSessionKindV1::Open,
                    open_ms: 1_772_086_400_000,
                    close_ms: 1_772_106_400_000,
                },
            ],
            calendar_hash: placeholder_hash('a'),
            order_routed: false,
            secret_content_serialized: false,
        }
    }

    /// **calendar_hash 規範化 preimage**(單一定義點;PIT 可重建的日曆錨)。
    ///
    /// 為什麼取這個欄集:日曆身分=「哪個 instrument、哪種 hours、哪個 tz、哪些 session」——
    /// con_id/symbol/hours_kind/tz + 逐 session (date|kind|open_ms|close_ms);欄序固定、
    /// `\n` 定界、域前綴防跨契約碰撞。**排除** calendar_hash 自身(避免自指)。同一 hours 字串
    /// 於任何端重建必得同 preimage → 同 hash,供 provenance 綁定。
    pub fn calendar_hash_preimage(&self) -> String {
        let mut parts: Vec<String> = Vec::with_capacity(6 + self.sessions.len());
        parts.push(IBKR_TRADING_CALENDAR_CONTRACT_ID.to_string());
        parts.push(
            match self.broker {
                Broker::Ibkr => "ibkr",
                Broker::Bybit => "bybit",
            }
            .to_string(),
        );
        parts.push(self.con_id.to_string());
        parts.push(self.symbol.clone());
        parts.push(self.hours_kind.as_wire().to_string());
        parts.push(self.time_zone_iana.clone());
        for s in &self.sessions {
            parts.push(format!(
                "{}|{}|{}|{}",
                s.date,
                s.kind.as_wire(),
                s.open_ms,
                s.close_ms
            ));
        }
        parts.join("\n")
    }

    /// 結構校驗(零副作用;defense-in-depth——engine 解析器已於上游拒 grammar/tz/date,本層
    /// 再驗結構不變量:非空 session、日期/時刻有序、Open 時刻關係、tz 非哨兵、hash shape、
    /// 負空間束)。fail-closed:任一違反即 blocker。
    pub fn validate(&self) -> IbkrTradingCalendarVerdict {
        use IbkrTradingCalendarBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_TRADING_CALENDAR_CONTRACT_ID {
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
        // tz:空=漏填;哨兵=解析器判未知——皆 fail-closed 拒(不靜默默認)。
        if self.time_zone_iana.trim().is_empty() {
            blockers.push(B::TimeZoneIdMissing);
        } else if self.time_zone_iana == CALENDAR_TZ_UNKNOWN_DENIED_SENTINEL {
            blockers.push(B::TimeZoneUnknownDenied);
        }
        // 非空 session(空日曆=解析未產出任何日,結構上不可用)。
        if self.sessions.is_empty() {
            blockers.push(B::EmptyCalendar);
        }

        // 逐 session 結構 + 跨 session 有序(date 非遞減;Open 時刻嚴格遞增不重疊)。
        let mut prev_date: Option<&str> = None;
        let mut last_end_ms: u64 = 0;
        for s in &self.sessions {
            if !is_yyyymmdd(&s.date) {
                blockers.push(B::DateInvalid);
            }
            if let Some(pd) = prev_date {
                // YYYYMMDD lexicographic == chronological;日期倒退=亂序。
                if s.date.as_str() < pd {
                    blockers.push(B::SessionOutOfOrder);
                }
            }
            prev_date = Some(&s.date);
            match s.kind {
                IbkrCalendarSessionKindV1::Closed => {
                    // 全休:時刻恆 0(非 0 代表解析語義漏失)。
                    if s.open_ms != 0 || s.close_ms != 0 {
                        blockers.push(B::SessionTimeInvalid);
                    }
                }
                IbkrCalendarSessionKindV1::Open => {
                    // Open:open>0、close>open(跨午夜已解絕對時刻)、且不早於前一段收市(不重疊/不倒退)。
                    if s.open_ms == 0 || s.close_ms <= s.open_ms {
                        blockers.push(B::SessionTimeInvalid);
                    }
                    if s.open_ms < last_end_ms {
                        blockers.push(B::SessionOutOfOrder);
                    }
                    last_end_ms = s.close_ms;
                }
            }
        }

        if !is_sha256_hex(&self.calendar_hash) {
            blockers.push(B::CalendarHashInvalid);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrTradingCalendarVerdict::new(blockers)
    }
}

/// `YYYYMMDD` 8 位純數字淺驗(engine 解析器另有語義日期驗;本層防漏填)。
fn is_yyyymmdd(raw: &str) -> bool {
    raw.len() == 8 && raw.bytes().all(|b| b.is_ascii_digit())
}

/// 校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrTradingCalendarVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrTradingCalendarBlocker>,
}

impl IbkrTradingCalendarVerdict {
    pub fn new(blockers: Vec<IbkrTradingCalendarBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 封閉 blocker 枚舉(engine 解析器 + 本契約 validate 共用;taxonomy 唯一定義點)。
/// 為什麼並列解析側與結構側:解析側(GrammarUnrecognized/TimeZoneUnknownDenied/DateInvalid)
/// 由 engine 於「不產曆」時 emit;結構側(SessionOutOfOrder/SessionTimeInvalid/EmptyCalendar/
/// CalendarHashInvalid/…)由已產曆的 `validate()` 再查——兩路 fail-closed 收斂到同一 typed 面。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTradingCalendarBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ConIdInvalid,
    SymbolInvalid,
    /// timeZoneId 欄漏填(空)。
    TimeZoneIdMissing,
    /// legacy timeZoneId 無法映射到 IANA(engine 解析側 fail-closed 拒;不靜默默認)。
    TimeZoneUnknownDenied,
    /// hours 字串 grammar 未識別(engine 解析側;雙 grammar 皆不match)。
    GrammarUnrecognized,
    /// 日期段非 `YYYYMMDD` 或語義非法(engine 解析側 + 結構淺驗)。
    DateInvalid,
    /// session 日期倒退 / Open 時刻重疊倒退(亂序)。
    SessionOutOfOrder,
    /// Open 時刻關係非法(open=0 / close≤open)或 Closed 帶非零時刻。
    SessionTimeInvalid,
    /// 無任何 session(空日曆)。
    EmptyCalendar,
    /// calendar_hash 非 sha256 64 hex。
    CalendarHashInvalid,
    OrderRouted,
    SecretContentSerialized,
}

/// fixture 用 64 hex 占位(沿 W6-S1/S3 `placeholder_hash` 慣例;真 hash 由 engine 鑄)。
fn placeholder_hash(fill: char) -> String {
    fill.to_string().repeat(64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepted_fixture_validates() {
        assert!(IbkrTradingCalendarV1::accepted_fixture().validate().accepted);
    }

    #[test]
    fn default_is_fail_closed() {
        let v = IbkrTradingCalendarV1::default().validate();
        assert!(!v.accepted);
        assert!(v.blockers.contains(&IbkrTradingCalendarBlocker::ContractIdMismatch));
        assert!(v.blockers.contains(&IbkrTradingCalendarBlocker::EmptyCalendar));
        assert!(v.blockers.contains(&IbkrTradingCalendarBlocker::TimeZoneIdMissing));
        assert!(v.blockers.contains(&IbkrTradingCalendarBlocker::CalendarHashInvalid));
    }

    #[test]
    fn tz_unknown_sentinel_is_denied() {
        let mut c = IbkrTradingCalendarV1::accepted_fixture();
        c.time_zone_iana = CALENDAR_TZ_UNKNOWN_DENIED_SENTINEL.to_string();
        assert!(c
            .validate()
            .blockers
            .contains(&IbkrTradingCalendarBlocker::TimeZoneUnknownDenied));
    }

    #[test]
    fn out_of_order_dates_rejected() {
        let mut c = IbkrTradingCalendarV1::accepted_fixture();
        c.sessions.reverse(); // 日期倒退
        assert!(c
            .validate()
            .blockers
            .contains(&IbkrTradingCalendarBlocker::SessionOutOfOrder));
    }

    #[test]
    fn open_session_time_relationship_enforced() {
        let mut c = IbkrTradingCalendarV1::accepted_fixture();
        c.sessions[0].close_ms = c.sessions[0].open_ms; // close≤open
        assert!(c
            .validate()
            .blockers
            .contains(&IbkrTradingCalendarBlocker::SessionTimeInvalid));
    }

    #[test]
    fn closed_session_must_be_zero_ms() {
        let mut c = IbkrTradingCalendarV1::accepted_fixture();
        c.sessions[1].kind = IbkrCalendarSessionKindV1::Closed; // 但仍帶非零時刻
        assert!(c
            .validate()
            .blockers
            .contains(&IbkrTradingCalendarBlocker::SessionTimeInvalid));
    }

    #[test]
    fn preimage_excludes_calendar_hash_and_binds_sessions() {
        let mut c = IbkrTradingCalendarV1::accepted_fixture();
        let p1 = c.calendar_hash_preimage();
        c.calendar_hash = placeholder_hash('f');
        assert_eq!(p1, c.calendar_hash_preimage()); // 改 hash 不動 preimage
        c.sessions[0].open_ms += 1;
        assert_ne!(p1, c.calendar_hash_preimage()); // 改 session 時刻則 preimage 變
    }
}
