#!/usr/bin/env python3
"""S2.4(WP4·W3b)systemd-creds 加密憑證託管葉(§7 / §10.5 #26/#32)。

本葉是 ``CREDENTIAL_INSTALL`` row 的秘密面:固定的 in-process ``s2_4_secret_broker_v1``、
封閉 DSN 鍵集、加密 blob 指紋,以及「兩把單次消費 sealed handle」的交接契約。

硬規則(§7,全部 code-owned,worker 不得選):

- **零明文可序列化面**:秘密只存在於 :class:`SealedSecretHandle` 內;該物件拒
  ``repr``/``str``/``format``/``__reduce__``/``copy``/``json``,且**只能被消費一次**,
  消費後 best-effort 歸零。每一把 handle 於建構時以 weakref 進入進程內哨兵登記簿,
  生產側的 verdict/result/receipt 建構點一律呼叫 :func:`scan_serializable_surface`
  (內部即 :func:`assert_no_secret_material`)遞迴掃描,命中即 fail-closed typed 拒;
  driver/子行程例外文字一律經 :func:`redact_driver_error` 收斂成「型別 + 有界已掃描訊息」,
  ``CalledProcessError`` 這類會渲染完整 argv/連線選項的例外**只留型別**;
- **兩把 handle**(§7 #1/#2):PG actor 消費其一於固定 parameterized create/alter-role;
  credential actor 消費另一把,把封閉 DSN **直接**餵進
  ``systemd-creds encrypt --name=pg-dsn --with-key=host+tpm2``——中間永不產生 str;
- **封閉 DSN 鍵集**(§7):恰好八鍵;缺鍵/多鍵/任一 ``passfile``/``service``/
  ``servicefile``/``sslkey``/``options``/``hostaddr``/環境衍生值一律在連線之前失敗;
- **指紋非密碼 digest**:``sha256`` 取**加密後 blob bytes** + 固定 name/path/owner/mode
  metadata,domain-separated,絕不是密碼或明文 DSN 的 digest;
- **A→B→A rotation**:rotation 必須已有 task-owned slot;補償把**前一份加密 slot**原樣復原
  (只用先前擷取的密文 digest,絕不重建明文)。

誠實界線:本葉不執行任何真 ``systemd-creds``——加密/落盤一律經注入的
:class:`CredentialInstallDriver`;``driver=None`` 即 typed ``EXTERNAL_VERIFICATION_PENDING``。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import subprocess as _subprocess
import sys
import weakref
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

canonical_digest = central_validator.canonical_digest

# ── §7 code-owned 憑證託管常量 ──────────────────────────────────────────────────
CREDENTIAL_SLOT_PATH = "/etc/credstore.encrypted/aiml-engine-scanner-pg-dsn"
CREDENTIAL_UNIT_NAME = "pg-dsn"
CREDENTIAL_PROCESS_PATH = "%d/pg-dsn"
CREDENTIAL_SLOT_OWNER = "root"
CREDENTIAL_SLOT_GROUP = "root"
CREDENTIAL_SLOT_MODE = "0600"
CREDENTIAL_ENCRYPT_COMMAND = ("systemd-creds", "encrypt")
CREDENTIAL_ENCRYPT_NAME_ARG = "--name=pg-dsn"
CREDENTIAL_ENCRYPT_KEY_ARG = "--with-key=host+tpm2"
CREDENTIAL_DECRYPTION_NAME_VERIFICATION = True
# §7:封閉 libpq 鍵集(恰好八鍵;次序即 canonical 次序)。
CLOSED_DSN_KEYS = (
    "host",
    "port",
    "dbname",
    "user",
    "password",
    "connect_timeout",
    "application_name",
    "sslmode",
)
CLOSED_DSN_FIXED_VALUES = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "trading_ai",
    "user": "aiml_engine_scanner",
    "connect_timeout": "5",
    "application_name": "arcane-equilibrium-alr-engine-scanner",
    "sslmode": "disable",
}
# §7:任一出現即在連線之前失敗(含環境衍生值)。
FORBIDDEN_DSN_KEYS = (
    "hostaddr",
    "options",
    "passfile",
    "service",
    "servicefile",
    "sslcert",
    "sslkey",
    "sslrootcert",
)
# §8.3/§10.5 #26:unit 端必須被 unset 的 libpq 路由/憑證變數(值取自 renderer 的凍結面)。
PG_ENVIRONMENT_SCRUB_REQUIRED = True
PROCESS_HARDENING_CONTRACT = {
    "pr_set_dumpable": 0,
    "limit_core": "0",
    "pg_environment_scrubbed": True,
    "decryption_name_verification": CREDENTIAL_DECRYPTION_NAME_VERIFICATION,
}
# §7:密碼熵(kernel CSPRNG bytes;絕不是可預測種子)。
CREDENTIAL_SECRET_BYTES = 32
_SECRET_DOMAIN = b"arcane-equilibrium-aiml-s2-4-credential-fingerprint-v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

CREDENTIAL_STATUS_CAPABILITY_UNSATISFIED = "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED"


class CredentialContractError(ValueError):
    """憑證託管契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SecretMaterialLeak(AssertionError):
    """artifact 中偵測到秘密材料(或其常見編碼形)——停機級錯誤。"""


