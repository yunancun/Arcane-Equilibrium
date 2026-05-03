"""ReplayQuotaEnforcer pytest — 5 cap behaviours pinned with in-memory cursor.
ReplayQuotaEnforcer pytest — 用 in-memory cursor 釘 5 條 cap 行為。

MODULE_NOTE (EN): REF-20 R20-P2a-S5 (Wave 3 Batch 3A). Pins five
  load-bearing behaviours of the quota enforcer via a hand-rolled
  in-memory fake cursor that simulates the V3 §4.1 replay schema:
    1. per-actor active manifest cap (=20) → 20-th create rejected
    2. per-actor active run cap (=1) → 2nd start rejected
    3. global active run cap (=1) → another actor's 2nd start rejected
    4. env-specific storage cap → over-cap rejected
    5. mark_manifest_expired → flips expires_at + idempotent
  Avoids spinning up real PostgreSQL; tests must be runnable on the Mac
  dev path where psycopg2 is installed but no PG instance exists.

MODULE_NOTE (中): REF-20 R20-P2a-S5（Wave 3 Batch 3A）。用手寫
  in-memory fake cursor 釘死 5 條 load-bearing 行為，模擬 V3 §4.1 replay
  schema：
    1. per-actor active manifest cap（=20）→ 第 20 次 create 拒絕
    2. per-actor active run cap（=1）→ 第二次 start 拒絕
    3. global active run cap（=1）→ 其他 actor 也拒絕
    4. env-specific storage cap → 超 cap 拒絕
    5. mark_manifest_expired → 翻 expires_at + 冪等
  不需要真 PostgreSQL；Mac dev 路徑（psycopg2 裝了但無 PG instance）
  能跑。

Tests / 測試覆蓋:
  1. test_per_actor_manifest_cap_enforced
  2. test_per_actor_run_cap_enforced
  3. test_global_run_cap_enforced
  4. test_env_storage_cap_enforced
  5. test_mark_manifest_expired_ttl_flip
"""
from __future__ import annotations

from typing import Any

import pytest


# conftest.py at tests/ root sets PROJECT_ROOT = control_api_v1 + appends
# to sys.path; sibling `tests/replay/test_manifest_signer_xlang_consistency.py`
# uses `from replay.manifest_signer import ...`. Follow same pattern here.
# tests/ 根的 conftest.py 設 PROJECT_ROOT = control_api_v1 並加入 sys.path；
# sibling test 用 `from replay.manifest_signer import ...`，本檔同 pattern。
from replay.quota_enforcer import (  # noqa: E402
    DEFAULT_ARTIFACT_STORAGE_CAP_MB,
    GLOBAL_ACTIVE_RUN_CAP,
    PER_ACTOR_ACTIVE_MANIFEST_CAP,
    PER_ACTOR_ACTIVE_RUN_CAP,
    QuotaCheckResult,
    ReplayQuotaEnforcer,
    ReplayQuotaExceededError,
)


