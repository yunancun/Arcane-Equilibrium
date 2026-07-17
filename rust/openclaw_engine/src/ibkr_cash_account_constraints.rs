//! MODULE_NOTE
//! 模塊用途：IBKR **W7-S2 cash 約束引擎（deterministic pre-submit gate）**（IBKR_TODO §5-W7;
//!   設計文檔 §3）。承 root principle「deterministic routing/transforms belong in code」——**純函數
//!   policy engine,非 model judgment**。跑在 **Rust authority accept 之後、order frame build 之前**
//!   （S1 lifecycle driver 產 `OrderFrame` 前的最後一道 cash-correctness 閘）。核心
//!   `evaluate(intent, cash_state, rules, calendar, now_ms)` 窮舉七道 gate,**任一不確定即 fail-closed
//!   拒**（規則缺失 / 快照非新鮮 / decimal 損壞 / 結算日不可算 → 一律拒,絕不放行）。
//! 主要區段：
//!   - (a) `CashAccountRules`：**注入式 config**——T+1 結算 offset / order-type 白名單 / fractional /
//!     LULD 帶寬 / RTH-only。**官方數值全歸 IB 现勘**,引擎只留接口 + 判斷邏輯,default 標 illustrative
//!     （避 R6/R8/R11 憑記憶寫死未證官方政策)。
//!   - (b) 輸入視圖：`CashOrderIntent`（gate 相關欄的精簡投影,消費 openclaw_types 既有枚舉,禁重造）、
//!     `MarketPreTradeState`（halt/LULD/參考價）、`CashAccountState`（settled/unsettled 台帳 + 每 symbol
//!     unsettled-funded 買入 + long positions + W5 `SnapshotStaleness`)、`CashTranche`/`UnsettledFundedBuyLot`。
//!   - (c) typed 裁決：`CashConstraintApproved`（放行 + 計算事實）/ `CashConstraintViolation`（窮舉拒因）。
//!   - (d) `evaluate` + 各 gate 純函數。
//!   - (e) 精確定點 decimal 比較（無 decimal crate → i128 scaled 10^-9;過精度 / 溢位 → fail-closed）
//!     + 交易日 / 結算日曆算術（承 W6 calendar,chrono-tz DST-aware）。
//! 依賴：`openclaw_types`（`StockEtfOrderSide`/`StockEtfPaperOrderType`/`StockEtfPaperTimeInForce`/
//!   `BrokerOperation`/`IbkrTradingCalendarV1`/`IbkrCalendarSessionKindV1`,**純消費不重造契約**)、
//!   `crate::ibkr_tws_account_data::SnapshotStaleness`（承 W5 帳戶面新鮮度)、`chrono`/`chrono-tz`（tz/日期）、
//!   `BTreeMap`（確定序)。
//! 硬邊界：
//!   - **純函數 gate,零 socket / async / send**；不觸 transport seam（INV-ORDER/INV-1 恆 HOLD,S2 不改
//!     order_transport)。純同步、注入時鐘（now_ms）、注入 config（禁 wall-clock 日期腐化 time-bomb)。
//!   - **no-short = 硬邊界**：sell qty > 既有 long → 拒（`ShortSaleDenied`;cash account 禁融券,short 永久
//!     denied——此 gate + S4 `check_effect_contact` operation 白名單雙證）。
//!   - **官方數值不硬編**：T+1 offset / LULD 帶寬 / order-type / RTH 全歸 `CashAccountRules` 注入;引擎不
//!     憑記憶寫死 SEC/GFV/LULD 官方規則值。IB 平行现勘校驗此接口與判斷。
//!   - **default build DCE（W3-W7 B′ 姿態）**：0 production caller（真接線=S4 IPC handler 的 submit gate)
//!     → default artifact DCE。Bybit crypto_perp 不變;無 DB migration;不擴 IPC。

// intentional-DCE 姿態繼承 lifecycle/account_data/transport:本模塊 default build 零 production caller
// （真接線=S4 IPC submit handler 的 cash gate)。allow(dead_code) 保留至 S4 接線移出。
#![allow(dead_code)]

use std::collections::BTreeMap;

use chrono::TimeZone;
use chrono_tz::Tz;

