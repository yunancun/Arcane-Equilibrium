"""Polymarket 軸 track-to-resolution 登記簿。

MODULE_NOTE:
  模塊用途：持久化「已見過的 market」集合，使 closed market 仍續抓至 resolution
    （QC memo §2 鐵則：lib 原版 skip closed 是搜索 UX；採集器必須反向，否則
    calibration / 事後研究帶 survivorship bias——H4 假說的 resolved 樣本全靠此）。
  主要類/函數：TrackerState（in-memory 登記）、load_state / save_state（原子持久化）。
  存放位置：${data_root}/polymarket_axis_state/tracked_markets.json——刻意與
    append-only 的 run dir 分離：run dir 禁覆寫，登記簿是可變狀態，混放會破
    append-only 不變量。
  依賴：僅標準庫。零生產模組 import、零 PG。
  硬邊界：
    - resolved / lost 終態條目保留不刪（resolved 條目 = H4 calibration 樣本索引；
      條目數受真實 market 數有界，非無界增長）。
    - 連續 follow-up 失敗達上限 → status="lost"（停止追抓）：否則已下架 / 404 的
      market id 會讓每日 follow-up 請求數無界累積（latent unbounded 教訓）。
    - 持久化必走 tmp + os.replace 原子替換：採集中途 crash 不可留半寫狀態檔。
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Optional

from . import STATE_SCHEMA_VERSION

# 終態與追蹤態枚舉（封閉集合）。
STATUS_TRACKING = "tracking"
STATUS_RESOLVED = "resolved"
STATUS_LOST = "lost"
# P-2（E2 2026-06-11）：counts() 的披露桶（非真實狀態）——load_state fail-soft 接受
# 任意 dict entry，缺/壞 status 的條目歸此桶，單壞條目不毀整輪也不靜默消失。
STATUS_UNKNOWN = "unknown"

# 連續 follow-up 失敗多少次後標 lost（daily cadence 下 ≈ 30 天）。
# 為什麼 30：Gamma 偶發 5xx / 單日空回應不應放棄追蹤（resolution 樣本珍貴），
# 但 30 天連續抓不到基本確定該 id 已不可達，繼續請求只是無界浪費。
LOST_AFTER_CONSECUTIVE_ERRORS = 30


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resolve_state_path(data_root: Path) -> Path:
    return Path(data_root) / "polymarket_axis_state" / "tracked_markets.json"


def _is_market_resolved(market: dict[str, Any]) -> bool:
    """判定 market 是否已達 resolution 終態。

    判據（2026-06-11 真實 API probe 驗證）：closed=True 且
    umaResolutionStatus == "resolved"。只看 closed 不夠——closed 但 UMA 仲裁
    未完的 market 賠率仍可能變動，提前終止會漏掉最終結算值。
    """
    if not market.get("closed", False):
        return False
    return str(market.get("umaResolutionStatus") or "").lower() == "resolved"


class TrackerState:
    """tracked market 登記簿（dict[market_id] -> entry）。

    不變量：entry 一旦進入 STATUS_RESOLVED / STATUS_LOST 終態即不再變動
    （record_seen 對終態條目只更新 last_seen_utc，不回退 status——resolution
    結果是 point-in-time 事實，回退 = 汙染 calibration 樣本）。
    """

    def __init__(self, entries: Optional[dict[str, dict[str, Any]]] = None) -> None:
        self.entries: dict[str, dict[str, Any]] = dict(entries or {})

    # ---- 觀測寫入 ----

    def record_seen(self, market: dict[str, Any], event_id: str, seen_at_utc: Optional[str] = None) -> None:
        """登記一次 market 觀測（enumeration / search / follow-up 共用單一路徑）。"""
        market_id = str(market.get("id") or "").strip()
        if not market_id:
            return
        now = seen_at_utc or _utc_now_iso()
        entry = self.entries.get(market_id)
        if entry is None:
            entry = {
                "market_id": market_id,
                "event_id": str(event_id or ""),
                "question": str(market.get("question") or ""),
                "clob_token_ids": _parse_clob_token_ids(market),
                "first_seen_utc": now,
                "last_seen_utc": now,
                "status": STATUS_TRACKING,
                "consecutive_fetch_errors": 0,
                "resolved_at_utc": None,
                "resolution_outcome_prices": None,
                "resolution_uma_status": None,
                "closed_time": None,
            }
            self.entries[market_id] = entry
        entry["last_seen_utc"] = now
        entry["consecutive_fetch_errors"] = 0
        # token ids 可能首見時缺、後續補齊（schema 漂移 fail-soft）。
        if not entry.get("clob_token_ids"):
            entry["clob_token_ids"] = _parse_clob_token_ids(market)
        # P-2：.get 容錯——load_state fail-soft 可載入缺 status 鍵的壞 entry，下標
        # KeyError 會毀整輪 sweep（連 snapshot 全丟）；缺 status 視同非 tracking（凍結）。
        if entry.get("status") != STATUS_TRACKING:
            return  # 終態/unknown 不回退（見類 docstring 不變量）。
        if _is_market_resolved(market):
            entry["status"] = STATUS_RESOLVED
            entry["resolved_at_utc"] = now
            entry["resolution_outcome_prices"] = market.get("outcomePrices")
            entry["resolution_uma_status"] = market.get("umaResolutionStatus")
            entry["closed_time"] = market.get("closedTime")

    def record_fetch_error(self, market_id: str) -> None:
        """follow-up 抓取失敗計數；連續達上限 → lost（停止追抓，防無界請求）。"""
        entry = self.entries.get(str(market_id))
        # P-2：.get 容錯（同 record_seen——缺 status 的壞 entry 不得 KeyError 毀整輪）。
        if entry is None or entry.get("status") != STATUS_TRACKING:
            return
        entry["consecutive_fetch_errors"] = int(entry.get("consecutive_fetch_errors") or 0) + 1
        if entry["consecutive_fetch_errors"] >= LOST_AFTER_CONSECUTIVE_ERRORS:
            entry["status"] = STATUS_LOST

    # ---- 讀面 ----

    def follow_up_ids(self, seen_this_run: set[str]) -> list[str]:
        """本輪 sweep 沒見到、且仍在追蹤中的 market id（需逐一 follow-up 抓取）。

        為什麼排除 seen_this_run：本輪枚舉已拿到其現值（同一 run 重抓 = 浪費 +
        同 snapshot 雙行）；為什麼只取 STATUS_TRACKING：resolved / lost 是終態。
        """
        return sorted(
            mid for mid, e in self.entries.items()
            if e.get("status") == STATUS_TRACKING and mid not in seen_this_run
        )

    def counts(self) -> dict[str, int]:
        """三態計數 + unknown 披露桶（P-2：壞 entry 流進 manifest stats.tracker_counts 可見）。"""
        out = {STATUS_TRACKING: 0, STATUS_RESOLVED: 0, STATUS_LOST: 0, STATUS_UNKNOWN: 0}
        for e in self.entries.values():
            status = str(e.get("status") or "")
            out[status if status in out else STATUS_UNKNOWN] += 1
        return out


def _parse_clob_token_ids(market: dict[str, Any]) -> list[str]:
    """clobTokenIds 是 JSON-encoded 字串（真實 API probe 驗證），fail-soft 解析。"""
    raw = market.get("clobTokenIds")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(t) for t in parsed]


def load_state(path: Path) -> TrackerState:
    """讀登記簿；檔案缺失 = 全新開始；壞檔 fail-soft 回空（並由 caller 決定是否告警）。

    為什麼壞檔不 raise：登記簿丟失的代價 = 漏 follow-up（資料少抓），但 raise 會
    讓整輪 daily sweep 全滅（連 enumeration snapshot 都丟）——snapshot 丟一天少
    一天（QC memo §2），兩害取其輕。
    """
    p = Path(path)
    if not p.exists():
        return TrackerState()
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            return TrackerState()
        return TrackerState({str(k): dict(v) for k, v in entries.items() if isinstance(v, dict)})
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return TrackerState()


def save_state(state: TrackerState, path: Path) -> None:
    """原子持久化（tmp + os.replace）：crash 不留半寫檔。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": STATE_SCHEMA_VERSION,
        "updated_at_utc": _utc_now_iso(),
        "entries": state.entries,
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, p)
