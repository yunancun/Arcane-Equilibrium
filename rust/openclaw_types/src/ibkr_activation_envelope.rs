//! IBKR **W8a `ibkr_activation_envelope_v1` readonly-scope 最小實體**（source-only,
//! Rust 為 authority;IBKR_TODO §5-W8a / AMD-2026-07-11-01 活化鐵律）。
//!
//! 本檔是活化 envelope 的**型別契約層**:把 §2 活化鐵律的綁定全清單逐欄變成 typed
//! shape + fail-closed 校驗。不開 socket、不啟 Gateway、不讀 secret、不做任何 IO、
//! 不持牆鐘（`validate(now_ms)` 注入時鐘）;純資料 + 純函數。
//!
//! **範圍紀律（D2 carve）**:本切片只實作 **readonly 單值白名單** operation scope——
//! paper / tiny_live / live / shadow 等表外值一律 `UnknownDenied`（歸 W8 全包;W8 落地
//! 時吸收本檔,共用同一驗證代碼路徑,禁兩套語義漂移）。envelope 型別**只承載與校驗,
//! 不簽發**:簽發/活化是 EA 跑道的 Operator 動作,本 crate 無任何簽發路徑。
//!
//! **鐵律逐欄對照（§2 活化鐵律 → 欄位）**:lane→`asset_lane`、broker→`broker`、
//! environment→`environment`、operation scope→`operation_scope`、`BUILD_GIT_SHA`→
//! `build_git_sha`、account fingerprint→`account_fingerprint`、Gateway/session
//! attestation fingerprint→`session_attestation_fingerprint`、risk-config hash+limits→
//! `risk_config_hash`+三 limits 欄（readonly 恆零——order 面在型別層即無額度）、
//! Cost Gate/Guardian/Decision Lease lineage→三 lineage 欄、Operator identity→
//! `operator_identity`、nonce→`activation_nonce`（原子消費歸 engine 驗證器）、
//! issued-at/expiry→`issued_at_ms`/`expires_at_ms`、revocation epoch→`revocation_epoch`、
//! kill-switch epoch→`kill_switch_epoch`（兩 epoch 的「與當前值比對」需 runtime 姿態,
//! 歸 engine 驗證器;本層只承載綁定值）。

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

/// 契約 id（engine 驗證器 / audit lineage 對齊）。
pub const IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID: &str = "ibkr_activation_envelope_v1";

/// 活化窗上限（24h;EA4 readonly soak 為**每日活化**姿態——time-bounded 是鐵律,
/// 超過一日的 readonly envelope 即非 time-bounded,結構性拒）。
pub const IBKR_ACTIVATION_WINDOW_MAX_MS: u64 = 24 * 60 * 60 * 1000;

/// operation scope 白名單枚舉（**readonly + paper 雙值**;W8a→W7-S4 擴充後）。
/// tiny_live/live/shadow 等表外 scope 一律 `UnknownDenied`——不是「未來擴充位」,是
/// fail-closed 分類:W8 全包引入其他 scope 時再擴白名單並吸收本切片。
///
/// **W7-S4a 擴充（effect 面）**:新增 `Paper` scope——paper order-write effect 授權面的
/// scope 綁定。**production 恆拒不變量不受影響**:Paper scope 的 shape 校驗
/// （`validate_paper_effect`）+ engine `check_effect_contact` 放行臂在 production **不可達**
/// （無真簽名 envelope provider/無金鑰）;唯一鑄造點 = `check_effect_contact` `Ok` 臂,
/// 其 production 零 caller → DCE。Paper scope 只讓「effect 授權機器」存在且經測試,不落活化。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrActivationOperationScopeV1 {
    /// 唯讀接觸（account/positions/market-data 讀面;零 order verb）。
    Readonly,
    /// paper order-write effect 授權面（W7-S4a;paper submit/cancel/replace）。
    /// **仍非活化**:envelope 存在 ≠ 活化,真簽名/金鑰/放行是 EA5 Operator-gated。
    Paper,
    /// 契約 default / 白名單外 scope 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrActivationOperationScopeV1 {
    fn default() -> Self {
        // fail-closed 預設＝未知拒。
        Self::UnknownDenied
    }
}

