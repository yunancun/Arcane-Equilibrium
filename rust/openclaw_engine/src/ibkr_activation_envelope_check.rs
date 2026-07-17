//! MODULE_NOTE
//! 模塊用途：IBKR **W8a activation envelope 驗證器（readonly-scope 最小切片）**
//!   （IBKR_TODO §5-W8a;AMD-2026-07-11-01 活化鐵律的 engine 消費面）。把 types 契約
//!   `IbkrActivationEnvelopeV1` 的 shape 校驗接上 runtime 姿態綁定:build SHA 比對、
//!   revocation/kill-switch epoch 比對、operation verb 白名單、seal≠活化、nonce 原子消費。
//! 主要區段：
//!   - (a) `ActivationCheckPosture`：注入的當前姿態（now_ms/現 binary BUILD_GIT_SHA/
//!     當前兩 epoch/Phase-2 seal 在位事實）。純資料,零 IO——姿態由呼叫端供給。
//!   - (b) `ActivationNonceLedger`：nonce **原子消費**帳本（Mutex<HashSet> 單鎖插入=
//!     消費判定原子;同 nonce 二次消費必拒=防 replay）。
//!   - (c) `check_readonly_contact`：唯一裁決入口——**先寫拒絕路徑**,blocker 全累積,
//!     nonce 只在全部綁定通過後才消費（deny path 永不燒 nonce）。
//! 依賴：`openclaw_types`（envelope 契約 + `BrokerOperation`）、`std::sync::Mutex`。
//! 硬邊界：
//!   - **只驗不發**：本模塊不存在任何 envelope 簽發/構造/簽名路徑——簽發與活化是 EA
//!     跑道的 authenticated Operator 動作（W8 option B 合流）;這裡只消費既存 envelope。
//!   - **seal 共路徑（W2 原則）**：`phase2_seal_present` 必須取自唯一 production seal
//!     消費點 `ibkr_phase2_gate_producer::phase2_immutable_pass_artifact_present()`;本
//!     模塊**刻意不**自行讀磁碟/env——禁止出現第二套 seal 讀取語義（語義漂移=審計盲點）。
//!     「seal 在位而 envelope 缺席 → 拒」是 seal≠活化的機器證明（AMD-07-11:Phase 2
//!     owner-only read-only seal 永不是 activation authority）。
//!   - **readonly scope 的 order verb 結構性拒**：任何 order verb（paper submit/cancel/
//!     replace、live submit、margin/short、options/cfd、transfer/account write）在
//!     readonly envelope 下**無條件**拒——不看 limits、不看 epoch、不看簽發者。
//!   - **INV-1 不受影響（dormant/DCE 姿態,同 attestation 模組）**：本模塊零 production
//!     caller（驗證器存在 ≠ 有 caller）;**不** impl `ConnectPermitProvider`、**不**觸碰
//!     `PermitToken`——production connect 路徑仍恆撞 `EnvelopeRequiredStub`。W8 全包以本
//!     驗證器替換該 trait 位並吸收本切片（**共用同一驗證代碼路徑,禁兩套語義漂移**——同
//!     W2「caller 與 consume 共路徑」原則）;在此之前 production 域零活化路徑不變。
//!   - **reconnect / scope 變更 = 重新活化**：nonce 單次消費使一份 envelope 至多支撐一次
//!     接觸授權;斷線重連或 scope 變更必須換新 envelope（新 nonce）,無「續用舊授權」路徑。
//!   - **移交契約（E2-F1）**：本入口=**活化時刻**裁決;per-operation 續用語義歸 W8 的
//!     session-scoped activated 態,**禁以重複呼叫本入口實作 per-operation 檢查**
//!     （第二次呼叫必 `NonceAlreadyConsumed`）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 IPC。

// dormant 姿態（同 ibkr_tws_session_attestation）:W8a 期本模塊零 production caller,
// 全部消費者在測試域;W8 接真 ConnectPermitProvider 位時移出。
#![allow(dead_code)]

use std::collections::HashSet;
use std::sync::Mutex;

use openclaw_types::{BrokerOperation, IbkrActivationEnvelopeBlocker, IbkrActivationEnvelopeV1};

// ===========================================================================
// (a) 注入姿態（呼叫端供給;本模塊零 IO/零 env/零時鐘）
// ===========================================================================

