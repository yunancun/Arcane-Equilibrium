"""
MODULE_NOTE
模塊用途：Sprint 2 Alpha Tournament Stream A 2 candidate
   (funding_short_v2 / liquidation_cascade_fade) 14d demo evidence accumulation
   helper package。per W2-A finalize §3 + §6 design。

主要 entry：
   - attribution_daily.py: daily cron @02:30 UTC fire；14d bucket-split SQL +
     Wilson CI 95% lower bound projection + Bonferroni K=2 alpha 調整 +
     sample size cumulative projection；stdout JSON log。
   - tournament_orchestrator.py: Sprint 3+ M11 counterfactual replay integration
     placeholder（Sprint 2 stub return success）。

依賴：psycopg2-binary (Linux runtime)；本 helper package 不引 SQLAlchemy / pandas，
   走 read-only SELECT 路徑（不寫 PG）。

硬邊界：
   - per ADR-0026 + V101 ENUM：所有 SELECT WHERE track = 'direct_exploit'
     （hand-coded Rust strategy 必 = direct_exploit；非 'alpha_short_carry' /
     'alpha_microstructure_fade' 虛構 track ENUM）。
   - per V100 + V103 EXTEND actual schema：DRAFT writeback target table =
     learning.hypotheses（非 learning.m4_hypotheses_extended，該 table 不存在）。
   - per Sprint N+0 closure attribution_chain_ok 100% 範式：bucket-split SQL
     必 WHERE attribution_chain_ok = TRUE。
   - per memory project_engine_mode_tag_live_demo：engine_mode IN ('demo',
     'live_demo')；不單獨用 ='demo'。
   - read-only：本 package 不 INSERT 任何 PG row；DRAFT writeback 由 W2-F MIT
     post-IMPL audit 手動跑 §3.5 INSERT pattern（per W2-A finalize）。
"""

__version__ = "0.1.0-w2b-scaffold"
