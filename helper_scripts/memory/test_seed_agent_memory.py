"""seed_agent_memory 測試（B 源解析 / 敏感網 / 冪等錨 / dry-run / fake-conn 寫路徑）。

MODULE_NOTE
模塊用途：釘死 seed CLI（PA 2026-06-11 spec §9/§13.1）load-bearing 行為，
  全部 Mac 可跑（0 真 PG）：
    1. MEMORY.md 索引行解析：feedback_→rule(80)、project_→incident(70)、
       reference_* 與「External tool authority」節排除。
    2. 敏感網雙層：keyword regex + 個人路徑 detector，命中 skip+列報告。
    3. 冪等錨 record_id = mem:seed:sha12(content)。
    4. 默認 dry-run：0 DB 連線（注入毒 psycopg2 自證）；對「真」repo
       MEMORY.md 跑通（PM 指定驗收）。
    5. --apply 寫路徑（fake conn）：INSERT ... ON CONFLICT DO NOTHING、
       全參數綁定、0 DELETE/UPDATE、recall 驗收空命中 ⇒ exit 1。
依賴：pytest + 標準庫。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_MEMORY_DIR = Path(__file__).resolve().parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

import seed_agent_memory as mod  # noqa: E402

# 個人路徑樣本以 runtime 拼接構造：避免測試檔字面出現 home 路徑形狀
# （跨平台紅線 grep 防誤中，per memory feedback_cross_platform）。
_FAKE_USER_PATH = "/" + "Users" + "/someone/.ssh/cfg"
_FAKE_HOME_PATH = "/" + "home" + "/tester/x.env"
_FAKE_POSTGRES_DSN = "postgres" + "://" + "service" + ":" + "pw" + "@dbhost:5432/trading_ai"
_FAKE_POSTGRESQL_DSN = "postgres" + "ql://" + "service" + ":" + "pw" + "@h/db"

_SAMPLE_MD = """# Memory Index

> 引言行不解析。

## Project context
- [事故 A (2026-01-01)](project_alpha_incident.md) — 根因=競態;修=唯一 mutator
- [評估 B](reference_some_tool.md) — 工具評估結論
- 沒有連結格式的行不解析

## Working principles & autonomy
- [原則 C](feedback_some_principle.md) — 永遠 fail-closed
- [洩漏樣本](feedback_leak.md) — 內含 api_key 字樣應被攔
- [路徑樣本](project_path_leak.md) — 提到 {fake_path} 應被攔
- [簽名樣本](feedback_sign_leak.md) — hmac 與 signing_key 輪換筆記應被攔
- [DSN 樣本](project_dsn_leak.md) — 連線串 {fake_dsn} 應被攔

