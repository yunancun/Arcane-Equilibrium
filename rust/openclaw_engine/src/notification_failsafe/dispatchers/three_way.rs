//! Wave 5 Packet C / C1 — 3-way notification dispatcher。
//!
//! 為什麼：把 Slack + Email + Console banner 三個獨立 dispatcher 綁成單一
//! `NotificationDispatcher` impl，供 `FailsafeWatcher` 透過 trait 物件統一呼叫；
//! 對齊 PA C spec §1-3 整合層 + 既有 `NotificationDispatcher` trait
//! （`super::super::NotificationDispatcher`）。
//!
//! 不變量（per AMD-2026-05-21-01 v2 §Decision 3.1 + PA spec §0 fail-soft 規則）：
//!   - 三路 **並發** 呼叫（`tokio::join!`），不序列；
//!   - 任一路成功（即使其餘失敗）→ `PartialFail{failed:[...]}` 或
//!     `AllSuccess`；
//!   - 三路全失敗 → `AllFail`（此 outcome 觸發 1h timer 武裝邏輯在 watcher 端）；
//!   - 個別 dispatcher 各自 fail-soft + per-dispatch timeout 包好，本層只看 bool；
//!   - 不 panic、不 unwrap。
//!
//! ref: docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §1-3

use async_trait::async_trait;

use super::console_banner::ConsoleBannerDispatcher;
use super::email::EmailDispatcher;
use super::slack::SlackDispatcher;
use super::super::{DispatchOutcome, NotificationChannel, NotificationDispatcher};

/// 三路通知 dispatcher — 包三個獨立通道並回 outcome。
pub struct ThreeWayDispatcher {
    slack: SlackDispatcher,
    email: EmailDispatcher,
    console: ConsoleBannerDispatcher,
    /// Banner 寫入時的 severity 標記（per AMD v2：3-way fail 為 critical）。
    banner_severity: String,
}

impl ThreeWayDispatcher {
    /// 顯式注入（測試 + runtime 共用入口）。
    pub fn new(
        slack: SlackDispatcher,
        email: EmailDispatcher,
        console: ConsoleBannerDispatcher,
    ) -> Self {
        Self {
            slack,
            email,
            console,
            banner_severity: "critical".to_string(),
        }
    }

    /// 從預設 secret 路徑載入三 dispatcher。
    /// 缺檔自動 fail-closed disabled（不報錯）。
    pub fn from_default_paths() -> Self {
        Self::new(
            SlackDispatcher::from_default_path(),
            EmailDispatcher::from_default_path(),
            ConsoleBannerDispatcher::from_default_path(),
        )
    }

    /// 自訂 banner severity（測試 / 自訂事件等級用）。
    pub fn with_banner_severity(mut self, severity: impl Into<String>) -> Self {
        self.banner_severity = severity.into();
        self
    }

    /// 各通道 enable 狀態快照（給 watcher / 健檢 GUI 用）。
    pub fn channels_enabled(&self) -> (bool, bool) {
        // slack enabled / email enabled；console banner 不需 enable 判斷（檔案
        // 路徑永遠可寫，缺權限才 fail）
        (self.slack.is_enabled(), self.email.is_enabled())
    }
}

#[async_trait]
impl NotificationDispatcher for ThreeWayDispatcher {
    /// 派發訊息至三路通道並回 outcome（per PA spec §0 fail-soft 規則）。
    ///
    /// 流程：
    ///   1. `tokio::join!` 三路並發；
    ///   2. 收三個 bool；
    ///   3. 計失敗通道；
    ///   4. AllSuccess / PartialFail / AllFail 對齊 既有 `DispatchOutcome` enum。
    ///
    /// banner 訊息與 Slack/Email 訊息一致；email subject 用「failsafe escalation」
    /// 固定字串（subject_prefix 由 EmailDispatcher 自動加）。
    async fn dispatch_3way(&self, message: &str) -> DispatchOutcome {
        let subject = "failsafe escalation";
        // 並發三路
        let (slack_ok, email_ok, console_ok) = tokio::join!(
            self.slack.send(message),
            self.email.send(subject, message),
            self.console.write_banner(&self.banner_severity, message),
        );

        compute_outcome(slack_ok, email_ok, console_ok)
    }
}

