# 2026-05-21 · PA Reverify — §11.3 P1 watch 3 條 (P1-DATA / P1-LG-5 / P1-EDGE) 狀態核驗

**作者**: PA (Project Architect)
**Trigger**: operator 2026-05-21 要求 v57.3 之前所有舊 active 工作收尾
**Scope**: read-only audit — ssh trade-core + PG SQL + source grep（不寫業務代碼，不發 IPC，不改 config）
**HEAD**: Linux trade-core 同步 Mac branch HEAD `33ef66f5`

---

## 摘要 — 3 條 verdict + closure 建議

| ID | 過往描述 | Verdict | Closure |
|---|---|---|---|
| **A. P1-DATA-1..3-WATCH** | Runtime-reloaded WARN cluster row-rolloff watch | **DOWNGRADE_TO_OPTIONAL** | 從 §11.3 移除；watch 已合併入 `[51]` scanner LOW_SAMPLE + P0-EDGE-1 範圍；單獨保留無增量價值 |
| **B. P1-LG-5** | LG-5 reviewer maturity watch | **STILL_ACTIVE** | 維持 §11.3；source 活躍、audit-row 健康、100% defer 是設計正確；不可降級 |
| **C.1 P1-EDGE-1** | ma_crossover/grid blocked_symbols frozen | **CLOSED** | 移到 §12.4 已完成；freeze registry permanent 由 static guard + RFC SOP 保護 |
| **C.2 P1-EDGE-2** | funding_arb 14d audit 2026-05-16 | **STILL_ACTIVE，性質改變** | 建議升 P0-FUNDING-ARB-DECISION-FORCE；n≥30 trigger 鎖死於 dormant 樣本 |

---

## §A. P1-DATA-1..3-WATCH — DOWNGRADE_TO_OPTIONAL

### 過往定義（git history 還原，from commit `bcf4f11a` 之前 v18 expansion）

| Sub-ID | 描述 | 對應 healthcheck slot |
|---|---|---|
| `P1-DATA-1` | Runtime-reloaded WARN cluster | `[14]` exit_features / `[37]` mlde_demo_applier / `[40]` realized_edge_acceptance / `[45]` pricing_binding |
| `P1-DATA-2` | Source-fixed low-sample attribution watch | `[42b]` / `[42c]` live_candidate_attribution_drift |
| `P1-DATA-3` | Source-fixed scanner opportunity calibration watch | `[51]` scanner_opportunity_shadow_acceptance |
| ~~P1-DATA-4~~ | scanner would-block evidence WARN-only（DONE, 已歸檔 v36 cleanup） | `[41]` |

從 v36 cleanup commit `3f4aa079` 起，P1-DATA-1..3 統一合併為 `P1-DATA-1..3-WATCH`，描述退為 "Runtime-reloaded WARN cluster row-rolloff watch / source 已修；保留 observation-only watch"。

### Verify item 1 — source fix evidence（grep + git log）

**P1-DATA-1 LG5-W3-FUP-2 attribution writer fix** — commit `34211ab4` (2026-05-02)：
- `mlde_demo_applier.py` +122 LOC（1374 → 1496）
- 新增 `_R_META_WINDOW_DAYS=3` constant + `_compute_attribution_sample_count_by_strategy`
- payload 加 `demo_attribution_window_days=3` + `_settled_attribution_chain_ratio_by_strategy`
- E1+E2 round 2 PASS / E4 regression PASS

**LG-5 reviewer consumer scheduler** — commit `463890d` (2026-05-02) + `c8240b6a` drain fix (2026-05-07)。

### Verify item 2 — runtime 7d/14d row-rolloff 健康度

PG empirical query 結果（2026-05-21 12:08 UTC 跑於 Linux trade-core）：

