"""STEP 0 — 資料覆蓋誠實檢查（唯讀，研究分析）。

MODULE_NOTE:
  模塊用途：在跑 axis (a)/(d) 之前，誠實量測 PG 資料覆蓋，決定哪些測試可跑、
    哪些受限。輸出 JSON 供主分析腳本與報告引用。查詢項目：
    (i)  market.klines 各 timeframe 的日期跨度 + symbol 數。
    (ii) demo/live_demo fills 的跨度 + 筆數 + per-strategy round-trip 摘要
         （直接複用 residual_alpha_producer_db.load_round_trips → realized_edge_stats
         的 FIFO 配對，net_pnl_bps 已扣費帶方向）。
    (iii) residual_alpha_producer 是否可跑（import 探測）。
    (iv) 5 個歷史崩盤日是否有 kline 覆蓋：2020-03-12 / 2021-05-19 /
         2022-05-09(LUNA) / 2022-11-08(FTX) / 2024-08-05。
  硬邊界（研究紅線）：
    - PG **唯讀**：conn.set_session(readonly=True)，只 SELECT，絕不寫 production 表。
    - 不碰 runtime / order / risk / auth；不修 production engine 代碼。
    - 缺資料誠實標記，不偽造覆蓋。
  依賴：psycopg2（延遲 import）；複用 ml_training.residual_alpha_producer_db。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

# 把 srv root 與 program_code 上 path，供複用既有 producer / edge-stats。
# 為什麼用 env + 向上搜尋而非固定 parents[N]：本腳本可能被 scp 到 /tmp 直跑（runtime），
# 也可能就地在 repo 內跑，固定 parents 索引會 IndexError；向上找含 program_code 的目錄
# 才跨平台穩健（不硬編碼 user path，符 §六）。
def _resolve_srv_root() -> Path:
    env = os.environ.get("OPENCLAW_SRV_ROOT", "").strip()
    if env and (Path(env) / "program_code").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for cand in [here, *here.parents]:
        if (cand / "program_code").is_dir():
            return cand
    # fallback：runtime 已知 repo 根（仍經 env 優先，不違跨平台紅線）。
    cwd = Path.cwd()
    if (cwd / "program_code").is_dir():
        return cwd
    raise SystemExit("找不到 srv root（含 program_code 的目錄）；請設 OPENCLAW_SRV_ROOT")


_SRV_ROOT = _resolve_srv_root()
for _p in (str(_SRV_ROOT), str(_SRV_ROOT / "helper_scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 5 個歷史崩盤日（UTC date）。
CRASH_DATES = [
    "2020-03-12",  # COVID 黑色星期四
    "2021-05-19",  # 519 大跌
    "2022-05-09",  # LUNA/UST 脫鉤崩盤
    "2022-11-08",  # FTX 崩盤
    "2024-08-05",  # 日圓 carry unwind / 全球避險
]


def _connect():
    """連 PG（唯讀，fail-closed）。DSN 取 OPENCLAW_DATABASE_URL（runtime secret）。"""
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPENCLAW_DATABASE_URL 未設定（需從 runtime_secrets 注入）")
    conn = psycopg2.connect(dsn, application_name="beta_decomp_step0")
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (180000,))
    return conn


def kline_coverage(conn) -> dict:
    """各 timeframe 的日期跨度 + symbol 數 + 行數。"""
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT timeframe,
                   count(*) AS n_rows,
                   count(DISTINCT symbol) AS n_symbols,
                   min(ts)::date AS min_d,
                   max(ts)::date AS max_d
            FROM market.klines
            GROUP BY timeframe
            ORDER BY timeframe
            """
        )
        for tf, n_rows, n_sym, mn, mx in cur.fetchall():
            out[tf] = {
                "n_rows": int(n_rows),
                "n_symbols": int(n_sym),
                "min_date": str(mn),
                "max_date": str(mx),
            }
    return out


