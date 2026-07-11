//! MODULE_NOTE
//! 模塊用途：IBKR Phase 2 external-surface gate **producer**（ADR-0048 /
//!   AMD-2026-07-08-01）。程式化組裝一條可過 `IbkrPhase2GateArtifactV1::validate()`
//!   的候選 artifact，通過雙綠（`validate()` + hash 自洽 re-verify）+ approval
//!   A-model + finding-1 triangulation 後，以 write-once（`create_new`/`hard_link`，
//!   絕不 rename）封存到治理目錄。**單一真源**：precontact 顯示面經本模塊的磁碟
//!   sealed 態 re-verify 反映 `immutable_pass_artifact_present`，不二次組裝 gate。
//! 主要函數：
//!   - `load_phase2_policy_bundle_from_dir`（真載 `ibkr_phase2_policies.toml`）
//!   - `load_phase2_seal_approval_from_dir`（approval A-model 讀取器，owner-only）
//!   - `build_external_surface_gate` / `build_phase2_artifact_candidate`（純組裝）
//!   - `verify_artifact_hashes`（pre-seal hash 自洽）/ `verify_sealed_artifact`
//!     （post-seal 磁碟 re-verify，含 path 綁定）
//!   - `seal_phase2_artifact`（write-once seal，雙綠 + triangulation 才寫）
//!   - `phase2_producer_outcome` / `phase2_gate_producer_summary`（report 面）
//!   - `phase2_immutable_pass_artifact_present`（precontact 唯一 production 消費點）
//! 依賴：`openclaw_types`（消費 `ibkr_phase2_*` 型別；T1 `IBKR-P2-SEAL-LINEAGE-FIELDS`
//!   受權為 artifact 型別加 `contact_authorization_amd`+`approval_lineage_hash` 兩欄）、
//!   `ibkr_secret_slot_loader`（P1 秘密槽 leg：OnceLock + denied fallback）、
//!   `boot_observability::BUILD_GIT_SHA`（source_commit）、`sha2`/`hex`/`toml`/
//!   `serde_json`/`libc::geteuid`。
//! 硬邊界（絕不鬆動）：
//!   - 只讀、零真錢、不接 IPC/socket、不建槽、不接 IBKR（`ibkr_call_performed` 硬
//!     編 false）、不翻 flag、Bybit 不變、無 DB migration、不動 Python 守衛 / 型別
//!     net-free 守衛。
//!   - **無 fake-success**：絕不封存假 PASS——僅 `validate().ibkr_contact_allowed`
//!     且 `verify_artifact_hashes` 且 triangulation 三綠才寫；任一不成立回
//!     Blocked/Err，不寫檔。
//!   - **refuse-ephemeral（finding-3）**：`OPENCLAW_DATA_DIR` 未設 / canonicalize
//!     落 `/tmp/*` 等易失路徑 → 拒 seal（`EphemeralDataDir`），**絕不**沿
//!     `halt_audit` 的 `/tmp/openclaw` fallback（治理證據不可寫易失盤）。
//!   - **approval A-model（6 綁定，缺一即 fail-closed 不注入 Operator）**：見
//!     `approval_is_valid` + `load_phase2_seal_approval_from_dir`。approval 引的是
//!     contact-授權 AMD `AMD-2026-07-08-01`，與 artifact shape-AMD
//!     `AMD-2026-06-29-01` 是兩軸（finding-2）。
//!   - **write-once**：`create_new` 唯一 tmp → `sync_all` → `hard_link(tmp,final)`
//!     （final 已存在 = 拒二次 seal，絕不 rename overwrite）→ 0o400 → fsync 父目錄。
//!
//! TODO(later phase)：現階段唯一 production 消費者是 precontact 的
//!   `phase2_immutable_pass_artifact_present`（現狀恒 false）；`seal`/`outcome`/
//!   `summary`/`build`/approval-reader 皆為後續 phase 接入前的 scaffold（僅測試觸
//!   達），故用檔案級 `#![allow(dead_code)]`（沿 crate 既有慣例：見 P1
//!   `ibkr_secret_slot_loader`）。真 seal 啟用 = operator 決策（現狀必然 BLOCKED）。

#![allow(dead_code)]

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use openclaw_types::{
    IbkrApiSessionTopologyV1, IbkrExternalSurfaceGateStatus, IbkrExternalSurfaceGateV1,
    IbkrPhase2GateArtifactV1, IbkrPhase2GatePrerequisiteFlags, IbkrPhase2PolicyBundleV1,
    IbkrSecretSlotContractV1, NonBybitApiAllowlistV1, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PHASE2_ADR, IBKR_PHASE2_AMD, IBKR_PHASE2_CONTACT_AMD,
};

use crate::boot_observability::BUILD_GIT_SHA;

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

/// 穩定 artifact_id（=contract_id 字串）：二次 seal 撞 `create_new`/`hard_link`。
const PHASE2_ARTIFACT_ID: &str = "phase2_ibkr_external_surface_gate_v1";

/// sealed artifact 磁碟檔名（write-once，0o400）。
const SEALED_FILENAME: &str = "phase2_ibkr_external_surface_gate_v1.sealed.json";

/// approval A-model 來源檔名（owner-only 0o600 TOML）。
const APPROVAL_FILENAME: &str = "phase2_seal_approval.toml";

/// 政策 bundle 來源檔名（settings/broker）。
const POLICIES_FILENAME: &str = "ibkr_phase2_policies.toml";

/// approval issue→now 上界（bounded freshness，30 天）；超齡即視為過期（fail-closed）。
const MAX_APPROVAL_AGE_MS: u64 = 30 * 24 * 60 * 60 * 1000;

/// producer-層 blocker reason（非 types `validate()` 覆蓋的三項）。
const REASON_EPHEMERAL: &str = "ephemeral_data_dir";
const REASON_TRIANGULATION: &str = "account_fingerprint_triangulation_mismatch";
const REASON_SOURCE_COMMIT_UNKNOWN: &str = "source_commit_unknown";

/// 易失路徑前綴（refuse-ephemeral）。跨平台涵蓋 Linux `/tmp`、Mac `/private/tmp`
/// 與 `/var/folders`（tempfile），以及 `/dev/shm`。
const EPHEMERAL_PREFIXES: &[&str] = &[
    "/tmp",
    "/private/tmp",
    "/var/tmp",
    "/private/var/tmp",
    "/var/folders",
    "/private/var/folders",
    "/dev/shm",
];

// ---------------------------------------------------------------------------
// approval A-model
// ---------------------------------------------------------------------------

/// Phase 2 seal approval（TOML deser）。producer 絕不自注 "Operator"——僅在本結構
/// 通過 `approval_is_valid` 的 6 綁定後，才把其 `reviewer_roles` 綁進 artifact。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Phase2SealApproval {
    pub adr: String,
    pub amd: String,
    pub reviewer_roles: Vec<String>,
    pub approved_source_commit: String,
    pub issued_at_ms: u64,
    pub expires_at_ms: u64,
}

/// approval 6 綁定（缺一即 false → 不注入 Operator → fail-closed）：
/// 1) adr==ADR-0048；2) amd==contact-AMD 07-08-01（非 shape-AMD）；
/// 3) approved_source_commit==BUILD_GIT_SHA 且非 "unknown"（anti-replay）；
/// 4) reviewer_roles 含 PM 且 Operator；
/// 5) 時窗有效：issued>0、issued<=now、expires>now、expires>issued；
/// 6) bounded freshness：now-issued<=30d；clock 異常（future-dated）判無效不 fail-open。
fn approval_is_valid(a: &Phase2SealApproval, now_ms: u64, build_sha: &str) -> bool {
    a.adr == IBKR_PHASE2_ADR
        && a.amd == IBKR_PHASE2_CONTACT_AMD
        && source_commit_is_known(build_sha)
        && a.approved_source_commit == build_sha
        && a.reviewer_roles.iter().any(|r| r == "PM")
        && a.reviewer_roles.iter().any(|r| r == "Operator")
        && a.issued_at_ms > 0
        && a.issued_at_ms <= now_ms
        && a.expires_at_ms > now_ms
        && a.expires_at_ms > a.issued_at_ms
        && now_ms.saturating_sub(a.issued_at_ms) <= MAX_APPROVAL_AGE_MS
}

/// source_commit 必須是真世代——拒空 / 拒 build.rs 的 "unknown" fallback。
fn source_commit_is_known(sha: &str) -> bool {
    !sha.trim().is_empty() && sha != "unknown"
}

// ---------------------------------------------------------------------------
// 錯誤 / 產出型別
// ---------------------------------------------------------------------------

/// seal 失敗原因。`AlreadySealed`=write-once 命中既有檔（正確拒二次 seal）；
/// `NotValid`=雙綠/triangulation 任一不成立；`EphemeralDataDir`=refuse-ephemeral；
/// `IoError`=I/O（訊息只帶 path + io::Error，零明文）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Phase2SealError {
    AlreadySealed,
    IoError(String),
    NotValid,
    EphemeralDataDir,
}

/// 各 leg 接受度（report 面；零明文，皆 bool）。
#[derive(Debug, Clone, Serialize)]
pub struct Phase2LegStatus {
    pub data_dir_ephemeral: bool,
    pub source_commit_known: bool,
    pub policy_bundle_accepted: bool,
    pub api_allowlist_accepted: bool,
    pub secret_contract_accepted: bool,
    pub api_topology_accepted: bool,
    pub external_surface_gate_accepted: bool,
    pub approval_present: bool,
    pub approval_valid: bool,
    pub account_fingerprint_triangulation_ok: bool,
    pub artifact_contact_allowed: bool,
    pub artifact_hashes_verified: bool,
}

/// producer 一次評估的結果。現階段 env-wrapper 恒回 `Blocked`（report-only，不寫檔）；
/// `Sealed`/`AlreadySealed` 為 seal 啟用後的形狀（現由測試觸達 seal 直接映射）。
pub enum Phase2ProducerOutcome {
    Sealed {
        path: PathBuf,
    },
    AlreadySealed {
        path: PathBuf,
    },
    Blocked {
        blockers: Vec<String>,
        leg_status: Phase2LegStatus,
    },
}

