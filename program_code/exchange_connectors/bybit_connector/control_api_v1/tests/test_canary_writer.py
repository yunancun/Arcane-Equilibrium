"""REF-20 Wave 4 R20-P2b-T3 — CanaryArtifactWriter unit tests.
REF-20 Wave 4 R20-P2b-T3 — CanaryArtifactWriter 單元測試。

MODULE_NOTE (EN):
    Hermetic 4-case suite covering Wave 4 R20-P2b-T3 canary/diagnostic
    artifact writer:

      Case 1: write_replay_artifact writes JSON to filesystem + returns
              WriteResult with correct artifact_id / path / byte_size.
      Case 2: register_artifact_in_db with V046 absent → no-op (returns False).
      Case 3: write + register two-phase happy path with mock cursor.
      Case 4: artifact_type validation rejects out-of-allowlist values.

    Tests use tempfile / monkeypatch to redirect filesystem writes to
    pytest-managed temp dirs (no pollution of real OPENCLAW_DATA_DIR).

MODULE_NOTE (中):
    封閉式 4-case 測試套件，覆蓋 Wave 4 R20-P2b-T3 canary/diagnostic
    artifact 寫手：

    Tests 用 tempfile / monkeypatch 把 filesystem 寫導入 pytest 管理的
    暫存目錄（不污染真實 OPENCLAW_DATA_DIR）。

SPEC: REF-20 V3 §11 P2b deliverables (canary/diagnostic artifacts
      registered Linux only) + §12 #7 (replay_registry_fk_contract)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 4 R20-P2b-T3
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.canary_writer import (  # noqa: E402
    ALLOWED_ARTIFACT_TYPES,
    ARTIFACT_TYPE_CANARY,
    ARTIFACT_TYPE_DIAGNOSTIC,
    CanaryArtifactWriter,
    WriteResult,
)


@pytest.fixture
def _tmp_data_dir(tmp_path, monkeypatch):
    """Redirect OPENCLAW_DATA_DIR to a pytest tmp_path for hermetic writes.
    把 OPENCLAW_DATA_DIR 重導到 pytest tmp_path 供封閉式寫入。
    """
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNTIME_ENV", "linux_trade_core")
    yield tmp_path


def test_write_replay_artifact_creates_json_file(_tmp_data_dir) -> None:
    """Case 1: write_replay_artifact writes JSON + returns metadata.
    Case 1：write_replay_artifact 寫 JSON + 回 metadata。
    """
    writer = CanaryArtifactWriter(runtime_environment="linux_trade_core")
    run_id = uuid.uuid4().hex
    payload = {"k": "v", "fills": [1, 2, 3]}

    result = writer.write_replay_artifact(
        run_id=run_id,
        artifact_type=ARTIFACT_TYPE_CANARY,
        payload=payload,
    )

    assert isinstance(result, WriteResult)
    assert result.artifact_id  # UUID hex non-empty
    assert result.is_mock is False  # linux_trade_core
    assert result.byte_size > 0

    # File should be JSON-readable and round-trip the payload.
    # 檔應為可讀 JSON 並能 round-trip payload。
    artifact_path = Path(result.artifact_path)
    assert artifact_path.is_file()
    with open(artifact_path) as f:
        loaded = json.load(f)
    assert loaded == payload


def test_register_artifact_in_db_with_v046_absent_returns_false(
    _tmp_data_dir,
) -> None:
    """Case 2: register_artifact_in_db with V046 absent → no-op (False).
    Case 2：register_artifact_in_db + V046 缺 → no-op（False）。
    """
    writer = CanaryArtifactWriter(runtime_environment="linux_trade_core")

    # Mock cursor that reports table absent.
    # mock cursor 回報 table 缺。
    mock_cursor = MagicMock()
    # First execute() → information_schema probe; fetchone() returns None.
    # 第一次 execute() → information_schema probe；fetchone() 回 None。
    mock_cursor.fetchone.return_value = None

    run_id = uuid.uuid4().hex
    write_result = WriteResult(
        artifact_id=uuid.uuid4().hex,
        artifact_path="/tmp/test.json",
        byte_size=100,
        is_mock=False,
    )

    ok = writer.register_artifact_in_db(
        cur=mock_cursor,
        run_id=run_id,
        write_result=write_result,
        artifact_type=ARTIFACT_TYPE_DIAGNOSTIC,
    )
    assert ok is False
    # Verify only the schema-probe SELECT was issued (no INSERT).
    # 確認只發了 schema-probe SELECT（無 INSERT）。
    sql_calls = [c.args[0] for c in mock_cursor.execute.call_args_list]
    assert any("information_schema" in s for s in sql_calls)
    assert not any("INSERT" in s for s in sql_calls)


def test_register_artifact_two_phase_happy_path(_tmp_data_dir) -> None:
    """Case 3: write + register two-phase happy path with mock cursor.
    Case 3：write + register 兩階段成功路徑（mock cursor）。
    """
    writer = CanaryArtifactWriter(runtime_environment="linux_trade_core")
    run_id = uuid.uuid4().hex

    # Phase 1: write payload to filesystem.
    # 階段 1：寫 payload 到 filesystem。
    payload = {"baseline_pnl": 12.5, "candidate_pnl": 14.2}
    result = writer.write_replay_artifact(
        run_id=run_id,
        artifact_type="baseline_compare",
        payload=payload,
    )
    assert Path(result.artifact_path).is_file()

    # Phase 2: register in DB. Mock cursor: schema present + INSERT returns row.
    # 階段 2：DB register。mock cursor：schema 存在 + INSERT 回 row。
    mock_cursor = MagicMock()
    # Sequence of fetchone() returns:
    # 1. information_schema probe → (1,) (table exists)
    # 2. INSERT ... RETURNING → (artifact_id_str,)
    mock_cursor.fetchone.side_effect = [
        (1,),
        (result.artifact_id,),
    ]

    ok = writer.register_artifact_in_db(
        cur=mock_cursor,
        run_id=run_id,
        write_result=result,
        artifact_type="baseline_compare",
    )
    assert ok is True
    # 2 execute() calls: 1 probe + 1 INSERT.
    # 2 次 execute()：1 probe + 1 INSERT。
    assert mock_cursor.execute.call_count == 2
    sql_calls = [c.args[0] for c in mock_cursor.execute.call_args_list]
    assert "INSERT INTO replay.report_artifacts" in sql_calls[1]


def test_artifact_type_validation_rejects_unknown(_tmp_data_dir) -> None:
    """Case 4: Unknown artifact_type raises ValueError on write + register.
    Case 4：未知 artifact_type 在 write + register 時 raise ValueError。
    """
    writer = CanaryArtifactWriter(runtime_environment="linux_trade_core")
    run_id = uuid.uuid4().hex

    # Write phase rejects.
    # write 階段拒絕。
    with pytest.raises(ValueError, match="not in allowlist"):
        writer.write_replay_artifact(
            run_id=run_id,
            artifact_type="not_a_real_type",
            payload={},
        )

    # Register phase also rejects (defensive).
    # register 階段也拒絕（defensive）。
    fake_result = WriteResult(
        artifact_id=uuid.uuid4().hex,
        artifact_path="/tmp/x.json",
        byte_size=10,
        is_mock=False,
    )
    mock_cursor = MagicMock()
    with pytest.raises(ValueError, match="not in allowlist"):
        writer.register_artifact_in_db(
            cur=mock_cursor,
            run_id=run_id,
            write_result=fake_result,
            artifact_type="bogus",
        )


def test_mac_runtime_writes_to_test_only_dir(monkeypatch, tmp_path) -> None:
    """Bonus: Mac runtime_environment routes writes to /tmp test-only dir +
    is_mock=True flag.
    額外：Mac runtime_environment 把寫入導到 /tmp test-only 目錄 + is_mock=True。
    """
    # Force Mac path resolution.
    # 強制 Mac 路徑解析。
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNTIME_ENV", "mac_dev_smoke_test_only")
    writer = CanaryArtifactWriter()
    assert writer.runtime_environment == "mac_dev_smoke_test_only"
    assert writer.is_mock_environment is True
    assert "/tmp/replay_artifacts_test_only" in str(writer.root_dir)


def test_allowed_artifact_types_match_v046_check_constraint() -> None:
    """Sanity: ALLOWED_ARTIFACT_TYPES matches V046 CHECK chk_replay_report_artifacts_type.
    健全性：ALLOWED_ARTIFACT_TYPES 對齊 V046 CHECK chk_replay_report_artifacts_type。
    """
    expected = {
        "canary",
        "diagnostic",
        "pnl_summary",
        "fill_log",
        "baseline_compare",
    }
    assert ALLOWED_ARTIFACT_TYPES == frozenset(expected)
