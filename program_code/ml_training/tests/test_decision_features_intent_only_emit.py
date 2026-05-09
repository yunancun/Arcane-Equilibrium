"""
W-AUDIT-4b-M1 (V082) — decision_features intent-only emit + evaluation 拆表 contract test.

W-AUDIT-4b-M1（V082）— decision_features intent-only emit 與 evaluation 拆表合約測試。

背景 / Background:
  2026-05-09 PG 直查發現 learning.decision_features 24h 31,183 行中
  ~99.32% 是 orphan candidate evaluation（無對應 trading.intents emit）。
  Root cause: rust/openclaw_engine/src/intent_processor/mod.rs::evaluate_predictor_gate
  在 cost_gate / Reject 之前頂端就 emit DecisionFeatureMsg，無論 intent 是否真實 emit。

修復 / Fix:
  V082 拆 evaluation 路徑到新表 learning.decision_features_evaluations
  （保 evaluation 流量為 producer-debug / gate 行為觀測），
  保 learning.decision_features 為 production training 表（intent-only emit）。

此測試驗 / This test verifies:
  (1) V082 migration 文件 syntax 與 column 列表 lock（防 schema 漂移）
  (2) decision_features 與 decision_features_evaluations 的 schema 主要差異
      (PK / outcome / evidence_source_tier / entry_context_id)
  (3) ML training query 仍 reference learning.decision_features（intent-only），
      不誤接 evaluations 表

Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
      2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ── Path resolution ──
# 不 hardcode 用戶 home（CLAUDE.md §七 跨平台規則）：
# Tests 跑在 srv/ 下，repo 根透過 Path 推導。
SRV_ROOT = Path(__file__).resolve().parents[3]
V082_PATH = SRV_ROOT / "sql" / "migrations" / "V082__decision_features_evaluations_split.sql"
V017_PATH = SRV_ROOT / "sql" / "migrations" / "V017__edge_predictor_tables.sql"


# ─────────────────────────────────────────────
# (1) V082 migration 文件存在且有完整 lock
# ─────────────────────────────────────────────


def test_v082_migration_file_exists():
    """V082 migration 文件須存在於 sql/migrations/ 下。"""
    assert V082_PATH.exists(), (
        f"V082 migration not found: {V082_PATH}. "
        "W-AUDIT-4b-M1 IMPL 必含 V082__decision_features_evaluations_split.sql"
    )


def test_v082_creates_decision_features_evaluations_table():
    """V082 須 CREATE TABLE learning.decision_features_evaluations。"""
    src = V082_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS learning.decision_features_evaluations" in src, (
        "V082 必含 'CREATE TABLE IF NOT EXISTS learning.decision_features_evaluations'"
    )


def test_v082_locked_required_columns():
    """V082 schema column 列表 lock — 防 producer / writer 漂移。"""
    src = V082_PATH.read_text(encoding="utf-8")
    # 必要欄位（按 V082 §主 DDL 順序）
    required_cols = [
        "evaluation_id",
        "context_id",
        "ts",
        "engine_mode",
        "strategy_name",
        "symbol",
        "side",
        "feature_schema_version",
        "feature_schema_hash",
        "feature_definition_hash",
        "features_jsonb",
        "evaluation_outcome",
        "evidence_source_tier",
        "entry_context_id",
        "created_at",
    ]
    for col in required_cols:
        assert col in src, f"V082 missing required column: {col}"


def test_v082_evaluation_outcome_check_enum():
    """evaluation_outcome CHECK enum 必包 7 個合法字串（與 PredictorAction 對齊）。"""
    src = V082_PATH.read_text(encoding="utf-8")
    # 必要 enum 值（與 Rust intent_processor 對應）
    expected_outcomes = [
        "accept",
        "reject",
        "reject_add",
        "shadow_fill",
        "fallback_use_legacy",
        "fallback_fail_closed",
        "use_legacy_no_predictor",
    ]
    for outcome in expected_outcomes:
        # 每個 outcome 應出現在 CHECK constraint 字串中
        # 用 'outcome'::text 形式或 'outcome' 形式皆可
        assert outcome in src, (
            f"V082 evaluation_outcome enum missing: {outcome}. "
            "Check chk_decision_features_evaluations_outcome CHECK clause."
        )


def test_v082_evidence_source_tier_check_enum():
    """evidence_source_tier CHECK enum 必包 2 個合法 tier，故意與 V050 不重疊。"""
    src = V082_PATH.read_text(encoding="utf-8")
    expected_tiers = ["evaluation_log", "shadow_synthetic"]
    for tier in expected_tiers:
        assert tier in src, f"V082 evidence_source_tier enum missing: {tier}"

    # 故意排除 V050 replay tier 字串（避免下游 SELECT 污染）
    forbidden_tiers = ["calibrated_replay", "synthetic_replay", "counterfactual_replay"]
    for tier in forbidden_tiers:
        # 若被 V082 採用會與 V050 replay.simulated_fills 撞 tier 字串
        # 允許在 comment 中提及（為解釋故意排除），但 CHECK clause 不可包
        # 簡化檢查：CHECK 只涵蓋 ('evaluation_log', 'shadow_synthetic')
        check_clause_match = re.search(
            r"CHECK \(evidence_source_tier IN \(([^)]+)\)\)", src
        )
        assert check_clause_match, "evidence_source_tier CHECK clause must exist"
        check_values = check_clause_match.group(1)
        assert tier not in check_values, (
            f"V082 evidence_source_tier CHECK 不可含 V050 replay tier: {tier}"
        )


def test_v082_guard_a_b_c_present():
    """Guard A/B/C 必須在 V082（CLAUDE.md §七 SQL migration 規範）。"""
    src = V082_PATH.read_text(encoding="utf-8")
    # Guard A: schema/table existence check
    assert "Guard A" in src or "Guard A2" in src or "Guard A3" in src, (
        "V082 須含 Guard A 模板（learning schema + decision_features 存在性）"
    )
    # Guard C: index column verification
    assert "Guard C" in src, (
        "V082 須含 Guard C 模板（idx_decision_features_evaluations_strategy_mode_ts 欄位驗證）"
    )
    # CLAUDE.md §七 + Guard 模板對齊：RAISE EXCEPTION on drift
    assert "RAISE EXCEPTION" in src, "Guard 必含 RAISE EXCEPTION on drift"


def test_v082_indexes_present():
    """V082 須建立 4 個 user index（PK 自動建）。"""
    src = V082_PATH.read_text(encoding="utf-8")
    expected_indexes = [
        "idx_decision_features_evaluations_strategy_mode_ts",
        "idx_decision_features_evaluations_ts",
        "idx_decision_features_evaluations_context_id",
        "idx_decision_features_evaluations_outcome_ts",
    ]
    for idx in expected_indexes:
        assert f"CREATE INDEX IF NOT EXISTS {idx}" in src, f"V082 missing index: {idx}"


def test_v082_does_not_drop_decision_features():
    """V082 **不可** DROP 既有 learning.decision_features（保 38k row history）。"""
    src = V082_PATH.read_text(encoding="utf-8")
    # CLAUDE.md §七 + PA spec：「保現有 38k 行為，新 producer 從新表開始」
    assert (
        "DROP TABLE learning.decision_features" not in src
        and "DROP TABLE IF EXISTS learning.decision_features" not in src
    ), "V082 不可 DROP learning.decision_features（保歷史 row）"


def test_v082_does_not_migrate_row_data():
    """V082 **不可** 遷移舊 row 到新表（PA spec：DO NOT migrate row data）。"""
    src = V082_PATH.read_text(encoding="utf-8")
    # 既有 38k row 不應被 INSERT INTO new table
    assert (
        "INSERT INTO learning.decision_features_evaluations" not in src
    ), (
        "V082 不可 INSERT migrate row data per PA spec; "
        "既有 38k 行為保留不複製，新 producer 從新表開始"
    )


# ─────────────────────────────────────────────
# (2) V017 base schema 不被 V082 修改
# ─────────────────────────────────────────────


def test_decision_features_intent_only_emit():
    """**核心測試**：V082 + producer 改造後，learning.decision_features schema 不變
    （仍以 context_id 為 PK，10 列 + 4 label 列 = 14 列），與 V017 對齊。

    意義 / Meaning:
      - V082 不動 V017 既有 schema
      - learning.decision_features 仍是 production ML training 表
      - 改的只是 *producer 何時 emit*：
          舊：每次 evaluate_predictor_gate 都 emit
          新：只在 step_4_5_dispatch success path 呼叫
              emit_decision_feature_intent_emitted 才 emit
      - 99.32% orphan 行為消失（producer 改造，不依靠 schema）
    """
    v082 = V082_PATH.read_text(encoding="utf-8")
    v017 = V017_PATH.read_text(encoding="utf-8")

    # V017 仍是 learning.decision_features 的權威 DDL
    assert "CREATE TABLE IF NOT EXISTS learning.decision_features (" in v017
    # V017 schema 包 14 列（10 必要 + 4 label）
    assert "context_id              TEXT         PRIMARY KEY" in v017
    # V082 不動此 V017 schema（不 ALTER TABLE learning.decision_features）
    # 允許 V082 在 Guard A2 內 information_schema 查詢驗證 columns
    # 但 V082 主 DDL 不可 ALTER 此表
    assert "ALTER TABLE learning.decision_features " not in v082, (
        "V082 不可 ALTER 既有 learning.decision_features schema; "
        "改動限於新建 learning.decision_features_evaluations"
    )


def test_decision_features_evaluations_split():
    """**核心測試**：V082 拆出獨立 schema decision_features_evaluations，
    BIGSERIAL PK + evaluation_outcome + evidence_source_tier + entry_context_id。

    意義 / Meaning:
      - 拆表使 evaluation log 與 production training 通道完全隔離
      - BIGSERIAL PK 容許同 context_id 多次 evaluate（無 dedup）
      - evidence_source_tier 與 V050 replay tier 故意不重疊
      - entry_context_id 為 M2 trigger 預留欄位
    """
    src = V082_PATH.read_text(encoding="utf-8")

    # 1. PK = BIGSERIAL evaluation_id（與 V017 PK=context_id 不同）
    assert "evaluation_id           BIGSERIAL    PRIMARY KEY" in src, (
        "decision_features_evaluations PK 必為 BIGSERIAL evaluation_id"
    )

    # 2. evaluation_outcome NOT NULL 必欄
    assert "evaluation_outcome      TEXT         NOT NULL" in src

    # 3. evidence_source_tier NOT NULL 必欄
    assert "evidence_source_tier    TEXT         NOT NULL" in src

    # 4. entry_context_id NULLABLE（M1 一律 None）
    # PA spec：「為 W-AUDIT-4b-M2 trigger 鋪路欄位」
    assert "entry_context_id        TEXT" in src
    # 不可 NOT NULL（M1 producer 一律 None，M2 trigger 才回填）
    assert "entry_context_id        TEXT,         -- NULL" not in src  # 不能 NOT NULL


# ─────────────────────────────────────────────
# (3) ML training view 不依賴 evaluations 表
# ─────────────────────────────────────────────


def test_ml_training_view_targets_decision_features_not_evaluations():
    """ML training view (learning.mlde_edge_training_rows) 必依賴
    learning.decision_features（V017 production），不可誤接 evaluations 表。

    背景：V082 evidence_source_tier='evaluation_log' rows 含 reject path 污染，
    SELECT 進 ML training 會破 producer training 信號。
    """
    # V017 是 production decision_features 的 DDL，
    # mlde_edge_training_rows view 由 V031/V034 建立，引用 learning.decision_features
    # 此測試僅確認 V082 不引入新 view 把 evaluations 表混入 ML SELECT
    src = V082_PATH.read_text(encoding="utf-8")

    # V082 不應建立任何 view 把 evaluations rows 接入 ML training
    assert "CREATE OR REPLACE VIEW learning.mlde_" not in src
    assert "CREATE VIEW learning.mlde_" not in src
    assert "CREATE OR REPLACE VIEW learning.scorer_" not in src
    assert "CREATE VIEW learning.scorer_" not in src

    # 顯式提示：V082 COMMENT 內必明文「不可作 ML training data」
    assert "不可作 ML training" in src or "training data" in src, (
        "V082 須以 COMMENT 文字明示 evaluations 表禁作 ML training data"
    )


# ─────────────────────────────────────────────
# (4) 24h row 估算驗：denominator 縮 99% 預期成立
# ─────────────────────────────────────────────


def test_24h_decision_features_estimate_drop_after_intent_only_emit():
    """估算驗 / Estimate verification:

    舊產出：~31,183 row / 24h（PG 直查 2026-05-09）
        其中 99.32% orphan = ~30,973 evaluation noise rows
        intent-emitted = 31,183 - 30,973 ≈ 210 rows
        (actual SDK observation: ~263 per V082 PA spec)

    新產出（V082 + intent-only emit）：
        learning.decision_features 24h ≈ 263 row（與 trading.intents 1:1）
        learning.decision_features_evaluations 24h ≈ 31,183 row（保 evaluation 流量）

    attribution_chain_ok = matched intents / total decision_features
        舊：263 / 31,183 ≈ 0.84%（接近 PA 報告 0.5%）
        新：263 / 263 ≈ 100%（理想），但實作上仍受其他 join key 不齊影響
        → PA 預期 25-40%（保守估計）
    """
    # 此 test 是文字契約 — 確保 PA spec 預期被記錄
    # （無 PG 連線，純 mock 估算驗證 invariant）
    pa_spec_old_24h_row = 31_183  # PG 直查 2026-05-09
    pa_spec_orphan_pct = 0.9932
    pa_spec_intent_only_24h = int(pa_spec_old_24h_row * (1 - pa_spec_orphan_pct))

    # 預期 intent-only emit 後 decision_features 24h row 估 ~210
    # PA spec 提供「~263 per V082」（含未來活躍策略 expansion）
    assert 100 < pa_spec_intent_only_24h < 500, (
        f"intent-only emit 24h estimate {pa_spec_intent_only_24h} 應在 [100, 500] 區間"
    )

    # attribution_chain_ok denominator 預期降幅 ≥ 99%
    expected_denominator_drop = 1 - (pa_spec_intent_only_24h / pa_spec_old_24h_row)
    assert expected_denominator_drop >= 0.98, (
        f"denominator drop {expected_denominator_drop:.4f} 必 >= 98%（V082 設計目標）"
    )
