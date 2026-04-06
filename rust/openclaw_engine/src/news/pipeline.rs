// MODULE_NOTE
// EN: NewsPipeline — orchestrates provider fetch → dedup → severity → DB write.
//     Triple-route consumer fan-out (Guardian / Regime / Learning) belongs to
//     4-09 and is intentionally NOT here.
// 中文: NewsPipeline — 編排 provider 拉取 → 去重 → severity → DB 寫入。
//       三層消費路由（Guardian/Regime/Learning）屬於 4-09，刻意不放這裡。

use crate::database::pool::DbPool;
use crate::news::dedup::DedupCache;
use crate::news::provider::NewsProvider;
use crate::news::router::NewsRouter;
use crate::news::severity::{score_severity, SeverityConfig};
use crate::news::types::RawNewsItem;
use std::sync::Arc;
use tracing::{debug, warn};

/// EN: A news item that has passed dedup and been scored for severity.
/// 中文: 通過去重並完成 severity 評分的新聞項目。
#[derive(Debug, Clone)]
pub struct ProcessedNewsItem {
    pub raw: RawNewsItem,
    pub headline_hash: String,
    pub severity: f64,
}

/// EN: News pipeline — fetch → dedup → score → persist (+ optional 4-09 fan-out).
/// 中文: 新聞管線 — 拉取 → 去重 → 評分 → 寫入（+ 可選 4-09 fan-out）。
pub struct NewsPipeline {
    providers: Vec<Box<dyn NewsProvider>>,
    dedup: DedupCache,
    severity_cfg: SeverityConfig,
    pool: Arc<DbPool>,
    /// EN: Optional triple-route consumer (4-09). When `Some`, every processed
    ///     item is also dispatched to Guardian / Regime / Learning routes.
    /// 中文: 可選的三路消費者（4-09）。為 `Some` 時，每條 processed item 也會
    ///       被分發到 Guardian / Regime / Learning 路由。
    router: Option<Arc<NewsRouter>>,
}

impl NewsPipeline {
    /// EN: Construct with the given providers and DB pool. Uses default 24h
    ///     dedup window and default severity weights.
    /// 中文: 用指定 providers 與 DB pool 建構，預設 24h 去重窗口與預設 severity 權重。
    pub fn new(providers: Vec<Box<dyn NewsProvider>>, pool: Arc<DbPool>) -> Self {
        Self {
            providers,
            dedup: DedupCache::new(),
            severity_cfg: SeverityConfig::defaults(),
            pool,
            router: None,
        }
    }

    /// EN: Override severity config (used by tests / future tuning).
    /// 中文: 覆寫 severity 設定（測試 / 未來調參用）。
    pub fn with_severity_config(mut self, cfg: SeverityConfig) -> Self {
        self.severity_cfg = cfg;
        self
    }

    /// EN: Attach a 4-09 NewsRouter for triple-route fan-out (Guardian / Regime / Learning).
    ///     Without this, `run_once` only does fetch → dedup → score → persist.
    /// 中文: 附加 4-09 NewsRouter 做三路 fan-out（Guardian / Regime / Learning）。
    ///       不附加時，`run_once` 只做拉取 → 去重 → 評分 → 寫入。
    pub fn with_router(mut self, router: Arc<NewsRouter>) -> Self {
        self.router = Some(router);
        self
    }

