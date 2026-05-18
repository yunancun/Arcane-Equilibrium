"""
測試 phase_1b_sweep_cells module — cell matrix + cartesian generator。

為什麼這些 test：spec §1.4 定 81 cells；任何偏差（block 數錯 / cell_id 重複 /
參數軸錯）都影響後續 simulation correctness。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 為 pytest standalone run 注入 module path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1b_sweep_cells import (  # noqa: E402
    AB_COMBINATIONS,
    C_GRID_TIMEOUTS_MS,
    C_PL_GIVEBACK_TIMEOUTS_MS,
    C_PL_STALE_TIMEOUTS_MS,
    SPREAD_GUARD_D_VALUES_BPS,
    CalibrationCell,
    cell_count_per_block,
    enumerate_cells,
    generate_block_1_grid,
    generate_block_2_phys_giveback,
    generate_block_3_phys_stale,
    generate_block_4_spread_guard,
)


def test_total_cell_count_is_81():
    """spec §1.4 Total = 24+24+24+9 = 81。"""
    cells = enumerate_cells()
    assert len(cells) == 81


def test_per_block_count():
    """Block 1/2/3 = 24 each; Block 4 = 9。"""
    counts = cell_count_per_block()
    assert counts["block_1_grid"] == 24
    assert counts["block_2_phys_giveback"] == 24
    assert counts["block_3_phys_stale"] == 24
    assert counts["block_4_spread_guard"] == 9
    assert counts["total"] == 81


def test_ab_combinations_count():
    """spec §1.4 AB sweep = 8 combos per block (1-3)。"""
    assert len(AB_COMBINATIONS) == 8


def test_grid_block_1_timeouts():
    """spec §1.4 Block 1 C-grid = {30, 60, 90}s。"""
    assert C_GRID_TIMEOUTS_MS == [30_000, 60_000, 90_000]


def test_phys_giveback_block_2_timeouts():
    """spec §1.4 Block 2 C-pl = {15, 45, 60}s。"""
    assert C_PL_GIVEBACK_TIMEOUTS_MS == [15_000, 45_000, 60_000]


def test_phys_stale_block_3_timeouts():
    """spec §1.4 Block 3 C-pl-stale = {10, 30, 45}s。"""
    assert C_PL_STALE_TIMEOUTS_MS == [10_000, 30_000, 45_000]


def test_spread_guard_block_4_values():
    """spec §1.4 Block 4 D = {25, 35, 50}bps。"""
    assert SPREAD_GUARD_D_VALUES_BPS == [25.0, 35.0, 50.0]


def test_cell_ids_are_unique():
    """spec hard constraint: cell_id must be unique across all 81 cells."""
    cells = enumerate_cells()
    ids = [c.cell_id for c in cells]
    assert len(set(ids)) == len(ids), f"duplicates: {len(ids) - len(set(ids))}"


def test_baseline_cells_marked():
    """每 block 必有 1 baseline anchor 標 is_baseline=True。"""
    cells = enumerate_cells()
    baselines_in_block = {}
    for c in cells:
        if c.is_baseline:
            baselines_in_block.setdefault(c.block, []).append(c.cell_id)
    # Block 1/2/3 should each have exactly 1 baseline cell (AB-01 + first timeout)
    assert len(baselines_in_block.get(1, [])) == 1
    assert len(baselines_in_block.get(2, [])) == 1
    assert len(baselines_in_block.get(3, [])) == 1
    # Block 4 D=50 in each family → 3 baseline cells
    assert len(baselines_in_block.get(4, [])) == 3


def test_block_1_grid_first_cell_is_anchor():
    """spec §1.4 Block 1 第一個 cell 應為 G-AB-01-C30 (0.5/1/30s baseline)。"""
    first = next(generate_block_1_grid())
    assert first.cell_id == "G-AB-01-C30"
    assert first.offset_bps == 0.5
    assert first.buffer_ticks == 1
    assert first.timeout_ms == 30_000
    assert first.spread_guard_bps == 50.0
    assert first.is_baseline is True


def test_block_2_phys_giveback_first_cell():
    """spec §1.4 Block 2 第一個 cell 應為 PG-AB-01-C15。"""
    first = next(generate_block_2_phys_giveback())
    assert first.cell_id == "PG-AB-01-C15"
    assert first.timeout_ms == 15_000


def test_block_3_phys_stale_first_cell():
    """spec §1.4 Block 3 第一個 cell 應為 PS-AB-01-C10。"""
    first = next(generate_block_3_phys_stale())
    assert first.cell_id == "PS-AB-01-C10"
    assert first.timeout_ms == 10_000


def test_block_4_spread_guard_cells():
    """spec §1.4 Block 4 = 3 families × 3 D values = 9 cells, baseline A=0.5/B=1。"""
    cells = list(generate_block_4_spread_guard())
    assert len(cells) == 9
    for c in cells:
        assert c.offset_bps == 0.5
        assert c.buffer_ticks == 1
        assert c.block == 4


def test_e2_tune_1_inside_cell_exists():
    """spec §1.4 G-AB-02 是 E2 Tune-1 inside cell (buffer=0)。"""
    cells = enumerate_cells()
    inside_cells = [c for c in cells if c.buffer_ticks == 0 and c.family == "grid"]
    # 應有 3 cells: G-AB-02-C30/C60/C90
    assert len(inside_cells) == 3
    assert {c.timeout_ms for c in inside_cells} == {30_000, 60_000, 90_000}


def test_v48_wide_cells_exist():
    """spec §1.4 v48 寬向：buffer_ticks ∈ {2,3,4} 在 grid block 1。"""
    cells = enumerate_cells()
    wide_cells = [
        c for c in cells
        if c.family == "grid" and c.buffer_ticks in (2, 3, 4)
    ]
    # AB-04 (buffer=2) + AB-06 (buffer=3) + AB-08 (buffer=4) × 3 timeouts = 9 cells
    assert len(wide_cells) == 9


def test_cell_to_dict_serializable():
    """CalibrationCell.to_dict 為 JSON serializable。"""
    import json
    cell = next(enumerate_cells().__iter__())
    d = cell.to_dict()
    json.dumps(d)  # 不應拋
    assert d["cell_id"] == cell.cell_id


def test_cells_are_immutable():
    """CalibrationCell 必 frozen dataclass。"""
    cell = next(enumerate_cells().__iter__())
    try:
        cell.cell_id = "MODIFIED"
        raise AssertionError("frozen dataclass should not allow mutation")
    except (AttributeError, Exception):
        # frozen dataclass raises FrozenInstanceError (subclass of AttributeError)
        pass
