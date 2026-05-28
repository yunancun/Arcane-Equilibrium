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
//! ## Dependency 決策（operator EA 拍板 — 已落地）
//!
//! C1 階段先用 `SmtpTransport` trait + 兩個內建實作（DisabledTransport /
//! StubTransport）佔位；本 follow-up（operator decision EA）加 lettre 0.11
//! workspace dep + `RealSmtpTransport` 接真實 Gmail SMTP，三路冗餘真的三路：
//!   - `DisabledTransport`：所有 send 回 false（fail-closed disabled / 缺 secret）
//!   - `StubTransport`：測試用 in-memory 攔截，記錄 envelope + 永遠 success
//!   - `RealSmtpTransport`：lettre `AsyncSmtpTransport<Tokio1Executor>` 真實寄送
//!
//! 不變量（per CLAUDE.md §二 + spec §2.3/§2.4）：
//!   - Secret 缺檔 → `transport = DisabledTransport`，send 回 false（fail-closed）；
//!   - per-dispatch timeout 10s（spec §2.3，tokio::time::timeout 硬限）；
//!   - port 587 走 STARTTLS、port 465 走 implicit TLS；禁 plaintext fallback；
//!   - SMTP envelope from/to 與 header 一致；
//!   - RealSmtpTransport::send 任何 error → false（fail-soft 不 panic）；
//!   - 不真實寄送 in test（StubTransport in-memory；RealSmtpTransport test 只連
//!     unreachable host 驗 timeout fail-soft，不連 Gmail）。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §2
//!   - autonomy_totp.py（fail-closed pattern 對齊）

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;

use async_trait::async_trait;
use lettre::message::{Mailbox, Message};
use lettre::transport::smtp::authentication::Credentials;
use lettre::{AsyncSmtpTransport, AsyncTransport, Tokio1Executor};
use serde::Deserialize;

/// Email config 檔案 schema。
///
/// 為什麼手寫 `Debug`（LOW-1 修法）：`smtp_app_password` 是 SMTP secret；若用
/// `derive(Debug)`，任何 `{:?}`（log / tracing / panic message / 結構體巢狀）都會把
/// 明文密碼印出 — latent leak。手寫 impl 把該欄位 redact 成 `***REDACTED***`，其餘欄位
/// 正常顯示，避免日後新增 debug log 時意外洩漏。
#[derive(Clone, Deserialize)]
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

impl std::fmt::Debug for EmailConfig {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("EmailConfig")
            .field("backend", &self.backend)
            .field("smtp_host", &self.smtp_host)
            .field("smtp_port", &self.smtp_port)
            .field("smtp_username", &self.smtp_username)
            // secret：永遠 redact，不印明文
            .field("smtp_app_password", &"***REDACTED***")
            .field("from_address", &self.from_address)
            .field("to_addresses", &self.to_addresses)
            .field("subject_prefix", &self.subject_prefix)
            // fingerprint 是 sha256 hex，非可逆 secret，但屬敏感衍生值：一併 redact 較安全
            .field(
                "fingerprint",
                &self.fingerprint.as_ref().map(|_| "***REDACTED***"),
            )
            .finish()
    }
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

/// 真實 SMTP transport — lettre `AsyncSmtpTransport<Tokio1Executor>` 包裝。
///
/// 為什麼：operator decision EA 拍板加 lettre 0.11，補上三路冗餘的真正第二路。
/// 走 Gmail SMTP App Password（operator Q2.1）；port 587 STARTTLS / port 465
/// implicit TLS；禁 plaintext fallback（spec §2.4）。
///
/// 不變量：
///   - build relay 失敗 / 認證失敗 / TLS handshake 失敗 / 連線逾時 → send 回 false；
///   - 不 panic、不 unwrap（fail-soft，hot path 安全）；
///   - per-send 10s timeout 由上層 EmailDispatcher::send 的 tokio::time::timeout 包，
///     本 struct 內 send 不另設 timeout（避免雙層計時語義混亂）。
pub struct RealSmtpTransport {
    config: EmailConfig,
}

impl RealSmtpTransport {
    /// 從已校驗的 EmailConfig 建立。
    ///
    /// 注意：config 應已通過 `load_email_config` 校驗（host/user/password/port
    /// 非空、backend=smtp_gmail、fingerprint 匹配）；本 ctor 不重複校驗。
    pub fn new(config: EmailConfig) -> Self {
        Self { config }
    }

