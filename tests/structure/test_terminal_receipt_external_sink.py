"""Structural + injected-client tests for the S1.2A external-capable WORM sink.

Covers the external-destination CONTRACT (fail-closed on incomplete config,
COMPLIANCE-without-approval, retain_until<=approved_at, secret-shaped channel id),
the client-injection append machinery against a small in-process S3 STUB (NEVER a
real boto3 network call), a typed EXTERNAL_VERIFICATION_PENDING fail-closed when no
client is injected, idempotent dedup that does not re-put / does not mutate the
committed record, an independent immutability-proving readback ACK by a DISTINCT
actor (checksum + version-id + Object-Lock retention match, overwrite/delete
denied), a same-actor readback that fails closed, and the no-plaintext-secret
property on every serialized artifact.  The disposable sibling's external_worm
fail-close is asserted UNCHANGED here and exercised by its own test module.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_terminal_receipt_external_sink as ext  # noqa: E402
import agent_governance_terminal_receipt_sink as sink  # noqa: E402


HEAD_A = "a" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
APPROVED_AT = "2026-07-22T09:00:00Z"
EXPIRES_AT = "2026-07-22T11:00:00Z"
NOW = "2026-07-22T10:00:00Z"
RETAIN_UNTIL = "2027-07-22T09:00:00Z"
APPEND_ACTOR = "external-append-actor"
VERIFIER = "independent-external-verifier"
ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
BUCKET = "aiml-worm-terminal-bucket"
CHANNEL = "aws-profile:aiml-worm-writer"


def _payload() -> dict:
    return {"kind": "disposable_proof_payload_v1", "scope": DIGEST_A, "note": "non-secret"}


def _intent(*, object_lock_mode: str = "GOVERNANCE",
            compliance_operator_approved: bool = False,
            credential_channel_id: str = CHANNEL,
            retain_until: str = RETAIN_UNTIL) -> dict:
    return ext.build_external_worm_append_intent(
        intent_id="intent-ext-worm-000001",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=sink.terminal_payload_digest(_payload()),
        append_actor_id=APPEND_ACTOR,
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
        endpoint=ENDPOINT,
        region=REGION,
        bucket=BUCKET,
        object_lock_mode=object_lock_mode,
        retain_until=retain_until,
        credential_channel_id=credential_channel_id,
        compliance_operator_approved=compliance_operator_approved,
        now=NOW,  # 凍結時鐘,避免 retain_until>now 檢查引入 wall-clock time-bomb
    )


# --------------------------------------------------------------------------- #
# in-process S3 Object-Lock STUB (no network, no boto3) — client injection
# --------------------------------------------------------------------------- #
class FakeS3ClientError(Exception):
    """botocore-ClientError-shaped stub error (carries .response.Error.Code)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeObjectLockS3:
    """A minimal S3-compatible Object-Lock stub.

    Stores one immutable version per key.  The readback proof is now NON-DESTRUCTIVE:
    it reads get_object_lock_configuration (bucket lock ENABLED iff ``worm=True``) and
    get_object_retention (mode + future retain-until).  ``worm=False`` simulates a
    NON-locked bucket so the immutability proof fails closed WITHOUT any destructive op.
    delete_object / put_object_retention remain defined ONLY to prove the verifier
    never calls them (delete_calls / retention_write_calls must stay 0).
    """

    def __init__(self, *, worm: bool = True) -> None:
        self.worm = worm
        self.objects: dict[tuple[str, str], dict] = {}
        self.put_calls = 0
        self.last_put_kwargs: dict | None = None
        self.delete_calls = 0
        self.retention_write_calls = 0
        self.lock_config_reads = 0

    def put_object(self, *, Bucket, Key, Body, ChecksumSHA256, ObjectLockMode,
                   ObjectLockRetainUntilDate):
        self.put_calls += 1
        self.last_put_kwargs = {
            "Bucket": Bucket, "Key": Key, "ChecksumSHA256": ChecksumSHA256,
            "ObjectLockMode": ObjectLockMode,
            "ObjectLockRetainUntilDate": ObjectLockRetainUntilDate,
        }
        version_id = f"v-{self.put_calls}-{hashlib.sha256(bytes(Body)).hexdigest()[:8]}"
        self.objects[(Bucket, Key)] = {
            "Body": bytes(Body), "ChecksumSHA256": ChecksumSHA256,
            "VersionId": version_id, "Mode": ObjectLockMode,
            "RetainUntilDate": ObjectLockRetainUntilDate,
        }
        return {"VersionId": version_id, "ChecksumSHA256": ChecksumSHA256}

    def _require(self, Bucket, Key):
        obj = self.objects.get((Bucket, Key))
        if obj is None:
            raise FakeS3ClientError("404")
        return obj

    def head_object(self, *, Bucket, Key, ChecksumMode=None):
        obj = self._require(Bucket, Key)
        return {"VersionId": obj["VersionId"], "ChecksumSHA256": obj["ChecksumSHA256"]}

    def get_object(self, *, Bucket, Key, VersionId=None, ChecksumMode=None):
        obj = self._require(Bucket, Key)
        if VersionId is not None and VersionId != obj["VersionId"]:
            raise FakeS3ClientError("NoSuchKey")
        return {
            "Body": io.BytesIO(obj["Body"]), "VersionId": obj["VersionId"],
            "ChecksumSHA256": obj["ChecksumSHA256"],
        }

    def get_object_retention(self, *, Bucket, Key, VersionId=None):
        obj = self._require(Bucket, Key)
        return {"Retention": {"Mode": obj["Mode"], "RetainUntilDate": obj["RetainUntilDate"]}}

    def get_object_lock_configuration(self, *, Bucket):
        # 非破壞式讀:桶層 Object-Lock 設定;worm=True ⇒ ENABLED,否則 Disabled(不刪任何物件)。
        self.lock_config_reads += 1
        return {"ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled" if self.worm else "Disabled"
        }}

    def delete_object(self, *, Bucket, Key, VersionId=None):  # pragma: no cover - must NOT be called
        self.delete_calls += 1
        if self.worm:
            raise FakeS3ClientError("AccessDenied")
        self.objects.pop((Bucket, Key), None)
        return {"DeleteMarker": True}

    def put_object_retention(self, *, Bucket, Key, VersionId=None, Retention=None,
                             BypassGovernanceRetention=False):  # pragma: no cover - must NOT be called
        self.retention_write_calls += 1
        if self.worm and not BypassGovernanceRetention:
            raise FakeS3ClientError("AccessDenied")
        obj = self._require(Bucket, Key)
        obj["RetainUntilDate"] = Retention["RetainUntilDate"]
        return {}


