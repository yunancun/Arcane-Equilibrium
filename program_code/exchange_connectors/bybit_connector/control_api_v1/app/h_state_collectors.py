from __future__ import annotations

"""
G3-08-FUP-HSQ-SPLIT P2 — H-state / Agent-state snapshot collectors (sibling of h_state_query_handler).
G3-08-FUP-HSQ-SPLIT P2 — H 狀態 / Agent 狀態 snapshot 收集器（h_state_query_handler 姊妹模組）。

MODULE_NOTE (EN):
  Pure refactor split-out of the snapshot-collection helpers from
  ``h_state_query_handler.py`` (which had grown to 859 LOC, exceeding the
  CLAUDE.md §九 800-LOC warning threshold after the Wave E SINGLETON
  hardening commit ``b579dae`` added the dual ``sys.modules.get`` pattern
  to both ``_collect_h_snapshots`` and ``_collect_agent_snapshots``).

  Sibling pattern mirrors the ``cost_edge_advisor_boot.py`` split (see
  CLAUDE.md §九 ``CostEdgeAdvisorDbSlot`` singleton table entry); the
  parent ``h_state_query_handler.py`` keeps the public envelope assembly
  function ``build_h_state_full_response`` and the schema constants, and
  re-exports the four collector helpers from this module so:

    1. External callers / tests that already import via
       ``from app.h_state_query_handler import _safe_snapshot`` (or
       ``_safe_snapshot_self`` / ``_collect_agent_snapshots`` / etc.)
       continue to work without any patch site change.
    2. The 35 ``test_h_state_query_handler.py`` SINGLETON-fix assertions
       and the 108 same-session ``test_api_contract.py`` +
       ``test_h_state_query_handler.py`` tests stay green.
    3. The Wave E SINGLETON hardening (``sys.modules.get`` bypass of the
       CPython ``from PKG import SUB`` attribute precedence trap) moves
       atomically with the two collector functions — no test fixture
       rewrite needed.

  Public surface (re-exported by ``h_state_query_handler``):
    - ``_collect_h_snapshots``      — H1+H2+H3+H4+H5 snapshot tuple builder.
    - ``_collect_agent_snapshots``  — 5-Agent (strategist/guardian/analyst/
      executor/scout) snapshot dict builder.
    - ``_safe_snapshot``            — defensive ``parent.<attr>.<method>()``.
    - ``_safe_snapshot_self``       — defensive ``target.<method>()``.

  Design constraints honoured:
    - Zero production behaviour change (pure code move; identical bodies).
    - SINGLETON fix sys.modules.get pattern preserved verbatim in both
      collectors (line-for-line same lookup logic).
    - All four functions remain underscore-prefixed (private API), but
      are deliberately re-exported by the parent module for back-compat
      with the ~50+ existing test patch sites.

MODULE_NOTE (中):
  將原 ``h_state_query_handler.py`` 中的 snapshot 收集 helper 純重構
  抽出（Wave E SINGLETON 加固 commit ``b579dae`` 為兩個 collector 加入
  雙 ``sys.modules.get`` pattern 後，原檔達 859 LOC 超過 CLAUDE.md §九
  800 LOC 警告線）。

  Sibling pattern 鏡 ``cost_edge_advisor_boot.py`` 拆分（見 CLAUDE.md §九
  ``CostEdgeAdvisorDbSlot`` singleton 表條目）；父模組
  ``h_state_query_handler.py`` 保留公開的 envelope 組裝函式
  ``build_h_state_full_response`` 與 schema 常數，並從本模組 re-export
  四個 collector helper，達成：

    1. 既有外部 caller / test 透過
       ``from app.h_state_query_handler import _safe_snapshot``（或
       ``_safe_snapshot_self`` / ``_collect_agent_snapshots`` 等）
       匯入的路徑無須改動。
    2. 35 個 ``test_h_state_query_handler.py`` SINGLETON-fix 斷言與
       108 個 same-session（``test_api_contract.py`` +
       ``test_h_state_query_handler.py``）測試保持綠燈。
    3. Wave E SINGLETON 加固（用 ``sys.modules.get`` 繞過 CPython
       ``from PKG import SUB`` 屬性優先序陷阱）與兩個 collector 一同原
       子搬移 —— 不需改動 test fixture。

  公開接口（由 ``h_state_query_handler`` re-export）：
    - ``_collect_h_snapshots``      — H1+H2+H3+H4+H5 snapshot tuple 建構器。
    - ``_collect_agent_snapshots``  — 5-Agent（strategist/guardian/analyst/
      executor/scout）snapshot dict 建構器。
    - ``_safe_snapshot``            — 防禦式 ``parent.<attr>.<method>()``。
    - ``_safe_snapshot_self``       — 防禦式 ``target.<method>()``。

  設計約束遵守：
    - 0 production 行為改變（純代碼搬移；函式體完全相同）。
    - SINGLETON fix sys.modules.get pattern 在兩個 collector 內逐行保留
      （查找邏輯一字不差）。
    - 四個函式仍為 underscore-prefixed（private API），但刻意由父模組
      re-export 以維持 ~50+ 既有 test patch site 之向後相容。
"""