# ─── In-memory fake cursor / 記憶體假 cursor ─────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for quota enforcer unit tests.
    Quota enforcer 單元測試最小 psycopg2-相容 cursor。

    Tracks executed SQL + params for assertions; returns canned
    `fetchone()` / `fetchall()` based on the SQL pattern (information_schema
    probe vs COUNT vs SUM vs SELECT-by-id vs UPDATE-RETURNING). Tests
    assemble cursor with the schema state they want to simulate.

    記錄已 execute 的 SQL + params 供 assert；依 SQL pattern 回 canned
    fetchone/fetchall（schema probe、COUNT、SUM、SELECT-by-id、
    UPDATE-RETURNING）。測試組裝想模擬的 schema state。
    """

    def __init__(
        self,
        experiments_present: bool = True,
        artifacts_present: bool = True,
        active_manifests_per_actor: dict[str, int] | None = None,
        active_runs_per_actor: dict[str, int] | None = None,
        active_runs_global: int = 0,
        storage_used_bytes_per_env: dict[str, int] | None = None,
        existing_manifest_ids: set[str] | None = None,
    ) -> None:
        self.experiments_present = experiments_present
        self.artifacts_present = artifacts_present
        self.active_manifests_per_actor = active_manifests_per_actor or {}
        self.active_runs_per_actor = active_runs_per_actor or {}
        self.active_runs_global = active_runs_global
        self.storage_used_bytes_per_env = storage_used_bytes_per_env or {}
        self.existing_manifest_ids = existing_manifest_ids or set()
        self.flipped_manifest_ids: set[str] = set()
        self.executed: list[tuple[str, Any]] = []
        self._next_fetchone: Any = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        sql_lower = sql.lower()

        # information_schema probe / information_schema 偵測。
        if "information_schema.tables" in sql_lower:
            if params and "experiments" in params:
                self._next_fetchone = (1,) if self.experiments_present else None
            elif params and "report_artifacts" in params:
                self._next_fetchone = (1,) if self.artifacts_present else None
            else:
                self._next_fetchone = None
            return

        # COUNT(*) per actor manifest. / COUNT(*) per actor manifest。
        if (
            "select count(*)" in sql_lower
            and "replay.experiments" in sql_lower
            and "created_by" in sql_lower
            and "expires_at" in sql_lower
            and "status" in sql_lower
        ):
            actor_id = params[0] if params else ""
            count = self.active_manifests_per_actor.get(actor_id, 0)
            self._next_fetchone = (count,)
            return

        # COUNT(*) per actor run. / COUNT(*) per actor run。
        if (
            "select count(*)" in sql_lower
            and "replay.experiments" in sql_lower
            and "created_by" in sql_lower
            and "status in ('created', 'running')" in sql_lower
        ):
            actor_id = params[0] if params else ""
            count = self.active_runs_per_actor.get(actor_id, 0)
            self._next_fetchone = (count,)
            return

        # COUNT(*) global run. / COUNT(*) global run。
        if (
            "select count(*)" in sql_lower
            and "replay.experiments" in sql_lower
            and "status in ('created', 'running')" in sql_lower
            and "created_by" not in sql_lower
        ):
            self._next_fetchone = (self.active_runs_global,)
            return

        # SUM(bytes) for storage cap. / SUM(bytes) for storage cap。
        if (
            "select coalesce(sum(ra.bytes), 0)" in sql_lower
            or "select coalesce(sum(ra.bytes),0)" in sql_lower
        ):
            env_str = params[0] if params else ""
            used = self.storage_used_bytes_per_env.get(env_str, 0)
            self._next_fetchone = (used,)
            return

        # UPDATE replay.experiments SET expires_at=NOW() RETURNING ...
        # mark_manifest_expired flow.
        if (
            "update replay.experiments" in sql_lower
            and "set expires_at" in sql_lower
            and "returning experiment_id" in sql_lower
        ):
            manifest_id = params[0] if params else ""
            if manifest_id in self.existing_manifest_ids and manifest_id not in self.flipped_manifest_ids:
                self.flipped_manifest_ids.add(manifest_id)
                self._next_fetchone = (manifest_id,)
            else:
                # Already expired or not present.
                self._next_fetchone = None
            return

        # Default: nothing to fetch. / 預設：無 fetch。
        self._next_fetchone = None

    def fetchone(self) -> Any:
        return self._next_fetchone


# ─── Fixtures / 固件 ─────────────────────────────────────────────────


@pytest.fixture
def enforcer(monkeypatch: pytest.MonkeyPatch) -> ReplayQuotaEnforcer:
    """Construct enforcer; clear env var override for default cap baseline.
    建構 enforcer；清掉 env var override，用預設 cap 為 baseline。

    Uses default cap from constants (1024 MB) so tests assert against
    the spec invariant (1024 MB) rather than env-tunable; env override
    test exercised separately.

    用預設 cap（1024 MB），測試針對 spec invariant assert，env override
    路徑在獨立測試覆蓋。
    """
    monkeypatch.delenv(
        "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", raising=False
    )
    return ReplayQuotaEnforcer()


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_per_actor_manifest_cap_enforced(
    enforcer: ReplayQuotaEnforcer,
) -> None:
    """V3 §5: per-actor active manifests = 20.
    actor with 19 active → PASS; actor with 20 active → REJECT.

    V3 §5：per-actor active manifests = 20。
    actor 已有 19 → 通過；actor 已有 20 → 拒絕。
    """
    # 19 active → PASS, remaining=1.
    cur_pass = _FakeCursor(active_manifests_per_actor={"alice": 19})
    result = enforcer.enforce_manifest_create(cur_pass, "alice")
    assert isinstance(result, QuotaCheckResult)
    assert result.quota_kind == "manifest_per_actor"
    assert result.current == 19
    assert result.cap == PER_ACTOR_ACTIVE_MANIFEST_CAP == 20
    assert result.remaining == 1
    assert result.schema_present is True

    # 20 active → REJECT.
    cur_reject = _FakeCursor(active_manifests_per_actor={"alice": 20})
    with pytest.raises(ReplayQuotaExceededError) as exc_info:
        enforcer.enforce_manifest_create(cur_reject, "alice")
    assert exc_info.value.quota_kind == "manifest_per_actor"
    assert exc_info.value.actor_or_env == "alice"
    assert exc_info.value.current == 20
    assert exc_info.value.cap == 20

    # Schema absent → graceful permit (count=0).
    # Schema 缺 → graceful 放行（count=0）。
    cur_absent = _FakeCursor(experiments_present=False)
    result_absent = enforcer.enforce_manifest_create(cur_absent, "alice")
    assert result_absent.schema_present is False
    assert result_absent.current == 0
    assert result_absent.remaining == PER_ACTOR_ACTIVE_MANIFEST_CAP


def test_per_actor_run_cap_enforced(enforcer: ReplayQuotaEnforcer) -> None:
    """V3 §5: per-actor active runs = 1.
    actor with 0 active runs → PASS; actor with 1 active → REJECT
    (per-actor takes precedence over global check).

    V3 §5：per-actor active runs = 1。
    actor 0 active → 通過；actor 1 active → 拒絕（per-actor 優先 global）。
    """
    # 0 per-actor + 0 global → PASS.
    cur_pass = _FakeCursor(
        active_runs_per_actor={"bob": 0}, active_runs_global=0
    )
    result = enforcer.enforce_run_start(cur_pass, "bob")
    assert result.quota_kind == "run_per_actor"
    assert result.current == 0
    assert result.cap == PER_ACTOR_ACTIVE_RUN_CAP == 1
    assert result.remaining == 1
    assert result.schema_present is True

    # 1 per-actor → REJECT (run_per_actor) BEFORE global check.
    # 1 per-actor → 拒絕（run_per_actor），global 檢查在前 raise 前不執行。
    cur_reject_actor = _FakeCursor(
        active_runs_per_actor={"bob": 1}, active_runs_global=1
    )
    with pytest.raises(ReplayQuotaExceededError) as exc_info:
        enforcer.enforce_run_start(cur_reject_actor, "bob")
    assert exc_info.value.quota_kind == "run_per_actor"
    assert exc_info.value.actor_or_env == "bob"

    # Schema absent → graceful permit.
    cur_absent = _FakeCursor(experiments_present=False)
    result_absent = enforcer.enforce_run_start(cur_absent, "bob")
    assert result_absent.schema_present is False


def test_global_run_cap_enforced(enforcer: ReplayQuotaEnforcer) -> None:
    """V3 §5: global active runs = 1 in P2/P3.
    actor=carol with 0 own active + 1 global other → REJECT (run_global).

    V3 §5：global active runs = 1 in P2/P3。
    actor=carol 自己 0 active + 1 global（他人）→ 拒絕（run_global）。
    """
    # carol has 0 of her own; another actor holds the global slot.
    # carol 自己 0；其他 actor 持有 global slot。
    cur = _FakeCursor(
        active_runs_per_actor={"carol": 0}, active_runs_global=1
    )
    with pytest.raises(ReplayQuotaExceededError) as exc_info:
        enforcer.enforce_run_start(cur, "carol")
    # Per-actor PASS first; global REJECT second.
    # Per-actor 先通過；global 後拒絕。
    assert exc_info.value.quota_kind == "run_global"
    assert exc_info.value.actor_or_env == "<global>"
    assert exc_info.value.current == 1
    assert exc_info.value.cap == GLOBAL_ACTIVE_RUN_CAP == 1


def test_env_storage_cap_enforced(enforcer: ReplayQuotaEnforcer) -> None:
    """V3 §5: artifact storage cap = env-specific (default 1024 MB).
    env=linux_trade_core under cap → PASS; over cap → REJECT.

    V3 §5：artifact storage cap = env-specific（預設 1024 MB）。
    env=linux_trade_core 未超 → 通過；超 → 拒絕。
    """
    # 500 MB used (well under 1024 MB cap) → PASS.
    # 500 MB 已用（遠低於 1024 MB cap）→ 通過。
    cur_pass = _FakeCursor(
        storage_used_bytes_per_env={
            "linux_trade_core": 500 * 1024 * 1024
        }
    )
    result = enforcer.enforce_artifact_storage(cur_pass, "linux_trade_core")
    assert result.quota_kind == "storage_env"
    assert result.current == 500  # MB
    assert result.cap == DEFAULT_ARTIFACT_STORAGE_CAP_MB == 1024
    assert result.remaining == 524
    assert result.schema_present is True

    # 1500 MB used → REJECT.
    # 1500 MB 已用 → 拒絕。
    cur_reject = _FakeCursor(
        storage_used_bytes_per_env={
            "linux_trade_core": 1500 * 1024 * 1024
        }
    )
    with pytest.raises(ReplayQuotaExceededError) as exc_info:
        enforcer.enforce_artifact_storage(cur_reject, "linux_trade_core")
    assert exc_info.value.quota_kind == "storage_env"
    assert exc_info.value.actor_or_env == "linux_trade_core"
    assert exc_info.value.current == 1500
    assert exc_info.value.cap == 1024

    # Schema absent → graceful permit.
    cur_absent = _FakeCursor(artifacts_present=False)
    result_absent = enforcer.enforce_artifact_storage(
        cur_absent, "linux_trade_core"
    )
    assert result_absent.schema_present is False
    assert result_absent.current == 0
    assert result_absent.remaining == DEFAULT_ARTIFACT_STORAGE_CAP_MB

    # Env var override / Env var override。
    import os as _os

    _os.environ["OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB"] = "2048"
    try:
        # New enforcer picks up new cap. / 新 enforcer 取新 cap。
        enforcer_2gb = ReplayQuotaEnforcer()
        assert enforcer_2gb.storage_cap_mb == 2048
        # 1500 MB used + 2048 MB cap → PASS now.
        # 1500 MB 已用 + 2048 MB cap → 此時通過。
        cur_pass_2gb = _FakeCursor(
            storage_used_bytes_per_env={
                "linux_trade_core": 1500 * 1024 * 1024
            }
        )
        result_pass = enforcer_2gb.enforce_artifact_storage(
            cur_pass_2gb, "linux_trade_core"
        )
        assert result_pass.cap == 2048
        assert result_pass.remaining == 548
    finally:
        _os.environ.pop("OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", None)


def test_mark_manifest_expired_ttl_flip(
    enforcer: ReplayQuotaEnforcer,
) -> None:
    """V3 §5: manifest TTL = 30 days default.
    mark_manifest_expired:
      - existing manifest → flip + return True
      - non-existent / already-flipped → return False (idempotent)
      - schema absent → return False (graceful no-op)

    V3 §5：manifest TTL = 30 days default。
    mark_manifest_expired:
      - 存在 manifest → 翻轉 + return True
      - 不存在 / 已翻過 → return False（冪等）
      - schema 缺 → return False（graceful no-op）
    """
    cur = _FakeCursor(
        existing_manifest_ids={"manifest-001", "manifest-002"}
    )

    # Existing manifest → flip True. / 存在 manifest → 翻轉 True。
    flipped = enforcer.mark_manifest_expired(cur, "manifest-001")
    assert flipped is True
    assert "manifest-001" in cur.flipped_manifest_ids

    # Re-flip same manifest → idempotent False.
    # 對同 manifest 再翻 → 冪等 False。
    flipped_again = enforcer.mark_manifest_expired(cur, "manifest-001")
    assert flipped_again is False

    # Non-existent manifest → False.
    # 不存在 manifest → False。
    flipped_missing = enforcer.mark_manifest_expired(cur, "manifest-999")
    assert flipped_missing is False

    # Schema absent → False (graceful no-op, no UPDATE issued).
    # Schema 缺 → False（graceful no-op，未發 UPDATE）。
    cur_absent = _FakeCursor(experiments_present=False)
    flipped_absent = enforcer.mark_manifest_expired(cur_absent, "manifest-002")
    assert flipped_absent is False
    # No UPDATE SQL executed because probe failed first.
    # 因 probe 先 fail，無 UPDATE SQL 執行。
    update_calls = [
        sql for sql, _ in cur_absent.executed
        if "update replay.experiments" in sql.lower()
    ]
    assert len(update_calls) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
