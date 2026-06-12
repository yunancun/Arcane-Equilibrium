"""recall — 記憶召回三級降級（vector → FTS → skip）+ B3 dormant 接縫。

MODULE_NOTE
模塊用途：對 agent.agent_memory 做相似度召回。dedup 候選池與未來 B3 prompt
  注入共用同一查詢核心。三級降級（PA spec §6.4）：
    L1 vector（V140 embedding 欄 + embed client 可用）
    L2 FTS（tsvector('simple') 與 pg_trgm 雙路單 SQL，GREATEST 取分）
    L3 skip（回空 list）
主要類/函數：RecallBundle、recall_top_k()、recall_for_prompt()。
依賴：標準庫 + 同 package store._rows_to_dicts；DB 連線注入（recall_top_k）
  或 lazy 取得（recall_for_prompt，import 時零 app/DB 依賴）。
硬邊界（E2 審查重點 3）：
  - 兩個降級 except 都不得 re-raise：召回失敗永遠降級/回空，絕不冒泡阻斷
    caller（dedup 失敗會誤殺蒸餾批；B3 失敗會阻斷 L2 session——皆不可接受）。
  - recall_for_prompt 簽名為 PA spec §8 釘死契約，未來批次 layer2_engine
    直接對接；本批不接線（zero engine diff），任何例外/逾時回空 bundle。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .store import _rows_to_dicts

logger = logging.getLogger(__name__)

# trgm 相似度門檻（G14 教訓：pg_trgm 預設 0.3 會擋掉真相關 0.27 命中；
# 與 layer2_critic LESSON_TRGM_MIN_SIM 同值對齊）。
RECALL_TRGM_MIN_SIM = 0.1

# hint 模式 word_similarity 門檻（MIT ratify 條件 ①）：pg_trgm 默認
# word_similarity_threshold=0.6 對 CJK 模糊 hint 偏嚴；0.3 取寬鬆向——
# top-5 + score DESC 下過寬只是弱命中墊池（dedup LLM 會裁、B3 有預算 cap），
# 漏召回才是 MIT [PROD] 實測的真風險（similarity 0.092<0.1 漏真命中）。
RECALL_HINT_WORD_SIM_MIN = 0.3

# L1 vector 召回 SQL（cosine 距離升序 = 相似度降序）。
_VECTOR_SQL = (
    "SELECT record_id, content, mem_type, priority, scene, created_at "
    "FROM agent.agent_memory "
    "WHERE status = 'active' AND embedding IS NOT NULL "
    "ORDER BY embedding <=> %s::vector "
    "LIMIT %s"
)

# L2 FTS 雙路單 SQL（PA spec §6.4）：tsvector 與 trgm 取 GREATEST 分。
# `%%` 為 psycopg2 參數風格下的 trgm 相似運算子字面（mirror layer2_critic）。
# content 模式（dedup：候選 content vs 庫存 content，同長度級幾何）用對稱
# similarity；MIT [PROD] 驗證 0.1 門檻對此幾何充分。
_FTS_SQL = (
    "SELECT record_id, content, mem_type, priority, scene, created_at, "
    "       GREATEST(ts_rank(content_tsv, plainto_tsquery('simple', %s)), "
    "                similarity(content, %s)) AS score "
    "FROM agent.agent_memory "
    "WHERE status = 'active' "
    "  AND (content_tsv @@ plainto_tsquery('simple', %s) OR content %% %s) "
    "ORDER BY score DESC "
    "LIMIT %s"
)

# hint 模式（B3 recall_for_prompt：短 hint vs 長 content，長度非對稱幾何）：
# MIT ratify 條件 ① —— 對稱 similarity 是「交集/聯集」度量，短 hint 對長混排
# content 實測 0.092<0.1 漏真命中；word_similarity（`<%` 運算子，hint 在前）
# 衡量 hint 與 content 內最相似連續詞段，正是此幾何的設計場景。
_FTS_HINT_SQL = (
    "SELECT record_id, content, mem_type, priority, scene, created_at, "
    "       GREATEST(ts_rank(content_tsv, plainto_tsquery('simple', %s)), "
    "                word_similarity(%s, content)) AS score "
    "FROM agent.agent_memory "
    "WHERE status = 'active' "
    "  AND (content_tsv @@ plainto_tsquery('simple', %s) OR %s <%% content) "
    "ORDER BY score DESC "
    "LIMIT %s"
)


def recall_top_k(
    conn: Any,
    text: str,
    k: int = 5,
    *,
    embed_client: Any = None,
    hint_mode: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """召回與 ``text`` 最相關的 top-k active 記憶。

    回 ``(rows, degraded_level)``，degraded_level ∈ {"vector","fts","skip"}。
    任何層級例外都降級、絕不 raise（硬邊界，見 MODULE_NOTE）。

    ``hint_mode``（MIT ratify 條件 ①）：True = 短 hint 幾何（B3
    recall_for_prompt），FTS 級 trgm 路改 word_similarity；False（默認）=
    content-vs-content 幾何（dedup），維持對稱 similarity + 0.1 門檻。
    """
    query = (text or "").strip()
    if not query:
        return [], "skip"

    # ── L1 vector：embed client 注入且可用才嘗試；任何例外（UndefinedColumn
    #    = V140 未 apply / embed 失敗 / 連線錯）→ rollback 後降 L2。
    if embed_client is not None:
        try:
            if embed_client.is_available():
                vectors = embed_client.embed_batch([query])
                if vectors:
                    literal = "[" + ",".join(repr(float(x)) for x in vectors[0]) + "]"
                    cur = conn.cursor()
                    cur.execute(_VECTOR_SQL, (literal, int(k)))
                    rows = _rows_to_dicts(cur)
                    if rows:
                        return rows, "vector"
                    # MIT F-2：查詢成功但 0 rows = 全表 embedding NULL（補嵌
                    # 未收斂/重索引窗口的常態）⇒ 落 FTS 而非回空 "vector"——
                    # 否則 dedup 池在最需要去重的窗口恆空（重複堆積）。
        except Exception as exc:  # noqa: BLE001 — 降級不冒泡（含 UndefinedColumn）
            logger.info("recall vector 級不可用，降 FTS: %s", exc)
            _safe_rollback(conn)

    # ── L2 FTS：事務內 SET LOCAL 降 trgm 門檻（G14）；例外 → 降 L3。
    try:
        cur = conn.cursor()
        if hint_mode:
            cur.execute(
                "SET LOCAL pg_trgm.word_similarity_threshold = %s",
                (RECALL_HINT_WORD_SIM_MIN,),
            )
            cur.execute(_FTS_HINT_SQL, (query, query, query, query, int(k)))
        else:
            cur.execute(
                "SET LOCAL pg_trgm.similarity_threshold = %s", (RECALL_TRGM_MIN_SIM,)
            )
            cur.execute(_FTS_SQL, (query, query, query, query, int(k)))
        return _rows_to_dicts(cur), "fts"
    except Exception as exc:  # noqa: BLE001 — 降級不冒泡
        logger.info("recall FTS 級失敗，降 skip: %s", exc)
        _safe_rollback(conn)

    # ── L3 skip：池空（dedup 對該候選 = 直接 store；B3 = 不注入）。
    return [], "skip"


def _safe_rollback(conn: Any) -> None:
    """rollback 失敗也吞掉（連線已死時 rollback 本身會拋）。"""
    try:
        conn.rollback()
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────────────────────────────────────────────────────────
# B3 dormant 接縫（PA spec §8；本批不接線，zero engine diff）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RecallBundle:
    """B3 召回注入 bundle（PA spec §8 釘死結構）。

    stable_block：rule + system_trait；priority DESC、record_id 次序穩定
      → 未來拼進 system prompt 尾（跨 session 字面穩定，KV cache 友好）。
    recent_block：incident；recency DESC → 未來拼進 user message 頭。
    """

    stable_block: str = ""
    recent_block: str = ""
    record_ids: list[str] = field(default_factory=list)
    total_chars: int = 0
    degraded_level: str = "skip"   # "vector" | "fts" | "skip"


# recall_for_prompt 內部取 k：stable/recent 兩塊各需素材，取大於 top-5 的
# 固定值（spec 未釘 k，小決策：10 = 兩塊各 ~5 條的素材上限）。
_PROMPT_RECALL_K = 10


def _open_db_conn() -> Any:
    """lazy 取得 app DB 連線 context manager（import 時零 app 依賴）。

    為什麼 lazy：memory_distiller 落點在 learning_engine，模組層 import app
    的 db_pool 會建立反向依賴 + 在 cron/測試環境拉起 FastAPI app 棧。B3 的
    真實 caller（layer2_engine）與 db_pool 同進程，函數內 import 必可解析；
    其他環境 import 失敗 → caller 收到例外 → 空 bundle（fail-open）。
    測試以 monkeypatch 本函數注入 FakeConn。
    """
    from control_api_v1.app import db_pool  # noqa: PLC0415 — 刻意 lazy

    return db_pool.get_pg_conn()


async def recall_for_prompt(
    symbol: str,
    context_hint: str,
    *,
    char_budget: int = 2000,
    timeout_s: float = 5.0,
) -> RecallBundle:
    """B3 召回接口（PA spec §8 釘死簽名；本批僅供未來批次接線）。

    任何例外/逾時 ⇒ 空 bundle ⇒ 行為等同 flag=0（fail-open，召回永不阻斷
    L2 session）。char_budget：stable 70% / recent 30%，超限按序丟整條。
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_recall_for_prompt_sync, symbol, context_hint, char_budget),
            timeout=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open：含 TimeoutError
        logger.warning("recall_for_prompt fail-open → 空 bundle: %s", exc)
        return RecallBundle()


