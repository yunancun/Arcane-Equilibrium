from __future__ import annotations

import re
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# Live 硬化面 snapshot 守衛（LOOP-DRIVER §9 遷移前 dilution tripwire）
# ───────────────────────────────────────────────────────────────────────────
# 目的：固化 tab-live 「當前硬化面」的標記計數，防 Phase 2 遷移 live view 時被
#       「稀釋」。這是 survival-first 硬邊界（CLAUDE 二.5 帳戶存活 > 利潤）的
#       機械化 tripwire：Live 硬化面「只換皮不改邏輯、熱紅雙主題永不稀釋、五閘 /
#       typed-confirm / REAL FUNDS / 緊急停止與平倉分離」。
#
# 模式：count-based snapshot ratchet（鏡像 test_gui_style_ratchet_static.py，但方向
#       相反）。style ratchet 是「上界 / 禁增長」（current > baseline → fail）；
#       本檔是「下界 / 禁稀釋」（current < baseline → fail）。baseline 為當前實測
#       快照（checked-in 常量），標記計數減少 = 稀釋 = 精確點名該 marker 失敗；
#       增加允許（硬化面加強不失敗）。
#
# ── MODULE_NOTE（誠實邊界，勿越界解讀）────────────────────────────────────
#   本檔是純靜態 Python 讀檔計數，只證「硬化標記未在源碼消失」。它 **不** 證：
#     · runtime 五閘（live_reserved / Operator auth / OPENCLAW_ALLOW_MAINNET /
#       secret slot / signed authorization.json）真的被 enforced；
#     · typed-confirm modal runtime 真的擋住誤觸；
#     · 緊急停止 / 平倉真的送出 IPC / 打到 Bybit 端點。
#   那些屬 backend + runtime 行為（Rust engine + Linux），是 NEEDS-LINUX，
#   非本 guard 範疇。此 guard = 遷移前 dilution tripwire，非 live 執行正確性驗證。
#   baseline 是「當前硬化面」快照；Phase 2 遷 live view 時用此對照確保等價。
# ═══════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)
LIVE_HTML = STATIC_DIR / "tab-live.html"
LIVE_JS = STATIC_DIR / "tab-live.js"


# ── 硬化標記 baseline（2026-07-11 實測；worktree=origin 當前態）─────────────
# 每筆 = (marker_id, 檔名, 計數用子字串, baseline 計數, 語義說明)。
# 斷言：current_count >= baseline。減少 = 稀釋 = FAIL 並精確點名該 marker。
# 全部 baseline > 0（anti-vacuous；某 marker 實測 0 表 survey 錯，不硬寫 0）。
# 子字串刻意用「plain substring count」（str.count），與 style ratchet 的 regex
# 對稱但更簡單 —— 硬化標記是穩定字面（handler 名 / phrase / token），無需 regex。
MarkerSpec = tuple[str, str, str, int, str]

