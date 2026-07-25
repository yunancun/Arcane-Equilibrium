"""ALR consumer 的 write-metrics 投影葉模組(S2.4 W2 · 2000 行治理拆分)。

自 ``alr_event_consumer`` 原樣下沉的**純投影**面:把 session 累計計數器折成
``alr_write_metrics_v1`` 文件,並在折算時 fail-closed 檢查計數自洽(負值/布林/
attempt 與 total 不一致一律 typed 拒絕)。零 DB、零 I/O、零 authority。

行為與拆分前逐位元組一致;``alr_event_consumer`` 逐名 re-export 保持既有匯入面
與 monkeypatch 縫不變。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ml_training.alr_candidate_board_events import AlrEventConsumerError


def build_write_metrics(
    totals: Mapping[str, int],
    *,
    session_id: str,
) -> dict[str, Any]:
    def counter(key: str) -> int:
        value = totals.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AlrEventConsumerError("write_metric_counter_invalid")
        return value

    def ratio(numerator: int, denominator: int) -> float:
        if numerator > denominator:
            raise AlrEventConsumerError("write_metric_ratio_invalid")
        return numerator / denominator if denominator else 0.0

    health_attempts = counter("health_attempts")
    health_emitted = counter("health_snapshots")
    health_suppressed = counter("health_writes_suppressed")
    decision_attempts = counter("decision_write_attempts")
    decision_suppressed = counter("decision_writes_suppressed")
    feedback_attempts = counter("feedback_write_attempts")
    feedback_persisted = counter("feedback_persisted")
    feedback_duplicate_retries = counter("feedback_duplicate_retries")
    feedback_artifact_rows = counter("feedback_artifact_rows_written")
    feedback_provenance_rows = counter(
        "feedback_provenance_rows_written"
    )
    feedback_event_rows = counter("feedback_event_rows_written")
    feedback_total_rows = counter("feedback_total_rows_written")
    feedback_payload_bytes = counter("feedback_payload_bytes_written")
    if feedback_persisted + feedback_duplicate_retries != feedback_attempts:
        raise AlrEventConsumerError("feedback_write_metric_attempt_invalid")
    if feedback_total_rows != (
        feedback_artifact_rows
        + feedback_provenance_rows
        + feedback_event_rows
    ):
        raise AlrEventConsumerError("feedback_write_metric_total_invalid")
    return {
        "schema_version": "alr_write_metrics_v1",
        "scope": {
            "kind": "consumer_session_cumulative",
            "session_id": session_id,
            "through_completed_health_attempt": health_attempts,
        },
        "health": {
            "attempts": health_attempts,
            "emitted": health_emitted,
            "state_delta_writes": counter("health_state_delta_writes"),
            "heartbeat_writes": counter("health_heartbeat_writes"),
            "writes_suppressed": health_suppressed,
            "rows_written": counter("health_rows_written"),
            "payload_bytes_written": counter(
                "health_payload_bytes_written"
            ),
            "suppression_ratio": ratio(
                health_suppressed,
                health_attempts,
            ),
        },
        "decision": {
            "attempts": decision_attempts,
            "writes_suppressed": decision_suppressed,
            "duplicate_retries": counter("decision_duplicate_retries"),
            "artifact_rows_written": counter(
                "operational_artifact_rows_written"
            )
            + feedback_artifact_rows,
            "provenance_rows_written": counter(
                "operational_provenance_rows_written"
            )
            + feedback_provenance_rows,
            "run_rows_written": counter("operational_run_rows_written"),
            "feedback_rows_written": feedback_event_rows
            + counter("operational_feedback_rows_written"),
            "defer_artifact_rows_written": counter(
                "operational_defer_artifact_rows_written"
            ),
            "payload_bytes_written": counter(
                "operational_payload_bytes_written"
            )
            + feedback_payload_bytes,
            "source_rows_consumed": counter(
                "operational_source_rows_consumed"
            ),
            "suppression_ratio": ratio(
                decision_suppressed,
                decision_attempts,
            ),
        },
        "feedback": {
            "attempts": feedback_attempts,
            "persisted": feedback_persisted,
            "duplicate_retries": feedback_duplicate_retries,
            "persisted_ratio": ratio(
                feedback_persisted,
                feedback_attempts,
            ),
            "duplicate_retry_ratio": ratio(
                feedback_duplicate_retries,
                feedback_attempts,
            ),
            "artifact_rows_written": feedback_artifact_rows,
            "provenance_rows_written": feedback_provenance_rows,
            "event_rows_written": feedback_event_rows,
            "total_rows_written": feedback_total_rows,
            "payload_bytes_written": feedback_payload_bytes,
        },
    }


def row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


__all__ = ["build_write_metrics", "row_value"]
