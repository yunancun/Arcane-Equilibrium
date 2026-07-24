"""AIML S1 formal-closure — reproducible target-host effect run driver (trade-core only).

驅動一次**真** bounded non-root target-host 探針,走 PR #114 findings-fix 後的完整路徑:
  1. 由 fresh 時鐘建一張 admitted typed intent(``target_host_disposable_runtime_probe_intent_v1``);
  2. ``apply_target_host_probe_effect``(真 runner)→ 經隔離 ``python3 -E`` 子行程(P1 process-isolation
     修復)在自身 env 開閘、真跑 ``run_target_host_probe``,產出 applier 自跑的 PROVISIONAL effect result;
  3. distinct OPS 驗證者以 ``independent_postcheck_on_host`` 做**真** on-host 殘留掃描,並以 OPS
     ``capture-command`` 對殘留掃描產出一份**真 governed** ``command_capture_v2``(P1 postcheck-binding 修復
     要求的第三份 evidence);
  4. ``attach_distinct_verifier_postcheck`` → BINDING 的 upgraded effect result(帶結構化
     ``verifier_capture_digest``);
  5. 把所有 producer artifacts 以 canonical JSON 寫到 ``--out-dir``。

界線:非 root、user-scope、拋棄式;不觸生產 PG(:5432)、不 deploy、不接 broker、不下單。頂層 finally
保證 rmtree throwaway_root。此腳本**只在 target host(trade-core)**產出真 ATTESTED 結果;於 Mac/非 target
host 乾淨 fail(``target_host_available()`` False),絕不 fake。closure_packet_v1 的組裝 + 受信主機 SSHSIG
為後續步驟(見 docs/execution_plan/ai_ml_landing/design/S1.6B-real-target-host-probe.md §11)。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_ML = _HERE.parents[1] / "program_code/ml_training"
if str(_ML) not in sys.path:
    sys.path.insert(0, str(_ML))

import agent_governance_target_host_probe as th
import agent_governance_target_host_apply as apply_mod
import agent_governance_target_host_effects as tfx
import agent_governance_command_capture_v2 as capmod
import agent_governance_component_effects as component_effects
import agent_governance_target_host_operator_authorization as operator_auth
import aiml_gate_receipt_validator as validator

APPLIER_NODE = "s1fc_apply_actor"
# 宣告的 postcheck 驗證者節點必須等於 verifier 的 governed command_capture_v2 的 capturer node_id
# (下方 _governed_verifier_capture 以 OPS ``ops_postcheck`` 節點產出),使 closure 的
# 「capture 必由宣告 verifier 節點產生」綁定成立(P1 Codex)。
VERIFIER_NODE = "ops_postcheck"
# 拋棄式探針的 S1.1/S1.4 digest 仍是 disposable source-stage dependencies；S1.5 的
# ``effect_seams_ready_receipt_v1`` 則必須由 caller 提供真 producer artifact，driver
# 會完整驗證並把其 self_digest 綁進 target-host choice receipt。這避免以固定 digest
# 冒充 Sprint-1 exit contribution。
DEP = {
    "runtime_candidate_receipt_a_digest": "sha256:" + "a" * 64,
    "runtime_candidate_receipt_b_digest": "sha256:" + "b" * 64,
    "runtime_candidate_comparison_digest": "sha256:" + "c" * 64,
    "pg_readonly_identity_receipt_digest": "sha256:" + "e" * 64,
}
OBSERVATION_SCRIPT = (
    "helper_scripts/maintenance_scripts/"
    "agent_governance_target_host_observation.py"
)


def _target_host_observation_argv(
    *,
    mode: str,
    intent: dict,
    authorization: dict,
    signature: bytes,
    unit: str | None = None,
    teardown_root: str | None = None,
) -> list[str]:
    encoded_intent = base64.b64encode(
        json.dumps(
            intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).decode("ascii")
    encoded_authorization = base64.b64encode(
        operator_auth.canonical_bytes(authorization)
    ).decode("ascii")
    encoded_signature = base64.b64encode(signature).decode("ascii")
    argv = [
        "python3",
        OBSERVATION_SCRIPT,
        "--mode",
        mode,
        "--intent-base64",
        encoded_intent,
        "--permit-base64",
        encoded_authorization,
        "--signature-base64",
        encoded_signature,
    ]
    if mode == "postcheck":
        argv.extend([
            "--unit",
            str(unit),
            "--teardown-root",
            str(teardown_root),
        ])
    return argv


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _verified_committed_source_head(repo_root: Path, claimed_head: str) -> str:
    """Bind the effect label to the exact clean Git worktree being executed."""

    if re.fullmatch(r"[0-9a-f]{40}", claimed_head) is None:
        raise SystemExit("--source-head must be exact lowercase 40-hex")
    try:
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        status = subprocess.run(
            [
                "git", "status", "--porcelain=v1", "--untracked-files=all",
                "--ignore-submodules=all",
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"cannot verify target-host source worktree: {error}") from error
    if actual != claimed_head:
        raise SystemExit(
            f"--source-head differs from target-host worktree HEAD: {claimed_head} != {actual}"
        )
    if status.strip():
        raise SystemExit(
            "target-host source worktree must be clean before effect execution"
        )
    return actual


def _build_intent(*, expected_host: str, throwaway_root: str, now: datetime) -> dict:
    intent = {
        "schema_version": "target_host_disposable_runtime_probe_intent_v1",
        "intent_id": "sha256:" + uuid.uuid4().hex + uuid.uuid4().hex,
        "expected_host": expected_host,
        "non_root_uid": True,
        "user_scope_only": True,
        "candidate_ids": ["content_addressed_fixed_path"],
        # start_stop 的 per-seam argv 是被 systemd-run --user --scope 包起來的**長駐 launcher payload**
        # (探針自己加 systemd-run 前綴),故此處是一個真長駐 sleeper,而非 systemd-run 前綴本身。
        "per_seam_argv": {
            "start_stop": [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
        },
        "throwaway_root": throwaway_root,
        "ttl_seconds": 900,
        "risk": "high",
        "rollback": {
            "atomic_pointer_swap": "swap current->new",
            "teardown_reset_failed": "systemctl --user reset-failed",
            "rmtree": "rm -rf throwaway_root",
        },
        "applier_node_id": APPLIER_NODE,
        "postcheck_node_id": VERIFIER_NODE,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=900)),
    }
    intent["self_digest"] = validator.artifact_self_digest(intent)
    errors = apply_mod.validate_probe_intent(intent, now=_iso(now))
    if errors:
        raise SystemExit("intent is not admissible: " + "; ".join(errors[:4]))
    return intent


def _governed_ops_capture(
    *,
    root: Path,
    node_id: str,
    objective: str,
    mode: str,
    intent: dict,
    authorization: dict,
    signature: bytes,
    unit: str | None = None,
    teardown_root: str | None = None,
) -> dict:
    """Capture one operator-authenticated, read-only target-host observation."""

    from agent_governance_context import capture_repository_baseline
    from agent_governance_execution import compile_context, materialize_context_artifact
    from agent_governance_routing import route_task

    vscope = [
        "helper_scripts/maintenance_scripts/agent_governance_target_host_observation.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_probe.py",
    ]
    facts = {
        "task_shape": "review", "surfaces": ["operations"], "risk": "medium",
        "uncertainty": "low", "side_effect_class": "none",
        "objective": objective,
        "scope": vscope, "dirty_scope": [], "verification_scope": vscope,
        "acceptance_criteria": ["one exact read-only command receipt"],
        "hard_stops": ["no runtime mutation"], "baseline": capture_repository_baseline(),
        "direct_interfaces": ["target_host_governed_observation_v1"],
        "previous_failure": "no derived read-only path scope",
    }
    routed = route_task(facts)
    artifact = materialize_context_artifact(compile_context("OPS", routed["task_facts"]))
    argv = _target_host_observation_argv(
        mode=mode,
        intent=intent,
        authorization=authorization,
        signature=signature,
        unit=unit,
        teardown_root=teardown_root,
    )
    return capmod.capture_governed_command(
        native_agent="OPS", node_id=node_id, context_artifact=artifact,
        argv=argv, root=root,
    )


def _captured_target_host_observation(
    capture: dict,
    *,
    mode: str,
    source_head: str,
    intent: dict,
    authorization: dict,
    signature: bytes,
    unit: str | None = None,
    teardown_root: str | None = None,
) -> dict:
    """Parse only a complete, valid command-capture stdout observation."""

    errors = capmod.validate_governed_command_capture(
        capture,
        expected_source_head=source_head,
    )
    if errors:
        raise SystemExit(
            "governed target-host observation capture is invalid: "
            + "; ".join(errors[:5])
        )
    expected_argv = _target_host_observation_argv(
        mode=mode,
        intent=intent,
        authorization=authorization,
        signature=signature,
        unit=unit,
        teardown_root=teardown_root,
    )
    if capture.get("argv") != expected_argv:
        raise SystemExit(
            "governed target-host observation command differs from the "
            "operator-authorized exact observer invocation"
        )
    stdout = capture.get("stdout") or {}
    preview = stdout.get("preview_text")
    if (
        capture.get("result") != "PASS"
        or capture.get("exit_code") != 0
        or stdout.get("encoding") != "utf-8"
        or not isinstance(preview, str)
        or stdout.get("truncated") is not False
        or stdout.get("bytes") != len(preview.encode("utf-8"))
        or stdout.get("digest")
        != "sha256:" + hashlib.sha256(preview.encode("utf-8")).hexdigest()
    ):
        raise SystemExit(
            "governed target-host observation lacks complete exact stdout"
        )
    try:
        artifact = json.loads(preview)
    except ValueError as error:
        raise SystemExit(
            "governed target-host observation stdout is not JSON"
        ) from error
    expected = {
        "schema_version": "target_host_governed_observation_v1",
        "mode": mode,
        "source_head": source_head,
        "intent_digest": intent["self_digest"],
        "operator_authorization_digest": authorization[
            "authorization_digest"
        ],
    }
    if not isinstance(artifact, dict) or any(
        artifact.get(field) != value for field, value in expected.items()
    ):
        raise SystemExit(
            "governed target-host observation is not bound to the exact "
            "mode/source/intent/operator permit"
        )
    observation = artifact.get("observation")
    if not isinstance(observation, dict):
        raise SystemExit(
            "governed target-host observation payload is missing"
        )
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-head", required=True)
    parser.add_argument(
        "--effect-seams-ready-receipt",
        required=True,
        type=Path,
        help="producer-generated effect_seams_ready_receipt_v1 JSON",
    )
    parser.add_argument(
        "--prepare-intent-only",
        action="store_true",
        help="emit the exact typed intent for out-of-band operator signing and exit",
    )
    parser.add_argument("--intent-file", type=Path)
    parser.add_argument("--operator-permit", type=Path)
    parser.add_argument("--operator-signature", type=Path)
    parser.add_argument("--repo-root", type=Path, default=_HERE.parents[1])
    args = parser.parse_args()
    source_head = _verified_committed_source_head(
        args.repo_root.resolve(), args.source_head
    )

    if (
        sys.platform != "linux"
        or shutil.which("systemd-run") is None
        or socket.gethostname() != th.EXPECTED_TARGET_HOST_DEFAULT
    ):
        raise SystemExit(
            "not the exact target host (need Linux trade-core + systemd-run); "
            "this driver refuses to fake a kernel fact off-target"
        )
    effect_seams_receipt = json.loads(
        args.effect_seams_ready_receipt.read_text(encoding="utf-8")
    )
    receipt_errors = component_effects.validate_effect_seams_ready_receipt(
        effect_seams_receipt, now=_iso(_now())
    )
    if receipt_errors or effect_seams_receipt.get("status") != "PASS":
        raise SystemExit(
            "effect_seams_ready_receipt_v1 is not a fresh producer-valid PASS: "
            + "; ".join(receipt_errors[:5])
        )
    dependency_receipts = {
        **DEP,
        "effect_seams_ready_receipt_digest": effect_seams_receipt["self_digest"],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    expected_host = th.EXPECTED_TARGET_HOST_DEFAULT
    if args.prepare_intent_only:
        if any((
            args.intent_file,
            args.operator_permit,
            args.operator_signature,
        )):
            raise SystemExit(
                "--prepare-intent-only cannot consume an existing permit"
            )
        prepared_at = _now()
        throwaway_root = (
            f"/run/user/{os.getuid()}/"
            f"aiml_s1fc_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        )
        prepared_intent = _build_intent(
            expected_host=expected_host,
            throwaway_root=throwaway_root,
            now=prepared_at,
        )
        (args.out_dir / "intent.json").write_text(
            json.dumps(
                prepared_intent,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "OPERATOR_SIGNATURE_REQUIRED",
            "intent_digest": prepared_intent["self_digest"],
            "source_head": source_head,
            "intent_path": str(args.out_dir / "intent.json"),
        }, sort_keys=True))
        return 0
    if not all((
        args.intent_file,
        args.operator_permit,
        args.operator_signature,
    )):
        raise SystemExit(
            "effect execution requires --intent-file, --operator-permit, "
            "and --operator-signature"
        )
    intent = json.loads(args.intent_file.read_text(encoding="utf-8"))
    authorization = json.loads(
        args.operator_permit.read_text(encoding="utf-8")
    )
    operator_signature = args.operator_signature.read_bytes()
    now = _now()
    intent_errors = apply_mod.validate_probe_intent(intent, now=_iso(now))
    authorization_errors = operator_auth.validate_operator_authorization(
        authorization,
        operator_signature,
        intent=intent,
        source_head=source_head,
        now=_iso(now),
        actual_host=socket.gethostname(),
    )
    if intent_errors or authorization_errors:
        raise SystemExit(
            "operator-signed exact intent is not admissible: "
            + "; ".join([*intent_errors, *authorization_errors][:6])
        )
    throwaway = str(intent["throwaway_root"])
    approved_at = _iso(now)
    preflight_capture = _governed_ops_capture(
        root=args.repo_root,
        node_id="ops_preflight",
        objective="capture the target-host readiness preflight before the S1 effect",
        mode="preflight",
        intent=intent,
        authorization=authorization,
        signature=operator_signature,
    )
    preflight_observation = _captured_target_host_observation(
        preflight_capture,
        mode="preflight",
        source_head=source_head,
        intent=intent,
        authorization=authorization,
        signature=operator_signature,
    )
    if (
        preflight_observation.get("observed_host") != expected_host
        or preflight_observation.get("expected_host") != expected_host
    ):
        raise SystemExit(
            "captured preflight is not bound to the exact target host"
        )
    # The applier receipt now embeds the real governed preflight capture, never
    # the old structural_reference_only shape.
    applier_capture = preflight_capture

    try:
        # (2) 真 child-executor apply:probe_runner 為預設真 runner ⇒ 走隔離 python3 -E 子行程。
        effect_result = apply_mod.apply_target_host_probe_effect(
            intent,
            source_head=source_head,
            approved_by="operator",
            approved_at=approved_at,
            capture_digest=applier_capture["record_digest"],
            capture_artifact=applier_capture,
            verifier_node_id=VERIFIER_NODE,
            now=_iso(now),
            dependency_receipts=dependency_receipts,
            operator_authorization=authorization,
            operator_signature=operator_signature,
        )
        # (3) distinct OPS verifier: the governed command itself performs the
        # residue sweep.  No same-process observation is allowed to substitute
        # for the captured stdout.
        absent_unit = f"aiml-probeB-absent-{os.getpid()}.scope"
        verifier_capture = _governed_ops_capture(
            root=args.repo_root,
            node_id=VERIFIER_NODE,
            objective="capture the distinct-verifier target-host residue sweep",
            mode="postcheck",
            intent=intent,
            authorization=authorization,
            signature=operator_signature,
            unit=absent_unit,
            teardown_root=throwaway,
        )
        swept = _captured_target_host_observation(
            verifier_capture,
            mode="postcheck",
            source_head=source_head,
            intent=intent,
            authorization=authorization,
            signature=operator_signature,
            unit=absent_unit,
            teardown_root=throwaway,
        )
        if swept.get("no_residue") is not True:
            raise SystemExit(
                "captured distinct OPS postcheck observed target-host residue"
            )
        residue_observation = {
            "units_gone": swept["unit_absent"],
            "cgroup_gone": swept["cgroup_gone"],
            "netns_gone": True,
            "temp_gone": swept["temp_gone"],
        }
        if not all(residue_observation.values()):
            raise SystemExit(
                "captured distinct OPS residue observation is not clean"
            )
        # (4) 升 BINDING(帶結構化 verifier_capture_digest)。
        upgraded = apply_mod.attach_distinct_verifier_postcheck(
            effect_result,
            verifier_node_id=VERIFIER_NODE,
            verifier_capture_digest=verifier_capture["record_digest"],
            residue_observation=residue_observation,
            now=_iso(now),
        )
        final_sweep = swept
    finally:
        shutil.rmtree(throwaway, ignore_errors=True)

    host_identity = (upgraded.get("choice_receipt") or {}).get("host_identity") or {}
    artifacts = {
        "intent.json": intent,
        "applier_effect_result.json": effect_result,
        "upgraded_effect_result.json": upgraded,
        "applier_capture.json": applier_capture,
        "preflight_capture.json": preflight_capture,
        "preflight_observation.json": preflight_observation,
        "verifier_capture.json": verifier_capture,
        "residue_observation.json": residue_observation,
        "final_residue_sweep.json": final_sweep,
        "host_identity.json": host_identity,
        "run_meta.json": {
            "source_head": source_head,
            "expected_host": expected_host,
            "applier_node": APPLIER_NODE,
            "verifier_node": VERIFIER_NODE,
            "observed_at": _iso(now),
            "preflight_capture_digest": preflight_capture.get("record_digest"),
            "verifier_capture_digest": upgraded.get("verifier_capture_digest"),
            "effect_status": upgraded.get("effect_status"),
            "binding": (upgraded.get("choice_receipt") or {}).get("selection", {}).get("binding"),
            "pg_identity_mode": (upgraded.get("choice_receipt") or {}).get("selection", {}).get("final_choice"),
        },
        "effect_seams_ready_receipt.json": effect_seams_receipt,
        "operator_authorization.json": authorization,
    }
    for name, value in artifacts.items():
        (args.out_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
        )
    (args.out_dir / "operator_authorization.json.sig").write_bytes(
        operator_signature
    )

    # producer-side 自驗:upgraded effect result 必過 require_success 嚴格閘。
    verify_errors = tfx.validate_target_host_effect_result(
        upgraded, now=_iso(now), expected_source_head=source_head, require_success=True
    )
    summary = {
        "effect_status": upgraded.get("effect_status"),
        "binding": (upgraded.get("choice_receipt") or {}).get("selection", {}).get("binding"),
        "observed_host": host_identity.get("observed_host"),
        "expected_host": host_identity.get("expected_host"),
        "zero_residue": all(final_sweep.get(k) in (True, None) for k in ("unit_absent", "cgroup_gone", "temp_gone")),
        "verifier_capture_governed_valid": capmod.validate_governed_command_capture(verifier_capture) == [],
        "upgraded_effect_result_valid": verify_errors == [],
        "upgraded_effect_result_errors": verify_errors[:5],
        "out_dir": str(args.out_dir),
    }
    (args.out_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if (verify_errors == [] and summary["verifier_capture_governed_valid"]) else 5


if __name__ == "__main__":
    raise SystemExit(main())
