from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)
SPEC_PATH = REPO_ROOT / "docs/execution_plan/gui_redesign/design/05_utilities.md"

# §A 起點(兩邊逐字同一行)與 CSS 檔內 §B 附錄起點
SECTION_A_MARKER = "/* ═══ oc-utilities.css §A 詞彙表(P0.2;append-only,變更走 05_utilities.md §11)═══ */"
SECTION_B_MARKER = "/* ═══ §B 過渡組件附錄(annex)"


def _spec_fence() -> str:
    """抽取 05_utilities.md §4 的 ```css fence 內容(以 §A marker 開頭那一塊)。"""
    text = SPEC_PATH.read_text(encoding="utf-8")
    for m in re.finditer(r"```css\n(.*?)```", text, re.S):
        block = m.group(1)
        if SECTION_A_MARKER in block:
            return block.rstrip("\n")
    raise AssertionError("05_utilities.md 找不到含 §A marker 的 ```css fence(正本結構變了?)")


def _css_section_a() -> str:
    """抽取 oc-utilities.css 的 §A 節(§A marker 起,至 §B 附錄 marker 前)。"""
    text = (STATIC_DIR / "oc-utilities.css").read_text(encoding="utf-8")
    start = text.find(SECTION_A_MARKER)
    assert start >= 0, "oc-utilities.css 缺 §A marker(檔頭契約被改?)"
    end = text.find(SECTION_B_MARKER, start)
    if end < 0:
        end = len(text)  # 無 §B 附錄也合法(annex 可空)
    return text[start:end].rstrip("\n")


def test_oc_utilities_section_a_matches_spec_fence_byte_identical() -> None:
    """P0.2 spec-of-record 防漂移:oc-utilities.css §A 詞彙表 == 05_utilities.md §4 fence。

    oc-utilities.css 檔頭契約:§A 是規格 §4 的實作鏡像,append-only,改名/改宣告/
    刪除一律禁止直到 P0.4 複審;新增走 §11 協議(規格與 CSS 同 commit 追加)。
    本測試把「同 commit 同步」變成機械可查:兩邊逐 byte 相等,單邊改動即紅。
    §B 附錄(annex)不在比對範圍 → annex 追加不觸發本測試(append-only 友好)。
    P0.4 複審若裁決改寫 §A,規格 fence 與本 CSS 同 commit 更新,本測試自然保持綠。
    """
    spec = _spec_fence()
    css = _css_section_a()
    assert css == spec, (
        "oc-utilities.css §A 與 05_utilities.md §4 fence 漂移(spec-of-record 破約):\n"
        "首個差異行 → "
        + next(
            (
                f"css[{i}]={c!r} != spec[{i}]={s!r}"
                for i, (c, s) in enumerate(
                    zip(css.splitlines(), spec.splitlines())
                )
                if c != s
            ),
            f"行數不同 css={len(css.splitlines())} spec={len(spec.splitlines())}",
        )
    )


def test_oc_utilities_spec_fence_is_substantive() -> None:
    """正常路徑錨點(gate 雙向):fence 非空洞,防「兩邊同時清空也綠」的 vacuous pass。

    錨定詞彙表已知成員:.hidden(display 軸唯一全局定義,tab-settings 頁內副本
    已刪、console 側欄/modal 顯隱全依賴它)與 .t-dim(最大宗色階歸宿)。
    """
    spec = _spec_fence()
    assert len(spec.splitlines()) > 50, "fence 行數異常少,詞彙表疑被清空"
    assert ".hidden{ display:none!important; }" in spec, "fence 缺 .hidden 定義"
    assert ".t-dim" in spec and "--text-secondary" in spec, "fence 缺 .t-dim 色階定義"
    assert ".is-stale" in spec, "fence 缺 .is-stale 狀態類"
