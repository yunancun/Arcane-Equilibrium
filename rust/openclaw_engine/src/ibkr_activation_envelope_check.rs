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
//!   - **W7-S4a effect 面（`check_effect_contact`;§4 option B）**：paper order-write 授權裁決,
//!     疊 option B HMAC 簽名 leg（`ibkr_effect_activation`）於 paper-scope envelope 之上。唯一鑄造
//!     `OrderEffectPermit`（§1.3）的位點在其 `Ok` 臂;但 **S4a production 零 caller → 放行臂不可達 →
//!     production 恆拒不變量維持**（無真簽名 envelope provider、無金鑰 slot、無 production caller）。
//!     窮舉 gate:readonly-scope+order→`OrderVerbStructurallyDenied`;margin/short/options/cfd/
//!     transfer/live→`PermanentlyDeniedVerb`;shape/posture/HMAC/nonce 全過才鑄 permit。真活化=EA5。
//!   - **INV-1 不受影響（R16 起部分解除 dormant）**：R16 mini-wiring 使
//!     `ibkr_readonly_tws_client` 的 G4 entry（feature `ibkr_g4_contact` gated）成為
//!     `check_readonly_contact` 首個 production caller——G4 readonly socket 線與 driver
//!     permit 線是兩條獨立受審面;本模塊仍**不** impl `ConnectPermitProvider`、**不**觸碰
//!     `PermitToken`——production connect（driver permit）路徑仍恆撞
//!     `EnvelopeRequiredStub`,default build（feature off）本模塊依舊零 caller/DCE。W8 全包
//!     以本驗證器替換該 trait 位並吸收本切片（**共用同一驗證代碼路徑,禁兩套語義漂移**——
//!     同 W2「caller 與 consume 共路徑」原則）。
//!   - **reconnect / scope 變更 = 重新活化**：nonce 單次消費使一份 envelope 至多支撐一次
//!     接觸授權;斷線重連或 scope 變更必須換新 envelope（新 nonce）,無「續用舊授權」路徑。
//!   - **移交契約（E2-F1）**：本入口=**活化時刻**裁決;per-operation 續用語義歸 W8 的
//!     session-scoped activated 態,**禁以重複呼叫本入口實作 per-operation 檢查**
//!     （第二次呼叫必 `NonceAlreadyConsumed`）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 IPC。

// dormant 姿態（R16 部分解除）:`check_readonly_contact`/`ActivationCheckPosture`/
// `ActivationNonceLedger` 已有 production caller（G4 entry,feature `ibkr_g4_contact`
// gated）;default build（feature off）該 caller 不編譯 → 本模塊仍整體無 caller,
// allow(dead_code) 必須保留;W8 接真 ConnectPermitProvider 位時移出。
#![allow(dead_code)]

use std::collections::HashSet;
use std::sync::Mutex;

use openclaw_types::{
    BrokerOperation, IbkrActivationEnvelopeBlocker, IbkrActivationEnvelopeV1,
    IbkrActivationOperationScopeV1,
};

use crate::ibkr_effect_activation::{EffectAuthError, EffectSignatureVerifier};
use crate::ibkr_tws_order_transport::OrderEffectPermit;

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

// ===========================================================================
// (d) W7-S4a effect 面裁決入口（`check_effect_contact`;§4 option B HMAC）
//     paper order-write 授權——疊 option B 簽名 leg 於 paper-scope envelope 之上。
// ===========================================================================

/// effect 裁決 blocker（封閉枚舉;paper order-write 面）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum EffectCheckBlocker {
    /// envelope 缺席（effect 接觸的第一前提;credentials/session/seal 皆不可替代）。
    EffectEnvelopeAbsent,
    /// seal 在位而 envelope 缺席:seal 永不是 activation authority（AMD-07-11;CC-B4——
    /// sealed Phase-2 PASS artifact 在位 + 無 effect envelope → order 拒,擴到 effect 面）。
    SealIsNotActivationAuthority,
    /// **readonly-scope envelope + paper order verb → 結構性拒**（§1.4 item 4;INV-ORDER 兄弟面）。
    OrderVerbStructurallyDenied,
    /// **永久 denied verb**（live submit / margin-short / options-cfd / transfer-account-write）——
    /// 任何 scope 下結構性拒（硬邊界;先於 scope 判定）。
    PermanentlyDeniedVerb,
    /// envelope scope 與 operation 不匹配 effect 面（paper-scope+非 order / readonly-scope+非 order）。
    OperationOutsideEffectScope,
    /// envelope scope 非 effect scope（`UnknownDenied` 等——fail-closed 分類）。
    EffectScopeDenied,
    /// paper-scope envelope 的 shape/綁定/時窗 blocker 嵌套投影（單一校驗真源=types
    /// `validate_paper_effect`,禁語義漂移）。
    EnvelopeContract(IbkrActivationEnvelopeBlocker),
    /// envelope 綁定的 build SHA ≠ 現 binary `BUILD_GIT_SHA`。
    BuildGitShaMismatch,
    /// envelope 綁定的 revocation epoch ≠ 當前值（落後/超前皆拒）。
    RevocationEpochMismatch,
    /// envelope 綁定的 kill-switch epoch ≠ 當前值（落後/超前皆拒）。
    KillSwitchEpochMismatch,
    /// **option B HMAC 簽名不符**（篡改 / 錯金鑰 / payload 漂移;新 leg）。
    SignatureInvalid,
    /// **金鑰 slot 缺席**（CC-B1 fail-closed;無金鑰即無法驗證 → 拒,絕不放行）。
    SigningKeyMissing,
    /// nonce 已被消費（replay / 二次活化嘗試）。
    NonceAlreadyConsumed,
}

