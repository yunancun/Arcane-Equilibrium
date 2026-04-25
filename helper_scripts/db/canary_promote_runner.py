#!/usr/bin/env python3
"""Canary auto-promote runner — single-shot CLI (G4-03 Phase A, 2026-04-25).
Canary 自動晉升執行腳本（G4-03 Phase A）。

MODULE_NOTE (EN): One-shot driver around `canary_promoter.auto_promote_
  eligible_models`. Operator invokes manually for preview / opt-in
  apply, OR cron-driven later (Phase 4 deliverable per draft §
  Auto-promote cron). Defaults to dry-run; `--apply` requires the
  default-OFF env var `OPENCLAW_AUTO_PROMOTE_ENABLED=1`.

  Usage:
    # preview (default)
    python3 helper_scripts/db/canary_promote_runner.py
    python3 helper_scripts/db/canary_promote_runner.py --dry-run

    # apply (requires env var)
    OPENCLAW_AUTO_PROMOTE_ENABLED=1 \\
      python3 helper_scripts/db/canary_promote_runner.py --apply

  Output: per-row decision table + summary counts. Exit 0 always
  (failures are per-row logged, not script-fatal).

MODULE_NOTE (中): canary 自動晉升一次性命令列工具。預設 dry-run
  預覽；`--apply` 需 env `OPENCLAW_AUTO_PROMOTE_ENABLED=1` 才實際呼叫
  狀態機。輸出：每筆 row 決策表 + 統計。退出碼永遠 0。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

# Allow running from repo root: `python3 helper_scripts/db/canary_promote_runner.py`.
# 從 repo 根執行的 sys.path 補丁。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from program_code.ml_training.canary_promoter import (  # noqa: E402
    CanaryDecision,
    CanaryThresholds,
    auto_promote_eligible_models,
    is_auto_promote_enabled,
)


def _format_table(results) -> str:
    if not results:
        return "(no shadow/promoting rows in registry)"
    cols = ("id", "strategy", "engine", "q", "from", "decision", "→", "reason")
    rows = [cols, ("-" * 4, "-" * 14, "-" * 6, "-" * 4, "-" * 9, "-" * 8, "-" * 4, "-" * 60)]
    for r in results:
        rows.append((
            str(r.row_id),
            r.strategy[:14],
            r.engine_mode[:6],
            r.quantile[:4],
            r.current_status[:9],
            r.decision.value[:8],
            (r.target_status or "")[:4],
            (r.reasons[0] if r.reasons else "")[:60],
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(cols))]
    out = []
    for row in rows:
        out.append("  ".join(c.ljust(w) for c, w in zip(row, widths)))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate canary registry rows + optionally apply state transitions"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) Print decisions without calling transition_canary_status",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply state transitions for non-Hold rows. "
            "Requires env var OPENCLAW_AUTO_PROMOTE_ENABLED=1."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN; default = env (OPENCLAW_DATABASE_URL etc.)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full reasons + metrics for each row",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dry_run = not args.apply
    if args.apply and not is_auto_promote_enabled():
        sys.stderr.write(
            "ERROR: --apply requires OPENCLAW_AUTO_PROMOTE_ENABLED=1 in env. "
            "Default-OFF env gate per draft §Auto-promote cron. "
            "Re-run with the env var set, or use --dry-run.\n"
        )
        return 0  # not script-fatal; caller decides

    thresholds = CanaryThresholds.from_env()
    now = datetime.now(timezone.utc)

    print(f"Canary promote runner — mode={'APPLY' if args.apply else 'DRY-RUN'} ts={now.isoformat()}")
    print(f"Thresholds: {thresholds}")
    print()

    results = auto_promote_eligible_models(
        dsn=args.dsn,
        thresholds=thresholds,
        dry_run=dry_run,
        now=now,
    )

    print(_format_table(results))
    print()

    counts = Counter(r.decision.value for r in results)
    summary = " | ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "(empty)"
    print(f"Summary ({len(results)} rows): {summary}")

    if args.verbose:
        print()
        for r in results:
            print(
                f"  row_id={r.row_id} {r.strategy}/{r.engine_mode}/{r.quantile} "
                f"{r.current_status} → {r.decision.value}"
            )
            for reason in r.reasons:
                print(f"    · {reason}")
            if r.metrics:
                print(f"    metrics: {r.metrics}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
