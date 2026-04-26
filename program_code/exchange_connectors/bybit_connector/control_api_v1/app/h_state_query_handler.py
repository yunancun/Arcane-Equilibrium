from __future__ import annotations

"""
G3-08 Phase 2 — H-state aggregator (Python query handler, real H1+H3).
G3-08 Phase 2 — H 狀態聚合器（Python 查詢處理器，真實 H1+H3）。

MODULE_NOTE (EN):
  Phase 2 upgrade of the ``query_h_state_full`` reverse IPC handler. Replaces
  the Phase 1 stub empty-shell with real H1 (ThoughtGate) + H3 (ModelRouter)
  snapshots aggregated from the process-global ``STRATEGIST_AGENT`` singleton
  (in ``strategy_wiring``). Phase 3 (H2+H4+H5 cost) and Phase 4 (5-Agent
  state events) progressively populate the remaining buckets.

  Phase 2 design intent (per PA design §10.2 + §5.1 + §7.1):
    - When H1 + H3 singletons are reachable AND env is enabled
      (``OPENCLAW_H_STATE_GATEWAY == "1"``), populate ``h_states.h1``
      and ``h_states.h3`` with the real snapshot dicts returned by
      ``H1ThoughtGate.get_h1_snapshot()`` / ``ModelRouter.get_h3_snapshot()``.
      Bump the schema ``version`` to 1.
    - When env is disabled OR singletons not yet wired (e.g. partial
      Phase 1 deploy / unit-test fixture) → fall back to the canonical
      Phase 1 empty shell (version=0, empty buckets). This preserves
      the contract that this handler **never raises** and is safe to
      call at any boot stage.
    - The reverse IPC route stays unconditionally registered (per
      Sub-task B); only the populated-vs-empty answer flips with env.
    - Forward-compatible: ``h_states`` and ``agent_states`` remain
      open dicts. Phase 3 adds ``h2`` / ``h4`` / ``h5`` keys without
      changing the wire shape; Phase 4 adds five agent keys to
      ``agent_states``. Rust ``HStateCache`` uses ``serde(default)`` +
      ``HashMap<String, …>`` to absorb new fields without lock-step
      deploy (PA §5.2).

  Lazy import strategy (avoids bootstrap circulars):
    - The handler does NOT import ``strategy_wiring`` at module top level
      because ``strategy_wiring`` itself imports ``h_state_invalidator``
      and many other agent modules. Top-level import would deadlock the
      worker boot sequence under uvicorn --workers 4.
    - Instead, ``_collect_h_snapshots()`` lazily imports inside the
      function body and silences any ``ImportError`` /
      ``AttributeError`` to keep the empty-shell contract.

  Thread safety:
    - ``H1ThoughtGate.get_h1_snapshot()`` and
      ``ModelRouter.get_h3_snapshot()`` each acquire only their own
      local locks; no cross-module locking, no deadlock risk.
    - Pure read; multiple concurrent ``query_h_state_full`` IPC calls
      (e.g. Rust poller + GUI healthcheck) are safe.

  Schema returned (PA §5.1 / §4.2.1, Phase 2 populated):

      {
        "version":       1,                   # Phase 2 (was 0 in Phase 1)
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      {
          "h1": { ... real H1ThoughtGate snapshot ... },
          "h3": { ... real ModelRouter snapshot ... },
        },
        "agent_states":  { },                 # filled by Phase 4
      }

  When H1/H3 singletons unreachable or env=0:

      {
        "version":       0,                   # Phase 1 fallback shape
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      { },
        "agent_states":  { },
      }

  Public API (unchanged from Phase 1):
    - ``build_h_state_full_response(include=None)`` — pure function
      (modulo singleton snapshots which are themselves pure reads).
      ``include`` filter still accepted; in Phase 2 we honour it for
      H1/H3 buckets (e.g. ``include=["h1"]`` returns only h1 in
      ``h_states``).

MODULE_NOTE (中):
  G3-08 Phase 2 升級。將 ``query_h_state_full`` reverse IPC handler 從
  Phase 1 stub 空殼升級為真實 H1（ThoughtGate）+ H3（ModelRouter）snapshot；
  從 ``strategy_wiring`` 的進程全域 ``STRATEGIST_AGENT`` singleton 透過
  ``._h1_gate`` / ``._model_router`` 拉取真實視圖。Phase 3（H2+H4+H5 成本）
  與 Phase 4（5-Agent 狀態事件）逐步填入剩餘桶。

  Phase 2 設計意圖（對齊 PA design §10.2 + §5.1 + §7.1）：
    - H1 + H3 singleton 可達且 env 開啟（``OPENCLAW_H_STATE_GATEWAY == "1"``）
      時，將 ``h_states.h1`` 與 ``h_states.h3`` 填入
      ``H1ThoughtGate.get_h1_snapshot()`` /
      ``ModelRouter.get_h3_snapshot()`` 的真實 snapshot dict；
      schema ``version`` 升至 1。
    - env 關閉或 singleton 尚未接線（如 Phase 1 部分部署 / unit-test fixture）
      → 退回 Phase 1 空殼（version=0、空桶）。維持本 handler **永不 raise**、
      可在任意 boot 階段安全呼叫的合約。
    - reverse IPC route 仍無條件註冊（Sub-task B）；env flip 影響的只是
      「填或空」，路由始終可達。
    - 向前相容：``h_states`` 與 ``agent_states`` 為開放 dict。Phase 3 新增
      ``h2`` / ``h4`` / ``h5`` 不改 wire shape；Phase 4 在 ``agent_states``
      加 5 個 agent key。Rust ``HStateCache`` 用 ``serde(default)`` +
      ``HashMap<String, …>`` 吸收新欄位，不需 lock-step 部署（PA §5.2）。

  延遲匯入策略（避免 bootstrap 循環）：
    - handler 模組頂層不 import ``strategy_wiring``，因為
      ``strategy_wiring`` 自身 import ``h_state_invalidator`` 與多個 agent
      模組；頂層匯入會在 uvicorn --workers 4 worker boot 序列死鎖。
    - 改在 ``_collect_h_snapshots()`` 函數體內延遲 import 並吞
      ``ImportError`` / ``AttributeError`` 以維持空殼合約。

  線程安全：
    - ``H1ThoughtGate.get_h1_snapshot()`` 與
      ``ModelRouter.get_h3_snapshot()`` 各自只取自身本地鎖；無跨模組鎖，
      無死鎖風險。
    - 純讀取；並發 ``query_h_state_full`` IPC（如 Rust poller + GUI
      healthcheck）安全。

  回傳 schema（PA §5.1 / §4.2.1，Phase 2 已填）：

      {
        "version":       1,                   # Phase 2（Phase 1 為 0）
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      {
          "h1": { ... 真實 H1ThoughtGate snapshot ... },
          "h3": { ... 真實 ModelRouter snapshot ... },
        },
        "agent_states":  { },                 # Phase 4 填入
      }

  H1/H3 singleton 不可達或 env=0：

      {
        "version":       0,                   # Phase 1 fallback 形狀
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      { },
        "agent_states":  { },
      }

  公開 API（與 Phase 1 不變）：
    - ``build_h_state_full_response(include=None)`` — 純函式（singleton
      snapshot 本身亦純讀）。``include`` 過濾在 Phase 2 對 H1/H3 桶生效
      （如 ``include=["h1"]`` 回 ``h_states`` 僅含 h1）。
"""

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Schema constants / Schema 常數 ──────────────────────────────────────────

