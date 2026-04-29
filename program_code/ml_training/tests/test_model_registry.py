"""INFRA-PREBUILD-1 Part B — model_registry.py unit tests (no DB required).
INFRA-PREBUILD-1 B 部 model_registry.py 單測（不需 DB）。

Covers the pure-logic branches that don't require a PostgreSQL connection:
- verdict=no_ship rejection (shouldn't even attempt DB connect)
- unknown verdict rejection
- transition state-machine validation (allowed_from matrix)
- _file_size_and_sha256 behaviour for existing + missing files
- CANARY_STATES / VERDICT_* constants stay aligned with V023 CHECK constraints

Integration with real PG covered in a separate test (DB fixture, not here).
涵蓋無需 PG 連線的純邏輯分支；真 DB 整合測試另檔處理。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from program_code.ml_training.model_registry import (
    CANARY_PRODUCTION,
    CANARY_PROMOTING,
    CANARY_REJECTED,
    CANARY_RETIRED,
    CANARY_SHADOW,
    CANARY_STATES,
    VERDICT_NO_SHIP,
    VERDICT_SHADOW_ONLY,
    VERDICT_SHOULD_SHIP,
    _file_size_and_sha256,
    register_model,
    transition_canary_status,
)


# ───── Constants alignment ──────────────────────────────────────────
# Drift guard: V023 CHECK constraint values must match these tuples.
# 漂移守：V023 CHECK 值必須對齊此處 tuple。


def test_canary_states_tuple_matches_v023():
    """V023 CHECK ('shadow', 'promoting', 'production', 'retired', 'rejected')."""
    assert CANARY_STATES == (
        CANARY_SHADOW, CANARY_PROMOTING, CANARY_PRODUCTION,
        CANARY_RETIRED, CANARY_REJECTED,
    )
    # Exact string values (these hit the DB CHECK — any typo silently breaks).
    # 精確字串（DB CHECK 會比對；typo 會靜默失敗）。
    assert CANARY_SHADOW == "shadow"
    assert CANARY_PROMOTING == "promoting"
    assert CANARY_PRODUCTION == "production"
    assert CANARY_RETIRED == "retired"
    assert CANARY_REJECTED == "rejected"


def test_verdict_constants_align_with_quantile_reports():
    """Mirror of quantile_reports.py verdict values (intentional duplication
    to avoid circular import). V023 CHECK enforces same 3-value enum."""
    assert VERDICT_SHOULD_SHIP == "should_ship"
    assert VERDICT_SHADOW_ONLY == "shadow_only"
    assert VERDICT_NO_SHIP == "no_ship"


# ───── register_model: verdict gate ─────────────────────────────────


def test_register_model_no_ship_returns_none_without_db():
    """no_ship verdict must short-circuit before any DB connect attempt.
    no_ship verdict 必須在 DB 連線前 short-circuit（registry 不該收 no_ship）。"""
    # Even without mocking psycopg, this should return None from the verdict
    # gate before _connect() is called.
    # 即使不 mock psycopg，也應在 verdict gate 回 None，根本不呼 _connect。
    result = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/nonexistent.onnx",
        verdict=VERDICT_NO_SHIP,
    )
    assert result is None


def test_register_model_unknown_verdict_returns_none():
    """Unknown verdict (typo / new value not yet in CHECK) must not write."""
    result = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/nonexistent.onnx",
        verdict="unknown_verdict_future_value",
    )
    assert result is None


def test_register_model_skips_when_db_unavailable(monkeypatch):
    """When OPENCLAW_DATABASE_URL unset and no dsn passed, gracefully skip."""
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)
    result = register_model(
        strategy="ma_crossover",
        engine_mode="demo",
        quantile="q50",
        schema_version="v1",
        train_date="2026-04-23",
        artifact_path="/tmp/nonexistent.onnx",
        verdict=VERDICT_SHOULD_SHIP,
        dsn=None,
    )
    assert result is None


# ───── _file_size_and_sha256 ─────────────────────────────────────────


def test_file_size_and_sha256_on_existing_file():
    """Happy path: real file → real size + sha256."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as f:
        payload = b"fake_onnx_bytes_for_test_" * 100
        f.write(payload)
        fpath = f.name
    try:
        size, sha = _file_size_and_sha256(fpath)
        assert size == len(payload)
        expected_sha = hashlib.sha256(payload).hexdigest()
        assert sha == expected_sha
    finally:
        os.unlink(fpath)