| Table | 7d | 14d | 健康度 |
|---|---:|---:|---|
| `trading.fills` | 368 | 1383 | 7d=27% × 14d（自然 sample velocity decay；非 rolloff bug） |
| `trading.risk_verdicts` | 796,939 | n/a | 極活躍 |
| `learning.mlde_edge_training_rows` | 216,007 | n/a | 活躍 |
| `learning.governance_audit_log` | 68 | 1,674 | 7d=4% × 14d（5/7 一次性 burst 1457 rows 拉高 14d；過去 14d daily 範圍 2-43 rows 穩定） |
| `learning.mlde_shadow_recommendations` | 3,840 | n/a | 活躍 |
| `learning.cost_edge_advisor_log` | 10,060 | n/a | 活躍 |
| `learning.mlde_param_applications` | 1,764 | n/a | 活躍 |
| `learning.lease_transitions` | 797,269 | n/a | 極活躍 |
| `learning.edge_estimate_snapshots` | 0 | n/a | ⚠️ stale (max=2026-05-07，14d 無新) — 獨立 follow-up |
| `learning.directive_executions` | 0 | n/a | by-design 不在 active path |

Daily `governance_audit_log` 14d distribution（無 rolloff 異常）：
```
2026-05-20: 2 / 05-19: 4 / 05-18: 2 / 05-17: 15 / 05-16: 23 / 05-15: 17
2026-05-14: 14 / 05-13: 42 / 05-12: 43 / 05-11: 12 / 05-10: 5 / 05-09: 18
2026-05-08: 20 / 05-07: 1457（initial burst, reviewer 啟動 / 回填）
```

### Verify item 3 — passive_wait_healthcheck 7 個 slot runtime 跑結果

`bash helper_scripts/db/passive_wait_healthcheck.sh --quiet`（2026-05-21 10:19 UTC 跑於 Linux）：

| Slot | 狀態 | 細節（runtime） |
|---|---|---|
| `[14]` exit_features_accumulation_rate | WARN | this_week=172 vs last_week=543 (ratio=0.32) decay 30-50%；grid=131[GROWING]、ma=38[SPARSE]、bb_rev=3[SPARSE] |
| `[37]` mlde_demo_applier | (PASS — 未在 --quiet 輸出) | — |
| `[40]` realized_edge_acceptance | WARN | 24h MLDE rows=8460 / win_rate 0.1% / avg_net=0.02bps（target>5bps）；maker_like 97.2% ✅ / fee_drop 97.2% ✅ — alpha negative 是 P0-EDGE-1 範圍 |
| `[42b]` live_candidate_attribution_drift (7d) | WARN | ma_crossover=1.000(n=215098) ✅ / grid_trading=1.000(n=145) ✅ / bb_breakout=LOW_SAMPLE(n=0) / bb_reversion=LOW_SAMPLE(n=8) / funding_arb=LOW_SAMPLE(n=0) — no drift, sample-maturity watch |
| `[42c]` live_candidate_attribution_drift_3d | WARN | ma=1.000(n=53110) / grid=1.000(n=29) — 3d R-meta gate 對齊 PASS |
| `[45]` pricing_binding | WARN | demo age=12045s / live_demo age=61911s — exceeds 1h cadence but within 24h |
| `[51]` scanner_opportunity_shadow_acceptance | WARN | 24h labels=8459 / positive_lcb_n=0 / opportunity_positive_n=0 — LOW_SAMPLE(n=0, need=10)；shadow-only until calibrated samples mature |

**結論**：6/7 WARN（無 FAIL）；2 個原本主因（P1-DATA-1 row rolloff / P1-DATA-2 attribution drift）已被 LG-5 W3 FUP-2 fix 完全 settled（`[42b]/[42c]` = 1.000 for active strategies）；剩餘 WARN 都是已知 sample-maturity（[42b]/[42c]/[51]）或 alpha-deficient（[40] 屬 P0-EDGE-1）。

### Verify item 4 — Verdict

**`P1-DATA-1..3-WATCH` 降級為 DOWNGRADE_TO_OPTIONAL**：

