"""Agent Decision Spine lineage healthcheck.
Agent Decision Spine lineage 健康檢查。

MODULE_NOTE (中文):
  `[55]` 監測 MAG-082 需要的 runtime typed lineage 是否真的可見。
  這和 `[52]` event-store row proof 不同：本檢查針對
  `agent.decision_objects` / `agent.decision_edges` /
  `agent.execution_idempotency_keys`，並明確區分 writer disabled、
  enabled-but-empty、recent lineage incomplete、以及 MAG-082 readiness。
  預設 WARN，`OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED=1` 時升 FAIL。
"""

from __future__ import annotations

import os


AGENT_SPINE_LINEAGE_WINDOW_MINUTES = 24 * 60
_TABLES = (
    "agent.decision_objects",
    "agent.decision_edges",
    "agent.execution_idempotency_keys",
)
_CORE_OBJECT_TYPES = (
    "strategy_signal",
    "strategist_decision",
    "guardian_verdict",
    "execution_plan",
)
_DISPLAY_OBJECT_TYPES = _CORE_OBJECT_TYPES + ("execution_report",)
_RUNTIME_ENABLED_MODES = {"shadow", "canary", "primary"}


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _status(required: bool) -> str:
    return "FAIL" if required else "WARN"


def _window_minutes() -> int:
    raw = os.getenv(
        "OPENCLAW_AGENT_SPINE_HEALTH_WINDOW_MINUTES",
        str(AGENT_SPINE_LINEAGE_WINDOW_MINUTES),
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return AGENT_SPINE_LINEAGE_WINDOW_MINUTES


def _engine_modes() -> list[str]:
    raw = os.getenv("OPENCLAW_AGENT_SPINE_HEALTH_ENGINE_MODES", "demo,live_demo")
    modes = [part.strip() for part in raw.split(",") if part.strip()]
    return modes or ["demo", "live_demo"]


def _runtime_mode() -> str:
    return os.getenv("OPENCLAW_AGENT_SPINE_RUNTIME_MODE", "disabled").strip().lower()


def _agent_spine_enabled() -> bool:
    return _enabled("OPENCLAW_AGENT_SPINE_CLIENT_ENABLED") or (
        _runtime_mode() in _RUNTIME_ENABLED_MODES
    )


def _mode_detail(modes: list[str]) -> str:
    return ",".join(modes)


def _count(row, index: int = 0) -> int:
    if not row:
        return 0
    return int(row[index] or 0)


def _type_detail(type_counts: dict[str, int]) -> str:
    return ",".join(
        f"{object_type}={type_counts.get(object_type, 0)}"
        for object_type in _DISPLAY_OBJECT_TYPES
    )


def _aggregate_counts(
    cur,
    table_name: str,
    ts_column: str,
    modes: list[str],
    window_minutes: int,
) -> tuple[int, int]:
    cur.execute(
        f"""
        SELECT
            count(*) FILTER (
                WHERE {ts_column} > now() - (%s::text || ' minutes')::interval
            )::int AS recent_rows,
            count(*)::int AS all_time_rows
        FROM {table_name}
        WHERE engine_mode = ANY(%s)
        """,
        (window_minutes, modes),
    )
    row = cur.fetchone() or (0, 0)
    return int(row[0] or 0), int(row[1] or 0)


def _complete_chain_counts(
    cur,
    modes: list[str],
    window_minutes: int,
) -> tuple[int, int, int, int, int]:
    cur.execute(
        """
        WITH chains AS (
            SELECT DISTINCT
                sig.object_id AS signal_object_id,
                dec.object_id AS decision_object_id,
                verdict.object_id AS verdict_object_id,
                plan.object_id AS plan_object_id,
                plan.order_plan_id,
                plan.decision_id,
                plan.engine_mode,
                plan.lease_id
            FROM agent.decision_objects sig
            JOIN agent.decision_edges sig_edge
              ON sig_edge.from_object_id = sig.object_id
             AND sig_edge.edge_type = 'signal_for'
            JOIN agent.decision_objects dec
              ON dec.object_id = sig_edge.to_object_id
             AND dec.object_type = 'strategist_decision'
            JOIN agent.decision_edges verdict_edge
              ON verdict_edge.from_object_id = dec.object_id
             AND verdict_edge.edge_type IN ('reviewed_by', 'modified_by')
            JOIN agent.decision_objects verdict
              ON verdict.object_id = verdict_edge.to_object_id
             AND verdict.object_type = 'guardian_verdict'
            JOIN agent.decision_edges plan_edge
              ON plan_edge.from_object_id = verdict.object_id
             AND plan_edge.edge_type = 'planned_by'
            JOIN agent.decision_objects plan
              ON plan.object_id = plan_edge.to_object_id
             AND plan.object_type = 'execution_plan'
            WHERE sig.object_type = 'strategy_signal'
              AND sig.engine_mode = ANY(%s)
              AND dec.engine_mode = ANY(%s)
              AND verdict.engine_mode = ANY(%s)
              AND plan.engine_mode = ANY(%s)
              AND sig.created_at > now() - (%s::text || ' minutes')::interval
              AND dec.created_at > now() - (%s::text || ' minutes')::interval
              AND verdict.created_at > now() - (%s::text || ' minutes')::interval
              AND plan.created_at > now() - (%s::text || ' minutes')::interval
        )
        SELECT
            count(DISTINCT c.plan_object_id)::int AS complete_chains,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE idem.idempotency_key IS NOT NULL
            )::int AS chains_with_idempotency,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE c.lease_id IS NOT NULL AND c.lease_id <> ''
            )::int AS chains_with_lease,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE report.object_id IS NOT NULL
            )::int AS chains_with_report,
            count(DISTINCT report.object_id) FILTER (
                WHERE report.object_id IS NOT NULL
                  AND (
                    NOT (report.payload ? 'quality_metrics')
                    OR NOT (report.payload ? 'requested_qty')
                    OR NOT (report.payload ? 'filled_qty')
                    OR NOT (report.payload ? 'liquidity_role')
                  )
            )::int AS bad_report_quality
        FROM chains c
        LEFT JOIN agent.execution_idempotency_keys idem
          ON idem.order_plan_id = c.order_plan_id
         AND idem.decision_id = c.decision_id
         AND idem.engine_mode = c.engine_mode
        LEFT JOIN agent.decision_edges report_edge
          ON report_edge.from_object_id = c.order_plan_id
         AND report_edge.edge_type = 'executed_by'
        LEFT JOIN agent.decision_objects report
          ON report.object_id = report_edge.to_object_id
         AND report.object_type = 'execution_report'
         AND report.engine_mode = c.engine_mode
         AND report.created_at > now() - (%s::text || ' minutes')::interval
        """,
        (
            modes,
            modes,
            modes,
            modes,
            window_minutes,
            window_minutes,
            window_minutes,
            window_minutes,
            window_minutes,
        ),
    )
    row = cur.fetchone() or (0, 0, 0, 0, 0)
    return (
        _count(row, 0),
        _count(row, 1),
        _count(row, 2),
        _count(row, 3),
        _count(row, 4),
    )


def check_55_agent_decision_spine_lineage(cur) -> tuple[str, str]:
    """[55] Verify Agent Decision Spine lineage rows for MAG-082 readiness."""
    required = _enabled("OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED")
    window_minutes = _window_minutes()
    modes = _engine_modes()
    mode_detail = _mode_detail(modes)

    runtime_mode = _runtime_mode()
    if not _agent_spine_enabled():
        return (
            _status(required),
            "agent decision spine disabled by env; "
            f"MAG-082 readiness=DISABLED window={window_minutes}m "
            f"modes={mode_detail} runtime_mode={runtime_mode}",
        )

    try:
        cur.connection.rollback()
    except Exception:
        pass

    missing: list[str] = []
    try:
        for table_name in _TABLES:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table_name,))
            row = cur.fetchone()
            if not row or not row[0]:
                missing.append(table_name)
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return (_status(required), f"agent decision spine table check failed: {exc}")

    if missing:
        return (
            _status(required),
            "agent decision spine schema incomplete; "
            f"MAG-082 readiness=BLOCKED_SCHEMA_MISSING missing={','.join(missing)}",
        )

    try:
        recent_objects, all_objects = _aggregate_counts(
            cur, "agent.decision_objects", "created_at", modes, window_minutes
        )
        recent_edges, all_edges = _aggregate_counts(
            cur, "agent.decision_edges", "created_at", modes, window_minutes
        )
        recent_idempotency, all_idempotency = _aggregate_counts(
            cur, "agent.execution_idempotency_keys", "first_seen_at", modes, window_minutes
        )
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return (_status(required), f"agent decision spine row check failed: {exc}")

    base_detail = (
        f"window={window_minutes}m modes={mode_detail} "
        f"objects={recent_objects}/{all_objects} edges={recent_edges}/{all_edges} "
        f"idempotency={recent_idempotency}/{all_idempotency}"
    )
    if all_objects <= 0 and all_edges <= 0 and all_idempotency <= 0:
        return (
            _status(required),
            "agent decision spine enabled but empty; "
            f"MAG-082 readiness=BLOCKED_ENABLED_EMPTY {base_detail}",
        )
    if recent_objects <= 0 or recent_edges <= 0 or recent_idempotency <= 0:
        return (
            _status(required),
            "agent decision spine enabled but no recent complete row proof; "
            f"MAG-082 readiness=BLOCKED_NO_RECENT_LINEAGE {base_detail}",
        )

    try:
        cur.execute(
            """
            SELECT object_type, count(*)::int
            FROM agent.decision_objects
            WHERE engine_mode = ANY(%s)
              AND created_at > now() - (%s::text || ' minutes')::interval
            GROUP BY object_type
            """,
            (modes, window_minutes),
        )
        type_counts = {
            str(object_type): int(count or 0)
            for object_type, count in cur.fetchall()
        }
        (
            complete_chains,
            chains_with_idempotency,
            chains_with_lease,
            chains_with_report,
            bad_report_quality,
        ) = _complete_chain_counts(cur, modes, window_minutes)
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return (_status(required), f"agent decision spine lineage query failed: {exc}")

    missing_types = [
        object_type
        for object_type in _CORE_OBJECT_TYPES
        if type_counts.get(object_type, 0) <= 0
    ]
    detail = (
        f"{base_detail} types={_type_detail(type_counts)} "
        f"chains={complete_chains} chains_with_idempotency={chains_with_idempotency} "
        f"chains_with_lease={chains_with_lease} chains_with_report={chains_with_report} "
        f"bad_report_quality={bad_report_quality}"
    )
    if missing_types or complete_chains <= 0:
        missing_text = ",".join(missing_types) if missing_types else "complete_chain"
        return (
            _status(required),
            "agent decision spine lineage incomplete; "
            f"MAG-082 readiness=BLOCKED_INCOMPLETE missing={missing_text} {detail}",
        )
    if chains_with_idempotency < complete_chains:
        return (
            _status(required),
            "agent decision spine idempotency incomplete; "
            f"MAG-082 readiness=BLOCKED_IDEMPOTENCY {detail}",
        )
    if chains_with_report <= 0:
        return (
            _status(required),
            "agent decision spine execution reports absent; "
            f"MAG-082 readiness=BLOCKED_REPORTS_PENDING {detail}",
        )
    if bad_report_quality > 0:
        return (
            _status(required),
            "agent decision spine execution report quality incomplete; "
            f"MAG-082 readiness=BLOCKED_REPORT_QUALITY {detail}",
        )

    return (
        "PASS",
        "agent decision spine lineage proof healthy; "
        f"MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS {detail}",
    )
