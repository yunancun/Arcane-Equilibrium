#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# test_ibkr_tws_permit_stub_source_static.py
#   IBKR W3-S2 INV-1 connect-permit stub 靜態守衛（CC 約束 #8;設計 §1.5/§10）。
#
# 斷言（default-build 源級,無需編譯）:
#   (a) production connect 路徑的 permit provider 是**具體型別 `EnvelopeRequiredStub`**——
#       禁 `dyn ConnectPermitProvider`、禁泛型 permit 參數（`: ConnectPermitProvider` 綁定 /
#       `impl ConnectPermitProvider` 參數位）;`TwsSessionManager` 以 `permit: EnvelopeRequiredStub`
#       持有（測試域無法向 production 路徑注入放行者）。**正向不變量（E3-F1,比枚舉壞 pattern 強）**:
#       production 檔對 `mint` 零呼叫點（只允許 `fn mint` 定義）——單條同擋「硬編條件自鑄」與
#       「attempt_connect 繞判自鑄」兩逃逸變體;且 `EnvelopeRequiredStub::check` region 禁 `Ok(`/`mint(`。
#   (b) `PermitToken` **非 Clone / 非 Copy**（無 derive Clone/Copy）+ 構造子 `mint` 為 **crate-private**
#       （`pub(crate) fn mint`,非 `pub fn`）;struct 本身 `pub(crate)`（非 `pub`）。
#   (c) stub 區塊（`PERMIT-STUB-GUARD-BEGIN..END`）**零 env / config / cfg 讀取**——`check` 恆
#       `Err(EnvelopeRequired)`,無任何開關可翻放行（掃 code,非註解）。
#   (d) 正控:臨時注入放行 provider / dyn / Clone derive / env 讀取 → 守衛必 FAIL（證明有牙）。
#   (e) inconclusive（檔缺 / 標界缺 / 錨點缺 / 正控未觸發）→ **非零 exit**（fail-closed）。
#
# Exit code:
#   0  PASS         — 真源零違規 且 正控全數觸發（守衛有牙）
#   1  FAIL         — 真源 ≥1 違規
#   5  INCONCLUSIVE — 檔/標界/錨點缺（無法鑑別 → fail-closed,不報 PASS）
#   6  TOOTHLESS    — 正控未能使守衛 FAIL（守衛無鑑別力 → fail-closed）
#
# 出典:docs/execution_plan/ibkr_live_capability/2026-07-15--w3_session_manager_design.md §1.5/§10;
#       仿 helper_scripts/ci/ibkr_g4_symbol_audit.sh 的 fail-closed / 正控 範式。
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "rust/openclaw_engine/src/ibkr_tws_session.rs"

BEGIN = "PERMIT-STUB-GUARD-BEGIN"
END = "PERMIT-STUB-GUARD-END"


# ── 輔助 ────────────────────────────────────────────────────────────────────
def _strip_line_comments(text: str) -> str:
    """移除每行 `//` 起的行註解（本檔 code 行內無字串含 `//`,安全）。用於掃 code 而非註解。"""
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


def _extract_stub_region(full_source: str) -> str | None:
    """抽 `BEGIN..END` 標界間的 stub 區塊（含標界間全部）。標界缺 → None（inconclusive）。"""
    b = full_source.find(BEGIN)
    e = full_source.find(END)
    if b < 0 or e < 0 or e <= b:
        return None
    return full_source[b:e]


