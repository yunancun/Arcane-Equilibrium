from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "deploy_intent_adapter.py"
)
PROBE_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "runtime_environment_probe.py"
)
RESTART_ALL_PATH = ROOT / "helper_scripts" / "restart_all.sh"
MAIN_PIPELINES_PATH = ROOT / "rust" / "openclaw_engine" / "src" / "main_pipelines.rs"
SYSTEMD_ENGINE_PATH = ROOT / "helper_scripts" / "systemd" / "openclaw-engine.service"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("deploy_intent_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_probe():
    spec = importlib.util.spec_from_file_location("runtime_environment_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_probe_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, dict[str, Path | str | int]]:
    probe = _load_probe()
    repo = tmp_path / "srv"
    binary = repo / "rust/target/release/openclaw-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"exact-engine-image")
    binary.chmod(0o700)
    proc_root = tmp_path / "proc"
    pid = 4242
    process = proc_root / str(pid)
    process.mkdir(parents=True)
    (process / "exe").symlink_to(binary)
    (process / "cwd").symlink_to(repo)
    (process / "stat").write_text(
        f"{pid} (openclaw-engine) " + " ".join(["S", *(["0"] * 18), "12345"]),
        encoding="ascii",
    )
    live_task = process / "task" / "4243"
    live_task.mkdir(parents=True)
    live_task_comm = live_task / "comm"
    live_task_comm.write_bytes(b"oc-live-rt\n")
    live_task_stat = live_task / "stat"
    live_task_stat.write_text(
        "4243 (oc-live-rt) " + " ".join(["S", *(["0"] * 18), "23456"]),
        encoding="ascii",
    )
    secrets = tmp_path / "secret-sentinel-path"
    endpoint = secrets / "live/bybit_endpoint"
    endpoint.parent.mkdir(parents=True)
    endpoint.write_bytes(b"demo\n")
    endpoint.chmod(0o600)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    allowlisted_entries = [
        b"OPENCLAW_ALLOW_MAINNET=0",
        b"OPENCLAW_ENABLE_PAPER=0",
        b"OPENCLAW_DEMO_LEARNING_LANE_WRITER=1",
        b"OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0",
        b"OPENCLAW_CANARY_MODE=0",
        f"OPENCLAW_DATA_DIR={data_dir}".encode(),
        f"OPENCLAW_SECRETS_DIR={secrets}".encode(),
    ]
    projection_path = tmp_path / "allowlisted-environment-projection"
    projection_path.write_bytes(b"\0".join(allowlisted_entries) + b"\0")
    environ = b"\0".join(
        [
            *allowlisted_entries,
            b"OPENAI_API_KEY=credential-sentinel-must-not-leak",
            b"DATABASE_URL=database-sentinel-must-not-leak",
        ]
    ) + b"\0"
    environ_path = process / "environ"
    environ_path.write_bytes(environ)
    environ_path.chmod(0o000)
    monkeypatch.setattr(probe, "REPO_ROOT", repo)
    monkeypatch.setattr(probe, "PROC_ROOT", proc_root)
    monkeypatch.setattr(probe, "_hostname", lambda: "trade-core-runtime")
    monkeypatch.setattr(probe, "_engine_pids", lambda: [pid])
    monkeypatch.setattr(
        probe,
        "_environment_projection",
        lambda _pid: (projection_path.read_bytes(), []),
    )
    monkeypatch.setattr(
        probe,
        "_git_text",
        lambda *args: "a" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    return probe, {
        "repo": repo,
        "binary": binary,
        "proc_root": proc_root,
        "pid": pid,
        "live_task": live_task,
        "live_task_comm": live_task_comm,
        "live_task_stat": live_task_stat,
        "secrets": secrets,
        "endpoint": endpoint,
        "environ": environ_path,
        "projection": projection_path,
    }


def test_local_probe_proves_only_exact_private_live_demo_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )
    assert blockers == []
    assert attestation is not None
    assert attestation["actual_endpoint_class"] == "bybit_demo"
    assert attestation["allow_mainnet"] is False
    assert probe.LIVE_SLOT_THREAD_NAME == "oc-live-rt"
    assert (
        f'.name("{probe.LIVE_SLOT_THREAD_NAME}".into())'
        in MAIN_PIPELINES_PATH.read_text(encoding="utf-8")
    )
    assert MAIN_PIPELINES_PATH.read_text(encoding="utf-8").count(
        f'.name("{probe.LIVE_SLOT_THREAD_NAME}".into())'
    ) == 1
    assert probe.LIVE_SLOT_THREAD_NAME not in RESTART_ALL_PATH.read_text(
        encoding="utf-8"
    )
    assert probe.LIVE_SLOT_THREAD_NAME not in SYSTEMD_ENGINE_PATH.read_text(
        encoding="utf-8"
    )
    assert probe.ATTESTED_TARGET_ENVIRONMENT == "live_demo"
    assert probe.ATTESTED_AUTHORIZATION_SCOPE == "live_demo_only"
    assert attestation["runtime_mode"] == probe.ATTESTED_TARGET_ENVIRONMENT
    assert (
        attestation["authorization_scope"]
        == probe.ATTESTED_AUTHORIZATION_SCOPE
    )
    serialized = json.dumps(attestation, sort_keys=True)
    for forbidden in (
        "credential-sentinel-must-not-leak",
        "database-sentinel-must-not-leak",
        str(fixture["secrets"]),
        "OPENAI_API_KEY",
        "DATABASE_URL",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "LIVE_SLOT_NOT_FOUND"),
        ("lookalike", "LIVE_SLOT_NOT_FOUND"),
        ("ambiguous", "LIVE_SLOT_AMBIGUOUS"),
        ("unreadable", "LIVE_SLOT_STATE_UNREADABLE"),
    ],
)
def test_local_probe_does_not_launder_demo_endpoint_into_live_demo_without_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    live_task = fixture["live_task"]
    assert isinstance(live_task, Path)
    if mutation == "missing":
        (live_task / "comm").unlink()
        (live_task / "stat").unlink()
        live_task.rmdir()
    elif mutation == "lookalike":
        (live_task / "comm").write_bytes(b"oc-live-rt-old\n")
    elif mutation == "ambiguous":
        duplicate = live_task.parent / "4244"
        duplicate.mkdir()
        (duplicate / "comm").write_bytes(b"oc-live-rt\n")
        (duplicate / "stat").write_text(
            "4244 (oc-live-rt) " + " ".join(["S", *(["0"] * 18), "34567"]),
            encoding="ascii",
        )
    else:
        (live_task / "stat").write_text("malformed", encoding="ascii")

    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )

    assert attestation is None
    assert expected_code in blockers


