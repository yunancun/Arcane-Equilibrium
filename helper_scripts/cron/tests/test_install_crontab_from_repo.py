"""install_crontab_from_repo.sh 靜態契約 + 負向行為測試（P0-2④ crontab 治理）。

MODULE_NOTE:
  驗證唯一 crontab 安裝入口的三道守衛:
    - shrink-guard:30 行 live 表裝 3 行表 → exit 7 拒絕（FA A5 負向測試）；
    - 空表守衛:render 出 0 active 行 → exit 6 拒絕（無豁免 flag）；
    - dry-run 預設:不傳 --apply 時絕不寫 crontab（fake shim 記錄零 apply 寫入）。
  為什麼用 fake crontab shim + OPENCLAW_CRONTAB_SKIP_PLATFORM_GUARD=1:installer
  平台守門僅 Linux 跑,本測試在 Mac dev 上以繞過旗跑純邏輯（render/行數/shrink），
  fake shim 讓 `crontab -l` 回可控 live 表、`crontab -` 只記錄不真寫,故負向行為
  可跨平台驗且零 runtime mutation。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
INSTALLER = CRON_DIR / "install_crontab_from_repo.sh"
TEMPLATE = CRON_DIR / "crontab.trade-core.template"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _make_fake_crontab(bin_dir: Path, live_lines: list[str]) -> Path:
    """造一個假 crontab:`-l` 印 live_lines、`-`(stdin) 把收到內容寫 applied.txt。

    為什麼:真 crontab 會改 runtime;測試以 shim 攔截,`-` 分支寫 applied.txt 讓
    測試可斷言「dry-run 從不 apply、apply 才寫入」。
    """
    applied = bin_dir / "applied.txt"
    live_body = "\\n".join(live_lines)
    fake = bin_dir / "crontab"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == \"-l\" ]]; then\n"
        f"  printf '%b\\n' \"{live_body}\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"-\" ]]; then\n"
        f"  cat > \"{applied}\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return applied


def _run(tmp_path: Path, template_body: str, live_lines: list[str], *args: str,
         extra_env: dict | None = None) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _make_fake_crontab(bin_dir, live_lines)
    template = tmp_path / "tmpl.template"
    template.write_text(template_body, encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["OPENCLAW_CRONTAB_SKIP_PLATFORM_GUARD"] = "1"
    env["OPENCLAW_CRONTAB_TEMPLATE"] = str(template)
    env["OPENCLAW_DATA_DIR"] = str(data_dir)
    # OPENCLAW_BASE_DIR 指向真 repo root（installer 需 git rev-parse HEAD 派生 pin）。
    env["OPENCLAW_BASE_DIR"] = str(CRON_DIR.parent.parent)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# 靜態契約
# ---------------------------------------------------------------------------

def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_executable_strict_and_linux_guard() -> None:
    src = _src(INSTALLER)
    assert INSTALLER.stat().st_mode & 0o111
    assert "set -euo pipefail" in src
    assert "install_crontab_from_repo.sh requires Linux runtime" in src
    # dry-run 預設 + shrink-guard + 空表守衛 + pin-by-reference 均在源。
    assert "MODE=\"dry-run\"" in src
    assert "OPENCLAW_CRONTAB_ALLOW_SHRINK" in src
    assert "rev-parse --short HEAD" in src


def test_template_has_no_inline_source_head_pin() -> None:
    body = _src(TEMPLATE)
    # 2026-07-12 升級：意圖從「禁手寫 short-sha 字面」升級為「禁 inline pin」——
    # 世代 pin 權威=$OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json
    # (寫者=restart_all.sh 成功啟動後+derive_expected_source_head.sh pull SOP 尾接),
    # cron 行不得再帶任何 OPENCLAW_EXPECTED_SOURCE_HEAD 欄位（含 {{HEAD}} render）。
    assert "OPENCLAW_EXPECTED_SOURCE_HEAD" not in body


# ---------------------------------------------------------------------------
# 負向行為（FA A5:30 行表裝 3 行表被拒）
# ---------------------------------------------------------------------------

def test_shrink_guard_rejects_30_to_3(tmp_path: Path) -> None:
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("bash/git not available")
    live = [f"{i} * * * * /bin/true # lane{i}" for i in range(30)]
    small = "\n".join(["1 * * * * /bin/true # a",
                        "2 * * * * /bin/true # b",
                        "3 * * * * /bin/true # c"]) + "\n"
    proc = _run(tmp_path, small, live)
    assert proc.returncode == 7, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "shrink-guard tripped" in proc.stderr


def test_shrink_guard_override_allows_shrink(tmp_path: Path) -> None:
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("bash/git not available")
    live = [f"{i} * * * * /bin/true # lane{i}" for i in range(30)]
    small = "1 * * * * /bin/true # a\n2 * * * * /bin/true # b\n3 * * * * /bin/true # c\n"
    # 顯式豁免 → dry-run 應成功退 0（override active,proceeding）。
    proc = _run(tmp_path, small, live, extra_env={"OPENCLAW_CRONTAB_ALLOW_SHRINK": "1"})
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "override active" in proc.stderr


def test_empty_template_rejected_no_override(tmp_path: Path) -> None:
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("bash/git not available")
    live = [f"{i} * * * * /bin/true # lane{i}" for i in range(30)]
    # 全註釋 / 空行 → 0 active 行 → 空表守衛 exit 6,ALLOW_SHRINK 也不能繞。
    empty_body = "# only comments\n#\n\n"
    proc = _run(tmp_path, empty_body, live, extra_env={"OPENCLAW_CRONTAB_ALLOW_SHRINK": "1"})
    assert proc.returncode == 6, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "0 active lines" in proc.stderr


def test_dry_run_default_does_not_apply(tmp_path: Path) -> None:
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("bash/git not available")
    live = [f"{i} * * * * /bin/true # lane{i}" for i in range(10)]
    body = "\n".join([f"{i} * * * * /bin/true # lane{i}" for i in range(10)]) + "\n"
    data_dir = tmp_path / "data"
    proc = _run(tmp_path, body, live)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "DRY-RUN" in proc.stdout
    # 預設 dry-run:fake crontab `-` 分支從未被叫 → applied.txt 不存在。
    assert not (tmp_path / "bin" / "applied.txt").exists()
    # manifest 有落持久路徑供追溯。
    mutations = list((data_dir / "crontab_mutations").glob("*/manifest.json"))
    assert mutations, "manifest 未落 crontab_mutations/"


def test_head_pin_rendered_into_manifest(tmp_path: Path) -> None:
    if shutil.which("bash") is None or shutil.which("git") is None:
        pytest.skip("bash/git not available")
    live = [f"{i} * * * * /bin/true # lane{i}" for i in range(10)]
    body = "1 * * * * OPENCLAW_EXPECTED_SOURCE_HEAD={{HEAD}} /bin/true # pinned\n" + \
           "\n".join([f"{i} * * * * /bin/true # lane{i}" for i in range(9)]) + "\n"
    data_dir = tmp_path / "data"
    proc = _run(tmp_path, body, live)
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    after = list((data_dir / "crontab_mutations").glob("*/crontab.after.txt"))
    assert after
    rendered = after[0].read_text(encoding="utf-8")
    # {{HEAD}} 已被替換為真 short-sha,render 產物不得殘留佔位符。
    assert "{{HEAD}}" not in rendered
    assert "OPENCLAW_EXPECTED_SOURCE_HEAD=" in rendered