# ── 核心稽核（純函數;正控可對 mutated source 重跑）────────────────────────────
def run_checks(full_source: str) -> tuple[list[str], list[str]]:
    """回 (violations, inconclusive)。violations 空 且 inconclusive 空 = PASS。"""
    violations: list[str] = []
    inconclusive: list[str] = []

    code = _strip_line_comments(full_source)
    region_raw = _extract_stub_region(full_source)
    if region_raw is None:
        inconclusive.append(f"stub guard markers {BEGIN}/{END} absent")
        return violations, inconclusive
    region_code = _strip_line_comments(region_raw)

    # 錨點:manager 存在（無 → 無法證明 connect 路徑,inconclusive）。
    if not re.search(r"\bstruct\s+TwsSessionManager\b", code):
        inconclusive.append("TwsSessionManager anchor absent")
        return violations, inconclusive

    # (a) 具體型別在 connect 路徑 + 禁 dyn / 泛型 permit 參數。
    if "permit: EnvelopeRequiredStub" not in code:
        violations.append("(a) TwsSessionManager permit field is not concrete EnvelopeRequiredStub")
    if "dyn ConnectPermitProvider" in code:
        violations.append("(a) forbidden trait object 'dyn ConnectPermitProvider' on connect path")
    if re.search(r":\s*ConnectPermitProvider\b", code):
        violations.append("(a) forbidden generic bound ': ConnectPermitProvider' (permit parameterised)")
    if re.search(r"\bimpl\s+ConnectPermitProvider\b(?!\s+for\b)", code):
        violations.append("(a) forbidden 'impl ConnectPermitProvider' parameter (permit parameterised)")

    # (b) PermitToken 非 Clone/Copy + 構造子 crate-private + struct crate-private。
    m = re.search(r"(?ms)^(.*?)\bpub\(crate\)\s+struct\s+PermitToken\b", region_raw)
    if not re.search(r"\bstruct\s+PermitToken\b", region_raw):
        inconclusive.append("PermitToken struct absent from stub region")
        return violations, inconclusive
    if "pub(crate) struct PermitToken" not in region_raw:
        violations.append("(b) PermitToken struct is not pub(crate) (over-exposed)")
    # 檢 struct 前緊鄰的 derive 屬性（若有）不得含 Clone/Copy。
    if m is not None:
        preceding = m.group(1)[-200:]
        derives = re.findall(r"#\[derive\(([^)]*)\)\]", preceding)
        for d in derives:
            if "Clone" in d or "Copy" in d:
                violations.append("(b) PermitToken derives Clone/Copy (must be single-use, non-Clone)")
    # 全域保險:stub 區塊不得對 PermitToken 派生 Clone/Copy。
    if re.search(r"#\[derive\([^)]*\b(Clone|Copy)\b[^)]*\)\]\s*pub\(crate\)\s+struct\s+PermitToken", region_raw):
        violations.append("(b) PermitToken derives Clone/Copy (must be single-use, non-Clone)")
    # 構造子 crate-private。
    if "pub(crate) fn mint" not in region_raw:
        violations.append("(b) PermitToken::mint constructor is not pub(crate)")
    if re.search(r"\bpub\s+fn\s+mint\b", region_raw):
        violations.append("(b) PermitToken::mint constructor is pub (must be crate-private)")

    # stub impl 存在且恆拒。
    if "impl ConnectPermitProvider for EnvelopeRequiredStub" not in region_raw:
        inconclusive.append("EnvelopeRequiredStub ConnectPermitProvider impl absent from stub region")
        return violations, inconclusive
    if "Err(ConnectDenied::EnvelopeRequired)" not in region_code:
        violations.append("(c) stub check does not return Err(EnvelopeRequired) unconditionally")

    # (a-strong) **正向不變量**（E3-F1;比枚舉壞 pattern 強）:production 檔對 `mint` **零呼叫點**——
    # 只允許 `fn mint` 定義行,任何 call site（`PermitToken::mint()` / `Self::mint()` / bare `mint()`）=
    # FAIL。此單條同時擋兩個 E3 逃逸變體:①stub check 內硬編條件自鑄 token;②attempt_connect 繞開
    # stub 判決自鑄 token。production 恆不鑄造 → 呼叫點必為 0。
    mint_calls = len(re.findall(r"\bmint\s*\(", code))
    mint_defs = len(re.findall(r"\bfn\s+mint\s*\(", code))
    if mint_calls - mint_defs != 0:
        violations.append(
            "(a) PermitToken::mint has call site(s) outside its definition "
            "(production must NEVER mint a token — stub always denies)"
        )

    # (b-strong) stub `check` region 禁 `Ok(` 與 `mint(`（恆 Err,無條件放行路徑)。掃 code 非註解;
    # 範圍鎖 EnvelopeRequiredStub 的 ConnectPermitProvider impl（避免 PermitToken::mint 定義誤命中）。
    check_impl_raw = region_raw[region_raw.find("impl ConnectPermitProvider for EnvelopeRequiredStub"):]
    check_impl_code = _strip_line_comments(check_impl_raw)
    if "Ok(" in check_impl_code:
        violations.append("(b) EnvelopeRequiredStub::check contains 'Ok(' (must deny unconditionally)")
    if re.search(r"\bmint\s*\(", check_impl_code):
        violations.append("(b) EnvelopeRequiredStub::check mints a token (must deny unconditionally)")

    # (c) stub 區塊零 env/config/cfg 讀取（掃 code,不掃註解）。
    forbidden_reads = [
        r"\benv::",
        r"\bstd::env\b",
        r"\benv!\(",
        r"\boption_env!\(",
        r"\bcfg!\(",
        r"#\[\s*cfg\b",
        r"::var\s*\(",
        r"\bConfig\b",
    ]
    for pat in forbidden_reads:
        if re.search(pat, region_code):
            violations.append(f"(c) stub region contains forbidden env/config/cfg read: /{pat}/")

    return violations, inconclusive