@pytest.mark.parametrize(
    ("final_identity",),
    [
        (((4244, "23456"),),),
        (((4243, "34567"),),),
    ],
)
def test_local_probe_denies_live_slot_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_identity: tuple[tuple[int, str], ...],
) -> None:
    probe, _fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    observations = iter(((((4243, "23456"),), []), (final_identity, [])))
    monkeypatch.setattr(
        probe, "_live_slot_task_identities", lambda _pid: next(observations)
    )

    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )

    assert attestation is None
    assert "LIVE_SLOT_IDENTITY_DRIFT" in blockers


def test_local_probe_keeps_environment_identity_stable_across_slot_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    first, first_blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )
    assert first_blockers == []
    assert first is not None

    live_task_stat = fixture["live_task_stat"]
    assert isinstance(live_task_stat, Path)
    live_task_stat.write_text(
        "4243 (oc-live-rt) " + " ".join(["S", *(["0"] * 18), "34567"]),
        encoding="ascii",
    )
    second, second_blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )
    assert second_blockers == []
    assert second is not None

    assert second["process_identity_digest"] == first["process_identity_digest"]
    assert second["config_identity_digest"] == first["config_identity_digest"]
    assert second["environment_identity_digest"] == first["environment_identity_digest"]
    assert second["attestation_digest"] == first["attestation_digest"]


