# Counterfactual Quality 月報生成 SOP

**狀態：** Draft（Sprint 1A-β deliverable；M11 nightly replay + V107 schema land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-CF-QUALITY-001
**Module：** Counterfactual quality 月報（M11 daily evidence aggregation + ADR-0030 Y1 末 4-gate Copy Trading Evidence input prep）
**Severity coverage：** SEV-2 / SEV-3（本 runbook 不涉及 live state SEV-1；報告生成失敗最高 SEV-2）
**On-call role：** PM（cron + 月度檢查）+ MIT（quality metric review）+ FA（Y1 末 4-gate evaluation 期間 evidence packet prep）
**Depends on：** v5.8 §2 M11 (line 391-423) / ADR-0030 (Copy Trading Evidence-gated; §Gate 1 Alpha gate input from Y1 evidence) / ADR-0038 (self-hosted PG market.liquidations; nightly replay source) / CR-7 spec (M11 threshold + M7 dedup; quality metric 分類基礎) / V107 schema (CR-8 placeholder; nightly aggregation source) / M11 runbook (daily-evidence pipeline)

> **Hands off — operator only**：月報是 evidence aggregation 與 trend reporting；任何「strategy promote / demote / activation」決策 **不從本月報生成**，必走 M7（demote） / ADR-0030（Y1 末 Copy Trading enable） / M11 runbook（divergence triage）對應路徑。月報只是 **input data prep**。

---

## 1. TL;DR / 用途

Counterfactual quality 月報是 M11 nightly replay 的**月度 aggregation + trend reporting** + ADR-0030 Y1 末 Copy Trading Evidence Gate 的 **Gate 1 Alpha gate input data prep**。每月 1 日 06:00 UTC cron 自動生成；PM + MIT 月度檢查 + 內部 review；Y1 末（Sprint 10 W36-39）作 ADR-0030 4-gate evaluation 的 evidence packet 之一。

**月報內容**：
- **counterfactual coverage**（哪些 strategy 必含 counterfactual；coverage rate）
- **quality metric**（divergence rate / sample n / OOS fit / multi-source confirm consistency）
- **monthly trend dashboard view**（4 週 / 12 週 / 24 週）
- **Y1 末 evidence packet template**（per ADR-0030 §Gate 1 Alpha gate input prep）

**核心紀律**：
- counterfactual coverage threshold：**所有 live + live_demo strategy 必含 nightly counterfactual**；coverage < 100% sustained 7d → SEV-2
- quality metric 失準（如 divergence rate jump / sample n 異常 collapse）→ M11 ADR-0038 historical source pipeline 檢查
- Y1 末 evidence packet 由本月報衍生；不直接做 Copy Trading enable 決策

本 runbook 規範 4 類事件：(a) **月報生成 cron + dashboard 健康** / (b) **counterfactual coverage threshold 驗證** / (c) **quality metric 報告 template + 失準 triage** / (d) **Y1 末 Copy Trading Evidence Gate input data prep 流程**（per ADR-0030 §Gate 1）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| 每月 1 日 06:00 UTC + 4h 未收到 Slack 月報通知 | cron log + Slack channel | §4 cron 健康 |
| Console `counterfactual_quality_reports` tab 月度 row 缺失 | `learning.cf_quality_reports` | §4 generation 失敗 |
| Strategy 在 `learning.replay_divergence_log` 連續 7d 無 row | counterfactual coverage SQL | §5 coverage threshold |
| Quality metric（divergence_rate / sample_n / oos_fit）月度 jump > 50% | 月報 trend section | §6 quality 失準 triage |
| Y1 末 Sprint 10 期間 ADR-0030 evidence packet 缺漏 | per ADR-0030 §Gate 1 input prep checklist | §7 evidence packet prep |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-2** | 月報生成失敗（cron fail / DB write fail）；counterfactual coverage 連 7d < 100%；Y1 末 evidence packet prep 落後 deadline | < 24h | PM + MIT 24h 內補；阻擋 ADR-0030 Y1 末 evaluation timeline 一個月 |
| **SEV-3** | Quality metric drift > 50% but pipeline 健康；個別 strategy 月度 sample n 偏低（如 Y1 早期新策略） | < 7d | PM 月度 review；登錄 12-week trend；MIT 評估 metric threshold 是否需調整 |

> **注**：本 runbook 無 SEV-1。月報是 read-only aggregation + report；live state 寫操作走 M7 / M11 / ADR-0030 對應 runbook。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 確認最近月報生成狀態
psql -h trade-core -U openclaw -d openclaw -c "
SELECT report_month, generated_at, generation_duration_sec,
       strategy_count, coverage_pct, divergence_rate_p50,
       sent_to_slack_at, payload->>'pdf_path' AS pdf