# ── 正控（d）:每個 mutation 必使守衛 FAIL ─────────────────────────────────────
def _mutations(full_source: str) -> list[tuple[str, str]]:
    """回 (label, mutated_source);每個都應觸發 ≥1 violation。"""
    muts: list[tuple[str, str]] = []
    # A1:非 stub 具體型別接進 connect 路徑。
    muts.append(("A1 non-stub concrete provider",
                 full_source.replace("permit: EnvelopeRequiredStub", "permit: AllowAllProvider")))
    # A2:trait object 接進 connect 路徑。
    muts.append(("A2 dyn provider",
                 full_source.replace("permit: EnvelopeRequiredStub",
                                     "permit: Box<dyn ConnectPermitProvider>")))
    # A3:泛型 permit 綁定。
    muts.append(("A3 generic permit bound",
                 full_source.replace("struct TwsSessionManager {",
                                     "struct TwsSessionManager<P: ConnectPermitProvider> {")))
    # B:PermitToken 派生 Clone。
    muts.append(("B clone derive",
                 full_source.replace("pub(crate) struct PermitToken {",
                                     "#[derive(Clone)]\npub(crate) struct PermitToken {")))
    # B2:mint 過度公開。
    muts.append(("B2 pub mint",
                 full_source.replace("pub(crate) fn mint()", "pub fn mint()")))
    # C:stub 內注入 env 讀取放行開關。
    muts.append(("C env switch in stub",
                 full_source.replace(
                     "        Err(ConnectDenied::EnvelopeRequired)",
                     '        if std::env::var("OPENCLAW_LET_ME_IN").is_ok() {\n'
                     "            return Ok(PermitToken::mint());\n"
                     "        }\n"
                     "        Err(ConnectDenied::EnvelopeRequired)")))
    # C2（E3-F1 變體①,**非 env**）:stub check 內硬編條件放行 + 保留 Err fallthrough。
    muts.append(("C2 hardcoded-condition Ok in stub",
                 full_source.replace(
                     "        Err(ConnectDenied::EnvelopeRequired)",
                     "        if 0 == 0 {\n"
                     "            return Ok(PermitToken::mint());\n"
                     "        }\n"
                     "        Err(ConnectDenied::EnvelopeRequired)")))
    # C3（E3-F1 變體②）:attempt_connect 繞開 stub 判決自鑄 token。
    muts.append(("C3 attempt_connect self-mints token",
                 full_source.replace(
                     "Err(ConnectDenied::EnvelopeRequired) => self.fsm.on_permit_denied(),",
                     "Err(ConnectDenied::EnvelopeRequired) => "
                     "self.fsm.on_permit_granted(PermitToken::mint(), now_ms),")))
    # D（E2-F3）:Copy derive on PermitToken（Clone 已有;補 Copy 證明 (Clone|Copy) 兩支皆有牙）。
    muts.append(("D copy derive",
                 full_source.replace("pub(crate) struct PermitToken {",
                                     "#[derive(Copy)]\npub(crate) struct PermitToken {")))
    # E（E2-F3）:stub 內 cfg! 讀取放行開關。
    muts.append(("E cfg! switch in stub",
                 full_source.replace(
                     "        Err(ConnectDenied::EnvelopeRequired)",
                     "        if cfg!(feature = \"let_me_in\") {\n"
                     "            return Ok(PermitToken::mint());\n"
                     "        }\n"
                     "        Err(ConnectDenied::EnvelopeRequired)")))
    # F（E2-F3）:stub 內 option_env! 讀取放行開關。
    muts.append(("F option_env! switch in stub",
                 full_source.replace(
                     "        Err(ConnectDenied::EnvelopeRequired)",
                     '        if option_env!("LET_ME_IN").is_some() {\n'
                     "            return Ok(PermitToken::mint());\n"
                     "        }\n"
                     "        Err(ConnectDenied::EnvelopeRequired)")))
    # G（E2-F3）:PermitToken struct 過度暴露（pub 非 pub(crate)）。
    muts.append(("G over-exposed pub struct PermitToken",
                 full_source.replace("pub(crate) struct PermitToken {",
                                     "pub struct PermitToken {")))
    return muts


