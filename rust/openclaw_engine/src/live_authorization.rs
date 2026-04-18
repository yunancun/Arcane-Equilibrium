//! LIVE-GATE-BINDING-1 — Python↔Rust signed authorization contract for the
//! Live pipeline. Python's EarnedTrust engine writes a HMAC-SHA256-signed
//! `authorization.json` on every renew/approve; Rust reads + verifies it
//! before spawning the Live pipeline (and re-verifies every 5 min).
//!
//! Without this module, Python's T0/T1/T2/T3 tiers, Operator role auth, and
//! `live_reserved` global mode had **zero** effect on the Rust engine — Rust
//! only checked whether the secret slot contained an api_key/api_secret, so
//! operators had no way to pause / downgrade / expire Live sessions.
//!
//! Design note (2026-04-18 operator): LiveDemo is NOT softer than Mainnet for
//! this gate. The point of LiveDemo is to exercise the real Live code path;
//! degrading its gates means mainnet cut-over has untested gate code.
//!
//! LIVE-GATE-BINDING-1 — Python↔Rust 簽名授權契約。Python EarnedTrust 引擎在
//! 每次 renew/approve 後以 HMAC-SHA256 簽名寫入 `authorization.json`；Rust
//! 在啟動 Live 管線前讀取並驗證（每 5 分鐘重驗）。
//!
//! 本模組存在之前，Python 的 T0-T3 階梯、Operator 角色認證、`live_reserved`
//! 全局模式對 Rust 引擎完全無約束力 — Rust 只檢查 secret slot 是否有
//! api_key/api_secret，operator 無法 pause/降級/到期 Live session。
//!
//! 設計註記（2026-04-18 operator）：LiveDemo 對本 gate 不比 Mainnet 寬鬆。
//! LiveDemo 的目的就是走真實 Live 代碼路徑，若 gate 降級則 mainnet 切換時
//! gate 代碼從未被驗證。

use crate::bybit_rest_client::BybitEnvironment;
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

type HmacSha256 = Hmac<Sha256>;

/// Schema version for `authorization.json`. Bump when the canonical signing
/// payload layout changes.
/// `authorization.json` schema 版本。簽名載荷布局變更時遞增。
pub const SCHEMA_VERSION: u32 = 1;

/// Filename inside `secret_files/bybit/live/`.
pub const AUTHORIZATION_FILENAME: &str = "authorization.json";

/// LiveDemo endpoint label used in `env_allowed`.
pub const ENV_LIVE_DEMO: &str = "live_demo";
/// Mainnet endpoint label used in `env_allowed`.
pub const ENV_MAINNET: &str = "mainnet";

/// Earned-Trust authorization record signed by the Python control API and
/// consumed by the Rust engine. The `sig` field is hex HMAC-SHA256 over the
/// canonical payload defined in [`canonical_payload`].
///
/// Python 控制層簽發、Rust 引擎消費的贏得信任授權記錄。`sig` 為標準載荷
/// （見 [`canonical_payload`]）的 HMAC-SHA256 hex 簽名。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LiveAuthorization {
    /// Schema version. Rust rejects anything != [`SCHEMA_VERSION`].
    pub version: u32,
    /// Human-readable tier id, e.g. `"T0_ENTRY"`. Used for telemetry; Rust
    /// does not interpret the ladder — Python is authoritative on tier logic.
    pub tier: String,
    /// Unix ms when the authorization was issued.
    pub issued_at_ms: u64,
    /// Unix ms after which the authorization is no longer valid.
    pub expires_at_ms: u64,
    /// Operator account id that approved the renewal.
    pub operator_id: String,
    /// Allowed endpoint labels (`"live_demo"` / `"mainnet"`). Canonical form
    /// for signing is this list sorted ASCII-ascending with no duplicates.
    pub env_allowed: Vec<String>,
    /// Hex-lowercase HMAC-SHA256 of [`canonical_payload`] keyed by the shared
    /// `OPENCLAW_IPC_SECRET`.
    pub sig: String,
}

