"""玄衡新殼 inline-reuse 原生 view「跨檔頂層詞法重名」靜態 guard(R71,static/view-*.js + tab/card source)。

MODULE_NOTE(保護的不變量 / 為何靜態 / 誠實邊界):
  保護對象:strangler-fig「fetch tab-*.html/card → 重跑其內聯 <script>」的 inline-reuse
    原生 view。若某 view 用 raw `appendChild(<script>)` 重跑,則該 script **頂層(巢狀
    層級 0)** 的 `let/const/class` 進入殼**共享 global lexical 環境**。兩個 raw 重跑的
    script 若在頂層宣告**同名** `let/const/class` → 跨 script 重宣告 **SyntaxError** →
    第二個被 navigate 的 view 整段 script 不執行 → 所有 onclick 未定義 → **靜默功能死**。
    (頂層 `function`/`var` 進 window,重賦值不拋,非此 bug;只 `let/const/class` 拋。)

  ★ 最高價值不變量(R70 E2 曾抓到真 bug:tab-paper.html:366 與 tab-settings.html:837 都
    頂層 `let stateRevision`,settings 未隔離時與 paper 撞 → 靜默 dead-view;已由 view-settings.js
    IIFE-wrap 修復):
      **任一頂層 `let/const/class` 名,至多由「一個」raw 重跑的 source 貢獻進殼共享
      global realm。** 跨 source(paper 內聯 / phase4 各 card / 未來 raw view)聯集無重複。

  raw vs isolated 判定(不硬編,查 view-*.js 的 rerun 實際邏輯):
    - **isolated(貢獻空集)**:view 的 rerun 把 source script text **IIFE 包裹**
      (`'(function(){' + txt + …'})();'`)再 appendChild → 頂層宣告成 IIFE-local,不進
      global realm。偵測=view 內「新 <script> 節點的 textContent 值」解析為含 IIFE-opener
      字串字面(直接或一跳 `var X = '(function…' + …`)。現況:view-settings.js。
    - **raw(貢獻其 source 全部頂層名)**:view 的 rerun 直接把 source script text
      appendChild(無 IIFE 包裹)。現況:view-paper.js、view-phase4.js。
    - **isolated-by-source**:即便 view 是 raw,若某 source 內聯 script **整段本身**就在
      IIFE 內(頂層宣告在深度 ≥1),則它本就不貢獻 global → 深度 0 掃描自然得空集。
      現況:phase4 的 4 張 card(teacher/linucb/news/dl3)內聯 script 皆 `(function(){…})();`
      整段包裹 → 貢獻空集。

  source 頂層名抽取(字元級掃描,非脆弱正則):跳過 字串/樣板/行·塊註釋/regex 字面,追蹤
    (){}[] 深度,只在**深度 0** 捕 `let|const|class <ident>`。整段在 IIFE 內 → 宣告在
    深度 ≥1 → 不計。

  為何靜態(純 Python 讀檔 + 寬鬆掃描,不 import / 不 eval / 不需 node/瀏覽器):只解析
    source 字面事實(view rerun 形式、內聯 script 深度 0 宣告)。零副作用、零連線。inline-reuse
    view 集**動態從 view-*.js 導出**(掃 createElement('script')+textContent+append 形狀),
    source 集**動態從 view 內 `/static/*.html` fetch 字面導出**,絕不硬編 —— 新增 view/source
    自動跟隨,不會假綠。

  誠實邊界(綠 ≠「runtime 真無 dead-view」):本檔純靜態,只證「頂層詞法名跨 raw source 無
    重複」= 瀏覽器共享 global lexical **不會重宣告拋 SyntaxError 的必要條件**。**不**證
    ① fetch/DOMParser/appendChild runtime 真行為 ② script 真被殼載入執行 ③ 真渲染出 DOM /
    真無 dead-view(那需 Linux + 瀏覽器,NEEDS-LINUX)。isolation 偵測基於 view-*.js 源碼
    **形式**(IIFE-opener 字串 + textContent 賦值);若未來改寫 rerun 隔離機制(如改用
    Function ctor / module / shadow realm),須同步更新本偵測器,否則此判定退化為已知限制。

anti-vacuous-green:inline-reuse view 數下限(≥3)+ raw/isolated 兩類各非空(證分類器兩分支
  皆觸)+ raw 貢獻聯集非空且含錨名 `stateRevision`(證深度 0 掃描器未壞)+ 合成負例
  (兩假 raw source 同名 → 偵測器抓得到;IIFE 包裹 source/view → 不誤報)。

硬紀律:本檔只新增,不改任何 static 源碼 / view-*.js。若某斷言紅 = 發現未爆 bug(如 phase4
  card 間或 card↔paper 頂層重名)→ 據實報告,勿改 source 使其綠。
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/structure/<this> → parents[2] = 倉庫根
REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)

# anti-vacuous 下限(當前樹:paper/phase4=raw、settings=isolated = 3 inline-reuse view)。
MIN_INLINE_REUSE_VIEWS = 3
MIN_RAW_VIEWS = 2       # paper、phase4
MIN_ISOLATED_VIEWS = 1  # settings(R70 IIFE-wrap 修復)
# R70 真 bug 的錨名:paper 頂層貢獻此名(settings source 亦有,但 IIFE 隔離不貢獻)。
ANCHOR_NAME = "stateRevision"
# paper source 頂層名下限(現況 7;取 5 作 floor,防深度 0 掃描器退化成空集假綠)。
MIN_PAPER_TOPLEVEL = 5


# ════════════════════════════════════════════════════════════════════════════
# 解析器(純字面,零副作用)
# ════════════════════════════════════════════════════════════════════════════
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_ID_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$")
_ID_CONT = _ID_START | set("0123456789")
# 前一有意義 code 字元屬此集 → `/` 視為 regex 起始(表達式位置),否則視為除號。
_REGEX_PREV = set("(,=:[!&|?{;}+-*%<>~^")
# 這些關鍵字後的 `/` 亦為 regex(表達式位置);掃到即把 prev 置為哨兵(':' ∈ _REGEX_PREV)。
_REGEX_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "do", "else", "yield", "case", "throw",
}


def _top_level_lexical_names(text: str) -> list[str]:
    """回傳 script 的**深度 0**(巢狀層級 0)`let/const/class` 宣告名(保序去重)。

    字元級掃描:跳過 字串('/")、樣板(`含 ${}`)、行/塊註釋、regex 字面;追蹤 (){}[]
    深度;只在深度 0 且處於 code(非上述任一)時捕關鍵字後的識別字。整段被 IIFE 包住 →
    宣告落在深度 ≥1 → 不計(isolated-by-source)。
    """
    names: list[str] = []
    i, n = 0, len(text)
    depth = 0
    prev_sig = ""  # 上一個有意義(非空白/註釋)code 字元
    while i < n:
        c = text[i]
        # 行註釋
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        # 塊註釋
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        # 字串 ' 或 "
        if c in "'\"":
            q = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == q:
                    i += 1
                    break
                i += 1
            prev_sig = q
            continue
        # 樣板字串(含 ${...} 巢狀插值)
        if c == "`":
            i += 1
            tmpl_depth = 0
            while i < n:
                ch = text[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "`" and tmpl_depth == 0:
                    i += 1
                    break
                if ch == "$" and i + 1 < n and text[i + 1] == "{":
                    tmpl_depth += 1
                    i += 2
                    continue
                if ch == "}" and tmpl_depth > 0:
                    tmpl_depth -= 1
                    i += 1
                    continue
                i += 1
            prev_sig = "`"
            continue
        # regex 字面(僅在表達式位置;含 [char-class] 內 `/` 為字面)
        if c == "/" and (prev_sig == "" or prev_sig in _REGEX_PREV):
            i += 1
            in_class = False
            while i < n:
                ch = text[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    i += 1
                    break
                elif ch == "\n":
                    break
                i += 1
            prev_sig = "/"
            continue
        # 括號深度
        if c in "([{":
            depth += 1
            prev_sig = c
            i += 1
            continue
        if c in ")]}":
            depth -= 1
            prev_sig = c
            i += 1
            continue
        # 識別字 / 關鍵字
        if c in _ID_START:
            j = i
            while j < n and text[j] in _ID_CONT:
                j += 1
            word = text[i:j]
            # 深度 0 + 關鍵字 + 前一 code 字元為識別字邊界(非 id 字元、非 `.` 屬性存取)
            if (
                word in ("let", "const", "class")
                and depth == 0
                and prev_sig not in _ID_CONT
                and prev_sig != "."
            ):
                k = j
                while k < n and text[k] in " \t\r\n":
                    k += 1
                if k < n and text[k] in _ID_START:
                    m = k
                    while m < n and text[m] in _ID_CONT:
                        m += 1
                    names.append(text[k:m])
            # regex-preceding 關鍵字 → 下一個 `/` 視為 regex(哨兵 ':' ∈ _REGEX_PREV)
            prev_sig = ":" if word in _REGEX_KEYWORDS else word[-1]
            i = j
            continue
        if not c.isspace():
            prev_sig = c
        i += 1

    seen: set[str] = set()
    out: list[str] = []
    for nm in names:
        if nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out


# 無 src 屬性的 <script> 內文;跳過 ocInjectBaseCSS bootstrap(view rerun 亦跳過,保真)。
_SCRIPT_BLOCK_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def _inline_scripts(html: str) -> list[str]:
    out: list[str] = []
    for m in _SCRIPT_BLOCK_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
            continue  # 外部 script(殼已載入),view 略過
        if "ocInjectBaseCSS" in body:
            continue  # bootstrap(ocAuthCheck+ocInjectBaseCSS),view 明確略過
        out.append(body)
    return out


# view rerun 特徵字面
_CREATE_SCRIPT_RE = re.compile(r"createElement\(\s*['\"]script['\"]\s*\)")
_TEXTCONTENT_RHS_RE = re.compile(r"\.textContent\s*=\s*([^;]+?)\s*;")
# IIFE-opener 字串字面(如 '(function(){' 或 "( function")
_IIFE_OPENER_STR_RE = re.compile(r"""['"]\s*\(\s*function\b""")
_SIMPLE_ID_RE = re.compile(r"[A-Za-z_$][\w$]*")
# view 內 fetch 的 source html 字面(/static/*.html、含 cards/)
_STATIC_HTML_REF_RE = re.compile(r"['\"](/static/[A-Za-z0-9_./-]+\.html)['\"]")


def _is_inline_reuse_view(view_src: str) -> bool:
    """membership:view-*.js 是否走「建 <script> + 設 textContent + append 重跑」形狀。"""
    has_create = bool(_CREATE_SCRIPT_RE.search(view_src))
    has_textcontent = bool(_TEXTCONTENT_RHS_RE.search(view_src))
    has_append = ("appendChild" in view_src) or ("replaceChild" in view_src)
    return has_create and has_textcontent and has_append


def _view_is_isolated(view_src: str) -> bool:
    """判 view rerun 是否 IIFE 包裹被重跑的 script text(→ 貢獻空集)。

    對每個「新 <script> 節點的 textContent 賦值」的 RHS:直接含 IIFE-opener 字串,或
    RHS 是單一識別字且其 `var <id> = …` 初值含 IIFE-opener 字串 → 判 isolated。
    """
    for rhs in _TEXTCONTENT_RHS_RE.findall(view_src):
        rhs = rhs.strip()
        if _IIFE_OPENER_STR_RE.search(rhs):
            return True
        mid = _SIMPLE_ID_RE.fullmatch(rhs)
        if mid:
            m = re.search(r"\bvar\s+" + re.escape(rhs) + r"\s*=\s*(.*?);", view_src, re.DOTALL)
            if m and _IIFE_OPENER_STR_RE.search(m.group(1)):
                return True
    return False


def _static_html_sources(view_src: str) -> list[str]:
    """view 內 fetch 的 /static/*.html 相對路徑(去 /static/ 前綴),只留真實存在檔。

    非硬編:順 view 的 fetch 字面;不存在的(如註釋裡的 `cards/X_card.html` 佔位)自動濾掉。
    """
    rels: list[str] = []
    for m in _STATIC_HTML_REF_RE.finditer(view_src):
        rel = m.group(1)[len("/static/"):]
        if (STATIC_DIR / rel).is_file() and rel not in rels:
            rels.append(rel)
    return sorted(rels)


def _inline_reuse_views() -> list[dict]:
    """掃 STATIC_DIR/view-*.js → inline-reuse view 清單。

    每 entry:{id, file, isolated(bool), sources(list[rel html])}。
    """
    out: list[dict] = []
    for path in sorted(STATIC_DIR.glob("view-*.js")):
        src = _read(path)
        if not _is_inline_reuse_view(src):
            continue
        out.append({
            "id": path.stem[len("view-"):],   # view-paper → paper
            "file": path.name,
            "isolated": _view_is_isolated(src),
            "sources": _static_html_sources(src),
        })
    return out


def _collect_contributions(views: list[dict]) -> dict[str, set[str]]:
    """回傳 {頂層名: {貢獻 source 標籤, ...}} —— 只計 **raw** view 的 source 深度 0 名。

    貢獻單位=單一被重跑的內聯 script(runtime 每個 rerun 都是一次獨立 <script> append 進
    同一 realm),標籤=`<view id>:<rel html>`(同檔多內聯 script 再綴 `#<idx>`)。
    """
    contrib: dict[str, set[str]] = {}
    for v in views:
        if v["isolated"]:
            continue  # isolated view → 貢獻空集
        for rel in v["sources"]:
            scripts = _inline_scripts(_read(STATIC_DIR / rel))
            for idx, s in enumerate(scripts):
                label = f"{v['id']}:{rel}" + (f"#{idx}" if len(scripts) > 1 else "")
                for name in _top_level_lexical_names(s):
                    contrib.setdefault(name, set()).add(label)
    return contrib


def _collisions(contrib: dict[str, set[str]]) -> dict[str, list[str]]:
    """純函數:回傳「≥2 個不同 source 貢獻」的頂層名 → 排序 source 標籤(空=無衝突)。"""
    return {nm: sorted(labels) for nm, labels in contrib.items() if len(labels) >= 2}


# ════════════════════════════════════════════════════════════════════════════
# 1. 最高價值不變量:跨 raw source 頂層詞法名無重複
# ════════════════════════════════════════════════════════════════════════════
def test_no_cross_source_toplevel_lexical_collision() -> None:
    """任一頂層 let/const/class 名至多由一個 raw source 貢獻進殼共享 global realm。

    紅 = 兩個 raw 重跑的 script 頂層同名 → 瀏覽器共享 global lexical 重宣告 SyntaxError →
    第二個 navigate 的 view 靜默功能死 —— 點名衝突的名 + 哪幾個 view/source。
    """
    views = _inline_reuse_views()
    contrib = _collect_contributions(views)
    coll = _collisions(contrib)
    assert not coll, (
        "跨檔頂層詞法重名 BREAK(共享 global lexical 重宣告 → 靜默 dead-view):"
        + "; ".join(f"'{nm}' 由 {srcs} 共同貢獻" for nm, srcs in sorted(coll.items()))
    )


# ════════════════════════════════════════════════════════════════════════════
# 2. anti-vacuous:下限 + 錨名 + 分類器兩分支皆觸
# ════════════════════════════════════════════════════════════════════════════
def test_anti_vacuous_lower_bounds() -> None:
    """inline-reuse view 數 ≥3、raw ≥2、isolated ≥1;raw 貢獻聯集非空且含錨名;paper
    source 頂層名 ≥ floor(防深度 0 掃描器退化成空集假綠)。
    """
    views = _inline_reuse_views()
    assert len(views) >= MIN_INLINE_REUSE_VIEWS, (
        f"inline-reuse view 數 {len(views)} < 下限 {MIN_INLINE_REUSE_VIEWS}"
        f"(疑 view 遺失或 membership 偵測退化);views={[v['file'] for v in views]}"
    )
    raw = [v for v in views if not v["isolated"]]
    iso = [v for v in views if v["isolated"]]
    assert len(raw) >= MIN_RAW_VIEWS, (
        f"raw view 數 {len(raw)} < 下限 {MIN_RAW_VIEWS}(分類器 raw 分支疑失效);"
        f"raw={[v['file'] for v in raw]}"
    )
    assert len(iso) >= MIN_ISOLATED_VIEWS, (
        f"isolated view 數 {len(iso)} < 下限 {MIN_ISOLATED_VIEWS}(分類器 isolated 分支疑失效);"
        f"iso={[v['file'] for v in iso]}"
    )

    contrib = _collect_contributions(views)
    assert contrib, "raw 貢獻聯集為空 → 深度 0 掃描器/正則壞(vacuous green 防護)"
    assert ANCHOR_NAME in contrib, (
        f"錨名 '{ANCHOR_NAME}' 未出現在 raw 貢獻 → 深度 0 掃描器退化;contrib keys={sorted(contrib)}"
    )

    paper = next((v for v in views if v["id"] == "paper"), None)
    assert paper is not None, "現況錨:應存在 id=paper 的 inline-reuse view"
    paper_names: set[str] = set()
    for rel in paper["sources"]:
        for s in _inline_scripts(_read(STATIC_DIR / rel)):
            paper_names.update(_top_level_lexical_names(s))
    assert len(paper_names) >= MIN_PAPER_TOPLEVEL, (
        f"paper source 頂層名數 {len(paper_names)} < floor {MIN_PAPER_TOPLEVEL}"
        f"(疑深度 0 掃描器抽空);paper_names={sorted(paper_names)}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 3. 現況錨:paper=raw 貢獻 stateRevision、settings=isolated 不貢獻、phase4 cards=空集
# ════════════════════════════════════════════════════════════════════════════
def test_current_state_classification_anchor() -> None:
    """正例錨(確認現狀綠且理解正確):
      - paper=raw,其 source 頂層貢獻含 stateRevision;
      - settings=isolated(view IIFE-wrap),雖 source 本身頂層亦有 stateRevision(若改回 raw
        會與 paper 撞)→ 證 view-IIFE 隔離是唯一防線;
      - phase4=raw 重跑,但 4 張 card source 各整段 IIFE-wrap → 貢獻空集(isolated-by-source)。
    此為當前樹快照;若某 card 未來移除自身 IIFE 或改名 view,此錨紅=提示須複查(非退化)。
    """
    views = {v["id"]: v for v in _inline_reuse_views()}
    assert {"paper", "settings", "phase4"} <= set(views), (
        f"現況錨:應存在 paper/settings/phase4 三 inline-reuse view;實得={sorted(views)}"
    )

    assert views["paper"]["isolated"] is False, "paper 應判 raw(其 rerun 直接 appendChild txt)"
    assert views["settings"]["isolated"] is True, "settings 應判 isolated(rerun IIFE-wrap)"
    assert views["phase4"]["isolated"] is False, "phase4 應判 raw(其 rerun 直接 appendChild card script)"

    def _names(view: dict) -> set[str]:
        acc: set[str] = set()
        for rel in view["sources"]:
            for s in _inline_scripts(_read(STATIC_DIR / rel)):
                acc.update(_top_level_lexical_names(s))
        return acc

    assert ANCHOR_NAME in _names(views["paper"]), (
        f"paper source 應頂層貢獻 '{ANCHOR_NAME}'(R70 bug 錨名)"
    )
    assert ANCHOR_NAME in _names(views["settings"]), (
        f"settings source 本身應頂層含 '{ANCHOR_NAME}'(若 view 改回 raw 即與 paper 撞;"
        f"證隔離是唯一防線)"
    )
    # phase4 的 4 張 card 皆源級 IIFE → 貢獻空集(當前樹事實;非硬不變量,benign 更新時同步)。
    phase4_names = _names(views["phase4"])
    assert phase4_names == set(), (
        f"現況理解:phase4 的 card source 皆整段 IIFE-wrap 應貢獻空集,實得={sorted(phase4_names)}"
        f"(若非空且與 paper/其他 card 交集 → 未爆 bug,見不變量測試;若無交集 → 更新此錨)"
    )


# ════════════════════════════════════════════════════════════════════════════
# 4. 合成負例:偵測器有牙(碰撞偵測 / raw·isolated 分類 / 源級 IIFE 不誤報)
# ════════════════════════════════════════════════════════════════════════════
def test_collision_detector_has_teeth() -> None:
    """兩個假 raw source 各含頂層 `let __synthetic_dup__` → 跨 source 聯集必判重複;
    函式體內 / 單 source 的名不得誤判。
    """
    src_a = "let __synthetic_dup__ = 1;\nfunction f(){ let inner_only = 2; }"
    src_b = "const other_single = 9;\nlet __synthetic_dup__ = 2;"
    contrib: dict[str, set[str]] = {}
    for label, s in [("viewA:a.html", src_a), ("viewB:b.html", src_b)]:
        for name in _top_level_lexical_names(s):
            contrib.setdefault(name, set()).add(label)

    coll = _collisions(contrib)
    assert coll.get("__synthetic_dup__") == ["viewA:a.html", "viewB:b.html"], (
        f"偵測器無牙:合成跨 source 同名頂層未被精確判重複;coll={coll}"
    )
    assert "inner_only" not in contrib, "深度 ≥1(函式體)宣告不得被計為頂層"
    assert "other_single" not in coll, "單 source 名不得被誤判為碰撞"


def test_raw_vs_isolated_classifier_has_teeth() -> None:
    """合成 raw / isolated 兩種 view rerun 形狀,證分類器精確區分。"""
    raw_view = (
        "var s=document.createElement('script'); s.textContent = txt; root.appendChild(s);"
    )
    iso_inline = (
        "var wrapped='(function(){\\n'+txt+'\\n})();';"
        "var s=document.createElement('script'); s.textContent=wrapped; root.appendChild(s);"
    )
    iso_direct = (
        "var s=document.createElement('script');"
        "s.textContent='(function(){'+txt+'})();'; root.appendChild(s);"
    )
    assert _is_inline_reuse_view(raw_view), "raw 合成應判 inline-reuse membership"
    assert _is_inline_reuse_view(iso_inline), "isolated(一跳)合成應判 inline-reuse membership"
    assert _is_inline_reuse_view(iso_direct), "isolated(直接)合成應判 inline-reuse membership"
    assert _view_is_isolated(raw_view) is False, "raw 合成不得被判 isolated"
    assert _view_is_isolated(iso_inline) is True, "IIFE-wrap(一跳 var)合成應判 isolated"
    assert _view_is_isolated(iso_direct) is True, "IIFE-wrap(直接賦值)合成應判 isolated"


def test_source_level_iife_contributes_empty() -> None:
    """源級 IIFE 包裹的 source → 深度 0 掃描應得空集(不誤報頂層名);非包裹則抽到。"""
    raw_source = "let __top_a__ = 1; const __top_b__ = 2; class __top_c__ {}"
    iife_source = "(function(){ let __top_a__ = 1; const __top_b__ = 2; })();"
    assert set(_top_level_lexical_names(raw_source)) == {"__top_a__", "__top_b__", "__top_c__"}
    assert _top_level_lexical_names(iife_source) == [], (
        "源級 IIFE 內宣告在深度 ≥1,不得被計為頂層(否則誤報 phase4 card 類 source)"
    )


def test_scanner_ignores_non_code_contexts() -> None:
    """深度 0 掃描器須跳過 字串/樣板/行·塊註釋/regex/函式體/巢狀塊,只抽真頂層宣告。"""
    tricky = "\n".join([
        "let real_top = 1;",
        "// let commented_line = 2;",
        "/* let block_commented = 3; */",
        "const in_str = \"let str_decl = 4;\";",
        "const in_tmpl = `let tmpl_decl = 5;`;",
        "const in_regex = /let regex_decl = 6/;",
        "function f() { let nested_fn = 7; }",
        "if (real_top) { let nested_block = 8; }",
        "const also_top = 9;",
    ])
    names = _top_level_lexical_names(tricky)
    for good in ("real_top", "in_str", "in_tmpl", "in_regex", "also_top"):
        assert good in names, f"真頂層宣告 '{good}' 應被抽到;names={names}"
    for bad in (
        "commented_line", "block_commented", "str_decl", "tmpl_decl",
        "regex_decl", "nested_fn", "nested_block",
    ):
        assert bad not in names, f"非 code / 深度 ≥1 的 '{bad}' 不得被誤判為頂層;names={names}"
