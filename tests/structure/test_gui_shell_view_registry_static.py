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
