//! MODULE_NOTE
//! 模塊用途：`ibkr_tws_contract_data` 的 **support 子模塊**（2000 行帽拆檔;非獨立面）——
//!   承載 W6-S1 contract details 消化層的純 codec/查詢/門控表/雜湊面:OUT v8 builder +
//!   全限定查詢型、per-field serverVersion 門控表、欄位游標、identity_hash 鑄造、
//!   longName unicode-escape 最小實作、staleness 投影與 wire 純 helper。
//! 依賴：父模塊型別（`ContractDataReject`/`SubPhase`）、`ibkr_tws_wire` codec、
//!   `openclaw_types` 契約、`sha2`/`hex`。
//! 硬邊界：與父模塊同一 typed fail-closed 紀律（不 panic、不捏值、不默認）;無 socket、
//!   無 I/O、無狀態——本檔只有純函數/純資料,狀態機恆在父模塊。

use std::time::Duration;

use sha2::{Digest, Sha256};

use openclaw_types::{is_normalized_symbol, IbkrInstrumentIdentityRowV1};

use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_wire::{encode_fields_checked, encode_frame, CodecError};

use super::{ContractDataReject, SubPhase};

// ===========================================================================
// OUT 常數 + 全限定查詢 + v8 builder（IB 現勘 2026-07-17 pinned;官方 ibapi
// 9.81.1.post1 sdist）
// 注:OUT 與 IN 是兩個獨立編號空間,9 撞值（OUT reqContractDetails=9 vs IN nextValidId=9）
// ——IN 空間常數居 `ibkr_tws_wire`（`IN_*`）,此處為 OUT 空間（`OUT_*`）,命名帶方向防混用。
// ===========================================================================

/// OUT 9:reqContractDetails（唯讀識別查詢）。
pub(crate) const OUT_REQ_CONTRACT_DATA_MSG_ID: &str = "9";
/// reqContractDetails 的 wire VERSION 欄（IB 現勘:v8,17 欄 body）。
const CONTRACT_DATA_OUT_VERSION: &str = "8";

/// 全限定 STK 查詢（伺服端對模糊查詢有遞增 hold → builder 只接受全限定形;`begin_*` 以
/// `QueryNotFullyQualified` typed 拒不合格查詢）。secType 恆 STK、currency 恆 USD、
/// includeExpired 恆 false——lane 白名單於出站即定界,非僅入站拒。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ContractDetailsQuery {
    /// conId 直查（`Some(>0)` 即全限定,symbol/exchange 可空作輔欄）。
    pub con_id: Option<i64>,
    /// 標的代碼（無 conId 時必填且過規範化;與 exchange 併為全限定）。
    pub symbol: String,
    /// 路由交易所（無 conId 時必填;慣例 `SMART`）。
    pub exchange: String,
    /// 主上市交易所（可選消歧欄;可空）。
    pub primary_exchange: String,
}

impl ContractDetailsQuery {
    /// 全限定判據:conId>0,或 規範化 symbol + 非空 exchange（+STK/USD 由 builder 恆定）。
    pub(crate) fn is_fully_qualified(&self) -> bool {
        match self.con_id {
            Some(id) if id > 0 => true,
            Some(_) => false,
            None => is_normalized_symbol(&self.symbol) && !self.exchange.trim().is_empty(),
        }
    }
}

/// encode reqContractDetails：framed v8 17 欄 body（IB 現勘欄位序）
/// `[9, 8, reqId, conId, symbol, secType, lastTradeDateOrContractMonth, strike, right,
/// multiplier, exchange, primaryExchange, currency, localSymbol, tradingClass,
/// includeExpired, secIdType, secId]`——STK 全限定:secType 恆 `"STK"`、currency 恆
/// `"USD"`、includeExpired 恆 `"0"`（false）、期權/期貨欄恆空（strike 按 ibapi 送 `"0"`）。
///
/// **E2-F1**:caller 供給欄（symbol/exchange/primaryExchange）經 `encode_fields_checked`——
/// 內嵌 NUL / 非 ASCII → typed `CodecError::OutboundFieldInvalid`,絕不送出被注入的 frame
/// （`is_fully_qualified` 的 symbol 規範化只覆 conId=None 路徑,conId 直查路徑的自由欄由此
/// builder 校驗兜底）。
pub(crate) fn encode_req_contract_details(
    req_id: i64,
    query: &ContractDetailsQuery,
) -> Result<Vec<u8>, CodecError> {
    let rid = req_id.to_string();
    let cid = query.con_id.unwrap_or(0).to_string();
    Ok(encode_frame(&encode_fields_checked(&[
        OUT_REQ_CONTRACT_DATA_MSG_ID,
        CONTRACT_DATA_OUT_VERSION,
        &rid,
        &cid,
        &query.symbol,
        "STK",
        "",  // lastTradeDateOrContractMonth（STK 無到期）
        "0", // strike（ibapi 對 unset 送 0）
        "",  // right
        "",  // multiplier
        &query.exchange,
        &query.primary_exchange,
        "USD",
        "",  // localSymbol
        "",  // tradingClass
        "0", // includeExpired=false（lane 只承現行上市 instrument）
        "",  // secIdType
        "",  // secId
    ])?))
}

