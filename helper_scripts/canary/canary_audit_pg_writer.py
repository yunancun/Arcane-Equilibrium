#!/usr/bin/env python3
"""canary_audit_pg_writer.py — ENGINE-AUDIT-VISIBILITY tail-bridge backstop (2026-06-15)

MODULE_NOTE
模塊用途：tail `canary_events.jsonl`（watchdog 寫的事件流）→ 冪等 INSERT 進 PG
  `audit_events`，作為 `engine_watchdog.py` direct fail-soft write 的 backstop。
  direct write 可能因 DB 暫時不可用 / psycopg2 缺 / 進程恰好崩潰而漏寫；本 cron tail
  以同一個確定性 dedup_key 補洞（含歷史 canary_events.jsonl 行）而不重複——`WHERE
  NOT EXISTS (event_details->>'dedup_key' = ...)` 保證真 backstop 不灌重複行。
  建模緊貼 sibling `halt_audit_pg_writer.py`（cursor tail / robust JSONL parse /
  fail-soft / cursor state file 全沿用其慣例）。
主要函數：
  - tail_and_insert：cron-driven tail loop；讀 cursor 後新行 → map → 冪等 INSERT。
  - _resolve_canary_events_path：與 watchdog 同法解析 canary_events.jsonl 路徑。
  - _resolve_cursor_path：cursor state file（紀錄已讀 byte offset）。
  - _canary_to_audit_row：把一條 canary 事件 dict 映射成 audit_events 行（含
    dedup_key；無 dedup_key 的舊行就地推導，與 direct write 同形）。
依賴：
  - canary_audit_common（DSN / dedup_key / INSERT shape 共用正本）
  - $OPENCLAW_DATA_DIR / canary_events.jsonl + cursor state file
  - psycopg2-binary（既有 helper_scripts 已用，延遲 import）
  - PG `audit_events`（schema：event_source/event_type/severity/summary/
    event_details jsonb/notes/created_at DEFAULT now()）
硬邊界：
  - 任一 INSERT 錯誤 fail-soft logged + cursor 不前進（下輪重試整個 chunk；冪等故安全）。
  - 壞 JSON 行：log + skip + 不卡死（robust parser 沿用 sibling）。
  - 缺 canary_events.jsonl → exit 0 + info（cold start / 首次部署）。
  - audit_events 表缺 → exit 0 + warn + cursor 不前進（等表 land 後重跑補全）。
  - 絕不碰任何硬邊界欄位 / 不寫 created_at（schema DEFAULT）。

Suggested cron entry（operator 手動 `crontab -e` 加入；本批不安裝，operator-gated）：
  建議每 1-2 分鐘 tail 一次（與 direct write 互補；direct 即時、bridge 補洞）：
  */2 * * * * cd "$OPENCLAW_BASE_DIR" && OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DATABASE_URL_FILE="$OPENCLAW_DATA_DIR/runtime_secrets/openclaw_database_url" \
    python3 helper_scripts/canary/canary_audit_pg_writer.py >> "$OPENCLAW_DATA_DIR/cron_logs/canary_audit_pg_writer.log" 2>&1

Exit codes:
  0   success（含 canary_events.jsonl absent / audit_events absent fallback）
  1   PG 連線 / SQL 錯誤（cron mailer surfaces）
  2   環境組態錯誤（no DSN buildable）
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import（cwd 漂移防護）
import canary_audit_common  # noqa: E402 — DSN / dedup_key / INSERT shape 共用正本


_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("canary_audit_pg_writer")

# canary_events.jsonl 檔名（與 engine_watchdog.CANARY_EVENTS_FILE 對齊；不 import watchdog
# 避免把 2000+ 行恢復元件拉進 cron 進程）。
CANARY_EVENTS_FILE = "canary_events.jsonl"


# ─── canary_events.jsonl 路徑解析（與 watchdog 同法） ──────────────────
def _resolve_canary_events_path() -> Path:
    """與 engine_watchdog 解析 canary_events.jsonl 同法：`<OPENCLAW_DATA_DIR>/canary_events.jsonl`。

    讀取優先序：
      1. env `OPENCLAW_CANARY_EVENTS_LOG`（顯式覆蓋，測試 / 非標準佈署用）
      2. `$OPENCLAW_DATA_DIR/canary_events.jsonl`
      3. `/tmp/openclaw/canary_events.jsonl`
    """
    explicit = os.environ.get("OPENCLAW_CANARY_EVENTS_LOG")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / CANARY_EVENTS_FILE


def _resolve_cursor_path() -> Path:
    """Cursor state file：紀錄已讀 byte offset（不碰 watchdog_state.json，獨立命名空間）。

    讀取優先序：
      1. env `OPENCLAW_CANARY_AUDIT_PG_WRITER_STATE`
      2. `$OPENCLAW_DATA_DIR/canary_audit_pg_writer_state.json`
      3. `/tmp/openclaw/canary_audit_pg_writer_state.json`
    """
    explicit = os.environ.get("OPENCLAW_CANARY_AUDIT_PG_WRITER_STATE")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "canary_audit_pg_writer_state.json"


def _load_cursor(state_path: Path) -> int:
    """讀 cursor offset；缺檔 / 壞檔 → 從 0 開始（fail-soft）。"""
    if not state_path.exists():
        return 0
    try:
        with state_path.open() as f:
            data = json.load(f)
        cur = data.get("byte_offset", 0)
        if isinstance(cur, int) and cur >= 0:
            return cur
        return 0
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("cursor state load failed: %s; rewind to 0 / cursor 載入失敗", exc)
        return 0


def _save_cursor(state_path: Path, offset: int) -> None:
    """寫 cursor offset。fail-soft：寫失敗只 log，不阻塞 cron 退出。"""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("w") as f:
            json.dump({"byte_offset": offset}, f)
    except OSError as exc:
        log.warning("cursor save failed: %s / cursor 寫入失敗", exc)


# ─── 容錯 JSON 行解析（鏡像 sibling halt_audit_pg_writer） ─────────────
def _parse_jsonl_robust(chunk: str) -> Iterator[dict[str, Any]]:
    """逐行解析；偶見「兩條 JSON 黏在同一 line」走 `}{` split fallback。

    為什麼必要：canary_events.jsonl 由 watchdog `write(json + "\\n")` append；多 writer
    （watchdog + incident_sentinel + 哨兵）並發 append 偶見兩 write 間被插入 → 同行兩 JSON。
    建模緊貼 halt_audit_pg_writer._parse_jsonl_robust。
    """
    seen: list[dict[str, Any]] = []
    for line in chunk.splitlines():
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                seen.append(obj)
                yield obj
                continue
        except json.JSONDecodeError:
            pass
        # fallback: split by "}{" 補 braces（只有 .splitlines() 那條 line 解析失敗才跑）
        parts = line.split("}{")
        if len(parts) <= 1:
            continue  # 確實只是壞 JSON；不做補救（避免假行）
        for i, p in enumerate(parts):
            seg = p
            if i > 0:
                seg = "{" + seg
            if not seg.endswith("}"):
                seg = seg + "}"
            try:
                obj = json.loads(seg)
                if isinstance(obj, dict) and obj not in seen:
                    seen.append(obj)
                    yield obj
            except json.JSONDecodeError:
                continue


# ─── PG table presence ───────────────────────────────────────────────
def _audit_events_present(cur: Any) -> bool:
    """audit_events 表存在性 probe（public schema；表名無 schema 前綴）。"""
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s LIMIT 1;",
        ("audit_events",),
    )
    return cur.fetchone() is not None


# ─── canary 事件 → audit_events 行映射 ────────────────────────────────
def _canary_to_audit_row(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    """把一條 canary 事件 dict 映射成 audit_events 行（含 dedup_key）。

    回傳 None = 此 canary 事件不寫 audit_events（非 watchdog 引擎健康事件，skip 非錯誤）。

    dedup_key 解析：
      - 優先用 canary 事件自帶的 `dedup_key`（direct write 路徑同步寫入的同形 key）。
      - 舊行 / 無 dedup_key 時：用 `ts` + 映射出的 event_type 就地推導（與 direct write
        build_dedup_key 完全同形），故歷史行也能被 backstop 補進去且與未來 direct write
        對齊不重複。`ts` 缺則無法構造穩定 key → skip（避免插入無法去重的行）。
    """
    canary_event = event.get("event")
    if not isinstance(canary_event, str):
        return None
    mapped = canary_audit_common.map_canary_to_audit(canary_event)
    if mapped is None:
        return None
    event_type, severity = mapped

    dedup_key = event.get("dedup_key")
    if not isinstance(dedup_key, str) or not dedup_key:
        ts = event.get("ts")
        if not isinstance(ts, (int, float)):
            log.warning(
                "skip canary event %s: no dedup_key and no usable ts / 無法構造去重 key",
                canary_event,
            )
            return None
        dedup_key = canary_audit_common.build_dedup_key(event_type, float(ts))

    # event_details：保留 canary payload 的數值欄位 + classification + hostname。
    details: dict[str, Any] = {"classification": event_type}
    for key in ("snapshot_age_seconds", "total_crashes", "total_outages", "restart_outcome"):
        if key in event:
            details[key] = event[key]
    details.setdefault("hostname", canary_audit_common.hostname())
    details["backfilled_by"] = "canary_audit_pg_writer"  # backstop 標記，與 direct write 區分

    summary = f"{event_type} (backstop from canary_events.jsonl)"
    notes = f"tail-bridge backstop; source canary event={canary_event}"
    return canary_audit_common.build_audit_row(
        event_type=event_type,
        severity=severity,
        summary=summary,
        event_details=details,
        notes=notes,
        dedup_key=dedup_key,
    )


# ─── Main entry ──────────────────────────────────────────────────────
def tail_and_insert(canary_log_path: Path, state_path: Path, dsn: str) -> int:
    """讀 canary_log_path 從 cursor offset 開始；冪等 INSERT 全部 mappable 新行；前進 cursor。

    回傳：0 success / 1 PG 錯誤。
    """
    if not canary_log_path.exists():
        log.info(
            "canary_events.jsonl absent at %s — cold start / 首次運行；exit 0",
            canary_log_path,
        )
        return 0

    cursor_offset = _load_cursor(state_path)
    log.info("tail start: log=%s cursor=%d", canary_log_path, cursor_offset)

    try:
        with canary_log_path.open("rb") as f:
            f.seek(0, 2)  # SEEK_END
            file_size = f.tell()
            if cursor_offset > file_size:
                # 檔被截斷 / 輪轉 → 從 0 重讀（冪等故重讀安全）。
                log.warning(
                    "cursor=%d > file_size=%d; rewind to 0 / 截斷 → 回 0",
                    cursor_offset, file_size,
                )
                cursor_offset = 0
            f.seek(cursor_offset)
            chunk = f.read(file_size - cursor_offset).decode("utf-8", errors="replace")
            new_offset = file_size
    except OSError as exc:
        log.error("read canary_events.jsonl failed: %s", exc)
        return 1

    if not chunk.strip():
        log.info("no new rows since last cursor; exit 0")
        return 0

    try:
        import psycopg2  # type: ignore
    except ImportError:
        log.error("psycopg2 not installed; cannot insert / 缺依賴")
        return 2

    try:
        conn = psycopg2.connect(
            dsn,
            connect_timeout=canary_audit_common.AUDIT_CONNECT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — psycopg2 error class varies
        log.error("PG connect failed: %s", exc)
        return 1

    inserted_count = 0
    skipped_count = 0
    table_present = True
    try:
        with conn:
            with conn.cursor() as cur:
                if not _audit_events_present(cur):
                    log.warning(
                        "audit_events table absent — exit 0, cursor NOT advanced "
                        "/ audit_events 表缺，cursor 不前進（等表 land 後補全）"
                    )
                    table_present = False
                else:
                    for event in _parse_jsonl_robust(chunk):
                        row = _canary_to_audit_row(event)
                        if row is None:
                            skipped_count += 1
                            continue
                        try:
                            if canary_audit_common.insert_audit_event_if_absent(cur, row):
                                inserted_count += 1
                            else:
                                skipped_count += 1  # dup（已被 direct write 或前次補洞插入）
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                "INSERT fail event=%s dedup_key=%s err=%s",
                                event.get("event"),
                                row["event_details"].get("dedup_key"),
                                exc,
                            )
                            skipped_count += 1  # 不 raise — 繼續處理其他 row
    finally:
        conn.close()

    if not table_present:
        # 表缺：cursor 不前進，等表 land 後重跑把整個 chunk 補進去。
        return 0

    log.info(
        "tail done: inserted=%d skipped=%d new_offset=%d",
        inserted_count, skipped_count, new_offset,
    )
    _save_cursor(state_path, new_offset)
    return 0


def main() -> int:
    canary_log_path = _resolve_canary_events_path()
    state_path = _resolve_cursor_path()
    dsn = canary_audit_common.resolve_dsn()
    if not dsn:
        log.error(
            "no DSN buildable; check OPENCLAW_DATABASE_URL_FILE / "
            "OPENCLAW_DATABASE_URL / POSTGRES_* env"
        )
        return 2
    return tail_and_insert(canary_log_path, state_path, dsn)


if __name__ == "__main__":
    sys.exit(main())
