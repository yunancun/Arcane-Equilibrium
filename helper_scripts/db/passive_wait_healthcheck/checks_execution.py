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

from .shared import _engine_process_age_minutes

MAKER_FEE_RATE = 0.00020
TAKER_FEE_RATE = 0.00055
MAKER_FEE_CUTOFF = (MAKER_FEE_RATE + TAKER_FEE_RATE) / 2.0
MAKER_FEE_DROP_TARGET_PCT = 60.0
MAKER_FILL_MIN_SAMPLE = 30


def check_intent_signal_attribution(cur) -> tuple[str, str]:
    """[34] Recent exchange intents must link to a persisted strategy signal.
    近期 demo/live_demo/live intent 必須能 join 到策略 signal。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute(
            "SELECT to_regclass('trading.intents') IS NOT NULL, "
            "       to_regclass('trading.signals') IS NOT NULL"
        )
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"intent/signal table existence check failed: {exc}")
    if not exists or not exists[0] or not exists[1]:
        return ("FAIL", "trading.intents or trading.signals missing — migrations incomplete")

    sql = (
        "WITH recent AS ( "
        "  SELECT intent_id, signal_id, context_id, engine_mode "
        "  FROM trading.intents "
        "  WHERE ts > now() - interval '30 minutes' "
        "    AND engine_mode IN ('demo', 'live_demo', 'live') "
        "    AND COALESCE(details->>'source', '') <> 'command' "
        "), joined AS ( "
        "  SELECT r.*, s.context_id AS signal_context_id "
        "  FROM recent r "
        "  LEFT JOIN trading.signals s ON s.signal_id = r.signal_id "
        ") "
        "SELECT count(*) AS total, "
        "  count(*) FILTER (WHERE signal_id IS NULL OR signal_id = '') AS empty_signal_id, "
        "  count(*) FILTER (WHERE signal_id IS NOT NULL AND signal_id <> '' "
        "                   AND signal_context_id IS NULL) AS missing_signal, "
        "  count(*) FILTER (WHERE signal_context_id IS NOT NULL "
        "                   AND signal_context_id <> context_id) AS context_mismatch "
        "FROM joined"
    )
    try:
        cur.execute(sql)
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"intent signal attribution query failed: {type(exc).__name__}: {exc}")

    if row is None:
        return ("WARN", "intent signal attribution query returned no row")

    total = int(row[0] or 0)
    empty_signal_id = int(row[1] or 0)
    missing_signal = int(row[2] or 0)
    context_mismatch = int(row[3] or 0)
    base = (
        f"30min exchange intents: total={total}, empty_signal_id={empty_signal_id}, "
        f"missing_signal={missing_signal}, context_mismatch={context_mismatch}"
    )
    if total == 0:
        return ("PASS", base + " — no recent exchange intents")
    broken = empty_signal_id + missing_signal + context_mismatch
    if broken > 0:
        return (
            "FAIL",
            base + " — attribution chain broken; inspect strategy_signal/persist_intent path",
        )
    return ("PASS", base + " — attribution chain linked")


def check_mlde_learning_data_contract(cur) -> tuple[str, str]:
    """[35] ML/Dream training rows must be attributed and post-fee labeled."""
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"MLDE training view existence check failed: {exc}")
    if not row or not row[0]:
        return ("FAIL", "learning.mlde_edge_training_rows missing — V031 not applied")

    try:
        cur.execute(
            """
            SELECT
                count(*)::int AS total,
                count(*) FILTER (WHERE attribution_chain_ok)::int AS attributed,
                count(*) FILTER (
                    WHERE attribution_chain_ok
                      AND net_bps_after_fee IS NOT NULL
                      AND linucb_arm_id IS NOT NULL
                      AND jsonb_typeof(context_features) = 'array'
                      AND jsonb_array_length(context_features) = 8
                )::int AS linucb_ready,
                count(*) FILTER (
                    WHERE signal_id IS NULL OR signal_id = ''
                       OR context_id IS NULL OR context_id = ''
                )::int AS missing_ids,
                count(*) FILTER (WHERE net_bps_after_fee IS NULL)::int AS missing_reward
            FROM learning.mlde_edge_training_rows
            WHERE ts > now() - interval '7 days'
              AND engine_mode IN ('demo', 'live_demo')
            """
        )
        total, attributed, linucb_ready, missing_ids, missing_reward = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"MLDE training contract query failed: {type(exc).__name__}: {exc}")

    total = _as_int(total)
    attributed = _as_int(attributed)
    linucb_ready = _as_int(linucb_ready)
    missing_ids = _as_int(missing_ids)
    missing_reward = _as_int(missing_reward)
    base = (
        f"7d demo/live_demo MLDE rows total={total}, attributed={attributed}, "
        f"linucb_ready={linucb_ready}, missing_ids={missing_ids}, missing_reward={missing_reward}"
    )
    if total == 0:
        return ("WARN", base + " — no post-V031 MLDE training rows yet")
    if missing_ids > 0:
        return ("FAIL", base + " — attribution ids missing; scanner→signal→intent chain regressed")
    if linucb_ready == 0:
        return ("WARN", base + " — no LinUCB-ready post-fee rows yet")
    return ("PASS", base + " — learning data contract usable")


def check_mlde_shadow_recommendations(cur) -> tuple[str, str]:
    """[36] ML/Dream advisory table exists and live applied rows need leases."""
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute("SELECT to_regclass('learning.mlde_shadow_recommendations') IS NOT NULL")
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"MLDE advisory table existence check failed: {exc}")
    if not row or not row[0]:
        return ("FAIL", "learning.mlde_shadow_recommendations missing — V031 not applied")

    try:
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE ts > now() - interval '24 hours')::int AS recent,
                count(DISTINCT source) FILTER (WHERE ts > now() - interval '24 hours')::int AS sources,
                count(*) FILTER (
                    WHERE engine_mode IN ('live', 'live_demo')
                      AND applied
                      AND COALESCE(decision_lease_id, '') = ''
                )::int AS live_applied_without_lease
            FROM learning.mlde_shadow_recommendations
            """
        )
        recent, sources, live_applied_without_lease = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"MLDE advisory query failed: {type(exc).__name__}: {exc}")

    recent = _as_int(recent)
    sources = _as_int(sources)
    live_applied_without_lease = _as_int(live_applied_without_lease)
    base = (
        f"24h MLDE advisory rows={recent}, sources={sources}, "
        f"live_applied_without_lease={live_applied_without_lease}"
    )
    if live_applied_without_lease > 0:
        return (
            "FAIL",
            base + " — live/live_demo applied advisory row lacks Decision Lease",
        )
    if recent == 0:
        return ("WARN", base + " — no recent MLDE shadow/advisory outputs yet")
    return ("PASS", base + " — advisory-only boundary intact")