def test_environment_projector_uses_one_exact_allowlist_and_returns_no_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    calls: list[tuple[list[str], dict]] = []

    def projected(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=b"OPENCLAW_ALLOW_MAINNET=0\0",
            stderr=b"credential-sentinel-must-not-leak",
        )

    monkeypatch.setattr(probe.subprocess, "run", projected)
    raw, blockers = probe._environment_projection(4242)
    assert blockers == []
    assert raw == b"OPENCLAW_ALLOW_MAINNET=0\0"
    argv, kwargs = calls[0]
    assert argv[:3] == [probe.ENVIRONMENT_PROJECTOR, "-z", "-E"]
    assert "OPENAI" not in argv[3] and "DATABASE" not in argv[3]
    assert kwargs["env"] == {"LC_ALL": "C"}
    assert kwargs["capture_output"] is True


def test_probe_tool_invocations_use_absolute_allowlisted_binaries_and_sanitized_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    monkeypatch.setenv("PATH", str(tmp_path / "attacker-controlled-bin"))
    calls: list[tuple[list[str], dict]] = []

    def completed(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if argv[0] == probe.GIT_EXECUTABLE:
            return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n", stderr="")
        if argv[0] == probe.PGREP_EXECUTABLE:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        raise AssertionError(f"unexpected executable: {argv[0]}")

    monkeypatch.setattr(probe.subprocess, "run", completed)
    assert probe._git_text("rev-parse", "HEAD") == "a" * 40
    assert probe._engine_pids() == []

    assert probe.GIT_EXECUTABLE == "/usr/bin/git"
    assert probe.PGREP_EXECUTABLE == "/usr/bin/pgrep"
    assert {call[0][0] for call in calls} == {
        probe.GIT_EXECUTABLE,
        probe.PGREP_EXECUTABLE,
    }
    assert all(Path(call[0][0]).is_absolute() for call in calls)
    assert all(call[1]["env"] == {"LC_ALL": "C"} for call in calls)
    assert all("PATH" not in call[1]["env"] for call in calls)


def test_environment_projection_pattern_is_exact_and_real_nul_input_never_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    expected_pattern = (
        "^("
        + "|".join(sorted(probe.ALLOWED_ENVIRONMENT_KEYS))
        + ")="
    )
    assert probe.ENVIRONMENT_PROJECTION_PATTERN == expected_pattern
    assert ".*" not in probe.ENVIRONMENT_PROJECTION_PATTERN
    assert {
        part for part in probe.ENVIRONMENT_PROJECTION_PATTERN[2:-2].split("|")
    } == set(probe.ALLOWED_ENVIRONMENT_KEYS)

    proc_root = tmp_path / "proc"
    process = proc_root / "4242"
    process.mkdir(parents=True)
    (process / "environ").write_bytes(
        b"OPENAI_API_KEY=credential-sentinel-must-not-reach-python\0"
        b"OPENCLAW_ALLOW_MAINNET=0\0"
        b"DATABASE_URL=database-sentinel-must-not-reach-python\0"
        b"OPENCLAW_CANARY_MODE=0\0"
    )
    monkeypatch.setattr(probe, "PROC_ROOT", proc_root)

    raw, blockers = probe._environment_projection(4242)

    assert blockers == []
    assert raw == b"OPENCLAW_ALLOW_MAINNET=0\0OPENCLAW_CANARY_MODE=0\0"
    assert b"sentinel-must-not-reach-python" not in raw
    assert b"OPENAI_API_KEY" not in raw
    assert b"DATABASE_URL" not in raw


@pytest.mark.parametrize(
    ("final_head", "final_status", "expected_code"),
    [
        ("b" * 40, "", "SOURCE_HEAD_DRIFT"),
        ("a" * 40, " M runtime-state", "SOURCE_TREE_DRIFT"),
    ],
)
def test_local_probe_rereads_repository_identity_and_denies_mid_probe_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_head: str,
    final_status: str,
    expected_code: str,
) -> None:
    probe, _fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    observations = iter(("a" * 40, "", final_head, final_status))
    monkeypatch.setattr(probe, "_git_text", lambda *_args: next(observations))

    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )

    assert attestation is None
    assert expected_code in blockers