use openclaw_types::{
    BrokerOperation, IbkrCalendarSessionKindV1, IbkrTradingCalendarV1, StockEtfOrderSide,
    StockEtfPaperOrderType, StockEtfPaperTimeInForce,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;

// ===========================================================================
// (a) CashAccountRules — 注入式 config（官方數值全歸 IB 现勘;default 標 illustrative）
// ===========================================================================

/// cash-account 約束規則（**注入式 config**;每項真讀取生效、可觀測——禁假功能）。**官方數值全歸 IB
/// 现勘校驗**：以下 default 皆標 *illustrative*（示意值,非當已證官方事實）,引擎只留接口 + 判斷邏輯,不
/// 憑記憶寫死 SEC/GFV/LULD/RTH/order-type 官方語義。
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct CashAccountRules {
    /// **T+1 結算 offset（business days）**——賣出所得待清算,結算日 = 交易日 + 此 offset 個交易日
    /// （由 W6 calendar 算,見 `settlement_date_for`）。SEC 2024-05-28 生效 T+1 → *illustrative* default=1;
    /// **真值/語義待 IB 现勘**（勿把 SEC 規則數值硬編進判斷邏輯,只當注入參數承載)。
    pub settlement_offset_business_days: u32,
    /// order-type 白名單:是否允 `Gtc`（v1=false,只 `Day`)。承 gate #5「LMT/MKT×DAY」。
    pub allow_gtc: bool,
    /// MOC/LOC opt-in（v1=false）。**forward-reserved**:官方支援但 `StockEtfPaperOrderType` 契約當前只
    /// 有 Market/Limit,MOC/LOC 尚不可表達 → 此旗於契約擴出 MOC/LOC 變體前為 inert（待後續 opt-in)。
    pub allow_moc_loc: bool,
    /// fractional opt-in（v1=false;非整數 qty 拒)。官方 cashQty（sv≥111）支援但列後續 opt-in。
    pub allow_fractional: bool,
    /// **marketable BUY 資金 buffer（basis points）**——MKT 買入無價格上限,pre-submit 以參考價估成本會
    /// 低估（實際成交可 > ref)→ 對 **MKT** 成本**保守上浮** `ref×(1+bps/10000)`,使閘 fail-closed（寧保守
    /// 拒不樂觀放行)。*illustrative* default;**真值待 IB/EA 现勘**（官方 Available-for-Trading 以即時可用
    /// 資金檢查,MKT 以估價保留)。**純 LMT 不套用**——限價即成本上界(見 `gate_buy_settled_funds`)。
    pub marketable_buffer_bps: u32,
    /// **LULD 帶寬百分比**（*approximate-only 保守 sanity,非官方 tier 帶寬*;**待 IB 现勘**)。官方 LULD
    /// 為 tiered（Tier1/2 × 價位分層 × 時段加倍 × 5-min-avg 參考)——單一 f64 **無法承載**,**權威態以 venue
    /// flag `MarketPreTradeState.luld_limit_state`/`halted` 為準**;本欄僅作 marketable 語境的 fat-finger
    /// sanity（見 `gate_luld_halt`,不對 resting limit 定價偏離誤判)。0.05 = ±5%。
    pub luld_band_percent: f64,
    /// 是否啟用 LULD 帶寬 pre-trade filter。啟用但市場資料缺（參考價不可解)→ fail-closed 拒
    /// （`LuldStateUnavailable`;不確定不放行)。venue flag（halt/limit-state)不受此旗影響,恆權威。
    pub luld_filter_enabled: bool,
    /// RTH-only 強制（v1=true;outsideRth 永久關,承 gate #4)。false 時跳過 RTH 閘（僅 config,非 v1 姿態)。
    pub rth_only: bool,
}

impl CashAccountRules {
    /// v1 保守 default（**全欄 illustrative,待 IB 现勘校驗**;非已證官方事實)。
    pub(crate) fn illustrative_v1() -> Self {
        Self {
            settlement_offset_business_days: 1, // T+1;待 IB 现勘
            allow_gtc: false,
            allow_moc_loc: false,
            allow_fractional: false,
            marketable_buffer_bps: 100, // MKT 成本 +1%;illustrative,待 IB/EA 现勘
            luld_band_percent: 0.05,    // ±5% approximate sanity;待 IB 现勘
            luld_filter_enabled: true,
            rth_only: true,
        }
    }
}

// ===========================================================================
// (b) 輸入視圖（消費 openclaw_types 既有枚舉;engine-local 精簡投影,禁重造契約枚舉）
// ===========================================================================

/// cash gate 的訂單意圖投影（S1 lifecycle 意圖 / S4 IPC 請求投影出的 gate 相關欄;
/// **消費 openclaw_types 契約枚舉**——側 / 型別 / TIF 不重造)。`Option` 欄缺失 = 不確定 → fail-closed。
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CashOrderIntent {
    /// 綁定帳號（與 `CashAccountState.account_id` 必相符,否則 `AccountMismatch`)。
    pub account_id: String,
    pub symbol: String,
    /// broker operation（v1 cash gate 只處理 `PaperOrderSubmit`;其餘 → `OperationNotSubmit`,
    /// replace/cancel 的 cash 重核列後續)。
    pub operation: BrokerOperation,
    /// 買 / 賣（`None` 或 `Unknown` → fail-closed)。
    pub side: Option<StockEtfOrderSide>,
    /// 訂單型別（`None` → fail-closed;白名單見 gate #5)。
    pub order_type: Option<StockEtfPaperOrderType>,
    /// 有效期（`None` → fail-closed;白名單見 gate #5)。
    pub time_in_force: Option<StockEtfPaperTimeInForce>,
    /// 下單量（正 decimal 字串;v1 整數,fractional 拒)。
    pub quantity_decimal: String,
    /// 限價（LMT 必填;MKT 空。BUY 成本估算:LMT 用此價)。
    pub limit_price_decimal: String,
    /// 該 symbol 的 pre-trade 市場狀態（halt/LULD/參考價)。
    pub market: MarketPreTradeState,
}

/// 單 symbol 的 pre-trade 市場狀態（LULD/halt filter 輸入;缺市場資料 → fail-closed)。
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct MarketPreTradeState {
    /// 交易暫停 / 熔斷（halt)→ 拒（`TradingHalted`)。
    pub halted: bool,
    /// 場方已標 LULD limit / pause 態（觸帶寬上下限)→ 拒（`LuldBandBreach`)。
    pub luld_limit_state: bool,
    /// 市場資料是否可信（缺 / 過期 → fail-closed;LULD filter 啟用時尤然)。
    pub data_available: bool,
    /// 參考價（LULD 帶寬中心 + MKT 買入成本估算;空 / 非法 → 依 gate fail-closed)。
    pub reference_price_decimal: String,
}

/// 現金 tranche（settled 或 unsettled;各帶結算日"YYYYMMDD")。
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CashTranche {
    /// 金額（decimal 字串;記帳承載)。
    pub amount_decimal: String,
    /// 結算日"YYYYMMDD"（unsettled tranche 待清算日;`≤ 今日` = 已成熟可用)。
    pub settlement_date: String,
}

/// 某 symbol 的 **unsettled-funded 買入**紀錄（GFV/free-riding 正解:官方 GFV = 以**未結算資金**支付的
/// 買入,在**該資金結算前**賣出 = violation;若買入當下已有足額 settled funds 支付即**不構成 GFV**)。
/// 故 GFV 綁「買入的**資金來源** tranche 未結算」而非「買入本身 T+1 未到」——避免誤殺以 settled cash 全額
/// 買入、T+1 結算前的**正當**賣出(官方明文不算 GFV)。**S2 買入閘只放行 settled-funded 買入 → 此 map 於
/// S2 世界恆空**,本閘為對 S3 ledger 的 defense-in-depth(下單前硬拒方向保留,CONFIRMED-conservative)。
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct UnsettledFundedBuyLot {
    /// 以未結算資金支付的買入量（decimal;記帳承載)。
    pub quantity_decimal: String,
    /// **支付該買入的未結算資金 tranche 的結算日**"YYYYMMDD"（`> 今日` = 資金仍未結算 → 此前賣出=GFV)。
    pub funding_settlement_date: String,
}

/// cash-account 快照狀態（**承 W5 帳戶面**:settled/unsettled 現金 + positions + 新鮮度)。
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CashAccountState {
    pub account_id: String,
    /// 已結算現金（可立即用於買入;**可負**——費用/借方餘額,承 W5 `SettledCash` 符號紀律)。
    pub settled_cash_decimal: String,
    /// 未結算 tranche（賣出所得待清算,各帶結算日;結算日 ≤ 今日者於 gate 併回可用資金)。
    pub unsettled_tranches: Vec<CashTranche>,
    /// 每 symbol **unsettled-funded 買入**追蹤（GFV gate;鍵=symbol;語義=以未結算資金支付的買入,見
    /// `UnsettledFundedBuyLot`)。**S2 世界恆空**(買入閘只放行 settled-funded),為 S3 ledger 的 defense。
    pub unsettled_funded_buys: BTreeMap<String, UnsettledFundedBuyLot>,
    /// 既有 long positions（W5 positions;no-short gate:sell qty ≤ 此量;鍵=symbol,值=qty decimal)。
    pub long_positions: BTreeMap<String, String>,
    /// 快照新鮮度（**承 W5 `SnapshotStaleness`**;非 `Fresh` → fail-closed 拒,不對陳舊 / 毒化快照下單)。
    pub staleness: SnapshotStaleness,
}

// ===========================================================================
// (c) typed 裁決（放行帶計算事實;拒因窮舉)
// ===========================================================================

/// 通過全七道 gate 的放行 + 計算事實（S4 IPC 投影 / audit 唯讀消費;禁在放行後另闢繞道)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CashConstraintApproved {
    pub symbol: String,
    pub side: StockEtfOrderSide,
    /// BUY:估算成本（qty × 有效價,decimal 字串);SELL:空。
    pub estimated_cost_decimal: String,
    /// BUY:估算扣款後剩餘可用 settled（decimal);SELL:空。
    pub settled_funds_remaining_decimal: String,
    /// BUY:本單將產生的結算日（交易日 + T+offset business day,由 W6 calendar 算);SELL:空。
    pub projected_settlement_date: String,
    pub evaluated_at_ms: u64,
}

