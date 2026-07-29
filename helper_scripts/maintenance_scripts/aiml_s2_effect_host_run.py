"""S2E.2a:S2 effect 受信主機 runner 的 CLI(``--out-dir`` canonical artifact 契約)。

三個 mode,全部 fail-closed:

``probe``
    只導出**主機事實**(``derive_host_target_class`` + kernel ABI 投影),可選再以進程分離的唯讀
    observer 取一份觀測。零 driver、零 adapter 呼叫、零主機變更。任何主機都能跑。

``admit``
    對一份 typed intent(+ 可選的 operator permit/signature)跑完整的 §E.2 准入矩陣並落盤裁決。
    **永不**構造 driver、**永不**呼叫 adapter。這是 operator 在真正動手前的 dry-run。

``apply``
    真正的施作 lane。先跑 ``admit`` 的同一道矩陣;通過後仍需要一個**主機能力供應者**
    (真 PG admin handle / 真 systemd executor)——那是 S2.0/S2.1 EFFECT session 在目標主機上供裝
    的東西,**刻意不存在於 source**。故本 mode 今日一律以 typed
    ``HOST_CAPABILITY_SUPPLIER_ABSENT`` 非零退出,零主機接觸。這與 adapter 的 ``driver=None`` 是
    同一種誠實:閘可達,但沒有 driver 可跑。

**誠實界線。**

* 本 CLI 的拒絕是 **L1 主機安全層**:它只決定「今天要不要碰這台主機」。證據完整性由 adapter 的
  L2 閘(permit 驗簽 / trusted-host attestation)與 closure 的 L3 閘負責,本波對兩者一行不動。
* ``--source-head`` 只做 40-hex 形檢與「等於 intent.source_head」的比對,**不**對 git worktree
  重新驗證(S1.6B 的 runner 以 ``git rev-parse``/``git status`` 做那件事,但 S2 host kernel 的
  session 是封閉的主機事實 session、刻意沒有 git 能力;加一個 git session 會讓 kernel 往通用
  exec service 漂移)。真正的 head 綁定在 L3:``agent_governance_s2_effect_binding
  .validate_s2_effect_evidence`` 已把 receipt 的 ``source_head`` 綁到 closure baseline head。
  run_meta 會誠實記錄 ``source_head_verification = "deferred_to_closure_baseline_binding"``。
* 任何 rehearsal / probe 的綠都**不是** closure PASS,也**不是** EFFECT 進展:S2E.1 已把 S2.0 與
  S2.1 標成 closure-PASS-blocked,PR#154 的 effect-DAG 傳遞阻塞使九步全不可 PASS;九 authority
  恆 false,runtime 恆 inactive。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
for _candidate in (_HERE, _REPO_ROOT / "program_code" / "ml_training"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_0_host_runner as s2_0_runner  # noqa: E402
import agent_governance_s2_1_host_runner as s2_1_runner  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402
import agent_governance_s2_host_observer as host_observer  # noqa: E402


SESSIONS = ("s2_0", "s2_1")
MODES = ("probe", "admit", "apply")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ADMISSION_REFUSED = 3
EXIT_HOST_CAPABILITY_ABSENT = 4
EXIT_OBSERVATION_FAILED = 5

HEAD_LENGTH = 40
_HEX = set("0123456789abcdef")


def _canonical_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _is_head(value: Any) -> bool:
    text = str(value or "")
    return len(text) == HEAD_LENGTH and set(text) <= _HEX


def _load_json(path: Path | None) -> Any:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_operator_authorization(
    *, session: str, intent: Any, authorization: Any, signature: bytes | None,
    source_head: str, now: str,
) -> dict[str, Any]:
    """委派各 adapter **既有**的 operator SSHSIG validator;本 CLI 絕不自己驗簽。"""

    if authorization is None or signature is None:
        return {"verified": False, "errors": ["no operator authorization / signature was supplied"]}
    try:
        if session == "s2_0":
            import agent_governance_pg_observer_bootstrap as adapter
        else:
            import agent_governance_alr_quiesce_fence as adapter
        errors = adapter.validate_operator_authorization(
            authorization, signature, intent=intent, source_head=source_head, now=now,
        )
    except Exception as error:  # noqa: BLE001 - 驗簽失敗一律 fail-closed,絕不冒充已驗證
        return {"verified": False, "errors": [f"operator authorization could not be verified: {error}"]}
    return {"verified": not errors, "errors": list(errors)}


def _admission(args, intent: Any, authorization: Any, signature: bytes | None) -> dict[str, Any]:
    target_view = host_kernel.derive_host_target_class()
    now = host_kernel.trusted_host_time()
    verification = _verify_operator_authorization(
        session=args.session, intent=intent, authorization=authorization, signature=signature,
        source_head=args.source_head, now=now,
    )
    intent_digest = intent.get("self_digest") if isinstance(intent, dict) else None
    errors = host_kernel.host_target_admission_errors(
        target_view,
        allow_production=bool(args.allow_production),
        production_confirm=args.production_confirm,
        intent_digest=intent_digest,
        operator_authorization_verified=bool(verification["verified"]),
    )
    if isinstance(intent, dict) and intent.get("source_head") != args.source_head:
        errors.append("--source-head must equal the intent source_head")
    return {
        "session": args.session,
        "observed_at": now,
        "target_class_view": target_view,
        "intent_digest": intent_digest,
        "operator_authorization": verification,
        "allow_production": bool(args.allow_production),
        "production_confirm_matches": (
            isinstance(intent_digest, str) and args.production_confirm == intent_digest
        ),
        "admitted": not errors,
        "refusal_reasons": errors,
        # L1 只是主機安全層;L2/L3 才是證據完整性層(本波未動)。
        "layer": "L1_host_safety_only",
        "closure_pass_blocked": True,
    }


def _observation(args) -> dict[str, Any]:
    kernel = host_kernel.HostExecutionKernel(
        session=host_kernel.SESSION_S2_HOST_OBSERVER_CHILD
    )
    request = {
        "schema_version": host_observer.REQUEST_SCHEMA_VERSION,
        "faces": [host_observer.FACE_FILE_IDENTITY, host_observer.FACE_PROCESS_IDENTITY],
        "path_keys": sorted(host_observer.CANONICAL_OBSERVABLE_PATHS),
    }
    if args.session == "s2_1":
        request["faces"] = [
            host_observer.FACE_UNIT_STATE, host_observer.FACE_FILE_IDENTITY,
            host_observer.FACE_PROCESS_IDENTITY,
        ]
    raw = kernel.run_observer_child(request)
    observation = json.loads(raw)
    errors = host_observer.validate_observation(observation)
    if errors:
        raise host_observer.S2HostObserverError(
            "the process-separated observation is invalid: " + "; ".join(errors[:3])
        )
    return observation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S2 effect trusted-host runner")
    parser.add_argument("--session", required=True, choices=SESSIONS)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--intent-file", type=Path)
    parser.add_argument("--operator-permit", type=Path)
    parser.add_argument("--operator-signature", type=Path)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--production-confirm", default=None)
    parser.add_argument("--observe", action="store_true")
    args = parser.parse_args(argv)

    if not _is_head(args.source_head):
        parser.error("--source-head must be exact lowercase 40-hex")
    if args.mode in ("admit", "apply") and args.intent_file is None:
        parser.error(f"--mode {args.mode} requires --intent-file")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "session": args.session,
        "mode": args.mode,
        "source_head": args.source_head,
        "source_head_verification": "deferred_to_closure_baseline_binding",
        "out_dir": str(args.out_dir),
        "status": "INCOMPLETE",
        "exit_code": EXIT_USAGE,
        "closure_pass_blocked": True,
        "production_effect_performed": False,
        "nine_authorities_false": True,
    }
    exit_code = EXIT_USAGE
    try:
        target_view = host_kernel.derive_host_target_class()
        _canonical_write(args.out_dir / "target_class_view.json", target_view)
        _canonical_write(args.out_dir / "kernel_abi.json", host_kernel.kernel_abi_projection())
        summary["target_class"] = target_view["target_class"]

        if args.mode == "probe":
            exit_code = EXIT_OK
            summary["status"] = "PROBED"
            if args.observe:
                try:
                    observation = _observation(args)
                except (host_kernel.S2HostKernelError, host_observer.S2HostObserverError,
                        ValueError) as error:
                    summary["status"] = "OBSERVATION_FAILED"
                    summary["observation_error"] = str(error)
                    exit_code = EXIT_OBSERVATION_FAILED
                else:
                    _canonical_write(args.out_dir / "observation.json", observation)
                    summary["observation_digest"] = observation["self_digest"]
            summary["exit_code"] = exit_code
            return exit_code

        intent = _load_json(args.intent_file)
        authorization = _load_json(args.operator_permit)
        signature = (
            args.operator_signature.read_bytes() if args.operator_signature is not None else None
        )
        admission = _admission(args, intent, authorization, signature)
        _canonical_write(args.out_dir / "admission.json", admission)
        summary["admitted"] = admission["admitted"]
        summary["refusal_reasons"] = admission["refusal_reasons"]

        if not admission["admitted"]:
            summary["status"] = "ADMISSION_REFUSED"
            exit_code = EXIT_ADMISSION_REFUSED
            summary["exit_code"] = exit_code
            return exit_code
        if args.mode == "admit":
            summary["status"] = "ADMITTED_DRY_RUN"
            exit_code = EXIT_OK
            summary["exit_code"] = exit_code
            return exit_code

        # mode == apply:閘可達,但主機能力供應者刻意不存在於 source(鏡 adapter 的 driver=None)。
        summary["status"] = "HOST_CAPABILITY_SUPPLIER_ABSENT"
        summary["reason"] = (
            "the S2 host capability supplier (a real local-socket PG admin handle for S2.0 / a real "
            "system-level systemd executor for S2.1) is provisioned by the S2.0/S2.1 EFFECT session "
            "on the target host and is deliberately absent from source; this runner refuses to "
            "fabricate one and makes zero host contact"
        )
        summary["runner_entrypoints"] = {
            "s2_0": f"{s2_0_runner.__name__}.run_observer_bootstrap_on_host",
            "s2_1": f"{s2_1_runner.__name__}.run_quiesce_fence_on_host",
        }
        exit_code = EXIT_HOST_CAPABILITY_ABSENT
        summary["exit_code"] = exit_code
        return exit_code
    finally:
        # 頂層 finally:不論走哪條路,``--out-dir`` 的 canonical artifact 契約都成立。
        summary["exit_code"] = exit_code
        _canonical_write(args.out_dir / "run_summary.json", summary)
        sys.stdout.write(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