# --------------------------------------------------------------------------- #
# 進程內秘密哨兵登記簿(§10.5 #15:讓生產路徑得以「無參數」掃描任何可序列化面)。
#
# 登記的是 sealed handle 的 **weakref**——不另複製明文,故本登記簿既不延長秘密的生命
# 週期、也不阻止 handle 被回收;``zeroize()`` 就地歸零後登記項即刻失效,handle 被 GC 後
# 登記項自動消失(無單調成長)。
# --------------------------------------------------------------------------- #
_SECRET_SENTINEL_HANDLES: "list[weakref.ReferenceType[SealedSecretHandle]]" = []


def register_secret_sentinel(handle: "SealedSecretHandle") -> None:
    """把一把 sealed handle 登記為掃描哨兵(weakref;絕不複製明文)。"""

    _SECRET_SENTINEL_HANDLES.append(weakref.ref(handle))


def active_secret_sentinels() -> list[bytes]:
    """目前仍「活著」(未被回收、未歸零)的哨兵材料快照(函式局部、用完即棄)。"""

    alive: list[bytes] = []
    survivors: list[weakref.ReferenceType] = []
    for reference in _SECRET_SENTINEL_HANDLES:
        handle = reference()
        if handle is None:
            continue
        survivors.append(reference)
        buffer = handle._buffer  # noqa: SLF001 - 同葉內部面
        if any(buffer):
            alive.append(bytes(buffer))
    _SECRET_SENTINEL_HANDLES[:] = survivors
    return alive


def scan_serializable_surface(artifact: Any) -> list[str]:
    """對任何**即將被回傳/落盤**的結構做秘密掃描;命中回 typed 理由(不逸出例外)。

    生產路徑(component/prepare/probe 的 verdict 建構點)呼叫此函式而非直接呼叫
    :func:`assert_no_secret_material`:gate 需要的是 fail-closed 的 typed 拒絕,而不是
    一個會從 fail-closed 閘中逃逸的 ``AssertionError``。
    """

    sentinels = active_secret_sentinels()
    if not sentinels:
        return []
    try:
        assert_no_secret_material(artifact, sentinels)
    except SecretMaterialLeak as leak:
        return [str(leak)]
    return []


# §7:driver/子行程例外文字的最大保留長度(超出即截斷;argv/連線字串永不整段入 reason)。
_MAX_REDACTED_ERROR_CHARS = 160
# 任一片段命中即整段改寫為 <redacted>(密碼賦值、DSN 鍵、PEM/SSH armor、長 base64/hex 串)。
_SECRET_SHAPED_PATTERNS = (
    re.compile(r"(?i)pass(word|file)\s*=", re.UNICODE),
    re.compile(r"(?i)\b(dsn|secret|token|credential)\b", re.UNICODE),
    re.compile(r"-----BEGIN [A-Z ]+-----", re.UNICODE),
    re.compile(r"[A-Za-z0-9+/=_-]{32,}", re.UNICODE),
)
# 這些屬性一出現就代表例外會把 argv / stdout / stderr 渲染進 str()(subprocess 家族、
# libpq 的 Error.pgerror 等);此時只留型別,連截斷訊息都不保留。
_DIAGNOSTIC_LEAK_ATTRIBUTES = (
    "cmd", "argv", "output", "stdout", "stderr", "pgerror", "diag", "args_repr",
)


