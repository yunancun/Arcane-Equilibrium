"""DL-3 Foundation Model Go/No-Go decision report generator (Phase 4 4-13).

DL-3 基礎模型 Go/No-Go 決策報告生成器。

MODULE_NOTE (EN):
    Reads a Dl3AbResult (from 4-12 dl3_ab_runner) plus operational metadata
    (latency, cost, model availability) and produces a plain-English Markdown
    report covering AUC delta, latency, cost, and a recommended Go/No-Go
    decision. Designed for AI-E sign-off.

    Decision matrix:
    - AB PROMOTE_PENDING + latency < 2000ms + cost_per_inference < $0.01 -> GO
    - AB PROMOTE_PENDING + latency >= 2000ms                              -> NO_GO (too slow)
    - AB PROMOTE_PENDING + cost >= $0.01                                  -> NO_GO (violates principle #14)
    - AB DEPRECATE                                                         -> NO_GO (insufficient AUC gain)
    - AB INCONCLUSIVE                                                      -> NO_GO (mixed signal, fail-closed)
    - AB INSUFFICIENT_DATA                                                 -> PENDING_DATA

MODULE_NOTE (中):
    讀取 4-12 dl3_ab_runner 的 AbResult 加上運營 metadata（延遲/成本/模型可用性），
    產出純英文 Markdown 報告，涵蓋 AUC delta、latency、cost 與 Go/No-Go 建議。
    供 AI-E 角色簽核。

    決策矩陣同上 (PROMOTE+快+便宜→GO, 太慢/太貴/AUC 不夠/混訊號→NO_GO,
    資料不足→PENDING_DATA)。

Usage / 用法:
    # Programmatic
    from program_code.ml_training.dl3_go_no_go import GoNoGoMetadata, generate_report
    report = generate_report(ab_result, GoNoGoMetadata(...))

    # CLI (via helper_scripts/phase4/dl3_go_no_go.py wrapper)
    python helper_scripts/phase4/dl3_go_no_go.py --output report.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Decision thresholds / 決策閾值
# ---------------------------------------------------------------------------

#: Maximum acceptable average inference latency for production GO.
#: 生產環境 GO 可接受的平均推理延遲上限。
MAX_LATENCY_MS_FOR_GO: float = 2000.0

#: Maximum acceptable cost per inference (USD) — principle #14 (zero-cost baseline).
#: 每次推理成本上限（美元）— 原則 #14（零成本可運行）。
MAX_COST_USD_PER_INFERENCE: float = 0.01


# ---------------------------------------------------------------------------
# Dataclasses / 資料類別
# ---------------------------------------------------------------------------


@dataclass
class GoNoGoMetadata:
    """Operational metadata beyond the AbResult.
    AbResult 之外的運營 metadata。
    """

    average_latency_ms: float
    cost_usd_per_inference: float
    inference_count_tested: int
    chronos_available: bool
    timesfm_available: bool


@dataclass
class GoNoGoReport:
    """Final report bundle: decision + reason + Markdown + machine summary.
    最終報告組合：決策 + 理由 + Markdown + 機器可讀摘要。
    """

    decision: str  # 'GO' / 'NO_GO' / 'PENDING_DATA'
    reason: str
    markdown: str
    machine_summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decision logic / 決策邏輯
# ---------------------------------------------------------------------------


def derive_decision(
    ab_decision: str, metadata: GoNoGoMetadata
) -> tuple[str, str]:
    """Map AbResult.decision + operational metadata into final Go/No-Go.

    將 AbResult.decision 加上運營 metadata 對映為最終 Go/No-Go。

    Returns:
        (decision, reason) where decision is one of GO / NO_GO / PENDING_DATA.
    """
    if ab_decision == "INSUFFICIENT_DATA":
        return (
            "PENDING_DATA",
            "Not enough samples to evaluate the AUC delta. Defer decision.",
        )

    if ab_decision == "DEPRECATE":
        return (
            "NO_GO",
            "AB test shows AUC improvement below the 0.01 threshold. "
            "DL-3 features do not meaningfully improve Scorer performance.",
        )

    if ab_decision == "INCONCLUSIVE":
        return (
            "NO_GO",
            "AB test shows mixed signal (AUC improved but Brier worsened). "
            "Fail-closed: holding off on promotion.",
        )

    if ab_decision == "PROMOTE_PENDING":
        # Check operational gates
        # 檢查運營門檻
        if metadata.average_latency_ms >= MAX_LATENCY_MS_FOR_GO:
            return (
                "NO_GO",
                f"AB recommends promotion but latency {metadata.average_latency_ms:.0f} ms "
                f"exceeds the {MAX_LATENCY_MS_FOR_GO:.0f} ms ceiling for the trading hot path.",
            )
        if metadata.cost_usd_per_inference >= MAX_COST_USD_PER_INFERENCE:
            return (
                "NO_GO",
                f"AB recommends promotion but cost ${metadata.cost_usd_per_inference:.4f}/inference "
                f"exceeds the ${MAX_COST_USD_PER_INFERENCE:.4f} ceiling (principle #14: zero-cost baseline).",
            )
        return (
            "GO",
            f"AB shows AUC improvement >= 0.01 with Brier improvement, "
            f"latency {metadata.average_latency_ms:.0f} ms < {MAX_LATENCY_MS_FOR_GO:.0f} ms, "
            f"cost ${metadata.cost_usd_per_inference:.4f}/inference < ${MAX_COST_USD_PER_INFERENCE:.4f}. "
            f"Recommend GO subject to AI-E sign-off.",
        )

    # Unknown ab_decision -> safe default
    # 未知的 ab_decision → 安全預設
    return (
        "NO_GO",
        f"Unknown AB decision '{ab_decision}', defaulting to NO_GO (fail-closed).",
    )


# ---------------------------------------------------------------------------
# Report generation / 報告生成
# ---------------------------------------------------------------------------


def _ab_field(ab_result: Any, name: str, default: Any = 0.0) -> Any:
    """Tolerant attribute / dict accessor for AbResult-shaped objects.
    對 AbResult 形狀物件的容忍式 attribute / dict 存取。
    """
    if hasattr(ab_result, name):
        return getattr(ab_result, name)
    if isinstance(ab_result, dict):
        return ab_result.get(name, default)
    return default


def generate_report(
    ab_result: Any,
    metadata: GoNoGoMetadata,
    operator_notes: str = "",
    now: Optional[datetime] = None,
) -> GoNoGoReport:
    """Build the full Markdown report and machine summary.

    建構完整的 Markdown 報告與機器摘要。

    Args:
        ab_result: Dl3AbResult-shaped object (dataclass or dict-like).
        metadata: GoNoGoMetadata instance.
        operator_notes: Optional free-form operator notes.
        now: Override current time for deterministic tests.

    Returns:
        GoNoGoReport with markdown ready to write to disk + sign-off checklist.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    ab_decision = str(_ab_field(ab_result, "decision", "INSUFFICIENT_DATA"))
    baseline_auc = float(_ab_field(ab_result, "baseline_auc", 0.0))
    augmented_auc = float(_ab_field(ab_result, "augmented_auc", 0.0))
    baseline_brier = float(_ab_field(ab_result, "baseline_brier", 0.0))
    augmented_brier = float(_ab_field(ab_result, "augmented_brier", 0.0))
    auc_delta = float(_ab_field(ab_result, "auc_delta", augmented_auc - baseline_auc))
    brier_delta = augmented_brier - baseline_brier
    n_samples = int(_ab_field(ab_result, "n_samples", 0))

    decision, reason = derive_decision(ab_decision, metadata)

    chronos_str = "Yes" if metadata.chronos_available else "No"
    timesfm_str = "Yes" if metadata.timesfm_available else "No"
    notes_block = operator_notes.strip() if operator_notes else "(none)"

    markdown = f"""# DL-3 Foundation Model Go/No-Go Report

**Generated**: {now.strftime("%Y-%m-%dT%H:%M:%SZ")}
**Decision**: **{decision}**
**Reason**: {reason}

## A/B Test Results / A/B 測試結果

| Metric | Baseline | + DL-3 | Delta |
|---|---|---|---|
| ROC-AUC | {baseline_auc:.4f} | {augmented_auc:.4f} | {auc_delta:+.4f} |
| Brier Score | {baseline_brier:.4f} | {augmented_brier:.4f} | {brier_delta:+.4f} |

- Sample size: {n_samples}
- AB engine decision: `{ab_decision}`

## Operational Metrics / 運營指標

| Metric | Value | Target |
|---|---|---|
| Average latency | {metadata.average_latency_ms:.1f} ms | < {MAX_LATENCY_MS_FOR_GO:.0f} ms |
| Cost per inference | ${metadata.cost_usd_per_inference:.4f} | < ${MAX_COST_USD_PER_INFERENCE:.4f} |
| Inferences tested | {metadata.inference_count_tested} | — |
| Chronos available | {chronos_str} | — |
| TimesFM available | {timesfm_str} | — |

## Recommended Decision / 建議決策

**{decision}** — {reason}

## Operator Notes / 操作員備註

{notes_block}

## Sign-off / 簽核

- [ ] AI-E reviewed and approved (AUC delta + AUC quality + sample size)
- [ ] PA architectural review (integration with Phase 3b Scorer)
- [ ] PM final acknowledgment
"""

    machine_summary = {
        "decision": decision,
        "reason": reason,
        "ab_decision": ab_decision,
        "baseline_auc": baseline_auc,
        "augmented_auc": augmented_auc,
        "auc_delta": auc_delta,
        "baseline_brier": baseline_brier,
        "augmented_brier": augmented_brier,
        "brier_delta": brier_delta,
        "n_samples": n_samples,
        "metadata": asdict(metadata),
        "thresholds": {
            "max_latency_ms": MAX_LATENCY_MS_FOR_GO,
            "max_cost_usd_per_inference": MAX_COST_USD_PER_INFERENCE,
        },
        "generated_at_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return GoNoGoReport(
        decision=decision,
        reason=reason,
        markdown=markdown,
        machine_summary=machine_summary,
    )


