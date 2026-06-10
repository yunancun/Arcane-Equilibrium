"""
L2 P4 online-FDR — α-wealth PG 帳本層 + fdr routes 測試（E1-B 段 1）。

覆蓋（對映 PA P4 §2.3/§4.2/§7 + MIT N-4 + QC FIX-1.1/1.2）：
  - canonical_spec_sha256：與 bridge `_canonical_sha256` 同算法（sort_keys /
    separators=(",",":") / ensure_ascii）字面鎖定 + 已知向量。
  - deterministic_debit_id（MIT N-4）：確定性、無隨機、窗變即變。
  - ledger 寫路徑：family_init 冪等（partial-unique ON CONFLICT）/ debit 負額 +
    k_for_dsr=n_eff / binding 錨定既存 debit / 全部參數化。
  - register_pre_registration：FIX-1.1（supersedes 鏈 head 強制）+ FIX-1.2
    （evidence 窗單調向後延伸；window_start 相等）+ 庫內 hash 對賬。
  - append-only 不變式：store 原始碼 0 UPDATE/DELETE SQL；硬邊界 grep 指紋 0 命中。
  - fdr routes：bind-demo operator-scope auth 第一行（viewer 403 不觸 store）、
    404/422/503 分流、GET wealth 唯讀。

全部注入 fake conn / monkeypatch store，0 真連線（PA §8.2 測試隔離鐵則）。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import inspect
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_alpha_wealth_store as STORE
from app import l2_fdr_routes as ROUTES


# ═══════════════════════════════════════════════════════════════════════════════
# 測試輔助：腳本化 conn（FIFO 順序消費 + SQL 片段自檢；0 真連線）
# ═══════════════════════════════════════════════════════════════════════════════


class _ScriptedConn:
    """注入式 conn（contextmanager+cursor 合一）：execute 依 FIFO 腳本回應。

    script item = (expected_sql_fragment, {"one":..., "all":..., "rowcount":n})；
    execute 時斷言 SQL 含該片段（防腳本與實作順序漂移的假綠）。
    """

    def __init__(self, script: list[tuple[str, dict[str, Any]]]):
        self._script = list(script)
        self.executed: list[tuple[str, Any]] = []
        self._current: dict[str, Any] = {}
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def execute(self, sql: str, params: Any = None) -> None:
        flat = " ".join(str(sql).split())
        self.executed.append((flat, params))
        assert self._script, f"unexpected extra execute: {flat[:120]}"
        frag, res = self._script.pop(0)
        assert frag in flat, f"script fragment mismatch: want '{frag}' in '{flat[:160]}'"
        self._current = res

    def fetchone(self):
        return self._current.get("one")

    def fetchall(self):
        return self._current.get("all", [])

    @property
    def rowcount(self):
        return self._current.get("rowcount", 1)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _provider_for(conn: Any):
    def _p():
        return conn

    return _p


class _NoneConn:
    """provider 回 None conn（db_pool 連不上的形）。"""

    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 純函數：canonical hash / debit_id / family_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanonicalHash:
    def test_algorithm_byte_identical_to_bridge_literal(self):
        """與 residual_hidden_oos_bridge._canonical_sha256 同算法（字面重算對照）。"""
        payload = {"b": 1, "a": {"y": [3, 2], "x": "中文"}, "c": None}
        expected = hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8")
        ).hexdigest()
        assert STORE.canonical_spec_sha256(payload) == expected

    def test_key_order_invariant(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert STORE.canonical_spec_sha256(a) == STORE.canonical_spec_sha256(b)

    def test_source_pins_exact_separators(self):
        """源碼鎖 sort_keys + separators=(",",":") + ensure_ascii（drift 防線）。"""
        src = inspect.getsource(STORE.canonical_spec_sha256)
        assert "sort_keys=True" in src
        assert 'separators=(",", ":")' in src
        assert "ensure_ascii=True" in src


class TestDeterministicDebitId:
    def test_deterministic_and_no_randomness(self):
        """MIT N-4：同輸入恆同 id（重複 100 次），無隨機 / 無 attempt 成分。"""
        ids = {
            STORE.deterministic_debit_id(7, "2026-01-01", "2026-03-01")
            for _ in range(100)
        }
        assert len(ids) == 1
        only = next(iter(ids))
        assert re.fullmatch(r"[0-9a-f]{16}", only)

    def test_window_or_prereg_change_changes_id(self):
        base = STORE.deterministic_debit_id(7, "2026-01-01", "2026-03-01")
        assert STORE.deterministic_debit_id(8, "2026-01-01", "2026-03-01") != base
        assert STORE.deterministic_debit_id(7, "2026-01-02", "2026-03-01") != base
        assert STORE.deterministic_debit_id(7, "2026-01-01", "2026-03-02") != base

    def test_family_id_format(self):
        assert (
            STORE.family_id_for("ml_advisory.hypothesize", "funding")
            == "ml_advisory.hypothesize:funding"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ledger 寫路徑（family_init / balance / debit / binding）
# ═══════════════════════════════════════════════════════════════════════════════


class TestLedgerWrites:
    def test_family_init_idempotent_on_conflict(self):
        conn = _ScriptedConn(
            [("ON CONFLICT (family_id) WHERE event_type = 'family_init'", {"rowcount": 1})]
        )
        STORE.ensure_family_initialized(
            "cap:axis",
            capability_id="cap",
            signal_axis="axis",
            amount=0.005,
            actor_id="t",
            evidence={"alpha_target": 0.05, "gamma": 0.10},
            conn_provider=_provider_for(conn),
        )
        sql, params = conn.executed[0]
        assert "INSERT INTO research.alpha_wealth_ledger" in sql
        assert params[0] == "cap:axis"
        assert params[4] == pytest.approx(0.005)
        assert conn.commits == 1

    def test_family_init_db_unavailable_raises(self):
        with pytest.raises(STORE.AlphaWealthStoreError):
            STORE.ensure_family_initialized(
                "f",
                capability_id="c",
                signal_axis="a",
                amount=0.005,
                actor_id="t",
                conn_provider=_provider_for(_NoneConn()),
            )

    def test_balance_sum_and_param(self):
        conn = _ScriptedConn([("COALESCE(SUM(amount), 0)", {"one": (0.0042,)})])
        bal = STORE.get_family_balance("cap:axis", conn_provider=_provider_for(conn))
        assert bal == pytest.approx(0.0042)
        assert conn.executed[0][1] == ("cap:axis",)

    def test_balance_db_unavailable_raises(self):
        with pytest.raises(STORE.AlphaWealthStoreError):
            STORE.get_family_balance("f", conn_provider=_provider_for(_NoneConn()))

    def test_debit_negative_amount_and_k_for_dsr_equals_n_eff(self):
        """M2 單 debit 合約：amount=−α_i、k_for_dsr 與 n_eff 同值同源。"""
        conn = _ScriptedConn(
            [("ON CONFLICT (debit_id) WHERE event_type = 'debit'", {"rowcount": 1})]
        )
        out = STORE.record_debit(
            family_id="cap:axis",
            capability_id="cap",
            signal_axis="axis",
            debit_id="abc123",
            alpha_i=5e-4,
            n_eff=3,
            pre_reg_id=11,
            actor_id="t",
            conn_provider=_provider_for(conn),
        )
        assert out.ok and not out.deduped
        _, params = conn.executed[0]
        # params: family, cap, axis, event, debit_id, amount, alpha_i, n_eff, k_for_dsr, pre_reg...
        assert params[5] == pytest.approx(-5e-4)  # debit 必為負額
        assert params[7] == 3 and params[8] == 3  # k_for_dsr == n_eff
        assert params[9] == 11

    def test_debit_conflict_rowcount_zero_is_deduped_not_double_charge(self):
        conn = _ScriptedConn([("ON CONFLICT (debit_id)", {"rowcount": 0})])
        out = STORE.record_debit(
            family_id="f",
            capability_id="c",
            signal_axis="a",
            debit_id="dup",
            alpha_i=1e-4,
            n_eff=1,
            pre_reg_id=1,
            actor_id="t",
            conn_provider=_provider_for(conn),
        )
        assert out.ok and out.deduped

    def test_debit_failure_returns_not_ok(self):
        out = STORE.record_debit(
            family_id="f",
            capability_id="c",
            signal_axis="a",
            debit_id="x",
            alpha_i=1e-4,
            n_eff=1,
            pre_reg_id=1,
            actor_id="t",
            conn_provider=_provider_for(_NoneConn()),
        )
        assert not out.ok and out.error == "db_unavailable"

    def test_binding_anchors_existing_debit(self):
        conn = _ScriptedConn(
            [
                ("WHERE event_type = 'debit' AND debit_id = %s", {"one": ("f", "c", "a")}),
                ("INSERT INTO research.alpha_wealth_ledger", {"rowcount": 1}),
            ]
        )
        res = STORE.record_demo_binding(
            debit_id="d1",
            demo_strategy="grid_trading",
            demo_symbol="BTCUSDT",
            demo_deployed_at=dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc),
            actor_id="op",
            conn_provider=_provider_for(conn),
        )
        assert res["ok"] is True
        _, params = conn.executed[1]
        assert "operator_adjustment" in params
        assert "grid_trading" in params and "BTCUSDT" in params

    def test_binding_missing_debit_rejected(self):
        conn = _ScriptedConn(
            [("WHERE event_type = 'debit' AND debit_id = %s", {"one": None})]
        )
        res = STORE.record_demo_binding(
            debit_id="ghost",
            demo_strategy="s",
            demo_symbol="X",
            demo_deployed_at=dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc),
            actor_id="op",
            conn_provider=_provider_for(conn),
        )
        assert res == {"ok": False, "error": "debit_not_found"}
        # 不存在 → 不 INSERT（無第二條 execute）。
        assert len(conn.executed) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# pre-registration（FIX-1.1 / FIX-1.2）
# ═══════════════════════════════════════════════════════════════════════════════


def _spec(ws: str = "2025-01-01", we: str = "2025-12-31", stmt: str = "s1") -> dict:
    return {
        "statement": stmt,
        "mechanism": "carry",
        "signal_axes_used": ["funding"],
        "primary_axis": "funding",
        "falsification_test": {
            "null_hypothesis": "no edge",
            "test_statistic": "dsr",
            "reject_condition": "dsr<thr",
        },
        STORE.SPEC_EVIDENCE_WINDOW_KEY: {"window_start": ws, "window_end": we},
    }


def _row_for(spec: dict, pre_reg_id: int):
    return (pre_reg_id, spec, STORE.canonical_spec_sha256(spec))


class TestPreRegistration:
    def _register(self, conn, spec):
        return STORE.register_pre_registration(
            family_id="cap:funding",
            capability_id="cap",
            signal_axis="funding",
            spec_jsonb=spec,
            source_l2_reply_id="l2r:abc",
            actor_id="t",
            conn_provider=_provider_for(conn),
        )

    def test_fresh_insert_no_prior(self):
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": None}),
                ("ORDER BY pre_reg_id", {"all": []}),
                ("INSERT INTO research.pre_registered_hypotheses", {"one": (42,)}),
            ]
        )
        out = self._register(conn, _spec())
        assert out.ok and out.pre_reg_id == 42
        _, params = conn.executed[2]
        assert params[6] is None  # supersedes NULL（首次）

    def test_exact_hit_head_reused(self):
        spec = _spec()
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": _row_for(spec, 7)}),
                ("supersedes_pre_reg_id = %s", {"one": None}),  # 無人 supersede → head
            ]
        )
        out = self._register(conn, spec)
        assert out.ok and out.pre_reg_id == 7
        assert len(conn.executed) == 2  # 0 INSERT（reuse）

    def test_exact_hit_superseded_defers(self):
        """FIX-1.1：被 supersede 的 pre-reg 不可 consume → DEFER。"""
        spec = _spec()
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": _row_for(spec, 7)}),
                ("supersedes_pre_reg_id = %s", {"one": (1,)}),  # 有人指向它 → 非 head
            ]
        )
        out = self._register(conn, spec)
        assert not out.ok
        assert out.defer_reason == "pre_registration_superseded"

    def test_exact_hit_stored_hash_integrity_failure_defers(self):
        spec = _spec()
        tampered = (7, {"statement": "tampered"}, STORE.canonical_spec_sha256(spec))
        conn = _ScriptedConn([("AND spec_sha256 = %s", {"one": tampered})])
        out = self._register(conn, spec)
        assert not out.ok
        assert out.defer_reason == "pre_registration_mismatch"

    def test_monotonic_window_extension_supersedes_head(self):
        """FIX-1.2：window_start 相等 + window_end 向後延伸 → 新 row 接鏈 head。"""
        prior = _spec(we="2025-06-30")
        new = _spec(we="2025-12-31")
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": None}),
                ("ORDER BY pre_reg_id", {"all": [(7, prior, None)]}),
                ("INSERT INTO research.pre_registered_hypotheses", {"one": (8,)}),
            ]
        )
        out = self._register(conn, new)
        assert out.ok and out.pre_reg_id == 8
        _, params = conn.executed[2]
        assert params[6] == 7  # supersedes = head

    @pytest.mark.parametrize(
        "new_spec",
        [
            _spec(ws="2025-02-01", we="2025-12-31"),  # window_start 偏離
            _spec(we="2025-03-31"),  # window_end 回退
        ],
    )
    def test_window_deviation_defers_mismatch(self, new_spec):
        prior = _spec(we="2025-06-30")
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": None}),
                ("ORDER BY pre_reg_id", {"all": [(7, prior, None)]}),
            ]
        )
        out = self._register(conn, new_spec)
        assert not out.ok
        assert out.defer_reason == "pre_registration_mismatch"

    def test_core_all_superseded_no_head_defers(self):
        prior = _spec(we="2025-06-30")
        # row 7 被 row 9（不同 core）supersede → core match 無 head。
        conn = _ScriptedConn(
            [
                ("AND spec_sha256 = %s", {"one": None}),
                ("ORDER BY pre_reg_id", {"all": [(7, prior, None), (9, _spec(stmt="other"), 7)]}),
            ]
        )
        out = self._register(conn, _spec(we="2025-12-31"))
        assert not out.ok
        assert out.defer_reason == "pre_registration_superseded"

    def test_store_unreachable_raises(self):
        with pytest.raises(STORE.AlphaWealthStoreError):
            self._register(_NoneConn(), _spec())


# ═══════════════════════════════════════════════════════════════════════════════
# append-only / 硬邊界 grep 指紋
# ═══════════════════════════════════════════════════════════════════════════════


def _code_only(module: Any) -> str:
    """剝 COMMENT 與 STRING token 只留真碼（MODULE_NOTE/docstring 合法提及邊界詞不誤紅；
    既有 carbon-layer grep 慣例——但 SQL 字面在 STRING 內，正面查表名須查 raw source）。"""
    src = inspect.getsource(module)
    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


class TestInvariants:
    def test_store_has_no_update_or_delete_sql(self):
        src = inspect.getsource(STORE)
        assert "UPDATE research." not in src
        assert "DELETE FROM" not in src

    @pytest.mark.parametrize(
        "token",
        [
            "promote_tier",
            "acquire_lease",
            "live_execution_allowed",
            "execution_authority",
            "system_mode",
            "OPENCLAW_ALLOW_MAINNET",
            "authorization.json",
        ],
    )
    def test_hard_boundary_fingerprint_zero_hits(self, token):
        for mod in (STORE, ROUTES):
            assert token not in _code_only(mod), f"{token} in {mod.__name__} code"


# ═══════════════════════════════════════════════════════════════════════════════
# fdr routes（auth 第一行 / 分流 / 唯讀）
# ═══════════════════════════════════════════════════════════════════════════════


def _operator_actor():
    a = MagicMock()
    a.roles = {"operator"}
    a.scopes = {"ai_budget:write"}
    a.actor_id = "test_op"
    return a


def _viewer_actor():
    a = MagicMock()
    a.roles = {"viewer"}
    a.scopes = set()
    a.actor_id = "test_viewer"
    return a


def _bind_req(**over) -> ROUTES.FdrBindDemoRequest:
    body = {
        "debit_id": "abc123",
        "demo_strategy": "grid_trading",
        "demo_symbol": "BTCUSDT",
        "demo_deployed_at": "2026-06-01T00:00:00+00:00",
    }
    body.update(over)
    return ROUTES.FdrBindDemoRequest(**body)


class TestFdrRoutes:
    def test_bind_demo_viewer_403_before_store(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            ROUTES._store, "record_demo_binding", lambda **kw: called.append(kw) or {"ok": True}
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ROUTES.bind_demo(_bind_req(), actor=_viewer_actor()))
        assert exc.value.status_code == 403
        assert called == []  # gate 在任何 store 訪問之前

    def test_bind_demo_operator_ok_calls_store_with_utc(self, monkeypatch):
        captured = {}

        def fake_binding(**kw):
            captured.update(kw)
            return {"ok": True, "debit_id": kw["debit_id"], "family_id": "f"}

        monkeypatch.setattr(ROUTES._store, "record_demo_binding", fake_binding)
        out = asyncio.run(ROUTES.bind_demo(_bind_req(), actor=_operator_actor()))
        assert out["data"]["ok"] is True
        assert captured["demo_deployed_at"].tzinfo == dt.timezone.utc
        assert captured["actor_id"] == "test_op"

    def test_bind_demo_missing_debit_404(self, monkeypatch):
        monkeypatch.setattr(
            ROUTES._store,
            "record_demo_binding",
            lambda **kw: {"ok": False, "error": "debit_not_found"},
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ROUTES.bind_demo(_bind_req(), actor=_operator_actor()))
        assert exc.value.status_code == 404

    def test_bind_demo_store_unavailable_503(self, monkeypatch):
        monkeypatch.setattr(
            ROUTES._store,
            "record_demo_binding",
            lambda **kw: {"ok": False, "error": "store_unavailable"},
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ROUTES.bind_demo(_bind_req(), actor=_operator_actor()))
        assert exc.value.status_code == 503

    @pytest.mark.parametrize(
        "bad", ["not-a-date", "2026-06-01T00:00:00"]  # 不可解析 / naive 無時區
    )
    def test_bind_demo_bad_deployed_at_422(self, bad, monkeypatch):
        called = []
        monkeypatch.setattr(
            ROUTES._store, "record_demo_binding", lambda **kw: called.append(kw)
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                ROUTES.bind_demo(_bind_req(demo_deployed_at=bad), actor=_operator_actor())
            )
        assert exc.value.status_code == 422
        assert called == []

    def test_bind_demo_auth_is_first_statement(self):
        """source-grep：require_scope_and_operator 在任何 store 訪問之前（E3-E1 模式）。"""
        src = inspect.getsource(ROUTES.bind_demo)
        gate = src.index("require_scope_and_operator")
        store_touch = src.index("record_demo_binding")
        assert gate < store_touch

    def test_get_wealth_read_only_authenticated_viewer_ok(self, monkeypatch):
        monkeypatch.setattr(
            ROUTES._store,
            "load_wealth_summary",
            lambda family_id=None: {"balances": {"f": 0.005}, "debits": []},
        )
        out = asyncio.run(ROUTES.get_wealth(family_id=None, actor=_viewer_actor()))
        assert out["data"]["balances"] == {"f": 0.005}
        assert out["is_simulated"] is True

    def test_get_wealth_store_error_503(self, monkeypatch):
        def boom(family_id=None):
            raise STORE.AlphaWealthStoreError("down")

        monkeypatch.setattr(ROUTES._store, "load_wealth_summary", boom)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ROUTES.get_wealth(family_id=None, actor=_viewer_actor()))
        assert exc.value.status_code == 503
