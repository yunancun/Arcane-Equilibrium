//! MODULE_NOTE
//! 模塊用途：IBKR **W7-S0 order-verb transport-gating 骨架（恆拒地基）**
//!   （IBKR_TODO §5-W7;設計文檔 §1 INV-ORDER）。在既有 pacing 單一出口（`OutboundGrant`,
//!   W3-S3）之上,為 order-verb 出站訊息增設**第二把型別鎖**:order frame 是獨立 newtype
//!   `OrderFrame`（型別上非通用 frame）,唯一送出函數 `send_order_framed` 額外要求一枚
//!   production 域**不可鑄造**的 `OrderEffectPermit`。無 effect envelope → 零 order frame 出站。
//! 主要區段：
//!   - (a) `OrderFrame`：order-verb 專屬出站 frame newtype。bytes **私有**,無 pub accessor——
//!     唯 `send_order_framed`（同模塊）可取出 → 無法餵入通用 `send_framed(&[u8])`（driver）。
//!     本輪**不含** placeOrder/cancelOrder 欄位編碼（=S1 encoder）;只是承載型別殼 + 受控構造。
//!   - (b) INV-ORDER permit：`OrderEffectPermit`（**非 Clone/非 Copy**,move 單次消費）+
//!     `EffectPermitProvider` trait + production 唯一實作 `EffectEnvelopeRequiredStub`（**恆拒,
//!     零 env/config/cfg 讀取**）。仿 W3 connect permit 先例（`ConnectPermitProvider`/
//!     `EnvelopeRequiredStub`）,但**兩線獨立**:connect permit 守 connect,order-effect permit
//!     守 order-verb send;EA 跑道 session 已 connected（readonly envelope）時,唯本線阻 order verb。
//!   - (c) `send_order_framed`：order frame 的**唯一出站位點**。by-value 消費 `OutboundGrant`
//!     （pacing 仍在）+ `OrderEffectPermit`（新）+ `OrderFrame`;回傳待寫線 framed bytes。
//!     實際 socket 寫入由 driver 接線（S1+;本輪不送任何 order 訊息）。
//!   - (d) `order_effect_capability_gate`：`broker_capability_registry_v1` machine-check——ADR
//!     硬序閘。消費既有 types 契約（`StockEtfBrokerCapabilityRegistryV1`,source-ready,不重造）,
//!     斷言 registry 必 admit paper order verb（PaperRehearsal + rust_owned）且恆 deny
//!     live/margin/short/options/cfd/transfer（Denied）方可存在 effect 路徑;不通過→拒。
//! 依賴：`ibkr_tws_pacing`（`OutboundGrant`）、`openclaw_types`（capability registry 契約 +
//!   `BrokerOperation`/`AuthorityScope`）。
//! 硬邊界：
//!   - **INV-ORDER（本模塊最高不變量）**：production build 零路徑可使 order-verb 訊息出
//!     transport 層。二元證明:①`OrderEffectPermit` production 零鑄造點（`mint` 為 `#[cfg(test)]`,
//!     production 無構造子）→ `send_order_framed` production 不可達;②本模塊 0 production caller →
//!     default build DCE（沿 driver/g4 audit 家族）。兩證獨立。
//!   - **S0 = 恆拒地基,放行臂 S4;encoder S1**：本輪不含任何 order encoder、不送任何 order 訊息、
//!     無放行臂。`EffectEnvelopeRequiredStub::check` 恆 `Err(EffectDenied::EnvelopeRequired)`,
//!     無任何開關可翻放行。W7-S4 才落 HMAC option B 放行臂（`check_effect_contact`,鑄
//!     `OrderEffectPermit`;唯一 production 鑄造點）。
//!   - **兩線獨立（INV-1 不受影響）**：本模塊**不** impl `ConnectPermitProvider`、**不**觸碰
//!     `PermitToken`;connect permit 線（`EnvelopeRequiredStub` 恆拒）不受本模塊影響。
//!   - margin/short/options/cfd/transfer/account-write 永久 denied（capability gate 結構性拒）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 IPC（IPC 接線=S4）。

