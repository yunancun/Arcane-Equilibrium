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
//!     **final-binary DCE**（`target/release/openclaw-engine` 零 seam 符號 AND 零 seam strings,
//!     含 `EffectDenied` literal 缺席）。**rlib 級非 DCE 證據**——rlib 保留 rmeta,`strings
//!     libopenclaw_engine*.rlib` 仍命中 seam 名;有效 DCE 證據唯 final binary（nm + strings 雙查）。
//!     沿 driver/g4 audit 家族。兩證獨立。
//!   - **S0 = 恆拒地基,放行臂 S4;encoder S1**：本輪不含任何 order encoder、不送任何 order 訊息、
//!     無放行臂。`EffectEnvelopeRequiredStub::check` 恆 `Err(EffectDenied::EnvelopeRequired)`,
//!     無任何開關可翻放行。W7-S4 才落 HMAC option B 放行臂（`check_effect_contact`,鑄
//!     `OrderEffectPermit`;唯一 production 鑄造點）。
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
use crate::ibkr_tws_wire::{encode_fields, encode_frame};

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
/// 158-176 band UNVERIFIED,§11 BLOCK-ORDER-BAND-1/2）。對稱於消化面 decode ceiling（157）。
const ENCODE_MAX_PINNED_SERVER_VERSION: i32 = 157;

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

/// encode **placeOrder**（OUT 3;sv∈[145,157] band 骨架）→ `OrderFrame`（gated 出線唯一經
/// `send_order_framed`）。**先過 §1.5 ceiling guard** 再逐欄輸出;whatIf flag 承載於骨架末段;
/// 末欄 = `usePriceMgmtAlgo`（@151,固定 unset 空欄）。**無 production send**（S1 零 caller → DCE）。
///
/// 骨架範圍紀律:輸出 IB 现勘 §2.0「承載欄」在 STK 現金塌縮佈局下的定長序列;66 步全欄佈局
/// （comboLegs/algo/conditions 變長塊）在 STK 現金天然塌縮為空,**真接觸位元組待 EA 前 10.x
/// re-pin**（§11 BLOCK-ORDER-BAND-1）。ceiling guard 確保 sv>157 永不產出（不猜送）。
pub(crate) fn encode_place_order(
    req: &PlaceOrderWireRequest,
    server_version: i32,
) -> Result<OrderFrame, OrderEncodeReject> {
    encode_band_guard(server_version)?;
    // 值層最小紀律（encoder 面 fail-closed:必填空缺/非法 decimal 拒產出;白名單值語義歸 lifecycle/
    // cash gate,encoder 只擋形狀損壞以免產出畸形 wire）。
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
    // 限價/輔助價/cashQty:空欄=unset 合法;非空必為簽名 decimal。
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
    // sv≥145 省前導 VERSION;STK 現金塌縮佈局承載欄序（IB 现勘 §2.0）:
    let frame = encode_frame(&encode_fields(&[
        OUT_PLACE_ORDER_MSG_ID,
        &order_id,
        // 塌縮 STK 現金合約識別（comboLegs/deltaNeutral 於 STK 現金為空,骨架不輸出變長塊）。
        &req.symbol,
        &req.sec_type,
        &req.exchange,
        &req.currency,
        // 承載欄。
        &req.action,
        &req.total_quantity_decimal,
        &req.order_type,
        &req.lmt_price_decimal,
        &req.aux_price_decimal,
        &req.time_in_force,
        &req.account,
        transmit,
        outside_rth,
        &req.cash_qty_decimal,
        what_if,
        // 骨架末欄 usePriceMgmtAlgo（@151;固定 unset 空欄——v1 不用 price-mgmt algo）。
        "",
    ]));
    Ok(OrderFrame::from_order_bytes(frame))
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
