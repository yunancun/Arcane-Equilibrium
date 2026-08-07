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
import agent_governance_s2_host_observer as host_observer  # noqa: E402
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
        # 掃描器對整個家族(含 kernel)都必須乾淨:``subprocess``/``ctypes`` 的 kernel-only 例外
        # 由掃描器自己按檔名判定,而不是由呼叫端事後把 finding 濾掉。
        assert _raw_command_findings(path) == [], f"{path.name}: {_raw_command_findings(path)}"


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


def test_observe_on_a_production_grade_host_needs_an_explicit_acknowledgement(tmp_path, monkeypatch):
    """P2 #7:observer 面原本完全不過 L1,直接對真主機發 ``systemctl show``。"""

    monkeypatch.setattr(
        cli.host_kernel, "derive_host_target_class",
        lambda: {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "forced", "facts": {}},
    )

    def _must_not_spawn(*args, **kwargs):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("the observer child must not spawn on a refused L1 observation")

    monkeypatch.setattr(
        cli.host_kernel.HostExecutionKernel, "run_observer_child", _must_not_spawn
    )
    out_dir = tmp_path / "refused"
    code = cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe",
    ])
    summary = _artifacts(out_dir)["run_summary.json"]
    assert code == cli.EXIT_OBSERVATION_FAILED
    assert summary["status"] == "OBSERVATION_FAILED"
    assert "refused by the L1 host gate" in summary["observation_error"]
    assert "observation.json" not in _artifacts(out_dir)


@pytest.mark.parametrize("target_class", [
    kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN,
])
def test_observe_is_admitted_once_production_is_acknowledged(tmp_path, monkeypatch, target_class):
    monkeypatch.setattr(
        cli.host_kernel, "derive_host_target_class",
        lambda: {"target_class": target_class, "reason": "forced", "facts": {}},
    )
    spawned = {"count": 0}

    def _spawn(self, request):
        spawned["count"] += 1
        raise cli.host_kernel.S2HostCommandFailed("no systemctl on this development machine")

    monkeypatch.setattr(cli.host_kernel.HostExecutionKernel, "run_observer_child", _spawn)
    out_dir = tmp_path / "acknowledged"
    cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe", "--allow-production",
    ])
    # L1 放行(child 真的被起了),失敗理由是主機本身而不是閘。
    assert spawned["count"] == 1
    summary = _artifacts(out_dir)["run_summary.json"]
    assert "refused by the L1 host gate" not in summary["observation_error"]


# --------------------------------------------------------------------------- #
# 出境秘密掃描(父側 sink):observation.json 落盤之前必須過同一支掃描器
# --------------------------------------------------------------------------- #
# 反例以片段拼接構造(repo 內不留看起來像真憑證的字面量)。
_SECRET_SHAPED_PROPERTY = "PG" + "PASSWORD" + "=" + "s3cr3t-not-real"


def _child_payload(environment_value: str) -> str:
    """一份 self_digest 合法的 child stdout —— 用來模擬「child 那道閘被繞過」的情形。"""

    import agent_governance_s2_host_observer as host_observer

    body = {
        "schema_version": host_observer.OBSERVATION_SCHEMA_VERSION,
        "observed_at": "2026-07-29T00:00:00Z",
        "target_class_view": {"target_class": kernel.TARGET_CLASS_NON_TARGET},
        "request_digest": "sha256:" + "0" * 64,
        "faces": {
            host_observer.FACE_UNIT_STATE: {
                "properties": {"ActiveState": "active", "Environment": environment_value},
            },
        },
    }
    body["self_digest"] = host_observer._digest(body)
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_observe_drops_an_observation_that_carries_secret_shaped_content(tmp_path, monkeypatch):
    """父側**不得**把「子行程有守衛」當成自己的保證:落盤 sink 自己也要擋。"""

    monkeypatch.setattr(
        cli.host_kernel.HostExecutionKernel, "run_observer_child",
        lambda self, request: _child_payload(_SECRET_SHAPED_PROPERTY),
    )
    out_dir = tmp_path / "leaky"
    code = cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe",
    ])
    artifacts = _artifacts(out_dir)
    summary = artifacts["run_summary.json"]
    assert code == cli.EXIT_OBSERVATION_FAILED
    assert summary["status"] == "OBSERVATION_FAILED"
    assert "carried secret-shaped content and was dropped" in summary["observation_error"]
    # 整包丟棄:既沒有 observation.json,run_summary 也拿不到 observation_digest。
    assert "observation.json" not in artifacts
    assert "observation_digest" not in summary
    assert _SECRET_SHAPED_PROPERTY not in json.dumps(artifacts, ensure_ascii=False)


