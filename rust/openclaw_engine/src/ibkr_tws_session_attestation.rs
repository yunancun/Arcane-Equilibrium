//! MODULE_NOTE
//! 模塊用途：IBKR **W5-S4 session attestation producer**（IBKR_TODO §5-W5 收口切片）。把
//!   「這是哪個帳戶、是不是 paper、資料新不新鮮」收斂為 typed、可審計的
//!   `IbkrSessionAttestationV1`（openclaw_types 契約,24 欄 30 blocker）。
//! 主要區段：
//!   - (a) `SessionWireFacts`：driver 握手期的 wire 實檢事實（`ManagedAccountsInspection`
//!     + ACK server_version / connection_time_raw + IN 49 server epoch + Ready 轉移點時鐘）。
//!   - (b) `SessionAttestationPosture`：非 wire 派生的姿態輸入（host/port/process identity/
//!     secret-slot 腿指紋/entitlement 姿態/有效期）。W6 接線時 secret-slot 欄必須取自
//!     `ibkr_secret_slot_loader` 真值（同一 sha256 演算法=指紋三角測量的跨腿契約）。
//!   - (c) producer：`produce_session_attestation`（純函數,注入 client 時鐘）+
//!     `blocked_session_attestation`（facts 缺席的 fail-closed 投影;W4 health emitter 消費）。
//! 依賴：`openclaw_types`（契約 + 枚舉）、`ibkr_tws_wire`（`ManagedAccountsInspection`）、
//!   `sha2`/`hex`（raw artifact hash）。**不依賴 `ibkr_tws_driver`**（driver-absence audit
//!   Part B 邊界:本模塊經 health emitter 有 production caller,不得把 driver 拉出 DCE）。
//! 硬邊界：
//!   - **無 socket / 無 I/O / 無 async**：純函數,注入時鐘（now_ms）;wire 事實由 driver 餵。
//!   - **`account_fingerprint_is_live` 禁聲明自填**（operator acceptance 2026-07-12）：
//!     is_live 與 account_fingerprint **只能**由 `ManagedAccountsInspection` 派生——該型別
//!     唯一鑄造點=`managed_accounts_inspect`（decode 邊界內實檢）,posture 輸入面**沒有**
//!     這兩欄,結構上無法聲明。
//!   - **paper_confirmed 未立只可產 Blocked**：facts 缺席（IN 15 缺席/亂序=transient
//!     false-fail）→ `blocked_session_attestation`,絕不以「未見」當「已驗證」。
//!   - **attestation 絕非活化授權**：attested 態只是 typed 會話事實;Phase 2 owner-only
//!     read-only seal 永不是 activation authority（AMD-2026-07-11-01;真活化=W8
//!     `ibkr_activation_envelope_v1`）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 types 契約。

// intentional-DCE 姿態沿 wire/session（見 MODULE_NOTE）:本模塊 production caller=W4 health
// emitter 的 `blocked_session_attestation`;attested 全路徑真消費者=driver 測試域,W6 IPC
// 投影接真消費。
#![allow(dead_code)]

use std::time::Duration;

use sha2::{Digest, Sha256};

use openclaw_types::{
    BrokerEnvironment, IbkrGatewayMode, IbkrSecretSlotMode, IbkrSessionAttestationStatus,
    IbkrSessionAttestationV1, IbkrSessionDataTier, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
};

use crate::ibkr_tws_wire::ManagedAccountsInspection;

// ===========================================================================
// (a) wire 實檢事實（driver 握手期收集;attestation 的唯一 wire 輸入）
// ===========================================================================

/// driver 一次握手的 wire 實檢事實。`inspection` 是 is_live/fingerprint 的**唯一來源**
/// （構造子在 wire decode 邊界,禁聲明自填）;非 paper fatal 早於 IN 49/Ready →
/// `server_epoch_s`/`ready_at_ms` 為 `None`（producer 據此只可產 Blocked）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SessionWireFacts {
    /// managedAccounts(15) 實檢產物（all_paper + 帳戶指紋;明文已在 decode 邊界 drop）。
    pub(crate) inspection: ManagedAccountsInspection,
    /// 握手 ACK 的 serverVersion。
    pub(crate) server_version: i32,
    /// 握手 ACK 的 connectionTime 原文（raw artifact 佐證欄;非帳戶資訊）。
    pub(crate) connection_time_raw: String,
    /// IN 49 server epoch 秒（**僅作 raw artifact 內 skew 佐證,不作權威時鐘**;IB 現勘
    /// 2026-07-17）。非 paper fatal 早於 49 → `None`。
    pub(crate) server_epoch_s: Option<i64>,
    /// Ready 轉移點的 driver 注入時鐘 ms（→ `gateway_started_at_ms`）。未到 Ready → `None`。
    pub(crate) ready_at_ms: Option<u64>,
}

