//! P1-8 跨語言 golden-vector 契約整合測試（Rust 側）——demo learning lane。
//!
//! MODULE_NOTE (中):
//!   本整合測試消費 tests/fixtures/demo_lane_contract/ 下的共用 golden fixture
//!   （與 Python sibling test
//!   helper_scripts/research/tests/test_demo_lane_contract_xlang_golden.py 同源），
//!   從 Rust 側對同一 fixture 跑真實現、對同一 expected 斷言，實現 06-30 connector
//!   cutover 後 Rust↔Python 內側契約 parity（BB P1-8 §2.1）。任一側漂移即紅。
//!
//!   覆蓋契約面：
//!     C1 envelope 13-check 矩陣（validate_operator_authorization_envelope）
//!     C2 ledger 行互讀 + 毒行三態（LedgerRecord::from_jsonl_str）
//!     C3 order_link_id 5 段 + FNV-1a lineage hash
//!        （bounded_probe_order_link_id_for_candidate /
//!         is_candidate_bound_bounded_probe_order_link_id）
//!     C4 契約常量逐值
//!     C5 AdmissionConfig defaults + 範圍（AdmissionConfig::validate）
//!     C6 plan 檔路徑契約（shared 默認子路徑；override 優先由 writer 單元測試+
//!        Python 測試覆蓋，見 c6 測試註）
//!
//! MODULE_NOTE (EN):
//!   Cross-language golden-vector contract integration test (Rust side) for the
//!   demo learning lane. Consumes the shared fixtures under
//!   tests/fixtures/demo_lane_contract/ (same source as the Python sibling), runs
//!   the real Rust implementations, and asserts the same expected values, so any
//!   drift on either side turns red.
//!
//! 執行 / Run:
//!   cargo test -p openclaw_engine --test demo_lane_contract_xlang_consistency

use openclaw_engine::bounded_probe_active_order::{
    bounded_probe_order_link_id_for_candidate, is_candidate_bound_bounded_probe_order_link_id,
    ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ, BYBIT_ORDER_LINK_ID_MAX_LEN,
    BYBIT_ORDER_LINK_ID_PREFIX,
};
use openclaw_engine::demo_learning_lane::{
    validate_operator_authorization_envelope, AdmissionConfig, BoundedProbeOperatorAuthorization,
    LedgerRecord, ADAPTER_SCHEMA_VERSION, ADMIT_DECISION, AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS, BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ELIGIBLE_REJECT_REASON_CODE, OPERATOR_AUTHORIZATION_EXPIRED_REASON, ORDER_AUTHORITY_GRANTED,
    PLAN_SCHEMA_VERSION,
};
use serde_json::Value;

// ---- fixture 載入（include_str! in-tree，與 Python 同檔）----

const CONSTANTS_JSON: &str =
    include_str!("fixtures/demo_lane_contract/constants.json");
const ENVELOPE_MATRIX_JSON: &str =
    include_str!("fixtures/demo_lane_contract/envelope_matrix.json");
const ORDER_LINK_ID_JSON: &str =
    include_str!("fixtures/demo_lane_contract/order_link_id_vectors.json");
const LEDGER_CONTRACT_JSON: &str =
    include_str!("fixtures/demo_lane_contract/ledger_contract.json");
const LEDGER_ROWS_JSONL: &str =
    include_str!("fixtures/demo_lane_contract/ledger_rows.jsonl");
const ADMISSION_CONFIG_JSON: &str =
    include_str!("fixtures/demo_lane_contract/admission_config.json");
const PATH_CONTRACT_JSON: &str =
    include_str!("fixtures/demo_lane_contract/path_contract.json");

fn parse(json: &str) -> Value {
    serde_json::from_str(json).expect("fixture JSON must parse")
}

// ---------------------------------------------------------------------------
// C4 — 契約常量逐值
// ---------------------------------------------------------------------------