impl IbkrActivationOperationScopeV1 {
    /// scope 字串 → 白名單枚舉（**精確匹配**;表外一律 `UnknownDenied`,含 tiny_live/
    /// live——該值歸 W8,本切片不承認）。W7-S4a 起承認 `"paper"`（effect 面）。
    pub fn classify_scope(raw: &str) -> Self {
        match raw {
            "readonly" => Self::Readonly,
            "paper" => Self::Paper,
            _ => Self::UnknownDenied,
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Readonly => "readonly",
            Self::Paper => "paper",
            Self::UnknownDenied => "unknown_denied",
        }
    }
}

/// `ibkr_activation_envelope_v1` readonly-scope 最小實體（§2 活化鐵律綁定全清單）。
///
/// 不變量:envelope 有效 ≠ 免除憑證/entitlement/market-hours/safety checks;envelope
/// 存在 ≠ 活化（nonce 原子消費 + epoch 比對 + 姿態綁定在 engine 驗證器）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrActivationEnvelopeV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// environment 綁定（本切片恆 `ReadOnly`;paper/shadow/live 拒——歸 W8）。
    pub environment: BrokerEnvironment,
    /// operation scope（readonly 單值白名單;表外 `UnknownDenied` 拒）。
    pub operation_scope: IbkrActivationOperationScopeV1,
    /// 精確 build 綁定（40-hex git SHA;「等於現 binary `BUILD_GIT_SHA`」歸 engine）。
    pub build_git_sha: String,
    /// 帳戶指紋（sha256 hex;明文帳號永不入 envelope）。
    pub account_fingerprint: String,
    /// Gateway/session attestation 指紋（sha256 hex;W5-S4 attestation 面派生）。
    pub session_attestation_fingerprint: String,
    /// risk-config 內容 hash（sha256 hex;config 漂移即綁定失效）。
    pub risk_config_hash: String,
    /// 單筆 order notional 上限（定點字串;readonly scope 恆 `"0"`——order 面零額度,
    /// 「readonly + 任何 order verb → 結構性拒」的型別層投影;禁 f64）。
    pub max_order_notional_usd_decimal: String,
    /// 總 position notional 上限（定點字串;readonly 恆 `"0"`;禁 f64）。
    pub max_position_notional_usd_decimal: String,
    /// 每日 order 數上限（readonly 恆 0）。
    pub max_orders_per_day: u32,
    /// global Cost Gate lineage 指紋（sha256 hex;Cost Gate 不得因本 lane 降低）。
    /// 本欄承載指紋;**現值綁定比對歸 W8 落實**,本切片僅 shape 驗證（CC-NOTE-3）。
    pub cost_gate_lineage: String,
    /// Guardian lineage 指紋（sha256 hex）。
    pub guardian_lineage: String,
    /// Decision Lease lineage 指紋（sha256 hex）。
    pub decision_lease_lineage: String,
    /// Operator identity（authenticated 活化紀錄的簽發者身分;非空）。
    pub operator_identity: String,
    /// 活化 nonce（64-hex;**單次消費**——原子消費/防 replay 在 engine 驗證器）。
    pub activation_nonce: String,
    /// 簽發時刻（epoch ms;0=缺,拒）。
    pub issued_at_ms: u64,
    /// 失效時刻（epoch ms;`now >= expires` 即拒;窗長 ≤ 24h）。
    pub expires_at_ms: u64,
    /// 簽發時綁定的 revocation epoch（「與當前 epoch 相等」比對歸 engine）。
    pub revocation_epoch: u64,
    /// 簽發時綁定的 kill-switch epoch（同上,比對歸 engine）。
    pub kill_switch_epoch: u64,
    // ---- 負空間安全束（envelope 為授權事實承載,恆 false）----
    /// envelope 承載過程永不路由訂單。
    pub order_routed: bool,
    /// envelope 永不承載 secret 內容（憑證 custody 是 Rust secret-slot 事,不入授權面）。
    pub secret_content_serialized: bool,
}