def _load_strategy_params(kind: str) -> tuple[dict[str, Any] | None, str]:
    """Load ``settings/strategy_params_<kind>.toml`` fail-soft.
    讀取指定 kind 的 strategy params TOML；失敗時回診斷，不拋例外。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return (None, "tomllib/tomli unavailable")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / f"strategy_params_{kind}.toml"
    if not toml_path.exists():
        return (None, f"strategy_params_{kind}.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return (None, f"TOML parse error: {exc}")
    if not isinstance(data, dict):
        return (None, f"strategy_params_{kind}.toml did not parse to a table")
    return (data, "ok")


def _maker_enabled_strategies(kind: str) -> tuple[list[str], str]:
    """Return active strategies that intend maker entries for one TOML kind.
    回傳指定 TOML 中 active 且 use_maker_entry=true 的策略。
    """
    data, diag = _load_strategy_params(kind)
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


def _maker_entry_expectations() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Build expected ``(health_mode, engine_mode, strategy_name)`` rows.
    建立應該使用 maker entry 的 health_mode / engine_mode / strategy 清單。
    """
    expectations: list[tuple[str, str, str]] = []
    diagnostics: list[str] = []

    demo_strategies, demo_diag = _maker_enabled_strategies("demo")
    if demo_diag != "ok":
        diagnostics.append(f"demo: {demo_diag}")
    for strategy in demo_strategies:
        expectations.append(("demo", "demo", strategy))

    live_strategies, live_diag = _maker_enabled_strategies("live")
    if live_diag != "ok":
        diagnostics.append(f"live: {live_diag}")
    for strategy in live_strategies:
        # Runtime DB writes may tag the live exchange pipeline as live_demo
        # while IPC/TOML still route through PipelineKind::Live.
        # runtime DB 可能把 live exchange pipeline 標為 live_demo，但 IPC/TOML
        # 仍走 PipelineKind::Live；這裡同時覆蓋三種常見標籤。
        for engine_mode in ("live", "live_demo", "live_testnet"):
            expectations.append(("live", engine_mode, strategy))

    return (expectations, diagnostics)


