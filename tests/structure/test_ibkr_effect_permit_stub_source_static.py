#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# test_ibkr_effect_permit_stub_source_static.py
#   IBKR W7-S4a INV-ORDER effect-permit / option-B 靜態守衛（CC-B1/B4;設計 §1.4/§4）。
#
#   INV-1 connect-permit 的兄弟守衛(見 test_ibkr_tws_permit_stub_source_static.py)——但守
#   **order-verb effect 面**（`EffectPermitProvider`/`OrderEffectPermit`/`check_effect_contact`）,
#   兩軸獨立。斷言 default-build 源級（無需編譯）**production 恆拒不變量**在 S4a 放行臂落地後維持:
#
#   (a) 恆拒 stub 唯一性:`EffectEnvelopeRequiredStub::check` region 恆 `Err(EnvelopeRequired)`,
#       禁 `Ok(` / `mint(`；EFFECT-STUB-GUARD region 零 env/config/cfg 讀取（掃 code 非註解）。
#   (b) `OrderEffectPermit` 非 Clone/Copy;`mint` 構造子 `pub(crate)`（非 `pub`）。
#   (c) **機器證明①**:`OrderEffectPermit::mint(` 全 production 域**恰一呼叫點**,且在
#       `ibkr_activation_envelope_check.rs`（= `check_effect_contact` 的唯一鑄造點,§1.3）。
#   (d) **機器證明②/⑤**:production 域唯一 `impl EffectPermitProvider` = order-transport 的
#       `EffectEnvelopeRequiredStub`（無第二 impl / 無真簽名 provider）。
#   (e) **機器證明③（放行臂不可達）**:`check_effect_contact` 全 production 域**零 caller**
#       （只出現其 `fn` 定義,無任何呼叫點）→ 放行臂 final-binary DCE → production 恆無 permit。
#   (f) **禁擴鐵律（設計 §4.1;CC-B1）**:effect activation 模塊不複用 Bybit slot
#       `OPENCLAW_LIVE_AUTH_SIGNING_KEY`、不 `use crate::live_authorization`;且用新 slot
#       `OPENCLAW_IBKR_EFFECT_ACTIVATION_SIGNING_KEY`（金鑰 custody,缺席 fail-closed）。
#   (g) 正控:注入第二 impl / 第二 mint 呼叫 / check_effect_contact caller / stub 內 Ok /
#       Bybit slot 複用 → 守衛必 FAIL（證明有牙）。
#   (h) inconclusive（檔缺 / 標界缺 / 錨點缺 / 正控未觸發）→ 非零 exit（fail-closed）。
#
# Exit code:
#   0  PASS         — 真源零違規 且 正控全數觸發（守衛有牙）
#   1  FAIL         — 真源 ≥1 違規
#   5  INCONCLUSIVE — 檔/標界/錨點缺（無法鑑別 → fail-closed,不報 PASS）
#   6  TOOTHLESS    — 正控未能使守衛 FAIL（守衛無鑑別力 → fail-closed）
#
# 出典:docs/execution_plan/ibkr_live_capability/2026-07-17--w7_order_lifecycle_design.md §1.4/§4;
#       仿 tests/structure/test_ibkr_tws_permit_stub_source_static.py 的 fail-closed / 正控 範式。
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "rust/openclaw_engine/src"

TRANSPORT_REL = "rust/openclaw_engine/src/ibkr_tws_order_transport.rs"
ENVELOPE_CHECK_REL = "rust/openclaw_engine/src/ibkr_activation_envelope_check.rs"
EFFECT_ACT_REL = "rust/openclaw_engine/src/ibkr_effect_activation.rs"

TRANSPORT = ROOT / TRANSPORT_REL

BEGIN = "EFFECT-STUB-GUARD-BEGIN"
END = "EFFECT-STUB-GUARD-END"

BYBIT_SLOT = "OPENCLAW_LIVE_AUTH_SIGNING_KEY"
EFFECT_SLOT = "OPENCLAW_IBKR_EFFECT_ACTIVATION_SIGNING_KEY"


# ── 輔助 ────────────────────────────────────────────────────────────────────
def _strip_line_comments(text: str) -> str:
    """移除每行 `//` 起的行註解（掃 code 而非註解）。"""
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


def _extract_stub_region(full_source: str) -> str | None:
    b = full_source.find(BEGIN)
    e = full_source.find(END)
    if b < 0 or e < 0 or e <= b:
        return None
    return full_source[b:e]


