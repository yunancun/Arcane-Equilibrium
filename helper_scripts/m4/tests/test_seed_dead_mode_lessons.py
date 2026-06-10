"""seed_dead_mode_lessons 測試 — fake conn 驗 SQL 構造 / 冪等分支 / 默認無害 CLI。

測試隔離鐵則（承 2026-06-10 prod 污染事故 0ce45a09；本檔不在 control_api_v1 conftest
全域隔離範圍）：autouse fixture 把 sys.modules['psycopg2'] 換成 connect 即 raise 的
stub——本檔任何測試**結構上不可能**建立真 DB 連線；需要連線行為的測試顯式注入
FakeConnection。Mac 假綠 ≠ 安全：連得上 prod 的環境就真寫，故隔離在 import 層鎖死。

覆蓋（對映 PA owed-conductor-wiring 設計 §C）：
  - seed 內容不變量：6 條 / 欄位值（symbol=ml_advisory / lesson_type=dead_mode /
    source=dead_mode_seed / context_id=seed:<slug> 唯一）/ content 英文主幹（pg_trgm
    可檢索）/ 不含 listing fade。
  - CLI 默認 dry-run 零連線；--apply 無 --dsn fail-closed；--apply 與 --dry-run 互斥。
  - SQL 構造：INSERT ... WHERE NOT EXISTS + 全參數綁定（content 不進 SQL 字面）。
  - 冪等分支：rowcount=0（已存在）→ inserted=0 skipped=6。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SRV_ROOT = Path(__file__).resolve().parents[3]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.m4.seed_dead_mode_lessons import (  # noqa: E402
    DEAD_MODE_SEEDS,
    SEED_LESSON_TYPE,
    SEED_SOURCE,
    SEED_SYMBOL,
    apply_seeds,
    build_seed_rows,
    main,
)


# ─────────────────────────────────────────────────────────
# 連線層隔離（autouse）+ fakes
# ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """全域鎖死真連線：psycopg2.connect 一被呼叫即 AssertionError。

    為什麼放 sys.modules 層：seed script 的 psycopg2 是 lazy import（main() 內），
    在 import 層替換 stub 可同時涵蓋「環境沒裝 psycopg2」與「環境裝了且連得上 prod」
    兩種情況——測試在任何機器上都零連線風險。
    """
    stub = types.ModuleType("psycopg2")

    def _refuse_connect(*args, **kwargs):
        raise AssertionError(f"測試禁止真 DB 連線（attempted dsn={args} {kwargs}）")

    stub.connect = _refuse_connect
    monkeypatch.setitem(sys.modules, "psycopg2", stub)
    yield stub


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self._fetchone_row = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: dict) -> None:
        self.conn.executed.append((sql, dict(params)))
        if "INSERT INTO agent.lessons" in sql:
            # rowcount 模擬：existing context_id → 0（WHERE NOT EXISTS 擋）；否則 1。
            if params["context_id"] in self.conn.existing_context_ids:
                self.rowcount = 0
            else:
                self.rowcount = 1
                self.conn.existing_context_ids.add(params["context_id"])
            return
        if "SELECT count(*)" in sql:
            self._fetchone_row = (len(self.conn.existing_context_ids),)
            self.rowcount = 1
            return
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    def fetchone(self):
        return self._fetchone_row


class FakeConnection:
    def __init__(self, existing_context_ids: set[str] | None = None) -> None:
        self.existing_context_ids: set[str] = set(existing_context_ids or set())
        self.executed: list[tuple[str, dict]] = []
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


# ─────────────────────────────────────────────────────────
# seed 內容不變量（純函數，0 DB）
# ─────────────────────────────────────────────────────────


def test_seed_rows_field_invariants():
    """6 條；欄位值對齊檢索鏈（PA §C.1）：symbol/lesson_type/source/context_id 前綴。"""
    rows = build_seed_rows()
    assert len(rows) == 6
    for row in rows:
        # symbol 必 = sink placeholder：與 _check_novelty 檢索 symbol 不一致 = 永 miss 死資料。
        assert row["symbol"] == SEED_SYMBOL == "ml_advisory"
        assert row["lesson_type"] == SEED_LESSON_TYPE == "dead_mode"
        assert row["source"] == SEED_SOURCE == "dead_mode_seed"
        assert row["context_id"].startswith("seed:")
        assert row["session_trigger"] == "seed:2026-06-10"
    # context_id 唯一（冪等錨點）。
    ids = [r["context_id"] for r in rows]
    assert len(set(ids)) == 6


def test_seed_slugs_grounded_in_real_nogos_no_listing_fade():
    """slug 集合 = 6 個真實 NO-GO 家族；不 seed listing fade（active 主路徑非 dead mode）。"""
    slugs = {s["slug"] for s in DEAD_MODE_SEEDS}
    assert slugs == {
        "funding_arb_v2",
        "funding_short_v2",
        "cascade_fade_h2",
        "funding_tilt",
        "grid_short_downtrend",
        "textbook_scalping_family",
    }
    for seed in DEAD_MODE_SEEDS:
        assert "listing" not in seed["content"].lower()


def test_seed_content_english_trigram_searchable():
    """content 英文主幹（pg_trgm 字面 trigram：中文 content vs 英文 hint 相似度≈0 = 死資料）。

    同時驗模板結構：DEAD MODE [family] + Why dead（機制）+ Evidence（數字）。
    """
    for seed in DEAD_MODE_SEEDS:
        content = seed["content"]
        assert content.isascii(), f"{seed['slug']} content 非純 ASCII（trgm 檢索會 miss）"
        assert content.startswith("DEAD MODE [")
        assert "Why dead:" in content
        assert "Evidence:" in content
        assert len(content) < 4000  # critic persist 路徑的 content cap 同界


# ─────────────────────────────────────────────────────────
# CLI：默認 dry-run 零連線 / fail-closed 參數
# ─────────────────────────────────────────────────────────


def test_default_dry_run_prints_and_never_connects(capsys, _no_real_db):
    """無參數 = dry-run：print 6 條、exit 0、psycopg2.connect 不被觸（stub 觸了會 raise）。"""
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    for seed in DEAD_MODE_SEEDS:
        assert f"seed:{seed['slug']}" in out


def test_explicit_dry_run_flag_same_behavior(capsys):
    """顯式 --dry-run 與默認等價（自描述 flag）。"""
    rc = main(["--dry-run"])
    assert rc == 0
    assert "DRY-RUN" in capsys.readouterr().out


def test_apply_without_dsn_fails_closed():
    """--apply 無 --dsn → parser.error（SystemExit≠0）：不隱式 fallback 任何連線。"""
    with pytest.raises(SystemExit) as exc:
        main(["--apply"])
    assert exc.value.code != 0


def test_apply_and_dry_run_mutually_exclusive():
    """--apply 與 --dry-run 互斥（語義矛盾必須 loud 拒絕）。"""
    with pytest.raises(SystemExit) as exc:
        main(["--apply", "--dry-run", "--dsn", "postgresql://x"])
    assert exc.value.code != 0


def test_main_apply_uses_injected_dsn_and_closes(monkeypatch, capsys):
    """--apply --dsn：connect 收到顯式 DSN；寫後 close；print inserted/count。"""
    fake_conn = FakeConnection()
    seen_dsn: list[str] = []

    def _fake_connect(dsn):
        seen_dsn.append(dsn)
        return fake_conn

    stub = types.ModuleType("psycopg2")
    stub.connect = _fake_connect
    monkeypatch.setitem(sys.modules, "psycopg2", stub)

    rc = main(["--apply", "--dsn", "postgresql://test-only"])
    assert rc == 0
    assert seen_dsn == ["postgresql://test-only"]
    assert fake_conn.closed is True
    out = capsys.readouterr().out
    assert "inserted=6" in out
    assert "count=6" in out


def test_write_alias_equivalent_to_apply(monkeypatch):
    """--write 是 --apply 的 alias（PA §C.4 用詞 --write、派發描述用詞 --apply，雙收斂）。"""
    fake_conn = FakeConnection()
    stub = types.ModuleType("psycopg2")
    stub.connect = lambda dsn: fake_conn
    monkeypatch.setitem(sys.modules, "psycopg2", stub)
    rc = main(["--write", "--dsn", "postgresql://test-only"])
    assert rc == 0
    inserts = [sql for sql, _ in fake_conn.executed if "INSERT" in sql]
    assert len(inserts) == 6


# ─────────────────────────────────────────────────────────
# SQL 構造 + 冪等分支（fake conn 直驅 apply_seeds）
# ─────────────────────────────────────────────────────────


def test_apply_seeds_sql_shape_and_param_binding():
    """每條 INSERT 含 WHERE NOT EXISTS；content 全走參數綁定，不進 SQL 字面。"""
    conn = FakeConnection()
    inserted, skipped = apply_seeds(conn, build_seed_rows())
    assert (inserted, skipped) == (6, 0)
    assert conn.commits == 1
    assert len(conn.executed) == 6
    for sql, params in conn.executed:
        assert "INSERT INTO agent.lessons" in sql
        assert "WHERE NOT EXISTS" in sql
        # 冪等錨點雙條件（source + context_id）都在 SQL 內以綁定形式出現。
        assert "source = %(source)s" in sql
        assert "context_id = %(context_id)s" in sql
        # forward-stub 欄位以 NULL 字面寫入（V133 規則：恆 NULL）。
        assert "NULL, NULL" in sql
        # 注入面驗證：英文長文本不在 SQL 字面，只在綁定參數。
        assert params["content"] not in sql
        assert params["content"].startswith("DEAD MODE [")
        assert params["source"] == SEED_SOURCE


def test_apply_seeds_idempotent_rerun_inserts_zero():
    """冪等：第一跑 inserted=6；同 conn 重跑 inserted=0 skipped=6（WHERE NOT EXISTS 擋）。"""
    conn = FakeConnection()
    rows = build_seed_rows()
    first = apply_seeds(conn, rows)
    second = apply_seeds(conn, rows)
    assert first == (6, 0)
    assert second == (0, 6)
    # 兩輪都「嘗試」了 6 條 INSERT（冪等靠 SQL 而非 client 端跳過——重跑安全不依賴狀態）。
    assert len(conn.executed) == 12
    assert len(conn.existing_context_ids) == 6


def test_apply_seeds_partial_existing_only_fills_gap():
    """部分已存在（如前次中斷）→ 只補缺的（gap-fill），不重複既有。"""
    conn = FakeConnection(existing_context_ids={"seed:funding_arb_v2", "seed:funding_tilt"})
    inserted, skipped = apply_seeds(conn, build_seed_rows())
    assert (inserted, skipped) == (4, 2)
    assert len(conn.existing_context_ids) == 6
