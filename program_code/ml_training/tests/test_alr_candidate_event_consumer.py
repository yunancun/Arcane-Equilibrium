from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ml_training import alr_event_consumer as consumer
from ml_training import alr_safe_file
from ml_training.alr_candidate_policy import (
    load_candidate_policy_template,
    render_candidate_policy_configuration,
)
from ml_training.alr_event_consumer import (
    main,
    read_candidate_policy_file,
    run_candidate_aware_backlog,
)


_POLICY_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
)


def _candidate_policy() -> dict[str, object]:
    return render_candidate_policy_configuration(
        load_candidate_policy_template(_POLICY_TEMPLATE),
        row_budget=10_000,
        byte_budget=1_000_000,
        collection_window_days=7,
        max_new_entries_per_window=70,
    )


def _rehash_policy(policy: dict[str, object]) -> None:
    body = {key: value for key, value in policy.items() if key != "policy_config_hash"}
    encoded = json.dumps(
        body,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    policy["policy_config_hash"] = hashlib.sha256(encoded).hexdigest()


@pytest.fixture(autouse=True)
def _empty_candidate_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        consumer,
        "fetch_recent_candidate_projection_decisions",
        lambda connection, *, limit: [],
        raising=False,
    )


def _cycles() -> list[dict[str, object]]:
    return [
        {
            "source_hash": f"{ordinal:064x}",
            "source_key": f"scan-{ordinal}|2026-07-10T12:0{ordinal}:00Z",
            "source_ts": f"2026-07-10T12:0{ordinal}:00Z",
            "canonical_payload": {"candidates": [{"symbol": "BTCUSDT"}]},
        }
        for ordinal in range(1, 4)
    ]


def _persisted(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "PERSISTED",
        "artifact_hash": "a" * 64,
        "artifact_rows_written": 1,
        "provenance_rows_written": 3,
        "payload_bytes_written": 512,
        "source_rows_consumed": 3,
        "training_run_rows_written": 0,
        "model_training_performed": False,
    }
    result.update(overrides)
    return result


def _result() -> dict[str, int]:
    return {
        "training_runs": 0,
        "training_duplicates": 0,
        "training_deferred": 0,
        "training_insufficient_source_cycles": 0,
        "defer_suppressions": 0,
        "suppression_duplicate_retries": 0,
        "decision_write_attempts": 1,
        "decision_writes_suppressed": 0,
        "decision_duplicate_retries": 0,
        "operational_artifact_rows_written": 1,
        "operational_provenance_rows_written": 3,
        "operational_run_rows_written": 0,
        "operational_feedback_rows_written": 0,
        "operational_defer_artifact_rows_written": 0,
        "operational_payload_bytes_written": 512,
        "operational_source_rows_consumed": 3,
    }


def test_configured_evidence_is_loaded_built_and_persisted_without_training(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: calls.append(("fetch", limit)) or _cycles(),
    )
    evidence = {
        "source_status": "READY",
        "candidate_rows": [],
        "snapshot_hash": "b" * 64,
    }

    def load(path: Path, **kwargs: object) -> dict[str, object]:
        calls.append(("load_path", path))
        calls.append(("load_args", kwargs))
        return evidence

    monkeypatch.setattr(consumer, "load_candidate_evidence_snapshot", load)

    def build(**kwargs: object) -> dict[str, object]:
        calls.append(("build", kwargs))
        return {"projection": True}

    monkeypatch.setattr(consumer, "build_candidate_aware_learning_projection", build)
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda connection, projection: calls.append(("persist", projection))
        or _persisted(),
    )

    result = run_candidate_aware_backlog(
        object(),
        source_head="c" * 40,
        max_batch=128,
        evidence_directory=tmp_path,
        candidate_policy={"policy_hash": "d" * 64},
        prior_decisions=[{"family_key": "e" * 64}],
    )

    assert result == _result()
    assert calls[0] == ("fetch", 64)
    assert ("load_path", tmp_path) in calls
    build_args = next(value for name, value in calls if name == "build")
    assert build_args["cycles"] == _cycles()
    assert build_args["evidence_snapshot"] is evidence
    assert build_args["policy"] == {
        "policy_hash": "d" * 64,
        "decision_ts_s": 1_783_684_980,
        "as_of_utc_date": "2026-07-10",
    }
    assert build_args["prior_decisions"] == [{"family_key": "e" * 64}]


