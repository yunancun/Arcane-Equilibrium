//! LLM client trait + Anthropic real impl + Mock impl for tests.
//! LLM client trait + Anthropic 真實實作 + 測試用 Mock 實作。
//!
//! MODULE_NOTE (EN): Defines the injectable `LlmClient` trait used by
//!   `ClaudeTeacher`. The real `AnthropicClient` is wired through reqwest,
//!   reads `ANTHROPIC_API_KEY` from env (cross-platform — never hardcoded),
//!   and **fail-closes** when no key is present so dev environments cannot
//!   accidentally burn budget. The `MockClient` returns a fixture verbatim
//!   for unit tests. The trait uses `Pin<Box<Future>>` so it is dyn-compatible
//!   without pulling in the `async-trait` crate.
//! MODULE_NOTE (中): 定義 `ClaudeTeacher` 注入用的 `LlmClient` trait。
//!   真實的 `AnthropicClient` 透過 reqwest 接線，從環境變量讀取
//!   `ANTHROPIC_API_KEY`（跨平台 — 絕不硬編碼），無 key 時 **fail-closed**
//!   以避免 dev 環境誤燒預算。`MockClient` 在單元測試中原樣回傳 fixture。
//!   trait 使用 `Pin<Box<Future>>` 以支援 dyn 物件，避免引入 `async-trait`。

use std::future::Future;
use std::pin::Pin;
use std::time::Duration;
use tracing::{debug, warn};

/// Result of a successful LLM call.
/// LLM 成功呼叫的結果。
#[derive(Debug, Clone)]
pub struct LlmResponse {
    /// JSON string the model returned (will be fed to `parser::parse_directive`).
    /// 模型回傳的 JSON 字串（將傳入 `parser::parse_directive`）。
    pub content_json: String,
    /// Raw provider envelope, persisted into `teacher_directives.content`.
    /// Provider 原始 envelope，會寫進 `teacher_directives.content`。
    pub raw_json: serde_json::Value,
    /// Input tokens consumed (for BudgetTracker.record_usage).
    /// 消耗的 input token 數（給 BudgetTracker.record_usage）。
    pub tokens_in: u32,
    /// Output tokens consumed.
    /// 消耗的 output token 數。
    pub tokens_out: u32,
}

/// Errors the LLM client may return.
/// LLM client 可能回傳的錯誤。
#[derive(Debug)]
pub enum LlmClientError {
    /// `ANTHROPIC_API_KEY` env var missing — fail-closed in dev.
    /// 缺 `ANTHROPIC_API_KEY` 環境變量 — dev 環境 fail-closed。
    MissingApiKey,
    /// HTTP error (network / 5xx / timeout).
    /// HTTP 錯誤（網路 / 5xx / 超時）。
    Http(String),
    /// Provider returned a 4xx with an error body.
    /// Provider 回傳 4xx 帶錯誤 body。
    ProviderError(String),
    /// Response body wasn't valid JSON.
    /// 回應 body 不是有效 JSON。
    InvalidJson(String),
}

impl std::fmt::Display for LlmClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LlmClientError::MissingApiKey => write!(f, "ANTHROPIC_API_KEY not set"),
            LlmClientError::Http(e) => write!(f, "http: {e}"),
            LlmClientError::ProviderError(e) => write!(f, "provider: {e}"),
            LlmClientError::InvalidJson(e) => write!(f, "invalid_json: {e}"),
        }
    }
}

impl std::error::Error for LlmClientError {}

/// Future type returned by `LlmClient::call_with_messages`. Boxed for dyn-compat.
/// `LlmClient::call_with_messages` 回傳的 Future 類型，Box 化以支援 dyn。
pub type LlmFuture<'a> =
    Pin<Box<dyn Future<Output = Result<LlmResponse, LlmClientError>> + Send + 'a>>;

/// Injectable LLM provider abstraction. Implementations must be Send + Sync.
/// 可注入的 LLM provider 抽象。實作必須是 Send + Sync。
pub trait LlmClient: Send + Sync {
    /// Issue a directive-generation request scoped by `scope` (strategy or symbol id).
    /// 發起一次 directive 產生請求，以 `scope` 限定（策略名或 symbol id）。
    fn call_with_messages<'a>(&'a self, scope: &'a str) -> LlmFuture<'a>;
}

// ---------------------------------------------------------------------------
// AnthropicClient — real provider (NEVER called from tests / dev without key)
// AnthropicClient — 真實 provider（無 key 時 dev/測試絕不呼叫）
// ---------------------------------------------------------------------------

/// Real Anthropic Messages API client. Reads API key from env.
/// 真實 Anthropic Messages API client。從環境變量讀取 API key。
pub struct AnthropicClient {
    /// HTTP client with sane timeout.
    /// 帶合理超時的 HTTP client。
    http: reqwest::Client,
    /// API base URL (overridable via `ANTHROPIC_BASE_URL` for proxies / tests).
    /// API base URL（可透過 `ANTHROPIC_BASE_URL` 覆寫，給 proxy / 測試用）。
    base_url: String,
    /// Model id (e.g. `claude-sonnet-4-5`).
    /// 模型 id（如 `claude-sonnet-4-5`）。
    model: String,
}

impl AnthropicClient {
    /// Build a new Anthropic client. Does NOT touch the network.
    /// 構造新的 Anthropic client。不會碰網路。
    pub fn new(model: impl Into<String>) -> Self {
        // Cross-platform: env-driven base URL, never hardcoded.
        // 跨平台：base URL 由環境變量驅動，絕不硬編碼。
        let base_url = std::env::var("ANTHROPIC_BASE_URL")
            .unwrap_or_else(|_| "https://api.anthropic.com".to_string());
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self {
            http,
            base_url,
            model: model.into(),
        }
    }