@pytest.mark.parametrize(
    ("endpoint_bytes", "allow_mainnet", "expected_code"),
    [
        (b"mainnet\n", b"0", "MAINNET_ENDPOINT_FORBIDDEN"),
        (b"Demo\n", b"0", "ENDPOINT_METADATA_UNSAFE"),
        (b"demo\n", b"1", "ALLOW_MAINNET_ENABLED"),
        (b"demo\n", b"yes", "RUNTIME_BOOLEAN_INVALID"),
    ],
)
def test_local_probe_denies_endpoint_and_authority_mutations_without_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    endpoint_bytes: bytes,
    allow_mainnet: bytes,
    expected_code: str,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    endpoint = fixture["endpoint"]
    assert isinstance(endpoint, Path)
    endpoint.write_bytes(endpoint_bytes)
    projection = fixture["projection"]
    assert isinstance(projection, Path)
    projection.write_bytes(
        projection.read_bytes().replace(
            b"OPENCLAW_ALLOW_MAINNET=0",
            b"OPENCLAW_ALLOW_MAINNET=" + allow_mainnet,
        )
    )
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )
    assert attestation is None
    assert any(expected_code in blocker for blocker in blockers)
    serialized = json.dumps(blockers)
    assert "credential-sentinel-must-not-leak" not in serialized
    assert str(fixture["secrets"]) not in serialized


def test_local_probe_denies_process_repo_and_endpoint_file_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)

    monkeypatch.setattr(probe, "_engine_pids", lambda: [])
    assert probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )[0] is None
    monkeypatch.setattr(probe, "_engine_pids", lambda: [4242, 4243])
    assert "PROCESS_AMBIGUOUS" in probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )[1]

    monkeypatch.setattr(probe, "_engine_pids", lambda: [4242])
    endpoint = fixture["endpoint"]
    assert isinstance(endpoint, Path)
    endpoint.chmod(0o644)
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight", expected_host="wrong-host",
        expected_source_head="b" * 40, now="2026-07-15T10:00:00+00:00",
    )
    assert attestation is None
    assert {"HOST_MISMATCH", "SOURCE_HEAD_MISMATCH", "ENDPOINT_METADATA_UNSAFE"}.issubset(
        set(blockers)
    )

    endpoint.unlink()
    outside = tmp_path / "outside-endpoint"
    outside.write_bytes(b"demo\n")
    outside.chmod(0o600)
    endpoint.symlink_to(outside)
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )
    assert attestation is None
    assert "ENDPOINT_METADATA_UNSAFE" in blockers


def test_local_probe_denies_pid_start_identity_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, _fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    observed = iter(("12345", "54321"))
    monkeypatch.setattr(probe, "_process_start_ticks", lambda _pid: next(observed))
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )
    assert attestation is None
    assert "PROCESS_IDENTITY_RACE" in blockers


def test_local_probe_rereads_endpoint_and_denies_mid_probe_mainnet_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    endpoint = fixture["endpoint"]
    assert isinstance(endpoint, Path)
    original = probe._endpoint_identity
    calls = 0

    def flip_after_first_read(secrets_root: Path):
        nonlocal calls
        result = original(secrets_root)
        calls += 1
        if calls == 1:
            endpoint.write_bytes(b"mainnet\n")
        return result

    monkeypatch.setattr(probe, "_endpoint_identity", flip_after_first_read)
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight", expected_host="trade-core-runtime",
        expected_source_head="a" * 40, now="2026-07-15T10:00:00+00:00",
    )
    assert attestation is None
    assert "MAINNET_ENDPOINT_FORBIDDEN" in blockers


def _intent(
    environment_identity: str, *, target_environment: str = "demo",
) -> dict:
    head = "a" * 40
    return {
        "schema_version": "deployment_intent_v1",
        "intent_id": "deploy-env-0001",
        "target_host": "trade-core-runtime",
        "target_environment": target_environment,
        "expected_source_head": head,
        "expected_deploy_script_sha256": "sha256:" + "b" * 64,
        "expected_runtime_environment_identity_digest": environment_identity,
        "require_clean_tree": True,
        "approved_by": "operator",
        "approved_at": "2026-07-11T10:00:00Z",
        "expires_at": "2026-07-11T12:00:00Z",
        "typed_confirm": f"deploy:trade-core-runtime:{head}:deploy-env-0001",
        "hard_stops": [
            "no live/mainnet authority expansion",
            "no risk/cost-gate/decision-lease bypass",
        ],
    }


