//! W7-S3 三向對賬引擎 **_support**：E2-LOW-2 結算台帳 disjoint 不變量（承 S2 carry）+ 定點 decimal
//! 輔助 + **broker-status → 本地態解讀**純函數（`broker_target`/`broker_terminal_target`/
//! `broker_conflicts_with_terminal`/`terminal_fill_qty_diverges`/`fill_from`/`has_positive_fill`）。
//! 自主檔（檔案行數治理:主 `ibkr_order_reconciliation.rs` 拆出本節）。純函數,注入日期/時鐘,
//! 零 socket/async/send。

use openclaw_types::IbkrPaperOrderLifecycleState;

use super::BrokerOrderTruth;
use crate::ibkr_cash_account_constraints::CashTranche;
use crate::ibkr_tws_order_exec_data::IbkrOrderStatusV1;
use crate::ibkr_tws_order_lifecycle::FillDelta;

// ===========================================================================
// broker-status → 本地態解讀 + fill/量對賏（純函數;主模塊 reconcile 迴路消費）
// ===========================================================================

/// broker order 的目標本地態 + 可選 fill（活躍前推用;白名單外 / 無 status → `None`=無法證明)。
pub(crate) fn broker_target(
    order: &BrokerOrderTruth,
) -> Option<(IbkrPaperOrderLifecycleState, Option<FillDelta>)> {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    let status = order.status?;
    let fill = fill_from(order);
    match status {
        S::Filled => Some((St::Filled, fill)),
        S::Submitted | S::PreSubmitted => {
            // 有部分成交 → PartiallyFilled;否則 broker 已受理 → BrokerAcknowledged。
            match &fill {
                Some(_) if has_positive_fill(order) => Some((St::PartiallyFilled, fill)),
                _ => Some((St::BrokerAcknowledged, None)),
            }
        }
        S::PendingSubmit => Some((St::BrokerSubmitRequested, None)),
        S::PendingCancel => Some((St::CancelRequested, None)),
        S::Cancelled | S::ApiCancelled => Some((St::Cancelled, None)),
        S::Inactive => Some((St::Inactive, None)),
        S::UnknownDenied => None,
    }
}

/// broker terminal-with-evidence 目標（StateUnknown 出口用;僅終態且帶 broker 佐證方回)。
pub(crate) fn broker_terminal_target(
    order: &BrokerOrderTruth,
) -> Option<(IbkrPaperOrderLifecycleState, Option<FillDelta>)> {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    match order.status? {
        S::Filled => Some((St::Filled, fill_from(order))),
        S::Cancelled | S::ApiCancelled => Some((St::Cancelled, None)),
        S::Inactive => Some((St::Inactive, None)),
        _ => None,
    }
}

/// broker 是否與本地終態衝突（幻影偵測:本地已 Cancelled/Rejected/Inactive 但 broker 顯示 Filled
/// 或有正成交 → 衝突;本地 Filled × broker Filled 時**再比成交量**=MED-1 終態量分歧偵測)。
/// `local_cum`=本地累積成交量(MED-1 用)。
pub(crate) fn broker_conflicts_with_terminal(
    local: IbkrPaperOrderLifecycleState,
    local_cum: Option<&str>,
    order: &BrokerOrderTruth,
) -> bool {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    match order.status {
        // 本地 Filled × broker Filled:量對賏（**不**再僅比 status enum;MED-1)。本地非 Filled × broker
        // Filled:狀態即衝突。
        Some(S::Filled) => {
            if local != St::Filled {
                true
            } else {
                terminal_fill_qty_diverges(local_cum, order)
            }
        }
        Some(S::Submitted)
        | Some(S::PreSubmitted)
        | Some(S::PendingSubmit)
        | Some(S::PendingCancel) => {
            // broker 仍顯示活躍/工作中,但本地已終態 → 衝突（除非本地 Inactive 且無正成交)。
            has_positive_fill(order) || local != St::Inactive
        }
        _ => false,
    }
}

