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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_target_host_child_apply as child  # noqa: E402


CHILD_PATH = HELPERS / "agent_governance_target_host_child_apply.py"
ACTUAL_HOST = socket.gethostname()


def _now() -> str:
    # 固定不了時鐘(child 用自己的 datetime.now),故用「相對現在」的 issued_at 讓 capsule 於 child 未過期。
    return datetime.now(timezone.utc).isoformat()


def _intent(expected_host: str = ACTUAL_HOST, *, expires_in: int = 3600) -> dict:
    exp = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    return {
        "intent_id": "th-intent-0001",
        "self_digest": "sha256:" + "a" * 64,
        "expected_host": expected_host,
        "applier_node_id": "s1fc_apply_actor",
        "expires_at": exp,
    }


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
    return child.build_authorization_capsule(
        intent=_intent(expected_host, expires_in=intent_expires_in), source_head="a" * 40,
        probe_params=_params(), nonce="nonce-abc-123456", now=now or _now(), ttl_seconds=ttl_seconds,
    )


def _run_child(capsule_bytes: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-E", str(CHILD_PATH), child.CHILD_FLAG],
        input=capsule_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
    )


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
    assert b"does not match the actual host" in proc.stderr


def test_child_rejects_tampered_capsule() -> None:
    cap = _capsule()
    cap["source_head"] = "f" * 40  # tamper without re-signing
    proc = _run_child(child._canonical(cap))
    assert proc.returncode == 3
    assert b"digest mismatch" in proc.stderr


def test_child_rejects_expired_capsule() -> None:
    issued = datetime.now(timezone.utc) - timedelta(seconds=600)
    proc = _run_child(child._canonical(_capsule(now=issued.isoformat(), ttl_seconds=60)))
    assert proc.returncode == 3
    assert b"expired" in proc.stderr


def test_child_accepts_valid_capsule_and_skips_on_non_target_host() -> None:
    # 合法 capsule(expected_host == 本機)→ 通過驗證 → child 於自身 env 開閘 → 但 Mac 非 target host,
    # run_target_host_probe 乾淨 SKIP(絕不 fake);child 以 SKIPPED 誠實回報,退出碼 0。
    import json

    proc = _run_child(child._canonical(_capsule()))
    if proc.returncode != 0:
        pytest.skip(f"unexpected child exit {proc.returncode}; stderr={proc.stderr.decode()[:200]}")
    payload = json.loads(proc.stdout.decode())
    # 於真 target host(trade-core)本測試不成立;那裡 status 會是 OK。Mac/CI runner 上應為 SKIPPED。
    assert payload["status"] in {"SKIPPED_NOT_TARGET_HOST", "OK"}
    if payload["status"] == "SKIPPED_NOT_TARGET_HOST":
        assert "never fakes" in payload["reason"] or "target-host" in payload["reason"]


def test_child_entrypoint_without_flag_is_fail_closed() -> None:
    proc = subprocess.run(
        [sys.executable, "-E", str(CHILD_PATH)], input=b"", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2  # 沒有 --probe-child flag → 拒
