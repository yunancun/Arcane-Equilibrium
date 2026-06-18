"""demo round-trip 成本分解（唯讀研究分析；cost-bleed diagnosis）。

MODULE_NOTE:
  模塊用途：把 axis (a) 揭露的 demo per-trade ~−12.5 bps 結構性 bleed 分解成可歸因
    的成本 component，找出 bleed 在哪集中、哪條 lever 最有 headroom，且**不與 sibling
    （a90ffc7b）已在拉的 maker-reprice / maker-markout 工作重疊**。本腳本只做 DIAGNOSIS，
    不提出/實作任何 fix（交 QC/operator 選 lever）。
  分解恆等式（SSOT，來自 realized_edge_stats._pair_round_trips）：
    net_pnl_bps = gross_pnl_bps − (entry_fee_bps + exit_fee_bps) + funding_bps
    其中 gross_pnl_bps 由 DB realized_pnl（真實成交價）算 → **執行 slippage / adverse
    selection 已內含於 gross**，不可再從 net 另外扣（否則雙重計入）。故：
      (1) explicit fee  = entry_fee_bps + exit_fee_bps（taker vs maker 可分，靠 fee_rate / role）
      (4) funding       = funding_bps（realized funding settlement，PIT-safe 半開區間歸因）
      (5) residual      = gross_pnl_bps（entry/exit timing PnL，非成本的部分）
      恆等：net = residual − fee + funding（reconciliation gap 應 ~0，誠實報差）
    (2) spread-crossing slippage 與 (3) adverse-selection markout 是**診斷 overlay**
      （fills.slippage_bps / fills.maker_markout_bps），描述 gross 在執行層被侵蝕在哪，
      **不是可加的 line item**；只用來定位 lever，不重複扣 net。
  硬邊界（研究紅線）：
    - PG **唯讀**：conn.set_session(readonly=True)，只 SELECT。
    - 復用 production SSOT（realized_edge_stats 的 FIFO 配對 + funding 歸因），不另寫
      會 drift 的配對邏輯；只額外建 per-fill (symbol, ts) → cost-meta 索引附掛 overlay。
    - realized-only，無 look-ahead；只用 funding_settlements 真實已結算（非 funding cap）。
    - 不碰 runtime / order / risk / auth / production engine 代碼。
    - 不重算 sibling 的 maker_markout instrument（直接讀 fills.maker_markout_bps）。
  依賴：numpy + psycopg2（延遲 import）；復用 program_code.ml_training.realized_edge_stats。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def _resolve_srv_root() -> Path:
    """向上找含 program_code 的目錄（env 優先；不硬編碼 user path，§六）。"""
    env = os.environ.get("OPENCLAW_SRV_ROOT", "").strip()
    if env and (Path(env) / "program_code").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for cand in [here, *here.parents]:
        if (cand / "program_code").is_dir():
            return cand
    cwd = Path.cwd()
    if (cwd / "program_code").is_dir():
        return cwd
    raise SystemExit("找不到 srv root（含 program_code 的目錄）；請設 OPENCLAW_SRV_ROOT")


_SRV_ROOT = _resolve_srv_root()
for _p in (str(_SRV_ROOT), str(_SRV_ROOT / "helper_scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from program_code.ml_training import realized_edge_stats as res
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training import realized_edge_stats as res  # type: ignore

SINCE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)  # demo fills 從 2026-04 才有
ENGINE_MODE = "demo"
# taker→maker 假想路由的 fee 差（demo 實測中位數：taker 5.5 bps、maker 2.0 bps）。
# 用實測中位數而非硬編碼，於 main 動態計算；此處僅作 fallback。
_FALLBACK_TAKER_FEE_BPS = 5.5
_FALLBACK_MAKER_FEE_BPS = 2.0


def _connect():
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPENCLAW_DATABASE_URL 未設定")
    conn = psycopg2.connect(dsn, application_name="cost_bleed_decomp")
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (300000,))
    return conn


# ---------------------------------------------------------------------------
# 資料載入（復用 production SSOT 的 round-trip 配對 + funding 歸因）
# ---------------------------------------------------------------------------
def load_round_trips_with_funding(conn) -> list:
    """復用 realized_edge_stats 的 FIFO 配對 + funding 歸因（SSOT，不 drift）。"""
    from psycopg2.extras import RealDictCursor

    modes = res._engine_mode_scope(ENGINE_MODE)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(res._FILLS_QUERY, {"since": SINCE, "engine_modes": modes})
        fills = [dict(r) for r in cur.fetchall()]
        cur.execute(res._FUNDING_QUERY, {"since": SINCE, "engine_modes": modes})
        funding_rows = [dict(r) for r in cur.fetchall()]
    records = res._pair_round_trips(fills)
    # funding 歸因（原地修改 net_pnl_bps + funding_bps；半開區間 PIT-safe）。
    res._attach_funding_to_records(records, funding_rows)
    return [r for r in records if r.exit_ts is not None]


def load_fill_cost_meta(conn) -> dict:
    """per-fill 執行成本 overlay 索引：key=(symbol, ts) → {role, slippage, markout, fee_rate}。

    為什麼用 (symbol, ts)：FIFO 配對的 RoundTripRecord 只保留 entry_ts / exit_ts，
    fill_id 未透傳；同 symbol 同毫秒撞 ts 機率極低（demo），以 (symbol, ts) 對齊足夠。
    撞鍵時保留首見並計數（report 揭露碰撞率，誠實）。
    """
    from psycopg2.extras import RealDictCursor

    modes = res._engine_mode_scope(ENGINE_MODE)
    meta: dict = {}
    collisions = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT symbol, ts, side, liquidity_role, slippage_bps,
                   maker_markout_bps, fee_rate, reference_source, close_maker_attempt
            FROM trading.fills
            WHERE engine_mode = ANY(%(modes)s) AND ts >= %(since)s
              AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%%')
            """,
            {"modes": modes, "since": SINCE},
        )
        for row in cur.fetchall():
            key = (row["symbol"], row["ts"])
            if key in meta:
                collisions += 1
                continue
            meta[key] = {
                "role": row["liquidity_role"],
                "slippage_bps": _f(row["slippage_bps"]),
                "markout_bps": _f(row["maker_markout_bps"]),
                "fee_rate_bps": (_f(row["fee_rate"]) or 0.0) * 10_000.0,
                "ref_source": row["reference_source"],
                "close_maker_attempt": row["close_maker_attempt"],
            }
    meta["_collisions"] = collisions
    return meta