def test_deploy_adapter_accepts_only_the_environment_its_real_probe_attests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe, _fixture = _safe_probe_fixture(tmp_path, monkeypatch)
    attestation, blockers = probe.probe_runtime_environment(
        phase="preflight",
        expected_host="trade-core-runtime",
        expected_source_head="a" * 40,
        now="2026-07-15T10:00:00+00:00",
    )
    assert blockers == []
    assert attestation is not None

    adapter = _load_adapter()
    live_demo_intent = _intent(
        attestation["environment_identity_digest"],
        target_environment="live_demo",
    )
    assert adapter.reconcile_runtime_attestations(
        attestation,
        attestation,
        live_demo_intent,
        phase="preflight",
        now="2026-07-15T10:01:00+00:00",
    ) == []
    common_validation = {
        "supplied_intent_digest": "sha256:" + "e" * 64,
        "actual_intent_digest": "sha256:" + "e" * 64,
        "actual_source_head": "a" * 40,
        "tree_clean": True,
        "actual_host": "trade-core-runtime",
        "deploy_script_digest": "sha256:" + "b" * 64,
        "now": "2026-07-11T10:15:00Z",
    }
    assert adapter.validate_intent(live_demo_intent, **common_validation) == []
    assert adapter.local_probe_target_environment_errors(live_demo_intent) == []

    for unsupported in ("demo", "research_runtime"):
        unsupported_intent = _intent(
            attestation["environment_identity_digest"],
            target_environment=unsupported,
        )
        assert adapter.validate_intent(
            unsupported_intent, **common_validation
        ) == []
        assert adapter.local_probe_target_environment_errors(
            unsupported_intent
        ) == [
            "target_environment is unsupported by the local runtime probe; "
            "expected live_demo"
        ]
        assert adapter.reconcile_runtime_attestations(
            attestation,
            attestation,
            unsupported_intent,
            phase="preflight",
            now="2026-07-15T10:01:00+00:00",
        )


def test_restart_launcher_exposes_the_probe_required_explicit_environment() -> None:
    text = RESTART_ALL_PATH.read_text(encoding="utf-8")
    secrets_resolve = (
        'BYBIT_SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-'
        '$SECRETS_ROOT/secret_files/bybit}"'
    )
    secrets_launch = 'OPENCLAW_SECRETS_DIR="$BYBIT_SECRETS_DIR"'
    assert secrets_resolve in text
    assert secrets_launch in text
    assert text.index(secrets_resolve) < text.index(secrets_launch) < text.index(
        "nohup rust/target/release/openclaw-engine"
    )

    for env_name, shell_name in (
        ("OPENCLAW_DEMO_LEARNING_LANE_WRITER", "demo_learning_lane_writer"),
        ("OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED", "bounded_probe_adapter_enabled"),
    ):
        resolve_index = text.index(f'{shell_name}="${{{env_name}:-')
        normalization = f'{shell_name}="${{{shell_name}:-0}}"'
        launch_index = text.index(f'{env_name}="${{{shell_name}}}"')
        assert normalization in text
        assert resolve_index < text.index(normalization) < launch_index


def test_demo_label_cannot_authorize_a_mainnet_runtime_attestation() -> None:
    adapter = _load_adapter()
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_mainnet",
        allow_mainnet=True,
        runtime_mode="mainnet",
        authorization_scope="mainnet",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    intent = _intent(attestation["environment_identity_digest"])

    errors = adapter.validate_runtime_attestation_for_intent(
        attestation,
        intent,
        phase="preflight",
        now="2026-07-11T10:15:00Z",
    )

    assert any("mainnet" in error or "safe runtime" in error for error in errors)


def test_generic_demo_attestation_remains_valid_for_intent_only_contract() -> None:
    adapter = _load_adapter()
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    intent = _intent(attestation["environment_identity_digest"])

    assert adapter.validate_runtime_attestation_for_intent(
        attestation,
        intent,
        phase="preflight",
        now="2026-07-11T10:15:00Z",
    ) == []
    assert adapter.validate_intent(
        intent,
        supplied_intent_digest="sha256:" + "e" * 64,
        actual_intent_digest="sha256:" + "e" * 64,
        actual_source_head="a" * 40,
        tree_clean=True,
        actual_host="trade-core-runtime",
        deploy_script_digest="sha256:" + "b" * 64,
        now="2026-07-11T10:15:00Z",
    ) == []