    /// Returns Ok(api_key) iff env var is non-empty. Fail-closed otherwise.
    /// 環境變量非空時回傳 Ok(api_key)，否則 fail-closed。
    fn require_api_key() -> Result<String, LlmClientError> {
        match std::env::var("ANTHROPIC_API_KEY") {
            Ok(k) if !k.trim().is_empty() => Ok(k),
            _ => Err(LlmClientError::MissingApiKey),
        }
    }
}

impl LlmClient for AnthropicClient {
    fn call_with_messages<'a>(&'a self, scope: &'a str) -> LlmFuture<'a> {
        Box::pin(async move {
            // Fail-closed: no key → no call.
            // fail-closed：無 key → 不呼叫。
            let api_key = Self::require_api_key()?;
            let url = format!("{}/v1/messages", self.base_url);
            let body = serde_json::json!({
                "model": self.model,
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": format!("Generate a directive for scope={scope}")}
                ]
            });

            // One retry on transient failure (timeout / 5xx).
            // 暫時性失敗（超時 / 5xx）重試一次。
            let mut attempt = 0u32;
            loop {
                attempt += 1;
                let resp = self
                    .http
                    .post(&url)
                    .header("x-api-key", &api_key)
                    .header("anthropic-version", "2023-06-01")
                    .header("content-type", "application/json")
                    .json(&body)
                    .send()
                    .await;
                match resp {
                    Ok(r) if r.status().is_success() => {
                        let raw: serde_json::Value = r
                            .json()
                            .await
                            .map_err(|e| LlmClientError::InvalidJson(e.to_string()))?;
                        // Anthropic returns content[0].text — extract for parser.
                        // Anthropic 回傳 content[0].text — 取出給 parser。
                        let content_json =
                            raw["content"][0]["text"].as_str().unwrap_or("").to_string();
                        let tokens_in = raw["usage"]["input_tokens"].as_u64().unwrap_or(0) as u32;
                        let tokens_out = raw["usage"]["output_tokens"].as_u64().unwrap_or(0) as u32;
                        debug!(tokens_in, tokens_out, "anthropic call ok / 呼叫成功");
                        return Ok(LlmResponse {
                            content_json,
                            raw_json: raw,
                            tokens_in,
                            tokens_out,
                        });
                    }
                    Ok(r) => {
                        let status = r.status();
                        let body = r.text().await.unwrap_or_default();
                        if status.is_server_error() && attempt < 2 {
                            warn!(%status, "anthropic 5xx — retrying once / 5xx 重試一次");
                            continue;
                        }
                        return Err(LlmClientError::ProviderError(format!("{status}: {body}")));
                    }
                    Err(e) => {
                        if attempt < 2 {
                            warn!(error = %e, "anthropic transport error — retrying once / 傳輸錯誤重試一次");
                            continue;
                        }
                        return Err(LlmClientError::Http(e.to_string()));
                    }
                }
            }
        })
    }
}

// ---------------------------------------------------------------------------
// MockClient — for unit tests
// MockClient — 單元測試用
// ---------------------------------------------------------------------------

/// Test-only LLM client returning a fixed fixture and token counts.
/// 測試專用 LLM client，回傳固定 fixture 與 token 計數。
pub struct MockClient {
    /// JSON content string the parser will receive.
    /// 將傳給 parser 的 JSON 內容字串。
    content_json: String,
    /// Reported input tokens.
    /// 報告的 input token 數。
    tokens_in: u32,
    /// Reported output tokens.
    /// 報告的 output token 數。
    tokens_out: u32,
}

impl MockClient {
    /// Build a new MockClient with explicit fixture + token counts.
    /// 以顯式 fixture + token 計數構造新的 MockClient。
    pub fn new(content_json: impl Into<String>, tokens_in: u32, tokens_out: u32) -> Self {
        Self {
            content_json: content_json.into(),
            tokens_in,
            tokens_out,
        }
    }
}

impl LlmClient for MockClient {
    fn call_with_messages<'a>(&'a self, _scope: &'a str) -> LlmFuture<'a> {
        let content = self.content_json.clone();
        let tokens_in = self.tokens_in;
        let tokens_out = self.tokens_out;
        Box::pin(async move {
            let raw_json = serde_json::json!({
                "content": [{"text": content}],
                "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out}
            });
            Ok(LlmResponse {
                content_json: content,
                raw_json,
                tokens_in,
                tokens_out,
            })
        })
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // Test 7: AnthropicClient with no API key fails closed.
    // 測試 7：無 API key 的 AnthropicClient fail-closed。
    #[tokio::test]
    async fn test_anthropic_client_no_api_key_fail_closed() {
        // SAFETY: tests run single-threaded per #[tokio::test] runtime,
        // and we restore the env immediately. Cross-platform safe.
        // SAFETY：tokio::test 單執行緒運行，立即還原環境變量，跨平台安全。
        let prev = std::env::var("ANTHROPIC_API_KEY").ok();
        std::env::remove_var("ANTHROPIC_API_KEY");

        let client = AnthropicClient::new("claude-sonnet-4-5");
        let result = client.call_with_messages("test_scope").await;

        if let Some(p) = prev {
            std::env::set_var("ANTHROPIC_API_KEY", p);
        }

        match result {
            Err(LlmClientError::MissingApiKey) => {}
            other => panic!("expected MissingApiKey, got {other:?}"),
        }
    }
}
