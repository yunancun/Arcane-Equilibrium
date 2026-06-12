"""memory_distiller 測試共用 conftest。

防 prod 污染鐵閘（autouse，承 0ce45a09 P0 教訓）：本目錄所有測試一律
mock 連線層——Mac 無 PG 時 fail-soft 會吞錯假綠，但在連得上真 PG 的環境
（Linux E4 / deploy re-test）漏 mock 的測試會把 fixture 假資料寫進 prod。
此處把 psycopg2.connect 與 recall 的 lazy db_pool 入口、urllib 真網路全部
攔死；需要行為的測試以 test 內 monkeypatch 顯式覆蓋（後設定者優先）。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """攔真 DB 連線 + 真網路：邏輯全真實走，只隔離 I/O 邊界。"""
    # psycopg2 可能未安裝（Mac venv 視情況）；裝了就攔。
    try:
        import psycopg2  # noqa: PLC0415

        def _blocked_connect(*_a, **_k):
            raise AssertionError("測試禁止真 psycopg2.connect（_no_real_db 鐵閘）")

        monkeypatch.setattr(psycopg2, "connect", _blocked_connect)
    except ImportError:
        pass

    # recall 的 B3 lazy 連線入口：默認炸掉（fail-open 路徑可測）；
    # happy-path 測試自行 monkeypatch 覆蓋。
    from program_code.learning_engine.memory_distiller import recall as recall_mod

    def _blocked_open_conn():
        raise AssertionError("測試禁止 lazy db_pool 連線（_no_real_db 鐵閘）")

    monkeypatch.setattr(recall_mod, "_open_db_conn", _blocked_open_conn)

    # urllib 真網路攔死（embedding 測試自行覆蓋 urlopen）。
    import urllib.request  # noqa: PLC0415

    def _blocked_urlopen(*_a, **_k):
        raise AssertionError("測試禁止真網路 urlopen（_no_real_db 鐵閘）")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)
