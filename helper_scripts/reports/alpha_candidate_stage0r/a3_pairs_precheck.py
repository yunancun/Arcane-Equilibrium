#!/usr/bin/env python3
"""A3 BTC/ETH cointegration pairs stats-first precheck.

MODULE_NOTE
模塊用途：Alpha Tournament A3（BTC/ETH pairs）DRAFT precheck。它只做
read-only PG 取數 + 純 Python 統計/replay 診斷：cointegration proxy、half-life、
shift(1) z-score pair replay、fee-adjusted edge。輸出只允許
`reject` / `draft_only` / `observe_more`，不產生 stage0_ready 或交易激活。

硬邊界：
  - 只 SELECT market.klines；不寫 PG、不改 TOML、不接 Rust、不碰 lease/auth。
  - replay 使用 shift(1) rolling mean/std；signal bar 之後的下一 bar 才可入場。
  - A3 是 stats-first DRAFT lane；即使通過 precheck 也只是 PA/QC/MIT spec input。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


A3_ALPHA_SOURCE_ID = "btc_eth_cointegration_pairs"
RUNNER_VERSION = "a3_pairs_precheck.v1"
DEFAULT_SYMBOL_X = "BTCUSDT"
DEFAULT_SYMBOL_Y = "ETHUSDT"
DEFAULT_TIMEFRAME = "5m"
BAR_INTERVALS: dict[str, str] = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
}


@dataclass(frozen=True)
class PairPrecheckConfig:
    symbol_x: str = DEFAULT_SYMBOL_X
    symbol_y: str = DEFAULT_SYMBOL_Y
    timeframe: str = DEFAULT_TIMEFRAME
    min_aligned_bars: int = 300
    min_abs_corr: float = 0.75
    adf_t_stat_max: float = -2.8
    max_half_life_bars: float = 288.0
    rolling_window: int = 96
    entry_z: float = 2.0
    exit_z: float = 0.5
    max_hold_bars: int = 144
    min_trades: int = 30
    roundtrip_cost_bps: float = 24.0
    min_avg_net_bps: float = 0.0


@dataclass(frozen=True)
class PairBar:
    ts: Any
    x_close: float
    y_close: float


def build_pairs_kline_query(
    *,
    symbol_x: str,
    symbol_y: str,
    timeframe: str,
    lookback_days: int,
) -> tuple[str, dict[str, Any]]:
    """Build the read-only aligned BTC/ETH kline query."""
    if timeframe not in BAR_INTERVALS:
        raise ValueError(f"unsupported timeframe={timeframe!r}")
    sql = """
WITH latest AS (
    SELECT max(ts) AS max_ts
    FROM market.klines
    WHERE symbol = ANY(%(symbols)s::text[])
      AND timeframe = %(timeframe)s
)
SELECT
    x.ts,
    x.close AS x_close,
    y.close AS y_close
FROM market.klines x
JOIN market.klines y
  ON y.ts = x.ts
 AND y.timeframe = x.timeframe
 AND y.symbol = %(symbol_y)s
CROSS JOIN latest
WHERE x.symbol = %(symbol_x)s
  AND x.timeframe = %(timeframe)s
  AND x.ts >= now() - %(lookback)s::interval
  AND latest.max_ts IS NOT NULL
  AND x.ts < latest.max_ts - %(bar_interval)s::interval
