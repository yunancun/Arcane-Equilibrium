// MODULE_NOTE
// EN: News provider abstraction layer for Phase 4 task 4-07.
//     Defines `NewsProvider` trait + 4 implementations (CryptoPanic free,
//     CoinTelegraph RSS, Google News RSS, Mock). This module ONLY handles
//     fetching raw news items. Dedup / severity scoring (4-08) and
//     three-tier consumer routing (4-09) are out-of-scope.
// 中文: Phase 4 子任務 4-07 的新聞 provider 抽象層。
//       定義 `NewsProvider` trait + 4 個實作（CryptoPanic free / CoinTelegraph RSS /
//       Google News RSS / Mock）。本模組只做拉取，dedup/severity（4-08）
//       與三層消費路由（4-09）不在本任務範圍。

pub mod cryptopanic;
pub mod dedup;
pub mod mock;
pub mod pipeline;
pub mod provider;
pub mod router;
pub mod rss;
pub mod severity;
pub mod types;

pub use cryptopanic::CryptoPanicProvider;
pub use dedup::DedupCache;
pub use mock::MockProvider;
pub use pipeline::{NewsPipeline, ProcessedNewsItem};
pub use provider::NewsProvider;
pub use router::{
    GuardianHaltCheck, LearningContextSink, NewsRouter, RegimeNewsBuffer,
    GUARDIAN_HALT_THRESHOLD, REGIME_FRESH_AGE_HOURS,
};
pub use rss::RssProvider;
pub use severity::{score_severity, SeverityConfig};
pub use types::{ProviderError, RawNewsItem};
