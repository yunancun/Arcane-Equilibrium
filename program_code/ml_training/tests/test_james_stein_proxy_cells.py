"""Tests for james_stein_estimator sync-label proxy cell injection (P0-14 Option B).
james_stein_estimator sync-label 代理格子注入測試（P0-14 Option B）。

Covers the P0-14 RCA fix: edge_estimates.json must include proxy cells for
runtime sync-label owner_strategy values (bybit_sync, orphan_adopted,
orphan_frozen, dust_frozen) so the Rust cost_gate Gate 1 lookup does not
silently miss and force phys_lock Hold.
覆蓋 P0-14 RCA 修復：edge_estimates.json 必須包含 sync-label owner_strategy
的代理格子，避免 Rust cost_gate Gate 1 靜默 miss 而強制 phys_lock Hold。
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from program_code.ml_training import james_stein_estimator as jse
from program_code.ml_training.james_stein_estimator import (
    SYNC_LABEL_STRATEGIES,
    _inject_sync_label_proxy_cells,
    _write_json_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures / 測試夾具
# ---------------------------------------------------------------------------

def _make_results(pairs: list[tuple[str, str]], grand_mean_bps: float = 1.2345):
    """Build a results dict in the shape run_james_stein produces, keyed by
    (strategy, symbol) tuples. Every cell shares the same grand_mean_bps.
    構造 run_james_stein 形狀的結果字典，每格共享 grand_mean_bps。"""
    results: dict[tuple[str, str], dict] = {}
    for strat, sym in pairs:
        results[(strat, sym)] = {
            "strategy_name": strat,
            "symbol": sym,
            "raw_bps": grand_mean_bps,
            "shrunk_bps": grand_mean_bps,
            "grand_mean_bps": grand_mean_bps,
            "shrinkage_factor_B": 0.5,
            "n_observations": 10,
            "win_rate": 0.55,
            "avg_win_bps": 20.0,
            "avg_loss_bps": -15.0,
            "win_rate_shrunk": 0.55,
            "avg_win_bps_shrunk": 20.0,
            "avg_loss_bps_shrunk": -15.0,
            "combined_ev_bps": 1.25,
        }
    return results


# ---------------------------------------------------------------------------
# Unit tests on _inject_sync_label_proxy_cells / 單元測試
# ---------------------------------------------------------------------------

def test_proxy_cells_added_for_sync_strategies():
    """Given a snapshot with cells only for grid::BTC and ma::ETH, all 4
    sync-label strategies × both symbols = 8 new proxy cells must appear.
    給定只有 grid::BTC + ma::ETH 的快照，4 sync strats × 2 symbols = 8 新 key。"""
    snapshot: dict = {
        "_meta": {"grand_mean_bps": 3.14},
        "grid_trading::BTCUSDT": {"shrunk_bps": 5.0, "n": 100},
        "ma_crossover::ETHUSDT": {"shrunk_bps": -2.0, "n": 50},
    }
    added = _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=3.14)
    assert added == 8  # 4 strategies × 2 symbols

    # Every sync-label × symbol combination must now be present.
    # 每個 sync-label × symbol 組合現在都必須存在。
    for strat in SYNC_LABEL_STRATEGIES:
        for sym in ("BTCUSDT", "ETHUSDT"):
            assert f"{strat}::{sym}" in snapshot, f"missing {strat}::{sym}"


def test_proxy_cells_use_grand_mean_bps():
    """Every proxy cell must have shrunk_bps == grand_mean_bps (rounded). /
    每個代理格子的 shrunk_bps 必須等於（四捨五入的）grand_mean_bps。"""
    snapshot: dict = {
        "_meta": {"grand_mean_bps": -7.8912},
        "grid_trading::SOLUSDT": {"shrunk_bps": 1.0, "n": 10},
    }
    _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=-7.8912)
    for strat in SYNC_LABEL_STRATEGIES:
        cell = snapshot[f"{strat}::SOLUSDT"]
        assert cell["shrunk_bps"] == pytest.approx(-7.8912, abs=1e-4)
        assert cell["n"] == 0


def test_proxy_cells_do_not_overwrite_existing():
    """If bybit_sync::BTCUSDT is already in the snapshot, it must stay untouched. /
    若 bybit_sync::BTCUSDT 已在快照中，必須保持不動。"""
    existing_cell = {"shrunk_bps": 99.99, "n": 42, "custom_marker": "keep_me"}
    snapshot: dict = {
        "_meta": {"grand_mean_bps": 0.0},
        "grid_trading::BTCUSDT": {"shrunk_bps": 1.0, "n": 5},
        "bybit_sync::BTCUSDT": dict(existing_cell),  # copy, will check identity of content
    }
    _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=0.0)

    # bybit_sync::BTCUSDT must still have the original values and marker.
    # bybit_sync::BTCUSDT 必須保留原值和標記。
    assert snapshot["bybit_sync::BTCUSDT"] == existing_cell
    # But the other 3 sync-label strategies × BTCUSDT must still be injected.
    # 但其他 3 sync-label strategies × BTCUSDT 仍必須注入。
    for strat in SYNC_LABEL_STRATEGIES:
        if strat == "bybit_sync":
            continue
        assert f"{strat}::BTCUSDT" in snapshot


def test_proxy_cells_marked_with_provenance():
    """Newly injected proxy cells must carry `_proxy_from == "grand_mean"`. /
    新注入的代理格子必須帶 `_proxy_from == "grand_mean"` 標記。"""
    snapshot: dict = {
        "_meta": {"grand_mean_bps": 2.5},
        "grid_trading::BTCUSDT": {"shrunk_bps": 5.0, "n": 20},
    }
    _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=2.5)
    for strat in SYNC_LABEL_STRATEGIES:
        cell = snapshot[f"{strat}::BTCUSDT"]
        assert cell.get("_proxy_from") == "grand_mean"

    # The real (pre-existing) cell must NOT be tagged as proxy. /
    # 真實（既有）格子不應被標為代理。
    assert "_proxy_from" not in snapshot["grid_trading::BTCUSDT"]


def test_proxy_injection_skips_meta_key():
    """The `_meta` top-level key must not be parsed as a symbol. /
    頂層 `_meta` 鍵不可被當作 symbol 解析。"""
    snapshot: dict = {
        "_meta": {"grand_mean_bps": 1.0, "updated_at": "2026-04-22T00:00:00+00:00"},
        "grid_trading::BTCUSDT": {"shrunk_bps": 3.0, "n": 10},
    }
    _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=1.0)
    # No proxy key should contain "_meta" as its symbol part.
    # 代理 key 中不應出現以 "_meta" 為 symbol 的組合。
    for key in snapshot:
        if "::" in key:
            _, _, sym = key.partition("::")
            assert sym != "_meta"


def test_proxy_injection_on_empty_snapshot_is_noop():
    """Empty snapshot (no real cells) → no proxy cells added, no crash. /
    空快照（沒有真實格子）→ 不加代理、不崩潰。"""
    snapshot: dict = {"_meta": {"grand_mean_bps": 0.0}}
    added = _inject_sync_label_proxy_cells(snapshot, grand_mean_bps=0.0)
    assert added == 0
    assert list(snapshot.keys()) == ["_meta"]


# ---------------------------------------------------------------------------
# Integration with _write_json_snapshot / 與 _write_json_snapshot 整合
# ---------------------------------------------------------------------------

def test_write_json_snapshot_injects_proxy_cells_end_to_end(tmp_path):
    """End-to-end: results with two (strategy, symbol) pairs → on-disk JSON
    contains both real cells and 4 × 2 = 8 proxy cells for sync-label strats.
    端到端：兩對 (strategy, symbol) → 落盤 JSON 含真實 + 4×2=8 代理格子。"""
    results = _make_results(
        [("grid_trading", "BTCUSDT"), ("ma_crossover", "ETHUSDT")],
        grand_mean_bps=1.5,
    )
    out_path = str(tmp_path / "edge_estimates.json")
    _write_json_snapshot(results, out_path)

    with open(out_path) as f:
        on_disk = json.load(f)

    # Real cells present.
    assert "grid_trading::BTCUSDT" in on_disk
    assert "ma_crossover::ETHUSDT" in on_disk
    # Proxy cells present for both symbols × all 4 sync strategies.
    for strat in SYNC_LABEL_STRATEGIES:
        for sym in ("BTCUSDT", "ETHUSDT"):
            assert f"{strat}::{sym}" in on_disk, f"missing proxy {strat}::{sym}"
            cell = on_disk[f"{strat}::{sym}"]
            assert cell["_proxy_from"] == "grand_mean"
            assert cell["n"] == 0
            assert cell["shrunk_bps"] == pytest.approx(1.5, abs=1e-4)

    # _meta preserved.
    assert on_disk["_meta"]["grand_mean_bps"] == pytest.approx(1.5, abs=1e-4)


def test_write_json_snapshot_empty_results_no_proxy(tmp_path):
    """Empty results → snapshot contains only `_meta`, no proxies (no symbols). /
    空 results → 快照只含 `_meta`，無代理（無 symbol 集合）。"""
    out_path = str(tmp_path / "edge_estimates.json")
    _write_json_snapshot({}, out_path)

    with open(out_path) as f:
        on_disk = json.load(f)

    assert list(on_disk.keys()) == ["_meta"]
    assert on_disk["_meta"]["n_cells"] == 0


def test_sync_label_strategies_constant_contains_expected_set():
    """Regression guard: spec-mandated 4 strategies in expected order. /
    回歸保護：規格要求的 4 個策略名（順序對應）。"""
    assert SYNC_LABEL_STRATEGIES == (
        "bybit_sync",
        "orphan_adopted",
        "orphan_frozen",
        "dust_frozen",
    )
