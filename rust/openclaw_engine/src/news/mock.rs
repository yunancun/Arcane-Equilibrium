// MODULE_NOTE
// EN: Mock provider for unit tests and dev environments. Returns a fixed
//     fixture (or a default 5-item set including high-severity keywords).
// 中文: 給單元測試與 dev 環境用的 mock provider。回傳固定 fixture
//       （或預設 5 條，含 high severity 關鍵字）。

use super::provider::NewsProvider;
use super::types::{ProviderError, RawNewsItem};
use async_trait::async_trait;

/// EN: Mock NewsProvider that replays a fixed fixture.
/// 中文: 重播固定 fixture 的 mock NewsProvider。
pub struct MockProvider {
    fixture: Vec<RawNewsItem>,
}

impl MockProvider {
    /// EN: Construct from caller-supplied fixture.
    /// 中文: 用呼叫端提供的 fixture 建構。
    pub fn with_fixture(fixture: Vec<RawNewsItem>) -> Self {
        Self { fixture }
    }

    /// EN: Construct with the canned 5-item default fixture (incl. high-severity).
    /// 中文: 用內建 5 條預設 fixture 建構（含 high severity）。
    pub fn default_fixture() -> Self {
        Self {
            fixture: Self::canned_items(),
        }
    }

    /// EN: The canned 5-item set. Two contain high-severity keywords
    ///     ("Bitcoin halving", "SEC investigation") so 4-08 severity tests
    ///     can rely on them.
    /// 中文: 內建 5 條集合。其中兩條含 high severity 關鍵字
    ///       （"Bitcoin halving"、"SEC investigation"），供 4-08 severity 測試使用。
    fn canned_items() -> Vec<RawNewsItem> {
        vec![
            RawNewsItem {
                headline: "Bitcoin halving expected to drive supply shock".into(),
                body_excerpt: "Analysts forecast the upcoming Bitcoin halving will reduce miner issuance by 50%.".into(),
                url: "https://example.com/btc-halving".into(),
                published_ms: 1_700_000_000_000,
                source: "mock".into(),
                raw_id: Some("mock-1".into()),
            },
            RawNewsItem {
                headline: "SEC investigation targets major crypto exchange".into(),
                body_excerpt: "The SEC investigation focuses on alleged unregistered securities offerings.".into(),
                url: "https://example.com/sec-probe".into(),
                published_ms: 1_700_000_100_000,
                source: "mock".into(),
                raw_id: Some("mock-2".into()),
            },
            RawNewsItem {
                headline: "Ethereum gas fees drop after upgrade".into(),
                body_excerpt: "Average gas fees fell ~30% following the latest network upgrade.".into(),
                url: "https://example.com/eth-gas".into(),
                published_ms: 1_700_000_200_000,
                source: "mock".into(),
                raw_id: Some("mock-3".into()),
            },
            RawNewsItem {
                headline: "Stablecoin issuer publishes monthly attestation".into(),
                body_excerpt: "Reserves remain fully backed according to the latest report.".into(),
                url: "https://example.com/stable-attest".into(),
                published_ms: 1_700_000_300_000,
                source: "mock".into(),
                raw_id: Some("mock-4".into()),
            },
            RawNewsItem {
                headline: "Layer 2 TVL hits new high".into(),
                body_excerpt: "Total value locked on L2 rollups crossed a new milestone this week.".into(),
                url: "https://example.com/l2-tvl".into(),
                published_ms: 1_700_000_400_000,
                source: "mock".into(),
                raw_id: Some("mock-5".into()),
            },
        ]
    }
}

#[async_trait]
impl NewsProvider for MockProvider {
    async fn fetch(&self) -> Result<Vec<RawNewsItem>, ProviderError> {
        Ok(self.fixture.clone())
    }

    fn name(&self) -> &str {
        "mock"
    }

