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
    include_h2: bool = False,
    include_h4: bool = False,
    include_h5: bool = False,
) -> tuple[
    Optional[dict[str, Any]],
    Optional[dict[str, Any]],
    Optional[dict[str, Any]],
    Optional[dict[str, Any]],
    Optional[dict[str, Any]],
]:
    """Lazy-import strategy_wiring and pull H1+H2+H3+H4+H5 snapshots.
    延遲 import strategy_wiring 並拉取 H1+H2+H3+H4+H5 snapshot。

    Phase 3 Sub-task 3-1: ``include_h2`` defaults to ``False`` to preserve
    Phase 2 callers' tuple shape compatibility — but ``build_h_state_full_response``
    always passes ``include_h2=True`` when env=1 + caller didn't filter
    h2 out, so production deployments always exercise the H2 path.
    Phase 3 Sub-task 3-2: ``include_h4`` likewise defaults to ``False``;
    same flow as H2 in production. H4 SSOT shape differs (caller-side on
    StrategistAgent itself, not a sub-attribute) — see ``include_h4`` block
    below for ``_safe_snapshot_self`` rationale.
    Phase 3 Sub-task 3-3: ``include_h5`` likewise defaults to ``False``.
    H5 SSOT = same Layer2CostTracker as H2 (cost_tracker.get_h5_snapshot()),
    but exposes a different lens (7d AI spend / paper PnL / cost_edge_ratio
    / data_days) — see ``include_h5`` block below for the deliberate
    Sub-task 3-1 vs 3-3 attribute reuse note.
    Phase 3 Sub-task 3-1：``include_h2`` 預設 ``False`` 維持 Phase 2 tuple 相容；
    production 由 ``build_h_state_full_response`` 一律傳 ``True``。
    Phase 3 Sub-task 3-2：``include_h4`` 同理；H4 SSOT 形狀不同（caller-side 在
    StrategistAgent 自身、非子屬性），見下方 ``include_h4`` 區塊
    ``_safe_snapshot_self`` 說明。
    Phase 3 Sub-task 3-3：``include_h5`` 同理。H5 SSOT 與 H2 同一 Layer2CostTracker
    （cost_tracker.get_h5_snapshot()），但暴露不同視角（7d AI 花費 / paper PnL /
    cost_edge_ratio / data_days）—— 見下方 ``include_h5`` 區塊刻意 Sub-task
    3-1 vs 3-3 屬性復用說明。

    Returns ``(h1_dict, h3_dict, h2_dict, h4_dict, h5_dict)`` — H2 / H4 / H5
    trail H1/H3 in tuple order to keep the Phase 2 positional contract for
    any caller that pre-existed Phase 3. Any element may be ``None`` when:
      - the corresponding ``include_*`` flag is False, or
      - ``strategy_wiring`` is not importable (bootstrap not finished /
        test fixture / partial deploy), or
      - ``STRATEGIST_AGENT`` is not yet constructed, or
      - for H2 / H5: ``STRATEGIST_AGENT.cost_tracker`` is ``None`` (e.g.
        Layer2CostTracker init failed — see ``strategy_wiring.py:163-170``
        ``_COST_TRACKER_FOR_STRATEGIST = None`` fail-open path), or
      - for H4: ``STRATEGIST_AGENT.get_h4_snapshot`` is missing (Phase 2
        deploy without Phase 3 Sub-task 3-2 land — silent skip preserves
        the never-raise contract), or
      - for H5: ``cost_tracker.get_h5_snapshot`` is missing (Sub-task 3-1
        deploy without 3-3 land — silent skip), or
      - the snapshot accessor itself raises (defensive: any
        ``Exception`` is logged at DEBUG and converted to ``None`` so
        the response stays well-formed).

    All exceptions silenced — this is a pure-read aggregator and must
    match the ``never-raises`` contract of ``build_h_state_full_response``.
    回 ``(h1_dict, h3_dict, h2_dict, h4_dict, h5_dict)``（H2 / H4 / H5 在
    tuple 末位以保 Phase 2 positional contract）；任一可能為 ``None`` 之原因：
      - 對應 ``include_*`` 旗標為 False；
      - ``strategy_wiring`` 不可匯入（bootstrap 未完成 / 測試 fixture /
        部分部署）；
      - ``STRATEGIST_AGENT`` 尚未建構；
      - 針對 H2 / H5：``STRATEGIST_AGENT.cost_tracker`` 為 ``None``（如
        Layer2CostTracker init 失敗 —— 見 ``strategy_wiring.py:163-170``
        ``_COST_TRACKER_FOR_STRATEGIST = None`` fail-open 路徑）；
      - 針對 H4：``STRATEGIST_AGENT.get_h4_snapshot`` 缺席（Phase 2 部署
        但 Phase 3 Sub-task 3-2 未 land —— 靜默跳過保 never-raise 合約）；
      - 針對 H5：``cost_tracker.get_h5_snapshot`` 缺席（Sub-task 3-1
        部署但 3-3 未 land —— 靜默跳過）；
      - snapshot accessor 自身拋例外（防禦：任何 ``Exception`` 於 DEBUG
        記錄並轉為 ``None``，回應仍 well-formed）。
    所有例外被吞 —— 本函式為純讀聚合器，須對齊
    ``build_h_state_full_response`` 的「永不 raise」合約。
    """
    h1_dict: Optional[dict[str, Any]] = None
    h3_dict: Optional[dict[str, Any]] = None
    h2_dict: Optional[dict[str, Any]] = None
    h4_dict: Optional[dict[str, Any]] = None
    h5_dict: Optional[dict[str, Any]] = None

    if not (include_h1 or include_h3 or include_h2 or include_h4 or include_h5):
        # Caller filtered all out — short-circuit before paying import cost.
        # caller 全部過濾 — 短路省匯入成本。
        return None, None, None, None, None

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
        return None, None, None, None, None

    strategist = getattr(_sw, "STRATEGIST_AGENT", None)
    if strategist is None:
        # Bootstrap raced or wiring partially complete — empty shell fallback.
        # bootstrap race 或 wiring 部分完成 — 退回空殼。
        logger.debug(
            "_collect_h_snapshots: STRATEGIST_AGENT not yet wired; "
            "falling back to empty shell "
            "/ STRATEGIST_AGENT 尚未接線；退回空殼"
        )
        return None, None, None, None, None

    if include_h1:
        h1_dict = _safe_snapshot(strategist, "_h1_gate", "get_h1_snapshot")  # G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE: deferred to G3-08-PHASE-4-STRATEGIST-SPLIT (de699df)
    if include_h3:
        h3_dict = _safe_snapshot(strategist, "_model_router", "get_h3_snapshot")  # G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE: deferred to G3-08-PHASE-4-STRATEGIST-SPLIT (de699df)
    if include_h2:
        # H2 SSOT = Layer2CostTracker, accessed via STRATEGIST_AGENT.cost_tracker
        # (set by BaseAgent.__init__ from the wiring-time injection in
        # strategy_wiring._COST_TRACKER_FOR_STRATEGIST). Public attribute
        # name `cost_tracker` (no underscore prefix) — distinct from the
        # `_h1_gate` / `_model_router` private composition pattern used
        # for H1/H3 because cost_tracker is shared/injected, not owned.
        # H2 SSOT = Layer2CostTracker，透過 STRATEGIST_AGENT.cost_tracker
        # 存取（由 BaseAgent.__init__ 接收 strategy_wiring 注入）。屬性名
        # `cost_tracker`（無底線前綴）—— 與 H1/H3 用 `_h1_gate` / `_model_router`
        # private composition pattern 不同，因 cost_tracker 為注入共享而非擁有。
        h2_dict = _safe_snapshot(strategist, "cost_tracker", "get_h2_snapshot")
    if include_h4:
        # G3-08 Phase 3 Sub-task 3-2: H4 stats live on the strategist itself
        # (caller-side counters _stats["h4_validation_*"]) because
        # ``h4_validator.validate_ai_output`` is a stateless pure function.
        # No nested attribute — pull directly via _safe_snapshot_self,
        # distinct from H1/H3 (sub-attribute owned) and H2 (sub-attribute
        # injected).
        # G3-08 Phase 3 Sub-task 3-2：H4 stats 在 strategist 自身（caller-side
        # 計數 _stats["h4_validation_*"]），因 ``h4_validator.validate_ai_output``
        # 為 stateless 純函式。無巢狀屬性 —— 透過 _safe_snapshot_self 直接拉
        # 取，與 H1/H3（擁有的子屬性）及 H2（注入的子屬性）皆不同。
        h4_dict = _safe_snapshot_self(strategist, "get_h4_snapshot")
    if include_h5:
        # G3-08 Phase 3 Sub-task 3-3: H5 SSOT = same Layer2CostTracker as
        # H2 (single tracker, multiple snapshot lenses). cost_tracker
        # exposes both ``get_h2_snapshot()`` (3-field budget gate state)
        # and ``get_h5_snapshot()`` (4-field cost_logging stats with the
        # cost_edge_ratio that unblocks G3-09). Reusing the cost_tracker
        # attribute means a single ``cost_tracker=None`` race drops BOTH
        # H2 and H5 buckets — acceptable per Sub-task 3-1's degradation
        # contract. Defensive ``_safe_snapshot`` continues to handle
        # missing-method (Sub-task 3-1 deploy without 3-3 land) silently.
        # G3-08 Phase 3 Sub-task 3-3：H5 SSOT 與 H2 同 Layer2CostTracker
        # （單一 tracker、多 snapshot 視角）。cost_tracker 同時暴露
        # ``get_h2_snapshot()``（3-field 預算閘狀態）與 ``get_h5_snapshot()``
        # （4-field cost_logging 統計，含解阻 G3-09 的 cost_edge_ratio）。
        # 復用 cost_tracker 屬性意味單一 ``cost_tracker=None`` race 會同時
        # 丟 H2 與 H5 桶 —— 對齊 Sub-task 3-1 降級合約可接受。防禦式
        # ``_safe_snapshot`` 仍能靜默處理 method missing（Sub-task 3-1 部署
        # 但 3-3 未 land）情境。
        h5_dict = _safe_snapshot(strategist, "cost_tracker", "get_h5_snapshot")

    return h1_dict, h3_dict, h2_dict, h4_dict, h5_dict


