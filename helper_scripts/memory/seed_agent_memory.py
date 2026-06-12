#!/usr/bin/env python3
"""seed_agent_memory — 兩源一次性重放 seed 進 agent.agent_memory（V139）。

MODULE_NOTE
模塊用途：
  L2 結構化記憶層（PA 2026-06-11 spec §9）的 seed CLI。把兩個既有知識源冪等重放
  入 V139 ``agent.agent_memory``：
    A 源：``agent.lessons`` WHERE lesson_type='dead_mode'（6 rows，V133）
          → mem_type='rule', priority=90, scene='seed:dead_mode'。
    B 源：repo 內 ``memory/MEMORY.md`` 索引行（``- [title](file.md) — summary``）
          → feedback_* → rule(80)；project_* → incident(70)；
          排除 reference_* 前綴與「External tool authority」整節。
          索引行即現成人寫蒸餾——零 LLM 依賴、確定性（PA 拍板）。
主要函數：
  - parse_memory_index(text)：純函數，B 源解析 + 白名單 + 敏感網（單測主體）。
  - build_lesson_rows(fetched)：純函數，A 源 DB rows → INSERT 參數。
  - apply_seeds(conn, rows)：冪等寫入（conn 注入；fake conn 可測）。
  - verify_recall(conn, hint)：seed 後真 recall SQL 驗收（spec §9：不能只驗 INSERT）。
  - main(argv)：CLI。默認 --dry-run（列將寫入清單，0 DB 連線）；
    --apply（alias --write）才真寫。
依賴：標準庫；--apply 路徑 lazy import psycopg2。
硬邊界：
  - **默認 --dry-run（print 不寫，0 DB 連線）**：承 0ce45a09 prod 污染教訓，
    任何寫庫工具必須默認無害（mirror helper_scripts/m4/seed_dead_mode_lessons.py）。
  - 自帶 INSERT SQL、不 import memory_distiller package（spec §9/§14：E1-A/E1-B
    檔案零重疊、兩線真並行）；SQL 形狀與 V139 store 契約一致
    （record_id 冪等錨 + ON CONFLICT DO NOTHING + 只填 INSERT 欄、其餘走 DDL 默認）。
  - 敏感過濾雙層（spec §9 + R8）：①來源白名單（僅 feedback_/project_ 前綴）；
    ②regex 安全網掃 content（密鑰 keyword + 個人路徑 pattern），命中即 skip+列報告。
  - 冪等錨：record_id = "mem:seed:" + sha256(content)[:12]；重跑 inserted=0。
  - 只寫 agent.agent_memory（學習平面，原則 7）；0 DELETE / 0 UPDATE。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

RECORD_ID_PREFIX = "mem:seed:"
SCENE_DEAD_MODE = "seed:dead_mode"
SCENE_MEMORY_INDEX = "seed:memory_index"
DEAD_MODE_LESSON_TYPE = "dead_mode"
EXCLUDED_SECTION = "External tool authority"

# 敏感網（spec §9 regex 原文 + IGNORECASE 加嚴：誤殺方向安全——skip 只是少 seed
# 一條並列入報告，漏放才是事故）。
# E3 修復輪補全（對齊 l2_secret_redactor 既有 keyword 家族）：hmac /
# signing_key（substring 亦蓋 auth_signing_key）/ private_key / X-BAPI-SIGN
# （Bybit 簽名 header）/ postgres DSN 帶密碼形（user:pass@——字元類寫法
# [^…]+ 線性掃描，避免相鄰貪婪量詞的回溯面）。無密碼 DSN（postgres://host/db）
# 不攔：純 host 引用非機密。
_SENSITIVE_KEYWORD_RE = re.compile(
    r"(api[_-]?key|secret|password|token|Bearer |hmac|signing[_-]?key"
    r"|private[_-]?key|X-BAPI-SIGN"
    r"|postgres(?:ql)?://[^\s@/]+:[^\s@/]+@)",
    re.IGNORECASE,
)
# 個人路徑偵測器（PM 要求）：匹配「home 目錄 + 任意使用者名」形狀。
# 注意：這是 detector pattern，非硬編任何機器路徑（跨平台紅線是具體使用者路徑字面）。
_PERSONAL_PATH_RE = re.compile(r"(?:/home|/Users)/[A-Za-z0-9_.\-]+")

# B 源索引行：`- [title](file.md) — summary`（分隔符容忍 em/en dash 與 hyphen）。
_INDEX_LINE_RE = re.compile(
    r"^-\s+\[(?P<title>[^\]]+)\]\((?P<fname>[^)\s]+\.md)\)\s*(?:[—–-]+\s*)?(?P<summary>.*)$"
)

_LESSONS_SQL = (
    "SELECT id, content FROM agent.lessons "
    "WHERE lesson_type = %(lesson_type)s ORDER BY id"
)

# 與 V139 store 契約一致：只填 INSERT 欄，status/embedding_pending/created_at/
# updated_at/event_* 走 DDL 默認；ON CONFLICT (record_id) DO NOTHING = 冪等錨。
_INSERT_SQL = """
INSERT INTO agent.agent_memory
    (record_id, content, mem_type, priority, scene, source_refs, metadata)
