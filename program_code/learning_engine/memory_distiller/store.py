"""store — agent.agent_memory 的寫入唯一入口（INSERT + 受限 UPDATE）。

MODULE_NOTE
模塊用途：封裝 V139 agent.agent_memory / agent_memory_embedding_meta 的全部
  SQL 存取。MemoryStore 以注入的 DB 連線運作（零模組級連線、零連線池 import），
  供 pipeline / backfill 使用；seed CLI 自帶 SQL 不經本模組（E1-B 線零重疊）。
主要類/函數：MemoryRecord、MemoryStore、new_record_id()。
依賴：僅 Python 標準庫（json/uuid/dataclasses）；conn 為 psycopg2 相容物件
  （cursor()/commit()/rollback()），由 caller 注入。
硬邊界（V139 application discipline，E2 審查重點 1）：
  - content 不可變：本模組沒有任何 UPDATE 觸碰 content；merge/update 產物
    是新 row（INSERT），舊 row 走 supersede 軟刪鏈。
  - UPDATE 僅限 status / superseded_by / updated_at / embedding /
    embedding_pending 五欄。
  - 全模組零物理刪除語句（V139 已對表 REVOKE 該權限；本模組連嘗試都不出現）。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

# ── SQL 常數（參數化；表名固定，不做字串拼接注入面）──────────────────────────

_INSERT_SQL = (
    "INSERT INTO agent.agent_memory "
    "(record_id, content, mem_type, priority, scene, source_refs, "
    " event_time_str, event_start, event_end, metadata) "
    "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb) "
    "ON CONFLICT (record_id) DO NOTHING"
)

# supersede：只動 status / superseded_by / updated_at 三欄（+ WHERE 守 active，
# 已 superseded 的 row 不重複改寫，保 superseded_by 鏈首次指向不被覆蓋）。
_SUPERSEDE_SQL = (
    "UPDATE agent.agent_memory "
    "SET status = 'superseded', superseded_by = %s, updated_at = NOW() "
    "WHERE record_id = ANY(%s) AND status = 'active'"
)

_LOAD_BY_IDS_SQL = (
    "SELECT record_id, content, mem_type, priority, scene, source_refs, "
    "       status, superseded_by, created_at, updated_at "
    "FROM agent.agent_memory WHERE record_id = ANY(%s)"
)

_EMBED_COLUMN_PROBE_SQL = (
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = 'agent' AND table_name = 'agent_memory' "
    "  AND column_name = 'embedding'"
)

# 補嵌游標（partial index idx_agent_memory_embed_pending 命中路徑）。
_LOAD_EMBED_PENDING_SQL = (
    "SELECT record_id, content FROM agent.agent_memory "
    "WHERE embedding_pending AND status = 'active' "
    "ORDER BY updated_at LIMIT %s"
)

# 補嵌寫回：只動 embedding / embedding_pending（不 bump updated_at——
# updated_at 語義保留給狀態/血緣變更，嵌入回填不是語義變更）。
_SET_EMBEDDING_SQL = (
    "UPDATE agent.agent_memory "
    "SET embedding = %s::vector, embedding_pending = false "
    "WHERE record_id = %s"
)

# 漂移重索引：全表標記待嵌 + 清空舊向量（PA spec §7 拍板語義）。
_MARK_ALL_PENDING_SQL = (
    "UPDATE agent.agent_memory "
    "SET embedding = NULL, embedding_pending = true"
)

_READ_META_SQL = (
    "SELECT provider, model, dims FROM agent.agent_memory_embedding_meta "
    "WHERE meta_id = 1"
)

_UPSERT_META_SQL = (
    "INSERT INTO agent.agent_memory_embedding_meta (meta_id, provider, model, dims, updated_at) "
    "VALUES (1, %s, %s, %s, NOW()) "
    "ON CONFLICT (meta_id) DO UPDATE "
    "SET provider = EXCLUDED.provider, model = EXCLUDED.model, "
    "    dims = EXCLUDED.dims, updated_at = NOW()"
)


def new_record_id() -> str:
    """產生 pipeline 記憶 record_id：``mem:<uuid12>``（seed CLI 用 mem:seed: 前綴，互不相撞）。"""
    return "mem:" + uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class MemoryRecord:
    """一條待寫入的記憶 row（status/embedding_pending 由 V139 DEFAULT 決定）。"""

    record_id: str
    content: str
    mem_type: str
    priority: int
    scene: str = ""
    source_refs: tuple[dict[str, Any], ...] = ()
    event_time_str: str = ""
    event_start: Any = None   # datetime | None（可解析時填）
    event_end: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    """agent.agent_memory 存取封裝（conn 注入；不擁有連線生命週期、不自行 commit）。

    事務邊界由 caller 控制（pipeline 的「單裁決一個事務」語義需要跨多語句
    的原子性，store 自行 commit 會破壞它）。
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # ── 寫入 ────────────────────────────────────────────────────────────

    def insert_record(self, record: MemoryRecord) -> bool:
        """INSERT 一條記憶；record_id 撞號時冪等 no-op（回 False）。"""
        cur = self._conn.cursor()
        cur.execute(
            _INSERT_SQL,
            (
                record.record_id,
                record.content,
                record.mem_type,
                int(record.priority),
                record.scene,
                json.dumps(list(record.source_refs), ensure_ascii=False),
                record.event_time_str,
                record.event_start,
                record.event_end,
                json.dumps(record.metadata, ensure_ascii=False),
            ),
        )
        return getattr(cur, "rowcount", 0) == 1

    def supersede_records(self, target_ids: Sequence[str], new_record_id: str) -> int:
        """把舊 row 標記為被 ``new_record_id`` 取代（軟刪鏈，永不物理刪）。

        只 UPDATE status/superseded_by/updated_at 三欄；content 永不觸碰。
        回實際被標記的 row 數。
        """
        if not target_ids:
            return 0
        cur = self._conn.cursor()
        cur.execute(_SUPERSEDE_SQL, (new_record_id, list(target_ids)))
        return getattr(cur, "rowcount", 0)

    # ── 讀取 ────────────────────────────────────────────────────────────

    def load_candidates_by_ids(self, record_ids: Sequence[str]) -> list[dict[str, Any]]:
        """按 record_id 批量讀 row（dedup 執行段取舊 row source_refs 用）。"""
        if not record_ids:
            return []
        cur = self._conn.cursor()
        cur.execute(_LOAD_BY_IDS_SQL, (list(record_ids),))
        return _rows_to_dicts(cur)

    def embedding_column_exists(self) -> bool:
        """探測 V140 embedding 欄是否存在（路徑 B 未 apply 時 backfill no-op 用）。"""
        cur = self._conn.cursor()
        cur.execute(_EMBED_COLUMN_PROBE_SQL)
        return cur.fetchone() is not None

    def load_embedding_pending(self, limit: int = 256) -> list[dict[str, Any]]:
        """補嵌游標讀取：待嵌 active row，updated_at 升序（partial index 命中）。"""
        cur = self._conn.cursor()
        cur.execute(_LOAD_EMBED_PENDING_SQL, (int(limit),))
        return _rows_to_dicts(cur)

    # ── 補嵌寫回（V140 軸；欄不存在時 caller 先 probe，不在此兜底）───────────

    def set_embedding(self, record_id: str, vector: Sequence[float]) -> None:
        """寫回單行 embedding 並清 pending 旗標。

        向量以 pgvector 文本格式 ``[x1,x2,...]`` 傳入（%s::vector cast）；
        真實 PG 接受度屬 E4 Linux dry-run 驗證範圍。
        """
        literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
        cur = self._conn.cursor()
        cur.execute(_SET_EMBEDDING_SQL, (literal, record_id))

    def mark_all_embedding_pending(self) -> int:
        """漂移重索引：全表 embedding 清空 + pending=true（meta 漂移時唯一觸發點）。"""
        cur = self._conn.cursor()
        cur.execute(_MARK_ALL_PENDING_SQL)
        return getattr(cur, "rowcount", 0)

    # ── embedding meta 單行表 ────────────────────────────────────────────

    def read_embedding_meta(self) -> dict[str, Any] | None:
        """讀 meta 單行（provider/model/dims）；不存在回 None。"""
        cur = self._conn.cursor()
        cur.execute(_READ_META_SQL)
        row = cur.fetchone()
        if row is None:
            return None
        return {"provider": row[0], "model": row[1], "dims": row[2]}

    def upsert_embedding_meta(self, provider: str, model: str, dims: int) -> None:
        """寫 meta 單行（INSERT 或覆蓋更新；meta_id 恆 1，CHECK 鎖死單行）。"""
        cur = self._conn.cursor()
        cur.execute(_UPSERT_META_SQL, (provider, model, int(dims)))


def _rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    """cursor 結果轉 dict list（欄位序與 SELECT 對齊；mirror layer2_critic 慣例）。"""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
