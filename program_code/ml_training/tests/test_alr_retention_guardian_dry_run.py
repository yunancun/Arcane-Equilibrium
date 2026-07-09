from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import pytest

from ml_training import alr_retention_guardian_dry_run as guardian
from ml_training.alr_retention_guardian_dry_run import (
    ALLOWED_RETENTION_STATES,
    BOUNDARY_LABEL,
    DRY_RUN_OUTPUT_NAME,
    INPUT_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    STATE_DISPUTED_PROTECTED,
    STATE_LINEAGE_PROVENANCE_PROTECTED,
    STATE_NEGATIVE_EXAMPLE_PROTECTED,
    STATE_PROOF_OR_AUDIT_PROTECTED,
    STATE_REFERENCE_UNKNOWN_PROTECTED,
    STATE_REBUILDABLE_SCRATCH_CANDIDATE,
    STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY,
    STOP_RETENTION_RISK,
    build_retention_guardian_dry_run,
    compute_artifact_manifest_hash,
    compute_reference_graph_hash,
    compute_retention_guardian_dry_run_hash,
    main,
    validate_retention_guardian_dry_run,
)


def _artifact(tmp_path: Path, artifact_id: str, **overrides) -> dict:
    body = overrides.pop("body", f"{artifact_id}\n".encode("utf-8"))
    path = tmp_path / f"{artifact_id}.json"
    path.write_bytes(body)
    stat = path.stat()
    row = {
        "artifact_id": artifact_id,
        "canonical_path": str(path),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "producer": "unit_test",
        "schema_version": "scratch_artifact_v1",
        "candidate_identity": {},
        "source_hash": "",
        "input_hashes": [],
        "order_ids": [],
        "fill_ids": [],
        "context_ids": [],
        "outbound_refs": [],
        "inbound_refs": [],
        "report_refs": [],
        "todo_refs": [],
        "adr_refs": [],
        "amd_refs": [],
        "_latest_refs": [],
        "classification_reason": "ordinary scratch",
        "retention_state": STATE_REBUILDABLE_SCRATCH_CANDIDATE,
        "blockers": [],
        "rebuild_or_disposable_proof": {"disposable": True, "proof_complete": True},
        "proposed_action": "NONE",
    }
    row.update(overrides)
    return row


def _manifest(artifacts: list[dict], **overrides) -> dict:
    manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "created_at": "2026-07-09T00:00:00Z",
        "source_head": "a" * 40,
        "latest_alias_used": False,
        "no_authority": {"runtime": False, "pg": False, "order_or_probe": False},
        "artifacts": artifacts,
    }
    manifest.update(overrides)
    manifest["manifest_hash"] = compute_artifact_manifest_hash(manifest)
    return manifest


def _row_by_id(dry_run: dict, artifact_id: str) -> dict:
    for row in dry_run["artifacts"]:
        if row["artifact_id"] == artifact_id:
            return row
    raise AssertionError(f"missing row {artifact_id}")


def _assert_stop(row: dict) -> None:
    assert row["retention_state"] in ALLOWED_RETENTION_STATES
    assert row["retention_state"] != STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY
    assert STOP_RETENTION_RISK in row["blockers"]
    assert row["proposed_action"] == "NONE_PROTECTED"


def test_valid_cli_writes_exactly_retention_guardian_dry_run_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    out_dir = tmp_path / "dry_run_out"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")]), sort_keys=True),
        encoding="utf-8",
    )

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 0

    assert sorted(path.name for path in out_dir.iterdir()) == [DRY_RUN_OUTPUT_NAME]
    output = json.loads((out_dir / DRY_RUN_OUTPUT_NAME).read_text(encoding="utf-8"))
    validation = validate_retention_guardian_dry_run(output)
    assert validation.valid is True
    assert validation.tombstone_count == 1


def test_manifest_reference_graph_and_dry_run_hashes_recompute(tmp_path: Path) -> None:
    manifest = _manifest([_artifact(tmp_path, "scratch")])
    dry_run = build_retention_guardian_dry_run(manifest)

    assert manifest["manifest_hash"] == compute_artifact_manifest_hash(manifest)
    assert dry_run["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert dry_run["reference_graph_hash"] == compute_reference_graph_hash(
        dry_run["reference_graph"]
    )
    assert dry_run["manifest_hash"] == compute_retention_guardian_dry_run_hash(dry_run)
    assert validate_retention_guardian_dry_run(dry_run).valid is True


def test_proof_audit_artifact_is_protected(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest([_artifact(tmp_path, "audit-row", order_ids=["order-1"])])
    )
    row = _row_by_id(dry_run, "audit-row")

    assert row["retention_state"] == STATE_PROOF_OR_AUDIT_PROTECTED
    _assert_stop(row)


def test_disputed_artifact_is_protected(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest(
            [
                _artifact(
                    tmp_path,
                    "disputed-row",
                    classification_reason="disputed operator review",
                )
            ]
        )
    )
    row = _row_by_id(dry_run, "disputed-row")

    assert row["retention_state"] == STATE_DISPUTED_PROTECTED
    _assert_stop(row)


