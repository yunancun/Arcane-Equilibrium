from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app import agent_spine_client as asc
from app.agent_contracts import (
    AnalystInsight,
    ExecutionPlan,
    ExecutionReport,
    GuardianP2Modification,
    GuardianVerdict,
    StrategistDecision,
    StrategySignal,
)
from app.agent_spine_client import AgentSpineClient


@dataclass
class _FakeCursor:
    executes: list[tuple[str, tuple]]
    rows: list[tuple] | None = None
    description: list[tuple] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executes.append((sql, params or ()))

    def fetchall(self):
        return list(self.rows or [])


class _FakeConn:
    def __init__(self):
        self.executes: list[tuple[str, tuple]] = []
        self.commits = 0
        self.cursor_obj = _FakeCursor(self.executes)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_conn(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(asc, "Json", None)
    monkeypatch.setattr(asc, "get_pg_conn", lambda: _ConnContext(conn))
    return conn


def _signal() -> StrategySignal:
    return StrategySignal(
        signal_id="sig-paper-BTCUSDT-1",
        ts_ms=1_700_000_000_000,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        direction="long",
        raw_signal_strength=0.72,
        confidence=0.72,
        context_id="ctx-paper-BTCUSDT-1",
    )


def _decision() -> StrategistDecision:
    return StrategistDecision(
        decision_id="decision-paper-BTCUSDT-1",
        signal_id="sig-paper-BTCUSDT-1",
        ts_ms=1_700_000_000_010,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        direction="long",
        confidence=0.7,
        proposed_qty=1.0,
        rationale="typed decision",
        metadata={"raw_prompt": "must redact"},
    )


def _verdict() -> GuardianVerdict:
    return GuardianVerdict(
        verdict_id="verdict-paper-BTCUSDT-1-v1",
        decision_id="decision-paper-BTCUSDT-1",
        verdict_version=1,
        ts_ms=1_700_000_000_020,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        allow=True,
        risk_level="low",
        reasons=["shadow_only"],
    )


def _modified_verdict() -> GuardianVerdict:
    return GuardianVerdict(
        verdict_id="verdict-paper-BTCUSDT-1-v2",
        decision_id="decision-paper-BTCUSDT-1",
        verdict_version=2,
        ts_ms=1_700_000_000_025,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        allow=True,
        risk_level="medium",
        reasons=["strategy_soft_risk"],
        p2_modifications=[
            GuardianP2Modification(
                field="size",
                action="reduce",
                original_value=1.0,
                modified_value=0.5,
                unit="base_qty",
                reason_code="strategy_soft_risk",
                reason="soft drawdown size cap",
            ),
            GuardianP2Modification(
                field="cooldown",
                action="extend",
                original_value=None,
                modified_value=1_800_000,
                unit="ms",
                reason_code="strategy_soft_risk",
                reason="soft drawdown cooldown",
            ),
        ],
    )


def _rejected_verdict() -> GuardianVerdict:
    return GuardianVerdict(
        verdict_id="verdict-paper-BTCUSDT-1-rejected",
        decision_id="decision-paper-BTCUSDT-1",
        verdict_version=3,
        ts_ms=1_700_000_000_026,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        allow=False,
        risk_level="high",
        reasons=["hard_risk_limit"],
    )


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        order_plan_id="plan-paper-BTCUSDT-1",
        decision_id="decision-paper-BTCUSDT-1",
        verdict_id="verdict-paper-BTCUSDT-1-v1",
        verdict_version=1,
        ts_ms=1_700_000_000_030,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        direction="long",
        symbol_source="strategist_decision",
        direction_source="strategist_decision",
        qty=1.0,
        reduce_only=False,
        order_style="post_only",
        urgency="normal",
        max_slippage_bps=10.0,
        maker_preference="maker_only",
        order_type="limit",
        limit_price=101.0,
        time_in_force="PostOnly",
        order_style_params={},
        local_stop_policy={"mode": "guardian_required"},
        anti_hunt_stop_policy={"enabled": True},
        lease_scope="TRADE_ENTRY",
        lease_ttl_ms=30_000,
        idempotency_key="idem-paper-BTCUSDT-1",
    )


def _report() -> ExecutionReport:
    return ExecutionReport(
        execution_report_id="report-paper-BTCUSDT-1",
        order_plan_id="plan-paper-BTCUSDT-1",
        decision_id="decision-paper-BTCUSDT-1",
        ts_ms=1_700_000_000_040,
        engine_mode="paper",
        symbol="BTCUSDT",
        status="filled",
        fill_id="fill-paper-BTCUSDT-1",
    )


