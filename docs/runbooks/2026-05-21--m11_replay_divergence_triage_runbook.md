# M11 Nightly Replay Divergence Triage SOP

**狀態：** Draft（Sprint 1A-β deliverable；V107 schema + ADR-0038 + CR-7 dedup contract land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M11-DIVERGENCE-001
**Module：** M11 Continuous Counterfactual Replay Automation
**Severity coverage：** SEV-1 / SEV-2 / SEV-3（對應 4 級 severity NOISE / WARN / CRITICAL / HALT 對齊 M8 per CR-7 §5）
**On-call role：** On-call PM + Operator + MIT（divergence root cause analysis）
**Depends on：** v5.8 §2 M11 (line 391-423) / ADR-0038 (self-hosted PG market.liquidations as historical source) / V107 schema (CR-8 placeholder; hypertable 必) / CR-7 spec (M11 + M7 dedup + threshold derivation + DECAY_ENFORCED rename) / M7 runbook (M11 → M7 input 路徑) / AMD-2026-05-21-01 (M11 daily Slack 5d 不被 ack auto-escalate per H-11)

> **Hands off — operator only**：M11 nightly cron 自動 emit divergence + M7 input；任何 strategy state transition / size shrink **必由 M7 single decay authority 處理**（per CR-7）；本 runbook 不允許 operator 透過 M11 路徑直接 demote strategy。

---

## 1. TL;DR / 用途

M11 把 v5.7 baseline 既有「Stage 0R replay one-time preflight」升級為 **continuous nightly counterfactual replay**：每日從 self-hosted PG `market.*` namespace pull 24h 歷史數據，跑所有 live strategies 對齊 replay engine，逐筆比 replay-decided 與 production-executed trades，flag 5-7 種 divergence type。

**核心治理立場**（per ADR-0038 + CR-7）：
- **Historical source 鎖死 self-hosted PG**（per Decision 1）— 禁依賴 Bybit historical API（不存在）/ 第三方 vendor / cross-exchange historical query
- **M11 是 emit-only**（per CR-7 dedup）— 寫 V107 row + emit M7 input；**不自行** demote strategy
- **5-7 divergence type × 4-level severity** matrix；CRITICAL+ 自動 emit M7 input；HALT 只在極端 reserved Y2+
- **5d passive Slack unack auto-escalate** 到 M3 HEALTH_WARN（per H-11 反向 attack #6）

本 runbook 規範 4 類事件：(a) **5-7 divergence type × severity 矩陣 triage** / (b) **nightly replay budget < 4h 監控** / (c) **5d passive Slack unack auto-escalate 處置**（per H-11）/ (d) **self-hosted PG market.liquidations 故障 fallback**（per ADR-0038 cold start 例外）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Slack daily report `[M11] divergence summary` 收到 | M11 nightly cron + Slack channel | §4 triage |
| Console `replay_divergence_log` tab 顯示 CRITICAL severity row | `learning.replay_divergence_log` | §5 type 1-7 處置 |
| M11 nightly cron 跑時間 > 4h budget | `learning.m11_replay_runs.duration` | §6 budget 監控 |
| 連續 5d 同一 strategy CRITICAL divergence 但 0 operator ack | M11 ack tracking | §7 5d unack escalation |
| `market.liquidations` 或 `market.public_trades` 表 row count 突然降為 0 | PG query | §8 fallback |
| M7 input emit rate 與 M11 CRITICAL count 不一致 | cross-table SQL | M7 runbook §8 dedup verify |

---

## 3. Severity Matrix（對齊 M8 4-level per CR-7 §5）

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **NOISE** (μ + 0.5σ) | 預期變異；不寫 M7 input；emit `learning.replay_divergence_log` row only | n/a | 不通知；月度 trend tracking |
| **WARN** (μ + 2.5σ) | SEV-3；emit M7 input；Slack `#ops-info` daily summary | < 4h | On-call PM 月度 review；無 escalate |
| **CRITICAL** (μ + 3.0σ) | SEV-2；emit M7 input；Slack `#ops-warn`；如 5d unack 升 SEV-1 | < 24h（next business day） | On-call PM ack；4-day cooldown 後再 critical → auto-escalate |
| **HALT** (Y2+ reserved) | SEV-1；emit M7 input + 觸發 M3 HEALTH_CRITICAL；新單暫停 | < 5 min | Operator + PM 立加入；30 min 內判 root cause；24h postmortem |

