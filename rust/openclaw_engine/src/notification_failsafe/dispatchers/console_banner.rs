//! Wave 5 Packet C / C1 — Console banner dispatcher。
//!
//! 為什麼：三路通知第三路；operator Q3.1 拍板「直到 ack 不 auto-clear」；
//! C1 階段採 vault-file 路徑（per PM 派發 prompt 指示）；
//! GUI 顯示 + PG 同步路徑屬 C5（Sprint 3）責任。
//!
//! Banner 路徑：`~/BybitOpenClaw/secrets/vault/failsafe_banner_active.json`
//! Schema 寫入：
//!   {
//!     "severity": "critical",
//!     "message": "<human-readable description>",
//!     "written_at_utc": "2026-05-28T12:34:56Z",
//!     "ack_required": true,
//!     "acked_at_utc": null,
//!     "acked_by": null
//!   }
//!
//! ## 與 PA spec §3.1 路徑 (b) 的差異
//!
//! PA spec §3.1 推薦「engine 寫 PG row → control_api 讀 PG」為 banner 路徑。
//! 本 C1 階段（per operator PC.B 拍板）採 vault-file 中介：
//!   - 寫檔（本檔）= C1 IMPL；
//!   - PG audit row（V114 schema）= C2 IMPL（audit_emitter.rs，獨立 wave）；
//!   - GUI 端讀 = C5 IMPL（可直接讀檔或讀 PG，待 Sprint 3 拍板）。
//!
//! 兩條路徑不互斥：本檔 + audit_emitter 並行寫入，GUI 之後依 spec 拍板選讀源。
//!
//! 不變量（per CLAUDE.md §二 + PA spec §3 + AMD-2026-05-21-01 v2 §3.1）：
//!   - 目錄不存在 → 自動建立（0700）；
//!   - 檔案不存在 → 建立 atomically（write tmp + rename）；
//!   - 檔案已存在 → overwrite（per Q3.1 持久化邏輯 = 由 caller 決定是否覆蓋）；
//!   - clear_banner ≠ 刪檔；UPDATE 加 acked_at_utc + acked_by 兩欄保留 audit；
//!   - 寫入失敗 fail-soft，回 false，不 panic；
//!   - 跨平台無硬編碼 `/home/ncyu`（per `feedback_cross_platform`）。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §3
//!   - PM 派發 prompt（2026-05-28 E1-PC1 Phase 3）

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// Banner 持久化 schema。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BannerPayload {
    pub severity: String,
    pub message: String,
    pub written_at_utc: String,
    pub ack_required: bool,
    #[serde(default)]
    pub acked_at_utc: Option<String>,
    #[serde(default)]
    pub acked_by: Option<String>,
}

/// Console banner 派發器 — 寫入 vault 檔案，等 GUI 讀取顯示。
///
/// `banner_dir` 預設 `~/BybitOpenClaw/secrets/vault/`；env var
/// `OPENCLAW_FAILSAFE_BANNER_DIR` override。
pub struct ConsoleBannerDispatcher {
    banner_dir: PathBuf,
}

/// Banner 檔名（固定）。
pub const BANNER_FILENAME: &str = "failsafe_banner_active.json";

impl ConsoleBannerDispatcher {
    /// 顯式指定 banner dir。
    pub fn new(banner_dir: PathBuf) -> Self {
        Self { banner_dir }
    }

    /// 預設路徑：`$OPENCLAW_FAILSAFE_BANNER_DIR` 或
    /// `$HOME/BybitOpenClaw/secrets/vault/`。
    pub fn from_default_path() -> Self {
        let dir = if let Ok(explicit) = std::env::var("OPENCLAW_FAILSAFE_BANNER_DIR") {
            PathBuf::from(explicit)
        } else {
            let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
            PathBuf::from(home)
                .join("BybitOpenClaw")
                .join("secrets")
                .join("vault")
        };
        Self::new(dir)
    }

    /// 取得 banner 檔絕對路徑（測試用 / GUI 路徑同步用）。
    pub fn banner_path(&self) -> PathBuf {
        self.banner_dir.join(BANNER_FILENAME)
    }