def _apply(intent, client, *, actor=APPEND_ACTOR):
    return ext.apply_external_worm_append(
        intent, s3_client=client, append_actor_id=actor, terminal_payload=_payload(),
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )


# --------------------------------------------------------------------------- #
# contract build fail-closed
# --------------------------------------------------------------------------- #
def test_build_intent_binds_contract_and_validates() -> None:
    intent = _intent()
    assert intent["schema_version"] == "external_worm_append_intent_v1"
    assert intent["external_sink_id"] == "terminal_receipt_external_worm_sink_v1"
    assert intent["target_class"] == "external_worm"
    assert intent["destination_contract"]["object_lock_mode"] == "GOVERNANCE"
    assert intent["append_intent"]["target_class"] == "external_worm"
    assert ext.validate_external_worm_append_intent(intent, now=NOW) == []
    assert not sink._contains_secret_like(intent)


@pytest.mark.parametrize("field", list(ext.DESTINATION_CONTRACT_FIELDS))
def test_incomplete_contract_fails_closed_at_build(field) -> None:
    kwargs = dict(
        intent_id="intent-ext-worm-000002",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A, landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=sink.terminal_payload_digest(_payload()),
        append_actor_id=APPEND_ACTOR, approved_by="PM",
        approved_at=APPROVED_AT, expires_at=EXPIRES_AT,
        endpoint=ENDPOINT, region=REGION, bucket=BUCKET,
        object_lock_mode="GOVERNANCE", retain_until=RETAIN_UNTIL,
        credential_channel_id=CHANNEL,
    )
    kwargs[field] = "   "  # blank / missing non-secret identifier
    with pytest.raises(ext.ExternalWormContractError):
        ext.build_external_worm_append_intent(**kwargs)


def test_compliance_requires_operator_approval() -> None:
    # COMPLIANCE 未經 operator 核准 ⇒ fail-closed(GOVERNANCE 為 disposable 整合預設)。
    with pytest.raises(ext.ExternalWormContractError, match="COMPLIANCE"):
        _intent(object_lock_mode="COMPLIANCE", compliance_operator_approved=False)
    # 經核准則可建;validator 亦通過。
    approved = _intent(object_lock_mode="COMPLIANCE", compliance_operator_approved=True)
    assert approved["compliance_operator_approved"] is True
    assert ext.validate_external_worm_append_intent(approved, now=NOW) == []


def test_retain_until_must_be_after_approved_at() -> None:
    with pytest.raises(ext.ExternalWormContractError, match="retain_until"):
        _intent(retain_until="2026-07-22T08:00:00Z")


