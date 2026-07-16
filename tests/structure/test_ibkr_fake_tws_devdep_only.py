#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# test_ibkr_fake_tws_devdep_only.py
#   IBKR-CI-3 (a) structure 守衛（CC 約束 ⑤;設計 §4「production 缺席機器斷言 ②」）。
#
# 斷言（掃全 workspace 成員 Cargo.toml,純源級,無需編譯）:
#   (a) **無任何 workspace 成員**在 `[dependencies]` / `[build-dependencies]`（production dep）引入
#       `openclaw_fake_tws`——fake crate 只允許出現在 `[dev-dependencies]`（default `cargo build`
#       不編譯 → 引擎 artifact 零 fake 符號）。
#   (b) `openclaw_engine` 的 `[dev-dependencies]` **確有** `openclaw_fake_tws`（證正確接線為 dev-dep）。
#   (c) `openclaw_fake_tws` **不** 依賴 `openclaw_engine`（engine-independent;避 dev-dep cycle 的
#       重複編譯單元陷阱——見 crate Cargo.toml/lib.rs）。
#   (d) 正控:臨時把 fake crate 加進 production `[dependencies]` / 移除 engine dev-dep / 令 fake 依賴
#       engine → 守衛必 FAIL（證有牙）。
#   (e) inconclusive（workspace / 成員檔缺 / member 清單解析失敗 / 正控未觸發）→ 非零 exit（fail-closed）。
#
# Exit code:
#   0  PASS         — 真源零違規 且 正控全數觸發（守衛有牙）
#   1  FAIL         — 真源 ≥1 違規
#   5  INCONCLUSIVE — workspace/成員檔缺 / 錨點缺（無法鑑別 → fail-closed,不報 PASS）
#   6  TOOTHLESS    — 正控未能使守衛 FAIL（守衛無鑑別力 → fail-closed）
#
# 出典:docs/execution_plan/ibkr_live_capability/2026-07-15--w3_session_manager_design.md §4/§10;
#       仿 helper_scripts/ci/ibkr_g4_symbol_audit.sh 的 fail-closed / 正控 範式。
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TOML = ROOT / "rust/Cargo.toml"
FAKE_CRATE = "openclaw_fake_tws"
ENGINE_CRATE = "openclaw_engine"
PROD_SECTIONS = ("dependencies", "build-dependencies")


# ── TOML 節/依賴解析（純線性,無外部依賴;section-aware）────────────────────────
def parse_dep_sections(toml_text: str) -> dict[str, set[str]]:
    """回 {section_base: {dep_name,...}}。section_base ∈ dependencies / build-dependencies /
    dev-dependencies / target-dependencies…（本檔只關心前三 + target.* 的 production dep）。
    dep 名來自:(1) `[<section>]` 內的 `name = ...` / `name.xxx = ...` 鍵行;(2) `[<section>.name]`
    子表頭。target-specific（`[target.'cfg(...)'.dependencies]`）歸入其 dependencies/dev 類。"""
    out: dict[str, set[str]] = {}
    cur_section: str | None = None  # 正規化後的 section base（e.g. dependencies）
    cur_subtable_dep: str | None = None  # `[<section>.name]` 情形的 name

    def section_base(header: str) -> tuple[str | None, str | None]:
        """由 header（不含 []）取 (section_base, subtable_dep)。認 dependencies/build-dependencies/
        dev-dependencies,含 target.'...'.<section> 前綴;`<section>.<name>` → subtable_dep=<name>。"""
        parts = header.split(".")
        # 找 section 關鍵字位置。
        for i, p in enumerate(parts):
            if p in ("dependencies", "build-dependencies", "dev-dependencies"):
                sub = ".".join(parts[i + 1 :]) if i + 1 < len(parts) else None
                return p, (sub or None)
        return None, None

    for raw in toml_text.splitlines():
        line = raw.split("#", 1)[0].rstrip()  # 去行註解
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\[+([^\]]+)\]+\s*$", stripped)
        if m:
            header = m.group(1).strip()
            base, sub = section_base(header)
            cur_section = base
            cur_subtable_dep = sub
            if base is not None:
                out.setdefault(base, set())
                if sub:
                    # `[dependencies.foo]` → foo 是該 section 的依賴（取子表首段,防 foo.bar）。
                    out[base].add(sub.split(".")[0].strip('"').strip("'"))
            continue
        if cur_section in ("dependencies", "build-dependencies", "dev-dependencies"):
            if cur_subtable_dep:
                # 已在 `[<section>.name]` 子表內,鍵行是該 dep 的欄位,非新 dep。
                continue
            km = re.match(r'^([A-Za-z0-9_\-]+|"[^"]+")\s*(=|\.)', stripped)
            if km:
                name = km.group(1).strip('"')
                out[cur_section].add(name)
    return out