#[test]
fn c4_shared_constants_match_manifest() {
    let m = parse(CONSTANTS_JSON);
    let shared = m["shared"].as_object().expect("shared object");

    let str_consts: &[(&str, &str)] = &[
        ("PLAN_SCHEMA_VERSION", PLAN_SCHEMA_VERSION),
        ("ADAPTER_SCHEMA_VERSION", ADAPTER_SCHEMA_VERSION),
        ("ORDER_AUTHORITY_GRANTED", ORDER_AUTHORITY_GRANTED),
        ("ELIGIBLE_REJECT_REASON_CODE", ELIGIBLE_REJECT_REASON_CODE),
        ("ADMIT_DECISION", ADMIT_DECISION),
        (
            "BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION",
            BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
        ),
        ("BOUNDED_PROBE_AUTHORIZED_STATUS", BOUNDED_PROBE_AUTHORIZED_STATUS),
        (
            "AUTHORITY_PATH_PATCH_READY_STATUS",
            AUTHORITY_PATH_PATCH_READY_STATUS,
        ),
        (
            "OPERATOR_AUTHORIZATION_EXPIRED_REASON",
            OPERATOR_AUTHORIZATION_EXPIRED_REASON,
        ),
        ("BYBIT_ORDER_LINK_ID_PREFIX", BYBIT_ORDER_LINK_ID_PREFIX),
        (
            "ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE",
            openclaw_engine::bounded_probe_active_order::ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE,
        ),
    ];
    for (key, val) in str_consts {
        assert_eq!(
            shared[*key].as_str().unwrap(),
            *val,
            "C4 shared const drift: {key}"
        );
    }

    // 數值常量
    assert_eq!(
        shared["BYBIT_ORDER_LINK_ID_MAX_LEN"].as_u64().unwrap(),
        BYBIT_ORDER_LINK_ID_MAX_LEN as u64
    );
    assert_eq!(
        shared["ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ"]
            .as_u64()
            .unwrap(),
        ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ
    );
    assert_eq!(
        shared["ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD"].as_u64().unwrap(),
        101_559_956_668_416u64
    );
    assert_eq!(
        shared["ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN"].as_u64().unwrap(),
        9u64
    );

    // record_type 契約字串（Rust ledger 常量）
    assert_eq!(
        shared["ADMISSION_LEDGER_RECORD_TYPE"].as_str().unwrap(),
        openclaw_engine::demo_learning_lane_ledger::ADMISSION_LEDGER_RECORD_TYPE
    );
}

// ---------------------------------------------------------------------------
// C1 — envelope 13-check 矩陣
// ---------------------------------------------------------------------------

/// 從 fixture envelope JSON 反序列化成 Rust struct（serde 對 max_authorized_probe_orders
/// 為字串時會 Err，正是 B3 契約——由 c1_boundary_string_budget 專測；此 helper 對
/// 可反序列化的 envelope 使用）。
fn deserialize_envelope(v: &Value) -> Result<BoundedProbeOperatorAuthorization, serde_json::Error> {
    serde_json::from_value(v.clone())
}

#[test]
fn c1_envelope_single_defect_matrix() {
    let m = parse(ENVELOPE_MATRIX_JSON);
    let now_ms = m["now_ms"].as_u64().unwrap();
    for vec in m["single_defect_matrix"].as_array().unwrap() {
        let name = vec["name"].as_str().unwrap();
        let env_json = &vec["envelope"];
        let expected = vec["rust_expected_reason"].as_str();

        // "missing" 缺陷 = 空 envelope 物件（無授權欄）。以 None 餵 validator。
        let auth = if env_json.as_object().map(|o| o.is_empty()).unwrap_or(true) {
            None
        } else {
            Some(deserialize_envelope(env_json).unwrap_or_else(|e| {
                panic!("C1 {name}: envelope deserialize failed: {e}")
            }))
        };
        let result = validate_operator_authorization_envelope(auth.as_ref(), now_ms);
        let err = result.expect_err(&format!("C1 {name}: expected reject"));
        assert_eq!(
            Some(err),
            expected,
            "C1 {name}: rust reason drift got={err} expected={expected:?}"
        );
    }
}

#[test]
fn c1_envelope_all_green_accept() {
    let m = parse(ENVELOPE_MATRIX_JSON);
    let now_ms = m["now_ms"].as_u64().unwrap();
    let vec = &m["accept_vector"];
    let auth = deserialize_envelope(&vec["envelope"]).unwrap();
    let result = validate_operator_authorization_envelope(Some(&auth), now_ms);
    assert!(result.is_ok(), "C1 all-green: expected accept, got {result:?}");
}

