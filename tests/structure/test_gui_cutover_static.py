"""P1.2 cutover plumbing 靜態不變量守衛 — /console → 玄衡新殼 cutover 的回滾陷阱防護。

MODULE_NOTE（為何靜態 / 為何純 stdlib）：
  cutover 把 /console 由 console.html 改為條件服 shell.html（flag=1），並新增 /console/legacy
  永久逃生口。alignment / asset-ref / style-ratchet 三組 glob smoke「不覆蓋路由 return 哪個檔」，
  也不覆蓋 fallback 連結指向，故此空隙需一條專責結構守衛：
    ① gui_legacy_routes.py：/console/legacy 逃生口路由存在 + OPENCLAW_GUI_SHELL_DEFAULT
       cutover flag-gate + console_index 與 console_legacy 皆保留 _redirect_if_unauthenticated
       守衛（auth 零弱化，不引入未守衛的檔案暴露路徑）。
    ② shell.html：兩條 fallback 連結指 /console/legacy（非裸 /console），防 cutover 態下
       fallback 指回自身的無限迴圈（orphan legacy，design/14 §6.2 回滾陷阱）。
  純 Python ast + HTMLParser 靜態解析，零 runtime、零 app import。

  誠實邊界：綠只證源碼結構不變量成立；「/console 實際 return 哪個檔 / flag 真生效 / curl 三態」
  = runtime 事實（NEEDS-LINUX；route 改動需 app 重啟才生效，見 design/14 §6.3）。

  anti-vacuous-green 紀律鏡像 test_gui_smoke_asset_refs_static.py：extractor 壞掉時大聲 fail
  （substantive-detector 合成正反例把解析與守衛偵測語義釘死）。

設計正本：docs/execution_plan/gui_redesign/design/14_p1_2_wiring_and_cutover.md §6.2 / §6.4。
"""

from __future__ import annotations

import ast
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app"
ROUTES_PY = APP_DIR / "gui_legacy_routes.py"
SHELL_HTML = APP_DIR / "static/shell.html"

_GUARD_CALL = "_redirect_if_unauthenticated"
_CUTOVER_FLAG = "OPENCLAW_GUI_SHELL_DEFAULT"


def _route_source_segments(source: str) -> dict[str, str]:
    """解析 route module 源碼，回傳 {route_path: 該 handler 的源碼片段}。

    只收 @<x>.get("<path>") 裝飾的 FunctionDef；path 取第一個位置字面參數。
    以 handler 源碼片段作後續守衛/flag 偵測的載體（片段內含 = 有牙）。
    """
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get"):
                continue
            if not dec.args:
                continue
            first = dec.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            seg = ast.get_source_segment(source, node)
            if seg is not None:
                out[first.value] = seg
    return out


class _AnchorHrefExtractor(HTMLParser):
    """抽 <a href> 值（帶行號）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.hrefs: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        d = {k.lower(): (v or "") for k, v in attrs}
        if "href" in d:
            self.hrefs.append((self.getpos()[0], d["href"]))


def _anchor_hrefs_from(text: str) -> list[tuple[int, str]]:
    ex = _AnchorHrefExtractor()
    ex.feed(text)
    ex.close()
    return ex.hrefs


def _norm(href: str) -> str:
    """剝除 ?query 與 #frag，取純路徑用於比對。"""
    return href.split("?", 1)[0].split("#", 1)[0]


_SEGMENTS = _route_source_segments(ROUTES_PY.read_text(encoding="utf-8"))
_SHELL_CONSOLE_HREFS = [
    (line, href)
    for (line, href) in _anchor_hrefs_from(SHELL_HTML.read_text(encoding="utf-8"))
    if href.startswith("/console")
]


def test_route_extractor_scanned_floor() -> None:
    """掃描面下界：防 ast 解析壞掉導致零路由空洞綠（現況 7 條 @app.get）。"""
    assert len(_SEGMENTS) >= 6, (
        f"gui_legacy_routes.py 抽到的 @app.get 路由數異常少（{sorted(_SEGMENTS)}），ast 解析疑壞掉"
    )


def test_console_legacy_route_exists_and_guarded() -> None:
    """/console/legacy 永久逃生口存在，且逐字複用未弱化的 auth 守衛。"""
    assert "/console/legacy" in _SEGMENTS, (
        "cutover orphan 風險：gui_legacy_routes.py 缺 /console/legacy 永久逃生口路由。"
    )
    seg = _SEGMENTS["/console/legacy"]
    assert _GUARD_CALL in seg, (
        f"/console/legacy 未複用 {_GUARD_CALL} 守衛 = 未守衛的檔案暴露路徑（auth 弱化）。"
    )
    assert "console.html" in seg, "/console/legacy 應無條件服 console.html。"


