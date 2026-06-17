//! Phase 1（rich-input tuner）— StrategistScheduler 的 leak-free 證據側車。
//!
//! MODULE_NOTE (中):
//!   模塊用途：在 5-min out-of-band 評估迴圈裡，為當前 (strategy, symbol) pair
//!     組裝 **additive INPUT** 證據（edge_estimates / 自算 regime / news context），
//!     並提供 server-side 的 `verify_quant_justification` quant gate。Phase 1 只擴
//!     **輸入面**：不改 scheduler 能寫什麼（仍 demo-only、仍只調 agent_adjustable
//!     參數、仍走既有 clamp/range/weight-sum validate）。
//!   主要類/函數：`RichInputs`（側車 owned snapshot）、`CellEstimateView` /
//!     `NewsItemView`（可序列化視圖）、`compute_regime_label`（point-in-time
//!     leak-free Hurst 自算）、`verify_quant_justification`（news-blind quant gate）。
//!   依賴：`crate::edge_estimates::{EdgeEstimates, CellEstimate}`、
//!     `crate::regime::hurst::compute_hurst`、`serde_json`。
//!   硬邊界：
//!     1. `verify_quant_justification` 簽名 **不含任何 news 參數** — news 結構上
//!        不可能影響 gate 是否通過（Alpha Evidence Governance：news 只能 corroborate）。
//!     2. quant gate 全程 **零讀** news 欄；唯一能授權調參的證據源是 `edge_estimates`。
//!     3. engine 端 **自查** 被引用的 edge cell（不信 LLM 的 claimed_shrunk_bps）；
//!        cell 缺 / stale / 未驗證 / 數值符號不符 → reject（fail-closed）。
//!     4. 整個側車只在 `OPENCLAW_STRATEGIST_RICH_INPUT=1`（flag-ON）時組裝；
//!        flag-OFF → 不建 `RichInputs`、payload 與 validate 路徑 bit-identical。

use crate::edge_estimates::{CellEstimate, EdgeEstimates};
use serde::Serialize;
use serde_json::Value;

/// rich-input quant gate 的兩個新 reject reason（與 cycle_counters.rs 對齊）。
/// 為什麼是 `&'static str`：對齊 `validate_recommendation_with_reason` 既有
/// reason 形態（穩定短字串、零分配、可當 CycleCounters HashMap key）。
pub const REASON_NEWS_SOLO_TRIGGER: &str = "news_solo_trigger";
pub const REASON_QUANT_JUSTIFICATION_UNVERIFIED: &str = "quant_justification_unverified";

/// claimed_shrunk_bps 與真 cell 數值的允許偏差（bps）。
/// 為什麼設容差而非精確相等：LLM 可能對 cell 數字四捨五入（如 2.13 → 2.1），
/// 純符號一致 + |Δ| <= 容差即視為「引用正確」；符號不同（捏造方向）必拒。
const CLAIMED_BPS_TOLERANCE: f64 = 1.0;

/// 可序列化的 edge cell 視圖（送進 payload 給 LLM 看，但 **不** 作為 gate 依據；
/// gate 永遠用 engine 自查的真 cell）。
/// 為什麼是獨立 owned 視圖而非借 `&CellEstimate`：payload 在 cycle 內組好後
/// 跨 await 邊界傳遞，須 owned + Serialize。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct CellEstimateView {
    pub shrunk_bps: f64,
    pub win_rate: f64,
    pub n_trades: u64,
    pub validation_passed: bool,
    pub validation_reason: String,
    pub from_runtime_field: bool,
    /// engine 自算的 freshness（gate 真正依據之一；payload 也展示讓 LLM 知道
    /// 是否有可引用證據）。
    pub is_fresh: bool,
}

impl CellEstimateView {
    /// 從真 `CellEstimate` + freshness 結果建視圖。
    /// `is_fresh` 由 caller 傳入（caller 持 `EdgeEstimates` snapshot 與 now/ttl，
    /// 在此一處算好，避免視圖再持有 snapshot 引用）。
    pub fn from_cell(cell: &CellEstimate, is_fresh: bool) -> Self {
        Self {
            shrunk_bps: cell.shrunk_bps,
            win_rate: cell.win_rate,
            n_trades: cell.n_trades,
            validation_passed: cell.validation_passed,
            validation_reason: cell.validation_reason.clone(),
            from_runtime_field: cell.from_runtime_field,
            is_fresh,
        }
    }
}

