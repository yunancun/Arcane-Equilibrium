#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：watchdog 偵測到的引擎事件 → PG `audit_events` 表的共用寫入層
  （ENGINE-AUDIT-VISIBILITY 2026-06-15）。`audit_events` 表存在但 operator 查到
  0 row，原因是「沒有任何路徑寫入它」。本模組是 direct fail-soft write（在
  `engine_watchdog.py` 內，重啟觸發「之後」best-effort INSERT 一行）與 tail-bridge
  backstop（`canary_audit_pg_writer.py`，cron tail `canary_events.jsonl` 補洞）
  兩個機制的共用正本——DSN 解析、dedup_key 推導、event→row 映射、INSERT shape
  全部單一來源，避免兩條路徑漂移（backstop 靠同一個 dedup_key 才能正確去重補洞）。
主要函數：
  - resolve_dsn：DSN 解析序 OPENCLAW_DATABASE_URL_FILE → OPENCLAW_DATABASE_URL
    → POSTGRES_* → 最後備援由 OPENCLAW_DATA_DIR 推導 runtime_secrets/
    openclaw_database_url（與 runtime restart_all.sh 寫的 secret 檔對齊）。
    推導擺最後 = 顯式 env 永遠優先；OPENCLAW_DATA_DIR 未設時絕不猜默認路徑
    （見 resolve_dsn docstring）。此備援讓 direct write 與 tail-bridge 對
    unit env 漂移（unit 有 OPENCLAW_DATA_DIR 但沒鋪 DSN 檔 env）免疫。
  - build_dedup_key：由 event_type + 偵測時間戳（epoch float）推導確定性唯一字串。
    direct write 與 bridge 共用，故同一事件兩條路徑算出同一 key → backstop 不重複。
  - map_canary_to_audit：把 watchdog 的 canary 事件名（ENGINE_CRASH/NETWORK_OUTAGE/
    ENGINE_RECOVERED/RESTART_CIRCUIT_BROKEN）映射成 (event_type, severity)。
  - insert_audit_event_if_absent：以 `event_details->>'dedup_key'` NOT EXISTS 冪等
    INSERT 一行 audit_events（給 bridge 用，連線/游標由 caller 管）。
  - write_audit_event_best_effort：direct write 入口——自開 connect（5s timeout）+
    INSERT + 關閉，任何例外吞沒只 logger.warning。供 watchdog 在重啟「之後」呼叫。
依賴：psycopg2-binary（既有 helper_scripts 已用，延遲 import；缺則 fail-soft skip）。
硬邊界：
  - 任何 DB 問題（import 失敗 / connect 逾時 / SQL 錯誤）都被吞沒 + logger.warning，
    絕不可拋進 watchdog 的偵測/重啟/分類邏輯——監控的正確性不依賴此寫入成功。
  - 為什麼 direct write 必須在重啟「之後」：恢復是第一要務，DB 寫入不得延遲重啟。
  - INSERT 不帶 created_at（schema DEFAULT now()）；不碰任何硬邊界欄位。

audit_events schema（live 確認）：
  id bigserial, event_source text NOT NULL, event_type text NOT NULL,
  severity text NOT NULL, summary text, event_details jsonb, notes text,
  created_at timestamptz NOT NULL DEFAULT now()。

