"""[9] check_model_registry_freshness — shadow-staleness blind-spot 回歸測試。

MODULE_NOTE (中): 鎖死 P2-MIT（2026-06-14）修復——production slot=0 時不再
一律 PASS「expected」，而是探測 shadow cohort：
  * 無 shadow row → PASS（真空表 Phase 1a/2）
  * shadow 但新鮮（≤30d）→ PASS（dormant-as-designed，非誤報）
  * shadow 且過齡（>30d）→ WARN（過期 shadow surface，非靜默 PASS）
  * shadow 永不升 FAIL（shadow 本就不晉升，缺晉升非故障）
production 路徑（已有 production slot）行為不變，僅補一條斷言。

fake cursor 鏡像真實上游：依序回應 (1) to_regclass 存在性、(2) production
聚合查詢、(3) shadow cohort 查詢；以 SQL 內容路由，與 _Cursor 既有範式一致。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helper_scripts.db.passive_wait_healthcheck.checks_ipc_edge import (
    check_model_registry_freshness,
)


class _Cursor:
    """以 SQL 子字串路由的 fake cursor；按真實查詢順序回應。

    為何按 SQL 內容路由而非呼叫次序：production slot=0 路徑才會發出 shadow
    查詢，slot>0 路徑不發；以內容路由讓同一 fake 同時覆蓋兩條分支。
    """

    def __init__(
        self,
        *,
        exists: bool = True,
        production_row: tuple | None = None,
        shadow_row: tuple | None = None,
        shadow_raises: bool = False,
    ) -> None:
        self._exists = exists
        # 預設：無 production slot、無 shadow row（真空 Phase 1a/2）。
        self._production_row = production_row or (0, None, None)
        self._shadow_row = shadow_row or (0, None)
        self._shadow_raises = shadow_raises
        self._pending: tuple | None = None
        self.queries: list[str] = []

    def execute(self, sql: str) -> None:
        self.queries.append(sql)
        if "to_regclass" in sql:
            self._pending = (self._exists,)
        elif "canary_status = 'production'" in sql:
            self._pending = self._production_row
        elif "canary_status = 'shadow'" in sql:
            if self._shadow_raises:
                raise RuntimeError("shadow query boom")
            self._pending = self._shadow_row
        else:  # pragma: no cover - guards against an unrouted query
            raise AssertionError(f"unrouted SQL: {sql[:80]}")

    def fetchone(self):
        return self._pending


def _utc_days_ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# --- shadow blind-spot 三態 ---------------------------------------------


def test_no_production_no_shadow_is_pass_empty() -> None:
    """真空表（無 production、無 shadow）→ PASS「expected」（Phase 1a/2）。"""
    cur = _Cursor(production_row=(0, None, None), shadow_row=(0, None))
    status, msg = check_model_registry_freshness(cur)
    assert status == "PASS"
    assert "shadow rows=0" in msg
    assert "expected in" in msg


def test_shadow_fresh_is_pass_not_silent_dormant() -> None:
    """shadow 但新鮮（≤30d）→ PASS，明示 dormant-as-designed。"""
    cur = _Cursor(
        production_row=(0, None, None),
        shadow_row=(3, _utc_days_ago(5)),
    )
    status, msg = check_model_registry_freshness(cur)
    assert status == "PASS"
    assert "shadow rows=3" in msg
    assert "shadow but fresh" in msg


def test_shadow_stale_is_warn_not_silent_pass() -> None:
    """shadow 且過齡（>30d）→ WARN（surface，非靜默 PASS）。"""
    cur = _Cursor(
        production_row=(0, None, None),
        shadow_row=(2, _utc_days_ago(45)),
    )
    status, msg = check_model_registry_freshness(cur)
    assert status == "WARN"
    assert "shadow pool stale" in msg
    assert "45d ago" in msg


def test_shadow_stale_never_escalates_to_fail() -> None:
    """即使 shadow 極度過齡（>60d）仍為 WARN，永不 FAIL（shadow 不晉升非故障）。"""
    cur = _Cursor(
        production_row=(0, None, None),
        shadow_row=(1, _utc_days_ago(120)),
    )
    status, _ = check_model_registry_freshness(cur)
    assert status == "WARN"


def test_shadow_at_boundary_30d_is_still_pass() -> None:
    """剛好 30d（含）內仍為 PASS；>30d 才 WARN（邊界精度）。"""
    # 29.5d → days==29 → PASS（未超 30d 窗口）。
    cur = _Cursor(
        production_row=(0, None, None),
        shadow_row=(1, _utc_days_ago(29.5)),
    )
    status, _ = check_model_registry_freshness(cur)
    assert status == "PASS"


def test_shadow_query_failure_fails_soft_to_pass() -> None:
    """shadow 查詢丟例外 → fail-soft 退回 PASS「expected」（不誤 FAIL/WARN）。"""
    cur = _Cursor(production_row=(0, None, None), shadow_raises=True)
    status, msg = check_model_registry_freshness(cur)
    assert status == "PASS"
    assert "shadow rows=0" in msg


# --- mutation bite：證測試真會抓到「回退舊盲區」-------------------------


def test_mutation_bite_old_blanket_pass_would_miss_stale_shadow() -> None:
    """mutation bite：模擬舊碼盲區——production slot=0 一律 PASS、不查 shadow。

    舊行為對 stale shadow 也回 PASS；本斷言證新碼對同一輸入回 WARN。
    若有人把 shadow fallback 改回 blanket PASS，本測試立即紅。
    """
    cur = _Cursor(
        production_row=(0, None, None),
        shadow_row=(2, _utc_days_ago(90)),
    )
    status, _ = check_model_registry_freshness(cur)
    # 舊碼會是 PASS；新碼必須 WARN。
    assert status == "WARN", "stale shadow must surface, not blanket PASS"
    # 驗證確實發出了 shadow 探測查詢（盲區修復的接線證據）。
    assert any("canary_status = 'shadow'" in q for q in cur.queries)


# --- production 路徑零回歸（slot>0 不發 shadow 查詢）---------------------


def test_production_slot_present_skips_shadow_probe() -> None:
    """有 production slot 時走原路徑、不發 shadow 查詢（零回歸）。"""
    from datetime import date

    fresh = date.today()
    cur = _Cursor(production_row=(4, fresh, fresh))
    status, msg = check_model_registry_freshness(cur)
    assert status == "PASS"
    assert "production slots=4" in msg
    assert not any("canary_status = 'shadow'" in q for q in cur.queries)


def test_table_missing_still_fails() -> None:
    """表不存在 → FAIL（V023 未 apply），既有硬失敗不退化。"""
    cur = _Cursor(exists=False)
    status, msg = check_model_registry_freshness(cur)
    assert status == "FAIL"
    assert "V023" in msg