/// **MED-1 終態成交量分歧**:本地累積成交量 vs broker filled 量對賏（定點精確比;不可解 / broker 有量
/// 本地無 → **fail-closed** 視為分歧)。broker 無 filled 量佐證 → 不以量判(false;交由 status 邏輯)。
pub(crate) fn terminal_fill_qty_diverges(
    local_cum: Option<&str>,
    order: &BrokerOrderTruth,
) -> bool {
    match (local_cum, order.filled_decimal.as_deref()) {
        (Some(l), Some(b)) => !matches!(fixed_decimals_equal(l, b), Some(true)),
        // broker 顯示成交量、本地無累積 → 無法證明相等 → fail-closed 分歧。
        (None, Some(_)) => true,
        // broker 無 filled 量佐證 → 不以量判。
        (_, None) => false,
    }
}

/// 由 broker order 的 filled/remaining 構 fill delta（缺任一 → `None`,不捏值)。
fn fill_from(order: &BrokerOrderTruth) -> Option<FillDelta> {
    match (&order.filled_decimal, &order.remaining_decimal) {
        (Some(f), Some(r)) => Some(FillDelta {
            cumulative_filled_decimal: f.clone(),
            remaining_decimal: r.clone(),
        }),
        _ => None,
    }
}

/// broker 是否有正累積成交（filled > 0;方向判別,非記帳)。
fn has_positive_fill(order: &BrokerOrderTruth) -> bool {
    order
        .filled_decimal
        .as_deref()
        .and_then(|s| s.parse::<f64>().ok())
        .map(|v| v > 0.0)
        .unwrap_or(false)
}

/// 結算台帳對賬結果（E2-LOW-2）:已成熟 tranche 滾入 settled_cash,並**移出** unsettled(disjoint)。
/// （`CashTranche` 僅派生 `PartialEq`——承 S2 契約,本型別亦不派生 `Eq`。）
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct SettlementLedger {
    /// 滾入已成熟 tranche 後的 settled cash（定點字串)。
    pub settled_cash_decimal: String,
    /// 剩餘 unsettled tranche（**僅** settlement_date > today;disjoint 保證)。
    pub unsettled_tranches: Vec<CashTranche>,
    /// 本次滾入的已成熟 tranche 數（觀測)。
    pub matured_folded_count: usize,
}

/// 結算台帳對賬 typed 錯誤（全 fail-closed;禁靜默截斷 / 假值)。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum LedgerReconcileError {
    #[error("malformed settled cash decimal")]
    MalformedSettledCash,
    #[error("malformed tranche amount: {0}")]
    MalformedTrancheAmount(String),
    #[error("malformed tranche settlement date: {0}")]
    MalformedTrancheDate(String),
    #[error("fixed-point overflow")]
    Overflow,
    /// **disjoint 不變量破壞**（防禦:輸出仍含已成熟 tranche 於 unsettled → 會被下游重複計數)。
    #[error("matured tranche double-counted: {0}")]
    MaturedTrancheDoubleCounted(String),
}

