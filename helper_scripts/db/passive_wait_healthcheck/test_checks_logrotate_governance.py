"""checks_logrotate_governance [95] focused tests（OPS F4）。

MODULE_NOTE:
  以 monkeypatch env + tmp_path 隔離檔案系統,驗 [95] 的判定分支:match=PASS(含
  短 hash)、mismatch 的 drift 起點=最新 applied:true manifest mtime(唯一安裝
  入口兩段式 manifest;無合規 manifest / 只有 dry-run applied:false / 壞 JSON /
  非 dict 頂層 / 超尺寸 / truthy 非布林 applied("false" 字串、數字 1,釘死
  `is True` 嚴格性)皆=視為超 24h 窗)、合規 manifest 1h 前=容忍窗、25h 前=超窗、未來 manifest
  mtime 保守 guard、恰 24h 邊界（now= 注入,strict >）、runtime/canonical 缺失
  分支、_TRUE_VALUES 變體。manifest fixture 一律 tmp_path/logrotate_mutations/
  下造檔 + os.utime 相對偏移,禁硬編日期/牆鐘絕對值（repo 有 fixture 日期腐化
  time-bomb 前科）。純函數不觸 runtime。
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
    # manifest 掃描根=tmp_path/logrotate_mutations（隔離真 runtime 資料面）。
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
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


def _write_manifest(tmp_path: Path, name: str, body: str,
                    hours_ago: float | None = None) -> Path:
    """造 tmp_path/logrotate_mutations/<name>/manifest.json;mtime=現在−hours_ago 小時。

    相對時鐘鐵則:偏移一律以 time.time() 為基準,無任何絕對日期。
    """
    d = tmp_path / "logrotate_mutations" / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "manifest.json"
    p.write_text(body, encoding="utf-8")
    if hours_ago is not None:
        old = time.time() - hours_ago * 3600
        os.utime(p, (old, old))
    return p


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


def test_95_mismatch_no_manifest_default_warn_required_fail(monkeypatch, tmp_path):
    # mismatch 且無任何 manifest（治理入口從未 --apply）→ 直接視為超 24h 窗。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "治理入口" in msg and "超 24h 窗" in msg
    # 訊息含兩側短 hash + 安裝入口修復提示。
    assert _short(_DRIFTED_BODY) in msg and _short(_CANONICAL_BODY) in msg
    assert "install_logrotate_from_repo.sh --apply" in msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "FAIL", msg2


def test_95_mismatch_dry_run_manifest_not_compliant(monkeypatch, tmp_path):
    # 只有 applied:false（dry-run 第一段）manifest → 不算合規安裝,不刷 drift 時鐘。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-dryrun", '{"applied": false, "mode": "dry-run"}',
                    hours_ago=1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "治理入口" in msg


def test_95_mismatch_malformed_manifests_fail_soft(monkeypatch, tmp_path):
    # 畸形 manifest 家族全 fail-soft 跳過,等同無合規 manifest（不上拋崩 lane、不刷
    # 時鐘）:截斷 JSON / 非 dict 頂層(null、list——data.get 會 AttributeError 的
    # 反例) / 超尺寸(>1 MiB,即使內含 applied:true 也不解析,防 MemoryError)。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-broken", '{"applied": true', hours_ago=1.0)  # 截斷 JSON
    _write_manifest(tmp_path, "m-null", "null", hours_ago=1.0)  # 非 dict:null
    _write_manifest(tmp_path, "m-list", '[{"applied": true}]', hours_ago=1.0)  # 非 dict:list
    oversize = '{"applied": true, "pad": "' + "x" * (1024 * 1024 + 100) + '"}'
    _write_manifest(tmp_path, "m-huge", oversize, hours_ago=1.0)  # 超尺寸守衛
    # 深巢 JSON:json.loads 拋 RecursionError(非 ValueError)——釘 except 的第三臂。
    _write_manifest(tmp_path, "m-deep", "[" * 100000 + "]" * 100000, hours_ago=1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "治理入口" in msg


def test_95_applied_string_false_truthy_not_compliant(monkeypatch, tmp_path):
    # E4 G-1:{"applied": "false"}(字串,truthy!)→ `is True` 嚴格判定不算合規,
    # mismatch + required=1 仍 FAIL——釘死 mutation survivor(若判定寫成 truthy
    # check,此 fixture 會被誤認合規安裝落入容忍窗)。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-strfalse", '{"applied": "false"}', hours_ago=1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "治理入口" in msg


def test_95_applied_numeric_one_not_compliant(monkeypatch, tmp_path):
    # E4 G-1 順手:{"applied": 1}(truthy 且 1 == True,但 1 is not True)→ 同不算
    # 合規;JSON 布林 true 才是安裝入口的契約輸出。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-numone", '{"applied": 1}', hours_ago=1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "治理入口" in msg


def test_95_applied_manifest_1h_tolerance_warn(monkeypatch, tmp_path):
    # 合規安裝 1h 前 → 容忍窗 WARN,即使 required=1;取「最新」applied manifest
    # （另放一個 30h 前的舊合規紀錄,證 newest 語意）。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-old", '{"applied": true}', hours_ago=30.0)
    _write_manifest(tmp_path, "m-new", '{"applied": true}', hours_ago=1.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "容忍窗" in msg


def test_95_applied_manifest_25h_default_warn_required_fail(monkeypatch, tmp_path):
    # 合規安裝 25h 前仍 mismatch → 超窗:預設 WARN、required=1 升 FAIL,訊息含 age。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    _write_manifest(tmp_path, "m-stale", '{"applied": true}', hours_ago=25.0)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "> 24h" in msg and "距上次合規安裝" in msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "FAIL", msg2
    assert "> 24h" in msg2


def test_95_future_manifest_mtime_conservative_escalation(monkeypatch, tmp_path):
    # manifest mtime 在未來 48h（時鐘偏移主機寫入 / touch -t 竄改情境）→ 不得以
    # age=max(0, 負)=0 永久壓制升級,保守超窗 required=1 升 FAIL。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    _write_manifest(tmp_path, "m-future", '{"applied": true}',
                    hours_ago=-48.0)  # 負時差=未來（仍是相對時鐘,無絕對日期）
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    assert "未來" in msg and "保守" in msg


def test_95_exact_24h_boundary_with_now_injection(monkeypatch, tmp_path):
    # now= 注入打確定性邊界:age==24h 恰在窗內（strict >）,+1s 才升級。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "1")
    manifest = _write_manifest(tmp_path, "m-boundary", '{"applied": true}')
    t0 = float(int(time.time()))  # 取整秒,utime/stat 往返無浮點殘差
    os.utime(manifest, (t0, t0))
    sev, msg = lg.check_95_logrotate_runtime_matches_repo(now=t0 + 24 * 3600)
    assert sev == "WARN", msg
    assert "容忍窗" in msg
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo(now=t0 + 24 * 3600 + 1)
    assert sev2 == "FAIL", msg2
    assert "> 24h" in msg2


def test_95_runtime_missing_default_warn_required_fail(monkeypatch, tmp_path):
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = tmp_path / "missing-runtime-logrotate.conf"  # 故意不建檔
    _set_common(monkeypatch, tmp_path, runtime)
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "WARN", msg
    assert "整機零輪替" in msg and "install_logrotate_from_repo.sh --apply" in msg
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


def test_95_required_env_true_values_variants(monkeypatch, tmp_path):
    # _TRUE_VALUES 變體:"true" 升級、"0" 不升級（mismatch 無合規 manifest 分支）。
    _write_canonical(tmp_path, _CANONICAL_BODY)
    runtime = _write_runtime(tmp_path, _DRIFTED_BODY)
    _set_common(monkeypatch, tmp_path, runtime)
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "true")
    sev, msg = lg.check_95_logrotate_runtime_matches_repo()
    assert sev == "FAIL", msg
    monkeypatch.setenv("OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED", "0")
    sev2, msg2 = lg.check_95_logrotate_runtime_matches_repo()
    assert sev2 == "WARN", msg2
