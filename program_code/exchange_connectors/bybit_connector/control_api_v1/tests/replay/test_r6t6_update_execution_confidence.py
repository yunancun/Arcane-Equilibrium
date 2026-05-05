"""REF-20 Sprint C R6-T6 — update_execution_confidence helper unit test。

由 PM 直接寫（per operator「W4 PM 直接寫」decision），跳 E1 dispatch。
驗 V049 execution_confidence column UPDATE 的 4 case：
  1. label='calibrated' → UPDATE 成功 + return True
  2. label='limited' → UPDATE 成功 + return True
  3. label invalid (e.g. 'high') → ValueError raise + 0 SQL execute
  4. row not found (rowcount=0) → return False
"""
from unittest.mock import MagicMock

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (
    update_execution_confidence,
    V049_EXECUTION_CONFIDENCE_ALLOWED,
)


def test_update_execution_confidence_calibrated_label():
    """R6-T6 case 1: label='calibrated' UPDATE V049 row 成功。"""
    cur = MagicMock()
    cur.rowcount = 1
    result = update_execution_confidence(
        cur,
        experiment_id="11111111-1111-1111-1111-111111111111",
        label="calibrated",
    )
    assert result is True
    cur.execute.assert_called_once()
    sql_arg = cur.execute.call_args.args[0]
    assert "UPDATE replay.experiments" in sql_arg
    assert "execution_confidence" in sql_arg
    params = cur.execute.call_args.args[1]
    assert params[0] == "calibrated"


def test_update_execution_confidence_limited_label():
    """R6-T6 case 2: label='limited' UPDATE V049 row 成功。"""
    cur = MagicMock()
    cur.rowcount = 1
    result = update_execution_confidence(
        cur,
        experiment_id="11111111-1111-1111-1111-111111111111",
        label="limited",
    )
    assert result is True


def test_update_execution_confidence_invalid_label_raises_valueerror():
    """R6-T6 case 3: label 不在 V049 CHECK enum allowlist → ValueError + 0 SQL execute。"""
    cur = MagicMock()
    with pytest.raises(ValueError, match="不在 V049 CHECK enum allowlist"):
        update_execution_confidence(
            cur,
            experiment_id="11111111-1111-1111-1111-111111111111",
            label="high",  # 不存在的 label
        )
    cur.execute.assert_not_called()  # fail-closed: 0 SQL


def test_update_execution_confidence_row_not_found_returns_false():
    """R6-T6 case 4: experiment_id not match → rowcount=0 → return False。"""
    cur = MagicMock()
    cur.rowcount = 0
    result = update_execution_confidence(
        cur,
        experiment_id="22222222-2222-2222-2222-222222222222",
        label="calibrated",
    )
    assert result is False


def test_v049_execution_confidence_allowed_set():
    """R6-T6 invariant: V049 CHECK enum allowlist 含 3 個 label。"""
    assert V049_EXECUTION_CONFIDENCE_ALLOWED == frozenset({"none", "limited", "calibrated"})
