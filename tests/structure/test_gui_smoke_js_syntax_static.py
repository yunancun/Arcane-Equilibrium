"""P1.0 GUI smoke — 家族 (2)+(3):JS 檔與 inline <script> 的語法完整性守衛。

MODULE_NOTE(為何 node / 為何靜態):
  GUI 是 browser vanilla JS(全域函式、無 build step),語法正確性今日僅靠「手動
  node --check sign-off」保證,inline <script> 更是零覆蓋(最大盲區)。本檔把該手動
  gate 升為強制靜態 CI:用 pytest 殼出 `node --check`(鏡像
  test_gui_numeric_formatter_contract_static.py 的 subprocess+pytest.skip seam),
  只做**語法解析**——不載 DOM、不連 runtime/DB/WS、不執行副作用。缺 browser 全域
  (document/ocAuthCheck…)**不**造成假失敗;node 缺席則 graceful skip(與 formatter
  契約同前提)。純檔數/區塊數的 floor 斷言不需 node,永遠會跑。

  誠實邊界:綠只證「source 語法可解析」,不 attest runtime / 真 fetch / 三態真值;
  綠的靜態 smoke 不得被讀作「GUI works」(見 design/08_smoke_tests.md §4)。

設計正本:docs/execution_plan/gui_redesign/design/08_smoke_tests.md §2 家族 (2)+(3)。
anti-vacuous-green 紀律鏡像 test_gui_style_ratchet_static.py:每個掃描斷言含
「scanned-count 下限 + substantive-detector 錨點」,glob/extractor 壞掉時大聲 fail。
"""

from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)

NODE = shutil.which("node")

# ── inline <script> 的 type 分類 ──
# JS 宿主:空 type(browser 預設 script)或明確 JS type。node --check 做 syntax-only,
# module/script goal 差異不影響「粗語法錯」偵測(現行樹 0 個 module/json,由 substantive
# 合成測試釘死過濾語義)。
_JS_TYPES_OK = {"", "text/javascript", "application/javascript", "text/ecmascript", "module"}
# 非-JS 宿主:JSON 資料島 / 模板島,不是可執行 JS,不得送 node --check(否則假失敗)。
_NON_JS_TYPES = {
    "application/json",
    "application/ld+json",
    "text/html",
    "text/template",
    "text/x-template",
    "text/x-handlebars-template",
}

# top-level await 在 script goal 下是 SyntaxError(node --check 把 stdin 當 CommonJS wrapper)。
# 偵測此特徵後改包一層 async function 重驗(design/08 §2 impl 細節:wrap 擇一)。
# 這兩個標記是 V8/node 對「script 內 top-level await」的標準訊息,genuine 語法錯不含之。
_TLA_MARKERS = (
    "await is only valid",
    "Failed to load the ES module",
)


