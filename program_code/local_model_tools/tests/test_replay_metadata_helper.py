"""REF-20 Sprint C2 R7 W1 — replay_metadata_helper 單元測試。

測試範圍：
  - test_build_replay_metadata_calibrated_label：CALIBRATED label →
    回 4-tuple，tier='calibrated_replay'，TTL=7d。
  - test_build_replay_metadata_limited_label_3d_ttl：LIMITED label →
    tier='calibrated_replay'，TTL=3d。
  - test_build_replay_metadata_none_label_returns_none：NONE label →
    回 None，0 SQL execute。
  - test_build_replay_metadata_v049_row_missing_returns_none：V049 row
    不存在 → log warn + 回 None。
  - test_build_replay_metadata_manifest_hash_null_returns_none：V049 row
    存在但 manifest_hash NULL → 回 None（advisory failure）。

Mode：
  - 純 Mac dev mock test（無 PG dependency）。
  - 模擬 cur.execute / cur.fetchone 行為。

CLAUDE.md §七 governance（2026-05-05 中文 default）：MODULE_NOTE +
docstring 全中文。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (
    CalibrationResult,
    ExecutionConfidence,
)
from program_code.local_model_tools.replay_metadata_helper import (
    build_replay_metadata,
)


def _make_calibration_result(
    label: ExecutionConfidence,
    *,
    ttl: timedelta,
    sample_count: int = 200,
) -> CalibrationResult:
    """構造測試用 CalibrationResult。"""
    return CalibrationResult(
        label=label,
        sample_count=sample_count,
        last_fill_age_ms=12_345,
        fee_bps_mad=2.0,
        fee_bps_iqr=5.0,
        net_bps_p5=-3.0,
        net_bps_p50=0.5,
        net_bps_p95=4.0,
        ttl=ttl,
    )


def _make_mock_cur_with_row(manifest_hash_bytes: bytes | None) -> MagicMock:
    """構造模擬 cursor，fetchone 回 (manifest_hash,)。"""
    cur = MagicMock()
    if manifest_hash_bytes is None:
        cur.fetchone.return_value = (None,)  # manifest_hash NULL
    else:
        cur.fetchone.return_value = (manifest_hash_bytes,)
    return cur


def _make_mock_cur_no_row() -> MagicMock:
    """構造模擬 cursor，fetchone 回 None（V049 row 不存在）。"""
    cur = MagicMock()
    cur.fetchone.return_value = None
    return cur


def test_build_replay_metadata_calibrated_label():
    """CALIBRATED label + 7d TTL → 回 4-tuple，tier='calibrated_replay'。"""
    cal = _make_calibration_result(
        ExecutionConfidence.CALIBRATED, ttl=timedelta(days=7), sample_count=1162,
    )
    fake_hash = bytes.fromhex("aa" * 32)  # 32 byte sha256 digest
    cur = _make_mock_cur_with_row(fake_hash)
    exp_id = "00000000-0000-0000-0000-000000000001"

    result = build_replay_metadata(
        experiment_id=exp_id, calibration_result=cal, cur=cur,
    )

    assert result is not None
    tier, replay_exp_id, hash_hex, expires_at = result
    assert tier == "calibrated_replay"
    assert replay_exp_id == exp_id
    assert hash_hex == "aa" * 32
    # expires_at 應在 (now, now+7d+1s) 範圍
    now = datetime.now(timezone.utc)
    assert now < expires_at <= now + timedelta(days=7, seconds=2)
    # SELECT V049 確認執行
    cur.execute.assert_called_once()


def test_build_replay_metadata_limited_label_3d_ttl():
    """LIMITED label + 3d TTL → tier='calibrated_replay' (兩 label 共用)，
    TTL=3d。"""
    cal = _make_calibration_result(
        ExecutionConfidence.LIMITED, ttl=timedelta(days=3), sample_count=99,
    )
    fake_hash = bytes.fromhex("bb" * 32)
    cur = _make_mock_cur_with_row(fake_hash)
    exp_id = "00000000-0000-0000-0000-000000000002"

    result = build_replay_metadata(
        experiment_id=exp_id, calibration_result=cal, cur=cur,
    )

    assert result is not None
    tier, replay_exp_id, hash_hex, expires_at = result
    assert tier == "calibrated_replay"  # 與 CALIBRATED 共用 tier
    assert replay_exp_id == exp_id
    assert hash_hex == "bb" * 32
    # TTL=3d
    now = datetime.now(timezone.utc)
    assert timedelta(days=2, hours=23) < (expires_at - now) <= timedelta(days=3, seconds=2)


def test_build_replay_metadata_none_label_returns_none():
    """NONE label → 回 None，0 SQL execute（短路）。"""
    cal = _make_calibration_result(
        ExecutionConfidence.NONE, ttl=timedelta(0), sample_count=0,
    )
    cur = MagicMock()  # 不該被 .execute 呼叫
    exp_id = "00000000-0000-0000-0000-000000000003"

    result = build_replay_metadata(
        experiment_id=exp_id, calibration_result=cal, cur=cur,
    )

    assert result is None
    cur.execute.assert_not_called()  # 短路；不 SELECT V049


def test_build_replay_metadata_v049_row_missing_returns_none(caplog):
    """V049 row 不存在 → log warn + 回 None（advisory failure）。"""
    cal = _make_calibration_result(
        ExecutionConfidence.CALIBRATED, ttl=timedelta(days=7),
    )
    cur = _make_mock_cur_no_row()
    exp_id = "00000000-0000-0000-0000-000000000004"

    with caplog.at_level("WARNING"):
        result = build_replay_metadata(
            experiment_id=exp_id, calibration_result=cal, cur=cur,
        )

    assert result is None
    assert any("不在 V049" in rec.message for rec in caplog.records)


def test_build_replay_metadata_manifest_hash_null_returns_none(caplog):
    """V049 row 存在但 manifest_hash NULL → log warn + 回 None。"""
    cal = _make_calibration_result(
        ExecutionConfidence.CALIBRATED, ttl=timedelta(days=7),
    )
    cur = _make_mock_cur_with_row(None)  # manifest_hash NULL
    exp_id = "00000000-0000-0000-0000-000000000005"

    with caplog.at_level("WARNING"):
        result = build_replay_metadata(
            experiment_id=exp_id, calibration_result=cal, cur=cur,
        )

    assert result is None
    assert any("manifest_hash NULL" in rec.message for rec in caplog.records)


def test_build_replay_metadata_returns_correct_hex_format():
    """manifest_hash 必為 64-char hex string（32 byte sha256）。"""
    cal = _make_calibration_result(
        ExecutionConfidence.CALIBRATED, ttl=timedelta(days=7),
    )
    fake_hash = bytes.fromhex("0123456789abcdef" * 4)  # 32 byte
    cur = _make_mock_cur_with_row(fake_hash)
    exp_id = "00000000-0000-0000-0000-000000000006"

    result = build_replay_metadata(
        experiment_id=exp_id, calibration_result=cal, cur=cur,
    )

    assert result is not None
    _, _, hash_hex, _ = result
    assert len(hash_hex) == 64
    assert hash_hex == "0123456789abcdef" * 4
    # Hex 字串可逆解碼
    assert bytes.fromhex(hash_hex) == fake_hash


def test_build_replay_metadata_memoryview_manifest_hash():
    """psycopg2 BYTEA 在某些 driver 版本回 memoryview；helper 應接受並 hex
    編碼。"""
    cal = _make_calibration_result(
        ExecutionConfidence.CALIBRATED, ttl=timedelta(days=7),
    )
    fake_hash = bytes.fromhex("ff" * 32)
    cur = _make_mock_cur_with_row(memoryview(fake_hash))
    exp_id = "00000000-0000-0000-0000-000000000007"

    result = build_replay_metadata(
        experiment_id=exp_id, calibration_result=cal, cur=cur,
    )

    assert result is not None
    _, _, hash_hex, _ = result
    assert hash_hex == "ff" * 32
