from __future__ import annotations

from helper_scripts.db.passive_wait_healthcheck.checks_openclaw_gateway import (
    check_54_openclaw_proposal_relay,
)


class _Cursor:
    def __init__(
        self,
        *,
        missing_tables: set[str] | None = None,
        expired_pending: int = 0,
        orphan_decisions: int = 0,
        missing_channel_event: int = 0,
        totals: tuple[int, int, int] = (0, 0, 0),
    ) -> None:
        self.missing_tables = missing_tables or set()
        self.expired_pending = expired_pending
        self.orphan_decisions = orphan_decisions
        self.missing_channel_event = missing_channel_event
        self.totals = totals
        self._row: tuple[object, ...] = (0,)

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        lowered = sql.lower()
        if "to_regclass" in lowered:
            table_name = str((params or ("",))[0])
            self._row = (table_name in self.missing_tables,)
            return
        if "expired_pending" not in lowered and "expires_at_ms" in lowered:
            self._row = (self.expired_pending,)
            return
        if "left join openclaw.proposals" in lowered:
            self._row = (self.orphan_decisions,)
            return
        if "not exists" in lowered:
            self._row = (self.missing_channel_event,)
            return
        if "as proposals" in lowered:
            self._row = self.totals
            return
        self._row = (0,)

    def fetchone(self) -> tuple[object, ...]:
        return self._row


def test_openclaw_proposal_relay_warns_when_tables_missing() -> None:
    status, msg = check_54_openclaw_proposal_relay(
        _Cursor(missing_tables={"openclaw.proposals"})
    )
    assert status == "WARN"
    assert "openclaw.proposals" in msg


def test_openclaw_proposal_relay_passes_clean_ledger() -> None:
    status, msg = check_54_openclaw_proposal_relay(
        _Cursor(totals=(3, 1, 2))
    )
    assert status == "PASS"
    assert "proposals=3" in msg


def test_openclaw_proposal_relay_fails_expired_pending_or_orphans() -> None:
    status, msg = check_54_openclaw_proposal_relay(
        _Cursor(expired_pending=1, orphan_decisions=1, totals=(2, 1, 1))
    )
    assert status == "FAIL"
    assert "expired_pending=1" in msg
    assert "orphan_decisions=1" in msg


def test_openclaw_proposal_relay_warns_missing_channel_audit() -> None:
    status, msg = check_54_openclaw_proposal_relay(
        _Cursor(missing_channel_event=1, totals=(2, 1, 1))
    )
    assert status == "WARN"
    assert "missing_channel_event=1" in msg