impl LiveAuthorization {
    /// Convert a [`BybitEnvironment`] into the string label that must appear
    /// in `env_allowed` for that endpoint to be authorized.
    ///
    /// Demo/Testnet are development-only exchanges that do not touch the Live
    /// pipeline; they never go through this gate.
    pub fn env_label(env: BybitEnvironment) -> Option<&'static str> {
        match env {
            BybitEnvironment::Mainnet => Some(ENV_MAINNET),
            BybitEnvironment::LiveDemo => Some(ENV_LIVE_DEMO),
            BybitEnvironment::Demo | BybitEnvironment::Testnet => None,
        }
    }
}

/// Error surface for the authorization gate. Every variant produces a
/// distinct `tracing` kv pair so log-grepping and alert rules can
/// disambiguate "operator has not approved yet" from "someone tampered
/// with the file".
///
/// 授權 gate 的錯誤面。各變體對應不同的 `tracing` kv 對，讓日誌檢索與
/// 告警規則能區分「operator 尚未批准」與「檔案被竄改」。
#[derive(Debug)]
pub enum AuthError {
    /// `OPENCLAW_IPC_SECRET` env var is unset. HMAC cannot be computed.
    /// Fatal — no signature can be trusted. Operator action: set env var.
    IpcSecretMissing,
    /// `authorization.json` does not exist under the live secret slot.
    /// Expected during first-time setup or post-revoke — operator must
    /// approve via `/api/v1/live/auth/renew`.
    FileMissing { path: PathBuf },
    /// File read I/O error (permission, disk, etc).
    FileReadError { path: PathBuf, reason: String },
    /// JSON deserialization error — likely malformed or hand-edited.
    JsonParseError { path: PathBuf, reason: String },
    /// Schema version mismatch. Newer authorization written by an incompatible
    /// Python build, or a legacy file from before the schema bump.
    UnsupportedVersion { got: u32, expected: u32 },
    /// HMAC signature does not match the canonical payload. Either tampered,
    /// or signed with a different `OPENCLAW_IPC_SECRET`.
    BadSignature,
    /// `expires_at_ms < now_ms`. Operator must renew via Python GUI.
    Expired { expires_at_ms: u64, now_ms: u64 },
    /// Current endpoint label is not in `env_allowed`. Example: mainnet not
    /// yet approved but `bybit_endpoint` flipped to `mainnet`.
    EnvNotAllowed { env: String, allowed: Vec<String> },
    /// Attempted to gate an environment that is not eligible for Live pipeline
    /// (Demo/Testnet). Programming error — should never happen at runtime.
    UnsupportedEnv { env: String },
}

impl std::fmt::Display for AuthError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::IpcSecretMissing => write!(
                f,
                "OPENCLAW_IPC_SECRET env var is not set — cannot verify signed \
                 live authorization / 無 OPENCLAW_IPC_SECRET 環境變量，無法驗證 \
                 簽名 live 授權"
            ),
            Self::FileMissing { path } => write!(
                f,
                "live authorization file missing at {} — operator must approve \
                 via POST /api/v1/live/auth/renew / live 授權檔案不存在，\
                 operator 須經 /auth/renew 批准",
                path.display()
            ),
            Self::FileReadError { path, reason } => write!(
                f,
                "live authorization read error at {}: {} / 授權檔案讀取錯誤",
                path.display(),
                reason
            ),
            Self::JsonParseError { path, reason } => write!(
                f,
                "live authorization JSON parse error at {}: {} / 授權檔案 \
                 JSON 解析錯誤",
                path.display(),
                reason
            ),
            Self::UnsupportedVersion { got, expected } => write!(
                f,
                "live authorization schema version mismatch (got {got}, \
                 expected {expected}) / 授權 schema 版本不匹配"
            ),
            Self::BadSignature => write!(
                f,
                "live authorization HMAC signature invalid — file tampered or \
                 signed with wrong OPENCLAW_IPC_SECRET / 授權 HMAC 簽名無效"
            ),
            Self::Expired {
                expires_at_ms,
                now_ms,
            } => write!(
                f,
                "live authorization expired at {} (now {}) — operator must \
                 renew / 授權已於 {} 過期（當前 {}），operator 須續期",
                expires_at_ms, now_ms, expires_at_ms, now_ms
            ),
            Self::EnvNotAllowed { env, allowed } => write!(
                f,
                "live authorization does not permit env {env} (allowed: {:?}) \
                 / 授權不允許當前 endpoint",
                allowed
            ),
            Self::UnsupportedEnv { env } => write!(
                f,
                "env {env} is not eligible for Live pipeline (Demo/Testnet \
                 should never reach this gate) / 當前 env 不適用 Live gate"
            ),
        }
    }
}

