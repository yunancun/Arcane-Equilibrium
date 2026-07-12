"""玄衡新殼 VIEWS 註冊表 + visibility 安全映射 完整性 smoke(P1.1-a,static/shell.js)。

MODULE_NOTE(保護的 safety 不變量 / 為何靜態 / 誠實邊界):
  保護對象:玄衡新殼(`static/shell.js`)的 `VIEWS` 註冊表(19 entry,每
    `{id,lane,hash,src,visId,label,...}`)。router 讀此建 view + rail + 廣播
    `openclaw-tab-visibility` postMessage `{type,tab:<visId>,visible}`。

  ★ 最高價值不變量(safety-critical,E2 R51 非協商點):
    殼廣播的 `tab` 欄位 = VIEWS entry 的 `visId`;隱藏 iframe 的既有消費者硬編期望
    某 id(現況 live / demo / governance)才會**暫停自身 WS / 輪詢**。若 Phase 2
    編輯 VIEWS 誤改某 `visId` → 該 tab 收不到自己期望的 visibility 訊息 → 隱藏
    iframe 的 WS 不暫停 → freshness / safety 退步。本檔機械化擋這條漂移。

  為何靜態(純 Python 讀檔 + 寬鬆 JS-literal 解析,不 import / 不 eval / 不需 node):
    只解析 source 字面事實(VIEWS 陣列欄位、消費者 `.tab` 比較字面量),零副作用、
    零連線。消費者 id 集**動態從源碼導出**(掃 `openclaw-tab-visibility` 消費行),
    絕不硬編 —— 消費者若新增 / 改名,測試自動跟隨,不會假綠。

  誠實邊界(綠 ≠「runtime WS 真暫停」):本檔**只證 visId 字串映射**——即「每個被
    消費的 tab id 都有一個 VIEWS entry 其 visId 等於該 id」。本檔**不**證
    ① postMessage 真送達隱藏 iframe ② 消費者收到後真的暫停 WS ③ router runtime
    行為。那些是 runtime 事實(NEEDS-LINUX:FastAPI + engine + 瀏覽器),不在靜態
    smoke 範圍。

  消費者偵測形狀(誠實限制):偵測器認「殼廣播訊息型別字串 + `.tab === / !== '<id>'`
    比較同現一行」的正典單行守衛形式(現 3 個消費者皆此形)。這刻意排除 producer
    (`tab: <expr>` 物件屬性,非 `.tab === '字面'`)與無關的 `.tab === 'profit'`
    (不含訊息型別字串的行)。若未來守衛拆成多行,須保持 id 比較在含訊息型別字串的
    守衛行,或同步更新本偵測器 —— 否則該消費者會漏偵(記為已知限制)。

anti-vacuous-green:VIEWS 數下限(≥19)+ 消費者數下限(≥3)+ 合成 detector
  (解析器抽不到 VIEWS / 消費者 = fail;合成假消費者 id 必被判 unmapped)。

硬紀律:本檔只新增,不改 shell.js / tab 源碼。若某斷言紅 = 發現真問題 → 據實報告,
  勿改 source 使其綠。
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

# tests/structure/<this> → parents[2] = 倉庫根
REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app"
)
STATIC_DIR = APP_DIR / "static"
SHELL_JS = STATIC_DIR / "shell.js"

# login.html 由他 session 編輯中(既有慣例)→ 排除消費者掃描。
EXCLUDE_FILES = {"login.html"}

# 殼 visibility 廣播訊息型別(唯一權威=源碼字串;消費者守衛行必含此)。
VIS_MSG_TYPE = "openclaw-tab-visibility"

# 消費者守衛:`ev.data.tab === '<id>'` 或 `.tab !== '<id>'`(同守衛行含訊息型別字串)。
_CONSUMER_TAB_RE = re.compile(r"\.tab\s*(?:===|!==)\s*'([A-Za-z0-9_-]+)'")

# VIEWS entry 必填非空欄位(缺 / 空 = 路由 / 廣播 / rail 缺料)。
REQUIRED_FIELDS = ("id", "lane", "hash", "src", "visId", "label")
VALID_LANES = {"crypto", "stock", "cross"}

# 非 /static iframe src 的允許路由集(附註:charts = trading.html 的 route,embed 模式)。
KNOWN_ROUTE_ALLOWLIST = {"/trading?embed=1"}

# anti-vacuous 下限(當前樹:19 view / 3 消費者)。
MIN_VIEWS = 19
MIN_CONSUMERS = 3


# ════════════════════════════════════════════════════════════════════════════
# 解析器(純字面,零副作用)
# ════════════════════════════════════════════════════════════════════════════
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_views_block(text: str) -> str | None:
    """抽 `var VIEWS = [ ... ]` 內容(bracket-match;此區塊字串/註釋內無方括號,安全)。"""
    m = re.search(r"var\s+VIEWS\s*=\s*\[", text)
    if not m:
        return None
    start = m.end() - 1  # '[' 位置
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    return None


def _extract_views() -> list[dict]:
    """解析 shell.js 的 VIEWS 陣列 → list[dict]。

    每 entry 是無巢狀花括號的物件字面量;抽字串欄位與布林欄位。整行 `//` 註釋略過。
    """
    text = _read(SHELL_JS)
    block = _extract_views_block(text)
    if block is None:
        return []
    # 去整行 `//` 註釋行(此區塊值內無 `//`,安全),避免註釋干擾。
    lines = []
    for ln in block.splitlines():
        if ln.lstrip().startswith("//"):
            continue
        lines.append(ln)
    clean = "\n".join(lines)

    views: list[dict] = []
    for obj in re.findall(r"\{[^{}]*\}", clean):
        entry: dict = {}
        for k, v in re.findall(r"(\w+)\s*:\s*'([^']*)'", obj):
            entry[k] = v
        for k, v in re.findall(r"(\w+)\s*:\s*(true|false)\b", obj):
            entry[k] = v == "true"
        if entry:
            views.append(entry)
    return views


def _extract_visibility_consumers() -> list[tuple[str, int, str]]:
    """動態掃全 static/ 的 visibility 消費者 → [(檔名, 行號, 被消費 tab id), ...]。

    偵測:同一行含 VIS_MSG_TYPE 字串 **且** 有 `.tab === / !== '<id>'` 比較。
    此形狀排除 producer(`tab:<expr>`)與無關 `.tab === 'profit'`(行不含訊息型別)。
    """
    out: list[tuple[str, int, str]] = []
    for path in sorted(STATIC_DIR.glob("*")):
        if not path.is_file() or path.name in EXCLUDE_FILES:
            continue
        if path.suffix not in (".js", ".html"):
            continue
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            if VIS_MSG_TYPE not in line:
                continue
            for mm in _CONSUMER_TAB_RE.finditer(line):
                out.append((path.name, lineno, mm.group(1)))
    return out


def _unmapped_consumer_ids(consumed_ids: set[str], visids: set[str]) -> list[str]:
    """純函數:回傳「被消費但無對應 VIEWS visId」的 id 排序清單(空=全映射)。"""
    return sorted(consumed_ids - visids)


# ════════════════════════════════════════════════════════════════════════════
# 1. safety(最高價值):visId 覆蓋 visibility 消費者
# ════════════════════════════════════════════════════════════════════════════
def test_visibility_consumers_have_matching_views_visid() -> None:
    """每個被消費的 tab id 都必須有一個 VIEWS entry 其 visId === 該 id。

    紅 = 隱藏 iframe 的 WS 暫停契約破裂(freshness / safety 退步)—— 點名失配 id。
    """
    views = _extract_views()
    consumers = _extract_visibility_consumers()
    visids = {v["visId"] for v in views if v.get("visId")}
    consumed_ids = {c[2] for c in consumers}

    unmapped = _unmapped_consumer_ids(consumed_ids, visids)
    assert not unmapped, (
        "safety BREAK:以下被消費的 visibility tab id 無對應 VIEWS visId="
        f"{unmapped};消費者來源={consumers};VIEWS visId 集={sorted(visids)}"
    )


def test_safety_mapping_detector_has_teeth() -> None:
    """反向 substantive:證映射檢測器有牙(非空過)。

    (a) 真消費者 id 全部應 mapped(unmapped 空);
    (b) 合成一個真實不存在的假消費者 id → 必被判為 unmapped。
    """
    views = _extract_views()
    visids = {v["visId"] for v in views if v.get("visId")}
    real_consumed = {c[2] for c in _extract_visibility_consumers()}

    assert not _unmapped_consumer_ids(real_consumed, visids), (
        "前置矛盾:真消費者 id 應全 mapped(此測試專驗檢測器有牙)"
    )

    bogus = "__nonexistent_consumer_tab__"
    synthetic = real_consumed | {bogus}
    flagged = _unmapped_consumer_ids(synthetic, visids)
    assert flagged == [bogus], (
        f"檢測器無牙:合成假消費者 id 未被精確判為 unmapped;flagged={flagged}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 2. registry 完整性
# ════════════════════════════════════════════════════════════════════════════
def test_registry_integrity() -> None:
    """VIEWS 每 entry 有非空 id/lane/hash/src/visId/label;id 唯一、hash 唯一;
    lane ∈ {crypto,stock,cross};hash 格式 `#/<lane>/<非空 view>`。
    """
    views = _extract_views()
    assert views, "VIEWS 解析為空 → 解析器壞(vacuous green 防護)"

    ids: list[str] = []
    hashes: list[str] = []
    for v in views:
        for field in REQUIRED_FIELDS:
            assert v.get(field), f"VIEWS entry 缺 / 空欄位 '{field}': {v}"
        assert v["lane"] in VALID_LANES, (
            f"VIEWS entry lane '{v['lane']}' 不在 {sorted(VALID_LANES)}: {v}"
        )
        prefix = "#/" + v["lane"] + "/"
        assert v["hash"].startswith(prefix), (
            f"VIEWS entry hash '{v['hash']}' 不符 `#/{v['lane']}/...` 格式: {v}"
        )
        view_seg = v["hash"][len(prefix):]
        assert view_seg, f"VIEWS entry hash '{v['hash']}' 缺 view 段: {v}"
        ids.append(v["id"])
        hashes.append(v["hash"])

    dup_ids = sorted(x for x, c in Counter(ids).items() if c > 1)
    assert not dup_ids, f"VIEWS id 重複(router VIEW_BY_ID 撞): {dup_ids}"

    dup_hashes = sorted(x for x, c in Counter(hashes).items() if c > 1)
    assert not dup_hashes, f"VIEWS hash 重複(router VIEW_BY_HASH 撞,深連結歧義): {dup_hashes}"


# ════════════════════════════════════════════════════════════════════════════
# 3. iframe src 可解
# ════════════════════════════════════════════════════════════════════════════
def test_iframe_src_resolvable() -> None:
    """每 VIEWS.src:`/static/*.html` → 檔存在;非-/static → 必在 KNOWN_ROUTE_ALLOWLIST。"""
    views = _extract_views()
    problems: list[str] = []
    for v in views:
        src = v.get("src", "")
        if src.startswith("/static/"):
            rel = src[len("/static/"):].split("?", 1)[0]
            if not (STATIC_DIR / rel).is_file():
                problems.append(f"{v.get('id')}: /static src 檔不存在 → {src}")
        elif src not in KNOWN_ROUTE_ALLOWLIST:
            problems.append(
                f"{v.get('id')}: 非-/static src 未列入 KNOWN_ROUTE_ALLOWLIST → {src}"
            )
    assert not problems, "iframe src 不可解:\n" + "\n".join(problems)


# ════════════════════════════════════════════════════════════════════════════
# 4. anti-vacuous-green:下限 + substantive detector
# ════════════════════════════════════════════════════════════════════════════
def test_anti_vacuous_lower_bounds() -> None:
    """VIEWS 數 ≥19、消費者數 ≥3;解析器抽不到任一 = fail(防空過)。"""
    views = _extract_views()
    consumers = _extract_visibility_consumers()
    consumed_ids = {c[2] for c in consumers}

    assert views, "VIEWS 解析為空 → 解析器壞"
    assert consumers, "visibility 消費者解析為空 → 解析器壞"
    assert len(views) >= MIN_VIEWS, (
        f"VIEWS 數 {len(views)} < 下限 {MIN_VIEWS}(疑內容丟失或解析退化)"
    )
    assert len(consumed_ids) >= MIN_CONSUMERS, (
        f"被消費 tab id 數 {len(consumed_ids)} < 下限 {MIN_CONSUMERS};"
        f"consumed={sorted(consumed_ids)}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 5. 原生 view 註冊完整性(R64:strangler-fig iframe:false → OC_NATIVE_VIEWS handler)
# ════════════════════════════════════════════════════════════════════════════
# 背景:殼 isNative(v)=(v.iframe===false);對原生 view 殼經
#   window.OC_NATIVE_VIEWS[<id>] 取 {render,pause,resume} 渲染。每個原生 view
#   於其 view-<id>.js 以 `OC_NATIVE_VIEWS['<id>'] = {...}` 註冊(key=VIEWS 的 id,
#   非 visId)。當前樹:monitor/ai/agents/learning/development/phase4/gates 共 7 個。
# 回歸風險:未來遷移把某 entry 翻 iframe:false 卻忘記/拼錯註冊 → 殼判 isNative=true
#   但 OC_NATIVE_VIEWS[<id>] undefined → 該 tab 靜默空白/壞。本節機械化擋這條漂移。
#
# 誠實邊界(綠 ≠ runtime handler 真被呼叫):本節純靜態,只證「某 view-*.js 內存在
#   OC_NATIVE_VIEWS['<id>'] 註冊字面」。不證 ① 該檔真被 shell.html 載入並執行
#   ② render/pause/resume 真被殼 router 呼叫 ③ 渲染出正確 DOM。那些是 runtime 事實
#   (NEEDS-LINUX:FastAPI + engine + 瀏覽器),不在靜態範圍。

# 原生 view 下限(當前樹:monitor/ai/agents/learning/development/phase4/gates = 7)。
MIN_NATIVE_VIEWS = 7

# 註冊字面:`OC_NATIVE_VIEWS['<id>'] =` 或 `["<id>"]`(要求 `=` 賦值,排除純讀取,
# 如 shell.js 的 `OC_NATIVE_VIEWS[v.id]` 變數下標=非字面,不誤判為註冊)。
_NATIVE_REG_RE = re.compile(
    r"OC_NATIVE_VIEWS\s*\[\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\]\s*="
)


def _native_view_ids() -> list[str]:
    """VIEWS 內所有 iframe === false 的 entry 的 id(= 原生 view,殼走 OC_NATIVE_VIEWS)。"""
    return sorted(v["id"] for v in _extract_views() if v.get("iframe") is False)


def _registered_native_ids() -> dict[str, list[str]]:
    """掃全 static/*.js 的 `OC_NATIVE_VIEWS['<id>'] =` 註冊字面 → {id: [檔名, ...]}。"""
    out: dict[str, list[str]] = {}
    for path in sorted(STATIC_DIR.glob("*.js")):
        if path.name in EXCLUDE_FILES:
            continue
        for m in _NATIVE_REG_RE.finditer(_read(path)):
            out.setdefault(m.group(1), []).append(path.name)
    return out


def _unregistered_native_ids(native_ids, registered_ids: set[str]) -> list[str]:
    """純函數:回傳「iframe:false 但無 OC_NATIVE_VIEWS 註冊」的 id 排序清單(空=全註冊)。"""
    return sorted(set(native_ids) - set(registered_ids))


def test_native_views_have_registered_handler() -> None:
    """每個 VIEWS iframe:false 的原生 view id 必須有對應 OC_NATIVE_VIEWS['<id>'] 註冊。

    紅 = 殼判 isNative=true 卻取不到 handler → 該 tab 靜默空白/壞 —— 點名失配 id。
    """
    native = _native_view_ids()
    registered = _registered_native_ids()
    missing = _unregistered_native_ids(native, set(registered))
    assert not missing, (
        "strangler-fig BREAK:以下 VIEWS iframe:false 原生 view id 無對應 "
        f"OC_NATIVE_VIEWS['<id>'] 註冊字面(殼 isNative=true 但 handler undefined → "
        f"該 tab 靜默空白/壞):{missing};已註冊 id={sorted(registered)};"
        f"原生 id 全集={native}"
    )


def test_native_registration_detector_has_teeth() -> None:
    """反向 substantive:證原生註冊檢測器有牙(非空過)。

    (a) 下限:須解析出 ≥7 原生 id(解析壞→空集合→假綠 的防護);
    (b) 掃描器須真抓到註冊字面(registered 非空);
    (c) 真樹全註冊(前置一致性);
    (d) 合成負例:注入一個無註冊的 iframe:false id → 必被精確判為 unregistered。
    """
    native = _native_view_ids()
    registered = _registered_native_ids()

    assert len(native) >= MIN_NATIVE_VIEWS, (
        f"原生 view id 數 {len(native)} < 下限 {MIN_NATIVE_VIEWS}"
        f"(疑 VIEWS 解析退化或原生遷移遺失);native={native}"
    )
    assert registered, "OC_NATIVE_VIEWS 註冊掃描為空 → 掃描器/正則壞(vacuous green 防護)"
    assert not _unregistered_native_ids(native, set(registered)), (
        "前置矛盾:真樹原生 id 應全註冊(此測試專驗檢測器有牙)"
    )

    bogus = "__synthetic_missing__"
    flagged = _unregistered_native_ids(native + [bogus], set(registered))
    assert flagged == [bogus], (
        f"檢測器無牙:合成「iframe:false 但無註冊」id 未被精確抓;flagged={flagged}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 6. 寫面 view 的殼 CSS 依賴鎖(R64:鎖 R63 修復,防靜默回退)
# ════════════════════════════════════════════════════════════════════════════
# 背景:已遷 4 寫面 view(view-ai / view-ai-providers / view-ai-cost / view-learning)
#   用 ocToast / openConfirmModal → emit .oc-toast* / .oc-confirm-* / .oc-prompt-* /
#   .oc-btn* class。殼跳過 ocInjectBaseCSS,故 R63 把這組 class port 進
#   shell-components.css 並由 shell.html 載入。回歸風險:該 port 被靜默回退 →
#   寫面 modal/toast 視覺退化(無樣式)。本節鎖住 shell.html 載入 + class 定義存在。
#
# 誠實邊界:純靜態,只證「shell.html 載入 shell-components.css 且該檔定義這組 class
#   selector」。不證 runtime 樣式真套用到寫面 view DOM(那需瀏覽器,NEEDS-LINUX)。

SHELL_HTML = STATIC_DIR / "shell.html"
SHELL_COMPONENTS_CSS = STATIC_DIR / "shell-components.css"

# 寫面 view 依賴的最小 class 集(toast / typed-confirm modal / prompt 表單 / 按鈕)。
WRITE_FACE_CSS_CLASSES = (
    ".oc-toast",
    ".oc-confirm-overlay",
    ".oc-confirm-dialog",
    ".oc-prompt-input",
    ".oc-btn",
    ".oc-btn-danger",
)


def _css_defines_selector(css: str, cls: str) -> bool:
    r"""css 內是否有以 `cls` 為 selector 的規則(排除註釋文句的裸提及,如 `(.oc-toast*)`)。

    要求 cls 前為行首/空白/`,`/`}`,後接 selector 終止字元 `[\s.,:{]` —— 故 `.oc-btn`
    不會誤配 `.oc-btn-primary`(後接 `-`,不在終止集),`(.oc-toast*)` 亦不誤配(後接 `*`)。
    """
    pat = re.compile(r"(?:^|[\s,}])" + re.escape(cls) + r"[\s.,:{]", re.MULTILINE)
    return bool(pat.search(css))


def test_shell_loads_write_face_component_css() -> None:
    """寫面 view 的殼 CSS 依賴鎖(R63):shell.html 載 shell-components.css 且該檔定義
    寫面 modal/toast/form/按鈕 class。紅 = R63 修復被靜默回退 → 寫面視覺退化。
    """
    html = _read(SHELL_HTML)
    assert "shell-components.css" in html, (
        "shell.html 未載入 shell-components.css(殼跳過 ocInjectBaseCSS,寫面 view 的 "
        "toast/modal/表單/按鈕 class 無來源 → 視覺退化)"
    )
    css = _read(SHELL_COMPONENTS_CSS)
    missing = [c for c in WRITE_FACE_CSS_CLASSES if not _css_defines_selector(css, c)]
    assert not missing, (
        "R63 修復被靜默回退:shell-components.css 缺寫面 class selector 定義="
        f"{missing}(寫面 view 的 ocToast/openConfirmModal 視覺退化)"
    )


def test_write_face_css_lock_detector_has_teeth() -> None:
    """反向 substantive:證 CSS selector 檢測器有牙(非子字串鬆判)。

    (a) 真樹全數存在(前置一致性);
    (b) 合成不存在的 class → 必判為缺;
    (c) 註釋裸提及(`.oc-toast*` 後接 `*`)不算「已定義」→ 精確 selector 判別。
    """
    css = _read(SHELL_COMPONENTS_CSS)

    for cls in WRITE_FACE_CSS_CLASSES:
        assert _css_defines_selector(css, cls), (
            f"前置矛盾:真樹應定義 {cls}(此測試專驗檢測器有牙)"
        )

    assert not _css_defines_selector(css, ".oc-nonexistent-write-face-class"), (
        "檢測器無牙:合成不存在 class 被誤判為已定義"
    )

    # 純提及但非 selector 的合成串:`(.oc-only-in-comment*)` 不應算已定義。
    comment_only = "/* 說明:(.oc-only-in-comment*) 僅文句提及,非規則 */"
    assert not _css_defines_selector(comment_only, ".oc-only-in-comment"), (
        "檢測器無牙:註釋裸提及(後接 `*`)被誤判為 selector 定義"
    )


