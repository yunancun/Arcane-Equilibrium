// MODULE_NOTE
// EN: NewsProvider trait — abstract interface every news source implements.
//     Object-safe so collections of `Box<dyn NewsProvider>` are allowed.
// 中文: NewsProvider trait — 所有新聞來源實作的抽象介面。
//       設計為 object-safe，允許 `Box<dyn NewsProvider>` 集合。

use super::types::{ProviderError, RawNewsItem};
use async_trait::async_trait;

/// EN: Abstract news provider. Implementations only fetch raw items;
///     no dedup, no severity scoring, no DB write — those belong to 4-08/4-09.
/// 中文: 抽象新聞 provider。實作僅負責拉取原始項目；
///       不做 dedup、不做 severity、不寫 DB —— 那些屬於 4-08/4-09。
#[async_trait]
pub trait NewsProvider: Send + Sync {
    /// EN: Fetch the latest batch of raw news items.
    /// 中文: 拉取最新一批原始新聞項目。
    async fn fetch(&self) -> Result<Vec<RawNewsItem>, ProviderError>;

    /// EN: Stable provider name (used as `source` field downstream).
    /// 中文: 穩定的 provider 名稱（下游做為 source 欄位）。
    fn name(&self) -> &str;

    /// EN: Remaining quota for the current window, if known.
    /// 中文: 當前窗口剩餘配額（若已知）。
    fn quota_remaining(&self) -> Option<u32>;
}
