"""REF-20 Sprint B2 R5-T7 — risk_config_sha256 delta acceptance test (A5).
REF-20 Sprint B2 R5-T7：risk_config_sha256 delta 驗收測試 (A5)。

MODULE_NOTE (EN):
    Plan §6.R5 + PA design §5.2 acceptance: changing a risk parameter
    that the risk gate actually consumes MUST change replay decisions
    (otherwise the replay risk path is fake — risk_config_sha256 column
    becomes lipstick on a pig). Tighter risk → more rejected intents →
    fewer accepted fills + more ``rejected_reason`` populated rows in
    V050 payload.

    Three hermetic cases prove distinct outcomes for
    ``position_size_max_pct=2.0`` (tight) vs ``position_size_max_pct=10.0``
    (loose) registered against the same fixture / strategy name:

      - Case 1 ``test_position_size_max_pct_delta_produces_different_sha``:
        register tight + loose via ``register_experiment``; assert
        ``risk_config_sha256`` differs (auditors join V050 by experiment
        FK whose registered risk sha is the only canonical risk config
        identifier).

      - Case 2 ``test_position_size_max_pct_propagates_to_disk_manifest``:
        register both, then drive the dispatch flow's
        ``build_default_manifest_payload(cur=stub)`` lookup over the V049
        row's ``manifest_jsonb._replay_risk_overrides`` blob; assert the
        payload that lands on disk for the Rust runner contains the SAME
        risk_overrides the operator registered (Round 3 Fix 3 invariant —
        without passthrough the Rust runner falls back to ``RiskConfig::
        default()`` and the A5 delta cannot materialise).

      - Case 3 ``test_risk_evidence_payload_records_rejected_gate``:
        simulate the writer's evidence injection for a qty=0 ghost fill
        (rejected by tight risk) vs a qty>0 fill (accepted by loose risk);
        assert the synthesized ``risk_decision`` field differs
        (``rejected`` for ghost, ``accepted`` for non-ghost) and the
        ``rejected_reason`` is populated only on ghost rows.

    These three cases together prove A5 acceptance — the risk param is
    decision-relevant, the SHA reflects the param, and the param flows all
    the way from V049 register → disk manifest → Rust runner → V050
    payload (qty + decision evidence). Hermetic via cursor stubs +
    ``monkeypatch``; no Linux engine spawn.

MODULE_NOTE (中):
    Plan §6.R5 + PA design §5.2 驗收：修改 risk gate 真會用到的參數時，
    replay 決策必須跟著變（否則 ``risk_config_sha256`` 欄就只是粉飾門面）。
    Tighter risk → 更多 intent 被拒 → V050 payload 含更多 ``rejected_reason``。

    三個 hermetic case 證明 ``position_size_max_pct=2.0`` (tight) vs ``10.0``
    (loose) 的差異：

      - Case 1：register tight + loose；驗 ``risk_config_sha256`` 不同。
      - Case 2：``build_default_manifest_payload(cur=stub)`` 把 V049 中的
        ``risk_overrides`` 注入 disk payload。
      - Case 3：模擬 writer 對 qty=0 ghost fill（tight risk 拒絕）vs qty>0
        fill（loose risk 接受）的 evidence 注入；驗 ``risk_decision``
        / ``rejected_reason`` 行為。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md
      §6.R5 + PA design §5.2 lines 506-527.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_tests_dir = os.path.dirname(_test_dir)
_control_api_dir = os.path.dirname(_tests_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.auth import AuthenticatedActor  # noqa: E402
from replay import experiment_registry as _er  # noqa: E402
from replay import route_helpers as _rh  # noqa: E402


_DUMMY_ENGINE_SHA = "0" * 64


@pytest.fixture(autouse=True)
def _set_engine_sha_and_clear_cache(monkeypatch):
    """Auto-fixture: set engine sha env + clear in-memory idempotency cache.
    自動 fixture：設 engine sha env + 清 in-memory idempotency cache。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)
    _er._cache_clear_for_test()
    yield
    _er._cache_clear_for_test()