def test_observe_writes_a_clean_observation_unchanged(tmp_path, monkeypatch):
    clean = _child_payload("ALR_SOURCE_HEAD=" + "0" * 40)
    monkeypatch.setattr(
        cli.host_kernel.HostExecutionKernel, "run_observer_child",
        lambda self, request: clean,
    )
    out_dir = tmp_path / "clean"
    code = cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe",
    ])
    artifacts = _artifacts(out_dir)
    assert code == cli.EXIT_OK
    assert artifacts["observation.json"] == json.loads(clean)
    assert artifacts["run_summary.json"]["observation_digest"] == (
        artifacts["observation.json"]["self_digest"]
    )


def test_the_parent_egress_guard_runs_before_the_observation_is_returned():
    """結構釘:守衛在 ``_observation`` 的 return 之前,故 ``observation.json`` 永遠寫不出髒 payload。"""

    import inspect

    source = inspect.getsource(cli._observation)
    assert source.index("scan_serializable_surface_for_secrets") < source.rindex("return observation")


# --------------------------------------------------------------------------- #
# 頂層 finally 的共同 sink:run_summary.json 與 stdout 兩面受同一道守衛
# --------------------------------------------------------------------------- #
def _emitted(out_dir: Path, capsys) -> tuple[dict, dict]:
    """回 ``(落盤 summary, stdout summary)`` —— 兩面必須逐鍵相同,守衛不得只擋一面。"""

    artifact = _artifacts(out_dir)["run_summary.json"]
    streamed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert artifact == streamed
    return artifact, streamed


def test_a_clean_summary_reaches_both_sinks_unchanged(tmp_path, capsys):
    """守衛不得改寫乾淨的一輪:兩個 sink 逐鍵相同,且退出碼仍是那條路徑自己的號碼。"""

    out_dir = tmp_path / "clean-summary"
    code = cli.main([
        "--session", "s2_0", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD,
    ])
    artifact, _streamed = _emitted(out_dir, capsys)
    assert code == cli.EXIT_OK
    assert artifact["status"] == "PROBED"
    assert artifact["exit_code"] == code


def test_a_secret_shaped_summary_is_withheld_from_both_sinks(tmp_path, monkeypatch, capsys):
    """``observation_error`` 是一段完全不受控的例外訊息 —— 它進得了 summary,就得被最後一道擋下。"""

    def _leaky(self, request):
        raise cli.host_kernel.S2HostCommandFailed(
            "systemctl show failed: " + _SECRET_SHAPED_PROPERTY
        )

    monkeypatch.setattr(cli.host_kernel.HostExecutionKernel, "run_observer_child", _leaky)
    out_dir = tmp_path / "leaky-summary"
    code = cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--observe",
    ])
    artifact, streamed = _emitted(out_dir, capsys)
    assert code == cli.EXIT_EGRESS_GUARD_WITHHELD
    assert artifact["status"] == cli.EGRESS_GUARD_WITHHELD_STATUS
    # artifact 的 exit_code 與 process 真實退出碼恆一致 —— 守衛開火的路徑也不例外。
    assert artifact["exit_code"] == code
    assert artifact["egress_guard_findings"] >= 1
    # 整包丟棄:髒欄位一個都不在,九 authority 的恆假宣告仍在。
    assert "observation_error" not in artifact
    assert "out_dir" not in artifact and "source_head" not in artifact
    assert artifact["nine_authorities_false"] is True
    assert artifact["closure_pass_blocked"] is True
    # 封閉列舉可以回填(argparse choices 是 code-owned 的)。
    assert (artifact["session"], artifact["mode"]) == ("s2_1", "probe")
    # 兩個 sink 都不得出現那個值(stdout 由 ``_emitted`` 對齊過,這裡連原始文字一起掃)。
    every_artifact = json.dumps(_artifacts(out_dir), ensure_ascii=False)
    assert _SECRET_SHAPED_PROPERTY not in every_artifact
    assert _SECRET_SHAPED_PROPERTY not in json.dumps(streamed, ensure_ascii=False)