def redact_driver_error(error: BaseException) -> str:
    """把 driver/子行程例外收斂成「型別 + 有界且已掃描的訊息」(§7:秘密永不入 reason)。

    - 帶 typed ``code`` 的契約例外:``code`` 是 code-owned 常量,原樣保留;
    - 帶 ``cmd``/``output``/``stderr``/``pgerror`` 等診斷屬性者(``CalledProcessError``、
      libpq 例外):**只留型別**——``str()`` 會渲染完整 argv / 連線選項;
    - 其餘:截斷到 :data:`_MAX_REDACTED_ERROR_CHARS`,再過 secret-shaped 形狀掃描與
      進程內哨兵掃描,任一命中即整段 ``<redacted>``。
    """

    kind = type(error).__name__
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return f"{kind}: {code}"
    if any(hasattr(error, name) for name in _DIAGNOSTIC_LEAK_ATTRIBUTES):
        return f"{kind}: <redacted driver diagnostics>"
    try:
        text = str(error)
    except Exception:  # noqa: BLE001 - __str__ 本身逸出也不得洩漏
        return f"{kind}: <unrenderable>"
    text = text[:_MAX_REDACTED_ERROR_CHARS]
    if any(pattern.search(text) for pattern in _SECRET_SHAPED_PATTERNS):
        return f"{kind}: <redacted>"
    if scan_serializable_surface(text):
        return f"{kind}: <redacted>"
    return f"{kind}: {text}" if text else kind


# --------------------------------------------------------------------------- #
# 不可序列化、單次消費的 sealed handle(§7:driver 收 handle,絕不收字串)。
# --------------------------------------------------------------------------- #
class SealedSecretHandle:
    """operation-ID 綁定的 read-once 秘密控點;任何序列化/顯示面一律拒。"""

    # ``__weakref__`` 存在才可被哨兵登記簿以 weakref 追蹤(見下方登記簿說明)。
    __slots__ = ("_buffer", "_consumed", "_operation_id", "_purpose", "_closed", "__weakref__")

    def __init__(self, payload: bytearray, *, operation_id: str, purpose: str) -> None:
        self._buffer = payload
        self._consumed = False
        self._closed = False
        self._operation_id = operation_id
        self._purpose = purpose
        # §10.5 #15:handle 一存在,其明文即成為「任何可序列化面都不得出現」的哨兵。
        # 登記的是 weakref(零額外明文複本),故 zeroize()/GC 皆即刻使其失效。
        register_secret_sentinel(self)

    @property
    def operation_id(self) -> str:
        return self._operation_id

    @property
    def purpose(self) -> str:
        return self._purpose

    @property
    def consumed(self) -> bool:
        return self._consumed

    def consume(self, *, operation_id: str) -> bytes:
        """單次消費;operation_id 不符或重複消費一律 typed 拒(§7 #4)。"""

        if self._closed:
            raise CredentialContractError("sealed_handle_closed")
        if self._consumed:
            raise CredentialContractError("sealed_handle_already_consumed")
        if not hmac.compare_digest(str(operation_id), self._operation_id):
            raise CredentialContractError("sealed_handle_operation_id_mismatch")
        self._consumed = True
        return bytes(self._buffer)

    def zeroize(self) -> None:
        """best-effort 記憶體歸零(有界操作結束後立即呼叫)。"""

        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._closed = True

    # ── 不可序列化面:任何洩漏路徑都是硬錯誤 ────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover - 顯示面恆為紅字
        return f"<SealedSecretHandle {self._purpose} redacted>"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        del spec
        return self.__repr__()

    def __reduce__(self):  # noqa: D105 - pickle/copy 一律拒
        raise CredentialContractError("sealed_handle_not_serializable")

    def __deepcopy__(self, memo):  # noqa: D105
        raise CredentialContractError("sealed_handle_not_serializable")

    def __copy__(self):  # noqa: D105
        raise CredentialContractError("sealed_handle_not_serializable")

    def __bytes__(self) -> bytes:
        raise CredentialContractError("sealed_handle_not_serializable")


