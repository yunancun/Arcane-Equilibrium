"""Disposable WORM-emulation proof for the S1.2 (LR0B) terminal-receipt sink.

Real OS semantics, nothing mocked and NO external service: an ``os.link`` atomic
commit into a temp-dir content-addressed store, ``chmod 0o444`` immutability, an
idempotency dedup driven by a genuine ``FileExistsError``, a distinct-actor
readback ACK, a same-actor refusal, an immutability prove-negative
(``PermissionError`` on rewrite), and interruption recovery (no committed record
⇒ key stays free ⇒ retryable).  The store is a ``tempfile`` dir torn down after
each test.  Runs everywhere with a POSIX filesystem (hardlinks + chmod); the
immutability-negative assertion is skipped only when running as root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_terminal_receipt_sink as worm  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


HEAD_A = "a" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
APPROVED_AT = "2026-07-22T09:00:00Z"
EXPIRES_AT = "2026-07-22T11:00:00Z"
APPEND_ACTOR = "append-actor"
VERIFIER = "independent-verifier"


@pytest.fixture()
def store_dir():
    # SHOULD-FIX 7:由 adapter 自有的建立函式產生私有 0o700 store(不交出 world-readable 目錄)。
    path = worm.new_disposable_store_dir()
    try:
        yield path
    finally:
        # 清理:committed record 是 0o444,rmtree 前先放寬權限確保可刪除。
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    os.chmod(os.path.join(root, name), 0o644)
                except OSError:
                    pass
        import shutil

        def _fail_loud(func, target, _exc_info):
            # SHOULD-FIX 6:清理失敗先 chmod+重試;仍失敗則 re-raise(未來目錄鎖變更 fail loud,
            # 不靜默洩漏 temp store)。取代舊 ignore_errors=True。
            os.chmod(target, 0o700)
            func(target)

        shutil.rmtree(path, onerror=_fail_loud)


def _payload() -> dict:
    return {"kind": "disposable_proof_payload_v1", "scope": DIGEST_A}


def _intent(intent_id: str = "intent-worm-disposable-1") -> dict:
    return worm.build_terminal_receipt_append_intent(
        intent_id=intent_id,
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=worm.terminal_payload_digest(_payload()),
        append_actor_id=APPEND_ACTOR,
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
    )


def _apply(intent, store_dir, *, offset: int, **kwargs):
    started = f"2026-07-22T10:0{offset}:00Z"
    completed = f"2026-07-22T10:0{offset}:01Z"
    return worm.apply_terminal_receipt_append(
        intent, store_dir=store_dir, append_actor_id=APPEND_ACTOR,
        terminal_payload=_payload(), started_at=started, completed_at=completed,
        **kwargs,
    )


def test_first_append_commits_one_immutable_record(store_dir) -> None:
    intent = _intent()
    result = _apply(intent, store_dir, offset=0)
    assert result["append_status"] == "APPENDED"
    record_path = Path(store_dir) / result["record_locator"]
    assert record_path.is_file()
    # immutable-after-write:真實 chmod 0o444。
    mode = record_path.stat().st_mode & 0o777
    assert mode == 0o444
    # tmp 已清空(無 orphan)。
    assert list((Path(store_dir) / "tmp").iterdir()) == []
    assert worm.validate_terminal_receipt_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    ) == []


def test_second_append_same_key_is_idempotent_dedup(store_dir) -> None:
    intent = _intent()
    first = _apply(intent, store_dir, offset=0)
    second = _apply(intent, store_dir, offset=1)
    assert first["append_status"] == "APPENDED"
    assert second["append_status"] == "IDEMPOTENT_DEDUP"
    # 去重後 records/ 仍恰好一個檔案。
    records = list((Path(store_dir) / "records").iterdir())
    assert len(records) == 1
    # 兩者綁同一 idempotency key,且 dedup 回讀的 payload digest 相同。
    assert first["idempotency_key"] == second["idempotency_key"]
    assert second["persisted_payload_digest"] == first["persisted_payload_digest"]


def test_readback_payload_hash_binds_and_distinct_actor_acks(store_dir) -> None:
    intent = _intent()
    result = _apply(intent, store_dir, offset=0)
    ack = worm.readback_terminal_receipt(
        result, store_dir=store_dir, readback_verifier_id=VERIFIER,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["ack"] is True
    assert ack["same_actor_violation"] is False
    # readback 以 record bytes 重算,必等於 result.persisted_payload_digest。
    assert ack["readback_payload_digest"] == result["persisted_payload_digest"]
    assert worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []


def test_same_actor_readback_is_refused(store_dir) -> None:
    intent = _intent()
    result = _apply(intent, store_dir, offset=0)
    ack = worm.readback_terminal_receipt(
        result, store_dir=store_dir, readback_verifier_id=APPEND_ACTOR,
        observed_at="2026-07-22T10:00:05Z",
    )
    assert ack["same_actor_violation"] is True
    assert ack["ack"] is False
    # 同一 actor 讀回:仍是結構有效的 ack(拒絕記錄),central validator 接受其形態。
    assert validator.validate_aiml_artifact(ack, now="2026-07-22T10:00:06Z") == []


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root can write through 0o444; immutability negative only holds for non-root",
)
def test_committed_record_is_immutable_prove_negative(store_dir) -> None:
    intent = _intent()
    result = _apply(intent, store_dir, offset=0)
    record_path = Path(store_dir) / result["record_locator"]
    before = record_path.read_bytes()
    observation = worm.attempt_record_rewrite(str(record_path))
    # 改寫 0o444 record 應觸 PermissionError ⇒ immutable=True。
    assert observation["immutable"] is True
    assert observation["observed_error"] == "PermissionError"
    # record 內容未被更動。
    assert record_path.read_bytes() == before


def test_interruption_commits_no_record_and_key_stays_retryable(store_dir) -> None:
    intent = _intent()
    interrupted = _apply(intent, store_dir, offset=0, simulate_interruption=True)
    assert interrupted["append_status"] == "ROLLED_BACK_INTERRUPTED"
    assert interrupted["record_locator"] is None
    assert interrupted["immutable_after_write"] is False
    # 中斷未 commit 任何 record ⇒ records/ 空,idempotency key 仍空缺。
    assert list((Path(store_dir) / "records").iterdir()) == []
    # 同 key 重試:乾淨 append 成功(WORM 從不改寫已 commit 的 record)。
    retried = _apply(intent, store_dir, offset=2)
    assert retried["append_status"] == "APPENDED"
    assert (Path(store_dir) / retried["record_locator"]).is_file()


def test_payload_digest_mismatch_fails_closed_without_committing(store_dir) -> None:
    intent = _intent()
    # 送入與 intent 綁定 digest 不符的 payload ⇒ FAILED,絕不 commit。
    result = worm.apply_terminal_receipt_append(
        intent, store_dir=store_dir, append_actor_id=APPEND_ACTOR,
        terminal_payload={"kind": "different-payload"},
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "FAILED"
    assert result["record_locator"] is None
    assert list((Path(store_dir) / "records").iterdir()) == []


def test_wrong_append_actor_fails_closed(store_dir) -> None:
    intent = _intent()
    result = worm.apply_terminal_receipt_append(
        intent, store_dir=store_dir, append_actor_id="impostor-actor",
        terminal_payload=_payload(),
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "FAILED"
    assert "append actor differs" in result["failure_reason"]
    assert list((Path(store_dir) / "records").iterdir()) == []


def test_self_created_store_is_private_0o700(tmp_path) -> None:
    # FIX 1(E3 P2):store_dir 不預先存在 ⇒ adapter 自建為私有 0o700(umask-proof),
    # 使 committed 的 0o444 record 不因可 traverse 的 0o755 目錄而 world/group-readable。
    fresh = tmp_path / "auto-created" / "worm-store"
    assert not fresh.exists()
    intent = _intent()
    result = worm.apply_terminal_receipt_append(
        intent, store_dir=str(fresh), append_actor_id=APPEND_ACTOR,
        terminal_payload=_payload(),
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "APPENDED"
    # 自建 store 一律 0o700(而非 umask 下的 0o755)。
    store_mode = os.stat(fresh).st_mode & 0o777
    assert store_mode == 0o700
    # record 本身仍是 immutable 0o444,但其 group/other 可達性由私有 store 目錄把關:
    # store 無 group/other 位 ⇒ 記錄不可被 group/other 讀取(effective not world/group-readable)。
    record_path = fresh / result["record_locator"]
    assert (record_path.stat().st_mode & 0o777) == 0o444
    record_world_group_readable = bool(store_mode & 0o077) and bool(
        record_path.stat().st_mode & 0o044
    )
    assert record_world_group_readable is False


def test_preexisting_group_readable_store_is_rejected_fail_closed(tmp_path) -> None:
    # FIX 1(E3 P2):既有 0o755(group/other 可存取)store ⇒ apply UNCONDITIONAL 斷言拒絕,
    # 不替呼叫端「修正」一個 world-readable 目錄,亦不寫入任何 record。
    loose = tmp_path / "loose-store"
    loose.mkdir()
    os.chmod(loose, 0o755)
    intent = _intent()
    with pytest.raises(worm.WormStoreError, match="must be private 0o700"):
        worm.apply_terminal_receipt_append(
            intent, store_dir=str(loose), append_actor_id=APPEND_ACTOR,
            terminal_payload=_payload(),
            started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
        )
    assert not (loose / "records").exists()


def test_preseeded_symlink_record_dedup_fails_closed_structured(store_dir) -> None:
    # FIX 2(E2 minor #1):在派生 key 路徑預植入 symlink,dedup 讀檔以 O_NOFOLLOW 觸 OSError(ELOOP)。
    # 必須回結構化 FAILED(而非拋未處理的 OSError),與 readback 讀檔失敗的處理對稱。
    intent = _intent()
    record_rel = worm._record_relative_locator(intent["idempotency_key"])
    record_path = Path(store_dir) / record_rel
    (Path(store_dir) / "records").mkdir(parents=True, exist_ok=True)
    # 預植入 symlink 佔用該 key(指向 store 外路徑;O_NOFOLLOW 應拒絕跟隨,不論 target 是否存在)。
    os.symlink("/nonexistent-worm-escape-target", record_path)
    result = _apply(intent, store_dir, offset=0)
    assert result["append_status"] == "FAILED"
    assert result["record_locator"] is None
    assert "not a regular readable file" in result["failure_reason"]


def test_preseeded_mismatched_record_dedup_fails_closed(store_dir) -> None:
    # P1-B:在派生 key 路徑植入「內容不符」的 record,dedup 不得佯稱 IDEMPOTENT_DEDUP 成功。
    intent = _intent()
    first = _apply(intent, store_dir, offset=0)
    assert first["append_status"] == "APPENDED"
    record_path = Path(store_dir) / first["record_locator"]
    # 竄改既有 record 內容(放寬→改寫→復原 0o444),模擬內容替換/預植入。
    os.chmod(record_path, 0o644)
    record_path.write_bytes(b"substituted-content-not-the-approved-payload")
    os.chmod(record_path, 0o444)
    # 同 key 再 apply:偵測既有內容 digest ≠ 核准 digest ⇒ FAILED(非 IDEMPOTENT_DEDUP)。
    second = _apply(intent, store_dir, offset=1)
    assert second["append_status"] == "FAILED"
    assert "substitution" in second["failure_reason"]
    assert second["record_locator"] is None


def test_readback_rejects_store_escape_locator_before_any_read(store_dir) -> None:
    # P2-A:未清洗的 record_locator(絕對路徑 / .. 逃逸 / 非 digest 檔名)必須在任何讀檔前被拒。
    intent = _intent()
    result = _apply(intent, store_dir, offset=0)
    for evil in ("/etc/passwd", "../../etc/passwd", "records/not-a-digest.record"):
        poisoned = dict(result)
        poisoned["record_locator"] = evil
        ack = worm.readback_terminal_receipt(
            poisoned, store_dir=store_dir, readback_verifier_id=VERIFIER,
            observed_at="2026-07-22T10:00:05Z",
        )
        # 形狀不合 ⇒ 不讀任何檔:無 read locator、無 digest、不 ack(fail-closed)。
        assert ack["read_record_locator"] is None
        assert ack["readback_payload_digest"] is None
        assert ack["ack"] is False


def test_secret_shaped_payload_commits_no_record_and_fails_closed(store_dir) -> None:
    # P2-B:payload 帶機密樣態 ⇒ FAILED,絕不寫入不可變 WORM record。機密樣態字串於 runtime
    # 由片段拼接,避免公開倉庫 secret scanner / gitleaks 對測試檔誤報(參 S1.1 DSN 片段作法)。
    secret_value = "pass" + "word=" + "s3cr3t-not-a-real-credential"
    payload = {"kind": "disposable_proof_payload_v1", "leak": secret_value}
    intent = worm.build_terminal_receipt_append_intent(
        intent_id="intent-worm-secret-1",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=worm.terminal_payload_digest(payload),
        append_actor_id=APPEND_ACTOR,
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
    )
    result = worm.apply_terminal_receipt_append(
        intent, store_dir=store_dir, append_actor_id=APPEND_ACTOR,
        terminal_payload=payload,
        started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
    )
    assert result["append_status"] == "FAILED"
    assert "secret-like content" in result["failure_reason"]
    assert list((Path(store_dir) / "records").iterdir()) == []


def test_apply_rejects_external_worm_target(store_dir) -> None:
    # SHOULD-FIX 7:disposable adapter 於 apply 亦拒絕 external_worm(不僅在 validate)。
    intent = worm.build_terminal_receipt_append_intent(
        intent_id="intent-worm-ext-1",
        terminal_receipt_type="aiml_module_landed_for_trading_receipt_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=worm.terminal_payload_digest(_payload()),
        append_actor_id=APPEND_ACTOR,
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
        target_class="external_worm",
    )
    with pytest.raises(worm.WormStoreError, match="external_worm is rejected at apply"):
        worm.apply_terminal_receipt_append(
            intent, store_dir=store_dir, append_actor_id=APPEND_ACTOR,
            terminal_payload=_payload(),
            started_at="2026-07-22T10:00:00Z", completed_at="2026-07-22T10:00:01Z",
        )
    records = Path(store_dir) / "records"
    assert not records.exists() or list(records.iterdir()) == []
