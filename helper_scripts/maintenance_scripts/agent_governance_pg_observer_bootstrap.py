"""S2.0 production PG observer-bootstrap SOURCE Adapter (AIML WP2).

把 S1.1(唯讀身分證明)/ S1.3(最小權限契約)/ S1.5(可拋棄 role/ACL apply+rollback)接成
一條「生產唯讀 observer 角色 bootstrap」的 SOURCE seam:一張 exact typed intent、一組**結構化
allowlist**(絕非呼叫端 raw SQL)產出的最小唯讀 observer grant set、一個 applier、與一位**相異**
獨立驗證者的唯讀證明,外加精確 REVOKE/DROP rollback。這是 S2.0 的 **SOURCE_READY** 交付。

**Reachable(但 authority-locked)生產閘(W0a + W0a 真實性強化)。** 生產 apply 不再是無條件 deferred:
``apply_observer_bootstrap`` 多一個 typed ``ObserverBootstrapProductionDriver`` 參數(預設 ``None``),production
目標走一條 mirror §6 的 fail-closed 閘(target-host 身分 → 必觀 ``learning.alr_consumer_events`` 依賴 → fresh
domain-separated operator SSHSIG → 結構化依賴 → driver)。**源碼/測試/Mac 恆 driver=None**,於閘的 step 5 回傳
typed ``EXTERNAL_VERIFICATION_PENDING`` 且**零變更**;``APPLIED``(``production_apply_performed=true``)唯有在真
Linux host driver 回傳一份**trusted-host 簽章的 apply attestation**(``pg_observer_bootstrap_apply_attestation_v1``
——綁 exact intent、applied 目錄 digest、獨立驗證者 reobserved(==applied,T2)、與**簽章的** trusted_host_time)
且通過 :func:`validate_apply_attestation`(T1 SSHSIG + §9.1 trust-root 綁定、T2 reobserved==applied、T5 trusted-clock
窗)時才 emit。bare ``evidence_class`` 只是第一道 cheap filter,不再是 unlock;注入的 simulation/disposable driver
的 ``LOCAL_REPRODUCIBLE``/``STRUCTURAL_ONLY`` 證據**永不**能偽造生產旗標。任何 mutation 若**補償無法確認**
→ 回傳 ``RECOVERY_REQUIRED``(絕不冒充「已補償」pending)。**誠實界線**:離線 validator/CLI 只證簽章完整性 +
trust-root 綁定,**不**背書「真 apply 過」;真正的 runtime-apply 真實性(§9.1 私鑰不在 Mac/trade-core)屬 S2.0 EFFECT
session 的帶外 trusted-host 驗證(OPS-2 closure predicate 未動)。W0a 只 land 這條 reachable 閘 + driver protocol +
attestation 驗證 + schema + 丟棄式測試鑰測試;**絕不**在生產跑它、**絕不**注入 live ``route_task`` effect 節點。
**永不**假成功。

**誠實界線(CLAUDE 四 / Typed Authority Matrix)。** land 時不接觸任何生產 PG/psql/network/broker。
可拋棄叢集測試(S1.1/S1.3/S1.5 同一 pattern)會真的 ``initdb`` 起一個丟棄式 cluster、真跑
``CREATE ROLE``/``GRANT``/``REVOKE``/``DROP`` 並真觀察 ``42501``/``28P01``(LOCAL_REPRODUCIBLE);
真正的生產 socket 一律 DEFERRED 給 S2.0 EFFECT session。九個 authority 恆 false;沒有任何 receipt
序列化機密(operator 私鑰既不在 Mac 也不在 trade-core;只帶非機密的 signer identity/fingerprint/
namespace 與**公開的** SSHSIG bytes)。canonical self-digest 只證完整性,不證誰執行、不證外部事實。

**Domain separation。** operator SSHSIG 沿用 S0.3/S1 既有信任根公鑰/指紋,但以**專屬 identity +
namespace**(``aiml-s2-observer-bootstrap-operator-v1`` / ``arcane-equilibrium-aiml-s2-observer-bootstrap``)
達成 domain separation:一張以 S1 target-host namespace 簽的 permit 於此因 namespace/identity 不符
被拒(反之亦然)。applier != 獨立驗證者(role/node/process/capture 皆須相異)。

stdlib-first;``psycopg2`` 只在可拋棄叢集路徑延遲匯入。唯讀消費 S1.1(``_pg_ident`` 等)/S1.3
(最小權限常量、憑證拒絕碼、``resolve_credential_denial_sqlstate``)/S1.5(``pg_role_acl_state_digest``);
中央 validator 加性委派這四個 typed schema,**不注入** live ``route_task`` effect 節點或 closure
effect 綁定(那要 S2.0 EFFECT session)。
"""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:S1.5 的 PG 識別碼引號 + role/ACL catalog 投影;S1.3 的最小權限常量/憑證拒絕碼;
# 中央 validator 的 canonical_digest / artifact_self_digest。SSHSIG 信任根與驗證基元已隨 operator 授權 +
# apply attestation 加密葉層移至姊妹模組 agent_governance_pg_observer_bootstrap_attestation(見下方再匯出)。
import agent_governance_component_effects as ce  # noqa: E402
import agent_governance_identity_acl_contract as acl  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402

# ── W0a helper decomposition(§10.4 行為守恆):operator 授權 + apply attestation 加密葉層已抽到
#    姊妹葉模組;此處單向再匯出所有被搬移的符號,使既有呼叫端 obs.<symbol> 一律仍解析到同一物件
#    (單一真實來源在葉模組;葉模組不反向匯入本模組,無循環匯入)。
from agent_governance_pg_observer_bootstrap_attestation import (  # noqa: E402,F401
    OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    OPERATOR_IDENTITY,
    OPERATOR_FINGERPRINT,
    OPERATOR_PUBLIC_KEY,
    OPERATOR_ALGORITHM,
    OPERATOR_SIGNATURE_NAMESPACE,
    MAX_AUTHORIZATION_TTL,
    AUTHORIZATION_FIELDS,
    APPLY_ATTESTATION_SCHEMA_VERSION,
    ATTESTOR_IDENTITY,
    ATTESTOR_FINGERPRINT,
    ATTESTOR_PUBLIC_KEY,
    ATTESTOR_ALGORITHM,
    APPLY_ATTESTATION_NAMESPACE,
    MAX_APPLY_ATTESTATION_TTL,
    ATTESTATION_FIELDS,
    APPLY_ATTESTATION_SCHEMA_PATH,
    DIGEST_RE,
    HEAD_RE,
    EVIDENCE_TTL_SECONDS,
    PRODUCTION_APPLIED_EVIDENCE_CLASS,
    PgObserverBootstrapError,
    SecretLeakageError,
    SECRET_LIKE_RE,
    _contains_secret_like,
    _guard_no_secret,
    canonical_bytes,
    _schema,
    _parse_time,
    _plus_seconds,
    intent_self_digest,
    authorization_digest,
    apply_attestation_digest,
    _SSH_SIGNATURE_ARMOR_MARKERS,
    _operator_signature_pem_body_is_strict_base64,
    _guard_operator_signature_pem_body,
    _guard_apply_attestation_signature_pem_body,
    build_operator_authorization,
    validate_operator_authorization,
    _operator_authorization_is_valid,
    operator_authorization_binding_errors,
    build_apply_attestation,
    validate_apply_attestation,
    _apply_attestation_binding_errors,
)


ADAPTER_ID = "pg_observer_bootstrap_adapter_v1"
OWNER_SESSION = "S2.0"

INTENT_SCHEMA_VERSION = "pg_observer_bootstrap_intent_v1"
RESULT_SCHEMA_VERSION = "pg_observer_bootstrap_result_v1"
POSTCHECK_SCHEMA_VERSION = "pg_observer_bootstrap_postcheck_v1"
ROLLBACK_SCHEMA_VERSION = "pg_observer_bootstrap_rollback_v1"

SCHEMA_DIR = ML_TRAINING_DIR / "schemas" / "aiml_gate_receipts"
INTENT_SCHEMA_PATH = SCHEMA_DIR / f"{INTENT_SCHEMA_VERSION}.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / f"{RESULT_SCHEMA_VERSION}.schema.json"
POSTCHECK_SCHEMA_PATH = SCHEMA_DIR / f"{POSTCHECK_SCHEMA_VERSION}.schema.json"
ROLLBACK_SCHEMA_PATH = SCHEMA_DIR / f"{ROLLBACK_SCHEMA_VERSION}.schema.json"

SQLSTATE_RE = re.compile(r"^[0-9A-Z]{5}$")

TARGET_CLASSES = frozenset({"disposable_local", "production"})
DISPOSABLE_TARGET_CLASS = "disposable_local"
PRODUCTION_TARGET_CLASS = "production"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
RESULT_STATUSES = frozenset({
    "APPLIED",
    "APPLIED_ROLLED_BACK_EXACT",
    "ROLLED_BACK_INTERRUPTED",
    "NOT_RESTORED_FAILED",
    # W0a(F2):生產 apply 失敗且**補償無法確認**(compensate 拋錯或 role 仍在)→ 新 additive status,
    # 帶明確 residual reason(observer role 可能殘留,需 operator 手動 recovery),絕不冒充「已補償」pending。
    "RECOVERY_REQUIRED",
    "EXTERNAL_VERIFICATION_PENDING",
    "FAILED",
})
# 非生產目標的主機標記:production apply 若 target_host 命名 Mac/dev/loopback → 於 step 2 typed
# 非成功(zero mutation)。真正的主機身分背書屬 driver + operator SSHSIG + 平台層(離線源碼不可自證)。
_NON_PRODUCTION_HOST_MARKERS = (
    "localhost", "127.0.0.1", "::1", ".local", "macbook", "mac-", "darwin", "dev-", "laptop",
)
TTL_CEILING_SECONDS = 3600

# 唯一可選的結構化 grant set(enum key,非 raw SQL);任何更寬的 selector 一律 fail-closed。
OBSERVER_GRANT_SET_SELECTOR = "observer_read_only_v1"
# observer 走 peer/ident 本地認證,絕不吃密碼(no password ingress);scram/loopback 密碼型一律拒。
OBSERVER_AUTH_METHODS = frozenset({"pg_hba_ident_local", "pg_hba_peer_local"})
# CREATE ROLE 顯式全禁用屬性:所有 S1.3 FORBIDDEN_ROLE_ATTRS 對應的 NO* 皆在,且 NOLOGIN。
_ROLE_ATTRIBUTE_CLAUSE = (
    "NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS"
)
# 連線層釘死唯讀交易 + pg_catalog search_path(session 內重設對 schema-qualified 查詢無害)。
CONNECTION_OPTIONS = "-c default_transaction_read_only=on -c search_path=pg_catalog"
# 任一鍵出現在 intent 即代表呼叫端試圖夾帶 raw SQL / 授權升級 / 寫入權 / 成員資格 → fail-closed。
FORBIDDEN_INTENT_KEYS = frozenset({
    "raw_sql", "sql", "statements", "privileges", "extra_privileges",
    "with_grant_option", "grant_option", "role_membership", "member_of",
    "grantor", "writer", "writer_role", "superuser", "is_superuser",
    "login", "password", "migration", "alter_system",
})
# 觀察端寫入拒絕碼(42501)、憑證升級拒絕碼(28P01/28000)——重用 S1.3 常量(EXERCISED,非僅 import)。
WRITE_DENIAL_SQLSTATES = acl.READER_WRITE_DENIAL_SQLSTATES  # {"42501"}
CREDENTIAL_DENIAL_SQLSTATES = acl.CREDENTIAL_DENIAL_SQLSTATES  # {"28P01","28000"}
# SET ROLE 升級拒絕同屬 insufficient_privilege(42501)。
SET_ROLE_DENIAL_SQLSTATES = frozenset({"42501", "0LP01", "42P01"})
# uid/role label 不得命名的特權身分 token(鏡像 S1.3 ``_PRIVILEGED_IDENTITY_TOKENS``)。
_PRIVILEGED_IDENTITY_TOKENS = ("root", "superuser", "sudo", "wheel", "admin")


