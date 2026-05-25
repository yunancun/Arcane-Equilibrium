"""AC-19 ALT bucket cron pytest 套件。

MODULE_NOTE:
  模塊用途：為 helper_scripts/cron/ac19_alt_bucket_jsonl_writer.py 釘 contract:
    - Wilson 95% lower-bound 公式（3 case：邊界 fills=4/n=6、ALT 9/35、零樣本）。
    - 3 級 verdict 閾值（large_cap 60% / alt 30%/20% / INSUFFICIENT_DATA）。
    - bucket 分類（BTC/ETH → large_cap，其它 → alt — SQL 那層分；本套件驗 verdict
      handler 接受兩 bucket 字串）。
    - day_index 計算（window 起 5/19 / day-7 / 過期 14 / 邊界）。
    - CSV 解析 + JSONL append + sanity drift 偵測。
  依賴：pytest / pathlib / json / math（stdlib only）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


# 把 cron/ 加入 sys.path 讓 `import ac19_alt_bucket_jsonl_writer` 可走。
HELPER_CRON = Path(__file__).resolve().parents[1]
if str(HELPER_CRON) not in sys.path:
    sys.path.insert(0, str(HELPER_CRON))

import ac19_alt_bucket_jsonl_writer as writer  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Wilson lower bound formula — 3 case + edge
# ─────────────────────────────────────────────────────────────────────────


class TestWilsonLower95:
    """Wilson 95% CI lower bound 公式 contract。"""

    def test_large_cap_6_of_4_per_sop_baseline(self) -> None:
        """W1-G SOP §1 baseline: large_cap n=6, fills=4 → Wilson lower 大致 30%。

        為什麼這 case：SOP §1 empirical 直接驗（驗 SQL 與 Python 雙端對齊）。
        """
        lower = writer.wilson_lower_95(fills=4, attempts=6)
        # SOP §2.1 提到 Wilson lower ~29.9%；canonical formula 算 30.0%（差異
        # 在 SOP doc 計算 rounding；接受 [29.0, 31.0] 容差）。
        assert 29.0 <= lower <= 31.5, f"large_cap 4/6 Wilson lower={lower}"

    def test_alt_35_of_9_per_sop_baseline(self) -> None:
        """W1-G SOP §1 baseline: alt n=35, fills=9 → Wilson lower ~14.1%。

        SOP §2.1 文字明示 14.1%；canonical formula 必對齊 ±0.5pp。
        """
        lower = writer.wilson_lower_95(fills=9, attempts=35)
        assert 13.5 <= lower <= 14.7, f"alt 9/35 Wilson lower={lower}"

    def test_zero_attempts_returns_zero(self) -> None:
        """attempts=0 不可拋；回 0.0（INSUFFICIENT_DATA 由 caller 判定）。"""
        assert writer.wilson_lower_95(fills=0, attempts=0) == 0.0

    def test_perfect_fills_lower_below_100(self) -> None:
        """p_hat=1.0 時 Wilson lower 仍 < 100（公式對 fills=attempts case 收斂）。"""
        lower = writer.wilson_lower_95(fills=10, attempts=10)
        assert 60.0 <= lower < 100.0, f"perfect 10/10 Wilson lower={lower}"

    def test_invalid_fills_raises(self) -> None:
        """fills > attempts fail-loud。"""
        with pytest.raises(ValueError):
            writer.wilson_lower_95(fills=10, attempts=5)


class TestWilsonUpper95:
    """Wilson 95% CI upper bound 公式。"""

    def test_alt_35_of_9_upper(self) -> None:
        """W1-G SOP §6.2 example: wilson_upper_pct=42.0；驗 ±2pp。"""
        upper = writer.wilson_upper_95(fills=9, attempts=35)
        assert 40.0 <= upper <= 44.0, f"alt 9/35 Wilson upper={upper}"

    def test_zero_attempts(self) -> None:
        assert writer.wilson_upper_95(fills=0, attempts=0) == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Verdict 3 級閾值 — per W1-G SOP §5
# ─────────────────────────────────────────────────────────────────────────


class TestClassifyVerdict:
    """3 級 verdict (PASS / MARGINAL / FAIL / INSUFFICIENT_DATA)。"""

    @pytest.mark.parametrize(
        "wilson_lower, attempts, expected",
        [
            (60.1, 6, "PASS"),
            (60.0, 6, "PASS"),  # 邊界 inclusive
            (59.9, 6, "FAIL"),
            (66.7, 100, "PASS"),
        ],
    )
    def test_large_cap_threshold(
        self, wilson_lower: float, attempts: int, expected: str
    ) -> None:
        assert (
            writer.classify_verdict("large_cap", wilson_lower, attempts) == expected
        )

    @pytest.mark.parametrize(
        "wilson_lower, attempts, expected",
        [
            (30.1, 100, "PASS"),
            (30.0, 100, "PASS"),  # 邊界 inclusive
            (29.9, 100, "MARGINAL"),
            (20.1, 100, "MARGINAL"),
            (20.0, 100, "MARGINAL"),  # 邊界 inclusive
            (19.9, 100, "FAIL"),
            (14.1, 35, "FAIL"),  # SOP §1 day-7 baseline → FAIL
            (0.0, 0, "INSUFFICIENT_DATA"),  # n=0 直接 INSUFFICIENT
        ],
    )
    def test_alt_threshold(
        self, wilson_lower: float, attempts: int, expected: str
    ) -> None:
        assert writer.classify_verdict("alt", wilson_lower, attempts) == expected

    def test_unknown_bucket_raises(self) -> None:
        with pytest.raises(ValueError):
            writer.classify_verdict("foo", 50.0, 10)


# ─────────────────────────────────────────────────────────────────────────
# bucket 分類（SQL 那層分；本套件確認 verdict handler 接受兩個值）
# ─────────────────────────────────────────────────────────────────────────


class TestBucketHandling:
    """Bucket 字串分類 — SQL 那層分 (BTCUSDT/ETHUSDT → large_cap，其它 → alt)，
    本測試確認 Python 端不誤判，且 fail-loud 對未知字串。"""

    def test_large_cap_accepted(self) -> None:
        # large_cap bucket Wilson lower 80% → PASS（≥60%）。
        assert writer.classify_verdict("large_cap", 80.0, 10) == "PASS"

    def test_alt_accepted(self) -> None:
        assert writer.classify_verdict("alt", 35.0, 50) == "PASS"

    def test_unknown_bucket_fail_loud(self) -> None:
        """defensive：SQL 端 bucket 永遠是 'large_cap' 或 'alt'，若漂移寫到 'mid_cap'
        必須 fail-loud（防靜默 swallow）。"""
        with pytest.raises(ValueError):
            writer.classify_verdict("mid_cap", 50.0, 10)


# ─────────────────────────────────────────────────────────────────────────
# day_index 計算 + window 邊界
# ─────────────────────────────────────────────────────────────────────────


class TestDayIndex:
    """day_index 計算 — window start = 2026-05-19 (day 1)。"""

    def test_day_1(self) -> None:
        ts = datetime(2026, 5, 19, 8, 0, 0, tzinfo=timezone.utc)
        assert writer.compute_day_index(ts) == 1

    def test_day_7(self) -> None:
        # W1-G SOP §1 day-7 = 2026-05-25。
        ts = datetime(2026, 5, 25, 14, 35, 0, tzinfo=timezone.utc)
        assert writer.compute_day_index(ts) == 7

    def test_day_8_cron_target(self) -> None:
        """W2-F NEW QA-2 deadline target：5/26 cron 必須產 day_index=8 row。"""
        ts = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)
        assert writer.compute_day_index(ts) == 8

    def test_day_14_window_end(self) -> None:
        # window end 6/2 = day 15（exclusive end → cron wrapper 用 day>14 idempotent skip）。
        ts = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
        assert writer.compute_day_index(ts) == 14

    def test_naive_datetime_treated_as_utc(self) -> None:
        """tz-naive 不誤 silently 漂移；視為 UTC。"""
        ts = datetime(2026, 5, 26, 8, 0, 0)
        assert writer.compute_day_index(ts) == 8


# ─────────────────────────────────────────────────────────────────────────
# CSV 解析
# ─────────────────────────────────────────────────────────────────────────


class TestLoadPsqlCsv:
    """psql --csv 輸出解析。"""

    def test_parse_two_rows(self) -> None:
        csv_text = (
            "bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict\n"
            "alt,35,9,23,25.7,14.1,42.0,FAIL\n"
            "large_cap,6,4,1,66.7,30.0,90.3,PASS\n"
        )
        rows = writer.load_psql_csv(csv_text)
        assert len(rows) == 2
        assert rows[0]["bucket"] == "alt"
        assert rows[0]["attempts"] == 35
        assert rows[0]["fills"] == 9
        assert rows[0]["timeouts"] == 23
        assert rows[0]["fill_rate_pct"] == pytest.approx(25.7)
        assert rows[0]["wilson_lower_pct"] == pytest.approx(14.1)
        assert rows[0]["verdict"] == "FAIL"

    def test_skip_psql_trailing_summary(self) -> None:
        """psql 在 --csv 下不會印 trailing '(2 rows)'，但 defensive 容忍。"""
        csv_text = (
            "bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict\n"
            "alt,35,9,23,25.7,14.1,42.0,FAIL\n"
            "(1 row)\n"
        )
        rows = writer.load_psql_csv(csv_text)
        assert len(rows) == 1
        assert rows[0]["bucket"] == "alt"

    def test_empty_csv_returns_empty(self) -> None:
        rows = writer.load_psql_csv("bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict\n")
        assert rows == []

    def test_malformed_row_raises(self) -> None:
        csv_text = (
            "bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict\n"
            "alt,not_a_number,9,23,25.7,14.1,42.0,FAIL\n"
        )
        with pytest.raises(ValueError):
            writer.load_psql_csv(csv_text)


# ─────────────────────────────────────────────────────────────────────────
# JSONL append + sanity drift
# ─────────────────────────────────────────────────────────────────────────


class TestBuildJsonlRecords:
    """JSONL row 構造 + Python 重算 Wilson 與 SQL 對比。"""

    def test_alt_day_7_baseline(self) -> None:
        rows = [
            {
                "bucket": "alt",
                "attempts": 35,
                "fills": 9,
                "timeouts": 23,
                "fill_rate_pct": 25.7,
                "wilson_lower_pct": 14.1,  # SOP §1 baseline
                "wilson_upper_pct": 42.0,
                "verdict": "FAIL",
            },
        ]
        records = writer.build_jsonl_records(rows, "2026-05-25T14:35:00Z")
        assert len(records) == 1
        rec = records[0]
        assert rec["bucket"] == "alt"
        assert rec["day_index"] == 7
        assert rec["window_start"] == "2026-05-19T00:00:00Z"
        assert rec["window_end"] == "2026-06-02T00:00:00Z"
        assert rec["attempts"] == 35
        assert rec["fills"] == 9
        # Python 重算 Wilson lower 應 ≈ SQL 報的 14.1（容差 1pp）。
        assert 13.0 <= rec["wilson_lower_pct"] <= 15.0
        # 14.1 < 20% → FAIL（per ALT bucket gate）。
        assert rec["verdict"] == "FAIL"
        # 無 sanity drift（Python 與 SQL 一致）。
        assert "sanity_drift_pct" not in rec

    def test_sanity_drift_logged_when_sql_lies(self) -> None:
        """SQL 故意報錯 wilson_lower：Python 重算發現 drift → sanity_drift_pct 寫入。"""
        rows = [
            {
                "bucket": "alt",
                "attempts": 35,
                "fills": 9,
                "timeouts": 23,
                "fill_rate_pct": 25.7,
                "wilson_lower_pct": 99.0,  # 明顯錯
                "wilson_upper_pct": 42.0,
                "verdict": "PASS",  # 也錯
            },
        ]
        records = writer.build_jsonl_records(rows, "2026-05-25T14:35:00Z")
        rec = records[0]
        # Python 重算 ≈ 14.1，但 SQL 報 99.0 → drift > 1pp。
        assert "sanity_drift_pct" in rec
        assert rec["sanity_drift_pct"] > 1.0
        # Python 重算 verdict 取代 SQL 錯的 verdict。
        assert rec["verdict"] == "FAIL"

    def test_zero_attempts_insufficient_data(self) -> None:
        rows = [
            {
                "bucket": "large_cap",
                "attempts": 0,
                "fills": 0,
                "timeouts": 0,
                "fill_rate_pct": 0.0,
                "wilson_lower_pct": 0.0,
                "wilson_upper_pct": 0.0,
                "verdict": "INSUFFICIENT_DATA",
            },
        ]
        records = writer.build_jsonl_records(rows, "2026-05-26T08:00:00Z")
        assert records[0]["verdict"] == "INSUFFICIENT_DATA"


class TestAppendJsonl:
    """JSONL append 行為。"""

    def test_append_creates_file_and_appends(self, tmp_path: Path) -> None:
        output = tmp_path / "ac19_alt_bucket_14d_summary.jsonl"
        records = [
            {"bucket": "alt", "day_index": 8, "verdict": "FAIL"},
            {"bucket": "large_cap", "day_index": 8, "verdict": "PASS"},
        ]
        writer.append_jsonl(output, records)
        assert output.exists()
        lines = output.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["bucket"] == "alt"
        assert json.loads(lines[1])["bucket"] == "large_cap"

    def test_append_preserves_existing(self, tmp_path: Path) -> None:
        output = tmp_path / "summary.jsonl"
        output.write_text(json.dumps({"bucket": "alt", "day_index": 7}) + "\n", encoding="utf-8")
        records = [{"bucket": "alt", "day_index": 8, "verdict": "FAIL"}]
        writer.append_jsonl(output, records)
        lines = output.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["day_index"] == 7
        assert json.loads(lines[1])["day_index"] == 8


# ─────────────────────────────────────────────────────────────────────────
# Aggregate exit code
# ─────────────────────────────────────────────────────────────────────────


class TestAggregateExitCode:
    """Cron exit code 聚合（0/1/2）。"""

    def test_all_pass_returns_0(self) -> None:
        records = [
            {"verdict": "PASS"},
            {"verdict": "PASS"},
        ]
        assert writer.aggregate_exit_code(records) == 0

    def test_marginal_returns_1(self) -> None:
        records = [
            {"verdict": "PASS"},
            {"verdict": "MARGINAL"},
        ]
        assert writer.aggregate_exit_code(records) == 1

    def test_fail_returns_2(self) -> None:
        records = [
            {"verdict": "FAIL"},
            {"verdict": "PASS"},
        ]
        assert writer.aggregate_exit_code(records) == 2

    def test_fail_takes_precedence_over_marginal(self) -> None:
        records = [
            {"verdict": "MARGINAL"},
            {"verdict": "FAIL"},
        ]
        assert writer.aggregate_exit_code(records) == 2

    def test_insufficient_data_does_not_escalate(self) -> None:
        records = [
            {"verdict": "INSUFFICIENT_DATA"},
            {"verdict": "INSUFFICIENT_DATA"},
        ]
        assert writer.aggregate_exit_code(records) == 0


# ─────────────────────────────────────────────────────────────────────────
# End-to-end CLI (dry-run, no PG / no JSONL write)
# ─────────────────────────────────────────────────────────────────────────


class TestCliDryRun:
    """CLI dry-run smoke：CSV 輸入 + ts 注入 → stdout JSONL + 不寫 output。"""

    def test_dry_run_does_not_write_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        csv_file = tmp_path / "input.csv"
        csv_file.write_text(
            "bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict\n"
            "alt,35,9,23,25.7,14.1,42.0,FAIL\n"
            "large_cap,6,4,1,66.7,30.0,90.3,FAIL\n",  # SOP §2.1 large_cap 6/4 Wilson lower ~29.9% → FAIL
            encoding="utf-8",
        )
        output = tmp_path / "summary.jsonl"
        rc = writer.main(
            [
                "--input",
                str(csv_file),
                "--ts",
                "2026-05-25T14:35:00Z",
                "--output",
                str(output),
                "--dry-run",
            ]
        )
        # ALT FAIL → rc=2。
        assert rc == 2
        # Output file 不應寫入。
        assert not output.exists()
        captured = capsys.readouterr()
        assert "alt" in captured.out
        assert "large_cap" in captured.out

    def test_missing_input_returns_2(self, tmp_path: Path) -> None:
        rc = writer.main(
            [
                "--input",
                str(tmp_path / "does_not_exist.csv"),
                "--ts",
                "2026-05-25T14:35:00Z",
                "--output",
                str(tmp_path / "summary.jsonl"),
            ]
        )
        assert rc == 2
