from __future__ import annotations

import hashlib
import importlib.util
import ast
import os
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parents[1] / "helper_scripts/maintenance_scripts/p0b_psycopg_private_bundle_stage_v1.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("p0b_bundle_stage_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    package = source / "psycopg2"
    libraries = source / "psycopg2_binary.libs"
    package.mkdir(mode=0o700)
    libraries.mkdir(mode=0o700)
    package_files = {
        "__init__.py": b"version = 'fixture'\n",
        "_psycopg.fixture.so": b"ELF-fixture",
    }
    library_files = {"libpq-fixture.so": b"libpq-fixture"}
    for name, raw in package_files.items():
        path = package / name
        path.write_bytes(raw)
        path.chmod(0o600)
    for name, raw in library_files.items():
        path = libraries / name
        path.write_bytes(raw)
        path.chmod(0o700)
    manifest = {
        "psycopg2": {name: _sha(raw) for name, raw in package_files.items()},
        "psycopg2_binary.libs": {
            name: _sha(raw) for name, raw in library_files.items()
        },
    }
    destination_parent = tmp_path / "private"
    destination_parent.mkdir(mode=0o700)
    destination_parent.chmod(0o700)
    return source, destination_parent, manifest


def test_preflight_is_zero_effect_and_binds_exact_manifest(tmp_path: Path) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)
    (source / "unrelated-package").mkdir()
    (source / "psycopg2/__pycache__").mkdir()

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=False,
    )

    assert result["status"] == "PREFLIGHT_PASS"
    assert result["mutation_performed"] is False
    assert result["source_manifest_sha256"] == module.canonical_manifest_sha256(
        manifest
    )
    assert not (destination_parent / "sealed").exists()


def test_apply_stages_private_exact_tree_atomically(tmp_path: Path) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=True,
    )

    destination = destination_parent / "sealed"
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert result["mutation_performed"] is True
    assert result["destination_manifest_sha256"] == module.canonical_manifest_sha256(
        manifest
    )
    assert destination.stat().st_mode & 0o777 == 0o700
    assert (destination / "site-packages").stat().st_mode & 0o777 == 0o700
    assert (destination / "site-packages/psycopg2").stat().st_mode & 0o777 == 0o700
    assert (
        destination / "site-packages/psycopg2_binary.libs"
    ).stat().st_mode & 0o777 == 0o700
    assert (
        destination / "site-packages/psycopg2/__init__.py"
    ).stat().st_mode & 0o777 == 0o600
    assert (
        destination / "site-packages/psycopg2/_psycopg.fixture.so"
    ).stat().st_mode & 0o777 == 0o700


def test_tampered_source_fails_before_destination_creation(tmp_path: Path) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)
    (source / "psycopg2/__init__.py").write_bytes(b"tampered")

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=True,
    )

    assert result["status"] == "BLOCKED_NO_EFFECT"
    assert "source_hash_mismatch" in result["reason_codes"]
    assert not (destination_parent / "sealed").exists()


@pytest.mark.parametrize("unexpected_kind", ["file", "symlink"])
def test_unexpected_source_entry_fails_closed(
    tmp_path: Path,
    unexpected_kind: str,
) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)
    unexpected = source / "psycopg2/unexpected"
    if unexpected_kind == "file":
        unexpected.write_bytes(b"unexpected")
    else:
        unexpected.symlink_to(source / "psycopg2/__init__.py")

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=False,
    )

    assert result["status"] == "BLOCKED_NO_EFFECT"
    assert "source_entry_set_mismatch" in result["reason_codes"]


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)
    destination = destination_parent / "sealed"
    destination.mkdir(mode=0o700)
    marker = destination / "user-owned"
    marker.write_bytes(b"preserve")

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=True,
    )

    assert result["status"] == "BLOCKED_NO_EFFECT"
    assert "destination_already_exists" in result["reason_codes"]
    assert marker.read_bytes() == b"preserve"


def test_noreplace_publication_rejects_raced_destination(tmp_path: Path) -> None:
    module = _load_module()
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "staged").mkdir()
    destination = parent / "published"
    destination.mkdir()
    marker = destination / "preserve"
    marker.write_bytes(b"preserve")
    parent_fd = os.open(parent, os.O_RDONLY)
    try:
        with pytest.raises(module.StageError, match="destination_raced"):
            module._rename_noreplace(parent_fd, "staged", "published")
    finally:
        os.close(parent_fd)
    assert marker.read_bytes() == b"preserve"


def test_production_strict_mode_requires_linux_before_any_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    source, destination_parent, manifest = _fixture(tmp_path)
    monkeypatch.setattr(module.sys, "platform", "darwin")

    result = module.stage_bundle(
        source_root=source,
        destination_parent=destination_parent,
        destination_name="sealed",
        manifest=manifest,
        apply=True,
        strict_anchors=True,
    )

    assert result["status"] == "BLOCKED_NO_EFFECT"
    assert result["reason_codes"] == ["production_linux_required"]
    assert not (destination_parent / "sealed").exists()


def test_static_surface_has_no_runtime_or_database_commands() -> None:
    source = MODULE_PATH.read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "subprocess" not in imported
    assert "shutil" not in imported
    assert "systemctl" not in source
    assert "import psycopg2" not in source
    assert ".connect(" not in source
    assert "postgres" not in source.lower()
