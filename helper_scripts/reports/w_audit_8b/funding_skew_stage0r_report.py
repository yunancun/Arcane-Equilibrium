#!/usr/bin/env python3
"""Read-only Stage 0R packet for W-AUDIT-8b Funding Skew Directional."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:
    from .funding_skew_stage0r_metrics import compute_stage0r, compute_stage0r_sweep
except ImportError:
    from funding_skew_stage0r_metrics import compute_stage0r, compute_stage0r_sweep  # type: ignore


DEFAULT_WINDOW_DAYS = 7
DEFAULT_COST_BPS = 12.0
DEFAULT_Z_CELLS = "1.0,1.2,1.5,2.0"
K_PRIOR_MODES = ("funding-related", "strict-funding-skew", "all")


def _repo_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[3]


def _get_conn():
    import psycopg2  # type: ignore

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    conn = psycopg2.connect(dsn, application_name="openclaw_w_audit_8b_stage0r")
    with conn.cursor() as cur:
        cur.execute(
            "SET statement_timeout = %s",
            (int(os.environ.get("OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS", "120000")),),
        )
    return conn


def _read_sql() -> str:
    path = _repo_root() / "sql" / "queries" / "w_audit_8b_funding_skew_stage0r_features.sql"
    return path.read_text(encoding="utf-8")


def _parse_symbols(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


def _parse_z_cells(raw: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError("--z-cells must contain at least one numeric threshold")
    return values


def fetch_panel_symbols(conn, *, window_days: int) -> tuple[str, ...]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH now_ms AS (SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS ms),
            f AS (
                SELECT symbol
                FROM panel.funding_rates_panel, now_ms
                WHERE snapshot_ts_ms >= now_ms.ms - (%s::int * 86400000)::bigint
                GROUP BY symbol
            ),
            oi AS (
                SELECT symbol
                FROM panel.oi_delta_panel, now_ms
                WHERE snapshot_ts_ms >= now_ms.ms - (%s::int * 86400000)::bigint
                GROUP BY symbol
            )
            SELECT f.symbol
            FROM f JOIN oi USING (symbol)
            ORDER BY f.symbol
            """,
            (window_days, window_days),
        )
        return tuple(str(row[0]) for row in cur.fetchall())


def fetch_k_prior(conn, *, mode: str) -> tuple[int, dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('learning.strategy_trial_ledger') IS NOT NULL")
        row = cur.fetchone()
        if not row or not row[0]:
            return 0, {
                "mode": mode,
                "source": "learning.strategy_trial_ledger",
                "available": False,
                "where": None,
            }
        if mode == "strict-funding-skew":
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name = 'funding_skew_directional'
                OR trial_family = 'funding_skew_directional'
                OR candidate_key ILIKE 'funding_skew_directional%%'
            )
            """
        elif mode == "funding-related":
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name ILIKE 'funding%%'
                OR trial_family ILIKE 'funding%%'
                OR candidate_key ILIKE '%%funding%%'
            )
            """
        elif mode == "all":
            where_sql = "candidate_key IS NOT NULL"
        else:
            raise ValueError(f"unsupported K_prior mode: {mode}")
        cur.execute(
            f"""
            SELECT count(DISTINCT candidate_key)::int
            FROM learning.strategy_trial_ledger
            WHERE {where_sql}
            """
        )
        prior = cur.fetchone()
        return int(prior[0] or 0), {
            "mode": mode,
            "source": "learning.strategy_trial_ledger",
            "available": True,
            "where": " ".join(where_sql.split()),
            "count_distinct": "candidate_key",
        }


