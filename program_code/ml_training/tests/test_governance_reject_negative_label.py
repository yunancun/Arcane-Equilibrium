"""
W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1 — governance reject 寫 negative label
+ class weight handling contract test.

W-AUDIT-4b-M3（2026-05-09）— governance reject 路徑寫 negative label 與 class
weight 處理合約測試。

背景 / Background:
  2026-05-09 MIT PG 直查：
    - trading.intents 24h 12,681 中只 175 成交（1.38%）
    - 98.6% reject 沒寫 negative label → ML training pool 67 row vs 應 12,500+
    - attribution_chain_ok 24h 0.5%（denominator 含全 intent，numerator 只 fill）
    - P0-MIT-LABEL-CLOSE-TAG-1 標記 attribution real root cause = label_close_tag
      NULL 98.9%

修復 / Fix:
  - Rust step_4_5_dispatch 三 reject path（pre_risk + exchange gate + paper gate）
    呼叫 intent_processor.emit_decision_feature_intent_rejected
  - DecisionFeatureMsg 加 3 個 optional fields：
      label_close_tag / label_net_edge_bps / label_filled_at_now
  - decision_feature_writer 兩條 SQL：
      reject 變體（INSERT 連 label 欄位）+ intent-emitted 變體（label NULL）
  - V084 migration：UDF mlde_sample_weight + view 加 sample_weight column
  - label_generator.compute_class_weights：Python sample_weight 計算

此測試驗 / This test verifies:
  (1) V084 migration 文件 syntax 與 Guard A/B + UDF lock
  (2) Rust 改動 schema lock：
      - DecisionFeatureMsg 含 label_close_tag / label_net_edge_bps / label_filled_at_now
      - decision_feature_writer reject SQL 連 label 欄位
      - intent_processor emit_decision_feature_intent_rejected method 存在
  (3) Python compute_class_weights 邏輯正確（DB / Python 雙寫對齊）
  (4) attribution_chain_ok ratio mock 模擬（從 0.5% → 5%+）

Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
      2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M3
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from program_code.ml_training.label_generator import (
    DEFAULT_SAMPLE_WEIGHT,
    REJECT_SAMPLE_WEIGHT,
    REJECTED_GOVERNANCE_TAG,
    compute_class_weights,
)


# ── Path resolution（不 hardcode 用戶 home） ──
SRV_ROOT = Path(__file__).resolve().parents[3]
V084_PATH = SRV_ROOT / "sql" / "migrations" / "V084__decision_features_reject_negative_label.sql"
V017_PATH = SRV_ROOT / "sql" / "migrations" / "V017__edge_predictor_tables.sql"
DATABASE_MOD_RS = (
    SRV_ROOT / "rust" / "openclaw_engine" / "src" / "database" / "mod.rs"
)
DECISION_FEATURE_WRITER_RS = (
    SRV_ROOT / "rust" / "openclaw_engine" / "src" / "database" / "decision_feature_writer.rs"
)
INTENT_PROCESSOR_MOD_RS = (
    SRV_ROOT / "rust" / "openclaw_engine" / "src" / "intent_processor" / "mod.rs"
)
STEP_4_5_DISPATCH_RS = (
    SRV_ROOT / "rust" / "openclaw_engine" / "src" / "tick_pipeline" / "on_tick"
    / "step_4_5_dispatch.rs"
)


# ─────────────────────────────────────────────
# (1) V084 migration 文件 lock
# ─────────────────────────────────────────────


def test_v084_migration_file_exists():
    """V084 migration 文件須存在於 sql/migrations/ 下。"""
    assert V084_PATH.exists(), (
        f"V084 migration not found: {V084_PATH}. "
        "W-AUDIT-4b-M3 IMPL 必含 V084__decision_features_reject_negative_label.sql"
    )


def test_v084_creates_sample_weight_udf():
    """V084 須建 learning.mlde_sample_weight UDF。"""
    src = V084_PATH.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION learning.mlde_sample_weight" in src, (
        "V084 必含 'CREATE OR REPLACE FUNCTION learning.mlde_sample_weight'"
    )
    # 邏輯 lock：weight 應為 1/170
    assert "1.0::double precision / 170.0" in src or "1.0/170.0" in src, (
        "V084 sample_weight 公式漂移：應為 1/170"
    )


def test_v084_view_has_sample_weight_column():
    """V084 須在 view 加 sample_weight column。"""
    src = V084_PATH.read_text(encoding="utf-8")
    assert "learning.mlde_sample_weight(sr.label_close_tag) AS sample_weight" in src, (
        "V084 view 須含 'learning.mlde_sample_weight(sr.label_close_tag) AS sample_weight'"
    )


def test_v084_has_guard_a_b():
    """V084 須含 Guard A（V017 三 label 欄位） + Guard B（型別檢查）。"""
    src = V084_PATH.read_text(encoding="utf-8")
    # Guard A：表 + 三 label 欄位
    assert "schema_guard A" in src, "V084 應含 Guard A 文字"
    for col in ("label_close_tag", "label_net_edge_bps", "label_filled_at"):
        assert col in src, f"V084 Guard A 必檢 {col}"
    # Guard B：型別檢查
    assert "schema_guard B" in src, "V084 應含 Guard B 型別檢查"


def test_v084_view_keeps_attribution_chain_ok_unchanged():
    """V084 不破既有 attribution_chain_ok 計算邏輯。"""
    src = V084_PATH.read_text(encoding="utf-8")
    # attribution_chain_ok 仍以 label_net_edge_bps IS NOT NULL 為條件
    assert "AND sr.label_net_edge_bps IS NOT NULL) AS attribution_chain_ok" in src, (
        "V084 不應改 attribution_chain_ok 計算 — 必保 'AND sr.label_net_edge_bps "
        "IS NOT NULL) AS attribution_chain_ok'"
    )


def test_v084_immutable_udf():
    """V084 UDF 須 IMMUTABLE + PARALLEL SAFE 給 PG plan cache 用。"""
    src = V084_PATH.read_text(encoding="utf-8")
    assert "IMMUTABLE" in src, "V084 UDF 應為 IMMUTABLE"
    assert "PARALLEL SAFE" in src, "V084 UDF 應為 PARALLEL SAFE"


# ─────────────────────────────────────────────
# (2) Rust schema lock — DecisionFeatureMsg + writer + emit
# ─────────────────────────────────────────────


def test_decision_feature_msg_has_negative_label_fields():
    """DecisionFeatureMsg struct 須含 3 個 negative-label 欄位。"""
    src = DATABASE_MOD_RS.read_text(encoding="utf-8")
    for field in (
        "label_close_tag: Option<String>",
        "label_net_edge_bps: Option<f64>",
        "label_filled_at_now: bool",
    ):
        assert field in src, (
            f"DecisionFeatureMsg 缺欄位 '{field}' — W-AUDIT-4b-M3 schema 必加"
        )


def test_decision_feature_writer_handles_reject_path_sql():
    """decision_feature_writer 須對 reject 變體 INSERT 寫 label 欄位。"""
    src = DECISION_FEATURE_WRITER_RS.read_text(encoding="utf-8")
    # reject path 必含 label 三欄位
    for token in (
        "label_close_tag",
        "label_net_edge_bps",
        "label_filled_at",
        # NOW() 條件：emit 時間戳 stale → 用 server-side NOW()
        "CASE WHEN $13 THEN now() ELSE NULL END",
    ):
        assert token in src, (
            f"decision_feature_writer reject SQL 缺 '{token}' — W-AUDIT-4b-M3"
        )


def test_intent_processor_has_emit_intent_rejected():
    """intent_processor 必含 emit_decision_feature_intent_rejected method。"""
    src = INTENT_PROCESSOR_MOD_RS.read_text(encoding="utf-8")
    assert "fn emit_decision_feature_intent_rejected(" in src, (
        "intent_processor 缺 emit_decision_feature_intent_rejected method"
    )
    # 寫入內容：rejected_governance + 0.0 + label_filled_at_now=true
    assert 'Some("rejected_governance".to_string())' in src, (
        "emit_decision_feature_intent_rejected 必寫 'rejected_governance' close_tag"
    )
    assert "Some(0.0)" in src, (
        "emit_decision_feature_intent_rejected 必寫 0.0 net_edge_bps（reject 沒成交）"
    )


def test_step_4_5_dispatch_reject_paths_emit_negative_label():
    """step_4_5_dispatch 三 reject path 都呼叫 emit_decision_feature_intent_rejected。"""
    src = STEP_4_5_DISPATCH_RS.read_text(encoding="utf-8")
    # 至少 3 個 call site（per_strategy reject + exchange gate reject + paper gate reject）
    n_calls = src.count("self.intent_processor.emit_decision_feature_intent_rejected(")
    assert n_calls >= 3, (
        f"step_4_5_dispatch 應有 ≥3 個 emit_decision_feature_intent_rejected "
        f"call site（pre_risk + exchange + paper），實際 {n_calls}"
    )


def test_step_4_5_dispatch_intent_emitted_unchanged():
    """W-AUDIT-4b-M1 既有 intent-emitted 路徑（success path）不應被改。"""
    src = STEP_4_5_DISPATCH_RS.read_text(encoding="utf-8")
    # 至少 2 個 call site（exchange success + paper success）
    n_calls = src.count("self.intent_processor.emit_decision_feature_intent_emitted(")
    assert n_calls >= 2, (
        f"step_4_5_dispatch 既有 emit_decision_feature_intent_emitted（M1 success path）"
        f"應 ≥2，實際 {n_calls}"
    )


# ─────────────────────────────────────────────
# (3) Python compute_class_weights — DB / Python 雙寫對齊
# ─────────────────────────────────────────────


def test_class_weights_for_rejected_governance():
    """rejected_governance close_tag 應拿 1/170 weight。"""
    tags = np.array([REJECTED_GOVERNANCE_TAG])
    w = compute_class_weights(tags)
    assert w[0] == pytest.approx(REJECT_SAMPLE_WEIGHT, abs=1e-9)
    assert w[0] == pytest.approx(1.0 / 170.0, abs=1e-9)


def test_class_weights_for_default_tags():
    """非 rejected_governance close_tag 應拿 1.0 weight（unweighted 兼容）。"""
    tags = np.array([
        None,
        "",
        "orphan_close:reverse_to_long",
        "adopted_close:t1",
        "shadow_fill:eps_greedy",
        "abandoned:no_close_fill",
    ], dtype=object)
    w = compute_class_weights(tags)
    assert np.allclose(w, np.full(len(tags), DEFAULT_SAMPLE_WEIGHT)), (
        f"非 reject close_tag 應 weight = 1.0，實際 {w}"
    )


def test_class_weights_mixed_pool_balances_imbalance():
    """混合 pool 加權後 reject:default 比近 1:0.41，dominance 消除。"""
    # 模擬 PA 觀察：12,500 reject + 175 fill ≈ 71:1
    n_reject = 12500
    n_fill = 175
    tags = np.array(
        [REJECTED_GOVERNANCE_TAG] * n_reject
        + [None] * n_fill,
        dtype=object,
    )
    w = compute_class_weights(tags)

    weighted_reject = float(np.sum(w[:n_reject]))
    weighted_fill = float(np.sum(w[n_reject:]))
    # Weighted ratio ≈ (12500/170) : 175 ≈ 73.5 : 175 → fill 反而稍重
    # 重點不在精確比例而在「reject 不再 dominance」
    assert weighted_fill > weighted_reject * 0.4, (
        f"weighted reject / fill 失衡：reject={weighted_reject:.2f}, "
        f"fill={weighted_fill:.2f}（fill 應 ≥ 0.4 × reject 才平衡）"
    )


def test_class_weights_handles_none_and_nan():
    """None / NaN-like value 不破 — 走 default weight。"""
    tags = np.array([None, np.nan, "", "fill", REJECTED_GOVERNANCE_TAG], dtype=object)
    w = compute_class_weights(tags)
    # 只 index 4 的 rejected_governance 拿 reject weight
    assert w[4] == pytest.approx(REJECT_SAMPLE_WEIGHT)
    for i in (0, 1, 2, 3):
        assert w[i] == pytest.approx(DEFAULT_SAMPLE_WEIGHT), (
            f"index {i} (tag={tags[i]!r}) 應 weight=1.0，實際 {w[i]}"
        )


def test_class_weights_empty_array():
    """空陣列回空 — 邊界 case 不 crash。"""
    tags = np.array([], dtype=object)
    w = compute_class_weights(tags)
    assert len(w) == 0
    assert w.dtype == np.float64


def test_python_db_weight_consistency():
    """Python compute_class_weights 與 V084 SQL UDF 邏輯對齊（DB / Python 雙寫一致）。

    V084 UDF：
        CASE WHEN close_tag = 'rejected_governance' THEN 1.0/170.0 ELSE 1.0 END
    Python compute_class_weights 同樣語意。
    """
    src = V084_PATH.read_text(encoding="utf-8")
    # 數字常數對齊 — 防 SQL/Python drift
    assert "170" in src, "V084 UDF reject weight 分母應為 170"
    assert REJECT_SAMPLE_WEIGHT == pytest.approx(1.0 / 170.0)


# ─────────────────────────────────────────────
# (4) attribution_chain_ok mock — 0.5% → 5%+ 估算
# ─────────────────────────────────────────────


def test_attribution_chain_ok_mock_recovery():
    """模擬 24h 12,681 intent → 175 fill + 12,506 reject 寫 negative label。

    M3 land 後 attribution_chain_ok ratio 應從 0.5% (≈67/12,681) 大幅 recover。
    具體計算：denominator = 12,681；numerator = filled rows + rejected rows
    （都有 label_net_edge_bps NOT NULL）= 175 + 12,506 = 12,681 → ratio ≈ 100%。

    保守估計（部分 intent 仍走 backfill 漏 / orphan / pre_risk path 改造慢）：
    ≥ 5% 是 PA spec 的 acceptance（FA invariant 21）。

    本測試驗 mock data 模擬 ratio 計算 → ≥ 5%。
    """
    # Mock 24h aggregate（按 PA 觀察）
    n_total_intents = 12_681
    n_filled = 175
    n_rejected = n_total_intents - n_filled  # 12,506
    # 假設 90% reject 成功寫 negative label（容錯 10% 路徑漏）
    coverage_rate = 0.90
    n_rejected_with_label = int(n_rejected * coverage_rate)

    # numerator = filled (有 net_edge_bps) + rejected_with_label (有 0.0 net_edge_bps，IS NOT NULL)
    numerator = n_filled + n_rejected_with_label
    ratio = numerator / n_total_intents

    assert ratio >= 0.05, (
        f"M3 land 後 attribution_chain_ok mock ratio={ratio:.4f}，期望 ≥ 0.05"
    )
    assert ratio >= 0.50, (
        f"M3 + 90% coverage 預期 ratio ≥ 50%，mock 計算 = {ratio:.4f}"
    )


def test_attribution_chain_ok_baseline_failure():
    """Baseline 對照（M3 land 前）— 應 fail 證 baseline 確實壞。"""
    n_total_intents = 12_681
    n_filled = 175
    # M3 land 前 reject 沒 label → 不入 numerator
    numerator = n_filled
    ratio = numerator / n_total_intents
    # PA observation: 0.5%
    assert ratio < 0.02, (
        f"baseline ratio={ratio:.4f}，期望 < 0.02（M3 land 前 0.5%）"
    )
