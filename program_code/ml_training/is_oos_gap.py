"""is_oos_gap — M3 leak-free PIT producer（temporal in-sample → out-of-sample gap 檢查）。

MODULE_NOTE
模塊用途：
  L2 Phase 3b M3 leak-typing producer（PA P3b 設計 §D + MIT §1.2）。給定 CV split spec
  （train/test signal ts + per-train label-window end），驗該 split 是否 temporally leak-free
  （time-series-cv-protocol §2）：temporal separation + embargo + purge + no-shuffle。emit
  source_class="is_oos_gap" 的 typed evidence row → M3 leak-free set。

  ★ namesake 區隔（MIT §1.2.3 option (a)，PA concur）：sample_weight_sensitivity.py:329 有一個
    「is_oos_gap」是 train-vs-OOS RMSE gap-ratio overfit detector（語義完全不同）。本模塊用
    **distinct 模塊/函數名 check_oos_gap**，但保留 M3 source_class 字串 "is_oos_gap"（leak-
    typing tag，非那個 RMSE metric）——source_class 層零衝突，只 human-facing 名不同。不改
    既有 overfit metric 的 consumer（避免為 cosmetic 改名違 surgical-change 紀律）。

主要類/函數：
  - OosGapResult：dataclass（source_class / leak_free / 四檢查布林 + 量值 / reasons）。
  - check_oos_gap(...)：四檢查（temporal separation / embargo / purge / no-shuffle）。

依賴：標準庫（無新算法、無 DB、無 model）。

硬邊界：
  - leak_free=True「只」當四檢查皆過（temporal_separation_ok AND embargo_sufficient AND
    purge_violations==0 AND NOT shuffle_detected）；任一不過 → leak_free=False（fail-closed）。
  - embargo size 由 caller 給（label horizon + autocorrelation 決定，不硬編；skill rule）。
  - 純 compute：0 DB、0 order path。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Hashable, Optional, Sequence

# M3 typed source_class（與 l2_prompt_contract_registry.ML_ADVISORY_LEAKFREE_SOURCE_CLASSES 對齊）。
SOURCE_CLASS = "is_oos_gap"


@dataclass
class OosGapResult:
    """is_oos_gap 裁決結果（M3 typed evidence row）。

    leak_free=True 只當四檢查皆過。各布林 + 量值是 audit 載體（為何 leak-free 或為何不是）。
    """

    source_class: str                  # 恆 "is_oos_gap"
    leak_free: bool
    temporal_separation_ok: bool       # max(train.signal_ts) < min(test.signal_ts)
    embargo_gap_bars: float            # 實際 gap（min(test) − max(train)，以 bar/序數計）
    embargo_sufficient: bool           # gap >= embargo_bars
    purge_violations: int              # train sample 其 label window 伸進 test 的數量
    shuffle_detected: bool             # fold 非連續時間塊（KFold-shuffle）
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class,
            "leak_free": self.leak_free,
            "temporal_separation_ok": self.temporal_separation_ok,
            "embargo_gap_bars": self.embargo_gap_bars,
            "embargo_sufficient": self.embargo_sufficient,
            "purge_violations": self.purge_violations,
            "shuffle_detected": self.shuffle_detected,
            "reasons": list(self.reasons),
        }


def check_oos_gap(
    train_signal_ts: Sequence[Hashable],
    test_signal_ts: Sequence[Hashable],
    train_label_end_ts: Sequence[Hashable],
    *,
    label_horizon_bars: int,
    embargo_bars: int,
) -> OosGapResult:
    """驗 CV split 是否 temporally leak-free（time-series-cv-protocol §2 四檢查）。

    參數：
      - train_signal_ts / test_signal_ts：train / test fold 的 signal timestamps（bar index
        或 datetime；以 _ord 轉序數比較）。
      - train_label_end_ts：per-train-sample 的 label window end（[t, t+H] 的 t+H），供 purge
        檢查（與 train_signal_ts 同長同序）。
      - label_horizon_bars：label horizon H（診斷記錄；purge 用 train_label_end_ts 直接判）。
      - embargo_bars：embargo size（Lopez de Prado AFML Ch.7；由 label horizon + autocorr 決定，
        caller 給，不硬編）。

    回 OosGapResult。leak_free=True 只當四檢查皆過（fail-closed）。
    """
    reasons: list[str] = []

    train_ord = _to_ords(train_signal_ts)
    test_ord = _to_ords(test_signal_ts)

    if not train_ord or not test_ord:
        # train/test 任一空 → 無法證 leak-free（fail-closed）。
        reasons.append("empty_train_or_test_fold")
        return OosGapResult(
            source_class=SOURCE_CLASS, leak_free=False, temporal_separation_ok=False,
            embargo_gap_bars=0.0, embargo_sufficient=False, purge_violations=0,
            shuffle_detected=False, reasons=reasons,
        )

    max_train = max(train_ord)
    min_test = min(test_ord)

    # ── 檢查 1：temporal separation（max(train) < min(test)；無 future-in-train）──
    temporal_separation_ok = max_train < min_test
    if not temporal_separation_ok:
        reasons.append("temporal_separation_violated")

    # ── 檢查 2：embargo gap（min(test) − max(train) >= embargo_bars）──
    embargo_gap = float(min_test - max_train)
    embargo_sufficient = embargo_gap >= float(embargo_bars)
    if not embargo_sufficient:
        reasons.append("embargo_gap_insufficient")

    # ── 檢查 3：purge（無 train sample 其 label window [t, t+H] 伸進 test）──
    # train.label_end_ts >= min(test.signal_ts) 即 label 窗 overlap 進 test → purge violation。
    label_end_ord = _to_ords(train_label_end_ts)
    purge_violations = 0
    if label_end_ord:
        purge_violations = sum(1 for le in label_end_ord if le >= min_test)
    else:
        # 無 label_end → 退用 train_signal_ts + horizon 估（保守：t + H 越過 min_test 算 violation）。
        purge_violations = sum(
            1 for t in train_ord if (t + float(label_horizon_bars)) >= min_test
        )
    if purge_violations > 0:
        reasons.append("purge_violation")

    # ── 檢查 4：no shuffle（train 與 test 各為連續時間塊；KFold-shuffle 禁）──
    shuffle_detected = _is_shuffled(train_ord) or _is_shuffled(test_ord) or _interleaved(
        train_ord, test_ord
    )
    if shuffle_detected:
        reasons.append("shuffle_detected")

    leak_free = (
        temporal_separation_ok
        and embargo_sufficient
        and purge_violations == 0
        and not shuffle_detected
    )
    return OosGapResult(
        source_class=SOURCE_CLASS,
        leak_free=leak_free,
        temporal_separation_ok=temporal_separation_ok,
        embargo_gap_bars=embargo_gap,
        embargo_sufficient=embargo_sufficient,
        purge_violations=int(purge_violations),
        shuffle_detected=bool(shuffle_detected),
        reasons=_dedupe(reasons),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 內部 helper（序數轉換 / shuffle 偵測）
# ═══════════════════════════════════════════════════════════════════════════════


def _to_ords(ts_list: Sequence[Hashable]) -> list[float]:
    """timestamps → 序數 float list（datetime → toordinal/timestamp；數值 → float）。保留原序。

    為什麼保留原序（不排序）：shuffle 偵測需要看「caller 給的順序」是否單調遞增。
    """
    out: list[float] = []
    for ts in ts_list:
        o = _ord(ts)
        if o is None:
            continue
        out.append(o)
    return out


def _ord(ts: Hashable) -> Optional[float]:
    """單一 ts → 序數 float（datetime.timestamp 優先精度；date.toordinal；數值 float）。"""
    ts_method = getattr(ts, "timestamp", None)
    if callable(ts_method):
        try:
            return float(ts_method())
        except Exception:  # noqa: BLE001 — 非標準 datetime → 試其他
            pass
    to_ord = getattr(ts, "toordinal", None)
    if callable(to_ord):
        try:
            return float(to_ord())
        except Exception:  # noqa: BLE001
            pass
    try:
        return float(ts)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _is_shuffled(ords: Sequence[float]) -> bool:
    """fold 內 ts 非單調遞增 → shuffle（KFold-shuffle 把時間塊打散）。

    為什麼非嚴格遞增也算 leak-suspect：時間序 CV 的 fold 必須是連續、單調的時間塊；亂序
    （或重複跳動）暗示 KFold-shuffle，破壞時序紀律。
    """
    for i in range(1, len(ords)):
        if ords[i] < ords[i - 1]:
            return True
    return False


def _interleaved(train_ord: Sequence[float], test_ord: Sequence[float]) -> bool:
    """train 與 test 時間塊交錯（某 test ts 落在 train 的 [min,max] 區間內）→ shuffle-class leak。

    為什麼：即使各 fold 內單調，若 test 塊嵌進 train 塊的時間範圍，就是 boundary 被打散
    （非乾淨的 train→gap→test 切分），等同 shuffle 洩漏。
    """
    if not train_ord or not test_ord:
        return False
    tr_min, tr_max = min(train_ord), max(train_ord)
    return any(tr_min <= t <= tr_max for t in test_ord)


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


__all__ = [
    "SOURCE_CLASS",
    "OosGapResult",
    "check_oos_gap",
]