// ===========================================================================
// (b) 姿態輸入（非 wire 派生欄;W6 接線時 secret-slot 腿取 loader 真值）
// ===========================================================================

/// attestation 的非 wire 姿態輸入。**刻意沒有** `account_fingerprint`/
/// `account_fingerprint_is_live` 欄——該二欄只能由 `SessionWireFacts::inspection` 派生
/// （operator acceptance 2026-07-12 的結構性落實）。
///
/// secret-slot 三欄（fingerprint/mode/world_readable）與 `live_secret_absent_or_empty` 是
/// 指紋三角測量的 secret-slot 腿:W6 IPC 投影接真消費時**必須**取
/// `ibkr_secret_slot_loader::ibkr_secret_slot_contract()` 真值,禁 fixture 冒充。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SessionAttestationPosture {
    pub(crate) host: String,
    pub(crate) port: u16,
    pub(crate) process_identity: String,
    pub(crate) environment: BrokerEnvironment,
    pub(crate) gateway_mode: IbkrGatewayMode,
    pub(crate) secret_slot_fingerprint: String,
    pub(crate) secret_slot_mode: IbkrSecretSlotMode,
    pub(crate) secret_world_readable: bool,
    pub(crate) live_secret_absent_or_empty: bool,
    pub(crate) env_var_credential_fallback_used: bool,
    pub(crate) data_tier: IbkrSessionDataTier,
    pub(crate) entitlements_fingerprint: String,
    pub(crate) market_data_entitlement_purchase_denied: bool,
    /// attestation 有效期（`expires_at_ms = attested_at_ms + validity`;時效綁定令舊會話
    /// 事實無法永久復用,契約 `StaleAttestation` blocker 收口）。
    pub(crate) validity: Duration,
}

// ===========================================================================
// (c) producer（純函數;validate 全綠才產 attested 態,否則 Blocked）
// ===========================================================================

/// raw artifact 正文（決定性重建面:connection_time_raw 原文 + IN 49 epoch + serverVersion;
/// 供 `raw_artifact_hash` 與測試重算對齊。不含任何帳戶明文/指紋——帳戶軸由
/// `account_fingerprint` 欄獨立承載）。
pub(crate) fn session_raw_artifact(facts: &SessionWireFacts) -> String {
    format!(
        "ibkr_session_attestation_raw_v1\nconnection_time_raw={}\nserver_epoch_s={}\nserver_version={}\n",
        facts.connection_time_raw,
        facts
            .server_epoch_s
            .map(|e| e.to_string())
            .unwrap_or_else(|| "absent".to_string()),
        facts.server_version,
    )
}

fn session_raw_artifact_hash(facts: &SessionWireFacts) -> String {
    let mut hasher = Sha256::new();
    hasher.update(session_raw_artifact(facts).as_bytes());
    hex::encode(hasher.finalize())
}

/// facts 缺席的 fail-closed 投影：contract_id/source_version 立正身,其餘欄保守默認,
/// status=Blocked。為什麼獨立函數：W4 health emitter（inactive 引擎,無 wire facts）由此
/// 真值餵 `attestation_status`/`account_fingerprint_is_live`——同一 producer 代碼路徑,
/// 非硬編聲明;is_live=false 在 Blocked 態承載「未實檢」而非「已證非 live」。
pub(crate) fn blocked_session_attestation() -> IbkrSessionAttestationV1 {
    IbkrSessionAttestationV1 {
        contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string(),
        source_version: 1,
        status: IbkrSessionAttestationStatus::Blocked,
        ..IbkrSessionAttestationV1::default()
    }
}

