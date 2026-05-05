"""REF-20 Sprint A R2-T4 — POST /experiments/register hermetic tests.
REF-20 Sprint A R2-T4 — POST /experiments/register 封閉式測試。

MODULE_NOTE (EN):
    Hermetic 9-case suite covering R2-T1 register endpoint:

      Case 1: minimal payload creates row (V049 22-col INSERT happy path).
      Case 2: idempotency_key + same actor → cached row returned (no
              second INSERT).
      Case 3: missing strategy_config_sha256 → 422 (Pydantic validation).
      Case 4: invalid data_tier='S5' → 422 (V049 CHECK enum proxy).
      Case 5: oversized manifest_jsonb (>256 KB canonical) → 422.
      Case 6: client-supplied actor_id is ignored (server uses actor.actor_id).
      Case 7: signature_hex with invalid bytes → 400
              (replay_register_signature_mismatch).
      Case 8: canonical_bytes hash consistent (same payload twice → same
              manifest_hash).
      Case 9: data_window_end <= start → 422.

    All cases use ``monkeypatch`` to swap ``get_pg_conn`` and (where
    relevant) ``manifest_signer`` so tests run hermetically on Mac dev
    (no real PG, no real key archive).

MODULE_NOTE (中):
    封閉式 9-case 測試套件，覆蓋 R2-T1 register endpoint：

      Case 1：最小 payload 建 row（V049 22-col INSERT 正向路徑）。
      Case 2：idempotency_key + 同 actor → 回 cached row（無第二次 INSERT）。
      Case 3：缺 strategy_config_sha256 → 422（Pydantic 驗）。
      Case 4：data_tier='S5' → 422（V049 CHECK enum 代理）。
      Case 5：manifest_jsonb canonical >256 KB → 422。
      Case 6：client 提的 actor_id 被忽略（server 用 actor.actor_id）。
      Case 7：signature_hex 不對 → 400（replay_register_signature_mismatch）。
      Case 8：canonical_bytes hash consistent（兩次同 payload → 同 hash）。
      Case 9：data_window_end <= start → 422。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_routes import replay_router  # noqa: E402
from replay import experiment_registry as _er  # noqa: E402


# REF-20 Sprint A R2 round 2 fix M-3: every register test must set
# OPENCLAW_ENGINE_BINARY_SHA so the linux_trade_core fail-closed gate
# does not fire under hermetic test profile (real prod must export the
# real sha; here a dummy 64-hex stand-in keeps tests environment-clean).
# REF-20 Sprint A R2 round 2 fix M-3：每 register 測試必設
# OPENCLAW_ENGINE_BINARY_SHA 否則 linux_trade_core fail-closed 會觸發。
_DUMMY_ENGINE_SHA = "0" * 64


@pytest.fixture(autouse=True)
def _set_engine_sha_and_clear_cache(monkeypatch):
    """Auto-fixture: set engine sha env + clear in-memory idempotency cache.
    自動 fixture：設 engine sha env + 清 in-memory idempotency cache。

    Cache clear is critical because the singleton dict persists across
    tests in the same Python process, so a Case-2 cache entry would
    leak into Case-1 if not cleared.
    cache 清空很關鍵 — singleton dict 跨測試持久化，Case-2 cache entry
    若不清會洩漏到 Case-1。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)
    _er._cache_clear_for_test()
    yield
    _er._cache_clear_for_test()


# ─── Test actors / 測試 actor ──────────────────────────────────────────


def _operator_actor_alice() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _operator_actor_bob() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="bob",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _build_client(actor_factory) -> TestClient:
    app = FastAPI()
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


# ─── Helpers / 輔助 ────────────────────────────────────────────────────


def _minimal_register_body(**overrides) -> dict:
    """Build the minimum-valid register POST body.
    建最小可註冊 POST body。
    """
    base = {
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "timeframe": "1m",
        "data_tier": "S3",
        "data_window_start": "2026-04-01T00:00:00Z",
        "data_window_end": "2026-04-30T23:59:00Z",
        "strategy_config_sha256": "a" * 64,
        "risk_config_sha256": "b" * 64,
        "half_life_days": 7.0,
        "embargo_days": 1.0,
        "manifest_jsonb": {
            "name": "test-replay-001",
            "candidate_K": 1,
            "symbol": "BTCUSDT",
            "strategy": "grid_trading",
            "timeframe": "1m",
            "data_tier": "S3",
        },
    }
    base.update(overrides)
    return base