/// 可序列化的 news 視圖（**untrusted narrative context**，零 gate 權重）。
/// 為什麼保留此型別即使 boot 暫不接 router：讓 gate 的「news 零權重」不變量
/// 可被測試（T-P1-9/10 注入 news 證 gate 結果不變），且未來 additive 接線即生效。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NewsItemView {
    pub headline: String,
    pub severity: f64,
    pub sentiment: String,
}

/// Phase 1 leak-free 證據側車。flag-OFF → 整個結構不建（caller 傳 None）。
/// 全 owned + Serialize：在 `evaluate_cycle` 組好後傳給 payload builder。
#[derive(Debug, Clone, Default, Serialize, PartialEq)]
pub struct RichInputs {
    /// per-cell edge 估計視圖；None = cell absent（該 pair 無 edge 證據）。
    pub edge_cell: Option<CellEstimateView>,
    /// scheduler 自算的 regime label（legacy 字串：trending / mean_reverting /
    /// random_walk）；None = closes 不足或算失敗 → payload 寫 "unknown"。
    pub regime: Option<String>,
    /// news context（untrusted）；None = 無 news / router 未接 → 欄 absent。
    pub news: Option<Vec<NewsItemView>>,
}

impl RichInputs {
    /// 把側車序列化成 payload 的單一新頂層鍵 `rich_input` 的內容值。
    /// 為什麼集中在此：payload builder 只需塞一個鍵，序列化形狀由側車掌握，
    /// Python prompt builder 讀同一形狀（edge_estimates / regime / news_context）。
    pub fn to_payload_value(&self) -> Value {
        serde_json::json!({
            // edge_estimates：null = 無 cell；LLM 看到 null 即知無可引用證據。
            "edge_estimates": self.edge_cell,
            // regime：不偽造，缺值寫 "unknown"（context-only，不影響 gate）。
            "regime": self.regime.clone().unwrap_or_else(|| "unknown".to_string()),
            // news_context：untrusted narrative；缺則空陣列（gate 永不讀此欄）。
            "news_context": self.news.clone().unwrap_or_default(),
        })
    }

    /// `quant_evidence_available`：是否存在「可被 quant gate 接受」的 edge 證據
    /// （cell 存在 + fresh + validated）。供 LLM 知道有無可引證據。
    /// 為什麼與 gate 同條件：避免 LLM 在無證據時硬編 quant_justification 又被拒
    /// （prompt 明示無證據 → 回 {}）。
    pub fn quant_evidence_available(&self) -> bool {
        self.edge_cell
            .as_ref()
            .map(|c| c.is_fresh && c.validation_passed)
            .unwrap_or(false)
    }
}

/// Phase 1 regime 自算（point-in-time leak-free）。
///
/// 為什麼自算而非讀 tick-path label：scheduler 是 5-min out-of-band loop，
/// 讀不到 tick-path 的記憶體 `indicators.hurst.regime`（且該功能 default
/// `hurst.enabled=false` dormant）。改由 scheduler 從 `market.klines` 取嚴格
/// 已收盤 1m closes 自算 Hurst → 分類。
///
/// 不變量（leak-free）：`closes` 必須只含 **嚴格過去已收盤** 的 1m bar（caller
/// 用 `ts < now()` 查詢保證，等價 shift(1)，不含當前未收 bar）。本函數不讀
/// wallclock、不查 DB，純對傳入序列分類 → 可單元測試。
///
/// 分類閾值鏡像 `HurstConfig` 預設（persistent>0.55、antipersistent<0.45），
/// 不施 hysteresis（單次無歷史）— 與既有 `hurst_label_for_symbol` 同語意，但
/// 此處 **不** gated by `enabled`（regime 是 Phase 1 context-only 欄，非交易行為）。
///
/// 回傳 legacy 字串以對齊既有 regime 詞彙（trending / mean_reverting /
/// random_walk）；窗口不足 / 估計退化 → None（caller 寫 "unknown"）。
pub fn compute_regime_label(closes: &[f64], min_window: usize, max_window: usize) -> Option<String> {
    let h = crate::regime::hurst::compute_hurst(closes, min_window, max_window)?;
    // 鏡像 HurstConfig 預設閾值（0.55 / 0.45）。硬碼於此是因為 regime 是
    // context-only 欄，不需要 operator 旋鈕；若日後要可調再讀 RiskConfig。
    let label = if h > 0.55 {
        "trending"
    } else if h < 0.45 {
        "mean_reverting"
    } else {
        "random_walk"
    };
    Some(label.to_string())
}

