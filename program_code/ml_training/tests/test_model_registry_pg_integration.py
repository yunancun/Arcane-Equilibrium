"""INFRA-PREBUILD-1 Part B — model_registry.py PG integration tests (L1-5).
INFRA-PREBUILD-1 B 部 model_registry.py PG 整合測試（L1-5）。

MODULE_NOTE (EN): Integration coverage for behaviour that the mock-based
  `test_model_registry.py` cannot validate — ON CONFLICT WHERE filter
  semantics, V023 CHECK constraints, transition state-machine UPDATE
  visibility, JSONB round-trip, and partial-index existence. Gated by
  `OPENCLAW_DATABASE_URL`: if unset (Mac dev-only / CI without PG) the
  whole module is skipped; on Linux trade-core with PG reachable the
  suite runs end-to-end against the real DB.

  Fresh schema per module: the fixture applies V023 migration against
  a clean `learning.model_registry` (dropped during teardown), so tests
  start with an empty table. `_truncate_between` keeps state isolation
  between test functions. No Docker / custom test DB required — uses
  the DSN already exported by the engine runtime.

MODULE_NOTE (中): 補 mock 測試（`test_model_registry.py`）驗不到的真 PG
  行為 — ON CONFLICT WHERE 過濾、V023 CHECK 約束、狀態機 UPDATE 可見性、
  JSONB 圓周轉、partial index 存在性。`OPENCLAW_DATABASE_URL` 環境變數
  gated：未設（Mac dev 或 CI 無 PG）整個 module skip；Linux trade-core
  有 PG 時端到端跑真 DB。模組級 fixture 建乾淨 schema + apply V023；
  teardown DROP；每個 test 前 TRUNCATE 保隔離。不需 Docker / 測試 DB。

Spec: sql/migrations/V023__model_registry.sql · INFRA-PREBUILD-1 audit L1-5.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from program_code.ml_training.model_registry import (
    CANARY_PRODUCTION,
    CANARY_PROMOTING,
    CANARY_REJECTED,
    CANARY_SHADOW,
    VERDICT_SHADOW_ONLY,
    VERDICT_SHOULD_SHIP,
    register_model,
    transition_canary_status,
)


# ───── Module-level gating: skip entire file when PG not available ────
# 模組級 gating：無 PG 時整 module skip（Mac dev / CI 無 PG 皆跳過）。


def _require_dsn() -> str:
    """Return OPENCLAW_DATABASE_URL or skip the whole test.
    回 OPENCLAW_DATABASE_URL 或整個測試 skip。"""
    dsn = os.environ.get("OPENCLAW_DATABASE_URL")
    if not dsn:
        pytest.skip("PG integration tests require OPENCLAW_DATABASE_URL")
    return dsn


@pytest.fixture(scope="module")
def pg_conn():
    """Module-scoped fixture: open psycopg connection + apply V023 migration.
    Teardown drops the table + trigger function to leave the schema clean.

    模組級 fixture：開 psycopg 連線 + apply V023 migration；teardown
    DROP TABLE + DROP FUNCTION 保持 schema 乾淨。
    """
    try:
        import psycopg  # noqa: F401 — import test
    except ImportError:
        pytest.skip("psycopg not installed")

    dsn = _require_dsn()
    import psycopg

    conn = psycopg.connect(dsn)
    # Apply V023 migration on a fresh schema. CREATE SCHEMA is idempotent;
    # V023 is IF NOT EXISTS throughout so re-running is safe.
    # Apply V023；CREATE SCHEMA 冪等，V023 全 IF NOT EXISTS 可重跑。
    v023_path = (
        Path(__file__).parent.parent.parent.parent
        / "sql"
        / "migrations"
        / "V023__model_registry.sql"
    )
    assert v023_path.exists(), f"V023 migration not found at {v023_path}"
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS learning")
        cur.execute(v023_path.read_text())
    conn.commit()

    yield conn

    # Teardown — drop table (cascades trigger) + trigger function.
    # Leaving schema `learning` intact because other V-migrations share it.
    # Teardown — DROP TABLE（自動連帶 trigger）+ DROP FUNCTION。
    # 不 drop schema `learning`，其他 V-migration 共用。
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS learning.model_registry CASCADE")
        cur.execute(
            "DROP FUNCTION IF EXISTS learning.model_registry_touch_updated_at()"
        )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def _truncate_between(pg_conn):
    """Reset table state before each test so tests start empty + isolated.
    每個 test 前 TRUNCATE 重置，保證各 test 獨立起手空桌。"""
    with pg_conn.cursor() as cur:
        cur.execute("TRUNCATE learning.model_registry RESTART IDENTITY")
    pg_conn.commit()
    yield


# ───── ON CONFLICT / register_model basic flow ──────────────────────


def test_register_model_shadow_initial_state(pg_conn):
    """Happy path: register → row exists with canary_status='shadow' default.
    快樂路徑：register 後 canary_status 預設為 'shadow'。"""
    dsn = _require_dsn()
    row_id = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/fake.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        training_sample_size=500,
        dsn=dsn,
    )
    assert row_id is not None
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT canary_status, verdict, training_sample_size "
            "FROM learning.model_registry WHERE id = %s",
            (row_id,),
        )
        row = cur.fetchone()
        assert row[0] == CANARY_SHADOW
        assert row[1] == VERDICT_SHOULD_SHIP
        assert row[2] == 500


def test_register_model_on_conflict_refreshes_shadow_row(pg_conn):
    """Re-training same slot with canary_status='shadow': DO UPDATE runs,
    artifact_path + verdict + training_sample_size get refreshed.
    同 slot 重訓在 shadow 狀態下 DO UPDATE 生效，artifact/verdict/sample 都刷新。"""
    dsn = _require_dsn()
    rid_1 = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v1.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        training_sample_size=300,
        dsn=dsn,
    )
    rid_2 = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v2.onnx",
        verdict=VERDICT_SHADOW_ONLY,
        training_sample_size=350,
        dsn=dsn,
    )
    # Same slot → same row id (ON CONFLICT DO UPDATE returned).
    # 同 slot → 同 row id（ON CONFLICT DO UPDATE 回傳）。
    assert rid_1 == rid_2
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_path, verdict, training_sample_size "
            "FROM learning.model_registry WHERE id = %s",
            (rid_1,),
        )
        row = cur.fetchone()
        assert row[0] == "/tmp/v2.onnx"
        assert row[1] == VERDICT_SHADOW_ONLY
        assert row[2] == 350


def test_register_model_on_conflict_preserves_promoting_canary(pg_conn):
    """INFRA-PREBUILD-1 L2-3 regression: retrain MUST NOT overwrite a
    promoting row's artifact/verdict metadata. WHERE filter on ON CONFLICT
    makes the UPDATE no-op; RETURNING yields no row → register_model
    returns None. The promoted slot stays intact.

    L2-3 回歸：retrain 不可覆寫 promoting row 的 artifact/verdict；
    WHERE filter 讓 DO UPDATE no-op，RETURNING 空 → 回 None；已晉升 slot 保留。"""
    dsn = _require_dsn()
    # Initial register (shadow).
    # 先註冊（shadow 狀態）。
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v1.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=dsn,
    )
    assert rid is not None
    # Manually promote to 'promoting' (bypassing state machine — simulating
    # Operator flip via /model_promote).
    # 手動升 promoting（模擬 operator 透過 /model_promote 轉移）。
    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE learning.model_registry SET canary_status = %s WHERE id = %s",
            (CANARY_PROMOTING, rid),
        )
    pg_conn.commit()

    # Retrain same slot — WHERE filter blocks UPDATE, register_model returns None.
    # 重訓同 slot — WHERE filter 擋 UPDATE，register_model 回 None。
    rid_2 = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v2.onnx",
        verdict=VERDICT_SHADOW_ONLY,
        dsn=dsn,
    )
    assert rid_2 is None

    # Verify nothing changed on the promoted row.
    # 驗已晉升 row 沒被動。
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_path, verdict, canary_status "
            "FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        row = cur.fetchone()
        assert row[0] == "/tmp/v1.onnx"
        assert row[1] == VERDICT_SHOULD_SHIP
        assert row[2] == CANARY_PROMOTING


def test_register_model_on_conflict_preserves_production_canary(pg_conn):
    """Same as promoting preservation but for canary_status='production'.
    Production is the deadliest case — swapping the live ONNX behind
    Operator's back would cause silent model drift in tick pipeline.

    與 promoting 保留相同，但對 production — production 是最危險的情境，
    偷換 live ONNX 會在 tick pipeline 造成靜默 model drift。"""
    dsn = _require_dsn()
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v1.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=dsn,
    )
    assert rid is not None
    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE learning.model_registry "
            "SET canary_status = %s, promoted_at = NOW() WHERE id = %s",
            (CANARY_PRODUCTION, rid),
        )
    pg_conn.commit()

    rid_2 = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/v2.onnx",
        verdict=VERDICT_SHADOW_ONLY,
        dsn=dsn,
    )
    assert rid_2 is None
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_path, verdict, canary_status "
            "FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        row = cur.fetchone()
        assert row[0] == "/tmp/v1.onnx"
        assert row[1] == VERDICT_SHOULD_SHIP
        assert row[2] == CANARY_PRODUCTION


# ───── V023 CHECK constraint enforcement ─────────────────────────────


def test_canary_status_check_constraint_rejects_invalid(pg_conn):
    """V023 CHECK rejects canary_status NOT IN the allowed enum. Guards against
    silent typos in application code writing unrecognised statuses.
    V023 CHECK 拒絕不在 enum 裡的 canary_status；守應用端 typo。"""
    import psycopg

    with pg_conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO learning.model_registry "
                "(strategy, engine_mode, quantile, schema_version, train_date, "
                " artifact_path, verdict, canary_status) "
                "VALUES (%s, %s, %s, %s, %s::date, %s, %s, %s)",
                (
                    "ma_crossover",
                    "demo",
                    "q50",
                    "v1",
                    "2026-04-23",
                    "/tmp/x.onnx",
                    VERDICT_SHOULD_SHIP,
                    "bogus_status",
                ),
            )
    # Rollback so the aborted transaction doesn't poison subsequent tests.
    # Rollback 以免污染後續測試。
    pg_conn.rollback()


def test_verdict_check_constraint_rejects_invalid(pg_conn):
    """V023 CHECK rejects verdict NOT IN ('should_ship','shadow_only','no_ship').
    V023 CHECK 拒絕不在 3-value enum 的 verdict。"""
    import psycopg

    with pg_conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO learning.model_registry "
                "(strategy, engine_mode, quantile, schema_version, train_date, "
                " artifact_path, verdict) "
                "VALUES (%s, %s, %s, %s, %s::date, %s, %s)",
                (
                    "ma_crossover",
                    "demo",
                    "q50",
                    "v1",
                    "2026-04-23",
                    "/tmp/x.onnx",
                    "bogus_verdict",
                ),
            )
    pg_conn.rollback()


def test_engine_mode_check_constraint_rejects_invalid(pg_conn):
    """V023 CHECK also restricts engine_mode to the 4-value enum.
    V023 CHECK 亦限 engine_mode 為 4-value enum。"""
    import psycopg

    with pg_conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO learning.model_registry "
                "(strategy, engine_mode, quantile, schema_version, train_date, "
                " artifact_path, verdict) "
                "VALUES (%s, %s, %s, %s, %s::date, %s, %s)",
                (
                    "ma_crossover",
                    "mainnet",  # not in (paper, demo, live, live_demo)
                    "q50",
                    "v1",
                    "2026-04-23",
                    "/tmp/x.onnx",
                    VERDICT_SHOULD_SHIP,
                ),
            )
    pg_conn.rollback()


# ───── transition_canary_status: real DB UPDATE visibility ──────────


def test_transition_shadow_to_promoting_updates_db(pg_conn):
    """transition_canary_status(shadow → promoting) commits and UPDATE is
    visible in subsequent SELECT. Mock tests can't prove the UPDATE actually
    landed on disk.

    transition 真能讓 UPDATE 落地 — mock 測不到這一點。"""
    dsn = _require_dsn()
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/fake.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=dsn,
    )
    assert rid is not None
    ok = transition_canary_status(row_id=rid, to_status=CANARY_PROMOTING, dsn=dsn)
    assert ok is True
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT canary_status, promoted_at FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        row = cur.fetchone()
        assert row[0] == CANARY_PROMOTING
        # shadow→promoting does NOT set promoted_at (that's for → production).
        # shadow→promoting 不設 promoted_at（只有 → production 才設）。
        assert row[1] is None


def test_transition_promoting_to_production_sets_promoted_at(pg_conn):
    """promoting → production UPDATE sets promoted_at to non-NULL (NOW()).
    promoting → production 的 UPDATE 設 promoted_at 為非 NULL（NOW()）。"""
    dsn = _require_dsn()
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/fake.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=dsn,
    )
    assert rid is not None
    # shadow → promoting first
    assert transition_canary_status(row_id=rid, to_status=CANARY_PROMOTING, dsn=dsn)
    # promoting → production
    assert transition_canary_status(row_id=rid, to_status=CANARY_PRODUCTION, dsn=dsn)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT canary_status, promoted_at FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        row = cur.fetchone()
        assert row[0] == CANARY_PRODUCTION
        assert row[1] is not None  # promoted_at = NOW()


def test_transition_shadow_to_rejected_sets_retired_at_and_reason(pg_conn):
    """shadow → rejected sets retired_at + retirement_reason (terminal path).
    shadow → rejected 設 retired_at + retirement_reason（終態路徑）。"""
    dsn = _require_dsn()
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/fake.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=dsn,
    )
    assert rid is not None
    reason = "low pinball skill on shadow window"
    ok = transition_canary_status(
        row_id=rid,
        to_status=CANARY_REJECTED,
        retirement_reason=reason,
        dsn=dsn,
    )
    assert ok is True
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT canary_status, retired_at, retirement_reason "
            "FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        row = cur.fetchone()
        assert row[0] == CANARY_REJECTED
        assert row[1] is not None
        assert row[2] == reason


# ───── JSONB round-trip for acceptance_report ──────────────────────


def test_acceptance_report_jsonb_roundtrip(pg_conn):
    """JSONB round-trip: dict → JSONB INSERT → SELECT → dict preserves nested
    structure + numeric types. Validates psycopg's jsonb adapter behaviour.

    JSONB 圓周轉：dict→JSONB→dict 保真（含巢狀結構+數值型態）；驗 psycopg jsonb adapter。"""
    dsn = _require_dsn()
    report = {
        "verdict": "should_ship",
        "metrics": {
            "pinball_skill_q50": 0.42,
            "coverage_error": 0.05,
            "n_train": 500,
        },
        "nested": {"a": [1, 2, 3], "b": {"c": "deep"}},
    }
    rid = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/fake.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        acceptance_report=report,
        dsn=dsn,
    )
    assert rid is not None
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT acceptance_report FROM learning.model_registry WHERE id = %s",
            (rid,),
        )
        retrieved = cur.fetchone()[0]
        # psycopg returns JSONB as Python dict; equality includes nested.
        # psycopg 把 JSONB 回成 Python dict；== 含巢狀比較。
        assert retrieved == report


# ───── Partial index existence + definition check ───────────────────


def test_production_latest_partial_index_exists(pg_conn):
    """V023 creates `idx_model_registry_production_latest` as a partial index
    with `WHERE canary_status IN ('production', 'promoting')`. Critical for
    hot-path resolver perf — absence → seq scan every tick in Phase 3+.

    V023 建 partial index，WHERE canary_status IN ('production','promoting')；
    缺此 index → Phase 3+ hot-path 每 tick 全表掃。"""
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'learning' AND tablename = 'model_registry'"
        )
        indexes = {r[0]: r[1] for r in cur.fetchall()}
        assert "idx_model_registry_production_latest" in indexes, (
            "missing partial index — hot-path resolver will seq-scan"
        )
        idxdef = indexes["idx_model_registry_production_latest"]
        # WHERE clause must mention both states.
        # WHERE 子句必須兩個狀態都包。
        assert "production" in idxdef
        assert "promoting" in idxdef


def test_expected_indexes_all_present(pg_conn):
    """Drift guard: V023 creates 4 indexes (PK + 3 explicit). If a future
    migration drops any, downstream queries degrade silently.
    漂移守：V023 建 4 個 index（PK + 3 顯式）；任一缺失 → 下游查詢靜默降級。"""
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'learning' AND tablename = 'model_registry'"
        )
        idx_names = {r[0] for r in cur.fetchall()}
    expected = {
        "model_registry_pkey",  # BIGSERIAL PK
        "uq_model_registry_identity",
        "idx_model_registry_production_latest",
        "idx_model_registry_canary_status_created",
        "idx_model_registry_train_date",
    }
    missing = expected - idx_names
    assert not missing, f"missing indexes: {missing}"