FROM learning.cf_quality_reports
ORDER BY report_month DESC LIMIT 6;"
# expected:
#   每月 1 row（report_month = month start UTC）
#   generated_at < report_month + INTERVAL '6 hours'
#   strategy_count = 全 live + live_demo strategy count
#   coverage_pct = 100.0
# decision branch:
#   缺月度 row → §4 Step 2 cron 健康
#   strategy_count < expected 或 coverage_pct < 100 → §5
```

```bash
# Step 2 — cron 健康（如月報缺）
ssh trade-core "tail -200 /tmp/openclaw/logs/cf_quality_report_cron.log | tail -50"
# 看 invocation status + error trace
ssh trade-core "crontab -l | grep cf_quality_report"
# expected: 0 6 1 * * /path/to/cf_quality_report_generator.py（每月 1 日 06:00 UTC）
```

```bash
# Step 3 — counterfactual coverage（all strategy 必含 nightly replay）
psql -h trade-core -U openclaw -d openclaw -c "
WITH live_strategies AS (
  SELECT DISTINCT strategy_name FROM trading.fills
  WHERE engine_mode IN ('live', 'live_demo')
    AND created_at > NOW() - INTERVAL '7 days'
),
covered AS (
  SELECT DISTINCT strategy_name FROM learning.replay_divergence_log
  WHERE created_at > NOW() - INTERVAL '7 days'
)
SELECT ls.strategy_name,
       (cov.strategy_name IS NOT NULL) AS has_counterfactual,
       (SELECT COUNT(*) FROM learning.m11_replay_runs WHERE created_at > NOW() - INTERVAL '7 days') AS nightly_count
FROM live_strategies ls LEFT JOIN covered cov USING (strategy_name);"
# decision branch:
#   has_counterfactual = false 連 7d → §5 SEV-2
```

```bash
# Step 4 — 最新月份 quality metric 概覽
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, sample_n_month, divergence_rate_pct,
       oos_fit_score, multi_source_consistency_pct
FROM learning.cf_quality_metrics
WHERE report_month = (SELECT MAX(report_month) FROM learning.cf_quality_metrics)
ORDER BY strategy_name;"
# decision branch:
#   sample_n_month < 30 → SEV-3 (Y1 早期新策略 expected)
#   divergence_rate_pct > prev_month × 1.5 → §6 quality 失準
#   oos_fit_score < 0.5 → quality 失準 SEV-3
#   multi_source_consistency_pct < 80 → SEV-2 (CR-7 dedup contract violation)
```

```bash
# Step 5 — Slack 通知路徑健康
curl -sS http://localhost:8001/api/v1/notify/health | jq '.slack_ok'
# 如 false → 月報生成 OK 但 Slack 通知不會發；§4 補手動 trigger
```

```bash
# Step 6 — Y1 末 evidence packet 進度（only Y1 末 Sprint 10 W36-39 期間 active）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT packet_name, status, last_updated_at
FROM learning.copy_trading_evidence_packet
WHERE evaluation_cycle = (SELECT MAX(evaluation_cycle) FROM learning.copy_trading_evidence_packet)
ORDER BY packet_name;"
# expected per ADR-0030 §Gate 1: 'alpha_gate_aggregate_sharpe' / 'per_strategy_hit_rate' / 'max_drawdown'
# 缺漏 → §7
```

```bash
# Step 7 — Dashboard 健康
curl -sS http://localhost:8001/api/v1/cf_quality/dashboard/health | jq
# expected: .last_render_at < 4h ago + .all_strategy_count > 0
# 如 stale → §4 dashboard render 失敗
```

```bash
# Step 8 —（only if SEV-2 + 真月報缺）手動 trigger 月報生成
ssh trade-core "python3 helper_scripts/cron/cf_quality_report_generator.py --month=YYYY-MM-DD --force-regen"
# 預期 effect: 寫 learning.cf_quality_reports row + 渲染 dashboard + Slack notification
# 報告 PDF 路徑：/tmp/openclaw/reports/cf_quality_YYYYMM.pdf
```

---

## 5. Counterfactual Coverage Threshold 驗證

**核心紀律**（per ADR-0030 §Gate 1 Alpha gate input prep）：
- 所有 live + live_demo strategy **必含** nightly counterfactual replay
- coverage < 100% sustained 7d → 月報 SEV-2 + 阻擋 ADR-0030 Y1 末 evaluation

### Coverage 範圍
- **All Y1 live strategy**：C10 funding harvest / Unlock SHORT / Pairs trading / C13 defined-risk options VRP / Funding short-only（per ADR-0030 §Y1 self-trading evidence accumulation 路徑）
- **All live_demo strategy**：5 textbook 策略（grid / ma / bb_breakout / bb_reversion / funding_arb）— P0-EDGE-1 期間仍納入 coverage
- **Demo-only**：可選；不在強制 coverage

### Coverage 失敗 root cause 候選
1. M11 nightly cron 對該 strategy `replay_runner` 漏跑
2. Strategy 在 `trading.fills` 有 row 但 M11 strategy_list config 漏登
3. self-hosted PG `market.*` 對該 strategy 涉及 symbol 數據缺漏（per M11 runbook §8）
4. Replay engine 對該 strategy 不支援（新策略 lineage code 未 wire 至 replay）

### Mitigation
- root cause 1-2 → 補 M11 strategy_list config + 觸發 next nightly
- root cause 3 → M11 runbook §8 fallback；coverage gap 標 strategy + 等 PG 累積
- root cause 4 → SEV-2；E1 wire replay engine support；阻 ADR-0030 evaluation 計入該 strategy

---

## 6. Quality Metric 報告 Template + 失準 Triage

### 6.1 Quality metric 4 維度

| Metric | 計算方式 | PASS threshold | WARN | FAIL |
|---|---|---|---|---|
| **divergence_rate_pct** | (CRITICAL + WARN divergence count) / (total replay decision count) × 100 | < 5% | 5-10% | > 10% |
| **sample_n_month** | 月度 replay decision row count per strategy | ≥ 200 | 30-199 | < 30 |
| **oos_fit_score** | Out-of-sample fit：replay-decided vs production-executed correlation | ≥ 0.7 | 0.5-0.69 | < 0.5 |
| **multi_source_consistency_pct** | M11 CRITICAL → M7 input emit 對齊率（per CR-7 dedup） | 100% | 95-99% | < 95% |

### 6.2 月報 template 結構

```markdown
# Counterfactual Quality Report — <YYYY-MM>

