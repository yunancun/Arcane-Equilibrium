# M7 Decay Signal 告警 SOP

**狀態：** Draft（Sprint 1A-β deliverable；V113 schema + DECAY_ENFORCED rename + M11 dedup contract land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M7-DECAY-001
**Module：** M7 Strategy Decay Detection + Auto-Retirement
**Severity coverage：** SEV-1 / SEV-2 / SEV-3
**On-call role：** On-call PM + Operator + MIT（Allocator 提出 demote proposal；operator 14d review window 末必 click）
**Depends on：** v5.8 §2 M7 (line 253-277) / V113 schema (DECAY_ENFORCED rename per CR-7) / M11 dedup contract (per CR-7 — M7 single decay authority；M11 emit-only) / spec `docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` / ADR-0034 (LAL 1 auto-demote 路徑) / AMD-2026-05-15-01 (Stage 0R-4 命名來源)

> **Hands off — operator only**：14d review window 末 RECOVER / RETIRE 判定 **必由 operator 親手 click**；M7 auto-demote (50% size) 是 state machine 內部行為，**不可被 LAL override**（per §5）。

---

## 1. TL;DR / 用途

M7 是 v5.8 §2 M7 為 strategy alpha decay 自動偵測 + auto demote / retire 的 module。基於 4 decay signal source 在 6-state lifecycle FSM 上做 state transition（STAGE_LIVE → DECAY_DETECTED → STAGE_DEMOTE_PROPOSED → DECAY_ENFORCED → RECOVER / RETIRE）。

**核心治理立場**（per CR-7 dedup contract）：
- **M7 是 single decay authority** — 一筆 strategy demote / param shrink / cooldown 全經 M7 state machine
- **M11 是 input source 不是 independent demote 路徑** — M11 nightly counterfactual divergence CRITICAL = emit M7 input row，**不自行** trigger demote
- **M8 anomaly + Sharpe collapse + DD breach + N consecutive loss 同樣只 emit M7 input** — multi-source confirm 規則由 M7 內部判定
- 4 signal source ≥ 2 confirm → state transition；單一 source 只到 DECAY_DETECTED