ORDER BY x.ts
"""
    return (
        sql,
        {
            "symbols": [symbol_x, symbol_y],
            "symbol_x": symbol_x,
            "symbol_y": symbol_y,
            "timeframe": timeframe,
            "lookback": f"{lookback_days} days",
            "bar_interval": BAR_INTERVALS[timeframe],
        },
    )


def analyze_pair_precheck(
    rows: Sequence[Mapping[str, Any] | PairBar],
    *,
    config: PairPrecheckConfig | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Run A3 stats-first precheck on aligned pair rows."""
    cfg = config or PairPrecheckConfig()
    bars = _normalize_pair_rows(rows)
    generated = generated_at or datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "runner_version": RUNNER_VERSION,
        "alpha_source_id": A3_ALPHA_SOURCE_ID,
        "generated_at_utc": generated.isoformat(),
        "symbols": [cfg.symbol_x, cfg.symbol_y],
        "timeframe": cfg.timeframe,
        "lane": "stats_first_draft",
        "stage0_ready_candidate": False,
        "eligible_for_demo_canary": False,
        "governance_attest": {
            "read_only": True,
            "emits_only": "draft_precheck_verdict",
            "no_stage0_ready": True,
            "no_auto_promote": True,
            "no_order_or_fill": True,
            "no_toml_mutation": True,
        },
        "config": _config_summary(cfg),
        "data_window": _data_window(bars),
    }
    if len(bars) < cfg.min_aligned_bars:
        result.update(
            {
                "verdict": "observe_more",
                "precheck_ready_for_pa_spec": False,
                "fail_reasons": [
                    f"aligned_bars {len(bars)} < min_aligned_bars {cfg.min_aligned_bars}"
                ],
                "cointegration": None,
                "fee_adjusted_replay": None,
                "verdict_basis": "insufficient aligned BTC/ETH klines",
            }
        )
        return result

    x_logs = [math.log(bar.x_close) for bar in bars]
    y_logs = [math.log(bar.y_close) for bar in bars]
    try:
        alpha, beta, corr = _ols_intercept_slope_corr(x_logs, y_logs)
    except ValueError as exc:
        result.update(
            {
                "verdict": "reject",
                "precheck_ready_for_pa_spec": False,
                "fail_reasons": [f"ols_unavailable: {exc}"],
                "cointegration": None,
                "fee_adjusted_replay": None,
                "verdict_basis": "pair price series variance is not usable",
            }
        )
        return result
    spread = [y - (alpha + beta * x) for x, y in zip(x_logs, y_logs)]
    coint = _cointegration_proxy(spread, corr=corr, beta=beta, alpha=alpha, cfg=cfg)
    replay = _replay_shift1_zscore_pairs(bars, spread, cfg)
    verdict, ready, reasons, basis = _verdict(coint, replay, cfg)
    result.update(
        {
            "cointegration": coint,
            "fee_adjusted_replay": replay,
            "verdict": verdict,
            "precheck_ready_for_pa_spec": ready,
            "fail_reasons": reasons,
            "verdict_basis": basis,
        }
    )
    return _clean_json(result)


def fetch_pair_rows(
    conn: Any,
    *,
    symbol_x: str,
    symbol_y: str,
    timeframe: str,
    lookback_days: int,
) -> list[dict[str, Any]]:
    """Fetch aligned pair klines through a psycopg2-like connection."""
    sql, params = build_pairs_kline_query(
        symbol_x=symbol_x,
        symbol_y=symbol_y,
        timeframe=timeframe,
        lookback_days=lookback_days,
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], Mapping):
            return [dict(row) for row in rows]
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]


def _normalize_pair_rows(rows: Sequence[Mapping[str, Any] | PairBar]) -> list[PairBar]:
    out: list[PairBar] = []
    for row in rows:
        if isinstance(row, PairBar):
            bar = row
        else:
            bar = PairBar(
                ts=row.get("ts"),
                x_close=_positive_float(row.get("x_close")),
                y_close=_positive_float(row.get("y_close")),
            )
        if bar.x_close > 0.0 and bar.y_close > 0.0:
            out.append(bar)
    return sorted(out, key=lambda item: _ts_sort_key(item.ts))


def _cointegration_proxy(
    spread: Sequence[float],
    *,
    corr: float,
    beta: float,
    alpha: float,
    cfg: PairPrecheckConfig,
) -> dict[str, Any]:
    adf = _adf_like_stats(spread)
    half_life = adf.get("half_life_bars")
    half_life_pass = (
        isinstance(half_life, (int, float))
        and 0.0 < float(half_life) <= cfg.max_half_life_bars
    )
    corr_pass = abs(corr) >= cfg.min_abs_corr
    adf_pass = (
        adf.get("t_stat") is not None
        and float(adf["t_stat"]) <= cfg.adf_t_stat_max
    )
    return {
        "method": "engle_granger_proxy_ols_residual_ar1",
        "n_aligned_bars": len(spread),
        "hedge_model": "log_y = alpha + beta * log_x",
        "alpha": alpha,
        "beta": beta,
        "pearson_corr_log_prices": corr,
        "min_abs_corr": cfg.min_abs_corr,
        "corr_pass": corr_pass,
        "adf_like": adf,
        "adf_t_stat_max": cfg.adf_t_stat_max,
        "adf_pass": adf_pass,
        "max_half_life_bars": cfg.max_half_life_bars,
        "half_life_pass": half_life_pass,
        "cointegration_pass": corr_pass and adf_pass and half_life_pass,
    }