> **threshold 派生**（per CR-7 / spec §2）：μ + Nσ 從 5d empirical baseline 計算；cold start 場景（新 strategy / 新 symbol）走 conservative absolute floor + WARN 直到 5d sample 累積。
> **為什麼 σ 而非絕對 bps**：跨 strategy 波動 scale 差 5-10×（如 grid vs bb_breakout）；絕對 bps threshold 會在 high-vol strategy 沉默 + low-vol strategy 過敏。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 昨夜 nightly run 狀態
psql -h trade-core -U openclaw -d openclaw -c "
SELECT run_id, started_at, duration_seconds, strategy_count, divergence_count,
       payload->>'historical_source' AS source
FROM learning.m11_replay_runs
ORDER BY started_at DESC LIMIT 5;"
# expected:
#   duration_seconds < 14400（4h budget）
#   source = 'self_hosted_pg'（per ADR-0038 Decision 1）
#   strategy_count = 全 live strategy count
# decision branch:
#   duration > 14400 → §6 budget 違反
#   source != 'self_hosted_pg' → SEV-1 ADR-0038 violation
```

```bash
# Step 2 — 今晨 divergence severity 分布
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, divergence_type, divergence_severity, COUNT(*) AS n
FROM learning.replay_divergence_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2, 3 ORDER BY 3 DESC, 4 DESC;"
# 5-7 divergence_type:
#   'pnl_bps' / 'decision_count' / 'slippage_bps' / 'fill_rate' / 'lease_grant_rate'
#   'param_drift' (silent param mismatch) / 'lineage_break'
# decision branch:
#   CRITICAL count > 5 → §5 type 1-7 處置（SEV-2）
#   HALT count ≥ 1 → SEV-1
```

```bash
# Step 3 — 驗 M11 emit-only 紀律（CR-7）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT COUNT(*) FILTER (WHERE payload->>'demote_emitted' = 'true') AS m11_self_demote_count
FROM learning.replay_divergence_log
WHERE created_at > NOW() - INTERVAL '24 hours';"
# expected: 0（M11 不自行 demote；per CR-7）
# 如 > 0 → SEV-1 dedup contract violation
```

```bash
# Step 4 — 驗 M7 input emit rate vs M11 CRITICAL count
psql -h trade-core -U openclaw -d openclaw -c "
WITH m11 AS (
  SELECT strategy_name, COUNT(*) AS critical_count
  FROM learning.replay_divergence_log
  WHERE divergence_severity = 'CRITICAL'
    AND created_at > NOW() - INTERVAL '24 hours'
  GROUP BY 1
),
m7 AS (
  SELECT strategy_name, COUNT(*) AS input_count
  FROM learning.decay_signals
  WHERE source_signal = 'm11_replay_divergence'
    AND created_at > NOW() - INTERVAL '24 hours'
  GROUP BY 1
)
SELECT COALESCE(m11.strategy_name, m7.strategy_name),
       m11.critical_count, m7.input_count
FROM m11 FULL JOIN m7 USING (strategy_name);"
# expected: critical_count == input_count per strategy
# 不等 → §7 emit pipeline 斷裂
```

```bash
# Step 5 — Historical source 健康（V107 source = self_hosted_pg 強制）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT
  (SELECT COUNT(*) FROM market.liquidations WHERE recorded_at > NOW() - INTERVAL '24 hours') AS liq_24h,
  (SELECT COUNT(*) FROM market.public_trades WHERE recorded_at > NOW() - INTERVAL '24 hours') AS trade_24h,
  (SELECT COUNT(*) FROM market.orderbook_l2_snapshot WHERE recorded_at > NOW() - INTERVAL '24 hours') AS ob_24h;"
# decision branch:
#   任一 = 0 → §8 fallback 路徑（cold start example or pipeline failure）
#   liq_24h < 1000（24h）→ WS subscription 可能炸；BB W-AUDIT-8a C1 期間 expected baseline
```

```bash
# Step 6 — Slack daily report 已發 + 5d unack tracking
psql -h trade-core -U openclaw -d openclaw -c "
SELECT report_date, sent_at, ack_at, ack_actor,
       (NOW() - sent_at) AS age,
       CASE WHEN ack_at IS NULL THEN (NOW() - sent_at)::interval ELSE NULL END AS unack_age
FROM learning.m11_daily_reports
ORDER BY report_date DESC LIMIT 7;"
# decision branch:
#   unack_age ≥ 5d → §7 auto-escalate 處置
```

```bash
# Step 7 — Replay engine vs production lineage 對齊
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, payload->>'replay_lineage_id' AS rl, payload->>'production_lineage_id' AS pl
FROM learning.replay_divergence_log
WHERE divergence_severity = 'CRITICAL'
  AND divergence_type = 'lineage_break'
  AND created_at > NOW() - INTERVAL '24 hours'
