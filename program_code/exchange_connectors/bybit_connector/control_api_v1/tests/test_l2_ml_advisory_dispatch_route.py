"""L2 P3b owed — /ml-advisory/dispatch route + _check_novelty placeholder union 測試。

覆蓋（對映 PA 2026-06-10 §A/§C.3 + E2 重點審查 2/3）：
  - route 安全面：operator-scope 第一行（viewer/缺 scope → 403）、capability 前綴 fail-closed
    400、evidence/context 互斥 400、inline-only（evidence 必為 dict，str path 被 pydantic 拒）。
  - E2E-0 單測鏡像：registry 內 capability enabled=false → dispatch admitted=false +
    admission_reason=capability_disabled + admission gate-seam 真被記（_record_admission_seam
    經 ledger writer.record_gate_seam）。
  - 薄投影：evidence → adapter context → orchestrator.dispatch_and_execute（trigger=manual，
    簽名零改動）。
  - _check_novelty placeholder union：先具體 symbol 後 placeholder、命中即停、fail-soft 不變。

測試隔離鐵則（0ce45a09 教訓）：autouse _no_real_db 攔 executor 模組的 db_pool 真連線 +
orchestrator/executor 的 D3 writer 注入 mock；conftest 全域池層降級為兜底。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_advisory_orchestrator as ORCH
from app import l2_capability_registry as REG
from app import l2_ml_advisory_executor as EXEC
from app import layer2_routes as LR
from app.learning_tier_gate import LearningTier


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """連線層隔離（鐵則）：攔 executor 的 db_pool.get_pg_conn；D3 writer 全注入 mock。"""
    fake_conn_cm = MagicMock()
    monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", lambda: fake_conn_cm)
    return fake_conn_cm


@pytest.fixture
def _mock_seam_writer(monkeypatch):
    """orchestrator 的 D3 ledger writer mock（斷言 _record_admission_seam 真被走）。"""
    writer = MagicMock()
    writer.record_gate_seam.return_value = {"ok": True}
    writer.record_l2_call.return_value = {"ok": True}
    monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: writer)
    return writer


def _viewer_actor():
    return SimpleNamespace(actor_id="viewer", roles={"viewer"}, scopes={"state:read"})


def _operator_actor():
    return SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"ai_budget:write"})


class _FakeTracker:
    def check_daily_budget(self):
        return True, 2.0


def _disabled_cap_orchestrator() -> ORCH.L2AdvisoryOrchestrator:
    """registry 注入單一 disabled 的 ml_advisory.diagnose_leak（鏡像 TOML 3 stanza
    enabled=false 的 deployed 狀態；0 enable）。"""
    cap = REG.L2Capability(
        capability_id="ml_advisory.diagnose_leak",
        enabled=False,  # ← 不碰 enable 鐵則：測的就是 disabled 短路
        min_tier="L1",
        model_tier="cloud_l2",
        lane="ml_backlog",
    )
    reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
    return ORCH.L2AdvisoryOrchestrator(
        cost_tracker=_FakeTracker(),
        registry_loader=lambda: reg,
        current_tier=LearningTier.L5,
        posture="Standard",
    )


def _req(**overrides) -> LR.MlAdvisoryDispatchRequest:
    base = dict(
        capability_id="ml_advisory.diagnose_leak",
        mode="diagnose_leak",
        coarse_subject="deployed_e2e_check",
    )
    base.update(overrides)
    return LR.MlAdvisoryDispatchRequest(**base)


# ═══════════════════════════════════════════════════════════════════════════════
# route 安全面（E2 重點審查 2）
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatchRouteAuth:
    def test_viewer_rejected_403(self):
        """viewer → 403（require_scope_and_operator 在任何 state 變更/dispatch 前攔）。"""
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.dispatch_ml_advisory(req=_req(), actor=_viewer_actor()))
        assert ei.value.status_code == 403

    def test_operator_without_scope_rejected_403(self):
        op_no_scope = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"state:read"})
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.dispatch_ml_advisory(req=_req(), actor=op_no_scope))
        assert ei.value.status_code == 403

    def test_auth_gate_is_first_statement_in_handler(self):
        """grep（鏡像既有 scope-gate 測試）：handler 真碼第一個呼叫是
        require_scope_and_operator(actor, "ai_budget:write")，先於 orchestrator/adapter。"""
        import inspect

        src = inspect.getsource(LR.dispatch_ml_advisory)
        gate = src.index('base.require_scope_and_operator(actor, "ai_budget:write")')
        assert gate < src.index("_get_orchestrator")
        assert gate < src.index("build_context_from_evidence")

    def test_non_ml_advisory_prefix_rejected_400(self):
        """capability 前綴 fail-closed：非 ml_advisory.* → 400（本入口不服務其他 capability）。"""
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.dispatch_ml_advisory(
                req=_req(capability_id="risk_remediation.suggest"), actor=_operator_actor(),
            ))
        assert ei.value.status_code == 400
        assert "capability_not_ml_advisory" in ei.value.detail["reason_codes"]

    def test_evidence_and_context_mutually_exclusive_400(self):
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.dispatch_ml_advisory(
                req=_req(candidate_evidence={"evidence_schema": "x"}, context={"k": 1}),
                actor=_operator_actor(),
            ))
        assert ei.value.status_code == 400
        assert "evidence_context_mutually_exclusive" in ei.value.detail["reason_codes"]

    def test_evidence_inline_only_str_path_rejected_by_model(self):
        """inline-only：candidate_evidence 收 str（server path）→ pydantic 直接拒
        （request model 無任何 path 欄，零 path-traversal 面）。"""
        with pytest.raises(ValidationError):
            LR.MlAdvisoryDispatchRequest(
                capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                candidate_evidence="/etc/passwd",
            )
        # request model 欄位面審計：無任何 *path* 命名欄。
        assert not any("path" in f for f in LR.MlAdvisoryDispatchRequest.model_fields)


# ═══════════════════════════════════════════════════════════════════════════════
# E2E-0 單測鏡像：disabled capability → admission reject + seam 真記
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatchDisabledCapabilityE2E0Mirror:
    def test_disabled_capability_blocked_and_seam_recorded(self, monkeypatch, _mock_seam_writer):
        """registry enabled=false 之下 dispatch → admitted=false / capability_disabled /
        action_result=blocked，且 admission gate-seam 真寫一筆（route→orchestrator→registry→
        D3 seam 鏈路通；零 model call、零 enable）。"""
        orch = _disabled_cap_orchestrator()
        monkeypatch.setattr(LR, "_get_orchestrator", lambda: orch)

        out = asyncio.run(LR.dispatch_ml_advisory(req=_req(), actor=_operator_actor()))

        assert out["action_result"] == "blocked"
        assert out["reason_codes"] == ["capability_disabled"]
        data = out["data"]
        assert data["admitted"] is False
        assert data["admission_reason"] == "capability_disabled"
        assert data["l2_reply_id"] is None  # 零 model call（cascade 未起）
        # _record_admission_seam 真被走：record_gate_seam(gate_id="admission", verdict="reject")。
        assert _mock_seam_writer.record_gate_seam.called
        kwargs = _mock_seam_writer.record_gate_seam.call_args.kwargs
        assert kwargs["gate_id"] == "admission"
        assert kwargs["verdict"] == "reject"
        assert kwargs["applied_as"] == "capability_disabled"
        assert kwargs["details"]["capability_id"] == "ml_advisory.diagnose_leak"

    def test_unknown_capability_blocked_failclosed(self, monkeypatch, _mock_seam_writer):
        """registry 無此 capability → unknown_capability fail-closed（前綴合法仍不可達）。"""
        orch = _disabled_cap_orchestrator()
        monkeypatch.setattr(LR, "_get_orchestrator", lambda: orch)
        out = asyncio.run(LR.dispatch_ml_advisory(
            req=_req(capability_id="ml_advisory.hypothesize", mode="hypothesize"),
            actor=_operator_actor(),
        ))
        assert out["action_result"] == "blocked"
        assert out["data"]["admission_reason"] == "unknown_capability"


# ═══════════════════════════════════════════════════════════════════════════════
# 薄投影：evidence → adapter → dispatch_and_execute（簽名零改動）
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeOrchestrator:
    """捕捉 dispatch_and_execute kwargs 的 fake（驗 route 薄投影，不跑真 cascade）。"""

    def __init__(self, result: ORCH.DispatchResult):
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def dispatch_and_execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class TestDispatchRouteProjection:
    def test_evidence_assembled_via_adapter_and_dispatched_manual(self, monkeypatch):
        """evidence 給定 → adapter 產 context 餵 dispatch_and_execute（trigger=manual），
        adapter reasons 入回應 context_assembly_reasons。"""
        sentinel_ctx = {"candidate_returns": None, "math_gate_inputs": {"bar": "daily"}}
        monkeypatch.setattr(
            "app.l2_candidate_evidence_adapter.build_context_from_evidence",
            lambda ev, **k: (sentinel_ctx, ["daily_returns_missing_b1_defer"]),
        )
        res = ORCH.DispatchResult(
            capability_id="ml_advisory.hypothesize", admitted=True,
            admission_reason="admitted", routed_to="neutral_sink",
            guard_verdict="pass", l2_reply_id="l2r:abc",
        )
        fake = _FakeOrchestrator(res)
        monkeypatch.setattr(LR, "_get_orchestrator", lambda: fake)

        out = asyncio.run(LR.dispatch_ml_advisory(
            req=_req(
                capability_id="ml_advisory.hypothesize", mode="hypothesize",
                candidate_evidence={"evidence_schema": "aeg_candidate_evidence.v1",
                                    "bull_only": True},
                symbol="TONUSDT",
            ),
            actor=_operator_actor(),
        ))

        assert len(fake.calls) == 1
        kw = fake.calls[0]
        assert kw["context"] is sentinel_ctx
        assert kw["trigger"] == "manual"
        assert kw["symbol"] == "TONUSDT"
        assert kw["mode"] == "hypothesize"
        # bull-only 取嚴：evidence 自報 true → dispatch bull_only=True（即便 request false）。
        assert kw["bull_only"] is True
        assert out["action_result"] == "success"
        assert out["data"]["context_assembly_reasons"] == ["daily_returns_missing_b1_defer"]
        assert out["data"]["l2_reply_id"] == "l2r:abc"
        assert out["data"]["routed_to"] == "neutral_sink"

    def test_direct_context_passthrough_without_adapter(self, monkeypatch):
        """context 直接給（E2E/診斷用）→ 原樣 passthrough，adapter 不被呼。"""
        called = []
        monkeypatch.setattr(
            "app.l2_candidate_evidence_adapter.build_context_from_evidence",
            lambda ev, **k: called.append(1) or ({}, []),
        )
        res = ORCH.DispatchResult(
            capability_id="ml_advisory.diagnose_leak", admitted=True,
            admission_reason="admitted", routed_to="neutral_sink",
        )
        fake = _FakeOrchestrator(res)
        monkeypatch.setattr(LR, "_get_orchestrator", lambda: fake)
        direct_ctx = {"run_summary": {"auc": 0.7}}

        asyncio.run(LR.dispatch_ml_advisory(
            req=_req(context=direct_ctx), actor=_operator_actor(),
        ))
        assert not called
        assert fake.calls[0]["context"] == direct_ctx

    def test_orchestrator_signature_untouched(self):
        """dispatch_and_execute 簽名零改動（鐵則）：與 P3a 凍結參數集一致。"""
        import inspect

        params = list(inspect.signature(
            ORCH.L2AdvisoryOrchestrator.dispatch_and_execute
        ).parameters)
        assert params == [
            "self", "capability_id", "mode", "context", "trigger", "coarse_subject",
            "engine", "engine_mode", "symbol", "strategy_name",
            "available_signal_axes", "bull_only", "now",
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# _check_novelty placeholder union（PA §C.3；E2 重點審查 3）
# ═══════════════════════════════════════════════════════════════════════════════


class _LessonStore:
    """retrieve_lessons mock：記錄 (symbol, lesson_type) 查詢序，按 symbol 回放結果。"""

    def __init__(self, by_symbol: dict[str, list[dict]]):
        self.by_symbol = by_symbol
        self.queries: list[tuple[str, str | None]] = []

    async def __call__(self, symbol, hint, lesson_type=None):
        self.queries.append((symbol, lesson_type))
        return self.by_symbol.get(symbol, [])


_HYP = {"feature_hypotheses": [{"statement": "short perp on funding extreme mean reversion"}]}


class TestCheckNoveltyPlaceholderUnion:
    def _run(self, store: _LessonStore, *, symbol, monkeypatch):
        import app.layer2_critic as critic

        monkeypatch.setattr(critic, "retrieve_lessons", store)
        return asyncio.run(EXEC._check_novelty(_HYP, symbol=symbol))

    def test_specific_symbol_hit_skips_placeholder(self, monkeypatch):
        """具體 symbol 命中 → duplicate，且「不」再查 placeholder（symbol-specific 優先）。"""
        store = _LessonStore({"TONUSDT": [{"content": "dead"}]})
        novelty, reason = self._run(store, symbol="TONUSDT", monkeypatch=monkeypatch)
        assert novelty == "duplicate"
        assert store.queries == [("TONUSDT", "dead_mode")]

    def test_specific_symbol_miss_falls_back_to_placeholder(self, monkeypatch):
        """具體 symbol miss → union 查 placeholder（global dead-mode seed 可命中），順序鎖定。"""
        store = _LessonStore({"ml_advisory": [{"content": "global dead mode"}]})
        novelty, reason = self._run(store, symbol="TONUSDT", monkeypatch=monkeypatch)
        assert novelty == "duplicate"
        assert store.queries == [("TONUSDT", "dead_mode"), ("ml_advisory", "dead_mode")]

    def test_placeholder_symbol_queries_once(self, monkeypatch):
        """無 symbol（placeholder 本身）→ 只查一次（sym == placeholder 不重複查）。"""
        store = _LessonStore({})
        novelty, _ = self._run(store, symbol=None, monkeypatch=monkeypatch)
        assert novelty == "novel"
        assert store.queries == [("ml_advisory", "dead_mode")]

    def test_both_miss_is_novel(self, monkeypatch):
        store = _LessonStore({})
        novelty, _ = self._run(store, symbol="TONUSDT", monkeypatch=monkeypatch)
        assert novelty == "novel"
        assert len(store.queries) == 2

    def test_failsoft_shell_unchanged(self, monkeypatch):
        """retrieve_lessons 例外 → fail-soft 視為 novel（novelty 是 dedupe 非安全閘）。"""
        import app.layer2_critic as critic

        async def _boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(critic, "retrieve_lessons", _boom)
        novelty, _ = asyncio.run(EXEC._check_novelty(_HYP, symbol="TONUSDT"))
        assert novelty == "novel"

    def test_union_order_specific_before_placeholder_in_source(self):
        """grep：union 真碼順序「先具體 symbol 後 placeholder」（不反轉）且 fail-soft 外殼仍在。"""
        import inspect

        src = inspect.getsource(EXEC._check_novelty)
        first = src.index("retrieve_lessons(sym, statement")
        second = src.index("retrieve_lessons(\n                _SINK_SYMBOL_PLACEHOLDER")
        assert first < second
        assert "except Exception" in src  # fail-soft 外殼未動
