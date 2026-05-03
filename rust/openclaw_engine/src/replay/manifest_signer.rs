//! REF-20 P2a-S2 Manifest Signer — server-side HMAC-SHA256 sign + verify.
//! REF-20 P2a-S2 Manifest 簽名器 — server-side HMAC-SHA256 簽名 + 驗證。
//!
//! MODULE_NOTE (EN):
//!   This module is the canonical Rust-side implementation of REF-20 V3 §3 G2
//!   + §5 manifest signature contract. Replay manifests are HMAC-SHA256 signed
//!   server-side; client-supplied signatures are rejected. This module is the
//!   single source of truth for verification on the engine path; the Python
//!   sibling `manifest_signer.py` MUST produce byte-equal HMAC tags for the
//!   same (canonical_bytes, key) pair (cross-language consistency invariant).
//!
//!   Wave 2 P2a-S2 scope (this commit):
//!     - 256-bit (64 hex char) signing key load from
//!       `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`.
//!     - `sign(manifest_canonical) -> hex_signature` synchronous helper.
//!     - `verify(canonical, declared_hash, sig_hex, fingerprint) -> Result<(), SignatureFailMode>`
//!       enforcing V3 §5 verify-order invariant: signature first, manifest
//!       hash second.
//!     - 4 fail-mode enum (`SignatureMismatch`, `ManifestHashMismatch`,
//!       `KeyMissing`, `KeyExpired`) wired to V3 §5 audit-distinguish
//!       requirement.
//!     - `KeyArchive` trait + `InMemoryKeyArchive` shipped for unit testing
//!       without V042 `replay_signing_keys` table dependency (V042 lands
//!       Wave 3; runtime SQL-backed archive is plugged in then).
//!
//!   NOT in this scope (per Wave 2 dispatch §3.4 + V3 §5 invariants):
//!     - DB INSERT into `replay.replay_signing_keys` (V042 reserved, P2a-S4
//!       lands archive writer).
//!     - Cron rotation / retention cleanup (R20-P2a-S1 sub-agent owns).
//!     - 5 min ticker re-verify wiring (Wave 3 R20-P2b-S7/S8 isolated runner).
//!     - IPC / dispatch / live exchange integration (red-line; replay subsystem
//!       MUST NOT couple to Live hot path).
//!     - tokio runtime usage — module is fully synchronous (per Wave 2 dispatch
//!       §2 ambiguity #2: tokio feature subset is `rt-multi-thread + macros`
//!       only; replay signer has no async primitives, so we do not import tokio
//!       at all).
//!
//! MODULE_NOTE (中):
//!   本模組為 REF-20 V3 §3 G2 + §5 manifest 簽名契約的 Rust 端正規實作。
//!   Replay manifest 由 server-side HMAC-SHA256 簽名；client 提供的簽名一律
//!   拒絕。本模組是引擎平面驗簽的唯一真理源；Python sibling
//!   `manifest_signer.py` 必對相同 (canonical_bytes, key) 產出 byte-equal
//!   HMAC tag（跨語言一致性不變量）。
//!
//!   Wave 2 P2a-S2 範圍（本 commit）：
//!     - 從 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` 讀 256-bit
//!       (64 hex char) 簽名 key。
//!     - `sign(manifest_canonical) -> hex_signature` 同步 helper。
//!     - `verify(canonical, declared_hash, sig_hex, fingerprint) -> Result<(), SignatureFailMode>`
//!       強制 V3 §5 驗證順序不變量：先 signature、後 manifest hash。
//!     - 4 fail-mode enum（`SignatureMismatch`、`ManifestHashMismatch`、
//!       `KeyMissing`、`KeyExpired`）對應 V3 §5 audit-distinguish 需求。
//!     - `KeyArchive` trait + `InMemoryKeyArchive` 為 unit test 可行而出貨，
//!       不依賴 V042 `replay_signing_keys` 表（V042 於 Wave 3 P2a-S4 落地）。
//!
//!   不在本範圍：
//!     - DB INSERT `replay.replay_signing_keys`（V042 reserved，P2a-S4 起
//!       archive writer）。
//!     - Cron rotation / retention cleanup（R20-P2a-S1 sub-agent owns）。
//!     - 5 min ticker re-verify wiring（Wave 3 R20-P2b-S7/S8 isolated runner）。
//!     - IPC / dispatch / live exchange 整合（紅線；replay subsystem 嚴禁
//!       耦合 Live hot path）。
//!     - 不用 tokio — 本模組完全同步（per Wave 2 dispatch §2 ambiguity #2：
//!       tokio feature subset 限 `rt-multi-thread + macros`；replay signer
//!       無 async primitive，故完全不 import tokio）。
//!
//! SPEC: REF-20 V3 §3 G2 + §5
//! Runbook: docs/runbooks/replay_signing_key_rotation.md §6
//! Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P2a-S2
//! V3 §12 acceptance #2: signature_verify 4 fail-mode unit test PASS

use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;

// HMAC-SHA256 type alias / HMAC-SHA256 別名。
type HmacSha256 = Hmac<Sha256>;

/// V3 §5: HMAC-SHA256 256-bit key 寫成 64 hex char (32 bytes raw).
/// V3 §5: HMAC-SHA256 256-bit key written as 64 hex chars (32 bytes raw).
const EXPECTED_KEY_HEX_LEN: usize = 64;