## §1 Executive Summary
- Coverage: <pct>% (target 100%)
- All strategy quality verdict: <PASS / WARN / FAIL count>
- Top 3 strategy by divergence_rate_pct
- Top 3 strategy by sample_n_month
- ADR-0038 historical source health: <green/yellow/red>

## §2 Per-Strategy Quality Table
| Strategy | divergence_rate_pct | sample_n | oos_fit | multi_source_consistency |
|---|---|---|---|---|
| (per strategy row) |

## §3 4-Week / 12-Week / 24-Week Trend
- Per-metric trend chart (Slack-attached PNG)
- 異常 jump 列表（> 50% month-over-month）

## §4 Coverage Gaps
- 缺 coverage 的 strategy 列表
- 對應 root cause + mitigation 進度

## §5 ADR-0038 Historical Source Health
- self-hosted PG row count per market.* table 30d trend
- WS subscription 健康（per BB W-AUDIT-8a C1）
- Cold start fallback 觸發次數

## §6 Y1 末 ADR-0030 Evidence Packet Snapshot（只在 Sprint 10 W36-39 顯示）
- Alpha gate input：aggregate sharpe / per-strategy hit rate / max drawdown
- Governance gate input：M7 input emit rate / Guardian block rate / Operator override count
- Infrastructure gate input：uptime / WS reconnect / DB integrity / migration audit
- Regulatory gate input：Bybit ToS check status