@contextmanager
def _stub_get_pg_conn_for_insert(insert_records: list, fetchone_returns: list):
    """Stub get_pg_conn yielding a cursor whose execute records SQL +
    fetchone returns are scripted.
    Stub get_pg_conn 給 cursor，記 SQL execute + 腳本化 fetchone 回值。
    """
    conn = MagicMock()
    cur = MagicMock()
    fetchone_iter = iter(fetchone_returns)

    def _execute(sql, params=()):
        # Skip SET LOCAL statement_timeout boilerplate.
        # 跳過 SET LOCAL 樣板。
        if "SET LOCAL" in str(sql):
            return None
        insert_records.append((str(sql), tuple(params) if not isinstance(params, tuple) else params))

    def _fetchone():
        try:
            return next(fetchone_iter)
        except StopIteration:
            return None

    cur.execute.side_effect = _execute
    cur.fetchone.side_effect = _fetchone
    conn.cursor.return_value = cur
    yield conn


# ─── Case 1: minimal payload creates row ───────────────────────────────


def test_register_minimal_payload_creates_row(monkeypatch):
    """Case 1: minimal payload → 200 + experiment_id + status='created'.
    Case 1：最小 payload → 200 + experiment_id + status='created'。
    """
    insert_records: list = []

    def _get_pg_conn_factory():
        # advisory lock True (no idempotency in body so not actually called),
        # then RETURNING (experiment_id_text, created_at).
        # 無 idempotency_key → 不取 advisory lock；RETURNING 回 (uuid, ts)。
        from datetime import datetime, timezone
        ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        fetchone_returns = [
            ("11111111-1111-1111-1111-111111111111", ts),
        ]
        return _stub_get_pg_conn_for_insert(insert_records, fetchone_returns)

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register",
                       json=_minimal_register_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["experiment_id"] == "11111111-1111-1111-1111-111111111111"
    assert data["status"] == "created"
    assert data["idempotency_hit"] is False
    # Assert an INSERT INTO replay.experiments was issued.
    insert_sqls = [s for s, _ in insert_records if "INSERT INTO replay.experiments" in s]
    assert len(insert_sqls) == 1, f"expected 1 INSERT, got: {len(insert_sqls)}"


# ─── Case 2: idempotency cache hit ────────────────────────────────────


def test_register_idempotency_key_returns_existing(monkeypatch):
    """Case 2: existing idempotency_key + same actor → cached row.
    Case 2：既有 idempotency_key + 同 actor → 回 cached row。

    R2 round 2 fix H-1: idempotency cache is now in-memory (module-level
    dict in ``replay.experiment_registry``), not DB-backed. We pre-populate
    the cache directly to simulate a prior register call, then verify the
    second call short-circuits without issuing INSERT.
    R2 round 2 fix H-1：idempotency cache 是 in-memory（experiment_registry
    module-level dict），非 DB 路徑。我們直接預填 cache 模擬先前 register，
    然後驗第二次呼叫短路，無 INSERT。
    """
    insert_records: list = []

    def _get_pg_conn_factory():
        # No DB roundtrip expected after cache hit — but provide an empty
        # stub so any unexpected execute fails loudly.
        # cache hit 後不應 round-trip DB；空 stub 讓非預期 execute 失敗醒目。
        return _stub_get_pg_conn_for_insert(insert_records, [])

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    # Pre-populate the cache to simulate a prior register call. The hash
    # MUST match the body's manifest_jsonb hash so H-2 (replay attack
    # detection) does not trip — we want a clean cache HIT.
    # 預填 cache 模擬先前 register；hash 必對齊本 body 的 manifest_jsonb
    # 否則 H-2（replay attack 偵測）會觸發。
    body_dict = _minimal_register_body(idempotency_key="alice-key-001")
    expected_hash = _er.compute_manifest_hash(body_dict["manifest_jsonb"])
    _er._cache_set_idempotency(
        "alice", "alice-key-001",
        {
            "experiment_id": "99999999-9999-9999-9999-999999999999",
            "manifest_hash": expected_hash,
            "status": "created",
            "created_at": "2026-05-04T12:00:00+00:00",
        },
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body_dict)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["experiment_id"] == "99999999-9999-9999-9999-999999999999"
    assert data["idempotency_hit"] is True
    # No INSERT should have been issued (cache hit short-circuits).
    # cache hit 短路 → 無 INSERT。
    insert_sqls = [s for s, _ in insert_records if "INSERT INTO replay.experiments" in s]
    assert len(insert_sqls) == 0, f"expected 0 INSERT for cache hit, got: {len(insert_sqls)}"


# ─── Case 3: missing strategy_config_sha256 ───────────────────────────


def test_register_missing_strategy_config_sha256_422():
    """Case 3: missing strategy_config_sha256 → 422 Pydantic.
    Case 3：缺 strategy_config_sha256 → 422 Pydantic。
    """
    body = _minimal_register_body()
    del body["strategy_config_sha256"]
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    assert resp.status_code == 422, resp.text


# ─── Case 4: invalid data_tier ────────────────────────────────────────


def test_register_invalid_data_tier_422():
    """Case 4: data_tier='S5' → 422 (V049 CHECK enum proxy).
    Case 4：data_tier='S5' → 422（V049 CHECK enum 代理）。
    """
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register",
                       json=_minimal_register_body(data_tier="S5"))
    assert resp.status_code == 422, resp.text


