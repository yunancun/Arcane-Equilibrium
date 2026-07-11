"""P1.0 GUI smoke — 家族 (4):HTML 資產引用存在性守衛(dangling ref 靜態偵測)。

MODULE_NOTE(為何靜態 / 為何不需 node):
  每個 <script src="/static/…"> 與 <link href="/static/…"> 應指向真存在的檔;dangling
  ref(改名/刪檔漏改引用)是 404 破版但 grep 難查的盲區。本檔純 Python 靜態解析
  HTML→抽引用→映射 /static/ 前綴到 static 目錄→查檔存在,不需 node、不連 runtime。
  外部 URL(如 CDN)與非-/static 相對引用不在本家族範圍(無法/不應靜態查外部)。

  誠實邊界:綠只證「引用目標檔存在於 repo」,不 attest 該檔內容正確或 runtime 真被載入。

設計正本:docs/execution_plan/gui_redesign/design/08_smoke_tests.md §2 家族 (4)。
anti-vacuous-green 紀律鏡像 test_gui_style_ratchet_static.py:掃描斷言含
「scanned-count 下限 + substantive-detector 錨點」,extractor/解析壞掉時大聲 fail。
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)

_STATIC_PREFIX = "/static/"


class _AssetRefExtractor(HTMLParser):
    """抽 <script src> 與 <link href> 的引用字串(帶行號)。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.refs: list[tuple[int, str]] = []  # (line, ref)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and "src" in d:
            self.refs.append((self.getpos()[0], d["src"]))
        elif tag == "link" and "href" in d:
            self.refs.append((self.getpos()[0], d["href"]))


def _rel(path: Path) -> str:
    return path.relative_to(STATIC_DIR).as_posix()


def _resolve_static_ref(ref: str, base_dir: Path) -> tuple[bool, Path | None]:
    """把 /static/ 引用映射到 base_dir 下真實路徑。

    回傳 (is_static_ref, target)。非-/static 引用(外部 URL、相對路徑)→ (False, None),
    不在家族(4)存在性範圍。strip `?v=…` cache-bust query 與 `#frag`。
    """
    if not ref.startswith(_STATIC_PREFIX):
        return False, None
    rel = ref[len(_STATIC_PREFIX) :]
    rel = rel.split("?", 1)[0].split("#", 1)[0]
    return True, (base_dir / rel)


def _iter_asset_refs() -> list[tuple[str, int, str, Path]]:
    """收所有 HTML 內指向 /static/ 的引用。

    回傳 (html_rel, line, ref, target_path)。外部/相對引用剔除(不在存在性範圍)。
    """
    out: list[tuple[str, int, str, Path]] = []
    for html in sorted(STATIC_DIR.rglob("*.html")):
        if not html.is_file():
            continue
        ex = _AssetRefExtractor()
        ex.feed(html.read_text(encoding="utf-8"))
        ex.close()
        for line, ref in ex.refs:
            is_static, target = _resolve_static_ref(ref, STATIC_DIR)
            if not is_static or target is None:
                continue
            out.append((_rel(html), line, ref, target))
    return out


ASSET_REFS = _iter_asset_refs()
_REF_IDS = [f"{rel}@L{line}:{ref}" for (rel, line, ref, _t) in ASSET_REFS]


def test_asset_refs_scanned_floor() -> None:
    """掃描面下界:防 HTMLParser 抽取/解析壞掉導致家族(4)零引用空洞綠。

    現況 211 個 /static/ 引用(common 系列 include × ~21 頁 + per-tab)。floor=100 排除歸零。
    """
    assert len(ASSET_REFS) >= 100, (
        f"HTML /static/ 引用抽取數異常少(scanned={len(ASSET_REFS)}),HTMLParser 抽取或解析疑壞掉"
    )


@pytest.mark.parametrize("asset_ref", ASSET_REFS, ids=_REF_IDS)
def test_asset_ref_target_exists(asset_ref: tuple[str, int, str, Path]) -> None:
    """每個 /static/ 引用的目標檔必須存在(dangling ref = 點名失敗)。"""
    rel, line, ref, target = asset_ref
    assert target.is_file(), (
        f"dangling 資產引用:{rel} @L{line} 引用 {ref}\n"
        f"  → 解析為 {target}(檔不存在)。改名/刪檔漏改引用?"
    )


def test_asset_ref_extractor_and_resolver_are_substantive(tmp_path: Path) -> None:
    """釘死 extractor + resolver 語義:防抽取恆空或存在性檢查被架空成恆綠。

    ① 合成 HTML 抽取:script src / link href / 帶 query / 外部 URL / 非-/static 相對 →
       驗抽取數、static-filter、query-strip 精確。
    ② 用受控 tmp static dir 驗存在性有牙:真檔 → is_file True;缺檔 → is_file False。
    """
    sample = (
        "<html><head>\n"
        "<link href='/static/tokens.css?v=20260711' rel='stylesheet'>\n"
        "<link href='/static/missing.css' rel='stylesheet'>\n"
        "<link href='https://cdn.example/x.css' rel='stylesheet'>\n"
        "</head><body>\n"
        "<script src='/static/js/app.js?v=1#frag'></script>\n"
        "<script src='https://unpkg.com/lib.js'></script>\n"
        "<script src='relative/local.js'></script>\n"
        "<script>const inline = 1;</script>\n"
        "</body></html>\n"
    )
    ex = _AssetRefExtractor()
    ex.feed(sample)
    ex.close()
    # 6 個帶 src/href 的 tag(inline <script> 無 src 不計)。
    assert len(ex.refs) == 6, f"引用抽取數不符:{[r for _, r in ex.refs]}"

    # static-filter + query/frag strip 語義。
    resolved = [_resolve_static_ref(ref, tmp_path) for _line, ref in ex.refs]
    static_targets = [t for is_static, t in resolved if is_static and t is not None]
    # 只有 3 個 /static 引用(tokens.css / missing.css / js/app.js);外部與相對剔除。
    assert len(static_targets) == 3, f"static-filter 語義壞(外部/相對未剔除?):{static_targets}"
    names = sorted(t.name for t in static_targets)
    assert names == ["app.js", "missing.css", "tokens.css"], f"query/frag strip 語義壞:{names}"

    # 存在性有牙:在 tmp static dir 建真檔,缺檔仍應判不存在。
    (tmp_path / "tokens.css").write_text("/* x */", encoding="utf-8")
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_text("const a=1;", encoding="utf-8")
    by_name = {t.name: t for t in static_targets}
    assert by_name["tokens.css"].is_file(), "存在性檢查對真檔誤判不存在"
    assert by_name["app.js"].is_file(), "query-strip 後真檔路徑解析錯(app.js 應存在)"
    assert not by_name["missing.css"].is_file(), (
        "存在性檢查被架空:缺檔竟判存在(dangling 偵測無牙?)"
    )