// ---------------------------------------------------------------------------
// hash（raw 自洽覆蓋所有實質欄位；redacted 只含 hash/bool/enum/contract_id）
// ---------------------------------------------------------------------------

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

/// raw_artifact_hash = sha256(canonical JSON；清兩 hash 欄位 + sealed 正規化為 true)。
///
/// 為什麼清兩 hash 欄位：hash 不能覆蓋自身（否則不可自洽）。為什麼 sealed 正規化：
/// sealed 是構造細節，恒為封存意圖 true，正規化保證重算穩定。
/// finding-2（T1 `IBKR-P2-SEAL-LINEAGE-FIELDS` 已閉合）：artifact 型別新增
/// `contact_authorization_amd`（自記 contact AMD）+ `approval_lineage_hash`（授權此
/// seal 的 approval canonical 之 sha256），兩欄隨整 struct serde 序列化**自動納入**本
/// raw hash 覆蓋域（此函數 0 改）→ 竄改任一即 hash 不符（tamper-evident lineage）；
/// 且 raw hash 只依賴 artifact 自身，令 `seal` 與磁碟 re-verify 皆自洽、無需重讀 approval。
fn compute_raw_artifact_hash(artifact: &IbkrPhase2GateArtifactV1) -> String {
    let mut norm = artifact.clone();
    norm.raw_artifact_hash = String::new();
    norm.redacted_summary_hash = String::new();
    norm.sealed = true;
    let json = serde_json::to_string(&norm).unwrap_or_default();
    sha256_hex(json.as_bytes())
}

/// redacted summary：只含 hash / bool / enum / contract_id——**禁 account_id 明文、
/// 禁本機路徑**（`immutable_storage_path` 刻意不入 → 治理報告零路徑洩漏）。
fn redacted_summary_value(a: &IbkrPhase2GateArtifactV1) -> serde_json::Value {
    serde_json::json!({
        "contract_id": a.contract_id,
        "artifact_id": a.artifact_id,
        "source_version": a.source_version,
        "adr": a.adr,
        "amd": a.amd,
        "source_commit": a.source_commit,
        "created_at_ms": a.created_at_ms,
        "sealed": a.sealed,
        "reviewer_roles": a.reviewer_roles,
        "gate_status": a.gate.status,
        "gate_ibkr_call_performed": a.gate.ibkr_call_performed,
        "gate_live_ports_denied": a.gate.live_ports_denied,
        "gate_secret_contract_present": a.gate.secret_contract_present,
        "gate_live_secret_absent_or_empty": a.gate.live_secret_absent_or_empty,
        "gate_api_allowlist_present": a.gate.api_allowlist_present,
        "policy_flags": a.policy_flags,
        "secret_slot_fingerprint": a.secret_slot_contract.secret_slot_fingerprint,
        "account_fingerprint_hash": a.secret_slot_contract.account_fingerprint_hash,
        "topology_account_fingerprint_hash": a.api_session_topology.account_fingerprint_hash,
        // T1：兩者皆非明文（AMD 字串 + 64-hex approval lineage）；令 redacted 摘要也覆蓋
        // lineage → 竄改 lineage 亦破 redacted hash。
        "contact_authorization_amd": a.contact_authorization_amd,
        "approval_lineage_hash": a.approval_lineage_hash,
    })
}

fn compute_redacted_summary_hash(a: &IbkrPhase2GateArtifactV1) -> String {
    let json = serde_json::to_string(&redacted_summary_value(a)).unwrap_or_default();
    sha256_hex(json.as_bytes())
}

/// approval_lineage_hash = sha256(approval canonical JSON)（T1）。
///
/// **決定性關鍵**（E2 審點）：用 `serde_json::json!` 顯式固定 key 序 + `roles.sort()`，
/// 絕不用裸 `to_string(&approval)`（struct 欄位序 / roles 元素序不保證穩定 → hash
/// 漂移，令 tamper-evidence 失效）。此 hash 於 seal-time 填入 artifact，令 sealed 檔
/// tamper-evidently 自記是哪份 approval 授權了它。
fn compute_approval_lineage_hash(a: &Phase2SealApproval) -> String {
    let mut roles = a.reviewer_roles.clone();
    roles.sort();
    let canonical = serde_json::json!({
        "adr": a.adr,
        "amd": a.amd,
        "reviewer_roles": roles,
        "approved_source_commit": a.approved_source_commit,
        "issued_at_ms": a.issued_at_ms,
        "expires_at_ms": a.expires_at_ms,
    });
    sha256_hex(
        serde_json::to_string(&canonical)
            .unwrap_or_default()
            .as_bytes(),
    )
}

/// pre-seal 自洽閘：重算兩 hash 與 artifact 內存欄位比對（因 types `validate()` 只驗
/// shape，不重算內容）。竄改任一 hash 為合法 64-hex 錯值即 false。
fn verify_artifact_hashes(a: &IbkrPhase2GateArtifactV1) -> bool {
    compute_raw_artifact_hash(a) == a.raw_artifact_hash
        && compute_redacted_summary_hash(a) == a.redacted_summary_hash
}

// ---------------------------------------------------------------------------
// 純組裝（gate + artifact 候選）
// ---------------------------------------------------------------------------

/// 程式化組裝 external-surface gate（單一真源）。5 policy flag 取 `policy_flags`；
/// `live_ports_denied=true`；`ibkr_call_performed` 硬編 false；host/port/baseline
/// 走 `Default`（LoopbackOnly / PaperGatewayPortOnly / IbGatewayTwsApi）。
fn build_external_surface_gate(
    policy_flags: IbkrPhase2GatePrerequisiteFlags,
    api_allowlist_present: bool,
    secret_contract_present: bool,
    live_secret_absent_or_empty: bool,
) -> IbkrExternalSurfaceGateV1 {
    IbkrExternalSurfaceGateV1 {
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
        status: IbkrExternalSurfaceGateStatus::Pass,
        live_ports_denied: true,
        secret_contract_present,
        live_secret_absent_or_empty,
        api_allowlist_present,
        redaction_suite_passed: policy_flags.redaction_suite_passed,
        rate_limit_policy_present: policy_flags.rate_limit_policy_present,
        audit_event_policy_present: policy_flags.audit_event_policy_present,
        paper_attestation_contract_present: policy_flags.paper_attestation_contract_present,
        python_no_write_guard_present: policy_flags.python_no_write_guard_present,
        ibkr_call_performed: false,
        // adr/amd/api_baseline/host_policy/port_policy 走型別 Default（皆安全方向）。
        ..IbkrExternalSurfaceGateV1::default()
    }
}

/// 組裝 artifact 候選（`sealed=true` 是構造意圖，非「已封存」保證——實際落檔仍須過
/// seal 的雙綠 + write-once）。
///
/// - `reviewer_roles` / `contact_authorization_amd` / `approval_lineage_hash`：approval
///   有效 → 綁定其 roles（含 PM+Operator）+ 常量 contact AMD + approval lineage hash；
///   否則三者皆空（absent/無效 → validate `OperatorReviewerMissing` /
///   `ContactAuthorizationAmdMismatch` / `ApprovalLineageHashInvalid` → 不 seal）。
///   producer 絕不自注 "Operator"。
/// - `api_session_topology` 用其自身之值（T2：不再覆寫 fp）；triangulation 由 seal /
///   outcome 以真 equality cross-check enforce，types 不 cross-check。
/// - 兩 hash 於組裝末尾計算（覆蓋所有實質欄位，含上述兩新欄）。
fn build_phase2_artifact_candidate(
    policy_bundle: &IbkrPhase2PolicyBundleV1,
    allowlist: &NonBybitApiAllowlistV1,
    secret_contract: &IbkrSecretSlotContractV1,
    topology: &IbkrApiSessionTopologyV1,
    approval: Option<&Phase2SealApproval>,
    immutable_storage_path: &str,
    source_commit: &str,
    now_ms: u64,
) -> IbkrPhase2GateArtifactV1 {
    let policy_flags = policy_bundle.gate_prerequisite_flags();
    let allowlist_accepted = allowlist.validate().accepted;
    let secret_accepted = secret_contract.validate().accepted;

    let gate = build_external_surface_gate(
        policy_flags,
        allowlist_accepted,
        secret_accepted,
        secret_contract.live_secret_absent_or_empty,
    );

    // T2（IBKR-P2-TRIANGULATION-CROSSCHECK）：移除舊的無條件覆寫，改用 topology 自身之
    // account_fingerprint_hash——令 triangulation 成為兩獨立真值源的真 equality
    // cross-check（見 `account_fingerprint_triangulation_ok` + seal 攔截）。遮蔽消除後：
    // pre-P5 topology 恒 source_template placeholder，production 下與 denied-secret fp
    // 不等 → triangulation mismatch → 正確 never-seal BLOCKED；topology 之真獨立 account
    // fp 源（P5 topology/session-attestation）待後續階段。
    let topo = topology.clone();

    // approval A-model：僅在 6 綁定全過時綁 reviewer_roles（含 Operator）+ 自記常量 contact
    // AMD + approval lineage hash（T1）。無效 approval → 三者皆空 → validate 拒
    // （OperatorReviewerMissing / ContactAuthorizationAmdMismatch /
    // ApprovalLineageHashInvalid），fail-closed。producer 絕不自注 "Operator"。
    let approval_valid = approval
        .map(|a| approval_is_valid(a, now_ms, source_commit))
        .unwrap_or(false);
    let (reviewer_roles, contact_authorization_amd, approval_lineage_hash) =
        match (approval_valid, approval) {
            (true, Some(a)) => (
                a.reviewer_roles.clone(),
                IBKR_PHASE2_CONTACT_AMD.to_string(),
                compute_approval_lineage_hash(a),
            ),
            _ => (Vec::new(), String::new(), String::new()),
        };

    let mut artifact = IbkrPhase2GateArtifactV1 {
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
        artifact_id: PHASE2_ARTIFACT_ID.to_string(),
        adr: IBKR_PHASE2_ADR.to_string(),
        // shape-AMD 06-29-01（型別世代，≠ contact-AMD 07-08-01；兩軸）。T1 已閉合：
        // sealed 檔另以 `contact_authorization_amd` 自記 contact 授權、以
        // `approval_lineage_hash` 自記授權它的 approval 內容指紋，二者皆入 raw/redacted
        // hash 覆蓋域（tamper-evident lineage）。
        amd: IBKR_PHASE2_AMD.to_string(),
        source_commit: source_commit.to_string(),
        created_at_ms: now_ms,
        immutable_storage_path: immutable_storage_path.to_string(),
        reviewer_roles,
        sealed: true,
        gate,
        policy_flags,
        secret_slot_contract: secret_contract.clone(),
        api_session_topology: topo,
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        contact_authorization_amd,
        approval_lineage_hash,
        supersedes_artifact_id: None,
    };
    artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
    artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);
    artifact
}

