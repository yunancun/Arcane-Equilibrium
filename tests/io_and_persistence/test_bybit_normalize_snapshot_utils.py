"""Tests for pure helpers in bybit_normalize_latest_snapshot_to_postgres.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRV_ROOT = Path(__file__).resolve().parents[2]
_SRC = (
    _SRV_ROOT
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "io_and_persistence"
)
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import bybit_normalize_latest_snapshot_to_postgres as ut  # noqa: E402


def test_q_none_returns_null() -> None:
    assert ut.q(None) == "NULL"


def test_q_simple_string_returns_quoted() -> None:
    assert ut.q("hello") == "'hello'"


def test_q_string_with_single_quotes_escaped() -> None:
    assert ut.q("It's okay") == "'It''s okay'"


def test_q_empty_string() -> None:
    assert ut.q("") == "''"


def test_q_numeric_string_is_still_quoted() -> None:
    assert ut.q("12345") == "'12345'"


def test_qb_none_returns_null() -> None:
    assert ut.qb(None) == "NULL"


def test_qb_true_returns_true() -> None:
    assert ut.qb(True) == "TRUE"


def test_qb_false_returns_false() -> None:
    assert ut.qb(False) == "FALSE"


def test_qb_truthy_non_bool() -> None:
    assert ut.qb(1) == "TRUE"
    assert ut.qb("non-empty") == "TRUE"


def test_qb_falsy_non_bool() -> None:
    assert ut.qb(0) == "FALSE"
    assert ut.qb("") == "FALSE"


def _json_from_qj(result: str):
    assert result.startswith("'")
    assert result.endswith("::jsonb")
    json_str = result[1 : -len("::jsonb") - 1]
    return json.loads(json_str.replace("''", "'"))


def test_qj_simple_dict() -> None:
    result = ut.qj({"key": "value"})
    assert _json_from_qj(result) == {"key": "value"}


def test_qj_null_returns_null_jsonb() -> None:
    assert ut.qj(None) == "'null'::jsonb"


def test_qj_empty_list() -> None:
    assert _json_from_qj(ut.qj([])) == []


def test_qj_list_with_items() -> None:
    assert _json_from_qj(ut.qj([1, 2, 3])) == [1, 2, 3]


def test_qj_single_quotes_in_data_escaped() -> None:
    result = ut.qj({"msg": "It's fine"})
    assert "It''s fine" in result
    assert _json_from_qj(result) == {"msg": "It's fine"}