// ===========================================================================
// per-field serverVersion 門控表（IB 現勘 2026-07-17 pinned;IN 10 尾段欄按協商 sv 出現/
// 缺席——表必須實作,否則 sv∈[145,151] 等 band 內按位消費必錯位）。
// ===========================================================================

/// mdSizeMultiplier 欄門檻（head 位 13）。
pub(crate) const SV_GATE_MD_SIZE_MULTIPLIER: i32 = 110;
/// aggGroup 欄門檻（secIdList 後位 31）。
pub(crate) const SV_GATE_AGG_GROUP: i32 = 121;
/// underSymbol/underSecType 欄門檻（位 32-33）。
pub(crate) const SV_GATE_UNDER_SYMBOL_SECTYPE: i32 = 122;
/// marketRuleIds 欄門檻（位 34）。
pub(crate) const SV_GATE_MARKET_RULE_IDS: i32 = 126;
/// realExpirationDate 欄門檻（位 35）。
pub(crate) const SV_GATE_REAL_EXPIRATION_DATE: i32 = 134;
/// stockType 欄門檻（位 36;ETF|COMMON 判別源——sv<152 缺席=UnknownDenied 契約拒）。
pub(crate) const SV_GATE_STOCK_TYPE: i32 = 152;
/// longName unicode-escape 解碼門檻（sv≥153 起 server 以 `\uXXXX` 轉義送非 ASCII——
/// 漏解=靜默 mojibake）。
pub(crate) const SV_GATE_LONG_NAME_UNICODE_ESCAPE: i32 = 153;

/// per-field 門控判據（協商 sv ≥ 門檻 → 該欄在 wire 上出現/該行為生效）。
pub(crate) fn sv_gate(server_version: i32, gate: i32) -> bool {
    server_version >= gate
}

// ===========================================================================
// 純 helper（欄位游標 / identity_hash / unicode-escape / staleness / wire 紀律）
// ===========================================================================

/// 欄位游標:按位消費 + 缺欄 typed 拒（fail-closed:欄不夠=wire 損壞,不猜、不補默認）。
pub(crate) struct FieldCursor<'a> {
    fields: &'a [String],
    idx: usize,
}

impl<'a> FieldCursor<'a> {
    pub(crate) fn new(fields: &'a [String], start: usize) -> Self {
        Self { fields, idx: start }
    }

    pub(crate) fn take(&mut self) -> Result<&'a str, ContractDataReject> {
        match self.fields.get(self.idx) {
            Some(f) => {
                self.idx += 1;
                Ok(f.as_str())
            }
            None => Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                "contract data frame truncated (field missing)",
            ))),
        }
    }

    pub(crate) fn remaining(&self) -> usize {
        self.fields.len().saturating_sub(self.idx)
    }
}

/// identity_hash 鑄造:sha256(preimage) → 64 lowercase hex。preimage 是契約純函數
/// （單一定義點,PIT 可重建——重放端以同 row 重建必得同 hash）;雜湊計算居 engine
/// （types crate 無雜湊依賴,契約只驗 shape）。
pub(crate) fn compute_identity_hash(row: &IbkrInstrumentIdentityRowV1) -> String {
    let mut hasher = Sha256::new();
    hasher.update(row.identity_hash_preimage().as_bytes());
    hex::encode(hasher.finalize())
}