def _replay_shift1_zscore_pairs(
    bars: Sequence[PairBar],
    spread: Sequence[float],
    cfg: PairPrecheckConfig,
) -> dict[str, Any]:
    zscores = _shift1_zscores(spread, cfg.rolling_window)
    trades: list[dict[str, Any]] = []
    entry_index: int | None = None
    entry_signal_index: int | None = None
    entry_spread = 0.0
    entry_z = 0.0
    direction = 0
    i = cfg.rolling_window
    while i < len(spread) - 1:
        z = zscores[i]
        if z is None:
            i += 1
            continue
        if entry_index is None:
            if z >= cfg.entry_z or z <= -cfg.entry_z:
                direction = -1 if z >= cfg.entry_z else 1
                entry_signal_index = i
                entry_index = i + 1
                entry_spread = spread[entry_index]
                entry_z = z
                i = entry_index
            else:
                i += 1
            continue

        held = i - entry_index
        should_exit = abs(z) <= cfg.exit_z or held >= cfg.max_hold_bars
        if should_exit:
            exit_index = min(i + 1, len(spread) - 1)
            if exit_index > entry_index and entry_signal_index is not None:
                gross = direction * (spread[exit_index] - entry_spread) * 10_000.0
                net = gross - cfg.roundtrip_cost_bps
                trades.append(
                    {
                        "side": "long_spread" if direction > 0 else "short_spread",
                        "entry_signal_ts": _iso_ts(bars[entry_signal_index].ts),
                        "entry_ts": _iso_ts(bars[entry_index].ts),
                        "exit_ts": _iso_ts(bars[exit_index].ts),
                        "bars_held": exit_index - entry_index,
                        "entry_z": entry_z,
                        "exit_z": z,
                        "gross_bps": gross,
                        "roundtrip_cost_bps": cfg.roundtrip_cost_bps,
                        "net_bps": net,
                        "exit_reason": "zscore_exit" if abs(z) <= cfg.exit_z else "max_hold",
                    }
                )
            entry_index = None
            entry_signal_index = None
            direction = 0
            i = exit_index + 1
            continue
        i += 1

    if entry_index is not None and entry_signal_index is not None:
        exit_index = len(spread) - 1
        if exit_index > entry_index:
            gross = direction * (spread[exit_index] - entry_spread) * 10_000.0
            trades.append(
                {
                    "side": "long_spread" if direction > 0 else "short_spread",
                    "entry_signal_ts": _iso_ts(bars[entry_signal_index].ts),
                    "entry_ts": _iso_ts(bars[entry_index].ts),
                    "exit_ts": _iso_ts(bars[exit_index].ts),
                    "bars_held": exit_index - entry_index,
                    "entry_z": entry_z,
                    "exit_z": zscores[exit_index],
                    "gross_bps": gross,
                    "roundtrip_cost_bps": cfg.roundtrip_cost_bps,
                    "net_bps": gross - cfg.roundtrip_cost_bps,
                    "exit_reason": "forced_end",
                }
            )

    nets = [float(trade["net_bps"]) for trade in trades]
    gross = [float(trade["gross_bps"]) for trade in trades]
    avg_net = sum(nets) / len(nets) if nets else None
    avg_gross = sum(gross) / len(gross) if gross else None
    first, second = _split_trade_avgs(trades)
    subperiod_pass = (
        first is not None
        and second is not None
        and first > cfg.min_avg_net_bps
        and second > cfg.min_avg_net_bps
    )
    fee_gate_pass = (
        len(trades) >= cfg.min_trades
        and avg_net is not None
        and avg_net > cfg.min_avg_net_bps
        and subperiod_pass
    )
    return {
        "method": "shift1_rolling_zscore_next_bar_entry",
        "n_trades": len(trades),
        "min_trades": cfg.min_trades,
        "avg_gross_bps": avg_gross,
        "avg_net_bps": avg_net,
        "win_rate": _win_rate(nets),
        "max_drawdown_bps": _max_drawdown(nets),
        "first_half_avg_net_bps": first,
        "second_half_avg_net_bps": second,
        "subperiod_pass": subperiod_pass,
        "fee_gate_pass": fee_gate_pass,
        "sample_classification": "sufficient" if len(trades) >= cfg.min_trades else "sample_insufficient",
        "trade_examples": trades[:5],
    }