    /// 寫入 active banner — overwrite 既有檔（per Q3.1 不 auto-clear，由
    /// `clear_banner` 顯式 ack）。
    ///
    /// 不變量：
    ///   - 目錄不存在 → create_dir_all（mode 0700 在 unix；Windows ignore）；
    ///   - tmp file + atomic rename（避免讀端讀到半寫檔）；
    ///   - severity 自動 lower-case 化（容錯）；
    ///   - 失敗 fail-soft 回 false。
    pub async fn write_banner(&self, severity: &str, message: &str) -> bool {
        let now_utc = now_iso8601_utc();
        let payload = BannerPayload {
            severity: severity.trim().to_lowercase(),
            message: message.to_string(),
            written_at_utc: now_utc,
            ack_required: true,
            acked_at_utc: None,
            acked_by: None,
        };
        self.write_payload(&payload).await
    }

    /// Operator GUI ack — 讀現有 banner（若不存在 → false），補 acked_at_utc /
    /// acked_by，atomic rewrite。
    ///
    /// 為什麼不刪檔：保留 audit trail；GUI 端用 `ack_required=true ∧ acked_at_utc=null`
    /// 來判斷是否顯示 banner。
    pub async fn clear_banner(&self, ack_by: &str) -> bool {
        let path = self.banner_path();
        let raw = match tokio::fs::read_to_string(&path).await {
            Ok(s) => s,
            Err(_) => return false,
        };
        let mut payload: BannerPayload = match serde_json::from_str(&raw) {
            Ok(p) => p,
            Err(_) => return false,
        };
        if payload.acked_at_utc.is_some() {
            // 已 ack；重複呼叫 idempotent return true（GUI 重 click 不算錯）
            return true;
        }
        payload.acked_at_utc = Some(now_iso8601_utc());
        payload.acked_by = Some(ack_by.to_string());
        self.write_payload(&payload).await
    }

    /// 讀取現有 banner（測試 + GUI 共用）。
    pub async fn read_banner(&self) -> Option<BannerPayload> {
        let raw = tokio::fs::read_to_string(self.banner_path()).await.ok()?;
        serde_json::from_str(&raw).ok()
    }

    /// 內部：序列化 payload + atomic write。
    async fn write_payload(&self, payload: &BannerPayload) -> bool {
        if tokio::fs::create_dir_all(&self.banner_dir).await.is_err() {
            return false;
        }
        // Unix: 目錄權限 0700（best effort；忽略錯誤）
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(meta) = std::fs::metadata(&self.banner_dir) {
                let mut perms = meta.permissions();
                perms.set_mode(0o700);
                let _ = std::fs::set_permissions(&self.banner_dir, perms);
            }
        }
        let serialized = match serde_json::to_string_pretty(payload) {
            Ok(s) => s,
            Err(_) => return false,
        };
        let final_path = self.banner_path();
        let tmp_path = self.banner_dir.join(format!(
            "{}.tmp.{}",
            BANNER_FILENAME,
            std::process::id()
        ));
        if tokio::fs::write(&tmp_path, serialized.as_bytes())
            .await
            .is_err()
        {
            return false;
        }
        // Unix: 檔案權限 0600（best effort）
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(meta) = std::fs::metadata(&tmp_path) {
                let mut perms = meta.permissions();
                perms.set_mode(0o600);
                let _ = std::fs::set_permissions(&tmp_path, perms);
            }
        }
        tokio::fs::rename(&tmp_path, &final_path).await.is_ok()
    }
}

