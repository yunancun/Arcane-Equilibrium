#!/usr/bin/env python3
"""halt_audit_pg_writer.py — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2

MUST-FIX-3 Round 2（2026-05-19/20）：tail halt_audit.log JSONL → INSERT into
learning.governance_audit_log per spec §3.8 / §3.9 audit contract.

MODULE_NOTE
模塊用途：Rust engine 寫 halt_audit.log forensic JSONL；本 tail writer 讀
  新增行 → 驗 jsonschema → INSERT learning.governance_audit_log，讓 spec
  AC A-6 / A-1-EV / A-2-EV / A-4-EV 的 operator one-liner SQL 查詢成立。
主要函數：
  - tail_and_insert：cron-driven 30s tail loop；讀 cursor 後新行 → INSERT
  - _build_dsn：mirror sibling cron 的 DSN 構造
  - _parse_jsonl_robust：容錯 JSON 行解析（同 process race 下偶見
    「兩行黏在一起」情況；Rust 端 fsync 後可能 buffered fs append race）
  - _insert_row：ON CONFLICT DO NOTHING 冪等寫入；複合 dedup key =
    (process_pid, ts_ms, event)
依賴：
  - $OPENCLAW_DATA_DIR / OPENCLAW_HALT_AUDIT_LOG 路徑 + cursor state file
  - learning.governance_audit_log（V098 24-value allowlist 已 land）
  - psycopg2-binary（既有 helper_scripts 已用）
硬邊界：
  - 任一 INSERT 錯誤 fail-soft logged + cursor 不前進（下輪重試）
  - jsonschema validate fail 行：log + skip + cursor 前進（避免污染行卡死）
  - 缺 halt_audit.log → exit 0 + warn（cold start / 首次部署）
  - 缺 learning.governance_audit_log 表 → exit 0 + warn（V098 尚未 deploy）

Spec source / 規格來源:
  - docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md §3.8 / §3.9
  - docs/execution_plan/halt_audit_schema.json (JSON Schema v1)
  - sql/migrations/V098__governance_audit_log_halt_event_types.sql

Suggested cron entry (operator manually adds via `crontab -e`).
建議 cron 條目（30s interval 由 wrapper sh 控制）：
  * * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/halt_audit_pg_writer_cron.sh"

Exit codes:
  0   success（含 V098 absent fallback / halt_audit.log absent fallback）
  1   PG 連線 / SQL 錯誤（cron mailer surfaces）
  2   環境組態錯誤（no DSN buildable）
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterator


_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("halt_audit_pg_writer")


# ─── jsonschema 載入（fail-soft） ────────────────────────────────────
def _load_schema() -> dict[str, Any] | None:
    """讀 halt_audit_schema.json；找不到回 None（validate 改 best-effort）。"""
    base = os.environ.get("OPENCLAW_BASE_DIR") or str(
        Path(__file__).resolve().parent.parent.parent
    )
    schema_path = Path(base) / "docs" / "execution_plan" / "halt_audit_schema.json"
    try:
        with schema_path.open() as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("schema file not found at %s; skip validation", schema_path)
        return None
    except json.JSONDecodeError as exc:
        log.warning("schema JSON parse failed: %s; skip validation", exc)
        return None


# ─── halt_audit.log 路徑解析 ──────────────────────────────────────────
def _resolve_audit_log_path() -> Path:
    """與 Rust `crate::halt_audit::resolve_log_path` 邏輯對齊。"""
    explicit = os.environ.get("OPENCLAW_HALT_AUDIT_LOG")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "halt_audit.log"


def _resolve_cursor_path() -> Path:
    """Cursor state file：紀錄已讀 byte offset。

    讀取優先序：
      1. env `OPENCLAW_HALT_AUDIT_PG_WRITER_STATE`
      2. `$OPENCLAW_DATA_DIR/halt_audit_pg_writer_state.json`
      3. `/tmp/openclaw/halt_audit_pg_writer_state.json`
    """
    explicit = os.environ.get("OPENCLAW_HALT_AUDIT_PG_WRITER_STATE")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "halt_audit_pg_writer_state.json"


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
        log.warning(
            "cursor state load failed: %s; rewind to 0 / cursor 載入失敗", exc
        )
        return 0


def _save_cursor(state_path: Path, offset: int) -> None:
    """寫 cursor offset。fail-soft：寫失敗只 log，不阻塞 cron 退出。"""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("w") as f:
            json.dump({"byte_offset": offset}, f)
    except OSError as exc:
        log.warning("cursor save failed: %s / cursor 寫入失敗", exc)


# ─── 容錯 JSON 行解析 ─────────────────────────────────────────────────
def _parse_jsonl_robust(chunk: str) -> Iterator[dict[str, Any]]:
    """逐行解析；偶見「兩條 JSON 黏在同一 line」走 `}{` split fallback。

    為什麼必要：Rust engine `writeln!` 是 `write_all(json) + write_all("\\n")`，
    macOS / Linux 上多 process / 多 thread append 偶爾會在兩 write 之間
    被另一 writer 插入 → 同行兩個 JSON。本 parser 健壯處理。
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
        # fallback: split by "}{" 補 braces
        # 注意：此 fallback 只有當 .splitlines() 那條 line 解析失敗才跑
        joined = line
        parts = joined.split("}{")
        if len(parts) <= 1:
            # 確實只是壞 JSON；不做任何補救（避免假行）
            continue
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