impl std::error::Error for AuthError {}

/// Short kv-safe label used in structured log fields. Allows ops to build
/// alert rules on specific failure modes (e.g. alert only on `bad_signature`
/// and `expired`, not on `file_missing` which is expected during approval
/// flow).
pub fn auth_error_kind(err: &AuthError) -> &'static str {
    match err {
        AuthError::IpcSecretMissing => "ipc_secret_missing",
        AuthError::FileMissing { .. } => "file_missing",
        AuthError::FileReadError { .. } => "file_read_error",
        AuthError::JsonParseError { .. } => "json_parse_error",
        AuthError::UnsupportedVersion { .. } => "unsupported_version",
        AuthError::BadSignature => "bad_signature",
        AuthError::Expired { .. } => "expired",
        AuthError::EnvNotAllowed { .. } => "env_not_allowed",
        AuthError::UnsupportedEnv { .. } => "unsupported_env",
    }
}

/// Resolve the on-disk path to `authorization.json`. Uses the same precedence
/// rule as [`bybit_rest_client::read_secret_file`]:
///   1. `OPENCLAW_SECRETS_DIR/live/authorization.json`
///   2. `$HOME/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json`
///
/// Cross-platform: falls back to `USERPROFILE` on Windows.
pub fn authorization_path() -> Option<PathBuf> {
    let base = if let Ok(dir) = std::env::var("OPENCLAW_SECRETS_DIR") {
        PathBuf::from(dir)
    } else {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .ok()?;
        PathBuf::from(home)
            .join("BybitOpenClaw")
            .join("secrets")
            .join("secret_files")
            .join("bybit")
    };
    Some(base.join("live").join(AUTHORIZATION_FILENAME))
}

/// Build the canonical payload that is HMAC-signed. Python and Rust MUST
/// agree on this format byte-for-byte.
///
/// Format (pipe-separated): `version|tier|issued_at_ms|expires_at_ms|operator_id|env_allowed_sorted_csv`
///
/// `env_allowed_sorted_csv` is ASCII-ascending sorted + comma-joined, with
/// duplicates removed. This lets Python write the list in any order and both
/// sides still arrive at the same signed bytes.
pub fn canonical_payload(auth: &LiveAuthorization) -> String {
    let mut envs: Vec<&str> = auth.env_allowed.iter().map(|s| s.as_str()).collect();
    envs.sort();
    envs.dedup();
    format!(
        "{}|{}|{}|{}|{}|{}",
        auth.version,
        auth.tier,
        auth.issued_at_ms,
        auth.expires_at_ms,
        auth.operator_id,
        envs.join(","),
    )
}

/// Compute the expected hex-lowercase HMAC-SHA256 of the canonical payload.
pub fn compute_signature(auth: &LiveAuthorization, ipc_secret: &str) -> String {
    let payload = canonical_payload(auth);
    let mut mac = HmacSha256::new_from_slice(ipc_secret.as_bytes())
        .expect("HMAC-SHA256 accepts any key size");
    mac.update(payload.as_bytes());
    let tag = mac.finalize().into_bytes();
    hex::encode(tag)
}