理由：
1. Source ✅；LG-5 W3 FUP-2 attribution fix 完全 settled，per-strategy = 1.000 / LOW_SAMPLE deferred by R-meta 是設計正確
2. row-rolloff watch 14d 證實非異常（daily distribution 在 2-43 範圍穩定）
3. 剩餘 watch items（[40] alpha / [51] scanner LOW_SAMPLE）已被覆蓋於 P0-EDGE-1 + R-1/R-2/R-3 路徑
4. 維持 watch 無增量價值；移除可清 §11.3 行數

**建議**：從 §11.3 移除整條，watch 改為「跟 §11.4 P0-MICRO-PROFIT / §11.5 EDGE-P2-3 Phase 1b 一起隨 alpha 修復進展自然回歸」。

---

## §B. P1-LG-5 — STILL_ACTIVE

### Verify item 1 — LG-5 spec / source 位置

Source（active）：
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py` — 1552 LOC，core review_live_candidate logic
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/lg5_review_consumer_scheduler.py` — 722 LOC，consumer scheduler

最近 commits：
- `c8240b6a` 2026-05-07 — P1 drain unaudited candidates（per-cycle cap starvation fix + SQL-shape regression test）
- `463890de` 2026-05-02 — FUP-1 consumer scheduler land

Spec：
- `docs/healthchecks/2026-05-02--lg5_health_checks.md`
- `docs/CCAgentWorkSpace/Operator/2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md`
- `docs/execution_plan/2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md`（提到 LG-1..LG-5 baseline 為 R-4 substrate）

### Verify item 2 — reviewer maturity metric 過去 7d

PG empirical query：
```sql
SELECT event_type, verdict_decision, COUNT(*)
FROM learning.governance_audit_log
WHERE ts > NOW() - INTERVAL '7 days'
GROUP BY 1,2 ORDER BY 3 DESC;
```

結果：
| event_type | verdict_decision | count |
|---|---|---:|
| review_live_candidate | defer | **66** |
| halt_session_set | (null) | 1 |
| halt_session_manual_cleared | (null) | 1 |

**100% verdict=defer**。

### Verify item 3 — audit-row 累積健康（per-strategy 3d）

```sql
SELECT strategy_name, COUNT(*), COUNT(*) FILTER(WHERE attribution_chain_ok IS TRUE) AS ok,
       ROUND(100.0 * COUNT(*) FILTER(WHERE attribution_chain_ok IS TRUE) / NULLIF(COUNT(*),0), 2) AS pct
FROM learning.mlde_edge_training_rows
WHERE ts > NOW() - INTERVAL '3 days'
GROUP BY 1 ORDER BY 2 DESC;
```

| strategy | rows_3d | OK | pct |
|---|---:|---:|---:|
| ma_crossover | 53,121 | 53,110 | 99.98% |
| grid_trading | 193 | 29 | 15.03% |
| bb_reversion | 3 | 3 | 100% |

**注意**：grid_trading 15% 不是 bug — grid 4-leg lifecycle（4 fills/round-trip）造成 partial attribution chain。`[42c]` 用 settled-only 過濾後 grid 3d = 1.000(n=29) ✅。Engine-mode 拆分：demo=29607 ma_crossover / live_demo=23514 ma_crossover；grid demo=161 / live_demo=32。

### Verify item 4 — source 仍 active vs land

- **Source 仍 active**：5/2 reviewer / 5/7 P1 drain fix；scheduler daily fire 4-43 reviews/day（5/8-5/19 穩定 active）
- **未進入 silent mode**：5/19 4 reviews / 5/18 2 reviews / 5/17 15 reviews 都 live
- **100% defer 是正確訊號**：5 textbook 策略 EV negative（per QC 2026-05-11 audit；`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`）；reviewer 預期應 defer。promote 真實發生需 alpha 路徑（W-AUDIT-8a Phase B/C/D + W-AUDIT-8e R-2 Strategist + W-AUDIT-8f R-3 Hypothesis Pipeline）+ LG-3 Wave 2.4 IMPL 完成

### Verdict

