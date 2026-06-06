"""signal_postmortem 聚焦測試（純 pytest，無 PG/IPC mock）。

每個 case 用上游 vetted 報告的真實 reason token 構造 evidence dict，
驗證 deterministic cascade、嚴格優先序、降級邏輯與 JSON-safe 序列化。
"""

from __future__ import annotations

import math

from program_code.learning_engine.signal_postmortem import (
    SignalPostmortemEvidence,
    classify_signal_failure,
)


def _ev(**overrides) -> SignalPostmortemEvidence:
    params: dict = {"candidate_id": "cand_1", "family_id": "fam_1"}
    params.update(overrides)
    return SignalPostmortemEvidence(**params)


# ─────────────────────────────────────────────────────────────────────────────
# 8 種 taxonomy 各 ≥1 case
# ─────────────────────────────────────────────────────────────────────────────


def test_data_leak_pit_violation():
    """data_leak：signal_spec_validation 含 PIT 違反 token。"""
    ev = _ev(
        signal_spec_validation={
            "verdict": "invalid",
            "reasons": ("pit_contract_future_data_allowed",),
        }
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "data_leak"
    assert any("pit_violation" in ref for ref in report.evidence_refs)


def test_data_leak_leak_free_shift1_inconsistent():
    """data_leak：leak_free_shift1_consistent is False。"""
    report = classify_signal_failure(_ev(leak_free_shift1_consistent=False))
    assert report.taxonomy == "data_leak"
    assert "leak_free_shift1_inconsistent" in report.evidence_refs


def test_implementation_bug_non_finite_metric():
    """implementation_bug：residual_report.reasons 含 non_finite_metric。"""
    ev = _ev(
        residual_report={"verdict": "fail", "reasons": ("non_finite_metric",)}
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "implementation_bug"


def test_implementation_bug_hash_mismatch():
    """implementation_bug：signal_spec hash mismatch。"""
    ev = _ev(
        signal_spec_validation={
            "verdict": "invalid",
            "reasons": ("signal_spec_hash_mismatch",),
        }
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "implementation_bug"


def test_sample_insufficient_residual_defer():
    """sample_insufficient：residual verdict==defer_data。"""
    ev = _ev(residual_report={"verdict": "defer_data", "reasons": ()})
    report = classify_signal_failure(ev)
    assert report.taxonomy == "sample_insufficient"


def test_sample_insufficient_dsr_pbo_nested_flags():
    """sample_insufficient：promotion_result 巢狀 dsr/pbo 不足旗標。"""
    ev = _ev(
        promotion_result={
            "verdict": "defer_data",
            "dsr": {"insufficient_observations": True},
            "pbo": {"insufficient_power": True},
        }
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "sample_insufficient"
    assert "dsr:insufficient_observations" in report.evidence_refs
    assert "pbo:insufficient_power" in report.evidence_refs


def test_cost_defeat_edge_le_cost():
    """cost_defeat：gross edge 為正但 <= cost。"""
    ev = _ev(
        cost_result={
            "expected_edge_bps": 2.0,
            "expected_cost_bps": 3.0,
            "ratio": 0.6667,
            "threshold": 0.8,
            "passes_threshold": False,
        },
        residual_report={"verdict": "fail", "residual_mean_bps": 2.0, "reasons": ()},
        settled_sample_count=50,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "cost_defeat"
    assert any("edge<=cost" in ref for ref in report.evidence_refs)


def test_beta_edge_raw_positive_residual_non_positive():
    """beta_edge：raw 為正但殘差非正（vetted token 命中）。"""
    ev = _ev(
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": 5.0,
            "residual_mean_bps": -1.0,
            "beta_edge_share": 1.2,
            "r_beta_retention": -0.2,
            "reasons": (
                "raw_positive_residual_non_positive",
                "beta_edge_share_above_threshold",
                "r_beta_retention_below_threshold",
            ),
        },
        regime_breakdown=[{"regime": "up"}, {"regime": "down"}],
        settled_sample_count=80,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "beta_edge"
    assert "residual:beta_edge_share_above_threshold" in report.evidence_refs


def test_regime_only_single_asymmetric():
    """regime_only：單一 regime + dominant_side 不對稱。"""
    ev = _ev(
        regime_breakdown=[
            {"regime": "down", "dominant_side": "short", "side_symmetric": False},
        ],
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": 3.0,
            "residual_mean_bps": 0.5,
            "reasons": (),
        },
        settled_sample_count=60,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "regime_only"
    assert "dominant_side_asymmetric" in report.evidence_refs


def test_fill_failure_execution_negative_and_stats():
    """fill_failure：execution attribution 強負 + fill_stats 差。"""
    ev = _ev(
        attribution_scores={"alpha": 0.1, "execution": -0.8},
        fill_stats={"maker_fill_rate": 0.2, "reject_rate": 0.3, "qty_zero": 5},
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": 1.0,
            "residual_mean_bps": 0.5,
            "reasons": (),
        },
        settled_sample_count=40,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "fill_failure"
    assert "attribution_execution=-0.8000" in report.evidence_refs


def test_no_edge_fallback():
    """no_edge（兜底）：樣本足、無 leak/bug/cost/beta/fill，殘差非正。"""
    ev = _ev(
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": -0.5,
            "residual_mean_bps": -0.5,
            "psr_residual": 0.4,
            "reasons": ("raw_mean_non_positive",),
        },
        cost_result={
            "expected_edge_bps": -0.5,
            "expected_cost_bps": 2.0,
            "passes_threshold": False,
        },
        settled_sample_count=100,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "no_edge"
    assert any("residual_mean_bps" in ref for ref in report.evidence_refs)


# ─────────────────────────────────────────────────────────────────────────────
# 回歸重點：sample_insufficient 嚴格先於 no_edge
# ─────────────────────────────────────────────────────────────────────────────


def test_sample_insufficient_strictly_precedes_no_edge():
    """同時滿足 sample_insufficient 與 no_edge 條件時，必判 sample_insufficient。"""
    ev = _ev(
        # no_edge 條件：殘差非正 + psr 不顯著。
        residual_report={
            "verdict": "defer_data",  # 同時觸發 sample_insufficient
            "raw_mean_bps": -0.2,
            "residual_mean_bps": -0.2,
            "psr_residual": 0.3,
            "reasons": ("raw_mean_non_positive",),
        },
        # sample_insufficient 條件：settled < 10。
        settled_sample_count=5,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "sample_insufficient"
    # 兩者都應在 candidate_taxonomies 中（no_edge 兜底必命中），但主判定是前者。
    assert "sample_insufficient" in report.candidate_taxonomies
    assert "no_edge" in report.candidate_taxonomies
    assert report.candidate_taxonomies.index("sample_insufficient") < report.candidate_taxonomies.index("no_edge")


# ─────────────────────────────────────────────────────────────────────────────
# 多因共存：cascade 優先（leak + cost 同在 → 必 data_leak）
# ─────────────────────────────────────────────────────────────────────────────


def test_multi_factor_leak_beats_cost_and_records_full_order():
    """leak + cost + sample 同在 → 必 data_leak，candidate_taxonomies 記完整命中序。"""
    ev = _ev(
        signal_spec_validation={
            "verdict": "invalid",
            "reasons": ("pit_contract_not_point_in_time",),
        },
        cost_result={
            "expected_edge_bps": 2.0,
            "expected_cost_bps": 3.0,
            "passes_threshold": False,
        },
        residual_report={
            "verdict": "defer_data",
            "residual_mean_bps": 2.0,
            "reasons": (),
        },
        settled_sample_count=4,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "data_leak"
    # 完整命中序透明化：data_leak 在最前，cost_defeat / sample_insufficient 也應記錄。
    assert report.candidate_taxonomies[0] == "data_leak"
    assert "cost_defeat" in report.candidate_taxonomies
    assert "sample_insufficient" in report.candidate_taxonomies


def test_implementation_bug_beats_sample_insufficient():
    """bug + sample 同在 → 必 implementation_bug（更致命）。"""
    ev = _ev(
        residual_report={
            "verdict": "defer_data",
            "reasons": ("non_finite_metric",),
        },
        settled_sample_count=2,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "implementation_bug"
    assert report.candidate_taxonomies[0] == "implementation_bug"


# ─────────────────────────────────────────────────────────────────────────────
# regime_only 降級：beta-like 但 regime_breakdown=None → beta_edge + 降級
# ─────────────────────────────────────────────────────────────────────────────


def test_beta_like_without_regime_breakdown_downgrades():
    """beta-like 命中但缺 regime_breakdown → beta_edge + regime_split_unavailable + 降級。"""
    ev = _ev(
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": 5.0,
            "residual_mean_bps": -1.0,
            "beta_edge_share": 1.1,
            "r_beta_retention": -0.2,
            "reasons": (
                "raw_positive_residual_non_positive",
                "beta_edge_share_above_threshold",
            ),
        },
        regime_breakdown=None,
        cost_result={"expected_edge_bps": -1.0, "passes_threshold": False},
        settled_sample_count=80,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "beta_edge"
    assert "regime_split_unavailable" in report.evidence_refs
    # confidence 應被降一級（從 high → medium）。
    assert report.confidence in ("medium", "low")


# ─────────────────────────────────────────────────────────────────────────────
# 空 bundle 不 crash + 兜底 + confidence=low
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_bundle_falls_back_low_confidence():
    """全 None bundle 不 crash，兜底 no_edge + confidence=low。"""
    report = classify_signal_failure(_ev())
    assert report.taxonomy == "no_edge"
    assert report.confidence == "low"
    assert "no_decisive_failure_signal" in report.evidence_refs
    assert report.candidate_taxonomies == ("no_edge",)


def test_malformed_report_types_do_not_crash():
    """報告欄位型別異常（reasons 非 iterable / verdict 非 str）不 crash。"""
    ev = _ev(
        residual_report={"verdict": 123, "reasons": "not_a_list"},
        cost_result="not_a_mapping",  # type: ignore[arg-type]
        promotion_result=None,
    )
    report = classify_signal_failure(ev)
    # 不 crash 即可；無決定性訊號 → 兜底 no_edge。
    assert report.taxonomy == "no_edge"


# ─────────────────────────────────────────────────────────────────────────────
# to_dict JSON-safe（含 NaN 輸入 → None）
# ─────────────────────────────────────────────────────────────────────────────


def test_to_dict_is_json_safe_with_nan_input():
    """to_dict 對 NaN 輸入不 crash，且輸出可序列化。"""
    import json

    ev = _ev(
        cost_result={
            "expected_edge_bps": 2.0,
            "expected_cost_bps": float("nan"),  # NaN cost
            "ratio": float("nan"),
            "passes_threshold": False,
        },
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": 2.0,
            "residual_mean_bps": float("nan"),
            "reasons": (),
        },
        attribution_chain_ratio=float("nan"),
        settled_sample_count=50,
    )
    report = classify_signal_failure(ev)
    payload = report.to_dict()
    # 應可被 json.dumps 序列化（NaN 已被 _json_safe 轉 None）。
    encoded = json.dumps(payload)
    assert "NaN" not in encoded
    assert payload["schema_version"] == "signal_postmortem_v1"
    assert payload["candidate_id"] == "cand_1"
    assert isinstance(payload["evidence_refs"], list)
    assert isinstance(payload["candidate_taxonomies"], list)


# ─────────────────────────────────────────────────────────────────────────────
# attribution_chain_ok：chain_ratio=1.0 但 taxonomy=data_leak → 仍 False
# ─────────────────────────────────────────────────────────────────────────────


def test_attribution_chain_ok_false_when_data_leak():
    """chain_ratio=1.0 + settled>=10 但 taxonomy=data_leak → attribution_chain_ok False。"""
    ev = _ev(
        signal_spec_validation={
            "verdict": "invalid",
            "reasons": ("pit_contract_future_data_allowed",),
        },
        attribution_chain_ratio=1.0,
        settled_sample_count=100,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "data_leak"
    assert report.attribution_chain_ok is False


def test_attribution_chain_ok_true_for_non_fatal_with_chain():
    """非 leak/bug + chain_ratio>=1.0 + settled>=10 → attribution_chain_ok True。"""
    ev = _ev(
        residual_report={
            "verdict": "fail",
            "raw_mean_bps": -0.5,
            "residual_mean_bps": -0.5,
            "reasons": ("raw_mean_non_positive",),
        },
        cost_result={"expected_edge_bps": -0.5, "passes_threshold": False},
        attribution_chain_ratio=1.0,
        settled_sample_count=50,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "no_edge"
    assert report.attribution_chain_ok is True


def test_attribution_chain_ok_false_when_settled_below_min():
    """chain_ratio>=1.0 但 settled<10 → False（且必判 sample_insufficient）。"""
    ev = _ev(
        residual_report={
            "verdict": "fail",
            "residual_mean_bps": -0.5,
            "reasons": ("raw_mean_non_positive",),
        },
        attribution_chain_ratio=2.0,
        settled_sample_count=5,
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "sample_insufficient"
    assert report.attribution_chain_ok is False


# ─────────────────────────────────────────────────────────────────────────────
# scheduler hint 純資料、不 act
# ─────────────────────────────────────────────────────────────────────────────


def test_scheduler_hint_is_pure_data():
    """research_scheduler_hint 為純資料 dict，標 acts=False。"""
    ev = _ev(residual_report={"verdict": "defer_data", "reasons": ()}, settled_sample_count=3)
    report = classify_signal_failure(ev)
    hint = report.research_scheduler_hint
    assert hint["acts"] is False
    assert hint["suggested_action"] == "needs_more_sample"
    assert hint["taxonomy"] == "sample_insufficient"
    assert hint["defer_reason"] == "insufficient_sample_or_power"


# ─────────────────────────────────────────────────────────────────────────────
# E4 行為鎖定（回歸）：E2 列的 2 個 LOW 觀察固化當前行為，非改邏輯
# ─────────────────────────────────────────────────────────────────────────────


def test_negative_settled_sample_count_classified_sample_insufficient():
    """E2 LOW：負 settled_sample_count 應歸 sample_insufficient（< 門檻），非 no_edge。

    鎖定當前行為：負數通過 ``settled < _MIN_SETTLED_SAMPLE`` 判定，
    並使 attribution_chain_ok=False、hint 帶上原始負值（誠實透傳，不臆測）。
    """
    ev = _ev(
        settled_sample_count=-5,
        residual_report={
            "verdict": "fail",
            "residual_mean_bps": -0.5,
            "reasons": ("raw_mean_non_positive",),
        },
    )
    report = classify_signal_failure(ev)
    assert report.taxonomy == "sample_insufficient"
    assert "settled_sample_count:-5<10" in report.evidence_refs
    # 負樣本數不滿足 chain_ok（settled >= 10 必要）。
    assert report.attribution_chain_ok is False
    # hint 誠實透傳原始值，不臆測為 0。
    assert report.research_scheduler_hint["settled_sample_count"] == -5


def test_to_dict_is_canonical_json_safe_accessor():
    """E2 LOW：報告為 dataclass，序列化須走 ``to_dict()``（內部呼 _json_safe）。

    鎖定 to_dict() 回 plain dict、含全部公開欄位、且可 json 序列化；
    防止 caller 誤用 dataclasses.asdict()（會跳過 NaN→None sanitize）。
    """
    import dataclasses
    import json

    report = classify_signal_failure(_ev())
    payload = report.to_dict()
    assert isinstance(payload, dict)
    # 公開契約欄位齊全。
    expected_keys = {
        "taxonomy",
        "confidence",
        "rationale",
        "evidence_refs",
        "candidate_taxonomies",
        "attribution_chain_ok",
        "research_scheduler_hint",
        "candidate_id",
        "family_id",
        "schema_version",
    }
    assert expected_keys <= set(payload.keys())
    # to_dict() 與 asdict() 對齊鍵集合（行為等價於 dataclass 投影 + sanitize）。
    assert set(payload.keys()) == set(dataclasses.asdict(report).keys())
    # 可序列化（無 NaN/Inf 殘留）。
    json.dumps(payload)
