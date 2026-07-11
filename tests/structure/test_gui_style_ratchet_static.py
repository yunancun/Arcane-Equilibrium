from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)

# token 正本 / 舊名映射層 / 工具集正本:裸 hex 與 class 的合法宿主,永不納入 ratchet。
# styles.css 刻意「不」在此(它是 C6e defer Phase3 的殘量宿主,納入 ratchet 逐步收斂)。
SKIP_CSS = {"tokens.css", "tokens-compat.css", "oc-utilities.css"}

# ── 三個 ratchet 維度的量測正則(baseline 與執行期以同一組正則量測,勿單邊改)──
# 1) inline style 屬性:HTML / JS 模板字串內的 style="..." 或 style='...'。
#    前置 (?<![\w-]) 排除 fontStyle= 之類誤命中。JS 的 .style.setProperty('--x', …) 與
#    .style.<prop> = … 是 scoped-var 正法,不含 style=" 字面 → 本就不匹配,無須豁免清單。
STYLE_ATTR_RE = re.compile(r"""(?<![\w-])style\s*=\s*["']""")
# 2) <style> 塊開標籤(不含 </style>);Phase0 iframe 過渡白名單,殼層(index/common)須維持 0。
STYLE_BLOCK_RE = re.compile(r"<style[\s>]", re.IGNORECASE)
# 3) 裸 hex 色值 #rgb / #rgba / #rrggbb / #rrggbbaa(長度優先,後接非 hex 才收,避免吞長識別碼)。
HEX_RE = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)

DIMENSIONS: dict[str, re.Pattern[str]] = {
    "hex": HEX_RE,
    "style_attr": STYLE_ATTR_RE,
    "style_block": STYLE_BLOCK_RE,
}

# ── baseline 快照(2026-07-11 實測;掃 61 檔,總計 hex=237 / style_attr=5 / style_block=32)──
# 只列「非零」檔;未列檔三維預設全 0(= 禁任何裸 hex / inline style / <style> 新增)。
# 這是 ratchet 上界:某檔某維 > 此值即回歸失敗;清污使某維下降不失敗(可留可移,非必須)。
# 現存合法保留來源:styles.css 殼層殘量(C6e defer Phase3)、console/trading legacy(Phase3)、
# app-learning 孤兒(Phase2)、各 tab per-page <style>(Phase0 iframe 白名單)、
# 卡片/JS 模板的 var(--x,#hex) fallback 與 --x: scoped-var、strategy 身份色。
BASELINE: dict[str, dict[str, int]] = {
    "app-learning.js": {"hex": 16, "style_attr": 2, "style_block": 0},
    "app-paper.js": {"hex": 0, "style_attr": 0, "style_block": 0},
    "canary-tab.js": {"hex": 0, "style_attr": 1, "style_block": 0},
    "cards/dl3_card.html": {"hex": 0, "style_attr": 0, "style_block": 0},
    "cards/linucb_card.html": {"hex": 0, "style_attr": 2, "style_block": 0},
    "cards/news_card.html": {"hex": 0, "style_attr": 0, "style_block": 0},
    "cards/teacher_card.html": {"hex": 0, "style_attr": 0, "style_block": 0},
    "common-formatters.js": {"hex": 0, "style_attr": 0, "style_block": 0},
    "common.js": {"hex": 5, "style_attr": 0, "style_block": 0},
    "console.html": {"hex": 12, "style_attr": 0, "style_block": 1},
    "handoff_helper.js": {"hex": 3, "style_attr": 0, "style_block": 0},
    "login.html": {"hex": 1, "style_attr": 0, "style_block": 1},
    "risk-tab.js": {"hex": 1, "style_attr": 0, "style_block": 1},
    "styles.css": {"hex": 119, "style_attr": 0, "style_block": 1},
    "tab-agents.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-ai.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-demo.html": {"hex": 1, "style_attr": 0, "style_block": 2},
    "tab-development.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-earn.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-edge-gates.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-governance.html": {"hex": 7, "style_attr": 0, "style_block": 2},
    "tab-learning.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-live.html": {"hex": 2, "style_attr": 0, "style_block": 1},
    "tab-live.js": {"hex": 1, "style_attr": 0, "style_block": 0},
    "tab-monitoring.html": {"hex": 0, "style_attr": 0, "style_block": 3},
    "tab-paper.html": {"hex": 8, "style_attr": 0, "style_block": 1},
    "tab-phase4.html": {"hex": 8, "style_attr": 0, "style_block": 2},
    "tab-replay.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-risk.html": {"hex": 4, "style_attr": 0, "style_block": 2},
    "tab-settings.html": {"hex": 1, "style_attr": 0, "style_block": 3},
    "tab-stock-etf.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-strategy.html": {"hex": 0, "style_attr": 0, "style_block": 1},
    "tab-system.html": {"hex": 0, "style_attr": 0, "style_block": 2},
    "trading.html": {"hex": 14, "style_attr": 0, "style_block": 1},
}

_GUIDE = (
    "修復指引:新增裸 hex 或 inline style / <style> 塊 = P0.2/C6 清污回歸。\n"
    "  · 色值改用 tokens.css 的語義 token(var(--…));版式改用 oc-utilities.css class。\n"
    "  · 見 gui-style-guide skill 與 docs/execution_plan/gui_redesign/design/05_utilities.md。\n"
    "  · 若確為必要的合法保留/defer,更新本檔 BASELINE 對應檔的該維數值並在此註明理由。"
)


