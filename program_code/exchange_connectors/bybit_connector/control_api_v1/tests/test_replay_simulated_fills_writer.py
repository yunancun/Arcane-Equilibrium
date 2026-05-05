"""REF-20 Sprint A R3-T2 — simulated_fills writer unit tests.
REF-20 Sprint A R3-T2 — simulated_fills writer 單元測試。

MODULE_NOTE (EN):
    Hermetic 7-case suite for ``replay/simulated_fills_writer.py``.
    Tests cover JSON parser, V050 row mapping, ON CONFLICT idempotency,
    payload truncation, and the high-level ``persist_replay_report``
    flow with mock cursor.

    Cases:
      1. parse_replay_report_json happy path (schema_version=1).
      2. parse_replay_report_json unknown schema_version raises.
      3. parse_replay_report_json oversized file raises.
      4. map_fill_to_v050_row evidence_tier allowlist reject.
      5. map_fill_to_v050_row qty/price <=0 reject.
      6. insert_simulated_fills idempotent via composite UNIQUE.
      7. persist_replay_report zero fills writes zero rows.
      8. map_fill_to_v050_row payload truncation marker.

MODULE_NOTE (中):
    封閉式 7-case 套件覆蓋 ``replay/simulated_fills_writer.py``。
    測試含 JSON parser、V050 row 映射、ON CONFLICT 冪等性、payload
    截斷，以及高層 ``persist_replay_report`` 流程（mock cursor）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3 R3-T2
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Test path injection identical to sibling test file pattern.
# 測試路徑注入與 sibling test file 模式一致。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.simulated_fills_writer import (  # noqa: E402
    MAX_PAYLOAD_BYTES,
    MAX_REPORT_BYTES,
    SimulatedFillsWriteResult,
    build_decision_evidence_index,
    consume_decision_evidence_for_fill,
    extract_decision_traces,
    insert_simulated_fills,
    map_fill_to_v050_row,
    parse_replay_report_json,
    persist_replay_report,
)


# ─── Fixtures / 測試固件 ─────────────────────────────────────────────


def _make_envelope(fills: list[dict]) -> dict:
    """Build a valid replay_report.json envelope with given fills."""
    return {
        "schema_version": 1,
        "generated_at_ms": 1717000000000,
        "manifest_id": "11111111-1111-1111-1111-111111111111",
        "execution_confidence": "none",
        "result": {
            "manifest_id": "11111111-1111-1111-1111-111111111111",
            "status": "Completed",
            "execution_confidence": "none",
            "fills": fills,
            "pnl_summary": {
                "events_processed": len(fills),
                "fills_emitted": len(fills),
                "starting_balance": 10000.0,
                "ending_balance": 10100.0,
                "net_pnl": 100.0,
            },
            "diagnostics": {
                "guard_enforce_runtime_calls": 0,
                "last_action_label": "test",
                "abort_reason": None,
            },
        },
    }


def _write_envelope(envelope: dict) -> Path:
    """Persist envelope to a temp file, return Path."""
    fd, name = tempfile.mkstemp(suffix=".json", prefix="replay_report_test_")
    os.close(fd)
    p = Path(name)
    p.write_text(json.dumps(envelope), encoding="utf-8")
    return p


def _make_synthetic_fill(idx: int = 0, **overrides) -> dict:
    """Build a single SimulatedFill dict matching Rust runner output."""
    fill = {
        "ts_ms": 1717000000000 + idx * 1000,
        "symbol": "BTCUSDT",
        "side": "long",
        "qty": 1.0,
        "price": 50000.0 + idx,
        "evidence_source_tier": "synthetic_replay",
    }
    fill.update(overrides)
    return fill


# ─── Case 1: parse happy path ────────────────────────────────────────


def test_parse_replay_report_json_happy_path():
    """Case 1: schema_version=1 + result.fills list parses cleanly.
    Case 1：schema_version=1 + result.fills list 解析乾淨。
    """
    envelope = _make_envelope([_make_synthetic_fill(0), _make_synthetic_fill(1)])
    p = _write_envelope(envelope)
    try:
        parsed = parse_replay_report_json(p)
        assert parsed["schema_version"] == 1
        assert len(parsed["result"]["fills"]) == 2
    finally:
        p.unlink(missing_ok=True)


# ─── Case 2: parse unknown schema_version ────────────────────────────


def test_parse_replay_report_json_unknown_schema_version_raises():
    """Case 2: schema_version=99 → ValueError.
    Case 2：schema_version=99 → ValueError。
    """
    envelope = _make_envelope([])
    envelope["schema_version"] = 99
    p = _write_envelope(envelope)
    try:
        with pytest.raises(ValueError, match="unsupported.*schema_version"):
            parse_replay_report_json(p)
    finally:
        p.unlink(missing_ok=True)


# ─── Case 3: parse oversized file ────────────────────────────────────


def test_parse_replay_report_json_oversized_file_raises():
    """Case 3: file > MAX_REPORT_BYTES → ValueError before json.loads.
    Case 3：檔案 > MAX_REPORT_BYTES → ValueError（在 json.loads 前）。
    """
    fd, name = tempfile.mkstemp(suffix=".json", prefix="replay_report_oversize_")
    os.close(fd)
    p = Path(name)
    try:
        # Write garbage bytes exceeding cap.
        # 寫超過 cap 的垃圾 byte。
        p.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
        with pytest.raises(ValueError, match="exceeds cap"):
            parse_replay_report_json(p)
    finally:
        p.unlink(missing_ok=True)


# ─── Case 4: map row evidence_tier allowlist reject ──────────────────


def test_map_fill_to_v050_row_evidence_tier_allowlist_reject():
    """Case 4: tier='real_outcome' (not in V050 allowlist) → None.
    Case 4：tier='real_outcome'（不在 V050 白名單）→ None。
    """
    fill = _make_synthetic_fill(0, evidence_source_tier="real_outcome")
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is None, "real_outcome must be rejected"


# ─── Case 5: map row qty/price <=0 reject ────────────────────────────


def test_map_fill_to_v050_row_qty_zero_rejects():
    """Case 5: qty=0 violates V050 CHECK qty>0 → return None.
    Case 5：qty=0 違 V050 CHECK qty>0 → 回 None。
    """
    fill = _make_synthetic_fill(0, qty=0.0)
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is None


def test_map_fill_to_v050_row_negative_price_rejects():
    """Case 5b: price<0 violates V050 CHECK price>0 → return None.
    Case 5b：price<0 違 V050 CHECK price>0 → 回 None。
    """
    fill = _make_synthetic_fill(0, price=-100.0)
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is None


# ─── Case 6: insert idempotent via composite UNIQUE ──────────────────


def test_insert_simulated_fills_idempotent_via_composite_unique():
    """Case 6: ON CONFLICT (experiment_id, idempotency_key) DO NOTHING semantics.
    Case 6：ON CONFLICT (experiment_id, idempotency_key) DO NOTHING 語意。

    Mock cursor that simulates rowcount=0 on second INSERT (conflict).
    Mock cursor 模擬第二次 INSERT rowcount=0（衝突）。
    """
    cur = MagicMock()
    # First call: INSERT succeeds (rowcount=1); second: ON CONFLICT (rowcount=0).
    # 第一次：INSERT 成功 (rowcount=1)；第二次：ON CONFLICT (rowcount=0)。
    rowcount_seq = iter([1, 0])

    def _execute(sql, params=None):
        # Set rowcount based on call sequence.
        # 依呼叫序設 rowcount。
        cur.rowcount = next(rowcount_seq)

    cur.execute.side_effect = _execute

    fill_params = [
        {
            "sim_fill_id": "aaaa1111aaaa1111aaaa1111aaaa1111",
            "experiment_id": "11111111-1111-1111-1111-111111111111",
            "intent_id": None, "decision_lease_id": None,
            "idempotency_key": "run123:0",
            "ts": "2026-05-04T00:00:00+00:00", "ts_ms": 1717000000000,
            "symbol": "BTCUSDT", "strategy_name": "grid_trading",
            "side": "long", "qty": 1.0, "price": 50000.0,
            "fee": 0.0, "fee_rate": 0.0, "liquidity_role": "taker",
            "evidence_source_tier": "synthetic_replay",
            "execution_model_version": "synthetic_v1",
            "ci_low_bps": None, "ci_mid_bps": None, "ci_high_bps": None,
            "payload": "{}",
        },
        {
            "sim_fill_id": "bbbb1111bbbb1111bbbb1111bbbb1111",
            "experiment_id": "11111111-1111-1111-1111-111111111111",
            "intent_id": None, "decision_lease_id": None,
            "idempotency_key": "run123:0",  # duplicate key
            "ts": "2026-05-04T00:00:00+00:00", "ts_ms": 1717000000000,
            "symbol": "BTCUSDT", "strategy_name": "grid_trading",
            "side": "long", "qty": 1.0, "price": 50000.0,
            "fee": 0.0, "fee_rate": 0.0, "liquidity_role": "taker",
            "evidence_source_tier": "synthetic_replay",
            "execution_model_version": "synthetic_v1",
            "ci_low_bps": None, "ci_mid_bps": None, "ci_high_bps": None,
            "payload": "{}",
        },
    ]
    inserted = insert_simulated_fills(cur, fill_params)
    assert inserted == 1, f"only first row should insert, got {inserted}"


# ─── Case 7: persist zero fills ──────────────────────────────────────


def test_persist_replay_report_zero_fills_writes_zero_rows():
    """Case 7: empty fills list → fills_inserted=0, no errors.
    Case 7：空 fills list → fills_inserted=0，無 errors。
    """
    envelope = _make_envelope([])
    p = _write_envelope(envelope)
    try:
        cur = MagicMock()
        # strategy_name lookup → ('grid_trading',).
        # strategy_name lookup → ('grid_trading',)。
        cur.fetchone.return_value = ("grid_trading",)

        result = persist_replay_report(
            cur, p,
            experiment_id="11111111-1111-1111-1111-111111111111",
            run_id="abc123",
        )
        assert isinstance(result, SimulatedFillsWriteResult)
        assert result.fills_inserted == 0
        assert result.fills_skipped == 0
        # No INSERT call should have been issued (only the SELECT for strategy).
        # 不應 INSERT（僅 SELECT strategy）。
        sql_calls = [c.args[0] for c in cur.execute.call_args_list]
        insert_calls = [s for s in sql_calls if "INSERT INTO replay.simulated_fills" in s]
        assert len(insert_calls) == 0
    finally:
        p.unlink(missing_ok=True)


# ─── Case 8: payload truncation marker ───────────────────────────────


def test_map_fill_to_v050_row_payload_truncation_marker():
    """Case 8: oversized fill payload → truncation marker written.
    Case 8：oversize fill payload → 寫截斷標記。
    """
    # Build a fill whose JSON serialization > MAX_PAYLOAD_BYTES.
    # 構造 JSON 序列化超 MAX_PAYLOAD_BYTES 的 fill。
    big_str = "x" * (MAX_PAYLOAD_BYTES + 100)
    fill = _make_synthetic_fill(0, _bloat=big_str)
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["_payload_truncated"] is True
    payload_obj = json.loads(result["payload"])
    assert payload_obj.get("_truncated") is True
    assert payload_obj.get("_original_size", 0) > MAX_PAYLOAD_BYTES


# ─── Case 9: persist happy path inserts N rows ───────────────────────


def test_persist_replay_report_happy_path_inserts_fills():
    """Case 9: 3 valid fills → 3 INSERTs issued, 3 rows reported.
    Case 9：3 個合法 fill → 3 次 INSERT，回報 3 row。
    """
    envelope = _make_envelope([
        _make_synthetic_fill(0),
        _make_synthetic_fill(1),
        _make_synthetic_fill(2),
    ])
    p = _write_envelope(envelope)
    try:
        cur = MagicMock()
        # strategy_name SELECT then 3 INSERTs.
        # First fetchone (SELECT strategy) → ('grid_trading',).
        # 之後 fetchone 不再被讀（INSERT 用 rowcount）。
        cur.fetchone.return_value = ("grid_trading",)

        # rowcount per INSERT call (success = 1).
        # INSERT 每次 rowcount = 1（成功）。
        rowcount_seq = iter([0, 1, 1, 1])  # 0 for SELECT (no-op), 1×3 for INSERT

        def _execute(sql, params=None):
            cur.rowcount = next(rowcount_seq)

        cur.execute.side_effect = _execute

        result = persist_replay_report(
            cur, p,
            experiment_id="11111111-1111-1111-1111-111111111111",
            run_id="abc123",
        )
        assert result.fills_inserted == 3
        assert result.fills_skipped == 0
    finally:
        p.unlink(missing_ok=True)


# ─── Case 10: persist mixed valid + skipped fills ────────────────────


def test_persist_replay_report_mixed_valid_and_skipped_fills():
    """Case 10: 2 valid + 1 invalid_tier fill → inserted=2, skipped=1.
    Case 10：2 合法 + 1 無效 tier → inserted=2、skipped=1。
    """
    envelope = _make_envelope([
        _make_synthetic_fill(0),
        _make_synthetic_fill(1, evidence_source_tier="real_outcome"),  # skip
        _make_synthetic_fill(2),
    ])
    p = _write_envelope(envelope)
    try:
        cur = MagicMock()
        cur.fetchone.return_value = ("grid_trading",)
        rowcount_seq = iter([0, 1, 1])  # SELECT (0) + 2 INSERT (1, 1)

        def _execute(sql, params=None):
            cur.rowcount = next(rowcount_seq)

        cur.execute.side_effect = _execute

        result = persist_replay_report(
            cur, p,
            experiment_id="11111111-1111-1111-1111-111111111111",
            run_id="abc123",
        )
        assert result.fills_inserted == 2, f"expected 2, got {result.fills_inserted}"
        assert result.fills_skipped == 1
    finally:
        p.unlink(missing_ok=True)


# ─── REF-20 Sprint B2 R5-T5 — decision-evidence injection tests ──────


def _make_decision_trace_open(
    *, ts_ms: int, symbol: str, qty: float, intent_signature: str = "abc123def456" * 4
) -> dict:
    """Build a single Open-side decision_traces entry mirroring Rust schema.
    建構一筆 Open 側 decision_traces entry 鏡射 Rust schema。
    """
    return {
        "ts_ms": ts_ms,
        "symbol": symbol,
        "strategy_name": "grid_trading",
        "indicators_present": False,
        "actions_emitted": [
            {
                "Open": {
                    "intent_signature": intent_signature,
                    "symbol": symbol,
                    "is_long": True,
                    "confidence": 0.5,
                    "qty": qty,
                    "strategy": "grid_trading",
                    "order_type": "market",
                }
            }
        ],
    }


def test_extract_decision_traces_absent_returns_empty():
    """R5-T5 Case A: synthetic walker run with no decision_traces field → []."""
    envelope = _make_envelope([_make_synthetic_fill(0)])
    # synthetic walker — Rust serde_json #[serde(default)] omits field.
    # synthetic walker — Rust serde_json #[serde(default)] 略 field。
    envelope["result"].pop("decision_traces", None)
    traces = extract_decision_traces(envelope)
    assert traces == []


def test_extract_decision_traces_well_formed_kept():
    """R5-T5 Case B: well-formed decision_traces entry survives extraction."""
    envelope = _make_envelope([_make_synthetic_fill(0)])
    envelope["result"]["decision_traces"] = [
        _make_decision_trace_open(ts_ms=1717000000000, symbol="BTCUSDT", qty=0.01),
    ]
    traces = extract_decision_traces(envelope)
    assert len(traces) == 1
    assert traces[0]["symbol"] == "BTCUSDT"


def test_extract_decision_traces_malformed_dropped():
    """R5-T5 Case B2: malformed entry (missing ts_ms / wrong type) dropped."""
    envelope = _make_envelope([_make_synthetic_fill(0)])
    envelope["result"]["decision_traces"] = [
        {"symbol": "BTCUSDT", "actions_emitted": []},  # missing ts_ms
        {"ts_ms": "not_int", "symbol": "BTC", "actions_emitted": []},
        _make_decision_trace_open(ts_ms=1717000000000, symbol="BTCUSDT", qty=0.01),
    ]
    traces = extract_decision_traces(envelope)
    assert len(traces) == 1, f"expected 1 well-formed, got {len(traces)}"


def test_consume_decision_evidence_matches_open_fill():
    """R5-T5 Case C: ts_ms+symbol+side match → evidence returned + popped."""
    traces = [
        _make_decision_trace_open(ts_ms=1717000000000, symbol="BTCUSDT", qty=0.01),
    ]
    idx = build_decision_evidence_index(traces)
    fill = _make_synthetic_fill(0)
    fill["ts_ms"] = 1717000000000
    fill["qty"] = 0.01
    evidence = consume_decision_evidence_for_fill(fill, idx)
    assert evidence is not None
    assert evidence["strategy_decision"] == "open"
    assert evidence["risk_decision"] == "accepted"
    assert evidence["intent_signature"]
    assert evidence["intended_qty"] == 0.01
    # Greedy consumption: second consume returns None.
    # 貪婪消費：第二次取為 None。
    second = consume_decision_evidence_for_fill(fill, idx)
    assert second is None


def test_consume_decision_evidence_qty_zero_marks_rejected():
    """R5-T5 Case D: qty=0 ghost fill maps to risk_decision=rejected."""
    traces = [
        _make_decision_trace_open(ts_ms=1717000000000, symbol="BTCUSDT", qty=0.01),
    ]
    idx = build_decision_evidence_index(traces)
    fill = _make_synthetic_fill(0)
    fill["ts_ms"] = 1717000000000
    fill["qty"] = 0.0  # ghost row from Gate 1.5 reject
    fill["side"] = "long"
    evidence = consume_decision_evidence_for_fill(fill, idx)
    assert evidence is not None
    assert evidence["risk_decision"] == "rejected"
    assert evidence["rejected_reason"] is not None
    assert "ghost_fill" in evidence["rejected_reason"]


def test_map_fill_to_v050_row_injects_decision_evidence():
    """R5-T5 Case E: decision_evidence kw arg injects payload sub-object."""
    fill = _make_synthetic_fill(0)
    fill["ts_ms"] = 1717000000000
    decision_evidence = {
        "signal_id": "1717000000000:BTCUSDT:long",
        "strategy_decision": "open",
        "risk_decision": "accepted",
        "rejected_reason": None,
        "intent_signature": "deadbeef" * 8,
        "intended_qty": 0.01,
        "intended_price": 50000.0,
    }
    params = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
        decision_evidence=decision_evidence,
    )
    assert params is not None
    payload = json.loads(params["payload"])
    assert "_replay_decision_evidence" in payload
    inner = payload["_replay_decision_evidence"]
    assert inner["intent_signature"].startswith("deadbeef")
    assert inner["risk_decision"] == "accepted"
    assert inner["intended_qty"] == 0.01


def test_map_fill_to_v050_row_no_evidence_no_injection():
    """R5-T5 Case F: decision_evidence=None leaves payload free of marker."""
    fill = _make_synthetic_fill(0)
    params = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
        decision_evidence=None,
    )
    assert params is not None
    payload = json.loads(params["payload"])
    assert "_replay_decision_evidence" not in payload, (
        "no evidence supplied but marker injected"
    )


def test_persist_replay_report_with_decision_traces_inline_evidence():
    """R5-T5 Case G: end-to-end — adapter-path envelope with decision_traces.

    Verifies that persist_replay_report wires extract → index → consume →
    map flow so the rendered V050 INSERT param's `payload` jsonb contains
    `_replay_decision_evidence` sub-object.
    驗收：persist_replay_report 串通 extract → index → consume → map 流程，
    使最終 V050 INSERT param 的 `payload` jsonb 含 `_replay_decision_evidence`
    子物件。
    """
    fill0 = _make_synthetic_fill(0)
    fill0["ts_ms"] = 1717000000000
    fill0["qty"] = 0.01
    envelope = _make_envelope([fill0])
    envelope["result"]["decision_traces"] = [
        _make_decision_trace_open(ts_ms=1717000000000, symbol="BTCUSDT", qty=0.01),
    ]
    p = _write_envelope(envelope)
    try:
        cur = MagicMock()
        cur.fetchone.return_value = ("grid_trading",)
        # SELECT (rowcount=0) + 1 INSERT (rowcount=1).
        rowcount_seq = iter([0, 1])

        captured_params: list[dict] = []

        def _execute(sql, params=None):
            cur.rowcount = next(rowcount_seq, 0)
            if params is not None and "INSERT" in sql:
                captured_params.append(dict(params))

        cur.execute.side_effect = _execute

        result = persist_replay_report(
            cur, p,
            experiment_id="11111111-1111-1111-1111-111111111111",
            run_id="abc123",
        )
        assert result.fills_inserted == 1
        assert len(captured_params) == 1
        payload = json.loads(captured_params[0]["payload"])
        assert "_replay_decision_evidence" in payload
        assert payload["_replay_decision_evidence"]["risk_decision"] == "accepted"
    finally:
        p.unlink(missing_ok=True)


def test_persist_replay_report_synthetic_walker_no_evidence():
    """R5-T5 Case H: legacy synthetic walker (no traces) → no evidence marker.

    Confirms backward compatibility — fills from the R5-T3 synthetic walker
    path (proof_1/4/5 e2e baseline) do not get evidence markers and the
    payload remains the bare fill object.
    確認向後兼容 — R5-T3 synthetic walker（proof_1/4/5 e2e baseline）的 fill
    無 evidence marker，payload 保持為純 fill 物件。
    """
    envelope = _make_envelope([_make_synthetic_fill(0)])
    # Explicitly drop decision_traces to mimic synthetic walker run.
    # 顯式刪 decision_traces 模擬 synthetic walker run。
    envelope["result"].pop("decision_traces", None)
    p = _write_envelope(envelope)
    try:
        cur = MagicMock()
        cur.fetchone.return_value = ("grid_trading",)
        rowcount_seq = iter([0, 1])
        captured_params: list[dict] = []

        def _execute(sql, params=None):
            cur.rowcount = next(rowcount_seq, 0)
            if params is not None and "INSERT" in sql:
                captured_params.append(dict(params))

        cur.execute.side_effect = _execute

        result = persist_replay_report(
            cur, p,
            experiment_id="11111111-1111-1111-1111-111111111111",
            run_id="abc123",
        )
        assert result.fills_inserted == 1
        payload = json.loads(captured_params[0]["payload"])
        assert "_replay_decision_evidence" not in payload, (
            "synthetic walker fill leaked evidence marker"
        )
    finally:
        p.unlink(missing_ok=True)


# ─── R6-T5: Sprint C 真實 fee/slippage/liquidity_role 解析 ──────────


def test_map_fill_v050_row_extracts_real_fee_from_rust_json():
    """R6-T5: Rust runner 寫真實 fee + fee_rate 進 fill JSON，writer 必解析非用 0.0。"""
    fill = _make_synthetic_fill(
        0,
        fee=2.75,
        fee_rate=0.00055,
        liquidity_role="taker",
        execution_model_version="calibrated_v1",
    )
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["fee"] == 2.75
    assert result["fee_rate"] == 0.00055
    assert result["liquidity_role"] == "taker"
    assert result["execution_model_version"] == "calibrated_v1"


def test_map_fill_v050_row_maker_liquidity_role_from_postonly():
    """R6-T5: PostOnly TIF → Rust 端寫 liquidity_role='maker'，writer 直傳。"""
    fill = _make_synthetic_fill(
        0, fee=1.0, fee_rate=0.0002, liquidity_role="maker"
    )
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["liquidity_role"] == "maker"
    assert result["fee_rate"] == 0.0002


def test_map_fill_v050_row_invalid_liquidity_role_falls_back_to_taker():
    """R6-T5: liquidity_role 不在 V050 enum allowlist → fallback 'taker' default。"""
    fill = _make_synthetic_fill(0, fee=1.0, liquidity_role="invalid_role")
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["liquidity_role"] == "taker", (
        "unknown enum value should fallback to taker default per LIQUIDITY_ROLE_DEFAULT"
    )


def test_map_fill_v050_row_synthetic_walker_fallback_to_sentinel_defaults():
    """R6-T5: synthetic walker fill 不帶 fee/fee_rate/liquidity_role keys → fallback Sprint A defaults。"""
    fill = _make_synthetic_fill(0)
    assert "fee" not in fill
    assert "fee_rate" not in fill
    assert "liquidity_role" not in fill
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["fee"] == 0.0
    assert result["fee_rate"] == 0.0
    assert result["liquidity_role"] == "taker"
    assert result["execution_model_version"] == "synthetic_v1"


def test_map_fill_v050_row_unknown_liquidity_role_accepted():
    """R6-T5: liquidity_role='unknown' 是 V050 enum 合法值（per CHECK），不 fallback。"""
    fill = _make_synthetic_fill(0, fee=1.0, liquidity_role="unknown")
    result = map_fill_to_v050_row(
        fill,
        experiment_id="11111111-1111-1111-1111-111111111111",
        run_id="abc123",
        fill_index=0,
        strategy_name="grid_trading",
    )
    assert result is not None
    assert result["liquidity_role"] == "unknown"