# ─── Case 5: oversized manifest_jsonb ─────────────────────────────────


def test_register_oversized_manifest_jsonb_422():
    """Case 5: manifest_jsonb canonical >256 KB → 422 size cap.
    Case 5：manifest_jsonb canonical >256 KB → 422 size cap。
    """
    huge = {"big_field": "x" * (300 * 1024)}  # canonical >256 KB
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register",
                       json=_minimal_register_body(manifest_jsonb=huge))
    assert resp.status_code == 422, resp.text


# ─── Case 6: actor_id server-side ─────────────────────────────────────


def test_register_actor_id_server_side(monkeypatch):
    """Case 6: client-supplied actor_id field is ignored — server uses actor.actor_id.
    Case 6：client 提 actor_id 被忽略；server 用 actor.actor_id。

    The Pydantic model has no actor_id field; any client-injected one is
    silently dropped by FastAPI (extra='ignore' default). This test
    verifies INSERT params[1] is the authenticated actor ('alice'), not
    any client-supplied poison.
    Pydantic model 無 actor_id 欄位；client 注的被 FastAPI extra='ignore'
    丟棄。本測試驗 INSERT params[1] 為認證 actor ('alice')。
    """
    insert_records: list = []

    def _get_pg_conn_factory():
        from datetime import datetime, timezone
        ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        fetchone_returns = [
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ts),
        ]
        return _stub_get_pg_conn_for_insert(insert_records, fetchone_returns)

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    body = _minimal_register_body()
    body["actor_id"] = "attacker-injected-id"  # type: ignore[assignment]
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    assert resp.status_code == 200, resp.text
    # INSERT params: 2nd positional is created_by=actor_id (alice).
    # INSERT 第 2 個 positional param = created_by=actor_id（'alice'）。
    insert_calls = [(s, p) for s, p in insert_records if "INSERT INTO replay.experiments" in s]
    assert len(insert_calls) == 1
    _sql, params = insert_calls[0]
    # params[0] = experiment_id (uuid str), params[1] = created_by (actor_id).
    # params[0] = experiment_id；params[1] = created_by=actor_id。
    assert params[1] == "alice", f"expected 'alice', got: {params[1]}"


# ─── Case 7: signature_hex invalid → 400 ──────────────────────────────


def test_register_signature_hex_invalid_400(monkeypatch):
    """Case 7: signature_hex provided but doesn't match → 400.
    Case 7：signature_hex 提供但不對 → 400。
    """
    monkeypatch.setenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "00" * 32)
    insert_records: list = []

    def _get_pg_conn_factory():
        # PG conn provided; register_experiment will compute manifest hash,
        # then run signature verify which fails before INSERT.
        # 提供 PG conn；register_experiment 算 hash 後 verify 失敗，
        # 走 conn.rollback() 不 INSERT。
        # No fetchone needed since INSERT is never reached.
        # INSERT 不會到，無 fetchone 需要。
        return _stub_get_pg_conn_for_insert(insert_records, [])

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    body = _minimal_register_body(
        signature_hex="ff" * 32,  # wrong sig
        signature_key_ref="test_key_ref",
    )
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    # Expected: 400 signature_mismatch.
    # 預期：400 signature_mismatch。
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", {})
    reasons = detail.get("reason_codes", [])
    assert any(r.startswith("replay_register_") for r in reasons), reasons
    # No INSERT INTO replay.experiments should have been issued.
    # 不應有 INSERT INTO replay.experiments。
    insert_sqls = [s for s, _ in insert_records if "INSERT INTO replay.experiments" in s]
    assert len(insert_sqls) == 0, f"signature verify failed but INSERT issued: {insert_sqls}"


# ─── Case 8: canonical_bytes hash consistent ──────────────────────────


def test_register_canonical_bytes_hash_consistent():
    """Case 8: same manifest_jsonb produces same manifest_hash twice.
    Case 8：同 manifest_jsonb 兩次得同 manifest_hash。

    Pure-helper test; no PG / route needed. Verifies the canonical-bytes
    contract (sort_keys=True, separators=(',', ':'), ensure_ascii=False).
    純 helper 測試；驗 canonical-bytes 契約。
    """
    payload = {"name": "abc", "tags": ["x", "y"], "k": 7}
    # Same payload, different key insertion order.
    # 同 payload 但 dict key 插入順序不同。
    payload2 = {"k": 7, "name": "abc", "tags": ["x", "y"]}
    h1 = _er.compute_manifest_hash(payload)
    h2 = _er.compute_manifest_hash(payload2)
    assert h1 == h2, f"hash drift on key order: {h1} != {h2}"
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


# ─── Case 9: data_window_end <= start ─────────────────────────────────


def test_register_window_end_before_start_422():
    """Case 9: data_window_end <= start → 422.
    Case 9：data_window_end <= start → 422。
    """
    body = _minimal_register_body(
        data_window_start="2026-04-30T00:00:00Z",
        data_window_end="2026-04-01T00:00:00Z",  # before start
    )
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    assert resp.status_code == 422, resp.text