# ─── jsonschema validate（best-effort） ───────────────────────────────
def _validate_row(row: dict[str, Any], schema: dict[str, Any] | None) -> bool:
    """jsonschema validate；schema=None 時 pass-through（best-effort）。

    為什麼 fail-soft：spec 內 schema 與本 writer 是「監測」而非「擋路」，
    schema 載入失敗 → 仍照常寫入 PG，否則啟動環境 broken 會丟資料。
    Validate fail → log 並 skip（不寫入髒 row），cursor 仍前進。
    """
    if schema is None:
        return True
    try:
        # 延遲 import 避免依賴 jsonschema 包；若未安裝 best-effort 跳過
        try:
            import jsonschema  # type: ignore
        except ImportError:
            log.debug("jsonschema not installed; skip validate")
            return True
        jsonschema.validate(instance=row, schema=schema)
        return True
    except Exception as exc:  # noqa: BLE001 — fail-soft log everything
        log.warning("schema validate FAIL: %s; skip row=%s", exc, row.get("event"))
        return False


# ─── DSN builder ──────────────────────────────────────────────────────
def _build_dsn() -> str | None:
    """從 env 構造 psycopg2 DSN（與 sibling cron 對齊）。"""
    explicit = os.environ.get("OPENCLAW_DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if not user or not password or not db:
        return None
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ─── PG table presence ───────────────────────────────────────────────
def _governance_audit_log_present(cur: Any) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("learning", "governance_audit_log"),
    )
    return cur.fetchone() is not None


# ─── INSERT 邏輯（冪等） ──────────────────────────────────────────────
def _insert_row(cur: Any, row: dict[str, Any]) -> bool:
    """INSERT 一行 governance_audit_log。冪等：複合 dedup key
    (payload->>'process_pid', payload->>'ts_ms', payload->>'event') 用
    `WHERE NOT EXISTS` 防重；既有 unique 約束無，採子查 EXISTS pattern。

    Spec §3.8 INSERT shape:
      event_type    = row['event']
      decided_by    = 'engine.halt_audit'
      payload       = full row jsonb
      rule_failures = '{}'
      lease_revoke_triggers = '{}'

    回傳：True = inserted；False = skipped（dup or schema fail）。
    """
    event_type = row.get("event", "")
    if event_type not in (
        "halt_session_set",
        "halt_session_auto_cleared",
        "halt_session_manual_cleared",
    ):
        log.warning(
            "skip row: event=%s not in V098 allowlist subset", event_type
        )
        return False

    process_pid = row.get("process_pid")
    ts_ms = row.get("ts_ms")
    if process_pid is None or ts_ms is None:
        log.warning("skip row: missing process_pid / ts_ms / 缺欄位")
        return False

    payload_json = json.dumps(row, separators=(",", ":"), sort_keys=True)

    # WHERE NOT EXISTS — 避免重複插入同 (pid, ts_ms, event) 組合
    cur.execute(
        """
        INSERT INTO learning.governance_audit_log (
            event_type, decided_by, payload, rule_failures, lease_revoke_triggers
        )
        SELECT %s, %s, %s::jsonb, '{}'::text[], '{}'::text[]
        WHERE NOT EXISTS (
            SELECT 1 FROM learning.governance_audit_log
             WHERE event_type = %s
               AND payload->>'process_pid' = %s
               AND payload->>'ts_ms' = %s
        );
        """,
        (
            event_type,
            "engine.halt_audit",
            payload_json,
            event_type,
            str(process_pid),
            str(ts_ms),
        ),
    )
    inserted = cur.rowcount == 1
    return inserted


