"""P1.0 GUI smoke — 切片 (5):fetch↔route 對齊 ratchet(§0 終態 criterion-3)。

MODULE_NOTE(為何靜態 / 誠實邊界 / 為何 AST 非 runtime introspection):
  本檔把「GUI 前端 fetch/wrapper 呼叫的 (method, path)」對齊「後端 FastAPI 權威路由集」,
  作 ratchet:任何 GUI 呼叫的路徑若不在 `authoritative ∪ DYNAMIC_DEBT ∪ KNOWN_MISMATCH`
  → 失敗並點名 檔:行 + method + path。這機械化地擋「GUI 呼一條後端沒有的路由(打死呼叫 /
  route 改名漏改 GUI / typo)」——今日 grep 難查、只有 runtime 404 才現形的盲區。

  ★ 路由權威取得 = AST 靜態解析(**非** runtime `app.routes` introspection)。
    5b 設計正本首選 runtime introspection,但**實測 import 不 clean/safe**:
    `import app.main` 會(1)自動生成並寫入 `.secrets/api_token` 檔、(2)嘗試連 PG
    127.0.0.1:15432、(3)嘗試連 engine socket /tmp/openclaw/engine.sock、(4)觸發
    AgentEventStore RuntimeError。屬硬邊界禁止的 DB/檔案副作用 → 依 §5「勿強行,改 AST
    fallback」。AST 解析零副作用、零連線,涵蓋 §5 十規則(見 _extract_routes)。

  誠實邊界(綠 ≠「GUI works」):本檔**只證 path + method 形狀對齊**,**不**證
    ① response 欄位真被消費 ② auth/CSRF ③ 200-vs-4xx 真回應 ④ 動態組路徑真值。
    這些是 runtime 事實(NEEDS-LINUX:FastAPI + engine),不在靜態 smoke 範圍。

  與 5a(PA-investigator R46 read-only)對照:authoritative=334(EXACT 同 5a);
    對齊分區**收緊**——見 DYNAMIC_DEBT_ALLOWLIST 註解(本檔 full-concat-resolver 解出
    5a 的 9 條 concat-truncated debt 為真路由 → MATCHED,只餘 5 條 load-bearing debt)。

設計正本:docs/execution_plan/gui_redesign/design/08_smoke_tests.md §5(5a 調查 + 5b 規格)。
anti-vacuous-green:route/callsite 掃描下限 + matched 下限 + 合成 detector(假路徑必被抓)。
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app"
)
STATIC_DIR = APP_DIR / "static"

# login.html 由他 session 編輯中 → 明列排除(coverage gap,記於 COVERAGE_GAPS)。
EXCLUDE_FILES = {"login.html"}

API_PREFIX = "/api/v1"  # settings.api_prefix(auth.py:175)——f-string 路由用
ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


# ════════════════════════════════════════════════════════════════════════════
# Part A — 權威路由集(AST over 全 244 個 app/*.py;§5 十規則)
# ════════════════════════════════════════════════════════════════════════════
def _norm_route_path(p: str) -> str:
    """{name} / {name:path} → {}(§5 ⑧);去尾斜線。"""
    out: list[str] = []
    i = 0
    while i < len(p):
        if p[i] == "{":
            j = p.find("}", i)
            if j == -1:
                out.append(p[i:])
                break
            out.append("{}")
            i = j + 1
        else:
            out.append(p[i])
            i += 1
    s = "".join(out)
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
    return s or "/"


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_fstring(node: ast.AST) -> str | None:
    """§5 ⑦:f"{settings.api_prefix}/system/..." → /api/v1/system/...;其餘 FormattedValue→{}。"""
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        elif isinstance(v, ast.FormattedValue):
            inner = v.value
            if isinstance(inner, ast.Attribute) and inner.attr == "api_prefix":
                parts.append(API_PREFIX)
            else:
                parts.append("{}")
        else:
            return None
    return "".join(parts)


def _decorator_receiver_name(attr: ast.Attribute) -> str | None:
    """decorator 的 `<recv>.<method>` 取 recv 末層名。
    §5 ④:@core.live_router.get 是 Attribute(value=Attribute) → 取末層 'live_router'。"""
    recv = attr.value
    if isinstance(recv, ast.Name):
        return recv.id
    if isinstance(recv, ast.Attribute):
        return recv.attr
    return None


def _extract_routes(app_dir: Path) -> tuple[set[tuple[str, str]], dict, list]:
    """回傳 (routes 集合, 診斷 dict, unresolved list)。純 AST,零 import/零副作用。"""
    pyfiles = sorted(app_dir.glob("*.py"))
    trees: dict[str, ast.Module] = {}
    file_prefix: dict[str, dict[str, str]] = {}
    global_prefix: dict[str, str] = {}
    nested_include: list[tuple[str, str]] = []

    # Pass 1:APIRouter(prefix=) 建構子(§5 ②,per-file);paper_router.include_router(§5 ⑤)。
    for f in pyfiles:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        trees[f.name] = tree
        fp: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                fn = call.func
                is_router = (isinstance(fn, ast.Name) and fn.id == "APIRouter") or (
                    isinstance(fn, ast.Attribute) and fn.attr == "APIRouter"
                )
                if is_router:
                    prefix = ""
                    for kw in call.keywords:
                        if kw.arg == "prefix":
                            s = _const_str(kw.value)
                            if s is not None:
                                prefix = s
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            fp[tgt.id] = prefix
                            global_prefix[tgt.id] = prefix
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id != "app"
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                nested_include.append((node.func.value.id, node.args[0].id))
        file_prefix[f.name] = fp

    # 巢狀 include prefix stacking(§5 ⑤:paper_router.include_router(ai_cost_router))
    nested_prefix: dict[str, str] = {}
    for parent, child in nested_include:
        nested_prefix[child] = global_prefix.get(parent, "") + global_prefix.get(child, "")

    def prefix_for(recv: str, fname: str) -> str | None:
        if recv == "app":  # §5 ⑥:@app 絕對路由(含 register_*_legacy_routes 內的 app 參數)
            return ""
        if recv in nested_prefix:
            return nested_prefix[recv]
        fp = file_prefix.get(fname, {})
        if recv in fp:  # per-file 優先(§5 ②:泛名 'router' 在多檔不同 prefix)
            return fp[recv]
        if recv in global_prefix:  # 跨檔命名 router(§5 ③:governance/live_router 側寫)
            return global_prefix[recv]
        return None

    # Pass 2:route decorators(§5 ③ 掃全檔,非 include 清單)
    routes: set[tuple[str, str]] = set()
    unresolved: list[tuple[str, str, str]] = []
    for fname, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                method_attr = dec.func.attr
                recv = _decorator_receiver_name(dec.func)
                if recv is None or not dec.args:
                    continue
                rel = _const_str(dec.args[0])
                if rel is None:
                    rel = _resolve_fstring(dec.args[0])
                if rel is None:
                    continue
                methods: list[str] = []
                if method_attr in ROUTE_METHODS:
                    methods = [method_attr.upper()]
                elif method_attr == "api_route":  # methods=[...] fan-out
                    for kw in dec.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for el in kw.value.elts:
                                s = _const_str(el)
                                if s:
                                    methods.append(s.upper())
                else:
                    continue  # middleware / exception_handler / on_event / websocket 非路由
                if not methods:
                    continue
                prefix = prefix_for(recv, fname)
                if prefix is None:
                    unresolved.append((fname, recv, rel))
                    continue
                full = _norm_route_path(prefix + rel)
                for m in methods:
                    routes.add((m, full))
    diag = {
        "py_files": len(pyfiles),
        "routers_named": len(global_prefix),
        "nested_includes": nested_include,
    }
    return routes, diag, unresolved


AUTHORITATIVE_ROUTES, _ROUTE_DIAG, _UNRESOLVED = _extract_routes(APP_DIR)


def route_matches(method: str, path: str) -> bool:
    """path+method 必須精確對齊 authoritative route。"""
    return (method, path) in AUTHORITATIVE_ROUTES


# ════════════════════════════════════════════════════════════════════════════
# Part B — GUI call-site 抽取(§5:wrapper 呼叫 + raw fetch;balanced-paren arg0)
# ════════════════════════════════════════════════════════════════════════════
# 方法推斷:apiGet/apiPost/ocPost 固定;ocApi/ocFetchWithCsrf/fetch 讀 opts.method 否則 GET。
_WRAPPERS: dict[str, str | None] = {
    "apiGet": "GET",
    "apiPost": "POST",
    "ocPost": "POST",
    "ocApi": None,
    "ocFetchWithCsrf": None,
    "fetch": None,
}
_CALL_RE = re.compile(r"(?<![.\w])(apiGet|apiPost|ocPost|ocApi|ocFetchWithCsrf|fetch)\s*\(")
# per-file const:`const NAME = '/literal'`(單行字面);call-site 用裸名時解析。
_CONST_RE = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(['"`][^'"`\n]*['"`])\s*;"""
)
_METHOD_OPT_RE = re.compile(r"method\s*:\s*['\"]?([A-Za-z]+)")
_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")