def test_secret_shaped_channel_id_fails_closed_at_build() -> None:
    # 機密樣態的 channel id 於 build 被機密掃描 fail-closed(片段拼接避免倉庫 secret scanner 誤報)。
    secret_channel = "author" + "ization=" + "x" * 20
    with pytest.raises(sink.SecretLeakageError):
        _intent(credential_channel_id=secret_channel)


# --------------------------------------------------------------------------- #
# fail-closed without an injected client / credentials -> typed PENDING
# --------------------------------------------------------------------------- #
def test_no_client_returns_typed_external_verification_pending() -> None:
    intent = _intent()
    result = ext.apply_external_worm_append(
        intent, s3_client=None, append_actor_id=APPEND_ACTOR,
        terminal_payload=_payload(), boto3_available=False,
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["external_verification_pending"] is True
    # 絕非假成功:未綁定任何 version/checksum/retention/record。
    assert result["record_locator"] is None
    assert result["object_version_id"] is None
    assert result["checksum_sha256"] is None
    assert result["retention"] is None
    assert "S8.6" in result["failure_reason"]
    # typed 結構有效,且無任何機密外洩。
    assert ext.validate_external_worm_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    ) == []
    assert not sink._contains_secret_like(result)
    assert "author" not in json.dumps(result)


def test_pending_request_lists_missing_non_secret_config_without_values() -> None:
    request = ext.external_verification_pending_request({"destination_contract": {
        "endpoint": ENDPOINT, "region": REGION,
    }})
    assert set(request["required_non_secret_config"]) == set(ext.DESTINATION_CONTRACT_FIELDS)
    assert "bucket" in request["missing_config"]
    assert "credential_channel_id" in request["missing_config"]
    assert request["config_presence"]["endpoint"] == "present"
    # 只列出存在性,不回傳任何值;無機密。
    assert not sink._contains_secret_like(request)
    assert ENDPOINT not in json.dumps(request)


# --------------------------------------------------------------------------- #
# injected client: successful append binds version_id + checksum + retention
# --------------------------------------------------------------------------- #
def test_injected_client_append_binds_version_checksum_retention() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    assert result["append_status"] == "APPENDED"
    assert result["object_version_id"] == client.objects[(BUCKET, result["record_locator"])][
        "VersionId"
    ]
    assert result["checksum_sha256"] == sink.terminal_payload_digest(_payload())
    assert result["retention"] == {
        "object_lock_mode": "GOVERNANCE", "retain_until": RETAIN_UNTIL,
    }
    assert result["external_verification_pending"] is False
    # put_object 真的帶了 ObjectLockMode/RetainUntilDate/ChecksumSHA256。
    b64 = base64.b64encode(
        hashlib.sha256(sink._canonical_bytes(_payload())).digest()
    ).decode("ascii")
    assert client.last_put_kwargs["ObjectLockMode"] == "GOVERNANCE"
    assert client.last_put_kwargs["ChecksumSHA256"] == b64
    assert isinstance(client.last_put_kwargs["ObjectLockRetainUntilDate"], datetime)
    assert ext.validate_external_worm_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    ) == []
    assert not sink._contains_secret_like(result)


def test_idempotent_retry_does_not_reput_or_mutate_committed_record() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    first = _apply(intent, client)
    stored_before = dict(client.objects[(BUCKET, first["record_locator"])])
    second = _apply(intent, client)
    assert first["append_status"] == "APPENDED"
    assert second["append_status"] == "IDEMPOTENT_DEDUP"
    # 冪等重試:put_object 只被呼叫一次,已 commit record 內容/版本完全未變。
    assert client.put_calls == 1
    assert client.objects[(BUCKET, first["record_locator"])] == stored_before
    assert second["object_version_id"] == first["object_version_id"]
    assert second["checksum_sha256"] == first["checksum_sha256"]


def test_content_substitution_on_existing_object_fails_closed() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    first = _apply(intent, client)
    # 竄改既有物件的 checksum(模擬內容替換);同 key 再 apply ⇒ FAILED,絕不佯稱去重。
    client.objects[(BUCKET, first["record_locator"])]["ChecksumSHA256"] = base64.b64encode(
        hashlib.sha256(b"substituted").digest()
    ).decode("ascii")
    second = _apply(intent, client)
    assert second["append_status"] == "FAILED"
    assert "substitution" in second["failure_reason"]


def test_wrong_append_actor_fails_closed() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client, actor="impostor")
    assert result["append_status"] == "FAILED"
    assert "append actor differs" in result["failure_reason"]
    assert client.put_calls == 0


