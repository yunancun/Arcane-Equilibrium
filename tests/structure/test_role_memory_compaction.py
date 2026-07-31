from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
MANIFEST = ROOT / "docs/agents/role-memory-compaction-v1.json"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from role_memory_compaction import (  # noqa: E402
    ALLOWED_H2,
    ROLE_NAMES,
    compact_repository,
    discover_role_memories,
    main,
    promote_durable_lesson,
    recover_original_bytes,
    validate_hot_memory_bytes,
    verify_manifest,
)


def _seed_repository(root: Path) -> tuple[bytes, bytes]:
    role_dir = root / "docs/CCAgentWorkSpace/A3"
    role_dir.mkdir(parents=True)
    (root / "docs/agents").mkdir(parents=True)
    original = (
        b"# A3 Memory\n\n"
        b"## 2026-01-02 task ledger\n\n"
        b"- recurring heuristic: verify the rendered interaction.\n"
    )
    prefix = b"# Existing archive\n\nimmutable prefix\n"
    (role_dir / "memory.md").write_bytes(original)
    (role_dir / "memory-archive.md").write_bytes(prefix)
    return original, prefix


def _record_digest(value: dict[str, object], field: str) -> str:
    canonical = {key: item for key, item in value.items() if key != field}
    return "sha256:" + hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _manifest_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _pointer_digest(entry: dict[str, object]) -> str:
    pointer = {
        "schema_version": "role_memory_archive_pointer_v1",
        "role": entry["role"],
        "active_path": entry["active_path"],
        "archive_path": entry["archive_path"],
        "payload_sha256": entry["payload_sha256"],
        "payload_offset": entry["payload_offset"],
        "payload_bytes": entry["payload_bytes"],
    }
    return _sha256_bytes(
        json.dumps(
            pointer,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _rewrite_current_entry_path(
    root: Path,
    manifest: dict[str, object],
    *,
    field: str,
    value: str,
) -> None:
    entry = manifest["roles"][0]
    canonical_active = (
        root / f"docs/CCAgentWorkSpace/{entry['role']}/memory.md"
    )
    previous_value = entry[field]
    previous_pointer_digest = entry["archive_pointer_digest"]
    entry[field] = value
    entry["archive_pointer_digest"] = _pointer_digest(entry)
    active = canonical_active.read_text(encoding="utf-8")
    if field == "archive_path":
        active = active.replace(previous_value, value)
    active = active.replace(
        previous_pointer_digest,
        entry["archive_pointer_digest"],
    )
    active_bytes = active.encode("utf-8")
    canonical_active.write_bytes(active_bytes)
    entry["active_bytes"] = len(active_bytes)
    entry["active_lines"] = len(active.splitlines())
    entry["active_sha256"] = _sha256_bytes(active_bytes)
    manifest["manifest_digest"] = _record_digest(
        manifest,
        "manifest_digest",
    )


def _tamper_archived_prior_manifest(
    root: Path,
    manifest: dict[str, object],
    *,
    promotion_index: int,
    mutation: str,
) -> None:
    promotion = manifest["promotions"][promotion_index]
    entry = next(
        candidate
        for candidate in manifest["roles"]
        if candidate["role"] == promotion["role"]
    )
    archive_path = root / entry["archive_path"]
    archive = bytearray(archive_path.read_bytes())
    replacement_prior_active: bytes | None = None
    manifest_start = promotion["prior_manifest_offset"]
    prior_manifest_bytes_before = promotion["prior_manifest_bytes"]
    manifest_end = manifest_start + prior_manifest_bytes_before
    record_bytes_before = promotion["archive_record_bytes"]
    record_end_before = promotion["archive_record_offset"] + record_bytes_before
    prior_manifest = json.loads(bytes(archive[manifest_start:manifest_end]))
    if mutation == "prior_generation_bool":
        assert prior_manifest["generation"] == 1
        assert promotion["prior_generation"] == 1
        prior_manifest["generation"] = True
        promotion["prior_generation"] = True
    elif mutation == "policy":
        prior_manifest["policy"]["max_hot_bytes"] += 1
    elif mutation == "policy_float":
        prior_manifest["policy"]["max_hot_bytes"] = float(
            prior_manifest["policy"]["max_hot_bytes"]
        )
    elif mutation == "role_fields":
        original_lines = prior_manifest["roles"][0].pop("original_lines")
        prior_manifest["roles"][0]["attacker_field"] = original_lines
    elif mutation.startswith("derived:"):
        field = mutation.removeprefix("derived:")
        prior_manifest["roles"][0][field] += 1
    elif mutation.startswith("numeric_bool:"):
        field = mutation.removeprefix("numeric_bool:")
        assert prior_manifest["roles"][0][field] == 0
        prior_manifest["roles"][0][field] = False
    elif mutation == "path:active_path":
        prior_entry = prior_manifest["roles"][0]
        previous_pointer_digest = prior_entry["archive_pointer_digest"]
        prior_entry["active_path"] = (
            f"docs/CCAgentWorkSpace/{prior_entry['role']}/../"
            f"{prior_entry['role']}/memory.md"
        )
        prior_entry["archive_pointer_digest"] = _pointer_digest(prior_entry)
        prior_active_start = promotion["prior_active_offset"]
        prior_active_end = (
            prior_active_start + promotion["prior_active_bytes"]
        )
        replacement_prior_active = bytes(
            archive[prior_active_start:prior_active_end]
        ).replace(
            previous_pointer_digest.encode("utf-8"),
            prior_entry["archive_pointer_digest"].encode("utf-8"),
        )
        assert len(replacement_prior_active) == promotion[
            "prior_active_bytes"
        ]
        prior_entry["active_sha256"] = _sha256_bytes(
            replacement_prior_active
        )
        promotion["prior_active_sha256"] = prior_entry["active_sha256"]
    else:
        raise AssertionError(f"unsupported archived-manifest mutation: {mutation}")
    prior_manifest["manifest_digest"] = _record_digest(
        prior_manifest,
        "manifest_digest",
    )
    prior_manifest_bytes = _manifest_bytes(prior_manifest)

    promotion["prior_manifest_digest"] = prior_manifest["manifest_digest"]
    promotion["prior_manifest_bytes"] = len(prior_manifest_bytes)
    promotion["prior_manifest_sha256"] = _sha256_bytes(
        prior_manifest_bytes
    )
    marker_header = {
        "schema_version": "role_memory_promotion_archive_record_v2",
        "role": promotion["role"],
        "request_digest": promotion["request_digest"],
        "prior_manifest_digest": promotion["prior_manifest_digest"],
        "prior_generation": promotion["prior_generation"],
        "prior_active_sha256": promotion["prior_active_sha256"],
        "prior_active_bytes": promotion["prior_active_bytes"],
        "prior_manifest_sha256": promotion["prior_manifest_sha256"],
        "prior_manifest_bytes": promotion["prior_manifest_bytes"],
    }
    marker = (
        b"<!-- ROLE_MEMORY_PROMOTION_V2\n"
        + json.dumps(
            marker_header,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n-->\n"
    )
    record_start = promotion["archive_record_offset"]
    old_active_start = promotion["prior_active_offset"]
    old_active_end = old_active_start + promotion["prior_active_bytes"]
    separator = b"\n<!-- ROLE_MEMORY_PRIOR_MANIFEST_V2 -->\n"
    assert bytes(archive[old_active_end:manifest_start]) == separator
    prior_active = (
        replacement_prior_active
        if replacement_prior_active is not None
        else bytes(archive[old_active_start:old_active_end])
    )
    footer = bytes(archive[manifest_end:record_end_before])
    record = marker + prior_active + separator + prior_manifest_bytes + footer
    record_length_delta = len(record) - record_bytes_before
    if record_length_delta:
        assert promotion_index == len(manifest["promotions"]) - 1
        assert record_end_before == len(archive)
    archive[record_start:record_end_before] = record
    promotion["prior_active_offset"] = record_start + len(marker)
    promotion["prior_manifest_offset"] = (
        promotion["prior_active_offset"]
        + promotion["prior_active_bytes"]
        + len(separator)
    )
    promotion["archive_record_bytes"] = len(record)
    record_end = record_start + promotion["archive_record_bytes"]
    promotion["archive_record_sha256"] = _sha256_bytes(
        bytes(archive[record_start:record_end])
    )
    archive_path.write_bytes(archive)
    promotion["promotion_digest"] = _record_digest(
        promotion,
        "promotion_digest",
    )
    if promotion_index == len(manifest["promotions"]) - 1:
        manifest["supersedes_manifest_digest"] = promotion[
            "prior_manifest_digest"
        ]
    manifest["manifest_digest"] = _record_digest(
        manifest,
        "manifest_digest",
    )


def _promotion_authority(
    *,
    role: str,
    lesson: str,
    closure_digest: str,
) -> dict[str, object]:
    authority: dict[str, object] = {
        "schema_version": "role_memory_promotion_authority_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "authority": "PM_CLOSURE",
        "role": role,
        "durable_lesson_digest": "sha256:"
        + hashlib.sha256(lesson.encode("utf-8")).hexdigest(),
        "closure_digest": closure_digest,
        "producer": {"kind": "platform", "id": "test-host"},
        "attestation_id": "test-attestation",
    }
    authority["record_digest"] = _record_digest(authority, "record_digest")
    return authority


def _accept_test_authority(
    kind: str,
    digest: str,
    artifact: dict[str, object],
) -> bool:
    return (
        kind == "role_memory_promotion_authority_v1"
        and digest == artifact.get("record_digest")
        and artifact.get("producer") == {
            "kind": "platform",
            "id": "test-host",
        }
    )


def _host_promotion(
    root: Path,
    *,
    role: str,
    lesson: str,
    closure_digest: str,
) -> dict[str, object]:
    return promote_durable_lesson(
        root,
        role=role,
        lesson=lesson,
        closure_authority=_promotion_authority(
            role=role,
            lesson=lesson,
            closure_digest=closure_digest,
        ),
        authority_verifier=_accept_test_authority,
    )


def test_fixture_compaction_is_prefix_preserving_recoverable_and_idempotent(
    tmp_path: Path,
) -> None:
    original, prefix = _seed_repository(tmp_path)

    first = compact_repository(tmp_path, roles=("A3",))
    entry = first["roles"][0]
    archive = tmp_path / entry["archive_path"]
    active = tmp_path / entry["active_path"]

    assert archive.read_bytes().startswith(prefix)
    assert recover_original_bytes(tmp_path, entry) == original
    assert validate_hot_memory_bytes(active.read_bytes()) == []
    assert verify_manifest(tmp_path, first) == []

    archive_after_first = archive.read_bytes()
    active_after_first = active.read_bytes()
    manifest_after_first = (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).read_bytes()

    second = compact_repository(tmp_path, roles=("A3",))

    assert second == first
    assert archive.read_bytes() == archive_after_first
    assert active.read_bytes() == active_after_first
    assert (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).read_bytes() == manifest_after_first


def test_existing_manifest_drift_fails_closed(tmp_path: Path) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_digest"] = "sha256:" + "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest digest mismatch"):
        compact_repository(tmp_path, roles=("A3",))


def test_pm_promotion_publishes_a_verified_successor_generation(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    first = compact_repository(tmp_path, roles=("A3",))
    lesson = (
        "Bind every durable lesson promotion to its reviewed closure authority."
    )

    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson=lesson,
        closure_digest="sha256:" + "1" * 64,
    )

    assert promoted["generation"] == first["generation"] + 1
    assert promoted["supersedes_manifest_digest"] == first["manifest_digest"]
    assert promoted["promotions"][-1]["durable_lesson"] == lesson
    assert lesson.encode("utf-8") in (
        tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    ).read_bytes()
    assert verify_manifest(tmp_path, promoted) == []


def test_self_digested_authority_without_host_verifier_cannot_mutate(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    lesson = "Require host authentication before durable memory mutation."
    authority = _promotion_authority(
        role="A3",
        lesson=lesson,
        closure_digest="sha256:" + "7" * 64,
    )
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    with pytest.raises(ValueError, match="out-of-band host verifier"):
        promote_durable_lesson(
            tmp_path,
            role="A3",
            lesson=lesson,
            closure_authority=authority,
            authority_verifier=None,
        )

    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_upgrades_unpromoted_legacy_state_without_rewriting_memory_bytes(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    current = compact_repository(tmp_path, roles=("A3",))
    legacy = json.loads(json.dumps(current))
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["manifest_digest"] = _record_digest(legacy, "manifest_digest")
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    manifest_path.write_text(
        json.dumps(legacy, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    active_before = active_path.read_bytes()
    archive_before = archive_path.read_bytes()

    upgraded = compact_repository(tmp_path, roles=("A3",))

    assert upgraded["schema_version"] == "role_memory_compaction_manifest_v3"
    assert upgraded["generation"] == 1
    assert upgraded["supersedes_manifest_digest"] is None
    assert upgraded["promotions"] == []
    assert active_path.read_bytes() == active_before
    assert archive_path.read_bytes() == archive_before
    assert verify_manifest(tmp_path, upgraded) == []


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_rejects_self_digested_legacy_policy_drift(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    current = compact_repository(tmp_path, roles=("A3",))
    legacy = json.loads(json.dumps(current))
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["policy"]["max_hot_bytes"] += 1
    legacy["manifest_digest"] = _record_digest(legacy, "manifest_digest")
    (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).write_bytes(_manifest_bytes(legacy))

    with pytest.raises(
        ValueError,
        match="legacy manifest policy differs from the canonical contract",
    ):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_rejects_self_digested_legacy_float_policy_drift(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    current = compact_repository(tmp_path, roles=("A3",))
    legacy = json.loads(json.dumps(current))
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["policy"]["max_hot_bytes"] = float(
        legacy["policy"]["max_hot_bytes"]
    )
    legacy["manifest_digest"] = _record_digest(legacy, "manifest_digest")
    (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).write_bytes(_manifest_bytes(legacy))

    with pytest.raises(
        ValueError,
        match="legacy manifest policy differs from the canonical contract",
    ):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_rejects_self_digested_legacy_role_entry_shape_drift(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    current = compact_repository(tmp_path, roles=("A3",))
    legacy = json.loads(json.dumps(current))
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["roles"][0]["forged_field"] = "caller-controlled"
    legacy["manifest_digest"] = _record_digest(legacy, "manifest_digest")
    (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).write_bytes(_manifest_bytes(legacy))

    with pytest.raises(
        ValueError,
        match="legacy manifest role entry fields differ",
    ):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_rejects_self_digested_legacy_noncanonical_role_path(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    legacy = compact_repository(tmp_path, roles=("A3",))
    _rewrite_current_entry_path(
        tmp_path,
        legacy,
        field="active_path",
        value="docs/CCAgentWorkSpace/A3/../A3/memory.md",
    )
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["manifest_digest"] = _record_digest(legacy, "manifest_digest")
    (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).write_bytes(_manifest_bytes(legacy))

    with pytest.raises(
        ValueError,
        match="active_path differs from canonical role memory path",
    ):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize(
    "legacy_schema",
    (
        "role_memory_compaction_manifest_v1",
        "role_memory_compaction_manifest_v2",
    ),
)
def test_apply_rejects_legacy_bool_zero_numeric_field_before_write(
    tmp_path: Path,
    legacy_schema: str,
) -> None:
    _seed_repository(tmp_path)
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    archive_path.write_bytes(b"")
    legacy = compact_repository(tmp_path, roles=("A3",))
    legacy["schema_version"] = legacy_schema
    if legacy_schema.endswith("_v1"):
        legacy.pop("generation")
        legacy.pop("supersedes_manifest_digest")
        legacy.pop("promotions")
        for entry in legacy["roles"]:
            entry.pop("durable_lessons")
    legacy["roles"][0]["archive_prefix_bytes"] = False
    legacy["manifest_digest"] = _record_digest(
        legacy,
        "manifest_digest",
    )
    manifest_path.write_bytes(_manifest_bytes(legacy))
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    with pytest.raises(
        ValueError,
        match="A3: archive_prefix_bytes must be a nonnegative integer",
    ):
        compact_repository(tmp_path, roles=("A3",))

    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_standalone_promote_cli_returns_external_limit_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    lesson = "Use a successor generation for every reviewed durable lesson."
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    result = main(
        (
            "--repo-root",
            str(tmp_path),
            "--promote",
            "A3",
            "--lesson",
            lesson,
            "--closure-digest",
            "sha256:" + "2" * 64,
            "--authority",
            "PM_CLOSURE",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "EXTERNAL_LIMIT"
    assert payload["mutation_applied"] is False
    assert payload["role"] == "A3"
    assert payload["required_trust_tier"] == (
        "PLATFORM_OR_EXTERNAL_ATTESTED"
    )
    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_apply_rejects_interrupted_promotion_without_host_reauthentication(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Reauthenticate every interrupted promotion before recovery.",
        closure_digest="sha256:" + "c" * 64,
    )
    promotion = promoted["promotions"][-1]
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    archive = archive_path.read_bytes()
    start = promotion["prior_active_offset"]
    end = start + promotion["prior_active_bytes"]
    active_path.write_bytes(archive[start:end])
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    with pytest.raises(
        ValueError,
        match="promotion recovery requires an out-of-band host verifier",
    ):
        compact_repository(tmp_path, roles=("A3",))

    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_apply_rejects_recovery_when_host_rejects_exact_promotion_authority(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Reject a forged recovery authority even when a verifier exists.",
        closure_digest="sha256:" + "d" * 64,
    )
    promotion = promoted["promotions"][-1]
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    archive = archive_path.read_bytes()
    start = promotion["prior_active_offset"]
    end = start + promotion["prior_active_bytes"]
    active_path.write_bytes(archive[start:end])
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )
    observed: dict[str, object] = {}

    def reject_authority(
        kind: str,
        digest: str,
        artifact: dict[str, object],
    ) -> bool:
        observed.update(
            {
                "kind": kind,
                "digest": digest,
                "artifact": artifact,
            }
        )
        return False

    with pytest.raises(
        ValueError,
        match="recovery authority was not authenticated",
    ):
        compact_repository(
            tmp_path,
            roles=("A3",),
            authority_verifier=reject_authority,
        )

    assert observed == {
        "kind": "role_memory_promotion_authority_v1",
        "digest": promotion["closure_authority"]["record_digest"],
        "artifact": promotion["closure_authority"],
    }
    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_apply_preflights_forged_successor_before_any_recovery_write(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Authenticate the real promotion while rejecting forged lineage.",
        closure_digest="sha256:" + "e" * 64,
    )
    promotion = promoted["promotions"][-1]
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    legitimate_active = active_path.read_text(encoding="utf-8")
    rogue = "This forged successor has no promotion lineage."
    forged_active = legitimate_active.replace(
        "\n## Topical pointers",
        f"\n- {rogue}\n\n## Topical pointers",
    ).encode("utf-8")
    forged = json.loads(json.dumps(promoted))
    forged_entry = forged["roles"][0]
    forged_entry["durable_lessons"].append(rogue)
    forged_entry["active_bytes"] = len(forged_active)
    forged_entry["active_lines"] = len(
        forged_active.decode("utf-8").splitlines()
    )
    forged_entry["active_sha256"] = (
        "sha256:" + hashlib.sha256(forged_active).hexdigest()
    )
    forged["manifest_digest"] = _record_digest(
        forged,
        "manifest_digest",
    )
    manifest_path.write_text(
        json.dumps(forged, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    archive = archive_path.read_bytes()
    start = promotion["prior_active_offset"]
    end = start + promotion["prior_active_bytes"]
    active_path.write_bytes(archive[start:end])
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    with pytest.raises(ValueError, match="durable lesson lineage mismatch"):
        compact_repository(
            tmp_path,
            roles=("A3",),
            authority_verifier=_accept_test_authority,
        )

    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_apply_rejects_forged_successor_pointer_transition_before_write(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="A promotion may change only its authorized durable lesson.",
        closure_digest="sha256:" + "f" * 64,
    )
    promotion = promoted["promotions"][-1]
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    legitimate_active = active_path.read_text(encoding="utf-8")
    archive = archive_path.read_bytes()
    forged = json.loads(json.dumps(promoted))
    forged_entry = forged["roles"][0]
    prior_payload_sha256 = forged_entry["payload_sha256"]
    prior_payload_offset = forged_entry["payload_offset"]
    prior_payload_bytes = forged_entry["payload_bytes"]
    prior_pointer_digest = forged_entry["archive_pointer_digest"]
    forged_payload = archive[0:1]
    forged_entry["payload_sha256"] = (
        "sha256:" + hashlib.sha256(forged_payload).hexdigest()
    )
    forged_entry["payload_offset"] = 0
    forged_entry["payload_bytes"] = 1
    forged_pointer = {
        "schema_version": "role_memory_archive_pointer_v1",
        "role": forged_entry["role"],
        "active_path": forged_entry["active_path"],
        "archive_path": forged_entry["archive_path"],
        "payload_sha256": forged_entry["payload_sha256"],
        "payload_offset": forged_entry["payload_offset"],
        "payload_bytes": forged_entry["payload_bytes"],
    }
    forged_entry["archive_pointer_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                forged_pointer,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    forged_active = (
        legitimate_active.replace(
            f"- Payload digest: `{prior_payload_sha256}`",
            f"- Payload digest: `{forged_entry['payload_sha256']}`",
        )
        .replace(
            f"- Payload slice: offset `{prior_payload_offset}`, "
            f"bytes `{prior_payload_bytes}`",
            "- Payload slice: offset `0`, bytes `1`",
        )
        .replace(
            f"- Pointer digest: `{prior_pointer_digest}`",
            f"- Pointer digest: `{forged_entry['archive_pointer_digest']}`",
        )
        .encode("utf-8")
    )
    forged_entry["active_bytes"] = len(forged_active)
    forged_entry["active_lines"] = len(
        forged_active.decode("utf-8").splitlines()
    )
    forged_entry["active_sha256"] = (
        "sha256:" + hashlib.sha256(forged_active).hexdigest()
    )
    forged["manifest_digest"] = _record_digest(
        forged,
        "manifest_digest",
    )
    manifest_path.write_text(
        json.dumps(forged, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    start = promotion["prior_active_offset"]
    end = start + promotion["prior_active_bytes"]
    active_path.write_bytes(archive[start:end])
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )

    with pytest.raises(ValueError, match="successor transition differs"):
        compact_repository(
            tmp_path,
            roles=("A3",),
            authority_verifier=_accept_test_authority,
        )

    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


def test_apply_resumes_interrupted_promotion_from_bound_prior_active_slice(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Resume a partially published promotion without duplicate history.",
        closure_digest="sha256:" + "3" * 64,
    )
    promotion = promoted["promotions"][-1]
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    expected_active = active_path.read_bytes()
    archive = archive_path.read_bytes()
    start = promotion["prior_active_offset"]
    end = start + promotion["prior_active_bytes"]
    active_path.write_bytes(archive[start:end])
    archive_before_resume = archive_path.read_bytes()
    manifest_before_resume = (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).read_bytes()

    resumed = compact_repository(
        tmp_path,
        roles=("A3",),
        authority_verifier=_accept_test_authority,
    )

    assert resumed == promoted
    assert active_path.read_bytes() == expected_active
    assert archive_path.read_bytes() == archive_before_resume
    assert (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).read_bytes() == manifest_before_resume
    assert verify_manifest(tmp_path, resumed) == []


def test_replaying_a_promotion_is_byte_idempotent_and_recovery_stays_exact(
    tmp_path: Path,
) -> None:
    original, archive_prefix = _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    request = {
        "role": "A3",
        "lesson": "Replay an admitted promotion without duplicating archive bytes.",
        "closure_digest": "sha256:" + "4" * 64,
    }

    first = _host_promotion(tmp_path, **request)
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    first_bytes = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )
    second = _host_promotion(tmp_path, **request)

    assert second == first
    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == first_bytes
    assert archive_path.read_bytes().startswith(archive_prefix)
    assert recover_original_bytes(tmp_path, first["roles"][0]) == original
    assert len(first["promotions"]) == 1


def test_prior_manifest_tamper_cannot_survive_archive_lineage_verification(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    first = compact_repository(tmp_path, roles=("A3",))
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    prior_manifest_bytes = manifest_path.read_bytes()
    promoted = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Bind each successor to exact predecessor manifest bytes.",
        closure_digest="sha256:" + "8" * 64,
    )
    promotion = promoted["promotions"][-1]
    archive = (
        tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    ).read_bytes()
    start = promotion["prior_manifest_offset"]
    end = start + promotion["prior_manifest_bytes"]

    assert archive[start:end] == prior_manifest_bytes
    assert json.loads(archive[start:end])["manifest_digest"] == (
        first["manifest_digest"]
    )

    promotion["prior_manifest_digest"] = "sha256:" + "9" * 64
    promoted["supersedes_manifest_digest"] = promotion[
        "prior_manifest_digest"
    ]
    promotion["promotion_digest"] = _record_digest(
        promotion, "promotion_digest"
    )
    promoted["manifest_digest"] = _record_digest(
        promoted, "manifest_digest"
    )

    errors = verify_manifest(tmp_path, promoted)

    assert any(
        "promotion archive marker differs" in error
        or "prior manifest" in error
        for error in errors
    )


def test_successive_promotion_archives_the_exact_promotion_prefix(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    first = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve the first durable lesson in predecessor lineage.",
        closure_digest="sha256:" + "a" * 64,
    )
    second = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Verify every predecessor promotion prefix exactly.",
        closure_digest="sha256:" + "b" * 64,
    )
    promotion = second["promotions"][-1]
    archive = (
        tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    ).read_bytes()
    start = promotion["prior_manifest_offset"]
    end = start + promotion["prior_manifest_bytes"]
    predecessor = json.loads(archive[start:end])

    assert second["generation"] == 3
    assert predecessor["manifest_digest"] == first["manifest_digest"]
    assert predecessor["promotions"] == second["promotions"][:-1]
    assert verify_manifest(tmp_path, second) == []


def test_manual_hot_and_manifest_edit_cannot_impersonate_pm_promotion(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    manifest = compact_repository(tmp_path, roles=("A3",))
    rogue = "This lesson bypassed the PM closure promotion protocol."
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    active = active_path.read_text(encoding="utf-8").replace(
        "\n## Topical pointers",
        f"\n- {rogue}\n\n## Topical pointers",
    )
    active_path.write_text(active, encoding="utf-8")
    entry = manifest["roles"][0]
    entry["durable_lessons"].append(rogue)
    active_bytes = active.encode("utf-8")
    entry["active_bytes"] = len(active_bytes)
    entry["active_lines"] = len(active.splitlines())
    entry["active_sha256"] = "sha256:" + hashlib.sha256(active_bytes).hexdigest()
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )
    (tmp_path / "docs/agents/role-memory-compaction-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = verify_manifest(tmp_path, manifest)

    assert "A3: durable lesson lineage mismatch" in errors
    with pytest.raises(ValueError, match="durable lesson lineage mismatch"):
        _host_promotion(
            tmp_path,
            role="A3",
            lesson="A different otherwise valid durable lesson.",
            closure_digest="sha256:" + "5" * 64,
        )


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("unknown_role", "unknown role"),
        ("empty_lesson", "non-empty"),
        ("invalid_closure", "closure digest is invalid"),
        ("self_attested", "trust tier is invalid"),
        ("wrong_authority", "authority kind is invalid"),
    ),
)
def test_promotion_rejects_incomplete_or_self_attested_authority(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    role = "UNKNOWN" if case == "unknown_role" else "A3"
    lesson = (
        ""
        if case == "empty_lesson"
        else "Only a host-verified authority may promote this lesson."
    )
    authority = _promotion_authority(
        role=role,
        lesson=lesson,
        closure_digest=(
            "not-a-digest"
            if case == "invalid_closure"
            else "sha256:" + "6" * 64
        ),
    )
    if case == "self_attested":
        authority["trust_tier"] = "SELF_ATTESTED"
        authority["record_digest"] = _record_digest(
            authority, "record_digest"
        )
    if case == "wrong_authority":
        authority["authority"] = "SELF_ATTESTED"
        authority["record_digest"] = _record_digest(
            authority, "record_digest"
        )

    with pytest.raises(ValueError, match=message):
        promote_durable_lesson(
            tmp_path,
            role=role,
            lesson=lesson,
            closure_authority=authority,
            authority_verifier=_accept_test_authority,
        )


def test_checked_in_manifest_covers_every_role_and_recovers_every_payload() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    discovered = discover_role_memories(ROOT)

    assert tuple(path.parent.name for path in discovered) == ROLE_NAMES
    assert [entry["role"] for entry in manifest["roles"]] == list(ROLE_NAMES)
    assert verify_manifest(ROOT, manifest) == []

    for entry in manifest["roles"]:
        original = recover_original_bytes(ROOT, entry)
        assert len(original) == entry["payload_bytes"]
        assert original


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_manifest_verifier_requires_exact_unique_discovered_role_roster(
    mutation: str,
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if mutation == "missing":
        manifest["roles"] = [
            entry for entry in manifest["roles"] if entry["role"] != "TW"
        ]
    else:
        manifest["roles"].append(json.loads(json.dumps(manifest["roles"][0])))
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert "manifest role roster must exactly match governed active memories" in (
        verify_manifest(ROOT, manifest)
    )


def test_manifest_verifier_rejects_self_digested_policy_drift() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["policy"]["max_hot_bytes"] += 1
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert "manifest policy differs from the canonical contract" in (
        verify_manifest(ROOT, manifest)
    )


def test_manifest_verifier_rejects_self_digested_float_policy_drift() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["policy"]["max_hot_bytes"] = float(
        manifest["policy"]["max_hot_bytes"]
    )
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert "manifest policy differs from the canonical contract" in (
        verify_manifest(ROOT, manifest)
    )


def test_manifest_verifier_rejects_self_digested_extra_role_field() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["roles"][0]["forged_field"] = "caller-controlled"
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert "A3: role entry fields differ from the v3 contract" in (
        verify_manifest(ROOT, manifest)
    )


def test_manifest_verifier_rejects_self_digested_missing_role_field() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["roles"][0].pop("original_lines")
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert "A3: role entry fields differ from the v3 contract" in (
        verify_manifest(ROOT, manifest)
    )


@pytest.mark.parametrize(
    ("field", "error"),
    (
        ("active_bytes", "active_bytes differs from exact active byte length"),
        ("active_lines", "active_lines differs from exact active line count"),
        (
            "original_lines",
            "original_lines differs from recovered original line count",
        ),
    ),
)
def test_manifest_verifier_rejects_self_digested_derived_metadata_drift(
    field: str,
    error: str,
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["roles"][0][field] += 1
    manifest["manifest_digest"] = _record_digest(
        manifest, "manifest_digest"
    )

    assert f"A3: {error}" in verify_manifest(ROOT, manifest)


def test_verifier_and_resume_reject_bool_zero_numeric_field_before_write(
    tmp_path: Path,
) -> None:
    original, _ = _seed_repository(tmp_path)
    active_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory.md"
    archive_path = tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    manifest_path = tmp_path / "docs/agents/role-memory-compaction-v1.json"
    archive_path.write_bytes(b"")
    manifest = compact_repository(tmp_path, roles=("A3",))
    entry = manifest["roles"][0]
    assert entry["archive_prefix_bytes"] == 0
    entry["archive_prefix_bytes"] = False
    manifest["manifest_digest"] = _record_digest(
        manifest,
        "manifest_digest",
    )

    expected_error = (
        "A3: archive_prefix_bytes must be a nonnegative integer"
    )
    assert expected_error in verify_manifest(tmp_path, manifest)

    manifest_path.write_bytes(_manifest_bytes(manifest))
    active_path.write_bytes(original)
    before = (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    )
    with pytest.raises(ValueError, match=expected_error):
        compact_repository(tmp_path, roles=("A3",))
    assert (
        active_path.read_bytes(),
        archive_path.read_bytes(),
        manifest_path.read_bytes(),
    ) == before


@pytest.mark.parametrize("field", ("active_path", "archive_path"))
def test_manifest_verifier_rejects_self_digested_noncanonical_role_paths(
    tmp_path: Path,
    field: str,
) -> None:
    _seed_repository(tmp_path)
    manifest = compact_repository(tmp_path, roles=("A3",))
    filename = "memory.md" if field == "active_path" else "memory-archive.md"
    _rewrite_current_entry_path(
        tmp_path,
        manifest,
        field=field,
        value=f"docs/CCAgentWorkSpace/A3/../A3/{filename}",
    )

    assert (
        f"A3: {field} differs from canonical role memory path"
        in verify_manifest(tmp_path, manifest)
    )
    (
        tmp_path / "docs/agents/role-memory-compaction-v1.json"
    ).write_bytes(_manifest_bytes(manifest))
    with pytest.raises(
        ValueError,
        match=f"{field} differs from canonical role memory path",
    ):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize("field", ("active_path", "archive_path"))
def test_verifier_and_apply_reject_exact_role_path_symlinks(
    tmp_path: Path,
    field: str,
) -> None:
    _seed_repository(tmp_path)
    manifest = compact_repository(tmp_path, roles=("A3",))
    entry = manifest["roles"][0]
    path = tmp_path / entry[field]
    outside = tmp_path.parent / f"{tmp_path.name}-{field}-outside"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)

    assert (
        f"A3: {field} has a symlink component"
        in verify_manifest(tmp_path, manifest)
    )
    with pytest.raises(ValueError, match="has a symlink component"):
        compact_repository(tmp_path, roles=("A3",))


@pytest.mark.parametrize("promotion_index", (0, 1))
def test_each_archived_prior_manifest_rejects_self_digested_policy_drift(
    tmp_path: Path,
    promotion_index: int,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve the first predecessor manifest contract.",
        closure_digest="sha256:" + "d" * 64,
    )
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve every predecessor manifest contract.",
        closure_digest="sha256:" + "e" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=promotion_index,
        mutation="policy",
    )

    assert (
        f"A3: prior manifest generation {promotion_index + 1} policy "
        "differs from the canonical contract"
    ) in verify_manifest(tmp_path, manifest)


def test_archived_generation_one_rejects_self_digested_float_policy_drift(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve type-sensitive predecessor policy values.",
        closure_digest="sha256:" + "1" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=0,
        mutation="policy_float",
    )

    assert (
        "A3: prior manifest generation 1 policy differs from the "
        "canonical contract"
    ) in verify_manifest(tmp_path, manifest)


@pytest.mark.parametrize(
    ("field", "error"),
    (
        ("active_bytes", "active_bytes differs from exact active byte length"),
        ("active_lines", "active_lines differs from exact active line count"),
        (
            "original_lines",
            "original_lines differs from recovered original line count",
        ),
    ),
)
def test_archived_generation_one_rejects_derived_metadata_drift(
    tmp_path: Path,
    field: str,
    error: str,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve exact derived predecessor metadata.",
        closure_digest="sha256:" + "2" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=0,
        mutation=f"derived:{field}",
    )

    assert (
        f"A3: prior manifest generation 1 role A3 {error}"
        in verify_manifest(tmp_path, manifest)
    )


def test_archived_generation_rejects_bool_zero_numeric_field(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    (
        tmp_path / "docs/CCAgentWorkSpace/A3/memory-archive.md"
    ).write_bytes(b"")
    compact_repository(tmp_path, roles=("A3",))
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve exact numeric types in predecessor manifests.",
        closure_digest="sha256:" + "8" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=0,
        mutation="numeric_bool:archive_prefix_bytes",
    )

    assert (
        "A3: prior manifest generation 1 role A3 "
        "archive_prefix_bytes must be a nonnegative integer"
        in verify_manifest(tmp_path, manifest)
    )


def test_promotion_rejects_bool_prior_generation(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve exact integer types in promotion lineage.",
        closure_digest="sha256:" + "9" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=0,
        mutation="prior_generation_bool",
    )

    assert (
        "A3: prior_generation must be a positive integer"
        in verify_manifest(tmp_path, manifest)
    )


def test_archived_generation_one_rejects_noncanonical_role_path(
    tmp_path: Path,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve canonical predecessor role paths.",
        closure_digest="sha256:" + "3" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=0,
        mutation="path:active_path",
    )

    assert (
        "A3: prior manifest generation 1 role A3 active_path differs "
        "from canonical role memory path"
    ) in verify_manifest(tmp_path, manifest)


@pytest.mark.parametrize("promotion_index", (0, 1))
def test_each_archived_prior_manifest_requires_exact_role_entry_fields(
    tmp_path: Path,
    promotion_index: int,
) -> None:
    _seed_repository(tmp_path)
    compact_repository(tmp_path, roles=("A3",))
    _host_promotion(
        tmp_path,
        role="A3",
        lesson="Preserve exact predecessor role entry fields.",
        closure_digest="sha256:" + "f" * 64,
    )
    manifest = _host_promotion(
        tmp_path,
        role="A3",
        lesson="Reject added predecessor role entry fields.",
        closure_digest="sha256:" + "0" * 64,
    )
    _tamper_archived_prior_manifest(
        tmp_path,
        manifest,
        promotion_index=promotion_index,
        mutation="role_fields",
    )

    assert (
        f"A3: prior manifest generation {promotion_index + 1} role A3 "
        "fields differ from the v3 contract"
    ) in verify_manifest(tmp_path, manifest)


def test_every_checked_in_active_memory_obeys_the_hot_memory_policy() -> None:
    for path in discover_role_memories(ROOT):
        data = path.read_bytes()
        assert validate_hot_memory_bytes(data) == [], path
        headings = [
            line
            for line in data.decode("utf-8").splitlines()
            if line.startswith("## ")
        ]
        assert tuple(headings) == ALLOWED_H2