def _balanced_call_body(text: str, open_paren_idx: int) -> tuple[str, int] | None:
    """從 '(' 起 balanced-paren 取內文;跳過字串字面。"""
    depth = 0
    i = open_paren_idx
    quote: str | None = None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : i], i
        i += 1
    return None


def _split_top_args(s: str) -> list[str]:
    """top-level 逗號分割(跳過字串 / 括號巢狀)。"""
    args: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(s):
        c = s[i]
        if quote:
            cur.append(c)
            if c == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            cur.append(c)
        elif c in "([{":
            depth += 1
            cur.append(c)
        elif c in ")]}":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    if cur:
        args.append("".join(cur))
    return args


def _tokenize_arg0(s: str) -> list[tuple[str, str]]:
    """把 arg0 表達式切成 ('lit', 內容) | ('expr', 文字);處理字串 / template / concat。
    template `${…}`→{};concat 的非字面 token 之後以 {} 代入。"""
    tokens: list[tuple[str, str]] = []
    i = 0
    s = s.strip()
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c in "'\"`":
            quote = c
            j = i + 1
            buf: list[str] = []
            while j < len(s):
                d = s[j]
                if d == "\\" and j + 1 < len(s):
                    buf.append(s[j : j + 2])
                    j += 2
                    continue
                if d == quote:
                    break
                buf.append(d)
                j += 1
            content = "".join(buf)
            if quote == "`":  # template literal:${…} → {}
                content = re.sub(r"\$\{[^{}]*\}", "{}", content)
                content = re.sub(r"\$\{.*?\}", "{}", content)
            tokens.append(("lit", content))
            i = j + 1
            continue
        if c == "+":  # concat 連接子
            i += 1
            continue
        # 非字面表達式 token(識別子 / 呼叫 / 括號):吃到下一個 top-level '+' 或結束
        depth = 0
        j = i
        while j < len(s):
            d = s[j]
            if d in "([{":
                depth += 1
            elif d in ")]}":
                depth -= 1
            elif d == "+" and depth == 0:
                break
            j += 1
        tokens.append(("expr", s[i:j].strip()))
        i = j
    return tokens