/// cash 約束 typed 拒因（全 typed;呼叫端據此分流,不 panic、不捏值、不默默放行)。窮舉七道 gate +
/// fail-closed 不確定族。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum CashConstraintViolation {
    // ---- fail-closed 不確定族（規則缺失 / 快照不新鮮 / 輸入損壞 → 拒)----
    /// 快照非 `Fresh`（陳舊 / 未完整 / 毒化 / 斷線 → 不對不可信快照下單)。
    #[error("account snapshot not fresh: {staleness:?}")]
    SnapshotNotFresh { staleness: SnapshotStaleness },
    /// intent 帳號與快照帳號不符（不對錯帳戶下單)。
    #[error("intent account does not match snapshot account")]
    AccountMismatch,
    /// intent 必填枚舉欄缺失（side/order_type/tif 為 None 或 side=Unknown)。
    #[error("intent field missing or unknown: {field}")]
    IntentFieldMissing { field: &'static str },
    /// decimal 欄形狀損壞（非數字 / 過精度 / 溢位 → fail-closed,不猜、不截斷)。
    #[error("decimal field malformed: {field}")]
    MalformedDecimal { field: &'static str },
    /// v1 cash gate 只處理 submit（其餘 operation → 拒,replace/cancel cash 重核列後續)。
    #[error("operation {operation:?} is not a paper submit (out of v1 cash-gate scope)")]
    OperationNotSubmit { operation: BrokerOperation },

    // ---- gate #1 settled-funds 台帳（T+1)----
    /// 買入所需 settled cash 不足（買入只用 settled cash + 已成熟 tranche)。
    #[error("insufficient settled funds: required {required} available {available}")]
    SettledFundsInsufficient { required: String, available: String },
    /// 結算日不可算（calendar 前瞻不足 / tz 不可解 → BUY fail-closed:不知結算排程即不下單)。
    #[error("settlement date uncomputable (insufficient calendar or unresolved tz)")]
    SettlementDateUncomputable,

    // ---- gate #2 GFV / free-riding----
    /// 以未結算資金支付的買入,在該資金結算前賣出 = free-riding（good-faith violation;官方 GFV 正解——
    /// 買入當下若已 settled-funded 即不構成)。
    #[error(
        "good-faith / free-riding violation: unsettled-funded buy for {symbol} not yet settled"
    )]
    GfvFreeRidingViolation { symbol: String },

    // ---- gate #3 no-short（硬邊界)----
    /// 賣量超既有 long（cash account 禁融券;short 永久 denied)。
    #[error("short sale denied: sell {requested} exceeds long {long_available}")]
    ShortSaleDenied {
        requested: String,
        long_available: String,
    },

    // ---- gate #4 RTH-only----
    /// 下單時刻不在 regular trading hours（W6 calendar,America/New_York + DST)。
    #[error("order time outside regular trading hours")]
    OutsideRegularTradingHours,

    // ---- gate #5 order-type / TIF 白名單----
    /// 有效期不在白名單（v1 只 `Day`;`Gtc` 需 `allow_gtc`)。
    #[error("time-in-force not whitelisted: {tif:?}")]
    TimeInForceNotWhitelisted { tif: StockEtfPaperTimeInForce },

    // ---- gate #6 fractional----
    /// 非整數 qty（v1 拒;需 `allow_fractional`)。
    #[error("fractional quantity denied (v1 integer-only)")]
    FractionalQuantityDenied,
    /// qty 非正（≤0)。
    #[error("non-positive quantity")]
    NonPositiveQuantity,

    // ---- gate #7 LULD / halt----
    /// 交易暫停 / 熔斷。
    #[error("trading halted")]
    TradingHalted,
    /// 觸 LULD 帶寬（場方 limit 態,或有效價偏離參考價超帶寬)。
    #[error("LULD band breached")]
    LuldBandBreach,
    /// LULD filter 啟用但市場資料缺（參考價不可解 → fail-closed,不確定不放行)。
    #[error("LULD state unavailable (market data missing while filter enabled)")]
    LuldStateUnavailable,
}

