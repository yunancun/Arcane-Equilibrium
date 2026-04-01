from __future__ import annotations

"""
MODULE_NOTE (中文):
  學習系統只讀查詢模塊。包含審核隊列、觀察流、實驗隊列的只讀視圖構建器。
  從 learning_ops.py 拆分而來（learning_ops Wave E 重構）。

  ★ 純讀操作，不寫入任何狀態，不依賴 _base 單例。

MODULE_NOTE (English):
  Learning system read-only query module. Contains review queue, observation feed,
  and experiment queue read-only view builders.
  Extracted from learning_ops.py (learning_ops Wave E refactoring).

  ★ Pure read operations, no state writes, no dependency on _base singletons.
"""

import copy
from typing import Any

# 每次最多返回多少条历史记录 / Max entries returned per call
_MAX_RECENT_ENTRIES: int = 20


def build_review_queue(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建审核队列视图 / Build review queue view.

    返回待审核的审核包（pending_review + ai_consulted + deferred）
    和最近已决定的审核包（approved + rejected）。
    Returns pending packets and recently decided packets.
    """
    ls = snapshot.get("learning_state", {})
    queue = ls.get("records", {}).get("review_queue", [])
    pipeline = ls.get("auto_pipeline", {})

    pending = [p for p in queue if p.get("status") in {"pending_review", "ai_consulted", "deferred"}]
    decided = [p for p in queue if p.get("status") in {"approved", "rejected"}]

    # 最新在前 / Newest first
    pending.sort(key=lambda x: x.get("created_ts_ms", 0), reverse=True)
    decided.sort(key=lambda x: x.get("decided_ts_ms", 0), reverse=True)

    return {
        "pending_packets": pending,
        "recent_decided": decided[:_MAX_RECENT_ENTRIES],
        "pending_count": len(pending),
        "total_count": len(queue),
        "auto_pipeline_summary": copy.deepcopy(pipeline),
    }


def build_learning_feed(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建完整学习观察流 / Build complete learning observation feed.

    返回最近 N 条观察和经验教训，以及摘要统计。
    Returns the last N observations and lessons, plus summary statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    observations = ls_records.get("observations", [])
    lessons = ls_records.get("lessons", [])

    # 取最近 N 条，按最新在前排列 / Take last N, newest first
    obs_recent = list(reversed(observations[-_MAX_RECENT_ENTRIES:]))
    les_recent = list(reversed(lessons[-_MAX_RECENT_ENTRIES:]))

    return {
        "observations_recent": obs_recent,
        "lessons_recent": les_recent,
        "observation_summary": copy.deepcopy(ls.get("observation_summary", {})),
        "memory_state": copy.deepcopy(ls.get("memory", {})),
        "totals": {
            "total_observations": len(observations),
            "total_lessons": len(lessons),
            "total_hypotheses": len(ls_records.get("hypotheses", [])),
            "total_experiments": len(ls_records.get("experiments", [])),
            "total_manual_notes": len(ls_records.get("manual_notes", [])),
        },
    }


def build_learning_experiments(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建实验队列完整视图 / Build complete experiment queue view.

    包含所有实验、关联假设和待审批统计。
    Includes all experiments, linked hypotheses, and pending approval statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    experiments = ls_records.get("experiments", [])
    hypotheses = ls_records.get("hypotheses", [])

    # 统计待审批数 / Count pending approvals
    pending = sum(1 for e in experiments if e.get("status") == "pending_approval")

    return {
        "experiments": list(reversed(experiments[-_MAX_RECENT_ENTRIES:])),
        "hypotheses": list(reversed(hypotheses[-_MAX_RECENT_ENTRIES:])),
        "pending_approval_count": pending,
        "approval_required": ls.get("experiments", {}).get("approval_required", True),
    }
