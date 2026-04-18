// MODULE_NOTE
// EN: Severity scorer — keyword × source weighting, no LLM.
//     Phase 5 will replace this with an LLM-based scorer; for now we use a
//     deterministic dictionary so dedup/pipeline can be wired and tested.
// 中文: Severity 評分 — keyword × source 加權，不含 LLM。
//       Phase 5 會換成 LLM 評分，現階段用確定性字典讓 dedup/pipeline 可接線測試。

use crate::news::types::RawNewsItem;
use std::collections::HashMap;

/// EN: Configurable severity scoring weights.
/// 中文: 可設定的 severity 評分權重表。
#[derive(Debug, Clone)]
pub struct SeverityConfig {
    /// EN: keyword (lowercased) → weight contribution.
    /// 中文: 關鍵字（小寫）→ 權重貢獻。
    pub keyword_weights: HashMap<String, f64>,
    /// EN: source name → multiplier (e.g. cryptopanic 1.0, google_news 0.65).
    /// 中文: 來源名稱 → 倍率（cryptopanic 1.0、google_news 0.65 等）。
    pub source_weights: HashMap<String, f64>,
    /// EN: Default source multiplier when source not in table.
    /// 中文: 來源不在表中時使用的預設倍率。
    pub default_source_weight: f64,
}

impl SeverityConfig {
    /// EN: Production default keyword + source weights.
    /// 中文: 生產用預設權重表。
    pub fn defaults() -> Self {
        // EN: Keyword dictionary — high-impact crypto market events.
        // 中文: 關鍵字字典 — 高影響加密市場事件。
        let kw_pairs: &[(&str, f64)] = &[
            ("halving", 0.6),
            ("hack", 0.7),
            ("hacked", 0.7),
            ("exploit", 0.7),
            ("bankruptcy", 0.7),
            ("insolvency", 0.7),
            ("sec", 0.5),
            ("etf", 0.5),
            ("ban", 0.5),
            ("banned", 0.5),
            ("lawsuit", 0.4),
            ("regulation", 0.4),
            ("regulatory", 0.4),
            ("approval", 0.4),
            ("approved", 0.4),
            ("delisting", 0.5),
            ("liquidation", 0.5),
            ("crash", 0.6),
            ("rug", 0.6),
            ("rugpull", 0.7),
            ("investigation", 0.4),
            ("sanction", 0.5),
            ("sanctions", 0.5),
        ];
        let keyword_weights: HashMap<String, f64> =
            kw_pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect();

        // EN: Source weights — paid/curated > free RSS aggregators.
        // 中文: 來源權重 — 付費/精選 > 免費 RSS 聚合器。
        let src_pairs: &[(&str, f64)] = &[
            ("cryptopanic", 1.0),
            ("cointelegraph", 0.85),
            ("rss_cointelegraph", 0.85),
            ("google_news_crypto", 0.65),
            ("rss_google", 0.65),
            ("mock", 1.0),
        ];
        let source_weights: HashMap<String, f64> =
            src_pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect();

        Self {
            keyword_weights,
            source_weights,
            default_source_weight: 0.5,
        }
    }
}

impl Default for SeverityConfig {
    fn default() -> Self {
        Self::defaults()
    }
}