/// 活化裁決所需的當前 runtime 姿態。全部由呼叫端注入:
/// - `current_build_git_sha`：現 binary 的 `BUILD_GIT_SHA`（envelope 綁死精確 build）。
/// - `current_revocation_epoch` / `current_kill_switch_epoch`：當前全域 epoch——envelope
///   綁定值**必須相等**（落後=已被撤銷/kill,超前=偽造或時序錯亂,兩向皆 fail-closed 拒）。
/// - `phase2_seal_present`：Phase-2 sealed PASS artifact 在位事實——**只能**取自
///   `phase2_immutable_pass_artifact_present()`（唯一 production seal 消費點,見 MODULE_NOTE）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ActivationCheckPosture {
    pub(crate) now_ms: u64,
    pub(crate) current_build_git_sha: String,
    pub(crate) current_revocation_epoch: u64,
    pub(crate) current_kill_switch_epoch: u64,
    pub(crate) phase2_seal_present: bool,
}

// ===========================================================================
// (b) nonce 原子消費帳本（防 replay;單鎖插入=消費判定原子）
// ===========================================================================

/// activation nonce 消費帳本。**原子消費**:`try_consume` 在單一 Mutex 臨界區內完成
/// 「查已消費 + 記消費」——併發下同 nonce 恰一個呼叫者取得消費權,其餘必拒（防 replay）。
/// 帳本只增不減:W8a 無任何清除/重置路徑（envelope 過期不歸還 nonce——一次性語義）。
/// **in-memory 易失（CC-NOTE-1）**:引擎重啟即遺忘已消費 nonce（重啟=重新活化語義,
/// 舊 envelope 仍受 expiry/epoch 綁定約束）;durable 消費紀錄歸 W8 吸收 blocking。
pub(crate) struct ActivationNonceLedger {
    consumed: Mutex<HashSet<String>>,
}

impl ActivationNonceLedger {
    pub(crate) fn new() -> Self {
        Self {
            consumed: Mutex::new(HashSet::new()),
        }
    }

    /// 原子消費:首次消費回 `true`;同 nonce 再消費恆 `false`。
    /// 為什麼 fail-closed:鎖中毒（持鎖執行緒 panic）視同「無法證明未消費」→ 拒。
    fn try_consume(&self, nonce: &str) -> bool {
        match self.consumed.lock() {
            Ok(mut set) => set.insert(nonce.to_string()),
            Err(_) => false,
        }
    }

    /// 只讀查詢（測試/觀測用;不消費）。鎖中毒視同已消費（fail-closed）。
    pub(crate) fn is_consumed(&self, nonce: &str) -> bool {
        match self.consumed.lock() {
            Ok(set) => set.contains(nonce),
            Err(_) => true,
        }
    }
}

// ===========================================================================
// (c) 裁決入口（先寫拒絕路徑;nonce 只在全綁定通過後消費）
// ===========================================================================

/// 活化裁決 blocker（封閉枚舉;engine 姿態面——契約 shape 面 blocker 以
/// `EnvelopeContract` 嵌套投影,不複製一套平行拒因）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum IbkrActivationCheckBlocker {
    /// envelope 缺席（任何接觸的第一前提;credentials/session/seal 皆不可替代）。
    EnvelopeAbsent,
    /// seal 在位而 envelope 缺席:seal 永不是 activation authority（AMD-07-11 鐵律的
    /// 機器證明位——sealed Phase-2 PASS artifact 在位 + 無 envelope → 接觸拒絕）。
    SealIsNotActivationAuthority,
    /// types 契約 shape/綁定/時窗 blocker 的嵌套投影（單一校驗真源,禁語義漂移）。
    EnvelopeContract(IbkrActivationEnvelopeBlocker),
    /// envelope 綁定的 build SHA ≠ 現 binary `BUILD_GIT_SHA`。
    BuildGitShaMismatch,
    /// envelope 綁定的 revocation epoch ≠ 當前值（落後/超前皆拒）。
    RevocationEpochMismatch,
    /// envelope 綁定的 kill-switch epoch ≠ 當前值（落後/超前皆拒）。
    KillSwitchEpochMismatch,
    /// readonly envelope + 任何 order verb → 結構性拒（無條件,先於一切放行考量）。
    OrderVerbStructurallyDenied,
    /// readonly 白名單外的非 order 操作（shadow/scorecard/fill-import 等——不屬唯讀
    /// broker 接觸面,readonly envelope 不授權）。
    OperationOutsideReadonlyScope,
    /// nonce 已被消費（replay / 二次活化嘗試）。
    NonceAlreadyConsumed,
}

/// 活化裁決（`activation_accepted=true` 僅表示:本次操作在此 envelope + 當前姿態下
/// 被授權**且 nonce 已被本次消費**;不免除憑證/entitlement/market-hours/safety checks）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct IbkrActivationCheckVerdict {
    pub(crate) activation_accepted: bool,
    pub(crate) blockers: Vec<IbkrActivationCheckBlocker>,
}

impl IbkrActivationCheckVerdict {
    fn deny(blockers: Vec<IbkrActivationCheckBlocker>) -> Self {
        Self {
            activation_accepted: false,
            blockers,
        }
    }
}

