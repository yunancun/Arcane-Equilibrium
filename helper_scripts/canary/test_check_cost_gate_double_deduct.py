#!/usr/bin/env python3
"""Unit tests for the standalone cost_gate double-cost-deduct sentinel.

MODULE_NOTE:
  PROFIT-1 cost_gate「雙重扣成本」latent issue 預防性哨兵的 standalone 測試。
  本檔只測純函數 / tmp_path 邊界：
    - per-cell 門檻公式與 gates.rs 對齊
      （threshold = fee_bps / clamp(cell.win_rate, floor, 1.0) × safety_multiplier）。
    - per-cell win_rate weighting 真實生效（同 runtime_bps、不同 win_rate →
      門檻不同 → 一命中一放行，鎖 HIGH-1 回歸）。
    - scan 謂詞（validation_passed / runtime_bps>0 / runtime_bps<per-cell threshold）。
    - fail-soft：缺 config / 缺 cell / 解析失敗 → INSUFFICIENT_SAMPLE（SKIP）非 FAIL。
    - mutation bite：把任一謂詞翻掉 → cell 不再命中（證 gate 不誤報）。
  全程 tmp_path，不碰真 settings/edge_estimates.json 或真 risk_config TOML。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_HEALTHCHECKS_DIR = _THIS_DIR / "healthchecks"
sys.path.insert(0, str(_HEALTHCHECKS_DIR))

import check_cost_gate_double_deduct as cgdd  # noqa: E402

# py3.10 無 stdlib tomllib 且 tomli 未裝時，受測模組 fail-soft 為 tomllib=None，
# run() 端到端斷言會失真 → 整檔明確 skip（取代先前的 collection error）。
if cgdd.tomllib is None:  # pragma: no cover
    pytest.skip("tomllib/tomli 皆不可用（py3.10 需安裝 tomli）", allow_module_level=True)


# ───────────────────────────────────────────────────────────────────────────
# fixtures：tmp srv root + risk_config + edge_estimates
# ───────────────────────────────────────────────────────────────────────────


def _risk_cfg(
    *,
    max_taker_fee_bps: float = 8.0,
    default_rate: float = 0.0005,
    win_rate_floor: float = 0.3,
    safety_multiplier: float = 1.3,
) -> dict:
    return {
        "market_gate": {"max_taker_fee_bps": max_taker_fee_bps},
        "slippage": {
            "default_rate": default_rate,
            "cost_gate_win_rate_floor": win_rate_floor,
            "cost_gate_safety_multiplier": safety_multiplier,
        },
    }


def _write_srv(
    tmp_path: Path,
    *,
    edge_estimates: dict | None,
    risk_cfgs: dict[str, dict] | None = None,
) -> Path:
    """寫一個最小 srv tree（settings/edge_estimates.json + 三 env TOML）。"""
    settings = tmp_path / "settings"
    rules = settings / "risk_control_rules"
    rules.mkdir(parents=True)
    if edge_estimates is not None:
        (settings / "edge_estimates.json").write_text(
            json.dumps(edge_estimates), encoding="utf-8"
        )
    cfgs = risk_cfgs if risk_cfgs is not None else {e: _risk_cfg() for e in cgdd.ENVIRONMENTS}
    for env, cfg in cfgs.items():
        (rules / f"risk_config_{env}.toml").write_text(
            _to_toml(cfg), encoding="utf-8"
        )
    return tmp_path


def _to_toml(cfg: dict) -> str:
    """極簡 dict → TOML（只支援本測試需要的兩段純數值結構，避免新依賴）。"""
    lines: list[str] = []
    for section, body in cfg.items():
        lines.append(f"[{section}]")
        for k, v in body.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────────
# gate params + per-cell 門檻公式（與 gates.rs 對齊）
# ───────────────────────────────────────────────────────────────────────────


def test_compute_gate_params_fee_bps() -> None:
    """demo 參數：fee_bps = 2×(8/1e4 + 0.0005)×1e4 = 2×(0.0008+0.0005)×1e4 = 26.0。"""
    cfg = _risk_cfg(max_taker_fee_bps=8.0, default_rate=0.0005)
    gate = cgdd.compute_gate_params(cfg)
    assert gate is not None
    fee_bps = 2.0 * (8.0 / 1e4 + 0.0005) * 1e4
    assert abs(gate.fee_bps - fee_bps) < 1e-9
    assert abs(gate.fee_bps - 26.0) < 1e-6
    assert gate.win_rate_floor == 0.3
    assert gate.safety_multiplier == 1.3


def test_cell_threshold_clamps_win_rate_below_floor() -> None:
    """cell.win_rate < floor → clamp 到 floor → threshold = fee_bps/floor×safety。
    fee_bps=26.0, floor=0.3, safety=1.3 → 26.0/0.3×1.3 = 112.666…bps。"""
    gate = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=8.0, default_rate=0.0005))
    assert gate is not None
    # win_rate=0.1 < floor 0.3 → 用 floor。
    assert abs(gate.cell_threshold_bps(0.1) - (26.0 / 0.3 * 1.3)) < 1e-6
    # win_rate=0.0（缺欄 fallback 後不可能，但邊界）→ 仍 clamp 到 floor。
    assert abs(gate.cell_threshold_bps(0.0) - (26.0 / 0.3 * 1.3)) < 1e-6


def test_cell_threshold_uses_win_rate_above_floor() -> None:
    """cell.win_rate >= floor → 用 cell.win_rate（非 floor）→ 門檻較低。
    win_rate=0.55 → 26.0/0.55×1.3 = 61.45…bps（< floor-based 112.67）。"""
    gate = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=8.0, default_rate=0.0005))
    assert gate is not None
    expected = 26.0 / 0.55 * 1.3
    assert abs(gate.cell_threshold_bps(0.55) - expected) < 1e-6
    # 與 gate.rs 同向：win_rate 越高門檻越低。
    assert gate.cell_threshold_bps(0.55) < gate.cell_threshold_bps(0.3)
    # win_rate=1.0 → clamp 上界 → threshold = fee_bps×safety。
    assert abs(gate.cell_threshold_bps(1.0) - (26.0 * 1.3)) < 1e-6


def test_compute_gate_params_per_env_differs() -> None:
    """三環境 max_taker_fee_bps 不同（demo 8 / live 7 / paper 12）→ fee_bps 不同。"""
    demo = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=8.0))
    live = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=7.0))
    paper = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=12.0))
    assert live.fee_bps < demo.fee_bps < paper.fee_bps


def test_compute_gate_params_missing_section_returns_none() -> None:
    """缺 [market_gate] 或 [slippage] → None（caller 判 INSUFFICIENT_SAMPLE）。"""
    assert cgdd.compute_gate_params({"slippage": {}}) is None
    assert cgdd.compute_gate_params({"market_gate": {}}) is None


def test_compute_gate_params_zero_win_rate_floor_returns_none() -> None:
    """win_rate_floor<=0 會除零 → None（fail-soft，不 crash）。"""
    cfg = _risk_cfg(win_rate_floor=0.0)
    assert cgdd.compute_gate_params(cfg) is None


def test_compute_gate_params_bool_field_rejected() -> None:
    """TOML 數值欄位若被寫成 bool（True）必須被拒（bool 是 int 子類陷阱）。"""
    cfg = _risk_cfg()
    cfg["slippage"]["default_rate"] = True  # type: ignore[assignment]
    assert cgdd.compute_gate_params(cfg) is None


# ───────────────────────────────────────────────────────────────────────────
# scan：謂詞 + per-cell win_rate weighting
# ───────────────────────────────────────────────────────────────────────────


def _gate() -> cgdd.GateParams:
    """測試用 gate params：fee_bps=26.0, floor=0.3, safety=1.3。
    win_rate<=floor → floor-threshold=112.666…bps；win_rate=0.5 → 67.6bps。"""
    gate = cgdd.compute_gate_params(_risk_cfg(max_taker_fee_bps=8.0, default_rate=0.0005))
    assert gate is not None
    return gate


def test_scan_hits_validated_positive_below_threshold() -> None:
    """validation_passed AND runtime_bps>0 AND runtime_bps<per-cell threshold → 命中。"""
    edge = {
        "grid::BTCUSDT": {
            "runtime_bps": 5.0,
            "validation_passed": True,
            "win_rate": 0.5,
            "n": 50,
        }
    }
    hits = cgdd.scan_double_deduct_cells(edge, _gate())
    assert len(hits) == 1
    assert hits[0]["cell"] == "grid::BTCUSDT"
    assert hits[0]["runtime_bps"] == 5.0
    assert hits[0]["win_rate"] == 0.5


def test_scan_per_cell_win_rate_weighting_one_hits_one_passes() -> None:
    """HIGH-1 回歸鎖：兩 cell 同 runtime_bps=60.0，win_rate 不同 → 門檻不同。

    fee_bps=26.0, safety=1.3：
      - low_wr win_rate=0.3 → threshold = 26/0.3×1.3 = 112.67 → 60<112.67 命中。
      - high_wr win_rate=0.6 → threshold = 26/0.6×1.3 = 56.33 → 60>=56.33 放行。
    若門檻仍用固定 floor（HIGH-1 bug）兩者都會命中 → 本斷言會紅。
    """
    edge = {
        "low_wr::SYM": {"runtime_bps": 60.0, "validation_passed": True, "win_rate": 0.3, "n": 50},
        "high_wr::SYM": {"runtime_bps": 60.0, "validation_passed": True, "win_rate": 0.6, "n": 50},
    }
    hits = cgdd.scan_double_deduct_cells(edge, _gate())
    hit_cells = {h["cell"] for h in hits}
    assert hit_cells == {"low_wr::SYM"}, (
        "per-cell win_rate weighting 失效：high-win_rate cell 不應命中"
        "（gate 會放行），只有 low-win_rate cell 命中"
    )


def test_scan_win_rate_shrunk_takes_precedence() -> None:
    """win_rate_shrunk 優先於 win_rate（與 edge_estimates.rs L163-165 一致）。
    win_rate_shrunk=0.6 → threshold=56.33 → runtime 60>=56.33 放行（即使 win_rate=0.3）。"""
    edge = {
        "s::SYM": {
            "runtime_bps": 60.0,
            "validation_passed": True,
            "win_rate_shrunk": 0.6,
            "win_rate": 0.3,
            "n": 50,
        }
    }
    assert cgdd.scan_double_deduct_cells(edge, _gate()) == []


def test_scan_missing_win_rate_defaults_to_half() -> None:
    """缺 win_rate 欄 → fallback 0.5（與 edge_estimates.rs unwrap_or(0.5) 一致）。
    win_rate=0.5 → threshold=67.6 → runtime 60<67.6 命中、win_rate 記 0.5。"""
    edge = {"s::SYM": {"runtime_bps": 60.0, "validation_passed": True, "n": 50}}
    hits = cgdd.scan_double_deduct_cells(edge, _gate())
    assert len(hits) == 1
    assert hits[0]["win_rate"] == 0.5


def test_scan_bite_unvalidated_not_hit() -> None:
    """mutation bite：validation_passed=false → 不命中（dormant 條件未滿足）。"""
    edge = {"s::SYM": {"runtime_bps": 5.0, "validation_passed": False, "n": 50}}
    assert cgdd.scan_double_deduct_cells(edge, _gate()) == []


def test_scan_bite_nonpositive_runtime_not_hit() -> None:
    """mutation bite：runtime_bps<=0 → 不命中（負/零 edge 本就該被 gate 處理）。"""
    edge = {
        "neg::SYM": {"runtime_bps": -1.0, "validation_passed": True, "n": 50},
        "zero::SYM": {"runtime_bps": 0.0, "validation_passed": True, "n": 50},
    }
    assert cgdd.scan_double_deduct_cells(edge, _gate()) == []


def test_scan_bite_above_threshold_not_hit() -> None:
    """mutation bite：runtime_bps>=threshold → 不命中（gate 本就會放行，無誤拒）。"""
    edge = {"big::SYM": {"runtime_bps": 200.0, "validation_passed": True, "n": 50}}
    assert cgdd.scan_double_deduct_cells(edge, _gate()) == []


def test_scan_runtime_bps_falls_back_to_shrunk_bps() -> None:
    """無 runtime_bps key 時 fallback shrunk_bps（與 edge_estimates.rs 一致）。"""
    edge = {"legacy::SYM": {"shrunk_bps": 5.0, "validation_passed": True, "n": 50}}
    hits = cgdd.scan_double_deduct_cells(edge, _gate())
    assert len(hits) == 1
    assert hits[0]["runtime_bps"] == 5.0


def test_scan_skips_meta_and_nonobject() -> None:
    """_meta 與非 object value 跳過，不誤判（與 rs 只解析 object cell 對齊）。"""
    edge = {
        "_meta": {"updated_at": "2026-06-14T00:00:00Z", "n_cells": 1},
        "bad::SYM": "not-an-object",
        "good::SYM": {"runtime_bps": 5.0, "validation_passed": True, "n": 50},
    }
    hits = cgdd.scan_double_deduct_cells(edge, _gate())
    assert len(hits) == 1
    assert hits[0]["cell"] == "good::SYM"


# ───────────────────────────────────────────────────────────────────────────
# run()：端到端（tmp srv tree + OPENCLAW_BASE_DIR）
# ───────────────────────────────────────────────────────────────────────────


def test_run_pass_when_no_double_deduct_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validated-positive 但高於 threshold（200bps）→ 三 env 全 PASS。"""
    edge = {"s::SYM": {"runtime_bps": 200.0, "validation_passed": True, "n": 50}}
    root = _write_srv(tmp_path, edge_estimates=edge)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(root))
    result = cgdd.run()
    assert result["verdict"] == cgdd.VERDICT_PASS
    assert len(result["checks"]) == 3


