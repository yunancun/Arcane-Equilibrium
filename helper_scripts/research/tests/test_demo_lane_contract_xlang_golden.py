"""P1-8 跨語言 golden-vector 契約測試（Python 側）——demo learning lane。

MODULE_NOTE:
  模塊用途：消費 rust/openclaw_engine/tests/fixtures/demo_lane_contract/ 下的共用
    golden fixture，從 Python 側斷言 6 契約面（C1-C6）與 Rust sibling 測試
    (tests/demo_lane_contract_xlang_consistency.rs) 逐值等價。兩側各讀同一 fixture、
    各跑真實現、對同一 expected 斷言——任一側漂移即紅。
  覆蓋契約面（BB P1-8 §2.1）：
    C1 envelope 13-check 矩陣（單缺陷 reject + 全綠 accept + 邊界）
    C2 ledger 行互讀 + 毒行三態（skip-and-count 語義，兩側計數對賬）
    C3 order_link_id 5 段 + FNV-1a 9 位 lineage hash 向量
    C4 契約常量逐值
    C5 AdmissionConfig defaults + 範圍
    C6 plan 檔路徑 env 矩陣（override 優先子測 PENDING，見 test 註）
  被測對象（真跑，非 mock）：cost_gate_learning_lane.runtime_adapter（envelope /
    ledger / config）、cost_gate_learning_lane.proof_exclusion（order_link_id /
    FNV-1a）、cost_gate_learning_lane.contract / policy（常量）。
  硬邊界：純 source 測試，不觸 PG / Bybit / runtime / 授權檔。
  B2/B3 現況：fix/authz-contract-0704(5e89fb4e5) 已把 naive expiry、字串預算統一
    到 Rust 嚴格側（兩側 reject），fixture 依此釘死。
  已知單側差異（fixture 註記、非本測試 fail）：C3 engine_mode F10（"Demo" Rust 收
    Python 拒，待 db07df83b 合併）、C5 NaN（Rust reject/Python 不 reject，B4）、
    C6 override 優先（PENDING，待 env 修）。
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace
from pathlib import Path

import pytest

from cost_gate_learning_lane import proof_exclusion as px
from cost_gate_learning_lane import runtime_adapter as ra
from cost_gate_learning_lane.contract import (
    ADAPTER_SCHEMA_VERSION,
    ADMIT_DECISION,
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ELIGIBLE_REJECT_REASON_CODE,
    ORDER_AUTHORITY_GRANTED,
    OUTCOME_ADAPTER_SCHEMA_VERSION,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.runtime_adapter import (
    RuntimeAdmissionConfig,
    validate_runtime_config,
)


# ---------------------------------------------------------------------------
# fixture 目錄解析（in-tree，與 Rust include_str! 同源）
# ---------------------------------------------------------------------------

def _fixture_dir() -> Path:
    # 本檔在 helper_scripts/research/tests/；repo root = parents[3]。
    root = Path(__file__).resolve().parents[3]
    d = root / "rust" / "openclaw_engine" / "tests" / "fixtures" / "demo_lane_contract"
    assert d.is_dir(), f"fixture dir missing: {d}"
    return d


def _load(name: str) -> dict:
    return json.loads((_fixture_dir() / name).read_text(encoding="utf-8"))


def _candidate_event_context() -> dict:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "rust/openclaw_engine/tests/fixtures/candidate_event_context_v1/canonical_fixture.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["valid_candidate_event_context"]


# BYBIT_ORDER_LINK_ID_MAX_LEN 只在 Rust 常量；Python 側由 build 內 bybit-safe 檢查
# 隱含強制，取 manifest shared 值供 Python 測試比對（避免硬編碼漂移）。
_MAX_ORDER_LINK_ID_LEN = _load("constants.json")["shared"]["BYBIT_ORDER_LINK_ID_MAX_LEN"]


# ---------------------------------------------------------------------------
# C4 — 契約常量逐值
# ---------------------------------------------------------------------------

_SHARED_CONST_LOOKUP = {
    "PLAN_SCHEMA_VERSION": DEMO_LEARNING_LANE_SCHEMA_VERSION,
    "ADAPTER_SCHEMA_VERSION": ADAPTER_SCHEMA_VERSION,
    "ORDER_AUTHORITY_GRANTED": ORDER_AUTHORITY_GRANTED,
    "ELIGIBLE_REJECT_REASON_CODE": ELIGIBLE_REJECT_REASON_CODE,
    "ADMIT_DECISION": ADMIT_DECISION,
    "BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION": (
        BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION
    ),
    "BOUNDED_PROBE_AUTHORIZED_STATUS": BOUNDED_PROBE_AUTHORIZED_STATUS,
    "AUTHORITY_PATH_PATCH_READY_STATUS": AUTHORITY_PATH_PATCH_READY_STATUS,
    "OPERATOR_AUTHORIZATION_EXPIRED_REASON": "operator_authorization_expired",
    "ADMISSION_LEDGER_RECORD_TYPE": PROBE_ADMISSION_DECISION_RECORD_TYPE,
    "PROBE_OUTCOME_RECORD_TYPE": PROBE_OUTCOME_RECORD_TYPE,
    "BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE": BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    "BYBIT_ORDER_LINK_ID_PREFIX": "oc_",
    "BYBIT_ORDER_LINK_ID_MAX_LEN": 36,
    "ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ": px.ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ,
    "ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD": px.ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD,
    "ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN": px.ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN,
    "ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE": px.ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE,
}

_PYTHON_ONLY_CONST_LOOKUP = {
    "STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
    "STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS": STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    "PROBE_ADMISSION_DECISION_RECORD_TYPE": PROBE_ADMISSION_DECISION_RECORD_TYPE,
    # C4(冷審計 R2):outcome 面 record 的 schema 版本。Rust 不寫 outcome record 故非
    # shared;admission 面共用常量 ADAPTER_SCHEMA_VERSION(=adapter_v1)兩側 parity。
    "OUTCOME_ADAPTER_SCHEMA_VERSION": OUTCOME_ADAPTER_SCHEMA_VERSION,
}


def test_c4_shared_constants_match_manifest():
    manifest = _load("constants.json")
    shared = manifest["shared"]
    # fixture manifest 的每個 shared 常量必與 Python 真常量逐值相等。
    for key, expected in shared.items():
        assert key in _SHARED_CONST_LOOKUP, f"unmapped shared const {key}"
        assert _SHARED_CONST_LOOKUP[key] == expected, (
            f"C4 shared const drift {key}: python={_SHARED_CONST_LOOKUP[key]!r} "
            f"manifest={expected!r}"
        )
    # 反向：Python lookup 未遺漏 manifest 任一鍵。
    assert set(shared.keys()) == set(_SHARED_CONST_LOOKUP.keys())


def test_c4_python_only_constants_match_manifest():
    manifest = _load("constants.json")
    for key, expected in manifest["python_only"].items():
        assert _PYTHON_ONLY_CONST_LOOKUP[key] == expected, (
            f"C4 python_only const drift {key}"
        )


# ---------------------------------------------------------------------------
# C1 — envelope 13-check 矩陣
# ---------------------------------------------------------------------------

def _py_envelope_verdict(envelope: dict, now_utc: dt.datetime, side_cell: str):
    """呼叫真 Python envelope 判準（透過合成 plan+candidate；candidate 預算=1 避免
    干擾單缺陷判定）。回 (accepted, reason)。"""
    plan = {"operator_authorization": envelope}
    candidate = {"probe_proposal": {"max_probe_orders": 1}}
    return ra._valid_operator_authorization(plan, candidate, side_cell, now_utc=now_utc)


def test_c1_envelope_single_defect_matrix():
    m = _load("envelope_matrix.json")
    now_utc = dt.datetime.fromisoformat(m["now_utc"])
    side_cell = m["side_cell_key"]
    for vec in m["single_defect_matrix"]:
        ok, reason = _py_envelope_verdict(vec["envelope"], now_utc, side_cell)
        assert ok is False, f"C1 {vec['name']}: expected reject, got accept"
        assert reason == vec["python_expected_reason"], (
            f"C1 {vec['name']}: python reason drift got={reason!r} "
            f"expected={vec['python_expected_reason']!r}"
        )


def test_c1_envelope_all_green_accept():
    m = _load("envelope_matrix.json")
    now_utc = dt.datetime.fromisoformat(m["now_utc"])
    side_cell = m["side_cell_key"]
    vec = m["accept_vector"]
    ok, reason = _py_envelope_verdict(vec["envelope"], now_utc, side_cell)
    assert ok is True, f"C1 all-green: expected accept, got {reason!r}"
    assert reason == vec["python_expected_reason"]


def test_c1_envelope_boundary_vectors():
    m = _load("envelope_matrix.json")
    now_utc = dt.datetime.fromisoformat(m["now_utc"])
    side_cell = m["side_cell_key"]
    for vec in m["boundary_vectors"]:
        ok, reason = _py_envelope_verdict(vec["envelope"], now_utc, side_cell)
        assert ok is vec["expected_accept"], (
            f"C1 boundary {vec['name']}: accept got={ok} expected={vec['expected_accept']}"
        )
        assert reason == vec["python_expected_reason"], (
            f"C1 boundary {vec['name']}: reason drift got={reason!r} "
            f"expected={vec['python_expected_reason']!r}"
        )


def test_c1_boundary_naive_and_string_are_fail_closed():
    """B2/B3 方向守衛：naive expiry 與字串預算必 reject（不該因統一嚴格側而誤放行）。
    這是 gate 雙向的 fail-closed 側。"""
    m = _load("envelope_matrix.json")
    names = {v["name"]: v for v in m["boundary_vectors"]}
    assert names["expiry_naive_no_offset_reject"]["expected_accept"] is False
    assert names["budget_string_5_reject"]["expected_accept"] is False


def test_c1_gate_not_overzealous_valid_envelope_still_admits():
    """Gate 雙向：不該擋的正常路徑仍通過。全綠 tz-aware envelope（含 Z/+00:00/+08:00
    等價 12:00Z）必 accept，證統一嚴格側未誤殺合法 offset 形式。"""
    m = _load("envelope_matrix.json")
    accept_names = {
        v["name"] for v in m["boundary_vectors"] if v["expected_accept"] is True
    }
    assert {"expiry_Z_suffix_accept", "expiry_plus0000_accept",
            "expiry_plus0800_equiv_1200Z_accept"} <= accept_names


# ---------------------------------------------------------------------------
# C2 — ledger 行互讀 + 毒行三態
# ---------------------------------------------------------------------------

def test_c2_python_reads_good_rows_file():
    meta = _load("ledger_contract.json")
    rows = ra.read_jsonl_ledger(_fixture_dir() / meta["good_rows_file"])
    assert len(rows) == meta["good_rows_count"]
    for exp in meta["good_rows_expected"]:
        row = rows[exp["row_index"]]
        assert row["decision"] == exp["decision"]
        assert row["side_cell_key"] == exp["side_cell_key"]
        assert row["allowed_to_submit_order"] == exp["allowed_to_submit_order"]
        assert ra._attempt_id(row) == exp["attempt_id"], (
            f"C2 row {exp['row_index']} attempt_id drift"
        )


def test_c2_python_reads_rust_shape_row():
    """Python read_jsonl_ledger 讀 Rust-shape 行（納秒 RFC3339 generated_at_utc +
    bounded_probe_placement 缺欄）不炸、欄位可取。"""
    meta = _load("ledger_contract.json")
    rows = ra.read_jsonl_ledger(_fixture_dir() / meta["good_rows_file"])
    rust_row = rows[1]
    assert rust_row["generated_at_utc"].startswith("2026-06-21T11:00:00.123456789")
    assert "bounded_probe_placement" not in rust_row
    # decision fallback（頂層 decision 存在）
    assert ra._row_decision(rust_row) == ADMIT_DECISION


def test_c2_python_preserves_valid_rust_candidate_event_context(tmp_path):
    context = _candidate_event_context()
    event = {
        "strategy_name": context["strategy_name"],
        "symbol": context["symbol"],
        "side": context["side"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
        "candidate_event_context": context,
    }
    path = tmp_path / "valid_candidate_context.jsonl"
    path.write_text(json.dumps({"event": event}) + "\n", encoding="utf-8")

    rows = ra.read_jsonl_ledger(path)

    assert rows[0]["event"]["candidate_event_context"] == context
    assert (
        rows[0]["event"]["candidate_event_context"]["event_hash"]
        == context["event_hash"]
    )
    assert rows[0]["candidate_summary"]["candidate_event_context_status"] == "VALID"
    assert rows[0]["candidate_summary"]["candidate_event_context"] == context


def test_c2_python_rejects_invalid_rust_candidate_event_context(tmp_path):
    context = _candidate_event_context()
    context["event_hash"] = "0" * 64
    event = {
        "strategy_name": context["strategy_name"],
        "symbol": context["symbol"],
        "side": context["side"],
        "context_id": context["context_id"],
        "signal_id": context["signal_id"],
        "engine_mode": context["evidence_engine_mode"],
        "ts_ms": context["captured_at_ms"],
        "candidate_event_context": context,
    }
    path = tmp_path / "invalid_candidate_context.jsonl"
    path.write_text(json.dumps({"event": event}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="EVENT_CONTEXT_HASH_MISMATCH"):
        ra.read_jsonl_ledger(path)


@pytest.mark.parametrize(
    ("shape", "declaration"),
    [
        ("missing_event", "context"),
        ("missing_event", "valid_status"),
        ("nonmapping_event", "context"),
        ("nonmapping_event", "valid_status"),
    ],
)
def test_c2_summary_only_valid_context_cannot_bypass_event_validation(
    tmp_path,
    shape,
    declaration,
):
    summary = (
        {"candidate_event_context": _candidate_event_context()}
        if declaration == "context"
        else {"candidate_event_context_status": "VALID"}
    )
    row = {"candidate_summary": summary}
    if shape == "nonmapping_event":
        row["event"] = "not-an-event-object"
    path = tmp_path / f"summary_only_{shape}.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT"):
        ra.read_jsonl_ledger(path)


def test_c2_poison_bad_json_raises(tmp_path):
    """毒行①壞 JSON：Python read_jsonl_ledger raise（all-or-nothing 現狀）。"""
    meta = _load("ledger_contract.json")
    f = tmp_path / "bad.jsonl"
    f.write_text(meta["poison_rows"]["bad_json"] + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ra.read_jsonl_ledger(f)


def test_c2_poison_non_dict_silently_skipped(tmp_path):
    """毒行②合法 JSON 非 dict：Python 靜默跳過（skip-and-count，計數=0）。"""
    meta = _load("ledger_contract.json")
    f = tmp_path / "nondict.jsonl"
    # 一條有效行 + 一條非 dict 行 -> 只讀到有效那條（非 dict 被跳過）。
    good = (_fixture_dir() / meta["good_rows_file"]).read_text(
        encoding="utf-8"
    ).splitlines()[0]
    f.write_text(good + "\n" + meta["poison_rows"]["non_dict_valid_json"] + "\n",
                 encoding="utf-8")
    rows = ra.read_jsonl_ledger(f)
    assert len(rows) == 1, "非 dict 行應被跳過，只剩 1 有效行"
    assert rows[0]["decision"] == ADMIT_DECISION


def test_c2_poison_torn_eof_raises(tmp_path):
    """毒行③torn EOF（截斷行）：Python raise（JSONDecodeError 包成 ValueError）。"""
    meta = _load("ledger_contract.json")
    f = tmp_path / "torn.jsonl"
    f.write_text(meta["poison_rows"]["torn_eof"], encoding="utf-8")  # 無尾換行
    with pytest.raises(ValueError):
        ra.read_jsonl_ledger(f)


# ---------------------------------------------------------------------------
# C3 — order_link_id 5 段 + FNV-1a lineage hash
# ---------------------------------------------------------------------------

def _py_build_order_link_id(engine_mode, ts_ms, seq, side_cell, ctx, sig):
    """鏡像 Rust bounded_probe_order_link_id_for_candidate 的 build 路徑（Python
    無公開 builder，用同一常量/演算法組裝並過 bybit-safe 檢查）。"""
    mt = {"demo": "dm", "live_demo": "ld"}.get(engine_mode.strip().lower())
    if mt is None:
        return None
    if ts_ms == 0 or not (1 <= seq <= px.ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ):
        return None
    for v in (side_cell, ctx, sig):
        if not v or v.strip() != v:
            return None
    h = px._candidate_lineage_hash_tag(side_cell, ctx, sig)
    if h is None:
        return None
    olid = f"oc_{mt}_{ts_ms}_{px._to_base36(seq)}_{h}"
    t = olid.strip()
    if not t or t != olid or not t.startswith("oc_") or len(t) > 36:
        return None
    if not all(c.isalnum() or c in "_-" for c in t):
        return None
    return olid


def test_c3_fnv1a_lineage_hash_vectors():
    v = _load("order_link_id_vectors.json")
    for hv in v["hash_vectors"]:
        got = px._candidate_lineage_hash_tag(
            hv["side_cell_key"], hv["context_id"], hv["signal_id"]
        )
        assert got == hv["expected_hash_tag"], (
            f"C3 hash drift for {hv['side_cell_key']!r}: got={got!r} "
            f"expected={hv['expected_hash_tag']!r}"
        )
        assert len(got) == px.ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN


def test_c3_separator_collision_is_shared_behavior():
    """finding E4X-1：0x1e 分隔在欄內含 0x1e 時不保證不碰撞。兩側同碰撞（parity 成立）。
    此測釘「A/B 兩個不同 (side_cell,ctx) 切分產生相同 hash」是兩側共有行為。"""
    v = _load("order_link_id_vectors.json")
    a = v["hash_vectors"][5]
    b = v["hash_vectors"][6]
    ha = px._candidate_lineage_hash_tag(a["side_cell_key"], a["context_id"], a["signal_id"])
    hb = px._candidate_lineage_hash_tag(b["side_cell_key"], b["context_id"], b["signal_id"])
    assert ha == hb == a["expected_hash_tag"]
    # 正常字元跨欄界必改 hash（證分隔在無 0x1e 欄內確實生效）。
    n1 = v["hash_vectors"][3]
    n2 = v["hash_vectors"][4]
    assert n1["expected_hash_tag"] != n2["expected_hash_tag"]


def test_c3_order_link_id_build_vectors():
    v = _load("order_link_id_vectors.json")
    for bv in v["build_vectors"]:
        got = _py_build_order_link_id(
            bv["engine_mode"], bv["ts_ms"], bv["seq"],
            bv["side_cell_key"], bv["context_id"], bv["signal_id"],
        )
        assert got == bv["expected_order_link_id"], (
            f"C3 build drift: got={got!r} expected={bv['expected_order_link_id']!r}"
        )
        # BYBIT_ORDER_LINK_ID_MAX_LEN 是 Rust 常量（proof_exclusion.py 不 re-export，
        # 由 build 內的 bybit-safe 檢查隱含強制）；此處取 manifest shared 值對賬。
        assert len(got) <= _MAX_ORDER_LINK_ID_LEN
        # 逆向驗證器必接受自產 id。
        assert px._candidate_bound_active_order_link_id_is_valid(
            got, bv["engine_mode"], bv["ts_ms"],
            bv["side_cell_key"], bv["context_id"], bv["signal_id"],
        )


def test_c3_invalid_build_vectors_reject():
    v = _load("order_link_id_vectors.json")
    for iv in v["invalid_build_vectors"]:
        got = _py_build_order_link_id(
            iv["engine_mode"], iv["ts_ms"], iv["seq"],
            iv["side_cell_key"], iv["context_id"], iv["signal_id"],
        )
        assert got is None, f"C3 invalid {iv['desc']}: expected None, got {got!r}"


def test_c3_base36_roundtrip():
    v = _load("order_link_id_vectors.json")
    for rt in v["base36_roundtrip"]:
        assert px._to_base36(rt["value"]) == rt["base36"]
        assert px._parse_base36(rt["base36"]) == rt["value"]


def test_c3_engine_mode_tag_matrix_python_exact_side():
    """C3 engine_mode 矩陣：Python 為 exact-dict lookup（此分支未含 F10 修）。
    釘 python_exact_tag 現況；divergent=True 者記錄與 Rust 分歧（fixture 已標，
    待 db07df83b 合併後兩側統一）。"""
    v = _load("order_link_id_vectors.json")
    for em in v["engine_mode_tag_matrix"]:
        got = {"demo": "dm", "live_demo": "ld"}.get(em["engine_mode"])
        assert got == em["python_exact_tag"], (
            f"C3 engine_mode {em['engine_mode']!r}: python got={got!r} "
            f"expected={em['python_exact_tag']!r}"
        )


# ---------------------------------------------------------------------------
# C5 — AdmissionConfig defaults + 範圍
# ---------------------------------------------------------------------------

def test_c5_admission_config_defaults():
    cfg_fx = _load("admission_config.json")["defaults"]
    cfg = RuntimeAdmissionConfig()
    assert cfg.max_plan_age_hours == cfg_fx["max_plan_age_hours"]
    assert cfg.min_failed_outcomes_to_disable == cfg_fx["min_failed_outcomes_to_disable"]
    assert cfg.min_outcome_net_positive_pct == cfg_fx["min_outcome_net_positive_pct"]
    assert cfg.min_avg_net_bps == cfg_fx["min_avg_net_bps"]
    validate_runtime_config(cfg)  # 默認值必通過


def test_c5_range_reject_vectors():
    fx = _load("admission_config.json")
    for rv in fx["range_reject_vectors"]:
        if not rv["python_reject"]:
            continue
        cfg = replace(RuntimeAdmissionConfig(), **{rv["field"]: rv["value"]})
        with pytest.raises(ValueError):
            validate_runtime_config(cfg)


def test_c5_range_accept_vectors():
    fx = _load("admission_config.json")
    for av in fx["range_accept_vectors"]:
        cfg = replace(RuntimeAdmissionConfig(), **{av["field"]: av["value"]})
        validate_runtime_config(cfg)  # 邊界 inclusive 必通過（gate 不誤殺）


def test_c5_nan_asymmetry_python_does_not_reject():
    """B4 單側差異：Python validate_runtime_config 不 reject NaN（Rust is_finite reject）。
    釘現況供跨語言對賬；統一策略待裁（見 fixture nan_vector）。"""
    fx = _load("admission_config.json")["nan_vector"]
    assert fx["python_reject"] is False
    cfg = replace(RuntimeAdmissionConfig(), min_avg_net_bps=float("nan"))
    validate_runtime_config(cfg)  # 不 raise = 確認 Python 側不擋 NaN


# ---------------------------------------------------------------------------
# C6 — plan 檔路徑 env 矩陣
# ---------------------------------------------------------------------------

def test_c6_shared_default_matrix(monkeypatch):
    fx = _load("path_contract.json")
    for case in fx["shared_default_matrix"]:
        for k in ("OPENCLAW_DATA_DIR", "OPENCLAW_DEMO_LEARNING_LANE_PLAN"):
            monkeypatch.delenv(k, raising=False)
        for k, val in case["env"].items():
            monkeypatch.setenv(k, val)
        got = ra._default_plan_path()
        assert str(got) == case["expected_plan_path"], (
            f"C6 shared default drift: got={got} expected={case['expected_plan_path']}"
        )


@pytest.mark.skip(
    reason="C6 override 優先 PENDING：此分支 Python _default_plan_path 只認 "
    "OPENCLAW_DATA_DIR，不支援 OPENCLAW_DEMO_LEARNING_LANE_PLAN override；Rust "
    "demo_learning_lane_plan_path 支援。兩側分歧待 env 修（overgate-b/後續 E1）"
    "落地後解除 skip 並釘 rust_expected==python_expected。"
)
def test_c6_override_priority_pending(monkeypatch):
    fx = _load("path_contract.json")
    case = fx["override_priority_matrix_pending"][0]
    for k, val in case["env"].items():
        monkeypatch.setenv(k, val)
    got = ra._default_plan_path()
    # 修後預期：Python 亦取 override，與 Rust 一致。
    assert str(got) == case["rust_expected_plan_path"]
