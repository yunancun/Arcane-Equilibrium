"""Phase 1（rich-input tuner）Python 端測試。

MODULE_NOTE (中):
  模塊用途：驗證 ai_service_dispatch.py 的兩處 Phase 1 改動 ——
    1. `_parse_strategist_response` 必須 **保留** 結構化 quant_justification dict
       （今天 :554 會把所有非數值靜默 strip）；且不破壞既有 int/float 數值保留、
       不洩漏其他非數值 junk 進 param recs。
    2. `_build_strategist_prompt` flag-OFF（rich_input=None）→ prompt byte-identical；
       flag-ON → 追加 rich_input facts + 標 news untrusted + 要求 quant_justification。
  依賴：app.ai_service.AIService（re-export 自 ai_service_dispatch）。
  硬邊界：flag-OFF identity 是主 kill-switch；測試以「同參數有/無 rich_input」
    斷言 base prompt 完全相同。
"""

from __future__ import annotations

from app.ai_service import AIService


# ─────────────────────────────────────────────────────────────────────────────
# PART A — _parse_strategist_response 保留 quant_justification（命門）
# ─────────────────────────────────────────────────────────────────────────────


def _base_ranges() -> list[dict]:
    return [{"name": "cooldown_ms", "min": 1_000, "max": 1_000_000, "agent_adjustable": True}]


# ── T-P1-12：quant_justification dict 被保留（不被 :554 strip）──
def test_parse_preserves_quant_justification_dict():
    text = (
        '{"cooldown_ms": 55000, '
        '"quant_justification": {'
        '"source": "edge_estimates", "cell": "ma_crossover::BTCUSDT", '
        '"claimed_shrunk_bps": 5.0, "direction": "tighten", "rationale": "edge supports"}}'
    )
    out = AIService._parse_strategist_response(text, "ma_crossover", "BTCUSDT")
    # 數值 param 保留為 int（既有 int 保留邏輯不破）。
    assert out["cooldown_ms"] == 55000
    assert isinstance(out["cooldown_ms"], int)
    # quant_justification 結構化保留。
    assert "quant_justification" in out
    qj = out["quant_justification"]
    assert qj["source"] == "edge_estimates"
    assert qj["cell"] == "ma_crossover::BTCUSDT"
    assert qj["claimed_shrunk_bps"] == 5.0
    assert isinstance(qj["claimed_shrunk_bps"], float)
    assert qj["direction"] == "tighten"
    assert qj["rationale"] == "edge supports"


# ── quant_justification 白名單：丟棄非白名單 key（防 LLM 塞 junk）──
def test_parse_quant_justification_whitelist_only():
    text = (
        '{"cooldown_ms": 55000, '
        '"quant_justification": {'
        '"source": "edge_estimates", "cell": "x::Y", "claimed_shrunk_bps": 3, '
        '"direction": "loosen", "rationale": "ok", '
        '"INJECTED_JUNK": "drop me", "nested": {"a": 1}}}'
    )
    out = AIService._parse_strategist_response(text, "x", "Y")
    qj = out["quant_justification"]
    assert set(qj.keys()) <= {
        "source", "cell", "claimed_shrunk_bps", "direction", "rationale"
    }
    assert "INJECTED_JUNK" not in qj
    assert "nested" not in qj
    # claimed int → 收斂為 float。
    assert qj["claimed_shrunk_bps"] == 3.0
    assert isinstance(qj["claimed_shrunk_bps"], float)


# ── 既有行為不破：非-quant_justification 的非數值 junk 仍被 strip ──
def test_parse_still_strips_other_nonnumeric_junk():
    text = (
        '{"cooldown_ms": 55000, "garbage_str": "should be dropped", '
        '"garbage_obj": {"foo": "bar"}, "flag": true}'
    )
    out = AIService._parse_strategist_response(text, "s", "SYM")
    assert out["cooldown_ms"] == 55000
    # 非白名單的 dict / str / bool 全被 strip（除既有 meta 欄）。
    assert "garbage_str" not in out
    assert "garbage_obj" not in out
    assert "flag" not in out  # bool 排除


# ── int/float 保留邏輯不破：float.is_integer() → int；分數 → float ──
def test_parse_numeric_preservation_unchanged():
    text = '{"cooldown_ms": 78000.0, "weight_adx": 12.5}'
    out = AIService._parse_strategist_response(text, "s", "SYM")
    # 78000.0 → int 78000（避免 Rust u64 serde 失敗，既有 bug fix 不破）。
    assert out["cooldown_ms"] == 78000
    assert isinstance(out["cooldown_ms"], int)
    # 12.5 → 保 float。
    assert out["weight_adx"] == 12.5
    assert isinstance(out["weight_adx"], float)


# ── quant_justification 缺欄 fail-soft：只保留存在的白名單欄 ──
def test_parse_quant_justification_partial_fields():
    text = '{"cooldown_ms": 55000, "quant_justification": {"source": "edge_estimates"}}'
    out = AIService._parse_strategist_response(text, "s", "SYM")
    qj = out["quant_justification"]
    assert qj == {"source": "edge_estimates"}  # 缺欄不補（Rust gate 缺欄自拒）


