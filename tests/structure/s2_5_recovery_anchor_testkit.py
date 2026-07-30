"""Authenticated recovery-anchor tests 的窄 boundary fakes。"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import aiml_gate_receipt_validator as validator
import agent_governance_s2_5_disposable_profile as profile


HEAD = "a" * 40
DIGEST = "sha256:" + "b" * 64
WRITER_FINGERPRINT = "sha256:" + "1" * 64
READER_FINGERPRINT = "sha256:" + "2" * 64
VERIFIER_FINGERPRINT = "sha256:" + "3" * 64
NOW = datetime(2030, 1, 1, 0, 2, tzinfo=timezone.utc)
ISSUED_AT = "2030-01-01T00:00:00+00:00"
EXPIRES_AT = "2030-01-01T00:05:00+00:00"

COMMON = {
    "evidence_class": profile.PROFILE_EVIDENCE_CLASS,
    "side_effect_class": profile.SIDE_EFFECT_CLASS,
    "target_class": profile.PROFILE_TARGET_CLASS,
    "target_profile_id": profile.PROFILE_ID,
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}


def seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(value)
    sealed["self_digest"] = validator.artifact_self_digest(sealed)
    return sealed


def identity(kind: str) -> dict[str, Any]:
    table = {
        "writer": (
            profile.ANCHOR_WRITER_ROLE,
            profile.ANCHOR_WRITER_UNIT,
            profile.ANCHOR_WRITER_CGROUP,
            WRITER_FINGERPRINT,
        ),
        "reader": (
            profile.ANCHOR_READER_ROLE,
            profile.ANCHOR_READER_UNIT,
            profile.ANCHOR_READER_CGROUP,
            READER_FINGERPRINT,
        ),
        "verifier": (
            profile.ANCHOR_VERIFIER_ROLE,
            profile.ANCHOR_VERIFIER_UNIT,
            profile.ANCHOR_VERIFIER_CGROUP,
            VERIFIER_FINGERPRINT,
        ),
    }
    role, unit, cgroup, fingerprint = table[kind]
    return {
        "role": role,
        "unit": unit,
        "cgroup": cgroup,
        "key_fingerprint": None,
    }


STATE_ROOT_IDENTITY = {
    "canonical_path": profile.DISPOSABLE_STATE_ROOT,
    "device": 1,
    "inode": 2,
    "mode": "0700",
    "uid": profile.PROFILE_UID,
    "gid": profile.PROFILE_GID,
    "nlink": 2,
    "is_directory": True,
}
STATE_ROOT_ID = validator.canonical_digest(STATE_ROOT_IDENTITY)
STORE_ID = "s2-5-store-" + validator.canonical_digest({
    "profile_id": profile.PROFILE_ID,
    "state_root_id": STATE_ROOT_ID,
}).removeprefix("sha256:")
EMPTY_JOURNAL_SET_DIGEST = validator.canonical_digest({
    "schema_version": "s2_5_recovery_journal_set_v1",
    "entries": [],
})


def manifest(*, generation: int = 1, phase: str = "PREPARED") -> dict[str, Any]:
    previous = None if generation == 1 else DIGEST
    unresolved = None if phase == "RESOLVED" else DIGEST
    anchor_head = None if phase == "PREPARED" else DIGEST
    consumed = ["s2-5-auth-" + "4" * 64] if phase == "RESOLVED" else []
    replay = {
        "basename": "authorization-replay-ledger.json",
        "present": bool(consumed),
        "file_digest": DIGEST if consumed else None,
        "entry_count": len(consumed),
        "head_digest": DIGEST if consumed else None,
    }
    return seal({
        "schema_version": "s2_5_recovery_store_manifest_v1",
        "store_id": STORE_ID,
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "generation": generation,
        "phase": phase,
        "previous_manifest_digest": previous,
        "unresolved_state_digest": unresolved,
        "anchor_head_digest": anchor_head,
        "consumed_authorization_ids": consumed,
        "state_root_identity": STATE_ROOT_IDENTITY,
        "journal_inventory": [],
        "journal_set_digest": EMPTY_JOURNAL_SET_DIGEST,
        "replay_ledger": replay,
        **{key: value for key, value in COMMON.items() if key != "evidence_class"},
    })


def head_digest(entry: dict[str, Any]) -> str:
    return validator.canonical_digest({
        "schema_version": "s2_5_recovery_anchor_head_v1",
        "sequence": entry["sequence"],
        "previous_anchor_digest": entry["previous_anchor_digest"],
        "entry_digest": entry["self_digest"],
    })


def entry(sequence: int, previous: str | None) -> dict[str, Any]:
    return seal({
        "schema_version": "s2_5_recovery_anchor_entry_v2",
        "anchor_store_id": profile.ANCHOR_STORE_ID,
        "anchor_collection_id": profile.ANCHOR_COLLECTION_ID,
        "store_id": STORE_ID,
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "sequence": sequence,
        "previous_anchor_digest": previous,
        "manifest_generation": sequence,
        "manifest_digest": validator.canonical_digest({
            "fixture_manifest_generation": sequence,
        }),
        "unresolved_state_digest": DIGEST,
        "authorization_id": None,
        "entry_status": "PREPARED",
        "append_actor_identity": identity("writer"),
        "appended_at": ISSUED_AT,
        "nonce": "s2-5-anchor-nonce-" + f"{sequence:064x}",
        **COMMON,
    })


def record(
    entry_value: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    sequence = entry_value["sequence"]
    if idempotency_key is None:
        idempotency_key = (
            "s2-5-anchor-idempotency-"
            + validator.canonical_digest({
                "fixture_entry_digest": entry_value["self_digest"],
            }).removeprefix("sha256:")
        )
    return {
        "object_id": "s2-5-anchor-object-" + f"{sequence:064x}",
        "version_id": "s2-5-anchor-version-" + f"{sequence:064x}",
        "idempotency_key": idempotency_key,
        "checksum": validator.canonical_digest(entry_value),
        "head_digest": head_digest(entry_value),
        "immutable": True,
        "retention_mode": "COMPLIANCE_WORM",
        "entry": copy.deepcopy(entry_value),
    }


def signed(
    payload: dict[str, Any],
    *,
    purpose: str,
    fingerprint: str = READER_FINGERPRINT,
) -> dict[str, Any]:
    return {
        "payload": copy.deepcopy(payload),
        "signer_key_fingerprint": fingerprint,
        "signature": validator.canonical_digest({
            "purpose": purpose,
            "signer_key_fingerprint": fingerprint,
            "payload_digest": payload["self_digest"],
        }),
    }


def chain(count: int = 3) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    previous = None
    for sequence in range(1, count + 1):
        current = entry(sequence, previous)
        current_record = record(current)
        records.append(current_record)
        previous = current_record["head_digest"]
    return records


def latest(records: list[dict[str, Any]], *, page_size: int = 2) -> dict[str, Any]:
    count = len(records)
    page_count = (count + page_size - 1) // page_size
    head = records[-1] if records else None
    snapshot_id = validator.canonical_digest({
        "record_heads": [item["head_digest"] for item in records],
    })
    return seal({
        "schema_version": "s2_5_recovery_anchor_latest_v1",
        "anchor_store_id": profile.ANCHOR_STORE_ID,
        "anchor_collection_id": profile.ANCHOR_COLLECTION_ID,
        "store_id": STORE_ID,
        "state_root_id": STATE_ROOT_ID,
        "source_head": HEAD,
        "snapshot_id": snapshot_id,
        "latest_version_id": "s2-5-anchor-version-" + "f" * 64,
        "sequence": count,
        "head_digest": head["head_digest"] if head else None,
        "head_object_id": head["object_id"] if head else None,
        "head_version_id": head["version_id"] if head else None,
        "entry_count": count,
        "page_count": page_count,
        "page_size": page_size,
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
        "signer_identity": identity("reader"),
        **COMMON,
    })


def pages(
    records: list[dict[str, Any]],
    latest_value: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    page_size = latest_value["page_size"]
    page_count = latest_value["page_count"]
    cursors = [
        "s2-5-anchor-cursor-" + f"{index:064x}"
        for index in range(1, page_count)
    ]
    for page_index in range(page_count):
        cursor_in = None if page_index == 0 else cursors[page_index - 1]
        cursor_out = None if page_index + 1 == page_count else cursors[page_index]
        result.append(seal({
            "schema_version": "s2_5_recovery_anchor_page_v1",
            "anchor_store_id": profile.ANCHOR_STORE_ID,
            "anchor_collection_id": profile.ANCHOR_COLLECTION_ID,
            "store_id": STORE_ID,
            "state_root_id": STATE_ROOT_ID,
            "source_head": HEAD,
            "snapshot_id": latest_value["snapshot_id"],
            "latest_version_id": latest_value["latest_version_id"],
            "latest_sequence": latest_value["sequence"],
            "latest_head_digest": latest_value["head_digest"],
            "entry_count": latest_value["entry_count"],
            "page_index": page_index,
            "page_count": page_count,
            "cursor_in": cursor_in,
            "cursor_out": cursor_out,
            "records": copy.deepcopy(
                records[page_index * page_size:(page_index + 1) * page_size]
            ),
            "issued_at": ISSUED_AT,
            "expires_at": EXPIRES_AT,
            "signer_identity": identity("reader"),
            **COMMON,
        }))
    return result


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.value = now
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self.value


class FakeVerifier:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def identity(self) -> dict[str, str]:
        return identity("verifier")

    def verify_signed(self, *, purpose: str, envelope: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(purpose)
        payload = envelope["payload"]
        fingerprint = envelope["signer_key_fingerprint"]
        expected = validator.canonical_digest({
            "purpose": purpose,
            "signer_key_fingerprint": fingerprint,
            "payload_digest": payload["self_digest"],
        })
        if envelope.get("signature") != expected:
            raise ValueError("signature_invalid")
        return copy.deepcopy(payload)


class FakeWriter:
    def identity(self) -> dict[str, str]:
        return identity("writer")

    def compare_append(self, *, request: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("pagination-only fixture must not append")


class FakeReader:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = copy.deepcopy(records)
        self.latest_value = latest(self.records)
        self.page_values = pages(self.records, self.latest_value)
        self.page_calls: list[tuple[str | None, str]] = []

    def identity(self) -> dict[str, str]:
        return identity("reader")

    def read_signed_latest(self) -> dict[str, Any]:
        return signed(self.latest_value, purpose="anchor_latest")

    def read_signed_page(
        self, *, cursor: str | None, snapshot_id: str
    ) -> dict[str, Any]:
        self.page_calls.append((cursor, snapshot_id))
        for page in self.page_values:
            if page["cursor_in"] == cursor:
                return signed(page, purpose="anchor_page")
        raise KeyError("cursor_unknown")

    def read_signed_exact(
        self, *, object_id: str, version_id: str
    ) -> dict[str, Any]:
        for item in self.records:
            if item["object_id"] == object_id and item["version_id"] == version_id:
                payload = seal({
                    "schema_version": "s2_5_recovery_anchor_exact_read_v1",
                    "record": copy.deepcopy(item),
                    "reader_identity": identity("reader"),
                    "issued_at": ISSUED_AT,
                    "expires_at": EXPIRES_AT,
                })
                return signed(payload, purpose="anchor_exact_read")
        raise KeyError("version_unknown")


class MutableAnchorBackend:
    """Fake WORM backend；append 只增不刪，reader 每次重建 signed snapshot。"""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = copy.deepcopy(records or [])
        self.idempotency: dict[str, dict[str, Any]] = {}
        self.delete_calls = 0


class MutableFakeReader:
    def __init__(self, backend: MutableAnchorBackend) -> None:
        self.backend = backend
        self.page_calls: list[tuple[str | None, str]] = []
        self.exact_calls: list[tuple[str, str]] = []

    def identity(self) -> dict[str, str]:
        return identity("reader")

    def _latest_and_pages(self):
        latest_value = latest(self.backend.records)
        return latest_value, pages(self.backend.records, latest_value)

    def read_signed_latest(self) -> dict[str, Any]:
        latest_value, _ = self._latest_and_pages()
        return signed(latest_value, purpose="anchor_latest")

    def read_signed_page(
        self, *, cursor: str | None, snapshot_id: str
    ) -> dict[str, Any]:
        self.page_calls.append((cursor, snapshot_id))
        _, page_values = self._latest_and_pages()
        for page in page_values:
            if page["cursor_in"] == cursor:
                return signed(page, purpose="anchor_page")
        raise KeyError("cursor_unknown")

    def read_signed_exact(
        self, *, object_id: str, version_id: str
    ) -> dict[str, Any]:
        self.exact_calls.append((object_id, version_id))
        for item in self.backend.records:
            if item["object_id"] == object_id and item["version_id"] == version_id:
                payload = seal({
                    "schema_version": "s2_5_recovery_anchor_exact_read_v1",
                    "anchor_store_id": profile.ANCHOR_STORE_ID,
                    "anchor_collection_id": profile.ANCHOR_COLLECTION_ID,
                    "record": copy.deepcopy(item),
                    "reader_identity": identity("reader"),
                    "issued_at": ISSUED_AT,
                    "expires_at": EXPIRES_AT,
                    "evidence_class": profile.PROFILE_EVIDENCE_CLASS,
                    "production_effect": False,
                    "production_effect_count": 0,
                })
                return signed(payload, purpose="anchor_exact_read")
        raise KeyError("version_unknown")


class AppendingFakeWriter:
    def __init__(
        self,
        backend: MutableAnchorBackend,
        *,
        response_status: str = "APPENDED",
    ) -> None:
        self.backend = backend
        self.response_status = response_status
        self.requests: list[dict[str, Any]] = []

    def identity(self) -> dict[str, str]:
        return identity("writer")

    def compare_append(self, *, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(copy.deepcopy(request))
        entry_value = request["entry"]
        idempotency_key = request["idempotency_key"]
        existing = self.backend.idempotency.get(idempotency_key)
        if self.response_status in {"CONFLICT", "HEAD_RACE", "ALREADY_EXISTS"}:
            response_record = None
            status = self.response_status
        elif existing is not None:
            response_record = existing
            status = "IDEMPOTENT_EXACT"
        else:
            response_record = record(
                entry_value,
                idempotency_key=idempotency_key,
            )
            self.backend.records.append(copy.deepcopy(response_record))
            self.backend.idempotency[idempotency_key] = copy.deepcopy(response_record)
            status = self.response_status
        payload = seal({
            "schema_version": "s2_5_recovery_anchor_compare_append_response_v1",
            "anchor_store_id": profile.ANCHOR_STORE_ID,
            "anchor_collection_id": profile.ANCHOR_COLLECTION_ID,
            "status": status,
            "idempotency_key": idempotency_key,
            "expected_latest_version_id": request["expected_latest_version_id"],
            "expected_sequence": request["expected_sequence"],
            "expected_head_digest": request["expected_head_digest"],
            "record": copy.deepcopy(response_record),
            "signer_identity": identity("writer"),
            "issued_at": ISSUED_AT,
            "expires_at": EXPIRES_AT,
            "evidence_class": profile.PROFILE_EVIDENCE_CLASS,
            "production_effect": False,
            "production_effect_count": 0,
        })
        return signed(
            payload,
            purpose="anchor_compare_append",
            fingerprint=WRITER_FINGERPRINT,
        )
