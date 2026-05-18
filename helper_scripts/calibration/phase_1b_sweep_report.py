"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep 輸出彙整 + Wilson CI + acceptance gate +
        JSON/CSV report 輸出。
依 PA spec §4 Acceptance Criteria + §2.4 output schema：
  - PASS: fill_rate≥25%, wilson_ci_low≥15%, fee_saving≥0.5bps, wilson_ci_low≥0,
          adverse_proxy ≤ pre-Phase-1b taker baseline
  - CONDITIONAL: fill_rate≥15%, fee_saving≥0.3bps, adverse_proxy ≤ baseline
  - FAIL: else
主要類/函數：CellReport / wilson_score_interval / classify_cell /
            aggregate_report / write_outputs。
依賴：std math; phase_1b_sweep_replay。
硬邊界：output 寫至 helper_scripts/calibration/output/；JSON schema 對齊 spec
        §2.4；data_source tag 必含；不動 production code 或 TOML / V### migration。
"""
from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_1b_sweep_replay import (  # noqa: E402
    CellSimulationOutcome,
    FillSimulationResult,
)
from phase_1b_tick_loader import DATA_SOURCE_TAG  # noqa: E402


# spec §4.1 PASS gate thresholds
PASS_MAKER_FILL_RATE = 0.25
PASS_WILSON_CI_LOW = 0.15
PASS_FEE_SAVING_BPS = 0.5
PASS_FEE_WILSON_CI_LOW = 0.0

# spec §4.2 CONDITIONAL gate thresholds
COND_MAKER_FILL_RATE = 0.15
COND_FEE_SAVING_BPS = 0.3


@dataclass
class CellReport:
    """單一 cell 完整 report 結構（output JSON schema per spec §2.4）。

    為什麼這結構：把 CellSimulationOutcome 攤平 + 加 Wilson CI + pass_gate；
    一個 cell 一個 JSON file，方便 PA / QA selectively load。
    """
    cell_id: str
    block: int
    family: str
    offset_bps: float
    buffer_ticks: int
    timeout_ms: int
    spread_guard_bps: float
    is_baseline: bool
    direction_note: str
    # simulation
    n_attempts: int
    n_simulated_fills: int
    n_skipped_spread_guard: int
    n_skipped_no_bbo: int
    n_skipped_tick_missing: int
    n_skipped_family_mismatch: int
    n_skipped_crossed_book: int
    n_eligible: int
    maker_fill_rate: float
    fill_rate_wilson_ci_low: float
    fill_rate_wilson_ci_high: float
    expected_fee_saving_bps: float
    fee_saving_wilson_ci_low: float
    fee_saving_wilson_ci_high: float
    adverse_selection_proxy_bps: Optional[float]
    pre_phase_1b_taker_baseline_bps: float
    pass_gate: str  # 'PASS' / 'CONDITIONAL' / 'FAIL'
    data_source: str = DATA_SOURCE_TAG
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def wilson_score_interval(
    successes: int,
    n: int,
    z: float = 1.96,
) -> tuple[float, float]:
    """Wilson score interval（95% CI default per spec AC-14）。

    為什麼 Wilson 非 normal approximation：小樣本（n=4 post-restart）下 normal
    approximation 嚴重偏；Wilson 在邊界 (p=0 or p=1) 仍有效。
    為什麼 z=1.96：對應 95% CI。
    return: (low, high) within [0, 1].
    """
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    low = max(0.0, centre - half)
    high = min(1.0, centre + half)
    return (low, high)


def fee_saving_ci(
    fee_savings: list[float],
    z: float = 1.96,
) -> tuple[float, float]:
    """fee_saving_bps 的 95% CI（normal approximation）。

    為什麼用 normal approx：fee_saving 是 continuous metric，n>1 時 t-test
    近似 normal；n=1 時無法計 CI → 回 (saving, saving)；n=0 → (0, 0)。
    """
    n = len(fee_savings)
    if n == 0:
        return (0.0, 0.0)
    mean = sum(fee_savings) / n
    if n == 1:
        return (mean, mean)
    variance = sum((x - mean) ** 2 for x in fee_savings) / (n - 1)
    se = math.sqrt(variance / n)
    return (mean - z * se, mean + z * se)


def classify_cell(
    *,
    maker_fill_rate: float,
    fill_rate_wilson_ci_low: float,
    expected_fee_saving_bps: float,
    fee_saving_wilson_ci_low: float,
    adverse_selection_proxy_bps: Optional[float],
    pre_phase_1b_taker_baseline_bps: float,
) -> str:
    """spec §4 PASS / CONDITIONAL / FAIL gate 評估。

    為什麼 adverse_selection 是 ≤ baseline 的硬條件：spec §4.1 強制；
    None proxy（無 post-drift sample）→ treat as worst case = FAIL adverse；
    保守 fail-closed 對齊 §二 #6。
    """
    adverse_ok = (
        adverse_selection_proxy_bps is not None
        and adverse_selection_proxy_bps <= pre_phase_1b_taker_baseline_bps
    )

    if (
        maker_fill_rate >= PASS_MAKER_FILL_RATE
        and fill_rate_wilson_ci_low >= PASS_WILSON_CI_LOW
        and expected_fee_saving_bps >= PASS_FEE_SAVING_BPS
        and fee_saving_wilson_ci_low >= PASS_FEE_WILSON_CI_LOW
        and adverse_ok
    ):
        return "PASS"

    if (
        maker_fill_rate >= COND_MAKER_FILL_RATE
        and expected_fee_saving_bps >= COND_FEE_SAVING_BPS
        and adverse_ok
    ):
        return "CONDITIONAL"

    return "FAIL"


def build_report_for_cell(
    outcome: CellSimulationOutcome,
    cell_meta: dict,
    pre_phase_1b_taker_baseline_bps: float,
) -> CellReport:
    """從 CellSimulationOutcome + cell metadata 組裝 CellReport。

    為什麼 cell_meta 是 dict 而非 CalibrationCell：保持 report 模塊不直接依賴
    sweep_cells；外部 dict 包含 cell_id/block/family/A/B/C/D/baseline/note。
    """
    fee_savings = [
        r.fee_saving_bps for r in outcome.per_fill_results
        if r.fee_saving_bps is not None
    ]
    n_eligible = outcome.n_attempts - (
        outcome.n_skipped_spread_guard
        + outcome.n_skipped_no_bbo
        + outcome.n_skipped_tick_missing
        + outcome.n_skipped_family_mismatch
        + outcome.n_skipped_crossed_book
    )
    fill_low, fill_high = wilson_score_interval(
        outcome.n_simulated_fills, max(1, n_eligible)
    )
    fee_low, fee_high = fee_saving_ci(fee_savings)

    pass_gate = classify_cell(
        maker_fill_rate=outcome.maker_fill_rate,
        fill_rate_wilson_ci_low=fill_low,
        expected_fee_saving_bps=outcome.expected_fee_saving_bps,
        fee_saving_wilson_ci_low=fee_low,
        adverse_selection_proxy_bps=outcome.adverse_selection_proxy_bps,
        pre_phase_1b_taker_baseline_bps=pre_phase_1b_taker_baseline_bps,
    )

    return CellReport(
        cell_id=outcome.cell_id,
        block=cell_meta["block"],
        family=cell_meta["family"],
        offset_bps=cell_meta["offset_bps"],
        buffer_ticks=cell_meta["buffer_ticks"],
        timeout_ms=cell_meta["timeout_ms"],
        spread_guard_bps=cell_meta["spread_guard_bps"],
        is_baseline=cell_meta["is_baseline"],
        direction_note=cell_meta["direction_note"],
        n_attempts=outcome.n_attempts,
        n_simulated_fills=outcome.n_simulated_fills,
        n_skipped_spread_guard=outcome.n_skipped_spread_guard,
        n_skipped_no_bbo=outcome.n_skipped_no_bbo,
        n_skipped_tick_missing=outcome.n_skipped_tick_missing,
        n_skipped_family_mismatch=outcome.n_skipped_family_mismatch,
        n_skipped_crossed_book=outcome.n_skipped_crossed_book,
        n_eligible=n_eligible,
        maker_fill_rate=outcome.maker_fill_rate,
        fill_rate_wilson_ci_low=fill_low,
        fill_rate_wilson_ci_high=fill_high,
        expected_fee_saving_bps=outcome.expected_fee_saving_bps,
        fee_saving_wilson_ci_low=fee_low,
        fee_saving_wilson_ci_high=fee_high,
        adverse_selection_proxy_bps=outcome.adverse_selection_proxy_bps,
        pre_phase_1b_taker_baseline_bps=pre_phase_1b_taker_baseline_bps,
        pass_gate=pass_gate,
    )


def aggregate_summary(reports: list[CellReport]) -> dict:
    """sweep-level aggregate：count per gate + top-2 by score。

    為什麼 score = fill_rate × fee_saving：spec §4.1 末段「top-2 cells by
    `expected_fee_saving_bps × maker_fill_rate`」對齊；
    PASS pool 內排序 → operator pilot dispatch input。
    """
    pass_cells = [r for r in reports if r.pass_gate == "PASS"]
    cond_cells = [r for r in reports if r.pass_gate == "CONDITIONAL"]
    fail_cells = [r for r in reports if r.pass_gate == "FAIL"]

    def score(r: CellReport) -> float:
        return r.maker_fill_rate * r.expected_fee_saving_bps

    pass_sorted = sorted(pass_cells, key=score, reverse=True)
    cond_sorted = sorted(cond_cells, key=score, reverse=True)

    return {
        "total_cells": len(reports),
        "n_pass": len(pass_cells),
        "n_conditional": len(cond_cells),
        "n_fail": len(fail_cells),
        "top_pass_cells": [r.cell_id for r in pass_sorted[:2]],
        "top_conditional_cells": [r.cell_id for r in cond_sorted[:2]],
        "data_source": DATA_SOURCE_TAG,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_outputs(
    reports: list[CellReport],
    output_dir: Path,
    per_fill_results: Optional[list[FillSimulationResult]] = None,
) -> dict:
    """寫 81 個 per-cell JSON + 1 aggregate CSV + 1 summary JSON。

    為什麼分檔：
      - per-cell JSON：PA / QA inspect 單 cell 用；
      - aggregate CSV：human-readable / spreadsheet load 用；
      - summary JSON：CI / 自動化 input。
    write_outputs 不負責 cleanup；每 sweep run 應建新 timestamped subdir。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)

    # per-cell JSON
    for report in reports:
        cell_path = cells_dir / f"{report.cell_id}.json"
        with cell_path.open("w") as f:
            json.dump(asdict(report), f, indent=2, default=str)

    # aggregate CSV
    csv_path = output_dir / "sweep_aggregate.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(reports[0]).keys()) if reports else [])
        writer.writeheader()
        for r in reports:
            writer.writerow(asdict(r))

    # summary JSON
    summary = aggregate_summary(reports)
    summary_path = output_dir / "sweep_summary.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2, default=str)

    # optional: per-fill audit (full simulation trace) — large file
    if per_fill_results is not None:
        per_fill_path = output_dir / "per_fill_audit.jsonl"
        with per_fill_path.open("w") as f:
            for r in per_fill_results:
                d = asdict(r)
                f.write(json.dumps(d, default=str) + "\n")

    return {
        "output_dir": str(output_dir),
        "cells_dir": str(cells_dir),
        "csv_path": str(csv_path),
        "summary_path": str(summary_path),
        "n_cells_written": len(reports),
        "summary": summary,
    }