def test_negative_or_falsification_artifact_is_protected(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest(
            [
                _artifact(
                    tmp_path,
                    "negative-row",
                    classification_reason="negative falsification example",
                )
            ]
        )
    )
    row = _row_by_id(dry_run, "negative-row")

    assert row["retention_state"] == STATE_NEGATIVE_EXAMPLE_PROTECTED
    _assert_stop(row)


def test_lineage_or_provenance_artifact_is_protected(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest([_artifact(tmp_path, "lineage-row", input_hashes=["b" * 64])])
    )
    row = _row_by_id(dry_run, "lineage-row")

    assert row["retention_state"] == STATE_LINEAGE_PROVENANCE_PROTECTED
    _assert_stop(row)


def test_transitive_reference_to_protected_artifact_protects_scratch(tmp_path: Path) -> None:
    scratch = _artifact(tmp_path, "scratch", outbound_refs=["middle"])
    middle = _artifact(tmp_path, "middle", outbound_refs=["proof-artifact"])
    proof = _artifact(
        tmp_path,
        "proof-artifact",
        schema_version="proof_packet_v1",
        fill_ids=["fill-1"],
    )

    dry_run = build_retention_guardian_dry_run(_manifest([scratch, middle, proof]))

    scratch_row = _row_by_id(dry_run, "scratch")
    middle_row = _row_by_id(dry_run, "middle")
    assert scratch_row["retention_state"] == STATE_LINEAGE_PROVENANCE_PROTECTED
    assert middle_row["retention_state"] == STATE_LINEAGE_PROVENANCE_PROTECTED
    assert "transitive_protected_reference" in scratch_row["blockers"]
    assert "transitive_protected_reference" in middle_row["blockers"]
    _assert_stop(scratch_row)
    _assert_stop(middle_row)


def test_unknown_reference_fails_closed_as_reference_unknown(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest([_artifact(tmp_path, "scratch", outbound_refs=["missing-artifact"])])
    )
    row = _row_by_id(dry_run, "scratch")

    assert row["retention_state"] == STATE_REFERENCE_UNKNOWN_PROTECTED
    assert "reference_unknown" in row["blockers"]
    _assert_stop(row)


@pytest.mark.parametrize(
    "field",
    ("report_refs", "todo_refs", "adr_refs", "amd_refs", "context_ids", "input_hashes"),
)
def test_reference_fields_create_graph_edges_and_protect_targets(
    tmp_path: Path, field: str
) -> None:
    source = _artifact(tmp_path, "source", **{field: ["target"]})
    target = _artifact(tmp_path, "target")

    dry_run = build_retention_guardian_dry_run(_manifest([source, target]))
    target_row = _row_by_id(dry_run, "target")

    assert {"from": "source", "to": "target", "field": field} in dry_run["reference_graph"][
        "edges"
    ]
    assert "reference_contact_not_transitively_empty" in target_row["blockers"]
    _assert_stop(target_row)


def test_input_hashes_create_edges_by_target_content_sha256(tmp_path: Path) -> None:
    artifact_dir = tmp_path.parent / "sha_edge_case"
    artifact_dir.mkdir()
    target = _artifact(artifact_dir, "target")
    source = _artifact(artifact_dir, "source", input_hashes=[target["content_sha256"]])

    dry_run = build_retention_guardian_dry_run(_manifest([source, target]))
    target_row = _row_by_id(dry_run, "target")

    assert {"from": "source", "to": "target", "field": "input_hashes"} in dry_run[
        "reference_graph"
    ]["edges"]
    assert "reference_contact_not_transitively_empty" in target_row["blockers"]
    _assert_stop(target_row)


def test_missing_artifact_fields_fail_closed_before_defaults(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "scratch")
    del artifact["producer"]

    dry_run = build_retention_guardian_dry_run(_manifest([artifact]))
    row = _row_by_id(dry_run, "scratch")

    assert "producer_missing" in row["blockers"]
    _assert_stop(row)


def test_extra_artifact_fields_fail_closed(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "scratch", unexpected_authority_claim=True)

    dry_run = build_retention_guardian_dry_run(_manifest([artifact]))
    row = _row_by_id(dry_run, "scratch")

    assert "unexpected_authority_claim_unexpected" in row["blockers"]
    _assert_stop(row)


def test_manifest_hash_mismatch_protects_artifacts(tmp_path: Path) -> None:
    manifest = _manifest([_artifact(tmp_path, "scratch")])
    manifest["manifest_hash"] = "0" * 64

    dry_run = build_retention_guardian_dry_run(manifest)
    row = _row_by_id(dry_run, "scratch")

    assert row["retention_state"] == STATE_LINEAGE_PROVENANCE_PROTECTED
    assert "manifest_hash_mismatch" in row["blockers"]
    _assert_stop(row)


