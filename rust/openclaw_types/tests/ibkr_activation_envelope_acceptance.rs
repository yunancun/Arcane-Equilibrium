//! W8a `ibkr_activation_envelope_v1` 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、無牆鐘
//! 依賴（`validate(now_ms)` 全部注入固定時刻——fixture 時刻為 epoch ms 常量,非 time-bomb）。
//! 拒絕矩陣紀律:§2 活化鐵律**每一綁定欄**至少「缺」「壞」各一負測試,時窗面含
//! 過期/倒置/超長/未來簽發;epoch「落後於當前」比對歸 engine 驗證器測試面。

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, IbkrActivationEnvelopeBlocker, IbkrActivationEnvelopeV1,
    IbkrActivationOperationScopeV1, IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID,
    IBKR_ACTIVATION_WINDOW_MAX_MS,
};

use IbkrActivationEnvelopeBlocker as B;

/// fixture 有效窗內的注入時刻（issued + 10min）。
const NOW_IN_WINDOW_MS: u64 = 1_772_232_600_000;

fn fixture() -> IbkrActivationEnvelopeV1 {
    IbkrActivationEnvelopeV1::readonly_fixture()
}

/// 單欄變異 → 斷言指定 blocker 出現（拒絕矩陣的最小單元）。
fn assert_rejects(mutated: IbkrActivationEnvelopeV1, expected: B) {
    let verdict = mutated.validate(NOW_IN_WINDOW_MS);
    assert!(!verdict.accepted, "expected rejection for {expected:?}");
    assert!(
        verdict.blockers.contains(&expected),
        "expected blocker {expected:?}, got {:?}",
        verdict.blockers
    );
}

#[test]
fn default_envelope_is_fail_closed_on_every_binding() {
    let verdict = IbkrActivationEnvelopeV1::default().validate(NOW_IN_WINDOW_MS);
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::EnvironmentNotReadonly,
        B::OperationScopeDenied,
        B::BuildGitShaInvalid,
        B::AccountFingerprintInvalid,
        B::SessionAttestationFingerprintInvalid,
        B::RiskConfigHashInvalid,
        B::OrderNotionalLimitNotZero,
        B::PositionNotionalLimitNotZero,
        B::CostGateLineageInvalid,
        B::GuardianLineageInvalid,
        B::DecisionLeaseLineageInvalid,
        B::OperatorIdentityMissing,
        B::ActivationNonceInvalid,
        B::MissingIssuedAt,
        B::InvalidActivationWindow,
        B::EnvelopeExpired,
    ] {
        assert!(
            verdict.blockers.contains(&expected),
            "default 缺 blocker {expected:?}"
        );
    }
}