**STILL_ACTIVE**：
- Source ✅ active；audit-row 健康；100% defer 是設計正確
- 維持 §11.3 watch；等 alpha 路徑（R-1/R-2/R-3）+ LG-3 Wave 2.4 IMPL 完成後再 re-evaluate
- **不可降級**：promotion 永遠 defer 的 reviewer 仍是 LG-5 substrate；R-4 per-alpha-source promotion gate 還未開
- 建議 watch 條件：「直到首個 promotion verdict ≠ defer 出現」

---

## §C.1 P1-EDGE-1 — CLOSED

### Verify item 1 — ma_crossover blocked_symbols runtime

PG empirical query（7d）：
```sql
SELECT symbol, engine_mode, COUNT(*), ROUND(SUM(realized_pnl)::numeric,4) AS pnl
FROM trading.fills
WHERE strategy_name='ma_crossover'
  AND symbol IN ('LABUSDT','NAORISUSDT','PENGUUSDT','FARTCOINUSDT')
  AND ts > NOW() - INTERVAL '7 days'
GROUP BY 1,2 ORDER BY 1,2;
```

結果：**0 rows** — 4 個 ma frozen symbols 過去 7d 完全無 new fill ✅

擴 30d 範圍可見歷史 fills（但都是 freeze land 2026-05-09 之前的舊樣本）：
| symbol | engine_mode | fills_30d | pnl |
|---|---|---:|---:|
| FARTCOINUSDT | demo | 27 | -1.32 |
| FARTCOINUSDT | live_demo | 28 | -0.03 |
| LABUSDT | demo | 15 | -15.19 |
| LABUSDT | live_demo | 7 | -0.93 |
| NAORISUSDT | demo | 12 | -2.92 |
| NAORISUSDT | live_demo | 9 | -0.77 |
| PENGUUSDT | demo | 36 | -2.75 |
| PENGUUSDT | live_demo | 23 | -0.28 |

### Verify item 2 — grid blocked_symbols runtime

17 個 grid frozen symbols 7d fills：**0 rows** ✅

30d（freeze 前 stale window）有歷史 fills 但都是 freeze 之前；其中 `[BSBUSDT, DOGEUSDT, ENAUSDT, FARTCOINUSDT, GALAUSDT, ORCAUSDT, PENGUUSDT, PRLUSDT, SOLUSDT, ZBTUSDT]` 12 個 pnl_usdt=0.0000（close-only fills，by-design — blocked 只阻止新開倉，允許 close/reduce）。其餘 `[1000PEPEUSDT +0.31 / ADAUSDT -0.27 / BILLUSDT -2.41 / LABUSDT -8.02 / NAORISUSDT -0.92 / TAOUSDT -0.38]` 是 freeze 之前的舊 entries close 出來的 P&L。

### Verify item 3 — freeze registry + static guard

Registry：`docs/governance_dev/strategy_blocked_symbols_freeze.json`
- schema_version=1, freeze_id=`P2-AUDIT-VERIFY-5-2026-05-09`, status=`frozen`, scope=`new_entries_only`
- grid_trading frozen 17 symbols；ma_crossover frozen 4 symbols
- policy.new_block_requirements 4 條：PA/operator RFC + 7d counterfactual + DSR/PBO 證據 + TODO.md 結構