/// finding-1（T2 遮蔽已消除，真 equality 啟用；producer enforce，types 不 cross-check）：
/// secret leg 與 topology 的 account_fingerprint_hash 必相等且非空。不等 → 拒 seal。
fn account_fingerprint_triangulation_ok(a: &IbkrPhase2GateArtifactV1) -> bool {
    let secret_fp = &a.secret_slot_contract.account_fingerprint_hash;
    !secret_fp.is_empty() && *secret_fp == a.api_session_topology.account_fingerprint_hash
}

/// owner-only path 的 permission 比對必須涵蓋 permission special bits；不能只 mask
/// 低九位，否則 setuid/setgid/sticky 可偽裝成安全 mode。
#[cfg(unix)]
fn owner_only_mode_is_exact(mode: u32, expected: u32) -> bool {
    (mode & 0o7777) == expected
}

/// sealed artifact consume-time metadata 必須同時是 euid 所有的 regular file、非
/// symlink、且**精確** `0o400`。這是 lstat/fstat 共用的 invariant；任一偏差均不讀。
#[cfg(unix)]
fn sealed_artifact_metadata_is_secure(meta: &std::fs::Metadata, expected_euid: u32) -> bool {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    !meta.file_type().is_symlink()
        && meta.is_file()
        && meta.uid() as u32 == expected_euid
        && owner_only_mode_is_exact(meta.permissions().mode(), 0o400)
}

/// owner-only directory 亦要求精確 `0o700`；不能僅 mask 低九個 permission bits，
/// 否則 special bits 可偽裝成安全目錄。lstat 與 fstat 都使用同一 predicate。
#[cfg(unix)]
fn owner_only_dir_metadata_is_secure(meta: &std::fs::Metadata, expected_euid: u32) -> bool {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    !meta.file_type().is_symlink()
        && meta.is_dir()
        && meta.uid() as u32 == expected_euid
        && owner_only_mode_is_exact(meta.permissions().mode(), 0o700)
}

/// `lstat`/`fstatat(AT_SYMLINK_NOFOLLOW)` 和稍後由 FD 取得的 `fstat` 必須指向同一
/// inode；否則 lstat→open 間的 replacement race 不能被視為可 consume。
#[cfg(unix)]
#[derive(Clone, Copy)]
struct SecureInode {
    dev: u64,
    ino: u64,
}

#[cfg(unix)]
fn metadata_matches_inode(meta: &std::fs::Metadata, inode: SecureInode) -> bool {
    use std::os::unix::fs::MetadataExt;

    meta.dev() == inode.dev && meta.ino() == inode.ino
}

#[cfg(unix)]
fn inode_from_metadata(meta: &std::fs::Metadata) -> SecureInode {
    use std::os::unix::fs::MetadataExt;

    SecureInode {
        dev: meta.dev(),
        ino: meta.ino(),
    }
}

/// 從已打開的 parent dirfd 對 child 做 `fstatat(..., AT_SYMLINK_NOFOLLOW)`，並以
/// type/owner/exact-mode 檢查該 lstat inode。下一步的 `openat` 必須以
/// `O_NOFOLLOW` 打開並比對此 inode，避免任何 path-based re-resolution；因此
/// data-root 一旦 FD-bound，後續目錄與檔案皆不再依賴可替換的字串路徑。
#[cfg(unix)]
fn lstatat_owner_only_inode(
    parent_fd: std::os::unix::io::RawFd,
    child: &std::ffi::CStr,
    expected_euid: u32,
    expected_file_type: u32,
    expected_mode: u32,
) -> Option<SecureInode> {
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::fstatat(
            parent_fd,
            child.as_ptr(),
            &mut stat,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        return None;
    }
    let mode = stat.st_mode as u32;
    if (mode & libc::S_IFMT as u32) != expected_file_type
        || stat.st_uid as u32 != expected_euid
        || !owner_only_mode_is_exact(mode, expected_mode)
    {
        return None;
    }
    Some(SecureInode {
        dev: stat.st_dev as u64,
        ino: stat.st_ino as u64,
    })
}

/// 從 parent dirfd 安全地打開 owner-only child directory：lstatat（不跟 symlink）→
/// `openat(O_NOFOLLOW|O_DIRECTORY)`→fstat+inode equality。所有失敗都 fail-closed。
#[cfg(unix)]
fn open_owner_only_child_dir(
    parent: &std::fs::File,
    child_name: &str,
    expected_euid: u32,
) -> Option<std::fs::File> {
    use std::os::unix::io::{AsRawFd, FromRawFd};

    let child = std::ffi::CString::new(child_name).ok()?;
    let before = lstatat_owner_only_inode(
        parent.as_raw_fd(),
        child.as_c_str(),
        expected_euid,
        libc::S_IFDIR as u32,
        0o700,
    )?;

    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            child.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return None;
    }
    let file = unsafe { std::fs::File::from_raw_fd(fd) };
    let after = file.metadata().ok()?;
    if !owner_only_dir_metadata_is_secure(&after, expected_euid)
        || !metadata_matches_inode(&after, before)
    {
        return None;
    }
    Some(file)
}

/// 從已綁定 `ibkr_phase2` dirfd 讀 sealed artifact：fstatat→
/// `openat(O_NOFOLLOW|O_NONBLOCK)`→fstat+inode equality→FD read。這個 helper 沒有
/// 任何 path-based re-open，故組件遭替換或變 symlink 都會拒絕。`O_NONBLOCK` 是
/// consume-time 防線的一部分：即使 attacker 在 lstat 與 open 間把 regular sealed
/// file 換成 FIFO，open 也不能先卡住，必須抵達 post-open type/inode reject。
#[cfg(unix)]
fn read_owner_only_sealed_child_after_lstat<F>(
    parent: &std::fs::File,
    expected_euid: u32,
    after_lstat: F,
) -> Option<String>
where
    F: FnOnce(),
{
    use std::io::Read;
    use std::os::unix::io::{AsRawFd, FromRawFd};

    let sealed_name = std::ffi::CString::new(SEALED_FILENAME).ok()?;
    let before = lstatat_owner_only_inode(
        parent.as_raw_fd(),
        sealed_name.as_c_str(),
        expected_euid,
        libc::S_IFREG as u32,
        0o400,
    )?;

    after_lstat();

    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            sealed_name.as_ptr(),
            libc::O_RDONLY | libc::O_NONBLOCK | libc::O_NOCTTY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return None;
    }
    let mut file = unsafe { std::fs::File::from_raw_fd(fd) };
    let after = file.metadata().ok()?;
    if !sealed_artifact_metadata_is_secure(&after, expected_euid)
        || !metadata_matches_inode(&after, before)
    {
        return None;
    }

    let mut raw = String::new();
    file.read_to_string(&mut raw).ok()?;
    Some(raw)
}

/// Production wrapper keeps the final-file race hook inert. The generic helper above is also
/// used by the Unix-only test to inject a FIFO replacement exactly after `fstatat`.
#[cfg(unix)]
fn read_owner_only_sealed_child(parent: &std::fs::File, expected_euid: u32) -> Option<String> {
    read_owner_only_sealed_child_after_lstat(parent, expected_euid, || {})
}

/// 從 data-root path 打開第一個安全 dirfd。lstat+`O_NOFOLLOW|O_DIRECTORY`+fstat
/// inode equality 把 root 鎖在單一 inode；其後只能用 `openat` 沿固定
/// `governance/ibkr_phase2` 組件下降。
#[cfg(unix)]
fn open_owner_only_data_root_after_lstat<F>(path: &Path, after_lstat: F) -> Option<std::fs::File>
where
    F: FnOnce(),
{
    use std::os::unix::fs::OpenOptionsExt;

    let expected_euid = unsafe { libc::geteuid() } as u32;
    let before = std::fs::symlink_metadata(path).ok()?;
    if !owner_only_dir_metadata_is_secure(&before, expected_euid) {
        return None;
    }
    let before_inode = inode_from_metadata(&before);

    after_lstat();

    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC)
        .open(path)
        .ok()?;
    let after = file.metadata().ok()?;
    if !owner_only_dir_metadata_is_secure(&after, expected_euid)
        || !metadata_matches_inode(&after, before_inode)
    {
        return None;
    }
    Some(file)
}

#[cfg(unix)]
fn sealed_artifact_data_root(path: &Path) -> Option<&Path> {
    let ibkr_phase2 = path.parent()?;
    let governance = ibkr_phase2.parent()?;
    let data_root = governance.parent()?;
    if path.file_name()?.to_str()? != SEALED_FILENAME
        || ibkr_phase2.file_name()?.to_str()? != "ibkr_phase2"
        || governance.file_name()?.to_str()? != "governance"
        || data_root.as_os_str().is_empty()
    {
        return None;
    }
    Some(data_root)
}

/// 由 data-root 的安全 dirfd 逐層 consume sealed artifact。`after_data_root_lstat`
/// 只供 deterministic ancestor-replacement attack 測試；production 呼叫空 closure。
#[cfg(unix)]
fn read_sealed_artifact_from_secure_tree_after_data_root_lstat<F>(
    path: &Path,
    after_data_root_lstat: F,
) -> Option<String>
where
    F: FnOnce(),
{
    let expected_euid = unsafe { libc::geteuid() } as u32;
    let data_root = sealed_artifact_data_root(path)?;
    let root_fd = open_owner_only_data_root_after_lstat(data_root, after_data_root_lstat)?;
    let governance_fd = open_owner_only_child_dir(&root_fd, "governance", expected_euid)?;
    let ibkr_phase2_fd = open_owner_only_child_dir(&governance_fd, "ibkr_phase2", expected_euid)?;
    read_owner_only_sealed_child(&ibkr_phase2_fd, expected_euid)
}