VALUES
    (%(record_id)s, %(content)s, %(mem_type)s, %(priority)s, %(scene)s,
     %(source_refs)s::jsonb, %(metadata)s::jsonb)
ON CONFLICT (record_id) DO NOTHING
"""

# 驗收用 recall SQL（spec §6.4 L2 級雙路同形，trgm 路取 hint 幾何）。
# MIT ratify 條件 ①：驗收 hint 是「短 hint vs 長 content」的長度非對稱幾何，
# 對稱 similarity 在 prod 實測漏真命中（0.092 < 0.1）⇒ 改 word_similarity
# （hint 在前；`<%%` 為 psycopg2 參數模式下 `<%` 運算子字面），與
# memory_distiller.recall hint_mode 同幾何（門檻 0.3 同步該模組常數）。
_RECALL_SQL = """
SELECT record_id,
       GREATEST(ts_rank(content_tsv, plainto_tsquery('simple', %(q)s)),
                word_similarity(%(q)s, content)) AS score
FROM agent.agent_memory
WHERE status = 'active'
  AND (content_tsv @@ plainto_tsquery('simple', %(q)s) OR %(q)s <%% content)
ORDER BY score DESC
LIMIT 5
"""

# 與 memory_distiller.recall.RECALL_HINT_WORD_SIM_MIN 同值（seed 自帶 SQL 不
# import M1 package——兩線檔案零重疊鐵則；數值漂移由雙側測試各自釘住）。
_VERIFY_WORD_SIM_THRESHOLD = 0.3

# 驗收 hint 默認值：en 對齊 A 源（dead-mode 教訓英文主幹）、zh 對齊 B 源
# （索引行中文摘要）。CLI 可覆蓋。
DEFAULT_VERIFY_HINT_EN = "dead mode funding beta neutral"
DEFAULT_VERIFY_HINT_ZH = "風控 教訓 修復"


def _repo_root_from_file() -> Path:
    # helper_scripts/memory/seed_agent_memory.py → parents[2] = srv repo root（實測）。
    return Path(__file__).resolve().parents[2]


def default_memory_md_path() -> Path:
    return _repo_root_from_file() / "memory" / "MEMORY.md"


def make_record_id(content: str) -> str:
    """冪等錨：同 content 永遠同 record_id（重跑 / 兩源重疊自然去重）。"""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return RECORD_ID_PREFIX + digest[:12]


def sensitive_reason(text: str) -> str | None:
    """敏感網：命中回 reason 字串（供 skip 報告），未命中回 None。

    為什麼 path 命中不回 echo 匹配片段：匹配內容本身可能就是要遮的資訊；
    keyword 命中只 echo pattern 詞（如 'token'），不含上下文。
    """
    m = _SENSITIVE_KEYWORD_RE.search(text)
    if m:
        return f"sensitive_keyword:{m.group(0).strip()}"
    if _PERSONAL_PATH_RE.search(text):
        return "personal_path"
    return None


def _make_row(
    *, content: str, mem_type: str, priority: int, scene: str, source_refs: list[dict]
) -> dict[str, Any]:
    return {
        "record_id": make_record_id(content),
        "content": content,
        "mem_type": mem_type,
        "priority": priority,
        "scene": scene,
        "source_refs": json.dumps(source_refs, ensure_ascii=False),
        "metadata": json.dumps({"seed_batch": "2026-06-11"}),
    }


def parse_memory_index(
    text: str,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """B 源解析：回 (rows, skipped)；skipped = [(識別字串, 原因)]。

    純函數（0 IO）：節追蹤 / 前綴白名單 / 敏感網 / 行格式全部可零連線單測。
    """
    rows: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue
        m = _INDEX_LINE_RE.match(stripped)
        if not m:
            continue  # 標頭 / 引言 / 非索引行：靜默略過（非排除事件）
        fname = m.group("fname")
        title = m.group("title").strip()
        summary = m.group("summary").strip()
        if current_section == EXCLUDED_SECTION:
            skipped.append((fname, f"excluded_section:{EXCLUDED_SECTION}"))
            continue
        if fname.startswith("feedback_"):
            mem_type, priority = "rule", 80
        elif fname.startswith("project_"):
            mem_type, priority = "incident", 70
        else:
            # 白名單之外（reference_* 等）一律排除（spec §9 ①來源白名單）。
            skipped.append((fname, "prefix_not_whitelisted"))
            continue
        content = f"{title} — {summary}" if summary else title
        reason = sensitive_reason(content)
        if reason:
            skipped.append((fname, reason))
            continue
        rows.append(
            _make_row(
                content=content,
                mem_type=mem_type,
                priority=priority,
                scene=SCENE_MEMORY_INDEX,
                source_refs=[{"kind": "memory_topic", "path": f"memory/{fname}"}],
            )
        )
    return rows, skipped


def build_lesson_rows(
    fetched: list[tuple[Any, str]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """A 源：agent.lessons dead-mode rows → INSERT 參數（敏感網同樣生效）。"""
    rows: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    for lesson_id, content in fetched:
        reason = sensitive_reason(content)
        if reason:
            skipped.append((f"lesson:{lesson_id}", reason))
            continue
        rows.append(
            _make_row(
                content=content,
                mem_type="rule",
                priority=90,
                scene=SCENE_DEAD_MODE,
                source_refs=[{"kind": "lesson", "id": int(lesson_id)}],
            )
        )
    return rows, skipped


def fetch_dead_mode_lessons(conn: Any) -> list[tuple[Any, str]]:
    with conn.cursor() as cur:
        cur.execute(_LESSONS_SQL, {"lesson_type": DEAD_MODE_LESSON_TYPE})
        return list(cur.fetchall())


def apply_seeds(conn: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """冪等寫入：逐條 INSERT ... ON CONFLICT DO NOTHING；回 (inserted, skipped)。

    conn 顯式注入（不在函數內建連線）：fake conn 可測 SQL 構造 / 冪等分支。
    失敗直接 raise（fail-loud，不吞）。
    """
    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(_INSERT_SQL, row)
            # ON CONFLICT DO NOTHING 擋掉時 rowcount=0（冪等 skip）；插入成功 =1。
            inserted += int(cur.rowcount or 0)
    conn.commit()
    return inserted, len(rows) - inserted


def verify_recall(conn: Any, hint: str) -> list[tuple[str, float]]:
    """seed 後驗收：真 recall SQL（spec §6.4 L2 級）。命中空 = 驗收 FAIL 信號。

    為什麼必跑：G4 pg_trgm 三重對齊教訓——INSERT 成功不代表檢索鏈真能命中
    （similarity 門檻 / 分詞 / 索引任一不對齊就是死資料）。
    """
    with conn.cursor() as cur:
        # SET LOCAL 須在事務內：psycopg2 默認非 autocommit，首條 execute 即開啟事務。
        cur.execute(
            "SET LOCAL pg_trgm.word_similarity_threshold = %(t)s",
            {"t": _VERIFY_WORD_SIM_THRESHOLD},
        )
        cur.execute(_RECALL_SQL, {"q": hint})
        hits = [(str(r[0]), float(r[1])) for r in cur.fetchall()]
    conn.commit()
    return hits


def _print_rows(label: str, rows: list[dict[str, Any]]) -> None:
    print(f"  [{label}] {len(rows)} 條：")
    for row in rows:
        preview = row["content"][:88].replace("\n", " ")
        print(
            f"    - {row['record_id']}  {row['mem_type']}/p{row['priority']}"
            f"  scene={row['scene']}"
        )
        print(f"      content[:88]: {preview}")


def _print_skipped(skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        print("  （敏感網/白名單 0 攔截）")
        return
    print(f"  攔截 {len(skipped)} 條（spec R8：dry-run 人工過目清單）：")
    for ident, reason in skipped:
        print(f"    - {ident}  reason={reason}")


def _resolve_conn_kwargs(dsn: str | None) -> dict[str, Any] | str | None:
    """寫模式連線解析：--dsn 優先；否則 POSTGRES_* env（spec §9）；都缺回 None。"""
    if dsn:
        return dsn
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    dbname = os.environ.get("POSTGRES_DB", "").strip()
    if not (user and password and dbname):
        return None
    return {
        "host": os.environ.get("POSTGRES_HOST", "").strip() or "127.0.0.1",
        "port": int(os.environ.get("POSTGRES_PORT", "").strip() or "5432"),
        "dbname": dbname,
        "user": user,
        "password": password,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "兩源（agent.lessons dead-mode + memory/MEMORY.md 索引行）冪等 seed 進 "
            "agent.agent_memory（默認 dry-run 不寫、0 DB 連線）。"
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="只 print 不寫（默認行為；顯式給以自描述）。",
    )
    group.add_argument(
        "--apply",
        "--write",
        dest="apply",
        action="store_true",
        help="真寫庫（--dsn 或 POSTGRES_* env 提供連線）。",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="顯式 PG DSN（優先於 POSTGRES_* env）。",
    )
    parser.add_argument(
        "--memory-md",
        default=None,
        help="B 源 MEMORY.md 路徑覆蓋（默認 repo 內 memory/MEMORY.md）。",
    )
    parser.add_argument(
        "--verify-hint-en",
        default=DEFAULT_VERIFY_HINT_EN,
        help="寫後 recall 驗收英文 hint（spec §9：中英各驗一次命中非空）。",
    )
    parser.add_argument(
        "--verify-hint-zh",
        default=DEFAULT_VERIFY_HINT_ZH,
        help="寫後 recall 驗收中文 hint。",
    )
    args = parser.parse_args(argv)

    md_path = Path(args.memory_md) if args.memory_md else default_memory_md_path()
    if not md_path.is_file():
        print(f"ERROR: MEMORY.md 不存在：{md_path}", file=sys.stderr)
        return 2
    b_rows, b_skipped = parse_memory_index(md_path.read_text(encoding="utf-8"))

    if not args.apply:
        # ── dry-run：0 DB 連線（A 源需 DB，誠實列為 deferred，不偽造預覽）──
        print("[DRY-RUN] 將寫入 agent.agent_memory（未寫庫；--apply 才落庫）：")
        print(
            f"  [A 源 agent.lessons lesson_type='{DEAD_MODE_LESSON_TYPE}'] "
            "deferred — 寫入時同連線讀取（dry-run 0 DB 連線；runtime 預期 6 rows）"
        )
        _print_rows(f"B 源 {md_path.name} 索引行", b_rows)
        _print_skipped(b_skipped)
        print(
            "[DRY-RUN] 冪等錨 = record_id（mem:seed:sha12(content)）；"
            "INSERT ... ON CONFLICT DO NOTHING，可重跑。"
        )
        return 0

    conn_target = _resolve_conn_kwargs(args.dsn)
    if conn_target is None:
        # 為什麼 fail-closed：寫庫目標必須顯式（--dsn）或完整（POSTGRES_* env），
        # 缺一不補不猜，杜絕誤寫錯環境。
        print(
            "ERROR: 寫模式需要 --dsn 或完整 POSTGRES_USER/PASSWORD/DB env。",
            file=sys.stderr,
        )
        return 2

    # lazy import：dry-run 路徑零第三方依賴（Mac 無 psycopg2 也能跑）。
    import psycopg2

    conn = (
        psycopg2.connect(conn_target)
        if isinstance(conn_target, str)
        else psycopg2.connect(**conn_target)
    )
    try:
        a_rows, a_skipped = build_lesson_rows(fetch_dead_mode_lessons(conn))
        all_rows = a_rows + b_rows
        inserted, skipped_existing = apply_seeds(conn, all_rows)
        print(
            f"[APPLY] A源={len(a_rows)} B源={len(b_rows)} "
            f"inserted={inserted} already_present={skipped_existing}"
            "（冪等：重跑 inserted=0）"
        )
        _print_skipped(a_skipped + b_skipped)

        # ── spec §9 驗收：中英 hint 各一次真 recall，命中非空才算 seed 成功 ──
        verify_failed = False
        for tag, hint in (("en", args.verify_hint_en), ("zh", args.verify_hint_zh)):
            hits = verify_recall(conn, hint)
            if hits:
                top = ", ".join(f"{rid}@{score:.3f}" for rid, score in hits[:3])
                print(f"[VERIFY-{tag}] hint={hint!r} hits={len(hits)} top: {top}")
            else:
                verify_failed = True
                print(
                    f"[VERIFY-{tag}] FAIL: hint={hint!r} 0 命中 — "
                    "檢索鏈未對齊（門檻/分詞/索引），seed 為死資料，須追因",
                    file=sys.stderr,
                )
        if verify_failed:
            return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
