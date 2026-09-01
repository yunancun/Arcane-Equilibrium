from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from helper_scripts.ci import verify_pytest_shards as verifier


SOURCE_SHA = "a" * 40


def _manifest(nodeids: list[str]) -> str:
    payload = b"\n".join(nodeid.encode("utf-8") for nodeid in nodeids)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _nodeids(count: int = 8) -> list[str]:
    return [f"tests/structure/test_fixture_{index:04d}.py::test_case" for index in range(count)]


def _payloads(
    *, count: int = 4, minimum: int = 8, full_count: int = 8
) -> list[dict[str, object]]:
    full = _nodeids(full_count)
    payloads = []
    for index in range(count):
        selected = full[index::count]
        payloads.append(
            {
                "schema_version": "governance_pytest_shard_evidence_v1",
                "source_sha": SOURCE_SHA,
                "shard_index": index,
                "shard_count": count,
                "minimum_count": minimum,
                "full_count": len(full),
                "selected_count": len(selected),
                "full_manifest_sha256": _manifest(full),
                "selected_manifest_sha256": _manifest(selected),
                "selected_nodeids": selected,
            }
        )
    return payloads


def _write_bundle(root: Path, payloads: list[dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for directory_index, payload in enumerate(payloads):
        directory = root / f"governance-pytest-shard-{directory_index}"
        directory.mkdir()
        path = directory / f"governance-pytest-shard-{directory_index}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


def _verify(root: Path, *, count: int = 4, minimum: int = 8) -> dict[str, object]:
    return verifier.verify_shard_artifacts(
        root,
        expected_source_sha=SOURCE_SHA,
        expected_shard_count=count,
        expected_minimum_count=minimum,
    )


def test_valid_independent_bundle_is_exhaustive_disjoint_balanced_and_replayable(tmp_path) -> None:
    _write_bundle(tmp_path, _payloads())
    assert _verify(tmp_path) == {
        "full_count": 8,
        "full_manifest_sha256": _manifest(_nodeids()),
        "selected_counts": [2, 2, 2, 2],
        "shard_indices": [0, 1, 2, 3],
        "shard_count": 4,
        "source_sha": SOURCE_SHA,
    }


def test_equal_count_divergent_full_manifest_fails_closed(tmp_path) -> None:
    payloads = _payloads()
    alternate_full = [
        f"tests/structure/test_alternate_{index:04d}.py::test_case"
        for index in range(8)
    ]
    alternate_selected = alternate_full[3::4]
    payloads[3]["selected_nodeids"] = alternate_selected
    payloads[3]["selected_count"] = len(alternate_selected)
    payloads[3]["selected_manifest_sha256"] = _manifest(alternate_selected)
    payloads[3]["full_manifest_sha256"] = _manifest(alternate_full)
    assert payloads[3]["full_count"] == len(alternate_full) == 8
    assert payloads[3]["selected_count"] == 2
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="common full manifest"):
        _verify(tmp_path)


def test_exact_hosted_floor_eight_shard_receipt_is_balanced(tmp_path) -> None:
    _write_bundle(
        tmp_path,
        _payloads(count=8, minimum=4548, full_count=4548),
    )
    receipt = _verify(tmp_path, count=8, minimum=4548)
    assert receipt["shard_indices"] == list(range(8))
    assert receipt["selected_counts"] == [569, 569, 569, 569, 568, 568, 568, 568]
    assert receipt["full_count"] == 4548


@pytest.mark.parametrize("mutation", ["missing", "extra", "recursive", "name_index"])
def test_artifact_layout_tampering_fails_closed(tmp_path, mutation: str) -> None:
    payloads = _payloads()
    _write_bundle(tmp_path, payloads)
    if mutation == "missing":
        (tmp_path / "governance-pytest-shard-3" / "governance-pytest-shard-3.json").unlink()
    elif mutation == "extra":
        (tmp_path / "unexpected").mkdir()
    elif mutation == "recursive":
        (tmp_path / "governance-pytest-shard-3" / "nested").mkdir()
    else:
        path = tmp_path / "governance-pytest-shard-3" / "governance-pytest-shard-3.json"
        path.rename(path.with_name("governance-pytest-shard-2.json"))
    with pytest.raises(verifier.ShardEvidenceError):
        _verify(tmp_path)


def test_symlinked_artifact_directory_or_file_fails_closed(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    _write_bundle(real, _payloads())
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    for index in range(4):
        (linked_root / f"governance-pytest-shard-{index}").symlink_to(
            real / f"governance-pytest-shard-{index}", target_is_directory=True
        )
    with pytest.raises(verifier.ShardEvidenceError, match="symlink"):
        _verify(linked_root)

    file_root = tmp_path / "file-linked"
    _write_bundle(file_root, _payloads())
    path = file_root / "governance-pytest-shard-3" / "governance-pytest-shard-3.json"
    target = real / "governance-pytest-shard-3" / "governance-pytest-shard-3.json"
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(verifier.ShardEvidenceError, match="symlink"):
        _verify(file_root)


def test_duplicate_json_keys_and_file_size_cap_fail_closed(tmp_path, monkeypatch) -> None:
    _write_bundle(tmp_path, _payloads())
    path = tmp_path / "governance-pytest-shard-0" / "governance-pytest-shard-0.json"
    path.write_text('{"schema_version":"x","schema_version":"y"}\n', encoding="utf-8")
    with pytest.raises(verifier.ShardEvidenceError, match="duplicate JSON key"):
        _verify(tmp_path)

    other = tmp_path / "oversize"
    _write_bundle(other, _payloads())
    monkeypatch.setattr(verifier, "MAX_EVIDENCE_BYTES", 8)
    with pytest.raises(verifier.ShardEvidenceError, match="size cap"):
        _verify(other)


def test_malformed_or_non_object_json_fails_closed(tmp_path) -> None:
    for suffix, content in (("malformed", "{\n"), ("array", "[]\n")):
        root = tmp_path / suffix
        _write_bundle(root, _payloads())
        path = root / "governance-pytest-shard-0" / "governance-pytest-shard-0.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(verifier.ShardEvidenceError, match="JSON|object"):
            _verify(root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "wrong", "schema"),
        ("source_sha", "A" * 40, "source SHA"),
        ("shard_index", True, "integer"),
        ("shard_count", True, "integer"),
        ("minimum_count", True, "integer"),
        ("full_count", True, "integer"),
        ("selected_count", True, "integer"),
        ("full_manifest_sha256", "sha256:" + "G" * 64, "manifest SHA"),
        ("selected_manifest_sha256", "b" * 64, "manifest SHA"),
        ("selected_nodeids", "not-a-list", "selected_nodeids"),
    ],
)
def test_exact_schema_types_and_sha_formats_fail_closed(
    tmp_path, field: str, value: object, message: str
) -> None:
    payloads = _payloads()
    payloads[0][field] = value
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match=message):
        _verify(tmp_path)


