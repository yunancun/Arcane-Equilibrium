"""selection_bias_validator — REF-20 Wave 6 P4-Q3 manifest selection-bias guard.

選擇偏差 manifest 校驗器 — REF-20 Wave 6 P4-Q3 manifest selection-bias 守門。

MODULE_NOTE (EN):
    Sibling validator that enforces V3 §8.3 selection-bias correction
    metadata at sign-time + verify-time of replay manifests. The
    `selection_bias_correction` block is a mandatory manifest field
    capturing the K-trial / OOS / CV-protocol / embargo provenance
    that downstream gates (DSR(K), PBO, embargo_validator) consume.

    This validator does not touch HMAC-SHA256 signing logic in
    `manifest_signer.py`; it complements it by validating manifest
    semantic content. Caller wires this check into:

      1. POST /api/v1/replay/manifests sign-time route handler.
      2. GET /api/v1/replay/manifests/<id>/verify verify-time handler.

    Wave 6 P4-Q3 scope (this commit):
      - SelectionBiasCorrection dataclass (5 mandatory fields).
      - validate_selection_bias_correction(manifest: dict) -> ValidationResult.
      - 4 enum-style fail modes mirroring `SignatureFailMode` style.
      - 8 pytest cases.

    NOT in this scope:
      - DB-side CHECK constraint (V3 §3 explicitly says manifest is
        file-based per S2 IMPL; no SQL CHECK at DB layer for this field).
      - replay_routes.py call-site wiring (separate sub-task; this
        module is import-ready).
      - DSR(K) / PBO sibling gates (Wave 6 P4-Q1/Q2 → dsr_gate.py /
        pbo_gate.py).
      - embargo_days numeric check (already done by V041 CHECK +
        embargo_validator.py — this validator only ensures the
        `embargo_days` field is present and non-negative).

MODULE_NOTE (中):
    Sibling 校驗器，在 replay manifest sign-time + verify-time 強制
    V3 §8.3 選擇偏差修正 metadata。`selection_bias_correction` block
    是 manifest 必要欄位，捕捉 K-trial / OOS / CV 協定 / embargo 來源，
    供下游 gate（DSR(K)、PBO、embargo_validator）消費。

    本校驗器不碰 `manifest_signer.py` 的 HMAC-SHA256 簽名邏輯；
    補充驗 manifest 語意內容。Caller 將此檢查接入：
      1. POST /api/v1/replay/manifests sign-time route handler。
      2. GET /api/v1/replay/manifests/<id>/verify verify-time handler。

    Wave 6 P4-Q3 範圍：
      - SelectionBiasCorrection dataclass（5 必要欄位）
      - validate_selection_bias_correction(manifest: dict) -> ValidationResult
      - 4 fail-mode 枚舉
      - 8 pytest cases

    不在範圍：
      - DB 端 CHECK 約束（V3 §3 明確：manifest 為 file-based per S2 IMPL）
      - replay_routes.py call-site wiring
      - DSR(K) / PBO sibling gates（Wave 6 P4-Q1/Q2）
      - embargo_days 數值 check（已由 V041 CHECK + embargo_validator.py 處理）

SPEC:
  - REF-20 V3 §8.3 (Selection Bias Controls)
  - REF-20 V3 §11 P4 Exit
  - REF-20 V3 §12 acceptance #17 (replay_cv_protocol)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P4-Q3
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Literal, Mapping, Optional


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.3 thresholds / V3 §8.3 閾值常數
# ─────────────────────────────────────────────────────────────────────────────

# K must be >= 10 per V3 §8.3 (mirrors PBO min_K).
# K 必 >= 10 依 V3 §8.3（與 PBO min_K 一致）。
MIN_TRIALS_K: int = 10

# OOS percentage must be >= 0.20 per V3 §8.3.
# 樣本外比例必 >= 0.20 依 V3 §8.3。
MIN_OOS_PCT: float = 0.20

# Embargo must be >= V041 CHECK floor (always 7 days minimum).
# Embargo 必 >= V041 CHECK 下限（最低 7 天）。
MIN_EMBARGO_DAYS_FLOOR: int = 7

# CV protocol allowlist per V3 §8.3 / §10.
# CV 協定白名單依 V3 §8.3 / §10。
ALLOWED_CV_PROTOCOLS: frozenset[str] = frozenset(
    {"walk_forward", "cscv", "purged_kfold"}
)


# ─────────────────────────────────────────────────────────────────────────────
# Fail-mode enum / Fail-mode 枚舉
# ─────────────────────────────────────────────────────────────────────────────


class SelectionBiasFailMode(Enum):
    """5 fail-mode mirroring `SignatureFailMode` style.

    5 fail-mode 鏡像 `SignatureFailMode` 風格。

    Each value maps to the `selection_bias_fail_mode` string label written
    to `learning.governance_audit_log` audit row so the dashboard can
    disambiguate selection-bias rejection root-causes.

    每 value 對應 audit row 寫入時的 `selection_bias_fail_mode` 字串 label。
    """

    MISSING_BLOCK = "missing_block"
    K_TOO_LOW = "k_too_low"
    OOS_PCT_TOO_LOW = "oos_pct_too_low"
    UNKNOWN_CV_PROTOCOL = "unknown_cv_protocol"
    EMBARGO_TOO_LOW = "embargo_too_low"


# ─────────────────────────────────────────────────────────────────────────────
# Schema dataclass / Schema dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SelectionBiasCorrection:
    """V3 §8.3 selection-bias correction metadata block.

    V3 §8.3 選擇偏差修正 metadata block。

    All 5 fields are mandatory in the manifest. Caller may pass nested
    dict matching this shape; `validate_selection_bias_correction()`
    parses + validates.

    全 5 欄位於 manifest 中必填。Caller 可傳結構吻合的 nested dict；
    `validate_selection_bias_correction()` 解析並校驗。

    Attributes / 屬性:
        n_trials_K: int >= 10. Number of variants explored before selecting
                    best candidate (drives DSR(K) deflation). /
                    探索變體數（驅動 DSR(K) 縮減）。
        backtest_period_days: int > 0. Total backtest window in days. /
                              回測窗口總天數。
        out_of_sample_pct: float ∈ [0.20, 1.0). Fraction held out for OOS. /
                           樣本外保留比例（V3 §8.3 >= 0.20）。
        cv_protocol: Literal['walk_forward', 'cscv', 'purged_kfold']. /
                     CV 協定（V3 §8.3 白名單）。
        embargo_days: int >= MIN_EMBARGO_DAYS_FLOOR (>=7). Aligns with V041
                      CHECK constraint floor. /
                      Embargo 天數（與 V041 CHECK 下限對齊，>=7）。
    """

    n_trials_K: int
    backtest_period_days: int
    out_of_sample_pct: float
    cv_protocol: Literal["walk_forward", "cscv", "purged_kfold"]
    embargo_days: int

    def to_dict(self) -> dict:
        """Convert to manifest-ready dict.

        轉為 manifest-ready dict。
        """
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Validation result / 驗證結果
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of `validate_selection_bias_correction()`.

    `validate_selection_bias_correction()` 結果。

    Attributes / 屬性:
        ok: True if all V3 §8.3 invariants pass. /
            V3 §8.3 不變量全通過時為 True。
        fail_mode: SelectionBiasFailMode if not ok; None if ok. /
                   不通過時的 SelectionBiasFailMode；通過時 None。
        reason_zh: Chinese reason if not ok; empty string if ok. /
                   不通過時中文原因；通過時空字串。
        reason_en: English reason if not ok; empty string if ok. /
                   不通過時英文原因；通過時空字串。
        parsed: Parsed SelectionBiasCorrection (None if MISSING_BLOCK). /
                解析後的 SelectionBiasCorrection（MISSING_BLOCK 時 None）。
    """

    ok: bool
    fail_mode: Optional[SelectionBiasFailMode]
    reason_zh: str
    reason_en: str
    parsed: Optional[SelectionBiasCorrection]