#[cfg(unix)]
fn read_sealed_artifact_from_secure_tree(path: &Path) -> Option<String> {
    read_sealed_artifact_from_secure_tree_after_data_root_lstat(path, || {})
}

/// 僅供測試釘 final-file lstat→open inode replacement 防線。production consume 走
/// `read_sealed_artifact_from_secure_tree`，不保留 path-based reopen。
#[cfg(all(unix, test))]
fn read_sealed_artifact_from_secure_fd_after_lstat<F>(path: &Path, after_lstat: F) -> Option<String>
where
    F: FnOnce(),
{
    use std::io::Read;
    use std::os::unix::fs::OpenOptionsExt;

    let expected_euid = unsafe { libc::geteuid() } as u32;
    let before = std::fs::symlink_metadata(path).ok()?;
    if !sealed_artifact_metadata_is_secure(&before, expected_euid) {
        return None;
    }
    let before_inode = inode_from_metadata(&before);
    after_lstat();
    let mut file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .ok()?;
    let after = file.metadata().ok()?;
    if !sealed_artifact_metadata_is_secure(&after, expected_euid)
        || !metadata_matches_inode(&after, before_inode)
    {
        return None;
    }
    let mut raw = String::new();
    file.read_to_string(&mut raw).ok()?;
    Some(raw)
}

/// 將 immutable artifact 從 secure tree FD parse；data-root、governance、
/// ibkr_phase2 與 sealed file 都在 lstat/no-follow-open/fstat inode binding 下。
#[cfg(unix)]
fn parse_sealed_artifact_from_secure_fd(path: &Path) -> Option<IbkrPhase2GateArtifactV1> {
    let raw = read_sealed_artifact_from_secure_tree(path)?;
    serde_json::from_str(&raw).ok()
}

#[cfg(not(unix))]
fn parse_sealed_artifact_from_secure_fd(path: &Path) -> Option<IbkrPhase2GateArtifactV1> {
    let _ = path;
    None
}

/// post-seal 磁碟 re-verify（design 命名）：secure-FD consume、build-generation 綁定、
/// 與傳入 artifact 全等（含 path 欄位）、hash 自洽、且 `validate()` 放行。
fn verify_sealed_artifact_for_build(
    artifact: &IbkrPhase2GateArtifactV1,
    expected_build_sha: &str,
) -> bool {
    if !source_commit_is_known(expected_build_sha)
        || !source_commit_is_known(&artifact.source_commit)
        || artifact.source_commit != expected_build_sha
    {
        return false;
    }
    let path = Path::new(&artifact.immutable_storage_path);
    let on_disk = match parse_sealed_artifact_from_secure_fd(path) {
        Some(a) => a,
        None => return false,
    };
    &on_disk == artifact
        && on_disk.source_commit == expected_build_sha
        && verify_artifact_hashes(&on_disk)
        && on_disk.validate().ibkr_contact_allowed
}

/// Production build wrapper：sealed artifact 必須屬於當前 `BUILD_GIT_SHA`，舊世代
/// 即使 shape/hash 均合法也不可被新 binary consume。
fn verify_sealed_artifact(artifact: &IbkrPhase2GateArtifactV1) -> bool {
    verify_sealed_artifact_for_build(artifact, BUILD_GIT_SHA)
}

/// precontact / summary 用的磁碟 re-verify（path-first，含 anti-relocation、
/// secure-FD consume、以及 expected build generation 綁定）。
fn reverify_sealed_artifact_at_for_build(path: &Path, expected_build_sha: &str) -> bool {
    if !source_commit_is_known(expected_build_sha) {
        return false;
    }
    let artifact = match parse_sealed_artifact_from_secure_fd(path) {
        Some(a) => a,
        None => return false,
    };
    if !source_commit_is_known(&artifact.source_commit)
        || artifact.source_commit != expected_build_sha
        // anti-relocation：磁碟聲明的 path 必等於實際讀取的 path（防搬檔偽造 PASS）。
        || artifact.immutable_storage_path != path.to_string_lossy().into_owned()
    {
        return false;
    }
    verify_artifact_hashes(&artifact) && artifact.validate().ibkr_contact_allowed
}

/// Production build wrapper：只能 consume 與現 binary 同一 `BUILD_GIT_SHA` 的 sealed
/// artifact；unknown fallback 或跨世代 artifact 均 fail-closed。
fn reverify_sealed_artifact_at(path: &Path) -> bool {
    reverify_sealed_artifact_at_for_build(path, BUILD_GIT_SHA)
}

// ---------------------------------------------------------------------------
// 時間
// ---------------------------------------------------------------------------

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn now_ns() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// 政策 bundle 載入（真載 settings/broker/ibkr_phase2_policies.toml）
// ---------------------------------------------------------------------------

/// 純載入器：從指定 dir 讀 `ibkr_phase2_policies.toml` 並 `toml::from_str` 成 bundle。
/// 為什麼收 dir：與 P1 / stock_etf 同構——路徑解析與 load+parse 拆開，令測試以真
/// repo TOML 直驗，繞過全域 env。回 Err（不捏值）→ 呼叫端計為 leg 失敗（fail-closed）。
pub(crate) fn load_phase2_policy_bundle_from_dir(
    dir: &Path,
) -> Result<IbkrPhase2PolicyBundleV1, String> {
    let path = dir.join(POLICIES_FILENAME);
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {} failed: {e}", path.display()))?;
    let bundle: IbkrPhase2PolicyBundleV1 =
        toml::from_str(&raw).map_err(|e| format!("parse {} failed: {e}", path.display()))?;
    Ok(bundle)
}

/// broker settings dir 解析（不硬編平台路徑）：優先 `OPENCLAW_BROKER_SETTINGS_DIR`，
/// 否則相對 `settings/broker`（沿 stock_etf risk policy 的 settings-dir 約定）。
fn resolve_broker_settings_dir() -> PathBuf {
    std::env::var("OPENCLAW_BROKER_SETTINGS_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("settings").join("broker"))
}

fn load_phase2_policy_bundle() -> Result<IbkrPhase2PolicyBundleV1, String> {
    load_phase2_policy_bundle_from_dir(&resolve_broker_settings_dir())
}

// ---------------------------------------------------------------------------
// DATA_DIR / governance dir 解析（refuse-ephemeral，finding-3）
// ---------------------------------------------------------------------------

/// 找 p 的最近存在祖先（用於 canonicalize 判易失，p 本身可能尚未建立）。
fn nearest_existing_ancestor(p: &Path) -> PathBuf {
    let mut cur = p;
    loop {
        if cur.exists() {
            return cur.to_path_buf();
        }
        match cur.parent() {
            Some(par) => cur = par,
            None => return p.to_path_buf(),
        }
    }
}

/// 是否落在易失盤（refuse-ephemeral）。同時檢查 canonicalize 後（解 symlink，如 Mac
/// `/tmp`→`/private/tmp`）與原字串，任一命中易失前綴即 true。
fn is_ephemeral_path(p: &Path) -> bool {
    let probe = nearest_existing_ancestor(p);
    let canon = probe.canonicalize().unwrap_or(probe);
    let hit = |s: &str| {
        EPHEMERAL_PREFIXES.iter().copied().any(|pre| {
            // 命中：s 恰等於前綴，或 s 以「前綴 + '/'」開頭（避免 /tmpfoo 誤判）。
            s == pre || (s.starts_with(pre) && s.as_bytes().get(pre.len()) == Some(&b'/'))
        })
    };
    hit(canon.to_string_lossy().as_ref()) || hit(p.to_string_lossy().as_ref())
}

/// 解析治理目錄 `<OPENCLAW_DATA_DIR>/governance/ibkr_phase2`；未設 / 易失 → 拒
/// （`EphemeralDataDir`），**絕不**沿 `/tmp/openclaw` fallback。
fn resolve_phase2_governance_dir() -> Result<PathBuf, Phase2SealError> {
    let raw = std::env::var("OPENCLAW_DATA_DIR").map_err(|_| Phase2SealError::EphemeralDataDir)?;
    if raw.trim().is_empty() {
        return Err(Phase2SealError::EphemeralDataDir);
    }
    let data_dir = PathBuf::from(raw);
    if is_ephemeral_path(&data_dir) {
        return Err(Phase2SealError::EphemeralDataDir);
    }
    Ok(data_dir.join("governance").join("ibkr_phase2"))
}

// ---------------------------------------------------------------------------
// approval reader（owner-only；#[cfg(unix)]）
// ---------------------------------------------------------------------------

/// gov_dir 與其父 `governance/` 皆須是 euid owner 的 regular directory 且精確
/// mode==0o700（包含拒 special bits）。這是 seal/approval path 的 owner-only
/// invariant；production sealed consume 另外以 dirfd/openat 鎖整條 data-root 鏈。
#[cfg(unix)]
fn check_dir_pair_owner_only(gov_dir: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;

    let euid = unsafe { libc::geteuid() } as u32;
    for dir in [Some(gov_dir), gov_dir.parent()] {
        let path = dir.ok_or_else(|| "gov_dir has no parent (governance) dir".to_string())?;
        let meta = std::fs::symlink_metadata(path)
            .map_err(|e| format!("gov ancestor stat {} failed: {e}", path.display()))?;
        if !owner_only_dir_metadata_is_secure(&meta, euid) {
            return Err(format!(
                "gov ancestor not owner-only regular 0o700 dir: {} mode={:#o}",
                path.display(),
                meta.permissions().mode() & 0o7777
            ));
        }
    }
    Ok(())
}

/// approval A-model 讀取器。缺檔 → `Ok(None)`（absent → 呼叫端不注入 Operator）；
/// symlink / 非 0o600 / 非本人所有 / 祖先鏈非 0o700 → `Err`（fail-closed）；存在且
/// 合法 → `Ok(Some)`。內容 6 綁定由 `approval_is_valid` 於組裝/seal 時判定。
#[cfg(unix)]
pub(crate) fn load_phase2_seal_approval_from_dir(
    gov_dir: &Path,
) -> Result<Option<Phase2SealApproval>, String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let path = gov_dir.join(APPROVAL_FILENAME);
    let meta = match std::fs::symlink_metadata(&path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("approval stat {} failed: {e}", path.display())),
    };
    // bind #1：檔本身不得為 symlink（lstat 不跟隨）。
    if meta.file_type().is_symlink() {
        return Err(format!(
            "approval file is symlink (denied): {}",
            path.display()
        ));
    }
    if !meta.is_file() {
        return Err(format!(
            "approval path is not a regular file: {}",
            path.display()
        ));
    }
    let euid = unsafe { libc::geteuid() } as u32;
    if (meta.permissions().mode() & 0o777) != 0o600 {
        return Err(format!("approval file not 0o600: {}", path.display()));
    }
    if meta.uid() as u32 != euid {
        return Err(format!(
            "approval file not owned by euid: {}",
            path.display()
        ));
    }
    // bind #1：0o700 祖先鏈。
    check_dir_pair_owner_only(gov_dir)?;

    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read approval {} failed: {e}", path.display()))?;
    let approval: Phase2SealApproval = toml::from_str(&raw)
        .map_err(|e| format!("parse approval {} failed: {e}", path.display()))?;
    Ok(Some(approval))
}

