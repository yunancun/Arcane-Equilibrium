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
    """[35] ML/Dream training rows must be attributed and post-fee labeled.

    The 7d aggregate is useful for learning readiness, but it can contain
    legacy rows written before the signal_id repair. Treat attribution-id
    failures as regressions only in a short recent window so a fixed deploy can
    recover without waiting seven days.
    """
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

    recent_minutes = 30
    try:
        recent_minutes = int(os.environ.get("OPENCLAW_MLDE_ATTRIBUTION_RECENT_MINUTES", "30"))
    except ValueError:
        recent_minutes = 30
    recent_minutes = max(5, min(24 * 60, recent_minutes))
    try:
        cur.execute(
            """
            SELECT
                count(*)::int AS recent_total,
                count(*) FILTER (WHERE attribution_chain_ok)::int AS recent_attributed,
                count(*) FILTER (
                    WHERE signal_id IS NULL OR signal_id = ''
                       OR context_id IS NULL OR context_id = ''
                )::int AS recent_missing_ids
            FROM learning.mlde_edge_training_rows
            WHERE ts > now() - (%s::int || ' minutes')::interval
              AND engine_mode IN ('demo', 'live_demo')
            """,
            (recent_minutes,),
        )
        recent_total, recent_attributed, recent_missing_ids = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"MLDE recent attribution query failed: {type(exc).__name__}: {exc}")

    total = _as_int(total)
    attributed = _as_int(attributed)
    linucb_ready = _as_int(linucb_ready)
    missing_ids = _as_int(missing_ids)
    missing_reward = _as_int(missing_reward)
    recent_total = _as_int(recent_total)
    recent_attributed = _as_int(recent_attributed)
    recent_missing_ids = _as_int(recent_missing_ids)
    base = (
        f"7d demo/live_demo MLDE rows total={total}, attributed={attributed}, "
        f"linucb_ready={linucb_ready}, missing_ids={missing_ids}, missing_reward={missing_reward}; "
        f"recent_{recent_minutes}m total={recent_total}, attributed={recent_attributed}, "
        f"missing_ids={recent_missing_ids}"
    )
    if total == 0:
        return ("WARN", base + " — no post-V031 MLDE training rows yet")
    if recent_total > 0 and recent_missing_ids > 0:
        return ("FAIL", base + " — recent attribution ids missing; scanner→signal→intent chain regressed")
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