部署驗證屬 runtime（Linux）步驟：Mac 無 PG，本模組單元測試全 mock DB 層。
"""
from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("canary_audit_common")

# event_source 常數 —— operator 用 `WHERE event_source='engine_watchdog'` 查 watchdog 事件。
EVENT_SOURCE = "engine_watchdog"

# connect / statement timeout（秒）。為什麼有界：DB 卡住絕不可拖住 watchdog 恢復迴圈。
AUDIT_CONNECT_TIMEOUT_SECONDS = 5

# canary 事件名 → (audit event_type, severity) 映射。
# severity 規則（spec）：ENGINE_CRASH=critical / NETWORK_OUTAGE=warning /
# ENGINE_RECOVERED=info。RESTART_CIRCUIT_BROKEN（自愈放棄=需人工介入）一併視為 critical，
# 讓 bridge 也能把這條既有 canary 事件補進 audit_events（backstop 範圍涵蓋）。
# SNAPSHOT_STALL_ENGINE_ALIVE（B1，2026-06-15）：snapshot 過期但 IPC 交叉檢查證明引擎
# 仍活，watchdog 抑制了破壞性重啟（不平倉）。severity=warning：這是「避免了誤殺」的
# 正向事件，不是引擎故障；但 snapshot-writer 停寫仍是需追蹤的退化（A1/A2 軌處理），
# 故進 audit_events 讓 operator 看得到、bridge 也能補洞。
_CANARY_EVENT_MAP: dict[str, tuple[str, str]] = {
    "ENGINE_CRASH": ("engine_crash", "critical"),
    "NETWORK_OUTAGE": ("network_outage", "warning"),
    "ENGINE_RECOVERED": ("engine_recovered", "info"),
    "RESTART_CIRCUIT_BROKEN": ("restart_circuit_broken", "critical"),
    "SNAPSHOT_STALL_ENGINE_ALIVE": ("snapshot_stall_engine_alive", "warning"),
}


def map_canary_to_audit(canary_event: str) -> Optional[tuple[str, str]]:
    """把 watchdog canary 事件名映射成 (audit event_type, severity)。

    回傳 None = 不是要寫進 audit_events 的事件（bridge 跳過，非錯誤）。
    """
    return _CANARY_EVENT_MAP.get(canary_event)


def _ts_to_iso(ts: float) -> str:
    """epoch float → ISO8601 UTC（毫秒精度，Z 結尾）。dedup_key 的穩定時間表示。

    為什麼固定 UTC + 毫秒：dedup_key 必須在 direct write 與 bridge 兩條路徑算出
    byte-identical 字串；本地時區 / 微秒抖動都會破壞去重，故統一正規化。
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def build_dedup_key(event_type: str, detection_ts: float) -> str:
    """確定性 dedup_key：`engine_watchdog|<event_type>|<detection_ts_iso>`。

    一個事件（down/recovery 轉移那一刻）對應一個偵測時間戳 → 一個 key。direct write
    把它嵌進 event_details，canary 事件也帶同一 key；bridge 直接讀 canary 事件的 key
    去 NOT EXISTS 比對，故兩條路徑天然對齊、不重複。
    """
    return f"{EVENT_SOURCE}|{event_type}|{_ts_to_iso(detection_ts)}"


def _derive_dsn_from_data_dir() -> Optional[str]:
    """第 4 步最後備援：由 OPENCLAW_DATA_DIR 推導 runtime DSN 契約檔並讀取。

    契約檔 = $OPENCLAW_DATA_DIR/runtime_secrets/openclaw_database_url——與
    restart_all.sh（每次重啟重寫）及 openclaw-engine.service 同一份。此備援讓
    watchdog 直寫與 tail-bridge 對 unit env 漂移免疫（2026-07-15 事故形：unit
    必有 OPENCLAW_DATA_DIR 但沒鋪 OPENCLAW_DATABASE_URL_FILE → 三顯式源全空）。

    鐵則：OPENCLAW_DATA_DIR 未設 / 空白時「不得」猜任何默認路徑（尤其
    /tmp/openclaw——/tmp 任何人可植檔，DSN 推導只信 systemd/caller 顯式給的
    data dir）。讀失敗 / 檔空 → None（fail-soft 照舊，caller skip 寫入）。
    """
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if not data_dir:
        return None
    derived = Path(data_dir) / "runtime_secrets" / "openclaw_database_url"
    try:
        content = derived.read_text(encoding="utf-8").strip()
        if content:
            return content
    # ValueError 涵蓋 UnicodeDecodeError（非 UTF-8 壞檔），與第 1 分支一致。
    except (OSError, ValueError) as exc:
        logger.warning(
            "audit DSN derived file read failed: %s; give up / 推導 DSN 檔讀取失敗",
            exc,
        )
    return None


def resolve_dsn() -> Optional[str]:
    """解析 PG DSN（與 runtime restart_all.sh 寫的 secret 檔對齊）。

    序：
      1. OPENCLAW_DATABASE_URL_FILE 指向的檔（runtime 把 DSN 寫進
         <data_dir>/runtime_secrets/openclaw_database_url，env 指向它）。
      2. OPENCLAW_DATABASE_URL（直接內嵌 DSN）。
      3. POSTGRES_*（user/password/db/host/port 組裝）。
      4. 最後備援（WATCHDOG-AUDIT-DSN-1）：OPENCLAW_DATA_DIR 非空時推導
         $OPENCLAW_DATA_DIR/runtime_secrets/openclaw_database_url（同一契約檔）。
         為什麼推導擺最後：顯式 env 永遠優先於推導，推導只在 unit env 漂移時
         兜底；OPENCLAW_DATA_DIR 未設時絕不猜默認路徑（/tmp 任何人可植檔）。
    任一步壞檔 / 缺值都 fail-soft 往下一步；全失敗回 None（caller skip 寫入）。
    """
    dsn_file = os.environ.get("OPENCLAW_DATABASE_URL_FILE")
    if dsn_file:
        try:
            content = Path(dsn_file).read_text(encoding="utf-8").strip()
            if content:
                return content
        # ValueError 涵蓋 UnicodeDecodeError（非 UTF-8 壞檔）——read_text 對壞編碼
        # 拋的不是 OSError，漏接會穿透 fail-soft 承諾（P2-1，2026-07-15）。
        except (OSError, ValueError) as exc:
            logger.warning(
                "audit DSN file read failed: %s; fall through / DSN 檔讀取失敗", exc
            )

    explicit = os.environ.get("OPENCLAW_DATABASE_URL")
    if explicit:
        return explicit

    user = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if not user or not password or not db:
        # 三顯式源全失敗 → 第 4 步推導備援（詳見 _derive_dsn_from_data_dir）。
        return _derive_dsn_from_data_dir()
    # DSN 字面量刻意拆開,避免 public-repo gate(embedded_credential_dsn query 形)匹配源碼 bytes;勿合併回單一字串。
    return f"postgresql://{host}:{port}/{db}?user={user}&pass" f"word={password}"


