//! Wave 5 Packet C / C1 — Slack Incoming Webhook dispatcher。
//!
//! 為什麼：三路通知第一路；operator Q1.2 拍板採 Incoming Webhook URL（拒 Bot
//! Token），避免 OAuth scope 管理；對齊 PA spec §1.1/§1.2。
//!
//! Secret 路徑：`~/BybitOpenClaw/secrets/vault/slack_webhook.json`（0600）
//! Schema:
//!   {
//!     "webhook_url": "https://hooks.slack.com/services/T0XX/B0XX/xxxx",
//!     "channel": "#openclaw-failsafe",        // optional metadata
//!     "username": "OpenClaw Failsafe",        // optional metadata
//!     "fingerprint": "<sha256 of webhook_url>"  // optional fingerprint guard
//!   }
//!
//! 不變量（per CLAUDE.md §二 + spec §1.3）：
//!   - Secret 缺檔 / 解析失敗 → `webhook_url = None`，`send()` 直接回 false
//!     （fail-closed disable，**不是 error**；對齊 `autonomy_totp.py` pattern）；
//!   - HTTP timeout 5s 硬限（PA spec §1.3）；
//!   - 4xx / 429 / 5xx / timeout 一律 false（C1 階段不做 retry —
//!     spec §1.3 max attempts=2 是 watcher 層三路冗餘 + 後續 wave 補；C1 minimal slice
//!     單次 attempt 即可，retry 屬 C4 incident_policy 觸發點責任）；
//!   - 不 panic、不 unwrap；
//!   - HTTPS URL 才允許；http / file / 其他 scheme fail-closed。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §1
//!   - autonomy_totp.py（pattern 對齊）

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

/// Slack secret 檔案 schema（其他欄位允許並忽略）。
#[derive(Debug, Clone, Deserialize)]
struct SlackSecretFile {
    webhook_url: String,
    #[serde(default)]
    #[allow(dead_code)]
    channel: Option<String>,
    #[serde(default)]
    #[allow(dead_code)]
    username: Option<String>,
    #[serde(default)]
    fingerprint: Option<String>,
}

/// Slack blocks markdown payload（per operator Q1.3 拍 PA 預設）。
#[derive(Debug, Serialize)]
struct SlackBlocksPayload<'a> {
    blocks: Vec<SlackBlock<'a>>,
}

#[derive(Debug, Serialize)]
#[serde(tag = "type")]
enum SlackBlock<'a> {
    #[serde(rename = "section")]
    Section { text: SlackText<'a> },
}

#[derive(Debug, Serialize)]
struct SlackText<'a> {
    #[serde(rename = "type")]
    kind: &'a str,
    text: &'a str,
}

/// Slack 派發器。
///
/// `webhook_url == None` 表示 fail-closed disabled（缺 secret / 格式錯 /
/// fingerprint mismatch / scheme 不是 https）。`send` 在 disabled 下直接回 false。
pub struct SlackDispatcher {
    webhook_url: Option<String>,
    http: reqwest::Client,
    timeout: Duration,
}

/// 每次派發的硬 timeout（per PA spec §1.3 line 53 = 5s）。
pub const SLACK_DISPATCH_TIMEOUT: Duration = Duration::from_secs(5);

impl SlackDispatcher {
    /// 從 secret 檔案載入；缺檔 / 解析失敗 / fingerprint mismatch / 非 https →
    /// `webhook_url = None`（disabled）。
    ///
    /// 為什麼用 `&Path` 而非 `&str`：避免呼叫端組路徑時誤把空字串當合法路徑。
    pub fn from_secret_file(path: &Path) -> Self {
        let webhook_url = load_webhook_url(path);
        let http = reqwest::Client::builder()
            .timeout(SLACK_DISPATCH_TIMEOUT)
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self {
            webhook_url,
            http,
            timeout: SLACK_DISPATCH_TIMEOUT,
        }
    }

    /// 預設 secret 路徑：`$HOME/BybitOpenClaw/secrets/vault/slack_webhook.json`
    /// 或環境變數 `OPENCLAW_SLACK_WEBHOOK_FILE` override（測試用）。
    pub fn from_default_path() -> Self {
        Self::from_secret_file(&default_secret_path())
    }

