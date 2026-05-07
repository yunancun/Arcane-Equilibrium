from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app import agent_spine_client as asc
from app.agent_contracts import (
    AnalystInsight,
    AnalystInsightL1,
    AnalystInsightL2,
    AnalystInsightL3,
    ExecutionPlan,
    ExecutionReport,
    GuardianP2Modification,
    GuardianVerdict,
    StrategistDecision,
    StrategySignal,
)
from app.agent_spine_client import AgentSpineClient
from app.strategist_decision_v2 import (
    StrategyCandidate,
    StrategyMatchInput,
    build_strategist_decision,
)


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
        requested_qty=1.0,
        filled_qty=1.0,
        expected_price=101.0,
        avg_fill_price=101.08,
        slippage_bps=7.920792,
        fees_paid=0.03,
        fee_bps=3.0,
        submit_latency_ms=120.0,
        fill_latency_ms=480.0,
        liquidity_role="maker",
        quality_metrics={"metric_source": "executor_report_v2"},
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
        analyst_tier="l1",
        insight_type="execution_quality",
        insight_level="fact",
        summary="round trip analyzed",
        evidence_refs=["fill-paper-BTCUSDT-1"],
        confidence=0.95,
        severity="info",
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


@pytest.mark.parametrize("field", ("symbol_source", "direction_source"))
def test_execution_plan_contract_forbids_non_strategist_scope_sources(field: str) -> None:
    plan_payload = _plan().model_dump(mode="json")
    plan_payload[field] = "executor"

    with pytest.raises(ValidationError):
        ExecutionPlan(**plan_payload)


def test_analyst_insight_contract_defines_l1_l2_l3_schema_labels() -> None:
    l1 = AnalystInsightL1(
        insight_id="insight-l1-execution-quality",
        ts_ms=1,
        engine_mode="paper",
        symbol="BTCUSDT",
        execution_report_id="report-paper-BTCUSDT-1",
        insight_type="execution_quality",
        insight_level="fact",
        summary="fill quality measured",
        evidence_refs=["report-paper-BTCUSDT-1"],
        confidence=1.0,
    )
    l2 = AnalystInsightL2(
        insight_id="insight-l2-strategy-pattern",
        ts_ms=2,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        insight_type="strategy_pattern",
        insight_level="inference",
        summary="grid_trading underperforms in one-way shock",
        evidence_refs=["report-paper-BTCUSDT-window"],
        claims=[
            {
                "claim_id": "claim-grid-loss",
                "strategy": "grid_trading",
                "polarity": "negative",
                "confidence": 0.8,
            }
        ],
        confidence=0.8,
    )
    l3 = AnalystInsightL3(
        insight_id="insight-l3-hypothesis",
        ts_ms=3,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        insight_type="hypothesis",
        insight_level="hypothesis",
        summary="reducing grid size during shock regime should improve drawdown",
        evidence_refs=[l2.insight_id],
        claims=[
            {
                "claim_id": "hyp-grid-size-shock",
                "strategy": "grid_trading",
                "polarity": "positive",
                "confidence": 0.55,
            }
        ],
        confidence=0.55,
    )

    assert l1.model_dump(mode="json")["analyst_tier"] == "l1"
    assert l2.model_dump(mode="json")["insight_level"] == "inference"
    assert l3.model_dump(mode="json")["insight_type"] == "hypothesis"

    with pytest.raises(ValidationError):
        AnalystInsightL2(
            insight_id="insight-l2-invalid",
            ts_ms=4,
            engine_mode="paper",
            symbol="BTCUSDT",
            insight_type="hypothesis",
            insight_level="inference",
            summary="wrong tier/type pairing",
        )

    with pytest.raises(ValidationError):
        AnalystInsightL1(
            insight_id="insight-l1-confidence-invalid",
            ts_ms=5,
            engine_mode="paper",
            symbol="BTCUSDT",
            insight_type="execution_quality",
            insight_level="fact",
            summary="confidence must be bounded",
            confidence=1.5,
        )


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("symbol", "ETHUSDT"),
        ("direction", "short"),
    ),
)
def test_publish_execution_plan_rejects_scope_not_from_approved_decision(
    fake_conn,
    field: str,
    value: str,
) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")
    plan_payload = _plan().model_dump(mode="json")
    plan_payload[field] = value

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

    assert len(fake_conn.executes) == 5
    assert fake_conn.executes[0][1][2] == "execution_report"
    assert fake_conn.executes[1][1][4] == "executed_by"
    assert fake_conn.executes[1][1][8]["slippage_bps"] == 7.920792
    assert fake_conn.executes[1][1][8]["fees_paid"] == 0.03
    assert fake_conn.executes[1][1][8]["fill_latency_ms"] == 480.0
    assert fake_conn.executes[1][1][8]["liquidity_role"] == "maker"
    assert fake_conn.executes[2][1][2] == "analyst_insight"
    assert fake_conn.executes[3][1][4] == "analyzed_by"
    assert fake_conn.executes[3][1][8] == {
        "analyst_tier": "l1",
        "insight_type": "execution_quality",
        "insight_level": "fact",
        "confidence": 0.95,
        "severity": "info",
    }
    assert fake_conn.executes[4][1][2:5] == (
        "fill-paper-BTCUSDT-1",
        "insight-paper-BTCUSDT-1",
        "evidence_for",
    )
    assert fake_conn.executes[4][1][8]["evidence_ref_index"] == 0


