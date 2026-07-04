"""
MODULE_NOTE
模塊用途:P1-10 probe_ledger rotation / retention / 跨輪轉讀取的驗收測試
  (到閾值輪轉、retention 清理、讀取視圖跨輪轉不丟行不重複)。
依賴:cost_gate_learning_lane.ledger_rotation、runtime_adapter(read/append 兩個
  choke point)。
硬邊界:純 tmp_path 檔案操作,零 PG / 零網路 / 零 runtime。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane import ledger_rotation
from cost_gate_learning_lane.ledger_rotation import (
    maybe_rotate_ledger,
    retained_ledger_files,
    rotated_segment_paths,
)
from cost_gate_learning_lane.runtime_adapter import (
    append_jsonl_ledger,
    read_jsonl_ledger,
)

_NOW = dt.datetime(2026, 7, 4, 12, 0, 0, tzinfo=dt.timezone.utc)


def _write_rows(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for key in keys:
            fh.write(json.dumps({"attempt_id": key}) + "\n")


def _keys(rows: list[dict]) -> list[str]:
    return [row["attempt_id"] for row in rows]


def test_rotation_below_threshold_is_noop(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_rows(ledger, ["a1"])
    summary = maybe_rotate_ledger(ledger, threshold_bytes=10_000, now_utc=_NOW)
    assert summary["rotated"] is False
    assert ledger.exists()
    assert rotated_segment_paths(ledger) == []


def test_rotation_missing_ledger_is_noop(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    summary = maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)
    assert summary == {"rotated": False, "segment_path": None, "expired_deleted": 0}


def test_rotation_triggers_at_threshold_and_preserves_rows(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_rows(ledger, ["a1", "a2"])
    summary = maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)
    assert summary["rotated"] is True
    segment = Path(summary["segment_path"])
    assert segment.name == "probe_ledger.20260704T120000Z.jsonl"
    # 主檔被轉走;段檔內容 = 輪轉前主檔全部行,經視圖讀取不丟行。
    assert not ledger.exists()
    assert _keys(read_jsonl_ledger(ledger)) == ["a1", "a2"]
    assert [line for line in segment.read_text().splitlines() if line] == [
        json.dumps({"attempt_id": "a1"}),
        json.dumps({"attempt_id": "a2"}),
    ]
    # 主檔缺席時再呼叫 = no-op。
    again = maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)
    assert again["rotated"] is False


def test_rotation_segment_name_collision_bumps_seq(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_rows(ledger, ["a1"])
    first = maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)
    _write_rows(ledger, ["a2"])
    second = maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)
    assert Path(first["segment_path"]).name == "probe_ledger.20260704T120000Z.jsonl"
    assert Path(second["segment_path"]).name == "probe_ledger.20260704T120000Z_1.jsonl"
    # 枚舉順序:(ts, seq) 升冪。
    assert [p.name for p in rotated_segment_paths(ledger)] == [
        "probe_ledger.20260704T120000Z.jsonl",
        "probe_ledger.20260704T120000Z_1.jsonl",
    ]


def test_retention_sweep_deletes_only_expired_segments(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    expired = tmp_path / "probe_ledger.20260601T000000Z.jsonl"  # 33 天前
    fresh = tmp_path / "probe_ledger.20260701T000000Z.jsonl"  # 3 天前
    unrelated = tmp_path / "sealed_horizon_learning_evidence_source_rows_20260601T000000Z.jsonl"
    malformed_name = tmp_path / "probe_ledger.not-a-ts.jsonl"
    for path in (expired, fresh, unrelated, malformed_name):
        _write_rows(path, ["x"])
    _write_rows(ledger, ["a1"])
    summary = maybe_rotate_ledger(ledger, threshold_bytes=1, retention_days=14, now_utc=_NOW)
    assert summary["rotated"] is True
    assert summary["expired_deleted"] == 1
    assert not expired.exists()
    # 未過期段、無關檔案、不匹配段名契約的檔案一律不動。
    assert fresh.exists()
    assert unrelated.exists()
    assert malformed_name.exists()


def test_retained_view_excludes_expired_segments_even_if_not_deleted(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    expired = tmp_path / "probe_ledger.20260601T000000Z.jsonl"
    fresh = tmp_path / "probe_ledger.20260701T000000Z.jsonl"
    _write_rows(expired, ["old"])
    _write_rows(fresh, ["mid"])
    _write_rows(ledger, ["new"])
    files = retained_ledger_files(ledger, retention_days=14, now_utc=_NOW)
    assert files == [fresh, ledger]


def test_read_jsonl_ledger_spans_rotation_no_loss_no_dup(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_rows(ledger, ["a1", "a2"])
    assert maybe_rotate_ledger(ledger, threshold_bytes=1, now_utc=_NOW)["rotated"] is True
    # 輪轉後經 append 入口續寫新主檔(閾值大,不再觸發輪轉)。
    append_jsonl_ledger(ledger, {"attempt_id": "b1"})
    append_jsonl_ledger(ledger, {"attempt_id": "b2"})
    # 跨輪轉讀取:段 + 新主檔,順序保持、不丟行、不重複。
    assert _keys(read_jsonl_ledger(ledger)) == ["a1", "a2", "b1", "b2"]
    # 再轉一次(注入下一秒時間戳),三段視圖仍完整。
    assert (
        maybe_rotate_ledger(
            ledger, threshold_bytes=1, now_utc=_NOW + dt.timedelta(seconds=1)
        )["rotated"]
        is True
    )
    append_jsonl_ledger(ledger, {"attempt_id": "c1"})
    assert _keys(read_jsonl_ledger(ledger)) == ["a1", "a2", "b1", "b2", "c1"]


def test_append_jsonl_ledger_rotates_at_module_threshold(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    monkeypatch.setattr(ledger_rotation, "ROTATE_THRESHOLD_BYTES", 1)
    append_jsonl_ledger(ledger, {"attempt_id": "a1"})  # 建檔(空檔不足閾值)
    append_jsonl_ledger(ledger, {"attempt_id": "a2"})  # 觸發輪轉後寫入新主檔
    segments = rotated_segment_paths(ledger)
    assert len(segments) == 1
    assert _keys(read_jsonl_ledger(ledger)) == ["a1", "a2"]


def test_read_jsonl_ledger_missing_everything_returns_empty(tmp_path: Path) -> None:
    assert read_jsonl_ledger(tmp_path / "probe_ledger.jsonl") == []


def test_read_jsonl_ledger_malformed_row_raises_with_file_and_line(tmp_path: Path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    segment = tmp_path / "probe_ledger.20260701T000000Z.jsonl"
    segment.write_text('{"attempt_id": "ok"}\nnot-json\n', encoding="utf-8")
    _write_rows(ledger, ["a1"])
    try:
        read_jsonl_ledger(ledger)
    except ValueError as exc:
        assert str(segment) in str(exc)
        assert ":2" in str(exc)
    else:
        raise AssertionError("malformed segment row must raise / 段檔壞行必須 fail-loud")