本 runbook 規範 4 類事件：(a) **4 decay signal × lifecycle FSM 6 enum 響應矩陣** / (b) **14d × 50% 累積 mitigation 強制 SUSPENDED 處置**（per §5，**不被 LAL override**）/ (c) **retrain trigger cooldown 處置** / (d) **M11 dedup 確認 SOP**（per CR-7）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console / Slack 收到 `[M7] DECAY_DETECTED <strategy>` | `learning.decay_signals` 新 row + Slack alert | §4 triage |
| 某 strategy live size 突然 scale 到 50% | `trading.position_sizing_audit` + Console banner | §5 DECAY_ENFORCED |
| 14d review window 已到期 + 0 operator click | `learning.strategy_lifecycle.review_due_at` | §6 14d window 處置 |
| M11 nightly replay 報 CRITICAL divergence 但 strategy 未 demote | `learning.replay_divergence_log` + M7 input 缺 | §8 M11 dedup 驗證 |
| 同 strategy DECAY_ENFORCED 後 14d 內持續虧 | `trading.fills` 累計 PnL trend | §7 反向 attack 「14d × 50% 持續虧」mitigation |
| Retrain pipeline 觸發但 cooldown 未到 | `learning.retrain_audit` | §9 retrain cooldown |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-1** | M7 state machine 寫 live state 但繞過 5-gate（per §11.5 #6 contract）；或 M11 自行 demote 違反 dedup contract | < 5 min | Operator 立 emergency disable M7 auto path；PM 30 min 內加入；24h postmortem |
| **SEV-2** | DECAY_ENFORCED 14d 後仍未 operator click（無 RECOVER / RETIRE 決定）；或 retrain cooldown 違反 | < 30 min | On-call PM 推 Slack reminder；7d 升 P1 ticket；30d 強制 SUSPENDED |
| **SEV-3** | DECAY_DETECTED 後 single source 4h 內未升 DECAY_ENFORCED（multi-source confirm 等待中，預期行為） | < 4h | On-call PM 看 dashboard；無 escalate；登錄 12-week trend |

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 列當前 6-state FSM 各 enum 的 strategy 計數
psql -h trade-core -U openclaw -d openclaw -c "
SELECT decay_action_level, COUNT(*) FROM learning.strategy_lifecycle GROUP BY 1 ORDER BY 1;"
# expected: 6 enum: STAGE_LIVE / DECAY_DETECTED / STAGE_DEMOTE_PROPOSED / DECAY_ENFORCED / RECOVERED / RETIRED
# decision branch:
#   DECAY_ENFORCED count 突然 jump → §5
#   STAGE_DEMOTE_PROPOSED 累積 ≥ 30d → §6 14d window 失效
```

```bash
# Step 2 — 確認當前告警 strategy 的 4 source signal 各自狀態
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, source_signal, severity, payload->>'rolling_metric' AS metric, created_at
FROM learning.decay_signals
WHERE strategy_name = '<from alert>' AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY id DESC LIMIT 30;"
# 4 source: 'sharpe_30d' / 'drawdown_stage4_envelope' / 'n_consecutive_loss' / 'm11_replay_divergence'
# decision branch:
#   ≥ 2 source confirm → 應 DECAY_ENFORCED
#   = 1 source → 預期 DECAY_DETECTED 等 multi-source（SEV-3 正常）
```

```bash
# Step 3 — 驗 M11 dedup contract（M11 不可獨立 demote）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, divergence_severity, payload->>'demote_emitted' AS m11_demote
FROM learning.replay_divergence_log
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND divergence_severity = 'CRITICAL'
ORDER BY id DESC LIMIT 20;"
# expected: m11_demote IS NULL 或 'false'；如 'true' → SEV-1 dedup contract 違反
# 對應 V107 schema CHECK constraint：CHECK (severity IN ('NOISE','WARN','CRITICAL') AND demote IS NULL)
```

```bash
# Step 4 — 驗 4 source ≥ 2 confirm 規則
psql -h trade-core -U openclaw -d openclaw -c "
WITH src AS (
  SELECT strategy_name, COUNT(DISTINCT source_signal) AS source_count
  FROM learning.decay_signals
  WHERE created_at > NOW() - INTERVAL '24 hours'
    AND severity >= 'WARN'
  GROUP BY 1
)
SELECT sl.strategy_name, sl.decay_action_level, src.source_count
FROM learning.strategy_lifecycle sl JOIN src USING (strategy_name)
WHERE sl.decay_action_level IN ('DECAY_DETECTED', 'STAGE_DEMOTE_PROPOSED', 'DECAY_ENFORCED');"
# decision branch:
#   decay_action_level = 'DECAY_ENFORCED' 但 source_count < 2 → SEV-1 multi-source confirm 規則違反
#   decay_action_level = 'STAGE_LIVE' 但 source_count ≥ 2 → SEV-2 state machine 漏 transition
```

```bash
# Step 5 — 驗 5-gate inheritance（M7 auto-demote 必經 5/5 gate）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, strategy_name, gate_pass_count, payload->>'demote_action' AS action
FROM learning.lal_audit
WHERE payload->>'demote_action' = 'm7_auto_demote_50pct'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY id DESC LIMIT 20;"
# expected: gate_pass_count = 5；如 < 5 但 demote 已執行 → §11.5 #6 violation（SEV-1）
```

```bash
# Step 6 — 14d review window 倒數
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, decay_action_level, demote_at,
       demote_at + INTERVAL '14 days' AS review_due_at,
       (demote_at + INTERVAL '14 days' - NOW()) AS time_remaining
FROM learning.strategy_lifecycle
WHERE decay_action_level = 'DECAY_ENFORCED'
ORDER BY demote_at;"
# decision branch:
#   time_remaining < 0 → §6 處置（強制 SUSPENDED）
#   < 24h → Slack reminder operator
```

```bash
# Step 7 — Retrain cooldown 驗
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, last_retrain_at,
       NOW() - last_retrain_at AS elapsed,
       cooldown_interval
