"""embedding — Ollama 嵌入客戶端（bge-m3，OpenAI 相容 /v1/embeddings）。

MODULE_NOTE
模塊用途：為 agent_memory 召回的 vector 級（V140 軸）提供嵌入。獨立小類、
  不擴 LocalLLMClient ABC（embed 非 generate 語義，動穩定抽象會波及全部
  既有 provider——PA spec §7 拍板）；仿其風格自帶 is_available /
  embed_batch / get_model_info。
主要類/函數：OllamaEmbeddingClient、detect_meta_drift()。
依賴：僅 Python 標準庫 urllib/json/os；零第三方 HTTP 套件。
硬邊界：
  - import 時零網路呼叫：全部 HTTP 在方法內發生，建構子只讀 env。
  - 嵌入請求 body 一律不帶 ``dimensions`` 欄位：bge-m3 不支持 matryoshka，
    帶了直接 HTTP 400（TencentDB-Agent-Memory README:336 實證坑，G18）。
  - 缺模型 / 服務不可達 ⇒ is_available()=False / embed_batch()=None，
    caller 降 FTS-only；本模組絕不向上拋網路例外。
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = "bge-m3"

# 單請求批量上限（小決策：64 條/請求，防單請求 payload 過大；
# spec 未釘值，僅要求「批次切分」可測）。
EMBED_REQUEST_BATCH_SIZE = 64

_DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# 非 loopback base url 的顯式放行 flag（E3 修復輪：防 cleartext 外送）。
ALLOW_REMOTE_ENV = "OPENCLAW_L2_MEMORY_EMBED_ALLOW_REMOTE"


def _is_loopback_base_url(base_url: str) -> bool:
    """判定 base url 是否指向本機 loopback。

    不可解析 / 無 host / 非 loopback hostname 一律回 False（fail-closed：
    判不準就當遠端，由 ALLOW_REMOTE flag 決定是否放行）。
    """
    try:
        host = urllib.parse.urlsplit(base_url).hostname
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OllamaEmbeddingClient:
    """bge-m3 嵌入客戶端（POST /v1/embeddings；OpenAI 相容回應格式）。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        # 建構子只讀 env，不打網路（import-time 安全由 caller 延後建構保證）。
        self._base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self._model = model or os.getenv(
            "OPENCLAW_L2_MEMORY_EMBED_MODEL", DEFAULT_EMBED_MODEL
        )
        self._timeout_s = float(timeout_s)
        self._available: bool | None = None  # 探測結果快取（None=未探測）
        # 為什麼拒絕非 loopback（E3 修復輪）：嵌入請求把記憶 content 以明文
        # HTTP 外送；非 loopback 目標必須 operator 顯式
        # OPENCLAW_L2_MEMORY_EMBED_ALLOW_REMOTE=1 才接受。拒絕 = embed 軸停用
        # （is_available 恆 False、_embed_request 恆 None ⇒ 全系統 FTS-only），
        # 不回退替代 URL（替你選一個目標比明確停用更危險）。
        self._remote_rejected = False
        if (
            not _is_loopback_base_url(self._base_url)
            and os.getenv(ALLOW_REMOTE_ENV, "0").strip() != "1"
        ):
            self._remote_rejected = True
            logger.warning(
                "OllamaEmbeddingClient：非 loopback base url 被拒絕"
                "（embed 軸停用，防 cleartext 外送）；需 %s=1 顯式放行。",
                ALLOW_REMOTE_ENV,
            )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model,
            "base_url": self._base_url,
        }

    # ── 可用性探測 ────────────────────────────────────────────────────────

    def is_available(self, *, force_check: bool = False) -> bool:
        """GET /api/tags 檢查模型已 pull（mirror OllamaClient 慣例）。

        G6 事實：現機未 pull bge-m3 ⇒ 部署日此處即 False ⇒ 全系統 FTS-only；
        operator pull 後自動升級，無需代碼變更。結果快取，force_check 重探。
        """
        if self._remote_rejected:
            return False  # 非 loopback 未放行：不探測、不外發任何請求
        if self._available is not None and not force_check:
            return self._available
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            names = [
                str(m.get("name", "")) for m in payload.get("models", [])
                if isinstance(m, dict)
            ]
            want = self._model.split(":")[0]
            self._available = any(n.split(":")[0] == want for n in names)
        except Exception as exc:  # noqa: BLE001 — 服務不可達=不可用，不冒泡
            logger.info("OllamaEmbeddingClient 不可用（tags 探測失敗）: %s", exc)
            self._available = False
        return self._available

    # ── 嵌入 ─────────────────────────────────────────────────────────────

    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        """批量嵌入；任何失敗回 None（caller 降級），絕不 raise。

        超過 EMBED_REQUEST_BATCH_SIZE 自動切分多請求；任一子批失敗即整批
        放棄（部分結果無法對位 row，寧可下輪重試）。
        """
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_REQUEST_BATCH_SIZE):
            chunk = texts[i : i + EMBED_REQUEST_BATCH_SIZE]
            vectors = self._embed_request(chunk)
            if vectors is None or len(vectors) != len(chunk):
                return None
            out.extend(vectors)
        return out

    def _embed_request(self, texts: list[str]) -> list[list[float]] | None:
        """單次 POST /v1/embeddings。

        body 僅 model + input 兩鍵——絕不帶 dimensions（G18 matryoshka 400 坑）。
        """
        if self._remote_rejected:
            # 雙保險：即使 caller 跳過 is_available()，也結構性保證零外發。
            return None
        body = {"model": self._model, "input": texts}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v1/embeddings",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 404=模型未 pull；400=請求不被接受（含 dimensions 類錯誤）。
            logger.warning("embed HTTP %s：模型/請求不可用，降 FTS", exc.code)
            self._available = False
            return None
        except Exception as exc:  # noqa: BLE001 — 連線錯不冒泡
            logger.warning("embed 請求失敗，降 FTS: %s", exc)
            return None

        rows = payload.get("data")
        if not isinstance(rows, list):
            logger.warning("embed 回應缺 data 數組，降 FTS")
            return None
        vectors: list[list[float]] = []
        for row in rows:
            vec = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vec, list) or not vec:
                logger.warning("embed 回應行缺 embedding，降 FTS")
                return None
            vectors.append([float(x) for x in vec])
        return vectors


def detect_meta_drift(
    meta_row: dict[str, Any] | None,
    *,
    provider: str,
    model: str,
    dims: int,
) -> bool:
    """meta 單行 vs 當前 config 嚴格三元組比對（R6：嚴格比對防誤觸發全表重索引）。

    meta 不存在回 False（首次補嵌走 INSERT meta，不是漂移）。
    """
    if meta_row is None:
        return False
    return (
        str(meta_row.get("provider")) != provider
        or str(meta_row.get("model")) != model
        or int(meta_row.get("dims", -1)) != int(dims)
    )