def _insight() -> AnalystInsight:
    return AnalystInsight(
        insight_id="insight-paper-BTCUSDT-1",
        ts_ms=1_700_000_000_050,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        decision_id="decision-paper-BTCUSDT-1",
        execution_report_id="report-paper-BTCUSDT-1",
        insight_level="fact",
        summary="round trip analyzed",
        evidence_refs=["fill-paper-BTCUSDT-1"],
    )


def test_contracts_forbid_unbounded_extra_free_text_fields() -> None:
    with pytest.raises(ValidationError):
        StrategistDecision(
            decision_id="d",
            signal_id="s",
            ts_ms=1,
            engine_mode="paper",
            symbol="BTCUSDT",
            strategy="grid_trading",
            direction="long",
            confidence=0.5,
            raw_prompt="not a contract field",
        )


def test_execution_contracts_require_deduplication_lineage_ids() -> None:
    plan_payload = _plan().model_dump(mode="json")
    for field in (
        "order_plan_id",
        "decision_id",
        "verdict_version",
        "idempotency_key",
        "symbol_source",
        "direction_source",
        "order_style",
    ):
        invalid_payload = dict(plan_payload)
        invalid_payload.pop(field)
        with pytest.raises(ValidationError):
            ExecutionPlan(**invalid_payload)
    invalid_payload = dict(plan_payload)
    invalid_payload["verdict_id"] = ""
    with pytest.raises(ValidationError):
        ExecutionPlan(**invalid_payload)

    report_payload = _report().model_dump(mode="json")
    for field in ("execution_report_id", "order_plan_id", "decision_id"):
        invalid_payload = dict(report_payload)
        invalid_payload.pop(field)
        with pytest.raises(ValidationError):
            ExecutionReport(**invalid_payload)


def test_execution_plan_contract_limits_allowed_order_styles() -> None:
    plan_payload = _plan().model_dump(mode="json")

    invalid_payload = dict(plan_payload)
    invalid_payload.update({"order_style": "market", "order_type": "market"})
    with pytest.raises(ValidationError):
        ExecutionPlan(**invalid_payload)

    invalid_payload = dict(plan_payload)
    invalid_payload.update({"order_style": "limit", "time_in_force": "PostOnly"})
    with pytest.raises(ValidationError):
        ExecutionPlan(**invalid_payload)

    invalid_payload = dict(plan_payload)
    invalid_payload.update({"order_style": "limit", "maker_preference": "maker_only"})
    with pytest.raises(ValidationError):
        ExecutionPlan(**invalid_payload)

    invalid_payload = dict(plan_payload)
    invalid_payload.update({"reduce_only": True, "direction": "long"})
    with pytest.raises(ValidationError):
        ExecutionPlan(**invalid_payload)

    close_payload = dict(plan_payload)
    close_payload.update(
        {
            "direction": "close_long",
            "reduce_only": True,
            "order_style": "market",
            "maker_preference": "none",
            "order_type": "market",
            "limit_price": None,
            "time_in_force": None,
        }
    )
    assert ExecutionPlan(**close_payload).reduce_only is True


def test_guardian_verdict_contract_carries_p2_modifications_without_authority_shift() -> None:
    verdict = _modified_verdict()
    payload = verdict.model_dump(mode="json")

    assert payload["allow"] is True
    assert payload["symbol"] == "BTCUSDT"
    assert "direction" not in payload["p2_modifications"][0]
    assert [item["field"] for item in payload["p2_modifications"]] == ["size", "cooldown"]


def test_disabled_client_never_writes(fake_conn) -> None:
    client = AgentSpineClient(enabled=False)

    assert client.publish_strategy_signal(_signal()) is False
    assert fake_conn.executes == []
    assert client.stats.disabled == 1