/// 非 unix：無法驗權限/owner → 結構性 fail-closed 視為無 approval（不注入 Operator）。
/// 部署目標皆 unix（Linux / Apple Silicon），此路徑實務不觸發。
#[cfg(not(unix))]
pub(crate) fn load_phase2_seal_approval_from_dir(
    gov_dir: &Path,
) -> Result<Option<Phase2SealApproval>, String> {
    let _ = gov_dir;
    Ok(None)
}

// ---------------------------------------------------------------------------
// seal（write-once；雙綠 + triangulation 才寫；#[cfg(unix)]）
// ---------------------------------------------------------------------------

/// write-once 封存。**絕不用 rename**（overwrite 語義會毀 write-once）：
/// `create_new` 唯一 tmp → `sync_all` → `hard_link(tmp,final)`（final 已存在 →
/// `AlreadySealed`）→ 移除 tmp → 0o400 → fsync 父目錄。gov_dir 以 `DirBuilder(0o700)`
/// 建（只影響新建目錄），寫前驗 owner-only（既有目錄權限過寬 → Err）。
///
/// 為什麼 seal 不做 refuse-ephemeral：refuse-ephemeral 在 `resolve_phase2_governance_dir`
/// （env→gov_dir 解析）強制；本純函數收「已解析的」gov_dir，令測試能把 sealed 檔寫進
/// tempdir（tempdir 本就落 /tmp）。production 唯一到達 seal 的路徑仍經 resolve 的
/// ephemeral 閘。
#[cfg(unix)]
fn seal_phase2_artifact(
    artifact: &IbkrPhase2GateArtifactV1,
    gov_dir: &Path,
) -> Result<PathBuf, Phase2SealError> {
    use std::io::Write;
    use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};

    // 雙綠 + triangulation（無 fake-success：任一不成立絕不寫檔）。
    if !artifact.validate().ibkr_contact_allowed {
        return Err(Phase2SealError::NotValid);
    }
    if !verify_artifact_hashes(artifact) {
        return Err(Phase2SealError::NotValid);
    }
    if !account_fingerprint_triangulation_ok(artifact) {
        return Err(Phase2SealError::NotValid);
    }

    let final_path = gov_dir.join(SEALED_FILENAME);
    // path 綁定：artifact 聲明的 immutable_storage_path 必等於實際落檔路徑。
    if artifact.immutable_storage_path != final_path.to_string_lossy().into_owned() {
        return Err(Phase2SealError::NotValid);
    }

    // 建 governance/ibkr_phase2 鏈（0o700，只影響新建目錄；既有目錄權限不改）。
    std::fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(gov_dir)
        .map_err(|e| {
            Phase2SealError::IoError(format!("create gov_dir {} failed: {e}", gov_dir.display()))
        })?;
    // 寫前驗 owner-only（既有目錄權限過寬即 Err）。
    check_dir_pair_owner_only(gov_dir).map_err(Phase2SealError::IoError)?;

    // write-once：唯一 tmp（pid.nanos）→ create_new → sync_all。
    let tmp_path = gov_dir.join(format!(
        "{SEALED_FILENAME}.{}.{}.tmp",
        std::process::id(),
        now_ns()
    ));
    let json = serde_json::to_string_pretty(artifact)
        .map_err(|e| Phase2SealError::IoError(format!("serialize artifact failed: {e}")))?;
    {
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&tmp_path)
            .map_err(|e| {
                Phase2SealError::IoError(format!(
                    "create_new tmp {} failed: {e}",
                    tmp_path.display()
                ))
            })?;
        f.write_all(json.as_bytes()).map_err(|e| {
            Phase2SealError::IoError(format!("write tmp {} failed: {e}", tmp_path.display()))
        })?;
        f.flush().map_err(|e| {
            Phase2SealError::IoError(format!("flush tmp {} failed: {e}", tmp_path.display()))
        })?;
        f.sync_all().map_err(|e| {
            Phase2SealError::IoError(format!("sync_all tmp {} failed: {e}", tmp_path.display()))
        })?;
    }

    // hard_link → final；final 已存在 = 拒二次 seal（絕不 rename overwrite）。
    match std::fs::hard_link(&tmp_path, &final_path) {
        Ok(()) => {}
        Err(e) => {
            let _ = std::fs::remove_file(&tmp_path);
            if e.kind() == std::io::ErrorKind::AlreadyExists {
                return Err(Phase2SealError::AlreadySealed);
            }
            return Err(Phase2SealError::IoError(format!(
                "hard_link to {} failed: {e}",
                final_path.display()
            )));
        }
    }
    // 移除 tmp（inode 經 final link 存活）；set final 唯讀 0o400；fsync 父目錄使 dir
    // entry durable（crash 半檔由 consume 端 verify 抓——hash 不符）。
    let _ = std::fs::remove_file(&tmp_path);
    std::fs::set_permissions(&final_path, std::fs::Permissions::from_mode(0o400)).map_err(|e| {
        Phase2SealError::IoError(format!("chmod final {} failed: {e}", final_path.display()))
    })?;
    if let Ok(dir) = std::fs::File::open(gov_dir) {
        let _ = dir.sync_all();
    }
    Ok(final_path)
}

/// 非 unix：無 owner-only/mode 保證 → 結構性拒 seal。
#[cfg(not(unix))]
fn seal_phase2_artifact(
    artifact: &IbkrPhase2GateArtifactV1,
    gov_dir: &Path,
) -> Result<PathBuf, Phase2SealError> {
    let _ = (artifact, gov_dir);
    Err(Phase2SealError::IoError(
        "seal unsupported on non-unix (permission/owner checks unavailable)".to_string(),
    ))
}

// ---------------------------------------------------------------------------
// 秘密槽 leg（復用 P1 OnceLock；Err → 同一 denied fallback）
// ---------------------------------------------------------------------------

fn secret_slot_contract_cloned() -> IbkrSecretSlotContractV1 {
    match crate::ibkr_secret_slot_loader::ibkr_secret_slot_contract() {
        Ok(c) => c.clone(),
        Err(_) => crate::ibkr_secret_slot_loader::denied_ibkr_secret_slot_contract_fallback(),
    }
}

// ---------------------------------------------------------------------------
// producer outcome + summary（report-only 現狀；不寫檔）
// ---------------------------------------------------------------------------

/// env-wrapper：解析 dir → 組裝 → verdict。**現狀只 report 不 seal**（真槽 absent +
/// 無 approval → 必然 Blocked，這是正確 fail-closed）。收集 producer-層 reason
/// （ephemeral / source_commit_unknown / triangulation）+ artifact `validate()`
/// blockers（PascalCase 字串）。
fn phase2_producer_outcome() -> Phase2ProducerOutcome {
    let source_commit = BUILD_GIT_SHA.to_string();
    let now = now_ms();
    let mut blockers: Vec<String> = Vec::new();

    // gov_dir / refuse-ephemeral
    let gov_dir_res = resolve_phase2_governance_dir();
    let data_dir_ephemeral = matches!(&gov_dir_res, Err(Phase2SealError::EphemeralDataDir));
    if data_dir_ephemeral {
        blockers.push(REASON_EPHEMERAL.to_string());
    }

    // source_commit 世代
    let source_commit_known = source_commit_is_known(&source_commit);
    if !source_commit_known {
        blockers.push(REASON_SOURCE_COMMIT_UNKNOWN.to_string());
    }

    // legs
    let policy_bundle = load_phase2_policy_bundle().ok();
    let policy_bundle_accepted = policy_bundle
        .as_ref()
        .map(|b| b.validate().accepted)
        .unwrap_or(false);
    let bundle_for_build = policy_bundle.unwrap_or_default();

    let allowlist = NonBybitApiAllowlistV1::accepted_fixture();
    let api_allowlist_accepted = allowlist.validate().accepted;

    let secret = secret_slot_contract_cloned();
    let secret_contract_accepted = secret.validate().accepted;

    let topology = IbkrApiSessionTopologyV1::source_template();

    let approval = match &gov_dir_res {
        Ok(gd) => load_phase2_seal_approval_from_dir(gd).unwrap_or(None),
        Err(_) => None,
    };
    let approval_present = approval.is_some();
    let approval_valid = approval
        .as_ref()
        .map(|a| approval_is_valid(a, now, &source_commit))
        .unwrap_or(false);

    let immutable_storage_path = gov_dir_res
        .as_ref()
        .map(|gd| gd.join(SEALED_FILENAME).to_string_lossy().into_owned())
        .unwrap_or_default();

    let artifact = build_phase2_artifact_candidate(
        &bundle_for_build,
        &allowlist,
        &secret,
        &topology,
        approval.as_ref(),
        &immutable_storage_path,
        &source_commit,
        now,
    );

    let triangulation_ok = account_fingerprint_triangulation_ok(&artifact);
    if !triangulation_ok {
        blockers.push(REASON_TRIANGULATION.to_string());
    }

    let artifact_verdict = artifact.validate();
    for b in &artifact_verdict.blockers {
        blockers.push(format!("{b:?}"));
    }

    let leg_status = Phase2LegStatus {
        data_dir_ephemeral,
        source_commit_known,
        policy_bundle_accepted,
        api_allowlist_accepted,
        secret_contract_accepted,
        api_topology_accepted: artifact.api_session_topology.validate().accepted,
        external_surface_gate_accepted: artifact.gate.validate().ibkr_contact_allowed,
        approval_present,
        approval_valid,
        account_fingerprint_triangulation_ok: triangulation_ok,
        artifact_contact_allowed: artifact_verdict.ibkr_contact_allowed,
        artifact_hashes_verified: verify_artifact_hashes(&artifact),
    };

    // 現狀：report-only，永不由本 wrapper 調 seal（真 seal 啟用 = operator 決策）。
    Phase2ProducerOutcome::Blocked {
        blockers,
        leg_status,
    }
}