# ── 核心稽核（純函數;正控可對 mutated tomls 重跑）─────────────────────────────
def run_checks(member_tomls: dict[str, str]) -> tuple[list[str], list[str]]:
    """member_tomls: {crate_name: cargo_toml_text}。回 (violations, inconclusive)。"""
    violations: list[str] = []
    inconclusive: list[str] = []

    if not member_tomls:
        inconclusive.append("no workspace member Cargo.toml resolved")
        return violations, inconclusive
    if ENGINE_CRATE not in member_tomls:
        inconclusive.append(f"anchor member {ENGINE_CRATE} Cargo.toml absent")
        return violations, inconclusive
    if FAKE_CRATE not in member_tomls:
        inconclusive.append(f"anchor member {FAKE_CRATE} Cargo.toml absent")
        return violations, inconclusive

    # (a) 無任何成員在 production dep 引入 fake crate。
    for crate, text in member_tomls.items():
        secs = parse_dep_sections(text)
        for prod in PROD_SECTIONS:
            if FAKE_CRATE in secs.get(prod, set()):
                violations.append(
                    f"(a) {crate} declares {FAKE_CRATE} in [{prod}] "
                    f"(fake crate must be dev-dependencies only)"
                )

    # (b) engine 的 dev-dependencies 確有 fake crate（正確接線）。
    engine_secs = parse_dep_sections(member_tomls[ENGINE_CRATE])
    if FAKE_CRATE not in engine_secs.get("dev-dependencies", set()):
        violations.append(
            f"(b) {ENGINE_CRATE} does not declare {FAKE_CRATE} in [dev-dependencies] "
            f"(fake harness not wired as dev-dep)"
        )

    # (c) fake crate 不依賴 engine（engine-independent;避 dev-dep cycle 陷阱）。
    fake_secs = parse_dep_sections(member_tomls[FAKE_CRATE])
    for prod in PROD_SECTIONS:
        if ENGINE_CRATE in fake_secs.get(prod, set()):
            violations.append(
                f"(c) {FAKE_CRATE} depends on {ENGINE_CRATE} in [{prod}] "
                f"(must stay engine-independent; dev-dep cycle causes non-unifying dup crate units)"
            )

    return violations, inconclusive


# ── workspace 成員解析 ────────────────────────────────────────────────────────
def resolve_member_tomls() -> dict[str, str]:
    """由 rust/Cargo.toml 的 [workspace] members 解析各成員 Cargo.toml 文本（{crate_name: text}）。"""
    if not WORKSPACE_TOML.exists():
        return {}
    raw = WORKSPACE_TOML.read_text(encoding="utf-8")
    # 先去行註解（避免 members 陣列內註解的 `]`（如 `[dev-dependencies]`）誤截非貪婪匹配）。
    ws = "\n".join(line.split("#", 1)[0] for line in raw.splitlines())
    # 抽 members = [ "a", "b", ... ]（跨行）。
    mm = re.search(r"members\s*=\s*\[(.*?)\]", ws, re.DOTALL)
    if not mm:
        return {}
    members = re.findall(r'"([^"]+)"', mm.group(1))
    out: dict[str, str] = {}
    for rel in members:
        member_toml = ROOT / "rust" / rel / "Cargo.toml"
        if not member_toml.exists():
            continue
        text = member_toml.read_text(encoding="utf-8")
        nm = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', text)
        crate = nm.group(1) if nm else rel
        out[crate] = text
    return out


# ── 正控(d):每個 mutation 必使守衛 FAIL ───────────────────────────────────────
def _mutations(member_tomls: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    muts: list[tuple[str, dict[str, str]]] = []

    # A:把 fake crate 加進 engine 的 production [dependencies]。
    m1 = dict(member_tomls)
    m1[ENGINE_CRATE] = member_tomls[ENGINE_CRATE].replace(
        "[dependencies]",
        f'[dependencies]\n{FAKE_CRATE} = {{ path = "../{FAKE_CRATE}" }}',
        1,
    )
    muts.append(("A fake crate injected into engine [dependencies]", m1))

    # B:移除 engine 的 dev-dep fake crate。
    m2 = dict(member_tomls)
    m2[ENGINE_CRATE] = re.sub(
        rf"(?m)^{re.escape(FAKE_CRATE)}\s*=.*$", "", member_tomls[ENGINE_CRATE]
    )
    muts.append(("B engine dev-dep fake crate removed", m2))

    # C:令 fake crate 依賴 engine（重建 cycle）。
    m3 = dict(member_tomls)
    m3[FAKE_CRATE] = member_tomls[FAKE_CRATE].replace(
        "[dependencies]",
        f'[dependencies]\n{ENGINE_CRATE} = {{ path = "../{ENGINE_CRATE}" }}',
        1,
    )
    muts.append(("C fake crate depends on engine (cycle)", m3))

    return muts


def positive_control(member_tomls: dict[str, str]) -> list[str]:
    escaped: list[str] = []
    for label, mutated in _mutations(member_tomls):
        if mutated == member_tomls:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, _inc = run_checks(mutated)
        if not v:
            escaped.append(f"{label} (guard did not FAIL on injected violation)")
    return escaped


# ── 主入口(standalone;fail-closed exit code)──────────────────────────────────
def main() -> int:
    member_tomls = resolve_member_tomls()
    violations, inconclusive = run_checks(member_tomls)
    if inconclusive:
        for r in inconclusive:
            print(f"[fake-devdep-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5

    escaped = positive_control(member_tomls)
    if escaped:
        for e in escaped:
            print(f"[fake-devdep-audit] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6

    if violations:
        for v in violations:
            print(f"[fake-devdep-audit] FAIL: {v}", file=sys.stderr)
        return 1

    print(
        "[fake-devdep-audit] PASS: openclaw_fake_tws is dev-dependencies-only, "
        "engine-wired, engine-independent; positive controls have teeth"
    )
    return 0


# ── pytest 介面(與 standalone 同源)────────────────────────────────────────────
def test_fake_tws_is_dev_dependency_only() -> None:
    member_tomls = resolve_member_tomls()
    violations, inconclusive = run_checks(member_tomls)
    assert not inconclusive, f"inconclusive: {inconclusive}"
    assert not violations, f"violations: {violations}"


def test_fake_tws_devdep_positive_controls_have_teeth() -> None:
    member_tomls = resolve_member_tomls()
    assert member_tomls, "no workspace members resolved"
    escaped = positive_control(member_tomls)
    assert not escaped, f"positive controls escaped (guard toothless): {escaped}"


if __name__ == "__main__":
    sys.exit(main())
