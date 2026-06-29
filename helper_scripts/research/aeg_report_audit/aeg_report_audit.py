#!/usr/bin/env python3
"""CLI for advisory PM/AEG/M4 report audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from . import audit as audit_mod
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research_root = _here.parents[1]
    if str(_research_root) not in sys.path:
        sys.path.insert(0, str(_research_root))
    from aeg_report_audit import audit as audit_mod  # type: ignore


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aeg_report_audit",
        description="Read-only advisory report/aeg/m4 checklist audit",
    )
    parser.add_argument("--profile", choices=sorted(audit_mod.PROFILE_CHECKLISTS), required=True)
    parser.add_argument("--input", action="append", required=True, dest="inputs")
    parser.add_argument("--json-output", default=None, dest="json_output")
    parser.add_argument("--markdown-output", default=None, dest="markdown_output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    batch = audit_mod.audit_many([Path(path) for path in args.inputs], profile=args.profile)
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(
            json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        Path(args.markdown_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown_output).write_text(audit_mod.markdown_summary(batch), encoding="utf-8")
    print(json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