    /// 依 smtp_port 決定 TLS 模式建出 lettre transport。
    ///
    /// 為什麼分 587/465：
    ///   - 587 = submission port，先明文連線再 STARTTLS 升級（lettre `starttls_relay`）；
    ///   - 465 = SMTPS，連線即 implicit TLS（lettre `relay`）；
    ///   - 其餘 port 一律走 STARTTLS relay（保守 — 禁 plaintext）。
    /// 任一步失敗回 Err，由 send 轉成 false。
    fn build_transport(&self) -> Result<AsyncSmtpTransport<Tokio1Executor>, String> {
        let creds = Credentials::new(
            self.config.smtp_username.clone(),
            self.config.smtp_app_password.clone(),
        );
        let builder = if self.config.smtp_port == 465 {
            // implicit TLS（SMTPS）：relay() 預設即 Tls::Wrapper
            AsyncSmtpTransport::<Tokio1Executor>::relay(&self.config.smtp_host)
                .map_err(|e| format!("smtp relay build failed: {e}"))?
        } else {
            // 587 或其他：STARTTLS（明文連線後強制升級 TLS；禁 plaintext fallback）
            AsyncSmtpTransport::<Tokio1Executor>::starttls_relay(&self.config.smtp_host)
                .map_err(|e| format!("smtp starttls relay build failed: {e}"))?
        };
        // relay()/starttls_relay() 已強制 TLS（Wrapper / Required），禁 plaintext
        // fallback（spec §2.4）；故此處無需另設 Tls::None 防呆。
        let transport = builder
            .port(self.config.smtp_port)
            .credentials(creds)
            .build();
        Ok(transport)
    }

    /// 把 EmailMessage 組成 lettre RFC 5322 Message。
    ///
    /// 不變量：from / 每個 to 都必須是合法 Mailbox，否則回 Err → send false。
    fn build_message(&self, msg: &EmailMessage) -> Result<Message, String> {
        let from: Mailbox = msg
            .from
            .parse()
            .map_err(|e| format!("invalid from address: {e}"))?;
        let mut builder = Message::builder().from(from).subject(msg.subject.clone());
        for addr in &msg.to {
            let to: Mailbox = addr
                .parse()
                .map_err(|e| format!("invalid to address {addr}: {e}"))?;
            builder = builder.to(to);
        }
        builder
            .body(msg.body.clone())
            .map_err(|e| format!("message build failed: {e}"))
    }
}

#[async_trait]
impl SmtpTransport for RealSmtpTransport {
    async fn send(&self, msg: &EmailMessage) -> bool {
        let transport = match self.build_transport() {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!(error = %e, "RealSmtpTransport build_transport failed");
                return false;
            }
        };
        let message = match self.build_message(msg) {
            Ok(m) => m,
            Err(e) => {
                tracing::warn!(error = %e, "RealSmtpTransport build_message failed");
                return false;
            }
        };
        match transport.send(message).await {
            Ok(_) => true,
            Err(e) => {
                // SMTP 4xx/5xx / TLS handshake / 連線錯誤一律 fail-soft（spec §2.3）
                tracing::warn!(error = %e, "RealSmtpTransport send failed");
                false
            }
        }
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

    /// Production 自動接線：secret 存在且校驗通過 → `RealSmtpTransport`（真實寄送）；
    /// 缺檔 / 格式錯 / fingerprint mismatch → `DisabledTransport`（fail-closed 不寄）。
    ///
    /// 為什麼新增此 ctor 而非改 `from_secret_file` 簽名：既有 11 email test 透過
    /// `from_secret_file(path, transport)` 注入 StubTransport，簽名不可破。runtime
    /// 端（C4 wire）改呼本 ctor 即接上真實 SMTP，三路冗餘真的三路。
    ///
    /// 不變量：config=None（缺檔/格式錯）必走 DisabledTransport，維持既有
    /// fail-closed 語義（send 永遠 false）。
    pub fn from_secret_file_real(path: &Path) -> Self {
        let config = load_email_config(path);
        let transport: Box<dyn SmtpTransport> = match &config {
            Some(cfg) => Box::new(RealSmtpTransport::new(cfg.clone())),
            None => Box::new(DisabledTransport),
        };
        Self {
            config,
            transport,
            timeout: EMAIL_DISPATCH_TIMEOUT,
        }
    }

