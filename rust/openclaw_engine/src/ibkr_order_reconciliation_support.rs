//! W7-S3 三向對賬引擎 **_support**：E2-LOW-2 結算台帳 disjoint 不變量（承 S2 carry）+ 定點 decimal
//! 輔助。自主檔（檔案行數治理:主 `ibkr_order_reconciliation.rs` 拆出本節）。純函數,注入日期,
//! 零 socket/async/send。

use crate::ibkr_cash_account_constraints::CashTranche;

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
