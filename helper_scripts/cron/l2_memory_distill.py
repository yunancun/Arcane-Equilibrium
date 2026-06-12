#!/usr/bin/env python3
"""l2_memory_distill — L2 記憶蒸餾管線 daily cron CLI 殼。

MODULE_NOTE
模塊用途：
  L2 結構化記憶層（PA 2026-06-11 spec §6.1/§14）的 cron 進程入口殼。每日 05:23 UTC
  由 l2_memory_distill_cron.sh 喚起；負責 flag gate、游標狀態檔、psycopg2 連線與
  LLM client 注入，然後把每個待處理 UTC 日交給
  ``learning_engine.memory_distiller.pipeline.run_daily``（E1-A 線交付）。
主要函數：
  - pending_days(cursor_day, today)：純函數，計算處理窗（單測主體）。
  - read_cursor / write_cursor：游標狀態檔（atomic replace）。
  - append_day_stats：成功日 summary 環形檔（[88] 語義死亡軸資料源；fail-soft）。
  - main(argv)：入口；exit code 0=成功/inert、1=runtime 失敗、2=配置錯誤。
依賴：
  - 標準庫（flag-off 路徑零第三方依賴）；flag-on 才 lazy import psycopg2 /
    memory_distiller / local_llm_factory（G8 慣例：cron 進程 import app leaf 模組）。
硬邊界：
  - flag ``OPENCLAW_L2_MEMORY_PIPELINE`` 默認 0：**任何 import 重模組 / DB 連線之前**
    檢查，off ⇒ 一行 log + exit 0（零連線零副作用，spec §10 / E2 審查點 3）。
  - memory_distiller 未落地（兩線並行合流前）⇒ ImportError ⇒ log + exit 0
    （spec §14：兩線真並行、合流後自然接通）。
  - 游標「成功才推進」：失敗日停在上次成功日，下輪 cron 自動補跑（spec §6.1）。
  - 回看上限 7 日（防長期停擺後爆量，spec R5）；無游標（首跑）只補昨日
    （保守起步，避免首次 enable 即 7×2 次 LLM call 爆量——歷史回放歸 seed CLI）。
  - 純學習平面：本殼只讀 env / 寫游標檔；所有 DB 寫入在 pipeline 內
    （目標僅 agent.agent_memory，原則 7）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FLAG_ENV = "OPENCLAW_L2_MEMORY_PIPELINE"
CURSOR_REL_PATH = "cron_state/l2_memory_distill_cursor.json"
CURSOR_KEY = "last_success_utc_date"
LOOKBACK_CAP_DAYS = 7

# per-day summary（[88] 語義死亡軸的資料源，E2 LOW-3 / MIT F-4 修復輪）：
# 游標只證「跑過」，不證「有寫入」——[88] 需要逐日 stored/materials_l2 才能
# 看見「l2_calls 有料但連續 N 日 0 寫入」。bounded 環形（只留最近 N 條）。
STATS_REL_PATH = "cron_state/l2_memory_distill_day_stats.json"
STATS_MAX_ENTRIES = 14

EXIT_OK = 0
EXIT_RUNTIME_FAIL = 1
EXIT_CONFIG_ERROR = 2


def _log(msg: str) -> None:
    print(f"[l2_memory_distill] {msg}", flush=True)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _repo_root_from_file() -> Path:
    # helper_scripts/cron/l2_memory_distill.py → parents[2] = srv repo root（實測）。
    return Path(__file__).resolve().parents[2]


def _ensure_repo_imports(base_dir: Path) -> None:
    """讓 ``learning_engine.*`` 與 ``exchange_connectors.*`` 可 import（G8 慣例）。"""
    for path in (base_dir, base_dir / "program_code"):
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)


def read_cursor(path: Path) -> date | None:
    """讀游標檔；缺檔 / 壞 JSON / 壞日期一律回 None（WARN log，視同首跑）。

    為什麼不 raise：游標檔損壞不該讓 cron 永久卡死；回 None 走「只補昨日」
    保守路徑，成功後 write_cursor 自我修復。
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        _log(f"WARN: cursor 檔讀取失敗（視同首跑）：{exc}")
        return None
    try:
        payload = json.loads(raw)
        return date.fromisoformat(str(payload[CURSOR_KEY]))
    except (ValueError, KeyError, TypeError) as exc:
        _log(f"WARN: cursor 檔內容無效（視同首跑）：{exc}")
        return None