/// IPC 顯示面（zero 明文；只回 posture/bool/64-hex/enum 與 blocker 名）。
pub(crate) fn phase2_gate_producer_summary() -> serde_json::Value {
    let present = phase2_immutable_pass_artifact_present();
    let (producer_status, blockers, leg_status, sealed_path) = match phase2_producer_outcome() {
        Phase2ProducerOutcome::Blocked {
            blockers,
            leg_status,
        } => ("blocked", blockers, Some(leg_status), None),
        Phase2ProducerOutcome::Sealed { path } => (
            "sealed",
            Vec::new(),
            None,
            Some(path.to_string_lossy().into_owned()),
        ),
        Phase2ProducerOutcome::AlreadySealed { path } => (
            "already_sealed",
            Vec::new(),
            None,
            Some(path.to_string_lossy().into_owned()),
        ),
    };

    serde_json::json!({
        "producer_status": producer_status,
        "immutable_pass_artifact_present": present,
        "blockers": blockers,
        "leg_status": leg_status,
        "sealed_artifact_basename": sealed_path.map(|_| SEALED_FILENAME),
        "adr": IBKR_PHASE2_ADR,
        "artifact_shape_amd": IBKR_PHASE2_AMD,
        "contact_authorization_amd": IBKR_PHASE2_CONTACT_AMD,
        "ibkr_call_performed": false,
        "seal_written_this_phase": false,
    })
}

/// precontact 唯一 production 消費點：磁碟 sealed 態 re-verify（非 file-exists）。
/// gov_dir 無法解析（未設 / 易失）或無合法 sealed 檔 → false（fail-closed）。
pub(crate) fn phase2_immutable_pass_artifact_present() -> bool {
    let gov_dir = match resolve_phase2_governance_dir() {
        Ok(d) => d,
        Err(_) => return false,
    };
    reverify_sealed_artifact_at(&gov_dir.join(SEALED_FILENAME))
}