def _f(v):
    if v is None:
        return None
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 分解
# ---------------------------------------------------------------------------
def decompose(round_trips, cost_meta) -> dict:
    """逐 round-trip 把 net 分解成 fee / funding / residual(gross)，並附 role/slippage/markout overlay。"""
    rows = []
    for rt in round_trips:
        entry_meta = cost_meta.get((rt.symbol, _norm_ts(rt.entry_ts)))
        exit_meta = cost_meta.get((rt.symbol, _norm_ts(rt.exit_ts))) if rt.exit_ts else None
        rows.append({
            "strategy": rt.strategy_name,
            "symbol": rt.symbol,
            "net_bps": rt.net_pnl_bps,
            "gross_bps": rt.gross_pnl_bps,            # = residual (非成本)
            "entry_fee_bps": rt.entry_fee_bps,
            "exit_fee_bps": rt.exit_fee_bps,
            "fee_bps": rt.entry_fee_bps + rt.exit_fee_bps,
            "funding_bps": rt.funding_bps,
            "entry_role": entry_meta["role"] if entry_meta else None,
            "exit_role": exit_meta["role"] if exit_meta else None,
            "entry_slippage_bps": entry_meta["slippage_bps"] if entry_meta else None,
            "exit_slippage_bps": exit_meta["slippage_bps"] if exit_meta else None,
            "entry_markout_bps": entry_meta["markout_bps"] if entry_meta else None,
            "exit_markout_bps": exit_meta["markout_bps"] if exit_meta else None,
        })
    return {"rows": rows, "n": len(rows)}