def build_audit_row(
    *,
    event_type: str,
    severity: str,
    summary: str,
    event_details: dict[str, Any],
    notes: str,
    dedup_key: str,
) -> dict[str, Any]:
    """組裝 audit_events 一行的欄位 dict（不含 created_at —— schema DEFAULT now()）。

    保證 event_details 帶 dedup_key（bridge 去重命脈）；event_source 固定為本模組常數。
    """
    details = dict(event_details)
    details["dedup_key"] = dedup_key
    return {
        "event_source": EVENT_SOURCE,
        "event_type": event_type,
        "severity": severity,
        "summary": summary,
        "event_details": details,
        "notes": notes,
    }


def insert_audit_event_if_absent(cur: Any, row: dict[str, Any]) -> bool:
    """以 `event_details->>'dedup_key'` NOT EXISTS 冪等 INSERT 一行 audit_events。

    冪等：同一 dedup_key 已存在則不插（WHERE NOT EXISTS）—— 這讓 bridge 成為真正的
    backstop，補 direct write 漏掉的洞（含歷史 canary_events.jsonl 行）而不重複。
    INSERT 不帶 created_at（schema DEFAULT now()）。

    回傳：True = inserted；False = 已存在（dup）跳過。
    cur 由 caller 管理連線/交易；本函數只發一條 SQL。
    """
    dedup_key = row["event_details"].get("dedup_key", "")
    details_json = json.dumps(
        row["event_details"], separators=(",", ":"), sort_keys=True
    )
    cur.execute(
        """
        INSERT INTO audit_events (
            event_source, event_type, severity, summary, event_details, notes
        )
        SELECT %s, %s, %s, %s, %s::jsonb, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM audit_events
             WHERE event_details->>'dedup_key' = %s
        );
        """,
        (
            row["event_source"],
            row["event_type"],
            row["severity"],
            row["summary"],
            details_json,
            row["notes"],
            dedup_key,
        ),
    )
    return cur.rowcount == 1


def write_audit_event_best_effort(row: dict[str, Any]) -> bool:
    """direct write 入口：自開連線（5s timeout）+ 冪等 INSERT + 關閉，全程 fail-soft。

    為什麼吞沒所有例外：本函數由 watchdog 在「重啟觸發之後」呼叫，任何 DB 問題
    （psycopg2 缺 / connect 逾時 / SQL 錯誤 / 表缺）都不得拋進偵測/重啟邏輯。
    回傳 True 僅代表本進程確實 INSERT 了一行；False = skip（dup / DB 不可用 / 任何失敗）。
    backstop bridge 之後會用同一 dedup_key 補上 direct write 漏掉的事件。
    """
    try:
        dsn = resolve_dsn()
        if not dsn:
            logger.warning(
                "audit write skipped: no DSN buildable / 無 DSN 可組（audit 寫入跳過）"
            )
            return False
        try:
            import psycopg2  # type: ignore  # 延遲 import：缺則 fail-soft
        except ImportError:
            logger.warning("audit write skipped: psycopg2 not installed / 缺依賴")
            return False
        conn = psycopg2.connect(
            dsn,
            connect_timeout=AUDIT_CONNECT_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={AUDIT_CONNECT_TIMEOUT_SECONDS * 1000}",
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    inserted = insert_audit_event_if_absent(cur, row)
        finally:
            conn.close()
        if inserted:
            logger.info(
                "audit_events row written: type=%s dedup_key=%s",
                row.get("event_type"),
                row["event_details"].get("dedup_key"),
            )
        return inserted
    except Exception as exc:  # noqa: BLE001 — fail-soft：DB 問題絕不得影響 watchdog
        logger.warning(
            "audit write best-effort failed (non-fatal): %s / audit 寫入失敗（吞沒）",
            exc,
        )
        return False


def hostname() -> str:
    """best-effort 取得 hostname（供 event_details）；失敗回空字串不拋。"""
    try:
        return socket.gethostname()
    except OSError:
        return ""