// ===========================================================================
// 測試（全 tempdir 純函數；權限/seal 測試 #[cfg(unix)]；env-mutating 測試共用鎖）
// ===========================================================================

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use openclaw_types::IbkrPhase2GateArtifactBlocker as B;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    const FIXED_NOW: u64 = 1_800_000_000_000;

    fn fake_sha() -> String {
        "a".repeat(40)
    }

    /// 建 governance/ibkr_phase2 鏈（皆 0o700），回 ibkr_phase2 路徑。
    fn make_gov_chain(root: &Path) -> PathBuf {
        let gov_parent = root.join("governance");
        let gov = gov_parent.join("ibkr_phase2");
        fs::create_dir_all(&gov).unwrap();
        // tempfile 在 macOS 預設可能是 0o755；這裡扮演 production data-root，
        // 故 fixture 也必須滿足 consume-time owner-only 0o700 invariant。
        fs::set_permissions(root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&gov_parent, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&gov, fs::Permissions::from_mode(0o700)).unwrap();
        gov
    }

    fn valid_bundle() -> IbkrPhase2PolicyBundleV1 {
        IbkrPhase2PolicyBundleV1::source_template()
    }
    fn valid_allowlist() -> NonBybitApiAllowlistV1 {
        NonBybitApiAllowlistV1::accepted_fixture()
    }
    fn valid_secret() -> IbkrSecretSlotContractV1 {
        IbkrSecretSlotContractV1::source_template()
    }
    fn valid_topology() -> IbkrApiSessionTopologyV1 {
        IbkrApiSessionTopologyV1::source_template()
    }

    /// T2：覆寫移除後，全綠候選需 topology fp == secret fp 才過 triangulation
    /// （source_template topology="c"*64 ≠ secret="b"*64，不對齊即 seal 失敗）。
    /// 此 helper 模擬 P5 之「topology 有真獨立且與 secret 一致的 account fp 源」。
    fn matched_topology(secret: &IbkrSecretSlotContractV1) -> IbkrApiSessionTopologyV1 {
        let mut topo = IbkrApiSessionTopologyV1::source_template();
        topo.account_fingerprint_hash = secret.account_fingerprint_hash.clone();
        topo
    }

    fn direct_approval(now: u64, sha: &str) -> Phase2SealApproval {
        Phase2SealApproval {
            adr: "ADR-0048".to_string(),
            amd: IBKR_PHASE2_CONTACT_AMD.to_string(),
            reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
            approved_source_commit: sha.to_string(),
            issued_at_ms: now - 1000,
            expires_at_ms: now + 3_600_000,
        }
    }

    fn write_approval(
        gov: &Path,
        adr: &str,
        amd: &str,
        roles: &[&str],
        sha: &str,
        issued: u64,
        expires: u64,
    ) {
        let roles_toml = roles
            .iter()
            .map(|r| format!("\"{r}\""))
            .collect::<Vec<_>>()
            .join(", ");
        let content = format!(
            "adr = \"{adr}\"\namd = \"{amd}\"\nreviewer_roles = [{roles_toml}]\n\
             approved_source_commit = \"{sha}\"\nissued_at_ms = {issued}\nexpires_at_ms = {expires}\n"
        );
        let p = gov.join(APPROVAL_FILENAME);
        fs::write(&p, content).unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o600)).unwrap();
    }

    /// 組全綠候選（approval 直建有效），immutable_storage_path=gov/SEALED。
    /// T2：topology 用 `matched_topology`（fp 對齊 secret）令 triangulation 過。
    fn build_full_green_for_sha(gov: &Path, sha: &str) -> IbkrPhase2GateArtifactV1 {
        let approval = direct_approval(FIXED_NOW, sha);
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let secret = valid_secret();
        build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &secret,
            &matched_topology(&secret),
            Some(&approval),
            &path,
            sha,
            FIXED_NOW,
        )
    }

    fn build_full_green(gov: &Path) -> IbkrPhase2GateArtifactV1 {
        build_full_green_for_sha(gov, &fake_sha())
    }

    // --- T1: 全綠 → validate + verify 雙綠 → seal 寫檔 0o400 + verify_sealed true ---
    #[test]
    fn t1_full_green_seal() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        // 順帶跑 approval 檔讀取器 happy path。
        write_approval(
            &gov,
            "ADR-0048",
            "AMD-2026-07-08-01",
            &["PM", "Operator"],
            &fake_sha(),
            FIXED_NOW - 1000,
            FIXED_NOW + 3_600_000,
        );
        let loaded = load_phase2_seal_approval_from_dir(&gov).unwrap();
        assert!(loaded.is_some(), "approval file should load");

        let artifact = build_full_green(&gov);
        let v = artifact.validate();
        assert!(
            v.ibkr_contact_allowed,
            "unexpected blockers: {:?}",
            v.blockers
        );
        assert!(verify_artifact_hashes(&artifact));
        // T1：sealed 檔自記 contact AMD（= 常量）+ 非空 approval lineage hash（64-hex）。
        assert_eq!(artifact.contact_authorization_amd, IBKR_PHASE2_CONTACT_AMD);
        assert!(openclaw_types::is_sha256_hex(
            &artifact.approval_lineage_hash
        ));

        let sealed = seal_phase2_artifact(&artifact, &gov).expect("seal ok");
        let mode = fs::symlink_metadata(&sealed).unwrap().permissions().mode() & 0o7777;
        assert_eq!(mode, 0o400, "sealed file must be read-only 0o400");
        assert!(
            verify_sealed_artifact_for_build(&artifact, &fake_sha()),
            "post-seal secure-FD re-verify must pass for its exact build generation"
        );
        assert!(reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
    }

    // --- W1: consumer generation binding（valid hash/shape 也不可跨 BUILD_GIT_SHA）---
    #[test]
    fn sealed_consume_rejects_cross_generation_and_unknown_build_sha() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();

        assert!(reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
        assert!(!reverify_sealed_artifact_at_for_build(
            &sealed,
            &"b".repeat(40),
        ));
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, "unknown"));
    }

    // --- W1: artifact 的 generation 也不得為 build.rs unknown fallback ---
    #[test]
    fn sealed_consume_rejects_unknown_artifact_generation_even_with_valid_hashes() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();

        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o600)).unwrap();
        let mut on_disk: IbkrPhase2GateArtifactV1 =
            serde_json::from_str(&fs::read_to_string(&sealed).unwrap()).unwrap();
        on_disk.source_commit = "unknown".to_string();
        on_disk.raw_artifact_hash = compute_raw_artifact_hash(&on_disk);
        on_disk.redacted_summary_hash = compute_redacted_summary_hash(&on_disk);
        fs::write(&sealed, serde_json::to_string_pretty(&on_disk).unwrap()).unwrap();
        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o400)).unwrap();

        assert!(
            verify_artifact_hashes(&on_disk),
            "fixture must be hash-valid"
        );
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
    }

    // --- W1: consume-time lstat rejects wrong mode, symlink, and non-regular file ---
    #[test]
    fn sealed_consume_rejects_insecure_file_kinds_and_mode() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();

        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o400)).unwrap();

        let replacement_target = gov.join("sealed-artifact-symlink-target.json");
        fs::copy(&sealed, &replacement_target).unwrap();
        fs::set_permissions(&replacement_target, fs::Permissions::from_mode(0o400)).unwrap();
        fs::remove_file(&sealed).unwrap();
        std::os::unix::fs::symlink(&replacement_target, &sealed).unwrap();
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));

        fs::remove_file(&sealed).unwrap();
        fs::create_dir(&sealed).unwrap();
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
    }

    // --- W1/E2: exact owner-only modes reject setuid/setgid/sticky, even where
    // the host filesystem declines to materialize special bits for an unprivileged user. ---
    #[test]
    fn sealed_consume_mode_guard_rejects_special_bits_for_file_and_every_secure_dir() {
        assert!(owner_only_mode_is_exact(0o400, 0o400));
        assert!(owner_only_mode_is_exact(0o700, 0o700));
        for insecure_file_mode in [0o1400, 0o2400, 0o4400] {
            assert!(
                !owner_only_mode_is_exact(insecure_file_mode, 0o400),
                "sealed 0o400 must reject special bits: {insecure_file_mode:#o}"
            );
        }
        for insecure_dir_mode in [0o1700, 0o2700, 0o4700] {
            assert!(
                !owner_only_mode_is_exact(insecure_dir_mode, 0o700),
                "owner-only 0o700 dir must reject special bits: {insecure_dir_mode:#o}"
            );
        }
    }

    // --- W1/E3: pure metadata owner mismatch test; no chown and no root-only skip. ---
    #[test]
    fn sealed_consume_rejects_owner_mismatch_without_mutating_fixture_ownership() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        let euid = unsafe { libc::geteuid() } as u32;
        let foreign_uid = if euid == 0 { 1 } else { 0 };

        let sealed_meta = fs::symlink_metadata(&sealed).unwrap();
        let root_meta = fs::symlink_metadata(tmp.path()).unwrap();
        assert!(!sealed_artifact_metadata_is_secure(
            &sealed_meta,
            foreign_uid
        ));
        assert!(!owner_only_dir_metadata_is_secure(&root_meta, foreign_uid));
    }

    // --- W1/E3: replacing data-root after lstat cannot redirect the fd-bound tree. ---
    #[test]
    fn sealed_consume_rejects_data_root_lstat_to_open_replacement_attack() {
        let tmp = tempfile::tempdir().unwrap();
        let data_root = tmp.path().join("data-root");
        let retired_root = tmp.path().join("retired-data-root");
        let replacement_root = tmp.path().join("replacement-data-root");
        fs::create_dir(&data_root).unwrap();
        let gov = make_gov_chain(&data_root);
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        fs::create_dir(&replacement_root).unwrap();
        fs::set_permissions(&replacement_root, fs::Permissions::from_mode(0o700)).unwrap();

        assert!(
            read_sealed_artifact_from_secure_tree_after_data_root_lstat(&sealed, || {
                fs::rename(&data_root, &retired_root).unwrap();
                fs::rename(&replacement_root, &data_root).unwrap();
            })
            .is_none(),
            "replacement data-root after lstat must never be consumed"
        );
    }

    // --- W1/E3: production wrappers bind to this binary's BUILD_GIT_SHA or fail closed. ---
    #[test]
    fn sealed_consume_production_wrappers_require_current_build_generation() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());

        if source_commit_is_known(BUILD_GIT_SHA) {
            let artifact = build_full_green_for_sha(&gov, BUILD_GIT_SHA);
            let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
            assert!(verify_sealed_artifact(&artifact));
            assert!(reverify_sealed_artifact_at(&sealed));
        } else {
            let artifact = build_full_green(&gov);
            let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
            assert!(!verify_sealed_artifact(&artifact));
            assert!(!reverify_sealed_artifact_at(&sealed));
        }
    }

    // --- W1: replacement between lstat and open is detected by fstat dev/inode binding ---
    #[test]
    fn sealed_consume_rejects_lstat_to_open_replacement_attack() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        let replacement = gov.join("replacement.sealed.json");
        fs::copy(&sealed, &replacement).unwrap();
        fs::set_permissions(&replacement, fs::Permissions::from_mode(0o400)).unwrap();

        assert!(
            read_sealed_artifact_from_secure_fd_after_lstat(&sealed, || {
                fs::rename(&replacement, &sealed).unwrap();
            })
            .is_none(),
            "an inode replacement after lstat must never reach the parser"
        );
    }

    // --- W1/P1: a FIFO swapped in after final-file lstat must not make `openat` block.
    // O_NONBLOCK brings the descriptor far enough to fstat/type+inode rejection; no wall-clock
    // assertion is needed (or desirable) because the absence of a FIFO writer would otherwise
    // make the old blocking open hang this deterministic test. ---
    #[test]
    fn sealed_consume_rejects_lstat_to_open_fifo_replacement_without_blocking() {
        use std::os::unix::ffi::OsStrExt;
        use std::os::unix::fs::FileTypeExt;

        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        let parent = fs::File::open(&gov).unwrap();
        let euid = unsafe { libc::geteuid() } as u32;

        let result = read_owner_only_sealed_child_after_lstat(&parent, euid, || {
            fs::remove_file(&sealed).unwrap();
            let fifo_path = std::ffi::CString::new(sealed.as_os_str().as_bytes()).unwrap();
            assert_eq!(unsafe { libc::mkfifo(fifo_path.as_ptr(), 0o400) }, 0);
        });

        let fifo_meta = fs::symlink_metadata(&sealed).unwrap();
        fs::remove_file(&sealed).unwrap();
        assert!(
            fifo_meta.file_type().is_fifo(),
            "fixture must replace with FIFO"
        );
        assert!(
            result.is_none(),
            "FIFO replacement after lstat must be rejected without blocking"
        );
    }

    // --- T2: 二次 seal → AlreadySealed，原檔 byte-identical ---
    #[test]
    fn t2_second_seal_already_sealed() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        let bytes1 = fs::read(&sealed).unwrap();

        let err = seal_phase2_artifact(&artifact, &gov).unwrap_err();
        assert_eq!(err, Phase2SealError::AlreadySealed);
        let bytes2 = fs::read(&sealed).unwrap();
        assert_eq!(
            bytes1, bytes2,
            "original sealed file must be byte-identical"
        );
        // 無殘留 tmp。
        let tmp_left: Vec<_> = fs::read_dir(&gov)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().ends_with(".tmp"))
            .collect();
        assert!(tmp_left.is_empty(), "no tmp file should remain");
    }

    // --- T3: paper 槽 absent（P1 denied secret）→ Blocked 含 secret+gate reject，無檔 ---
    #[test]
    fn t3_secret_absent_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let approval = direct_approval(FIXED_NOW, &sha);
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let denied_secret =
            crate::ibkr_secret_slot_loader::denied_ibkr_secret_slot_contract_fallback();
        let artifact = build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &denied_secret,
            &valid_topology(),
            Some(&approval),
            &path,
            &sha,
            FIXED_NOW,
        );
        let v = artifact.validate();
        assert!(v.blockers.contains(&B::SecretSlotContractRejected));
        assert!(v.blockers.contains(&B::ExternalSurfaceGateRejected));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(
            !gov.join(SEALED_FILENAME).exists(),
            "no sealed file must be written"
        );
    }

    // --- T4: approval absent → Blocked 含 OperatorReviewerMissing，無檔 ---
    #[test]
    fn t4_approval_absent_operator_missing() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let artifact = build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &valid_secret(),
            &valid_topology(),
            None,
            &path,
            &fake_sha(),
            FIXED_NOW,
        );
        let v = artifact.validate();
        assert!(v.blockers.contains(&B::OperatorReviewerMissing));
        assert!(v.blockers.contains(&B::PmReviewerMissing));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T5: 篡改 raw/redacted hash（合法 64-hex 錯值）→ verify false → 拒 ---
    #[test]
    fn t5_tampered_hash_verify_false() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let base = build_full_green(&gov);
        assert!(verify_artifact_hashes(&base));

        let mut t_raw = base.clone();
        t_raw.raw_artifact_hash = "b".repeat(64);
        assert!(!verify_artifact_hashes(&t_raw));
        assert!(seal_phase2_artifact(&t_raw, &gov).is_err());

        let mut t_red = base.clone();
        t_red.redacted_summary_hash = "c".repeat(64);
        assert!(!verify_artifact_hashes(&t_red));
        assert!(seal_phase2_artifact(&t_red, &gov).is_err());

        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T6: ibkr_call_performed=true → validate reject IbkrCallAlreadyPerformed，不 seal ---
    #[test]
    fn t6_ibkr_call_performed_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let mut artifact = build_full_green(&gov);
        artifact.gate.ibkr_call_performed = true;
        // 重算 hash 以隔離 validate 拒絕（否則會先被 hash 自洽攔）。
        artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
        artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);

        assert!(verify_artifact_hashes(&artifact));
        assert!(artifact
            .validate()
            .blockers
            .contains(&B::IbkrCallAlreadyPerformed));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T7: source_commit=="unknown" → approval 失效 + source_commit_known false → Blocked ---
    #[test]
    fn t7_source_commit_unknown_blocked() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        assert!(!source_commit_is_known("unknown"));
        let approval = direct_approval(FIXED_NOW, "unknown");
        // approval.approved_source_commit=="unknown" 且 build_sha=="unknown" → 仍失效。
        assert!(!approval_is_valid(&approval, FIXED_NOW, "unknown"));
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let artifact = build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &valid_secret(),
            &valid_topology(),
            Some(&approval),
            &path,
            "unknown",
            FIXED_NOW,
        );
        assert!(artifact
            .validate()
            .blockers
            .contains(&B::OperatorReviewerMissing));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T8: policy flag=false → PolicyPrerequisiteFlagsRejected + ExternalSurfaceGateRejected ---
    // 註：設計文案另提 PolicyGateFlagMismatch，但 producer 令 gate 5 flag = policy_flags，
    // 兩者同步為 false → 不 mismatch；mismatch 由 T9 專測。此處斷言真實發生的 blocker。
    #[test]
    fn t8_policy_flag_false_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let mut bundle = valid_bundle();
        bundle.redaction.policy_present = false; // redaction.validate() 失敗 → flag false
        let sha = fake_sha();
        let approval = direct_approval(FIXED_NOW, &sha);
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let artifact = build_phase2_artifact_candidate(
            &bundle,
            &valid_allowlist(),
            &valid_secret(),
            &valid_topology(),
            Some(&approval),
            &path,
            &sha,
            FIXED_NOW,
        );
        let v = artifact.validate();
        assert!(v.blockers.contains(&B::PolicyPrerequisiteFlagsRejected));
        assert!(v.blockers.contains(&B::ExternalSurfaceGateRejected));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T9: gate flag 不對齊 policy_flags → PolicyGateFlagMismatch，無檔 ---
    #[test]
    fn t9_gate_flag_mismatch() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let mut artifact = build_full_green(&gov);
        // policy_flags.redaction_suite_passed 仍 true；令 gate 反向 → mismatch。
        artifact.gate.redaction_suite_passed = false;
        artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
        artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);

        let v = artifact.validate();
        assert!(v.blockers.contains(&B::PolicyGateFlagMismatch));
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T10: redacted summary 零本機路徑 + 只用 hash（無明文欄位可容）---
    #[test]
    fn t10_redacted_summary_no_path_no_plaintext() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let redacted = serde_json::to_string(&redacted_summary_value(&artifact)).unwrap();
        // 不洩本機路徑（immutable_storage_path 刻意不入 redacted）。
        assert!(
            !redacted.contains(gov.to_string_lossy().as_ref()),
            "redacted summary leaked local path: {redacted}"
        );
        assert!(!redacted.contains("immutable_storage_path"));
        // 用 hash（64-hex）而非明文。
        assert!(redacted.contains(&artifact.secret_slot_contract.account_fingerprint_hash));
    }

    // --- T11: gov_dir 非 0o700 → seal Err（IoError），無檔 ---
    #[test]
    fn t11_gov_dir_wrong_perms_err() {
        let tmp = tempfile::tempdir().unwrap();
        let gov_parent = tmp.path().join("governance");
        let gov = gov_parent.join("ibkr_phase2");
        fs::create_dir_all(&gov).unwrap();
        fs::set_permissions(&gov_parent, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&gov, fs::Permissions::from_mode(0o750)).unwrap(); // 過寬

        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        let sha = fake_sha();
        let approval = direct_approval(FIXED_NOW, &sha);
        let secret = valid_secret();
        // T2：用 matched_topology 令 triangulation 過，seal 才會抵達目錄權限閘（否則會先
        // 在 triangulation 被 NotValid 攔，此測試就不再測權限）。
        let artifact = build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &secret,
            &matched_topology(&secret),
            Some(&approval),
            &path,
            &sha,
            FIXED_NOW,
        );
        assert!(seal_phase2_artifact(&artifact, &gov).is_err());
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- T12: 真載 consuming repo TOML → bundle.validate().accepted ---
    #[test]
    fn t12_real_policies_toml_accepted() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("settings")
            .join("broker");
        let bundle = load_phase2_policy_bundle_from_dir(&dir).expect("load real policies TOML");
        let v = bundle.validate();
        assert!(
            v.accepted,
            "real policies bundle rejected: {:?}",
            v.blockers
        );
    }

    // --- F1(finding-1): 兩 account_fingerprint_hash 不等 → 拒 seal ---
    #[test]
    fn f1_triangulation_mismatch_refused() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let mut artifact = build_full_green(&gov);
        // build 已把 topology fp 對齊 secret；此處人為破壞 + 重算 hash 令 verify 過。
        artifact.api_session_topology.account_fingerprint_hash = "d".repeat(64);
        artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
        artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);

        assert!(!account_fingerprint_triangulation_ok(&artifact));
        // validate 不 cross-check fp → 仍放行；triangulation 由 seal 攔。
        assert!(artifact.validate().ibkr_contact_allowed);
        assert!(verify_artifact_hashes(&artifact));
        assert_eq!(
            seal_phase2_artifact(&artifact, &gov),
            Err(Phase2SealError::NotValid)
        );
        assert!(!gov.join(SEALED_FILENAME).exists());
    }

    // --- F3(finding-3): DATA_DIR 未設 / 落 /tmp → 拒（EphemeralDataDir）---
    #[test]
    fn f3_ephemeral_data_dir_refused() {
        let _g = crate::test_env_lock::guard();
        let prev = std::env::var("OPENCLAW_DATA_DIR").ok();

        std::env::remove_var("OPENCLAW_DATA_DIR");
        assert!(matches!(
            resolve_phase2_governance_dir(),
            Err(Phase2SealError::EphemeralDataDir)
        ));
        assert!(!phase2_immutable_pass_artifact_present());

        std::env::set_var("OPENCLAW_DATA_DIR", "/tmp/openclaw_p2_f3_test");
        assert!(matches!(
            resolve_phase2_governance_dir(),
            Err(Phase2SealError::EphemeralDataDir)
        ));
        assert!(!phase2_immutable_pass_artifact_present());

        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }

    // --- A-model: expiry 過期 → 拒 ---
    #[test]
    fn a_model_expired_approval_invalid() {
        let sha = fake_sha();
        let mut a = direct_approval(FIXED_NOW, &sha);
        a.expires_at_ms = FIXED_NOW - 1;
        assert!(!approval_is_valid(&a, FIXED_NOW, &sha));
    }

    // --- A-model: source_commit 不匹配（replay）→ 拒 ---
    #[test]
    fn a_model_replay_commit_mismatch_invalid() {
        let a = direct_approval(FIXED_NOW, &"a".repeat(40));
        assert!(!approval_is_valid(&a, FIXED_NOW, &"b".repeat(40)));
    }

    // --- A-model: amd 非 07-08-01（誤用 shape-AMD）→ 拒 ---
    #[test]
    fn a_model_wrong_amd_invalid() {
        let sha = fake_sha();
        let mut a = direct_approval(FIXED_NOW, &sha);
        a.amd = "AMD-2026-06-29-01".to_string(); // shape-AMD，非 contact-AMD
        assert!(!approval_is_valid(&a, FIXED_NOW, &sha));
    }

    // --- A-model: future-dated（clock 異常）→ 判無效不 fail-open ---
    #[test]
    fn a_model_future_dated_invalid() {
        let sha = fake_sha();
        let mut a = direct_approval(FIXED_NOW, &sha);
        a.issued_at_ms = FIXED_NOW + 10_000; // 未來簽發
        assert!(!approval_is_valid(&a, FIXED_NOW, &sha));
    }

    // --- A-model: approval 檔非 owner-only → load Err ---
    #[test]
    fn a_model_approval_not_owner_only_err() {
        // root 繞過 file permission → 跳過（無 0o644 語義差異）。
        if unsafe { libc::geteuid() } == 0 {
            return;
        }
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_approval(
            &gov,
            "ADR-0048",
            "AMD-2026-07-08-01",
            &["PM", "Operator"],
            &fake_sha(),
            FIXED_NOW - 1000,
            FIXED_NOW + 3_600_000,
        );
        fs::set_permissions(
            &gov.join(APPROVAL_FILENAME),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        assert!(load_phase2_seal_approval_from_dir(&gov).is_err());
    }

    // --- A-model: approval 檔是 symlink → load Err ---
    #[test]
    fn a_model_approval_symlink_err() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let real = tmp.path().join("real_approval.toml");
        fs::write(&real, "adr = \"ADR-0048\"\n").unwrap();
        fs::set_permissions(&real, fs::Permissions::from_mode(0o600)).unwrap();
        std::os::unix::fs::symlink(&real, gov.join(APPROVAL_FILENAME)).unwrap();
        assert!(load_phase2_seal_approval_from_dir(&gov).is_err());
    }

    // --- T1: approval lineage hash 決定性 + roles 序無關 + 內容敏感 ---
    #[test]
    fn approval_lineage_hash_is_deterministic_and_role_order_independent() {
        let sha = fake_sha();
        let a1 = direct_approval(FIXED_NOW, &sha);
        // roles 反序：sort 後 canonical 相同 → hash 必相同。
        let mut a2 = a1.clone();
        a2.reviewer_roles = vec!["Operator".to_string(), "PM".to_string()];
        assert_eq!(
            compute_approval_lineage_hash(&a1),
            compute_approval_lineage_hash(&a2),
            "roles 排序後 lineage hash 必與元素順序無關"
        );
        // 內容變動（issued_at_ms）→ hash 必變（tamper-sensitive）。
        let mut a3 = a1.clone();
        a3.issued_at_ms += 1;
        assert_ne!(
            compute_approval_lineage_hash(&a1),
            compute_approval_lineage_hash(&a3)
        );
        assert!(openclaw_types::is_sha256_hex(
            &compute_approval_lineage_hash(&a1)
        ));
    }

    // --- 補: verify_sealed_artifact 抓磁碟竄改（parse 後欄位不符）---
    #[test]
    fn verify_sealed_detects_ondisk_tamper() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        assert!(verify_sealed_artifact_for_build(&artifact, &fake_sha()));

        // 竄改磁碟檔（先放寬 0o400 → 改 source_commit → 回寫）。
        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o600)).unwrap();
        let mut on_disk: IbkrPhase2GateArtifactV1 =
            serde_json::from_str(&fs::read_to_string(&sealed).unwrap()).unwrap();
        on_disk.source_commit = "tampered".to_string();
        fs::write(&sealed, serde_json::to_string_pretty(&on_disk).unwrap()).unwrap();

        assert!(
            !verify_sealed_artifact_for_build(&artifact, &fake_sha()),
            "on-disk tamper must fail re-verify"
        );
        assert!(!reverify_sealed_artifact_at_for_build(&sealed, &fake_sha()));
    }

    // --- 補: summary 形狀（現狀 blocked + immutable_pass=false）---
    #[test]
    fn summary_reports_blocked_shape() {
        let _g = crate::test_env_lock::guard();
        let prev = std::env::var("OPENCLAW_DATA_DIR").ok();
        std::env::remove_var("OPENCLAW_DATA_DIR");

        let s = phase2_gate_producer_summary();
        assert_eq!(s["producer_status"], "blocked");
        assert_eq!(s["immutable_pass_artifact_present"], false);
        assert_eq!(s["ibkr_call_performed"], false);
        assert_eq!(s["contact_authorization_amd"], IBKR_PHASE2_CONTACT_AMD);
        assert_eq!(s["artifact_shape_amd"], IBKR_PHASE2_AMD);
        assert!(s["blockers"].as_array().is_some());
        // T2：production placeholder topology（"c"*64）≠ denied-secret fp（空）→
        // triangulation mismatch，佐證覆寫移除後真 equality 生效（自然正確 BLOCKED）。
        assert_eq!(
            s["leg_status"]["account_fingerprint_triangulation_ok"],
            false
        );

        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }
}