def test_run_warns_when_double_deduct_cell_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validated-positive 5bps < threshold → 三 env 全 WARN（整體 WARN）。"""
    edge = {"grid::BTCUSDT": {"runtime_bps": 5.0, "validation_passed": True, "n": 50}}
    root = _write_srv(tmp_path, edge_estimates=edge)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(root))
    result = cgdd.run()
    assert result["verdict"] == cgdd.VERDICT_WARN
    warn_notes = [c for c in result["checks"] if c["verdict"] == cgdd.VERDICT_WARN]
    assert len(warn_notes) == 3
    assert "grid::BTCUSDT" in warn_notes[0]["note"]


def test_run_insufficient_sample_when_edge_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """edge_estimates.json 缺 → INSUFFICIENT_SAMPLE（SKIP）非 FAIL（fail-soft）。"""
    root = _write_srv(tmp_path, edge_estimates=None)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(root))
    result = cgdd.run()
    assert result["verdict"] == cgdd.VERDICT_INSUFFICIENT_SAMPLE


def test_run_insufficient_sample_when_risk_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """risk_config TOML 全缺 → INSUFFICIENT_SAMPLE（SKIP）非 FAIL。"""
    settings = tmp_path / "settings"
    (settings / "risk_control_rules").mkdir(parents=True)
    (settings / "edge_estimates.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    result = cgdd.run()
    assert result["verdict"] == cgdd.VERDICT_INSUFFICIENT_SAMPLE


def test_run_empty_edge_estimates_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """edge_estimates.json 為空 object（只 _meta 或全空）→ 0 cell → PASS。"""
    edge = {"_meta": {"updated_at": "2026-06-14T00:00:00Z", "n_cells": 0}}
    root = _write_srv(tmp_path, edge_estimates=edge)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(root))
    result = cgdd.run()
    assert result["verdict"] == cgdd.VERDICT_PASS