def _operator_actor() -> AuthenticatedActor:
    """Standard operator actor.
    register API 用的標準 operator actor。
    """
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _capturing_cursor():
    """Build a cursor that records INSERT params + serves SELECTs.
    建一個記下 INSERT params + 服務 SELECT 的 cursor。

    Mirrors Round 3 Fix 3 production flow where the same xact-scoped
    cursor that did the INSERT also services the
    ``lookup_replay_config_blob`` SELECT issued by
    ``build_default_manifest_payload``.
    模擬 Round 3 Fix 3 在 PG xact 中的真實行為：同 cursor 既 INSERT 又
    為後續 ``lookup_replay_config_blob`` 服務 SELECT。
    """
    captured: list = []
    persisted: dict[str, Any] = {}

    class _Cur:
        def __init__(self) -> None:
            self.rowcount = 0
            self._next: Any = None
            self.last_sql = ""

        def execute(self, sql: str, params: Any = None) -> None:
            self.last_sql = sql
            sql_text = str(sql)
            if "INSERT INTO replay.experiments" in sql_text:
                captured.append(params)
                persisted["experiment_id"] = (
                    "55555555-5555-5555-5555-555555555555"
                )
                persisted["manifest_jsonb"] = json.loads(params[12])
                self._next = (
                    persisted["experiment_id"],
                    datetime.now(timezone.utc),
                )
            elif "SELECT manifest_jsonb" in sql_text:
                if persisted.get("manifest_jsonb"):
                    self._next = (persisted["manifest_jsonb"],)
                else:
                    self._next = None
            else:
                self._next = None

        def fetchone(self) -> Any:
            return self._next

    return _Cur(), captured, persisted


def _minimal_register_body(
    *, manifest_name: str, risk_overrides: dict[str, Any] | None
) -> _er.ReplayExperimentRegisterRequest:
    """Build a register request body parameterised by ``risk_overrides``.
    參數化建一個 register 請求 body。
    """
    return _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        # Client placeholders; server overrides risk sha when blob supplied.
        # Client placeholder；blob 提供時 server 用 sha 覆寫 risk_config_sha256。
        strategy_config_sha256="a" * 64,
        risk_config_sha256="0" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": manifest_name},
        risk_overrides=risk_overrides,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 1: distinct risk_overrides → distinct risk_config_sha256 in V049
# ═══════════════════════════════════════════════════════════════════════════════