/// V3 §5 4 fail-mode 枚舉。每個 variant 對應 audit row 寫入時的
/// `replay_fail_mode` 字串 label，供 `learning.governance_audit_log`
/// dashboard 區分四種失敗根因（signature_mismatch / manifest_hash_mismatch
/// / key_missing / key_expired）。
///
/// V3 §5 four fail-mode enum. Each variant maps to the
/// `replay_fail_mode` string label written into
/// `learning.governance_audit_log` so the dashboard can disambiguate the four
/// failure root-causes.
///
/// Variant ordering note:
/// - The verify path checks key presence first (else `KeyMissing`).
/// - Then key status (else `KeyExpired`).
/// - Then signature byte equality (else `SignatureMismatch`).
/// - Then manifest hash equality (else `ManifestHashMismatch`).
/// This matches V3 §5 verify-order invariant: signature first, hash second
/// (after the key gate has resolved).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignatureFailMode {
    /// Manifest body 與 declared hash 不符（signature 對得上，但 body 簽後被改）。
    /// Manifest body does not match declared hash (signature matches but body was tampered after sign).
    ManifestHashMismatch,
    /// HMAC byte mismatch (tamper or wrong key).
    /// HMAC byte 對不上（tampering 或用錯 key）。
    SignatureMismatch,
    /// fingerprint 不在 archive — 可能 key 從未註冊或已被 GC 過 180d。
    /// Fingerprint not in archive — key never registered or already pruned past 180d.
    KeyMissing,
    /// fingerprint 在 archive 但 status ∈ {expired, compromised}。
    /// Fingerprint in archive but status ∈ {expired, compromised}.
    KeyExpired,
}

impl SignatureFailMode {
    /// Short kv-safe label for structured log fields and audit row writes.
    /// V3 §5 mandates these exact 4 string labels; do NOT rename without a
    /// runbook + audit dashboard update.
    ///
    /// 結構化日誌欄位與 audit row 用的短 kv-safe label。V3 §5 規定這 4 個
    /// 確切字串；非配合 runbook + dashboard 同步更新不可改名。
    pub fn audit_label(self) -> &'static str {
        match self {
            Self::ManifestHashMismatch => "manifest_hash_mismatch",
            Self::SignatureMismatch => "signature_mismatch",
            Self::KeyMissing => "key_missing",
            Self::KeyExpired => "key_expired",
        }
    }
}

impl std::fmt::Display for SignatureFailMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.audit_label())
    }
}

/// Status of a key in the archive. Mirrors the `status` column of V042
/// `replay.replay_signing_keys` (Wave 3 land), kept in sync with runbook §3-§5.
///
/// archive 中 key 的狀態。鏡像 V042 `replay.replay_signing_keys` 的 `status`
/// 欄位（Wave 3 land），與 runbook §3-§5 同步。
///
/// - `Active`: 唯一 active key per env，新 manifest 必用此 key 簽。
/// - `Retired`: 90d rotation 後的舊 key，仍可驗最多 180d 內舊 manifest。
/// - `Expired`: 過 180d retention 的舊 key，verify 一律拒（KeyExpired）。
/// - `Compromised`: emergency rotation 後的洩漏 key，verify 一律拒（KeyExpired）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyStatus {
    Active,
    Retired,
    Expired,
    Compromised,
}

impl KeyStatus {
    /// 此 status 是否仍允許 verify 通過（簽名 + body hash 都對的前提下）。
    /// Whether this status still permits verify-pass (assuming signature + hash both match).
    ///
    /// `Active` / `Retired` → 允許（runbook §4.3 dual key 支援 180d 內舊 manifest）。
    /// `Expired` / `Compromised` → 拒（KeyExpired fail-mode）。
    fn permits_verify(self) -> bool {
        matches!(self, Self::Active | Self::Retired)
    }
}

/// Trait that abstracts the V042 `replay_signing_keys` archive lookup.
///
/// Wave 2 P2a-S2 ships only the in-memory `InMemoryKeyArchive` for unit
/// testing. Wave 3 R20-P2a-S4 will land a SQL-backed implementation that
/// reads from `replay.replay_signing_keys` via the engine `DbPool`.
///
/// V042 `replay_signing_keys` archive 查詢的抽象 trait。
///
/// Wave 2 P2a-S2 僅出貨記憶體版 `InMemoryKeyArchive` 供 unit test。
/// Wave 3 R20-P2a-S4 會落地 SQL 版本，透過 engine `DbPool` 讀
/// `replay.replay_signing_keys`。
pub trait KeyArchive {
    /// 查 fingerprint 對應的 status；不存在回 `None` → caller 視為 `KeyMissing`。
    /// Look up status for fingerprint; absent returns `None` → caller treats as `KeyMissing`.
    fn lookup_status(&self, fingerprint: &str) -> Option<KeyStatus>;
}

/// In-memory `KeyArchive` impl for unit testing without DB dependency.
///
/// 不依賴 DB 的記憶體版 `KeyArchive` 實作，供 unit test 用。
#[derive(Debug, Clone, Default)]
pub struct InMemoryKeyArchive {
    entries: Vec<(String, KeyStatus)>,
}

impl InMemoryKeyArchive {
    /// 新建一個空 archive。
    /// Construct an empty archive.
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
        }
    }

    /// 加入 fingerprint → status 對映。
    /// Insert a fingerprint → status mapping.
    pub fn insert(&mut self, fingerprint: impl Into<String>, status: KeyStatus) {
        self.entries.push((fingerprint.into(), status));
    }
}

impl KeyArchive for InMemoryKeyArchive {
    fn lookup_status(&self, fingerprint: &str) -> Option<KeyStatus> {
        self.entries
            .iter()
            .find(|(fp, _)| fp == fingerprint)
            .map(|(_, status)| *status)
    }
}

