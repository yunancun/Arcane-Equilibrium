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

    resumed = compact_repository(tmp_path, roles=("A3",))

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
