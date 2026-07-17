#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# test_ibkr_order_lifecycle_single_mutator_source_static.py
#   IBKR W7-S1 訂單生命週期「單一狀態 mutator」機器守衛（E4-GAP-2;Bybit 幻影倉教訓機器化）。
#
#   不變量:lifecycle `record.state` 賦值(`\.state\s*=`,排除 `==`/`!=`)**只**出現在唯一狀態
#   mutator `apply_lifecycle_event` 的函數體內——絕無第二狀態寫入路徑（PositionUpdate/Fill 無序
#   雙寫是 Bybit 幻影倉根因）。api_pending 計時器等非狀態注記不碰 `.state`。
#
#   G1 恰一 `fn apply_lifecycle_event` 定義。
#   G2 全模塊 `.state =` 賦值皆落於該函數 brace-span 內（≥1,守衛非空洞）。
#
#   正控(注入):在他處(如 observe_api_pending)加 `record.state = ...` → 守衛須 FAIL。
#   inconclusive(檔缺/錨點缺/無 .state 賦值)→ 非零 exit(fail-closed)。
#
# Exit: 0 PASS / 1 FAIL / 5 INCONCLUSIVE / 6 TOOTHLESS。
# 出典:docs/execution_plan/ibkr_live_capability/2026-07-17--w7_order_lifecycle_design.md
#       §2.2(唯一 mutator apply_lifecycle_event)/§7(幻影倉教訓)。
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_REL = "rust/openclaw_engine/src/ibkr_tws_order_lifecycle.rs"
MODULE = ROOT / MODULE_REL

MUTATOR = "apply_lifecycle_event"


def _strip_line_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


def _fn_body_span(code: str, name: str) -> tuple[int, int] | None:
    """回 `fn name` 函數體(含外層 { })的 [start,end) 字元 span;brace 配對。"""
    m = re.search(rf"\bfn\s+{re.escape(name)}\s*\(", code)
    if m is None:
        return None
    # 從簽名後找第一個 '{'
    brace = code.find("{", m.end())
    if brace < 0:
        return None
    depth = 0
    for i in range(brace, len(code)):
        c = code[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (brace, i + 1)
    return None


def _state_assign_positions(code: str) -> list[int]:
    """`.state =` 賦值位置(排除 `==`/`!=`/`>=`/`<=`;`.state` 後可有空白再 `=` 非 `=`)。"""
    positions = []
    for m in re.finditer(r"\.state\s*=(?!=)", code):
        # 排除 `!= ` / `>= ` / `<= `：檢 `=` 前一非空白字元
        eq = m.end() - 1
        j = eq - 1
        while j >= 0 and code[j] in " \t":
            j -= 1
        if j >= 0 and code[j] in "!<>":
            continue
        positions.append(m.start())
    return positions


def check(module_src: str) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    code = _strip_line_comments(module_src)

    defs = re.findall(rf"\bfn\s+{re.escape(MUTATOR)}\s*\(", code)
    if len(defs) != 1:
        inc.append(f"G1 expected exactly one `fn {MUTATOR}`, found {len(defs)}")
        return v, inc

    span = _fn_body_span(code, MUTATOR)
    if span is None:
        inc.append(f"G1 could not resolve `{MUTATOR}` body span")
        return v, inc
    start, end = span

    positions = _state_assign_positions(code)
    if not positions:
        inc.append("G2 no `.state =` assignment found (guard would be vacuous)")
        return v, inc

    for pos in positions:
        if not (start <= pos < end):
            line = code[:pos].count("\n") + 1
            v.append(
                f"G2 `.state =` assignment at line {line} is OUTSIDE {MUTATOR} "
                f"(second state write path = Bybit phantom-position risk)"
            )
    return v, inc


def _mutations(module_src: str):
    muts = []
    # M1:在 observe_api_pending 內注入 record.state 賦值(第二狀態寫入路徑)。
    muts.append((
        "M1 second state write in observe_api_pending",
        module_src.replace(
            "        if record.api_pending_since_ms.is_none() {",
            "        record.state = IbkrPaperOrderLifecycleState::StateUnknown;\n"
            "        if record.api_pending_since_ms.is_none() {",
        ),
    ))
    return muts


def positive_control(module_src: str) -> list[str]:
    escaped = []
    for label, ms in _mutations(module_src):
        if ms == module_src:
            escaped.append(f"{label} (mutation no-op — anchor drift)")
            continue
        v, _inc = check(ms)
        if not v:
            escaped.append(f"{label} (guard did not FAIL on injected violation)")
    return escaped


def main() -> int:
    if not MODULE.exists():
        print(f"[lifecycle-mutator-audit] INCONCLUSIVE: source absent: {MODULE}", file=sys.stderr)
        return 5
    src = MODULE.read_text(encoding="utf-8")
    v, inc = check(src)
    if inc:
        for r in inc:
            print(f"[lifecycle-mutator-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5
    escaped = positive_control(src)
    if escaped:
        for e in escaped:
            print(f"[lifecycle-mutator-audit] TOOTHLESS: {e}", file=sys.stderr)
        return 6
    if v:
        for vv in v:
            print(f"[lifecycle-mutator-audit] FAIL: {vv}", file=sys.stderr)
        return 1
    print("[lifecycle-mutator-audit] PASS: single state mutator; positive control has teeth")
    return 0


# pytest 介面
def test_single_state_mutator() -> None:
    assert MODULE.exists(), f"source absent: {MODULE}"
    v, inc = check(MODULE.read_text(encoding="utf-8"))
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"violations: {v}"


def test_positive_control_has_teeth() -> None:
    assert MODULE.exists()
    escaped = positive_control(MODULE.read_text(encoding="utf-8"))
    assert not escaped, f"positive control escaped (toothless): {escaped}"


if __name__ == "__main__":
    sys.exit(main())