def test_publish_strategist_decision_writes_object_and_signal_edge(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")

    assert client.publish_strategist_decision(_decision()) is True

    assert len(fake_conn.executes) == 2
    object_sql, object_params = fake_conn.executes[0]
    edge_sql, edge_params = fake_conn.executes[1]
    assert "INSERT INTO agent.decision_objects" in object_sql
    assert object_params[2] == "strategist_decision"
    assert object_params[8] == "decision-paper-BTCUSDT-1"
    assert object_params[16] == "shadow"
    assert object_params[18].startswith("sha256:")
    assert object_params[19]["metadata"]["raw_prompt"] == "[REDACTED]"
    assert "must redact" not in str(object_params[19])
    assert "INSERT INTO agent.decision_edges" in edge_sql
    assert edge_params[2:5] == (
        "sig-paper-BTCUSDT-1",
        "decision-paper-BTCUSDT-1",
        "signal_for",
    )
    assert client.stats.object_rows == 1
    assert client.stats.edge_rows == 1


def test_publish_guardian_verdict_and_plan_write_chain_and_idempotency(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")

    assert client.publish_strategist_decision(_decision()) is True
    assert client.publish_guardian_verdict(_verdict()) is True
    assert client.publish_execution_plan(_plan()) is True

    assert len(fake_conn.executes) == 7
    assert fake_conn.executes[0][1][2] == "strategist_decision"
    assert fake_conn.executes[1][1][4] == "signal_for"
    assert fake_conn.executes[2][1][2] == "guardian_verdict"
    assert fake_conn.executes[3][1][4] == "reviewed_by"
    assert fake_conn.executes[4][1][2] == "execution_plan"
    assert fake_conn.executes[5][1][4] == "planned_by"
    assert fake_conn.executes[5][1][8]["order_style"] == "post_only"
    idem_sql, idem_params = fake_conn.executes[6]
    assert "INSERT INTO agent.execution_idempotency_keys" in idem_sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in idem_sql
    assert idem_params[:4] == (
        "idem-paper-BTCUSDT-1",
        "plan-paper-BTCUSDT-1",
        "decision-paper-BTCUSDT-1",
        "paper",
    )
    assert client.stats.idempotency_rows == 1


def test_publish_execution_plan_requires_prior_allowing_guardian_verdict(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")

    assert client.publish_strategist_decision(_decision()) is True
    assert client.publish_execution_plan(_plan()) is False

    assert client.stats.last_error == "publish_execution_plan:ValueError"
    assert client.stats.write_failures == 1
    assert not any(
        len(params) > 2 and params[2] == "execution_plan"
        for _, params in fake_conn.executes
    )


def test_publish_execution_plan_rejects_rejected_guardian_verdict(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")
    plan_payload = _plan().model_dump(mode="json")
    plan_payload["verdict_id"] = _rejected_verdict().verdict_id

    assert client.publish_strategist_decision(_decision()) is True
    assert client.publish_guardian_verdict(_rejected_verdict()) is True
    assert client.publish_execution_plan(ExecutionPlan(**plan_payload)) is False

    assert fake_conn.executes[2][1][14] == "rejected"
    assert not any(
        len(params) > 2 and params[2] == "execution_plan"
        for _, params in fake_conn.executes
    )


def test_publish_execution_plan_rejects_executor_symbol_direction_authority(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")
    plan_payload = _plan().model_dump(mode="json")
    plan_payload["direction"] = "short"

    assert client.publish_strategist_decision(_decision()) is True
    assert client.publish_guardian_verdict(_verdict()) is True
    assert client.publish_execution_plan(ExecutionPlan(**plan_payload)) is False

    assert client.stats.last_error == "publish_execution_plan:ValueError"
    assert not any(
        len(params) > 2 and params[2] == "execution_plan"
        for _, params in fake_conn.executes
    )


def test_publish_modified_guardian_verdict_records_modified_state(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")

    assert client.publish_guardian_verdict(_modified_verdict()) is True

    assert fake_conn.executes[0][1][2] == "guardian_verdict"
    assert fake_conn.executes[0][1][14] == "modified"


def test_fetch_chain_by_signal_returns_typed_payload_rows(fake_conn) -> None:
    fake_conn.cursor_obj.description = [
        ("object_id",),
        ("object_type",),
        ("state",),
        ("payload",),
    ]
    fake_conn.cursor_obj.rows = [
        ("sig-paper-BTCUSDT-1", "strategy_signal", "observed", _signal().model_dump(mode="json")),
        (
            "decision-paper-BTCUSDT-1",
            "strategist_decision",
            "proposed",
            _decision().model_dump(mode="json"),
        ),
    ]
    client = AgentSpineClient(enabled=True)

    rows = client.fetch_chain_by_signal("sig-paper-BTCUSDT-1")

    assert [row["object_type"] for row in rows] == ["strategy_signal", "strategist_decision"]
    assert rows[1]["payload"]["decision_id"] == "decision-paper-BTCUSDT-1"
    sql, params = fake_conn.executes[0]
    assert "JOIN agent.decision_edges e1" in sql
    assert params == ("sig-paper-BTCUSDT-1",)


def test_publish_execution_report_and_analyst_insight_write_typed_edges(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")

    assert client.publish_execution_report(_report()) is True
    assert client.publish_analyst_insight(_insight()) is True

    assert len(fake_conn.executes) == 4
    assert fake_conn.executes[0][1][2] == "execution_report"
    assert fake_conn.executes[1][1][4] == "executed_by"
    assert fake_conn.executes[2][1][2] == "analyst_insight"
    assert fake_conn.executes[3][1][4] == "analyzed_by"
