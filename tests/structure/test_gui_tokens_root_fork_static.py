from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)

# :root 定義開頭(選擇器級,含 [attr] / :not() 變體);純注釋提及 :root(無 `{`)不命中
ROOT_DEF_RE = re.compile(r":root\s*(?:\[[^\]]*\]|:not\([^)]*\))*\s*\{")

# token 正本 + 過渡映射層(P0.4 收斂完成刪 compat 時同步更新本名單)
ALLOWED_ROOT_DEF_FILES = {"tokens.css", "tokens-compat.css"}


def test_static_root_token_definitions_only_in_tokens_files() -> None:
    """P0.1 token fork 防回歸:static/ 內 :root{...} 定義只允許 tokens.css/tokens-compat.css。

    styles.css / common.js(ocInjectBaseCSS 注入)曾各持一份 :root fork(色板
    三處漂移根因);P0.1 收斂為 tokens.css 正本 + tokens-compat.css 舊名映射層。
    任何其他 static/ 檔(CSS/JS 模板字串/HTML inline <style>)再引入 :root
    定義 = fork 復發,雙主題(玄夜/帛晝)必漂。
    """
    offenders: list[str] = []
    scanned = 0
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.suffix not in {".css", ".js", ".html"}:
            continue
        if path.name in ALLOWED_ROOT_DEF_FILES:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8")
        if ROOT_DEF_RE.search(text):
            offenders.append(str(path.relative_to(STATIC_DIR)))
    assert scanned > 20, f"expected to scan static GUI surface, got {scanned} files"
    assert not offenders, (
        ":root 定義 fork 復發(token 定義只允許 tokens.css/tokens-compat.css): "
        + ", ".join(offenders)
    )


def test_tokens_css_defines_root_and_compat_maps_legacy_names() -> None:
    """正常路徑錨點(gate 雙向):正本/映射層本身必須真的存在且有 :root 定義。

    防止「刪掉 tokens.css 也能讓 fork guard 通過」的空洞綠;compat 至少映射
    舊名 --bg/--text(存量消費點最大宗),P0.4 刪 compat 時同步改本測試。
    """
    tokens = (STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    compat = (STATIC_DIR / "tokens-compat.css").read_text(encoding="utf-8")
    assert ROOT_DEF_RE.search(tokens), "tokens.css 應含 :root token 正本定義"
    assert ROOT_DEF_RE.search(compat), "tokens-compat.css 應含 :root 映射層定義"
    assert "--bg:" in compat and "--text:" in compat, "compat 應映射舊名 --bg/--text"