# ═══════════════════════════════════════════════════════════════════════
# REF-20 Sprint A R2 round 2 cases (E2 review fix coverage).
# REF-20 Sprint A R2 round 2 案例（E2 review fix 覆蓋）。
# ═══════════════════════════════════════════════════════════════════════


# ─── R2 round 2 H-1: DB row self-consistent hash ─────────────────────


def test_register_db_row_self_consistent_hash(monkeypatch):
    """R2 round 2 H-1: persisted manifest_jsonb byte-equal to client input.
    R2 round 2 H-1：持久化 manifest_jsonb 與 client 輸入 byte-equal。

    Round 1 injected ``_idempotency_key`` into manifest_jsonb so the
    INSERT-d row was no longer self-consistent (sha256 of persisted
    JSONB != manifest_hash). This test captures the INSERT params and
    recomputes sha256 over the persisted JSONB bytes; it MUST match
    manifest_hash (returned to caller).

    Round 1 注入 ``_idempotency_key``，破壞 sha256(persisted_jsonb)==
    manifest_hash 不變式。本測試抓 INSERT 參數對 persisted JSONB 重算
    sha256，必對齊 manifest_hash。
    """
    insert_records: list = []

    def _get_pg_conn_factory():
        from datetime import datetime, timezone
        ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        # Sequence under cache miss + idempotency_key:
        # 1) advisory lock try → True
        # 2) INSERT RETURNING (uuid, ts)
        fetchone_returns = [
            (True,),
            ("abcdef00-0000-0000-0000-000000000001", ts),
        ]
        return _stub_get_pg_conn_for_insert(insert_records, fetchone_returns)

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    body_dict = _minimal_register_body(idempotency_key="alice-key-h1")
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body_dict)
    assert resp.status_code == 200, resp.text
    response_data = resp.json()["data"]
    response_hash = response_data["manifest_hash"]

    # Find the INSERT call and extract params[12] = manifest_jsonb json string.
    # Per the SQL VALUES order: experiment_id, actor_id, runtime, git_sha,
    # engine_sha, strat_sha, risk_sha, timeframe, data_tier, exec_conf,
    # win_start, win_end, manifest_jsonb_str, manifest_hash_bytes, ...
    # 找 INSERT call，取 params[12] = manifest_jsonb json 字串。
    insert_calls = [(s, p) for s, p in insert_records
                    if "INSERT INTO replay.experiments" in s]
    assert len(insert_calls) == 1
    _sql, params = insert_calls[0]
    persisted_jsonb_str = params[12]

    # H-1 invariant: persisted JSONB must NOT contain '_idempotency_key' key.
    # H-1 不變式：persisted JSONB 不可含 ``_idempotency_key`` key。
    import json as _json
    persisted_obj = _json.loads(persisted_jsonb_str)
    assert "_idempotency_key" not in persisted_obj, (
        f"persisted manifest_jsonb leaked '_idempotency_key': "
        f"{list(persisted_obj.keys())}"
    )

    # Recompute sha256 over the SAME canonical bytes the server used; MUST
    # equal manifest_hash returned to the caller.
    # 對 server 用的同一 canonical bytes 重算 sha256；必等於 caller 收到的
    # manifest_hash。
    recomputed_hash = _er.compute_manifest_hash(persisted_obj)
    assert recomputed_hash == response_hash, (
        f"DB row self-consistency broken: persisted hash {recomputed_hash} "
        f"!= response hash {response_hash}"
    )


# ─── R2 round 2 H-2: idempotency replay attack → 409 ─────────────────


def test_register_idempotency_replay_attack_409(monkeypatch):
    """R2 round 2 H-2: same idempotency_key + DIFFERENT manifest → 409.
    R2 round 2 H-2：同 idempotency_key + 不同 manifest → 409。

    Pre-populates cache with a hash for a known body; second register
    sends a DIFFERENT manifest_jsonb under the same key+actor → server
    detects mismatch and returns 409 ``replay_register_idempotency_replay_attack``.
    預填 cache hash；第二次送不同 manifest_jsonb → server 偵測不符回 409。
    """
    insert_records: list = []

    def _get_pg_conn_factory():
        # Should NEVER reach DB on hash mismatch (early 409 return).
        # hash 不符時不應到 DB（早 409 return）。
        return _stub_get_pg_conn_for_insert(insert_records, [])

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    # Pre-populate cache with the hash of a DIFFERENT manifest (the
    # "original" register that allegedly came first).
    # 先預填 cache 一個不同 manifest 的 hash（"原本"先到的 register）。
    original_manifest = {"name": "original-001", "candidate_K": 1}
    original_hash = _er.compute_manifest_hash(original_manifest)
    _er._cache_set_idempotency(
        "alice", "alice-key-attack",
        {
            "experiment_id": "11111111-1111-1111-1111-aaaaaaaaaaaa",
            "manifest_hash": original_hash,
            "status": "created",
            "created_at": "2026-05-04T11:00:00+00:00",
        },
    )

    # Now send a DIFFERENT manifest with the same idempotency_key.
    # 送不同 manifest 但同 idempotency_key。
    body = _minimal_register_body(
        idempotency_key="alice-key-attack",
        manifest_jsonb={"name": "attacker-injected", "candidate_K": 999},
    )
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    assert resp.status_code == 409, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_register_idempotency_replay_attack" in (
        detail.get("reason_codes", [])
    ), detail
    # No INSERT issued.
    insert_sqls = [s for s, _ in insert_records
                   if "INSERT INTO replay.experiments" in s]
    assert len(insert_sqls) == 0


