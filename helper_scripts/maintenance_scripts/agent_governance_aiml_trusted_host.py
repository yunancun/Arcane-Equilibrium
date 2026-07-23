"""Trusted-host validation facade for S0.3 AIML Program adoption.

The facade owns secure local inputs and the pinned execution-signature trust
root. Immutable Git and authenticated GitHub verification live in bounded
submodules and are re-exported here as the stable public interface.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import os
import re
import select
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from agent_governance_aiml_trusted_common import (
    DIGEST_RE,
    MAX_JSON_BYTES,
    canonical_bytes as _canonical_bytes,
    canonical_digest,
    instant as _instant,
    strict_json_loads,
    utc_now as _utc_now,
)
from agent_governance_aiml_trusted_git import (
    MAX_BLOB_BYTES,
    REPO_ROOT,
    GitSourceManifestVerifier,
)
from agent_governance_aiml_trusted_github import (
    EXPECTED_DEFAULT_BRANCH,
    EXPECTED_PULL_REQUEST_PARAMETERS,
    EXPECTED_REQUIRED_CHECKS,
    EXPECTED_REPOSITORY_FULL_NAME,
    EXPECTED_REPOSITORY_ID,
    EXPECTED_REQUIRED_STATUS_CHECK_PARAMETERS,
    EXPECTED_RULESET_ID,
    EXPECTED_RULESET_NAME,
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    GITHUB_PAGE_SIZE,
    MAX_GITHUB_PAGES,
    GitHubRulesetVerifier,
    _associated_pulls_projection,
    _check_runs_projection,
    _commit_projection,
    _compare_projection,
    _effective_rules_projection,
    _github_associated_pulls_path,
    _github_check_runs_path,
    _github_commit_path,
    _github_compare_path,
    _github_effective_rules_path,
    _github_inventory_path,
    _github_pull_path,
    _github_static_paths,
    _pull_projection,
    _ref_projection,
    _repo_projection,
    _ruleset_inventory_projection,
    _ruleset_projection,
)


SSH_KEYGEN_EXECUTABLE = "/usr/bin/ssh-keygen"
EXPECTED_EXECUTION_SIGNER_IDENTITY = "aiml-s03-operator-v1"
EXPECTED_EXECUTION_SIGNER_FINGERPRINT = (
    "SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ"
)
EXECUTION_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s03"
EXECUTION_BUNDLE_ALGORITHM = "SSH-ED25519"
# The matching private key is deliberately absent from the trusted finalizer host.
# This reviewed source constant is the execution-evidence trust root.
TRUSTED_EXECUTION_PUBLIC_KEY = (
    "ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIJophp6Jd52hCchnFxzm4DIS/G7YOsLQGJNHI0vvLb7L"
)
# S1 formal-closure 簽章決策(Amendment A1 §6,取代 Wave A 的 operator-placeholder):S1 target-host
# 收尾**不新增第二套實體私鑰**,沿用 S0.3 既有信任根——公鑰/指紋 == S0.3 的
# TRUSTED_EXECUTION_PUBLIC_KEY / EXPECTED_EXECUTION_SIGNER_FINGERPRINT(對應私鑰同樣刻意不在源碼/
# 受信主機中,由 operator 帶外持有)。domain-separation 改由**身分 + 命名空間**達成:S1 用自己的
# identity(aiml-s1-target-host-operator-v1)與 namespace(arcane-equilibrium-aiml-s1-target-host),
# 故一張以 S0.3 命名空間簽的 bundle 於 S1 profile 下因 namespace 不符而被拒(反之亦然),而同一把真鑰
# 以 S1 namespace 簽的 bundle 可通過 S1。這讓 S1 profile 自洽(指紋 == 公鑰指紋),驗證邏輯可離線完整
# 測試(丟棄式測試鑰 + monkeypatch);真正的 S1 closure bundle SSHSIG 仍是帶外 operator 簽署步驟。
# S0.3 的 identity/namespace/公鑰/指紋/schema/receipt/既有簽章一律不動(S0.3 路徑 byte-identical)。
EXPECTED_S1_TARGET_HOST_SIGNER_IDENTITY = "aiml-s1-target-host-operator-v1"
S1_TARGET_HOST_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s1-target-host"
EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT = EXPECTED_EXECUTION_SIGNER_FINGERPRINT
S1_TRUSTED_TARGET_HOST_PUBLIC_KEY = TRUSTED_EXECUTION_PUBLIC_KEY
MAX_SIGNATURE_BYTES = 16 * 1024
MAX_BUNDLE_TTL = timedelta(minutes=15)
MAX_BUNDLE_AGE = timedelta(minutes=5)
MAX_ENTRY_TTL = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(seconds=60)
SECRET_PIPE_FRAME_TIMEOUT_SECONDS = 2.0
ALLOWED_EXECUTION_KINDS = frozenset({
    "context_artifact_v1",
    "workflow_wave_record_v1",
    "effect_adapter_result_v1",
    "runtime_observation_receipt_v1",
    "business_outcome_receipt_v1",
    "telemetry_record_v1",
})
# S1 formal-closure Wave A(S1.6B),§13 更正 C2:專屬 target_host_effect_result_v1 刻意 NOT 白名單。
# closure/attestation 路徑對每一筆 effect receipt 一律以硬編通用 kind effect_adapter_result_v1 認證
# (見 agent_governance_execution_attestation.validate_execution_attestations:59-62),沒有任何消費端
# 會消費 target_host_effect_result_v1 這種 bundle 項——白名單它即成死碼且是誤用陷阱(帶此 kind 的已簽
# 項會在 exact_consumption_errors() 觸「未消費項」而 fail-closed)。與 P0-B 一致:P0-B 亦刻意不白名單
# 自身的 p0b_alr_rollforward_effect_result_v1 kind,專屬 result 仍經通用 effect_adapter_result_v1 認證。
_BUNDLE_FIELDS = {
    "schema_version", "signer_identity", "signer_fingerprint", "algorithm",
    "signature_namespace", "task_contract_digest", "context_artifact_digest",
    "dag_digest", "issued_at", "expires_at", "entries",
}
_ENTRY_FIELDS = {
    "kind", "subject_digest", "artifact_digest", "observed_at", "expires_at",
}


@dataclass(frozen=True)
class ExecutionSignerProfile:
    """One domain-separated SSHSIG signer identity/namespace/fingerprint/public-key.

    把 bundle 認證的四個信任根參數化,讓 S0.3 收尾路徑與 S1 target-host 路徑各用自己的命名空間/
    身分/公鑰,彼此 domain-separated;預設仍是 S0.3 profile,故 S0.3 路徑 byte-identical。
    """

    identity: str
    fingerprint: str
    namespace: str
    algorithm: str
    public_key: str


def _default_s0_3_profile() -> "ExecutionSignerProfile":
    # 於「呼叫時」由 module 全域組出 S0.3 profile(而非 import 時凍結),以保留既有測試對
    # EXPECTED_EXECUTION_SIGNER_FINGERPRINT / TRUSTED_EXECUTION_PUBLIC_KEY 的 monkeypatch 行為;
    # S0.3 路徑因此 byte-identical(未傳 signer_profile 即用此)。
    return ExecutionSignerProfile(
        identity=EXPECTED_EXECUTION_SIGNER_IDENTITY,
        fingerprint=EXPECTED_EXECUTION_SIGNER_FINGERPRINT,
        namespace=EXECUTION_SIGNATURE_NAMESPACE,
        algorithm=EXECUTION_BUNDLE_ALGORITHM,
        public_key=TRUSTED_EXECUTION_PUBLIC_KEY,
    )


# S1 target-host profile(保留佔位;fingerprint/public_key 為 operator 輸入)。
S1_TARGET_HOST_EXECUTION_SIGNER_PROFILE = ExecutionSignerProfile(
    identity=EXPECTED_S1_TARGET_HOST_SIGNER_IDENTITY,
    fingerprint=EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT,
    namespace=S1_TARGET_HOST_SIGNATURE_NAMESPACE,
    algorithm=EXECUTION_BUNDLE_ALGORITHM,
    public_key=S1_TRUSTED_TARGET_HOST_PUBLIC_KEY,
)


def ssh_public_key_fingerprint(public_key: str) -> str:
    """Return the OpenSSH SHA-256 fingerprint for one exact public key."""

    try:
        algorithm, encoded = public_key.split(" ", 1)
        if algorithm != "ssh-ed25519" or not encoded or " " in encoded:
            raise ValueError("trusted execution public key format is invalid")
        wire_key = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("trusted execution public key format is invalid") from error
    fingerprint = base64.b64encode(hashlib.sha256(wire_key).digest()).decode("ascii")
    return "SHA256:" + fingerprint.rstrip("=")


def read_secure_bytes(path: Path, *, max_bytes: int) -> bytes:
    """Read one owner-controlled regular file once without following symlinks."""

    resolved_parent = path.parent.resolve(strict=True)
    candidate = resolved_parent / path.name
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(candidate, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("trusted-host JSON input must be a regular file")
        if info.st_uid != os.geteuid():
            raise ValueError("trusted-host JSON input has the wrong owner")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("trusted-host JSON input is group/world writable")
        raw = bytearray()
        while len(raw) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > max_bytes:
            raise ValueError("trusted-host file input exceeds size limit")
    finally:
        os.close(fd)
    return bytes(raw)


def read_secure_json(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    """Read and strictly decode one owner-controlled JSON file."""

    return strict_json_loads(read_secure_bytes(path, max_bytes=max_bytes))


def read_secret_fd(fd: int, *, label: str, max_bytes: int = 16 * 1024) -> bytes:
    """Consume a secret from an inherited FD without putting it in argv/output."""

    info = os.fstat(fd)
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISFIFO(info.st_mode)):
        raise ValueError(f"{label} FD must be a regular file or pipe")
    if stat.S_ISREG(info.st_mode):
        if info.st_uid != os.geteuid():
            raise ValueError(f"{label} FD has the wrong owner")
        if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError(f"{label} file permissions are too broad")
    raw = bytearray()
    if stat.S_ISFIFO(info.st_mode):
        deadline = time.monotonic() + SECRET_PIPE_FRAME_TIMEOUT_SECONDS
        while len(raw) <= max_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError(f"{label} pipe is missing a newline frame or EOF")
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                raise ValueError(f"{label} pipe is missing a newline frame or EOF")
            chunk = os.read(fd, min(4096, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if b"\n" in raw:
                frame, _, trailing = raw.partition(b"\n")
                if trailing.strip(b"\r\n"):
                    raise ValueError(f"{label} pipe contains multiple frames")
                raw = bytearray(frame.rstrip(b"\r"))
                break
    else:
        while len(raw) <= max_bytes:
            chunk = os.read(fd, min(4096, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
    if len(raw) > max_bytes:
        raise ValueError(f"{label} exceeds size limit")
    secret = bytes(raw).rstrip(b"\r\n")
    if not secret:
        raise ValueError(f"{label} is empty")
    return secret


def _verify_ssh_signature(
    message: bytes,
    signature: bytes,
    *,
    public_key: str,
    identity: str = EXPECTED_EXECUTION_SIGNER_IDENTITY,
    namespace: str = EXECUTION_SIGNATURE_NAMESPACE,
) -> bool:
    """Verify one SSHSIG with an exact public key and domain-separated identity."""

    if (
        not signature
        or len(signature) > MAX_SIGNATURE_BYTES
        or not signature.startswith(b"-----BEGIN SSH SIGNATURE-----\n")
        or not signature.rstrip().endswith(b"-----END SSH SIGNATURE-----")
    ):
        return False
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+", public_key):
        return False
    allowed_signer = (
        f'{identity} namespaces="{namespace}" {public_key}\n'.encode("ascii")
    )
    try:
        with tempfile.TemporaryDirectory(prefix="aiml-s03-verify-") as directory:
            root = Path(directory)
            allowed_path = root / "allowed_signers"
            signature_path = root / "execution_bundle.sig"
            allowed_path.write_bytes(allowed_signer)
            signature_path.write_bytes(signature)
            allowed_path.chmod(0o600)
            signature_path.chmod(0o600)
            result = subprocess.run(
                [
                    SSH_KEYGEN_EXECUTABLE,
                    "-Y", "verify",
                    "-f", str(allowed_path),
                    "-I", identity,
                    "-n", namespace,
                    "-s", str(signature_path),
                ],
                input=message,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                timeout=15,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _verify_execution_signature(
    bundle: Mapping[str, Any],
    signature: bytes,
    *,
    signer_profile: ExecutionSignerProfile | None = None,
) -> bool:
    # signer_profile 預設 S0.3(值同既有常量),故 S0.3 呼叫路徑 byte-identical。
    profile = signer_profile or _default_s0_3_profile()
    try:
        fingerprint_matches = hmac.compare_digest(
            ssh_public_key_fingerprint(profile.public_key),
            profile.fingerprint,
        )
    except ValueError:
        return False
    if not fingerprint_matches:
        return False
    return _verify_ssh_signature(
        _canonical_bytes(bundle),
        signature,
        public_key=profile.public_key,
        identity=profile.identity,
        namespace=profile.namespace,
    )


@dataclass
class AuthenticatedExecutionEvidenceIndex:
    """Stateful verifier backed by a separately authenticated host bundle."""

    entries: dict[tuple[str, str], dict[str, Any]]
    consumed: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def from_bundle(
        cls,
        bundle: Any,
        *,
        signature: bytes,
        now: datetime,
        task_contract_digest: str,
        context_artifact_digest: str,
        dag_digest: str,
        signer_profile: ExecutionSignerProfile | None = None,
    ) -> "AuthenticatedExecutionEvidenceIndex":
        # signer_profile 預設 S0.3(值同既有常量),故 S0.3 收尾路徑 byte-identical;傳入
        # S1_TARGET_HOST_EXECUTION_SIGNER_PROFILE 即切到 domain-separated 的 S1 target-host profile。
        profile = signer_profile or _default_s0_3_profile()
        if not isinstance(bundle, dict) or set(bundle) != _BUNDLE_FIELDS:
            raise ValueError("trusted execution bundle fields do not match contract")
        if bundle.get("schema_version") != "trusted_execution_bundle_v1":
            raise ValueError("trusted execution bundle schema_version is invalid")
        if bundle.get("signer_identity") != profile.identity:
            raise ValueError("trusted execution bundle signer identity is invalid")
        if (
            bundle.get("signer_fingerprint")
            != profile.fingerprint
        ):
            raise ValueError("trusted execution bundle signer fingerprint is invalid")
        if bundle.get("algorithm") != profile.algorithm:
            raise ValueError("trusted execution bundle algorithm is invalid")
        if bundle.get("signature_namespace") != profile.namespace:
            raise ValueError("trusted execution bundle signature namespace is invalid")
        for field_name, expected in (
            ("task_contract_digest", task_contract_digest),
            ("context_artifact_digest", context_artifact_digest),
            ("dag_digest", dag_digest),
        ):
            if not DIGEST_RE.fullmatch(str(bundle.get(field_name, ""))):
                raise ValueError(f"trusted execution bundle {field_name} is invalid")
            if bundle[field_name] != expected:
                raise ValueError(f"trusted execution bundle {field_name} mismatch")
        if not _verify_execution_signature(bundle, signature, signer_profile=profile):
            raise ValueError("trusted execution bundle authentication failed")

        current = now.astimezone(timezone.utc)
        issued = _instant(bundle.get("issued_at"))
        expires = _instant(bundle.get("expires_at"))
        if issued > current + MAX_CLOCK_SKEW:
            raise ValueError("trusted execution bundle is future-dated")
        if issued >= expires or expires - issued > MAX_BUNDLE_TTL:
            raise ValueError("trusted execution bundle TTL is invalid")
        if current - issued > MAX_BUNDLE_AGE or current >= expires:
            raise ValueError("trusted execution bundle is stale")

        raw_entries = bundle.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError("trusted execution bundle entries are required")
        entries: dict[tuple[str, str], dict[str, Any]] = {}
        canonical_order: list[tuple[str, str]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict) or set(entry) != _ENTRY_FIELDS:
                raise ValueError("trusted execution entry fields do not match contract")
            kind = entry.get("kind")
            subject = entry.get("subject_digest")
            if kind not in ALLOWED_EXECUTION_KINDS:
                raise ValueError("trusted execution entry kind is invalid")
            if not DIGEST_RE.fullmatch(str(subject or "")):
                raise ValueError("trusted execution entry subject digest is invalid")
            if not DIGEST_RE.fullmatch(str(entry.get("artifact_digest", ""))):
                raise ValueError("trusted execution entry artifact digest is invalid")
            observed = _instant(entry.get("observed_at"))
            entry_expires = _instant(entry.get("expires_at"))
            if observed > current + MAX_CLOCK_SKEW:
                raise ValueError("trusted execution entry is future-dated")
            if observed >= entry_expires or entry_expires - observed > MAX_ENTRY_TTL:
                raise ValueError("trusted execution entry TTL is invalid")
            if current >= entry_expires:
                raise ValueError("trusted execution entry is stale")
            identity = (str(kind), str(subject))
            if identity in entries:
                raise ValueError("trusted execution bundle contains duplicate entries")
            entries[identity] = entry
            canonical_order.append(identity)
        if canonical_order != sorted(canonical_order):
            raise ValueError("trusted execution bundle entries are not canonical")
        return cls(entries=entries)

    def verify(self, kind: str, digest: str, artifact: dict[str, Any]) -> bool:
        identity = (kind, digest)
        entry = self.entries.get(identity)
        if entry is None or not isinstance(artifact, dict):
            return False
        try:
            matched = hmac.compare_digest(
                str(entry["artifact_digest"]), canonical_digest(artifact)
            )
        except (TypeError, ValueError):
            return False
        if matched:
            self.consumed.add(identity)
        return matched

    def exact_consumption_errors(self) -> list[str]:
        extra = sorted(set(self.entries) - self.consumed)
        return (
            ["trusted execution bundle contains unconsumed entries"] if extra else []
        )



def _packet_bindings(packet: Mapping[str, Any]) -> tuple[str, str, str]:
    if not isinstance(packet, Mapping):
        raise ValueError("closure packet must be an object")
    dispatch = packet.get("dispatch")
    if not isinstance(dispatch, dict):
        raise ValueError("closure dispatch is absent")
    context = dispatch.get("context_artifact")
    if not isinstance(context, dict):
        raise ValueError("closure context artifact is absent")
    task_digest = context.get("task_contract_digest")
    context_digest = context.get("artifact_digest")
    dag_digest = dispatch.get("dag_digest")
    if not all(DIGEST_RE.fullmatch(str(value or "")) for value in (
        task_digest, context_digest, dag_digest
    )):
        raise ValueError("closure trusted-host bindings are invalid")
    return str(task_digest), str(context_digest), str(dag_digest)


def _receipt_digest(packet: Mapping[str, Any]) -> str | None:
    matches = [
        item for item in packet.get("evidence", [])
        if isinstance(item, dict) and item.get("kind") == "program_adoption_receipt_v1"
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("artifact"), dict):
        return None
    receipt = matches[0]["artifact"].get("receipt")
    value = receipt.get("self_digest") if isinstance(receipt, dict) else None
    return str(value) if DIGEST_RE.fullmatch(str(value or "")) else None


def _finalize_program_adoption(
    packet: Mapping[str, Any],
    *,
    execution_index: AuthenticatedExecutionEvidenceIndex,
    github_verifier: GitHubRulesetVerifier,
    source_verifier: GitSourceManifestVerifier,
    evaluated_at: datetime,
) -> dict[str, Any]:
    """Run the canonical closure validator once and return a sanitized decision."""

    from agent_governance_closure import validate_closure

    immutable_packet = copy.deepcopy(dict(packet))
    closure_digest = canonical_digest(immutable_packet)
    errors = validate_closure(
        immutable_packet,
        execution_attestation_verifier=execution_index.verify,
        external_evidence_verifier=github_verifier,
        source_manifest_verifier=source_verifier,
        trusted_evaluated_at=evaluated_at,
    )
    errors.extend(execution_index.exact_consumption_errors())
    errors = sorted(set(str(error) for error in errors))
    passed = not errors
    return {
        "schema_version": "aiml_trusted_host_finalization_result_v1",
        "status": "PASS" if passed else "FAIL",
        "closure_digest": closure_digest,
        "program_adoption_receipt_digest": _receipt_digest(immutable_packet) if passed else None,
        "errors": errors,
    }


def finalize_from_host_inputs(
    packet: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    execution_signature: bytes,
    github_token: bytes,
) -> dict[str, Any]:
    """Build fixed host capabilities, then validate the caller's complete packet."""

    evaluated_at = _utc_now().astimezone(timezone.utc)
    task_digest, context_digest, dag_digest = _packet_bindings(packet)
    execution_index = AuthenticatedExecutionEvidenceIndex.from_bundle(
        bundle,
        signature=execution_signature,
        now=evaluated_at,
        task_contract_digest=task_digest,
        context_artifact_digest=context_digest,
        dag_digest=dag_digest,
    )
    return _finalize_program_adoption(
        packet,
        execution_index=execution_index,
        github_verifier=GitHubRulesetVerifier(github_token, now=evaluated_at),
        source_verifier=GitSourceManifestVerifier(REPO_ROOT),
        evaluated_at=evaluated_at,
    )