FROM learning.retrain_audit
WHERE last_retrain_at > NOW() - INTERVAL '30 days'
ORDER BY last_retrain_at DESC LIMIT 20;"
# decision branch:
#   elapsed < cooldown_interval 但 retrain 已執行 → §9 cooldown violation
```

```bash
# Step 8 —（only if SEV-1）emergency disable M7 auto path
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"auto_demote":false}' \
  http://localhost:8001/api/v1/m7/config
# 預期 effect：decay_signals 持續寫 V113；state transition 寫 row 但 demote action 停
# §9 escalate；24h postmortem 必補
```

---

## 5. Mitigation — 4 Decay Signal × Lifecycle FSM 6 Enum 響應矩陣

### 5.1 響應矩陣（per CR-7 multi-source confirm + LAL 對齊）

| Signal source ↓ / FSM state → | STAGE_LIVE | DECAY_DETECTED | STAGE_DEMOTE_PROPOSED | DECAY_ENFORCED | RECOVERED | RETIRED |
|---|---|---|---|---|---|---|
| **Sharpe rolling 30d 跌破 threshold** | → DECAY_DETECTED（emit input） | 等 multi-source confirm | Allocator 已 propose | 已執行 50% size；繼續寫 input | recover 後 input 清零 | 已 retire 不適用 |
| **DD exceeds Stage 4 envelope max** | → DECAY_DETECTED | 等 confirm | propose | 已執行 | recover | n/a |
| **N consecutive loss > 2σ historical** | → DECAY_DETECTED | 等 confirm | propose | 已執行 | recover | n/a |
| **M11 replay divergence CRITICAL** | → DECAY_DETECTED（emit-only） | M11 不可獨立升 | propose | input 持續紀錄 | recover | n/a |

**核心紀律**（per §11.5 + CR-7）：
- 任一 single source → DECAY_DETECTED（observation；不寫 live state）
- ≥ 2 source confirm → STAGE_DEMOTE_PROPOSED（Allocator 提案）
- Operator approve OR LAL 1 auto-approve → DECAY_ENFORCED（50% size）
- M7 auto-demote 路徑 = LAL 1 always-on（per §11.5 #6）；M7 不被 LAL 3/4 override

### 5.2 14d review window 必經 Operator click

```
DECAY_ENFORCED 進入後 14d review window：
  Day 0-13: live size = 50%；M7 持續觀察 signal source 變化
  Day 14:
    - Operator click "RECOVER" → state → RECOVERED + 走 ramp-up（per AMD-2026-05-15-01 manual ramp）
    - Operator click "RETIRE" → state → RETIRED + live size = 0
    - 0 operator click → §6 強制 SUSPENDED（不可被 LAL override，per §11.5 反向 attack #4）
```

### 5.3 Rollback option

如 M7 state machine 行為本身 regression（如自動 retire 不留 14d window）：

```bash
# Emergency unlatch — 強制把 strategy 拉回 DECAY_DETECTED（observation only）
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"strategy":"<name>", "force_state":"DECAY_DETECTED", "reason":"<rca>"}' \
  http://localhost:8001/api/v1/m7/force_state
# 預期 effect：state 回 DECAY_DETECTED；live size 自動回 100%（如已 demote）
# 預期 audit：force_applied=true + 24h postmortem 必補
# 立刻 §10 escalate
```

---

## 6. 14d × 50% 累積 Mitigation — 強制 SUSPENDED 處置（不被 LAL override）

**Trigger**（per §11.5 反向 attack #4）：
- DECAY_ENFORCED 14d review window 結束 + 0 operator click → 強制 SUSPENDED
- 或 DECAY_ENFORCED 14d 內持續虧損（每日累計 PnL 連 14d < 0）→ 提前強制 SUSPENDED

```bash
# Mitigation step 1 — 強制 SUSPENDED
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"strategy":"<name>", "force_state":"SUSPENDED", "reason":"14d_no_ack OR 14d_continued_loss"}' \
  http://localhost:8001/api/v1/m7/force_state
