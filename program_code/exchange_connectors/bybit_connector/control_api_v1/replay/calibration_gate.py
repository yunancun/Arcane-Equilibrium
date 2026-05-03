"""REF-20 P3a-Q6 Calibration Freshness + Sample-Power Gate.

REF-20 P3a-Q6 校準鮮度 + 樣本功效守門。

MODULE_NOTE (EN):
    Composite handoff gate that enforces V3 §8.1 calibration maturity
    invariants at the GET ``/api/v1/replay/handoff/verdict`` (or
    ``replay_routes.py::generate_handoff_verdict``) call site:

      1. Freshness ≤ 72h: model age must be <= 72 hours since last
         calibration timestamp (V3 §11 P3a Exit + §12 acceptance #15).
      2. Sample power ≥ 200 fills/(strategy, window): below this
         threshold, calibration confidence is too low to drive a
         handoff (V3 §11 P3a Exit + §12 acceptance #16). Cell-level
         n>=30 is enforced in P3b (regime_controller) — Q6 is the
         strategy-window global gate.

    A manifest can FAIL on freshness, power, or both. The composite
    verdict surfaces the failing dimension(s) so operator GUI can show
    a precise rejection reason instead of a generic ``defer_data``.

    Wave 5 P3a-Q6 scope (this commit):
      - ``CalibrationGate`` class with three pure methods:
          * ``check_freshness(calibration_ts)`` → ``FreshnessCheck``
          * ``check_sample_power(n)`` → ``PowerCheck``
          * ``gate_handoff(manifest)`` → ``HandoffVerdict``
      - 5 dataclass result types with bilingual reason fields.
      - 4 unit tests covering pass / stale / underpowered / both fail.

    NOT in this scope:
      - replay_routes.py call-site wiring (separate sub-task; this
        module is import-ready but not yet hooked into handoff route).
      - Cell-level n>=30 gate (P3b sibling RGM-Q3 / Q4 work).
      - DSR(K) > 0.95 / PBO < 0.5 / cost_edge_ratio gates (P4 sibling
        Q1 / Q2 / Q6 in workplan §4 Wave 6).
      - V045/V046 DB INSERT for handoff verdict audit (P6 sibling
        S15 governance_audit_log row).

MODULE_NOTE (中):
    複合 handoff gate，在 GET ``/api/v1/replay/handoff/verdict``
    （即 ``generate_handoff_verdict``）call site 強制 V3 §8.1 校準成熟度
    不變量：

      1. 鮮度 ≤ 72h：模型年齡距上次校準必 <= 72 小時。
      2. 樣本功效 ≥ 200 fills/(strategy, window)：低於此值校準信心不足，
         不可推動 handoff。

    一個 manifest 可以在鮮度、功效或兩者都失敗。複合 verdict 顯露失敗
    維度，讓 operator GUI 顯示精確拒絕理由而非通用 ``defer_data``。

    Wave 5 P3a-Q6 範圍：
      - ``CalibrationGate`` class（三純函式方法）
      - 5 dataclass 結果型別含雙語 reason
      - 4 unit test：pass / stale / underpowered / both fail

    不在範圍：
      - replay_routes.py call-site wiring（後續任務）
      - Cell-level n>=30（P3b RGM-Q3/Q4）
      - DSR(K) / PBO / cost_edge_ratio（P4 Q1/Q2/Q6）
      - V045/V046 audit row（P6 S15）

SPEC:
  - REF-20 V3 §8.1 (Sample, Freshness, Embargo)
  - REF-20 V3 §11 P3a Exit (stale <=72h, n>=200/strategy-window)
  - REF-20 V3 §12 acceptance #15 (execution_calibration_freshness)
  - REF-20 V3 §12 acceptance #16 (execution_calibration_power)
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P3a-Q6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Mapping, Optional


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.1 / §11 thresholds / V3 §8.1 / §11 閾值常數
# ─────────────────────────────────────────────────────────────────────────────

# V3 §8.1 / §11 P3a Exit: model age must be <= 72h.
# V3 §8.1 / §11 P3a Exit：模型年齡 <= 72h。
FRESHNESS_MAX_HOURS: float = 72.0

# V3 §8.1 / §11 P3a Exit: n >= 200 per strategy-window for global calibration.
# V3 §8.1 / §11 P3a Exit：每個 strategy-window 至少 200 fill。
SAMPLE_POWER_MIN_N: int = 200


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


# Verdict literal — 4 mutually exclusive composite states.
# Verdict literal — 4 個互斥複合狀態。
HandoffVerdictLiteral = Literal[
    "handoff_ok",
    "stale_calibration",
    "insufficient_power",
    "both_fail",
]

# Per-dimension status literal.
# 單維度狀態 literal。
FreshnessStatus = Literal["ok", "stale"]
PowerStatus = Literal["ok", "insufficient"]


@dataclass(frozen=True)
class FreshnessCheck:
    """Result of the ≤72h freshness check.

    ≤72h 鮮度檢查結果。
    """

    status: FreshnessStatus
    age_hours: float
    threshold_hours: float
    calibration_ts: datetime
    reason_zh: str
    reason_en: str


@dataclass(frozen=True)
class PowerCheck:
    """Result of the n≥200 sample-power check.

    n≥200 樣本功效檢查結果。
    """

    status: PowerStatus
    n: int
    threshold_n: int
    deficit: int  # 0 if status=ok else (threshold_n - n)
    reason_zh: str
    reason_en: str


@dataclass(frozen=True)
class HandoffVerdict:
    """Composite verdict from CalibrationGate.gate_handoff().

    CalibrationGate.gate_handoff() 的複合 verdict。
    """

    verdict: HandoffVerdictLiteral
    freshness_check: FreshnessCheck
    power_check: PowerCheck
    reason_zh: str
    reason_en: str

    # Snapshot of the input manifest fields used for transparency.
    # 透明性：輸入 manifest 用到的欄位快照。
    manifest_snapshot: Mapping[str, object] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# CalibrationGate / 校準 gate
# ─────────────────────────────────────────────────────────────────────────────


class CalibrationGate:
    """Composite freshness + sample-power gate.

    複合鮮度 + 樣本功效 gate。

    Constructor params allow operator override of V3 §8.1 thresholds
    for hermetic test purposes; production callers MUST use defaults.
    （constructor 參數允許 hermetic test 覆寫；production caller 必用預設。）
    """

    def __init__(
        self,
        *,
        freshness_max_hours: float = FRESHNESS_MAX_HOURS,
        sample_power_min_n: int = SAMPLE_POWER_MIN_N,
    ) -> None:
        """Initialise gate with threshold overrides.

        以閾值覆寫初始化 gate。
        """
        if freshness_max_hours <= 0:
            raise ValueError(
                f"freshness_max_hours must be positive; got {freshness_max_hours}"
            )
        if sample_power_min_n <= 0:
            raise ValueError(
                f"sample_power_min_n must be positive; got {sample_power_min_n}"
            )
        self._freshness_max_hours = freshness_max_hours
        self._sample_power_min_n = sample_power_min_n

    def check_freshness(
        self,
        calibration_ts: datetime,
        *,
        now: Optional[datetime] = None,
    ) -> FreshnessCheck:
        """Return ``FreshnessCheck`` based on age vs threshold.

        依年齡對閾值回 ``FreshnessCheck``。

        Args:
            calibration_ts: Timestamp of last calibration; MUST be
                timezone-aware (UTC recommended).
            now: Override current time (test seam). Default = UTC now.

        Returns:
            ``FreshnessCheck`` with status='ok' if age <= threshold else 'stale'.

        Raises:
            ValueError: if ``calibration_ts`` is naive (no tzinfo).
        """
        if calibration_ts.tzinfo is None:
            raise ValueError(
                "calibration_ts must be timezone-aware (V3 §8.1 audit invariant); "
                "naive datetime would silently misalign across DST / regions"
            )

        ref_now = now if now is not None else datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            raise ValueError("now override must be timezone-aware")

        age_delta: timedelta = ref_now - calibration_ts
        age_hours = age_delta.total_seconds() / 3600.0

        if age_hours <= self._freshness_max_hours:
            status: FreshnessStatus = "ok"
            reason_zh = ""
            reason_en = ""
        else:
            status = "stale"
            reason_zh = (
                f"校準鮮度過期：年齡 {age_hours:.1f}h > "
                f"V3 §8.1 上限 {self._freshness_max_hours:.0f}h"
            )
            reason_en = (
                f"calibration stale: age {age_hours:.1f}h > "
                f"V3 §8.1 max {self._freshness_max_hours:.0f}h"
            )

        return FreshnessCheck(
            status=status,
            age_hours=age_hours,
            threshold_hours=self._freshness_max_hours,
            calibration_ts=calibration_ts,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    def check_sample_power(self, n: int) -> PowerCheck:
        """Return ``PowerCheck`` based on n vs threshold.

        依 n 對閾值回 ``PowerCheck``。

        Args:
            n: Sample size for the strategy-window. Must be non-negative
                integer.

        Returns:
            ``PowerCheck`` with status='ok' if n >= threshold else
            'insufficient' + deficit.

        Raises:
            ValueError: if n is negative or not an integer.
        """
        if not isinstance(n, int):
            raise ValueError(
                f"n must be int (V3 §8.1 fill count); got {type(n).__name__}"
            )
        if n < 0:
            raise ValueError(
                f"n must be non-negative (V3 §8.1 fill count); got {n}"
            )

        if n >= self._sample_power_min_n:
            status: PowerStatus = "ok"
            deficit = 0
            reason_zh = ""
            reason_en = ""
        else:
            status = "insufficient"
            deficit = self._sample_power_min_n - n
            reason_zh = (
                f"樣本功效不足：n={n} < V3 §8.1 下限 "
                f"{self._sample_power_min_n}（缺 {deficit}）"
            )
            reason_en = (
                f"insufficient sample power: n={n} < V3 §8.1 minimum "
                f"{self._sample_power_min_n} (deficit {deficit})"
            )

        return PowerCheck(
            status=status,
            n=n,
            threshold_n=self._sample_power_min_n,
            deficit=deficit,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    def gate_handoff(
        self,
        manifest: Mapping[str, object],
        *,
        now: Optional[datetime] = None,
    ) -> HandoffVerdict:
        """Composite gate: returns HandoffVerdict.

        複合 gate：回 HandoffVerdict。

        Args:
            manifest: Mapping containing at minimum:
                - ``calibration_ts``: timezone-aware datetime
                - ``n_fills`` (or ``sample_n``): int sample size
            now: Override current time (test seam).

        Returns:
            ``HandoffVerdict`` with verdict in {handoff_ok,
            stale_calibration, insufficient_power, both_fail}.

        Raises:
            KeyError: if required manifest fields are absent.
            ValueError: as per :meth:`check_freshness` / :meth:`check_sample_power`.
        """
        # Extract manifest fields with explicit error on absence (V3 §6
        # canonical manifest contract — these MUST be present at handoff
        # time).
        # 從 manifest 取欄位；缺則明確 raise（V3 §6 canonical manifest 契約）。
        if "calibration_ts" not in manifest:
            raise KeyError(
                "manifest missing required field 'calibration_ts' "
                "(V3 §6 canonical manifest contract)"
            )

        calibration_ts_raw = manifest["calibration_ts"]
        if not isinstance(calibration_ts_raw, datetime):
            raise ValueError(
                f"manifest['calibration_ts'] must be datetime; "
                f"got {type(calibration_ts_raw).__name__}"
            )

        # Allow either ``n_fills`` or ``sample_n`` for backward compat.
        # 為向前相容，接受 ``n_fills`` 或 ``sample_n``。
        n_raw = manifest.get("n_fills", manifest.get("sample_n"))
        if n_raw is None:
            raise KeyError(
                "manifest missing required field 'n_fills' (or 'sample_n') "
                "(V3 §6 canonical manifest contract)"
            )
        if not isinstance(n_raw, int):
            raise ValueError(
                f"manifest['n_fills'] must be int; got {type(n_raw).__name__}"
            )

        # Run both checks unconditionally so the verdict carries both
        # reasons even when one passes.
        # 兩 check 都跑，verdict 帶兩 reason，便於 GUI 顯示精確失敗維度。
        freshness = self.check_freshness(calibration_ts_raw, now=now)
        power = self.check_sample_power(n_raw)

        # Compose verdict / 組合 verdict。
        if freshness.status == "ok" and power.status == "ok":
            verdict: HandoffVerdictLiteral = "handoff_ok"
            reason_zh = "校準鮮度與樣本功效均符合 V3 §8.1 不變量"
            reason_en = "freshness and sample power both satisfy V3 §8.1 invariants"
        elif freshness.status == "stale" and power.status == "ok":
            verdict = "stale_calibration"
            reason_zh = freshness.reason_zh
            reason_en = freshness.reason_en
        elif freshness.status == "ok" and power.status == "insufficient":
            verdict = "insufficient_power"
            reason_zh = power.reason_zh
            reason_en = power.reason_en
        else:
            # Both fail — surface composite reason.
            # 兩者皆失敗 — 組合 reason。
            verdict = "both_fail"
            reason_zh = f"{freshness.reason_zh}；{power.reason_zh}"
            reason_en = f"{freshness.reason_en}; {power.reason_en}"

        return HandoffVerdict(
            verdict=verdict,
            freshness_check=freshness,
            power_check=power,
            reason_zh=reason_zh,
            reason_en=reason_en,
            manifest_snapshot={
                "calibration_ts_iso": calibration_ts_raw.isoformat(),
                "n_fills": n_raw,
            },
        )


__all__ = [
    "CalibrationGate",
    "FreshnessCheck",
    "FRESHNESS_MAX_HOURS",
    "FreshnessStatus",
    "HandoffVerdict",
    "HandoffVerdictLiteral",
    "PowerCheck",
    "PowerStatus",
    "SAMPLE_POWER_MIN_N",
]