# ── W0a(F4)生產 intent 必須觀察的 read-only 依賴關係(design S2.4 §2.2):S2.1 需觀 consumer-session 狀態 ──
REQUIRED_PRODUCTION_OBSERVED_SCHEMA = "learning"
REQUIRED_PRODUCTION_OBSERVED_RELATION = "alr_consumer_events"

SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token", "credential_assignment", "github_token", "postgres_dsn_credentials",
)


class PgObserverReadOnlyError(PgObserverBootstrapError):
    """Raised when a negative probe did not observe its required denial (not truly read-only)."""


# --------------------------------------------------------------------------- #
# typed production-driver protocol (fixed operations only; NEVER raw SQL / DSN)
# --------------------------------------------------------------------------- #
class ObserverBootstrapProductionDriver(Protocol):
    """Typed, fixed-operation production driver for the reachable S2.0 apply path.

    誠實界線:此 protocol 只暴露**固定操作**方法,呼叫端**永不**遞交 raw SQL、DSN 字串或
    admin 憑證——``create_read_only_observer`` 消費的是由 ``generate_observer_grant_sql`` 結構化
    allowlist 投影出的 grant_set(``CREATE ROLE ... NO*`` + ``GRANT USAGE``/``GRANT SELECT``),
    driver 內部持有一個**不可序列化、僅本機**的 PG admin handle。具體 Linux 實作是 authority-locked
    且 dormant 的:只有在後續 S2.0 EFFECT session 於真主機上供給 handle 時才開真連線。W0a 只 land
    這個 protocol + reachable 閘,W0a **絕不**在生產跑它(源碼/測試路徑 driver 恆為 None)。

    ``evidence_class`` W0a 後降級為**第一道 cheap filter**(非最終 unlock):一個回報 ``LOCAL_REPRODUCIBLE``/
    ``STRUCTURAL_ONLY`` 的 simulation/disposable driver 於請求 attestation **之前**即被擋下。真正解鎖
    ``APPLIED`` 的是 ``signed_apply_attestation`` 回傳、且通過 :func:`validate_apply_attestation`(T1 簽章 +
    trust-root 綁定、T2 reobserved==applied、T5 trusted-clock 窗)的**簽章 attestation**;bare
    ``evidence_class`` 屬性不再足以令 ``production_apply_performed=true``。
    """

    evidence_class: str

    def observer_role_present(self, *, role: str) -> bool:
        """Read-only catalog probe: does the observer role already exist? (pre-state guard)."""
        ...

    def signed_apply_attestation(
        self, *, intent: dict[str, Any], applied_grant_set_digest: str, reobserved_digest: str
    ) -> dict[str, Any]:
        """Return ``{"attestation": <pg_observer_bootstrap_apply_attestation_v1 object>,
                    "signature": <raw ASCII-armored SSHSIG bytes>}``.

        The attestation binds the exact intent identity, the applied catalog digest, the DISTINCT
        verifier's ``reobserved_digest`` (== applied), ``evidence_class=PLATFORM_ATTESTED``, and a
        trusted-host-signed timestamp; it is signed by the §9.1 trust-root key family under the
        observer-bootstrap-apply namespace.  Only a real trusted host that holds the off-repo
        private key can produce a signature that verifies against the pinned ``ATTESTOR_PUBLIC_KEY``.
        """
        ...

    def observe_acl_state(self, *, role: str, schema: str, relations: list[str]) -> str:
        """Read-only observation → the ``observer_role_acl_state_digest`` projection digest."""
        ...

    def create_read_only_observer(self, *, grant_set: dict[str, Any]) -> None:
        """Drive the fixed structured CREATE ROLE + GRANT USAGE/SELECT (grant_set only; no caller SQL)."""
        ...

    def independent_read_only_proof(self, *, grant_set: dict[str, Any]) -> dict[str, Any]:
        """The DISTINCT verifier node re-observes the provisioned observer and returns
        ``{read_only_proof, reobserved_digest, verifier_capture_digest}`` — the platform-attested
        denial evidence (write->42501, SET ROLE->42501, credential->28P01, harmless search_path)."""
        ...

    def compensate(self, *, grant_set: dict[str, Any]) -> None:
        """Ownership-aware failure/compensation rollback ONLY (a successful production apply leaves
        the observer provisioned for S2.1; this is never used to undo an attested success)."""
        ...


def _is_attested_production_target_host(target_host: Any) -> bool:
    """Structural step-2 guard: a production apply must name a non-Mac/non-dev/non-loopback host.

    誠實界線:離線源碼**無法**真正背書「我此刻正跑在該 Linux 主機上」(那是平台層事實);真主機身分
    由 operator SSHSIG(綁 exact target_host)+ driver 只存在於真主機 + 平台背書共同保證。此處只做
    結構性理智檢查,擋掉明顯的 Mac/dev/loopback 標記,令 Mac/non-target 於 step 2 即 typed 非成功。
    """

    if not isinstance(target_host, str) or not target_host.strip():
        return False
    lowered = target_host.lower()
    return not any(marker in lowered for marker in _NON_PRODUCTION_HOST_MARKERS)


# --------------------------------------------------------------------------- #
# canonical digest helpers (reuse central validator; local bytes for SSHSIG)
# --------------------------------------------------------------------------- #
canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


# --------------------------------------------------------------------------- #
# secret scan (fail-closed)
# --------------------------------------------------------------------------- #
def _result_secret_scan_view(result: dict[str, Any]) -> dict[str, Any]:
    # operator_signature_pem 是**公開的** SSHSIG(非機密):其 base64 body 理論上可能以 "auth=" padding
    # 收尾而誤觸 secret 正則。它是受控欄位(來自 operator 簽章 bytes),故 build 與 validate 一致地
    # 把它排除在 secret 掃描之外,避免對合法 receipt 造成 flaky false-positive 拒絕。
    # FIX-7(E2 P3):result schema 對 operator_signature_pem 釘死完整 SSHSIG armor pattern
    # (header+body+END footer);DSN 子形(含 ':'/'@' 等非 body-charset 字元)在 schema 階段即被 pattern 拒。
    # FIX-10(E2 P2 更正):**僅** armor pattern 不足以令此排除安全——其 body charset [A-Za-z0-9+/=\n] 仍
    # 允許可讀 plaintext(如 "password=hunter2"/"pgpassword=…"/"bearer …"),而這些正是 SECRET_LIKE_RE 認得、
    # 卻因本排除而不被掃到的形。故 build 與 validate 皆額外要求 operator_signature_pem 的 armor body 必為
    # 嚴格標準 base64(見 _operator_signature_pem_body_is_strict_base64);FIX-11(E2 P2 根因)更把 validate
    # 側此檢查移出 APPLIED 分支、對任何非 None 字串**無條件**生效(不再僅限 APPLIED;build 兩條路徑本就以
    # _guard_operator_signature_pem_body 對稱把關)。嚴格 base64 一旦成立,所有可讀 plaintext 機密形
    # (credential_assignment / auth_scheme_token / DSN)在結構上皆不可能搭載
    # ——唯一能搭載的是 base64-**編碼**後的 bytes(非可讀 plaintext,落在既有離線捏造邊界內,非 plaintext
    # 序列化通道),故此 secret-scan 排除**可證安全**,絕非放行機密的破口。
    # W0a(§4):apply_attestation_signature_pem 是**另一份公開的** SSHSIG(非機密),其 armor body 亦可能誤觸
    # secret 正則,故與 operator_signature_pem 一致排除於 secret 掃描之外;兩者皆另以嚴格 base64 body 護欄
    # (build + validate)無條件把關,故此排除可證安全(不可搭載可讀 plaintext 機密)。
    return {
        k: v for k, v in result.items()
        if k not in {"operator_signature_pem", "apply_attestation_signature_pem"}
    }


def _names_privileged_identity(label: Any) -> bool:
    # 鏡像 S1.3:label 命名 root/superuser/sudo/wheel/admin 一律視為特權身分(即使宣稱 NOLOGIN)。
    if not isinstance(label, str):
        return False
    lowered = label.lower()
    return any(token in lowered for token in _PRIVILEGED_IDENTITY_TOKENS)


def _safe_ident(name: Any) -> str:
    # 重用 S1.5 ``_pg_ident`` 白名單(^[a-z_][a-z0-9_]*$),把 ComponentEffectError 轉為本模組錯誤。
    try:
        return ce._pg_ident(name)
    except ce.ComponentEffectError as exc:  # noqa: PERF203
        raise PgObserverBootstrapError(f"unsafe SQL identifier: {name!r}") from exc