def test_file_size_and_sha256_on_missing_file():
    """Missing file → (None, None), not exception (best-effort provenance)."""
    size, sha = _file_size_and_sha256("/tmp/definitely_nonexistent_path_xyz.onnx")
    assert size is None
    assert sha is None


# ───── transition_canary_status state machine ───────────────────────
# These tests mock _connect to avoid needing PG. Validation happens before
# DB fetch anyway for invalid to_status — those don't even reach _connect.
# mock _connect 避 PG；invalid to_status 在到 _connect 前就被拒。


def test_transition_invalid_status_returns_false():
    """Unknown to_status (not in CANARY_STATES) rejected without DB touch."""
    result = transition_canary_status(
        row_id=1,
        to_status="bogus_status",
    )
    assert result is False


def test_transition_rejects_invalid_from_via_allowed_matrix():
    """Transition matrix: promoting requires current=shadow; production requires
    current=promoting. Test by stub-connecting and returning unexpected current.
    轉移矩陣：promoting 需 current=shadow；production 需 current=promoting。"""
    # Simulate DB returning current=production, attempt promote again → deny.
    # 模擬 DB 回 current=production 時又嘗試 promoting → 應拒。
    class FakeCursor:
        def execute(self, sql, params=None):
            self._last_sql = sql
        def fetchone(self):
            return ("ma_crossover", "demo", "v1", "2026-04-29", "production")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeConn:
        def cursor(self): return FakeCursor()
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("program_code.ml_training.model_registry._connect",
               return_value=FakeConn()):
        result = transition_canary_status(
            row_id=42,
            to_status=CANARY_PROMOTING,
        )
        assert result is False  # current=production can't go back to promoting


def test_transition_retired_requires_production_source():
    """retired can only follow production; from shadow → rejected goes elsewhere."""
    class FakeCursor:
        def execute(self, sql, params=None):
            pass
        def fetchone(self):
            return ("ma_crossover", "demo", "v1", "2026-04-29", "shadow")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeConn:
        def cursor(self): return FakeCursor()
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("program_code.ml_training.model_registry._connect",
               return_value=FakeConn()):
        result = transition_canary_status(
            row_id=99,
            to_status=CANARY_RETIRED,
            retirement_reason="pre-prod never promoted",
        )
        assert result is False  # shadow → retired not allowed


def test_transition_shadow_to_rejected_allowed():
    """Shadow → rejected IS allowed (pre-prod rejection path)."""
    class FakeCursor:
        _executed_updates = []
        _last_sql = ""
        def execute(self, sql, params=None):
            self._last_sql = sql
            if "UPDATE" in sql:
                self._executed_updates.append((sql, params))
        def fetchone(self):
            return ("ma_crossover", "demo", "v1", "2026-04-29", "shadow")
        def fetchall(self):
            return [
                (1, "q10", "shadow"),
                (2, "q50", "shadow"),
                (3, "q90", "shadow"),
            ]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeConn:
        def cursor(self): return FakeCursor()
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    fake_cur = FakeCursor()  # module-level var persists across with-blocks
    with patch("program_code.ml_training.model_registry._connect",
               return_value=FakeConn()):
        result = transition_canary_status(
            row_id=1,
            to_status=CANARY_REJECTED,
            retirement_reason="low Brier score on shadow",
        )
        # Transition logic accepted; return value reflects execute + commit path.
        # 轉移邏輯通過；return value 反映 execute + commit 是否成功。
        assert result is True


def test_transition_rejects_incomplete_quantile_trio():
    """No q50-only promotion: q10/q50/q90 must transition together."""
    class FakeCursor:
        def execute(self, sql, params=None):
            pass
        def fetchone(self):
            return ("ma_crossover", "demo", "v1", "2026-04-29", "shadow")
        def fetchall(self):
            return [(2, "q50", "shadow")]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeConn:
        def cursor(self): return FakeCursor()
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("program_code.ml_training.model_registry._connect", return_value=FakeConn()):
        assert transition_canary_status(row_id=2, to_status=CANARY_PROMOTING) is False


# ───── INFRA-PREBUILD-1 audit L2-3: ON CONFLICT canary preserve ─────
# Static SQL drift guard: the ON CONFLICT DO UPDATE clause MUST filter out
# rows where canary_status IN ('promoting', 'production') so a re-training
# run cannot silently rewrite artifact_path / verdict / acceptance_report
# on top of a promoted model slot. Without the filter, the promoted canary
# or production ONNX gets swapped behind Operator's back. Source-level
# assertion so this test stays green without a live PG connection.
# INFRA-PREBUILD-1 審計 L2-3：ON CONFLICT DO UPDATE 必須用
# `WHERE canary_status NOT IN ('promoting','production')` 過濾已晉升列，
# 否則 retrain 會把 canary / production ONNX 的 metadata 覆寫。純源碼
# 斷言，不需要 live PG 連線。