// dormant 姿態：本模塊 W7-S0 落地時 **0 production caller**（放行臂/encoder/IPC 接線皆 S1-S4）,
// default build 因 0 caller 被 DCE（同 driver/session pre-W4 姿態）。allow(dead_code) 必須保留;
// S4 接 `check_effect_contact` production 放行臂 + IPC handler 時移出。
#![allow(dead_code)]

use openclaw_types::{
    AuthorityScope, BrokerOperation, StockEtfBrokerCapabilityRegistryV1, StockEtfDenialReason,
};

use crate::ibkr_tws_pacing::OutboundGrant;

// ===========================================================================
// (a) OrderFrame：order-verb 專屬出站 frame newtype（bytes 私有,唯本模塊可取）
// ===========================================================================

/// order-verb 專屬出站 frame。**型別上非通用 frame**——內部 bytes **私有**且**無 pub accessor**,
/// 故 crate 外/本模塊外無法取出 bytes 餵入 driver 的 `send_framed(&[u8])`。唯一取出點 =
/// `send_order_framed`（同模塊,可讀私有欄）。
///
/// 本輪（S0）**不含** placeOrder/cancelOrder 欄位編碼——`OrderFrame` 只是承載 order-verb 出站
/// 位元組的型別殼;真 encoder（IN/OUT 欄位序列化）= W7-S1。構造子 `from_order_bytes` 為
/// **crate-private**（受控構造）,S0 零 production caller（DCE）;S1 order builder 為首個 caller。
pub(crate) struct OrderFrame {
    /// 私有 order-verb framed bytes：無 pub accessor;唯 `send_order_framed`（同模塊）可取。
    bytes: Vec<u8>,
}

impl OrderFrame {
    /// **crate-private** 構造子（受控）。S1 order builder 為首個 caller;S0 零 production caller。
    /// 為什麼受控:order-verb bytes 一旦成型即受 INV-ORDER 約束,不得經任意路徑構造繞閘。
    pub(crate) fn from_order_bytes(bytes: Vec<u8>) -> Self {
        Self { bytes }
    }

    /// **模塊私有** bytes 取出（唯一提取點,唯 `send_order_framed` 消費）。非 `pub(crate)`——
    /// 令 order bytes 只能經 gated 的 `send_order_framed` 流出,不得旁路。
    fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

// ===========================================================================
// (b) INV-ORDER order-effect permit（恆拒地基;仿 W3 connect permit,兩線獨立）
// ===========================================================================
// EFFECT-STUB-GUARD-BEGIN
// 【CI 靜態守衛掃描邊界】本區塊（BEGIN..END）內:
//   - production effect provider = 具體型別 `EffectEnvelopeRequiredStub`（禁 dyn/泛型 permit 參數）;
//   - `EffectEnvelopeRequiredStub::check` 恆 `Err(EnvelopeRequired)`,**零 env / config / cfg 讀取**
//     （無任何開關可翻放行——S4 才以真 HMAC option B 驗證器落放行臂）;
//   - `OrderEffectPermit` 非 Clone / 非 Copy,構造子 `mint` 為 **`#[cfg(test)]`**（本輪唯一鑄造點=
//     測試域;production **無** `mint` 符號 → 恆無 permit → `send_order_framed` production 不可達）。
// ---------------------------------------------------------------------------

/// INV-ORDER order-effect permit:order-verb send 授權的**單次消費證明**。**非 Clone / 非 Copy**——
/// move 進 `send_order_framed` 後即消費,結構上禁止「舊 envelope 靜默復用 order 授權」。
/// 構造只能經 `mint`,而 S0 `mint` 為 `#[cfg(test)]` → **production 無任何構造路徑**（放行臂 S4
/// 才把 `mint` 移出 test 域,由 `check_effect_contact` `Ok` 臂鑄造）。
pub(crate) struct OrderEffectPermit {
    /// 私有零大小封印:令 `OrderEffectPermit { .. }` literal 在模塊外不可構造。
    _seal: (),
}

impl OrderEffectPermit {
    /// **唯一鑄造點（S0 = `#[cfg(test)]` 測試域）**。production 恆無此符號 → 恆無 permit →
    /// INV-ORDER 二元成立。S4 放行臂落地時移除 `#[cfg(test)]`,由 HMAC option B 裁決 `Ok` 臂呼叫。
    #[cfg(test)]
    pub(crate) fn mint() -> Self {
        Self { _seal: () }
    }
}

/// order-effect permit 被拒原因（S0 production 恆 `EnvelopeRequired`;S4 真驗證器擴此枚舉）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub(crate) enum EffectDenied {
    /// effect-scope 活化 envelope 前置未滿足（production S4 前恆此路;INV-ORDER）。
    #[error("order effect denied: activation envelope required")]
    EnvelopeRequired,
}