def check_mlde_demo_applier(cur) -> tuple[str, str]:
    """[37] Demo MLDE autonomous applier audit table and live lease boundary."""
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute("SELECT to_regclass('learning.mlde_param_applications') IS NOT NULL")
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"MLDE demo applier table existence check failed: {exc}")
    if not row or not row[0]:
        return ("FAIL", "learning.mlde_param_applications missing — V032 not applied")

    try:
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE ts > now() - interval '24 hours')::int AS recent,
                count(*) FILTER (
                    WHERE ts > now() - interval '24 hours'
                      AND engine_mode = 'demo'
                      AND status IN ('applied', 'dry_run')
                )::int AS demo_applied,
                count(*) FILTER (
                    WHERE ts > now() - interval '24 hours'
                      AND status = 'candidate'
                      AND requires_governance
                )::int AS governed_candidates,
                count(*) FILTER (
                    WHERE ts > now() - interval '24 hours'
                      AND status = 'failed'
                )::int AS failed,
                count(*) FILTER (
                    WHERE engine_mode IN ('live', 'live_demo')
                      AND status = 'applied'
                      AND COALESCE(decision_lease_id, '') = ''
                )::int AS live_applied_without_lease
            FROM learning.mlde_param_applications
            """
        )
        recent, demo_applied, governed_candidates, failed, live_applied_without_lease = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"MLDE demo applier query failed: {type(exc).__name__}: {exc}")

    recent = _as_int(recent)
    demo_applied = _as_int(demo_applied)
    governed_candidates = _as_int(governed_candidates)
    failed = _as_int(failed)
    live_applied_without_lease = _as_int(live_applied_without_lease)
    base = (
        f"24h MLDE applier rows={recent}, demo_applied={demo_applied}, "
        f"governed_live_candidates={governed_candidates}, failed={failed}, "
        f"live_applied_without_lease={live_applied_without_lease}"
    )
    if live_applied_without_lease > 0:
        return ("FAIL", base + " — live/live_demo applied row lacks Decision Lease")
    if failed > 0:
        return ("WARN", base + " — applier failures need inspection")
    if recent == 0:
        return ("WARN", base + " — no MLDE applier decisions yet")
    return ("PASS", base + " — demo autonomy audited, live boundary intact")


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


# ============================================================================
# [38] grid_trading single-position lifecycle drift between demo / live_demo.
# 2026-04-29 — MIT skill: data-drift-detection + ml-pipeline-maturity-audit.
# Background: GUI Learning tab 24h fills shows grid_trading at LiveDemo (157)
# vs Demo (63) — 2.5x asymmetry. risk_config_live.toml has
# trailing_distance_pct=2.0% (vs demo 3.5%) + partial_tp_enabled=true, which
# physically pushes live grid lifetimes shorter. Passive observe 7d to
# distinguish "reasonable turnover from physical config diff" vs "grid out
# of control (re-entry spiral burning fees)". Pure monitor — no enforcement,
# no business-code change, no risk_config / strategy params modification.
#
# [38] grid_trading 單倉 lifecycle 漂移（demo vs live_demo）。2026-04-29 MIT
# 設計（data-drift-detection + ml-pipeline-maturity-audit skill）。背景：GUI
# 24h fills 顯示 grid_trading LiveDemo 157 vs Demo 63（2.5x）。Live config
# trailing 2.0%（demo 3.5%）+ partial_tp 開 → 物理上 lifetime 應較短。
# 被動觀察 7d 區分「合理 turnover」vs「grid 反覆收割 fee 失控」。純監控，
# 不修 strategy / risk_config / 不阻斷 trading。
# ============================================================================

# Lifetime drift threshold: live should not be < 0.5x demo (physical
# trailing-distance ratio 2.0/3.5 = 0.571 implies ~0.5-0.7x baseline).
# Lifetime 漂移 threshold：live 不應 < 0.5x demo（trailing 比 0.571 預期 0.5-0.7x）。
GRID_LIFETIME_RATIO_WARN = 0.5
GRID_LIFETIME_RATIO_FAIL = 0.3

# Fee-burn ratio: fee_total / |pnl_total|. > 0.8 means fee dominates PnL.
# Fee-burn 比例：fee 總額 / |pnl| 總額。> 0.8 表 fee 主導 PnL。
GRID_FEE_BURN_ABS_WARN = 0.8
GRID_FEE_BURN_ABS_FAIL = 1.5
GRID_FEE_BURN_RATIO_WARN = 2.0   # live > 2x demo

# Re-entry rate: same symbol + same side within 1h is a re-entry.
# Re-entry 率：同 symbol 同 side 1h 內重新開倉。
GRID_REENTRY_RATE_WARN = 0.5
GRID_REENTRY_RATE_FAIL = 0.7
GRID_REENTRY_DELTA_WARN = 0.3    # live - demo > 0.3 absolute

# Sample-size floor — below this skip evaluation (PASS-with-note).
# 樣本下限：低於此值跳評估（PASS-with-note）。
GRID_LIFECYCLE_MIN_SAMPLE = 5


def check_grid_trading_lifecycle_drift(cur) -> tuple[str, str]:
    """[38] grid_trading single-position lifecycle drift demo vs live_demo.

    Pairing strategy: V017 ``trading.fills.entry_context_id`` JOIN — close
    fill rows carry the originating entry's context_id. ``row_number()`` picks
    first close per entry (partial_tp may produce multiple close rows).

    Three drift indicators, each tagged INFO/WARN/FAIL independently;
    final verdict = max severity. DB unreachable / 0 rows → WARN/PASS,
    never FAIL — avoid spurious alerts during low-activity windows.

    [38] grid_trading 單倉 lifecycle 漂移（demo vs live_demo）。配對策略：
    V017 ``trading.fills.entry_context_id`` JOIN（close fill 帶 entry context）。
    partial_tp 可能多筆 close，用 ``row_number()`` 取首次 close。三個漂移
    指標獨立標記，最終 verdict = max severity。DB 不通 / 0 rows → WARN/PASS，
    避免低活動期假警報。
    """
    # Per-check rollback in case caller's prior cursor errored.
    # 預先 rollback，避免 caller 上一個 cursor 出錯影響本 check。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Existence check — required tables / columns.
    # 存在性檢查 — 必要表 / column。
    try:
        cur.execute("SELECT to_regclass('trading.fills') IS NOT NULL")
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"trading.fills existence check failed: {exc}")
    if not row or not row[0]:
        return ("WARN", "trading.fills missing — pre-migration state, skip")

    # Indicator A: lifetime drift (per engine_mode median).
    # 指標 A：每 engine_mode 中位 lifetime 漂移。
    lifecycle_cte = """