// ===========================================================================
// (d) evaluate — 七道 gate 窮舉（fail-closed;任一不確定即拒）
// ===========================================================================

/// **cash 約束引擎主入口**（純函數 deterministic gate;跑在 Rust authority accept 之後、order frame
/// build 之前)。窮舉七道 gate,任一不確定 / 違規即回 typed `Err`;全綠回 `CashConstraintApproved`
/// （帶計算事實)。gate 序:輸入健全性 → operation → 白名單 → fractional → RTH → LULD/halt → 側別
/// （BUY settled-funds + 結算日;SELL no-short + GFV)。
pub(crate) fn evaluate(
    intent: &CashOrderIntent,
    cash_state: &CashAccountState,
    rules: &CashAccountRules,
    calendar: &IbkrTradingCalendarV1,
    now_ms: u64,
) -> Result<CashConstraintApproved, CashConstraintViolation> {
    // ── 0. 輸入健全性（快照新鮮 / 帳號相符 / operation 在範圍) ──
    match cash_state.staleness {
        SnapshotStaleness::Fresh { .. } => {}
        other => return Err(CashConstraintViolation::SnapshotNotFresh { staleness: other }),
    }
    if intent.account_id != cash_state.account_id {
        return Err(CashConstraintViolation::AccountMismatch);
    }
    if intent.operation != BrokerOperation::PaperOrderSubmit {
        return Err(CashConstraintViolation::OperationNotSubmit {
            operation: intent.operation,
        });
    }

    // ── 必填枚舉欄（缺失 = 不確定 → fail-closed) ──
    let side = match intent.side {
        Some(StockEtfOrderSide::Buy) => StockEtfOrderSide::Buy,
        Some(StockEtfOrderSide::Sell) => StockEtfOrderSide::Sell,
        Some(StockEtfOrderSide::Unknown) | None => {
            return Err(CashConstraintViolation::IntentFieldMissing { field: "side" })
        }
    };
    let order_type = intent
        .order_type
        .ok_or(CashConstraintViolation::IntentFieldMissing {
            field: "order_type",
        })?;
    let tif = intent
        .time_in_force
        .ok_or(CashConstraintViolation::IntentFieldMissing {
            field: "time_in_force",
        })?;

    // ── gate #5 order-type / TIF 白名單（LMT/MKT×DAY) ──
    gate_order_type_whitelist(order_type, tif, rules)?;

    // ── gate #6 fractional（v1 整數;qty > 0) ──
    let qty_fixed = gate_quantity(&intent.quantity_decimal, rules)?;

    // ── gate #4 RTH-only ──
    if rules.rth_only {
        gate_rth(calendar, now_ms)?;
    }

    // ── gate #7 LULD / halt pre-trade filter ──
    gate_luld_halt(intent, side, order_type, rules)?;

    // ── 側別 gate ──
    match side {
        StockEtfOrderSide::Buy => gate_buy_settled_funds(
            intent, cash_state, rules, calendar, qty_fixed, order_type, now_ms,
        ),
        StockEtfOrderSide::Sell => gate_sell_no_short_gfv(intent, cash_state, calendar, now_ms),
        StockEtfOrderSide::Unknown => {
            Err(CashConstraintViolation::IntentFieldMissing { field: "side" })
        }
    }
}

