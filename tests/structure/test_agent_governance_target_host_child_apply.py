"""S1 formal-closure P1: isolated ``python3 -E`` target-host probe child executor.

驗證 P1(Codex)「把 target-host 授權移出 process-global state」修復:授權由一張 intent-derived
capsule 經一次性 stdin pipe 傳入專屬子行程,子行程自行重驗 capsule 後才於**自身** env 開授權閘;
parent 行程從不翻開閘。涵蓋 capsule 建構/驗證的 fail-closed 分支,以及真子行程對 empty / host 不符 /
竄改 / 過期 capsule 的 fail-closed(退出碼 3),與合法 capsule 於 Mac 乾淨 SKIP(絕不 fake kernel 事實)。
"""

from __future__ import annotations

import socket
import subprocess
import sys
import json
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_target_host_child_apply as child  # noqa: E402
import agent_governance_target_host_operator_authorization as operator_auth  # noqa: E402


CHILD_PATH = HELPERS / "agent_governance_target_host_child_apply.py"
ACTUAL_HOST = socket.gethostname()


def _now() -> str:
    # 固定不了時鐘(child 用自己的 datetime.now),故用「相對現在」的 issued_at 讓 capsule 於 child 未過期。
    return datetime.now(timezone.utc).isoformat()


def _intent(expected_host: str = ACTUAL_HOST, *, expires_in: int = 3600) -> dict:
    exp = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    intent = {
        "schema_version": "target_host_disposable_runtime_probe_intent_v1",
        "intent_id": "sha256:" + "1" * 64,
        "expected_host": expected_host,
        "applier_node_id": "s1fc_apply_actor",
        "postcheck_node_id": "ops_postcheck",
        "throwaway_root": "/run/user/1000/aiml-probe-xyz",
        "per_seam_argv": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": exp,
    }
    intent["self_digest"] = operator_auth.intent_digest(intent)
    return intent


def _params() -> dict:
    return {
        "throwaway_root": "/run/user/1000/aiml-probe-xyz",
        "pg_readonly_identity_receipt_digest": "sha256:" + "b" * 64,
        "launcher_argv": None,
        "target_host_capture_digest": None,
    }


def _capsule(
    *, expected_host: str = ACTUAL_HOST, now: str | None = None, ttl_seconds: int = 120,
    intent_expires_in: int = 3600,
) -> dict:
    intent = _intent(expected_host, expires_in=intent_expires_in)
    authorization = operator_auth.build_operator_authorization(
        intent=intent,
        source_head="a" * 40,
    )
    return child.build_authorization_capsule(
        intent=intent, source_head="a" * 40,
        probe_params=_params(), nonce="nonce-abc-123456", now=now or _now(), ttl_seconds=ttl_seconds,
        operator_authorization=authorization,
    )


def _run_child(capsule_bytes: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-E", str(CHILD_PATH), child.CHILD_FLAG],
        input=capsule_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
    )