/// 簽名器主類。持有 raw 32-byte key + 自身 fingerprint。
/// Manifest signer. Holds raw 32-byte key + own fingerprint.
pub struct ManifestSigner {
    key_bytes: Vec<u8>,
    fingerprint: String,
}

impl ManifestSigner {
    /// 從 disk 讀 key 構造 signer。Path 必為
    /// `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`（V3 §5 hardcode）。
    ///
    /// Construct signer by reading key from disk. Path must be
    /// `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` (V3 §5 hardcode).
    ///
    /// `fingerprint` 是 caller-provided 預期 fingerprint（first 16 hex char of
    /// SHA-256 over **key file contents bytes**，含 trailing `\n`，鏡像 helper
    /// script `generate_replay_signing_key.sh` line 91/93/111 的算法）；caller
    /// 從 V042 archive / 1Password vault 取得，本函式驗證磁碟 key 的
    /// fingerprint == caller 預期值，不一致則 IO error（key path 對但內容對
    /// 不上預期 → cron 失敗 / rotation 漏更新等案例）。
    ///
    /// `fingerprint` is the caller-provided expected fingerprint (first 16 hex
    /// chars of SHA-256 over **key file content bytes**, including trailing
    /// `\n`, mirroring helper script `generate_replay_signing_key.sh` line
    /// 91/93/111 algorithm); caller fetches from V042 archive / 1Password
    /// vault. This function verifies disk-key fingerprint == caller expected;
    /// mismatch → IO error (path correct but content drift, e.g. cron failure
    /// / rotation forgot to update archive).
    ///
    /// 不變量 / Invariant: HMAC key = decoded 32 raw bytes（去除 newline 後
    /// hex decode）；fingerprint = sha256(file content bytes 含 newline)[:16]。
    /// 兩條 derivation 路徑分離以對齊 helper script 的 operator-facing
    /// fingerprint（operator 用 openssl 算後寫入 1Password vault，runtime 必
    /// 與此一致才能查 archive）。
    pub fn new(key_path: PathBuf, fingerprint: String) -> Result<Self, std::io::Error> {
        // 讀 key 檔案內容 / Read key file contents (含 trailing newline).
        let raw = fs::read_to_string(&key_path).map_err(|e| {
            std::io::Error::new(
                e.kind(),
                format!(
                    "replay_signing_key read failed at {}: {} / replay_signing_key 讀取失敗",
                    key_path.display(),
                    e
                ),
            )
        })?;
        // file content bytes（給 fingerprint 用，鏡像 openssl dgst -sha256 -hex < KEY_FILE）。
        // file content bytes (used for fingerprint, mirrors openssl dgst -sha256 -hex < KEY_FILE).
        let file_content_bytes = raw.as_bytes().to_vec();
        let key_hex = raw.trim();

        // 不變量 / Invariant: V3 §5 demands 256-bit key = 64 hex chars.
        if key_hex.len() != EXPECTED_KEY_HEX_LEN {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!(
                    "replay_signing_key length {} != expected {} hex chars (256-bit) / \
                     replay_signing_key 長度錯誤",
                    key_hex.len(),
                    EXPECTED_KEY_HEX_LEN
                ),
            ));
        }

        let key_bytes = hex::decode(key_hex).map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!(
                    "replay_signing_key hex decode failed: {} / replay_signing_key hex 解碼失敗",
                    e
                ),
            )
        })?;

        // 驗 caller 預期 fingerprint == disk key 真實 fingerprint。
        // 注意：fingerprint 算法用 file content bytes（含 newline）以對齊 helper
        // script line 91/93/111；HMAC key 用 decoded raw 32 bytes（去除 newline）。
        // Verify caller-expected fingerprint == disk-key real fingerprint.
        // Note: fingerprint computed over file content bytes (including newline)
        // to align with helper script line 91/93/111; HMAC key uses decoded raw
        // 32 bytes (newline stripped).
        let actual_fp = compute_key_fingerprint(&file_content_bytes);
        if actual_fp != fingerprint {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!(
                    "replay_signing_key fingerprint mismatch: expected {}, got {} / \
                     fingerprint 不符",
                    fingerprint, actual_fp
                ),
            ));
        }

        Ok(Self {
            key_bytes,
            fingerprint,
        })
    }

    /// Test-only constructor — accepts raw key bytes + fingerprint without
    /// disk I/O. Used by cross-lang consistency tests where the fixture key
    /// is loaded from an in-tree fixture file.
    ///
    /// 純測試 constructor — 直接接 raw key bytes + fingerprint，不讀磁碟。
    /// 用於 cross-lang consistency test，fixture key 從 in-tree fixture 讀。
    ///
    /// 注意 / Note：`key_bytes` 必為 decoded raw 32 bytes（HMAC key 用），
    /// 與 `fingerprint`（caller 預先用 file content bytes 算的 sha256[:16]）
    /// 是兩條獨立 derivation；本 constructor 不重算 fingerprint，直接信任
    /// caller — 整合測試在 fixture loader 中以 file content bytes 算
    /// fingerprint 並對齊 `fingerprint.txt`。
    /// `key_bytes` MUST be decoded raw 32 bytes (HMAC key); `fingerprint` is
    /// caller-precomputed sha256[:16] over file content bytes. The two
    /// derivations are independent; this constructor does NOT recompute
    /// fingerprint and trusts the caller — integration tests compute
    /// fingerprint over file content bytes in the fixture loader and assert
    /// against `fingerprint.txt`.
    ///
    /// `#[doc(hidden)]` is used instead of `#[cfg(test)]` because integration
    /// tests in `tests/` link against the lib's regular (non-test) build —
    /// `cfg(test)` would hide this symbol from them. Production callers MUST
    /// NOT use this constructor (use `new()` to load from disk); the
    /// hidden-ness keeps it out of public docs.
    ///
    /// 用 `#[doc(hidden)]` 而非 `#[cfg(test)]`：`tests/` 整合測試 link 的是 lib
    /// 的非測試 build；`cfg(test)` 會把符號藏起整合測試看不到。生產 caller
    /// 嚴禁用此 constructor（請用 `new()` 從磁碟讀），hidden 屬性確保不出現
    /// 在公開文件中。
    #[doc(hidden)]
    pub fn new_from_bytes_for_test(key_bytes: Vec<u8>, fingerprint: String) -> Self {
        Self {
            key_bytes,
            fingerprint,
        }
    }

    /// 此 signer 的 fingerprint。
    /// Fingerprint of this signer.
    pub fn fingerprint(&self) -> &str {
        &self.fingerprint
    }

    /// HMAC-SHA256 sign canonical manifest bytes → hex (lowercase) signature.
    ///
    /// 對 canonical manifest bytes 做 HMAC-SHA256 簽名 → hex（小寫）signature。
    ///
    /// `manifest_canonical` 必為 caller 預先 canonicalize 過的 bytes（typically
    /// `serde_json::to_vec` 對 sorted keys + UTF-8 normalized 的結果）；本
    /// 函式不重做 canonicalization，避免雙端 normalization drift。
    ///
    /// `manifest_canonical` MUST be caller-canonicalized bytes (typically
    /// `serde_json::to_vec` over sorted-keys + UTF-8 normalized). This
    /// function does NOT re-canonicalize; that prevents
    /// canonicalization-drift between Rust and Python sides.
    pub fn sign(&self, manifest_canonical: &[u8]) -> String {
        // SAFETY / 不變量: HMAC-SHA256 accepts arbitrary key length. The
        // 32-byte (256-bit) constraint is verified at `new()`; here we trust
        // the constructor invariant.
        // 不變量：HMAC-SHA256 接受任意長度 key。32-byte 限制在 `new()` 強制；
        // 此處信任 constructor invariant。
        let mut mac = HmacSha256::new_from_slice(&self.key_bytes)
            .expect("HMAC-SHA256 accepts any key size");
        mac.update(manifest_canonical);
        let tag = mac.finalize().into_bytes();
        hex::encode(tag)
    }

    /// V3 §5 verify-order invariant: 先 signature 後 manifest hash。
    ///
    /// V3 §5 verify-order invariant: signature first, manifest hash second.
    ///
    /// Order of checks:
    ///   1. archive lookup → `KeyMissing` if fingerprint absent.
    ///   2. archive status → `KeyExpired` if status ∈ {expired, compromised}.
    ///   3. signature byte-equal → `SignatureMismatch` else.
    ///   4. body hash equal → `ManifestHashMismatch` else.
    ///
    /// 順序：(1) archive lookup → KeyMissing，(2) status → KeyExpired，
    /// (3) signature byte-equal → SignatureMismatch，(4) body hash → ManifestHashMismatch。
    ///
    /// 不變量：steps 3-4 即「先 signature 後 hash」的 V3 §5 順序強制。
    /// Invariant: steps 3-4 enforce the V3 §5 "signature first, hash second" order.
    pub fn verify<A: KeyArchive>(
        &self,
        manifest_canonical: &[u8],
        manifest_declared_hash: &str,
        signature_hex: &str,
        fingerprint: &str,
        archive: &A,
    ) -> Result<(), SignatureFailMode> {
        // Step 1: archive lookup gate / archive 查詢 gate。
        let status = match archive.lookup_status(fingerprint) {
            Some(s) => s,
            None => return Err(SignatureFailMode::KeyMissing),
        };

        // Step 2: archive status gate / archive 狀態 gate。
        if !status.permits_verify() {
            return Err(SignatureFailMode::KeyExpired);
        }

        // Step 3: signature first / 先驗 signature（V3 §5 順序不變量）。
        //
        // 若 verify 用的 fingerprint 對應 key != 本 signer 的 key（即 caller
        // 用錯 signer instance 驗別人簽的 manifest），signature 計算結果一定
        // mismatch → SignatureMismatch（這是設計的 fail-closed 行為，prod
        // 環境 caller 必先按 fingerprint 路由到正確 signer）。
        //
        // If the key behind `fingerprint` differs from this signer's key
        // (caller used the wrong signer instance to verify someone else's
        // manifest), the recomputed signature mismatches → SignatureMismatch
        // (intentional fail-closed; production caller must route by
        // fingerprint to the correct signer).
        let expected_sig = self.sign(manifest_canonical);
        if !constant_time_eq(expected_sig.as_bytes(), signature_hex.as_bytes()) {
            return Err(SignatureFailMode::SignatureMismatch);
        }

        // Step 4: manifest hash second / 後驗 manifest body hash。
        let actual_body_hash = compute_body_hash(manifest_canonical);
        if !constant_time_eq(
            actual_body_hash.as_bytes(),
            manifest_declared_hash.as_bytes(),
        ) {
            return Err(SignatureFailMode::ManifestHashMismatch);
        }

        Ok(())
    }
}

