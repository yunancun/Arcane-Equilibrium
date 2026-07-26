"""alr_retention_runner(S2.4 §2.1 W2a 拆分後的 retention-backlog 獨立入口)行為測試。

原 test_alr_event_consumer.test_retention_backlog_reports_only_derived_cache_actions
等值搬移至此(行為/異常身分不變),並補 batch-limit 與 result-shape 負向。
"""

from __future__ import annotations

import pytest

from ml_training import alr_retention_runner as runner
from ml_training.alr_event_consumer import AlrEventConsumerError
from ml_training.alr_retention_runner import process_retention_backlog


def test_retention_backlog_reports_only_derived_cache_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "run_retention_pass",
        lambda connection, *, now, grace_seconds, limit: {
            "scanned": 2,
            "quarantined": 1,
            "restored": 0,
            "swept": 1,
            "retained": 0,
            "skipped": 0,
        },
    )

    result = process_retention_backlog(object(), max_batch=8)

    assert result == {
        "retention_scanned": 2,
        "retention_quarantined": 1,
        "retention_restored": 0,
        "retention_swept": 1,
        "retention_retained": 0,
        "retention_skipped": 0,
    }


@pytest.mark.parametrize("max_batch", [0, 257, True, "8", None])
def test_retention_backlog_rejects_invalid_batch_limit(max_batch: object) -> None:
    # 異常身分不變:仍是 AlrEventConsumerError(consumer re-export 同一類別)。
    with pytest.raises(AlrEventConsumerError, match="retention_batch_limit_invalid"):
        process_retention_backlog(object(), max_batch=max_batch)  # type: ignore[arg-type]


def test_retention_backlog_rejects_malformed_pass_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "run_retention_pass",
        lambda connection, *, now, grace_seconds, limit: {"scanned": 1},
    )
    with pytest.raises(AlrEventConsumerError, match="retention_result_invalid"):
        process_retention_backlog(object(), max_batch=8)


def test_runner_error_class_is_the_consumer_error_class() -> None:
    # 搬移不裂開異常家族:runner 拋的類別必須與 consumer 公開的同一物件。
    assert runner.AlrEventConsumerError is AlrEventConsumerError