# ─── R2 round 2 M-3: linux_trade_core missing engine sha → 503 ────────


def test_register_linux_trade_core_missing_engine_sha_503(monkeypatch):
    """R2 round 2 M-3: linux_trade_core + no OPENCLAW_ENGINE_BINARY_SHA → 503.
    R2 round 2 M-3：linux_trade_core + 無 OPENCLAW_ENGINE_BINARY_SHA → 503。

    Round 1 silently fell back to a sentinel string ``register_pending_engine_sha``
    which polluted DB rows for supply-chain audit. Round 2 fails closed
    with 503 + ``replay_engine_binary_sha_not_provisioned``.
    Round 1 用 sentinel 過 CHECK 但污染 supply-chain audit；Round 2 503 fail-closed。
    """
    # Override the autouse fixture's setenv: explicitly delete this env.
    # 蓋過 autouse fixture 的 setenv：明確 delete 該 env。
    monkeypatch.delenv("OPENCLAW_ENGINE_BINARY_SHA", raising=False)
    # Force linux_trade_core runtime (default; explicit for clarity).
    # 強制 linux_trade_core runtime（默認；顯式）。
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNTIME_ENV", "linux_trade_core")

    insert_records: list = []

    def _get_pg_conn_factory():
        # Should never reach INSERT (M-3 short-circuits before SQL).
        # 不應到 INSERT（M-3 在 SQL 前短路）。
        return _stub_get_pg_conn_for_insert(insert_records, [])

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _get_pg_conn_factory)

    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register",
                       json=_minimal_register_body())
    assert resp.status_code == 503, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_engine_binary_sha_not_provisioned" in (
        detail.get("reason_codes", [])
    ), detail
    insert_sqls = [s for s, _ in insert_records
                   if "INSERT INTO replay.experiments" in s]
    assert len(insert_sqls) == 0


# ─── R2 round 2 M-4: reserved prefix key → 422 ───────────────────────


def test_register_reserved_prefix_key_422():
    """R2 round 2 M-4: manifest_jsonb keys with '_' prefix → 422.
    R2 round 2 M-4：manifest_jsonb 含 '_' 前綴 key → 422。

    Reserved for server-controlled metadata. Pydantic validator rejects
    before INSERT.
    保留給 server metadata；Pydantic validator 在 INSERT 前 reject。
    """
    body = _minimal_register_body(
        manifest_jsonb={"_my_key": "x", "name": "test"},
    )
    client = _build_client(_operator_actor_alice)
    resp = client.post("/api/v1/replay/experiments/register", json=body)
    assert resp.status_code == 422, resp.text
    # Pydantic 422 envelope wraps the validator message.
    # Pydantic 422 信封包 validator 訊息。
    raw = resp.json()
    msg = str(raw)
    assert "_my_key" in msg or "_'" in msg or "reserved" in msg.lower(), (
        f"422 detail did not surface the reserved-prefix reason: {raw}"
    )


# ─── REF-20 Sprint B2 R5-T6 — config sha lookup helper ────────────────


def test_lookup_replay_config_sha256_returns_pair_when_row_exists():
    """R5-T6 Case A: row exists → returns (strategy_sha, risk_sha) tuple.

    Mock cursor simulates V049 SELECT returning the canonical 64-hex shas
    that R2 register handler INSERTed. Helper must return them as plain
    strings (not bytes / not memoryview).

    R5-T6 Case A：row 存在 → 回 (strategy_sha, risk_sha) tuple。
    Mock cursor 模擬 V049 SELECT 回 R2 register handler 寫入的 64-hex sha。
    Helper 必回純字串（非 bytes / memoryview）。
    """
    cur = MagicMock()
    cur.fetchone.return_value = ("a" * 64, "b" * 64)
    strategy_sha, risk_sha = _er.lookup_replay_config_sha256(
        cur, "11111111-1111-1111-1111-111111111111"
    )
    assert strategy_sha == "a" * 64
    assert risk_sha == "b" * 64
    # Confirm SELECT used parameterised SQL and uuid cast.
    # 確認 SELECT 用參數化 SQL + uuid 轉型。
    sql_arg = cur.execute.call_args.args[0]
    assert "SELECT strategy_config_sha256, risk_config_sha256" in sql_arg
    assert "%s::uuid" in sql_arg
    params_arg = cur.execute.call_args.args[1]
    assert params_arg == ("11111111-1111-1111-1111-111111111111",)


