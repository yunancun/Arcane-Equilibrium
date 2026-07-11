"""ALR candidate board 專用 rendezvous publisher 行為測試。"""

from __future__ import annotations

import copy
import hashlib
import json
import stat
import subprocess
import sys
import threading
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)
from cost_gate_learning_lane import candidate_board_publisher as publisher
from cost_gate_learning_lane.candidate_board_publisher import (
    CandidateBoardPublishError,
    publish_candidate_board,
)
from cost_gate_learning_lane.outcome_review import build_blocked_signal_outcome_review
from cost_gate_learning_lane.outcome_review import BlockedOutcomeReviewConfig
from cost_gate_learning_lane.slippage_quantile_artifact import (
    build_slippage_quantile_artifact,
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_review(
    path: Path,
    *,
    generated_at_utc: str = "2026-07-10T12:00:00Z",
) -> bytes:
    top_audit = {
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": 0,
        "qualified_lineage_outcome_row_count": 0,
        "unqualified_lineage_outcome_row_count": 0,
        "invalid_lineage_outcome_row_count": 0,
        "invalid_exact_cohort_row_count": 0,
        "invalid_identity_family_row_count": 0,
        "unassigned_invalid_lineage_outcome_row_count": 0,
        "unqualified_raw_valid_evaluation_missing_row_count": 0,
        "unqualified_event_outside_evaluation_window_row_count": 0,
        "consistent_duplicate_event_hash_extra_row_count": 0,
        "conflicting_duplicate_event_hash_row_count": 0,
        "conflicting_duplicate_event_hash_attribution_row_count": 0,
        "lineage_exclusion_reason_counts": {},
    }
    board = {
        "schema_version": "cost_gate_learning_candidate_board_v2",
        "as_of_utc_date": generated_at_utc[:10],
        "candidate_universe_complete": True,
        **top_audit,
        "candidate_rows": [],
        "selection_hash": _canonical_hash(
            {
                "schema_version": "cost_gate_learning_candidate_selection_v2",
                "candidate_rows": [],
            }
        ),
        "audit_hash": _canonical_hash(
            {
                "schema_version": "cost_gate_learning_candidate_audit_v2",
                **top_audit,
                "candidate_audit_rows": [],
            }
        ),
    }
    board["board_hash"] = _canonical_hash(board)
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
        "generated_at_utc": generated_at_utc,
        "cost_basis_main": "conservative_v1",
        "expected_cost_artifact": {
            "available": False,
            "asof": None,
            "source_asof_utc": None,
            "source_payload_sha256": None,
            "source_payload": None,
            "normalized_projection": None,
            "normalized_projection_sha256": None,
            "global_mean_abs_bps": None,
            "global_tail_bps": None,
            "global_tail_metric": None,
            "n_total_global": 0,
            "max_age_hours": 48,
        },
        "learning_candidate_board": board,
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _rewrite_review(path: Path, mutate: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    board = payload.get("learning_candidate_board")
    if isinstance(board, dict):
        board["board_hash"] = _canonical_hash(
            {key: value for key, value in board.items() if key != "board_hash"}
        )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _rewrite_rehashed_board(path: Path, mutate: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    board = payload["learning_candidate_board"]
    mutate(board)
    _rehash_candidate_board(board)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


_SELECTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "candidate_family_key",
    "stable_cohort_hash",
    "candidate_identity",
    "identity_complete",
    "arbiter_input",
    "arbiter_input_complete",
    "selection_eligible",
    "blockers",
)
_TOP_AUDIT_FIELDS = (
    "lineage_partition_complete",
    "raw_blocked_outcome_row_count",
    "qualified_lineage_outcome_row_count",
    "unqualified_lineage_outcome_row_count",
    "invalid_lineage_outcome_row_count",
    "invalid_exact_cohort_row_count",
    "invalid_identity_family_row_count",
    "unassigned_invalid_lineage_outcome_row_count",
    "unqualified_raw_valid_evaluation_missing_row_count",
    "unqualified_event_outside_evaluation_window_row_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_duplicate_event_hash_row_count",
    "conflicting_duplicate_event_hash_attribution_row_count",
    "lineage_exclusion_reason_counts",
)


def _rehash_candidate_board(board: dict[str, object]) -> None:
    """Recompute every public board hash after an adversarial semantic mutation."""
    rows = board["candidate_rows"]
    assert isinstance(rows, list)
    semantic_rows = sorted(
        (
            {field: copy.deepcopy(row[field]) for field in _SELECTION_FIELDS}
            for row in rows
        ),
        key=lambda row: (row["candidate_id"], _canonical_hash(row)),
    )
    board["selection_hash"] = _canonical_hash(
        {
            "schema_version": "cost_gate_learning_candidate_selection_v2",
            "candidate_rows": semantic_rows,
        }
    )
    candidate_audit_rows = sorted(
        (
            {
                "candidate_id": row["candidate_id"],
                **{
                    key: copy.deepcopy(value)
                    for key, value in row.items()
                    if key not in _SELECTION_FIELDS and key != "candidate_id"
                },
            }
            for row in rows
        ),
        key=lambda row: row["candidate_id"],
    )
    board["audit_hash"] = _canonical_hash(
        {
            "schema_version": "cost_gate_learning_candidate_audit_v2",
            **{field: copy.deepcopy(board[field]) for field in _TOP_AUDIT_FIELDS},
            "candidate_audit_rows": candidate_audit_rows,
        }
    )
    board.pop("board_hash", None)
    board["board_hash"] = _canonical_hash(board)


def _rewrite_rehashed_candidate(
    path: Path,
    mutate: object,
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    board = payload["learning_candidate_board"]
    row = board["candidate_rows"][0]
    mutate(row)
    arbiter_input = row["arbiter_input"]
    resource = arbiter_input["resource"]
    resource["resource_estimator_hash"] = _canonical_hash(
        {
            "daily_buckets": [
                {
                    "utc_date": bucket["utc_date"],
                    "scan_complete": bucket["scan_complete"],
                    "distinct_entries": bucket["distinct_entries"],
                }
                for bucket in resource["daily_buckets"]
            ],
            "estimated_rows_scanned": resource["estimated_rows_scanned"],
            "predicted_canonical_bytes": resource["predicted_canonical_bytes"],
            "zero_resource_attested": resource["zero_resource_attested"],
        }
    )
    arbiter_input.pop("arbiter_input_hash", None)
    arbiter_input["arbiter_input_hash"] = _canonical_hash(arbiter_input)
    _rebind_candidate_row(row)
    _rehash_candidate_board(board)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _rebind_candidate_row(row: dict[str, object]) -> None:
    """Keep every declared candidate binding self-consistent after mutation."""
    arbiter_input = row["arbiter_input"]
    identity = arbiter_input["identity"]
    target = identity["target_regime"]
    context_hashes = arbiter_input["context_hashes"]
    raw_identity = {
        "strategy_name": identity["strategy_name"],
        "strategy_version": identity["strategy_version"],
        "strategy_config_hash": identity["config_hash"],
        "symbol": identity["symbol"],
        "side": identity["side"],
        "horizon_minutes": identity["horizon_minutes"],
        "venue": identity["venue"],
        "product": identity["product"],
        "evidence_engine_mode": identity["evidence_engine_mode"],
    }
    target_context = {
        key: copy.deepcopy(value)
        for key, value in target.items()
        if key != "hash"
    }
    row["candidate_identity"] = {
        **raw_identity,
        "target_regime_context": target_context,
        "target_regime_hash": target["hash"],
        "engine_mode": "shadow",
    }
    row["candidate_id"] = _canonical_hash(
        {
            "schema_version": "cost_gate_learning_candidate_v2",
            "identity": identity,
            "context_hashes": context_hashes,
        }
    )
    row["candidate_family_key"] = _canonical_hash(
        {
            "schema_version": "candidate_learning_family_v2",
            "identity": raw_identity,
        }
    )
    evidence = arbiter_input["evidence"]
    stable_projection = {
        "strategy_version": raw_identity["strategy_version"],
        "strategy_config_hash": raw_identity["strategy_config_hash"],
        "target_regime_context": {
            key: target_context[key]
            for key in ("label", "utc_date", "point_in_time")
        },
        "target_regime_hash": target["hash"],
        "venue": raw_identity["venue"],
        "product": raw_identity["product"],
        "evidence_engine_mode": raw_identity["evidence_engine_mode"],
        "context_hashes": context_hashes,
        "resource": arbiter_input["resource"],
        "portfolio": arbiter_input["portfolio"],
        "proof": {
            "proof_stage": evidence["proof_stage"],
            "completed_proof_stages": evidence["completed_proof_stages"],
            "next_gap": evidence["next_gap"],
        },
        "hidden_oos_consumed": arbiter_input["quality"]["hidden_oos_consumed"],
    }
    row["stable_cohort_hash"] = _canonical_hash(
        {"identity": raw_identity, "stable_projection": stable_projection}
    )
    row["horizon_minutes"] = raw_identity["horizon_minutes"]
    row["side_cell_key"] = (
        f"{raw_identity['strategy_name']}|{raw_identity['symbol']}|"
        f"{raw_identity['side']}"
    )


def _set_target_label_and_hash(row: dict[str, object], label: str) -> None:
    target = row["arbiter_input"]["identity"]["target_regime"]
    target["label"] = label
    target["hash"] = _canonical_hash(
        {key: value for key, value in target.items() if key != "hash"}
    )


def _inject_unreported_exact_invalid(row: dict[str, object]) -> None:
    code = "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT"
    row["invalid_lineage_exact_cohort_row_count"] = 1
    row["lineage_blocker_reason_counts"] = {code: 1}
    row["blockers"] = sorted({*row["blockers"], code})
    row["arbiter_input_complete"] = False
    row["selection_eligible"] = False
    row["qualified_metrics_actionable"] = False
    row["metrics_scope"] = "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"


def _detach_distinct_day_count(row: dict[str, object]) -> None:
    row["distinct_entry_utc_days"] = 2
    row["arbiter_input"]["evidence"]["utc_day_count"] = 2


def _detach_censoring_share(row: dict[str, object]) -> None:
    row["censored_share"] = 0.5
    row["censored_pct"] = 50.0
    row["arbiter_input"]["quality"]["censored_share"] = 0.5


def _detach_cluster_count(row: dict[str, object]) -> None:
    row["cluster_count"] = 2
    row["arbiter_input"]["evidence"]["cluster_count"] = 2


def _detach_cluster_variance_from_se(row: dict[str, object]) -> None:
    variance = row["day_cluster_variance"]
    assert isinstance(variance, float)
    row["day_cluster_variance"] = variance * 4.0
    row["arbiter_input"]["evidence"]["day_cluster_variance"] = variance * 4.0


def _detach_cluster_se_from_variance(row: dict[str, object]) -> None:
    cluster_se = row["cluster_se"]
    assert isinstance(cluster_se, float)
    row["cluster_se"] = cluster_se * 2.0
    row["arbiter_input"]["evidence"]["cluster_se"] = cluster_se * 2.0


def _forge_nonclean_cluster_values(row: dict[str, object]) -> None:
    row["day_cluster_variance"] = 1.0
    row["cluster_se"] = 0.0
    row["arbiter_input"]["evidence"]["day_cluster_variance"] = 1.0
    row["arbiter_input"]["evidence"]["cluster_se"] = 0.0


def _add_arbitrary_blocker(row: dict[str, object]) -> None:
    row["blockers"] = sorted({*row["blockers"], "ARBITRARY_REHASHED_BLOCKER"})
    row["selection_eligible"] = False


def _write_nonempty_review(
    path: Path,
    *,
    cfg: BlockedOutcomeReviewConfig | None = None,
    legacy_optimistic_cost: bool = False,
) -> None:
    row = attach_candidate_lineage_v2(
        {
            "record_type": "blocked_signal_outcome",
            "attempt_id": "publisher-v2-candidate",
            "side_cell_key": "ma_crossover|BTCUSDT|Buy",
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "gross_bps": 11.0,
            "realized_net_bps": -1.0,
            "net_bps_optimistic": 7.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
        },
        context_id="publisher-v2-candidate",
        as_of_utc_date="2026-07-10",
    )
    if legacy_optimistic_cost:
        row.pop("cost_model_version")
    payload = build_blocked_signal_outcome_review(
        [row],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        cfg=cfg,
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_two_candidate_review(path: Path) -> None:
    rows = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        context_id = f"publisher-v2-order-{symbol.lower()}"
        rows.append(
            attach_candidate_lineage_v2(
                {
                    "record_type": "blocked_signal_outcome",
                    "gross_bps": 11.0,
                    "realized_net_bps": -1.0,
                    "net_bps_optimistic": 7.0,
                    "cost_bps": 12.0,
                    "cost_model_version": "conservative_v1",
                },
                context_id=context_id,
                symbol=symbol,
                as_of_utc_date="2026-07-10",
            )
        )
    payload = build_blocked_signal_outcome_review(
        rows,
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_duplicate_conflict_review(path: Path) -> None:
    row = attach_candidate_lineage_v2(
        {
            "record_type": "blocked_signal_outcome",
            "gross_bps": 11.0,
            "realized_net_bps": -1.0,
            "net_bps_optimistic": 7.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
        },
        context_id="publisher-v2-conflict",
        as_of_utc_date="2026-07-10",
    )
    conflicting = copy.deepcopy(row)
    conflicting["realized_net_bps"] = 1.0
    payload = build_blocked_signal_outcome_review(
        [row, conflicting],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_multi_cohort_unqualified_conflict_review(path: Path) -> None:
    base = {
        "record_type": "blocked_signal_outcome",
        "gross_bps": 11.0,
        "realized_net_bps": -1.0,
        "net_bps_optimistic": 7.0,
        "cost_bps": 12.0,
        "cost_model_version": "conservative_v1",
    }
    context_id = "publisher-v2-multi-cohort-conflict"
    first = attach_candidate_lineage_v2(
        base,
        context_id=context_id,
        as_of_utc_date="2026-07-10",
    )
    second = attach_candidate_lineage_v2(
        base,
        context_id=context_id,
        as_of_utc_date="2026-07-10",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    raw_only = copy.deepcopy(first)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)
    payload = build_blocked_signal_outcome_review(
        [raw_only, second, first],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_identity_family_invalid_review(path: Path) -> None:
    base = {
        "record_type": "blocked_signal_outcome",
        "gross_bps": 11.0,
        "realized_net_bps": -1.0,
        "net_bps_optimistic": 7.0,
        "cost_bps": 12.0,
        "cost_model_version": "conservative_v1",
    }
    qualified = attach_candidate_lineage_v2(
        base,
        context_id="publisher-v2-family-qualified",
        as_of_utc_date="2026-07-10",
    )
    family_invalid = attach_candidate_lineage_v2(
        base,
        context_id="publisher-v2-family-invalid",
        as_of_utc_date="2026-07-10",
    )
    family_invalid["candidate_summary"].pop("candidate_evaluation_context")
    payload = build_blocked_signal_outcome_review(
        [family_invalid, qualified],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _expected_slippage_payload(
    *,
    now_utc: datetime = datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    symbol: str | None = None,
    symbol_mean_abs: float = 1.5,
) -> dict[str, object]:
    global_mean_abs = (
        (symbol_mean_abs * 200.0 + 2.0 * 300.0) / 500.0
        if symbol is not None
        else 2.0
    )
    rows: list[dict[str, object]] = [
        {
            "symbol": None,
            "n": 500,
            "mean_abs": global_mean_abs,
            "mean_signed": 1.0,
            "q50": 1.0,
            "q75": 4.0,
            "q90": 8.0,
            "cvar90": 9.0,
        }
    ]
    if symbol is None:
        rows.append(
            {
                "symbol": "ZZZGLOBALUSDT",
                "n": 500,
                "mean_abs": 2.0,
                "mean_signed": 1.0,
                "q50": 1.0,
                "q75": 4.0,
                "q90": 8.0,
                "cvar90": 9.0,
            }
        )
    else:
        rows.append(
            {
                "symbol": symbol,
                "n": 200,
                "mean_abs": symbol_mean_abs,
                "mean_signed": symbol_mean_abs / 2.0,
                "q50": symbol_mean_abs / 2.0,
                "q75": symbol_mean_abs * 2.0,
                "q90": symbol_mean_abs * 4.0,
                "cvar90": symbol_mean_abs * 4.5,
            }
        )
        rows.append(
            {
                "symbol": "ZZZFILLUSDT",
                "n": 300,
                "mean_abs": 2.0,
                "mean_signed": 1.0,
                "q50": 1.0,
                "q75": 4.0,
                "q90": 8.0,
                "cvar90": 9.0,
            }
        )
    return build_slippage_quantile_artifact(rows, now_utc=now_utc)


def _write_json_payload(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_expected_cost_review(path: Path) -> dict[str, object]:
    row = attach_candidate_lineage_v2(
        {
            "record_type": "blocked_signal_outcome",
            "gross_bps": 30.0,
            "realized_net_bps": 26.0,
            "net_bps_optimistic": 26.0,
            "cost_bps": 4.0,
            "cost_model_version": "conservative_v1",
        },
        context_id="publisher-v2-expected-cost",
        as_of_utc_date="2026-07-10",
    )
    slippage_payload = _expected_slippage_payload()
    payload = build_blocked_signal_outcome_review(
        [row],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        slippage_quantiles=slippage_payload,
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return slippage_payload


def _write_five_of_thirty_review(path: Path) -> dict[str, object]:
    base = datetime(2026, 7, 3, tzinfo=timezone.utc)
    rows = []
    for index in range(30):
        entry = base + timedelta(days=index // 5, hours=index % 5)
        entry_ts_ms = int(entry.timestamp() * 1_000)
        rows.append(
            attach_candidate_lineage_v2(
                {
                    "record_type": "blocked_signal_outcome",
                    "gross_bps": 10.0 + index / 100.0,
                    "realized_net_bps": -2.0 + index / 100.0,
                    "net_bps_optimistic": 6.0 + index / 100.0,
                    "cost_bps": 12.0,
                    "cost_model_version": "conservative_v1",
                    "entry_ts_ms": entry_ts_ms,
                },
                context_id=f"publisher-five-of-thirty-{index}",
                captured_at_ms=entry_ts_ms,
                as_of_utc_date="2026-07-10",
            )
        )
    payload = build_blocked_signal_outcome_review(
        rows,
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def test_publishes_byte_identical_private_stamped_snapshot_only(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    expected = _write_review(source)
    destination = tmp_path / "rendezvous"

    result = publish_candidate_board(
        source,
        destination,
        retention_limit=128,
    )

    published = destination / source.name
    assert result["schema_version"] == "alr_candidate_board_publish_result_v2"
    assert result["status"] == "PUBLISHED"
    assert result["published_path"] == str(published)
    assert published.read_bytes() == expected
    assert published.stat().st_mode & 0o777 == 0o600
    assert sorted(path.name for path in destination.iterdir() if not path.name.startswith(".")) == [
        source.name
    ]
    assert not (destination / "blocked_outcome_review_latest.json").exists()


def test_secure_read_rejects_ctime_only_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same inode/size/mtime with changed ctime is still a raced source read."""
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    original_fstat = publisher.os.fstat
    call_count = 0

    def ctime_changed(descriptor: int) -> object:
        nonlocal call_count
        metadata = original_fstat(descriptor)
        call_count += 1
        if call_count != 2:
            return metadata
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=metadata.st_size,
            st_mtime_ns=metadata.st_mtime_ns,
            st_ctime_ns=metadata.st_ctime_ns + 1,
        )

    monkeypatch.setattr(publisher.os, "fstat", ctime_changed)

    with pytest.raises(CandidateBoardPublishError, match="source_changed_during_read"):
        publisher._read_bounded_regular(source, max_bytes=publisher._MAX_SOURCE_BYTES)


def test_publisher_exact_comparator_distinguishes_signed_zero() -> None:
    assert publisher._exact_value_equal(0.0, -0.0) is False
    assert publisher._exact_value_equal(-0.0, -0.0) is True


def test_direct_script_help_bootstraps_research_package() -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(publisher.__file__)), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--slippage-artifact" in completed.stdout


def test_cli_omission_uses_source_sibling_slippage_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    observed: dict[str, object] = {}

    def fake_publish(
        source_path: Path,
        destination_directory: Path,
        **kwargs: object,
    ) -> dict[str, object]:
        observed.update(kwargs)
        return {
            "schema_version": "alr_candidate_board_publish_result_v2",
            "status": "PUBLISHED",
        }

    monkeypatch.setattr(publisher, "publish_candidate_board", fake_publish)

    result = publisher.main(
        [
            "--source",
            str(source),
            "--destination",
            str(tmp_path / "destination"),
            "--retention-limit",
            "1",
        ]
    )

    assert result == 0
    assert observed["slippage_artifact_path"] == (
        source.parent / "slippage_quantiles_latest.json"
    )
    assert '"status": "PUBLISHED"' in capsys.readouterr().out


def test_expected_basis_requires_independent_slippage_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_expected_cost_review(source)

    with pytest.raises(
        CandidateBoardPublishError,
        match="expected_cost_independent_artifact_required",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
        )


def test_expected_basis_rejects_independent_slippage_artifact_mismatch(
    tmp_path: Path,
) -> None:
    """Review 內嵌 A 不得由另一份合法但不同的 B artifact 漂白。"""
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_expected_cost_review(source)
    independent = tmp_path / "slippage_quantiles_latest.json"
    _write_json_payload(
        independent,
        _expected_slippage_payload(symbol="BTCUSDT", symbol_mean_abs=9.0),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="expected_cost_independent_artifact_mismatch",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            slippage_artifact_path=independent,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_expected_basis_accepts_exact_independent_artifact_with_reordered_keys(
    tmp_path: Path,
) -> None:
    """JSON object key order 不是語義；相同 producer bytes 投影應可發布。"""
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    artifact = _write_expected_cost_review(source)
    reordered = {
        key: (
            {nested: value[nested] for nested in reversed(tuple(value))}
            if isinstance(value, dict)
            else [
                {nested: row[nested] for nested in reversed(tuple(row))}
                for row in value
            ]
            if key == "symbols"
            else value
        )
        for key, value in reversed(tuple(artifact.items()))
    }
    independent = tmp_path / "slippage_quantiles_latest.json"
    _write_json_payload(independent, reordered)

    result = publish_candidate_board(
        source,
        tmp_path / "rendezvous",
        retention_limit=128,
        slippage_artifact_path=independent,
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )

    assert result["status"] == "PUBLISHED"


def test_expected_cost_cannot_fall_below_selected_source_projection(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    artifact = _write_expected_cost_review(source)
    independent = tmp_path / "slippage_quantiles_latest.json"
    _write_json_payload(independent, artifact)
    _rewrite_rehashed_candidate(
        source,
        lambda row: row.__setitem__("avg_expected_cost_bps", 11.0),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_cost_evidence_binding_invalid",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            slippage_artifact_path=independent,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_publisher_rejects_fresh_wrapper_around_stale_board_date(
    tmp_path: Path,
) -> None:
    """Fresh filename/generated_at 不得替舊 board 重新包裝成當日證據。"""
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board.__setitem__("as_of_utc_date", "2026-07-09"),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="board_as_of_generated_at_mismatch",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (
            lambda payload: payload.__setitem__(
                "schema_version",
                "cost_gate_demo_learning_lane_blocked_outcome_review_v5",
            ),
            "source_schema_invalid",
        ),
        (
            lambda payload: payload["learning_candidate_board"].__setitem__(
                "schema_version",
                "cost_gate_learning_candidate_board_v1",
            ),
            "board_schema_invalid",
        ),
    ),
)
def test_publisher_rejects_pre_lineage_v1_artifacts(
    tmp_path: Path,
    mutate: object,
    reason: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    _rewrite_review(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match=reason):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("selection_hash", "selection_hash_invalid"),
        ("audit_hash", "audit_hash_invalid"),
    ),
)
def test_publisher_rejects_rehashed_selection_or_audit_poison(
    tmp_path: Path,
    field: str,
    reason: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    _rewrite_review(
        source,
        lambda payload: payload["learning_candidate_board"].__setitem__(
            field, "0" * 64
        ),
    )

    with pytest.raises(CandidateBoardPublishError, match=reason):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_candidate_input_poison(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_review(
        source,
        lambda payload: payload["learning_candidate_board"]["candidate_rows"][0][
            "arbiter_input"
        ]["quality"].__setitem__("integrity_ok", True),
    )

    with pytest.raises(CandidateBoardPublishError, match="arbiter_input_hash_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "ignored_extension", True
        ),
        lambda row: row["arbiter_input"]["identity"]["target_regime"].__setitem__(
            "ignored_extension", True
        ),
        lambda row: row["arbiter_input"]["context_hashes"].__setitem__(
            "ignored_extension", "0" * 64
        ),
        lambda row: row["arbiter_input"]["quality"].__setitem__(
            "ignored_extension", True
        ),
        lambda row: row["arbiter_input"]["evidence"].__setitem__(
            "ignored_extension", 0
        ),
        lambda row: row["arbiter_input"]["evidence"]["next_gap"].__setitem__(
            "ignored_extension", True
        ),
        lambda row: row["arbiter_input"]["resource"].__setitem__(
            "ignored_extension", 0
        ),
        lambda row: row["arbiter_input"]["resource"]["daily_buckets"][0].__setitem__(
            "ignored_extension", 0
        ),
        lambda row: row["arbiter_input"]["portfolio"].__setitem__(
            "ignored_extension", "0"
        ),
    ),
)
def test_publisher_rejects_fully_rehashed_nested_arbiter_input_extensions(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="arbiter_input_nested_fields_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "strategy_version", "v2.1.0"
        ),
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "symbol", "btcusdt"
        ),
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "venue", "coinbase"
        ),
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "product", "spot"
        ),
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "horizon_minutes", 0
        ),
        lambda row: row["arbiter_input"]["identity"].__setitem__(
            "horizon_minutes", 1_441
        ),
        lambda row: _set_target_label_and_hash(row, "not-a-canonical-regime"),
        lambda row: row["arbiter_input"]["identity"]["target_regime"].__setitem__(
            "hash", "f" * 64
        ),
    ),
)
def test_publisher_rejects_fully_rehashed_noncanonical_candidate_identity(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="candidate_identity_semantics_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row["arbiter_input"]["context_hashes"].__setitem__(
            "data", "not-a-hash"
        ),
        lambda row: row["arbiter_input"]["quality"].__setitem__("hash_ok", 1),
        lambda row: row["arbiter_input"]["quality"].__setitem__(
            "censored_share", "0"
        ),
        lambda row: row["arbiter_input"]["evidence"].__setitem__("n_eff", True),
        lambda row: row["arbiter_input"]["evidence"].__setitem__(
            "completed_proof_stages", [0, 2]
        ),
        lambda row: row["arbiter_input"]["evidence"]["next_gap"].__setitem__(
            "kind", "MYSTERY"
        ),
        lambda row: row["arbiter_input"]["resource"]["daily_buckets"][0].__setitem__(
            "scan_complete", 1
        ),
        lambda row: row["arbiter_input"]["resource"]["daily_buckets"][0].__setitem__(
            "distinct_entries", True
        ),
        lambda row: row["arbiter_input"]["resource"]["daily_buckets"][0].__setitem__(
            "utc_date", "2026-07-04"
        ),
        lambda row: row["arbiter_input"]["portfolio"].__setitem__(
            "sector_exposure_share", "0.10"
        ),
    ),
)
def test_publisher_rejects_fully_rehashed_noncanonical_arbiter_values(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="arbiter_input_semantics_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row.__setitem__("qualified_raw_outcome_count", 2),
        _inject_unreported_exact_invalid,
    ),
)
def test_publisher_rejects_fully_rehashed_candidate_totals_detached_from_board(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="candidate_board_count_invariant_violation"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row.__setitem__("qualified_duplicate_outcome_row_count", 1),
        lambda row: row.__setitem__(
            "qualified_window_overlap_excluded_entry_count", 1
        ),
        lambda row: row["entry_day_counts"].__setitem__("2026-07-09", 2),
        _detach_distinct_day_count,
        lambda row: row.__setitem__("expected_cost_recomputable_count", 2),
        lambda row: row.__setitem__("tail_cost_recomputable_count", 2),
        _detach_censoring_share,
        _detach_cluster_count,
        lambda row: row["regime_coverage_inputs"].__setitem__(
            "observed_composite_bucket_count", 2
        ),
    ),
)
def test_publisher_rejects_fully_rehashed_candidate_statistical_poison(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="candidate_statistical_invariant_violation"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("source_kind", "mutate"),
    (
        ("clean", _detach_cluster_variance_from_se),
        ("clean", _detach_cluster_se_from_variance),
        ("nonclean", _forge_nonclean_cluster_values),
    ),
)
def test_publisher_rejects_rehashed_cluster_variance_se_algebra_detachment(
    tmp_path: Path,
    source_kind: str,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    if source_kind == "clean":
        _write_five_of_thirty_review(source)
    else:
        _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_cluster_algebra_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: row.__setitem__("identity_complete", False),
        lambda row: row.__setitem__("arbiter_input_complete", 1),
        lambda row: row.__setitem__("selection_eligible", 0),
        lambda row: row.__setitem__("qualified_metrics_actionable", 1),
        lambda row: row.__setitem__("zero_variance_suspect", 0),
        lambda row: row.__setitem__("data_integrity_suspect", 0),
        lambda row: row.__setitem__("cluster_variance_clean", 0),
        lambda row: row.__setitem__("hidden_oos_consumed", 0),
    ),
)
def test_publisher_rejects_fully_rehashed_invalid_candidate_flags(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="candidate_flags_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_fully_rehashed_arbitrary_candidate_blocker(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(source, _add_arbitrary_blocker)

    with pytest.raises(CandidateBoardPublishError, match="candidate_blockers_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("source_kind", "mutate"),
    (
        (
            "canonical",
            lambda row: (
                row.__setitem__(
                    "blockers",
                    sorted({*row["blockers"], "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"}),
                ),
                row.__setitem__("selection_eligible", False),
            ),
        ),
        (
            "below_gate",
            lambda row: row.__setitem__(
                "blockers",
                [
                    code
                    for code in row["blockers"]
                    if code != "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
                ],
            ),
        ),
        (
            "canonical",
            lambda row: (
                row.__setitem__(
                    "blockers",
                    sorted({*row["blockers"], "LEGACY_OPTIMISTIC_COST_UNBACKFILLED"}),
                ),
                row.__setitem__("selection_eligible", False),
            ),
        ),
        (
            "legacy",
            lambda row: row.__setitem__(
                "blockers",
                [
                    code
                    for code in row["blockers"]
                    if code != "LEGACY_OPTIMISTIC_COST_UNBACKFILLED"
                ],
            ),
        ),
    ),
)
def test_publisher_rejects_rehashed_fixed_gate_or_legacy_blocker_detachment(
    tmp_path: Path,
    source_kind: str,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    if source_kind == "canonical":
        _write_five_of_thirty_review(source)
    else:
        _write_nonempty_review(
            source,
            legacy_optimistic_cost=source_kind == "legacy",
        )
    _rewrite_rehashed_candidate(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match="candidate_blockers_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_fully_rehashed_conservative_cost_basis_laundering(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_five_of_thirty_review(source)

    def launder_cost_basis(row: dict[str, object]) -> None:
        n_eff = row["n_eff"]
        assert isinstance(n_eff, int) and n_eff == 30
        row.update(
            {
                "expected_cost_recomputable_count": n_eff,
                "expected_cost_recomputable_share": 1.0,
                "cost_recomputable_share": 1.0,
                "avg_expected_cost_bps": 11.0,
                "tail_cost_recomputable_count": n_eff,
                "tail_cost_recomputable_share": 1.0,
                "avg_tail_cost_bps": 12.0,
                "tail_metric": "cvar90",
                "selection_eligible": True,
                "blockers": [],
            }
        )
        row["arbiter_input"]["quality"]["cost_recomputable_share"] = 1.0

    _rewrite_rehashed_candidate(source, launder_cost_basis)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_fully_rehashed_nonempty_null_mean(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_five_of_thirty_review(source)

    def null_mean(row: dict[str, object]) -> None:
        row["avg_net_bps"] = None
        row["mean_net_e"] = None
        row["arbiter_input"]["evidence"]["mean_net_e"] = None

    _rewrite_rehashed_candidate(source, null_mean)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "field",
    ("avg_expected_cost_bps", "avg_tail_cost_bps"),
)
def test_publisher_rejects_fully_rehashed_negative_cost_average(
    tmp_path: Path,
    field: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_expected_cost_review(source)
    _rewrite_rehashed_candidate(
        source,
        lambda row: row.__setitem__(field, -999.0),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("hash_ok", False),
        ("freshness_ok", False),
        ("integrity_ok", True),
        ("unknown_regime_share", 0.5),
        ("legacy_optimistic_cost_present", True),
    ),
)
def test_publisher_rejects_fully_rehashed_detached_quality_flags(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_candidate(
        source,
        lambda row: row["arbiter_input"]["quality"].__setitem__(field, value),
    )

    with pytest.raises(CandidateBoardPublishError, match="candidate_quality_binding_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize("reason", ("PADDED_REASON", " PADDED_REASON "))
def test_publisher_rejects_noncanonical_zero_count_reason_key(
    tmp_path: Path,
    reason: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_review(
        source,
        lambda payload: payload["learning_candidate_board"].__setitem__(
            "lineage_exclusion_reason_counts", {reason: 0}
        ),
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    _rehash_candidate_board(payload["learning_candidate_board"])
    source.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CandidateBoardPublishError, match="candidate_board_reason_counts_invalid"):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("reason", "named_counter"),
    (
        ("NOT_A_V2_EXCLUSION_REASON", None),
        (
            "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
            "unqualified_raw_valid_evaluation_missing_row_count",
        ),
        (
            "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
            "unqualified_event_outside_evaluation_window_row_count",
        ),
    ),
)
def test_publisher_rejects_rehashed_exclusion_reason_enum_or_named_counter_drift(
    tmp_path: Path,
    reason: str,
    named_counter: str | None,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)

    def mutate(board: dict[str, object]) -> None:
        board["raw_blocked_outcome_row_count"] = 2
        board["unqualified_lineage_outcome_row_count"] = 1
        board["lineage_exclusion_reason_counts"] = {reason: 1}
        if named_counter is not None:
            board[named_counter] = 0

    _rewrite_rehashed_board(source, mutate)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_reason_counts_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda board: board.__setitem__(
            "consistent_duplicate_event_hash_extra_row_count", 1
        ),
        lambda board: board.__setitem__(
            "conflicting_duplicate_event_hash_attribution_row_count", 1
        ),
        lambda board: board.__setitem__(
            "conflicting_duplicate_event_hash_row_count", 1
        ),
        lambda board: board.update(
            {
                "conflicting_duplicate_event_hash_row_count": 2,
                "conflicting_duplicate_event_hash_attribution_row_count": 1,
            }
        ),
    ),
)
def test_publisher_rejects_rehashed_top_duplicate_total_or_ordering_drift(
    tmp_path: Path,
    mutate: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_five_of_thirty_review(source)
    _rewrite_rehashed_board(source, mutate)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_duplicate_totals_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_fully_rehashed_noncanonical_candidate_row_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_two_candidate_review(source)

    def reverse_candidate_rows(board: dict[str, object]) -> None:
        rows = board["candidate_rows"]
        assert isinstance(rows, list) and len(rows) == 2
        rows.reverse()

    _rewrite_rehashed_board(source, reverse_candidate_rows)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_rows_order_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_unique_conflict_below_candidate_attribution(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_duplicate_conflict_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board.__setitem__(
            "conflicting_duplicate_event_hash_row_count", 1
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_duplicate_totals_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_unique_conflict_above_raw_board_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_multi_cohort_unqualified_conflict_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board.__setitem__(
            "conflicting_duplicate_event_hash_row_count", 4
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_duplicate_totals_invalid",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_qualified_raw_count_without_row_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)

    def inflate_qualified_raw_count(board: dict[str, object]) -> None:
        board["raw_blocked_outcome_row_count"] = 2
        board["qualified_lineage_outcome_row_count"] = 2
        row = board["candidate_rows"][0]
        row["qualified_raw_outcome_count"] = 2

    _rewrite_rehashed_board(source, inflate_qualified_raw_count)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_count_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_family_attribution_above_unique_family_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_identity_family_invalid_review(source)

    def inflate_family_attribution(board: dict[str, object]) -> None:
        row = board["candidate_rows"][0]
        row["invalid_lineage_identity_family_row_count"] = 2
        row["lineage_blocker_reason_counts"][
            "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT"
        ] = 2

    _rewrite_rehashed_board(source, inflate_family_attribution)

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_board_count_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_data_integrity_boolean_detachment(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(
            "zero_variance_suspect", True
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_unknown_cost_basis(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(
            "cost_basis_main", "invented_cost_basis"
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_avg_net_detached_from_cluster_mean(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__("avg_net_bps", 4.0),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    "average_field",
    ("avg_expected_cost_bps", "avg_tail_cost_bps"),
)
def test_publisher_rejects_rehashed_average_when_recomputable_count_is_zero(
    tmp_path: Path,
    average_field: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(average_field, 1.0),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("average_field", "poison"),
    (
        ("avg_expected_cost_bps", None),
        ("avg_expected_cost_bps", 1),
        ("avg_tail_cost_bps", None),
        ("avg_tail_cost_bps", 1),
    ),
)
def test_publisher_rejects_rehashed_nonfinite_float_average_when_count_positive(
    tmp_path: Path,
    average_field: str,
    poison: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_expected_cost_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(
            average_field, poison
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


@pytest.mark.parametrize(
    ("expected_cost_track", "tail_metric"),
    ((False, "cvar90"), (True, None)),
)
def test_publisher_rejects_rehashed_tail_metric_count_detachment(
    tmp_path: Path,
    expected_cost_track: bool,
    tail_metric: object,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    writer = _write_expected_cost_review if expected_cost_track else _write_nonempty_review
    writer(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(
            "tail_metric", tail_metric
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_rejects_rehashed_unknown_tail_metric(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_expected_cost_review(source)
    _rewrite_rehashed_board(
        source,
        lambda board: board["candidate_rows"][0].__setitem__(
            "tail_metric", "invented_tail_metric"
        ),
    )

    with pytest.raises(
        CandidateBoardPublishError,
        match="candidate_statistical_invariant_violation",
    ):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_publisher_accepts_valid_board_built_with_nondefault_sample_thresholds(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_nonempty_review(
        source,
        cfg=BlockedOutcomeReviewConfig(
            min_effective_entries_per_side_cell=1,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
        ),
    )

    result = publish_candidate_board(
        source,
        tmp_path / "rendezvous",
        retention_limit=128,
    )

    assert result["status"] == "PUBLISHED"


def test_publisher_accepts_canonical_partial_expected_cost_as_ineligible(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    entry_ts_ms = int(datetime(2026, 7, 9, 12, tzinfo=timezone.utc).timestamp() * 1_000)
    row = attach_candidate_lineage_v2(
        {
            "record_type": "blocked_signal_outcome",
            "entry_ts_ms": entry_ts_ms,
            "gross_bps": None,
            "realized_net_bps": -2.0,
            "net_bps_optimistic": 6.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
        },
        context_id="publisher-partial-expected-cost",
        captured_at_ms=entry_ts_ms,
        as_of_utc_date="2026-07-10",
    )
    slippage_payload = _expected_slippage_payload()
    payload = build_blocked_signal_outcome_review(
        [row],
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        slippage_quantiles=slippage_payload,
    )
    candidate = payload["learning_candidate_board"]["candidate_rows"][0]
    assert candidate["cost_basis_main"] == "expected_slippage_mean_abs_v1"
    assert candidate["n_eff"] == 1
    assert candidate["expected_cost_recomputable_count"] == 0
    assert candidate["tail_cost_recomputable_count"] == 0
    assert "EXPECTED_COST_NOT_FULLY_RECOMPUTABLE" in candidate["blockers"]
    assert "TAIL_COST_NOT_FULLY_RECOMPUTABLE" in candidate["blockers"]
    source.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    slippage_path = tmp_path / "slippage_quantiles_latest.json"
    _write_json_payload(slippage_path, slippage_payload)

    result = publish_candidate_board(
        source,
        tmp_path / "rendezvous",
        retention_limit=128,
        slippage_artifact_path=slippage_path,
        now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )

    assert result["status"] == "PUBLISHED"


def test_publisher_accepts_producer_exact_five_of_thirty_top_day_share(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    payload = _write_five_of_thirty_review(source)
    candidate = payload["learning_candidate_board"]["candidate_rows"][0]
    expected_pct = 5 / 30 * 100.0

    assert candidate["top_entry_day_share_pct"] == expected_pct
    assert candidate["top_entry_day_share"] == expected_pct / 100.0
    assert candidate["top_entry_day_share"] != 5 / 30

    result = publish_candidate_board(
        source,
        tmp_path / "rendezvous",
        retention_limit=128,
    )

    assert result["status"] == "PUBLISHED"


def test_retention_prunes_oldest_before_publish_and_never_exceeds_limit(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    for stamp in ("20260710T090000Z", "20260710T100000Z", "20260710T110000Z"):
        _write_review(destination / f"blocked_outcome_review_{stamp}.json")
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)

    result = publish_candidate_board(source, destination, retention_limit=3)

    names = sorted(path.name for path in destination.glob("blocked_outcome_review_*.json"))
    assert result["retained_file_count"] == 3
    assert names == [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "blocked_outcome_review_latest.json",
        "blocked_outcome_review_partial.json",
    ),
)
def test_refuses_consumer_poisoning_alias_or_partial_file(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    (destination / unsafe_name).write_text("{}\n", encoding="utf-8")
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)

    with pytest.raises(CandidateBoardPublishError, match="unsafe_destination_file"):
        publish_candidate_board(source, destination, retention_limit=128)

    assert not (destination / source.name).exists()


def test_identical_retry_is_idempotent_without_rewriting_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    destination = tmp_path / "rendezvous"
    first = publish_candidate_board(source, destination, retention_limit=128)
    first_inode = (destination / source.name).stat().st_ino

    second = publish_candidate_board(source, destination, retention_limit=128)

    assert first["status"] == "PUBLISHED"
    assert second["status"] == "ALREADY_PUBLISHED"
    assert (destination / source.name).stat().st_ino == first_inode


def test_source_is_bounded_read_from_one_no_follow_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    observed_flags: list[int] = []
    original_open = publisher.os.open

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(path) == source:
            observed_flags.append(flags)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(publisher.os, "open", recording_open)

    publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)

    assert len(observed_flags) == 1
    assert observed_flags[0] & publisher.os.O_NOFOLLOW
    assert observed_flags[0] & publisher.os.O_CLOEXEC


def test_retention_also_prunes_to_consumer_total_byte_bound(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    existing: list[Path] = []
    for stamp in ("20260710T090000Z", "20260710T100000Z", "20260710T110000Z"):
        path = destination / f"blocked_outcome_review_{stamp}.json"
        _write_review(path)
        existing.append(path)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    raw = _write_review(source)
    byte_bound = len(raw) * 2

    result = publish_candidate_board(
        source,
        destination,
        retention_limit=128,
        max_total_bytes=byte_bound,
    )

    retained = sorted(destination.glob("blocked_outcome_review_*.json"))
    assert [path.name for path in retained] == [
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    assert result["retained_total_bytes"] <= byte_bound


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (lambda payload: payload.pop("generated_at_utc"), "generated_at_invalid"),
        (
            lambda payload: payload["learning_candidate_board"].__setitem__(
                "candidate_rows", {}
            ),
            "candidate_rows_invalid",
        ),
        (
            lambda payload: payload["learning_candidate_board"].__setitem__(
                "candidate_rows", ["not-a-mapping"]
            ),
            "candidate_rows_invalid",
        ),
    ),
)
def test_publisher_rejects_source_shapes_the_consumer_cannot_load(
    tmp_path: Path,
    mutate: object,
    reason: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    _rewrite_review(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match=reason):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_failed_atomic_link_does_not_prune_last_good_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    original_names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
    ]
    for name in original_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    monkeypatch.setattr(
        publisher.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("simulated link failure")),
    )

    with pytest.raises(OSError, match="simulated link failure"):
        publish_candidate_board(source, destination, retention_limit=2)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == original_names


def test_failed_first_directory_fsync_rolls_back_new_link_before_pruning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    original_names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
    ]
    for name in original_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    original_fsync = publisher.os.fsync
    directory_fsync_calls = 0

    def fail_first_directory_fsync(descriptor: int) -> None:
        nonlocal directory_fsync_calls
        if stat.S_ISDIR(publisher.os.fstat(descriptor).st_mode):
            directory_fsync_calls += 1
            if directory_fsync_calls == 1:
                raise OSError("simulated directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(publisher.os, "fsync", fail_first_directory_fsync)

    with pytest.raises(OSError, match="simulated directory fsync failure"):
        publish_candidate_board(source, destination, retention_limit=2)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == original_names


def test_identical_retry_applies_lowered_retention_without_rewrite(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in names:
        _write_review(destination / name)
    source = tmp_path / names[-1]
    _write_review(source)
    inode = (destination / source.name).stat().st_ino

    result = publish_candidate_board(source, destination, retention_limit=2)

    assert result["status"] == "ALREADY_PUBLISHED"
    assert result["retained_file_count"] == 2
    assert (destination / source.name).stat().st_ino == inode
    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == names[-2:]


def test_stale_new_snapshot_cannot_replace_newer_retained_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    newest_names = [
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in newest_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T090000Z.json"
    _write_review(source)

    with pytest.raises(
        CandidateBoardPublishError,
        match="source_stamp_not_newer_than_destination",
    ):
        publish_candidate_board(source, destination, retention_limit=1)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == newest_names


def test_stale_identical_retry_never_prunes_newer_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    names = [
        "blocked_outcome_review_20260710T090000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in names:
        _write_review(destination / name)
    source = tmp_path / names[0]
    _write_review(source)

    result = publish_candidate_board(source, destination, retention_limit=1)

    assert result["status"] == "ALREADY_PUBLISHED_STALE"
    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == names


def test_filename_stamp_cannot_be_after_payload_generation_time(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120001Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:00Z")

    with pytest.raises(
        CandidateBoardPublishError,
        match="filename_stamp_after_generated_at",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 13, tzinfo=timezone.utc),
        )


def test_filename_stamp_future_poison_exceeding_skew_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120006Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:06Z")

    with pytest.raises(CandidateBoardPublishError, match="filename_stamp_from_future"):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_payload_generation_future_poison_exceeding_skew_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:06Z")

    with pytest.raises(CandidateBoardPublishError, match="payload_generated_at_from_future"):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_interleaved_newer_publish_cannot_enter_after_older_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    _write_review(destination / "blocked_outcome_review_20260710T110000Z.json")
    older = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    newer = tmp_path / "blocked_outcome_review_20260710T130000Z.json"
    _write_review(older, generated_at_utc="2026-07-10T12:00:00Z")
    _write_review(newer, generated_at_utc="2026-07-10T13:00:00Z")
    older_enumerated = threading.Event()
    release_older = threading.Event()
    original_stamped_files = publisher._stamped_files
    older_first_enumeration = True

    def pause_older_after_precheck(path: Path) -> list[Path]:
        nonlocal older_first_enumeration
        retained = original_stamped_files(path)
        if threading.current_thread().name == "older-publisher" and older_first_enumeration:
            older_first_enumeration = False
            older_enumerated.set()
            assert release_older.wait(timeout=5)
        return retained

    monkeypatch.setattr(publisher, "_stamped_files", pause_older_after_precheck)
    older_result: list[dict[str, object]] = []
    older_errors: list[BaseException] = []

    def publish_older() -> None:
        try:
            older_result.append(
                publish_candidate_board(
                    older,
                    destination,
                    retention_limit=1,
                    now_utc=datetime(2026, 7, 10, 14, tzinfo=timezone.utc),
                )
            )
        except BaseException as exc:  # noqa: BLE001 - thread must report to test.
            older_errors.append(exc)

    thread = threading.Thread(target=publish_older, name="older-publisher")
    thread.start()
    assert older_enumerated.wait(timeout=5)
    try:
        with pytest.raises(
            CandidateBoardPublishError,
            match="destination_lock_unavailable",
        ):
            publish_candidate_board(
                newer,
                destination,
                retention_limit=1,
                now_utc=datetime(2026, 7, 10, 14, tzinfo=timezone.utc),
            )
    finally:
        release_older.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert older_errors == []
    assert older_result[0]["status"] == "PUBLISHED"
    assert [path.name for path in destination.glob("blocked_outcome_review_*.json")] == [
        older.name
    ]
