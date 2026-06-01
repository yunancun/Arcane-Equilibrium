//! 跨語言狀態機對等契約測試（Rust 側 harness）— 4a 治理里程碑。
//!
//! MODULE_NOTE
//! 模塊用途：讀單一權威 fixture (tests/fixtures/sm_contract_vectors.json)，對每條
//!   向量驅動「真實」的 Rust SM (auth / lease / risk_gov) transition()，把結果分類成
//!   {allowed / error_kind} 後與 fixture expect 比對。Python harness 讀同一 fixture 做
//!   同樣比對 → 兩側對等。
//! 主要函數：test_sm_contract_parity（單一整合 test，逐向量斷言並彙總失敗）。
//! 依賴：openclaw_core::sm::{auth, lease, risk_gov}、serde_json、CARGO_MANIFEST_DIR。
//! 硬邊界：
//!   - TEST-ONLY，0 行改動 sm/*.rs；只「觀察」遷移行為。
//!   - 不可繞過真實 transition()（不直接呼私有 lookup_rule）— 對等必須是「真實驗證路徑」對等。
//!   - SM-04 min_hold 設 0（fixture harness_contract），使 de-escalation allowed 只反映
//!     rule+initiator+approval；hold-time 不變量另由 sm/risk_gov.rs 內建 test 守。
//!
//! 為什麼設計成「驅動真實 transition 並分類錯誤」而非「直接比規則表」：
//!   Rust lookup_rule/is_forbidden 是 module-private，無 pub is_valid_transition；唯一公開
//!   驗證面是 transition()（含 5 guard + 終態 + hold-time）。比對「真實 transition 結果」才是
//!   對 Python `_validate_transition`（同 5 guard）的真對等，而非比對一份各自手抄的影子表。
//!
//! 為什麼預期首跑 RED：fixture 含 rust_only drift 向量（Reconciler initiator /
//!   NotificationFailsafeTimeout）— 這些在 Rust 端 allowed=true 會通過；真正的 RED 來自
//!   tagged-count guard：若未來新增「未登記的」分歧（untagged divergence），等值斷言 fail。
//!   本里程碑的主交付是「把 silent drift 轉成顯式列舉」，見 E1 report 的 DRIFT LIST。

use openclaw_core::sm::{auth, lease, risk_gov};
use serde_json::Value;
use std::path::PathBuf;

// ═══════════════════════════════════════════════════════════════════════════════
// Fixture 載入
// ═══════════════════════════════════════════════════════════════════════════════

fn fixture_path() -> PathBuf {
    // Rust 以 CARGO_MANIFEST_DIR 為錨（= rust/openclaw_core），Python 以 repo root parents[5]
    // 解析「同一個」絕對路徑 → 單一 source of truth。
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("sm_contract_vectors.json")
}

fn load_vectors() -> Vec<Value> {
    let path = fixture_path();
    let raw = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("讀 fixture 失敗 {}: {e}", path.display()));
    let doc: Value = serde_json::from_str(&raw).expect("fixture JSON parse 失敗");
    doc.get("vectors")
        .and_then(|v| v.as_array())
        .cloned()
        .expect("fixture 缺 vectors 陣列")
}

// ═══════════════════════════════════════════════════════════════════════════════
// 結果分類：把 Result<(), SmError> 映成 fixture 可比的 (allowed, error_kind)
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, PartialEq, Eq)]
struct Outcome {
    allowed: bool,
    error_kind: Option<&'static str>,
}