def _iter_scanned_files():
    """遍歷 static/ 的受管面:所有 .html / .js,加入 ratchet 的 .css(排除 token 正本)。"""
    for path in sorted(STATIC_DIR.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".css":
            if path.name in SKIP_CSS:
                continue
        elif suffix not in {".html", ".js"}:
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(STATIC_DIR).as_posix()


def _measure(text: str) -> dict[str, int]:
    return {dim: len(rx.findall(text)) for dim, rx in DIMENSIONS.items()}


def test_gui_style_ratchet_no_new_inline_style_or_bare_hex() -> None:
    """P0.6 baseline-ratchet:static/ 受管面每檔三維(hex / style_attr / style_block)不得超 baseline。

    P0.2(inline style 清零)+ C6(hex→token)清污後,現狀仍有合法保留/defer 的裸 hex 與
    per-page <style>(見 BASELINE 註解)。硬禁會全紅,故用 ratchet:每檔當前計數即上界,
    只在「新增」時失敗;清污(下降)不失敗。這把「不得再手寫裸色值 / inline style」變機械可查。
    """
    offenders: list[str] = []
    scanned = 0
    for path in _iter_scanned_files():
        scanned += 1
        rel = _rel(path)
        base = BASELINE.get(rel, {})
        counts = _measure(path.read_text(encoding="utf-8"))
        for dim in DIMENSIONS:
            current = counts[dim]
            allowed = base.get(dim, 0)
            if current > allowed:
                offenders.append(
                    f"{rel} [{dim}] 當前 {current} > baseline {allowed}"
                )
    # 掃描面下界:防「掃描路徑壞掉/掃到空目錄」導致 ratchet 空洞綠(現況 61 檔)。
    assert scanned >= 50, (
        f"受管 GUI 面掃描檔數異常少(scanned={scanned}),掃描路徑或副檔名過濾疑壞掉"
    )
    assert not offenders, (
        "GUI style ratchet 回歸(某檔某維超出 baseline,= 新增裸 hex / inline style / <style>):\n"
        + "\n".join(offenders)
        + "\n"
        + _GUIDE
    )


def test_gui_style_ratchet_detectors_are_substantive() -> None:
    """正常路徑錨點(gate 雙向):量測正則本身必須真的會命中,防「正則被改成永不命中→ratchet 空洞綠」。

    若三條正則任一被改壞成 findall 恆空,主測試每檔計數皆 0 ≤ baseline → 永遠綠但零守衛。
    這裡用合成正反例把正則語義釘死;同時錨定 baseline 尚有實質存量(總 hex/塊數不為零),
    確保清污進行中仍能區分「regex 壞掉」與「真的清乾淨」。
    """
    # hex:三/四/六/八位命中;兩位過短、非 hex 字母不命中;長識別碼不被吞成色值。
    assert HEX_RE.findall("#fff #aabb #12ab56 #12345678") == [
        "#fff",
        "#aabb",
        "#12ab56",
        "#12345678",
    ], "HEX_RE 未正確命中 3/4/6/8 位裸 hex"
    assert HEX_RE.findall("#12 #ghijkl") == [], "HEX_RE 誤命中過短或非 hex 串"
    assert HEX_RE.findall("#deadbeefcafe") == [], "HEX_RE 誤把長 hex 識別碼當色值吞"

    # style_attr:HTML 屬性命中;JS 的 .style.setProperty / .style.prop = 不命中(scoped-var 正法)。
    assert STYLE_ATTR_RE.search('<div style="color:#fff">'), "STYLE_ATTR_RE 未命中 inline style"
    assert STYLE_ATTR_RE.search("<i style='x'>"), "STYLE_ATTR_RE 未命中單引號 inline style"
    assert not STYLE_ATTR_RE.search("el.style.setProperty('--w', v)"), (
        "STYLE_ATTR_RE 誤命中 .style.setProperty scoped-var 正法"
    )
    assert not STYLE_ATTR_RE.search("el.style.width = v"), (
        "STYLE_ATTR_RE 誤命中 .style.<prop> = scoped-var 正法"
    )
    assert not STYLE_ATTR_RE.search('fontStyle="italic"'), "STYLE_ATTR_RE 誤命中 fontStyle="

    # style_block:開標籤命中(含帶屬性),閉標籤不命中。
    assert STYLE_BLOCK_RE.search("<style>"), "STYLE_BLOCK_RE 未命中 <style>"
    assert STYLE_BLOCK_RE.search('<style type="text/css">'), "STYLE_BLOCK_RE 未命中帶屬性 <style>"
    assert not STYLE_BLOCK_RE.search("</style>"), "STYLE_BLOCK_RE 誤命中 </style> 閉標籤"

    # baseline 尚有實質存量(清污全綠前不應為零),與檔數下界共同排除空洞綠。
    tot_hex = sum(v.get("hex", 0) for v in BASELINE.values())
    tot_block = sum(v.get("style_block", 0) for v in BASELINE.values())
    assert tot_hex >= 150, f"baseline 總 hex 存量異常({tot_hex}),疑 baseline 被清空"
    assert tot_block >= 20, f"baseline 總 <style> 塊數異常({tot_block})"