/// Compute first-16-hex-chars SHA-256 fingerprint over **key file content bytes**
/// (including trailing newline written by `printf '%s\n' "$NEW_KEY"`). Mirrors
/// the helper script `generate_replay_signing_key.sh` line 91/93/111 algorithm:
///
///   `openssl dgst -sha256 -hex < $KEY_FILE | awk '{print $NF}' | cut -c1-16`
///
/// The script's `< $KEY_FILE` redirect feeds the entire file content (including
/// the `\n` appended by `printf '%s\n'`) to `openssl dgst -sha256 -hex`. This
/// function MUST sha256 the same byte sequence (file content as-is, no trim,
/// no hex decode) so the operator-facing fingerprint logged in 1Password vault
/// matches the runtime-computed fingerprint used to look up V042
/// `replay_signing_keys` archive.
///
/// 對 **key 檔案內容 bytes**（含 `printf '%s\n'` 寫入的 trailing newline）算
/// first-16-hex-chars SHA-256 fingerprint。鏡像 helper script
/// `generate_replay_signing_key.sh` line 91/93/111 的算法：
///
///   `openssl dgst -sha256 -hex < $KEY_FILE | awk '{print $NF}' | cut -c1-16`
///
/// Script 的 `< $KEY_FILE` 重定向把整個檔案內容（含 `printf '%s\n'` 寫入的
/// `\n`）餵給 `openssl dgst -sha256 -hex`。本函式必對相同 byte sequence 做
/// sha256（檔案內容 as-is，**不 trim、不 hex decode**），以便 operator 寫
/// 1Password vault 的 fingerprint 與 runtime 查 V042 `replay_signing_keys`
/// archive 用的 fingerprint 對得上。
///
/// 不變量 / Invariant：caller MUST 傳檔案 content bytes（typically
/// `fs::read_to_string(path).unwrap().as_bytes().to_vec()` 或測試時手 craft
/// `format!("{key_hex}\n").as_bytes()`）；切勿傳 `hex::decode(...)` 後的 raw
/// 32 bytes — 那會與 script-computed fingerprint 不符 → 100% `KeyMissing`
/// fail-mode（archive lookup miss）。
pub fn compute_key_fingerprint(key_file_content: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(key_file_content);
    let digest = hasher.finalize();
    let full_hex = hex::encode(digest);
    full_hex[..16].to_string()
}

