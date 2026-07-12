from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# MODULE_NOTE — 雙主題(玄夜/帛晝)AA 對比 ratchet 靜態測試(P1.3 item ③)
# ═══════════════════════════════════════════════════════════════════════════
# 用途:把「兩主題 token-pair 的 WCAG 對比達 AA」變成純算術、零 runtime/DOM/
#   瀏覽器的 CI gate。設計正本 = docs/execution_plan/gui_redesign/design/
#   12_p1_3_dual_theme.md §5(§5.1 結構 / §5.2 pair 清單 / §5.3 閾值 / §5.4
#   anti-vacuous)+ 附錄 WCAG 公式。
#
# 公式(WCAG 2.x,附錄逐位吻合):
#   · gamma 展開 C' = C/255; c<=0.03928 ? c/12.92 : ((c+0.055)/1.055)^2.4
#   · 相對亮度 L = 0.2126·R' + 0.7152·G' + 0.0722·B'
#   · 對比 contrast = (L_hi + 0.05) / (L_lo + 0.05)
#   · α 合成 out = α·fg + (1−α)·parent(逐通道;疊 overlay 得實色)
#   自檢錨:黑/白 = 21.00、同色 = 1.00。
#
# baseline 紀律(§5.3 選 (a)):P1.3-a retune 先於本 test 上線 → 上線即全綠。
#   帛晝 AA retune(--warn #7A5200 / --live #BE1E27 / --pos #166B4C /
#   --neg #A83232 及對應 *-bg)+ 4 個 --ov-*-rgb overlay 三元組已 land,
#   本 test 只鎖不放寬。玄夜三元組 = 原冷底字面 byte-identical(§5.4 錨 ⑤)。
#
# PM 裁決(2026-07-12)後,兩條 <閾值 pair 三分類(不改 tokens.css 值):
#   · #16 玄夜 --neg 在最亮暗底 --bg-raised = 4.287 < 4.5 → frozen-PENDING(見 _PENDING)。
#     PRE-EXISTING 玄夜 gap:--neg #E5484D 與 --bg-raised #241B1F 皆玄夜既有值,
#     P1.3 retune 只動帛晝、未改玄夜 → 非 P1.3 回歸,本測試首次量化揭示。canon-9
#     active-theme 值+salience,歸 A3 runtime 走查 gate(brighten vs accept
#     bold-PnL tolerance),併「解 data-theme 釘死前 A3+Linux runtime」downstream。
#   · #25 帛晝 --border-strong(rgba(34,27,24,.26))在 --bg-app ≈ 1.716 < 3.0 →
#     WCAG 1.4.11 裝飾髮絲線豁免(_DECORATIVE_EXEMPT):26% alpha 髮絲線物理上限
#     ~1.74,threshold=3.0 對純裝飾邊框係 pair-def 錯誤 → 非 AA 目標、非待修。
#     移出 enforced、移出 _PENDING,只留 informational 記錄供追溯。
#
# ratchet 面向:本檔在 tests/,不在 static/;GUI style ratchet
#   (test_gui_style_ratchet_static.py)只掃 static/ 受管面,不掃本檔 →
#   本檔 PAIRS/預期值裡的 #hex 是測試資料,非 ratchet 違規。
# ═══════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS_CSS = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tokens.css"
)

THRESH_TEXT = 4.5  # 文字級 AA(§5.3)
THRESH_UI = 3.0  # UI/圖形級 AA(§5.3)
_EPS = 1e-9

# ── 玄夜 overlay 三元組的 byte-parity 錨(§5.4 ⑤;改壞玄夜值即紅)──
_DARK_OV_LITERALS: dict[str, tuple[int, int, int]] = {
    "ov-panel-rgb": (13, 17, 23),
    "ov-panel-b-rgb": (22, 27, 34),
    "ov-accent-rgb": (56, 139, 253),
    "ov-muted-rgb": (139, 148, 158),
}