#[test]
fn readonly_fixture_validates_in_window() {
    let envelope = fixture();
    let verdict = envelope.validate(NOW_IN_WINDOW_MS);
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(envelope.contract_id, IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID);
    assert_eq!(envelope.source_version, 1);
    assert_eq!(envelope.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(envelope.broker, Broker::Ibkr);
    assert_eq!(envelope.environment, BrokerEnvironment::ReadOnly);
    assert_eq!(
        envelope.operation_scope,
        IbkrActivationOperationScopeV1::Readonly
    );
    // 負空間束:恆 false。
    assert!(!envelope.order_routed);
    assert!(!envelope.secret_content_serialized);
}

// ---------------------------------------------------------------------------
// 拒絕矩陣:§2 綁定逐欄(缺/壞各一)
// ---------------------------------------------------------------------------

#[test]
fn rejects_contract_id_missing_and_wrong() {
    let mut e = fixture();
    e.contract_id = String::new();
    assert_rejects(e, B::ContractIdMismatch);

    let mut e = fixture();
    e.contract_id = "ibkr_activation_envelope_v0".to_string();
    assert_rejects(e, B::ContractIdMismatch);
}

#[test]
fn rejects_source_version_missing_and_wrong() {
    let mut e = fixture();
    e.source_version = 0;
    assert_rejects(e, B::SourceVersionMismatch);

    let mut e = fixture();
    e.source_version = 2;
    assert_rejects(e, B::SourceVersionMismatch);
}

#[test]
fn rejects_wrong_lane_and_wrong_broker() {
    let mut e = fixture();
    e.asset_lane = AssetLane::CryptoPerp;
    assert_rejects(e, B::WrongAssetLane);

    let mut e = fixture();
    e.asset_lane = AssetLane::CfdMarginReserved;
    assert_rejects(e, B::WrongAssetLane);

    let mut e = fixture();
    e.broker = Broker::Bybit;
    assert_rejects(e, B::WrongBroker);
}

#[test]
fn rejects_every_non_readonly_environment() {
    // 本切片 environment 白名單 = ReadOnly 單值:paper/shadow/live 全拒(paper 歸 W8)。
    for env in [
        BrokerEnvironment::Paper,
        BrokerEnvironment::Shadow,
        BrokerEnvironment::LiveReservedDenied,
    ] {
        let mut e = fixture();
        e.environment = env;
        assert_rejects(e, B::EnvironmentNotReadonly);
    }
}

#[test]
fn rejects_unknown_denied_operation_scope() {
    let mut e = fixture();
    e.operation_scope = IbkrActivationOperationScopeV1::UnknownDenied;
    assert_rejects(e, B::OperationScopeDenied);
}

#[test]
fn scope_whitelist_is_readonly_single_value_and_fail_closed() {
    use IbkrActivationOperationScopeV1 as Scope;

    assert_eq!(Scope::classify_scope("readonly"), Scope::Readonly);
    // 表外值(含 W8 才承認的 paper/tiny_live/live)一律 UnknownDenied。
    for raw in [
        "paper",
        "tiny_live",
        "live",
        "shadow",
        "READONLY",
        "read_only",
        "readonly ",
        "",
    ] {
        assert_eq!(
            Scope::classify_scope(raw),
            Scope::UnknownDenied,
            "scope {raw:?} 必須 fail-closed 拒"
        );
    }
    assert_eq!(Scope::default(), Scope::UnknownDenied);
    assert_eq!(Scope::Readonly.as_str(), "readonly");
    assert_eq!(Scope::UnknownDenied.as_str(), "unknown_denied");
}

#[test]
fn rejects_build_git_sha_missing_and_malformed() {
    let mut e = fixture();
    e.build_git_sha = String::new();
    assert_rejects(e, B::BuildGitShaInvalid);

    let mut e = fixture();
    e.build_git_sha = "F".repeat(40); // 大寫非規範 hex
    assert_rejects(e, B::BuildGitShaInvalid);

    let mut e = fixture();
    e.build_git_sha = "f".repeat(39); // 長度不足
    assert_rejects(e, B::BuildGitShaInvalid);
}

#[test]
fn rejects_fingerprints_and_hashes_missing_and_malformed() {
    // (欄位變異器, 專屬 blocker):sha256-hex 家族逐欄。
    let cases: [(fn(&mut IbkrActivationEnvelopeV1, String), B); 6] = [
        (
            |e, v| e.account_fingerprint = v,
            B::AccountFingerprintInvalid,
        ),
        (
            |e, v| e.session_attestation_fingerprint = v,
            B::SessionAttestationFingerprintInvalid,
        ),
        (|e, v| e.risk_config_hash = v, B::RiskConfigHashInvalid),
        (|e, v| e.cost_gate_lineage = v, B::CostGateLineageInvalid),
        (|e, v| e.guardian_lineage = v, B::GuardianLineageInvalid),
        (
            |e, v| e.decision_lease_lineage = v,
            B::DecisionLeaseLineageInvalid,
        ),
    ];
    for (mutate, blocker) in cases {
        // 缺。
        let mut e = fixture();
        mutate(&mut e, String::new());
        assert_rejects(e, blocker);
        // 壞(非 hex 字元)。
        let mut e = fixture();
        mutate(&mut e, "z".repeat(64));
        assert_rejects(e, blocker);
        // 壞(長度不足)。
        let mut e = fixture();
        mutate(&mut e, "a".repeat(63));
        assert_rejects(e, blocker);
    }
}

#[test]
fn rejects_nonzero_limits_for_readonly_scope() {
    // readonly envelope 的 order 面額度恆零——非零即拒(order verb 結構性拒的額度層投影)。
    let mut e = fixture();
    e.max_order_notional_usd_decimal = "1".to_string();
    assert_rejects(e, B::OrderNotionalLimitNotZero);

    let mut e = fixture();
    e.max_order_notional_usd_decimal = String::new();
    assert_rejects(e, B::OrderNotionalLimitNotZero);

    let mut e = fixture();
    e.max_position_notional_usd_decimal = "0.01".to_string();
    assert_rejects(e, B::PositionNotionalLimitNotZero);

    let mut e = fixture();
    e.max_position_notional_usd_decimal = String::new();
    assert_rejects(e, B::PositionNotionalLimitNotZero);

    let mut e = fixture();
    e.max_orders_per_day = 1;
    assert_rejects(e, B::OrdersPerDayLimitNotZero);
}

#[test]
fn rejects_operator_identity_missing_and_whitespace() {
    let mut e = fixture();
    e.operator_identity = String::new();
    assert_rejects(e, B::OperatorIdentityMissing);

    let mut e = fixture();
    e.operator_identity = "   ".to_string();
    assert_rejects(e, B::OperatorIdentityMissing);
}

#[test]
fn rejects_nonce_missing_and_malformed() {
    let mut e = fixture();
    e.activation_nonce = String::new();
    assert_rejects(e, B::ActivationNonceInvalid);

    let mut e = fixture();
    e.activation_nonce = "not-a-nonce".to_string();
    assert_rejects(e, B::ActivationNonceInvalid);
}

// ---------------------------------------------------------------------------
// 時窗面:缺/未來簽發/倒置/超長/過期
// ---------------------------------------------------------------------------

#[test]
fn rejects_missing_issued_at() {
    let mut e = fixture();
    e.issued_at_ms = 0;
    assert_rejects(e, B::MissingIssuedAt);
}

#[test]
fn rejects_issued_in_future() {
    let e = fixture();
    // 注入時刻早於簽發時刻 → 未來簽發拒。
    let verdict = e.validate(e.issued_at_ms - 1);
    assert!(verdict.blockers.contains(&B::IssuedInFuture));
}

#[test]
fn rejects_inverted_activation_window() {
    let mut e = fixture();
    e.expires_at_ms = e.issued_at_ms; // 窗長 0 = 倒置
    assert_rejects(e, B::InvalidActivationWindow);
}

#[test]
fn rejects_activation_window_longer_than_24h() {
    let mut e = fixture();
    e.expires_at_ms = e.issued_at_ms + IBKR_ACTIVATION_WINDOW_MAX_MS + 1;
    assert_rejects(e, B::ActivationWindowTooLong);

    // 邊界:恰 24h 允許(time-bounded 上限含界)。
    let mut e = fixture();
    e.expires_at_ms = e.issued_at_ms + IBKR_ACTIVATION_WINDOW_MAX_MS;
    assert!(e.validate(NOW_IN_WINDOW_MS).accepted);
}

#[test]
fn rejects_expired_envelope() {
    let e = fixture();
    let at_expiry = e.expires_at_ms;
    let verdict = e.validate(at_expiry); // now == expires 即過期(含界拒)
    assert!(verdict.blockers.contains(&B::EnvelopeExpired));
}

// ---------------------------------------------------------------------------
// 負空間束 + serde 形態
// ---------------------------------------------------------------------------

#[test]
fn rejects_order_routed_and_secret_content() {
    let mut e = fixture();
    e.order_routed = true;
    assert_rejects(e, B::OrderRouted);

    let mut e = fixture();
    e.secret_content_serialized = true;
    assert_rejects(e, B::SecretContentSerialized);
}

#[test]
fn serde_is_snake_case_and_round_trips() {
    let envelope = fixture();
    let json = serde_json::to_string(&envelope).expect("serialize");
    // snake_case 欄位名 + scope 白名單值。
    assert!(json.contains("\"operation_scope\":\"readonly\""));
    assert!(json.contains("\"asset_lane\":\"stock_etf_cash\""));
    assert!(json.contains("\"environment\":\"read_only\""));
    assert!(json.contains("\"activation_nonce\""));
    assert!(json.contains("\"kill_switch_epoch\""));
    let back: IbkrActivationEnvelopeV1 = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(back, envelope);
}

#[test]
fn epoch_bindings_are_carried_verbatim_for_engine_comparison() {
    // types 層只承載 epoch 綁定值;「與當前 epoch 相等」的比對與拒絕在 engine 驗證器
    // (ibkr_activation_envelope_check)——此測試釘住承載不被 validate 靜默改寫。
    let e = fixture();
    assert_eq!(e.revocation_epoch, 1);
    assert_eq!(e.kill_switch_epoch, 1);
    let _ = e.validate(NOW_IN_WINDOW_MS);
    assert_eq!(e.revocation_epoch, 1);
    assert_eq!(e.kill_switch_epoch, 1);
}