/// 產一份 session attestation：
///   - `facts` 缺席（paper_confirmed 未立:IN 15 缺席/亂序 → driver transient false-fail）
///     → 只可產 Blocked（絕不以未見當已驗證）。
///   - `facts` 在場：`account_fingerprint`/`account_fingerprint_is_live` **由實檢派生**
///     （is_live = !all_paper;DU* 白名單外一律當 live）;`attested_at_ms`=注入 client 時鐘,
///     `gateway_started_at_ms`=Ready 轉移點時鐘,raw artifact hash 見上。候選經契約
///     `validate(now_ms)` **全綠才保留 attested 態**,任一 blocker → status 覆為 Blocked
///     （欄位保留真觀測值供審計,重 validate 必然再拒=fail-closed 自洽）。
pub(crate) fn produce_session_attestation(
    facts: Option<&SessionWireFacts>,
    posture: &SessionAttestationPosture,
    now_ms: u64,
) -> IbkrSessionAttestationV1 {
    let facts = match facts {
        Some(f) => f,
        None => return blocked_session_attestation(),
    };
    // is_live 唯一派生點：非全 DU（含空 token/表外前綴）= live 語義（白名單非黑名單）。
    let account_fingerprint_is_live = !facts.inspection.all_paper();
    let status = match posture.environment {
        BrokerEnvironment::Paper => IbkrSessionAttestationStatus::PaperAttested,
        BrokerEnvironment::ReadOnly => IbkrSessionAttestationStatus::ReadonlyAttested,
        // shadow/live 姿態不在本 producer 的可 attest 域（W8 活化軸另議）→ Blocked。
        _ => IbkrSessionAttestationStatus::Blocked,
    };
    let mut attestation = IbkrSessionAttestationV1 {
        contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string(),
        source_version: 1,
        status,
        account_fingerprint: facts.inspection.fingerprint_hex(),
        account_fingerprint_is_live,
        environment: posture.environment,
        host: posture.host.clone(),
        port: posture.port,
        process_identity: posture.process_identity.clone(),
        gateway_mode: posture.gateway_mode,
        secret_slot_fingerprint: posture.secret_slot_fingerprint.clone(),
        secret_slot_mode: posture.secret_slot_mode,
        secret_world_readable: posture.secret_world_readable,
        live_secret_absent_or_empty: posture.live_secret_absent_or_empty,
        env_var_credential_fallback_used: posture.env_var_credential_fallback_used,
        api_server_version: format!("tws_server_v{}", facts.server_version),
        data_tier: posture.data_tier,
        entitlements_fingerprint: posture.entitlements_fingerprint.clone(),
        market_data_entitlement_purchase_denied: posture.market_data_entitlement_purchase_denied,
        // 未到 Ready → 0 → 契約 MissingGatewayStartupTime blocker（fail-closed,不捏時刻）。
        gateway_started_at_ms: facts.ready_at_ms.unwrap_or(0),
        attested_at_ms: now_ms,
        expires_at_ms: now_ms.saturating_add(posture.validity.as_millis() as u64),
        raw_artifact_hash: session_raw_artifact_hash(facts),
    };
    // validate 全綠才產 attested 態;任一 blocker → Blocked（真觀測值保留供審計）。
    if !attestation.validate(now_ms).attestation_accepted {
        attestation.status = IbkrSessionAttestationStatus::Blocked;
    }
    attestation
}