    /// EN: Pull from all providers, dedup, score, persist. Returns the new
    ///     items that survived dedup (in fetch order). Provider errors are
    ///     logged and skipped — pipeline never panics on a single bad source.
    /// 中文: 從所有 provider 拉取、去重、評分、寫入。返回去重後的新項目（按拉取順序）。
    ///       provider 錯誤只記 log 跳過，單一壞來源不會讓 pipeline panic。
    pub async fn run_once(&self, now_ms: i64) -> Result<Vec<ProcessedNewsItem>, String> {
        let mut processed: Vec<ProcessedNewsItem> = Vec::new();

        for provider in &self.providers {
            match provider.fetch().await {
                Ok(items) => {
                    for raw in items {
                        // EN: Dedup against the 24h sliding window.
                        // 中文: 在 24h 滑動窗口內去重。
                        if !self.dedup.check_and_record(&raw.headline, now_ms) {
                            continue;
                        }
                        let headline_hash = DedupCache::hash_headline(&raw.headline);
                        let severity = score_severity(&raw, &self.severity_cfg);
                        let item = ProcessedNewsItem {
                            raw,
                            headline_hash,
                            severity,
                        };
                        // EN: Persist; failure is logged, item still returned.
                        // 中文: 寫 DB；失敗只 log，項目仍回傳。
                        if let Err(e) = self.persist(&item).await {
                            warn!(provider = provider.name(), error = %e, "news persist failed / 新聞寫入失敗");
                        }
                        processed.push(item);
                    }
                }
                Err(e) => {
                    warn!(provider = provider.name(), error = %e.to_string(), "news provider fetch failed / 新聞 provider 拉取失敗");
                }
            }
        }

        // ── 4-09 fan-out: dispatch each surviving item to the three routes. ──
        // 4-09 fan-out：把每條存活的 item 分發到三條路由。
        if let Some(ref router) = self.router {
            for item in &processed {
                router.dispatch(item, now_ms).await;
            }
        }

        debug!(count = processed.len(), "news pipeline run_once done / 新聞管線本輪完成");
        Ok(processed)
    }

    /// EN: Persist a single processed item to market.news_signals (V002 schema).
    ///     If pool is unavailable, this is a no-op (engine runs without PG).
    /// 中文: 寫單條到 market.news_signals (V002 schema)。
    ///       pool 不可用時為 no-op（無 PG 也能跑引擎）。
    async fn persist(&self, item: &ProcessedNewsItem) -> Result<(), String> {
        let pg = match self.pool.get() {
            Some(p) => p,
            None => return Ok(()),
        };

        // EN: Map RawNewsItem → V002 columns. Sentiment / confidence / cost
        //     are NULL/0 for now (Phase 5 LLM scorer will fill them).
        // 中文: RawNewsItem → V002 欄位映射。sentiment/confidence/cost 暫 NULL/0
        //       （Phase 5 LLM 評分器會補上）。
        let ts = chrono::DateTime::from_timestamp_millis(item.raw.published_ms)
            .unwrap_or_else(chrono::Utc::now);
        let severity_f32 = item.severity as f32;
        let summary = if item.raw.body_excerpt.is_empty() {
            item.raw.headline.clone()
        } else {
            item.raw.body_excerpt.clone()
        };

        let res = sqlx::query(
            "INSERT INTO market.news_signals \
             (ts, source, source_url, severity, severity_source, category, \
              affected_symbols, is_market_wide, sentiment, confidence, summary, \
              raw_content, ai_model_used, processing_cost_usd, attributed_trade_count) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
        )
        .bind(ts)
        .bind(item.raw.source.as_str())
        .bind(item.raw.url.as_str())
        .bind(severity_f32)
        .bind("keyword_v1") // EN: severity_source — deterministic dictionary. 中文: 確定性字典。
        .bind("uncategorized") // EN: category — Phase 5 LLM will tag. 中文: Phase 5 LLM 會標。
        .bind::<Vec<String>>(Vec::new()) // EN: affected_symbols. 中文: 受影響幣種。
        .bind(false) // EN: is_market_wide. 中文: 是否市場廣泛。
        .bind(Option::<f32>::None) // sentiment
        .bind(Option::<f32>::None) // confidence
        .bind(summary.as_str())
        .bind(Option::<&str>::None) // raw_content
        .bind(Option::<&str>::None) // ai_model_used
        .bind(0.0_f64) // processing_cost_usd
        .bind(0_i32) // attributed_trade_count
        .execute(pg)
        .await;

        match res {
            Ok(_) => {
                self.pool.record_success();
                Ok(())
            }
            Err(e) => {
                self.pool.record_failure();
                Err(e.to_string())
            }
        }
    }