/// INV-ORDER 掛點:每次 order-verb send **之前**必經 `check`;回 `Ok(permit)` 才可送,回 `Err`
/// 不放行。仿 W3 `ConnectPermitProvider`——但**兩線獨立**（connect permit ⊥ order-effect permit）。
pub(crate) trait EffectPermitProvider {
    fn check(&mut self) -> Result<OrderEffectPermit, EffectDenied>;
}

/// W7-S0 production **唯一** order-effect provider:**恆拒**。**零 env / config / cfg 讀取**——本
/// struct 與其 `check` 實作內不存在任何可翻放行的開關;S4 以真 `ibkr_activation_envelope_v1`
/// effect-scope + HMAC option B 驗證器替換同一 trait 位。對應 connect 面
/// `EnvelopeRequiredStub`,但守 order-verb send（非 connect）。
pub(crate) struct EffectEnvelopeRequiredStub;

impl EffectPermitProvider for EffectEnvelopeRequiredStub {
    fn check(&mut self) -> Result<OrderEffectPermit, EffectDenied> {
        // 恆拒。不讀 env、不讀 config、不 cfg!——production 無任何放行路徑（放行臂 S4）。
        Err(EffectDenied::EnvelopeRequired)
    }
}
// EFFECT-STUB-GUARD-END

// ===========================================================================
// (c) send_order_framed：order frame 的唯一出站位點（pacing grant AND effect permit）
// ===========================================================================

/// **order-verb 出站的唯一位點**。by-value 消費三令牌:
///   - `grant: OutboundGrant`——pacing 放行（既有單一出口約束不鬆動;W3-S3）。
///   - `permit: OrderEffectPermit`——order-effect 活化證明（S0 production 零鑄造 → 本函數
///     production 不可達 → INV-ORDER）。
///   - `frame: OrderFrame`——order-verb bytes（bytes 私有,唯此函數可取出）。
///
/// 回傳待寫線的 order-verb framed bytes;實際 socket 寫入由 driver 接線（S1+）。**S0 不送任何
/// order 訊息**（本函數 0 production caller → DCE）。無 `OrderEffectPermit` **型別上**無法呼叫本
/// 函數 → order frame 結構上無法經一般出站路徑繞過 envelope。
pub(crate) fn send_order_framed(
    grant: OutboundGrant,
    permit: OrderEffectPermit,
    frame: OrderFrame,
) -> Vec<u8> {
    // grant / permit by-value 消費（drop）:各為單次出站憑證,不可復用（非 Clone/非 Copy）。
    drop(grant);
    let OrderEffectPermit { _seal: () } = permit;
    // 唯一 OrderFrame → bytes 提取點:order bytes 只能經此 gated 位點流出。
    frame.into_bytes()
}

// ===========================================================================
// (d) capability registry machine-check（ADR 硬序閘;消費既有 types 契約,不重造）
// ===========================================================================