/// Constant-time signature comparison. Prevents timing-oracle attacks on the
/// HMAC tag even though the attack surface is local (requires filesystem write
/// access to `authorization.json`, at which point the attacker controls the
/// whole file anyway — but using constant-time compare costs nothing and keeps
/// the audit story clean).
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

/// Verify a [`LiveAuthorization`] record without reading from disk. Pure
/// function — useful for testing and for re-verifying a cached copy.
pub fn verify_in_memory(
    auth: &LiveAuthorization,
    env: BybitEnvironment,
    now_ms: u64,
    ipc_secret: &str,
) -> Result<(), AuthError> {
    if auth.version != SCHEMA_VERSION {
        return Err(AuthError::UnsupportedVersion {
            got: auth.version,
            expected: SCHEMA_VERSION,
        });
    }

    let expected_sig = compute_signature(auth, ipc_secret);
    if !constant_time_eq(expected_sig.as_bytes(), auth.sig.as_bytes()) {
        return Err(AuthError::BadSignature);
    }

    if auth.expires_at_ms <= now_ms {
        return Err(AuthError::Expired {
            expires_at_ms: auth.expires_at_ms,
            now_ms,
        });
    }

    let env_label = match LiveAuthorization::env_label(env) {
        Some(l) => l,
        None => {
            return Err(AuthError::UnsupportedEnv {
                env: format!("{env:?}"),
            })
        }
    };
    if !auth.env_allowed.iter().any(|s| s == env_label) {
        return Err(AuthError::EnvNotAllowed {
            env: env_label.to_string(),
            allowed: auth.env_allowed.clone(),
        });
    }

    Ok(())
}

