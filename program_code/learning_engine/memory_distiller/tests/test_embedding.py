"""embedding 測試：body 無 dimensions（G18 鐵律）+ 降級 + 批次切分。"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from program_code.learning_engine.memory_distiller.embedding import (
    ALLOW_REMOTE_ENV,
    EMBED_REQUEST_BATCH_SIZE,
    OllamaEmbeddingClient,
    detect_meta_drift,
)


@pytest.fixture(autouse=True)
def _default_loopback_env(monkeypatch):
    """hermetic：宿主機若設了遠端 OLLAMA_BASE_URL，remote gate 會讓既有
    建構測試誤紅——默認清掉兩個 env；gate 測試在測試體內自行 setenv 覆蓋。"""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _embed_payload(n_vectors: int, dims: int = 4) -> dict:
    return {"data": [{"embedding": [0.1] * dims} for _ in range(n_vectors)]}


@pytest.fixture()
def captured_requests(monkeypatch):
    """攔 urlopen，記錄 request 並按腳本回應。"""
    captured: list[urllib.request.Request] = []
    responses: list = []

    def _fake_urlopen(req, timeout=None):
        captured.append(req)
        if not responses:
            raise AssertionError("無腳本回應")
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    return captured, responses


def test_constructor_makes_no_network_call():
    # conftest 鐵閘 urlopen 直接炸：建構子若打網路本測試即紅。
    client = OllamaEmbeddingClient(base_url="http://127.0.0.1:11434", model="bge-m3")
    assert client.model == "bge-m3"
    assert client.provider_name == "ollama"


def test_embed_request_body_never_contains_dimensions(captured_requests):
    """G18 鐵律：bge-m3 不支持 matryoshka，body 帶 dimensions 直接 HTTP 400。"""
    captured, responses = captured_requests
    responses.append(_FakeHTTPResponse(_embed_payload(2)))
    client = OllamaEmbeddingClient(model="bge-m3")
    out = client.embed_batch(["甲", "乙"])
    assert out is not None and len(out) == 2
    body = json.loads(captured[0].data.decode("utf-8"))
    assert "dimensions" not in body
    assert set(body.keys()) == {"model", "input"}
    assert body["input"] == ["甲", "乙"]


def test_http_404_returns_none_and_marks_unavailable(captured_requests):
    captured, responses = captured_requests
    responses.append(
        urllib.error.HTTPError("u", 404, "model not found", {}, io.BytesIO(b""))
    )
    client = OllamaEmbeddingClient(model="bge-m3")
    assert client.embed_batch(["x"]) is None
    assert client.is_available() is False  # 快取已標不可用，無第二次網路


def test_http_400_matryoshka_style_returns_none(captured_requests):
    _captured, responses = captured_requests
    responses.append(
        urllib.error.HTTPError("u", 400, "dimensions not supported", {}, io.BytesIO(b""))
    )
    assert OllamaEmbeddingClient(model="bge-m3").embed_batch(["x"]) is None


def test_malformed_payload_returns_none(captured_requests):
    _captured, responses = captured_requests
    responses.append(_FakeHTTPResponse({"unexpected": True}))
    assert OllamaEmbeddingClient().embed_batch(["x"]) is None


def test_batch_splitting_chunks_requests(captured_requests):
    captured, responses = captured_requests
    n = EMBED_REQUEST_BATCH_SIZE * 2 + 2  # 130 → 64+64+2 三請求
    responses.extend(
        [
            _FakeHTTPResponse(_embed_payload(EMBED_REQUEST_BATCH_SIZE)),
            _FakeHTTPResponse(_embed_payload(EMBED_REQUEST_BATCH_SIZE)),
            _FakeHTTPResponse(_embed_payload(2)),
        ]
    )
    out = OllamaEmbeddingClient().embed_batch([f"t{i}" for i in range(n)])
    assert out is not None and len(out) == n
    assert len(captured) == 3
    sizes = [len(json.loads(r.data.decode("utf-8"))["input"]) for r in captured]
    assert sizes == [EMBED_REQUEST_BATCH_SIZE, EMBED_REQUEST_BATCH_SIZE, 2]


def test_partial_chunk_failure_aborts_whole_batch(captured_requests):
    # 子批失敗 ⇒ 整批 None（部分結果無法對位 row，寧可下輪重試）。
    _captured, responses = captured_requests
    responses.extend(
        [
            _FakeHTTPResponse(_embed_payload(EMBED_REQUEST_BATCH_SIZE)),
            urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"")),
        ]
    )
    out = OllamaEmbeddingClient().embed_batch(
        [f"t{i}" for i in range(EMBED_REQUEST_BATCH_SIZE + 1)]
    )
    assert out is None


def test_empty_texts_no_network():
    assert OllamaEmbeddingClient().embed_batch([]) == []


def test_is_available_checks_tags_model_list(captured_requests):
    captured, responses = captured_requests
    responses.append(_FakeHTTPResponse({"models": [{"name": "bge-m3:latest"}]}))
    client = OllamaEmbeddingClient(model="bge-m3")
    assert client.is_available() is True
    assert "/api/tags" in captured[0].full_url
    # 快取：第二次不打網路（responses 已空，若再打會 AssertionError）。
    assert client.is_available() is True


def test_is_available_false_when_model_missing(captured_requests):
    _captured, responses = captured_requests
    responses.append(_FakeHTTPResponse({"models": [{"name": "qwen3.5:9b-q4_K_M"}]}))
    assert OllamaEmbeddingClient(model="bge-m3").is_available() is False


def test_is_available_false_on_connection_error(captured_requests):
    _captured, responses = captured_requests
    responses.append(ConnectionError("refused"))
    assert OllamaEmbeddingClient().is_available() is False


def test_detect_meta_drift_strict_triple():
    cur = {"provider": "ollama", "model": "bge-m3", "dims": 1024}
    assert detect_meta_drift(None, provider="ollama", model="bge-m3", dims=1024) is False
    assert detect_meta_drift(cur, provider="ollama", model="bge-m3", dims=1024) is False
    assert detect_meta_drift(cur, provider="ollama", model="bge-m4", dims=1024) is True
    assert detect_meta_drift(cur, provider="ollama", model="bge-m3", dims=512) is True
    assert detect_meta_drift(cur, provider="lm_studio", model="bge-m3", dims=1024) is True


# ── E3 修復輪：非 loopback base url 顯式放行 gate（防 cleartext 外送）─────────


class _CountingUrlopen:
    """計數 fake：被呼叫即記錄；rejection 路徑必須 0 呼叫（零外發證明）。"""

    def __init__(self):
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        return _FakeHTTPResponse({"models": [{"name": "bge-m3:latest"}]})


@pytest.fixture()
def counting_urlopen(monkeypatch):
    fake = _CountingUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def test_remote_env_base_url_rejected_without_allow_flag(
    monkeypatch, counting_urlopen, caplog
):
    """mutation 錨：移除 remote gate ⇒ 本測試紅（urlopen 被呼叫/available True）。"""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.5:11434")
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)
    with caplog.at_level("WARNING"):
        client = OllamaEmbeddingClient()
        assert client.is_available() is False
        assert client.embed_batch(["記憶內容"]) is None
    assert counting_urlopen.calls == 0  # 結構性零外發
    assert any(ALLOW_REMOTE_ENV in r.getMessage() for r in caplog.records)


def test_remote_base_url_accepted_with_explicit_allow_flag(
    monkeypatch, counting_urlopen
):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.5:11434")
    monkeypatch.setenv(ALLOW_REMOTE_ENV, "1")
    assert OllamaEmbeddingClient().is_available() is True
    assert counting_urlopen.calls == 1


def test_explicit_constructor_remote_base_also_gated(monkeypatch, counting_urlopen):
    """gate 對「解析後的 base」一體生效：建構子顯式傳遠端 URL 同樣須放行。"""
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)
    client = OllamaEmbeddingClient(base_url="http://example.test:11434")
    assert client.is_available() is False
    assert counting_urlopen.calls == 0


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
        "http://127.0.0.53:11434",  # 整個 127/8 loopback 段
    ],
)
def test_loopback_variants_allowed_without_flag(monkeypatch, counting_urlopen, base):
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)
    assert OllamaEmbeddingClient(base_url=base).is_available() is True
    assert counting_urlopen.calls == 1


def test_unparseable_host_treated_as_remote_fail_closed(monkeypatch, counting_urlopen):
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)
    client = OllamaEmbeddingClient(base_url="not a url")
    assert client.is_available() is False
    assert counting_urlopen.calls == 0
