"""AEG regime runner V127 DB writer.

MODULE_NOTE:
  模塊用途：把已驗證的 regime label / transition rows 寫入 V127
    ``research.aeg_regime_labels`` 與 ``research.aeg_regime_transitions``。此檔只被
    harness 的顯式 ``--write-db`` 路徑使用；默認 runner 只產 artifact。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence


def persist_regime_rows(
    conn: Any,
    *,
    labels: Sequence[Mapping[str, Any]],
    transitions: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """在 caller 交易中寫 V127 rows；caller 負責 commit/rollback。"""
    with conn.cursor() as cur:
        label_count = _insert_labels(cur, labels)
        transition_count = _insert_transitions(cur, transitions)
    return {"labels": label_count, "transitions": transition_count}


def _insert_labels(cur: Any, labels: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for row in labels:
        cur.execute(
            """
            INSERT INTO research.aeg_regime_labels (
                classifier_version, run_id, signal_ts, symbol, timeframe,
                main_regime, market_anchor_regime, high_vol_overlay, overlay_flags,
                ret_30d, ret_90d, rv_30d, rv_90d, trend_z_30, ma_50, ma_200,
                efficiency_30, direction_flip_30, rv_30d_percentile_365,
                context_bars, insufficient_context, feature_rules_digest,
                git_sha, git_dirty
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (classifier_version, symbol, timeframe, signal_ts, run_id)
            DO NOTHING
            """,
            (
                row.get("classifier_version"),
                row.get("run_id"),
                row.get("signal_ts"),
                row.get("symbol"),
                row.get("timeframe"),
                row.get("main_regime"),
                row.get("market_anchor_regime"),
                bool(row.get("high_vol_overlay")),
                json.dumps(row.get("overlay_flags") or {}, sort_keys=True),
                row.get("ret_30d"),
                row.get("ret_90d"),
                row.get("rv_30d"),
                row.get("rv_90d"),
                row.get("trend_z_30"),
                row.get("ma_50"),
                row.get("ma_200"),
                row.get("efficiency_30"),
                row.get("direction_flip_30"),
                row.get("rv_30d_percentile_365"),
                int(row.get("context_bars") or 0),
                bool(row.get("insufficient_context")),
                row.get("feature_rules_digest"),
                _git_sha(row),
                bool(row.get("git_dirty", False)),
            ),
        )
        count += int(getattr(cur, "rowcount", 0) or 0)
    return count


def _insert_transitions(cur: Any, transitions: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for row in transitions:
        cur.execute(
            """
            INSERT INTO research.aeg_regime_transitions (
                classifier_version, run_id, symbol, timeframe, transition_ts,
                from_regime, to_regime, trigger_feature
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s::jsonb
            )
            ON CONFLICT (classifier_version, symbol, timeframe, transition_ts, run_id)
            DO NOTHING
            """,
            (
                row.get("classifier_version"),
                row.get("run_id"),
                row.get("symbol"),
                row.get("timeframe"),
                row.get("transition_ts"),
                row.get("from_regime"),
                row.get("to_regime"),
                json.dumps(row.get("trigger_feature") or {}, sort_keys=True),
            ),
        )
        count += int(getattr(cur, "rowcount", 0) or 0)
    return count


def _git_sha(row: Mapping[str, Any]) -> str:
    value: Optional[Any] = row.get("git_sha")
    return str(value or "unknown")