/// EN: Score severity in [0, 1] for a single news item.
///     Formula: clamp(sum(keyword_weight for each keyword found) × source_weight, 0, 1).
///     Match: lowercase substring on `headline + " " + body_excerpt`.
/// 中文: 為單條新聞算 severity (0-1)。
///       公式：clamp(命中關鍵字權重總和 × 來源倍率, 0, 1)。
///       比對方式：在 headline + body_excerpt（皆轉小寫）做 substring 查找。
pub fn score_severity(item: &RawNewsItem, cfg: &SeverityConfig) -> f64 {
    let haystack = format!(
        "{} {}",
        item.headline.to_lowercase(),
        item.body_excerpt.to_lowercase()
    );

    let mut sum = 0.0_f64;
    for (kw, w) in &cfg.keyword_weights {
        if haystack.contains(kw) {
            sum += *w;
        }
    }

    let src_w = cfg
        .source_weights
        .get(&item.source)
        .copied()
        .unwrap_or(cfg.default_source_weight);

    let raw = sum * src_w;
    raw.clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn item(headline: &str, body: &str, source: &str) -> RawNewsItem {
        RawNewsItem {
            headline: headline.into(),
            body_excerpt: body.into(),
            url: "https://example.com/x".into(),
            published_ms: 1_700_000_000_000,
            source: source.into(),
            raw_id: None,
        }
    }

    #[test]
    fn test_severity_no_keywords_returns_zero() {
        // EN: A neutral headline with zero keywords scores 0.
        // 中文: 沒命中任何關鍵字 → 0 分。
        let cfg = SeverityConfig::defaults();
        let it = item(
            "Ethereum gas fees drop slightly today",
            "Average fees fell after a routine update.",
            "cryptopanic",
        );
        assert_eq!(score_severity(&it, &cfg), 0.0);
    }

    #[test]
    fn test_severity_high_keyword_high_score() {
        // EN: "Bitcoin halving" must score ≥ 0.5 from cryptopanic source.
        // 中文: cryptopanic 來源的 "Bitcoin halving" 必須 ≥ 0.5。
        let cfg = SeverityConfig::defaults();
        let it = item(
            "Bitcoin halving expected to drive supply shock",
            "Analysts forecast the upcoming Bitcoin halving will cut issuance.",
            "cryptopanic",
        );
        let s = score_severity(&it, &cfg);
        assert!(s >= 0.5, "expected severity >= 0.5, got {}", s);
    }

    #[test]
    fn test_severity_clamped_to_one() {
        // EN: Many high-weight keywords still cap at 1.0.
        // 中文: 多個高權重關鍵字命中也封頂為 1.0。
        let cfg = SeverityConfig::defaults();
        let it = item(
            "SEC lawsuit hack exploit bankruptcy crash etf approval halving",
            "Multiple regulatory and security events triggered an investigation.",
            "cryptopanic",
        );
        let s = score_severity(&it, &cfg);
        assert!(s <= 1.0 + f64::EPSILON);
        assert!((s - 1.0).abs() < 1e-9, "expected exactly 1.0, got {}", s);
    }

    #[test]
    fn test_severity_source_weight_applied() {
        // EN: Same content, google_news source (0.65) should be lower than cryptopanic (1.0).
        // 中文: 同樣內容，google_news 來源(0.65) 應低於 cryptopanic(1.0)。
        let cfg = SeverityConfig::defaults();
        // EN: Use single keyword "etf"(0.4) so neither side hits the 1.0 clamp.
        // 中文: 用單一關鍵字 "etf"(0.4) 確保雙方都不觸頂。
        let cp = item("ETF news today", "neutral body", "cryptopanic");
        let gn = item("ETF news today", "neutral body", "google_news_crypto");
        let s_cp = score_severity(&cp, &cfg);
        let s_gn = score_severity(&gn, &cfg);
        assert!(
            s_cp > s_gn,
            "cryptopanic ({}) should beat google_news ({})",
            s_cp,
            s_gn
        );
        // EN: Ratio should reflect 0.65 / 1.0.
        // 中文: 比值應反映 0.65 / 1.0。
        assert!((s_gn / s_cp - 0.65).abs() < 1e-9);
    }

    #[test]
    fn test_severity_unknown_source_uses_default() {
        // EN: Unknown source falls back to default_source_weight (0.5).
        // 中文: 未知來源走預設倍率 0.5。
        let cfg = SeverityConfig::defaults();
        let it = item("hack reported", "exploit drained funds", "weird_blog");
        let s = score_severity(&it, &cfg);
        // EN: hack(0.7) + exploit(0.7) = 1.4, × 0.5 = 0.7, clamped fine.
        // 中文: hack(0.7) + exploit(0.7) = 1.4, × 0.5 = 0.7。
        assert!((s - 0.7).abs() < 1e-9, "got {}", s);
    }
}