    /// 顯式注入 webhook URL（測試 / 自定義 secret store 才用）。
    ///
    /// 不變量：URL 必 https。否則 disabled。
    pub fn from_explicit_url(url: String) -> Self {
        let webhook_url = if url.starts_with("https://") || url.starts_with("http://localhost") {
            // localhost 開放給 mockito 整合測試；production 真實 URL 必 https
            Some(url)
        } else {
            None
        };
        let http = reqwest::Client::builder()
            .timeout(SLACK_DISPATCH_TIMEOUT)
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self {
            webhook_url,
            http,
            timeout: SLACK_DISPATCH_TIMEOUT,
        }
    }

    /// 是否可派發（secret 有效 + scheme 合法）。
    pub fn is_enabled(&self) -> bool {
        self.webhook_url.is_some()
    }

    /// 派發訊息至 Slack。success = HTTP 2xx；其餘一律 false（fail-soft）。
    ///
    /// 不變量：
    ///   - disabled (no URL) → false；
    ///   - reqwest send / response 任一階段失敗 → false；
    ///   - 不重試（C1 minimal slice）。
    pub async fn send(&self, message: &str) -> bool {
        let url = match &self.webhook_url {
            Some(u) => u,
            None => return false,
        };

        let payload = SlackBlocksPayload {
            blocks: vec![SlackBlock::Section {
                text: SlackText {
                    kind: "mrkdwn",
                    text: message,
                },
            }],
        };

        // reqwest 本身 client timeout 已 5s；再用 tokio::time::timeout 包一層
        // 做雙保險避免某些 transport corner case 卡 connect。
        let send_fut = self.http.post(url).json(&payload).send();
        let response = match tokio::time::timeout(self.timeout, send_fut).await {
            Ok(Ok(resp)) => resp,
            Ok(Err(_)) => return false, // reqwest error（DNS / connect / TLS）
            Err(_) => return false,     // 全局 timeout
        };

        let status = response.status();
        status.is_success()
    }
}