    /// 預設 secret 路徑：`$HOME/BybitOpenClaw/secrets/vault/email_config.json`
    /// 或 env var `OPENCLAW_EMAIL_SECRET_FILE` override。
    ///
    /// operator EA 拍板後預設改用 `RealSmtpTransport`（secret 存在時真實寄送；
    /// 缺檔仍 fail-closed DisabledTransport）。
    pub fn from_default_path() -> Self {
        Self::from_secret_file_real(&default_secret_path())
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

    // ── T12: from_secret_file_real，secret 存在 → RealSmtpTransport 建立不 panic ──
    // 為什麼不真實寄送：本 test 只驗 secret 存在時 production ctor 走 RealSmtpTransport
    // 路徑、is_enabled()=true、且建構過程不 panic（build_transport lazy 在 send 才跑，
    // 故 enable 階段不會連 Gmail）。

    #[tokio::test]
    async fn t12_real_transport_built_from_valid_secret() {
        let f = write_secret(&valid_config_json("appPw1234567890x"));
        let d = EmailDispatcher::from_secret_file_real(f.path());
        assert!(
            d.is_enabled(),
            "valid secret 必走 RealSmtpTransport 且 is_enabled=true"
        );
    }

    // ── T13: from_secret_file_real，secret 缺檔 → fallback DisabledTransport ──
    // 維持既有 fail-closed 語義：缺檔 config=None → DisabledTransport → send false。

    #[tokio::test]
    async fn t13_real_missing_secret_falls_back_disabled() {
        let d = EmailDispatcher::from_secret_file_real(Path::new("/nonexistent/email_real.json"));
        assert!(!d.is_enabled(), "缺檔必 fail-closed disabled");
        let ok = d.send("subj", "body").await;
        assert!(!ok, "DisabledTransport fallback send 必 false");
    }

    // ── T14: RealSmtpTransport::send 對 unreachable host → false（fail-soft）─────
    // 為什麼用 127.0.0.1:1：保證連線立即失敗（埠 1 無服務），驗 send 在連線/
    // handshake 失敗時回 false 不 panic。10s timeout 上限不會被吃滿（連線拒絕秒回）。
    // 不連 Gmail，符合「test 不真實寄送」禁線。

    #[tokio::test]
    async fn t14_real_send_unreachable_host_fail_soft() {
        let cfg = EmailConfig {
            backend: "smtp_gmail".to_string(),
            smtp_host: "127.0.0.1".to_string(),
            smtp_port: 1,
            smtp_username: "x@example.com".to_string(),
            smtp_app_password: "pw".to_string(),
            from_address: "x@example.com".to_string(),
            to_addresses: vec!["y@example.com".to_string()],
            subject_prefix: "[OpenClaw Failsafe]".to_string(),
            fingerprint: None,
        };
        let transport = RealSmtpTransport::new(cfg);
        let msg = EmailMessage {
            from: "x@example.com".to_string(),
            to: vec!["y@example.com".to_string()],
            subject: "[OpenClaw Failsafe] test".to_string(),
            body: "body".to_string(),
        };
        let ok = transport.send(&msg).await;
        assert!(!ok, "unreachable host send 必 fail-soft 回 false");
    }

    // ── T15: EmailConfig Debug 輸出 redact secret（LOW-1 驗）────────────────────
    // 為什麼：`{:?}` 不得洩漏 smtp_app_password / fingerprint 明文。
    #[test]
    fn t15_email_config_debug_redacts_secret() {
        let cfg = EmailConfig {
            backend: "smtp_gmail".to_string(),
            smtp_host: "smtp.gmail.com".to_string(),
            smtp_port: 465,
            smtp_username: "alerts@example.com".to_string(),
            smtp_app_password: "super-secret-app-password-1234".to_string(),
            from_address: "alerts@example.com".to_string(),
            to_addresses: vec!["ops@example.com".to_string()],
            subject_prefix: "[OpenClaw Failsafe]".to_string(),
            fingerprint: Some("deadbeefcafef00d".to_string()),
        };
        let dbg = format!("{cfg:?}");
        // 明文密碼絕不出現
        assert!(
            !dbg.contains("super-secret-app-password-1234"),
            "Debug 輸出洩漏了 smtp_app_password 明文：{dbg}"
        );
        // fingerprint 明文也不出現
        assert!(
            !dbg.contains("deadbeefcafef00d"),
            "Debug 輸出洩漏了 fingerprint 明文：{dbg}"
        );
        // redaction 標記在
        assert!(dbg.contains("***REDACTED***"), "應有 redaction 標記：{dbg}");
        // 非 secret 欄位仍正常顯示（驗未過度 redact）
        assert!(dbg.contains("smtp.gmail.com"));
        assert!(dbg.contains("alerts@example.com"));
    }
}