#[test]
fn c1_envelope_boundary_vectors() {
    let m = parse(ENVELOPE_MATRIX_JSON);
    let now_ms = m["now_ms"].as_u64().unwrap();
    for vec in m["boundary_vectors"].as_array().unwrap() {
        let name = vec["name"].as_str().unwrap();
        let expect_accept = vec["expected_accept"].as_bool().unwrap();
        let env_json = &vec["envelope"];

        // budget 為字串的邊界（budget_string_5）：serde 反序列化 Option<u64> 對字串 Err
        // = Rust 拒（B3）。deserialize 失敗即等同 envelope 無效 -> reject。
        let auth = match deserialize_envelope(env_json) {
            Ok(a) => a,
            Err(_) => {
                assert!(
                    !expect_accept,
                    "C1 boundary {name}: serde rejected but fixture expects accept"
                );
                continue;
            }
        };
        let result = validate_operator_authorization_envelope(Some(&auth), now_ms);
        assert_eq!(
            result.is_ok(),
            expect_accept,
            "C1 boundary {name}: accept got={} expected={} ({result:?})",
            result.is_ok(),
            expect_accept
        );
        if let Some(expected_reason) = vec["rust_expected_reason"].as_str() {
            if let Err(err) = result {
                assert_eq!(err, expected_reason, "C1 boundary {name}: reason drift");
            }
        }
    }
}

#[test]
fn c1_gate_not_overzealous_valid_offsets_admit() {
    // Gate 雙向：Z / +00:00 / +08:00(等價 1200Z) 三種合法 offset 形式必 accept，
    // 證統一 RFC3339 嚴格側未誤殺合法輸入（不該擋的正常路徑仍過）。
    let m = parse(ENVELOPE_MATRIX_JSON);
    let now_ms = m["now_ms"].as_u64().unwrap();
    let accept_names = ["expiry_Z_suffix_accept", "expiry_plus0000_accept",
        "expiry_plus0800_equiv_1200Z_accept"];
    for vec in m["boundary_vectors"].as_array().unwrap() {
        let name = vec["name"].as_str().unwrap();
        if !accept_names.contains(&name) {
            continue;
        }
        let auth = deserialize_envelope(&vec["envelope"]).unwrap();
        assert!(
            validate_operator_authorization_envelope(Some(&auth), now_ms).is_ok(),
            "C1 gate over-zealous: {name} should admit"
        );
    }
}

#[test]
fn c1_boundary_string_budget_serde_rejects() {
    // B3 直證：max_authorized_probe_orders="5"（字串）-> serde Option<u64> Err。
    let m = parse(ENVELOPE_MATRIX_JSON);
    let vec = m["boundary_vectors"]
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["name"] == "budget_string_5_reject")
        .expect("budget_string_5_reject vector present");
    let result = deserialize_envelope(&vec["envelope"]);
    assert!(
        result.is_err(),
        "B3: string budget must fail serde deserialize (Rust reject)"
    );
}

// ---------------------------------------------------------------------------
// C2 — ledger 行互讀 + 毒行三態
// ---------------------------------------------------------------------------

#[test]
fn c2_rust_reads_good_rows_file() {
    // Rust from_jsonl_str 讀兩條 good 行（第1行=Python writer sort_keys、第2行=Rust-shape）。
    let rows = LedgerRecord::from_jsonl_str(LEDGER_ROWS_JSONL)
        .expect("good rows must parse");
    let meta = parse(LEDGER_CONTRACT_JSON);
    assert_eq!(rows.len(), meta["good_rows_count"].as_u64().unwrap() as usize);
    for exp in meta["good_rows_expected"].as_array().unwrap() {
        let idx = exp["row_index"].as_u64().unwrap() as usize;
        let row = &rows[idx];
        assert_eq!(
            row.decision.as_deref(),
            exp["decision"].as_str(),
            "C2 row {idx} decision"
        );
        assert_eq!(
            row.side_cell_key.as_deref(),
            exp["side_cell_key"].as_str(),
            "C2 row {idx} side_cell_key"
        );
        assert_eq!(
            row.allowed_to_submit_order,
            exp["allowed_to_submit_order"].as_bool(),
            "C2 row {idx} allowed_to_submit_order"
        );
    }
}

#[test]
fn c2_rust_reads_python_writer_row_fields() {
    // 專證 Rust 能解析 Python sort_keys 行的 microsecond ts 與嵌套 event。
    let rows = LedgerRecord::from_jsonl_str(LEDGER_ROWS_JSONL).unwrap();
    let py_row = &rows[0];
    assert_eq!(py_row.decision.as_deref(), Some(ADMIT_DECISION));
    assert!(
        py_row.generated_at_utc.is_some(),
        "C2 python row generated_at_utc present"
    );
}