# Phase 2 schema version. Phase 1 was 0 (empty shell); when env=1 + singletons
# wired we bump to 1 to signal real H1+H3 snapshots present. Phase 3 keeps 1
# (additive H2/H4/H5 fill the same wire shape); Phase 4 will likewise stay 1
# unless we add a breaking field. Bump to 2 only on schema-breaking change.
# Phase 2 schema 版本號。Phase 1 為 0（空殼）；env=1 + singleton 接線時升到 1
# 以信號真實 H1+H3 snapshot 已存在。Phase 3 維持 1（新增 H2/H4/H5 為加性，
# 不改 wire shape）；Phase 4 同理維持 1（除非加破壞性欄位）。僅破壞性變更
# 才升到 2。
_PHASE2_VERSION: int = 1
_PHASE1_FALLBACK_VERSION: int = 0

# Canonical buckets — Rust ``HStateCache`` uses identical key names (PA §6.1).
# 標準桶 —— Rust ``HStateCache`` 使用相同 key 名（PA §6.1）。
_H_BUCKET_KEY: str = "h_states"
_AGENT_BUCKET_KEY: str = "agent_states"

# Strict env-gate value (mirrors h_state_invalidator + Rust h_state_poller
# spawn condition). Anything other than "1" falls back to empty shell.
# 嚴格 env 閘值（對齊 h_state_invalidator 與 Rust h_state_poller spawn 條件）。
# 非 "1" 一律退回空殼。
_GATEWAY_ENV_VAR: str = "OPENCLAW_H_STATE_GATEWAY"
_GATEWAY_ENABLED_VALUE: str = "1"


