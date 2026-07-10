from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest


_RESEARCH_ROOT = Path(__file__).resolve().parents[3] / "helper_scripts" / "research"
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from cost_gate_learning_lane.outcome_review import (  # noqa: E402
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.candidate_board_publisher import (  # noqa: E402
    publish_candidate_board,
)
from ml_training import alr_event_consumer as consumer  # noqa: E402


_NOW = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
_DAY_MS = 86_400_000
_HOUR_MS = 3_600_000
_ENTRY_BASE_TS_MS = 1_782_000_000_000


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _resource() -> dict[str, object]:
    body: dict[str, object] = {
        "daily_buckets": [
            {
                "utc_date": f"2026-{month_day}",
                "scan_complete": True,
                "distinct_entries": 5,
            }
            for month_day in (
                "06-27",
                "06-28",
                "06-29",
                "06-30",
                "07-01",
                "07-02",
                "07-03",
            )
        ],
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    return {**body, "resource_estimator_hash": _sha(body)}


def _candidate_context(*, complete: bool = True) -> dict[str, object]:
    context: dict[str, object] = {
        "strategy_version": "v3.2.1",
        "strategy_config_hash": "1" * 64,
        "target_regime_context": {
            "label": "range_low_vol",
            "utc_date": "2026-07-03",
            "point_in_time": "D-1",
        },
        "target_regime_hash": "2" * 64,
        "venue": "bybit",
        "product": "linear_perpetual",
        "evidence_engine_mode": "demo",
        "evidence_regime_label": "neutral|low_vol|liquid",
        "context_hashes": {
            "data": "3" * 64,
            "evidence": "4" * 64,
            "cost": "5" * 64,
            "portfolio": "6" * 64,
        },
        "resource": _resource(),
        "portfolio": {
            "sector_exposure_share": "0.10",
            "strategy_active_target_share": "0.20",
            "beta_to_portfolio": "0.30",
        },
        "proof": {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
        },
    }
    if complete:
        context["hidden_oos_consumed"] = False
    return context


def _outcome_rows(
    count: int = 30,
    *,
    complete_context: bool = True,
) -> list[dict[str, object]]:
    day_effects = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0)
    rows: list[dict[str, object]] = []
    for index in range(count):
        gross = -20.0 + day_effects[index // 5] + (index % 5) * 0.1
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"full-chain-{index}",
                "side_cell_key": "strat|TYPEDUSDT|Buy",
                "symbol": "TYPEDUSDT",
                "strategy_name": "strat",
                "side": "Buy",
                "horizon_minutes": 60,
                "gross_bps": gross,
                "realized_net_bps": gross - 4.0,
                "net_bps_optimistic": gross - 4.0,
                "cost_bps": 4.0,
                "cost_model_version": "conservative_v1",
                "entry_ts_ms": (
                    _ENTRY_BASE_TS_MS
                    + (index // 5) * _DAY_MS
                    + (index % 5) * _HOUR_MS
                ),
                "candidate_summary": {
                    "candidate_learning_context": _candidate_context(
                        complete=complete_context
                    )
                },
            }
        )
    return rows


def _cost_artifact(now: datetime) -> dict[str, object]:
    return {
        "asof": now.isoformat(),
        "symbols": [],
        "global": {
            "n": 500,
            "mean_abs": 2.0,
            "mean_signed": 1.0,
            "q50": 1.0,
            "q75": 4.0,
            "q90": 8.0,
            "cvar90": 8.0,
        },
    }


def _write_board(
    evidence_directory: Path,
    *,
    now: datetime,
    count: int = 30,
    complete_context: bool = True,
) -> Path:
    packet = build_blocked_signal_outcome_review(
        _outcome_rows(count, complete_context=complete_context),
        slippage_quantiles=_cost_artifact(now),
        now_utc=now,
    )
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    producer_directory = evidence_directory.parent / "producer"
    producer_directory.mkdir(parents=True, exist_ok=True)
    source_path = producer_directory / f"blocked_outcome_review_{stamp}.json"
    source_path.write_text(
        json.dumps(packet, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = publish_candidate_board(
        source_path,
        evidence_directory,
        retention_limit=128,
    )
    assert result["status"] in {"PUBLISHED", "ALREADY_PUBLISHED"}
    return evidence_directory / source_path.name


def _policy() -> dict[str, object]:
    stable: dict[str, object] = {
        "algorithm_version": "candidate_learning_arbiter_v1",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    return {**stable, "policy_config_hash": _sha(stable)}


def _cycles(at: datetime) -> list[dict[str, object]]:
    cycles: list[dict[str, object]] = []
    for ordinal in range(1, 4):
        source_ts = (at - timedelta(minutes=3 - ordinal)).isoformat().replace(
            "+00:00", "Z"
        )
        cycles.append(
            {
                "source_hash": _sha(
                    {"ordinal": ordinal, "source_ts": source_ts}
                ),
                "source_key": f"scan-{ordinal}|{source_ts}",
                "source_ts": source_ts,
                "canonical_payload": {
                    "candidates": [{"symbol": "TYPEDUSDT"}],
                    "added": ["TYPEDUSDT"] if ordinal == 1 else [],
                },
            }
        )
    return cycles


class _Connection:
    def __init__(self) -> None:
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.kinds: dict[str, str] = {}
        self.edges: dict[str, tuple[str, str, str]] = {}
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.row: Any = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        assert params is not None
        if "artifact_kind = ANY" in sql:
            kinds = set(params[0])
            self.row = [
                {"canonical_payload": copy.deepcopy(payload)}
                for artifact_hash, payload in reversed(
                    list(self.connection.artifacts.items())
                )
                if self.connection.kinds[artifact_hash] in kinds
            ][: int(params[2])]
        elif "SELECT canonical_payload FROM learning.alr_artifact_nodes" in sql:
            payload = self.connection.artifacts.get(str(params[0]))
            self.row = (
                None
                if payload is None
                else {"canonical_payload": copy.deepcopy(payload)}
            )
        elif "SELECT count(*) FROM learning.alr_provenance_edges" in sql:
            self.row = (
                sum(str(edge_hash) in self.connection.edges for edge_hash in params[0]),
            )
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            artifact_hash = str(params[0])
            if artifact_hash in self.connection.artifacts:
                self.row = None
            else:
                self.connection.artifacts[artifact_hash] = json.loads(str(params[2]))
                self.connection.kinds[artifact_hash] = str(params[1])
                self.row = (artifact_hash,)
        elif "INSERT INTO learning.alr_provenance_edges" in sql:
            edge_hash = str(params[0])
            if edge_hash in self.connection.edges:
                self.row = None
            else:
                self.connection.edges[edge_hash] = (
                    str(params[1]),
                    str(params[2]),
                    str(params[3]),
                )
                self.row = (edge_hash,)
        else:  # pragma: no cover - rejects accidental schema expansion
            raise AssertionError(f"unexpected_sql:{sql}")

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def _patch_non_candidate_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        consumer,
        "process_outcome_feedback_backlog",
        lambda connection, *, max_batch: {
            "feedback_persisted": 0,
            "feedback_duplicates": 0,
            "feedback_deferred": 0,
            "feedback_rotations": 0,
            "feedback_boundary_blocks": 0,
            "feedback_write_attempts": 0,
            "feedback_duplicate_retries": 0,
            "feedback_artifact_rows_written": 0,
            "feedback_provenance_rows_written": 0,
            "feedback_event_rows_written": 0,
            "feedback_total_rows_written": 0,
            "feedback_payload_bytes_written": 0,
        },
    )
    monkeypatch.setattr(
        consumer,
        "process_retention_backlog",
        lambda connection, *, max_batch: {
            "retention_scanned": 0,
            "retention_quarantined": 0,
            "retention_restored": 0,
            "retention_swept": 0,
            "retention_retained": 0,
            "retention_skipped": 0,
        },
    )
    monkeypatch.setattr(
        consumer,
        "process_health_snapshot",
        lambda connection, *, source_head, write_metrics: {
            "health_attempts": 0,
            "health_snapshots": 0,
            "health_state_delta_writes": 0,
            "health_heartbeat_writes": 0,
            "health_writes_suppressed": 0,
            "health_rows_written": 0,
            "health_payload_bytes_written": 0,
            "health_authority_mismatches": 0,
        },
    )


def _run_cycle(
    monkeypatch: pytest.MonkeyPatch,
    connection: _Connection,
    *,
    evidence_directory: Path,
    policy: dict[str, object] | None,
    at: datetime,
) -> dict[str, int]:
    _patch_non_candidate_boundaries(monkeypatch)
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles(at),
    )
    totals: dict[str, int] = {}
    consumer._process_operational_cycle(
        totals,
        connection=connection,
        source_head="a" * 40,
        max_batch=32,
        session_id="full-chain-session",
        candidate_evidence_directory=evidence_directory,
        candidate_policy=policy,
    )
    return totals


def _decisions(connection: _Connection) -> list[dict[str, object]]:
    return [
        payload["decision"]
        for artifact_hash, payload in connection.artifacts.items()
        if connection.kinds[artifact_hash] in {"learning_target", "target_rotation"}
    ]


def test_real_r3_board_runs_through_active_cycle_and_persists_no_training(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_directory = tmp_path / "evidence"
    _write_board(evidence_directory, now=_NOW)
    connection = _Connection()

    totals = _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=_policy(),
        at=_NOW + timedelta(minutes=1),
    )

    decisions = _decisions(connection)
    assert totals["decision_write_attempts"] == 1
    assert totals["operational_run_rows_written"] == 0
    assert totals["training_runs"] == 0
    assert decisions[0]["decision_code"] == "QUALIFIED_CANDIDATE_SELECTED"
    assert decisions[0]["selected_candidate"]["identity"]["symbol"] == "TYPEDUSDT"
    assert all(value is False for value in decisions[0]["no_authority"].values())
    assert all(value == 0 for value in decisions[0]["authority_counters"].values())
    sql = "\n".join(statement for statement, _ in connection.calls).upper()
    assert "ALR_TRAINING_RUNS" not in sql
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


@pytest.mark.parametrize(
    "policy",
    [None, {**_policy(), "policy_config_hash": "0" * 64}],
    ids=["missing", "invalid"],
)
def test_missing_or_invalid_policy_persists_durable_repair_without_training(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy: dict[str, object] | None,
) -> None:
    evidence_directory = tmp_path / "evidence"
    _write_board(evidence_directory, now=_NOW)
    connection = _Connection()

    _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=policy,
        at=_NOW + timedelta(minutes=1),
    )

    decision = _decisions(connection)[0]
    assert decision["decision_code"] == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    assert decision["selected_candidate"] is None
    assert decision["selected_collection_target"] is None
    assert "ALR_TRAINING_RUNS" not in "\n".join(
        statement for statement, _ in connection.calls
    ).upper()


def test_incomplete_typed_context_persists_repair_not_flat_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_directory = tmp_path / "evidence"
    _write_board(evidence_directory, now=_NOW, complete_context=False)
    connection = _Connection()

    _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=_policy(),
        at=_NOW + timedelta(minutes=1),
    )

    decision = _decisions(connection)[0]
    assert decision["decision_code"] == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    assert decision["candidate_count"] == 1
    assert decision["evaluated_candidates"][0]["identity"] is None
    assert decision["evaluated_candidates"][0]["metrics"] is None


