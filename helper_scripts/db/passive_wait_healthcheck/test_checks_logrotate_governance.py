"""checks_logrotate_governance [95] focused tests（OPS F4）。

MODULE_NOTE:
  以 monkeypatch env + tmp_path 隔離檔案系統,驗 [95] 的判定分支:match=PASS(含
  短 hash)、drift 兩側 mtime 均超窗=升級、單側近期 mtime=容忍窗（proxy 取 max,
  runtime/canonical 兩側各驗一次）、runtime/canonical 缺失分支、proxy-None 保守
  超窗、未來 mtime 保守 guard、恰 24h 邊界（now= 注入,strict >）、_TRUE_VALUES
  變體。fixture 一律 time.time() 相對偏移經 os.utime,禁硬編日期/牆鐘絕對值
  （repo 有 fixture 日期腐化 time-bomb 前科）。純函數不觸 runtime。
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import helper_scripts.db.passive_wait_healthcheck.checks_logrotate_governance as lg


_CANONICAL_BODY = "/var/openclaw/engine.log {\n    size 1G\n    rotate 3\n}\n"
_DRIFTED_BODY = "/tmp/openclaw/engine.log {\n    size 1M\n    rotate 1\n}\n"


def _set_common(monkeypatch, tmp_path: Path, runtime: Path) -> None:
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path / "repo"))
    monkeypatch.setenv("OPENCLAW_LOGROTATE_RUNTIME_CONF", str(runtime))
    # 防外部 shell 殘留 required env 污染預設-WARN 分支。
    monkeypatch.delenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", raising=False)


def _write_canonical(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "repo" / "helper_scripts"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "logrotate-openclaw.conf"
    p.write_text(body, encoding="utf-8")
    return p


def _write_runtime(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "runtime-logrotate-openclaw.conf"
    p.write_text(body, encoding="utf-8")
    return p


def _age(p: Path, hours: float) -> None:
    """把檔案 mtime 設為「現在 − hours 小時」（相對時鐘,無絕對日期）。"""
    old = time.time() - hours * 3600
    os.utime(p, (old, old))


def _short(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# [95] logrotate_runtime_matches_repo
# ---------------------------------------------------------------------------

def test_95_match_pass_with_short_hash(monkeypatch, tmp_path):
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _CANONICAL_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "PASS", msg
    assert _short(_CANONICAL_BODY) in msg


def test_95_drift_over_24h_required_fail(monkeypatch, tmp_path):
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    # 兩檔 mtime 均 25h 前 → proxy=max 也超 24h 窗。
    _age(canonical, 25.0)
    _age(runtime, 25.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "> 24h" in msg
    # 訊息含兩側短 hash + cp 修復提示。
    assert _short(_DRIFTED_BODY) in msg and _short(_CANONICAL_BODY) in msg
    assert "cp " in msg


def test_95_drift_over_24h_default_warn(monkeypatch, tmp_path):
    # 同上但無 required env → 預設 WARN。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    _age(canonical, 25.0)
    _age(runtime, 25.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "> 24h" in msg


def test_95_recent_runtime_mtime_tolerance_warn(monkeypatch, tmp_path):
    # runtime 1h 前被動過（可能剛 cp 對齊中）→ 容忍窗 WARN,即使 required=1。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _age(canonical, 25.0)
    _age(runtime, 1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "容忍窗" in msg


def test_95_recent_canonical_mtime_tolerance_warn(monkeypatch, tmp_path):
    # canonical 1h 前剛過 review 更新（cp 尚未跟上）→ 容忍窗 WARN,即使 required=1
    # （proxy 取 max 的另一側驗證）。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _age(canonical, 1.0)
    _age(runtime, 25.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "容忍窗" in msg


def test_95_runtime_missing_default_warn_required_fail(monkeypatch, tmp_path):
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = tmp_path / "missing-runtime-logrotate.conf"  # 故意不建檔
    _set_common(monkeypatch, tmp_path, runtime)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "整機零輪替" in msg and "cp " in msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "FAIL", msg2


def test_95_canonical_missing_severity(monkeypatch, tmp_path):
    # repo 下故意不建 canonical → sev（預設 WARN / required=1 FAIL）,訊息含路徑。
    runtime = _write_runtime(tmp_path, _CANONICAL_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "canonical" in msg and str(tmp_path / "repo") in msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "FAIL", msg2


def test_95_proxy_none_conservative_over_window(monkeypatch, tmp_path):
    # proxy 不可得（sha 讀後檔案被移走等 stat race）→ 保守視為超窗,required=1 升 FAIL。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    monkeypatch.setattr(lg, "_drift_proxy_mtime", lambda *a: None)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "保守" in msg


def test_95_future_mtime_conservative_escalation(monkeypatch, tmp_path):
    # runtime mtime 在未來 48h（時鐘偏移主機 cp / touch -t 竄改情境）→ 不得以
    # age=max(0, 負)=0 永久壓制升級,保守超窗 required=1 升 FAIL。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _age(canonical, 25.0)
    _age(runtime, -48.0)  # 負時差=未來（仍是相對時鐘,無絕對日期）
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "未來" in msg and "保守" in msg


def test_95_exact_24h_boundary_with_now_injection(monkeypatch, tmp_path):
    # now= 注入打確定性邊界:age==24h 恰在窗內（strict >）,+1s 才升級。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    t0 = float(int(time.time()))  # 取整秒,utime/stat 往返無浮點殘差
    os.utime(canonical, (t0, t0))
    os.utime(runtime, (t0, t0))
    sev, msg = lg.check_95_logrotate_runtime_matches_repo(now=t0 + 24 * 3600)
    assert sev == "WARN", msg
    assert "容忍窗" in msg
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo(now=t0 + 24 * 3600 + 1)
    assert sev2 == "FAIL", msg2
    assert "> 24h" in msg2


def test_95_required_env_true_values_variants(monkeypatch, tmp_path):
    # _TRUE_VALUES 變體:"true" 升級、"0" 不升級。
    canonical = _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    _age(canonical, 25.0)
    _age(runtime, 25.0)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "true")
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "0")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "WARN", msg2