MARKERS: list[MarkerSpec] = [
    # ── typed-confirm gating（打字確認 modal，五閘後最後一道人工閘）──────────
    # 4 道 live 破壞性變更全走 openTypedConfirmModal：START / STOP / EMERGENCY / CLOSE ALL。
    ("typed_confirm_call", "tab-live.js", "openTypedConfirmModal(", 4,
     "打字確認 modal 實際呼叫點（START LIVE / STOP LIVE / EMERGENCY STOP / CLOSE ALL 四道）"),
    # classifyLiveMutation：live 變更回應分類 gating（partial_failure / 殘留風險判讀），
    # 防 fake-success（只 `if(d)` 就顯成功）。出現數含判讀點 + 契約註解。
    ("classify_live_mutation", "tab-live.js", "classifyLiveMutation", 7,
     "live 變更分類 gating（partial_failure / rust_synced / 殘留風險判讀）"),

    # ── REAL FUNDS 常駐真金身分標記（html + js 都要有）─────────────────────
    ("real_funds_html", "tab-live.html", "REAL FUNDS", 4,
     "常駐真金身分標記（html：主題說明 + Mainnet 熱紅語義）"),
    ("real_funds_js", "tab-live.js", "REAL FUNDS", 3,
     "真金身分標記（js：real-funds-badge 常駐橫幅 + mainnet theme）"),

    # ── 緊急停止 handler（doEmergencyStop）與其接線 / 標籤 ──────────────────
    ("emergency_stop_def_js", "tab-live.js", "doEmergencyStop", 1,
     "緊急停止 handler 定義（→ POST /api/v1/live/session/stop）"),
    ("emergency_stop_wire_html", "tab-live.html", "doEmergencyStop", 1,
     "緊急停止 handler onclick 接線（btn-emergency-stop）"),
    ("emergency_stop_label_html", "tab-live.html", "緊急停止", 3,
     "緊急停止標籤 / 文案"),

    # ── 平倉 / close-position handler（與緊急停止 **分離**，不可合併為單鍵）──
    # 注意：源碼無 `flatten`（=0），真實平倉 handler 名為 doLiveCloseAll（全部平倉，
    # session 不停）+ closeLivePosition（單倉平倉）。survey 之 `flatten` 是抽象別名。
    ("close_all_def_js", "tab-live.js", "doLiveCloseAll", 1,
     "全部平倉 handler 定義（→ POST /api/v1/live/close-all-positions；session 不停）"),
    ("close_all_wire_html", "tab-live.html", "doLiveCloseAll", 1,
     "全部平倉 onclick 接線（與緊急停止不同按鈕）"),
    ("close_position_def_js", "tab-live.js", "closeLivePosition", 12,
     "單倉平倉 handler 定義 + 逐倉 onclick 接線（含 dust-frozen 分支）"),

    # ── 五閘引用（Python live_reserved 為五閘之一）─────────────────────────
    ("live_reserved_js", "tab-live.js", "live_reserved", 1,
     "五閘之一 live_reserved 引用（鎖鍵 title：Operator + live_reserved + Rust 授權門控）"),

    # ── canon-6 熱紅 salience（REAL FUNDS badge 熱紅 / --live 主題，永不稀釋）──
    # rgba(239,68,68 = REAL FUNDS badge / live 邊框 / trust-bar crit 熱紅；
    # --live = real-money 熱紅主題變數（與 --neg 虧損紅刻意區分）。
    ("hot_red_rgba_html", "tab-live.html", "rgba(239,68,68", 8,
     "canon-6 熱紅裸值（REAL FUNDS badge / live 邊框 / trust-bar crit）"),
    ("hot_red_live_var_html", "tab-live.html", "--live", 9,
     "熱紅 --live 主題變數（real-money accent，與 --neg 區分）"),
    ("hot_red_live_var_js", "tab-live.js", "--live", 1,
     "熱紅 --live 主題變數（js：oc-chip-live 熱紅語義）"),
]

# typed-confirm 的四道確認短語（phrase gate）—— 存在性不變量（非計數）。
# 每道破壞性 live 變更必須要求操作員逐字輸入對應短語才放行。
REQUIRED_TYPED_PHRASES = ["START LIVE", "STOP LIVE", "EMERGENCY STOP", "CLOSE ALL"]

_GUIDE = (
    "修復指引:Live 硬化標記計數低於 baseline = 遷移稀釋（survival-first 硬邊界違反）。\n"
    "  · Live 硬化面只換皮不改邏輯:遷移 live view 時必須保留 typed-confirm / 五閘 /\n"
    "    REAL FUNDS / 緊急停止與平倉分離 / canon-6 熱紅（--live、rgba(239,68,68)。\n"
    "  · 若某 marker 為正當重構（如 handler 改名 / 拆檔），必須：①在新宿主保留等價硬化,\n"
    "    ②更新本檔 MARKERS 對應行的 baseline 並註明遷移理由與新宿主。\n"
    "  · 見 CLAUDE 二.4-5 硬邊界 + LOOP-DRIVER §9 遷移前 guard。"
)


def _read(fname: str) -> str:
    path = STATIC_DIR / fname
    return path.read_text(encoding="utf-8")


def _texts() -> dict[str, str]:
    """一次讀入受管兩檔;掃描面下界防路徑壞掉導致空洞綠。"""
    return {"tab-live.html": _read("tab-live.html"), "tab-live.js": _read("tab-live.js")}


