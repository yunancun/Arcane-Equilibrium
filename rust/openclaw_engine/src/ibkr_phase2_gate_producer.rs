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
//! 依賴：`openclaw_types`（消費既有 4 個 `ibkr_phase2_*` 型別，**不改型別 crate**）、
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
    IBKR_PHASE2_ADR, IBKR_PHASE2_AMD,
};

use crate::boot_observability::BUILD_GIT_SHA;

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

/// approval 引的 **contact-授權** AMD（≠ artifact 的 shape-AMD `IBKR_PHASE2_AMD`
/// = 06-29-01）。finding-2：兩軸不可混——approval 是「授權首次接觸」（07-08-01），
/// shape 是「artifact 型別世代」（06-29-01）。硬編 shape-AMD 到 approval 會誤放行。
const PHASE2_CONTACT_AMD: &str = "AMD-2026-07-08-01";

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
        && a.amd == PHASE2_CONTACT_AMD
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
    Sealed { path: PathBuf },
    AlreadySealed { path: PathBuf },
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
/// 為什麼 approval-lineage 不另立欄位（finding-2）：型別 crate 凍結、不得加欄位；
/// approval 綁定事實已鏡射進 artifact 的 `adr`/`source_commit`/`reviewer_roles`，
/// 三者皆落在本 raw hash 覆蓋域內 → 竄改任一即 hash 不符（tamper-evident lineage）；
/// 且 raw hash 只依賴 artifact 自身，令 `seal(artifact, gov_dir)` 與磁碟 re-verify
/// 皆自洽、無需重讀 approval 檔（見 report 偏差說明）。
// TODO(finding-2, IBKR-P2-SEAL-LINEAGE-FIELDS): 當前以鏡射 adr/source_commit/
// reviewer_roles 進 raw-hash 作 proxy lineage；完整 tamper-evident lineage（嵌
// approval-content-hash + 自記 contact AMD）待上述 ticket 給 artifact 型別加欄後閉合。
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
    })
}

fn compute_redacted_summary_hash(a: &IbkrPhase2GateArtifactV1) -> String {
    let json = serde_json::to_string(&redacted_summary_value(a)).unwrap_or_default();
    sha256_hex(json.as_bytes())
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
/// - `reviewer_roles`：approval 有效 → 綁定其 roles（含 PM+Operator）；否則 `[]`
///   （absent/無效 → validate `OperatorReviewerMissing` → 不 seal）。producer 絕不
///   自注 "Operator"。
/// - `api_session_topology.account_fingerprint_hash` 覆寫為 secret leg 的 hash
///   （跨腿對齊；triangulation 由 seal / outcome enforce，types 不 cross-check）。
/// - 兩 hash 於組裝末尾計算（覆蓋所有實質欄位）。
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

    // 跨腿指紋對齊：topology 的 account_fingerprint_hash 覆寫為 secret leg 之值。
    // TODO(finding-1, IBKR-P2-TRIANGULATION-CROSSCHECK): 此無條件覆寫使 triangulation
    // 現恒真（topology 恒 source_template 故 dormant、零 runtime 效果）。在 {P5
    // topology/session-attestation 成獨立 account 源} 與 {production-seal-wiring} 二者
    // 較早者，必須移除此覆寫，改為兩獨立真值源的真 equality cross-check
    // (secret.account_fingerprint_hash == topology.account_fingerprint_hash)。
    let mut topo = topology.clone();
    topo.account_fingerprint_hash = secret_contract.account_fingerprint_hash.clone();

    // approval A-model：僅在 6 綁定全過時綁定 reviewer_roles（含 Operator）。
    let approval_valid = approval
        .map(|a| approval_is_valid(a, now_ms, source_commit))
        .unwrap_or(false);
    let reviewer_roles = if approval_valid {
        approval.map(|a| a.reviewer_roles.clone()).unwrap_or_default()
    } else {
        Vec::new()
    };

    let mut artifact = IbkrPhase2GateArtifactV1 {
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
        artifact_id: PHASE2_ARTIFACT_ID.to_string(),
        adr: IBKR_PHASE2_ADR.to_string(),
        // shape-AMD 06-29-01（≠ approval 的 contact-AMD 07-08-01；finding-2 兩軸）。
        // TODO(finding-2, IBKR-P2-SEAL-LINEAGE-FIELDS): sealed 檔目前只自記 shape-AMD
        // (06-29-01)；contact-授權 AMD(07-08-01) 僅存在於 report 面 + approval seal-time
        // 閘，未入凍結的 artifact 型別。在任何 production caller 真正 invoke seal 之前，
        // 必須先給 IbkrPhase2GateArtifactV1 加 contact_authorization_amd +
        // approval_lineage_hash 兩欄（走 PA→E1→E2→E4，types crate 改動）。
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
        supersedes_artifact_id: None,
    };
    artifact.raw_artifact_hash = compute_raw_artifact_hash(&artifact);
    artifact.redacted_summary_hash = compute_redacted_summary_hash(&artifact);
    artifact
}

