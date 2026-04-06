// MODULE_NOTE
// EN: Generic RSS provider backed by `feed-rs`. Two preset constructors
//     wire up CoinTelegraph and Google News crypto search. The fetch path
//     is HTTP-based but tests use `parse_feed_xml()` directly with embedded
//     fixture XML so no network is required.
// 中文: 以 `feed-rs` 為基礎的通用 RSS provider。兩個預設 constructor
//       接 CoinTelegraph 與 Google News 加密貨幣搜尋。fetch 走 HTTP，
//       但測試直接用 `parse_feed_xml()` + 內嵌 fixture XML，免網路。

use super::provider::NewsProvider;
use super::types::{ProviderError, RawNewsItem};
use async_trait::async_trait;
use std::sync::Mutex;

/// EN: Default CoinTelegraph RSS feed.
/// 中文: 預設 CoinTelegraph RSS feed。
pub const COINTELEGRAPH_RSS: &str = "https://cointelegraph.com/rss";

/// EN: Default Google News crypto-search RSS feed.
/// 中文: 預設 Google News 加密貨幣搜尋 RSS feed。
pub const GOOGLE_NEWS_CRYPTO_RSS: &str =
    "https://news.google.com/rss/search?q=cryptocurrency&hl=en-US&gl=US&ceid=US:en";

/// EN: Generic RSS / Atom provider.
/// 中文: 通用 RSS / Atom provider。
pub struct RssProvider {
    name: String,
    url: String,
    /// EN: Last seen ETag for conditional GETs (best-effort cache key).
    /// 中文: 上次看到的 ETag，用於條件式 GET。
    last_etag: Mutex<Option<String>>,
}

impl RssProvider {
    /// EN: Generic constructor.
    /// 中文: 通用 constructor。
    pub fn new(name: impl Into<String>, url: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            url: url.into(),
            last_etag: Mutex::new(None),
        }
    }

    /// EN: Preset for CoinTelegraph.  中文: CoinTelegraph 預設。
    pub fn cointelegraph() -> Self {
        Self::new("cointelegraph", COINTELEGRAPH_RSS)
    }

    /// EN: Preset for Google News crypto search.  中文: Google News 加密貨幣搜尋預設。
    pub fn google_news_crypto() -> Self {
        Self::new("google_news_crypto", GOOGLE_NEWS_CRYPTO_RSS)
    }

    /// EN: Pure parse path — takes raw XML, returns RawNewsItem vec.
    ///     Used by both `fetch()` and unit tests.
    /// 中文: 純解析路徑 — 接收原始 XML，回傳 RawNewsItem 向量。
    ///       fetch() 與單元測試共用。
    pub fn parse_feed_xml(&self, xml: &str) -> Result<Vec<RawNewsItem>, ProviderError> {
        let feed = feed_rs::parser::parse(xml.as_bytes())
            .map_err(|e| ProviderError::Parse(format!("feed-rs parse failed: {}", e)))?;

        let mut items = Vec::with_capacity(feed.entries.len());
        for entry in feed.entries {
            let headline = entry
                .title
                .as_ref()
                .map(|t| t.content.clone())
                .unwrap_or_default();

            let body_excerpt = entry
                .summary
                .as_ref()
                .map(|s| truncate(&s.content, 512))
                .or_else(|| entry.content.as_ref().and_then(|c| c.body.as_ref().map(|b| truncate(b, 512))))
                .unwrap_or_default();

            let url = entry
                .links
                .first()
                .map(|l| l.href.clone())
                .unwrap_or_default();

            let published_ms = entry
                .published
                .or(entry.updated)
                .map(|dt| dt.timestamp_millis())
                .unwrap_or(0);

            items.push(RawNewsItem {
                headline,
                body_excerpt,
                url,
                published_ms,
                source: self.name.clone(),
                raw_id: Some(entry.id.clone()),
            });
        }
        Ok(items)
    }

    /// EN: Test/inspection helper — peek at the cached ETag.
    /// 中文: 測試/檢查 helper — 查看快取的 ETag。
    #[doc(hidden)]
    pub fn cached_etag(&self) -> Option<String> {
        self.last_etag.lock().ok().and_then(|g| g.clone())
    }
}

#[async_trait]
impl NewsProvider for RssProvider {
    async fn fetch(&self) -> Result<Vec<RawNewsItem>, ProviderError> {
        // EN: Build a request and (optionally) attach the cached ETag.
        // 中文: 建構請求，並可選地附上快取的 ETag。
        let client = reqwest::Client::builder()
            .user_agent("openclaw-engine/0.1 news-provider")
            .build()
            .map_err(|e| ProviderError::ConfigError(format!("reqwest client: {}", e)))?;

        let mut req = client.get(&self.url);
        if let Some(etag) = self.last_etag.lock().ok().and_then(|g| g.clone()) {
            req = req.header(reqwest::header::IF_NONE_MATCH, etag);
        }

        let resp = req
            .send()
            .await
            .map_err(|e| ProviderError::Network(e.to_string()))?;

        // EN: 304 Not Modified → no new items.
        // 中文: 304 Not Modified → 沒有新項目。
        if resp.status().as_u16() == 304 {
            return Ok(Vec::new());
        }

        if !resp.status().is_success() {
            return Err(ProviderError::Network(format!(
                "HTTP {} from {}",
                resp.status(),
                self.url
            )));
        }

        // EN: Cache the new ETag for next call.
        // 中文: 快取新的 ETag 給下次使用。
        if let Some(etag) = resp
            .headers()
            .get(reqwest::header::ETAG)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string())
        {
            if let Ok(mut g) = self.last_etag.lock() {
                *g = Some(etag);
            }
        }

        let body = resp
            .text()
            .await
            .map_err(|e| ProviderError::Network(e.to_string()))?;
        self.parse_feed_xml(&body)
    }

    fn name(&self) -> &str {
        &self.name
    }

    fn quota_remaining(&self) -> Option<u32> {
        // EN: Public RSS feeds have no enforced quota.
        // 中文: 公開 RSS feed 沒有固定 quota。
        None
    }
}

/// EN: Truncate to at most `n` chars (char-boundary safe).
/// 中文: 安全截斷至最多 `n` 個字元（char boundary 安全）。
fn truncate(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}