## §7 Action Items
- 個別 strategy quality 改善建議
- M11 ADR / threshold 調整建議
- Coverage gap 補 plan
```

### 6.3 Quality 失準 Triage

**Trigger**：§4 Step 4 任一 metric FAIL 或 WARN sustained 2+ months。

```bash
# Triage step 1 — divergence_rate jump 排查
psql -h trade-core -U openclaw -d openclaw -c "
SELECT divergence_type, severity, COUNT(*) AS n
FROM learning.replay_divergence_log
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY 1, 2 ORDER BY 3 DESC;"
# 對應 M11 runbook §5 5-7 divergence type 處置
```

```bash
# Triage step 2 — sample_n 偏低排查
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, COUNT(*) AS sample_n_30d
FROM learning.replay_divergence_log
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY 1 ORDER BY 2;"
# decision branch:
#   < 30 → 該 strategy 月度 sample 不足；Y1 早期 expected；待累積
#   突然 collapse → M11 nightly 對該 strategy 漏跑（§5 coverage）
```

```bash
# Triage step 3 — multi_source_consistency 失準（CR-7 dedup violation）
psql -h trade-core -U openclaw -d openclaw -c "
-- 同 M7 runbook §4 Step 4 query
"
# 如 consistency < 100% → SEV-2；走 M7 runbook §8 dedup verify
```

---

## 7. Y1 末 Copy Trading Evidence Gate Input Data Prep（per ADR-0030 §Gate 1）

**只在 Sprint 10 W36-39 期間 active**。月報自動 emit packet input；FA + PM 月度 review。

### 7.1 ADR-0030 §Gate 1 Alpha Gate Input

| Sub-criterion | Threshold | 數據源 | 月報來源 |
|---|---|---|---|
| Aggregate Sharpe ratio (Y1 portfolio) | ≥ 0.8 net of cost | `learning.attribution_chain` + `trading.fills` aggregate | §1 + §2 |
| Per-strategy hit rate | ≥ 3/5 策略 hit_rate ≥ 50% live + live_demo | per-strategy aggregation | §2 |
| Maximum drawdown (Y1) | ≤ 15% account peak-to-trough | account balance reconciliation | §1 |

### 7.2 ADR-0030 §Gate 2 Governance Gate Input

| Sub-criterion | 月報來源 |
|---|---|
| Decision Lease 通過率 ≥ 70% | §6 governance section（per M11 quality cross-table） |
| Guardian 攔截次數 trend（不該升）| §6 governance section |
| Operator override 次數 trend（不該升） | §6 governance section |

### 7.3 ADR-0030 §Gate 3 Infrastructure Gate Input

| Sub-criterion | 月報來源 |
|---|---|
| Engine uptime ≥ 99% | §6 infra section |
| WS reconnect rate < 1/day | §6 infra section |
| DB integrity check pass rate = 100% | §6 infra section |
| V### migration audit clean | §6 infra section |

### 7.4 ADR-0030 §Gate 4 Regulatory Gate Input

| Sub-criterion | 月報來源 |
|---|---|
| Bybit Copy Trading ToS 仍允許 | §6 regulatory section（manual check by Operator + legal） |
| Project ToS compliance status | 同上 |

### 7.5 Packet 生成步驟

```bash
# Y1 末（Sprint 10 W36-39 期間）每月 1 日自動觸發 evidence packet
ssh trade-core "python3 helper_scripts/cron/cf_quality_report_generator.py --emit-copy-trading-packet"
# 寫入 learning.copy_trading_evidence_packet 多 row（per packet_name）
```

```bash
# FA + PM monthly review
psql -h trade-core -U openclaw -d openclaw -c "
SELECT packet_name, value, threshold, status, reviewer_note
FROM learning.copy_trading_evidence_packet
WHERE evaluation_cycle = (SELECT MAX(evaluation_cycle) FROM learning.copy_trading_evidence_packet)
ORDER BY packet_name;"
# decision branch:
#   任一 status='FAIL' → ADR-0030 4-gate Y1 末 evaluation 該 gate fail；不 enable Copy Trading
#   全 'PASS' → 進 ADR-0030 §Decision Y2 enable evaluation cycle
```

**禁忌**：
- 月報 packet **不直接決定** Copy Trading enable / disable；只是 input data prep
- 最終 Y1 末 4-gate verdict 由 Operator 親手 click on Console（per ADR-0030 §Decision 對齊 §四 hard boundaries）
- 不允許 month-mid 拉新 packet 「重算」evidence（snapshot-based 紀律；per ADR-0030 §evaluation cycle）

---

## 8. 月報生成失敗 Mitigation

### 8.1 Cron 失敗

- cron exit ≠ 0 → 7 day retry window（每日同時間自動 retry）
- 7 day 內未補 → SEV-2 + PM 手動 §4 Step 8 force-regen
- 14 day 內未補 → SEV-1 升 P0；阻 ADR-0030 evaluation

### 8.2 PDF render 失敗

- 渲染失敗但 DB row 寫入 OK → 月報數據可從 SQL 取；PDF 補渲染走 §4 Step 8
- 失敗根因 candidate：matplotlib / weasyprint 依賴變更；Linux PG 連線 timeout

### 8.3 Slack 通知失敗

- DB row OK + Slack fail → 月報生成成功但 operator 不知；§4 Step 5 確認通知路徑
- 補通知：手動 `curl -X POST slack_webhook -d '<payload>'`

### 8.4 Rollback option

如月報 generator 本身 regression（生成錯誤數據）：
- 暫停 cron + 標 row `status='regression'`
- E1 修 generator + 補 regen
- PM 通知所有 reviewer「<month> 月報數據作廢，等修復後重 generate」

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-2；§5 coverage < 100% sustained 14d；§7 Y1 末 evidence packet 落後 Sprint 10 deadline 1 個月。

**Escalation channel**：
- SEV-2：Slack `#ops-warn` + email PM + email FA（Y1 末期）+ email MIT
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.cf_quality_reports` 最近 6 month row
- `learning.cf_quality_metrics` 對應 month per strategy
- `learning.replay_divergence_log` 30d aggregate
- `learning.copy_trading_evidence_packet`（only Y1 末）
- cron log + Slack send log
- M11 nightly runs 30d health

**Post-escalation action**：
- PM 24h 內派 MIT review quality metric threshold + ADR-0030 Y1 末 evidence packet completeness
- 7d 內補 postmortem `docs/audits/<date>--cf_quality_report_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# Counterfactual Quality Report Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Severity: SEV-?
- Affected month(s): <list>
- Failure mode: <cron / DB write / PDF / Slack / coverage / metric drift>
- Y1 末 impact (if any): <ADR-0030 evaluation delay days>

