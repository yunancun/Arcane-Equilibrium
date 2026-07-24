"""AIML S1 formal-closure: isolated ``python3 -E`` target-host probe child executor (P1 process isolation).

取代 Wave B 的 process-global 授權(舊 ``_run_probe_under_intent_authorization`` 直接改 **parent** 行程的
``os.environ["AIML_TARGET_HOST_PROBE"]``,在 ``probe_runner`` 執行期間對整個 parent 行程翻開低階閘——
同行程的另一 task / direct caller 於該窗口內可未經自己的 validated intent 就跑真基元)。本模組把真探針
移進一個**專屬子行程**:

  * parent(在 apply orchestrator)先驗證 typed intent,再由 VALIDATED intent 派生一張 canonical
    authorization capsule——綁 intent digest / source head / expected host / expiry / throwaway root /
    actor node / nonce / capsule digest——並連同 operator 對 exact intent 的 SSHSIG 授權，經一次性 stdin
    pipe 傳入子行程;不寫檔、不進全局 env、不走 argv。
  * 子行程以 sanitized allowlist environment 啟動(**不**繼承 ``AIML_TARGET_HOST_PROBE``);讀入完整
    request，驗 operator SSHSIG、exact intent/self-digest、capsule 與 intent 的參數投影、時效和 actual
    host；通過後才在**自己**的 ``os.environ`` 設 ``AIML_TARGET_HOST_PROBE=1``，呼叫低階
    ``run_target_host_probe``，把 canonical JSON 結果寫回 stdout。子行程退出後 capability 即失效
    (閘只存在於已結束的子行程)。parent 行程**從不**翻開該閘。
  * 任意 direct caller、自造或改封 capsule、無效 SSHSIG、過期授權、host/intent/參數不符或缺 request
    均 fail-closed。

governed ``capture-command`` 對 ``AIML_TARGET_HOST_PROBE`` 的 env-strip(allowlist)不受本模組削弱:child
的授權來自 capsule(pipe)而非 env,故經 capture 走私旗標仍無效。本模組 stdlib-first,parent-side helper
不 import 探針模組;探針模組僅在子行程 ``_child_main`` 內、通過 capsule 驗證後才延遲載入。

**安全界線**:``capsule_digest`` 只提供 canonical 傳輸完整性；真正的 authorization 邊界是 source-pinned
operator public key 對 exact typed intent/source head 的 domain-separated SSHSIG。子行程同時驗證簽名、
intent self-digest、capsule→intent 的 throwaway root/launcher/host/actor/expiry 投影，故 caller 不能以
重算 capsule checksum 替換已簽參數。PG 依賴與 preflight capture digest 由 closure 的 producer/semantic
capture 三方綁定驗證，不由 operator permit 重複承載。OS 非 root/user-scope 界線與生產前綴禁令仍保持。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import agent_governance_target_host_operator_authorization as operator_auth

# 本檔所在的 maintenance_scripts 目錄(以 __file__ 推導,於子行程顯式加回 sys.path;-E 忽略 PYTHONPATH,
# 故不依賴 env 注入路徑,而以受信的 __file__ 目錄為準——belt-and-suspenders,即使解譯器已 prepend 腳本目錄)。
_MAINTENANCE_DIR = Path(__file__).resolve().parent

CAPSULE_SCHEMA_VERSION = "target_host_probe_authorization_capsule_v1"
# 低階 seam(agent_governance_target_host_probe.target_host_available)讀的授權旗標名。
CAPSULE_ENV_GATE = "AIML_TARGET_HOST_PROBE"
# capsule 存活極短(單次 apply 用),過期即拒——限制任何被側錄 capsule 的重放窗口。
DEFAULT_CAPSULE_TTL_SECONDS = 120
CHILD_FLAG = "--probe-child"
CHILD_TIMEOUT_SECONDS = 300

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")

CAPSULE_FIELDS = frozenset({
    "schema_version", "intent_id", "intent_digest", "source_head", "expected_host",
    "actor_node", "throwaway_root", "pg_readonly_identity_receipt_digest",
    "launcher_argv", "target_host_capture_digest", "nonce", "issued_at",
    "intent_expires_at", "expires_at", "operator_authorization_digest",
    "capsule_digest",
})
CHILD_REQUEST_FIELDS = frozenset({
    "intent", "capsule", "operator_authorization",
    "operator_signature_base64",
})


class TargetHostChildApplyError(RuntimeError):
    """Raised when the isolated child probe cannot be safely driven (fail-closed)."""


# --------------------------------------------------------------------------- #
# canonical helpers (mirror the Wave A/B modules; stdlib-only)
# --------------------------------------------------------------------------- #
def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def capsule_digest(capsule: dict[str, Any]) -> str:
    """Hash every capsule field except the self-referential ``capsule_digest``."""

    return _digest({k: v for k, v in capsule.items() if k != "capsule_digest"})


# --------------------------------------------------------------------------- #
# parent-side: build one intent-derived authorization capsule
# --------------------------------------------------------------------------- #
def build_authorization_capsule(
    *,
    intent: dict[str, Any],
    source_head: str,
    probe_params: dict[str, Any],
    nonce: str,
    now: str,
    operator_authorization: dict[str, Any],
    ttl_seconds: int = DEFAULT_CAPSULE_TTL_SECONDS,
) -> dict[str, Any]:
    """Derive the canonical one-time authorization capsule from a VALIDATED typed intent.

    綁定 intent 的 ``self_digest`` / ``expected_host`` / ``applier_node_id`` 與 source head、以及由 intent
    派生的探針參數(throwaway_root / pg digest / launcher / capture digest),加 nonce 與短 TTL,最後以
    ``capsule_digest`` 自封。呼叫端須先 ``validate_probe_intent`` 通過本 intent(本函式不重驗 intent,只
    忠實投影已驗過的欄位)。
    """

    # P1(Codex):TTL 必為合理正整數上限(不得任意放大),且 capsule 授權期**不得逾越** intent 期——
    # 取 (now + 短 TTL) 與 intent expires_at 的**較早者**,故 child gate 絕不能活過其授權 intent。
    if not (isinstance(ttl_seconds, int) and not isinstance(ttl_seconds, bool)
            and 1 <= ttl_seconds <= DEFAULT_CAPSULE_TTL_SECONDS):
        raise ValueError(
            f"capsule ttl_seconds must be an int in [1, {DEFAULT_CAPSULE_TTL_SECONDS}]"
        )
    issued = _parse_time(now)
    intent_expires_at = str(intent["expires_at"])
    intent_expiry = _parse_time(intent_expires_at)
    expires = min(issued + timedelta(seconds=ttl_seconds), intent_expiry)
    authorization_digest = operator_authorization.get("authorization_digest")
    if not DIGEST_RE.fullmatch(str(authorization_digest or "")):
        raise ValueError(
            "operator_authorization must carry a canonical authorization_digest"
        )
    capsule: dict[str, Any] = {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "source_head": source_head,
        "expected_host": intent["expected_host"],
        "actor_node": intent["applier_node_id"],
        "throwaway_root": probe_params["throwaway_root"],
        "pg_readonly_identity_receipt_digest": probe_params["pg_readonly_identity_receipt_digest"],
        "launcher_argv": probe_params.get("launcher_argv"),
        "target_host_capture_digest": probe_params.get("target_host_capture_digest"),
        "nonce": nonce,
        "issued_at": now,
        "intent_expires_at": intent_expires_at,
        "expires_at": expires.isoformat(),
        "operator_authorization_digest": authorization_digest,
    }
    capsule["capsule_digest"] = capsule_digest(capsule)
    return capsule


def validate_capsule(
    capsule: Any,
    *,
    now: str,
    actual_host: str | None = None,
    intent: dict[str, Any] | None = None,
    expected_operator_authorization_digest: str | None = None,
) -> list[str]:
    """Fail-closed validation of an authorization capsule (used by the child before opening the gate).

    檢查:結構/欄位集、schema 常量、digest 自洽、格式(intent/source head/expected host)、未過期
    (``issued_at <= now < expires_at``),以及(當提供 ``actual_host``)``expected_host == actual_host``。
    """

    errors: list[str] = []
    if not isinstance(capsule, dict):
        return ["authorization capsule must be an object"]
    if set(capsule) != CAPSULE_FIELDS:
        errors.append(
            "authorization capsule fields mismatch: "
            f"missing={sorted(CAPSULE_FIELDS - set(capsule))} extra={sorted(set(capsule) - CAPSULE_FIELDS)}"
        )
        return errors
    if capsule.get("schema_version") != CAPSULE_SCHEMA_VERSION:
        errors.append("authorization capsule schema_version is invalid")
    if capsule.get("capsule_digest") != capsule_digest(capsule):
        errors.append("authorization capsule digest mismatch (tampered or decoupled)")
    if not DIGEST_RE.fullmatch(str(capsule.get("intent_digest", ""))):
        errors.append("authorization capsule intent_digest must be a sha256 digest")
    if not HEAD_RE.fullmatch(str(capsule.get("source_head", ""))):
        errors.append("authorization capsule source_head must be a 40-hex commit id")
    expected_host = capsule.get("expected_host")
    if not (isinstance(expected_host, str) and expected_host):
        errors.append("authorization capsule expected_host is required")
    elif actual_host is not None and expected_host != actual_host:
        errors.append(
            f"authorization capsule expected_host {expected_host!r} does not match the actual host "
            f"{actual_host!r} (refusing to run the probe on the wrong host)"
        )
    if not (isinstance(capsule.get("intent_id"), str) and capsule.get("intent_id")):
        errors.append("authorization capsule intent_id is required")
    if not (isinstance(capsule.get("actor_node"), str) and capsule.get("actor_node")):
        errors.append("authorization capsule actor_node is required")
    if not (isinstance(capsule.get("nonce"), str) and capsule.get("nonce")):
        errors.append("authorization capsule nonce is required")
    if not DIGEST_RE.fullmatch(str(capsule.get("pg_readonly_identity_receipt_digest", ""))):
        errors.append("authorization capsule pg_readonly_identity_receipt_digest must be a sha256 digest")
    operator_digest = capsule.get("operator_authorization_digest")
    if not DIGEST_RE.fullmatch(str(operator_digest or "")):
        errors.append(
            "authorization capsule operator_authorization_digest must be a sha256 digest"
        )
    if (
        expected_operator_authorization_digest is not None
        and operator_digest != expected_operator_authorization_digest
    ):
        errors.append(
            "authorization capsule is not bound to the operator authorization"
        )
    if intent is not None:
        for capsule_field, intent_field in (
            ("intent_id", "intent_id"),
            ("intent_digest", "self_digest"),
            ("expected_host", "expected_host"),
            ("actor_node", "applier_node_id"),
            ("throwaway_root", "throwaway_root"),
            ("intent_expires_at", "expires_at"),
        ):
            if capsule.get(capsule_field) != intent.get(intent_field):
                errors.append(
                    f"authorization capsule {capsule_field} differs from the exact intent"
                )
        per_seam = intent.get("per_seam_argv")
        expected_launcher = (
            per_seam.get("start_stop")
            if isinstance(per_seam, dict)
            else None
        )
        if capsule.get("launcher_argv") != expected_launcher:
            errors.append(
                "authorization capsule launcher_argv differs from the exact intent"
            )
    # launcher_argv 若存在必為 list[str](None=交由探針用預設 sleeper)。防「字串被 *展開成單字元」及
    # 非字串元素流入 systemd-run argv 的 footgun(E3 LOW-1 sub-note);仍非 shell(固定 list、無 shell=True)。
    launcher_argv = capsule.get("launcher_argv")
    if launcher_argv is not None and not (
        isinstance(launcher_argv, list) and all(isinstance(a, str) for a in launcher_argv)
    ):
        errors.append("authorization capsule launcher_argv must be null or a list of strings")
    try:
        issued = _parse_time(capsule["issued_at"])
        expires = _parse_time(capsule["expires_at"])
        intent_expiry = _parse_time(capsule["intent_expires_at"])
        current = _parse_time(now)
        if not issued <= expires:
            errors.append("authorization capsule issued_at must precede expires_at")
        if current >= expires:
            errors.append("authorization capsule has expired (expires_at <= now)")
        if current < issued:
            errors.append("authorization capsule is not yet valid (now < issued_at)")
        # P1(Codex):capsule 授權期不得逾越其授權 intent 的期限;且 intent 本身不得已過期。
        if expires > intent_expiry:
            errors.append("authorization capsule expires_at must not outlive the intent expires_at")
        if current >= intent_expiry:
            errors.append("authorization capsule's authorizing intent has already expired (intent_expires_at <= now)")
    except (KeyError, TypeError, ValueError):
        errors.append("authorization capsule timestamps are invalid")
    return errors


def validate_child_request(
    request: Any,
    *,
    now: str,
    actual_host: str,
) -> list[str]:
    """Authenticate the exact intent before the child opens its local gate."""

    if not isinstance(request, dict) or set(request) != CHILD_REQUEST_FIELDS:
        return ["operator authorization child request fields are invalid"]
    intent = request.get("intent")
    capsule = request.get("capsule")
    authorization = request.get("operator_authorization")
    encoded_signature = request.get("operator_signature_base64")
    try:
        signature = base64.b64decode(
            encoded_signature, validate=True
        ) if isinstance(encoded_signature, str) else b""
    except (ValueError, TypeError):
        signature = b""
    source_head = (
        str(capsule.get("source_head", ""))
        if isinstance(capsule, dict)
        else ""
    )
    errors = operator_auth.validate_operator_authorization(
        authorization,
        signature,
        intent=intent if isinstance(intent, dict) else {},
        source_head=source_head,
        now=now,
        actual_host=actual_host,
    )
    expected_digest = (
        authorization.get("authorization_digest")
        if isinstance(authorization, dict)
        else None
    )
    errors.extend(
        validate_capsule(
            capsule,
            now=now,
            actual_host=actual_host,
            intent=intent if isinstance(intent, dict) else None,
            expected_operator_authorization_digest=(
                str(expected_digest)
                if DIGEST_RE.fullmatch(str(expected_digest or ""))
                else None
            ),
        )
    )
    return errors


def _probe_params_from_capsule(capsule: dict[str, Any]) -> dict[str, Any]:
    return {
        "throwaway_root": capsule["throwaway_root"],
        "nonce": capsule["nonce"],
        "pg_readonly_identity_receipt_digest": capsule["pg_readonly_identity_receipt_digest"],
        "launcher_argv": capsule["launcher_argv"],
        "target_host_capture_digest": capsule["target_host_capture_digest"],
    }


# --------------------------------------------------------------------------- #
# parent-side: spawn the isolated child and read its canonical probe output
# --------------------------------------------------------------------------- #
def run_probe_via_child(
    capsule: dict[str, Any],
    *,
    intent: dict[str, Any],
    operator_authorization: dict[str, Any],
    operator_signature: bytes,
    python_executable: str = sys.executable,
    timeout: int = CHILD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Spawn ``python3 -E`` on this module, feed the capsule via a one-time stdin pipe, return probe output.

    子行程以 sanitized allowlist env 啟動:只帶 PATH/LANG/LC_ALL 與(存在時)執行環境所需的 non-secret
    ``XDG_RUNTIME_DIR`` / ``DBUS_SESSION_BUS_ADDRESS``——**絕不**傳 ``AIML_TARGET_HOST_PROBE``(閘由 child
    自行在驗過 capsule 後於自身 env 設定)。子行程於非 target host(如 Mac)乾淨 SKIP → 這裡以
    ``TargetHostUnavailableError`` 傳遞,保留「Mac 上真 runner 直接跳過、絕不 fake」的既有語意。

    直譯器旗標用 ``-E``(忽略 PYTHON* env,含 PYTHONPATH ⇒ 防 env 注入)而非 ``-I``:``-I`` 額外含
    ``-s``(排除 user site-packages),會使探針的合法 runtime 相依(如 pg_identity seam 需要的
    user-site ``psycopg2``)無法載入 ⇒ 該 seam 偽 DEFERRED、runtime 選擇由 BINDING 誤降為 PROVISIONAL。
    安全邊界不變:授權閘/秘密永不經 env 傳入(``env=child_env`` 白名單且不含旗標),PYTHONPATH 注入由
    ``-E`` 擋掉,capsule 於 child 內驗過才開閘;child 以絕對腳本路徑啟動,``sys.path[0]`` 為受信的
    maintenance_scripts 目錄(非 cwd),user site 為 runtime user 自有(此威脅模型下非新攻擊面)。
    """

    argv = [
        python_executable, "-E",
        str(_MAINTENANCE_DIR / "agent_governance_target_host_child_apply.py"),
        CHILD_FLAG,
    ]
    child_env = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}
    for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        value = os.environ.get(key)
        if value:
            child_env[key] = value
    try:
        request = {
            "intent": intent,
            "capsule": capsule,
            "operator_authorization": operator_authorization,
            "operator_signature_base64": base64.b64encode(
                operator_signature
            ).decode("ascii"),
        }
        proc = subprocess.run(
            argv, input=_canonical(request), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=child_env, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TargetHostChildApplyError(f"failed to spawn isolated probe child: {error}") from error
    if proc.returncode != 0:
        raise TargetHostChildApplyError(
            f"isolated probe child exited {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[:400]}"
        )
    try:
        payload = json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise TargetHostChildApplyError("isolated probe child did not return canonical JSON") from error
    if not isinstance(payload, dict):
        raise TargetHostChildApplyError("isolated probe child payload is not an object")
    status = payload.get("status")
    if status == "SKIPPED_NOT_TARGET_HOST":
        # 延遲 import 探針模組僅為取得其例外型別;保留真 runner 在 Mac 上 SKIP 的語意。
        sys.path.insert(0, str(_MAINTENANCE_DIR))
        import agent_governance_target_host_probe as th

        raise th.TargetHostUnavailableError(str(payload.get("reason") or "target host unavailable"))
    if status != "OK" or "probe_output" not in payload:
        raise TargetHostChildApplyError(f"isolated probe child returned an unusable payload (status={status!r})")
    probe_output = payload["probe_output"]
    if not isinstance(probe_output, dict):
        raise TargetHostChildApplyError("isolated probe child probe_output is not an object")
    return probe_output


# --------------------------------------------------------------------------- #
# child entrypoint (runs under python3 -E; the ONLY place the gate is opened)
# --------------------------------------------------------------------------- #
def _child_emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()


def _child_main() -> int:
    raw = sys.stdin.buffer.read()
    try:
        request = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        sys.stderr.write("authorization capsule is not valid JSON\n")
        return 3
    now = datetime.now(timezone.utc).isoformat()
    errors = validate_child_request(
        request,
        now=now,
        actual_host=socket.gethostname(),
    )
    if errors:
        sys.stderr.write(
            "operator authorization rejected: "
            + "; ".join(errors[:4])
            + "\n"
        )
        return 3
    capsule = request["capsule"]
    # 唯一翻開授權閘之處:於**本子行程**的 env(非 parent、非全局)、且僅在 capsule 驗過之後。
    os.environ[CAPSULE_ENV_GATE] = "1"
    sys.path.insert(0, str(_MAINTENANCE_DIR))
    import agent_governance_target_host_probe as th

    try:
        probe_output = th.run_target_host_probe(**_probe_params_from_capsule(capsule))
    except th.TargetHostUnavailableError as error:
        # 非 target host(Mac / 缺 systemd-run)——乾淨 SKIP,絕不 fake kernel 事實。
        _child_emit({
            "status": "SKIPPED_NOT_TARGET_HOST",
            "reason": str(error),
            "capsule_digest": capsule.get("capsule_digest"),
        })
        return 0
    except Exception as error:  # noqa: BLE001 - 真探針失敗仍須把 gate 關在子行程內,誠實回報非零
        sys.stderr.write(f"target-host probe failed inside isolated child: {error}\n")
        return 4
    _child_emit({
        "status": "OK",
        "probe_output": probe_output,
        "capsule_digest": capsule.get("capsule_digest"),
    })
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == CHILD_FLAG:
        raise SystemExit(_child_main())
    sys.stderr.write(
        "this module is the isolated target-host probe child executor; run it with "
        f"{CHILD_FLAG} and feed one authorization capsule on stdin\n"
    )
    raise SystemExit(2)