def _verdict(
    coint: Mapping[str, Any],
    replay: Mapping[str, Any],
    cfg: PairPrecheckConfig,
) -> tuple[str, bool, list[str], str]:
    reasons: list[str] = []
    if not coint.get("cointegration_pass"):
        if not coint.get("corr_pass"):
            reasons.append("correlation_breakdown")
        if not coint.get("adf_pass"):
            reasons.append("cointegration_adf_proxy_fail")
        if not coint.get("half_life_pass"):
            reasons.append("half_life_out_of_bounds")
        return "reject", False, reasons, "cointegration or half-life precheck failed"
    if replay.get("sample_classification") == "sample_insufficient":
        reasons.append("fee_replay_sample_insufficient")
        return "observe_more", False, reasons, "cointegration passed but replay trade sample is insufficient"
    if not replay.get("fee_gate_pass"):
        reasons.append("fee_adjusted_replay_fail")
        avg_net = replay.get("avg_net_bps")
        if avg_net is not None and float(avg_net) <= cfg.min_avg_net_bps:
            reasons.append("avg_net_not_positive_after_two_leg_cost")
        if replay.get("subperiod_pass") is not True:
            reasons.append("subperiod_stability_fail")
        return "reject", False, reasons, "fee-adjusted replay did not pass"
    return (
        "draft_only",
        True,
        ["cointegration_and_fee_replay_pass_stats_first_only"],
        "A3 precheck passed; DRAFT/spec input only, no Stage 0 or Demo activation",
    )


def _ols_intercept_slope_corr(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float]:
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("OLS requires aligned x/y length >= 3")
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    sxx = sum((value - mx) ** 2 for value in x)
    syy = sum((value - my) ** 2 for value in y)
    if sxx <= 1e-18 or syy <= 1e-18:
        raise ValueError("OLS variance is zero")
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    beta = sxy / sxx
    alpha = my - beta * mx
    corr = sxy / math.sqrt(sxx * syy)
    return alpha, beta, max(-1.0, min(1.0, corr))


def _adf_like_stats(spread: Sequence[float]) -> dict[str, Any]:
    lagged = list(spread[:-1])
    delta = [spread[i] - spread[i - 1] for i in range(1, len(spread))]
    if len(lagged) < 3:
        return {"t_stat": None, "gamma": None, "phi": None, "half_life_bars": None}
    try:
        intercept, gamma, _corr = _ols_intercept_slope_corr(lagged, delta)
    except ValueError:
        return {"t_stat": None, "gamma": None, "phi": None, "half_life_bars": None}
    fitted = [intercept + gamma * value for value in lagged]
    residuals = [actual - fit for actual, fit in zip(delta, fitted)]
    sxx = sum((value - (sum(lagged) / len(lagged))) ** 2 for value in lagged)
    dof = max(1, len(lagged) - 2)
    sigma2 = sum(value * value for value in residuals) / dof
    se = math.sqrt(sigma2 / sxx) if sxx > 1e-18 else None
    t_stat = gamma / se if se and se > 1e-18 else None
    phi = 1.0 + gamma
    half_life = None
    if 0.0 < phi < 1.0:
        half_life = math.log(0.5) / math.log(phi)
    return {
        "t_stat": t_stat,
        "gamma": gamma,
        "phi": phi,
        "half_life_bars": half_life,
    }