# ── 兩主題各須存在的 gate token(§5.4 ②;缺任一 → FAIL,防 parser 靜默漏)──
_GATE_TOKENS = (
    "ov-panel-rgb",
    "ov-panel-b-rgb",
    "ov-accent-rgb",
    "ov-muted-rgb",
    "warn",
    "live",
    "seal",
    "text-muted",
    "text-primary",
    "text-secondary",
    "pos",
    "neg",
    "bg-app",
    "bg-surface",
    "bg-raised",
)

# ── PENDING(frozen-pending;凍結集,防隱性紅膨脹或靜默清空)──
# n → 該 pair 的「實算 vs spec」對照與 gate 歸屬,僅記錄不 hard-assert;
# test_pending_set_is_frozen_and_reported 會再算一次並確保集合恰為此。
# PM 裁決(2026-07-12):僅 #16 保留 pending(#25 已改判裝飾豁免,見 _DECORATIVE_EXEMPT)。
_PENDING: dict[int, str] = {
    16: (
        "PRE-EXISTING 玄夜 --neg on --bg-raised 4.287<4.5;--neg #E5484D 與 --bg-raised "
        "#241B1F 皆玄夜既有值,P1.3 retune 只動帛晝、未改玄夜 → 非 P1.3 回歸,本測試首次量化"
        "揭示。canon-9 active-theme 值+salience,歸 A3 runtime 走查 gate 決(brighten vs "
        "accept bold-PnL tolerance);併「解 data-theme 釘死前 A3+Linux runtime 走查」"
        "downstream。E4 不擅改玄夜值。"
    ),
}

# ── WCAG 1.4.11 裝飾豁免(非 enforced、非 pending、非待修;informational 記錄供追溯)──
# PM 裁決(2026-07-12):--border-strong = rgba(34,27,24,.26) 是 26% alpha 髮絲線
# (canon 5:海拔靠亮度+髮絲線,不靠陰影),純裝飾分隔線非 UI-component 邊界 →
# WCAG 1.4.11 明確豁免 3:1。26% alpha 疊自身底物理上限 ~1.74,故 threshold=3.0 對
# 此 pair 係「定義錯誤」,不作 enforced pair、亦不列 _PENDING(它不會被「修」到 ≥3.0)。
# 快照 = composite(rgba(34,27,24,.26) over 底) 之實色 vs 底(可用本檔合成器復算)。
_DECORATIVE_EXEMPT: dict[str, str] = {
    "--border-strong on --bg-app (帛晝)": "measured≈1.716;WCAG 1.4.11 裝飾髮絲線豁免,非 AA 目標",
    "--border-strong on --bg-raised (玄夜)": "measured≈1.867;同上裝飾豁免",
}


# ═══ Parser(§5.1)═══════════════════════════════════════════════════════════

# 帛晝 base = 頂層 `:root{…}`(`:root` 後緊接可選空白再 `{`;`:root[`/`:root:` 不匹配)。
_BASE_RE = re.compile(r":root\s*\{([^}]*)\}")
# 玄夜 = 顯式 toggle 態 `:root[data-theme="dark"]{…}`(權威,與 @media 塊同值)。
_DARK_RE = re.compile(r':root\[data-theme="dark"\]\s*\{([^}]*)\}')
# 宣告:--name: value;(值取到首個 `;`;不吞相鄰註釋/宣告)。
_DECL_RE = re.compile(r"--([A-Za-z0-9-]+)\s*:\s*([^;]+);")

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_TRIPLE_RE = re.compile(r"^\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*$")
_RGBA_RE = re.compile(
    r"^\s*rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)\s*$"
)
_VAR_RE = re.compile(r"^\s*var\(\s*--([A-Za-z0-9-]+)\s*\)\s*$")


def _decls(block: str) -> dict[str, str]:
    """從單一 CSS 塊體抽 --name→value(去空白)。"""
    return {name: val.strip() for name, val in _DECL_RE.findall(block)}


