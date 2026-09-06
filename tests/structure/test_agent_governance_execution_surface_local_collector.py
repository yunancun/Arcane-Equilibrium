"""
MODULE_NOTE
模塊用途：以公開 collector 與 canonical CLI 驗證 bounded local execution-surface 收集。
主要函數：直接呼叫 collect_local_execution_surface，並以真實暫存 TOML 驗證 replay。
依賴：pytest、agent_governance facade、Registry loader。
硬邊界：expected digest 來自獨立 literal bytes；只 mock 必要的 I/O race，不 mock 業務規則。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
sys.path.insert(0, str(HELPERS))

import agent_governance as governance_facade  # noqa: E402
import agent_governance_execution_surface_local_collector as collector  # noqa: E402
from agent_governance_registry import load_registry  # noqa: E402


def test_collector_reads_repository_config_and_replays_truth_report(
    tmp_path: Path,
) -> None:
    config_bytes = b"[agents]\nenabled = true\n"
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_bytes(config_bytes)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["schema_version"] == "execution_surface_local_collection_v1"
    assert collection["collection_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert collection["sources"] == [
        {
            "source_id": "global_config",
            "status": "not_requested",
            "file_bytes_sha256": None,
            "error_code": None,
        },
        {
            "source_id": "repository_config",
            "status": "collected",
            "file_bytes_sha256": (
                "sha256:0d4cde6e4a8e4d44392f8d7f5dc2c456e7637afe3e61296a355447b1487550d7"
            ),
            "error_code": None,
        },
    ]
    assert collection["request"]["sources"][0]["payload"] == {
        "values": [{"key": "agents.enabled", "value": True}]
    }
    report = collection["report"]
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert report["authenticity"] == {
        "host_verifier": "UNAVAILABLE",
        "profile_selection": "CALLER_CLAIMED",
        "sha256_scope": "INTEGRITY_ONLY",
    }
    assert governance_facade.validate_execution_surface_truth_report(
        report, load_registry()
    ) == []


def test_no_usable_declaration_is_explicitly_unavailable(tmp_path: Path) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text("[unrelated]\ncredential = 'must-not-escape'\n", encoding="utf-8")

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["collection_status"] == "UNAVAILABLE"
    assert collection["request"] is None
    assert collection["report"] is None
    assert collection["sources"][1]["status"] == "no_data"
    assert "must-not-escape" not in str(collection)


def test_canonical_cli_collect_local_emits_replayable_wrapper(capsys) -> None:
    exit_code = governance_facade.main(
        [
            "execution-surface-probe",
            "--collect-local",
            "--surface-profile-id",
            "codex_native_collaboration_v1",
        ]
    )

    collection = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert collection["schema_version"] == "execution_surface_local_collection_v1"
    assert collection["collection_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert collection["report"]["instruction_selection"]["status"] == "UNVERIFIED"
    assert {
        item["selected"]["status"]
        for item in collection["report"]["config_precedence"]["keys"]
    } == {"UNVERIFIED"}


def test_missing_and_empty_sources_remain_distinct(tmp_path: Path) -> None:
    empty_global = tmp_path / "explicit" / "config.toml"
    empty_global.parent.mkdir()
    empty_global.write_text(" \n", encoding="utf-8")

    collection = governance_facade.collect_local_execution_surface(
        "generic_host_v1",
        load_registry(),
        root=tmp_path,
        global_config=empty_global,
    )

    assert collection["collection_status"] == "UNAVAILABLE"
    assert [item["status"] for item in collection["sources"]] == [
        "empty",
        "missing",
    ]
    assert collection["request"] is None
    assert collection["report"] is None


def test_explicit_global_and_repository_sources_keep_probe_precedence(
    tmp_path: Path,
) -> None:
    repository = tmp_path / ".codex" / "config.toml"
    repository.parent.mkdir()
    repository.write_text("[agents]\nenabled = true\n", encoding="utf-8")
    global_config = tmp_path / "global" / "config.toml"
    global_config.parent.mkdir()
    global_config.write_text("[agents]\nenabled = false\n", encoding="utf-8")

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
        global_config=global_config,
    )

    key_report = collection["report"]["config_precedence"]["keys"][0]
    assert key_report["declared_candidates"] == [
        {"source_id": "global_config", "precedence_rank": 10, "value": False},
        {"source_id": "repository_config", "precedence_rank": 20, "value": True},
    ]
    assert key_report["selected"]["status"] == "UNVERIFIED"
    assert collection["sources"][0]["file_bytes_sha256"] == (
        "sha256:0ccae8bc474c3465958233b7e50705031f9e6dd4d2e069b990584c9f3dc367a8"
    )
    assert (
        collection["sources"][0]["file_bytes_sha256"]
        != collection["request"]["sources"][0]["source_sha256"]
    )


@pytest.mark.parametrize(
    ("config_bytes", "error_code"),
    [
        (b"[broken\ncredential-sentinel", "LOCAL_CONFIG_TOML"),
        (b"[agents]\nenabled=true\nenabled=false\n", "LOCAL_CONFIG_TOML"),
        (b"\xffcredential-sentinel", "LOCAL_CONFIG_ENCODING"),
        (
            ("[" + ".".join(["nested"] * 34) + "]\nvalue=1\n").encode(),
            "LOCAL_CONFIG_TOO_DEEP",
        ),
        (
            b"[agents]\nenabled='credential-sentinel'\n",
            "LOCAL_CONFIG_SOURCE_POLICY",
        ),
    ],
)
def test_invalid_source_is_wholly_rejected_without_secret_or_parser_echo(
    tmp_path: Path,
    config_bytes: bytes,
    error_code: str,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_bytes(config_bytes)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    repository_status = collection["sources"][1]
    assert repository_status["status"] == "rejected"
    assert repository_status["error_code"] == error_code
    assert collection["collection_status"] == "UNAVAILABLE"
    serialized = json.dumps(collection, sort_keys=True)
    assert "credential-sentinel" not in serialized
    assert "enabled" not in serialized


def test_symlink_oversize_and_nonregular_inputs_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.toml"
    target.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    linked_file = tmp_path / "linked-file" / "config.toml"
    linked_file.parent.mkdir()
    linked_file.symlink_to(target)
    target_directory = tmp_path / "target-directory"
    target_directory.mkdir()
    (target_directory / "config.toml").write_text(
        "[agents]\nenabled=true\n", encoding="utf-8"
    )
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(target_directory, target_is_directory=True)
    oversized = tmp_path / "oversized" / "config.toml"
    oversized.parent.mkdir()
    oversized.write_bytes(b" " * (collector.LOCAL_CONFIG_MAX_BYTES + 1))
    nonregular = tmp_path / "nonregular" / "config.toml"
    nonregular.mkdir(parents=True)
    fifo = tmp_path / "fifo" / "config.toml"
    fifo.parent.mkdir()
    os.mkfifo(fifo)

    cases = [
        (linked_file, "LOCAL_CONFIG_SYMLINK"),
        (linked_parent / "config.toml", "LOCAL_CONFIG_SYMLINK"),
        (oversized, "LOCAL_CONFIG_TOO_LARGE"),
        (nonregular, "LOCAL_CONFIG_NOT_REGULAR"),
        (fifo, "LOCAL_CONFIG_NOT_REGULAR"),
    ]
    for explicit_path, error_code in cases:
        collection = governance_facade.collect_local_execution_surface(
            "generic_host_v1",
            load_registry(),
            root=tmp_path,
            global_config=explicit_path,
        )
        assert collection["sources"][0]["status"] == "rejected"
        assert collection["sources"][0]["error_code"] == error_code
        assert collection["collection_status"] == "UNAVAILABLE"


def test_profile_is_rejected_before_any_config_path_is_read() -> None:
    with pytest.raises(
        collector.ExecutionSurfaceLocalCollectionError,
        match="Registry declared",
    ) as caught:
        governance_facade.collect_local_execution_surface(
            "not-registered",
            load_registry(),
            root=Path("/definitely/missing/and/unreadable"),
        )

    assert caught.value.error_code == "LOCAL_PROFILE_INVALID"


def test_ambient_home_config_is_not_read(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / ".codex" / "config.toml"
    repository.parent.mkdir()
    repository.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    ambient = tmp_path / "ambient-home" / ".codex" / "config.toml"
    ambient.parent.mkdir(parents=True)
    ambient.write_text("[agents]\nenabled=false\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(ambient.parents[1]))
    monkeypatch.setenv("CODEX_HOME", str(ambient.parent))

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert [source["source_id"] for source in collection["request"]["sources"]] == [
        "repository_config"
    ]
    assert collection["request"]["sources"][0]["payload"] == {
        "values": [{"key": "agents.enabled", "value": True}]
    }


def test_changed_snapshot_is_rejected_via_real_file_io(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    real_read = collector.os.read
    changed = False

    def read_then_change(descriptor: int, amount: int) -> bytes:
        nonlocal changed
        chunk = real_read(descriptor, amount)
        if chunk and not changed:
            changed = True
            config.write_text(
                "[agents]\nenabled=false\ninterrupt_message=true\n",
                encoding="utf-8",
            )
        return chunk

    monkeypatch.setattr(collector.os, "read", read_then_change)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["sources"][1]["status"] == "rejected"
    assert collection["sources"][1]["error_code"] == "LOCAL_CONFIG_CHANGED"
    assert collection["request"] is None


def test_replaced_snapshot_is_rejected_via_anchored_final_lookup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    replacement = tmp_path / "replacement.toml"
    replacement.write_text("[agents]\nenabled=false\n", encoding="utf-8")
    real_read = collector.os.read
    changed = False

    def read_then_replace(descriptor: int, amount: int) -> bytes:
        nonlocal changed
        chunk = real_read(descriptor, amount)
        if chunk and not changed:
            changed = True
            os.replace(replacement, config)
        return chunk

    monkeypatch.setattr(collector.os, "read", read_then_replace)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["sources"][1]["status"] == "rejected"
    assert collection["sources"][1]["error_code"] == "LOCAL_CONFIG_CHANGED"


@pytest.mark.parametrize(
    "config_bytes",
    [
        b"[agents]\nmax_concurrent_threads_per_session=nan\n",
        b"[agents]\nmax_concurrent_threads_per_session=inf\n",
        b"[agents]\nmax_concurrent_threads_per_session=2026-09-06\n",
    ],
)
def test_non_json_allowed_key_values_are_secret_safely_rejected(
    tmp_path: Path,
    config_bytes: bytes,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_bytes(config_bytes)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["sources"][1]["status"] == "rejected"
    assert collection["sources"][1]["error_code"] == "LOCAL_CONFIG_SOURCE_POLICY"
    assert collection["request"] is None
    assert collection["report"] is None
    assert "2026-09-06" not in json.dumps(collection, sort_keys=True)


def test_explicit_global_path_requires_config_toml_basename(tmp_path: Path) -> None:
    unexpected = tmp_path / "credential-sentinel.toml"
    unexpected.write_text("[agents]\nenabled=true\n", encoding="utf-8")

    with pytest.raises(
        collector.ExecutionSurfaceLocalCollectionError,
        match="global config argument is invalid",
    ) as caught:
        governance_facade.collect_local_execution_surface(
            "generic_host_v1",
            load_registry(),
            root=tmp_path,
            global_config=unexpected,
        )

    assert caught.value.error_code == "LOCAL_GLOBAL_CONFIG_ARGUMENT"
    assert "credential-sentinel" not in str(caught.value)


def test_cli_global_basename_error_is_fixed_and_secret_safe(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = governance_facade.main(
        [
            "execution-surface-probe",
            "--collect-local",
            "--surface-profile-id",
            "generic_host_v1",
            "--global-config",
            str(tmp_path / "credential-sentinel.toml"),
        ]
    )

    error = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert error == {
        "schema_version": "execution_surface_local_collection_error_v1",
        "status": "FAIL",
        "error_code": "LOCAL_GLOBAL_CONFIG_ARGUMENT",
        "error": "global config argument is invalid",
    }
    assert "credential-sentinel" not in json.dumps(error, sort_keys=True)


def test_stat_to_fifo_race_is_nonblocking_and_rejected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    real_open = collector.os.open
    replaced = False

    def replace_with_fifo_before_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if (
            path == "config.toml"
            and kwargs.get("dir_fd") is not None
            and not flags & getattr(os, "O_DIRECTORY", 0)
            and not replaced
        ):
            replaced = True
            assert flags & getattr(os, "O_NONBLOCK", 0)
            config.unlink()
            os.mkfifo(config)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(collector.os, "open", replace_with_fifo_before_open)

    collection = governance_facade.collect_local_execution_surface(
        "generic_host_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["sources"][1]["status"] == "rejected"
    assert collection["sources"][1]["error_code"] == "LOCAL_CONFIG_CHANGED"


def test_parent_directory_replacement_is_rejected_by_final_rewalk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_directory = tmp_path / ".codex"
    config_directory.mkdir()
    config = config_directory / "config.toml"
    config.write_text("[agents]\nenabled=true\n", encoding="utf-8")
    old_directory = tmp_path / "old-codex"
    real_read = collector.os.read
    replaced = False

    def read_then_replace_parent(descriptor: int, amount: int) -> bytes:
        nonlocal replaced
        chunk = real_read(descriptor, amount)
        if chunk and not replaced:
            replaced = True
            config_directory.rename(old_directory)
            config_directory.mkdir()
            config.write_text("[agents]\nenabled=false\n", encoding="utf-8")
        return chunk

    monkeypatch.setattr(collector.os, "read", read_then_replace_parent)

    collection = governance_facade.collect_local_execution_surface(
        "codex_native_collaboration_v1",
        load_registry(),
        root=tmp_path,
    )

    assert collection["sources"][1]["status"] == "rejected"
    assert collection["sources"][1]["error_code"] == "LOCAL_CONFIG_CHANGED"