/// Compute SHA-256 hex digest over canonical manifest bytes. Used both for
/// `sign()` step (caller declares this hash in manifest) and `verify()` step
/// (we recompute and compare against declared).
///
/// 計算 canonical manifest bytes 的 SHA-256 hex digest。`sign()` 時 caller
/// 把此 hash 寫進 manifest，`verify()` 時重算並與 declared 比對。
pub fn compute_body_hash(manifest_canonical: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(manifest_canonical);
    hex::encode(hasher.finalize())
}

// ---------------------------------------------------------------------------
// Track B (REF-20 Sprint 1) — canonical-body-for-signing helper.
// ---------------------------------------------------------------------------
//
// MODULE_NOTE (EN): When Track A's `_write_manifest_fixture(...)` writes a
// SINGLE-FILE manifest containing both the body fields AND the signature /
// manifest_hash / signature_key_ref envelope fields, the bytes on disk are
// NOT the bytes that were signed. The signing payload (the byte sequence the
// HMAC tag and SHA-256 body hash were computed over) is the body with the
// envelope fields stripped, re-serialized in a deterministic canonical form.
//
// This helper provides that canonical form. Track B's verify path calls it
// before `signer.verify(...)` so the verify input matches what Python sibling
// signed (instead of the disk-file raw bytes which include the signature
// itself — that would be self-referential and unverifiable).
//
// Algorithm (V3 §6.2 sorted-keys serde_json contract):
//   1. Parse the disk-file bytes as `serde_json::Value` (REJECT non-object).
//   2. Remove keys: `signature`, `manifest_hash`, `signature_key_ref`.
//   3. Re-serialize via `serde_json::to_vec(&value)` — `serde_json` without
//      `preserve_order` (workspace default — checked at Cargo.toml) uses
//      `BTreeMap` internally, producing alphabetically sorted keys + compact
//      separators (`,` and `:` no spaces).
//
// Cross-language byte-equal invariant (Track A Python sibling MUST match):
//   Python: `json.dumps(stripped_dict, sort_keys=True, separators=(',', ':'),
//                       ensure_ascii=False).encode('utf-8')`.
//
//   * `sort_keys=True`              ↔  Rust BTreeMap default sort.
//   * `separators=(',', ':')`       ↔  Rust serde_json compact default.
//   * `ensure_ascii=False`          ↔  Rust serde_json never escapes
//                                       non-ASCII by default.
//
// Cross-platform note: this function is endian-agnostic and produces the same
// byte sequence on Mac dev (aarch64-apple-darwin) and Linux runtime
// (x86_64-unknown-linux-gnu) — verified by `tests/canonical_body_xplat.rs`
// in this commit.
//
// MODULE_NOTE (中): Track A `_write_manifest_fixture(...)` 寫單檔 manifest
// （body 欄位 + signature / manifest_hash / signature_key_ref envelope 欄位
// 同檔）時，磁碟 bytes ≠ 簽名時的 bytes。簽名 payload（HMAC tag 與 body hash
// 算的 byte sequence）是「剝除 envelope 欄位 + 確定性 canonical 重序列化」
// 之後的結果。
//
// 此 helper 提供該 canonical form。Track B verify 路徑在 `signer.verify(...)`
// 之前呼叫，使 verify 輸入與 Python sibling 簽時一致（而非含 signature 本身
// 的磁碟原始 bytes — 那是自我引用、無法驗證的）。
//
// 演算法（V3 §6.2 sorted-keys serde_json 契約）：
//   1. parse 磁碟 bytes 為 `serde_json::Value`（非 object 即拒絕）。
//   2. 移除 keys：`signature`、`manifest_hash`、`signature_key_ref`。
//   3. `serde_json::to_vec(&value)` 重序列化 — `serde_json` 無 `preserve_order`
//      （workspace 預設，checked at Cargo.toml）內部用 `BTreeMap`，產出
//      alphabetical sorted keys + compact separator（`,` 與 `:` 無空白）。
//
// 跨語言 byte-equal 不變量（Track A Python sibling 必對齊）：
//   Python: `json.dumps(stripped_dict, sort_keys=True, separators=(',', ':'),
//                       ensure_ascii=False).encode('utf-8')`。
//
// 跨平台：endian 無關；Mac dev 與 Linux runtime byte-equal。
//
// 不變量 / Invariant: caller MUST 傳磁碟單檔 manifest 原始 bytes；本 helper
// 不接收已預先 strip 過的 body（會 double-strip 但 noop，仍正確）。