def test_payload_digest_mismatch_fails_closed_without_put() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = ext.apply_external_worm_append(
        intent, s3_client=client, append_actor_id=APPEND_ACTOR,
        terminal_payload={"kind": "different-payload"},
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "FAILED"
    assert client.put_calls == 0


# --------------------------------------------------------------------------- #
# independent immutability-proving readback ACK
# --------------------------------------------------------------------------- #
def test_distinct_actor_readback_proves_immutability_and_acks() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    ack = ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["ack"] is True
    assert ack["same_actor_violation"] is False
    assert ack["checksum_match"] is True
    assert ack["version_id_match"] is True
    assert ack["retention_match"] is True
    # 不可變性由「非破壞式」config 讀證成:桶層 Object-Lock ENABLED。
    assert ack["object_lock_enabled"] is True
    assert ack["immutability_proven"] is True
    # E2 P2a:證明「非破壞」—— 絕不呼叫 delete_object / put_object_retention;物件仍在(未被刪)。
    assert client.delete_calls == 0
    assert client.retention_write_calls == 0
    assert client.lock_config_reads == 1
    assert (BUCKET, result["record_locator"]) in client.objects
    assert ext.validate_external_worm_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []
    assert not sink._contains_secret_like(ack)


def test_same_actor_readback_fails_closed() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    ack = ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=APPEND_ACTOR,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["same_actor_violation"] is True
    assert ack["ack"] is False
    assert ack["immutability_proven"] is False
    # 同一 actor:不讀任何物件、不下任何探針。
    assert client.delete_calls == 0
    assert client.retention_write_calls == 0
    assert client.lock_config_reads == 0
    assert ext.validate_external_worm_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []


def test_readback_against_non_locked_bucket_fails_closed() -> None:
    # 非 WORM 桶(Object-Lock 設定 Disabled)⇒ object_lock_enabled=False ⇒ proven=False ⇒ ack=False,
    # 且 E2 P2a:絕不用破壞式探針去「證」不可變 —— 已 commit 的 record 未被刪除。
    client = FakeObjectLockS3(worm=False)
    intent = _intent()
    result = _apply(intent, client)
    ack = ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["object_lock_enabled"] is False
    assert ack["immutability_proven"] is False
    assert ack["ack"] is False
    # 記錄未被破壞:no-ack 卻不摧毀 record。
    assert client.delete_calls == 0
    assert client.retention_write_calls == 0
    assert (BUCKET, result["record_locator"]) in client.objects
    assert ext.validate_external_worm_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []


def test_readback_against_expired_retention_fails_closed_non_destructively() -> None:
    # E3/E2 P2:保留期已過(retain_until<=now)⇒ retention_match=False ⇒ proven=False ⇒ ack=False,
    # 且不下任何破壞式操作。以直接把已存物件的 RetainUntilDate 改成過去,模擬過期保留桶。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    client.objects[(BUCKET, result["record_locator"])]["RetainUntilDate"] = datetime(
        2026, 7, 22, 9, 0, 0, tzinfo=timezone.utc
    )
    ack = ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["retention_match"] is False
    assert ack["immutability_proven"] is False
    assert ack["ack"] is False
    assert client.delete_calls == 0
    assert client.retention_write_calls == 0
    assert (BUCKET, result["record_locator"]) in client.objects
    assert ext.validate_external_worm_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []


# --------------------------------------------------------------------------- #
# P2(Codex): readback must verify observed retain_until >= approved retain_until
# --------------------------------------------------------------------------- #
def _readback(client, result, intent):
    return ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )


def test_readback_longer_observed_retention_still_acks() -> None:
    # observed retain_until 比核准更長(更不可變)⇒ retention_match=True ⇒ ack=True(>= 允許等值與更長)。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    client.objects[(BUCKET, result["record_locator"])]["RetainUntilDate"] = datetime(
        2028, 7, 22, 9, 0, 0, tzinfo=timezone.utc  # 比核准的 2027-07-22 更晚
    )
    ack = _readback(client, result, intent)
    assert ack["retention_match"] is True
    assert ack["ack"] is True


def test_readback_shorter_observed_retention_fails_closed() -> None:
    # store 接受寫入卻套用「較短的未來保留」⇒ observed < approved ⇒ retention_match=False ⇒ ack=False。
    # 這正是 Codex P2 指出的漏洞:舊實作只比 mode + 未來性,故較短保留仍能騙過不可變 ACK。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    # 核准的 retain_until=2027-07-22;改為 2026-08(仍在未來,但比核准短)。
    client.objects[(BUCKET, result["record_locator"])]["RetainUntilDate"] = datetime(
        2026, 8, 22, 9, 0, 0, tzinfo=timezone.utc
    )
    ack = _readback(client, result, intent)
    assert ack["retention_match"] is False
    assert ack["immutability_proven"] is False
    assert ack["ack"] is False
    assert client.delete_calls == 0 and client.retention_write_calls == 0  # 非破壞式


