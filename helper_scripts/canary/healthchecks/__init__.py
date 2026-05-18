"""Phase 1b Close-Maker-First standalone healthcheck scripts.

MODULE_NOTE:
  本 package 是 AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1 規定的 Phase 1b
  close-maker-first runtime 觀察腳本集合（[62][63][64][65]），對應 QA T+6h /
  T+24h post-deploy verification 流程。設計目標 = standalone CLI（不走
  passive_wait_healthcheck 6h cron pipeline）：operator 或 QA 可單獨跑某一
  healthcheck，立即拿到 PG 真實 sample 上的 Wilson-CI / NULL ladder /
  backoff duration / reject 樣本 verdict。

  與 ``helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py``
  ([70][71][72][73][74] slot) 關係：
    - 兩者讀同一張 ``trading.fills`` V094 schema + 同一份 enum allowlist
    - passive_wait 是 cron 自動化、聚合多 check 結果的常駐 healthcheck
    - 本 package 是 PM/QA 手動驗收用的薄殼：純 SQL + Wilson 計算 + JSON 輸出
  兩者 SQL / 閾值故意對齊，若未來治理需要可在 _common 抽共享層；現階段保留
  獨立性以避 cron 故障影響 PM 24h 驗收路徑。

  入口 4 個腳本（與 spec §8.1 + AMD §4.1 編號對齊）：
    - 62_close_maker_fill_rate.py
    - 63_close_maker_fallback_audit.py
    - 64_close_maker_rate_limit_pause_duration.py
    - 65_reject_sample_healthcheck.py
  共享 helper：_common.py（PG conn + Wilson CI + JSON formatter + argparse）
"""
