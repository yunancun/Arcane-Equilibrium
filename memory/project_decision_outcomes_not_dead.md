---
name: decision_outcomes 不是 dead (2026-04-21 RCA)
description: trading.decision_outcomes 113k 條 max_favorable/max_adverse 全 NULL 不是 writer 死亡；writer 活躍（Rust outcome_backfiller 5min tick + main spawn）；根因 = market.klines 歷史稀疏；下游 LinUCB 仍用，不可刪
type: project
originSessionId: aaf4cf28-cfa5-48d0-9847-f0c087dbeed8
---
# trading.decision_outcomes 不是 dead（2026-04-21 RCA 結論）

**原 TODO `DECISION-OUTCOMES-DEAD-1` → 更正 reframed as `ATTEMPT-LOG-NOT-DEAD-1`**（詳 `docs/worklogs/2026-04-21--decision_outcomes_rca.md`）

## 關鍵事實

- **Writer 活躍**：`rust/openclaw_engine/src/database/outcome_backfiller.rs` + `tasks.rs::spawn_outcome_backfiller` + `main.rs:873` 已 spawn。5 min tick loop，每次 LIMIT 200 對 25h+ 前的 decision_context_snapshots 回填。
- **113k NULL 根因 = 上游 `market.klines` 稀疏**：MARKET-KLINES-STALE-1 2026-04-18 只修 forward-going，歷史空洞未回填。LATERAL 子查詢無 kline → 5 個 outcome + 兩個 excursion 同步 NULL。
- **`outcome_backfilled = TRUE` 語意是「已嘗試」** 非「資料完整」；是 schema 設計的隱性歧義，但下游 consumer 本來就 `WHERE outcome_1h IS NOT NULL` 自然過濾，無行為 bug。
- **與 `learning.exit_features` 語意正交**：decision_outcomes = entry-anchored forward-return **label**（1m/5m/1h/4h/24h），exit_features = exit-anchored 7 維 trajectory **feature**；**不互相取代**。
- **下游 consumer 仍用**：`linucb_trainer.py:215` / `linucb_shadow_compare.py:188` JOIN 取 label；**絕不可刪 schema**。

## 2026-04-18 設計文件誤判已更正

`docs/worklogs/2026-04-18-2--exit_features_table_design.md:15-18` 寫「decision_outcomes ... 該表已 dead，沿用會混淆」— 此「dead」判斷是當時 RCA 前誤判；本次 RCA 更正。

## 未來遇到這個表時避免重蹈誤判

1. 看到 `max_favorable/max_adverse` 全 NULL 不要立刻懷疑 writer 死 — 先查 `market.klines` 覆蓋率
2. `outcome_backfilled = TRUE` 不等於「資料完整」，是「已嘗試」
3. 考慮廢棄此表前必查 `grep -r 'decision_outcomes' program_code/` 確認無 LinUCB 類 consumer 依賴

## Linux DB 驗證一次性 SQL

```sql
SELECT
  COUNT(*) AS total,
  COUNT(max_favorable)  AS mf_non_null,
  COUNT(outcome_1h)     AS o1h_non_null,
  COUNT(backfilled_ts)  AS bt_non_null,
  engine_mode,
  MIN(backfilled_ts), MAX(backfilled_ts)
FROM trading.decision_outcomes
GROUP BY engine_mode;
```
預期：`bt_non_null ≈ total` + `o1h_non_null ≪ total` → 證實 RCA 結論。
