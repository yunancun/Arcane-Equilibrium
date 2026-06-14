#!/usr/bin/env python3
"""Unit tests for the [90] cost_gate double-cost-deduct delegate wrapper.

MODULE_NOTE:
  PROFIT-1 cost_gate「雙重扣成本」latent issue 預防性哨兵 wrapper 測試。
  鏡像 [80] pg_dump wrapper 測法：monkeypatch sys.modules 注入 fake standalone
  ``check_cost_gate_double_deduct``，驗：
    - 全 PASS collapse 摘要
    - non-PASS env 進 summary（不被吞）
    - WARN-by-default；OPENCLAW_COST_GATE_DOUBLE_DEDUCT_REQUIRED=1 升 FAIL
    - INSUFFICIENT_SAMPLE 透傳（dormant / 缺 config 不製造噪音）
    - import 失敗 / run() 例外 fail-soft（不打掛 runner）
  不碰真 settings/ 或真 PG。
"""

from __future__ import annotations

import os
import sys
import types

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_cost_gate_double_deduct import (  # noqa: E402
    check_90_cost_gate_double_deduct,
)

_MODULE_NAME = "check_cost_gate_double_deduct"
_REQUIRED_ENV = "OPENCLAW_COST_GATE_DOUBLE_DEDUCT_REQUIRED"


def _result(
    verdict: str,
    checks: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Build a minimal standalone cost_gate_double_deduct result packet."""
    return {
        "verdict": verdict,
        "checks": checks
        if checks is not None
        else [{"id": e, "verdict": "PASS"} for e in ("demo", "live", "paper")],
    }


def test_wrapper_collapses_all_pass_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 PASS → PASS + all-PASS 摘要。"""
    monkeypatch.delenv(_REQUIRED_ENV, raising=False)
    fake_mod = types.SimpleNamespace(run=lambda: _result("PASS"))
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "PASS"
    assert "[90] cost_gate_double_deduct verdict=PASS" in msg
    assert "3 env all PASS" in msg


def test_wrapper_surfaces_non_pass_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    """non-PASS env 需進 summary（避免 latent issue 被吞）。"""
    monkeypatch.delenv(_REQUIRED_ENV, raising=False)
    fake_mod = types.SimpleNamespace(
        run=lambda: _result(
            "WARN",
            [
                {"id": "demo", "verdict": "WARN"},
                {"id": "live", "verdict": "WARN"},
                {"id": "paper", "verdict": "PASS"},
            ],
        )
    )
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "WARN"
    assert "demo:WARN" in msg
    assert "live:WARN" in msg


def test_wrapper_warn_escalates_to_fail_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQUIRED=1 時 WARN 升 FAIL（雙重扣成本誤拒 active → fail-closed）。"""
    monkeypatch.setenv(_REQUIRED_ENV, "1")
    fake_mod = types.SimpleNamespace(
        run=lambda: _result("WARN", [{"id": "demo", "verdict": "WARN"}])
    )
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "FAIL"
    assert "verdict=WARN" in msg


def test_wrapper_passes_through_insufficient_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INSUFFICIENT_SAMPLE（dormant / 缺 config）透傳，不製造噪音、不升 FAIL。"""
    monkeypatch.setenv(_REQUIRED_ENV, "1")
    fake_mod = types.SimpleNamespace(
        run=lambda: _result(
            "INSUFFICIENT_SAMPLE",
            [{"id": "demo", "verdict": "INSUFFICIENT_SAMPLE"}],
        )
    )
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "INSUFFICIENT_SAMPLE"
    assert "demo:INSUFFICIENT_SAMPLE" in msg


def test_wrapper_run_exception_warns_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """standalone run() 例外 → 預設 WARN（不打掛 runner）。"""
    monkeypatch.delenv(_REQUIRED_ENV, raising=False)

    def boom() -> dict[str, object]:
        raise RuntimeError("edge json unreadable")

    fake_mod = types.SimpleNamespace(run=boom)
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "WARN"
    assert "standalone run() raised RuntimeError: edge json unreadable" in msg


def test_wrapper_run_exception_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQUIRED=1 時 run() 例外升 FAIL。"""
    monkeypatch.setenv(_REQUIRED_ENV, "1")

    def boom() -> dict[str, object]:
        raise RuntimeError("edge json unreadable")

    fake_mod = types.SimpleNamespace(run=boom)
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "FAIL"
    assert "standalone run() raised RuntimeError" in msg


def test_wrapper_fail_verdict_not_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """standalone FAIL 不被 REQUIRED=0 降級。"""
    monkeypatch.delenv(_REQUIRED_ENV, raising=False)
    fake_mod = types.SimpleNamespace(
        run=lambda: _result("FAIL", [{"id": "live", "verdict": "FAIL"}])
    )
    monkeypatch.setitem(sys.modules, _MODULE_NAME, fake_mod)

    status, msg = check_90_cost_gate_double_deduct()

    assert status == "FAIL"
    assert "live:FAIL" in msg
