"""D2 re-validation 掛接：cascade 事件 → 反向 maker 掛單 → fill/逆選擇 → net 裁決。

MODULE_NOTE:
  模塊用途：把 D2（liquidation-cascade delta-中性 LP 收斂候選）掛到 fill-realism
    harness 上，用真 L2 queue 裁決 maker net（**禁 rebate**）：
      1. 事件源（read-only）：market.liquidations 逐筆強平 → 時間聚類 + 累積 qty
         閾值 + 方向 → cascade 事件序列。Mac/無 PG 時可改用 Tardis liquidations
         CSV（同窗）構造，作為 PG 不可達時的離線等價來源。
      2. 掛單規格（leak-free）：每事件掛反 cascade passive maker 限價單——被
         Sell-清算的下殺 → 掛 buy 接超調；被 Buy-清算的上衝 → 掛 sell。
         **entry 必落事件後第一個 tick + feed latency**（harness 內 elapse 到
         事件時戳之後才 submit + 逐單 entry_ts>=event_ts 斷言）。
      3. queue 裁決：harness ProbQueueModel(log_prob) 算 fill/queue position/
         成交後逆選擇 + time-based exit（半衰期 5min 收斂窗）。
      4. net 計算：對成交單算 convergence − maker_fee(2bps/leg, **rebate=0**) −
         逆選擇。**未成交的單計入 fill_rate 分母**（D2 non-harvestable 假說核心）。
      5. 裁決：d2_revalidation.json{maker_fill_rate, adverse_selection_bps,
         net_maker_bps, net_taker_bps, n_events, verdict}。
  依賴：numpy + harness（hftbacktest）；market.liquidations 讀取用 psycopg2
    （read-only，強制 set_session(readonly=True)）；converter load_event_array。
  誠實鐵則（DECISIVE）：
    - net 永不含正 rebate（__init__.assert_no_rebate 在計算入口硬擋）。
    - free-sample 成交事件數 < MIN_HARVESTABLE_FILLED_EVENTS → 禁吐 HARVESTABLE
      （verdict 強制 INSUFFICIENT_SAMPLE 或 NON-HARVESTABLE）。
    - fill_rate < FILL_RATE_FATAL_FLOOR = 致命低 → NON-HARVESTABLE（小樣本即穩健）。
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from . import (
    CASCADE_CLUSTER_WINDOW_S_DEFAULT,
    CASCADE_MIN_EVENTS_DEFAULT,
    D2_EXIT_HORIZON_S_DEFAULT,
    FILL_RATE_FATAL_FLOOR,
    MAKER_FEE_BPS_PER_LEG,
    MAKER_REBATE_BPS,
    MIN_HARVESTABLE_FILLED_EVENTS,
    TAKER_FEE_BPS_PER_LEG,
    VERDICT_BLOCKED,
    VERDICT_HARVESTABLE,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NON_HARVESTABLE,
    assert_no_rebate,
)
from . import converter as converter_mod
from . import harness as harness_mod

logger = logging.getLogger(__name__)

_STATEMENT_TIMEOUT_MS = 180000


@dataclass
class CascadeEvent:
    """一個 liquidation cascade 事件（時間聚類後的群組）。

    liq_side：被清算方向（'Buy'/'Sell'，Bybit 語義）。被 Sell-清算 = 多頭被強平
      下殺 → 反 cascade = buy（接下殺）；被 Buy-清算 = 空頭被強平上衝 → 反 cascade
      = sell（接上衝）。
    """

    symbol: str
    event_ts: dt.datetime
    liq_side: str
    n_liquidations: int
    total_qty: float
    last_price: float


# ---------------------------------------------------------------------------
# 事件源：cascade 偵測（時間聚類 + qty 閾值 + 方向）
# ---------------------------------------------------------------------------

def detect_cascades(
    liquidations: Sequence[dict],
    *,
    cluster_window_s: float = CASCADE_CLUSTER_WINDOW_S_DEFAULT,
    min_events: int = CASCADE_MIN_EVENTS_DEFAULT,
) -> list[CascadeEvent]:
    """把逐筆強平按 (symbol, side) 分組、時間聚類成 cascade 事件。

    cascade 定義：同 symbol 同方向、相鄰強平時間差 <= cluster_window_s 的連續群組，
    且群組內事件數 >= min_events（qty 閾值由 min_events 隱含；可由 caller 加總過閾）。
    每行 dict 需含 ts(datetime)/symbol/side/qty/price。
    """
    # 依 (symbol, side, ts) 排序，逐組滑窗聚類。
    rows = sorted(
        (r for r in liquidations if r.get("ts") is not None),
        key=lambda r: (r["symbol"], r["side"], r["ts"]),
    )
    events: list[CascadeEvent] = []
    cur: list[dict] = []

    def _flush(group: list[dict]) -> None:
        if len(group) >= min_events:
            total_qty = float(sum(float(g["qty"]) for g in group))
            last = group[-1]
            events.append(
                CascadeEvent(
                    symbol=last["symbol"],
                    # 事件時戳 = 群組最後一筆強平時戳（entry 必落「事件確認」之後，
                    # 用末筆=最保守，確保不向前看群組內更早資訊）。
                    event_ts=last["ts"],
                    liq_side=last["side"],
                    n_liquidations=len(group),
                    total_qty=total_qty,
                    last_price=float(last["price"]),
                )
            )

    for r in rows:
        if not cur:
            cur = [r]
            continue
        prev = cur[-1]
        same_group = (
            r["symbol"] == prev["symbol"]
            and r["side"] == prev["side"]
            and (r["ts"] - prev["ts"]).total_seconds() <= cluster_window_s
        )
        if same_group:
            cur.append(r)
        else:
            _flush(cur)
            cur = [r]
    _flush(cur)
    return events


def load_liquidations_pg(
    conn,
    *,
    symbol: str,
    window_start: dt.datetime,
    window_end: dt.datetime,
) -> list[dict]:
    """read-only 讀 market.liquidations（強制 readonly session 由 caller 設定）。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, symbol, side, qty, price
              FROM market.liquidations
             WHERE symbol = %s AND ts >= %s AND ts <= %s
             ORDER BY ts ASC
            """,
            (symbol, window_start, window_end),
        )
        rows = cur.fetchall()
    return [
        {"ts": r[0], "symbol": r[1], "side": r[2], "qty": float(r[3]), "price": float(r[4])}
        for r in rows
    ]


def connect_readonly(dsn: Optional[str], application_name: str = "hftbacktest_fill_realism_d2"):
    """read-only PG 連線（強制 set_session(readonly=True)，mirror panel_export）。

    為什麼 fail-closed readonly：本 harness 對 market.liquidations 只讀，readonly
    session 是「結構上不可能寫 trading/market schema」的硬保證（即使 SQL 寫錯）。
    """
    import sys

    import psycopg2  # type: ignore

    if dsn is None:
        srv_root = Path(__file__).resolve().parents[3]
        helper_dir = srv_root / "helper_scripts"
        if str(helper_dir) not in sys.path:
            sys.path.insert(0, str(helper_dir))
        try:
            from lib.pg_connect import resolve_report_dsn  # type: ignore

            dsn = resolve_report_dsn()
        except Exception:  # noqa: BLE001 —— 退 env DSN，仍 readonly。
            import os

            dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn, application_name=application_name)
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
    return conn


def load_liquidations_tardis_csv(csv_gz_path: Path) -> list[dict]:
    """Tardis liquidations CSV.gz → 強平行（PG 不可達時的離線等價事件源）。

    Tardis schema：exchange,symbol,timestamp,local_timestamp,id,side,price,amount。
    timestamp 是微秒（µs）；side 小寫 buy/sell → 正規化成 Bybit Buy/Sell 語義。
    """
    import csv
    import gzip

    rows: list[dict] = []
    with gzip.open(str(csv_gz_path), "rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                ts_us = int(r["timestamp"])
                ts = dt.datetime.fromtimestamp(ts_us / 1_000_000.0, tz=dt.timezone.utc)
                side = r["side"].strip().lower()
                side_norm = "Buy" if side == "buy" else "Sell"
                rows.append(
                    {
                        "ts": ts,
                        "symbol": r["symbol"],
                        "side": side_norm,
                        "qty": float(r["amount"]),
                        "price": float(r["price"]),
                    }
                )
            except (KeyError, ValueError):
                # 壞行跳過（raw 不可信任，fail-soft per row）。
                continue
    return rows


# ---------------------------------------------------------------------------
# cascade 事件 → maker 掛單規格（leak-free，反 cascade 方向）
# ---------------------------------------------------------------------------

def event_ts_to_ns(ts: dt.datetime) -> int:
    """datetime → epoch ns（與 converter 8-field 的 exch_ts/local_ts 同單位）。"""
    return int(ts.timestamp() * 1_000_000_000)


def build_maker_specs(
    events: Sequence[CascadeEvent],
    *,
    exit_horizon_s: float = D2_EXIT_HORIZON_S_DEFAULT,
    overshoot_offset_bps: float = 0.0,
    qty: float = 0.01,
) -> list[harness_mod.MakerOrderSpec]:
    """每個 cascade 事件構造一張反向 passive maker 限價單規格。

    leak-free：event_ts_ns = cascade 事件時戳（harness 推進到此之後才 submit）。
    方向：反 cascade——被 Sell-清算（多頭被強平下殺）→ buy（掛 bid 側接下殺）；
      被 Buy-清算（空頭被強平上衝）→ sell（掛 ask 側接上衝）。
    peg：以 ``overshoot_offset_bps``（相對「事件當時 live BBO」的偏移，由 harness
      在事件時戳當下用真 BBO 計算）表達；**不**用 cascade 的 stale liquidation
      price 定錨——清算執行價在 cascade 偵測時已偏離現價數十 bps，用它定錨會把
      掛單推到簿外永不成交（peg artifact，非真 non-harvestable）。
      offset=0 = 貼 BBO（最積極被動 maker）；>0 = 退到更深處接超調。
    """
    specs: list[harness_mod.MakerOrderSpec] = []
    for i, ev in enumerate(events):
        # Sell-清算 → 反 cascade buy；Buy-清算 → 反 cascade sell。
        side = "buy" if ev.liq_side == "Sell" else "sell"
        specs.append(
            harness_mod.MakerOrderSpec(
                event_id=f"{ev.symbol}-{i}-{int(ev.event_ts.timestamp())}",
                side=side,
                event_ts_ns=event_ts_to_ns(ev.event_ts),
                peg_offset_bps=float(overshoot_offset_bps),
                qty=float(qty),
                exit_horizon_ns=int(exit_horizon_s * 1_000_000_000),
            )
        )
    return specs


# ---------------------------------------------------------------------------
# net 計算（rebate 鐵則執行點）+ 裁決
# ---------------------------------------------------------------------------

def compute_net_and_verdict(
    sim: harness_mod.SimResult,
    *,
    maker_fee_bps_per_leg: float = MAKER_FEE_BPS_PER_LEG,
    maker_rebate_bps: float = MAKER_REBATE_BPS,
    taker_fee_bps_per_leg: float = TAKER_FEE_BPS_PER_LEG,
    min_harvestable_filled: int = MIN_HARVESTABLE_FILLED_EVENTS,
    fill_rate_fatal_floor: float = FILL_RATE_FATAL_FLOOR,
) -> dict:
    """從 sim outcome 算 fill_rate / 逆選擇 / net（禁 rebate）並裁決。

    net_maker_bps = mean(convergence − adverse) − round-trip maker fee（entry+exit
      兩腳，rebate=0）。net_taker_bps 為對照腳（同 convergence/adverse，扣 taker
      round-trip fee 而非 maker），驗成本腳差異。
    """
    # 鐵則守衛：任何非 0 rebate 即 raise（DECISIVE BLOCKER 執行點）。
    assert_no_rebate(maker_rebate_bps)

    n_events = sim.n_events
    # fill_rate 分母 = 所有事件（含未成交！D2 non-harvestable 假說核心）。
    n_filled = sim.n_filled
    fill_rate = (n_filled / n_events) if n_events > 0 else 0.0

    filled = [o for o in sim.outcomes if o.filled]
    if filled:
        mean_conv = sum(o.convergence_bps for o in filled) / len(filled)
        mean_adverse = sum(o.adverse_selection_bps for o in filled) / len(filled)
    else:
        mean_conv = 0.0
        mean_adverse = 0.0

    gross_edge_bps = mean_conv - mean_adverse
    # round-trip = 兩腳費用（entry maker + exit maker）。rebate=0 已由守衛保證。
    maker_round_trip_fee = 2.0 * maker_fee_bps_per_leg - 2.0 * maker_rebate_bps
    taker_round_trip_fee = 2.0 * taker_fee_bps_per_leg
    net_maker_bps = gross_edge_bps - maker_round_trip_fee
    net_taker_bps = gross_edge_bps - taker_round_trip_fee

    # 裁決（誠實鐵則）：
    if n_events == 0:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        detail = "no_cascade_events_in_free_sample"
    elif fill_rate < fill_rate_fatal_floor:
        # 致命低 fill_rate = 掛單接不到 cascade 對手盤 = D2 non-harvestable 核心。
        # 小樣本即穩健（PA design §3.3）。
        verdict = VERDICT_NON_HARVESTABLE
        detail = f"fatal_low_fill_rate={fill_rate:.3f}<{fill_rate_fatal_floor}"
    elif net_maker_bps <= 0.0:
        verdict = VERDICT_NON_HARVESTABLE
        detail = f"net_maker_bps={net_maker_bps:.3f}<=0_after_fees_and_adverse_selection"
    elif n_filled < min_harvestable_filled:
        # net 正、fill 不致命，但成交樣本不足 → 禁吐 HARVESTABLE（高後果結論需大樣本）。
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        detail = (
            f"net_maker_positive_but_filled={n_filled}<{min_harvestable_filled}"
            "_free_tier_cannot_prove_harvestable"
        )
    else:
        verdict = VERDICT_HARVESTABLE
        detail = (
            f"net_maker_bps={net_maker_bps:.3f}>0 fill_rate={fill_rate:.3f} "
            f"filled={n_filled}>={min_harvestable_filled}"
        )

    return {
        "n_events": n_events,
        "n_submitted": sim.n_submitted,
        "n_filled": n_filled,
        "maker_fill_rate": round(fill_rate, 6),
        "adverse_selection_bps": round(mean_adverse, 6),
        "convergence_bps": round(mean_conv, 6),
        "gross_edge_bps": round(gross_edge_bps, 6),
        "maker_fee_bps_per_leg": maker_fee_bps_per_leg,
        "maker_rebate_bps": maker_rebate_bps,
        "maker_round_trip_fee_bps": maker_round_trip_fee,
        "taker_round_trip_fee_bps": taker_round_trip_fee,
        "net_maker_bps": round(net_maker_bps, 6),
        "net_taker_bps": round(net_taker_bps, 6),
        "verdict": verdict,
        "verdict_detail": detail,
        "sim_errors": sim.errors,
    }


def revalidate_d2(
    *,
    npz_path: Path,
    liquidations: Sequence[dict],
    symbol: str,
    tick_size: float,
    lot_size: float,
    cluster_window_s: float = CASCADE_CLUSTER_WINDOW_S_DEFAULT,
    min_events: int = CASCADE_MIN_EVENTS_DEFAULT,
    exit_horizon_s: float = D2_EXIT_HORIZON_S_DEFAULT,
    overshoot_offset_bps: float = 5.0,
    order_qty: float = 0.01,
    queue_model: str = "log_prob",
) -> dict:
    """端到端：liquidations → cascade → maker specs → harness 模擬 → net 裁決。

    npz_path = converter 產出的 8-field event array（同 symbol 同窗的 Tardis L2 tape）。
    若 hftbacktest 不可用，harness 回 errors，本函數導向 BLOCKED（不偽造 verdict）。
    """
    events = detect_cascades(liquidations, cluster_window_s=cluster_window_s, min_events=min_events)
    specs = build_maker_specs(
        events, exit_horizon_s=exit_horizon_s, overshoot_offset_bps=overshoot_offset_bps, qty=order_qty,
    )

    try:
        event_array = converter_mod.load_event_array(Path(npz_path))
    except Exception as exc:  # noqa: BLE001 —— npz 缺/壞 → BLOCKED，不偽造。
        return {
            "verdict": VERDICT_BLOCKED,
            "verdict_detail": f"event_array_load_failed:{exc!r}",
            "n_events": len(events),
            "symbol": symbol,
        }

    sim = harness_mod.simulate_maker_fills(
        event_array,
        specs,
        tick_size=tick_size,
        lot_size=lot_size,
        queue_model=queue_model,
    )

    # hftbacktest 不可用 = 結構性 errors 且 0 submit → BLOCKED（誠實，不裁 NON-HARVESTABLE）。
    if sim.errors and any(e.startswith("hftbacktest_unavailable") for e in sim.errors):
        return {
            "verdict": VERDICT_BLOCKED,
            "verdict_detail": "hftbacktest_engine_unavailable",
            "n_events": len(events),
            "symbol": symbol,
            "sim_errors": sim.errors,
        }

    result = compute_net_and_verdict(sim)
    result["symbol"] = symbol
    result["cascade_cluster_window_s"] = cluster_window_s
    result["cascade_min_events"] = min_events
    result["exit_horizon_s"] = exit_horizon_s
    result["queue_model"] = queue_model
    # 逐單 leak 斷言結果（harness 已偵測 entry_ts<event_ts 並記入 sim.errors）。
    result["leak_violations"] = [e for e in sim.errors if e.startswith("leak:")]
    return result
