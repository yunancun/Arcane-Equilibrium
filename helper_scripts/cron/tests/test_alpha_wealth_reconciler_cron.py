"""ml_training_maintenance.py alpha_wealth_reconciler job 接線測試（P4 E1-C）。

證行為中性硬約束（鏡像 test_residual_preflight_cron.py）：
  - alpha_wealth_reconciler 不在 DEFAULT_JOBS（預設 cron 不 dispatch）。
  - 在 VALID_JOBS / OPTIONAL_JOBS（--jobs 可顯式選入）。
  - flag off → _run_alpha_wealth_reconciler 回 skipped（非 error），零連線零寫入。
  - flag on + 無 DSN → skipped no_database_url（不嘗試連線）。
  - _run_job dispatcher 路由正確。

pure-core：不連 PG（flag off / 無 DSN 在開連線前就 skipped）。
"""

from __future__ import annotations

import argparse
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


def test_alpha_wealth_reconciler_not_in_default_jobs():
    assert "alpha_wealth_reconciler" not in m.DEFAULT_JOBS
    args = m._parse_args([])
    assert "alpha_wealth_reconciler" not in args.jobs


def test_alpha_wealth_reconciler_in_valid_jobs_optin():
    assert "alpha_wealth_reconciler" in m.VALID_JOBS
    assert "alpha_wealth_reconciler" in m.OPTIONAL_JOBS
    args = m._parse_args(["--jobs", "alpha_wealth_reconciler"])
    assert args.jobs == ["alpha_wealth_reconciler"]


def test_run_skipped_when_flag_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCLAW_ALPHA_WEALTH_RECONCILER", raising=False)
    ns = argparse.Namespace(dry_run=False)
    result = m._run_alpha_wealth_reconciler("postgresql://fake", ns)
    assert result.status == "skipped"
    assert "flag_off" in str(result.detail.get("reason", ""))
    assert result.error == ""


def test_run_skipped_when_no_dsn(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCLAW_ALPHA_WEALTH_RECONCILER", "1")
    ns = argparse.Namespace(dry_run=False)
    result = m._run_alpha_wealth_reconciler(None, ns)
    assert result.status == "skipped"
    assert result.error == "no_database_url"


def test_dispatcher_routes_to_runner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCLAW_ALPHA_WEALTH_RECONCILER", raising=False)
    ns = argparse.Namespace(dry_run=True)
    result = m._run_job("alpha_wealth_reconciler", None, ns)
    # flag off → skipped 證明已路由到本 job 的 wrapper（unknown_job 會是 error）。
    assert result.job == "alpha_wealth_reconciler"
    assert result.status == "skipped"