def _load_themes() -> dict[str, dict[str, str]]:
    """讀 tokens.css,回傳 {"light": 帛晝 base dict, "dark": 玄夜 dict}。缺檔/缺塊 → skip。"""
    if not TOKENS_CSS.exists():
        pytest.skip(f"tokens.css 不存在(dev 環境未拉 GUI 檔?):{TOKENS_CSS}")
    css = TOKENS_CSS.read_text(encoding="utf-8")
    base_m = _BASE_RE.search(css)
    dark_m = _DARK_RE.search(css)
    if base_m is None or dark_m is None:
        pytest.skip("tokens.css 缺 :root{} 或 :root[data-theme=\"dark\"]{} 塊,結構已變")
    return {"light": _decls(base_m.group(1)), "dark": _decls(dark_m.group(1))}


# ═══ 值解析器(§5.1)═════════════════════════════════════════════════════════


def parse_hex(value: str) -> tuple[int, int, int]:
    m = _HEX_RE.match(value.strip())
    if not m:
        raise ValueError(f"非法 hex:{value!r}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def token_triple(theme: dict[str, str], name: str) -> tuple[int, int, int]:
    """--ov-*-rgb 逗號三元組 → (r,g,b)。"""
    m = _TRIPLE_RE.match(theme[name])
    if not m:
        raise ValueError(f"token {name} 非三元組:{theme[name]!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def token_rgb(theme: dict[str, str], name: str) -> tuple[int, int, int]:
    """實色 token → (r,g,b);支援 #hex 與 var(--x) 後備展開。"""
    value = theme[name].strip()
    if value.startswith("#"):
        return parse_hex(value)
    vm = _VAR_RE.match(value)
    if vm:
        return token_rgb(theme, vm.group(1))
    raise ValueError(f"token {name} 非可解析實色:{value!r}")


def token_alpha_color(theme: dict[str, str], name: str) -> tuple[tuple[int, int, int], float]:
    """rgba token → ((r,g,b), α)。"""
    m = _RGBA_RE.match(theme[name])
    if not m:
        raise ValueError(f"token {name} 非 rgba:{theme[name]!r}")
    return ((int(m.group(1)), int(m.group(2)), int(m.group(3))), float(m.group(4)))


# ═══ WCAG 合成器 + 對比(§5.1 / 附錄)═══════════════════════════════════════


def composite(
    fg: tuple[float, float, float], alpha: float, parent: tuple[float, float, float]
) -> tuple[float, float, float]:
    """α over parent:out = α·fg + (1−α)·parent(逐通道)。"""
    return tuple(alpha * f + (1.0 - alpha) * p for f, p in zip(fg, parent))


def rel_luminance(rgb: tuple[float, float, float]) -> float:
    def expand(c: float) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    r, g, b = (expand(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1: tuple[float, float, float], c2: tuple[float, float, float]) -> float:
    l1, l2 = rel_luminance(c1), rel_luminance(c2)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def contrast_hex(hex1: str, hex2: str) -> float:
    """便捷:兩個 #hex 直接對比(§5.4 ① 自檢用)。"""
    return contrast(parse_hex(hex1), parse_hex(hex2))


# ═══ PAIRS 清單(§5.2,全 25 條)══════════════════════════════════════════════
# 欄位:n / theme / fg / bg(層鏈,外層在前、base 在末)/ need / enforced / desc。
#   fg:  ("solid", token)            — 實色前景(現行 pair 全為實色;半透明裝飾邊框
#                                      走 WCAG 1.4.11 豁免 _DECORATIVE_EXEMPT,不列 pair)
#   bg 層:("base", token)                 — 底色實色(鏈末唯一)
#          ("overlay", ov-triple-token, α) — RGB 三元組 α 疊於下層
#          ("alpha_token", rgba-token)     — rgba token(自帶 α)疊於下層
# worst-case 背景(§5.2):帛晝取最深平底 --bg-app;玄夜取最亮暗底 --bg-raised。

Pair = dict


def _P(n, theme, fg, bg, need, desc, enforced=True) -> Pair:
    return {
        "n": n,
        "theme": theme,
        "fg": fg,
        "bg": bg,
        "need": need,
        "enforced": enforced,
        "desc": desc,
    }


PAIRS: list[Pair] = [
    # ── 文字級 ≥4.5(#1–19)──
    _P(1, "light", ("solid", "text-primary"), [("base", "bg-app")], THRESH_TEXT, "text-primary/bg-app"),
    _P(2, "light", ("solid", "text-secondary"), [("base", "bg-app")], THRESH_TEXT, "text-secondary/bg-app"),
    _P(3, "light", ("solid", "warn"), [("base", "bg-app")], THRESH_TEXT, "warn/bg-app"),
    _P(4, "light", ("solid", "live"), [("base", "bg-app")], THRESH_TEXT, "live/bg-app"),
    _P(5, "light", ("solid", "pos"), [("base", "bg-app")], THRESH_TEXT, "pos/bg-app"),
    _P(6, "light", ("solid", "neg"), [("base", "bg-app")], THRESH_TEXT, "neg/bg-app"),
    _P(7, "light", ("solid", "warn"), [("alpha_token", "warn-bg"), ("base", "bg-surface")], THRESH_TEXT, "warn/warn-bg·surface"),
    _P(8, "light", ("solid", "live"), [("alpha_token", "live-bg"), ("base", "bg-surface")], THRESH_TEXT, "live/live-bg·surface"),
    _P(9, "light", ("solid", "pos"), [("alpha_token", "pos-bg"), ("base", "bg-surface")], THRESH_TEXT, "pos/pos-bg·surface"),
    _P(10, "light", ("solid", "neg"), [("alpha_token", "neg-bg"), ("base", "bg-surface")], THRESH_TEXT, "neg/neg-bg·surface"),
    _P(11, "dark", ("solid", "text-primary"), [("base", "bg-raised")], THRESH_TEXT, "text-primary/bg-raised"),
    _P(12, "dark", ("solid", "text-secondary"), [("base", "bg-raised")], THRESH_TEXT, "text-secondary/bg-raised"),
    _P(13, "dark", ("solid", "warn"), [("base", "bg-raised")], THRESH_TEXT, "warn/bg-raised"),
    _P(14, "dark", ("solid", "live"), [("base", "bg-raised")], THRESH_TEXT, "live/bg-raised"),
    _P(15, "dark", ("solid", "pos"), [("base", "bg-raised")], THRESH_TEXT, "pos/bg-raised"),
    # #16 PENDING:玄夜 neg 在 raised 4.29 < 4.5(見 _PENDING)。
    _P(16, "dark", ("solid", "neg"), [("base", "bg-raised")], THRESH_TEXT, "neg/bg-raised", enforced=False),
    _P(17, "light", ("solid", "text-secondary"), [("overlay", "ov-panel-rgb", 0.70), ("base", "bg-app")], THRESH_TEXT, "text-secondary/ov-panel@.70·app"),
    _P(18, "light", ("solid", "text-primary"), [("overlay", "ov-panel-rgb", 0.70), ("base", "bg-app")], THRESH_TEXT, "text-primary/ov-panel@.70·app"),
    _P(19, "dark", ("solid", "text-secondary"), [("overlay", "ov-panel-rgb", 0.70), ("base", "bg-raised")], THRESH_TEXT, "text-secondary/ov-panel@.70·raised"),
    # ── UI/圖形級 ≥3.0(#20–25)──
    _P(20, "dark", ("solid", "seal"), [("base", "bg-raised")], THRESH_UI, "seal/bg-raised(朱印方印,canon9)"),
    _P(21, "light", ("solid", "seal"), [("base", "bg-app")], THRESH_UI, "seal/bg-app(朱印方印)"),
    _P(22, "light", ("solid", "text-muted"), [("base", "bg-app")], THRESH_UI, "text-muted/bg-app(非必讀豁免≥3.0)"),
    _P(23, "dark", ("solid", "text-muted"), [("base", "bg-raised")], THRESH_UI, "text-muted/bg-raised(豁免≥3.0)"),
    _P(24, "light", ("solid", "accent"), [("base", "bg-app")], THRESH_UI, "accent/bg-app(:focus-visible 環)"),
    # #25(border-strong 髮絲線)已改判 WCAG 1.4.11 裝飾豁免 → 移出 PAIRS,見 _DECORATIVE_EXEMPT。
]


def _resolve_bg(theme: dict[str, str], layers: list) -> tuple[float, float, float]:
    """由 base(鏈末)往外疊每一層,得背景實色。"""
    base = layers[-1]
    assert base[0] == "base", "bg 鏈末必為 base"
    rgb: tuple[float, float, float] = token_rgb(theme, base[1])
    for layer in reversed(layers[:-1]):
        if layer[0] == "overlay":
            _, ov_tok, alpha = layer
            rgb = composite(token_triple(theme, ov_tok), alpha, rgb)
        elif layer[0] == "alpha_token":
            _, tok = layer
            col, alpha = token_alpha_color(theme, tok)
            rgb = composite(col, alpha, rgb)
        else:  # pragma: no cover - 防打字錯
            raise ValueError(f"未知 bg 層:{layer!r}")
    return rgb


def _resolve_fg(theme: dict[str, str], fg: tuple) -> tuple[float, float, float]:
    # 現行 PAIRS 前景皆實色 token;半透明裝飾邊框(--border-strong)走 WCAG 1.4.11
    # 豁免(_DECORATIVE_EXEMPT),不作 enforced pair,故此處只解析實色。
    if fg[0] == "solid":
        return token_rgb(theme, fg[1])
    raise ValueError(f"未支援的 fg 型別:{fg!r}")


def _eval_pair(themes: dict[str, dict[str, str]], p: Pair) -> tuple[tuple, tuple, float]:
    """回傳 (fg_rgb, bg_rgb, contrast)。"""
    theme = themes[p["theme"]]
    bg = _resolve_bg(theme, p["bg"])
    fg = _resolve_fg(theme, p["fg"])
    return fg, bg, contrast(fg, bg)


def _fmt(rgb: tuple) -> str:
    return "(" + ",".join(f"{c:.1f}" for c in rgb) + ")"


# ═══ anti-vacuous(§5.4)═════════════════════════════════════════════════════


def test_contrast_formula_selfcheck() -> None:
    """§5.4 ①:公式自檢——黑/白=21.0(±0.05)、同色<1.05。防合成/gamma 寫錯。"""
    bw = contrast_hex("#000000", "#ffffff")
    assert abs(bw - 21.0) <= 0.05, f"黑/白對比應=21.0,實得 {bw}"
    same = contrast_hex("#777777", "#777777")
    assert same < 1.05, f"同色對比應≈1.0,實得 {same}"


def test_theme_dicts_have_gate_tokens() -> None:
    """§5.4 ②:兩主題 dict 各 ≥15 token 且含全部 gate token;缺任一 → FAIL。"""
    themes = _load_themes()
    for name in ("light", "dark"):
        d = themes[name]
        assert len(d) >= 15, f"{name} 主題只解析到 {len(d)} 個 token(<15),parser 疑漏塊"
        missing = [t for t in _GATE_TOKENS if t not in d]
        assert not missing, f"{name} 主題缺 gate token:{missing}"


def test_dark_overlay_triples_byte_parity() -> None:
    """§5.4 ⑤:玄夜 --ov-*-rgb 三元組必等於原冷底字面(改壞玄夜值即紅)。"""
    themes = _load_themes()
    dark = themes["dark"]
    for tok, literal in _DARK_OV_LITERALS.items():
        got = token_triple(dark, tok)
        assert got == literal, (
            f"byte-parity 破裂:玄夜 --{tok} = {got},應 = {literal}(玄夜零視覺回歸硬約束)"
        )


def test_all_pairs_meet_aa_threshold() -> None:
    """§5.2 主 gate + §5.4 ③:逐條評估 25 pair;enforced 段須全達閾。

    fail 訊息含 theme/fg/bg/got/need(§5.2)。PENDING 兩條仍評估+記錄,只不 hard-assert
    (§5.3「移出 enforced 段記 pending 明列,不留隱性紅」;凍結由另一 test 守)。
    """
    themes = _load_themes()
    evaluated = 0
    failures: list[str] = []
    for p in PAIRS:
        fg, bg, c = _eval_pair(themes, p)
        evaluated += 1
        if p["enforced"] and c + _EPS < p["need"]:
            failures.append(
                f"#{p['n']} [{p['theme']}] {p['desc']}:fg={_fmt(fg)} bg={_fmt(bg)} "
                f"got={c:.3f} need={p['need']}"
            )
    # 評估數下界:防 PAIRS 被清空 / 迴圈壞掉的空洞綠(§5.4 ③)。
    assert evaluated >= len(PAIRS) and evaluated >= 20, (
        f"實評 pair 數異常({evaluated}),PAIRS 清單疑被清空"
    )
    assert not failures, (
        "雙主題 AA 對比 ratchet 回歸(enforced pair < 閾值):\n"
        + "\n".join(failures)
        + "\n修復指引:此為 retune 值/pair 定義問題,非放寬閾值;對照 12_p1_3_dual_theme.md §5。"
    )


def test_pending_set_is_frozen_and_reported() -> None:
    """§5.3:PENDING 集凍結——PAIRS 中 enforced=False 的 n 必恰為 _PENDING 鍵集。

    防兩向腐化:①有人偷把新失敗 pair 標 pending 藏紅;②有人靜默把 pending 清成
    enforced 假綠。並再算一次記錄實值(交 PM 裁,誠實對照 spec)。
    """
    themes = _load_themes()
    pending_in_pairs = {p["n"] for p in PAIRS if not p["enforced"]}
    assert pending_in_pairs == set(_PENDING), (
        f"PENDING 集漂移:PAIRS 標 pending={sorted(pending_in_pairs)},"
        f"_PENDING={sorted(_PENDING)}。任何增減須 PM 裁並同步兩處。"
    )
    # 再算實值,確保 pending 條目仍可評估(非被繞過的死條目)。
    for p in PAIRS:
        if p["enforced"]:
            continue
        _, _, c = _eval_pair(themes, p)
        assert 1.0 <= c <= 21.0, f"#{p['n']} pending 實算 {c} 超出合理域,評估鏈疑壞"


def test_enforced_assertion_has_teeth_redproof() -> None:
    """§5.4 ④ red-proof:證 enforce 機制有牙——合成注入過淺 fg → 同機制判 FAIL。

    取 enforced 帛晝文字 pair #2(text-secondary/bg-app),原值遠過閾;把 fg 注入
    近底色的過淺值後,用同一 _eval_pair 重算,對比必跌破 need。這即「注入 → 精確
    定位失敗 → 還原全綠」在測試內的機械證(檔級親證見交付報告)。
    """
    themes = _load_themes()
    p2 = next(p for p in PAIRS if p["n"] == 2)
    _, _, c_ok = _eval_pair(themes, p2)
    assert c_ok >= p2["need"], f"前提:原 text-secondary 應過閾,實得 {c_ok}"

    poisoned = {"light": dict(themes["light"]), "dark": dict(themes["dark"])}
    poisoned["light"]["text-secondary"] = "#EDE7DC"  # 過淺,近 bg-app,合成注入
    _, _, c_bad = _eval_pair(poisoned, p2)
    assert c_bad < p2["need"], (
        f"red-proof 失效:注入過淺 fg 後對比 {c_bad} 仍 ≥ need {p2['need']},enforce 機制無牙"
    )