def test_lookup_replay_config_sha256_returns_none_when_row_missing():
    """R5-T6 Case B: experiment not found → (None, None) tuple."""
    cur = MagicMock()
    cur.fetchone.return_value = None
    strategy_sha, risk_sha = _er.lookup_replay_config_sha256(
        cur, "22222222-2222-2222-2222-222222222222"
    )
    assert strategy_sha is None
    assert risk_sha is None


def test_lookup_replay_config_sha256_handles_partial_null_defensively():
    """R5-T6 Case C: V049 NOT NULL violated (defensive) → log warning + return.

    V049 currently NOT NULL on both columns; this test exercises the
    defense-in-depth branch in case a future migration relaxes the
    constraint. Helper must return whichever side is non-empty so callers
    can fail-loud on partial state without exception.

    R5-T6 Case C：V049 NOT NULL 違反（縱深防禦）→ 印 warning + 回。
    當前 V049 兩 column NOT NULL；本 test 測未來 migration 放寬時的縱深
    分支。Helper 必回非空那側使 caller 可 fail-loud 而不 raise。
    """
    cur = MagicMock()
    cur.fetchone.return_value = ("a" * 64, "")  # risk_sha empty
    strategy_sha, risk_sha = _er.lookup_replay_config_sha256(
        cur, "33333333-3333-3333-3333-333333333333"
    )
    assert strategy_sha == "a" * 64
    assert risk_sha is None