def _shift1_zscores(values: Sequence[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for index in range(window, len(values)):
        prev = values[index - window:index]
        mean = sum(prev) / window
        variance = sum((value - mean) ** 2 for value in prev) / window
        std = math.sqrt(variance)
        if std > 1e-18:
            out[index] = (values[index] - mean) / std
    return out


def _split_trade_avgs(trades: Sequence[Mapping[str, Any]]) -> tuple[float | None, float | None]:
    if len(trades) < 2:
        return None, None
    midpoint = len(trades) // 2
    first = [float(trade["net_bps"]) for trade in trades[:midpoint]]
    second = [float(trade["net_bps"]) for trade in trades[midpoint:]]
    return sum(first) / len(first), sum(second) / len(second)


def _max_drawdown(nets: Sequence[float]) -> float | None:
    if not nets:
        return None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in nets:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _win_rate(nets: Sequence[float]) -> float | None:
    if not nets:
        return None
    return sum(1 for value in nets if value > 0.0) / len(nets)


def _config_summary(cfg: PairPrecheckConfig) -> dict[str, Any]:
    return {
        "min_aligned_bars": cfg.min_aligned_bars,
        "min_abs_corr": cfg.min_abs_corr,
        "adf_t_stat_max": cfg.adf_t_stat_max,
        "max_half_life_bars": cfg.max_half_life_bars,
        "rolling_window": cfg.rolling_window,
        "entry_z": cfg.entry_z,
        "exit_z": cfg.exit_z,
        "max_hold_bars": cfg.max_hold_bars,
        "min_trades": cfg.min_trades,
        "roundtrip_cost_bps": cfg.roundtrip_cost_bps,
        "min_avg_net_bps": cfg.min_avg_net_bps,
    }


def _data_window(bars: Sequence[PairBar]) -> dict[str, Any]:
    return {
        "n_aligned_bars": len(bars),
        "start_ts": _iso_ts(bars[0].ts) if bars else None,
        "end_ts": _iso_ts(bars[-1].ts) if bars else None,
        "source_tables": ["market.klines"],
    }


def _positive_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result) or result <= 0.0:
        return 0.0
    return result


def _ts_sort_key(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return float(timestamp())
    return 0.0


def _iso_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return value


def _load_runtime_pg_env() -> None:
    """Load canonical Linux runtime PG env when explicit env is absent."""
    if os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        return
    if os.environ.get("POSTGRES_USER") and os.environ.get("POSTGRES_DB"):
        return
    secrets_root = Path(
        os.environ.get("OPENCLAW_SECRETS_ROOT")
        or Path.home() / "BybitOpenClaw" / "secrets"
    )
    env_path = secrets_root / "environment_files" / "basic_system_services.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        if item.startswith("export "):
            item = item[len("export "):]
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get_conn() -> Any:
    import psycopg2  # type: ignore

    _load_runtime_pg_env()
    dsn = os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn, application_name="openclaw_a3_pairs_precheck")
    required = {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB"),
        "user": os.environ.get("POSTGRES_USER"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError("missing PG connection env: " + ", ".join(missing))
    password = os.environ.get("POSTGRES_PASSWORD")
    if password:
        required["password"] = password
    return psycopg2.connect(**required, application_name="openclaw_a3_pairs_precheck")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A3 BTC/ETH pairs DRAFT precheck")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--symbols", default=f"{DEFAULT_SYMBOL_X},{DEFAULT_SYMBOL_Y}")
    parser.add_argument("--timeframe", choices=tuple(BAR_INTERVALS), default=DEFAULT_TIMEFRAME)
    parser.add_argument("--min-aligned-bars", type=int, default=300)
    parser.add_argument("--min-abs-corr", type=float, default=0.75)
    parser.add_argument("--adf-t-stat-max", type=float, default=-2.8)
    parser.add_argument("--max-half-life-bars", type=float, default=288.0)
    parser.add_argument("--rolling-window", type=int, default=96)
    parser.add_argument("--entry-z", type=float, default=2.0)
    parser.add_argument("--exit-z", type=float, default=0.5)
    parser.add_argument("--max-hold-bars", type=int, default=144)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--roundtrip-cost-bps", type=float, default=24.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if len(symbols) != 2:
        print("[FATAL] --symbols must contain exactly two symbols", file=sys.stderr)
        return 2
    cfg = PairPrecheckConfig(
        symbol_x=symbols[0],
        symbol_y=symbols[1],
        timeframe=args.timeframe,
        min_aligned_bars=args.min_aligned_bars,
        min_abs_corr=args.min_abs_corr,
        adf_t_stat_max=args.adf_t_stat_max,
        max_half_life_bars=args.max_half_life_bars,
        rolling_window=args.rolling_window,
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        max_hold_bars=args.max_hold_bars,
        min_trades=args.min_trades,
        roundtrip_cost_bps=args.roundtrip_cost_bps,
    )
    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] PG connection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        rows = fetch_pair_rows(
            conn,
            symbol_x=cfg.symbol_x,
            symbol_y=cfg.symbol_y,
            timeframe=cfg.timeframe,
            lookback_days=args.lookback_days,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] A3 query failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    packet = analyze_pair_precheck(rows, config=cfg)
    text = json.dumps(_clean_json(packet), ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] packet written: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