## Timeline (UTC)
- T+0: <expected cron / symptom>
- T+N: <step>

## Root cause
- generator / coverage / quality metric / dependency 任一斷裂？
- ADR-0030 evidence packet 是否被影響？
- M11 ADR-0038 historical source 是否健康？

## Mitigation
- 即時 mitigation (§8 對應)
- 永久 mitigation（cron retry policy / quality threshold 調整 / packet schema 補）

## Action items
- [ ] Cron retry window 調整
- [ ] cf_quality_metrics schema 補 column
- [ ] runbook §X 更新
- [ ] M11 ADR-0038 對齊（如 source health 問題）

## 12-week trend
- 加入 monthly CF quality trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard 含 CF Quality section：
- 4 週 / 12 週 monthly report 生成狀態
- Coverage rate trend
- Per-strategy quality metric trend
- Y1 末 evidence packet readiness（Sprint 10 期間突出顯示）

Dashboard：`http://localhost:8001/console#governance/cf_quality` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **v5.8 §2 M11**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:391-423`（continuous nightly replay；月報 input source）
- **ADR-0030**：`docs/adr/0030-copy-trading-evidence-gated.md`（§Gate 1 Alpha gate input from Y1 evidence；本 runbook §7 packet prep 目標）
- **ADR-0031**：`docs/adr/0031-framework-expansion-earn-macro-onchain.md`（Earn / Macro / On-chain counterfactual policy；月報 §1 + §5 涉及）
- **ADR-0038**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（self-hosted PG source；月報 §5 health 段）
- **CR-7 spec**：`docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`（M11 threshold + M7 dedup；multi_source_consistency metric 依據）
- **V107 schema spec**（pending CR-8）：`docs/execution_plan/specs/2026-05-21--v107-replay-divergence-log.md`（月報 source data）
- **M11 runbook**：`docs/runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md`（daily-evidence pipeline；月報 aggregation 對象）
- **M7 runbook**：`docs/runbooks/2026-05-21--m7_decay_alert_runbook.md`（CR-7 dedup contract；multi_source_consistency 驗證）
- **Earn runbook**：`docs/runbooks/2026-05-21--earn_governance_runbook.md`（Y1 income evidence；ADR-0030 §Gate 1 旁路 evidence）
- **REF-21 replay 範式**：`docs/runbooks/ref21_replay_operator_runbook.md`（風格參考）
- **既有 H0 runbook（風格參考）**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **Cron script**：`helper_scripts/cron/cf_quality_report_generator.py`（pending Sprint 1A-β IMPL；SCRIPT_INDEX 待補）
- **Metric dashboard**：`http://localhost:8001/console#governance/cf_quality`（pending）
- **Healthcheck integration**：`helper_scripts/db/passive_wait_healthcheck.py --check cf_quality_monthly_report` + `--check cf_coverage_threshold`（pending）

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；月報 cron + dashboard + coverage threshold + quality metric 4 維度 template + Y1 末 ADR-0030 4-gate evidence packet input prep + 月報生成失敗 mitigation |

---

*OpenClaw / Arcane Equilibrium Runbook — Counterfactual quality 月報生成 SOP (Draft — M11 nightly + V107 schema + ADR-0030 4-gate framework land 後 v1 promote)*