def positive_control(full_source: str) -> list[str]:
    """回未被守衛攔下的 mutation label（應為空;非空=守衛無牙 → TOOTHLESS）。"""
    escaped: list[str] = []
    for label, mutated in _mutations(full_source):
        if mutated == full_source:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, inc = run_checks(mutated)
        if not v:
            escaped.append(f"{label} (guard did not FAIL on injected violation)")
    return escaped


# ═════════════════════════════════════════════════════════════════════════════
# E3-F1 permit audit-scope 四聯擴張（W8a 首階段;IBKR_TODO §7 W3 移交項）
#   掃描面從 file-scoped(ibkr_tws_session.rs) 擴到全 production 域 + driver +
#   W8a envelope 驗證器。W8 落 production TCP factory 時做第二階段擴張並吸收。
#
# 四聯斷言（production 域 = rust/openclaw_engine/src 全部 .rs,排除 *_tests.rs 與
# */tests/* —— granting provider 只存在於 cfg(test) 掛入的 *_tests.rs 檔）:
#   ① 唯一 connect 位點:permit-path 檔集(session/driver/envelope-check)內,唯一的
#      connect 呼叫 = driver 的 `self.factory.connect()`（恰一處);三檔零
#      `TcpStream`（真 socket factory 是 W8 事,落地時本段第二階段擴張）。
#   ② connect 前必經 permit 且 `PermitToken` move 消費:driver `connect_and_handshake`
#      內 `self.permit.check()` 必在 `self.factory.connect()` 之前;token 以
#      `on_permit_granted(token` move 進 FSM(單次消費)。
#   ③ fake 缺席:production 域零 `GrantingProvider`。
#   ④ provider 型別唯一性:production 域唯一 `impl ConnectPermitProvider` =
#      session 檔的 `EnvelopeRequiredStub`;`PermitToken::mint(` 全域零 production
#      呼叫點;W8a envelope 驗證器(只驗不發)零 permit 面型別觸碰。
#   正控:注入第二 impl / mint 呼叫 / 第二 connect 位點 / TcpStream / 移除 permit
#   check → 守衛必 FAIL（證明有牙）。
#
# 範圍注記:`ibkr_readonly_tws_client.rs`(G4 B1 客戶端)與 `ai_service_client.rs`
# 的 connect 是**獨立受審面**（ibkr_g4_symbol_audit.sh / 各自 gate),不屬 permit
# connect 路徑,不入 ① 檔集;④ 的全域 impl/mint 掃描仍覆蓋之。
# ═════════════════════════════════════════════════════════════════════════════

ENGINE_SRC = ROOT / "rust/openclaw_engine/src"
SESSION_REL = "rust/openclaw_engine/src/ibkr_tws_session.rs"
DRIVER_REL = "rust/openclaw_engine/src/ibkr_tws_driver.rs"
ENVELOPE_CHECK_REL = "rust/openclaw_engine/src/ibkr_activation_envelope_check.rs"
PERMIT_PATH_RELS = (SESSION_REL, DRIVER_REL, ENVELOPE_CHECK_REL)