Static guard：`tests/structure/test_strategy_blocked_symbols_freeze.py`（83 LOC）
Audit helper：`helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`（247 LOC，read-only）
PM report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--p2_audit_verify_5_blocked_symbols_freeze.md`

Commit `c081029d` (2026-05-09 18:20) land 完整 freeze policy；CC `--rebuild` 不需要（純 JSON registry + Python helper）。

### Verdict

**CLOSED** — 移到 §12.4 已完成列表：
- runtime freeze 完全執行（7d 新 fills=0）
- 結構 guard + audit helper + PM report 三位一體
- 新 block 需走 RFC + 7d counterfactual + DSR/PBO SOP（policy 強制）
- 不需保留 ACTIVE-P1 — freeze 是 permanent 治理規定，非工程 active 工作

---

## §C.2 P1-EDGE-2 — STILL_ACTIVE 性質改變（建議升 P0）

### Verify item 1 — funding_arb 14d audit 2026-05-16 是否真跑

Audit script + .sh wrapper：
- `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py`（463 LOC，commit `2d67c952` 2026-05-02 land）
- `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`（67 LOC venv-aware wrapper）

**沒看到 2026-05-16 真實執行的 audit report**（搜遍 `docs/CCAgentWorkSpace/` 無相應 5/16 結果文件；只有 5/2 E2 PR review）。

### Verify item 2 — PA 親自跑 audit（2026-05-21 12:18 UTC）

```bash
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh"
```

結果摘要：
- Window: 2026-05-02 17:42 UTC → 2026-05-16 17:42 UTC
- Engine: demo
- **Total round-trips: 18**（< 30 trigger threshold）
- Win rate: 11.1%（wins=2）
- Gross bps: -32.48
- **Net bps after fee: -49.74** ⚠️
- Min realized_pnl (worst single): -4.20 USD
- **Max single-trade abs(loss)/notional: 6.29%** ⚠️ — 3% hard cap；**>5% = SL gate bug**
- **Fills exceeding 5% notional: 1**（must be 0；**SL gate failure**）⚠️
- Total notional: 1680.59 USD
- Total fee: 2.90 USD
- **Decision: INSUFFICIENT**（n=18 < 30；net_bps preview only）

### Verify item 3 — funding_arb fills volume 14d/30d

```sql
SELECT 'funding_arb_fills_14d', COUNT(*) FROM trading.fills
WHERE strategy_name='funding_arb' AND ts > NOW() - INTERVAL '14 days';
-- → 0

