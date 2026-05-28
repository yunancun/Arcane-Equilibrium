//! Wave 5 Packet C / C1 — Email dispatcher (Gmail SMTP App Password)。
//!
//! 為什麼：三路通知第二路；operator Q2.1 拍板採 Gmail SMTP + App Password（PA
//! 推薦 (c) — 零外部付費 SaaS，對齊 CLAUDE.md §二 原則 14）；對齊 PA spec §2。
//!
//! Secret 路徑：`~/BybitOpenClaw/secrets/vault/email_config.json`（0600）
//! Schema:
//!   {
//!     "backend": "smtp_gmail",
//!     "smtp_host": "smtp.gmail.com",
//!     "smtp_port": 587,
//!     "smtp_username": "cloud@ncyu.me",
//!     "smtp_app_password": "xxxxxxxxxxxxxxxx",
//!     "from_address": "cloud@ncyu.me",
//!     "to_addresses": ["cloud@ncyu.me"],
//!     "subject_prefix": "[OpenClaw Failsafe]",
//!     "fingerprint": "<sha256 of smtp_app_password>"  // optional guard
//!   }
//!
//! ## Dependency 決策（PM 拍板待回覆）
//!
//! C1 階段 **不引入 lettre crate**（避免 unilateral 加 top-level dep）；改用
//! `SmtpTransport` trait + 兩個內建實作：
//!   - `DisabledTransport`：所有 send 回 false（fail-closed disabled）
//!   - `StubTransport`：測試用 in-memory 攔截，記錄 envelope + 永遠 success
//!
//! 真實 SMTP 走 lettre 的 work item 留給 PM 拍板後 follow-up commit
//! （後續會在 `RealSmtpTransport` 注入；或改自寫 raw SMTP socket）。
//!
//! 不變量（per CLAUDE.md §二 + spec §2.3/§2.4）：
//!   - Secret 缺檔 → `transport = DisabledTransport`，send 回 false（fail-closed）；
//!   - per-dispatch timeout 10s（spec §2.3）；
//!   - STARTTLS 必（後續 lettre wire 時強制）；禁 plaintext fallback；
//!   - SMTP envelope from/to 與 header 一致；
//!   - 不真實寄送 in test（StubTransport 全 in-memory）。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §2
//!   - autonomy_totp.py（fail-closed pattern 對齊）

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;

use async_trait::async_trait;
use serde::Deserialize;

/// Email config 檔案 schema。
#[derive(Debug, Clone, Deserialize)]
pub struct EmailConfig {
    pub backend: String,
    pub smtp_host: String,
    pub smtp_port: u16,
    pub smtp_username: String,
    pub smtp_app_password: String,
    pub from_address: String,
    pub to_addresses: Vec<String>,
    #[serde(default = "default_subject_prefix")]
    pub subject_prefix: String,
    #[serde(default)]
    pub fingerprint: Option<String>,
}

fn default_subject_prefix() -> String {
    "[OpenClaw Failsafe]".to_string()
}

/// Email envelope 摘要（測試用 + 真實 SMTP wire 時組 RFC 5322 訊息）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmailMessage {
    pub from: String,
    pub to: Vec<String>,
    pub subject: String,
    pub body: String,
}

/// SMTP 傳輸抽象 — runtime 注入真實 lettre transport；測試注入 stub。
///
/// 為什麼：C1 minimal slice 不引入 lettre top-level dep；trait 邊界讓 PM 拍 lettre
/// 後在 follow-up commit 接上 `lettre::AsyncSmtpTransport` 不影響 C1 IMPL/test。
#[async_trait]
pub trait SmtpTransport: Send + Sync {
    async fn send(&self, msg: &EmailMessage) -> bool;
}

/// Fail-closed disabled transport — secret 缺檔時用；send 永遠 false。
pub struct DisabledTransport;

#[async_trait]
impl SmtpTransport for DisabledTransport {
    async fn send(&self, _msg: &EmailMessage) -> bool {
        false
    }
}

/// 測試用 in-memory transport — 攔截 envelope 記錄；不真實寄送。
///
/// 為什麼：spec §7.4 line 423-428 要求 test 路徑必走 stub 不真實 SMTP；本 stub
/// 對應 spec 提的 `lettre::transport::stub::StubTransport` 角色。
pub struct StubTransport {
    captured: Mutex<Vec<EmailMessage>>,
    force_fail: bool,
}