WITH entries AS (
  SELECT f.engine_mode, f.symbol, f.side,
         f.context_id AS entry_cid, f.ts AS entry_ts,
         f.price AS entry_price, f.fee AS entry_fee
  FROM trading.fills f
  WHERE f.ts > now() - interval '24 hours'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.strategy_name = 'grid_trading'
    AND coalesce(f.exit_source, '') = ''
),
closes AS (
  SELECT f.entry_context_id AS entry_cid, f.ts AS exit_ts,
         f.price AS exit_price, f.fee AS exit_fee,
         f.realized_pnl AS realized_pnl,
         f.strategy_name AS close_strategy_name,
         row_number() OVER (PARTITION BY f.entry_context_id ORDER BY f.ts) AS rn
  FROM trading.fills f
  WHERE f.ts > now() - interval '24 hours'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.entry_context_id IS NOT NULL
    AND f.entry_context_id <> ''
    AND coalesce(f.exit_source, '') <> ''
),
first_close AS (SELECT * FROM closes WHERE rn = 1),
lifecycles AS (
  SELECT e.engine_mode, e.symbol, e.side, e.entry_ts, c.exit_ts,
         EXTRACT(EPOCH FROM (c.exit_ts - e.entry_ts))/60.0 AS lifetime_min,
         (e.entry_fee + c.exit_fee) AS total_fee_usd,
         c.realized_pnl, c.close_strategy_name
  FROM entries e
  JOIN first_close c ON c.entry_cid = e.entry_cid
)
"""
    try:
        cur.execute(
            lifecycle_cte +
            """
SELECT engine_mode,
       count(*)::int AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lifetime_min)::float8 AS p50_min,
       avg(lifetime_min)::float8 AS avg_min,
       sum(total_fee_usd)::float8 AS sum_fee,
       sum(abs(coalesce(realized_pnl,0)))::float8 AS sum_abs_pnl
FROM lifecycles
GROUP BY engine_mode
ORDER BY engine_mode
"""
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"lifecycle aggregation query failed: {type(exc).__name__}: {exc}")

    stats: dict[str, dict[str, float]] = {}
    for r in rows:
        em, n, p50, avg, sum_fee, sum_abs_pnl = (
            str(r[0] or ""),
            _as_int(r[1]),
            _as_float(r[2], 0.0),
            _as_float(r[3], 0.0),
            _as_float(r[4], 0.0),
            _as_float(r[5], 0.0),
        )
        stats[em] = {
            "n": float(n),
            "p50": p50,
            "avg": avg,
            "sum_fee": sum_fee,
            "sum_abs_pnl": sum_abs_pnl,
        }

    demo = stats.get("demo")
    live_demo = stats.get("live_demo")

    # 0 row in either side: PASS-with-note (no enforcement during ramp).
    # 任一邊 0 row：PASS-with-note（爬升期不警報）。
    if not demo or demo["n"] < GRID_LIFECYCLE_MIN_SAMPLE:
        return (
            "PASS",
            f"24h grid_trading demo lifecycles n={int(demo['n']) if demo else 0} "
            f"< {GRID_LIFECYCLE_MIN_SAMPLE} — insufficient demo baseline, skip drift",
        )
    if not live_demo or live_demo["n"] < GRID_LIFECYCLE_MIN_SAMPLE:
        return (
            "PASS",
            f"24h grid_trading live_demo lifecycles n={int(live_demo['n']) if live_demo else 0} "
            f"< {GRID_LIFECYCLE_MIN_SAMPLE} — insufficient live sample, skip drift",
        )

    # Indicator A: lifetime ratio.
    # 指標 A：lifetime 比例。
    lifetime_ratio = (
        live_demo["p50"] / demo["p50"] if demo["p50"] > 0 else None
    )

    # Indicator B: fee-burn ratio absolute + relative.
    # 指標 B：fee-burn 比例（絕對 + 相對）。
    fee_burn_demo = (
        demo["sum_fee"] / demo["sum_abs_pnl"] if demo["sum_abs_pnl"] > 0 else None
    )
    fee_burn_live = (
        live_demo["sum_fee"] / live_demo["sum_abs_pnl"]
        if live_demo["sum_abs_pnl"] > 0 else None
    )
    fee_burn_ratio = (
        fee_burn_live / fee_burn_demo
        if fee_burn_demo and fee_burn_demo > 0 else None
    )

    # Indicator C: same-symbol same-side re-entry rate (1h window).
    # 指標 C：同 symbol 同 side 1h 內 re-entry 比率。
    try:
        cur.execute(
            """
WITH entries_with_lag AS (
  SELECT engine_mode, symbol, side, ts AS entry_ts,
         LAG(ts) OVER (PARTITION BY engine_mode, symbol, side ORDER BY ts) AS prev_ts
  FROM trading.fills
  WHERE ts > now() - interval '24 hours'
    AND engine_mode IN ('demo', 'live_demo')
    AND strategy_name = 'grid_trading'
    AND coalesce(exit_source, '') = ''
)
SELECT engine_mode,
       count(*)::int AS total_entries,
       count(*) FILTER (
           WHERE prev_ts IS NOT NULL
             AND entry_ts - prev_ts < interval '1 hour')::int AS re_entries,
       (count(*) FILTER (
           WHERE prev_ts IS NOT NULL
             AND entry_ts - prev_ts < interval '1 hour'))::float8
         / NULLIF(count(*), 0)::float8 AS re_entry_rate
