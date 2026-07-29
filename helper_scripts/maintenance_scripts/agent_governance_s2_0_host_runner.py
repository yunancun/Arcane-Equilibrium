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
    (``verifier_connect``)是兩條相異連線 ⇒ 相異 PG backend;verifier 另需一條**已經可以**
    ``SET ROLE <observer>`` 的 session 連線(``observer_session_connect``)才可能做出真正的拒絕
    證明。缺任一能力時 :meth:`independent_read_only_proof` **typed raise**,絕不偽造一份 proof。

    **本 driver 絕不執行任何 role membership DDL(E2 RUN-2(b) 的處置)。** registry 的
    ``pg_observer_bootstrap_adapter_v1.invariant`` 明文 ``no role membership``,而本模組正被 append
    進該 adapter 的 ``implementation_paths`` ⇒ 由 runner 自己發 ``GRANT <observer> TO <session>`` /
    ``REVOKE`` 會在該 invariant 的**字面**下把 observer 角色的成員圖改寫,且會逼「independent
    verifier」持有一條 **admin 寫連線**(與設計 §B.2「observer 結構上不持有任何寫能力」直接衝突)。
    故 assumable session 一律由**供裝者**提供,runner 這邊只發一條 session 局部、非 DDL、不持久的
    ``SET ROLE``——與 adapter 自己的 ``probe_observer_set_role_denied`` 同形,且識別碼一律經
    ``_safe_ident`` 白名單。

    ``observer_session_connect`` 的**真實供裝時序(E2 在真 PG 16.14 上實證,更正前一版敘述)。**
    前一版本寫「T1 由 harness 預先建立、生產面由 operator 的 peer/ident 映射預先建立」——那句
    **被證偽**,而且是**結構上不可能**的:

    * ``GRANT "<observer>" TO "<login>"`` 在 observer 角色存在之前一律
      ``UndefinedObject: role "<observer>" does not exist``;而 observer 角色要到 adapter 的
      **step 7**(``create_read_only_observer``)才被建立,adapter 的 **step 6** 又硬拒任何**既存**
      的 observer 角色(``refusing to adopt or rotate a pre-existing role``)⇒ 這筆 membership
      **不可能預先建立**。
    * 沒有 membership 的**非 superuser** 登入角色直接 ``SET ROLE <observer>`` 一律
      ``InsufficientPrivilege``。

    ⇒ **peer/ident 只解決「認證」,不解決「membership」。** 正確時序是 **lazy**:供裝者必須在
    adapter **step 7 之後、step 8(**``independent_read_only_proof``**)之前**才發那一條
    ``GRANT <observer> TO <login>``。本 driver 在 step 8 才呼叫 ``observer_session_connect()``,
    正是為了讓供裝者能在那一刻(而不是更早)完成它。T1 的
    ``_provisioned_observer_session()`` 今日就是這樣 lazy 做的;生產面同理。

    **生產面 operator 前置(供裝 ``observer_session_connect`` /
    ``credential_escalation_connect`` 所需,缺任一項本 driver 一律 typed raise、絕不偽造 proof)。**

    1. 一個**專用登入角色**(下稱 ``<login>``),必須 ``NOSUPERUSER``(另建議 ``NOCREATEROLE``)。
       superuser 的 session 可以 ``SET ROLE`` 任何角色,``probe_observer_set_role_denied`` 就永遠
       拿不到真的 42501 —— 那會把「拒絕證明」變成假的。``NOCREATEROLE`` 則使它無法自行補授
       membership。
    2. ``<login>`` 對目標 database 有 ``CONNECT``(peer/ident 本地認證即可),T1 另授
       ``USAGE ON SCHEMA <observed_schema>`` 作為參照供裝。
    3. **membership 必須 lazy 授予**:``GRANT <observer_role> TO <login>`` 只能在 step 7 之後、
       step 8 之前發出;runner 這邊一行都不發。窗後的
       ``REVOKE <observer_role> FROM <login>`` 同樣是 operator 的職責(runner **刻意沒有**撤權
       路徑,見 RUN-2(c) 的 fail-loud 處置)。
    4. ``credential_escalation_connect`` 這個能力**也要供裝**:它必須是一次會被 PG 以
       ``28P01``/``28000`` 拒絕的連線嘗試(T1 用同一個 ``<login>`` 配錯密碼)。這要求 ``<login>``
       有一條**密碼型**認證入口可打(``scram-sha-256``);observer 角色自己仍然是
       ``NOLOGIN`` + peer/ident 無密碼(``generate_observer_grant_sql`` 對非 peer/ident 的
       ``auth_mapping`` 恆 fail-closed),兩者是**不同角色**,故此前置不放寬 observer 的
       no-password-ingress 邊界。若這條入口無法供裝,``independent_read_only_proof`` 會 typed
       raise —— 絕不偽造一個 28P01。
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
        # 識別碼一律過 S1.5 ``_pg_ident`` 白名單(``^[a-z_][a-z0-9_]*$`` + 引號化);S2.0 家族其他
        # 每一處識別碼都走同一道,本 driver 不得例外(E2 RUN-2(a):真 PG 上實證可逃出裸雙引號)。
        role = pg_observer._safe_ident(grant_set["role"])
        role_name = str(grant_set["role"])
        schema = str(grant_set["schema"])
        relations = [str(item) for item in grant_set["relations"]]
        if self._credential_escalation_connect is None:
            raise S2_0HostRunnerError(
                "the distinct verifier has no credential-escalation probe capability; "
                "refusing to fabricate a 28P01 denial"
            )
        session = self._observer_session_connect()
        try:
            session_cursor = session.cursor()
            # 唯一一條由 runner 發出的語句:session 局部、非 DDL、不持久的 SET ROLE。
            # **絕不** GRANT/REVOKE role membership(見 class docstring 的 invariant 論證)。
            session_cursor.execute(f"SET ROLE {role}")
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
        credential_denied = pg_observer.probe_credential_escalation_denied(
            self._credential_escalation_connect
        )
        # verifier 連線只做**唯讀** catalog 投影(零 DDL、零 membership),故它不需要、也不應該是
        # 一條 admin 寫連線。
        reobserved = pg_observer.observer_role_acl_state_digest(
            self._verifier_connect().cursor(), role=role_name, schema=schema, relations=relations
        )
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


