"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep 的 cell matrix 與 cartesian product 生成。
依 PA spec `docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`
§1.4 Pruned Cell Matrix 定義 81 cells（24+24+24+9）跨 4 block：
  - Block 1: grid family A×B sweep × C-grid timeout {30, 60, 90}s
  - Block 2: phys_lock_gate4_giveback A×B sweep × C-pl {15, 45, 60}s
  - Block 3: phys_lock_gate4_stale_roc_neg A×B sweep × C-pl-stale {10, 30, 45}s
  - Block 4: spread guard D decoupled sweep × 3 families
主要類/函數：CalibrationCell dataclass、enumerate_cells、generate_block_1/2/3/4。
依賴：std dataclasses only（純 Python，無 IO，可單測）。
硬邊界：cell_id 必唯一；output 順序固定為 deterministic replay；
        baseline cell 必含於每 block 用於 vs-baseline 比較。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterator, List


# §1.4 Block 1-3 共用 8 A×B combination（pruned per §1.3 Rule 3）
# baseline anchor + E2 Tune-1 inside + v48 寬向多階。
AB_COMBINATIONS = [
    # (cell_subid_suffix, offset_bps, buffer_ticks, direction_note)
    ("AB-01", 0.5, 1, "baseline anchor"),
    ("AB-02", 0.5, 0, "E2 Tune-1 inside (same-price maker)"),
    ("AB-03", 1.0, 1, "v48 mid offset, baseline buffer"),
    ("AB-04", 1.0, 2, "v48 mid offset, wide buffer"),
    ("AB-05", 2.0, 1, "v48 wide offset"),
    ("AB-06", 2.0, 3, "v48 wide × wide"),
    ("AB-07", 3.0, 1, "v48 max offset"),
    ("AB-08", 3.0, 4, "v48 max × max wide"),
]

# §1.4 Block 1 grid family timeout（C-grid）— include baseline 30s + extensions.
C_GRID_TIMEOUTS_MS = [30_000, 60_000, 90_000]

# §1.4 Block 2 phys_lock_gate4_giveback timeout（C-pl）.
C_PL_GIVEBACK_TIMEOUTS_MS = [15_000, 45_000, 60_000]

# §1.4 Block 3 phys_lock_gate4_stale_roc_neg timeout（C-pl-stale）.
C_PL_STALE_TIMEOUTS_MS = [10_000, 30_000, 45_000]

# §1.4 Block 4 spread guard D values（含 baseline 50）.
SPREAD_GUARD_D_VALUES_BPS = [25.0, 35.0, 50.0]

# Family canonical exit_reason mapping per spec §1.3 Prune Rule 1.
# grid family 共用 grid-baseline policy，sweep 時其代表 exit_reason 用於 fill seed。
FAMILY_EXIT_REASONS = {
    "grid": [
        "grid_close_short",
        "grid_close_long",
        "bb_mean_revert",
        "ma_reverse_cross",
        "bw_squeeze",
        "pctb_revert",
    ],
    "phys_lock_giveback": ["phys_lock_gate4_giveback"],
    "phys_lock_stale_roc_neg": ["phys_lock_gate4_stale_roc_neg"],
}


@dataclass(frozen=True)
class CalibrationCell:
    """Phase 1b sweep 單一 cell 配置。

    為什麼用 frozen dataclass：cell 是 deterministic input，hash 與 replay 一致；
    不變量：cell_id 唯一；offset_bps ≥ 0；buffer_ticks ≥ 0；timeout_ms > 0。
    """
    cell_id: str
    family: str  # "grid" / "phys_lock_giveback" / "phys_lock_stale_roc_neg"
    block: int  # 1 / 2 / 3 / 4
    offset_bps: float  # axis A
    buffer_ticks: int  # axis B
    timeout_ms: int  # axis C
    spread_guard_bps: float = 50.0  # axis D, default = baseline
    is_baseline: bool = False
    direction_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _generate_block_ab_c(
    family: str,
    block_num: int,
    timeouts_ms: List[int],
) -> Iterator[CalibrationCell]:
    """生成 block 1/2/3 共用結構：8 AB × 3 timeout = 24 cells。

    為什麼共用 helper：3 block 結構同形，只 family + block_num + timeout 不同；
    減少重複；維持 spec §1.4 對齊。
    """
    family_prefix = {
        "grid": "G",
        "phys_lock_giveback": "PG",
        "phys_lock_stale_roc_neg": "PS",
    }[family]
    for ab_suffix, offset, buffer_ticks, note in AB_COMBINATIONS:
        for timeout_ms in timeouts_ms:
            timeout_label = f"C{timeout_ms // 1000}"
            cell_id = f"{family_prefix}-{ab_suffix}-{timeout_label}"
            # baseline = first timeout (spec baseline value) + first AB combo (0.5/1)
            is_baseline = (
                ab_suffix == "AB-01"
                and timeout_ms == timeouts_ms[0]
            )
            yield CalibrationCell(
                cell_id=cell_id,
                family=family,
                block=block_num,
                offset_bps=offset,
                buffer_ticks=buffer_ticks,
                timeout_ms=timeout_ms,
                spread_guard_bps=50.0,  # baseline D
                is_baseline=is_baseline,
                direction_note=note,
            )


