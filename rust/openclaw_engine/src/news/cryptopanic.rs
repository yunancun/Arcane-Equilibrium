// MODULE_NOTE
// EN: CryptoPanic free-tier provider. Free tier = 50 requests/day, so we
//     enforce a minimum 28-minute polling interval (24h*60min/50 ≈ 28.8min).
//     If quota_used_today >= MAX_DAILY → RateLimit. If api_key missing →
//     AuthMissing. URL builder is unit-tested but the actual HTTP call is
//     NOT exercised in tests (no key, don't burn quota in dev env).
// 中文: CryptoPanic 免費版 provider。免費版 50 req/day，因此強制
//       最少 28 分鐘輪詢間隔（24h*60min/50 ≈ 28.8min）。
//       quota 用盡 → RateLimit；api_key 缺失 → AuthMissing。
//       URL build 邏輯有測試，但實際 HTTP 呼叫不在測試中觸發
//       （沒 key + dev env 不該燒額度）。

use super::provider::NewsProvider;
use super::types::{ProviderError, RawNewsItem};
use async_trait::async_trait;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};

/// EN: CryptoPanic free-tier daily request cap.
/// 中文: CryptoPanic 免費版每日請求上限。
pub const MAX_DAILY_REQUESTS: u32 = 50;

/// EN: Minimum interval between polls in milliseconds (28 min, includes safety margin).
/// 中文: 兩次輪詢的最小間隔（毫秒，28 分鐘，含安全墊）。
pub const MIN_POLL_INTERVAL_MS: u64 = 28 * 60 * 1_000;

/// EN: CryptoPanic free-tier provider.
/// 中文: CryptoPanic 免費版 provider。
pub struct CryptoPanicProvider {
    api_key: Option<String>,
    /// EN: Last request timestamp (epoch ms). 0 = never called.
    /// 中文: 上次請求時間戳（epoch ms）。0 = 從未呼叫。
    last_call_ms: AtomicU64,
    /// EN: Requests used in the current 24h window.
    /// 中文: 當前 24h 窗口已用請求數。
    quota_used_today: AtomicU32,
}

impl CryptoPanicProvider {
    /// EN: Construct from optional API key. None → fetch() returns AuthMissing.
    /// 中文: 從可選 api key 建構。None → fetch() 回傳 AuthMissing。
    pub fn new(api_key: Option<String>) -> Self {
        Self {
            api_key,
            last_call_ms: AtomicU64::new(0),
            quota_used_today: AtomicU32::new(0),
        }
    }

    /// EN: Build the public-feed URL for the free tier.
    /// 中文: 建構免費版 public feed URL。
    pub fn build_url(api_key: &str) -> String {
        format!(
            "https://cryptopanic.com/api/v1/posts/?auth_token={}&public=true",
            api_key
        )
    }

    /// EN: Internal core: validate quota + interval against an injected `now_ms`.
    ///     Pure function so tests can drive a fake clock without sleeping.
    /// 中文: 內部核心：用注入的 `now_ms` 驗證 quota + interval。
    ///       純函式，測試可用假時鐘驅動，無需 sleep。
    pub fn check_and_record(&self, now_ms: u64) -> Result<String, ProviderError> {
        let key = self
            .api_key
            .as_ref()
            .ok_or_else(|| ProviderError::AuthMissing("CRYPTOPANIC_API_KEY not set".into()))?;

        let used = self.quota_used_today.load(Ordering::Relaxed);
        if used >= MAX_DAILY_REQUESTS {
            return Err(ProviderError::RateLimit(format!(
                "daily quota {} exhausted",
                MAX_DAILY_REQUESTS
            )));
        }

        let last = self.last_call_ms.load(Ordering::Relaxed);
        if last != 0 && now_ms.saturating_sub(last) < MIN_POLL_INTERVAL_MS {
            return Err(ProviderError::RateLimit(format!(
                "min interval {}ms not yet elapsed (since={}ms)",
                MIN_POLL_INTERVAL_MS,
                now_ms.saturating_sub(last)
            )));
        }

        // EN: Reserve the slot before the network call.
        // 中文: 在發網路請求前先佔住 slot。
        self.last_call_ms.store(now_ms, Ordering::Relaxed);
        self.quota_used_today.fetch_add(1, Ordering::Relaxed);

        Ok(Self::build_url(key))
    }

    /// EN: Test-only helper to reset the daily quota counter (e.g. midnight rollover).
    /// 中文: 測試用 helper，重設每日 quota 計數器（午夜重置）。
    #[doc(hidden)]
    pub fn reset_daily_quota(&self) {
        self.quota_used_today.store(0, Ordering::Relaxed);
    }
}

#[async_trait]
impl NewsProvider for CryptoPanicProvider {
    async fn fetch(&self) -> Result<Vec<RawNewsItem>, ProviderError> {
        // EN: Validate quota/interval and obtain the URL. We deliberately do
        //     NOT issue the HTTP call here in dev: no key + don't burn quota.
        //     The real HTTP wiring will be added when an API key is provisioned.
        // 中文: 驗證 quota/interval 並取得 URL。dev 環境刻意不發 HTTP 請求：
        //       沒 key + 不該燒額度。等真的有 API key 再接 HTTP 線。
        let now_ms = current_unix_ms();
        let _url = self.check_and_record(now_ms)?;

        // EN: Until a real key is provisioned, return empty (no error).
        //     Replace with reqwest::get(_url) + JSON parse when key arrives.
        // 中文: 真正 key 到位前，回傳空（非錯誤）。
        //       拿到 key 後改成 reqwest::get(_url) + JSON 解析。
        Ok(Vec::new())
    }

    fn name(&self) -> &str {
        "cryptopanic"
    }

    fn quota_remaining(&self) -> Option<u32> {
        let used = self.quota_used_today.load(Ordering::Relaxed);
        Some(MAX_DAILY_REQUESTS.saturating_sub(used))
    }
}

/// EN: Current unix epoch in milliseconds (cross-platform).
/// 中文: 當前 unix epoch（毫秒，跨平台）。
fn current_unix_ms() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}
