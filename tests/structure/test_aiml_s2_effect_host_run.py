"""S2E.2a:S2 effect 受信主機 runner CLI 的結構證明(production 拒絕矩陣 + artifact 契約)。

* 三個 mode 的 ``--out-dir`` canonical artifact 契約在**每一條路徑**上都成立(頂層 finally);
* ``production`` / ``unknown`` 的**全路徑** typed 拒且 driver / fence capability **從未被構造**
  (以兩個 runner 的建構計數器 + 會炸的 factory 雙重斷言);
* ``--allow-production`` 單獨不足;三條件並存才 admitted;``--production-confirm`` 必須逐字回填;
* ``apply`` mode 今日一律 ``HOST_CAPABILITY_SUPPLIER_ABSENT`` 非零退出(鏡 adapter 的 driver=None);
* runner 家族的五個檔案全部存在,且 AST no-raw-command 掃描對整個家族成立。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_pg_observer_bootstrap as obs  # noqa: E402
import agent_governance_s2_0_host_runner as s2_0_runner  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402
import aiml_s2_effect_host_run as cli  # noqa: E402

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-28T12:00:00+00:00"

RUNNER_FAMILY = (
    HELPERS / "agent_governance_s2_host_kernel.py",
    HELPERS / "agent_governance_s2_host_observer.py",
    HELPERS / "agent_governance_s2_0_host_runner.py",
    HELPERS / "agent_governance_s2_1_host_runner.py",
    HELPERS / "aiml_s2_effect_host_run.py",
)


def _intent(target_class="production"):
    return obs.build_pg_observer_bootstrap_intent(
        target_class=target_class, target_host="trade-core", database="trading_ai",
        observer_role="aiml_s2e2_cli_observer", observed_schema="learning",
        observed_relations=["alr_consumer_events"], socket_dir="/var/run/postgresql",
        auth_mapping="pg_hba_ident_local", applier_node_id="s2_0_apply_actor",
        postcheck_node_id="s2_0_ops_postcheck", created_at=CREATED, ttl_seconds=900,
        source_head=HEAD,
    )


def _write_intent(tmp_path: Path, intent) -> Path:
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(intent, sort_keys=True, indent=2), encoding="utf-8")
    return path


def _artifacts(out_dir: Path) -> dict:
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in out_dir.glob("*.json")}


# --------------------------------------------------------------------------- #
# family completeness + the AST acceptance criterion over the whole family
# --------------------------------------------------------------------------- #
def test_the_runner_family_is_complete():
    for path in RUNNER_FAMILY:
        assert path.is_file(), path


def test_no_raw_command_outside_the_kernel_for_the_complete_family():
    from test_agent_governance_s2_host_kernel import _raw_command_findings  # noqa: PLC0415

    for path in RUNNER_FAMILY:
        findings = _raw_command_findings(path)
        if path.name == "agent_governance_s2_host_kernel.py":
            # kernel 是唯一 exec 點:必須帶 subprocess,且**只**准帶 subprocess。
            assert findings and all("import subprocess" in item for item in findings), findings
        else:
            assert findings == [], f"{path.name}: {findings}"


# --------------------------------------------------------------------------- #
# mode probe — always safe, always writes the canonical artifacts
# --------------------------------------------------------------------------- #
def test_probe_mode_writes_the_canonical_artifact_set(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD,
    ])
    assert code == cli.EXIT_OK
    artifacts = _artifacts(out_dir)
    assert set(artifacts) == {"target_class_view.json", "kernel_abi.json", "run_summary.json"}
    assert artifacts["run_summary.json"]["status"] == "PROBED"
    assert artifacts["run_summary.json"]["closure_pass_blocked"] is True
    assert artifacts["run_summary.json"]["production_effect_performed"] is False
    assert artifacts["run_summary.json"]["nine_authorities_false"] is True
    assert artifacts["run_summary.json"]["source_head_verification"] == (
        "deferred_to_closure_baseline_binding"
    )
    assert artifacts["target_class_view.json"]["target_class"] in {
        kernel.TARGET_CLASS_NON_TARGET, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE,
        kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN,
    }
    # canonical JSON:sorted keys + 2 空格縮排 + 結尾換行。
    raw = (out_dir / "run_summary.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw == json.dumps(
        artifacts["run_summary.json"], ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"


def test_probe_mode_with_observe_runs_the_process_separated_observer(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe",
    ])
    artifacts = _artifacts(out_dir)
    assert code == cli.EXIT_OK
    assert artifacts["run_summary.json"]["status"] == "PROBED"
    assert artifacts["observation.json"]["self_digest"] == (
        artifacts["run_summary.json"]["observation_digest"]
    )


def test_bad_source_head_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as error:
        cli.main([
            "--session", "s2_0", "--mode", "probe", "--out-dir", str(tmp_path / "out"),
            "--source-head", "not-a-head",
        ])
    assert error.value.code == cli.EXIT_USAGE


def test_admit_and_apply_require_an_intent(tmp_path):
    for mode in ("admit", "apply"):
        with pytest.raises(SystemExit):
            cli.main([
                "--session", "s2_0", "--mode", mode, "--out-dir", str(tmp_path / mode),
                "--source-head", HEAD,
            ])


# --------------------------------------------------------------------------- #
# production refusal matrix — the driver / fence capability is NEVER constructed
# --------------------------------------------------------------------------- #
def _force_target_class(monkeypatch, target_class):
    monkeypatch.setattr(
        cli.host_kernel, "derive_host_target_class",
        lambda: {"target_class": target_class, "reason": "forced by test", "facts": {}},
    )


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
@pytest.mark.parametrize("flags", [
    [],
    ["--allow-production"],
    ["--allow-production", "--production-confirm", "sha256:" + "9" * 64],
])
def test_production_refusal_never_constructs_a_driver(tmp_path, monkeypatch, target_class, flags):
    _force_target_class(monkeypatch, target_class)
    intent = _intent()
    out_dir = tmp_path / "out"
    before = s2_0_runner.ObserverBootstrapHostDriver.constructions
    code = cli.main([
        "--session", "s2_0", "--mode", "apply", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)), *flags,
    ])
    assert code == cli.EXIT_ADMISSION_REFUSED
    assert s2_0_runner.ObserverBootstrapHostDriver.constructions == before
    admission = _artifacts(out_dir)["admission.json"]
    assert admission["admitted"] is False
    assert admission["layer"] == "L1_host_safety_only"
    # 缺 operator SSHSIG 這條理由在**每一種** flag 組合下都存在 ⇒ --allow-production 單獨不足。
    assert any("operator SSHSIG" in reason for reason in admission["refusal_reasons"])


def test_allow_production_alone_is_never_enough(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    intent = _intent()
    out_dir = tmp_path / "out"
    cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--allow-production",
    ])
    admission = _artifacts(out_dir)["admission.json"]
    assert admission["allow_production"] is True
    assert admission["admitted"] is False
    assert any("--production-confirm" in reason for reason in admission["refusal_reasons"])
    assert any("operator SSHSIG" in reason for reason in admission["refusal_reasons"])


def test_production_confirm_must_be_the_exact_intent_digest(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_UNKNOWN)
    intent = _intent()
    monkeypatch.setattr(
        cli, "_verify_operator_authorization",
        lambda **kwargs: {"verified": True, "errors": []},
    )
    out_dir = tmp_path / "wrong"
    cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--allow-production", "--production-confirm", "sha256:" + "0" * 64,
    ])
    assert _artifacts(out_dir)["admission.json"]["admitted"] is False
    exact = tmp_path / "exact"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(exact),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--allow-production", "--production-confirm", intent["self_digest"],
    ])
    admission = _artifacts(exact)["admission.json"]
    assert code == cli.EXIT_OK
    assert admission["admitted"] is True
    assert admission["production_confirm_matches"] is True
    assert _artifacts(exact)["run_summary.json"]["status"] == "ADMITTED_DRY_RUN"


def test_source_head_must_equal_the_intent_source_head(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE)
    intent = _intent()
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", "f" * 40, "--intent-file", str(_write_intent(tmp_path, intent)),
    ])
    assert code == cli.EXIT_ADMISSION_REFUSED
    assert any(
        "--source-head must equal" in reason
        for reason in _artifacts(out_dir)["admission.json"]["refusal_reasons"]
    )


def test_unverifiable_operator_authorization_is_never_reported_as_verified(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    intent = _intent()
    permit = tmp_path / "permit.json"
    permit.write_text(json.dumps({"totally": "bogus"}), encoding="utf-8")
    signature = tmp_path / "permit.sig"
    signature.write_bytes(b"not-a-signature")
    out_dir = tmp_path / "out"
    cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--operator-permit", str(permit), "--operator-signature", str(signature),
        "--allow-production", "--production-confirm", intent["self_digest"],
    ])
    admission = _artifacts(out_dir)["admission.json"]
    assert admission["operator_authorization"]["verified"] is False
    assert admission["operator_authorization"]["errors"]
    assert admission["admitted"] is False


# --------------------------------------------------------------------------- #
# apply mode — reachable gate, no host capability supplier in source
# --------------------------------------------------------------------------- #
def test_apply_mode_fails_closed_without_a_host_capability_supplier(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE)
    intent = _intent()
    out_dir = tmp_path / "out"
    before = s2_0_runner.ObserverBootstrapHostDriver.constructions
    code = cli.main([
        "--session", "s2_0", "--mode", "apply", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
    ])
    assert code == cli.EXIT_HOST_CAPABILITY_ABSENT
    assert s2_0_runner.ObserverBootstrapHostDriver.constructions == before
    summary = _artifacts(out_dir)["run_summary.json"]
    assert summary["status"] == "HOST_CAPABILITY_SUPPLIER_ABSENT"
    assert "deliberately absent from source" in summary["reason"]
    assert summary["production_effect_performed"] is False


@pytest.mark.parametrize("session", ["s2_0", "s2_1"])
def test_every_mode_writes_a_run_summary_even_on_refusal(tmp_path, monkeypatch, session):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    intent = _intent()
    for mode in ("probe", "admit", "apply"):
        out_dir = tmp_path / f"{session}-{mode}"
        cli.main([
            "--session", session, "--mode", mode, "--out-dir", str(out_dir),
            "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        ])
        summary = _artifacts(out_dir)["run_summary.json"]
        assert summary["session"] == session and summary["mode"] == mode
        assert summary["exit_code"] in {
            cli.EXIT_OK, cli.EXIT_ADMISSION_REFUSED, cli.EXIT_HOST_CAPABILITY_ABSENT,
            cli.EXIT_OBSERVATION_FAILED,
        }
        assert summary["closure_pass_blocked"] is True


# --------------------------------------------------------------------------- #
# the CLI is really runnable as a script (no import-time host contact)
# --------------------------------------------------------------------------- #
def test_cli_runs_as_a_script_and_makes_no_host_contact(tmp_path):
    out_dir = tmp_path / "out"
    completed = subprocess.run(
        [sys.executable, str(HELPERS / "aiml_s2_effect_host_run.py"),
         "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
         "--source-head", HEAD],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == cli.EXIT_OK, completed.stderr
    summary = json.loads(completed.stdout.strip().splitlines()[-1])
    assert summary["status"] == "PROBED"
    assert (out_dir / "run_summary.json").is_file()