def _truncate_glued_param(path: str) -> str:
    """glued-{}:一個 {} 若非完整 path segment(前字元非 '/'),代表 query/後綴變數
    (如 '/x/closed-pnl' + qs → '/x/closed-pnl{}'),自該 {} 起截斷當 query。"""
    i = path.find("{}")
    while i != -1:
        prev_ok = i > 0 and path[i - 1] == "/"
        after = path[i + 2 :]
        after_ok = after == "" or after.startswith("/")
        if prev_ok and after_ok:  # clean segment param,保留
            i = path.find("{}", i + 2)
            continue
        path = path[:i]
        break
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _normalize_arg0(arg0: str, const_map: dict[str, str]) -> tuple[str, str | None]:
    """回傳 (kind, path)。kind ∈ static / param / dynamic / nonapi。
    normalize:${…}→{}、strip ?query/#frag、trailing-slash、glued-{} query 截斷。"""
    s = arg0.strip()
    if _IDENT_RE.fullmatch(s):  # 裸識別子 → per-file const 解析
        if s in const_map:
            s = const_map[s]
        else:
            return ("dynamic", None)  # 無法解析的 base(wrapper 參數 / 計算變數)
    toks = _tokenize_arg0(s)
    if not toks:
        return ("dynamic", None)
    parts = ["{}" if t[0] == "expr" else t[1] for t in toks]
    path = "".join(parts)
    if not path.startswith("/"):
        return ("nonapi", None)  # 相對路徑 / 外部 URL
    if path.startswith("/static/"):
        return ("nonapi", None)  # 靜態資產抓取(cards fragment 等),非 API 路由
    path = path.split("?", 1)[0].split("#", 1)[0]
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    path = _truncate_glued_param(path)
    if not path.startswith("/"):
        return ("nonapi", None)
    return ("param" if "{}" in path else "static", path or "/")