def test_register_then_lookup_round_trip(monkeypatch):
    """R5-T6 Case D: round-trip — register → SELECT shas back.

    Verifies the V049 INSERT path written by R2 round 2 stores both
    strategy_config_sha256 and risk_config_sha256 as canonical 64-hex
    columns that R5-T6 helper can read back. Uses real register code +
    mocked PG connection so we exercise the SELECT shape end-to-end.

    R5-T6 Case D：round-trip — register → SELECT 取回 sha。
    驗 R2 round 2 寫入路徑將兩 sha 存為 canonical 64-hex column，R5-T6
    helper 可讀回。用真實 register 代碼 + mock PG 連線端對端驗 SELECT shape。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)

    # Stub PG connection with cursor that records INSERT params + replays
    # them on subsequent SELECT.
    # Stub PG 連線；cursor 記下 INSERT params 並在後續 SELECT 重播。
    captured_insert_params: list = []
    captured_select_results: list = []

    class StubCursor:
        def __init__(self):
            self.rowcount = 0
            self._next_result = None
            self.last_sql = ""
            self.last_params = None

        def execute(self, sql, params=None):
            self.last_sql = sql
            self.last_params = params
            if "INSERT INTO replay.experiments" in sql:
                captured_insert_params.append(params)
                # Simulate RETURNING experiment_id::text, created_at.
                from datetime import datetime, timezone
                self._next_result = (
                    "44444444-4444-4444-4444-444444444444",
                    datetime.now(timezone.utc),
                )
            elif "SELECT strategy_config_sha256" in sql:
                captured_select_results.append(params)
                # Replay the strategy_config_sha256 + risk_config_sha256 from
                # the INSERT params tuple. Positional layout in
                # ``register_experiment``'s cur.execute call:
                #   [0] str(experiment_id)
                #   [1] actor_id
                #   [2] runtime_environment
                #   [3] git_sha
                #   [4] engine_binary_sha
                #   [5] body.strategy_config_sha256   ← R5-T6 read target
                #   [6] body.risk_config_sha256       ← R5-T6 read target
                # （R5-T6：對齊 register_experiment 內 INSERT 參數順序）
                if captured_insert_params:
                    insert_args = captured_insert_params[-1]
                    self._next_result = (
                        insert_args[5],  # strategy_config_sha256
                        insert_args[6],  # risk_config_sha256
                    )
                else:
                    self._next_result = None
            else:
                self._next_result = None

        def fetchone(self):
            return self._next_result

    cur = StubCursor()

    body = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        strategy_config_sha256="a" * 64,
        risk_config_sha256="b" * 64,
        half_life_days=1.0,
        manifest_jsonb={"strategy": "grid_trading", "version": 1},
    )
    actor = _operator_actor_alice()
    result, err = _er.register_experiment(cur, actor, body)
    assert err is None
    assert result is not None
    experiment_id = result["experiment_id"]

    # R5-T6 SELECT: read back the shas via helper.
    # R5-T6 SELECT：透過 helper 讀回 sha。
    strategy_sha, risk_sha = _er.lookup_replay_config_sha256(cur, experiment_id)
    assert strategy_sha == "a" * 64
    assert risk_sha == "b" * 64


# ─── REF-20 Sprint B2 R5-T6 round 2 — config blob server-side wiring ──


def _capturing_cursor():
    """Build a cursor that records all INSERT params for inspection.
    建一個記下所有 INSERT params 的 cursor 供斷言檢查。
    """
    captured: list = []

    class _Cur:
        def __init__(self):
            self.rowcount = 0
            self._next = None
            self.last_sql = ""

        def execute(self, sql, params=None):
            self.last_sql = sql
            if "INSERT INTO replay.experiments" in sql:
                captured.append(params)
                from datetime import datetime, timezone
                self._next = (
                    "55555555-5555-5555-5555-555555555555",
                    datetime.now(timezone.utc),
                )
            else:
                self._next = None

        def fetchone(self):
            return self._next

    return _Cur(), captured


def test_register_with_strategy_params_computes_distinct_sha(monkeypatch):
    """R5-T6 round 2 Case A: same strategy name + DIFFERENT strategy_params
    → server-computed strategy_config_sha256 distinct (A4 acceptance proof).

    R5-T6 round 2 Case A：同 strategy name + 不同 strategy_params → server
    計出的 strategy_config_sha256 不同（A4 acceptance proof）。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)

    # Baseline: grid_levels=10
    cur_a, captured_a = _capturing_cursor()
    body_a = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        # Client-supplied placeholder; server will OVERRIDE this when
        # strategy_params is provided.
        # Client 提的 placeholder；server 會用 strategy_params 算出的真值覆寫。
        strategy_config_sha256="0" * 64,
        risk_config_sha256="b" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": "test-A4-baseline"},
        strategy_params={"grid_trading": {"grid_levels": 10}},
    )
    res_a, err_a = _er.register_experiment(cur_a, _operator_actor_alice(), body_a)
    assert err_a is None and res_a is not None

    # Candidate: grid_levels=20
    cur_b, captured_b = _capturing_cursor()
    body_b = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        strategy_config_sha256="0" * 64,
        risk_config_sha256="b" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": "test-A4-candidate"},
        strategy_params={"grid_trading": {"grid_levels": 20}},
    )
    res_b, err_b = _er.register_experiment(cur_b, _operator_actor_alice(), body_b)
    assert err_b is None and res_b is not None

    # INSERT param positional layout (see register_experiment cur.execute):
    #   [5] strategy_config_sha256
    #   [6] risk_config_sha256
    # INSERT 參數位置（見 register_experiment cur.execute）。
    sha_a = captured_a[0][5]
    sha_b = captured_b[0][5]
    # Server must override the "0"*64 placeholder with computed sha.
    # Server 必用算出的 sha 覆寫 client placeholder。
    assert sha_a != "0" * 64, (
        f"server did NOT override placeholder strategy sha: {sha_a}"
    )
    assert sha_b != "0" * 64
    # Distinct params → distinct sha (A4 acceptance core invariant).
    # 不同 params → 不同 sha（A4 核心不變式）。
    assert sha_a != sha_b, (
        "same strategy name + different strategy_params produced IDENTICAL "
        f"strategy_config_sha256: {sha_a} (A4 acceptance fail; "
        "compute_manifest_canonical_bytes contract drift?)"
    )
    # Risk sha untouched (no risk_overrides supplied).
    # 未提供 risk_overrides → risk sha 不變。
    assert captured_a[0][6] == "b" * 64
    assert captured_b[0][6] == "b" * 64