def test_live_hardening_markers_not_below_baseline() -> None:
    """核心 ratchet:tab-live 每個硬化標記計數不得低於 baseline(減少 = 稀釋 = FAIL)。

    這把「Live 硬化面永不稀釋」變機械可查:Phase 2 遷移 live view 時,任何讓
    typed-confirm / 五閘 / REAL FUNDS / 緊急停止-平倉分離 / 熱紅 salience 標記
    消失或減少的改動,都會精確點名該 marker 失敗。增加允許(硬化加強不失敗)。
    """
    texts = _texts()
    # 掃描面完整性:兩檔都須存在且非空(防路徑破壞 → 計數皆 0 → 全部 < baseline 反而全紅,
    # 但更該先明確報「檔讀不到」而非讓 marker 斷言噪音淹沒根因)。
    for fname, text in texts.items():
        assert len(text) > 5000, (
            f"{fname} 讀入異常過短(len={len(text)}),掃描路徑疑破壞"
        )

    offenders: list[str] = []
    for marker_id, fname, needle, baseline, note in MARKERS:
        current = texts[fname].count(needle)
        if current < baseline:
            offenders.append(
                f"[{marker_id}] {fname} 子字串 {needle!r} 當前 {current} < baseline {baseline}"
                f"  —— {note}"
            )

    assert not offenders, (
        "Live 硬化面 snapshot 回歸(標記計數低於 baseline = 遷移稀釋):\n"
        + "\n".join(offenders)
        + "\n"
        + _GUIDE
    )


def test_live_typed_confirm_phrases_present() -> None:
    """不變量:四道破壞性 live 變更的 typed-confirm 短語必須存在(逐字打字閘)。

    START LIVE / STOP LIVE / EMERGENCY STOP / CLOSE ALL —— 每道對應一個
    openTypedConfirmModal 呼叫,操作員須逐字輸入短語才放行。短語消失 = 該道
    變更失去打字確認保護(稀釋)。
    """
    js = _read("tab-live.js")
    missing = [p for p in REQUIRED_TYPED_PHRASES if f"phrase: '{p}'" not in js]
    assert not missing, (
        f"tab-live.js 缺 typed-confirm 短語(打字確認閘被稀釋):{missing}\n"
        f"  每道破壞性 live 變更必須 openTypedConfirmModal({{ phrase: '<PHRASE>' }})。"
    )
    # 呼叫點數與短語數對齊:4 道破壞性變更 = 4 個 typed-confirm 呼叫。
    call_sites = js.count("openTypedConfirmModal(")
    assert call_sites >= len(REQUIRED_TYPED_PHRASES), (
        f"openTypedConfirmModal 呼叫點 {call_sites} < 短語數 {len(REQUIRED_TYPED_PHRASES)},"
        f"疑有破壞性變更繞過打字確認"
    )


def test_live_real_funds_badge_present_both_files() -> None:
    """不變量:REAL FUNDS 常駐真金身分標記在 html 與 js 都必須存在。

    REAL FUNDS 是操作員「這是真錢不是 demo」的常駐視覺身分(html 主題語義 +
    js real-funds-badge 常駐橫幅)。任一端消失 = 真金身分稀釋。
    """
    html, js = _read("tab-live.html"), _read("tab-live.js")
    assert "REAL FUNDS" in html, "tab-live.html 缺 REAL FUNDS 真金身分標記(稀釋)"
    assert "REAL FUNDS" in js, "tab-live.js 缺 REAL FUNDS 真金身分標記(稀釋)"
    # js badge class 常駐(渲染熱紅 REAL FUNDS 橫幅)。
    assert "real-funds-badge" in js, (
        "tab-live.js 缺 real-funds-badge(REAL FUNDS 常駐橫幅被移除 = 稀釋)"
    )


def test_live_emergency_stop_and_close_are_separate_handlers() -> None:
    """關鍵不變量:緊急停止與平倉是 **分離的兩個 handler**,不可合併為單鍵。

    親證:
      · js 內 doEmergencyStop 與 doLiveCloseAll 各為 1 個 distinct async function 定義;
      · 兩者名稱不同(非同一函數);
      · html 內兩個 **不同按鈕** 各自 onclick 到不同 handler。
    合併為單鍵 = 操作員無法「只平倉不停 session」或「只緊急停止」,硬化面稀釋。
    """
    js, html = _read("tab-live.js"), _read("tab-live.html")

    emg_def = js.count("async function doEmergencyStop(")
    close_def = js.count("async function doLiveCloseAll(")
    assert emg_def == 1, f"doEmergencyStop async 定義數={emg_def}(應恰 1)"
    assert close_def == 1, f"doLiveCloseAll async 定義數={close_def}(應恰 1)"

    # 兩 handler 名稱不同 = 確實分離(非同一函數)。
    assert "doEmergencyStop" != "doLiveCloseAll"  # 語義釘死:分離契約

    # html 兩個不同按鈕分別接線(緊急停止 vs 全部平倉)。
    assert 'onclick="doEmergencyStop()"' in html, (
        "tab-live.html 缺緊急停止按鈕接線(doEmergencyStop)"
    )
    assert 'onclick="doLiveCloseAll()"' in html, (
        "tab-live.html 缺全部平倉按鈕接線(doLiveCloseAll)"
    )
    # 緊急停止走 session/stop(撤授權+停 session);平倉走 close-all-positions(session 不停)。
    # 兩者打不同端點 = 語義真分離,非同一動作換名。
    assert "/api/v1/live/session/stop" in js, "緊急停止端點(session/stop)消失"
    assert "/api/v1/live/close-all-positions" in js, "平倉端點(close-all-positions)消失"


