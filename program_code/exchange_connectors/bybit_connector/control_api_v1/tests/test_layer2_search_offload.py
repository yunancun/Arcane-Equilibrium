"""
MODULE_NOTE
模塊用途：冷審計 R2 latent（E5）——layer2_tools 3/4 SearchProvider 在 async def
內同步阻塞的修復回歸測試（asyncio.to_thread 卸載）。
主要類/函數：TestSearchProviderOffload（三個 provider 各一條 offload 斷言）。
依賴：app.layer2_tools（LocalLLMWebSearchProvider / LocalLLMSearchProvider /
WebPilotSearchProvider）。
硬邊界：斷言判準=阻塞呼叫的執行線程 ≠ event loop 線程（to_thread 卸載的
直接證據）；同時鎖定回應解析行為不變（results / provider_used / error）。
舊碼（阻塞呼叫直接跑在 loop 線程）下三條測試必紅。
"""

import asyncio
import sys
import threading
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_tools import (
    LocalLLMSearchProvider,
    LocalLLMWebSearchProvider,
    WebPilotSearchProvider,
)


def _run(coro):
    # 對齊 test_layer2.py 既有慣例：每次自管 new loop + close，不污染 global。
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSearchProviderOffload:
    """三個原同步阻塞 provider 的 to_thread 卸載證明。

    為什麼用線程身份斷言：event loop 跑在本測試線程上（run_until_complete），
    若阻塞呼叫仍在 loop 線程執行（舊碼行為），recorded thread == 測試主線程
    → 紅；to_thread 卸載後必在 worker thread → 綠。
    """

    def test_local_llm_web_search_runs_subprocess_off_loop_thread(self, monkeypatch):
        seen: dict = {}

        def fake_run(cmd, **kwargs):
            seen["thread"] = threading.current_thread()
            return types.SimpleNamespace(
                returncode=0,
                stdout='{"results": [{"title": "t1", "snippet": "s1", "url": "u1"}]}',
                stderr="",
            )

        monkeypatch.setattr("app.layer2_tools.subprocess.run", fake_run)
        provider = LocalLLMWebSearchProvider()
        resp = _run(provider.search("test query"))

        assert "thread" in seen, "subprocess.run 未被呼叫"
        assert seen["thread"] is not threading.current_thread(), (
            "subprocess.run（最長阻塞 30s）仍在 event loop 線程上執行"
        )
        # 行為保持：解析路徑不變。
        assert resp.error is None
        assert len(resp.results) == 1
        assert resp.results[0].title == "t1"
        assert resp.results[0].url == "u1"

    def test_local_llm_search_runs_generate_off_loop_thread(self, monkeypatch):
        seen: dict = {}

        class FakeClient:
            def generate(self, prompt, **kwargs):
                seen["thread"] = threading.current_thread()
                return types.SimpleNamespace(success=True, text="mocked answer", error=None)

        monkeypatch.setattr("app.layer2_tools.get_local_llm_client", lambda: FakeClient())
        provider = LocalLLMSearchProvider()
        resp = _run(provider.search("test query"))

        assert "thread" in seen, "client.generate 未被呼叫"
        assert seen["thread"] is not threading.current_thread(), (
            "client.generate（最長阻塞 60s）仍在 event loop 線程上執行"
        )
        assert resp.error is None
        assert len(resp.results) == 1
        assert resp.results[0].snippet == "mocked answer"

    def test_webpilot_search_runs_ddgs_off_loop_thread(self, monkeypatch):
        seen: dict = {}

        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def text(self, query, max_results=5):
                seen["thread"] = threading.current_thread()
                return [{"title": "t1", "body": "b1", "href": "h1"}]

        fake_mod = types.ModuleType("duckduckgo_search")
        fake_mod.DDGS = FakeDDGS
        monkeypatch.setitem(sys.modules, "duckduckgo_search", fake_mod)
        provider = WebPilotSearchProvider()
        resp = _run(provider.search("test query"))

        assert "thread" in seen, "DDGS.text 未被呼叫"
        assert seen["thread"] is not threading.current_thread(), (
            "DDGS 網路查詢仍在 event loop 線程上執行"
        )
        assert resp.error is None
        assert len(resp.results) == 1
        assert resp.results[0].title == "t1"
        assert resp.results[0].url == "h1"