def fetch_feature_rows(conn, *, window_days: int, symbols: Sequence[str]) -> list[dict]:
    sql = _read_sql()
    with conn.cursor() as cur:
        cur.execute(sql, {"window_days": window_days, "symbols": list(symbols)})
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _clean_json(value):
    if isinstance(value, dict):
        return {k: _clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_json(v) for v in value]
    if isinstance(value, tuple):
        return [_clean_json(v) for v in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return value


def render_summary(packet: dict) -> str:
    pooled = packet.get("pooled_primary") or {}
    best = packet.get("best_primary_cell") or {}
    panel = packet.get("panel_metadata") or {}
    settlement = packet.get("settlement_window") or {}
    plateau = packet.get("plateau_check") or {}
    baseline = packet.get("baseline_lift") or {}
    cost_model = packet.get("execution_cost_model") or {}
    reasons = packet.get("eligibility_fail_reasons") or []
    lines = [
        "# W-AUDIT-8b Funding Skew Stage 0R Packet",
        "",
        f"generated_at_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"strategy_variant: {packet.get('strategy_variant')}",
        f"alpha_source_id: {packet.get('alpha_source_id')}",
        f"funding_attribution_mode: {packet.get('funding_attribution_mode')}",
        f"source_mode: {packet.get('source_mode')}",
        f"symbols: {packet.get('symbol_count')} rows: {packet.get('row_count')}",
        (
            f"K_prior: {packet.get('k_prior')} K_new: {packet.get('k_new')} "
            f"K_new_actual: {packet.get('k_new_actual')} K_total: {packet.get('k_total')}"
        ),
        f"K_prior_semantic: {json.dumps(packet.get('k_prior_semantic'), sort_keys=True)}",
        "",
        "## Verdict",
        "",
        f"eligible_for_demo_canary: {str(packet.get('eligible_for_demo_canary')).lower()}",
    ]
    if reasons:
        lines.append("fail_reasons: " + "; ".join(str(r) for r in reasons))
    lines.extend(
        [
            "",
            "## Pooled Primary Horizon",
            "",
            f"n: {pooled.get('n')} n_eff: {pooled.get('n_eff')}",
            f"avg_net_bps: {pooled.get('avg_net_bps')}",
            f"PSR(0): {pooled.get('psr_0')} DSR: {pooled.get('dsr')} PBO: {packet.get('pbo')}",
            f"bootstrap_ci_95_60m: {pooled.get('bootstrap_ci_95_60m')}",
            f"bootstrap_ci_95_8h: {pooled.get('bootstrap_ci_95_8h')}",
            "",
            "## Contract Fields",
            "",
            f"panel_metadata: {json.dumps(_clean_json(panel), sort_keys=True)}",
            f"settlement_window: {json.dumps(_clean_json(settlement), sort_keys=True)}",
            f"plateau_check: {json.dumps(_clean_json(plateau), sort_keys=True)}",
            f"baseline_lift: {json.dumps(_clean_json(baseline), sort_keys=True)}",
            f"execution_cost_model: {json.dumps(_clean_json(cost_model), sort_keys=True)}",
            "",
            "## Best Primary Cell",
            "",
            json.dumps(_clean_json(best), indent=2, sort_keys=True),
        ]
    )
    sweep_meta = packet.get("sweep_meta")
    if isinstance(sweep_meta, dict):
        sweep_per_z = packet.get("sweep_per_z_cell") or {}
        lines.extend(
            [
                "",
                "## Sweep v0.3",
                "",
                f"sweep_meta: {json.dumps(_clean_json(sweep_meta), sort_keys=True)}",
                f"sweep_per_z_cell_keys: {list(sweep_per_z.keys()) if isinstance(sweep_per_z, dict) else []}",
                f"sweep_per_symbol_rows: {len(packet.get('sweep_per_symbol') or [])}",
                (
                    "best_primary_cell_per_z_branch_rows: "
                    f"{len(packet.get('best_primary_cell_per_z_branch') or [])}"
                ),
                f"sweep_cross_z_comparison_rows: {len(packet.get('sweep_cross_z_comparison') or [])}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="W-AUDIT-8b Funding Skew Stage 0R read-only packet generator"
    )
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--symbols", type=str, default=None)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--k-prior", type=int, default=None)
    parser.add_argument(
        "--k-prior-mode",
        choices=K_PRIOR_MODES,
        default="strict-funding-skew",
        help="how to estimate comparable prior trials when --k-prior is not set",
    )
    parser.add_argument("--out", type=str, default=None, help="optional output path")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="enable v0.3 z-cell sensitivity sweep mode",
    )
    parser.add_argument(
        "--z-cells",
        type=str,
        default=DEFAULT_Z_CELLS,
        help=f"comma-separated z thresholds for --sweep (default: {DEFAULT_Z_CELLS})",
    )
    args = parser.parse_args()

    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {exc}", file=sys.stderr)
        return 2

    try:
        symbols = _parse_symbols(args.symbols) or fetch_panel_symbols(conn, window_days=args.window_days)
        if not symbols:
            print("[FATAL] no overlapping funding/OI panel symbols", file=sys.stderr)
            return 1
        if args.k_prior is not None:
            k_prior = args.k_prior
            k_prior_meta = {
                "mode": "manual",
                "source": "--k-prior",
                "available": True,
                "where": None,
            }
        else:
            k_prior, k_prior_meta = fetch_k_prior(conn, mode=args.k_prior_mode)
        rows = fetch_feature_rows(conn, window_days=args.window_days, symbols=symbols)
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] Stage 0R query failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    try:
        if args.sweep:
            packet = compute_stage0r_sweep(
                rows,
                k_prior=k_prior,
                cost_bps=args.cost_bps,
                z_cells=_parse_z_cells(args.z_cells),
            )
        else:
            packet = compute_stage0r(rows, k_prior=k_prior, cost_bps=args.cost_bps)
    except ValueError as exc:
        print(f"[FATAL] invalid Stage 0R parameters: {exc}", file=sys.stderr)
        return 2
    packet["symbols"] = list(symbols)
    packet["window_days"] = args.window_days
    packet["k_prior_semantic"] = k_prior_meta

    rendered = (
        render_summary(packet)
        if args.format == "markdown"
        else json.dumps(_clean_json(packet), indent=2, sort_keys=True)
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
