from __future__ import annotations

"""
G3-08 Phase 1 Sub-task B — H-state aggregator (Python query handler stub).
G3-08 Phase 1 Sub-task B — H 狀態聚合器（Python 查詢處理器 stub）。

MODULE_NOTE (EN):
  Phase 1 stub for the ``query_h_state_full`` reverse IPC handler. Returns the
  empty-shell response shape defined in PA design plan §5.1 / §4.2.1 so that
  the Rust ``h_state_cache`` poller can connect end-to-end **before** any H1-H5
  / 5-Agent producer is wired up. Phase 2 (H1+H3), Phase 3 (H2+H4+H5), Phase 4
  (5-Agent) will progressively populate the empty dicts.

  Design intent (per PA §10.1 completion criteria):
    - When ``OPENCLAW_H_STATE_GATEWAY`` is enabled, the IPC handler exists and
      is callable; it returns the canonical empty shape.
    - When the env var is disabled, the IPC handler is **still callable** (the
      route is unconditionally registered), but again returns the empty shape.
      Per PA §10.1 the route must be reachable at all times — only the
      Python-side invalidator + Rust-side poller daemon are env-gated.
    - The schema is forward-compatible: ``h_states`` and ``agent_states`` are
      open dicts. Phase 2-4 add keys without changing the wire shape; Rust
      side uses ``serde(default)`` + ``HashMap<String, …>`` to absorb new
      fields without lock-step deploy (see PA §5.2).
    - This module **does not** import H1-H5 / 5-Agent singletons; the actual
      ``get_*_snapshot()`` calls land in Phase 2-4. This keeps Phase 1 strictly
      mechanical (IPC plumbing only) and avoids circular-import risk during
      bootstrap.

  Schema returned (matches PA §5.1 / §4.2.1 result skeleton):

      {
        "version":       <monotonic int>,    # 0 in Phase 1
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      { },                # filled by Phase 2-4
        "agent_states":  { },                # filled by Phase 4
      }

  Why the wrapping ``h_states`` / ``agent_states`` keys instead of flat
  ``h1`` / ``h2`` / ... at the top level:
    - PA §5.1 example uses flat top-level keys, but the Rust side (PA §5.2 /
      §6.1) groups them into ``HStateCache.h1 / h2 / h3 / h4 / h5 / agents``
      DashMaps. Phase 1 chooses an explicit two-bucket grouping so:
        a) the Rust deserializer has a single top-level field per bucket
           (``h_states`` → 5 H modules, ``agent_states`` → 5 agents);
        b) future H6+ or new agents add keys inside the bucket without
           touching the response root;
        c) clients can detect "Phase 1 placeholder" cheaply by checking
           ``not response["h_states"] and not response["agent_states"]``.

  Public API:
    - ``build_h_state_full_response(include=None)`` — pure function, returns
      the shaped dict. ``include`` filter accepted for API parity with PA
      §5.1 but Phase 1 ignores it (no producers to filter against).

MODULE_NOTE (中):
  G3-08 Phase 1 ``query_h_state_full`` reverse IPC handler 的 stub。回傳 PA
  design §5.1 / §4.2.1 定義的空殼結構，讓 Rust ``h_state_cache`` poller 在
  H1-H5 / 5-Agent producer 接線**之前**即可端對端打通。Phase 2（H1+H3）、
  Phase 3（H2+H4+H5）、Phase 4（5-Agent）逐步填空。

  設計意圖（對齊 PA §10.1 完成標準）：
    - ``OPENCLAW_H_STATE_GATEWAY`` 開啟時，IPC handler 存在且可被呼叫，
      回傳標準空殼。
    - env 關閉時，IPC handler **仍可被呼叫**（route 無條件註冊），仍回空殼。
      PA §10.1 規定 route 任何時候都可達 —— 只有 Python 端 invalidator 與
      Rust 端 poller daemon 受 env 閘控。
    - schema 向前相容：``h_states`` 與 ``agent_states`` 為開放 dict；Phase
      2-4 加 key 不改 wire shape；Rust 側用 ``serde(default)`` +
      ``HashMap<String, …>`` 吸收新欄位，不需 lock-step 部署（PA §5.2）。
    - 本模組**不** import H1-H5 / 5-Agent singleton；實際 ``get_*_snapshot()``
      呼叫於 Phase 2-4 落地，藉此讓 Phase 1 維持純機械（僅 IPC 線路），
      避免 bootstrap 期循環匯入風險。

  回傳 schema（對齊 PA §5.1 / §4.2.1 result 骨架）：

      {
        "version":       <monotonic int>,    # Phase 1 為 0
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      { },                # Phase 2-4 填入
        "agent_states":  { },                # Phase 4 填入
      }

  為何包一層 ``h_states`` / ``agent_states`` 而非 PA §5.1 範例那樣 flat 平鋪：
    - PA §5.1 用 flat top-level，但 Rust 端（PA §5.2 / §6.1）把 H 與 Agent
      分桶為 ``HStateCache.h1 / h2 / h3 / h4 / h5 / agents`` DashMap。
      Phase 1 採顯式兩桶分組讓：
        (a) Rust deserializer 每桶一個 top-level 欄位（``h_states`` → 5 H
            模組、``agent_states`` → 5 agent）；
        (b) 未來 H6+ 或新 agent 在桶內加 key，不動 response root；
        (c) client 可廉價偵測「Phase 1 placeholder」：
            ``not response["h_states"] and not response["agent_states"]``。

  公開 API：
    - ``build_h_state_full_response(include=None)`` — 純函式，回傳成形 dict。
      ``include`` 過濾參數保留以對齊 PA §5.1，但 Phase 1 不消化（無 producer
      可過濾）。
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Schema constants / Schema 常數 ──────────────────────────────────────────

# Phase 1 placeholder version. Phase 2+ replaces with a monotonic counter
# fed by the Python H-state-store (per PA §5.1 ``_state_version_counter()``).
# Phase 1 placeholder 版本；Phase 2+ 改為由 Python H 狀態儲存驅動的單調計數器
# （PA §5.1 ``_state_version_counter()``）。
_PHASE1_VERSION: int = 0

# Canonical buckets — Rust ``HStateCache`` uses identical key names (PA §6.1).
# 標準桶 —— Rust ``HStateCache`` 使用相同 key 名（PA §6.1）。
_H_BUCKET_KEY: str = "h_states"
_AGENT_BUCKET_KEY: str = "agent_states"


def build_h_state_full_response(
    include: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Phase 1 stub: return the canonical empty-shell H-state response.
    Phase 1 stub：回傳標準空殼 H 狀態回應。

    Args:
        include: Optional bucket-filter (e.g. ``["h1", "h3"]``) accepted for
            API parity with PA §5.1; **ignored in Phase 1** because no
            producers are wired. Phase 2+ honors this list.
            可選的桶過濾（如 ``["h1", "h3"]``），保留以對齊 PA §5.1；
            **Phase 1 忽略**（無 producer 可過濾），Phase 2+ 始遵循。

    Returns:
        Dict with keys ``version`` / ``fetched_at_ms`` / ``h_states`` /
        ``agent_states``. Both bucket dicts are empty in Phase 1.
        含 ``version`` / ``fetched_at_ms`` / ``h_states`` / ``agent_states``
        鍵的 dict；Phase 1 兩個桶 dict 皆為空。

    Notes:
        - Pure function: no I/O, no singleton access, no env-var read.
          The IPC dispatch handler is responsible for calling this and
          packaging into a JSON-RPC ``result``.
        - Always succeeds (cannot raise on the empty path).
        - 純函式：無 I/O、無 singleton 存取、無 env 讀取。
          IPC 派發 handler 負責呼叫並包成 JSON-RPC ``result``。
        - 永遠成功（空殼路徑不可能 raise）。
    """
    if include is not None:
        # Phase 1 honours API surface but does NOT filter (no producers).
        # Log at DEBUG so Phase 2+ migration can audit any caller passing
        # a filter expecting it to take effect already.
        # Phase 1 保留 API 但不過濾（無 producer）；DEBUG 記錄以便
        # Phase 2+ 遷移時審計提早傳 filter 的呼叫端。
        logger.debug(
            "build_h_state_full_response: include=%r received but Phase 1 "
            "stub ignores filter (no H/agent producers wired yet) "
            "/ Phase 1 stub 忽略過濾參數（H/agent producer 尚未接線）",
            include,
        )

    # Wall-clock ms timestamp aligned with PA §4.2.1 ``fetched_at_ms`` field.
    # Use ``time.time()`` (not ``time.monotonic()``) since the Rust side
    # compares with its own ``unix_ms()`` for staleness math (PA §4.1).
    # 對齊 PA §4.2.1 ``fetched_at_ms`` 欄位的 wall-clock ms 時間戳。
    # 用 ``time.time()``（非 ``time.monotonic()``），因為 Rust 側用自家
    # ``unix_ms()`` 比對 staleness（PA §4.1）。
    fetched_at_ms = int(time.time() * 1000)

    return {
        "version": _PHASE1_VERSION,
        "fetched_at_ms": fetched_at_ms,
        _H_BUCKET_KEY: {},
        _AGENT_BUCKET_KEY: {},
    }


__all__ = [
    "build_h_state_full_response",
]
