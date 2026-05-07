from __future__ import annotations

"""
OpenClaw MAG-016/MAG-017 route contract tests.

MODULE_NOTE (中文):
  驗證 OpenClaw 只讀 allowlist：只暴露 status、self-state、
  brief/latest、diagnostics、escalations，PG / request context 缺失時回 degraded
  envelope，且 route source 不直接觸碰交易寫入、live auth、secret 類入口。
"""

import ast
import io
import os
import re
import sys
import tokenize
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import openclaw_routes as oc_routes  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.openclaw_routes import openclaw_router  # noqa: E402


_CONTEXT_HEADERS = {
    "x-openclaw-source": "console",
    "x-openclaw-channel": "console",
    "x-openclaw-sender": "test-operator",
    "x-openclaw-auth-profile": "read_only",
    "x-openclaw-request-id": "req-openclaw-test-1",
}


def _viewer_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-operator",
        actor_type="human",
        roles={"viewer", "operator"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(openclaw_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    return TestClient(app)


@pytest.fixture
def operator_client() -> TestClient:
    app = FastAPI()
    app.include_router(openclaw_router)
    app.dependency_overrides[current_actor] = _operator_actor
    return TestClient(app)


class _FakeProposalStore:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []

    def list_proposals(self) -> tuple[dict[str, Any], None]:
        return (
            {
                "source_table": "openclaw.proposals",
                "available": True,
                "items": [],
                "recent_count": 0,
            },
            None,
        )

    def create_proposal(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        return {
            "proposal_id": "prop-test-1",
            "request_id": kwargs["request_context"]["request_id"],
            "created_at_ms": 1_778_000_000_000,
            "created_by": {"actor": kwargs["actor"]},
            "proposal_type": kwargs["proposal_type"],
            "risk_class": kwargs["risk_class"],
            "status": "pending_approval",
            "summary": kwargs["summary"],
            "evidence_refs": kwargs["evidence_refs"],
            "required_approval_class": kwargs["required_approval_class"],
            "operator_action_required": True,
            "expires_at_ms": kwargs["expires_at_ms"],
            "linked_diagnosis_id": kwargs["linked_diagnosis_id"],
            "linked_escalation_id": kwargs["linked_escalation_id"],
            "side_effect_route": kwargs["side_effect_route"],
            "payload": kwargs["payload"],
        }

    def decide_proposal(self, **kwargs: Any) -> dict[str, Any] | None:
        self.decisions.append(kwargs)
        return {
            "approval_id": "appr-test-1",
            "proposal_id": kwargs["proposal_id"],
            "request_id": kwargs["request_context"]["request_id"],
            "decision": "approved" if kwargs["action"] == "approve" else "rejected",
            "decided_at_ms": 1_778_000_000_100,
            "actor": kwargs["actor"],
            "auth_result": "authenticated",
            "reason": kwargs["reason"],
            "delegated_route": None,
            "governance_result_ref": {
                "status": "not_delegated",
                "reason": "openclaw_p1_approval_relay_records_decision_only",
            },
        }


class _FakeCursor:
    def __init__(
        self,
        *,
        tables_present: bool = True,
        counts: dict[str, int] | None = None,
        supervisor_rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self._tables_present = tables_present
        self._counts = counts or {
            "agent.messages": 2,
            "agent.state_changes": 11,
            "agent.ai_invocations": 2,
        }
        self._supervisor_rows = supervisor_rows or []
        self._row: tuple[Any, ...] | None = None
        self._rows: list[tuple[Any, ...]] = []
        self.executed_sql: list[str] = []

    def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
        lowered = sql.lower()
        self._rows = []
        if "statement_timeout" in lowered:
            self._row = None
            return
        self.executed_sql.append(sql)
        if "to_regclass" in lowered:
            self._row = (self._tables_present,)
            return
        if (
            "from agent.ai_invocations" in lowered
            and "purpose" in lowered
            and "order by ts desc" in lowered
        ):
            self._row = None
            self._rows = list(self._supervisor_rows)
            return
        for table_name, count in self._counts.items():
            if table_name in sql:
                self._row = (count,)
                return
        self._row = (0,)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor_obj = cursor

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


@contextmanager
def _pg_returns(
    *,
    tables_present: bool = True,
    counts: dict[str, int] | None = None,
    supervisor_rows: list[tuple[Any, ...]] | None = None,
    capture: list[_FakeConn] | None = None,
):
    cursor = _FakeCursor(
        tables_present=tables_present,
        counts=counts,
        supervisor_rows=supervisor_rows,
    )
    conn = _FakeConn(cursor)
    if capture is not None:
        capture.append(conn)

    @contextmanager
    def _fake() -> Any:
        yield conn

    with patch.object(oc_routes, "get_pg_conn", _fake):
        yield conn


@contextmanager
def _pg_unavailable():
    @contextmanager
    def _fake() -> Any:
        yield None

    with patch.object(oc_routes, "get_pg_conn", _fake):
        yield


@contextmanager
def _runtime_snapshot_ok(now_ms: int = 1_778_000_000_000):
    snapshot = {
        "meta": {
            "snapshot_id": "state-test-snapshot",
            "snapshot_ts_ms": now_ms - 1_000,
            "state_revision": 42,
        },
        "global_runtime": {
            "facts": {"engine_alive": True, "paper_state": "ready"},
            "derived": {"global_mode_state": "paper"},
        },
    }
    source_context = types.SimpleNamespace(
        runtime_connection_state="healthy",
        pinned_runtime_snapshot_id="runtime:test",
        pinned_runtime_snapshot_ts_ms=now_ms - 900,
    )
    with patch.object(oc_routes.base, "get_latest_snapshot", lambda: (snapshot, source_context)):
        yield


def _strip_comments_and_docstrings(src: str) -> str:
    no_comments_lines: list[str] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
        comment_spans: dict[int, list[tuple[int, int]]] = {}
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                comment_spans.setdefault(tok.start[0], []).append(
                    (tok.start[1], tok.end[1])
                )
        for idx, line in enumerate(src.splitlines(keepends=True), start=1):
            if idx in comment_spans:
                first_col = min(start for start, _ in comment_spans[idx])
                no_comments_lines.append(line[:first_col].rstrip() + "\n")
            else:
                no_comments_lines.append(line)
        no_comments = "".join(no_comments_lines)
    except tokenize.TokenizeError:
        no_comments = src

    try:
        tree = ast.parse(no_comments)
    except SyntaxError:
        return no_comments

    doc_locs: list[tuple[int, int, int, int]] = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None) or []
        if not isinstance(body, list):
            continue
        for stmt in body:
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                doc_locs.append(
                    (
                        stmt.lineno,
                        stmt.col_offset,
                        stmt.end_lineno or stmt.lineno,
                        stmt.end_col_offset or 0,
                    )
                )

    lines = no_comments.splitlines(keepends=True)
    for lineno, col, end_lineno, end_col in sorted(doc_locs, key=lambda item: -item[0]):
        if lineno == end_lineno:
            idx = lineno - 1
            lines[idx] = lines[idx][:col] + '""' + lines[idx][end_col:]
        else:
            start_idx = lineno - 1
            end_idx = end_lineno - 1
            lines[start_idx] = lines[start_idx][:col] + '""\n'
            for idx in range(start_idx + 1, end_idx + 1):
                lines[idx] = "\n" if idx < end_idx else lines[idx][end_col:]
    return "".join(lines)


def test_status_happy_path_returns_backend_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    with _runtime_snapshot_ok(), _pg_returns():
        resp = client.get("/api/v1/openclaw/status", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "pass"
    assert body["degraded"] is False
    assert body["data_category"] == "openclaw_status"
    assert body["data"]["authority"]["trading_authority"] == "rust_openclaw_engine"
    assert body["data"]["authority"]["can_submit_orders"] is False
    assert body["data"]["authority"]["can_mutate_live_config"] is False
    assert body["data"]["authority"]["can_read_secrets"] is False
    assert body["data"]["agent_event_store"]["row_proof"] is True
    assert body["data"]["runtime"]["engine_alive"] is True


def test_self_state_contains_required_backend_view_model_sections(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    with _runtime_snapshot_ok(), _pg_returns():
        resp = client.get("/api/v1/openclaw/self-state", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_self_state"
    data = body["data"]
    assert data["snapshot_id"].startswith("openclaw_self_state_")
    for key in (
        "runtime",
        "agents",
        "agent_event_store",
        "governance",
        "edge",
        "model_budget",
        "open_blockers",
        "latest_diagnoses",
    ):
        assert key in data
    roles = {row["role"] for row in data["agents"]}
    assert {"scout", "strategist", "guardian", "executor", "analyst", "conductor", "supervisor"} <= roles
    assert data["edge"]["raw_table_join_in_frontend_allowed"] is False


def test_brief_latest_returns_backend_authored_view_model(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    with _runtime_snapshot_ok(), _pg_returns():
        resp = client.get("/api/v1/openclaw/brief/latest", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_brief_latest"
    brief = body["data"]["brief"]
    assert brief["brief_id"].startswith("brief_")
    assert brief["source_tables"] == [
        "agent.messages",
        "agent.state_changes",
        "agent.ai_invocations",
    ]
    assert brief["proposal_lane"]["creation_endpoint_enabled"] is False
    assert body["data"]["authority"]["can_submit_orders"] is False
    assert body["data"]["authority"]["can_mutate_live_config"] is False


def test_diagnostics_separate_facts_inferences_and_hypotheses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    counts = {
        "agent.messages": 0,
        "agent.state_changes": 0,
        "agent.ai_invocations": 0,
    }
    with _runtime_snapshot_ok(), _pg_returns(counts=counts):
        resp = client.get("/api/v1/openclaw/diagnostics", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_diagnostics"
    diagnostics = body["data"]["diagnostics"]
    assert diagnostics
    zero_row_diag = next(
        item
        for item in diagnostics
        if item["facts"] == [
            "Required recent agent event-store row proof is incomplete."
        ]
    )
    assert zero_row_diag["severity"] == "fail"
    assert zero_row_diag["domain"] == "data"
    assert zero_row_diag["inferences"]
    assert zero_row_diag["hypotheses"]
    assert zero_row_diag["linked_escalation_id"] is None
    assert zero_row_diag["linked_proposal_id"] is None


def test_escalations_lists_supervisor_ai_invocation_ledger_rows_read_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    supervisor_rows = [
        (
            "ai_supervisor_test_1",
            1_778_000_000_000,
            "anthropic",
            "claude",
            "L2",
            "prompt-hash",
            False,
            "reserved before request",
            "esc-test-1",
            {
                "control_plane": True,
                "escalation_id": "esc-test-1",
                "trigger_type": "healthcheck_fail",
                "source_observation_ids": ["[52]"],
                "budget_decision": {"allowed": True, "status": "allowed"},
                "ledger_phase": "before_cloud_call",
            },
        )
    ]
    with _runtime_snapshot_ok(), _pg_returns(supervisor_rows=supervisor_rows):
        resp = client.get("/api/v1/openclaw/escalations", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_escalations"
    escalations = body["data"]["escalations"]
    assert escalations["creation_endpoint_enabled"] is False
    assert escalations["approval_relay_enabled"] is False
    assert escalations["direct_cloud_call_allowed_from_route"] is False
    assert escalations["ledger"]["source_table"] == "agent.ai_invocations"
    assert escalations["ledger"]["recent_count"] == 1
    item = escalations["items"][0]
    assert item["escalation_id"] == "esc-test-1"
    assert item["ai_invocation_id"] == "ai_supervisor_test_1"
    assert item["trigger_type"] == "healthcheck_fail"
    assert item["source_observation_ids"] == ["[52]"]
    assert item["status"] == "invocation_recorded"


def test_proposals_get_returns_readable_empty_ledger(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeProposalStore()
    monkeypatch.setattr(oc_routes, "_get_proposal_store", lambda: fake_store)
    resp = client.get("/api/v1/openclaw/proposals", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_proposals"
    assert body["data"]["proposals"]["source_table"] == "openclaw.proposals"
    assert body["data"]["side_effect_delegation_enabled"] is False


def test_proposal_create_requires_complete_openclaw_context(
    operator_client: TestClient,
) -> None:
    resp = operator_client.post(
        "/api/v1/openclaw/proposals",
        json={
            "proposal_type": "read_only_report",
            "risk_class": "read_only",
            "summary": "test proposal",
            "evidence_refs": [
                {
                    "ref_type": "api_route",
                    "ref_id": "GET /api/v1/openclaw/status",
                    "label": "status",
                }
            ],
            "required_approval_class": "operator",
            "expires_at_ms": 1_778_000_300_000,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["reason_codes"] == [
        "openclaw_request_context_required"
    ]


def test_proposal_create_persists_without_side_effect(
    operator_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeProposalStore()
    monkeypatch.setattr(oc_routes, "_get_proposal_store", lambda: fake_store)
    resp = operator_client.post(
        "/api/v1/openclaw/proposals",
        headers=_CONTEXT_HEADERS,
        json={
            "proposal_type": "read_only_report",
            "risk_class": "read_only",
            "summary": "test proposal",
            "evidence_refs": [
                {
                    "ref_type": "api_route",
                    "ref_id": "GET /api/v1/openclaw/status",
                    "label": "status",
                }
            ],
            "required_approval_class": "operator",
            "expires_at_ms": 1_778_000_300_000,
            "payload": {"safe": True},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_proposal_created"
    assert body["data"]["proposal"]["proposal_id"] == "prop-test-1"
    assert body["data"]["side_effect_executed"] is False
    assert fake_store.created[0]["request_context"]["request_id"] == "req-openclaw-test-1"


def test_proposal_approval_requires_operator_role(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/openclaw/proposals/prop-test-1/approve",
        headers=_CONTEXT_HEADERS,
        json={"reason": "ok"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason_codes"] == [
        "openclaw_operator_approval_required"
    ]


def test_proposal_approval_records_decision_without_delegation(
    operator_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeProposalStore()
    monkeypatch.setattr(oc_routes, "_get_proposal_store", lambda: fake_store)
    resp = operator_client.post(
        "/api/v1/openclaw/proposals/prop-test-1/approve",
        headers=_CONTEXT_HEADERS,
        json={"reason": "approved for read-only followup"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_category"] == "openclaw_proposal_decision"
    approval = body["data"]["approval"]
    assert approval["decision"] == "approved"
    assert approval["delegated_route"] is None
    assert body["data"]["side_effect_executed"] is False
    assert body["data"]["side_effect_delegation_enabled"] is False


def test_pg_unavailable_returns_degraded_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    with _runtime_snapshot_ok(), _pg_unavailable():
        resp = client.get("/api/v1/openclaw/status", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "degraded"
    assert body["degraded"] is True
    assert "pg_unavailable" in body["degraded_reasons"]
    assert body["data"]["agent_event_store"]["status"] == "degraded"


def test_missing_request_context_downgrades_read_to_degraded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    with _runtime_snapshot_ok(), _pg_returns():
        resp = client.get("/api/v1/openclaw/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert "request_context_inferred" in body["degraded_reasons"]
    assert body["data"]["request_context"]["complete"] is False
    assert set(body["data"]["request_context"]["missing"]) == {
        "source",
        "channel",
        "sender",
        "auth_profile",
        "request_id",
    }


def test_zero_rows_are_fail_visible_when_required(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED", "1")
    counts = {
        "agent.messages": 0,
        "agent.state_changes": 0,
        "agent.ai_invocations": 0,
    }
    with _runtime_snapshot_ok(), _pg_returns(counts=counts):
        resp = client.get("/api/v1/openclaw/self-state", headers=_CONTEXT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "fail"
    assert body["data"]["agent_event_store"]["zero_row_blocker"] is True
    assert "agent_event_store_zero_rows" in {
        blocker["code"] for blocker in body["data"]["open_blockers"]
    }


def test_openclaw_router_exposes_only_openclaw_allowlist() -> None:
    routes = {
        (tuple(sorted(route.methods or [])), route.path)
        for route in openclaw_router.routes
        if getattr(route, "path", "").startswith("/api/v1/openclaw")
    }
    assert routes == {
        (("GET",), "/api/v1/openclaw/status"),
        (("GET",), "/api/v1/openclaw/self-state"),
        (("GET",), "/api/v1/openclaw/brief/latest"),
        (("GET",), "/api/v1/openclaw/diagnostics"),
        (("GET",), "/api/v1/openclaw/escalations"),
        (("GET",), "/api/v1/openclaw/proposals"),
        (("POST",), "/api/v1/openclaw/proposals"),
        (("POST",), "/api/v1/openclaw/proposals/{proposal_id}/approve"),
        (("POST",), "/api/v1/openclaw/proposals/{proposal_id}/reject"),
    }
    forbidden_path_fragments = (
        "order",
        "cancel",
        "close",
        "secret",
        "key",
        "live-auth",
        "session/start",
        "risk-config",
        "strategy-config",
        "toml",
        "deploy",
        "restart",
        "shell",
        "migration",
    )
    for _, path in routes:
        assert not any(fragment in path for fragment in forbidden_path_fragments)


def test_openclaw_route_source_has_no_write_sql_or_forbidden_proxies() -> None:
    route_path = Path(oc_routes.__file__)
    src = _strip_comments_and_docstrings(route_path.read_text(encoding="utf-8"))
    assert re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", src) is None
    forbidden_call_markers = (
        "submit_order(",
        "cancel_order(",
        "close_position(",
        "grant_live",
        "activate_live",
        "/api/v1/live/session/start",
        "/api/v1/settings/api-keys",
        "/api/v1/settings/secrets",
        "subprocess.",
        "os.system(",
    )
    for marker in forbidden_call_markers:
        assert marker not in src


def test_main_registers_openclaw_router_statically() -> None:
    main_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "main.py"
    )
    src = main_path.read_text(encoding="utf-8")
    assert "from .openclaw_routes import openclaw_router" in src
    assert "app.include_router(openclaw_router)" in src