# --------------------------------------------------------------------------- #
# structured grant-set allowlist (enum-selected; NEVER caller raw SQL)
# --------------------------------------------------------------------------- #
def generate_observer_grant_sql(intent: Any) -> dict[str, Any]:
    """Project ONE exact minimal read-only observer grant set from a STRUCTURED intent.

    Fail-closed by construction: the only admissible ``grant_set_selector`` is
    ``observer_read_only_v1``; identifiers pass the S1.5 ``_pg_ident`` allowlist;
    the role/schema/relation labels must not name a privileged identity; auth is
    peer/ident local (no password ingress).  Any caller raw SQL, migration,
    writer/superuser role, role membership, ``WITH GRANT OPTION`` or other
    over-grant marker key is REJECTED (raises).  The returned SQL is exactly:
    ``CREATE ROLE <obs> NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION
    NOBYPASSRLS`` + ``GRANT USAGE ON SCHEMA <observed>`` + ``GRANT SELECT`` on
    exactly the observed relations, with the connection pinned read-only /
    pg_catalog.
    """

    if not isinstance(intent, dict):
        raise PgObserverBootstrapError("observer intent must be an object")
    if intent.get("grant_set_selector") != OBSERVER_GRANT_SET_SELECTOR:
        raise PgObserverBootstrapError(
            f"grant_set_selector must be {OBSERVER_GRANT_SET_SELECTOR!r}; "
            "no broader / caller-defined grant set is admissible"
        )
    forbidden = sorted(FORBIDDEN_INTENT_KEYS & set(intent))
    if forbidden:
        raise PgObserverBootstrapError(
            "observer intent carries forbidden over-grant / raw-SQL keys: " + ", ".join(forbidden)
        )
    if intent.get("auth_mapping") not in OBSERVER_AUTH_METHODS:
        raise PgObserverBootstrapError(
            "observer auth_mapping must be peer/ident local "
            f"(one of {sorted(OBSERVER_AUTH_METHODS)}); no password ingress"
        )
    role = intent.get("observer_role")
    schema = intent.get("observed_schema")
    relations = intent.get("observed_relations")
    if not isinstance(relations, list) or not relations:
        raise PgObserverBootstrapError("observer intent must observe at least one relation")
    for label in (role, schema, *relations):
        _safe_ident(label)
        if _names_privileged_identity(label):
            raise PgObserverBootstrapError(f"observer identifier names a privileged identity: {label!r}")

    role_q = _safe_ident(role)
    schema_q = _safe_ident(schema)
    grant_select = [
        f"GRANT SELECT ON {schema_q}.{_safe_ident(rel)} TO {role_q}" for rel in relations
    ]
    revoke = [f"REVOKE ALL ON {schema_q}.{_safe_ident(rel)} FROM {role_q}" for rel in relations]
    revoke.append(f"REVOKE ALL ON SCHEMA {schema_q} FROM {role_q}")
    grant_set = {
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "role": role,
        "schema": schema,
        "relations": list(relations),
        "auth_mapping": intent.get("auth_mapping"),
        "create_role": f"CREATE ROLE {role_q} {_ROLE_ATTRIBUTE_CLAUSE}",
        # FIX-C3(Codex P2):CONNECTION_OPTIONS 原本只是描述性資料,從未施加到角色,故 observer 角色實際
        # 沒有唯讀/pg_catalog 約束。此處把該策略釘成 **role-level** 設定:ALTER ROLE SET(值為固定常量,
        # 非呼叫端 SQL;角色以 _safe_ident 引號化),令廣告的 least-privilege 連線策略成為角色持久設定。
        "alter_role_settings": [
            f"ALTER ROLE {role_q} SET default_transaction_read_only = on",
            f"ALTER ROLE {role_q} SET search_path = pg_catalog",
        ],
        "grant_usage": f"GRANT USAGE ON SCHEMA {schema_q} TO {role_q}",
        "grant_select": grant_select,
        "revoke": revoke,
        "drop_role": f"DROP ROLE IF EXISTS {role_q}",
        "connection_options": CONNECTION_OPTIONS,
    }
    _guard_no_secret(grant_set)
    return grant_set


def grant_set_digest(grant_set: dict[str, Any]) -> str:
    return canonical_digest(grant_set)


# --------------------------------------------------------------------------- #
# real structured SQL operators (disposable cluster; reuse S1.5 _pg_ident/state_digest)
# --------------------------------------------------------------------------- #
def observer_role_acl_state_digest(cursor: Any, *, role: str, schema: str, relations: list[str]) -> str:
    """Digest the observer role + its per-relation grant catalog projection.

    Reuses S1.5 ``pg_role_acl_state_digest`` per relation (a real catalog read); an
    absent role yields a stable "absent" projection, so pre(absent) != applied(present)
    and post(absent after rollback) == pre.
    """

    per_relation = {
        rel: ce.pg_role_acl_state_digest(cursor, role=role, schema=schema, table=rel)
        for rel in sorted(relations)
    }
    return canonical_digest({"role": role, "schema": schema, "relations": per_relation})


def observer_bootstrap_apply(
    cursor: Any, *, grant_set: dict[str, Any], on_step: Callable[[str], None] | None = None
) -> None:
    """Real CREATE ROLE (all forbidden attrs absent) + GRANT USAGE + GRANT SELECT apply.

    ``on_step`` is a test-only hook (mirrors S1.5's fail-closed toggles): it is called
    after each committed step so a disposable test can inject a mid-apply failure and
    prove the rollback restores pre == post.
    """

    cursor.execute(grant_set["create_role"])
    if on_step is not None:
        on_step("create_role")
    # FIX-C3(Codex P2):create_role 後真的施加連線層唯讀約束(role-level ALTER ROLE SET),令
    # default_transaction_read_only=on / search_path=pg_catalog 成為角色持久設定(存於 pg_db_role_setting)。
    # rollback 無需額外步驟:角色恆為本次新建(FIX-1 在 apply 前拒絕既存角色),rollback DROP ROLE 時這些 SET
    # 隨角色一併消滅(設定綁在角色上,角色不存在即設定不存在),故不會殘留孤兒設定。
    for statement in grant_set["alter_role_settings"]:
        cursor.execute(statement)
    if on_step is not None:
        on_step("alter_role_settings")
    cursor.execute(grant_set["grant_usage"])
    if on_step is not None:
        on_step("grant_usage")
    for index, statement in enumerate(grant_set["grant_select"]):
        cursor.execute(statement)
        if on_step is not None:
            on_step(f"grant_select:{index}")


def observer_role_present(cursor: Any, *, role: str) -> bool:
    """Real catalog read: does the observer role already exist in ``pg_roles``?"""

    cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
    return cursor.fetchone() is not None


def observer_bootstrap_rollback(cursor: Any, *, grant_set: dict[str, Any]) -> None:
    """Real REVOKE ALL + DROP ROLE rollback; partial-failure safe (role-existence guarded)."""

    if not observer_role_present(cursor, role=grant_set["role"]):
        return  # CREATE ROLE never committed; nothing to roll back
    for statement in grant_set["revoke"]:
        cursor.execute(statement)
    cursor.execute(grant_set["drop_role"])


# --------------------------------------------------------------------------- #
# read-only denial probes (distinct verifier connects AS the observer)
# --------------------------------------------------------------------------- #
def _rollback_quietly(cursor: Any) -> None:
    connection = getattr(cursor, "connection", None)
    if connection is not None:
        try:
            connection.rollback()
        except Exception:  # pragma: no cover - best effort  # noqa: BLE001
            pass


def _observe_denial(cursor: Any, sql: str) -> str:
    # 執行預期會被拒絕的敘述;回傳觀察到的 SQLSTATE,未被拒即致命(refuse)。
    try:
        cursor.execute(sql)
    except Exception as exc:  # noqa: BLE001 - psycopg2.Error carries pgcode
        pgcode = getattr(exc, "pgcode", None)
        _rollback_quietly(cursor)
        if pgcode is None:
            raise
        return str(pgcode)
    _rollback_quietly(cursor)
    raise PgObserverReadOnlyError(f"expected denial but statement succeeded: {sql}")


def probe_observer_write_denied(cursor: Any, *, schema: str, relation: str) -> dict[str, Any]:
    """Attempt a write as the observer; require an insufficient-privilege denial (42501)."""

    attempted = f"DELETE FROM {_safe_ident(schema)}.{_safe_ident(relation)}"
    return {"attempted": attempted, "observed_sqlstate": _observe_denial(cursor, attempted), "verdict": "DENIED"}


def probe_observer_set_role_denied(cursor: Any, *, target_role: str) -> dict[str, Any]:
    """Attempt SET ROLE to a writer/superuser; require an escalation denial (42501)."""

    attempted = f"SET ROLE {_safe_ident(target_role)}"
    return {"attempted": attempted, "observed_sqlstate": _observe_denial(cursor, attempted), "verdict": "DENIED"}


def probe_observer_search_path_reset_harmless(
    cursor: Any, *, schema: str, relation: str
) -> dict[str, Any]:
    """Reset the session search_path (allowed, harmless) and confirm a qualified read still works.

    Unlike a persistent hijack, a session-local ``SET search_path`` is harmless: every
    allowlisted read is schema-qualified, so the observer cannot escalate by moving the
    search_path.  Records the effective search_path after the reset as evidence.
    """

    cursor.execute("SET search_path TO public")
    cursor.execute(f"SELECT 1 FROM {_safe_ident(schema)}.{_safe_ident(relation)} LIMIT 1")
    cursor.fetchall()
    cursor.execute("SELECT current_setting('search_path')")
    effective = cursor.fetchone()[0]
    return {
        "attempted": "SET search_path TO public",
        "effective_search_path": str(effective),
        "harmless": True,
        "queries_schema_qualified": True,
    }


def probe_credential_escalation_denied(
    connect_with_bad_credential: Callable[[], Any],
    *,
    attempted: str = "connect_with_escalated_credential",
) -> dict[str, Any]:
    """Attempt a connection with an escalated/invalid credential; require 28P01/28000."""

    try:
        connection = connect_with_bad_credential()
    except Exception as exc:  # noqa: BLE001 - any driver error is the denial
        sqlstate = acl.resolve_credential_denial_sqlstate(getattr(exc, "pgcode", None), str(exc))
        if sqlstate not in CREDENTIAL_DENIAL_SQLSTATES:
            raise PgObserverReadOnlyError(
                "credential escalation was not denied with invalid-authorization (28P01/28000)"
            ) from exc
        return {"attempted": attempted, "observed_sqlstate": sqlstate, "verdict": "DENIED"}
    try:
        connection.close()
    except Exception:  # pragma: no cover - best effort  # noqa: BLE001
        pass
    raise PgObserverReadOnlyError("escalated credential connected; the observer is not fail-closed")