def test_register_model_sql_has_canary_preserve_where_clause():
    """Drift guard: ON CONFLICT DO UPDATE must filter out promoting/production rows
    so re-training doesn't regress an already-promoted model back to shadow metadata.
    漂移守：ON CONFLICT DO UPDATE 需過濾 promoting/production，retrain 不能回退已晉升 model。"""
    from program_code.ml_training import model_registry
    import inspect
    src = inspect.getsource(model_registry.register_model)
    assert "canary_status NOT IN" in src, \
        "register_model SQL lost canary_status preserve filter — retrain could regress promoting/production"
    assert "'promoting'" in src
    assert "'production'" in src


# ───── INFRA-PREBUILD-1 P3-1 (2026-04-23): ExitSource 4-tag cross-layer drift ─
# 4 storage sites must agree on the exact 4-string tag vocabulary:
#   1. Rust const EXIT_SOURCE_TAGS (combine_layer.rs)
#   2. V021 CHECK on trading.fills.exit_source
#   3. V021 CHECK on learning.decision_shadow_exits.exit_source
#   4. Python VALID_EXIT_SOURCES (ml_routes.py)
# Any drift → silent runtime rejection or ORM mis-cast. Test greps + imports
# to verify all 4 sites stay aligned without spinning up a real PG / engine.
#
# INFRA-PREBUILD-1 P3-1（2026-04-23）：ExitSource 4-tag 跨層漂移守。4 個儲存點
# 必須共享一致 4-string 字典。drift → runtime 靜默拒收或 ORM mis-cast。
# grep + import 驗證，不需 live PG / engine。


def test_exit_source_tags_aligned_across_layers():
    """INFRA-PREBUILD-1 P3-1: ExitSource 4-tag dict drift guard.

    Rust combine_layer.rs EXIT_SOURCE_TAGS / V021 CHECK (x2) / ml_routes
    VALID_EXIT_SOURCES must all align. Any drift red-lights this test.

    Uses source-level grep for ml_routes to avoid a fastapi/pydantic import
    dependency on Mac dev envs that don't install them (the test should be
    runnable without the full API stack).

    INFRA-PREBUILD-1 P3-1：ExitSource 4-tag 字典漂移守。Rust EXIT_SOURCE_TAGS /
    V021 CHECK x2 / Python VALID_EXIT_SOURCES 必須對齊；任一漂移本測試紅。
    對 ml_routes 走源碼 grep 避免 fastapi/pydantic import 依賴（Mac dev 通常
    不裝全 API stack），測試在 bare Python 環境亦可跑。
    """
    expected = ("Physical", "Hybrid", "ML", "Disabled")
    srv_root = Path(__file__).parent.parent.parent.parent

    # (1) Python ml_routes VALID_EXIT_SOURCES — source-level grep (avoid
    #     fastapi/pydantic import cost + Mac-dev missing-deps false red).
    # (1) Python ml_routes VALID_EXIT_SOURCES — 源碼 grep，避免 fastapi/pydantic
    #     import 依賴（Mac dev 可能沒裝 → 假紅）。
    ml_routes = (
        srv_root / "program_code" / "exchange_connectors" / "bybit_connector"
        / "control_api_v1" / "app" / "ml_routes.py"
    )
    assert ml_routes.exists(), f"ml_routes.py missing at {ml_routes}"
    py_src = ml_routes.read_text()
    assert "VALID_EXIT_SOURCES" in py_src, (
        "ml_routes.py missing VALID_EXIT_SOURCES constant — P3-1 drift guard broken"
    )
    # The tuple literal must name each tag in quotes (order-insensitive grep).
    # tuple 字面值必須以引號列出每個 tag（無序 grep）。
    for tag in expected:
        assert f'"{tag}"' in py_src, (
            f"ml_routes.py missing VALID_EXIT_SOURCES tag literal: \"{tag}\""
        )

    # (2) V021 migration content must mention each tag as a quoted literal
    # (2) V021 遷移檔必須每個 tag 都以引號字串出現
    v021 = srv_root / "sql" / "migrations" / "V021__fills_exit_source.sql"
    assert v021.exists(), f"V021 migration missing at {v021}"
    sql = v021.read_text()
    for tag in expected:
        assert f"'{tag}'" in sql, f"V021 CHECK missing tag literal: '{tag}'"

    # (3) Rust combine_layer.rs must declare EXIT_SOURCE_TAGS + each tag literal
    # (3) Rust combine_layer.rs 必須宣告 EXIT_SOURCE_TAGS 且每個 tag 字面值到位
    combine = srv_root / "rust" / "openclaw_engine" / "src" / "combine_layer.rs"
    assert combine.exists(), f"combine_layer.rs missing at {combine}"
    rust_src = combine.read_text()
    assert "EXIT_SOURCE_TAGS" in rust_src, (
        "combine_layer.rs missing EXIT_SOURCE_TAGS const — P3-1 drift guard broken"
    )
    for tag in expected:
        assert f'"{tag}"' in rust_src, (
            f"combine_layer.rs missing Rust string literal for tag: \"{tag}\""
        )