def test_the_withheld_envelope_keeps_only_boolean_facts(tmp_path, monkeypatch, capsys):
    """s2_4 補償 lane:守衛可以吃掉理由字串,但不能吃掉「有沒有動到主機」這個布林事實。"""

    monkeypatch.setattr(
        cli.s2_4_recovery, "reconcile_before_s2_4_intent",
        lambda driver, **kwargs: {
            "status": cli.s2_4_recovery.INTENT_GATE_RECOVERY_REQUIRED,
            "reasons": ["the host journal quoted " + _SECRET_SHAPED_PROPERTY],
            "mutation_performed": False,
            "driver_engaged": False,
        },
    )
    out_dir = tmp_path / "leaky-verdict"
    code = cli.main([
        "--session", "s2_4", "--mode", "reconcile", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--lane", "probe", "--lane-id", "0" * 64,
    ])
    artifact, _streamed = _emitted(out_dir, capsys)
    assert code == cli.EXIT_EGRESS_GUARD_WITHHELD
    assert artifact["status"] == cli.EGRESS_GUARD_WITHHELD_STATUS
    assert artifact["mutation_performed"] is False
    assert artifact["driver_engaged"] is False
    assert "reasons" not in artifact
    # 只斷言本守衛管得到的兩面。``s2_4_startup_verdict.json`` 有它**自己**那道守衛(recovery 的
    # ``_verdict`` 出境前跑 ``_component.scan_serializable_surface``),而這個測試替身正是把整支
    # ``reconcile_before_s2_4_intent`` 換掉、連那道一起繞過的情形 —— 兩道是各自 sink 的守衛,
    # 不是互相的備援。
    assert _SECRET_SHAPED_PROPERTY not in json.dumps(artifact, ensure_ascii=False)


def test_a_guard_that_cannot_run_withholds_the_summary(tmp_path, monkeypatch, capsys):
    """掃描器自己炸掉 = 無法斷言乾淨 ⇒ 扣住整包,絕不因為守衛壞了而放行。"""

    def _broken(payload):
        raise RuntimeError("the central secret criterion is unavailable")

    monkeypatch.setattr(cli.host_kernel, "scan_serializable_surface_for_secrets", _broken)
    out_dir = tmp_path / "broken-guard"
    code = cli.main([
        "--session", "s2_0", "--mode", "probe", "--out-dir", str(out_dir),
        "--source-head", HEAD,
    ])
    artifact, _streamed = _emitted(out_dir, capsys)
    assert code == cli.EXIT_EGRESS_GUARD_WITHHELD
    assert artifact["status"] == cli.EGRESS_GUARD_WITHHELD_STATUS


def test_the_summary_guard_runs_before_both_sinks():
    """結構釘:守衛在落盤與 stdout **兩個**寫入之前,且掃的是已寫完 exit_code 的最終物件。"""

    import inspect

    source = inspect.getsource(cli.main)
    guard = source.index("_summary_egress_guard(summary)")
    assert source.rindex('summary["exit_code"] = exit_code') < guard
    assert guard < source.index('"run_summary.json", emitted')
    assert guard < source.rindex("sys.stdout.write")


def test_every_typed_exit_code_is_distinct():
    codes = [
        cli.EXIT_OK, cli.EXIT_USAGE, cli.EXIT_ADMISSION_REFUSED,
        cli.EXIT_HOST_CAPABILITY_ABSENT, cli.EXIT_OBSERVATION_FAILED,
        cli.EXIT_INPUT_INVALID, cli.EXIT_INTERNAL_ERROR, cli.EXIT_RECOVERY_REQUIRED,
        cli.EXIT_EGRESS_GUARD_WITHHELD,
    ]
    assert len(set(codes)) == len(codes)


# --------------------------------------------------------------------------- #
# P2 #8 — bad input is a typed fail-closed, and the artifact matches the exit code
# --------------------------------------------------------------------------- #
def _artifact_exit_code_matches(out_dir: Path, code: int) -> None:
    assert _artifacts(out_dir)["run_summary.json"]["exit_code"] == code


def test_a_malformed_intent_file_is_typed_and_the_artifact_matches_the_exit_code(tmp_path):
    intent_file = tmp_path / "intent.json"
    intent_file.write_text("{ not json at all", encoding="utf-8")
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(intent_file),
    ])
    summary = _artifacts(out_dir)["run_summary.json"]
    assert code == cli.EXIT_INPUT_INVALID
    assert summary["status"] == "INPUT_INVALID"
    assert "not valid JSON" in summary["input_error"]
    _artifact_exit_code_matches(out_dir, code)


def test_an_absent_intent_file_is_typed_not_a_traceback(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(tmp_path / "nope.json"),
    ])
    assert code == cli.EXIT_INPUT_INVALID
    assert "not readable" in _artifacts(out_dir)["run_summary.json"]["input_error"]
    _artifact_exit_code_matches(out_dir, code)