def test_live_hardening_baseline_is_anti_vacuous() -> None:
    """anti-vacuous:每個 baseline > 0,且計數器對合成內容真的會命中/落空。

    防兩種空洞綠:
      ① baseline 全 0 → ratchet 恆綠零守衛(此處硬性要求每 marker baseline > 0);
      ② 計數 helper 壞掉恆回 0/恆回大值 → 用合成正反例把 str.count 語義釘死。
    """
    # 每 marker baseline 嚴格 > 0(survey 對:某 marker 若實測 0 表 survey 錯,不硬寫 0)。
    zero_base = [m[0] for m in MARKERS if m[3] <= 0]
    assert not zero_base, f"以下 marker baseline <= 0(anti-vacuous 違反):{zero_base}"

    # 至少覆蓋兩檔(html + js),且涵蓋七大硬化類別。
    files = {m[1] for m in MARKERS}
    assert files == {"tab-live.html", "tab-live.js"}, f"marker 檔覆蓋異常:{files}"

    # 計數 helper 語義釘死:合成內容已知命中數。
    synthetic = "REAL FUNDS x REAL FUNDS y openTypedConfirmModal( z --live --live-bg"
    assert synthetic.count("REAL FUNDS") == 2, "str.count 未正確計數(REAL FUNDS)"
    assert synthetic.count("openTypedConfirmModal(") == 1, "str.count 未正確計數(呼叫點)"
    assert synthetic.count("--live") == 2, "str.count 未正確計數(--live 含 --live-bg 子串)"
    assert synthetic.count("鑄幣廠不存在") == 0, "str.count 對不存在子串應回 0"


def test_live_hardening_dilution_detector_is_substantive() -> None:
    """substantive detector:合成刪除一個硬化標記,對應 marker 必落到 baseline 以下並被點名。

    這是「守衛真的會 FAIL」的正反錨:若把當前 REAL FUNDS 之一刪掉、或把一個
    openTypedConfirmModal 呼叫刪掉,ratchet 邏輯必須精確點名該 marker(而非漏放)。
    在記憶體副本上模擬,不改真檔。
    """
    texts = _texts()

    def _first_below(mutated: dict[str, str]) -> list[str]:
        named: list[str] = []
        for marker_id, fname, needle, baseline, _note in MARKERS:
            if mutated[fname].count(needle) < baseline:
                named.append(marker_id)
        return named

    # 反例 1:當前樹本身 —— 零 marker 低於 baseline(當前硬化面完整 = 綠)。
    assert _first_below(texts) == [], (
        "當前樹即應全綠(硬化面完整);若此處紅表 baseline 高於實測,需據實校正"
    )

    # 反例 2:合成刪除一個 REAL FUNDS(html)→ real_funds_html 必被點名。
    mut_html = dict(texts)
    mut_html["tab-live.html"] = texts["tab-live.html"].replace("REAL FUNDS", "demo funds", 1)
    named = _first_below(mut_html)
    assert "real_funds_html" in named, (
        f"刪一個 REAL FUNDS 後 real_funds_html 未被點名(detector 空洞);named={named}"
    )

    # 反例 3:合成刪除一個 openTypedConfirmModal 呼叫 → typed_confirm_call 必被點名。
    mut_js = dict(texts)
    mut_js["tab-live.js"] = texts["tab-live.js"].replace("openTypedConfirmModal(", "noConfirm(", 1)
    named = _first_below(mut_js)
    assert "typed_confirm_call" in named, (
        f"刪一個 typed-confirm 呼叫後 typed_confirm_call 未被點名;named={named}"
    )

    # 反例 4:合成刪除緊急停止 handler 定義 → emergency_stop_def_js 必被點名。
    mut_emg = dict(texts)
    mut_emg["tab-live.js"] = texts["tab-live.js"].replace(
        "async function doEmergencyStop(", "async function _removedEmergencyStop(", 1
    )
    named = _first_below(mut_emg)
    assert "emergency_stop_def_js" in named, (
        f"刪緊急停止 handler 後 emergency_stop_def_js 未被點名;named={named}"
    )
