#!/usr/bin/env python3
"""Gate-B 隔離探針 — artifact 落地 / manifest / provenance / parquet 鏡像 / verdict。

MODULE_NOTE:
  模塊用途：Gate-B isolated listing-capture 探針的「封裝與裁決」層。負責：
    (1) 在跨平台 artifact root 建立單次 run 目錄並提供各 channel 的 JSONL writer；
    (2) 收尾時寫 manifest.json（含 point_in_time=true + provenance 規格 + 隔離聲明）；
    (3) 用 duckdb 把 JSONL 鏡像成 parquet + 產 topic_summary.csv（缺套件則 skip，
        不阻斷主流程）；(4) 彙總 phase_transition_summary.json 與 verdict.json，
        verdict 必含 ``INCONCLUSIVE_NO_TRANSITION``（無事件非 fail）。
  主要類/函數：
    - ``resolve_artifact_root`` / ``GateBArtifactWriter`` — 跨平台路徑 + JSONL writer。
    - ``build_phase_transition_summary`` / ``build_verdict`` — 純函數裁決邏輯。
    - ``mirror_jsonl_to_parquet`` — duckdb 鏡像（可選，缺套件 skip）。
  依賴：``duckdb`` + ``pyarrow``（Linux runtime 已驗；Mac dev 無，故延遲 import，
    缺套件時 parquet 鏡像 skip 並在 manifest 記 ``parquet_mirror=skipped``）。
    其餘為 Python 標準庫。
  硬邊界（R-0 隔離紅線）：
    - 絕不 import 任何生產模組。零 auth / 零 order / 零 DB write（duckdb 只寫本地
      parquet 檔，非生產 PG）。
    - **artifact root 禁硬編碼 /tmp/openclaw**（跨平台原則 feedback_cross_platform）：
      root = ``${OPENCLAW_DATA_DIR:-/tmp/openclaw}/aeg_gate_b_runs/<run_id>/``。
    - verdict 必含 INCONCLUSIVE_NO_TRANSITION：phase transition 稀有，無轉移是
      預期可能結果，不可當成 fail（會誤導後續決策）。
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# verdict 枚舉（封閉集合）。為什麼 INCONCLUSIVE 是一等公民：listing phase 轉移稀有，
# 24h 窗常常零轉移；那是「沒樣本」不是「捕捉失敗」，必須與真正的 fail 區分。
VERDICT_PASS_CAPTURE = "PASS_CAPTURE"
VERDICT_SLOW_CAPTURE = "SLOW_CAPTURE"
VERDICT_INCONCLUSIVE_NO_TRANSITION = "INCONCLUSIVE_NO_TRANSITION"
VERDICT_PIPELINE_ERROR = "PIPELINE_ERROR"
# FIX-2：發生了 phase 轉移，但**至少一個**轉移到 Trading 的 symbol 沒抓到有效首成交時間
# （capture_lag_ms 為 None / 該 symbol 無 capture block）。涵蓋兩種失敗：
#   (a) total-miss：全部轉移 symbol 都沒抓到（capture 全空 / 全 None）；
#   (b) partial-miss：部分轉移 symbol 抓到、部分沒抓到（FIX-2 re-E2 邊界）。
# 為什麼必須與 PASS_CAPTURE 嚴格區分：這恰是 Gate-B 唯一要 catch 的核心失敗——
# 轉移已發生卻有 symbol 0 capture，代表 WS 對該 symbol 沒收到首筆成交（漏訂閱 /
# handler-not-found 毒化 / 連線斷），是「捕捉失敗」非「捕捉成功」。先前邏輯只在
# 「capture 全空」時才標此 verdict，partial-miss（有 symbol 抓到就 falls through）會把
# 沒抓到的 symbol 當「不慢」靜默吞 → 誤報 PASS_CAPTURE，遮蔽真失敗。
VERDICT_TRANSITION_BUT_NO_CAPTURE = "TRANSITION_BUT_NO_CAPTURE"

# capture_lag PASS 閾值（毫秒），與 gate_b_ws._CAPTURE_LAG_PASS_MS 對齊。
_CAPTURE_LAG_PASS_MS = 5 * 60 * 1000

# artifact 各 channel → 檔名。
_CHANNEL_FILES = {
    "rest": "rest_phase_poll.jsonl",
    "kline": "ws_kline.jsonl",
    "publictrade": "ws_publictrade.jsonl",
    "control": "ws_control.jsonl",
    "capture_lag": "capture_lag.jsonl",
    "markout": "markout.jsonl",
}


def resolve_artifact_root() -> Path:
    """解析 artifact 根目錄（跨平台，禁硬編碼）。

    為什麼用 OPENCLAW_DATA_DIR：feedback_cross_platform.md / R-1 修正——不可把
    ``/tmp/openclaw`` 寫死進程式（Mac 與 Linux 資料目錄不同，且 operator 可改）。
    預設 fallback ``/tmp/openclaw`` 僅在 env 未設時生效。
    """
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "aeg_gate_b_runs"


class GateBArtifactWriter:
    """單次 run 的 artifact 目錄管理 + 各 channel JSONL writer。

    每個 channel 對應一個 append-only JSONL 檔；writer 以行為單位 flush，確保
    探針中途被中斷也保留已收事件（探針短窗運行，不追求高吞吐）。
    """

    def __init__(
        self,
        run_id: str,
        *,
        artifact_root: Optional[Path] = None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.run_id = run_id
        self._clock_ms = clock_ms
        root = artifact_root if artifact_root is not None else resolve_artifact_root()
        self.run_dir = Path(root) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, Any] = {}
        self._counts: dict[str, int] = {ch: 0 for ch in _CHANNEL_FILES}

    def writer_for(self, channel: str) -> Callable[[dict[str, Any]], None]:
        """回傳某 channel 的 JSONL 寫入回呼（lazy 開檔，逐行 flush）。"""
        if channel not in _CHANNEL_FILES:
            raise ValueError(f"unknown_artifact_channel:{channel}")

        def _write(row: dict[str, Any]) -> None:
            fh = self._files.get(channel)
            if fh is None:
                fh = open(self.run_dir / _CHANNEL_FILES[channel], "a", encoding="utf-8")
                self._files[channel] = fh
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            self._counts[channel] += 1

        return _write

    def writers(self) -> dict[str, Callable[[dict[str, Any]], None]]:
        """回傳 WS 層需要的 channel→writer 映射（kline/publictrade/control/...）。"""
        return {ch: self.writer_for(ch) for ch in _CHANNEL_FILES if ch != "rest"}

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def close(self) -> None:
        for fh in self._files.values():
            try:
                fh.close()
            except OSError:
                # 收尾關檔失敗不影響已 flush 的內容，吞掉避免遮蔽主流程結論。
                pass
        self._files.clear()

    def path_of(self, channel: str) -> Path:
        return self.run_dir / _CHANNEL_FILES[channel]

    def write_manifest(self, extra: dict[str, Any]) -> Path:
        """寫 manifest.json：隔離聲明 + provenance 規格 + point_in_time + 計數。"""
        manifest = {
            "probe": "aeg_gate_b_isolated_listing_capture",
            "run_id": self.run_id,
            "created_ts_local_ms": self._clock_ms(),
            # point_in_time=true：所有 row 帶 event_ts_exchange_ms，研究只用事件時間
            # 排序，無 look-ahead；ingest_ts_local 僅供 clock-skew 診斷。
            "point_in_time": True,
            "provenance": {
                "event_time_field": "event_ts_exchange_ms",
                "ingest_time_field": "ingest_ts_local_ms",
                "skew_field": "ingest_minus_event_ms",
                "ordering_rule": "research_must_sort_by_event_ts_exchange_only",
            },
            "isolation": {
                "standalone_process": True,
                "imports_production_modules": False,
                "auth_used": False,
                "orders_placed": False,
                "db_writes": False,
                "endpoints_allowlisted": True,
            },
            "channels": dict(_CHANNEL_FILES),
            "counts": self.counts(),
        }
        manifest.update(extra)
        path = self.run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def build_phase_transition_summary(
    transitions: list[dict[str, Any]],
    capture_lags: list[dict[str, Any]],
) -> dict[str, Any]:
    """彙總 phase 轉移 + 每 symbol capture_lag（純函數，供 verdict 與落地共用）。"""
    by_symbol: dict[str, dict[str, Any]] = {}
    for t in transitions:
        sym = t.get("symbol")
        if not sym:
            continue
        by_symbol.setdefault(sym, {})["transition"] = {
            "prev_status": t.get("prev_status"),
            "new_status": t.get("new_status"),
            "launch_time_ms": t.get("launch_time_ms"),
            "detected_ingest_ts_ms": t.get("detected_ingest_ts_ms"),
        }
    for c in capture_lags:
        sym = c.get("symbol")
        if not sym:
            continue
        by_symbol.setdefault(sym, {})["capture_lag"] = {
            "launch_time_ms": c.get("launch_time_ms"),
            "first_trade_event_ts_ms": c.get("first_trade_event_ts_ms"),
            "capture_lag_ms": c.get("capture_lag_ms"),
            "verdict": c.get("verdict"),
        }
    return {
        "transition_count": len(transitions),
        "symbols_with_capture_lag": len([1 for c in capture_lags if c.get("capture_lag_ms") is not None]),
        "per_symbol": by_symbol,
    }


def build_verdict(
    summary: dict[str, Any],
    control_liveness: dict[str, Any],
    *,
    pipeline_error: Optional[str] = None,
) -> dict[str, Any]:
    """產 verdict.json 內容（純函數）。

    裁決規則（順序敏感）：
      - pipeline_error 非空 → PIPELINE_ERROR（探針本身出錯，需重跑）。
      - transition_count == 0 → INCONCLUSIVE_NO_TRANSITION（無事件，非 fail）。
      - 有轉移但「轉移 symbol 集 ⊄ 有效 capture symbol 集」（即任一轉移到 Trading 的
        symbol 沒抓到有效首成交時間）→ TRANSITION_BUT_NO_CAPTURE
        （FIX-2：涵蓋 total-miss 與 partial-miss，皆為管線捕捉失敗，絕不可 PASS_CAPTURE）。
      - 全部轉移 symbol 皆抓到、但任一 capture_lag > 5min → SLOW_CAPTURE（捕捉到但偏慢）。
      - 全部轉移 symbol 皆抓到且皆 ≤ 5min → PASS_CAPTURE。
    control_liveness.poisoned_suspect 不改 capture verdict，但會在 verdict 標記
    隔離健康警示（供人判斷該次資料是否可信）。
    """
    transition_count = int(summary.get("transition_count", 0))
    per_symbol = summary.get("per_symbol", {})

    # 計數語義（已讀碼確認，gate_b_rest.PhaseStateMachine.observe / gate_b_ws
    # ._maybe_record_capture_lag）：每個 symbol 最多一筆轉移（observe 觸發後將
    # _last_status 設為 Trading，下輪不再觸發）、每個 symbol 最多一筆 capture_lag
    # （_maybe_record_capture_lag 對 _first_trade_ts 去重）。故 per_symbol 的 key 即
    # distinct symbol，可做集合完備性檢查。
    # 為什麼用集合檢查而非聚合計數 `symbols_with_capture_lag < transition_count`：
    #   (1) 語義最精確——直接表達「每個轉移到 Trading 的 symbol 都必須有有效 capture」；
    #   (2) fail-closed 更穩健——萬一某 symbol 異常重複轉移致 transition_count inflate，
    #       純計數比較仍會偏向標記（symbols_with_capture_lag < transition_count 更易成立，
    #       方向 fail-closed-safe），但集合檢查根本不受重複計數干擾，直接看「是否存在
    #       轉移 symbol 沒抓到」。安全方向：寧過度標記（operator 多查一次，無害），不可假
    #       PASS（operator 誤信管線就緒，有害）。
    transition_symbols = {
        sym for sym, blk in per_symbol.items() if blk.get("transition") is not None
    }
    captured_symbols = {
        sym
        for sym, blk in per_symbol.items()
        if (blk.get("capture_lag") or {}).get("capture_lag_ms") is not None
    }

    # 防 transition_count>0 但 per_symbol 無可歸因轉移 symbol 的異常（transition row
    # 缺 symbol，build_phase_transition_summary 會跳過不入 per_symbol）：此時無從證明
    # 任何轉移有抓到首成交，fail-closed 視為未完備（不得 falls through 成 PASS）。
    all_transitions_captured = (
        bool(transition_symbols) and transition_symbols.issubset(captured_symbols)
    )

    if pipeline_error:
        capture_verdict = VERDICT_PIPELINE_ERROR
    elif transition_count == 0:
        capture_verdict = VERDICT_INCONCLUSIVE_NO_TRANSITION
    elif not all_transitions_captured:
        # 至少一個轉移到 Trading 的 symbol 沒抓到有效首成交（total-miss 或 partial-miss），
        # 或轉移資料缺 symbol 無從歸因。fail-closed：這是 Gate-B 核心要 catch 的失敗，
        # 不得降級成 PASS。涵蓋先前漏徑——「3 轉移、僅 1 symbol 抓到」會 falls through 把
        # 缺 capture 的 2 symbol 當「不慢」靜默吞而誤報 PASS_CAPTURE。
        capture_verdict = VERDICT_TRANSITION_BUT_NO_CAPTURE
    else:
        worst_slow = False
        for _sym, blk in per_symbol.items():
            cl = blk.get("capture_lag") or {}
            lag = cl.get("capture_lag_ms")
            if lag is not None and lag > _CAPTURE_LAG_PASS_MS:
                worst_slow = True
        capture_verdict = VERDICT_SLOW_CAPTURE if worst_slow else VERDICT_PASS_CAPTURE

    return {
        "capture_verdict": capture_verdict,
        "transition_count": transition_count,
        "capture_lag_pass_threshold_ms": _CAPTURE_LAG_PASS_MS,
        "control_liveness": control_liveness,
        "isolation_health_warning": bool(control_liveness.get("poisoned_suspect")),
        "pipeline_error": pipeline_error,
        # 誠實標註：捕捉管線就緒 ≠ alpha 定論；capture_lag/alpha 結論需 ~Q4 樣本。
        "note": (
            "capture pipeline readiness only; capture_lag/alpha conclusions require "
            "~Q4 sample of real listing transitions"
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def mirror_jsonl_to_parquet(run_dir: Path) -> dict[str, Any]:
    """用 duckdb 把各 JSONL 鏡像成 parquet + 產 topic_summary.csv/parquet。

    為什麼可選 skip：duckdb/pyarrow 在 Mac dev 不一定裝；缺套件時回 skipped，不阻斷
    主流程（JSONL 才是 SoT，parquet 只是研究便利鏡像）。延遲 import 維持 import-time
    無重依賴。

    非阻斷契約（硬邊界）：parquet 鏡像是研究便利層，JSONL 才是 SoT。**任何**失敗
    （缺套件 / duckdb IO 錯 / 壞 JSONL / 不可寫路徑）都必須被吞並以結構化結果回報，
    絕不 raise——否則 24h run 收尾會在 ``_finalize`` 崩潰退非零（verdict 雖已先寫，
    但探針進程整體 traceback 退出）。單一 channel 轉換失敗也不得連累其他 channel 或
    verdict：逐 channel 隔離，失敗者記入 ``channels_failed``，成功者照常產出。
    回報語義：``ok``=全部成功；``partial``=至少一 channel 失敗但有成功；
    ``failed``=全部失敗或鏡像層級失敗（如連線建立失敗）。
    """
    try:
        import duckdb  # 延遲 import；Linux runtime 已驗可用。
    except ImportError:
        return {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}

    # 整個鏡像層級的保護：連線建立、csv 落地、topic_summary 等任一環節若拋例外，
    # 都收斂成 failed 回報而非傳播（Part A 非阻斷紅線）。
    try:
        summary_rows: list[tuple[str, int]] = []
        channels_ok: list[str] = []
        channels_failed: list[str] = []
        # 為什麼用 read_json().write_parquet() 關聯式 API 而非 COPY (...) TO ?：
        # duckdb 的 ``COPY (...) TO ?`` 對 TO 目標**不支援 ? bind 參數**（會把 ?
        # 當字面 glob 路徑解析 → 比對不到任何檔 → IOException "No files found"），
        # 且 read_json_auto(?) 的 input 參數化亦同病。關聯式 API 以 Python str 直接
        # 傳路徑，避開 COPY-TO-param 限制（Linux duckdb 1.5.1 / Mac 1.5.3 皆驗）。
        con = duckdb.connect(database=":memory:")
        try:
            for channel, fname in _CHANNEL_FILES.items():
                jsonl_path = run_dir / fname
                if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
                    summary_rows.append((channel, 0))
                    channels_ok.append(channel)
                    continue
                parquet_path = run_dir / f"{channel}.parquet"
                try:
                    rel = con.read_json(str(jsonl_path))
                    rel.write_parquet(str(parquet_path))
                    cnt = con.read_json(str(jsonl_path)).count("*").fetchone()
                    summary_rows.append((channel, int(cnt[0]) if cnt else 0))
                    channels_ok.append(channel)
                except (duckdb.Error, OSError, ValueError) as exc:
                    # 單 channel 失敗（壞 JSONL / schema 推斷失敗 / 寫檔失敗）：隔離記錄，
                    # 不連累其他 channel 與 verdict。row_count 記 0 佔位，summary 仍完整。
                    summary_rows.append((channel, 0))
                    channels_failed.append(channel)
        finally:
            con.close()

        # topic_summary.csv + parquet。csv 始終寫（純標準庫），parquet 為便利鏡像。
        csv_path = run_dir / "topic_summary.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["channel", "row_count"])
            for ch, cnt in summary_rows:
                writer.writerow([ch, cnt])

        # 同時輸出 parquet 版 topic_summary。read_csv_auto 同樣改關聯式 read_csv。
        topic_summary_ok = True
        try:
            con2 = duckdb.connect(database=":memory:")
            try:
                con2.read_csv(str(csv_path)).write_parquet(
                    str(run_dir / "topic_summary.parquet")
                )
            finally:
                con2.close()
        except (duckdb.Error, OSError, ValueError) as exc:
            topic_summary_ok = False
            logger.warning("gate_b topic_summary parquet 鏡像失敗: %s", exc)

        if channels_failed or not topic_summary_ok:
            return {
                "parquet_mirror": "partial",
                "reason": (
                    "topic_summary_parquet_failed"
                    if not topic_summary_ok and not channels_failed
                    else "channel_mirror_failed"
                ),
                "channels_ok": channels_ok,
                "channels_failed": channels_failed,
                "topic_summary_ok": topic_summary_ok,
                "channels": {ch: cnt for ch, cnt in summary_rows},
            }
        return {
            "parquet_mirror": "ok",
            "channels_ok": channels_ok,
            "channels_failed": channels_failed,
            "channels": {ch: cnt for ch, cnt in summary_rows},
        }
    except Exception as exc:  # noqa: BLE001 - 鏡像層級失敗不阻斷主流程（JSONL 才是 SoT）
        # 連線建立或其他未預期錯誤：fail-safe 回報 failed，絕不傳播給 _finalize。
        logger.warning("gate_b parquet 鏡像整體失敗（不阻斷，JSONL 為 SoT）: %s", exc)
        return {"parquet_mirror": "failed", "reason": f"mirror_failed:{exc}"}


__all__ = [
    "VERDICT_PASS_CAPTURE",
    "VERDICT_SLOW_CAPTURE",
    "VERDICT_INCONCLUSIVE_NO_TRANSITION",
    "VERDICT_PIPELINE_ERROR",
    "VERDICT_TRANSITION_BUT_NO_CAPTURE",
    "resolve_artifact_root",
    "GateBArtifactWriter",
    "build_phase_transition_summary",
    "build_verdict",
    "write_json",
    "mirror_jsonl_to_parquet",
]