    fn quota_remaining(&self) -> Option<u32> {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::super::cryptopanic::{
        CryptoPanicProvider, MAX_DAILY_REQUESTS, MIN_POLL_INTERVAL_MS,
    };
    use super::super::provider::NewsProvider;
    use super::super::rss::RssProvider;
    use super::super::types::{ProviderError, RawNewsItem};
    use super::*;

    // ---------- mock ----------

    #[tokio::test]
    async fn test_mock_provider_returns_fixture() {
        // EN: with_fixture returns exactly what was supplied.
        // 中文: with_fixture 回傳完全相同的 fixture。
        let fixture = vec![RawNewsItem {
            headline: "h".into(),
            body_excerpt: "b".into(),
            url: "u".into(),
            published_ms: 42,
            source: "mock".into(),
            raw_id: None,
        }];
        let p = MockProvider::with_fixture(fixture.clone());
        let got = p.fetch().await.expect("fetch ok");
        assert_eq!(got, fixture);
        assert_eq!(p.name(), "mock");
        assert!(p.quota_remaining().is_none());
    }

    #[tokio::test]
    async fn test_mock_provider_default_fixture_5_items() {
        // EN: Default fixture has 5 items, two high-severity headlines.
        // 中文: 預設 fixture 5 條，其中 2 條 high severity 標題。
        let p = MockProvider::default_fixture();
        let items = p.fetch().await.expect("fetch ok");
        assert_eq!(items.len(), 5);
        assert!(items.iter().any(|i| i.headline.contains("Bitcoin halving")));
        assert!(items
            .iter()
            .any(|i| i.headline.contains("SEC investigation")));
    }

    // ---------- cryptopanic ----------

    #[tokio::test]
    async fn test_cryptopanic_no_api_key_returns_auth_missing() {
        // EN: Missing key → fetch() returns AuthMissing, not panic.
        // 中文: 缺 key → fetch() 回 AuthMissing，不 panic。
        let p = CryptoPanicProvider::new(None);
        match p.fetch().await {
            Err(ProviderError::AuthMissing(_)) => (),
            other => panic!("expected AuthMissing, got {:?}", other),
        }
        // EN: Quota remaining still readable when no key set.
        // 中文: 沒 key 時 quota_remaining 仍可讀。
        assert_eq!(p.quota_remaining(), Some(MAX_DAILY_REQUESTS));
    }

    #[test]
    fn test_cryptopanic_url_builds_with_key() {
        // EN: URL builder embeds the key and the public flag.
        // 中文: URL builder 嵌入 key 與 public flag。
        let url = CryptoPanicProvider::build_url("test_key_123");
        assert!(url.contains("auth_token=test_key_123"));
        assert!(url.contains("public=true"));
        assert!(url.starts_with("https://cryptopanic.com/api/v1/posts/"));
    }

    #[test]
    fn test_cryptopanic_quota_enforces_28min_interval() {
        // EN: First call OK, second call within 28min → RateLimit.
        //     Third call after 28min+1s → OK again.
        // 中文: 第一次呼叫 OK，28 分鐘內第二次 → RateLimit。
        //       28 分鐘+1s 後第三次 → 再次 OK。
        let p = CryptoPanicProvider::new(Some("k".into()));
        let t0: u64 = 1_700_000_000_000;
        assert!(p.check_and_record(t0).is_ok(), "first call should succeed");

        // EN: 27 minutes later — still throttled.
        // 中文: 27 分鐘後 — 仍被節流。
        let t1 = t0 + 27 * 60 * 1_000;
        match p.check_and_record(t1) {
            Err(ProviderError::RateLimit(_)) => (),
            other => panic!("expected RateLimit, got {:?}", other),
        }

        // EN: After 28 minutes + 1s — allowed.
        // 中文: 28 分鐘 +1s 後 — 允許。
        let t2 = t0 + MIN_POLL_INTERVAL_MS + 1_000;
        assert!(
            p.check_and_record(t2).is_ok(),
            "after interval should succeed"
        );
        assert_eq!(p.quota_remaining(), Some(MAX_DAILY_REQUESTS - 2));
    }

    #[test]
    fn test_cryptopanic_quota_exhaustion_returns_rate_limit() {
        // EN: Exhausting daily quota returns RateLimit even when interval ok.
        // 中文: 用盡每日 quota 後即使間隔足夠也回 RateLimit。
        let p = CryptoPanicProvider::new(Some("k".into()));
        let mut t = 1_700_000_000_000u64;
        for _ in 0..MAX_DAILY_REQUESTS {
            assert!(p.check_and_record(t).is_ok());
            t += MIN_POLL_INTERVAL_MS + 1;
        }
        assert_eq!(p.quota_remaining(), Some(0));
        match p.check_and_record(t + MIN_POLL_INTERVAL_MS + 1) {
            Err(ProviderError::RateLimit(_)) => (),
            other => panic!("expected RateLimit, got {:?}", other),
        }
    }

    // ---------- rss ----------

    #[test]
    fn test_rss_parses_valid_xml() {
        // EN: Minimal valid RSS 2.0 fixture parses into one item.
        // 中文: 最小有效 RSS 2.0 fixture 解析為 1 條項目。
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>desc</description>
    <item>
      <title>Bitcoin price hits new high</title>
      <link>https://example.com/btc</link>
      <description>BTC has reached a new all-time high.</description>
      <pubDate>Wed, 06 Apr 2026 12:00:00 GMT</pubDate>
      <guid>btc-001</guid>
    </item>
  </channel>
</rss>"#;
        let p = RssProvider::new("test", "https://example.com/rss");
        let items = p.parse_feed_xml(xml).expect("parse ok");
        assert_eq!(items.len(), 1);
        assert!(items[0].headline.contains("Bitcoin price hits new high"));
        assert_eq!(items[0].source, "test");
        assert!(items[0].published_ms > 0);
    }

    #[test]
    fn test_rss_handles_malformed_xml() {
        // EN: Garbage input → ProviderError::Parse, no panic.
        // 中文: 垃圾輸入 → ProviderError::Parse，不 panic。
        let p = RssProvider::new("test", "https://example.com/rss");
        let res = p.parse_feed_xml("<<<not xml>>>");
        match res {
            Err(ProviderError::Parse(_)) => (),
            other => panic!("expected Parse error, got {:?}", other),
        }
    }

    #[test]
    fn test_rss_presets_have_expected_urls() {
        // EN: Preset constructors wire up the documented URLs and names.
        // 中文: 預設 constructor 接到文件中規定的 URL 與名稱。
        let ct = RssProvider::cointelegraph();
        assert_eq!(ct.name(), "cointelegraph");
        let gn = RssProvider::google_news_crypto();
        assert_eq!(gn.name(), "google_news_crypto");
    }

    // ---------- trait object safety ----------

    #[tokio::test]
    async fn test_news_provider_trait_object_safe() {
        // EN: NewsProvider must be object-safe (Box<dyn ...>).
        // 中文: NewsProvider 必須是 object-safe（Box<dyn ...>）。
        let providers: Vec<Box<dyn NewsProvider>> = vec![
            Box::new(MockProvider::default_fixture()),
            Box::new(CryptoPanicProvider::new(None)),
            Box::new(RssProvider::cointelegraph()),
            Box::new(RssProvider::google_news_crypto()),
        ];
        assert_eq!(providers.len(), 4);
        // EN: Each provider exposes a stable name.
        // 中文: 每個 provider 都有穩定名稱。
        let names: Vec<&str> = providers.iter().map(|p| p.name()).collect();
        assert!(names.contains(&"mock"));
        assert!(names.contains(&"cryptopanic"));
        assert!(names.contains(&"cointelegraph"));
        assert!(names.contains(&"google_news_crypto"));

        // EN: Mock fetch through trait object works.
        // 中文: 透過 trait object 呼叫 mock fetch 可成功。
        let mock_items = providers[0].fetch().await.expect("mock fetch ok");
        assert_eq!(mock_items.len(), 5);
    }
}
