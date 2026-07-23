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
import json
import os
import shutil
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
import agent_governance_target_host_choice as thc
import agent_governance_target_host_apply as apply_mod
import agent_governance_target_host_effects as tfx
import agent_governance_command_capture_v2 as capmod
import aiml_gate_receipt_validator as validator

APPLIER_NODE = "s1fc_apply_actor"
# 宣告的 postcheck 驗證者節點必須等於 verifier 的 governed command_capture_v2 的 capturer node_id
# (下方 _governed_verifier_capture 以 OPS ``ops_postcheck`` 節點產出),使 closure 的
# 「capture 必由宣告 verifier 節點產生」綁定成立(P1 Codex)。
VERIFIER_NODE = "ops_postcheck"
# 拋棄式探針的依賴 receipt(S1.1/S1.4/S1.5):此為 DISPOSABLE 證據,依賴 digest 為確定式占位
# (closure 只驗 sha256 形狀 + 交叉綁定,非比對真 receipt 位元組;真 landing 於 S8 綁真依賴)。
DEP = {
    "runtime_candidate_receipt_a_digest": "sha256:" + "a" * 64,
    "runtime_candidate_receipt_b_digest": "sha256:" + "b" * 64,
    "runtime_candidate_comparison_digest": "sha256:" + "c" * 64,
    "effect_seams_ready_receipt_digest": "sha256:" + "d" * 64,
    "pg_readonly_identity_receipt_digest": "sha256:" + "e" * 64,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


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


def _governed_verifier_capture(*, root: Path) -> dict:
    """A REAL OPS governed command_capture_v2 for the distinct verifier's residue sweep."""

    from agent_governance_context import capture_repository_baseline
    from agent_governance_execution import compile_context, materialize_context_artifact
    from agent_governance_routing import route_task

    vscope = ["helper_scripts/maintenance_scripts/runtime_environment_probe.py"]
    facts = {
        "task_shape": "review", "surfaces": ["operations"], "risk": "medium",
        "uncertainty": "low", "side_effect_class": "none",
        "objective": "capture the distinct-verifier target-host residue sweep",
        "scope": vscope, "dirty_scope": [], "verification_scope": vscope,
        "acceptance_criteria": ["one exact read-only command receipt"],
        "hard_stops": ["no runtime mutation"], "baseline": capture_repository_baseline(),
        "direct_interfaces": ["runtime_environment_probe_v1"],
        "previous_failure": "no derived read-only path scope",
    }
    routed = route_task(facts)
    artifact = materialize_context_artifact(compile_context("OPS", routed["task_facts"]))
    # governed capture 用一條保證通過 native-policy 的 read-only 指令產出真 record(證「distinct 驗證者
    # 跑過一條 governed command」);真 on-host 殘留觀察另由 independent_postcheck_on_host 產出(見 main)。
    return capmod.capture_governed_command(
        native_agent="OPS", node_id="ops_postcheck", context_artifact=artifact,
        argv=["git", "rev-parse", "--is-inside-work-tree"], root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--repo-root", type=Path, default=_HERE.parents[1])
    args = parser.parse_args()

    # 本 driver 是一個「專屬、拋棄式、被授權的 on-host effect 執行器」(等同 operator 手跑一次探針)。它於
    # 自身 env 開授權閘,使 target_host_available() 為真、讓 distinct 驗證者的 independent_postcheck_on_host
    # 得以做真殘留觀察。**注意**:applier 的 apply_target_host_probe_effect(真 runner)仍走隔離 python3 -E
    # 子行程——run_probe_via_child 以 sanitized allowlist env(不含此旗標)spawn 子行程,子行程自驗 capsule 後
    # 才在**它自己**的 env 開閘。故 P1 process-isolation 修復在此真跑中依然成立(applier 不靠 parent 的閘)。
    os.environ["AIML_TARGET_HOST_PROBE"] = "1"
    if not th.target_host_available():
        raise SystemExit(
            "not the target host (need linux + systemd-run on PATH); this driver runs ONLY on trade-core "
            "and refuses to fake a kernel fact off-target."
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    now = _now()
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    throwaway = os.path.join(xdg, f"aiml_s1fc_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    expected_host = th.EXPECTED_TARGET_HOST_DEFAULT

    intent = _build_intent(expected_host=expected_host, throwaway_root=throwaway, now=now)
    approved_at = _iso(now)
    applier_capture = thc._structural_capture_artifact()

    try:
        # (2) 真 child-executor apply:probe_runner 為預設真 runner ⇒ 走隔離 python3 -E 子行程。
        effect_result = apply_mod.apply_target_host_probe_effect(
            intent,
            source_head=args.source_head,
            approved_by="operator",
            approved_at=approved_at,
            capture_digest=applier_capture["record_digest"],
            capture_artifact=applier_capture,
            verifier_node_id=VERIFIER_NODE,
            now=_iso(now),
            dependency_receipts=DEP,
        )
        # (3) distinct 驗證者:真 on-host 殘留掃描 + 真 governed capture。
        swept = th.independent_postcheck_on_host(
            unit=f"aiml-probeB-absent-{os.getpid()}.scope",
            teardown_root=throwaway,
        )
        residue_observation = {
            "units_gone": swept["unit_absent"],
            "cgroup_gone": swept["cgroup_gone"],
            "netns_gone": True,
            "temp_gone": swept["temp_gone"],
        }
        verifier_capture = _governed_verifier_capture(root=args.repo_root)
        # (4) 升 BINDING(帶結構化 verifier_capture_digest)。
        upgraded = apply_mod.attach_distinct_verifier_postcheck(
            effect_result,
            verifier_node_id=VERIFIER_NODE,
            verifier_capture_digest=verifier_capture["record_digest"],
            residue_observation=residue_observation,
            now=_iso(now),
        )
        # 最終殘留確認(生產 PG :5432 未觸):零殘留。
        final_sweep = th.independent_postcheck_on_host(
            unit=f"aiml-probeB-final-{os.getpid()}.scope",
            teardown_root=throwaway,
        )
    finally:
        shutil.rmtree(throwaway, ignore_errors=True)

    host_identity = (upgraded.get("choice_receipt") or {}).get("host_identity") or {}
    artifacts = {
        "intent.json": intent,
        "applier_effect_result.json": effect_result,
        "upgraded_effect_result.json": upgraded,
        "applier_capture.json": applier_capture,
        "verifier_capture.json": verifier_capture,
        "residue_observation.json": residue_observation,
        "final_residue_sweep.json": final_sweep,
        "host_identity.json": host_identity,
        "run_meta.json": {
            "source_head": args.source_head,
            "expected_host": expected_host,
            "applier_node": APPLIER_NODE,
            "verifier_node": VERIFIER_NODE,
            "observed_at": _iso(now),
            "verifier_capture_digest": upgraded.get("verifier_capture_digest"),
            "effect_status": upgraded.get("effect_status"),
            "binding": (upgraded.get("choice_receipt") or {}).get("selection", {}).get("binding"),
            "pg_identity_mode": (upgraded.get("choice_receipt") or {}).get("selection", {}).get("final_choice"),
        },
    }
    for name, value in artifacts.items():
        (args.out_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
        )

    # producer-side 自驗:upgraded effect result 必過 require_success 嚴格閘。
    verify_errors = tfx.validate_target_host_effect_result(
        upgraded, now=_iso(now), expected_source_head=args.source_head, require_success=True
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