/// readonly scope 的操作白名單裁決:唯讀 broker 接觸四面（health/account snapshot/
/// market data/contract details）放行;order verb 家族結構性拒;其餘一律 scope 外拒。
/// **窮舉 match（無萬用臂）**:`BrokerOperation` 新增變體時此處編譯期強制重審。
fn readonly_operation_blocker(op: BrokerOperation) -> Option<IbkrActivationCheckBlocker> {
    use BrokerOperation as Op;
    use IbkrActivationCheckBlocker as B;
    match op {
        // readonly 白名單:唯讀接觸面。
        Op::HealthRead | Op::AccountSnapshotRead | Op::MarketDataRead | Op::ContractDetailsRead => {
            None
        }
        // order verb 家族:readonly envelope 下無條件結構性拒（含永久 denied 面）。
        Op::PaperOrderSubmit
        | Op::PaperOrderCancel
        | Op::PaperOrderReplace
        | Op::LiveOrderSubmit
        | Op::MarginOrShort
        | Op::OptionsOrCfd
        | Op::TransferOrAccountWrite => Some(B::OrderVerbStructurallyDenied),
        // 非 order 但不屬唯讀接觸面:readonly envelope 不授權（paper/shadow 歸各自 scope）。
        Op::PaperOrderFillImport
        | Op::ShadowSignalEmit
        | Op::ShadowFillReconstruct
        | Op::ScorecardDerive => Some(B::OperationOutsideReadonlyScope),
    }
}

/// **唯一裁決入口**:readonly-scope 接觸授權檢查。
///
/// 順序（先寫拒絕路徑）:
/// 1. envelope 缺席 → 拒（seal 在位另加 `SealIsNotActivationAuthority`——seal≠活化）。
/// 2. types 契約 `validate(now_ms)`（shape/綁定/時窗）blocker 全量嵌套投影。
/// 3. build SHA / revocation epoch / kill-switch epoch 與當前姿態逐一比對。
/// 4. operation verb 白名單（order verb 結構性拒）。
/// 5. **全部通過後**才原子消費 nonce;消費失敗（replay）→ 拒。
///
/// 不變量:任何 deny path 都不消費 nonce（拒絕不燒授權;replay 防護只針對已放行的
/// 消費）;本函數無提前放行分支——放行是「blocker 為空 + nonce 消費成功」的唯一交點。
pub(crate) fn check_readonly_contact(
    envelope: Option<&IbkrActivationEnvelopeV1>,
    operation: BrokerOperation,
    posture: &ActivationCheckPosture,
    ledger: &ActivationNonceLedger,
) -> IbkrActivationCheckVerdict {
    use IbkrActivationCheckBlocker as B;

    // 1. envelope 缺席:credentials/session/seal 皆永不自動活化。
    let Some(envelope) = envelope else {
        let mut blockers = vec![B::EnvelopeAbsent];
        if posture.phase2_seal_present {
            blockers.push(B::SealIsNotActivationAuthority);
        }
        return IbkrActivationCheckVerdict::deny(blockers);
    };

    let mut blockers = Vec::new();

    // 2. 契約 shape/綁定/時窗（單一校驗真源=types validate;不在 engine 重寫一套）。
    for shape_blocker in envelope.validate(posture.now_ms).blockers {
        blockers.push(B::EnvelopeContract(shape_blocker));
    }

    // 3. 姿態綁定比對（精確相等;任何不等皆 fail-closed 拒）。
    if envelope.build_git_sha != posture.current_build_git_sha {
        blockers.push(B::BuildGitShaMismatch);
    }
    if envelope.revocation_epoch != posture.current_revocation_epoch {
        blockers.push(B::RevocationEpochMismatch);
    }
    if envelope.kill_switch_epoch != posture.current_kill_switch_epoch {
        blockers.push(B::KillSwitchEpochMismatch);
    }

    // 4. operation verb 白名單（readonly + 任何 order verb → 結構性拒）。
    if let Some(op_blocker) = readonly_operation_blocker(operation) {
        blockers.push(op_blocker);
    }

    // deny path:不消費 nonce（拒絕不燒授權）。
    if !blockers.is_empty() {
        return IbkrActivationCheckVerdict::deny(blockers);
    }

    // 5. nonce 原子消費（放行的最後一道;同 nonce 二次驗證必拒=防 replay）。
    if !ledger.try_consume(&envelope.activation_nonce) {
        return IbkrActivationCheckVerdict::deny(vec![B::NonceAlreadyConsumed]);
    }

    IbkrActivationCheckVerdict {
        activation_accepted: true,
        blockers: Vec::new(),
    }
}

#[cfg(test)]
#[path = "ibkr_activation_envelope_check_tests.rs"]
mod tests;