def _collect_agent_snapshots(
    include_strategist: bool = False,
    include_guardian: bool = False,
    include_analyst: bool = False,
    include_executor: bool = False,
    include_scout: bool = False,
) -> dict[str, Optional[dict[str, Any]]]:
    """Lazy-import strategy_wiring and pull 5-Agent state snapshots.
    延遲 import strategy_wiring 並拉取 5-Agent 狀態 snapshot。

    G3-08 Phase 4 Sub-task 4-1 lands the ``strategist`` key; subsequent
    Sub-tasks 4-2 / 4-3 / 4-4 / 4-5 incrementally fill ``guardian`` /
    ``analyst`` / ``executor`` / ``scout``. Pattern (PA RFC §3.2 Option B):
    return ``dict[str, Optional[dict]]`` rather than a tuple so that adding
    a sub-task arm is purely additive — no caller signature break across
    the multi-agent merge wave.
    G3-08 Phase 4 Sub-task 4-1 落 ``strategist`` 鍵；後續 4-2/3/4/5 sub-task
    依序填 ``guardian`` / ``analyst`` / ``executor`` / ``scout``。Pattern
    （PA RFC §3.2 Option B）：回 ``dict`` 而非 tuple，新增 sub-task arm 為
    純加性，跨 sub-task 合併不破壞 caller signature。

    Returns dict with five canonical agent keys; ``None`` value when:
      - the corresponding ``include_*`` flag is False, or
      - ``strategy_wiring`` is not importable (bootstrap not finished /
        test fixture / partial deploy), or
      - the singleton (e.g. ``STRATEGIST_AGENT``) is not yet wired, or
      - the snapshot accessor (e.g. ``get_strategist_snapshot``) is missing
        (sub-task not yet landed — silent skip preserves never-raise contract), or
      - the accessor itself raises (defensive: any ``Exception`` is logged
        at DEBUG and converted to ``None`` so the response stays well-formed).

    All exceptions silenced — pure-read aggregator, must match the
    ``never-raises`` contract of ``build_h_state_full_response``.
    回傳含 5 個 canonical agent key 的 dict；某 key 為 ``None`` 之原因：
      - 對應 ``include_*`` 旗標為 False；
      - ``strategy_wiring`` 不可匯入；
      - singleton（如 ``STRATEGIST_AGENT``）尚未接線；
      - snapshot accessor（如 ``get_strategist_snapshot``）缺席（對應
        sub-task 未 land — 靜默跳過保 never-raise 合約）；
      - accessor 拋例外（防禦：DEBUG 記錄、轉為 ``None``）。
    所有例外被吞 —— 對齊 ``build_h_state_full_response`` never-raise 合約。
    """
    result: dict[str, Optional[dict[str, Any]]] = {
        "strategist": None,
        "guardian": None,
        "analyst": None,
        "executor": None,
        "scout": None,
    }

    if not (
        include_strategist
        or include_guardian
        or include_analyst
        or include_executor
        or include_scout
    ):
        # Caller filtered all out — short-circuit before paying import cost.
        # caller 全部過濾 — 短路省匯入成本。
        return result

    try:
        # Lazy import: same rationale as _collect_h_snapshots — strategy_wiring
        # is heavy and must not boot transitively at module top.
        # 延遲匯入：與 _collect_h_snapshots 同理，strategy_wiring 重，
        # 不可在模組頂層傳遞性匯入。
        from . import strategy_wiring as _sw  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — broad: any import-time failure
        logger.debug(
            "_collect_agent_snapshots: strategy_wiring not importable; "
            "falling back to empty result. Reason: %s "
            "/ strategy_wiring 不可匯入；退回空 dict",
            exc,
        )
        return result

    if include_strategist:
        # G3-08 Phase 4 Sub-task 4-1: pull StrategistAgent.get_strategist_snapshot
        # via _safe_snapshot_self (sibling of _safe_snapshot) — accessor lives
        # on the agent itself, not a sub-attribute (mirrors H4 SSOT pattern).
        # G3-08 Phase 4 Sub-task 4-1：透過 _safe_snapshot_self 拉取
        # StrategistAgent.get_strategist_snapshot — accessor 在 agent 自身
        # 而非子屬性（與 H4 SSOT pattern 同模式）。
        strategist = getattr(_sw, "STRATEGIST_AGENT", None)
        if strategist is not None:
            result["strategist"] = _safe_snapshot_self(
                strategist, "get_strategist_snapshot"
            )

    # G3-08 Phase 4 Sub-task 4-2 / 4-3 / 4-4 / 4-5 will fill the remaining
    # four buckets (Guardian / Analyst / Executor / Scout). Their arms land
    # additively in this same function — no signature change required.
    # Sub-task 4-2/3/4/5 會於本 function 加入 Guardian / Analyst / Executor /
    # Scout arm；加性不改 signature。

    return result


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