impl Default for IbkrActivationEnvelopeV1 {
    /// fail-closed 預設:每一綁定欄都取「校驗必拒」值（含 environment 取
    /// `LiveReservedDenied`、scope 取 `UnknownDenied`——default 不存在任何可誤放行位）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            operation_scope: IbkrActivationOperationScopeV1::UnknownDenied,
            build_git_sha: String::new(),
            account_fingerprint: String::new(),
            session_attestation_fingerprint: String::new(),
            risk_config_hash: String::new(),
            max_order_notional_usd_decimal: String::new(),
            max_position_notional_usd_decimal: String::new(),
            max_orders_per_day: 0,
            cost_gate_lineage: String::new(),
            guardian_lineage: String::new(),
            decision_lease_lineage: String::new(),
            operator_identity: String::new(),
            activation_nonce: String::new(),
            issued_at_ms: 0,
            expires_at_ms: 0,
            revocation_epoch: 0,
            kill_switch_epoch: 0,
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrActivationEnvelopeV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;時刻為固定 epoch ms 常量,測試以
    /// 注入 `now_ms` 相對取值——無牆鐘依賴,非 time-bomb）。
    pub fn readonly_fixture() -> Self {
        Self {
            contract_id: IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::ReadOnly,
            operation_scope: IbkrActivationOperationScopeV1::Readonly,
            build_git_sha: "f".repeat(40),
            account_fingerprint: "b".repeat(64),
            session_attestation_fingerprint: "c".repeat(64),
            risk_config_hash: "d".repeat(64),
            max_order_notional_usd_decimal: "0".to_string(),
            max_position_notional_usd_decimal: "0".to_string(),
            max_orders_per_day: 0,
            cost_gate_lineage: "1".repeat(64),
            guardian_lineage: "2".repeat(64),
            decision_lease_lineage: "3".repeat(64),
            operator_identity: "operator:fixture".to_string(),
            activation_nonce: "e".repeat(64),
            issued_at_ms: 1_772_232_000_000,
            expires_at_ms: 1_772_235_600_000,
            revocation_epoch: 1,
            kill_switch_epoch: 1,
            ..Self::default()
        }
    }

    /// **W7-S4a paper-scope effect envelope 代表 fixture**（`validate_paper_effect` 基線;
    /// 時刻為固定 epoch ms 常量,測試以注入 `now_ms` 相對取值——無牆鐘依賴,非 time-bomb）。
    /// 與 `readonly_fixture` 差異僅 scope-specific 面:environment=`Paper`、scope=`Paper`、
    /// order/position 額度=正定點、每日 order 數 ≥1。**仍非活化**（簽名/金鑰/放行 EA5-gated）。
    pub fn paper_effect_fixture() -> Self {
        Self {
            environment: BrokerEnvironment::Paper,
            operation_scope: IbkrActivationOperationScopeV1::Paper,
            max_order_notional_usd_decimal: "1000".to_string(),
            max_position_notional_usd_decimal: "5000".to_string(),
            max_orders_per_day: 10,
            ..Self::readonly_fixture()
        }
    }