# 預期 effect：state → SUSPENDED；live size = 0；Slack alert PM + operator
```

```bash
# Mitigation step 2 — 確認 LAL 不會 auto-recover
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, payload->>'lal_override_attempted' AS override
FROM learning.lal_audit
WHERE payload->>'strategy' = '<name>'
  AND payload->>'demote_action' IN ('lal_override_recover', 'auto_recover')
  AND created_at > NOW() - INTERVAL '1 hour';"
# expected: 0 row（SUSPENDED 不被 LAL override；per §11.5 #6）
# 如 ≥ 1 row → SEV-1 dedup contract 違反
```

**SUSPENDED → 後續 path**：
- Operator manual review + 完整 Stage 0R replay preflight + Stage 1 重啟（per AMD-2026-05-15-01）
- 不接受 LAL 1 / LAL 2 auto path 把 SUSPENDED 拉回 STAGE_LIVE
- SUSPENDED ≥ 90d 不被 review → 自動轉 RETIRED（archival）

---

## 7. Retrain Trigger Cooldown 處置

**Cooldown 規則**：M7 觸發 retrain pipeline 需符合 cooldown（per `learning.retrain_audit.cooldown_interval`）：
- Default cooldown = 7 days per strategy（防 thrash）
- DECAY_ENFORCED 觸發的 retrain = 立即 allow（cooldown 不阻）
- RECOVERED 後 retrain = cooldown apply

```bash
# Triage — retrain history + cooldown
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, last_retrain_at, cooldown_interval,
       (last_retrain_at + cooldown_interval) AS next_allowed_at
FROM learning.retrain_audit
ORDER BY last_retrain_at DESC LIMIT 30;"
```

如 cooldown 內 retrain 已執行 → 視為 violation：
1. 確認 trigger reason（DECAY_ENFORCED bypass cooldown 是 by-design；其他 reason violation）
2. SEV-2；§10 escalate；24h 修 retrain orchestrator + 補 postmortem

---

## 8. M11 Dedup 確認 SOP（per CR-7）

**Invariant**（per CR-7 + ADR-0038 + M11 spec）：
- M11 nightly replay 報 divergence → **emit-only**（寫 V107 row + emit M7 input）
- M11 **不自行** demote / size shrink / state transition
- V107 schema CHECK constraint：`CHECK (severity IN ('NOISE','WARN','CRITICAL') AND demote IS NULL)`

```bash
# Verify 1 — V107 schema constraint 存在
psql -h trade-core -U openclaw -d openclaw -c "
SELECT conname, pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_class t ON c.conrelid = t.oid
WHERE t.relname = 'replay_divergence_log' AND conname LIKE '%severity%';"
# expected: CHECK (severity IN ('NOISE','WARN','CRITICAL')) + 禁 demote column
```

```bash
# Verify 2 — M11 CRITICAL divergence 必對應 M7 input row（dedup ↔ multi-source confirm）
psql -h trade-core -U openclaw -d openclaw -c "
WITH m11 AS (
  SELECT strategy_name, MAX(created_at) AS last_critical
  FROM learning.replay_divergence_log
  WHERE divergence_severity = 'CRITICAL'
    AND created_at > NOW() - INTERVAL '24 hours'
  GROUP BY 1
)
SELECT m11.strategy_name, m11.last_critical,
       EXISTS (SELECT 1 FROM learning.decay_signals ds
               WHERE ds.strategy_name = m11.strategy_name
                 AND ds.source_signal = 'm11_replay_divergence'
                 AND ds.created_at >= m11.last_critical) AS m7_input_emitted
FROM m11;"
# expected: m7_input_emitted = true 全部 row
# 如 false → M11 → M7 emit 路徑斷裂（SEV-1）
```

```bash
# Verify 3 — 4 source ≥ 2 confirm 規則生效
# （per §4 Step 4 SQL；M11 CRITICAL 是 1 source；需另一 source confirm 才升 DEMOTE_PROPOSED）
```

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；§5 mitigation 失敗；§6 強制 SUSPENDED 被 LAL override；§8 M11 dedup contract 違反。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator + MIT @here
- SEV-2：Slack `#ops-warn` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.strategy_lifecycle` 對應 strategy row（full history via `audit_history` join）
- `learning.decay_signals` 對應 strategy 7d 全 export
- `learning.replay_divergence_log` 對應 strategy 7d
- `learning.lal_audit` 涉及 demote action 的 7d row
- `learning.retrain_audit` 對應 strategy history
- engine.log 最近 1h `m7_*` + `decay_*` grep