def _safe_snapshot_self(
    target: Any,
    method_name: str,
) -> Optional[dict[str, Any]]:
    """Defensively call ``target.<method_name>()`` (no nested attribute).
    防禦式呼叫 ``target.<method_name>()``（無巢狀屬性）。

    Sibling of ``_safe_snapshot`` for the H4 case where the snapshot
    accessor lives directly on the target (e.g. ``StrategistAgent``)
    instead of on a sub-attribute. H4 stats are caller-side because
    ``h4_validator.validate_ai_output`` is stateless.

    Returns the snapshot dict on success, ``None`` when the method is
    missing / not callable / raises / returns non-dict. Same defensive
    contract as ``_safe_snapshot``: never raises.

    ``_safe_snapshot`` 的姊妹函式，給 H4 用（snapshot accessor 在 target
    自身而非子屬性）。H4 stats 由 caller 維護，因 ``h4_validator`` 無狀態。
    成功回 snapshot dict；方法缺失 / 不可呼叫 / 拋例外 / 回非 dict 皆回
    ``None``。永不 raise，與 ``_safe_snapshot`` 同合約。
    """
    try:
        method = getattr(target, method_name, None)
        if method is None or not callable(method):
            logger.debug(
                "_safe_snapshot_self: %s.%s missing or non-callable "
                "/ 方法缺失或不可呼叫",
                type(target).__name__, method_name,
            )
            return None
        result = method()
        if not isinstance(result, dict):
            logger.debug(
                "_safe_snapshot_self: %s.%s returned non-dict %s; ignoring "
                "/ 方法回傳非 dict，忽略",
                type(target).__name__, method_name, type(result).__name__,
            )
            return None
        return result
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.debug(
            "_safe_snapshot_self: %s.%s raised %s; falling back to None "
            "/ 方法呼叫拋例外，退回 None",
            type(target).__name__, method_name, exc,
        )
        return None


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
        # Sub-task 4-1 fills strategist now, 4-2/3/4/5 fill the rest. Until
        # those land the unfilled keys silently degrade to None and are
        # dropped from agent_states (same shape as H bucket missing).
        # G3-08 Phase 4：預設 include 涵蓋全部 agent 桶；Sub-task 4-1 填
        # strategist，其他 4 個由後續 sub-task 填，未 land 前靜默退化為 None
        # 並從 agent_states 丟出（與 H 桶缺席同形狀）。
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

    # G3-08 Phase 4 Sub-task 4-1: aggregate 5-Agent state snapshots.
    # Returns a dict keyed by canonical agent name; ``None`` value signals
    # "not available" (sub-task not yet landed / singleton not wired /
    # accessor raised) and is dropped from the wire response below.
    # G3-08 Phase 4 Sub-task 4-1：聚合 5-Agent 狀態 snapshot。
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
