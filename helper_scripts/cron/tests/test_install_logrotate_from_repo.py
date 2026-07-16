"""install_logrotate_from_repo.sh 靜態契約 + 負向行為測試（[95] 收口配套）。

MODULE_NOTE:
  驗證唯一 logrotate 安裝入口的守衛家族:
    - 空 canonical 守衛:0 active 行 → exit 6 拒絕（無豁免 flag）；
    - stanza shrink-guard:runtime 3 stanza 裝 1 stanza → exit 7 拒絕,
      OPENCLAW_LOGROTATE_ALLOW_SHRINK=1 顯式豁免;首裝（runtime 缺）不觸發；
    - validation gate:fake logrotate -d 非 0 → exit 8（dry-run 也擋）；
    - dry-run 預設:runtime 檔零改動,manifest 落 applied:false（不刷 [95] 時鐘）；
    - --apply:原子安裝 + post-verify 後 manifest 改寫 applied:true + post_apply_sha256；
    - manifest JSON escape:REASON/ACTOR 含引號/換行/反斜線仍產合法 JSON 且值往返；
    - 同秒 mutation dir 碰撞:fake date shim 固定 stamp,第二次執行追加 .$$ 後綴；
    - stanza opener-idiom:postrotate 內 awk '{print}' 等行內大括號不誤計、不誤觸
      shrink-guard。
  為什麼用 fake logrotate shim + OPENCLAW_LOGROTATE_SKIP_PLATFORM_GUARD=1:installer
  平台守門僅 Linux 跑,本測試在 Mac dev 上以繞過旗在 tmp_path 目標上跑完整流程
  （含 --apply）,PATH shim 讓 `logrotate -d` 回可控退出碼,故 validation gate 可
  跨平台驗。runtime/canonical/data 路徑全走 tmp_path env override,絕不真寫 $HOME。
  fixture 一律相對時鐘,禁絕對日期（repo 有 fixture 日期腐化 time-bomb 前科;
  fake date shim 輸出用非日期字面 stamp,同理由）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
INSTALLER = CRON_DIR / "install_logrotate_from_repo.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _conf_body(n_stanzas: int, size: str = "1M") -> str:
    """造 n 個 stanza 的 logrotate conf 內容（路徑純字面,fake shim 不會真讀）。"""
    parts = ["# 測試 conf（fixture,相對時鐘,無絕對日期）\n"]
    for i in range(n_stanzas):
        parts.append(
            f"/var/log/test{i}.log {{\n    size {size}\n    rotate 3\n    missingok\n}}\n"
        )
    return "".join(parts)


def _make_fake_logrotate(bin_dir: Path, exit_code: int) -> None:
    """造一個假 logrotate:任何呼叫（含 -d）以指定退出碼結束。

    為什麼:Mac dev 無 logrotate binary;shim 讓 validation gate 的通過/失敗兩態
    皆可控,且絕不觸任何真輪替面。
    """
    fake = bin_dir / "logrotate"
    fake.write_text(
        f"#!/usr/bin/env bash\nexit {exit_code}\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)


def _run(
    tmp_path: Path,
    canonical_body: str | None,
    runtime_body: str | None,
    *args: str,
    logrotate_exit: int = 0,
    extra_env: dict | None = None,
    fake_date_stamp: str | None = None,
) -> subprocess.CompletedProcess:
    """跑 installer:canonical/runtime/data 全指 tmp_path,PATH 前置 fake logrotate。

    canonical_body=None → 不建 canonical 檔（缺失分支）;runtime_body=None → 首裝。
    fake_date_stamp:非 None 時 shim `date` 固定輸出該字串（非日期字面,相對時鐘
    鐵則）,讓同秒 mutation dir 碰撞可確定性重現。
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _make_fake_logrotate(bin_dir, logrotate_exit)
    if fake_date_stamp is not None:
        fake_date = bin_dir / "date"
        fake_date.write_text(
            f"#!/usr/bin/env bash\necho {fake_date_stamp}\n", encoding="utf-8"
        )
        fake_date.chmod(0o755)

    canonical = tmp_path / "canonical-logrotate.conf"
    if canonical_body is not None:
        canonical.write_text(canonical_body, encoding="utf-8")
    runtime = tmp_path / "runtime-logrotate.conf"
    if runtime_body is not None:
        runtime.write_text(runtime_body, encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["OPENCLAW_LOGROTATE_SKIP_PLATFORM_GUARD"] = "1"
    env["OPENCLAW_LOGROTATE_CANONICAL"] = str(canonical)
    env["OPENCLAW_LOGROTATE_RUNTIME_CONF"] = str(runtime)
    env["OPENCLAW_DATA_DIR"] = str(data_dir)
    # OPENCLAW_BASE_DIR 指向真 repo root（head_sha 僅溯源用,git 失敗也不 hard-fail）。
    env["OPENCLAW_BASE_DIR"] = str(CRON_DIR.parent.parent)
    # 防外部 shell 殘留豁免旗污染守衛分支。
    env.pop("OPENCLAW_LOGROTATE_ALLOW_SHRINK", None)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _manifests(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "data" / "logrotate_mutations").glob("*/manifest.json"))