// ===========================================================================
// 測試（synthetic;fixture 全相對時鐘,禁硬編當前日期）
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    use openclaw_types::{IbkrSessionAttestationBlocker, IBKR_PAPER_GATEWAY_DEFAULT_PORT};

    use crate::ibkr_tws_wire::{encode_fields, managed_accounts_inspect};

    /// paper 姿態 fixture（對齊契約 `paper_fixture` 的可過 validate 值;validity=1h）。
    fn paper_posture() -> SessionAttestationPosture {
        SessionAttestationPosture {
            host: "127.0.0.1".to_string(),
            port: IBKR_PAPER_GATEWAY_DEFAULT_PORT,
            process_identity: "test:ibgateway-paper".to_string(),
            environment: BrokerEnvironment::Paper,
            gateway_mode: IbkrGatewayMode::Paper,
            secret_slot_fingerprint: "a".repeat(64),
            secret_slot_mode: IbkrSecretSlotMode::Paper,
            secret_world_readable: false,
            live_secret_absent_or_empty: true,
            env_var_credential_fallback_used: false,
            data_tier: IbkrSessionDataTier::Delayed,
            entitlements_fingerprint: "c".repeat(64),
            market_data_entitlement_purchase_denied: true,
            validity: Duration::from_secs(3600),
        }
    }

    /// wire facts fixture：經真實 decode 邊界鑄 inspection（唯一鑄造點,非手搓）。
    fn facts_for(csv: &str) -> SessionWireFacts {
        let payload = encode_fields(&["15", "1", csv]);
        SessionWireFacts {
            inspection: managed_accounts_inspect(&payload).unwrap(),
            server_version: 176,
            connection_time_raw: "20260101 09:30:00 EST".to_string(),
            server_epoch_s: Some(1_700_000_000),
            ready_at_ms: Some(1_000),
        }
    }

    #[test]
    fn all_paper_facts_produce_attested_full_green() {
        let att =
            produce_session_attestation(Some(&facts_for("DU1234567")), &paper_posture(), 2_000);
        assert_eq!(att.status, IbkrSessionAttestationStatus::PaperAttested);
        assert!(!att.account_fingerprint_is_live);
        let v = att.validate(2_000);
        assert!(v.attestation_accepted, "blockers: {:?}", v.blockers);
        assert_eq!(att.gateway_started_at_ms, 1_000);
        assert_eq!(att.attested_at_ms, 2_000);
        assert_eq!(att.expires_at_ms, 2_000 + 3_600_000);
        assert_eq!(att.api_server_version, "tws_server_v176");
    }

    #[test]
    fn facts_absent_only_blocked() {
        // paper_confirmed 未立（IN 15 缺席/亂序）→ 只可產 Blocked,絕不以未見當已驗證。
        let att = produce_session_attestation(None, &paper_posture(), 2_000);
        assert_eq!(att.status, IbkrSessionAttestationStatus::Blocked);
        assert!(!att.account_fingerprint_is_live);
        let v = att.validate(2_000);
        assert!(!v.attestation_accepted);
        assert!(v
            .blockers
            .contains(&IbkrSessionAttestationBlocker::StatusBlocked));
    }

    #[test]
    fn non_paper_inspection_derives_is_live_and_blocks() {
        // 混入 U*（live 前綴）→ is_live 由實檢派生為 true → LiveAccountFingerprint → Blocked。
        let att = produce_session_attestation(
            Some(&facts_for("DU1234567,U7654321")),
            &paper_posture(),
            2_000,
        );
        assert!(att.account_fingerprint_is_live);
        assert_eq!(att.status, IbkrSessionAttestationStatus::Blocked);
        assert!(att
            .validate(2_000)
            .blockers
            .contains(&IbkrSessionAttestationBlocker::LiveAccountFingerprint));
    }

    #[test]
    fn missing_ready_time_blocks() {
        // 有實檢但未到 Ready（ready_at_ms=None）→ MissingGatewayStartupTime → Blocked。
        let mut facts = facts_for("DU1234567");
        facts.ready_at_ms = None;
        let att = produce_session_attestation(Some(&facts), &paper_posture(), 2_000);
        assert_eq!(att.status, IbkrSessionAttestationStatus::Blocked);
        assert!(att
            .validate(2_000)
            .blockers
            .contains(&IbkrSessionAttestationBlocker::MissingGatewayStartupTime));
    }

    #[test]
    fn expired_attestation_hits_stale_blocker() {
        // 產出時綠;時鐘推過 expires → 契約 StaleAttestation blocker（時效綁定收口）。
        let att =
            produce_session_attestation(Some(&facts_for("DU1234567")), &paper_posture(), 2_000);
        assert!(att.validate(2_000).attestation_accepted);
        let later = att.expires_at_ms; // now >= expires 即 stale
        assert!(att
            .validate(later)
            .blockers
            .contains(&IbkrSessionAttestationBlocker::StaleAttestation));
    }

    #[test]
    fn raw_artifact_hash_is_deterministic_and_input_bound() {
        let f1 = facts_for("DU1234567");
        let att1 = produce_session_attestation(Some(&f1), &paper_posture(), 2_000);
        // 64 hex 非零 + 可由 artifact 正文重算。
        assert_eq!(att1.raw_artifact_hash.len(), 64);
        assert_ne!(att1.raw_artifact_hash, "0".repeat(64));
        let mut h = Sha256::new();
        h.update(session_raw_artifact(&f1).as_bytes());
        assert_eq!(att1.raw_artifact_hash, hex::encode(h.finalize()));
        // epoch 佐證欄變 → hash 變（真綁 IN 49 輸入）。
        let mut f2 = f1.clone();
        f2.server_epoch_s = Some(1_700_000_001);
        let att2 = produce_session_attestation(Some(&f2), &paper_posture(), 2_000);
        assert_ne!(att1.raw_artifact_hash, att2.raw_artifact_hash);
    }

    #[test]
    fn blocked_projection_matches_contract_identity() {
        // W4 health emitter 消費面：contract 身分立正,狀態恆 Blocked / is_live=false。
        let att = blocked_session_attestation();
        assert_eq!(att.contract_id, IBKR_SESSION_ATTESTATION_CONTRACT_ID);
        assert_eq!(att.source_version, 1);
        assert_eq!(att.status, IbkrSessionAttestationStatus::Blocked);
        assert!(!att.account_fingerprint_is_live);
        assert!(!att.validate(0).attestation_accepted);
    }

    #[test]
    fn readonly_environment_maps_to_readonly_attested() {
        let mut posture = paper_posture();
        posture.environment = BrokerEnvironment::ReadOnly;
        posture.gateway_mode = IbkrGatewayMode::ReadOnly;
        posture.secret_slot_mode = IbkrSecretSlotMode::ReadOnly;
        let att = produce_session_attestation(Some(&facts_for("DU1234567")), &posture, 2_000);
        assert_eq!(att.status, IbkrSessionAttestationStatus::ReadonlyAttested);
        assert!(att.validate(2_000).attestation_accepted);
    }
}
