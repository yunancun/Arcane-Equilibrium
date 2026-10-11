#!/usr/bin/env python3
"""R8 階段 1 的本機入口；沒有取數、資料庫或部署行為。"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    analytics = subs.add_parser("analytics")
    analytics.add_argument("report", type=Path)
    analytics.add_argument("--output", required=True, type=Path)
    analytics.add_argument("--replay-end-ts-ms", type=int)
    analytics.add_argument("--funding-hours", type=Path, help='JSON symbol -> UTC hours; "*" sets default')
    manifest = subs.add_parser("manifest")
    for name in ("fixture", "key-file", "output"):
        manifest.add_argument(f"--{name}", required=True, type=Path)
    manifest.add_argument("--experiment-id", required=True)
    manifest.add_argument("--strategy", default="ma_crossover")
    manifest.add_argument("--environment", choices=("demo", "paper", "live"))
    manifest.add_argument("--snapshot", type=Path)
    manifest.add_argument("--repo-root", type=Path, default=ROOT)
    manifest.add_argument("--next-open", action="store_true")
    manifest.add_argument("--taker-entry", action="store_true")
    manifest.add_argument("--full-chain", action="store_true")
    manifest.add_argument("--starting-balance", type=float, default=10000)
    manifest.add_argument("--data-tier", choices=("S2", "S3"), default="S2")
    manifest.add_argument("--run-id")
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        if command == "manifest":
            from replay.offline_manifest import build_signed_manifest
            signed = build_signed_manifest(**args)
            print(json.dumps({"parameter_provenance": signed["parameter_provenance"],
                              "parameter_overrides": signed["parameter_overrides"],
                              "manifest_hash": signed["manifest_hash"]}, ensure_ascii=False))
        else:
            from replay.offline_analytics import analyze_report
            report, output, schedule = args.pop("report"), args.pop("output"), args.pop("funding_hours")
            if output.resolve() in {report.resolve(), schedule.resolve() if schedule else report.resolve()}:
                raise ValueError("output must not overwrite input")
            result = analyze_report(json.loads(report.read_text()),
                                    funding_hours=json.loads(schedule.read_text()) if schedule else None, **args)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"replay_local: {exc}\n")


if __name__ == "__main__":
    main()