/// longName unicode-escape **最小實作**（sv≥153;IB 現勘:server 以 escape 形送非 ASCII,
/// 漏解=靜默 mojibake）。按 ibapi `unicode-escape` 語義取最小子集:`\uXXXX`（4 hex）→
/// 對應 char、`\\` → `\`;其餘 backslash 序列與孤尾 `\` **原樣保留**（保真優先,不擴大
/// 轉義面——完整 Python unicode-escape 含八進位/`\x` 等,STK longName 實務只出現 `\u`;
/// 非法 `\uXXXX`（hex 不足/surrogate 無法成 char）原樣保留,不 panic、不捏值）。
pub(crate) fn decode_unicode_escape_minimal(raw: &str) -> String {
    let bytes = raw.as_bytes();
    let mut out = String::with_capacity(raw.len());
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] == b'\\' && i + 1 < bytes.len() {
            match bytes[i + 1] {
                b'u' if i + 6 <= bytes.len() => {
                    let hex = &raw[i + 2..i + 6];
                    match u32::from_str_radix(hex, 16).ok().and_then(char::from_u32) {
                        Some(c) => {
                            out.push(c);
                            i += 6;
                            continue;
                        }
                        None => {
                            // 非法 escape:原樣保留(保真,不猜)。
                            out.push('\\');
                            i += 1;
                            continue;
                        }
                    }
                }
                b'\\' => {
                    out.push('\\');
                    i += 2;
                    continue;
                }
                _ => {
                    out.push('\\');
                    i += 1;
                    continue;
                }
            }
        }
        // wire 已由 decode_fields 限 ASCII → 單位元組步進安全。
        out.push(bytes[i] as char);
        i += 1;
    }
    out
}

/// 相位 + 最後更新時刻 → typed staleness（同構 W5-S2 `staleness_of`——該 fn 為模塊私有,
/// 此處同義複刻,不越界改動 account_data）。
pub(crate) fn staleness_of(
    phase: SubPhase,
    last_update_ms: u64,
    stale_after: Duration,
    now_ms: u64,
) -> SnapshotStaleness {
    match phase {
        SubPhase::Idle => SnapshotStaleness::NotSubscribed,
        SubPhase::SnapshotIncomplete => SnapshotStaleness::SnapshotIncomplete,
        SubPhase::Invalidated => SnapshotStaleness::Invalidated,
        SubPhase::DisconnectedStale => SnapshotStaleness::DisconnectedStale,
        SubPhase::Live => {
            let age_ms = now_ms.saturating_sub(last_update_ms);
            if age_ms > stale_after.as_millis() as u64 {
                SnapshotStaleness::Stale {
                    as_of_ms: last_update_ms,
                    age_ms,
                }
            } else {
                SnapshotStaleness::Fresh {
                    as_of_ms: last_update_ms,
                }
            }
        }
    }
}

/// wire 幣別 → lane 白名單（USD 精確匹配;表外 → `UnknownDenied`,契約 `validate()` 拒。
/// 同構 W5-S2/S3 `classify_wire_currency`——該 fn 為模塊私有,同義複刻不越界改動）。
pub(crate) fn classify_wire_currency(raw: &str) -> openclaw_types::StockEtfCurrency {
    match raw {
        "USD" => openclaw_types::StockEtfCurrency::Usd,
        _ => openclaw_types::StockEtfCurrency::UnknownDenied,
    }
}

/// 欄位 0 的 msgId 斷言（非數字/錯 id → `WireMalformed`,不猜、不容錯位;同構 W5-S2/S3）。
pub(crate) fn expect_msg_id(raw: &str, expected: i64) -> Result<(), ContractDataReject> {
    let got = parse_i64(raw, "msg_id")?;
    if got != expected {
        return Err(ContractDataReject::WireMalformed(
            CodecError::UnexpectedMsgId { got },
        ));
    }
    Ok(())
}

/// 數字欄 parse（非數字 → `WireMalformed(NonNumericField)`,禁 `unwrap_or(0)` 捏造;
/// 同構 W5-S2/S3）。
pub(crate) fn parse_i64(raw: &str, field: &'static str) -> Result<i64, ContractDataReject> {
    raw.parse::<i64>()
        .map_err(|_| ContractDataReject::WireMalformed(CodecError::NonNumericField(field)))
}