LIMIT 10;"
# 如 lineage_break critical → §5 type 7 處置
```

```bash
# Step 8 —（only if SEV-1）emergency disable M11 nightly + auto-escalate path
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"nightly_enabled":false, "auto_m3_escalate":false}' \
  http://localhost:8001/api/v1/m11/config
# 預期 effect：今夜 cron skip；不發 Slack；不 emit M7 input；既有 V107 row 不變
# §9 escalate；24h postmortem 必補
```

---

## 5. 5-7 Divergence Type × Severity Triage

### Type 1 — `pnl_bps`（PnL 偏差 > threshold bps）

- **Root cause 候選**：strategy decision 邏輯漂移 / replay engine cost model 過時 / production execution slippage 異常
- **Triage**：對齊 production fills `executed_price` vs replay `simulated_price`；如 σ > 2σ historical → MIT review

### Type 2 — `decision_count`（決策數量不一致）

- **Root cause 候選**：strategy param hot-reload 不對齊 / replay 使用舊 param snapshot / scanner symbol filter 漂移
- **Triage**：確認 `learning.config_snapshots` 在 replay 起始時間點的 hash 與 production 一致

### Type 3 — `slippage_bps`（執行 slippage 與 replay 估計差異）

- **Root cause 候選**：replay maker/taker model 過時 / production microstructure 變化 / OrderRouter 行為差
- **Triage**：對齊 replay `model_predicted_slippage_bps` vs production `actual_slippage_bps`；如 strategy maker-vs-taker 分布漂移 → M12 input

### Type 4 — `fill_rate`（fill 比 intent 比例偏差）

- **Root cause 候選**：production WS reconnect 期間 missed fills / replay maker fill model 過時
- **Triage**：確認 production 期間是否有 WS dropout（M3 ws_latency domain）

### Type 5 — `lease_grant_rate`（Decision Lease 通過率偏差）

- **Root cause 候選**：Guardian gate 邏輯變更未同步到 replay / risk envelope drift
- **Triage**：對齊 replay & production guardian_block_log；如 Guardian gate 變化 → M3 input

### Type 6 — `param_drift`（silent param mismatch）

- **Root cause 候選**：runtime IPC `patch_risk_config` 未寫入 audit / 多 session 並寫衝突
- **Triage**：grep `learning.risk_config_audit` 對應時間段；如有 unlogged patch → SEV-1 audit 路徑 regression
- **與 ADR-0034 D2 對應**：lease_id uniqueness contract 應防 silent param mismatch；如此 type 出現代表 contract 漏

### Type 7 — `lineage_break`（replay vs production lineage 對不上）

- **Root cause 候選**：production lineage record incomplete / replay schema drift
- **Triage**：對齊 `trading.fills.lineage_id` ↔ `learning.intent_lineage`；如 missing → MIT + E1 root cause；通常 V### migration 未跑或 race

### Common rollback

每 type 對應 mitigation 後皆走「next nightly run 自動 verify」；不需手動 reset V107 row。如 root cause 是 replay engine 本身 bug → 可暫停 nightly（§4 Step 8 emergency disable）+ E1 hotfix。

---

## 6. Nightly Replay Budget < 4h 監控

**Budget**（per spec / E4 audit）：每夜 24h replay 5 strategy × all live symbols 必在 4h wall-clock 內完成（per `project_hardware_constraints` 128GB 統一記憶體 / PG 4-8GB shared_buffers 限制 + TimescaleDB hypertable 預估）。

```bash
# Triage step 1 — 最近 7d 每夜 duration
psql -h trade-core -U openclaw -d openclaw -c "
SELECT started_at::date AS run_date,
       duration_seconds, strategy_count,
       (duration_seconds * 1.0 / strategy_count) AS sec_per_strategy
FROM learning.m11_replay_runs
WHERE started_at > NOW() - INTERVAL '7 days'
ORDER BY started_at DESC;"
# decision branch:
#   duration_seconds > 14400 → SEV-2 budget 違反
#   sec_per_strategy 突然 3x jump → 個別 strategy 觸發 cost spike
```

```bash
# Triage step 2 — PG buffer cache 命中率（hypertable 健康度）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT chunk_schema, chunk_name, range_start, range_end, is_compressed
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('liquidations', 'public_trades', 'orderbook_l2_snapshot')
  AND range_end > NOW() - INTERVAL '7 days'