fn classify(res: Result<(), openclaw_core::sm::SmError>) -> Outcome {
    use openclaw_core::sm::SmError::*;
    match res {
        Ok(()) => Outcome { allowed: true, error_kind: None },
        Err(e) => {
            let kind = match e {
                NotFound(_) => "NotFound",
                TerminalState(_) => "TerminalState",
                Forbidden { .. } => "Forbidden",
                InvalidTransition { .. } => "InvalidTransition",
                InitiatorNotAllowed { .. } => "InitiatorNotAllowed",
                ApprovalRequired { .. } => "ApprovalRequired",
                HoldTimeNotMet { .. } => "HoldTimeNotMet",
            };
            Outcome { allowed: false, error_kind: Some(kind) }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SM-01 auth：enum 解析 + 預定位 + 驅動
// ═══════════════════════════════════════════════════════════════════════════════

fn auth_state(s: &str) -> auth::AuthState {
    use auth::AuthState::*;
    match s {
        "DRAFT" => Draft,
        "PENDING_APPROVAL" => PendingApproval,
        "ACTIVE" => Active,
        "RESTRICTED" => Restricted,
        "FROZEN" => Frozen,
        "REVOKED" => Revoked,
        "EXPIRED" => Expired,
        "REJECTED" => Rejected,
        other => panic!("未知 AuthState: {other}"),
    }
}

fn auth_initiator(s: &str) -> auth::AuthInitiator {
    use auth::AuthInitiator::*;
    match s {
        "AuthorizationGovernance" => Governance,
        "Operator" => Operator,
        "IncidentPolicy" => IncidentPolicy,
        "RecoveryApprovalFlow" => RecoveryFlow,
        "ExpiryGuardian" => ExpiryGuardian,
        other => panic!("未知 AuthInitiator: {other}"),
    }
}

/// 用「特權路徑」把 auth 物件驅動到 from_state，回 (sm, idx)。
/// 為什麼用特權 initiator/approval 預定位：fixture 測的是「最後一跳」的對等；預定位本身
/// 走真實 transition() 但用必然合法的 initiator + approved_by，避免污染最後一跳的判定。
fn auth_position(from: auth::AuthState) -> (auth::AuthorizationSm, usize) {
    use auth::AuthState::*;
    let mut sm = auth::AuthorizationSm::new();
    let idx = sm.create_draft("contract", serde_json::json!({}), "operator", Some(u64::MAX));
    // create 後在 Draft。預定位走真實 convenience 方法（各自帶正確 initiator/approval）。
    match from {
        Draft => {}
        PendingApproval => {
            sm.submit_for_approval(idx).unwrap();
        }
        Active => {
            sm.submit_for_approval(idx).unwrap();
            sm.approve(idx, "op", "pos").unwrap();
        }
        Restricted => {
            sm.submit_for_approval(idx).unwrap();
            sm.approve(idx, "op", "pos").unwrap();
            sm.restrict(idx, "pos").unwrap();
        }
        Frozen => {
            sm.submit_for_approval(idx).unwrap();
            sm.approve(idx, "op", "pos").unwrap();
            sm.freeze(idx, "pos").unwrap();
        }
        Revoked => {
            sm.submit_for_approval(idx).unwrap();
            sm.approve(idx, "op", "pos").unwrap();
            sm.revoke(idx, "op", "pos").unwrap();
        }
        Expired => {
            sm.submit_for_approval(idx).unwrap();
            sm.approve(idx, "op", "pos").unwrap();
            // Active→Expired 必用 ExpiryGuardian（allow-list = {ExpiryGuardian, Governance}，
            // 不含 Operator）；用 convenience expire() 走 ExpiryGuardian。
            sm.expire(idx).unwrap();
        }
        Rejected => {
            sm.reject(idx).unwrap(); // Draft→Rejected
        }
    }
    (sm, idx)
}

fn run_auth(v: &Value) -> Outcome {
    let from = auth_state(v["from_state"].as_str().unwrap());
    let to = auth_state(v["to_state"].as_str().unwrap());
    let init = auth_initiator(v["initiator"].as_str().unwrap());
    let approved_by = v["approved_by"].as_str();
    let (mut sm, idx) = auth_position(from);
    let res = sm.transition(
        idx, to, auth::AuthEvent::Approved, init,
        vec!["contract".into()], approved_by, "contract",
    );
    classify(res)
}

// ═══════════════════════════════════════════════════════════════════════════════
// SM-02 lease
// ═══════════════════════════════════════════════════════════════════════════════

fn lease_state(s: &str) -> lease::LeaseState {
    use lease::LeaseState::*;
    match s {
        "DRAFT" => Draft,
        "REGISTERED" => Registered,
        "ACTIVE" => Active,
        "BRIDGED" => Bridged,
        "FROZEN" => Frozen,
        "REVOKED" => Revoked,
        "EXPIRED" => Expired,
        "REJECTED" => Rejected,
        "CONSUMED" => Consumed,
        other => panic!("未知 LeaseState: {other}"),
    }
}

fn lease_initiator(s: &str) -> lease::LeaseInitiator {
    use lease::LeaseInitiator::*;
    match s {
        "I" => ControlPlane,
        "Operator" => Operator,
        "AuthorizationGovernance" => Governance,
        "IncidentPolicy" => IncidentPolicy,
        "ExecutionClosureFlow" => ExecutionClosure,
        "ExpiryGuardian" => ExpiryGuardian,
        "RiskGovernor" => RiskGovernor,
        other => panic!("未知 LeaseInitiator: {other}"),
    }
}

fn lease_position(from: lease::LeaseState) -> (lease::DecisionLeaseSm, usize) {
    use lease::LeaseState::*;
    let mut sm = lease::DecisionLeaseSm::new();
    let idx = sm.create_draft(serde_json::json!({}), "strategist", Some(u64::MAX));
    let drive = |sm: &mut lease::DecisionLeaseSm, to: lease::LeaseState, appr: Option<&str>| {
        sm.transition(
            idx, to, lease::LeaseEvent::RecoveryApproved,
            lease::LeaseInitiator::ControlPlane,
            vec!["position".into()], appr, "position",
        )
    };
    match from {
        Draft => {}
        Registered => {
            sm.register(idx).unwrap();
        }
        Active => {
            sm.register(idx).unwrap();
            sm.activate(idx).unwrap();
        }
        Bridged => {
            sm.register(idx).unwrap();
            sm.activate(idx).unwrap();
            sm.bridge(idx).unwrap();
        }
        Frozen => {
            sm.register(idx).unwrap();
            sm.activate(idx).unwrap();
            sm.freeze(idx, "pos").unwrap();
        }
        Revoked => {
            sm.register(idx).unwrap();
            sm.revoke(idx, "op", "pos").unwrap();
        }
        Expired => {
            sm.register(idx).unwrap();
            drive(&mut sm, Expired, None).unwrap(); // Registered→Expired (ExpiryGuardian/ControlPlane)
        }
        Rejected => {
            sm.reject(idx, "pos").unwrap(); // Draft→Rejected
        }
        Consumed => {
            sm.register(idx).unwrap();
            sm.activate(idx).unwrap();
            sm.bridge(idx).unwrap();
            sm.consume(idx).unwrap();
        }
    }
    (sm, idx)
}

fn run_lease(v: &Value) -> Outcome {
    let from = lease_state(v["from_state"].as_str().unwrap());
    let to = lease_state(v["to_state"].as_str().unwrap());
    let init = lease_initiator(v["initiator"].as_str().unwrap());
    let approved_by = v["approved_by"].as_str();
    let (mut sm, idx) = lease_position(from);
    let res = sm.transition(
        idx, to, lease::LeaseEvent::RecoveryApproved, init,
        vec!["contract".into()], approved_by, "contract",
    );
    classify(res)
}

// ═══════════════════════════════════════════════════════════════════════════════
// SM-04 risk_gov
// ═══════════════════════════════════════════════════════════════════════════════

fn risk_level(s: &str) -> risk_gov::RiskLevel {
    use risk_gov::RiskLevel::*;
    match s {
        "NORMAL" => Normal,
        "CAUTIOUS" => Cautious,
        "REDUCED" => Reduced,
        "DEFENSIVE" => Defensive,
        "CIRCUIT_BREAKER" => CircuitBreaker,
        "MANUAL_REVIEW" => ManualReview,
        other => panic!("未知 RiskLevel: {other}"),
    }
}

fn risk_initiator(s: &str) -> risk_gov::RiskInitiator {
    use risk_gov::RiskInitiator::*;
    match s {
        "RiskGovernor" => RiskGovernor,
        "Operator" => Operator,
        "IncidentPolicy" => IncidentPolicy,
        "HealthMonitor" => HealthMonitor,
        "ExpiryGuardian" => ExpiryGuardian,
        "Reconciler" => Reconciler,
        other => panic!("未知 RiskInitiator: {other}"),
    }
}

/// risk_gov 預定位：min_hold=0，從 Normal 單跳 escalate 到 from_level（所有 level 皆 1-hop 可達）。
fn risk_position(from: risk_gov::RiskLevel) -> risk_gov::RiskGovernorSm {
    use risk_gov::RiskLevel::*;
    let mut t = risk_gov::EscalationThresholds::default();
    t.min_hold_time_ms = 0; // 關閉 hold-time（fixture harness_contract）
    let mut sm = risk_gov::RiskGovernorSm::with_thresholds(t);
    if from != Normal {
        // 用 Operator escalate（Operator ∈ AUTO 與 OP_GOV，對 Normal→任何 escalation 皆合法）
        sm.transition(
            from, risk_gov::RiskEvent::OperatorEscalation,
            risk_gov::RiskInitiator::Operator,
            vec!["position".into()], None, "position",
        )
        .unwrap_or_else(|e| panic!("risk 預定位到 {from:?} 失敗: {e:?}"));
    }
    sm
}

fn run_risk(v: &Value) -> Outcome {
    let from = risk_level(v["from_state"].as_str().unwrap());
    let to = risk_level(v["to_state"].as_str().unwrap());
    let init = risk_initiator(v["initiator"].as_str().unwrap());
    let approved_by = v["approved_by"].as_str();
    let mut sm = risk_position(from);
    let res = sm.transition(
        to, risk_gov::RiskEvent::RecoveryApproved, init,
        vec!["contract".into()], approved_by, "contract",
    );
    classify(res)
}

// ═══════════════════════════════════════════════════════════════════════════════
// 主 test
// ═══════════════════════════════════════════════════════════════════════════════

fn expected_outcome(v: &Value) -> Outcome {
    let e = &v["expect"];
    Outcome {
        allowed: e["allowed"].as_bool().unwrap(),
        error_kind: e.get("error_kind").and_then(|k| k.as_str()).map(|s| match s {
            "NotFound" => "NotFound",
            "TerminalState" => "TerminalState",
            "Forbidden" => "Forbidden",
            "InvalidTransition" => "InvalidTransition",
            "InitiatorNotAllowed" => "InitiatorNotAllowed",
            "ApprovalRequired" => "ApprovalRequired",
            "HoldTimeNotMet" => "HoldTimeNotMet",
            other => panic!("fixture 未知 error_kind: {other}"),
        }),
    }
}

#[test]
fn test_sm_contract_parity() {
    let vectors = load_vectors();
    assert!(!vectors.is_empty(), "fixture 無向量");

    let mut failures: Vec<String> = Vec::new();
    let mut equality_checked = 0usize;
    let mut rust_only = 0usize;
    let mut py_only = 0usize;

    for v in &vectors {
        let sm = v["sm"].as_str().unwrap();
        let tag = v.get("tag").and_then(|t| t.as_str());

        let actual = match sm {
            "auth" => run_auth(v),
            "lease" => run_lease(v),
            "risk_gov" => run_risk(v),
            other => panic!("fixture 未知 sm: {other}"),
        };

        // py_only 向量：Rust 端無此 element（state/initiator/event），不在 Rust 跑等值，只計數。
        // （本 fixture 目前無 py_only 規則層向量；保留分支防未來新增。）
        if tag == Some("py_only") {
            py_only += 1;
            continue;
        }

        let expected = expected_outcome(v);

        if tag == Some("rust_only") {
            // rust_only：Rust 端「應」能跑出 fixture expect（多為 allowed=true）。
            // 仍做 Rust 自身斷言（保證 Rust 行為符合 drift 描述），但不計入跨語言等值。
            rust_only += 1;
            if actual.allowed != expected.allowed {
                failures.push(format!(
                    "[rust_only] {} {}->{} init={} : Rust allowed={} 但 fixture expect.allowed={} (note={})",
                    sm, v["from_state"], v["to_state"], v["initiator"],
                    actual.allowed, expected.allowed,
                    v.get("note").and_then(|n| n.as_str()).unwrap_or("")
                ));
            }
            continue;
        }

        // 等值向量：allowed 必相符；當 !allowed 時 error_kind 亦必相符。
        equality_checked += 1;
        let mut mismatch = actual.allowed != expected.allowed;
        if !expected.allowed && !mismatch {
            // 只在「兩側都判 deny」時比 error_kind（Python 弱分類也會比對）。
            if actual.error_kind != expected.error_kind {
                mismatch = true;
            }
        }
        if mismatch {
            failures.push(format!(
                "{} {}->{} init={} appr={:?} note={}: actual={:?} expected={:?}",
                sm, v["from_state"], v["to_state"], v["initiator"], v["approved_by"],
                v.get("note").and_then(|n| n.as_str()).unwrap_or(""),
                actual, expected
            ));
        }
    }

    // ── tagged-count drift guard：把「已登記 drift」鎖死。新增未登記分歧 → 此處或等值斷言 fail。
    // 目前 fixture 已登記：rust_only=4（Reconciler×3 + NotificationFailsafe×1）、py_only=0。
    const EXPECTED_RUST_ONLY: usize = 4;
    const EXPECTED_PY_ONLY: usize = 0;
    assert_eq!(
        rust_only, EXPECTED_RUST_ONLY,
        "rust_only drift 計數變動：實際 {rust_only} != 預期 {EXPECTED_RUST_ONLY}。\
         若有意新增/移除 drift，請同步本常數 + E1 report DRIFT LIST。"
    );
    assert_eq!(
        py_only, EXPECTED_PY_ONLY,
        "py_only drift 計數變動：實際 {py_only} != 預期 {EXPECTED_PY_ONLY}。"
    );

    eprintln!(
        "[sm_contract] 向量={} 等值核對={} rust_only={} py_only={} 失敗={}",
        vectors.len(), equality_checked, rust_only, py_only, failures.len()
    );

    if !failures.is_empty() {
        let body = failures.join("\n  ");
        panic!(
            "SM 契約對等失敗 {} 條（Rust 側真實 transition 與 fixture expect 不符）:\n  {}",
            failures.len(), body
        );
    }
}
