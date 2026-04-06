// MODULE_NOTE
// EN: Shared data types for news providers — RawNewsItem (provider output)
//     and ProviderError (fail-closed error variants).
// 中文: 新聞 provider 共用型別 — RawNewsItem（provider 輸出）
//       與 ProviderError（fail-closed 錯誤變體）。

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// EN: A raw news item produced by a provider, before dedup/severity scoring.
/// 中文: provider 產出的原始新聞項目，尚未經過 dedup/severity 評分。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawNewsItem {
    /// EN: Headline / title.  中文: 標題。
    pub headline: String,
    /// EN: Short body excerpt (truncated).  中文: 短摘要（截斷）。
    pub body_excerpt: String,
    /// EN: Canonical article URL.  中文: 文章 URL。
    pub url: String,
    /// EN: Publication time in epoch milliseconds.  中文: 發布時間（epoch ms）。
    pub published_ms: i64,
    /// EN: Provider source name (e.g. "cryptopanic").  中文: provider 來源名稱。
    pub source: String,
    /// EN: Provider-specific raw id (optional).  中文: provider 原始 id（可選）。
    pub raw_id: Option<String>,
}

/// EN: Fail-closed error variants for any NewsProvider implementation.
/// 中文: 所有 NewsProvider 實作的 fail-closed 錯誤變體。
#[derive(Debug, Error)]
pub enum ProviderError {
    /// EN: Network failure (DNS/TCP/TLS/HTTP).  中文: 網路錯誤。
    #[error("network error: {0}")]
    Network(String),
    /// EN: Quota exhausted or polling too fast.  中文: 配額用盡或輪詢過快。
    #[error("rate limited: {0}")]
    RateLimit(String),
    /// EN: Response body could not be parsed.  中文: 回應解析失敗。
    #[error("parse error: {0}")]
    Parse(String),
    /// EN: Required API key / credential missing.  中文: 缺少必要 API key / 憑證。
    #[error("auth missing: {0}")]
    AuthMissing(String),
    /// EN: Misconfiguration (bad URL, empty fields, ...).  中文: 設定錯誤。
    #[error("config error: {0}")]
    ConfigError(String),
}