def test_cooldown_waits_for_identical_material_then_evidence_delta_reselects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_directory = tmp_path / "evidence"
    _write_board(evidence_directory, now=_NOW)
    connection = _Connection()

    _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=_policy(),
        at=_NOW + timedelta(minutes=1),
    )
    _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=_policy(),
        at=_NOW + timedelta(minutes=2),
    )
    _write_board(
        evidence_directory,
        now=_NOW + timedelta(minutes=20),
        count=31,
    )
    _run_cycle(
        monkeypatch,
        connection,
        evidence_directory=evidence_directory,
        policy=_policy(),
        at=_NOW + timedelta(minutes=21),
    )

    codes = [decision["decision_code"] for decision in _decisions(connection)]
    assert codes == [
        "QUALIFIED_CANDIDATE_SELECTED",
        "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN",
        "QUALIFIED_CANDIDATE_SELECTED",
    ]
    selected = [
        decision["selected_candidate"]
        for decision in _decisions(connection)
        if decision["selected_candidate"] is not None
    ]
    assert selected[0]["family_key"] == selected[1]["family_key"]
    assert selected[0]["material_fingerprint"] != selected[1]["material_fingerprint"]
    assert all(
        "ALR_TRAINING_RUNS" not in statement.upper()
        for statement, _ in connection.calls
    )