def _recall_for_prompt_sync(
    symbol: str, context_hint: str, char_budget: int
) -> RecallBundle:
    """同步召回 + bundle 組裝（在 to_thread 內執行）。"""
    query = f"{(symbol or '').strip()} {(context_hint or '').strip()}".strip()
    if not query:
        return RecallBundle()
    with _open_db_conn() as conn:
        if conn is None:
            return RecallBundle()
        # 短 hint vs 長 content 幾何 ⇒ hint_mode（word_similarity，MIT 條件 ①）。
        rows, level = recall_top_k(conn, query, k=_PROMPT_RECALL_K, hint_mode=True)
    return build_recall_bundle(rows, level, char_budget=char_budget)


def build_recall_bundle(
    rows: list[dict[str, Any]],
    degraded_level: str,
    *,
    char_budget: int = 2000,
) -> RecallBundle:
    """把召回 rows 組裝為 RecallBundle（純函數，預算分配 stable 70%/recent 30%）。"""
    stable_budget = int(char_budget * 0.7)
    recent_budget = char_budget - stable_budget

    stable_rows = [r for r in rows if r.get("mem_type") in ("rule", "system_trait")]
    recent_rows = [r for r in rows if r.get("mem_type") == "incident"]

    # stable：priority DESC、record_id ASC（確定性次序 → 跨 session 字面穩定）。
    stable_rows.sort(key=lambda r: (-int(r.get("priority", 0)), str(r.get("record_id", ""))))
    # recent：recency DESC（created_at 缺者排最後；tuple 首元素隔離 None 防跨型比較）。
    recent_rows.sort(
        key=lambda r: (r.get("created_at") is not None, r.get("created_at") or ""),
        reverse=True,
    )

    stable_lines, ids_a = _fit_lines(stable_rows, stable_budget)
    recent_lines, ids_b = _fit_lines(recent_rows, recent_budget)
    stable_block = "\n".join(stable_lines)
    recent_block = "\n".join(recent_lines)
    return RecallBundle(
        stable_block=stable_block,
        recent_block=recent_block,
        record_ids=ids_a + ids_b,
        total_chars=len(stable_block) + len(recent_block),
        degraded_level=degraded_level,
    )


def _fit_lines(rows: list[dict[str, Any]], budget: int) -> tuple[list[str], list[str]]:
    """按序裝入預算：單條超出剩餘預算即整條丟棄（不截半句，PA spec §8）。"""
    lines: list[str] = []
    ids: list[str] = []
    used = 0
    for r in rows:
        line = f"- [{r.get('mem_type', '')}] {str(r.get('content', '')).strip()}"
        cost = len(line) + (1 if lines else 0)  # 換行符
        if used + cost > budget:
            continue
        lines.append(line)
        ids.append(str(r.get("record_id", "")))
        used += cost
    return lines, ids
