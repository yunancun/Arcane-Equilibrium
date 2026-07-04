"""Rust/Python plan path 解析 parity 測試（RES-8）。

為什麼需要：Rust writer / soak 圍欄（demo_learning_lane_writer.rs:211-231）與
Python runtime_adapter._default_plan_path 必須對同一組 (OPENCLAW_DATA_DIR,
OPENCLAW_DEMO_LEARNING_LANE_PLAN) 輸入解析出同一 plan 路徑；任一漂移=guard 與
admission 判準漂移（安全洞，2026-07-02 設計 §1.2）。本測把 Rust
path_override_or_default 的 trim/空串語義編成 golden 矩陣，Python 側逐格對齊。
Rust 側同一矩陣由 demo_learning_lane_writer.rs
plan_path_override_trim_and_empty_fallback_golden_vectors 覆蓋。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cost_gate_learning_lane import runtime_adapter


PLAN_ENV = "OPENCLAW_DEMO_LEARNING_LANE_PLAN"
DATA_DIR_ENV = "OPENCLAW_DATA_DIR"
DATA_DIR = "/tmp/openclaw-test-data"
DEFAULT_PATH = Path(DATA_DIR) / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"

# (override_env_value, expected_path)；None = env 未設。
# 與 Rust golden vectors 逐格對齊：空/空白回退默認，非空 trim 後直用。
GOLDEN_CASES = [
    (None, DEFAULT_PATH),
    ("", DEFAULT_PATH),
    ("   ", DEFAULT_PATH),
    ("/custom/plan.json", Path("/custom/plan.json")),
    ("  /custom/plan.json  ", Path("/custom/plan.json")),
]


@pytest.mark.parametrize("override, expected", GOLDEN_CASES)
def test_python_plan_path_matches_rust_golden(monkeypatch, override, expected) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, DATA_DIR)
    if override is None:
        monkeypatch.delenv(PLAN_ENV, raising=False)
    else:
        monkeypatch.setenv(PLAN_ENV, override)
    # 函數內部即時讀 os.environ，monkeypatch 直接生效，無需 reload。
    assert runtime_adapter._default_plan_path() == expected


def test_python_data_dir_default_matches_rust(monkeypatch) -> None:
    # DATA_DIR 未設時兩端都默認 "/tmp/openclaw"（Rust demo_learning_lane_plan_path_from_env
    # 的 unwrap_or_else 慣例）。
    monkeypatch.delenv(PLAN_ENV, raising=False)
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    assert runtime_adapter._default_plan_path() == (
        Path("/tmp/openclaw") / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    )