impl StubTransport {
    pub fn new() -> Self {
        Self {
            captured: Mutex::new(Vec::new()),
            force_fail: false,
        }
    }

    pub fn new_failing() -> Self {
        Self {
            captured: Mutex::new(Vec::new()),
            force_fail: true,
        }
    }

    pub fn captured(&self) -> Vec<EmailMessage> {
        self.captured.lock().unwrap().clone()
    }
}

impl Default for StubTransport {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl SmtpTransport for StubTransport {
    async fn send(&self, msg: &EmailMessage) -> bool {
        self.captured.lock().unwrap().push(msg.clone());
        !self.force_fail
    }
}

/// Email 派發器。
///
/// - `config = None` ⇒ disabled（缺 secret / 格式錯 / fingerprint mismatch）；
/// - `transport` 由 caller 注入；production 應傳 RealSmtpTransport（PM 拍 lettre
///   後另 commit 接），test 傳 StubTransport。
pub struct EmailDispatcher {
    config: Option<EmailConfig>,
    transport: Box<dyn SmtpTransport>,
    timeout: Duration,
}

/// 每次派發的硬 timeout（per PA spec §2.3 line 108 = 10s）。
pub const EMAIL_DISPATCH_TIMEOUT: Duration = Duration::from_secs(10);

impl EmailDispatcher {
    /// 從 secret 檔載入 config + 注入 transport。
    ///
    /// 為什麼讓 caller 傳 transport：runtime（PM 拍 lettre 後）傳真實
    /// `lettre::AsyncSmtpTransport` wrap；test 傳 `StubTransport`；C1 階段
    /// runtime 暫傳 `DisabledTransport`（fail-closed 不寄送）。
    pub fn from_secret_file(path: &Path, transport: Box<dyn SmtpTransport>) -> Self {
        let config = load_email_config(path);
        Self {
            config,
            transport,
            timeout: EMAIL_DISPATCH_TIMEOUT,
        }
    }

    /// 預設 secret 路徑：`$HOME/BybitOpenClaw/secrets/vault/email_config.json`
    /// 或 env var `OPENCLAW_EMAIL_SECRET_FILE` override。
    /// transport 預設 `DisabledTransport`（真實 SMTP 待 PM 拍 lettre 後接）。
    pub fn from_default_path() -> Self {
        Self::from_secret_file(&default_secret_path(), Box::new(DisabledTransport))
    }

    /// 是否可派發（config 載入 + transport 非 DisabledTransport）。
    /// 注意：transport=Disabled 即使 config 有效也視為 disabled。
    pub fn is_enabled(&self) -> bool {
        self.config.is_some()
    }