    /// readonly-scope envelope 校驗（零副作用;注入 `now_ms`,無牆鐘）。fail-closed:任一
    /// 綁定欄缺/壞/過期即拒。**先寫拒絕路徑**:本函數只累積 blocker,不存在任何提前放行分支。
    ///
    /// **語意不變（W7-S4a 重構）**:scope-independent 綁定欄檢查抽入
    /// `push_scope_independent_blockers`（readonly 與 paper 共用同一校驗真源,禁語義漂移）;
    /// readonly-specific 面（environment==ReadOnly / scope==Readonly / limits 恆零）留在本函數。
    /// 對 readonly-scope 輸入的 blocker 集與重構前**完全一致**（`.contains()`/`.accepted` 語意保真）。
    pub fn validate(&self, now_ms: u64) -> IbkrActivationEnvelopeVerdict {
        use IbkrActivationEnvelopeBlocker as B;

        let mut blockers = Vec::new();
        self.push_scope_independent_blockers(now_ms, &mut blockers);

        // ── readonly-specific 面（environment 白名單=ReadOnly 單值;scope==Readonly;order 面零額度）──
        if self.environment != BrokerEnvironment::ReadOnly {
            blockers.push(B::EnvironmentNotReadonly);
        }
        if self.operation_scope != IbkrActivationOperationScopeV1::Readonly {
            blockers.push(B::OperationScopeDenied);
        }
        // readonly scope 的 limits 恆零:非 `"0"` / 非 0 即拒（order 面在額度層也無路）。
        if self.max_order_notional_usd_decimal != "0" {
            blockers.push(B::OrderNotionalLimitNotZero);
        }
        if self.max_position_notional_usd_decimal != "0" {
            blockers.push(B::PositionNotionalLimitNotZero);
        }
        if self.max_orders_per_day != 0 {
            blockers.push(B::OrdersPerDayLimitNotZero);
        }

        IbkrActivationEnvelopeVerdict::new(blockers)
    }

    /// **W7-S4a paper-scope effect envelope 校驗**（零副作用;注入 `now_ms`,無牆鐘）。
    /// 與 `validate()` 共用 `push_scope_independent_blockers`（單一校驗真源;禁兩套語義漂移）,
    /// 差異僅 scope-specific 面:environment==`Paper`、scope==`Paper`、order 額度須為正定點
    /// （effect 面需真額度;**現值綁定比對歸 W8/EA5,本切片僅 shape 驗證**）。
    ///
    /// **不變量**:本函數只 shape-驗證,回 accepted 僅代表 paper envelope 型別/綁定/時窗合格;
    /// **活化裁決在 engine `check_effect_contact`**（seal≠活化 + posture 綁定 + option B HMAC 簽名
    /// + nonce 原子消費 + 唯一鑄造點）。envelope 存在 ≠ 活化。
    pub fn validate_paper_effect(&self, now_ms: u64) -> IbkrActivationEnvelopeVerdict {
        use IbkrActivationEnvelopeBlocker as B;

        let mut blockers = Vec::new();
        self.push_scope_independent_blockers(now_ms, &mut blockers);

        // ── paper-specific 面（environment==Paper;scope==Paper;order 額度正定點 shape）──
        if self.environment != BrokerEnvironment::Paper {
            blockers.push(B::PaperEnvironmentMismatch);
        }
        if self.operation_scope != IbkrActivationOperationScopeV1::Paper {
            blockers.push(B::OperationScopeDenied);
        }
        // paper effect: order/position 額度須為正定點字串（shape;禁 f64;值綁定歸 W8/EA5）。
        if !crate::is_positive_decimal_string(&self.max_order_notional_usd_decimal) {
            blockers.push(B::PaperOrderNotionalLimitInvalid);
        }
        if !crate::is_positive_decimal_string(&self.max_position_notional_usd_decimal) {
            blockers.push(B::PaperPositionNotionalLimitInvalid);
        }
        if self.max_orders_per_day == 0 {
            blockers.push(B::PaperOrdersPerDayLimitInvalid);
        }

        IbkrActivationEnvelopeVerdict::new(blockers)
    }