def test_register_with_risk_overrides_computes_distinct_sha(monkeypatch):
    """R5-T6 round 2 Case B: same strategy + DIFFERENT risk_overrides →
    server-computed risk_config_sha256 distinct (A5 acceptance proof).

    R5-T6 round 2 Case B：同 strategy + 不同 risk_overrides → server 計
    risk_config_sha256 不同（A5 acceptance proof）。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)

    # Tight: position_size_max_pct = 2.0
    cur_a, captured_a = _capturing_cursor()
    body_a = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        strategy_config_sha256="a" * 64,
        risk_config_sha256="0" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": "test-A5-tight"},
        risk_overrides={"limits": {"position_size_max_pct": 2.0}},
    )
    res_a, err_a = _er.register_experiment(cur_a, _operator_actor_alice(), body_a)
    assert err_a is None and res_a is not None

    # Loose: position_size_max_pct = 10.0
    cur_b, captured_b = _capturing_cursor()
    body_b = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        strategy_config_sha256="a" * 64,
        risk_config_sha256="0" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": "test-A5-loose"},
        risk_overrides={"limits": {"position_size_max_pct": 10.0}},
    )
    res_b, err_b = _er.register_experiment(cur_b, _operator_actor_alice(), body_b)
    assert err_b is None and res_b is not None

    risk_sha_a = captured_a[0][6]
    risk_sha_b = captured_b[0][6]
    assert risk_sha_a != "0" * 64
    assert risk_sha_b != "0" * 64
    assert risk_sha_a != risk_sha_b, (
        "same strategy + different risk_overrides produced IDENTICAL "
        f"risk_config_sha256: {risk_sha_a} (A5 acceptance fail)"
    )
    # Strategy sha untouched (no strategy_params supplied).
    assert captured_a[0][5] == "a" * 64
    assert captured_b[0][5] == "a" * 64


def test_lookup_replay_config_blob_returns_params_and_overrides():
    """R5-T6 round 2 Case C: lookup_replay_config_blob round-trips both
    blobs from manifest_jsonb's reserved keys.

    R5-T6 round 2 Case C：lookup_replay_config_blob 從 manifest_jsonb 保留 key
    讀回兩 blob。
    """
    cur = MagicMock()
    # Simulate persisted manifest_jsonb with both reserved keys.
    # 模擬 manifest_jsonb 兩保留 key 已注入。
    cur.fetchone.return_value = (
        {
            "name": "test",
            "_replay_strategy_params": {"grid_trading": {"grid_levels": 7}},
            "_replay_risk_overrides": {
                "limits": {"position_size_max_pct": 3.5}
            },
        },
    )
    blob = _er.lookup_replay_config_blob(
        cur, "11111111-1111-1111-1111-111111111111"
    )
    assert blob["strategy_params"] == {
        "grid_trading": {"grid_levels": 7}
    }
    assert blob["risk_overrides"] == {
        "limits": {"position_size_max_pct": 3.5}
    }
    # SELECT shape contract.
    sql_arg = cur.execute.call_args.args[0]
    assert "SELECT manifest_jsonb" in sql_arg
    assert "%s::uuid" in sql_arg


def test_lookup_replay_config_blob_returns_none_when_absent():
    """R5-T6 round 2 Case D: experiment row exists but manifest_jsonb has
    no reserved keys → both fields None.

    R5-T6 round 2 Case D：experiment 存在但 manifest_jsonb 無保留 key
    → 兩 field 皆 None。
    """
    cur = MagicMock()
    cur.fetchone.return_value = (
        {"name": "legacy-without-blob"},  # no _replay_* keys
    )
    blob = _er.lookup_replay_config_blob(
        cur, "22222222-2222-2222-2222-222222222222"
    )
    assert blob == {"strategy_params": None, "risk_overrides": None}

    # Row missing entirely.
    cur2 = MagicMock()
    cur2.fetchone.return_value = None
    blob2 = _er.lookup_replay_config_blob(
        cur2, "33333333-3333-3333-3333-333333333333"
    )
    assert blob2 == {"strategy_params": None, "risk_overrides": None}


def test_register_blob_path_preserves_jsonb_hash_invariant(monkeypatch):
    """R5-T6 round 2 Case E: when blobs are injected, recomputed
    manifest_hash matches sha256(canonical_bytes(persisted_jsonb)) so the
    DB self-consistency invariant holds (E2 review H-1 guarantee).

    R5-T6 round 2 Case E：注入 blob 後重算 manifest_hash 必等於
    sha256(canonical_bytes(persisted_jsonb))，DB 自洽不變式維持。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)

    cur, captured = _capturing_cursor()
    body = _er.ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="1m",
        data_tier="S2",
        data_window_start="2026-01-01T00:00:00Z",
        data_window_end="2026-01-02T00:00:00Z",
        strategy_config_sha256="0" * 64,
        risk_config_sha256="0" * 64,
        half_life_days=1.0,
        manifest_jsonb={"name": "invariant-check"},
        strategy_params={"grid_trading": {"grid_levels": 13}},
        risk_overrides={"limits": {"position_size_max_pct": 4.2}},
    )
    res, err = _er.register_experiment(cur, _operator_actor_alice(), body)
    assert err is None and res is not None

    # INSERT param positional layout (matches register_experiment
    # cur.execute call):
    #   [12] manifest_jsonb (json.dumps str)
    #   [13] manifest_hash (bytes)
    # INSERT 參數位置。
    persisted_jsonb_str = captured[0][12]
    persisted_hash_bytes = captured[0][13]
    persisted_jsonb_dict = json.loads(persisted_jsonb_str)
    # Augmented body must contain reserved keys.
    # 注入後 body 必含保留 key。
    assert "_replay_strategy_params" in persisted_jsonb_dict
    assert "_replay_risk_overrides" in persisted_jsonb_dict
    # Recompute hash from persisted body bytes — must match INSERTed hash.
    # 重算 hash 必等於 INSERTed hash。
    import hashlib as _hl
    expected = _hl.sha256(
        _er.compute_manifest_canonical_bytes(persisted_jsonb_dict)
    ).digest()
    assert persisted_hash_bytes == expected, (
        "DB self-consistency invariant BROKEN: "
        f"sha256(persisted_jsonb) != manifest_hash "
        f"(persisted_hash={persisted_hash_bytes.hex()} "
        f"recomputed={expected.hex()})"
    )