/// Envelope keys that MUST NOT participate in the signing payload.
/// 不得納入簽名 payload 的 envelope 欄位。
///
/// `signature`        — the HMAC tag itself (self-referential if signed).
/// `manifest_hash`    — the body hash itself (self-referential if signed).
/// `signature_key_ref` — fingerprint hint (not part of body semantics).
///
/// `signature`        — HMAC tag 本身（簽進去就自我引用）。
/// `manifest_hash`    — body hash 本身（同理）。
/// `signature_key_ref` — fingerprint 提示（非 body 語義）。
pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3] =
    ["signature", "manifest_hash", "signature_key_ref"];

/// Re-canonicalize a single-file manifest (Track A `_write_manifest_fixture`
/// output) into the canonical body bytes that were signed.
///
/// 把單檔 manifest（Track A `_write_manifest_fixture` 輸出）重 canonicalize
/// 成被簽的 canonical body bytes。
///
/// See module-level note above (`Track B (REF-20 Sprint 1) — canonical-body-
/// for-signing helper`) for the full algorithm + cross-language invariant.
///
/// 演算法與跨語言不變量見上方 module-level 注釋。
///
/// # Errors
/// - Returns a `serde_json::Error` if the disk bytes are not valid JSON or
///   not a top-level object (V3 §5 requires manifest to be a JSON object).
///
/// 錯誤：磁碟 bytes 非 JSON 或非 top-level object 時回 `serde_json::Error`
/// （V3 §5 要求 manifest 為 JSON object）。
pub fn canonical_body_for_signing(
    disk_bytes: &[u8],
) -> Result<Vec<u8>, serde_json::Error> {
    // Parse → Value（REJECT 非 object）。
    // Parse → Value (REJECT non-object).
    let mut value: serde_json::Value = serde_json::from_slice(disk_bytes)?;

    // 不變量 / Invariant: V3 §5 manifest MUST be a top-level JSON object.
    // 非 object（array / scalar）= signing payload 沒有「envelope 欄位 strip」
    // 語義 → 拒絕。
    let obj = match value.as_object_mut() {
        Some(o) => o,
        None => {
            // 用 serde_json 自有 error 路徑保持型別一致。
            // Use serde_json's own error path to keep the Result type.
            return Err(serde_json::from_str::<serde_json::Map<String, serde_json::Value>>(
                "\"manifest body must be a JSON object\"",
            )
            .unwrap_err());
        }
    };

    // Strip envelope keys / 剝除 envelope 欄位。
    for k in ENVELOPE_KEYS_FOR_SIGNING.iter() {
        obj.remove(*k);
    }

    // serde_json::to_vec → BTreeMap-default sorted keys + compact separators
    // → byte-equal Python json.dumps(sort_keys=True, separators=(',', ':'),
    //   ensure_ascii=False).encode('utf-8').
    serde_json::to_vec(&value)
}

/// Constant-time byte comparison to defeat timing-oracle attacks on HMAC tag.
/// Mirrors `live_authorization.rs::constant_time_eq` (sibling pattern).
///
/// 常數時間 byte 比對，防 HMAC tag 的 timing oracle 攻擊。
/// 鏡像 `live_authorization.rs::constant_time_eq`（sibling 模式）。
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

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------
//
// 4 fail-mode 各 1 unit test + 1 happy-path test + fingerprint helper test。
// V3 §12 acceptance #2 binding 由本檔 `#[cfg(test)] mod tests` + sibling
// integration test `tests/replay_manifest_signer_xlang_consistency.rs`
// 共同覆蓋。
//
// Four fail-mode unit tests + one happy-path test + fingerprint helper test.
// V3 §12 acceptance #2 binding is jointly satisfied by this `#[cfg(test)]
// mod tests` and sibling integration test
// `tests/replay_manifest_signer_xlang_consistency.rs`.
#[cfg(test)]
mod tests {
    use super::*;

    /// 64 hex-char (32 bytes) fixture key for unit tests.
    /// 64 hex-char (32 bytes) fixture key 供 unit test 用。
    const FIXTURE_KEY_HEX: &str =
        "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

    fn fixture_signer() -> ManifestSigner {
        // HMAC key 用 decoded raw 32 bytes（去除 newline 後 hex decode）。
        // HMAC key uses decoded raw 32 bytes (newline stripped, hex decoded).
        let key_bytes = hex::decode(FIXTURE_KEY_HEX).unwrap();
        // fingerprint 用 file content bytes（hex string + trailing `\n`），鏡像
        // helper script `printf '%s\n'` 寫入磁碟後 `openssl dgst < KEY_FILE` 的算法。
        // fingerprint uses file content bytes (hex string + trailing `\n`), mirroring
        // helper script `printf '%s\n'` then `openssl dgst < KEY_FILE`.
        let file_content = format!("{}\n", FIXTURE_KEY_HEX);
        let fp = compute_key_fingerprint(file_content.as_bytes());
        ManifestSigner::new_from_bytes_for_test(key_bytes, fp)
    }