def fills_coverage(conn) -> dict:
    """demo/live_demo fills 的跨度 + 筆數 + per-strategy 摘要。"""
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT engine_mode, count(*) AS n, min(ts)::date AS mn, max(ts)::date AS mx
            FROM trading.fills
            WHERE engine_mode IN ('demo', 'live_demo')
            GROUP BY engine_mode
            ORDER BY engine_mode
            """
        )
        out["by_engine_mode"] = {
            em: {"n_fills": int(n), "min_date": str(mn), "max_date": str(mx)}
            for em, n, mn, mx in cur.fetchall()
        }
        # per-strategy fill 計數（demo+live_demo），給 round-trip 配對前的粗覽。
        cur.execute(
            """
            SELECT COALESCE(strategy_name, 'unknown') AS strat,
                   count(*) AS n,
                   min(ts)::date AS mn, max(ts)::date AS mx
            FROM trading.fills
            WHERE engine_mode IN ('demo', 'live_demo')
              AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%%')
            GROUP BY COALESCE(strategy_name, 'unknown')
            ORDER BY count(*) DESC
            LIMIT 40
            """
        )
        out["by_strategy_fill_count"] = [
            {"strategy": s, "n_fills": int(n), "min_date": str(mn), "max_date": str(mx)}
            for s, n, mn, mx in cur.fetchall()
        ]
    return out


def roundtrip_summary(conn) -> dict:
    """複用既有 FIFO 配對統計 round-trips（demo scope），per-strategy 摘要。"""
    try:
        from program_code.ml_training.residual_alpha_producer_db import load_round_trips
        from program_code.ml_training import realized_edge_stats as res
    except ModuleNotFoundError:
        from ml_training.residual_alpha_producer_db import load_round_trips  # type: ignore
        from ml_training import realized_edge_stats as res  # type: ignore

    # 先抓 demo scope 全 fills 配對出的 round-trips 的 entry strategy 列表。
    from psycopg2.extras import RealDictCursor

    since = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    modes = res._engine_mode_scope("demo")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(res._FILLS_QUERY, {"since": since, "engine_modes": modes})
        fills = [dict(r) for r in cur.fetchall()]
    rts = list(res._pair_round_trips(fills))
    by_strat: dict[str, list] = {}
    for rec in rts:
        if rec.exit_ts is None:
            continue
        by_strat.setdefault(rec.strategy_name, []).append(rec)

    summary = []
    for strat, recs in sorted(by_strat.items(), key=lambda kv: -len(kv[1])):
        entry_ts = [r.entry_ts for r in recs]
        net = [r.net_pnl_bps for r in recs if r.net_pnl_bps is not None]
        summary.append(
            {
                "strategy": strat,
                "n_round_trips": len(recs),
                "min_entry": str(min(entry_ts).date()) if entry_ts else None,
                "max_entry": str(max(entry_ts).date()) if entry_ts else None,
                "mean_net_bps": (sum(net) / len(net)) if net else None,
                "n_symbols": len({r.symbol for r in recs}),
            }
        )
    return {
        "engine_mode_scope": modes,
        "total_round_trips": sum(len(v) for v in by_strat.values()),
        "by_strategy": summary,
        "since": str(since.date()),
    }


def residual_producer_runnable() -> dict:
    """探測 residual_alpha_producer / DB adapter 是否可 import + 關鍵函數存在。"""
    info: dict = {"path_checked": []}
    try:
        from program_code.ml_training import residual_alpha_producer_db as rdb
        from program_code.learning_engine import residual_alpha_producer as r1
    except ModuleNotFoundError:
        try:
            from ml_training import residual_alpha_producer_db as rdb  # type: ignore
            from learning_engine import residual_alpha_producer as r1  # type: ignore
        except ModuleNotFoundError as exc:
            return {"importable": False, "error": str(exc)}
    info["importable"] = True
    info["db_adapter"] = rdb.__file__
    info["r1_core"] = r1.__file__
    info["has_build_bucketed_residual_report"] = hasattr(rdb, "build_bucketed_residual_report")
    info["has_bucket_round_trips_by_exit"] = hasattr(rdb, "bucket_round_trips_by_exit")
    info["has_build_residual_alpha_report"] = hasattr(r1, "build_residual_alpha_report")
    return info


def crash_date_coverage(conn) -> dict:
    """5 個歷史崩盤日的 kline 覆蓋（哪些 timeframe / symbol 數有資料）。"""
    out: dict = {}
    with conn.cursor() as cur:
        for d in CRASH_DATES:
            day = dt.date.fromisoformat(d)
            nxt = day + dt.timedelta(days=1)
            cur.execute(
                """
                SELECT timeframe, count(*) AS n, count(DISTINCT symbol) AS nsym
                FROM market.klines
                WHERE ts >= %s AND ts < %s
                GROUP BY timeframe
                ORDER BY timeframe
                """,
                (day, nxt),
            )
            rows = cur.fetchall()
            out[d] = {
                "covered": bool(rows),
                "by_timeframe": {
                    tf: {"n_rows": int(n), "n_symbols": int(nsym)} for tf, n, nsym in rows
                },
            }
    return out


def main() -> None:
    conn = _connect()
    try:
        report = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "kline_coverage_by_timeframe": kline_coverage(conn),
            "fills_coverage": fills_coverage(conn),
            "roundtrip_summary": roundtrip_summary(conn),
            "crash_date_kline_coverage": crash_date_coverage(conn),
        }
    finally:
        conn.close()
    # residual producer 探測無需 DB。
    report["residual_producer"] = residual_producer_runnable()

    out_path = os.environ.get("STEP0_OUT", "/tmp/openclaw/beta_decomp/step0_coverage.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
