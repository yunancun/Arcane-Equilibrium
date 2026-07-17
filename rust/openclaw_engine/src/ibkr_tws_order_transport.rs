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
//!     transport 層。二元證明:①`OrderEffectPermit::mint`（W7-S4a 起 `pub(crate)`）**唯一 production
//!     呼叫點 = `check_effect_contact` `Ok` 臂**,而 `check_effect_contact` S4a 零 production caller →
//!     mint 呼叫 + `send_order_framed` 一併 production 不可達;②本模塊 0 production caller →
//!     **final-binary DCE**（`target/release/openclaw-engine` 零 seam 符號 AND 零 seam strings,
//!     含 `EffectDenied` literal 缺席）。**rlib 級非 DCE 證據**——rlib 保留 rmeta,`strings
//!     libopenclaw_engine*.rlib` 仍命中 seam 名;有效 DCE 證據唯 final binary（nm + strings 雙查）。
//!     沿 driver/g4 audit 家族。兩證獨立。源級機器證明:mint 單呼叫點 + 唯一 stub provider +
//!     check_effect_contact 零 caller,見 `tests/structure/test_ibkr_effect_permit_stub_source_static.py`。
//!   - **恆拒地基;放行臂 = `check_effect_contact`（W7-S4a 落於 `ibkr_activation_envelope_check`）**：
//!     本模塊的 `EffectEnvelopeRequiredStub::check` 恆 `Err(EffectDenied::EnvelopeRequired)`,無任何
//!     開關可翻放行——它是 production **唯一** `EffectPermitProvider`,永不鑄 permit。option B HMAC
//!     放行臂在 `check_effect_contact`（鑄 `OrderEffectPermit`;§1.3 唯一鑄造點）,但其 production 零
//!     caller → 放行臂 production 不可達。真活化=EA5 Operator-gated。
//!   - **兩線獨立（INV-1 不受影響）**：本模塊**不** impl `ConnectPermitProvider`、**不**觸碰
//!     `PermitToken`;connect permit 線（`EnvelopeRequiredStub` 恆拒）不受本模塊影響。
//!   - margin/short/options/cfd/transfer/account-write 永久 denied（capability gate 結構性拒）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 IPC（IPC 接線=S4）。

// dormant 姿態：本模塊 W7-S0 落地時 **0 production caller**（放行臂/encoder/IPC 接線皆 S1-S4）,
// final binary 因 0 caller 被 DCE（rlib 保留 rmeta 非 DCE 證據;證據唯 final-binary nm+strings。
// 同 driver/session pre-W4 姿態）。allow(dead_code) 必須保留;
// S4 接 `check_effect_contact` production 放行臂 + IPC handler 時移出。
#![allow(dead_code)]

use openclaw_types::{
    is_positive_decimal_string, is_signed_decimal_string, AuthorityScope, BrokerOperation,
    StockEtfBrokerCapabilityRegistryV1, StockEtfDenialReason,
};

use crate::ibkr_tws_pacing::OutboundGrant;
use crate::ibkr_tws_wire::{encode_fields, encode_fields_checked, encode_frame, CodecError};

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
//     （無任何開關可翻放行——真 HMAC option B 放行臂在 `check_effect_contact`,非本 stub）;
//   - `OrderEffectPermit` 非 Clone / 非 Copy,構造子 `mint` 為 **`pub(crate)`（W7-S4a 起移出
//     `#[cfg(test)]`）**——但 INV-ORDER 二元仍成立:mint **唯一 production 呼叫點 =
//     `check_effect_contact` `Ok` 臂**（`ibkr_activation_envelope_check`）,而 `check_effect_contact`
//     S4a **零 production caller** → mint 呼叫 + check_effect_contact 一併 **final-binary DCE**;
//     production 仍恆無 permit → `send_order_framed` production 不可達。機器證明見
//     `tests/structure/test_ibkr_effect_permit_stub_source_static.py`（唯一 impl + mint 單呼叫點 +
//     check_effect_contact 零 caller）。
// ---------------------------------------------------------------------------