def write_report(report: GoNoGoReport, output_path: str | Path) -> Path:
    """Write the Markdown report to disk plus a sibling .json with machine_summary.

    把 Markdown 報告寫到磁碟，並產生 sibling .json 檔含 machine_summary。

    Cross-platform: uses pathlib, no hardcoded /home paths.
    跨平台：用 pathlib，無硬編碼路徑。

    Returns the Path of the written Markdown file.
    """
    md_path = Path(output_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report.markdown, encoding="utf-8")

    json_path = md_path.with_suffix(md_path.suffix + ".json")
    json_path.write_text(
        json.dumps(report.machine_summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return md_path


# ---------------------------------------------------------------------------
# CLI entry / CLI 入口
# ---------------------------------------------------------------------------


def _placeholder_ab_result() -> dict:
    """Synthetic INSUFFICIENT_DATA placeholder so the script runs end-to-end with no inputs.
    合成 INSUFFICIENT_DATA 占位，使腳本無輸入也能跑通。
    """
    return {
        "decision": "INSUFFICIENT_DATA",
        "baseline_auc": 0.0,
        "augmented_auc": 0.0,
        "baseline_brier": 0.0,
        "augmented_brier": 0.0,
        "auc_delta": 0.0,
        "n_samples": 0,
    }


def _placeholder_metadata() -> GoNoGoMetadata:
    """Synthetic placeholder metadata.
    合成占位 metadata。
    """
    return GoNoGoMetadata(
        average_latency_ms=0.0,
        cost_usd_per_inference=0.0,
        inference_count_tested=0,
        chronos_available=False,
        timesfm_available=False,
    )


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry. Reads JSON files for ab_result + metadata, writes Markdown + JSON output.

    CLI 入口。從 JSON 檔讀取 ab_result 與 metadata，寫出 Markdown + JSON。

    Args via argparse:
        --ab-result-json PATH  : path to JSON dump of AbResult
        --metadata-json PATH   : path to JSON dump of GoNoGoMetadata
        --output PATH          : path to output Markdown
        --notes "..."          : operator notes

    All args optional — runs with synthetic placeholders for end-to-end smoke.
    """
    import argparse

    parser = argparse.ArgumentParser(description="DL-3 Go/No-Go report generator")
    parser.add_argument("--ab-result-json", type=str, default=None)
    parser.add_argument("--metadata-json", type=str, default=None)
    parser.add_argument(
        "--output",
        type=str,
        default="reports/dl3_go_no_go.md",
        help="Output Markdown path (sibling .json will also be written)",
    )
    parser.add_argument("--notes", type=str, default="")
    args = parser.parse_args(argv)

    if args.ab_result_json:
        ab_result = json.loads(Path(args.ab_result_json).read_text())
    else:
        ab_result = _placeholder_ab_result()

    if args.metadata_json:
        meta_dict = json.loads(Path(args.metadata_json).read_text())
        metadata = GoNoGoMetadata(**meta_dict)
    else:
        metadata = _placeholder_metadata()

    report = generate_report(ab_result, metadata, operator_notes=args.notes)
    output_path = write_report(report, args.output)
    print(f"DL-3 Go/No-Go report written: {output_path} (decision={report.decision})")
    return 0
