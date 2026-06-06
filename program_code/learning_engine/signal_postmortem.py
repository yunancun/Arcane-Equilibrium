"""signal_postmortem — 失敗交易信號的純離線 failure taxonomy 分類器。

本模組只做離線分類：把一個失敗候選信號的 evidence bundle（皆為已算好的
vetted gate 報告 dict）映射到 8 種 failure taxonomy 之一。0 DB、0 IPC、
0 Bybit、0 order/lease、0 runtime state、0 caller wiring；不重算任何統計，
只消費上游 vetted 報告（residual_alpha_gate / cost_edge_advisor /
promotion_gate / dsr_gate / pbo_gate / candidate_signal_spec）的欄位。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional, Sequence

# 復用 residual_alpha_gate 的 _json_safe（NaN/Inf → None 遞迴 sanitize），
# 不複製第三份；learning_engine 內部 import，無跨棧依賴。
from .residual_alpha_gate import _json_safe


MODULE_NOTE = """\
模塊用途：把失敗交易信號的 evidence bundle 分類成 8 種 failure taxonomy（純離線、不 act）。
主要類/函數：SignalPostmortemEvidence、SignalPostmortemReport、classify_signal_failure()。
依賴：僅 Python 標準庫 + residual_alpha_gate._json_safe；不連 DB、不讀 Bybit、不碰 IPC/order/lease/runtime state。
硬邊界：root principle 7 — learning 不得改 live state。本模組 0 寫入、0 caller wiring、0 重算統計（只讀上游 vetted gate 報告）。learning_engine 不得 import control_api.trade_attribution（反向依賴禁令）；attribution_scores 以 dict 傳入。缺證據誠實降 confidence / 標 reason，絕不硬湊 taxonomy。
"""


FailureTaxonomy = Literal[
    "no_edge",
    "beta_edge",
    "cost_defeat",
    "fill_failure",
    "regime_only",
    "sample_insufficient",
    "data_leak",
    "implementation_bug",
]

Confidence = Literal["high", "medium", "low"]

SCHEMA_VERSION = "signal_postmortem_v1"


# ─────────────────────────────────────────────────────────────────────────────
# 上游 vetted 報告的 reason token（以源碼真名為準，不近似）
# ─────────────────────────────────────────────────────────────────────────────

# candidate_signal_spec.validate_signal_spec 的 PIT 違反 token。
_PIT_LEAK_TOKENS: frozenset[str] = frozenset(
    {
        "pit_contract_future_data_allowed",
        "pit_contract_not_point_in_time",
        "pit_contract_missing",
    }
)

# candidate_signal_spec 的 hidden OOS reuse 訊號（state 非 sealed = 重用風險）。
_HIDDEN_OOS_REUSE_TOKEN = "hidden_oos_policy_state_not_sealed"

# candidate_signal_spec 的 hash mismatch token（signal_spec / manifest）。
_HASH_MISMATCH_TOKENS: frozenset[str] = frozenset(
    {
        "signal_spec_hash_mismatch",
        "expected_spec_hash_mismatch",
    }
)

# residual_alpha_gate._metric_reasons 的 non-finite metric token（IMPL bug 訊號）。
_NON_FINITE_METRIC_TOKEN = "non_finite_metric"

# 樣本門檻：低於此 settled fill 數視為樣本不足（與 dsr_gate / residual eval
# min-observation 精神一致；此處用於 postmortem 兜底，避免把樣本不足當 no_edge）。
_MIN_SETTLED_SAMPLE = 10


@dataclass(frozen=True)
class SignalPostmortemEvidence:
    """失敗信號的 evidence bundle；所有報告皆為 caller 已序列化的 dict。

    各 Optional 欄位缺失時不可 crash；分類器一律以 ``.get()`` 容錯讀取，
    缺關鍵欄位則誠實降 confidence / 標 reason，不臆測。
    """

    candidate_id: str
    family_id: str
    residual_report: Optional[Mapping[str, Any]] = None
    cost_result: Optional[Mapping[str, Any]] = None
    promotion_result: Optional[Mapping[str, Any]] = None
    signal_spec_validation: Optional[Mapping[str, Any]] = None
    manifest_validation: Optional[Mapping[str, Any]] = None
    # {alpha,timing,sizing,execution,cost,luck}；attribution 以 dict 傳入，
    # 嚴禁 import control_api.trade_attribution（反向依賴禁令）。
    attribution_scores: Optional[Mapping[str, float]] = None
    regime_breakdown: Optional[Sequence[Mapping[str, Any]]] = None
    fill_stats: Optional[Mapping[str, Any]] = None
    leak_free_shift1_consistent: Optional[bool] = None
    attribution_chain_ratio: Optional[float] = None
    settled_sample_count: Optional[int] = None


@dataclass(frozen=True)
class SignalPostmortemReport:
    """failure taxonomy 分類結果（純資料，不觸發任何動作）。

    ``research_scheduler_hint`` 只描述建議，絕不寫 state、不呼叫 scheduler。
    """

    taxonomy: FailureTaxonomy
    confidence: Confidence
    rationale: str
    evidence_refs: tuple[str, ...]
    # cascade 命中順序（透明化）：依致命優先序逐條命中的 taxonomy。
    candidate_taxonomies: tuple[FailureTaxonomy, ...]
    attribution_chain_ok: bool
    research_scheduler_hint: dict[str, Any]
    candidate_id: str
    family_id: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """回傳 JSON-safe dict（NaN/Inf → None），供 audit / evidence surface 使用。"""
        return _json_safe(
            {
                "taxonomy": self.taxonomy,
                "confidence": self.confidence,
                "rationale": self.rationale,
                "evidence_refs": list(self.evidence_refs),
                "candidate_taxonomies": list(self.candidate_taxonomies),
                "attribution_chain_ok": self.attribution_chain_ok,
                "research_scheduler_hint": dict(self.research_scheduler_hint),
                "candidate_id": self.candidate_id,
                "family_id": self.family_id,
                "schema_version": self.schema_version,
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# 內部 detection 結果容器
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Detection:
    """單一 taxonomy 的命中結果（內部用）。"""

    hit: bool = False
    refs: list[str] = field(default_factory=list)
    rationale: str = ""
    # 命中時的初始 confidence；可被降級邏輯下調。
    confidence: Confidence = "high"


# ─────────────────────────────────────────────────────────────────────────────
# 報告欄位安全讀取輔助
# ─────────────────────────────────────────────────────────────────────────────


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """非 Mapping 一律回空 dict，讓下游 ``.get()`` 安全。"""
    return value if isinstance(value, Mapping) else {}


def _reasons_of(report: Optional[Mapping[str, Any]]) -> frozenset[str]:
    """讀報告的 reasons（tuple/list/任意 iterable），轉成 str 集合。

    缺欄位或型別非預期都回空集合，不 crash。
    """
    raw = _as_mapping(report).get("reasons")
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in raw)
    return frozenset()


def _verdict_of(report: Optional[Mapping[str, Any]]) -> str:
    raw = _as_mapping(report).get("verdict")
    return str(raw) if raw is not None else ""


def _float_or_none(value: Any) -> Optional[float]:
    """轉 float；非數值或 NaN/Inf 回 None（不把噪音當數值用）。"""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _bool_flag(report: Optional[Mapping[str, Any]], key: str) -> bool:
    """讀 bool flag；嚴格 ``is True`` 判定，缺欄位 / 非 True 一律 False。"""
    return _as_mapping(report).get(key) is True


def _nested_flag(
    report: Optional[Mapping[str, Any]],
    parent: str,
    key: str,
) -> bool:
    """讀巢狀 bool flag，如 promotion_result['dsr']['insufficient_observations']。"""
    return _bool_flag(_as_mapping(report).get(parent), key)


# ─────────────────────────────────────────────────────────────────────────────
# 各 taxonomy detection（語意見 PA 規格；reason token 以源碼為準）
# ─────────────────────────────────────────────────────────────────────────────


def _detect_data_leak(ev: SignalPostmortemEvidence) -> _Detection:
    """data_leak：PIT 違反 / hidden OOS reuse / leak-free shift(1) 不一致。"""
    det = _Detection()
    spec_reasons = _reasons_of(ev.signal_spec_validation)
    manifest_reasons = _reasons_of(ev.manifest_validation)

    pit_hits = sorted((spec_reasons | manifest_reasons) & _PIT_LEAK_TOKENS)
    if pit_hits:
        det.hit = True
        det.refs.extend(f"pit_violation:{token}" for token in pit_hits)

    if _HIDDEN_OOS_REUSE_TOKEN in (spec_reasons | manifest_reasons):
        det.hit = True
        det.refs.append(f"hidden_oos_reuse:{_HIDDEN_OOS_REUSE_TOKEN}")

    if ev.leak_free_shift1_consistent is False:
        det.hit = True
        det.refs.append("leak_free_shift1_inconsistent")

    if det.hit:
        det.rationale = (
            "偵測到 point-in-time / hidden-OOS / leak-free shift(1) 違反，"
            "edge 可能來自 look-ahead 洩漏，最致命，優先判定。"
        )
    return det


def _detect_implementation_bug(ev: SignalPostmortemEvidence) -> _Detection:
    """implementation_bug：non-finite metric / signal_spec 或 manifest hash mismatch。"""
    det = _Detection()
    residual_reasons = _reasons_of(ev.residual_report)
    spec_reasons = _reasons_of(ev.signal_spec_validation)
    manifest_reasons = _reasons_of(ev.manifest_validation)

    if _NON_FINITE_METRIC_TOKEN in residual_reasons:
        det.hit = True
        det.refs.append(f"residual:{_NON_FINITE_METRIC_TOKEN}")

    hash_hits = sorted((spec_reasons | manifest_reasons) & _HASH_MISMATCH_TOKENS)
    if hash_hits:
        det.hit = True
        det.refs.extend(f"hash_mismatch:{token}" for token in hash_hits)

    if det.hit:
        det.rationale = (
            "偵測到 non-finite metric 或 spec/manifest hash mismatch，"
            "屬實作/管線錯誤而非 alpha 判定，須先修 bug 再評。"
        )
    return det


def _detect_sample_insufficient(ev: SignalPostmortemEvidence) -> _Detection:
    """sample_insufficient：必須嚴格先於 no_edge（回歸重點）。

    觸發任一：residual verdict==defer_data、dsr.insufficient_observations、
    promotion verdict==defer_data、pbo.insufficient_power、settled<10。
    """
    det = _Detection()

    if _verdict_of(ev.residual_report) == "defer_data":
        det.hit = True
        det.refs.append("residual_verdict:defer_data")

    # dsr / pbo flag 可獨立傳入，亦巢狀於 promotion_result['dsr'|'pbo']。
    if _nested_flag(ev.promotion_result, "dsr", "insufficient_observations"):
        det.hit = True
        det.refs.append("dsr:insufficient_observations")

    if _verdict_of(ev.promotion_result) == "defer_data":
        det.hit = True
        det.refs.append("promotion_verdict:defer_data")

    if _nested_flag(ev.promotion_result, "pbo", "insufficient_power"):
        det.hit = True
        det.refs.append("pbo:insufficient_power")

    if (
        ev.settled_sample_count is not None
        and ev.settled_sample_count < _MIN_SETTLED_SAMPLE
    ):
        det.hit = True
        det.refs.append(f"settled_sample_count:{ev.settled_sample_count}<{_MIN_SETTLED_SAMPLE}")

    if det.hit:
        det.rationale = (
            "證據顯示樣本/檢定力不足（defer_data 或 settled < "
            f"{_MIN_SETTLED_SAMPLE}）；嚴格先於 no_edge，避免把樣本不足誤判為無 edge。"
        )
    return det


def _detect_cost_defeat(ev: SignalPostmortemEvidence) -> _Detection:
    """cost_defeat：gross edge 為正但被成本吃掉（net<=0 或 ratio 不過閾值）。"""
    det = _Detection()
    cost = _as_mapping(ev.cost_result)
    edge = _float_or_none(cost.get("expected_edge_bps"))
    cost_bps = _float_or_none(cost.get("expected_cost_bps"))

    if edge is None or edge <= 0.0:
        # gross edge 非正 → 非「被成本擊敗」（屬 no_edge / beta），不在此判。
        return det

    edge_le_cost = cost_bps is not None and edge <= cost_bps
    ratio_fails = cost.get("passes_threshold") is False
    if edge_le_cost or ratio_fails:
        det.hit = True
        if edge_le_cost:
            det.refs.append(f"edge<=cost:{edge:.4f}<={cost_bps:.4f}")
        if ratio_fails:
            ratio = _float_or_none(cost.get("ratio"))
            threshold = _float_or_none(cost.get("threshold"))
            det.refs.append(
                "cost_ratio_below_threshold:"
                f"{'nan' if ratio is None else format(ratio, '.4f')}"
                f"<{'nan' if threshold is None else format(threshold, '.4f')}"
            )

    if det.hit:
        # 交叉檢查：residual gross 為正但 net 非正，佐證成本擊敗（不重算，只引用）。
        residual_mean = _float_or_none(_as_mapping(ev.residual_report).get("residual_mean_bps"))
        if residual_mean is not None and residual_mean > 0.0 and edge_le_cost:
            det.refs.append(f"residual_positive_but_net_non_positive:{residual_mean:.4f}")
        det.rationale = (
            "gross edge 為正但 <= 成本（或 cost/edge ratio 不過閾值），"
            "edge 真實但被交易成本擊敗。"
        )
    return det


def _detect_beta_edge(ev: SignalPostmortemEvidence) -> _Detection:
    """beta_edge：edge 主要來自 BTC/market beta（殘差化後消失）。"""
    det = _Detection()
    residual = _as_mapping(ev.residual_report)
    reasons = _reasons_of(ev.residual_report)

    raw_mean = _float_or_none(residual.get("raw_mean_bps"))
    residual_mean = _float_or_none(residual.get("residual_mean_bps"))
    beta_share = _float_or_none(residual.get("beta_edge_share"))
    retention = _float_or_none(residual.get("r_beta_retention"))

    # 典型 beta trap：raw 為正但殘差非正（residual_alpha_gate token 直接命中）。
    if "raw_positive_residual_non_positive" in reasons:
        det.hit = True
        det.refs.append("residual:raw_positive_residual_non_positive")
    elif raw_mean is not None and raw_mean > 0.0 and residual_mean is not None and residual_mean <= 0.0:
        det.hit = True
        det.refs.append(f"raw_positive_residual_non_positive:{raw_mean:.4f}->{residual_mean:.4f}")

    # beta_edge_share 過高 / r_beta_retention 過低的 vetted 旗標。
    if "beta_edge_share_above_threshold" in reasons:
        det.hit = True
        det.refs.append("residual:beta_edge_share_above_threshold")
    if "r_beta_retention_below_threshold" in reasons:
        det.hit = True
        det.refs.append("residual:r_beta_retention_below_threshold")

    if det.hit:
        if beta_share is not None:
            det.refs.append(f"beta_edge_share={beta_share:.4f}")
        if retention is not None:
            det.refs.append(f"r_beta_retention={retention:.4f}")
        det.rationale = (
            "raw edge 為正但殘差化（扣 BTC/market beta）後消失，"
            "edge 實為 beta 偽裝，非獨立 alpha。"
        )
    return det


def _detect_regime_only(ev: SignalPostmortemEvidence) -> _Detection:
    """regime_only：單一 regime（如 down-market）+ dominant_side 不對稱。

    硬約束：regime_breakdown 為 None 時不可判 regime_only（由 cascade 降級為
    beta_edge）；此函數只在有 regime_breakdown 時嘗試命中。
    """
    det = _Detection()
    breakdown = ev.regime_breakdown
    if not breakdown:
        # 缺 regime_breakdown：不命中（cascade 會處理 beta-like 降級）。
        return det

    active_regimes = [_as_mapping(row) for row in breakdown]
    # 「單一 regime 主導」：只有一個 regime bucket，或某 bucket 標記 dominant。
    single_regime = len(active_regimes) == 1
    dominant_rows = [
        row
        for row in active_regimes
        if row.get("dominant") is True or _bool_flag(row, "is_dominant")
    ]
    asymmetric = any(
        bool(row.get("dominant_side"))
        and row.get("side_symmetric") is False
        for row in active_regimes
    )

    if (single_regime or dominant_rows) and asymmetric:
        det.hit = True
        label = (
            active_regimes[0].get("regime")
            if single_regime
            else (dominant_rows[0].get("regime") if dominant_rows else None)
        )
        det.refs.append(f"regime_breakdown_buckets={len(active_regimes)}")
        if label is not None:
            det.refs.append(f"dominant_regime={label}")
        det.refs.append("dominant_side_asymmetric")
        det.rationale = (
            "edge 集中於單一 regime 且 dominant_side 不對稱（如 down-market 偏空），"
            "屬 regime-bet 非穩健 alpha。"
        )
    return det


def _detect_fill_failure(ev: SignalPostmortemEvidence) -> _Detection:
    """fill_failure：execution attribution 強負 或 fill_stats 顯示成交品質差。"""
    det = _Detection()

    execution = _float_or_none(_as_mapping(ev.attribution_scores).get("execution"))
    if execution is not None and execution < 0.0:
        det.hit = True
        det.refs.append(f"attribution_execution={execution:.4f}")

    fill = _as_mapping(ev.fill_stats)
    maker_rate = _float_or_none(fill.get("maker_fill_rate"))
    reject_rate = _float_or_none(fill.get("reject_rate"))
    qty_zero = fill.get("qty_zero")

    if maker_rate is not None and maker_rate < 0.5:
        det.hit = True
        det.refs.append(f"maker_fill_rate={maker_rate:.4f}")
    if reject_rate is not None and reject_rate > 0.1:
        det.hit = True
        det.refs.append(f"reject_rate={reject_rate:.4f}")
    if qty_zero is True or (isinstance(qty_zero, (int, float)) and not isinstance(qty_zero, bool) and qty_zero > 0):
        det.hit = True
        det.refs.append(f"qty_zero={qty_zero}")

    if det.hit:
        det.rationale = (
            "成交層失敗（execution attribution 強負 / maker fill 率低 / "
            "reject 率高 / qty_zero），edge 損失在執行而非信號本身。"
        )
    return det


def _detect_no_edge(ev: SignalPostmortemEvidence) -> _Detection:
    """no_edge（兜底）：樣本足、無 leak、非 beta、非 cost、非 fill 後的殘餘。

    語意上由 cascade 兜底；此處給出 residual_mean<=0 或 psr_residual 不顯著的
    佐證 ref（若有），否則純兜底。
    """
    det = _Detection(hit=True)
    residual = _as_mapping(ev.residual_report)
    residual_mean = _float_or_none(residual.get("residual_mean_bps"))
    psr_residual = _float_or_none(residual.get("psr_residual"))

    if residual_mean is not None and residual_mean <= 0.0:
        det.refs.append(f"residual_mean_bps={residual_mean:.4f}<=0")
    if "raw_mean_non_positive" in _reasons_of(ev.residual_report):
        det.refs.append("residual:raw_mean_non_positive")
    if psr_residual is not None and psr_residual < 0.95:
        det.refs.append(f"psr_residual={psr_residual:.4f}<0.95")

    if not det.refs:
        det.refs.append("no_decisive_failure_signal")
        det.confidence = "low"
    det.rationale = (
        "排除 leak / bug / 樣本不足 / 成本 / beta / fill 後，"
        "殘差 edge 不顯著為正，判定為無 edge。"
    )
    return det


# detection 函數依「先判最致命」的 cascade 順序排列。
_CASCADE: tuple[tuple[FailureTaxonomy, Any], ...] = (
    ("data_leak", _detect_data_leak),
    ("implementation_bug", _detect_implementation_bug),
    ("sample_insufficient", _detect_sample_insufficient),
    ("cost_defeat", _detect_cost_defeat),
    ("beta_edge", _detect_beta_edge),
    ("regime_only", _detect_regime_only),
    ("fill_failure", _detect_fill_failure),
    ("no_edge", _detect_no_edge),
)


# ─────────────────────────────────────────────────────────────────────────────
# confidence / attribution_chain / scheduler hint
# ─────────────────────────────────────────────────────────────────────────────


_CONFIDENCE_ORDER: tuple[Confidence, ...] = ("low", "medium", "high")


def _downgrade(confidence: Confidence, steps: int = 1) -> Confidence:
    """把 confidence 下調 steps 級（不低於 low）。"""
    idx = _CONFIDENCE_ORDER.index(confidence)
    return _CONFIDENCE_ORDER[max(0, idx - steps)]


def _bundle_completeness(ev: SignalPostmortemEvidence) -> int:
    """統計 bundle 中非 None 的關鍵證據塊數（用於 confidence 評估）。"""
    blocks = (
        ev.residual_report,
        ev.cost_result,
        ev.promotion_result,
        ev.signal_spec_validation,
        ev.attribution_scores,
        ev.regime_breakdown,
        ev.fill_stats,
    )
    return sum(1 for block in blocks if block)


def _compute_attribution_chain_ok(
    ev: SignalPostmortemEvidence,
    taxonomy: FailureTaxonomy,
) -> bool:
    """attribution_chain_ok：只輸出不 act。

    chain_ratio >= 1.0 且 settled >= 10 且 taxonomy 非 leak/bug 才為 True。
    """
    chain_ratio = ev.attribution_chain_ratio
    return (
        chain_ratio is not None
        and chain_ratio >= 1.0
        and ev.settled_sample_count is not None
        and ev.settled_sample_count >= _MIN_SETTLED_SAMPLE
        and taxonomy not in ("data_leak", "implementation_bug")
    )


def _scheduler_hint(
    ev: SignalPostmortemEvidence,
    taxonomy: FailureTaxonomy,
) -> dict[str, Any]:
    """純資料 dict 建議；絕不寫 state、不呼叫 scheduler。"""
    # taxonomy → 建議動作（純描述）。
    action_map: dict[FailureTaxonomy, str] = {
        "data_leak": "fix_leak_and_resubmit",
        "implementation_bug": "fix_pipeline_and_resubmit",
        "sample_insufficient": "needs_more_sample",
        "cost_defeat": "needs_cost_reduction",
        "beta_edge": "drop_family",
        "regime_only": "drop_family",
        "fill_failure": "needs_execution_fix",
        "no_edge": "drop_family",
    }
    hint: dict[str, Any] = {
        "candidate_id": ev.candidate_id,
        "family_id": ev.family_id,
        "taxonomy": taxonomy,
        "suggested_action": action_map[taxonomy],
        "acts": False,
    }
    if taxonomy == "sample_insufficient":
        hint["defer_reason"] = "insufficient_sample_or_power"
        hint["settled_sample_count"] = ev.settled_sample_count
    return hint


# ─────────────────────────────────────────────────────────────────────────────
# 主分類函數
# ─────────────────────────────────────────────────────────────────────────────


def classify_signal_failure(
    evidence: SignalPostmortemEvidence,
) -> SignalPostmortemReport:
    """把失敗信號 evidence bundle 分類成 8 種 failure taxonomy 之一。

    deterministic cascade（先判最致命）：
        data_leak → implementation_bug → sample_insufficient → cost_defeat
        → beta_edge → regime_only → fill_failure → no_edge(兜底)。

    為什麼純離線且不 act：root principle 7 — learning 不得改 live state。
    本函數只讀已算好的 vetted gate 報告 dict，輸出純資料報告，缺證據誠實
    降 confidence，不臆測、不重算統計、不寫任何 state。
    """
    # 1) 跑完整 cascade，收集所有命中（透明化命中順序）。
    detections: dict[FailureTaxonomy, _Detection] = {}
    candidate_hits: list[FailureTaxonomy] = []
    for name, detector in _CASCADE:
        det = detector(evidence)
        detections[name] = det
        if det.hit:
            candidate_hits.append(name)

    # 2) 取 cascade 中最先命中者為主判定（no_edge 必命中，保證兜底）。
    chosen: FailureTaxonomy = candidate_hits[0]
    chosen_det = detections[chosen]
    refs: list[str] = list(chosen_det.refs)
    rationale = chosen_det.rationale
    confidence: Confidence = chosen_det.confidence

    # 3) regime_only 降級：beta-like 命中 regime_only 但缺 regime_breakdown 時，
    #    硬約束要求降為 beta_edge + regime_split_unavailable + confidence 降一級。
    #    （_detect_regime_only 在缺 breakdown 時不命中，故此處處理「想判 regime
    #    但無資料」的情境：beta_edge 已命中且 regime_breakdown 缺失。）
    if (
        chosen == "beta_edge"
        and not evidence.regime_breakdown
        and "regime_only" not in candidate_hits
    ):
        refs.append("regime_split_unavailable")
        confidence = _downgrade(confidence, 1)
        rationale = (
            f"{rationale} 另：缺 regime_breakdown，無法區分 regime-only，"
            "保守歸 beta_edge 並降 confidence。"
        )

    # 4) confidence 再校準：
    #    - 致命且明確（data_leak/implementation_bug/sample_insufficient）+ bundle
    #      夠完整 → 維持 high。
    #    - regime_only 缺 regime_breakdown、fill_failure 缺 fill_stats → 降級 + 標記。
    confidence, extra_refs = _calibrate_confidence(evidence, chosen, confidence)
    refs.extend(extra_refs)

    attribution_chain_ok = _compute_attribution_chain_ok(evidence, chosen)
    hint = _scheduler_hint(evidence, chosen)

    return SignalPostmortemReport(
        taxonomy=chosen,
        confidence=confidence,
        rationale=rationale,
        evidence_refs=tuple(refs),
        candidate_taxonomies=tuple(candidate_hits),
        attribution_chain_ok=attribution_chain_ok,
        research_scheduler_hint=hint,
        candidate_id=evidence.candidate_id,
        family_id=evidence.family_id,
    )


def _calibrate_confidence(
    ev: SignalPostmortemEvidence,
    taxonomy: FailureTaxonomy,
    confidence: Confidence,
) -> tuple[Confidence, list[str]]:
    """依證據完整度與 taxonomy 性質校準 confidence；缺關鍵欄位降級並標記。"""
    refs: list[str] = []

    # regime_only 缺 regime_breakdown：理論上不會走到（detector 已 guard），
    # 但若 caller 強塞 taxonomy 仍保守降級。
    if taxonomy == "regime_only" and not ev.regime_breakdown:
        refs.append("downgraded_missing_regime_breakdown")
        confidence = _downgrade(confidence, 1)

    # fill_failure 但缺 fill_stats（只靠 attribution execution 推斷）→ 降級。
    if taxonomy == "fill_failure" and not ev.fill_stats:
        refs.append("downgraded_missing_fill_stats")
        confidence = _downgrade(confidence, 1)

    # 兜底 no_edge 但 bundle 幾乎為空 → 缺證據，降到 low。
    if taxonomy == "no_edge" and _bundle_completeness(ev) <= 1:
        refs.append("downgraded_sparse_bundle")
        confidence = "low"

    # 整體 bundle 過稀（<=1 塊）對任何非致命判定都降級（致命類已由 reason
    # token 明確命中，不因 bundle 稀疏而降）。
    if (
        taxonomy not in ("data_leak", "implementation_bug")
        and _bundle_completeness(ev) <= 1
        and "downgraded_sparse_bundle" not in refs
    ):
        refs.append("downgraded_sparse_bundle")
        confidence = _downgrade(confidence, 1)

    return confidence, refs
