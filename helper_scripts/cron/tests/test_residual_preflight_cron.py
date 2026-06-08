"""ml_training_maintenance.py residual_preflight job 接線測試（PART 4 Gap A）。

證行為中性硬約束：
  - residual_preflight 不在 DEFAULT_JOBS（預設 cron 不 dispatch）。
  - 在 VALID_JOBS（--jobs 可顯式選入）。
  - flags off → _run_residual_preflight 回 skipped（非 error），零 orchestrator 寫入。
  - _run_job dispatcher 把 residual_preflight 路由到 _run_residual_preflight。

pure-core：不連 PG（flags off 在開連線前就 skipped）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pytest


# repo 路徑：對齊 ml_training_maintenance._ensure_repo_imports（base_dir + program_code）。
_CRON_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _CRON_DIR.parents[1]  # helper_scripts/cron/tests → srv
for _p in (str(_CRON_DIR), str(_REPO_ROOT), str(_REPO_ROOT / "program_code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ml_training_maintenance as m  # noqa: E402


def test_residual_preflight_not_in_default_jobs():
    assert "residual_preflight" not in m.DEFAULT_JOBS
    # 預設 args.jobs 不含 residual_preflight → 預設 cron 不 dispatch。
    args = m._parse_args([])
    assert "residual_preflight" not in args.jobs


def test_residual_preflight_in_valid_jobs_optin():
    assert "residual_preflight" in m.VALID_JOBS
    assert "residual_preflight" in m.OPTIONAL_JOBS
    # --jobs 可顯式選入。
    args = m._parse_args(["--jobs", "residual_preflight"])
    assert args.jobs == ["residual_preflight"]


def test_bogus_job_still_rejected():
    with pytest.raises(SystemExit):
        m._parse_args(["--jobs", "bogus_job"])


def test_run_residual_preflight_skipped_when_stage0r_flag_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT", raising=False)
    monkeypatch.setenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", "1")
    ns = argparse.Namespace(dry_run=False)
    result = m._run_residual_preflight("postgresql://fake", ns)
    assert result.status == "skipped"
    assert "flag_off" in str(result.detail.get("reason", ""))
    assert result.error == ""


def test_run_residual_preflight_skipped_when_producer_flag_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT", "1")
    monkeypatch.delenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", raising=False)
    ns = argparse.Namespace(dry_run=False)
    result = m._run_residual_preflight("postgresql://fake", ns)
    assert result.status == "skipped"
    assert "OPENCLAW_RESIDUAL_ALPHA_PRODUCER" in str(result.detail.get("reason", ""))


def test_run_residual_preflight_skipped_no_dsn(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT", "1")
    monkeypatch.setenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", "1")
    ns = argparse.Namespace(dry_run=False)
    result = m._run_residual_preflight(None, ns)
    assert result.status == "skipped"
    assert result.error == "no_database_url"


def test_run_residual_preflight_skipped_no_window(monkeypatch: pytest.MonkeyPatch):
    # flags + DSN 都有但無時間窗 env → skipped（PIT：窗是 operator 承諾，不自猜）。
    monkeypatch.setenv("OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT", "1")
    monkeypatch.setenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", "1")
    monkeypatch.delenv("OPENCLAW_RESIDUAL_PREFLIGHT_OOS_START", raising=False)
    monkeypatch.delenv("OPENCLAW_RESIDUAL_PREFLIGHT_DATA_END", raising=False)
    monkeypatch.delenv("OPENCLAW_RESIDUAL_PREFLIGHT_SINCE", raising=False)
    ns = argparse.Namespace(dry_run=False)
    result = m._run_residual_preflight("postgresql://fake", ns)
    assert result.status == "skipped"
    assert result.detail.get("reason") == "oos_window_not_configured"


def test_run_job_dispatches_residual_preflight(monkeypatch: pytest.MonkeyPatch):
    # _run_job 把 residual_preflight 路由到 _run_residual_preflight。
    called = {"n": 0}

    def _fake(dsn, args):
        called["n"] += 1
        return m.JobResult("residual_preflight", "skipped", 0, {"reason": "stub"})

    monkeypatch.setattr(m, "_run_residual_preflight", _fake)
    ns = argparse.Namespace(dry_run=False)
    result = m._run_job("residual_preflight", "dsn", ns)
    assert called["n"] == 1
    assert result.job == "residual_preflight"


def test_parse_iso_env_helper(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X_ISO", "2026-01-02T03:04:05+00:00")
    dt = m._parse_iso_env("X_ISO")
    assert dt is not None and dt.year == 2026 and dt.tzinfo is not None
    # naive → 當 UTC。
    monkeypatch.setenv("X_ISO_NAIVE", "2026-01-02T03:04:05")
    dt2 = m._parse_iso_env("X_ISO_NAIVE")
    assert dt2 is not None and dt2.tzinfo is not None
    # 缺/非法 → None。
    monkeypatch.delenv("X_MISSING", raising=False)
    assert m._parse_iso_env("X_MISSING") is None
    monkeypatch.setenv("X_BAD", "not-a-date")
    assert m._parse_iso_env("X_BAD") is None