def write_cursor(path: Path, day: date) -> None:
    """atomic 寫游標（temp file + os.replace），避免半寫檔毒化下輪解析。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({CURSOR_KEY: day.isoformat()})
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".cursor_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _day_stats_entry(day: date, stats: Any) -> dict[str, Any]:
    """run_daily 回傳 → [88] 語義死亡軸所需最小欄位（防禦性取值，缺=0）。"""
    result: dict[str, Any] = {}
    if isinstance(stats, dict):
        day_results = stats.get("day_results")
        if isinstance(day_results, list) and day_results and isinstance(day_results[0], dict):
            result = day_results[0]

    def _as_int(key: str) -> int:
        try:
            return int(result.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "utc_date": day.isoformat(),
        "stored": _as_int("stored"),
        "materials_l2": _as_int("materials_l2"),
        "dropped": _as_int("dropped"),
    }


def append_day_stats(path: Path, entry: dict[str, Any]) -> None:
    """成功日 summary 追加（bounded 環形 + atomic replace + fail-soft）。

    為什麼 fail-soft 不拋：這是觀測軸（[88] 讀），不是游標紀律載體——觀測
    寫入失敗不得反殺管線本體/汙染 exit code；壞檔直接重建（觀測資料可丟，
    游標檔才是補跑紀律的唯一憑據）。
    """
    try:
        days: list[dict[str, Any]] = []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("days"), list):
                days = [d for d in payload["days"] if isinstance(d, dict)]
        except (FileNotFoundError, OSError, ValueError):
            days = []
        days.append(entry)
        days = days[-STATS_MAX_ENTRIES:]
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".stats_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"days": days}, ensure_ascii=False))
            os.replace(tmp_name, str(path))
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001 - 觀測寫入失敗不影響游標/exit code
        _log(f"WARN: day stats 寫入失敗（不影響游標紀律）：{exc}")


def pending_days(cursor_day: date | None, today: date) -> list[date]:
    """處理窗 = (cursor+1 日)..(昨日)，上限回看 7 日；無游標（首跑）只補昨日。

    純函數：窗口數學零 IO，可直接單測（spec §6.1）。
    """
    yesterday = today - timedelta(days=1)
    if cursor_day is None:
        start = yesterday
    else:
        start = cursor_day + timedelta(days=1)
    floor = yesterday - timedelta(days=LOOKBACK_CAP_DAYS - 1)
    if start < floor:
        start = floor
    if start > yesterday:
        return []
    return [start + timedelta(days=i) for i in range((yesterday - start).days + 1)]


def _load_pipeline() -> Any:
    """string import E1-A 的 pipeline 模組；ImportError 由 caller 處理（exit 0）。"""
    import importlib

    return importlib.import_module("learning_engine.memory_distiller.pipeline")


def _resolve_llm() -> Any:
    """經既有工廠取本地 LLM client（G7：Ollama qwen3.5:9b 單例，cost_usd=0）。"""
    from exchange_connectors.bybit_connector.control_api_v1.app.local_llm_factory import (
        get_local_llm_client,
    )

    return get_local_llm_client(heavy=False)


def _connect_db() -> Any:
    """psycopg2 連線：POSTGRES_* env（wrapper grep-parse 注入）。

    為什麼 fail-closed 回 None：缺憑證時絕不 fallback 其他隱式 DSN；
    caller 以 EXIT_CONFIG_ERROR 結束，wrapper log 可見。
    """
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    dbname = os.environ.get("POSTGRES_DB", "").strip()
    host = os.environ.get("POSTGRES_HOST", "").strip() or "127.0.0.1"
    port = os.environ.get("POSTGRES_PORT", "").strip() or "5432"
    if not (user and password and dbname):
        return None
    import psycopg2

    return psycopg2.connect(
        host=host, port=int(port), dbname=dbname, user=user, password=password
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="L2 記憶蒸餾 daily cron 殼（flag-OFF 默認 inert）。"
    )
    parser.add_argument(
        "--base-dir",
        default=None,
        help="repo root 覆蓋（默認由本檔路徑推算；cron wrapper 顯式傳入）。",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="資料目錄覆蓋（默認 env OPENCLAW_DATA_DIR，再退 /tmp/openclaw）。",
    )
    args = parser.parse_args(argv)

    # ── flag gate：必須先於任何重 import / DB 連線（spec §10、E2 審查點 3）──
    if os.environ.get(FLAG_ENV, "0").strip() != "1":
        _log(f"flag {FLAG_ENV} != 1 — pipeline inert（log-only），exit 0")
        return EXIT_OK

    base_dir = Path(args.base_dir).resolve() if args.base_dir else _repo_root_from_file()
    data_dir = Path(
        args.data_dir or os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    )
    cursor_path = data_dir / CURSOR_REL_PATH

    _ensure_repo_imports(base_dir)

    # ── E1-A 模組可用性：未落地 = 合法狀態（兩線並行），log + exit 0 ──
    try:
        pipeline = _load_pipeline()
    except ImportError as exc:
        _log(f"memory_distiller 模組未落地（兩線合流前合法狀態）：{exc} — exit 0")
        return EXIT_OK

    cursor_day = read_cursor(cursor_path)
    days = pending_days(cursor_day, _utc_today())
    if not days:
        _log(f"cursor={cursor_day} 已最新，無待處理日 — exit 0")
        return EXIT_OK
    _log(f"cursor={cursor_day} 待處理 {len(days)} 日：{days[0]}..{days[-1]}")

    conn = _connect_db()
    if conn is None:
        _log("ERROR: POSTGRES_USER/PASSWORD/DB 憑證不完整 — 不嘗試任何隱式 DSN，exit 2")
        return EXIT_CONFIG_ERROR

    try:
        try:
            llm = _resolve_llm()
        except Exception as exc:  # noqa: BLE001 - 工廠失敗即 runtime 故障，不吞細節
            _log(f"ERROR: 本地 LLM client 解析失敗：{exc}")
            return EXIT_RUNTIME_FAIL

        # 逐日處理：成功立即推進游標（部分成功也保住進度）；失敗即停，
        # 失敗日下輪 cron 自動補跑（spec §6.1「成功才推進 cursor」）。
        for day in days:
            try:
                stats = pipeline.run_daily(conn, llm, target_date=day)
            except TypeError as exc:
                # 兩線並行合流接縫：spec §4 接口 = run_daily(conn, llm, *, target_date)。
                # TypeError 最可能是簽名不匹配——log 明示供合流時一行修正。
                _log(
                    "ERROR: run_daily 呼叫 TypeError（疑兩線接口簽名不匹配，"
                    f"spec §4 約定 run_daily(conn, llm, *, target_date)）：{exc}"
                )
                return EXIT_RUNTIME_FAIL
            except Exception as exc:  # noqa: BLE001 - 單日失敗停輪，cursor 停在上次成功
                _log(f"ERROR: run_daily({day.isoformat()}) 失敗：{exc} — 游標不推進，下輪補跑")
                return EXIT_RUNTIME_FAIL
            write_cursor(cursor_path, day)
            # 成功日 summary（[88] 語義死亡軸資料源；fail-soft 在函數內）。
            append_day_stats(data_dir / STATS_REL_PATH, _day_stats_entry(day, stats))
            try:
                stats_text = json.dumps(stats, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                stats_text = repr(stats)
            _log(f"day={day.isoformat()} OK stats={stats_text}")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - close 失敗不影響 exit code 語意
            pass

    _log("all pending days done")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