/// gate #5:order-type / TIF 白名單。`StockEtfPaperOrderType` 契約當前僅 Market/Limit（皆 v1 白名單;
/// 窮舉 match 使契約擴 MOC/LOC 時編譯期強制重審)。TIF:`Day` 放行,`Gtc` 需 `allow_gtc`。
fn gate_order_type_whitelist(
    order_type: StockEtfPaperOrderType,
    tif: StockEtfPaperTimeInForce,
    rules: &CashAccountRules,
) -> Result<(), CashConstraintViolation> {
    // order_type 白名單:Market/Limit 皆放（窮舉——MOC/LOC 尚不可由契約表達,`allow_moc_loc` 為
    // forward-reserved,契約擴變體前 inert)。
    match order_type {
        StockEtfPaperOrderType::Market | StockEtfPaperOrderType::Limit => {}
    }
    match tif {
        StockEtfPaperTimeInForce::Day => Ok(()),
        StockEtfPaperTimeInForce::Gtc => {
            if rules.allow_gtc {
                Ok(())
            } else {
                Err(CashConstraintViolation::TimeInForceNotWhitelisted { tif })
            }
        }
    }
}

/// gate #6:fractional 拒 + 正量。回 qty 定點值（scaled 10^-9)供成本估算。非整數且未 opt-in → 拒。
fn gate_quantity(
    quantity_decimal: &str,
    rules: &CashAccountRules,
) -> Result<i128, CashConstraintViolation> {
    let qty = parse_fixed(quantity_decimal)
        .ok_or(CashConstraintViolation::MalformedDecimal { field: "quantity" })?;
    if qty <= 0 {
        return Err(CashConstraintViolation::NonPositiveQuantity);
    }
    if !rules.allow_fractional && qty % FIXED_SCALE != 0 {
        return Err(CashConstraintViolation::FractionalQuantityDenied);
    }
    Ok(qty)
}

/// gate #4:RTH-only。now_ms 須落在某 `Open` session `[open_ms, close_ms)` 內（W6 calendar 已解成
/// DST-aware 絕對時刻)。無命中 → 拒（含全休日 / 盤前盤後 / 空曆)。
fn gate_rth(calendar: &IbkrTradingCalendarV1, now_ms: u64) -> Result<(), CashConstraintViolation> {
    let in_session = calendar.sessions.iter().any(|s| {
        s.kind == IbkrCalendarSessionKindV1::Open && now_ms >= s.open_ms && now_ms < s.close_ms
    });
    if in_session {
        Ok(())
    } else {
        Err(CashConstraintViolation::OutsideRegularTradingHours)
    }
}

