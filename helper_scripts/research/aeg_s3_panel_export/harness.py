#!/usr/bin/env python3
"""AEG-S3 offline panel export CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import sys
from pathlib import Path
from typing import Optional

try:
    from . import DEFAULT_ALPHA_HISTORY_RUN_ID, DEFAULT_REGIME_CLASSIFIER_VERSION, DEFAULT_UNIVERSE, RUNNER_VERSION
    from . import builder as builder_mod
    from . import data_loader
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_panel_export import DEFAULT_ALPHA_HISTORY_RUN_ID, DEFAULT_REGIME_CLASSIFIER_VERSION, DEFAULT_UNIVERSE, RUNNER_VERSION  # type: ignore
    from aeg_s3_panel_export import builder as builder_mod  # type: ignore
    from aeg_s3_panel_export import data_loader  # type: ignore


def _parse_ts(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _symbols(value: str) -> list[str]:
    seen = set()
    out = []
    for part in value.split(","):
        symbol = part.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _artifact_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def _default_out_dir(export_run_id: str) -> Path:
    return _artifact_root() / export_run_id


def build_and_write(args: argparse.Namespace) -> dict:
    symbols = _symbols(args.symbols)
    sources = data_loader.load_export_sources(
        symbols,
        dsn=args.dsn,
        run_id=args.run_id,
        category=args.category,
        price_timeframe=args.price_timeframe,
        oi_interval_time=args.oi_interval_time,
        regime_classifier_version=args.regime_classifier_version,
        regime_run_id=args.regime_run_id,
        regime_timeframe=args.regime_timeframe,
        window_start=_parse_ts(args.window_start),
        window_end=_parse_ts(args.window_end),
    )
    oi_rows, oi_summary = builder_mod.build_daily_oi_delta_panel(
        price_rows=sources["price_rows"],
        oi_rows=sources["oi_rows"],
        regime_rows=sources["regime_rows"],
        run_id=args.run_id,
        category=args.category,
    )
    funding_rows, funding_summary = builder_mod.build_funding_revive_panel(
        price_rows=sources["price_rows"],
        funding_rows=sources["funding_rows"],
        regime_rows=sources["regime_rows"],
        run_id=args.run_id,
        category=args.category,
    )
    export_run_id = args.export_run_id or f"aeg_s3_panel_export_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(export_run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    oi_path = builder_mod.write_jsonl(out_dir / "oi_delta_panel.jsonl", oi_rows)
    funding_path = builder_mod.write_jsonl(out_dir / "funding_revive_panel.jsonl", funding_rows)
    summary = builder_mod.combined_summary(oi_summary, funding_summary, run_id=args.run_id)
    summary.update({
        "export_run_id": export_run_id,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime_host": socket.gethostname(),
        "source": {
            "alpha_history_run_id": args.run_id,
            "category": args.category,
            "price_timeframe": args.price_timeframe,
            "oi_interval_time": args.oi_interval_time,
            "regime_classifier_version": args.regime_classifier_version,
            "regime_run_id": args.regime_run_id,
            "regime_timeframe": args.regime_timeframe,
            "symbols": symbols,
            "window_start": args.window_start,
            "window_end": args.window_end,
        },
        "artifacts": {
            "oi_delta_panel_jsonl": str(oi_path),
            "funding_revive_panel_jsonl": str(funding_path),
            "summary_json": str(out_dir / "panel_export_summary.json"),
        },
    })
    summary_path = builder_mod.write_json(out_dir / "panel_export_summary.json", summary)
    return {
        "out_dir": str(out_dir),
        "oi_delta_panel_jsonl": str(oi_path),
        "funding_revive_panel_jsonl": str(funding_path),
        "summary_json": str(summary_path),
        "summary": summary,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_s3_panel_export.harness",
        description="Read-only V125/V127 storage export to AEG-S3 offline JSONL panels",
    )
    p.add_argument("--run-id", default=DEFAULT_ALPHA_HISTORY_RUN_ID, dest="run_id")
    p.add_argument("--category", default="linear", dest="category")
    p.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE), dest="symbols")
    p.add_argument("--price-timeframe", default="1d", dest="price_timeframe")
    p.add_argument("--oi-interval-time", default="1h", dest="oi_interval_time")
    p.add_argument("--regime-classifier-version", default=DEFAULT_REGIME_CLASSIFIER_VERSION, dest="regime_classifier_version")
    p.add_argument("--regime-run-id", default=None, dest="regime_run_id")
    p.add_argument("--regime-timeframe", default="1d", dest="regime_timeframe")
    p.add_argument("--window-start", default=None, dest="window_start")
    p.add_argument("--window-end", default=None, dest="window_end")
    p.add_argument("--dsn", default=None, dest="dsn")
    p.add_argument("--export-run-id", default=None, dest="export_run_id")
    p.add_argument("--out-dir", default=None, dest="out_dir")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = build_and_write(args)
    summary = result["summary"]
    print(json.dumps({
        "export_run_id": summary["export_run_id"],
        "run_id": summary["run_id"],
        "out_dir": result["out_dir"],
        "total_rows": summary["total_rows"],
        "total_rejected_rows": summary["total_rejected_rows"],
        "artifacts": summary["artifacts"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
