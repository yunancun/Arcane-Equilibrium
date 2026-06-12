"""l2_memory_distill 三件套測試（CLI 殼 + cron wrapper + installer）。

MODULE_NOTE
模塊用途：釘死 L2 記憶蒸餾 cron 三件套（PA 2026-06-11 spec §11/§13.1）的
  load-bearing 行為，全部 Mac 可跑（0 真 PG / 0 真 LLM / 0 crontab 寫入）：
    1. CLI 殼 flag gate：flag-OFF ⇒ exit 0 且零 DB/零 pipeline/零 LLM 呼叫
       （E2 審查點 3：flag 檢查先於任何 psycopg2 connect）。
    2. memory_distiller 未落地（兩線並行）⇒ ImportError ⇒ exit 0。
    3. 游標窗口數學（pending_days 純函數）+「成功才推進」失敗語義
       （含 PipelineDisabledError 同 MRO 鏡像：disabled ≠ 成功）。
    4. day stats 環形檔（[88] 語義死亡軸資料源）：有界 / 只記成功日 /
       fail-soft 不反殺管線。
    5. wrapper 鎖防重入 / stale lock 自清 / heartbeat / 日誌輪轉（hermetic：
       OPENCLAW_BASE_DIR 指向 tmp 內 stub script）。
    6. wrapper / installer bash -n 語法守門。
依賴：pytest + 標準庫 subprocess；bash（雙平台都有）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

_CRON_DIR = Path(__file__).resolve().parent
if str(_CRON_DIR) not in sys.path:
    sys.path.insert(0, str(_CRON_DIR))

import l2_memory_distill as mod  # noqa: E402

WRAPPER = _CRON_DIR / "l2_memory_distill_cron.sh"
INSTALLER = _CRON_DIR / "install_l2_memory_distill_cron.sh"


# ─────────────────────────── 純函數：游標窗口數學 ───────────────────────────


class TestPendingDays:
    TODAY = date(2026, 6, 11)

    def test_no_cursor_first_run_only_yesterday(self):
        # 首跑保守：只補昨日（歷史回放歸 seed CLI，避免首 enable 即爆量）。
        assert mod.pending_days(None, self.TODAY) == [date(2026, 6, 10)]

    def test_cursor_at_yesterday_nothing_pending(self):
        assert mod.pending_days(date(2026, 6, 10), self.TODAY) == []

    def test_cursor_ahead_clock_skew_nothing_pending(self):
        # 游標在未來（時鐘漂移/手工誤寫）不得產生負窗口。
        assert mod.pending_days(date(2026, 6, 11), self.TODAY) == []
        assert mod.pending_days(date(2026, 7, 1), self.TODAY) == []

    def test_three_day_gap(self):
        days = mod.pending_days(date(2026, 6, 7), self.TODAY)
        assert days == [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]

    def test_lookback_capped_at_seven_days(self):
        # 長期停擺後最多回看 7 日（spec R5），窗口以昨日收尾。
        days = mod.pending_days(date(2026, 5, 1), self.TODAY)
        assert len(days) == mod.LOOKBACK_CAP_DAYS == 7
        assert days[0] == date(2026, 6, 4)
        assert days[-1] == date(2026, 6, 10)


# ─────────────────────────── 游標檔讀寫 ───────────────────────────


class TestCursorFile:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "cron_state" / "cursor.json"
        mod.write_cursor(p, date(2026, 6, 9))
        assert mod.read_cursor(p) == date(2026, 6, 9)

    def test_missing_returns_none(self, tmp_path):
        assert mod.read_cursor(tmp_path / "nope.json") is None

    def test_corrupt_json_returns_none(self, tmp_path):
        p = tmp_path / "cursor.json"
        p.write_text("{not json", encoding="utf-8")
        assert mod.read_cursor(p) is None

    def test_bad_date_returns_none(self, tmp_path):
        p = tmp_path / "cursor.json"
        p.write_text(json.dumps({"last_success_utc_date": "not-a-date"}))
        assert mod.read_cursor(p) is None


# ─────────────────────────── day stats 環形檔（[88] 語義死亡軸資料源）───────────────────────────


class TestDayStats:
    def test_entry_extracts_fields_from_day_results(self):
        stats = {
            "status": "ok",
            "day_results": [
                {"ok": True, "stored": 3, "materials_l2": 7, "dropped": 2}
            ],
        }
        entry = mod._day_stats_entry(date(2026, 6, 10), stats)
        assert entry == {
            "utc_date": "2026-06-10",
            "stored": 3,
            "materials_l2": 7,
            "dropped": 2,
        }

    @pytest.mark.parametrize(
        "bad",
        [
            None,
            "not a dict",
            {},
            {"day_results": "not a list"},
            {"day_results": []},
            {"day_results": [{"stored": "NaN", "materials_l2": None}]},
        ],
    )
    def test_entry_defensive_defaults_on_malformed(self, bad):
        # 防禦性取值：run_daily 回傳形狀異常 ⇒ 全 0（觀測軸絕不拋）。
        entry = mod._day_stats_entry(date(2026, 6, 10), bad)
        assert entry["utc_date"] == "2026-06-10"
        assert (entry["stored"], entry["materials_l2"], entry["dropped"]) == (0, 0, 0)

    def test_append_bounds_ring_to_max_entries(self, tmp_path):
        p = tmp_path / "stats.json"
        for i in range(mod.STATS_MAX_ENTRIES + 5):
            mod.append_day_stats(p, {"utc_date": f"d{i}", "stored": i})
        days = json.loads(p.read_text(encoding="utf-8"))["days"]
        assert len(days) == mod.STATS_MAX_ENTRIES, "環形必須有界（防無限增長）"
        assert days[0]["utc_date"] == "d5"
        assert days[-1]["utc_date"] == f"d{mod.STATS_MAX_ENTRIES + 4}"

    def test_append_corrupt_file_rebuilds_without_raise(self, tmp_path):
        # 觀測資料可丟：壞檔直接重建（游標檔才是補跑紀律的唯一憑據）。
        p = tmp_path / "stats.json"
        p.write_text("{broken", encoding="utf-8")
        mod.append_day_stats(p, {"utc_date": "2026-06-10", "stored": 1})
        days = json.loads(p.read_text(encoding="utf-8"))["days"]
        assert days == [{"utc_date": "2026-06-10", "stored": 1}]

    def test_append_write_failure_fail_soft_no_raise(self, tmp_path, capsys):
        # fail-soft 硬邊界：觀測寫入失敗不得反殺管線本體（不拋、WARN log）。
        blocker = tmp_path / "blocked"
        blocker.write_text("file not dir", encoding="utf-8")
        mod.append_day_stats(blocker / "stats.json", {"utc_date": "x"})
        assert "WARN" in capsys.readouterr().out


# ─────────────────────────── CLI 殼：flag gate / 接線語義 ───────────────────────────


def _forbid(name):
    def _boom(*_a, **_k):
        raise AssertionError(f"{name} 不應在此路徑被呼叫")

    return _boom


class FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture()
def clean_env(monkeypatch):
    for var in (
        mod.FLAG_ENV,
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "OPENCLAW_DATA_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestCliFlagGate:
    def test_flag_unset_exit0_zero_side_effects(self, clean_env):
        # E2 審查點 3：flag-OFF ⇒ 連 pipeline import / DB connect / LLM 解析都不發生。
        clean_env.setattr(mod, "_load_pipeline", _forbid("_load_pipeline"))
        clean_env.setattr(mod, "_connect_db", _forbid("_connect_db"))
        clean_env.setattr(mod, "_resolve_llm", _forbid("_resolve_llm"))
        assert mod.main([]) == mod.EXIT_OK

    def test_flag_zero_exit0(self, clean_env):
        clean_env.setenv(mod.FLAG_ENV, "0")
        clean_env.setattr(mod, "_load_pipeline", _forbid("_load_pipeline"))
        clean_env.setattr(mod, "_connect_db", _forbid("_connect_db"))
        assert mod.main([]) == mod.EXIT_OK

    def test_module_not_landed_exit0_before_db(self, clean_env):
        # 兩線並行：E1-A package 未落地 ⇒ ImportError ⇒ log + exit 0，且不碰 DB。
        clean_env.setenv(mod.FLAG_ENV, "1")
        clean_env.setattr(
            mod, "_load_pipeline", _forbid("ImportError")
        )

        def _raise_import(*_a, **_k):
            raise ImportError("No module named 'learning_engine.memory_distiller'")

        clean_env.setattr(mod, "_load_pipeline", _raise_import)
        clean_env.setattr(mod, "_connect_db", _forbid("_connect_db"))
        clean_env.setattr(mod, "_resolve_llm", _forbid("_resolve_llm"))
        assert mod.main([]) == mod.EXIT_OK

    def test_db_creds_missing_config_error(self, clean_env, tmp_path):
        # flag=1 + pipeline 在 + 無 POSTGRES_* ⇒ fail-closed exit 2（不猜隱式 DSN）。
        clean_env.setenv(mod.FLAG_ENV, "1")
        clean_env.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=_forbid("run_daily"))
        )
        clean_env.setattr(mod, "_resolve_llm", _forbid("_resolve_llm"))
        rc = mod.main(["--data-dir", str(tmp_path)])
        assert rc == mod.EXIT_CONFIG_ERROR


class TestCliPipelineLoop:
    @pytest.fixture()
    def wired(self, clean_env, tmp_path):
        clean_env.setenv(mod.FLAG_ENV, "1")
        calls: list[date] = []

        def run_daily(conn, llm, *, target_date):
            calls.append(target_date)
            return {"stored": 1, "day": target_date.isoformat()}

        conn = FakeConn()
        clean_env.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=run_daily)
        )
        clean_env.setattr(mod, "_connect_db", lambda: conn)
        clean_env.setattr(mod, "_resolve_llm", lambda: object())
        clean_env.setattr(mod, "_utc_today", lambda: date(2026, 6, 11))
        return SimpleNamespace(
            calls=calls, conn=conn, data_dir=tmp_path, monkeypatch=clean_env
        )

    def _cursor_file(self, data_dir: Path) -> Path:
        return data_dir / mod.CURSOR_REL_PATH

    def test_success_advances_cursor_per_day(self, wired):
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 8))
        rc = mod.main(["--data-dir", str(wired.data_dir)])
        assert rc == mod.EXIT_OK
        assert wired.calls == [date(2026, 6, 9), date(2026, 6, 10)]
        assert mod.read_cursor(self._cursor_file(wired.data_dir)) == date(2026, 6, 10)
        assert wired.conn.closed is True

    def test_failure_day_stops_and_keeps_cursor(self, wired):
        # 「成功才推進」：第二日失敗 ⇒ 游標停在第一日，exit 1，下輪補跑。
        def flaky(conn, llm, *, target_date):
            if target_date == date(2026, 6, 10):
                raise RuntimeError("ollama down")
            return {}

        wired.monkeypatch.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=flaky)
        )
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 8))
        rc = mod.main(["--data-dir", str(wired.data_dir)])
        assert rc == mod.EXIT_RUNTIME_FAIL
        assert mod.read_cursor(self._cursor_file(wired.data_dir)) == date(2026, 6, 9)

    def test_interface_mismatch_typeerror_exit1(self, wired, capsys):
        # 兩線合流接縫：簽名不匹配 ⇒ 清晰 log + exit 1（不推進游標）。
        def legacy_signature(conn, llm):  # 缺 target_date
            return {}

        wired.monkeypatch.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=legacy_signature)
        )
        rc = mod.main(["--data-dir", str(wired.data_dir)])
        assert rc == mod.EXIT_RUNTIME_FAIL
        out = capsys.readouterr().out
        assert "簽名不匹配" in out
        assert mod.read_cursor(self._cursor_file(wired.data_dir)) is None

    def test_nothing_pending_exit0_without_db(self, wired):
        wired.monkeypatch.setattr(mod, "_connect_db", _forbid("_connect_db"))
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 10))
        assert mod.main(["--data-dir", str(wired.data_dir)]) == mod.EXIT_OK
        assert wired.calls == []

    def _stats_file(self, data_dir: Path) -> Path:
        return data_dir / mod.STATS_REL_PATH

    def test_success_writes_day_stats_ring_for_88(self, wired):
        # 成功日落 per-day summary（[88] 語義死亡軸資料源）：逐日 entry +
        # stored/materials_l2 取自 run_daily 回傳 day_results[0]。
        def run_daily(conn, llm, *, target_date):
            return {
                "status": "ok",
                "day_results": [
                    {"ok": True, "stored": 2, "materials_l2": 5, "dropped": 1}
                ],
            }

        wired.monkeypatch.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=run_daily)
        )
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 8))
        assert mod.main(["--data-dir", str(wired.data_dir)]) == mod.EXIT_OK
        days = json.loads(self._stats_file(wired.data_dir).read_text(encoding="utf-8"))[
            "days"
        ]
        assert [d["utc_date"] for d in days] == ["2026-06-09", "2026-06-10"]
        assert all(d["stored"] == 2 and d["materials_l2"] == 5 for d in days)

    def test_failed_day_writes_no_stats(self, wired):
        # stats 只記成功日（[88] 的同步判準 = 最新 entry == 游標日；失敗日寫入
        # 會讓 stats 跑在游標前面、被 fail-soft 判 stale 而失效）。
        def always_fail(conn, llm, *, target_date):
            raise RuntimeError("ollama down")

        wired.monkeypatch.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=always_fail)
        )
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 9))
        assert mod.main(["--data-dir", str(wired.data_dir)]) == mod.EXIT_RUNTIME_FAIL
        assert not self._stats_file(wired.data_dir).exists()

    def test_pipeline_disabled_error_keeps_cursor_discipline(self, wired):
        # E2-A LOW-1 修復輪核對：pipeline target_date 模式 flag-OFF 改 raise
        # PipelineDisabledError（RuntimeError 子類）——CLI 通用例外臂必須把它當
        # 失敗日處置：exit 1、游標不推進、stats 不寫（disabled ≠ 成功）。
        # 本檔 mock pipeline（接縫由 M1 側測試鎖），以同 MRO 的本地子類鏡像。
        class PipelineDisabledError(RuntimeError):
            pass

        def disabled(conn, llm, *, target_date):
            raise PipelineDisabledError("OPENCLAW_L2_MEMORY_PIPELINE != 1")

        wired.monkeypatch.setattr(
            mod, "_load_pipeline", lambda: SimpleNamespace(run_daily=disabled)
        )
        mod.write_cursor(self._cursor_file(wired.data_dir), date(2026, 6, 9))
        assert mod.main(["--data-dir", str(wired.data_dir)]) == mod.EXIT_RUNTIME_FAIL
        assert mod.read_cursor(self._cursor_file(wired.data_dir)) == date(2026, 6, 9)
        assert not self._stats_file(wired.data_dir).exists()


# ─────────────────────────── wrapper / installer（bash）───────────────────────────


def test_wrapper_bash_syntax_ok():
    assert subprocess.run(["bash", "-n", str(WRAPPER)]).returncode == 0


def test_installer_bash_syntax_ok():
    assert subprocess.run(["bash", "-n", str(INSTALLER)]).returncode == 0


def _make_stub_base(tmp_path: Path) -> tuple[Path, Path]:
    """假 BASE：stub l2_memory_distill.py 寫 marker（hermetic，不跑真殼）。"""
    base = tmp_path / "base"
    cron_dir = base / "helper_scripts" / "cron"
    cron_dir.mkdir(parents=True)
    marker = cron_dir / "ran.marker"
    stub = cron_dir / "l2_memory_distill.py"
    stub.write_text(
        "import sys, pathlib\n"
        "pathlib.Path(__file__).resolve().parent.joinpath('ran.marker')"
        ".write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return base, marker


def _wrapper_env(tmp_path: Path, base: Path) -> dict[str, str]:
    data = tmp_path / "data"
    return {
        **os.environ,
        "OPENCLAW_BASE_DIR": str(base),
        "OPENCLAW_DATA_DIR": str(data),
        "OPENCLAW_SECRETS_ROOT": str(tmp_path / "no_secrets"),
        "OPENCLAW_PYTHON_BIN": sys.executable,
    }


def _run_wrapper(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(WRAPPER)], env=env, capture_output=True, text=True, timeout=60
    )


class TestWrapperLockAndLog:
    def test_runs_releases_lock_heartbeat_logs(self, tmp_path):
        base, marker = _make_stub_base(tmp_path)
        env = _wrapper_env(tmp_path, base)
        proc = _run_wrapper(env)
        assert proc.returncode == 0
        assert marker.exists(), "stub 應被執行"
        data = Path(env["OPENCLAW_DATA_DIR"])
        assert (data / "cron_heartbeat" / "l2_memory_distill.last_fire").exists()
        assert not (data / "locks" / "l2_memory_distill_cron.lock.d").exists(), (
            "trap 應釋放鎖"
        )
        log_text = (data / "logs" / "l2_memory_distill_cron.log").read_text()
        assert "l2_memory_distill start" in log_text
        assert "end rc=0" in log_text

    def test_lock_held_skips_run(self, tmp_path):
        # 防重入：fresh lock 在 ⇒ SKIP、stub 不執行、既有鎖不被動（非本進程持有）。
        base, marker = _make_stub_base(tmp_path)
        env = _wrapper_env(tmp_path, base)
        lock_dir = Path(env["OPENCLAW_DATA_DIR"]) / "locks" / "l2_memory_distill_cron.lock.d"
        lock_dir.mkdir(parents=True)
        proc = _run_wrapper(env)
        assert proc.returncode == 0  # fail-soft
        assert not marker.exists(), "鎖被持有時不得執行 stub"
        log_text = (
            Path(env["OPENCLAW_DATA_DIR"]) / "logs" / "l2_memory_distill_cron.log"
        ).read_text()
        assert "SKIP" in log_text
        assert lock_dir.exists(), "他持鎖不可被本輪清掉（非 stale）"

    def test_stale_lock_cleared_then_runs(self, tmp_path):
        # stale 自清：mtime > 180min 的殭屍鎖 ⇒ 清掉並正常執行。
        base, marker = _make_stub_base(tmp_path)
        env = _wrapper_env(tmp_path, base)
        lock_dir = Path(env["OPENCLAW_DATA_DIR"]) / "locks" / "l2_memory_distill_cron.lock.d"
        lock_dir.mkdir(parents=True)
        stale = time.time() - 4 * 3600
        os.utime(lock_dir, (stale, stale))
        proc = _run_wrapper(env)
        assert proc.returncode == 0
        assert marker.exists(), "stale 鎖清除後應執行"
        log_text = (
            Path(env["OPENCLAW_DATA_DIR"]) / "logs" / "l2_memory_distill_cron.log"
        ).read_text()
        assert "stale lock" in log_text

    def test_log_rotation_over_5mb(self, tmp_path):
        base, _marker = _make_stub_base(tmp_path)
        env = _wrapper_env(tmp_path, base)
        log_dir = Path(env["OPENCLAW_DATA_DIR"]) / "logs"
        log_dir.mkdir(parents=True)
        log = log_dir / "l2_memory_distill_cron.log"
        log.write_bytes(b"x" * (5242880 + 1))
        proc = _run_wrapper(env)
        assert proc.returncode == 0
        assert (log_dir / "l2_memory_distill_cron.log.1").exists(), "超限應輪轉到 .1"
        assert log.stat().st_size < 5242880, "輪轉後新 log 應從小開始"

    def test_flag_passthrough_default_zero(self, tmp_path):
        # wrapper 默認導出 flag=0（inert）；stub 收到的 env 即 CLI 殼所見。
        base, marker = _make_stub_base(tmp_path)
        stub = base / "helper_scripts" / "cron" / "l2_memory_distill.py"
        stub.write_text(
            "import os, pathlib\n"
            "pathlib.Path(__file__).resolve().parent.joinpath('ran.marker')"
            ".write_text(os.environ.get('OPENCLAW_L2_MEMORY_PIPELINE', 'MISSING'))\n",
            encoding="utf-8",
        )
        env = _wrapper_env(tmp_path, base)
        env.pop("OPENCLAW_L2_MEMORY_PIPELINE", None)
        proc = _run_wrapper(env)
        assert proc.returncode == 0
        assert marker.read_text() == "0"