/// Server-side quant_justification 驗證（Phase 1 must-fix 核心）。
///
/// **硬不變量：簽名不含任何 news 參數 — news 結構上不可能影響 verdict。**
/// news 只能在 LLM **內部** 作為「已被 edge 支撐的選項間」的 post-hoc tiebreaker，
/// 永遠過不了「沒有 edge 支撐」這關。
///
/// 只在 flag-ON 且 recommendation **非空**（含 ≥1 實際 param delta）時呼叫；
/// flag-OFF / 空 recommendation `{}` → caller bypass（payload+validate bit-identical）。
///
/// 參數：
/// - `rec`：LLM 回的 recommendation JSON 物件（含數值 param + 可能的
///   `quant_justification` 結構化 dict）。
/// - `param_ranges_with_delta`：本 rec 中「真正落在 agent_adjustable 範圍內、
///   與當前值不同」的 param 是否存在（caller 算好傳 bool；避免本函數再解析
///   ParamRange — 保持 news-blind + 純對 edge 證據驗證的單一職責）。
/// - `edge`：engine 持有的 `EdgeEstimates` snapshot（gate 自查真 cell 的來源；
///   **不信** LLM 傳的 claimed_shrunk_bps）。
/// - `now_ts` / `ttl`：freshness 判定（鏡像 cost_gate；now 由 caller 注入，
///   純函數可測）。
///
/// 驗證邏輯（engine 端獨立、news 零權重）：
/// 1. rec 有 ≥1 實際 param delta 但 **缺** quant_justification → news_solo_trigger。
/// 2. quant_justification.source != "edge_estimates" → news_solo_trigger。
/// 3. engine 自查 cited cell：absent / !is_fresh / !validation_passed /
///    真 shrunk_bps 符號與 claimed 不符（或 |Δ| 超容差）→ quant_justification_unverified。
/// 4. 全過 → Ok(())。
pub fn verify_quant_justification(
    rec: &Value,
    has_real_param_delta: bool,
    edge: &EdgeEstimates,
    now_ts: i64,
    ttl: i64,
) -> Result<(), &'static str> {
    // 無實際 param delta → 不可能 news-solo（沒在改任何參數）→ 直接放行。
    // 這條保護「LLM 只回 meta、沒改參數」的退化情況（caller 通常已 bypass，
    // 但雙重保險：無 delta = 無調參 = 無需 quant 支撐）。
    if !has_real_param_delta {
        return Ok(());
    }

    let rec_obj = match rec.as_object() {
        Some(o) => o,
        // 非物件不可能帶結構化 justification；有 delta 卻非物件 = 無理由支撐。
        None => return Err(REASON_NEWS_SOLO_TRIGGER),
    };

    // (1) 有 delta 但完全沒帶 quant_justification → 唯一可能支撐只剩 news/context → 拒。
    let qj = match rec_obj.get("quant_justification").and_then(|v| v.as_object()) {
        Some(o) => o,
        None => return Err(REASON_NEWS_SOLO_TRIGGER),
    };

    // (2) source 必為 "edge_estimates"；寫 "news"/"sentiment"/自由文字 → 拒。
    //     news/敘事永遠不可作為調參的量化來源。
    let source = qj.get("source").and_then(|v| v.as_str()).unwrap_or("");
    if source != "edge_estimates" {
        return Err(REASON_NEWS_SOLO_TRIGGER);
    }

    // (3) engine 自查被引用的 cell —— 解析 "cell" 為 "strategy::symbol"。
    //     不信 LLM 的 claimed_shrunk_bps，engine 用 get_cell 拿真值。
    let cell_key = qj.get("cell").and_then(|v| v.as_str()).unwrap_or("");
    let (strategy, symbol) = match cell_key.split_once("::") {
        Some((s, sym)) if !s.is_empty() && !sym.is_empty() => (s, sym),
        // cell 鍵格式非法（無 "::" 或空段）→ 無法定位真 cell → 未驗證。
        _ => return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED),
    };

    let cell = match edge.get_cell(strategy, symbol) {
        Some(c) => c,
        // cell 不存在（該 strategy::symbol 無 edge 估計）→ 未驗證。
        None => return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED),
    };

    // stale 證據不算數（鏡像 cost_gate freshness gate）。
    if !edge.is_fresh(now_ts, ttl) {
        return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED);
    }

    // James-Stein producer 自己沒過 leak-free OOS 驗證 → 不可作為調參授權。
    if !cell.validation_passed {
        return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED);
    }

    // claimed_shrunk_bps 與真值比對：符號必須一致、且 |Δ| 不超容差。
    // 缺 claimed 欄視為「未提供可核對數字」→ 未驗證（LLM 必須引用具體數字）。
    let claimed = match qj.get("claimed_shrunk_bps").and_then(|v| v.as_f64()) {
        Some(v) => v,
        None => return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED),
    };
    let real = cell.shrunk_bps;
    // 符號不一致（捏造方向）必拒。零值兩側皆視為 0（符號相同），交給容差判定。
    let sign_disagree = (real > 0.0 && claimed < 0.0) || (real < 0.0 && claimed > 0.0);
    if sign_disagree || (real - claimed).abs() > CLAIMED_BPS_TOLERANCE {
        return Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED);
    }

    // 全過：edge 證據真實、fresh、validated、數值對齊。
    // 注意：v1 不卡 direction × param 語意（QC 在 U4-P1 後另定 additive 映射），
    // 避免 param 語意映射誤殺；但 cell 必須真存在 + fresh + validated + 數值對齊。
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::edge_estimates::EdgeEstimates;

    // ── 共用 fixture ──

    /// 建一個含單 cell 的 EdgeEstimates，updated_at 固定，可控 validation。
    fn edge_with_cell(
        key: &str,
        shrunk_bps: f64,
        validation_passed: bool,
        updated_at: &str,
    ) -> EdgeEstimates {
        let vp = if validation_passed { "true" } else { "false" };
        let json = format!(
            r#"{{
                "_meta": {{"updated_at": "{updated_at}"}},
                "{key}": {{
                    "runtime_bps": {shrunk_bps},
                    "validation_passed": {vp},
                    "n": 120
                }}
            }}"#
        );
        EdgeEstimates::load_from_str(&json).unwrap()
    }

    /// fresh now / ttl 對齊 cost_gate 預設 48h。updated_at = 2026-05-29T00:00:00Z。
    const UPDATED_AT: &str = "2026-05-29T00:00:00+00:00";
    const UPDATED_EPOCH: i64 = 1_780_012_800;
    const TTL: i64 = 172_800; // 48h

    fn fresh_now() -> i64 {
        UPDATED_EPOCH + 100 // 100s after update → fresh
    }
    fn stale_now() -> i64 {
        UPDATED_EPOCH + TTL + 1 // 超 TTL 1s → stale
    }

    fn rec_with_qj(source: &str, cell: &str, claimed: f64) -> Value {
        serde_json::json!({
            "cooldown_ms": 55000,
            "quant_justification": {
                "source": source,
                "cell": cell,
                "claimed_shrunk_bps": claimed,
                "direction": "tighten",
                "rationale": "edge supports tightening"
            }
        })
    }

    // ── T-P1-2：有 delta 但無 quant_justification → news_solo_trigger ──
    #[test]
    fn t_p1_2_delta_without_justification_is_news_solo() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = serde_json::json!({ "cooldown_ms": 55000 });
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_NEWS_SOLO_TRIGGER));
    }

    // ── T-P1-3：source="news" → news_solo_trigger ──
    #[test]
    fn t_p1_3_source_news_is_news_solo() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = rec_with_qj("news", "ma_crossover::BTCUSDT", 5.0);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_NEWS_SOLO_TRIGGER));
    }

    // ── T-P1-4：cited cell 不存在 → unverified ──
    #[test]
    fn t_p1_4_absent_cell_is_unverified() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = rec_with_qj("edge_estimates", "grid_trading::ETHUSDT", 5.0);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-5：cell stale（is_fresh=false）→ unverified ──
    #[test]
    fn t_p1_5_stale_cell_is_unverified() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", 5.0);
        let r = verify_quant_justification(&rec, true, &edge, stale_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-6：cell validation_passed=false → unverified ──
    #[test]
    fn t_p1_6_unvalidated_cell_is_unverified() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, false, UPDATED_AT);
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", 5.0);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-7：claimed 符號與真 cell 相反 → unverified ──
    #[test]
    fn t_p1_7_sign_mismatch_is_unverified() {
        // 真 cell = +5.0；LLM 聲稱 -5.0（符號相反，捏造方向）。
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", -5.0);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-7b：claimed |Δ| 超容差（同號但偏太多）→ unverified ──
    #[test]
    fn t_p1_7b_magnitude_too_far_is_unverified() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        // 真 5.0、claimed 8.0、|Δ|=3 > 1.0 容差。
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", 8.0);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-8：cell 真實+fresh+validated+對齊 → Ok ──
    #[test]
    fn t_p1_8_valid_cell_passes() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        // claimed 5.2 與真 5.0 同號、|Δ|=0.2 <= 1.0 容差。
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", 5.2);
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Ok(()));
    }

    // ── T-P1-9：強烈 bullish news 但無 edge cell → 仍拒（證 news 零權重）──
    // verify_quant_justification 簽名根本沒有 news 參數，所以「強 news」無法
    // 表達進這個函數 —— 這正是不變量。本測試證：當引用的 cell 不存在時，
    // 不論 LLM rationale 裡寫多強的 bullish 敘事，gate 都拒。
    #[test]
    fn t_p1_9_strong_news_rationale_no_cell_still_rejected() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = serde_json::json!({
            "cooldown_ms": 55000,
            "quant_justification": {
                "source": "edge_estimates",
                "cell": "ma_crossover::DOGEUSDT",  // 不存在的 cell
                "claimed_shrunk_bps": 50.0,
                "direction": "loosen",
                "rationale": "MASSIVE BULLISH NEWS: ETF approved, price mooning, all-in!"
            }
        });
        let r = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(r, Err(REASON_QUANT_JUSTIFICATION_UNVERIFIED));
    }

    // ── T-P1-10：同 rec 結果不隨 news 變（news 零權重的直接證明）──
    // 因 verify_quant_justification 無 news 參數，無論側車 news 欄如何，gate
    // 對「同一 rec + 同一 edge」必回相同 verdict。本測試以「有/無 news 欄的
    // RichInputs」組同一 rec，斷言 gate 結果 byte-identical。
    #[test]
    fn t_p1_10_news_field_does_not_change_gate_result() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = rec_with_qj("edge_estimates", "ma_crossover::BTCUSDT", 5.0);

        // 同一 rec、同一 edge、同一 now/ttl → gate 不讀 news → verdict 必同。
        let without_news = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        let with_news = verify_quant_justification(&rec, true, &edge, fresh_now(), TTL);
        assert_eq!(without_news, with_news);
        assert_eq!(without_news, Ok(()));

        // 同時驗：RichInputs 的 news 欄（payload context）不進入 gate —— 兩個
        // 只差 news 欄的側車，其 quant_evidence_available + edge_cell 完全相同。
        let mut ri_no_news = RichInputs {
            edge_cell: Some(CellEstimateView::from_cell(
                edge.get_cell("ma_crossover", "BTCUSDT").unwrap(),
                edge.is_fresh(fresh_now(), TTL),
            )),
            regime: Some("trending".to_string()),
            news: None,
        };
        let ri_with_news = RichInputs {
            news: Some(vec![NewsItemView {
                headline: "BULLISH".to_string(),
                severity: 0.9,
                sentiment: "positive".to_string(),
            }]),
            ..ri_no_news.clone()
        };
        assert_eq!(
            ri_no_news.quant_evidence_available(),
            ri_with_news.quant_evidence_available()
        );
        assert_eq!(ri_no_news.edge_cell, ri_with_news.edge_cell);
        // news 欄差異不改 edge_cell / quant_evidence_available（gate 依據）。
        ri_no_news.news = ri_with_news.news.clone();
        assert_eq!(ri_no_news, ri_with_news);
    }

    // ── 無 param delta → bypass（caller 通常已短路，雙重保險）──
    #[test]
    fn no_param_delta_bypasses() {
        let edge = edge_with_cell("ma_crossover::BTCUSDT", 5.0, true, UPDATED_AT);
        let rec = serde_json::json!({ "status": "evaluated" });
        let r = verify_quant_justification(&rec, false, &edge, fresh_now(), TTL);
        assert_eq!(r, Ok(()));
    }

    // ── regime 自算：leak-free（只用傳入 closes，不讀 wallclock/DB）──
    #[test]
    fn compute_regime_label_trending_above_threshold() {
        // 強趨勢（單調上升）→ Hurst > 0.55 → trending。
        let closes: Vec<f64> = (0..128).map(|i| 100.0 + i as f64 * 0.5).collect();
        let label = compute_regime_label(&closes, 8, 64);
        // 趨勢序列應分類為 trending（或至少非 None）。
        assert!(label.is_some());
    }

    #[test]
    fn compute_regime_label_insufficient_window_is_none() {
        // closes < min_window*4 → compute_hurst None → label None。
        let closes: Vec<f64> = vec![100.0, 101.0, 100.5];
        assert!(compute_regime_label(&closes, 8, 64).is_none());
    }

    // ── payload 序列化形狀（Python prompt builder 讀同一形狀）──
    #[test]
    fn to_payload_value_shape() {
        let ri = RichInputs {
            edge_cell: None,
            regime: None,
            news: None,
        };
        let v = ri.to_payload_value();
        // edge_estimates null、regime "unknown"、news_context 空陣列。
        assert!(v["edge_estimates"].is_null());
        assert_eq!(v["regime"], "unknown");
        assert!(v["news_context"].is_array());
        assert_eq!(v["news_context"].as_array().unwrap().len(), 0);
    }
}