    fn archive_with(fingerprint: &str, status: KeyStatus) -> InMemoryKeyArchive {
        let mut a = InMemoryKeyArchive::new();
        a.insert(fingerprint, status);
        a
    }

    #[test]
    fn happy_path_verify_passes() {
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_001","manifest_version":1}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);
        let archive = archive_with(signer.fingerprint(), KeyStatus::Active);

        let result = signer.verify(body, &body_hash, &sig, signer.fingerprint(), &archive);
        assert!(result.is_ok(), "happy path must verify, got {:?}", result);
    }

    #[test]
    fn fail_mode_signature_mismatch() {
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_002"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        // Tamper signature 1 byte / 改 signature 第 1 byte。
        let mut tampered = sig.into_bytes();
        tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
        let tampered_sig = String::from_utf8(tampered).unwrap();

        let archive = archive_with(signer.fingerprint(), KeyStatus::Active);
        let err = signer
            .verify(body, &body_hash, &tampered_sig, signer.fingerprint(), &archive)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::SignatureMismatch);
        assert_eq!(err.audit_label(), "signature_mismatch");
    }

    #[test]
    fn fail_mode_manifest_hash_mismatch() {
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_003"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        // Tamper declared hash 1 char / 改 declared hash 第 1 char。
        // 此 case：signature 用 body 算對，但 caller 在 manifest 內聲明的 hash
        // 是錯的（body 簽後被改寫，重算不會等於 declared）。
        let mut tampered_hash = body_hash.into_bytes();
        tampered_hash[0] = if tampered_hash[0] == b'a' { b'b' } else { b'a' };
        let tampered_hash = String::from_utf8(tampered_hash).unwrap();

        let archive = archive_with(signer.fingerprint(), KeyStatus::Active);
        let err = signer
            .verify(body, &tampered_hash, &sig, signer.fingerprint(), &archive)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::ManifestHashMismatch);
        assert_eq!(err.audit_label(), "manifest_hash_mismatch");
    }

    #[test]
    fn fail_mode_key_missing() {
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_004"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        // Empty archive: fingerprint 永不會找到 → KeyMissing。
        // Empty archive: fingerprint never found → KeyMissing.
        let empty_archive = InMemoryKeyArchive::new();
        let err = signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &empty_archive)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::KeyMissing);
        assert_eq!(err.audit_label(), "key_missing");
    }

    #[test]
    fn fail_mode_key_expired() {
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_005"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        // archive 內 fingerprint 存在但 status = Expired → KeyExpired。
        // archive contains fingerprint but status = Expired → KeyExpired.
        let archive = archive_with(signer.fingerprint(), KeyStatus::Expired);
        let err = signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &archive)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::KeyExpired);
        assert_eq!(err.audit_label(), "key_expired");
    }

    #[test]
    fn key_expired_also_fires_for_compromised_status() {
        // V3 §5 + runbook §6 — Compromised 與 Expired 都應走 KeyExpired
        // fail-mode（emergency rotation 後 compromised key 必拒）。
        // V3 §5 + runbook §6 — Compromised and Expired both map to KeyExpired
        // fail-mode (emergency-rotated compromised key MUST reject).
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_006"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        let archive = archive_with(signer.fingerprint(), KeyStatus::Compromised);
        let err = signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &archive)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::KeyExpired);
    }

    #[test]
    fn retired_status_still_verifies() {
        // Runbook §4.3 dual key support: retired key 仍可驗 180d 內舊 manifest。
        // Runbook §4.3 dual key support: retired key still verifies historical
        // manifests within 180d retention.
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_007"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        let archive = archive_with(signer.fingerprint(), KeyStatus::Retired);
        assert!(signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &archive)
            .is_ok());
    }

    #[test]
    fn fingerprint_matches_helper_script() {
        // 與 `generate_replay_signing_key.sh` line 91/93/111 算法一致：
        //   openssl dgst -sha256 -hex < key_file | awk '{print $NF}' | cut -c1-16
        //
        // 本實作對 file content bytes（含 trailing `\n`，即 `printf '%s\n'` 寫入的
        // 內容）做 sha256，與 script `< $KEY_FILE` 餵給 openssl 的 byte sequence
        // 完全相同 → fingerprint 對得上。Operator 用 openssl 算 fingerprint 寫入
        // 1Password vault，runtime 查 V042 archive 必算同一值（這是 R20-P2a-S2
        // surgical fix-up 的核心：確保 runtime 不會 100% `KeyMissing` 失敗）。
        //
        // This implementation sha256s the file content bytes (including trailing
        // `\n` from `printf '%s\n'`), which matches the byte sequence the script
        // pipes to openssl via `< $KEY_FILE`. Operator records fingerprint via
        // openssl into 1Password vault; runtime must compute the same value to
        // look up V042 archive (this is the core of R20-P2a-S2 surgical fix-up:
        // ensure runtime does NOT 100% `KeyMissing` fail).
        let file_content = format!("{}\n", FIXTURE_KEY_HEX);
        let fp = compute_key_fingerprint(file_content.as_bytes());
        assert_eq!(fp.len(), 16);
        assert!(fp.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn verify_order_signature_before_hash() {
        // V3 §5 verify-order invariant: 同時 tamper signature 與 declared hash 時，
        // 應先報 SignatureMismatch（不是 ManifestHashMismatch）。
        // V3 §5 verify-order invariant: when both signature AND declared hash
        // are tampered, the error MUST be SignatureMismatch (not
        // ManifestHashMismatch) because signature is checked first.
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_order"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        let mut tampered_sig = sig.into_bytes();
        tampered_sig[0] = if tampered_sig[0] == b'a' { b'b' } else { b'a' };
        let mut tampered_hash = body_hash.into_bytes();
        tampered_hash[0] = if tampered_hash[0] == b'a' { b'b' } else { b'a' };

        let archive = archive_with(signer.fingerprint(), KeyStatus::Active);
        let err = signer
            .verify(
                body,
                std::str::from_utf8(&tampered_hash).unwrap(),
                std::str::from_utf8(&tampered_sig).unwrap(),
                signer.fingerprint(),
                &archive,
            )
            .unwrap_err();
        assert_eq!(
            err,
            SignatureFailMode::SignatureMismatch,
            "V3 §5 verify-order invariant violated: signature must check first"
        );
    }

    // ---------------------------------------------------------------------
    // Track B (REF-20 Sprint 1) — canonical_body_for_signing tests
    // Track B（REF-20 Sprint 1）— canonical_body_for_signing 測試
    // ---------------------------------------------------------------------

    #[test]
    fn canonical_strips_envelope_and_sorts_keys() {
        // 輸入故意亂序 + 含 envelope 三欄。
        // Input deliberately unordered + contains all three envelope fields.
        let raw = br#"{"signature":"sig_x","experiment_id":"exp_test","data_tier":"S2","manifest_hash":"hash_y","run_id":"run_abc","manifest_version":1,"fixture_uri":"fixtures/","signature_key_ref":"fp_x"}"#;
        let canon = canonical_body_for_signing(raw).expect("must parse");
        // sorted alphabetical + compact + envelope stripped.
        let expected = br#"{"data_tier":"S2","experiment_id":"exp_test","fixture_uri":"fixtures/","manifest_version":1,"run_id":"run_abc"}"#;
        assert_eq!(
            canon, expected,
            "canonical body drift: got {} expected {}",
            std::str::from_utf8(&canon).unwrap(),
            std::str::from_utf8(expected).unwrap()
        );
    }

    #[test]
    fn canonical_is_idempotent_on_already_stripped_body() {
        // 既有 fixture 使用 stripped body（無 envelope 欄位）；canonical_body_for_signing
        // 對它應 noop（除了 sorted-keys 重序列化），且因既有 fixture key 已是
        // alphabetical → byte-equal 不變。
        // Existing fixture uses stripped body (no envelope keys); helper must
        // be a noop (modulo sorted-keys re-serialization). Existing fixture
        // keys are alphabetical → output byte-equal to input.
        let raw = br#"{"experiment_id":"exp_fixture_1","manifest_version":1}"#;
        let canon = canonical_body_for_signing(raw).expect("must parse");
        assert_eq!(canon, raw.to_vec());
    }

    #[test]
    fn canonical_rejects_non_object() {
        // V3 §5 manifest MUST be a JSON object; array / scalar 立即拒絕。
        // V3 §5 manifest MUST be a JSON object; array / scalar reject.
        let raw_array = br#"["not_an_object"]"#;
        assert!(canonical_body_for_signing(raw_array).is_err());

        let raw_scalar = br#"42"#;
        assert!(canonical_body_for_signing(raw_scalar).is_err());

        let raw_invalid = br#"{not valid json"#;
        assert!(canonical_body_for_signing(raw_invalid).is_err());
    }

    #[test]
    fn canonical_idempotent_double_apply() {
        // 連續呼叫兩次 canonical 應 byte-equal（已是 sorted + stripped）。
        // Calling twice should be byte-equal (already sorted + stripped).
        let raw = br#"{"signature":"x","experiment_id":"e","manifest_hash":"h","run_id":"r"}"#;
        let once = canonical_body_for_signing(raw).expect("first pass");
        let twice = canonical_body_for_signing(&once).expect("second pass");
        assert_eq!(once, twice);
    }

    #[test]
    fn envelope_keys_constant_matches_doc() {
        // 不變量 / Invariant: 三 envelope key 確切為 signature / manifest_hash /
        //   signature_key_ref（V3 §5 與 Python sibling _canonical_body 對齊）。
        // Three envelope keys MUST be exactly signature / manifest_hash /
        //   signature_key_ref (V3 §5 + Python sibling alignment).
        assert_eq!(ENVELOPE_KEYS_FOR_SIGNING.len(), 3);
        assert!(ENVELOPE_KEYS_FOR_SIGNING.contains(&"signature"));
        assert!(ENVELOPE_KEYS_FOR_SIGNING.contains(&"manifest_hash"));
        assert!(ENVELOPE_KEYS_FOR_SIGNING.contains(&"signature_key_ref"));
    }

    #[test]
    fn verify_order_archive_gates_before_signature() {
        // archive gate (KeyMissing / KeyExpired) 必在 signature gate 之前 —
        // 即使 signature/hash 都對，archive 沒命中或 expired 仍應拒。
        // archive gates (KeyMissing / KeyExpired) MUST precede signature gate
        // — even with valid signature/hash, an absent or expired key must reject.
        let signer = fixture_signer();
        let body = br#"{"experiment_id":"exp_order2"}"#;
        let body_hash = compute_body_hash(body);
        let sig = signer.sign(body);

        // KeyMissing wins over correct signature.
        let empty = InMemoryKeyArchive::new();
        let err = signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &empty)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::KeyMissing);

        // KeyExpired wins over correct signature.
        let expired = archive_with(signer.fingerprint(), KeyStatus::Expired);
        let err = signer
            .verify(body, &body_hash, &sig, signer.fingerprint(), &expired)
            .unwrap_err();
        assert_eq!(err, SignatureFailMode::KeyExpired);
    }
}