def test_an_unreadable_operator_signature_is_typed(tmp_path):
    permit = tmp_path / "permit.json"
    permit.write_text(json.dumps({"totally": "bogus"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, _intent())),
        "--operator-permit", str(permit), "--operator-signature", str(tmp_path / "absent.sig"),
    ])
    assert code == cli.EXIT_INPUT_INVALID
    _artifact_exit_code_matches(out_dir, code)


def test_a_permit_without_a_signature_is_an_admission_refusal(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    permit = tmp_path / "permit.json"
    permit.write_text(json.dumps({"totally": "bogus"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, _intent())),
        "--operator-permit", str(permit),
    ])
    assert code == cli.EXIT_ADMISSION_REFUSED
    assert any(
        "must be supplied together" in reason
        for reason in _artifacts(out_dir)["admission.json"]["refusal_reasons"]
    )


def test_an_unexpected_failure_is_loud_and_still_leaves_a_consistent_artifact(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("injected internal failure")

    monkeypatch.setattr(cli, "_admission", _boom)
    out_dir = tmp_path / "out"
    code = cli.main([
        "--session", "s2_0", "--mode", "admit", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, _intent())),
    ])
    summary = _artifacts(out_dir)["run_summary.json"]
    assert code == cli.EXIT_INTERNAL_ERROR
    assert summary["status"] == "RUNNER_FAILED"
    assert "injected internal failure" in summary["runner_error"]
    _artifact_exit_code_matches(out_dir, code)


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


@pytest.mark.parametrize("session", ["s2_0", "s2_1"])
def test_a_disposable_local_intent_is_refused_on_a_production_grade_host(
    tmp_path, monkeypatch, session
):
    """P1-B(CLI 面):四條件裡的三條全滿足,唯一的拒絕理由是 intent/主機 class 不匹配。"""

    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    monkeypatch.setattr(
        cli, "_verify_operator_authorization",
        lambda **kwargs: {"verified": True, "errors": []},
    )
    intent = _intent(target_class="disposable_local")
    out_dir = tmp_path / f"{session}-mismatch"
    before = s2_0_runner.ObserverBootstrapHostDriver.constructions
    code = cli.main([
        "--session", session, "--mode", "apply", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--allow-production", "--production-confirm", intent["self_digest"],
    ])
    admission = _artifacts(out_dir)["admission.json"]
    assert code == cli.EXIT_ADMISSION_REFUSED
    assert admission["admitted"] is False
    assert admission["refusal_reasons"] == [
        reason for reason in admission["refusal_reasons"] if "disposable_local" in reason
    ]
    assert s2_0_runner.ObserverBootstrapHostDriver.constructions == before


def test_a_forged_disposable_candidate_view_is_refused_by_every_mode(tmp_path, monkeypatch):
    """P1-A(CLI 面):rehearsal-only class 不再是「無條件放行」的萬能鑰匙。"""

    _force_target_class(monkeypatch, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE)
    monkeypatch.setattr(
        cli, "_verify_operator_authorization",
        lambda **kwargs: {"verified": True, "errors": []},
    )
    intent = _intent()
    for mode in ("admit", "apply"):
        out_dir = tmp_path / mode
        code = cli.main([
            "--session", "s2_1", "--mode", mode, "--out-dir", str(out_dir),
            "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
            "--allow-production", "--production-confirm", intent["self_digest"],
        ])
        admission = _artifacts(out_dir)["admission.json"]
        assert code == cli.EXIT_ADMISSION_REFUSED
        assert any("rehearsal-only" in reason for reason in admission["refusal_reasons"])


def test_the_s2_0_observation_never_asks_for_an_unobservable_process_record(monkeypatch):
    """P2-D:``s2_0`` 沒有 unit 面 ⇒ 它絕不可請求 ``process_identity``(否則發出的是預設值)。"""

    seen: dict = {}

    def _capture(self, request):
        seen.update(request)
        raise cli.host_kernel.S2HostCommandFailed("no host contact in this test")

    monkeypatch.setattr(cli.host_kernel.HostExecutionKernel, "run_observer_child", _capture)
    for session in ("s2_0", "s2_1"):
        seen.clear()
        args = cli.argparse.Namespace(
            session=session, allow_production=False, observe=True,
        )
        with pytest.raises(cli.host_kernel.S2HostCommandFailed):
            cli._observation(args, {"target_class": kernel.TARGET_CLASS_NON_TARGET})
        # request 本身必須是可承認的(process 面永遠與 unit 面同行,或根本不出現)。
        assert host_observer.validate_observation_request(seen) == []
        if session == "s2_0":
            assert host_observer.FACE_PROCESS_IDENTITY not in seen["faces"]
        else:
            assert host_observer.FACE_UNIT_STATE in seen["faces"]
            assert host_observer.FACE_PROCESS_IDENTITY in seen["faces"]