class SecretBroker:
    """固定的 in-process ``s2_4_secret_broker_v1``:無 top-level route、不收 caller 秘密。"""

    schema_version = "s2_4_secret_broker_v1"

    def __init__(self, *, operation_id: str) -> None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise CredentialContractError("secret_broker_operation_id_invalid")
        self.operation_id = operation_id
        self._handles: list[SealedSecretHandle] = []

    def mint_first_provisioning_handles(self) -> tuple[SealedSecretHandle, SealedSecretHandle]:
        """自 kernel CSPRNG 取高熵密碼,回兩把單次消費 handle(PG actor / credential actor)。"""

        password = secrets.token_urlsafe(CREDENTIAL_SECRET_BYTES).encode("ascii")
        pg_handle = SealedSecretHandle(
            bytearray(password), operation_id=self.operation_id, purpose="pg_role_password"
        )
        dsn_bytes = _render_closed_dsn_bytes(password)
        credential_handle = SealedSecretHandle(
            bytearray(dsn_bytes), operation_id=self.operation_id, purpose="closed_dsn"
        )
        # 本地明文只活在上面兩個 bytearray;此處的 bytes 立即失去引用。
        del password, dsn_bytes
        self._handles.extend([pg_handle, credential_handle])
        return pg_handle, credential_handle

    def zeroize_all(self) -> None:
        for handle in self._handles:
            handle.zeroize()
        self._handles.clear()


def _render_closed_dsn_bytes(password: bytes) -> bytes:
    """把封閉八鍵 DSN 渲染成 bytes(唯一構造點;絕不回傳 str,絕不入 log/argv)。"""

    parts: list[bytes] = []
    for key in CLOSED_DSN_KEYS:
        if key == "password":
            parts.append(b"password=" + password)
        else:
            parts.append(f"{key}={CLOSED_DSN_FIXED_VALUES[key]}".encode("ascii"))
    return b" ".join(parts)


def closed_dsn_key_contract() -> dict[str, Any]:
    """封閉 DSN 契約投影(W3 ABI 折入面;不含任何秘密)。"""

    return {
        "keys": list(CLOSED_DSN_KEYS),
        "fixed_values": dict(CLOSED_DSN_FIXED_VALUES),
        "forbidden_keys": list(FORBIDDEN_DSN_KEYS),
        "credential_slot_path": CREDENTIAL_SLOT_PATH,
        "credential_unit_name": CREDENTIAL_UNIT_NAME,
        "credential_process_path": CREDENTIAL_PROCESS_PATH,
        "encrypt_argv": list(CREDENTIAL_ENCRYPT_COMMAND)
        + [CREDENTIAL_ENCRYPT_NAME_ARG, CREDENTIAL_ENCRYPT_KEY_ARG],
        "slot_owner": CREDENTIAL_SLOT_OWNER,
        "slot_group": CREDENTIAL_SLOT_GROUP,
        "slot_mode": CREDENTIAL_SLOT_MODE,
        "process_hardening": dict(PROCESS_HARDENING_CONTRACT),
    }


def derive_closed_dsn_key_status(observed_keys: Any) -> dict[str, Any]:
    """§7:一組 DSN 鍵能否被接受?缺鍵/多鍵/禁鍵一律在連線之前失敗。"""

    if not isinstance(observed_keys, (list, tuple, set, frozenset)):
        return {
            "status": "CLOSED_DSN_REJECTED",
            "reasons": ["observed DSN key set must be a collection of key names"],
        }
    keys = [str(key) for key in observed_keys]
    reasons: list[str] = []
    missing = sorted(set(CLOSED_DSN_KEYS) - set(keys))
    extra = sorted(set(keys) - set(CLOSED_DSN_KEYS))
    if missing:
        reasons.append(f"closed DSN is missing required libpq keys {missing}")
    if extra:
        reasons.append(
            f"closed DSN carries additional keys {extra}; the eight-key set in §7 is closed"
        )
    forbidden = sorted(set(keys) & set(FORBIDDEN_DSN_KEYS))
    if forbidden:
        reasons.append(
            f"closed DSN carries forbidden keys {forbidden} (passfile/service/servicefile/"
            "sslkey/options/hostaddr or an environment-derived value fails before connection)"
        )
    if len(keys) != len(set(keys)):
        reasons.append("closed DSN repeats a key")
    return {
        "status": "CLOSED_DSN_ACCEPTED" if not reasons else "CLOSED_DSN_REJECTED",
        "reasons": reasons,
    }