ORDER BY range_end DESC LIMIT 30;"
# decision branch:
#   < 1 chunk per 7d → chunking 不對；E5 audit V### compression
#   is_compressed = false 占 > 30% → compression policy 未跑
```

**Mitigation**：
- Budget 違反 → 暫停某些 high-cost strategy 的 replay；MIT + E5 review hypertable compression
- 連續 3d 違反 → SEV-1；M11 nightly disable 並 escalate

---

## 7. 5d Passive Slack Unack Auto-Escalate（per H-11 #6）

**Trigger**：M11 daily Slack report 連續 5d 收到 0 operator ack（per AMD-2026-05-21-01 inactivity ladder）。

**Auto-escalation 路徑**（自動，無需 on-call manual trigger）：

| 累積 unack 天數 | 自動行為 |
|---|---|
| 5d | 升 M3 `HEALTH_WARN` + Slack `#ops-warn` 升級通知；M11 nightly 持續 |
| 7d | 升 M3 `HEALTH_DEGRADED` + 暫停 LAL 1+2 auto-approval (fail-safe to Advisory)；Slack `#ops-critical` |
| 14d | Operator inactivity 觸發 AMD-2026-05-21-01 §3 opt-in scope 自動回 Advisory |

```bash
# Triage step 1 — 確認 5d unack 真實
psql -h trade-core -U openclaw -d openclaw -c "
SELECT report_date, sent_at, ack_at
FROM learning.m11_daily_reports
WHERE sent_at > NOW() - INTERVAL '14 days'
ORDER BY report_date DESC;"
# 若連 5+ row ack_at IS NULL → 5d unack
```

```bash
# Triage step 2 — 確認 auto-escalation 已執行
psql -h trade-core -U openclaw -d openclaw -c "
SELECT created_at, from_state, to_state, trigger_reason
FROM learning.health_state_transitions
WHERE trigger_reason LIKE '%m11_unack%'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY id DESC LIMIT 10;"
# expected: 應有 row trigger_reason = 'm11_unack_5d_to_warn' / 'm11_unack_7d_to_degraded'
# 如 5d unack 但 0 transition row → SEV-1 auto-escalate 路徑 regression
```

**Mitigation**：
- Operator 立刻 review 5d M11 reports + click ack（Console banner button）
- ack 後 M3 state 自動回 NORMAL；LAL fall-back 自動解除（per §11.5）
- 如 ack 流程斷裂 → §9 escalate；補 H-11 mitigation #6 audit

---

## 8. Self-Hosted PG `market.*` 故障 Fallback（per ADR-0038 cold start 例外）

**Trigger**：§4 Step 5 任一 `market.*` table 24h row count 異常低或為 0。

**ADR-0038 紀律**（per Decision 1 例外條款）：
- **首次 cold start** 場景下，新 strategy 在 self-hosted PG 累積期不足時，**仍走 self-hosted PG with degraded sample** + Slack warn；**不允許暫時走 vendor backfill 補洞**
- 任何向 Bybit historical API / 第三方 vendor / cross-exchange historical query 的 fallback **嚴禁**

```bash
# Triage step 1 — 確認 source dataset row count 與歷史 baseline
psql -h trade-core -U openclaw -d openclaw -c "
SELECT
  date_trunc('day', recorded_at) AS day,
  COUNT(*) AS n
FROM market.liquidations
WHERE recorded_at > NOW() - INTERVAL '7 days'
GROUP BY 1 ORDER BY 1 DESC;"
# decision branch:
#   今日 < 5d historical avg × 50% → SEV-2 ingestion 路徑問題（WS subscription / writer 故障）
#   今日 = 0 → SEV-1 ingestion 全斷
```

```bash
# Triage step 2 — 確認 WS writer 健康
ssh trade-core "tail -200 /tmp/openclaw/logs/engine.log | grep -E 'liquidations|public_trades' | tail -50"
# 看 subscription 狀態 / reconnect 嘗試 / per-symbol writer drops
```

