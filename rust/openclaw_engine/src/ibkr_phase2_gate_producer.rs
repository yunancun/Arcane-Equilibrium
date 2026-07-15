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
//!   - **production 批准模型（W2，6 綁定，缺一即 fail-closed 零寫）**：現行
//!     production 批准=`Phase2SealControlApprovalV1`（經
//!     `phase2_control_approval_is_valid`；綁 `authorization_amd ==
//!     AMD-2026-07-11-01`、`contract_id == ibkr_phase2_seal_control_v1`、
//!     `approved_source_commit == BUILD_GIT_SHA`、PM+Operator 雙角色、時窗
//!     ≤30 天）。ADR-0048 / shape-AMD（06-29-01）/ contact-AMD（07-08-01）三
//!     綁定下沉到 artifact 層，由 `IbkrPhase2GateArtifactV1::validate()` 硬 pin
//!     強制；`approval_lineage_hash` = `control_approval_digest`（canonical 固定
//!     key 序 + roles 排序）。舊 A-model（07-08-01 TOML 批准，`approval_is_valid`
//!     + `load_phase2_seal_approval_from_dir`）**僅存於 `#[cfg(test)]` 供歷史
//!     對照**，不再是 production 路徑。
//!   - **write-once**：`create_new` 唯一 tmp → `sync_all` → `hard_link(tmp,final)`
//!     （final 已存在 = 拒二次 seal，絕不 rename overwrite）→ 0o400 → fsync 父目錄。
//!
//! W2（AMD-2026-07-11-01）把原 report-only 的 gap 替換為 Rust-only controlled
//! seal control：預設 dry-run；只有 standalone bin 的 `--apply` **以及** literal
//! `OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1` 才可 append immutable generation/control
//! records。這仍不是 activation、不是 broker contact，G4 與後續 Rust activation
//! envelope 仍是獨立硬閘。production path 從不把 fixture/template 當作 seal input。

use std::collections::{BTreeMap, BTreeSet};
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
#[cfg(test)]
const PHASE2_ARTIFACT_ID: &str = "phase2_ibkr_external_surface_gate_v1";

/// sealed artifact 磁碟檔名（write-once，0o400）。
#[cfg(test)]
const SEALED_FILENAME: &str = "phase2_ibkr_external_surface_gate_v1.sealed.json";

/// W2 production input/control filenames.  They are provisioned owner-only by
/// the operator/runtime; source templates and accepted fixtures are never read
/// through these names.
const CONTROL_INPUTS_FILENAME: &str = "phase2_seal_inputs.json";
const CONTROL_APPROVAL_FILENAME: &str = "phase2_seal_control_approval.json";
const GENERATIONS_DIRNAME: &str = "generations";
const CONTROLS_DIRNAME: &str = "controls";
const W2_CONTROL_AMD: &str = "AMD-2026-07-11-01";
const W2_CONTROL_CONTRACT_ID: &str = "ibkr_phase2_seal_control_v1";
const W2_INPUTS_CONTRACT_ID: &str = "ibkr_phase2_seal_inputs_v1";

/// approval A-model 來源檔名（owner-only 0o600 TOML）。
#[cfg(test)]
const APPROVAL_FILENAME: &str = "phase2_seal_approval.toml";

/// 政策 bundle 來源檔名（settings/broker）。
#[cfg(test)]
const POLICIES_FILENAME: &str = "ibkr_phase2_policies.toml";

/// approval issue→now 上界（bounded freshness，30 天）；超齡即視為過期（fail-closed）。
const MAX_APPROVAL_AGE_MS: u64 = 30 * 24 * 60 * 60 * 1000;

const REASON_SOURCE_COMMIT_UNKNOWN: &str = "source_commit_unknown";

/// 易失路徑前綴（refuse-ephemeral）。跨平台涵蓋 Linux `/tmp`、Mac `/private/tmp`
/// 與 `/var/folders`（tempfile），以及 `/dev/shm`。
/// E3-F1:`/run` 族(systemd tmpfs;含 `/run/user/<uid>` 與傳統 `/var/run`
/// symlink、Mac `/private/var/run`)同為 reboot 即蒸發的易失盤,治理證據一律拒寫。
const EPHEMERAL_PREFIXES: &[&str] = &[
    "/tmp",
    "/private/tmp",
    "/var/tmp",
    "/private/var/tmp",
    "/var/folders",
    "/private/var/folders",
    "/dev/shm",
    "/run",
    "/var/run",
    "/private/var/run",
];

// ---------------------------------------------------------------------------
// approval A-model
// ---------------------------------------------------------------------------

/// Phase 2 seal approval（TOML deser）。producer 絕不自注 "Operator"——僅在本結構
/// 通過 `approval_is_valid` 的 6 綁定後，才把其 `reviewer_roles` 綁進 artifact。
#[cfg(test)]
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
#[cfg(test)]
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

