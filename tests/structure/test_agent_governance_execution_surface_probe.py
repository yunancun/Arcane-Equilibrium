"""Public-interface tests for the execution-surface truth probe."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "agent_governance"
    / "execution_surface_truth_probe_v1.json"
)
sys.path.insert(0, str(HELPERS))

import agent_governance as governance_facade  # noqa: E402
from agent_governance_registry import load_registry, validate_registry  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _source(source_id: str, source_kind: str, payload: dict) -> dict:
    source = {
        "source_id": source_id,
        "source_kind": source_kind,
        "payload": payload,
        "payload_sha256": _digest(payload),
    }
    source["source_sha256"] = _digest(source)
    return source


def _request(*sources: dict) -> dict:
    return {
        "schema_version": "execution_surface_probe_request_v1",
        "surface_profile_id": "codex_native_collaboration_v1",
        "sources": list(sources),
    }


def _run_cli(tmp_path: Path, capsys, request: dict) -> tuple[int, dict]:
    request_path = (
        ROOT
        / ".pytest_cache"
        / "execution-surface-probe"
        / tmp_path.name
        / "probe-request.json"
    )
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")
    exit_code = governance_facade.main(
        ["execution-surface-probe", f"@{request_path.relative_to(ROOT)}"]
    )
    return exit_code, json.loads(capsys.readouterr().out)


class _ExactHostVerifier:
    def __init__(self, profile_id: str, profile_sha256: str, sources: list[dict]):
        self.profile_id = profile_id
        self.profile_sha256 = profile_sha256
        self.sources = {source["source_id"]: source for source in sources}
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(
        self,
        surface_profile_id: str,
        surface_profile_sha256: str,
        source: dict,
    ) -> bool:
        self.calls.append((surface_profile_id, surface_profile_sha256, source))
        return (
            surface_profile_id == self.profile_id
            and surface_profile_sha256 == self.profile_sha256
            and source == self.sources.get(source.get("source_id"))
        )


def test_public_cli_keeps_selected_values_unverified_without_host_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        )
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    assert exit_code == 0
    assert report["schema_version"] == "execution_surface_truth_probe_v1"
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    key_report = report["config_precedence"]["keys"][0]
    assert key_report["key"] == "agents.enabled"
    assert key_report["declared_candidates"] == [
        {"source_id": "repository_config", "precedence_rank": 20, "value": True}
    ]
    assert key_report["selected"] == {
        "status": "UNVERIFIED",
        "value": None,
        "origin_source_id": None,
        "evidence_source_id": None,
    }
    assert key_report["mismatch_classification"] == "SELECTION_UNVERIFIED"
    assert key_report["causal_attribution"] == "NOT_INFERRED"


def test_public_cli_does_not_promote_forged_host_config_with_self_computed_hashes(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "global_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": False}]},
        ),
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        ),
        _source(
            "host_config_read",
            "host_config_read_observation_v1",
            {
                "ordered_layer_source_ids": [
                    "global_config",
                    "repository_config",
                ],
                "selected_values": [
                    {
                        "key": "agents.enabled",
                        "value": False,
                        "origin_source_id": "global_config",
                    }
                ],
            },
        ),
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    assert exit_code == 0
    key_report = report["config_precedence"]["keys"][0]
    assert key_report["selected"] == {
        "status": "UNVERIFIED",
        "value": None,
        "origin_source_id": None,
        "evidence_source_id": None,
    }
    assert key_report["mismatch_classification"] == "SELECTION_UNVERIFIED"
    assert key_report["causal_attribution"] == "NOT_INFERRED"
    assert report["config_precedence"]["observed_layer_order"] == []
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert report["authenticity"] == {
        "host_verifier": "UNAVAILABLE",
        "profile_selection": "CALLER_CLAIMED",
        "sha256_scope": "INTEGRITY_ONLY",
    }
    assert {
        item["source_id"]: item["authenticity_status"]
        for item in report["source_manifest"]
    }["host_config_read"] == "CALLER_CLAIMED"


def test_public_cli_does_not_promote_forged_prompt_or_cwd_with_valid_hashes(
    tmp_path: Path,
    capsys,
) -> None:
    instruction_digest = "sha256:" + "a" * 64
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        ),
        _source(
            "prompt_input",
            "prompt_input_observation_v1",
            {
                "cwd_class": "linked_worktree",
                "instruction_sources": [
                    {
                        "instruction_id": "canonical_repo_agents",
                        "selection": "SELECTED",
                        "content_sha256": instruction_digest,
                    },
                    {
                        "instruction_id": "knowledgepilot_auto_rule",
                        "selection": "SELECTED",
                        "content_sha256": "sha256:" + "b" * 64,
                    },
                    {
                        "instruction_id": "workspace_entry_shim",
                        "selection": "NOT_SELECTED",
                        "content_sha256": None,
                    },
                ],
            },
        ),
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    assert exit_code == 0
    instructions = report["instruction_selection"]
    assert instructions["status"] == "UNVERIFIED"
    assert instructions["cwd_class"] is None
    assert instructions["evidence_source_id"] is None
    assert instructions["sources"] == []
    assert instructions["causal_attribution"] == "NOT_INFERRED"
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert {
        item["source_id"]: item["authenticity_status"]
        for item in report["source_manifest"]
    }["prompt_input"] == "CALLER_CLAIMED"


def test_allowlisted_config_surface_accepts_only_safe_typed_values(
    tmp_path: Path,
    capsys,
) -> None:
    values = [
        {"key": "agents.enabled", "value": True},
        {"key": "agents.max_concurrent_threads_per_session", "value": 3},
        {"key": "agents.default_subagent_model", "value": "gpt-5.6-terra"},
        {"key": "agents.default_subagent_reasoning_effort", "value": "medium"},
        {"key": "agents.interrupt_message", "value": False},
    ]
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": values},
        )
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    assert exit_code == 0
    assert [
        item["key"] for item in report["config_precedence"]["keys"]
    ] == sorted(item["key"] for item in values)


def test_unknown_config_key_and_secret_value_fail_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    secret = "credential-sentinel-must-not-leak"
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "api_token", "value": secret}]},
        )
    )

    exit_code, error = _run_cli(tmp_path, capsys, request)

    serialized = json.dumps(error, sort_keys=True)
    assert exit_code == 2
    assert error["status"] == "FAIL"
    assert error["error_code"] == "SOURCE_POLICY_VIOLATION"
    assert secret not in serialized
    assert "api_token" not in serialized


def test_probe_module_owns_the_schema_and_closed_source_policy() -> None:
    registry = load_registry()

    assert validate_registry(registry) == []
    policy = governance_facade.execution_surface_probe_policy()
    assert policy == {
        "schema_version": "execution_surface_probe_policy_v1",
        "report_schema_path": (
            ".codex/schemas/execution_surface_truth_probe_v1.schema.json"
        ),
        "declaration_source_precedence": {
            "global_config": 10,
            "repository_config": 20,
        },
        "host_observation_sources": {
            "host_config_read": "host_config_read_observation_v1",
            "prompt_input": "prompt_input_observation_v1",
        },
        "config_key_allowlist": [
            "agents.default_subagent_model",
            "agents.default_subagent_reasoning_effort",
            "agents.enabled",
            "agents.interrupt_message",
            "agents.max_concurrent_threads_per_session",
        ],
        "config_value_allowlists": {
            "agents.default_subagent_model": [
                "gpt-5.6-luna",
                "gpt-5.6-sol",
                "gpt-5.6-terra",
            ],
            "agents.default_subagent_reasoning_effort": [
                "high",
                "low",
                "max",
                "medium",
                "ultra",
                "xhigh",
            ],
        },
        "instruction_source_allowlist": [
            "canonical_repo_agents",
            "knowledgepilot_auto_rule",
            "workspace_entry_shim",
        ],
        "missing_selection_status": "UNVERIFIED",
        "causal_attribution": "NOT_INFERRED",
    }
    assert (ROOT / policy["report_schema_path"]).is_file()


def test_caller_cannot_mutate_the_probe_policy_authority() -> None:
    policy = governance_facade.execution_surface_probe_policy()
    policy["config_key_allowlist"].remove("agents.enabled")

    assert "agents.enabled" in governance_facade.execution_surface_probe_policy()[
        "config_key_allowlist"
    ]


def test_report_preserves_safe_evidence_payloads_with_both_digests(
    tmp_path: Path,
    capsys,
) -> None:
    source = _source(
        "repository_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": True}]},
    )

    exit_code, report = _run_cli(tmp_path, capsys, _request(source))

    assert exit_code == 0
    binding = report["source_manifest"][0]
    assert binding["evidence_payload"] == source["payload"]
    assert binding["payload_sha256"] == _digest(binding["evidence_payload"])
    assert binding["source_sha256"] == source["source_sha256"]


def test_report_binds_the_exact_registry_policy(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        )
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    assert exit_code == 0
    assert report["policy_sha256"] == _digest(
        governance_facade.execution_surface_probe_policy()
    )
    profile = load_registry()["execution_policy"]["surface_profiles"][
        "codex_native_collaboration_v1"
    ]
    assert report["surface_profile_sha256"] == _digest(profile)


def test_direct_api_exact_host_verifier_can_promote_complete_observation() -> None:
    values = [
        {"key": "agents.enabled", "value": True},
        {"key": "agents.max_concurrent_threads_per_session", "value": 3},
        {"key": "agents.default_subagent_model", "value": "gpt-5.6-terra"},
        {"key": "agents.default_subagent_reasoning_effort", "value": "medium"},
        {"key": "agents.interrupt_message", "value": False},
    ]
    selected_values = [
        {**item, "origin_source_id": "repository_config"} for item in values
    ]
    repository_source = _source(
        "repository_config",
        "config_declaration_v1",
        {"values": values},
    )
    host_source = _source(
        "host_config_read",
        "host_config_read_observation_v1",
        {
            "ordered_layer_source_ids": ["repository_config"],
            "selected_values": selected_values,
        },
    )
    prompt_source = _source(
        "prompt_input",
        "prompt_input_observation_v1",
        {
            "cwd_class": "linked_worktree",
            "instruction_sources": [
                {
                    "instruction_id": "canonical_repo_agents",
                    "selection": "SELECTED",
                    "content_sha256": "sha256:" + "a" * 64,
                },
                {
                    "instruction_id": "knowledgepilot_auto_rule",
                    "selection": "SELECTED",
                    "content_sha256": "sha256:" + "b" * 64,
                },
                {
                    "instruction_id": "workspace_entry_shim",
                    "selection": "NOT_SELECTED",
                    "content_sha256": None,
                },
            ],
        },
    )
    request = _request(repository_source, host_source, prompt_source)
    registry = load_registry()
    profile = registry["execution_policy"]["surface_profiles"][
        "codex_native_collaboration_v1"
    ]
    verifier = _ExactHostVerifier(
        "codex_native_collaboration_v1",
        _digest(profile),
        [host_source, prompt_source],
    )

    report = governance_facade.build_execution_surface_truth_report(
        request,
        registry,
        host_verifier=verifier,
    )

    assert report["report_status"] == "COMPLETE"
    assert report["authenticity"] == {
        "host_verifier": "AVAILABLE",
        "profile_selection": "HOST_VERIFIED",
        "sha256_scope": "INTEGRITY_ONLY",
    }
    assert report["config_precedence"]["observed_layer_order"] == [
        "repository_config"
    ]
    assert {
        item["selected"]["status"]
        for item in report["config_precedence"]["keys"]
    } == {"HOST_OBSERVED"}
    assert report["instruction_selection"]["status"] == "HOST_OBSERVED"
    assert report["instruction_selection"]["cwd_class"] == "linked_worktree"
    assert [call[2]["source_id"] for call in verifier.calls] == [
        "host_config_read",
        "prompt_input",
    ]
    assert (
        "host-verified execution-surface report requires an out-of-band verifier"
        in governance_facade.validate_execution_surface_truth_report(
            report,
            registry,
        )
    )
    assert governance_facade.validate_execution_surface_truth_report(
        report,
        registry,
        host_verifier=verifier,
    ) == []


def test_verified_host_mismatch_is_classified_without_causal_attribution() -> None:
    global_source = _source(
        "global_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": False}]},
    )
    repository_source = _source(
        "repository_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": True}]},
    )
    host_source = _source(
        "host_config_read",
        "host_config_read_observation_v1",
        {
            "ordered_layer_source_ids": ["global_config", "repository_config"],
            "selected_values": [
                {
                    "key": "agents.enabled",
                    "value": False,
                    "origin_source_id": "global_config",
                }
            ],
        },
    )
    request = _request(global_source, repository_source, host_source)
    registry = load_registry()
    profile_sha256 = _digest(
        registry["execution_policy"]["surface_profiles"][
            "codex_native_collaboration_v1"
        ]
    )

    report = governance_facade.build_execution_surface_truth_report(
        request,
        registry,
        host_verifier=_ExactHostVerifier(
            "codex_native_collaboration_v1", profile_sha256, [host_source]
        ),
    )

    key_report = report["config_precedence"]["keys"][0]
    assert (
        key_report["mismatch_classification"]
        == "DIFFERS_FROM_HIGHEST_PRECEDENCE_DECLARATION"
    )
    assert key_report["causal_attribution"] == "NOT_INFERRED"


def test_report_schema_exposes_integrity_authenticity_boundary() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert report["authenticity"]["sha256_scope"] == "INTEGRITY_ONLY"
    assert report["authenticity"]["host_verifier"] == "UNAVAILABLE"
    assert report["authenticity"]["profile_selection"] == "CALLER_CLAIMED"
    assert report["causal_limits"]["sha256_establishes_authenticity"] is False
    assert {
        binding["authenticity_status"] for binding in report["source_manifest"]
    } == {"DECLARATION_SNAPSHOT"}


def test_public_json_cannot_supply_a_host_verifier(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        )
    )
    request["host_verifier"] = True

    exit_code, error = _run_cli(tmp_path, capsys, request)

    assert exit_code == 2
    assert error["error_code"] == "SOURCE_POLICY_VIOLATION"
    assert error["error"] == "execution-surface probe request fields are not exact"


def test_probe_loader_rejects_absolute_and_traversal_paths_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    secret_path = tmp_path / "credential-sentinel.json"

    absolute_exit = governance_facade.main(
        ["execution-surface-probe", f"@{secret_path}"]
    )
    absolute_error = json.loads(capsys.readouterr().out)
    traversal_exit = governance_facade.main(
        ["execution-surface-probe", "@../credential-sentinel.json"]
    )
    traversal_error = json.loads(capsys.readouterr().out)

    assert absolute_exit == 2
    assert absolute_error["error_code"] == "PROBE_PATH_ABSOLUTE"
    assert "credential-sentinel" not in json.dumps(absolute_error)
    assert traversal_exit == 2
    assert traversal_error["error_code"] == "PROBE_PATH_TRAVERSAL"
    assert "credential-sentinel" not in json.dumps(traversal_error)


def test_probe_loader_rejects_symlink_missing_and_non_regular_paths(
    tmp_path: Path,
    capsys,
) -> None:
    probe_dir = ROOT / ".pytest_cache" / "execution-surface-probe" / tmp_path.name
    probe_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside-repository.json"
    target.write_text("{}", encoding="utf-8")
    link = probe_dir / "linked.json"
    link.unlink(missing_ok=True)
    link.symlink_to(target)

    cases = [
        (link, "PROBE_PATH_SYMLINK"),
        (probe_dir / "missing.json", "PROBE_PATH_MISSING"),
        (probe_dir, "PROBE_PATH_NOT_REGULAR"),
    ]
    for path, error_code in cases:
        exit_code = governance_facade.main(
            ["execution-surface-probe", f"@{path.relative_to(ROOT)}"]
        )
        error = json.loads(capsys.readouterr().out)
        assert exit_code == 2
        assert error["error_code"] == error_code


def test_probe_loader_rejects_oversized_invalid_utf8_and_unsafe_json(
    tmp_path: Path,
    capsys,
) -> None:
    probe_dir = ROOT / ".pytest_cache" / "execution-surface-probe" / tmp_path.name
    probe_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        (
            "oversized.json",
            b" " * (governance_facade.EXECUTION_SURFACE_PROBE_MAX_REQUEST_BYTES + 1),
            "PROBE_INPUT_TOO_LARGE",
        ),
        ("invalid-utf8.json", b"\xff", "PROBE_INPUT_ENCODING"),
        ("duplicate-key.json", b'{"sources":[],"sources":[]}', "PROBE_INPUT_JSON"),
        ("nonfinite.json", b'{"value":NaN}', "PROBE_INPUT_JSON"),
        (
            "secret-invalid.json",
            b'{"credential-sentinel":',
            "PROBE_INPUT_JSON",
        ),
        (
            "excessive-depth.json",
            b"[" * 2000 + b"]" * 2000,
            "PROBE_INPUT_JSON",
        ),
    ]
    for filename, payload, error_code in cases:
        path = probe_dir / filename
        path.write_bytes(payload)
        exit_code = governance_facade.main(
            ["execution-surface-probe", f"@{path.relative_to(ROOT)}"]
        )
        error = json.loads(capsys.readouterr().out)
        assert exit_code == 2
        assert error["error_code"] == error_code
        assert "credential-sentinel" not in json.dumps(error, sort_keys=True)


def test_public_cli_declaration_report_is_schema_valid_and_self_bound(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {"values": [{"key": "agents.enabled", "value": True}]},
        )
    )

    exit_code, report = _run_cli(tmp_path, capsys, request)

    schema = json.loads(
        (
            ROOT
            / governance_facade.execution_surface_probe_policy()[
                "report_schema_path"
            ]
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert schema_subset_errors(report, schema, schema) == []
    assert report["report_digest"] == governance_facade.execution_surface_truth_report_digest(
        report
    )


def test_committed_reference_fixture_is_schema_valid_and_honestly_unverified() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schema = json.loads(
        (
            ROOT
            / governance_facade.execution_surface_probe_policy()[
                "report_schema_path"
            ]
        ).read_text(encoding="utf-8")
    )

    assert schema_subset_errors(report, schema, schema) == []
    assert report["report_digest"] == governance_facade.execution_surface_truth_report_digest(
        report
    )
    assert report["report_status"] == "COMPLETE_WITH_UNVERIFIED"
    assert {
        item["selected"]["status"]
        for item in report["config_precedence"]["keys"]
    } == {"UNVERIFIED"}
    assert report["instruction_selection"]["status"] == "UNVERIFIED"


def test_same_value_from_lower_layer_is_an_origin_mismatch(
) -> None:
    global_source = _source(
        "global_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": True}]},
    )
    repository_source = _source(
        "repository_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": True}]},
    )
    host_source = _source(
        "host_config_read",
        "host_config_read_observation_v1",
        {
            "ordered_layer_source_ids": [
                "global_config",
                "repository_config",
            ],
            "selected_values": [
                {
                    "key": "agents.enabled",
                    "value": True,
                    "origin_source_id": "global_config",
                }
            ],
        },
    )
    request = _request(global_source, repository_source, host_source)
    registry = load_registry()
    profile_sha256 = _digest(
        registry["execution_policy"]["surface_profiles"][
            "codex_native_collaboration_v1"
        ]
    )

    report = governance_facade.build_execution_surface_truth_report(
        request,
        registry,
        host_verifier=_ExactHostVerifier(
            "codex_native_collaboration_v1", profile_sha256, [host_source]
        ),
    )

    assert (
        report["config_precedence"]["keys"][0]["mismatch_classification"]
        == "ORIGIN_DIFFERS_FROM_HIGHEST_PRECEDENCE_DECLARATION"
    )


def test_public_validator_rechecks_schema_policy_payload_and_report_digests() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    registry = load_registry()

    assert governance_facade.validate_execution_surface_truth_report(
        report, registry
    ) == []
    tampered = deepcopy(report)
    tampered["source_manifest"][0]["evidence_payload"]["values"][0][
        "value"
    ] = False
    tampered["policy_sha256"] = "sha256:" + "f" * 64

    errors = governance_facade.validate_execution_surface_truth_report(
        tampered, registry
    )

    assert "execution-surface policy digest is invalid" in errors
    assert "repository_config: evidence payload digest is invalid" in errors
    assert "execution-surface report digest is invalid" in errors


def test_public_validator_replays_sources_instead_of_trusting_resealed_semantics() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report["config_precedence"]["keys"][0]["mismatch_classification"] = (
        "OBSERVED_VALUE_NOT_DECLARED"
    )
    report["report_digest"] = governance_facade.execution_surface_truth_report_digest(
        report
    )

    errors = governance_facade.validate_execution_surface_truth_report(
        report, load_registry()
    )

    assert "execution-surface report differs from deterministic source replay" in errors


def test_untrusted_selection_source_fails_closed(
    tmp_path: Path,
    capsys,
) -> None:
    request = _request(
        _source(
            "caller_selected_values",
            "host_config_read_observation_v1",
            {
                "ordered_layer_source_ids": ["repository_config"],
                "selected_values": [
                    {
                        "key": "agents.enabled",
                        "value": True,
                        "origin_source_id": "repository_config",
                    }
                ],
            },
        )
    )

    exit_code, error = _run_cli(tmp_path, capsys, request)

    assert exit_code == 2
    assert error["error_code"] == "SOURCE_POLICY_VIOLATION"
    assert error["error"] == "execution-surface source is not allowlisted"


def test_tampered_payload_digest_fails_before_report_emission(
    tmp_path: Path,
    capsys,
) -> None:
    source = _source(
        "repository_config",
        "config_declaration_v1",
        {"values": [{"key": "agents.enabled", "value": True}]},
    )
    source["payload"]["values"][0]["value"] = False

    exit_code, error = _run_cli(tmp_path, capsys, _request(source))

    assert exit_code == 2
    assert error["error_code"] == "SOURCE_POLICY_VIOLATION"
    assert error["error"] == "execution-surface source payload digest is invalid"


def test_secret_like_value_cannot_hide_behind_an_allowlisted_string_key(
    tmp_path: Path,
    capsys,
) -> None:
    secret = "credential-sentinel-must-not-leak"
    request = _request(
        _source(
            "repository_config",
            "config_declaration_v1",
            {
                "values": [
                    {
                        "key": "agents.default_subagent_model",
                        "value": secret,
                    }
                ]
            },
        )
    )

    exit_code, error = _run_cli(tmp_path, capsys, request)

    assert exit_code == 2
    assert error["error_code"] == "SOURCE_POLICY_VIOLATION"
    assert secret not in json.dumps(error, sort_keys=True)