def test_apply_rejects_environment_the_local_probe_cannot_attest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    adapter = _load_adapter()
    now = datetime.now(timezone.utc)
    intent = _intent("sha256:" + "c" * 64, target_environment="demo")
    intent["approved_at"] = (now - timedelta(minutes=2)).isoformat()
    intent["expires_at"] = (now + timedelta(hours=1)).isoformat()
    intent["expected_deploy_script_sha256"] = adapter.sha256_bytes(
        adapter.DEPLOY_COMPONENT.read_bytes()
    )
    intent_path = tmp_path / "intent.json"
    intent_bytes = json.dumps(intent, sort_keys=True, separators=(",", ":")).encode()
    intent_path.write_bytes(intent_bytes)
    monkeypatch.setattr(
        adapter,
        "git_text",
        lambda *args: "a" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "trade-core-runtime")
    monkeypatch.setenv("OPENCLAW_DEPLOY_ADAPTER_APPLY", "1")

    exit_code = adapter.main(
        [
            "--intent",
            str(intent_path),
            "--intent-sha256",
            adapter.sha256_bytes(intent_bytes),
            "--apply",
        ]
    )

    output = capsys.readouterr()
    assert exit_code == 4
    blocked = json.loads(output.err)
    assert blocked == {
        "status": "RUNTIME_ENVIRONMENT_PROBE_TARGET_UNSUPPORTED",
        "errors": [
            "target_environment is unsupported by the local runtime probe; "
            "expected live_demo"
        ],
    }


def test_actual_apply_stays_disabled_after_probe_until_recovery_controls_are_bound(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    adapter = _load_adapter()
    now = datetime.now(timezone.utc)
    observed = now - timedelta(minutes=1)
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="live_demo",
        authorization_scope="live_demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at=observed.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    intent = _intent(
        attestation["environment_identity_digest"],
        target_environment="live_demo",
    )
    intent["approved_at"] = (now - timedelta(minutes=2)).isoformat()
    intent["expires_at"] = (now + timedelta(hours=1)).isoformat()
    intent["expected_deploy_script_sha256"] = adapter.sha256_bytes(
        adapter.DEPLOY_COMPONENT.read_bytes()
    )
    intent_path = tmp_path / "intent.json"
    attestation_path = tmp_path / "runtime-attestation.json"
    intent_bytes = json.dumps(intent, sort_keys=True, separators=(",", ":")).encode()
    intent_path.write_bytes(intent_bytes)
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")

    monkeypatch.setattr(
        adapter,
        "git_text",
        lambda *args: "a" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "trade-core-runtime")
    intent_only_exit = adapter.main(
        [
            "--intent",
            str(intent_path),
            "--intent-sha256",
            adapter.sha256_bytes(intent_bytes),
        ]
    )
    intent_only_status = json.loads(capsys.readouterr().out)
    assert intent_only_exit == 0
    assert intent_only_status["status"] == "INTENT_VALIDATED_APPLY_DISABLED"
    assert intent_only_status["apply_executable"] is False
    assert intent_only_status["blocked_on"] == "deploy recovery controls"

    monkeypatch.setenv("OPENCLAW_DEPLOY_ADAPTER_APPLY", "1")
    monkeypatch.setattr(
        adapter,
        "probe_local_runtime_environment",
        lambda **_kwargs: (attestation, []),
    )

    def forbidden_component(*_args, **_kwargs):
        raise AssertionError("deploy component must not run without a local probe")

    monkeypatch.setattr(adapter.subprocess, "run", forbidden_component)
    exit_code = adapter.main(
        [
            "--intent",
            str(intent_path),
            "--intent-sha256",
            adapter.sha256_bytes(intent_bytes),
            "--runtime-attestation",
            str(attestation_path),
            "--apply",
        ]
    )

    output = capsys.readouterr()
    assert exit_code == 4
    blocked = json.loads(output.err)
    assert blocked["status"] == "DEPLOY_RECOVERY_CONTROLS_UNBOUND"
    assert blocked["apply_executable"] is False


