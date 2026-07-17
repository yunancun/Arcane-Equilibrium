//! MODULE_NOTE
//! 模塊用途：IBKR **W7-S4a option B HMAC effect-activation 簽名層（新軸;憲法面）**
//!   （IBKR_TODO §5-W7;設計文檔 §4 option B HMAC）。paper order-write / 資本暴露面
//!   （AMD-2026-07-08-01 澄清 #2）強制升級 option B——HMAC-SHA256 簽名 leg **疊在** W8a
//!   activation envelope shape **之上**（envelope 只承載綁定,簽名是獨立驗證 leg,不入 envelope 型別）。
//! 主要區段：
//!   - (a) `canonical_effect_payload`：pipe-separated 正規化 payload（版本前綴 + lane/broker/env/
//!     scope/operation/build-SHA/account-fingerprint/nonce/issued/expiry/兩 epoch）——Operator
//!     out-of-band 簽名對象。任何欄漂移/endianness drift 立刻改變 payload → 簽名不符 → 拒。
//!   - (b) `compute_effect_signature`：hex-lowercase HMAC-SHA256(payload) keyed by Operator 驗證金鑰。
//!   - (c) `constant_time_eq`：定時比對（非 short-circuit;防 timing-oracle,承 live_authorization 紀律）。
//!   - (d) `EffectSignatureVerifier`：**金鑰 custody（CC-B1）** + caller 供給的 opaque out-of-band
//!     簽名 blob（CC-B3:IPC 只轉 opaque blob,不解析）。`from_secret_slot` 從 **新 secret slot**
//!     （`OPENCLAW_IBKR_EFFECT_ACTIVATION_SIGNING_KEY`,**非** Bybit `OPENCLAW_LIVE_AUTH_SIGNING_KEY`）
//!     讀金鑰;**缺席 fail-closed**（無金鑰 → `SigningKeyMissing` → 拒,絕不放行）;輪替=換 slot 內容
//!     後重建 verifier（讀取每次構造刷新）。
//! 依賴：`secret_env`（新 slot custody）、`hmac`/`sha2`/`hex`、`openclaw_types`（envelope + BrokerOperation）。
//! 硬邊界：
//!   - **禁擴鐵律（設計 §4.1）**：W2 seal 軸（6-binding/批准檔/ledger）+ Bybit auth 軸
//!     （`authorization.json`/`OPENCLAW_LIVE_AUTH_SIGNING_KEY` env）**皆不複用/擴充**到本軸——
//!     option B 是獨立新軸;本模塊**刻意不** import/引用 `live_authorization` 或 W2 seal producer。
//!   - **CC-B1 金鑰 custody**：Rust secret-slot（新 slot,`secret_env::var_or_file` 支援 `_FILE`
//!     companion 檔式 custody,避免長壽命 env 明文）;缺席 fail-closed（非放行）;無 Python/GUI 明文 ingress。
//!   - **CC-B3 cross-runtime**：簽名/驗證全 Rust-owned;caller 供 opaque 簽名 blob（S4a 不落 IPC,
//!     但型別上簽名只是 `&str` opaque hex——未來 IPC 只轉此 blob,不解析）。
//!   - **production 恆拒不變量**：本模塊只提供「驗證機器」;production 無金鑰 slot（缺席→拒）、
//!     無真簽名 envelope provider 構造 → 放行臂不可達。真活化=EA5 Operator-gated,本模塊絕不簽發。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 IPC（S4b）。

// dormant 姿態：本模塊 W7-S4a 落地時 **0 production caller**（`check_effect_contact` 的
// production 消費要到 EA5/W8 接真 provider;S4a 唯測試域構造 verifier）。final binary 因 0
// caller 被 DCE（同 order_transport / envelope_check pre-W8 姿態）。allow(dead_code) 必須保留;
// W8 接 production effect provider 時移出。
#![allow(dead_code)]

use hmac::{Hmac, Mac};
use sha2::Sha256;

use openclaw_types::{BrokerOperation, IbkrActivationEnvelopeV1};

use crate::secret_env;

type HmacSha256 = Hmac<Sha256>;

/// **新 secret slot 名**（金鑰 custody;`secret_env::var_or_file` 支援 `<NAME>_FILE` companion 檔式
/// custody）。**刻意非** Bybit `OPENCLAW_LIVE_AUTH_SIGNING_KEY`——option B 是獨立新軸（禁擴鐵律）。
pub(crate) const EFFECT_SIGNING_KEY_SLOT: &str = "OPENCLAW_IBKR_EFFECT_ACTIVATION_SIGNING_KEY";

/// canonical payload 版本前綴（布局變更時遞增;drift guard——Operator 簽名端必對齊此版本與欄序）。
pub(crate) const EFFECT_SIG_PAYLOAD_VERSION: u32 = 1;

/// option B 簽名/驗證的 typed 錯誤面（各變體對應不同拒因;fail-closed 先寫拒絕路徑）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub(crate) enum EffectAuthError {
    /// 金鑰 slot 缺席（CC-B1 fail-closed）——無金鑰即無法驗證 → 拒（絕不放行）。
    #[error("effect activation signing key slot absent — fail-closed deny")]
    SigningKeyMissing,
    /// HMAC 簽名與 canonical payload 不符（篡改 / 錯金鑰 / payload 漂移）。
    #[error("effect activation signature invalid")]
    BadSignature,
}