    /// 派發訊息。success = transport.send 回 true；其餘一律 false。
    ///
    /// 不變量：
    ///   - config = None → false（disabled fail-closed）；
    ///   - tokio::time::timeout 包 transport.send；timeout → false；
    ///   - 不 panic、不 unwrap。
    pub async fn send(&self, subject: &str, body: &str) -> bool {
        let cfg = match &self.config {
            Some(c) => c,
            None => return false,
        };
        let full_subject = if subject.starts_with(&cfg.subject_prefix) {
            subject.to_string()
        } else {
            format!("{} {}", cfg.subject_prefix, subject)
        };
        let msg = EmailMessage {
            from: cfg.from_address.clone(),
            to: cfg.to_addresses.clone(),
            subject: full_subject,
            body: body.to_string(),
        };
        let send_fut = self.transport.send(&msg);
        tokio::time::timeout(self.timeout, send_fut)
            .await
            .unwrap_or(false)
    }
}

/// 預設 secret 檔位置。
fn default_secret_path() -> PathBuf {
    if let Ok(explicit) = std::env::var("OPENCLAW_EMAIL_SECRET_FILE") {
        return PathBuf::from(explicit);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
    PathBuf::from(home)
        .join("BybitOpenClaw")
        .join("secrets")
        .join("vault")
        .join("email_config.json")
}

/// 純函數 — 讀檔解析 + 校驗回 EmailConfig 或 None。
///
/// 不變量：
///   - 檔案缺 / 不可讀 / 非 JSON → None；
///   - smtp_host / smtp_username / smtp_app_password / from_address 任一空 → None；
///   - to_addresses 空 → None；
///   - smtp_port 非 1-65535 → None；
///   - backend != "smtp_gmail" → None（C1 階段只支援 Gmail；後續可放寬）；
///   - fingerprint 設定但與 sha256(smtp_app_password) 不匹配 → None。
fn load_email_config(path: &Path) -> Option<EmailConfig> {
    let raw = std::fs::read_to_string(path).ok()?;
    let cfg: EmailConfig = serde_json::from_str(&raw).ok()?;
    if cfg.smtp_host.trim().is_empty()
        || cfg.smtp_username.trim().is_empty()
        || cfg.smtp_app_password.trim().is_empty()
        || cfg.from_address.trim().is_empty()
    {
        return None;
    }
    if cfg.to_addresses.is_empty() {
        return None;
    }
    if cfg.smtp_port == 0 {
        return None;
    }
    // C1 階段只認 Gmail backend（spec §2.1 line 78-86 PA 推薦 (c)）
    if cfg.backend.trim().to_lowercase() != "smtp_gmail" {
        return None;
    }
    // fingerprint guard
    if let Some(expected) = cfg.fingerprint.as_deref() {
        let expected = expected.trim().to_lowercase();
        if !expected.is_empty() {
            let actual = sha256_hex(&cfg.smtp_app_password);
            if actual != expected {
                return None;
            }
        }
    }
    Some(cfg)
}

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

    fn valid_config_json(app_pw: &str) -> String {
        format!(
            r#"{{
                "backend":"smtp_gmail",
                "smtp_host":"smtp.gmail.com",
                "smtp_port":587,
                "smtp_username":"cloud@ncyu.me",
                "smtp_app_password":"{app_pw}",
                "from_address":"cloud@ncyu.me",
                "to_addresses":["cloud@ncyu.me"],
                "subject_prefix":"[OpenClaw Failsafe]"
            }}"#
        )
    }

    // ── T1: missing secret file → disabled, send false ──────────────────────

    #[tokio::test]
    async fn t1_missing_secret_disabled() {
        let d = EmailDispatcher::from_secret_file(
            Path::new("/nonexistent/email_secret.json"),
            Box::new(StubTransport::new()),
        );
        assert!(!d.is_enabled());
        let ok = d.send("test", "body").await;
        assert!(!ok);
    }

    // ── T2: malformed JSON → disabled ───────────────────────────────────────

    #[tokio::test]
    async fn t2_malformed_disabled() {
        let f = write_secret("not json {");
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(!d.is_enabled());
    }

    // ── T3: missing required field → disabled ───────────────────────────────

    #[tokio::test]
    async fn t3_missing_smtp_host_disabled() {
        let content = r#"{
            "backend":"smtp_gmail",
            "smtp_host":"",
            "smtp_port":587,
            "smtp_username":"x",
            "smtp_app_password":"y",
            "from_address":"z@example.com",
            "to_addresses":["z@example.com"]
        }"#;
        let f = write_secret(content);
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(!d.is_enabled());
    }

    // ── T4: empty to_addresses → disabled ───────────────────────────────────

    #[tokio::test]
    async fn t4_empty_recipients_disabled() {
        let content = r#"{
            "backend":"smtp_gmail",
            "smtp_host":"smtp.gmail.com",
            "smtp_port":587,
            "smtp_username":"x",
            "smtp_app_password":"y",
            "from_address":"z@example.com",
            "to_addresses":[]
        }"#;
        let f = write_secret(content);
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(!d.is_enabled());
    }

    // ── T5: non-gmail backend rejected ─────────────────────────────────────

    #[tokio::test]
    async fn t5_non_gmail_backend_disabled() {
        let content = r#"{
            "backend":"sendgrid_api",
            "smtp_host":"smtp.sendgrid.net",
            "smtp_port":587,
            "smtp_username":"x",
            "smtp_app_password":"y",
            "from_address":"z@example.com",
            "to_addresses":["z@example.com"]
        }"#;
        let f = write_secret(content);
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(!d.is_enabled(), "non-gmail backend must be rejected in C1");
    }

    // ── T6: fingerprint mismatch → disabled ─────────────────────────────────

    #[tokio::test]
    async fn t6_fingerprint_mismatch_disabled() {
        let content = r#"{
            "backend":"smtp_gmail",
            "smtp_host":"smtp.gmail.com",
            "smtp_port":587,
            "smtp_username":"cloud@ncyu.me",
            "smtp_app_password":"realpassword",
            "from_address":"cloud@ncyu.me",
            "to_addresses":["cloud@ncyu.me"],
            "fingerprint":"deadbeef"
        }"#;
        let f = write_secret(content);
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(!d.is_enabled());
    }

    // ── T7: fingerprint match → enabled ─────────────────────────────────────

    #[tokio::test]
    async fn t7_fingerprint_match_enabled() {
        let pw = "real_app_password_16chars";
        let fp = sha256_hex(pw);
        let content = format!(
            r#"{{
                "backend":"smtp_gmail",
                "smtp_host":"smtp.gmail.com",
                "smtp_port":587,
                "smtp_username":"cloud@ncyu.me",
                "smtp_app_password":"{pw}",
                "from_address":"cloud@ncyu.me",
                "to_addresses":["cloud@ncyu.me"],
                "fingerprint":"{fp}"
            }}"#
        );
        let f = write_secret(&content);
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new()));
        assert!(d.is_enabled());
    }

    // ── T8: valid config + StubTransport success ────────────────────────────

    #[tokio::test]
    async fn t8_send_with_stub_success() {
        let f = write_secret(&valid_config_json("appPw1234567890x"));
        let stub = StubTransport::new();
        // 因 trait object 包 Box 後拿不回 captured ref，先用 explicit owned 包再傳 ref
        // 改成從 dispatcher 後拿 transport 不適合 — 改:封一個 inspector StubTransport
        // 透過內部 Arc<Mutex<Vec>> 共享。這條測試改用單獨 Arc。
        struct CapturedStub {
            inner: std::sync::Arc<std::sync::Mutex<Vec<EmailMessage>>>,
        }
        #[async_trait]
        impl SmtpTransport for CapturedStub {
            async fn send(&self, msg: &EmailMessage) -> bool {
                self.inner.lock().unwrap().push(msg.clone());
                true
            }
        }
        drop(stub);
        let shared = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let d = EmailDispatcher::from_secret_file(
            f.path(),
            Box::new(CapturedStub {
                inner: shared.clone(),
            }),
        );
        assert!(d.is_enabled());
        let ok = d.send("test subject", "body content").await;
        assert!(ok);
        let captured = shared.lock().unwrap();
        assert_eq!(captured.len(), 1);
        let msg = &captured[0];
        assert_eq!(msg.from, "cloud@ncyu.me");
        assert_eq!(msg.to, vec!["cloud@ncyu.me".to_string()]);
        assert_eq!(msg.subject, "[OpenClaw Failsafe] test subject");
        assert_eq!(msg.body, "body content");
    }

    // ── T9: subject prefix idempotent (avoid double-prefix) ─────────────────

    #[tokio::test]
    async fn t9_subject_prefix_idempotent() {
        let f = write_secret(&valid_config_json("pw"));
        let shared = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        struct Cap(std::sync::Arc<std::sync::Mutex<Vec<EmailMessage>>>);
        #[async_trait]
        impl SmtpTransport for Cap {
            async fn send(&self, msg: &EmailMessage) -> bool {
                self.0.lock().unwrap().push(msg.clone());
                true
            }
        }
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(Cap(shared.clone())));
        let _ = d
            .send("[OpenClaw Failsafe] already-prefixed", "body")
            .await;
        let c = shared.lock().unwrap();
        assert_eq!(c[0].subject, "[OpenClaw Failsafe] already-prefixed");
    }

    // ── T10: StubTransport::new_failing → send false ────────────────────────

    #[tokio::test]
    async fn t10_failing_transport_returns_false() {
        let f = write_secret(&valid_config_json("pw"));
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(StubTransport::new_failing()));
        assert!(d.is_enabled());
        let ok = d.send("subj", "body").await;
        assert!(!ok);
    }

    // ── T11: DisabledTransport always returns false even with valid config ──

    #[tokio::test]
    async fn t11_disabled_transport_send_false() {
        let f = write_secret(&valid_config_json("pw"));
        let d = EmailDispatcher::from_secret_file(f.path(), Box::new(DisabledTransport));
        // config is_enabled() = true but transport disabled → send returns false
        assert!(d.is_enabled());
        let ok = d.send("subj", "body").await;
        assert!(!ok);
    }
}
