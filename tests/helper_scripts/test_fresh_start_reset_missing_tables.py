from __future__ import annotations

from helper_scripts.db.fresh_start_reset import truncate_tables


class _Cursor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self._last_count = 0

    def execute(self, sql: str) -> None:
        self.queries.append(sql)
        if "observability.scorer_predictions" in sql and sql.lower().startswith("select"):
            raise RuntimeError("relation does not exist")
        self._last_count = 0

    def fetchone(self):
        return (self._last_count,)


def test_fresh_start_truncate_skips_missing_dead_tables() -> None:
    cur = _Cursor()

    counts = truncate_tables(cur, dry_run=True)

    assert counts["observability.scorer_predictions"] == -1
    assert not any(
        query.startswith("TRUNCATE observability.scorer_predictions")
        for query in cur.queries
    )