#[test]
fn c2_poison_bad_json_errors() {
    // 毒行①壞 JSON：Rust from_jsonl_str 整檔 Err（all-or-nothing 現狀）。
    let meta = parse(LEDGER_CONTRACT_JSON);
    let bad = meta["poison_rows"]["bad_json"].as_str().unwrap();
    assert!(
        LedgerRecord::from_jsonl_str(bad).is_err(),
        "C2 poison bad_json: Rust must Err"
    );
}

#[test]
fn c2_poison_non_dict_errors() {
    // 毒行②合法 JSON 非 dict（陣列）：Rust serde 型別不符 -> 整檔 Err。
    // （對照 Python：靜默跳過。E4 F4 已知不對稱，fixture current_behavior 記錄。）
    let meta = parse(LEDGER_CONTRACT_JSON);
    let non_dict = meta["poison_rows"]["non_dict_valid_json"].as_str().unwrap();
    assert!(
        LedgerRecord::from_jsonl_str(non_dict).is_err(),
        "C2 poison non_dict: Rust must Err (serde type mismatch)"
    );
    // 對賬 fixture 記錄的兩側現況（防後續改動悄悄改語義未同步 fixture）。
    assert_eq!(
        meta["current_behavior"]["rust_non_dict"].as_str().unwrap(),
        "Err (serde 型別不符)"
    );
    assert_eq!(
        meta["current_behavior"]["python_non_dict"].as_str().unwrap(),
        "silent skip (row dropped, no raise)"
    );
}

#[test]
fn c2_poison_torn_eof_errors() {
    // 毒行③torn EOF（截斷行）：Rust from_jsonl_str Err。
    let meta = parse(LEDGER_CONTRACT_JSON);
    let torn = meta["poison_rows"]["torn_eof"].as_str().unwrap();
    assert!(
        LedgerRecord::from_jsonl_str(torn).is_err(),
        "C2 poison torn_eof: Rust must Err"
    );
}

// ---------------------------------------------------------------------------
// C3 — order_link_id 5 段 + FNV-1a lineage hash
// ---------------------------------------------------------------------------

/// 從 Rust build 出來的 order_link_id 取第 5 段（lineage hash tag）。
fn hash_tag_from_order_link_id(order_link_id: &str) -> &str {
    order_link_id.split('_').nth(4).expect("5-segment order_link_id")
}

#[test]
fn c3_fnv1a_lineage_hash_vectors() {
    // Rust 無 pub hash 函數；用 build（固定 mode=demo/ts/seq=1）取第 5 段驗 hash。
    let v = parse(ORDER_LINK_ID_JSON);
    let ts_ms = 1_782_037_200_000u64;
    for hv in v["hash_vectors"].as_array().unwrap() {
        let sc = hv["side_cell_key"].as_str().unwrap();
        let ctx = hv["context_id"].as_str().unwrap();
        let sig = hv["signal_id"].as_str().unwrap();
        let expected = hv["expected_hash_tag"].as_str().unwrap();
        let olid = bounded_probe_order_link_id_for_candidate("demo", ts_ms, 1, sc, ctx, sig)
            .unwrap_or_else(|| panic!("C3 build None for hash vec {sc:?}"));
        assert_eq!(
            hash_tag_from_order_link_id(&olid),
            expected,
            "C3 hash drift for {sc:?}"
        );
        assert_eq!(expected.len(), 9, "hash tag len");
    }
}

#[test]
fn c3_separator_collision_is_shared_behavior() {
    // finding E4X-1：欄內含 0x1e 時分隔不保證不碰撞；Rust 亦碰撞（與 Python parity）。
    let v = parse(ORDER_LINK_ID_JSON);
    let ts_ms = 1_782_037_200_000u64;
    let a = &v["hash_vectors"][5];
    let b = &v["hash_vectors"][6];
    let olid_a = bounded_probe_order_link_id_for_candidate(
        "demo", ts_ms, 1,
        a["side_cell_key"].as_str().unwrap(),
        a["context_id"].as_str().unwrap(),
        a["signal_id"].as_str().unwrap(),
    )
    .unwrap();
    let olid_b = bounded_probe_order_link_id_for_candidate(
        "demo", ts_ms, 1,
        b["side_cell_key"].as_str().unwrap(),
        b["context_id"].as_str().unwrap(),
        b["signal_id"].as_str().unwrap(),
    )
    .unwrap();
    assert_eq!(
        hash_tag_from_order_link_id(&olid_a),
        hash_tag_from_order_link_id(&olid_b),
        "E4X-1: separator collision must reproduce on Rust side too"
    );
    assert_eq!(hash_tag_from_order_link_id(&olid_a), a["expected_hash_tag"].as_str().unwrap());
}