def test_each_cycle_injects_fresh_decision_clock_without_changing_policy_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = datetime(2026, 7, 10, 12, 3, tzinfo=timezone.utc)
    offsets = (0, 1, 1_799, 1_800)
    cycle_sets: list[list[dict[str, object]]] = []
    for offset in offsets:
        cycles = _cycles()
        evaluated_at = start + timedelta(seconds=offset)
        cycles[-1]["source_ts"] = evaluated_at.isoformat().replace(
            "+00:00", "Z"
        )
        cycle_sets.append(cycles)
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: cycle_sets.pop(0),
    )
    observed: list[dict[str, object]] = []

    def build(**kwargs: object) -> dict[str, object]:
        observed.append(dict(kwargs["policy"]))
        return {"projection": True}

    monkeypatch.setattr(consumer, "build_candidate_aware_learning_projection", build)
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda connection, projection: _persisted(),
    )
    semantic_policy = {
        "policy_config_hash": "d" * 64,
        "decision_ts_s": 1,
        "as_of_utc_date": "1970-01-01",
    }

    for _ in offsets:
        run_candidate_aware_backlog(
            object(),
            source_head="c" * 40,
            max_batch=32,
            candidate_policy=semantic_policy,
            prior_decisions=[],
        )

    assert [item["decision_ts_s"] for item in observed] == [
        int((start + timedelta(seconds=offset)).timestamp())
        for offset in offsets
    ]
    assert {item["as_of_utc_date"] for item in observed} == {"2026-07-10"}
    assert {item["policy_config_hash"] for item in observed} == {"d" * 64}
    assert semantic_policy["decision_ts_s"] == 1
    assert semantic_policy["as_of_utc_date"] == "1970-01-01"


def test_missing_evidence_configuration_persists_durable_repair_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles(),
    )
    monkeypatch.setattr(
        consumer,
        "load_candidate_evidence_snapshot",
        lambda *args, **kwargs: pytest.fail("unconfigured path must not be read"),
    )

    def build(**kwargs: object) -> dict[str, object]:
        captured.append(kwargs["evidence_snapshot"])
        return {"durable_rotation": True}

    monkeypatch.setattr(consumer, "build_candidate_aware_learning_projection", build)
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda connection, projection: _persisted(),
    )

    result = run_candidate_aware_backlog(
        object(),
        source_head="c" * 40,
        max_batch=32,
    )

    assert result == _result()
    assert captured[0]["source_status"] == "EVIDENCE_DIRECTORY_NOT_CONFIGURED"
    assert captured[0]["schema_version"] == "alr_candidate_evidence_snapshot_v2"
    assert captured[0]["selection_allowed"] is False
    assert captured[0]["candidate_rows"] == []
    assert len(captured[0]["snapshot_hash"]) == 64


def test_projection_duplicate_is_not_mislabeled_as_training_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles(),
    )
    monkeypatch.setattr(
        consumer,
        "build_candidate_aware_learning_projection",
        lambda **kwargs: {"projection": True},
    )
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda connection, projection: _persisted(
            status="DUPLICATE",
            artifact_rows_written=0,
            provenance_rows_written=0,
            payload_bytes_written=0,
            source_rows_consumed=0,
        ),
    )

    result = run_candidate_aware_backlog(
        object(), source_head="c" * 40, max_batch=32
    )

    assert result["training_duplicates"] == 0
    assert result["decision_duplicate_retries"] == 1
    assert result["operational_artifact_rows_written"] == 0
    assert result["operational_run_rows_written"] == 0


def test_default_path_reads_bounded_prior_decisions_for_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = [
        {
            "decision_schema_version": "alr_candidate_learning_decision_v2",
            "family_key": "a" * 64,
            "material_fingerprint": "b" * 64,
            "decision_ts_s": 1_783_684_000,
        }
    ]
    observed: list[object] = []
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles(),
    )
    monkeypatch.setattr(
        consumer,
        "fetch_recent_candidate_projection_decisions",
        lambda connection, *, limit: observed.append(limit) or history,
        raising=False,
    )

    def build(**kwargs: object) -> dict[str, object]:
        observed.append(kwargs["prior_decisions"])
        return {"projection": True}

    monkeypatch.setattr(consumer, "build_candidate_aware_learning_projection", build)
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda connection, projection: _persisted(),
    )

    run_candidate_aware_backlog(
        object(), source_head="c" * 40, max_batch=32
    )

    assert observed == [64, history]


def test_programming_failure_is_not_silently_rewritten_as_defer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles(),
    )
    monkeypatch.setattr(
        consumer,
        "build_candidate_aware_learning_projection",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("broken_contract")),
    )

    with pytest.raises(RuntimeError, match="broken_contract"):
        run_candidate_aware_backlog(
            object(), source_head="c" * 40, max_batch=32
        )


def test_insufficient_scanner_cycles_do_not_create_an_unbound_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer,
        "fetch_untrained_scanner_cycles",
        lambda connection, *, limit: _cycles()[:2],
    )
    monkeypatch.setattr(
        consumer,
        "persist_candidate_learning_projection",
        lambda *args, **kwargs: pytest.fail("must not persist without source floor"),
    )

    result = run_candidate_aware_backlog(
        object(), source_head="c" * 40, max_batch=32
    )

    assert result["training_insufficient_source_cycles"] == 1
    assert result["decision_write_attempts"] == 0