/// order-effect capability gate 被拒原因（engine 姿態面）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum OrderEffectCapabilityDenial {
    /// types 契約 `validate()` 未通過（registry shape/矩陣不合;嵌套 blocker 數留證）。
    RegistryContractInvalid(usize),
    /// paper order verb 未被 admit 為 PaperRehearsal + rust_owned（effect 路徑前置不滿足）。
    PaperOrderVerbNotAdmitted(BrokerOperation),
    /// 永久 denied verb 未維持 Denied（margin/short/options/cfd/transfer/live 放行破口）。
    DeniedVerbNotDenied(BrokerOperation),
}

/// **ADR 硬序閘**:effect-capable paper-route 實作前必先通過本 machine-check。
///
/// 消費既有 types 契約 `StockEtfBrokerCapabilityRegistryV1`（source-ready,不重造）:
///   1. `registry.validate()` 必 accepted（pins registry_id/lane/broker/全 operation 矩陣）。
///   2. paper order verb（submit/cancel/replace）必 admit 為 `AuthorityScope::PaperRehearsal`
///      且 `rust_owned`（effect 授權真源在 Rust)。
///   3. 永久 denied verb（live submit / margin-short / options-cfd / transfer-account-write）
///      必維持 `AuthorityScope::Denied`（放行破口 = fail-closed 拒）。
///
/// 不變量:任一不滿足 → `Err` → effect 路徑不得存在（S1+ 於建 order builder 前必呼叫本閘）。
/// 本閘**只讀**,不改 registry、不接觸 broker、不鑄 permit。
pub(crate) fn order_effect_capability_gate(
    registry: &StockEtfBrokerCapabilityRegistryV1,
) -> Result<(), OrderEffectCapabilityDenial> {
    // 1. types 契約矩陣校驗（單一真源=types validate,不在 engine 重寫一套）。
    let verdict = registry.validate();
    if !verdict.accepted {
        return Err(OrderEffectCapabilityDenial::RegistryContractInvalid(
            verdict.blockers.len(),
        ));
    }

    // 2. paper order verb 必 PaperRehearsal + rust_owned（獨立 engine 側斷言=縱深防禦）。
    for op in [
        BrokerOperation::PaperOrderSubmit,
        BrokerOperation::PaperOrderCancel,
        BrokerOperation::PaperOrderReplace,
    ] {
        let admitted = registry.operations.iter().any(|entry| {
            entry.operation == op
                && entry.authority_scope == AuthorityScope::PaperRehearsal
                && entry.rust_owned
                && entry.typed_denial_reason.is_none()
        });
        if !admitted {
            return Err(OrderEffectCapabilityDenial::PaperOrderVerbNotAdmitted(op));
        }
    }

    // 3. 永久 denied verb 必維持 Denied（放行破口 fail-closed 拒）。
    for op in [
        BrokerOperation::LiveOrderSubmit,
        BrokerOperation::MarginOrShort,
        BrokerOperation::OptionsOrCfd,
        BrokerOperation::TransferOrAccountWrite,
    ] {
        let denied = registry.operations.iter().any(|entry| {
            entry.operation == op
                && entry.authority_scope == AuthorityScope::Denied
                && matches!(entry.typed_denial_reason, Some(reason) if is_hard_denial(reason))
        });
        if !denied {
            return Err(OrderEffectCapabilityDenial::DeniedVerbNotDenied(op));
        }
    }

    Ok(())
}

/// 永久 denied verb 的 typed denial reason 白名單（結構性拒;新 reason 變體編譯期強制重審）。
fn is_hard_denial(reason: StockEtfDenialReason) -> bool {
    use StockEtfDenialReason as Deny;
    match reason {
        Deny::IbkrLiveNotAuthorized
        | Deny::StockEtfCashOnly
        | Deny::InstrumentKindDenied
        | Deny::AccountWriteDenied => true,
        // 非硬邊界 denial reason 不算「永久 denied verb 維持 Denied」的合法理由。
        _ => false,
    }
}

#[cfg(test)]
#[path = "ibkr_tws_order_transport_tests.rs"]
mod tests;