/// finding-1（producer enforce，types 不 cross-check）：secret leg 與 topology 的
/// account_fingerprint_hash 必相等且非空。不等 → 拒 seal。
fn account_fingerprint_triangulation_ok(a: &IbkrPhase2GateArtifactV1) -> bool {
    let secret_fp = &a.secret_slot_contract.account_fingerprint_hash;
    !secret_fp.is_empty() && *secret_fp == a.api_session_topology.account_fingerprint_hash
}

/// post-seal 磁碟 re-verify（design 命名）：讀 `artifact.immutable_storage_path`、解析、
/// 與傳入 artifact 全等（含 path 欄位）、hash 自洽、且 `validate()` 放行。
fn verify_sealed_artifact(artifact: &IbkrPhase2GateArtifactV1) -> bool {
    let path = Path::new(&artifact.immutable_storage_path);
    let raw = match std::fs::read_to_string(path) {
        Ok(r) => r,
        Err(_) => return false,
    };
    let on_disk: IbkrPhase2GateArtifactV1 = match serde_json::from_str(&raw) {
        Ok(a) => a,
        Err(_) => return false,
    };
    &on_disk == artifact
        && verify_artifact_hashes(&on_disk)
        && on_disk.validate().ibkr_contact_allowed
}

/// precontact / summary 用的磁碟 re-verify（path-first，含 anti-relocation）。
fn reverify_sealed_artifact_at(path: &Path) -> bool {
    let raw = match std::fs::read_to_string(path) {
        Ok(r) => r,
        Err(_) => return false,
    };
    let artifact: IbkrPhase2GateArtifactV1 = match serde_json::from_str(&raw) {
        Ok(a) => a,
        Err(_) => return false,
    };
    // anti-relocation：磁碟聲明的 path 必等於實際讀取的 path（防搬檔偽造 PASS）。
    if artifact.immutable_storage_path != path.to_string_lossy().into_owned() {
        return false;
    }
    verify_artifact_hashes(&artifact) && artifact.validate().ibkr_contact_allowed
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

/// gov_dir 與其父 `governance/` 皆須 mode==0o700 且 owner==euid（bind #1 祖先鏈）。
/// 用 lstat：symlink 祖先的 mode 不會是 0o700 → 自然 fail-closed。
#[cfg(unix)]
fn check_dir_pair_owner_only(gov_dir: &Path) -> Result<(), String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let euid = unsafe { libc::geteuid() } as u32;
    for dir in [Some(gov_dir), gov_dir.parent()] {
        let path = dir.ok_or_else(|| "gov_dir has no parent (governance) dir".to_string())?;
        let meta = std::fs::symlink_metadata(path)
            .map_err(|e| format!("gov ancestor stat {} failed: {e}", path.display()))?;
        if (meta.permissions().mode() & 0o777) != 0o700 {
            return Err(format!(
                "gov ancestor not 0o700: {} mode={:#o}",
                path.display(),
                meta.permissions().mode() & 0o777
            ));
        }
        if meta.uid() as u32 != euid {
            return Err(format!("gov ancestor not owned by euid: {}", path.display()));
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
        return Err(format!("approval file is symlink (denied): {}", path.display()));
    }
    if !meta.is_file() {
        return Err(format!("approval path is not a regular file: {}", path.display()));
    }
    let euid = unsafe { libc::geteuid() } as u32;
    if (meta.permissions().mode() & 0o777) != 0o600 {
        return Err(format!("approval file not 0o600: {}", path.display()));
    }
    if meta.uid() as u32 != euid {
        return Err(format!("approval file not owned by euid: {}", path.display()));
    }
    // bind #1：0o700 祖先鏈。
    check_dir_pair_owner_only(gov_dir)?;

    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read approval {} failed: {e}", path.display()))?;
    let approval: Phase2SealApproval =
        toml::from_str(&raw).map_err(|e| format!("parse approval {} failed: {e}", path.display()))?;
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
        .map_err(|e| Phase2SealError::IoError(format!("create gov_dir {} failed: {e}", gov_dir.display())))?;
    // 寫前驗 owner-only（既有目錄權限過寬即 Err）。
    check_dir_pair_owner_only(gov_dir).map_err(Phase2SealError::IoError)?;

    // write-once：唯一 tmp（pid.nanos）→ create_new → sync_all。
    let tmp_path = gov_dir.join(format!("{SEALED_FILENAME}.{}.{}.tmp", std::process::id(), now_ns()));
    let json = serde_json::to_string_pretty(artifact)
        .map_err(|e| Phase2SealError::IoError(format!("serialize artifact failed: {e}")))?;
    {
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&tmp_path)
            .map_err(|e| Phase2SealError::IoError(format!("create_new tmp {} failed: {e}", tmp_path.display())))?;
        f.write_all(json.as_bytes())
            .map_err(|e| Phase2SealError::IoError(format!("write tmp {} failed: {e}", tmp_path.display())))?;
        f.flush()
            .map_err(|e| Phase2SealError::IoError(format!("flush tmp {} failed: {e}", tmp_path.display())))?;
        f.sync_all()
            .map_err(|e| Phase2SealError::IoError(format!("sync_all tmp {} failed: {e}", tmp_path.display())))?;
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
    std::fs::set_permissions(&final_path, std::fs::Permissions::from_mode(0o400))
        .map_err(|e| Phase2SealError::IoError(format!("chmod final {} failed: {e}", final_path.display())))?;
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
        Phase2ProducerOutcome::Sealed { path } => {
            ("sealed", Vec::new(), None, Some(path.to_string_lossy().into_owned()))
        }
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
        "contact_authorization_amd": PHASE2_CONTACT_AMD,
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

    fn direct_approval(now: u64, sha: &str) -> Phase2SealApproval {
        Phase2SealApproval {
            adr: "ADR-0048".to_string(),
            amd: "AMD-2026-07-08-01".to_string(),
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
    fn build_full_green(gov: &Path) -> IbkrPhase2GateArtifactV1 {
        let sha = fake_sha();
        let approval = direct_approval(FIXED_NOW, &sha);
        let path = gov.join(SEALED_FILENAME).to_string_lossy().into_owned();
        build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &valid_secret(),
            &valid_topology(),
            Some(&approval),
            &path,
            &sha,
            FIXED_NOW,
        )
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
        assert!(v.ibkr_contact_allowed, "unexpected blockers: {:?}", v.blockers);
        assert!(verify_artifact_hashes(&artifact));

        let sealed = seal_phase2_artifact(&artifact, &gov).expect("seal ok");
        let mode = fs::symlink_metadata(&sealed).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o400, "sealed file must be read-only 0o400");
        assert!(verify_sealed_artifact(&artifact), "post-seal disk re-verify must pass");
        assert!(reverify_sealed_artifact_at(&sealed));
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
        assert_eq!(bytes1, bytes2, "original sealed file must be byte-identical");
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
        assert!(!gov.join(SEALED_FILENAME).exists(), "no sealed file must be written");
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
        assert!(artifact.validate().blockers.contains(&B::IbkrCallAlreadyPerformed));
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
        assert!(artifact.validate().blockers.contains(&B::OperatorReviewerMissing));
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
        let artifact = build_phase2_artifact_candidate(
            &valid_bundle(),
            &valid_allowlist(),
            &valid_secret(),
            &valid_topology(),
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
        assert!(v.accepted, "real policies bundle rejected: {:?}", v.blockers);
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

    // --- 補: verify_sealed_artifact 抓磁碟竄改（parse 後欄位不符）---
    #[test]
    fn verify_sealed_detects_ondisk_tamper() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let artifact = build_full_green(&gov);
        let sealed = seal_phase2_artifact(&artifact, &gov).unwrap();
        assert!(verify_sealed_artifact(&artifact));

        // 竄改磁碟檔（先放寬 0o400 → 改 source_commit → 回寫）。
        fs::set_permissions(&sealed, fs::Permissions::from_mode(0o600)).unwrap();
        let mut on_disk: IbkrPhase2GateArtifactV1 =
            serde_json::from_str(&fs::read_to_string(&sealed).unwrap()).unwrap();
        on_disk.source_commit = "tampered".to_string();
        fs::write(&sealed, serde_json::to_string_pretty(&on_disk).unwrap()).unwrap();

        assert!(
            !verify_sealed_artifact(&artifact),
            "on-disk tamper must fail re-verify"
        );
        assert!(!reverify_sealed_artifact_at(&sealed));
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
        assert_eq!(s["contact_authorization_amd"], PHASE2_CONTACT_AMD);
        assert_eq!(s["artifact_shape_amd"], IBKR_PHASE2_AMD);
        assert!(s["blockers"].as_array().is_some());

        match prev {
            Some(v) => std::env::set_var("OPENCLAW_DATA_DIR", v),
            None => std::env::remove_var("OPENCLAW_DATA_DIR"),
        }
    }
}