def test_console_index_flag_gated_and_guard_retained() -> None:
    """/console 具 cutover flag-gate（服 shell/console 兩檔）且保留原 auth 守衛。"""
    assert "/console" in _SEGMENTS, "gui_legacy_routes.py 缺 /console 路由。"
    seg = _SEGMENTS["/console"]
    assert _CUTOVER_FLAG in seg, f"/console 缺 {_CUTOVER_FLAG} cutover flag-gate。"
    assert "shell.html" in seg, "/console flag=1 分支應服 shell.html。"
    assert "console.html" in seg, "/console default 分支應服 console.html（default OFF）。"
    assert _GUARD_CALL in seg, f"/console 的 {_GUARD_CALL} 守衛被移除 = auth 弱化。"


def test_shell_fallback_links_point_to_legacy_not_bare_console() -> None:
    """shell.html 的 legacy fallback 連結指 /console/legacy（非裸 /console）。

    cutover(flag=1)後 /console=shell.html；若 fallback 仍指裸 /console 會回殼無限迴圈。
    """
    assert len(_SHELL_CONSOLE_HREFS) >= 2, (
        f"shell.html 指向 /console* 的 fallback 連結數異常少（{_SHELL_CONSOLE_HREFS}），"
        "HTMLParser 抽取疑壞掉或 fallback 連結被移除。"
    )
    bare = [(line, href) for (line, href) in _SHELL_CONSOLE_HREFS if _norm(href) == "/console"]
    assert not bare, (
        "cutover orphan 風險：shell.html 仍有 fallback 連結指裸 /console（cutover 後回殼無限迴圈）：\n"
        + "\n".join(f"  L{line}: {href}" for line, href in bare)
        + "\n  → 應改指 /console/legacy 永久逃生口。"
    )
    for line, href in _SHELL_CONSOLE_HREFS:
        assert _norm(href) == "/console/legacy", (
            f"shell.html L{line} fallback href={href} 非預期 /console/legacy。"
        )


def test_extractors_are_substantive() -> None:
    """釘死 route ast 抽取 + anchor 抽取 + 守衛偵測語義：防抽取恆空/檢查被架空成恆綠。"""
    # ① route 抽取：合成含守衛與缺守衛兩 handler + 一條 POST，驗 path→segment 對應與過濾精確。
    sample_py = (
        "def register(app):\n"
        "    @app.get('/guarded', include_in_schema=False)\n"
        "    def a(request):\n"
        "        redirect = _redirect_if_unauthenticated(request)\n"
        "        if redirect is not None:\n"
        "            return redirect\n"
        "        return FileResponse('console.html')\n"
        "    @app.get('/naked')\n"
        "    def b(request):\n"
        "        return FileResponse('shell.html')\n"
        "    @app.post('/notget')\n"
        "    def c():\n"
        "        return 1\n"
    )
    segs = _route_source_segments(sample_py)
    assert set(segs) == {"/guarded", "/naked"}, f"route 抽取（僅 .get）語義壞：{sorted(segs)}"
    assert _GUARD_CALL in segs["/guarded"], "守衛偵測對含守衛 handler 誤判缺守衛"
    assert _GUARD_CALL not in segs["/naked"], "守衛偵測被架空：對缺守衛 handler 誤判有守衛"

    # ② anchor 抽取 + startswith 過濾 + norm strip 語義。
    sample_html = (
        "<a href='/console' title='x'>舊</a>\n"
        "<a href='/console/legacy'>返回</a>\n"
        "<a href='https://x/console'>外部</a>\n"
        "<a href='/console?v=1'>帶query</a>\n"
    )
    console_hrefs = [h for _l, h in _anchor_hrefs_from(sample_html) if h.startswith("/console")]
    assert console_hrefs == ["/console", "/console/legacy", "/console?v=1"], (
        f"anchor 抽取 / startswith 過濾語義壞（外部 https 應剔除）：{console_hrefs}"
    )
    assert _norm("/console?v=1#f") == "/console", "norm query/frag strip 語義壞"
    assert _norm("/console/legacy") == "/console/legacy", "norm 誤傷正常路徑"