# ── (a)(b) stub region 稽核（純函數;正控可對 mutated source 重跑）─────────────────
def run_region_checks(full_source: str) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    inconclusive: list[str] = []

    region_raw = _extract_stub_region(full_source)
    if region_raw is None:
        inconclusive.append(f"stub guard markers {BEGIN}/{END} absent")
        return violations, inconclusive
    region_code = _strip_line_comments(region_raw)

    # (b) OrderEffectPermit 非 Clone/Copy + mint 構造子 crate-private。
    if "pub(crate) struct OrderEffectPermit" not in region_raw:
        violations.append("(b) OrderEffectPermit struct not pub(crate) in stub region")
    if re.search(
        r"#\[derive\([^)]*\b(Clone|Copy)\b[^)]*\)\]\s*pub\(crate\)\s+struct\s+OrderEffectPermit",
        region_raw,
    ):
        violations.append("(b) OrderEffectPermit derives Clone/Copy (must be single-use)")
    if "pub(crate) fn mint" not in region_raw:
        violations.append("(b) OrderEffectPermit::mint constructor is not pub(crate)")
    if re.search(r"\bpub\s+fn\s+mint\b", region_raw):
        violations.append("(b) OrderEffectPermit::mint constructor is pub (must be crate-private)")

    # stub impl 存在且恆拒。
    stub_anchor = "impl EffectPermitProvider for EffectEnvelopeRequiredStub"
    if stub_anchor not in region_raw:
        inconclusive.append("EffectEnvelopeRequiredStub EffectPermitProvider impl absent from region")
        return violations, inconclusive
    if "Err(EffectDenied::EnvelopeRequired)" not in region_code:
        violations.append("(a) stub check does not return Err(EnvelopeRequired) unconditionally")

    # (a) stub `check` region 禁 `Ok(` 與 `mint(`（恆 Err,無條件放行路徑）。掃 code 非註解。
    check_impl_raw = region_raw[region_raw.find(stub_anchor):]
    check_impl_code = _strip_line_comments(check_impl_raw)
    if "Ok(" in check_impl_code:
        violations.append("(a) EffectEnvelopeRequiredStub::check contains 'Ok(' (must deny)")
    if re.search(r"\bmint\s*\(", check_impl_code):
        violations.append("(a) EffectEnvelopeRequiredStub::check mints a permit (must deny)")

    # (a) stub region 零 env/config/cfg 讀取（掃 code,不掃註解）。
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
            violations.append(f"(a) stub region contains forbidden env/config/cfg read: /{pat}/")

    return violations, inconclusive