/// gate #7:LULD / halt pre-trade filter。
/// **權威態 = venue flag**:`halted` → `TradingHalted`;`luld_limit_state`（場方自算 tier 帶寬觸限/暫停)
/// → `LuldBandBreach`（官方 LULD 為 tiered,交易所權威,恆先判)。
/// **本地 `luld_band_percent` = approximate-only 保守 sanity**(非官方帶寬):**僅套用於 marketable 語境**
/// （執行價≈市場價:MKT,或 marketable LMT——買入 limit≥ref / 賣出 limit≤ref)。**resting limit（遠離現價,
/// 如 dip-buy)不以定價偏離誤判 LULD**（LULD 是市場價觸帶事件,非你的限價位置)——修 E2 NOTE-1 誤殺。
/// f64 僅作偏離門檻判別（非記帳,同 S1 dir-guard 紀律)。
fn gate_luld_halt(
    intent: &CashOrderIntent,
    side: StockEtfOrderSide,
    order_type: StockEtfPaperOrderType,
    rules: &CashAccountRules,
) -> Result<(), CashConstraintViolation> {
    let m = &intent.market;
    // ── venue-flag 權威（恆判,不受 luld_filter_enabled 影響)──
    if m.halted {
        return Err(CashConstraintViolation::TradingHalted);
    }
    if m.luld_limit_state {
        return Err(CashConstraintViolation::LuldBandBreach);
    }
    // ── 本地 approximate band sanity（可 config 關;僅 marketable 語境)──
    if !rules.luld_filter_enabled {
        return Ok(());
    }
    // filter 啟用:市場資料不可信 → fail-closed（不確定不放行)。
    if !m.data_available {
        return Err(CashConstraintViolation::LuldStateUnavailable);
    }
    let reference = parse_fixed(&m.reference_price_decimal)
        .ok_or(CashConstraintViolation::LuldStateUnavailable)?;
    if reference <= 0 {
        return Err(CashConstraintViolation::LuldStateUnavailable);
    }
    // 只對 marketable 語境(執行價≈市場)套 band sanity;純 resting limit(遠離現價)不誤判。
    let limit = match order_type {
        StockEtfPaperOrderType::Market => {
            // MKT 執行價≈參考價,無 limit 定價偏離可查;venue flag 已權威承載 → 放行。
            return Ok(());
        }
        StockEtfPaperOrderType::Limit => parse_fixed(&intent.limit_price_decimal).ok_or(
            CashConstraintViolation::MalformedDecimal {
                field: "limit_price",
            },
        )?,
    };
    if limit <= 0 {
        return Err(CashConstraintViolation::MalformedDecimal {
            field: "limit_price",
        });
    }
    // marketable 判定:買入 limit≥ref(會即時觸市) / 賣出 limit≤ref。非 marketable(resting)→ 不套 band。
    let marketable = match side {
        StockEtfOrderSide::Buy => limit >= reference,
        StockEtfOrderSide::Sell => limit <= reference,
        StockEtfOrderSide::Unknown => return Ok(()),
    };
    if !marketable {
        return Ok(());
    }
    // marketable LMT 的 fat-finger sanity:limit 偏離參考價超 band → 拒（approximate;venue flag 為權威)。
    let ref_f = reference as f64;
    let limit_f = limit as f64;
    let deviation = ((limit_f - ref_f) / ref_f).abs();
    if deviation > rules.luld_band_percent {
        return Err(CashConstraintViolation::LuldBandBreach);
    }
    Ok(())
}

/// gate #1 + #2（BUY 側):settled-funds 台帳（T+1)。買入只用 **settled cash + 已成熟 unsettled tranche**
/// （結算日 ≤ 今日)。成本 = qty × 有效價（LMT=限價,MKT=參考價);成本 > 可用 settled → 拒。並算本單
/// 結算日（交易日 + T+offset business day,W6 calendar);不可算 → fail-closed。
fn gate_buy_settled_funds(
    intent: &CashOrderIntent,
    cash_state: &CashAccountState,
    rules: &CashAccountRules,
    calendar: &IbkrTradingCalendarV1,
    qty_fixed: i128,
    order_type: StockEtfPaperOrderType,
    now_ms: u64,
) -> Result<CashConstraintApproved, CashConstraintViolation> {
    // 今日（venue tz;結算成熟度 / T+offset 起點)。tz 不可解 → BUY fail-closed。
    let today =
        venue_today(calendar, now_ms).ok_or(CashConstraintViolation::SettlementDateUncomputable)?;

    // 可用 settled = settled_cash + Σ(結算日 ≤ 今日的 unsettled tranche)。
    let mut available = parse_fixed(&cash_state.settled_cash_decimal).ok_or(
        CashConstraintViolation::MalformedDecimal {
            field: "settled_cash",
        },
    )?;
    for t in &cash_state.unsettled_tranches {
        if !is_valid_yyyymmdd(&t.settlement_date) {
            return Err(CashConstraintViolation::MalformedDecimal {
                field: "tranche_settlement_date",
            });
        }
        // 結算日 ≤ 今日 → 已成熟,併入可用（YYYYMMDD 字典序=時序)。
        if t.settlement_date.as_str() <= today.as_str() {
            let amt = parse_fixed(&t.amount_decimal).ok_or(
                CashConstraintViolation::MalformedDecimal {
                    field: "tranche_amount",
                },
            )?;
            available =
                available
                    .checked_add(amt)
                    .ok_or(CashConstraintViolation::MalformedDecimal {
                        field: "tranche_amount",
                    })?;
        }
    }

    // 有效價(成本上界):**LMT=限價**——限價即成本上界(你永不付高於限價),故**不套 buffer**(marketable
    // LMT 亦然:limit 已是付款上限)。**MKT=參考價 × (1 + marketable_buffer_bps/10000)**——MKT 無價格上限,
    // pre-submit 以 ref 估會低估(實際成交可 > ref),**保守上浮使閘 fail-closed**(修 MED-1 唯一 fail-open;
    // buffer 值 illustrative 待 IB/EA 现勘)。上浮取**向上取整**(保守高估成本,寧拒不樂觀放行)。
    let price = match order_type {
        StockEtfPaperOrderType::Limit => parse_fixed(&intent.limit_price_decimal).ok_or(
            CashConstraintViolation::MalformedDecimal {
                field: "limit_price",
            },
        )?,
        StockEtfPaperOrderType::Market => {
            let reference = parse_fixed(&intent.market.reference_price_decimal).ok_or(
                CashConstraintViolation::MalformedDecimal {
                    field: "reference_price",
                },
            )?;
            marketable_buffered_price(reference, rules.marketable_buffer_bps).ok_or(
                CashConstraintViolation::MalformedDecimal {
                    field: "reference_price",
                },
            )?
        }
    };
    if price <= 0 {
        return Err(CashConstraintViolation::MalformedDecimal {
            field: "limit_price",
        });
    }

    // 成本 = qty(shares) × price。qty_fixed 已過 fractional gate（整數時 qty_fixed % SCALE==0);
    // shares = qty_fixed / SCALE(整數);成本定點 = shares × price(定點)。checked 防溢位。
    let shares = qty_fixed / FIXED_SCALE;
    let frac_shares = qty_fixed % FIXED_SCALE; // allow_fractional 時可非零
                                               // cost = (shares × price) + (frac_shares × price / SCALE)。frac 部分定點乘除保守。
    let cost_int = shares
        .checked_mul(price)
        .ok_or(CashConstraintViolation::MalformedDecimal { field: "quantity" })?;
    let cost_frac = frac_shares
        .checked_mul(price)
        .ok_or(CashConstraintViolation::MalformedDecimal { field: "quantity" })?
        / FIXED_SCALE;
    let cost = cost_int
        .checked_add(cost_frac)
        .ok_or(CashConstraintViolation::MalformedDecimal { field: "quantity" })?;

    if cost > available {
        return Err(CashConstraintViolation::SettledFundsInsufficient {
            required: fmt_fixed(cost),
            available: fmt_fixed(available),
        });
    }

    // 本單結算日（交易日=今日 + T+offset business day;W6 calendar)。不可算 → fail-closed。
    let settlement = settlement_date_for(calendar, &today, rules.settlement_offset_business_days)
        .ok_or(CashConstraintViolation::SettlementDateUncomputable)?;

    Ok(CashConstraintApproved {
        symbol: intent.symbol.clone(),
        side: StockEtfOrderSide::Buy,
        estimated_cost_decimal: fmt_fixed(cost),
        settled_funds_remaining_decimal: fmt_fixed(available - cost),
        projected_settlement_date: settlement,
        evaluated_at_ms: now_ms,
    })
}