/// **E2-LOW-2 disjoint 不變量**:已成熟（settlement_date ≤ today）tranche 滾入 settled_cash 並移出
/// unsettled——**禁同時計數**（防 S2 gate 於下一輪把 settled_cash 內已含之成熟 tranche 又從
/// unsettled 併回=fail-open 重複計數)。承 S2 carry(E2-LOW-2);本函數為 defense-in-depth,以型別
/// 強制 disjoint。純函數,`today_yyyymmdd` 注入(禁 wall-clock 日期腐化)。
pub(crate) fn reconcile_settlement_ledger(
    settled_cash_decimal: &str,
    unsettled_tranches: &[CashTranche],
    today_yyyymmdd: &str,
) -> Result<SettlementLedger, LedgerReconcileError> {
    if !is_valid_yyyymmdd(today_yyyymmdd) {
        return Err(LedgerReconcileError::MalformedTrancheDate(
            today_yyyymmdd.to_string(),
        ));
    }
    let mut settled =
        parse_fixed_i128(settled_cash_decimal).ok_or(LedgerReconcileError::MalformedSettledCash)?;
    let mut remaining: Vec<CashTranche> = Vec::new();
    let mut matured_folded_count = 0usize;
    for t in unsettled_tranches {
        if !is_valid_yyyymmdd(&t.settlement_date) {
            return Err(LedgerReconcileError::MalformedTrancheDate(
                t.settlement_date.clone(),
            ));
        }
        let amount = parse_fixed_i128(&t.amount_decimal).ok_or_else(|| {
            LedgerReconcileError::MalformedTrancheAmount(t.amount_decimal.clone())
        })?;
        if t.settlement_date.as_str() <= today_yyyymmdd {
            // 已成熟:滾入 settled,**移出** unsettled(不 push 至 remaining)。
            settled = settled
                .checked_add(amount)
                .ok_or(LedgerReconcileError::Overflow)?;
            matured_folded_count += 1;
        } else {
            remaining.push(t.clone());
        }
    }
    // disjoint 斷言(defense-in-depth):remaining 內不得再有已成熟 tranche。
    for t in &remaining {
        if t.settlement_date.as_str() <= today_yyyymmdd {
            return Err(LedgerReconcileError::MaturedTrancheDoubleCounted(
                t.settlement_date.clone(),
            ));
        }
    }
    Ok(SettlementLedger {
        settled_cash_decimal: fmt_fixed_i128(settled),
        unsettled_tranches: remaining,
        matured_folded_count,
    })
}

// ---- 定點 decimal 輔助（i128 scaled 10^-9;與 S2 `ibkr_cash_account_constraints` 紀律平行,本模塊
//      自持避免跨模塊耦合;fail-closed:空/多點/非數字/過精度/溢位 → None) ----

/// 定點刻度(10^-9)。
const LEDGER_FIXED_SCALE: i128 = 1_000_000_000;
/// 定點小數位數。
const LEDGER_FIXED_DIGITS: u32 = 9;

fn parse_fixed_i128(raw: &str) -> Option<i128> {
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
        return None;
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
    if frac_part.len() as u32 > LEDGER_FIXED_DIGITS {
        return None;
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
    let pad = LEDGER_FIXED_DIGITS - frac_part.len() as u32;
    frac_val = frac_val.checked_mul(10i128.checked_pow(pad)?)?;
    let total = int_val
        .checked_mul(LEDGER_FIXED_SCALE)?
        .checked_add(frac_val)?;
    Some(if neg { -total } else { total })
}

fn fmt_fixed_i128(v: i128) -> String {
    let neg = v < 0;
    let abs = v.unsigned_abs();
    let scale = LEDGER_FIXED_SCALE as u128;
    let int_part = abs / scale;
    let frac_part = abs % scale;
    let sign = if neg { "-" } else { "" };
    if frac_part == 0 {
        return format!("{sign}{int_part}");
    }
    let mut frac = format!("{frac_part:09}");
    while frac.ends_with('0') {
        frac.pop();
    }
    format!("{sign}{int_part}.{frac}")
}

fn is_valid_yyyymmdd(raw: &str) -> bool {
    raw.len() == 8 && raw.bytes().all(|b| b.is_ascii_digit())
}

/// 兩 decimal 字串是否**數值相等**（定點精確比;`"100"`==`"100.0"`==`"100.000"`）。任一不可解 →
/// `None`（呼叫端 fail-closed:不可解不得當作相等）。MED-1 終態量對賏用。
pub(crate) fn fixed_decimals_equal(a: &str, b: &str) -> Option<bool> {
    Some(parse_fixed_i128(a)? == parse_fixed_i128(b)?)
}
