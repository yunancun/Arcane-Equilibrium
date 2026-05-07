"""OpenClaw proposal / approval relay healthcheck.
OpenClaw proposal / approval relay 健康檢查。

MODULE_NOTE (中文):
  `[54]` 監測 OC-GW-5/6/7 ledger 是否可審計：proposal / approval /
  channel-event 表存在、pending approval 未過期、approval rows 有 parent、
  proposal create 有 channel event。缺表先 WARN，避免 source 先於 migration
  deploy 時把 runtime 直接打成 FAIL。
"""

from __future__ import annotations


_TABLES = (
    "openclaw.proposals",
    "openclaw.approval_decisions",
    "openclaw.channel_events",
)


def _table_missing(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NULL", (table_name,))
    row = cur.fetchone()
    return bool(row and row[0])


def check_54_openclaw_proposal_relay(cur) -> tuple[str, str]:
    try:
        missing = [table_name for table_name in _TABLES if _table_missing(cur, table_name)]
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return ("WARN", f"openclaw proposal relay table check failed: {exc}")
    if missing:
        return (
            "WARN",
            "openclaw proposal relay tables missing: " + ",".join(missing),
        )

    try:
        cur.execute(
            """
            SELECT count(*)::int
              FROM openclaw.proposals
             WHERE status = 'pending_approval'
               AND expires_at_ms IS NOT NULL
               AND expires_at_ms <= (EXTRACT(EPOCH FROM now()) * 1000)::bigint
            """
        )
        expired_pending = int((cur.fetchone() or (0,))[0])

        cur.execute(
            """
            SELECT count(*)::int
              FROM openclaw.approval_decisions d
              LEFT JOIN openclaw.proposals p
                ON p.proposal_id = d.proposal_id
             WHERE p.proposal_id IS NULL
            """
        )
        orphan_decisions = int((cur.fetchone() or (0,))[0])

        cur.execute(
            """
            SELECT count(*)::int
              FROM openclaw.proposals p
             WHERE NOT EXISTS (
                   SELECT 1
                     FROM openclaw.channel_events e
                    WHERE e.linked_proposal_id = p.proposal_id
                      AND e.event_type = 'proposal_created'
               )
            """
        )
        proposals_without_channel_event = int((cur.fetchone() or (0,))[0])

        cur.execute(
            """
            SELECT
                count(*)::int AS proposals,
                count(*) FILTER (WHERE status = 'pending_approval')::int AS pending,
                count(*) FILTER (WHERE status IN ('approved', 'rejected', 'expired'))::int AS terminal
              FROM openclaw.proposals
            """
        )
        totals = cur.fetchone() or (0, 0, 0)
        proposal_total = int(totals[0] or 0)
        pending_total = int(totals[1] or 0)
        terminal_total = int(totals[2] or 0)
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return ("WARN", f"openclaw proposal relay query failed: {exc}")

    detail = (
        f"proposals={proposal_total} pending={pending_total} terminal={terminal_total} "
        f"expired_pending={expired_pending} orphan_decisions={orphan_decisions} "
        f"missing_channel_event={proposals_without_channel_event}"
    )
    if expired_pending > 0 or orphan_decisions > 0:
        return ("FAIL", "openclaw proposal relay audit violation: " + detail)
    if proposals_without_channel_event > 0:
        return ("WARN", "openclaw proposal channel audit incomplete: " + detail)
    return ("PASS", "openclaw proposal relay ledger healthy: " + detail)
