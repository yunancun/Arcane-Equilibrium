"""Agent event-store healthcheck.
Agent event-store 健康檢查。

MODULE_NOTE (中文):
  `[52]` 監測 MAG-010..012 durable event-store wiring 是否真的在 Linux PG
  寫入 `agent.messages` / `agent.state_changes` / `agent.ai_invocations`。
  預設隨 feature flag 關閉而 PASS-skip；啟用後 table missing 或 row=0 先
  WARN，只有 `OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED=1` 才升 FAIL。
"""

from __future__ import annotations

import os


AGENT_EVENT_STORE_RECENT_WINDOW_MINUTES = 30
_TABLES = (
    "agent.messages",
    "agent.state_changes",
    "agent.ai_invocations",
)


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _status(required: bool) -> str:
    return "FAIL" if required else "WARN"


def check_52_agent_event_store_rows(cur) -> tuple[str, str]:
    """[52] Verify recent durable rows for the 5-Agent advisory event store."""
    if not _enabled("OPENCLAW_AGENT_EVENT_STORE_ENABLED"):
        return ("PASS", "agent event-store disabled by env; row proof skipped")

    required = _enabled("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED")
    window_minutes = int(
        os.getenv(
            "OPENCLAW_AGENT_EVENT_STORE_HEALTH_WINDOW_MINUTES",
            str(AGENT_EVENT_STORE_RECENT_WINDOW_MINUTES),
        )
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
        return (_status(required), f"agent event-store table check failed: {exc}")

    if missing:
        return (
            _status(required),
            "agent event-store table missing: " + ", ".join(missing),
        )

    try:
        counts: dict[str, int] = {}
        for table_name in _TABLES:
            cur.execute(
                f"""
                SELECT count(*)::int
                FROM {table_name}
                WHERE ts > now() - (%s::text || ' minutes')::interval
                """,
                (window_minutes,),
            )
            row = cur.fetchone()
            counts[table_name] = int(row[0] if row else 0)
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return (_status(required), f"agent event-store row check failed: {exc}")

    zero_tables = [table_name for table_name, count in counts.items() if count <= 0]
    detail = (
        f"window={window_minutes}m messages={counts['agent.messages']} "
        f"state_changes={counts['agent.state_changes']} "
        f"ai_invocations={counts['agent.ai_invocations']}"
    )
    if zero_tables:
        return (
            _status(required),
            f"agent event-store recent row proof incomplete ({detail}); "
            f"zero={','.join(zero_tables)}",
        )

    return ("PASS", f"agent event-store recent row proof healthy ({detail})")