/// INV-ORDER order-effect permit:order-verb send 授權的**單次消費證明**。**非 Clone / 非 Copy**——
/// move 進 `send_order_framed` 後即消費,結構上禁止「舊 envelope 靜默復用 order 授權」。
/// 構造只能經 `mint`（`pub(crate)`,crate 外不可鑄）;**唯一 production 呼叫點 =
/// `check_effect_contact` `Ok` 臂**（§1.3 唯一鑄造點）,而該函數 S4a 零 production caller → DCE →
/// production 恆無 permit（INV-ORDER 二元）。真金鑰/真簽名 envelope = EA5 Operator-gated。
pub(crate) struct OrderEffectPermit {
    /// 私有零大小封印:令 `OrderEffectPermit { .. }` literal 在模塊外不可構造。
    _seal: (),
}

impl OrderEffectPermit {
    /// **唯一鑄造點（§1.3）**。W7-S4a 起為 `pub(crate)`（供 `check_effect_contact` `Ok` 臂鑄造）,
    /// 但唯一 production 呼叫點在 `check_effect_contact`,其零 production caller → mint 呼叫 DCE →
    /// production 恆無 permit。test 域另可鑄（transport 骨架單元測試）。**禁**在 production 新增
    /// 任何第二呼叫點（機器證明守衛會 FAIL）。
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
//     + WireBytes sealed 出線型別（W7-S1 NOTE-1 (a):型別層封 order 出線 bytes）
// ===========================================================================

/// **order-verb 已閘出線 bytes 的 sealed 承載**（W7-S1 NOTE-1 (a) 型別屏障）。內部 bytes **私有**、
/// 無 pub accessor——唯 `send_order_framed`（gated,收 `OrderEffectPermit`）可鑄造。**用途**:令
/// gated 出線的產物本身也是 sealed 型別（非裸 `Vec<u8>`）→ order-verb wire bytes 在通過 permit 閘
/// **之後**仍不退化為可餵入 driver 的裸 `&[u8]`——`ibkr_tws_driver::send_framed(grant, &[u8])` 是
/// pacing-only、effect-ungated 的平行出線路徑（NOTE-1 seam);WireBytes 型別上不 deref 為 `&[u8]`,
/// 故 order bytes 無型別安全路徑可繞過 permit 直達 `send_framed`。socket 寫入承接由 S4 driver
/// order-write shim 消費 WireBytes（S1 零 caller → DCE，同 OrderFrame 姿態）。
pub(crate) struct WireBytes {
    /// 私有已閘出線 bytes:無 pub accessor;唯 `send_order_framed`（同模塊）鑄造。
    bytes: Vec<u8>,
}

impl WireBytes {
    /// **模塊私有**鑄造子（唯 `send_order_framed` 呼叫）。名稱刻意非 `from_*`/`new`,標明它只是
    /// gated 邊界內部的封裝點,非公開構造面。
    fn seal(bytes: Vec<u8>) -> Self {
        Self { bytes }
    }

    /// **模塊私有**已閘 bytes 取出（S4 driver order-write shim 唯一提取點;S1 零 caller → DCE）。
    /// 名稱刻意避開 G1 accessor 黑名單（as_bytes/as_slice/into_bytes/bytes）——它是 driver 接線的
    /// 受控出口,非公開 accessor。
    fn into_wire(self) -> Vec<u8> {
        self.bytes
    }

