"""L2 結構化記憶層 dormant 哨兵 — `[88]`-`[89]`。

MODULE_NOTE
模塊用途：L2 記憶層（PA 2026-06-11 spec §12；V139 agent.agent_memory +
  daily 蒸餾 cron）的兩軸哨兵：
    [88] l2_memory_pipeline_freshness — pipeline flag=1 時驗表可達 + 游標
         滯後 ≤3 日（cursor 檔 = cron_state/l2_memory_distill_cursor.json）
         + 語義死亡軸（連續 3 個有 l2 材料的日子 stored=0 ⇒ WARN；資料源 =
         CLI 寫的 day_stats 環形檔，MIT F-4 修復輪）。
    [89] l2_memory_embedding_drift — backfill flag=1 時驗 embedding meta
         （provider/model/dims）vs 當前 config 漂移。
主要函數：check_88_* / check_89_*（``(cur) -> (status, msg)`` 與既有 checks_*
  同契約）。
依賴：psycopg2 cursor（runner 注入）+ env flag/路徑；0 其他依賴。
硬邊界：**flag-OFF → PASS-skip 不 FAIL**（dormant 系統不製造噪音——部署即
  flag-OFF 是設計態，PM 拍板 SKIP 語意）；flag-ON 才做真檢查；全部唯讀
  SELECT；表缺而 flag=1 = 真配置錯 → WARN（與 [83]-[87] 無 flag 的
  graceful-absent PASS-skip 不同：這裡 flag 即 operator 顯式啟用聲明）。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_FLAG_ENV = "OPENCLAW_L2_MEMORY_PIPELINE"
BACKFILL_FLAG_ENV = "OPENCLAW_L2_MEMORY_EMBED_BACKFILL"
EMBED_MODEL_ENV = "OPENCLAW_L2_MEMORY_EMBED_MODEL"

# 與 spec §7 embedding 軸常數對齊（meta 漂移比對的 config 側）。
EXPECTED_EMBED_PROVIDER = "ollama"
EXPECTED_EMBED_DIMS = 1024
DEFAULT_EMBED_MODEL = "bge-m3"

# spec §12：cursor 滯後 >3 日（健康態 = 昨日已處理 → lag=1）。
CURSOR_LAG_WARN_DAYS = 3
_CURSOR_REL_PATH = "cron_state/l2_memory_distill_cursor.json"

# 語義死亡軸（MIT F-4 / E2 LOW-3 修復輪）：連續 N 個「l2_calls 有料」的已處理
# 日 stored=0 ⇒ WARN。資料源 = cron CLI 寫的 per-day summary 環形檔（游標旁）。
SEMANTIC_DEATH_CONSECUTIVE_DAYS = 3
_STATS_FILENAME = "l2_memory_distill_day_stats.json"


def _rollback_quietly(cur: Any) -> None:
    """前一 check 的 aborted txn 不應汙染本 check（既有 checks_* 慣例）。"""
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - rollback 失敗讓後續 execute 自然炸出
        pass


def _flag_on(name: str) -> bool:
    return os.environ.get(name, "0").strip() == "1"


def _table_deployed(cur: Any, qualified_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (qualified_name,))
    row = cur.fetchone()
    return bool(row and row[0])


def _cursor_path() -> Path:
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip()
    return Path(data_dir) / _CURSOR_REL_PATH


def _utc_today() -> date:
    # 獨立小函數：測試 monkeypatch 控制「今天」以驗 lag 邏輯。
    return datetime.now(timezone.utc).date()


def _semantic_death_streak(stats_path: Path, cursor_day: date) -> bool:
    """連續 N 個已處理日「materials_l2>0 且 stored=0」⇒ 語義性死亡（MIT F-4）。

    為什麼需要 stats 檔而非只看游標：游標「成功才推進」只證管線跑過——上游
    l2_calls writer 死亡或 parser 全丟時，游標照推而記憶零累積，[88] 原本
    恆 PASS。materials_l2=0 的日子（無料可蒸）不是死亡證據，會切斷連續性。
    fail-soft：檔缺/壞損/與游標不同步（最新 entry ≠ 游標日，例如 pipeline
    自管模式推的游標、stats 由 CLI 獨家寫）⇒ False，絕不誤 WARN。
    """
    try:
        payload = json.loads(stats_path.read_text(encoding="utf-8"))
        entries = [
            d for d in payload.get("days", []) if isinstance(d, dict)
        ] if isinstance(payload, dict) else []
        if len(entries) < SEMANTIC_DEATH_CONSECUTIVE_DAYS:
            return False
        if str(entries[-1].get("utc_date", "")) != cursor_day.isoformat():
            return False  # stats 與游標不同步（stale）⇒ 不據以告警
        recent = entries[-SEMANTIC_DEATH_CONSECUTIVE_DAYS:]
        return all(
            int(e.get("materials_l2", 0) or 0) > 0
            and int(e.get("stored", 0) or 0) == 0
            for e in recent
        )
    except Exception:  # noqa: BLE001 - 觀測檔任何壞損 ⇒ 不告警（fail-soft）
        return False


def check_88_l2_memory_pipeline_freshness(cur: Any) -> tuple[str, str]:
    """[88] 蒸餾管線 freshness：flag-OFF → PASS-skip；flag-ON → 表可達 + 游標滯後。

    為什麼 flag=1 而表缺/游標缺是 WARN 非 FAIL：管線是學習平面（零交易影響），
    壞掉的代價是記憶不再累積，不是資金風險——WARN 引導追因即足，不該佔用
    FAIL 等級的告警頻寬。
    """
    _rollback_quietly(cur)
    if not _flag_on(PIPELINE_FLAG_ENV):
        return (
            "PASS",
            f"SKIP (flag off): {PIPELINE_FLAG_ENV} != 1 — pipeline dormant",
        )
    if not _table_deployed(cur, "agent.agent_memory"):
        return (
            "WARN",
            "flag=1 but agent.agent_memory absent (V139 not applied) — pipeline cannot store",
        )
    cur.execute("SELECT count(*) FROM agent.agent_memory")
    total = int(cur.fetchone()[0])

    path = _cursor_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        last_success = date.fromisoformat(str(payload["last_success_utc_date"]))
    except FileNotFoundError:
        return (
            "WARN",
            f"flag=1 but cursor file missing ({path}) — cron 未成功跑過或 OPENCLAW_DATA_DIR 不一致",
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return ("WARN", f"flag=1 but cursor file unreadable: {exc}")

    lag_days = (_utc_today() - last_success).days
    msg = (
        f"rows={total} last_success={last_success.isoformat()} "
        f"lag_days={lag_days} (warn>{CURSOR_LAG_WARN_DAYS})"
    )
    if lag_days > CURSOR_LAG_WARN_DAYS:
        return ("WARN", msg + " — pipeline stalled, 查 l2_memory_distill_cron.log")
    # 語義死亡軸（游標健康 ≠ 記憶在累積；lag WARN 優先於本軸）。
    if _semantic_death_streak(path.parent / _STATS_FILENAME, last_success):
        return (
            "WARN",
            msg
            + f" — semantic death: 連續 {SEMANTIC_DEATH_CONSECUTIVE_DAYS} 個有"
            " l2_calls 材料的日子 stored=0（游標照推但記憶零累積），"
            "查 extraction/parser/dedup 鏈",
        )
    return ("PASS", msg)


def check_89_l2_memory_embedding_drift(cur: Any) -> tuple[str, str]:
    """[89] embedding meta vs config 漂移：backfill flag-OFF → PASS-skip。

    meta 行（agent.agent_memory_embedding_meta 單行表）記錄「已入庫 embedding
    由哪個 provider/model/dims 產生」；與當前 config 不符 = 新舊向量混在同一
    距離空間（語義檢索失真）→ WARN（backfill job 會全表重索引收斂，spec §7）。
    """
    _rollback_quietly(cur)
    if not _flag_on(BACKFILL_FLAG_ENV):
        return (
            "PASS",
            f"SKIP (flag off): {BACKFILL_FLAG_ENV} != 1 — embed backfill dormant",
        )
    if not _table_deployed(cur, "agent.agent_memory_embedding_meta"):
        return (
            "WARN",
            "flag=1 but agent.agent_memory_embedding_meta absent (V139 not applied)",
        )
    cur.execute(
        "SELECT provider, model, dims FROM agent.agent_memory_embedding_meta"
        " WHERE meta_id = 1"
    )
    row = cur.fetchone()
    if not row:
        # 首輪 backfill 前 meta 未初始化是合法過渡態（backfill 會 INSERT）。
        return ("PASS", "meta row not initialized yet (first backfill will create it)")
    provider, model, dims = str(row[0]), str(row[1]), int(row[2])
    expected_model = os.environ.get(EMBED_MODEL_ENV, "").strip() or DEFAULT_EMBED_MODEL
    if (provider, model, dims) != (
        EXPECTED_EMBED_PROVIDER,
        expected_model,
        EXPECTED_EMBED_DIMS,
    ):
        return (
            "WARN",
            f"drift: meta=({provider},{model},{dims}) "
            f"config=({EXPECTED_EMBED_PROVIDER},{expected_model},{EXPECTED_EMBED_DIMS})"
            " — backfill 將標記全表重索引",
        )
    return ("PASS", f"meta=({provider},{model},{dims}) matches config")
