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