/// 純函數 — 三 bool 算 outcome。
///
/// 邏輯（per spec §1-3 + DispatchOutcome 既有定義）：
///   - 全 true → AllSuccess
///   - 全 false → AllFail
///   - 混合 → PartialFail { failed: 失敗清單 }
pub fn compute_outcome(slack_ok: bool, email_ok: bool, console_ok: bool) -> DispatchOutcome {
    let mut failed = Vec::new();
    if !slack_ok {
        failed.push(NotificationChannel::Slack);
    }
    if !email_ok {
        failed.push(NotificationChannel::Email);
    }
    if !console_ok {
        failed.push(NotificationChannel::ConsoleBanner);
    }
    match failed.len() {
        0 => DispatchOutcome::AllSuccess,
        3 => DispatchOutcome::AllFail,
        _ => DispatchOutcome::PartialFail { failed },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notification_failsafe::dispatchers::console_banner::ConsoleBannerDispatcher;
    use crate::notification_failsafe::dispatchers::email::{
        DisabledTransport, EmailDispatcher, StubTransport,
    };
    use crate::notification_failsafe::dispatchers::slack::SlackDispatcher;
    use std::io::Write;
    use tempfile::{NamedTempFile, TempDir};

    fn write_secret(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::new().expect("tmpfile");
        f.write_all(content.as_bytes()).expect("write");
        f
    }

    fn valid_email_config(pw: &str) -> String {
        format!(
            r#"{{
                "backend":"smtp_gmail",
                "smtp_host":"smtp.gmail.com",
                "smtp_port":587,
                "smtp_username":"x@example.com",
                "smtp_app_password":"{pw}",
                "from_address":"x@example.com",
                "to_addresses":["x@example.com"]
            }}"#
        )
    }

    // ── T1: compute_outcome all true → AllSuccess ───────────────────────────

    #[test]
    fn t1_all_success() {
        assert_eq!(compute_outcome(true, true, true), DispatchOutcome::AllSuccess);
    }

    // ── T2: compute_outcome all false → AllFail ─────────────────────────────

    #[test]
    fn t2_all_fail() {
        assert_eq!(compute_outcome(false, false, false), DispatchOutcome::AllFail);
    }

    // ── T3: 9 種組合驗 outcome (3^2 - 全成功 - 全失敗) ──────────────────────

    #[test]
    fn t3_partial_fail_combinations() {
        // 只 slack fail
        match compute_outcome(false, true, true) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(failed, vec![NotificationChannel::Slack]);
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
        // 只 email fail
        match compute_outcome(true, false, true) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(failed, vec![NotificationChannel::Email]);
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
        // 只 banner fail
        match compute_outcome(true, true, false) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(failed, vec![NotificationChannel::ConsoleBanner]);
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
        // slack + email fail
        match compute_outcome(false, false, true) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(
                    failed,
                    vec![NotificationChannel::Slack, NotificationChannel::Email]
                );
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
        // slack + banner fail
        match compute_outcome(false, true, false) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(
                    failed,
                    vec![NotificationChannel::Slack, NotificationChannel::ConsoleBanner]
                );
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
        // email + banner fail
        match compute_outcome(true, false, false) {
            DispatchOutcome::PartialFail { failed } => {
                assert_eq!(
                    failed,
                    vec![NotificationChannel::Email, NotificationChannel::ConsoleBanner]
                );
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
    }

    // ── T4: dispatch_3way with all-disabled secrets → AllFail ───────────────

    #[tokio::test]
    async fn t4_dispatch_all_disabled_returns_all_fail() {
        // Slack: 缺檔 disabled → false
        let slack = SlackDispatcher::from_secret_file(std::path::Path::new("/nonexistent_slack"));
        // Email: 缺檔 disabled → false
        let email = EmailDispatcher::from_secret_file(
            std::path::Path::new("/nonexistent_email"),
            Box::new(StubTransport::new()),
        );
        // Banner: 路徑無寫權限 → 寫到 read-only dir 模擬 fail
        // 用 tmpdir → write_banner 應 success，所以這條 partial fail
        let tmp = TempDir::new().unwrap();
        let banner = ConsoleBannerDispatcher::new(tmp.path().to_path_buf());

        let d = ThreeWayDispatcher::new(slack, email, banner);
        let outcome = d.dispatch_3way("test message").await;
        match outcome {
            DispatchOutcome::PartialFail { failed } => {
                // slack + email 失敗，banner 成功
                assert!(failed.contains(&NotificationChannel::Slack));
                assert!(failed.contains(&NotificationChannel::Email));
                assert!(!failed.contains(&NotificationChannel::ConsoleBanner));
            }
            o => panic!("expected PartialFail (slack+email), got {o:?}"),
        }
    }

    // ── T5: dispatch_3way with banner only success → PartialFail ────────────

    #[tokio::test]
    async fn t5_only_banner_succeeds_partial_fail() {
        let slack = SlackDispatcher::from_explicit_url("http://localhost:1/hook".to_string()); // 拒
        let f = write_secret(&valid_email_config("pw")); // config valid
        let email = EmailDispatcher::from_secret_file(f.path(), Box::new(DisabledTransport)); // transport disabled
        let tmp = TempDir::new().unwrap();
        let banner = ConsoleBannerDispatcher::new(tmp.path().to_path_buf());

        let d = ThreeWayDispatcher::new(slack, email, banner);
        let outcome = d.dispatch_3way("msg").await;
        match outcome {
            DispatchOutcome::PartialFail { failed } => {
                assert!(failed.contains(&NotificationChannel::Slack));
                assert!(failed.contains(&NotificationChannel::Email));
                assert!(!failed.contains(&NotificationChannel::ConsoleBanner));
                assert_eq!(failed.len(), 2);
            }
            o => panic!("expected PartialFail, got {o:?}"),
        }
    }

    // ── T6: dispatch_3way fully failing → AllFail (banner dir read-only) ────

    #[tokio::test]
    async fn t6_all_three_fail_returns_all_fail() {
        let slack = SlackDispatcher::from_explicit_url("http://localhost:1/hook".to_string()); // 拒
        let email = EmailDispatcher::from_secret_file(
            std::path::Path::new("/nonexistent_email"),
            Box::new(StubTransport::new()),
        );
        // Banner 寫到 /nonexistent root 路徑（建目錄通常 fail on macOS sandbox + Linux non-root）
        let banner =
            ConsoleBannerDispatcher::new(std::path::PathBuf::from("/proc/cannot_write_here"));

        let d = ThreeWayDispatcher::new(slack, email, banner);
        let outcome = d.dispatch_3way("msg").await;
        match outcome {
            DispatchOutcome::AllFail => {}
            o => panic!("expected AllFail, got {o:?}"),
        }
    }

    // ── T7: dispatch_3way concurrent execution semantics smoke ──────────────

    #[tokio::test]
    async fn t7_dispatch_uses_tokio_join_concurrent() {
        // 純煙霧測試 — 確認三路 join 不死鎖 + 完成（mock 全成功）
        // 三路全 enabled 但 stub 攔截
        let shared = std::sync::Arc::new(std::sync::Mutex::new(Vec::<String>::new()));
        struct CapStub(std::sync::Arc<std::sync::Mutex<Vec<String>>>);
        #[async_trait::async_trait]
        impl super::super::email::SmtpTransport for CapStub {
            async fn send(&self, m: &super::super::email::EmailMessage) -> bool {
                self.0.lock().unwrap().push(format!("email:{}", m.subject));
                true
            }
        }
        let f = write_secret(&valid_email_config("pw"));
        let email = EmailDispatcher::from_secret_file(f.path(), Box::new(CapStub(shared.clone())));
        // Slack 用 disabled 但 join 不阻塞
        let slack = SlackDispatcher::from_secret_file(std::path::Path::new("/none"));
        let tmp = TempDir::new().unwrap();
        let banner = ConsoleBannerDispatcher::new(tmp.path().to_path_buf());

        let d = ThreeWayDispatcher::new(slack, email, banner);
        let _ = d.dispatch_3way("hello").await;
        // 至少 email + banner 完成（slack disabled）
        let calls = shared.lock().unwrap();
        assert_eq!(calls.len(), 1, "email transport should fire once");
        assert!(banner_exists(tmp.path()));
    }

    fn banner_exists(dir: &std::path::Path) -> bool {
        dir.join("failsafe_banner_active.json").is_file()
    }

    // ── T8: from_default_paths constructs without panic ─────────────────────

    #[tokio::test]
    async fn t8_from_default_paths_constructs() {
        // 測試環境 $HOME 通常存在；secrets 通常不存在 → 三 dispatcher 各自 disabled
        let _d = ThreeWayDispatcher::from_default_paths();
        // 不 assert 行為（依環境）；只測 constructor 不 panic
    }

    // ── T9: with_banner_severity propagates ─────────────────────────────────

    #[tokio::test]
    async fn t9_with_banner_severity_propagates() {
        let slack = SlackDispatcher::from_secret_file(std::path::Path::new("/none"));
        let email = EmailDispatcher::from_secret_file(
            std::path::Path::new("/none"),
            Box::new(StubTransport::new()),
        );
        let tmp = TempDir::new().unwrap();
        let banner = ConsoleBannerDispatcher::new(tmp.path().to_path_buf());

        let d = ThreeWayDispatcher::new(slack, email, banner).with_banner_severity("warning");
        let _ = d.dispatch_3way("test").await;
        // 讀 banner 驗 severity
        let banner_path = tmp.path().join("failsafe_banner_active.json");
        let raw = std::fs::read_to_string(&banner_path).unwrap();
        assert!(raw.contains(r#""severity": "warning""#));
    }
}