/// 產生 ISO-8601 UTC 時間字串（無秒以下精度）。
fn now_iso8601_utc() -> String {
    use chrono::SecondsFormat;
    chrono::Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn dispatcher(tmp: &TempDir) -> ConsoleBannerDispatcher {
        ConsoleBannerDispatcher::new(tmp.path().to_path_buf())
    }

    // ── T1: write_banner creates file + correct schema ──────────────────────

    #[tokio::test]
    async fn t1_write_banner_creates_file() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        let ok = d.write_banner("CRITICAL", "三路通知失敗 1h 超時").await;
        assert!(ok);
        let payload = d.read_banner().await.expect("banner should exist");
        assert_eq!(payload.severity, "critical");
        assert_eq!(payload.message, "三路通知失敗 1h 超時");
        assert!(payload.ack_required);
        assert!(payload.acked_at_utc.is_none());
        assert!(payload.acked_by.is_none());
        assert!(payload.written_at_utc.ends_with('Z'));
    }

    // ── T2: write_banner overwrites existing ────────────────────────────────

    #[tokio::test]
    async fn t2_write_banner_overwrites() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        assert!(d.write_banner("info", "first").await);
        assert!(d.write_banner("critical", "second").await);
        let payload = d.read_banner().await.unwrap();
        assert_eq!(payload.severity, "critical");
        assert_eq!(payload.message, "second");
    }

    // ── T3: clear_banner adds acked fields ──────────────────────────────────

    #[tokio::test]
    async fn t3_clear_banner_adds_ack_fields() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        assert!(d.write_banner("critical", "msg").await);
        let ok = d.clear_banner("operator_cloud").await;
        assert!(ok);
        let payload = d.read_banner().await.unwrap();
        assert_eq!(payload.acked_by.as_deref(), Some("operator_cloud"));
        assert!(payload.acked_at_utc.is_some());
        // 既有欄位保留
        assert_eq!(payload.severity, "critical");
        assert_eq!(payload.message, "msg");
        assert!(payload.ack_required);
    }

    // ── T4: clear_banner without banner file → false ────────────────────────

    #[tokio::test]
    async fn t4_clear_without_banner_returns_false() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        let ok = d.clear_banner("operator").await;
        assert!(!ok);
    }

    // ── T5: clear_banner idempotent (re-ack returns true, no field overwrite) ─

    #[tokio::test]
    async fn t5_clear_banner_idempotent() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        assert!(d.write_banner("critical", "msg").await);
        assert!(d.clear_banner("op1").await);
        let first = d.read_banner().await.unwrap();
        // 第二次 ack 應 no-op return true，不改 acked_by
        assert!(d.clear_banner("op2").await);
        let second = d.read_banner().await.unwrap();
        assert_eq!(first.acked_by, second.acked_by, "idempotent ack must preserve original acker");
    }

    // ── T6: banner_path round-trip ──────────────────────────────────────────

    #[tokio::test]
    async fn t6_banner_path() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        assert_eq!(d.banner_path(), tmp.path().join("failsafe_banner_active.json"));
    }

    // ── T7: write_banner creates parent dir when missing ────────────────────

    #[tokio::test]
    async fn t7_write_creates_parent_dir() {
        let tmp = TempDir::new().unwrap();
        let nested = tmp.path().join("nested").join("dir");
        // 不預先 create_dir_all；write_banner 自己應建
        let d = ConsoleBannerDispatcher::new(nested.clone());
        assert!(d.write_banner("info", "test").await);
        assert!(nested.is_dir());
        assert!(nested.join("failsafe_banner_active.json").is_file());
    }

    // ── T8: malformed JSON in banner file → clear returns false ─────────────

    #[tokio::test]
    async fn t8_malformed_banner_clear_false() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("failsafe_banner_active.json");
        tokio::fs::write(&path, b"{ broken").await.unwrap();
        let d = dispatcher(&tmp);
        assert!(!d.clear_banner("op").await);
    }

    // ── T9: read_banner None when file missing ──────────────────────────────

    #[tokio::test]
    async fn t9_read_banner_missing_none() {
        let tmp = TempDir::new().unwrap();
        let d = dispatcher(&tmp);
        assert!(d.read_banner().await.is_none());
    }

    // ── T10: now_iso8601_utc shape ──────────────────────────────────────────

    #[test]
    fn t10_iso8601_format() {
        let s = now_iso8601_utc();
        assert!(s.ends_with('Z'));
        // 形如 2026-05-28T12:34:56Z（20 字符）
        assert_eq!(s.len(), 20);
    }
}