/// 預設 secret 檔位置。允許環境變數 `OPENCLAW_SLACK_WEBHOOK_FILE` override。
///
/// 為什麼提供 env override：integration test 注入 tmpdir secret；production 走 $HOME。
fn default_secret_path() -> PathBuf {
    if let Ok(explicit) = std::env::var("OPENCLAW_SLACK_WEBHOOK_FILE") {
        return PathBuf::from(explicit);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
    PathBuf::from(home)
        .join("BybitOpenClaw")
        .join("secrets")
        .join("vault")
        .join("slack_webhook.json")
}

/// 純函數 — 讀檔解析回 webhook URL 或 None。
///
/// 不變量：
///   - 檔案缺 / 不可讀 / 非 JSON / 缺 `webhook_url` 欄 → None（disabled）；
///   - URL 非 https://hooks.slack.com 與 http://localhost 開頭 → None；
///   - fingerprint 設定但與 sha256(webhook_url) 不匹配 → None。
fn load_webhook_url(path: &Path) -> Option<String> {
    let raw = std::fs::read_to_string(path).ok()?;
    let parsed: SlackSecretFile = serde_json::from_str(&raw).ok()?;
    let url = parsed.webhook_url.trim().to_string();
    if url.is_empty() {
        return None;
    }
    // Production 必 https；test localhost 例外
    let scheme_ok = url.starts_with("https://hooks.slack.com/")
        || url.starts_with("http://localhost")
        || url.starts_with("http://127.0.0.1");
    if !scheme_ok {
        return None;
    }
    // fingerprint guard（per autonomy_totp.json pattern）
    if let Some(expected) = parsed.fingerprint.as_deref() {
        let expected = expected.trim().to_lowercase();
        if !expected.is_empty() {
            let actual = sha256_hex(&url);
            if actual != expected {
                return None;
            }
        }
    }
    Some(url)
}

/// sha256 hex（給 fingerprint guard）。
fn sha256_hex(s: &str) -> String {
    use sha2::Digest;
    let mut hasher = sha2::Sha256::new();
    hasher.update(s.as_bytes());
    hex::encode(hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn write_secret(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::new().expect("tmpfile");
        f.write_all(content.as_bytes()).expect("write");
        f
    }

    // ── T1: missing file → disabled, send returns false ─────────────────────

    #[tokio::test]
    async fn t1_missing_file_disabled() {
        let d = SlackDispatcher::from_secret_file(Path::new("/nonexistent/openclaw_slack.json"));
        assert!(!d.is_enabled());
        let ok = d.send("hello").await;
        assert!(!ok, "disabled dispatcher must return false");
    }

    // ── T2: malformed JSON → disabled ───────────────────────────────────────

    #[tokio::test]
    async fn t2_malformed_json_disabled() {
        let f = write_secret("{ not json");
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(!d.is_enabled());
        assert!(!d.send("x").await);
    }

    // ── T3: missing webhook_url field → disabled ────────────────────────────

    #[tokio::test]
    async fn t3_missing_webhook_field_disabled() {
        let f = write_secret(r##"{"channel":"#x"}"##);
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(!d.is_enabled());
    }

    // ── T4: empty webhook_url → disabled ────────────────────────────────────

    #[tokio::test]
    async fn t4_empty_webhook_url_disabled() {
        let f = write_secret(r#"{"webhook_url":""}"#);
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(!d.is_enabled());
    }

    // ── T5: non-https / non-localhost scheme → disabled ─────────────────────

    #[tokio::test]
    async fn t5_non_https_scheme_disabled() {
        let f = write_secret(r#"{"webhook_url":"http://evil.example.com/hook"}"#);
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(!d.is_enabled(), "non-https external URL must be rejected");
    }

    // ── T6: fingerprint mismatch → disabled ─────────────────────────────────

    #[tokio::test]
    async fn t6_fingerprint_mismatch_disabled() {
        let f = write_secret(
            r#"{"webhook_url":"https://hooks.slack.com/services/T0/B0/xx","fingerprint":"deadbeef"}"#,
        );
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(!d.is_enabled(), "fingerprint mismatch must disable");
    }

    // ── T7: fingerprint matches → enabled ───────────────────────────────────

    #[tokio::test]
    async fn t7_fingerprint_match_enabled() {
        let url = "https://hooks.slack.com/services/T0/B0/xx";
        let fp = sha256_hex(url);
        let content = format!(r#"{{"webhook_url":"{url}","fingerprint":"{fp}"}}"#);
        let f = write_secret(&content);
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(d.is_enabled(), "fingerprint match must enable");
    }

    // ── T8: valid https URL no fingerprint → enabled ────────────────────────

    #[tokio::test]
    async fn t8_valid_https_url_enabled() {
        let f = write_secret(
            r#"{"webhook_url":"https://hooks.slack.com/services/T0/B0/xx"}"#,
        );
        let d = SlackDispatcher::from_secret_file(f.path());
        assert!(d.is_enabled());
    }

    // ── T9: localhost URL allowed (integration test escape hatch) ───────────

    #[tokio::test]
    async fn t9_localhost_url_allowed() {
        let d = SlackDispatcher::from_explicit_url("http://localhost:0/hook".to_string());
        assert!(d.is_enabled());
    }

    // ── T10: from_explicit_url rejects non-https non-localhost ──────────────

    #[tokio::test]
    async fn t10_explicit_url_rejects_unsafe_scheme() {
        let d = SlackDispatcher::from_explicit_url("ftp://evil/".to_string());
        assert!(!d.is_enabled());
    }

    // ── T11: send to unreachable URL returns false (fail-soft) ──────────────

    #[tokio::test]
    async fn t11_unreachable_url_returns_false() {
        // 127.0.0.1:1 通常 connect refused / fail；確保 send 不 panic 不 hang
        let d = SlackDispatcher::from_explicit_url("http://localhost:1/hook".to_string());
        assert!(d.is_enabled());
        let ok = d.send("test").await;
        assert!(!ok, "unreachable URL must return false");
    }

    // ── T12: sha256_hex round-trip ──────────────────────────────────────────

    #[test]
    fn t12_sha256_hex_known_vector() {
        // sha256("abc") = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
        assert_eq!(
            sha256_hex("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