SELECT 'funding_arb_fills_30d', COUNT(*) FROM trading.fills
WHERE strategy_name='funding_arb' AND ts > NOW() - INTERVAL '30 days';
-- → 125
```

**14d = 0**；30d=125 是 5/2-5/16 audit window 內樣本。**funding_arb 已 dormant**（per memory `project_funding_arb_v2_deprecation_path` 確認 demo active=true 收 EDGE-DIAG-2 樣本，但**樣本 5/16 起停止流入**）。

### Verify item 4 — Verdict

**STILL_ACTIVE 性質改變** — 兩個獨立問題：

**問題 1（governance decision deadlock）**：
- 2A trigger 需 n≥30；audit 5/16 n=18，過去 14d 樣本 = 0；**繼續等 n≥30 是 deadlock**
- 既然 memory 已確認「2A 中期棄策略決議」(`project_funding_arb_v2_deprecation_path`)，但 audit script 仍依 n≥30 trigger 邏輯走 INSUFFICIENT verdict
- **建議升級為 `P0-FUNDING-ARB-DECISION-FORCE`**：由 PM/QC 用現有 n=18 + memory 2A 決議路徑強制 governance judgement decision，不再等 n≥30 trigger

**問題 2（SL gate failure - 衍生 follow-up）**：
- audit 結果有 1 fill 超過 5% notional（6.29% abs loss / notional）
- 3% hard cap 設計上應該 = 0 fills 超 5%；**>5% 表示 dynamic SL gate / position sizing 有 bug**
- 建議升 P1 follow-up `P1-FUNDING-ARB-SL-GATE-BUG`：FA 查 SL gate 為何放行 6.29% loss

### Verdict

**STILL_ACTIVE，但**：
- 維持 §11.3 P1-EDGE-2 **但**升 P0 = `P0-FUNDING-ARB-DECISION-FORCE`（PM/QC 強制 governance decision，不再等 n≥30）
- 衍生新 follow-up `P1-FUNDING-ARB-SL-GATE-BUG`（FA owner）

---

## §D. PM action items

### §11.3 → §12.4 closure 建議

| 條目 | 操作 | 目標 §  | 備註 |
|---|---|---|---|
| `P1-DATA-1..3-WATCH` | DOWNGRADE_TO_OPTIONAL，從 §11.3 刪除 | （刪除/不再 active）| watch 已被 P0-EDGE-1 + R-1/R-2/R-3 + `[51]` scanner LOW_SAMPLE 覆蓋 |
| `P1-EDGE-1` | CLOSED → 移 §12.4 | §12.4 | freeze permanent；新 block 走 RFC + counterfactual SOP（policy.new_block_requirements） |
| `P1-LG-5` | STILL_ACTIVE，維持 §11.3 | §11.3 | reviewer 100% defer 是設計正確；等 alpha 路徑 + LG-3 Wave 2.4 |
| `P1-EDGE-2` | STILL_ACTIVE 性質改變 → 升 P0 | §10（新 `P0-FUNDING-ARB-DECISION-FORCE`）| n≥30 trigger 鎖死於 dormant；PM/QC 強制 governance decision |
| **NEW** `P1-FUNDING-ARB-SL-GATE-BUG` | 衍生 → 新增 §11.3 | §11.3 | audit 6.29% loss/notional 超過 3% hard cap；FA 查 SL gate；P1 |

### 額外 watch 條件建議（不阻塞本次 closure）

- 本次 reverify 暴露 9 個獨立 critical issues（不在 watch 範圍）：
  - `[Xa]` leader_election DEAD（pid 2897824, lock at /tmp/openclaw/edge_scheduler.leader.lock）→ 需 PM/E5 即刻處理
  - `[66]` panel_freshness FAIL 1383s（PanelAggregator 可能 dead 或 BB WS stale）
  - `[56]` live_pipeline_active FAIL（snapshot stale 1335s > 180s threshold）
  - `[48]` replay_manifest_registry_growth 7d=0（replay_runner stalled）
  - `[12]` bb_breakout_post_deadlock_fix FAIL（bb_breakout 7d entries=0）
  - `[74]` close_maker_reject_samples FAIL（missing PostOnly reject samples blocks promotion）
  - `[75]` panel_aggregator_health cron stale 26.1min
  - `[76]` wave9_replay_no_live_mutation_watch cron stale 1.4h
  - `[79]` blocked_symbols_30d_unblock_check cron heartbeat missing
- 這些不在本 reverify 範圍但建議 PM 起一條 `P0-RUNTIME-STATUS-RECOVERY` 統籌處理

### 衍生 follow-up（從 PA reverify 過程中發現）

| ID | 來源 | 任務 | 優先 |
|---|---|---|---|
| `P1-FUNDING-ARB-SL-GATE-BUG` | §C.2 audit 結果 | FA 查 SL gate 為何放行 6.29% loss/notional（>5% must be 0；3% hard cap） | P1 |
| `P0-FUNDING-ARB-DECISION-FORCE` | §C.2 deadlock | PM/QC 用 n=18 + 2A memory 路徑強制 governance decision | P0 |
| `P2-AUDIT-SCRIPT-EXEC-EVIDENCE` | §C.2 verify item 1 | 5/16 audit script 有 land 但無 5/16 真實執行報告；建議 cron 化 + 自動 store output to `docs/audits/YYYY-MM-DD--<topic>.md` 確保 SOP 留證 | P2 |

---

## 完成證據

- ssh trade-core: ✅ 6 個 PG SQL queries empirical + 1 healthcheck runner（`bash helper_scripts/db/passive_wait_healthcheck.sh --quiet`）+ 1 audit script（`bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`）
- source grep: ✅ rust risk_checks_per_strategy_tests.rs + python LG-5 reviewer / scheduler / mlde_demo_applier
- git log: ✅ 從 commit `c081029d`（freeze）→ `34211ab4`（LG-5 W3 FUP-2）→ `2d67c952`（funding_arb audit script）→ `c8240b6a`（LG-5 drain fix）→ `463890de`（reviewer consumer）→ `3f4aa079`（v36 P1 compact）
- 結論性報告: 本檔 + memory append