/// **canonical payload**（pipe-separated;Operator out-of-band 簽名對象）。Rust 與 Operator 簽名端
/// 必 byte-for-byte 對齊此格式。含**版本前綴**（drift guard）+ 綁定全欄:contract/source/lane/
/// broker/environment/scope/**operation verb**/build-SHA/account-fingerprint/nonce/issued/expiry/
/// revocation-epoch/kill-switch-epoch。operation verb 入 payload → 簽名綁定精確操作面（submit 簽名
/// 不能拿去 cancel）;nonce+expiry+epoch 入 payload → 綁定單次活化窗（防跨窗/replay 重用）。
pub(crate) fn canonical_effect_payload(
    envelope: &IbkrActivationEnvelopeV1,
    operation: BrokerOperation,
) -> String {
    format!(
        "{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
        EFFECT_SIG_PAYLOAD_VERSION,
        envelope.contract_id,
        envelope.source_version,
        envelope.asset_lane.as_str(),
        envelope.broker.as_str(),
        envelope.environment.as_str(),
        envelope.operation_scope.as_str(),
        operation.as_str(),
        envelope.build_git_sha,
        envelope.account_fingerprint,
        envelope.activation_nonce,
        envelope.issued_at_ms,
        envelope.expires_at_ms,
        envelope.revocation_epoch,
        envelope.kill_switch_epoch,
    )
}

/// 計算 canonical payload 的 hex-lowercase HMAC-SHA256（keyed by Operator 驗證金鑰）。
pub(crate) fn compute_effect_signature(
    envelope: &IbkrActivationEnvelopeV1,
    operation: BrokerOperation,
    operator_key: &str,
) -> String {
    let payload = canonical_effect_payload(envelope, operation);
    let mut mac = HmacSha256::new_from_slice(operator_key.as_bytes())
        .expect("HMAC-SHA256 accepts any key size");
    mac.update(payload.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// **定時比對**（非 short-circuit）:長度不等即拒;等長則 XOR-累積全部位元組,不因首個差異位元組
/// 提前返回——防 HMAC tag 的 timing-oracle（承 live_authorization::constant_time_eq 紀律）。
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

/// **option B 簽名驗證器**:金鑰 custody（CC-B1）+ caller 供給的 opaque out-of-band 簽名 blob（CC-B3）。
///
/// - `operator_key`：Operator 驗證金鑰,從**新 secret slot** 讀（缺席=`None`→fail-closed）。**憑證
///   custody 只在此持有,不序列化/不日誌/不回傳/不入 Python**。
/// - `provided_signature_hex`：caller 供給的 out-of-band Operator 簽名（hex）——**opaque blob**,
///   本驗證器只拿來與重算值定時比對,不解析內容（未來 IPC 只轉此 blob,CC-B3）。
///
/// **fail-closed**:金鑰缺席 → `verify` 回 `SigningKeyMissing`（絕不放行）;簽名不符 → `BadSignature`。
pub(crate) struct EffectSignatureVerifier {
    operator_key: Option<String>,
    provided_signature_hex: String,
}

impl EffectSignatureVerifier {
    /// **production custody 構造**:從新 secret slot 讀 Operator 驗證金鑰（`secret_env::var_or_file`;
    /// 每次構造刷新讀取 → 輪替=換 slot 內容後重建 verifier)。金鑰缺席 → `operator_key=None` →
    /// `verify` fail-closed。`provided_signature_hex` = caller out-of-band 簽名 blob（opaque）。
    pub(crate) fn from_secret_slot(provided_signature_hex: String) -> Self {
        Self {
            operator_key: secret_env::var_or_file(EFFECT_SIGNING_KEY_SLOT),
            provided_signature_hex,
        }
    }

    /// 測試域構造（注入金鑰;`#[cfg(test)]` → production 無此符號,不成金鑰注入面）。
    #[cfg(test)]
    pub(crate) fn with_key(operator_key: Option<String>, provided_signature_hex: String) -> Self {
        Self {
            operator_key,
            provided_signature_hex,
        }
    }

    /// **驗證 leg**:重算 canonical payload 的 HMAC == caller 供給的 opaque 簽名 blob（定時比對）。
    /// fail-closed:金鑰缺席先拒（`SigningKeyMissing`,不做任何比對）;不符回 `BadSignature`。
    pub(crate) fn verify(
        &self,
        envelope: &IbkrActivationEnvelopeV1,
        operation: BrokerOperation,
    ) -> Result<(), EffectAuthError> {
        let key = self
            .operator_key
            .as_deref()
            .ok_or(EffectAuthError::SigningKeyMissing)?;
        let expected = compute_effect_signature(envelope, operation, key);
        if !constant_time_eq(expected.as_bytes(), self.provided_signature_hex.as_bytes()) {
            return Err(EffectAuthError::BadSignature);
        }
        Ok(())
    }
}

#[cfg(test)]
#[path = "ibkr_effect_activation_tests.rs"]
mod tests;
