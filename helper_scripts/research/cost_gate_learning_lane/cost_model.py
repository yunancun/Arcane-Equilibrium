"""保守反事實成本模型(P1-2a)。

MODULE_NOTE:
  模塊用途：把被擋信號/markout-proxy 的反事實成本，從單一樂觀常數
    (4.0 bps round-trip = 純 maker 雙腿 fee、零滑點) 換成「taker fee + per-symbol
    滑點分位 p75 × 安全乘數」的保守模型，避免系統性低估執行成本後污染候選排序。
  主要函數：conservative_cost_bps（單筆成本）、load_slippage_quantiles（讀分位 artifact）、
    funding_crossing_count（horizon 內 funding 結算跨越次數）。
  依賴：分位 artifact(slippage_quantiles_latest.json，由 slippage_quantile_artifact.py 產)、
    risk_config_demo.toml [slippage.tiers] fallback；不直連 PG(artifact-only lane 邊界)。
  硬邊界：任何情況下成本 ≥ 純 taker fee 雙腿下界 FEE_FLOOR_BPS(手續費不打折，
    QC 硬約束 #4)；分位缺失/過期走 fallback 鏈逐級降級並記 cost_model_source。

QC spec 正本：docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-04--evidence_
methodology_redesign_p12_p27_p28_f7.md §2 + addendum §C。
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import math
from typing import Any


# Bybit VIP0 taker 單腿 fee(bps)。maker 不假設成交(touchability 33/33 no-touch)。
FEE_TAKER_BPS = 5.5
# 純 taker fee 雙腿硬 floor：手續費不打折，任何 fallback 都不得低於此值。
FEE_FLOOR_BPS = 2.0 * FEE_TAKER_BPS  # = 11.0
# 復用 risk_config_demo.toml:398 cost_gate_safety_multiplier，勿新增旋鈕。
COST_GATE_SAFETY_MULTIPLIER = 1.3
# per-symbol 分位激活門檻：該 symbol 90d taker fills n ≥ 20 才用 symbol_q75。
MIN_SYMBOL_FILLS_FOR_QUANTILE = 20
# 分位分位數 τ=0.75：p50 半數比它貴(非保守)、p95 被尾樣本擺佈(估計噪音大)。
SLIPPAGE_QUANTILE_TAU = 0.75
# artifact 新鮮度上界(小時)。超過即視為過期，走 fallback 鏈第 3 級。
QUANTILE_ARTIFACT_MAX_AGE_HOURS = 48
# funding 快照缺失時，每次 crossing 記此保守常數(bps)。
FUNDING_FALLBACK_BPS_PER_CROSSING = 1.0

# risk_config_demo.toml [[slippage.tiers]] 的 rate(小數)→ bps 換算後的 tier fallback。
# 依 24h turnover 由高到低取第一個 min_turnover 命中的 tier；無 turnover 時取最保守
# tier(最後一項 30bps)。artifact-only lane 不讀 PG，故此表內嵌避免 TOML 依賴。
_TOML_SLIPPAGE_TIERS_BPS: tuple[tuple[float, float], ...] = (
    (1_000_000_000.0, 1.0),
    (100_000_000.0, 2.0),
    (10_000_000.0, 5.0),
    (1_000_000.0, 15.0),
    (0.0, 30.0),
)


COST_MODEL_VERSION = "conservative_v1"
LEGACY_COST_MODEL_VERSION = "legacy_optimistic_v0"
LEGACY_OPTIMISTIC_COST_BPS = 4.0


@dataclass(frozen=True)
class SymbolSlippageQuantile:
    """單一 symbol 的滑點分位快照(來自 artifact)。"""

    symbol: str
    n_total: int
    q75_bps: float
    asof: str | None = None
    thin_sample: bool = False


@dataclass(frozen=True)
class SlippageQuantileTable:
    """分位 artifact 的內存投影。global_q75 由 symbol=None(ROLLUP) 承載。"""

    per_symbol: dict[str, SymbolSlippageQuantile]
    global_q75_bps: float | None
    asof: str | None
    n_total_global: int

    def is_fresh(self, *, now: dt.datetime, max_age_hours: int) -> bool:
        """artifact 是否在新鮮度窗口內。asof 缺失/不可解析 → 視為不新鮮。"""
        parsed = _parse_dt(self.asof)
        if parsed is None:
            return False
        age = now.astimezone(dt.timezone.utc) - parsed
        return age <= dt.timedelta(hours=max_age_hours)


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_slippage_quantiles(payload: dict[str, Any] | None) -> SlippageQuantileTable | None:
    """把分位 artifact payload 投影為查表結構。None/畸形 → None(觸發 toml_tier fallback)。

    artifact schema(由 slippage_quantile_artifact.py 產)：
      { "asof": ISO8601, "symbols": [ {symbol, n, q75, thin_sample}, ... ],
        "global": {n, q75} }
    symbol=None 或 "GLOBAL"/"ALL" 的 ROLLUP 行由 global 欄承載。
    """
    if not isinstance(payload, dict):
        return None
    asof = payload.get("asof")
    per_symbol: dict[str, SymbolSlippageQuantile] = {}
    rows = payload.get("symbols")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            q75 = _float(row.get("q75"))
            if not symbol or q75 is None:
                continue
            per_symbol[symbol] = SymbolSlippageQuantile(
                symbol=symbol,
                n_total=_int(row.get("n")),
                q75_bps=q75,
                asof=asof,
                thin_sample=bool(row.get("thin_sample")),
            )
    global_block = payload.get("global")
    global_q75 = None
    n_total_global = 0
    if isinstance(global_block, dict):
        global_q75 = _float(global_block.get("q75"))
        n_total_global = _int(global_block.get("n"))
    return SlippageQuantileTable(
        per_symbol=per_symbol,
        global_q75_bps=global_q75,
        asof=asof,
        n_total_global=n_total_global,
    )


def _toml_tier_slippage_bps(turnover_usd: float | None) -> float:
    """依 24h turnover 取 TOML tier 滑點(bps)。turnover 缺失 → 最保守 tier。"""
    if turnover_usd is None or turnover_usd <= 0.0:
        return _TOML_SLIPPAGE_TIERS_BPS[-1][1]
    for min_turnover, rate_bps in _TOML_SLIPPAGE_TIERS_BPS:
        if turnover_usd >= min_turnover:
            return rate_bps
    return _TOML_SLIPPAGE_TIERS_BPS[-1][1]


def _resolve_slippage_bps(
    *,
    symbol: str,
    table: SlippageQuantileTable | None,
    table_fresh: bool,
    turnover_usd: float | None,
) -> tuple[float, str]:
    """fallback 鏈:symbol_q75 → global_q75 → toml_tier。回傳 (slip_bps, source)。

    為什麼分級：per-symbol 分位在頭部 symbol 覆蓋良好但長尾 n 不足；n<20 時
    per-symbol p75 估計自身噪音過大，退回 global p75(全體 taker)更穩；PG/artifact
    完全不可達時退回 TOML tier(離線可跑)，保住 lane 的純函數性與可離線性。
    """
    symbol_up = symbol.strip().upper()
    if table is not None and table_fresh:
        entry = table.per_symbol.get(symbol_up)
        if entry is not None and entry.n_total >= MIN_SYMBOL_FILLS_FOR_QUANTILE:
            return entry.q75_bps, "symbol_q75"
        if table.global_q75_bps is not None:
            return table.global_q75_bps, "global_q75"
    return _toml_tier_slippage_bps(turnover_usd), "toml_tier"


def conservative_cost_bps(
    *,
    symbol: str,
    horizon_minutes: int,
    table: SlippageQuantileTable | None,
    now: dt.datetime | None = None,
    turnover_usd: float | None = None,
    funding_crossings: int = 0,
    max_age_hours: int = QUANTILE_ARTIFACT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """單筆反事實 outcome 的保守 round-trip 成本(bps)。

    公式：cost = 2×[fee_taker + slip_q(symbol)]×SM + funding_drag。
    滑點全記在成本，entry price 不再另做 adverse-side 調整(避免雙重計費)。

    回傳 dict:{cost_bps, cost_model_version, cost_model_source, slippage_bps,
      fee_taker_bps, safety_multiplier, funding_crossings, funding_drag_bps}。
    不變量：cost_bps ≥ FEE_FLOOR_BPS(手續費不打折硬 floor)。
    """
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    table_fresh = table is not None and table.is_fresh(now=now, max_age_hours=max_age_hours)
    slip_bps, source = _resolve_slippage_bps(
        symbol=symbol,
        table=table,
        table_fresh=table_fresh,
        turnover_usd=turnover_usd,
    )
    crossings = max(0, int(funding_crossings))
    funding_drag_bps = crossings * FUNDING_FALLBACK_BPS_PER_CROSSING
    raw = 2.0 * (FEE_TAKER_BPS + slip_bps) * COST_GATE_SAFETY_MULTIPLIER + funding_drag_bps
    cost_bps = raw
    if cost_bps < FEE_FLOOR_BPS:
        # 低於純 taker fee 雙腿下界代表 slip_bps 為負/畸形；夾到硬 floor 並改記 source。
        cost_bps = FEE_FLOOR_BPS
        source = "fee_floor"
    return {
        "cost_bps": cost_bps,
        "cost_model_version": COST_MODEL_VERSION,
        "cost_model_source": source,
        "slippage_bps": slip_bps,
        "fee_taker_bps": FEE_TAKER_BPS,
        "safety_multiplier": COST_GATE_SAFETY_MULTIPLIER,
        "funding_crossings": crossings,
        "funding_drag_bps": funding_drag_bps,
    }


def funding_crossing_count(
    *,
    event_ts_ms: int,
    horizon_minutes: int,
    funding_interval_hours: float = 8.0,
) -> int:
    """horizon [event_ts, event_ts+horizon] 內跨越的 funding 結算 instant 次數。

    結算對齊 epoch 的 fundingInterval 邊界(0/8/16h UTC for 8h interval)。
    fundingInterval per-symbol 可低至 1h → 240m horizon 最多 4 次(addendum §C errata)。
    """
    if horizon_minutes <= 0 or funding_interval_hours <= 0.0:
        return 0
    interval_ms = int(funding_interval_hours * 3_600_000)
    if interval_ms <= 0:
        return 0
    start_ms = int(event_ts_ms)
    end_ms = start_ms + horizon_minutes * 60_000
    # 第一個 > start 的結算 instant = 下一個 interval 邊界。
    first_crossing = ((start_ms // interval_ms) + 1) * interval_ms
    if first_crossing > end_ms:
        return 0
    return (end_ms - first_crossing) // interval_ms + 1