def test_latest_refs_fail_closed(tmp_path: Path) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest([_artifact(tmp_path, "scratch", _latest_refs=["artifact_latest.json"])])
    )
    row = _row_by_id(dry_run, "scratch")

    assert "latest_refs_non_empty" in row["blockers"]
    _assert_stop(row)


def test_only_unreferenced_rebuildable_scratch_reaches_tombstone_dry_run(
    tmp_path: Path,
) -> None:
    dry_run = build_retention_guardian_dry_run(
        _manifest([_artifact(tmp_path, "scratch", rebuild_or_disposable_proof={"rebuildable": True})])
    )
    row = _row_by_id(dry_run, "scratch")

    assert row["retention_state"] == STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY
    assert row["blockers"] == []
    assert row["proposed_action"] == "TOMBSTONE_STAGE_1_DRY_RUN_ONLY"


def test_cli_rejects_latest_input_output_and_writes_nothing(tmp_path: Path) -> None:
    manifest = _manifest([_artifact(tmp_path, "scratch")])
    latest_manifest_path = tmp_path / "artifact_manifest_latest.json"
    latest_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    out_dir = tmp_path / "out"

    assert main(["--artifact-manifest", str(latest_manifest_path), "--out-dir", str(out_dir)]) == 2
    assert not out_dir.exists()

    manifest_path = tmp_path / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    latest_out_dir = tmp_path / "out_latest"

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(latest_out_dir)]) == 2
    assert not latest_out_dir.exists()


def test_cli_rejects_forbidden_output_authority_paths_and_writes_nothing(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")])),
        encoding="utf-8",
    )
    out_dir = tmp_path / "order_scope"

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 2
    assert not out_dir.exists()


def test_cli_rejects_non_empty_output_dir_and_writes_nothing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")])),
        encoding="utf-8",
    )
    out_dir = tmp_path / "dry_run_out"
    out_dir.mkdir()
    sentinel = out_dir / "sentinel.json"
    sentinel.write_text("{}", encoding="utf-8")

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 2
    assert sorted(path.name for path in out_dir.iterdir()) == ["sentinel.json"]


def test_cli_rejects_broken_output_symlink_and_writes_nothing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")])),
        encoding="utf-8",
    )
    out_dir = tmp_path / "dry_run_out"
    out_dir.mkdir()
    output_path = out_dir / DRY_RUN_OUTPUT_NAME
    escaped_target = tmp_path / "escaped.json"
    output_path.symlink_to(escaped_target)

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 2
    assert output_path.is_symlink()
    assert not escaped_target.exists()


def test_cli_rejects_symlinked_output_dir_to_forbidden_target(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")])),
        encoding="utf-8",
    )
    forbidden_target = tmp_path / "runtime"
    forbidden_target.mkdir()
    out_dir = tmp_path / "safe_output"
    out_dir.symlink_to(forbidden_target, target_is_directory=True)

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 2
    assert sorted(path.name for path in forbidden_target.iterdir()) == []


def test_cli_rejects_symlinked_output_parent_and_writes_nothing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_artifact(tmp_path, "scratch")])),
        encoding="utf-8",
    )
    forbidden_target = tmp_path / "runtime"
    forbidden_target.mkdir()
    parent_link = tmp_path / "safe_parent"
    parent_link.symlink_to(forbidden_target, target_is_directory=True)
    out_dir = parent_link / "dry_run_out"

    assert main(["--artifact-manifest", str(manifest_path), "--out-dir", str(out_dir)]) == 2
    assert not (forbidden_target / "dry_run_out").exists()


def test_static_guard_has_no_destructive_imports_or_calls() -> None:
    source = Path(guardian.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "os",
        "subprocess",
        "shutil",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "aiohttp",
        "psycopg",
        "asyncpg",
        "sqlalchemy",
    }
    forbidden_name_calls = {
        "__import__",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "setattr",
    }
    forbidden_attribute_calls = {
        "unlink",
        "remove",
        "rmtree",
        "rename",
        "replace",
        "chmod",
        "rmdir",
        "symlink_to",
        "hardlink_to",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in forbidden_import_roots
                assert "prune" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module.split(".", 1)[0] not in forbidden_import_roots
            assert "retention" not in module
            assert "prune" not in module
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
                assert name not in forbidden_attribute_calls
            elif isinstance(func, ast.Name):
                name = func.id
                assert name not in forbidden_name_calls

    upper_source = source.upper()
    forbidden_source_tokens = (
        "DELETE FROM",
        "DROP TABLE",
        "ALTER TABLE",
        "INSERT INTO",
        "CREATE TABLE",
        "UPDATE ",
        "RM -RF",
        "--APPLY",
        "--DELETE",
        "--PRUNE",
        "OS.SYSTEM",
        "SUBPROCESS.",
        "SOCKET.",
        "REQUESTS.",
        "HTTPX.",
        "PSYCOPG",
        "ASYNCPG",
        "SQLALCHEMY",
        "__IMPORT__",
    )
    for token in forbidden_source_tokens:
        assert token not in upper_source
