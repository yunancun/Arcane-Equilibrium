"""Shared fixtures for h_state_query_handler tests."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time
import types
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.h_state_query_handler import build_h_state_full_response  # noqa: E402


# ── Helpers / 輔助 ──


class _FakeH1Gate:
    """Minimal stub matching H1ThoughtGate.get_h1_snapshot contract."""

    def __init__(self, snapshot=None, raises=None):
        self._snapshot = snapshot if snapshot is not None else {
            "total_decisions": 7,
            "ai_calls_allowed": 4,
            "budget_skip": 1,
            "complexity_skip": 1,
            "cooldown_skip": 1,
            "cooldown_dict_size": 3,
            "budget_remaining_pct": 42.0,
        }
        self._raises = raises

    def get_h1_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeModelRouter:
    """Minimal stub matching ModelRouter.get_h3_snapshot contract."""

    def __init__(self, snapshot=None, raises=None):
        self._snapshot = snapshot if snapshot is not None else {
            "total_routes": 12,
            "l1_9b_count": 6,
            "l1_27b_count": 4,
            "l1_5_count": 1,
            "l2_count": 1,
            "budget_denied_count": 0,
            "l2_cache_hit": 2,
            "l2_cache_expired": 0,
            "l2_cache_stored": 1,
            "cache_size": 5,
        }
        self._raises = raises

    def get_h3_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeCostTracker:
    """Minimal stub matching Layer2CostTracker.get_h2_snapshot + get_h5_snapshot contracts.

    Schema mirrors Rust H2BudgetState (3 fields) + H5CostStats (4 fields).

    Phase 3 Sub-task 3-3 adds opt-in ``with_h5`` / ``h5_snapshot`` /
    ``h5_raises`` to drive the cost_tracker.get_h5_snapshot accessor.
    Default ``with_h5=False`` mirrors the silent-skip default — Phase 3
    Sub-task 3-1 / 3-2 tests stay unaffected (they don't expect h5 in
    h_states because their fixture skipped binding get_h5_snapshot).
    Phase 3 Sub-task 3-3 加 opt-in ``with_h5`` 等參數。預設 with_h5=False
    與靜默跳過預設對齊 —— Sub-task 3-1 / 3-2 既有測試（fixture 未綁
    get_h5_snapshot，不期望 h5 在 h_states）不受影響。
    """

    def __init__(
        self,
        snapshot=None,
        raises=None,
        with_h5=False,
        h5_snapshot=None,
        h5_raises=None,
    ):
        self._snapshot = snapshot if snapshot is not None else {
            "daily_remaining_usd": 1.75,
            "hard_cap_usd": 2.0,
            "adaptive_multiplier": 0.85,
        }
        self._raises = raises
        # Phase 3 Sub-task 3-3 H5 stub state.
        # Phase 3 Sub-task 3-3 H5 stub 狀態。
        self._h5_snapshot = h5_snapshot if h5_snapshot is not None else {
            "ai_spend_7d_usd": 0.42,
            "paper_pnl_7d_usd": 0.84,
            "cost_edge_ratio": 2.0,
            "data_days": 5,
        }
        self._h5_raises = h5_raises
        if with_h5:
            # Bind get_h5_snapshot only when opted in — preserves Sub-task
            # 3-1 / 3-2 test fixture semantics where get_h5_snapshot is
            # absent and the silent-skip path triggers.
            # 僅在 opt-in 時綁定 get_h5_snapshot —— 保留 Sub-task 3-1 / 3-2
            # 測試 fixture 語意（get_h5_snapshot 缺席 + 靜默跳過路徑）。
            def _get_h5(_self=self):
                if _self._h5_raises is not None:
                    raise _self._h5_raises
                return _self._h5_snapshot
            self.get_h5_snapshot = _get_h5

    def get_h2_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeStrategist:
    """Minimal stub mirroring strategy_wiring.STRATEGIST_AGENT shape.

    Phase 3 Sub-task 3-1 adds ``cost_tracker`` (public attribute, no
    underscore prefix — matches BaseAgent.__init__ contract).
    Phase 3 Sub-task 3-2 adds opt-in ``with_h4`` / ``h4_snapshot`` /
    ``h4_raises`` to drive the strategist-self ``get_h4_snapshot()``
    accessor (caller-side counters, distinct from H1/H3 sub-attribute
    pattern). Default ``with_h4=False`` mirrors ``cost_tracker=None``
    silent-skip default — Phase 2 / Sub-task 3-1 tests stay unaffected.
    Phase 3 Sub-task 3-2 加 opt-in ``with_h4`` 等參數。預設 with_h4=False
    與 cost_tracker=None 預設靜默跳過對齊 — Phase 2 / Sub-task 3-1 測試
    不受影響。
    """

    def __init__(
        self,
        h1_gate=None,
        model_router=None,
        cost_tracker=None,
        with_h4=False,
        h4_snapshot=None,
        h4_raises=None,
        with_strategist_snapshot=False,
        strategist_snapshot=None,
        strategist_snapshot_raises=None,
    ):
        self._h1_gate = h1_gate
        self._model_router = model_router
        # Public attribute (no underscore) — mirrors BaseAgent.cost_tracker.
        # 公開屬性（無底線）—— 鏡射 BaseAgent.cost_tracker。
        self.cost_tracker = cost_tracker
        # Phase 3 Sub-task 3-2: H4 snapshot is on the strategist itself.
        # Default with_h4=False — opt in so existing Phase 2 tests
        # (which expect h_states without h4) keep their semantics.
        # Phase 3 Sub-task 3-2：H4 snapshot 在 strategist 自身。
        # 預設 with_h4=False — opt in，避免 Phase 2 測試（預期 h_states 無 h4）
        # 語義被破壞。
        self._h4_snapshot = h4_snapshot if h4_snapshot is not None else {
            "validation_fail": 3,
            "validation_pass": 17,
        }
        self._h4_raises = h4_raises
        if with_h4:
            def _get(_self=self):
                if _self._h4_raises is not None:
                    raise _self._h4_raises
                return _self._h4_snapshot
            # Bind as instance method
            self.get_h4_snapshot = _get

        # G3-08 Phase 4 Sub-task 4-1: Strategist agent_state snapshot accessor.
        # Default with_strategist_snapshot=False — opt-in, mirrors with_h4 pattern,
        # so Phase 1-3 tests stay unaffected (they don't expect agent_states.strategist).
        # G3-08 Phase 4 Sub-task 4-1：Strategist agent_state snapshot 存取器。
        # 預設 with_strategist_snapshot=False — opt-in，與 with_h4 同模式，
        # Phase 1-3 測試（不期望 agent_states.strategist）不受影響。
        self._strategist_snapshot = strategist_snapshot if strategist_snapshot is not None else {
            "intel_received": 11,
            "intel_evaluated": 7,
            "intents_produced": 3,
            "intents_shadow_logged": 4,
            "evaluations_rejected": 2,
            "ai_evaluations": 5,
            "heuristic_evaluations": 2,
            "errors": 0,
            "pending_intents": 1,
            "emergency_mode_active": 0,
            "cognitive_modulator_connected": 1,
        }
        self._strategist_snapshot_raises = strategist_snapshot_raises
        if with_strategist_snapshot:
            def _get_strategist(_self=self):
                if _self._strategist_snapshot_raises is not None:
                    raise _self._strategist_snapshot_raises
                return _self._strategist_snapshot
            self.get_strategist_snapshot = _get_strategist

    def get_h1_snapshot(self):
        return self._h1_gate.get_h1_snapshot()

    def get_h3_snapshot(self):
        return self._model_router.get_h3_snapshot()


class _FakeExecutor:
    """Minimal stub mirroring strategy_wiring.EXECUTOR_AGENT shape.

    G3-08 Phase 4 Sub-task 4-4: provides opt-in ``with_executor_snapshot`` /
    ``executor_snapshot`` / ``executor_snapshot_raises`` so the round-trip
    tests can exercise present / missing / raises paths without booting
    the real ExecutorAgent stack.

    G3-08 Phase 4 Sub-task 4-4：以 opt-in 方式提供 9 欄位 snapshot；
    支持 missing / present / raises 三種降級路徑驗證。
    """

    def __init__(
        self,
        with_executor_snapshot=False,
        executor_snapshot=None,
        executor_snapshot_raises=None,
    ):
        self._executor_snapshot = executor_snapshot if executor_snapshot is not None else {
            "intents_received": 11,
            "intents_deduped": 1,
            "executions_attempted": 8,
            "executions_success": 6,
            "executions_failed": 2,
            "total_slippage_bps": 47,
            "errors": 1,
            "recent_intent_id_size": 3,
            "shadow_mode": 1,
        }
        self._executor_snapshot_raises = executor_snapshot_raises
        if with_executor_snapshot:
            def _get_exec(_self=self):
                if _self._executor_snapshot_raises is not None:
                    raise _self._executor_snapshot_raises
                return _self._executor_snapshot
            self.get_executor_snapshot = _get_exec


class _FakeScout:
    """Minimal stub mirroring strategy_wiring.SCOUT_AGENT shape.

    Phase 4 Sub-task 4-5: caller-side ``get_scout_snapshot`` accessor lives
    on the agent itself (mirrors StrategistAgent Sub-task 4-1 pattern).
    Default ``with_scout_snapshot=False`` makes the method absent — used to
    test Sub-task 4-2/3/4 deploy scenarios where 4-5 hasn't landed yet.
    Phase 4 Sub-task 4-5：caller-side ``get_scout_snapshot`` 存取器在 agent
    自身（對齊 Strategist Sub-task 4-1）。預設 ``with_scout_snapshot=False``
    使方法缺席，用於測 Sub-task 4-2/3/4 部署但 4-5 未 land 情境。
    """

    def __init__(
        self,
        with_scout_snapshot=False,
        scout_snapshot=None,
        scout_snapshot_raises=None,
    ):
        self._scout_snapshot = scout_snapshot if scout_snapshot is not None else {
            "intel_produced": 13,
            "alerts_produced": 5,
            "scans_completed": 21,
            "intel_log_size": 7,
            "alert_log_size": 3,
        }
        self._scout_snapshot_raises = scout_snapshot_raises
        if with_scout_snapshot:
            def _get(_self=self):
                if _self._scout_snapshot_raises is not None:
                    raise _self._scout_snapshot_raises
                return _self._scout_snapshot
            self.get_scout_snapshot = _get


_SW_ATTR_MISSING = object()  # sentinel for "no attribute on app pkg" / 標記 app 上原無屬性


def _install_fake_strategy_wiring(strategist, guardian=None, analyst=None, executor=None, scout=None):
    """Replace ``app.strategy_wiring`` in sys.modules with a stub.

    G3-08 Phase 4 Sub-task 4-2/3/4/5 add optional ``guardian`` / ``analyst`` /
    ``executor`` / ``scout`` kw. Defaults None preserve prior call-site shapes.
    G3-08 Phase 4 Sub-task 4-2/3/4/5 增加 ``guardian`` / ``analyst`` /
    ``executor`` / ``scout`` 參數。預設 None 保持先前呼叫面向不變。

    G3-08-PHASE-FUP-IMPORT-PATH-LEAK (2026-04-28 PA RFC Option A):
    Patch BOTH ``sys.modules["app.strategy_wiring"]`` AND the
    ``app.strategy_wiring`` package attribute. Background: CPython
    ``from PKG import SUB`` semantic does ``getattr(PKG, "SUB")`` first;
    once ``test_api_contract.py:16`` calls
    ``importlib.reload(main_legacy)+importlib.reload(main)``, the real
    ``app.strategy_wiring`` module gets bound to the ``app`` package
    attribute permanently. Patching only sys.modules has zero effect on
    callers that resolve via ``from . import strategy_wiring``. We mirror
    the W3 fix dual-patch pattern (commit ``a2b660d``) so the fake is
    visible regardless of how the production code resolves the module.
    Note: production-side Option B (sys.modules.get in
    ``h_state_query_handler.py``) is the primary fix — Option A here is
    defense-in-depth for any future production code that still uses
    ``from . import``.
    G3-08-PHASE-FUP-IMPORT-PATH-LEAK（2026-04-28 PA RFC Option A）：
    同時 patch ``sys.modules["app.strategy_wiring"]`` 與
    ``app.strategy_wiring`` 套件屬性。背景：CPython ``from PKG import SUB``
    語意先 ``getattr(PKG, "SUB")``；一旦 ``test_api_contract.py:16`` 呼叫
    ``importlib.reload(main_legacy)+importlib.reload(main)``，真
    ``app.strategy_wiring`` 模組會永久綁到 ``app`` 套件屬性。僅 patch
    sys.modules 對走 ``from . import strategy_wiring`` 的 caller 完全無效。
    鏡 W3 fix 雙 patch pattern（commit ``a2b660d``），確保 fake 對所有
    解析路徑都可見。注意：production 端 Option B（``h_state_query_handler.py``
    內 sys.modules.get）是主修；本處 Option A 為 defense-in-depth，防未來
    新 production code 仍走 ``from . import``。

    Returns ``(prev_in_modules, prev_attr_or_sentinel)`` so caller can
    restore both states atomically.
    回傳 ``(prev_in_modules, prev_attr_or_sentinel)`` 供 caller 原子還原。
    """
    prev_in_modules = sys.modules.get("app.strategy_wiring")
    fake_mod = types.ModuleType("app.strategy_wiring")
    fake_mod.STRATEGIST_AGENT = strategist
    if guardian is not None:
        fake_mod.GUARDIAN_AGENT = guardian
    if analyst is not None:
        fake_mod.ANALYST_AGENT = analyst
    if executor is not None:
        fake_mod.EXECUTOR_AGENT = executor
    if scout is not None:
        fake_mod.SCOUT_AGENT = scout
    sys.modules["app.strategy_wiring"] = fake_mod

    # Dual-patch: also bind on parent ``app`` package attribute so
    # ``from . import strategy_wiring`` resolves to our stub. Capture
    # prior attr state via sentinel (None is a valid value).
    # 雙 patch：同時綁到 ``app`` 套件屬性，確保 ``from . import strategy_wiring``
    # 解析到我們的 stub。用 sentinel 記原屬性狀態（None 為合法值）。
    import app as _app_pkg  # noqa: PLC0415 — local import keeps top minimal
    prev_attr = getattr(_app_pkg, "strategy_wiring", _SW_ATTR_MISSING)
    _app_pkg.strategy_wiring = fake_mod  # type: ignore[attr-defined]

    return (prev_in_modules, prev_attr)



def _restore_strategy_wiring(prev):
    """Reverse :func:`_install_fake_strategy_wiring` for both sys.modules and
    the ``app.strategy_wiring`` attribute.

    Backward-compat: also accepts the legacy ``prev`` shape (a single module
    or ``None``) for any caller still using the pre-Option-A signature.
    向後相容：同時接受舊 ``prev`` 形狀（單一 module 或 ``None``）以兼容
    尚未升級 Option A 的呼叫端。
    """
    if isinstance(prev, tuple) and len(prev) == 2:
        prev_in_modules, prev_attr = prev
    else:  # legacy single-value form / 舊單值形式
        prev_in_modules, prev_attr = prev, _SW_ATTR_MISSING

    # Restore sys.modules first / 先還原 sys.modules
    if prev_in_modules is None:
        sys.modules.pop("app.strategy_wiring", None)
    else:
        sys.modules["app.strategy_wiring"] = prev_in_modules

    # Restore parent package attribute / 還原父套件屬性
    import app as _app_pkg  # noqa: PLC0415
    if prev_attr is _SW_ATTR_MISSING:
        # No attribute existed before — remove our injection.
        # 原本沒屬性 — 移除我們的注入。
        if hasattr(_app_pkg, "strategy_wiring"):
            try:
                delattr(_app_pkg, "strategy_wiring")
            except AttributeError:
                pass
    else:
        _app_pkg.strategy_wiring = prev_attr  # type: ignore[attr-defined]


# ── 1-4. Phase 1 fallback — empty-shell shape (env=0) ──

__all__ = [name for name in globals() if not name.startswith("__")]