class _ScriptExtractor(HTMLParser):
    """抽 HTML 內的 inline <script>…</script> 區塊(帶 type)與外部 <script src>。

    convert_charrefs=False:script CDATA 內容取原始位元(勿把 &amp; 等當實體轉換),
    確保送 node 的是真 JS 原文。HTMLParser 對 script/style 走 CDATA 模式,handle_data
    收到完整 raw 內容直到 </script>。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.inline_blocks: list[tuple[int, str, str]] = []  # (line, type, code)
        self.src_refs: list[tuple[int, str]] = []  # (line, src)
        self._in_script = False
        self._cur_type = ""
        self._cur_start = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        d = {k.lower(): (v or "") for k, v in attrs}
        if "src" in d:
            self.src_refs.append((self.getpos()[0], d["src"]))
            return
        self._in_script = True
        self._cur_type = d.get("type", "").strip().lower()
        self._cur_start = self.getpos()[0]
        self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script:
            self.inline_blocks.append((self._cur_start, self._cur_type, "".join(self._buf)))
            self._in_script = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._buf.append(data)


def _rel(path: Path) -> str:
    return path.relative_to(STATIC_DIR).as_posix()


def _iter_js_files() -> list[Path]:
    """static/ 下全部 .js(頂層 + js/ 子目錄),排序穩定。"""
    return [p for p in sorted(STATIC_DIR.rglob("*.js")) if p.is_file()]


def _iter_inline_blocks() -> list[tuple[str, int, int, str]]:
    """收所有 HTML 內「JS 宿主且非空」的 inline <script> 區塊。

    回傳 (rel, block_index, line, code);block_index 是該檔第幾個 JS inline 區塊(1-based)。
    濾掉 type=module/json 之類與空白區塊(空白無語法可驗)。
    """
    out: list[tuple[str, int, int, str]] = []
    for html in sorted(STATIC_DIR.rglob("*.html")):
        if not html.is_file():
            continue
        ex = _ScriptExtractor()
        ex.feed(html.read_text(encoding="utf-8"))
        ex.close()
        idx = 0
        for line, typ, code in ex.inline_blocks:
            if typ in _NON_JS_TYPES:
                continue
            if typ not in _JS_TYPES_OK:
                continue
            if not code.strip():
                continue
            idx += 1
            out.append((_rel(html), idx, line, code))
    return out


JS_FILES = _iter_js_files()
INLINE_BLOCKS = _iter_inline_blocks()

_JS_IDS = [_rel(p) for p in JS_FILES]
_BLOCK_IDS = [f"{rel}#{idx}@L{line}" for (rel, idx, line, _code) in INLINE_BLOCKS]


def _node_check_file(path: Path) -> tuple[int, str]:
    p = subprocess.run(
        ["node", "--check", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.returncode, p.stderr


def _node_check_stdin(code: str) -> tuple[int, str]:
    p = subprocess.run(
        ["node", "--check", "-"],
        input=code,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.returncode, p.stderr


def _check_inline_block(code: str) -> tuple[bool, str]:
    """語法檢查單一 inline 區塊;top-level await 特徵則包 async 重驗。

    回傳 (ok, detail)。ok=False 時 detail 帶 node stderr 尾段供點名。
    """
    rc, err = _node_check_stdin(code)
    if rc == 0:
        return True, ""
    if any(m in err for m in _TLA_MARKERS):
        rc2, err2 = _node_check_stdin("async function __smoke__(){\n" + code + "\n}")
        if rc2 == 0:
            return True, ""  # TLA-tolerated:包 async 後語法合法
        return False, err2.strip()
    return False, err.strip()


# ─────────────────────────── 家族 (2):每 JS 檔 node --check ───────────────────────────


def test_js_files_scanned_floor() -> None:
    """掃描面下界(不需 node):防 rglob 壞掉/掃到空目錄導致家族(2)空洞綠。

    現況 33 檔(30 頂層 + 3 js/)。floor=30 留裁併/拆檔餘裕但排除歸零。
    """
    assert len(JS_FILES) >= 30, (
        f"static/ 下 .js 掃描檔數異常少(scanned={len(JS_FILES)}),rglob 路徑或副檔名過濾疑壞掉"
    )


@pytest.mark.skipif(NODE is None, reason="node 不可用;JS 語法守衛需 node --check(與 formatter 契約同前提)")
@pytest.mark.parametrize("js_path", JS_FILES, ids=_JS_IDS)
def test_js_file_passes_node_check(js_path: Path) -> None:
    """每個 .js 檔必須通過 `node --check`(手動 sign-off gate 升為強制 CI)。"""
    rc, err = _node_check_file(js_path)
    assert rc == 0, f"node --check 失敗:{_rel(js_path)}\n{err.strip()}"


# ─────────────────────── 家族 (3):每 inline <script> node --check ───────────────────────


def test_inline_scripts_scanned_floor() -> None:
    """掃描面下界(不需 node):防 HTMLParser 抽取壞掉導致家族(3)零區塊空洞綠。

    現況 51 個 JS inline 區塊(tab-phase4 一檔就多個)。floor=40 排除歸零/大幅漏抽。
    """
    assert len(INLINE_BLOCKS) >= 40, (
        f"HTML inline <script> 抽取數異常少(scanned={len(INLINE_BLOCKS)}),HTMLParser 抽取疑壞掉"
    )


@pytest.mark.skipif(NODE is None, reason="node 不可用;inline <script> 語法守衛需 node --check")
@pytest.mark.parametrize("block", INLINE_BLOCKS, ids=_BLOCK_IDS)
def test_inline_script_passes_node_check(block: tuple[str, int, int, str]) -> None:
    """每個 inline <script> 區塊語法可解析(top-level await 以 async-wrap 容忍)。"""
    rel, idx, line, code = block
    ok, detail = _check_inline_block(code)
    assert ok, f"inline <script> 語法失敗:{rel} 第{idx}個區塊 @L{line}\n{detail}"


# ─────────────────────────── anti-vacuous-green 錨點(substantive) ───────────────────────────


@pytest.mark.skipif(NODE is None, reason="node 不可用;無法驗 node --check 有牙")
def test_node_check_and_tla_logic_are_substantive() -> None:
    """釘死「node --check + TLA-wrap」真的會判罪/赦免:防檢查器被架空成恆綠。

    若 _node_check_* 被改成永遠 rc=0(如 mock 掉 subprocess),家族(2)(3)全綠但零守衛。
    這裡用合成正反例把語義釘死(= red-proof 內建,不只一次性人工注入)。
    """
    # 正例:合法 JS → rc 0。
    rc_ok, _ = _node_check_stdin("const a = 1; function f(){ return a; }\n")
    assert rc_ok == 0, "node --check 對合法 JS 竟非零(檢查器語義壞?)"

    # 反例:壞語法 → rc 非零(有牙)。
    rc_bad, err_bad = _node_check_stdin("function f( { return 1 }\n")
    assert rc_bad != 0, "node --check 對壞語法竟回 0(檢查器被架空成恆綠?)"
    assert "SyntaxError" in err_bad, f"壞語法未回報 SyntaxError:{err_bad!r}"

    # TLA:as-is 應失敗且帶 TLA 標記;包 async 後應合法 → _check_inline_block 判 ok。
    tla = "const r = await fetch('/x');\n"
    rc_tla, err_tla = _node_check_stdin(tla)
    assert rc_tla != 0, "top-level await(script goal)竟通過 as-is(node 行為變更?)"
    assert any(m in err_tla for m in _TLA_MARKERS), f"TLA 未帶預期標記:{err_tla!r}"
    ok_tla, _ = _check_inline_block(tla)
    assert ok_tla, "TLA 區塊包 async 後仍判失敗(wrap 邏輯壞?)"

    # 但「真壞語法」不因 wrap 被赦免:_check_inline_block 對非-TLA 壞語法仍判罪。
    ok_bad, _ = _check_inline_block("function f( { return 1 }\n")
    assert not ok_bad, "真語法錯被 _check_inline_block 誤赦免(wrap 邏輯過寬?)"


def test_inline_extractor_is_substantive() -> None:
    """釘死 _ScriptExtractor 的抽取/type 過濾語義:防抽取被改成恆空 → 家族(3)空洞綠。

    合成 HTML 含:2 個合法 inline JS、1 個 <script src>、1 個 type=module、1 個
    type=application/json 資料島、1 個空 inline。斷言抽取數與過濾後可驗數精確。
    """
    sample = (
        "<html><head>\n"
        "<script src='/static/x.js'></script>\n"
        "<script type='application/json' id='cfg'>{\"a\":1}</script>\n"
        "</head><body>\n"
        "<script>const a = 1;</script>\n"
        "<script type='module'>const b = 2;</script>\n"
        "<script>   </script>\n"
        "<script>function g(){ return 42; }</script>\n"
        "</body></html>\n"
    )
    ex = _ScriptExtractor()
    ex.feed(sample)
    ex.close()

    # 原始抽取:5 個 inline 區塊(含 json/module/空白)+ 1 個 src。
    assert len(ex.inline_blocks) == 5, f"inline 區塊抽取數不符:{len(ex.inline_blocks)}"
    assert len(ex.src_refs) == 1, f"src 抽取數不符:{len(ex.src_refs)}"
    assert ex.src_refs[0][1] == "/static/x.js"

    # 套用家族(3)的過濾規則:json 資料島剔除、空白剔除;module/普通 JS 保留 → 3 個可驗。
    checkable = [
        (typ, code)
        for (_line, typ, code) in ex.inline_blocks
        if typ not in _NON_JS_TYPES and typ in _JS_TYPES_OK and code.strip()
    ]
    assert len(checkable) == 3, f"過濾後可驗 JS 區塊數不符(應含 module,排除 json/空白):{checkable}"
    types = sorted(t for t, _ in checkable)
    assert types == ["", "", "module"], f"type 過濾語義壞:{types}"