/// gate #2 + #3（SELL 側):no-short（賣量 ≤ 既有 long)+ GFV（未結算買入後結算前賣出 = free-riding)。
fn gate_sell_no_short_gfv(
    intent: &CashOrderIntent,
    cash_state: &CashAccountState,
    calendar: &IbkrTradingCalendarV1,
    now_ms: u64,
) -> Result<CashConstraintApproved, CashConstraintViolation> {
    let qty = parse_fixed(&intent.quantity_decimal)
        .ok_or(CashConstraintViolation::MalformedDecimal { field: "quantity" })?;

    // gate #3 no-short（硬邊界):賣量 > 既有 long → 拒（缺倉位=0)。
    let long = match cash_state.long_positions.get(&intent.symbol) {
        Some(q) => parse_fixed(q).ok_or(CashConstraintViolation::MalformedDecimal {
            field: "long_position",
        })?,
        None => 0,
    };
    if qty > long {
        return Err(CashConstraintViolation::ShortSaleDenied {
            requested: fmt_fixed(qty),
            long_available: fmt_fixed(long),
        });
    }

    // gate #2 GFV:該 symbol 有 **unsettled-funded 買入**且**其資金 tranche 結算日 > 今日** → free-riding。
    // 綁「資金來源未結算」而非「買入 T+1 未到」→ 以 settled cash 全額買入、T+1 前的正當賣出**不誤殺**。
    let today =
        venue_today(calendar, now_ms).ok_or(CashConstraintViolation::SettlementDateUncomputable)?;
    if let Some(lot) = cash_state.unsettled_funded_buys.get(&intent.symbol) {
        if !is_valid_yyyymmdd(&lot.funding_settlement_date) {
            return Err(CashConstraintViolation::MalformedDecimal {
                field: "funding_settlement_date",
            });
        }
        if lot.funding_settlement_date.as_str() > today.as_str() {
            return Err(CashConstraintViolation::GfvFreeRidingViolation {
                symbol: intent.symbol.clone(),
            });
        }
    }

    Ok(CashConstraintApproved {
        symbol: intent.symbol.clone(),
        side: StockEtfOrderSide::Sell,
        estimated_cost_decimal: String::new(),
        settled_funds_remaining_decimal: String::new(),
        projected_settlement_date: String::new(),
        evaluated_at_ms: now_ms,
    })
}

// ===========================================================================
// (e) 定點 decimal 比較 + 交易日 / 結算日曆算術
// ===========================================================================

/// 定點刻度（10^-9;無 decimal crate → i128 scaled 精確比較,不用 f64 記帳)。
const FIXED_SCALE: i128 = 1_000_000_000;
/// 定點小數位數（與 `FIXED_SCALE` 對應;過此精度的輸入 → fail-closed 拒,不靜默截斷)。
const FIXED_SCALE_DIGITS: u32 = 9;

