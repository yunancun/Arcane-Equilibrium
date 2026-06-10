"""全域 prod-DB 隔離鐵閘的迴歸測試（P0 2026-06-10；E2 對抗 probe 固化）。

背景：v1 guard 是 per-test autouse fixture，E2 以 psycopg2.connect hook 實測抓到
grafana_data_writer 的 daemon thread 在 <outside-test-window> 走
get_conn→_init_pool→ThreadedConnectionPool 真連線（常駐 thread 跨測試生命週期，
fixture teardown 後落在無保護窗口）。v2 改為 conftest import 期的進程級封鎖。

本檔把 E2 的 probe 場景固化：daemon thread 任何時點呼 get_conn 都拿 None。
"""

from __future__ import annotations

import threading

from app import db_pool as DBP


class TestProcessLevelBlock:
    def test_init_pool_is_process_level_blocked(self):
        """進程級封鎖在位：_init_pool 是 conftest 的封鎖版，非真實建池函數。"""
        assert DBP._init_pool.__name__ == "_blocked_init_pool", (
            "conftest 進程級封鎖未生效——_init_pool 是真版，daemon thread 可在測試窗外真連 prod"
        )
        assert DBP._pool is None
        assert DBP._pool_init_attempted is True

    def test_get_conn_returns_none(self):
        """主執行緒：get_conn 走封鎖池層 → None（等價 Mac 無 PG graceful degradation）。"""
        assert DBP.get_conn() is None

    def test_get_pg_conn_yields_none(self):
        """context-manager 入口同樣拿 None（業務 fail-soft 分支）。"""
        with DBP.get_pg_conn() as conn:
            assert conn is None

    def test_daemon_thread_gets_none_conn(self):
        """E2 probe 場景鏡像：背景 thread（grafana_data_writer._loop 形）呼 get_conn
        必拿 None——進程級封鎖對任何 thread、任何時點生效，非 fixture 作用域。
        """
        results: list[object] = []

        def _loop_once():
            # 模擬 daemon writer 的單輪 _write_snapshot 連線借用。
            results.append(DBP.get_conn())

        t = threading.Thread(target=_loop_once, daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "probe thread 未在期限內結束"
        assert results == [None], f"daemon thread 拿到非 None 連線：{results!r}（封鎖被繞過）"