## External tool authority
- [外部工具權威](feedback_external_tool_authority.md) — 整節排除
""".replace("{fake_path}", _FAKE_USER_PATH).replace(
    "{fake_dsn}", _FAKE_POSTGRES_DSN
)


# ─────────────────────────── B 源解析 ───────────────────────────


class TestParseMemoryIndex:
    def _parse(self):
        return mod.parse_memory_index(_SAMPLE_MD)

    def test_project_maps_incident_70(self):
        rows, _ = self._parse()
        row = next(r for r in rows if "project_alpha_incident" in r["source_refs"])
        assert row["mem_type"] == "incident"
        assert row["priority"] == 70
        assert row["scene"] == mod.SCENE_MEMORY_INDEX
        assert row["content"].startswith("事故 A (2026-01-01) — 根因=競態")

    def test_feedback_maps_rule_80(self):
        rows, _ = self._parse()
        row = next(r for r in rows if "feedback_some_principle" in r["source_refs"])
        assert row["mem_type"] == "rule"
        assert row["priority"] == 80

    def test_reference_prefix_excluded(self):
        rows, skipped = self._parse()
        assert not any("reference_some_tool" in r["source_refs"] for r in rows)
        assert ("reference_some_tool.md", "prefix_not_whitelisted") in skipped

    def test_external_tool_authority_section_excluded(self):
        # feedback_ 前綴本可入白名單——但整節排除優先（spec §9 B 源裁決）。
        rows, skipped = self._parse()
        assert not any(
            "feedback_external_tool_authority" in r["source_refs"] for r in rows
        )
        reasons = dict(skipped)
        assert reasons["feedback_external_tool_authority.md"].startswith(
            "excluded_section:"
        )

    def test_sensitive_keyword_skipped(self):
        rows, skipped = self._parse()
        assert not any("feedback_leak" in r["source_refs"] for r in rows)
        reasons = dict(skipped)
        assert reasons["feedback_leak.md"].startswith("sensitive_keyword:")

    def test_personal_path_skipped_without_echo(self):
        rows, skipped = self._parse()
        assert not any("project_path_leak" in r["source_refs"] for r in rows)
        reasons = dict(skipped)
        # path 命中不 echo 匹配片段（匹配內容本身可能就是要遮的資訊）。
        assert reasons["project_path_leak.md"] == "personal_path"

    def test_non_index_lines_ignored(self):
        rows, skipped = self._parse()
        idents = [i for i, _ in skipped]
        assert "沒有連結格式的行不解析" not in str(idents)
        # 3 入選：project_alpha + feedback_some_principle；洩漏兩條與 reference
        # 與 external 節被攔 ⇒ rows 恰 2 條。
        assert len(rows) == 2

    def test_source_refs_shape(self):
        rows, _ = self._parse()
        import json

        refs = json.loads(rows[0]["source_refs"])
        assert refs[0]["kind"] == "memory_topic"
        assert refs[0]["path"].startswith("memory/")


# ─────────────────────────── 冪等錨 / 敏感網單元 ───────────────────────────


class TestRecordIdAndSensitive:
    def test_record_id_stable_prefixed(self):
        a = mod.make_record_id("同一內容")
        b = mod.make_record_id("同一內容")
        assert a == b
        assert a.startswith(mod.RECORD_ID_PREFIX)
        assert len(a) == len(mod.RECORD_ID_PREFIX) + 12

    def test_record_id_differs_by_content(self):
        assert mod.make_record_id("a") != mod.make_record_id("b")

    @pytest.mark.parametrize(
        "text",
        [
            "leaked api_key=xyz",
            "leaked API-KEY here",
            "my Secret stash",
            "the PASSWORD is",
            "bearer token list",
            f"see {_FAKE_HOME_PATH} for detail",
            f"see {_FAKE_USER_PATH} for detail",
            # E3 修復輪補全（簽名/DSN 家族）：
            "HMAC 簽名流程筆記",
            "rotate the signing_key quarterly",
            "auth_signing_key 已輪換",  # substring 蓋長名
            "store the signing-key safely",
            "private_key in slot 2",
            "X-BAPI-SIGN header mismatch",
            "x-bapi-sign 大小寫不敏感",
            f"dsn={_FAKE_POSTGRES_DSN}",
            f"dsn={_FAKE_POSTGRESQL_DSN}",
        ],
    )
    def test_sensitive_hits(self, text):
        assert mod.sensitive_reason(text) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "beta 中性化檢驗必跑;demo fills 估 edge",
            # 無密碼 DSN = 純 host 引用非機密，不誤殺（E3 修復輪負向釘）。
            "讀庫走 postgres://dbhost:5432/trading_ai 唯讀",
            "postgresql://localhost/devdb 本機庫",
        ],
    )
    def test_clean_text_passes(self, text):
        assert mod.sensitive_reason(text) is None

    def test_sample_md_sign_and_dsn_lines_skipped(self):
        """構造行級驗證：含 hmac/signing_key 與帶密碼 DSN 的索引行被攔下。"""
        _rows, skipped = mod.parse_memory_index(_SAMPLE_MD)
        reasons = dict(skipped)
        assert reasons["feedback_sign_leak.md"].startswith("sensitive_keyword:")
        assert reasons["project_dsn_leak.md"].startswith("sensitive_keyword:")


# ─────────────────────────── A 源（lessons → rows）───────────────────────────


class TestBuildLessonRows:
    def test_maps_rule_90_with_lesson_ref(self):
        rows, skipped = mod.build_lesson_rows([(7, "DEAD MODE [x]: ...")])
        assert skipped == []
        assert rows[0]["mem_type"] == "rule"
        assert rows[0]["priority"] == 90
        assert rows[0]["scene"] == mod.SCENE_DEAD_MODE
        assert '"id": 7' in rows[0]["source_refs"]

    def test_sensitive_lesson_skipped(self):
        rows, skipped = mod.build_lesson_rows([(9, "uses api_key inside")])
        assert rows == []
        assert skipped[0][0] == "lesson:9"


# ─────────────────────────── dry-run（含對真 MEMORY.md）───────────────────────────


class _PoisonPsycopg2:
    """dry-run 路徑連 connect 都不可達——任何觸碰即 AssertionError。"""

    def connect(self, *_a, **_k):  # pragma: no cover - 觸發即測試失敗
        raise AssertionError("dry-run 不得建立任何 DB 連線")


class TestDryRun:
    def test_dry_run_real_memory_md_parses_and_exits_0(self, capsys, monkeypatch):
        # PM 驗收：對 repo 真 MEMORY.md 跑通 dry-run（禁 --apply）。
        monkeypatch.setitem(sys.modules, "psycopg2", _PoisonPsycopg2())
        rc = mod.main(["--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[DRY-RUN]" in out
        assert "deferred" in out  # A 源誠實列為 deferred（0 DB 連線）
        assert "mem:seed:" in out  # B 源至少一條入選

    def test_real_memory_md_b_source_properties(self):
        text = mod.default_memory_md_path().read_text(encoding="utf-8")
        rows, skipped = mod.parse_memory_index(text)
        assert len(rows) > 10, "真 MEMORY.md 應解析出可觀數量的索引行"
        assert all(
            ('"path": "memory/feedback_' in r["source_refs"])
            or ('"path": "memory/project_' in r["source_refs"])
            for r in rows
        ), "白名單外前綴不得入選"
        assert not any(
            "feedback_external_tool_authority" in r["source_refs"] for r in rows
        ), "External tool authority 節必須整節排除"

    def test_missing_memory_md_exit2(self, tmp_path, capsys):
        rc = mod.main(["--dry-run", "--memory-md", str(tmp_path / "absent.md")])
        assert rc == 2


# ─────────────────────────── --apply 寫路徑（fake conn）───────────────────────────


class FakeCursor:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.owner.executed.append((sql, params))
        self._last_sql = sql

    @property
    def rowcount(self):
        # 冪等模擬：同 record_id 第二次 INSERT 回 0。
        sql, params = self.owner.executed[-1]
        if "INSERT INTO agent.agent_memory" not in sql:
            return 0
        rid = params["record_id"]
        if rid in self.owner.inserted_ids:
            return 0
        self.owner.inserted_ids.add(rid)
        return 1

    def fetchall(self):
        if "FROM agent.lessons" in self._last_sql:
            return self.owner.lessons_rows
        if "FROM agent.agent_memory" in self._last_sql:
            return self.owner.recall_rows
        return []


class FakeConn:
    def __init__(self, lessons_rows=None, recall_rows=None):
        self.executed: list[tuple[str, dict | None]] = []
        self.inserted_ids: set[str] = set()
        self.lessons_rows = lessons_rows or []
        self.recall_rows = recall_rows if recall_rows is not None else [
            ("mem:seed:abcdef123456", 0.42)
        ]
        self.commits = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _fake_psycopg2(conn):
    return SimpleNamespace(connect=lambda *a, **k: conn)


@pytest.fixture()
def small_md(tmp_path):
    p = tmp_path / "MEMORY.md"
    p.write_text(
        "## Project context\n"
        "- [事故 A](project_a.md) — 摘要甲\n"
        "## Working principles & autonomy\n"
        "- [原則 B](feedback_b.md) — 摘要乙\n",
        encoding="utf-8",
    )
    return p


class TestApplyPath:
    def test_apply_requires_dsn_or_env(self, small_md, monkeypatch, capsys):
        for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
            monkeypatch.delenv(var, raising=False)
        rc = mod.main(["--apply", "--memory-md", str(small_md)])
        assert rc == 2
        assert "ERROR" in capsys.readouterr().err

    def test_apply_inserts_idempotent_and_verifies(self, small_md, monkeypatch):
        conn = FakeConn(lessons_rows=[(1, "DEAD MODE [g]: grid short downtrend.")])
        monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(conn))
        rc = mod.main(
            ["--apply", "--dsn", "postgresql://stub/db", "--memory-md", str(small_md)]
        )
        assert rc == 0
        inserts = [
            (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
        ]
        assert len(inserts) == 3  # A 源 1 + B 源 2
        assert all("ON CONFLICT (record_id) DO NOTHING" in s for s, _ in inserts)
        # 全參數綁定：content 不進 SQL 字面。
        assert all(p["content"] not in s for s, p in inserts)
        # 0 DELETE / 0 UPDATE（spec E2 重點 1 同族紀律：seed 只 INSERT）。
        all_sql = " ".join(s.upper() for s, _ in conn.executed)
        assert "DELETE" not in all_sql
        assert "UPDATE" not in all_sql
        # recall 驗收真的跑了（SET LOCAL + 雙 hint）。
        recall_calls = [s for s, _ in conn.executed if "plainto_tsquery" in s]
        assert len(recall_calls) == 2
        assert any("similarity_threshold" in s for s, _ in conn.executed)
        assert conn.closed is True

    def test_apply_rerun_idempotent_inserted_zero(self, small_md, monkeypatch, capsys):
        conn = FakeConn()
        monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(conn))
        assert (
            mod.main(
                ["--apply", "--dsn", "postgresql://stub/db", "--memory-md", str(small_md)]
            )
            == 0
        )
        capsys.readouterr()
        # 同一 conn 物件保留 inserted_ids ⇒ 第二輪全部 rowcount=0。
        assert (
            mod.main(
                ["--apply", "--dsn", "postgresql://stub/db", "--memory-md", str(small_md)]
            )
            == 0
        )
        assert "inserted=0" in capsys.readouterr().out

    def test_recall_zero_hits_exit1(self, small_md, monkeypatch, capsys):
        # spec §9 驗收：不能只驗 INSERT——recall 空命中 = 死資料 ⇒ exit 1。
        conn = FakeConn(recall_rows=[])
        monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(conn))
        rc = mod.main(
            ["--apply", "--dsn", "postgresql://stub/db", "--memory-md", str(small_md)]
        )
        assert rc == 1
        assert "0 命中" in capsys.readouterr().err