# ── quant_justification 非 dict（LLM 寫成字串）→ 走既有 strip 分支，不保留 ──
def test_parse_quant_justification_non_dict_dropped():
    text = '{"cooldown_ms": 55000, "quant_justification": "not a dict"}'
    out = AIService._parse_strategist_response(text, "s", "SYM")
    assert "quant_justification" not in out


# ─────────────────────────────────────────────────────────────────────────────
# PART B — _build_strategist_prompt flag-OFF identity + flag-ON rich section
# ─────────────────────────────────────────────────────────────────────────────


def _build(rich_input=None, quant_evidence_available=False) -> str:
    return AIService._build_strategist_prompt(
        strategy="ma_crossover",
        symbol="BTCUSDT",
        win_rate=0.31,
        avg_pnl=-1.25,
        fill_count=42,
        current_params={"cooldown_ms": 100_000},
        param_ranges=_base_ranges(),
        normal_delta_pct=0.30,
        max_delta_pct=0.50,
        rich_input=rich_input,
        quant_evidence_available=quant_evidence_available,
    )


# ── flag-OFF identity：rich_input=None → prompt 與「不傳 rich_input」byte-identical ──
def test_prompt_flag_off_byte_identical_to_legacy():
    # 不傳 rich_input（用既有 8-arg 簽名 default）。
    legacy = AIService._build_strategist_prompt(
        strategy="ma_crossover",
        symbol="BTCUSDT",
        win_rate=0.31,
        avg_pnl=-1.25,
        fill_count=42,
        current_params={"cooldown_ms": 100_000},
        param_ranges=_base_ranges(),
        normal_delta_pct=0.30,
        max_delta_pct=0.50,
    )
    # 顯式傳 rich_input=None → 必須 byte-identical。
    explicit_off = _build(rich_input=None)
    assert legacy == explicit_off
    # 且不含任何 rich-input section 標記。
    assert "QUANTITATIVE EVIDENCE" not in legacy
    assert "NEWS CONTEXT" not in legacy
    assert "quant_justification" not in legacy


# ── flag-ON：rich_input=dict → base prompt 完整保留 + 追加 rich section ──
def test_prompt_flag_on_appends_rich_section():
    rich = {
        "edge_estimates": {
            "shrunk_bps": 5.0,
            "win_rate": 0.55,
            "n_trades": 120,
            "validation_passed": True,
            "is_fresh": True,
        },
        "regime": "trending",
        "news_context": [
            {"headline": "ETF approved", "severity": 0.8, "sentiment": "positive"}
        ],
    }
    prompt = _build(rich_input=rich, quant_evidence_available=True)
    # base prompt 仍完整（flag-ON 是 additive，不改 base）。
    off = _build(rich_input=None)
    assert prompt.startswith(off)
    # rich section 標記。
    assert "QUANTITATIVE EVIDENCE" in prompt
    assert "shrunk_bps=5.0" in prompt
    assert "regime (self-computed Hurst, point-in-time): trending" in prompt
    assert "quant_evidence_available: True" in prompt
    # news 標 UNTRUSTED。
    assert "NEWS CONTEXT (UNTRUSTED" in prompt
    assert "ETF approved" in prompt
    # quant_justification 要求 + news 不可作唯一理由。
    assert '"source": "edge_estimates"' in prompt
    assert "news_context may NEVER be the sole" in prompt
    assert "respond with {} (empty object)" in prompt


# ── flag-ON 無 edge cell：明示 NONE + quant_evidence_available False ──
def test_prompt_flag_on_no_edge_cell():
    rich = {"edge_estimates": None, "regime": "unknown", "news_context": []}
    prompt = _build(rich_input=rich, quant_evidence_available=False)
    assert "edge_estimates cell: NONE" in prompt
    assert "quant_evidence_available: False" in prompt
    assert "regime (self-computed Hurst, point-in-time): unknown" in prompt


# ── news 零權重（prompt 層）：有 vs 無 news，base prompt + quant 規則完全相同 ──
# 證 news 只進 UNTRUSTED 敘事段，不改 base prompt / quant_justification 要求段。
def test_prompt_news_does_not_change_base_or_quant_rules():
    edge = {
        "edge_estimates": {
            "shrunk_bps": 5.0, "win_rate": 0.55, "n_trades": 120,
            "validation_passed": True, "is_fresh": True,
        },
        "regime": "trending",
    }
    with_news = _build(
        rich_input={**edge, "news_context": [
            {"headline": "MOON", "severity": 0.9, "sentiment": "positive"}
        ]},
        quant_evidence_available=True,
    )
    without_news = _build(
        rich_input={**edge, "news_context": []},
        quant_evidence_available=True,
    )
    # 兩 prompt 只應在 NEWS CONTEXT 段不同；quant requirement 段必須完全相同。
    marker = "--- QUANT JUSTIFICATION REQUIREMENT"
    assert marker in with_news and marker in without_news
    assert with_news.split(marker, 1)[1] == without_news.split(marker, 1)[1]
    # base prompt 段（QUANTITATIVE EVIDENCE 之前）也完全相同。
    head_marker = "--- QUANTITATIVE EVIDENCE"
    assert (
        with_news.split(head_marker, 1)[0] == without_news.split(head_marker, 1)[0]
    )