def test_publish_analyst_insight_links_unique_round_trip_and_metric_evidence(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")
    insight = AnalystInsightL2(
        insight_id="insight-paper-grid-pattern-1",
        ts_ms=1_700_000_000_060,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        decision_id="decision-paper-BTCUSDT-1",
        order_plan_id="plan-paper-BTCUSDT-1",
        insight_type="strategy_pattern",
        insight_level="inference",
        summary="grid round trips underperform after one-way shock",
        evidence_refs=[
            "roundtrip-paper-BTCUSDT-grid-1",
            "strategy-metric-paper-grid-drawdown",
            "roundtrip-paper-BTCUSDT-grid-1",
        ],
        claims=[
            {
                "claim_id": "claim-grid-drawdown",
                "strategy": "grid_trading",
                "polarity": "negative",
                "confidence": 0.82,
            }
        ],
        confidence=0.82,
        severity="medium",
    )

    assert client.publish_analyst_insight(insight) is True

    assert len(fake_conn.executes) == 4
    assert fake_conn.executes[0][1][2] == "analyst_insight"
    assert fake_conn.executes[1][1][2:5] == (
        "plan-paper-BTCUSDT-1",
        "insight-paper-grid-pattern-1",
        "analyzed_by",
    )
    assert fake_conn.executes[2][1][2:5] == (
        "roundtrip-paper-BTCUSDT-grid-1",
        "insight-paper-grid-pattern-1",
        "evidence_for",
    )
    assert fake_conn.executes[3][1][2:5] == (
        "strategy-metric-paper-grid-drawdown",
        "insight-paper-grid-pattern-1",
        "evidence_for",
    )
    assert fake_conn.executes[2][1][8] == {
        "evidence_ref": "roundtrip-paper-BTCUSDT-grid-1",
        "evidence_ref_index": 0,
        "analyst_tier": "l2",
        "insight_type": "strategy_pattern",
        "insight_level": "inference",
    }


def test_losing_pattern_to_strategist_weight_change_persists_reason(fake_conn) -> None:
    client = AgentSpineClient(enabled=True, authority_mode="shadow")
    insight = AnalystInsightL2(
        insight_id="insight-paper-grid-loss-e2e",
        ts_ms=1_700_000_000_070,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        decision_id="decision-paper-BTCUSDT-prior",
        order_plan_id="plan-paper-BTCUSDT-prior",
        insight_type="strategy_pattern",
        insight_level="inference",
        summary="grid_trading loses during one-way shock",
        evidence_refs=[
            "roundtrip-paper-grid-loss-window",
            "strategy-metric-paper-grid-drawdown",
        ],
        claims=[
            {
                "claim_id": "claim-grid-loss-e2e",
                "strategy": "grid_trading",
                "polarity": "negative",
                "confidence": 0.9,
                "observation_count": 20,
                "reason": "losing pattern: one-way shock",
            }
        ],
        confidence=0.9,
        severity="medium",
    )

    assert client.publish_analyst_insight(insight) is True

    decision = build_strategist_decision(
        StrategyMatchInput(
            match_id="match-paper-BTCUSDT-e2e",
            signal_id="sig-paper-BTCUSDT-e2e",
            ts_ms=1_700_000_000_100,
            engine_mode="paper",
            symbol="BTCUSDT",
            direction="long",
            scanner_candidate_id="scanner-paper-BTCUSDT-e2e",
            candidate_routes=[
                StrategyCandidate(
                    candidate_id="route-grid-losing-e2e",
                    strategy="grid_trading",
                    action="open",
                    direction="long",
                    market_fit_score=0.80,
                    edge_lcb_bps=20.0,
                    cost_bps=5.0,
                    data_quality_score=0.9,
                    learning_weight=0.8,
                ),
                StrategyCandidate(
                    candidate_id="route-ma-neutral-e2e",
                    strategy="ma_crossover",
                    action="open",
                    direction="long",
                    market_fit_score=0.80,
                    edge_lcb_bps=20.0,
                    cost_bps=5.0,
                    data_quality_score=0.9,
                    learning_weight=0.5,
                ),
            ],
            analyst_insights=[insight],
            default_size=0.001,
        )
    )

    assert decision.selected_strategy == "ma_crossover"
    grid_feedback = decision.candidate_scores[0]["learning_feedback"]
    assert grid_feedback["reason_codes"] == ["analyst_negative_pattern:claim-grid-loss-e2e"]
    assert grid_feedback["typed_rules"][0]["reason_code"] == (
        "analyst_negative_pattern:claim-grid-loss-e2e"
    )
    assert "insight-paper-grid-loss-e2e" in grid_feedback["evidence_refs"]

    assert client.publish_strategist_decision(decision) is True

    persisted_decision = next(
        params[19]
        for _, params in fake_conn.executes
        if len(params) > 19 and params[2] == "strategist_decision"
    )
    persisted_feedback = persisted_decision["candidate_scores"][0]["learning_feedback"]
    assert persisted_feedback["typed_rules"][0]["claim_id"] == "claim-grid-loss-e2e"
    assert persisted_feedback["typed_rules"][0]["evidence_refs"] == [
        "insight-paper-grid-loss-e2e",
        "roundtrip-paper-grid-loss-window",
        "strategy-metric-paper-grid-drawdown",
    ]
