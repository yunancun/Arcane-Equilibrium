#!/usr/bin/env python3
"""每日 taker 滑點分位 artifact 生產(P1-2b)。

MODULE_NOTE:
  模塊用途：從 read-only PG ``trading.fills`` 量測 90d taker |slippage_bps| 的
    per-symbol 與 global(ROLLUP) 分位(q50/q75/q90)+ 期望/尾部統計
    (mean_abs=E[|slip|]、mean_signed 透明對照、cvar90=E[|slip| | |slip|≥q90])，
    落成 slippage_quantiles_latest.json，供 outcome_writer 的保守成本模型與
    outcome_review 的 E[cost] 主判/CVaR90 尾部欄離線讀取(lane 純函數性:
    writer 不直連 PG)。mean_abs/cvar90 為 QC 預註冊 §6.1/§6.2 凍結成分
    (docs/research/2026-07-10--counterfactual_rerun_preregistration.md)。
  主要函數：build_slippage_quantile_artifact(純函數，可用 fixture 行測試)、
    fetch_taker_slippage_rows(PG SELECT-only)、main(CLI)。
  依賴：helper_scripts.lib.pg_connect(read-only 連線)；OPENCLAW_DATA_DIR 決定輸出路徑。
  硬邊界：PG 全程 SELECT-only(set_session readonly);不寫 PG、不呼叫 Bybit、不送單、
    不改 runtime config;artifact 為唯一寫入面。

QC spec 正本:docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-04--evidence_
methodology_redesign_p12_p27_p28_f7.md §2.2 + addendum §C(SQL 內嵌下方)。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    utc_now as _utc_now,
)


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


# v2:加 mean_abs/mean_signed/cvar90 欄(預註冊 §6 成本雙軌成分);純增欄,
# 舊消費端(cost_model.load_slippage_quantiles 讀 q75)不驗版、不受影響。
ARTIFACT_SCHEMA_VERSION = "cost_gate_slippage_quantile_artifact_v2"
ARTIFACT_FILENAME = "slippage_quantiles_latest.json"
# thin_sample 純觀測標記:n<100 分位估計自身噪音大(addendum §C:全表僅 178 行)。
# 不加新乘數旋鈕——SM=1.3 已覆蓋估計不確定性,避免死參數。
THIN_SAMPLE_THRESHOLD = 100
DEFAULT_WINDOW_DAYS = 90

# addendum §C 內嵌 SQL(分位 artifact 生產必須用本查詢)。ROLLUP 產 per-symbol +
# global(symbol IS NULL)兩層;engine_mode/liquidity_role/window 過濾與 spec 一致。
# 預註冊 §6 擴欄:mean_abs=E[|slip|](§6.1 主判成分)、mean_signed(透明對照)、
# cvar90=E[|slip| | |slip|≥q90](§6.2 尾部成分;相關子查詢按 ROLLUP 層對應
# 全體/單 symbol 樣本,q90 為 NULL 時自然回傳 NULL → 消費端 fallback q90)。
SLIPPAGE_QUANTILE_SQL = """
WITH t AS (
  SELECT symbol, abs(slippage_bps) AS s, slippage_bps AS s_signed
  FROM trading.fills
  WHERE engine_mode IN ('demo','live_demo') AND liquidity_role='taker'
    AND ts > now() - make_interval(days => %(window_days)s) AND slippage_bps IS NOT NULL),
q AS (
  SELECT symbol, count(*) AS n,
         avg(s) AS mean_abs,
         avg(s_signed) AS mean_signed,
         percentile_cont(0.5)  WITHIN GROUP (ORDER BY s) AS q50,
         percentile_cont(0.75) WITHIN GROUP (ORDER BY s) AS q75,
         percentile_cont(0.9)  WITHIN GROUP (ORDER BY s) AS q90
  FROM t GROUP BY ROLLUP(symbol))
SELECT q.symbol, q.n, q.mean_abs, q.mean_signed, q.q50, q.q75, q.q90,
       (SELECT avg(t2.s) FROM t t2
        WHERE (q.symbol IS NULL OR t2.symbol = q.symbol)
          AND t2.s >= q.q90) AS cvar90
FROM q
"""


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_slippage_quantile_artifact(
    rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """把 ROLLUP 分位查詢結果投影為 artifact payload(純函數)。

    rows: 每列 {symbol(None=ROLLUP global), n, mean_abs, mean_signed,
    q50, q75, q90, cvar90}。outcome_writer 的 load_slippage_quantiles 讀本
    payload:{asof, symbols[], global};outcome_review 的 E[cost] 主判讀
    mean_abs、尾部欄讀 cvar90(缺失 fallback q90)。
    """
    asof = (now_utc or _utc_now()).astimezone(dt.timezone.utc).isoformat()
    symbols: list[dict[str, Any]] = []
    global_block: dict[str, Any] | None = None
    for row in rows:
        symbol = row.get("symbol")
        n = _int(row.get("n"))
        entry = {
            "n": n,
            "mean_abs": _float(row.get("mean_abs")),
            "mean_signed": _float(row.get("mean_signed")),
            "q50": _float(row.get("q50")),
            "q75": _float(row.get("q75")),
            "q90": _float(row.get("q90")),
            "cvar90": _float(row.get("cvar90")),
            "thin_sample": n < THIN_SAMPLE_THRESHOLD,
        }
        if symbol is None or str(symbol).strip() == "":
            # ROLLUP 的 grand total 行(symbol IS NULL)= global。
            global_block = entry
        else:
            symbols.append({"symbol": str(symbol).strip().upper(), **entry})
    symbols.sort(key=lambda item: item["symbol"])
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "asof": asof,
        "window_days": window_days,
        "n_total_global": global_block.get("n") if global_block else 0,
        "symbols": symbols,
        "global": global_block
        or {
            "n": 0,
            "mean_abs": None,
            "mean_signed": None,
            "q50": None,
            "q75": None,
            "q90": None,
            "cvar90": None,
            "thin_sample": True,
        },
        "boundary": (
            "slippage quantile artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def fetch_taker_slippage_rows(
    conn: Any,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """SELECT-only 量測 taker 滑點分位(ROLLUP)。conn 須為 read-only 連線。"""
    cur = conn.cursor()
    try:
        cur.execute(SLIPPAGE_QUANTILE_SQL, {"window_days": window_days})
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, record)) for record in cur.fetchall()]
    finally:
        cur.close()


def _connect_readonly_pg(*, statement_timeout_ms: int = 180_000) -> Any:
    from helper_scripts.lib.pg_connect import connect_report_pg

    conn = connect_report_pg(
        "cost_gate_slippage_quantiles",
        statement_timeout_ms_default=statement_timeout_ms,
    )
    conn.rollback()
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _default_artifact_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / ARTIFACT_FILENAME


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=180_000)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.window_days < 1 or args.window_days > 3650:
        raise ValueError("--window-days must be in [1, 3650]")
    conn = _connect_readonly_pg(statement_timeout_ms=args.pg_statement_timeout_ms)
    try:
        rows = fetch_taker_slippage_rows(conn, window_days=args.window_days)
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()
    artifact = build_slippage_quantile_artifact(rows, window_days=args.window_days)
    output = args.output or _default_artifact_path()
    _write_json(output, artifact)
    if args.print_json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