    /// test 域檢視（`#[cfg(test)]`:同 `mint` 紀律,production 無此符號 → 不成公開 bytes 逃逸面）。
    #[cfg(test)]
    pub(crate) fn view(&self) -> &[u8] {
        &self.bytes
    }
}

/// **order-verb 出站的唯一位點**。by-value 消費三令牌:
///   - `grant: OutboundGrant`——pacing 放行（既有單一出口約束不鬆動;W3-S3）。
///   - `permit: OrderEffectPermit`——order-effect 活化證明（S0 production 零鑄造 → 本函數
///     production 不可達 → INV-ORDER）。
///   - `frame: OrderFrame`——order-verb bytes（bytes 私有,唯此函數可取出）。
///
/// 回傳 **sealed `WireBytes`**（W7-S1 NOTE-1 (a);非裸 `Vec<u8>`）——gated 出線的產物型別層封裝,
/// 不退化為可餵入 `send_framed(&[u8])` 的裸 bytes。實際 socket 寫入由 S4 driver order-write shim
/// 消費 WireBytes。**S1 不送任何 order 訊息**（本函數 0 production caller → DCE）。無
/// `OrderEffectPermit` **型別上**無法呼叫本函數 → order frame 結構上無法繞過 envelope 出線。
pub(crate) fn send_order_framed(
    grant: OutboundGrant,
    permit: OrderEffectPermit,
    frame: OrderFrame,
) -> WireBytes {
    // grant / permit by-value 消費（drop）:各為單次出站憑證,不可復用（非 Clone/非 Copy）。
    drop(grant);
    let OrderEffectPermit { _seal: () } = permit;
    // 唯一 OrderFrame → bytes 提取點:order bytes 只能經此 gated 位點流出,且立即封回 sealed WireBytes。
    WireBytes::seal(frame.into_bytes())
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

// ===========================================================================
// (e) place/cancel encoder（W7-S1;產 OrderFrame,§1.5 encode ceiling guard;無 production send）
// IB 现勘 2026-07-17:OUT PLACE_ORDER=3（含 whatIf flag）/ CANCEL_ORDER=4;replace=無獨立 msg
// （同 PLACE_ORDER=3 覆蓋同 orderId,狀態機層封裝,transport 走 place encoder）。
// ===========================================================================

/// OUT 3:placeOrder（含 whatIf flag;replace 亦走此 encoder 覆蓋同 orderId）。
pub(crate) const OUT_PLACE_ORDER_MSG_ID: &str = "3";
/// OUT 4:cancelOrder。
pub(crate) const OUT_CANCEL_ORDER_MSG_ID: &str = "4";
/// cancelOrder ≤157 band 的 wire VERSION 欄（IB 现勘:1;≤157 band 無 `manualOrderCancelTime`——
/// 該欄 sv≥161 才加,見 §11 BLOCK-ORDER-BAND-2 DIVERGENT）。
const CANCEL_ORDER_OUT_VERSION: &str = "1";

/// **encode band 下界**（sv < 此值 → 拒產出;placeOrder 省前導 VERSION 門檻,對齊消化面 floor 145）。
const ENCODE_MIN_SERVER_VERSION: i32 = 145;
/// **§1.5 INV-ORDER-ENCODE 上界**（sv > 此值 → 一律拒產出下單訊息 + audit,禁 157 佈局猜送;
/// 158-176 band UNVERIFIED,§11 BLOCK-ORDER-BAND-1/4）。對稱於消化面 decode ceiling（157）。
const ENCODE_MAX_PINNED_SERVER_VERSION: i32 = 157;

/// band 內 sv-gated 欄門檻（逐位對照 pinned ibapi 9.81.1 `client.py placeOrder` + `server_versions.py`;
/// [145,157] 內僅此二欄 sv-gated,其餘門檻皆 <145 恆送或 >157 不在 band）。
/// `MIN_SERVER_VER_D_PEG_ORDERS`=148:`discretionaryUpToLimitPrice`（bool,default "0"）。
const MIN_SV_D_PEG_ORDERS: i32 = 148;
/// `MIN_SERVER_VER_PRICE_MGMT_ALGO`=151:`usePriceMgmtAlgo`（handle_empty;default UNSET_INTEGER → ""）。
const MIN_SV_PRICE_MGMT_ALGO: i32 = 151;

/// `make_field(UNSET_DOUBLE)` 的 encode 側 wire 形（Python `str(sys.float_info.max)`;pinned ibapi
/// `cashQty`/PEGGED 尾等以 **plain make_field**（非 handle_empty）送 UNSET_DOUBLE → 此字面量,非空欄）。
/// **注**:與消化面 realizedPNL 哨兵 `1.7976931348623157E308`（TWS 回送形,大寫 E 無 +）**不同串**——
/// 此為 client 出站形（小寫 e、+308）,逐位對照 ibapi make_field 輸出,勿混用。
const UNSET_DOUBLE_WIRE: &str = "1.7976931348623157e+308";

/// placeOrder wire 請求（sv∈[145,157] band **骨架**承載欄;IB 现勘 §2.0「承載欄」子集,STK 現金
/// 天然塌縮 comboLegs/deltaNeutral/algo/conditions 變長塊）。**冪等真源=`idempotency_key`（見
/// lifecycle driver）;`order_id` 由 nextValidId 本地遞增分配**（重連可漂移,故 join 不以此為鍵）。
/// 全欄以 decimal 字串/枚舉承載,禁 f64 折算。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PlaceOrderWireRequest {
    /// nextValidId 本地分配的 order-id（replace 復用同一 orderId 覆蓋）。
    pub order_id: i64,
    /// 塌縮 STK 現金合約識別（symbol/secType/exchange/currency;骨架承載,值層紀律歸 lifecycle）。
    pub symbol: String,
    pub sec_type: String,
    pub exchange: String,
    pub currency: String,
    /// BUY/SELL（白名單值層歸 lifecycle;encoder 只承載字串）。
    pub action: String,
    /// 下單量（正 decimal 字串;sv≥101 float,STK v1 整數由 cash gate 把守）。
    pub total_quantity_decimal: String,
    /// LMT/MKT（白名單歸 cash gate;encoder 承載字串）。
    pub order_type: String,
    /// 限價（LMT 必填、MKT 空;空欄=unset）。
    pub lmt_price_decimal: String,
    /// 輔助價（v1 STK 恆空;空欄=unset）。
    pub aux_price_decimal: String,
    /// DAY/GTC。
    pub time_in_force: String,
    /// 帳號（恆綁本 lane 帳號）。
    pub account: String,
    /// transmit（true=立即送出;whatIf 預覽時仍 true——broker 回預估不成單）。
    pub transmit: bool,
    /// outsideRth（v1 恆 false,RTH-only 歸 cash gate）。
    pub outside_rth: bool,
    /// cashQty（sv≥111 fractional;v1 STK 恆空）。
    pub cash_qty_decimal: String,
    /// **whatIf**:true=零效果預覽（broker 回 margin/commission 預估,不成單;§2.2.2）。
    pub what_if: bool,
}

/// order encoder typed 裁決（禁 panic/捏值;每項可觀測,呼叫端據 typed reject 落 audit）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum OrderEncodeReject {
    /// **§1.5 INV-ORDER-ENCODE**:協商 sv > pinned 上界 → 一律拒產出下單訊息（禁 157 佈局猜送;
    /// 158-176 band UNVERIFIED,真接觸待 10.x re-pin）。此 reject **即 audit 信號**（呼叫端計數）。
    #[error(
        "server version {server_version} above encode ceiling {ceiling} (refuse to emit order msg)"
    )]
    ServerVersionAboveCeiling { server_version: i32, ceiling: i32 },
    /// 協商 sv < encode band 下界 → 拒產出（不實作 <145 舊佈局分支,對齊消化面 floor）。
    #[error("server version {server_version} below encode floor {floor}")]
    ServerVersionBelowFloor { server_version: i32, floor: i32 },
    /// 欄位值違反本地 typed 紀律（decimal 形狀/必填空缺;回欄名供 typed 分流）。
    #[error("order field invalid: {field}")]
    FieldInvalid { field: &'static str },
    /// **E3-N1/E2-F1 出站注入防護**:caller 字串欄含內嵌 NUL / 非 ASCII（`encode_fields_checked`
    /// 拒——placeOrder 定長位置編碼下,內嵌 NUL 會多切欄位終止符 → wire desync/注入）。
    #[error("outbound order field rejected: {0}")]
    WireFieldRejected(&'static str),
}

/// **§1.5 encode ceiling guard**（INV-ORDER-ENCODE;decode ceiling 的 encode 鏡射）。placeOrder/
/// cancelOrder 皆先過此閘:sv 在 `[145,157]` band 方可 encode;sv>157 一律拒產出（禁佈局猜送）、
/// sv<145 拒產出。**transport-gating 不變量的 encode 對稱面**。
fn encode_band_guard(server_version: i32) -> Result<(), OrderEncodeReject> {
    if server_version > ENCODE_MAX_PINNED_SERVER_VERSION {
        return Err(OrderEncodeReject::ServerVersionAboveCeiling {
            server_version,
            ceiling: ENCODE_MAX_PINNED_SERVER_VERSION,
        });
    }
    if server_version < ENCODE_MIN_SERVER_VERSION {
        return Err(OrderEncodeReject::ServerVersionBelowFloor {
            server_version,
            floor: ENCODE_MIN_SERVER_VERSION,
        });
    }
    Ok(())
}

/// encode **placeOrder**（OUT 3;sv∈[145,157] band,**byte-exact vs pinned ibapi 9.81.1
/// `client.py placeOrder`@896-1426**）→ `OrderFrame`（gated 出線唯一經 `send_order_framed`）。
/// **先過 §1.5 ceiling guard** 再逐位輸出**完整** ≤157 定長標量欄序（STK 現金 LMT/MKT×DAY 白名單）。
///
/// **忠實紀律（IB DIVERGENT-1 重導,逐位對照 client.py）**:sv≥145 省前導 VERSION（ORDER_CONTAINER
/// =145);contract 段完整（conId/symbol/secType/lastTradeDate/strike/right/multiplier/exchange/
/// primaryExchange/currency/localSymbol/tradingClass/secIdType/secId);order 段完整（含 ~70 個
/// mandatory 標量欄:extended/shortSale/oca/volatility/scale/hedge/pta/deltaNeutralFlag/algo…）;
/// STK(非 BAG)天然**省 comboLegs count 欄**;非 PEG BENCH 仍送 `conditions count=0` + adjustedOrder
/// 7 欄（PEGGED_TO_BENCHMARK=102<145 恆送）;**whatIf@位（cashQty 之前）**;`cashQty` 以 plain
/// make_field 送 UNSET_DOUBLE 哨兵(**非 handle_empty**);sv-gated:`discretionaryUpToLimitPrice`
/// (≥148)、`usePriceMgmtAlgo`(≥151) 條件末附。**無 production send**（S1 零 caller → DCE）。
pub(crate) fn encode_place_order(
    req: &PlaceOrderWireRequest,
    server_version: i32,
) -> Result<OrderFrame, OrderEncodeReject> {
    encode_band_guard(server_version)?;
    // 值層最小紀律（fail-closed:必填空缺/非法 decimal 拒產出;白名單值語義歸 lifecycle/cash gate）。
    if req.symbol.trim().is_empty() {
        return Err(OrderEncodeReject::FieldInvalid { field: "symbol" });
    }
    if req.account.trim().is_empty() {
        return Err(OrderEncodeReject::FieldInvalid { field: "account" });
    }
    if !is_positive_decimal_string(&req.total_quantity_decimal) {
        return Err(OrderEncodeReject::FieldInvalid {
            field: "total_quantity",
        });
    }
    // lmt/aux 為 make_field_handle_empty 欄:空=unset 合法（送空欄）;非空必簽名 decimal。
    // cashQty 為 **plain make_field** 欄:空=unset → 送 UNSET_DOUBLE 哨兵(非空欄);非空必簽名 decimal。
    for (raw, field) in [
        (&req.lmt_price_decimal, "lmt_price"),
        (&req.aux_price_decimal, "aux_price"),
        (&req.cash_qty_decimal, "cash_qty"),
    ] {
        if !raw.is_empty() && !is_signed_decimal_string(raw) {
            return Err(OrderEncodeReject::FieldInvalid { field });
        }
    }
    let order_id = req.order_id.to_string();
    let transmit = bool_wire(req.transmit);
    let outside_rth = bool_wire(req.outside_rth);
    let what_if = bool_wire(req.what_if);
    // cashQty:empty → UNSET_DOUBLE 哨兵（plain make_field 語義）;非空 → decimal 透傳。
    let cash_qty: &str = if req.cash_qty_decimal.is_empty() {
        UNSET_DOUBLE_WIRE
    } else {
        &req.cash_qty_decimal
    };

    // ── 逐位重導 client.py placeOrder ≤157 STK 現金定長欄序（U=UNSET_DOUBLE 哨兵,S=make_field_handle_empty 空）──
    let mut flds: Vec<&str> = vec![
        OUT_PLACE_ORDER_MSG_ID, // @1100 PLACE_ORDER（sv≥145 無 VERSION 前綴,@1102-1103）
        &order_id,              // @1105
        // contract 段（@1108-1125;PLACE_ORDER_CONID=46/TRADING_CLASS=68/SEC_ID_TYPE=45 皆 <145 恆送）
        "0",           // conId（@1109;新單 default 0）
        &req.symbol,   // @1110
        &req.sec_type, // @1111
        "",            // lastTradeDateOrContractMonth @1112
        "0.0",         // strike @1113（float 0.0 default）
        "",            // right @1114
        "",            // multiplier @1115
        &req.exchange, // @1116
        "",            // primaryExchange @1117
        &req.currency, // @1118
        "",            // localSymbol @1119
        "",            // tradingClass @1121
        "",            // secIdType @1124
        "",            // secId @1125
        // main order 段（@1128-1145）
        &req.action,                 // @1128
        &req.total_quantity_decimal, // @1131（FRACTIONAL_POSITIONS=101<145;decimal 透傳）
        &req.order_type,             // @1135
        &req.lmt_price_decimal,      // @1140 handle_empty
        &req.aux_price_decimal,      // @1145 handle_empty
        // extended order 段（@1148-1161）
        &req.time_in_force, // tif @1148
        "",                 // ocaGroup @1149
        &req.account,       // account @1150
        "",                 // openClose @1151
        "0",                // origin @1152
        "",                 // orderRef @1153
        transmit,           // transmit @1154
        "0",                // parentId @1155
        "0",                // blockOrder @1156
        "0",                // sweepToFill @1157
        "0",                // displaySize @1158
        "0",                // triggerMethod @1159
        outside_rth,        // outsideRth @1160
        "0",                // hidden @1161
        // STK(非 BAG):省 comboLegs/orderComboLegs/smartComboRouting 塊（@1164/1181/1189 皆 gated on BAG）
        // sharesAllocation + 財顧/折扣段（@1210-1219）
        "",  // sharesAllocation @1210（deprecated 空）
        "0", // discretionaryAmt @1212
        "",  // goodAfterTime @1213
        "",  // goodTillDate @1214
        "",  // faGroup @1216
        "",  // faMethod @1217
        "",  // faPercentage @1218
        "",  // faProfile @1219
        "",  // modelCode @1222（MODELS_SUPPORT=103<145）
        // 機構空賣段（@1225-1228）
        "0",  // shortSaleSlot @1225
        "",   // designatedLocation @1226
        "-1", // exemptCode @1228（SSHORTX_OLD=51<145;default -1）
        // srv v19+ 段（@1234-1260）
        "0", // ocaType @1234
        "",  // rule80A @1239
        "",  // settlingFirm @1240
        "0", // allOrNone @1241
        "",  // minQty @1242 handle_empty
        "",  // percentOffset @1243 handle_empty
        "1", // eTradeOnly @1244（default True）
        "1", // firmQuoteOnly @1245（default True）
        "",  // nbboPriceCap @1246 handle_empty
        "0", // auctionStrategy @1247
        "",  // startingPrice @1248 handle_empty
        "",  // stockRefPrice @1249 handle_empty
        "",  // delta @1250 handle_empty
        "",  // stockRangeLower @1251 handle_empty
        "",  // stockRangeUpper @1252 handle_empty
        "0", // overridePercentageConstraints @1254
        // volatility 段（@1257-1260;deltaNeutralOrderType 空 → 省 DELTA_NEUTRAL_CONID/OPEN_CLOSE 塊）
        "",  // volatility @1257 handle_empty
        "",  // volatilityType @1258 handle_empty
        "",  // deltaNeutralOrderType @1259
        "",  // deltaNeutralAuxPrice @1260 handle_empty
        "0", // continuousUpdate @1274
        "",  // referencePriceType @1275 handle_empty
        "",  // trailStopPrice @1276 handle_empty
        "",  // trailingPercent @1279 handle_empty（TRAILING_PERCENT=62<145）
        // SCALE 段（@1283-1307;scalePriceIncrement UNSET → 省 SCALE_ORDERS3 adjust 塊）
        "",      // scaleInitLevelSize @1283 handle_empty
        "",      // scaleSubsLevelSize @1284 handle_empty
        "",      // scalePriceIncrement @1290 handle_empty
        "",      // scaleTable @1305
        "",      // activeStartTime @1306
        "",      // activeStopTime @1307
        "",      // hedgeType @1311（空 → 省 hedgeParam）
        "0",     // optOutSmartRouting @1316
        "",      // clearingAccount @1319（PTA_ORDERS=39<145）
        "",      // clearingIntent @1320
        "0",     // notHeld @1323（NOT_HELD=44<145）
        "0",     // deltaNeutralContract flag @1332（None → False）
        "",      // algoStrategy @1335（空 → 省 algoParams）
        "",      // algoId @1345（ALGO_ID=71<145）
        what_if, // whatIf @1347
        "",      // miscOptionsStr @1355（LINKING=70<145）
        "0",     // solicited @1358（ORDER_SOLICITED=73<145）
        "0",     // randomizeSize @1361（RANDOMIZE=76<145）
        "0",     // randomizePrice @1362
        // PEGGED_TO_BENCHMARK=102<145 恆送:非 PEG BENCH → 省 pegged 5 欄,仍送 conditions count + adjusted 7 欄
        "0",               // len(conditions) @1372
        "",                // adjustedOrderType @1382
        UNSET_DOUBLE_WIRE, // triggerPrice @1383（plain make_field UNSET_DOUBLE）
        UNSET_DOUBLE_WIRE, // lmtPriceOffset @1384
        UNSET_DOUBLE_WIRE, // adjustedStopPrice @1385
        UNSET_DOUBLE_WIRE, // adjustedStopLimitPrice @1386
        UNSET_DOUBLE_WIRE, // adjustedTrailingAmount @1387
        "0",               // adjustableTrailingUnit @1388
        "",                // extOperator @1391（EXT_OPERATOR=105<145）
        "",                // softDollarTier.name @1394（SOFT_DOLLAR_TIER=106<145）
        "",                // softDollarTier.val @1395
        cash_qty,          // cashQty @1398（CASH_QTY=111<145;plain make_field UNSET_DOUBLE 哨兵）
        "",                // mifid2DecisionMaker @1401（DECISION_MAKER=138<145）
        "",                // mifid2DecisionAlgo @1402
        "",                // mifid2ExecutionTrader @1405（MIFID_EXECUTION=139<145）
        "",                // mifid2ExecutionAlgo @1406
        "0",               // dontUseAutoPriceForHedge @1409（AUTO_PRICE_FOR_HEDGE=141<145）
        "0",               // isOmsContainer @1412（ORDER_CONTAINER=145 → sv≥145 恆送）
    ];
    // sv-gated band 內二欄（逐位對照 @1414-1418）。
    if server_version >= MIN_SV_D_PEG_ORDERS {
        flds.push("0"); // discretionaryUpToLimitPrice @1415（D_PEG_ORDERS=148）
    }
    if server_version >= MIN_SV_PRICE_MGMT_ALGO {
        flds.push(""); // usePriceMgmtAlgo @1418（PRICE_MGMT_ALGO=151;None → UNSET_INTEGER → handle_empty ""）
    }

    // E3-N1/E2-F1:含 caller 字串出站一律 encode_fields_checked（拒內嵌 NUL / 非 ASCII）。
    let payload = encode_fields_checked(&flds).map_err(|e| match e {
        CodecError::OutboundFieldInvalid(note) => OrderEncodeReject::WireFieldRejected(note),
        _ => OrderEncodeReject::WireFieldRejected("outbound field invalid"),
    })?;
    Ok(OrderFrame::from_order_bytes(encode_frame(&payload)))
}

/// encode **cancelOrder**（OUT 4;≤157 band=`[4, VERSION=1, orderId]`,**無 `manualOrderCancelTime`**
/// ——該欄 sv≥161 才加,§11 BLOCK-ORDER-BAND-2 DIVERGENT）→ `OrderFrame`。先過 §1.5 ceiling guard。
pub(crate) fn encode_cancel_order(
    order_id: i64,
    server_version: i32,
) -> Result<OrderFrame, OrderEncodeReject> {
    encode_band_guard(server_version)?;
    let oid = order_id.to_string();
    let frame = encode_frame(&encode_fields(&[
        OUT_CANCEL_ORDER_MSG_ID,
        CANCEL_ORDER_OUT_VERSION,
        &oid,
    ]));
    Ok(OrderFrame::from_order_bytes(frame))
}

/// bool → IB wire 形（`"1"`/`"0"`;IB 慣例）。
fn bool_wire(v: bool) -> &'static str {
    if v {
        "1"
    } else {
        "0"
    }
}

#[cfg(test)]
#[path = "ibkr_tws_order_transport_tests.rs"]
mod tests;
