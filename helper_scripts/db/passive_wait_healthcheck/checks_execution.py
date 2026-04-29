"""Execution-shape healthchecks.
執行形態 healthcheck。

These checks compare configuration intent against the runtime records written
by the engine. They stay separate from ``checks_strategy.py`` so that already
large module does not grow further.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _load_demo_strategy_params() -> tuple[dict[str, Any] | None, str]:
    """Load ``settings/strategy_params_demo.toml`` fail-soft.
    讀取 demo strategy params TOML；失敗時回診斷，不拋例外。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return (None, "tomllib/tomli unavailable")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"
    if not toml_path.exists():
        return (None, f"strategy_params_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return (None, f"TOML parse error: {exc}")
    if not isinstance(data, dict):
        return (None, "strategy_params_demo.toml did not parse to a table")
    return (data, "ok")


def _maker_enabled_demo_strategies() -> tuple[list[str], str]:
    """Return active demo strategies that intend maker entries.
    回傳 demo TOML 中 active 且 use_maker_entry=true 的策略。
    """
    data, diag = _load_demo_strategy_params()
    if data is None:
        return ([], diag)

    strategies: list[str] = []
    for name, section in data.items():
        if not isinstance(section, dict):
            continue
        if section.get("active") is False:
            continue
        if section.get("use_maker_entry") is True:
            strategies.append(str(name))
    return (sorted(strategies), "ok")


def check_maker_entry_intent_drift(cur) -> tuple[str, str]:
    """[32] Demo maker-entry intent drift.

    If demo TOML says a strategy should use maker entries, its recent entry
    intents should not be ``order_type='market'``. This checks
    ``trading.intents`` rather than ``trading.orders`` because close orders are
    intentionally Market and the orders table does not persist ``is_close``.

    [32] Demo maker 入場 intent 漂移。若 demo TOML 指定 maker entry，近期
    入場 intent 不應仍為 market。使用 trading.intents 而非 orders，因為
    平倉本來就是 Market，orders 表也沒有 is_close 可安全過濾。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    strategies, diag = _maker_enabled_demo_strategies()
    if not strategies:
        if diag == "ok":
            return ("PASS", "no active demo strategies with use_maker_entry=true")
        return ("WARN", f"maker-entry TOML read unavailable: {diag}")

    placeholders = ", ".join(["%s"] * len(strategies))
    try:
        cur.execute(
            f"""
            SELECT strategy_name, lower(order_type) AS order_type, COUNT(*)::int AS n
            FROM trading.intents
            WHERE ts > now() - interval '30 minutes'
              AND engine_mode = 'demo'
              AND strategy_name IN ({placeholders})
            GROUP BY strategy_name, lower(order_type)
            ORDER BY strategy_name, lower(order_type)
            """,
            tuple(strategies),
        )
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return ("WARN", f"maker-entry intent drift query failed: {exc}")

    totals: dict[str, int] = {name: 0 for name in strategies}
    market: dict[str, int] = {name: 0 for name in strategies}
    limit: dict[str, int] = {name: 0 for name in strategies}
    other: dict[str, int] = {name: 0 for name in strategies}
    for strategy_name, order_type, n in rows:
        name = str(strategy_name)
        typ = str(order_type or "").lower()
        count = int(n or 0)
        totals[name] = totals.get(name, 0) + count
        if typ == "market":
            market[name] = market.get(name, 0) + count
        elif typ == "limit":
            limit[name] = limit.get(name, 0) + count
        else:
            other[name] = other.get(name, 0) + count

    active_rows = [name for name, total in totals.items() if total > 0]
    if not active_rows:
        return (
            "PASS",
            "maker-enabled demo strategies emitted no entry intents in 30m "
            f"({', '.join(strategies)})",
        )

    parts = [
        f"{name}: total={totals[name]}, market={market[name]}, "
        f"limit={limit[name]}, other={other[name]}"
        for name in active_rows
    ]
    bad = [name for name in active_rows if market[name] > 0]
    if bad:
        return (
            "FAIL",
            "maker-enabled demo strategies emitted market entry intents — "
            + "; ".join(parts)
            + " — check StrategyParams partial-merge / persisted replay drift",
        )
    return ("PASS", "maker-entry intent shape ok — " + "; ".join(parts))