def check_maker_entry_intent_drift(cur) -> tuple[str, str]:
    """[32] Maker-entry intent drift across demo and live-demo exchange paths.

    If demo/live TOML says a strategy should use maker entries, its recent
    entry intents should not be ``order_type='market'``. This checks
    ``trading.intents`` rather than ``trading.orders`` because close orders are
    intentionally Market and the orders table does not persist ``is_close``.

    [32] maker 入場 intent 漂移。若 demo/live TOML 指定 maker entry，近期
    入場 intent 不應仍為 market。使用 trading.intents 而非 orders，因為平倉
    本來就是 Market，orders 表也沒有 is_close 可安全過濾。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    expectations, diagnostics = _maker_entry_expectations()
    if not expectations:
        if not diagnostics:
            return ("PASS", "no active strategies with use_maker_entry=true")
        return ("WARN", "maker-entry TOML read unavailable: " + "; ".join(diagnostics))

    window_minutes = 30.0
    window_note = "30m"
    engine_age_min, _engine_age_diag = _engine_process_age_minutes()
    if engine_age_min is not None and engine_age_min < 30.0:
        window_minutes = max(1.0, engine_age_min)
        window_note = f"{window_minutes:.1f}m post-restart"

    values_sql = ", ".join(["(%s, %s, %s)"] * len(expectations))
    query_params: list[Any] = []
    for health_mode, engine_mode, strategy_name in expectations:
        query_params.extend([health_mode, engine_mode, strategy_name])
    query_params.append(window_minutes)

    try:
        cur.execute(
            f"""
            WITH expected(health_mode, engine_mode, strategy_name) AS (
                VALUES {values_sql}
            )
            SELECT
                expected.health_mode,
                intents.strategy_name,
                lower(intents.order_type) AS order_type,
                COUNT(*)::int AS n
            FROM expected
            JOIN trading.intents AS intents
              ON intents.engine_mode = expected.engine_mode
             AND intents.strategy_name = expected.strategy_name
            WHERE intents.ts > now() - (%s::double precision * interval '1 minute')
            GROUP BY expected.health_mode, intents.strategy_name, lower(intents.order_type)
            ORDER BY expected.health_mode, intents.strategy_name, lower(intents.order_type)
            """,
            tuple(query_params),
        )
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return ("WARN", f"maker-entry intent drift query failed: {exc}")

    expected_keys = sorted({(mode, strategy) for mode, _, strategy in expectations})
    totals: dict[tuple[str, str], int] = {key: 0 for key in expected_keys}
    market: dict[tuple[str, str], int] = {key: 0 for key in expected_keys}
    limit: dict[tuple[str, str], int] = {key: 0 for key in expected_keys}
    other: dict[tuple[str, str], int] = {key: 0 for key in expected_keys}
    for health_mode, strategy_name, order_type, n in rows:
        key = (str(health_mode), str(strategy_name))
        typ = str(order_type or "").lower()
        count = int(n or 0)
        totals[key] = totals.get(key, 0) + count
        if typ == "market":
            market[key] = market.get(key, 0) + count
        elif typ == "limit":
            limit[key] = limit.get(key, 0) + count
        else:
            other[key] = other.get(key, 0) + count

    active_rows = [key for key, total in totals.items() if total > 0]
    if not active_rows:
        enabled = ", ".join(f"{mode}/{strategy}" for mode, strategy in expected_keys)
        return (
            "PASS",
            f"maker-enabled strategies emitted no entry intents in {window_note} ({enabled})",
        )

    parts = [
        f"{mode}/{strategy}: total={totals[(mode, strategy)]}, "
        f"market={market[(mode, strategy)]}, limit={limit[(mode, strategy)]}, "
        f"other={other[(mode, strategy)]}"
        for mode, strategy in active_rows
    ]
    bad = [key for key in active_rows if market[key] > 0]
    if bad:
        return (
            "FAIL",
            "maker-enabled strategies emitted market entry intents — "
            + f"window={window_note}; "
            + "; ".join(parts)
            + " — check StrategyParams partial-merge / TOML runtime drift",
        )
    return ("PASS", f"maker-entry intent shape ok — window={window_note}; " + "; ".join(parts))


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fee_drop_pct(avg_fee_rate: float) -> float:
    fee_span = TAKER_FEE_RATE - MAKER_FEE_RATE
    if fee_span <= 0.0:
        return 0.0
    pct = (TAKER_FEE_RATE - avg_fee_rate) / fee_span * 100.0
    return max(0.0, min(100.0, pct))


def _format_strategy_slices(rows: list[tuple[Any, ...]]) -> str:
    parts: list[str] = []
    for row in rows[:8]:
        name = str(row[0] or "unknown")
        total = _as_int(row[1])
        maker_like = _as_int(row[2])
        avg_fee_rate = _as_float(row[3], TAKER_FEE_RATE)
        maker_pct = maker_like / total * 100.0 if total else 0.0
        fee_drop = _fee_drop_pct(avg_fee_rate)
        parts.append(
            f"{name}: n={total}, maker_like={maker_pct:.1f}%, "
            f"avg_fee={avg_fee_rate * 10_000:.2f}bps, fee_drop={fee_drop:.1f}%"
        )
    return "; ".join(parts) if parts else "no per-strategy rows"


_MAKER_FILL_CTE = """
WITH entry_fills AS (
    SELECT
        f.strategy_name,
        lower(coalesce(f.liquidity_role, '')) AS liquidity_role,
        lower(coalesce(o.order_type, '')) AS order_type,
        lower(coalesce(o.time_in_force, '')) AS time_in_force,
        coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
        CASE
            WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
              OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
            THEN 1
            ELSE 0
        END AS maker_like
    FROM trading.fills f
    LEFT JOIN trading.orders o
      ON o.order_id = f.order_id
     AND o.ts > now() - interval '8 days'
    WHERE f.ts > now() - interval '7 days'
      AND f.engine_mode IN ('demo', 'live_demo')
      AND coalesce(f.strategy_name, '') <> ''
      AND f.strategy_name NOT LIKE 'risk_close:%%'
      AND f.strategy_name NOT LIKE 'strategy_close:%%'
      AND f.strategy_name NOT LIKE 'ipc_close%%'
      AND f.strategy_name NOT LIKE 'unattributed:%%'
      AND coalesce(f.exit_source, '') = ''
)
"""


def check_maker_fill_rate(cur) -> tuple[str, str]:
    """[33] G2-01 PostOnly maker-fill / fee-drop monitor.

    G2-01 validates whether PostOnly demo execution actually reduces fees.
    Earlier docs mistakenly mapped this to [3], but [3] is the
    exit_features writer check. This dedicated check measures the last 7d of
    demo/live_demo entry fills, joins orders only for limit diagnostics, and
    scores acceptance on effective fee-drop from taker 5.5bps toward maker
    2.0bps. ``trading.orders.time_in_force`` is not written by the current
    Rust order writer, so fee_rate/liquidity_role are the runtime truth.

    [33] G2-01 PostOnly maker 成交 / fee-drop 監控。過去文件曾誤標 [3]，
    但 [3] 實際是 exit_features writer；此處用 7d demo/live_demo 入場 fill
    的有效 fee_rate 驗證 5.5bps taker → 2.0bps maker 的降費幅度。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    params = (TAKER_FEE_RATE, TAKER_FEE_RATE, MAKER_FEE_CUTOFF)
    summary_sql = (
        _MAKER_FILL_CTE
        + """
SELECT
    count(*)::int AS total_fills,
    coalesce(sum(maker_like), 0)::int AS maker_like_fills,
    avg(effective_fee_rate)::float8 AS avg_fee_rate,
    count(*) FILTER (WHERE order_type = 'limit')::int AS limit_order_fills,
    count(*) FILTER (WHERE time_in_force = 'postonly')::int AS postonly_order_fills
FROM entry_fills
"""
    )
    strategy_sql = (
        _MAKER_FILL_CTE
        + """
SELECT
    strategy_name,
    count(*)::int AS total_fills,
    coalesce(sum(maker_like), 0)::int AS maker_like_fills,
    avg(effective_fee_rate)::float8 AS avg_fee_rate
FROM entry_fills
GROUP BY strategy_name
ORDER BY total_fills DESC, strategy_name
LIMIT 8
"""
    )

    try:
        cur.execute(summary_sql, params)
        row = cur.fetchone()
        cur.execute(strategy_sql, params)
        strategy_rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return ("WARN", f"maker fill-rate query failed: {type(exc).__name__}: {exc}")

    if row is None:
        return ("WARN", "maker fill-rate query returned no row (PG / cursor anomaly)")

    total = _as_int(row[0])
    maker_like = _as_int(row[1])
    avg_fee_rate = _as_float(row[2], TAKER_FEE_RATE)
    limit_rows = _as_int(row[3])
    postonly_rows = _as_int(row[4])

    if total == 0:
        return (
            "PASS",
            "7d demo/live_demo entry_fills=0 — no G2-01 maker-fill sample yet",
        )

    maker_pct = maker_like / total * 100.0
    fee_drop = _fee_drop_pct(avg_fee_rate)
    limit_pct = limit_rows / total * 100.0
    postonly_pct = postonly_rows / total * 100.0
    base_msg = (
        f"7d demo/live_demo entry_fills={total}, "
        f"avg_fee={avg_fee_rate * 10_000:.2f}bps, "
        f"fee_drop={fee_drop:.1f}% target>={MAKER_FEE_DROP_TARGET_PCT:.0f}%, "
        f"maker_like={maker_like}/{total} ({maker_pct:.1f}%), "
        f"limit_order_rows={limit_rows} ({limit_pct:.1f}%), "
        f"postonly_order_rows={postonly_rows} ({postonly_pct:.1f}%); "
        f"by_strategy: {_format_strategy_slices(list(strategy_rows or []))}"
    )

    if total < MAKER_FILL_MIN_SAMPLE:
        return (
            "WARN",
            base_msg + f" — insufficient sample (<{MAKER_FILL_MIN_SAMPLE})",
        )
    if fee_drop >= MAKER_FEE_DROP_TARGET_PCT:
        return ("PASS", base_msg)
    return (
        "WARN",
        base_msg
        + " — below G2-01 PostOnly fee-drop target; keep passive monitor until settlement",
    )