def encrypted_credential_fingerprint(
    *,
    encrypted_blob_digest: str,
    name: str = CREDENTIAL_UNIT_NAME,
    path: str = CREDENTIAL_SLOT_PATH,
    owner: str = CREDENTIAL_SLOT_OWNER,
    mode: str = CREDENTIAL_SLOT_MODE,
) -> str:
    """``sha256`` 取加密 blob digest + 固定 slot metadata(domain-separated;非密碼 digest)。"""

    if not isinstance(encrypted_blob_digest, str) or _DIGEST_RE.fullmatch(
        encrypted_blob_digest
    ) is None:
        raise CredentialContractError("encrypted_blob_digest_invalid")
    payload = canonical_digest({
        "encrypted_blob_digest": encrypted_blob_digest,
        "name": name,
        "path": path,
        "owner": owner,
        "mode": mode,
    }).encode("ascii")
    return "sha256:" + hashlib.sha256(_SECRET_DOMAIN + b"|" + payload).hexdigest()


def assert_no_secret_material(artifact: Any, sentinels: Any) -> None:
    """遞迴掃描任何 artifact 的秘密材料與常見編碼形;命中即停機級錯誤(§10.5 #15)。"""

    encoded: list[str] = []
    for sentinel in list(sentinels or []):
        raw = sentinel if isinstance(sentinel, bytes) else str(sentinel).encode("utf-8")
        if not raw:
            continue
        import base64

        encoded.extend([
            raw.decode("utf-8", "ignore"),
            base64.b64encode(raw).decode("ascii"),
            base64.b16encode(raw).decode("ascii"),
            base64.b16encode(raw).decode("ascii").lower(),
            base64.urlsafe_b64encode(raw).decode("ascii"),
            raw.hex(),
        ])
    if not encoded:
        return
    hits: list[str] = []

    def _walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                _walk(key, trail)
                _walk(value, f"{trail}{key}.")
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item, trail)
        elif isinstance(node, (str, bytes)):
            text = node if isinstance(node, str) else node.decode("utf-8", "ignore")
            for form in encoded:
                if form and form in text:
                    hits.append(trail or "<root>")
                    return

    _walk(artifact, "")
    if hits:
        raise SecretMaterialLeak(
            f"secret material (or a common encoded form) reached a serializable surface at {sorted(set(hits))}"
        )


# --------------------------------------------------------------------------- #
# 注入式 driver protocol —— 真 systemd-creds / PG 密碼設定的唯一出口。
# --------------------------------------------------------------------------- #
class CredentialInstallDriver(Protocol):
    """加密憑證託管的固定操作面;caller **永不**遞交秘密字串或任意路徑。"""

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None:
        """把一筆 WAL transition 落盤(temp-create→fsync→atomic-rename→parent-fsync)。"""
        ...

    def host_credential_capability(self) -> dict[str, Any]:
        """回 ``{systemd_creds_available, tpm2_available, decryption_name_verification}``。"""
        ...

    def observe_credential_slot(self, *, slot_path: str) -> dict[str, Any] | None:
        """唯讀 slot 中繼資料 ``{owner, group, mode, encrypted_blob_digest, task_owned}``;
        **絕不**解密或回傳明文。不存在回 ``None``。"""
        ...

    def encrypt_credential(
        self, *, name: str, with_key: str, dsn_handle: SealedSecretHandle, operation_id: str
    ) -> dict[str, Any]:
        """把封閉 DSN 經 protected FD 餵給 ``systemd-creds encrypt``。回
        ``{encrypted_blob_digest, argv}``——**絕不**回傳明文或密文本體。"""
        ...

    def install_encrypted_slot(
        self, *, slot_path: str, encrypted_blob_digest: str, owner: str, group: str, mode: str
    ) -> dict[str, Any]:
        """原子安裝 root-owned mode 0600 的加密 slot;回安裝後觀測。"""
        ...

    def independent_login_postcheck(
        self, *, slot_path: str, role: str, endpoint: dict[str, Any], applier_node: str
    ) -> dict[str, Any]:
        """相異 verifier:經 systemd credential 託管解密並實證 end-to-end SCRAM 登入。
        回 ``{verifier_node, login_verified, decrypted_via_credential_custody,
        observed_dsn_keys, verifier_capture_digest, observed_subject_digest}``。"""
        ...

    def restore_previous_slot(
        self, *, slot_path: str, previous_encrypted_blob_digest: str
    ) -> dict[str, Any]:
        """A→B→A rotation 補償:原樣復原前一份**密文** slot(絕不重建明文)。"""
        ...

    def remove_task_owned_slot(self, *, slot_path: str) -> dict[str, Any]:
        """first-provision 補償:只移除本次 task-owned 的新 slot。"""
        ...

    def trusted_host_time(self) -> str:
        """trusted-host 時鐘。"""
        ...