FROM entries_with_lag
GROUP BY engine_mode
ORDER BY engine_mode
"""
        )
        re_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"re-entry rate query failed: {type(exc).__name__}: {exc}")

    re_stats: dict[str, dict[str, float]] = {}
    for r in re_rows:
        em, total, re_count, rate = (
            str(r[0] or ""),
            _as_int(r[1]),
            _as_int(r[2]),
            _as_float(r[3], 0.0),
        )
        re_stats[em] = {"total": float(total), "re": float(re_count), "rate": rate}

    re_demo = re_stats.get("demo", {"rate": 0.0, "total": 0, "re": 0})
    re_live = re_stats.get("live_demo", {"rate": 0.0, "total": 0, "re": 0})

    # Verdict aggregation — max severity wins; multiple WARN reasons accrue.
    # 結論彙總 — 取最高嚴重度；多 WARN 理由累積。
    severities: list[tuple[str, str]] = []  # (level, reason)

    # A: lifetime
    if lifetime_ratio is not None:
        if lifetime_ratio < GRID_LIFETIME_RATIO_FAIL:
            severities.append(
                ("FAIL", f"lifetime_ratio={lifetime_ratio:.2f} < {GRID_LIFETIME_RATIO_FAIL} (live too fast)")
            )
        elif lifetime_ratio < GRID_LIFETIME_RATIO_WARN:
            severities.append(
                ("WARN", f"lifetime_ratio={lifetime_ratio:.2f} < {GRID_LIFETIME_RATIO_WARN}")
            )

    # B: fee burn
    if fee_burn_live is not None:
        if fee_burn_live > GRID_FEE_BURN_ABS_FAIL:
            severities.append(
                ("FAIL", f"live fee_burn={fee_burn_live:.2f} > {GRID_FEE_BURN_ABS_FAIL} (fee dominates)")
            )
        elif fee_burn_live > GRID_FEE_BURN_ABS_WARN:
            severities.append(
                ("WARN", f"live fee_burn={fee_burn_live:.2f} > {GRID_FEE_BURN_ABS_WARN}")
            )
    if fee_burn_ratio is not None and fee_burn_ratio > GRID_FEE_BURN_RATIO_WARN:
        severities.append(
            ("WARN", f"fee_burn_ratio live/demo={fee_burn_ratio:.2f} > {GRID_FEE_BURN_RATIO_WARN}")
        )

    # C: re-entry rate
    if re_live["rate"] > GRID_REENTRY_RATE_FAIL:
        severities.append(
            ("FAIL", f"live re_entry_rate={re_live['rate']:.2f} > {GRID_REENTRY_RATE_FAIL}")
        )
    elif re_live["rate"] > GRID_REENTRY_RATE_WARN:
        severities.append(
            ("WARN", f"live re_entry_rate={re_live['rate']:.2f} > {GRID_REENTRY_RATE_WARN}")
        )
    delta = re_live["rate"] - re_demo["rate"]
    if delta > GRID_REENTRY_DELTA_WARN:
        severities.append(
            ("WARN", f"re_entry delta live-demo={delta:.2f} > {GRID_REENTRY_DELTA_WARN}")
        )

    # Final verdict
    has_fail = any(s[0] == "FAIL" for s in severities)
    has_warn = any(s[0] == "WARN" for s in severities)

    fee_burn_demo_str = f"{fee_burn_demo:.2f}" if fee_burn_demo is not None else "N/A"
    fee_burn_live_str = f"{fee_burn_live:.2f}" if fee_burn_live is not None else "N/A"
    lifetime_ratio_str = f"{lifetime_ratio:.2f}" if lifetime_ratio is not None else "N/A"

    base_msg = (
        f"24h lifecycle: demo n={int(demo['n'])} p50={demo['p50']:.1f}min "
        f"fee_burn={fee_burn_demo_str} re_rate={re_demo['rate']:.2f}; "
        f"live_demo n={int(live_demo['n'])} p50={live_demo['p50']:.1f}min "
        f"fee_burn={fee_burn_live_str} re_rate={re_live['rate']:.2f}; "
        f"lifetime_ratio={lifetime_ratio_str}"
    )

    if has_fail:
        reasons = "; ".join(r for lvl, r in severities if lvl == "FAIL")
        warns = "; ".join(r for lvl, r in severities if lvl == "WARN")
        warn_suffix = f"; warns: {warns}" if warns else ""
        return ("FAIL", f"{base_msg} — FAIL: {reasons}{warn_suffix}")
    if has_warn:
        reasons = "; ".join(r for lvl, r in severities if lvl == "WARN")
        return ("WARN", f"{base_msg} — WARN: {reasons}")
    return ("PASS", f"{base_msg} — drift within expected physical config range")


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