def test_source_head_must_equal_the_intent_source_head(tmp_path, monkeypatch):
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
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
    # P1-A:``disposable_candidate`` 不再是可導出的 class(且生產進入點一律拒),故「閘可達」
    # 這件事只能經真正的四條件承認來證明。
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_PRODUCTION)
    monkeypatch.setattr(
        cli, "_verify_operator_authorization",
        lambda **kwargs: {"verified": True, "errors": []},
    )
    intent = _intent()
    out_dir = tmp_path / "out"
    before = s2_0_runner.ObserverBootstrapHostDriver.constructions
    code = cli.main([
        "--session", "s2_0", "--mode", "apply", "--out-dir", str(out_dir),
        "--source-head", HEAD, "--intent-file", str(_write_intent(tmp_path, intent)),
        "--allow-production", "--production-confirm", intent["self_digest"],
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
def test_registry_binds_the_runner_family_to_the_two_existing_adapters():
    registry = json.loads((ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8"))
    adapters = registry["effect_adapters"]
    shared = {
        "helper_scripts/maintenance_scripts/agent_governance_s2_host_kernel.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_host_observer.py",
        "helper_scripts/maintenance_scripts/aiml_s2_effect_host_run.py",
    }
    s2_0 = adapters["pg_observer_bootstrap_adapter_v1"]["implementation_paths"]
    s2_1 = adapters["alr_quiesce_fence_adapter_v1"]["implementation_paths"]
    assert shared <= set(s2_0) and shared <= set(s2_1)
    assert "helper_scripts/maintenance_scripts/agent_governance_s2_0_host_runner.py" in s2_0
    assert "helper_scripts/maintenance_scripts/agent_governance_s2_1_host_runner.py" in s2_1
    # runner 不是新的 effect adapter,而是既有 adapter 的主機面實作 ⇒ 不得新增 adapter 條目。
    assert "s2_host_runner_adapter_v1" not in adapters
    for path in (*s2_0, *s2_1):
        assert (ROOT / path).is_file(), path
    # 九條 S2 adapter 的 authority / invariant 一行不改(本波只 append implementation_paths)。
    assert "nine authorities stay false" in adapters["pg_observer_bootstrap_adapter_v1"]["invariant"]
    assert (
        "no route_task effect node or closure effect binding is injected before the S2.0 "
        "EFFECT session"
    ) in adapters["pg_observer_bootstrap_adapter_v1"]["invariant"]
    assert (
        "NEVER pkill/kill-by-name/kill-by-pattern/kill-by-pid"
    ) in adapters["alr_quiesce_fence_adapter_v1"]["invariant"]


def test_script_index_documents_every_new_runner_family_script():
    index = (ROOT / "helper_scripts/SCRIPT_INDEX.md").read_text(encoding="utf-8").splitlines()
    for path in RUNNER_FAMILY:
        prefix = f"| `maintenance_scripts/{path.name}` |"
        rows = [line for line in index if line.startswith(prefix)]
        assert len(rows) == 1, path.name


# Linux caps a *single* argv element at ``MAX_ARG_STRLEN`` = 32 * PAGE_SIZE,
# independently of the ~16x larger total ``ARG_MAX``.  Measured read-only on the
# current runtime host ``trade-core`` on 2026-08-07 (Linux 6.17.0-35-generic
# x86_64, Ubuntu 24.04.4 LTS): PAGE_SIZE=4096, largest accepted single argv
# element = 131071 bytes => MAX_ARG_STRLEN = 131072; ARG_MAX = 2097152.
MAX_ARG_STRLEN = 128 * 1024
LINUX_PAGE_SIZE_MEASURED_ON_TRADE_CORE = 4096

# G1 的 transport invariant 執法面在
# ``tests/structure/test_agent_governance_context_transport.py``:
# ``agent_governance.py`` 的 ``--context-artifact`` 現在**只**接受 ``@path``,inline
# JSON 是 typed refusal。argv 元素因此恆為一條路徑,與 payload 大小解耦。
CONTEXT_TRANSPORT_INVARIANT_TEST = (
    "tests/structure/test_agent_governance_context_transport.py"
)
# compiled Context 真正會被送進一次 model call 的部分,是 shared + role 兩個 semantic
# projection 串起來的 prompt prefix;governing cap 是 Registry 宣告的
# ``max_prompt_utf8_bytes_per_call``,不是 execve。餘裕以 bytes 明寫,成長會在這裡先紅。
SEMANTIC_PREFIX_REQUIRED_HEADROOM_BYTES = 16 * 1024
# registry 對 compiled Context 的**全部**貢獻只有 digest 與由它推導的 DAG binding。
REGISTRY_CONTRIBUTION_TO_CONTEXT_BUDGET_BYTES = 2048


def _registry_bytes() -> int:
    return len((ROOT / ".codex/agent_registry_v1.json").read_bytes())


def test_registry_bytes_are_never_argv_transported_and_stay_inside_their_budget():
    """(舊名 ``test_registry_tracked_bytes_leave_headroom_under_the_execve_single_argument_cap``)

    舊測試把「registry 檔身 + 24 KiB 餘裕」當成 compiled artifact 的**代理**,理由就寫在
    它自己的 docstring:「乾淨樹上 artifact ≈ registry + ~18 KiB(115030 vs 96675)」。
    這個代理關係現在**實測不成立**,而且不只是漂移了,是方向本身就錯:

    * 差距已從 +18 KiB 變成 +27 KiB(registry 107089 vs E1 artifact 134159);
    * 更關鍵的是,registry **不是** artifact 變大的成因。逐位元組量測:registry 對
      compiled Context 的全部貢獻是 ``registry_digest``(73 bytes)與由它推導出來的
      ``execution_dag_binding``(~892 bytes),合計約 1 KiB。artifact 的 134 KiB 幾乎
      全部來自 context packs 的 source content(docs/README.md 17511、AGENTS.md 16437
      …),那是**文件**成長,不是 registry 成長。

    而且 registry 從頭到尾由 ``load_registry()`` 從磁碟讀取,**從不進入任何 argv**——
    所以「registry 的 execve 單參數餘裕」這個量測從一開始就是範疇錯誤。

    語義修復後這裡釘兩條更強的 invariant:
    ① registry 的**檔身位元組不會進入 transported Context**(結構性,直接量);
    ② registry 對 Context 的貢獻仍有一條**明確且緊**的 payload budget(2 KiB,現值
       約 1 KiB),取代那條已失效的 24 KiB 代理餘裕。
    舊測試唯一仍然成立的硬界(``registry < MAX_ARG_STRLEN``)原封保留。
    """

    registry_bytes = _registry_bytes()
    # 舊測試中唯一沒有壞掉的斷言,原封保留(非放寬)。
    assert registry_bytes < MAX_ARG_STRLEN, registry_bytes

    dirt = _worktree_dirt()
    if dirt is not None:
        pytest.skip(
            "the Registry-contribution measurement needs a clean worktree "
            f"(compile_context ingests the working-tree diff): {dirt}"
        )

    artifact = _measure_context_artifacts()["_artifacts"]["E1"]
    plan = json.loads(artifact["canonical_plan"])
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )

    # ① registry 檔身沒有被 inline 進 transported Context。逐層枚舉 plan 的全部 dict
    #    key,斷言 registry 的頂層 section 名稱一個都不出現 —— registry 只能以 digest
    #    被引用。任何人把整份(或一部分)registry 塞進 Context,這裡就會紅。
    def _collect_keys(node, sink):
        if isinstance(node, dict):
            sink.update(node)
            for value in node.values():
                _collect_keys(value, sink)
        elif isinstance(node, list):
            for value in node:
                _collect_keys(value, sink)

    plan_keys: set[str] = set()
    _collect_keys(plan, plan_keys)
    leaked = sorted(set(registry) & plan_keys)
    assert leaked == [], f"Registry sections are inlined into the Context: {leaked}"

    # ② registry 對 Context 的實際貢獻仍在明確預算內。
    contribution = len(
        json.dumps(
            {
                "registry_digest": plan["registry_digest"],
                "registry_schema_version": plan["registry_schema_version"],
                "execution_dag_binding": plan["execution_dag_binding"],
            },
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    )
    assert contribution <= REGISTRY_CONTRIBUTION_TO_CONTEXT_BUDGET_BYTES, {
        "registry_file_bytes": registry_bytes,
        "registry_contribution_to_context_bytes": contribution,
        "budget": REGISTRY_CONTRIBUTION_TO_CONTEXT_BUDGET_BYTES,
    }


# 這支釘量的是 **source**(乾淨工作樹)而不是當下的編輯狀態,故必須有一道「樹必須乾淨」的
# 前置。E2 的 M-1:FIX-3 把本測試**綠著刪掉**且未在 commit body 揭露 —— 刪除本身可辯護(髒樹會誤
# 紅),不揭露不可辯護。本波以「前置 + 誠實 skip 理由」把它復原,使它在 CI / 乾淨 HEAD 上恆跑,
# 在編輯中的髒樹上誠實 SKIP 而不是誤紅,也不是消失。
_EXECVE_CAP_MEASURED_ROLES = ("E1", "E2", "OPS", "PM")


def _worktree_dirt() -> str | None:
    """乾淨回 ``None``;否則回一句可讀的「為什麼這棵樹不能拿來量 source」。"""

    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT), capture_output=True, text=True, check=False, timeout=120,
        )
    except OSError as error:  # pragma: no cover - 無 git 的環境
        return f"git is not invocable here ({error})"
    if completed.returncode != 0:  # pragma: no cover - 非 git 樹 / 壞倉庫
        return f"git status failed (rc={completed.returncode}): {completed.stderr.strip()[:200]}"
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    if dirty:
        return f"{len(dirty)} uncommitted/untracked path(s), first: {dirty[0].strip()!r}"
    return None


def _measure_context_artifacts() -> dict:
    """Compile the four E2-measured role Contexts once and return sizes + artifacts."""

    from agent_governance_context import capture_repository_baseline
    from agent_governance_execution import compile_context, materialize_context_artifact
    from agent_governance_routing import route_task

    scope = ["helper_scripts/maintenance_scripts/agent_governance_s2_host_kernel.py"]
    baseline = capture_repository_baseline(root=ROOT)
    routed = route_task({
        "task_shape": "implementation", "surfaces": ["governance"], "risk": "medium",
        "uncertainty": "low", "side_effect_class": "repo_write",
        "objective": "measure the compiled context artifact size after the registry append",
        "scope": scope, "dirty_scope": scope, "verification_scope": scope,
        "acceptance_criteria": ["registry growth leaves execve headroom"],
        "hard_stops": ["no runtime mutation"],
        "baseline": baseline,
        "direct_interfaces": ["agent_governance_s2_host_kernel"],
        "previous_failure": "PR#129 registry growth crossed MAX_ARG_STRLEN and raised E2BIG",
    })
    measured: dict[str, int] = {}
    artifacts: dict[str, dict] = {}
    for role in _EXECVE_CAP_MEASURED_ROLES:
        artifact = materialize_context_artifact(
            compile_context(role, routed["task_facts"], root=ROOT)
        )
        artifacts[role] = artifact
        measured[role] = len(
            json.dumps(artifact, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
    return {**measured, "_artifacts": artifacts, "_baseline": baseline}


def test_compiled_context_artifact_transport_is_file_bound_not_argv_bound():
    """(舊名 ``test_compiled_context_artifact_stays_under_the_execve_cap``)

    舊測試對四個角色逐一釘 ``artifact_bytes < MAX_ARG_STRLEN``。它現在紅,實測
    E1 134159 / E2 134151 / OPS 120928 / PM 98654,前兩者已越過 131072。

    但把 artifact 壓回 131072 以下**不是**正確的修復,理由是這條 cap 根本不管這個
    payload:``MAX_ARG_STRLEN`` 只約束**單一 argv 元素**,而 compiled Context 從來不是
    argv 元素——canonical 慣例是 ``--context-artifact @<context.json>``,argv 裡走的是
    一條路徑。G1 逐一盤點全 repo 41 個帶該旗標的 tracked 檔後,確認**沒有任何 active
    caller** 把 payload 放進單一 argv(``.claude/workflows/openclaw-full-audit.js`` 亦
    無 ``child_process``,它是 in-process model call,並且自帶 byte cap)。

    真正的缺陷是這條 invariant 只有慣例、零 source 執法:``_json_arg`` 對
    ``--context-artifact`` 同時接受 ``@file`` 與 inline JSON。所以語義修復是**把假設
    換成結構**,而不是把數字換成另一個數字:

    * transport 面 —— ``--context-artifact`` 現在只接受 ``@path``,inline 是 typed
      refusal(執法與負面測試在 ``CONTEXT_TRANSPORT_INVARIANT_TEST``);本測試在此處
      cross-check 該執法仍在,所以任何人把 inline 放回來,這裡就會紅。
    * payload 面 —— 換成兩條**真正**約束這個 payload 的預算:
      ① 會進 model call 的 semantic prompt prefix 必須留在 Registry 宣告的
         ``max_prompt_utf8_bytes_per_call`` 內,且保留 16 KiB 明寫餘裕;
      ② 整份 artifact 必須留在 CLI 的檔案 transport 預算內。

    這不是放寬:舊斷言只保證「payload 小到即使被誤用成 argv 也不會炸」,新斷言保證
    「payload 結構上不可能成為 argv」**加上**「payload 在它真正會經過的通道裡有明確餘裕」。
    """

    dirt = _worktree_dirt()
    if dirt is not None:
        pytest.skip(
            "the compiled-artifact measurement only means anything on a clean worktree "
            f"(compile_context ingests the working-tree diff): {dirt}"
        )

    import agent_governance as governance  # noqa: PLC0415 - HELPERS is already on sys.path

    # transport 面:inline 必須仍然被結構性拒絕。
    source = (HELPERS / "agent_governance.py").read_text(encoding="utf-8")
    assert "_json_arg(args.context_artifact)" not in source
    assert "_context_artifact_arg(args.context_artifact)" in source
    with pytest.raises(ValueError, match=r"must be @"):
        governance._context_artifact_arg('{"schema_version": "context_artifact_v1"}')
    assert (ROOT / CONTEXT_TRANSPORT_INVARIANT_TEST).is_file()

    measured = _measure_context_artifacts()
    artifacts = measured.pop("_artifacts")
    baseline = measured.pop("_baseline")

    # payload 面 ①:真正會進一次 model call 的 prompt prefix。
    for role, artifact in artifacts.items():
        prefix_bytes = len(
            (
                artifact["shared_task_context_canonical"]
                + "\n\n"
                + artifact["role_context_delta_canonical"]
            ).encode("utf-8")
        )
        cap = json.loads(artifact["budget_authority_canonical"])[
            "max_prompt_utf8_bytes_per_call"
        ]
        assert prefix_bytes + SEMANTIC_PREFIX_REQUIRED_HEADROOM_BYTES <= cap, {
            "role": role, "semantic_prefix_bytes": prefix_bytes,
            "max_prompt_utf8_bytes_per_call": cap,
            "required_headroom": SEMANTIC_PREFIX_REQUIRED_HEADROOM_BYTES,
        }

    # payload 面 ②:整份 artifact 的檔案 transport 預算。
    assert max(measured.values()) < governance.CONTEXT_ARTIFACT_MAX_BYTES, {
        "measured": measured,
        "file_transport_budget": governance.CONTEXT_ARTIFACT_MAX_BYTES,
        "tree_state": baseline,
    }


def test_an_uncreatable_out_dir_is_a_typed_usage_exit_not_a_bare_traceback(tmp_path):
    """RES-7:``mkdir`` 原本在 ``try:`` 之外 ⇒ 裸 traceback + rc=1 + 零 artifact。

    out-dir 建不起來時**沒有任何地方**可以落盤,那是誠實的物理限制;但收場必須是 typed usage
    exit + 一行 stderr,而不是一個 traceback 把 process 退成 1(那與本檔 docstring 字面衝突)。
    """

    blocked = tmp_path / "not_a_dir"
    blocked.write_text("i am a file", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(HELPERS / "aiml_s2_effect_host_run.py"),
         "--session", "s2_1", "--mode", "probe", "--out-dir", str(blocked / "nope"),
         "--source-head", HEAD],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == cli.EXIT_USAGE, (completed.returncode, completed.stderr)
    assert "Traceback" not in completed.stderr, completed.stderr
    assert "--out-dir is not creatable" in completed.stderr
    assert completed.stdout == ""


def test_the_summary_write_failure_never_replaces_the_exit_code(tmp_path, monkeypatch):
    """RES-7 的另一半:``finally`` 內逸出的例外會**取代** return value ⇒ 又變回裸 traceback。"""

    out_dir = tmp_path / "out"

    def _explode(path, value):
        raise OSError("the artifact directory vanished mid-run")

    monkeypatch.setattr(cli, "_canonical_write", _explode)
    code = cli.main([
        "--session", "s2_1", "--mode", "probe", "--out-dir", str(out_dir), "--source-head", HEAD,
    ])
    assert code == cli.EXIT_INTERNAL_ERROR


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