import logging
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)


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

    # G3-08-PHASE-FUP-IMPORT-PATH-LEAK (2026-04-28 PA RFC Option B):
    # Resolve strategy_wiring via ``sys.modules.get`` instead of
    # ``from . import strategy_wiring as _sw``. Background: CPython
    # ``from PKG import SUB`` semantic does ``getattr(PKG, "SUB")`` first
    # and only falls back to ``sys.modules["PKG.SUB"]`` if the attribute
    # is missing. Once any sibling test (e.g. test_api_contract.py:16
    # ``importlib.reload(main_legacy) + importlib.reload(main)``)
    # transitively imports strategy_wiring, the ``app.strategy_wiring``
    # attribute on the parent ``app`` package is permanently bound to the
    # real module. Subsequent fixtures that patch only
    # ``sys.modules["app.strategy_wiring"]`` therefore have ZERO effect on
    # this lookup → 35 ``test_h_state_query_handler.py`` assertions read
    # the real STRATEGIST_AGENT (zero stats) instead of the fake.
    # ``sys.modules.get`` bypasses the attribute precedence entirely.
    # Runtime semantics are equivalent: at uvicorn boot the wiring import
    # populates both ``sys.modules`` AND the package attribute in lock-step
    # → live lookup hits the real module via either path. Fail-soft path
    # below already covers the lookup-miss case.
    # G3-08-PHASE-FUP-IMPORT-PATH-LEAK（2026-04-28 PA RFC Option B）：
    # 改用 ``sys.modules.get`` 取代 ``from . import strategy_wiring``。
    # 背景：CPython ``from PKG import SUB`` 語意先 ``getattr(PKG, "SUB")``，
    # 缺才落 ``sys.modules["PKG.SUB"]``。任何 sibling test
    # （例 test_api_contract.py:16 ``importlib.reload(main_legacy/main)``）
    # 透過 transitive import 將 ``app.strategy_wiring`` 屬性永久綁到真模組
    # 後，僅 patch ``sys.modules["app.strategy_wiring"]`` 的 fixture 對此查找
    # 完全無效 → 35 個 ``test_h_state_query_handler.py`` assertion 讀到真
    # STRATEGIST_AGENT（all-zero stats），fake 失效。``sys.modules.get`` 完全
    # 繞過屬性優先序。Runtime 語意等價：uvicorn boot 時 wiring import 會同步
    # 填入 ``sys.modules`` 與 package attribute，live lookup 走任一路徑都
    # 命中真模組。下方 fail-soft path 已覆蓋 lookup-miss 案例。
    _sw = sys.modules.get("app.strategy_wiring")
    if _sw is None:
        logger.debug(
            "_collect_h_snapshots: app.strategy_wiring not in sys.modules; "
            "falling back to empty shell "
            "/ sys.modules 缺 app.strategy_wiring；退回空殼"
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
        h1_dict = _safe_snapshot_self(strategist, "get_h1_snapshot")
    if include_h3:
        h3_dict = _safe_snapshot_self(strategist, "get_h3_snapshot")
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

    G3-08 Phase 4 Sub-task 4-1 lands the ``strategist`` key; Sub-task 4-2
    lands ``guardian``; subsequent Sub-tasks 4-3 / 4-4 / 4-5 incrementally
    fill ``analyst`` / ``executor`` / ``scout``. Pattern (PA RFC §3.2
    Option B): return ``dict[str, Optional[dict]]`` rather than a tuple so
    that adding a sub-task arm is purely additive — no caller signature
    break across the multi-agent merge wave.
    G3-08 Phase 4 Sub-task 4-1 落 ``strategist`` 鍵；Sub-task 4-2 落
    ``guardian``；後續 4-3/4/5 依序填 ``analyst`` / ``executor`` /
    ``scout``。Pattern（PA RFC §3.2 Option B）：回 ``dict`` 而非 tuple，
    新增 sub-task arm 為純加性，跨 sub-task 合併不破壞 caller signature。

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

    # G3-08-PHASE-FUP-IMPORT-PATH-LEAK (2026-04-28 PA RFC Option B):
    # Same sys.modules.get rationale as _collect_h_snapshots above —
    # bypass CPython ``from PKG import SUB`` attribute precedence so test
    # fixtures patching only ``sys.modules["app.strategy_wiring"]`` take
    # effect. Runtime semantics equivalent (sys.modules + package attr
    # populated in lock-step at uvicorn boot); fail-soft path covers miss.
    # G3-08-PHASE-FUP-IMPORT-PATH-LEAK（2026-04-28 PA RFC Option B）：
    # 同 _collect_h_snapshots — 用 sys.modules.get 繞過 CPython
    # ``from PKG import SUB`` 屬性優先序，讓僅 patch
    # ``sys.modules["app.strategy_wiring"]`` 的 fixture 生效。Runtime
    # 語意等價（uvicorn boot 時 sys.modules + package attr 同步填入）；
    # fail-soft path 已覆蓋 miss。
    _sw = sys.modules.get("app.strategy_wiring")
    if _sw is None:
        logger.debug(
            "_collect_agent_snapshots: app.strategy_wiring not in sys.modules; "
            "falling back to empty result "
            "/ sys.modules 缺 app.strategy_wiring；退回空 dict"
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

    if include_guardian:
        # G3-08 Phase 4 Sub-task 4-2: pull GuardianAgent.get_guardian_snapshot
        # via _safe_snapshot_self — accessor lives on the agent itself
        # (same SSOT pattern as Strategist 4-1).
        # G3-08 Phase 4 Sub-task 4-2：透過 _safe_snapshot_self 拉取
        # GuardianAgent.get_guardian_snapshot — accessor 在 agent 自身
        # （與 Strategist 4-1 同 SSOT pattern）。
        guardian = getattr(_sw, "GUARDIAN_AGENT", None)
        if guardian is not None:
            result["guardian"] = _safe_snapshot_self(
                guardian, "get_guardian_snapshot"
            )

    if include_analyst:
        # G3-08 Phase 4 Sub-task 4-3: pull AnalystAgent.get_analyst_snapshot
        # via _safe_snapshot_self — accessor on agent self (same pattern as 4-1).
        # ANALYST_AGENT may be ``None`` when strategy_wiring partial-init failed
        # (see strategy_wiring.py:444 fallback); result["analyst"] stays None
        # and is dropped from agent_states by the caller's comprehension.
        # G3-08 Phase 4 Sub-task 4-3：透過 _safe_snapshot_self 拉取
        # AnalystAgent.get_analyst_snapshot — accessor 在 agent 自身（與 4-1 同模式）。
        # ANALYST_AGENT 在 strategy_wiring 部分初始化失敗時為 ``None``
        # （見 strategy_wiring.py:444 fallback），此時 result["analyst"] 留 None，
        # caller 的 dict comprehension 將其丟出。
        analyst = getattr(_sw, "ANALYST_AGENT", None)
        if analyst is not None:
            result["analyst"] = _safe_snapshot_self(
                analyst, "get_analyst_snapshot"
            )

    if include_executor:
        # G3-08 Phase 4 Sub-task 4-4: pull ExecutorAgent.get_executor_snapshot
        # via _safe_snapshot_self — accessor lives on the agent itself
        # (same pattern as Sub-task 4-1 strategist). 9 fields per PA RFC §2.4.
        # G3-08 Phase 4 Sub-task 4-4：透過 _safe_snapshot_self 拉取
        # ExecutorAgent.get_executor_snapshot — accessor 在 agent 自身
        # （與 Sub-task 4-1 strategist 同模式），9 欄位（PA RFC §2.4）。
        executor = getattr(_sw, "EXECUTOR_AGENT", None)
        if executor is not None:
            result["executor"] = _safe_snapshot_self(
                executor, "get_executor_snapshot"
            )

    if include_scout:
        # G3-08 Phase 4 Sub-task 4-5: pull ScoutAgent.get_scout_snapshot via
        # _safe_snapshot_self — same caller-side pattern as Sub-task 4-1
        # (accessor on the agent itself). ScoutAgent class lives in
        # multi_agent_framework.py (not in a dedicated scout_agent.py module);
        # see G3-08-FUP-MAF-SPLIT for the future split-out backlog ticket
        # (per PA RFC §5.1 — defer to keep Sub-task 4-5 surface area minimal).
        # G3-08 Phase 4 Sub-task 4-5：透過 _safe_snapshot_self 拉取
        # ScoutAgent.get_scout_snapshot — 與 Sub-task 4-1 相同 caller-side
        # pattern（accessor 在 agent 自身）。ScoutAgent 類仍在
        # multi_agent_framework.py（無獨立 scout_agent.py）；拆分為未來工作
        # G3-08-FUP-MAF-SPLIT（依 PA RFC §5.1 — 維持 Sub-task 4-5 最小修改面）。
        scout = getattr(_sw, "SCOUT_AGENT", None)
        if scout is not None:
            result["scout"] = _safe_snapshot_self(
                scout, "get_scout_snapshot"
            )

    # G3-08 Phase 4 COMPLETE — 5 agents (strategist/guardian/analyst/executor/scout)
    # all wired. Phase 4 完整 = 5 個 agent 均已接線。

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


__all__ = [
    "_collect_h_snapshots",
    "_collect_agent_snapshots",
    "_safe_snapshot",
    "_safe_snapshot_self",
]