**Post-escalation action**：
- PM 30 min 內派 MIT review M7 state machine + M11 dedup contract
- 24h 內補 postmortem `docs/audits/<date>--m7_<strategy>_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# M7 Decay Incident Postmortem — <strategy> · <YYYY-MM-DD>

## TL;DR
- Strategy: <name>
- State trajectory: STAGE_LIVE → DECAY_DETECTED → ... → DECAY_ENFORCED / SUSPENDED / RETIRED
- Trigger signal(s): <list of 4 source>
- Multi-source confirm count at transition: <N>
- Operator action(s): <RECOVER / RETIRE / 0 click>
- LAL override attempts (should be 0): <N>

## Timeline (UTC)
- T+0: <first DECAY_DETECTED emit>
- T+N: <transition step>

## Root cause
- Strategy alpha 真實 decay vs 環境 transient vs M7 FP？
- M11 dedup contract 是否被尊重？
- 14d review window 內 operator click 是否準時？

## Mitigation
- 即時 mitigation（§5 / §6 對應）
- 永久 mitigation（V113 schema / M7 ADR / signal threshold 調整）

## Action items
- [ ] V113 schema constraint 補
- [ ] M7 multi-source confirm 規則調整
- [ ] runbook §X 更新
- [ ] M11 V107 schema CHECK constraint 補

## 12-week trend
- 加入 monthly M7 trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard 含 M7 section：
- 4 週 / 12 週 DECAY_DETECTED count by strategy
- DECAY_ENFORCED → RECOVER vs RETIRE 比例
- 強制 SUSPENDED 觸發次數
- M11 input emit count vs DECAY_DETECTED transition 比

Dashboard：`http://localhost:8001/console#strategy/m7` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **v5.8 §2 M7**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:253-277`（4 decay signal + 6-state FSM + 14d review）
- **v5.8 §11.5 #6**：同上 line 875（M7 auto-demote 5-gate inheritance + multi-source confirm）
- **CR-7 spec**：`docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`（M7 single decay authority + DECAY_ENFORCED rename + V107 schema CHECK constraint + state machine 5 transitions）
- **ADR-0034 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 1 auto-demote 路徑；M7 不被 LAL 3/4 override）
- **ADR-0038 M11**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（M11 emit-only nightly）
- **AMD-2026-05-15-01**：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（Stage 0R-4 命名；RECOVER 後 manual ramp）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（M7 demote 屬 opt-in scope）
- **V113 schema spec**（pending CR-8）：`docs/execution_plan/specs/2026-05-21--v113-decay-signals.md`（hypertable + DECAY_ENFORCED enum）
- **M11 runbook**：`docs/runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md`（M11 → M7 input 路徑）
- **M3 runbook**：`docs/runbooks/2026-05-21--m3_health_oncall_runbook.md`（HEALTH_DEGRADED → strategy domain 6 對應）
- **既有 H0 runbook（風格參考）**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **Metric dashboard**：`http://localhost:8001/console#strategy/m7`（pending）
- **Healthcheck integration**：`helper_scripts/db/passive_wait_healthcheck.py --check m7_state_consistency` + `--check m7_m11_dedup_contract`（pending）

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；4 source × 6 FSM enum 響應矩陣 + 14d × 50% 強制 SUSPENDED + M11 dedup SOP + retrain cooldown + 6 反向 attack mitigation 對應 M7 |

---

*OpenClaw / Arcane Equilibrium Runbook — M7 decay signal 告警 SOP (Draft — V113 schema + DECAY_ENFORCED rename + CR-7 dedup land 後 v1 promote)*