    /// EN: Expose the dedup cache size for tests / metrics.
    /// 中文: 暴露去重快取大小供測試 / 指標使用。
    pub fn dedup_cache_size(&self) -> usize {
        self.dedup.cache_size()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;
    use crate::news::mock::MockProvider;
    use crate::news::types::ProviderError;
    use async_trait::async_trait;

    async fn empty_pool() -> Arc<DbPool> {
        // EN: Pool with empty URL → is_available()=false → persist is no-op.
        // 中文: 空 URL pool → 不可用 → persist 為 no-op。
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    fn raw(headline: &str, source: &str, ms: i64) -> RawNewsItem {
        RawNewsItem {
            headline: headline.into(),
            body_excerpt: "body text here".into(),
            url: "https://example.com/x".into(),
            published_ms: ms,
            source: source.into(),
            raw_id: None,
        }
    }

    /// EN: Mock provider that returns a caller-supplied vec.
    /// 中文: 回傳呼叫端提供 vec 的 mock provider。
    struct VecProvider {
        items: Vec<RawNewsItem>,
        name: String,
    }

    #[async_trait]
    impl NewsProvider for VecProvider {
        async fn fetch(&self) -> Result<Vec<RawNewsItem>, ProviderError> {
            Ok(self.items.clone())
        }
        fn name(&self) -> &str {
            &self.name
        }
        fn quota_remaining(&self) -> Option<u32> {
            None
        }
    }

    #[tokio::test]
    async fn test_pipeline_dedup_blocks_repeat_in_same_run() {
        // EN: Two identical headlines from one provider → only one survives.
        // 中文: 同一 provider 兩條相同標題 → 只留一條。
        let pool = empty_pool().await;
        let prov = VecProvider {
            name: "vec".into(),
            items: vec![
                raw("Bitcoin halving incoming", "cryptopanic", 1_700_000_000_000),
                raw("Bitcoin halving incoming", "cryptopanic", 1_700_000_001_000),
                raw("Different story entirely", "cryptopanic", 1_700_000_002_000),
            ],
        };
        let pipe = NewsPipeline::new(vec![Box::new(prov)], pool);
        let out = pipe.run_once(1_700_000_010_000).await.expect("ok");
        assert_eq!(out.len(), 2);
    }

    #[tokio::test]
    async fn test_pipeline_severity_attached_to_processed_item() {
        // EN: High-severity headline gets a non-zero severity in the output.
        // 中文: 高 severity 標題輸出 severity > 0。
        let pool = empty_pool().await;
        let prov = MockProvider::default_fixture();
        let pipe = NewsPipeline::new(vec![Box::new(prov)], pool);
        let out = pipe.run_once(1_700_000_500_000).await.expect("ok");
        assert_eq!(out.len(), 5);
        let halving = out
            .iter()
            .find(|p| p.raw.headline.contains("Bitcoin halving"))
            .expect("halving present");
        assert!(halving.severity > 0.0);
        let sec = out
            .iter()
            .find(|p| p.raw.headline.contains("SEC investigation"))
            .expect("sec present");
        assert!(sec.severity > 0.0);
        // EN: Each processed item carries a 16-char hash.
        // 中文: 每條 processed item 帶 16 字 hash。
        for p in &out {
            assert_eq!(p.headline_hash.len(), 16);
        }
    }

    #[tokio::test]
    async fn test_pipeline_run_once_with_mock_provider_no_pg() {
        // EN: With pool unavailable, run_once still returns processed items
        //     (persist is a silent no-op).
        // 中文: pool 不可用時 run_once 仍返回 processed items（persist 靜默 no-op）。
        let pool = empty_pool().await;
        assert!(!pool.is_available());
        let pipe = NewsPipeline::new(
            vec![Box::new(MockProvider::default_fixture())],
            pool,
        );
        let out = pipe.run_once(1_700_000_500_000).await.expect("ok");
        assert_eq!(out.len(), 5);
        assert_eq!(pipe.dedup_cache_size(), 5);
    }

    #[tokio::test]
    async fn test_pipeline_dedup_high_hit_rate() {
        // EN: 20 items, 19 duplicates → ≥ 95% dedup hit rate.
        // 中文: 20 條輸入、19 條重複 → 去重命中率 ≥ 95%。
        let pool = empty_pool().await;
        let mut items = Vec::new();
        for i in 0..20 {
            items.push(raw("Same headline repeated", "cryptopanic", 1_700_000_000_000 + i));
        }
        let prov = VecProvider {
            name: "vec".into(),
            items,
        };
        let pipe = NewsPipeline::new(vec![Box::new(prov)], pool);
        let out = pipe.run_once(1_700_000_100_000).await.expect("ok");
        assert_eq!(out.len(), 1);
        // EN: Hit rate = 19/20 = 0.95.
        // 中文: 命中率 = 19/20 = 0.95。
        let hit_rate = (20 - out.len()) as f64 / 20.0;
        assert!(hit_rate >= 0.95);
    }
}
