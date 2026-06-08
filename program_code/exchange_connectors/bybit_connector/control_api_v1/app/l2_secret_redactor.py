"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh D3 取證帳本「寫入前 secret 消毒器」（PA 設計 §B / §D.1.1，
  E3-HIGH gate）。把 secret-pattern（API key / bearer / HMAC sign /
  authorization.json 物料 / secret-slot / DB DSN·密碼 / 私有 URL·IP / JWT）從 L2
  的 FULL system_prompt / input_context / raw_response / final_summary 掃成
  `[REDACTED:<kind>]` token，在它們進入 append-only durable store 之前。

  偵測 vs 存入文本（v3 store-original-by-span，§B.5 fix-round 不變量）：
    偵測在「正規化文本」上跑（NFKC + strip zero-width/control + URL-decode 一次），
    用來抓編碼規避；但 redactor 存入 ledger 的文本是「原文，僅實際 secret span 被
    `[REDACTED:*]`」——正規化只服務偵測，絕不改寫存入文本。零-secret 輸入（中文
    全形標點、合法 %2F/%20、zero-width）存入須 byte-identical（principle 8 =
    ledger 可重建；正規化過的文本 != 原文會毀 forensic 重建）。實作：建
    normalized→original offset map，在 normalized 空間偵測 span → 映回 original
    offset → 在 original 文本遮。

  封死的向量（v4，keyword-gated + 結構臂；operator 2026-06-08 拍板 A）：
    keyword（api_key/secret/Authorization/Bearer/sign/password/hmac/signing_key/
      auth_signing_key/private_key/...；v4 LOW-1 補全 named critical 資產）
    + 結構 keyword-free（DSN scheme://user:pw@、JWT eyJ...、私有 IPv4·IPv6）
    + 編碼規避（NFKC、strip zero-width/control、URL-decode 一次——僅供偵測）
    + 私有拓撲（trade-core/.local/私有 IP）
    + JSONB key-name（dict key ∈ 敏感名集 → 不論 value 結構一律遮其 value）。

  v4 fast-path gate fix（CRITICAL，Finding 1）：判斷是否走 slow-path 的 gate 改用
    strip 謂詞 `_is_control_or_format` 本身（_needs_offset_map），gate-set 與 strip-set
    結構上恆相等。前一版用手列 codepoint regex 當 gate，漏 136 個會被 strip 但 regex
    未涵蓋且 NFKC-stable 的 strip-set 字元（U+180E/U+061C/U+2066-2069/U+E00xx tag 區等）→
    這些字元切斷 keyword 的 secret 走 fast-path 在 raw 文本偵測（不 strip）→ 漏遮逐字
    入庫洩漏。改為複用 strip 謂詞後 drift 不可能再發生。

  v4 size cap（DoS guard，LOW-2）：偵測前對輸入文本截斷於 256KB（高位，遠大於現實
    L2 response）+ logged truncation marker。bound store-original per-char 迴圈在
    degenerate 全-evasion 輸入下的 super-linear 成本 + bound 儲存。

  殘留（誠實文件化，operator 2026-06-08 拍板 A）：
    「naked-context-free 高熵」串——bare alnum token / bare 64-hex / bare base64
    blob，無 adjacent keyword 且無 JWT/DSN/IP 結構——在資訊論上無法與合法高熵識別碼
    （git-SHA / sha256 / config-flag / model-id）區分而不大量誤遮（前一輪 blanket
    高熵臂實測誤遮 29% 合法 forensic 內容，毀 ledger 可重建性 = D3 目的本身）。
    本 redactor 封死全部「具名」critical 資產（皆帶其慣常 keyword/結構，真實流程
    幾乎必帶）；truly-naked 殘留的最佳解在 P3 source-side（產生端不把裸密鑰寫進
    prompt/summary），非 redactor 端大量誤遮。

主要函數：
  - redact(text) -> RedactResult：偵測在 normalized 文本，遮在 original 文本，回
    (text=original-redacted, kinds_hit, redactor_version)。
  - redact_jsonb(obj)：對 JSONB-like 結構遞迴消毒；string leaf 過 redact()，
    dict 並對「敏感 key」一律遮其 value（不論結構）。
  - REDACTOR_VERSION：版本字串，任何 pattern-set 變更必 bump（寫入 ledger 欄位）。

依賴：標準庫 re / unicodedata / urllib.parse / dataclasses
  （純函數，無 DB / 無 provider / 無 IO）。

