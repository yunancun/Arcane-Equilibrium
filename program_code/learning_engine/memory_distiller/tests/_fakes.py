"""測試共用 fakes：FakeConn（SQL substring 路由）+ FakeLLM（腳本化回應）。

FakeConn 鏡像 psycopg2 連線的最小 surface（cursor/commit/rollback +
cursor.execute/fetchall/fetchone/description/rowcount），以 SQL 子字串路由
回應；未註冊的語句回空結果（description=[]），不拋——讓 fail-soft 路徑
可被真實觸發而非被 fake 噪音掩蓋。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Sequence


class _Route:
    def __init__(
        self,
        key: str,
        *,
        rows: Sequence[tuple] = (),
        columns: Sequence[str] = (),
        rowcount: int | None = None,
        raises: Exception | None = None,
        raise_when: Callable[[str, Any], bool] | None = None,
    ) -> None:
        self.key = key
        self.rows = list(rows)
        self.columns = list(columns)
        self.rowcount = rowcount
        self.raises = raises
        self.raise_when = raise_when


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self._conn = conn
        self._rows: list[tuple] = []
        self.description: list[tuple] | None = []
        self.rowcount = 0

    def execute(self, sql: str, params: Any = None) -> None:
        self._conn.executed.append((sql, params))
        route = self._conn._match(sql)
        if route is None:
            self._rows = []
            self.description = []
            self.rowcount = 0
            return
        if route.raises is not None and (
            route.raise_when is None or route.raise_when(sql, params)
        ):
            raise route.raises
        self._rows = list(route.rows)
        self.description = [(c,) for c in route.columns]
        self.rowcount = (
            route.rowcount if route.rowcount is not None else len(route.rows)
        )

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class FakeConn:
    """SQL substring 路由的假連線；先註冊者優先匹配。"""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self._routes: list[_Route] = []

    def add_route(self, key: str, **kwargs: Any) -> None:
        self._routes.append(_Route(key, **kwargs))

    def _match(self, sql: str) -> _Route | None:
        for route in self._routes:
            if route.key in sql:
                return route
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    # 觀測 helpers
    def sqls(self) -> list[str]:
        return [s for s, _ in self.executed]

    def count_sql(self, key: str) -> int:
        return sum(1 for s in self.sqls() if key in s)


class FakeLLM:
    """腳本化 LLM：依序回放 responses（str=成功文本 / Exception=raise /
    (text, success) tuple=自訂 success 旗標）。"""

    def __init__(self, responses: Sequence[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout_s: float | None = None,
        timeout: int | None = None,
    ) -> Any:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout_s": timeout_s,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("FakeLLM responses 用罄（測試腳本缺回應）")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            text, success = item
            return SimpleNamespace(text=text, success=success)
        return SimpleNamespace(text=str(item), success=True)
