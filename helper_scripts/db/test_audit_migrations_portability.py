"""audit_migrations.py 可攜性回歸測試（item 12 / E3 portability fix）。

驗證重點（跨平台規則）：
1) source 內不再有開發機硬編絕對路徑 `/Users/ncyu/...`；
2) `_REPO_ROOT` 由 `__file__` 上溯三層正確反推 repo root；
3) migrations 目錄候選含 repo-relative 路徑，且解析結果指向 `<repo>/sql/migrations`；
4) `OPENCLAW_MIGRATIONS_DIR` 環境覆寫：有效目錄回傳、無效目錄 fail-closed（SystemExit）。

純 stdlib，Mac 可直接跑；不觸 DB（psycopg2 於 source 內為 late-import，未被本測試觸發）。
以 spec-from-file 載入腳本，避免套件 import 副作用，且因 __name__ 非 "__main__" 不會執行 main()。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


# 以檔案路徑載入被測腳本（與 sibling test_check_applied_migration_checksums.py 同風格）
SCRIPT = Path(__file__).with_name("audit_migrations.py")
SPEC = importlib.util.spec_from_file_location("audit_migrations_under_test", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)  # 載入即計算 _REPO_ROOT / MIGRATIONS_DIR_CANDIDATES；不跑 main()


def test_no_hardcoded_user_path_in_source() -> None:
    # 核心 acceptance：source 內不得殘留任何 /Users/ncyu 開發機絕對路徑。
    text = SCRIPT.read_text(encoding="utf-8")
    assert "/Users/ncyu" not in text, "source 仍含硬編開發機路徑"
    # 也不得殘留舊的完整硬編字串
    assert "/Users/ncyu/Projects/TradeBot/srv/sql/migrations" not in text


def test_repo_root_resolves_three_levels_up() -> None:
    # helper_scripts/db/audit_migrations.py → 上溯三層 = srv repo root。
    expected = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(str(SCRIPT))))
    )
    assert mod._REPO_ROOT == expected
    # repo-relative migrations 目錄應真實存在（本 worktree 即 repo root）
    repo_mig = os.path.join(mod._REPO_ROOT, "sql", "migrations")
    assert os.path.isdir(repo_mig), f"repo-relative migrations 目錄不存在: {repo_mig}"


def test_candidates_are_portable_and_repo_relative_present() -> None:
    # 被移除的具體硬編開發機字面量不得再出現在候選中。
    # 注意：`expanduser("~/...")` 於本 Mac 展開為 /Users/ncyu/... 屬 home-relative（source 內為 `~`，
    #       Linux 會展成 /home/... 故仍可攜），不是被移除的硬編缺陷，不可誤判為殘留。
    removed_literal = os.path.join(
        "/Users/ncyu/Projects/TradeBot/srv", "sql", "migrations"
    )
    assert removed_literal not in mod.MIGRATIONS_DIR_CANDIDATES
    # 必須包含由 __file__ 反推的 repo-relative 候選（本 fix 新增項）。
    repo_rel = os.path.join(mod._REPO_ROOT, "sql", "migrations")
    assert repo_rel in mod.MIGRATIONS_DIR_CANDIDATES


def test_find_migrations_dir_resolves_via_repo_relative(monkeypatch) -> None:
    # 隔離出 repo-relative 解析：只保留 repo-relative 候選，證明其單獨即可命中，
    # 不依賴 cwd（先前 cwd 候選可能恰好也命中，故此處刻意排除以真證 fix）。
    monkeypatch.delenv("OPENCLAW_MIGRATIONS_DIR", raising=False)
    repo_rel = os.path.join(mod._REPO_ROOT, "sql", "migrations")
    monkeypatch.setattr(mod, "MIGRATIONS_DIR_CANDIDATES", [repo_rel])
    resolved = mod.find_migrations_dir()
    assert resolved == repo_rel
    assert os.path.isdir(resolved)
    assert "/Users/ncyu" not in resolved


def test_env_override_valid_dir_is_returned(monkeypatch, tmp_path: Path) -> None:
    # 顯式 env 覆寫有效目錄 → 直接回傳，繞過候選推斷。
    target = tmp_path / "sql" / "migrations"
    target.mkdir(parents=True)
    monkeypatch.setenv("OPENCLAW_MIGRATIONS_DIR", str(target))
    assert mod.find_migrations_dir() == str(target)


def test_env_override_invalid_dir_is_fail_closed(monkeypatch, tmp_path: Path) -> None:
    # 顯式 env 覆寫非目錄 → fail-closed 中止（SystemExit），不靜默回退候選，
    # 避免誤對錯誤的 migrations 目錄做稽核。
    bad = tmp_path / "does_not_exist"
    monkeypatch.setenv("OPENCLAW_MIGRATIONS_DIR", str(bad))
    with pytest.raises(SystemExit):
        mod.find_migrations_dir()


def test_import_smoke_via_subprocess_prints_repo_relative_path() -> None:
    # 「import/help」冒煙：以子行程 import 腳本並印出 find_migrations_dir()，
    # 證明從 repo root 呼叫時解析到 <repo>/sql/migrations 且輸出無 /Users/ncyu。
    repo_root = mod._REPO_ROOT
    code = (
        "import importlib.util,os,sys;"
        f"s=importlib.util.spec_from_file_location('m',{str(SCRIPT)!r});"
        "m=importlib.util.module_from_spec(s);sys.modules['m']=m;"  # dataclass 需先註冊
        "s.loader.exec_module(m);"
        "print(m.find_migrations_dir())"
    )
    env = dict(os.environ)
    env.pop("OPENCLAW_MIGRATIONS_DIR", None)
    cp = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert cp.returncode == 0, cp.stderr
    out = cp.stdout.strip()
    assert out.endswith(os.path.join("sql", "migrations"))
    assert os.path.isdir(out)
    assert "/Users/ncyu" not in out