# ── (c)(d)(e)(f) production-scope 機器證明（純函數）──────────────────────────────
def _production_engine_sources() -> dict[str, str]:
    """production 域源集:engine src 全部 .rs,排除 `*_tests.rs` 與 `*/tests/*`
    （兩者皆 cfg(test) 專屬——test-域鑄 permit 的合法棲地）。"""
    sources: dict[str, str] = {}
    for path in sorted(ENGINE_SRC.rglob("*.rs")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name.endswith("_tests.rs") or "/tests/" in rel:
            continue
        sources[rel] = path.read_text(encoding="utf-8", errors="ignore")
    return sources


def run_effect_audit(sources: dict[str, str]) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    inconclusive: list[str] = []

    for rel in (TRANSPORT_REL, ENVELOPE_CHECK_REL, EFFECT_ACT_REL):
        if rel not in sources:
            inconclusive.append(f"effect-path source absent: {rel}")
    if inconclusive:
        return violations, inconclusive

    code = {rel: _strip_line_comments(text) for rel, text in sources.items()}

    # (d)/⑤ provider 型別唯一性（全 production 域）。
    impls: list[tuple[str, str]] = []
    for rel, c in code.items():
        for m in re.finditer(r"\bimpl\s+EffectPermitProvider\s+for\s+(\w+)", c):
            impls.append((rel, m.group(1)))
    if not impls:
        inconclusive.append("no production impl EffectPermitProvider found (anchor absent)")
        return violations, inconclusive
    if impls != [(TRANSPORT_REL, "EffectEnvelopeRequiredStub")]:
        violations.append(
            "(d) production EffectPermitProvider impl set is not exactly "
            f"{{EffectEnvelopeRequiredStub @ order_transport}}: {impls}"
        )

    # (c)/① `OrderEffectPermit::mint(` 全 production 域恰一呼叫點,且在 envelope-check。
    mint_call_sites: list[str] = []
    for rel, c in code.items():
        mint_call_sites.extend([rel] * len(re.findall(r"OrderEffectPermit::mint\s*\(", c)))
    if mint_call_sites != [ENVELOPE_CHECK_REL]:
        violations.append(
            "(c) OrderEffectPermit::mint( production call sites must be exactly one "
            f"in {ENVELOPE_CHECK_REL} (check_effect_contact Ok arm), found {mint_call_sites}"
        )

    # (e)/③ `check_effect_contact` 全 production 域零 caller（只出現 `fn` 定義）。放行臂不可達 → DCE。
    total_occurrences = 0
    defs = 0
    for _rel, c in code.items():
        total_occurrences += len(re.findall(r"\bcheck_effect_contact\s*\(", c))
        defs += len(re.findall(r"\bfn\s+check_effect_contact\s*\(", c))
    if defs != 1:
        inconclusive.append(
            f"expected exactly one `fn check_effect_contact` definition, found {defs}"
        )
        return violations, inconclusive
    if total_occurrences - defs != 0:
        violations.append(
            "(e) check_effect_contact has production call site(s) beyond its definition "
            f"({total_occurrences - defs}) — release arm must stay DCE (zero production caller)"
        )

    # (f)/CC-B1 禁擴鐵律:effect activation 不複用 Bybit slot / 不 use live_authorization;用新 slot。
    eff = code[EFFECT_ACT_REL]
    if BYBIT_SLOT in eff:
        violations.append(f"(f) effect activation reuses Bybit slot {BYBIT_SLOT} (禁擴鐵律)")
    if re.search(r"\buse\s+crate::live_authorization\b", eff):
        violations.append("(f) effect activation imports crate::live_authorization (禁擴鐵律)")
    if EFFECT_SLOT not in eff:
        violations.append(f"(f) effect activation does not reference new slot {EFFECT_SLOT}")

    return violations, inconclusive


# ── 正控（g）─────────────────────────────────────────────────────────────────
def _region_mutations(full_source: str) -> list[tuple[str, str]]:
    muts: list[tuple[str, str]] = []
    # R1:stub check 內注入 Ok 放行。
    muts.append((
        "R1 Ok in stub check",
        full_source.replace(
            "        Err(EffectDenied::EnvelopeRequired)",
            "        if 0 == 0 {\n"
            "            return Ok(OrderEffectPermit::mint());\n"
            "        }\n"
            "        Err(EffectDenied::EnvelopeRequired)",
        ),
    ))
    # R2:mint 過度公開。
    muts.append((
        "R2 pub mint",
        full_source.replace("pub(crate) fn mint()", "pub fn mint()"),
    ))
    # R3:OrderEffectPermit 派生 Clone。
    muts.append((
        "R3 clone derive",
        full_source.replace(
            "pub(crate) struct OrderEffectPermit {",
            "#[derive(Clone)]\npub(crate) struct OrderEffectPermit {",
        ),
    ))
    # R4:stub 內 env 讀取放行開關。
    muts.append((
        "R4 env switch in stub",
        full_source.replace(
            "        Err(EffectDenied::EnvelopeRequired)",
            '        if std::env::var("LET_ME_IN").is_ok() {\n'
            "            return Ok(OrderEffectPermit::mint());\n"
            "        }\n"
            "        Err(EffectDenied::EnvelopeRequired)",
        ),
    ))
    return muts


def region_positive_control(full_source: str) -> list[str]:
    escaped: list[str] = []
    for label, mutated in _region_mutations(full_source):
        if mutated == full_source:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, _inc = run_region_checks(mutated)
        if not v:
            escaped.append(f"{label} (guard did not FAIL on injected violation)")
    return escaped


def _effect_audit_mutations(sources: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    muts: list[tuple[str, dict[str, str]]] = []

    def mutated(rel: str, transform) -> dict[str, str]:
        out = dict(sources)
        out[rel] = transform(out[rel])
        return out

    # Q1:注入第二個 production impl EffectPermitProvider。
    muts.append((
        "Q1 second production EffectPermitProvider impl",
        mutated(ENVELOPE_CHECK_REL, lambda s: s + "\nimpl EffectPermitProvider for OpenSesame {}\n"),
    ))
    # Q2:注入第二個 OrderEffectPermit::mint() 呼叫點。
    muts.append((
        "Q2 second OrderEffectPermit::mint call",
        mutated(TRANSPORT_REL, lambda s: s + "\nfn q2_forge() { let _p = OrderEffectPermit::mint(); }\n"),
    ))
    # Q3:注入 check_effect_contact caller（放行臂變 production-reachable）。
    muts.append((
        "Q3 check_effect_contact production caller",
        mutated(
            TRANSPORT_REL,
            lambda s: s + "\nfn q3_call() { let _ = check_effect_contact(None, todo!(), todo!(), todo!(), todo!()); }\n",
        ),
    ))
    # Q4:effect activation 複用 Bybit slot。
    muts.append((
        "Q4 Bybit slot reuse in effect activation",
        mutated(EFFECT_ACT_REL, lambda s: s + f'\nconst LEAK: &str = "{BYBIT_SLOT}";\n'),
    ))
    # Q5:effect activation import live_authorization（禁擴鐵律）。
    muts.append((
        "Q5 effect activation imports live_authorization",
        mutated(EFFECT_ACT_REL, lambda s: s + "\nuse crate::live_authorization;\n"),
    ))
    return muts


def effect_audit_positive_control(sources: dict[str, str]) -> list[str]:
    escaped: list[str] = []
    for label, mutated_sources in _effect_audit_mutations(sources):
        if mutated_sources == sources:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, _inc = run_effect_audit(mutated_sources)
        if not v:
            escaped.append(f"{label} (effect audit did not FAIL on injected violation)")
    return escaped


# ── 主入口（standalone;fail-closed exit code）────────────────────────────────
def main() -> int:
    if not TRANSPORT.exists():
        print(f"[effect-stub-audit] INCONCLUSIVE: source absent: {TRANSPORT}", file=sys.stderr)
        return 5
    src = TRANSPORT.read_text(encoding="utf-8")

    violations, inconclusive = run_region_checks(src)
    if inconclusive:
        for r in inconclusive:
            print(f"[effect-stub-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5
    escaped = region_positive_control(src)
    if escaped:
        for e in escaped:
            print(f"[effect-stub-audit] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6
    if violations:
        for v in violations:
            print(f"[effect-stub-audit] FAIL: {v}", file=sys.stderr)
        return 1

    sources = _production_engine_sources()
    v2, inc2 = run_effect_audit(sources)
    if inc2:
        for r in inc2:
            print(f"[effect-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5
    escaped2 = effect_audit_positive_control(sources)
    if escaped2:
        for e in escaped2:
            print(f"[effect-audit] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6
    if v2:
        for v in v2:
            print(f"[effect-audit] FAIL: {v}", file=sys.stderr)
        return 1

    print("[effect-stub-audit] PASS: INV-ORDER effect-permit stub guard (a-b) satisfied; positive controls have teeth")
    print("[effect-audit] PASS: machine proofs (mint single call site / unique stub provider / check_effect_contact zero caller / no Bybit-slot reuse) satisfied; positive controls have teeth")
    return 0


# ── pytest 介面（與 standalone 同源）──────────────────────────────────────────
def test_effect_stub_region_has_zero_violations() -> None:
    assert TRANSPORT.exists(), f"source absent: {TRANSPORT}"
    violations, inconclusive = run_region_checks(TRANSPORT.read_text(encoding="utf-8"))
    assert not inconclusive, f"inconclusive: {inconclusive}"
    assert not violations, f"violations: {violations}"


def test_effect_stub_region_positive_controls_have_teeth() -> None:
    assert TRANSPORT.exists(), f"source absent: {TRANSPORT}"
    escaped = region_positive_control(TRANSPORT.read_text(encoding="utf-8"))
    assert not escaped, f"positive controls escaped (guard toothless): {escaped}"


def test_effect_audit_production_scope_has_zero_violations() -> None:
    violations, inconclusive = run_effect_audit(_production_engine_sources())
    assert not inconclusive, f"inconclusive: {inconclusive}"
    assert not violations, f"violations: {violations}"


def test_effect_audit_positive_controls_have_teeth() -> None:
    escaped = effect_audit_positive_control(_production_engine_sources())
    assert not escaped, f"effect audit positive controls escaped (toothless): {escaped}"


if __name__ == "__main__":
    sys.exit(main())
