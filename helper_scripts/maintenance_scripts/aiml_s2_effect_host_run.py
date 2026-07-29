"""S2E.2a:S2 effect 受信主機 runner 的 CLI(``--out-dir`` canonical artifact 契約)。

五個 mode,全部 fail-closed;每個 session 只認得自己那組(:data:`SESSION_MODES`)——S2.0/S2.1
的輸入是 typed intent + operator SSHSIG,S2.4 的輸入是簽過的 install plan / lane id / 兩張已燒
permit,混用只會產生一份「看起來跑過了」的 artifact。

``probe``
    只導出**主機事實**(``derive_host_target_class`` + kernel ABI 投影),可選再以進程分離的唯讀
    observer 取一份觀測。零 driver、零 adapter 呼叫、零主機變更。任何主機都能跑,但 ``--observe``
    **也要過 L1**(``host_observation_admission_errors``):``production`` / ``unknown`` 需要一次
    顯式 ``--allow-production`` 承認,否則 observer 子行程根本不被 spawn。該閘刻意比 apply 面弱
    一級(不要 SSHSIG / 不要 ``--production-confirm``),理由寫在 kernel 的謂詞 docstring:觀測面
    的每條 argv 都在唯讀 allowlist 內、結構上不可能變更狀態,而觀測正是「拿到 permit 之前」要做
    的事。**同一道閘也下沉到 observer 的 ``main()``**(E2 RES-6):那個腳本是獨立進入點,「不經
    本 CLI 直接跑它」是完全合法的路徑,故承認隨 request 傳下去、child 自己再判一次 ——
    「否則子行程根本不被 spawn」只是**本 CLI 路徑上**的說法,不是那個進入點的全部保護。

``admit``
    對一份 typed intent(+ 可選的 operator permit/signature)跑完整的 §E.2 准入矩陣並落盤裁決。
    **永不**構造 driver、**永不**呼叫 adapter。這是 operator 在真正動手前的 dry-run。

``apply``
    真正的施作 lane。先跑 ``admit`` 的同一道矩陣;通過後仍需要一個**主機能力供應者**
    (真 PG admin handle / 真 systemd executor)——那是 S2.0/S2.1 EFFECT session 在目標主機上供裝
    的東西,**刻意不存在於 source**。故本 mode 今日一律以 typed
    ``HOST_CAPABILITY_SUPPLIER_ABSENT`` 非零退出,零主機接觸。這與 adapter 的 ``driver=None`` 是
    同一種誠實:閘可達,但沒有 driver 可跑。

``reconcile``(僅 ``--session s2_4``)
    §5.2 的「接受新 probe / PREPARE intent 之前先收斂任何非終端 journal」。要 ``--lane`` 與
    ``--lane-id``;lane id 一律經 journal 葉的導出函式重算,caller 字串永不 join 進 state root。

``compensate``(僅 ``--session s2_4``)
    §5.4 的啟動逆序補償。要簽過的 ``--plan-file``、五份 ``--component-intents-file``,以及
    **兩張** permit(``--apply-aggregate-permit`` / ``--pg-migration-permit``)——那次 APPLY 是
    atomically 消費兩張的,所以它的 undo 不可能只由其中一張授權。

    兩個 S2.4 mode 今日 driver 恆為 ``None``:S2.4 的 aggregate host driver 需要 systemd 觀測面
    與五支 row driver,兩者都不在 recovery core 的範圍內。故這條 CLI 跑得到的是「輸入站不站得
    住」與「主機面在不在」兩層——兩者都是真閘、都能真的紅,而且都不碰主機。退出碼另有
    :data:`EXIT_RECOVERY_REQUIRED`(8),與 4 刻意分開:4 是「還沒開始」,8 是「閘跑完了,結論
    是這台主機需要 operator 介入」。

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
* 壞輸入一律 typed fail-closed,且**落盤 artifact 的 ``exit_code`` 與 process 的真實退出碼恆
  一致**:不可讀 / 非 JSON 的 ``--intent-file`` / ``--operator-permit`` / ``--operator-signature``
  → ``INPUT_INVALID``(exit 6);任何未預期例外 → ``RUNNER_FAILED``(exit 7)+ stderr 明文,絕不讓一個裸
  traceback 把 process 退成 1、卻在 ``run_summary.json`` 寫另一個號碼。**唯一沒有 artifact 的
  路徑**是 ``--out-dir`` 自己建不起來(例如 ``--out-dir /dev/null/nope``):那時沒有任何地方可以
  落盤,故收成 typed usage(exit 2)+ stderr 明文(E2 RES-7;此前那條路是裸 traceback rc=1)。
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
import agent_governance_s2_4_host_recovery as s2_4_recovery  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402
import agent_governance_s2_host_observer as host_observer  # noqa: E402


SESSIONS = ("s2_0", "s2_1", "s2_4")
MODES = ("probe", "admit", "apply", "reconcile", "compensate")
# 每個 session 只認得自己的 mode。S2.0/S2.1 的 `admit`/`apply` 走各自 adapter 的 operator
# SSHSIG validator;S2.4 的兩個 mode 走的是 §5.2/§5.4 的啟動路徑,兩組輸入完全不同,
# 混用只會產生一份「看起來跑過了」的 artifact。
SESSION_MODES = {
    "s2_0": ("probe", "admit", "apply"),
    "s2_1": ("probe", "admit", "apply"),
    "s2_4": ("reconcile", "compensate"),
}

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ADMISSION_REFUSED = 3
EXIT_HOST_CAPABILITY_ABSENT = 4
EXIT_OBSERVATION_FAILED = 5
# 壞輸入(不可讀 / 非 JSON / 形不對的 intent·permit·signature)一律 typed fail-closed;絕不讓一個
# 未捕捉的 traceback 把 process 退成 1、卻在 artifact 裡寫另一個號碼(E2 P2 #8)。
EXIT_INPUT_INVALID = 6
EXIT_INTERNAL_ERROR = 7
# §5.2/§5.4 的 typed 非成功(RECOVERY_REQUIRED 家族)。它與 4 刻意不同:4 的意思是「閘可達但
# 主機能力供應者不在」,8 的意思是「閘跑完了,結論是這台主機需要 operator 介入」。把兩者收成
# 同一個號碼會讓自動化把「還沒開始」與「已經知道有殘留」當成同一件事。
EXIT_RECOVERY_REQUIRED = 8
# S2.4 兩個 mode 的 typed 結局 → 退出碼。表外一律 EXIT_RECOVERY_REQUIRED(fail-closed:
# 一個沒被列舉的新終端絕不能靜默變成 0)。
S2_4_STATUS_EXIT_CODES = {
    s2_4_recovery.STARTUP_COMPENSATION_COMPLETED_EXACT: EXIT_OK,
    s2_4_recovery.STARTUP_COMPENSATION_NOT_APPLICABLE: EXIT_OK,
    s2_4_recovery.INTENT_GATE_ADMITTED: EXIT_OK,
    s2_4_recovery.STARTUP_COMPENSATION_PENDING: EXIT_HOST_CAPABILITY_ABSENT,
}

HEAD_LENGTH = 40
_HEX = set("0123456789abcdef")


def _canonical_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _is_head(value: Any) -> bool:
    text = str(value or "")
    return len(text) == HEAD_LENGTH and set(text) <= _HEX


class CliInputError(ValueError):
    """Raised when a caller-supplied file is missing / unreadable / not canonical JSON."""


def _load_json(path: Path | None, *, label: str) -> Any:
    if path is None:
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CliInputError(f"--{label} is not readable: {error}") from error
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise CliInputError(f"--{label} is not valid JSON: {error}") from error


def _load_bytes(path: Path | None, *, label: str) -> bytes | None:
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError as error:
        raise CliInputError(f"--{label} is not readable: {error}") from error


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
    now = host_kernel.host_wall_clock_time()
    verification = _verify_operator_authorization(
        session=args.session, intent=intent, authorization=authorization, signature=signature,
        source_head=args.source_head, now=now,
    )
    intent_digest = intent.get("self_digest") if isinstance(intent, dict) else None
    # P1-B:同一道 intent/主機 class 綁定也套在 CLI 的 dry-run 矩陣上 —— ``admit`` 的裁決必須與
    # 兩個 runner 進入點逐字同義,否則 operator 會拿到一份與真實施作不同的預演結論。
    intent_target_class = intent.get("target_class") if isinstance(intent, dict) else None
    errors = host_kernel.host_target_admission_errors(
        target_view,
        allow_production=bool(args.allow_production),
        production_confirm=args.production_confirm,
        intent_digest=intent_digest,
        operator_authorization_verified=bool(verification["verified"]),
        intent_target_class=intent_target_class,
    )
    if not isinstance(intent, dict):
        errors.append("--intent-file must contain a typed intent object")
    elif intent.get("source_head") != args.source_head:
        errors.append("--source-head must equal the intent source_head")
    # permit 與 signature 必須成對出現:單獨一份永遠無法構成一次已驗證的 operator 授權。
    if (args.operator_permit is None) != (args.operator_signature is None):
        errors.append(
            "--operator-permit and --operator-signature must be supplied together"
        )
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


def _observation(args, target_view: dict[str, Any]) -> dict[str, Any]:
    """唯讀觀測面 —— **也要過 L1**(E2 P2 #7),只是刻意比 apply 面弱一級並寫明理由。

    ``production`` / ``unknown`` 需要一次顯式 ``--allow-production`` 承認才會真的碰主機;不需要
    綁 intent digest 的 SSHSIG,因為觀測面的每條 argv 都在唯讀 allowlist 內、結構上不可能變更狀態,
    而觀測正是「拿到 permit 之前」要做的事(理由字串一併落盤,不靠讀者記憶)。
    """

    admission_errors = host_kernel.host_observation_admission_errors(
        target_view, allow_production=bool(args.allow_production)
    )
    if admission_errors:
        raise host_observer.S2HostObserverError(
            "the read-only observation is refused by the L1 host gate: "
            + "; ".join(admission_errors)
        )
    kernel = host_kernel.HostExecutionKernel(
        session=host_kernel.SESSION_S2_HOST_OBSERVER_CHILD
    )
    # P2-D:``s2_0`` 段**沒有** unit 面(它的主機面是 local-socket PG,不是 systemd),而
    # ``process_identity`` 的每一個欄位都衍生自 unit 的 MainPID/InvocationID/ControlGroup ——
    # 少了 unit 面,它只會發出 ``main_pid=0`` / ``proc_present=false`` 與由**缺席**屬性算出的指紋,
    # 也就是把一個從未被觀測的 process 包裝成看似有效的 runtime 證據。故 s2_0 只取檔案身分面。
    request = {
        "schema_version": host_observer.REQUEST_SCHEMA_VERSION,
        "faces": [host_observer.FACE_FILE_IDENTITY],
        "path_keys": sorted(host_observer.CANONICAL_OBSERVABLE_PATHS),
        # child 的 ``main()`` 自己也過同一道 L1 閘(RES-6),故承認必須隨 request 傳下去 ——
        # 否則 CLI 這邊放行、child 那邊自己拒,兩道閘會不一致。
        "allow_production": bool(args.allow_production),
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
    # 出境守衛(父側,與 child 的 stdout 閘同一支掃描器):observation 落 ``observation.json``
    # 之前必須再過一次。父側**不得**把「子行程有守衛」當成自己的保證 —— 這裡是 observer 產出
    # 進入落盤 sink 的唯一入口,舊 child / 被替換的 child / 未來新增的觀測面都必須在此被同一套
    # 判準攔下。命中即 typed 拒 ⇒ 零 observation.json。
    #
    # 誠實界線:真 spawn 路徑上,child stdout 早已在 kernel 的 ``_execute`` 裡過了同一套規則的
    # ``_redact``,所以命中形會先變成 ``<redacted>`` 而導致 self_digest 對不上(上面那道 typed
    # 拒)。本守衛因此**不是**該路徑上的第一道防線,而是「不經 ``_redact`` 的傳輸」(測試替身、
    # 被替換的 child、未來任何直接回傳形)上的顯式且理由正確的那一道。
    leak_reasons = host_kernel.scan_serializable_surface_for_secrets(observation)
    if leak_reasons:
        raise host_observer.S2HostObserverError(
            "the process-separated observation carried secret-shaped content and was dropped: "
            + "; ".join(leak_reasons[:3])
        )
    return observation


def _s2_4_run(args) -> dict[str, Any]:
    """S2.4 的兩個啟動 mode。**driver 恆為 ``None``**,故零主機接觸。

    這不是「還沒接上」的殘缺:S2.4 的 aggregate host driver 需要 systemd 觀測面與五支 row
    driver,而那兩樣都不在本波範圍內(本波是 recovery core,零新主機能力)。今日這條 CLI 因此
    只跑得到「plan / lane id / permit 這些**輸入**站不站得住」與「主機面在不在」這兩層——兩者
    都是真的閘、都能真的紅,而且都不需要碰主機。
    """

    if args.mode == "reconcile":
        return s2_4_recovery.reconcile_before_s2_4_intent(
            None, lane=str(args.lane), lane_id=args.lane_id
        )
    plan = _load_json(args.plan_file, label="plan-file")
    intents = _load_json(args.component_intents_file, label="component-intents-file")
    authorizations = {
        "apply_aggregate": _load_json(
            args.apply_aggregate_permit, label="apply-aggregate-permit"
        ),
        "pg_migration": _load_json(args.pg_migration_permit, label="pg-migration-permit"),
    }
    return s2_4_recovery.compensate_s2_4_startup_residue(
        plan, authorizations, None, component_intents=intents
    )


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
    # ── S2.4 §5.2/§5.4 的啟動 mode ──
    parser.add_argument("--lane", choices=s2_4_recovery.INTENT_GATE_LANES)
    parser.add_argument("--lane-id", default=None)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--component-intents-file", type=Path)
    parser.add_argument("--apply-aggregate-permit", type=Path)
    parser.add_argument("--pg-migration-permit", type=Path)
    args = parser.parse_args(argv)

    if not _is_head(args.source_head):
        parser.error("--source-head must be exact lowercase 40-hex")
    if args.mode not in SESSION_MODES[args.session]:
        parser.error(
            f"--session {args.session} supports only "
            f"{list(SESSION_MODES[args.session])}; --mode {args.mode} belongs to another "
            "session's input contract"
        )
    if args.mode in ("admit", "apply") and args.intent_file is None:
        parser.error(f"--mode {args.mode} requires --intent-file")
    if args.mode == "reconcile" and (args.lane is None or args.lane_id is None):
        parser.error("--mode reconcile requires --lane and --lane-id")
    if args.mode == "compensate" and (
        args.plan_file is None
        or args.component_intents_file is None
        or args.apply_aggregate_permit is None
        or args.pg_migration_permit is None
    ):
        parser.error(
            "--mode compensate requires --plan-file, --component-intents-file and BOTH "
            "--apply-aggregate-permit / --pg-migration-permit (§5.4 reverse compensation is "
            "the undo of an APPLY that atomically consumed both permits)"
        )

    # E2 RES-7:``mkdir`` 原本在 ``try:`` **之外** ⇒ ``--out-dir /dev/null/nope`` 會產生一個裸
    # traceback、process rc=1、零 artifact,與本檔 docstring「絕不讓一個裸 traceback 把 process
    # 退成 1」字面衝突。out-dir 建不起來時**沒有任何地方**可以落盤(那是誠實的物理限制),所以
    # 正確的收場是 typed usage 退出 + stderr 明文,而不是 traceback。
    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        sys.stderr.write(
            f"--out-dir is not creatable ({error}); no artifact can be written there and this "
            "runner refuses to continue without its artifact contract\n"
        )
        return EXIT_USAGE
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

        if args.mode in ("reconcile", "compensate"):
            verdict = _s2_4_run(args)
            _canonical_write(args.out_dir / "s2_4_startup_verdict.json", verdict)
            summary["status"] = verdict["status"]
            summary["reasons"] = verdict["reasons"]
            summary["mutation_performed"] = bool(verdict.get("mutation_performed"))
            summary["driver_engaged"] = bool(verdict.get("driver_engaged"))
            summary["new_obligations"] = list(verdict.get("new_obligations") or [])
            # 表外一律 EXIT_RECOVERY_REQUIRED:一個沒被列舉的新終端絕不能靜默變成 0。
            exit_code = S2_4_STATUS_EXIT_CODES.get(
                verdict["status"], EXIT_RECOVERY_REQUIRED
            )
            summary["exit_code"] = exit_code
            return exit_code

        if args.mode == "probe":
            exit_code = EXIT_OK
            summary["status"] = "PROBED"
            if args.observe:
                try:
                    observation = _observation(args, target_view)
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

        intent = _load_json(args.intent_file, label="intent-file")
        authorization = _load_json(args.operator_permit, label="operator-permit")
        signature = _load_bytes(args.operator_signature, label="operator-signature")
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
    except CliInputError as error:
        # 壞 --intent-file / --operator-permit / --operator-signature:typed fail-closed,且
        # artifact 的 exit_code 與 process 的真實退出碼一致(E2 P2 #8)。
        summary["status"] = "INPUT_INVALID"
        summary["input_error"] = str(error)
        exit_code = EXIT_INPUT_INVALID
        return exit_code
    except Exception as error:  # noqa: BLE001 - fail loud:記錄後以 typed 退出碼收場,絕不裸逸
        summary["status"] = "RUNNER_FAILED"
        summary["runner_error"] = f"{type(error).__name__}: {error}"
        exit_code = EXIT_INTERNAL_ERROR
        sys.stderr.write(f"S2 host runner failed: {type(error).__name__}: {error}\n")
        return exit_code
    finally:
        # 頂層 finally:不論走哪條路,``--out-dir`` 的 canonical artifact 契約都成立。
        summary["exit_code"] = exit_code
        try:
            _canonical_write(args.out_dir / "run_summary.json", summary)
        except OSError as error:
            # RES-7:``finally`` 內任何逸出的例外都會**取代** return value ⇒ 又變回裸 traceback
            # 退 1。out-dir 若在執行中途消失,只能誠實記在 stderr,絕不讓它吃掉退出碼。
            sys.stderr.write(f"run_summary.json could not be written: {error}\n")
        sys.stdout.write(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