# ─────────────────────────────────────────────────────────────────────────────
# Public API / 公開 API
# ─────────────────────────────────────────────────────────────────────────────


def validate_selection_bias_correction(
    manifest: Mapping[str, object],
    *,
    block_key: str = "selection_bias_correction",
) -> ValidationResult:
    """Validate `selection_bias_correction` block in manifest dict.

    校驗 manifest dict 中的 `selection_bias_correction` block。

    Validation order (V3 §8.3 binding) / 校驗順序：
      1. block presence → MISSING_BLOCK
      2. K >= 10 → K_TOO_LOW
      3. oos_pct >= 0.20 → OOS_PCT_TOO_LOW
      4. cv_protocol ∈ allowlist → UNKNOWN_CV_PROTOCOL
      5. embargo_days >= MIN_EMBARGO_DAYS_FLOOR → EMBARGO_TOO_LOW

    Args / 引數:
        manifest: Mapping (typically dict). Caller may pass full manifest
                  or just the inner block; we look up `block_key`.
                  完整 manifest 或內層 block 皆可（依 block_key 查找）。
        block_key: Top-level key under which the bias block lives. /
                   bias block 之頂層鍵。

    Returns / 回傳:
        ValidationResult with ok / fail_mode / reasons / parsed. /
        含 ok / fail_mode / reasons / parsed 之 ValidationResult。
    """
    # Step 1: Block presence / 步驟 1：block 存在性
    block = manifest.get(block_key)
    if block is None:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.MISSING_BLOCK,
            reason_zh=f"manifest 缺 `{block_key}` block（V3 §8.3 強制）",
            reason_en=f"manifest missing `{block_key}` block (V3 §8.3 mandatory)",
            parsed=None,
        )

    if not isinstance(block, Mapping):
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.MISSING_BLOCK,
            reason_zh=(
                f"`{block_key}` 必為 dict / Mapping，"
                f"實際 type={type(block).__name__}"
            ),
            reason_en=(
                f"`{block_key}` must be dict / Mapping; "
                f"got type={type(block).__name__}"
            ),
            parsed=None,
        )

    # Required field presence + type / 必要欄位存在性 + 型別
    required_fields = {
        "n_trials_K": int,
        "backtest_period_days": int,
        "out_of_sample_pct": float,
        "cv_protocol": str,
        "embargo_days": int,
    }
    for field_name, expected_type in required_fields.items():
        if field_name not in block:
            return ValidationResult(
                ok=False,
                fail_mode=SelectionBiasFailMode.MISSING_BLOCK,
                reason_zh=(
                    f"`{block_key}` 缺必要欄位 `{field_name}`"
                ),
                reason_en=(
                    f"`{block_key}` missing required field `{field_name}`"
                ),
                parsed=None,
            )
        # Allow int for float (Python int IS instance-of for float
        # numerically; we coerce explicitly).
        # 允許 int 充當 float（數值上 Python int 為 float 之子集；顯式 coerce）。
        value = block[field_name]
        if expected_type is float:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return ValidationResult(
                    ok=False,
                    fail_mode=SelectionBiasFailMode.MISSING_BLOCK,
                    reason_zh=(
                        f"`{block_key}.{field_name}` 必為 float，"
                        f"實際 type={type(value).__name__}"
                    ),
                    reason_en=(
                        f"`{block_key}.{field_name}` must be float; "
                        f"got type={type(value).__name__}"
                    ),
                    parsed=None,
                )
        else:
            # Reject bool when int expected (bool is a subclass of int).
            # 預期 int 時拒 bool（bool 為 int 子類）。
            if not isinstance(value, expected_type) or isinstance(value, bool):
                return ValidationResult(
                    ok=False,
                    fail_mode=SelectionBiasFailMode.MISSING_BLOCK,
                    reason_zh=(
                        f"`{block_key}.{field_name}` 必為 {expected_type.__name__}，"
                        f"實際 type={type(value).__name__}"
                    ),
                    reason_en=(
                        f"`{block_key}.{field_name}` must be {expected_type.__name__}; "
                        f"got type={type(value).__name__}"
                    ),
                    parsed=None,
                )

    # Parse into dataclass for downstream consumer convenience.
    # 解析為 dataclass 供下游 consumer 便利使用。
    parsed = SelectionBiasCorrection(
        n_trials_K=int(block["n_trials_K"]),
        backtest_period_days=int(block["backtest_period_days"]),
        out_of_sample_pct=float(block["out_of_sample_pct"]),
        cv_protocol=str(block["cv_protocol"]),  # type: ignore[arg-type]
        embargo_days=int(block["embargo_days"]),
    )

    # Step 2: K >= 10 / 步驟 2
    if parsed.n_trials_K < MIN_TRIALS_K:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.K_TOO_LOW,
            reason_zh=(
                f"n_trials_K={parsed.n_trials_K} < {MIN_TRIALS_K}（V3 §8.3 最小 K）"
            ),
            reason_en=(
                f"n_trials_K={parsed.n_trials_K} < {MIN_TRIALS_K} (V3 §8.3 min K)"
            ),
            parsed=parsed,
        )

    # Step 3: oos_pct >= 0.20 / 步驟 3
    if parsed.out_of_sample_pct < MIN_OOS_PCT:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.OOS_PCT_TOO_LOW,
            reason_zh=(
                f"out_of_sample_pct={parsed.out_of_sample_pct} < {MIN_OOS_PCT}"
                f"（V3 §8.3 最小 OOS 比例）"
            ),
            reason_en=(
                f"out_of_sample_pct={parsed.out_of_sample_pct} < {MIN_OOS_PCT} "
                f"(V3 §8.3 min OOS fraction)"
            ),
            parsed=parsed,
        )
    if parsed.out_of_sample_pct >= 1.0:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.OOS_PCT_TOO_LOW,
            reason_zh=(
                f"out_of_sample_pct={parsed.out_of_sample_pct} 必 < 1.0"
                f"（OOS 不可佔 100%）"
            ),
            reason_en=(
                f"out_of_sample_pct={parsed.out_of_sample_pct} must be < 1.0 "
                f"(OOS cannot consume 100%)"
            ),
            parsed=parsed,
        )

    # Step 4: cv_protocol ∈ allowlist / 步驟 4
    if parsed.cv_protocol not in ALLOWED_CV_PROTOCOLS:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.UNKNOWN_CV_PROTOCOL,
            reason_zh=(
                f"cv_protocol='{parsed.cv_protocol}' 不在白名單"
                f"{sorted(ALLOWED_CV_PROTOCOLS)}（V3 §8.3）"
            ),
            reason_en=(
                f"cv_protocol='{parsed.cv_protocol}' not in allowlist "
                f"{sorted(ALLOWED_CV_PROTOCOLS)} (V3 §8.3)"
            ),
            parsed=parsed,
        )

    # Step 5: embargo_days >= V041 floor / 步驟 5：embargo_days >= V041 下限
    if parsed.embargo_days < MIN_EMBARGO_DAYS_FLOOR:
        return ValidationResult(
            ok=False,
            fail_mode=SelectionBiasFailMode.EMBARGO_TOO_LOW,
            reason_zh=(
                f"embargo_days={parsed.embargo_days} < {MIN_EMBARGO_DAYS_FLOOR}"
                f"（V041 CHECK 下限）"
            ),
            reason_en=(
                f"embargo_days={parsed.embargo_days} < {MIN_EMBARGO_DAYS_FLOOR} "
                f"(V041 CHECK floor)"
            ),
            parsed=parsed,
        )

    # All checks passed. / 全部通過。
    return ValidationResult(
        ok=True,
        fail_mode=None,
        reason_zh="",
        reason_en="",
        parsed=parsed,
    )