def generate_block_1_grid() -> Iterator[CalibrationCell]:
    """Block 1: grid family A×B sweep × C-grid timeout {30, 60, 90}s = 24 cells."""
    return _generate_block_ab_c("grid", 1, C_GRID_TIMEOUTS_MS)


def generate_block_2_phys_giveback() -> Iterator[CalibrationCell]:
    """Block 2: phys_lock_gate4_giveback A×B × C-pl {15, 45, 60}s = 24 cells."""
    return _generate_block_ab_c(
        "phys_lock_giveback", 2, C_PL_GIVEBACK_TIMEOUTS_MS
    )


def generate_block_3_phys_stale() -> Iterator[CalibrationCell]:
    """Block 3: phys_lock_gate4_stale_roc_neg A×B × C-pl-stale {10, 30, 45}s = 24 cells."""
    return _generate_block_ab_c(
        "phys_lock_stale_roc_neg", 3, C_PL_STALE_TIMEOUTS_MS
    )


def generate_block_4_spread_guard() -> Iterator[CalibrationCell]:
    """Block 4: spread guard D decoupled sweep × 3 families = 9 cells.

    依 spec §1.3 Prune Rule 2：D 軸 baseline A=0.5/B=1/C=baseline-per-family，
    僅變動 D ∈ {25, 35, 50}。effect 主要在 PostOnly reject volume + wide-spread skip。
    """
    family_baselines = {
        "grid": (1, "G", C_GRID_TIMEOUTS_MS[0]),  # 30s
        "phys_lock_giveback": (2, "PG", C_PL_GIVEBACK_TIMEOUTS_MS[0]),  # 15s
        "phys_lock_stale_roc_neg": (3, "PS", C_PL_STALE_TIMEOUTS_MS[0]),  # 10s
    }
    for family, (block_num, prefix, timeout_ms) in family_baselines.items():
        for d_bps in SPREAD_GUARD_D_VALUES_BPS:
            cell_id = f"{prefix}-D-D{int(d_bps)}"
            # baseline D=50 既存於 Block 1-3 baseline 也存於 Block 4：標 is_baseline=True
            # 但 cell_id 不同；report 階段需 dedupe by (family, A, B, C, D)。
            yield CalibrationCell(
                cell_id=cell_id,
                family=family,
                block=4,
                offset_bps=0.5,  # baseline A
                buffer_ticks=1,  # baseline B
                timeout_ms=timeout_ms,
                spread_guard_bps=d_bps,
                is_baseline=(d_bps == 50.0),
                direction_note=f"D-axis spread_guard sweep at family baseline",
            )


def enumerate_cells() -> List[CalibrationCell]:
    """生成全部 81 cells，per spec §1.4 順序：Block 1 → 2 → 3 → 4。

    輸出順序 deterministic：sweep replay 可 resume / partial run / 與 report 對齊。
    """
    cells: List[CalibrationCell] = []
    cells.extend(generate_block_1_grid())
    cells.extend(generate_block_2_phys_giveback())
    cells.extend(generate_block_3_phys_stale())
    cells.extend(generate_block_4_spread_guard())
    return cells


def cell_count_per_block() -> dict:
    """回傳每 block cell 數，方便 test 驗證 total = 81。"""
    return {
        "block_1_grid": len(list(generate_block_1_grid())),
        "block_2_phys_giveback": len(list(generate_block_2_phys_giveback())),
        "block_3_phys_stale": len(list(generate_block_3_phys_stale())),
        "block_4_spread_guard": len(list(generate_block_4_spread_guard())),
        "total": len(enumerate_cells()),
    }


if __name__ == "__main__":
    # CLI smoke：列出所有 cells（用於 PA spec verify）
    import json
    cells = enumerate_cells()
    summary = cell_count_per_block()
    print(f"Total cells: {summary['total']}")
    print(f"Per-block: {json.dumps(summary, indent=2)}")
    for c in cells[:5]:
        print(c)
    print(f"... ({len(cells) - 5} more)")
