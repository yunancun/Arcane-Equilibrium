"""Phase 1b Close-Maker-First standalone healthcheck scripts.

MODULE_NOTE:
  本 package 是 AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1 規定的 Phase 1b
  close-maker-first runtime 觀察腳本集合（[62][63][64][65][66]），對應 QA
  T+6h / T+24h post-deploy verification 流程。設計目標 = standalone CLI
  （不走 passive_wait_healthcheck 6h cron pipeline）：operator 或 QA 可單
  獨跑某一 healthcheck，立即拿到 PG 真實 sample 上的 Wilson-CI / NULL
  ladder / backoff duration / reject 樣本 / pre-stopout rate verdict。

  與 ``helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py``
  ([70][71][72][73][74] slot) 關係：
    - 兩者讀同一張 ``trading.fills`` V094 schema + 同一份 enum allowlist
    - passive_wait 是 cron 自動化、聚合多 check 結果的常駐 healthcheck
    - 本 package 是 PM/QA 手動驗收用的薄殼：純 SQL + Wilson / 雙閾值計算
      + JSON 輸出
  兩者 SQL / 閾值故意對齊，若未來治理需要可在 _common 抽共享層；現階段保留
  獨立性以避 cron 故障影響 PM 24h 驗收路徑。

  Slot 編號邊界（2026-05-21 R2 釐清，避 namespace 混淆）：
    - canary/healthchecks/（本 package）：[62][63][64][65][66]
    - passive_wait_healthcheck/：[70][71][72][73][74]
    - 兩 namespace 物理分離但 PM/operator 看 mixed report 可能誤判同一
      slot，故新加 healthcheck 必走未被佔用 slot；[66] 之選定即源於此。

  入口 5 個腳本（與 spec §8.1 + AMD §4.1 編號對齊；[66] 為 FA round 1 #5
  follow-up 補加）：
    - 62_close_maker_fill_rate.py — close-maker-first maker fill rate
      (Consensus-MF-2)；R2 加 ``--stratify hour|dow|both`` 子維度分桶
      （AC-20 OBS-2）
    - 63_close_maker_fallback_audit.py — fallback reason NULL ladder
    - 64_close_maker_rate_limit_pause_duration.py — 10403/10429 backoff
      duration 量度
    - 65_reject_sample_healthcheck.py — reject 樣本量度
    - 66_close_maker_pre_stopout_rate.py — close-maker-first 「來得及」
      健康度量（P1-OBS-PRE-STOPOUT-RATE，2026-05-21 FA round 1 #5；
      閾值 0.10 PASS / 0.30 FAIL；R2 從 [71] rename 避碰）
  共享 helper：_common.py（PG conn + Wilson CI + JSON formatter + argparse）
"""