/// decimal 字串 → i128 定點（scaled 10^-9)。**fail-closed**:空 / 多小數點 / 非數字 / 過精度
/// （小數位 > 9)/ 溢位 → `None`（不猜、不截斷)。允負（cash 可負)。
fn parse_fixed(raw: &str) -> Option<i128> {
    let s = raw.trim();
    if s.is_empty() {
        return None;
    }
    let (neg, body) = if let Some(r) = s.strip_prefix('-') {
        (true, r)
    } else {
        (false, s.strip_prefix('+').unwrap_or(s))
    };
    if body.is_empty() {
        return None;
    }
    let mut parts = body.split('.');
    let int_part = parts.next().unwrap_or("");
    let frac_part = parts.next().unwrap_or("");
    if parts.next().is_some() {
        return None; // 多個小數點
    }
    if int_part.is_empty() && frac_part.is_empty() {
        return None;
    }
    if !int_part.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if !frac_part.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if frac_part.len() as u32 > FIXED_SCALE_DIGITS {
        return None; // 過精度 → fail-closed（不截斷)
    }
    let int_val: i128 = if int_part.is_empty() {
        0
    } else {
        int_part.parse().ok()?
    };
    let mut frac_val: i128 = if frac_part.is_empty() {
        0
    } else {
        frac_part.parse().ok()?
    };
    let pad = FIXED_SCALE_DIGITS - frac_part.len() as u32;
    frac_val = frac_val.checked_mul(10i128.checked_pow(pad)?)?;
    let total = int_val.checked_mul(FIXED_SCALE)?.checked_add(frac_val)?;
    Some(if neg { -total } else { total })
}

/// marketable BUY(MKT)成本上界:`reference × (1 + bps/10000)`,**向上取整**(保守高估成本 → 閘
/// fail-closed;修 MED-1 MKT fail-open)。定點整數算術(無 f64 記帳);溢位 → `None`。`bps=0` → 原價。
fn marketable_buffered_price(reference: i128, bps: u32) -> Option<i128> {
    if bps == 0 {
        return Some(reference);
    }
    let numer = reference.checked_mul(10_000i128.checked_add(bps as i128)?)?;
    // 向上取整除以 10000(保守:寧高估成本)。reference 於本 lane 恆正(呼叫端已驗 >0)。
    Some((numer + 9_999) / 10_000)
}

/// i128 定點 → decimal 字串（觀測 / 回報用;去尾零,整數不帶小數點)。
fn fmt_fixed(v: i128) -> String {
    let neg = v < 0;
    let abs = v.unsigned_abs();
    let scale = FIXED_SCALE as u128;
    let int_part = abs / scale;
    let frac_part = abs % scale;
    let sign = if neg { "-" } else { "" };
    if frac_part == 0 {
        return format!("{sign}{int_part}");
    }
    // 9 位小數,去尾零。
    let mut frac = format!("{:09}", frac_part);
    while frac.ends_with('0') {
        frac.pop();
    }
    format!("{sign}{int_part}.{frac}")
}

/// `now_ms` → venue tz 的今日"YYYYMMDD"（結算成熟度 / T+offset 起點)。tz 不可解 / 時刻歧義 → `None`
/// （fail-closed)。承 W6 calendar 的 `time_zone_iana`（DST-aware,chrono-tz 解,禁手寫偏移)。
fn venue_today(calendar: &IbkrTradingCalendarV1, now_ms: u64) -> Option<String> {
    let tz: Tz = calendar.time_zone_iana.parse().ok()?;
    if now_ms > i64::MAX as u64 {
        return None;
    }
    let dt = tz.timestamp_millis_opt(now_ms as i64).single()?;
    Some(dt.format("%Y%m%d").to_string())
}

/// 結算日 = 交易日 + `offset` 個交易日（W6 calendar 的 `Open` session 日期序)。offset=0 → 交易日本身;
/// offset≥1 → 今日之後第 offset 個 `Open` 日。calendar 前瞻 `Open` 日不足 → `None`（fail-closed:不知
/// 結算排程即不放行 BUY)。**offset 歸 rules 注入（T+1 待 IB 现勘),此處只做 business-day 位移算術**。
fn settlement_date_for(
    calendar: &IbkrTradingCalendarV1,
    trade_date: &str,
    offset: u32,
) -> Option<String> {
    if offset == 0 {
        return Some(trade_date.to_string());
    }
    // 收斂唯一、排序的 Open 日期集（同日多 session 去重)。
    let mut open_dates: Vec<&str> = calendar
        .sessions
        .iter()
        .filter(|s| s.kind == IbkrCalendarSessionKindV1::Open)
        .map(|s| s.date.as_str())
        .collect();
    open_dates.sort_unstable();
    open_dates.dedup();
    // 嚴格晚於 trade_date 的 Open 日,取第 (offset-1) 個（YYYYMMDD 字典序=時序)。
    let after: Vec<&str> = open_dates.into_iter().filter(|d| *d > trade_date).collect();
    after.get((offset - 1) as usize).map(|d| d.to_string())
}

/// "YYYYMMDD" 語法驗（8 位 ASCII 數字;非法 → 拒,承 calendar 日期紀律)。
fn is_valid_yyyymmdd(raw: &str) -> bool {
    raw.len() == 8 && raw.bytes().all(|b| b.is_ascii_digit())
}

#[cfg(test)]
#[path = "ibkr_cash_account_constraints_tests.rs"]
mod tests;