硬邊界：
  - store-original-by-span（§B.5 不變量）：存入 ledger 的文本恆為原文僅 secret span
    被遮；零-secret 輸入存入 byte-identical（NFKC/url-decode/strip 只用於偵測，不改
    寫存入文本）；sha256 算在此「原文-遮-span」上（writer 仍 hash redactor.text）。
  - 確定性 + 冪等：對已消毒文本再跑 redact() 為 no-op（`[REDACTED:*]` token 不被
    任何 pattern 命中）；同輸入同輸出（無隨機、無時間）。設計 §B.2。
  - 為何必須在「寫入路徑前」跑且 sha256 算在已消毒文本上：raw exception / stack /
    DSN 絕不可 verbatim 落進難以清除的 append-only 取證庫（root principle 8
    reconstructable + CLAUDE §四 signed-auth material never leak）。
  - 本模塊只「遮罩已落入文本的 secret」，不取代 error_sanitize（後者管
    str(e)→classified reason_code 那半）；D3 writer 兩者併用（hybrid）。
  - keyword-gated + 結構臂（operator A）：非 keyword/非結構的 bare 高熵串不再被遮
    （回 PA LOCKED §B.2 行為，避免誤遮合法高熵識別碼毀 ledger 可重建性）。
  - ReDoS：所有 regex 無 catastrophic backtracking（避免巢狀量詞 / 重疊
    alternation）；re-E3 壓測 200K-400K payload <50ms 軟標。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

logger = logging.getLogger("l2_secret_redactor")

# 版本：任何 pattern-set 變更必 bump（寫入 agent.l2_calls.redactor_version）。
# v2→v3：(1) 移除 blanket bare 高熵臂（越過 PA LOCKED §B.2 只授權 keyword-gated 高熵；
#        前一輪實測誤遮 29% 合法 forensic 內容，operator 拍板 A 回 keyword-gated）；
#        (2) store-original-by-span：偵測在 normalized 文本、遮在 original 文本，
#        零-secret 輸入存入 byte-identical（NFKC/url-decode/strip 只供偵測）。
# v3→v4：(1) CRITICAL fast-path gate fix（gate-set==strip-set by construction，
#        補洩漏 136 個被 strip 但 regex 漏的 strip-set 字元）；(2) keyword-set 補全
#        （hmac/signing/auth/裸 secret/private_key）；(3) raw 文本 size cap（DoS guard）。
REDACTOR_VERSION = "l2_redactor.v4"

# 取代 token：穩定、forensic-useful（知道有 kind X 的 secret 曾在此）但不含 secret。
# 冪等性靠結構達成（非用 token regex 排除）：pattern arm 要求 scheme/keyword/結構，
# [REDACTED:*] token 皆不符。
_TOKEN_FMT = "[REDACTED:{kind}]"

# 高位 size cap（v4 LOW-2，DoS guard）：偵測前對輸入文本截斷。理由：store-original
# 的 slow-path per-char Python 迴圈在 degenerate 全-evasion 輸入下是 super-linear
# （實測 ~n^1.7，800K 全-evasion 9.4s），且未消毒文本不應無上限落 durable store。
# 256KB 遠大於任何現實 L2 response（realistic 響應 <<256KB），只 bound 病態/濫用輸入
# 不影響 full-forensic 目標；對齊既有 cap 紀律（final_summary[:2000] / str(e)[:500]）。
# 超過則截斷 + 留 logged truncation marker（forensic 可見曾截斷 + 原長）。
_MAX_REDACT_INPUT_CHARS = 256 * 1024  # 262144
_TRUNCATION_MARKER_FMT = "…[TRUNCATED:{n} chars]"
# 冪等性：已截斷文本（== 256KB + marker）長度本就 >cap，再跑 redact() 不可二次截斷
# （否則丟 marker + 換 n，破壞「已消毒文本再跑為 no-op」硬邊界）。偵測尾端 marker →
# 視為已 cap，跳過再截。marker 無 keyword/結構故偵測層本就不會誤遮其內容。
_TRUNCATION_MARKER_TAIL_RE = re.compile(r"…\[TRUNCATED:\d+ chars\]$")

# 零寬 / BOM / 其他易被用來切斷 keyword 的隱形字元（NFKC 後仍殘留者另 strip）。
# U+200B-200D ZW(space/non-joiner/joiner)、U+FEFF BOM、U+2060 word-joiner、
# U+00AD soft-hyphen、U+180E、U+200E/200F 方向標記。
_ZERO_WIDTH_CHARS = frozenset(
    "​‌‍⁠﻿­᠎‎‏"
)


