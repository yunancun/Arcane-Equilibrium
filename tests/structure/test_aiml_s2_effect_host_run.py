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
    _force_target_class(monkeypatch, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE)
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


MAX_ARG_STRLEN = 128 * 1024


def test_registry_tracked_bytes_leave_headroom_under_the_execve_single_argument_cap():
    """PR#129 的 ``E2BIG`` 前例的**可重現**量測:只量 tracked 檔身(E2 P2 #14 的處置)。

    原測試以 ``capture_repository_baseline()`` + ``compile_context()`` 量 artifact bytes 並釘
    8 KiB 餘裕。E2 指出該量測**不可重現**:``compile_context`` 會把當下工作樹的 diff / inventory
    納入,未提交與未追蹤檔都會推高它。這不是理論顧慮 —— 本次修復期間同一支測試實測:

    ==================================  ==========
    工作樹狀態                            E1 artifact
    ==================================  ==========
    乾淨 @ ``9dfb4d27f``                  115030
    修復進行中(3 個 source 檔已改)        124107
    修復進行中(source + 4 個 test 檔)     137488  ← 已越過 131072
    ==================================  ==========

    也就是說連「< MAX_ARG_STRLEN」這條硬上限在髒樹上都會紅,它量的是**工作樹**而不是 source。
    故改量唯一真正被 S2E.2a 的 registry append 推大的 tracked 檔:
    ``.codex/agent_registry_v1.json``(S2E.2a 前 96035 → 後 96675,+640 bytes),與工作樹髒度
    完全無關、逐位元組可重現。

    代理關係:乾淨樹上 artifact ≈ registry + ~18 KiB(115030 vs 96675)⇒ 釘住 registry ≤ 104 KiB
    等價於在乾淨樹上把 artifact 壓在 ~122 KiB 以下,仍在 ``MAX_ARG_STRLEN``(128 KiB = 131072)
    之內。canonical 慣例本來就是以 ``@file`` 傳 context artifact 而非塞進單一 argv 元素。
    """

    registry_bytes = len((ROOT / ".codex/agent_registry_v1.json").read_bytes())
    assert registry_bytes < MAX_ARG_STRLEN, registry_bytes
    # registry 自身留 ≥ 24 KiB 餘裕:任何一次把它推到 104 KiB 以上的成長都必須被重新評估。
    assert MAX_ARG_STRLEN - registry_bytes > 24 * 1024, registry_bytes


# 這支硬邊界釘量的是 **source**(乾淨工作樹)而不是當下的編輯狀態,故必須有一道「樹必須乾淨」的
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


def test_compiled_context_artifact_stays_under_the_execve_cap():
    """compiled artifact 的**硬邊界**釘(``MAX_ARG_STRLEN``;不是可重現的餘裕釘)。

    ``compile_context`` 會把當下工作樹的 diff / inventory 納入 ⇒ 量到的 bytes 依樹狀態而變。
    本次修復期間同一支測試實測 115030 → 124107 → 137488(最後一個已越過 131072),也就是說在
    **髒樹**上它量的是工作樹而不是 source,會誤紅。處置**不是**刪掉它,而是加一道前置:

    * 工作樹不乾淨 ⇒ ``pytest.skip`` 並把髒度逐字寫進 skip 理由(fail loud,不靜默通過);
    * 工作樹乾淨 ⇒ 真的量,且對 E2 實測過的四個角色**逐一**釘住 ``< MAX_ARG_STRLEN``。

    乾淨 HEAD ``50a224af4`` 上的實測(E1 與 E2 兩台各自獨立跑出同一組數字):
    E1 115468 / E2 115460 / OPS 113033 / PM 95905,registry 檔身 96675 —— 全部 < 131072。
    canonical 慣例本來就是以 ``@file`` 傳 context artifact 而非塞進單一 argv 元素。
    """

    dirt = _worktree_dirt()
    if dirt is not None:
        pytest.skip(
            "the execve hard-cap measurement only means anything on a clean worktree "
            f"(compile_context ingests the working-tree diff): {dirt}"
        )

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
    for role in _EXECVE_CAP_MEASURED_ROLES:
        artifact = materialize_context_artifact(
            compile_context(role, routed["task_facts"], root=ROOT)
        )
        measured[role] = len(
            json.dumps(artifact, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
    assert max(measured.values()) < MAX_ARG_STRLEN, {
        "measured": measured, "cap": MAX_ARG_STRLEN, "tree_state": baseline,
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