# ════════════════════════════════════════════════════════════════════════════
# cache-buster 一致性守衛(F-R96-1 HIGH 防復發)
#   背景:R55→R96 期間 shell.js 的 BUILD_TS 與 shell.html 的 `shell.js?v=` 同凍結
#   於 20260711.shell-p11a,致 shell.js 的 R86-R96 改動被客戶端快取污染(不傳播)。
#   守衛:BUILD_TS 常量 **必等於** shell.html 載入 shell.js 的 `?v=` 版號 → 兩者不可
#   靜默漂移;殼-loader 凍結 = 大聲 fail。(不涵蓋其他檔的 ?v=,但鎖住最關鍵的殼-loader。)
# ════════════════════════════════════════════════════════════════════════════
_BUILD_TS_RE = re.compile(r"var\s+BUILD_TS\s*=\s*'([^']+)'")
_SHELL_JS_VER_RE = re.compile(r"shell\.js\?v=([A-Za-z0-9._-]+)")


def _extract_build_ts(js_text: str) -> str | None:
    m = _BUILD_TS_RE.search(js_text)
    return m.group(1) if m else None


def _extract_shell_js_cache_buster(html_text: str) -> str | None:
    m = _SHELL_JS_VER_RE.search(html_text)
    return m.group(1) if m else None