/// source_commit 必須是可被 current-build ledger 目錄表達的真世代：精確的
/// 40-hex git SHA。只拒 `unknown` 仍會讓 apply 寫入 reader 永遠無法枚舉的
/// generation 目錄，因而產生 applied-but-unconsumable 的假成功。
fn source_commit_is_known(sha: &str) -> bool {
    sha.len() == 40 && sha.bytes().all(|byte| byte.is_ascii_hexdigit())
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
#[cfg(test)]
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
#[cfg(test)]
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
#[derive(Clone, Copy, PartialEq, Eq)]
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
fn read_owner_only_named_child_after_lstat<F>(
    parent: &std::fs::File,
    child_name: &str,
    expected_euid: u32,
    after_lstat: F,
) -> Option<String>
where
    F: FnOnce(),
{
    use std::io::Read;
    use std::os::unix::io::{AsRawFd, FromRawFd};

    let sealed_name = std::ffi::CString::new(child_name).ok()?;
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

/// Dynamic-name version of the W1 secure consumer primitive.  W2 uses this
/// only after strict generated-file-name validation; `openat` remains
/// nonblocking/no-follow and binds the post-open inode to the pre-open lstat.
#[cfg(unix)]
fn read_owner_only_named_child(
    parent: &std::fs::File,
    child_name: &str,
    expected_euid: u32,
) -> Option<String> {
    read_owner_only_named_child_after_lstat(parent, child_name, expected_euid, || {})
}

#[cfg(unix)]
#[cfg(test)]
fn read_owner_only_sealed_child_after_lstat<F>(
    parent: &std::fs::File,
    expected_euid: u32,
    after_lstat: F,
) -> Option<String>
where
    F: FnOnce(),
{
    read_owner_only_named_child_after_lstat(parent, SEALED_FILENAME, expected_euid, after_lstat)
}

/// Production wrapper keeps the final-file race hook inert. The generic helper above is also
/// used by the Unix-only test to inject a FIFO replacement exactly after `fstatat`.
#[cfg(unix)]
#[cfg(test)]
fn read_owner_only_sealed_child(parent: &std::fs::File, expected_euid: u32) -> Option<String> {
    read_owner_only_named_child(parent, SEALED_FILENAME, expected_euid)
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
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
fn parse_sealed_artifact_from_secure_fd(path: &Path) -> Option<IbkrPhase2GateArtifactV1> {
    let raw = read_sealed_artifact_from_secure_tree(path)?;
    serde_json::from_str(&raw).ok()
}

#[cfg(not(unix))]
#[cfg(test)]
fn parse_sealed_artifact_from_secure_fd(path: &Path) -> Option<IbkrPhase2GateArtifactV1> {
    let _ = path;
    None
}

/// post-seal 磁碟 re-verify（design 命名）：secure-FD consume、build-generation 綁定、
/// 與傳入 artifact 全等（含 path 欄位）、hash 自洽、且 `validate()` 放行。
#[cfg(test)]
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
#[cfg(test)]
fn verify_sealed_artifact(artifact: &IbkrPhase2GateArtifactV1) -> bool {
    verify_sealed_artifact_for_build(artifact, BUILD_GIT_SHA)
}

/// precontact / summary 用的磁碟 re-verify（path-first，含 anti-relocation、
/// secure-FD consume、以及 expected build generation 綁定）。
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
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
    // E3-F2:相對路徑一律拒。治理目錄依 cwd 解析=同一 env 在不同進程/工作目錄
    // 指向不同帳本(不可再現、可被 cwd 操縱繞過 ephemeral 前綴比對),與
    // refuse-ephemeral 同屬「治理證據落點不可信」→ 沿用同一 typed reason。
    if !data_dir.is_absolute() {
        return Err(Phase2SealError::EphemeralDataDir);
    }
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
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
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
#[cfg(test)]
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
// W2 controlled no-contact seal/supersession ledger
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// W2 controlled no-contact seal/supersession ledger
// ---------------------------------------------------------------------------

/// A provisioned, no-credential input bundle.  It is intentionally a concrete
/// JSON value rather than a source template: all legs must be independently
/// supplied by the owner-only runtime directory, or the evaluation remains
/// `external_verification_pending` and writes nothing.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Phase2SealProductionInputsV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub policy_bundle: IbkrPhase2PolicyBundleV1,
    pub api_allowlist: NonBybitApiAllowlistV1,
    pub secret_slot_contract: IbkrSecretSlotContractV1,
    pub api_session_topology: IbkrApiSessionTopologyV1,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase2SealControlAction {
    Seal,
    Supersede,
    Revoke,
}

/// An operator-provisioned control approval.  It authorizes only the local,
/// no-contact artifact control action; it is never an activation envelope and
/// contains no session, account ID, or credential material.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Phase2SealControlApprovalV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub approval_id: String,
    pub action: Phase2SealControlAction,
    pub authorization_amd: String,
    pub reviewer_roles: Vec<String>,
    pub approved_source_commit: String,
    pub issued_at_ms: u64,
    pub expires_at_ms: u64,
    pub predecessor_artifact_id: Option<String>,
    pub predecessor_raw_hash: Option<String>,
}

/// Each generation owns both the typed gate artifact and the approval expiry
/// that bounds it.  This wrapper is immutable and is sealed as one 0400 file.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Phase2SealedGenerationV1 {
    contract_id: String,
    source_version: u32,
    generation_id: String,
    approval_id: String,
    approval_digest: String,
    valid_until_ms: u64,
    artifact: IbkrPhase2GateArtifactV1,
    generation_hash: String,
}

/// Append-only action record.  There is deliberately no mutable `current`
/// file: consumers derive the one active leaf from this hash chain.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Phase2SealControlRecordV1 {
    contract_id: String,
    source_version: u32,
    control_id: String,
    action: Phase2SealControlAction,
    approval_id: String,
    approval_digest: String,
    source_commit: String,
    recorded_at_ms: u64,
    valid_until_ms: u64,
    target_artifact_id: String,
    target_raw_hash: String,
    predecessor_artifact_id: Option<String>,
    predecessor_raw_hash: Option<String>,
    previous_control_hash: Option<String>,
    control_hash: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Phase2SealEvaluation {
    pub status: String,
    pub blockers: Vec<String>,
    pub inputs_present: bool,
    pub inputs_valid: bool,
    pub approval_present: bool,
    pub approval_valid: bool,
    /// E2-F1:active 世代存在**且未過期**才 true(authority 真值)。
    pub active_current_build: bool,
    /// E2-F1:active 世代存在但已過期(expired_needs_supersede 態)——gate 非
    /// authoritative,operator 需以 Supersede 續期(或 Revoke 終結)。
    pub active_expired_needs_supersede: bool,
    pub no_contact: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Phase2SealApplyOutcome {
    pub status: String,
    pub blockers: Vec<String>,
    pub action: Option<Phase2SealControlAction>,
    pub no_contact: bool,
    pub wrote_generation: bool,
    pub wrote_control: bool,
}

#[derive(Debug, Clone)]
struct Phase2LineageState {
    /// replay 得出的 active 世代(**不含 expiry 判定**)。supersede/revoke 的
    /// predecessor 綁定必須以它為準——即使已過期,續期(Supersede)仍需要它。
    active: Option<Phase2SealedGenerationV1>,
    /// E2-F1:consume 側唯一 authority 真值——active 存在**且未過期**才 true。
    /// 過期的 active 世代 → false(gate 非 authoritative,fail-closed),但
    /// `active` 仍保留以維持帳本可操作性(expired_needs_supersede 態)。
    active_authoritative: bool,
    tail_hash: Option<String>,
    approval_ids: BTreeSet<String>,
    approval_digests: BTreeSet<String>,
}

/// A successful immutable publication can either create a record or discover
/// the byte-identical record left behind by an interrupted prior attempt.  The
/// latter is deliberately *not* an error: callers must be able to complete the
/// missing sibling record without minting a fork.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ImmutablePublication {
    Written,
    AlreadyPresent,
}

/// The lock file is coordination only, never an authority record and never a
/// consumer input.  `flock` is tied to this fd/open-file-description, so a
/// crash releases it automatically.  The immutable generation/control ledger
/// remains the sole active-authority input.
#[cfg(unix)]
struct Phase2ApplyLock {
    file: std::fs::File,
    /// The `governance/` dirfd which owns the `ibkr_phase2` pathname.  Holding
    /// this flock prevents a replacement `ibkr_phase2` directory from gaining
    /// a second writer while the original critical section is still alive.
    governance: std::fs::File,
    parent: std::fs::File,
    governance_inode: SecureInode,
    parent_inode: SecureInode,
    inode: SecureInode,
}

#[cfg(unix)]
impl Phase2ApplyLock {
    const FILENAME: &'static str = ".phase2_seal_apply.lock";

    fn acquire(gov_dir: &Path) -> Result<Self, String> {
        Self::acquire_inner(gov_dir, false)
    }

    #[cfg(test)]
    fn try_acquire(gov_dir: &Path) -> Result<Self, String> {
        Self::acquire_inner(gov_dir, true)
    }

    fn acquire_inner(gov_dir: &Path, nonblocking: bool) -> Result<Self, String> {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        use std::os::unix::io::{AsRawFd, FromRawFd};

        let euid = unsafe { libc::geteuid() } as u32;
        // Bind the directory chain first; path text is never used to reopen
        // a ledger child after this point.  Keep both the `governance/` and
        // `ibkr_phase2/` dirfds: the former serializes an attempted whole
        // `ibkr_phase2` directory replacement, while the latter is the only
        // parent used for ledger I/O during this apply.
        let (governance, parent) = open_secure_phase2_parent_and_child(gov_dir)
            .ok_or_else(|| "secure phase2 apply-lock directory unavailable".to_string())?;
        let governance_metadata = governance
            .metadata()
            .map_err(|error| format!("secure phase2 governance stat failed: {error}"))?;
        let parent_metadata = parent
            .metadata()
            .map_err(|error| format!("secure phase2 apply-lock parent stat failed: {error}"))?;
        if !owner_only_dir_metadata_is_secure(&governance_metadata, euid)
            || !owner_only_dir_metadata_is_secure(&parent_metadata, euid)
        {
            return Err("secure phase2 apply-lock directory is not owner-only 0700".to_string());
        }
        let governance_inode = inode_from_metadata(&governance_metadata);
        let parent_inode = inode_from_metadata(&parent_metadata);
        // The child lock alone cannot serialize a compliant sibling writer if
        // its pathname is unlinked and replaced after the first flock: the
        // sibling could otherwise lock that new inode.  Lock the inode-bound
        // parent directory for the whole critical section as well, so every
        // Phase2ApplyLock user remains serialized across a rejected swap.
        let mut operation = libc::LOCK_EX;
        if nonblocking {
            operation |= libc::LOCK_NB;
        }
        loop {
            let result = unsafe { libc::flock(governance.as_raw_fd(), operation) };
            if result == 0 {
                break;
            }
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(format!(
                "secure phase2 apply-lock governance directory acquire failed: {error}"
            ));
        }
        loop {
            let result = unsafe { libc::flock(parent.as_raw_fd(), operation) };
            if result == 0 {
                break;
            }
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(format!(
                "secure phase2 apply-lock directory acquire failed: {error}"
            ));
        }
        let name = std::ffi::CString::new(Self::FILENAME)
            .map_err(|_| "invalid phase2 apply-lock filename".to_string())?;
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDWR | libc::O_CREAT | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd < 0 {
            return Err(format!(
                "secure phase2 apply-lock open failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        let file = unsafe { std::fs::File::from_raw_fd(fd) };
        let metadata = file
            .metadata()
            .map_err(|error| format!("secure phase2 apply-lock stat failed: {error}"))?;
        if !metadata.is_file()
            || metadata.uid() as u32 != euid
            || !owner_only_mode_is_exact(metadata.permissions().mode(), 0o600)
        {
            return Err("secure phase2 apply-lock is not owner-only regular 0600".to_string());
        }
        // Bind the opened fd to its current directory entry.  This catches a
        // replacement that races creation/open before the child flock begins.
        let inode = lstatat_owner_only_inode(
            parent.as_raw_fd(),
            name.as_c_str(),
            euid,
            libc::S_IFREG as u32,
            0o600,
        )
        .ok_or_else(|| "secure phase2 apply-lock is not owner-only regular 0600".to_string())?;
        if !metadata_matches_inode(&metadata, inode) {
            return Err("secure phase2 apply-lock changed during open".to_string());
        }
        loop {
            let result = unsafe { libc::flock(file.as_raw_fd(), operation) };
            if result == 0 {
                break;
            }
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(format!("secure phase2 apply-lock acquire failed: {error}"));
        }
        let lock = Self {
            file,
            governance,
            parent,
            governance_inode,
            parent_inode,
            inode,
        };
        // No caller may enter the ledger critical section after an unlink or
        // pathname redirect to a different lock inode.
        lock.ensure_bound()?;
        Ok(lock)
    }

    /// Verify that the lock pathname still resolves through the original
    /// parent dirfd to the exact inode held by this critical section.  The
    /// apply path calls this at each immutable publication boundary.
    fn ensure_bound(&self) -> Result<(), String> {
        use std::os::unix::io::AsRawFd;

        let euid = unsafe { libc::geteuid() } as u32;
        let name = std::ffi::CString::new(Self::FILENAME)
            .map_err(|_| "invalid phase2 apply-lock filename".to_string())?;
        let fd_metadata = self
            .file
            .metadata()
            .map_err(|error| format!("secure phase2 apply-lock fd stat failed: {error}"))?;
        let governance_metadata = self
            .governance
            .metadata()
            .map_err(|error| format!("secure phase2 governance fd stat failed: {error}"))?;
        let parent_metadata = self
            .parent
            .metadata()
            .map_err(|error| format!("secure phase2 apply-lock parent fd stat failed: {error}"))?;
        let phase2_name = std::ffi::CString::new("ibkr_phase2")
            .map_err(|_| "invalid phase2 directory name".to_string())?;
        if !owner_only_dir_metadata_is_secure(&governance_metadata, euid)
            || !metadata_matches_inode(&governance_metadata, self.governance_inode)
            || !owner_only_dir_metadata_is_secure(&parent_metadata, euid)
            || !metadata_matches_inode(&parent_metadata, self.parent_inode)
            || lstatat_owner_only_inode(
                self.governance.as_raw_fd(),
                phase2_name.as_c_str(),
                euid,
                libc::S_IFDIR as u32,
                0o700,
            ) != Some(self.parent_inode)
            || !fd_metadata.is_file()
            || !metadata_matches_inode(&fd_metadata, self.inode)
            || lstatat_owner_only_inode(
                self.parent.as_raw_fd(),
                name.as_c_str(),
                euid,
                libc::S_IFREG as u32,
                0o600,
            ) != Some(self.inode)
        {
            return Err(
                "secure phase2 apply-lock or bound directory was unlinked or replaced".to_string(),
            );
        }
        Ok(())
    }
}

#[cfg(unix)]
impl Drop for Phase2ApplyLock {
    fn drop(&mut self) {
        use std::os::unix::io::AsRawFd;

        // Closing the fd also releases flock; this explicit unlock only makes
        // the hand-off point obvious and never influences ledger authority.
        unsafe {
            libc::flock(self.file.as_raw_fd(), libc::LOCK_UN);
            libc::flock(self.parent.as_raw_fd(), libc::LOCK_UN);
            libc::flock(self.governance.as_raw_fd(), libc::LOCK_UN);
        }
    }
}

#[cfg(not(unix))]
struct Phase2ApplyLock;

#[cfg(not(unix))]
impl Phase2ApplyLock {
    fn acquire(_gov_dir: &Path) -> Result<Self, String> {
        Err("phase2 apply lock unsupported on non-unix".to_string())
    }
}

fn control_approval_digest(approval: &Phase2SealControlApprovalV1) -> String {
    let mut roles = approval.reviewer_roles.clone();
    roles.sort();
    let canonical = serde_json::json!({
        "contract_id": approval.contract_id,
        "source_version": approval.source_version,
        "approval_id": approval.approval_id,
        "action": approval.action,
        "authorization_amd": approval.authorization_amd,
        "reviewer_roles": roles,
        "approved_source_commit": approval.approved_source_commit,
        "issued_at_ms": approval.issued_at_ms,
        "expires_at_ms": approval.expires_at_ms,
        "predecessor_artifact_id": approval.predecessor_artifact_id,
        "predecessor_raw_hash": approval.predecessor_raw_hash,
    });
    sha256_hex(
        serde_json::to_string(&canonical)
            .unwrap_or_default()
            .as_bytes(),
    )
}

fn phase2_control_approval_is_valid(
    approval: &Phase2SealControlApprovalV1,
    now: u64,
    expected_build_sha: &str,
) -> bool {
    approval.contract_id == W2_CONTROL_CONTRACT_ID
        && approval.source_version == 1
        && openclaw_types::is_sha256_hex(&approval.approval_id)
        && approval.authorization_amd == W2_CONTROL_AMD
        && source_commit_is_known(expected_build_sha)
        && approval.approved_source_commit == expected_build_sha
        && approval.reviewer_roles.iter().any(|r| r == "PM")
        && approval.reviewer_roles.iter().any(|r| r == "Operator")
        && approval.issued_at_ms > 0
        && approval.issued_at_ms <= now
        && approval.expires_at_ms > now
        && approval.expires_at_ms > approval.issued_at_ms
        && now.saturating_sub(approval.issued_at_ms) <= MAX_APPROVAL_AGE_MS
        && approval
            .predecessor_artifact_id
            .as_deref()
            .map(openclaw_types::is_sha256_hex)
            .unwrap_or(matches!(approval.action, Phase2SealControlAction::Seal))
        && approval
            .predecessor_raw_hash
            .as_deref()
            .map(openclaw_types::is_sha256_hex)
            .unwrap_or(matches!(approval.action, Phase2SealControlAction::Seal))
}

/// E2-F3 anti-placeholder:repo template 的 placeholder 指紋形態=**全同字元
/// 64-hex**。出典:`rust/openclaw_types/src/ibkr_phase2_runtime.rs` 之
/// `source_template()`——secret_slot_fingerprint="a"*64、secret account
/// fp="b"*64、topology account fp="c"*64;
/// `settings/broker/ibkr_phase2_gate_artifact.template.toml` 的對應欄為空字串
/// (空串已被 `validate()` 的 is_sha256_hex 拒,無需在此重複)。真 sha256
/// 出現全同字元的機率可忽略,此形態即「template 原樣抄進 runtime 目錄」的
/// 指紋,production seal inputs 必拒。
fn fingerprint_is_template_placeholder(value: &str) -> bool {
    value.len() == 64
        && value
            .as_bytes()
            .first()
            .is_some_and(|first| value.bytes().all(|byte| byte == *first))
}

fn production_inputs_are_valid(inputs: &Phase2SealProductionInputsV1) -> bool {
    inputs.contract_id == W2_INPUTS_CONTRACT_ID
        && inputs.source_version == 1
        && inputs.policy_bundle.validate().accepted
        && inputs.api_allowlist.validate().accepted
        && inputs.secret_slot_contract.validate().accepted
        && inputs.api_session_topology.validate().accepted
        && inputs.secret_slot_contract.account_fingerprint_hash
            == inputs.api_session_topology.account_fingerprint_hash
        // E2-F3:template placeholder 指紋(全同字元 64-hex)不得進 production
        // seal——它們是 shape 樣板,不對應任何真實 slot/topology 指紋。
        && !fingerprint_is_template_placeholder(&inputs.secret_slot_contract.secret_slot_fingerprint)
        && !fingerprint_is_template_placeholder(
            &inputs.secret_slot_contract.account_fingerprint_hash,
        )
        && !fingerprint_is_template_placeholder(
            &inputs.api_session_topology.account_fingerprint_hash,
        )
}

/// generation_hash = sha256(清空自身 hash 欄後的整結構 serde JSON)。
///
/// **欄位序 load-bearing(E3-F4/E2-F4)**:此 canonical 形態直接取
/// `Phase2SealedGenerationV1` 的 struct 宣告欄位序(serde 按宣告序序列化)。
/// 重排/增刪任何欄位=改變 hash 前像 → 既有 0400 帳本全部驗證失敗(等同人為
/// brick)。任何 shape 變更必須走新 source_version/新 contract,絕不可原地重排。
fn generation_hash(generation: &Phase2SealedGenerationV1) -> String {
    let mut canonical = generation.clone();
    canonical.generation_hash.clear();
    sha256_hex(
        serde_json::to_string(&canonical)
            .unwrap_or_default()
            .as_bytes(),
    )
}

fn control_id(record: &Phase2SealControlRecordV1) -> String {
    let canonical = serde_json::json!({
        "action": record.action,
        "approval_id": record.approval_id,
        "approval_digest": record.approval_digest,
        "source_commit": record.source_commit,
        "target_artifact_id": record.target_artifact_id,
        "target_raw_hash": record.target_raw_hash,
        "predecessor_artifact_id": record.predecessor_artifact_id,
        "predecessor_raw_hash": record.predecessor_raw_hash,
        "previous_control_hash": record.previous_control_hash,
    });
    sha256_hex(
        serde_json::to_string(&canonical)
            .unwrap_or_default()
            .as_bytes(),
    )
}

/// control_hash = sha256(清空自身 hash 欄後的整結構 serde JSON)。
///
/// **欄位序 load-bearing(E3-F4/E2-F4)**:canonical 形態=
/// `Phase2SealControlRecordV1` 的 struct 宣告欄位序。重排/增刪欄位即改變
/// hash 前像 → 既有 control 鏈(含 previous_control_hash 鏈接)全部失效。
/// shape 變更必須走新 source_version/新 contract,絕不可原地重排。
fn control_hash(record: &Phase2SealControlRecordV1) -> String {
    let mut canonical = record.clone();
    canonical.control_hash.clear();
    sha256_hex(
        serde_json::to_string(&canonical)
            .unwrap_or_default()
            .as_bytes(),
    )
}

#[cfg(unix)]
fn data_root_from_phase2_governance_dir(gov_dir: &Path) -> Option<&Path> {
    let governance = gov_dir.parent()?;
    let data_root = governance.parent()?;
    if gov_dir.file_name()?.to_str()? != "ibkr_phase2"
        || governance.file_name()?.to_str()? != "governance"
        || data_root.as_os_str().is_empty()
    {
        return None;
    }
    Some(data_root)
}

/// Open the existing W1 data-root -> governance -> ibkr_phase2 chain entirely
/// by inode-bound dirfds.  The pair form is used by `Phase2ApplyLock`: keeping
/// the governance parent FD lets it reject and serialize a full `ibkr_phase2`
/// pathname replacement rather than only a lock-file replacement.
#[cfg(unix)]
fn open_secure_phase2_parent_and_child(gov_dir: &Path) -> Option<(std::fs::File, std::fs::File)> {
    let expected_euid = unsafe { libc::geteuid() } as u32;
    let data_root = data_root_from_phase2_governance_dir(gov_dir)?;
    let root_fd = open_owner_only_data_root_after_lstat(data_root, || {})?;
    let governance_fd = open_owner_only_child_dir(&root_fd, "governance", expected_euid)?;
    let phase2_fd = open_owner_only_child_dir(&governance_fd, "ibkr_phase2", expected_euid)?;
    Some((governance_fd, phase2_fd))
}

/// Single-dirfd convenience form for read-only callers.  Apply owns the pair
/// through `Phase2ApplyLock` and never reopens this path after acquisition.
#[cfg(unix)]
fn open_secure_phase2_dir(gov_dir: &Path) -> Option<std::fs::File> {
    open_secure_phase2_parent_and_child(gov_dir).map(|(_, phase2_fd)| phase2_fd)
}

#[cfg(unix)]
fn secure_phase2_file_read(gov_dir: &Path, filename: &str) -> Option<String> {
    if filename.is_empty() || filename.contains('/') || filename.contains('\0') {
        return None;
    }
    let expected_euid = unsafe { libc::geteuid() } as u32;
    let phase2_fd = open_secure_phase2_dir(gov_dir)?;
    read_owner_only_named_child(&phase2_fd, filename, expected_euid)
}

#[cfg(not(unix))]
fn secure_phase2_file_read(_gov_dir: &Path, _filename: &str) -> Option<String> {
    None
}

fn load_control_inputs_from_dir(
    gov_dir: &Path,
) -> Result<Option<Phase2SealProductionInputsV1>, String> {
    let raw = match secure_phase2_file_read(gov_dir, CONTROL_INPUTS_FILENAME) {
        Some(value) => value,
        None => return Ok(None),
    };
    serde_json::from_str(&raw)
        .map(Some)
        .map_err(|e| format!("invalid controlled phase2 inputs: {e}"))
}

fn load_control_approval_from_dir(
    gov_dir: &Path,
) -> Result<Option<Phase2SealControlApprovalV1>, String> {
    let raw = match secure_phase2_file_read(gov_dir, CONTROL_APPROVAL_FILENAME) {
        Some(value) => value,
        None => return Ok(None),
    };
    serde_json::from_str(&raw)
        .map(Some)
        .map_err(|e| format!("invalid controlled phase2 approval: {e}"))
}

/// E3-F3:清 errno。`readdir(3)` 以回傳 NULL 同時表示「枚舉完成」與「讀取
/// 錯誤」,唯一區分手段是 errno;呼叫前不清零,殘留的舊 errno 會令錯誤判定
/// 不可靠。部署目標僅 Linux/Apple Silicon,兩系皆有對應 thread-local 入口。
#[cfg(unix)]
fn clear_errno() {
    #[cfg(any(target_os = "macos", target_os = "ios"))]
    unsafe {
        *libc::__error() = 0;
    }
    #[cfg(any(target_os = "linux", target_os = "android"))]
    unsafe {
        *libc::__errno_location() = 0;
    }
}

/// 安全列舉 dirfd 下的 entry 名。**fail-closed 語義(E3-F3)**:`readdir` 回
/// NULL 且 errno≠0(如 EBADF/EIO)代表列舉「中途失敗」而非「正常讀完」——
/// 此時回 `None`,絕不把部分列舉當成完整 ledger 快照(部分快照會令 lineage
/// 驗證在缺頁的記錄集上誤判)。每次 `readdir` 前先清 errno,避免前一 libc
/// 呼叫殘留的 errno 造成誤報/漏報。
#[cfg(unix)]
fn secure_dir_entry_names(dir: &std::fs::File) -> Option<Vec<String>> {
    use std::os::unix::io::AsRawFd;

    let duplicate = unsafe { libc::dup(dir.as_raw_fd()) };
    if duplicate < 0 {
        return None;
    }
    let raw_dir = unsafe { libc::fdopendir(duplicate) };
    if raw_dir.is_null() {
        unsafe { libc::close(duplicate) };
        return None;
    }
    let mut names = Vec::new();
    let mut invalid_name = false;
    let mut read_failed = false;
    loop {
        clear_errno();
        let entry = unsafe { libc::readdir(raw_dir) };
        if entry.is_null() {
            // NULL + errno≠0 = 讀取錯誤,非正常終止 → fail-closed。
            read_failed = std::io::Error::last_os_error().raw_os_error().unwrap_or(0) != 0;
            break;
        }
        let name = match unsafe { std::ffi::CStr::from_ptr((*entry).d_name.as_ptr()) }.to_str() {
            Ok(value) => value.to_string(),
            Err(_) => {
                invalid_name = true;
                break;
            }
        };
        if name != "." && name != ".." {
            names.push(name);
        }
    }
    unsafe { libc::closedir(raw_dir) };
    if invalid_name || read_failed {
        return None;
    }
    names.sort();
    Some(names)
}

/// Open one current-build ledger leaf from an already inode-bound Phase2
/// directory.  Callers which must compose multiple ledger surfaces (the
/// generation and control chains) retain the same `phase2_fd` for every
/// branch, rather than re-resolving the path tree per branch.
#[cfg(unix)]
fn secure_open_current_build_dir_from_phase2(
    phase2_fd: &std::fs::File,
    top_level: &str,
    expected_build_sha: &str,
) -> Option<std::fs::File> {
    if expected_build_sha.len() != 40 || !expected_build_sha.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return None;
    }
    let expected_euid = unsafe { libc::geteuid() } as u32;
    let top_fd = open_owner_only_child_dir(phase2_fd, top_level, expected_euid)?;
    open_owner_only_child_dir(&top_fd, expected_build_sha, expected_euid)
}

#[cfg(unix)]
fn generation_filename_is_valid(name: &str) -> bool {
    name.strip_suffix(".sealed.json")
        .map(openclaw_types::is_sha256_hex)
        .unwrap_or(false)
}

#[cfg(unix)]
fn control_filename_is_valid(name: &str) -> bool {
    name.strip_suffix(".control.json")
        .map(openclaw_types::is_sha256_hex)
        .unwrap_or(false)
}

/// A process can die after creating/syncing its private tmp inode and before
/// publishing it with `link(2)`.  Such an inode is never a ledger record and
/// must not make an otherwise valid immutable lineage unreadable.  We ignore
/// only the writer's exact hidden-name shape and still require it to be an
/// owner-only regular 0400/0600 file; symlinks, special files, and arbitrary
/// names remain fail-closed.
#[cfg(unix)]
fn interrupted_immutable_tmp_name_is_valid(name: &str) -> bool {
    let Some(body) = name
        .strip_prefix('.')
        .and_then(|value| value.strip_suffix(".tmp"))
    else {
        return false;
    };
    let mut components = body.rsplitn(3, '.');
    let nanos = components.next();
    let pid = components.next();
    let record = components.next();
    record.is_some_and(|value| !value.is_empty())
        && pid.is_some_and(|value| {
            !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit())
        })
        && nanos.is_some_and(|value| {
            !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit())
        })
}

#[cfg(unix)]
fn interrupted_immutable_tmp_is_secure(
    parent: &std::fs::File,
    name: &str,
    expected_euid: u32,
) -> bool {
    use std::os::unix::io::AsRawFd;

    let Ok(name) = std::ffi::CString::new(name) else {
        return false;
    };
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::fstatat(
            parent.as_raw_fd(),
            name.as_ptr(),
            &mut stat,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        return false;
    }
    let mode = stat.st_mode as u32;
    (mode & libc::S_IFMT as u32) == libc::S_IFREG as u32
        && stat.st_uid as u32 == expected_euid
        && (owner_only_mode_is_exact(mode, 0o400) || owner_only_mode_is_exact(mode, 0o600))
}

#[cfg(unix)]
#[cfg(test)]
fn read_current_build_records<T: for<'de> Deserialize<'de>>(
    gov_dir: &Path,
    top_level: &str,
    expected_build_sha: &str,
    valid_name: fn(&str) -> bool,
) -> Result<Vec<T>, String> {
    let phase2_fd = match open_secure_phase2_dir(gov_dir) {
        Some(directory) => directory,
        None => return Ok(Vec::new()),
    };
    read_current_build_records_from_phase2(&phase2_fd, top_level, expected_build_sha, valid_name)
}

/// Read one current-build ledger branch from a caller-owned, FD-bound
/// `ibkr_phase2` snapshot.  In particular, `load_current_build_lineage`
/// invokes this twice against the same directory FD so generation and control
/// records cannot be composed from independently reopened trees.
#[cfg(unix)]
fn read_current_build_records_from_phase2<T: for<'de> Deserialize<'de>>(
    phase2_fd: &std::fs::File,
    top_level: &str,
    expected_build_sha: &str,
    valid_name: fn(&str) -> bool,
) -> Result<Vec<T>, String> {
    let directory =
        match secure_open_current_build_dir_from_phase2(phase2_fd, top_level, expected_build_sha) {
            Some(dir) => dir,
            None => return Ok(Vec::new()),
        };
    let euid = unsafe { libc::geteuid() } as u32;
    let names = secure_dir_entry_names(&directory)
        .ok_or_else(|| "secure directory enumeration failed".to_string())?;
    let mut records = Vec::new();
    for name in names {
        if interrupted_immutable_tmp_name_is_valid(&name) {
            if interrupted_immutable_tmp_is_secure(&directory, &name, euid) {
                continue;
            }
            return Err("insecure interrupted immutable temporary record".to_string());
        }
        if !valid_name(&name) {
            return Err("unexpected immutable ledger entry".to_string());
        }
        let raw = read_owner_only_named_child(&directory, &name, euid)
            .ok_or_else(|| "insecure immutable ledger entry".to_string())?;
        records.push(
            serde_json::from_str(&raw)
                .map_err(|e| format!("invalid immutable ledger JSON: {e}"))?,
        );
    }
    Ok(records)
}

#[cfg(not(unix))]
#[cfg(test)]
fn read_current_build_records<T: for<'de> Deserialize<'de>>(
    _gov_dir: &Path,
    _top_level: &str,
    _expected_build_sha: &str,
    _valid_name: fn(&str) -> bool,
) -> Result<Vec<T>, String> {
    Ok(Vec::new())
}

/// 世代記錄的**結構性**驗證(hash 自洽/檔名路徑綁定/artifact 雙綠/triangulation)。
///
/// E2-F1:此處刻意**不做 expiry 檢查**——expiry 只約束「active leaf 的
/// authority 判定」(見 `evaluate_current_build_lineage_records` 末端)。
/// 若對帳本內每個世代(含已被 supersede 的祖先、已 revoke 的世代)套 expiry,
/// 任一祖先過期即整鏈 Err → summary 翻 false 且 seal/supersede/revoke 全被擋
/// → ledger 永久死鎖,打穿 ADR-0048「Re-attestation uses Supersede」。
/// 歷史世代只需結構完整;`valid_until_ms` 僅驗非零(shape),過期與否由
/// replay 完成後對 active 世代單獨判定。
fn sealed_generation_is_valid(
    generation: &Phase2SealedGenerationV1,
    gov_dir: &Path,
    expected_build_sha: &str,
) -> bool {
    generation.contract_id == W2_CONTROL_CONTRACT_ID
        && generation.source_version == 1
        && openclaw_types::is_sha256_hex(&generation.generation_id)
        && openclaw_types::is_sha256_hex(&generation.approval_id)
        && openclaw_types::is_sha256_hex(&generation.approval_digest)
        && generation.valid_until_ms > 0
        && generation.generation_hash == generation_hash(generation)
        && generation.artifact.artifact_id == generation.generation_id
        && generation.artifact.source_commit == expected_build_sha
        && generation.artifact.immutable_storage_path
            == generation_path(gov_dir, expected_build_sha, &generation.generation_id)
                .to_string_lossy()
                .into_owned()
        && generation.artifact.created_at_ms > 0
        && generation.artifact.validate().ibkr_contact_allowed
        && verify_artifact_hashes(&generation.artifact)
        && account_fingerprint_triangulation_ok(&generation.artifact)
}

fn control_record_is_valid(record: &Phase2SealControlRecordV1, expected_build_sha: &str) -> bool {
    record.contract_id == W2_CONTROL_CONTRACT_ID
        && record.source_version == 1
        && openclaw_types::is_sha256_hex(&record.control_id)
        && openclaw_types::is_sha256_hex(&record.approval_id)
        && openclaw_types::is_sha256_hex(&record.approval_digest)
        && openclaw_types::is_sha256_hex(&record.target_artifact_id)
        && openclaw_types::is_sha256_hex(&record.target_raw_hash)
        && record.source_commit == expected_build_sha
        && record.recorded_at_ms > 0
        && record.valid_until_ms > record.recorded_at_ms
        && record.control_id == control_id(record)
        && record.control_hash == control_hash(record)
}

/// Validate the immutable generation/control graph using a single
/// inode-bound `ibkr_phase2` directory snapshot.  The hook exists solely for
/// the deterministic Unix test that swaps the pathname after generation read:
/// controls must still come from this FD's original directory, never from a
/// replacement tree re-opened by path.
#[cfg(unix)]
fn load_current_build_lineage_from_phase2_after_generations<F>(
    phase2_fd: &std::fs::File,
    gov_dir: &Path,
    expected_build_sha: &str,
    now: u64,
    after_generations: F,
) -> Result<Phase2LineageState, String>
where
    F: FnOnce(),
{
    let generations: Vec<Phase2SealedGenerationV1> = read_current_build_records_from_phase2(
        phase2_fd,
        GENERATIONS_DIRNAME,
        expected_build_sha,
        generation_filename_is_valid,
    )?;
    after_generations();
    let controls: Vec<Phase2SealControlRecordV1> = read_current_build_records_from_phase2(
        phase2_fd,
        CONTROLS_DIRNAME,
        expected_build_sha,
        control_filename_is_valid,
    )?;
    evaluate_current_build_lineage_records(gov_dir, expected_build_sha, now, generations, controls)
}

#[cfg(unix)]
fn load_current_build_lineage_from_phase2(
    phase2_fd: &std::fs::File,
    gov_dir: &Path,
    expected_build_sha: &str,
    now: u64,
) -> Result<Phase2LineageState, String> {
    load_current_build_lineage_from_phase2_after_generations(
        phase2_fd,
        gov_dir,
        expected_build_sha,
        now,
        || {},
    )
}

fn load_current_build_lineage(
    gov_dir: &Path,
    expected_build_sha: &str,
    now: u64,
) -> Result<Phase2LineageState, String> {
    #[cfg(unix)]
    let phase2_fd = open_secure_phase2_dir(gov_dir)
        .ok_or_else(|| "secure phase2 ledger directory unavailable".to_string())?;
    #[cfg(unix)]
    return load_current_build_lineage_from_phase2(&phase2_fd, gov_dir, expected_build_sha, now);

    #[cfg(not(unix))]
    {
        let _ = (gov_dir, expected_build_sha, now);
        Ok(Phase2LineageState {
            active: None,
            active_authoritative: false,
            tail_hash: None,
            approval_ids: BTreeSet::new(),
            approval_digests: BTreeSet::new(),
        })
    }
}

fn evaluate_current_build_lineage_records(
    gov_dir: &Path,
    expected_build_sha: &str,
    now: u64,
    generations: Vec<Phase2SealedGenerationV1>,
    controls: Vec<Phase2SealControlRecordV1>,
) -> Result<Phase2LineageState, String> {
    if generations.is_empty() && controls.is_empty() {
        return Ok(Phase2LineageState {
            active: None,
            active_authoritative: false,
            tail_hash: None,
            approval_ids: BTreeSet::new(),
            approval_digests: BTreeSet::new(),
        });
    }
    if generations.is_empty() || controls.is_empty() {
        return Err("incomplete immutable generation/control lineage".to_string());
    }

    let mut generation_by_id = BTreeMap::new();
    for generation in generations {
        // E2-F1:此處只做結構驗證(不含 expiry)——歷史/被 supersede/被 revoke
        // 的世代過期不得毀掉整條 lineage 的可載入性。
        if !sealed_generation_is_valid(&generation, gov_dir, expected_build_sha)
            || generation_by_id
                .insert(generation.generation_id.clone(), generation)
                .is_some()
        {
            return Err("invalid, stale, or duplicate sealed generation".to_string());
        }
    }
    let mut by_hash = BTreeMap::new();
    let mut referenced = BTreeSet::new();
    let mut approval_ids = BTreeSet::new();
    let mut approval_digests = BTreeSet::new();
    for control in controls {
        if !control_record_is_valid(&control, expected_build_sha)
            || !approval_ids.insert(control.approval_id.clone())
            || !approval_digests.insert(control.approval_digest.clone())
            || by_hash
                .insert(control.control_hash.clone(), control.clone())
                .is_some()
        {
            return Err("invalid or replayed immutable control record".to_string());
        }
        if let Some(previous) = &control.previous_control_hash {
            if !openclaw_types::is_sha256_hex(previous) || !referenced.insert(previous.clone()) {
                return Err("invalid or forked immutable control chain".to_string());
            }
        }
    }
    let roots: Vec<_> = by_hash
        .values()
        .filter(|control| control.previous_control_hash.is_none())
        .collect();
    let leaves: Vec<_> = by_hash
        .iter()
        .filter(|(hash, _)| !referenced.contains(*hash))
        .map(|(hash, _)| hash.clone())
        .collect();
    if roots.len() != 1 || leaves.len() != 1 {
        return Err("ambiguous immutable control chain".to_string());
    }

    let mut reverse = Vec::new();
    let mut cursor = leaves[0].clone();
    let mut visited = BTreeSet::new();
    loop {
        if !visited.insert(cursor.clone()) {
            return Err("cycle in immutable control chain".to_string());
        }
        let control = by_hash
            .get(&cursor)
            .ok_or_else(|| "missing immutable control predecessor".to_string())?;
        reverse.push(control.clone());
        match &control.previous_control_hash {
            Some(previous) => cursor = previous.clone(),
            None => break,
        }
    }
    if reverse.len() != by_hash.len() {
        return Err("disconnected immutable control chain".to_string());
    }
    reverse.reverse();

    let mut active: Option<Phase2SealedGenerationV1> = None;
    for (index, control) in reverse.iter().enumerate() {
        let target = generation_by_id
            .get(&control.target_artifact_id)
            .ok_or_else(|| "control target generation missing".to_string())?;
        if target.artifact.raw_artifact_hash != control.target_raw_hash {
            return Err("control target raw hash mismatch".to_string());
        }
        match control.action {
            Phase2SealControlAction::Seal if index == 0 && active.is_none() => {
                if control.predecessor_artifact_id.is_some()
                    || control.predecessor_raw_hash.is_some()
                {
                    return Err("genesis seal unexpectedly has predecessor".to_string());
                }
                if !generation_matches_control_binding(target, control) {
                    return Err("generation/control approval binding mismatch".to_string());
                }
                active = Some(target.clone());
            }
            Phase2SealControlAction::Supersede => {
                let previous = active
                    .as_ref()
                    .ok_or_else(|| "supersession without active predecessor".to_string())?;
                if control.predecessor_artifact_id.as_deref()
                    != Some(previous.generation_id.as_str())
                    || control.predecessor_raw_hash.as_deref()
                        != Some(previous.artifact.raw_artifact_hash.as_str())
                {
                    return Err("supersession predecessor mismatch".to_string());
                }
                if !generation_matches_control_binding(target, control) {
                    return Err("generation/control approval binding mismatch".to_string());
                }
                active = Some(target.clone());
            }
            Phase2SealControlAction::Revoke => {
                let previous = active
                    .as_ref()
                    .ok_or_else(|| "revoke without active predecessor".to_string())?;
                if control.target_artifact_id != previous.generation_id
                    || control.target_raw_hash != previous.artifact.raw_artifact_hash
                    || control.predecessor_artifact_id.as_deref()
                        != Some(previous.generation_id.as_str())
                    || control.predecessor_raw_hash.as_deref()
                        != Some(previous.artifact.raw_artifact_hash.as_str())
                {
                    return Err("revoke predecessor mismatch".to_string());
                }
                active = None;
            }
            _ => return Err("invalid immutable control action order".to_string()),
        }
    }
    // E2-F1:expiry 只在 replay 完成後、只對 active leaf 判定 authority。
    // 過期的 active 世代保留在 `active`(供 supersede/revoke 做 predecessor
    // 綁定=expired_needs_supersede 態),但 `active_authoritative=false` →
    // consume 側(`phase2_immutable_pass_artifact_present` 及 summary)一律呈
    // false/inactive,fail-closed 語義不變;帳本可操作性不受任何世代過期影響。
    let active_authoritative = active
        .as_ref()
        .map(|generation| generation.valid_until_ms > now)
        .unwrap_or(false);
    Ok(Phase2LineageState {
        active,
        active_authoritative,
        tail_hash: Some(leaves[0].clone()),
        approval_ids,
        approval_digests,
    })
}

/// E2-F9 reader 交叉檢查:generation 與其配對 control 必須同源——
/// `approval_id`/`approval_digest`/`valid_until_ms` 三欄等值,且 artifact 自記
/// 的 `supersedes_artifact_id` 必須等於 control 的 `predecessor_artifact_id`。
/// 否則兩份各自 hash 自洽的 0400 記錄可由**不同 approval** 拼裝成混鏈
/// (writer 雖同源寫入,reader 不能只信 writer 紀律)。僅適用 Seal/Supersede
/// arm;Revoke 的 target 是被撤的舊世代,其 approval 欄位本就屬於舊 approval。
fn generation_matches_control_binding(
    generation: &Phase2SealedGenerationV1,
    control: &Phase2SealControlRecordV1,
) -> bool {
    generation.approval_id == control.approval_id
        && generation.approval_digest == control.approval_digest
        && generation.valid_until_ms == control.valid_until_ms
        && generation.artifact.supersedes_artifact_id == control.predecessor_artifact_id
}

fn evaluate_controlled_phase2_for_dir(
    gov_dir: &Path,
    expected_build_sha: &str,
    now: u64,
) -> Phase2SealEvaluation {
    let mut blockers = Vec::new();
    let inputs = match load_control_inputs_from_dir(gov_dir) {
        Ok(value) => value,
        Err(reason) => {
            blockers.push(reason);
            None
        }
    };
    let approval = match load_control_approval_from_dir(gov_dir) {
        Ok(value) => value,
        Err(reason) => {
            blockers.push(reason);
            None
        }
    };
    let inputs_present = inputs.is_some();
    let inputs_valid = inputs
        .as_ref()
        .map(production_inputs_are_valid)
        .unwrap_or(false);
    let approval_present = approval.is_some();
    let approval_valid = approval
        .as_ref()
        .map(|value| phase2_control_approval_is_valid(value, now, expected_build_sha))
        .unwrap_or(false);
    let lineage = load_current_build_lineage(gov_dir, expected_build_sha, now);
    // E2-F1:authority=active 且未過期;expired_needs_supersede=active 存在但
    // 已過期(帳本可操作、gate 不放行)。
    let active_current_build = lineage
        .as_ref()
        .map(|state| state.active_authoritative)
        .unwrap_or(false);
    let active_expired_needs_supersede = lineage
        .as_ref()
        .map(|state| state.active.is_some() && !state.active_authoritative)
        .unwrap_or(false);
    if !source_commit_is_known(expected_build_sha) {
        blockers.push(REASON_SOURCE_COMMIT_UNKNOWN.to_string());
    }
    if !inputs_present {
        blockers.push("external_verification_pending:controlled_inputs_missing".to_string());
    } else if !inputs_valid {
        blockers.push("controlled_inputs_rejected".to_string());
    }
    if !approval_present {
        blockers.push("external_verification_pending:control_approval_missing".to_string());
    } else if !approval_valid {
        blockers.push("control_approval_rejected".to_string());
    }
    if let Err(reason) = lineage {
        blockers.push(format!("immutable_lineage_rejected:{reason}"));
    }
    let status = if blockers.is_empty() {
        "ready_no_contact".to_string()
    } else if blockers
        .iter()
        .any(|reason| reason.starts_with("external_verification_pending:"))
    {
        "external_verification_pending".to_string()
    } else {
        "rejected".to_string()
    };
    Phase2SealEvaluation {
        status,
        blockers,
        inputs_present,
        inputs_valid,
        approval_present,
        approval_valid,
        active_current_build,
        active_expired_needs_supersede,
        no_contact: true,
    }
}

/// Production dry-run entry point.  It only opens local owner-only files and
/// returns a redacted state; it cannot create an artifact or contact a broker.
pub fn phase2_seal_dry_run() -> Phase2SealEvaluation {
    let gov_dir = match resolve_phase2_governance_dir() {
        Ok(path) => path,
        Err(_) => {
            return Phase2SealEvaluation {
                status: "external_verification_pending".to_string(),
                blockers: vec![
                    "external_verification_pending:owner_only_data_dir_missing_or_ephemeral"
                        .to_string(),
                ],
                inputs_present: false,
                inputs_valid: false,
                approval_present: false,
                approval_valid: false,
                active_current_build: false,
                active_expired_needs_supersede: false,
                no_contact: true,
            }
        }
    };
    evaluate_controlled_phase2_for_dir(&gov_dir, BUILD_GIT_SHA, now_ms())
}

#[cfg(unix)]
fn ensure_owner_only_child_dir_after_lstat<F>(
    parent: &std::fs::File,
    child_name: &str,
    after_lstat: F,
) -> Result<std::fs::File, String>
where
    F: FnOnce(),
{
    use std::os::unix::io::{AsRawFd, FromRawFd};

    if child_name.is_empty() || child_name.contains('/') || child_name.contains('\0') {
        return Err("invalid immutable ledger directory name".to_string());
    }
    let euid = unsafe { libc::geteuid() } as u32;
    let parent_meta = parent
        .metadata()
        .map_err(|error| format!("immutable ledger parent stat failed: {error}"))?;
    if !owner_only_dir_metadata_is_secure(&parent_meta, euid) {
        return Err("immutable ledger parent is not owner-only 0700".to_string());
    }
    let name = std::ffi::CString::new(child_name)
        .map_err(|_| "invalid immutable ledger directory name".to_string())?;
    if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EEXIST) {
            return Err(format!("create immutable ledger directory failed: {error}"));
        }
    } else {
        parent
            .sync_all()
            .map_err(|error| format!("sync immutable ledger parent failed: {error}"))?;
    }
    let before = lstatat_owner_only_inode(
        parent.as_raw_fd(),
        name.as_c_str(),
        euid,
        libc::S_IFDIR as u32,
        0o700,
    )
    .ok_or_else(|| "immutable ledger child is not owner-only 0700".to_string())?;

    after_lstat();

    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(format!(
            "secure immutable ledger child open failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    let child = unsafe { std::fs::File::from_raw_fd(fd) };
    let after = child
        .metadata()
        .map_err(|error| format!("immutable ledger child stat failed: {error}"))?;
    if !owner_only_dir_metadata_is_secure(&after, euid) || !metadata_matches_inode(&after, before) {
        return Err("immutable ledger child changed during secure open".to_string());
    }
    Ok(child)
}

#[cfg(unix)]
fn ensure_owner_only_child_dir(
    parent: &std::fs::File,
    child_name: &str,
) -> Result<std::fs::File, String> {
    ensure_owner_only_child_dir_after_lstat(parent, child_name, || {})
}

#[cfg(not(unix))]
fn ensure_owner_only_child_dir(
    _parent: &std::fs::File,
    _child_name: &str,
) -> Result<std::fs::File, String> {
    Err("immutable ledger unsupported on non-unix".to_string())
}

/// Read an existing immutable record through the same inode-bound owner-only
/// dirfd used for publication and compare exact canonical bytes.  A retry can
/// therefore acknowledge only the record that this writer attempted to
/// publish; path re-resolution never participates in that decision.
#[cfg(unix)]
fn immutable_record_matches(
    dir: &std::fs::File,
    filename: &str,
    expected_raw: &[u8],
) -> Result<bool, String> {
    let euid = unsafe { libc::geteuid() } as u32;
    let raw = read_owner_only_named_child(dir, filename, euid)
        .ok_or_else(|| "existing immutable record is insecure or unreadable".to_string())?;
    Ok(raw.as_bytes() == expected_raw)
}

/// Write-once JSON record.  The final name is generated only from a verified
/// sha256 identifier.  The temporary inode is made 0400 *before* hard-link
/// publication, so a crash after the link can never leave a 0600 final record.
/// Retry compares an existing final record through a secure no-follow FD and
/// returns `AlreadyPresent` only for byte-identical content.  Thus a crash
/// between generation and control can be resumed without rewriting either.
#[cfg(unix)]
fn write_immutable_json<T: Serialize>(
    dir: &std::fs::File,
    filename: &str,
    value: &T,
) -> Result<ImmutablePublication, String> {
    use std::io::Write;
    use std::os::unix::io::{AsRawFd, FromRawFd};

    if filename.is_empty() || filename.contains('/') || filename.contains('\0') {
        return Err("invalid immutable ledger filename".to_string());
    }
    let euid = unsafe { libc::geteuid() } as u32;
    let dir_meta = dir
        .metadata()
        .map_err(|e| format!("immutable ledger directory stat failed: {e}"))?;
    if !owner_only_dir_metadata_is_secure(&dir_meta, euid) {
        return Err("immutable ledger directory is insecure".to_string());
    }
    let filename_string = filename.to_string();
    let filename = std::ffi::CString::new(filename_string.as_str())
        .map_err(|_| "invalid immutable ledger filename".to_string())?;
    let tmp_name = std::ffi::CString::new(format!(
        ".{filename_string}.{}.{}.tmp",
        std::process::id(),
        now_ns()
    ))
    .map_err(|_| "invalid immutable ledger temporary filename".to_string())?;
    let raw = serde_json::to_vec_pretty(value)
        .map_err(|e| format!("serialize immutable record failed: {e}"))?;
    {
        let fd = unsafe {
            libc::openat(
                dir.as_raw_fd(),
                tmp_name.as_ptr(),
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd < 0 {
            return Err(format!(
                "create immutable tmp failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        let mut file = unsafe { std::fs::File::from_raw_fd(fd) };
        file.write_all(&raw)
            .map_err(|e| format!("write immutable tmp failed: {e}"))?;
        file.sync_all()
            .map_err(|e| format!("sync immutable tmp failed: {e}"))?;
        if unsafe { libc::fchmod(file.as_raw_fd(), 0o400) } != 0 {
            let _ = unsafe { libc::unlinkat(dir.as_raw_fd(), tmp_name.as_ptr(), 0) };
            return Err(format!(
                "seal immutable tmp mode failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        let tmp_meta = file
            .metadata()
            .map_err(|e| format!("immutable tmp stat failed: {e}"))?;
        if !sealed_artifact_metadata_is_secure(&tmp_meta, euid) {
            let _ = unsafe { libc::unlinkat(dir.as_raw_fd(), tmp_name.as_ptr(), 0) };
            return Err("immutable tmp failed owner-only verification".to_string());
        }
        let tmp_inode = inode_from_metadata(&tmp_meta);
        if unsafe {
            libc::linkat(
                dir.as_raw_fd(),
                tmp_name.as_ptr(),
                dir.as_raw_fd(),
                filename.as_ptr(),
                0,
            )
        } != 0
        {
            let error = std::io::Error::last_os_error();
            let _ = unsafe { libc::unlinkat(dir.as_raw_fd(), tmp_name.as_ptr(), 0) };
            if error.kind() == std::io::ErrorKind::AlreadyExists
                && immutable_record_matches(dir, &filename_string, &raw)?
            {
                return Ok(ImmutablePublication::AlreadyPresent);
            }
            return Err(format!("publish immutable record failed: {error}"));
        }
        let final_inode = lstatat_owner_only_inode(
            dir.as_raw_fd(),
            filename.as_c_str(),
            euid,
            libc::S_IFREG as u32,
            0o400,
        );
        let _ = unsafe { libc::unlinkat(dir.as_raw_fd(), tmp_name.as_ptr(), 0) };
        if final_inode != Some(tmp_inode) {
            return Err("published immutable record changed before verification".to_string());
        }
    }
    dir.sync_all()
        .map_err(|e| format!("sync immutable directory failed: {e}"))?;
    Ok(ImmutablePublication::Written)
}

#[cfg(not(unix))]
fn write_immutable_json<T: Serialize>(
    _dir: &std::fs::File,
    _filename: &str,
    _value: &T,
) -> Result<ImmutablePublication, String> {
    Err("immutable ledger unsupported on non-unix".to_string())
}

fn generation_path(gov_dir: &Path, source_commit: &str, generation_id: &str) -> PathBuf {
    gov_dir
        .join(GENERATIONS_DIRNAME)
        .join(source_commit)
        .join(format!("{generation_id}.sealed.json"))
}

/// The generation name is intentionally a stable identity of the approved
/// lineage rather than a retry attempt.  A crash can therefore leave a single
/// immutable generation that a later invocation must recover, not overwrite
/// or fork.  Time remains inside the sealed artifact for auditability and is
/// consequently *not* part of this name.
fn controlled_generation_id(
    source_commit: &str,
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
    predecessor: Option<&Phase2SealedGenerationV1>,
) -> String {
    let predecessor_id = predecessor.map(|generation| generation.generation_id.as_str());
    let predecessor_hash =
        predecessor.map(|generation| generation.artifact.raw_artifact_hash.as_str());
    let id_material = serde_json::json!({
        "contract_id": W2_CONTROL_CONTRACT_ID,
        "source_commit": source_commit,
        "approval_id": approval.approval_id,
        "approval_digest": approval_digest,
        "predecessor_artifact_id": predecessor_id,
        "predecessor_raw_hash": predecessor_hash,
    });
    sha256_hex(
        serde_json::to_string(&id_material)
            .unwrap_or_default()
            .as_bytes(),
    )
}

fn build_controlled_generation(
    gov_dir: &Path,
    inputs: &Phase2SealProductionInputsV1,
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
    predecessor: Option<&Phase2SealedGenerationV1>,
    source_commit: &str,
    now: u64,
) -> Result<Phase2SealedGenerationV1, String> {
    if !production_inputs_are_valid(inputs)
        || !phase2_control_approval_is_valid(approval, now, source_commit)
    {
        return Err("controlled generation inputs or approval rejected".to_string());
    }
    let generation_id =
        controlled_generation_id(source_commit, approval, approval_digest, predecessor);
    let immutable_storage_path = generation_path(gov_dir, source_commit, &generation_id)
        .to_string_lossy()
        .into_owned();
    let policy_flags = inputs.policy_bundle.gate_prerequisite_flags();
    let mut artifact = IbkrPhase2GateArtifactV1 {
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
        artifact_id: generation_id.clone(),
        adr: IBKR_PHASE2_ADR.to_string(),
        amd: IBKR_PHASE2_AMD.to_string(),
        source_commit: source_commit.to_string(),
        created_at_ms: now,
        immutable_storage_path,
        reviewer_roles: approval.reviewer_roles.clone(),
        sealed: true,
        gate: build_external_surface_gate(
            policy_flags,
            inputs.api_allowlist.validate().accepted,
            inputs.secret_slot_contract.validate().accepted,
            inputs.secret_slot_contract.live_secret_absent_or_empty,
        ),
        policy_flags,
        secret_slot_contract: inputs.secret_slot_contract.clone(),
        api_session_topology: inputs.api_session_topology.clone(),
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        // This shape field remains an old artifact compatibility requirement;
        // W2's 07-11 control approval is separately recorded above and is not
        // a contact/activation authorization.
        contact_authorization_amd: IBKR_PHASE2_CONTACT_AMD.to_string(),
        approval_lineage_hash: approval_digest.to_string(),
        supersedes_artifact_id: predecessor.map(|value| value.generation_id.clone()),
    };
    artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
    artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);
    if !artifact.validate().ibkr_contact_allowed
        || !verify_artifact_hashes(&artifact)
        || !account_fingerprint_triangulation_ok(&artifact)
    {
        return Err("controlled artifact construction rejected".to_string());
    }
    let mut generation = Phase2SealedGenerationV1 {
        contract_id: W2_CONTROL_CONTRACT_ID.to_string(),
        source_version: 1,
        generation_id,
        approval_id: approval.approval_id.clone(),
        approval_digest: approval_digest.to_string(),
        valid_until_ms: approval.expires_at_ms,
        artifact,
        generation_hash: String::new(),
    };
    generation.generation_hash = generation_hash(&generation);
    Ok(generation)
}

fn build_control_record(
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
    target: &Phase2SealedGenerationV1,
    predecessor: Option<&Phase2SealedGenerationV1>,
    previous_control_hash: Option<String>,
    source_commit: &str,
    now: u64,
) -> Phase2SealControlRecordV1 {
    let mut record = Phase2SealControlRecordV1 {
        contract_id: W2_CONTROL_CONTRACT_ID.to_string(),
        source_version: 1,
        control_id: String::new(),
        action: approval.action,
        approval_id: approval.approval_id.clone(),
        approval_digest: approval_digest.to_string(),
        source_commit: source_commit.to_string(),
        recorded_at_ms: now,
        valid_until_ms: approval.expires_at_ms,
        target_artifact_id: target.generation_id.clone(),
        target_raw_hash: target.artifact.raw_artifact_hash.clone(),
        predecessor_artifact_id: predecessor.map(|value| value.generation_id.clone()),
        predecessor_raw_hash: predecessor.map(|value| value.artifact.raw_artifact_hash.clone()),
        previous_control_hash,
        control_hash: String::new(),
    };
    record.control_id = control_id(&record);
    record.control_hash = control_hash(&record);
    record
}

/// FD-bound form used inside `Phase2ApplyLock`.  It intentionally takes the
/// caller-owned Phase2 directory instead of reopening `gov_dir`, so control
/// replay checks cannot be composed from a swapped ledger tree.
#[cfg(unix)]
fn matching_control_for_approval_from_phase2(
    phase2_fd: &std::fs::File,
    source_commit: &str,
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
) -> Result<Option<Phase2SealControlRecordV1>, String> {
    let records: Vec<Phase2SealControlRecordV1> = read_current_build_records_from_phase2(
        phase2_fd,
        CONTROLS_DIRNAME,
        source_commit,
        control_filename_is_valid,
    )?;
    let mut matching = records.into_iter().filter(|record| {
        record.approval_id == approval.approval_id || record.approval_digest == approval_digest
    });
    let first = matching.next();
    if matching.next().is_some() {
        return Err("multiple immutable controls match one approval".to_string());
    }
    match first {
        Some(record)
            if record.approval_id == approval.approval_id
                && record.approval_digest == approval_digest
                && record.action == approval.action
                && record.source_commit == source_commit =>
        {
            Ok(Some(record))
        }
        Some(_) => Err("immutable control approval replay mismatch".to_string()),
        None => Ok(None),
    }
}

/// Lock-held version of the completed-retry proof.  All reads are derived from
/// one Phase2 dirfd captured by `Phase2ApplyLock`; no ledger path is reopened
/// between acquiring the lock and deciding an idempotent result.
#[cfg(unix)]
fn validate_completed_control_retry_from_phase2(
    phase2_fd: &std::fs::File,
    gov_dir: &Path,
    source_commit: &str,
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
    now: u64,
) -> Result<bool, String> {
    let lineage = load_current_build_lineage_from_phase2(phase2_fd, gov_dir, source_commit, now)?;
    let Some(record) = matching_control_for_approval_from_phase2(
        phase2_fd,
        source_commit,
        approval,
        approval_digest,
    )?
    else {
        return Ok(false);
    };
    match approval.action {
        Phase2SealControlAction::Seal | Phase2SealControlAction::Supersede => {
            if lineage
                .active
                .as_ref()
                .map(|active| active.generation_id.as_str())
                != Some(record.target_artifact_id.as_str())
            {
                return Err("completed control does not own active generation".to_string());
            }
        }
        Phase2SealControlAction::Revoke if lineage.active.is_none() => {}
        Phase2SealControlAction::Revoke => {
            return Err("completed revoke still has an active generation".to_string())
        }
    }
    Ok(true)
}

/// Find the one unpaired generation which an interrupted apply may have
/// published before its matching control.  The object is re-read through the
/// secure ledger reader and is bound to the current approval *and* expected
/// predecessor before it can be used.  This is deliberately not a general
/// "pick the newest generation" recovery path: any extra/unmatched orphan is
/// a fail-closed lineage error.
/// Lock-held orphan recovery.  This is the only form used by apply so an
/// interrupted generation cannot be recovered from a replacement tree.
#[cfg(unix)]
fn recoverable_orphan_generation_from_phase2(
    phase2_fd: &std::fs::File,
    gov_dir: &Path,
    source_commit: &str,
    approval: &Phase2SealControlApprovalV1,
    approval_digest: &str,
    predecessor: Option<&Phase2SealedGenerationV1>,
) -> Result<Option<Phase2SealedGenerationV1>, String> {
    let generations: Vec<Phase2SealedGenerationV1> = read_current_build_records_from_phase2(
        phase2_fd,
        GENERATIONS_DIRNAME,
        source_commit,
        generation_filename_is_valid,
    )?;
    let controls: Vec<Phase2SealControlRecordV1> = read_current_build_records_from_phase2(
        phase2_fd,
        CONTROLS_DIRNAME,
        source_commit,
        control_filename_is_valid,
    )?;
    let controlled_generation_ids: BTreeSet<_> = controls
        .iter()
        .map(|control| control.target_artifact_id.as_str())
        .collect();
    let mut orphans: Vec<_> = generations
        .into_iter()
        .filter(|generation| !controlled_generation_ids.contains(generation.generation_id.as_str()))
        .collect();
    if orphans.is_empty() {
        return Ok(None);
    }
    if orphans.len() != 1 {
        return Err("multiple unpaired immutable generations prevent recovery".to_string());
    }
    let orphan = orphans.pop().expect("length checked");
    let expected_id =
        controlled_generation_id(source_commit, approval, approval_digest, predecessor);
    // E2-F1:結構驗證不含 expiry;orphan 的 valid_until 被下方
    // `orphan.valid_until_ms != approval.expires_at_ms` 綁死在「當前有效
    // approval 的過期時點」上,故被收養的 orphan 必然未過期。
    if !sealed_generation_is_valid(&orphan, gov_dir, source_commit)
        || orphan.generation_id != expected_id
        || orphan.approval_id != approval.approval_id
        || orphan.approval_digest != approval_digest
        || orphan.valid_until_ms != approval.expires_at_ms
        || orphan.artifact.supersedes_artifact_id
            != predecessor.map(|value| value.generation_id.clone())
    {
        return Err(
            "unpaired immutable generation does not match retry approval/lineage".to_string(),
        );
    }
    Ok(Some(orphan))
}

fn apply_controlled_phase2_for_dir(
    gov_dir: &Path,
    inputs: Option<&Phase2SealProductionInputsV1>,
    approval: &Phase2SealControlApprovalV1,
    source_commit: &str,
    now: u64,
) -> Result<Phase2SealApplyOutcome, String> {
    apply_controlled_phase2_for_dir_with_hooks(
        gov_dir,
        inputs,
        approval,
        source_commit,
        now,
        || {},
        || {},
    )
}

/// Both hooks are inert in production.  Unix tests use them to model a process
/// dying after the generation link or after the control link, then prove that a
/// retry revalidates the ledger and writes only the missing sibling record.
fn apply_controlled_phase2_for_dir_with_hooks<AfterGeneration, AfterControl>(
    gov_dir: &Path,
    inputs: Option<&Phase2SealProductionInputsV1>,
    approval: &Phase2SealControlApprovalV1,
    source_commit: &str,
    now: u64,
    after_generation: AfterGeneration,
    after_control: AfterControl,
) -> Result<Phase2SealApplyOutcome, String>
where
    AfterGeneration: FnOnce(),
    AfterControl: FnOnce(),
{
    apply_controlled_phase2_for_dir_with_lock_hook(
        gov_dir,
        inputs,
        approval,
        source_commit,
        now,
        || {},
        after_generation,
        after_control,
    )
}

/// Inner apply transaction with a test-only pre-read hook.  Production passes
/// an inert hook through `apply_controlled_phase2_for_dir_with_hooks`; the
/// hook lets the regression model a whole `ibkr_phase2` pathname swap exactly
/// after the lock owns its bound directory FDs and before any ledger read or
/// write occurs.
fn apply_controlled_phase2_for_dir_with_lock_hook<AfterLock, AfterGeneration, AfterControl>(
    gov_dir: &Path,
    inputs: Option<&Phase2SealProductionInputsV1>,
    approval: &Phase2SealControlApprovalV1,
    source_commit: &str,
    now: u64,
    after_lock: AfterLock,
    after_generation: AfterGeneration,
    after_control: AfterControl,
) -> Result<Phase2SealApplyOutcome, String>
where
    AfterLock: FnOnce(),
    AfterGeneration: FnOnce(),
    AfterControl: FnOnce(),
{
    if !source_commit_is_known(source_commit)
        || !phase2_control_approval_is_valid(approval, now, source_commit)
    {
        return Err("controlled phase2 approval rejected".to_string());
    }
    let lock = Phase2ApplyLock::acquire(gov_dir)?;
    after_lock();
    // From this point through completion, every ledger read and write is
    // rooted in `lock.parent`.  `ensure_bound` also proves the governance
    // entry still names that exact inode before any decision or publication.
    lock.ensure_bound()?;
    let approval_digest = control_approval_digest(approval);
    let lineage =
        match load_current_build_lineage_from_phase2(&lock.parent, gov_dir, source_commit, now) {
            Ok(lineage) => {
                if validate_completed_control_retry_from_phase2(
                    &lock.parent,
                    gov_dir,
                    source_commit,
                    approval,
                    &approval_digest,
                    now,
                )? {
                    return Ok(Phase2SealApplyOutcome {
                        status: "already_applied_no_contact".to_string(),
                        blockers: Vec::new(),
                        action: Some(approval.action),
                        no_contact: true,
                        wrote_generation: false,
                        wrote_control: false,
                    });
                }
                lineage
            }
            Err(reason) => {
                // E2 驗證點 5:lineage Err 時唯一可恢復的形態=「創世 seal 已
                // 寫入 generation、control 尚未落盤」的中斷——此時 controls
                // 分支必然為空。controls 非空而 lineage 仍 Err = 帳本本體損壞
                // (fork/竄改/亂序);若仍放行 orphan 收養,會在空 lineage 假設
                // 下寫入第二個 control root,永久 brick 帳本 → fail-closed,
                // 原因原樣回傳,零寫。controls 分支本身讀不動也視為非空(拒)。
                let controls_branch_is_empty =
                    read_current_build_records_from_phase2::<Phase2SealControlRecordV1>(
                        &lock.parent,
                        CONTROLS_DIRNAME,
                        source_commit,
                        control_filename_is_valid,
                    )
                    .map(|records| records.is_empty())
                    .unwrap_or(false);
                if !controls_branch_is_empty
                    || !matches!(approval.action, Phase2SealControlAction::Seal)
                    || recoverable_orphan_generation_from_phase2(
                        &lock.parent,
                        gov_dir,
                        source_commit,
                        approval,
                        &approval_digest,
                        None,
                    )?
                    .is_none()
                {
                    return Err(reason);
                }
                Phase2LineageState {
                    active: None,
                    active_authoritative: false,
                    tail_hash: None,
                    approval_ids: BTreeSet::new(),
                    approval_digests: BTreeSet::new(),
                }
            }
        };
    lock.ensure_bound()?;
    if lineage.approval_ids.contains(&approval.approval_id)
        || lineage.approval_digests.contains(&approval_digest)
    {
        return Err("controlled phase2 approval replay rejected".to_string());
    }

    let predecessor = lineage.active.as_ref();
    match approval.action {
        Phase2SealControlAction::Seal if predecessor.is_some() => {
            return Err("seal rejected: active generation already exists".to_string())
        }
        // Seal 僅能作創世 control。revoke 後 active=None 但鏈非空(tail_hash=Some)，
        // 若放行，新 genesis Seal 會在寫入不可變 0400 記錄「後」才被 post-write
        // evaluator 於 index>0 拒絕 → ledger 從此 load 失敗且無法再 apply(bricking)。
        // 故在任何寫入前 fail-closed。revoke 對同一 build SHA 為終態。
        Phase2SealControlAction::Seal if lineage.tail_hash.is_some() => {
            return Err(
                "seal rejected: build sha lineage already exists (revoke is terminal)".to_string(),
            )
        }
        Phase2SealControlAction::Seal
            if approval.predecessor_artifact_id.is_some()
                || approval.predecessor_raw_hash.is_some() =>
        {
            return Err("seal rejected: unexpected predecessor binding".to_string())
        }
        Phase2SealControlAction::Supersede | Phase2SealControlAction::Revoke => {
            let previous = predecessor
                .ok_or_else(|| "control rejected: active predecessor missing".to_string())?;
            if approval.predecessor_artifact_id.as_deref() != Some(previous.generation_id.as_str())
                || approval.predecessor_raw_hash.as_deref()
                    != Some(previous.artifact.raw_artifact_hash.as_str())
            {
                return Err("control rejected: predecessor binding mismatch".to_string());
            }
        }
        _ => {}
    }

    let target = match approval.action {
        Phase2SealControlAction::Revoke => predecessor
            .cloned()
            .ok_or_else(|| "revoke rejected: active predecessor missing".to_string())?,
        Phase2SealControlAction::Seal | Phase2SealControlAction::Supersede => {
            match recoverable_orphan_generation_from_phase2(
                &lock.parent,
                gov_dir,
                source_commit,
                approval,
                &approval_digest,
                predecessor,
            )? {
                Some(orphan) => orphan,
                None => {
                    let supplied = inputs.ok_or_else(|| {
                        "external_verification_pending:controlled_inputs_missing".to_string()
                    })?;
                    build_controlled_generation(
                        gov_dir,
                        supplied,
                        approval,
                        &approval_digest,
                        predecessor,
                        source_commit,
                        now,
                    )?
                }
            }
        }
    };
    let record = build_control_record(
        approval,
        &approval_digest,
        &target,
        predecessor,
        lineage.tail_hash,
        source_commit,
        now,
    );

    lock.ensure_bound()?;
    let generations_root = ensure_owner_only_child_dir(&lock.parent, GENERATIONS_DIRNAME)?;
    let controls_root = ensure_owner_only_child_dir(&lock.parent, CONTROLS_DIRNAME)?;
    let generation_dir = ensure_owner_only_child_dir(&generations_root, source_commit)?;
    let control_dir = ensure_owner_only_child_dir(&controls_root, source_commit)?;
    let mut wrote_generation = false;
    if !matches!(approval.action, Phase2SealControlAction::Revoke) {
        lock.ensure_bound()?;
        wrote_generation = write_immutable_json(
            &generation_dir,
            &format!("{}.sealed.json", target.generation_id),
            &target,
        )? == ImmutablePublication::Written;
        lock.ensure_bound()?;
        after_generation();
    }
    lock.ensure_bound()?;
    let wrote_control = write_immutable_json(
        &control_dir,
        &format!("{}.control.json", record.control_id),
        &record,
    )? == ImmutablePublication::Written;
    lock.ensure_bound()?;
    after_control();
    lock.ensure_bound()?;
    let completed = validate_completed_control_retry_from_phase2(
        &lock.parent,
        gov_dir,
        source_commit,
        approval,
        &approval_digest,
        now,
    )?;
    lock.ensure_bound()?;
    if !completed {
        return Err("post-write immutable lineage validation failed".to_string());
    }
    Ok(Phase2SealApplyOutcome {
        status: "applied_no_contact".to_string(),
        blockers: Vec::new(),
        action: Some(approval.action),
        no_contact: true,
        wrote_generation,
        wrote_control,
    })
}

/// The only production mutation entry point.  A caller must explicitly pass
/// `true` (the standalone bin only does so for `--apply`) and the environment
/// must be exactly literal `1`.  Any missing input/approval leaves no ledger
/// write and is reported as external verification pending.
pub fn phase2_apply_seal_if_explicitly_requested(
    cli_apply_requested: bool,
) -> Phase2SealApplyOutcome {
    if !cli_apply_requested {
        return Phase2SealApplyOutcome {
            status: "dry_run".to_string(),
            blockers: vec!["apply_flag_required".to_string()],
            action: None,
            no_contact: true,
            wrote_generation: false,
            wrote_control: false,
        };
    }
    if std::env::var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY")
        .ok()
        .as_deref()
        != Some("1")
    {
        return Phase2SealApplyOutcome {
            status: "blocked".to_string(),
            blockers: vec!["OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1_required".to_string()],
            action: None,
            no_contact: true,
            wrote_generation: false,
            wrote_control: false,
        };
    }
    let gov_dir = match resolve_phase2_governance_dir() {
        Ok(path) => path,
        Err(_) => {
            return Phase2SealApplyOutcome {
                status: "external_verification_pending".to_string(),
                blockers: vec![
                    "external_verification_pending:owner_only_data_dir_missing_or_ephemeral"
                        .to_string(),
                ],
                action: None,
                no_contact: true,
                wrote_generation: false,
                wrote_control: false,
            }
        }
    };
    // E2-F4 診斷分流:load 的 Err(檔案存在但 JSON 壞)≠ Ok(None)(檔案缺席)。
    // 舊 `.ok().flatten()` 把兩者混為 missing → operator 佈了壞檔會被誤導成
    // 「還沒佈檔」。rejected → blocked+原因;missing → pending。
    // (檔案存在但 owner/mode/symlink 不安全時 secure reader 回 None,仍歸
    // missing——不洩漏拒讀原因是 W1 consumer 既定語義,此處不改。)
    let inputs = match load_control_inputs_from_dir(&gov_dir) {
        Ok(value) => value,
        Err(reason) => {
            return Phase2SealApplyOutcome {
                status: "blocked".to_string(),
                blockers: vec![reason],
                action: None,
                no_contact: true,
                wrote_generation: false,
                wrote_control: false,
            }
        }
    };
    let approval = match load_control_approval_from_dir(&gov_dir) {
        Ok(value) => value,
        Err(reason) => {
            return Phase2SealApplyOutcome {
                status: "blocked".to_string(),
                blockers: vec![reason],
                action: None,
                no_contact: true,
                wrote_generation: false,
                wrote_control: false,
            }
        }
    };
    let Some(approval) = approval else {
        return Phase2SealApplyOutcome {
            status: "external_verification_pending".to_string(),
            blockers: vec!["external_verification_pending:control_approval_missing".to_string()],
            action: None,
            no_contact: true,
            wrote_generation: false,
            wrote_control: false,
        };
    };
    match apply_controlled_phase2_for_dir(
        &gov_dir,
        inputs.as_ref(),
        &approval,
        BUILD_GIT_SHA,
        now_ms(),
    ) {
        Ok(outcome) => outcome,
        Err(reason) => Phase2SealApplyOutcome {
            status: if reason.starts_with("external_verification_pending:") {
                "external_verification_pending".to_string()
            } else {
                "blocked".to_string()
            },
            blockers: vec![reason],
            action: Some(approval.action),
            no_contact: true,
            wrote_generation: false,
            wrote_control: false,
        },
    }
}

/// IPC/display surface remains read-only and cannot invoke the apply entry.
pub fn phase2_gate_producer_summary() -> serde_json::Value {
    let evaluation = phase2_seal_dry_run();
    serde_json::json!({
        "producer_status": evaluation.status,
        "immutable_pass_artifact_present": evaluation.active_current_build,
        // E2-F1:active 世代存在但過期 → 非 authoritative;operator 以
        // Supersede 續期(帳本不死鎖,ADR-0048 re-attestation 語義)。
        "active_expired_needs_supersede": evaluation.active_expired_needs_supersede,
        "blockers": evaluation.blockers,
        "inputs_present": evaluation.inputs_present,
        "inputs_valid": evaluation.inputs_valid,
        "approval_present": evaluation.approval_present,
        "approval_valid": evaluation.approval_valid,
        "no_contact": true,
        "seal_apply_requires_cli_and_env": true,
        "activation_authority": "separate_rust_activation_envelope_required",
        "ibkr_call_performed": false,
    })
}

/// The precontact consumer derives exactly one active current-build, unexpired,
/// non-revoked immutable lineage.  Ambiguity, replay, fork, stale build/expiry,
/// insecure filesystem, or any parse failure returns false.
pub(crate) fn phase2_immutable_pass_artifact_present() -> bool {
    let gov_dir = match resolve_phase2_governance_dir() {
        Ok(path) => path,
        Err(_) => return false,
    };
    // E2-F1:consume 側取 authority 真值(active 且未過期);過期的 active 呈
    // false/inactive(fail-closed),但不影響帳本側 supersede/revoke 可操作性。
    load_current_build_lineage(&gov_dir, BUILD_GIT_SHA, now_ms())
        .map(|state| state.active_authoritative)
        .unwrap_or(false)
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

    fn controlled_inputs() -> Phase2SealProductionInputsV1 {
        let mut secret = valid_secret();
        // E2-F3 anti-placeholder:production inputs 不得沿用 template 全同字元
        // 指紋("a"*64/"b"*64/"c"*64)。fixture 改用真實形態的非 placeholder
        // 64-hex(內容任意、僅形態真實,絕非任何真憑證材料)。
        secret.secret_slot_fingerprint = sha256_hex(b"w2-test-secret-slot-fingerprint");
        secret.account_fingerprint_hash = sha256_hex(b"w2-test-account-fingerprint");
        Phase2SealProductionInputsV1 {
            contract_id: W2_INPUTS_CONTRACT_ID.to_string(),
            source_version: 1,
            policy_bundle: valid_bundle(),
            api_allowlist: valid_allowlist(),
            secret_slot_contract: secret.clone(),
            api_session_topology: matched_topology(&secret),
        }
    }

    fn controlled_approval(
        approval_id: char,
        action: Phase2SealControlAction,
        sha: &str,
        predecessor: Option<&Phase2SealedGenerationV1>,
    ) -> Phase2SealControlApprovalV1 {
        Phase2SealControlApprovalV1 {
            contract_id: W2_CONTROL_CONTRACT_ID.to_string(),
            source_version: 1,
            approval_id: approval_id.to_string().repeat(64),
            action,
            authorization_amd: W2_CONTROL_AMD.to_string(),
            reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
            approved_source_commit: sha.to_string(),
            issued_at_ms: FIXED_NOW - 1000,
            expires_at_ms: FIXED_NOW + 3_600_000,
            predecessor_artifact_id: predecessor.map(|value| value.generation_id.clone()),
            predecessor_raw_hash: predecessor.map(|value| value.artifact.raw_artifact_hash.clone()),
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

    // --- W2: default summary is external-verification-pending and cannot apply. ---
    #[test]
    fn summary_reports_blocked_shape() {
        let _g = crate::test_env_lock::guard();
        let prev = std::env::var("OPENCLAW_DATA_DIR").ok();
        std::env::remove_var("OPENCLAW_DATA_DIR");

        let s = phase2_gate_producer_summary();
        assert_eq!(s["producer_status"], "external_verification_pending");
        assert_eq!(s["immutable_pass_artifact_present"], false);
        assert_eq!(s["ibkr_call_performed"], false);
        assert!(s["blockers"].as_array().is_some());
        assert_eq!(s["no_contact"], true);
        assert_eq!(s["seal_apply_requires_cli_and_env"], true);

        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }

    #[test]
    fn w2_controlled_seal_supersede_revoke_preserves_predecessor_and_consumes_once() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let seal = controlled_approval('d', Phase2SealControlAction::Seal, &sha, None);

        let first = apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("first no-contact seal");
        assert_eq!(first.status, "applied_no_contact");
        assert!(first.wrote_generation && first.wrote_control);
        let state1 = load_current_build_lineage(&gov, &sha, FIXED_NOW).unwrap();
        let predecessor = state1.active.clone().expect("active first generation");
        let predecessor_path = generation_path(&gov, &sha, &predecessor.generation_id);
        let predecessor_bytes = fs::read(&predecessor_path).unwrap();

        let idempotent =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
                .expect("same approval must validate the already-complete publication");
        assert_eq!(idempotent.status, "already_applied_no_contact");
        assert!(!idempotent.wrote_generation && !idempotent.wrote_control);

        let supersede = controlled_approval(
            'e',
            Phase2SealControlAction::Supersede,
            &sha,
            Some(&predecessor),
        );
        let second =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &supersede, &sha, FIXED_NOW + 1)
                .expect("supersede no-contact seal");
        assert!(second.wrote_generation && second.wrote_control);
        assert_eq!(fs::read(&predecessor_path).unwrap(), predecessor_bytes);
        let state2 = load_current_build_lineage(&gov, &sha, FIXED_NOW + 1).unwrap();
        let active = state2.active.clone().expect("active successor generation");
        assert_ne!(active.generation_id, predecessor.generation_id);
        assert_eq!(
            active.artifact.supersedes_artifact_id.as_deref(),
            Some(predecessor.generation_id.as_str())
        );

        let revoke = controlled_approval('f', Phase2SealControlAction::Revoke, &sha, Some(&active));
        let revoked = apply_controlled_phase2_for_dir(&gov, None, &revoke, &sha, FIXED_NOW + 2)
            .expect("revoke no-contact seal");
        assert!(!revoked.wrote_generation && revoked.wrote_control);
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 2)
                .unwrap()
                .active
                .is_none(),
            "revocation must make the current-build consumer fail closed"
        );
    }

    /// P2 回歸：revoke 後對同一 build SHA 再發 genesis Seal 必須在寫入前被擋，
    /// 不得留下不可變記錄而 brick ledger（修前：reseal 寫檔後 post-write 失敗，
    /// 之後 load 永久 Err）。
    #[test]
    fn w2_reseal_after_revoke_is_rejected_without_bricking_ledger() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        let seal = controlled_approval('1', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("genesis seal");
        let active = load_current_build_lineage(&gov, &sha, FIXED_NOW)
            .unwrap()
            .active
            .expect("active after seal");

        let revoke = controlled_approval('2', Phase2SealControlAction::Revoke, &sha, Some(&active));
        apply_controlled_phase2_for_dir(&gov, None, &revoke, &sha, FIXED_NOW + 1).expect("revoke");
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 1)
                .unwrap()
                .active
                .is_none(),
            "revoke 後 active 必為 None"
        );

        // 對同一 build SHA 再發全新 genesis seal：必須被 pre-write guard 擋，回 Err。
        let reseal = controlled_approval('3', Phase2SealControlAction::Seal, &sha, None);
        let err =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &reseal, &sha, FIXED_NOW + 2)
                .expect_err("reseal after revoke must be rejected pre-write");
        assert!(
            err.contains("lineage already exists") || err.contains("revoke is terminal"),
            "unexpected rejection reason: {err}"
        );

        // 關鍵：ledger 未被 brick — load 仍成功且維持 revoked(None)。
        // 修前此處會是 Err（不可變 reseal 記錄已落盤）。
        let after = load_current_build_lineage(&gov, &sha, FIXED_NOW + 2)
            .expect("ledger must remain loadable (not bricked) after rejected reseal");
        assert!(after.active.is_none(), "ledger 應維持 revoked 狀態");
    }

    /// P2 回歸（多 entry 鏈）：seal → supersede → revoke 之後，tail_hash 指向的是
    /// 一條較長 control 鏈末端的 revoke（非單世代情形）。對同一 build SHA 再發全新
    /// genesis Seal 仍必須在寫入前被 tail_hash guard 擋下，且 ledger 不得被 brick。
    /// 用意：釘住 guard 不只覆蓋「seal→revoke」單代路徑，也涵蓋 tail_hash 深埋在
    /// 多筆 control 之後的長鏈。
    #[test]
    fn w2_reseal_after_supersede_revoke_multi_entry_chain_is_rejected_without_brick() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        // 世代 1：genesis seal。
        let seal = controlled_approval('4', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("genesis seal");
        let gen1 = load_current_build_lineage(&gov, &sha, FIXED_NOW)
            .unwrap()
            .active
            .expect("active after seal");

        // 世代 2：supersede（control 鏈加長至 2 筆）。
        let supersede =
            controlled_approval('5', Phase2SealControlAction::Supersede, &sha, Some(&gen1));
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &supersede, &sha, FIXED_NOW + 1)
            .expect("supersede");
        let gen2 = load_current_build_lineage(&gov, &sha, FIXED_NOW + 1)
            .unwrap()
            .active
            .expect("active after supersede");

        // revoke 世代 2 → active=None、tail_hash=Some(第 3 筆 control=revoke)。
        let revoke = controlled_approval('6', Phase2SealControlAction::Revoke, &sha, Some(&gen2));
        apply_controlled_phase2_for_dir(&gov, None, &revoke, &sha, FIXED_NOW + 2).expect("revoke");
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 2)
                .unwrap()
                .active
                .is_none(),
            "revoke 後 active 必為 None"
        );

        // 對同一 build SHA 再發全新 genesis seal（predecessor=None）：即使 tail_hash
        // 深埋在較長鏈末端，仍須於任何寫入前被擋回 Err。
        let reseal = controlled_approval('7', Phase2SealControlAction::Seal, &sha, None);
        let err =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &reseal, &sha, FIXED_NOW + 3)
                .expect_err("reseal after supersede+revoke must be rejected pre-write");
        assert!(
            err.contains("lineage already exists") || err.contains("revoke is terminal"),
            "unexpected rejection reason: {err}"
        );

        // 關鍵：ledger 未被 brick — load 仍成功且維持 revoked(None)。
        let after = load_current_build_lineage(&gov, &sha, FIXED_NOW + 3)
            .expect("ledger must remain loadable (not bricked) after rejected reseal");
        assert!(after.active.is_none(), "ledger 應維持 revoked 狀態");
    }

    /// P2 回歸（arm 排序鎖）：seal → revoke 之後 active=None、tail_hash=Some。
    /// 若未來重構讓一個「攜帶 predecessor bindings 的 Seal」進入 apply，該 approval
    /// 仍會通過 `phase2_control_approval_is_valid`——Seal 對 `Some(valid sha256_hex)`
    /// 綁定回傳 true（見驗證斷言），故必然抵達 match。此測試釘住：tail_hash arm
    /// 排在 predecessor-binding arm 之前，拒絕理由必須是 tail_hash guard
    /// （"lineage already exists"/"revoke is terminal"），而非 "unexpected predecessor
    /// binding"。否則一個帶綁定的 reseal 可能在未來繞過 guard 溜進寫入路徑。
    #[test]
    fn w2_reseal_after_revoke_with_predecessor_bindings_is_caught_by_tail_hash_guard() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        let seal = controlled_approval('8', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("genesis seal");
        let revoked_gen = load_current_build_lineage(&gov, &sha, FIXED_NOW)
            .unwrap()
            .active
            .expect("active after seal");

        let revoke = controlled_approval(
            '9',
            Phase2SealControlAction::Revoke,
            &sha,
            Some(&revoked_gen),
        );
        apply_controlled_phase2_for_dir(&gov, None, &revoke, &sha, FIXED_NOW + 1).expect("revoke");
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 1)
                .unwrap()
                .active
                .is_none(),
            "revoke 後 active 必為 None"
        );

        // 帶 predecessor bindings 的 Seal（指向已被 revoke 的世代）。helper 以該世代的
        // generation_id / raw_artifact_hash 填綁定，兩者皆 valid sha256_hex。
        let bound_reseal =
            controlled_approval('a', Phase2SealControlAction::Seal, &sha, Some(&revoked_gen));
        // 前置健檢：確認此 Seal-with-bindings 確實攜帶綁定，且通過 approval 有效性
        // ——唯有通過有效性才會真正抵達 match，測到 arm 排序（否則會測錯拒絕點）。
        assert!(
            bound_reseal.predecessor_artifact_id.is_some()
                && bound_reseal.predecessor_raw_hash.is_some(),
            "此 reseal 必須確實攜帶 predecessor bindings"
        );
        assert!(
            phase2_control_approval_is_valid(&bound_reseal, FIXED_NOW + 2, &sha),
            "帶合法 hex 綁定的 Seal 必須通過 approval 有效性，才能真正測到 arm 排序"
        );

        let err = apply_controlled_phase2_for_dir(
            &gov,
            Some(&inputs),
            &bound_reseal,
            &sha,
            FIXED_NOW + 2,
        )
        .expect_err("bound reseal after revoke must be rejected");
        // tail_hash arm 必須勝出（排在 predecessor-binding arm 之前）。
        assert!(
            err.contains("lineage already exists") || err.contains("revoke is terminal"),
            "tail_hash guard 應先命中，實得: {err}"
        );
        assert!(
            !err.contains("unexpected predecessor binding"),
            "不得落入 predecessor-binding arm——那代表 arm 排序被破壞: {err}"
        );

        // ledger 未被 brick — load 仍成功且維持 revoked(None)。
        let after = load_current_build_lineage(&gov, &sha, FIXED_NOW + 2)
            .expect("ledger must remain loadable (not bricked)");
        assert!(after.active.is_none(), "ledger 應維持 revoked 狀態");
    }

    #[test]
    fn w2_controlled_lineage_rejects_fork_crossbuild_and_expired_approval() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let seal = controlled_approval('a', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW).unwrap();
        let state = load_current_build_lineage(&gov, &sha, FIXED_NOW).unwrap();
        let active = state.active.clone().unwrap();

        let mut expired =
            controlled_approval('b', Phase2SealControlAction::Supersede, &sha, Some(&active));
        expired.expires_at_ms = FIXED_NOW - 1;
        assert!(!phase2_control_approval_is_valid(&expired, FIXED_NOW, &sha));
        assert!(!phase2_control_approval_is_valid(
            &seal,
            FIXED_NOW,
            &"b".repeat(40)
        ));

        // A syntactically valid second branch uses a distinct approval but the
        // same predecessor control hash.  Reader must reject the ambiguity
        // rather than selecting by filesystem enumeration order.
        let branch_approval =
            controlled_approval('c', Phase2SealControlAction::Revoke, &sha, Some(&active));
        let branch = build_control_record(
            &branch_approval,
            &control_approval_digest(&branch_approval),
            &active,
            Some(&active),
            state.tail_hash.clone(),
            &sha,
            FIXED_NOW + 1,
        );
        let controls = gov.join(CONTROLS_DIRNAME).join(&sha);
        let controls_fd = fs::File::open(&controls).unwrap();
        write_immutable_json(
            &controls_fd,
            &format!("{}.control.json", branch.control_id),
            &branch,
        )
        .unwrap();
        let second_branch_approval =
            controlled_approval('d', Phase2SealControlAction::Revoke, &sha, Some(&active));
        let second_branch = build_control_record(
            &second_branch_approval,
            &control_approval_digest(&second_branch_approval),
            &active,
            Some(&active),
            state.tail_hash.clone(),
            &sha,
            FIXED_NOW + 2,
        );
        write_immutable_json(
            &controls_fd,
            &format!("{}.control.json", second_branch.control_id),
            &second_branch,
        )
        .unwrap();
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 1).is_err(),
            "forked append-only chain must not yield an arbitrary active leaf"
        );
    }

    #[test]
    fn w2_writer_rejects_ledger_child_replacement_after_lstat() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let phase2_fd = open_secure_phase2_dir(&gov).expect("secure writer parent");
        let generations = gov.join(GENERATIONS_DIRNAME);
        let retired = gov.join("retired-generations");

        let result =
            ensure_owner_only_child_dir_after_lstat(&phase2_fd, GENERATIONS_DIRNAME, || {
                fs::rename(&generations, &retired).unwrap();
                std::os::unix::fs::symlink(&retired, &generations).unwrap();
            });
        assert!(
            result.is_err(),
            "writer must reject a same-owner child replacement between lstat and openat"
        );
        assert!(
            fs::symlink_metadata(&generations)
                .unwrap()
                .file_type()
                .is_symlink(),
            "fixture must exercise the replacement shape"
        );
    }

    #[test]
    fn w2_apply_requires_explicit_cli_flag_even_when_env_gate_is_set() {
        let _g = crate::test_env_lock::guard();
        let old = std::env::var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY").ok();
        std::env::set_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY", "1");
        let outcome = phase2_apply_seal_if_explicitly_requested(false);
        assert_eq!(outcome.status, "dry_run");
        assert!(!outcome.wrote_generation && !outcome.wrote_control);
        match old {
            Some(value) => std::env::set_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY", value),
            None => std::env::remove_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY"),
        }
    }

    #[test]
    fn w2_first_seal_interrupted_after_generation_retries_control_only_fail_closed_until_then() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let approval = controlled_approval('1', Phase2SealControlAction::Seal, &sha, None);

        let interrupted = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = apply_controlled_phase2_for_dir_with_hooks(
                &gov,
                Some(&inputs),
                &approval,
                &sha,
                FIXED_NOW,
                || panic!("simulated crash after generation publication"),
                || {},
            );
        }));
        assert!(interrupted.is_err());
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW).is_err(),
            "a generation without a control must never be consumed as active"
        );
        assert!(
            !evaluate_controlled_phase2_for_dir(&gov, &sha, FIXED_NOW).active_current_build,
            "no premature active consumer success before the control record exists"
        );

        let retry_now = FIXED_NOW + 17;
        let retried =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &approval, &sha, retry_now)
                .expect("later-time retry must append only the missing control");
        assert_eq!(retried.status, "applied_no_contact");
        assert!(!retried.wrote_generation && retried.wrote_control);
        let active = load_current_build_lineage(&gov, &sha, retry_now)
            .unwrap()
            .active
            .expect("recovered generation becomes active only with its control");
        assert_eq!(
            active.artifact.created_at_ms, FIXED_NOW,
            "retry must reuse the persisted generation rather than minting a later-time variant"
        );
    }

    #[test]
    fn w2_supersede_interrupted_after_generation_retries_control_only_without_fork() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let first = controlled_approval('2', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &first, &sha, FIXED_NOW).unwrap();
        let predecessor = load_current_build_lineage(&gov, &sha, FIXED_NOW)
            .unwrap()
            .active
            .unwrap();
        let supersede = controlled_approval(
            '3',
            Phase2SealControlAction::Supersede,
            &sha,
            Some(&predecessor),
        );

        let interrupted = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = apply_controlled_phase2_for_dir_with_hooks(
                &gov,
                Some(&inputs),
                &supersede,
                &sha,
                FIXED_NOW + 1,
                || panic!("simulated crash after supersede generation publication"),
                || {},
            );
        }));
        assert!(interrupted.is_err());
        let before_retry = load_current_build_lineage(&gov, &sha, FIXED_NOW + 1)
            .unwrap()
            .active
            .unwrap();
        assert_eq!(
            before_retry.generation_id, predecessor.generation_id,
            "orphan successor must not become active before its control record"
        );

        let retry_now = FIXED_NOW + 19;
        let retried =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &supersede, &sha, retry_now)
                .expect("later-time supersede retry must append only the missing control");
        assert!(!retried.wrote_generation && retried.wrote_control);
        let active = load_current_build_lineage(&gov, &sha, retry_now)
            .unwrap()
            .active
            .unwrap();
        assert_ne!(active.generation_id, predecessor.generation_id);
        assert_eq!(
            active.artifact.created_at_ms,
            FIXED_NOW + 1,
            "retry must retain the orphan successor's original creation time"
        );
        let generations: Vec<Phase2SealedGenerationV1> = read_current_build_records(
            &gov,
            GENERATIONS_DIRNAME,
            &sha,
            generation_filename_is_valid,
        )
        .unwrap();
        assert_eq!(generations.len(), 2, "recovery must not fork a successor");
    }

    #[test]
    fn w2_ambiguous_post_control_write_retries_as_validated_idempotent_success() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let approval = controlled_approval('4', Phase2SealControlAction::Seal, &sha, None);

        let interrupted = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = apply_controlled_phase2_for_dir_with_hooks(
                &gov,
                Some(&inputs),
                &approval,
                &sha,
                FIXED_NOW,
                || {},
                || panic!("simulated crash after control publication"),
            );
        }));
        assert!(interrupted.is_err());
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW)
                .unwrap()
                .active
                .is_some(),
            "a fully linked control must survive an ambiguous caller outcome"
        );
        let retried =
            apply_controlled_phase2_for_dir(&gov, Some(&inputs), &approval, &sha, FIXED_NOW)
                .expect("retry must verify rather than rewrite the completed pair");
        assert_eq!(retried.status, "already_applied_no_contact");
        assert!(!retried.wrote_generation && !retried.wrote_control);
    }

    #[test]
    fn w2_apply_lock_serializes_sibling_controls_and_is_crash_releasable() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let first = Phase2ApplyLock::try_acquire(&gov).expect("first writer owns lock");
        assert!(
            Phase2ApplyLock::try_acquire(&gov).is_err(),
            "a concurrent/reentrant sibling writer must not observe an unlocked ledger"
        );
        drop(first);
        assert!(
            Phase2ApplyLock::try_acquire(&gov).is_ok(),
            "advisory flock release on fd close is the safe stale-lock recovery"
        );
    }

    #[test]
    fn w2_apply_lock_rejects_inode_swap_without_admitting_a_second_writer() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let first = Phase2ApplyLock::try_acquire(&gov).expect("first writer owns lock");
        let lock_path = gov.join(Phase2ApplyLock::FILENAME);
        let retired = gov.join("retired-phase2-seal-apply.lock");

        // Simulate a same-owner attacker unlinking the locked inode and
        // supplying a fresh, otherwise policy-shaped lock file.  A lock only
        // on `first.file` would let a sibling lock this new inode.
        fs::rename(&lock_path, &retired).unwrap();
        fs::write(&lock_path, b"replacement lock inode").unwrap();
        fs::set_permissions(&lock_path, fs::Permissions::from_mode(0o600)).unwrap();

        assert!(
            first.ensure_bound().is_err(),
            "the original critical section must reject an unlinked/replaced lock"
        );
        assert!(
            Phase2ApplyLock::try_acquire(&gov).is_err(),
            "the inode-bound parent flock must keep a sibling from locking the swapped child"
        );
        drop(first);
        let second = Phase2ApplyLock::try_acquire(&gov)
            .expect("replacement may only become acquirable after first critical section exits");
        second.ensure_bound().unwrap();
    }

    #[test]
    fn w2_apply_rejects_whole_phase2_directory_swap_without_publication() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let approval = controlled_approval('7', Phase2SealControlAction::Seal, &sha, None);
        let retired = gov
            .parent()
            .expect("governance parent")
            .join("retired-ibkr-phase2");
        let replacement = tmp.path().join("replacement-ibkr-phase2");
        fs::create_dir(&replacement).unwrap();
        fs::set_permissions(&replacement, fs::Permissions::from_mode(0o700)).unwrap();

        let result = apply_controlled_phase2_for_dir_with_lock_hook(
            &gov,
            Some(&inputs),
            &approval,
            &sha,
            FIXED_NOW,
            || {
                // The original transaction owns both the old `ibkr_phase2`
                // FD and its governance-parent flock.  A same-owner rename
                // must neither redirect its publication nor admit an
                // independent writer through the replacement pathname.
                fs::rename(&gov, &retired).unwrap();
                fs::rename(&replacement, &gov).unwrap();
                assert!(
                    Phase2ApplyLock::try_acquire(&gov).is_err(),
                    "replacement ibkr_phase2 path must remain serialized by original governance lock"
                );
            },
            || {},
            || {},
        );

        assert!(
            result.is_err(),
            "original transaction must reject a whole ibkr_phase2 directory swap"
        );
        for tree in [&gov, &retired] {
            assert!(
                !tree.join(GENERATIONS_DIRNAME).exists() && !tree.join(CONTROLS_DIRNAME).exists(),
                "directory swap rejection must publish no immutable ledger record"
            );
        }
    }

    #[test]
    fn w2_lineage_uses_one_phase2_dirfd_and_rejects_mixed_tree_composition() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        let approval = controlled_approval('6', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &approval, &sha, FIXED_NOW)
            .expect("create a valid immutable pair before splitting its tree");

        // Split a valid pair so old `ibkr_phase2` holds only generations and a
        // replacement tree holds only matching controls.  A reader which
        // opens the path once for generations and reopens it for controls
        // would wrongly compose an active lineage across two trees.
        let replacement = tmp.path().join("replacement-ibkr-phase2");
        fs::create_dir(&replacement).unwrap();
        fs::set_permissions(&replacement, fs::Permissions::from_mode(0o700)).unwrap();
        fs::rename(
            gov.join(CONTROLS_DIRNAME),
            replacement.join(CONTROLS_DIRNAME),
        )
        .unwrap();
        let phase2_fd = open_secure_phase2_dir(&gov).expect("bind original phase2 tree");
        let retired = tmp.path().join("retired-ibkr-phase2");

        let result = load_current_build_lineage_from_phase2_after_generations(
            &phase2_fd,
            &gov,
            &sha,
            FIXED_NOW,
            || {
                fs::rename(&gov, &retired).unwrap();
                fs::rename(&replacement, &gov).unwrap();
            },
        );
        assert!(
            result.is_err(),
            "generation records from the original FD must not combine with controls from replacement pathname"
        );
        assert!(
            gov.join(CONTROLS_DIRNAME).exists() && !gov.join(GENERATIONS_DIRNAME).exists(),
            "fixture must leave the replacement tree containing controls only"
        );
    }

    #[test]
    fn w2_apply_rejects_malformed_nonunknown_build_sha_without_writes() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let malformed = "malformed-but-not-unknown";
        let inputs = controlled_inputs();
        let approval = controlled_approval('5', Phase2SealControlAction::Seal, malformed, None);
        assert!(apply_controlled_phase2_for_dir(
            &gov,
            Some(&inputs),
            &approval,
            malformed,
            FIXED_NOW,
        )
        .is_err());
        assert!(!gov.join(GENERATIONS_DIRNAME).exists());
        assert!(!gov.join(CONTROLS_DIRNAME).exists());
    }

    /// FIX-1(E2-F1)紅→綠:staggered expiry 不得 brick 帳本。
    /// seal(expiry T1)→ supersede(expiry T2>T1);now∈(T1,T2) 時:
    /// ① lineage load 必須 OK(修前:被 supersede 的祖先 gen1 已過期 → 整鏈 Err);
    /// ② active 世代(gen2)未過期 → gate authority 成立;
    /// ③ now>T2:active 過期 → gate 非 authoritative(consume 側 false),
    ///    但 lineage 照常可 load、supersede 照常可執行(ADR-0048 re-attestation
    ///    via Supersede 不死鎖)。
    #[test]
    fn w2_staggered_expiry_keeps_ledger_operable_and_authority_follows_active_leaf() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        let t1 = FIXED_NOW + 1_000;
        let t2 = FIXED_NOW + 100_000;

        let mut seal = controlled_approval('b', Phase2SealControlAction::Seal, &sha, None);
        seal.expires_at_ms = t1;
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("genesis seal with early expiry");
        let gen1 = load_current_build_lineage(&gov, &sha, FIXED_NOW)
            .unwrap()
            .active
            .expect("active gen1");

        let mut supersede =
            controlled_approval('c', Phase2SealControlAction::Supersede, &sha, Some(&gen1));
        supersede.expires_at_ms = t2;
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &supersede, &sha, FIXED_NOW + 1)
            .expect("supersede with later expiry");

        // ① now ∈ (T1,T2):祖先 gen1 已過期,但 lineage 必須照常 load。
        let mid = t1 + 500;
        let state = load_current_build_lineage(&gov, &sha, mid)
            .expect("expired superseded ancestor must not brick lineage load");
        let gen2 = state.active.clone().expect("gen2 must stay active at mid");
        assert_ne!(gen2.generation_id, gen1.generation_id);
        // ② active 未過期 → consume 側 authority 成立。
        assert!(
            evaluate_controlled_phase2_for_dir(&gov, &sha, mid).active_current_build,
            "unexpired active leaf must remain authoritative despite expired ancestor"
        );

        // ③ now > T2:active 過期 → 非 authoritative,但可 load、可 supersede。
        let late = t2 + 500;
        let state_late = load_current_build_lineage(&gov, &sha, late)
            .expect("expired active leaf must not brick lineage load");
        assert!(
            state_late.active.is_some(),
            "expired active generation must remain replayable for supersede predecessor binding"
        );
        let eval_late = evaluate_controlled_phase2_for_dir(&gov, &sha, late);
        assert!(
            !eval_late.active_current_build,
            "expired active leaf must not be consumed as authoritative (fail-closed)"
        );

        // 續期 supersede 仍可執行(operator 唯一合法解鎖路徑)。
        let mut renew =
            controlled_approval('e', Phase2SealControlAction::Supersede, &sha, Some(&gen2));
        renew.issued_at_ms = late - 1000;
        renew.expires_at_ms = late + 3_600_000;
        let renewed = apply_controlled_phase2_for_dir(&gov, Some(&inputs), &renew, &sha, late)
            .expect("supersede of an expired active leaf must remain executable");
        assert_eq!(renewed.status, "applied_no_contact");
        assert!(
            evaluate_controlled_phase2_for_dir(&gov, &sha, late).active_current_build,
            "renewed generation must restore authority"
        );
    }

    /// FIX-1(E2 驗證點 5)釘死:lineage Err(controls 非空,如 fork)時,即使
    /// 存在一個恰好匹配新 Seal approval 的 orphan generation,apply 也必須拒絕
    /// 且零寫——否則會以空 lineage 假設鑄造第二個 control root,永久 brick 帳本。
    #[test]
    fn w2_apply_rejects_seal_recovery_when_lineage_err_with_nonempty_controls() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        let seal = controlled_approval('f', Phase2SealControlAction::Seal, &sha, None);
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &seal, &sha, FIXED_NOW)
            .expect("genesis seal");
        let state = load_current_build_lineage(&gov, &sha, FIXED_NOW).unwrap();
        let active = state.active.clone().unwrap();

        // 製造 fork:兩筆結構自洽的 control 掛同一 previous_control_hash。
        // 注意:approval_id 契約是 64-hex,fixture 字元必須取自 [0-9a-f],
        // 否則 control 會先敗在 is_sha256_hex(結構無效)而非 fork 檢查。
        let controls_dir = gov.join(CONTROLS_DIRNAME).join(&sha);
        let controls_fd = fs::File::open(&controls_dir).unwrap();
        for approval_char in ['7', '8'] {
            let branch_approval = controlled_approval(
                approval_char,
                Phase2SealControlAction::Revoke,
                &sha,
                Some(&active),
            );
            let branch = build_control_record(
                &branch_approval,
                &control_approval_digest(&branch_approval),
                &active,
                Some(&active),
                state.tail_hash.clone(),
                &sha,
                FIXED_NOW + 1,
            );
            write_immutable_json(
                &controls_fd,
                &format!("{}.control.json", branch.control_id),
                &branch,
            )
            .unwrap();
        }
        assert!(
            load_current_build_lineage(&gov, &sha, FIXED_NOW + 2).is_err(),
            "fixture must brick lineage load via forked controls"
        );

        // 手工放一個匹配「新 Seal approval」的 orphan generation(模擬攻擊者/
        // 誤操作為 Err 帳本鋪好可收養的孤兒)。
        let reseal = controlled_approval('9', Phase2SealControlAction::Seal, &sha, None);
        let digest = control_approval_digest(&reseal);
        let orphan =
            build_controlled_generation(&gov, &inputs, &reseal, &digest, None, &sha, FIXED_NOW + 3)
                .expect("orphan generation fixture");
        let generations_dir = gov.join(GENERATIONS_DIRNAME).join(&sha);
        let generations_fd = fs::File::open(&generations_dir).unwrap();
        write_immutable_json(
            &generations_fd,
            &format!("{}.sealed.json", orphan.generation_id),
            &orphan,
        )
        .unwrap();

        let controls_before = fs::read_dir(&controls_dir).unwrap().count();
        apply_controlled_phase2_for_dir(&gov, Some(&inputs), &reseal, &sha, FIXED_NOW + 4)
            .expect_err("lineage Err with non-empty controls must reject seal recovery");
        let controls_after = fs::read_dir(&controls_dir).unwrap().count();
        assert_eq!(
            controls_before, controls_after,
            "零寫:損壞帳本上不得追加任何 control 記錄(否則鑄造第二 root)"
        );
    }

    /// FIX-2(E3-F1):`/run` 族 tmpfs 前綴必須被 refuse-ephemeral 拒絕。
    #[test]
    fn f3_run_prefixed_data_dir_refused() {
        let _g = crate::test_env_lock::guard();
        let prev = std::env::var("OPENCLAW_DATA_DIR").ok();
        for candidate in [
            "/run/user/1000/x",
            "/var/run/openclaw",
            "/private/var/run/openclaw",
        ] {
            std::env::set_var("OPENCLAW_DATA_DIR", candidate);
            assert!(
                matches!(
                    resolve_phase2_governance_dir(),
                    Err(Phase2SealError::EphemeralDataDir)
                ),
                "tmpfs-backed data dir must be refused: {candidate}"
            );
        }
        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }

    /// FIX-3(E3-F2):相對路徑 DATA_DIR 必拒(cwd 依賴=治理目錄不可再現)。
    #[test]
    fn f3_relative_data_dir_refused() {
        let _g = crate::test_env_lock::guard();
        let prev = std::env::var("OPENCLAW_DATA_DIR").ok();
        for candidate in ["data", "./x", "x/governance"] {
            std::env::set_var("OPENCLAW_DATA_DIR", candidate);
            assert!(
                matches!(
                    resolve_phase2_governance_dir(),
                    Err(Phase2SealError::EphemeralDataDir)
                ),
                "relative data dir must be refused: {candidate}"
            );
        }
        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }

    /// FIX-5(E2-F3)anti-placeholder:repo template 的全同字元 64-hex 指紋
    /// (source_template 的 "a"*64/"b"*64/"c"*64)不得被當作 production seal
    /// inputs 接受——那代表 operator 把 template 原樣抄進了 runtime 目錄。
    #[test]
    fn w2_production_inputs_reject_template_placeholder_fingerprints() {
        // template 原樣值(secret fp="a"*64、account fp="b"*64、topology 對齊)必拒。
        let secret = valid_secret();
        let template_inputs = Phase2SealProductionInputsV1 {
            contract_id: W2_INPUTS_CONTRACT_ID.to_string(),
            source_version: 1,
            policy_bundle: valid_bundle(),
            api_allowlist: valid_allowlist(),
            secret_slot_contract: secret.clone(),
            api_session_topology: matched_topology(&secret),
        };
        assert!(
            !production_inputs_are_valid(&template_inputs),
            "template placeholder fingerprints must be rejected as production inputs"
        );
        // 對照:非 placeholder 的真實形態 64-hex 必過(其餘 leg 不變)。
        assert!(
            production_inputs_are_valid(&controlled_inputs()),
            "non-placeholder fingerprints must remain accepted"
        );
    }

    /// FIX-6(E2-F8)雙閘負測試:cli=true 但 env 缺席/非 literal "1"(含空白、
    /// 換行、"true")→ status=blocked 且零寫。釘死 env 閘不做 trim/寬鬆解析。
    #[test]
    fn w2_apply_env_gate_rejects_missing_and_non_literal_values() {
        let _g = crate::test_env_lock::guard();
        let old = std::env::var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY").ok();

        std::env::remove_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY");
        let missing = phase2_apply_seal_if_explicitly_requested(true);
        assert_eq!(missing.status, "blocked");
        assert!(missing
            .blockers
            .contains(&"OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1_required".to_string()));
        assert!(!missing.wrote_generation && !missing.wrote_control);

        for non_literal in ["true", " 1", "1\n", "1 ", "01", ""] {
            std::env::set_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY", non_literal);
            let outcome = phase2_apply_seal_if_explicitly_requested(true);
            assert_eq!(
                outcome.status, "blocked",
                "non-literal env value must block: {non_literal:?}"
            );
            assert!(
                !outcome.wrote_generation && !outcome.wrote_control,
                "non-literal env value must write nothing: {non_literal:?}"
            );
        }

        match old {
            Some(value) => std::env::set_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY", value),
            None => std::env::remove_var("OPENCLAW_IBKR_PHASE2_SEAL_APPLY"),
        }
    }

    /// FIX-7(E2-F9):generation 與其配對 control 的 approval 綁定
    /// (approval_id/approval_digest/valid_until_ms)必須等值,否則兩份各自
    /// hash 自洽的 0400 記錄可由不同 approval 拼裝(混鏈)。
    #[test]
    fn w2_lineage_rejects_generation_control_approval_binding_mismatch() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();
        // approval_id 契約=64-hex,fixture 字元必須取自 [0-9a-f]。
        let approval = controlled_approval('1', Phase2SealControlAction::Seal, &sha, None);
        let digest = control_approval_digest(&approval);
        let generation =
            build_controlled_generation(&gov, &inputs, &approval, &digest, None, &sha, FIXED_NOW)
                .expect("build genesis generation");
        let control =
            build_control_record(&approval, &digest, &generation, None, None, &sha, FIXED_NOW);
        // 對照組:一致 → Ok(active)。
        assert!(evaluate_current_build_lineage_records(
            &gov,
            &sha,
            FIXED_NOW,
            vec![generation.clone()],
            vec![control.clone()],
        )
        .expect("consistent pair must replay")
        .active
        .is_some());

        // generation 的 approval_id 換成另一合法 64-hex(重算 generation_hash
        // 保持結構自洽)→ 與 control 綁定不等 → 必 Err。
        let mut tampered = generation.clone();
        tampered.approval_id = "9".repeat(64);
        tampered.generation_hash = generation_hash(&tampered);
        assert!(
            evaluate_current_build_lineage_records(
                &gov,
                &sha,
                FIXED_NOW,
                vec![tampered],
                vec![control.clone()],
            )
            .is_err(),
            "generation/control approval_id mismatch must be rejected"
        );

        // valid_until_ms 漂移(結構自洽)同樣必 Err。
        let mut drifted = generation.clone();
        drifted.valid_until_ms += 1;
        drifted.generation_hash = generation_hash(&drifted);
        assert!(
            evaluate_current_build_lineage_records(
                &gov,
                &sha,
                FIXED_NOW,
                vec![drifted],
                vec![control],
            )
            .is_err(),
            "generation/control valid_until_ms mismatch must be rejected"
        );
    }

    /// FIX-7(E2-F9):artifact 自記的 supersedes_artifact_id 必須等於配對
    /// control 的 predecessor_artifact_id,否則 supersession 語義可被拼裝偽造。
    #[test]
    fn w2_lineage_rejects_supersession_binding_mismatch_between_artifact_and_control() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let sha = fake_sha();
        let inputs = controlled_inputs();

        // approval_id 契約=64-hex,fixture 字元必須取自 [0-9a-f]。
        let seal_approval = controlled_approval('2', Phase2SealControlAction::Seal, &sha, None);
        let seal_digest = control_approval_digest(&seal_approval);
        let gen_a = build_controlled_generation(
            &gov,
            &inputs,
            &seal_approval,
            &seal_digest,
            None,
            &sha,
            FIXED_NOW,
        )
        .expect("build genesis generation");
        let control_a = build_control_record(
            &seal_approval,
            &seal_digest,
            &gen_a,
            None,
            None,
            &sha,
            FIXED_NOW,
        );

        let sup_approval =
            controlled_approval('3', Phase2SealControlAction::Supersede, &sha, Some(&gen_a));
        let sup_digest = control_approval_digest(&sup_approval);
        // 故意以 predecessor=None 構造世代 → artifact.supersedes_artifact_id=None,
        // 但 control 卻聲明 predecessor=gen_a → 綁定不等,必 Err。
        let gen_b = build_controlled_generation(
            &gov,
            &inputs,
            &sup_approval,
            &sup_digest,
            None,
            &sha,
            FIXED_NOW + 1,
        )
        .expect("build successor generation without supersedes binding");
        let control_b = build_control_record(
            &sup_approval,
            &sup_digest,
            &gen_b,
            Some(&gen_a),
            Some(control_a.control_hash.clone()),
            &sha,
            FIXED_NOW + 1,
        );
        assert!(
            evaluate_current_build_lineage_records(
                &gov,
                &sha,
                FIXED_NOW + 1,
                vec![gen_a, gen_b],
                vec![control_a, control_b],
            )
            .is_err(),
            "artifact supersedes/control predecessor mismatch must be rejected"
        );
    }
}