/// effect 裁決:`Accepted(permit)` **僅**在 shape/posture/operation/HMAC/nonce 全過時鑄一枚
/// `OrderEffectPermit`（§1.3 唯一鑄造點);否則 `Denied(blockers)`。`OrderEffectPermit` 刻意非
/// Debug/Clone → 本枚舉不 derive Debug/PartialEq（測試以 `matches!` 斷言）。
pub(crate) enum EffectVerdict {
    Accepted(OrderEffectPermit),
    Denied(Vec<EffectCheckBlocker>),
}

impl EffectVerdict {
    /// 測試/觀測用:是否放行（不取出 permit）。
    #[cfg(test)]
    pub(crate) fn is_accepted(&self) -> bool {
        matches!(self, EffectVerdict::Accepted(_))
    }

    /// 測試/觀測用:被拒 blocker（放行時回空）。
    #[cfg(test)]
    pub(crate) fn blockers(&self) -> Vec<EffectCheckBlocker> {
        match self {
            EffectVerdict::Accepted(_) => Vec::new(),
            EffectVerdict::Denied(b) => b.clone(),
        }
    }
}

/// **effect operation × envelope-scope 結構性閘**（窮舉 match,無萬用臂;`BrokerOperation` 新增
/// 變體時編譯期強制重審）。回 `None`=放行（進 shape/簽名/nonce）;`Some(blocker)`=結構性拒。
///
/// 優先序:①永久 denied verb（硬邊界,任何 scope 皆拒,先判）→ ②(scope, op) 對照。
fn effect_operation_blocker(
    scope: IbkrActivationOperationScopeV1,
    op: BrokerOperation,
) -> Option<EffectCheckBlocker> {
    use BrokerOperation as Op;
    use EffectCheckBlocker as B;
    use IbkrActivationOperationScopeV1 as Scope;

    // ① 永久 denied verb:任何 scope 下結構性拒（硬邊界先於 scope）。
    match op {
        Op::LiveOrderSubmit | Op::MarginOrShort | Op::OptionsOrCfd | Op::TransferOrAccountWrite => {
            return Some(B::PermanentlyDeniedVerb)
        }
        _ => {}
    }

    // ② (scope, op) 窮舉對照。
    match (scope, op) {
        // paper scope + paper order verb → 放行（進簽名/nonce)。
        (Scope::Paper, Op::PaperOrderSubmit | Op::PaperOrderCancel | Op::PaperOrderReplace) => None,
        // paper scope + 非 paper-order 操作 → effect 面外。
        (Scope::Paper, _) => Some(B::OperationOutsideEffectScope),
        // readonly scope + 任何 paper order verb → 結構性拒（§1.4 item 4）。
        (Scope::Readonly, Op::PaperOrderSubmit | Op::PaperOrderCancel | Op::PaperOrderReplace) => {
            Some(B::OrderVerbStructurallyDenied)
        }
        // readonly scope + 非 order → 不屬 effect 面（唯讀接觸走 check_readonly_contact）。
        (Scope::Readonly, _) => Some(B::OperationOutsideEffectScope),
        // unknown scope → effect scope 拒。
        (Scope::UnknownDenied, _) => Some(B::EffectScopeDenied),
    }
}