# ---------------------------------------------------------------------------
# 靜態契約
# ---------------------------------------------------------------------------

def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(
        ["bash", "-n", str(INSTALLER)], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr


def test_executable_strict_and_linux_guard() -> None:
    src = _src(INSTALLER)
    assert INSTALLER.stat().st_mode & 0o111
    assert "set -euo pipefail" in src
    assert "install_logrotate_from_repo.sh requires Linux runtime" in src
    # dry-run 預設 + shrink-guard 豁免旗 + 兩段式 manifest 關鍵字均在源。
    assert 'MODE="dry-run"' in src
    assert "OPENCLAW_LOGROTATE_ALLOW_SHRINK" in src
    assert '"applied": false' in src or '"applied": $applied' in src
    # 零硬編 runtime 機器路徑（$HOME 表述）。
    assert "/home/ncyu" not in src and "/Users/ncyu" not in src


# ---------------------------------------------------------------------------
# pre-flight 守衛
# ---------------------------------------------------------------------------

def test_canonical_missing_exit_4(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(tmp_path, None, None)
    assert proc.returncode == 4, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "canonical not found" in proc.stderr


def test_empty_canonical_rejected_no_override(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # 全註釋 / 空行 → 0 active 行 → exit 6,ALLOW_SHRINK=1 也不能繞。
    empty_body = "# only comments\n#\n\n"
    proc = _run(
        tmp_path, empty_body, _conf_body(3),
        extra_env={"OPENCLAW_LOGROTATE_ALLOW_SHRINK": "1"},
    )
    assert proc.returncode == 6, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "0 active lines" in proc.stderr


# ---------------------------------------------------------------------------
# stanza shrink-guard
# ---------------------------------------------------------------------------

def test_shrink_guard_rejects_3_to_1(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(tmp_path, _conf_body(1), _conf_body(3))
    assert proc.returncode == 7, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "shrink-guard tripped" in proc.stderr
    # 拒絕路徑 manifest 必停在 applied:false(留檔可追溯,但不計為 [95] 合規安裝)。
    manifests = _manifests(tmp_path)
    assert manifests
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    assert data["applied"] is False
    assert data["shrink_guard_triggered"] == 1


def test_shrink_guard_override_allows_shrink(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(
        tmp_path, _conf_body(1), _conf_body(3),
        extra_env={"OPENCLAW_LOGROTATE_ALLOW_SHRINK": "1"},
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "override active" in proc.stderr


def test_first_install_runtime_missing_no_shrink_guard(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # runtime 缺=首裝:shrink-guard 不適用,dry-run 成功;manifest before_sha256 記 absent。
    proc = _run(tmp_path, _conf_body(1), None)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "DRY-RUN" in proc.stdout
    manifests = _manifests(tmp_path)
    assert manifests
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    assert data["before_sha256"] == "absent"
    assert data["before_stanzas"] == 0


# ---------------------------------------------------------------------------
# validation gate
# ---------------------------------------------------------------------------

def test_validation_failure_blocks_even_dry_run(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # fake logrotate -d 非 0 → exit 8;預設 dry-run 模式也擋（plan 本身壞）。
    proc = _run(tmp_path, _conf_body(2), None, logrotate_exit=1)
    assert proc.returncode == 8, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "validation failed" in proc.stderr
    # 拒絕路徑 manifest 必停在 applied:false 且記錄 validation:failed。
    manifests = _manifests(tmp_path)
    assert manifests
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    assert data["applied"] is False
    assert data["validation"] == "failed"


def test_validation_pass_allows_dry_run(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(tmp_path, _conf_body(2), None, logrotate_exit=0)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "validation      : passed" in proc.stdout


# ---------------------------------------------------------------------------
# dry-run 預設 / --apply 兩段式 manifest
# ---------------------------------------------------------------------------

def test_dry_run_default_zero_mutation_four_files(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    runtime_body = _conf_body(2, size="9M")  # 與 canonical 內容不同,stanza 數相同
    canonical_body = _conf_body(2)
    proc = _run(tmp_path, canonical_body, runtime_body)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "DRY-RUN" in proc.stdout
    # runtime 檔零改動。
    assert (tmp_path / "runtime-logrotate.conf").read_text(encoding="utf-8") == runtime_body
    # mutation dir 恰四檔。
    mut_dirs = list((tmp_path / "data" / "logrotate_mutations").iterdir())
    assert len(mut_dirs) == 1
    names = sorted(p.name for p in mut_dirs[0].iterdir())
    assert names == ["conf.after.txt", "conf.before.txt", "conf.diff.txt", "manifest.json"]
    # manifest 停在 applied:false + mode dry-run（不計為 [95] 合規安裝）。
    data = json.loads((mut_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert data["applied"] is False
    assert data["mode"] == "dry-run"
    assert "post_apply_sha256" not in data


def test_apply_installs_and_rewrites_manifest_applied_true(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    runtime_body = _conf_body(1, size="9M")
    canonical_body = _conf_body(2)
    proc = _run(tmp_path, canonical_body, runtime_body, "--apply")
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "INSTALLED" in proc.stdout
    # runtime 內容 == canonical（原子安裝 + post-verify 同口徑）。
    installed = (tmp_path / "runtime-logrotate.conf").read_text(encoding="utf-8")
    assert installed == canonical_body
    # manifest 改寫為 applied:true + post_apply_sha256（兩段式第二段）。
    manifests = _manifests(tmp_path)
    assert len(manifests) == 1
    data = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert data["applied"] is True
    assert data["mode"] == "apply"
    expected_sha = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
    assert data["post_apply_sha256"] == expected_sha
    assert data["after_sha256"] == expected_sha
    assert data["applied_utc"]


def test_unknown_argument_exit_3(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(tmp_path, _conf_body(1), None, "--bogus")
    assert proc.returncode == 3, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "unknown argument" in proc.stderr


def test_manifest_json_parses_with_full_field_set(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = _run(tmp_path, _conf_body(2), _conf_body(2, size="9M"))
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    manifests = _manifests(tmp_path)
    assert manifests
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    expected_keys = {
        "utc", "mode", "applied", "actor", "reason", "canonical", "runtime_conf",
        "head_sha", "before_sha256", "after_sha256", "before_stanzas",
        "after_stanzas", "shrink_guard_triggered", "shrink_guard_override",
        "validation",
    }
    assert expected_keys <= set(data.keys())
    assert isinstance(data["before_stanzas"], int)
    assert isinstance(data["after_stanzas"], int)
    assert data["validation"] == "passed"


def test_manifest_json_escapes_special_chars_roundtrip(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # REASON 是自然語言:引號/反斜線/換行/tab 是常態非欺詐——manifest 必須仍為合法
    # JSON 且值位元組往返(否則 applied:true receipt 自毀,[95] 視同無合規安裝)。
    reason = 'he said "boom" \\ path\nline2\ttab'
    actor = 'op "quoted" \\x'
    proc = _run(
        tmp_path, _conf_body(1), None, "--apply",
        extra_env={
            "OPENCLAW_LOGROTATE_REASON": reason,
            "OPENCLAW_LOGROTATE_ACTOR": actor,
        },
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    manifests = _manifests(tmp_path)
    assert len(manifests) == 1
    data = json.loads(manifests[0].read_text(encoding="utf-8"))  # 壞 JSON 會在此拋
    assert data["applied"] is True
    assert data["reason"] == reason
    assert data["actor"] == actor


def test_mutation_dir_same_second_collision_gets_suffix(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # fake date 固定 stamp(非日期字面)→ 兩次執行必碰撞;第二次應追加 .$$ 後綴,
    # 而非覆蓋前一份 receipt。
    stamp = "STAMPFIXEDZ"
    proc1 = _run(tmp_path, _conf_body(1), None, fake_date_stamp=stamp)
    assert proc1.returncode == 0, f"stdout={proc1.stdout}\nstderr={proc1.stderr}"
    proc2 = _run(tmp_path, _conf_body(1), None, fake_date_stamp=stamp)
    assert proc2.returncode == 0, f"stdout={proc2.stdout}\nstderr={proc2.stderr}"
    mut_dirs = sorted(p.name for p in (tmp_path / "data" / "logrotate_mutations").iterdir())
    assert len(mut_dirs) == 2, mut_dirs
    assert stamp in mut_dirs
    suffixed = [n for n in mut_dirs if n != stamp]
    assert len(suffixed) == 1 and suffixed[0].startswith(f"{stamp}.")
    # 兩份 receipt 各自完整可解析。
    for m in _manifests(tmp_path):
        json.loads(m.read_text(encoding="utf-8"))


def test_stanza_count_opener_idiom_ignores_inner_braces(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    # runtime 2 真 stanza,但 postrotate 內 awk '{print}' 與註釋 ${HOME} 帶行內大括號:
    # 裸 grep -c '{' 會數到 7 → canonical(2)*2=4 < 7 誤觸 shrink-guard;
    # opener-idiom(非註釋行且行尾 '{')正確數 2 → 不觸發。
    stanza = (
        "/var/log/inner{i}.log {{\n"
        "    size 1M\n"
        "    postrotate\n"
        "        /usr/bin/awk '{{print}}' /dev/null\n"
        "        /usr/bin/awk '{{print $1}}' /dev/null\n"
        "    endscript\n"
        "}}\n"
    )
    runtime_body = "# ${HOME} 行內大括號註釋示例\n" + "".join(
        stanza.format(i=i) for i in range(2)
    )
    proc = _run(tmp_path, _conf_body(2), runtime_body)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    manifests = _manifests(tmp_path)
    assert manifests
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    assert data["before_stanzas"] == 2
    assert data["after_stanzas"] == 2
    assert data["shrink_guard_triggered"] == 0
