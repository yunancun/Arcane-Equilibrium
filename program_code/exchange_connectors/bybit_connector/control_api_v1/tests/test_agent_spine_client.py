from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app import agent_spine_client as asc
from app.agent_contracts import (
    AnalystInsight,
    ExecutionPlan,
    ExecutionReport,
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


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        order_plan_id="plan-paper-BTCUSDT-1",
        decision_id="decision-paper-BTCUSDT-1",
        verdict_id="verdict-paper-BTCUSDT-1-v1",
        ts_ms=1_700_000_000_030,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        direction="long",
        qty=1.0,
        order_type="limit",
        limit_price=101.0,
        time_in_force="PostOnly",
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
    for field in ("order_plan_id", "decision_id", "idempotency_key"):
        invalid_payload = dict(plan_payload)
        invalid_payload.pop(field)
        with pytest.raises(ValidationError):
            ExecutionPlan(**invalid_payload)

    report_payload = _report().model_dump(mode="json")
    for field in ("execution_report_id", "order_plan_id", "decision_id"):
        invalid_payload = dict(report_payload)
        invalid_payload.pop(field)
        with pytest.raises(ValidationError):
            ExecutionReport(**invalid_payload)


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

    assert client.publish_guardian_verdict(_verdict()) is True
    assert client.publish_execution_plan(_plan()) is True

    assert len(fake_conn.executes) == 5
    assert fake_conn.executes[0][1][2] == "guardian_verdict"
    assert fake_conn.executes[1][1][4] == "reviewed_by"
    assert fake_conn.executes[2][1][2] == "execution_plan"
    assert fake_conn.executes[3][1][4] == "planned_by"
    idem_sql, idem_params = fake_conn.executes[4]
    assert "INSERT INTO agent.execution_idempotency_keys" in idem_sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in idem_sql
    assert idem_params[:4] == (
        "idem-paper-BTCUSDT-1",
        "plan-paper-BTCUSDT-1",
        "decision-paper-BTCUSDT-1",
        "paper",
    )
    assert client.stats.idempotency_rows == 1


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