# --------------------------------------------------------------------------- #
# intent builder + validator
# --------------------------------------------------------------------------- #
def build_pg_observer_bootstrap_intent(
    *,
    target_class: str,
    target_host: str,
    database: str,
    observer_role: str,
    observed_schema: str,
    observed_relations: list[str],
    socket_dir: str | None = None,
    loopback_host: str | None = None,
    port: int | None = None,
    endpoint_class: str = "unix_socket_allowlisted",
    auth_mapping: str = "pg_hba_ident_local",
    applier_node_id: str,
    postcheck_node_id: str,
    created_at: str,
    ttl_seconds: int,
    source_head: str,
    intent_id: str | None = None,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``pg_observer_bootstrap_intent_v1``."""

    if target_class not in TARGET_CLASSES:
        raise PgObserverBootstrapError(f"unrecognized target_class: {target_class!r}")
    if auth_mapping not in OBSERVER_AUTH_METHODS:
        raise PgObserverBootstrapError("auth_mapping must be peer/ident local (no password ingress)")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise PgObserverBootstrapError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if applier_node_id == postcheck_node_id:
        raise PgObserverBootstrapError("applier_node_id must differ from postcheck_node_id (applier != verifier)")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise PgObserverBootstrapError("source_head must be a 40-hex commit id")
    created = _parse_time(created_at)
    expires = created + timedelta(seconds=ttl_seconds)
    endpoint = {
        "endpoint_class": endpoint_class,
        "socket_dir": socket_dir,
        "loopback_host": loopback_host,
        "port": port,
    }
    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id or canonical_digest({
            "observer_role": observer_role, "database": database, "target_host": target_host,
            "created_at": created.isoformat(), "source_head": source_head,
        }),
        "target_class": target_class,
        "target_host": target_host,
        "endpoint": endpoint,
        "database": database,
        "observer_role": observer_role,
        "auth_mapping": auth_mapping,
        "observed_schema": observed_schema,
        "observed_relations": list(observed_relations),
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "ttl_seconds": ttl_seconds,
        "applier_node_id": applier_node_id,
        "postcheck_node_id": postcheck_node_id,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "source_head": source_head,
    }
    # 建構期即跑一次結構化 allowlist,任何 over-grant / raw SQL 立即 fail-closed。
    generate_observer_grant_sql(intent)
    _guard_no_secret(intent)
    intent["self_digest"] = intent_self_digest(intent)
    return intent


def validate_pg_observer_bootstrap_intent(intent: Any, *, now: str | None = None) -> list[str]:
    """Validate intent structure/integrity + the grant-set allowlist + time window."""

    if not isinstance(intent, dict):
        return ["observer bootstrap intent must be an object"]
    schema = _schema(str(INTENT_SCHEMA_PATH))
    errors = [
        f"observer bootstrap intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    if errors:
        return errors
    if intent.get("applier_node_id") == intent.get("postcheck_node_id"):
        errors.append("observer bootstrap intent applier_node_id must differ from postcheck_node_id")
    try:
        generate_observer_grant_sql(intent)
    except PgObserverBootstrapError as exc:
        errors.append(f"observer bootstrap intent grant set is inadmissible: {exc}")
    if _contains_secret_like(intent):
        errors.append("observer bootstrap intent carries secret-like content")
    if intent.get("self_digest") != intent_self_digest(intent):
        errors.append("observer bootstrap intent self_digest does not match canonical intent")
    try:
        created = _parse_time(intent["created_at"])
        expires = _parse_time(intent["expires_at"])
        if expires <= created:
            errors.append("observer bootstrap intent created_at must precede expires_at")
        if expires - created > timedelta(seconds=TTL_CEILING_SECONDS):
            errors.append("observer bootstrap intent TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not created <= current < expires:
                errors.append("observer bootstrap intent is outside its validity window")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap intent timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# rollback record builder + validator
# --------------------------------------------------------------------------- #
def build_pg_observer_bootstrap_rollback(
    *,
    intent: dict[str, Any],
    grant_set: dict[str, Any],
    pre_state_digest: str,
    post_state_digest: str,
    observer_absent: bool,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build one canonical ``pg_observer_bootstrap_rollback_v1`` (exact restoration crux)."""

    restored_exact = pre_state_digest == post_state_digest
    status = "RESTORED_EXACT" if (restored_exact and observer_absent) else "NOT_RESTORED"
    observed = _parse_time(observed_at)
    rollback: dict[str, Any] = {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "status": status,
        "intent_id": intent["intent_id"],
        "observer_role": intent["observer_role"],
        "database": intent["database"],
        "host": intent["target_host"],
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "revoke_statements": list(grant_set["revoke"]),
        "drop_statement": grant_set["drop_role"],
        "restored_exact": restored_exact,
        "observer_absent": bool(observer_absent),
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
    }
    _guard_no_secret(rollback)
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def validate_pg_observer_bootstrap_rollback(rollback: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(rollback, dict):
        return ["observer bootstrap rollback must be an object"]
    schema = _schema(str(ROLLBACK_SCHEMA_PATH))
    errors = [
        f"observer bootstrap rollback schema violation: {error}"
        for error in schema_subset_errors(rollback, schema, schema)
    ]
    if errors:
        return errors
    exact = rollback.get("pre_state_digest") == rollback.get("post_state_digest")
    if rollback.get("status") == "RESTORED_EXACT":
        if not exact:
            errors.append("RESTORED_EXACT requires pre_state_digest == post_state_digest")
        if rollback.get("restored_exact") is not True or rollback.get("observer_absent") is not True:
            errors.append("RESTORED_EXACT requires restored_exact and observer_absent to be true")
    else:
        if exact and rollback.get("observer_absent") is True:
            errors.append("NOT_RESTORED contradicts an exact restoration with an absent observer")
    if _contains_secret_like(rollback):
        errors.append("observer bootstrap rollback carries secret-like content")
    if rollback.get("self_digest") != artifact_self_digest(rollback):
        errors.append("observer bootstrap rollback self_digest is invalid")
    try:
        observed = _parse_time(rollback["observed_at"])
        expires = _parse_time(rollback["expires_at"])
        if not observed < expires:
            errors.append("observer bootstrap rollback observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("observer bootstrap rollback is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap rollback timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# independent postcheck builder + validator
# --------------------------------------------------------------------------- #
def _denial_ok(record: Any, allowed: frozenset[str]) -> bool:
    return (
        isinstance(record, dict)
        and record.get("verdict") == "DENIED"
        and SQLSTATE_RE.fullmatch(str(record.get("observed_sqlstate", "")))
        and str(record.get("observed_sqlstate")) in allowed
    )


def build_pg_observer_bootstrap_postcheck(
    *,
    intent: dict[str, Any],
    verifier_node: str,
    applier_node: str,
    reobserved_post_rollback_digest: str,
    read_only_proof: dict[str, Any],
    verifier_capture_digest: str,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the independent-verifier ``pg_observer_bootstrap_postcheck_v1``.

    Fail-closed: raises unless the observer's own read-only proof observed every
    required denial (write -> 42501, escalation denied, credential-escalation ->
    28P01/28000) and the search-path reset was harmless.  ``verifier_node`` must
    differ from ``applier_node`` (applier != independent verifier).
    """

    if verifier_node == applier_node:
        raise PgObserverBootstrapError("independent verifier node must differ from the applier node")
    if not DIGEST_RE.fullmatch(str(verifier_capture_digest)):
        raise PgObserverBootstrapError("verifier_capture_digest must be a sha256 digest")
    write = read_only_proof.get("write_denied") if isinstance(read_only_proof, dict) else None
    set_role = read_only_proof.get("set_role_denied") if isinstance(read_only_proof, dict) else None
    search_path = read_only_proof.get("search_path_reset_harmless") if isinstance(read_only_proof, dict) else None
    credential = read_only_proof.get("credential_escalation_denied") if isinstance(read_only_proof, dict) else None
    if not _denial_ok(write, WRITE_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("observer write was not denied with insufficient_privilege 42501")
    if not _denial_ok(set_role, SET_ROLE_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("observer SET ROLE escalation was not denied")
    if not _denial_ok(credential, CREDENTIAL_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("credential escalation was not denied with 28P01/28000")
    if not (isinstance(search_path, dict) and search_path.get("harmless") is True
            and search_path.get("queries_schema_qualified") is True):
        raise PgObserverReadOnlyError("search-path reset was not proven harmless")

    observed = _parse_time(observed_at)
    postcheck: dict[str, Any] = {
        "schema_version": POSTCHECK_SCHEMA_VERSION,
        "status": "PASS",
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "observer_role": intent["observer_role"],
        "database": intent["database"],
        "host": intent["target_host"],
        "source_head": intent["source_head"],
        "reobserved_post_rollback_digest": reobserved_post_rollback_digest,
        "restoration_confirmed": True,
        "read_only_proof": {
            "write_denied": {
                "attempted": str(write["attempted"]),
                "observed_sqlstate": str(write["observed_sqlstate"]),
                "verdict": "DENIED",
            },
            "set_role_denied": {
                "attempted": str(set_role["attempted"]),
                "observed_sqlstate": str(set_role["observed_sqlstate"]),
                "verdict": "DENIED",
            },
            "search_path_reset_harmless": {
                "attempted": str(search_path["attempted"]),
                "effective_search_path": str(search_path["effective_search_path"]),
                "harmless": True,
                "queries_schema_qualified": True,
            },
            "credential_escalation_denied": {
                "attempted": str(credential["attempted"]),
                "observed_sqlstate": str(credential["observed_sqlstate"]),
                "verdict": "DENIED",
            },
        },
        "verifier_capture_digest": verifier_capture_digest,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
    }
    _guard_no_secret(postcheck)
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck


def validate_pg_observer_bootstrap_postcheck(
    postcheck: Any, *, result: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    if not isinstance(postcheck, dict):
        return ["observer bootstrap postcheck must be an object"]
    schema = _schema(str(POSTCHECK_SCHEMA_PATH))
    errors = [
        f"observer bootstrap postcheck schema violation: {error}"
        for error in schema_subset_errors(postcheck, schema, schema)
    ]
    if errors:
        return errors
    if postcheck.get("verifier_node") == postcheck.get("applier_node"):
        errors.append("observer bootstrap postcheck verifier_node must differ from applier_node")
    proof = postcheck.get("read_only_proof", {})
    if postcheck.get("status") == "PASS":
        if not _denial_ok(proof.get("write_denied"), WRITE_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires the observer write to be denied 42501")
        if not _denial_ok(proof.get("set_role_denied"), SET_ROLE_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires SET ROLE escalation denied")
        if not _denial_ok(proof.get("credential_escalation_denied"), CREDENTIAL_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires credential escalation denied 28P01/28000")
        if postcheck.get("restoration_confirmed") is not True:
            errors.append("PASS postcheck requires restoration_confirmed")
    if _contains_secret_like(postcheck):
        errors.append("observer bootstrap postcheck carries secret-like content")
    if postcheck.get("self_digest") != artifact_self_digest(postcheck):
        errors.append("observer bootstrap postcheck self_digest is invalid")
    if isinstance(result, dict):
        # FIX-C1(Codex P2):把 postcheck 的**完整身分**綁死到 result,而非只綁 intent_id/applier/verifier。
        # intent_id 由呼叫端供給,單綁 intent_id 會讓「針對另一個 target、卻重用同一 intent_id」的偽造
        # postcheck 被接受。故額外要求 intent_digest / source_head 與三個 target 欄位(observer_role/database/
        # host)皆等於 result 攜帶者。註:postcheck 的 host 對應 result 的 target_host(欄位名不同、語意相同);
        # 其餘欄位 postcheck 與 result 同名。postcheck 這些欄位皆為 new-this-PR schema 既有欄位(無需新增)。
        for postcheck_field, result_field in (
            ("intent_id", "intent_id"),
            ("intent_digest", "intent_digest"),
            ("source_head", "source_head"),
            ("observer_role", "observer_role"),
            ("database", "database"),
            ("host", "target_host"),
        ):
            if postcheck.get(postcheck_field) != result.get(result_field):
                errors.append(f"observer bootstrap postcheck {postcheck_field} is not bound to the result")
        if postcheck.get("applier_node") != result.get("apply_actor_node"):
            errors.append("observer bootstrap postcheck applier_node is not the result apply actor")
        if postcheck.get("verifier_node") != result.get("independent_verifier_node"):
            errors.append("observer bootstrap postcheck verifier_node is not the result verifier")
    try:
        observed = _parse_time(postcheck["observed_at"])
        expires = _parse_time(postcheck["expires_at"])
        if not observed < expires:
            errors.append("observer bootstrap postcheck observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("observer bootstrap postcheck is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap postcheck timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# result builder + validator (+ the fail-closed pending result)
# --------------------------------------------------------------------------- #
def _redact_endpoint(endpoint: Any) -> dict[str, Any]:
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    return {
        "endpoint_class": endpoint.get("endpoint_class"),
        "socket_dir": endpoint.get("socket_dir"),
        "loopback_host": endpoint.get("loopback_host"),
        "port": endpoint.get("port"),
    }


def _base_result(intent: dict[str, Any], grant_set: dict[str, Any], *, apply_actor_node: str) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "target_class": intent["target_class"],
        "target_host": intent["target_host"],
        "endpoint": _redact_endpoint(intent.get("endpoint")),
        "database": intent["database"],
        "observer_role": intent["observer_role"],
        "auth_mapping": intent["auth_mapping"],
        "observed_schema": intent["observed_schema"],
        "observed_relations": list(intent["observed_relations"]),
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "grant_set_digest": grant_set_digest(grant_set),
        "apply_actor_node": apply_actor_node,
        "independent_verifier_node": intent["postcheck_node_id"],
        "source_head": intent["source_head"],
        # W0a additive:每個 builder 皆繼承這三個「恆存在」欄位的預設;唯生產 APPLIED path 帶簽章 attestation,
        # 唯 RECOVERY_REQUIRED path 把 recovery_required 設 true。其餘 status 一律 None/None/False。
        "apply_attestation": None,
        "apply_attestation_signature_pem": None,
        "recovery_required": False,
        "boundary": {
            "production_apply_performed": False,
            "production_running_attested": False,
            "load_verified": False,
            "nine_authorities_false": True,
        },
    }


def build_pending_result(
    intent: dict[str, Any],
    *,
    reason: str,
    now: str,
    apply_actor_node: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the typed ``EXTERNAL_VERIFICATION_PENDING`` result — never a fake success."""

    grant_set = generate_observer_grant_sql(intent)
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node or intent["applier_node_id"])
    result.update({
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "pre_state_digest": None,
        "applied_grant_set_digest": None,
        "independent_postcheck": None,
        "rollback_record": None,
        "operator_authorization": None,
        "operator_signature_pem": None,
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "completed_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": _plus_seconds(now, ttl_seconds),
        "ttl_seconds": ttl_seconds,
        "failure_reason": reason,
    })
    _guard_no_secret(result)
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_recovery_required_result(
    intent: dict[str, Any],
    *,
    reason: str,
    now: str,
    apply_actor_node: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the additive ``RECOVERY_REQUIRED`` result (W0a F2).

    Emitted ONLY when a failed production apply's compensation could **not** be confirmed
    (``driver.compensate`` raised OR the observer role is still present after compensate).  Unlike a
    "compensated" ``EXTERNAL_VERIFICATION_PENDING`` it honestly signals the observer role may persist
    in production and requires explicit operator recovery.  It is a failure (blocks S2.5, which admits
    only ``APPLIED_ROLLED_BACK_EXACT``): ``recovery_required=true``, ``STRUCTURAL_ONLY`` evidence, no
    postcheck/rollback/attestation, ``production_apply_performed=false``, nine authorities false.
    """

    grant_set = generate_observer_grant_sql(intent)
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node or intent["applier_node_id"])
    result.update({
        "status": "RECOVERY_REQUIRED",
        "pre_state_digest": None,
        "applied_grant_set_digest": None,
        "independent_postcheck": None,
        "rollback_record": None,
        "operator_authorization": None,
        "operator_signature_pem": None,
        "apply_attestation": None,
        "apply_attestation_signature_pem": None,
        "recovery_required": True,
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "completed_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": _plus_seconds(now, ttl_seconds),
        "ttl_seconds": ttl_seconds,
        "failure_reason": reason,
    })
    _guard_no_secret(result)
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_pg_observer_bootstrap_result(
    *,
    intent: dict[str, Any],
    grant_set: dict[str, Any],
    status: str,
    pre_state_digest: str,
    applied_grant_set_digest: str | None,
    postcheck: dict[str, Any] | None,
    rollback_record: dict[str, Any] | None,
    operator_authorization: dict[str, Any],
    operator_signature: bytes,
    apply_actor_node: str,
    started_at: str,
    completed_at: str,
    failure_reason: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build a canonical ``pg_observer_bootstrap_result_v1`` for a real disposable apply."""

    if status not in {"APPLIED_ROLLED_BACK_EXACT", "ROLLED_BACK_INTERRUPTED", "NOT_RESTORED_FAILED", "FAILED"}:
        raise PgObserverBootstrapError(f"unrecognized applied result status: {status!r}")
    if intent.get("target_class") != DISPOSABLE_TARGET_CLASS:
        raise PgObserverBootstrapError("a real applied result is only emitted for a disposable_local target")
    if status == "APPLIED_ROLLED_BACK_EXACT":
        if not isinstance(postcheck, dict) or not isinstance(rollback_record, dict):
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires an embedded postcheck and rollback record")
        if rollback_record.get("post_state_digest") != pre_state_digest:
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires rollback post == pre (exact restoration)")
        if applied_grant_set_digest is None or applied_grant_set_digest == pre_state_digest:
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires the apply to change catalog state")
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node)
    completed = _parse_time(completed_at)
    result.update({
        "status": status,
        "pre_state_digest": pre_state_digest,
        "applied_grant_set_digest": applied_grant_set_digest,
        "independent_postcheck": postcheck,
        "rollback_record": rollback_record,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(operator_signature).decode("ascii"),
        "evidence_class": "LOCAL_REPRODUCIBLE" if status == "APPLIED_ROLLED_BACK_EXACT" else "STRUCTURAL_ONLY",
        "started_at": _parse_time(started_at).isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": (completed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None if status == "APPLIED_ROLLED_BACK_EXACT" else (
            failure_reason or "observer apply did not complete an exact rollback"
        ),
    })
    # SSHSIG bytes 為公開簽章(非機密);掃描整份 result(排除公開簽章欄位)確保沒有 DSN/密碼被夾帶。
    # FIX-10(E2 P2):公開簽章欄位另以 strict-base64 body 護欄把關,確保 build 不會 emit 一份 armor 外殼
    # 合法但 body 夾帶可讀 plaintext 的簽章;其餘欄位再走(排除該欄的)secret 掃描,確保無 DSN/密碼夾帶。
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_pg_observer_bootstrap_applied_result(
    *,
    intent: dict[str, Any],
    grant_set: dict[str, Any],
    pre_state_digest: str,
    applied_grant_set_digest: str,
    postcheck: dict[str, Any],
    operator_authorization: dict[str, Any],
    operator_signature: bytes,
    apply_attestation: dict[str, Any],
    apply_attestation_signature: bytes,
    apply_actor_node: str,
    evidence_class: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the production ``APPLIED`` result (``production_apply_performed=true``).

    Emitted ONLY by the reachable production gate when the real Linux host driver returns
    ``PLATFORM_ATTESTED`` apply evidence AND a trusted-host-signed ``apply_attestation`` that passed
    :func:`validate_apply_attestation`.  Unlike the disposable proof the observer role is left
    provisioned (no rollback record) for S2.1; the nine authorities + ``production_running_attested``/
    ``load_verified`` stay false.  ``started_at``/``completed_at``/``evidence_expires_at`` are derived
    from the **signed** ``trusted_host_time`` (trusted-anchored, not caller-anchored).  Never emitted in
    the source lane (driver is None on Mac/tests) and never by a simulation driver (non-attested).
    """

    if intent.get("target_class") != PRODUCTION_TARGET_CLASS:
        raise PgObserverBootstrapError("an APPLIED result is only emitted for a production target")
    if evidence_class != PRODUCTION_APPLIED_EVIDENCE_CLASS:
        raise PgObserverBootstrapError(
            "APPLIED requires PLATFORM_ATTESTED driver evidence (a simulation/disposable driver cannot forge it)"
        )
    if not isinstance(apply_attestation, dict):
        raise PgObserverBootstrapError("APPLIED requires a trusted-host apply attestation object")
    if not isinstance(postcheck, dict):
        raise PgObserverBootstrapError("APPLIED requires the distinct verifier's independent postcheck")
    if applied_grant_set_digest is None or applied_grant_set_digest == pre_state_digest:
        raise PgObserverBootstrapError("APPLIED requires the apply to change catalog state (applied != pre)")
    if not (
        apply_attestation.get("reobserved_digest")
        == apply_attestation.get("applied_grant_set_digest")
        == applied_grant_set_digest
    ):
        raise PgObserverBootstrapError(
            "APPLIED requires the attestation reobserved == applied == the applied catalog digest (T2)"
        )
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node)
    result["boundary"]["production_apply_performed"] = True
    # trusted-anchored receipt bookkeeping:started/completed/evidence_expires 皆由簽章 trusted_host_time 導出。
    completed = _parse_time(apply_attestation["trusted_host_time"])
    result.update({
        "status": "APPLIED",
        "pre_state_digest": pre_state_digest,
        "applied_grant_set_digest": applied_grant_set_digest,
        "independent_postcheck": postcheck,
        "rollback_record": None,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(operator_signature).decode("ascii"),
        "apply_attestation": apply_attestation,
        "apply_attestation_signature_pem": bytes(apply_attestation_signature).decode("ascii"),
        "recovery_required": False,
        "evidence_class": PRODUCTION_APPLIED_EVIDENCE_CLASS,
        "started_at": completed.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": (completed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None,
    })
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_apply_attestation_signature_pem_body(result.get("apply_attestation_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


def validate_pg_observer_bootstrap_result(result: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(result, dict):
        return ["observer bootstrap result must be an object"]
    schema = _schema(str(RESULT_SCHEMA_PATH))
    errors = [
        f"observer bootstrap result schema violation: {error}"
        for error in schema_subset_errors(result, schema, schema)
    ]
    if errors:
        return errors
    status = result.get("status")
    if result.get("apply_actor_node") == result.get("independent_verifier_node"):
        errors.append("observer bootstrap result apply actor must differ from the independent verifier")
    # 邊界:九 authority / running attested / load verified 恆 false;production_apply_performed 唯有
    # APPLIED(真 Linux driver + PLATFORM_ATTESTED)才為 true,其餘 status 一律 false。
    boundary = result.get("boundary", {})
    expect_production_apply = status == "APPLIED"
    if boundary.get("nine_authorities_false") is not True:
        errors.append("observer bootstrap result boundary must keep the nine authorities false")
    if boundary.get("production_apply_performed") is not expect_production_apply:
        errors.append(
            "observer bootstrap result production_apply_performed must be True only for APPLIED and False otherwise"
        )
    # W0a(F2):recovery_required 唯 RECOVERY_REQUIRED status 才可為 true,其餘 status 一律 false。
    if bool(result.get("recovery_required")) is not (status == "RECOVERY_REQUIRED"):
        errors.append(
            "observer bootstrap result recovery_required must be True only for RECOVERY_REQUIRED and False otherwise"
        )
    if status == "APPLIED":
        # 生產 reachable apply:唯有真 Linux host driver + PLATFORM_ATTESTED 才可達此;離線 validator 只證
        # 結構/整合(不背書「真 apply 過」——平台背書屬 S2.0 EFFECT session,見模組 docstring 誠實界線)。
        if result.get("target_class") != PRODUCTION_TARGET_CLASS:
            errors.append("APPLIED requires a production target")
        if result.get("evidence_class") != PRODUCTION_APPLIED_EVIDENCE_CLASS:
            errors.append("APPLIED requires PLATFORM_ATTESTED evidence (never fabricated by a non-attested driver)")
        if result.get("rollback_record") is not None:
            errors.append("APPLIED leaves the observer provisioned; it carries no rollback record")
        if result.get("failure_reason") is not None:
            errors.append("APPLIED must not carry a failure_reason")
        applied_digest = result.get("applied_grant_set_digest")
        if applied_digest is None or applied_digest == result.get("pre_state_digest"):
            errors.append("APPLIED requires the apply to change catalog state (applied != pre)")
        errors.extend(validate_pg_observer_bootstrap_postcheck(result.get("independent_postcheck"), result=result, now=now))
        errors.extend(operator_authorization_binding_errors(
            result.get("operator_authorization"),
            intent_id=result.get("intent_id"),
            intent_digest=result.get("intent_digest"),
            source_head=result.get("source_head"),
        ))
        # W0a(§6):T2 offline mirror + 結構性 apply-attestation 綁定(F1 Option A;不做離線 SSHSIG 再驗)。
        postcheck = result.get("independent_postcheck") or {}
        if postcheck.get("reobserved_post_rollback_digest") != result.get("applied_grant_set_digest"):
            errors.append("APPLIED postcheck reobserved digest must equal the applied catalog digest (T2)")
        errors.extend(_apply_attestation_binding_errors(
            result.get("apply_attestation"),
            result.get("apply_attestation_signature_pem"),
            intent_id=result.get("intent_id"),
            intent_digest=result.get("intent_digest"),
            source_head=result.get("source_head"),
            applied_grant_set_digest=result.get("applied_grant_set_digest"),
            operator_authorization=result.get("operator_authorization"),
        ))
    if status == "EXTERNAL_VERIFICATION_PENDING":
        if result.get("independent_postcheck") is not None or result.get("rollback_record") is not None:
            errors.append("EXTERNAL_VERIFICATION_PENDING must not embed a postcheck or rollback record")
        if not (isinstance(result.get("failure_reason"), str) and result.get("failure_reason")):
            errors.append("EXTERNAL_VERIFICATION_PENDING requires a failure_reason")
    elif status == "RECOVERY_REQUIRED":
        # W0a(F2):生產 apply 補償無法確認 → 明確 residual failure;絕不冒充「已補償」pending。
        if result.get("recovery_required") is not True:
            errors.append("RECOVERY_REQUIRED requires recovery_required=true")
        if result.get("evidence_class") != "STRUCTURAL_ONLY":
            errors.append("RECOVERY_REQUIRED requires STRUCTURAL_ONLY evidence")
        if result.get("independent_postcheck") is not None or result.get("rollback_record") is not None:
            errors.append("RECOVERY_REQUIRED must not embed a postcheck or rollback record")
        if result.get("apply_attestation") is not None or result.get("apply_attestation_signature_pem") is not None:
            errors.append("RECOVERY_REQUIRED must not carry an apply attestation")
        if not (isinstance(result.get("failure_reason"), str) and result.get("failure_reason")):
            errors.append("RECOVERY_REQUIRED requires a failure_reason")
        if boundary.get("production_apply_performed") is not False:
            errors.append("RECOVERY_REQUIRED must keep production_apply_performed false")
    elif status == "APPLIED_ROLLED_BACK_EXACT":
        if result.get("target_class") != DISPOSABLE_TARGET_CLASS:
            errors.append("APPLIED_ROLLED_BACK_EXACT requires a disposable_local target")
        if result.get("evidence_class") != "LOCAL_REPRODUCIBLE":
            errors.append("APPLIED_ROLLED_BACK_EXACT requires LOCAL_REPRODUCIBLE evidence")
        errors.extend(validate_pg_observer_bootstrap_postcheck(result.get("independent_postcheck"), result=result, now=now))
        errors.extend(validate_pg_observer_bootstrap_rollback(result.get("rollback_record"), now=now))
        rollback = result.get("rollback_record") or {}
        if rollback.get("post_state_digest") != result.get("pre_state_digest"):
            errors.append("APPLIED_ROLLED_BACK_EXACT requires rollback post_state == result pre_state")
        if rollback.get("status") != "RESTORED_EXACT":
            errors.append("APPLIED_ROLLED_BACK_EXACT requires a RESTORED_EXACT rollback")
        postcheck = result.get("independent_postcheck") or {}
        if postcheck.get("reobserved_post_rollback_digest") != result.get("pre_state_digest"):
            errors.append("postcheck reobserved digest must equal the restored (pre == post) baseline")
        # FIX-5(E2 P2):APPLIED receipt 的 operator_authorization 必須是「結構良好 + 精確 intent 綁定」
        # 的物件(重用 AUTHORIZATION_FIELDS 契約),把 {"totally":"bogus"} 及任何 intent 不符的授權擋掉。
        # 這是**結構完整性**綁定,不是密碼學認證——真 SSHSIG 再驗留給 S2.0 EFFECT session(見 helper 註)。
        errors.extend(operator_authorization_binding_errors(
            result.get("operator_authorization"),
            intent_id=result.get("intent_id"),
            intent_digest=result.get("intent_digest"),
            source_head=result.get("source_head"),
        ))
    # grant_set_digest 必可由 intent 的結構化 allowlist 獨立重算。
    intent_shape = {
        "grant_set_selector": result.get("grant_set_selector"),
        "observer_role": result.get("observer_role"),
        "observed_schema": result.get("observed_schema"),
        "observed_relations": result.get("observed_relations"),
        "auth_mapping": result.get("auth_mapping"),
    }
    try:
        recomputed = grant_set_digest(generate_observer_grant_sql(intent_shape))
        if result.get("grant_set_digest") != recomputed:
            errors.append("observer bootstrap result grant_set_digest does not bind the structured allowlist")
    except PgObserverBootstrapError:
        errors.append("observer bootstrap result grant set is inadmissible")
    # FIX-11(E2 P2 根因收口):operator_signature_pem 的 strict-base64 body 護欄必須**無條件**對任何
    # 非 None 字串生效,不限 APPLIED status。FIX-10 誤把它置於 APPLIED_ROLLED_BACK_EXACT elif 內,
    # 使其餘 status(EXTERNAL_VERIFICATION_PENDING / FAILED / ROLLED_BACK_INTERRUPTED / NOT_RESTORED_FAILED)
    # 的偽造 receipt 能於此欄搭載可讀 plaintext 機密(如 "password=hunter2" / "pgpassword=…"):該欄被
    # _result_secret_scan_view 排除於下方 secret 掃描之外,central validator 又純委派(無獨立掃描)→ 機密
    # 會被序列化過中央閘。此處把檢查移出所有 status 分支,與 build 兩條路徑的 _guard_operator_signature_pem_body
    # (build 期 1144/1382)對稱,令任何 status/path 皆不可能於此欄搭載可讀 plaintext。None → isinstance False
    # → 跳過(PENDING 的 None 路徑不受影響)。此無條件檢查正是令下方 secret-scan 排除該欄位得以**可證安全**者。
    signature_pem = result.get("operator_signature_pem")
    if isinstance(signature_pem, str) and not _operator_signature_pem_body_is_strict_base64(signature_pem):
        errors.append(
            "operator_signature_pem body is not strict base64 (possible non-signature payload)"
        )
    # W0a(§4):apply_attestation_signature_pem 亦為公開 SSHSIG(secret 掃描排除此欄位)——同樣**無條件**要求
    # 其 armor body 為嚴格 base64,關閉「armor 外殼合法但 body 夾帶可讀 plaintext 機密」的同型破口(任何 status)。
    attestation_signature_pem = result.get("apply_attestation_signature_pem")
    if isinstance(attestation_signature_pem, str) and not _operator_signature_pem_body_is_strict_base64(attestation_signature_pem):
        errors.append(
            "apply_attestation_signature_pem body is not strict base64 (possible non-signature payload)"
        )
    if _contains_secret_like(_result_secret_scan_view(result)):
        errors.append("observer bootstrap result carries secret-like content")
    if result.get("self_digest") != artifact_self_digest(result):
        errors.append("observer bootstrap result self_digest is invalid")
    try:
        started = _parse_time(result["started_at"])
        expires = _parse_time(result["evidence_expires_at"])
        if not started <= expires:
            errors.append("observer bootstrap result started_at must precede evidence_expires_at")
        if now is not None and not started <= _parse_time(now) < expires:
            errors.append("observer bootstrap result evidence is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap result timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# the applier (production is REACHABLE but authority-locked; APPLIED needs a real
# host driver returning a trusted-host-SIGNED apply attestation — never source/tests)
# --------------------------------------------------------------------------- #
_RECOVERY_REQUIRED_REASON = (
    "production observer apply RECOVERY_REQUIRED: compensation was NOT confirmed "
    "(driver.compensate raised or the observer role is still present); the observer role may persist "
    "in production and requires explicit operator recovery; production_apply_performed stays false"
)


def _compensate_and_confirm(
    driver: "ObserverBootstrapProductionDriver", *, grant_set: dict[str, Any], role: str
) -> bool:
    """Compensate the throwaway/created state, then re-observe the observer role is ABSENT.

    Returns True (CONFIRMED gone) iff ``compensate`` did not raise AND a follow-up
    ``observer_role_present`` returns False.  A raising ``compensate`` or a still-present role (or a
    raising re-observation) returns False (NOT confirmed) — the caller then emits RECOVERY_REQUIRED
    instead of a misleading "compensated" pending (W0a T3).
    """

    try:
        driver.compensate(grant_set=grant_set)
    except Exception:  # noqa: BLE001 - a raising compensate is NOT a confirmed rollback
        return False
    try:
        return not driver.observer_role_present(role=role)
    except Exception:  # noqa: BLE001 - a raising re-observation cannot confirm absence (fail-closed)
        return False


def _apply_production_observer_bootstrap(
    intent: dict[str, Any],
    operator_authorization: Any,
    signature: Any,
    *,
    now: str,
    source_head: str,
    driver: "ObserverBootstrapProductionDriver | None",
    apply_actor_node: str,
) -> dict[str, Any]:
    """Reachable, fail-closed production gate (mirrors §6 order).

    Each step returns a typed non-success on failure; there is **zero mutation** before the driver
    call.  Steps 1 (intent schema/digests/idempotency) and the source_head==intent binding were
    already enforced by :func:`apply_observer_bootstrap` before this branch.

    2.  Linux target-host identity — Mac/dev/loopback -> ``EXTERNAL_VERIFICATION_PENDING`` (zero mutation);
    2.5 required production dependency relation — the intent must observe ``learning.alr_consumer_events``
        (design S2.4 §2.2); otherwise a typed ``EXTERNAL_VERIFICATION_PENDING`` with zero mutation,
        BEFORE any driver call (auth-independent policy reject of a structurally-valid intent);
    3.  a FRESH domain-separated operator SSHSIG over the exact intent (identity/namespace = §2.2) —
        missing/stale/wrong-namespace -> AUTHORIZATION_REJECTED-class ``EXTERNAL_VERIFICATION_PENDING``;
    4.  structured dependency pre-state — the exact read-only ``observer_read_only_v1`` grant set must
        project (pure/zero-mutation; the observer-absent DB check happens via the driver in step 6);
    5.  ``driver is None`` (Mac / source / tests / no host) -> ``EXTERNAL_VERIFICATION_PENDING`` (zero mutation);
    6-9. driver present: observe pre-state (observer must be ABSENT), drive the fixed structured
        create-role/grants, run the DISTINCT verifier's independent proof, gate T2 (reobserved==applied),
        first-filter the driver's ``evidence_class``, then require a trusted-host-SIGNED apply attestation
        that passes :func:`validate_apply_attestation` (T1 signature + trust-root, T2, T5 trusted-clock).
        ``APPLIED`` (``production_apply_performed=true``) emits ONLY when the signed attestation verifies.
        Any mutation that cannot be CONFIRMED compensated returns ``RECOVERY_REQUIRED`` (never a
        misleading "compensated" pending, never a stranded role reported as gone).
    """

    # step 2 — attested Linux target-host identity (Mac/non-target -> typed non-success, zero mutation).
    if not _is_attested_production_target_host(intent.get("target_host")):
        return build_pending_result(
            intent,
            reason=(
                "production observer apply requires the attested Linux target host; this environment "
                "is not the S2.0 production target (zero mutation)"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )
    # step 2.5 — required production dependency relation (W0a T4; auth-independent, zero mutation, pre-driver).
    observed_schema = intent.get("observed_schema")
    relations = intent.get("observed_relations") or []
    if observed_schema != REQUIRED_PRODUCTION_OBSERVED_SCHEMA or REQUIRED_PRODUCTION_OBSERVED_RELATION not in relations:
        return build_pending_result(
            intent,
            reason=(
                "production observer intent OMITS the required read-only dependency "
                "learning.alr_consumer_events (design S2.4 §2.2); refusing to invoke the driver"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )
    # step 3 — a fresh domain-separated operator SSHSIG over the exact intent (AUTHORIZATION_REJECTED class).
    valid, reason = _operator_authorization_is_valid(
        operator_authorization, signature, intent=intent, source_head=source_head, now=now
    )
    if not valid:
        return build_pending_result(
            intent,
            reason="production observer apply AUTHORIZATION_REJECTED: " + reason,
            now=now,
            apply_actor_node=apply_actor_node,
        )
    # step 4 — structured dependency pre-state: the exact read-only allowlist must project (zero mutation).
    grant_set = generate_observer_grant_sql(intent)
    # step 5 — no host production driver (Mac / source / tests): reachable gate present, nothing to run.
    if driver is None:
        return build_pending_result(
            intent,
            reason=(
                "production observer apply is reachable but authority-locked: no host production driver "
                "is present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )
    # steps 6-9 — driver-present interaction. The whole region is fail-closed: ANY failure after the
    # create is attempted (a raising create/proof/postcheck OR the APPLIED build raising) must
    # _compensate_and_confirm; a CONFIRMED-gone role keeps the honest "compensated" pending, an
    # UNCONFIRMED compensation (raised / role still present) returns RECOVERY_REQUIRED — never an
    # uncaught exception, never a stranded provisioned role reported as gone (W0a T3).
    role = intent["observer_role"]
    schema = intent["observed_schema"]
    relations = intent["observed_relations"]
    role_created = False
    try:
        # step 6 — read-only pre-state; the observer role must be ABSENT (no adoption/rotation).
        if driver.observer_role_present(role=role):
            return build_pending_result(
                intent,
                reason="observer role already exists; refusing to adopt or rotate a pre-existing role",
                now=now,
                apply_actor_node=apply_actor_node,
            )
        pre = driver.observe_acl_state(role=role, schema=schema, relations=relations)
        # step 7 — the driver drives the fixed structured operations (create role + grants); NO caller SQL/DSN.
        # From here any failure must compensate (a create may partially apply), so mark before the call.
        role_created = True
        driver.create_read_only_observer(grant_set=grant_set)
        applied = driver.observe_acl_state(role=role, schema=schema, relations=relations)
        # step 8 — the DISTINCT verifier node independently re-observes the provisioned observer's denials.
        proof = driver.independent_read_only_proof(grant_set=grant_set)
        reobserved = proof.get("reobserved_digest") if isinstance(proof, dict) else None
        # step 8a — T2 runtime gate: the verifier's reobserved digest must equal the applied catalog digest.
        if reobserved != applied:
            confirmed = _compensate_and_confirm(driver, grant_set=grant_set, role=role)
            if confirmed:
                return build_pending_result(
                    intent,
                    reason=(
                        "production observer apply verifier reobserved digest != applied (T2); "
                        "compensated; production_apply_performed stays false"
                    ),
                    now=now,
                    apply_actor_node=apply_actor_node,
                )
            return build_recovery_required_result(
                intent, reason=_RECOVERY_REQUIRED_REASON, now=now, apply_actor_node=apply_actor_node
            )
        # step 9a — FIRST FILTER (cheap): a non-attested simulation/disposable driver is rejected BEFORE
        # any attestation is requested (preserves the exact existing behaviour for _SimulationProductionDriver).
        if getattr(driver, "evidence_class", None) != PRODUCTION_APPLIED_EVIDENCE_CLASS:
            confirmed = _compensate_and_confirm(driver, grant_set=grant_set, role=role)
            if confirmed:
                return build_pending_result(
                    intent,
                    reason=(
                        "production observer apply driver evidence is not PLATFORM_ATTESTED "
                        f"(got {getattr(driver, 'evidence_class', None)!r}); production_apply_performed stays false"
                    ),
                    now=now,
                    apply_actor_node=apply_actor_node,
                )
            return build_recovery_required_result(
                intent, reason=_RECOVERY_REQUIRED_REASON, now=now, apply_actor_node=apply_actor_node
            )
        # step 9b — request the trusted-host-SIGNED apply attestation (opaque object + raw SSHSIG bytes).
        bundle = driver.signed_apply_attestation(
            intent=intent, applied_grant_set_digest=applied, reobserved_digest=reobserved
        )
        attestation = bundle.get("attestation") if isinstance(bundle, dict) else None
        attestation_signature = bundle.get("signature") if isinstance(bundle, dict) else None
        # step 9c — the REAL gate: verify the signed attestation (T1 signature + trust-root, T2, T5 clock).
        attestation_errors = validate_apply_attestation(
            attestation, attestation_signature, intent=intent,
            operator_authorization=operator_authorization, applied_grant_set_digest=applied,
        )
        if attestation_errors:
            confirmed = _compensate_and_confirm(driver, grant_set=grant_set, role=role)
            if confirmed:
                return build_pending_result(
                    intent,
                    reason=(
                        "production observer apply attestation invalid: "
                        + "; ".join(str(e) for e in attestation_errors[:2])
                        + "; compensated; production_apply_performed stays false"
                    ),
                    now=now,
                    apply_actor_node=apply_actor_node,
                )
            return build_recovery_required_result(
                intent, reason=_RECOVERY_REQUIRED_REASON, now=now, apply_actor_node=apply_actor_node
            )
        # step 9d — build the DISTINCT verifier's postcheck, trusted-anchored on the SIGNED trusted_host_time.
        trusted_completed = attestation["trusted_host_time"]
        postcheck = build_pg_observer_bootstrap_postcheck(
            intent=intent,
            verifier_node=intent["postcheck_node_id"],
            applier_node=apply_actor_node,
            reobserved_post_rollback_digest=reobserved,
            read_only_proof=proof.get("read_only_proof") if isinstance(proof, dict) else None,
            verifier_capture_digest=proof.get("verifier_capture_digest") if isinstance(proof, dict) else None,
            observed_at=trusted_completed,
        )
        # step 9e — attested success: leave the observer provisioned for S2.1 (no rollback) and emit APPLIED.
        return build_pg_observer_bootstrap_applied_result(
            intent=intent,
            grant_set=grant_set,
            pre_state_digest=pre,
            applied_grant_set_digest=applied,
            postcheck=postcheck,
            operator_authorization=operator_authorization,
            operator_signature=bytes(signature),
            apply_attestation=attestation,
            apply_attestation_signature=bytes(attestation_signature),
            apply_actor_node=apply_actor_node,
            evidence_class=PRODUCTION_APPLIED_EVIDENCE_CLASS,
        )
    except Exception as exc:  # noqa: BLE001 - any driver/postcheck/build failure fails closed
        if role_created:
            confirmed = _compensate_and_confirm(driver, grant_set=grant_set, role=role)
            if not confirmed:
                return build_recovery_required_result(
                    intent, reason=_RECOVERY_REQUIRED_REASON, now=now, apply_actor_node=apply_actor_node
                )
        return build_pending_result(
            intent,
            reason=(
                f"production observer apply interrupted and compensated: {exc}"
                if role_created
                else f"production observer apply preflight failed and fails closed: {exc}"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )


def apply_observer_bootstrap(
    intent: Any,
    operator_authorization: Any = None,
    signature: Any = None,
    *,
    now: str,
    source_head: str,
    disposable: Any = None,
    driver: "ObserverBootstrapProductionDriver | None" = None,
    postcheck: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    apply_fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Intent-derived observer-bootstrap applier — production apply is reachable but authority-locked.

    Returns a typed ``pg_observer_bootstrap_result_v1``.  Without a VALID operator SSHSIG over the
    exact intent+source_head it returns ``EXTERNAL_VERIFICATION_PENDING`` (NEVER a success).  A
    ``production`` target enters the reachable, fail-closed gate
    (:func:`_apply_production_observer_bootstrap`, mirroring §6): with ``driver=None`` (Mac / source
    / tests) it returns ``EXTERNAL_VERIFICATION_PENDING`` with **zero mutation**; only a real Linux
    host ``ObserverBootstrapProductionDriver`` returning ``PLATFORM_ATTESTED`` evidence may emit
    ``APPLIED`` (``production_apply_performed=true``).  For a ``disposable_local`` target with a
    valid SSHSIG and an injected throwaway-cluster ``disposable`` connection it runs the REAL
    structured SQL (apply -> rollback, exact restoration) and embeds the distinct verifier's
    ``postcheck``.  ``apply_fault`` is a test-only hook to inject a mid-apply failure
    (partial-failure rollback proof).
    """

    # FIX-6(E2 P3):先只驗「結構/整合/allowlist/TTL 上限」(now=None,**不含**當前有效窗)——
    # genuine malformed / invalid-structure intent 一律 raise(硬契約錯誤)。
    structural_errors = validate_pg_observer_bootstrap_intent(intent)
    if structural_errors:
        raise PgObserverBootstrapError("observer bootstrap intent is inadmissible: " + "; ".join(structural_errors[:3]))
    if not HEAD_RE.fullmatch(str(source_head)) or intent.get("source_head") != source_head:
        raise PgObserverBootstrapError("source_head must be a 40-hex id equal to the intent source head")
    apply_actor_node = intent["applier_node_id"]
    started_at = started_at or now
    completed_at = completed_at or now
    # FIX-6(E2 P3):結構有效但落在「當前有效窗」之外(例如 expired TTL / not-yet-valid)→ 依 PENDING
    # 合約 fail-closed(typed EXTERNAL_VERIFICATION_PENDING,非 raise)。此處刻意與上方 malformed-raise
    # 分離:now=None 只擋結構,now=now 只多擋有效窗,故不會把 malformed 與 stale-window 混為一談。
    # FIX-9(E2 #3):governance 供給的 now 若本身 malformed(無法 parse),window validator 會把它歸為
    # 非空錯誤而落入 build_pending_result,其內 _parse_time(now) 會逸出**裸 ValueError**。此處把該路徑
    # 唯一的 ValueError 來源(malformed now)比照 malformed-intent 硬合約轉為 typed PgObserverBootstrapError
    # (fail-closed);不讓未分類例外逸出,也不冒充「outside validity window」的 stale-window pending。
    # 註:此點之後才可能被走到的其他 build_pending_result 呼叫,皆以「now 已可 parse」為前提(malformed
    # now 必先在此被攔),故不需重複包裹。
    try:
        if validate_pg_observer_bootstrap_intent(intent, now=now):
            return build_pending_result(
                intent,
                reason="observer bootstrap intent is outside its current validity window (expired or not-yet-valid)",
                now=now,
                apply_actor_node=apply_actor_node,
            )
    except ValueError as exc:
        raise PgObserverBootstrapError(f"observer bootstrap now is malformed: {now!r}") from exc

    if intent["target_class"] == PRODUCTION_TARGET_CLASS:
        # 生產 reachable(但 authority-locked)閘:mirror §6 的固定順序;driver 為 None(Mac/源碼/測試)
        # 時於 step 5 回傳 EXTERNAL_VERIFICATION_PENDING 且**零變更**——reachable 閘已在,但無 driver 可執行。
        return _apply_production_observer_bootstrap(
            intent,
            operator_authorization,
            signature,
            now=now,
            source_head=source_head,
            driver=driver,
            apply_actor_node=apply_actor_node,
        )

    # ── disposable_local 邏輯證明路徑(SSHSIG → 注入的丟棄式叢集;順序不變) ──
    valid, reason = _operator_authorization_is_valid(
        operator_authorization, signature, intent=intent, source_head=source_head, now=now
    )
    if not valid:
        return build_pending_result(intent, reason=reason, now=now, apply_actor_node=apply_actor_node)
    if disposable is None:
        return build_pending_result(
            intent,
            reason=(
                "disposable_local logic proof requires an injected throwaway-cluster connection; none was provided"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )

    # disposable_local + 有效 SSHSIG + 注入的丟棄式叢集連線 → 真實結構化 SQL。
    grant_set = generate_observer_grant_sql(intent)
    role, schema, relations = intent["observer_role"], intent["observed_schema"], intent["observed_relations"]
    cursor = disposable.cursor()
    pre = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    # FIX-1(OPS F1):角色若「本來就存在」→ 在任何 DDL 之前 fail-closed。existence-guarded rollback
    # 無法分辨「本次 CREATE 的角色」與「原本就有的角色」;若貿然 apply→42710(duplicate_object)→
    # rollback,會把這個既存(非本次建立)的角色連同其權限一併 DROP。故此處在 apply 前就拒絕,
    # 絕不進入 apply/rollback,回傳 typed fail-closed pending(既存角色必存活)。
    if observer_role_present(cursor, role=role):
        return build_pending_result(
            intent,
            reason=(
                "observer role already exists; refusing to create or drop a pre-existing role"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )
    apply_ok = True
    applied: str | None = None
    interruption: str | None = None
    try:
        observer_bootstrap_apply(cursor, grant_set=grant_set, on_step=apply_fault)
        applied = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    except Exception as exc:  # noqa: BLE001 - a mid-apply failure must still roll back
        apply_ok = False
        interruption = f"observer apply interrupted before completion: {exc}"
    observer_bootstrap_rollback(cursor, grant_set=grant_set)
    post = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    observer_absent = post == pre

    rollback_record = build_pg_observer_bootstrap_rollback(
        intent=intent, grant_set=grant_set, pre_state_digest=pre,
        post_state_digest=post, observer_absent=observer_absent, observed_at=completed_at,
    )
    if apply_ok and post == pre and applied is not None and applied != pre:
        if not isinstance(postcheck, dict):
            raise PgObserverBootstrapError(
                "a disposable exact apply requires the distinct verifier's postcheck to embed"
            )
        if postcheck.get("applier_node") != apply_actor_node:
            raise PgObserverBootstrapError("embedded postcheck applier_node must equal the applier node")
        return build_pg_observer_bootstrap_result(
            intent=intent, grant_set=grant_set, status="APPLIED_ROLLED_BACK_EXACT",
            pre_state_digest=pre, applied_grant_set_digest=applied, postcheck=postcheck,
            rollback_record=rollback_record, operator_authorization=operator_authorization,
            operator_signature=bytes(signature), apply_actor_node=apply_actor_node,
            started_at=started_at, completed_at=completed_at,
        )
    # 部分失敗但已還原(observer 已消失,post == pre):誠實回報 ROLLED_BACK_INTERRUPTED(不假成功)。
    status = "ROLLED_BACK_INTERRUPTED" if (post == pre and observer_absent) else "NOT_RESTORED_FAILED"
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node)
    completed = _parse_time(completed_at)
    result.update({
        "status": status,
        "pre_state_digest": pre,
        "applied_grant_set_digest": applied,
        "independent_postcheck": None,
        "rollback_record": rollback_record,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(signature).decode("ascii"),
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _parse_time(started_at).isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": (completed + timedelta(seconds=EVIDENCE_TTL_SECONDS)).isoformat().replace("+00:00", "Z"),
        "ttl_seconds": EVIDENCE_TTL_SECONDS,
        "failure_reason": interruption or "observer apply did not complete an exact rollback",
    })
    # FIX-10(E2 P2):非精確路徑同樣先過 strict-base64 body 護欄再走 secret 掃描(build 永不 emit 一份
    # body 非 base64 的簽章欄位)。
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


# --------------------------------------------------------------------------- #
# closure binding (source-only; mirrors validate_target_host_effect_binding)
# --------------------------------------------------------------------------- #
def validate_pg_observer_bootstrap_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Closure admission for one observer-bootstrap effect: intent + OPS preflight + result
    + independent postcheck bound to the verifier's OWN governed command_capture_v2.

    SOURCE-only: this predicate is NOT wired into the live ``validate_deploy_effect_binding``
    dispatch and no ``route_task`` effect node is injected before the S2.0 EFFECT session;
    it exists so that session's closure can admit the exact three-way (result verifier
    capture digest == ops_postcheck capture digest == verifier command_capture_v2
    record_digest) cross-check with applier != verifier.
    """

    errors: list[str] = []
    matching = [
        (evidence_id, receipt) for evidence_id, receipt in valid_receipts.items()
        if isinstance(receipt, dict) and receipt.get("adapter_id") == ADAPTER_ID
    ]
    if len(matching) != 1:
        return ["observer bootstrap closure PASS requires exactly one observer-bootstrap effect receipt"]
    receipt_id, receipt = matching[0]

    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if not any(node.get("id") == ADAPTER_ID for node in effect_nodes):
        errors.append("observer bootstrap effect receipt is not routed to the exact adapter node")
    if receipt.get("status") != "APPLIED_ROLLED_BACK_EXACT":
        errors.append("observer bootstrap closure PASS requires an APPLIED_ROLLED_BACK_EXACT receipt")
    else:
        # FIX-5(E2 P2):APPLIED closure receipt 的 operator_authorization 必須結構良好且精確綁定其 intent
        # (結構完整性,不是密碼學認證——真 SSHSIG 再驗留給 S2.0 EFFECT session,見 helper 誠實界線註)。
        errors.extend(operator_authorization_binding_errors(
            receipt.get("operator_authorization"),
            intent_id=receipt.get("intent_id"),
            intent_digest=receipt.get("intent_digest"),
            source_head=receipt.get("source_head"),
        ))

    # 精確 intent 授權(claim_evidence,digest 綁定)。
    intent_source = f"{INTENT_SCHEMA_VERSION}:{receipt.get('intent_id')}"
    intent_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
    ]
    if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get("intent_digest"):
        errors.append("observer bootstrap effect receipt lacks exact intent authority")
    # OPS preflight fragment 必存在(intent + OPS preflight + result + independent postcheck)。
    if not fragments_by_node.get("ops_preflight"):
        errors.append("observer bootstrap closure requires an OPS preflight fragment")

    # 內嵌的獨立 postcheck:verifier != applier,且帶一個 bound verifier_capture_digest。
    postcheck = receipt.get("independent_postcheck") if isinstance(receipt.get("independent_postcheck"), dict) else None
    applier_node = receipt.get("apply_actor_node")
    receipt_verifier_digest = postcheck.get("verifier_capture_digest") if isinstance(postcheck, dict) else None
    verifier_capture_ev: dict[str, Any] | None = None
    if postcheck is None:
        errors.append("observer bootstrap closure requires the receipt's embedded independent postcheck")
    else:
        errors.extend(validate_pg_observer_bootstrap_postcheck(postcheck, result=receipt))
        if postcheck.get("verifier_node") == applier_node:
            errors.append("observer bootstrap postcheck verifier must differ from the applier node")
        if not DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
            errors.append("observer bootstrap postcheck lacks a bound verifier_capture_digest")

    # 第三份 evidence:獨立驗證者自己的 governed command_capture_v2(在 ops_postcheck fragment)。
    # 三方交叉:effect receipt 內嵌 postcheck 的 verifier_capture_digest == 該 evidence digest ==
    # 內嵌 command_capture_v2 的 record_digest;capturer node/role 與 applier 相異(applier != verifier)。
    fragment = fragments_by_node.get("ops_postcheck", {})
    cap_refs = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == "command_capture_v2"
    ]
    verifier_capture_record_ok = False
    if len(cap_refs) != 1:
        errors.append("observer bootstrap closure requires exactly one verifier command_capture_v2 in ops_postcheck")
    elif DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
        verifier_capture_ev = cap_refs[0]
        outer_digest_ok = verifier_capture_ev.get("digest") == receipt_verifier_digest
        if not outer_digest_ok:
            errors.append("observer bootstrap verifier capture digest is not the three-way-bound digest")
        capture = verifier_capture_ev.get("artifact")
        # FIX-C2(Codex P2):artifact 必須是 dict 型的 governed command_capture_v2 record。舊碼把 record_digest
        # 與 node_id 兩檢查都包在 isinstance(capture, dict) guard 內,故 artifact 為 null / 裸 digest 字串等
        # 非 dict 時**靜默跳過**驗證,evidence 卻仍計入 acceptance(等於接受一個未經 record 驗證的 bare digest
        # 冒充 command_capture_v2)。此處對非 dict artifact 直接 fail-closed,且只有 record 完整通過
        # (record_digest 綁定 + node_id != applier + outer digest 相符)才承認此 verifier capture。
        if not isinstance(capture, dict):
            errors.append("observer bootstrap verifier command_capture_v2 artifact must be a well-formed record")
        else:
            record_digest_ok = str(capture.get("record_digest")) == str(receipt_verifier_digest)
            node_distinct = capture.get("node_id") != applier_node
            if not record_digest_ok:
                errors.append("observer bootstrap verifier command_capture_v2 record_digest is not the bound digest")
            if not node_distinct:
                errors.append("observer bootstrap verifier capture node must differ from the applier node")
            verifier_capture_record_ok = outer_digest_ok and record_digest_ok and node_distinct

    # acceptance PASS 必同時綁 effect receipt + verifier capture 兩份 evidence id。
    # FIX-C2:verifier capture 只有在其 record 完整通過驗證(verifier_capture_record_ok)時才計入 acceptance;
    # 非 dict / 未綁定 record 的 bare digest 不足以構成一份 governed command_capture_v2。
    required_ids = {receipt_id}
    if verifier_capture_ev is not None:
        required_ids.add(verifier_capture_ev.get("id"))
    accepted = (
        postcheck is not None and verifier_capture_record_ok
        and any(
            item.get("status") == "PASS" and required_ids.issubset(set(item.get("evidence_refs", [])))
            for item in packet.get("acceptance", [])
        )
    )
    if not accepted:
        errors.append(
            "observer bootstrap passed acceptance must bind the effect receipt + verifier command capture"
        )
    return errors