def _t(kind: str) -> str:
    return _TOKEN_FMT.format(kind=kind)


def _is_control_or_format(ch: str) -> bool:
    """是否為 C0/C1 控制或格式字元（保留 \\t \\n \\r 以維持多行 prompt 可讀）。
    為何 strip：控制 / 零寬字元可被插進 keyword 中段（api\\u200b_key=...）以規避
    keyworded arm；偵測前先 strip 讓 keyword 重新連續。"""
    if ch in ("\t", "\n", "\r"):
        return False
    if ch in _ZERO_WIDTH_CHARS:
        return True
    cat = unicodedata.category(ch)
    return cat in ("Cc", "Cf")  # 控制 / 格式字元


def _needs_offset_map(text: str) -> bool:
    """fast-path gate：是否需要建 normalized↔original offset map（走 slow-path）。

    為何 gate-set 必 == strip-set（by construction，CRITICAL fix Finding 1）：
      slow-path 的偵測在「strip 掉所有 `_is_control_or_format` 字元後」的正規化文本
      上跑；fast-path 直接在 raw 文本偵測（不 strip）。若 gate 用「手列 codepoint
      範圍的 regex」判斷是否走 slow-path，該範圍必須恰好涵蓋 `_is_control_or_format`
      會 strip 的全部字元——否則任何「會被 strip 但 gate 漏、且 NFKC-stable」的 Cf
      字元（如 U+180E / U+061C / U+2066-2069 / U+E00xx tag 區）會走 fast-path，在
      raw 文本偵測時 keyword 仍被該字元切斷 → secret 逐字入庫洩漏。
      前一版用手列 regex `_NEEDS_OFFSET_MAP_RE` 正是此 drift（brute-force 實測漏 136
      個 strip-set 字元，全 Unicode 空間 strip-set 共 223 個）。
      故此處「直接複用 strip 謂詞 `_is_control_or_format` 當 gate」，gate-set 與
      strip-set 結構上恆相等，drift 不可能再發生（E2 方向 A）。

    走 slow-path 的三條件（任一為真）：
      1. 含任何 `_is_control_or_format(c)` 為真的字元（== strip-set）。
      2. 含 '%'（可能是 URL-encode 的 secret，slow-path 才會 url-decode-once 偵測）。
      3. 文本非 NFKC-normalized（含全形/相容字元，slow-path 才會 NFKC 後偵測）。
    皆否 → fast-path（normalized == 原文，identity 映射，省 per-char 迴圈，行為等價）。
    is_normalized 是 C-level 快檢；any(...) 對純散文短路（多數真實 payload 走 fast）。
    """
    if "%" in text:
        return True
    if any(_is_control_or_format(c) for c in text):
        return True
    if not unicodedata.is_normalized("NFKC", text):
        return True
    return False