def test_candidate_policy_file_is_explicit_private_regular_json(tmp_path: Path) -> None:
    path = tmp_path / "candidate-policy.json"
    path.write_text(json.dumps(_candidate_policy()) + "\n", encoding="utf-8")
    path.chmod(0o600)

    loaded = read_candidate_policy_file(path)

    assert loaded == _candidate_policy()


def test_candidate_policy_read_uses_no_follow_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "candidate-policy.json"
    path.write_text(json.dumps(_candidate_policy()) + "\n", encoding="utf-8")
    path.chmod(0o600)
    original = alr_safe_file.os.open
    observed_flags: list[int] = []

    def recording_open(target, flags, *args, **kwargs):
        observed_flags.append(flags)
        return original(target, flags, *args, **kwargs)

    monkeypatch.setattr(alr_safe_file.os, "open", recording_open)

    assert read_candidate_policy_file(path) == _candidate_policy()
    assert observed_flags[-1] & alr_safe_file.os.O_NOFOLLOW
    assert observed_flags[-1] & alr_safe_file.os.O_CLOEXEC


def test_candidate_policy_file_rejects_symlink_or_broad_mode(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "policy.json"
    link.symlink_to(target)
    with pytest.raises(consumer.AlrEventConsumerError, match="candidate_policy_not_regular"):
        read_candidate_policy_file(link)

    target.chmod(0o640)
    with pytest.raises(consumer.AlrEventConsumerError, match="candidate_policy_mode_invalid"):
        read_candidate_policy_file(target)


@pytest.mark.parametrize("content", ("[]", "{", '{"row_budget":NaN}'))
def test_candidate_policy_file_rejects_non_mapping_or_invalid_json(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "policy.json"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(consumer.AlrEventConsumerError, match="candidate_policy_json_invalid"):
        read_candidate_policy_file(path)


def test_candidate_policy_file_rejects_semantically_incomplete_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policy.json"
    path.write_text("{}\n", encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(
        consumer.AlrEventConsumerError,
        match="candidate_policy_semantics_invalid",
    ):
        read_candidate_policy_file(path)


def test_entrypoint_missing_runtime_policy_keeps_listener_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    def fake_run_event_consumer(**kwargs: object) -> dict[str, int]:
        observed.update(kwargs)
        return {"training_runs": 0, "decision_write_attempts": 1}

    monkeypatch.setattr(consumer, "run_event_consumer", fake_run_event_consumer)

    rc = main(
        [
            "--dsn-file",
            str(tmp_path / "unused.dsn"),
            "--lock-file",
            str(tmp_path / "unused.lock"),
            "--source-head",
            "c" * 40,
            "--candidate-evidence-dir",
            str(tmp_path / "evidence"),
            "--candidate-policy-file",
            str(tmp_path / "missing-policy.json"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert observed["candidate_policy"] is None
    assert payload["candidate_policy"]["status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert payload["schema_version"] == "alr_event_consumer_result_v2"
    assert payload["result"]["training_runs"] == 0
    assert set(payload["authority_counters"].values()) == {0}


def test_entrypoint_semantic_policy_drift_keeps_listener_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[object] = []
    monkeypatch.setattr(
        consumer,
        "run_event_consumer",
        lambda **kwargs: observed.append(kwargs["candidate_policy"])
        or {"training_runs": 0, "decision_write_attempts": 1},
    )
    noncanonical = _candidate_policy()
    noncanonical["unknown_portfolio_penalty"] = "1.0"
    _rehash_policy(noncanonical)

    for index, content in enumerate(("{}", json.dumps(noncanonical))):
        policy_path = tmp_path / f"invalid-{index}.json"
        policy_path.write_text(content + "\n", encoding="utf-8")
        policy_path.chmod(0o600)
        rc = main(
            [
                "--dsn-file",
                str(tmp_path / "unused.dsn"),
                "--lock-file",
                str(tmp_path / "unused.lock"),
                "--source-head",
                "c" * 40,
                "--candidate-evidence-dir",
                str(tmp_path / "evidence"),
                "--candidate-policy-file",
                str(policy_path),
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["candidate_policy"]["status"] == "UNAVAILABLE_FAIL_CLOSED"
        assert payload["result"]["training_runs"] == 0
        assert set(payload["authority_counters"].values()) == {0}

    assert observed == [None, None]


def test_atomic_v2_cutover_does_not_rename_existing_single_instance_lock() -> None:
    assert consumer._SINGLE_INSTANCE_LOCK_NAME == "alr_event_consumer_v1"