def _production_engine_sources() -> dict[str, str]:
    """production 域源集:engine src 全部 .rs,排除 `*_tests.rs` 與 `*/tests/*`
    （兩者皆 cfg(test) 專屬——granting provider 的合法棲地）。"""
    sources: dict[str, str] = {}
    for path in sorted(ENGINE_SRC.rglob("*.rs")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name.endswith("_tests.rs") or "/tests/" in rel:
            continue
        sources[rel] = path.read_text(encoding="utf-8", errors="ignore")
    return sources


def run_audit4(sources: dict[str, str]) -> tuple[list[str], list[str]]:
    """四聯 audit(純函數;正控可對 mutated 源集重跑)。回 (violations, inconclusive)。"""
    violations: list[str] = []
    inconclusive: list[str] = []

    for rel in PERMIT_PATH_RELS:
        if rel not in sources:
            inconclusive.append(f"permit-path source absent: {rel}")
    if inconclusive:
        return violations, inconclusive

    code = {rel: _strip_line_comments(text) for rel, text in sources.items()}

    # ④ provider 型別唯一性(全 production 域)。
    impls: list[tuple[str, str]] = []
    for rel, c in code.items():
        for m in re.finditer(r"\bimpl\s+ConnectPermitProvider\s+for\s+(\w+)", c):
            impls.append((rel, m.group(1)))
    if not impls:
        inconclusive.append("no production impl ConnectPermitProvider found (anchor absent)")
        return violations, inconclusive
    if impls != [(SESSION_REL, "EnvelopeRequiredStub")]:
        violations.append(
            "(4) production ConnectPermitProvider impl set is not exactly "
            f"{{EnvelopeRequiredStub @ session}}: {impls}"
        )

    # ④b `PermitToken::mint(` 全域零 production 呼叫點(定義行是 `fn mint`,不匹配此型)。
    for rel, c in code.items():
        if re.search(r"PermitToken::mint\s*\(", c):
            violations.append(f"(4) PermitToken::mint call site in production source: {rel}")

    # ③ fake 缺席:granting provider 只可存在於 cfg(test) 測試檔。
    for rel, c in code.items():
        if "GrantingProvider" in c:
            violations.append(f"(3) GrantingProvider present in production source: {rel}")

    # ① 唯一 connect 位點(permit-path 檔集)。
    driver_code = code[DRIVER_REL]
    factory_connect = len(re.findall(r"\.factory\s*\.\s*connect\s*\(", driver_code))
    if factory_connect != 1:
        violations.append(
            f"(1) driver must have exactly one factory.connect() call site, found {factory_connect}"
        )
    dot_connect = len(re.findall(r"\.connect\s*\(", driver_code))
    if dot_connect != factory_connect:
        violations.append(
            "(1) driver has connect call site(s) outside the single factory.connect() "
            f"(total {dot_connect})"
        )
    for rel in (SESSION_REL, ENVELOPE_CHECK_REL):
        if re.search(r"\.connect\s*\(", code[rel]):
            violations.append(f"(1) forbidden connect call site outside driver: {rel}")
    for rel in PERMIT_PATH_RELS:
        if "TcpStream" in code[rel]:
            violations.append(f"(1) TcpStream in permit-path source (W8 TCP factory not landed): {rel}")

    # ② connect 前必經 permit + token move 消費。
    permit_idx = driver_code.find("self.permit.check()")
    connect_idx = driver_code.find("self.factory.connect()")
    if permit_idx < 0:
        violations.append("(2) driver permit gate `self.permit.check()` absent")
    if connect_idx < 0:
        violations.append("(2) driver `self.factory.connect()` absent")
    if permit_idx >= 0 and connect_idx >= 0 and permit_idx > connect_idx:
        violations.append("(2) factory.connect() precedes permit.check() (permit not a pre-gate)")
    if "on_permit_granted(token" not in driver_code:
        violations.append("(2) PermitToken move-consumption `on_permit_granted(token` absent")

    # ④c W8a envelope 驗證器隔離:只驗不發,W8 前不得觸碰 permit 面型別。
    for tok in ("ConnectPermitProvider", "PermitToken"):
        if tok in code[ENVELOPE_CHECK_REL]:
            violations.append(f"(4) envelope check touches permit surface `{tok}` before W8")

    return violations, inconclusive


def _audit4_mutations(sources: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    """正控 mutation 集;每個都應觸發 ≥1 violation。"""
    muts: list[tuple[str, dict[str, str]]] = []

    def mutated(rel: str, transform) -> dict[str, str]:
        out = dict(sources)
        out[rel] = transform(out[rel])
        return out

    # Q1:driver 注入第二個 production impl(型別唯一性破口)。
    muts.append((
        "Q1 second production impl in driver",
        mutated(DRIVER_REL, lambda s: s + "\nimpl ConnectPermitProvider for OpenSesame {}\n"),
    ))
    # Q2:driver 注入 PermitToken::mint() 呼叫點(自鑄 token)。
    muts.append((
        "Q2 PermitToken::mint call in driver",
        mutated(DRIVER_REL, lambda s: s + "\nfn q2_forge() { let _t = PermitToken::mint(); }\n"),
    ))
    # Q3:production 域出現 GrantingProvider(fake 逃逸)。
    muts.append((
        "Q3 GrantingProvider leaked into production",
        mutated(DRIVER_REL, lambda s: s + "\nstruct GrantingProvider;\n"),
    ))
    # Q4:driver 注入第二個 connect 位點(唯一位點破口)。
    muts.append((
        "Q4 second factory.connect site in driver",
        mutated(DRIVER_REL, lambda s: s + "\n// q4\nfn q4(&mut self) { let _ = self.factory.connect(); }\n"),
    ))
    # Q5:移除 permit 前置閘(connect 不再必經 permit)。
    muts.append((
        "Q5 permit gate removed from driver",
        mutated(DRIVER_REL, lambda s: s.replace("self.permit.check()", "self.permit_gate_removed()")),
    ))
    # Q6:envelope 驗證器注入真 socket。
    muts.append((
        "Q6 TcpStream in envelope check",
        mutated(ENVELOPE_CHECK_REL, lambda s: s + "\nfn q6() { let _ = TcpStream::connect(\"127.0.0.1:4001\"); }\n"),
    ))
    # Q7:envelope 驗證器提前接 permit trait 位(W8 前禁)。
    muts.append((
        "Q7 envelope check impls ConnectPermitProvider",
        mutated(ENVELOPE_CHECK_REL, lambda s: s + "\nimpl ConnectPermitProvider for ActivationNonceLedger {}\n"),
    ))
    return muts


def audit4_positive_control(sources: dict[str, str]) -> list[str]:
    """回未被四聯守衛攔下的 mutation label(應為空;非空=守衛無牙)。"""
    escaped: list[str] = []
    for label, mutated_sources in _audit4_mutations(sources):
        if mutated_sources == sources:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, _inc = run_audit4(mutated_sources)
        if not v:
            escaped.append(f"{label} (audit4 did not FAIL on injected violation)")
    return escaped


# ── 主入口（standalone;fail-closed exit code）────────────────────────────────
def main() -> int:
    if not SESSION.exists():
        print(f"[permit-stub-audit] INCONCLUSIVE: source absent: {SESSION}", file=sys.stderr)
        return 5
    src = SESSION.read_text(encoding="utf-8")

    violations, inconclusive = run_checks(src)
    if inconclusive:
        for r in inconclusive:
            print(f"[permit-stub-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5

    escaped = positive_control(src)
    if escaped:
        for e in escaped:
            print(f"[permit-stub-audit] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6

    if violations:
        for v in violations:
            print(f"[permit-stub-audit] FAIL: {v}", file=sys.stderr)
        return 1

    # E3-F1 四聯擴張(W8a 首階段):production 域 + driver + envelope-check。
    sources = _production_engine_sources()
    v4, inc4 = run_audit4(sources)
    if inc4:
        for r in inc4:
            print(f"[permit-audit4] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5
    escaped4 = audit4_positive_control(sources)
    if escaped4:
        for e in escaped4:
            print(f"[permit-audit4] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6
    if v4:
        for v in v4:
            print(f"[permit-audit4] FAIL: {v}", file=sys.stderr)
        return 1

    print("[permit-stub-audit] PASS: INV-1 permit stub guard (a-e) satisfied; positive controls have teeth")
    print("[permit-audit4] PASS: E3-F1 four-point audit (1-4) satisfied across production scope; positive controls have teeth")
    return 0


# ── pytest 介面（與 standalone 同源）──────────────────────────────────────────
def test_permit_stub_real_source_has_zero_violations() -> None:
    assert SESSION.exists(), f"source absent: {SESSION}"
    violations, inconclusive = run_checks(SESSION.read_text(encoding="utf-8"))
    assert not inconclusive, f"inconclusive: {inconclusive}"
    assert not violations, f"violations: {violations}"


def test_permit_stub_positive_controls_have_teeth() -> None:
    assert SESSION.exists(), f"source absent: {SESSION}"
    escaped = positive_control(SESSION.read_text(encoding="utf-8"))
    assert not escaped, f"positive controls escaped (guard toothless): {escaped}"


def test_permit_audit4_production_scope_has_zero_violations() -> None:
    violations, inconclusive = run_audit4(_production_engine_sources())
    assert not inconclusive, f"inconclusive: {inconclusive}"
    assert not violations, f"violations: {violations}"


def test_permit_audit4_positive_controls_have_teeth() -> None:
    escaped = audit4_positive_control(_production_engine_sources())
    assert not escaped, f"audit4 positive controls escaped (toothless): {escaped}"


if __name__ == "__main__":
    sys.exit(main())