def test_effect_receipt_binds_pre_and_post_runtime_identity() -> None:
    adapter = _load_adapter()
    preflight = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    postcheck = adapter.build_runtime_environment_attestation(
        phase="postcheck",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "e" * 64,
        observed_at="2026-07-11T10:16:00Z",
        expires_at="2026-07-11T10:26:00Z",
    )
    intent = _intent(preflight["environment_identity_digest"])
    receipt = adapter.build_effect_receipt(
        intent,
        intent_digest="sha256:" + "f" * 64,
        component_exit_code=0,
        component_stdout=(
            b">>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=123 POST_SHA=" + b"e" * 64 + b"\n"
        ),
        component_stderr=b"",
        started_at="2026-07-11T10:12:00Z",
        completed_at="2026-07-11T10:15:00Z",
        pre_runtime_attestation=preflight,
        post_runtime_attestation=postcheck,
    )

    assert receipt["effect_status"] == "APPLIED_VERIFIED"
    assert receipt["runtime_environment_identity_digest"] == intent[
        "expected_runtime_environment_identity_digest"
    ]
    assert receipt["pre_runtime_attestation"] == preflight
    assert receipt["post_runtime_attestation"] == postcheck
    assert adapter.parse_time(receipt["evidence_expires_at"]) == adapter.parse_time(
        postcheck["expires_at"]
    )
    assert adapter.validate_effect_receipt(receipt, require_success=True) == []

    ops_postcheck = adapter.build_ops_evidence(
        receipt,
        phase="postcheck",
        observed_at=postcheck["observed_at"],
        evidence_id="ev-ops-post",
        expiry=postcheck["expires_at"],
        running_binary_sha256=receipt["deployed_binary_sha256"],
    )
    operation_receipt = ops_postcheck["operation_receipt"]
    assert operation_receipt["runtime_environment_identity_digest"] == postcheck[
        "environment_identity_digest"
    ]
    assert operation_receipt["runtime_attestation_digest"] == postcheck[
        "attestation_digest"
    ]
    assert operation_receipt["actual_endpoint_class"] == "bybit_demo"
    assert operation_receipt["allow_mainnet"] is False
    assert operation_receipt["running_binary_sha256"] == postcheck[
        "process_identity_digest"
    ]
    receipt_schema = json.loads(
        (ROOT / ".codex/schemas/effect_adapter_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt_schema["properties"]["pre_runtime_attestation"] == {
        "$ref": "#/$defs/runtimeAttestation"
    }
    assert receipt_schema["properties"]["post_runtime_attestation"] == {
        "$ref": "#/$defs/runtimeAttestation"
    }
    runtime_schema = json.loads(
        (ROOT / ".codex/schemas/runtime_environment_attestation_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt_schema["$defs"]["runtimeAttestation"] == {
        key: runtime_schema[key]
        for key in ("type", "additionalProperties", "required", "properties")
    }

    with pytest.raises(ValueError, match="must match runtime attestation"):
        adapter.build_ops_evidence(
            receipt,
            phase="postcheck",
            observed_at=postcheck["observed_at"],
            evidence_id="ev-ops-post-relabelled",
            expiry="2026-07-11T10:30:00Z",
            running_binary_sha256=receipt["deployed_binary_sha256"],
        )


def test_postdeploy_mainnet_drift_cannot_produce_a_success_receipt() -> None:
    adapter = _load_adapter()
    preflight = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    unsafe_postcheck = adapter.build_runtime_environment_attestation(
        phase="postcheck",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_mainnet",
        allow_mainnet=True,
        runtime_mode="mainnet",
        authorization_scope="mainnet",
        process_identity_digest="sha256:" + "e" * 64,
        observed_at="2026-07-11T10:16:00Z",
        expires_at="2026-07-11T10:26:00Z",
    )
    intent = _intent(preflight["environment_identity_digest"])
    receipt = adapter.build_effect_receipt(
        intent,
        intent_digest="sha256:" + "f" * 64,
        component_exit_code=0,
        component_stdout=(
            b">>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=123 POST_SHA=" + b"e" * 64 + b"\n"
        ),
        component_stderr=b"",
        started_at="2026-07-11T10:12:00Z",
        completed_at="2026-07-11T10:15:00Z",
        pre_runtime_attestation=preflight,
        post_runtime_attestation=unsafe_postcheck,
    )

    assert receipt["effect_status"] == "FAILED"
    assert adapter.validate_effect_receipt(receipt, require_success=True)