def _ephemeral_signer(tmp_path: Path, monkeypatch) -> Path:
    private_key = tmp_path / "operator"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
    )
    public_parts = private_key.with_suffix(".pub").read_text(
        encoding="ascii"
    ).split()
    public_key = " ".join(public_parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(operator_auth, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(operator_auth, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


def _sign_permit(permit: dict, private_key: Path, tmp_path: Path) -> bytes:
    message = tmp_path / "permit.json"
    message.write_bytes(operator_auth.canonical_bytes(permit))
    subprocess.run(
        [
            "ssh-keygen", "-Y", "sign", "-f", str(private_key),
            "-n", operator_auth.OPERATOR_SIGNATURE_NAMESPACE, str(message),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return message.with_suffix(".json.sig").read_bytes()


# --------------------------------------------------------------------------- #
# capsule build + validate (in-process)
# --------------------------------------------------------------------------- #
def test_capsule_roundtrip_is_self_consistent_and_valid() -> None:
    cap = _capsule()
    assert cap["schema_version"] == child.CAPSULE_SCHEMA_VERSION
    assert cap["capsule_digest"] == child.capsule_digest(cap)
    # 未提供 actual_host → 跳過 host 比對;capsule 自洽、未過期。
    assert child.validate_capsule(cap, now=cap["issued_at"]) == []
    assert child.validate_capsule(cap, now=cap["issued_at"], actual_host=ACTUAL_HOST) == []


def test_child_request_requires_operator_signed_exact_intent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    private_key = _ephemeral_signer(tmp_path, monkeypatch)
    intent = _intent()
    permit = operator_auth.build_operator_authorization(
        intent=intent,
        source_head="a" * 40,
    )
    signature = _sign_permit(permit, private_key, tmp_path)
    capsule = child.build_authorization_capsule(
        intent=intent,
        source_head="a" * 40,
        probe_params=_params(),
        nonce="nonce-abc-123456",
        now=intent["created_at"],
        operator_authorization=permit,
    )
    request = {
        "intent": intent,
        "capsule": capsule,
        "operator_authorization": permit,
        "operator_signature_base64": base64.b64encode(signature).decode("ascii"),
    }

    assert child.validate_child_request(
        request,
        now=intent["created_at"],
        actual_host=ACTUAL_HOST,
    ) == []

    forged = json.loads(json.dumps(request))
    forged["intent"]["expected_host"] = "attacker-selected-host"
    assert any(
        "operator authorization" in error
        for error in child.validate_child_request(
            forged,
            now=intent["created_at"],
            actual_host=ACTUAL_HOST,
        )
    )


def test_self_created_capsule_without_operator_signature_is_rejected() -> None:
    cap = _capsule()
    request = {
        "intent": _intent(),
        "capsule": cap,
        "operator_authorization": {},
        "operator_signature_base64": "",
    }
    errors = child.validate_child_request(
        request,
        now=cap["issued_at"],
        actual_host=ACTUAL_HOST,
    )
    assert any("operator authorization" in error for error in errors)


@pytest.mark.parametrize(
    "field,value,needle",
    [
        (
            "throwaway_root",
            "/run/user/1000/attacker-selected-root",
            "throwaway_root differs from the exact intent",
        ),
        (
            "launcher_argv",
            ["python3", "-c", "raise SystemExit(99)"],
            "launcher_argv differs from the exact intent",
        ),
    ],
)
def test_signed_intent_rejects_self_resealed_capsule_parameter_substitution(
    tmp_path: Path,
    monkeypatch,
    field,
    value,
    needle,
) -> None:
    """A valid operator permit cannot authorize caller-selected probe params."""

    private_key = _ephemeral_signer(tmp_path, monkeypatch)
    intent = _intent()
    permit = operator_auth.build_operator_authorization(
        intent=intent,
        source_head="a" * 40,
    )
    signature = _sign_permit(permit, private_key, tmp_path)
    capsule = child.build_authorization_capsule(
        intent=intent,
        source_head="a" * 40,
        probe_params=_params(),
        nonce="nonce-abc-123456",
        now=intent["created_at"],
        operator_authorization=permit,
    )
    capsule[field] = value
    capsule["capsule_digest"] = child.capsule_digest(capsule)
    request = {
        "intent": intent,
        "capsule": capsule,
        "operator_authorization": permit,
        "operator_signature_base64": base64.b64encode(signature).decode("ascii"),
    }

    errors = child.validate_child_request(
        request,
        now=intent["created_at"],
        actual_host=ACTUAL_HOST,
    )
    assert any(needle in error for error in errors)


def test_capsule_digest_detects_tamper() -> None:
    cap = _capsule()
    cap["source_head"] = "f" * 40  # 改欄位不重簽
    errors = child.validate_capsule(cap, now=cap["issued_at"])
    assert any("digest mismatch" in e for e in errors)


def test_capsule_rejects_expired() -> None:
    issued = datetime.now(timezone.utc) - timedelta(seconds=600)
    cap = _capsule(now=issued.isoformat(), ttl_seconds=120)
    errors = child.validate_capsule(cap, now=datetime.now(timezone.utc).isoformat())
    assert any("expired" in e for e in errors)


def test_capsule_rejects_host_mismatch() -> None:
    cap = _capsule(expected_host="some-other-host")
    errors = child.validate_capsule(cap, now=cap["issued_at"], actual_host=ACTUAL_HOST)
    assert any("does not match the actual host" in e for e in errors)


def test_capsule_rejects_missing_field() -> None:
    cap = _capsule()
    cap.pop("nonce")
    errors = child.validate_capsule(cap, now=cap["issued_at"])
    assert any("fields mismatch" in e for e in errors)


@pytest.mark.parametrize("field, value, needle", [
    ("intent_digest", "not-a-digest", "intent_digest must be a sha256"),
    ("source_head", "zz", "source_head must be a 40-hex"),
    ("pg_readonly_identity_receipt_digest", "nope", "pg_readonly_identity_receipt_digest must be a sha256"),
])
def test_capsule_rejects_malformed_bindings(field, value, needle) -> None:
    cap = _capsule()
    cap[field] = value
    cap["capsule_digest"] = child.capsule_digest(cap)  # 重簽,隔離出格式錯而非 digest 錯
    errors = child.validate_capsule(cap, now=cap["issued_at"])
    assert any(needle in e for e in errors)


# P1(Codex): the child authorization must not outlive its authorizing intent
def test_capsule_expiry_capped_at_intent_expiry() -> None:
    # intent 只剩 30s 而 TTL=120s → capsule.expires_at 被夾到 intent.expires_at(不逾越 intent 期)。
    cap = _capsule(ttl_seconds=120, intent_expires_in=30)
    assert cap["expires_at"] == cap["intent_expires_at"]


def test_capsule_rejects_overlong_ttl() -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        _capsule(ttl_seconds=child.DEFAULT_CAPSULE_TTL_SECONDS + 1)


def test_capsule_rejects_nonpositive_ttl() -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        _capsule(ttl_seconds=0)


def test_validate_rejects_capsule_outliving_intent() -> None:
    # 手工把 expires_at 撐過 intent_expires_at(重簽)→ validate 拒(閘不得活過 intent)。
    cap = _capsule(intent_expires_in=60)
    later = (datetime.fromisoformat(cap["intent_expires_at"]) + timedelta(seconds=300)).isoformat()
    cap["expires_at"] = later
    cap["capsule_digest"] = child.capsule_digest(cap)
    errors = child.validate_capsule(cap, now=cap["issued_at"])
    assert any("must not outlive the intent" in e for e in errors)


def test_validate_rejects_expired_intent() -> None:
    # intent 本身已過期(now >= intent_expires_at)→ validate 拒。
    cap = _capsule(intent_expires_in=60)
    after_intent = (datetime.fromisoformat(cap["intent_expires_at"]) + timedelta(seconds=1)).isoformat()
    errors = child.validate_capsule(cap, now=after_intent)
    assert any("authorizing intent has already expired" in e for e in errors)


# --------------------------------------------------------------------------- #
# real child subprocess (python3 -E) fail-closed / never-fake
# --------------------------------------------------------------------------- #
def test_child_rejects_empty_stdin() -> None:
    proc = _run_child(b"")
    assert proc.returncode == 3
    assert b"not valid JSON" in proc.stderr


def test_child_rejects_non_json() -> None:
    proc = _run_child(b"{not json")
    assert proc.returncode == 3


def test_child_rejects_host_mismatch() -> None:
    proc = _run_child(child._canonical(_capsule(expected_host="definitely-not-this-host")))
    assert proc.returncode == 3
    assert b"operator authorization" in proc.stderr


def test_child_rejects_tampered_capsule() -> None:
    cap = _capsule()
    cap["source_head"] = "f" * 40  # tamper without re-signing
    proc = _run_child(child._canonical(cap))
    assert proc.returncode == 3
    assert b"operator authorization" in proc.stderr


def test_child_rejects_expired_capsule() -> None:
    issued = datetime.now(timezone.utc) - timedelta(seconds=600)
    proc = _run_child(child._canonical(_capsule(now=issued.isoformat(), ttl_seconds=60)))
    assert proc.returncode == 3
    assert b"operator authorization" in proc.stderr


def test_child_rejects_a_self_created_capsule_even_when_structurally_valid() -> None:
    # A checksum-valid capsule is no longer authority.  The exact typed intent
    # plus operator SSHSIG envelope is mandatory before the child opens its
    # process-local gate.
    proc = _run_child(child._canonical(_capsule()))
    assert proc.returncode == 3
    assert b"operator authorization" in proc.stderr


def test_child_entrypoint_without_flag_is_fail_closed() -> None:
    proc = subprocess.run(
        [sys.executable, "-E", str(CHILD_PATH)], input=b"", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2  # 沒有 --probe-child flag → 拒