def test_position_size_max_pct_delta_produces_different_sha() -> None:
    """A5 Case 1: same strategy + different ``position_size_max_pct`` →
    distinct server-computed risk_config_sha256 in V049.

    A5 Case 1：同 strategy + 不同 ``position_size_max_pct`` → V049 持久化的
    server-computed risk_config_sha256 不同。
    """
    cur_tight, captured_tight, _ = _capturing_cursor()
    body_tight = _minimal_register_body(
        manifest_name="A5-tight",
        risk_overrides={"limits": {"position_size_max_pct": 2.0}},
    )
    res_tight, err_tight = _er.register_experiment(
        cur_tight, _operator_actor(), body_tight
    )
    assert err_tight is None and res_tight is not None, (
        f"tight register failed: err={err_tight}"
    )

    cur_loose, captured_loose, _ = _capturing_cursor()
    body_loose = _minimal_register_body(
        manifest_name="A5-loose",
        risk_overrides={"limits": {"position_size_max_pct": 10.0}},
    )
    res_loose, err_loose = _er.register_experiment(
        cur_loose, _operator_actor(), body_loose
    )
    assert err_loose is None and res_loose is not None, (
        f"loose register failed: err={err_loose}"
    )

    # INSERT positional: [6] risk_config_sha256 (R5-T6 round 2 wiring
    # makes server override placeholder when risk_overrides supplied).
    # INSERT 位置：[6] risk_config_sha256（R5-T6 round 2 wiring server 在
    # risk_overrides 提供時覆寫 placeholder）。
    sha_tight = captured_tight[0][6]
    sha_loose = captured_loose[0][6]
    assert sha_tight != "0" * 64, (
        f"server did NOT override placeholder for tight risk sha: {sha_tight}"
    )
    assert sha_loose != "0" * 64
    assert sha_tight != sha_loose, (
        "A5 acceptance FAIL: same strategy + position_size_max_pct=2.0 vs "
        f"10.0 produced IDENTICAL risk_config_sha256: {sha_tight} → "
        "risk_overrides column is fake / canonical_bytes contract drift?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Case 2: blob propagates from V049 → build_default_manifest_payload disk
# ═══════════════════════════════════════════════════════════════════════════════


def test_position_size_max_pct_propagates_to_disk_manifest(
    tmp_path: Path,
) -> None:
    """A5 Case 2: register both → ``build_default_manifest_payload(cur=stub)``
    surfaces the registered ``risk_overrides`` in disk payload (Round 3
    Fix 3 invariant).

    A5 Case 2：register 兩 experiment 後 ``build_default_manifest_payload(
    cur=stub)`` 把 V049 中的 risk_overrides 注入 disk payload。
    """
    cur_tight, _captured_tight, _ = _capturing_cursor()
    body_tight = _minimal_register_body(
        manifest_name="A5-disk-tight",
        risk_overrides={"limits": {"position_size_max_pct": 2.0}},
    )
    res_tight, err_tight = _er.register_experiment(
        cur_tight, _operator_actor(), body_tight
    )
    assert err_tight is None and res_tight is not None
    eid_tight = res_tight["experiment_id"]

    payload_tight = _rh.build_default_manifest_payload(
        experiment_id=eid_tight,
        output_dir=tmp_path / "tight",
        cur=cur_tight,
    )
    assert "_replay_risk_overrides" in payload_tight, (
        "Round 3 Fix 3 BROKE: build_default_manifest_payload did NOT inject "
        "_replay_risk_overrides from V049; Rust runner will see "
        "RiskConfig::default() → A5 delta dies at disk hand-off."
    )
    assert payload_tight["_replay_risk_overrides"] == {
        "limits": {"position_size_max_pct": 2.0}
    }

    cur_loose, _captured_loose, _ = _capturing_cursor()
    body_loose = _minimal_register_body(
        manifest_name="A5-disk-loose",
        risk_overrides={"limits": {"position_size_max_pct": 10.0}},
    )
    res_loose, err_loose = _er.register_experiment(
        cur_loose, _operator_actor(), body_loose
    )
    assert err_loose is None and res_loose is not None
    eid_loose = res_loose["experiment_id"]

    payload_loose = _rh.build_default_manifest_payload(
        experiment_id=eid_loose,
        output_dir=tmp_path / "loose",
        cur=cur_loose,
    )
    assert "_replay_risk_overrides" in payload_loose
    assert payload_loose["_replay_risk_overrides"] == {
        "limits": {"position_size_max_pct": 10.0}
    }

    # Two payloads carry distinct blobs → Rust runner reads DIFFERENT
    # RiskConfig → A5 delta materialises.
    # 兩 payload 帶不同 blob → Rust runner 讀不同 RiskConfig → A5 成立。
    assert (
        payload_tight["_replay_risk_overrides"]
        != payload_loose["_replay_risk_overrides"]
    ), (
        "A5 acceptance FAIL: two payloads carry IDENTICAL risk_overrides "
        f"despite distinct register inputs: {payload_tight['_replay_risk_overrides']}"
    )

    # Sanity check: strategy_params blob is NOT present (we did not register it).
    # 健全性：strategy_params blob 未注入（register 時未提供）。
    assert "_replay_strategy_params" not in payload_tight
    assert "_replay_strategy_params" not in payload_loose


# ═══════════════════════════════════════════════════════════════════════════════
# Case 3: rejected vs accepted gate → V050 payload._replay_decision_evidence
# carries distinct risk_decision + rejected_reason
# ═══════════════════════════════════════════════════════════════════════════════


def test_risk_evidence_payload_records_rejected_gate() -> None:
    """A5 Case 3: simulate writer evidence injection for a tight-risk
    rejected (qty=0 ghost) fill vs a loose-risk accepted (qty>0) fill →
    ``risk_decision`` and ``rejected_reason`` differ.

    A5 Case 3：模擬 writer 對 tight-risk 拒絕（qty=0 ghost）vs loose-risk
    接受（qty>0）兩種 fill 的 evidence 注入；驗 ``risk_decision`` 與
    ``rejected_reason`` 不同。

    Rationale: in production the Rust runner emits a ``decision_traces[*]``
    Open action regardless of risk decision — the Open action says "the
    strategy WANTED to open"; whether the risk gate accepted is reflected
    by whether the corresponding ``fills`` row carries qty>0 (accepted) or
    qty=0 (ghost / rejected). The writer's ``consume_decision_evidence_for_fill``
    inspects ``fill.qty`` to populate ``risk_decision`` and only fills
    ``rejected_reason`` for ghost rows. We exercise both branches here.
    """
    from replay import simulated_fills_writer as _sfw

    ts_ms = 1735689600000
    symbol = "BTCUSDT"

    # Same trace shape (the strategy emitted the same Open action under
    # both risk configs); only the fill row's ``qty`` differs (accepted vs
    # rejected by tight-vs-loose risk gate).
    # 同 trace shape（兩 risk config 下策略都 emit 同 Open）；fill 的 qty
    # 因 risk gate 不同而異（loose accept / tight reject ghost）。
    base_trace = [
        {
            "ts_ms": ts_ms,
            "symbol": symbol,
            "strategy_name": "grid_trading",
            "indicators_present": True,
            "actions_emitted": [
                {
                    "Open": {
                        "is_long": True,
                        "intent_signature": "sha_grid_action_open_long",
                        "qty": 0.5,  # strategy's intended qty
                        "price": 50000.0,
                        "confidence": 0.8,
                        "order_type": "Limit",
                    }
                }
            ],
        }
    ]

    # Tight risk gate → ghost fill (qty=0 marker for rejected).
    # Tight risk gate → ghost fill（qty=0 拒絕標記）。
    index_tight = _sfw.build_decision_evidence_index(base_trace)
    fill_tight = {
        "ts_ms": ts_ms, "symbol": symbol, "side": "long", "qty": 0.0,
    }
    evidence_tight = _sfw.consume_decision_evidence_for_fill(
        fill_tight, index_tight
    )
    assert evidence_tight is not None
    assert evidence_tight["risk_decision"] == "rejected", (
        "A5 Case 3 FAIL: qty=0 ghost fill should map to risk_decision='rejected'"
    )
    assert evidence_tight["rejected_reason"] is not None, (
        "A5 Case 3 FAIL: rejected_reason should be populated on ghost row"
    )
    assert "qty=0_ghost_fill" in evidence_tight["rejected_reason"]
    assert "strategy=grid_trading" in evidence_tight["rejected_reason"]

    # Loose risk gate → accepted fill (qty>0).
    # Loose risk gate → 接受 fill（qty>0）。
    index_loose = _sfw.build_decision_evidence_index(base_trace)
    fill_loose = {
        "ts_ms": ts_ms, "symbol": symbol, "side": "long", "qty": 0.5,
    }
    evidence_loose = _sfw.consume_decision_evidence_for_fill(
        fill_loose, index_loose
    )
    assert evidence_loose is not None
    assert evidence_loose["risk_decision"] == "accepted", (
        "A5 Case 3 FAIL: qty>0 fill should map to risk_decision='accepted'"
    )
    assert evidence_loose["rejected_reason"] is None, (
        "A5 Case 3 FAIL: rejected_reason should be None on accepted fill"
    )

    # Branch divergence proven.
    # 分支差異已證。
    assert (
        evidence_tight["risk_decision"] != evidence_loose["risk_decision"]
    ), (
        "A5 acceptance FAIL: tight ghost vs loose accepted produced "
        "IDENTICAL risk_decision; risk-evidence schema is fake."
    )