def _normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """掃描前正規化（§B.2.a，僅供偵測）並建 normalized→original offset map。

    為什麼：攻擊面包含「用 Unicode 等價字元 / 零寬切斷 / URL-encode」把 secret
    寫成 pattern 不命中的形。偵測前把文本拉回 canonical 形：
      1. strip zero-width / 控制 / 格式字元（先做，逐字元保留原 index）。
      2. 對每個保留字元做 NFKC normalize（全形→半形、相容字元合一）；NFKC 可能
         把 1 char 展開成多 char（如 ﬁ→fi），每個展開 char 都映回該原字元 index。
      3. URL-decode 一次（%3D→=、%2F→/ …），讓 url-encoded DSN/key 現形；一個
         `%XX` 三元組解成 1 char，映回該三元組的「起始 %」原 index（遮回時整個
         %XX 區域被涵蓋）。

    回 (normalized_text, offset_map)。offset_map[i] = normalized char i 對應的
    original 起始 index；長度 = len(normalized_text)+1（末位哨兵 = len(text)，供
    span 結束 index 映射）。為何不遞迴 url-decode：一次足以揭露常見規避，且避免對
    合法含 `%` 文本過度變形。

    嚴格線性（單遍 strip+NFKC 逐字元，url-decode 用 finditer 線性掃 %XX），無回溯。
    """
    # ── Step 1+2：strip control/zero-width + per-char NFKC，逐字元保留 original index ──
    norm_chars: list[str] = []
    norm_to_orig: list[int] = []
    for orig_idx, ch in enumerate(text):
        if _is_control_or_format(ch):
            continue
        nfkc = unicodedata.normalize("NFKC", ch)
        for nch in nfkc:
            norm_chars.append(nch)
            norm_to_orig.append(orig_idx)
    norm_to_orig.append(len(text))  # 末位哨兵
    stage1 = "".join(norm_chars)

    # ── Step 3：URL-decode 一次（線性掃 %XX），維護 offset map ──
    # 找出所有合法 %XX 三元組；對每個三元組，輸出 1 解碼 char，映回三元組起始的
    # original index（即 stage1 中 '%' 的 norm_to_orig）。非 %XX 區段逐字元複製。
    if "%" not in stage1:
        return stage1, norm_to_orig

    _PCT = re.compile(r"%[0-9A-Fa-f]{2}")
    out_chars: list[str] = []
    out_to_orig: list[int] = []
    pos = 0
    for m in _PCT.finditer(stage1):
        s, e = m.start(), m.end()
        # 複製 [pos, s) 非編碼區段（逐字元，原 index 不變）。
        for j in range(pos, s):
            out_chars.append(stage1[j])
            out_to_orig.append(norm_to_orig[j])
        # 解碼 %XX → 1 char（unquote 單一三元組）。errors=strict 確保非法序列已被
        # _PCT regex 排除（只匹配 hex），故此處恆成功；保險用 try。
        try:
            dec = unquote(m.group(0), errors="strict")
        except Exception:  # noqa: BLE001 — 退回原樣（保留三元組原文），不阻斷偵測
            dec = stage1[s:e]
            for j in range(s, e):
                out_chars.append(stage1[j])
                out_to_orig.append(norm_to_orig[j])
            pos = e
            continue
        for dch in dec:
            out_chars.append(dch)
            out_to_orig.append(norm_to_orig[s])  # 映回三元組起始 '%' 的原 index
        pos = e
    # 複製尾段。
    for j in range(pos, len(stage1)):
        out_chars.append(stage1[j])
        out_to_orig.append(norm_to_orig[j])
    out_to_orig.append(len(text))  # 末位哨兵
    return "".join(out_chars), out_to_orig


# 合併 keyworded 臂的 named-group → kind 映射（見 _PATTERNS 內 "__keyworded__" 條）。
_KW_DISPATCH: list[tuple[str, str]] = [
    ("g_db", "db_dsn"),
    ("g_bearer", "bearer"),
    ("g_auth", "auth_json"),
    ("g_slot", "secret_slot"),
    ("g_api", "api_key"),
]

