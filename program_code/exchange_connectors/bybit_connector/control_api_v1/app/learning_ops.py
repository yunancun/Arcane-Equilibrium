from __future__ import annotations

"""
MODULE_NOTE (中文):
  學習系統操作門面模塊（re-export）。原 1624 行已拆分為三個子模塊：
  - learning_records.py：觀察/經驗/假設/實驗的 CRUD 寫操作
  - learning_auto_pipeline.py：自動掃描/審核包生成/審核決策/AI 諮詢
  - learning_queries.py：審核隊列/觀察流/實驗隊列的只讀查詢

  本文件僅做 re-export，保持向後兼容。新代碼應直接 import 子模塊。

MODULE_NOTE (English):
  Learning system operations facade module (re-export). The original 1624 lines
  have been split into three sub-modules:
  - learning_records.py: observation/lesson/hypothesis/experiment CRUD writes
  - learning_auto_pipeline.py: auto scan / review packet generation / review decisions / AI consultation
  - learning_queries.py: review queue / observation feed / experiment queue read-only queries

  This file only re-exports for backward compatibility. New code should import sub-modules directly.
"""

# ── learning_records: CRUD 寫操作 / CRUD write operations ──
from .learning_records import (  # noqa: F401
    apply_experiment_approval,
    apply_experiment_completion,
    apply_hypothesis_verdict,
    apply_learning_experiment,
    apply_learning_hypothesis,
    apply_learning_lesson,
    apply_learning_observation,
)

# ── learning_auto_pipeline: 自動管線 + 審核決策 / Auto pipeline + review decisions ──
from .learning_auto_pipeline import (  # noqa: F401
    apply_ai_consultation,
    apply_auto_generate,
    apply_review_decision,
    generate_auto_hypotheses,
    generate_auto_lessons,
    generate_auto_observations,
)

# ── learning_queries: 只讀查詢 / Read-only queries ──
from .learning_queries import (  # noqa: F401
    build_learning_experiments,
    build_learning_feed,
    build_review_queue,
)