#[test]
fn c3_order_link_id_build_vectors() {
    let v = parse(ORDER_LINK_ID_JSON);
    for bv in v["build_vectors"].as_array().unwrap() {
        let em = bv["engine_mode"].as_str().unwrap();
        let ts = bv["ts_ms"].as_u64().unwrap();
        let seq = bv["seq"].as_u64().unwrap();
        let sc = bv["side_cell_key"].as_str().unwrap();
        let ctx = bv["context_id"].as_str().unwrap();
        let sig = bv["signal_id"].as_str().unwrap();
        let expected = bv["expected_order_link_id"].as_str().unwrap();
        let got = bounded_probe_order_link_id_for_candidate(em, ts, seq, sc, ctx, sig)
            .expect("C3 build must succeed");
        assert_eq!(got, expected, "C3 build drift");
        assert!(got.len() <= BYBIT_ORDER_LINK_ID_MAX_LEN);
        // 逆向驗證器必接受自產 id。
        assert!(
            is_candidate_bound_bounded_probe_order_link_id(&got, em, ts, sc, ctx, sig),
            "C3 self-built id must validate"
        );
    }
}

#[test]
fn c3_invalid_build_vectors_reject() {
    let v = parse(ORDER_LINK_ID_JSON);
    for iv in v["invalid_build_vectors"].as_array().unwrap() {
        let desc = iv["desc"].as_str().unwrap();
        let em = iv["engine_mode"].as_str().unwrap();
        let ts = iv["ts_ms"].as_u64().unwrap();
        let seq = iv["seq"].as_u64().unwrap();
        let sc = iv["side_cell_key"].as_str().unwrap();
        let ctx = iv["context_id"].as_str().unwrap();
        let sig = iv["signal_id"].as_str().unwrap();
        assert!(
            bounded_probe_order_link_id_for_candidate(em, ts, seq, sc, ctx, sig).is_none(),
            "C3 invalid {desc}: expected None"
        );
    }
}

#[test]
fn c3_engine_mode_tag_matrix_rust_side() {
    // Rust 側 engine_mode tag = trim+lowercase。用 build 取第 2 段驗（demo->dm/live_demo->ld）。
    // divergent=true 者（"Demo"/"DEMO"/" demo "）Rust 收但 Python exact-dict 拒——
    // fixture 已標，此測只釘 Rust 側現況（rust_tag）。
    let v = parse(ORDER_LINK_ID_JSON);
    let ts = 1_782_037_200_000u64;
    let (sc, ctx, sig) = ("ma_crossover|ETHUSDT|Sell", "ctx-1", "sig-1");
    for em in v["engine_mode_tag_matrix"].as_array().unwrap() {
        let mode = em["engine_mode"].as_str().unwrap();
        let expected_tag = em["rust_tag"].as_str();
        let olid = bounded_probe_order_link_id_for_candidate(mode, ts, 1, sc, ctx, sig);
        match expected_tag {
            Some(tag) => {
                let olid = olid
                    .unwrap_or_else(|| panic!("C3 engine_mode {mode:?}: expected build ok"));
                assert_eq!(
                    olid.split('_').nth(1).unwrap(),
                    tag,
                    "C3 engine_mode {mode:?} rust tag drift"
                );
            }
            None => assert!(
                olid.is_none(),
                "C3 engine_mode {mode:?}: rust expected reject"
            ),
        }
    }
}

// ---------------------------------------------------------------------------
// C5 — AdmissionConfig defaults + 範圍
// ---------------------------------------------------------------------------

#[test]
fn c5_admission_config_defaults() {
    let fx = parse(ADMISSION_CONFIG_JSON);
    let d = &fx["defaults"];
    let cfg = AdmissionConfig::default();
    assert_eq!(cfg.max_plan_age_hours, d["max_plan_age_hours"].as_u64().unwrap());
    assert_eq!(
        cfg.min_failed_outcomes_to_disable as u64,
        d["min_failed_outcomes_to_disable"].as_u64().unwrap()
    );
    assert_eq!(
        cfg.min_outcome_net_positive_pct,
        d["min_outcome_net_positive_pct"].as_f64().unwrap()
    );
    assert_eq!(cfg.min_avg_net_bps, d["min_avg_net_bps"].as_f64().unwrap());
    assert!(cfg.validate().is_ok(), "defaults must validate");
}

