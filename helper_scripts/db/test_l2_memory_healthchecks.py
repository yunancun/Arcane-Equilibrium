"""[88][89] L2 記憶層 dormant 哨兵測試（FakeCursor，0 真 PG）。

MODULE_NOTE
模塊用途：釘死 checks_l2_memory（PA 2026-06-11 spec §12）的 dormant 語義：
    1. flag-OFF（部署默認態）⇒ PASS 且 msg 帶 SKIP——絕不 FAIL/WARN
       （dormant 不造噪音，PM 拍板 SKIP 非 FAIL）。
    2. flag-ON：[88] 表缺/游標缺/游標壞/滯後>3 日 ⇒ WARN；健康 ⇒ PASS。
    3. flag-ON：[88] 語義死亡軸（MIT F-4 / E2 LOW-3 修復輪）：連續 3 個有
       l2 材料的已處理日 stored=0 ⇒ WARN；stats 檔缺/壞/與游標不同步 ⇒
       fail-soft 不誤 WARN；lag WARN 優先。
    4. flag-ON：[89] meta 表缺 ⇒ WARN；meta 未初始化 ⇒ PASS（合法過渡態）；
       provider/model/dims 漂移 ⇒ WARN；吻合 ⇒ PASS。
依賴：pytest + 標準庫（mirror test_mlde_healthchecks 同族 FakeCursor 範式）。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

_DB_DIR = Path(__file__).resolve().parent
if str(_DB_DIR) not in sys.path:
    sys.path.insert(0, str(_DB_DIR))

from passive_wait_healthcheck import checks_l2_memory as mod  # noqa: E402


class FakeCursor:
    def __init__(self, *, table_exists=True, row_count=5, meta_row=None):
        self.table_exists = table_exists
        self.row_count = row_count
        self.meta_row = meta_row
        self.connection = SimpleNamespace(rollback=lambda: None)
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = sql

    def fetchone(self):
        if "to_regclass" in self._last_sql:
            return (self.table_exists,)
        if "count(*)" in self._last_sql:
            return (self.row_count,)
        if "provider, model, dims" in self._last_sql:
            return self.meta_row
        return None


@pytest.fixture()
def flags_off(monkeypatch):
    monkeypatch.delenv(mod.PIPELINE_FLAG_ENV, raising=False)
    monkeypatch.delenv(mod.BACKFILL_FLAG_ENV, raising=False)
    monkeypatch.delenv(mod.EMBED_MODEL_ENV, raising=False)
    return monkeypatch


def _write_cursor_file(tmp_path: Path, day: str) -> None:
    p = tmp_path / "cron_state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "l2_memory_distill_cursor.json").write_text(
        json.dumps({"last_success_utc_date": day}), encoding="utf-8"
    )


def _write_stats_file(tmp_path: Path, entries: list[dict]) -> None:
    """CLI day_stats 環形檔（與 cron CLI append_day_stats 同形 {"days": [...]}）。"""
    p = tmp_path / "cron_state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "l2_memory_distill_day_stats.json").write_text(
        json.dumps({"days": entries}), encoding="utf-8"
    )


def _dead_day(day: str) -> dict:
    """「有 l2 材料但 0 寫入」日（語義死亡證據單元）。"""
    return {"utc_date": day, "stored": 0, "materials_l2": 5, "dropped": 5}


class TestCheck88PipelineFreshness:
    def test_flag_off_pass_skip_not_fail(self, flags_off):
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"
        assert "SKIP" in msg

    def test_flag_on_table_absent_warn(self, flags_off):
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        status, msg = mod.check_88_l2_memory_pipeline_freshness(
            FakeCursor(table_exists=False)
        )
        assert status == "WARN"
        assert "V139" in msg

    def test_flag_on_cursor_file_missing_warn(self, flags_off, tmp_path):
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "WARN"
        assert "cursor file missing" in msg

    def test_flag_on_cursor_corrupt_warn(self, flags_off, tmp_path):
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        p = tmp_path / "cron_state"
        p.mkdir(parents=True)
        (p / "l2_memory_distill_cursor.json").write_text("{bad", encoding="utf-8")
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "WARN"
        assert "unreadable" in msg

    def test_flag_on_healthy_lag1_pass(self, flags_off, tmp_path):
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        flags_off.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        _write_cursor_file(tmp_path, "2026-06-10")
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor(row_count=42))
        assert status == "PASS"
        assert "lag_days=1" in msg
        assert "rows=42" in msg

    def test_flag_on_stalled_lag_over_3_warn(self, flags_off, tmp_path):
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        flags_off.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        _write_cursor_file(tmp_path, "2026-06-06")
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "WARN"
        assert "lag_days=5" in msg

    def test_flag_on_lag_exactly_3_pass(self, flags_off, tmp_path):
        # 邊界：spec 寫「滯後 >3 日」⇒ 恰 3 日仍 PASS。
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        flags_off.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        _write_cursor_file(tmp_path, "2026-06-08")
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"


class TestCheck88SemanticDeath:
    """語義死亡軸（MIT F-4 / E2 LOW-3 修復輪）：游標健康 ≠ 記憶在累積。

    資料源 = cron CLI 寫的 per-day summary 環形檔（游標旁同目錄）；
    判準 = 連續 SEMANTIC_DEATH_CONSECUTIVE_DAYS 個「materials_l2>0 且
    stored=0」的已處理日。觀測檔任何不可信狀態 ⇒ fail-soft 不誤 WARN。
    """

    def _healthy_cursor(self, flags_off, tmp_path):
        # 共用前置：flag=1、游標=昨日（lag 1 健康），讓語義死亡軸成為判定主軸。
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        flags_off.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        _write_cursor_file(tmp_path, "2026-06-10")

    def test_three_consecutive_dead_days_warn(self, flags_off, tmp_path):
        self._healthy_cursor(flags_off, tmp_path)
        _write_stats_file(
            tmp_path,
            [_dead_day("2026-06-08"), _dead_day("2026-06-09"), _dead_day("2026-06-10")],
        )
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "WARN"
        assert "semantic death" in msg

    def test_two_dead_days_below_threshold_pass(self, flags_off, tmp_path):
        self._healthy_cursor(flags_off, tmp_path)
        _write_stats_file(tmp_path, [_dead_day("2026-06-09"), _dead_day("2026-06-10")])
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_noop_day_breaks_streak_pass(self, flags_off, tmp_path):
        # materials_l2=0（無料可蒸）不是死亡證據——必須切斷連續性。
        self._healthy_cursor(flags_off, tmp_path)
        noop = {"utc_date": "2026-06-09", "stored": 0, "materials_l2": 0, "dropped": 0}
        _write_stats_file(
            tmp_path, [_dead_day("2026-06-08"), noop, _dead_day("2026-06-10")]
        )
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_stored_day_breaks_streak_pass(self, flags_off, tmp_path):
        self._healthy_cursor(flags_off, tmp_path)
        alive = {"utc_date": "2026-06-09", "stored": 2, "materials_l2": 4, "dropped": 0}
        _write_stats_file(
            tmp_path, [_dead_day("2026-06-08"), alive, _dead_day("2026-06-10")]
        )
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_only_last_n_entries_considered(self, flags_off, tmp_path):
        # 歷史更早的死亡日不算——只看最近 N 連續窗（早年死過、近期復活 ⇒ PASS）。
        self._healthy_cursor(flags_off, tmp_path)
        alive = {"utc_date": "2026-06-09", "stored": 1, "materials_l2": 3, "dropped": 0}
        _write_stats_file(
            tmp_path,
            [
                _dead_day("2026-06-06"),
                _dead_day("2026-06-07"),
                _dead_day("2026-06-08"),
                alive,
                _dead_day("2026-06-10"),
            ],
        )
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_stats_file_missing_fail_soft_pass(self, flags_off, tmp_path):
        # 觀測檔缺（CLI 未升級/自管模式無 stats）⇒ 不據以告警（fail-soft）。
        self._healthy_cursor(flags_off, tmp_path)
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_stats_corrupt_fail_soft_pass(self, flags_off, tmp_path):
        self._healthy_cursor(flags_off, tmp_path)
        p = tmp_path / "cron_state" / "l2_memory_distill_day_stats.json"
        p.write_text("{broken json", encoding="utf-8")
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_stats_stale_not_synced_with_cursor_pass(self, flags_off, tmp_path):
        # 最新 stats entry ≠ 游標日（pipeline 自管模式推游標、stats 由 CLI 獨家寫）
        # ⇒ stats 不可信，不據以告警。
        self._healthy_cursor(flags_off, tmp_path)
        _write_stats_file(
            tmp_path,
            [_dead_day("2026-06-06"), _dead_day("2026-06-07"), _dead_day("2026-06-08")],
        )
        status, _msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "PASS"

    def test_lag_warn_priority_over_semantic_death(self, flags_off, tmp_path):
        # 游標停擺（lag>3）與語義死亡並存 ⇒ 報 stalled（更上游的死因優先）。
        flags_off.setenv(mod.PIPELINE_FLAG_ENV, "1")
        flags_off.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
        flags_off.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        _write_cursor_file(tmp_path, "2026-06-05")
        _write_stats_file(
            tmp_path,
            [_dead_day("2026-06-03"), _dead_day("2026-06-04"), _dead_day("2026-06-05")],
        )
        status, msg = mod.check_88_l2_memory_pipeline_freshness(FakeCursor())
        assert status == "WARN"
        assert "stalled" in msg
        assert "semantic death" not in msg


class TestCheck89EmbeddingDrift:
    def test_flag_off_pass_skip(self, flags_off):
        status, msg = mod.check_89_l2_memory_embedding_drift(FakeCursor())
        assert status == "PASS"
        assert "SKIP" in msg

    def test_flag_on_meta_table_absent_warn(self, flags_off):
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        status, msg = mod.check_89_l2_memory_embedding_drift(
            FakeCursor(table_exists=False)
        )
        assert status == "WARN"
        assert "V139" in msg

    def test_flag_on_meta_uninitialized_pass(self, flags_off):
        # 首輪 backfill 前 meta 未建是合法過渡態（spec：僅「不符」才 WARN）。
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        status, msg = mod.check_89_l2_memory_embedding_drift(FakeCursor(meta_row=None))
        assert status == "PASS"
        assert "not initialized" in msg

    def test_flag_on_model_drift_warn(self, flags_off):
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        status, msg = mod.check_89_l2_memory_embedding_drift(
            FakeCursor(meta_row=("ollama", "old-model", 1024))
        )
        assert status == "WARN"
        assert "drift" in msg

    def test_flag_on_dims_drift_warn(self, flags_off):
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        status, _msg = mod.check_89_l2_memory_embedding_drift(
            FakeCursor(meta_row=("ollama", "bge-m3", 768))
        )
        assert status == "WARN"

    def test_flag_on_match_pass(self, flags_off):
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        status, msg = mod.check_89_l2_memory_embedding_drift(
            FakeCursor(meta_row=("ollama", "bge-m3", 1024))
        )
        assert status == "PASS"
        assert "matches config" in msg

    def test_env_model_override_respected(self, flags_off):
        # config 側 model 由 OPENCLAW_L2_MEMORY_EMBED_MODEL 決定（spec §10）。
        flags_off.setenv(mod.BACKFILL_FLAG_ENV, "1")
        flags_off.setenv(mod.EMBED_MODEL_ENV, "custom-embed")
        status, _msg = mod.check_89_l2_memory_embedding_drift(
            FakeCursor(meta_row=("ollama", "custom-embed", 1024))
        )
        assert status == "PASS"


def test_runner_wires_88_89():
    """接線釘子：runner 真的 import 並呼叫兩個 check（防 silent 死碼）。"""
    runner_src = (_DB_DIR / "passive_wait_healthcheck" / "runner.py").read_text(
        encoding="utf-8"
    )
    assert "check_88_l2_memory_pipeline_freshness(cur)" in runner_src
    assert "check_89_l2_memory_embedding_drift(cur)" in runner_src
    assert '"[88] l2_memory_pipeline_freshness"' in runner_src
    assert '"[89] l2_memory_embedding_drift"' in runner_src
