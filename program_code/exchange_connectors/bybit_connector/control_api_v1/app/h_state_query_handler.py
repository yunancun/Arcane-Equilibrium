from __future__ import annotations

"""
G3-08 Phase 3 — H-state aggregator (Python query handler, real H1+H2+H3+H4+H5).
G3-08 Phase 3 — H 狀態聚合器（Python 查詢處理器，真實 H1+H2+H3+H4+H5）。

MODULE_NOTE (EN):
  Phase 3 Sub-task 3-3 upgrade — Phase 3 IS NOW COMPLETE. The
  ``query_h_state_full`` reverse IPC handler now aggregates all 5 H buckets
  (H1+H2+H3+H4+H5) when env=1 + STRATEGIST_AGENT wired. Builds on
  Sub-task 3-1 (H2 commit 8cd257e) and Sub-task 3-2 (H4 commit 71faf4c)
  by adding H5 cost_logging snapshot pulled from the ``Layer2CostTracker``
  instance reachable via ``STRATEGIST_AGENT.cost_tracker`` — same singleton
  source as H2 (BaseAgent.__init__ injects from
  ``strategy_wiring._COST_TRACKER_FOR_STRATEGIST``).

  Phase 4 (5-Agent state events) extends ``agent_states`` next; Phase 3
  per-H pattern (Sub-tasks 3-1/3-2/3-3) confirmed that the additive
  bucket-population approach scales — Phase 4 mirrors the same template.

  G3-08-FUP-HSQ-SPLIT P2 (2026-04-28): the four snapshot-collection
  helpers (``_collect_h_snapshots`` / ``_collect_agent_snapshots`` /
  ``_safe_snapshot`` / ``_safe_snapshot_self``) were extracted to the
  sibling module ``h_state_collectors.py`` after the Wave E SINGLETON
  hardening commit ``b579dae`` pushed this file to 859 LOC (above the
  CLAUDE.md §九 800 LOC warning threshold). They are re-exported below
  so all existing test patch sites
  (``from app.h_state_query_handler import _safe_snapshot``, etc.)
  keep working unchanged. The Wave E ``sys.modules.get`` SINGLETON fix
  moves atomically with the two collectors (line-for-line preserved in
  the new sibling).

  Per PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4 / §5 / §6:
    - Sub-task 3-1 (commit 8cd257e) landed H2; 3-2 (commit 71faf4c) landed
      H4; 3-3 (this commit) lands H5 — Phase 3 is now COMPLETE.
      Pattern is additive — adding ``h5`` bucket does not affect existing
      H1/H2/H3/H4 wiring or schema version semantics.
    - Schema version stays at 1 throughout Phase 3 (additive bucket
      population is forward-compat by design; only breaking shape changes
      bump version per Phase 2 contract).
    - G3-09 cost_edge_ratio (Rust hot-path) now UNBLOCKED: Rust
      ``HStateCache::query_h_state(cache, "h5", "cost_edge_ratio")`` returns
      the live ratio in ≤1ms p99 (DashMap shard lookup), enabling the
      proposed risk_gate downgrade-on-overspend trigger (cost_edge_ratio
      ≥ 0.8 → reduce position sizing).

  Phase 2/3 design intent (per PA design §10.2 + §5.1 + §7.1, Phase 3
  per RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4 / §5 / §6):
    - When the H1 / H2 / H3 / H4 / H5 singletons are reachable AND env is
      enabled (``OPENCLAW_H_STATE_GATEWAY == "1"``), populate
      ``h_states.h1``, ``h_states.h2``, ``h_states.h3``, ``h_states.h4``,
      and ``h_states.h5`` with the real snapshot dicts returned by
      ``H1ThoughtGate.get_h1_snapshot()`` /
      ``Layer2CostTracker.get_h2_snapshot()`` /
      ``ModelRouter.get_h3_snapshot()`` /
      ``StrategistAgent.get_h4_snapshot()`` /
      ``Layer2CostTracker.get_h5_snapshot()``. Bump the schema ``version``
      to 1.
    - When env is disabled OR singletons not yet wired (e.g. partial
      Phase 1 deploy / unit-test fixture) → fall back to the canonical
      Phase 1 empty shell (version=0, empty buckets). This preserves
      the contract that this handler **never raises** and is safe to
      call at any boot stage.
    - The reverse IPC route stays unconditionally registered (per
      Sub-task B); only the populated-vs-empty answer flips with env.
    - Forward-compatible: ``h_states`` and ``agent_states`` remain
      open dicts. Phase 3 added ``h2`` / ``h4`` / ``h5`` keys without
      changing the wire shape; Phase 4 will add five agent keys to
      ``agent_states``. Rust ``HStateCache`` uses ``serde(default)`` +
      ``HashMap<String, …>`` to absorb new fields without lock-step
      deploy (PA §5.2).

  Lazy import strategy (avoids bootstrap circulars):
    - ``h_state_collectors._collect_h_snapshots`` does NOT import
      ``strategy_wiring`` at module top level because ``strategy_wiring``
      itself imports ``h_state_invalidator`` and many other agent modules.
      Top-level import would deadlock the worker boot sequence under
      uvicorn --workers 4. Instead the collector lazily resolves via
      ``sys.modules.get("app.strategy_wiring")`` (Wave E SINGLETON fix)
      and silences any ``ImportError`` / ``AttributeError`` to keep the
      empty-shell contract.

  Thread safety:
    - ``H1ThoughtGate.get_h1_snapshot()`` and
      ``ModelRouter.get_h3_snapshot()`` each acquire only their own
      local locks; no cross-module locking, no deadlock risk.
    - Pure read; multiple concurrent ``query_h_state_full`` IPC calls
      (e.g. Rust poller + GUI healthcheck) are safe.

  Schema returned (PA §5.1 / §4.2.1, Phase 3 COMPLETE — 5 H buckets):

      {
        "version":       1,                   # Phase 2/3 (was 0 in Phase 1)
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      {
          "h1": { ... real H1ThoughtGate snapshot ... },
          "h2": { ... real Layer2CostTracker H2 snapshot ... },
          "h3": { ... real ModelRouter snapshot ... },
          "h4": { ... real StrategistAgent H4 snapshot ... },
          "h5": { ... real Layer2CostTracker H5 snapshot ... },
        },
        "agent_states":  { },                 # filled by Phase 4
      }

  When H1/H2/H3/H4/H5 singletons unreachable or env=0:

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
  G3-08 Phase 3 Sub-task 3-3 升級 —— Phase 3 至此 COMPLETE。
  ``query_h_state_full`` reverse IPC handler 在 env=1 + STRATEGIST_AGENT
  接線時聚合全部 5 個 H 桶（H1+H2+H3+H4+H5）。基於 Sub-task 3-1
  （H2 commit 8cd257e）與 Sub-task 3-2（H4 commit 71faf4c）新增 H5
  cost_logging snapshot，從 ``STRATEGIST_AGENT.cost_tracker``
  （Layer2CostTracker 實例）拉取 —— 與 H2 同一 singleton source
  （BaseAgent.__init__ 從 ``strategy_wiring._COST_TRACKER_FOR_STRATEGIST``
  注入）。

  Phase 4（5-Agent 狀態事件）下一步擴充 ``agent_states``；Phase 3 的
  per-H pattern（Sub-tasks 3-1/3-2/3-3）證明加性桶填補方法可擴展 ——
  Phase 4 沿用相同模板。

  G3-08-FUP-HSQ-SPLIT P2（2026-04-28）：四個 snapshot 收集 helper
  （``_collect_h_snapshots`` / ``_collect_agent_snapshots`` /
  ``_safe_snapshot`` / ``_safe_snapshot_self``）在 Wave E SINGLETON
  加固 commit ``b579dae`` 將本檔推升到 859 LOC（超過 CLAUDE.md §九
  800 LOC 警告線）後，已抽到 sibling 模組 ``h_state_collectors.py``。
  下方仍 re-export，所有既有 test patch site
  （``from app.h_state_query_handler import _safe_snapshot`` 等）
  無須改動繼續工作。Wave E ``sys.modules.get`` SINGLETON fix 與兩個
  collector 一同原子搬移（在新 sibling 內逐行保留）。

  依 PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4 / §5 / §6：
    - Sub-task 3-1（commit 8cd257e）落 H2；3-2（commit 71faf4c）落 H4；
      3-3（本 commit）落 H5 —— Phase 3 COMPLETE。pattern 為加性 ——
      新增 ``h5`` 桶不影響既有 H1/H2/H3/H4 接線或 schema 版本語意。
    - schema 版本 Phase 3 全程維持 1（加性桶填補設計上 forward-compat；
      只有破壞性形狀改動才升 version，per Phase 2 contract）。
    - G3-09 cost_edge_ratio（Rust hot-path）現 UNBLOCKED：Rust
      ``HStateCache::query_h_state(cache, "h5", "cost_edge_ratio")`` 可
      ≤1ms p99 取得即時 ratio（DashMap shard lookup），啟用提案中的
      risk_gate 過支降頻觸發（cost_edge_ratio ≥ 0.8 → 縮倉）。

  Phase 2/3 設計意圖（對齊 PA design §10.2 + §5.1 + §7.1，Phase 3 per
  RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4 / §5 / §6）：
    - H1 / H2 / H3 / H4 / H5 singleton 可達且 env 開啟
      （``OPENCLAW_H_STATE_GATEWAY == "1"``）時，將 ``h_states.h1`` /
      ``h_states.h2`` / ``h_states.h3`` / ``h_states.h4`` / ``h_states.h5``
      填入 ``H1ThoughtGate.get_h1_snapshot()`` /
      ``Layer2CostTracker.get_h2_snapshot()`` /
      ``ModelRouter.get_h3_snapshot()`` /
      ``StrategistAgent.get_h4_snapshot()`` /
      ``Layer2CostTracker.get_h5_snapshot()`` 的真實 snapshot dict；
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
    - ``h_state_collectors._collect_h_snapshots`` 模組頂層不 import
      ``strategy_wiring``，因為 ``strategy_wiring`` 自身 import
      ``h_state_invalidator`` 與多個 agent 模組；頂層匯入會在
      uvicorn --workers 4 worker boot 序列死鎖。改在 collector 內透過
      ``sys.modules.get("app.strategy_wiring")``（Wave E SINGLETON fix）
      延遲解析並吞 ``ImportError`` / ``AttributeError`` 以維持空殼合約。

  線程安全：
    - ``H1ThoughtGate.get_h1_snapshot()`` 與
      ``ModelRouter.get_h3_snapshot()`` 各自只取自身本地鎖；無跨模組鎖，
      無死鎖風險。
    - 純讀取；並發 ``query_h_state_full`` IPC（如 Rust poller + GUI
      healthcheck）安全。

  回傳 schema（PA §5.1 / §4.2.1，Phase 3 COMPLETE — 5 H 桶）：

      {
        "version":       1,                   # Phase 2/3（Phase 1 為 0）
        "fetched_at_ms": <wall-clock ms>,
        "h_states":      {
          "h1": { ... 真實 H1ThoughtGate snapshot ... },
          "h2": { ... 真實 Layer2CostTracker H2 snapshot ... },
          "h3": { ... 真實 ModelRouter snapshot ... },
          "h4": { ... 真實 StrategistAgent H4 snapshot ... },
          "h5": { ... 真實 Layer2CostTracker H5 snapshot ... },
        },
        "agent_states":  { },                 # Phase 4 填入
      }

  H1/H2/H3/H4/H5 singleton 不可達或 env=0：

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

# G3-08-FUP-HSQ-SPLIT P2 (2026-04-28): re-export the four snapshot-collection
# helpers from the sibling ``h_state_collectors`` module so that all
# existing test patch sites — e.g.
#   ``from app.h_state_query_handler import _safe_snapshot``
#   ``from app.h_state_query_handler import _collect_agent_snapshots``
# — continue to work without modification. The Wave E ``sys.modules.get``
# SINGLETON fix lives inside the collectors and moved atomically with them.
# G3-08-FUP-HSQ-SPLIT P2（2026-04-28）：從 sibling ``h_state_collectors``
# 模組 re-export 四個 snapshot 收集 helper，使既有 test patch site
# （如 ``from app.h_state_query_handler import _safe_snapshot`` /
# ``_collect_agent_snapshots``）無須改動繼續運作。Wave E
# ``sys.modules.get`` SINGLETON fix 在 collector 內，與 collector 一同原子
# 搬移。
from .h_state_collectors import (  # noqa: F401 — re-export for back-compat
    _collect_agent_snapshots,
    _collect_h_snapshots,
    _safe_snapshot,
    _safe_snapshot_self,
)

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


def build_h_state_full_response(
    include: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Phase 3 COMPLETE: return real H1+H2+H3+H4+H5 snapshots from STRATEGIST_AGENT.
    Phase 3 COMPLETE：回傳從 STRATEGIST_AGENT 聚合的真實 H1+H2+H3+H4+H5 snapshot。

    Args:
        include: Optional bucket-filter, e.g. ``["h1"]`` or ``["h3"]`` or
            ``["h1", "h3", "h4", "h5"]``. ``None`` (default) means "include all
            available buckets". Unknown bucket names are silently ignored
            (Phase 4 will add ``agent_states.<agent>``; passing them as
            bucket names now is harmless).
            可選的桶過濾，如 ``["h1"]`` / ``["h3"]`` /
            ``["h1", "h3", "h4", "h5"]``。``None``（預設）= 包含所有可用桶。
            未知桶名靜默忽略（Phase 4 會加 ``agent_states.<agent>``；
            現在傳無害）。

    Returns:
        Dict with keys ``version`` / ``fetched_at_ms`` / ``h_states`` /
        ``agent_states``. ``h_states`` populated with H1 + H2 + H3 + H4 + H5
        dicts when env=1 and STRATEGIST_AGENT wired; ``version`` is 1.
        Otherwise empty buckets + ``version=0`` (Phase 1 fallback shape).
        含 ``version`` / ``fetched_at_ms`` / ``h_states`` / ``agent_states``
        鍵的 dict。env=1 且 STRATEGIST_AGENT 接線時 ``h_states`` 含
        H1+H2+H3+H4+H5 dict、``version`` 為 1；否則空桶 + ``version=0``
        （Phase 1 fallback 形狀）。

    Notes:
        - Pure-read function: no I/O, no env-write, no IPC. Singleton
          accessors only acquire local locks (or no locks for H5 — see
          ``Layer2CostTracker.get_h5_snapshot`` thread-safety analysis).
        - Always succeeds (cannot raise on any path).
        - Phase 3 Sub-task 3-3 (this commit) lands ``h5`` from
          ``Layer2CostTracker.get_h5_snapshot`` — Phase 3 is COMPLETE.
        - Phase 4 will fill ``agent_states`` from the 5 agent singletons
          (Strategist / Guardian / Analyst / Executor / Scout).
        - 純讀函式：無 I/O、無 env 寫入、無 IPC。Singleton accessor 僅取
          本地鎖（H5 不取鎖 —— 見 ``Layer2CostTracker.get_h5_snapshot``
          線程安全分析）。
        - 永遠成功（任何路徑皆不可能 raise）。
        - Phase 3 Sub-task 3-3（本 commit）落 ``h5``（從
          ``Layer2CostTracker.get_h5_snapshot``）—— Phase 3 COMPLETE。
        - Phase 4 從 5 個 agent singleton 填入 ``agent_states``。
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
        include_h2 = True
        include_h4 = True
        include_h5 = True
        # G3-08 Phase 4: default include selects every available agent bucket;
        # Sub-task 4-1 fills strategist, 4-2 fills guardian, 4-3/4/5 fill the
        # rest. Until those land the unfilled keys silently degrade to None
        # and are dropped from agent_states (same shape as H bucket missing).
        # G3-08 Phase 4：預設 include 涵蓋全部 agent 桶；Sub-task 4-1 填
        # strategist，4-2 填 guardian，其他 3 個由後續 sub-task 填，未 land
        # 前靜默退化為 None 並從 agent_states 丟出（與 H 桶缺席同形狀）。
        include_strategist = True
        include_guardian = True
        include_analyst = True
        include_executor = True
        include_scout = True
    else:
        include_h1 = "h1" in include
        include_h3 = "h3" in include
        include_h2 = "h2" in include
        include_h4 = "h4" in include
        include_h5 = "h5" in include
        include_strategist = "strategist" in include
        include_guardian = "guardian" in include
        include_analyst = "analyst" in include
        include_executor = "executor" in include
        include_scout = "scout" in include

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

    # Aggregate snapshots (env enabled path). Any may return None on
    # singleton-not-wired race; we then drop that key from h_states.
    # 聚合 snapshot（env 開啟路徑）。任一在 singleton 未接線 race 下可能
    # 回 None；該 key 從 h_states 略掉。
    h1_dict, h3_dict, h2_dict, h4_dict, h5_dict = _collect_h_snapshots(
        include_h1, include_h3, include_h2, include_h4, include_h5,
    )

    h_states: dict[str, Any] = {}
    if h1_dict is not None:
        h_states["h1"] = h1_dict
    if h2_dict is not None:
        h_states["h2"] = h2_dict
    if h3_dict is not None:
        h_states["h3"] = h3_dict
    if h4_dict is not None:
        h_states["h4"] = h4_dict
    if h5_dict is not None:
        h_states["h5"] = h5_dict

    # G3-08 Phase 4 Sub-task 4-1/4-2: aggregate 5-Agent state snapshots.
    # Returns a dict keyed by canonical agent name; ``None`` value signals
    # "not available" (sub-task not yet landed / singleton not wired /
    # accessor raised) and is dropped from the wire response below.
    # G3-08 Phase 4 Sub-task 4-1/4-2：聚合 5-Agent 狀態 snapshot。
    # dict key = canonical agent name；``None`` 表示「不可得」（sub-task
    # 未 land / singleton 未接線 / accessor 拋例外），下方從 wire response 丟出。
    agent_dict_map = _collect_agent_snapshots(
        include_strategist=include_strategist,
        include_guardian=include_guardian,
        include_analyst=include_analyst,
        include_executor=include_executor,
        include_scout=include_scout,
    )
    agent_states: dict[str, Any] = {
        k: v for k, v in agent_dict_map.items() if v is not None
    }

    # Bump version when at least one bucket is real; stay at fallback
    # version when nothing populated (callers can detect "Phase 1 shape"
    # cheaply: ``version == 0 and not h_states and not agent_states``).
    # G3-08 Phase 4: agent_states now also counts toward "real" so a
    # standalone agent_states (e.g. include=["strategist"] only) lifts
    # version to 1 even with empty h_states.
    # 至少一桶為真實時升 version；空殼時維持 fallback version。
    # G3-08 Phase 4：agent_states 也計入「真實」，故僅含 agent_states
    # （例：include=["strategist"]）也會將 version 升至 1。
    if h_states or agent_states:
        version = _PHASE2_VERSION
    else:
        version = _PHASE1_FALLBACK_VERSION

    return {
        "version": version,
        "fetched_at_ms": fetched_at_ms,
        _H_BUCKET_KEY: h_states,
        _AGENT_BUCKET_KEY: agent_states,
    }


__all__ = [
    "build_h_state_full_response",
]