def test_readback_tz_normalized_equal_retention_acks() -> None:
    # 同一瞬時、不同時區表述(核准 2027-07-22T09:00Z == observed 2027-07-22T17:00+08:00)⇒ 視為相等 ⇒ ack。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    client.objects[(BUCKET, result["record_locator"])]["RetainUntilDate"] = datetime(
        2027, 7, 22, 17, 0, 0, tzinfo=timezone(timedelta(hours=8))
    )
    ack = _readback(client, result, intent)
    assert ack["retention_match"] is True
    assert ack["ack"] is True


def test_readback_malformed_observed_retention_fails_closed() -> None:
    # get_object_retention 回傳無法解析的 retain_until ⇒ retention_match=False ⇒ ack=False(fail-closed)。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    client.objects[(BUCKET, result["record_locator"])]["RetainUntilDate"] = "not-a-timestamp"
    ack = _readback(client, result, intent)
    assert ack["retention_match"] is False
    assert ack["ack"] is False


def test_idempotent_dedup_rejects_shorter_existing_retention() -> None:
    # dedup 既有物件亦須驗證 retention 不少於核准期限:既有物件被套較短保留 ⇒ 冪等重試 FAILED,絕不佯稱去重。
    client = FakeObjectLockS3()
    intent = _intent()
    first = _apply(intent, client)
    assert first["append_status"] == "APPENDED"
    # 把既有物件改成較短保留(仍在未來),再冪等重試。
    client.objects[(BUCKET, first["record_locator"])]["RetainUntilDate"] = datetime(
        2026, 8, 22, 9, 0, 0, tzinfo=timezone.utc
    )
    second = _apply(intent, client)
    assert second["append_status"] == "FAILED"
    assert "shorter than or different" in (second.get("failure_reason") or "")
    assert client.put_calls == 1  # 未重 put


def test_idempotent_dedup_accepts_equal_existing_retention() -> None:
    # 既有物件保留 == 核准 ⇒ 冪等去重仍成立(等值通過 >= 檢查)。
    client = FakeObjectLockS3()
    intent = _intent()
    first = _apply(intent, client)
    second = _apply(intent, client)
    assert second["append_status"] == "IDEMPOTENT_DEDUP"
    assert client.put_calls == 1


def test_idempotent_dedup_fails_closed_on_retention_read_error() -> None:
    # dedup 讀既有物件 retention 時拋錯 ⇒ fail-closed(FAILED),絕不佯稱去重(E4 gap)。
    class RaisingRetentionS3(FakeObjectLockS3):
        def get_object_retention(self, *, Bucket, Key, VersionId=None):
            raise FakeS3ClientError("AccessDenied")

    client = RaisingRetentionS3()
    intent = _intent()
    first = _apply(intent, client)
    assert first["append_status"] == "APPENDED"
    second = _apply(intent, client)
    assert second["append_status"] == "FAILED"
    assert "retention read failed" in (second.get("failure_reason") or "")
    assert client.put_calls == 1


def test_forged_same_actor_positive_ack_is_rejected_by_validator() -> None:
    # 手工偽造:綁定 append actor 卻自稱獨立且 immutability_proven=true、ack=true ⇒ validator 拒。
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    forged = {
        "schema_version": "external_worm_readback_ack_v1",
        "external_sink_id": "terminal_receipt_external_worm_sink_v1",
        "intent_id": result["intent_id"],
        "result_digest": result["result_digest"],
        "readback_verifier_id": APPEND_ACTOR,
        "read_record_locator": result["record_locator"],
        "read_object_version_id": result["object_version_id"],
        "readback_checksum_sha256": result["checksum_sha256"],
        "readback_retention": result["retention"],
        "checksum_match": True, "version_id_match": True, "retention_match": True,
        "object_lock_enabled": True, "immutability_proven": True,
        "ack": True, "same_actor_violation": False,
        "observed_at": "2026-07-22T10:00:05Z", "expires_at": "2026-07-22T10:30:05Z",
        "ack_digest": "sha256:" + "0" * 64,
    }
    forged["ack_digest"] = ext.external_ack_digest(forged)
    errors = ext.validate_external_worm_readback_ack(
        forged, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("must set same_actor_violation=true" in e for e in errors)
    assert any("cannot be issued by the bound append actor" in e for e in errors)


def test_immutability_proven_must_equal_conjunction() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    ack = ext.independent_readback_ack(
        result, intent, s3_client=client, verifier_actor_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )
    # 竄改一個證明布林但保留 immutability_proven=true ⇒ 一致性檢查拒。
    ack["object_lock_enabled"] = False
    ack["ack_digest"] = ext.external_ack_digest(ack)
    errors = ext.validate_external_worm_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("immutability_proven must equal" in e for e in errors)


# --------------------------------------------------------------------------- #
# result cross-binding + no real boto3 network
# --------------------------------------------------------------------------- #
def test_result_checksum_tamper_breaks_intent_binding() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    result = _apply(intent, client)
    result["checksum_sha256"] = "sha256:" + "e" * 64
    result["result_digest"] = ext.external_result_digest(result)
    errors = ext.validate_external_worm_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    )
    assert any("checksum is not bound to the approved intent payload digest" in e
               for e in errors)