def _observed_driver_calls(driver: Any) -> list[str] | None:
    """runner 自有 driver → 真實呼叫序;其他 → ``None``(**絕不**把「無法觀測」報成 ``[]``)。

    E2 RUN-3:``getattr(driver, "calls", [])`` 會把一個確實被呼叫過的注入物件記成空序列,
    等於把零值當成事實發出。無法觀測時只能誠實發 ``null``。

    E2 RES-4(同源):比對用 ``type(x) is`` 而非 ``isinstance`` —— 一個覆寫方法但不 append
    ``self.calls`` 的子類別能通過 ``isinstance``,零值又會被當成事實。
    """

    if type(driver) is ObserverBootstrapHostDriver:
        return list(driver.calls)
    return None


def _run_result(
    *,
    lane: str,
    target_view: dict[str, Any],
    receipt: dict[str, Any],
    pre_state_digest: str | None,
    post_state_digest: str | None,
    observer_present_after: bool | None,
    driver_calls: list[str] | None,
    verifier_node: str,
) -> dict[str, Any]:
    postcheck = _ops_postcheck_projection(
        receipt, verifier_node=verifier_node, observed_at=host_kernel.host_wall_clock_time()
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
        "driver_calls": None if driver_calls is None else list(driver_calls),
        "driver_calls_observable": driver_calls is not None,
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
) -> dict[str, Any]:
    """Drive one S2.0 production apply on a real trusted host (L1 admission first).

    **production lane 不收任何 caller target view**(E2 RUN-1)。target class 一律當場由
    ``derive_host_target_class()`` 從主機事實導出;一個 ``target_view=`` 參數(即使 default 是
    ``None``)等於把「我在拋棄式主機上」這個自我宣告的洞原樣搬回 L1,並且會讓落盤 artifact 記下
    偽造值 ⇒ 稽核說謊。要在非目標主機上證明拒絕矩陣,請用 rehearsal lane 的**只能加嚴**注入。

    ``driver_factory`` 只有在 host admission **通過之後**才被呼叫 —— 這是「production 被拒時
    driver 根本不被構造」在程式結構上的保證;且回傳物件必須是 runner 自有的
    :class:`ObserverBootstrapHostDriver`,否則 typed 拒(RUN-3:一個無法觀測的注入物件會讓
    ``driver_calls`` 這類欄位變成不可信的零值,而 runner 存在的理由正是提供可觀測的主機面)。
    """

    view = host_kernel.derive_host_target_class()
    _require_host_admission(
        view,
        allow_production=allow_production,
        production_confirm=production_confirm,
        intent_digest=intent.get("self_digest"),
        operator_authorization_verified=operator_authorization_verified,
    )
    driver = driver_factory()
    if type(driver) is not ObserverBootstrapHostDriver:
        raise S2_0HostRunnerError(
            "the S2.0 production lane only drives the runner's own ObserverBootstrapHostDriver "
            f"(exact type); an unobservable {type(driver).__name__!r} capability is refused (its "
            "call sequence could never be reported honestly)"
        )
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
        driver_calls=_observed_driver_calls(driver),
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
    **逐位元組**回到前態。

    ``target_view`` 只在**排練**面存在,且**只能加嚴**:derived 或 injected 任一為
    ``production``/``unknown`` 即拒(``unknown`` 與 ``production`` 同等對待)。落盤的
    ``target_class_view.target_class`` 永遠是**導出值**。
    """

    derived = host_kernel.derive_host_target_class()
    refusals = host_kernel.rehearsal_target_refusals(derived, target_view)
    if refusals:
        raise S2_0HostRunnerError(
            "refusing to rehearse the S2.0 apply: " + "; ".join(refusals)
        )
    view = host_kernel.rehearsal_target_view_record(derived, target_view)
    if type(driver) is not ObserverBootstrapHostDriver:
        raise S2_0HostRunnerError(
            "the S2.0 rehearsal lane only drives the runner's own ObserverBootstrapHostDriver "
            "(exact type)"
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
        driver_calls=_observed_driver_calls(driver),
        verifier_node=str(intent.get("postcheck_node_id")),
    )
    result["rehearsal"] = True
    return result
