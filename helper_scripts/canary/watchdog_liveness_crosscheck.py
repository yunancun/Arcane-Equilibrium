#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：watchdog 「破壞性重啟前」的第二獨立存活訊號交叉檢查（B1，2026-06-15）。
  engine_watchdog 以 pipeline_snapshot.json 的 mtime 過期（>STALE_THRESHOLD）判定
  ENGINE_CRASH，隨即 `restart_all.sh --engine-only` 對引擎發 SIGTERM——這會「以市價
  平掉所有未平倉位」。RCA（2026-06-15）顯示 ~21/21 次這類重啟其實引擎是活的（仍在
  serve IPC、處理 tick），只是 snapshot-writer task 停寫快照。即引擎被以市價平倉 ~2×/天
  全屬誤殺。本模組在宣告 ENGINE_CRASH→重啟「之前」，向第二個獨立訊號（引擎 IPC
  socket /tmp/openclaw/engine.sock）發一個唯讀輕量請求（get_risk_runtime_status，
  與 engine.log 觀測到實際被 serve 的同一 method）求證引擎是否仍活。

主要函數：
  - probe_engine_ipc：對 engine.sock 發 HMAC-auth + 唯讀 JSON-RPC，回 ProbeResult；
    任何連線/認證/逾時/亂碼皆 fail toward NOT-alive（保守，重啟治本優先於避免平倉）。
  - decide_restart_suppression：把 ProbeResult + max-hold 計數轉成「是否抑制重啟」的
    決策（SuppressionDecision），含 N-連續週期上限與硬性 10 分鐘上限。
  - liveness_crosscheck_enabled / resolve_stale_threshold_ms：env 旗標（B3-lite）。

硬邊界（fail toward restart）：
  - 本模組改變 watchdog 核心安全行為（是否平倉）。任何「不確定」一律倒向「重啟」
    （= NOT alive），唯有 IPC 在緊湊 timeout 內「明確」回正確 reply 才抑制重啟。
  - 抑制不是無限期：snapshot 持續 stale 但 IPC 仍活超過 N 連續週期或硬性 max-hold 牆
    （MAX_HOLD_SECONDS）即升級為重啟——永久停寫快照的 writer 本身就是故障，不可
    無限期靜坐。max-hold 上限為顯式常數並註明理由。
  - 純唯讀探測：絕不送任何會改變交易狀態的 method；method 白名單僅 get_risk_runtime_status。
  - 不 import FastAPI app（維持 watchdog 零 app 依賴）；IPC helper 是 edge_p2_flip_dry_run.py
    內聯 helper 的精簡 clone（同 ts=unix 秒 HMAC 對齊 Rust verifier ±30s 容差）。

依賴：標準庫 socket / hmac / hashlib / json / time / os；OPENCLAW_IPC_SECRET（設了才認證，
  未設=dev 模式跳過）；OPENCLAW_IPC_SOCKET（socket 路徑，預設 /tmp/openclaw/engine.sock）。