def test_shell_js_cache_buster_matches_build_ts() -> None:
    """shell.html 載入 shell.js 的 `?v=` 必等於 shell.js 的 BUILD_TS(F-R96-1 防復發)。

    兩者漂移 = 殼-loader 快取凍結(shell.js 改動不傳播,需硬刷新)。此守衛令漂移大聲 fail。
    """
    build_ts = _extract_build_ts(_read(SHELL_JS))
    assert build_ts, "shell.js 未找到 `var BUILD_TS = '...'`(解析器失效或常量被移除)"

    shell_html = STATIC_DIR / "shell.html"
    ver = _extract_shell_js_cache_buster(_read(shell_html))
    assert ver, "shell.html 未找到 `shell.js?v=...`(shell.js 未帶 cache-buster ?v=)"

    assert ver == build_ts, (
        "F-R96-1 復發:shell.html 的 `shell.js?v=" + ver + "` 與 shell.js 的 "
        "BUILD_TS='" + build_ts + "' 不一致 → 殼-loader 快取凍結(shell.js 改動不傳播)。"
        "每次改 shell.js 的批必同步 bump 兩處。"
    )


def test_cache_buster_guard_has_teeth() -> None:
    """反向 substantive:證 cache-buster 一致性檢測器有牙(非空綠)。

    (a) 真樹兩正則都命中(前置一致性,否則守衛空過);
    (b) 合成漂移(BUILD_TS 與 ?v= 不同)必被判不一致。
    """
    # (a) 真樹前置:兩者都可抽出(否則主守衛會因 None 而假過)。
    assert _extract_build_ts(_read(SHELL_JS)), "前置矛盾:真樹 shell.js 應有 BUILD_TS"
    assert _extract_shell_js_cache_buster(_read(STATIC_DIR / "shell.html")), (
        "前置矛盾:真樹 shell.html 應有 shell.js?v="
    )

    # (b) 合成漂移:檢測器須能區分一致 vs 不一致。
    same_js = "var BUILD_TS = '20260713.r99';"
    same_html = '<script src="/static/shell.js?v=20260713.r99"></script>'
    drift_html = '<script src="/static/shell.js?v=20260101.stale"></script>'
    assert _extract_build_ts(same_js) == _extract_shell_js_cache_buster(same_html), (
        "檢測器無牙:一致的合成對被判為不一致"
    )
    assert _extract_build_ts(same_js) != _extract_shell_js_cache_buster(drift_html), (
        "檢測器無牙:漂移的合成對未被判為不一致"
    )
