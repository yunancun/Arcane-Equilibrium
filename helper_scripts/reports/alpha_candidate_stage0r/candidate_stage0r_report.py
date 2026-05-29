#!/usr/bin/env python3
"""Alpha Candidate Stage 0R Runner — PG 取數 + CLI/IO 層（read-only）。

MODULE_NOTE
模塊用途：candidate_stage0r_runner 的 read-only PG 取數 + argparse + JSON
render IO 層。與 8c metrics.py / report.py 同樣的「純計算層 + IO 編排層」拆分
（純 offline 邏輯在 candidate_stage0r_runner.run_candidates；本檔負責連 PG、
跑 8c SQL、組 config、輸出 JSON）。

主要類/函數：_get_conn / fetch_k_prior / _read_8c_sql / _fetch_a2_panel_rows /
            _apply_k_prior_to_packet / _clean_json / main。
k_prior（QC round 2 blocker）：--k-prior default None → auto-query
            learning.strategy_trial_ledger（mirror 8c fetch_k_prior）；fail-closed
            ——ledger 缺則標 k_prior_source=unavailable 並降保守 verdict，禁 silent
            用 0 餵 DSR（over-PASS bias）；顯式 --k-prior N 才當 override。
依賴：psycopg2（read-only PG）；sibling candidate_stage0r_runner（run_candidates）
      + a2_cascade_adapter（A2CandidateConfig）；A2 復用
      `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`（不改）。
硬邊界（per CLAUDE §四 + AMD §3.2）：read-only PG SELECT；不寫 trading|panel|
      market；不調 Rust；不碰 authorization|lease|paper|mainnet；不改 TOML；
      fail-closed exit code（PG connect fail=2 / query fail=1，propagate 不吞）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

# K_prior query mode（mirror 8c K_PRIOR_MODES）：strict-liquidation 為 A2
# (liquidation_cascade_fade) 自身 family，default 採 undercount-safe strict 口徑。
K_PRIOR_MODES = ("strict-liquidation", "liquidation-related", "all")

try:
    from .candidate_stage0r_runner import run_candidates  # type: ignore
    from .a2_cascade_adapter import A2CandidateConfig  # type: ignore
except ImportError:
    _HERE = Path(__file__).resolve().parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from candidate_stage0r_runner import run_candidates  # type: ignore
    from a2_cascade_adapter import A2CandidateConfig  # type: ignore


def _repo_root() -> Path:
    """解析 repo 根目錄，禁硬編碼路徑（feedback_cross_platform.md 跨平台原則）。"""
    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if base:
        return Path(base)
    # helper_scripts/reports/alpha_candidate_stage0r/<this> → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def _get_conn():
    """連 PG read-only。mirror 8b/8c report wrapper（禁硬編碼 hostname）。"""
    import psycopg2  # type: ignore

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    conn = psycopg2.connect(dsn, application_name="openclaw_alpha_candidate_stage0r")
    with conn.cursor() as cur:
        cur.execute(
            "SET statement_timeout = %s",
            (int(os.environ.get("OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS", "180000")),),
        )
    return conn


def fetch_k_prior(conn, *, mode: str) -> tuple[int, dict[str, object]]:
    """從 learning.strategy_trial_ledger 取 K_prior（mirror 8c fetch_k_prior L185-243）。

    為什麼：DSR `sr_benchmark = √(2 ln K_total)`；K_total = K_prior + K_new。
    K_prior 嚴重低估 → benchmark 偏低 → DSR 膨脹 → over-PASS bias（= 8c E2
    round 1 HIGH-3 + 本檔 QC round 2 blocker；違 CLAUDE §二 RP6 uncertainty→
    conservative）。default 不可 silent 用 0；必須真實 query ledger。

    回 (k_prior, meta)。meta.available=False 代表 ledger 表不存在（infra gap）→
    caller fail-closed 標 k_prior_source=unavailable 並降保守 verdict（不可把
    silent 0 當權威 prior 餵給 DSR 重算）。query 連線錯誤不在此吞，由 caller
    既有 fail-closed exit path propagate。
    """
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
        if mode == "strict-liquidation":
            # A2 自身 family undercount-safe 口徑：strategy/family/candidate_key
            # 任一含 'liquidation' 或 evidence.alpha_source_id =
            # 'liquidation_cascade_fade'（A2 SSOT alpha_source_id）。
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name ILIKE '%%liquidation%%'
                OR trial_family ILIKE '%%liquidation%%'
                OR candidate_key ILIKE '%%liquidation%%'
                OR evidence->>'alpha_source_id' = 'liquidation_cascade_fade'
            )
            """
        elif mode == "liquidation-related":
            # 寬鬆 mode：candidate_key/strategy/family 任一含 liquid 前綴。
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name ILIKE '%%liquid%%'
                OR trial_family ILIKE '%%liquid%%'
                OR candidate_key ILIKE '%%liquid%%'
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