    /// scope-independent 綁定欄檢查（readonly 與 paper 共用;§2 活化鐵律的 scope 無關面）。
    /// 涵蓋 contract_id/source_version/lane/broker/build-SHA/三指紋+risk hash/三 lineage/
    /// operator/nonce/issued-at/window/expiry/負空間束——**不含** environment/scope/limits
    /// （scope-specific,由各 `validate*` 自持）。
    fn push_scope_independent_blockers(
        &self,
        now_ms: u64,
        blockers: &mut Vec<IbkrActivationEnvelopeBlocker>,
    ) {
        use IbkrActivationEnvelopeBlocker as B;

        if self.contract_id != IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID {
            blockers.push(B::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(B::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(B::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(B::WrongBroker);
        }
        if !is_git_sha40_hex(&self.build_git_sha) {
            blockers.push(B::BuildGitShaInvalid);
        }
        if !is_sha256_hex(&self.account_fingerprint) {
            blockers.push(B::AccountFingerprintInvalid);
        }
        if !is_sha256_hex(&self.session_attestation_fingerprint) {
            blockers.push(B::SessionAttestationFingerprintInvalid);
        }
        if !is_sha256_hex(&self.risk_config_hash) {
            blockers.push(B::RiskConfigHashInvalid);
        }
        if !is_sha256_hex(&self.cost_gate_lineage) {
            blockers.push(B::CostGateLineageInvalid);
        }
        if !is_sha256_hex(&self.guardian_lineage) {
            blockers.push(B::GuardianLineageInvalid);
        }
        if !is_sha256_hex(&self.decision_lease_lineage) {
            blockers.push(B::DecisionLeaseLineageInvalid);
        }
        if self.operator_identity.trim().is_empty() {
            blockers.push(B::OperatorIdentityMissing);
        }
        if !is_sha256_hex(&self.activation_nonce) {
            blockers.push(B::ActivationNonceInvalid);
        }
        if self.issued_at_ms == 0 {
            blockers.push(B::MissingIssuedAt);
        } else if self.issued_at_ms > now_ms {
            // 未來簽發＝時鐘不可信或偽造,拒（stale-issue 對偶面）。
            blockers.push(B::IssuedInFuture);
        }
        if self.expires_at_ms <= self.issued_at_ms {
            blockers.push(B::InvalidActivationWindow);
        } else if self.expires_at_ms - self.issued_at_ms > IBKR_ACTIVATION_WINDOW_MAX_MS {
            blockers.push(B::ActivationWindowTooLong);
        }
        if now_ms >= self.expires_at_ms {
            blockers.push(B::EnvelopeExpired);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }
    }
}

/// envelope 校驗裁決（`accepted` 只代表 shape/綁定/時窗合格;活化裁決在 engine
/// 驗證器——nonce 消費 + epoch 比對 + build 綁定 + seal≠活化）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrActivationEnvelopeVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrActivationEnvelopeBlocker>,
}

impl IbkrActivationEnvelopeVerdict {
    pub fn new(blockers: Vec<IbkrActivationEnvelopeBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// envelope blocker（封閉枚舉;每一 §2 綁定欄各有專屬拒因,拒絕矩陣可逐欄斷言）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrActivationEnvelopeBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentNotReadonly,
    OperationScopeDenied,
    BuildGitShaInvalid,
    AccountFingerprintInvalid,
    SessionAttestationFingerprintInvalid,
    RiskConfigHashInvalid,
    OrderNotionalLimitNotZero,
    PositionNotionalLimitNotZero,
    OrdersPerDayLimitNotZero,
    // ---- W7-S4a paper-scope effect envelope 專屬拒因（additive;readonly 面不觸發）----
    /// paper-scope envelope 的 environment 非 `Paper`。
    PaperEnvironmentMismatch,
    /// paper-scope envelope 的單筆 order notional 上限非正定點字串（shape）。
    PaperOrderNotionalLimitInvalid,
    /// paper-scope envelope 的總 position notional 上限非正定點字串（shape）。
    PaperPositionNotionalLimitInvalid,
    /// paper-scope envelope 的每日 order 數上限為 0（effect 面須 ≥1）。
    PaperOrdersPerDayLimitInvalid,
    CostGateLineageInvalid,
    GuardianLineageInvalid,
    DecisionLeaseLineageInvalid,
    OperatorIdentityMissing,
    ActivationNonceInvalid,
    MissingIssuedAt,
    IssuedInFuture,
    InvalidActivationWindow,
    ActivationWindowTooLong,
    EnvelopeExpired,
    OrderRouted,
    SecretContentSerialized,
}

/// 40-hex git SHA 檢查（小寫 hex;`BUILD_GIT_SHA` 綁定欄的 shape 檢）。
fn is_git_sha40_hex(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 40
        && bytes
            .iter()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b))
}