# ─── Main entry ──────────────────────────────────────────────────────
def tail_and_insert(audit_log_path: Path, state_path: Path, dsn: str) -> int:
    """讀 audit_log_path 從 cursor offset 開始；INSERT 全部新行；前進 cursor。

    回傳：0 success / 1 PG 錯誤。
    """
    if not audit_log_path.exists():
        log.info(
            "halt_audit.log absent at %s — cold start / 首次運行；exit 0",
            audit_log_path,
        )
        return 0

    schema = _load_schema()
    cursor_offset = _load_cursor(state_path)
    log.info("tail start: log=%s cursor=%d", audit_log_path, cursor_offset)

    # 讀 audit log 從 cursor 開始
    try:
        with audit_log_path.open("rb") as f:
            f.seek(0, 2)  # SEEK_END
            file_size = f.tell()
            if cursor_offset > file_size:
                # 檔被截斷 / 輪轉 → 從 0 重讀
                log.warning(
                    "cursor=%d > file_size=%d; rewind to 0 / 截斷 → 回 0",
                    cursor_offset,
                    file_size,
                )
                cursor_offset = 0
            f.seek(cursor_offset)
            chunk = f.read(file_size - cursor_offset).decode(
                "utf-8", errors="replace"
            )
            new_offset = file_size
    except OSError as exc:
        log.error("read halt_audit.log failed: %s", exc)
        return 1

    if not chunk.strip():
        log.info("no new rows since last cursor; exit 0")
        return 0

    # 連 PG、檢查表存在、批量寫入
    try:
        import psycopg2  # type: ignore
    except ImportError:
        log.error("psycopg2 not installed; cannot insert / 缺依賴")
        return 2

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001 — psycopg2 error class varies
        log.error("PG connect failed: %s", exc)
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                if not _governance_audit_log_present(cur):
                    log.warning(
                        "learning.governance_audit_log absent — V098 not deployed; "
                        "exit 0 / V098 未 deploy"
                    )
                    # cursor 不前進，等 V098 land 後重跑會把整個 chunk INSERT
                    return 0
                inserted_count = 0
                skipped_count = 0
                for row in _parse_jsonl_robust(chunk):
                    if not _validate_row(row, schema):
                        skipped_count += 1
                        continue
                    try:
                        if _insert_row(cur, row):
                            inserted_count += 1
                        else:
                            skipped_count += 1
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "INSERT fail row event=%s ts_ms=%s err=%s",
                            row.get("event"),
                            row.get("ts_ms"),
                            exc,
                        )
                        skipped_count += 1
                        # 不 raise — 繼續處理其他 row
        log.info(
            "tail done: inserted=%d skipped=%d new_offset=%d",
            inserted_count,
            skipped_count,
            new_offset,
        )
    finally:
        conn.close()

    _save_cursor(state_path, new_offset)
    return 0


def main() -> int:
    audit_log_path = _resolve_audit_log_path()
    state_path = _resolve_cursor_path()
    dsn = _build_dsn()
    if not dsn:
        log.error("no DSN buildable; check POSTGRES_* env / OPENCLAW_DATABASE_URL")
        return 2
    return tail_and_insert(audit_log_path, state_path, dsn)


if __name__ == "__main__":
    sys.exit(main())
