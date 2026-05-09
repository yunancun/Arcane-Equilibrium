from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import json_fast  # noqa: E402


def test_dumps_line_bytes_compact_raw_utf8_round_trip() -> None:
    payload = {"jsonrpc": "2.0", "params": {"intent_id": "测试", "n": 1}}

    line = json_fast.dumps_line_bytes(payload)

    assert line.endswith(b"\n")
    assert b" " not in line
    assert "\\u" not in line.decode("utf-8")
    assert json_fast.loads(line.strip()) == payload


def test_dumps_preserves_stdlib_ensure_ascii_default() -> None:
    assert json_fast.dumps({"x": "测试"}) == '{"x": "\\u6d4b\\u8bd5"}'


def test_dumps_bytes_supports_default_str_and_sorted_compact() -> None:
    class Custom:
        def __str__(self) -> str:
            return "custom-value"

    encoded = json_fast.dumps_bytes(
        {"b": Custom(), "a": 1},
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert encoded == b'{"a":1,"b":"custom-value"}'