def _read_8c_sql() -> str:
    """讀 W-AUDIT-8c features SQL（A2 復用，不複製、不改）。

    為什麼讀檔而非 inline：spec v2 §2 + §8.4 #1 — 不改 8c SQL 結構；A2 沿用
    8c per-event leak-free 查詢，consumer 不複製 SQL（merge 衝突最小化）。
    """
    path = (
        _repo_root() / "sql" / "queries"
        / "w_audit_8c_liquidation_cluster_stage0r_features.sql"
    )
    return path.read_text(encoding="utf-8")


def _fetch_a2_panel_rows(
    conn, *, window_days: int, cohort: Sequence[str], cost_bps: float, horizon_min: int,
) -> tuple[list[dict[str, Any]], int]:
    """執行 8c SQL（A2 cohort + 最寬鬆 pre-filter）+ 查 raw_buckets count。

    回 (panel_rows, total_bucket_count)。
    SQL pre-filter 用最寬鬆值（candidate per-symbol threshold 在 adapter 層 tighten）；
    total_bucket_count = CTE 1 raw_buckets count（both-direction floor 分母，
    避免 64× anti-conservative bias）。
    """
    sql = _read_8c_sql()
    # 8c SQL 最寬鬆 pre-filter（adapter 再 tighten per-symbol threshold）。
    params = {
        "window_days": window_days,
        "symbols": list(cohort),
        "k_event_floor": 1,
        "n_usd_floor": 1.0,
        "m_dominant_floor": 1,
        "side_dominance_floor": 0.0,
        "cluster_notional_floor_usd": 0.0,
        "notional_pct_floor": 0.0,
        "quiet_window_sec": 0,
        "horizon_min": horizon_min,
        "cost_bps": cost_bps,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        raw_rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = dict(zip(columns, raw))
        # bucket_end_ts (timestamptz) → bucket_end_ts_ms (int ms)（mirror 8c CRIT-5）。
        bet = row.get("bucket_end_ts")
        if bet is not None and hasattr(bet, "timestamp"):
            row["bucket_end_ts_ms"] = int(bet.timestamp() * 1000)
        elif isinstance(bet, (int, float)):
            row["bucket_end_ts_ms"] = int(bet)
        else:
            row["bucket_end_ts_ms"] = None
        out.append(row)

    # raw_buckets count（CTE 1 等價：per-symbol per-5m-bucket，不論是否 trigger）。
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)::int FROM (
                SELECT symbol, (floor(extract(epoch FROM ts) / 300.0))::bigint * 300 AS b
                FROM market.liquidations
                WHERE ts >= now() - (%(window_days)s::int * INTERVAL '1 day')
                  AND symbol = ANY(%(symbols)s::text[])
                GROUP BY symbol, b
            ) q
            """,
            {"window_days": window_days, "symbols": list(cohort)},
        )
        row = cur.fetchone()
        total_bucket_count = int(row[0]) if row and row[0] is not None else 0
    return out, total_bucket_count


def _apply_k_prior_to_packet(
    packet: dict[str, Any],
    *,
    k_prior: int,
    k_prior_source: str,
    k_prior_meta: dict[str, Any],
    mode: str,
) -> None:
    """report-layer：把 k_prior provenance 寫進 packet + ledger 缺時降保守 verdict。

    為什麼 fail-closed：DSR benchmark = √(2 ln K_total)，K_total = K_prior +
    K_new。k_prior 未知時 adapter 只能用佔位 0，benchmark 偏低 → DSR 膨脹 →
    over-PASS（QC round 2 blocker）。若 ledger 不可達(unavailable)，明文標
    k_prior_source=unavailable 並把任何 stage0_ready 降到 observe_more（CLAUDE
    §二 RP6 uncertainty→conservative）——k_prior 未知是 evidence-infra gap，
    非 signal failure，故降到 observe_more 而非 reject/draft_only。

    只動 packet dict（IO 層）；不改 runner/adapter k_total math。

    附帶（QC non-blocking note）：加 pbo_semantics key，標明 time-block PBO 是
    level-test generalization proxy 非 Bailey-LdP CSCV calibrated 機率，避免未來
    window 拉長時誤讀。
    """
    packet["k_prior"] = int(k_prior)
    packet["k_prior_source"] = k_prior_source
    packet["k_prior_mode"] = mode
    packet["k_prior_meta"] = k_prior_meta
    # PBO 語意標註（time-block CSCV proxy 非 Bailey-LdP 校準機率）。
    packet["pbo_semantics"] = (
        "day_block_generalization_proxy_not_bailey_cscv"
    )

    if k_prior_source != "unavailable":
        return

    # ── fail-closed 降保守：ledger 不可達 → k_prior 未知 → 禁 stage0_ready ──
    downgrade_reason = (
        "k_prior_source=unavailable（learning.strategy_trial_ledger 不可達）→ "
        "DSR multiple-comparison benchmark 無法可靠估計 → fail-closed 降保守"
        "（RP6 uncertainty→conservative）；非 signal failure，需補 ledger 後重跑"
    )
    candidates = packet.get("candidates")
    a2 = candidates.get("A2_liquidation_cascade_fade") if isinstance(candidates, dict) else None
    if isinstance(a2, dict) and a2.get("verdict") == "stage0_ready":
        a2["verdict"] = "observe_more"
        a2["eligible_for_demo_canary"] = False
        a2["stage0_ready_candidate"] = False
        reasons = a2.get("fail_reasons")
        if not isinstance(reasons, list):
            reasons = []
        reasons.append("k_prior_unavailable_conservative_downgrade")
        a2["fail_reasons"] = reasons
        a2["k_prior_downgrade"] = downgrade_reason
    if packet.get("verdict") == "stage0_ready":
        packet["verdict"] = "observe_more"
        packet["stage0_ready"] = False
        packet["verdict_basis"] = downgrade_reason


def _clean_json(value):
    """遞迴清理 NaN/Inf → None（RFC 8259 safe）；mirror 8c。"""
    if isinstance(value, dict):
        return {k: _clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(v) for v in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Alpha Tournament Candidate Stage 0R Runner（A1 stub draft_only / "
                    "A2 functional via 8c adapter；read-only offline）",
    )
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument(
        "--cohort", type=str, default="BTCUSDT,ETHUSDT",
        help="candidate cohort（A2 2-symbol；default BTC/ETH）",
    )
    parser.add_argument("--cost-bps", type=float, default=12.0)
    parser.add_argument(
        "--horizon-min", type=int, default=60,
        help="A2 fixed-horizon proxy（default 60m = A2 max_hold time-stop）",
    )
    parser.add_argument(
        "--btc-threshold-usd", type=float, default=500_000.0,
        help="A2 BTC dominant_notional_5m threshold（A2 spec §1.3）",
    )
    parser.add_argument(
        "--eth-threshold-usd", type=float, default=300_000.0,
        help="A2 ETH dominant_notional_5m threshold（A2 spec §1.3）",
    )
    parser.add_argument(
        "--k-prior", type=int, default=None,
        help="DSR k_total 的 k_prior 手動 override（spec v2 §4.3）；不傳則從 "
             "learning.strategy_trial_ledger auto-query（fail-closed：ledger 缺則"
             "標 unavailable + 降保守 verdict，不 silent 用 0）",
    )
    parser.add_argument(
        "--k-prior-mode", choices=K_PRIOR_MODES, default="strict-liquidation",
        help="K_prior auto-query mode（mirror 8c；default strict-liquidation "
             "undercount-safe，僅在 --k-prior 未顯式傳入時生效）",
    )
    parser.add_argument("--bootstrap-iters", type=int, default=400)
    parser.add_argument("--rng-seed", type=int, default=20260529)
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument(
        "--out", type=str, default=None,
        help="JSON 輸出路徑；空則 stdout",
    )
    args = parser.parse_args(argv)

    cohort = tuple(s.strip().upper() for s in args.cohort.split(",") if s.strip())

    # === PG 取數（read-only；fail-closed exit code mirror 8b/8c）===
    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] PG 連線失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        # QC round 2 blocker fix：k_prior 不可 silent 用 0。顯式 --k-prior 才
        # override；否則 auto-query ledger（mirror 8c）。ledger query 連線錯誤
        # 由本 try 既有 fail-closed exit (return 1) propagate，不吞。
        if args.k_prior is not None:
            k_prior = int(args.k_prior)
            k_prior_source = "manual"
            k_prior_meta: dict[str, Any] = {
                "mode": "manual",
                "source": "--k-prior",
                "available": True,
                "where": None,
            }
        else:
            k_prior, k_prior_meta = fetch_k_prior(conn, mode=args.k_prior_mode)
            # ledger 表存在=ledger；不存在(available=False)=unavailable infra gap。
            k_prior_source = "ledger" if k_prior_meta.get("available") else "unavailable"

        a2_rows, a2_total_buckets = _fetch_a2_panel_rows(
            conn, window_days=args.window_days, cohort=cohort,
            cost_bps=args.cost_bps, horizon_min=args.horizon_min,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] Stage 0R query 失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    cfg = A2CandidateConfig(
        cohort=cohort,
        per_symbol_threshold={
            "BTCUSDT": args.btc_threshold_usd,
            "ETHUSDT": args.eth_threshold_usd,
        },
        horizon_min=args.horizon_min,
        cost_bps=args.cost_bps,
        # ledger 缺時 adapter math 仍需 int；此處傳 0 僅為計算佔位，但下游
        # _apply_k_prior_to_packet 會把 packet 標 unavailable 並降保守 verdict，
        # 確保「k_prior 未知」不會被當權威 prior 產出 stage0_ready（fail-closed）。
        k_prior=int(k_prior),
    )

    packet = run_candidates(
        a2_rows,
        a2_total_bucket_count=a2_total_buckets,
        window_days=args.window_days,
        a2_cfg=cfg,
        bootstrap_iters=args.bootstrap_iters,
        rng_seed=args.rng_seed,
    )
    # report-layer：把 k_prior provenance 寫進 packet + ledger 缺時降保守 verdict。
    _apply_k_prior_to_packet(
        packet, k_prior=k_prior, k_prior_source=k_prior_source,
        k_prior_meta=k_prior_meta, mode=args.k_prior_mode,
    )
    cleaned = _clean_json(packet)
    text = json.dumps(cleaned, ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] packet written: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
