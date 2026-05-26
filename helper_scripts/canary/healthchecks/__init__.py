"""Phase 1b Close-Maker-First standalone healthcheck scripts.

MODULE_NOTE:
  本 package 是 AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1 規定的 Phase 1b
  close-maker-first runtime 觀察腳本集合（[62][63][64][65][66][67][69]），
  對應 QA T+6h / T+24h post-deploy verification 流程。設計目標 = standalone
  CLI（不走 passive_wait_healthcheck 6h cron pipeline）：operator 或 QA
  可單獨跑某一 healthcheck，立即拿到 PG 真實 sample 上的 Wilson-CI / NULL
  ladder / backoff duration / reject 樣本 / pre-stopout rate / liquidation
  pulse freshness / halt-session root-cause recurrence verdict。

  與 ``helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py``
  ([70][71][72][73][74] slot) 關係：
    - 兩者讀同一張 ``trading.fills`` V094 schema + 同一份 enum allowlist
    - passive_wait 是 cron 自動化、聚合多 check 結果的常駐 healthcheck
    - 本 package 是 PM/QA 手動驗收用的薄殼：純 SQL + Wilson / 雙閾值計算
      + JSON 輸出
  兩者 SQL / 閾值故意對齊，若未來治理需要可在 _common 抽共享層；現階段保留
  獨立性以避 cron 故障影響 PM 24h 驗收路徑。

  Slot 編號邊界（2026-05-21 釐清 / 2026-05-25 operator rename [67]→[80] 後再釐清）：
    - canary/healthchecks/（本 package）：[62][63][64][65][66][68][69][80]
      （原 [67] 2026-05-25 rename 為 [80] 避與 passive_wait_healthcheck
      runner.py:1181 ``[67] feature_baseline_readiness`` 字面衝突）
    - [68] 由 P2-PHYS-LOCK-72-HEALTHCHECK 占用（per TODO §6.1 row 給 slot
      選項 [68]/[69]/[76]，[69] 已被 P1-HALT-TRIGGER 占用故 PA 拍板取 [68]）
    - [69] 由本次 P1-HALT-TRIGGER 占用（halt_session_root_cause_recurrence）
    - [80] liquidation_pulse_freshness（2026-05-25 由 [67] rename；緊鄰
      passive_wait [70-79] block 之後；未來新 canary slot 建議從 [81] 起遞增）
    - passive_wait_healthcheck/：[67] feature_baseline_readiness +
      [70][71][72][73][74] close_maker_audit + [75][76][77][78][79]
      cron_heartbeat
    - 兩 namespace 物理分離但 PM/operator 看 mixed report 可能誤判同一
      slot，故新加 healthcheck 必走未被佔用 slot；canary [68] vs
      passive_wait [68] = 不同 domain（前者 phys_lock gate4 / 後者
      portfolio_resting），result payload 強制標 ``namespace="canary"``
      field 供 dashboard 區分

  入口 8 個腳本（與 spec §8.1 + AMD §4.1 編號對齊；[66] 為 FA round 1 #5
  follow-up 補加；[80] W-AUDIT-8a（原 [67] 2026-05-25 rename）；
  [68] P2-PHYS-LOCK-72-HEALTHCHECK 2026-05-21；[69] P1-HALT-TRIGGER
  2026-05-21）：
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
    - 80_liquidation_pulse_freshness.py — W-AUDIT-8a C1-LIQ-WRITER
      acceptance #3（topic freshness + row volume + symbol coverage
      + parse guard）；2026-05-25 由 [67] rename 為 [80] 避 passive_wait
      [67] feature_baseline_readiness 衝突
    - 68_phys_lock_gate4_distribution.py — P2-PHYS-LOCK-72-HEALTHCHECK
      (2026-05-21 FA C6 OQ-C6-2 follow-up)；phys_lock gate4 trigger 分布
      觀察，**區分 0-fire-natural vs 0-fire-router-bug**；FAIL =
      stale_roc_neg alive 但 close path 不通 / WARN = giveback 多但
      stale_roc_neg 全 0 / PASS = policy alive + close path 通；daily
      cron 04:00 UTC（spec docs/execution_plan/2026-05-21--p2_phys_lock_
      72_healthcheck_spec.md）
    - 69_halt_session_root_cause_recurrence.py — P1-HALT-TRIGGER-
      ROOT-CAUSE-INVESTIGATION-1 passive-wait healthcheck；監測 v56
      P0 §1.4 五個候選假設 (a)-(e) 在下次自然事件是否仍出現 metric
      < threshold 的 pattern（v56 不通數學的再現）；WARN = 模式相符
      v56 / FAIL = forensic halt_audit.log 對應 row 缺
  共享 helper：_common.py（PG conn + Wilson CI + JSON formatter + argparse）
"""
