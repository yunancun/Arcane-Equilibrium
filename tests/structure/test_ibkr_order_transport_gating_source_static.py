#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# test_ibkr_order_transport_gating_source_static.py
#   IBKR W7-S0 order-verb transport-gating 骨架靜態守衛（設計 §1 INV-ORDER;§1.4 四守衛）。
#
# 四條機器守衛（default-build 源級,無需編譯;fail-closed exit code）:
#   G1 send_order_framed 是 order frame 唯一出站位點:`OrderFrame` bytes 無 pub 逃逸——欄位私有 +
#      無 pub byte accessor + `into_bytes` 模塊私有 + 恰一 `fn send_order_framed`（收 OrderEffectPermit）。
#   G2 `OrderEffectPermit::mint` production 域零鑄造點（僅 cfg(test)）:`fn mint` 掛 `#[cfg(test)]` +
#      production（非 test）源零 `mint(` 呼叫點 + OrderEffectPermit 非 Clone/非 Copy + pub(crate)。
#   G3 default-build DCE（seam 0 production caller）:seam 型別/函數符號於**模塊自身以外**的 production
#      源零引用（0 caller → default artifact DCE,沿 driver/g4 audit 家族;放行臂/encoder/IPC 皆 S1-S4）。
#   G4 readonly-scope + order verb → 拒:envelope-check `readonly_operation_blocker` 把 order verb
#      家族（paper submit/cancel/replace + live/margin/options/transfer）結構性映射為
#      `OrderVerbStructurallyDenied`（order-effect 面在 readonly envelope 下結構性拒）。
#
#   正控（每守衛注入對應違規 → 守衛必 FAIL,證有牙）:注入第二出站位點 / production mint / 繞過路徑 /
#   把 order verb 挪進 readonly 白名單。
#   inconclusive（檔缺 / 標界缺 / 錨點缺 / 正控未觸發）→ **非零 exit**（fail-closed）。
#
# Exit code:
#   0 PASS         — 真源零違規 且 正控全數觸發（守衛有牙）
#   1 FAIL         — 真源 ≥1 違規
#   5 INCONCLUSIVE — 檔/標界/錨點缺（無法鑑別 → fail-closed）
#   6 TOOTHLESS    — 正控未能使守衛 FAIL（守衛無鑑別力 → fail-closed）
#
# 出典:docs/execution_plan/ibkr_live_capability/2026-07-17--w7_order_lifecycle_design.md §1;
#       仿 tests/structure/test_ibkr_tws_permit_stub_source_static.py（INV-1 對應面）。
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "rust/openclaw_engine/src"
MODULE_REL = "rust/openclaw_engine/src/ibkr_tws_order_transport.rs"
ENVELOPE_CHECK_REL = "rust/openclaw_engine/src/ibkr_activation_envelope_check.rs"
MODULE = ROOT / MODULE_REL
ENVELOPE_CHECK = ROOT / ENVELOPE_CHECK_REL

STUB_BEGIN = "EFFECT-STUB-GUARD-BEGIN"
STUB_END = "EFFECT-STUB-GUARD-END"

# seam 符號（G3 掃 production 域引用;module 自身除外）。W7-S1 追加:WireBytes（NOTE-1 (a) sealed
# 出線型別）+ place/cancel encoder（產 OrderFrame,S1 零 production caller → DCE;S4 接線移出）。
SEAM_SYMBOLS = (
    "OrderFrame",
    "OrderEffectPermit",
    "EffectEnvelopeRequiredStub",
    "EffectPermitProvider",
    "send_order_framed",
    "order_effect_capability_gate",
    "WireBytes",
    "encode_place_order",
    "encode_cancel_order",
)

# order verb 家族（G4 必全數落 OrderVerbStructurallyDenied 拒臂）。
ORDER_VERBS = (
    "PaperOrderSubmit",
    "PaperOrderCancel",
    "PaperOrderReplace",
    "LiveOrderSubmit",
    "MarginOrShort",
    "OptionsOrCfd",
    "TransferOrAccountWrite",
)