def test_missing_or_extra_field_fails_closed(tmp_path) -> None:
    for suffix, mutate in (
        ("missing", lambda payload: payload.pop("minimum_count")),
        ("extra", lambda payload: payload.__setitem__("timestamp", "forbidden")),
    ):
        root = tmp_path / suffix
        payloads = _payloads()
        mutate(payloads[0])
        _write_bundle(root, payloads)
        with pytest.raises(verifier.ShardEvidenceError, match="exact fields"):
            _verify(root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_sha", "b" * 40, "expected source"),
        ("shard_count", 5, "expected shard count"),
        ("minimum_count", 7, "expected minimum"),
        ("full_count", 9, "common full count"),
    ],
)
def test_worker_binding_mismatch_fails_closed(
    tmp_path, field: str, value: object, message: str
) -> None:
    payloads = _payloads()
    payloads[2][field] = value
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match=message):
        _verify(tmp_path)


def test_duplicate_or_missing_payload_index_fails_closed(tmp_path) -> None:
    payloads = _payloads()
    payloads[3]["shard_index"] = 2
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="name/index"):
        _verify(tmp_path)


@pytest.mark.parametrize("mutation", ["unsorted", "duplicate", "oversized", "invalid"])
def test_selected_nodeids_are_canonical_unique_bounded_tests(tmp_path, mutation: str) -> None:
    payloads = _payloads()
    selected = list(payloads[0]["selected_nodeids"])
    if mutation == "unsorted":
        selected.reverse()
    elif mutation == "duplicate":
        selected[1] = selected[0]
    elif mutation == "oversized":
        selected[0] = "tests/test_x.py::test_" + "x" * (verifier.MAX_NODEID_BYTES + 1)
    else:
        selected[0] = "outside/test_x.py::test_x"
    payloads[0]["selected_nodeids"] = selected
    payloads[0]["selected_manifest_sha256"] = _manifest(selected)
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError):
        _verify(tmp_path)


@pytest.mark.parametrize("field", ["selected_count", "selected_manifest_sha256"])
def test_local_selected_count_and_manifest_are_recomputed(tmp_path, field: str) -> None:
    payloads = _payloads()
    payloads[0][field] = 3 if field == "selected_count" else "sha256:" + "b" * 64
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="local selected"):
        _verify(tmp_path)


def test_unbalanced_sizes_fail_closed_even_with_valid_local_manifests(tmp_path) -> None:
    payloads = _payloads()
    moved = payloads[0]["selected_nodeids"].pop()
    payloads[1]["selected_nodeids"].append(moved)
    payloads[1]["selected_nodeids"].sort(key=lambda value: value.encode("utf-8"))
    for payload in payloads[:2]:
        selected = payload["selected_nodeids"]
        payload["selected_count"] = len(selected)
        payload["selected_manifest_sha256"] = _manifest(selected)
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="balanced"):
        _verify(tmp_path)


def test_selected_lists_must_be_disjoint(tmp_path) -> None:
    payloads = _payloads()
    payloads[1]["selected_nodeids"][0] = payloads[0]["selected_nodeids"][0]
    payloads[1]["selected_nodeids"].sort(key=lambda value: value.encode("utf-8"))
    payloads[1]["selected_manifest_sha256"] = _manifest(payloads[1]["selected_nodeids"])
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="disjoint"):
        _verify(tmp_path)


@pytest.mark.parametrize(
    ("field", "message"),
    [("full_count", "balanced"), ("full_manifest_sha256", "union")],
)
def test_exact_union_count_and_manifest_are_recomputed(
    tmp_path, field: str, message: str
) -> None:
    payloads = _payloads()
    value: object = 9 if field == "full_count" else "sha256:" + "b" * 64
    for payload in payloads:
        payload[field] = value
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match=message):
        _verify(tmp_path)


def test_modulo_partition_is_replayed_not_inferred_from_union(tmp_path) -> None:
    payloads = _payloads()
    left = payloads[0]["selected_nodeids"]
    right = payloads[1]["selected_nodeids"]
    left[0], right[0] = right[0], left[0]
    for payload in payloads[:2]:
        payload["selected_nodeids"].sort(key=lambda value: value.encode("utf-8"))
        payload["selected_manifest_sha256"] = _manifest(payload["selected_nodeids"])
    _write_bundle(tmp_path, payloads)
    with pytest.raises(verifier.ShardEvidenceError, match="modulo replay"):
        _verify(tmp_path)


def test_module_is_pure_stdlib_and_has_no_pytest_import() -> None:
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    assert "import pytest" not in source
    assert "from pytest" not in source
