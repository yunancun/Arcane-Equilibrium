#!/usr/bin/env python3
"""production listing capture-only collector — PG sink（雙寫 + JSONL fallback + resume）。

MODULE_NOTE:
  模塊用途：listing capture collector 的 PG 寫面（PA 設計 §3.3 / D-3）。雙寫：
    (1) market.klines（既有表，additive，ON CONFLICT DO NOTHING）— 確認的 1m kline
        進主 klines 表，與 engine 同 schema 同 dedup 鍵，下游 alpha 工具鏈無縫。
    (2) research.listing_capture_events（V130 新表，ON CONFLICT DO NOTHING）— 逐筆
        publicTrade + phase transition + capture_lag + kline 摘要，帶 leak-free
        provenance（OQ-3 PK 含 trade_id）。
    PG 寫失敗 → 重試 N 次後落 JSONL fallback（OQ-5）+ 記 error counter，**WS 繼續收**
    （捕獲不可因 PG 抖動中斷；listing 不可重捕）。
    restart-resume：query_resume_symbols 讀「最近 N 小時內有事件」的 symbol（G4）。
  主要類/函數：
    - ``DbConfig`` / ``read_db_config`` / ``connect_db`` — env-sourced 連線（比照 ref21）。
    - ``ListingPgSink`` — 連線管理 + 雙寫 + JSONL fallback + resume query + error counter。
  依賴：延遲 import psycopg2（連線時才 import，維持 import-time 零 DB 依賴）。JSONL
    fallback 用標準庫。
  硬邊界（capture-only 旁路）:
    - 寫 PG 僅限 research.listing_capture_events（新研究表）+ market.klines（additive
      ON CONFLICT DO NOTHING，與 engine 同表不覆蓋）。**不 UPDATE/DELETE 任何 live 資料**，
      不碰 governance/risk/lease/order 表。
    - 零 auth、零 order、零 intent、零 IPC、零 execution_authority。純資料採集 sink。
    - JSONL fallback 落 ${OPENCLAW_DATA_DIR}/listing_capture_fallback/（跨平台無硬編碼）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DbConfig:
    """PG 連線參數（env-sourced，跨平台無硬編碼）。"""

    host: str
    port: int
    db: str
    user: str
    password: str


def read_db_config(base: Path = REPO_ROOT) -> DbConfig:
    """讀 env + basic_system_services.env 組出 PG 連線參數（比照 ref21 read_db_config）。

    為什麼多候選 fallback：跨平台部署（Mac dev / Linux runtime / 未來 Apple Silicon）
    secrets 路徑不同；env 直接覆寫 > settings 檔 > home fallback。host 預設 127.0.0.1
    （feedback_cross_platform：禁硬編碼 hostname）。
    """
    values: dict[str, str] = {}
    candidates = [base / "settings/environment_files/basic_system_services.env"]
    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        candidates.append(
            Path(secrets_root) / "environment_files/basic_system_services.env"
        )
    candidates.append(
        Path.home() / "BybitOpenClaw/secrets/environment_files/basic_system_services.env"
    )
    for env_file in candidates:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return DbConfig(
        host=os.environ.get("PG_HOST") or values.get("POSTGRES_HOST") or "127.0.0.1",
        port=int(os.environ.get("PG_PORT") or values.get("POSTGRES_PORT") or "5432"),
        db=os.environ.get("PG_DB") or values.get("POSTGRES_DB") or "trading_ai",
        user=os.environ.get("PG_USER") or values.get("POSTGRES_USER") or "trading_admin",
        password=os.environ.get("PG_PASSWORD") or values.get("POSTGRES_PASSWORD") or "",
    )


def connect_db(config: DbConfig) -> Any:
    """連 PG（capture-only writer）。延遲 import psycopg2。"""
    import psycopg2  # type: ignore[import]

    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.db,
        user=config.user,
        password=config.password,
        connect_timeout=5,
        application_name="listing_capture_collector",
    )


def _resolve_fallback_dir() -> Path:
    """JSONL fallback 目錄（跨平台，禁硬編碼 /tmp/openclaw）。"""
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "listing_capture_fallback"


# ── research.listing_capture_events 欄位順序（與 V130 schema 對齊）──
_RESEARCH_COLUMNS = (
    "event_ts_exchange", "symbol", "event_kind", "trade_id", "launch_time_ms",
    "price", "side", "size",
    "prev_status", "new_status", "cur_auction_phase",
    "capture_lag_ms", "capture_verdict",
    "kline_open", "kline_high", "kline_low", "kline_close",
    "kline_volume", "kline_turnover", "kline_confirm",
    "ingest_ts_local_ms", "event_ts_exchange_ms", "ingest_minus_event_ms",
    "collector_version",
)


class ListingPgSink:
    """listing capture PG sink：雙寫 + JSONL fallback + resume query + error counter。

    為什麼把 conn 管理放這層：collector daemon 從 WS thread 與主 thread 都可能寫 PG
    （逐筆事件 + phase transition）；本 sink 用單一連線 + 寫操作加鎖序列化（psycopg2
    connection 非 thread-safe），fail-closed（寫失敗落 JSONL，不丟資料）。
    """

    def __init__(
        self,
        *,
        collector_version: str,
        pg_write_max_attempts: int = 3,
        pg_batch_size: int = 500,
        conn_factory: Optional[Any] = None,
        fallback_dir: Optional[Path] = None,
        clock_ms: Any = lambda: int(time.time() * 1000),
    ) -> None:
        import threading

        self._collector_version = collector_version
        self._max_attempts = pg_write_max_attempts
        self._batch_size = pg_batch_size
        # conn_factory 注入式（測試傳 fake；production 用 connect_db(read_db_config())）。
        self._conn_factory = conn_factory or (lambda: connect_db(read_db_config()))
        self._fallback_dir = fallback_dir if fallback_dir is not None else _resolve_fallback_dir()
        self._clock_ms = clock_ms
        self._conn: Any = None
        self._lock = threading.Lock()
        # 健康計數（healthcheck 讀）。
        self._research_rows_written = 0
        self._klines_rows_written = 0
        self._pg_write_errors = 0
        self._fallback_rows_written = 0
        self._last_write_ok_ms: Optional[int] = None

    # ── 連線管理 ──

    def _ensure_conn(self) -> Any:
        if self._conn is None:
            self._conn = self._conn_factory()
        return self._conn

    def _reset_conn(self) -> None:
        """連線異常時關閉重建（下次寫 _ensure_conn 重連）。"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - 關閉失敗不重要，目標是丟棄壞連線
                pass
            self._conn = None

    def close(self) -> None:
        with self._lock:
            self._reset_conn()

    # ── 對外寫入 API ──

    def write_research_events(self, rows: list[dict[str, Any]]) -> int:
        """寫一批 research.listing_capture_events（ON CONFLICT DO NOTHING）。

        為什麼 ON CONFLICT DO NOTHING：OQ-3 PK (symbol,event_kind,event_ts_exchange_ms,
        price,trade_id) 對重複事件天然 dedup（WS 重連可能重收）；後到者 no-op。
        寫失敗（重試耗盡）→ 落 JSONL fallback（OQ-5），回傳實際嘗試行數。
        """
        if not rows:
            return 0
        normalized = [self._normalize_research_row(r) for r in rows]
        ok = self._write_with_retry(self._do_write_research, normalized)
        if not ok:
            self._spill_to_fallback("research_events", normalized)
        return len(normalized)

    def write_klines(self, rows: list[dict[str, Any]]) -> int:
        """寫一批 market.klines（confirm 1m bar，additive ON CONFLICT DO NOTHING）。

        為什麼寫主 klines 表：listing symbol 的 1m bar 進主表，與 engine 同 PK
        (symbol,timeframe,ts) 同 dedup；collector 與 engine 對同 bar 重複寫 = 後者
        no-op，無需協調（PA 設計 §1.3）。寫失敗 → JSONL fallback。
        """
        if not rows:
            return 0
        ok = self._write_with_retry(self._do_write_klines, rows)
        if not ok:
            self._spill_to_fallback("klines", rows)
        return len(rows)

    # ── 重試包裝 ──

    def _write_with_retry(self, do_write: Any, rows: list[dict[str, Any]]) -> bool:
        """執行寫操作，失敗重試（連線異常重建）。全失敗回 False（觸發 JSONL fallback）。

        為什麼 WS 繼續收：捕獲不可因 PG 抖動中斷（listing 不可重捕，PA 設計 §3.5）；
        故寫失敗不 raise 到 WS thread，落 JSONL + 記 error，下批繼續嘗試。
        """
        with self._lock:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    conn = self._ensure_conn()
                    do_write(conn, rows)
                    conn.commit()
                    self._last_write_ok_ms = self._clock_ms()
                    # commit 成功即視為寫成功（回 True → 不觸發 JSONL fallback）；
                    # 本方法語義只關心成功/失敗，do_write 的 row 數不參與決策。
                    return True
                except Exception as exc:  # noqa: BLE001 - capture-only：寫失敗落 JSONL 不中斷捕獲
                    self._pg_write_errors += 1
                    logger.warning(
                        "listing_capture PG write attempt %s/%s failed: %s",
                        attempt, self._max_attempts, exc,
                    )
                    self._reset_conn()
                    if attempt < self._max_attempts:
                        time.sleep(0.25 * (2 ** (attempt - 1)))
            return False

    def _do_write_research(self, conn: Any, rows: list[dict[str, Any]]) -> int:
        from psycopg2.extras import execute_batch  # type: ignore[import]

        cols = ", ".join(_RESEARCH_COLUMNS)
        placeholders = ", ".join(f"%({c})s" for c in _RESEARCH_COLUMNS)
        sql = (
            f"INSERT INTO research.listing_capture_events ({cols}) "
            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        )
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows, page_size=self._batch_size)
        self._research_rows_written += len(rows)
        return len(rows)

    def _do_write_klines(self, conn: Any, rows: list[dict[str, Any]]) -> int:
        from psycopg2.extras import execute_batch  # type: ignore[import]

        # market.klines schema（PA 設計 §1.2）：ts/open_ts_ms/close_ts_ms/symbol/
        # timeframe/open/high/low/close/volume/turnover/tick_count。PK (symbol,timeframe,ts)。
        sql = (
            "INSERT INTO market.klines ("
            "ts, open_ts_ms, close_ts_ms, symbol, timeframe, "
            "open, high, low, close, volume, turnover, tick_count"
            ") VALUES ("
            "%(ts)s, %(open_ts_ms)s, %(close_ts_ms)s, %(symbol)s, %(timeframe)s, "
            "%(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(turnover)s, %(tick_count)s"
            ") ON CONFLICT (symbol, timeframe, ts) DO NOTHING"
        )
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows, page_size=self._batch_size)
        self._klines_rows_written += len(rows)
        return len(rows)

    # ── JSONL fallback（OQ-5）──

    def _spill_to_fallback(self, kind: str, rows: list[dict[str, Any]]) -> None:
        """PG 寫失敗（重試耗盡）→ 落 JSONL，供後續回補（listing 不可重捕）。

        為什麼必須 fallback：PG 長時間 down 時若直接丟資料，listing 上市瞬間就永久
        遺失（不可 retro-backfill）。落 JSONL（append-only，逐行 flush）保住資料，
        待 PG 恢復後由 operator/補回工具回灌。落盤失敗也不 raise（最後防線是 WS 仍收，
        記 error counter）。
        """
        try:
            self._fallback_dir.mkdir(parents=True, exist_ok=True)
            day = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
            path = self._fallback_dir / f"{kind}_{day}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
                fh.flush()
            self._fallback_rows_written += len(rows)
            logger.error(
                "listing_capture PG write failed; spilled %s rows to JSONL fallback %s",
                len(rows), path,
            )
        except OSError as exc:
            logger.error(
                "listing_capture JSONL fallback spill failed (%s rows lost from buffer): %s",
                len(rows), exc,
            )

    # ── restart-resume query（G4）──

    def query_resume_symbols(self, *, lookback_hours: float) -> list[dict[str, Any]]:
        """讀「最近 lookback_hours 內有捕捉事件」的 symbol（含最早事件時刻 + launchTime）。

        為什麼這樣 resume：daemon 重啟後從 PG 重建 capture window（不持久化 in-memory
        state，G4）。每 symbol 取 lookback 窗內最早事件時刻（≈ captured_at）→ ledger
        據此推算 window_expiry。launch_time_ms 取該 symbol 任一非 NULL 值。
        read-only 查詢；失敗回空 list（resume 退化為只靠 REST PreLaunch，不 raise）。
        """
        cutoff_ms = self._clock_ms() - int(lookback_hours * 60 * 60 * 1000)
        sql = """
            SELECT symbol,
                   MIN(event_ts_exchange_ms) AS earliest_event_ts_ms,
                   MAX(launch_time_ms)        AS launch_time_ms
            FROM research.listing_capture_events
            WHERE event_ts_exchange_ms >= %s
            GROUP BY symbol
        """
        with self._lock:
            try:
                conn = self._ensure_conn()
                with conn.cursor() as cur:
                    cur.execute(sql, (cutoff_ms,))
                    fetched = cur.fetchall()
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - resume 失敗退化為 REST-only，不中斷啟動
                self._pg_write_errors += 1
                logger.warning("listing_capture resume query failed: %s", exc)
                self._reset_conn()
                return []
        out: list[dict[str, Any]] = []
        for row in fetched:
            out.append({
                "symbol": str(row[0]),
                "earliest_event_ts_ms": int(row[1]) if row[1] is not None else 0,
                "launch_time_ms": int(row[2]) if row[2] is not None else None,
            })
        return out

    # ── 健康計數（healthcheck 讀）──

    def stats(self) -> dict[str, Any]:
        return {
            "research_rows_written": self._research_rows_written,
            "klines_rows_written": self._klines_rows_written,
            "pg_write_errors": self._pg_write_errors,
            "fallback_rows_written": self._fallback_rows_written,
            "last_write_ok_ms": self._last_write_ok_ms,
        }

    # ── row 正規化（補齊 research schema 缺欄為 None；統一 collector_version）──

    def _normalize_research_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """把上游事件 dict 正規化成 research schema 全欄位（缺欄補 None，PK 欄補預設）。

        為什麼補齊：execute_batch 的 named placeholder 要求每 row 含全部 key；上游
        publicTrade/phase/lag/kline 各只帶部分欄。trade_id/price 是 PK 成員：trade_id
        None → '' （非 trade 事件無 trade_id，與 V130 DEFAULT '' 對齊）；price None →
        以 0.0 入 PK（phase/lag 事件無 price，PK 仍唯一因 kind 不同）。
        """
        out: dict[str, Any] = {c: row.get(c) for c in _RESEARCH_COLUMNS}
        out["collector_version"] = self._collector_version
        # PK 成員 NOT NULL 對齊（V130：trade_id NOT NULL DEFAULT ''；price 為 PK 不可 NULL）。
        if out.get("trade_id") in (None, ""):
            out["trade_id"] = ""
        if out.get("price") is None:
            out["price"] = 0.0
        return out


def _json_default(obj: Any) -> str:
    """JSON 序列化 fallback（datetime → ISO；其餘 → str）。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


__all__ = [
    "DbConfig",
    "read_db_config",
    "connect_db",
    "ListingPgSink",
]
