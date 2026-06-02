#!/usr/bin/env python3
"""Gate-B 隔離探針 — REST instruments-info 輪詢 + PreLaunch phase 狀態機。

MODULE_NOTE:
  模塊用途：Gate-B isolated listing-capture 探針的「真實來源（SoT）」層。以
    純 urllib（仿 replay/bybit_public_client.py 隔離模式，但不 import 它）輪詢
    Bybit live REST ``GET /v5/market/instruments-info?category=linear&status=PreLaunch``，
    追蹤每個 PreLaunch symbol 的 phase 轉移（PreLaunch → Trading），把每次輪詢
    與每次 phase 轉移落地成 rest_phase_poll.jsonl，並回報「哪些 symbol 需要被
    WS 動態訂閱」。
  主要類/函數：
    - ``InstrumentsInfoPoller`` — urllib + endpoint allowlist，無 auth/無簽名。
    - ``PhaseStateMachine`` — 純記憶體 phase 狀態機，偵測 PreLaunch→Trading 轉移。
    - ``GateBRestProbe`` — 組裝輪詢 + 狀態機 + JSONL 落地，產出候選 symbol 集合。
  依賴：僅 Python 標準庫（urllib / json / time / dataclasses）。**零** 生產模組、
    零 SymbolRegistry、零 KlineManager、零 auth、零 order、零 DB。
  硬邊界（R-0 隔離紅線）：
    - 絕不 import openclaw_engine / SymbolRegistry / KlineManager / governance_hub /
      production bybit_rest_client / scanner / strategy / intent / decision_lease。
    - 只打 public market endpoint（instruments-info），endpoint allowlist 強制，
      不簽名、不帶 API key、不下單、不寫 DB。
    - 為什麼用 live REST 而非 symbol_universe_snapshots：snapshot 的 ``listed_at``
      是過去（已上市時刻），無法提供「未來 launchTime / 當前 auction phase」這個
      Gate-B 需要的前瞻訊號。SoT 必須是 live instruments-info 的 PreLaunch 視圖。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── 隔離常量（自帶 base / endpoint allowlist，不從生產 client 取） ──
_BYBIT_PUBLIC_BASE_URL = "https://api.bybit.com"
_INSTRUMENTS_INFO_ENDPOINT = "/v5/market/instruments-info"
# 為什麼 allowlist：與 replay/bybit_public_client.py 同一防呆——本探針只允許打這
# 一個 public 端點，任何其他 endpoint 直接 raise，杜絕誤觸生產/簽名路徑。
_ALLOWED_ENDPOINTS = {_INSTRUMENTS_INFO_ENDPOINT}
_RETRIABLE_HTTP_CODES = {429, 500, 502, 503, 504}
# Bybit 限流 / 系統繁忙類 retCode（與 replay client 對齊）。
_RETRIABLE_BYBIT_RETCODES = {10006, 10016, 10018}

# PreLaunch 為「上市前競價」狀態；Trading 為「正式可交易」。Gate-B 關注的核心
# 轉移就是 PreLaunch → Trading（symbol 真正開盤的瞬間）。
_STATUS_PRELAUNCH = "PreLaunch"
_STATUS_TRADING = "Trading"


class GateBRestError(RuntimeError):
    """REST 輪詢無法安全完成時拋出。"""


@dataclass(frozen=True)
class RestPollPolicy:
    """REST 輪詢策略（全部可由 env override，預設保守）。

    為什麼可調且保守：PreLaunch→Trading 轉移稀有，過密輪詢只是浪費 public rate
    budget；預設 30s 一輪足以把 capture_lag 量到秒級。
    """

    poll_interval_seconds: float = 30.0
    max_attempts: int = 3
    base_backoff_ms: int = 250
    timeout_seconds: float = 12.0
    limit: int = 1000


def _env_float(name: str, default: float, *, lower: float, upper: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        parsed = float(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


def _env_int(name: str, default: int, *, lower: int, upper: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        parsed = int(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


def current_rest_poll_policy() -> RestPollPolicy:
    """讀環境變數組出當前 REST 輪詢策略（保守 clamp）。"""
    return RestPollPolicy(
        poll_interval_seconds=_env_float(
            "OPENCLAW_GATE_B_REST_POLL_INTERVAL_S", 30.0, lower=5.0, upper=300.0
        ),
        max_attempts=_env_int(
            "OPENCLAW_GATE_B_REST_RETRY_MAX_ATTEMPTS", 3, lower=1, upper=5
        ),
        base_backoff_ms=_env_int(
            "OPENCLAW_GATE_B_REST_BACKOFF_BASE_MS", 250, lower=50, upper=2_000
        ),
        timeout_seconds=_env_float(
            "OPENCLAW_GATE_B_REST_TIMEOUT_S", 12.0, lower=2.0, upper=30.0
        ),
        limit=_env_int("OPENCLAW_GATE_B_REST_LIMIT", 1000, lower=1, upper=1000),
    )


@dataclass(frozen=True)
class InstrumentPhase:
    """單一 symbol 的一次 phase 觀測（point-in-time 快照）。

    所有時間欄位區分 exchange 來源（launch_time_ms / 由 REST 給）與本地觀測
    （observed_ingest_ts_ms / 本探針讀到的本地時刻），以滿足 leak-free provenance。
    """

    symbol: str
    status: str
    launch_time_ms: Optional[int]
    cur_auction_phase: Optional[str]
    pre_listing_phases: tuple[dict[str, Any], ...]
    observed_ingest_ts_ms: int


class InstrumentsInfoPoller:
    """隔離的 instruments-info 輪詢 client（urllib + endpoint allowlist，無 auth）。"""

    def __init__(
        self,
        *,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        base_url: str = _BYBIT_PUBLIC_BASE_URL,
    ) -> None:
        self._urlopen = urlopen
        self._sleeper = sleeper
        self._clock_ms = clock_ms
        self._base_url = base_url.rstrip("/")

    def fetch_prelaunch(
        self, *, category: str = "linear", status: str = _STATUS_PRELAUNCH
    ) -> list[InstrumentPhase]:
        """拉一頁 instruments-info（預設 PreLaunch），解析成 InstrumentPhase 列表。

        為什麼預設 status=PreLaunch：Gate-B SoT 是「即將上市的候選」這個前瞻視圖；
        symbol 一旦轉 Trading，下一輪以 status=Trading 補查即可確認轉移時刻。
        """
        policy = current_rest_poll_policy()
        data = self._request_json(
            _INSTRUMENTS_INFO_ENDPOINT,
            {
                "category": category,
                "status": status,
                "limit": str(policy.limit),
            },
        )
        ret_code = data.get("retCode")
        if ret_code != 0:
            raise GateBRestError(
                "instruments_info_error:"
                + str(data.get("retMsg") or ret_code or "unknown")
            )
        observed = self._clock_ms()
        rows = data.get("result", {}).get("list", [])
        out: list[InstrumentPhase] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(self._parse_row(row, observed))
        return out

    def _parse_row(self, row: dict[str, Any], observed_ingest_ts_ms: int) -> InstrumentPhase:
        symbol = str(row.get("symbol", ""))
        status = str(row.get("status", ""))
        launch_raw = row.get("launchTime")
        launch_time_ms: Optional[int]
        try:
            # Bybit launchTime 為毫秒字串；"0" / 空 代表未設。
            launch_time_ms = int(launch_raw) if launch_raw not in (None, "", "0") else None
        except (TypeError, ValueError):
            launch_time_ms = None
        pre_listing = row.get("preListingInfo") or {}
        phases_raw = pre_listing.get("phases") if isinstance(pre_listing, dict) else None
        phases: tuple[dict[str, Any], ...]
        if isinstance(phases_raw, list):
            phases = tuple(p for p in phases_raw if isinstance(p, dict))
        else:
            phases = ()
        cur_auction = pre_listing.get("curAuctionPhase") if isinstance(pre_listing, dict) else None
        # curAuctionPhase 也可能直接掛在 row（不同 schema 版本），取其一。
        if cur_auction in (None, "") and "curAuctionPhase" in row:
            cur_auction = row.get("curAuctionPhase")
        return InstrumentPhase(
            symbol=symbol,
            status=status,
            launch_time_ms=launch_time_ms,
            cur_auction_phase=str(cur_auction) if cur_auction not in (None, "") else None,
            pre_listing_phases=phases,
            observed_ingest_ts_ms=observed_ingest_ts_ms,
        )

    def _request_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise GateBRestError(f"gate_b_endpoint_not_allowed:{endpoint}")
        policy = current_rest_poll_policy()
        query = urllib.parse.urlencode(params)
        url = f"{self._base_url}{endpoint}?{query}"
        last_error: Optional[BaseException] = None
        for attempt in range(1, policy.max_attempts + 1):
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "OpenClawGateBProbe/1.0"},
            )
            try:
                with self._urlopen(req, timeout=policy.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in _RETRIABLE_HTTP_CODES and attempt < policy.max_attempts:
                    self._sleep_before_retry(attempt, policy)
                    continue
                raise GateBRestError(f"instruments_info_http_error:{exc.code}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < policy.max_attempts:
                    self._sleep_before_retry(attempt, policy)
                    continue
                raise GateBRestError(f"instruments_info_url_error:{exc.reason}") from exc

            ret_code = data.get("retCode")
            if ret_code in _RETRIABLE_BYBIT_RETCODES and attempt < policy.max_attempts:
                last_error = GateBRestError(f"instruments_info_retriable_retcode:{ret_code}")
                self._sleep_before_retry(attempt, policy)
                continue
            return data

        raise GateBRestError(f"instruments_info_retry_exhausted:{last_error}")

    def _sleep_before_retry(self, attempt: int, policy: RestPollPolicy) -> None:
        base_seconds = policy.base_backoff_ms / 1000.0
        self._sleeper(base_seconds * (2 ** (attempt - 1)))


@dataclass
class PhaseTransition:
    """一次偵測到的 phase 轉移（記憶體事件，後由 artifact 層封裝）。"""

    symbol: str
    prev_status: str
    new_status: str
    launch_time_ms: Optional[int]
    detected_ingest_ts_ms: int


@dataclass
class PhaseStateMachine:
    """純記憶體 phase 狀態機 — 偵測 PreLaunch → Trading 轉移。

    為什麼純記憶體：探針是一次性短窗運行，不持久化狀態（不寫 DB）；每次輪詢比對
    上一輪 status，發現「曾在 PreLaunch、本輪變 Trading」即記一個 transition。
    """

    # symbol → 上一次觀測到的 status。
    _last_status: dict[str, str] = field(default_factory=dict)
    # symbol → 首次看到的 launch_time_ms（供 capture_lag 計算的 launchTime 基準）。
    _launch_time: dict[str, Optional[int]] = field(default_factory=dict)

    def observe(self, phases: list[InstrumentPhase]) -> list[PhaseTransition]:
        """吃一輪觀測，回傳本輪新偵測到的 PreLaunch→Trading 轉移列表。"""
        transitions: list[PhaseTransition] = []
        for p in phases:
            prev = self._last_status.get(p.symbol)
            # 記錄/更新 launchTime（一旦有非 None 值就鎖住，避免後續被 null 覆蓋）。
            if p.launch_time_ms is not None or p.symbol not in self._launch_time:
                self._launch_time[p.symbol] = p.launch_time_ms
            if prev == _STATUS_PRELAUNCH and p.status == _STATUS_TRADING:
                transitions.append(
                    PhaseTransition(
                        symbol=p.symbol,
                        prev_status=prev,
                        new_status=p.status,
                        launch_time_ms=self._launch_time.get(p.symbol),
                        detected_ingest_ts_ms=p.observed_ingest_ts_ms,
                    )
                )
            self._last_status[p.symbol] = p.status
        return transitions

    def prelaunch_symbols(self) -> set[str]:
        """當前仍處於 PreLaunch 的 symbol 集合（= WS 應動態訂閱的候選）。"""
        return {s for s, st in self._last_status.items() if st == _STATUS_PRELAUNCH}

    def launch_time_of(self, symbol: str) -> Optional[int]:
        """回傳某 symbol 鎖定的 launchTime（capture_lag 基準），未知回 None。"""
        return self._launch_time.get(symbol)


class GateBRestProbe:
    """組裝 instruments-info 輪詢 + phase 狀態機 + JSONL 落地。

    這層只負責「SoT 側」：輪詢、偵測轉移、寫 rest_phase_poll.jsonl、並把候選
    symbol 集合與 transition 暴露給上層 entry（由 entry 餵給 WS 層動態訂閱）。
    """

    def __init__(
        self,
        *,
        poller: Optional[InstrumentsInfoPoller] = None,
        jsonl_writer: Optional[Callable[[dict[str, Any]], None]] = None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._poller = poller or InstrumentsInfoPoller()
        self._jsonl_writer = jsonl_writer
        self._clock_ms = clock_ms
        self.state = PhaseStateMachine()

    def poll_once(self) -> tuple[list[InstrumentPhase], list[PhaseTransition]]:
        """執行單輪輪詢：拉 PreLaunch + 補拉 Trading 確認轉移，落地 JSONL。

        為什麼補拉 Trading：symbol 轉 Trading 後就會從 status=PreLaunch 的結果集
        消失；只看 PreLaunch 視圖看不到「轉移後」狀態。故每輪在 PreLaunch 之外，
        針對「上一輪還在 PreLaunch」的 symbol 以 status=Trading 再查一次確認。
        """
        prelaunch = self._poller.fetch_prelaunch(status=_STATUS_PRELAUNCH)
        # 針對先前 PreLaunch 的 symbol 補查 Trading，捕捉「剛轉 Trading」者。
        watched = self.state.prelaunch_symbols()
        trading_confirm: list[InstrumentPhase] = []
        if watched:
            trading_rows = self._poller.fetch_prelaunch(status=_STATUS_TRADING)
            trading_confirm = [r for r in trading_rows if r.symbol in watched]
        combined = prelaunch + trading_confirm
        transitions = self.state.observe(combined)
        self._emit_poll(combined, transitions)
        return combined, transitions

    def _emit_poll(
        self, phases: list[InstrumentPhase], transitions: list[PhaseTransition]
    ) -> None:
        if self._jsonl_writer is None:
            return
        poll_ts = self._clock_ms()
        for p in phases:
            self._jsonl_writer(
                {
                    "kind": "rest_phase_poll",
                    "poll_ts_local_ms": poll_ts,
                    "symbol": p.symbol,
                    "status": p.status,
                    "launch_time_ms": p.launch_time_ms,
                    "cur_auction_phase": p.cur_auction_phase,
                    "pre_listing_phases": list(p.pre_listing_phases),
                    "observed_ingest_ts_ms": p.observed_ingest_ts_ms,
                }
            )
        for t in transitions:
            self._jsonl_writer(
                {
                    "kind": "phase_transition",
                    "poll_ts_local_ms": poll_ts,
                    "symbol": t.symbol,
                    "prev_status": t.prev_status,
                    "new_status": t.new_status,
                    "launch_time_ms": t.launch_time_ms,
                    "detected_ingest_ts_ms": t.detected_ingest_ts_ms,
                }
            )


__all__ = [
    "GateBRestError",
    "RestPollPolicy",
    "current_rest_poll_policy",
    "InstrumentPhase",
    "InstrumentsInfoPoller",
    "PhaseTransition",
    "PhaseStateMachine",
    "GateBRestProbe",
]
