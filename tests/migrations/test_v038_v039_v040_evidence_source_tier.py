"""Mock-based unit tests for REF-20 R20-P2a-S6 evidence_source_tier 3-step retrofit.

REF-20 R20-P2a-S6 evidence_source_tier 三步回補的 mock 單元測試。

We do not run psql against a real database in this Mac dev test layer; instead
we statically parse the migration SQL files and verify the structural contract:

1. V038 ADDs evidence_source_tier as TEXT NULLABLE (no NOT NULL keyword in
   the ADD COLUMN statement).
2. V039 backfills NULL → 'real_outcome' for the 3 P0-T7 allowlisted sources
   AND writes a governance_audit_log row.
3. V040 SETs NOT NULL on the column.
4. V040 ADDs the 4-value CHECK constraint chk_evidence_source_tier.

Linux Operator deploys with real psql + the Guard B / Guard B' / Guard B''
runtime checks defined in the SQL files. This test layer is the static
compile-time gate (E2 review-ready bundle on Mac dev).

我們在 Mac dev 測試層不對真實資料庫跑 psql；改為靜態 parse migration SQL 檔，驗證結構契約：
1. V038 加 evidence_source_tier 為 TEXT NULLABLE（ADD COLUMN 語句不含 NOT NULL）。
2. V039 對 3 個 P0-T7 白名單 source 將 NULL 回填為 'real_outcome'，並寫一條 governance_audit_log。
3. V040 對欄位加 NOT NULL。
4. V040 加 4 值 CHECK 約束 chk_evidence_source_tier。

Linux operator 部署時跑真 psql + 各 Guard B 動態檢查。本測試層是靜態編譯期 gate（Mac dev E2 審查）。

Test invocation / 測試呼叫:
    pytest srv/tests/migrations/test_v038_v039_v040_evidence_source_tier.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §3 G3 + §4.2
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3 R20-P2a-S6
- docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_source_classification.md
- sql/migrations/REF-20_RESERVATION.md §3 V038 / V039 / V040
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# Resolve relative to repo root (srv/) regardless of pytest invocation cwd.
# 不依 pytest 呼叫 cwd；以本測試檔位置回推 srv/ repo 根。
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V038_PATH = _MIGRATIONS_DIR / "V038__add_evidence_source_tier.sql"
V039_PATH = _MIGRATIONS_DIR / "V039__backfill_evidence_source_tier.sql"
V040_PATH = _MIGRATIONS_DIR / "V040__finalize_evidence_source_tier.sql"
V040_HEALTHCHECK_PATH = _MIGRATIONS_DIR / "V040_healthcheck.sql"


# ---------------------------------------------------------------------------
# Helpers / 工具函數
# ---------------------------------------------------------------------------
def _read_sql(path: Path) -> str:
    """Read full SQL file as text. / 讀取完整 SQL 檔為文字。"""
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments so keyword greps don't false-positive on
    docstring text describing the constraint we are about to add.

    去除 `-- ...` 行註解，避免關鍵字 grep 誤命中描述約束的 docstring 文字。
    """
    return "\n".join(
        re.sub(r"--.*$", "", line) for line in sql.splitlines()
    )


# ---------------------------------------------------------------------------
# Tests / 測試
# ---------------------------------------------------------------------------
class TestV038AddColumn:
    """V038: ADD COLUMN evidence_source_tier TEXT NULLABLE / V038：加 nullable 欄位。"""

    def test_adds_nullable_text_column(self):
        """V038 must ADD COLUMN evidence_source_tier TEXT (no NOT NULL).

        V038 必加 evidence_source_tier TEXT 欄位（不可帶 NOT NULL）。
        """
        sql = _strip_sql_comments(_read_sql(V038_PATH))

        # Match `ADD COLUMN [IF NOT EXISTS] evidence_source_tier TEXT` allowing
        # whitespace variations; require `;` or end-of-line right after TEXT
        # to ensure NOT NULL is not appended.
        # 用 regex 匹配 `ADD COLUMN ... evidence_source_tier TEXT`，允許空白變體；
        # 要求 TEXT 後直接 `;` 或行尾，確保未掛 NOT NULL。
        pattern = re.compile(
            r"ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+evidence_source_tier\s+TEXT\s*;",
            re.IGNORECASE,
        )
        assert pattern.search(sql), (
            "V038 must contain `ADD COLUMN [IF NOT EXISTS] evidence_source_tier TEXT;` "
            "without NOT NULL (V038 stays nullable; V040 enforces NOT NULL)."
        )

        # Defense: explicitly assert no `evidence_source_tier ... NOT NULL` in the
        # ADD COLUMN region. We grep for the token combo regardless of position.
        # 防禦性斷言：ADD COLUMN 區內無 `evidence_source_tier ... NOT NULL`。
        not_null_pattern = re.compile(
            r"ADD\s+COLUMN[^;]*evidence_source_tier[^;]*NOT\s+NULL",
            re.IGNORECASE,
        )
        assert not not_null_pattern.search(sql), (
            "V038 ADD COLUMN must not contain NOT NULL; V040 enforces it."
        )

    def test_v038_has_guard_b(self):
        """V038 must contain Guard B precondition for column-type drift.

        V038 必含 Guard B 偵測欄位型別漂移。
        """
        sql = _read_sql(V038_PATH)
        assert "V038 Guard B" in sql, "V038 missing Guard B header"
        assert "data_type" in sql, "V038 Guard B must query information_schema.columns.data_type"
        assert "RAISE EXCEPTION" in sql, "V038 Guard B must RAISE on type drift"


