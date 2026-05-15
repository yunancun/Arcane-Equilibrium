use openclaw_core::alpha_surface::BtcLeadLagPanel;

/// BtcLeadLagPanelSnapshot — 一個 1m grain 的完整 panel snapshot。
///
/// 對應 V088 `panel.btc_lead_lag_panel` 12-column schema（per spec §4.1）。
/// Writer 端把此 struct INSERT 為 1 row（per-snapshot vector layout）。
///
/// **不變式**：
/// - `alt_symbols.len() == alt_xcorr.len() == alt_expected_dir.len()`
///   （writer 端 assert，違反 = drop snapshot 不 INSERT）
/// - `lead_window_secs == LEAD_WINDOW_SECS_MAIN`（120）— 主信號鎖定
/// - `regime_tag` ∈ {"normal", "extreme"}
/// - `source_tier == SOURCE_TIER` or `DIAGNOSTIC_SOURCE_TIER`
#[derive(Debug, Clone, PartialEq)]
pub struct BtcLeadLagPanelSnapshot {
    /// 1m grain epoch ms（對齊 1m bucket）。
    pub snapshot_ts_ms: i64,
    /// 主信號 lead window 秒數，固定 120。
    pub lead_window_secs: u32,
    /// 主信號 BTC lead return（bps，N=120）。NaN = 樣本不足。
    pub btc_lead_return_pct: f64,
    /// Shadow N=60 BTC lead return（bps，decay curve evidence）。NaN = 樣本不足。
    pub btc_lead_return_pct_60s: f64,
    /// Shadow N=300 BTC lead return（bps，decay curve evidence）。NaN = 樣本不足。
    pub btc_lead_return_pct_300s: f64,
    /// 主信號 BTC volume z-score（rolling 1h baseline shift(1)）。NaN = 樣本不足。
    pub btc_volume_z: f64,
    /// BTC orderbook top-N imbalance（spec §3.1.3 ∈ [-1, +1]）。
    ///
    /// W2-IMPL-1 (2026-05-11) — 從 WS `orderbook.50.BTCUSDT` push 計算：
    /// `(sum(bid_qty[0..N]) - sum(ask_qty[0..N])) / (sum_all)`。
    ///
    /// `f64::NAN` 表 ingest task 尚未收到 fresh orderbook event（producer boot
    /// 後 ~ms 內或 WS reconnect 短窗口）；下游 evaluator `WHERE NOT
    /// btc_book_imbalance = 'NaN'::REAL` 過濾。**禁寫 0.0 假值**：0.0 是合法
    /// 「平衡 book」訊號，與「尚無資料」語意衝突，會造成 lost evidence
    /// （per dispatch §3.1 acceptance criteria 5）。
    pub btc_book_imbalance: f64,
    /// Cohort alt symbols（per spec §2.2 7-symbol cohort，與 alt_xcorr / alt_expected_dir 同序）。
    pub alt_symbols: Vec<String>,
    /// Per-alt-symbol cross-correlation vs BTC lead return（rolling 1h，min 30 sample）。
    /// NaN 表 sample 不足（consumer 視 NaN 為 no-signal）。
    pub alt_xcorr: Vec<f64>,
    /// Per-alt-symbol predicted direction（−1 / 0 / +1，per spec §3.3）。
    pub alt_expected_dir: Vec<i8>,
    /// Regime tag："normal" / "extreme"（|BTCUSDT 1h return| > 200 bps → "extreme"）。
    pub regime_tag: String,
    /// Source tier（normal or diagnostic marker; diagnostic rows are non-promotional）。
    pub source_tier: String,
}

impl BtcLeadLagPanelSnapshot {
    /// 三 array length invariant 自驗（writer 端 INSERT 前必跑）。
    /// 違反 → 返 false → writer drop snapshot fail-soft，不 INSERT 半 schema row。
    pub fn arrays_aligned(&self) -> bool {
        let n = self.alt_symbols.len();
        n == self.alt_xcorr.len() && n == self.alt_expected_dir.len()
    }
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — snapshot → trait struct adaptor。
///
/// `BtcLeadLagPanelSnapshot`（producer 端，含 12-column schema 全字段）映射至
/// `BtcLeadLagPanel`（trait struct，AlphaSurface field type）。adaptor 只取
/// 主信號 N=120 字段（per spec line 207「主 N=120 信號寫主 panel 欄位，60s/300s
/// shadow value 寫 schema column 但不寫 IPC slot」）。
///
/// **不變式**：
/// - `lead_window_secs == LEAD_WINDOW_SECS_MAIN` (120) — 主信號鎖定
/// - `alt_symbols.len() == alt_xcorr.len() == alt_expected_dir.len()`（snapshot
///   端已 invariant，adaptor 直接 clone）
pub fn snapshot_to_trait_panel(snapshot: &BtcLeadLagPanelSnapshot) -> BtcLeadLagPanel {
    BtcLeadLagPanel {
        alt_symbols: snapshot.alt_symbols.clone(),
        btc_lead_return_pct: snapshot.btc_lead_return_pct,
        lead_window_secs: snapshot.lead_window_secs,
        alt_xcorr: snapshot.alt_xcorr.clone(),
        alt_expected_dir: snapshot.alt_expected_dir.clone(),
        snapshot_ts_ms: snapshot.snapshot_ts_ms,
        source_tier: snapshot.source_tier.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::panel_aggregator::btc_lead_lag::{LEAD_WINDOW_SECS_MAIN, SOURCE_TIER};

    fn make_snapshot() -> BtcLeadLagPanelSnapshot {
        BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_700_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: 25.5,
            btc_lead_return_pct_60s: 12.3,
            btc_lead_return_pct_300s: 50.0,
            btc_volume_z: 1.5,
            btc_book_imbalance: 0.0,
            alt_symbols: vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()],
            alt_xcorr: vec![0.6, -0.4],
            alt_expected_dir: vec![1, -1],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        }
    }

    #[test]
    fn arrays_aligned_invariant_on_snapshot() {
        let mut s = make_snapshot();
        assert!(s.arrays_aligned());
        s.alt_xcorr.push(0.99);
        assert!(!s.arrays_aligned());
    }

    #[test]
    fn snapshot_to_trait_panel_propagates_main_signal_fields() {
        let snapshot = make_snapshot();
        let panel = snapshot_to_trait_panel(&snapshot);
        assert_eq!(panel.snapshot_ts_ms, snapshot.snapshot_ts_ms);
        assert_eq!(panel.lead_window_secs, LEAD_WINDOW_SECS_MAIN);
        assert_eq!(panel.btc_lead_return_pct, 25.5);
        assert_eq!(
            panel.alt_symbols,
            vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()]
        );
        assert_eq!(panel.alt_xcorr, vec![0.6, -0.4]);
        assert_eq!(panel.alt_expected_dir, vec![1, -1]);
        assert_eq!(panel.source_tier, SOURCE_TIER);
    }

    #[test]
    fn snapshot_to_trait_panel_preserves_nan() {
        let mut snapshot = make_snapshot();
        snapshot.btc_lead_return_pct = f64::NAN;
        snapshot.alt_xcorr = vec![f64::NAN];
        snapshot.alt_symbols = vec!["ETHUSDT".to_string()];
        snapshot.alt_expected_dir = vec![0];
        let panel = snapshot_to_trait_panel(&snapshot);
        assert!(panel.btc_lead_return_pct.is_nan());
        assert!(panel.alt_xcorr[0].is_nan());
    }
}