/// **W7-S4a effect 裁決入口**:paper order-write 授權（§4 option B）。
///
/// 順序（先寫拒絕路徑;fail-closed;nonce 只在全過後消費）:
/// 1. envelope 缺席 → 拒（seal 在位另加 `SealIsNotActivationAuthority`——seal≠活化;CC-B4）。
/// 2. **結構性 operation×scope 閘**（短路,單 blocker 潔淨拒）:readonly+order→
///    `OrderVerbStructurallyDenied`;margin/short/options/cfd/transfer/live→`PermanentlyDeniedVerb`;
///    paper+非 order→`OperationOutsideEffectScope`;unknown→`EffectScopeDenied`。唯 paper+paper-order
///    放行進下一步。
/// 3. paper-scope shape/綁定/時窗（`validate_paper_effect`)blocker 全量嵌套投影。
/// 4. build SHA / revocation epoch / kill-switch epoch 與當前姿態逐一比對（累積）。
/// 5. 累積 blocker 非空 → 拒（deny path 不燒 nonce、不鑄 permit）。
/// 6. **option B HMAC 簽名驗證**（`sig_verifier`;金鑰缺席 fail-closed）→ 失敗拒。
/// 7. nonce 原子消費（同 nonce 二次必拒=防 replay）→ 失敗拒。
/// 8. **全過 → `Accepted(OrderEffectPermit::mint())`**（§1.3 唯一鑄造點）。
///
/// **production 恆拒不變量**:本函數 S4a 零 production caller → 放行臂 final-binary DCE;production
/// 無金鑰 slot（步 6 恆 `SigningKeyMissing`）、無真簽名 envelope provider 構造 paper envelope →
/// 步 8 不可達。真活化=EA5 Operator-gated。
pub(crate) fn check_effect_contact(
    envelope: Option<&IbkrActivationEnvelopeV1>,
    operation: BrokerOperation,
    posture: &ActivationCheckPosture,
    ledger: &ActivationNonceLedger,
    sig_verifier: &EffectSignatureVerifier,
) -> EffectVerdict {
    use EffectCheckBlocker as B;

    // 1. envelope 缺席:credentials/session/seal 皆永不自動活化（seal≠活化,CC-B4）。
    let Some(envelope) = envelope else {
        let mut blockers = vec![B::EffectEnvelopeAbsent];
        if posture.phase2_seal_present {
            blockers.push(B::SealIsNotActivationAuthority);
        }
        return EffectVerdict::Denied(blockers);
    };

    // 2. 結構性 operation×scope 閘（短路:單 blocker 潔淨拒,不受 shape 雜訊污染)。
    if let Some(structural) = effect_operation_blocker(envelope.operation_scope, operation) {
        return EffectVerdict::Denied(vec![structural]);
    }

    // 到此:paper-scope envelope + paper order verb。累積 shape + posture blocker。
    let mut blockers = Vec::new();

    // 3. paper-scope 契約 shape/綁定/時窗（單一校驗真源=types validate_paper_effect）。
    for shape_blocker in envelope.validate_paper_effect(posture.now_ms).blockers {
        blockers.push(B::EnvelopeContract(shape_blocker));
    }

    // 4. 姿態綁定比對（精確相等;任何不等皆 fail-closed 拒）。
    if envelope.build_git_sha != posture.current_build_git_sha {
        blockers.push(B::BuildGitShaMismatch);
    }
    if envelope.revocation_epoch != posture.current_revocation_epoch {
        blockers.push(B::RevocationEpochMismatch);
    }
    if envelope.kill_switch_epoch != posture.current_kill_switch_epoch {
        blockers.push(B::KillSwitchEpochMismatch);
    }

    // 5. deny path:不消費 nonce、不鑄 permit。
    if !blockers.is_empty() {
        return EffectVerdict::Denied(blockers);
    }

    // 6. option B HMAC 簽名驗證（金鑰缺席 fail-closed;篡改/錯金鑰拒）。簽名驗證在 nonce 消費**之前**、
    //    permit 鑄造**之前**——防「先寬後緊」授權事故（對抗性第二思考,設計 §8）。
    if let Err(auth_err) = sig_verifier.verify(envelope, operation) {
        let blocker = match auth_err {
            EffectAuthError::SigningKeyMissing => B::SigningKeyMissing,
            EffectAuthError::BadSignature => B::SignatureInvalid,
        };
        return EffectVerdict::Denied(vec![blocker]);
    }

    // 7. nonce 原子消費（放行的最後一道;同 nonce 二次驗證必拒=防 replay;reconnect 需新 envelope）。
    if !ledger.try_consume(&envelope.activation_nonce) {
        return EffectVerdict::Denied(vec![B::NonceAlreadyConsumed]);
    }

    // 8. 全過 → 鑄 order-effect permit（§1.3 唯一鑄造點;production 零 caller → DCE → 不可達)。
    EffectVerdict::Accepted(OrderEffectPermit::mint())
}

#[cfg(test)]
#[path = "ibkr_activation_envelope_check_tests.rs"]
mod tests;