def _infer_method(name: str, args: list[str]) -> str:
    fixed = _WRAPPERS[name]
    if fixed:
        return fixed
    if len(args) >= 2:  # ocApi/ocFetchWithCsrf/fetch:讀 opts.method
        m = _METHOD_OPT_RE.search(args[1])
        if m:
            return m.group(1).upper()
    return "GET"


class _InlineScriptExtractor(HTMLParser):
    """抽 HTML 內 inline <script> 塊(濾 type=module/application-json);記塊起始行。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[tuple[int, str]] = []
        self._in = False
        self._skip = False
        self._buf: list[str] = []
        self._start = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            d = {k.lower(): (v or "") for k, v in attrs}
            typ = d.get("type", "").lower()
            self._skip = typ in ("module", "application/json", "application/ld+json")
            self._in = True
            self._buf = []
            self._start = self.getpos()[0]

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in:
            if not self._skip:
                self.scripts.append((self._start, "".join(self._buf)))
            self._in = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in:
            self._buf.append(data)


def _iter_gui_units() -> list[tuple[str, str, int]]:
    """(rel, text, line_offset)。掃 static/*.js + js/*.js + static/*.html + cards/*.html
    的 inline <script>;login.html 排除。"""
    units: list[tuple[str, str, int]] = []
    js_files = sorted(STATIC_DIR.glob("*.js")) + sorted((STATIC_DIR / "js").glob("*.js"))
    for p in js_files:
        if p.name in EXCLUDE_FILES:
            continue
        units.append((p.relative_to(STATIC_DIR).as_posix(), p.read_text(encoding="utf-8"), 0))
    html_files = sorted(STATIC_DIR.glob("*.html")) + sorted((STATIC_DIR / "cards").glob("*.html"))
    for p in html_files:
        if p.name in EXCLUDE_FILES:
            continue
        rel = p.relative_to(STATIC_DIR).as_posix()
        ex = _InlineScriptExtractor()
        ex.feed(p.read_text(encoding="utf-8"))
        ex.close()
        for start_line, block in ex.scripts:
            units.append((rel, block, start_line - 1))
    return units


class CallSite:
    __slots__ = ("rel", "line", "method", "kind", "path", "raw")

    def __init__(self, rel, line, method, kind, path, raw):
        self.rel = rel
        self.line = line
        self.method = method
        self.kind = kind
        self.path = path
        self.raw = raw

    def where(self) -> str:
        return f"{self.rel}:{self.line}"


def _extract_callsites() -> list[CallSite]:
    out: list[CallSite] = []
    for rel, text, off in _iter_gui_units():
        const_map = {mm.group(1): mm.group(2) for mm in _CONST_RE.finditer(text)}
        for m in _CALL_RE.finditer(text):
            name = m.group(1)
            body = _balanced_call_body(text, m.end() - 1)
            if body is None:
                continue
            inside, _end = body
            args = _split_top_args(inside)
            if not args or not args[0].strip():
                continue
            kind, path = _normalize_arg0(args[0], const_map)
            method = _infer_method(name, args)
            line = text.count("\n", 0, m.start()) + 1 + off
            out.append(CallSite(rel, line, method, kind, path, args[0].strip()[:70]))
    return out


CALL_SITES = _extract_callsites()
API_CALL_SITES = [c for c in CALL_SITES if c.kind in ("static", "param")]
DYNAMIC_CALL_SITES = [c for c in CALL_SITES if c.kind == "dynamic"]


# ════════════════════════════════════════════════════════════════════════════
# Part C — allowlist(checked-in 明列常量;增/減都過 code review)
# ════════════════════════════════════════════════════════════════════════════
# DYNAMIC_DEBT_ALLOWLIST:GUI 以 concat 動態組路徑,且**後端該 family 是具體(非-param)路由**
# → 動態 /{} 無法 exact-match 任何後端路由(後端有 /control/demo/{validate,arm,...} 而非
# /control/demo/{action})。各已人工核到真 backend family,列 declared debt(絕不靜默通過)。
#
# ★ 與 5a 分區差異(誠實報告):5a 列 14 條 concat debt;本檔 full-concat-resolver(把
#   '/a/'+x+'/close' 解為 /a/{}/close)exact-match 其中 9 條到真 backend param 路由 →
#   那 9 條現為 MATCHED(見 RESOLVED_CONCAT_SEEDS),**不**入 debt allowlist(避免 shadow
#   ratchet 洞:若後端刪該路由,GUI 呼叫應轉紅而非被 debt 靜默放行)。只餘下列 5 條真 debt。
DYNAMIC_DEBT_ALLOWLIST: set[tuple[str, str]] = {
    # tab-settings.html:842  '/api/v1/control/demo/' + action
    #   → 後端具體:/control/demo/{validate,arm,enable,relock}。ticket: P1.0-5(可留 debt)。
    ("POST", "/api/v1/control/demo/{}"),
    # tab-learning.html:231  '/api/v1/learning/auto/' + scan
    #   → 後端具體:/learning/auto/{scan-hypotheses,scan-lessons,scan-observations}。
    ("POST", "/api/v1/learning/auto/{}"),
    # tab-paper.html:402  '/api/v1/paper/session/' + action
    #   → 後端具體:/paper/session/{start,stop,pause,resume,status,reauth,stop-all}。
    ("POST", "/api/v1/paper/session/{}"),
    # tab-demo.html:1290  '/api/v1/strategy/demo/session/' + action
    #   → 後端具體:/strategy/demo/session/{start,stop,pause,resume,status}。
    ("POST", "/api/v1/strategy/demo/session/{}"),
    # tab-strategy.html:371  '/api/v1/strategy/' + id + '/' + action
    #   → 後端無 /strategy/{id}/{action} param 路由(具體 action 端點分散)。
    ("POST", "/api/v1/strategy/{}/{}"),
}

# RESOLVED_CONCAT_SEEDS:5a 列為 concat debt、本檔解析器已對齊真後端 param 路由的 9 條。
# 留檔=①保 5a ticket 追溯 ②ratchet-hole 收緊:各斷言 ∈ authoritative(見對應 test);
# 若未來後端刪任一路由,該斷言轉紅 → 不會被 debt 靜默吞掉。
RESOLVED_CONCAT_SEEDS: set[tuple[str, str]] = {
    ("POST", "/api/v1/control/product-family/{}/config"),  # tab-settings:1119
    ("POST", "/api/v1/learning/review/{}/decide"),         # tab-learning:219
    ("POST", "/api/v1/live/positions/{}/close"),           # tab-live.js:1201
    ("DELETE", "/api/v1/paper/layer2/providers/{}"),       # tab-ai:930
    ("POST", "/api/v1/paper/positions/{}/close"),          # tab-paper:604
    ("GET", "/api/v1/settings/api-key/{}"),                # tab-settings:1291
    ("POST", "/api/v1/settings/api-key/{}"),               # tab-settings:1411
    ("DELETE", "/api/v1/strategy/{}"),                     # tab-strategy:360
    ("POST", "/api/v1/strategy/demo/positions/{}/close"),  # tab-demo:1419
}

# KNOWN_MISMATCH_ALLOWLIST:GUI 呼一條後端**無**的路由(真 drift / forward-ref),各附處置。
KNOWN_MISMATCH_ALLOWLIST: set[tuple[str, str]] = {
    # M1 已解決(reconcile Path B):govPostReconcile 改為伺服器端組裝快照,前端不再呼叫
    #   GET /api/v1/paper/status → drift 從源頭消失,ratchet 自動收緊(移除本列)。
    # M2 handoff_helper.js:363  GET /api/v1/replay/handoff/state —— known forward-ref(HIGH)。
    #   碼自證「Endpoint not yet shipped, Wave 8 sibling S13 in flight」+ graceful pending。
    #   處置=allowlist(Wave 8 closure 建後端路由時刪),非 bug。
    ("GET", "/api/v1/replay/handoff/state"),
}

ACCEPTED = AUTHORITATIVE_ROUTES | DYNAMIC_DEBT_ALLOWLIST | KNOWN_MISMATCH_ALLOWLIST

# 明列 coverage gap(靜態不可檢,非失敗;供 PM / verifier 追溯):
#   · login.html 排除(他 session 編輯中)。
#   · dynamic-base call-site(wrapper 實作內部 path/url 參數 + risk-tab.js:715 計算 ternary
#     _url = paper/risk/config 或 /engine/{}):路徑由變數決定,靜態不可解 → 見 DYNAMIC_CALL_SITES。
#   · 只證 path+method 形狀;response 消費 / auth / 200-vs-4xx / 動態真值 = NEEDS-LINUX。
COVERAGE_GAPS = ("login.html(excluded)", "dynamic-base call-sites", "runtime response/auth/status")


# ════════════════════════════════════════════════════════════════════════════
# Part D — 測試
# ════════════════════════════════════════════════════════════════════════════
def test_authoritative_route_scan_floor() -> None:
    """權威路由掃描下限(anti-vacuous):防 AST glob / 解析壞掉導致空集空綠。
    現況 334 distinct(method,path);floor=300。同時 0 unresolved receiver。"""
    assert len(AUTHORITATIVE_ROUTES) >= 300, (
        f"權威路由抽取數異常少(={len(AUTHORITATIVE_ROUTES)},預期 ~334);"
        f"AST 掃描 / prefix 解析疑壞掉。診斷={_ROUTE_DIAG}"
    )
    assert not _UNRESOLVED, (
        "有 route decorator 的 router prefix 無法解析(§5 陷阱?):\n"
        + "\n".join(f"  {f}:{recv} rel={rel}" for f, recv, rel in _UNRESOLVED[:20])
    )


def test_gui_callsite_scan_floor() -> None:
    """GUI call-site 掃描下限(anti-vacuous):防 wrapper regex / balanced-paren 壞掉空綠。
    現況 static+param ~261 sites;floor=200。"""
    assert len(API_CALL_SITES) >= 200, (
        f"GUI API call-site 抽取數異常少(={len(API_CALL_SITES)},預期 ~261);"
        f"wrapper 掃描或 arg0 抽取疑壞掉。kinds={Counter(c.kind for c in CALL_SITES)}"
    )


def test_matched_floor_not_vacuous() -> None:
    """真 matched 下限(anti-vacuous):防 matcher 被架空成恆綠(全部落 allowlist / 空過)。
    現況 ~174 distinct matched;floor=150。"""
    matched_distinct = {
        (c.method, c.path) for c in API_CALL_SITES if route_matches(c.method, c.path)
    }
    assert len(matched_distinct) >= 150, (
        f"真 matched (GUI↔route) distinct 數異常少(={len(matched_distinct)});"
        "matcher 疑被架空。這防「allowlist 吞一切 / route 集空」的空洞綠。"
    )


def test_fetch_route_alignment_ratchet() -> None:
    """★ 主 ratchet:每個 GUI static/param (method,path) ∈ authoritative ∪ DEBT ∪ KNOWN_MISMATCH。
    新增未匹配 = 失敗並點名 檔:行 + method + path(§0 終態 criterion-3)。

    現況全覆蓋(254 matched sites + 5 load-bearing debt + 2 known-mismatch)。修好 M1/清 debt =
    刪對應 allowlist 列(收緊);絕不靜默放寬。真新 unmatched = drift/typo,轉紅點名。
    """
    offenders: list[str] = []
    for c in API_CALL_SITES:
        if route_matches(c.method, c.path):
            continue
        if (c.method, c.path) in DYNAMIC_DEBT_ALLOWLIST:
            continue
        if (c.method, c.path) in KNOWN_MISMATCH_ALLOWLIST:
            continue
        offenders.append(f"  {c.where():40} {c.method:6} {c.path}   (arg0={c.raw!r})")
    assert not offenders, (
        "GUI fetch↔route 對齊 ratchet 失敗:下列 GUI 呼叫路徑不在 "
        "authoritative ∪ DYNAMIC_DEBT ∪ KNOWN_MISMATCH。\n"
        "= GUI 呼一條後端沒有的路由(route 改名漏改 GUI / typo / 新 drift)。\n"
        "修法:①GUI typo→改 GUI ②後端真缺→建路由或列 KNOWN_MISMATCH(附 ticket)\n"
        "③真動態 concat→列 DYNAMIC_DEBT(附 backend family)。勿為湊綠弱化 matcher。\n"
        + "\n".join(offenders)
    )


def test_resolved_concat_seeds_covered_by_authoritative() -> None:
    """ratchet-hole 收緊:5a 列為 concat-debt、本檔解析器對齊真路由的 9 條,各 ∈ authoritative。
    若未來後端刪任一路由,此處轉紅(而非被 debt allowlist 靜默吞掉)。"""
    missing = sorted(s for s in RESOLVED_CONCAT_SEEDS if s not in AUTHORITATIVE_ROUTES)
    assert not missing, (
        "先前對齊到真後端路由的 concat call-site 現已無對應 authoritative 路由"
        "(後端路由被刪 / 改名?):\n"
        + "\n".join(f"  {m} {p}" for m, p in missing)
        + "\n若確為後端下線 → 該 GUI 呼叫需改為 KNOWN_MISMATCH 並開 ticket。"
    )


def test_debt_allowlist_entries_are_load_bearing() -> None:
    """DEBT 每列必須「真 load-bearing」:不在 authoritative(否則是 shadow 冗餘=ratchet 洞)。
    防未來把已對齊的路由誤塞 debt 而弱化守衛。"""
    shadow = sorted(s for s in DYNAMIC_DEBT_ALLOWLIST if route_matches(*s))
    assert not shadow, (
        "DYNAMIC_DEBT_ALLOWLIST 有已被 authoritative 覆蓋的冗餘列(shadow ratchet 洞,應刪):\n"
        + "\n".join(f"  {m} {p}" for m, p in shadow)
    )


def test_known_mismatch_entries_are_genuinely_absent() -> None:
    """KNOWN_MISMATCH 每列必須後端真無此路由(否則 mismatch 已修,應刪列=收緊)。"""
    resolved = sorted(s for s in KNOWN_MISMATCH_ALLOWLIST if route_matches(*s))
    assert not resolved, (
        "KNOWN_MISMATCH_ALLOWLIST 有已存在於 authoritative 的列(drift 已修?應刪該列):\n"
        + "\n".join(f"  {m} {p}" for m, p in resolved)
    )


def test_route_extractor_is_substantive() -> None:
    """route 抽取語義釘死(anti-vacuous + §5 陷阱回歸):合成模組驗
    ① APIRouter(prefix=) ② 兩層 @core.live_router.get(§5 ④)③ api_route methods fan-out
    ④ @app 絕對 ⑤ f-string api_prefix(§5 ⑦)。並錨真樹已知路由存在。"""
    synthetic = (
        "from fastapi import APIRouter\n"
        "live_router = APIRouter(prefix='/api/v1/live')\n"
        "gen_router = APIRouter(prefix='/api/v1/gen')\n"
        "app = None\n"
        "@core.live_router.get('/session/status')\n"      # 兩層 attr → 末層 live_router
        "def a():\n    pass\n"
        "@gen_router.api_route('/multi', methods=['GET', 'POST'])\n"  # fan-out
        "def b():\n    pass\n"
        "@app.get('/console')\n"                          # @app 絕對
        "def c():\n    pass\n"
        "@app.post(f'{settings.api_prefix}/system/x')\n"  # f-string
        "def d():\n    pass\n"
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "syn.py").write_text(synthetic, encoding="utf-8")
        routes, _diag, unresolved = _extract_routes(Path(td))
    assert ("GET", "/api/v1/live/session/status") in routes, "兩層 @core.live_router 解析壞(§5 ④)"
    assert ("GET", "/api/v1/gen/multi") in routes and ("POST", "/api/v1/gen/multi") in routes, (
        "api_route methods fan-out 壞"
    )
    assert ("GET", "/console") in routes, "@app 絕對路由解析壞(§5 ⑥)"
    assert ("POST", "/api/v1/system/x") in routes, "f-string api_prefix 解析壞(§5 ⑦)"
    assert not unresolved, f"合成模組不應有 unresolved:{unresolved}"

    # 錨真樹已知路由(掃描面真連上實碼):
    for known in [
        ("GET", "/api/v1/paper/session/status"),
        ("POST", "/api/v1/live/positions/{}/close"),
        ("GET", "/api/v1/openclaw/status"),
    ]:
        assert known in AUTHORITATIVE_ROUTES, f"真樹已知路由缺失(抽取疑漏):{known}"


def test_gui_normalizer_is_substantive() -> None:
    """GUI normalizer/matcher 語義釘死(anti-vacuous + substantive-detector)。
    含 §5 全部 normalize 分支 + 合成假路徑必被 gate 抓。"""
    cm = {"EP": "'/api/v1/x/status'"}
    # static literal
    assert _normalize_arg0("'/api/v1/paper/session/status'", {}) == ("static", "/api/v1/paper/session/status")
    # template ${…} → {}
    assert _normalize_arg0("`/api/v1/learning/review/${id}/decide`", {}) == (
        "param",
        "/api/v1/learning/review/{}/decide",
    )
    # concat 全解析 → param
    assert _normalize_arg0("'/api/v1/live/positions/' + sym + '/close'", {}) == (
        "param",
        "/api/v1/live/positions/{}/close",
    )
    # concat query-var glued → 截斷當 query(static)
    assert _normalize_arg0("'/api/v1/live/closed-pnl' + qs", {}) == (
        "static",
        "/api/v1/live/closed-pnl",
    )
    # literal query strip
    assert _normalize_arg0("'/api/v1/earn/records?' + qs", {}) == ("static", "/api/v1/earn/records")
    # const 解析
    assert _normalize_arg0("EP", cm) == ("static", "/api/v1/x/status")
    # /static asset → nonapi
    assert _normalize_arg0("'/static/cards/dl3_card.html'", {})[0] == "nonapi"
    # 相對 / 外部 → nonapi
    assert _normalize_arg0("'relative/thing'", {})[0] == "nonapi"
    # 裸變數(wrapper 參數)→ dynamic
    assert _normalize_arg0("path", {})[0] == "dynamic"

    # method 推斷
    assert _infer_method("apiGet", ["'/x'"]) == "GET"
    assert _infer_method("apiPost", ["'/x'", "{}"]) == "POST"
    assert _infer_method("ocApi", ["'/x'", "{ method: 'DELETE' }"]) == "DELETE"
    assert _infer_method("ocApi", ["'/x'"]) == "GET"

    # matcher 有牙 + substantive-detector:合成一個後端不存在的假路徑 → 必判不匹配。
    assert route_matches("GET", "/api/v1/paper/session/status"), "matcher 對真路由誤判不匹配"
    fake = ("GET", "/api/v1/__totally__/__fake__/route")
    assert not route_matches(*fake), "matcher 被架空:假路徑竟判匹配(gate 無牙)"
    # 若假路徑出現在 GUI,主 ratchet 必抓(既不在 authoritative 也不在 allowlist)。
    assert fake[0:2] not in ACCEPTED, "假路徑不應落任何 allowlist(gate 空洞?)"
