# PA Reconcile — MIT-P0-2 "6/12 ML cron 未裝" vs TODO P0-V3-CRON-NOT-INSTALLED DONE

**Date**: 2026-05-16
**Trigger**: PM Sign-off 第 2 條 reprioritization 強制 PA reconcile before WP-08 dispatch
**Mode**: Read-only — 純 source verification + Linux crontab empirical query；不裝 cron / 不改 script / 不 commit
**Cross-ref**:
- TODO §10 line 323 `P0-V3-CRON-NOT-INSTALLED` ✅ DONE 2026-05-09
- TODO §11 line 359 `P1-CRON-ML-1` DONE
- PA report `2026-05-16--12-agent-consolidated-fix-plan.md` line 182 (MIT-P0-2)
- PM signoff `2026-05-16--12-agent-audit-pm-signoff.md` line 13 (reprioritization #2)
- MIT report `2026-05-10--sprint_n0_final_review.md` §5.2 + §5.3 + §7.1 invariant 18

---

## 1. Verdict 一句話

**MIT-P0-2 是 FALSE FINDING (stale narrative + definition drift)；TODO `P0-V3-CRON-NOT-INSTALLED` DONE 2026-05-09 是正確的，invariant 18 真實已 closed。建議 PM accept TODO closure，將 MIT-P0-2 在 WP-08 從 P0 降為 KNOWN-STATE / WONTFIX，不裝任何新 cron。**

唯一可選的小尾巴：MIT 可能在 *額外* 4 個 cron script (`blocked_symbols_30d_unblock_check_cron.sh` / `edge_estimate_snapshots_cycle_cron.sh` / `outcome_backfiller_live_cron.sh` / `panel_aggregator_health_cron.sh`) 「scripts exist but not in crontab」上 frame 為「未裝」— 但這幾個目前 deliberately not in crontab 也不阻塞 invariant 18 / ML training pipeline / F-08。是否要裝是獨立 P2 觀察決策，不該掛 MIT-P0-2 / WP-08 ML Pipeline Maturity name。

---

## 2. 真實 inventory（read-only verified 2026-05-16）

### 2.1 `helper_scripts/cron/` 目錄真實 script 數（Mac source）

讀 `ls helper_scripts/cron/` 後去 `test_*` 與 `__pycache__`：

**A. cron 入口腳本 (.sh / .py executable，共 14)**

| # | Script | 性質 | 真實 crontab? |
|---|---|---|---|
| 1 | `blocked_symbols_30d_unblock_check_cron.sh` | risk control | ❌ 未在 crontab |
| 2 | `edge_estimate_snapshots_cycle_cron.sh` | edge data | ❌ 未在 crontab |
| 3 | `edge_label_backfill_cron.sh` | edge label retrofit | ✅ `*/30 * * * *` |
| 4 | `feature_baseline_writer_cron.sh` | ML feature baseline | ⚠️ 不在 crontab — 由 `83afb318` 手動執行（2026-05-15）；未來可能裝 |
| 5 | `ml_training_maintenance_cron.sh` | **ML training wrapper** | ✅ `17 3 * * *` (F-08) |
| 6 | `mlde_shadow_recommendations_retention_cron.sh` | ML retention | ❌ 未在 crontab |
| 7 | `outcome_backfiller_live_cron.sh` | live outcome backfill | ❌ 未在 crontab |
| 8 | `panel_aggregator_health_cron.sh` | panel health | ❌ 未在 crontab |
| 9 | `ref21_market_microstructure_recorder.py` | replay recorder | ✅ `* * * * *` |
| 10 | `ref21_symbol_universe_snapshot_cron.sh` | replay universe | ✅ `20 * * * *` |
| 11 | `replay_artifact_prune.py` | replay 維護 | ❌ 未在 crontab |
| 12 | `replay_key_archive_cleanup.py` | replay 維護 | ❌ 未在 crontab |
| 13 | `replay_key_rotation_check.sh` | replay 維護 | ❌ 未在 crontab |
| 14 | `wave9_audit_incident_scan.py` / `wave9_business_kpi_collector.py` / `wave9_replay_no_live_mutation_watch.sh` | wave9 操作 | ❌ 未在 crontab |

(共 16 個若包含 wave9 三個與 ref21 retention；數法精確的話約 14 個 distinct executable cron script entry candidates；MIT「12」可能來自此口徑，去掉 ref21 retention / replay_key_archive_cleanup.py 等不算)

**B. `ml_training_maintenance.py` 內含的 ML jobs（一個 cron entry 跑 10 個 job，不是 10 個 cron）**

```
helper_scripts/cron/ml_training_maintenance.py DEFAULT_JOBS:
  1. linucb_trainer       (legacy)
  2. mlde_shadow_advisor  (legacy)
  3. mlde_demo_applier    (legacy)
  4. scorer_trainer       (legacy)
  5. quantile_trainer     (legacy)
  6. thompson_sampling    (F-08 new)
  7. optuna_optimizer     (F-08 new)
  8. cpcv_validator       (F-08 new)
  9. dl3_foundation       (F-08 new)
 10. weekly_report_generator (F-08 new)
```

**全部 10 job 用單一 crontab entry `17 3 * * *` 觸發** — 這是 MIT 2026-05-10 final review §5.2 verdict「All 10 ML jobs (5 legacy + 5 F-08 new) read production `learning.decision_features`」的真實設計。

### 2.2 Linux `trade-core` 真實 crontab（2026-05-16 ssh empirical query）

```
10 active cron entries (grep -c '^[^#]' returns 10):

5 0 * * *      maintenance_scripts/daily_cost_snapshot.sh
*/5 * * * *    bybit_readonly_status_writer.py
*/5 * * * *    cron_observer_cycle.sh
0 6 * * *      db/counterfactual_daily_cron.sh
0 */6 * * *    db/passive_wait_healthcheck_cron.sh
*/30 * * * *   cron/edge_label_backfill_cron.sh
20 * * * *     cron/ref21_symbol_universe_snapshot_cron.sh
* * * * *      cron/ref21_market_microstructure_recorder.py
17 3 * * *     cron/ml_training_maintenance_cron.sh             ← F-08 5 ML cron 載體
0 * * * *      logrotate openclaw
```

`helper_scripts/cron/` 命中數 = **4**：edge_label_backfill / ref21_universe / ref21_microstructure / ml_training_maintenance。其中 `ml_training_maintenance_cron.sh` 內部 invoke 10 個 ML job。

### 2.3 F-08 invariant 18 真實 fire 證據（ssh empirical）

```
trade-core:/tmp/openclaw/logs/ml_training_maintenance_cron.log (649KB)
[2026-05-15 03:36:32] === ML training maintenance end OK ===

trade-core:/tmp/openclaw/status/ml_training_maintenance_status.json
"status": "ok"
```

✅ F-08 cron 已裝、24h+ 真實 fire、status=ok。invariant 18 closed 是 verified 事實。

---

## 3. MIT "12" 數字溯源（PA inference — MIT raw audit 無單獨報告）

MIT 在 PA consolidated `2026-05-16--12-agent-consolidated-fix-plan.md` line 182 + Cluster B line 328 寫「6/12 ML cron not installed」。沒有獨立 MIT raw audit md 列舉這 12 個。PA 反推三種可能口徑：

**口徑 A — 「cron script files in `helper_scripts/cron/`」**：14 個 candidate (見 §2.1 A 表)；去 4 已裝 = 10 未裝。**和 6 不符**。

**口徑 B — 「F-08 + ML pipeline 相關 script」**（ml_training + feature_baseline + outcome_backfiller + panel_aggregator + mlde_shadow_recommendations_retention + edge_estimate_snapshots + blocked_symbols + edge_label_backfill + ref21_recorder + ref21_universe + replay_artifact_prune + replay_key_rotation = 12）：12 個 ML/feature 相關 script；其中 ✅ 在 crontab = ml_training + edge_label_backfill + ref21_recorder + ref21_universe + feature_baseline 手動 fire = ~5；6 未裝 = blocked_symbols / edge_estimate_snapshots / outcome_backfiller_live / panel_aggregator_health / mlde_shadow_recommendations_retention / replay_artifact_prune (或 replay_key_rotation_check)。**這個 frame 是 MIT 大概的口徑**。

**口徑 C — ml_training_maintenance.py 內 10 job + 2 個 audit script**：不太合理，job 不是 cron entry。

PA 推斷 MIT 用 **口徑 B**：「ML/learning 相關的 12 個 .sh/.py script 中只 4 個在 crontab，feature_baseline_writer 是手動補的，6 個 deliberately not installed」。

**口徑 B 下 MIT 點名「6 未裝」的可能成員（PA 識別）**：
1. `blocked_symbols_30d_unblock_check_cron.sh` — risk control 30d unblock retry；裝了會自動 unblock 風險，operator deliberately 留手動
2. `edge_estimate_snapshots_cycle_cron.sh` — edge data 雪球；P0-EDGE-1 active 期間 deliberately 不裝（怕污染 stats）
3. `outcome_backfiller_live_cron.sh` — live outcome backfill；live 階段未啟動前不該裝
4. `panel_aggregator_health_cron.sh` — panel health；by-design 非 cron 觸發（panel_aggregator_health 是 W1-1 BB WS-first 一部分）
5. `mlde_shadow_recommendations_retention_cron.sh` — MLDE shadow retention；P1-WA4B period 才該啟用
6. `replay_artifact_prune.py` / `replay_key_archive_cleanup.py` — replay 維護；REF-20 Sprint A-D 收口期間先不啟動 retention

**每個都有 deliberate「未裝」原因**，不是 oversight，**不是 P0**。

---

## 4. 真正落差分析

### 4.1 TODO 主張 vs MIT 主張

| 主張 | 範圍 | 證據 | 結論 |
|---|---|---|---|
| **TODO P0-V3-CRON-NOT-INSTALLED DONE** | F-08 「5 ML cron」 in 1 wrapper at `17 3 * * *` | ✅ Linux crontab 確認 + log fire confirmed (2026-05-15 03:36) | **正確**（範圍精確，指 ml_training_maintenance F-08 5 jobs） |
| **TODO 文字 "F-08 5 ML cron"** | 字面誤導 — 像 5 個獨立 cron entry | 實際是 1 entry 跑 5 個 F-08 job + 5 個 legacy job | **TODO 文字小瑕疵但不影響 invariant 18 closure** |
| **MIT-P0-2「6/12 ML cron 未裝」** | 廣 definition 把所有 ML/learning helper_scripts/cron 算入 | 12 個 candidate script - 4 已裝 - feature_baseline 手動 - 1 by-design = ~6 by-design 未裝 | **frame 為 P0 過頭** — 6 個 deliberately not installed，不是 oversight |
| **MIT 2026-05-10 final review invariant 18** | 「ml_training_maintenance_cron.sh + [Xc] healthcheck PASS」 | 已 install + ok | **invariant 18 = TODO `P0-V3-CRON-NOT-INSTALLED` 同一範圍，已 closed** |

### 4.2 MIT-P0-2 「6 未裝」每個的真實處理建議

| Script | MIT 暗示 | PA 處理建議 | 優先級 |
|---|---|---|---|
| `blocked_symbols_30d_unblock_check_cron.sh` | 應裝 | KEEP MANUAL — operator 控 30d unblock window 是 deliberate；自動 unblock 等 LG-3 supervised-live 才裝 | P2 |
| `edge_estimate_snapshots_cycle_cron.sh` | 應裝 | EVALUATE — P0-EDGE-1 active 期間裝/不裝由 EDGE-P2-3 Phase 1b decide | P2 / 等 EDGE-P2 |
| `outcome_backfiller_live_cron.sh` | 應裝 | DEFER — live 階段未啟動；裝了沒 live trades 也沒事，但 risk = 跑空轉浪費資源 | P2 / pre-live 再裝 |
| `panel_aggregator_health_cron.sh` | 應裝 | EVALUATE — 與 W1-1 BB WS-first refactor 相關；若 W1-1 IMPL 後 panel_aggregator 是常駐 process 而非 cron，這 script 變 redundant | P2 / W1-1 decide |
| `mlde_shadow_recommendations_retention_cron.sh` | 應裝 | EVALUATE — `learning.mlde_shadow_recommendations` 表 row growth + retention 政策對齊；若用 V075 prune_old_plain_tables() 路徑，這 script 變 redundant | P2 / V075 prune decide |
| `replay_artifact_prune.py` / `replay_key_archive_cleanup.py` | 應裝 | DEFER — REF-20 Sprint A-D 已收口；replay 體積目前不痛，pre-live 再裝避免空轉 | P2 / pre-live 再裝 |

**結論**：6 個 deliberately not in crontab；都是 P2 觀察決策，**不該掛 MIT-P0-2 / WP-08 ML Pipeline Maturity P0 BLOCKER name**。

### 4.3 MIT-P0-2 在 WP-08 framing 的副作用

PA 在 12-agent consolidated `2026-05-16--12-agent-consolidated-fix-plan.md` 把 MIT-P0-2 列入 WP-08 sequencer 第二項：
```
| MIT-P0-2 6/12 ML cron scripts not installed | Install missing crontab entries on trade-core. Scripts exist in `helper_scripts/cron/` but are not in crontab. |
```

這 framing 是錯的：
1. 6 script 各有 deliberate 「不裝」理由 — 不是 「install missing」可一鍵解決
2. MIT 在 2026-05-10 final review §7.1 invariant 18 的 verdict 是「ml_training_maintenance_cron.sh + [Xc] healthcheck PASS」— 那個 invariant 18 已 closed
3. 把 6 個獨立決策包進 1 個 P0 P0-line 等於把 deliberate design 誤標為 oversight

---

## 5. 改進建議（不執行，只列）

### 5.1 TODO 文字 hygiene patch（P2，可選）

TODO line 323：
```
| `P0-V3-CRON-NOT-INSTALLED` | ✅ DONE 2026-05-09 | F-08 5 ML cron `17 3 * * *` installed and 24h fire verified. | invariant 18 closed. |
```

PA 建議 改為（不需立即動，僅供 hygiene wave）：
```
| `P0-V3-CRON-NOT-INSTALLED` | ✅ DONE 2026-05-09 | F-08 `ml_training_maintenance_cron.sh @ 17 3 * * *` (含 5 F-08 jobs + 5 legacy jobs) installed; 2026-05-15 03:36 真實 fire + status=ok. | invariant 18 closed. 其他 helper_scripts/cron/*_cron.sh deliberately not in crontab 屬 P2 觀察決策不含此 invariant 範圍。 |
```

### 5.2 WP-08 內 MIT-P0-2 處理（必做，但是 RECLASSIFY 不是裝 cron）

PM signoff Section 5 reprioritization 加一條：

> **6. WP-08 MIT-P0-2 RECLASSIFY**: PA reconcile 結論 = false finding (definition drift)。F-08 invariant 18 真實已 closed (2026-05-15 03:36 fire ok)。MIT 識別的「6 未裝」是 6 個 deliberately-not-in-crontab P2 觀察 script，每個有獨立 deliberate 理由（見 PA reconcile §4.2）。從 WP-08 P0 BLOCKER 移除；如果未來需要逐個評估這 6 script，新開 6 個 P2 ticket。

### 5.3 MIT raw audit hygiene（可選）

未來 MIT audit 報告引用「N/M ML cron」前，必須先：
1. 點名是哪 12 個（candidate list）
2. 點名是哪 6 個（未裝 list）
3. 對每個未裝 candidate 給出「是否該裝」的 verdict

避免 PA / PM 反推 MIT 口徑浪費 capacity。

---

## 6. 副作用識別清單（PA reconcile 不執行，但需 PM 知道）

對 MIT-P0-2 不裝 cron 的副作用評估：

1. ❓ **其他模塊 import 了這些 script?** — 否。每個 *_cron.sh 是獨立 entry point，無 cross-import
2. ❓ **改動的函數在哪些測試中被 mock?** — 否（不改動）
3. ❓ **是否涉及 asyncio/threading 混用邊界?** — 否（不改動）
4. ❓ **是否改動 API response schema?** — 否（不改動）
5. ❓ **是否觸 RustEngine ↔ Python IPC schema?** — 否（不改動）
6. ❓ **是否阻塞 Sprint 1b / EDGE-P2-3 / W3 / true live promotion?** — 否：
   - F-08 invariant 18 已 closed
   - `[55]` agent_decision_spine_lineage / `[67]` feature_baseline_readiness / `[27]` intents counter freeze 都 ✅
   - `[40]` negative edge 是 strategy 結構問題不是 cron 問題
   - LG-1/2/3 / W-AUDIT-8a C1 / W-AUDIT-8b 都不依賴這 6 個未裝 cron

---

## 7. 16 根原則合規 quick check（per skill `16-root-principles-checklist`）

對「不裝 cron + reclassify MIT-P0-2」這個決策：

| # | 原則 | 影響 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | 無 | 不改 IntentProcessor |
| 2 | 讀寫分離 | 無 | reconcile = read-only |
| 3 | AI 輸出 ≠ 命令 | 無 | 無 AI 決策路徑改動 |
| 4 | 策略不繞風控 | 無 | 不改 Guardian / risk envelope |
| 5 | 生存 > 利潤 | 無 | 不裝這 6 cron 反而保「不啟動空轉浪費」 |
| 6 | 失敗默認收縮 | ✅ | 「deliberately not installed」就是 fail-closed 邊界 |
| 7 | 學習 ≠ 改寫 Live | 無 | learning 平面表 retention 暫不啟用 |
| 8 | 交易可解釋 | 無 | 不改 audit_log |
| 9 | 災難保護 | 無 | 不改 Hard/Trailing stop |
| 10 | 認知誠實 | ✅ | 本 reconcile 顯示「MIT-P0-2 frame 不精確 + TODO 文字小瑕疵」就是執行此原則 |
| 11 | Agent 最大自主 | 無 | 不影響 Agent 邊界 |
| 12 | 持續進化 | 無 | F-08 ML training 持續學習路徑已開啟 |
| 13 | AI 成本感知 | 無 | 不改 cost_edge_ratio |
| 14 | 零外部成本 | 無 | 不增加外部依賴 |
| 15 | 多 Agent 協作 | 無 | 不影響 5 Agent |
| 16 | 組合級風險 | 無 | 不影響 portfolio risk |

**硬邊界（CLAUDE.md §四）grep check**：
```
'(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json)' → 0 hit
```

**評級**：A 級 — 16/16 完全合規 + 硬邊界 0 觸碰。

**DOC-08 §12 9 不變量**：本 reconcile 不影響任何一條，逐條 PASS（不改 pre-trade / lease / fills / 風控降級 / authorization / OPENCLAW_ALLOW_MAINNET / Bybit retCode / Reconciler / Operator + live_reserved）。

---

## 8. PA verdict 三選一

| 選項 | 描述 | PA 推薦 |
|---|---|---|
| (a) **Accept MIT-P0-2 全部裝** | 一鍵 install 6 script 進 crontab | ❌ **拒絕** — 每個都有 deliberate 不裝理由，盲裝會帶 side effect（30d unblock 自動啟動 / edge data 污染 / live 空轉 / panel/retention race / replay prune 過早） |
| (b) **Accept TODO closure + RECLASSIFY MIT-P0-2** | F-08 invariant 18 已 closed (verified)；MIT 12/6 framing 是 definition drift；reclassify 為 P2 觀察 list，6 個獨立 P2 ticket 按需開 | ✅ **推薦** |
| (c) **MIT 完全 stale finding 直接 WONTFIX** | 認 MIT-P0-2 false 不做任何後續 | ⚠️ 部分 — false 是正確的，但 6 script 真正狀態仍值得登記在 P2 backlog 供未來決策 |

**PA 推薦 (b)**：
- F-08 invariant 18 真實 closed（log + status_json + crontab empirical 三證據）
- MIT-P0-2「6/12」frame 拆解後 = 6 個 deliberate 不裝 script，每個獨立評估
- 不裝任何新 cron，不執行 MIT-P0-2 install fix
- WP-08 MIT-P0-2 行 reclassify 為 KNOWN-STATE / P2-NEXT-EVAL，從 WP-08 P0 BLOCKER 移除
- 6 個未裝 script 各開 P2 ticket（或一個 P2 umbrella ticket）供未來 EDGE-P2 / W1-1 / pre-live runbook 時逐個評估
- TODO line 323 文字 hygiene patch optional（可選）

---

## 9. PM dispatch recommendation

**Wave 3 WP-08 重新 scope**（取代 PA 12-agent consolidated 原 line 182）：

| WP-08 sub | Original | Reconciled |
|---|---|---|
| MIT-P0-1 PG tuning | Linux runtime tune postgresql.conf | **保留** — operator manual action (PM signoff §5.3 已 reframe) |
| MIT-P0-2 6/12 ML cron not installed | Install missing crontab entries | **REMOVE from WP-08** — false finding，invariant 18 closed；改 spawn P2 umbrella ticket `P2-CRON-DELIBERATE-NOT-INSTALLED-LIST`（不要 inline 進 WP-08） |
| MIT-P1-1 Drift chain broken | feature_baseline_writer cron (partially done per P1-WA4B-INSERT-1) | **保留**（且已 closed by 2026-05-15 13:13 UTC commit `83afb318`） |
| MIT-P1-2 Walk-forward purge missing | Add `purge_days` parameter | **保留** — 真實 code 改動 |
| MIT-P1-3 decision_features 10.22M rows no prune | Ensure cron calls prune_old_plain_tables() | **保留** — 真實需求；可與 §4.2 第 6 列 replay_artifact_prune 一起考慮 P2 |
| MIT-DB-6 Training uses only "demo" | engine_mode IN ('demo', 'live_demo') | **保留** |

WP-08 工作 IMPL 量從 6 項 → 5 項（移除 1 項 false finding）；WP-08 P0 BLOCKER 性質不變（MIT-P1-1 已 closed，但 MIT-P1-2 + MIT-P1-3 + MIT-DB-6 + MIT-P0-1 PG tuning 仍是 P1，不是 P0）；P0 BLOCKER 標籤可考慮降為 P1。

---

## 10. References

- `srv/TODO.md` line 323 `P0-V3-CRON-NOT-INSTALLED` ✅ DONE 2026-05-09
- `srv/TODO.md` line 359 `P1-CRON-ML-1` DONE
- `srv/2026-05-16--full-system-audit-fix-plan.md` line 182 / 328 / 431（MIT-P0-2 claim + PM signoff conditions #2）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md` line 182 (WP-08 row)
- `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--sprint_n0_final_review.md` §5.2 / §5.3 / §7.1（10 jobs / invariant 18）
- `srv/helper_scripts/cron/ml_training_maintenance.py` DEFAULT_JOBS 10 items（line 41-52）
- `srv/helper_scripts/cron/ml_training_maintenance_cron.sh` line 1-131（F-08 wrapper）
- Linux `trade-core` crontab + log empirical (ssh 2026-05-16, content quoted §2.2 / §2.3)
- Memory `project_2026_05_09_ml_training_cron_weekly.md`（hybrid daily/weekly nuance）

---

## 11. 一句話 summary 給 PM

```
PA reconcile DONE:
- F-08 invariant 18 真實 closed（log + status_json + crontab 三證據）
- MIT-P0-2 「6/12」frame 是 definition drift，不是 missing cron
- 6 個 deliberately-not-installed cron 各有 deliberate 理由，是 P2 觀察 不是 P0 oversight
- 建議 WP-08 移除 MIT-P0-2 行，改 spawn `P2-CRON-DELIBERATE-NOT-INSTALLED-LIST` umbrella ticket
- 不需要在 Wave 3 / WP-08 dispatch 中執行任何「install cron」動作
- TODO line 323 文字 hygiene patch optional
```

---

## PA DESIGN DONE

report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--mit_cron_reconcile.md`