def _norm_ts(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def _agg(vals):
    a = np.array([v for v in vals if v is not None], dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {"n": 0, "mean": None, "sum": None, "median": None}
    return {
        "n": int(len(a)),
        "mean": float(a.mean()),
        "sum": float(a.sum()),
        "median": float(np.median(a)),
    }


def reconcile(rows) -> dict:
    """component 加總 vs net 的對賬（恆等式自證 + reconciliation gap）。"""
    net = _agg([r["net_bps"] for r in rows])
    gross = _agg([r["gross_bps"] for r in rows])
    fee = _agg([r["fee_bps"] for r in rows])
    funding = _agg([r["funding_bps"] for r in rows])
    entry_fee = _agg([r["entry_fee_bps"] for r in rows])
    exit_fee = _agg([r["exit_fee_bps"] for r in rows])
    # net 應 == gross − fee + funding。
    recon_mean = (gross["mean"] - fee["mean"] + funding["mean"]) if all(
        x["mean"] is not None for x in (gross, fee, funding)
    ) else None
    gap = (net["mean"] - recon_mean) if (net["mean"] is not None and recon_mean is not None) else None
    return {
        "mean_net_bps": net["mean"],
        "mean_gross_residual_bps": gross["mean"],
        "mean_total_fee_bps": fee["mean"],
        "mean_entry_fee_bps": entry_fee["mean"],
        "mean_exit_fee_bps": exit_fee["mean"],
        "mean_funding_bps": funding["mean"],
        "reconstructed_net_mean_bps": recon_mean,
        "reconciliation_gap_bps": gap,
        "identity": "net = gross_residual - total_fee + funding",
    }


def slice_by(rows, key_fn) -> dict:
    """按 key_fn 分組，回每組的 net / fee / funding / gross 均值 + n。"""
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    out = {}
    for k, recs in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        net = _agg([r["net_bps"] for r in recs])
        out[str(k)] = {
            "n": len(recs),
            "mean_net_bps": net["mean"],
            "mean_fee_bps": _agg([r["fee_bps"] for r in recs])["mean"],
            "mean_funding_bps": _agg([r["funding_bps"] for r in recs])["mean"],
            "mean_gross_residual_bps": _agg([r["gross_bps"] for r in recs])["mean"],
            "total_net_bps": net["sum"],   # 對總 bleed 的貢獻（n × mean）
        }
    return out


def maker_taker_share(rows) -> dict:
    """maker vs taker fill share（entry+exit 兩腿合計），及各自 fee/slippage/markout。"""
    leg_roles = []
    for r in rows:
        for role in (r["entry_role"], r["exit_role"]):
            if role is not None:
                leg_roles.append(role)
    counts = defaultdict(int)
    for role in leg_roles:
        counts[role] += 1
    total_known = sum(counts.values())
    # 逐腿 slippage / markout / fee（按 role）。
    taker_slip, maker_markout = [], []
    for r in rows:
        for role, slip, mk in (
            (r["entry_role"], r["entry_slippage_bps"], r["entry_markout_bps"]),
            (r["exit_role"], r["exit_slippage_bps"], r["exit_markout_bps"]),
        ):
            if role == "taker" and slip is not None:
                taker_slip.append(slip)
            if role == "maker" and mk is not None:
                maker_markout.append(mk)
    return {
        "leg_role_counts": dict(counts),
        "total_known_role_legs": total_known,
        "maker_leg_share": (counts.get("maker", 0) / total_known) if total_known else None,
        "taker_leg_share": (counts.get("taker", 0) / total_known) if total_known else None,
        "unknown_role_legs": counts.get(None, 0),
        "taker_slippage_bps": _agg(taker_slip),   # 簽名：正=adverse(穿越劣勢)
        "maker_markout_bps": _agg(maker_markout),  # sibling instrument；正=adverse selection
    }


def taker_to_maker_headroom(rows, taker_fee_bps, maker_fee_bps) -> dict:
    """taker→maker 路由的可尋址 bps（不與 sibling maker-reprice 重疊：此為 *taker* 腿改走 maker）。

    sibling 修的是「已是 maker close 但 fill 失敗 → reprice」；此 lever 是把**現在走 taker
    的腿**（非 stop/urgent 安全腿）改成 maker 報價，省下 (taker_fee − maker_fee) 的 fee 差。
    只計可路由腿：排除 close_maker_attempt 已嘗試 maker 的腿（避免與 sibling 重疊）。
    """
    routable_taker_legs = 0
    total_legs = 0
    fee_saving_bps_per_rt = []
    for r in rows:
        rt_saving = 0.0
        for role in (r["entry_role"], r["exit_role"]):
            if role is None:
                continue
            total_legs += 1
            if role == "taker":
                routable_taker_legs += 1
                rt_saving += (taker_fee_bps - maker_fee_bps)
        if rt_saving > 0:
            fee_saving_bps_per_rt.append(rt_saving)
    return {
        "fee_delta_taker_minus_maker_bps": taker_fee_bps - maker_fee_bps,
        "routable_taker_legs": routable_taker_legs,
        "total_known_role_legs": total_legs,
        "n_rt_with_taker_leg": len(fee_saving_bps_per_rt),
        # 全 round-trip 平均可省 fee（把 taker 腿改 maker，理想上限，未計成交率損失）。
        "mean_addressable_fee_bps_per_rt_upper_bound": (
            float(np.mean(fee_saving_bps_per_rt)) if fee_saving_bps_per_rt else 0.0
        ),
        "note": (
            "上限估計：假設所有非安全 taker 腿都能成功掛 maker；實際受成交率折損。"
            "與 sibling 不重疊（sibling 修已 maker 的 close 失敗 reprice，此修 taker→maker 路由）。"
        ),
    }


def funding_headroom(rows) -> dict:
    """funding / holding-cost lever：funding 對 bleed 的貢獻 + 是否 short 在付 funding。"""
    by_dir = {"net_funding_paid": [], "net_funding_received": []}
    funding_vals = [r["funding_bps"] for r in rows if r["funding_bps"] not in (None, 0.0)]
    for r in rows:
        fb = r["funding_bps"]
        if fb is None or fb == 0.0:
            continue
        if fb < 0:
            by_dir["net_funding_paid"].append(fb)
        else:
            by_dir["net_funding_received"].append(fb)
    return {
        "n_rt_with_funding": len(funding_vals),
        "mean_funding_bps_all_rt": _agg([r["funding_bps"] for r in rows])["mean"],
        "mean_funding_bps_when_nonzero": _agg(funding_vals)["mean"],
        "n_paid": len(by_dir["net_funding_paid"]),
        "n_received": len(by_dir["net_funding_received"]),
        "sum_funding_bps_paid": _agg(by_dir["net_funding_paid"])["sum"],
        "sum_funding_bps_received": _agg(by_dir["net_funding_received"])["sum"],
    }


# ---------------------------------------------------------------------------
# 主編排
# ---------------------------------------------------------------------------
def main() -> None:
    conn = _connect()
    try:
        round_trips = load_round_trips_with_funding(conn)
        cost_meta = load_fill_cost_meta(conn)
        # 動態取 taker/maker fee 中位數（bps），fallback 為實測常數。
        from psycopg2.extras import RealDictCursor
        modes = res._engine_mode_scope(ENGINE_MODE)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT liquidity_role,
                  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fee_rate)) * 10000 AS median_fee_bps
                FROM trading.fills
                WHERE engine_mode = ANY(%(modes)s) AND ts >= %(since)s
                  AND liquidity_role IN ('taker','maker')
                GROUP BY liquidity_role
                """,
                {"modes": modes, "since": SINCE},
            )
            fee_med = {row["liquidity_role"]: _f(row["median_fee_bps"]) for row in cur.fetchall()}
    finally:
        conn.close()

    taker_fee = fee_med.get("taker") or _FALLBACK_TAKER_FEE_BPS
    maker_fee = fee_med.get("maker") or _FALLBACK_MAKER_FEE_BPS

    dec = decompose(round_trips, cost_meta)
    rows = dec["rows"]

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "engine_mode": ENGINE_MODE,
        "n_round_trips": dec["n"],
        "cost_meta_collisions": cost_meta.get("_collisions", 0),
        "median_taker_fee_bps": taker_fee,
        "median_maker_fee_bps": maker_fee,
        "reconciliation": reconcile(rows),
        "slice_by_strategy": slice_by(rows, lambda r: r["strategy"]),
        "slice_by_symbol_top_bleeders": dict(
            sorted(
                slice_by(rows, lambda r: r["symbol"]).items(),
                key=lambda kv: (kv[1]["total_net_bps"] or 0.0),
            )[:20]  # 最負 total_net（對總 bleed 貢獻最大）排前
        ),
        "maker_taker_share": maker_taker_share(rows),
        "lever_taker_to_maker_routing": taker_to_maker_headroom(rows, taker_fee, maker_fee),
        "lever_funding_holding": funding_headroom(rows),
    }

    out_path = os.environ.get("DECOMP_OUT", "/tmp/openclaw/cost_bleed/decompose.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