/// Full disk-read + verify path used by Live pipeline startup and the periodic
/// ticker. Returns the parsed [`LiveAuthorization`] on success so callers can
/// log `tier` / `expires_at_ms` / `operator_id` for audit trail.
pub fn load_and_verify(env: BybitEnvironment) -> Result<LiveAuthorization, AuthError> {
    let ipc_secret =
        std::env::var("OPENCLAW_IPC_SECRET").map_err(|_| AuthError::IpcSecretMissing)?;
    let path = authorization_path().ok_or(AuthError::FileMissing {
        path: PathBuf::from("<unresolved-HOME>"),
    })?;
    if !path.exists() {
        return Err(AuthError::FileMissing { path });
    }
    let raw = std::fs::read_to_string(&path).map_err(|e| AuthError::FileReadError {
        path: path.clone(),
        reason: e.to_string(),
    })?;
    let auth: LiveAuthorization =
        serde_json::from_str(&raw).map_err(|e| AuthError::JsonParseError {
            path: path.clone(),
            reason: e.to_string(),
        })?;
    let now_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    verify_in_memory(&auth, env, now_ms, &ipc_secret)?;
    Ok(auth)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_SECRET: &str = "test-ipc-secret-do-not-use-in-prod";

    fn fresh_auth(now_ms: u64) -> LiveAuthorization {
        let mut auth = LiveAuthorization {
            version: SCHEMA_VERSION,
            tier: "T0_ENTRY".into(),
            issued_at_ms: now_ms,
            expires_at_ms: now_ms + 24 * 3600 * 1000,
            operator_id: "ncyu".into(),
            env_allowed: vec!["live_demo".into()],
            sig: String::new(),
        };
        auth.sig = compute_signature(&auth, TEST_SECRET);
        auth
    }

    #[test]
    fn canonical_payload_sorts_and_dedups_envs() {
        let auth = LiveAuthorization {
            version: 1,
            tier: "T1_PROVISIONAL".into(),
            issued_at_ms: 1_700_000_000_000,
            expires_at_ms: 1_700_000_000_000 + 3600_000,
            operator_id: "op".into(),
            // Intentionally unsorted + duplicated
            env_allowed: vec!["mainnet".into(), "live_demo".into(), "live_demo".into()],
            sig: "".into(),
        };
        let payload = canonical_payload(&auth);
        assert!(payload.ends_with("|live_demo,mainnet"), "got {}", payload);
        assert!(
            !payload.contains("live_demo,live_demo"),
            "duplicates not deduped: {}",
            payload
        );
    }

    #[test]
    fn valid_live_demo_authorization_verifies() {
        let now = 1_700_000_000_000;
        let auth = fresh_auth(now);
        assert!(verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, TEST_SECRET).is_ok());
    }

    #[test]
    fn mainnet_rejected_when_only_live_demo_approved() {
        let now = 1_700_000_000_000;
        let auth = fresh_auth(now); // env_allowed = ["live_demo"]
        let err = verify_in_memory(&auth, BybitEnvironment::Mainnet, now, TEST_SECRET).unwrap_err();
        assert!(
            matches!(err, AuthError::EnvNotAllowed { .. }),
            "expected EnvNotAllowed, got {:?}",
            err
        );
    }

    #[test]
    fn mainnet_accepted_when_mainnet_approved() {
        let now = 1_700_000_000_000;
        let mut auth = LiveAuthorization {
            version: SCHEMA_VERSION,
            tier: "T2_ESTABLISHED".into(),
            issued_at_ms: now,
            expires_at_ms: now + 168 * 3600 * 1000,
            operator_id: "ncyu".into(),
            env_allowed: vec!["mainnet".into(), "live_demo".into()],
            sig: String::new(),
        };
        auth.sig = compute_signature(&auth, TEST_SECRET);
        assert!(verify_in_memory(&auth, BybitEnvironment::Mainnet, now, TEST_SECRET).is_ok());
        assert!(verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, TEST_SECRET).is_ok());
    }

    #[test]
    fn expired_authorization_rejected() {
        let issued = 1_700_000_000_000;
        let auth = fresh_auth(issued);
        let now_after_expiry = auth.expires_at_ms + 1;
        let err = verify_in_memory(
            &auth,
            BybitEnvironment::LiveDemo,
            now_after_expiry,
            TEST_SECRET,
        )
        .unwrap_err();
        assert!(
            matches!(err, AuthError::Expired { .. }),
            "expected Expired, got {:?}",
            err
        );
    }

    #[test]
    fn expiry_at_now_is_rejected_not_accepted() {
        // Boundary: `expires_at_ms == now_ms` must reject (strict <=).
        let now = 1_700_000_000_000;
        let auth = fresh_auth(now);
        let expiry = auth.expires_at_ms;
        let err =
            verify_in_memory(&auth, BybitEnvironment::LiveDemo, expiry, TEST_SECRET).unwrap_err();
        assert!(matches!(err, AuthError::Expired { .. }));
    }

    #[test]
    fn tampered_tier_detected_by_signature_check() {
        let now = 1_700_000_000_000;
        let mut auth = fresh_auth(now);
        auth.tier = "T3_TRUSTED".into(); // escalate without re-signing
        let err =
            verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, TEST_SECRET).unwrap_err();
        assert!(matches!(err, AuthError::BadSignature));
    }

    #[test]
    fn tampered_env_allowed_detected() {
        let now = 1_700_000_000_000;
        let mut auth = fresh_auth(now);
        auth.env_allowed.push("mainnet".into()); // escalate
        let err = verify_in_memory(&auth, BybitEnvironment::Mainnet, now, TEST_SECRET).unwrap_err();
        assert!(matches!(err, AuthError::BadSignature));
    }

    #[test]
    fn tampered_expiry_detected() {
        let now = 1_700_000_000_000;
        let mut auth = fresh_auth(now);
        auth.expires_at_ms += 365 * 24 * 3600 * 1000; // extend a year
        let err =
            verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, TEST_SECRET).unwrap_err();
        assert!(matches!(err, AuthError::BadSignature));
    }

    #[test]
    fn wrong_secret_produces_bad_signature() {
        let now = 1_700_000_000_000;
        let auth = fresh_auth(now);
        let err = verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, "different-secret")
            .unwrap_err();
        assert!(matches!(err, AuthError::BadSignature));
    }

    #[test]
    fn unsupported_version_rejected_before_signature() {
        let now = 1_700_000_000_000;
        let mut auth = fresh_auth(now);
        auth.version = 99;
        let err =
            verify_in_memory(&auth, BybitEnvironment::LiveDemo, now, TEST_SECRET).unwrap_err();
        assert!(matches!(
            err,
            AuthError::UnsupportedVersion {
                got: 99,
                expected: 1
            }
        ));
    }

    #[test]
    fn demo_and_testnet_are_unsupported_envs() {
        let now = 1_700_000_000_000;
        let auth = fresh_auth(now);
        for env in [BybitEnvironment::Demo, BybitEnvironment::Testnet] {
            let err = verify_in_memory(&auth, env, now, TEST_SECRET).unwrap_err();
            assert!(
                matches!(err, AuthError::UnsupportedEnv { .. }),
                "expected UnsupportedEnv for {:?}, got {:?}",
                env,
                err
            );
        }
    }

    #[test]
    fn env_allowed_order_does_not_break_signature() {
        // Python may serialize env_allowed in any order; canonical_payload
        // sorts before hashing so the signature stays stable.
        let now = 1_700_000_000_000;
        let mut a = LiveAuthorization {
            version: 1,
            tier: "T2_ESTABLISHED".into(),
            issued_at_ms: now,
            expires_at_ms: now + 3600_000,
            operator_id: "op".into(),
            env_allowed: vec!["live_demo".into(), "mainnet".into()],
            sig: String::new(),
        };
        a.sig = compute_signature(&a, TEST_SECRET);

        let b = LiveAuthorization {
            env_allowed: vec!["mainnet".into(), "live_demo".into()],
            ..a.clone()
        };
        // Same signature verifies both orderings.
        assert!(verify_in_memory(&b, BybitEnvironment::LiveDemo, now, TEST_SECRET).is_ok());
    }

    #[test]
    fn load_and_verify_reads_file_via_env_override() {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
        let auth = fresh_auth(now);
        let serialized = serde_json::to_string_pretty(&auth).unwrap();

        let tmp = tempfile::tempdir().expect("tempdir");
        let live_dir = tmp.path().join("live");
        std::fs::create_dir_all(&live_dir).unwrap();
        std::fs::write(live_dir.join(AUTHORIZATION_FILENAME), &serialized).unwrap();

        // Snapshot & override env vars.
        let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
        let prev_ipc = std::env::var("OPENCLAW_IPC_SECRET").ok();
        std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());
        std::env::set_var("OPENCLAW_IPC_SECRET", TEST_SECRET);

        let result = load_and_verify(BybitEnvironment::LiveDemo);

        // Restore env before asserting (so a failing assert doesn't pollute
        // other tests in the same process).
        match prev_secrets {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
        }
        match prev_ipc {
            Some(v) => std::env::set_var("OPENCLAW_IPC_SECRET", v),
            None => std::env::remove_var("OPENCLAW_IPC_SECRET"),
        }

        let loaded = result.expect("should verify");
        assert_eq!(loaded.tier, "T0_ENTRY");
        assert_eq!(loaded.operator_id, "ncyu");
    }

    #[test]
    fn auth_error_kind_labels_are_stable() {
        // Alert rules depend on these strings — any rename is a breaking change.
        assert_eq!(
            auth_error_kind(&AuthError::IpcSecretMissing),
            "ipc_secret_missing"
        );
        assert_eq!(auth_error_kind(&AuthError::BadSignature), "bad_signature");
        assert_eq!(
            auth_error_kind(&AuthError::Expired {
                expires_at_ms: 0,
                now_ms: 1
            }),
            "expired"
        );
        assert_eq!(
            auth_error_kind(&AuthError::EnvNotAllowed {
                env: "mainnet".into(),
                allowed: vec![]
            }),
            "env_not_allowed"
        );
    }
}