def _is_gateway_enabled() -> bool:
    """Strict env-gate: True iff env var equals exactly ``"1"``.
    嚴格 env 閘檢查：env 變數恰為 ``"1"`` 才回 True。"""
    return os.environ.get(_GATEWAY_ENV_VAR) == _GATEWAY_ENABLED_VALUE


def _collect_h_snapshots(
    include_h1: bool,
    include_h3: bool,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Lazy-import strategy_wiring and pull H1+H3 snapshots.
    延遲 import strategy_wiring 並拉取 H1+H3 snapshot。

    Returns ``(h1_dict, h3_dict)``; either may be ``None`` when:
      - the corresponding ``include_*`` flag is False, or
      - ``strategy_wiring`` is not importable (bootstrap not finished /
        test fixture / partial deploy), or
      - ``STRATEGIST_AGENT`` is not yet constructed, or
      - the snapshot accessor itself raises (defensive: any
        ``Exception`` is logged at DEBUG and converted to ``None`` so
        the response stays well-formed).

    All exceptions silenced — this is a pure-read aggregator and must
    match the ``never-raises`` contract of ``build_h_state_full_response``.
    回 ``(h1_dict, h3_dict)``；任一可能為 ``None`` 之原因：
      - 對應 ``include_*`` 旗標為 False；
      - ``strategy_wiring`` 不可匯入（bootstrap 未完成 / 測試 fixture /
        部分部署）；
      - ``STRATEGIST_AGENT`` 尚未建構；
      - snapshot accessor 自身拋例外（防禦：任何 ``Exception`` 於 DEBUG
        記錄並轉為 ``None``，回應仍 well-formed）。
    所有例外被吞 —— 本函式為純讀聚合器，須對齊
    ``build_h_state_full_response`` 的「永不 raise」合約。
    """
    h1_dict: Optional[dict[str, Any]] = None
    h3_dict: Optional[dict[str, Any]] = None

    if not (include_h1 or include_h3):
        # Caller filtered both out — short-circuit before paying import cost.
        # caller 雙重過濾 — 短路省匯入成本。
        return None, None

    try:
        # Lazy import: strategy_wiring is heavy (instantiates many agents +
        # singletons at import time). Importing here ensures unit tests that
        # only touch this module don't transitively boot the whole agent
        # stack.
        # 延遲匯入：strategy_wiring 重（匯入時實例化多個 agent + singleton）。
        # 此處延遲匯入確保只測本模組的 unit test 不會傳遞性啟動整個 agent stack。
        from . import strategy_wiring as _sw  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — broad: any import-time failure
        logger.debug(
            "_collect_h_snapshots: strategy_wiring not importable; "
            "falling back to empty shell. Reason: %s "
            "/ strategy_wiring 不可匯入；退回空殼",
            exc,
        )
        return None, None

    strategist = getattr(_sw, "STRATEGIST_AGENT", None)
    if strategist is None:
        # Bootstrap raced or wiring partially complete — empty shell fallback.
        # bootstrap race 或 wiring 部分完成 — 退回空殼。
        logger.debug(
            "_collect_h_snapshots: STRATEGIST_AGENT not yet wired; "
            "falling back to empty shell "
            "/ STRATEGIST_AGENT 尚未接線；退回空殼"
        )
        return None, None

    if include_h1:
        h1_dict = _safe_snapshot(strategist, "_h1_gate", "get_h1_snapshot")
    if include_h3:
        h3_dict = _safe_snapshot(strategist, "_model_router", "get_h3_snapshot")

    return h1_dict, h3_dict


def _safe_snapshot(
    parent: Any,
    attr_name: str,
    method_name: str,
) -> Optional[dict[str, Any]]:
    """Defensively call ``parent.<attr_name>.<method_name>()``.
    防禦式呼叫 ``parent.<attr_name>.<method_name>()``。

    Returns the snapshot dict on success, ``None`` when:
      - the attribute is missing (singleton schema drift),
      - the method is absent (Phase 1 component without Phase 2 upgrade),
      - the call raises (snapshot bug must NOT crash the IPC handler).

    回傳 snapshot dict（成功）或 ``None``（屬性缺失 / 方法缺席 / 呼叫拋例外）；
    snapshot bug 絕不可使 IPC handler 崩潰。
    """
    try:
        sub = getattr(parent, attr_name, None)
        if sub is None:
            logger.debug(
                "_safe_snapshot: %s.%s is None / 屬性為 None",
                type(parent).__name__, attr_name,
            )
            return None
        method = getattr(sub, method_name, None)
        if method is None or not callable(method):
            logger.debug(
                "_safe_snapshot: %s.%s.%s missing or non-callable / "
                "方法缺失或不可呼叫",
                type(parent).__name__, attr_name, method_name,
            )
            return None
        result = method()
        if not isinstance(result, dict):
            logger.debug(
                "_safe_snapshot: %s.%s.%s returned non-dict %s; ignoring "
                "/ 方法回傳非 dict，忽略",
                type(parent).__name__, attr_name, method_name, type(result).__name__,
            )
            return None
        return result
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.debug(
            "_safe_snapshot: %s.%s.%s raised %s; falling back to None "
            "/ 方法呼叫拋例外，退回 None",
            type(parent).__name__, attr_name, method_name, exc,
        )
        return None


def build_h_state_full_response(
    include: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Phase 2: return real H1+H3 snapshots aggregated from STRATEGIST_AGENT.
    Phase 2：回傳從 STRATEGIST_AGENT 聚合的真實 H1+H3 snapshot。

    Args:
        include: Optional bucket-filter, e.g. ``["h1"]`` or ``["h3"]`` or
            ``["h1", "h3"]``. ``None`` (default) means "include all
            available buckets". Unknown bucket names are silently ignored
            (Phase 3+ will add ``h2`` / ``h4`` / ``h5``; passing them in
            Phase 2 is harmless).
            可選的桶過濾，如 ``["h1"]`` / ``["h3"]`` / ``["h1", "h3"]``。
            ``None``（預設）= 包含所有可用桶。未知桶名靜默忽略
            （Phase 3+ 會加 ``h2`` / ``h4`` / ``h5``；Phase 2 傳入無害）。

    Returns:
        Dict with keys ``version`` / ``fetched_at_ms`` / ``h_states`` /
        ``agent_states``. ``h_states`` populated with H1 + H3 dicts when
        env=1 and STRATEGIST_AGENT wired; ``version`` is 1 in that case.
        Otherwise empty buckets + ``version=0`` (Phase 1 fallback shape).
        含 ``version`` / ``fetched_at_ms`` / ``h_states`` / ``agent_states``
        鍵的 dict。env=1 且 STRATEGIST_AGENT 接線時 ``h_states`` 含 H1+H3
        dict、``version`` 為 1；否則空桶 + ``version=0``（Phase 1 fallback
        形狀）。

    Notes:
        - Pure-read function: no I/O, no env-write, no IPC. Singleton
          accessors only acquire local locks.
        - Always succeeds (cannot raise on any path).
        - Phase 3 adds ``h2`` / ``h4`` / ``h5`` from
          Layer2CostTracker + StrategistAgent stats; Phase 4 fills
          ``agent_states`` from the 5 agent singletons.
        - 純讀函式：無 I/O、無 env 寫入、無 IPC。Singleton accessor 僅取
          本地鎖。
        - 永遠成功（任何路徑皆不可能 raise）。
        - Phase 3 從 Layer2CostTracker + StrategistAgent stats 加
          ``h2`` / ``h4`` / ``h5``；Phase 4 從 5 個 agent singleton 填入
          ``agent_states``。
    """
    # Wall-clock ms timestamp (PA §4.2.1 ``fetched_at_ms`` field).
    # wall-clock ms 時間戳（PA §4.2.1 ``fetched_at_ms``）。
    fetched_at_ms = int(time.time() * 1000)

    # Defensive include validation. Phase 1 honoured the param without
    # filtering; Phase 2 filters real buckets. Tolerate non-list types
    # (e.g. operator passes a string by mistake) by treating as None.
    # 防禦式 include 驗證。Phase 1 收參但不過濾；Phase 2 對真實桶過濾。
    # 容忍非 list（如 operator 誤傳字串）視同 None。
    if include is not None and not isinstance(include, list):
        logger.debug(
            "build_h_state_full_response: include=%r is not a list; "
            "treating as None / include 非 list，視同 None",
            include,
        )
        include = None

    # Compute per-bucket include flags.
    # 計算各桶 include 旗標。
    if include is None:
        include_h1 = True
        include_h3 = True
    else:
        include_h1 = "h1" in include
        include_h3 = "h3" in include

    # Phase 2 short-circuit: env disabled → empty shell to keep dispatch
    # path cheap. We could still try to populate (snapshots are env-
    # independent reads), but PA §10.2 + §4.5 specify env-gated push
    # channel ↔ env-gated pull semantics for symmetry.
    # Phase 2 短路：env 關閉 → 空殼，保持 dispatch 路徑廉價。雖 snapshot
    # 本身與 env 無關，但 PA §10.2 + §4.5 規定 push 與 pull 通道對稱受
    # env 控制。
    if not _is_gateway_enabled():
        return {
            "version": _PHASE1_FALLBACK_VERSION,
            "fetched_at_ms": fetched_at_ms,
            _H_BUCKET_KEY: {},
            _AGENT_BUCKET_KEY: {},
        }

    # Aggregate snapshots (env enabled path). Either may return None on
    # singleton-not-wired race; we then drop that key from h_states.
    # 聚合 snapshot（env 開啟路徑）。任一在 singleton 未接線 race 下可能
    # 回 None；該 key 從 h_states 略掉。
    h1_dict, h3_dict = _collect_h_snapshots(include_h1, include_h3)

    h_states: dict[str, Any] = {}
    if h1_dict is not None:
        h_states["h1"] = h1_dict
    if h3_dict is not None:
        h_states["h3"] = h3_dict

    # Bump version when at least one bucket is real; stay at fallback
    # version when nothing populated (callers can detect "Phase 1 shape"
    # cheaply: ``version == 0 and not h_states and not agent_states``).
    # 至少一桶為真實時升 version；空殼時維持 fallback version（caller
    # 可廉價偵測 Phase 1 形狀：``version == 0 and not h_states and not
    # agent_states``）。
    if h_states:
        version = _PHASE2_VERSION
    else:
        version = _PHASE1_FALLBACK_VERSION

    return {
        "version": version,
        "fetched_at_ms": fetched_at_ms,
        _H_BUCKET_KEY: h_states,
        _AGENT_BUCKET_KEY: {},  # Phase 4 fills this bucket / Phase 4 填入
    }


__all__ = [
    "build_h_state_full_response",
]