**Mitigation**：
- WS writer 故障 → restart_all + 重新 subscribe；M11 跳過該夜 + Slack warn
- 紀律違反（vendor backfill attempted）→ SEV-1；§9 escalate；24h postmortem + ADR-0038 amendment 評估
- **絕不可**為了補 M11 nightly 而向 vendor historical API request（per ADR-0038 Decision 1 反模式 (a)）

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；§7 auto-escalation 路徑 regression；§8 ADR-0038 紀律違反；§6 budget 連 3d 違反。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator + MIT @here
- SEV-2：Slack `#ops-warn` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.m11_replay_runs` 最近 7d
- `learning.replay_divergence_log` 觸發 incident 的 type × severity 全 export
- `learning.m11_daily_reports` 7d ack 狀態
- `learning.decay_signals` 對應 strategy 7d（M7 input 驗）
- `learning.health_state_transitions` 對應 5d unack escalation row
- engine.log 最近 24h `m11_*` grep
- `market.*` table row count 7d trend

**Post-escalation action**：
- PM 30 min 內派 MIT review M11 ↔ M7 dedup + ADR-0038 historical source 紀律
- 24h 內補 postmortem `docs/audits/<date>--m11_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# M11 Divergence Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Divergence type(s): <list of 5-7>
- Severity: <NOISE/WARN/CRITICAL/HALT>
- Strategy(ies) affected: <list>
- Operator ack delay: <hr or day>
- ADR-0038 source rule 是否被尊重: <yes/no>
- M7 dedup contract 是否被尊重: <yes/no>

## Timeline (UTC)
- T+0: nightly run started
- T+N: divergence detected
- T+M: ack / escalation

## Root cause
- Production 邏輯漂移 / replay engine 過時 / hypertable budget 違反？
- 5d unack auto-escalate 是否準時觸發？
- self-hosted PG ingestion 是否健康？

## Mitigation
- 即時 mitigation (§5/§6/§7/§8 對應)
- 永久 mitigation（V107 schema / M11 ADR / threshold 調整 / hypertable 補）

## Action items
- [ ] V107 schema constraint 補
- [ ] M11 threshold 重 calibrate（5d empirical baseline 更新）
- [ ] ADR-0038 amendment 對應紀律
- [ ] runbook §X 更新

## 12-week trend
- 加入 monthly M11 trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard 含 M11 section：
- 4 週 / 12 週 divergence count by type × severity
- Nightly budget violation count
- 5d unack auto-escalate trigger 次數
- M11 → M7 input emit rate vs M7 multi-source confirm rate
- self-hosted PG ingestion 健康度

Dashboard：`http://localhost:8001/console#replay/m11` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

> **本 runbook 同時是 counterfactual quality 月報的 daily-evidence input**；月報生成 SOP 見對應 runbook（cross-ref §11）。

---

## 11. Cross-References

- **v5.8 §2 M11**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:391-423`（continuous nightly replay + 5-7 divergence type + 4h budget）
- **v5.8 §11.5 + §11 #6**：同上 line 887-896（5d unack auto-escalate H-11 #6）
- **ADR-0038**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（self-hosted PG only + Decision 1-5）
- **CR-7 spec**：`docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`（threshold 統計推導 + M7 dedup contract + DECAY_ENFORCED rename + V107 schema CHECK）
- **ADR-0034 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（M11 不繞 lease 路徑；HEALTH_DEGRADED → LAL fallback）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（M11 daily report 屬 opt-in；inactivity ladder）
- **V107 schema spec**（pending CR-8）：`docs/execution_plan/specs/2026-05-21--v107-replay-divergence-log.md`（hypertable + CHECK constraint demote IS NULL）
- **M7 runbook**：`docs/runbooks/2026-05-21--m7_decay_alert_runbook.md`（§8 M7 ↔ M11 dedup verify）
- **M3 runbook**：`docs/runbooks/2026-05-21--m3_health_oncall_runbook.md`（5d unack → HEALTH_WARN → DEGRADED）
- **Counterfactual quality report runbook**：`docs/runbooks/2026-05-21--counterfactual_quality_report_runbook.md`（月報生成 SOP）
- **REF-21 replay 範式**：`docs/runbooks/ref21_replay_operator_runbook.md`（one-click replay 風格參考）
- **既有 H0 runbook（風格參考）**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **Metric dashboard**：`http://localhost:8001/console#replay/m11`（pending）
- **Healthcheck integration**：`helper_scripts/db/passive_wait_healthcheck.py --check m11_nightly_budget` + `--check m11_dedup_contract`（pending）

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；5-7 divergence type × 4-level severity matrix + 4h budget + 5d unack auto-escalate (H-11 #6) + self-hosted PG fallback（ADR-0038 Decision 1）+ M7 dedup contract verify SOP |

---

*OpenClaw / Arcane Equilibrium Runbook — M11 nightly replay divergence triage SOP (Draft — V107 schema + ADR-0038 + CR-7 dedup land 後 v1 promote)*