# ───── INFRA-PREBUILD-1 P3-2 (2026-04-23): Python ModelSlot validation ───
# Mirrors Rust ml::registry::ModelSlot; validate engine_mode / quantile
# against the same 4 × 3 tag domains V023 CHECK enforces. Operator-facing
# type so mistyped params fail at API boundary, not at DB.
#
# INFRA-PREBUILD-1 P3-2（2026-04-23）：Python ModelSlot 驗證。鏡像 Rust
# ml::registry::ModelSlot；engine_mode / quantile 與 V023 CHECK 同域
# (4 × 3)。操作者側型別，typo 在 API 邊界拒，不落 DB。


# Mac dev envs may lack fastapi/pydantic; ml_routes import chain requires both.
# Linux runtime + CI have them; skip gracefully rather than fail on Mac.
# Mac dev 可能沒裝 fastapi/pydantic；Linux runtime + CI 都有。缺包時優雅 skip。
def _ml_routes_available() -> bool:
    try:
        import fastapi  # noqa: F401
        import pydantic  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not _ml_routes_available(),
    reason="fastapi/pydantic not installed (Mac dev env); ModelSlot validation exercised on Linux",
)
def test_model_slot_accepts_valid_combinations():
    """Happy path: all 4 × 3 combinations construct successfully.
    正常路徑：全部 4 × 3 組合皆可構造。"""
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ml_routes import (
        ModelSlot,
    )
    for eng in ("paper", "demo", "live", "live_demo"):
        for q in ("q10", "q50", "q90"):
            slot = ModelSlot(strategy="ma_crossover", engine_mode=eng, quantile=q)
            assert slot.strategy == "ma_crossover"
            assert slot.engine_mode == eng
            assert slot.quantile == q


@pytest.mark.skipif(
    not _ml_routes_available(),
    reason="fastapi/pydantic not installed (Mac dev env)",
)
def test_model_slot_rejects_invalid_engine_mode():
    """Typo engine_mode → ValidationError at construction.
    engine_mode typo → 構造時 ValidationError。"""
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ml_routes import (
        ModelSlot,
    )
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ModelSlot(strategy="ma_crossover", engine_mode="main_net", quantile="q50")
    # Case-sensitive: "Demo" with capital D must be rejected too.
    # 大小寫敏感：大寫 "Demo" 也必須被拒。
    with pytest.raises(ValidationError):
        ModelSlot(strategy="ma_crossover", engine_mode="Demo", quantile="q50")


@pytest.mark.skipif(
    not _ml_routes_available(),
    reason="fastapi/pydantic not installed (Mac dev env)",
)
def test_model_slot_rejects_invalid_quantile():
    """Typo quantile (q05 / q99 / median) → ValidationError.
    quantile typo → ValidationError。"""
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ml_routes import (
        ModelSlot,
    )
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ModelSlot(strategy="ma_crossover", engine_mode="demo", quantile="q05")
    with pytest.raises(ValidationError):
        ModelSlot(strategy="ma_crossover", engine_mode="demo", quantile="median")


@pytest.mark.skipif(
    not _ml_routes_available(),
    reason="fastapi/pydantic not installed (Mac dev env)",
)
def test_model_slot_rejects_empty_strategy():
    """Empty strategy name → ValidationError (min_length=1 on Field).
    空 strategy → ValidationError（Field min_length=1）。"""
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ml_routes import (
        ModelSlot,
    )
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ModelSlot(strategy="", engine_mode="demo", quantile="q50")
