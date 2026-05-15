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

# value_quality cutoff 預設「不過濾」哨兵：1970 epoch 確保所有 row 都在 cutoff 之後;
# 真正用法是部署完 Caveat 1+2 fix 後 operator 設定 OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS=
# <deploy_ts ISO8601 with tz> 排除歷史 stub row。
_VALUE_QUALITY_CUTOFF_DEFAULT = "1970-01-01T00:00:00+00"

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


def _value_quality_cutoff_ts() -> str:
    # 讀取 deploy_ts cutoff; 未設則使用 1970 epoch 哨兵（等同不過濾）。
    raw = os.getenv(
        "OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS",
        _VALUE_QUALITY_CUTOFF_DEFAULT,
    ).strip()
    return raw or _VALUE_QUALITY_CUTOFF_DEFAULT


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
    value_quality_cutoff_ts: str,
) -> tuple[int, int, int, int, int, int, int, int, int, int, int]:
    # 回傳 11-tuple:
    #   (complete_chains, chains_with_idempotency, chains_with_lease,
    #    chains_with_report, bad_report_quality,
    #    bad_report_value_quality, chains_with_real_fill_report,
    #    chains_with_plan_order_fill, chains_with_full_plan_fill,
    #    full_plan_fills_missing_report, partial_plan_fill_chains)
    #
    # 新增兩個 value-realism 指標（PA `2026-05-10--w_c_caveat_fix_plan.md` §3）:
    #   - bad_report_value_quality: cutoff 後但 filled_qty<=0 或 liquidity_role 非 maker/taker 的 real-fill row 數
    #   - chains_with_real_fill_report: cutoff 後且 filled_qty>0 且 liquidity_role IN (maker,taker) 的 row 數
    # real-fill row 由新 edge filter 抓: edge_type='executed_by' AND details->>'fill_completion'='true'
    # （Caveat 2 Option α / Migration A: 既有 edge_type + JSON 標記，不需新 enum / migration）
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
                plan.lease_id,
                (plan.payload->>'qty')::numeric AS plan_qty,
                COALESCE(
                    plan.payload->>'exchange_order_id',
                    plan.payload#>>'{metadata,dispatch_order_link_id}'
                ) AS exchange_order_id
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
        ),
        plan_fill_status AS (
            SELECT
                c.plan_object_id,
                COALESCE(sum(f.qty::numeric), 0)::numeric AS real_filled_qty,
                count(f.fill_id)::int AS real_fill_rows
            FROM chains c
            LEFT JOIN trading.fills f
              ON f.engine_mode = c.engine_mode
             AND f.order_id = c.exchange_order_id
             AND f.ts > now() - (%s::text || ' minutes')::interval
             AND f.ts > %s::timestamptz
             AND f.qty > 0
             AND f.liquidity_role IN ('maker','taker')
            GROUP BY c.plan_object_id
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
            )::int AS bad_report_quality,
            count(DISTINCT filled_report.object_id) FILTER (
                WHERE filled_report.object_id IS NOT NULL
                  AND filled_report.created_at > %s::timestamptz
                  AND (
                    (filled_report.payload->>'filled_qty')::numeric <= 0
                    OR filled_report.payload->>'liquidity_role' NOT IN ('maker','taker')
                  )
            )::int AS bad_report_value_quality,
            count(DISTINCT filled_report.object_id) FILTER (
                WHERE filled_report.object_id IS NOT NULL
                  AND filled_report.created_at > %s::timestamptz
                  AND (filled_report.payload->>'filled_qty')::numeric > 0
                  AND filled_report.payload->>'liquidity_role' IN ('maker','taker')
            )::int AS chains_with_real_fill_report,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE pfs.real_fill_rows > 0
            )::int AS chains_with_plan_order_fill,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE c.plan_qty > 0
                  AND pfs.real_filled_qty >= c.plan_qty * 0.999
            )::int AS chains_with_full_plan_fill,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE c.plan_qty > 0
                  AND pfs.real_filled_qty >= c.plan_qty * 0.999
                  AND filled_report.object_id IS NULL
            )::int AS full_plan_fills_missing_report,
            count(DISTINCT c.plan_object_id) FILTER (
                WHERE pfs.real_fill_rows > 0
                  AND (
                    c.plan_qty IS NULL
                    OR c.plan_qty <= 0
                    OR pfs.real_filled_qty < c.plan_qty * 0.999
                  )
            )::int AS partial_plan_fill_chains
        FROM chains c
        LEFT JOIN plan_fill_status pfs
          ON pfs.plan_object_id = c.plan_object_id
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
        LEFT JOIN agent.decision_edges filled_report_edge
          ON filled_report_edge.from_object_id = c.order_plan_id
         AND filled_report_edge.edge_type = 'executed_by'
         AND (filled_report_edge.details->>'fill_completion')::boolean IS TRUE
        LEFT JOIN agent.decision_objects filled_report
          ON filled_report.object_id = filled_report_edge.to_object_id
         AND filled_report.object_type = 'execution_report'
         AND filled_report.engine_mode = c.engine_mode
         AND filled_report.created_at > now() - (%s::text || ' minutes')::interval
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
            value_quality_cutoff_ts,
            value_quality_cutoff_ts,
            value_quality_cutoff_ts,
            window_minutes,
            window_minutes,
        ),
    )
    row = cur.fetchone() or (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    return (
        _count(row, 0),
        _count(row, 1),
        _count(row, 2),
        _count(row, 3),
        _count(row, 4),
        _count(row, 5),
        _count(row, 6),
        _count(row, 7),
        _count(row, 8),
        _count(row, 9),
        _count(row, 10),
    )


def _state_changes_count_24h(
    cur,
    modes: list[str],
    window_minutes: int,
) -> int:
    # 補 Caveat 1 揭露 SoT: agent.decision_state_changes 是否被 producer 寫入。
    # 0 row → Spine 5 個 object 的 SM lifecycle 沒接 caller。
    cur.execute(
        """
        SELECT count(*)::int
        FROM agent.decision_state_changes
        WHERE engine_mode = ANY(%s)
          AND ts > now() - (%s::text || ' minutes')::interval
        """,
        (modes, window_minutes),
    )
    row = cur.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


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

    value_quality_cutoff_ts = _value_quality_cutoff_ts()
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
            bad_report_value_quality,
            chains_with_real_fill_report,
            chains_with_plan_order_fill,
            chains_with_full_plan_fill,
            full_plan_fills_missing_report,
            partial_plan_fill_chains,
        ) = _complete_chain_counts(cur, modes, window_minutes, value_quality_cutoff_ts)
        state_changes_24h = _state_changes_count_24h(cur, modes, window_minutes)
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return (_status(required), f"agent decision spine lineage query failed: {exc}")

    missing_types = [
        object_type
        for object_type in _CORE_OBJECT_TYPES
        if type_counts.get(object_type, 0) <= 0
    ]
    # detail message 含全部新舊指標 + cutoff 時間戳，供 reviewer 與 W-D MAG-083
    # 解讀 caveat fix delta（PA §3.4 message format）。
    detail = (
        f"{base_detail} types={_type_detail(type_counts)} "
        f"chains={complete_chains} chains_with_idempotency={chains_with_idempotency} "
        f"chains_with_lease={chains_with_lease} chains_with_report={chains_with_report} "
        f"bad_report_quality={bad_report_quality} "
        f"bad_report_value_quality={bad_report_value_quality} "
        f"chains_with_real_fill_report={chains_with_real_fill_report} "
        f"chains_with_plan_order_fill={chains_with_plan_order_fill} "
        f"chains_with_full_plan_fill={chains_with_full_plan_fill} "
        f"full_plan_fills_missing_report={full_plan_fills_missing_report} "
        f"partial_plan_fill_chains={partial_plan_fill_chains} "
        f"state_changes_24h={state_changes_24h} "
        f"value_quality_cutoff={value_quality_cutoff_ts}"
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
    # Caveat 1+2 fix 後新加語意 gate：
    #   - state_changes_24h<=0: Spine SM producer 未接 caller (Caveat 1)
    #   - bad_report_value_quality>0: cutoff 後 ExecutionReport 仍是 stub (Caveat 2)
    #   - full_plan_fills_missing_report>0: Rust fully_filled 門檻已達成但缺少
    #     fill-completion ExecutionReport。
    #
    # 舊版用 chains_with_real_fill_report / complete_chains >= 50% 的啟發式。
    # 這會把合法無成交 chain 與未達 fully_filled 的 partial chain 放進分母，
    # 在低成交率 / PostOnly partial 期間誤報 WARN。這裡改成對齊 Rust 目前
    # 契約：`loop_exchange.rs` 只在 `cum_filled_qty >= qty * 0.999` 時 emit
    # fill-completion lineage。
    if state_changes_24h <= 0:
        return (
            _status(required),
            "agent decision spine state-changes empty; "
            f"MAG-082 readiness=BLOCKED_STATE_CHANGES_EMPTY {detail}",
        )
    if bad_report_value_quality > 0:
        return (
            _status(required),
            "agent decision spine execution report value-realism incomplete; "
            f"MAG-082 readiness=BLOCKED_REPORT_VALUE_QUALITY {detail}",
        )
    if full_plan_fills_missing_report > 0:
        return (
            _status(required),
            "agent decision spine full-fill report missing; "
            f"MAG-082 readiness=BLOCKED_REAL_FILL_REPORT_MISSING {detail}",
        )

    return (
        "PASS",
        "agent decision spine lineage proof healthy; "
        f"MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS {detail}",
    )