def derive_host_credential_capability_status(capability: Any) -> dict[str, Any]:
    """§7:加密憑證託管無法建立即 ``HOST_CREDENTIAL_CAPABILITY_UNSATISFIED``(零 PG/unit 變更)。"""

    if not isinstance(capability, dict):
        return {
            "status": CREDENTIAL_STATUS_CAPABILITY_UNSATISFIED,
            "reasons": ["host credential capability observation must be an object"],
        }
    reasons: list[str] = []
    if capability.get("systemd_creds_available") is not True:
        reasons.append("systemd-creds is unavailable; LoadCredentialEncrypted= is mandatory")
    if capability.get("tpm2_available") is not True:
        reasons.append(
            "the host+tpm2 key is unavailable; --with-key=host+tpm2 is not worker-selectable"
        )
    if capability.get("decryption_name_verification") is not True:
        reasons.append("decryption-name verification must remain enabled")
    return {
        "status": (
            "HOST_CREDENTIAL_CAPABILITY_SATISFIED"
            if not reasons
            else CREDENTIAL_STATUS_CAPABILITY_UNSATISFIED
        ),
        "reasons": reasons,
    }


def credential_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的憑證面(骨架 + 封閉 DSN/指紋契約的活再導出)。"""

    try:
        dsn_contract_digest = canonical_digest(closed_dsn_key_contract())
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        dsn_contract_digest = None
    try:
        fingerprint_probe = encrypted_credential_fingerprint(
            encrypted_blob_digest="sha256:" + "0" * 64
        )
    except Exception:  # noqa: BLE001
        fingerprint_probe = None
    return {
        "secret_broker": "agent_governance_s2_4_credential.SecretBroker",
        "sealed_handle": "agent_governance_s2_4_credential.SealedSecretHandle",
        "credential_driver_protocol": (
            "agent_governance_s2_4_credential.CredentialInstallDriver"
        ),
        "closed_dsn_contract_digest": dsn_contract_digest,
        "closed_dsn_keys": list(CLOSED_DSN_KEYS),
        "forbidden_dsn_keys": list(FORBIDDEN_DSN_KEYS),
        "credential_slot_path": CREDENTIAL_SLOT_PATH,
        "credential_encrypt_argv": list(CREDENTIAL_ENCRYPT_COMMAND)
        + [CREDENTIAL_ENCRYPT_NAME_ARG, CREDENTIAL_ENCRYPT_KEY_ARG],
        "credential_fingerprint_probe": fingerprint_probe,
        "process_hardening": dict(PROCESS_HARDENING_CONTRACT),
        "typed_failure": CREDENTIAL_STATUS_CAPABILITY_UNSATISFIED,
        # §10.5 #15:秘密掃描與例外文字紅字化在生產路徑上的活再導出面。
        "serializable_surface_scanner": (
            "agent_governance_s2_4_credential.scan_serializable_surface"
        ),
        "driver_error_redactor": "agent_governance_s2_4_credential.redact_driver_error",
        "diagnostic_leak_attributes": list(_DIAGNOSTIC_LEAK_ATTRIBUTES),
        "redacted_error_max_chars": _MAX_REDACTED_ERROR_CHARS,
        "called_process_error_redaction_probe": redact_driver_error(
            _subprocess.CalledProcessError(
                1, ["systemd-creds", "encrypt", "--name=pg-dsn"], output=b"", stderr=b""
            )
        ),
    }
