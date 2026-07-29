"""S2E.2a:S2.0(PG observer bootstrap)的**受信主機 runner**。

本模組提供 ``agent_governance_pg_observer_bootstrap.ObserverBootstrapProductionDriver`` 的
**local-socket-only** 實作,以及兩條互斥的驅動 lane:

* :func:`run_observer_bootstrap_on_host` —— 生產 lane。在**構造任何 driver 之前**先由
  ``agent_governance_s2_host_kernel.derive_host_target_class()`` 導出 target class 並過
  ``host_target_admission_errors``:``production`` / ``unknown`` 必須 ``--allow-production`` +
  已驗證 operator SSHSIG + ``--production-confirm`` 逐字回填三者並存;任一缺席即 typed 拒且
  **driver 永不被構造**(``ObserverBootstrapHostDriver.constructions`` 是可斷言的計數器)。
* :func:`rehearse_observer_bootstrap` —— 拋棄式 rehearsal lane。只對**注入的**丟棄式叢集連線
  執行,且**恆拒**在 ``production`` target class 上排練。

**誠實界線(必讀,絕不可被誤讀為 EFFECT 進展)。**

1. 本模組對 ``agent_governance_pg_observer_bootstrap`` **零行修改**。刪掉整個 runner 家族,
   該 adapter 的行為與今日逐位元組相同(driver 恆為 ``None`` ⇒ 全部 ``EXTERNAL_VERIFICATION_PENDING``)。
2. rehearsal 的每個成功頂點在 S2E.1 都已被標成 closure-PASS-blocked
   (``agent_governance_s2_effect_binding`` 的 ``closure_pass_blocked_reason``),且 PR#154 的
   effect-DAG 傳遞性阻塞使九步全不可 PASS。**rehearsal 綠絕不是 closure PASS,也絕不是 EFFECT 進展。**
3. rehearsal driver 的 ``evidence_class`` 誠實回報 ``LOCAL_REPRODUCIBLE``,故 adapter 於 §6 step 9a
   的第一道 cheap filter 就會補償並回 ``EXTERNAL_VERIFICATION_PENDING`` —— 這正是預期行為,
   ``production_apply_performed`` 恆 false。
4. ``signed_apply_attestation`` 在本模組**永遠 raise**:attestor 私鑰不在 Mac、也不在 trade-core,
   任何「排練時簽一張」的做法都是偽造 platform 背書。
5. 獨立 ops_postcheck:一律呼叫 S2E.1 既有的
   ``agent_governance_s2_effect_binding.build_s2_effect_ops_postcheck_evidence``。該函式對 S2.0
   **typed 拒絕**(其硬門要求的 runtime ``command_capture_v2`` 形狀今日在 ``closure_packet_v1``
   不可表示),本 runner 忠實把那份拒絕理由記進 run result,**絕不**另造第二種 receipt schema(§H R4)。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
for _candidate in (_HERE, _REPO_ROOT / "program_code" / "ml_training"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_pg_observer_bootstrap as pg_observer  # noqa: E402
import agent_governance_s2_effect_binding as s2_effect_binding  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402


S2_0_STEP = "S2_0_APPLY"
# rehearsal driver 的誠實證據等級:拋棄式叢集永遠不是 PLATFORM_ATTESTED。
LOCAL_REPRODUCIBLE_EVIDENCE_CLASS = "LOCAL_REPRODUCIBLE"


class S2_0HostRunnerError(RuntimeError):
    """Raised when the S2.0 host runner refuses to act (fail-closed; the driver is never built)."""


# --------------------------------------------------------------------------- #
# the local-socket-only production driver implementation
# --------------------------------------------------------------------------- #
class ObserverBootstrapHostDriver:
    """Local-socket-only ``ObserverBootstrapProductionDriver``.

    **絕不**接受 raw SQL、**絕不**接受 DSN 字串:所有 DDL 都由 adapter 以結構化 enum selector
    投影出的 ``grant_set`` 驅動,所有連線都由注入的 capability callable 提供(生產面由真主機供裝,
    rehearsal 面由丟棄式叢集供裝)。

    能力分割:applier 連線(``applier_connect``)與 **distinct verifier** 連線
    (``verifier_connect``)是兩條相異連線 ⇒ 相異 PG backend;verifier 另需一條能
    ``SET ROLE <observer>`` 的登入連線(``observer_session_connect``)才可能做出真正的拒絕證明。
    缺任一能力時 :meth:`independent_read_only_proof` **typed raise**,絕不偽造一份 proof。
    """

    #: 建構計數器 —— 「production 拒絕時 driver 未被構造」以此為可機證的斷言。
    constructions = 0

    def __init__(
        self,
        *,
        applier_connect: Callable[[], Any],
        verifier_connect: Callable[[], Any],
        observer_session_connect: Callable[[], Any] | None = None,
        credential_escalation_connect: Callable[[], Any] | None = None,
        set_role_target: str | None = None,
        observer_session_role: str | None = None,
        verifier_capture_digest: str | None = None,
        evidence_class: str = LOCAL_REPRODUCIBLE_EVIDENCE_CLASS,
        proof_fault: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        compensate_fault: Callable[[], None] | None = None,
    ) -> None:
        type(self).constructions += 1
        self.evidence_class = evidence_class
        self._applier_connect = applier_connect
        self._verifier_connect = verifier_connect
        self._observer_session_connect = observer_session_connect
        self._credential_escalation_connect = credential_escalation_connect
        self._set_role_target = set_role_target
        self._observer_session_role = observer_session_role
        self._verifier_capture_digest = verifier_capture_digest
        # 兩個 fault hook 與 adapter 既有的 ``apply_fault`` 同性質:**測試專用**,用來把真實的
        # 「驗證者不同意 / 補償失敗」路徑逼出來,絕不用於偽造成功。
        self._proof_fault = proof_fault
        self._compensate_fault = compensate_fault
        self.calls: list[str] = []

    # -- read-only pre-state ------------------------------------------------ #
    def observer_role_present(self, *, role: str) -> bool:
        self.calls.append("observer_role_present")
        connection = self._applier_connect()
        return bool(pg_observer.observer_role_present(connection.cursor(), role=role))

    def observe_acl_state(self, *, role: str, schema: str, relations: list[str]) -> str:
        self.calls.append("observe_acl_state")
        connection = self._applier_connect()
        return pg_observer.observer_role_acl_state_digest(
            connection.cursor(), role=role, schema=schema, relations=list(relations)
        )

    # -- the fixed structured apply (grant_set only; no caller SQL) ---------- #
    def create_read_only_observer(self, *, grant_set: dict[str, Any]) -> None:
        self.calls.append("create_read_only_observer")
        connection = self._applier_connect()
        pg_observer.observer_bootstrap_apply(connection.cursor(), grant_set=grant_set)

    # -- the DISTINCT verifier's independent proof -------------------------- #
    def independent_read_only_proof(self, *, grant_set: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("independent_read_only_proof")
        if self._observer_session_connect is None or self._set_role_target is None:
            raise S2_0HostRunnerError(
                "the distinct verifier cannot connect AS the observer role (no observer session "
                "capability / no SET ROLE target); refusing to fabricate a read-only proof"
            )
        role = str(grant_set["role"])
        schema = str(grant_set["schema"])
        relations = [str(item) for item in grant_set["relations"]]
        verifier = self._verifier_connect()
        cursor = verifier.cursor()
        session_role = self._observer_session_role
        granted = False
        try:
            if session_role:
                cursor.execute(f'GRANT "{role}" TO "{session_role}"')
                granted = True
            session = self._observer_session_connect()
            try:
                session_cursor = session.cursor()
                session_cursor.execute(f'SET ROLE "{role}"')
                write_denied = pg_observer.probe_observer_write_denied(
                    session_cursor, schema=schema, relation=relations[0]
                )
                set_role_denied = pg_observer.probe_observer_set_role_denied(
                    session_cursor, target_role=self._set_role_target
                )
                search_path = pg_observer.probe_observer_search_path_reset_harmless(
                    session_cursor, schema=schema, relation=relations[0]
                )
            finally:
                session.close()
            if self._credential_escalation_connect is None:
                raise S2_0HostRunnerError(
                    "the distinct verifier has no credential-escalation probe capability; "
                    "refusing to fabricate a 28P01 denial"
                )
            credential_denied = pg_observer.probe_credential_escalation_denied(
                self._credential_escalation_connect
            )
            reobserved = pg_observer.observer_role_acl_state_digest(
                cursor, role=role, schema=schema, relations=relations
            )
        finally:
            if granted and session_role:
                try:
                    cursor.execute(f'REVOKE "{role}" FROM "{session_role}"')
                except Exception:  # noqa: BLE001 - 撤回失敗不得掩蓋主要結果
                    pass
        proof = {
            "read_only_proof": {
                "write_denied": write_denied,
                "set_role_denied": set_role_denied,
                "search_path_reset_harmless": search_path,
                "credential_escalation_denied": credential_denied,
            },
            "reobserved_digest": reobserved,
            "verifier_capture_digest": self._verifier_capture_digest,
        }
        if self._proof_fault is not None:
            proof = self._proof_fault(proof)
        return proof

    # -- ownership-aware compensation --------------------------------------- #
    def compensate(self, *, grant_set: dict[str, Any]) -> None:
        self.calls.append("compensate")
        if self._compensate_fault is not None:
            self._compensate_fault()
        connection = self._applier_connect()
        pg_observer.observer_bootstrap_rollback(connection.cursor(), grant_set=grant_set)

    # -- platform attestation: never available off a real trusted host ------ #
    def signed_apply_attestation(
        self, *, intent: dict[str, Any], applied_grant_set_digest: str, reobserved_digest: str
    ) -> dict[str, Any]:
        self.calls.append("signed_apply_attestation")
        raise S2_0HostRunnerError(
            "the S2.0 apply attestation must be signed by the off-repo trust-root key, which is on "
            "neither Mac nor trade-core; this runner never mints a platform attestation"
        )


# --------------------------------------------------------------------------- #
# host admission (L1) — refuse BEFORE constructing any driver
# --------------------------------------------------------------------------- #
def _require_host_admission(
    target_view: dict[str, Any],
    *,
    allow_production: bool,
    production_confirm: Any,
    intent_digest: Any,
    operator_authorization_verified: bool,
) -> None:
    errors = host_kernel.host_target_admission_errors(
        target_view,
        allow_production=allow_production,
        production_confirm=production_confirm,
        intent_digest=intent_digest,
        operator_authorization_verified=operator_authorization_verified,
    )
    if errors:
        raise S2_0HostRunnerError(
            "S2.0 host runner refuses to construct a driver: " + "; ".join(errors)
        )


def _ops_postcheck_projection(receipt: dict[str, Any], *, verifier_node: str, observed_at: str) -> dict[str, Any]:
    """一律走 S2E.1 既有的建構子;它對 S2.0 typed 拒絕時忠實記錄理由(絕不另造第二種 schema)。"""

    try:
        evidence = s2_effect_binding.build_s2_effect_ops_postcheck_evidence(
            receipt, verifier_node=verifier_node, observed_at=observed_at
        )
    except ValueError as error:
        return {"evidence": None, "refusal": str(error)}
    return {"evidence": evidence, "refusal": None}


def _run_result(
    *,
    lane: str,
    target_view: dict[str, Any],
    receipt: dict[str, Any],
    pre_state_digest: str | None,
    post_state_digest: str | None,
    observer_present_after: bool | None,
    driver_calls: list[str],
    verifier_node: str,
) -> dict[str, Any]:
    postcheck = _ops_postcheck_projection(
        receipt, verifier_node=verifier_node, observed_at=host_kernel.trusted_host_time()
    )
    return {
        "lane": lane,
        "step": S2_0_STEP,
        "target_class_view": target_view,
        "status": receipt.get("status"),
        "receipt": receipt,
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "catalog_restored_exact": (
            pre_state_digest is not None and pre_state_digest == post_state_digest
        ),
        "observer_present_after": observer_present_after,
        "driver_calls": list(driver_calls),
        "ops_postcheck_evidence": postcheck["evidence"],
        "ops_postcheck_refusal": postcheck["refusal"],
        # S2E.1 已把 S2.0 標成 closure-PASS-blocked,且 effect-DAG 傳遞阻塞使九步全不可 PASS。
        "closure_pass_blocked": True,
        "closure_pass_blocked_reason": s2_effect_binding.S2_STEP_RECEIPT_CONTRACTS[S2_0_STEP][
            "closure_pass_blocked_reason"
        ],
        "production_apply_performed": bool(
            (receipt.get("boundary") or {}).get("production_apply_performed")
        ),
    }


# --------------------------------------------------------------------------- #
# lane 1 — production apply on a real trusted host
# --------------------------------------------------------------------------- #
def run_observer_bootstrap_on_host(
    intent: dict[str, Any],
    operator_authorization: Any,
    signature: Any,
    *,
    now: str,
    source_head: str,
    driver_factory: Callable[[], Any],
    allow_production: bool = False,
    production_confirm: Any = None,
    operator_authorization_verified: bool = False,
    target_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive one S2.0 production apply on a real trusted host (L1 admission first).

    ``driver_factory`` 只有在 host admission **通過之後**才被呼叫 —— 這是「production 被拒時
    driver 根本不被構造」在程式結構上的保證。
    """

    view = target_view or host_kernel.derive_host_target_class()
    _require_host_admission(
        view,
        allow_production=allow_production,
        production_confirm=production_confirm,
        intent_digest=intent.get("self_digest"),
        operator_authorization_verified=operator_authorization_verified,
    )
    driver = driver_factory()
    surface_errors = host_kernel.assert_read_only_surface(
        driver, forbidden={"enable_now", "restart", "mask", "unmask", "daemon_reload", "kill"}
    )
    if surface_errors:
        raise S2_0HostRunnerError("; ".join(surface_errors))
    receipt = pg_observer.apply_observer_bootstrap(
        intent, operator_authorization, signature,
        now=now, source_head=source_head, driver=driver,
    )
    return _run_result(
        lane="production",
        target_view=view,
        receipt=receipt,
        pre_state_digest=None,
        post_state_digest=None,
        observer_present_after=None,
        driver_calls=getattr(driver, "calls", []),
        verifier_node=str(intent.get("postcheck_node_id")),
    )