部署驗證屬 runtime（Linux）步驟：Mac 無引擎，本模組單元測試全 mock IPC 層。
"""
from __future__ import annotations

import hashlib
import hmac as _hmac_lib
import json
import logging
import os
import socket as _socket
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("watchdog_liveness_crosscheck")

# ── env / socket 常數（與 ipc_client_sync.py / edge_p2_flip_dry_run.py 對齊）──
DEFAULT_SOCKET_PATH = "/tmp/openclaw/engine.sock"
SOCKET_ENV_VAR = "OPENCLAW_IPC_SOCKET"
IPC_SECRET_ENV_VAR = "OPENCLAW_IPC_SECRET"

# B3-lite：交叉檢查總開關（預設開）。誤動作時可由 env 一鍵關閉，立即退回舊行為
# （stale 即重啟，無交叉檢查）。為什麼 default-on：B1 的全部價值在於擋掉誤殺平倉。
CROSSCHECK_ENABLED_ENV_VAR = "OPENCLAW_WATCHDOG_LIVENESS_CROSSCHECK"
# B3-lite：可由 env 覆寫 stale 門檻（毫秒）。default 不變（由 watchdog 主常數決定），
# 只在 env 提供且可解析為正數時生效。為什麼留覆寫：現場若需臨時放寬/收緊門檻不必改碼。
STALE_THRESHOLD_MS_ENV_VAR = "OPENCLAW_WATCHDOG_STALE_MS"

# 探測用的唯讀 method —— 與 engine.log「IPC client authenticated (HMAC-SHA256)」後
# 實際被 serve 的同一 method 一致；唯讀、不改交易狀態。白名單只此一個，杜絕誤送寫 method。
PROBE_METHOD = "get_risk_runtime_status"
# 探測 timeout（秒）：緊湊。為什麼 3s：活引擎本地 unix socket 唯讀查詢應遠快於此；
# 超過即視為「沒有明確的存活證據」→ fail toward restart。連線+認證+請求共用此預算。
PROBE_TIMEOUT_SECONDS = 3.0

# ── max-hold 上限（兩道，任一達到即升級為重啟）──
# 為什麼必須有上限：snapshot-writer 永久停寫本身就是故障；若引擎 IPC 一直活而我們無限
# 抑制重啟，等於對「半死」引擎（活著處理 tick 但完全不寫快照、可能也不寫其他狀態）視而
# 不見。A1/A2 軌在修 stall 本身；B1 只負責「不要在引擎其實活著時誤殺平倉」，但不能變成
# 「永遠不重啟」。兩道牆取先到者：
#   (1) N 連續抑制週期：以 poll 計數，快速封頂（poll=2s 時 ~5 分鐘）。
MAX_HOLD_CONSECUTIVE_CYCLES = 150
#   (2) 硬性 wall-clock 上限：自「首次因本機制抑制」起算，超過即重啟。10 分鐘是「snapshot
#       停寫但引擎仍活」可容忍上限——再久就必須讓 self-heal 介入（即使會平倉）。
MAX_HOLD_SECONDS = 600.0


@dataclass
class ProbeResult:
    """IPC 探測結果。alive=True 僅代表引擎在 timeout 內明確回了正確 reply。"""
    alive: bool
    # 失敗/降級原因分類鍵（穩定字串，供 log/canary/audit 去重與診斷）。
    reason: str
    # 探測往返耗時（秒，best-effort；失敗時可能為近似值）。
    latency_seconds: float = 0.0


@dataclass
class SuppressionDecision:
    """重啟抑制決策。suppress=True → 不重啟、不平倉、發 SNAPSHOT_STALL_ENGINE_ALIVE。"""
    suppress: bool
    # 決策原因分類鍵（穩定字串）。
    reason: str
    # 自首次抑制起的連續抑制週期數（達上限升級重啟時供 payload）。
    hold_cycles: int = 0
    # 自首次抑制起經過秒數（best-effort）。
    hold_seconds: float = 0.0


def liveness_crosscheck_enabled() -> bool:
    """B3-lite：交叉檢查是否啟用（env default-on）。

    為什麼 default-on 但可關：B1 預設應生效（擋誤殺）；若本機制自身誤動作（例如某種
    引擎狀態下 IPC 假活），operator 設 OPENCLAW_WATCHDOG_LIVENESS_CROSSCHECK=0 即可
    立刻退回「stale 即重啟」的舊保守行為，不必改碼/重部署。
    """
    raw = os.environ.get(CROSSCHECK_ENABLED_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def resolve_stale_threshold_ms(default_ms: float) -> float:
    """B3-lite：解析 stale 門檻（毫秒）。env 提供且為正數才覆寫，否則回 default。

    fail-safe：env 缺失/空/非數字/非正數一律退回 default_ms（不放寬也不報錯）。
    """
    raw = os.environ.get(STALE_THRESHOLD_MS_ENV_VAR)
    if raw is None:
        return default_ms
    try:
        val = float(raw.strip())
    except (TypeError, ValueError):
        logger.warning(
            "invalid %s=%r — using default %.0fms / stale 門檻 env 非法，用預設",
            STALE_THRESHOLD_MS_ENV_VAR, raw, default_ms,
        )
        return default_ms
    if val <= 0:
        logger.warning(
            "non-positive %s=%r — using default %.0fms / stale 門檻 env 非正數，用預設",
            STALE_THRESHOLD_MS_ENV_VAR, raw, default_ms,
        )
        return default_ms
    return val


def probe_engine_ipc(
    socket_path: Optional[str] = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> ProbeResult:
    """向引擎 IPC socket 發 HMAC-auth + 唯讀 JSON-RPC，回 ProbeResult。

    為什麼 fail toward NOT-alive：本探測的回答決定「是否抑制一個會平倉的重啟」。任何
    含糊（連不上 / socket 不存在 / 認證失敗 / 逾時 / 空回應 / 亂碼 / JSON-RPC error /
    id 不符 / 非預期 result 形狀）都當作「沒有明確存活證據」→ alive=False → 重啟照舊。
    唯有引擎在 timeout 內明確回一個格式正確的 result，才回 alive=True。

    探測流程（精簡 clone 自 edge_p2_flip_dry_run.py 內聯 helper）：
      1. AF_UNIX 連線（settimeout=timeout）。
      2. 若設 OPENCLAW_IPC_SECRET：送 __auth（ts=unix 秒，對齊 Rust verifier ±30s）。
      3. 送 get_risk_runtime_status（唯讀），讀一行 JSON-RPC 回應。
      4. 驗 id==1 且無 error 且 result 為 dict → alive。
    """
    path = socket_path or os.environ.get(SOCKET_ENV_VAR, DEFAULT_SOCKET_PATH)
    ipc_secret = os.environ.get(IPC_SECRET_ENV_VAR, "")
    started = time.time()

    def _elapsed() -> float:
        return time.time() - started

    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(path)

            def _recv_line() -> str:
                buf = b""
                while True:
                    ch = sock.recv(1)
                    if not ch:
                        raise ConnectionResetError("engine closed connection")
                    if ch == b"\n":
                        return buf.decode("utf-8")
                    buf += ch

            def _send(msg: dict[str, Any]) -> None:
                sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))

            # HMAC-SHA256 認證握手（未設密鑰時跳過，dev 模式）。ts 必須 unix 秒，
            # 對齊 Rust verifier（ipc_server/mod.rs，±30s 容差）；毫秒會 100% fail。
            if ipc_secret:
                ts = int(time.time())
                token = _hmac_lib.new(
                    ipc_secret.encode("utf-8"),
                    str(ts).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                _send({"jsonrpc": "2.0", "method": "__auth",
                       "params": {"token": token, "ts": ts}, "id": 0})
                auth_resp = json.loads(_recv_line())
                if not isinstance(auth_resp, dict) or auth_resp.get("error"):
                    # 認證失敗 = 沒有明確存活證據 → fail toward restart。
                    return ProbeResult(
                        alive=False, reason="ipc_auth_failed", latency_seconds=_elapsed(),
                    )

            # 唯讀探測請求。
            _send({"jsonrpc": "2.0", "method": PROBE_METHOD, "params": {}, "id": 1})
            resp = json.loads(_recv_line())

            if not isinstance(resp, dict):
                return ProbeResult(
                    alive=False, reason="ipc_garbled_reply", latency_seconds=_elapsed(),
                )
            if resp.get("error"):
                # 引擎回了 JSON-RPC error —— 不是「明確的健康 reply」，保守當 not-alive。
                return ProbeResult(
                    alive=False, reason="ipc_rpc_error", latency_seconds=_elapsed(),
                )
            if resp.get("id") != 1:
                return ProbeResult(
                    alive=False, reason="ipc_id_mismatch", latency_seconds=_elapsed(),
                )
            result = resp.get("result")
            if not isinstance(result, dict):
                # get_risk_runtime_status 正常回 dict；非 dict = 非預期形狀，保守。
                return ProbeResult(
                    alive=False, reason="ipc_unexpected_result", latency_seconds=_elapsed(),
                )
            # 到此 = 引擎在 timeout 內明確回了格式正確的唯讀 result → 確定活著。
            return ProbeResult(
                alive=True, reason="ipc_responsive", latency_seconds=_elapsed(),
            )
    except FileNotFoundError:
        # socket 不存在 = 引擎進程未跑（真死）→ 重啟。
        return ProbeResult(alive=False, reason="ipc_socket_missing", latency_seconds=_elapsed())
    except (_socket.timeout, TimeoutError):
        # timeout = 引擎可能掛死/不回應 → 沒有明確存活證據 → 重啟。
        return ProbeResult(alive=False, reason="ipc_timeout", latency_seconds=_elapsed())
    except (ConnectionError, OSError) as exc:
        return ProbeResult(
            alive=False, reason=f"ipc_conn_error:{type(exc).__name__}",
            latency_seconds=_elapsed(),
        )
    except (json.JSONDecodeError, ValueError):
        # 回應不是合法 JSON = 亂碼 → 保守。
        return ProbeResult(alive=False, reason="ipc_garbled_reply", latency_seconds=_elapsed())
    except Exception as exc:  # noqa: BLE001 — 探測自身任何意外都不得拋進 watchdog；保守當 not-alive
        logger.warning(
            "liveness probe unexpected error (treating as NOT alive): %s / "
            "存活探測意外錯誤（保守判 not-alive）",
            exc,
        )
        return ProbeResult(
            alive=False, reason=f"ipc_probe_exception:{type(exc).__name__}",
            latency_seconds=_elapsed(),
        )


def decide_restart_suppression(
    probe: ProbeResult,
    *,
    prior_hold_cycles: int,
    first_suppress_ts: Optional[float],
    now: float,
) -> SuppressionDecision:
    """根據 IPC 探測 + max-hold 計數，決定本次 stale poll 是否抑制重啟。

    決策表（fail toward restart）：
      - probe.alive=False → 不抑制（suppress=False, reason=probe.reason）：真死/含糊一律重啟。
      - probe.alive=True 但已達 max-hold 上限（連續週期 ≥ N 或 wall-clock ≥ MAX_HOLD_SECONDS）
        → 不抑制（suppress=False, reason="max_hold_*"）：永久停寫快照本身是故障，升級重啟。
      - probe.alive=True 且未達上限 → 抑制（suppress=True, reason="engine_alive_snapshot_stalled"）：
        引擎活著只是 snapshot-writer 停了，不 SIGTERM、不平倉。

    Args:
      prior_hold_cycles: 在此次 poll 之前已連續抑制的週期數（0=尚未抑制）。
      first_suppress_ts: 首次因本機制抑制的時間戳（None=尚未抑制）。
      now: 當前時間戳。
    回傳的 hold_cycles 是「若本次抑制，累計到第幾個週期」（prior+1）；hold_seconds 同理。
    """
    if not probe.alive:
        # 引擎沒有明確存活證據 → 重啟照舊（B1 的 fail-safe 核心）。
        return SuppressionDecision(
            suppress=False, reason=probe.reason,
            hold_cycles=prior_hold_cycles, hold_seconds=0.0,
        )

    # 引擎明確活著。計算「若繼續抑制」會落在第幾個週期 / 經過多久。
    candidate_cycles = prior_hold_cycles + 1
    base_ts = first_suppress_ts if first_suppress_ts is not None else now
    hold_seconds = max(0.0, now - base_ts)

    # max-hold 牆（兩道取先到）：達到即「即使 IPC 活也升級重啟」。
    if candidate_cycles > MAX_HOLD_CONSECUTIVE_CYCLES:
        return SuppressionDecision(
            suppress=False, reason="max_hold_cycles_exceeded",
            hold_cycles=candidate_cycles, hold_seconds=hold_seconds,
        )
    if hold_seconds >= MAX_HOLD_SECONDS:
        return SuppressionDecision(
            suppress=False, reason="max_hold_seconds_exceeded",
            hold_cycles=candidate_cycles, hold_seconds=hold_seconds,
        )

    # 未達上限 → 抑制重啟（引擎活著，只是 snapshot-writer 停寫）。
    return SuppressionDecision(
        suppress=True, reason="engine_alive_snapshot_stalled",
        hold_cycles=candidate_cycles, hold_seconds=hold_seconds,
    )