# 合併結構單-token 臂的 named-group → kind 映射（見 __struct__ pattern）。
_STRUCT_DISPATCH: list[tuple[str, str]] = [
    ("s_jwt", "jwt"),
    ("s_ip6", "private_ip"),
    ("s_ip4", "private_ip"),
    ("s_host", "private_url"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Pattern set（確定性 regex；偵測在 normalized 文本上跑，回報 secret span）。
# v3：keyword-gated + 結構臂；NO blanket bare 高熵臂（operator 2026-06-08 拍板 A）。
# 每條 (compiled_regex, kind_tag, span_extractor)。span_extractor(m) 回
# [(start, end, kind), ...]（normalized 座標），由 redact() 映回 original 後遮。
# ReDoS 註：所有量詞作用於互斥字元類（`[^@\s]` / `[A-Za-z0-9_\-]` 等），
# alternation 無重疊前綴，無巢狀量詞 → 線性匹配，無 catastrophic backtracking。
# ─────────────────────────────────────────────────────────────────────────────

# 私有 IPv4 八位組（10/8、127/8、192.168/16、172.16-31/12、169.254/16、192.0.2/24）。
_PRIV_IPV4 = (
    r"(?:"
    r"10(?:\.\d{1,3}){3}"                      # 10.0.0.0/8
    r"|127(?:\.\d{1,3}){3}"                    # 127.0.0.0/8 loopback
    r"|192\.168(?:\.\d{1,3}){2}"               # 192.168.0.0/16
    r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"  # 172.16.0.0/12
    r"|169\.254(?:\.\d{1,3}){2}"               # 169.254.0.0/16 link-local
    r"|192\.0\.2(?:\.\d{1,3})"                 # 192.0.2.0/24 TEST-NET-1
    r")"
)

# 私有 IPv6：fc00::/7（fc / fd 開頭）、fe80::/10 link-local（fe8/fe9/fea/feb）。
_PRIV_IPV6 = (
    r"(?:"
    r"(?:f[cd][0-9a-f]{0,2}:)(?:[0-9a-f]{0,4}:){1,6}[0-9a-f]{0,4}"  # fc00::/7
    r"|(?:fe[89ab][0-9a-f]?:)(?:[0-9a-f]{0,4}:){1,6}[0-9a-f]{0,4}"  # fe80::/10
    r")"
)


def _spans_db_dsn(m: "re.Match[str]") -> list[tuple[int, int, str]]:
    """DSN：只遮 scheme:// 之後到 @ 的整段 credential（保留 scheme 結構脈絡）。"""
    return [(m.start("cred"), m.end("cred"), "db_dsn")]


def _spans_value_only(kind: str):
    """key=<secret> 形：只遮 value group（保留 key 名 + 分隔符脈絡）。"""
    def _f(m: "re.Match[str]") -> list[tuple[int, int, str]]:
        return [(m.start("v"), m.end("v"), kind)]
    return _f


def _spans_keyworded(m: "re.Match[str]") -> list[tuple[int, int, str]]:
    """合併 keyworded 臂：kind 由命中的具名 keyword group 決定，只遮 value group。"""
    kind = "api_key"
    for grp, k in _KW_DISPATCH:
        if m.group(grp) is not None:
            kind = k
            break
    return [(m.start("v"), m.end("v"), kind)]


def _spans_struct(m: "re.Match[str]") -> list[tuple[int, int, str]]:
    """合併結構臂：依命中的具名 group 決定 kind，遮整個命中 group。"""
    for grp, k in _STRUCT_DISPATCH:
        if m.group(grp) is not None:
            return [(m.start(grp), m.end(grp), k)]
    return []


_PATTERNS: list[tuple["re.Pattern[str]", object]] = [
    # ── 結構臂（keyword-free）：DSN scheme（§B.2.b）。多 driver scheme。
    # postgres/postgresql/mysql/mariadb/redis/rediss/amqp/amqps/mongodb(+srv)。
    (
        re.compile(
            r"(?P<scheme>(?:postgres(?:ql)?|mysql|mariadb|redis(?:s)?|amqps?|"
            r"mongodb(?:\+srv)?)://)"
            r"(?P<cred>[^@\s/]+)@",
            re.IGNORECASE,
        ),
        _spans_db_dsn,
    ),
    # bearer：Authorization: Bearer <token> / Authorization: <...>（只遮 value）。
    (
        re.compile(
            r"(?P<k>Authorization)(?P<sep>\s*[:=]\s*)(?P<v>(?:Bearer\s+)?\S+)",
            re.IGNORECASE,
        ),
        _spans_value_only("bearer"),
    ),
    # bearer：裸 "Bearer <token>"（降下限至 6，keyworded 命中即遮不設長下限 §B.2.d）。
    (
        re.compile(r"\bBearer\s+(?P<v>[A-Za-z0-9._\-]{6,})"),
        _spans_value_only("bearer"),
    ),
    # ── 合併 keyworded key=value 臂（單遍掃描）。kind 由命中的具名 keyword group
    # 決定（_KW_DISPATCH）。降下限：keyworded 命中即遮，value ≥4（E3：api_key= 值
    # <16 漏 §B.2.d）。只遮 value group（保留 key 名脈絡）。ReDoS-safe：alternation
    # 是互斥 literal keyword 前綴，value 量詞作用於互斥字元類，無回溯。
    # 註（v4 LOW-1）：補上 named critical 資產 keyword 使設計 §B.5「every named
    # critical asset still caught」屬實 + 對齊 secret-leak-detection skill Pattern-A：
    # HMAC（hmac_key/hmac）、signing 物料（auth_signing_key/signing_key/signing_secret/
    # auth_key）、裸 secret、private_key。alternation 序：每組「長/具體 keyword 先於短
    # 前綴」（如 hmac_key 先於 hmac、auth_signing_key 先於 signing_key），裸 secret 置
    # g_api 末作 catch-all——避免短前綴先匹配後 sep 失敗才回溯（ReDoS-safe，少回溯）。
    (re.compile(
        r"(?P<k>"
        # db_dsn 密碼類
        r"(?P<g_db>PGPASSWORD|password|passwd|pwd)"
        # bearer：HMAC sign / x-bapi header / HMAC key 物料
        r"|(?P<g_bearer>X-BAPI-SIGN|X-BAPI-API-KEY|hmac[_-]?key|hmac|sign)"
        # auth_json：authorization.json 物料 + auth/signing 簽章金鑰類
        r"|(?P<g_auth>signature|signed_payload|approval_token|approved_by_token|"
        r"auth[_-]?signing[_-]?key|signing[_-]?secret|signing[_-]?key|auth[_-]?key)"
        # secret_slot
        r"|(?P<g_slot>secret_slot|slot_secret|secret_slot_material)"
        # api_key：相鄰 api_key/apiKey/secret/access_token/token/private_key keyword
        # （裸 secret 置末作 catch-all，前序更具體者優先匹配）
        r"|(?P<g_api>api[_-]?key|apiKey|api[_-]?secret|secret[_-]?key|"
        r"access[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key|"
        r"token|secret)"
        r")"
        r"(?P<sep>\s*[=:]\s*\"?)(?P<v>[A-Za-z0-9+/=._\-]{4,})",
        re.IGNORECASE,
    ), _spans_keyworded),
    # ── 合併結構單-token 臂（JWT / 私有 IPv6 / 私有 IPv4 / 內部 host·.local）。
    # kind 由命中的具名 group 決定（_STRUCT_DISPATCH）。IPv6 排 IPv4 前以免被部分
    # 吃掉。ReDoS-safe：各 alternative 字元類互斥、量詞有界、無巢狀回溯。
    # 註（v3）：JWT/DSN/IP 是「可分辨、低誤遮」的結構臂（符 PA §B.2 結構臂精神），
    # 保留；blanket bare 高熵臂已移除（operator A）。
    (re.compile(
        r"(?P<s_jwt>\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
        r"|(?P<s_ip6>" + _PRIV_IPV6 + r")"
        r"|\b(?P<s_ip4>" + _PRIV_IPV4 + r")\b"
        r"|\b(?P<s_host>trade-core|[A-Za-z0-9\-]+\.local)\b",
        re.IGNORECASE,
    ), _spans_struct),
]


def _detect_spans(norm_text: str) -> tuple[list[tuple[int, int, str]], set[str]]:
    """在 normalized 文本上跑全部 pattern arm，回 (spans, kinds_hit)。

    spans = [(norm_start, norm_end, kind), ...]（normalized 座標，可能重疊；redact()
    映回 original 後依 start 排序、合併重疊再遮）。kinds_hit = 去重 kind 集。
    為何只「偵測」不在此遮：store-original-by-span 要把 span 映回 original 文本再遮
    （見 redact()），故各 arm 回報 span 而非就地 sub。
    """
    spans: list[tuple[int, int, str]] = []
    hits: set[str] = set()
    for pattern, extractor in _PATTERNS:
        for m in pattern.finditer(norm_text):
            for (s, e, kind) in extractor(m):  # type: ignore[operator]
                if e > s:
                    spans.append((s, e, kind))
                    hits.add(kind)
    return spans, hits


def _map_span_to_original(
    norm_start: int, norm_end: int, offset_map: list[int]
) -> tuple[int, int]:
    """把 normalized span [norm_start, norm_end) 映回 original [orig_start, orig_end)。

    orig_start = offset_map[norm_start]（該 normalized char 的原起始 index）。
    orig_end   = offset_map[norm_end]（下一個 normalized char 的原起始；norm_end ==
    len(norm) 時為末位哨兵 = len(original)）。

    為何用「下一字元起始」當 end：NFKC 展開 / url-decode 使 normalized↔original 非
    1:1；單一 normalized char 可能對應 original 的多 char 區域（如 %2F 三元組）。
    取 [offset_map[start], offset_map[end]) 保證涵蓋整個原 secret 區域——fail-safe
    寧可多遮一兩個相鄰原字元，絕不洩漏 secret、絕不破壞無關文本（span 邊界對齊
    keyword/結構命中，相鄰原字元是 secret 自身或其分隔符，非無關散文）。
    """
    orig_start = offset_map[norm_start]
    orig_end = offset_map[norm_end]
    return orig_start, orig_end


def _merge_spans(
    spans: list[tuple[int, int, str]]
) -> list[tuple[int, int, str]]:
    """合併重疊 / 相鄰 original span（依 start 排序）。重疊時 kind 取先命中者
    （pattern 順序 load-bearing：結構/keyword 先於其他）。回不重疊、升序 span。"""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda x: (x[0], x[1]))
    merged: list[tuple[int, int, str]] = [ordered[0]]
    for s, e, kind in ordered[1:]:
        ls, le, lkind = merged[-1]
        if s <= le:  # 重疊或相接 → 合併（kind 保留先者）
            merged[-1] = (ls, max(le, e), lkind)
        else:
            merged.append((s, e, kind))
    return merged


@dataclass
class RedactResult:
    """消毒結果。text=已消毒文本（原文僅 secret span 被遮）；kinds_hit=命中的 kind
    （去重、穩定排序）；redactor_version=跑的版本（寫入 ledger）。"""

    text: str
    kinds_hit: list[str] = field(default_factory=list)
    redactor_version: str = REDACTOR_VERSION


def redact(text: str | None) -> RedactResult:
    """對純文本做確定性、冪等的 secret 消毒（store-original-by-span，§B.5）。

    流程（v4）：
      0. size cap：text >256KB 先截斷（DoS guard），消毒後附 truncation marker。
      1. normalize_with_offsets：建 normalized 文本（NFKC + strip zero-width/control
         + URL-decode 一次）+ normalized→original offset map（僅供偵測）。
      2. 在 normalized 文本上跑 keyword-gated + 結構 pattern arm，收集 secret span。
      3. 把每個 span 映回 original 文本座標，合併重疊。
      4. 在 ORIGINAL 文本上對 merged span 套 `[REDACTED:kind]`（從尾到頭以免 index
         位移）。存入 = 原文僅 secret span 被遮；零-secret → byte-identical 原文。

    為什麼冪等：normalize 對已含 `[REDACTED:*]` 的文本不破壞 token（token 內無
    keyword/結構/scheme，pattern arm 皆不命中）→ 偵測零 span → 原文（已含 token）
    原樣返回。

    為什麼存原文非 normalized：principle 8（ledger 可重建）+ forensic——normalized
    過的文本（全形→半形、%2F→/、zero-width 消失）已非「as sent」原文；只在實際
    secret span 動刀，無關內容（中文全形標點、合法 %2F、zero-width）byte-identical。

    None / 空字串原樣返回（kinds_hit 空）。

    size cap（v4 LOW-2，DoS guard）：text 超過 _MAX_REDACT_INPUT_CHARS（256KB）先截斷，
    消毒截斷後文本，再附 truncation marker。bound super-linear per-char 迴圈 + bound
    儲存；marker 無 keyword/結構不被誤遮、冪等（再跑不命中）。
    """
    if not text:
        return RedactResult(text=text or "", kinds_hit=[], redactor_version=REDACTOR_VERSION)

    # ── size cap（DoS guard）：截斷後消毒，marker 事後附（marker 不過偵測，零誤遮）──
    # 冪等：尾端已有 truncation marker（前次已 cap）→ 不再截（防丟 marker/換 n）。
    truncation_suffix = ""
    if len(text) > _MAX_REDACT_INPUT_CHARS and not _TRUNCATION_MARKER_TAIL_RE.search(text):
        dropped = len(text) - _MAX_REDACT_INPUT_CHARS
        # 為何 log WARNING：>256KB L2 文本非現實正常響應（realistic <<256KB），多半是
        # 病態/濫用輸入（degenerate 全-evasion）或上游 bug；出聲讓部署期可見截斷事件。
        logger.warning(
            "l2_secret_redactor 輸入超過 %d chars（實 %d），截斷以 bound DoS：丟棄 %d chars",
            _MAX_REDACT_INPUT_CHARS, len(text), dropped,
        )
        truncation_suffix = _TRUNCATION_MARKER_FMT.format(n=dropped)
        text = text[:_MAX_REDACT_INPUT_CHARS]

    # ── Fast-path：無任何 strip-set 字元（_is_control_or_format）、無 '%'、且已
    # NFKC-normalized → normalized 文本 == 原文，offset map 為 identity，可直接在原文
    # 偵測+遮，省 per-char 迴圈。gate 由 _needs_offset_map 判定，gate-set 與 strip-set
    # 結構上恆相等（CRITICAL fix Finding 1：禁手列 regex 與 strip 謂詞 drift）。
    # 行為與 slow-path 完全等價（identity 映射下 span 座標不變）。多數真實 payload 走此路。
    if not _needs_offset_map(text):
        spans, hits = _detect_spans(text)
        if not spans:
            return RedactResult(
                text=text + truncation_suffix, kinds_hit=[], redactor_version=REDACTOR_VERSION
            )
        merged = _merge_spans([(s, e, kind) for (s, e, kind) in spans])
        out = text
        for s, e, kind in reversed(merged):
            out = out[:s] + _t(kind) + out[e:]
        return RedactResult(
            text=out + truncation_suffix, kinds_hit=sorted(hits), redactor_version=REDACTOR_VERSION
        )

    # ── Slow-path：含規避字元 → 建 normalized 文本 + offset map，偵測映回 original。
    norm_text, offset_map = _normalize_with_offsets(text)
    norm_spans, hits = _detect_spans(norm_text)
    if not norm_spans:
        # 零 secret → 原文 byte-identical 返回（store-original 不變量）。
        return RedactResult(
            text=text + truncation_suffix, kinds_hit=[], redactor_version=REDACTOR_VERSION
        )

    # 映回 original 座標。
    orig_spans = [
        (*_map_span_to_original(s, e, offset_map), kind) for (s, e, kind) in norm_spans
    ]
    merged = _merge_spans(orig_spans)

    # 在 original 文本上遮（從尾到頭，避免前序替換位移後序 index）。
    out = text
    for s, e, kind in reversed(merged):
        out = out[:s] + _t(kind) + out[e:]

    return RedactResult(
        text=out + truncation_suffix,
        kinds_hit=sorted(hits),
        redactor_version=REDACTOR_VERSION,
    )


# JSONB dict key（case-insensitive）∈ 此集 → 不論 value 結構一律遮其 value
# （§B.2.e：catch JSON header-echo dict 形，如 {"Authorization": "<tok>"}，
# value 不一定含 keyword/結構，靠 key 名判定）。
# v4 LOW-1：補 HMAC / signing / auth 簽章金鑰類 key 名（與上方 keyworded 臂同步，
# 使 §B.5「every named critical asset」對 JSONB-key 形也成立）。此 regex 全名錨定
# （^...$），無部分前綴 shadow，序無關。
_SENSITIVE_KEY_RE = re.compile(
    r"^(?:"
    r"authorization|api[_-]?key|api[_-]?secret|secret|password|passwd|"
    r"token|access[_-]?token|refresh[_-]?token|x-bapi-sign|x-bapi-api-key|"
    r"bearer|dsn|connection[_-]?string|private[_-]?key|"
    r"hmac[_-]?key|hmac|auth[_-]?signing[_-]?key|signing[_-]?secret|"
    r"signing[_-]?key|auth[_-]?key"
    r")$",
    re.IGNORECASE,
)


def _redact_sensitive_value(v: object) -> object:
    """敏感 key 的 value 一律遮：str → token；非 str（dict/list/數值）→ 遞迴
    消毒後再把任何殘留 string leaf 也視為 secret。對純 str 直接回 token（不論
    內容是否含 keyword/結構），這是 §B.2.e 的 catch-all。"""
    if isinstance(v, str):
        return _t("api_key")  # 敏感 key 的字串 value：一律遮（不嘗試保留脈絡）
    # 非字串 value（如 header dict 內嵌 list/dict）：遞迴正常消毒，避免漏。
    return redact_jsonb(v)


def redact_jsonb(obj: object) -> object:
    """對 JSONB-like 結構遞迴消毒。

    兩層保護：
      1. string leaf value 過 redact()（keyword + 結構 + 編碼規避偵測）。
      2. dict 的「敏感 key」（§B.2.e key 名集）→ 不論 value 結構一律遮其 value
         （catch header-echo dict {"Authorization": "<bare-tok>"}，其 value 可能
         無 keyword/結構，唯靠 key 名判定）。

    為什麼非敏感 key 仍只遮 value 不遮 key：input_context 的 key 多為
    schema-controlled（非 secret-bearing）；value 才是脈絡塊可能 drift 進 secret
    之處。回傳新結構（不就地改 caller 物件）。
    """
    if isinstance(obj, str):
        return redact(obj).text
    if isinstance(obj, dict):
        out: dict[object, object] = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SENSITIVE_KEY_RE.match(k.strip()):
                out[k] = _redact_sensitive_value(v)
            else:
                out[k] = redact_jsonb(v)
        return out
    if isinstance(obj, list):
        return [redact_jsonb(v) for v in obj]
    if isinstance(obj, tuple):
        return [redact_jsonb(v) for v in obj]
    return obj


def is_clean(text: str | None) -> bool:
    """便利：text 已不含任何可遮 secret（redact 為 no-op）→ True。供測試 / 斷言用。

    註（v3 store-original-by-span）：因偵測在 normalized 文本但遮在 original 文本，
    is_clean 對「含 url-encoded secret 但無明文 secret」的輸入回 False（normalized
    偵測到 → 有 span → redact 改了原文）；對純散文 / 零-secret 回 True（原文不變）。
    """
    if not text:
        return True
    return redact(text).text == text


__all__ = [
    "REDACTOR_VERSION",
    "RedactResult",
    "redact",
    "redact_jsonb",
    "is_clean",
]
