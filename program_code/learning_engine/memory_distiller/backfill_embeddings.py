"""backfill_embeddings — 補嵌 batch job（embedding_pending 游標 + 漂移重索引）。

MODULE_NOTE
模塊用途：daily pipeline 尾端（flag OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1 時）
  批量補嵌 agent_memory 待嵌行；先做 meta 三元組漂移偵測，漂移 ⇒ 全表標記
  重索引（PA spec §7 拍板語義）。
主要類/函數：run_backfill()。
依賴：同 package store / embedding；conn 與 embed_client 注入。
硬邊界：
  - V140 未 apply（無 embedding 欄）⇒ 啟動探測欄存在性，缺 ⇒ no-op log
    （絕不讓 UndefinedColumn 冒泡殺掉 daily pipeline）。
  - embed 服務不可用 ⇒ no-op；任一子批 embed 失敗 ⇒ 該輪放棄（下輪游標
    自動續跑，embedding_pending 旗標未清即重試）。
  - 寫入僅 embedding / embedding_pending / meta 單行（V139 UPDATE 白名單內）。
"""

from __future__ import annotations

import logging
from typing import Any

from .embedding import detect_meta_drift
from .store import MemoryStore

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 256

# dims 探測文本（嵌一次取向量長度；bge-m3=1024，但以實測為準不硬編）。
_DIMS_PROBE_TEXT = "dimension probe"


def run_backfill(
    conn: Any,
    embed_client: Any,
    *,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
) -> dict[str, Any]:
    """執行一輪補嵌。回統計 dict，絕不 raise（fail-soft，daily pipeline 尾端安全）。"""
    store = MemoryStore(conn)

    # ── 0) V140 欄探測：缺 ⇒ no-op（路徑 B 未 apply 的合法常態）。
    try:
        if not store.embedding_column_exists():
            logger.info("backfill no-op：embedding 欄不存在（V140 未 apply）")
            return {"status": "no_embedding_column", "embedded": 0}
    except Exception as exc:  # noqa: BLE001
        _safe_rollback(conn)
        return {"status": "error", "error": f"column_probe_failed: {exc}", "embedded": 0}

    # ── 1) embed 服務可用性 + dims 實測。
    if embed_client is None or not embed_client.is_available():
        return {"status": "embed_unavailable", "embedded": 0}
    probe = embed_client.embed_batch([_DIMS_PROBE_TEXT])
    if not probe or not probe[0]:
        return {"status": "embed_unavailable", "embedded": 0}
    dims = len(probe[0])
    provider = str(getattr(embed_client, "provider_name", "ollama"))
    model = str(getattr(embed_client, "model", "unknown"))

    # ── 2) meta 漂移偵測（R6：嚴格三元組；漂移 ⇒ 全表重索引標記 + meta 更新）。
    reindexed = False
    try:
        meta = store.read_embedding_meta()
        if detect_meta_drift(meta, provider=provider, model=model, dims=dims):
            marked = store.mark_all_embedding_pending()
            store.upsert_embedding_meta(provider, model, dims)
            conn.commit()
            reindexed = True
            logger.warning(
                "embedding meta 漂移：%s → (%s,%s,%s)；全表 %s rows 標記重索引",
                meta, provider, model, dims, marked,
            )
        elif meta is None:
            # 首次補嵌：寫 meta 行（INSERT），不觸發重索引。
            store.upsert_embedding_meta(provider, model, dims)
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        _safe_rollback(conn)
        return {"status": "error", "error": f"meta_stage_failed: {exc}", "embedded": 0}

    # ── 3) 批處理：pending 游標 → embed → 逐行寫回（一輪一 commit）。
    try:
        rows = store.load_embedding_pending(limit=batch_limit)
        if not rows:
            return {"status": "ok", "embedded": 0, "reindexed": reindexed}
        vectors = embed_client.embed_batch([str(r.get("content", "")) for r in rows])
        if vectors is None or len(vectors) != len(rows):
            # 整批放棄：pending 旗標未清，下輪自動重試（不部分寫避免錯位）。
            return {"status": "embed_failed", "embedded": 0, "reindexed": reindexed}
        for row, vec in zip(rows, vectors):
            store.set_embedding(str(row.get("record_id", "")), vec)
        conn.commit()
        return {"status": "ok", "embedded": len(rows), "reindexed": reindexed}
    except Exception as exc:  # noqa: BLE001
        _safe_rollback(conn)
        return {"status": "error", "error": f"batch_stage_failed: {exc}", "embedded": 0}


def _safe_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:  # noqa: BLE001
        pass
