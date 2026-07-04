"""checks_crontab_governance [92][93] focused tests（P0-2④）。

MODULE_NOTE:
  以 monkeypatch 隔離 subprocess（crontab -l / journalctl / git）與檔案系統,
  驗兩哨兵的判定分支:match=PASS、drift>24h=FAIL(required)、空 live=FAIL、
  REPLACE>manifest=FAIL、journal 不可用=PASS-skip。純函數不觸 runtime。
"""

from __future__ import annotations

import time
from pathlib import Path

import helper_scripts.db.passive_wait_healthcheck.checks_crontab_governance as cg


def _set_common(monkeypatch, tmp_path: Path, head="abc1234"):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path / "repo"))
    monkeypatch.setattr(cg, "_head_sha", lambda: head)


def _write_template(tmp_path: Path, body: str) -> None:
    tmpl = tmp_path / "repo" / "helper_scripts" / "cron"
    tmpl.mkdir(parents=True, exist_ok=True)
    (tmpl / "crontab.trade-core.template").write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# [92] crontab_matches_repo_render
# ---------------------------------------------------------------------------

def test_92_match_pass(monkeypatch, tmp_path):
    _set_common(monkeypatch, tmp_path)
    _write_template(tmp_path, "1 * * * * /bin/true OPENCLAW_EXPECTED_SOURCE_HEAD={{HEAD}}\n")
    monkeypatch.setattr(cg, "_live_crontab",
                        lambda: "1 * * * * /bin/true OPENCLAW_EXPECTED_SOURCE_HEAD=abc1234")
    sev, msg = cg.check_92_crontab_matches_repo_render()
    assert sev == "PASS", msg
    assert "live == repo render" in msg


def test_92_empty_live_is_fail_closed(monkeypatch, tmp_path):
    # 即使非 required,live 空(屠殺後狀態)一律 FAIL。
    _set_common(monkeypatch, tmp_path)
    _write_template(tmp_path, "1 * * * * /bin/true\n")
    monkeypatch.setattr(cg, "_live_crontab", lambda: None)
    sev, msg = cg.check_92_crontab_matches_repo_render()
    assert sev == "FAIL", msg
    assert "屠殺" in msg


def test_92_drift_over_24h_required_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    _set_common(monkeypatch, tmp_path)
    _write_template(tmp_path, "1 * * * * /bin/true\n")
    monkeypatch.setattr(cg, "_live_crontab", lambda: "9 * * * * /bin/false")
    # manifest 存在但 25h 前 → drift 超窗。
    mut = tmp_path / "crontab_mutations" / "old"
    mut.mkdir(parents=True)
    mf = mut / "manifest.json"
    mf.write_text("{}", encoding="utf-8")
    old = time.time() - 25 * 3600
    import os
    os.utime(mf, (old, old))
    sev, msg = cg.check_92_crontab_matches_repo_render()
    assert sev == "FAIL", msg
    assert "> 24h" in msg


def test_92_drift_no_manifest_treated_over_window(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    _set_common(monkeypatch, tmp_path)
    _write_template(tmp_path, "1 * * * * /bin/true\n")
    monkeypatch.setattr(cg, "_live_crontab", lambda: "9 * * * * /bin/false")
    sev, msg = cg.check_92_crontab_matches_repo_render()
    assert sev == "FAIL", msg
    assert "無任何 manifest" in msg


def test_92_drift_within_window_warn(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    _set_common(monkeypatch, tmp_path)
    _write_template(tmp_path, "1 * * * * /bin/true\n")
    monkeypatch.setattr(cg, "_live_crontab", lambda: "9 * * * * /bin/false")
    # manifest 1h 前 → drift < 24h → WARN（即使 required）。
    mut = tmp_path / "crontab_mutations" / "recent"
    mut.mkdir(parents=True)
    (mut / "manifest.json").write_text("{}", encoding="utf-8")
    sev, msg = cg.check_92_crontab_matches_repo_render()
    assert sev == "WARN", msg
    assert "容忍窗" in msg


# ---------------------------------------------------------------------------
# [93] crontab_replace_has_manifest
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, rc, out):
        self.returncode = rc
        self.stdout = out


def test_93_replace_without_manifest_required_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    # journal 有 2 個 REPLACE,manifest 目錄空 → 2 > 0 → FAIL。
    monkeypatch.setattr(cg.subprocess, "run",
                        lambda *a, **k: _FakeProc(0, "crontab REPLACE\ncrontab REPLACE\n"))
    sev, msg = cg.check_93_crontab_replace_has_manifest()
    assert sev == "FAIL", msg
    assert "REPLACE=2" in msg and "manifest=0" in msg


def test_93_replace_with_manifest_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cg.subprocess, "run",
                        lambda *a, **k: _FakeProc(0, "crontab REPLACE\n"))
    mut = tmp_path / "crontab_mutations" / "now"
    mut.mkdir(parents=True)
    (mut / "manifest.json").write_text("{}", encoding="utf-8")
    sev, msg = cg.check_93_crontab_replace_has_manifest()
    assert sev == "PASS", msg


def test_93_no_replace_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cg.subprocess, "run", lambda *a, **k: _FakeProc(0, "some log\n"))
    sev, msg = cg.check_93_crontab_replace_has_manifest()
    assert sev == "PASS", msg
    assert "無 crontab REPLACE" in msg


def test_93_journalctl_unavailable_skip(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED", "1")
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))

    def _raise(*a, **k):
        raise FileNotFoundError("journalctl")

    monkeypatch.setattr(cg.subprocess, "run", _raise)
    sev, msg = cg.check_93_crontab_replace_has_manifest()
    assert sev == "PASS", msg
    assert "skip" in msg
