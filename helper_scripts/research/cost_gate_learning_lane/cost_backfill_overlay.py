#!/usr/bin/env python3
"""歷史樂觀成本回填 overlay(P1-2c)。

MODULE_NOTE:
  模塊用途：對 append-only ledger 中既有的 legacy_optimistic(cost_bps=4.0)outcome
    row，不原地改寫(append-only 紀律 + D9 rotation 將動此檔)，改產 overlay artifact
    ``blocked_outcome_cost_backfill_v1.jsonl``：attempt_id → 保守成本重算值，供 review
    覆蓋計算。多 ledger 檔 lineage 取 UNION、按 (attempt_id, record_type) 去重
    (addendum §B.4:遷移檔 + /tmp 遺留副本可互有獨占行)。
  主要函數：build_cost_backfill_overlay(純函數，多檔 rows + slippage table)、
    load_overlay(review 側讀回)、main(CLI)。
  依賴：cost_model.py(保守成本)、runtime_adapter(read_jsonl_ledger)、
    slippage artifact；OPENCLAW_DATA_DIR 決定預設路徑。
  硬邊界：只讀 ledger、只寫 overlay artifact;不改寫 ledger、不寫 PG、不送單。

QC spec 正本:docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-04--evidence_
methodology_redesign_p12_p27_p28_f7.md §2.4 + addendum §B.4/§D(A6 lineage)。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import (
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.cost_model import (
    LEGACY_OPTIMISTIC_COST_BPS,
    conservative_cost_bps,
    funding_crossing_count,
    load_slippage_quantiles,
)
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger


OVERLAY_SCHEMA_VERSION = "cost_gate_blocked_outcome_cost_backfill_v1"
OVERLAY_FILENAME = "blocked_outcome_cost_backfill_v1.jsonl"
_OUTCOME_RECORD_TYPES = frozenset(
    {BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE, PROBE_OUTCOME_RECORD_TYPE}
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _needs_backfill(row: dict[str, Any]) -> bool:
    """僅回填 legacy_optimistic row:cost_model_version 缺失(舊 schema v1)。

    已含 conservative_v1 的 row 由 writer 直接算好，不需 overlay(避免雙重覆蓋)。
    """
    if _str(row.get("record_type")) not in _OUTCOME_RECORD_TYPES:
        return False
    if row.get("censored") is True:
        return False
    if _str(row.get("cost_model_version")):
        return False
    return _float(row.get("gross_bps")) is not None


def build_cost_backfill_overlay(
    ledger_files: list[tuple[str, list[dict[str, Any]]]],
    *,
    slippage_payload: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
    funding_interval_hours: float = 8.0,
) -> dict[str, Any]:
    """多 ledger 檔 UNION 去重 → 每 attempt 的保守成本重算 overlay(純函數)。

    ledger_files: [(lineage_source, rows), ...]。去重鍵 = (attempt_id, record_type)。
    per-file 行數與交集/差集統計落 overlay 頭部(A6 lineage 驗收)。獨占行照常回填
    並標 lineage_source。
    """
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    table = load_slippage_quantiles(slippage_payload)

    # 各檔的回填候選鍵集合(供交集/差集統計)。
    per_file_keys: dict[str, set[tuple[str, str]]] = {}
    per_file_row_count: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    overlay_rows: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for lineage_source, rows in ledger_files:
        per_file_row_count[lineage_source] = len(rows)
        keys: set[tuple[str, str]] = set()
        for row in rows:
            if not _needs_backfill(row):
                continue
            attempt_id = _str(row.get("attempt_id"))
            record_type = _str(row.get("record_type"))
            if not attempt_id:
                unmatched.append(f"{lineage_source}:missing_attempt_id")
                continue
            key = (attempt_id, record_type)
            keys.add(key)
            if key in seen:
                continue
            seen.add(key)
            overlay_rows.append(
                _overlay_row_for(
                    row,
                    lineage_source=lineage_source,
                    table=table,
                    now=now,
                    funding_interval_hours=funding_interval_hours,
                )
            )
        per_file_keys[lineage_source] = keys

    lineage_sources = [name for name, _ in ledger_files]
    intersection = None
    for keys in per_file_keys.values():
        intersection = keys if intersection is None else (intersection & keys)
    intersection = intersection or set()

    return {
        "schema_version": OVERLAY_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "lineage_sources": lineage_sources,
        "per_file_row_count": per_file_row_count,
        "per_file_backfill_candidate_count": {
            name: len(keys) for name, keys in per_file_keys.items()
        },
        "union_backfilled_count": len(overlay_rows),
        "intersection_count": len(intersection),
        "unmatched": unmatched,
        "unmatched_count": len(unmatched),
        "overlay_rows": overlay_rows,
        "boundary": (
            "cost backfill overlay artifact only; ledger is not rewritten; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def _overlay_row_for(
    row: dict[str, Any],
    *,
    lineage_source: str,
    table: Any,
    now: dt.datetime,
    funding_interval_hours: float,
) -> dict[str, Any]:
    symbol = _str(row.get("symbol")).upper()
    horizon_minutes = _int(row.get("horizon_minutes"), default=60)
    event_ts_ms = _int(row.get("event_ts_ms"))
    gross_bps = _float(row.get("gross_bps")) or 0.0
    crossings = funding_crossing_count(
        event_ts_ms=event_ts_ms,
        horizon_minutes=horizon_minutes,
        funding_interval_hours=funding_interval_hours,
    )
    cost = conservative_cost_bps(
        symbol=symbol,
        horizon_minutes=horizon_minutes,
        table=table,
        now=now,
        funding_crossings=crossings,
    )
    cost_cons = cost["cost_bps"]
    return {
        "attempt_id": _str(row.get("attempt_id")),
        "record_type": _str(row.get("record_type")),
        "side_cell_key": _str(row.get("side_cell_key")),
        "lineage_source": lineage_source,
        "cost_bps_conservative": cost_cons,
        "realized_net_bps_conservative": gross_bps - cost_cons,
        "overstated_bps": cost_cons - LEGACY_OPTIMISTIC_COST_BPS,
        "cost_model_source": cost["cost_model_source"],
        "cost_model_version": cost["cost_model_version"],
    }


def load_overlay(path: Path) -> dict[str, dict[str, Any]]:
    """review 側讀回 overlay:{(attempt_id) → overlay_row}(以 attempt_id 為鍵)。

    overlay 檔為 JSONL(每行一 overlay_row)或含 overlay_rows 的 JSON;不存在 → {}。
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    rows: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(payload)
    else:
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows = [r for r in payload.get("overlay_rows", []) if isinstance(r, dict)]
    return {_str(r.get("attempt_id")): r for r in rows if _str(r.get("attempt_id"))}


def _write_overlay_jsonl(path: Path, batch: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in batch.get("overlay_rows", []):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _default_overlay_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / OVERLAY_FILENAME


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, action="append", required=True,
                        help="ledger 檔(可多次;每個 = 一 lineage source)")
    parser.add_argument("--slippage-artifact", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    slippage_payload = None
    if args.slippage_artifact and args.slippage_artifact.exists():
        slippage_payload = json.loads(args.slippage_artifact.read_text(encoding="utf-8"))
    ledger_files = [
        (str(path), read_jsonl_ledger(path)) for path in args.ledger
    ]
    batch = build_cost_backfill_overlay(ledger_files, slippage_payload=slippage_payload)
    output = args.output or _default_overlay_path()
    _write_overlay_jsonl(output, batch)
    if args.summary_output:
        summary = {k: v for k, v in batch.items() if k != "overlay_rows"}
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    if args.print_json:
        summary = {k: v for k, v in batch.items() if k != "overlay_rows"}
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
