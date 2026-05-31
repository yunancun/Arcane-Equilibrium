"""
MODULE_NOTE
模塊用途：M4 Pattern Miner Stage 1 helper package（per W1-B spec §5.2）。
   提供 5 source ingest + statistical orchestration + leakage validator +
   DRAFT writeback to learning.hypotheses (V100+V103 EXTEND 6 column)。

主要 entry：
   - pattern_miner_stage_1.py: 主 entry（cron 呼）
   - stage1_production_runner.py: non-dry-run source read / candidate compute / gated DRAFT writeback
   - sources/*.py: 4 PG loader + 1 stub
   - algorithms/*.py: cross-correlation + event-window + Bonferroni K=2500
   - attribute_enforcer.py: 6 attribute gate
   - feature_engineering_validator.py: shift(1) leak-free 三語言驗
   - draft_writer.py: V103 EXTEND DRAFT writeback

依賴：psycopg2-binary (Linux runtime) / pandas / scipy / numpy。

硬邊界（per W1-B spec §0 + §5.2）：
   - I-2 黑名單 method 禁用：HMM / Markov-switching / GARCH（grep 必 0 hit）
   - I-3 Bonferroni K=2500：所有 sub-test 必經 algorithms.bonferroni
   - I-4 N>=30 硬 gate
   - I-5 DRAFT writeback 不 auto-promote past 'preregistered'；analysis lane
     'exploratory' must map to PG status 'draft'
   - engine_mode IN ('live', 'live_demo')：禁 'paper'（per CLAUDE.md §四 + memory
     `project_engine_mode_tag_live_demo`）
"""

__version__ = "0.2.0-stage1-production-runner"
