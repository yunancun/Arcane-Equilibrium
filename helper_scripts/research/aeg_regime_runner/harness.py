#!/usr/bin/env python3
"""AEG-S2 regime label runner CLI.

MODULE_NOTE:
  模塊用途：CLI 編排。讀 FND-2 universe artifact 或顯式 symbols → read-only daily
    close panel → classifier → feature lineage gate → artifact → 可選 ``--write-db`` 寫
    V127。默認 artifact-only，不會寫 DB。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from . import CLASSIFIER_VERSION, feature_rules_digest
    from . import artifact as artifact_mod
    from . import data_loader
    from . import healthcheck
    from .classifier import build_label_rows
    from .lineage import build_feature_lineage_rows, validate_feature_lineage
except ImportError:  # pragma: no cover - 直接執行檔案路徑時
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_regime_runner import CLASSIFIER_VERSION, feature_rules_digest  # type: ignore
    from aeg_regime_runner import artifact as artifact_mod  # type: ignore
    from aeg_regime_runner import data_loader  # type: ignore
    from aeg_regime_runner import healthcheck  # type: ignore
    from aeg_regime_runner.classifier import build_label_rows  # type: ignore
    from aeg_regime_runner.lineage import (  # type: ignore
        build_feature_lineage_rows,
        validate_feature_lineage,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_utc(value: str) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _load_fnd2_symbols_and_mask(fnd2_run_dir: str | None) -> tuple[list[str], dict[str, tuple[Any, Any]], dict[str, Any]]:
    if not fnd2_run_dir:
        return [], {}, {}
    try:
        from aeg_breadth_ladder import universe_artifact as ua_mod
    except ImportError:
        _research = Path(__file__).resolve().parents[1]
        if str(_research) not in sys.path:
            sys.path.insert(0, str(_research))
        from aeg_breadth_ladder import universe_artifact as ua_mod  # type: ignore
    rows, meta = ua_mod.load_fnd2_universe(Path(fnd2_run_dir))
    alive_mask = ua_mod.build_alive_mask(rows)
    symbols = sorted(alive_mask.keys())
    return symbols, alive_mask, meta


def _filter_alive(
    labels: list[dict[str, Any]],
    alive_mask: dict[str, tuple[Any, Any]],
) -> list[dict[str, Any]]:
    if not alive_mask:
        return labels
    out = []
    for row in labels:
        mask = alive_mask.get(str(row.get("symbol")))
        if mask is None:
            continue
        alive_from, alive_to = mask
        signal_ts = row["signal_ts"]
        if alive_from is not None and signal_ts < alive_from:
            continue
        if alive_to is not None and signal_ts > alive_to:
            continue
        out.append(row)
    return out


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        except Exception:
            return ""

    sha = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    dirty = bool(_run(["git", "status", "--porcelain"]))
    return {"git_sha": sha, "git_dirty": dirty}


def _build_summary(
    *,
    run_id: str,
    labels: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
    lineage_ok: bool,
    lineage_reason: str,
    fnd2_meta: dict[str, Any],
    symbol_count_requested: int,
) -> dict[str, Any]:
    anchor_count = sum(1 for r in labels if r.get("symbol") == "BTCUSDT")
    return {
        "run_id": run_id,
        "classifier_version": CLASSIFIER_VERSION,
        "feature_rules_digest": feature_rules_digest(),
        "label_count": len(labels),
        "transition_count": len(transitions),
        "lineage_row_count": len(lineage),
        "lineage_status": "pass" if lineage_ok else lineage_reason,
        "anchor_label_count": anchor_count,
        "symbol_count_requested": symbol_count_requested,
        "symbols_labeled": sorted({str(r.get("symbol")) for r in labels}),
        "regime_counts": healthcheck.regime_counts(labels),
        "fnd2_universe_id": fnd2_meta.get("fnd2_universe_id"),
        "fnd2_run_id": fnd2_meta.get("fnd2_run_id"),
        "source_tables": ["market.klines"],
    }


def run_regime(args: argparse.Namespace) -> dict[str, Any]:
    window_start = _parse_utc(args.window_start)
    window_end = _parse_utc(args.window_end)
    closed_bar_cutoff = _parse_utc(args.cutoff)

    fnd2_symbols, alive_mask, fnd2_meta = _load_fnd2_symbols_and_mask(args.fnd2_run_dir)
    explicit_symbols = data_loader.parse_symbols(args.symbols or "")
    symbols = fnd2_symbols or explicit_symbols
    if not symbols:
        raise ValueError("必須提供 --fnd2-run-dir 或 --symbols")
    if "BTCUSDT" not in symbols:
        symbols = ["BTCUSDT", *symbols]

    closes = data_loader.load_daily_closes(
        symbols,
        window_start=window_start,
        window_end=window_end,
        closed_bar_cutoff=closed_bar_cutoff,
        lookback_days=args.lookback_days,
        dsn=args.dsn,
    )
    labels, transitions = build_label_rows(
        closes,
        run_id=args.run_id,
        window_start=window_start,
        window_end=window_end,
    )
    labels = _filter_alive(labels, alive_mask)
    transitions = [
        t for t in transitions
        if any(
            l["symbol"] == t["symbol"] and l["signal_ts"] == t["transition_ts"]
            for l in labels
        )
    ]
    prov = _git_provenance(_repo_root())
    for row in labels:
        row.update(prov)

    lineage = build_feature_lineage_rows(labels)
    lineage_ok, lineage_reason = validate_feature_lineage(
        lineage,
        allow_insufficient_context=True,
    )
    summary = _build_summary(
        run_id=args.run_id,
        labels=labels,
        transitions=transitions,
        lineage=lineage,
        lineage_ok=lineage_ok,
        lineage_reason=lineage_reason,
        fnd2_meta=fnd2_meta,
        symbol_count_requested=len(symbols),
    )
    hc_status, hc_msg = healthcheck.check_regime_run_summary(summary)
    summary["healthcheck"] = {"status": hc_status, "message": hc_msg}
    if not lineage_ok or hc_status == "FAIL":
        raise RuntimeError(f"AEG regime runner healthcheck failed: {summary}")

    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    written = artifact_mod.write_all(
        labels=labels,
        transitions=transitions,
        lineage=lineage,
        summary=summary,
        run_id=args.run_id,
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        artifact_root=artifact_root,
        session_id=args.session_id,
        created_by_role=args.created_by_role,
    )

    db_written = None
    if args.write_db:
        db_written = _write_db(args, labels=labels, transitions=transitions)

    return {"summary": summary, "written": written, "db_written": db_written}


def _write_db(
    args: argparse.Namespace,
    *,
    labels: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> dict[str, int]:
    import psycopg2  # type: ignore

    srv_root = _repo_root()
    helper_dir = srv_root / "helper_scripts"
    if str(helper_dir) not in sys.path:
        sys.path.insert(0, str(helper_dir))
    from lib.pg_connect import resolve_report_dsn  # type: ignore

    # dual-path import（鏡像本檔頂部既有 pattern，兩種執行模式都通）：package 模式
    # （python3 -m helper_scripts.research.aeg_regime_runner.harness）走 relative；
    # direct-file 模式（python3 harness.py，頂部 fallback 已插 research/ 進 sys.path）
    # 走絕對。舊碼只有絕對形且基於 helper_scripts/ 根（差一層 research）→ package 模式
    # --write-db 必 ModuleNotFoundError；artifact-only 不踩此 import、V127 從未被
    # populate，故 deploy 至今未暴露。
    try:
        from .db_writer import persist_regime_rows  # type: ignore
    except ImportError:  # pragma: no cover — direct-file 執行模式
        from aeg_regime_runner.db_writer import persist_regime_rows  # type: ignore

    dsn = args.dsn or resolve_report_dsn()
    conn = psycopg2.connect(dsn, application_name="aeg_regime_runner_write")
    try:
        with conn:
            return persist_regime_rows(conn, labels=labels, transitions=transitions)
    finally:
        conn.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_regime_runner.harness",
        description="AEG-S2 regime label runner (daily kline → artifact, optional V127 DB write)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--fnd2-run-dir", default=None, dest="fnd2_run_dir")
    p.add_argument("--symbols", default=None, help="diagnostic fallback, comma-separated")
    p.add_argument("--window-start", required=True, dest="window_start")
    p.add_argument("--window-end", required=True, dest="window_end")
    p.add_argument("--cutoff", required=True, help="closed_bar_cutoff_utc ISO8601")
    p.add_argument("--lookback-days", type=int, default=430, dest="lookback_days")
    p.add_argument("--dsn", default=None)
    p.add_argument("--artifact-root", default=None, dest="artifact_root")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    p.add_argument("--write-db", action="store_true", dest="write_db")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = run_regime(args)
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