fn cfg_with_field(field: &str, value: &Value) -> AdmissionConfig {
    let mut cfg = AdmissionConfig::default();
    match field {
        "max_plan_age_hours" => cfg.max_plan_age_hours = value.as_u64().unwrap_or(0),
        "min_failed_outcomes_to_disable" => {
            cfg.min_failed_outcomes_to_disable = value.as_u64().unwrap_or(0) as usize
        }
        "min_outcome_net_positive_pct" => {
            cfg.min_outcome_net_positive_pct = value.as_f64().unwrap()
        }
        "min_avg_net_bps" => cfg.min_avg_net_bps = value.as_f64().unwrap(),
        other => panic!("unknown field {other}"),
    }
    cfg
}

#[test]
fn c5_range_reject_vectors() {
    let fx = parse(ADMISSION_CONFIG_JSON);
    for rv in fx["range_reject_vectors"].as_array().unwrap() {
        if !rv["rust_reject"].as_bool().unwrap() {
            continue;
        }
        let field = rv["field"].as_str().unwrap();
        // 負整數(如 max_plan_age_hours=0 已是 u64 邊界；-0.1 落在 f64 欄)由型別對應處理。
        let cfg = cfg_with_field(field, &rv["value"]);
        assert!(
            cfg.validate().is_err(),
            "C5 range reject {field}={:?}: expected Err",
            rv["value"]
        );
    }
}

#[test]
fn c5_range_accept_vectors() {
    let fx = parse(ADMISSION_CONFIG_JSON);
    for av in fx["range_accept_vectors"].as_array().unwrap() {
        let field = av["field"].as_str().unwrap();
        let cfg = cfg_with_field(field, &av["value"]);
        assert!(
            cfg.validate().is_ok(),
            "C5 range accept {field}={:?}: expected Ok (gate 不誤殺邊界)",
            av["value"]
        );
    }
}

#[test]
fn c5_nan_asymmetry_rust_rejects() {
    // B4 單側差異：Rust AdmissionConfig::validate 以 is_finite reject NaN
    //（Python validate_runtime_config 不 reject——fixture nan_vector 記錄）。
    let fx = parse(ADMISSION_CONFIG_JSON);
    assert!(fx["nan_vector"]["rust_reject"].as_bool().unwrap());
    let mut cfg = AdmissionConfig::default();
    cfg.min_avg_net_bps = f64::NAN;
    assert!(cfg.validate().is_err(), "Rust must reject NaN min_avg_net_bps");
}

// ---------------------------------------------------------------------------
// C6 — plan 檔路徑契約（shared 默認子路徑）
// ---------------------------------------------------------------------------

#[test]
fn c6_shared_default_subpath_contract() {
    // C6 default_subpath 是兩側共用契約（<data_dir>/<subpath>）。Rust
    // demo_learning_lane_plan_path 為 pub(crate)，其 override/default 解析由
    // demo_learning_lane_writer.rs 內部單元測試覆蓋、Python override 由 sibling
    // Python 測試覆蓋。此整合測試釘 fixture 的 subpath 契約字面（防 fixture 與
    // 兩側程式碼默認子路徑漂移）。override 優先 = PENDING（見 path_contract.json
    // override_priority_matrix_pending，待 env 修）。
    let fx = parse(PATH_CONTRACT_JSON);
    assert_eq!(
        fx["default_subpath"].as_str().unwrap(),
        "cost_gate_learning_lane/demo_learning_lane_plan_latest.json"
    );
    assert_eq!(fx["default_data_dir_fallback"].as_str().unwrap(), "/tmp/openclaw");
    assert_eq!(
        fx["env_names"]["plan_override"].as_str().unwrap(),
        "OPENCLAW_DEMO_LEARNING_LANE_PLAN"
    );
    assert_eq!(
        fx["env_names"]["data_dir"].as_str().unwrap(),
        "OPENCLAW_DATA_DIR"
    );
    // shared 默認矩陣兩側 agree
    for case in fx["shared_default_matrix"].as_array().unwrap() {
        assert!(
            case["both_sides_agree"].as_bool().unwrap(),
            "C6 shared default case must agree"
        );
    }
    // override 優先仍 pending（防有人誤把 fixture 標成 agree 而未實作 env 修）。
    assert!(
        !fx["override_priority_matrix_pending"][0]["both_sides_agree"]
            .as_bool()
            .unwrap(),
        "C6 override priority still PENDING on this branch"
    );
}