class TestV039Backfill:
    """V039: backfill NULL → 'real_outcome' for 3 allowlisted sources +
    governance_audit_log row.

    V039：對 3 個白名單 source 將 NULL 回填為 'real_outcome'，並寫審計列。
    """

    ALLOWLIST_SOURCES = ("dream_engine", "ml_shadow", "opportunity_tracker")

    def test_updates_only_allowlisted_sources(self):
        """V039 UPDATE WHERE clause must target the 3 P0-T7 allowlisted sources.

        V039 UPDATE WHERE 必命中 3 個 P0-T7 白名單 source。
        """
        sql = _strip_sql_comments(_read_sql(V039_PATH))

        # The UPDATE statement and the WHERE-IN list / UPDATE 與 WHERE-IN 列表
        update_match = re.search(
            r"UPDATE\s+learning\.mlde_shadow_recommendations[^;]+",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert update_match, "V039 must contain UPDATE learning.mlde_shadow_recommendations"

        update_block = update_match.group(0)

        # SET evidence_source_tier = 'real_outcome'
        set_pattern = re.compile(
            r"SET\s+evidence_source_tier\s*=\s*'real_outcome'",
            re.IGNORECASE,
        )
        assert set_pattern.search(update_block), (
            "V039 UPDATE must SET evidence_source_tier = 'real_outcome'."
        )

        # WHERE evidence_source_tier IS NULL — idempotent guarantee
        # WHERE evidence_source_tier IS NULL — 幂等保證
        idempotent_pattern = re.compile(
            r"WHERE[^;]*evidence_source_tier\s+IS\s+NULL",
            re.IGNORECASE | re.DOTALL,
        )
        assert idempotent_pattern.search(update_block), (
            "V039 WHERE must filter evidence_source_tier IS NULL for idempotency."
        )

        # All 3 allowlist sources must be referenced in the WHERE IN list.
        # 3 個白名單 source 必須在 WHERE IN 列表中。
        for src in self.ALLOWLIST_SOURCES:
            assert f"'{src}'" in update_block, (
                f"V039 UPDATE WHERE must include source '{src}'."
            )

    def test_does_not_force_update_existing_non_null(self):
        """V039 must not include UPDATE without the IS NULL guard (would
        force-overwrite future producers' tier values).

        V039 不可包含未含 IS NULL 守衛的 UPDATE（會強蓋未來 producer 的 tier 值）。
        """
        sql = _strip_sql_comments(_read_sql(V039_PATH))

        # Find every UPDATE statement; each must contain the IS NULL filter.
        # 找每個 UPDATE 語句；每個必含 IS NULL 過濾。
        for update_block in re.findall(
            r"UPDATE\s+learning\.mlde_shadow_recommendations[^;]+",
            sql,
            re.IGNORECASE | re.DOTALL,
        ):
            assert re.search(
                r"WHERE[^;]*evidence_source_tier\s+IS\s+NULL",
                update_block,
                re.IGNORECASE | re.DOTALL,
            ), (
                "Every V039 UPDATE on mlde_shadow_recommendations must filter "
                "`evidence_source_tier IS NULL`; otherwise it could clobber "
                "non-NULL rows. Found UPDATE without guard:\n"
                + update_block[:200]
            )

    def test_writes_governance_audit_log_row(self):
        """V039 must INSERT one audit row into learning.governance_audit_log.

        V039 必對 learning.governance_audit_log 寫一筆審計列。
        """
        sql = _strip_sql_comments(_read_sql(V039_PATH))

        insert_pattern = re.compile(
            r"INSERT\s+INTO\s+learning\.governance_audit_log",
            re.IGNORECASE,
        )
        assert insert_pattern.search(sql), (
            "V039 must INSERT a row into learning.governance_audit_log "
            "for backfill batch tracking."
        )

        # Audit decided_by must mark this as migration:V039
        # Audit decided_by 須標記為 migration:V039
        assert "'migration:V039'" in sql, (
            "V039 audit row decided_by must be 'migration:V039' for traceability."
        )

    def test_v039_has_guards(self):
        """V039 must verify V038 ran (column exists) and V035 ran (audit table).

        V039 必驗 V038 已 run（欄位存在）+ V035 已 run（審計表存在）。
        """
        sql = _read_sql(V039_PATH)
        assert "V039 Guard B" in sql, "V039 missing Guard B for V038 precondition"
        assert "must run before V039" in sql, (
            "V039 must communicate dependency on prior migrations clearly."
        )


class TestV040Finalize:
    """V040: ALTER COLUMN SET NOT NULL + ADD CHECK constraint.

    V040：ALTER COLUMN SET NOT NULL + 加 CHECK 約束。
    """

    EXPECTED_TIER_VALUES = (
        "real_outcome",
        "calibrated_replay",
        "synthetic_replay",
        "counterfactual_replay",
    )

    def test_alters_column_not_null(self):
        """V040 must ALTER COLUMN evidence_source_tier SET NOT NULL.

        V040 必對 evidence_source_tier 加 SET NOT NULL。
        """
        sql = _strip_sql_comments(_read_sql(V040_PATH))

        pattern = re.compile(
            r"ALTER\s+TABLE\s+learning\.mlde_shadow_recommendations[\s\S]*?"
            r"ALTER\s+COLUMN\s+evidence_source_tier\s+SET\s+NOT\s+NULL",
            re.IGNORECASE,
        )
        assert pattern.search(sql), (
            "V040 must ALTER COLUMN evidence_source_tier SET NOT NULL."
        )

    def test_adds_check_constraint_with_4_value_allowlist(self):
        """V040 must ADD CONSTRAINT chk_evidence_source_tier with 4 enum values.

        V040 必加 chk_evidence_source_tier 約束，含 4 個 enum 值。
        """
        sql = _strip_sql_comments(_read_sql(V040_PATH))

        # ADD CONSTRAINT chk_evidence_source_tier
        constraint_pattern = re.compile(
            r"ADD\s+CONSTRAINT\s+chk_evidence_source_tier\s+CHECK",
            re.IGNORECASE,
        )
        assert constraint_pattern.search(sql), (
            "V040 must ADD CONSTRAINT chk_evidence_source_tier ... CHECK (...)"
        )

        # All 4 allowlist values must appear inside the CHECK clause body.
        # 4 個白名單值都必須出現在 CHECK 子句內。
        for tier in self.EXPECTED_TIER_VALUES:
            assert f"'{tier}'" in sql, (
                f"V040 CHECK constraint must include allowlist value '{tier}'."
            )

    def test_v040_check_rejects_invalid_tier_values(self):
        """The CHECK constraint clause must use IN (... 4 values ...) such that
        any value outside the allowlist would be rejected on INSERT.

        CHECK 子句必用 IN (... 4 values ...) 形式，外部值 INSERT 必被拒絕。

        We don't run a real INSERT; instead we structurally verify:
          1. CHECK uses `IN (...)` syntax
          2. The IN list contains exactly the 4 allowlist values
          3. No other tier-like literals appear inside the IN list
        靜態驗：CHECK 用 IN 語法 / IN 列表恰含 4 值 / IN 列表中無其他 tier 文字常量。
        """
        sql = _strip_sql_comments(_read_sql(V040_PATH))

        # Extract the body of the CHECK constraint we added
        # 提取我們加的 CHECK 約束主體
        m = re.search(
            r"ADD\s+CONSTRAINT\s+chk_evidence_source_tier\s+CHECK\s*\(([\s\S]+?)\)\s*;",
            sql,
            re.IGNORECASE,
        )
        assert m, "Cannot locate chk_evidence_source_tier CHECK body"
        check_body = m.group(1)

        # Must use IN syntax / 必用 IN 語法
        assert re.search(r"\bIN\b", check_body, re.IGNORECASE), (
            "CHECK body must use IN (...) syntax for enum allowlist."
        )

        # All quoted string literals inside the body
        # 主體內所有引號字串常量
        literals = set(re.findall(r"'([^']+)'", check_body))
        assert literals == set(self.EXPECTED_TIER_VALUES), (
            f"CHECK IN list must contain exactly {set(self.EXPECTED_TIER_VALUES)}, "
            f"got {literals}. Extra literal would silently allow invalid tier values."
        )

    def test_v040_has_null_precheck_guard(self):
        """V040 must Guard B precheck: if any NULL row remains, RAISE before ALTER.

        V040 必有 Guard B 前置：若仍有 NULL row，ALTER 前 RAISE。
        """
        sql = _read_sql(V040_PATH)
        assert "V040 Guard B" in sql, "V040 missing Guard B header"
        assert "evidence_source_tier IS NULL" in sql, (
            "V040 Guard B must count NULL rows before SET NOT NULL."
        )
        assert "V039 backfill must complete" in sql, (
            "V040 must reference V039 dependency in Guard B error message."
        )


class TestHealthcheck:
    """V040 healthcheck SQL helper / V040 健康檢查 SQL 輔助腳本。"""

    def test_healthcheck_file_exists(self):
        """V040_healthcheck.sql must exist alongside V040.

        V040_healthcheck.sql 必與 V040 同層存在。
        """
        assert V040_HEALTHCHECK_PATH.exists(), (
            f"V040 healthcheck missing at {V040_HEALTHCHECK_PATH}"
        )

    def test_healthcheck_has_3_probes(self):
        """V040_healthcheck.sql must contain 3 SELECT probes:
        null count / tier distribution / constraint state.

        V040_healthcheck.sql 必含 3 個 SELECT 探針：null 計數 / tier 分佈 / 約束狀態。
        """
        sql = _strip_sql_comments(_read_sql(V040_HEALTHCHECK_PATH))

        # Probe 1: NULL count / 探針 1：NULL 計數
        assert re.search(
            r"COUNT\(\*\)[\s\S]+?WHERE\s+evidence_source_tier\s+IS\s+NULL",
            sql,
            re.IGNORECASE,
        ), "Healthcheck must include NULL count probe"

        # Probe 2: distribution / 探針 2：分佈
        assert re.search(
            r"GROUP\s+BY",
            sql,
            re.IGNORECASE,
        ), "Healthcheck must include GROUP BY distribution probe"

        # Probe 3: constraint state / 探針 3：約束狀態
        assert "is_nullable" in sql.lower(), (
            "Healthcheck must include is_nullable column-state probe"
        )
        assert "chk_evidence_source_tier" in sql, (
            "Healthcheck must reference chk_evidence_source_tier constraint name"
        )

    def test_healthcheck_is_read_only(self):
        """V040_healthcheck.sql must contain no INSERT / UPDATE / DELETE / ALTER /
        CREATE / DROP — read-only by design.

        V040_healthcheck.sql 不可含 INSERT/UPDATE/DELETE/ALTER/CREATE/DROP — 設計純讀。
        """
        sql_no_comments = _strip_sql_comments(_read_sql(V040_HEALTHCHECK_PATH))
        forbidden = ("INSERT", "UPDATE", "DELETE", "ALTER ", "CREATE ", "DROP ")
        sql_upper = sql_no_comments.upper()
        for kw in forbidden:
            assert kw not in sql_upper, (
                f"Healthcheck must be read-only; found forbidden keyword: {kw!r}"
            )


class TestBilingualComments:
    """All 3 migrations + healthcheck must contain bilingual headers per
    CLAUDE.md §七 + bilingual-comment-style skill.

    所有 3 個 migration + healthcheck 必含中英對照表頭（CLAUDE.md §七 + skill 規範）。
    """

    @pytest.mark.parametrize(
        "path",
        [V038_PATH, V039_PATH, V040_PATH, V040_HEALTHCHECK_PATH],
    )
    def test_bilingual_header(self, path: Path):
        """Each file's header must contain both 'Purpose' (EN) and '目的' (中文).

        每個檔案表頭必含 'Purpose'（英）與 '目的'（中）。
        """
        head = _read_sql(path)[:1500]
        assert "Purpose" in head, f"{path.name} header missing English 'Purpose'"
        assert "目的" in head, f"{path.name} header missing Chinese '目的'"