def test_no_boto3_module_is_imported_by_apply(monkeypatch) -> None:
    # 保證 apply 不真的 import/建立 boto3 client(S1.2A 絕不觸網;真 append 在 S8.6)。
    import builtins

    real_import = builtins.__import__

    def _guard(name, *args, **kwargs):
        if name == "boto3" or name.startswith("boto3."):
            raise AssertionError("apply must not import boto3 (no real network in S1.2A)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guard)
    client = FakeObjectLockS3()
    intent = _intent()
    assert _apply(intent, client)["append_status"] == "APPENDED"
    # 無 client 的 PENDING 路徑亦不得 import boto3(僅 find_spec 探測)。
    pending = ext.apply_external_worm_append(
        intent, s3_client=None, append_actor_id=APPEND_ACTOR,
        terminal_payload=_payload(), boto3_available=False,
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert pending["append_status"] == "EXTERNAL_VERIFICATION_PENDING"


# --------------------------------------------------------------------------- #
# disposable sibling external_worm fail-close is UNCHANGED
# --------------------------------------------------------------------------- #
def test_disposable_sibling_still_rejects_external_worm() -> None:
    # 本 Wave 建 separate 模組,絕不放寬 disposable sibling 的 external_worm fail-close。
    disposable_intent = sink.build_terminal_receipt_append_intent(
        intent_id="intent-worm-unchanged-1",
        terminal_receipt_type="aiml_module_landed_for_trading_receipt_v1",
        final_source_head=HEAD_A, landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=sink.terminal_payload_digest(_payload()),
        append_actor_id="append-actor", approved_by="PM",
        approved_at=APPROVED_AT, expires_at=EXPIRES_AT,
        target_class="external_worm",
    )
    errors = sink.validate_terminal_receipt_append_intent(disposable_intent, now=NOW)
    assert any("external_worm is rejected fail-closed" in e for e in errors)
    with pytest.raises(sink.WormStoreError, match="external_worm is rejected at apply"):
        store = sink.new_disposable_store_dir()
        sink.apply_terminal_receipt_append(
            disposable_intent, store_dir=store, append_actor_id="append-actor",
            terminal_payload=_payload(),
            started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
        )


# --------------------------------------------------------------------------- #
# B2 P1 (E2+E3 converged): positive-format validation blocks AWS-shaped smuggling
# --------------------------------------------------------------------------- #
# 片段拼接,避免倉庫 secret scanner 誤報;皆為機密掃描漏接的 AWS 形狀。
AWS_SECRET_KEY = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"  # 40-char secret shape
AKIA_ID = "AKIA" + "IOSFODNN7" + "EXAMPLE"
AWS_KEY_ASSIGN = "aws_secret_" + "access_key=" + "wJalrXUtnFEMI"


def _build_full(**overrides) -> dict:
    kwargs = dict(
        intent_id="intent-ext-worm-smuggle-1",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A, landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=sink.terminal_payload_digest(_payload()),
        append_actor_id=APPEND_ACTOR, approved_by="PM",
        approved_at=APPROVED_AT, expires_at=EXPIRES_AT,
        endpoint=ENDPOINT, region=REGION, bucket=BUCKET,
        object_lock_mode="GOVERNANCE", retain_until=RETAIN_UNTIL,
        credential_channel_id=CHANNEL, now=NOW,
    )
    kwargs.update(overrides)
    return ext.build_external_worm_append_intent(**kwargs)


def _tampered_intent(**contract_overrides) -> dict:
    # 建一張合法 intent,再直接竄改 destination_contract 走私欄位並重簽,用於驗 validate 端 fail-closed。
    intent = _intent()
    intent["destination_contract"].update(contract_overrides)
    intent["external_intent_digest"] = ext.external_intent_digest(intent)
    return intent


@pytest.mark.parametrize("field,value", [
    ("credential_channel_id", AWS_SECRET_KEY),
    ("credential_channel_id", AKIA_ID),
    ("credential_channel_id", AWS_KEY_ASSIGN),
    ("endpoint", AWS_KEY_ASSIGN),
    ("endpoint", "http://" + AKIA_ID),          # 非 https
    ("bucket", AKIA_ID),                          # 大寫不符 S3 charset
    ("bucket", AWS_KEY_ASSIGN),                   # 底線/等號不符
    ("region", AKIA_ID),
    ("region", AWS_SECRET_KEY),
])
def test_aws_shaped_smuggle_rejected_at_build(field, value) -> None:
    with pytest.raises(ext.ExternalWormContractError, match="positive-format"):
        _build_full(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("credential_channel_id", AWS_SECRET_KEY),
    ("credential_channel_id", AKIA_ID),
    ("credential_channel_id", AWS_KEY_ASSIGN),
    ("endpoint", AWS_KEY_ASSIGN),
    ("bucket", AKIA_ID),
    ("region", AWS_SECRET_KEY),
])
def test_aws_shaped_smuggle_rejected_at_validate(field, value) -> None:
    intent = _tampered_intent(**{field: value})
    errors = ext.validate_external_worm_append_intent(intent, now=NOW)
    # 確有一則正向格式錯誤指名該欄位(validate 端亦 fail-closed)。
    assert any(field.split("_")[0] in e for e in errors)


def test_ssrf_metadata_endpoint_rejected_build_and_validate() -> None:
    # 169.254.169.254(cloud metadata)/私網/loopback/裸 IP/localhost 一律拒(SSRF/憑證重導防護)。
    for host in ("https://169.254.169.254", "https://10.0.0.5", "https://127.0.0.1",
                 "https://localhost", "https://192.168.1.1", "https://[::1]"):
        with pytest.raises(ext.ExternalWormContractError, match="positive-format"):
            _build_full(endpoint=host)
        tampered = _tampered_intent(endpoint=host)
        errors = ext.validate_external_worm_append_intent(tampered, now=NOW)
        assert any("endpoint host must not be" in e for e in errors)


@pytest.mark.parametrize("channel", [
    "aws-profile:aiml-s16b", "iam-role:aiml-s16b-writer",
    "sts-session:session-2026-07-22", "env-channel:aiml_worm",
])
def test_legitimate_channels_pass_build_and_validate(channel) -> None:
    intent = _build_full(credential_channel_id=channel)
    assert intent["destination_contract"]["credential_channel_id"] == channel
    assert ext.validate_external_worm_append_intent(intent, now=NOW) == []


def test_legitimate_endpoint_and_contract_pass() -> None:
    intent = _build_full(endpoint="https://s3.us-east-1.amazonaws.com")
    assert ext.validate_external_worm_append_intent(intent, now=NOW) == []


# --------------------------------------------------------------------------- #
# B2 P2 (E3): retain_until <= now rejected at build AND validate
# --------------------------------------------------------------------------- #
def test_retain_until_not_in_future_rejected_at_build() -> None:
    # retain_until 在 approved_at 之後但 <= now(過去/當下)⇒ 立即可刪 no-op ⇒ 拒。
    with pytest.raises(ext.ExternalWormContractError, match="future"):
        _build_full(retain_until="2026-07-22T09:30:00Z", now=NOW)


def test_retain_until_not_in_future_rejected_at_validate() -> None:
    intent = _tampered_intent(retain_until="2026-07-22T09:30:00Z")
    errors = ext.validate_external_worm_append_intent(intent, now=NOW)
    assert any("immediately-deletable no-op" in e for e in errors)


# --------------------------------------------------------------------------- #
# B2 P2 (E3): production terminal receipt types require operator-approved COMPLIANCE
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("receipt_type", sorted(ext.PRODUCTION_TERMINAL_RECEIPT_TYPES))
def test_production_receipt_requires_compliance_at_build(receipt_type) -> None:
    # GOVERNANCE 對生產終端 receipt 一律拒(僅 disposable-integration 類型可用 GOVERNANCE)。
    with pytest.raises(ext.ExternalWormContractError, match="COMPLIANCE"):
        _build_full(terminal_receipt_type=receipt_type, object_lock_mode="GOVERNANCE")
    # 未核准的 COMPLIANCE 亦拒。
    with pytest.raises(ext.ExternalWormContractError, match="COMPLIANCE"):
        _build_full(
            terminal_receipt_type=receipt_type, object_lock_mode="COMPLIANCE",
            compliance_operator_approved=False,
        )
    # operator-approved COMPLIANCE 才可建,且 validate 通過。
    approved = _build_full(
        terminal_receipt_type=receipt_type, object_lock_mode="COMPLIANCE",
        compliance_operator_approved=True,
    )
    assert ext.validate_external_worm_append_intent(approved, now=NOW) == []


def test_production_receipt_governance_rejected_at_validate() -> None:
    approved = _build_full(
        terminal_receipt_type="aiml_module_landed_for_trading_receipt_v1",
        object_lock_mode="COMPLIANCE", compliance_operator_approved=True,
    )
    # 竄改回 GOVERNANCE + 撤核准並重簽 ⇒ validate 端偵測生產型未綁 COMPLIANCE(base receipt_type 不動)。
    approved["destination_contract"]["object_lock_mode"] = "GOVERNANCE"
    approved["compliance_operator_approved"] = False
    approved["external_intent_digest"] = ext.external_intent_digest(approved)
    errors = ext.validate_external_worm_append_intent(approved, now=NOW)
    assert any("production terminal receipt type requires operator-approved COMPLIANCE" in e
               for e in errors)


# --------------------------------------------------------------------------- #
# E4 coverage: pending request / FAILED result branch / apply fail-closed branches
# --------------------------------------------------------------------------- #
def test_pending_request_content_and_non_dict_branch() -> None:
    request = ext.external_verification_pending_request({"destination_contract": {}})
    assert request["request_kind"] == "external_worm_verification_pending_request_v1"
    assert request["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert request["external_sink_id"] == ext.SINK_ID
    assert "NON-SECRET" in request["credential_channel_note"]
    assert "Object-Lock" in request["object_lock_requirement"]
    assert "S8.6" in request["external_binding_note"]
    assert set(request["missing_config"]) == set(ext.DESTINATION_CONTRACT_FIELDS)
    # non-dict intent 分支:contract 視為空 ⇒ 全部 MISSING(絕不因非 dict 崩潰)。
    non_dict = ext.external_verification_pending_request("not-an-object")
    assert set(non_dict["missing_config"]) == set(ext.DESTINATION_CONTRACT_FIELDS)
    assert non_dict["config_presence"]["endpoint"] == "MISSING"
    assert not sink._contains_secret_like(non_dict)


def test_validate_result_failed_branch() -> None:
    client = FakeObjectLockS3()
    intent = _intent()
    # payload-digest 不符 ⇒ FAILED,append actor 仍為核准者(可正常 cross-bind)。
    failed = ext.apply_external_worm_append(
        intent, s3_client=client, append_actor_id=APPEND_ACTOR,
        terminal_payload={"kind": "different-payload"},
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert failed["append_status"] == "FAILED"
    assert ext.validate_external_worm_append_result(
        failed, intent=intent, now="2026-07-22T10:00:05Z"
    ) == []
    # FAILED 卻聲稱 committed 欄位 ⇒ validator 拒。
    forged = dict(failed)
    forged["record_locator"] = "records/" + "a" * 64 + ".record"
    forged["result_digest"] = ext.external_result_digest(forged)
    errors = ext.validate_external_worm_append_result(
        forged, intent=intent, now="2026-07-22T10:00:05Z"
    )
    assert any("cannot claim record_locator" in e for e in errors)


def test_apply_rejects_secret_like_payload() -> None:
    secret_payload = {"kind": "x", "blob": "author" + "ization=" + "y" * 20}
    intent = _build_full(terminal_payload_digest=sink.terminal_payload_digest(secret_payload))
    client = FakeObjectLockS3()
    result = ext.apply_external_worm_append(
        intent, s3_client=client, append_actor_id=APPEND_ACTOR,
        terminal_payload=secret_payload,
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "FAILED"
    assert "secret-like" in result["failure_reason"]
    assert client.put_calls == 0
    assert not sink._contains_secret_like(result)


def test_apply_raises_on_invalid_intent() -> None:
    with pytest.raises(ext.ExternalWormContractError, match="invalid"):
        ext.apply_external_worm_append(
            {}, s3_client=FakeObjectLockS3(), append_actor_id=APPEND_ACTOR,
            terminal_payload=_payload(),
            started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
        )


def test_apply_fails_closed_on_non_404_head_error() -> None:
    class HeadErrorS3(FakeObjectLockS3):
        def head_object(self, *, Bucket, Key, ChecksumMode=None):
            raise FakeS3ClientError("AccessDenied")  # 非 404 ⇒ fail-closed,不佯稱新 commit

    client = HeadErrorS3()
    result = _apply(_intent(), client)
    assert result["append_status"] == "FAILED"
    assert "head_object failed" in result["failure_reason"]
    assert client.put_calls == 0


def test_apply_fails_closed_when_put_returns_no_version_id() -> None:
    class NoVersionS3(FakeObjectLockS3):
        def put_object(self, **kwargs):
            self.put_calls += 1
            return {}  # 無 VersionId ⇒ object-lock/versioning 未啟用 ⇒ FAILED

    client = NoVersionS3()
    result = _apply(_intent(), client)
    assert result["append_status"] == "FAILED"
    assert "no VersionId" in result["failure_reason"]