# ── 輔助 ────────────────────────────────────────────────────────────────────
def _strip_line_comments(text: str) -> str:
    """移除每行 `//` 起的行註解（掃 code 非註解）。"""
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


def _production_engine_sources() -> dict[str, str]:
    """production 域源集:engine src 全部 .rs,排除 `*_tests.rs` 與 `*/tests/*`
    （兩者皆 cfg(test) 專屬——permit 鑄造/grant 取用的合法棲地）。"""
    sources: dict[str, str] = {}
    for path in sorted(ENGINE_SRC.rglob("*.rs")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name.endswith("_tests.rs") or "/tests/" in rel:
            continue
        sources[rel] = path.read_text(encoding="utf-8", errors="ignore")
    return sources


# ── G1 send_order_framed 唯一出站位點（OrderFrame bytes 無 pub 逃逸）───────────
def check_g1(module_src: str) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    code = _strip_line_comments(module_src)

    if not re.search(r"\bstruct\s+OrderFrame\b", code):
        inc.append("G1 anchor absent: struct OrderFrame")
        return v, inc

    # (a) OrderFrame `bytes` 欄位私有（禁 `pub bytes` / `pub(crate) bytes`）。
    if re.search(r"\bpub(\(crate\))?\s+bytes\s*:", code):
        v.append("G1(a) OrderFrame.bytes field is pub/pub(crate) (order bytes must be private)")

    # (b) OrderFrame 無 pub byte accessor（as_bytes/as_slice/bytes()/into_bytes 皆不得 pub）。
    for acc in ("as_bytes", "as_slice", "into_bytes", "bytes"):
        if re.search(rf"\bpub(\(crate\))?\s+fn\s+{acc}\b", code):
            v.append(f"G1(b) OrderFrame exposes pub byte accessor `{acc}` (bytes must not escape)")

    # (c) `into_bytes` 存在且模塊私有（`fn into_bytes`,非 pub）——唯一提取點。
    if not re.search(r"\bfn\s+into_bytes\b", code):
        v.append("G1(c) OrderFrame::into_bytes extractor absent")

    # (d) 恰一 `fn send_order_framed` 定義且收 OrderEffectPermit（型別上需 permit）。
    defs = re.findall(r"\bfn\s+send_order_framed\s*\(", code)
    if len(defs) != 1:
        v.append(f"G1(d) send_order_framed definition count != 1 (found {len(defs)})")
    m = re.search(r"\bfn\s+send_order_framed\s*\((.*?)\)\s*->", code, re.S)
    if m is None or "OrderEffectPermit" not in m.group(1):
        v.append("G1(d) send_order_framed does not take OrderEffectPermit (order-effect gate missing)")

    # (e) OrderFrame bytes 唯一提取 = 恰一 `.into_bytes()` 呼叫點（在 send_order_framed 內）+
    # 恰一函數以 `OrderFrame` 為 by-value 參數（=send_order_framed;第二消費者即第二出站位點）。
    into_calls = len(re.findall(r"\.into_bytes\s*\(", code))
    if into_calls != 1:
        v.append(f"G1(e) OrderFrame::into_bytes call site count != 1 (found {into_calls}; second consumer = second outbound point)")
    frame_params = len(re.findall(r"\bfn\s+\w+\s*\([^)]*\bframe\s*:\s*OrderFrame\b", code, re.S))
    if frame_params != 1:
        v.append(f"G1(e) functions taking OrderFrame by value != 1 (found {frame_params}; only send_order_framed may consume OrderFrame)")
    return v, inc


# ── G2 OrderEffectPermit::mint production 零鑄造（僅 cfg(test)）─────────────────
def check_g2(module_src: str, prod_sources: dict[str, str]) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    region = _extract_stub_region(module_src)
    if region is None:
        inc.append(f"G2 stub guard markers {STUB_BEGIN}/{STUB_END} absent")
        return v, inc

    # (a) `fn mint` 掛 `#[cfg(test)]`（緊鄰前一屬性）。
    m = re.search(r"(#\[cfg\(test\)\]\s*)?\bpub\(crate\)\s+fn\s+mint\s*\(", region)
    if m is None:
        v.append("G2(a) OrderEffectPermit::mint (pub(crate) fn mint) absent from stub region")
    elif m.group(1) is None:
        v.append("G2(a) OrderEffectPermit::mint is NOT gated by #[cfg(test)] (production could mint)")

    # (b) OrderEffectPermit 非 Clone / 非 Copy + pub(crate)（非 pub）。
    if not re.search(r"\bpub\(crate\)\s+struct\s+OrderEffectPermit\b", region):
        v.append("G2(b) OrderEffectPermit struct is not pub(crate) (over-exposed or absent)")
    mm = re.search(r"(?s)(.*?)\bpub\(crate\)\s+struct\s+OrderEffectPermit\b", region)
    if mm is not None:
        preceding = mm.group(1)[-160:]
        for d in re.findall(r"#\[derive\(([^)]*)\)\]", preceding):
            if "Clone" in d or "Copy" in d:
                v.append("G2(b) OrderEffectPermit derives Clone/Copy (must be single-use)")

    # (c) production（非 test）源零 `OrderEffectPermit::mint(` / `Self::mint(` 呼叫點。
    # 範圍鎖 order-effect permit 的 mint（`bare mint(` 會誤命中 pacing/live_authz 等其他型別）。
    for rel, src in prod_sources.items():
        c = _strip_line_comments(src)
        if re.search(r"\bOrderEffectPermit::mint\s*\(", c):
            v.append(f"G2(c) OrderEffectPermit::mint call site in production source: {rel}")
        # 模塊自身:`Self::mint(` 亦指 OrderEffectPermit::mint（cfg(test) 定義以外零呼叫）。
        if rel == MODULE_REL and re.search(r"\bSelf::mint\s*\(", c):
            v.append(f"G2(c) Self::mint call site in seam module production code: {rel}")
    return v, inc


# ── G3 default-build DCE（seam 0 production caller,module 自身除外）────────────
def check_g3(prod_sources: dict[str, str]) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    if MODULE_REL not in prod_sources:
        inc.append(f"G3 seam module absent: {MODULE_REL}")
        return v, inc
    for rel, src in prod_sources.items():
        if rel == MODULE_REL:
            continue
        c = _strip_line_comments(src)
        for sym in SEAM_SYMBOLS:
            if re.search(rf"\b{re.escape(sym)}\b", c):
                v.append(f"G3 seam symbol `{sym}` referenced in production source {rel} "
                         f"(S0 must have 0 production caller → default-build DCE)")
    return v, inc


# ── G4 readonly-scope + order verb → 拒（envelope-check 結構性拒臂）─────────────
def check_g4(envelope_src: str) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    code = _strip_line_comments(envelope_src)
    m = re.search(r"fn\s+readonly_operation_blocker\s*\(.*?\{(.*)\n\}", code, re.S)
    if m is None:
        inc.append("G4 anchor absent: readonly_operation_blocker")
        return v, inc
    body = m.group(1)
    # 只抓緊鄰 deny `=>` 之前的 `Op::...` 鏈（非整段 body,否則 readonly 白名單的 Op 會誤入）。
    # 分隔管線設為必需(每次重複前綴 `\s*\|\s*`),消除 `(\s*\|?\s*…)+` 對空白的歧義切分
    # →避免 catastrophic backtracking(CodeQL py/redos);行為等價:仍抓緊鄰 deny `=>` 前的 `Op::…` 鏈。
    deny = re.search(r"\|?\s*(Op::\w+(?:\s*\|\s*Op::\w+)*)\s*=>\s*Some\(\s*B::OrderVerbStructurallyDenied\s*\)", body)
    if deny is None:
        inc.append("G4 anchor absent: OrderVerbStructurallyDenied deny arm")
        return v, inc
    deny_pattern = deny.group(1)
    for verb in ORDER_VERBS:
        # verb 必出現在 OrderVerbStructurallyDenied 拒臂的 pattern（該 `=>` 之前的 match arm）。
        if not re.search(rf"\bOp::{verb}\b", deny_pattern):
            v.append(f"G4 order verb `{verb}` not structurally denied under readonly envelope")
    return v, inc


# ── G5 NOTE-1 (a) 型別屏障:order-verb wire bytes 唯經 gated send_order_framed 出線 ──────
#    （承 W7-S1 NOTE-1 擇 (a):send_order_framed 回 sealed WireBytes 取代裸 Vec<u8>;order-verb
#     encoder 產物是 sealed OrderFrame。型別層阻斷 order bytes 直達 effect-ungated 的
#     `ibkr_tws_driver::send_framed(&[u8])`（NOTE-1 平行出線 seam）。）
def check_g5(module_src: str) -> tuple[list[str], list[str]]:
    v: list[str] = []
    inc: list[str] = []
    code = _strip_line_comments(module_src)

    if not re.search(r"\bstruct\s+WireBytes\b", code):
        inc.append("G5 anchor absent: struct WireBytes (NOTE-1 (a) sealed out type)")
        return v, inc

    # (a) send_order_framed 回 sealed WireBytes（非裸 Vec<u8>）——gated 出線產物本身 sealed。
    m = re.search(r"\bfn\s+send_order_framed\s*\(.*?\)\s*->\s*([A-Za-z0-9_<>]+)", code, re.S)
    if m is None:
        v.append("G5(a) send_order_framed signature not found")
    elif m.group(1).strip() != "WireBytes":
        v.append(f"G5(a) send_order_framed must return sealed WireBytes, got `{m.group(1).strip()}` (raw bytes escape gated boundary)")

    # (b) WireBytes pub(crate) 且無 pub byte accessor（bytes 私有;into_wire 模塊私有）。
    if not re.search(r"\bpub\(crate\)\s+struct\s+WireBytes\b", code):
        v.append("G5(b) WireBytes struct is not pub(crate) (over-exposed or absent)")
    if re.search(r"\bpub(\(crate\))?\s+bytes\s*:", code):
        # 注:此 regex 亦覆蓋 OrderFrame.bytes（G1 已管）,WireBytes.bytes 同紀律必私有。
        pass  # 由 G1(a) 已斷言 bytes 私有;此處不重複計數。
    for acc in ("as_bytes", "as_slice", "into_bytes", "bytes", "into_wire"):
        # into_wire 是 WireBytes 的模塊私有提取點:不得 pub（否則裸 bytes 逃逸）。
        if re.search(rf"\bpub(\(crate\))?\s+fn\s+{acc}\b", code):
            v.append(f"G5(b) WireBytes/OrderFrame exposes pub byte accessor `{acc}` (bytes must not escape gated boundary)")

    # (c) order-verb encoder 產物是 sealed OrderFrame（非裸 Vec<u8>）——encoder 輸出即受 INV-ORDER。
    for enc in ("encode_place_order", "encode_cancel_order"):
        me = re.search(rf"\bfn\s+{enc}\s*\(.*?\)\s*->\s*([^{{]+)\{{", code, re.S)
        if me is None:
            v.append(f"G5(c) encoder `{enc}` signature not found")
        elif "OrderFrame" not in me.group(1):
            v.append(f"G5(c) encoder `{enc}` must yield OrderFrame (order bytes must be sealed, not raw)")

    # (d) E3-N2/E2-NOTE-6:禁 leak-trait impl 使 sealed 型別 coerce 繞封（未來加 `impl Deref<
    # Target=[u8]>` 可 `&wire` coerce 成 `&[u8]` 餵 send_framed 而 G5(a-c) 仍綠）。黑名單對
    # WireBytes/OrderFrame 的 Deref/DerefMut/AsRef/AsMut/Borrow/BorrowMut/Index/Into 及
    # `From<WireBytes|OrderFrame> for Vec<u8>/[u8]`。
    leak_traits = ("Deref", "DerefMut", "AsRef", "AsMut", "Borrow", "BorrowMut", "Index")
    for sealed in ("WireBytes", "OrderFrame"):
        for tr in leak_traits:
            if re.search(rf"\bimpl\b[^\n]*\b{tr}\b[^\n]*\bfor\s+{sealed}\b", code):
                v.append(f"G5(d) leak-trait `impl {tr} for {sealed}` (byte coercion escapes seal)")
        # From<Sealed> for Vec<u8>/[u8]（into-bytes 逃逸面）。
        if re.search(rf"\bimpl\b[^\n]*\bFrom\s*<\s*{sealed}\s*>\s*for\s+(Vec\s*<\s*u8|&?\s*\[\s*u8)", code):
            v.append(f"G5(d) `impl From<{sealed}> for [u8]/Vec<u8>` (into-bytes escape)")

    # (e) WireBytes::view（test-only bytes 檢視）必保持 #[cfg(test)]（production 不成 bytes 逃逸面;
    # 同 mint 紀律）。抓 `fn view` 前是否緊鄰 #[cfg(test)]。
    mv = re.search(r"(#\[cfg\(test\)\]\s*)?\bpub\(crate\)\s+fn\s+view\s*\(", code)
    if mv is None:
        inc.append("G5(e) anchor absent: WireBytes::view accessor")
    elif mv.group(1) is None:
        v.append("G5(e) WireBytes::view is NOT gated by #[cfg(test)] (production bytes escape)")
    return v, inc


def _extract_stub_region(module_src: str) -> str | None:
    b = module_src.find(STUB_BEGIN)
    e = module_src.find(STUB_END)
    if b < 0 or e < 0 or e <= b:
        return None
    return module_src[b:e]


# ── 全稽核（純函數;正控可對 mutated 源重跑）─────────────────────────────────────
def run_checks(module_src: str, envelope_src: str, prod_sources: dict[str, str]) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    inconclusive: list[str] = []
    for fn, args in (
        (check_g1, (module_src,)),
        (check_g2, (module_src, prod_sources)),
        (check_g3, (prod_sources,)),
        (check_g4, (envelope_src,)),
        (check_g5, (module_src,)),
    ):
        v, inc = fn(*args)  # type: ignore[operator]
        violations += v
        inconclusive += inc
    return violations, inconclusive


# ── 正控:每 mutation 必使守衛 FAIL ────────────────────────────────────────────
def _mutations(module_src: str, envelope_src: str, prod_sources: dict[str, str]):
    """回 (label, module_src', envelope_src', prod_sources')。每個都應觸發 ≥1 violation。"""
    muts = []

    # M1（G1）:OrderFrame 加 pub byte accessor（bytes 逃逸,可繞 send_order_framed）。
    muts.append((
        "M1 pub as_bytes accessor on OrderFrame",
        module_src.replace(
            "    fn into_bytes(self) -> Vec<u8> {",
            "    pub(crate) fn as_bytes(&self) -> &[u8] { &self.bytes }\n    fn into_bytes(self) -> Vec<u8> {",
        ),
        envelope_src, prod_sources,
    ))
    # M2（G1）:第二個消費 OrderFrame 的出站函數（第二出站位點）。
    muts.append((
        "M2 second outbound point consuming OrderFrame",
        module_src.replace(
            "pub(crate) fn send_order_framed(",
            "pub(crate) fn send_order_bypass(frame: OrderFrame) -> Vec<u8> { frame.into_bytes() }\n"
            "pub(crate) fn send_order_framed(",
        ),
        envelope_src, prod_sources,
    ))
    # M3（G2）:mint 去掉 #[cfg(test)]（production 可鑄 permit）。
    muts.append((
        "M3 production mint (cfg(test) removed)",
        module_src.replace(
            "    #[cfg(test)]\n    pub(crate) fn mint()",
            "    pub(crate) fn mint()",
        ),
        envelope_src, prod_sources,
    ))
    # M4（G2）:OrderEffectPermit 派生 Clone（可復用授權）。
    muts.append((
        "M4 OrderEffectPermit derives Clone",
        module_src.replace(
            "pub(crate) struct OrderEffectPermit {",
            "#[derive(Clone)]\npub(crate) struct OrderEffectPermit {",
        ),
        envelope_src, prod_sources,
    ))
    # M5（G2 / G3）:另一 production 源注入 mint 呼叫點 + seam 引用（繞過/自鑄）。
    inj = dict(prod_sources)
    tgt = "rust/openclaw_engine/src/ibkr_tws_driver.rs"
    if tgt in inj:
        inj[tgt] = inj[tgt] + "\nfn m5_forge() { let _p = OrderEffectPermit::mint(); }\n"
    muts.append(("M5 production mint call + seam ref in driver", module_src, envelope_src, inj))
    # M6（G4）:把 PaperOrderSubmit 從拒臂挪進 readonly 白名單（None 臂放行 order verb）。
    muts.append((
        "M6 PaperOrderSubmit moved to readonly whitelist",
        module_src,
        envelope_src.replace(
            "        Op::PaperOrderSubmit\n        | Op::PaperOrderCancel",
            "        Op::PaperOrderCancel",
        ).replace(
            "Op::ContractDetailsRead => {\n            None\n        }",
            "Op::ContractDetailsRead | Op::PaperOrderSubmit => {\n            None\n        }",
        ),
        prod_sources,
    ))
    # M7（G5a）:send_order_framed 回裸 Vec<u8>（gated 出線退化為可餵 send_framed 的裸 bytes）。
    muts.append((
        "M7 send_order_framed returns raw Vec<u8>",
        module_src.replace(
            "    frame: OrderFrame,\n) -> WireBytes {",
            "    frame: OrderFrame,\n) -> Vec<u8> {",
        ),
        envelope_src, prod_sources,
    ))
    # M8（G5b）:WireBytes 加 pub byte accessor（裸 bytes 逃逸 gated 邊界）。
    muts.append((
        "M8 pub accessor on WireBytes",
        module_src.replace(
            "    fn into_wire(self) -> Vec<u8> {",
            "    pub(crate) fn as_bytes(&self) -> &[u8] { &self.bytes }\n    fn into_wire(self) -> Vec<u8> {",
        ),
        envelope_src, prod_sources,
    ))
    # M9（G5c）:encode_place_order 回裸 Vec<u8>（order bytes 不再 sealed 於 OrderFrame）。
    muts.append((
        "M9 encode_place_order yields raw Vec<u8>",
        module_src.replace(
            "pub(crate) fn encode_place_order(\n    req: &PlaceOrderWireRequest,\n    server_version: i32,\n) -> Result<OrderFrame, OrderEncodeReject> {",
            "pub(crate) fn encode_place_order(\n    req: &PlaceOrderWireRequest,\n    server_version: i32,\n) -> Result<Vec<u8>, OrderEncodeReject> {",
        ),
        envelope_src, prod_sources,
    ))
    # M10（G5d）:加 `impl Deref<Target=[u8]> for WireBytes`（byte coercion 繞封）。
    muts.append((
        "M10 impl Deref for WireBytes",
        module_src.replace(
            "impl WireBytes {",
            "impl std::ops::Deref for WireBytes { type Target = [u8]; fn deref(&self) -> &[u8] { &self.bytes } }\nimpl WireBytes {",
        ),
        envelope_src, prod_sources,
    ))
    # M11（G5e）:WireBytes::view 去掉 #[cfg(test)]（production bytes 逃逸）。
    muts.append((
        "M11 WireBytes::view un-cfg(test)",
        module_src.replace(
            "    #[cfg(test)]\n    pub(crate) fn view(&self)",
            "    pub(crate) fn view(&self)",
        ),
        envelope_src, prod_sources,
    ))
    return muts


def positive_control(module_src: str, envelope_src: str, prod_sources: dict[str, str]) -> list[str]:
    escaped: list[str] = []
    for label, ms, es, ps in _mutations(module_src, envelope_src, prod_sources):
        if ms == module_src and es == envelope_src and ps == prod_sources:
            escaped.append(f"{label} (mutation was a no-op — anchor text drift)")
            continue
        v, _inc = run_checks(ms, es, ps)
        if not v:
            escaped.append(f"{label} (guard did not FAIL on injected violation)")
    return escaped


# ── 主入口（standalone;fail-closed exit code）────────────────────────────────
def main() -> int:
    if not MODULE.exists():
        print(f"[order-transport-audit] INCONCLUSIVE: source absent: {MODULE}", file=sys.stderr)
        return 5
    if not ENVELOPE_CHECK.exists():
        print(f"[order-transport-audit] INCONCLUSIVE: source absent: {ENVELOPE_CHECK}", file=sys.stderr)
        return 5
    module_src = MODULE.read_text(encoding="utf-8")
    envelope_src = ENVELOPE_CHECK.read_text(encoding="utf-8")
    prod_sources = _production_engine_sources()

    violations, inconclusive = run_checks(module_src, envelope_src, prod_sources)
    if inconclusive:
        for r in inconclusive:
            print(f"[order-transport-audit] INCONCLUSIVE: {r}", file=sys.stderr)
        return 5
    escaped = positive_control(module_src, envelope_src, prod_sources)
    if escaped:
        for e in escaped:
            print(f"[order-transport-audit] TOOTHLESS: positive control escaped: {e}", file=sys.stderr)
        return 6
    if violations:
        for vv in violations:
            print(f"[order-transport-audit] FAIL: {vv}", file=sys.stderr)
        return 1
    print("[order-transport-audit] PASS: INV-ORDER G1-G5 satisfied; positive controls have teeth")
    return 0


# ── pytest 介面（與 standalone 同源）──────────────────────────────────────────
def test_g1_send_order_framed_sole_outbound_point() -> None:
    assert MODULE.exists(), f"source absent: {MODULE}"
    v, inc = check_g1(MODULE.read_text(encoding="utf-8"))
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"G1 violations: {v}"


def test_g2_order_effect_permit_mint_zero_production() -> None:
    assert MODULE.exists(), f"source absent: {MODULE}"
    v, inc = check_g2(MODULE.read_text(encoding="utf-8"), _production_engine_sources())
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"G2 violations: {v}"


def test_g3_seam_default_build_dce_zero_production_caller() -> None:
    v, inc = check_g3(_production_engine_sources())
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"G3 violations: {v}"


def test_g4_readonly_envelope_order_verb_structurally_denied() -> None:
    assert ENVELOPE_CHECK.exists(), f"source absent: {ENVELOPE_CHECK}"
    v, inc = check_g4(ENVELOPE_CHECK.read_text(encoding="utf-8"))
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"G4 violations: {v}"


def test_g5_note1_sealed_wire_bytes_type_barrier() -> None:
    assert MODULE.exists(), f"source absent: {MODULE}"
    v, inc = check_g5(MODULE.read_text(encoding="utf-8"))
    assert not inc, f"inconclusive: {inc}"
    assert not v, f"G5 violations: {v}"


def test_positive_controls_have_teeth() -> None:
    assert MODULE.exists() and ENVELOPE_CHECK.exists()
    escaped = positive_control(
        MODULE.read_text(encoding="utf-8"),
        ENVELOPE_CHECK.read_text(encoding="utf-8"),
        _production_engine_sources(),
    )
    assert not escaped, f"positive controls escaped (guard toothless): {escaped}"


if __name__ == "__main__":
    sys.exit(main())