# --------------------------------------------------------------------------- #
# lane 2 — disposable rehearsal against an INJECTED throwaway cluster
# --------------------------------------------------------------------------- #
def rehearse_observer_bootstrap(
    intent: dict[str, Any],
    operator_authorization: Any,
    signature: Any,
    *,
    now: str,
    source_head: str,
    driver: ObserverBootstrapHostDriver,
    catalog_probe: Callable[[], str],
    role_probe: Callable[[], bool],
    target_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rehearse the S2.0 production gate against an injected throwaway cluster.

    ``catalog_probe`` / ``role_probe`` 是**獨立於 driver** 的觀測 callable(由 rehearsal harness
    直接連丟棄式叢集提供),用來在 apply 前後各取一次 catalog 投影,證明補償後的 catalog digest
    **逐位元組**回到前態。恆拒在 ``production`` target class 上排練。
    """

    view = target_view or host_kernel.derive_host_target_class()
    if view.get("target_class") == host_kernel.TARGET_CLASS_PRODUCTION:
        raise S2_0HostRunnerError(
            "refusing to rehearse the S2.0 apply on a production target host"
        )
    if driver.evidence_class == pg_observer.PRODUCTION_APPLIED_EVIDENCE_CLASS:
        raise S2_0HostRunnerError(
            "a rehearsal driver may never claim PLATFORM_ATTESTED evidence"
        )
    pre_state_digest = catalog_probe()
    receipt = pg_observer.apply_observer_bootstrap(
        intent, operator_authorization, signature,
        now=now, source_head=source_head, driver=driver,
    )
    post_state_digest = catalog_probe()
    result = _run_result(
        lane="disposable_rehearsal",
        target_view=view,
        receipt=receipt,
        pre_state_digest=pre_state_digest,
        post_state_digest=post_state_digest,
        observer_present_after=bool(role_probe()),
        driver_calls=getattr(driver, "calls", []),
        verifier_node=str(intent.get("postcheck_node_id")),
    )
    result["rehearsal"] = True
    return result
